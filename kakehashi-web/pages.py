"""HTML for the webapp: the page layout, the shots and games sidebars, the shot view."""

import re
import sqlite3
from datetime import datetime
from html import escape
from pathlib import Path

import db

# Every 3 s, ask for the newest shot id. When it changes, replace both sidebars
# and show the banner. Dates the user opened stay open. The page never navigates
# by itself. The status in the top bar shows "Offline" while the webapp does not answer.
SCRIPT = """
const shotsNav = document.getElementById("shots");
const gamesNav = document.getElementById("games");
const banner = document.getElementById("banner");
const status = document.getElementById("status");
const since = Number(shotsNav.dataset.latest);
let latest = since;
setInterval(async () => {
  let data;
  try {
    const response = await fetch(`/sidebar?current=${shotsNav.dataset.current}&since=${since}`);
    data = await response.json();
  } catch {
    status.textContent = "Offline";
    status.classList.add("offline");
    return;
  }
  status.textContent = "Live";
  status.classList.remove("offline");
  if (data.latest === latest) return;
  latest = data.latest;
  const open = new Set([...shotsNav.querySelectorAll("details[open]")].map((day) => day.dataset.day));
  shotsNav.innerHTML = data.shots;
  shotsNav.querySelectorAll("details").forEach((day) => { if (open.has(day.dataset.day)) day.open = true; });
  gamesNav.innerHTML = data.games;
  banner.href = `/shot/${latest}`;
  banner.hidden = false;
}, 3000);

// Keep the shots list as it was when you open another shot of the same game: the same open days
// and the same scroll position (kept for this tab only). Without this, each new page starts the list
// at the top with only the current day open, and the shot you clicked moves out of view.
window.addEventListener("pagehide", () => {
  sessionStorage.setItem("shotsList", JSON.stringify({
    game: shotsNav.dataset.game,
    scrollTop: shotsNav.scrollTop,
    open: [...shotsNav.querySelectorAll("details[open]")].map((day) => day.dataset.day),
  }));
});
const savedList = JSON.parse(sessionStorage.getItem("shotsList") || "null");
if (savedList && savedList.game === shotsNav.dataset.game) {
  shotsNav.querySelectorAll("details").forEach((day) => { if (savedList.open.includes(day.dataset.day)) day.open = true; });
  shotsNav.scrollTop = savedList.scrollTop;
}
shotsNav.querySelector("a.current")?.scrollIntoView({ block: "nearest" });

"""

PLATFORMS = ["PS Vita", "PSP / PS1", "3DS", "PC"]
RECENT = 10  # shots in the "Recent shots" list of the home page, after the newest


def page(title: str, shots: list[sqlite3.Row], current: int, body: str, active: str = "shots", query: str = "") -> str:
    """Return a full page: the top bar with the search box, the shots of the current game on the left, the body,
    and the games per platform on the right. `active` marks the top bar link of the page; `query` fills the search box."""
    latest = latest_id(shots)
    game = current_game(shots, current)
    links = "".join(
        f'<a href="{href}"{" class=active" if key == active else ""}>{name}</a>'
        for key, href, name in (
            ("home", "/", "Home"), ("shots", "/latest", "Shots"), ("search", "/search", "Search"), ("stats", "/stats", "Stats"),
            ("server", "/server", "Server"), ("about", "/about", "About"),
        )
    )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(title)}</title><link rel="stylesheet" href="/static/style.css?v={version("style.css")}">'
        '<header class="topbar"><a class="brand" href="/"><span class="brand-mark">架</span>kakehashi'
        '<span class="brand-sub">架け橋</span></a>'
        f'<nav class="links">{links}</nav>'
        '<form class="search" action="/search" role="search">'
        f'<input type="search" name="q" value="{escape(query)}" placeholder="Search text" aria-label="Search text"></form>'
        '<span id="status" class="status">Live</span></header>'
        '<aside class="shots-side"><h2 class="side-title">Shots</h2>'
        f'<nav id="shots" data-latest="{latest}" data-current="{current}" data-game="{escape(game or "")}">{shot_list(shots, current, latest)}</nav></aside>'
        f'<main><a id="banner" hidden>New shot</a><div class="content">{body}</div></main>'
        '<aside class="games-side"><h2 class="side-title">Games</h2>'
        f'<nav id="games">{game_list(shots, game, latest)}</nav></aside>'
        f"<script>{SCRIPT}</script>"
    )


