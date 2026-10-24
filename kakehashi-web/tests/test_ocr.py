"""Tests for the OCR text cleanup (no network)."""

import asyncio

from PIL import Image

import ocr


def word(text: str, height: float) -> dict:
    """A Lens word with only the fields the cleanup uses."""
    return {"word": text, "geometry": {"height": height}}


def test_furigana_below_60_percent_height_is_dropped():
    words = [word("約束", 0.05), word("やくそく", 0.02), word("した", 0.05)]
    assert ocr.clean_lens(words) == "約束した"


def test_no_words_gives_empty_text():
    assert ocr.clean_lens([]) == ""


def test_markers_and_spaces_are_removed_and_ellipsis_normalized():
    assert ocr.clean("腿が ▼焼ける･･･＞") == "腿が焼ける…"


def test_only_one_lens_call_at_a_time(monkeypatch):
    running = 0
    most = 0

    async def fake_lens(image):
        nonlocal running, most
        running += 1
        most = max(most, running)
        await asyncio.sleep(0.05)
        running -= 1
        return {"ocr_text": "", "word_data": []}

    monkeypatch.setattr(ocr, "lens_read", fake_lens)
    image = Image.new("RGB", (96, 54))

    async def three_reads():
        await asyncio.gather(ocr.read(image), ocr.read(image), ocr.read(image))

    asyncio.run(three_reads())
    assert most == 1


def test_lens_failure_raises_ocr_error(monkeypatch):
    async def failing_lens(image):
        raise ocr.LensException("no network")

    monkeypatch.setattr(ocr, "lens_read", failing_lens)
    image = Image.new("RGB", (96, 54))
    try:
        asyncio.run(ocr.read(image))
    except ocr.OCRError as error:
        assert "no network" in str(error)
    else:
        raise AssertionError("no OCRError")
