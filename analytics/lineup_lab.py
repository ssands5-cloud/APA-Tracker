"""Lineup Lab: the "approved best lineup" assignment for Stage 3 of
docs/captain_first_edge_experience.md.

The scoring formula and the assignment rule are both specified, with
worked examples and edge cases, in
docs/stage3_lineup_lab_scoring.md (posted to Issue #14 before this module
was written, per §10 of the governing spec). This module is the
implementation of that document and nothing else -- it introduces no
threshold, weight, or heuristic beyond what that document already states.

Deliberately NOT built on analytics.lineup_optimizer: that module's
``pairing_score`` defaults every missing input (including a missing
``modeled_win_probability``) to a neutral 0.5, which would let an UNKNOWN
pairing compete for -- and potentially win -- a lineup slot on a fabricated
value. See docs/stage3_lineup_lab_scoring.md §6.1 for the full reasoning.

Purely derived and purely computational, the same split every analytics
module in this project uses: takes a real, already-classified
``analytics.pairing_evidence.PairingEvidenceMatrix`` as input and queries
nothing itself.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Optional

from analytics.lineup_legality import LINEUP_SIZE, check_lineup_legality
from analytics.pairing_evidence import EvidenceLabel, PairingEvidence, PairingEvidenceMatrix

# Same real cap, same real reason, as analytics.lineup_optimizer's own
# MAX_ASSIGNMENT_PERMUTATIONS: an exact search that would take an
# unreasonable amount of time is a data anomaly worth surfacing (narrow
# tonight's availability), not something to solve approximately without
# saying so. See docs/stage3_lineup_lab_scoring.md §6.4 for the real
# 13-player-roster example this bound is sized against.
MAX_ASSIGNMENT_ATTEMPTS = 500_000


class LineupLabError(RuntimeError):
    """The Lineup Lab could not compute a result without guessing or
    exceeding its bounded search."""


@dataclass(frozen=True)
class LineupSlot:
    """One real, scoreable pairing chosen for the approved lineup."""

    player_id: int
    player_name: str
    player_skill_level: Optional[int]
    opponent_id: int
    opponent_name: str
    opponent_skill_level: Optional[int]
    evidence_label: EvidenceLabel
    observed_win_rate: Optional[float]
    direct_evidence_count: int
    modeled_win_probability: float
    model_source: str


@dataclass(frozen=True)
class UnmatchedPlayer:
    player_id: int
    player_name: str


@dataclass(frozen=True)
class UnmatchedOpponent:
    opponent_id: int
    opponent_name: str


@dataclass(frozen=True)
class LineupLabResult:
    """The full result of one Lineup Lab computation.

    ``is_legal`` is ``True``/``False`` only when the chosen assignment has
    exactly ``LINEUP_SIZE`` slots AND every chosen player/opponent has a
    real current skill level to check; ``None`` means legality could not be
    evaluated (a partial lineup, or a missing current skill level) -- never
    a guessed verdict.

    ``blocked_reason`` is set, and ``assignments`` may still be populated
    for transparency, when no fully approved result exists (see
    docs/stage3_lineup_lab_scoring.md §6.3 step 5).
    """

    assignments: tuple[LineupSlot, ...]
    unassigned_players: tuple[UnmatchedPlayer, ...]
    unassigned_opponents: tuple[UnmatchedOpponent, ...]
    total_score: Optional[float]
    skill_total: Optional[int]
    is_legal: Optional[bool]
    blocked_reason: Optional[str]


def pairing_score(pairing: PairingEvidence) -> Optional[float]:
    """The Stage 3 score: analytics.pairing_evidence's own
    ``modeled_win_probability``, unchanged. ``None`` for UNKNOWN --
    Stage 1's own classifier already guarantees ``modeled_win_probability``
    is ``None`` exactly when ``evidence_label`` is UNKNOWN and populated
    otherwise; this function names that invariant rather than
    re-implementing it. See docs/stage3_lineup_lab_scoring.md §2.
    """
    if pairing.evidence_label is EvidenceLabel.UNKNOWN:
        assert pairing.modeled_win_probability is None
        return None
    assert pairing.modeled_win_probability is not None
    return pairing.modeled_win_probability


def _attempt_count(our_count: int, opp_count: int, size: int) -> int:
    if size == 0:
        return 1
    if our_count < size or opp_count < size:
        return 0
    return math.comb(our_count, size) * math.perm(opp_count, size)


def _best_matching(
    our_ids: list[int],
    opp_ids: list[int],
    score_by_pair: dict[tuple[int, int], float],
    size: int,
    legal_pairs: Optional[set[tuple[int, int]]] = None,
) -> Optional[tuple[tuple[tuple[int, int], ...], float]]:
    """The highest-total-score matching of exactly ``size`` scoreable edges,
    or ``None`` when no such matching exists.

    ``legal_pairs``, when given, restricts candidate edges to that set (used
    for the "search only among legal 5-matchings" fallback in
    docs/stage3_lineup_lab_scoring.md §6.3 step 5) -- the score itself is
    unaffected; this only prunes which combinations are considered.

    Exact and exhaustive, bounded by MAX_ASSIGNMENT_ATTEMPTS at the call
    site (see ``solve``), the same "exact or refuse, never approximate"
    posture analytics.lineup_optimizer already established.
    """
    if size == 0:
        return ((), 0.0)

    best: Optional[tuple[tuple[tuple[int, int], ...], float]] = None
    for our_subset in itertools.combinations(our_ids, size):
        for opp_perm in itertools.permutations(opp_ids, size):
            assignment = tuple(zip(our_subset, opp_perm))
            total = 0.0
            valid = True
            for pair in assignment:
                if legal_pairs is not None and pair not in legal_pairs:
                    valid = False
                    break
                score = score_by_pair.get(pair)
                if score is None:
                    valid = False
                    break
                total += score
            if not valid:
                continue
            if best is None or total > best[1]:
                best = (assignment, total)
    return best


def solve(matrix: PairingEvidenceMatrix) -> LineupLabResult:
    """Compute the approved best lineup for one real, already-classified
    evidence matrix. See docs/stage3_lineup_lab_scoring.md §6.3 for the
    exact algorithm this implements.
    """
    by_pair: dict[tuple[int, int], PairingEvidence] = {
        (p.player_id, p.opponent_id): p for p in matrix.pairings
    }
    score_by_pair: dict[tuple[int, int], float] = {}
    for key, pairing in by_pair.items():
        score = pairing_score(pairing)
        if score is not None:
            score_by_pair[key] = score

    our_ids = sorted({p.player_id for p in matrix.pairings})
    opp_ids = sorted({p.opponent_id for p in matrix.pairings})
    names_by_player = {p.player_id: p.player_name for p in matrix.pairings}
    names_by_opponent = {p.opponent_id: p.opponent_name for p in matrix.pairings}

    target_size = min(LINEUP_SIZE, len(our_ids), len(opp_ids))
    if _attempt_count(len(our_ids), len(opp_ids), target_size) > MAX_ASSIGNMENT_ATTEMPTS:
        raise LineupLabError(
            f"Too many available players/opponents to search exactly "
            f"({len(our_ids)} of ours, {len(opp_ids)} identified) -- narrow "
            "tonight's availability before requesting the approved lineup."
        )

    # Largest matching size, using only scoreable edges, up to LINEUP_SIZE.
    chosen_size = 0
    best = None
    for size in range(target_size, -1, -1):
        candidate = _best_matching(our_ids, opp_ids, score_by_pair, size)
        if candidate is not None:
            chosen_size = size
            best = candidate
            break

    def _unassigned(assignment: tuple[tuple[int, int], ...]) -> LineupLabResult:
        used_players = {p for p, _ in assignment}
        used_opponents = {o for _, o in assignment}
        return (
            tuple(UnmatchedPlayer(pid, names_by_player[pid])
                  for pid in our_ids if pid not in used_players),
            tuple(UnmatchedOpponent(oid, names_by_opponent[oid])
                  for oid in opp_ids if oid not in used_opponents),
        )

    def _slots(assignment: tuple[tuple[int, int], ...]) -> tuple[LineupSlot, ...]:
        slots = []
        for pid, oid in assignment:
            pairing = by_pair[(pid, oid)]
            slots.append(LineupSlot(
                player_id=pid, player_name=pairing.player_name,
                player_skill_level=pairing.player_skill_level,
                opponent_id=oid, opponent_name=pairing.opponent_name,
                opponent_skill_level=pairing.opponent_skill_level,
                evidence_label=pairing.evidence_label,
                observed_win_rate=pairing.observed_win_rate,
                direct_evidence_count=pairing.direct_evidence_count,
                modeled_win_probability=pairing.modeled_win_probability,
                model_source=pairing.model_source,
            ))
        return tuple(slots)

    if best is None or chosen_size == 0:
        return LineupLabResult(
            assignments=(), unassigned_players=tuple(
                UnmatchedPlayer(pid, names_by_player[pid]) for pid in our_ids
            ),
            unassigned_opponents=tuple(
                UnmatchedOpponent(oid, names_by_opponent[oid]) for oid in opp_ids
            ),
            total_score=None, skill_total=None, is_legal=None,
            blocked_reason="No scoreable (DIRECT or INDIRECT) pairing exists "
                            "for any available player against any identified opponent.",
        )

    assignment, total_score = best
    unassigned_players, unassigned_opponents = _unassigned(assignment)

    if chosen_size < LINEUP_SIZE:
        return LineupLabResult(
            assignments=_slots(assignment),
            unassigned_players=unassigned_players,
            unassigned_opponents=unassigned_opponents,
            total_score=total_score, skill_total=None, is_legal=None,
            blocked_reason=(
                f"Only {chosen_size} of {LINEUP_SIZE} positions could be filled "
                "from approved evidence -- not enough scoreable pairings exist "
                "for a complete lineup."
            ),
        )

    def _legality_for(assignment) -> Optional["LineupLegality"]:  # noqa: F821
        slots = []
        for pid, oid in assignment:
            pairing = by_pair[(pid, oid)]
            if pairing.player_skill_level is None or pairing.opponent_skill_level is None:
                return None
            slots.append((pid, pairing.player_skill_level))
        return check_lineup_legality(slots)

    legality = _legality_for(assignment)
    if legality is None or legality.is_legal:
        return LineupLabResult(
            assignments=_slots(assignment),
            unassigned_players=unassigned_players,
            unassigned_opponents=unassigned_opponents,
            total_score=total_score,
            skill_total=legality.skill_total if legality else None,
            is_legal=legality.is_legal if legality else None,
            blocked_reason=None,
        )

    # The unconstrained best 5-matching is illegal -- search again, this
    # time restricted to pairs whose OWN skill level is known (needed for
    # any legality verdict at all), trying every legal 5-subset+assignment
    # for the best-scoring one that passes check_lineup_legality.
    legal_best = None
    for our_subset in itertools.combinations(our_ids, LINEUP_SIZE):
        for opp_perm in itertools.permutations(opp_ids, LINEUP_SIZE):
            candidate = tuple(zip(our_subset, opp_perm))
            scores = []
            slots = []
            ok = True
            for pid, oid in candidate:
                score = score_by_pair.get((pid, oid))
                pairing = by_pair.get((pid, oid))
                if score is None or pairing is None or pairing.player_skill_level is None:
                    ok = False
                    break
                scores.append(score)
                slots.append((pid, pairing.player_skill_level))
            if not ok:
                continue
            verdict = check_lineup_legality(slots)
            if verdict is None or not verdict.is_legal:
                continue
            total = sum(scores)
            if legal_best is None or total > legal_best[1]:
                legal_best = (candidate, total, verdict)

    if legal_best is None:
        return LineupLabResult(
            assignments=_slots(assignment),
            unassigned_players=unassigned_players,
            unassigned_opponents=unassigned_opponents,
            total_score=total_score,
            skill_total=legality.skill_total,
            is_legal=False,
            blocked_reason=(
                "No legal 5-player lineup exists using only approved evidence; "
                f"the highest-scoring scoreable assignment (shown) totals skill "
                f"level {legality.skill_total}, exceeding the real "
                f"{legality.limit} limit."
            ),
        )

    legal_assignment, legal_total, legal_verdict = legal_best
    unassigned_players, unassigned_opponents = _unassigned(legal_assignment)
    return LineupLabResult(
        assignments=_slots(legal_assignment),
        unassigned_players=unassigned_players,
        unassigned_opponents=unassigned_opponents,
        total_score=legal_total,
        skill_total=legal_verdict.skill_total,
        is_legal=True,
        blocked_reason=None,
    )
