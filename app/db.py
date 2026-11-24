import atexit
from contextlib import contextmanager
from typing import Generator
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=10,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )
    return _pool


@contextmanager
def connect() -> Generator[psycopg.Connection, None, None]:
    """Provide a connection from the connection pool."""
    with get_pool().connection() as conn:
        yield conn


def close_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            _pool.close(timeout=2.0)
        except Exception:
            pass
        _pool = None


atexit.register(close_pool)


def start_event(gmail_message_id: str) -> dict | None:
    """Claim a message. Returns None when it is already handled or in progress."""
    with connect() as conn:
        return conn.execute(
            """
            insert into events (gmail_message_id) values (%s)
            on conflict (gmail_message_id) do update
              set attempts = events.attempts + 1, status = 'processing', error = null
              where events.status = 'failed'
            returning id, attempts
            """,
            (gmail_message_id,),
        ).fetchone()


def finish_event(event_id: int, status: str, result: dict) -> None:
    with connect() as conn:
        conn.execute(
            "update events set status = %s, result = %s, processed_at = now() where id = %s",
            (status, Jsonb(result), event_id),
        )


def fail_event(event_id: int, error: str) -> None:
    with connect() as conn:
        conn.execute(
            "update events set status = 'failed', error = %s where id = %s",
            (error, event_id),
        )


def upsert_ticket(gmail_thread_id: str, customer_email: str, subject: str) -> int:
    with connect() as conn:
        row = conn.execute(
            """
            insert into tickets (gmail_thread_id, customer_email, subject)
            values (%s, %s, %s)
            on conflict (gmail_thread_id) do update set updated_at = now()
            returning id
            """,
            (gmail_thread_id, customer_email, subject),
        ).fetchone()
        return row["id"]


def update_ticket(
    ticket_id: int,
    status: str,
    category: str | None = None,
    proposed_action: str | None = None,
    draft_reply: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            update tickets
            set status = %s, category = coalesce(%s, category),
                proposed_action = coalesce(%s, proposed_action),
                draft_reply = coalesce(%s, draft_reply),
                updated_at = now()
            where id = %s
            """,
            (status, category, proposed_action, draft_reply, ticket_id),
        )


def get_tickets(status: str | None = None, limit: int = 50) -> list[dict]:
    """Retrieve tickets, optionally filtered by status ('open', 'answered', 'escalated')."""
    with connect() as conn:
        if status:
            return conn.execute(
                """
                select id, gmail_thread_id, customer_email, subject, category,
                       status, proposed_action, draft_reply, created_at, updated_at
                from tickets
                where status = %s
                order by updated_at desc
                limit %s
                """,
                (status, limit),
            ).fetchall()
        else:
            return conn.execute(
                """
                select id, gmail_thread_id, customer_email, subject, category,
                       status, proposed_action, draft_reply, created_at, updated_at
                from tickets
                order by updated_at desc
                limit %s
                """,
                (limit,),
            ).fetchall()


def get_ticket_details(ticket_id: int) -> dict | None:
    """Retrieve a single ticket along with its complete message history."""
    with connect() as conn:
        ticket = conn.execute(
            "select * from tickets where id = %s",
            (ticket_id,),
        ).fetchone()
        if not ticket:
            return None
        messages = conn.execute(
            """
            select id, gmail_message_id, direction, from_address, body, created_at
            from messages
            where ticket_id = %s
            order by created_at asc
            """,
            (ticket_id,),
        ).fetchall()
        ticket["messages"] = messages
        return ticket


def get_stats() -> dict:
    with connect() as conn:
        total = conn.execute("select count(*) as count from tickets").fetchone()["count"]
        escalated = conn.execute("select count(*) as count from tickets where status = 'escalated'").fetchone()["count"]
        answered = conn.execute("select count(*) as count from tickets where status = 'answered'").fetchone()["count"]
        events = conn.execute("select count(*) as count from events").fetchone()["count"]
        return {
            "total_tickets": total,
            "escalated_tickets": escalated,
            "answered_tickets": answered,
            "total_events": events,
        }




def save_message(
    ticket_id: int, gmail_message_id: str, direction: str, from_address: str, body: str
) -> None:
    with connect() as conn:
        conn.execute(
            """
            insert into messages (ticket_id, gmail_message_id, direction, from_address, body)
            values (%s, %s, %s, %s, %s)
            on conflict (gmail_message_id) do nothing
            """,
            (ticket_id, gmail_message_id, direction, from_address, body),
        )


def list_sections() -> list[str]:
    with connect() as conn:
        rows = conn.execute("select distinct section from knowledge_base order by section").fetchall()
        return [row["section"] for row in rows]


def get_section(section: str) -> list[dict]:
    with connect() as conn:
        return conn.execute(
            "select title, content from knowledge_base where section = %s order by id",
            (section,),
        ).fetchall()


def search_knowledge_base(
    query_embedding: list[float], limit: int = 4, section: str | None = None
) -> list[dict]:
    """Perform approximate nearest-neighbor vector search using pgvector cosine distance."""
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    with connect() as conn:
        if section:
            return conn.execute(
                """
                select id, section, title, content,
                       1 - (embedding <=> %s::vector) as similarity
                from knowledge_base
                where section = %s and embedding is not null
                order by embedding <=> %s::vector
                limit %s
                """,
                (embedding_str, section, embedding_str, limit),
            ).fetchall()
        else:
            return conn.execute(
                """
                select id, section, title, content,
                       1 - (embedding <=> %s::vector) as similarity
                from knowledge_base
                where embedding is not null
                order by embedding <=> %s::vector
                limit %s
                """,
                (embedding_str, embedding_str, limit),
            ).fetchall()


def update_entry_embedding(section: str, title: str, embedding: list[float]) -> None:
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with connect() as conn:
        conn.execute(
            """
            update knowledge_base
            set embedding = %s::vector, updated_at = now()
            where section = %s and title = %s
            """,
            (embedding_str, section, title),
        )

