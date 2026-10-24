# /// script
# requires-python = ">=3.12"
# dependencies = ["pillow"]
# ///
"""Draw demo "game" screens and send them to a webapp, for a recording with no real game in it.

The text is the start of Natsume Soseki's "I Am a Cat" (1905, public domain), with furigana
above the kanji and a dialogue box, at the Vita size. The font is Noto Sans JP (SIL Open Font
License), downloaded once into tools/fonts/.

Run from the repo root, with a demo server running (make demo):
  uv run tools/demo.py              send one screen each time you press Enter
  uv run tools/demo.py --save DIR   only write the screens as PNG files to DIR
The server is http://localhost:8767; set another one with --server.
"""

import argparse
import io
import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = Path(__file__).parent / "fonts" / "NotoSansJP-Bold.otf"
FONT_URL = "https://github.com/notofonts/noto-cjk/raw/main/Sans/SubsetOTF/JP/NotoSansJP-Bold.otf"
GAME = "DEMO00001"
GAME_NAME = "吾輩は猫である (demo)"
WIDTH, HEIGHT = 960, 544
TEXT_SIZE, RUBY_SIZE = 30, 13  # furigana under 60% of the text height, so the OCR drops it
BOX = (40, 352, 920, 520)  # dialogue box: left, top, right, bottom
CHARS_PER_LINE = 26

# Each screen: the dialogue, and the furigana as (kanji, reading) in the order they appear.
SCREENS = [
    ("吾輩は猫である。名前はまだ無い。", [("吾輩", "わがはい"), ("猫", "ねこ"), ("名前", "なまえ"), ("無", "な")]),
    ("どこで生れたかとんと見当がつかぬ。", [("生", "うま"), ("見当", "けんとう")]),
    (
        "何でも薄暗いじめじめした所でニャーニャー泣いていた事だけは記憶している。",
        [("何", "なん"), ("薄暗", "うすぐら"), ("所", "ところ"), ("泣", "な"), ("事", "こと"), ("記憶", "きおく")],
    ),
    ("吾輩はここで始めて人間というものを見た。", [("吾輩", "わがはい"), ("始", "はじ"), ("人間", "にんげん"), ("見", "み")]),
]


def font(size: int) -> ImageFont.FreeTypeFont:
    """Return Noto Sans JP Bold at a size, downloaded first if needed."""
    if not FONT.exists():
        FONT.parent.mkdir(exist_ok=True)
        print(f"Downloading {FONT_URL}")
        urllib.request.urlretrieve(FONT_URL, FONT)
    return ImageFont.truetype(str(FONT), size)


def background() -> Image.Image:
    """Return an evening sky with a moon and two hills."""
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        t = y / HEIGHT
        draw.line([(0, y), (WIDTH, y)], fill=(int(40 + 180 * t), int(50 + 90 * t), int(110 + 40 * t)))
    draw.ellipse((730, 50, 810, 130), fill=(250, 240, 200))
    draw.polygon([(0, 330), (260, 230), (520, 330), (520, HEIGHT), (0, HEIGHT)], fill=(40, 70, 60))
    draw.polygon([(380, 340), (700, 250), (960, 320), (960, HEIGHT), (380, HEIGHT)], fill=(30, 55, 50))
    return image


def lines(text: str) -> list[str]:
    """Split the dialogue into lines of at most CHARS_PER_LINE characters."""
    return [text[i : i + CHARS_PER_LINE] for i in range(0, len(text), CHARS_PER_LINE)]


def draw_screen(text: str, ruby: list[tuple[str, str]]) -> Image.Image:
    """Return one screen: the background, the dialogue box, the text with furigana, and a marker."""
    image = background().convert("RGBA")
    box = Image.new("RGBA", image.size)
    ImageDraw.Draw(box).rounded_rectangle(BOX, 16, fill=(15, 20, 45, 215), outline=(230, 230, 255), width=3)
    image = Image.alpha_composite(image, box)
    draw = ImageDraw.Draw(image)
    big, small = font(TEXT_SIZE), font(RUBY_SIZE)
    pending = list(ruby)
    y = BOX[1] + 38
    for line in lines(text):
        x = BOX[0] + 34
        draw.text((x, y), line, font=big, fill="white")
        start = 0
        while pending and (at := line.find(pending[0][0], start)) >= 0:
            kanji, reading = pending.pop(0)
            left = x + draw.textlength(line[:at], font=big)
            middle = left + draw.textlength(kanji, font=big) / 2
            draw.text((middle - draw.textlength(reading, font=small) / 2, y - 17), reading, font=small, fill="white")
            start = at + len(kanji)
        y += 56
    draw.text((BOX[2] - 46, BOX[3] - 44), "▼", font=font(20), fill="white")
    return image.convert("RGB")


def png(image: Image.Image) -> bytes:
    """Encode an image as PNG."""
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def call(method: str, url: str, data: bytes, headers: dict) -> dict:
    """Send one request and return the JSON reply."""
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    return json.load(urllib.request.urlopen(request, timeout=120))


def send(server: str) -> None:
    """Send each screen to the Shot API when the user presses Enter. Name the game after the first one."""
    token = {"X-Token": os.environ["KAKEHASHI_TOKEN"]} if os.environ.get("KAKEHASHI_TOKEN") else {}
    for number, (text, ruby) in enumerate(SCREENS, 1):
        input(f"Press Enter to send screen {number} of {len(SCREENS)}: {text}")
        taken = datetime.now().strftime("%Y%m%d-%H%M%S")
        reply = call("POST", f"{server}/shot?game={GAME}&taken={taken}", png(draw_screen(text, ruby)), token)
        print(f"  shot {reply['id']}: {reply.get('text', '(already saved)')}")
        if number == 1:
            name = json.dumps({"name": GAME_NAME}).encode()
            call("PUT", f"{server}/games/{GAME}/name", name, {"Content-Type": "application/json", **token})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server", default="http://localhost:8767")
    parser.add_argument("--save", type=Path, help="write the screens as PNG files to this folder, send nothing")
    args = parser.parse_args()
    if args.save:
        args.save.mkdir(parents=True, exist_ok=True)
        for number, (text, ruby) in enumerate(SCREENS, 1):
            draw_screen(text, ruby).save(args.save / f"demo-{number}.png")
        print(f"Saved {len(SCREENS)} screens in {args.save}")
    else:
        send(args.server)


if __name__ == "__main__":
    main()
