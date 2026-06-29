"""Logo image processing: validate -> re-encode -> resize -> WebP.

The re-encode is the security crux: opening the upload and writing a fresh WebP
neutralises any payload embedded in the original bytes. We also validate by magic
bytes (Pillow), reject SVG (XSS-capable), strip EXIF, and cap dimensions.
"""

import io

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.common.exceptions import DomainError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def process_logo(uploaded, *, max_px: int = 512) -> ContentFile:
    """Return a sanitised, resized WebP ContentFile, or raise DomainError."""
    if uploaded.size > MAX_UPLOAD_BYTES:
        raise DomainError("Image is too large (max 10 MB).", code="image_too_large")
    try:
        Image.open(uploaded).verify()  # integrity / magic-byte check
        uploaded.seek(0)  # verify() consumes the file; reopen
        img = Image.open(uploaded)
    except (UnidentifiedImageError, OSError) as exc:
        raise DomainError("That file isn't a valid image.", code="image_invalid") from exc

    if img.format not in ALLOWED_FORMATS:  # excludes SVG and anything exotic
        raise DomainError("Use a JPG, PNG or WebP image.", code="image_unsupported")

    img = ImageOps.exif_transpose(img)  # apply rotation, then EXIF is gone
    img = img.convert("RGB")
    img.thumbnail((max_px, max_px))  # cap size, keep aspect ratio

    out = io.BytesIO()
    img.save(out, format="WEBP", quality=82, method=6)
    return ContentFile(out.getvalue())
