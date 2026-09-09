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

**What this module deliberately does NOT implement**: an earlier draft of
this feature (before the rule was verified) assumed additional
constraints -- "no more than two SL6+ players", "at least one SL3 or
below" -- that do not appear anywhere in APA's own published rule. Those
were a plausible-sounding but UNVERIFIED guess, exactly the kind of thing
this project's whole approach exists to catch before it ships as if
authoritative. They are not implemented here. If APA does publish such a
constraint somewhere this check hasn't found, it needs its own citation
before it's added -- not assumed because it sounded plausible.

**What this module also does not implement yet**: the 4-player/19 and
(per a secondary, less-directly-confirmed search result) a further
3-player/15 fallback for a team that cannot field 5 (or 4) legal players.
`TEAM_SKILL_LEVEL_LIMIT_4` is recorded as a real, sourced constant, but no
function here decides "should this team fall back to 4 players" -- that is
a captain decision (which player to sit, not just how many) genuinely
harder than the 5-player check, and is left for a follow-up with its own
tests once actually needed.

**Duplicate players**: APA's skill-level cap says nothing about player
identity, but a lineup that names the same real player in two slots isn't
a real lineup at all -- a person can't play two positions on their own
team's card in the same match. This was missed in an earlier pass (the
function only ever saw bare skill levels, with no identity to compare),
caught in a real review of that commit. Player identity is now a required
part of the input specifically so this can be checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

TEAM_SKILL_LEVEL_LIMIT_5 = 23
"""The 23-Rule's real cap for a standard 5-player lineup. Same for 8-Ball
Open and 9-Ball Open -- APA's rule does not vary the cap by format."""

TEAM_SKILL_LEVEL_LIMIT_4 = 19
"""The real fallback cap when a team cannot field 5 legal players: 4
players totalling this or less, forfeiting the 5th match. Recorded here
for documentation; not yet wired into a decision function -- see the
module docstring."""

LINEUP_SIZE = 5

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
