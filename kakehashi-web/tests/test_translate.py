"""Tests for the translate route. A fake translate is used, so tests never call Google."""

import db
import translate
from conftest import image_bytes


def add_shot(client) -> int:
    """Send one shot and return its id."""
    return client.post("/shot?game=PCSG00563", content=image_bytes("PNG")).json()["id"]


def test_translate_returns_and_saves_the_translation(client, monkeypatch):
    monkeypatch.setattr(translate, "translate", lambda text: f"EN {text}")
    shot_id = add_shot(client)
    response = client.post(f"/shot/{shot_id}/translate", json={"text": " もう行こう。 "})
    assert response.json() == {"translation": "EN もう行こう。"}
    assert db.get_shot(shot_id)["translation"] == "EN もう行こう。"


def test_a_new_translation_replaces_the_old_one(client, monkeypatch):
    monkeypatch.setattr(translate, "translate", lambda text: f"EN {text}")
    shot_id = add_shot(client)
    client.post(f"/shot/{shot_id}/translate", json={"text": "もう行こう。"})
    client.post(f"/shot/{shot_id}/translate", json={"text": "行こう。"})
    assert db.get_shot(shot_id)["translation"] == "EN 行こう。"


def test_translate_reports_no_answer_from_google(client, monkeypatch):
    def fail(text):
        raise OSError("timed out")

    monkeypatch.setattr(translate, "translate", fail)
    shot_id = add_shot(client)
    response = client.post(f"/shot/{shot_id}/translate", json={"text": "もう行こう。"})
    assert response.status_code == 502
    assert "timed out" in response.json()["detail"]
    assert db.get_shot(shot_id)["translation"] is None


def test_translate_of_no_shot_is_404(client):
    assert client.post("/shot/999/translate", json={"text": "もう行こう。"}).status_code == 404


def test_empty_text_is_refused(client):
    shot_id = add_shot(client)
    assert client.post(f"/shot/{shot_id}/translate", json={"text": "  "}).status_code == 422


def test_translation_card_shows_empty_before_translate(client):
    page = client.get(f"/shot/{add_shot(client)}").text
    assert '<div id="translation-card" class="card text-card"><div class="text-head">' in page
    assert '<div id="translation" lang="en"></div>' in page


def test_page_shows_the_saved_translation(client, monkeypatch):
    monkeypatch.setattr(translate, "translate", lambda text: "Let's <go>.")
    shot_id = add_shot(client)
    client.post(f"/shot/{shot_id}/translate", json={"text": "もう行こう。"})
    page = client.get(f"/shot/{shot_id}").text
    assert '<div id="translation-card" class="card text-card">' in page
    assert "Let&#x27;s &lt;go&gt;." in page


def test_an_edit_replaces_the_translation(client, monkeypatch):
    monkeypatch.setattr(translate, "translate", lambda text: f"EN {text}")
    shot_id = add_shot(client)
    client.post(f"/shot/{shot_id}/translate", json={"text": "もう行こう。"})
    response = client.post(f"/shot/{shot_id}/translation", json={"translation": " Let's go now. "})
    assert response.json() == {"translation": "Let's go now."}
    assert db.get_shot(shot_id)["translation"] == "Let's go now."


def test_an_empty_edit_clears_the_translation(client):
    shot_id = add_shot(client)
    client.post(f"/shot/{shot_id}/translation", json={"translation": "Let's go."})
    client.post(f"/shot/{shot_id}/translation", json={"translation": "  "})
    assert db.get_shot(shot_id)["translation"] == ""


def test_an_edit_of_a_missing_shot_is_404(client):
    assert client.post("/shot/999/translation", json={"translation": "Hi"}).status_code == 404
