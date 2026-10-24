"""OCR test: the webapp's OCR on 3DS top screens (400x240), at 1x, 2x and 3x size.

Compares the text with samples/3ds/expected.tsv, after NFKC (so ！ and ! or ３ and 3 match).
Each shot is read with its game's crop box and on the full screen. Fire Emblem and Pokemon
move their text boxes, so they have no game box.
Run from kakehashi-web: PYTHONPATH=. uv run ../experiments/ocr_3ds.py
"""

import asyncio
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image

import ocr

SAMPLES = Path(__file__).parent.parent / "samples" / "3ds"
SCALES = [1, 2, 3]

# Crop box (left, top, right, bottom) as fractions, around the dialogue lines, per game.
BOXES = {
    "dragon-quest-8": (0.02, 0.60, 0.98, 0.98),
    "ace-attorney-123": (0.10, 0.76, 0.90, 0.98),
    "ace-attorney-5": (0.07, 0.77, 0.93, 0.99),
}


def score(expected: str, got: str) -> float:
    """Return the similarity of two texts, 0 to 1, after NFKC."""
    norm = lambda text: unicodedata.normalize("NFKC", text)
    return SequenceMatcher(None, norm(expected), norm(got)).ratio()


async def main() -> None:
    lines = (SAMPLES / "expected.tsv").read_text(encoding="utf-8").splitlines()
    pairs = [line.split("\t") for line in lines if line]
    results = {}
    for rel_path, expected in pairs:
        game = rel_path.split("/")[0]
        original = Image.open(SAMPLES / rel_path).convert("RGB")
        for scale in SCALES:
            image = original.resize((original.width * scale, original.height * scale), Image.LANCZOS)
            for mode, box in (("box", BOXES.get(game)), ("full", None)):
                if mode == "box" and box is None:
                    continue
                _, text = await ocr.read(image, box)
                value = score(expected, text)
                results.setdefault((mode, scale), []).append((game, value))
                if value < 1:
                    print(f"  {mode} {scale}x {rel_path} {value:.2f}: {text}", flush=True)
    print()
    for (mode, scale), values in sorted(results.items()):
        mean = sum(value for _, value in values) / len(values)
        perfect = sum(value == 1 for _, value in values)
        print(f"{mode:4} {scale}x: mean {mean:.3f}, {perfect}/{len(values)} at 1.00")
    for game in sorted({game for _, game_values in results.items() for game, _ in game_values}):
        row = []
        for (mode, scale), values in sorted(results.items()):
            own = [value for g, value in values if g == game]
            if own:
                row.append(f"{mode} {scale}x {sum(own) / len(own):.2f}")
        print(f"{game}: " + ", ".join(row))


asyncio.run(main())
