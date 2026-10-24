"""kakehashi webapp: receives screenshots, runs OCR and shows the shots per game.

Run: uv run uvicorn main:app --host 0.0.0.0 --port 8766
Set KAKEHASHI_TOKEN to require that token in the X-Token header of each shot,
and of each change (edit, delete, box, rename, translate) that does not come from this computer.
"""

import hashlib
import io
import os
import socket
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi import Path as UrlPath
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, StringConstraints

import db
import ocr
import pages
import translate

# A game id: letters, digits and "-". It is also a folder name in IMAGES, so it can never be "..".
GAME_ID = r"^[A-Za-z0-9-]{1,64}$"

IMAGES = Path(__file__).parent / "data" / "images"
IMAGES.mkdir(parents=True, exist_ok=True)

TOKEN = os.environ.get("KAKEHASHI_TOKEN")

# Image formats a device can send, and the file extension for each. A BMP is saved as JPEG.
FORMATS = {"JPEG": "jpg", "PNG": "png", "BMP": "jpg"}

# In the OCR tests, 15 shots read with crop boxes scored 1.00 down to quality 70; 90 keeps a margin.
JPEG_QUALITY = 90



def local_or_token(request: Request, x_token: Annotated[str | None, Header()] = None) -> None:
    """Allow a change from this computer, or from another device with the token. Without a token, allow all."""
    if TOKEN and request.client.host not in ("127.0.0.1", "::1") and x_token != TOKEN:
        raise HTTPException(401, "a change from another device needs the token")


# Routes that change data. The page on http://localhost:8766 needs no token.
LOCAL_OR_TOKEN = [Depends(local_or_token)]

app = FastAPI()
app.mount("/images", StaticFiles(directory=IMAGES), name="images")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


class BoxIn(BaseModel):
    """A crop box: left, top, right, bottom as fractions of the image, 0 to 1."""

    box: db.Box


class TextIn(BaseModel):
    """The edited text of a shot, and the box it came from when "Use for this shot" made it."""

    text: str
    box: db.Box | None = None


class NameIn(BaseModel):
    """The name of a game, as the user types it."""

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class TranslateIn(BaseModel):
    """Japanese text to translate, as the page shows it (with manual edits)."""

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


def load_image(shot) -> Image.Image:
    """Open the saved image of a shot."""
    return Image.open(IMAGES / shot["game"] / shot["name"]).convert("RGB")


def to_jpeg(image: Image.Image) -> bytes:
    """Encode an image as JPEG, with no chroma subsampling, so colored text stays sharp."""
    out = io.BytesIO()
    image.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY, subsampling=0)
    return out.getvalue()


async def read_text(image: Image.Image, box: db.Box | None) -> tuple[str, str]:
    """Return (raw OCR text, clean text), or raise 502 when Google Lens fails."""
    try:
        return await ocr.read(image, box)
    except ocr.OCRError as error:
        raise HTTPException(502, f"Google Lens did not read the image: {error}")


def find_shot(shot_id: int):
    """Return a shot, or raise 404."""
    shot = db.get_shot(shot_id)
    if shot is None:
        raise HTTPException(404, "no such shot")
    return shot


