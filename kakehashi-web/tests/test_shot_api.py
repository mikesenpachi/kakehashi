"""Tests for POST /shot, the one contract for all devices."""

import hashlib

import db
import main
import ocr
from conftest import image_bytes


def post(client, body: bytes, game="PCSG00563", **params):
    """Post one image to the Shot API."""
    return client.post("/shot", params={"game": game, **params}, content=body)


def test_bmp_is_saved_as_jpeg_with_the_hash_of_the_bmp(client):
    body = image_bytes("BMP")
    reply = post(client, body).json()
    name = hashlib.sha256(body).hexdigest()[:16] + ".jpg"
    saved = main.IMAGES / "PCSG00563" / name
    assert reply["new"] and reply["text"] == "テスト"
    assert saved.read_bytes()[:3] == b"\xff\xd8\xff"
    assert db.get_shot(reply["id"])["name"] == name


def test_same_image_twice_is_saved_once(client):
    body = image_bytes("BMP")
    first = post(client, body).json()
    second = post(client, body).json()
    assert second == {"id": first["id"], "new": False}
    assert len(db.list_shots()) == 1


def test_png_is_saved_as_sent(client):
    body = image_bytes("PNG")
    reply = post(client, body).json()
    name = db.get_shot(reply["id"])["name"]
    assert name.endswith(".png")
    assert (main.IMAGES / "PCSG00563" / name).read_bytes() == body


def test_taken_time_is_used(client):
    reply = post(client, image_bytes("PNG"), taken="20261016-154300").json()
    assert db.get_shot(reply["id"])["taken"] == "2026-10-16T15:43:00"


def test_not_an_image_is_refused(client):
    assert post(client, b"hello").status_code == 400


def test_other_image_format_is_refused(client):
    assert post(client, image_bytes("GIF")).status_code == 400


def test_bad_game_id_is_refused(client):
    assert post(client, image_bytes("PNG"), game="../etc").status_code == 422


def test_token_is_checked_when_set(client, monkeypatch):
    monkeypatch.setattr(main, "TOKEN", "abc123")
    body = image_bytes("PNG")
    assert post(client, body).status_code == 401
    good = client.post("/shot", params={"game": "PCSG00563"}, content=body, headers={"X-Token": "abc123"})
    assert good.status_code == 200


def test_new_shot_is_read_with_the_game_box(client, reads):
    post(client, image_bytes("PNG"))
    client.put("/games/PCSG00563/box", json={"box": [0.1, 0.7, 0.9, 1.0]})
    post(client, image_bytes("PNG", color=(30, 30, 200)))
    assert reads[-1] == (0.1, 0.7, 0.9, 1.0)


def test_clear_keeps_the_image_files(client):
    reply = post(client, image_bytes("PNG")).json()
    name = db.get_shot(reply["id"])["name"]
    client.post("/clear")
    assert db.list_shots() == []
    assert (main.IMAGES / "PCSG00563" / name).exists()


def test_new_box_is_only_for_new_shots(client, reads):
    old = post(client, image_bytes("PNG")).json()["id"]
    client.put("/games/PCSG00563/box", json={"box": [0.1, 0.7, 0.9, 1.0]})
    client.delete("/games/PCSG00563/box")
    assert reads == [None]
    assert db.get_shot(old)["box_used"] == ""


def test_delete_game_removes_its_shots_files_name_and_box_only(client):
    p4g = post(client, image_bytes("PNG", (1, 4, 0))).json()["id"]
    post(client, image_bytes("PNG", (2, 4, 0)), game="PSPEMU010")
    client.put("/games/PCSG00563/name", json={"name": "P4G"})
    client.put("/games/PCSG00563/box", json={"box": [0.1, 0.7, 0.9, 0.95]})
    folder = main.IMAGES / "PCSG00563"
    (folder / "not-ours.txt").write_text("a file the app did not save")
    assert client.delete("/games/PCSG00563").json() == {"deleted": 1}
    assert [shot["game"] for shot in db.list_shots()] == ["PSPEMU010"]
    assert db.get_shot(p4g) is None
    assert [path.name for path in folder.iterdir()] == ["not-ours.txt"]
    assert len(list((main.IMAGES / "PSPEMU010").iterdir())) == 1
    assert db.get_box("PSPEMU010") is None
    again = post(client, image_bytes("PNG", (1, 4, 0))).json()["id"]
    assert db.get_shot(again)["game_name"] == "PCSG00563"
    assert db.get_box("PCSG00563") is None


def test_delete_game_removes_the_empty_folder(client):
    post(client, image_bytes("PNG", (3, 4, 0)))
    client.delete("/games/PCSG00563")
    assert not (main.IMAGES / "PCSG00563").exists()


def test_delete_shot_removes_its_row_and_file_and_names_the_next_older(client):
    old = post(client, image_bytes("PNG", (1, 5, 0)), taken="20261016-200000").json()["id"]
    mid = post(client, image_bytes("PNG", (2, 5, 0)), taken="20261016-210000").json()["id"]
    post(client, image_bytes("PNG", (3, 5, 0)), game="PSPEMU010", taken="20261016-203000")
    new = post(client, image_bytes("PNG", (4, 5, 0)), taken="20261016-220000").json()["id"]
    name = db.get_shot(mid)["name"]
    assert client.delete(f"/shot/{mid}").json() == {"deleted": 1, "next": old}
    assert db.get_shot(mid) is None and db.get_shot(new) is not None
    assert not (main.IMAGES / "PCSG00563" / name).exists()
    assert client.delete(f"/shot/{old}").json() == {"deleted": 1, "next": None}
    assert client.delete(f"/shot/{new}").json() == {"deleted": 1, "next": None}
    assert not (main.IMAGES / "PCSG00563").exists()
    assert client.delete(f"/shot/{new}").status_code == 404


def test_delete_game_refuses_bad_ids(client):
    assert client.delete("/games/%2E%2E").status_code == 422
    assert client.delete("/games/NOGAME01").status_code == 404


def fail_ocr(monkeypatch):
    """Make the fake OCR fail as Google Lens does without a network."""

    async def failing_read(image, box=None):
        raise ocr.OCRError("no network")

    monkeypatch.setattr(ocr, "read", failing_read)


def test_lens_failure_saves_no_shot_and_a_retry_works(client, monkeypatch, reads):
    working_read = ocr.read
    fail_ocr(monkeypatch)
    reply = post(client, image_bytes("PNG"))
    assert reply.status_code == 502
    assert "no network" in reply.json()["detail"]
    assert db.list_shots() == []
    monkeypatch.setattr(ocr, "read", working_read)
    reply = post(client, image_bytes("PNG"))
    assert reply.json()["new"] is True
    assert len(db.list_shots()) == 1


def test_lens_failure_on_test_box_is_502(client, monkeypatch):
    shot_id = post(client, image_bytes("PNG")).json()["id"]
    fail_ocr(monkeypatch)
    reply = client.post(f"/shot/{shot_id}/test", json={"box": [0.1, 0.1, 0.9, 0.9]})
    assert reply.status_code == 502
