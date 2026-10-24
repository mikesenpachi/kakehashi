"""One-time conversion: save each BMP shot as JPEG and rename it in the database.

Run from kakehashi-web: uv run convert_bmps.py
The name keeps its hash: <hash>.bmp becomes <hash>.jpg. Each BMP moves to
data/bmp_backup/<game>/; delete that folder after a check of the shots.
BMP files that no shot uses (left from "Clear database") are not touched.
"""

from PIL import Image

import db
from main import IMAGES, to_jpeg

BACKUP = IMAGES.parent / "bmp_backup"


def convert(conn, shot) -> None:
    """Write the JPEG of one BMP shot, rename the shot, and move the BMP to the backup."""
    bmp = IMAGES / shot["game"] / shot["name"]
    jpg = bmp.with_suffix(".jpg")
    if conn.execute("select 1 from shots where name = ?", (jpg.name,)).fetchone():
        print(f"skip {shot['game']}/{shot['name']}: {jpg.name} is already a shot")
        return
    jpg.write_bytes(to_jpeg(Image.open(bmp)))
    conn.execute("update shots set name = ? where id = ?", (jpg.name, shot["id"]))
    conn.commit()
    backup = BACKUP / shot["game"]
    backup.mkdir(parents=True, exist_ok=True)
    bmp.rename(backup / bmp.name)
    print(f"shot {shot['id']}: {shot['game']}/{jpg.name} ({jpg.stat().st_size // 1024} KB)")


def main() -> None:
    with db.connect() as conn:
        shots = conn.execute("select id, game, name from shots where name like '%.bmp'").fetchall()
        for shot in shots:
            convert(conn, shot)
    print(f"{len(shots)} BMP shots done")


if __name__ == "__main__":
    main()