def empty_view() -> str:
    """Return the home page body when there are no shots."""
    return (
        '<div class="card empty"><h1>No shots yet</h1>'
        "<p>Press the capture combo on the Vita. New shots show up here within a few seconds.</p></div>"
    )


def home_view(shots: list[sqlite3.Row], numbers: dict[int, int], size: int) -> str:
    """Return the home page: the newest shot with its text, the next RECENT shots of all games, and the numbers.

    `shots` is newest first and not empty. `numbers` are the shot numbers within each game and day.
    """
    newest = shots[0]
    src = f"/images/{escape(newest['game'])}/{escape(newest['name'])}"
    rows = "".join(
        f'<li><a href="/shot/{shot["id"]}"><span class="when">{datetime.fromisoformat(shot["taken"]):%m-%d %H:%M}</span>'
        f'<span class="game">{escape(shot["game_name"])}</span>'
        f'{snippet(shot["text"])}</a></li>'
        for shot in shots[1 : RECENT + 1]
    )
    recent = f'<ul class="recent">{rows}</ul>' if rows else '<p class="none">No other shots yet.</p>'
    return (
        '<div class="shot-head"><h1>Home</h1></div>'
        '<div class="card latest"><div class="text-head"><h2>Latest shot</h2>'
        f'<a class="push" href="/shot/{newest["id"]}">{escape(label(newest, numbers[newest["id"]]))} →</a></div>'
        f'<a href="/shot/{newest["id"]}"><img src="{src}" alt="Newest shot"></a>'
        f'<p class="latest-text" lang="ja">{escape(newest["text"] or "")}</p></div>'
        f'<div class="card text-card"><div class="text-head"><h2>Recent shots</h2></div>{recent}</div>'
        f"{stats_view(shots, size)}"
    )


def search_view(query: str, found: list[sqlite3.Row], numbers: dict[int, int]) -> str:
    """Return the search page: the shots found (newest first), each with its text and translation,
    the query marked in both. `numbers` are the shot numbers within each game and day."""
    query = query.strip()
    if not query:
        return '<div class="shot-head"><h1>Search</h1></div><p class="none">Type a word in Japanese or English.</p>'
    rows = "".join(
        f'<li><a href="/shot/{shot["id"]}"><span class="result-head">{escape(label(shot, numbers[shot["id"]]))}</span>'
        f'<span class="result-text" lang="ja">{mark(shot["text"] or "", query)}</span>'
        + (f'<span class="result-translation" lang="en">{mark(shot["translation"], query)}</span>' if shot["translation"] else "")
        + "</a></li>"
        for shot in found
    )
    if len(found) == db.FOUND:
        count = f"Newest {db.FOUND} shots"
    else:
        count = "1 shot" if len(found) == 1 else f"{len(found)} shots"
    results = f'<ul class="results">{rows}</ul>' if rows else '<p class="none">No shot has this text.</p>'
    return (
        f'<div class="shot-head"><h1>Search: <span lang="ja">{escape(query)}</span></h1></div>'
        f'<div class="card text-card"><div class="text-head"><h2>{count}</h2></div>{results}</div>'
    )


def mark(text: str, query: str) -> str:
    """Return a text as HTML, with each place of the query in <mark>, in any letter case."""
    parts = re.split(f"({re.escape(query)})", text, flags=re.IGNORECASE)
    return "".join(f"<mark>{escape(part)}</mark>" if index % 2 else escape(part) for index, part in enumerate(parts))


def snippet(text: str | None) -> str:
    """Return the text of a shot for one line of the recent list, or a muted "No text"."""
    if not text:
        return '<span class="snippet none-text">No text</span>'
    return f'<span class="snippet" lang="ja">{escape(text)}</span>'


