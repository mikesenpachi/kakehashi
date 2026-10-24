"""Tests for the about and server pages."""

import main
from conftest import image_bytes


def test_about_shows_the_numbers(client):
    client.post("/shot", params={"game": "PCSG00563"}, content=image_bytes("PNG"))
    html = client.get("/about").text
    assert "<b>1</b><span>shots</span>" in html
    assert "<b>1</b><span>games</span>" in html


def test_server_shows_the_address_and_a_vita_config(client, monkeypatch):
    monkeypatch.setattr(main, "lan_address", lambda: "192.168.1.10")
    html = client.get("http://testserver:8766/server").text
    assert "http://192.168.1.10:8766" in html
    assert "server=192.168.1.10\nport=8766\ntoken=</pre>" in html
    assert "Off:" in html


def test_server_shows_a_3ds_config(client, monkeypatch):
    monkeypatch.setattr(main, "lan_address", lambda: "192.168.1.10")
    html = client.get("http://testserver:8766/server").text
    assert "sdmc:/kakehashi/config.txt" in html
    assert "server=192.168.1.10\nport=8766\ntoken=\ncombo=L+SELECT</pre>" in html


def test_server_tells_when_the_token_check_is_on(client, monkeypatch):
    monkeypatch.setattr(main, "lan_address", lambda: "192.168.1.10")
    monkeypatch.setattr(main, "TOKEN", "abc123")
    html = client.get("/server").text
    assert "On:" in html and "abc123" not in html


def test_server_without_network(client, monkeypatch):
    monkeypatch.setattr(main, "lan_address", lambda: None)
    assert "No network" in client.get("/server").text
