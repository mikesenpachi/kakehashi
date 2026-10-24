"""Test setup: a temporary data folder and a fake OCR, so tests never touch real shots or call Google Lens."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import db
import main
import ocr


@pytest.fixture
def reads(monkeypatch):
    """Replace OCR with a fake. Return the list of boxes it was called with."""
    boxes = []

    async def fake_read(image, box=None):
        boxes.append(box)
        return "raw text", "テスト"

    monkeypatch.setattr(ocr, "read", fake_read)
    return boxes


@pytest.fixture
def client(tmp_path, monkeypatch, reads):
    """A client for the webapp, with its data in a temporary folder and no token."""
    monkeypatch.setattr(db, "DB", tmp_path / "kakehashi.db")
    monkeypatch.setattr(main, "IMAGES", tmp_path / "images")
    monkeypatch.setattr(main, "TOKEN", None)
    main.IMAGES.mkdir()
    return TestClient(main.app)


def image_bytes(format: str, color=(200, 30, 30)) -> bytes:
    """Return a small 96x54 image in the given format."""
    out = io.BytesIO()
    Image.new("RGB", (96, 54), color).save(out, format)
    return out.getvalue()
