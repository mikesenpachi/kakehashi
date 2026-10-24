# /// script
# requires-python = ">=3.12"
# dependencies = ["chrome-lens-py", "manga-ocr", "pillow"]
# ///
"""OCR test: run an OCR engine on a tight crop of each sample shot's text.

Compares the OCR output with samples/expected.tsv.
Run from the repo root: uv run experiments/ocr_test.py <engine>
Engines: manga, lens, lens-clean
"""

import asyncio
import sys
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image

SAMPLES = Path(__file__).parent.parent / "samples"

# Crop box (left, top, right, bottom) around the dialogue text lines, per game.
# Leaves out the speaker name and the box icons.
BOXES = {
    "time-travelers": (40, 425, 915, 544),
    "persona-4-golden": (50, 415, 880, 500),
}


def load_expected() -> list[tuple[str, str]]:
    """Return (relative path, expected text) pairs from expected.tsv."""
    lines = (SAMPLES / "expected.tsv").read_text(encoding="utf-8").splitlines()
    return [tuple(line.split("\t")) for line in lines if line]


def text_box(rel_path: str) -> Image.Image:
    """Crop the dialogue text lines, using the box of the shot's game folder."""
    game = rel_path.split("/")[0]
    return Image.open(SAMPLES / rel_path).convert("RGB").crop(BOXES[game])


def manga_engine():
    """Return a function that reads an image with manga-ocr."""
    from manga_ocr import MangaOcr

    return MangaOcr()


def lens_engine():
    """Return a function that reads an image with Google Lens (unofficial API)."""
    from chrome_lens_py import LensAPI

    def read(image: Image.Image) -> str:
        result = asyncio.run(lens_read(LensAPI(), image))
        return result["ocr_text"].replace(" ", "")

    return read


def lens_clean_engine():
    """Return a function that reads an image with Google Lens and removes furigana and markers.

    Furigana words are much shorter than the main text, so words below
    60% of the tallest word height are dropped.
    """
    from chrome_lens_py import LensAPI

    def read(image: Image.Image) -> str:
        words = asyncio.run(lens_read(LensAPI(), image))["word_data"]
        tallest = max(word["geometry"]["height"] for word in words)
        kept = [word["word"] for word in words if word["geometry"]["height"] >= 0.6 * tallest]
        return "".join(kept).translate(str.maketrans("", "", "▼>＞ "))

    return read


async def lens_read(api, image: Image.Image) -> dict:
    """Send one image to Google Lens and close the client."""
    try:
        return await api.process_image(image, ocr_language="ja", ocr_preserve_line_breaks=False)
    finally:
        await api.aclose()


ENGINES = {
    "manga": manga_engine,
    "lens": lens_engine,
    "lens-clean": lens_clean_engine,
}


def main() -> None:
    read = ENGINES[sys.argv[1]]()
    scores = []
    for rel_path, expected in load_expected():
        got = read(text_box(rel_path))
        score = SequenceMatcher(None, expected, got).ratio()
        scores.append(score)
        print(f"{rel_path}  score={score:.2f}")
        print(f"  expected: {expected}")
        print(f"  got:      {got}")
    print(f"\nmean score: {sum(scores) / len(scores):.2f} over {len(scores)} shots")


if __name__ == "__main__":
    main()
