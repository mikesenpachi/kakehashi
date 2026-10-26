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
GAMES_PER_PAGE = 10


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


def board_view(shots: list[sqlite3.Row], today: date, year: int | None = None, page: int = 1) -> str:
    """Return the /stats page body: number tiles, the heatmap of one year, and one page of the games table.

    `year` is the heatmap year (default: this year). `page` is the games table page, from 1.
    """
    if not shots:
        return '<div class="shot-head"><h1>Stats</h1></div><p class="none">No shots yet.</p>'
    year = year or today.year
    days = per_day(shots)
    in_year = sum(count for day, count in days.items() if day.year == year)
    return (
        '<div class="shot-head"><h1>Stats</h1></div>'
        f"{tiles(numbers(shots, today))}"
        f'<div class="card board-card"><div class="text-head"><h2>Characters per day</h2>'
        f'<span class="hint">{in_year:,} in {year}</span>{year_links(years(days, today), year, page)}</div>'
        f"{heatmap(days, today, year)}</div>"
        '<div class="card board-card"><div class="text-head"><h2>Games</h2></div>'
        f"{games_table(games(shots), page, year)}</div>"
        f"<script>{TOOLTIP}</script>"
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


def years(days: dict[date, int], today: date) -> list[int]:
    """Return the years with shots and this year, newest first."""
    return sorted({day.year for day in days} | {today.year}, reverse=True)


def year_links(choices: list[int], year: int, page: int) -> str:
    """Return one link per year; the shown year is marked. The games page stays the same."""
    links = "".join(
        f'<a href="?year={choice}&amp;page={page}"{" class=active" if choice == year else ""}>{choice}</a>'
        for choice in choices
    )
    return f'<nav class="years push" aria-label="Year">{links}</nav>'


def level(count: int, most: int) -> int:
    """Return the shade of a day, 0 (no characters) to 4 (the most characters of a day)."""
    return 0 if count == 0 else max(1, -(-4 * count // most))


def heatmap(days: dict[date, int], today: date, year: int) -> str:
    """Return one square per day of the year, a column per week (Monday on top), darker for more characters.

    Shades compare with the best day of that year. A month name is above the week of its 1st day.
    Days outside the year are blank; days after today are outlines. The tooltip (TOOLTIP) reads data-day and data-count.
    """
    start = date(year, 1, 1) - timedelta(days=date(year, 1, 1).weekday())
    weeks = (date(year, 12, 31) - start).days // 7 + 1
    most = max((count for day, count in days.items() if day.year == year), default=0) or 1
    months, cells = [], []
    for week in range(weeks):
        week_days = [start + timedelta(weeks=week, days=offset) for offset in range(7)]
        first = next((day for day in week_days if day.day == 1 and day.year == year), None)
        months.append(f"<span>{first:%b}</span>" if first else "<span></span>")
        for day in week_days:
            if day.year != year or day > today:
                cells.append(f'<span class="{"blank" if day.year != year else "later"}"></span>')
                continue
            count = days.get(day, 0)
            cells.append(f'<span class="l{level(count, most)}" data-day="{day:%Y-%m-%d}" data-count="{count:,}"></span>')
    legend = "".join(f'<span class="l{shade}"></span>' for shade in range(5))
    return (
        f'<div class="heatmap" style="--weeks: {weeks}" role="img" aria-label="Characters read per day in {year}">'
        f'<div class="months">{"".join(months)}</div><div class="days">{"".join(cells)}</div></div>'
        f'<div class="heat-legend">Less {legend} More</div><div id="heat-tip" class="heat-tip" hidden></div>'
    )


# Shows the date and the characters of the heatmap square under the pointer, at once, above the square.
# Fixed position, so the scroll box of the heatmap does not cut it.
TOOLTIP = """
const tip = document.getElementById("heat-tip");
const squares = document.querySelector(".heatmap .days");
squares.addEventListener("mouseover", (event) => {
  const day = event.target.dataset.day;
  if (!day) { tip.hidden = true; return; }
  tip.textContent = `${day}: ${event.target.dataset.count} characters`;
  tip.hidden = false;
  const square = event.target.getBoundingClientRect();
  tip.style.left = `${square.left + square.width / 2 - tip.offsetWidth / 2}px`;
  tip.style.top = `${square.top - tip.offsetHeight - 6}px`;
});
squares.addEventListener("mouseleave", () => (tip.hidden = true));
"""


def games_table(rows: list[dict], page: int, year: int) -> str:
    """Return one page of the games table (GAMES_PER_PAGE rows, most characters first), with page links."""
    pages_count = max(1, -(-len(rows) // GAMES_PER_PAGE))
    page = min(max(page, 1), pages_count)
    first = (page - 1) * GAMES_PER_PAGE
    shown = rows[first : first + GAMES_PER_PAGE]
    body = "".join(
        f'<tr><td>{escape(row["name"])}<span class="platform">{row["platform"]}</span></td>'
        f'<td>{row["characters"]:,}</td><td>{row["shots"]:,}</td><td>{len(row["days"])}</td>'
        f'<td>{row["first"]:%Y-%m-%d}</td><td>{row["last"]:%Y-%m-%d}</td><td>{row["translate_rate"]:.0%}</td></tr>'
        for row in shown
    )
    return (
        '<div class="table-wrap"><table class="games-table"><thead><tr><th>Game</th><th>Characters</th><th>Shots</th>'
        f"<th>Days</th><th>First</th><th>Last</th><th>Translated</th></tr></thead><tbody>{body}</tbody></table></div>"
        f"{pager(page, pages_count, first + 1, first + len(shown), len(rows), year)}"
    )


def pager(page: int, pages_count: int, first: int, last: int, total: int, year: int) -> str:
    """Return "1-10 of 23 games" with Previous and Next links, or only the count when all fit on one page."""
    count = f'<span class="hint">{first}-{last} of {total} games</span>'
    if pages_count == 1:
        return f'<div class="pager">{count}</div>'

    def link(target: int, text: str) -> str:
        if 1 <= target <= pages_count:
            return f'<a href="?year={year}&amp;page={target}">{text}</a>'
        return f'<span class="off">{text}</span>'

    return f'<div class="pager">{count}{link(page - 1, "Previous")}{link(page + 1, "Next")}</div>'
