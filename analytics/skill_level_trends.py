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
    """P2 volatility normalization, for analytics.matchup_builder ONLY --
    NOT a replacement for skill_level_volatility() above, which still
    backs the separate, unrelated per-player Skill Level History summary
    (ui/export_json.py's _skill_level_summaries): that one's "how volatile
    has this player been all season" question is different from this
    one's "how volatile has this player been RECENTLY", and changing the
    shared function would have silently changed that other feature too --
    out of P2's stated scope (the Matchup Advantage Engine specifically).

    Returns a RATE in [0.0, 1.0], not a count:

        volatility = changes / valid_transitions
        valid_transitions = window_length - 1

    where `window_length` is how many readings are actually present in the
    window, not the nominal `window` size. That distinction is the whole
    point: a player who changed twice across three readings was unsettled
    on every single opportunity (2/2 = 1.0), while a player who changed
    twice across five readings held steady more often than not (2/4 =
    0.5). The old implementation counted both as a flat 2 and could not
    tell them apart.

    Readings without a skill level are excluded from BOTH sides of the
    ratio -- skill_level_changes already skips them, so counting them in
    the denominator would silently understate a real rate.

    A rate needs no cap: it is bounded at 1.0 by construction, so the
    earlier `cap` parameter is gone. `matches` must already be in
    chronological order (same requirement as skill_level_changes) and
    should already be scoped to one (player, format, session) group by the
    caller (P1-4) -- "recent" here means recent WITHIN that group.

    0.0 for fewer than two readings: one reading (or none) offers no
    opportunity to change, which is an absence of evidence, not evidence
    of stability.
    """
    recent = matches[-window:] if window else matches
    readings = [m for m in recent if m.skill_level is not None]
    valid_transitions = len(readings) - 1
    if valid_transitions <= 0:
        return 0.0
    return len(skill_level_changes(readings)) / valid_transitions
