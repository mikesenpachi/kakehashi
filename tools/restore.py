# /// script
# requires-python = ">=3.12"
# ///
"""Restore the shots from a backup that tools/backup.py made.

Stop the server first: the tool refuses while a server answers on localhost:8766 (KAKEHASHI_PORT to change).
Nothing is deleted: the current data folder is renamed to <data>.before-restore-YYYYMMDD-HHMMSS.
Then the data folder gets the database copy, and the image files that this copy names.
Run from the repo root (the data folder is KAKEHASHI_DATA, default kakehashi-web/data):
    uv run tools/restore.py <backup folder>             restore the newest database copy
    uv run tools/restore.py <backup folder> <db file>   restore this database copy
"""

import os
import shutil
import socket
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DATA = Path(os.environ.get("KAKEHASHI_DATA") or Path(__file__).parent.parent / "kakehashi-web" / "data")
PORT = int(os.environ.get("KAKEHASHI_PORT") or 8766)


def server_running() -> bool:
    """Return True when something answers on localhost:PORT."""
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def pick_database(backup: Path, name: str | None) -> Path:
    """Return the database copy to restore: the one named, or the newest in backup/db."""
    if name:
        return Path(name).expanduser()
    copies = sorted((backup / "db").glob("kakehashi-*.db"))
    if not copies:
        sys.exit(f"No database copy in {backup / 'db'}")
    return copies[-1]


def shots_of(database: Path) -> list[tuple[str, str]]:
    """Check a database copy and return its shots as (game, image name)."""
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as conn:
            result = conn.execute("pragma integrity_check").fetchone()[0]
            shots = conn.execute("select game, name from shots").fetchall()
        conn.close()
    except sqlite3.DatabaseError as error:
        sys.exit(f"Cannot read {database}: {error}. Nothing changed.")
    if result != "ok":
        sys.exit(f"The database copy is damaged: {result}. Nothing changed.")
    return shots


def main() -> None:
    if len(sys.argv) not in (2, 3):
        sys.exit("Usage: uv run tools/restore.py <backup folder> [<db file>]")
    backup = Path(sys.argv[1]).expanduser()
    if server_running():
        sys.exit(f"A server answers on port {PORT}. Stop it first, then restore.")
    database = pick_database(backup, sys.argv[2] if len(sys.argv) == 3 else None)
    shots = shots_of(database)
    missing = [f"{game}/{name}" for game, name in shots if not (backup / "images" / game / name).is_file()]
    if missing:
        sys.exit(f"{len(missing)} shots have no image in the backup, first: {missing[0]}. Nothing changed.")
    if DATA.exists():
        old = DATA.with_name(f"{DATA.name}.before-restore-{datetime.now():%Y%m%d-%H%M%S}")
        DATA.rename(old)
        print(f"Current data moved to: {old}")
    (DATA / "images").mkdir(parents=True)
    shutil.copy2(database, DATA / "kakehashi.db")
    for game, name in shots:
        (DATA / "images" / game).mkdir(exist_ok=True)
        shutil.copy2(backup / "images" / game / name, DATA / "images" / game / name)
    print(f"Restored {database.name}: {len(shots)} shots and their images, in {DATA}")


if __name__ == "__main__":
    main()