def stats_view(shots: list[sqlite3.Row], size: int) -> str:
    """Return the numbers: shots, games and the size of the images on disk."""
    games = len({shot["game"] for shot in shots})
    return (
        '<div class="stats">'
        f'<div><b>{len(shots)}</b><span>shots</span></div><div><b>{games}</b><span>games</span></div>'
        f'<div><b>{size / 1_000_000:.1f} MB</b><span>images on disk</span></div></div>'
    )


def about_view(shots: list[sqlite3.Row], size: int) -> str:
    """Return the about page: what kakehashi is, how a shot travels, OCR notes and numbers."""
    return (
        '<div class="shot-head"><h1>About</h1></div>'
        '<div class="card info"><p class="lead">kakehashi (架け橋, "bridge") helps you read Japanese games. '
        "Press a button combo while you play. The screenshot comes to this page, OCR reads the text, "
        "and you look up the words with Yomitan in the browser.</p>"
        "<h2>How a shot travels</h2><ol>"
        "<li>The capture plugin on the Vita saves the screen in a queue folder when you press the combo.</li>"
        "<li>The sender plugin sends each shot from the queue to this webapp over Wi-Fi.</li>"
        "<li>The webapp saves the image and reads the text with OCR, inside the crop box of the game.</li>"
        "<li>The page shows the new shot within a few seconds. Hold Shift over a word to look it up with Yomitan.</li>"
        "</ol>"
        "<h2>OCR</h2><ul>"
        "<li>Google Lens (unofficial API). Screenshots go to Google. Google can change or stop this API.</li>"
        "<li>When Lens fails (for example with no network), the shot is not saved: the device keeps it and sends it again later.</li>"
        "</ul>"
        f"<h2>Numbers</h2>{stats_view(shots, size)}</div>"
    )


def server_view(address: str | None, port: int, token: bool) -> str:
    """Return the server page: the address for the device configs, the Vita and 3DS configs and the Shot API."""
    if address is None:
        return (
            '<div class="shot-head"><h1>Server</h1></div>'
            '<div class="card info"><p class="lead">No network. Connect this computer to the network, then reload the page.</p></div>'
        )
    url = f"http://{address}:{port}"
    token_line = "token=&lt;your token&gt;" if token else "token="
    token_text = (
        "On: each shot must send the <code>X-Token</code> header with the value of <code>KAKEHASHI_TOKEN</code>."
        if token
        else "Off: <code>KAKEHASHI_TOKEN</code> is not set, so the webapp accepts shots without a token."
    )
    return (
        '<div class="shot-head"><h1>Server</h1></div>'
        f'<div class="card info"><h2>Address on the local network</h2><p class="address"><code>{url}</code></p>'
        "<p>Devices on the same Wi-Fi send shots to this address. It can change when this computer joins another network.</p>"
        "<h2>PS Vita</h2><p>In <code>ux0:data/kakehashi/config.txt</code> (edit it with VitaShell, then reboot):</p>"
        f"<pre>server={address}\nport={port}\n{token_line}</pre>"
        "<h2>3DS</h2><p>In <code>sdmc:/kakehashi/config.txt</code> (edit it over FTP, then start the game again). "
        "A line like <code>combo.0004000000108800=L+DOWN</code> sets the combo for one game, by title ID:</p>"
        f"<pre>server={address}\nport={port}\n{token_line}\ncombo=L+SELECT</pre>"
        f"<h2>Token check</h2><p>{token_text}</p>"
        "<h2>Shot API</h2><p>Other devices and scripts send the image as the raw request body:</p>"
        f"<pre>POST {url}/shot?game=&lt;game id&gt;&amp;taken=YYYYMMDD-HHMMSS</pre></div>"
    )


def latest_id(shots: list[sqlite3.Row]) -> int:
    """Return the highest shot id, or 0 when there are no shots."""
    return max((shot["id"] for shot in shots), default=0)


def platform(game: str) -> str:
    """Return the platform of a game id.

    PSP / PS1: "PSPEMU..." (an Adrenaline bubble on the Vita, one per game).
    PS Vita: 4 letters and 5 digits (PCSG00563) or "main" (the home screen).
    3DS: 16 hex digits (0004000000055D00). Anything else: PC.
    """
    if game.startswith("PSPEMU"):
        return "PSP / PS1"
    if re.fullmatch(r"[A-Z]{4}\d{5}", game) or game == "main":
        return "PS Vita"
    if re.fullmatch(r"[0-9A-Fa-f]{16}", game):
        return "3DS"
    return "PC"


