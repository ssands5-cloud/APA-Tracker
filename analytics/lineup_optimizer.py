"""Lineup Optimizer.

Solves the assignment problem the Captain's Decision Engine explicitly did
not: which of my players should take which specific opponent, given that
each opponent can only be assigned to one of my players. The Decision Engine
ranks each player's best pairing independently, so two players could end up
recommended against the same opponent; this module finds the single
whole-lineup assignment that maximizes total score.

Purely derived and purely computational. It takes an already-built score
matrix and returns an assignment -- it queries no database and writes to no
table. Building that matrix (resolving rosters, pulling matchup_score /
win_probability / confidence / risk_factor) is scripts/build_lineups.py's
job, mirroring how analytics.captains_edge stays pure and
scripts/build_captains_edge.py does the querying.

Every input concept is real and already computed elsewhere:

    matchup_score    -> analytics.captains_edge.matchup_score (0..1)
    win_probability  -> player_h2h_advantage (0..1)
    confidence       -> analytics.captains_edge.confidence (player-level, 0..1)
    risk_factor      -> analytics.captains_edge.risk_factor (player-level, 0..1)

Full write-up: docs/lineup_optimizer.md
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

# --- objective weights (spec section 1.1) -----------------------------------
WEIGHT_MATCHUP_SCORE = 0.50
WEIGHT_WIN_PROBABILITY = 0.30
WEIGHT_CONFIDENCE = 0.15
WEIGHT_RISK_PENALTY = 0.05

# A missing input is treated as uninformative, not negative or positive.
NEUTRAL_DEFAULT = 0.5

# Exhaustive search is exact (never greedy) and trivially fast at the sizes
# this domain actually produces -- every real matchup checked was 3-5 players
# per side. This guards against a pathological input silently taking
# minutes: math.perm(larger, smaller) beyond this raises rather than hangs,
# because a roster that large would be a data anomaly worth surfacing, not
# something to solve approximately without saying so.
MAX_ASSIGNMENT_PERMUTATIONS = 500_000


def effective_confidence(confidence: Optional[float]) -> float:
    """ECi -- confidence, defaulted to neutral when missing (spec 4.1)."""
    return confidence if confidence is not None else NEUTRAL_DEFAULT


def effective_risk(risk_factor: Optional[float]) -> float:
    """ERi -- risk, defaulted to neutral when missing (spec 4.1)."""
    return risk_factor if risk_factor is not None else NEUTRAL_DEFAULT


def risk_penalty(risk_factor: Optional[float]) -> float:
    """RPi = 1 - ERi. Higher for a calmer player."""
    return 1.0 - effective_risk(risk_factor)


def pairing_score(matchup_score: Optional[float], win_probability: Optional[float],
                  confidence: Optional[float], risk_factor: Optional[float]) -> float:
    """Fij, the per-pairing objective score.

        Fij = 0.50*Sij + 0.30*Wij + 0.15*ECi + 0.05*RPi

    Every component defaults to neutral (0.5) independently when missing, per
    spec section 4: a pairing is NEVER excluded for lacking data. This always
    returns a float -- a pairing with no evidence at all still scores
    0.5*0.50 + 0.5*0.30 + 0.5*0.15 + 0.5*0.05 = 0.5, neither favoured nor
    penalised for being unknown.

    Note the asymmetry with display: this NEUTRAL-DEFAULTED value is for the
    optimizer's internal arithmetic only. The UI and Excel sheet show the
    RAW matchup_score / win_probability / confidence / risk_factor (or "No
    data"), never this filled-in 0.5 -- showing a fabricated neutral value as
    if it were a real measurement would violate this project's standing
    non-fabrication policy. See docs/lineup_optimizer.md.
    """
    Sij = matchup_score if matchup_score is not None else NEUTRAL_DEFAULT
    Wij = win_probability if win_probability is not None else NEUTRAL_DEFAULT
    ECi = effective_confidence(confidence)
    RPi = risk_penalty(risk_factor)
    return round(
        WEIGHT_MATCHUP_SCORE * Sij
        + WEIGHT_WIN_PROBABILITY * Wij
        + WEIGHT_CONFIDENCE * ECi
        + WEIGHT_RISK_PENALTY * RPi,
        6,
    )


@dataclass
class PairingCandidate:
    """One (my player, opponent) cell in the score matrix -- raw values for
    display, plus the computed Fij used for optimization."""

    player_id: str
    player_name: str
    opponent_id: str
    opponent_name: str
    matchup_score: Optional[float]
    win_probability: Optional[float]
    confidence: Optional[float]
    risk_factor: Optional[float]
    score: float = field(init=False)

    def __post_init__(self):
        self.score = pairing_score(
            self.matchup_score, self.win_probability, self.confidence, self.risk_factor
        )


@dataclass
class AssignmentEntry:
    """One player's slot in the solved lineup."""

    player_id: str
    player_name: str
    opponent_id: Optional[str]
    opponent_name: Optional[str]
    matchup_score: Optional[float]
    win_probability: Optional[float]
    confidence: Optional[float]
    risk_factor: Optional[float]
    final_score: Optional[float]
    lineup_rank: Optional[int]
    rationale: str


@dataclass
class LineupSolution:
    """The full solved lineup for one (my team, opponent team) matchup."""

    assignments: list[AssignmentEntry]
    unassigned_players: list[str]
    unassigned_opponents: list[str]
    objective_total: float
    total_risk: float
    total_confidence: float
    tie_break_applied: bool


def build_rationale(matchup_score: Optional[float], win_probability: Optional[float],
                    confidence: Optional[float], risk_factor: Optional[float]) -> str:
    """One short phrase naming the strongest signal(s) behind the pick.

    Mirrors analytics.captains_edge.build_rationale's honesty: says plainly
    when a signal is unknown rather than staying silent about it.
    """
    if matchup_score is None and win_probability is None:
        return "No matchup history - assignment based on default scoring."

    parts = []
    if win_probability is not None and win_probability >= 0.65:
        parts.append("high win probability")
    if confidence is not None and confidence >= 0.70:
        parts.append("strong recent form")
    elif confidence is None:
        parts.append("form unknown")
    if risk_factor is not None and risk_factor <= 0.15:
        parts.append("low risk")
    elif risk_factor is not None and risk_factor >= 0.50:
        parts.append("elevated risk")
    elif risk_factor is None:
        parts.append("stability unknown")

    if not parts:
        parts.append(f"matchup score {matchup_score if matchup_score is not None else 'unscored'}")

    return ", ".join(parts).capitalize() + "."


def _assignment_permutations(m: int, n: int):
    """Yield every valid injective (player_index -> opponent_index) mapping,
    as a tuple of (player_index, opponent_index) pairs.

    Always permutes the SMALLER side's assignment across the LARGER side's
    positions -- choosing r = min(m, n) distinct opponent (or player)
    indices in order -- which minimizes the permutation count without
    changing which assignments are considered.
    """
    r = min(m, n)
    if r == 0:
        return
    if m <= n:
        for combo in itertools.permutations(range(n), r):
            yield tuple(zip(range(m), combo))
    else:
        for combo in itertools.permutations(range(m), r):
            yield tuple(zip(combo, range(n)))


def solve_lineup_assignment(
    matrix: Sequence[Sequence[PairingCandidate]],
    players: Sequence[str],
    opponents: Sequence[str],
) -> LineupSolution:
    """Find the whole-lineup assignment that maximizes total Fij.

    `matrix[i][j]` is the PairingCandidate for players[i] vs opponents[j].
    `players`/`opponents` are display names, used only for the lexicographic
    tie-break and for reporting who is left unassigned.

    Exact by exhaustive search over every valid one-to-one assignment --
    "equivalent maximum-weight assignment" per spec section 2.2, and strictly
    exact rather than a heuristic. Chosen over implementing the Hungarian
    algorithm directly because it is simpler to prove correct, trivially
    supports the spec's exact 3-level tie-break by directly comparing whole
    candidate solutions, and every real matchup in this data is 3-5 players
    per side (see docs/lineup_optimizer.md for the size guard).

    Tie-break order (spec section 5), applied only among assignments tied on
    the level above:
      1. maximize Objective(A)              (the real optimization goal)
      2. minimize total risk  (sum of ERi over assigned players)
      3. maximize total confidence (sum of ECi over assigned players)
      4. lexicographically smallest sequence of (player_name, opponent_name),
         sorted by player_name -- guarantees a single deterministic answer
         even in the -- extremely unlikely -- case of a full 3-way tie.
    """
    m, n = len(players), len(opponents)
    if m == 0 or n == 0:
        return LineupSolution([], list(players), list(opponents), 0.0, 0.0, 0.0, False)

    r = min(m, n)
    larger = max(m, n)
    permutation_count = math.perm(larger, r)
    if permutation_count > MAX_ASSIGNMENT_PERMUTATIONS:
        raise ValueError(
            f"Lineup of {m} players vs {n} opponents needs {permutation_count:,} "
            f"assignments to check exhaustively, above the "
            f"{MAX_ASSIGNMENT_PERMUTATIONS:,} guard. This is a real limitation, "
            "not expected at APA roster sizes -- see docs/lineup_optimizer.md."
        )

    # Per-player effective confidence/risk are opponent-independent, so
    # compute them once rather than per candidate pairing.
    player_ec = [None] * m
    player_er = [None] * m
    for i in range(m):
        for j in range(n):
            if matrix[i][j] is not None:
                player_ec[i] = effective_confidence(matrix[i][j].confidence)
                player_er[i] = effective_risk(matrix[i][j].risk_factor)
                break
        else:
            player_ec[i] = NEUTRAL_DEFAULT
            player_er[i] = NEUTRAL_DEFAULT

    # Evaluate every candidate once, then pick the best by the exact 4-level
    # spec order -- objective desc, risk asc, confidence desc, lexicographic
    # asc. Doing this as "collect then min()" rather than a running-best
    # comparison makes tie counting a simple, separately-verifiable pass
    # over the same list, instead of state threaded through the scan.
    candidates = []
    for pairs in _assignment_permutations(m, n):
        objective = sum(matrix[i][j].score for i, j in pairs)
        total_risk = sum(player_er[i] for i, _ in pairs)
        total_confidence = sum(player_ec[i] for i, _ in pairs)
        lexicographic = tuple(sorted((players[i], opponents[j]) for i, j in pairs))
        key = (-round(objective, 6), round(total_risk, 6), -round(total_confidence, 6),
               lexicographic)
        candidates.append((key, pairs))

    best_key, best_pairs = min(candidates, key=lambda c: c[0])
    # A tie-break was exercised if more than one candidate shares the best
    # OBJECTIVE value -- meaning the primary criterion alone did not
    # determine the winner, and risk/confidence/lexicographic order decided
    # it instead.
    tie_count = sum(1 for key, _ in candidates if key[0] == best_key[0]) - 1

    assigned_players = {i for i, _ in best_pairs}
    assigned_opponents = {j for _, j in best_pairs}

    entries = []
    rank_order = sorted(best_pairs, key=lambda pair: -matrix[pair[0]][pair[1]].score)
    for rank, (i, j) in enumerate(rank_order, start=1):
        candidate = matrix[i][j]
        entries.append(AssignmentEntry(
            player_id=candidate.player_id,
            player_name=candidate.player_name,
            opponent_id=candidate.opponent_id,
            opponent_name=candidate.opponent_name,
            matchup_score=candidate.matchup_score,
            win_probability=candidate.win_probability,
            confidence=candidate.confidence,
            risk_factor=candidate.risk_factor,
            final_score=candidate.score,
            lineup_rank=rank,
            rationale=build_rationale(candidate.matchup_score, candidate.win_probability,
                                      candidate.confidence, candidate.risk_factor),
        ))

    objective_total = sum(matrix[i][j].score for i, j in best_pairs)
    total_risk = sum(player_er[i] for i in assigned_players)
    total_confidence = sum(player_ec[i] for i in assigned_players)

    return LineupSolution(
        assignments=entries,
        unassigned_players=[players[i] for i in range(m) if i not in assigned_players],
        unassigned_opponents=[opponents[j] for j in range(n) if j not in assigned_opponents],
        objective_total=round(objective_total, 6),
        total_risk=round(total_risk, 6),
        total_confidence=round(total_confidence, 6),
        tie_break_applied=tie_count > 0,
    )
