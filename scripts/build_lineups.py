"""Build one-to-one lineup recommendations from derived APA analytics.

This is the reporter/builder for :mod:`analytics.lineup_optimizer`.  It reads
the already-computed ``player_h2h_advantage`` and ``player_trends`` tables,
resolves each pairing to an own-team/opponent-team matchup, and writes the
optimizer's whole-lineup assignment to ``exports/lineups.json``.

The database is opened with SQLite's ``mode=ro`` URI.  This script therefore
cannot create tables, migrate the database, or accidentally change the source
rows while producing an export.  Missing evidence stays ``null`` in the
payload; the optimizer's neutral defaults are used only for its internal
objective arithmetic and are never written as observed measurements.

Rows whose team identity cannot be resolved unambiguously are retained in the
raw ``pairings`` list with a resolution status and warning, but are not put
into a lineup.  In particular, an unknown opponent team is never replaced by
an invented "unknown" bucket: doing that would mix unrelated opponents into
one assignment problem.

Usage::

    python scripts/build_lineups.py
    python scripts/build_lineups.py --db path/to/apa.db
    python scripts/build_lineups.py --out-dir exports
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sqlite3
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ``python scripts/build_lineups.py`` is a documented operator command.  In
# that direct-file mode Python puts only ``scripts/`` on sys.path, so the
# sibling ``analytics`` package would otherwise be unimportable.  Module mode
# (``python -m scripts.build_lineups``) already has the project root present;
# this conditional keeps both entry points equivalent without changing the
# import path for callers.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics.captains_edge import confidence as calculate_confidence
from analytics.captains_edge import risk_factor as calculate_risk_factor
from analytics.lineup_optimizer import (
    DEFAULT_WEIGHTS,
    LineupWeights,
    PairingCandidate,
    solve_lineup_assignment,
)
from analytics.lineup_risk import (
    DEFAULT_LINEUP_RISK_WEIGHTS,
    LineupRiskWeights,
    compute_lineup_risk,
)
from analytics.player_trends import normalize_format
from analytics.rationale import (
    DEFAULT_RATIONALE_TOGGLES,
    RationaleToggles,
    lineup_risk_rationale,
)
from analytics.win_probability import (
    DEFAULT_WIN_PROBABILITY_WEIGHTS,
    WinProbabilityWeights,
    compute_win_probability,
)
from analytics.win_probability import sl_delta as compute_sl_delta
from scripts.build_captains_edge import (
    NoDatabaseError,
    PROJECT_ROOT,
    connect_read_only,
    resolve_db_path,
)

logger = logging.getLogger(__name__)

DEFAULT_OUT_DIR = PROJECT_ROOT / "exports"
JSON_NAME = "lineups.json"
SCHEMA_VERSION = 1


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    """Return whether a source table is present without mutating SQLite."""

    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    """Read a table's columns for a graceful response to older databases."""

    try:
        return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
    except sqlite3.Error:
        return set()


def _warn(warnings: list[str], message: str) -> None:
    """Append a warning once, keeping the JSON deterministic and readable."""

    if message not in warnings:
        warnings.append(message)


