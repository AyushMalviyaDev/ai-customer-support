from pathlib import Path
from app import db
from app.ai.embeddings import get_embedding


def parse(path: Path) -> list[tuple[str, str, str]]:
    """Split a section file into (section, title, content) rows, one per ## heading."""
    entries = []
    for block in path.read_text(encoding="utf-8").split("\n## ")[1:]:
        title, _, content = block.partition("\n")
        entries.append((path.stem, title.strip(), content.strip()))
    return entries


def main() -> None:
    print("Seeding knowledge base and generating Gemini embeddings...")
    for path in sorted(Path("knowledge_base").glob("*.md")):
        rows = parse(path)
        for section, title, content in rows:
            text_to_embed = f"Section: {section}\nTitle: {title}\nContent:\n{content}"
            embedding = get_embedding(text_to_embed)
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            with db.connect() as conn:
                conn.execute(
                    """
                    insert into knowledge_base (section, title, content, embedding)
                    values (%s, %s, %s, %s::vector)
                    on conflict (section, title) do update
                      set content = excluded.content,
                          embedding = excluded.embedding,
                          updated_at = now()
                    """,
                    (section, title, content, embedding_str),
                )
        print(f"✓ {path.stem}: {len(rows)} entries embedded and indexed")
    db.close_pool()
    print("Knowledge base seeding with vector embeddings complete!")


if __name__ == "__main__":
    main()
