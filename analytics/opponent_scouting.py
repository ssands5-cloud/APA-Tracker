"""Opponent Scouting -- aggregates the real, already-computed per-pairing
signals (player_h2h_advantage's matchup_score/win_probability, and the
opponent's own real player_trends.volatility) by OPPONENT PLAYER, so a
captain can see, before a match, which specific opponents are dangerous
and why.

Purely derived and purely computational, the same split every other
analytics module in this project uses: this module takes already-fetched
real rows as input and queries nothing itself.
scripts/build_lineups.py builds the real inputs (it already fetches both
`pairings` and `trends` for the Lineup Optimizer) and calls
summarize_opponents; apa_config.yaml's own `opponent_scouting` section
supplies real, overridable danger thresholds via
scripts.build_lineups.load_opponent_scouting_thresholds_from_config.

Every input is real:

    matchup_score / win_probability -> player_h2h_advantage, the same
                                        real rows analytics.lineup_optimizer
                                        already reads (see docs/lineup_optimizer.md)
    opponent_volatility             -> player_trends.volatility for the
                                        OPPONENT's own alias -- the same
                                        real signal analytics.win_probability
                                        already reads for the PLAYER side
                                        (see docs/win_probability.md);
                                        player_trends carries no notion of
                                        "mine" vs "theirs", so the same
                                        real table answers this too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from analytics.player_trends import normalize_format

# Real, overridable "this opponent is dangerous" cutoffs -- see
# docs/opponent_scouting.md. Not claimed as empirically fit: there is no
# historical "which opponent actually upset us" record to check them
# against, the same real gap docs/lineup_optimizer.md and
# docs/lineup_risk.md each already document for their own thresholds.
WIN_PROBABILITY_DANGER_THRESHOLD = 0.40
VOLATILITY_DANGER_THRESHOLD = 0.50


@dataclass(frozen=True)
class OpponentScoutingThresholds:
    win_probability_danger: float = WIN_PROBABILITY_DANGER_THRESHOLD
    volatility_danger: float = VOLATILITY_DANGER_THRESHOLD


DEFAULT_OPPONENT_SCOUTING_THRESHOLDS = OpponentScoutingThresholds()


@dataclass(frozen=True)
class OpponentScoutingEntry:
    """One real opponent player's real, aggregated scouting profile."""

    opponent_id: str
    opponent_name: str
    opponent_team_id: Optional[str]
    opponent_team_name: Optional[str]
    times_faced: int
    avg_matchup_score: Optional[float]
    avg_win_probability: Optional[float]
    opponent_volatility: Optional[float]
    is_danger_matchup: bool
    danger_reasons: list[str]


def _mean(values: list[float]) -> Optional[float]:
    return round(sum(values) / len(values), 6) if values else None


def summarize_opponent(
    rows: list[dict[str, Any]],
    opponent_volatility: Optional[float],
    thresholds: OpponentScoutingThresholds = DEFAULT_OPPONENT_SCOUTING_THRESHOLDS,
) -> OpponentScoutingEntry:
    """Aggregate every real pairing row against ONE opponent player into
    their real scouting profile.

    `rows` must all share the same opponent -- one call per opponent,
    same convention analytics.lineup_optimizer.solve_lineup_assignment's
    callers already use for grouping by team/format/session. A missing
    matchup_score/win_probability on an individual row is simply excluded
    from that row's contribution to the average, never treated as 0 or a
    guessed value; an opponent with zero usable rows for a given signal
    gets None for it, not a fabricated average.

    Raises ValueError for an empty `rows` -- there is no real opponent
    identity to report on at all, a real caller error (summarize_opponents
    never constructs a group this way) rather than a silent, confusing
    IndexError.
    """
    if not rows:
        raise ValueError("summarize_opponent requires at least one real pairing row")
    first = rows[0]
    matchup_scores = [
        float(row["matchup_score"]) for row in rows if row.get("matchup_score") is not None
    ]
    win_probabilities = [
        float(row["win_probability"]) for row in rows if row.get("win_probability") is not None
    ]
    avg_matchup_score = _mean(matchup_scores)
    avg_win_probability = _mean(win_probabilities)

    reasons: list[str] = []
    if avg_win_probability is not None and avg_win_probability < thresholds.win_probability_danger:
        reasons.append(
            f"our average win probability against them ({avg_win_probability:.0%}) is below "
            f"the {thresholds.win_probability_danger:.0%} threshold"
        )
    if opponent_volatility is not None and opponent_volatility >= thresholds.volatility_danger:
        reasons.append(f"their own volatility ({opponent_volatility:.2f}) is elevated")

    return OpponentScoutingEntry(
        opponent_id=str(first["opponent_id"]),
        opponent_name=first.get("opponent_name") or "",
        opponent_team_id=(
            str(first["opponent_team_pk"]) if first.get("opponent_team_pk") is not None else None
        ),
        opponent_team_name=first.get("opponent_team_name"),
        times_faced=len(rows),
        avg_matchup_score=avg_matchup_score,
        avg_win_probability=avg_win_probability,
        opponent_volatility=opponent_volatility,
        is_danger_matchup=bool(reasons),
        danger_reasons=reasons,
    )


def summarize_opponents(
    pairing_rows: list[dict[str, Any]],
    trends: dict[tuple[int, Optional[str], Optional[str]], dict[str, Any]],
    thresholds: OpponentScoutingThresholds = DEFAULT_OPPONENT_SCOUTING_THRESHOLDS,
) -> list[OpponentScoutingEntry]:
    """Group every real pairing row by real opponent and summarize each.

    `trends` is exactly scripts.build_lineups.fetch_trends's own return
    value -- (player_pk, normalized_format, session_name) -> trend record
    -- the same real dict already built for the "my player" side of every
    other lookup in this pipeline. An opponent's OWN volatility reading is
    looked up in the SAME real (format, session) context each pairing row
    carries, not an arbitrary cross-context value. Within one opponent's
    group of rows, the first row with a real match wins -- the group is
    almost always one real (format, session) context already (rows come
    from one team pairing), mirroring analytics.lineup_optimizer's own
    "first real signal found" convention for a per-player value spread
    across a matrix. Absent entirely when no row resolves to a real
    reading -- never a guessed one.

    Sorted by opponent team, then opponent name, for deterministic output.
    """
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in pairing_rows:
        grouped.setdefault(row["opponent_pk"], []).append(row)

    entries = []
    for opponent_pk, rows in grouped.items():
        volatility = None
        for row in rows:
            key = (opponent_pk, normalize_format(row.get("format")), row.get("session_name"))
            trend = trends.get(key)
            if trend is not None and trend.get("volatility") is not None:
                volatility = trend["volatility"]
                break
        entries.append(summarize_opponent(rows, volatility, thresholds))

    entries.sort(key=lambda entry: (
        entry.opponent_team_name or "", entry.opponent_name or "",
    ))
    return entries
