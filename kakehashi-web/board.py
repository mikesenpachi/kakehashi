"""Stats board: reading numbers from the shots, and the HTML of the /stats page.

Characters are Japanese characters only (kana and kanji), so menu words like "SAFETY" do not count.
A day is the date of `taken`, the capture time.
"""

import re
import sqlite3
from datetime import date, timedelta
from html import escape

import pages

JAPANESE = re.compile(r"[぀-ヿ㐀-䶿一-鿿々]")
HEATMAP_WEEKS = (13, 53)  # the heatmap shows at least 13 weeks, at most 53


def characters(text: str | None) -> int:
    """Return the number of Japanese characters in a text."""
    return len(JAPANESE.findall(text or ""))


def per_day(shots: list[sqlite3.Row]) -> dict[date, int]:
    """Return the characters read on each day that has shots."""
    days: dict[date, int] = {}
    for shot in shots:
        day = date.fromisoformat(shot["taken"][:10])
        days[day] = days.get(day, 0) + characters(shot["text"])
    return days


def current_streak(days: set[date], today: date) -> int:
    """Return the number of days in a row with shots, up to today.

    A streak that ends yesterday still counts: today is not over yet.
    """
    day = today if today in days else today - timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def longest_streak(days: set[date]) -> int:
    """Return the most days in a row with shots."""
    longest = 0
    for day in days:
        if day - timedelta(days=1) in days:
            continue
        length = 1
        while day + timedelta(days=length) in days:
            length += 1
        longest = max(longest, length)
    return longest


def translated(shot: sqlite3.Row) -> bool:
    """Return True when the shot has a translation."""
    return bool(shot["translation"])


def games(shots: list[sqlite3.Row]) -> list[dict]:
    """Return one row per game, most characters first: name, platform, shots, characters,
    days played, first and last day, and the share of shots translated."""
    rows: dict[str, dict] = {}
    for shot in shots:
        row = rows.setdefault(shot["game"], {
            "name": shot["game_name"], "platform": pages.platform(shot["game"]),
            "shots": 0, "characters": 0, "translated": 0, "days": set(),
        })
        row["shots"] += 1
        row["characters"] += characters(shot["text"])
        row["translated"] += translated(shot)
        row["days"].add(date.fromisoformat(shot["taken"][:10]))
    for row in rows.values():
        row["first"], row["last"] = min(row["days"]), max(row["days"])
        row["translate_rate"] = row["translated"] / row["shots"]
    return sorted(rows.values(), key=lambda row: row["characters"], reverse=True)


def numbers(shots: list[sqlite3.Row], today: date) -> dict:
    """Return the numbers for the tiles at the top of the board."""
    days = per_day(shots)
    week = sum(count for day, count in days.items() if today - day < timedelta(days=7))
    total = sum(days.values())
    return {
        "today": days.get(today, 0),
        "week": week,
        "total": total,
        "days": len(days),
        "average": round(total / len(days)) if days else 0,
        "streak": current_streak(set(days), today),
        "longest": longest_streak(set(days)),
        "translate_rate": sum(map(translated, shots)) / len(shots) if shots else 0,
    }


def board_view(shots: list[sqlite3.Row], today: date) -> str:
    """Return the /stats page body: number tiles, the heatmap of characters per day, and the games table."""
    if not shots:
        return '<div class="shot-head"><h1>Stats</h1></div><p class="none">No shots yet.</p>'
    return (
        '<div class="shot-head"><h1>Stats</h1></div>'
        f"{tiles(numbers(shots, today))}"
        '<div class="card board-card"><div class="text-head"><h2>Characters per day</h2></div>'
        f"{heatmap(per_day(shots), today)}</div>"
        '<div class="card board-card"><div class="text-head"><h2>Games</h2></div>'
        f"{games_table(games(shots))}</div>"
    )


def tiles(values: dict) -> str:
    """Return the number tiles: characters today, this week and in total, the streak and the translate rate."""
    def tile(value: str, text: str) -> str:
        return f"<div><b>{value}</b><span>{text}</span></div>"

    return (
        '<div class="stats">'
        + tile(f"{values['today']:,}", "characters today")
        + tile(f"{values['week']:,}", "characters in the last 7 days")
        + tile(f"{values['total']:,}", f"characters in {values['days']} days ({values['average']:,} per day)")
        + tile(f"{values['streak']} {'day' if values['streak'] == 1 else 'days'}", f"streak (longest {values['longest']})")
        + tile(f"{values['translate_rate']:.0%}", "of shots translated")
        + "</div>"
    )


def heatmap_start(days: dict[date, int], today: date) -> date:
    """Return the Monday of the first heatmap week: the week of the first shot, within HEATMAP_WEEKS."""
    least, most = HEATMAP_WEEKS
    monday = today - timedelta(days=today.weekday())
    weeks = (monday - min(days)).days // 7 + 1
    return monday - timedelta(weeks=min(max(weeks, least), most) - 1)


def level(count: int, most: int) -> int:
    """Return the shade of a day, 0 (no characters) to 4 (the most characters of a day)."""
    return 0 if count == 0 else max(1, -(-4 * count // most))


def heatmap(days: dict[date, int], today: date) -> str:
    """Return one square per day, a column per week (Monday on top), darker for more characters.

    Each square has a tooltip with the date and the characters. A month name is above its first week.
    """
    start = heatmap_start(days, today)
    most = max(days.values()) or 1
    weeks = (today - start).days // 7 + 1
    months, cells = [], []
    for week in range(weeks):
        monday = start + timedelta(weeks=week)
        new_month = week == 0 or monday.month != (monday - timedelta(weeks=1)).month
        months.append(f"<span>{monday:%b}</span>" if new_month else "<span></span>")
        for offset in range(7):
            day = monday + timedelta(days=offset)
            if day > today:
                cells.append('<span class="future"></span>')
                continue
            count = days.get(day, 0)
            tip = f"{day:%a %Y-%m-%d}: {count:,} characters"
            cells.append(f'<span class="l{level(count, most)}" title="{tip}"></span>')
    legend = "".join(f'<span class="l{shade}"></span>' for shade in range(5))
    return (
        f'<div class="heatmap" style="--weeks: {weeks}" role="img" aria-label="Characters read per day">'
        f'<div class="months">{"".join(months)}</div><div class="days">{"".join(cells)}</div></div>'
        f'<div class="heat-legend">Less {legend} More</div>'
    )


def games_table(rows: list[dict]) -> str:
    """Return the games table: one row per game, most characters first."""
    body = "".join(
        f'<tr><td>{escape(row["name"])}<span class="platform">{row["platform"]}</span></td>'
        f'<td>{row["characters"]:,}</td><td>{row["shots"]:,}</td><td>{len(row["days"])}</td>'
        f'<td>{row["first"]:%Y-%m-%d}</td><td>{row["last"]:%Y-%m-%d}</td><td>{row["translate_rate"]:.0%}</td></tr>'
        for row in rows
    )
    return (
        '<div class="table-wrap"><table class="games-table"><thead><tr><th>Game</th><th>Characters</th><th>Shots</th>'
        f"<th>Days</th><th>First</th><th>Last</th><th>Translated</th></tr></thead><tbody>{body}</tbody></table></div>"
    )
