"""
Skill level trend analytics, derived from PlayerMatch.skill_level readings
across a season (database.queries.skill_level_history).

These operate on a plain, already-chronological list of PlayerMatch rows for
ONE player -- the same shape database.queries.skill_level_history returns,
grouped by player -- rather than querying the database directly, so they're
testable against fixture PlayerMatch rows and reusable from any caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from database.models import PlayerMatch


@dataclass
class SkillLevelChange:
    from_level: int
    to_level: int
    match_date: Optional[str]
    week: Optional[int]


def skill_level_changes(matches: list[PlayerMatch]) -> list[SkillLevelChange]:
    """Every point where skill_level differs from the previous reading, in
    order. `matches` must already be in chronological order (as
    database.queries.skill_level_history returns them) -- this doesn't
    re-sort, so a caller passing an unordered list gets unordered nonsense.
    Readings with no skill_level are skipped, not treated as a change.
    """
    changes = []
    previous = None
    for m in matches:
        if m.skill_level is None:
            continue
        if previous is not None and m.skill_level != previous.skill_level:
            changes.append(
                SkillLevelChange(
                    from_level=previous.skill_level,
                    to_level=m.skill_level,
                    match_date=m.match_date,
                    week=m.match.week if m.match else None,
                )
            )
        previous = m
    return changes


def skill_level_trend(matches: list[PlayerMatch]) -> str:
    """"up" / "down" / "stable" / "no data", comparing the first and last
    skill_level reading -- not the min/max, so a level that dipped and
    recovered still reads "stable", matching what the player actually ended
    the season at.
    """
    readings = [m.skill_level for m in matches if m.skill_level is not None]
    if not readings:
        return "no data"
    if readings[-1] > readings[0]:
        return "up"
    if readings[-1] < readings[0]:
        return "down"
    return "stable"


def skill_level_volatility(matches: list[PlayerMatch]) -> int:
    """Count of week-to-week changes -- not a statistical variance, just how
    many times the level actually moved. 0 for a player with one reading, or
    with several readings that never changed.
    """
    return len(skill_level_changes(matches))
