"""APA Team Skill Level Limit -- the real "23-Rule", verified against APA's
own published rules before any of this was written, not assumed from a
plausible-sounding name.

Source: APA's official rules site, "Team Skill Level Limit"
(https://rules.poolplayers.com/general-rules/team-skill-level-limit/),
fetched and checked against a second independent search result before
this module existed. Per that source: a standard 5-player lineup's
combined skill levels must not exceed 23 -- identical for 8-Ball Open and
9-Ball Open, not a different cap per format. A team unable to field 5
legal players may instead play 4 players totalling 19 or less and forfeit
the 5th match.

This module implements both paths. ``check_lineup_legality`` remains the
strict already-complete 5-player/23 verifier. ``legal_completion_exists``
remains the backwards-compatible live-planner question for the normal
5-player path. ``assess_completion_options`` adds the verified fallback:
it distinguishes a legal standard completion from the 4-player/19 path
that requires a forfeit, while preserving ``None`` whenever unknown skill
levels prevent an honest answer.

**What this module deliberately does NOT implement**: an earlier draft of
this feature (before the rule was verified) assumed additional
constraints -- "no more than two SL6+ players", "at least one SL3 or
below" -- that do not appear anywhere in APA's own published rule. Those
were a plausible-sounding but UNVERIFIED guess, exactly the kind of thing
this project's whole approach exists to catch before it ships as if
authoritative. They are not implemented here. If APA does publish such a
constraint somewhere this check hasn't found, it needs its own citation
before it's added -- not assumed because it sounded plausible.

**Duplicate players**: APA's skill-level cap says nothing about player
identity, but a lineup that names the same real player in two slots isn't
a real lineup at all -- a person can't play two positions on their own
team's card in the same match. This was missed in an earlier pass (the
function only ever saw bare skill levels, with no identity to compare),
caught in a real review of that commit. Player identity is now a required
part of the input specifically so this can be checked.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Optional, Sequence

TEAM_SKILL_LEVEL_LIMIT_5 = 23
"""The 23-Rule's real cap for a standard 5-player lineup. Same for 8-Ball
Open and 9-Ball Open -- APA's rule does not vary the cap by format."""

TEAM_SKILL_LEVEL_LIMIT_4 = 19
"""The verified fallback cap when a team cannot field 5 legal players:
4 players totalling this or less, with the 5th match forfeited."""

LINEUP_SIZE = 5
FALLBACK_LINEUP_SIZE = 4

LINEUP_LEGALITY_SOURCE_URL = "https://rules.poolplayers.com/general-rules/team-skill-level-limit/"


@dataclass(frozen=True)
class LineupLegality:
    skill_total: int
    limit: int
    is_legal: bool
    has_duplicate_players: bool
    """True when the same real player identity appears in more than one
    slot. A duplicate always makes `is_legal` False regardless of
    `skill_total` -- it isn't a real lineup to begin with, independent of
    the skill-level math."""


@dataclass(frozen=True)
class CompletionAssessment:
    """Tri-state assessment of the two verified APA completion paths.

    Each ``*_possible`` field is True/False when the available-player and
    skill-level facts are sufficient to decide that path, or None when
    unknown skill levels keep the answer genuinely unresolved.

    ``preferred_lineup_size`` is 5 whenever a normal legal completion is
    proven. It becomes 4 only when the 5-player path is proven impossible
    AND the 4-player/19 fallback is proven possible. We never recommend a
    forfeit merely because the 5-player path is uncertain.
    """

    standard_five_possible: Optional[bool]
    four_player_fallback_possible: Optional[bool]
    preferred_lineup_size: Optional[int]
    skill_limit: Optional[int]
    requires_forfeit: bool


def check_lineup_legality(
    players: Sequence[tuple[object, Optional[int]]]
) -> Optional[LineupLegality]:
    """The real 23-Rule check for a standard 5-player lineup, plus
    duplicate-player rejection.

    `players` is one `(player_id, skill_level)` pair per lineup slot.
    `player_id` just needs to be a stable real identifier for that player
    (an external id or an internal database id -- whichever the caller
    already has); it is only ever compared for equality, never displayed
    or interpreted.

    Returns None (never a guessed verdict) unless given exactly
    LINEUP_SIZE slots, each with both a real player id and a real skill
    level -- an incomplete or malformed lineup selection has no legality
    verdict, not a default "legal" or "illegal" one. Never silently treats
    a missing player's skill level as 0, which would understate the real
    total.

    A lineup that IS well-formed (5 real players, 5 real skill levels) but
    names the same player twice gets a real verdict, not None -- it's
    `is_legal=False` with `has_duplicate_players=True`, distinguishing
    "malformed/incomplete selection" from "well-formed but illegal because
    of a repeated player".
    """
    if len(players) != LINEUP_SIZE:
        return None
    if any(player_id is None or skill_level is None for player_id, skill_level in players):
        return None

    player_ids = [player_id for player_id, _ in players]
    has_duplicate_players = len(set(player_ids)) != len(player_ids)
    total = sum(skill_level for _, skill_level in players)
    return LineupLegality(
        skill_total=total,
        limit=TEAM_SKILL_LEVEL_LIMIT_5,
        is_legal=(total <= TEAM_SKILL_LEVEL_LIMIT_5) and not has_duplicate_players,
        has_duplicate_players=has_duplicate_players,
    )


