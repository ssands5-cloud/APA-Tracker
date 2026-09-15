"""Player vs Player: a focused head-to-head comparison between two specific
real players.

Real data only, reusing the pre-existing, already-validated Head-to-Head
Advantage Engine (``analytics.head_to_head``) directly -- no new blending,
no new heuristic, no second scoring layer. ``next_match_projection`` is
literally ``analytics.head_to_head.win_probability`` restated under a
name this view's UI uses; it is not a different computation.

Input rows come from ``database.queries.head_to_head_history(db, player_id,
opponent_id)`` -- the real, pre-existing, already-shipped query for exactly
this shape (every game between two specific players, chronological, oldest
first). There is no ``game_results`` table in this project's schema; the
real per-game table is ``PlayerHeadToHead`` (see database/models.py). This
module does not query the database itself, matching every other analytics
module in this project: it takes already-fetched real rows and computes.

What this deliberately does not include
----------------------------------------
Two fields an earlier ask for this feature wanted are not real data in this
project, for the same reason ``docs/matchups.md`` already documents for the
Head-to-Head/Matchup views this module is built on top of:

- **Innings** has never appeared in any query APA's API returns to this
  project (checked every captured operation in ``parser/apa_graphql.py``).
  Not a real captured field. No ``avg_innings``/volatility-of-innings
  metric is computed here -- there is nothing real to compute it from.
- **Defensive shot average** exists only as a lifetime, career-wide number
  (``PlayerCareerStats.defensive_shot_avg``) -- never per-opponent. There
  is no real per-pairing defensive-shot figure to report.

A third gap, found while building this module rather than inherited from
prior documentation: **break/run events are captured per MATCH, not per
opponent** (``PlayerMatch.eight_on_break``/``eight_break_and_run``/
``nine_on_snap``/``nine_break_and_run``). A single match can include games
against more than one opponent (see ``PlayerHeadToHead``'s own docstring:
one real match had one player facing two different opponents), so a
match-level break/run count cannot be honestly attributed to one specific
pairing. No ``break_run_rate`` is computed here.

No placeholder, proxy, estimate, synthetic value, or fabricated substitute
is used for any of the three.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from analytics.head_to_head import (
    average_skill_level_delta,
    skill_level_trend,
    skill_only_win_probability,
    win_loss,
    win_probability,
)
from analytics.matchups import recognized_results, reliability_weight
from database.models import PlayerHeadToHead

DEFAULT_RECENT_GAMES = 5


@dataclass(frozen=True)
class GameRecord:
    """One real game between the two players, for a sortable table.

    ``match_date`` is optional and supplied by the caller (see
    ``summarize``'s ``match_dates`` parameter) -- ``PlayerHeadToHead`` has
    no ORM relationship back to ``Match``, so resolving a real date is the
    query layer's job, not this pure module's. Rows are already in real
    chronological order (oldest first) by construction (the caller's
    ``rows`` input); ``match_date`` is display-only context, never used
    here to re-sort or recompute anything.
    """

    match_id: int
    match_date: Optional[str]
    result: Optional[str]
    own_skill_level: Optional[int]
    opponent_skill_level: Optional[int]
    points_earned: Optional[float]
    nine_ball_points: Optional[int]
    format: Optional[str]
    session_name: Optional[str]


@dataclass(frozen=True)
class PlayerVsPlayerSummary:
    """Every real, already-validated number this project has for one
    specific (player, opponent) pairing."""

    player_id: str
    opponent_id: str
    total_games: int
    wins: int
    losses: int
    sl_delta: Optional[float]
    reliability: float
    modeled_win_probability: Optional[float]
    skill_only_probability: Optional[float]
    trend: str
    recent_trend: str
    next_match_projection: Optional[float]
    games: tuple[GameRecord, ...]


def _game_record(row: PlayerHeadToHead, match_date: Optional[str]) -> GameRecord:
    return GameRecord(
        match_id=row.match_id,
        match_date=match_date,
        result=row.result,
        own_skill_level=row.own_skill_level,
        opponent_skill_level=row.opponent_skill_level,
        points_earned=row.points_earned,
        nine_ball_points=row.nine_ball_points,
        format=row.format,
        session_name=row.session_name,
    )


def recent_trend(rows: Sequence[PlayerHeadToHead], k: int = DEFAULT_RECENT_GAMES) -> str:
    """"up"/"down"/"stable"/"no data" from the player's own skill level
    across only the last ``k`` games -- the same first-vs-last rule
    ``analytics.head_to_head.skill_level_trend`` already uses over the
    whole history, scoped to a recent window so a long-past shift doesn't
    hide (or masquerade as) a real recent one. Not a new trend
    calculation: a direct reuse of the existing function on a shorter
    slice."""
    return skill_level_trend(list(rows)[-k:])


def summarize(
    rows: Sequence[PlayerHeadToHead],
    player_id: str,
    opponent_id: str,
    *,
    recent_games: int = DEFAULT_RECENT_GAMES,
    match_dates: Optional[dict[int, str]] = None,
) -> PlayerVsPlayerSummary:
    """Every real, already-validated number for one (player, opponent) pair.

    ``rows`` must already be chronologically ordered (oldest first) -- see
    ``database.queries.head_to_head_history``, the real query this is built
    to consume. An empty ``rows`` is a real, valid input (two players who
    have never played) and produces an honest all-``None``/zero summary,
    never a fabricated one.

    ``skill_only_probability`` is the ablation term alone
    (``analytics.head_to_head.skill_only_win_probability``), evaluated on
    the most recently POSTED skill levels from the last real game between
    them -- the only real "current skill" signal this pairing's own rows
    carry. It is shown alongside ``modeled_win_probability`` (the full,
    history-plus-skill estimate) as separate, transparently-labeled
    context, never blended into one number.

    ``next_match_projection`` is exactly ``modeled_win_probability`` --
    the same real value under the name this view's UI uses for a forward-
    looking read. No second computation.
    """
    rows = list(rows)
    match_dates = match_dates or {}
    wins, losses = win_loss(rows)
    recognized = recognized_results(rows)
    modeled = win_probability(rows)
    last_row = rows[-1] if rows else None
    skill_only = (
        skill_only_win_probability(last_row.own_skill_level, last_row.opponent_skill_level)
        if last_row is not None
        else None
    )

    return PlayerVsPlayerSummary(
        player_id=player_id,
        opponent_id=opponent_id,
        total_games=len(recognized),
        wins=wins,
        losses=losses,
        sl_delta=average_skill_level_delta(rows),
        reliability=reliability_weight(len(recognized)),
        modeled_win_probability=modeled,
        skill_only_probability=skill_only,
        trend=skill_level_trend(rows),
        recent_trend=recent_trend(rows, recent_games),
        next_match_projection=modeled,
        games=tuple(_game_record(r, match_dates.get(r.match_id)) for r in rows),
    )
