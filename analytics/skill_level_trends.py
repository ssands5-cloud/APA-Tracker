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
    with several readings that never changed. Uncapped, over the player's
    WHOLE history -- see normalized_volatility() below for the Matchup
    Advantage Engine's own, deliberately different, normalized RATE.
    """
    return len(skill_level_changes(matches))


def normalized_volatility(matches: list[PlayerMatch], window: int = 5) -> float:
    """Recent skill-level volatility for the Matchup Advantage Engine as a
    rate in ``[0.0, 1.0]`` rather than a raw change count.

    This deliberately stays separate from ``skill_level_volatility()``,
    which backs the whole-history Skill Level summary. Only the last
    ``window`` readings are considered here, and readings whose skill level
    is unknown are excluded from both the numerator and denominator.

    The denominator is the number of real opportunities to change:

        volatility = changes / valid_transitions
        valid_transitions = known_readings - 1

    So two changes across three known readings is 1.0, while two changes
    across five known readings is 0.5. A raw count would report both as 2
    and incorrectly treat them as equally unstable.

    ``matches`` must already be chronological and scoped to one player,
    format, and session by the caller. Fewer than two known readings return
    0.0 because there is no observed transition to score. The rate needs no
    cap because it is bounded by construction.
    """
    recent = matches[-window:] if window else matches
    readings = [m for m in recent if m.skill_level is not None]
    valid_transitions = len(readings) - 1
    if valid_transitions <= 0:
        return 0.0
    return len(skill_level_changes(readings)) / valid_transitions