def fetch_pairing_rows(
    connection: sqlite3.Connection,
    warnings: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Fetch raw H2H pairing rows and roster identity metadata.

    ``player_h2h_advantage.matchup_score`` is stored on a 0..100 scale.  The
    raw value is preserved as ``matchup_score``; ``build_payload`` adds a
    separate normalized ``matchup_score_normalized`` field for the pure
    optimizer, whose contract is 0..1.  No values are filled in here.
    """

    local_warnings = warnings if warnings is not None else []
    required_h2h = {
        "player_id", "opponent_id", "matchup_score", "win_probability",
        "format", "session_name", "expected_points", "expected_balls",
    }
    if not _table_exists(connection, "player_h2h_advantage"):
        _warn(local_warnings, "player_h2h_advantage is unavailable; no pairing rows were read.")
        return []
    if not _table_exists(connection, "players"):
        _warn(local_warnings, "players is unavailable; no pairing rows were read.")
        return []
    if not required_h2h.issubset(_columns(connection, "player_h2h_advantage")):
        _warn(
            local_warnings,
            "player_h2h_advantage has an older/incomplete schema; no pairing rows were read.",
        )
        return []

    if not {"id", "external_id", "name", "team_id"}.issubset(
        _columns(connection, "players")
    ):
        _warn(local_warnings, "players has an older/incomplete schema; no pairing rows were read.")
        return []

    if _table_exists(connection, "teams"):
        team_columns = ", t.name AS team_name, ot.name AS opponent_team_name"
        team_joins = (
            "LEFT JOIN teams t ON t.id = p.team_id "
            "LEFT JOIN teams ot ON ot.id = o.team_id"
        )
    else:
        team_columns = ", NULL AS team_name, NULL AS opponent_team_name"
        team_joins = ""
        _warn(local_warnings, "teams is unavailable; team names will be blank where IDs exist.")

    try:
        rows = connection.execute(
            f"""
            SELECT
                p.id          AS player_pk,
                p.external_id AS player_id,
                p.name        AS player_name,
                p.team_id     AS team_pk,
                p.skill_level AS player_skill_level,
                o.id          AS opponent_pk,
                o.external_id AS opponent_id,
                o.name        AS opponent_name,
                o.team_id     AS opponent_team_pk,
                o.skill_level AS opponent_skill_level
                {team_columns},
                a.matchup_score,
                a.win_probability,
                a.expected_points,
                a.expected_balls,
                a.format,
                a.session_name
            FROM player_h2h_advantage a
            JOIN players p ON p.id = a.player_id
            JOIN players o ON o.id = a.opponent_id
            {team_joins}
            ORDER BY COALESCE(p.name, ''), COALESCE(o.name, ''),
                     COALESCE(a.format, ''), COALESCE(a.session_name, '')
            """
        ).fetchall()
    except sqlite3.Error as exc:
        _warn(local_warnings, f"Could not read player_h2h_advantage: {exc}.")
        return []

    return [dict(row) for row in rows]


def fetch_trends(
    connection: sqlite3.Connection,
    warnings: Optional[list[str]] = None,
) -> dict[tuple[int, Optional[str], Optional[str]], dict[str, Any]]:
    """Fetch trend rows keyed by database player, normalized format, session."""

    local_warnings = warnings if warnings is not None else []
    if not _table_exists(connection, "player_trends"):
        _warn(local_warnings, "player_trends is unavailable; confidence and risk remain null.")
        return {}
    if not _table_exists(connection, "players"):
        _warn(local_warnings, "players is unavailable; player trends cannot be joined.")
        return {}

    required_trends = {
        "player_id", "format", "session_name", "regression_slope", "volatility",
        "sl_stability", "hot_cold_flag",
    }
    if not required_trends.issubset(_columns(connection, "player_trends")):
        _warn(local_warnings, "player_trends has an older/incomplete schema; trends were ignored.")
        return {}

    try:
        rows = connection.execute(
            """
            SELECT p.id AS player_pk, p.external_id AS player_id,
                   t.format, t.session_name, t.regression_slope, t.volatility,
                   t.sl_stability, t.hot_cold_flag
            FROM player_trends t
            JOIN players p ON p.id = t.player_id
            ORDER BY p.id, COALESCE(t.format, ''), COALESCE(t.session_name, '')
            """
        ).fetchall()
    except sqlite3.Error as exc:
        _warn(local_warnings, f"Could not read player_trends: {exc}.")
        return {}

    trends: dict[tuple[int, Optional[str], Optional[str]], dict[str, Any]] = {}
    for row in rows:
        record = dict(row)
        key = (
            record["player_pk"],
            normalize_format(record.get("format")),
            record.get("session_name"),
        )
        # The ORM declares this key unique.  setdefault keeps a malformed old
        # database deterministic without silently averaging unlike rows.
        trends.setdefault(key, record)
    return trends


def fetch_win_rates_by_skill_level(
    connection: sqlite3.Connection,
    warnings: Optional[list[str]] = None,
) -> dict[tuple[int, int], float]:
    """Real WR_SL for analytics.win_probability: for each real player, their
    win rate across every real, decided (W/L) player_head_to_head game
    against an opponent of a given skill level -- grouped by the
    OPPONENT's skill level, not by opponent identity (that's WR_H2H,
    already covered by the existing, real
    player_h2h_advantage.win_probability -- see
    scripts.build_lineups._candidate).

    Keyed by (player_pk, opponent_skill_level) -> win_rate (0..1). A
    (player, skill level) combination with zero decided games is simply
    absent from the returned dict -- callers treat a missing key as "no
    real evidence," never as 0 wins, per docs/win_probability.md.
    """
    local_warnings = warnings if warnings is not None else []
    if not _table_exists(connection, "player_head_to_head"):
        _warn(local_warnings, "player_head_to_head is unavailable; WR_SL remains null.")
        return {}

    required = {"player_id", "opponent_skill_level", "result"}
    if not required.issubset(_columns(connection, "player_head_to_head")):
        _warn(local_warnings, "player_head_to_head has an older/incomplete schema; WR_SL was ignored.")
        return {}

    try:
        rows = connection.execute(
            """
            SELECT player_id AS player_pk, opponent_skill_level,
                   SUM(CASE WHEN result = 'W' THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN result IN ('W', 'L') THEN 1 ELSE 0 END) AS decided
            FROM player_head_to_head
            WHERE opponent_skill_level IS NOT NULL
            GROUP BY player_id, opponent_skill_level
            """
        ).fetchall()
    except sqlite3.Error as exc:
        _warn(local_warnings, f"Could not read player_head_to_head for WR_SL: {exc}.")
        return {}

    win_rates: dict[tuple[int, int], float] = {}
    for row in rows:
        record = dict(row)
        if not record["decided"]:
            continue
        win_rates[(record["player_pk"], record["opponent_skill_level"])] = (
            record["wins"] / record["decided"]
        )
    return win_rates


def _normalized_matchup_score(
    raw: Any,
    warnings: list[str],
    context: str,
) -> Optional[float]:
    """Convert the stored 0..100 score to optimizer's 0..1 scale.

    Invalid values are treated as missing, never clamped into a plausible
    score.  That keeps an upstream data defect visible in the export.
    """

    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        _warn(warnings, f"Invalid matchup_score for {context}; it remains null.")
        return None
    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
        _warn(warnings, f"Invalid matchup_score for {context}; it remains null.")
        return None
    return round(value / 100.0, 6)


def _bounded_probability(
    raw: Any,
    warnings: list[str],
    context: str,
) -> Optional[float]:
    """Validate the H2H probability without turning bad data into evidence."""

    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        _warn(warnings, f"Invalid win_probability for {context}; it remains null.")
        return None
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        _warn(warnings, f"Invalid win_probability for {context}; it remains null.")
        return None
    return round(value, 6)


def _name_team_map(connection: sqlite3.Connection) -> dict[str, set[Any]]:
    """Map a roster name to all team IDs carrying that exact name."""

    if not _table_exists(connection, "players"):
        return {}
    try:
        rows = connection.execute(
            "SELECT name, team_id FROM players WHERE name IS NOT NULL AND team_id IS NOT NULL"
        ).fetchall()
    except sqlite3.Error:
        return {}
    mapping: dict[str, set[Any]] = defaultdict(set)
    for row in rows:
        mapping[row["name"]].add(row["team_id"])
    return dict(mapping)


def _team_names(connection: sqlite3.Connection) -> dict[Any, str]:
    if not _table_exists(connection, "teams"):
        return {}
    try:
        rows = connection.execute("SELECT id, name FROM teams").fetchall()
    except sqlite3.Error:
        return {}
    return {row["id"]: row["name"] or "" for row in rows}


def _resolve_team(
    row: dict[str, Any],
    *,
    side: str,
    name_to_teams: dict[str, set[Any]],
    team_names: dict[Any, str],
) -> str:
    """Resolve one side as ``team_id``, ``player_name`` or ``unresolved``."""

    pk_key = "team_pk" if side == "player" else "opponent_team_pk"
    name_key = "player_name" if side == "player" else "opponent_name"
    method_key = "team_resolution" if side == "player" else "opponent_team_resolution"
    name_output_key = "team_name" if side == "player" else "opponent_team_name"

    if row.get(pk_key) is not None:
        row[method_key] = "team_id"
        if not row.get(name_output_key):
            row[name_output_key] = team_names.get(row[pk_key], "")
        return "team_id"

    candidates = name_to_teams.get(row.get(name_key), set())
    if len(candidates) == 1:
        resolved_pk = next(iter(candidates))
        row[pk_key] = resolved_pk
        row[method_key] = "player_name"
        row[name_output_key] = team_names.get(resolved_pk, "")
        return "player_name"

    row[method_key] = "ambiguous_name" if len(candidates) > 1 else "unresolved"
    return row[method_key]


def _resolve_rows(
    connection: sqlite3.Connection,
    rows: list[dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    """Annotate rows and return only rows safe to put in an assignment group."""

    name_to_teams = _name_team_map(connection)
    team_names = _team_names(connection)
    eligible: list[dict[str, Any]] = []
    skipped_team = 0
    skipped_context = 0
    skipped_identity = 0

    for row in rows:
        row["lineup_eligible"] = False
        if row.get("player_pk") is None or row.get("opponent_pk") is None:
            skipped_identity += 1
            row["lineup_skip_reason"] = "missing database identity"
            continue
        own = _resolve_team(
            row, side="player", name_to_teams=name_to_teams, team_names=team_names
        )
        opponent = _resolve_team(
            row, side="opponent", name_to_teams=name_to_teams, team_names=team_names
        )
        if own not in {"team_id", "player_name"} or opponent not in {
            "team_id", "player_name"
        }:
            skipped_team += 1
            row["lineup_skip_reason"] = "team identity unresolved"
            continue
        if not row.get("format") or not row.get("session_name"):
            skipped_context += 1
            row["lineup_skip_reason"] = "format or session missing"
            continue
        row["lineup_eligible"] = True
        eligible.append(row)

    if skipped_identity:
        _warn(warnings, f"{skipped_identity} pairing row(s) lacked a database identity and were skipped.")
    if skipped_team:
        _warn(
            warnings,
            f"{skipped_team} pairing row(s) lacked an unambiguous own or opponent team; "
            "they were retained but not assigned.",
        )
    if skipped_context:
        _warn(
            warnings,
            f"{skipped_context} pairing row(s) lacked format/session context and were skipped.",
        )
    return eligible


def _trend_signals(
    player_pk: int,
    format_name: Optional[str],
    session_name: Optional[str],
    trends: dict[tuple[int, Optional[str], Optional[str]], dict[str, Any]],
) -> tuple[Optional[float], Optional[float], bool]:
    """Return (risk, confidence, trend_row_was_found) for one player slot."""

    trend = trends.get((player_pk, normalize_format(format_name), session_name))
    if trend is None:
        return None, None, False
    return (
        calculate_risk_factor(trend.get("volatility"), trend.get("sl_stability")),
        calculate_confidence(trend.get("regression_slope"), trend.get("hot_cold_flag")),
        True,
    )


def _raw_volatility(
    player_pk: int,
    format_name: Optional[str],
    session_name: Optional[str],
    trends: dict[tuple[int, Optional[str], Optional[str]], dict[str, Any]],
) -> Optional[float]:
    """The real, un-combined player_trends.volatility for one player slot --
    analytics.win_probability's own Volatility input. Distinct from
    _trend_signals' `risk` above, which is volatility ALREADY combined with
    sl_stability (analytics.captains_edge.risk_factor); win_probability
    wants the raw signal on its own, not that combined one.
    """
    trend = trends.get((player_pk, normalize_format(format_name), session_name))
    if trend is None:
        return None
    return trend.get("volatility")


def _candidate(
    source: Optional[dict[str, Any]],
    player: dict[str, Any],
    opponent: dict[str, Any],
    *,
    format_name: str,
    session_name: str,
    trends: dict[tuple[int, Optional[str], Optional[str]], dict[str, Any]],
    warnings: list[str],
    weights: LineupWeights = DEFAULT_WEIGHTS,
    win_rates_by_sl: Optional[dict[tuple[int, int], float]] = None,
    win_probability_weights: WinProbabilityWeights = DEFAULT_WIN_PROBABILITY_WEIGHTS,
) -> PairingCandidate:
    player_id = str(player["player_id"])
    opponent_id = str(opponent["opponent_id"])
    context = f"{player.get('player_name', '')} vs {opponent.get('opponent_name', '')}"
    risk, confidence, _ = _trend_signals(
        player["player_pk"], format_name, session_name, trends
    )
    volatility = _raw_volatility(player["player_pk"], format_name, session_name, trends)
    player_skill_level = player.get("player_skill_level")
    opponent_skill_level = opponent.get("opponent_skill_level")
    delta = compute_sl_delta(player_skill_level, opponent_skill_level)
    wr_sl = None
    if win_rates_by_sl is not None and opponent_skill_level is not None:
        wr_sl = win_rates_by_sl.get((player["player_pk"], opponent_skill_level))

    if source is None:
        # This is an absent H2H edge, not a fabricated measurement.  The
        # optimizer can still complete a lineup using neutral defaults; the
        # serialized assignment marks source_pairing=false and warns.
        # WR_H2H (wr_h2h below) has no source here either -- there is no
        # real per-opponent win rate to read for an edge that doesn't
        # exist -- compute_win_probability treats it, like every other
        # missing input, as 0 rather than excluding the pairing.
        modeled_win_probability = compute_win_probability(
            delta, wr_sl, None, volatility, weights=win_probability_weights,
        )
        return PairingCandidate(
            player_id=player_id,
            player_name=player["player_name"] or "",
            opponent_id=opponent_id,
            opponent_name=opponent["opponent_name"] or "",
            matchup_score=None,
            win_probability=None,
            confidence=confidence,
            risk_factor=risk,
            weights=weights,
            modeled_win_probability=modeled_win_probability,
            volatility=volatility,
        )

    wr_h2h = _bounded_probability(source.get("win_probability"), warnings, context)
    modeled_win_probability = compute_win_probability(
        delta, wr_sl, wr_h2h, volatility, weights=win_probability_weights,
    )
    return PairingCandidate(
        player_id=player_id,
        player_name=source["player_name"] or "",
        opponent_id=str(source["opponent_id"]),
        opponent_name=source["opponent_name"] or "",
        matchup_score=_normalized_matchup_score(
            source.get("matchup_score"), warnings, context
        ),
        win_probability=wr_h2h,
        confidence=confidence,
        risk_factor=risk,
        weights=weights,
        modeled_win_probability=modeled_win_probability,
        volatility=volatility,
    )


def _resolution_label(rows: list[dict[str, Any]]) -> str:
    methods = {
        row.get("team_resolution") for row in rows
    } | {
        row.get("opponent_team_resolution") for row in rows
    }
    methods.discard(None)
    if methods == {"team_id"}:
        return "team_id"
    if methods == {"player_name"}:
        return "player_name"
    return "mixed"


def _lineup_for_group(
    rows: list[dict[str, Any]],
    trends: dict[tuple[int, Optional[str], Optional[str]], dict[str, Any]],
    warnings: list[str],
    weights: LineupWeights = DEFAULT_WEIGHTS,
    win_rates_by_sl: Optional[dict[tuple[int, int], float]] = None,
    win_probability_weights: WinProbabilityWeights = DEFAULT_WIN_PROBABILITY_WEIGHTS,
    lineup_risk_weights: LineupRiskWeights = DEFAULT_LINEUP_RISK_WEIGHTS,
    rationale_toggles: RationaleToggles = DEFAULT_RATIONALE_TOGGLES,
) -> dict[str, Any]:
    """Build one assignment document for a resolved team/format/session group."""

    first = rows[0]
    format_name = first["format"]
    session_name = first["session_name"]

    players_by_key: dict[int, dict[str, Any]] = {}
    opponents_by_key: dict[int, dict[str, Any]] = {}
    source_by_pair: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        players_by_key.setdefault(row["player_pk"], row)
        opponents_by_key.setdefault(row["opponent_pk"], row)
        source_by_pair.setdefault((row["player_pk"], row["opponent_pk"]), row)

    players = sorted(
        players_by_key.values(),
        key=lambda row: ((row.get("player_name") or "").casefold(), str(row["player_pk"])),
    )
    opponents = sorted(
        opponents_by_key.values(),
        key=lambda row: (
            (row.get("opponent_name") or "").casefold(), str(row["opponent_pk"])
        ),
    )
    player_names = [row.get("player_name") or "" for row in players]
    opponent_names = [row.get("opponent_name") or "" for row in opponents]

    matrix: list[list[PairingCandidate]] = []
    missing_edges = 0
    for player in players:
        cells: list[PairingCandidate] = []
        for opponent in opponents:
            source = source_by_pair.get((player["player_pk"], opponent["opponent_pk"]))
            if source is None:
                missing_edges += 1
            cells.append(
                _candidate(
                    source,
                    player,
                    opponent,
                    format_name=format_name,
                    session_name=session_name,
                    trends=trends,
                    warnings=warnings,
                    weights=weights,
                    win_rates_by_sl=win_rates_by_sl,
                    win_probability_weights=win_probability_weights,
                )
            )
        matrix.append(cells)

    if missing_edges:
        _warn(
            warnings,
            f"{missing_edges} possible pairing edge(s) in {first.get('team_name') or first.get('team_pk')} "
            f"vs {first.get('opponent_team_name') or first.get('opponent_team_pk')} "
            f"({format_name}, {session_name}) have no H2H row; neutral defaults may be used.",
        )

    solution = solve_lineup_assignment(matrix, player_names, opponent_names)
    assignments: list[dict[str, Any]] = []
    for entry in solution.assignments:
        serialized = vars(entry).copy()
        source = source_by_pair.get(
            next(
                (
                    key
                    for key, value in source_by_pair.items()
                    if str(value.get("player_id")) == entry.player_id
                    and str(value.get("opponent_id")) == entry.opponent_id
                ),
                (None, None),
            )
        )
        serialized["source_pairing"] = source is not None
        serialized["matchup_score_raw"] = source.get("matchup_score") if source else None
        serialized["format"] = format_name
        serialized["session_name"] = session_name
        assignments.append(serialized)

    risk = compute_lineup_risk(solution.assignments, weights=lineup_risk_weights)

    return {
        "team_id": str(first["team_pk"]),
        "team_name": first.get("team_name") or "",
        "opponent_team_id": str(first["opponent_team_pk"]),
        "opponent_team_name": first.get("opponent_team_name") or "",
        "format": format_name,
        "session_name": session_name,
        "roster_resolution": _resolution_label(rows),
        "pairing_rows": len(rows),
        "players_considered": len(players),
        "opponents_considered": len(opponents),
        "assignments": assignments,
        "unassigned_players": solution.unassigned_players,
        "unassigned_opponents": solution.unassigned_opponents,
        "objective_total": solution.objective_total,
        "total_risk": solution.total_risk,
        "total_confidence": solution.total_confidence,
        "tie_break_applied": solution.tie_break_applied,
        "lineup_risk": {
            "upset_risk_index": risk.upset_risk_index,
            "anchor_stability_score": risk.anchor_stability_score,
            "anchor_player_name": risk.anchor_player_name,
            "lineup_volatility_load": risk.lineup_volatility_load,
            "danger_matchup_count": risk.danger_matchup_count,
            "lineup_risk_score": risk.lineup_risk_score,
            "rationale": (
                lineup_risk_rationale(risk, lineup_risk_weights)
                if rationale_toggles.include_lineup_rationale
                else None
            ),
        },
    }


def build_payload(
    connection: sqlite3.Connection,
    source_db: str = "",
    weights: LineupWeights = DEFAULT_WEIGHTS,
    win_probability_weights: WinProbabilityWeights = DEFAULT_WIN_PROBABILITY_WEIGHTS,
    lineup_risk_weights: LineupRiskWeights = DEFAULT_LINEUP_RISK_WEIGHTS,
    rationale_toggles: RationaleToggles = DEFAULT_RATIONALE_TOGGLES,
) -> dict[str, Any]:
    """Build the complete JSON-serializable lineup document."""

    warnings: list[str] = []
    pairings = fetch_pairing_rows(connection, warnings)
    trends = fetch_trends(connection, warnings)
    win_rates_by_sl = fetch_win_rates_by_skill_level(connection, warnings)

    for row in pairings:
        # Keep the source identity separate from any safe name-based
        # resolution below.  A reader can therefore see exactly what the
        # database supplied and why a resolved lineup may use a different
        # team_pk value.
        row["team_pk_raw"] = row.get("team_pk")
        row["opponent_team_pk_raw"] = row.get("opponent_team_pk")
        row["matchup_score_normalized"] = _normalized_matchup_score(
            row.get("matchup_score"),
            warnings,
            f"{row.get('player_name', '')} vs {row.get('opponent_name', '')}",
        )
        row["win_probability_validated"] = _bounded_probability(
            row.get("win_probability"),
            warnings,
            f"{row.get('player_name', '')} vs {row.get('opponent_name', '')}",
        )
        risk, confidence, found = _trend_signals(
            row["player_pk"], row.get("format"), row.get("session_name"), trends
        )
        row["risk_factor"] = risk
        row["confidence"] = confidence
        row["trend_available"] = found

    eligible = _resolve_rows(connection, pairings, warnings)
    grouped: dict[tuple[Any, Any, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        grouped[
            (row["team_pk"], row["opponent_team_pk"], row["format"], row["session_name"])
        ].append(row)

    lineups = [
        _lineup_for_group(
            group, trends, warnings, weights=weights,
            win_rates_by_sl=win_rates_by_sl, win_probability_weights=win_probability_weights,
            lineup_risk_weights=lineup_risk_weights, rationale_toggles=rationale_toggles,
        )
        for _, group in sorted(grouped.items(), key=lambda item: tuple(map(str, item[0])))
    ]

    if pairings:
        trendless = sum(1 for row in pairings if not row.get("trend_available"))
        if trendless:
            _warn(
                warnings,
                f"{trendless} pairing row(s) have no matching player trend for their format/session; "
                "confidence and risk_factor remain null.",
            )

    source = str(Path(source_db).resolve()) if source_db else ""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "source_db": source,
        "pairing_rows": len(pairings),
        "pairings": pairings,
        "players_with_trends": len({key[0] for key in trends}),
        "eligible_pairing_rows": len(eligible),
        "lineups": lineups,
        "resolution_warnings": warnings,
    }


def write_lineups_json(payload: dict[str, Any], path: Path | str) -> Path:
    """Atomically replace a prior lineup export with ``payload``."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    return destination


