"""Player vs Player Matrix: a whole-scope, multi-opponent export document.

Combines two already-real, already-separate sources for one
(team, opponent, format, session) scope -- never a third, new computation:

    analytics.pairing_evidence.PairingEvidenceMatrix   Stage 1's own
        evidence label, distinct authoritative-match count, and observed
        win rate for every feasible pairing in the scope.

    analytics.player_vs_player.summarize                 the real,
        chronological per-pair game history and its already-validated
        probabilities/trends, for the SAME exact (player, opponent) pair.

This module is the "application adapter" docs/player_vs_player_exports.md
describes: it does not modify, duplicate, or extend either source. It is
purely computational, like every other analytics module in this project --
callers supply the already-fetched matrix and the already-fetched
head-to-head histories; this module never queries the database itself.

Explicit scope split from analytics/player_vs_player.py: that module
answers "everything real we know about ONE specific pairing." This module
answers "here is that same real information for EVERY feasible pairing in
one scope, in one stable order, ready to export." Neither file imports the
other's private internals; the only shared surface is
analytics.player_vs_player.summarize's own public API.

What this deliberately does not include
----------------------------------------
Identical to analytics/player_vs_player.py, restated here because an export
row must carry the disclosure explicitly rather than relying on a reader to
already know it: no innings, no per-opponent defensive-shot average, and no
per-opponent break/run rate. See that module's docstring for the real,
sourced reason for each. This module also does not blend
`observed_win_rate`, `reliability`, `skill_only_probability`, and
`modeled_win_probability` into any new score -- each is carried through
untouched, separately labeled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from analytics.pairing_evidence import EvidenceLabel, PairingEvidenceMatrix
from analytics.player_vs_player import PlayerVsPlayerSummary, summarize
from database.models import PlayerHeadToHead

# Real, fixed disclosure text for fields this project cannot honestly
# produce at any grain finer than what analytics/player_vs_player.py
# already documents. Identical across every row -- these are gaps in what
# APA's captured data contains, not something that varies pairing to
# pairing.
UNAVAILABLE_FIELDS = (
    "innings (not captured by APA's API at any grain)",
    "defensive_shot_avg (career-wide lifetime figure only, never per-opponent)",
    "break_run_rate (captured per match, not per opponent; a match can "
    "include games against more than one opponent)",
    "volatility (not produced by analytics.player_vs_player; "
    "player_trends.volatility is a separate, differently-scoped signal, "
    "not joined here)",
)

# 8-ball before 9-ball before anything else, per the export's structural
# ordering rule -- never score-driven.
_FORMAT_ORDER = {"8-ball": 0, "9-ball": 1}


def _format_rank(format_name: Optional[str]) -> tuple[int, str]:
    normalized = (format_name or "").strip().lower()
    if normalized.startswith("8"):
        return (_FORMAT_ORDER["8-ball"], normalized)
    if normalized.startswith("9"):
        return (_FORMAT_ORDER["9-ball"], normalized)
    return (len(_FORMAT_ORDER), normalized)


@dataclass(frozen=True)
class PlayerVsPlayerExportRow:
    """One real, fully-identified pairing, ready for an export renderer.

    Every field here is either copied unchanged from Stage 1's
    ``PairingEvidenceMatrix`` (evidence identity/label/DIRECT count/observed
    rate) or from ``analytics.player_vs_player.summarize`` (the pair's own
    chronological history and probabilities) -- nothing here is computed
    fresh. ``direct_matches`` (Stage 1's distinct authoritative-match count)
    and ``summary.total_games`` (recognized exact-pair game rows) are
    intentionally separate fields: one real team match can contain more
    than one legitimate game for the same two players, so the two counts
    are not forced equal.
    """

    our_team_external_id: str
    opponent_team_external_id: str
    format: str
    session_name: str
    player_id: int
    player_external_id: str
    player_name: str
    player_skill_level: Optional[int]
    opponent_id: int
    opponent_external_id: str
    opponent_name: str
    opponent_skill_level: Optional[int]
    evidence_label: EvidenceLabel
    direct_matches: int
    observed_win_rate: Optional[float]
    summary: PlayerVsPlayerSummary
    unavailable_fields: tuple[str, ...] = UNAVAILABLE_FIELDS


def _sort_key(row: PlayerVsPlayerExportRow) -> tuple:
    return (
        row.session_name.lower(),
        _format_rank(row.format),
        row.player_name.lower(),
        row.player_external_id,
        row.opponent_name.lower(),
        row.opponent_external_id,
    )


def build_matrix_export(
    matrix: PairingEvidenceMatrix,
    histories: Mapping[tuple[int, int], Sequence[PlayerHeadToHead]],
    *,
    recent_games: int = 5,
    match_dates: Optional[Mapping[int, str]] = None,
) -> tuple[PlayerVsPlayerExportRow, ...]:
    """Every feasible pairing in ``matrix``, combined with its own real
    per-pair game history, in the export's stable structural order.

    ``histories`` maps ``(player_id, opponent_id)`` to that exact pair's
    real ``PlayerHeadToHead`` rows (chronological, oldest first -- see
    ``database.queries.head_to_head_history``, the real query that
    produces this shape). A pairing absent from ``histories`` is treated
    as having no real game history -- ``analytics.player_vs_player.summarize``
    then produces an honest all-``None``/zero summary, never a guess. This
    is the normal, expected shape for an INDIRECT or UNKNOWN pairing.

    Every pairing in ``matrix.pairings`` appears exactly once here,
    DIRECT/INDIRECT/UNKNOWN alike -- this function does not filter, hide,
    or reorder by evidence label or score. Order is purely structural
    (session, format, player name/id, opponent name/id); a caller wanting
    only DIRECT rows, say, filters this output afterward.
    """
    match_dates = match_dates or {}
    rows = []
    for pairing in matrix.pairings:
        history = histories.get((pairing.player_id, pairing.opponent_id), ())
        summary = summarize(
            history,
            pairing.player_external_id,
            pairing.opponent_external_id,
            recent_games=recent_games,
            match_dates=dict(match_dates),
        )
        rows.append(
            PlayerVsPlayerExportRow(
                our_team_external_id=matrix.our_team_external_id,
                opponent_team_external_id=matrix.opponent_team_external_id,
                format=matrix.format,
                session_name=matrix.session_name,
                player_id=pairing.player_id,
                player_external_id=pairing.player_external_id,
                player_name=pairing.player_name,
                player_skill_level=pairing.player_skill_level,
                opponent_id=pairing.opponent_id,
                opponent_external_id=pairing.opponent_external_id,
                opponent_name=pairing.opponent_name,
                opponent_skill_level=pairing.opponent_skill_level,
                evidence_label=pairing.evidence_label,
                direct_matches=pairing.direct_evidence_count,
                observed_win_rate=pairing.observed_win_rate,
                summary=summary,
            )
        )
    return tuple(sorted(rows, key=_sort_key))


def rows_for_player(
    rows: Sequence[PlayerVsPlayerExportRow], player_id: int
) -> tuple[PlayerVsPlayerExportRow, ...]:
    """Every real row for one of our players against every identified
    opponent in the scope -- the "multi-opponent comparison" view: one
    player, ranked against the whole field they could face tonight. Still
    the export's stable structural order, not score-sorted."""
    return tuple(row for row in rows if row.player_id == player_id)
