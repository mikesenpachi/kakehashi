# /// script
# requires-python = ">=3.12"
# ///
"""List the image files that no shot uses, and delete them only when asked.

The webapp deletes a shot's file with the shot. If a file delete fails, or a file has no shot for another reason,
this tool finds it. It finds the files in kakehashi-web/data/images/ that have no shot in kakehashi.db.
Run from the repo root:
    uv run tools/prune_images.py            list the files and their total size (deletes nothing)
    uv run tools/prune_images.py --delete   delete those files, then the game folders that are empty
"""

import sqlite3
import sys
from pathlib import Path

DATA = Path(__file__).parent.parent / "kakehashi-web" / "data"


def unused_files() -> list[Path]:
    """Return the image files with no shot in the database."""
    with sqlite3.connect(DATA / "kakehashi.db") as conn:
        used = {(game, name) for game, name in conn.execute("select game, name from shots")}
    return sorted(
        path for path in (DATA / "images").glob("*/*") if path.is_file() and (path.parent.name, path.name) not in used
    )


def main() -> None:
    files = unused_files()
    for path in files:
        print(path.relative_to(DATA))
    size = sum(path.stat().st_size for path in files)
    print(f"{len(files)} unused files, {size / 1_000_000:.1f} MB")
    if not files:
        return
    if "--delete" not in sys.argv:
        print("Nothing deleted. To delete them: uv run tools/prune_images.py --delete")
        return
    for path in files:
        path.unlink()
    for folder in {path.parent for path in files}:
        if not any(folder.iterdir()):
            folder.rmdir()
    print("Deleted.")


if __name__ == "__main__":
    main()
