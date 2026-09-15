"""Opponent Volatility Profile: docs/opponent_volatility.md.

Summarizes how much each canonical opponent roster player's captured skill
level has varied, from the already-persisted ``PlayerTrend.volatility``
(sample standard deviation over the last 20 readings) and
``PlayerTrend.sl_stability``. Introduces one monotonic display transform and
a median team summary -- it does NOT infer per-opponent-game volatility,
shot variance, temperament, or match risk, and it never joins
`analytics.opponent_scouting`'s legacy threshold-based danger model.

Purely derived and purely computational: takes already-fetched, already-
scoped real rows (canonical opponent roster identity + matching PlayerTrend
rows, the caller's job) and computes. Queries nothing, imports no UI
renderer, and does not modify analytics/player_vs_player.py.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Optional, Sequence

FORMULA_VERSION = "opponent-volatility-v1-sl-transform"

INSUFFICIENT_EVIDENCE = "Insufficient evidence"
NO_OBSERVED_VARIATION = "No observed SL variation"
OBSERVED_VARIATION = "Observed SL variation"


@dataclass(frozen=True)
class OpponentVolatilityPlayerRow:
    """One canonical opponent roster player's real volatility evidence."""

    player_id: int
    player_external_id: str
    player_name: str
    format: Optional[str]
    session_name: Optional[str]
    sample_size: Optional[int]
    sigma: Optional[float]
    sl_stability: Optional[float]
    volatility_index: Optional[float]
    regression_slope: Optional[float]
    descriptor: str
    source_status: str


@dataclass(frozen=True)
class OpponentVolatilityProfile:
    opponent_team_external_id: str
    opponent_team_name: str
    session_name: str
    format: Optional[str]
    source_manifest_id: Optional[str]
    captured_at: Optional[str]
    formula_version: str

    team_volatility_index: Optional[float]
    coverage: Optional[float]
    roster_count: int
    measured_count: int

    player_rows: tuple[OpponentVolatilityPlayerRow, ...]


def volatility_index(sigma: Optional[float]) -> Optional[float]:
    """100 * sigma / (1 + sigma) -- a monotonic 0-100 display transform of
    the unbounded skill-level standard deviation. Null when sigma is null;
    a measured zero (>= 2 real readings, no observed change) is a real,
    different fact from missing evidence."""
    if sigma is None:
        return None
    return round(100 * sigma / (1 + sigma), 4)


def descriptor(sigma: Optional[float]) -> str:
    """Evidence state and the sign of the measured value only -- no
    invented high/medium/low cutoff, never restyled as danger/favorable/
    Avoid/Target."""
    if sigma is None:
        return INSUFFICIENT_EVIDENCE
    if sigma == 0:
        return NO_OBSERVED_VARIATION
    return OBSERVED_VARIATION


def _player_row(row: dict) -> OpponentVolatilityPlayerRow:
    sigma = row.get("volatility")
    return OpponentVolatilityPlayerRow(
        player_id=row["player_id"],
        player_external_id=row["player_external_id"],
        player_name=row["player_name"],
        format=row.get("format"),
        session_name=row.get("session_name"),
        sample_size=row.get("sample_size"),
        sigma=sigma,
        sl_stability=row.get("sl_stability"),
        volatility_index=volatility_index(sigma),
        regression_slope=row.get("regression_slope"),
        descriptor=descriptor(sigma),
        source_status="Measured" if sigma is not None else "No trend row",
    )


def build_profile(
    opponent_team_external_id: str,
    opponent_team_name: str,
    session_name: str,
    roster_players: Sequence[dict],
    trend_by_player_id: dict[int, dict],
    *,
    format: Optional[str] = None,
    source_manifest_id: Optional[str] = None,
    captured_at: Optional[str] = None,
) -> OpponentVolatilityProfile:
    """``roster_players`` -- one dict per canonical opponent roster player:
    ``player_id``/``player_external_id``/``player_name``. ``trend_by_player_id``
    -- at most one already-persisted PlayerTrend dict per player id, already
    scoped to the exact normalized format/session (the caller's join). Every
    roster player appears in the output even when no trend row matches;
    missing rows produce null values and reduce coverage, never a guess.
    """
    rows = []
    for player in roster_players:
        trend = trend_by_player_id.get(player["player_id"])
        merged = {
            "player_id": player["player_id"],
            "player_external_id": player["player_external_id"],
            "player_name": player["player_name"],
            "format": (trend or {}).get("format", format),
            "session_name": (trend or {}).get("session_name", session_name),
            "sample_size": (trend or {}).get("sample_size"),
            "volatility": (trend or {}).get("volatility"),
            "sl_stability": (trend or {}).get("sl_stability"),
            "regression_slope": (trend or {}).get("regression_slope"),
        }
        rows.append(_player_row(merged))

    measured = [r.volatility_index for r in rows if r.volatility_index is not None]
    team_index = round(statistics.median(measured), 4) if measured else None
    coverage = round(len(measured) / len(rows), 6) if rows else None

    return OpponentVolatilityProfile(
        opponent_team_external_id=opponent_team_external_id,
        opponent_team_name=opponent_team_name,
        session_name=session_name,
        format=format,
        source_manifest_id=source_manifest_id,
        captured_at=captured_at,
        formula_version=FORMULA_VERSION,
        team_volatility_index=team_index,
        coverage=coverage,
        roster_count=len(rows),
        measured_count=len(measured),
        player_rows=tuple(rows),
    )
