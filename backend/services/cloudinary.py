from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path


def configure_cloudinary() -> None:
    import cloudinary

    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    api_key = os.getenv("CLOUDINARY_API_KEY")
    api_secret = os.getenv("CLOUDINARY_API_SECRET")

    if not all([cloud_name, api_key, api_secret]):
        raise RuntimeError(
            "Cloudinary is not configured. "
            "Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, "
            "and CLOUDINARY_API_SECRET."
        )

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )


def upload_diagram_to_cloudinary(
    image_bytes: bytes,
    folder: str,
    public_id: str,
) -> dict:
    import cloudinary.uploader

    configure_cloudinary()

    result = cloudinary.uploader.upload(
        BytesIO(image_bytes),
        folder=folder,
        public_id=Path(public_id).stem,
        resource_type="image",
        overwrite=True,
    )

    url = result.get("secure_url")
    stored_public_id = result.get("public_id")

    if not url or not stored_public_id:
        raise RuntimeError("Cloudinary did not return upload metadata.")

    return {
        "secure_url": url,
        "public_id": stored_public_id,
        "resource_type": result.get("resource_type", "image"),
    }


def destroy_cloudinary_image(public_id: str) -> None:
    import cloudinary.uploader

    if not public_id:
        return

    configure_cloudinary()
    cloudinary.uploader.destroy(
        public_id,
        resource_type="image",
        invalidate=True,
    )
