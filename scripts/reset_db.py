"""Utility script to reset and clean up database tables."""
import sys
from app import db


def reset_tickets_and_events() -> None:
    """Clear all customer tickets, email messages, and processing event logs."""
    with db.connect() as conn:
        conn.execute("TRUNCATE TABLE messages, tickets, events RESTART IDENTITY CASCADE;")
        t_count = conn.execute("SELECT count(*) as c FROM tickets").fetchone()["c"]
        m_count = conn.execute("SELECT count(*) as c FROM messages").fetchone()["c"]
        e_count = conn.execute("SELECT count(*) as c FROM events").fetchone()["c"]
        print(f"✓ Cleared customer data: tickets={t_count}, messages={m_count}, events={e_count}")


def reset_knowledge_base() -> None:
    """Clear the knowledge base entries and pgvector embeddings."""
    with db.connect() as conn:
        conn.execute("TRUNCATE TABLE knowledge_base RESTART IDENTITY CASCADE;")
        k_count = conn.execute("SELECT count(*) as c FROM knowledge_base").fetchone()["c"]
        print(f"✓ Cleared knowledge base: entries={k_count}")


def main() -> None:
    print("\n--- Resetting Database ---")
    reset_tickets_and_events()
    print("Database reset complete! Your dashboard is now clean and empty.\n")
    db.close_pool()


if __name__ == "__main__":
    main()
