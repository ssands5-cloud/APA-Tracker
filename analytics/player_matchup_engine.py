"""Player Matchup Engine (Coach Mode): a purely descriptive, one-pairing
report for a coach comparing two specific players.

This is a REPORTER, like every other module in this project's analytics
layer -- it recomputes nothing. Every field comes straight from
``analytics.pairing_evidence.PairingEvidence`` (evidence label, DIRECT
observed win rate, DIRECT match count, the validated modeled probability)
and ``analytics.skill_level_trends`` (raw trend direction/volatility,
already NOT excluded by docs/captain_first_edge_experience.md's Issue #14
table as long as it stays numeric/raw rather than a categorical badge --
see that table's row for ``analytics.player_trends.trend_score`` /
``hot_cold_flag`` specifically).

Deliberately excluded, per the same table, until a real validation pass
exists (Option B in the Coach Advantage architecture plan): a new modeled
win-probability/confidence number, and any categorical "favored"/"dangerous"
verdict. The ``summary`` field here is plain-language but strictly
descriptive -- it states what the real evidence is, never a verdict a
threshold hasn't been checked to support. See ``docs/matchups.md`` and
``docs/captain_first_edge_experience.md`` §13 for the fuller history of why
that distinction matters in this codebase specifically.

Purely computational: takes an already-built ``PairingEvidence`` row plus
each side's already-computed skill-trend info, queries nothing itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from analytics.pairing_evidence import EvidenceLabel, PairingEvidence
from analytics.skill_level_trends import (
    skill_level_changes,
    skill_level_trend,
    skill_level_volatility,
)
from database.models import PlayerMatch


@dataclass(frozen=True)
class SkillTrendInfo:
    """One player's raw skill-level trend, over their whole captured
    history -- not scoped to this one pairing's format/session, since
    skill level itself is not format/session-specific in this project's
    data model (``Player.skill_level`` / ``PlayerMatch.skill_level`` carry
    no format dimension)."""

    trend: str
    volatility: int
    last_change: Optional[str]


def skill_trend_for(matches: list[PlayerMatch]) -> SkillTrendInfo:
    """Build one player's ``SkillTrendInfo`` from their own chronological
    ``PlayerMatch`` rows (the same shape
    ``database.queries.skill_level_history`` returns, already filtered to
    one player_id by the caller -- see
    ``ui/export_json.py::_skill_level_summary`` for the same grouping
    pattern this mirrors).
    """
    changes = skill_level_changes(matches)
    last_change_text: Optional[str] = None
    if changes:
        last = changes[-1]
        last_change_text = f"SL {last.from_level} → SL {last.to_level}"
        if last.week is not None:
            last_change_text += f" in Week {last.week}"
    return SkillTrendInfo(
        trend=skill_level_trend(matches),
        volatility=skill_level_volatility(matches),
        last_change=last_change_text,
    )


NO_SKILL_TREND = SkillTrendInfo(trend="no data", volatility=0, last_change=None)


@dataclass(frozen=True)
class PlayerMatchupReport:
    """One real (player, opponent) pairing's full Coach Mode report,
    scoped to the exact real team pairing it came from -- ``our_team_*``/
    ``opponent_team_*`` make this report's identity unique across a bundle
    covering several real scopes (the same two players can face each other
    under more than one real format/session against the division), which
    ``player_id``/``opponent_id`` alone do not guarantee."""

    player_id: int
    player_external_id: str
    player_name: str
    player_skill_level: Optional[int]
    player_trend: SkillTrendInfo
    opponent_id: int
    opponent_external_id: str
    opponent_name: str
    opponent_skill_level: Optional[int]
    opponent_trend: SkillTrendInfo
    our_team_external_id: str
    opponent_team_external_id: str
    opponent_team_name: Optional[str]
    format: str
    session_name: str
    evidence_label: EvidenceLabel
    observed_win_rate: Optional[float]
    direct_evidence_count: int
    direct_wins: Optional[int]
    direct_losses: Optional[int]
    modeled_win_probability: Optional[float]
    model_source: Optional[str]
    summary: str


def _summary_for(
    pairing: PairingEvidence,
    player_trend: SkillTrendInfo,
    opponent_trend: SkillTrendInfo,
    direct_wins: Optional[int],
    direct_losses: Optional[int],
) -> str:
    """Plain-language, strictly descriptive summary -- states what the real
    evidence is, never a "favored because" verdict (see module docstring).
    """
    if pairing.evidence_label is EvidenceLabel.DIRECT:
        rate_pct = (
            f"{pairing.observed_win_rate:.0%}" if pairing.observed_win_rate is not None else "No data"
        )
        record = f" ({direct_wins}-{direct_losses})" if direct_wins is not None else ""
        parts = [
            f"Direct record: {rate_pct} observed win rate{record} across "
            f"{pairing.direct_evidence_count} recorded match(es)."
        ]
    elif pairing.evidence_label is EvidenceLabel.INDIRECT:
        parts = [
            "No direct history."
            + (
                f" Skill-only estimate: {pairing.modeled_win_probability:.0%} "
                f"(SL{pairing.player_skill_level} vs SL{pairing.opponent_skill_level})."
                if pairing.modeled_win_probability is not None
                else " No skill-only estimate available (a skill level is missing)."
            )
        ]
    else:
        parts = ["No data available for this pairing."]

    trend_bits = []
    if player_trend.trend != "no data":
        trend_bits.append(f"{pairing.player_name}: {player_trend.trend}")
    if opponent_trend.trend != "no data":
        trend_bits.append(f"{pairing.opponent_name}: {opponent_trend.trend}")
    if trend_bits:
        # "Whole captured history", never "recent": skill_level_history()
        # pulls every match-linked reading a player has, across whatever
        # teams/sessions were captured -- not scoped to this one pairing's
        # format/session, and not windowed to anything recent.
        parts.append("Skill trend (whole captured history) — " + "; ".join(trend_bits) + ".")

    return " ".join(parts)


def build_player_matchup_report(
    pairing: PairingEvidence,
    our_team_external_id: str,
    opponent_team_external_id: str,
    player_trend: Optional[SkillTrendInfo] = None,
    opponent_trend: Optional[SkillTrendInfo] = None,
    opponent_team_name: Optional[str] = None,
) -> PlayerMatchupReport:
    """Build one Coach Mode report from an already-classified
    ``PairingEvidence`` row, scoped to the real team pairing it came from.
    ``player_trend``/``opponent_trend`` default to "no data" rather than
    raising, since a player with no skill-level reading at all is a real,
    valid state this report must still show honestly. ``direct_wins``/
    ``direct_losses`` are carried straight through from ``pairing`` --
    counted directly from the authoritative rows at Stage 1, never
    reconstructed from the rounded ``observed_win_rate`` here (GPT audit
    follow-up: reconstruction is not exact in general for large samples).
    ``opponent_team_name`` disambiguates this report from another real
    scope against a same-named opponent player on a different team (GPT
    audit follow-up: linked opponent-selector labels need the team, not
    just the opponent's name/format/session).
    """
    player_trend = player_trend if player_trend is not None else NO_SKILL_TREND
    opponent_trend = opponent_trend if opponent_trend is not None else NO_SKILL_TREND
    direct_wins, direct_losses = pairing.direct_wins, pairing.direct_losses
    return PlayerMatchupReport(
        player_id=pairing.player_id,
        player_external_id=pairing.player_external_id,
        player_name=pairing.player_name,
        player_skill_level=pairing.player_skill_level,
        player_trend=player_trend,
        opponent_id=pairing.opponent_id,
        opponent_external_id=pairing.opponent_external_id,
        opponent_name=pairing.opponent_name,
        opponent_skill_level=pairing.opponent_skill_level,
        opponent_trend=opponent_trend,
        our_team_external_id=our_team_external_id,
        opponent_team_external_id=opponent_team_external_id,
        opponent_team_name=opponent_team_name,
        format=pairing.format,
        session_name=pairing.session_name,
        evidence_label=pairing.evidence_label,
        observed_win_rate=pairing.observed_win_rate,
        direct_evidence_count=pairing.direct_evidence_count,
        direct_wins=direct_wins,
        direct_losses=direct_losses,
        modeled_win_probability=pairing.modeled_win_probability,
        model_source=pairing.model_source,
        summary=_summary_for(pairing, player_trend, opponent_trend, direct_wins, direct_losses),
    )