def current_game(shots: list[sqlite3.Row], current: int) -> str | None:
    """Return the game of the current shot, or None when there is no current shot."""
    return next((shot["game"] for shot in shots if shot["id"] == current), None)


def day_numbers(shots: list[sqlite3.Row]) -> dict[int, int]:
    """Return the number of each shot within its game and day: the first shot of a game on a day is 1.

    The order is the capture time (`taken`), then the id. The database id stays in the URLs.
    """
    numbers = {}
    counts: dict[tuple[str, str], int] = {}
    for shot in sorted(shots, key=lambda shot: (shot["taken"], shot["id"])):
        key = (shot["game"], shot["taken"][:10])
        counts[key] = counts.get(key, 0) + 1
        numbers[shot["id"]] = counts[key]
    return numbers


def shot_list(shots: list[sqlite3.Row], current: int, since: int) -> str:
    """Return the shots of the current shot's game, grouped by day, newest first.

    Each day can be opened and closed. The day of the current shot and days with new shots
    (id above `since`) are open. Each shot shows its time and its number in the day, or a "new" label.
    """
    game = current_game(shots, current)
    numbers = day_numbers(shots)
    days: dict[datetime, list[str]] = {}
    open_days = set()
    for shot in shots:
        if shot["game"] != game:
            continue
        taken = datetime.fromisoformat(shot["taken"])
        day = datetime(taken.year, taken.month, taken.day)
        new = shot["id"] > since
        if shot["id"] == current or new:
            open_days.add(day)
        css = "current" if shot["id"] == current else ""
        tag = '<span class="new">new</span>' if new else f'<span class="id">#{numbers[shot["id"]]}</span>'
        days.setdefault(day, []).append(
            f'<li><a class="{css}" href="/shot/{shot["id"]}"><span>{taken:%H:%M:%S}</span>{tag}</a></li>'
        )
    if not days:
        return '<p class="none">Pick a game on the right.</p>'
    return "".join(
        f'<details data-day="{day:%Y-%m-%d}"{" open" if day in open_days else ""}>'
        f'<summary><span>{day:%a}</span> {day:%Y-%m-%d}<span class="count">{len(items)}</span></summary>'
        f'<ul>{"".join(items)}</ul></details>'
        for day, items in days.items()
    )


def game_list(shots: list[sqlite3.Row], current: str | None, since: int) -> str:
    """Return the games per platform, the game with the newest shot first.

    A game links to its newest shot and shows its shot count. A game with new shots
    (id above `since`) gets a dot.
    """
    games: dict[str, dict] = {}
    for shot in shots:
        game = games.setdefault(shot["game"], {"name": shot["game_name"], "latest": shot["id"], "count": 0, "new": False})
        game["count"] += 1
        game["new"] = game["new"] or shot["id"] > since
    html = []
    for name in PLATFORMS:
        items = [
            f'<li><a class="{"current" if game == current else ""}" href="/shot/{info["latest"]}">'
            f'<span class="name">{escape(info["name"])}</span>{"<span class=dot></span>" if info["new"] else ""}'
            f'<span class="count">{info["count"]}</span></a></li>'
            for game, info in games.items()
            if platform(game) == name
        ]
        body = f'<ul>{"".join(items)}</ul>' if items else '<p class="none">No games yet</p>'
        html.append(f"<h3>{name}</h3>{body}")
    return "".join(html)


def label(shot: sqlite3.Row, number: int) -> str:
    """Return the page title of a shot: "P4G #7 · 2026-10-14 15:24:49". The number counts within the game and day."""
    return f"{shot['game_name']} #{number} · {taken_text(shot)}"


def taken_text(shot: sqlite3.Row) -> str:
    """Return the full capture time of a shot: "2026-10-14 15:24:49"."""
    return datetime.fromisoformat(shot["taken"]).strftime("%Y-%m-%d %H:%M:%S")


