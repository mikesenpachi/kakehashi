"""Tests for full text search. The index must follow every change of the shots."""

import sqlite3
from datetime import datetime

import db
import translate
from conftest import image_bytes


def add_shot(client, color=(200, 30, 30), game="PCSG00563") -> int:
    """Send one shot (the fake OCR reads "テスト") and return its id."""
    return client.post("/shot", params={"game": game}, content=image_bytes("PNG", color)).json()["id"]


def found(query: str) -> list[int]:
    """Return the ids of the shots whose index entry matches a query."""
    with db.connect() as conn:
        return [row[0] for row in conn.execute("select rowid from search where search match ? order by rowid", (query,))]


def assert_in_sync() -> None:
    """Fail if the index differs from the text and translation in shots (FTS5 integrity check with rank 1)."""
    with db.connect() as conn:
        conn.execute("insert into search (search, rank) values ('integrity-check', 1)")


def test_new_shot_is_found(client):
    shot_id = add_shot(client)
    assert found("テスト") == [shot_id]
    assert_in_sync()


def test_edited_text_replaces_the_old_text(client):
    shot_id = add_shot(client)
    client.post(f"/shot/{shot_id}/text", json={"text": "ペルソナを手に入れた"})
    assert found("テスト") == []
    assert found("ペルソナ") == [shot_id]
    assert_in_sync()


def test_translation_is_found_in_any_case(client, monkeypatch):
    monkeypatch.setattr(translate, "translate", lambda text: "Obtained the Persona")
    shot_id = add_shot(client)
    client.post(f"/shot/{shot_id}/translate", json={"text": "テスト"})
    assert found("persona") == [shot_id]
    assert found("OBTAINED") == [shot_id]
    assert_in_sync()


def test_box_change_keeps_the_index_in_sync(client):
    shot_id = add_shot(client)
    client.post(f"/shot/{shot_id}/text", json={"text": "ペルソナ", "box": [0.1, 0.1, 0.9, 0.9]})
    assert found("ペルソナ") == [shot_id]
    assert_in_sync()


def test_deleted_shot_is_not_found(client):
    first = add_shot(client)
    second = add_shot(client, (30, 200, 30))
    client.delete(f"/shot/{first}")
    assert found("テスト") == [second]
    assert_in_sync()


def test_deleted_game_is_not_found(client):
    add_shot(client)
    kept = add_shot(client, (30, 200, 30), game="PCSG00062")
    client.delete("/games/PCSG00563")
    assert found("テスト") == [kept]
    assert_in_sync()


def test_clear_empties_the_index(client):
    add_shot(client)
    client.post("/clear")
    assert found("テスト") == []
    assert_in_sync()


def test_index_of_an_old_database_is_filled_once(client):
    with sqlite3.connect(db.DB) as conn:
        conn.executescript(
            "create table shots (id integer primary key, name text unique not null, game text not null,"
            " raw_ocr text, text text, taken text not null, box_used text, edited integer not null default 0);"
            "insert into shots (name, game, text, taken) values ('a.jpg', 'PCSG00563', 'イザナギ', '2026-10-24T10:00:00');"
        )
    assert found("イザナギ") == [1]
    assert_in_sync()
    with db.connect() as conn:
        assert conn.execute("select count(*) from search where search match 'イザナギ'").fetchone()[0] == 1


def shot(text: str, translation: str | None = None, minute: int = 0) -> int:
    """Add a shot with this text and translation, taken at 10:<minute>, and return its id."""
    shot_id = db.add_shot(f"{text}{minute}.jpg", "PCSG00563", "", text, datetime(2026, 10, 24, 10, minute), None)
    if translation:
        db.set_translation(shot_id, translation)
    return shot_id


def ids(query: str) -> list[int]:
    """Return the ids of the shots that db.search finds, in its order."""
    return [row["id"] for row in db.search(query)]


def test_search_japanese_with_the_index(client):
    persona = shot("ペルソナ“イザナギ”を手に入れた!")
    shot("お前…妙な事に首突っ込んだりしてないよな?", minute=1)
    assert ids("イザナギ") == [persona]
    assert ids("手に入") == [persona]


def test_search_finds_1_and_2_characters(client):
    magic = shot("魔法の剣", "A magic sword. Go!")
    shot("真実を求めて", "Seeking the truth", minute=1)
    assert ids("魔法") == [magic]
    assert ids("剣") == [magic]
    assert ids("go") == [magic]


def test_search_english_in_any_case(client):
    persona = shot("ペルソナ", "Obtained the Persona")
    assert ids("persona") == [persona]
    assert ids("OBTAINED THE") == [persona]


