"""SQLite storage for games, shots and their OCR text.

A box is (left, top, right, bottom) as fractions of the image, 0 to 1.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path

# The data folder: images and the database. KAKEHASHI_DATA sets another one (for example a demo).
DATA = Path(os.environ.get("KAKEHASHI_DATA") or Path(__file__).parent / "data")
DB = DATA / "kakehashi.db"

SCHEMA = """
create table if not exists games (
    id text primary key,
    name text not null,
    box_left real,
    box_top real,
    box_right real,
    box_bottom real
);
create table if not exists shots (
    id integer primary key,
    name text unique not null,
    game text not null,
    raw_ocr text,
    text text,
    taken text not null,
    box_used text,
    edited integer not null default 0,
    translation text
);
"""

# Full text search over the text and the translation of each shot. The index reads from
# shots (content='shots'); the triggers keep it in sync with every insert, edit and delete.
# Trigram finds any 3 or more characters, also in Japanese, which has no spaces between words.
SEARCH = """
create virtual table if not exists search using fts5(
    text, translation, content='shots', content_rowid='id', tokenize='trigram'
);
create trigger if not exists search_insert after insert on shots begin
    insert into search (rowid, text, translation) values (new.id, new.text, new.translation);
end;
create trigger if not exists search_delete after delete on shots begin
    insert into search (search, rowid, text, translation) values ('delete', old.id, old.text, old.translation);
end;
create trigger if not exists search_update after update of text, translation on shots begin
    insert into search (search, rowid, text, translation) values ('delete', old.id, old.text, old.translation);
    insert into search (rowid, text, translation) values (new.id, new.text, new.translation);
end;
"""

Box = tuple[float, float, float, float]


def connect() -> sqlite3.Connection:
    """Open the database and create the tables if needed."""
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma journal_mode = wal")  # page reads do not wait for a shot write
    conn.executescript(SCHEMA)
    add_translation_column(conn)
    add_search(conn)
    return conn


def add_search(conn: sqlite3.Connection) -> None:
    """Make the search index and its triggers if needed. A new index is filled from the shots once (2026-10-24)."""
    new = conn.execute("select 1 from sqlite_master where name = 'search'").fetchone() is None
    conn.executescript(SEARCH)
    if new:
        conn.execute("insert into search (search) values ('rebuild')")
        conn.commit()


def add_translation_column(conn: sqlite3.Connection) -> None:
    """Add the translation column to a database made before it existed (2026-10-24)."""
    columns = [row["name"] for row in conn.execute("pragma table_info(shots)")]
    if "translation" not in columns:
        conn.execute("alter table shots add column translation text")


def box_text(box: Box | None) -> str:
    """Return a box as text for the box_used column, or "" for the full screen."""
    return ",".join(f"{value:.3f}" for value in box) if box else ""


def used_box(shot: sqlite3.Row) -> Box | None:
    """Return the box that the text of a shot came from, or None for the full screen."""
    return tuple(float(value) for value in shot["box_used"].split(",")) if shot["box_used"] else None


def add_shot(name: str, game: str, raw_ocr: str, text: str, taken: datetime, box: Box | None) -> int:
    """Insert a shot, add its game if new, and return the shot id."""
    with connect() as conn:
        conn.execute("insert or ignore into games (id, name) values (?, ?)", (game, game))
        cursor = conn.execute(
            "insert into shots (name, game, raw_ocr, text, taken, box_used) values (?, ?, ?, ?, ?, ?)",
            (name, game, raw_ocr, text, taken.isoformat(timespec="seconds"), box_text(box)),
        )
        return cursor.lastrowid


def existing_shot(game: str, name: str) -> int | None:
    """Return the id of a shot with this game and image name, or None."""
    with connect() as conn:
        row = conn.execute("select id from shots where game = ? and name = ?", (game, name)).fetchone()
    return row[0] if row else None


# Shot columns plus game_name, the name of its game (the game id until the user renames it).
SHOTS = "select shots.*, games.name as game_name from shots join games on games.id = shots.game"


def get_shot(shot_id: int) -> sqlite3.Row | None:
    """Return one shot, or None."""
    with connect() as conn:
        return conn.execute(f"{SHOTS} where shots.id = ?", (shot_id,)).fetchone()


def list_shots() -> list[sqlite3.Row]:
    """Return all shots, newest first."""
    with connect() as conn:
        return conn.execute(f"{SHOTS} order by taken desc, shots.id desc").fetchall()


FOUND = 100  # most search results to return


def search(query: str) -> list[sqlite3.Row]:
    """Return the newest FOUND shots whose text or translation contains the query, as Ctrl+F does.

    3 or more characters use the trigram index. Fewer use LIKE, which reads all rows,
    because a trigram index cannot find 1 or 2 characters (Japanese words such as 魔法).
    """
    query = query.strip()
    if not query:
        return []
    order = f"order by taken desc, shots.id desc limit {FOUND}"
    with connect() as conn:
        if len(query) >= 3:
            phrase = '"' + query.replace('"', '""') + '"'
            where = "where shots.id in (select rowid from search where search match ?)"
            return conn.execute(f"{SHOTS} {where} {order}", (phrase,)).fetchall()
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where = "where shots.text like ? escape '\\' or shots.translation like ? escape '\\'"
        return conn.execute(f"{SHOTS} {where} {order}", (pattern, pattern)).fetchall()


def rename_game(game: str, name: str) -> None:
    """Set the name of a game. The sidebar and the shot page show it instead of the game id."""
    with connect() as conn:
        conn.execute("update games set name = ? where id = ?", (name, game))


def set_text(shot_id: int, text: str) -> None:
    """Save a manual edit of the text and mark the shot as edited."""
    with connect() as conn:
        conn.execute("update shots set text = ?, edited = 1 where id = ?", (text, shot_id))


def set_translation(shot_id: int, translation: str) -> None:
    """Save the English translation of a shot's text."""
    with connect() as conn:
        conn.execute("update shots set translation = ? where id = ?", (translation, shot_id))


def set_box_used(shot_id: int, box: Box) -> None:
    """Save the box that the text of a shot came from ("Use for this shot")."""
    with connect() as conn:
        conn.execute("update shots set box_used = ? where id = ?", (box_text(box), shot_id))


def set_box(game: str, box: Box | None) -> None:
    """Save the crop box of a game. None clears it."""
    with connect() as conn:
        conn.execute(
            "update games set box_left = ?, box_top = ?, box_right = ?, box_bottom = ? where id = ?",
            (*(box or (None,) * 4), game),
        )


def clear() -> None:
    """Delete all shots and games. The image files stay on disk."""
    with connect() as conn:
        conn.execute("delete from shots")
        conn.execute("delete from games")


def delete_game(game: str) -> list[str]:
    """Delete a game: its shots, its name and its box. Return the image file names of its shots."""
    with connect() as conn:
        names = [row["name"] for row in conn.execute("select name from shots where game = ?", (game,))]
        conn.execute("delete from shots where game = ?", (game,))
        conn.execute("delete from games where id = ?", (game,))
    return names


def delete_shot(shot_id: int) -> None:
    """Delete one shot."""
    with connect() as conn:
        conn.execute("delete from shots where id = ?", (shot_id,))


def get_box(game: str) -> Box | None:
    """Return the crop box of a game, or None for the full screen."""
    with connect() as conn:
        row = conn.execute(
            "select box_left, box_top, box_right, box_bottom from games where id = ?", (game,)
        ).fetchone()
    return tuple(row) if row and row[0] is not None else None