@app.post("/shot")
async def save_shot(
    request: Request,
    game: Annotated[str, Query(pattern=GAME_ID)],
    taken: Annotated[str | None, Query(pattern=r"^\d{8}-\d{6}$")] = None,
    x_token: Annotated[str | None, Header()] = None,
) -> dict:
    """Save the image in the request body, then OCR it.

    The image is saved as data/images/<game>/<hash>.<format>, a BMP as JPEG (about
    1.5 MB becomes about 70 KB). The hash is of the body as sent, so the same image
    sent twice is saved once. `taken` is the capture time (YYYYMMDD-HHMMSS); without it,
    the shot gets the time it arrived. When Google Lens fails, the reply is 502 and no shot is saved:
    the device keeps the shot in its queue and sends it again later.
    """
    if TOKEN and x_token != TOKEN:
        raise HTTPException(401, "bad token")
    body = await request.body()
    try:
        image = Image.open(io.BytesIO(body))
    except UnidentifiedImageError:
        raise HTTPException(400, "not an image")
    if image.format not in FORMATS:
        raise HTTPException(400, f"image format must be JPEG, PNG or BMP, not {image.format}")
    name = f"{hashlib.sha256(body).hexdigest()[:16]}.{FORMATS[image.format]}"
    shot_id = db.existing_shot(game, name)
    if shot_id:
        return {"id": shot_id, "new": False}
    folder = IMAGES / game
    folder.mkdir(exist_ok=True)
    (folder / name).write_bytes(to_jpeg(image) if image.format == "BMP" else body)
    box = db.get_box(game)
    raw, text = await read_text(image.convert("RGB"), box)
    when = datetime.strptime(taken, "%Y%m%d-%H%M%S") if taken else datetime.now()
    shot_id = db.add_shot(name, game, raw, text, when, box)
    return {"id": shot_id, "new": True, "text": text}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    """Show the home page: the newest shot, the recent shots of all games, and the numbers."""
    shots = db.list_shots()
    if not shots:
        return pages.page("kakehashi", shots, 0, pages.empty_view(), "home")
    view = pages.home_view(shots, pages.day_numbers(shots), image_bytes())
    return pages.page("kakehashi", shots, 0, view, "home")


@app.get("/latest")
def latest() -> RedirectResponse:
    """Open the newest shot, or the home page when there are no shots."""
    shots = db.list_shots()
    return RedirectResponse(f"/shot/{shots[0]['id']}" if shots else "/")


def image_bytes() -> int:
    """Return the size of all image files on disk."""
    return sum(path.stat().st_size for path in IMAGES.rglob("*") if path.is_file())


@app.get("/shot/{shot_id}", response_class=HTMLResponse)
def show_shot(shot_id: int) -> str:
    """Show the sidebar and one shot."""
    return page_of(find_shot(shot_id), db.list_shots())


def page_of(shot, shots: list) -> str:
    """Return the full page of one shot, with its number within its game and day."""
    number = pages.day_numbers(shots)[shot["id"]]
    with Image.open(IMAGES / shot["game"] / shot["name"]) as image:
        size = image.size
    count = sum(other["game"] == shot["game"] for other in shots)
    view = pages.shot_view(shot, db.get_box(shot["game"]), number, size, count)
    return pages.page(pages.label(shot, number), shots, shot["id"], view)


@app.get("/search", response_class=HTMLResponse)
def search(q: str = "") -> str:
    """Show the newest shots whose text or translation contains q, in Japanese or English."""
    shots = db.list_shots()
    view = pages.search_view(q, db.search(q), pages.day_numbers(shots))
    return pages.page("Search · kakehashi", shots, 0, view, "search", q)


@app.get("/about", response_class=HTMLResponse)
def about() -> str:
    """Show what kakehashi is, how it works, and the numbers of shots, games and image bytes."""
    shots = db.list_shots()
    return pages.page("About · kakehashi", shots, 0, pages.about_view(shots, image_bytes()), "about")


@app.get("/server", response_class=HTMLResponse)
def server(request: Request) -> str:
    """Show the address of this webapp on the local network, for the device configs."""
    view = pages.server_view(lan_address(), request.url.port or 80, TOKEN is not None)
    return pages.page("Server · kakehashi", db.list_shots(), 0, view, "server")


