# kakehashi-web

Desktop webapp: receives screenshots, reads their text with OCR, shows them per game, translates and searches them.

## Run

Needs [uv](https://docs.astral.sh/uv/). Runs on macOS and Linux (both tested) and should run on Windows (not tested).

```
cd kakehashi-web
uv run uvicorn main:app --host 0.0.0.0 --port 8766
```

The first run installs the dependencies. Stop the server with Ctrl+C.

To require a token, start the server with `KAKEHASHI_TOKEN=<token>`. Then each shot needs the token, and so does each change from another device (edit, delete, clear, box, rename, translate, edit translation). Changes from this computer itself (`http://localhost:8766`) need no token, so the page works there. On another device the page shows the shots, and a change shows "Not done". Without a token, anyone who can reach the port can change or delete shots: set one on a shared network.

- Open http://localhost:8766/ for the home page: the newest shot, the recent shots of all games, and the numbers. "Shots" in the top bar opens the newest shot. The left sidebar shows the shots of the current game by day; the right sidebar shows the games per platform.
- `--host 0.0.0.0` lets other devices on your Wi-Fi reach the server. The console sends to `http://<computer IP>:8766`. The `/server` page shows that address.
- Images and the database go in `data/`. Delete `data/` for a clean start. `KAKEHASHI_DATA=<folder>` uses another folder (for example for a demo). The database uses WAL mode, so `kakehashi.db` has two more files next to it while the server runs (`-wal`, `-shm`). To copy the database, stop the server first, or use `sqlite3 data/kakehashi.db ".backup copy.db"`.
- Backup: `make backup` (from the repo root) adds a dated copy of the database and the new image files to `~/kakehashi-backups`, or to `make backup BACKUP_DIR=<folder>`. It is safe while the server runs. It never deletes or overwrites in the backup, so a deleted shot stays there. It then checks the database copy, and that each shot has its image in the backup. Put the folder on another disk (an external disk, a NAS, or a synced cloud folder): a backup on the same disk does not survive a disk failure. To restore: stop the server, then `make restore` (the newest database copy) or `make restore DB=<backup>/db/kakehashi-<time>.db`, with the same `BACKUP_DIR`. It refuses while a server answers on port 8766, and when the copy is damaged or an image is missing in the backup. It never deletes: the current `data/` becomes `data.before-restore-<time>/` (delete it yourself when the restore is good). Then `data/` gets the database copy and only the images it names.

## Files

| File | What it does |
|---|---|
| `main.py` | Web routes |
| `pages.py` | HTML: page layout, shots and games sidebars, shot view |
| `board.py` | Stats board: reading numbers and the `/stats` page |
| `static/style.css` | Page styles; dark mode follows the system setting |
| `static/box.js` | Shot page: crop box, text edits, translate, copy, rename, delete |
| `ocr.py` | OCR with Google Lens, text cleanup |
| `translate.py` | Japanese to English with Google Translate |
| `db.py` | SQLite storage (`data/kakehashi.db`) and full text search |

## API

### Shot API

The one entry point for all devices (Vita, 3DS) and scripts on the computer.

```
POST /shot?game=<game id>[&taken=YYYYMMDD-HHMMSS]
X-Token: <token>
<image bytes: JPEG, PNG or BMP>
```

- `game`: letters, digits and dashes, 1 to 64 characters. For example `PCSG00123` (Vita), `0004000000055D00` (3DS), `pc-steam-1234`.
- `taken`: optional capture time. Without it, the shot gets the time it arrived. A device that queues shots offline sends it.
- The webapp detects the image format from the bytes and saves the image as `data/images/<game>/<hash>.<jpg|png>`. A BMP is saved as JPEG (quality 90). The hash is the first 16 hex characters of the SHA-256 of the body as sent.
- The same image sent twice is saved once, so a device can retry safely.

| Reply | When |
|---|---|
| `200 {"id", "new": true, "text"}` | Saved and read with OCR |
| `200 {"id", "new": false}` | Already saved before |
| `400` | Not an image, or not JPEG, PNG or BMP |
| `401` | Bad token (only when `KAKEHASHI_TOKEN` is set) |
| `422` | Bad `game` or `taken` |

```
curl -H "X-Token: abc123" --data-binary @shot.jpg "localhost:8766/shot?game=PCSG00123&taken=20261011-142233"
```

### Pages and other routes

`GET /` shows the home page. `GET /latest` redirects to the newest shot (to `/` when there are no shots). `GET /shot/<id>` shows one shot: the image on top, in a box of fixed height (so the text always starts at the same place), then the editable OCR text and the translation. **Enlarge** shows the image as large as the window allows (a click or Esc closes it). Both pages have the two sidebars.

The search box in the top bar (on every page) opens `GET /search?q=<text>`; the **Search** link in the top bar opens the empty search page. It shows the newest 100 shots whose text or translation contains the text, in all games, with the text marked. It finds exact text, as Ctrl+F does: Japanese or English, any letter case. `まほう` does not find `魔法`, and `行く` does not find `行こう`. 3 or more characters use the trigram index (SQLite FTS5); 1 or 2 characters read all rows.

`GET /stats` (top bar link **Stats**) shows the stats board: Japanese characters (kana and kanji) read today, in the last 7 days and in total, the streak of days in a row with shots, the share of shots translated, a heatmap of characters per day for one calendar year (`?year=2026`, default this year; one link per year with shots; point at a day to see `YYYY-MM-DD: N characters`), and a table per game, 10 games per page (`?page=2`; characters, shots, days played, first and last day, translated). A day is the date of the capture time.

`GET /about` shows what kakehashi is, how a shot travels, the OCR engines, and the numbers of shots, games and image bytes on disk.

`GET /server` shows the address of this computer on the local network and the port (for example `http://192.168.1.10:8766`), a ready `config.txt` block for the Vita, whether the token check is on (never the token itself), and the Shot API URL. The top bar links to both pages.

`GET /sidebar?current=<id>&since=<id>` returns `{"latest", "shots", "games"}`: the newest shot id and the HTML of both sidebars. Shots with an id above `since` get a "new" label, and their game gets a dot.
The page calls it every 3 s. When `latest` changes, the page replaces both sidebars (days the user opened stay open) and shows a "New shot" toast in the bottom-right corner. The page never opens the new shot by itself. The top bar shows "Live", or "Offline" while the webapp does not answer.

Left sidebar: the shots of the current shot's game, newest `taken` first, grouped by day (`Fri 2026-10-16`, with the shot count). A day opens and closes with a click. The day of the current shot and days with new shots are open. When you open another shot of the same game, the list keeps its open days and scroll position, so the shot you clicked stays in place (kept per tab in `sessionStorage`); after a game change, the list starts at the top. Each row shows the time and the shot number (`15:24:49  #7`). The number counts within the game and day: the first shot of a game on a day is `#1` (`pages.day_numbers`, by `taken`). The URL keeps the database id (`/shot/<id>`).

Right sidebar: the games per platform (PS Vita, PSP / PS1, 3DS, PC), the game with the newest shot first, each with its shot count. A click opens the game's newest shot. The platform comes from the game ID (`pages.platform`): `PSPEMU...` (an Adrenaline bubble) is PSP / PS1; 4 letters and 5 digits or `main` is PS Vita; 16 hex digits is 3DS; anything else is PC.

`GET /images/<game>/<name>` returns a saved image.

`DELETE /shot/<id>` deletes one shot, then its image file, and returns `next`: the next older shot of the same game (or `null`). The **Delete shot** button calls it after a confirm and opens `next` (or the home page).

`DELETE /games/<game>` deletes a game: its shots, its name and its box, then the image files of its shots. A new shot of the same game starts again with its game ID as the name and no box. The **Delete game** button calls it after a confirm.

Both delete only the files that the database names, one at a time, inside `data/images/`: never a link, never a folder with files in it (an empty game folder is removed). The database row goes first; if a file delete fails, only an unused file stays. `make prune` (from the repo root) lists unused files; `uv run tools/prune_images.py --delete` deletes them.

`POST /clear` deletes all shots and games (texts and boxes) from the database; the images stay on disk. It has no button; use it with `curl` for fresh test data.

`POST /shot/<id>/text` with `{"text"}` saves a manual edit and marks the shot as edited. The page sends it when the text loses focus.

### Crop box

A box is `[left, top, right, bottom]` as fractions of the image, 0 to 1. One box per game.

- `POST /shot/<id>/test` with `{"box"}` runs OCR on this shot with the box and returns `{"text"}`. It saves nothing.
- `PUT /games/<game>/box` with `{"box"}` saves the box. `DELETE /games/<game>/box` clears it.
  Only new shots use the change. Old shots keep their box and text, so a box change makes no OCR calls (a re-read of all shots would be thousands of Lens calls on a long game).

On the shot page, the header shows the game name, the shot number in its game and day, and the full capture time (`2026-10-14 15:24:49`). The text comes first, with **Translate**; the crop box buttons are above the image. Drag over the dialogue text, click **Test**, compare the text with the image, then click one of these:

- **Use for this shot**: OCR reads the box, and the result replaces the text of this shot only. The shot is marked as edited, and the box becomes its outline (`POST /shot/<id>/text` with `{"text", "box"}`). The box is not saved for the game. Use it for scenes the game box does not fit.
- **Save for this game**: new shots of the game use the box. Old shots keep their text; use **Use for this shot** to read one again. **Clear box**: new shots are read on the full screen. The dashed green outline on each shot shows the box that the shot's own text came from (`box_used`), not the game's current box.
- **Hide box** / **Show box**: hides or shows the green outlines on all shots of the game. The choice is kept in this browser (localStorage), not in the database.
- **Rename** (next to the game name): sets the name that the sidebar and the shot page show instead of the game ID. `PUT /games/<game>/name` with `{"name"}`.
- **Translate**: shows the English translation (Google Translate) in the Translation card under the text, and saves it with the shot. The card is always shown; before the first translation it says "Not translated yet. Click Translate." A new click translates again and replaces the saved translation; an edit of the text does not change it. Edit the text first if the OCR is wrong. `POST /shot/<id>/translate` with `{"text"}` returns `{"translation"}`. **Copy translation** copies it.
- **Edit translation**: makes the translation editable; the button becomes **Save translation**, and a click saves it (`POST /shot/<id>/translation` with `{"translation"}`; empty clears it). A new **Translate** click replaces the edit.
- **Copy text** and **Copy image** (top right): copy the text, or the shot as PNG at full size, to the clipboard. The button shows a check sign when done. Browsers allow this only on `http://localhost:8766`; on the network address the page says so.

## OCR

Google Lens (unofficial API) reads the crop box of the game, or the full screen when there is no box. If Lens fails, `POST /shot` answers 502 and saves nothing; the console keeps the shot in its queue and sends it again later. **Test** and **Use for this shot** show the error. The webapp makes one Lens call at a time: when two reads come together (a shot from the Vita and a **Test** click, or two devices), the second waits. Run one uvicorn worker (the default), because the lock is per process.
Cleanup drops furigana (words shorter than 60% of the tallest word), drops a word that Lens returns twice at the same place, removes `▼ > ＞` and spaces, and changes `･･･` to `…`.
The raw OCR output is also saved.

Without a box, speaker names and menus get into the text.