def test_search_takes_query_syntax_as_plain_text(client):
    question = shot("してないよな?", 'He said "no" - OR not')
    shot("してないよな", minute=1)
    assert ids("ないよな?") == [question]
    assert ids('"no"') == [question]
    assert ids("- OR") == [question]
    assert ids("NEAR(") == []


def test_short_search_takes_like_wildcards_as_plain_text(client):
    percent = shot("100%")
    shot("100", minute=1)
    assert ids("%") == [percent]
    assert ids("_") == []


def test_search_is_newest_first_and_stops_at_found(client, monkeypatch):
    monkeypatch.setattr(db, "FOUND", 2)
    old, middle, new = shot("ペルソナ", minute=1), shot("ペルソナ", minute=2), shot("ペルソナ", minute=3)
    assert ids("ペルソナ") == [new, middle]
    assert ids("ペル") == [new, middle]
    assert old not in ids("ペルソナ")


def test_empty_search_finds_nothing(client):
    shot("ペルソナ")
    assert ids("  ") == []


def test_search_of_3_or_more_characters_uses_the_index(client):
    # The trigram index folds the case of all letters; LIKE folds only A to Z.
    school = shot("学校", "une école")
    assert ids("ÉCOLE") == [school]


def test_search_page_lists_and_marks_the_shots_found(client):
    persona = shot("ペルソナを手に入れた", "Obtained the Persona")
    shot("真実を求めて", minute=1)
    page = client.get("/search", params={"q": "ペルソナ"}).text
    assert "1 shot<" in page
    assert f'href="/shot/{persona}"' in page
    assert "<mark>ペルソナ</mark>を手に入れた" in page
    assert "真実" not in page.split('class="results"')[1]


def test_search_page_marks_english_in_the_case_of_the_text(client):
    shot("ペルソナ", "Obtained the Persona")
    page = client.get("/search", params={"q": "persona"}).text
    assert "Obtained the <mark>Persona</mark>" in page


def test_search_page_escapes_the_text_and_the_query(client):
    shot("<b>太字</b>", "<i>bold</i>")
    page = client.get("/search", params={"q": "<b>太字"}).text
    assert "<mark>&lt;b&gt;太字</mark>&lt;/b&gt;" in page
    assert "Search: <span lang=\"ja\">&lt;b&gt;太字</span>" in page
    assert "<i>bold</i>" not in page


def test_search_page_says_when_nothing_is_found(client):
    shot("ペルソナ")
    page = client.get("/search", params={"q": "イザナギ"}).text
    assert "No shot has this text." in page
    assert "0 shots" in page


def test_search_page_counts_newest_found(client, monkeypatch):
    monkeypatch.setattr(db, "FOUND", 2)
    for minute in range(3):
        shot("ペルソナ", minute=minute)
    assert "Newest 2 shots" in client.get("/search", params={"q": "ペルソナ"}).text


def test_search_page_without_a_query_asks_for_one(client):
    shot("ペルソナ")
    page = client.get("/search").text
    assert "Type a word in Japanese or English." in page
    assert 'class="results"' not in page


SEARCH_BOX = '<form class="search" action="/search" role="search"><input type="search" name="q" value="'


def test_every_page_has_the_search_box(client):
    shot_id = add_shot(client)
    for url in ("/", f"/shot/{shot_id}", "/about", "/server", "/search"):
        assert SEARCH_BOX + '"' in client.get(url).text, url


def test_search_box_keeps_the_query_escaped(client):
    shot("ペルソナ")
    page = client.get("/search", params={"q": '"><b>ペルソナ'}).text
    assert SEARCH_BOX + '&quot;&gt;&lt;b&gt;ペルソナ"' in page


def test_database_uses_wal_so_reads_do_not_wait_for_writes(client):
    shot("ペルソナ")
    writer = sqlite3.connect(db.DB, timeout=0)
    writer.execute("begin exclusive")
    writer.execute("update shots set text = 'イザナギ'")
    assert ids("ペルソナ")  # reads the last commit while the write is open
    writer.rollback()
    with db.connect() as conn:
        assert conn.execute("pragma journal_mode").fetchone()[0] == "wal"


def test_top_bar_links_to_search_and_marks_it_on_the_search_page(client):
    shot("ペルソナ")
    assert '<a href="/search">Search</a>' in client.get("/about").text
    assert '<a href="/search" class=active>Search</a>' in client.get("/search", params={"q": "ペルソナ"}).text
