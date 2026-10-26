# /// script
# requires-python = ">=3.12"
# ///
"""Back up the shots: a dated copy of the database, and the image files that are not in the backup yet.

Image files never change (each name is the hash of its content), so the backup only adds new files.
It never deletes or overwrites a file in the backup: a shot deleted in the webapp stays in the backup.
The database copy uses the SQLite backup API, so it is safe while the server runs.
At the end, the copy gets an integrity check, and each shot in it must have its image in the backup.
Run from the repo root (the data folder is KAKEHASHI_DATA, default kakehashi-web/data):
    uv run tools/backup.py <backup folder>
The backup folder gets:
    db/kakehashi-YYYYMMDD-HHMMSS.db   one per run
    images/<game>/<name>              all image files
To restore: stop the server, copy one db file to <data>/kakehashi.db and the images folder to <data>/images.
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DATA = Path(os.environ.get("KAKEHASHI_DATA") or Path(__file__).parent.parent / "kakehashi-web" / "data")


def copy_database(backup: Path) -> Path:
    """Copy the database into backup/db with the SQLite backup API and return the copy."""
    folder = backup / "db"
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / f"kakehashi-{datetime.now():%Y%m%d-%H%M%S}.db"
    with sqlite3.connect(DATA / "kakehashi.db") as source, sqlite3.connect(copy) as target:
        source.backup(target)
    source.close()
    target.close()
    return copy


def copy_images(backup: Path) -> tuple[int, int]:
    """Copy the image files that the backup does not have yet. Return (files copied, bytes copied).

    A file of another size in the backup (a copy cut short) is copied again. A copy goes to a .part file first.
    """
    copied = size = 0
    for path in sorted((DATA / "images").glob("*/*")):
        target = backup / "images" / path.parent.name / path.name
        if target.exists() and target.stat().st_size == path.stat().st_size:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        shutil.copy2(path, part)
        part.replace(target)
        copied += 1
        size += path.stat().st_size
    return copied, size


def check(copy: Path, backup: Path) -> list[str]:
    """Check the database copy and return the shots whose image is not in the backup, as "game/name"."""
    with sqlite3.connect(copy) as conn:
        result = conn.execute("pragma integrity_check").fetchone()[0]
        if result != "ok":
            sys.exit(f"The database copy is damaged: {result}")
        shots = conn.execute("select game, name from shots").fetchall()
    conn.close()
    return [f"{game}/{name}" for game, name in shots if not (backup / "images" / game / name).is_file()]


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: uv run tools/backup.py <backup folder>")
    backup = Path(sys.argv[1]).expanduser()
    copy = copy_database(backup)
    copied, size = copy_images(backup)
    missing = check(copy, backup)
    print(f"Database: {copy}")
    print(f"Images: {copied} new files, {size / 1_000_000:.1f} MB, in {backup / 'images'}")
    if missing:
        print(f"{len(missing)} shots have no image file (not in the data folder either):")
        print("\n".join(f"  {name}" for name in missing))
        sys.exit(1)
    print("Check: the database copy is ok, and every shot has its image in the backup.")


if __name__ == "__main__":
    main()