def load_weights_from_config(config: Optional[dict[str, Any]]) -> LineupWeights:
    """The objective's four real weights, from `config`'s own
    `lineup_optimizer` section -- real, optional overrides, never required.

    Falls back to DEFAULT_WEIGHTS (analytics.lineup_optimizer's original,
    fixed 0.50/0.30/0.15/0.05 split) for a missing section entirely, and
    independently for any one key missing from an otherwise-present
    section -- a config that only overrides one weight does not silently
    zero out the other three.  `config` may be None (no config available
    at all): same fallback, not an error.
    """
    section = (config or {}).get("lineup_optimizer") or {}
    return LineupWeights(
        matchup_score=section.get("weight_matchup_score", DEFAULT_WEIGHTS.matchup_score),
        win_probability=section.get("weight_win_probability", DEFAULT_WEIGHTS.win_probability),
        confidence=section.get("weight_confidence", DEFAULT_WEIGHTS.confidence),
        risk_penalty=section.get("weight_risk_penalty", DEFAULT_WEIGHTS.risk_penalty),
    )


def load_win_probability_weights_from_config(
    config: Optional[dict[str, Any]]
) -> WinProbabilityWeights:
    """analytics.win_probability's real, optional weight overrides, from
    `config`'s own `win_probability` section -- same fallback contract as
    load_weights_from_config above: a missing section, or any one missing
    key within it, falls back to that key's own DEFAULT_WIN_PROBABILITY_WEIGHTS
    value, never a guessed one. `config` may be None.
    """
    section = (config or {}).get("win_probability") or {}
    defaults = DEFAULT_WIN_PROBABILITY_WEIGHTS
    return WinProbabilityWeights(
        sl_delta=section.get("weight_sl_delta", defaults.sl_delta),
        wr_sl=section.get("weight_wr_sl", defaults.wr_sl),
        wr_h2h=section.get("weight_wr_h2h", defaults.wr_h2h),
        volatility=section.get("weight_volatility", defaults.volatility),
        logistic_scale=section.get("logistic_scale", defaults.logistic_scale),
        clamp_min=section.get("clamp_min", defaults.clamp_min),
        clamp_max=section.get("clamp_max", defaults.clamp_max),
    )


