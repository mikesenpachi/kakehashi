"""OCR: read the Japanese text in a screenshot, then clean it.

Engine: Google Lens, one call at a time. When Lens fails, read raises OCRError: nothing is read.
"""

import asyncio
import logging

from chrome_lens_py import LensAPI
from chrome_lens_py.exceptions import LensException
from PIL import Image

MARKERS = str.maketrans("", "", "▼>＞ ")

log = logging.getLogger(__name__)


class OCRError(Exception):
    """Google Lens could not read the image."""

# One Lens call at a time: requests that arrive together (a Vita shot and a "Test" click,
# or two devices) wait here, so Google never gets parallel calls from this webapp.
LENS_LOCK = asyncio.Lock()


async def read(image: Image.Image, box: tuple[float, float, float, float] | None = None) -> tuple[str, str]:
    """Return (raw OCR text, clean text) for an image.

    With a box (left, top, right, bottom as fractions 0 to 1), read only that part.
    """
    if box:
        left, top, right, bottom = box
        image = image.crop((left * image.width, top * image.height, right * image.width, bottom * image.height))
    try:
        async with LENS_LOCK:
            result = await lens_read(image)
    except LensException as error:
        log.warning("Google Lens failed: %s", error)
        raise OCRError(error) from error
    return result["ocr_text"], clean_lens(result["word_data"])


async def lens_read(image: Image.Image) -> dict:
    """Send one image to Google Lens (unofficial API) and close the client."""
    api = LensAPI()
    try:
        return await api.process_image(image, ocr_language="ja", ocr_preserve_line_breaks=False)
    finally:
        await api.aclose()


def clean_lens(words: list[dict]) -> str:
    """Join the Lens words into one string without furigana.

    Furigana words are much shorter than the main text, so words below
    60% of the tallest word height are dropped.
    """
    if not words:
        return ""
    tallest = max(word["geometry"]["height"] for word in words)
    return clean("".join(word["word"] for word in words if word["geometry"]["height"] >= 0.6 * tallest))


def clean(text: str) -> str:
    """Remove markers and spaces, and normalize the ellipsis."""
    return text.translate(MARKERS).replace("･･･", "…")
