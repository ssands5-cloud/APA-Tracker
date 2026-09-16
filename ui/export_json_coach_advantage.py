"""JSON serialization for the Coach Advantage Tools
(``analytics.player_matchup_engine`` / ``analytics.team_matchup_engine``).

A REPORTER, like ``scripts/build_captains_edge.py``'s own JSON writer:
turns already-built dataclasses into plain dicts. No computation happens
here.
"""

from __future__ import annotations

from typing import Optional

from analytics.lineup_lab import LineupLabResult
from analytics.player_matchup_engine import PlayerMatchupReport, SkillTrendInfo
from analytics.team_matchup_engine import RankedOpponent, RosterEntry, TeamMatchupReport


def _trend_dict(trend: SkillTrendInfo) -> dict:
    return {
        "trend": trend.trend,
        "volatility": trend.volatility,
        "last_change": trend.last_change,
        "readings": list(trend.readings),
        "reading_dates": list(trend.reading_dates),
    }


def player_matchup_report_to_dict(report: PlayerMatchupReport) -> dict:
    return {
        "player": {
            "id": report.player_id,
            "external_id": report.player_external_id,
            "name": report.player_name,
            "skill_level": report.player_skill_level,
            "trend": _trend_dict(report.player_trend),
        },
        "opponent": {
            "id": report.opponent_id,
            "external_id": report.opponent_external_id,
            "name": report.opponent_name,
            "skill_level": report.opponent_skill_level,
            "trend": _trend_dict(report.opponent_trend),
        },
        "our_team_id": report.our_team_external_id,
        "opponent_team_id": report.opponent_team_external_id,
        "opponent_team_name": report.opponent_team_name,
        "format": report.format,
        "session_name": report.session_name,
        "evidence_label": report.evidence_label.value,
        "observed_win_rate": report.observed_win_rate,
        "direct_evidence_count": report.direct_evidence_count,
        "direct_wins": report.direct_wins,
        "direct_losses": report.direct_losses,
        "modeled_win_probability": report.modeled_win_probability,
        "model_source": report.model_source,
        "summary": report.summary,
    }


def _roster_entry_to_dict(entry: RosterEntry) -> dict:
    return {
        "id": entry.player_id,
        "external_id": entry.player_external_id,
        "name": entry.player_name,
        "skill_level": entry.skill_level,
        "trend": _trend_dict(entry.trend),
    }


def _ranked_opponent_to_dict(entry: RankedOpponent) -> dict:
    return {
        "id": entry.opponent_id,
        "external_id": entry.opponent_external_id,
        "name": entry.opponent_name,
        "skill_level": entry.opponent_skill_level,
        "direct_win_rate": entry.direct_win_rate,
        "direct_wins": entry.direct_wins,
        "direct_losses": entry.direct_losses,
        "direct_sample_size": entry.direct_sample_size,
        "reliability_weighted_skill_probability": entry.reliability_weighted_skill_probability,
    }


def _lineup_result_to_dict(result: Optional[LineupLabResult]) -> Optional[dict]:
    if result is None:
        return None
    return {
        "assignments": [
            {
                "board": index + 1,
                "player_id": slot.player_id,
                "player_name": slot.player_name,
                "player_skill_level": slot.player_skill_level,
                "opponent_id": slot.opponent_id,
                "opponent_name": slot.opponent_name,
                "opponent_skill_level": slot.opponent_skill_level,
                "evidence_label": slot.evidence_label.value,
                "observed_win_rate": slot.observed_win_rate,
                "direct_evidence_count": slot.direct_evidence_count,
                "modeled_win_probability": slot.modeled_win_probability,
                "model_source": slot.model_source,
                "lineup_score": slot.lineup_score,
                "lineup_score_source": slot.lineup_score_source,
            }
            for index, slot in enumerate(result.assignments)
        ],
        "unassigned_players": [
            {"id": u.player_id, "name": u.player_name} for u in result.unassigned_players
        ],
        "unassigned_opponents": [
            {"id": u.opponent_id, "name": u.opponent_name} for u in result.unassigned_opponents
        ],
        "total_score": result.total_score,
        "skill_total": result.skill_total,
        "is_legal": result.is_legal,
        "blocked_reason": result.blocked_reason,
    }


def team_matchup_report_to_dict(report: TeamMatchupReport) -> dict:
    return {
        "our_team": {"id": report.our_team_external_id, "name": report.our_team_name},
        "opponent_team": {
            "id": report.opponent_team_external_id, "name": report.opponent_team_name,
        },
        "format": report.format,
        "session_name": report.session_name,
        "our_roster": [_roster_entry_to_dict(r) for r in report.our_roster],
        "opponent_roster": [_roster_entry_to_dict(r) for r in report.opponent_roster],
        "evidence_counts": report.evidence_counts,
        "ranked_opponents": [_ranked_opponent_to_dict(r) for r in report.ranked_opponents],
        "lineup": _lineup_result_to_dict(report.lineup_result),
        "lineup_error": report.lineup_error,
        "summary": report.summary,
    }