def _configured_weights() -> LineupWeights:
    """apa_config.yaml's own `lineup_optimizer` weights, for the standalone
    CLI entry point -- mirrors _configured_db_path's own convention in
    scripts.build_captains_edge: a malformed or absent config is advisory,
    never fatal, and just falls back to DEFAULT_WEIGHTS."""
    config_path = PROJECT_ROOT / "apa_config.yaml"
    if not config_path.is_file():
        return DEFAULT_WEIGHTS
    try:
        import yaml  # only needed to read the configured weights

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:  # pragma: no cover - config is advisory, never required
        logger.debug("Could not read %s; using default lineup optimizer weights", config_path)
        return DEFAULT_WEIGHTS
    return load_weights_from_config(config)


def _configured_win_probability_weights() -> WinProbabilityWeights:
    """apa_config.yaml's own `win_probability` weights, for the standalone
    CLI entry point -- same advisory-never-fatal convention as
    _configured_weights above."""
    config_path = PROJECT_ROOT / "apa_config.yaml"
    if not config_path.is_file():
        return DEFAULT_WIN_PROBABILITY_WEIGHTS
    try:
        import yaml  # only needed to read the configured weights

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:  # pragma: no cover - config is advisory, never required
        logger.debug("Could not read %s; using default win probability weights", config_path)
        return DEFAULT_WIN_PROBABILITY_WEIGHTS
    return load_win_probability_weights_from_config(config)