# A real, small bound on the exact searches below -- same "exact or refuse,
# never approximate" posture as analytics.lineup_lab's own
# MAX_ASSIGNMENT_ATTEMPTS. A real team's own available roster is small, so
# this is generous while still preventing an accidental combinatorial hang.
MAX_COMPLETION_ATTEMPTS = 200_000


def _completion_exists_for_target(
    committed_skill_levels: Sequence[Optional[int]],
    available_skill_levels: Sequence[Optional[int]],
    *,
    target_size: int,
    skill_limit: int,
    insufficient_players_are_unknown: bool,
) -> Optional[bool]:
    """Exact tri-state completion check for one lineup size/limit pair."""
    if any(level is None for level in committed_skill_levels):
        return None
    if len(committed_skill_levels) > target_size:
        return False

    still_needed = target_size - len(committed_skill_levels)
    committed_total = sum(committed_skill_levels)
    if still_needed == 0:
        return committed_total <= skill_limit

    # Distinguish "not enough players exist" from "players exist but some
    # skill levels are unknown." The legacy 5-player wrapper preserves its
    # historical None behavior for the first case; the new fallback
    # assessment treats a complete pool with too few players as a proven
    # impossible path, which is what unlocks the verified 4-player rule.
    if len(available_skill_levels) < still_needed:
        return None if insufficient_players_are_unknown else False

    known = [level for level in available_skill_levels if level is not None]
    if len(known) < still_needed:
        return None

    attempts = 1
    for i in range(still_needed):
        attempts *= len(known) - i
    for j in range(1, still_needed + 1):
        attempts //= j
    if attempts > MAX_COMPLETION_ATTEMPTS:
        raise ValueError(
            f"Too many remaining available players ({len(known)}) to search "
            f"exactly for a {still_needed}-slot completion -- narrow "
            "tonight's availability before asking for this check."
        )

    remaining_cap = skill_limit - committed_total
    return any(
        sum(combo) <= remaining_cap
        for combo in itertools.combinations(known, still_needed)
    )


def legal_completion_exists(
    committed_skill_levels: Sequence[Optional[int]],
    available_skill_levels: Sequence[Optional[int]],
) -> Optional[bool]:
    """Whether a legal standard 5-player lineup can still be completed.

    This retains the original live-planner contract. ``None`` means the
    normal 5-player answer cannot be verified from the supplied skill-level
    facts; callers that need the verified 4-player/19 fallback should use
    ``assess_completion_options`` instead.
    """
    if len(committed_skill_levels) > LINEUP_SIZE:
        return None
    return _completion_exists_for_target(
        committed_skill_levels,
        available_skill_levels,
        target_size=LINEUP_SIZE,
        skill_limit=TEAM_SKILL_LEVEL_LIMIT_5,
        insufficient_players_are_unknown=True,
    )


def assess_completion_options(
    committed_skill_levels: Sequence[Optional[int]],
    available_skill_levels: Sequence[Optional[int]],
) -> Optional[CompletionAssessment]:
    """Assess both verified APA lineup paths for a live Match Night state.

    The supplied available list is treated as the complete remaining pool.
    Therefore, if there are literally fewer players left than needed for a
    5-player lineup, the standard path is proven impossible rather than
    unknown. A player whose skill level is unknown must still appear as
    ``None``; that produces the honest tri-state ``None`` for any path whose
    legality depends on that missing value.

    The 4-player path is considered only as a fallback. It may be reported
    possible alongside a possible 5-player path, but ``preferred_lineup_size``
    remains 5. It becomes 4 only when five is proven impossible and four is
    proven legal, because the four-player path requires forfeiting match 5.
    """
    if len(committed_skill_levels) > LINEUP_SIZE:
        return None
    if any(level is None for level in committed_skill_levels):
        return None

    standard = _completion_exists_for_target(
        committed_skill_levels,
        available_skill_levels,
        target_size=LINEUP_SIZE,
        skill_limit=TEAM_SKILL_LEVEL_LIMIT_5,
        insufficient_players_are_unknown=False,
    )

    fallback = _completion_exists_for_target(
        committed_skill_levels,
        available_skill_levels,
        target_size=FALLBACK_LINEUP_SIZE,
        skill_limit=TEAM_SKILL_LEVEL_LIMIT_4,
        insufficient_players_are_unknown=False,
    )

    preferred_lineup_size: Optional[int] = None
    skill_limit: Optional[int] = None
    requires_forfeit = False

    if standard is True:
        preferred_lineup_size = LINEUP_SIZE
        skill_limit = TEAM_SKILL_LEVEL_LIMIT_5
    elif standard is False and fallback is True:
        preferred_lineup_size = FALLBACK_LINEUP_SIZE
        skill_limit = TEAM_SKILL_LEVEL_LIMIT_4
        requires_forfeit = True

    return CompletionAssessment(
        standard_five_possible=standard,
        four_player_fallback_possible=fallback,
        preferred_lineup_size=preferred_lineup_size,
        skill_limit=skill_limit,
        requires_forfeit=requires_forfeit,
    )