def shot_view(shot: sqlite3.Row, game_box: tuple | None, number: int, size: tuple[int, int], count: int) -> str:
    """Return one shot: the image with the crop box buttons on top, then the editable OCR text and the translation.

    The image scales to fit a box of fixed height (`size` is its width and height in pixels), so the text
    starts at the same place on every shot. "Enlarge" shows the image as large as the window allows.
    PSP and PS1 shots are small and always scaled up, so they keep sharp pixels.
    "Rename game" sets the game name. "Delete shot" deletes this shot and its image file. "Delete game" deletes the game: all `count` shots, their image files, its name and its box.
    The outline shows the box that this shot's text came from,
    and "Hide box" hides it. "Clear box" shows when the game has a box.
    static/box.js draws, tests and saves a new box, copies the text, translates it (Translation card, always shown; a hint while the shot has no translation), edits the translation, and copies the image.
    """
    src = f"/images/{escape(shot['game'])}/{escape(shot['name'])}"
    own = db.used_box(shot)
    saved = box_style(own) if own else ""
    edited = '<span class="chip edited">Edited</span>' if shot["edited"] else ""
    no_own = "" if own else " hidden"
    no_game_box = "" if game_box else " hidden"
    width, height = size
    pixels = " pixels" if platform(shot["game"]) == "PSP / PS1" else ""
    return (
        f'<div class="shot-head"><h1 id="game-name">{escape(shot["game_name"])}</h1>'
        '<button id="rename" class="ghost">Rename</button>'
        f'<button id="delete-game" class="ghost danger" data-count="{count}">Delete game</button>'
        '<button id="copy-text" class="push">Copy text</button>'
        '<button id="copy">Copy image</button><button id="delete-shot" class="ghost danger">Delete shot</button></div>'
        f'<div class="meta"><span class="chip">Shot #{number}</span><span class="chip">{taken_text(shot)}</span>{edited}</div>'
        '<div class="card shot-image"><div class="toolbar"><div class="group"><span class="group-label">Crop box</span>'
        '<button id="test" disabled>Test</button><button id="use" disabled>Use for this shot</button>'
        '<button id="save" class="primary" disabled>Save for this game</button></div>'
        f'<div class="group"><button id="toggle" class="ghost"{no_own}>Hide box</button>'
        f'<button id="clear" class="ghost"{no_game_box}>Clear box</button></div>'
        '<button id="enlarge" class="push">Enlarge</button></div>'
        f'<div class="image-box{pixels}" style="--ratio:{width / height:.4f}">'
        f'<div id="frame" data-shot="{shot["id"]}" data-game="{escape(shot["game"])}">'
        f'<img src="{src}" draggable="false" alt="Screenshot {shot["id"]}">'
        f'<div id="saved" class="box" style="{saved}"{no_own}></div>'
        '<div id="drawn" class="box" hidden></div></div></div>'
        '<p id="values" class="hint">Drag over the dialogue text to draw a box.</p>'
        '<p id="result" class="result" lang="ja"></p></div>'
        '<div class="card text-card"><div class="text-head"><h2>Text</h2><span class="hint">Click to edit</span>'
        '<button id="translate" class="push">Translate</button></div>'
        f'<div id="text" lang="ja" contenteditable spellcheck="false">{escape(shot["text"])}</div></div>'
        '<div id="translation-card" class="card text-card"><div class="text-head"><h2>Translation</h2>'
        '<button id="edit-translation" class="push">Edit translation</button>'
        '<button id="copy-translation">Copy translation</button></div>'
        f'<div id="translation" lang="en">{escape(shot["translation"] or "")}</div></div>'
        f'<dialog id="viewer" class="{pixels.strip()}" style="--ratio:{width / height:.4f}"><img src="{src}" alt="Screenshot {shot["id"]}, enlarged"></dialog>'
        f'<script src="/static/box.js?v={version("box.js")}"></script>'
    )


def version(name: str) -> int:
    """Return the change time of a static file. It goes in the file URL, so a browser never uses an old cached copy."""
    return int((Path(__file__).parent / "static" / name).stat().st_mtime)


def box_style(box: tuple) -> str:
    """Return CSS that places a box over the image, in percent."""
    left, top, right, bottom = box
    return f"left:{left:.1%};top:{top:.1%};width:{right - left:.1%};height:{bottom - top:.1%}"
