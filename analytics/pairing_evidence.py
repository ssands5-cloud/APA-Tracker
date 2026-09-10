"""
Pairing Evidence Classifier: labels every feasible player-vs-opponent
pairing DIRECT, INDIRECT, or UNKNOWN before any captain-first view renders
it, and keeps the observed win rate that backs a DIRECT/INDIRECT label
strictly separate from any modeled probability.

This is the Stage 1 (data-layer) piece of
docs/captain_first_edge_experience.md (see its §4-§8). It does not touch
HTML, Excel, the frozen scraper contract, or any analytics module listed in
that document's §13 exclusion table (analytics.win_probability,
analytics.lineup_risk, analytics.opponent_scouting, analytics.rationale,
analytics.season_projection, analytics.captains_edge_summary) -- it reads
only raw, recognized-result PlayerHeadToHead rows, the same real evidence
analytics.matchups already scores, through a second, independent lens: not
"how good is this pairing" but "how much do we actually know about it, and
from what."

Evidence labels
----------------
DIRECT   -- at least one recognized-result (W/L) PlayerHeadToHead row
            exists for this exact (player, opponent) pair, in the given
            format/session scope. observed_win_rate is the real,
            unweighted win rate over those rows -- the same definition
            analytics.matchups.head_to_head_win_rate uses, computed
            independently here so this module has no import-time
            dependency on that engine's own neutral-fallback behaviour
            (see docs/captain_first_edge_experience.md §6).
INDIRECT -- no direct row exists, but the player has at least one
            recognized-result row against a DIFFERENT opponent who shares
            the target opponent's skill level, in the same format/session
            scope. indirect_win_rate is the real, unweighted win rate over
            those other-opponent games -- the same real aggregation
            docs/win_probability.md calls WR_SL, reported here as a
            labeled, separately-surfaced observed rate, never blended into
            a single number with the DIRECT case and never called a
            "probability."
UNKNOWN  -- neither of the above. No fallback score, no neutral 0.5 or 50,
            is substituted. observed_win_rate and indirect_win_rate are
            both None; a caller renders that as "No data", never as a
            fabricated rate.

A pairing with a DIRECT label may still have indirect evidence available
(games against other same-skill-level opponents); this module still labels
it DIRECT -- exact-opponent evidence outranks same-skill-level evidence for
the label -- but indirect_win_rate stays populated alongside it as
descriptive context, never blended into observed_win_rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from analytics.matchups import _is_win, recognized_results
from database.models import PlayerHeadToHead


class EvidenceLabel(str, Enum):
    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PairingEvidence:
    player_id: int
    opponent_id: int
    format: Optional[str]
    session_name: Optional[str]
    evidence_label: EvidenceLabel
    observed_win_rate: Optional[float]      # DIRECT only; None otherwise -- never 0.0/50 as a stand-in for "no data"
    direct_evidence_count: int              # recognized DIRECT games; 0 when not DIRECT
    indirect_win_rate: Optional[float]      # same-skill-level rate, when it exists, regardless of the pairing's own label
    indirect_evidence_count: int            # recognized same-skill-level games behind indirect_win_rate
    indirect_skill_level: Optional[int]     # the opponent skill level indirect_win_rate is scoped to; None when there's no indirect evidence


def _observed_win_rate(rows: list[PlayerHeadToHead]) -> Optional[float]:
    """Wins / recognized games, or None when there are no recognized games
    -- never 0.0 for "no data". See docs/captain_first_edge_experience.md
    §6: this module's neutral case is None, not analytics.matchups'
    documented 0.0/50 fallbacks (those are correct for their own,
    already-shipped, already-documented outputs, not for this one)."""
    recognized = recognized_results(rows)
    if not recognized:
        return None
    wins = sum(1 for row in recognized if _is_win(row.result))
    return round(wins / len(recognized), 3)


def classify_pairing(
    player_id: int,
    opponent_id: int,
    opponent_skill_level: Optional[int],
    format: Optional[str],
    session_name: Optional[str],
    direct_rows: list[PlayerHeadToHead],
    same_skill_level_rows: list[PlayerHeadToHead],
) -> PairingEvidence:
    """Classify one feasible pairing.

    direct_rows -- every real PlayerHeadToHead row already scoped by the
    caller to this exact (player_id, opponent_id, format, session_name).
    This module does not query the database or apply its own scoping --
    see database.queries.head_to_head_history for the real query.

    same_skill_level_rows -- every real PlayerHeadToHead row for player_id
    against a DIFFERENT opponent sharing opponent_skill_level, same
    format/session scope, EXCLUDING opponent_id's own rows (so a DIRECT
    pairing's own games are never double-counted into its own indirect
    rate). The caller does this exclusion -- see
    tests/test_pairing_evidence.py for the exact real-data shape expected.
    """
    direct_recognized = recognized_results(direct_rows)
    indirect_recognized = recognized_results(same_skill_level_rows)
    indirect_rate = _observed_win_rate(same_skill_level_rows)

    if direct_recognized:
        label = EvidenceLabel.DIRECT
        observed = _observed_win_rate(direct_rows)
    elif indirect_recognized:
        label = EvidenceLabel.INDIRECT
        observed = None
    else:
        label = EvidenceLabel.UNKNOWN
        observed = None

    return PairingEvidence(
        player_id=player_id,
        opponent_id=opponent_id,
        format=format,
        session_name=session_name,
        evidence_label=label,
        observed_win_rate=observed,
        direct_evidence_count=len(direct_recognized),
        indirect_win_rate=indirect_rate,
        indirect_evidence_count=len(indirect_recognized),
        indirect_skill_level=opponent_skill_level if indirect_recognized else None,
    )


def feasible_pairings(
    our_player_ids: list[int],
    opponent_player_ids: list[int],
    unavailable_player_ids: Optional[set[int]] = None,
) -> list[tuple[int, int]]:
    """Every (player_id, opponent_id) combination across two real player-id
    lists, minus any player the captain marked unavailable for tonight
    (docs/captain_first_edge_experience.md §2/§3). This is the complete
    feasible set every pairing in the matrix must be classified against --
    see build_pairing_matrix's reconciliation requirement below.

    Duplicate ids in either input collapse via dict.fromkeys (order-
    preserving): a real roster/id list has no duplicates, but this guards a
    caller's list either way rather than silently inflating the feasible
    count with a repeated pair.
    """
    unavailable = unavailable_player_ids or set()
    ours = [pid for pid in dict.fromkeys(our_player_ids) if pid not in unavailable]
    theirs = [pid for pid in dict.fromkeys(opponent_player_ids) if pid not in unavailable]
    return [(player_id, opponent_id) for player_id in ours for opponent_id in theirs]


def build_pairing_matrix(pairings: list[PairingEvidence]) -> dict[str, int]:
    """Evidence-count reconciliation
    (docs/captain_first_edge_experience.md §8): DIRECT + INDIRECT + UNKNOWN
    must equal the total number of feasible pairings classified. Returns
    the counts (plus 'total_feasible_pairings'); raises AssertionError if
    they don't reconcile.

    This is a hard gate, not a soft warning -- a silently dropped or
    silently duplicated pairing (e.g. a caller who forgot to classify one
    combination, or classified the same one twice) is exactly the class of
    bug this module exists to make impossible to ship unnoticed.
    """
    counts = {label.value: 0 for label in EvidenceLabel}
    for pairing in pairings:
        counts[pairing.evidence_label.value] += 1

    total = len(pairings)
    reconciled = sum(counts.values())
    if reconciled != total:
        raise AssertionError(
            "Evidence counts do not reconcile: "
            f"DIRECT({counts[EvidenceLabel.DIRECT.value]}) + "
            f"INDIRECT({counts[EvidenceLabel.INDIRECT.value]}) + "
            f"UNKNOWN({counts[EvidenceLabel.UNKNOWN.value]}) = {reconciled}, "
            f"expected {total} feasible pairings."
        )

    counts["total_feasible_pairings"] = total
    return counts
