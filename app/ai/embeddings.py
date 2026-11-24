import logging
import os
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSION = 768

_client: genai.Client | None = None


def get_genai_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GOOGLE_API_KEY")
        _client = genai.Client(api_key=api_key)
    return _client


def get_embedding(text: str) -> list[float]:
    """Generate 768-dimensional text embedding using Gemini."""
    client = get_genai_client()
    try:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSION),
        )
        return response.embeddings[0].values
    except Exception as e:
        logger.error("Failed to generate embedding: %s", e)
        raise
