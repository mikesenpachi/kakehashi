# kakehashi

[![Tests](https://github.com/mikesenpachi/kakehashi/actions/workflows/test.yml/badge.svg)](https://github.com/mikesenpachi/kakehashi/actions/workflows/test.yml)

**kakehashi** (架け橋, "bridge") helps you read Japanese games.

Press a button combo while you play on a PS Vita (also PSP and PS1 games in Adrenaline) or a 3DS. The screenshot goes to a webapp on your computer, which reads the text with OCR. You read the text in the browser and look up words with [Yomitan](https://yomitan.wiki/).

## What it does

- **Capture on the console:** a plugin saves the screen when you press the combo, and shows "SAVED" on the screen. Shots wait in a queue on the console and go to the computer when Wi-Fi is on.
- **OCR:** Google Lens reads the text. Furigana is removed. When Lens fails, the console keeps the shot and sends it again later.
- **Crop box per game:** draw a box around the dialogue once, and new shots of that game read only the box.
- **Read and look up:** the text shows next to the shot, ready for Yomitan. You can edit the text.
- **Translate:** one click shows an English translation (Google Translate) and saves it with the shot.
- **Search:** find any Japanese or English text in all your shots.
- **Live:** new shots show up in the open page within a few seconds.

## Requirements

- A computer with [uv](https://docs.astral.sh/uv/): macOS or Linux (both tested), or Windows (not tested).
- One or both of:
  - A PS Vita with HENkaku / taiHEN (tested on firmware 3.65). PSP and PS1 games run in Adrenaline.
  - A 3DS with Luma3DS and its plugin loader (tested on a New 3DS XL with Luma3DS v13.3.3).
- The console and the computer on the same network.
- A browser with the [Yomitan](https://yomitan.wiki/) extension and a Japanese dictionary.

## Quick start

1. Start the webapp on the computer (macOS or Linux; on Windows PowerShell, first `$env:KAKEHASHI_TOKEN="<pick a token>"`, then the `uv run` command alone):
   ```
   cd kakehashi-web
   KAKEHASHI_TOKEN=<pick a token> uv run uvicorn main:app --host 0.0.0.0 --port 8766
   ```
   The first run installs the dependencies. Open http://localhost:8766/.
2. Open http://localhost:8766/server. It shows the computer's address and a ready `config.txt` block for the console.
3. Install the plugin on your console and put that `config.txt` on it:
   - Vita: [kakehashi-vita/README.md](kakehashi-vita/README.md)
   - 3DS: [kakehashi-3ds/README.md](kakehashi-3ds/README.md)
4. Play, and press the combo (Vita: L+R+SELECT, 3DS: L+SELECT, both can be changed). The shot shows up in the page.
5. Hold Shift over a word to look it up with Yomitan.

The token is optional, but set one on a shared network. Without it, anyone who can reach the port can change or delete your shots. More about the webapp, its pages and its API: [kakehashi-web/README.md](kakehashi-web/README.md).

## Privacy

- Each screenshot is sent to Google Lens for OCR.
- **Translate** sends the text to Google Translate.
- Shots, texts and translations stay on your computer, in `kakehashi-web/data/`.

## Disclaimers

- OCR and translation use Google endpoints that Google does not document: Google Lens through [chrome-lens-py](https://github.com/bropines/chrome-lens-py), and the Google Translate endpoint of the Chrome extension. Google can change or stop them at any time, and their use may not follow Google's terms. Use them at your own risk.
- kakehashi is not affiliated with or endorsed by Sony, Nintendo, Google, or any game publisher.
- The plugins need a console with custom firmware. kakehashi does not help with piracy; use it with games you own.
- The software comes with no warranty (see [LICENSE](LICENSE)). A kernel plugin can stop a console from booting normally; each plugin README says how to recover.

## Development

From the repo root:

| Command | What it does |
|---|---|
| `make server` | Start the webapp on port 8766, with reload on `.py` changes |
| `make test` | Run the webapp unit tests (temporary data, fake OCR, no network) |
| `make plugins` | Build the Vita plugins (needs VitaSDK, see the Vita README) |
| `make zip-vita` | Build the Vita plugins and zip them (`release/kakehashi-vita.zip`) |
| `make plugin-3ds` | Build the 3DS plugin in Docker |
| `make zip-3ds` | Build the 3DS plugin and zip it for the SD card (`release/kakehashi-3ds.zip`) |
| `make demo` | Start a demo server on port 8767 with empty data; then `uv run tools/demo.py` sends demo screens (public domain text, no real game) |
| `make help` | List all targets |

GitHub Actions runs the tests on Linux, macOS and Windows for each push to `main` and each pull request (`.github/workflows/test.yml`).

| Folder | Contents |
|---|---|
| `kakehashi-web/` | The webapp (FastAPI, SQLite) |
| `kakehashi-vita/` | Vita plugins in C: capture (kernel) and sender (SceShell) |
| `kakehashi-3ds/` | 3DS plugin in C++ (CTRPluginFramework) |
| `tools/` | Scripts for the webapp data, and `demo.py` for recordings |
| `experiments/` | OCR test scripts |

All devices use one contract, the Shot API: `POST /shot?game=<id>` with the image as the body. A new device needs only that.

## License

MIT, see [LICENSE](LICENSE). The 3DS plugin includes code from CTRPluginFramework and libctru under their own licenses (see [kakehashi-3ds/README.md](kakehashi-3ds/README.md#licenses)).
