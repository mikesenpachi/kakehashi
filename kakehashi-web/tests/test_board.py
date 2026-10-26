"""Tests for the stats board numbers. Plain dicts stand in for the shot rows."""

from datetime import date

import board
from conftest import image_bytes

TODAY = date(2026, 10, 26)


def shot(taken: str, text: str = "", game: str = "PCSG00563", translation: str | None = None) -> dict:
    """Return a shot row with the columns the board reads."""
    return {"taken": f"{taken}T12:00:00", "text": text, "game": game, "game_name": game, "translation": translation}


def test_characters_count_kana_and_kanji_only():
    assert board.characters("SAFETY 物語を始める。") == 6
    assert board.characters("カタカナー々") == 6
    assert board.characters(None) == 0


def test_characters_are_added_per_day():
    shots = [shot("2026-10-25", "約束"), shot("2026-10-25", "行こう"), shot("2026-10-26", "はい")]
    assert board.per_day(shots) == {date(2026, 10, 25): 5, date(2026, 10, 26): 2}


def test_streak_counts_back_from_today():
    days = {date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 26)}
    assert board.current_streak(days, TODAY) == 3


def test_streak_ending_yesterday_still_counts():
    assert board.current_streak({date(2026, 10, 24), date(2026, 10, 25)}, TODAY) == 2


def test_streak_with_a_gap_is_zero():
    assert board.current_streak({date(2026, 10, 23)}, TODAY) == 0


def test_longest_streak():
    days = {date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 10), date(2026, 10, 11)}
    assert board.longest_streak(days) == 3
    assert board.longest_streak(set()) == 0


def test_games_are_sorted_by_characters():
    shots = [
        shot("2026-10-20", "はい", "PCSG00563", "Yes"),
        shot("2026-10-22", "いいえ", "PCSG00563"),
        shot("2026-10-21", "ドラゴンクエスト", "000400000015CD00"),
    ]
    first, second = board.games(shots)
    assert first["name"] == "000400000015CD00" and first["platform"] == "3DS" and first["characters"] == 8
    assert second["shots"] == 2 and second["characters"] == 5 and second["translate_rate"] == 0.5
    assert second["first"] == date(2026, 10, 20) and second["last"] == date(2026, 10, 22)
    assert len(second["days"]) == 2


def test_numbers():
    shots = [
        shot("2026-10-26", "はい", translation="Yes"),
        shot("2026-10-20", "いいえ"),
        shot("2026-10-01", "約束"),
    ]
    result = board.numbers(shots, TODAY)
    assert result["today"] == 2 and result["week"] == 5 and result["total"] == 7
    assert result["days"] == 3 and result["average"] == 2
    assert result["streak"] == 1 and result["longest"] == 1
    assert round(result["translate_rate"], 2) == 0.33


def test_numbers_without_shots():
    result = board.numbers([], TODAY)
    assert result["total"] == 0 and result["average"] == 0 and result["translate_rate"] == 0


def test_stats_page_without_shots(client):
    assert "No shots yet." in client.get("/stats").text


def test_stats_page_shows_the_numbers_and_the_game(client):
    client.post("/shot", params={"game": "PCSG00563"}, content=image_bytes("PNG"))
    html = client.get("/stats").text
    assert "<b>3</b><span>characters today</span>" in html
    assert "<b>1 day</b><span>streak (longest 1)</span>" in html
    assert "<td>PCSG00563<span class=\"platform\">PS Vita</span></td>" in html
    assert 'class="l4" title="' in html
