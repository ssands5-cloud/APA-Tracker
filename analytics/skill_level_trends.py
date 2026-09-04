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
    WHOLE history -- see windowed_volatility() below for the Matchup
    Advantage Engine's own, deliberately different, normalized version.
    """
    return len(skill_level_changes(matches))


def windowed_volatility(matches: list[PlayerMatch], window: int = 5, cap: int = 3) -> int:
    """P2 volatility normalization, for analytics.matchup_builder ONLY --
    NOT a replacement for skill_level_volatility() above, which still
    backs the separate, unrelated per-player Skill Level History summary
    (ui/export_json.py's _skill_level_summaries): that one's "how volatile
    has this player been all season" question is different from this
    one's "how volatile has this player been RECENTLY", and changing the
    shared function would have silently changed that other feature too --
    out of P2's stated scope (the Matchup Advantage Engine specifically).

    Counts skill-level changes among only the last `window` readings
    (default 5) -- not the player's whole history -- then caps the result
    at `cap` (default 3) so one wildly bouncing stretch doesn't dominate
    matchup_score/confidence_score any more than a few real changes would.
    `matches` must already be in chronological order (same requirement as
    skill_level_changes) and should already be scoped to one (player,
    format, session) group by the caller (P1-4) -- "recent" here means
    recent WITHIN that group, not recent overall.
    """
    recent = matches[-window:] if window else matches
    return min(len(skill_level_changes(recent)), cap)
