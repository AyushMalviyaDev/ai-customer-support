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
        _pool.close()
        _pool = None


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
    ticket_id: int, status: str, category: str | None = None, proposed_action: str | None = None
) -> None:
    with connect() as conn:
        conn.execute(
            """
            update tickets
            set status = %s, category = coalesce(%s, category),
                proposed_action = %s, updated_at = now()
            where id = %s
            """,
            (status, category, proposed_action, ticket_id),
        )


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