def load_lineup_risk_weights_from_config(config: Optional[dict[str, Any]]) -> LineupRiskWeights:
    """analytics.lineup_risk's real, optional weight overrides, from
    `config`'s own `lineup_risk` section -- same fallback contract as
    load_weights_from_config/load_win_probability_weights_from_config
    above: a missing section, or any one missing key within it, falls
    back to that key's own DEFAULT_LINEUP_RISK_WEIGHTS value. `config`
    may be None.
    """
    section = (config or {}).get("lineup_risk") or {}
    defaults = DEFAULT_LINEUP_RISK_WEIGHTS
    return LineupRiskWeights(
        upset_risk=section.get("weight_upset_risk", defaults.upset_risk),
        anchor_instability=section.get("weight_anchor_instability", defaults.anchor_instability),
        volatility_load=section.get("weight_volatility_load", defaults.volatility_load),
        danger_count=section.get("weight_danger_count", defaults.danger_count),
        danger_threshold=section.get("danger_threshold", defaults.danger_threshold),
    )


def _configured_lineup_risk_weights() -> LineupRiskWeights:
    """apa_config.yaml's own `lineup_risk` weights, for the standalone CLI
    entry point -- same advisory-never-fatal convention as
    _configured_weights above."""
    config_path = PROJECT_ROOT / "apa_config.yaml"
    if not config_path.is_file():
        return DEFAULT_LINEUP_RISK_WEIGHTS
    try:
        import yaml  # only needed to read the configured weights

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:  # pragma: no cover - config is advisory, never required
        logger.debug("Could not read %s; using default lineup risk weights", config_path)
        return DEFAULT_LINEUP_RISK_WEIGHTS
    return load_lineup_risk_weights_from_config(config)


