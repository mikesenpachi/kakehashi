# experiments

OCR test scripts. They need your own screenshots in `samples/` (the repo has none: game screenshots are copyrighted). Git ignores `samples/`.

## Samples

- One folder per game, for example `samples/time-travelers/`, with PNG screenshots named by capture time: `2026-10-11-183738.png`.
- `samples/expected.tsv` holds the correct text of each dialogue shot: `<folder>/<file><TAB><text>`. Only the dialogue: no furigana, no speaker name, no `>` or arrow markers, lines joined.
- 3DS shots go in `samples/3ds/<game>/`, with their own `samples/3ds/expected.tsv`.

## Scripts

- `ocr_test.py`: runs an OCR engine on a crop of each shot's text box (one box per game, in `BOXES`) and compares the result with `samples/expected.tsv`. Engines: `manga` (manga-ocr), `lens` (Google Lens), `lens-clean` (Google Lens with furigana and marker removal). Run from the repo root: `uv run experiments/ocr_test.py lens-clean`
- `ocr_3ds.py`: the webapp's OCR on 3DS top screens (400x240) at 1x, 2x and 3x size, with and without the game's crop box. Run from `kakehashi-web`: `PYTHONPATH=. uv run ../experiments/ocr_3ds.py`

Set the crop boxes in each script for your own games.
