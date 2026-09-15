"""Trend Analyzer: docs/trend_analyzer.md's presentation contract.

``analytics/player_trends.py`` remains the sole formula owner -- this module
introduces no second trend calculation. It assembles the dedicated,
immutable ``TrendAnalyzerReport`` the doc's "Current status and extension
wiring" section calls for: one row per already-persisted ``PlayerTrend``
(plus its already-public ``trend_score``, computed here only by calling
``analytics.player_trends.trend_score`` on the SAME regression_slope/
volatility/sample_size that row already carries -- never re-derived from raw
skill levels) and one row per real chronological skill-level observation for
the "Trend History" sheet/chart.

Purely derived and purely computational: takes already-fetched, already-
scoped real rows (the caller's job, per docs/trend_analyzer.md's query
boundary) and computes. Queries nothing, imports no UI renderer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from analytics.player_trends import trend_score as _trend_score

FORMULA_VERSION = "trend-analyzer-v1-presentation-over-player-trends"


@dataclass(frozen=True)
class TrendAnalyzerRow:
    """One (player, format, session) presentation row: the persisted
    PlayerTrend fields plus the already-public trend_score."""

    player_id: int
    player_external_id: str
    player_name: str
    format: Optional[str]
    session_name: Optional[str]
    sample_size: int
    current_skill_level: Optional[int]
    regression_slope: Optional[float]
    volatility: Optional[float]
    sl_stability: Optional[float]
    hot_cold_indicator: Optional[str]
    trend_score: Optional[float]
    projected_sl_change_probability: Optional[float]


@dataclass(frozen=True)
class TrendHistoryRow:
    """One real, chronologically-ordered skill-level observation."""

    player_id: int
    player_external_id: str
    match_id: Optional[str]
    match_order: int
    match_date: Optional[str]
    format: Optional[str]
    session_name: Optional[str]
    skill_level: Optional[int]


@dataclass(frozen=True)
class TrendAnalyzerReport:
    team_external_id: str
    team_name: str
    session_name: str
    format: Optional[str]
    source_manifest_id: Optional[str]
    captured_at: Optional[str]
    formula_version: str

    rows: tuple[TrendAnalyzerRow, ...]
    history: tuple[TrendHistoryRow, ...]

    measured_count: int
    hot_count: int
    cold_count: int
    neutral_count: int
    no_data_count: int


def build_rows(trend_rows: Sequence[dict]) -> tuple[TrendAnalyzerRow, ...]:
    """One ``TrendAnalyzerRow`` per already-persisted PlayerTrend dict.

    ``trend_rows`` -- one dict per row: ``player_id``/``player_external_id``/
    ``player_name``/``format``/``session_name``/``sample_size``/
    ``current_skill_level``/``regression_slope``/``volatility``/
    ``sl_stability``/``hot_cold_flag``/``projected_sl_change_probability``.
    """
    rows = []
    for r in trend_rows:
        rows.append(TrendAnalyzerRow(
            player_id=r["player_id"],
            player_external_id=r["player_external_id"],
            player_name=r["player_name"],
            format=r.get("format"),
            session_name=r.get("session_name"),
            sample_size=r["sample_size"],
            current_skill_level=r.get("current_skill_level"),
            regression_slope=r.get("regression_slope"),
            volatility=r.get("volatility"),
            sl_stability=r.get("sl_stability"),
            hot_cold_indicator=r.get("hot_cold_flag"),
            trend_score=_trend_score(
                r.get("regression_slope"), r.get("volatility"), r["sample_size"]
            ),
            projected_sl_change_probability=r.get("projected_sl_change_probability"),
        ))
    # Canonical initial order: format, session, player name, external id --
    # never the existing table's slope-first order (docs/trend_analyzer.md).
    rows.sort(key=lambda r: (
        r.format or "", r.session_name or "", r.player_name, r.player_external_id
    ))
    return tuple(rows)


def build_report(
    team_external_id: str,
    team_name: str,
    session_name: str,
    trend_rows: Sequence[dict],
    history_rows: Sequence[dict],
    *,
    format: Optional[str] = None,
    source_manifest_id: Optional[str] = None,
    captured_at: Optional[str] = None,
) -> TrendAnalyzerReport:
    """``history_rows`` -- one dict per real observation: ``player_id``/
    ``player_external_id``/``match_id``/``match_order``/``match_date``/
    ``format``/``session_name``/``skill_level``."""
    rows = build_rows(trend_rows)
    history = tuple(
        TrendHistoryRow(
            player_id=h["player_id"], player_external_id=h["player_external_id"],
            match_id=h.get("match_id"), match_order=h["match_order"],
            match_date=h.get("match_date"), format=h.get("format"),
            session_name=h.get("session_name"), skill_level=h.get("skill_level"),
        )
        for h in history_rows
    )

    hot = sum(1 for r in rows if r.hot_cold_indicator == "HOT")
    cold = sum(1 for r in rows if r.hot_cold_indicator == "COLD")
    neutral = sum(1 for r in rows if r.hot_cold_indicator == "NEUTRAL")
    no_data = sum(1 for r in rows if r.hot_cold_indicator is None)

    return TrendAnalyzerReport(
        team_external_id=team_external_id, team_name=team_name, session_name=session_name,
        format=format, source_manifest_id=source_manifest_id, captured_at=captured_at,
        formula_version=FORMULA_VERSION,
        rows=rows, history=history,
        measured_count=len(rows) - no_data, hot_count=hot, cold_count=cold,
        neutral_count=neutral, no_data_count=no_data,
    )