def load_rationale_toggles_from_config(config: Optional[dict[str, Any]]) -> RationaleToggles:
    """analytics.rationale's real, optional toggles, from `config`'s own
    `rationale` section -- same fallback contract as the weight loaders
    above: a missing section, or a missing key within it, falls back to
    that key's own DEFAULT_RATIONALE_TOGGLES value."""
    section = (config or {}).get("rationale") or {}
    defaults = DEFAULT_RATIONALE_TOGGLES
    return RationaleToggles(
        include_lineup_rationale=section.get(
            "include_lineup_rationale", defaults.include_lineup_rationale
        ),
    )


def _configured_rationale_toggles() -> RationaleToggles:
    """apa_config.yaml's own `rationale` toggles, for the standalone CLI
    entry point -- same advisory-never-fatal convention as
    _configured_weights above."""
    config_path = PROJECT_ROOT / "apa_config.yaml"
    if not config_path.is_file():
        return DEFAULT_RATIONALE_TOGGLES
    try:
        import yaml  # only needed to read the configured toggles

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:  # pragma: no cover - config is advisory, never required
        logger.debug("Could not read %s; using default rationale toggles", config_path)
        return DEFAULT_RATIONALE_TOGGLES
    return load_rationale_toggles_from_config(config)


def build(
    db_path: Optional[str] = None,
    out_dir: Optional[str] = None,
    weights: LineupWeights = DEFAULT_WEIGHTS,
    win_probability_weights: WinProbabilityWeights = DEFAULT_WIN_PROBABILITY_WEIGHTS,
    lineup_risk_weights: LineupRiskWeights = DEFAULT_LINEUP_RISK_WEIGHTS,
    rationale_toggles: RationaleToggles = DEFAULT_RATIONALE_TOGGLES,
) -> Path:
    """Read the source database and atomically write ``lineups.json``."""

    resolved = resolve_db_path(db_path)
    logger.info("Reading %s", resolved)
    connection = connect_read_only(resolved)
    try:
        payload = build_payload(
            connection, source_db=str(resolved), weights=weights,
            win_probability_weights=win_probability_weights,
            lineup_risk_weights=lineup_risk_weights,
            rationale_toggles=rationale_toggles,
        )
    finally:
        connection.close()

    directory = Path(out_dir) if out_dir else DEFAULT_OUT_DIR
    output = write_lineups_json(payload, directory / JSON_NAME)
    logger.info(
        "Wrote %s (%d pairing rows, %d lineup(s))",
        output,
        payload["pairing_rows"],
        len(payload["lineups"]),
    )
    return output


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Build one-to-one APA lineups.")
    parser.add_argument("--db", help="path to the SQLite database")
    parser.add_argument("--out-dir", help=f"output directory (default: {DEFAULT_OUT_DIR})")
    args = parser.parse_args()
    try:
        output = build(
            args.db, args.out_dir,
            weights=_configured_weights(),
            win_probability_weights=_configured_win_probability_weights(),
            lineup_risk_weights=_configured_lineup_risk_weights(),
            rationale_toggles=_configured_rationale_toggles(),
        )
    except NoDatabaseError as exc:
        print(f"\n{exc}\n")
        return 1
    print(f"\nOpen lineup export: {output}\n")
    return 0


# Small, discoverable aliases for callers that use the plural noun from the
# artifact name.  ``build`` remains the canonical CLI/pipeline entry point.
fetch_pairings = fetch_pairing_rows
write_json = write_lineups_json
build_lineups = build


if __name__ == "__main__":
    raise SystemExit(main())
