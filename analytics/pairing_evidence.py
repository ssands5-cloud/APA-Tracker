"""Fail-closed evidence classification for the captain-first matrix.

The production entry point is :func:`build_pairing_evidence_matrix`. It
owns roster identity and database scoping end to end: immutable APA team
ids, an explicit session and format, finalized/scored/non-bye matches, and
the exact target opponent. Callers cannot hand the classifier a bag of
unverified rows.

Labels have deliberately narrow meanings:

``DIRECT``
    At least one distinct authoritative match contains a recognized W/L
    result for the exact player/opponent pair in the requested scope.
``INDIRECT``
    No DIRECT evidence exists, but both canonical current-roster rows carry
    real skill levels, so the already validated skill-gap-only model in
    :mod:`analytics.head_to_head` can produce a probability.
``UNKNOWN``
    Neither condition holds. No 0%, 50%, neutral score, or same-skill-level
    proxy is substituted.

The failed ``analytics.win_probability`` WR_SL/logistic stack is never
imported or consulted here.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Collection, Optional, Sequence

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from analytics.head_to_head import skill_only_win_probability, win_probability
from database.models import Match, PlayerHeadToHead, PlayerTeamHistory
from database.queries import canonical_current_roster


class EvidenceLabel(str, Enum):
    DIRECT = "DIRECT"
    INDIRECT = "INDIRECT"
    UNKNOWN = "UNKNOWN"


class PairingEvidenceError(RuntimeError):
    """Evidence could not be classified without guessing."""


class PairingReconciliationError(AssertionError):
    """The classified matrix differs from the exact feasible-pair set."""


@dataclass(frozen=True)
class PairingEvidence:
    player_id: int
    player_external_id: str
    player_name: str
    player_skill_level: Optional[int]
    opponent_id: int
    opponent_external_id: str
    opponent_name: str
    opponent_skill_level: Optional[int]
    format: str
    session_name: str
    evidence_label: EvidenceLabel
    observed_win_rate: Optional[float]
    direct_evidence_count: int
    modeled_win_probability: Optional[float]
    model_source: Optional[str]


@dataclass(frozen=True)
class PairingEvidenceMatrix:
    our_team_external_id: str
    opponent_team_external_id: str
    format: str
    session_name: str
    expected_pairings: tuple[tuple[int, int], ...]
    pairings: tuple[PairingEvidence, ...]
    counts: dict[str, int]
    our_roster_available: bool
    opponent_roster_available: bool


def _scope_value(name: str, value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    return normalized


def feasible_pairings(
    our_player_ids: Sequence[int],
    opponent_player_ids: Sequence[int],
    unavailable_our_player_ids: Optional[Collection[int]] = None,
    unavailable_opponent_player_ids: Optional[Collection[int]] = None,
) -> list[tuple[int, int]]:
    """Return the exact cross-product after side-specific availability.

    The two unavailable sets are intentionally separate. A value selected
    on our side can never suppress the same value in an opponent-side id
    space. Duplicate roster ids collapse deterministically before the
    product is formed; the canonical roster query separately rejects
    duplicate membership rows instead of hiding them here.
    """
    unavailable_ours = set(unavailable_our_player_ids or ())
    unavailable_theirs = set(unavailable_opponent_player_ids or ())
    ours = [
        player_id
        for player_id in dict.fromkeys(our_player_ids)
        if player_id not in unavailable_ours
    ]
    theirs = [
        player_id
        for player_id in dict.fromkeys(opponent_player_ids)
        if player_id not in unavailable_theirs
    ]
    return [
        (player_id, opponent_id)
        for player_id in ours
        for opponent_id in theirs
    ]


def build_pairing_matrix(
    pairings: Sequence[PairingEvidence],
    expected_pairings: Sequence[tuple[int, int]],
) -> dict[str, int]:
    """Reconcile classifications against the independently derived set.

    Equality of totals is insufficient: one duplicate plus one omission can
    keep the arithmetic balanced. This gate therefore rejects duplicate
    expected keys, duplicate classified keys, missing keys, and unexpected
    keys before returning label counts.
    """
    expected = list(expected_pairings)
    expected_counts = Counter(expected)
    duplicate_expected = sorted(
        key for key, count in expected_counts.items() if count > 1
    )

    actual = [(row.player_id, row.opponent_id) for row in pairings]
    actual_counts = Counter(actual)
    duplicate_actual = sorted(
        key for key, count in actual_counts.items() if count > 1
    )

    expected_set = set(expected)
    actual_set = set(actual)
    missing = sorted(expected_set - actual_set)
    unexpected = sorted(actual_set - expected_set)
    if duplicate_expected or duplicate_actual or missing or unexpected:
        details = []
        if duplicate_expected:
            details.append(f"duplicate expected keys={duplicate_expected}")
        if duplicate_actual:
            details.append(f"duplicate classified keys={duplicate_actual}")
        if missing:
            details.append(f"missing keys={missing}")
        if unexpected:
            details.append(f"unexpected keys={unexpected}")
        raise PairingReconciliationError(
            "Pairing matrix does not match the feasible-pair set: "
            + "; ".join(details)
        )

    counts = {label.value: 0 for label in EvidenceLabel}
    for pairing in pairings:
        counts[pairing.evidence_label.value] += 1
    counts["total_feasible_pairings"] = len(expected)
    return counts


def _authoritative_direct_rows(
    db: Session,
    *,
    player_id: int,
    opponent_id: int,
    our_team_external_id: str,
    opponent_team_external_id: str,
    format: str,
    session_name: str,
) -> list[PlayerHeadToHead]:
    """Fetch exact-pair evidence from authoritative, matching match rows."""
    rows = (
        db.query(PlayerHeadToHead)
        .join(Match, PlayerHeadToHead.match_id == Match.id)
        .filter(
            PlayerHeadToHead.player_id == player_id,
            PlayerHeadToHead.opponent_id == opponent_id,
            PlayerHeadToHead.format == format,
            PlayerHeadToHead.session_name == session_name,
            PlayerHeadToHead.result.in_(("W", "L")),
            Match.format == format,
            Match.session_name == session_name,
            Match.is_scored.is_(True),
            Match.is_finalized.is_(True),
            Match.is_bye.is_(False),
            or_(
                and_(
                    Match.home_team_id == our_team_external_id,
                    Match.away_team_id == opponent_team_external_id,
                ),
                and_(
                    Match.home_team_id == opponent_team_external_id,
                    Match.away_team_id == our_team_external_id,
                ),
            ),
        )
        .order_by(Match.match_date, PlayerHeadToHead.match_id, PlayerHeadToHead.id)
        .all()
    )
    return _one_row_per_distinct_match(rows, player_id, opponent_id)


def _one_row_per_distinct_match(
    rows: Sequence[PlayerHeadToHead],
    player_id: int,
    opponent_id: int,
) -> list[PlayerHeadToHead]:
    """Collapse exact duplicates, rejecting conflicting evidence per match."""
    by_match: dict[int, list[PlayerHeadToHead]] = defaultdict(list)
    for row in rows:
        by_match[row.match_id].append(row)

    distinct: list[PlayerHeadToHead] = []
    for match_id, match_rows in by_match.items():
        facts = {
            (row.result, row.own_skill_level, row.opponent_skill_level)
            for row in match_rows
        }
        if len(facts) > 1:
            raise PairingEvidenceError(
                "Conflicting head-to-head evidence exists for one distinct "
                f"match: player={player_id}, opponent={opponent_id}, "
                f"match={match_id}"
            )
        distinct.append(match_rows[0])
    return distinct


def _observed_win_rate(rows: Sequence[PlayerHeadToHead]) -> Optional[float]:
    if not rows:
        return None
    wins = sum(1 for row in rows if row.result == "W")
    return round(wins / len(rows), 3)


def _classify_pairing(
    db: Session,
    *,
    player: PlayerTeamHistory,
    opponent: PlayerTeamHistory,
    our_team_external_id: str,
    opponent_team_external_id: str,
    format: str,
    session_name: str,
) -> PairingEvidence:
    if player.player is None or opponent.player is None:
        raise PairingEvidenceError("A canonical roster row has no Player identity")

    direct_rows = _authoritative_direct_rows(
        db,
        player_id=player.player_id,
        opponent_id=opponent.player_id,
        our_team_external_id=our_team_external_id,
        opponent_team_external_id=opponent_team_external_id,
        format=format,
        session_name=session_name,
    )
    if direct_rows:
        label = EvidenceLabel.DIRECT
        observed = _observed_win_rate(direct_rows)
        modeled = win_probability(direct_rows)
        model_source = "analytics.head_to_head:direct-history-and-skill"
    else:
        observed = None
        modeled = skill_only_win_probability(
            player.skill_level,
            opponent.skill_level,
        )
        if modeled is None:
            label = EvidenceLabel.UNKNOWN
            model_source = None
        else:
            label = EvidenceLabel.INDIRECT
            model_source = "analytics.head_to_head:validated-skill-only"

    return PairingEvidence(
        player_id=player.player_id,
        player_external_id=player.player.external_id,
        player_name=player.player.name,
        player_skill_level=player.skill_level,
        opponent_id=opponent.player_id,
        opponent_external_id=opponent.player.external_id,
        opponent_name=opponent.player.name,
        opponent_skill_level=opponent.skill_level,
        format=format,
        session_name=session_name,
        evidence_label=label,
        observed_win_rate=observed,
        direct_evidence_count=len(direct_rows),
        modeled_win_probability=modeled,
        model_source=model_source,
    )


def _validate_unavailable_ids(
    unavailable_ids: set[int],
    roster: Sequence[PlayerTeamHistory],
    side: str,
) -> None:
    roster_ids = {row.player_id for row in roster}
    unknown = sorted(unavailable_ids - roster_ids)
    if unknown:
        raise PairingEvidenceError(
            f"Unavailable {side} player ids are not in the canonical roster: {unknown}"
        )


def build_pairing_evidence_matrix(
    db: Session,
    *,
    our_team_external_id: str,
    opponent_team_external_id: str,
    format: str,
    session_name: str,
    unavailable_our_player_ids: Optional[Collection[int]] = None,
    unavailable_opponent_player_ids: Optional[Collection[int]] = None,
) -> PairingEvidenceMatrix:
    """Build and reconcile one fully scoped, production-owned matrix."""
    our_team_external_id = _scope_value(
        "our_team_external_id", our_team_external_id
    )
    opponent_team_external_id = _scope_value(
        "opponent_team_external_id", opponent_team_external_id
    )
    format = _scope_value("format", format)
    session_name = _scope_value("session_name", session_name)
    if our_team_external_id == opponent_team_external_id:
        raise PairingEvidenceError("Our team and opponent team must be different")

    our_roster = canonical_current_roster(
        db, our_team_external_id, session_name
    )
    opponent_roster = canonical_current_roster(
        db, opponent_team_external_id, session_name
    )

    overlap = sorted(
        {row.player_id for row in our_roster}
        & {row.player_id for row in opponent_roster}
    )
    if overlap:
        raise PairingEvidenceError(
            "The same canonical player is current on both selected teams: "
            + ", ".join(str(player_id) for player_id in overlap)
        )

    unavailable_ours = set(unavailable_our_player_ids or ())
    unavailable_theirs = set(unavailable_opponent_player_ids or ())
    _validate_unavailable_ids(unavailable_ours, our_roster, "our")
    _validate_unavailable_ids(unavailable_theirs, opponent_roster, "opponent")

    expected = feasible_pairings(
        [row.player_id for row in our_roster],
        [row.player_id for row in opponent_roster],
        unavailable_our_player_ids=unavailable_ours,
        unavailable_opponent_player_ids=unavailable_theirs,
    )
    ours_by_id = {row.player_id: row for row in our_roster}
    theirs_by_id = {row.player_id: row for row in opponent_roster}
    classified = [
        _classify_pairing(
            db,
            player=ours_by_id[player_id],
            opponent=theirs_by_id[opponent_id],
            our_team_external_id=our_team_external_id,
            opponent_team_external_id=opponent_team_external_id,
            format=format,
            session_name=session_name,
        )
        for player_id, opponent_id in expected
    ]
    counts = build_pairing_matrix(classified, expected)
    return PairingEvidenceMatrix(
        our_team_external_id=our_team_external_id,
        opponent_team_external_id=opponent_team_external_id,
        format=format,
        session_name=session_name,
        expected_pairings=tuple(expected),
        pairings=tuple(classified),
        counts=counts,
        our_roster_available=bool(our_roster),
        opponent_roster_available=bool(opponent_roster),
    )
