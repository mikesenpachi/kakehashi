"""Tests for the sidebars: platforms, shots grouped by day, games per platform."""

import db
import pages
from conftest import image_bytes


def test_platform_comes_from_the_game_id():
    assert pages.platform("PCSG00563") == "PS Vita"
    assert pages.platform("main") == "PS Vita"
    assert pages.platform("PSPEMU010") == "PSP / PS1"
    assert pages.platform("0004000000055D00") == "3DS"
    assert pages.platform("steam-1234") == "PC"


def post(client, game, taken, color):
    """Post one small PNG and return its shot id."""
    reply = client.post("/shot", params={"game": game, "taken": taken}, content=image_bytes("PNG", color))
    return reply.json()["id"]


def test_shot_list_has_only_the_current_game_grouped_by_day(client):
    p4g_old = post(client, "PCSG00563", "20261015-200000", (1, 0, 0))
    p4g_new = post(client, "PCSG00563", "20261016-210000", (2, 0, 0))
    post(client, "0004000000055D00", "20261016-220000", (3, 0, 0))
    html = client.get("/sidebar", params={"current": p4g_old, "since": 999}).json()["shots"]
    assert f"/shot/{p4g_old}" in html and f"/shot/{p4g_new}" in html
    assert "22:00:00" not in html
    assert '<details data-day="2026-10-15" open>' in html
    assert '<details data-day="2026-10-16">' in html


def test_days_with_new_shots_are_open(client):
    first = post(client, "PCSG00563", "20261015-200000", (1, 0, 0))
    post(client, "PCSG00563", "20261016-210000", (2, 0, 0))
    html = client.get("/sidebar", params={"current": first, "since": first}).json()["shots"]
    assert '<details data-day="2026-10-16" open>' in html


def test_game_list_splits_games_by_platform(client):
    vita = post(client, "PCSG00563", "20261016-210000", (1, 0, 0))
    post(client, "0004000000055D00", "20261016-220000", (2, 0, 0))
    post(client, "PSPEMU010", "20261016-230000", (3, 0, 0))
    html = client.get("/sidebar", params={"current": vita, "since": 999}).json()["games"]
    vita_part, rest = html.split("<h3>PSP / PS1</h3>")
    psp, rest = rest.split("<h3>3DS</h3>")
    three_ds, pc = rest.split("<h3>PC</h3>")
    assert "PCSG00563" in vita_part and 'class="current"' in vita_part
    assert "PSPEMU010" in psp and "PSPEMU010" not in vita_part
    assert "0004000000055D00" in three_ds
    assert "No games yet" in pc


def test_numbers_start_at_1_for_each_game_and_day(client):
    day1 = [post(client, "PCSG00563", f"20261015-2000{i}0", (i, 1, 0)) for i in range(3)]
    other_game = post(client, "PCSG00062", "20261015-201000", (9, 9, 0))
    day2 = post(client, "PCSG00563", "20261016-090000", (4, 1, 0))
    numbers = pages.day_numbers(db.list_shots())
    assert [numbers[shot] for shot in day1] == [1, 2, 3]
    assert numbers[other_game] == 1
    assert numbers[day2] == 1
    html = client.get(f"/shot/{day2}").text
    assert "Shot #1" in html and "<title>PCSG00563 #1 · 2026-10-16 09:00:00</title>" in html


def test_outline_shows_the_box_of_the_shot_not_of_the_game(client):
    old = post(client, "PCSG00563", "20261016-210000", (1, 0, 0))
    client.put("/games/PCSG00563/box", json={"box": [0.1, 0.7, 0.9, 1.0]})
    new = post(client, "PCSG00563", "20261016-220000", (2, 0, 0))
    old_html = client.get(f"/shot/{old}").text
    new_html = client.get(f"/shot/{new}").text
    assert '<div id="saved" class="box" style="" hidden>' in old_html
    assert 'style="left:10.0%;top:70.0%;width:80.0%;height:30.0%"' in new_html
    assert '<button id="clear" class="ghost">' in old_html


def test_use_for_this_shot_stores_its_box(client):
    shot = post(client, "PCSG00563", "20261016-210000", (1, 0, 0))
    client.post(f"/shot/{shot}/text", json={"text": "約束", "box": [0.2, 0.6, 0.8, 0.9]})
    saved = db.get_shot(shot)
    assert saved["text"] == "約束" and saved["edited"] == 1
    assert db.used_box(saved) == (0.2, 0.6, 0.8, 0.9)
    client.post(f"/shot/{shot}/text", json={"text": "約束した"})
    assert db.used_box(db.get_shot(shot)) == (0.2, 0.6, 0.8, 0.9)


def test_home_shows_the_newest_shot_and_the_recent_shots(client):
    old = post(client, "PCSG00563", "20261016-200000", (1, 2, 0))
    newest = post(client, "PSPEMU010", "20261016-210000", (2, 2, 0))
    html = client.get("/").text
    latest_part, recent_part = html.split("</main>")[0].split("Recent shots")
    assert f'href="/shot/{newest}"' in latest_part and "PSPEMU010 #1" in latest_part
    assert f'href="/shot/{old}"' in recent_part and f'href="/shot/{newest}"' not in recent_part
    assert "<b>2</b><span>shots</span>" in html


def test_latest_opens_the_newest_shot(client):
    assert client.get("/latest", follow_redirects=False).headers["location"] == "/"
    post(client, "PCSG00563", "20261016-200000", (1, 3, 0))
    newest = post(client, "PCSG00563", "20261016-210000", (2, 3, 0))
    assert client.get("/latest", follow_redirects=False).headers["location"] == f"/shot/{newest}"
