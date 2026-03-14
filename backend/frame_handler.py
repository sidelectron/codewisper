"""Screen frame processing utilities for CodeWhisper backend."""

import base64
import logging
from io import BytesIO

from PIL import Image

logger = logging.getLogger("codewhisper")

JPEG_MAGIC = bytes([0xFF, 0xD8])
DEFAULT_TARGET_SIZE = 768


def validate_frame(data: str) -> bytes | None:
    """Decode base64 frame string and validate as JPEG.

    Args:
        data: Base64-encoded JPEG string, or data URL (data:image/jpeg;base64,...).

    Returns:
        Raw JPEG bytes if valid, None if invalid.
    """
    if not data:
        return None
    if data.startswith("data:image/jpeg;base64,"):
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data, validate=True)
    except Exception as e:
        logger.debug(f"Frame base64 decode failed: {e}")
        return None

    if len(raw) < 2:
        return None
    if raw[:2] != JPEG_MAGIC:
        logger.debug("Frame missing JPEG magic number")
        return None

    try:
        Image.open(BytesIO(raw)).verify()
    except Exception as e:
        logger.debug(f"Frame JPEG validation failed: {e}")
        return None

    return raw


def resize_frame(image_bytes: bytes, target_size: int = DEFAULT_TARGET_SIZE) -> bytes:
    """Resize JPEG to target_size x target_size if needed.

    Args:
        image_bytes: Raw JPEG bytes.
        target_size: Target width and height (default 768).

    Returns:
        Raw JPEG bytes (resized if necessary).
    """
    if not image_bytes:
        return image_bytes
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        logger.warning(f"Frame open failed: {e}")
        return image_bytes

    w, h = img.size
    if w == target_size and h == target_size:
        return image_bytes

    img = img.resize((target_size, target_size), Image.Resampling.LANCZOS)
    out = BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()


def encode_frame_for_gemini(image_bytes: bytes) -> str:
    """Encode raw JPEG bytes as base64 for sending as image blob (e.g. to ADK queue).

    Args:
        image_bytes: Raw JPEG bytes.

    Returns:
        Base64-encoded string.
    """
    return base64.b64encode(image_bytes).decode("ascii")
