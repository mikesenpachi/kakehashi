# /// script
# requires-python = ">=3.12"
# ///
"""Upload your sample screenshots to the webapp, oldest first, 2 s apart.

Each PNG in samples/<folder>/ (folders in GAMES; see experiments/README.md) is sent as it is,
with its game ID and the capture time from its filename. The game IDs are made up: edit GAMES.
Sends KAKEHASHI_TOKEN as the X-Token header, if set.
Run from the repo root: uv run tools/upload_samples.py [server]
The default server is http://localhost:8766.
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

SAMPLES = Path(__file__).parent.parent / "samples"
GAMES = {"persona-4-golden": "PCSG00123", "time-travelers": "PCSG00999"}


def taken(png: Path) -> str:
    """Return the capture time of a sample, for example 2026-10-11-183738 -> 20261011-183738."""
    stamp = png.stem.replace("-", "")
    return f"{stamp[:8]}-{stamp[8:]}"


def upload(server: str, png: Path) -> dict:
    """Send one sample and return the reply of the webapp."""
    url = f"{server}/shot?game={GAMES[png.parent.name]}&taken={taken(png)}"
    headers = {"X-Token": os.environ.get("KAKEHASHI_TOKEN", "")}
    request = urllib.request.Request(url, data=png.read_bytes(), headers=headers, method="POST")
    return json.load(urllib.request.urlopen(request))


def main() -> None:
    server = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8766"
    pngs = sorted((png for game in GAMES for png in (SAMPLES / game).glob("*.png")), key=lambda png: png.stem)
    for png in pngs:
        reply = upload(server, png)
        print(f"{png.parent.name}/{png.name} -> id {reply['id']}: {reply.get('text', '(already saved)')}", flush=True)
        time.sleep(2)


if __name__ == "__main__":
    main()
