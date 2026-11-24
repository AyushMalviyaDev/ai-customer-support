import logging
from app.ai.agent import write_reply
from app.ai.classifier import classify
from app.ai.rules import CUSTOMER_STEPS, resolve_issue
from app.ai.schemas import Decision
from app.ai.vision import inspect_image

logger = logging.getLogger(__name__)


def decide(thread: str, attachments: list[dict] | None = None) -> Decision:
    """Run the AI steps for one email thread. The models propose, this function decides."""
    visual_context = []
    has_damage_photo = False
    damage_details = []

    if attachments:
        for att in attachments:
            mime = att.get("mime_type", "").lower()
            data = att.get("data")
            filename = att.get("filename", "unknown")
            is_image = mime.startswith("image/") or any(
                filename.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")
            )

            if is_image and data:
                try:
                    result = inspect_image(data, mime or "image/jpeg", filename)
                    visual_context.append(
                        f"[Attachment {filename} Analysis: {result.summary}]"
                    )
                    if result.damage_detected:
                        has_damage_photo = True
                        damage_details.append(
                            f"{result.furniture_type or 'Item'}: {result.damage_description or 'Damage visible'}"
                        )
                    if result.is_layout_or_blueprint and result.dimensions_or_specs:
                        visual_context.append(
                            f"[Layout Dimensions/Specs: {result.dimensions_or_specs}]"
                        )
                except Exception as e:
                    logger.warning("Failed to analyze image attachment %s: %s", filename, e)
            else:
                visual_context.append(f"[Non-image attachment included: {filename}]")

    enriched_thread = thread
    if visual_context:
        enriched_thread += "\n\n--- Attachment Inspections ---\n" + "\n".join(visual_context)

    classification = classify(enriched_thread)

    def escalate(reason: str, proposed_action: str | None = None) -> Decision:
        return Decision(
            action="escalate",
            section=classification.section,
            reply=classification.acknowledgement,
            reason=reason,
            proposed_action=proposed_action,
        )

    # If physical damage is visually confirmed from customer photos, escalate for claims review
    if has_damage_photo:
        details_str = "; ".join(damage_details)
        return escalate(
            f"Customer submitted photos showing verified damage: {details_str}",
            proposed_action="Review photo evidence and process warranty/replacement claim",
        )

    # If non-image attachments or other attachments could not be analyzed, safely escalate
    if attachments and not visual_context:
        return escalate("The email has unverified attachments")

    if classification.needs_human:
        return escalate(classification.reason)

    answer = write_reply(enriched_thread, classification.section)
    if answer.action == "escalate":
        return escalate(answer.reasoning)
    if not answer.enough_information:
        return escalate("The knowledge base does not answer this")
    if answer.issue:
        step = resolve_issue(answer.issue)
        if step not in CUSTOMER_STEPS:
            return escalate(f"Next step: {step}", proposed_action=step)
    if answer.promises_an_action:
        return escalate("The reply promises an action")

    return Decision(
        action="reply",
        section=classification.section,
        reply=answer.reply,
        reason=answer.reasoning,
    )
