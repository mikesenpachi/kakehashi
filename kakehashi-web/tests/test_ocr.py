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


def placed(text: str, x: float, y: float, width: float, height: float = 0.06) -> dict:
    """A Lens word with its box."""
    return {"word": text, "geometry": {"center_x": x, "center_y": y, "width": width, "height": height}}


def test_a_word_that_lens_returns_twice_at_one_place_is_kept_once():
    # Real Lens output (demo screen 3): a part of the line comes twice, the extra copy first.
    words = [
        placed("薄暗い", 0.219, 0.758, 0.087), placed("した", 0.418, 0.757, 0.035),
        placed("何", 0.091, 0.764, 0.034), placed("でも", 0.136, 0.762, 0.061),
        placed("薄暗い", 0.217, 0.762, 0.096), placed("した", 0.420, 0.762, 0.046), placed("所", 0.467, 0.762, 0.029),
    ]
    assert ocr.clean_lens(words) == "何でも薄暗いした所"


def test_the_same_word_at_two_places_is_kept_twice():
    words = [placed("た", 0.431, 0.762, 0.015), placed("い", 0.811, 0.762, 0.026), placed("た", 0.841, 0.762, 0.026)]
    assert ocr.clean_lens(words) == "たいた"


def test_different_words_at_one_place_are_both_kept():
    words = [placed("吾輩", 0.2, 0.76, 0.08), placed("猫", 0.2, 0.76, 0.08), placed("。", 0.3, 0.76, 0.02)]
    assert ocr.clean_lens(words) == "吾輩猫。"
