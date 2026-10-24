"""Tests for who may change data: this computer always; another device only with the token, when one is set."""

import pytest
from fastapi.testclient import TestClient

import main
import translate
from conftest import image_bytes

# Every route that changes data: method, URL (shot 1 of game PCSG00563) and JSON body.
CHANGES = [
    ("POST", "/clear", None),
    ("POST", "/shot/1/test", {"box": [0.1, 0.1, 0.9, 0.9]}),
    ("POST", "/shot/1/text", {"text": "ペルソナ"}),
    ("POST", "/shot/1/translate", {"text": "ペルソナ"}),
    ("PUT", "/games/PCSG00563/name", {"name": "P4G"}),
    ("PUT", "/games/PCSG00563/box", {"box": [0.1, 0.1, 0.9, 0.9]}),
    ("DELETE", "/games/PCSG00563/box", None),
    ("DELETE", "/games/PCSG00563", None),
    ("DELETE", "/shot/1", None),
]


@pytest.fixture
def token(client, monkeypatch):
    """Set the token "abc123", add shot 1, and fake the translation."""
    monkeypatch.setattr(main, "TOKEN", "abc123")
    monkeypatch.setattr(translate, "translate", lambda text: "Persona")
    reply = client.post("/shot?game=PCSG00563", content=image_bytes("PNG"), headers={"X-Token": "abc123"})
    assert reply.json()["id"] == 1


def change(client, method, url, body, headers=None):
    return client.request(method, url, json=body, headers=headers)


@pytest.mark.parametrize("method, url, body", CHANGES)
def test_another_device_without_the_token_is_refused(client, token, method, url, body):
    assert change(client, method, url, body).status_code == 401
    assert change(client, method, url, body, {"X-Token": "wrong"}).status_code == 401


@pytest.mark.parametrize("method, url, body", CHANGES)
def test_another_device_with_the_token_may_change(client, token, method, url, body):
    assert change(client, method, url, body, {"X-Token": "abc123"}).status_code == 200


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("method, url, body", CHANGES)
def test_this_computer_needs_no_token(client, token, host, method, url, body):
    computer = TestClient(main.app, client=(host, 50000))
    assert change(computer, method, url, body).status_code == 200


@pytest.mark.parametrize("method, url, body", CHANGES)
def test_without_a_token_everyone_may_change(client, method, url, body, monkeypatch):
    monkeypatch.setattr(translate, "translate", lambda text: "Persona")
    client.post("/shot?game=PCSG00563", content=image_bytes("PNG"))
    assert change(client, method, url, body, {"X-Token": "old"}).status_code == 200
    assert change(client, method, url, body).status_code in (200, 404)  # the 1st change may delete shot 1


def test_another_device_may_view_without_the_token(client, token):
    for url in ("/", "/shot/1", "/search?q=テスト", "/about", "/server"):
        assert client.get(url).status_code == 200, url
