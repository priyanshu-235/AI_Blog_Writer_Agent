from __future__ import annotations

import os

from backend.config import IMAGE_MODEL


def create_diagram_bytes(prompt: str) -> bytes:
    from google import genai
    from google.genai import types

    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY missing.")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )

    image_parts = getattr(response, "parts", None)

    if not image_parts and getattr(response, "candidates", None):
        image_parts = response.candidates[0].content.parts

    if not image_parts:
        raise RuntimeError("Gemini returned no image.")

    for part in image_parts:
        inline_data = getattr(part, "inline_data", None)

        if inline_data and getattr(inline_data, "data", None):
            return inline_data.data

    raise RuntimeError("No image bytes found.")
