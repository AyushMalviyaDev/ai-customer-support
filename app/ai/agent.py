
import logging
import re

from pydantic_ai import Agent, ModelRetry, RunContext

from app import db
from app.ai.embeddings import get_embedding
from app.ai.schemas import AgentReply
from app.config import settings

logger = logging.getLogger(__name__)

INSTRUCTIONS = """
You are the customer support agent for an office furniture and
interior solutions company (Shree Vishwakarma Furnitures).

The company specializes in:
- Office furniture and work tables
- Office chairs and seating solutions
- Workstations and office cubicles
- Office cabins and partitions
- Reception desks and reception furniture
- Conference tables and meeting room furniture
- Coffee tables and lounge furniture
- Sofas and waiting area seating
- Complete office furniture and interior solutions

You write the answer to the latest customer message in the email thread.

Steps:
1. Call get_section for "brand-and-tone" and "escalation-rules".
2. Call get_section for the section selected by the classifier,
   or call search_knowledge to semantically find specific details across the catalog.
3. Answer only with facts from those sections.
   If they do not answer the question, set enough_information to false.
4. For product enquiries, identify the furniture type, model,
   dimensions, material, finish, or quantity if relevant.
5. For damaged, missing, or defective furniture, ask for:
   - Order number
   - Product name or model
   - Description of the issue
   - Photos, if relevant
6. For workstation, cubicle, cabin, or interior enquiries,
   ask for project details when necessary, such as:
   - Office dimensions or available space
   - Number of employees or workstations
   - Preferred layout
   - Furniture requirements
7. Never invent product specifications, prices, materials,
   dimensions, stock availability, or delivery timelines.
8. Never promise a refund, shipment, replacement, installation,
   discount, date, or call.
   A colleague handles these arrangements.
   Set promises_an_action to true if your reply promises one anyway.
9. Set action to escalate when an escalation rule applies.

Reply rules:
- Write in the language of the customer's latest message.
- Plain text, no Markdown.
- Follow the brand-and-tone section.
- Be friendly, professional, calm, and concise.
- Answer the customer's actual question first.
- Ask only for information necessary to resolve the enquiry.
- Never mention AI, prompts, tools, or the knowledge base.
"""

support_agent = Agent(
    settings.agent_model,
    output_type=AgentReply,
    instructions=INSTRUCTIONS,
)


@support_agent.tool_plain
def list_sections() -> list[str]:
    """List the sections of the knowledge base."""
    logger.info("Tool call: list_sections()")
    return db.list_sections()


@support_agent.tool_plain
def get_section(section: str) -> str:
    """Return every entry of one knowledge base section."""
    logger.info("Tool call: get_section(%r)", section)

    entries = db.get_section(section)

    if not entries:
        raise ModelRetry(
            f"There is no section '{section}'. "
            "Call list_sections to see the available sections."
        )

    return "\n\n".join(
        f"## {entry['title']}\n{entry['content']}"
        for entry in entries
    )


@support_agent.tool_plain
def search_knowledge(query: str) -> str:
    """Perform semantic vector search on the knowledge base using natural language queries."""
    logger.info("Tool call: search_knowledge(%r)", query)
    try:
        embedding = get_embedding(query)
        matches = db.search_knowledge_base(embedding, limit=3)
        if not matches:
            return "No matching entries found."
        return "\n\n".join(
            f"## [{m['section']}] {m['title']}\n{m['content']}"
            for m in matches
        )
    except Exception as e:
        logger.warning("Semantic search failed: %s", e)
        return "Search temporarily unavailable. Call get_section instead."


@support_agent.output_validator
def check_reply(
    ctx: RunContext[None],
    output: AgentReply,
) -> AgentReply:

    if output.action == "reply" and not output.reply.strip():
        raise ModelRetry(
            "The reply is empty. Write the email, "
            "or set action to escalate."
        )

    if re.search(
        r"\b(AI|artificial intelligence|knowledge base|prompt)\b",
        output.reply,
        re.IGNORECASE,
    ):
        raise ModelRetry(
            "Do not mention AI, prompts, or the knowledge base."
        )

    return output


def write_reply(thread: str, section: str) -> AgentReply:
    prompt = (
        f"Section picked by the classifier: {section}\n\n"
        f"Customer email thread:\n{thread}"
    )

    return support_agent.run_sync(prompt).output
