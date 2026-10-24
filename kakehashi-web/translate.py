"""Translate Japanese text to English with Google Translate.

Unofficial endpoint (the one the Google Translate Chrome extension uses): no key, can stop working at any time.
translate.googleapis.com (client=gtx) answered "Sorry..." from this Mac on 2026-10-20, so it is not used.
"""

import json
import urllib.parse
import urllib.request

URL = "https://clients5.google.com/translate_a/t"


def translate(text: str) -> str:
    """Return the English translation of a Japanese text. Line breaks stay."""
    query = urllib.parse.urlencode({"client": "dict-chrome-ex", "sl": "ja", "tl": "en", "q": text})
    with urllib.request.urlopen(f"{URL}?{query}", timeout=10) as response:
        return json.load(response)[0]
