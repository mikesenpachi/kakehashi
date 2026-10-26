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
    assert 'class="l4" data-day="' in html


def test_heatmap_shows_one_year_with_full_dates():
    days = {date(2025, 12, 31): 50, date(2026, 1, 1): 100, date(2026, 3, 2): 25}
    html = board.heatmap(days, TODAY, 2026)
    assert 'data-day="2026-01-01" data-count="100"' in html and 'class="l4" data-day="2026-01-01"' in html
    assert 'class="l1" data-day="2026-03-02"' in html
    assert "2025-12-31" not in html and "2026-10-27" not in html
    assert html.count("data-day=") == TODAY.timetuple().tm_yday
    assert html.count("<span>Jan</span>") == 1 and html.count("<span>Dec</span>") == 1


def test_years_are_the_years_with_shots_and_this_year():
    assert board.years({date(2024, 5, 1): 1, date(2026, 1, 1): 1}, TODAY) == [2026, 2024]


def rows(count: int) -> list[dict]:
    """Return game rows for the games table."""
    day = date(2026, 10, 1)
    return [{"name": f"Game {n}", "platform": "PC", "characters": 100 - n, "shots": 1, "days": {day},
             "first": day, "last": day, "translate_rate": 0} for n in range(count)]


def test_games_table_shows_10_games_per_page():
    first_page = board.games_table(rows(23), 1, 2026)
    assert first_page.count("<tr><td>") == 10 and "Game 0<" in first_page and "Game 10<" not in first_page
    assert "1-10 of 23 games" in first_page and 'href="?year=2026&amp;page=2">Next' in first_page
    last_page = board.games_table(rows(23), 3, 2026)
    assert last_page.count("<tr><td>") == 3 and "21-23 of 23 games" in last_page
    assert '<span class="off">Next</span>' in last_page


def test_games_table_page_out_of_range_shows_the_last_page():
    assert "21-23 of 23 games" in board.games_table(rows(23), 9, 2026)


def test_games_table_on_one_page_has_no_links():
    html = board.games_table(rows(3), 1, 2026)
    assert "1-3 of 3 games" in html and "Next" not in html


def test_stats_page_takes_a_year_and_refuses_a_bad_one(client):
    client.post("/shot", params={"game": "PCSG00563"}, content=image_bytes("PNG"))
    html = client.get("/stats?year=2025").text
    assert "0 in 2025" in html and 'aria-label="Characters read per day in 2025"' in html
    assert client.get("/stats?year=1").status_code == 422
    assert client.get("/stats?page=0").status_code == 422