def lan_address() -> str | None:
    """Return the IPv4 address of this computer on the local network, or None without a network.

    Connecting a UDP socket sends nothing; it only picks the interface of the default route.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("192.0.2.1", 80))
        except OSError:
            return None
        return sock.getsockname()[0]


@app.post("/clear", dependencies=LOCAL_OR_TOKEN)
def clear_database() -> dict:
    """Delete all shots and games from the database. The image files stay on disk."""
    db.clear()
    return {"cleared": True}


@app.post("/shot/{shot_id}/test", dependencies=LOCAL_OR_TOKEN)
async def test_box(shot_id: int, body: BoxIn) -> dict:
    """OCR one shot with a new box. Save nothing."""
    _, text = await read_text(load_image(find_shot(shot_id)), body.box)
    return {"text": text}


@app.post("/shot/{shot_id}/text", dependencies=LOCAL_OR_TOKEN)
def save_text(shot_id: int, body: TextIn) -> dict:
    """Save a manual edit of the text. A new box does not overwrite it."""
    db.set_text(find_shot(shot_id)["id"], body.text)
    if body.box:
        db.set_box_used(shot_id, body.box)
    return {"edited": True}


@app.post("/shot/{shot_id}/translate", dependencies=LOCAL_OR_TOKEN)
def translate_shot(shot_id: int, body: TranslateIn) -> dict:
    """Translate the text of a shot to English and save the translation. A new click replaces it."""
    shot = find_shot(shot_id)
    try:
        translation = translate.translate(body.text)
    except OSError as error:
        raise HTTPException(502, f"Google Translate did not answer: {error}")
    db.set_translation(shot["id"], translation)
    return {"translation": translation}


@app.put("/games/{game}/name", dependencies=LOCAL_OR_TOKEN)
def rename_game(game: str, body: NameIn) -> dict:
    """Give a game a name to show instead of its id."""
    db.rename_game(game, body.name)
    return {"name": body.name}


@app.put("/games/{game}/box", dependencies=LOCAL_OR_TOKEN)
def save_box(game: str, body: BoxIn) -> dict:
    """Save the crop box of a game. Only new shots use it; old shots keep their box and text."""
    db.set_box(game, body.box)
    return {"saved": True}


@app.delete("/games/{game}/box", dependencies=LOCAL_OR_TOKEN)
def clear_box(game: str) -> dict:
    """Clear the crop box of a game. New shots are read on the full screen; old shots keep their text."""
    db.set_box(game, None)
    return {"cleared": True}


@app.delete("/games/{game}", dependencies=LOCAL_OR_TOKEN)
def delete_game(game: Annotated[str, UrlPath(pattern=GAME_ID)]) -> dict:
    """Delete a game: its shots, name and box, then the image files of its shots.

    A new shot of the same game starts again with its game id as the name and no box.
    """
    names = db.delete_game(game)
    if not names:
        raise HTTPException(404, "No shots for this game")
    for name in names:
        delete_image(game, name)
    return {"deleted": len(names)}


@app.delete("/shot/{shot_id}", dependencies=LOCAL_OR_TOKEN)
def delete_shot(shot_id: int) -> dict:
    """Delete one shot, then its image file. `next` is the next older shot of the same game, or None."""
    shot = find_shot(shot_id)
    shots = [other["id"] for other in db.list_shots() if other["game"] == shot["game"]]
    older = shots[shots.index(shot_id) + 1 :]
    db.delete_shot(shot_id)
    delete_image(shot["game"], shot["name"])
    return {"deleted": 1, "next": older[0] if older else None}


def delete_image(game: str, name: str) -> None:
    """Delete one image file that the database named, then its game folder if it is empty.

    The database row is deleted first: if this fails, only an unused file stays, and `make prune` finds it.
    Only a file inside IMAGES is deleted, never a folder with files in it, never a link.
    """
    path = IMAGES / game / name
    if path.is_symlink() or not path.resolve().is_relative_to(IMAGES.resolve()):
        raise HTTPException(500, f"Not deleted, outside the images folder: {game}/{name}")
    path.unlink(missing_ok=True)
    if not any(path.parent.iterdir()):
        path.parent.rmdir()


@app.get("/sidebar")
def sidebar(current: int, since: int) -> dict:
    """Return the newest shot id and the HTML of both sidebars, for the live update."""
    shots = db.list_shots()
    game = pages.current_game(shots, current)
    return {
        "latest": pages.latest_id(shots),
        "shots": pages.shot_list(shots, current, since),
        "games": pages.game_list(shots, game, since),
    }
