import logging
from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent

from app.config import settings

logger = logging.getLogger(__name__)


class ImageInspectionResult(BaseModel):
    is_furniture_related: bool = Field(
        description="True if the image contains office furniture, seating, workstations, cubicles, cabins, interior layouts, or packaging"
    )
    furniture_type: str | None = Field(
        default=None,
        description="e.g. ergonomic chair, executive desk, workstation partition, meeting table, modular cabin",
    )
    damage_detected: bool = Field(
        default=False,
        description="True if physical damage, defects, cracks, tears, broken parts, or missing components are visible",
    )
    damage_description: str | None = Field(
        default=None,
        description="Detailed description of visible damage, defect, or wear, if any",
    )
    is_layout_or_blueprint: bool = Field(
        default=False,
        description="True if the image is an architectural floor plan, office layout sketch, or dimension blueprint",
    )
    dimensions_or_specs: str | None = Field(
        default=None,
        description="Any measurements, seat counts, room dimensions, or model labels extracted from the image",
    )
    summary: str = Field(
        description="Objective summary of what is visible in the image for support staff and agent context"
    )


VISION_INSTRUCTIONS = """
You are a multimodal computer vision specialist for Shree Vishwakarma Furnitures, an office furniture and interior solutions company.

Analyze customer-submitted attachment images.
Tasks:
1. Identify if the image contains office furniture, cubicles, chairs, conference tables, executive cabins, or office layout drawings.
2. If the customer reports an issue or damage, inspect closely for broken wheels, torn upholstery, damaged wood/laminate edges, bent metal frames, broken hydraulic mechanisms, or missing parts.
3. If the image is a room layout, architectural plan, or blueprint, extract room dimensions, employee count, or layout requirements.
4. If the image is unrelated spam or offensive content, mark is_furniture_related as false.
5. Provide a factual, concise summary of your visual findings.
"""

vision_agent = Agent(
    settings.agent_model,
    output_type=ImageInspectionResult,
    instructions=VISION_INSTRUCTIONS,
)


def inspect_image(image_bytes: bytes, mime_type: str, filename: str) -> ImageInspectionResult:
    """Analyze a customer-attached image using Gemini Vision."""
    logger.info("Running vision inspection on %s (%s)", filename, mime_type)
    content = [
        f"Please inspect this customer-submitted attachment: {filename}",
        BinaryContent(data=image_bytes, media_type=mime_type),
    ]
    return vision_agent.run_sync(content).output
