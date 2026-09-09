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


@dataclass(frozen=True)
class LineupLegality:
    skill_total: int
    limit: int
    is_legal: bool


def check_lineup_legality(skill_levels: Sequence[Optional[int]]) -> Optional[LineupLegality]:
    """The real 23-Rule check for a standard 5-player lineup.

    None (not a guessed answer) when `skill_levels` isn't exactly
    LINEUP_SIZE real, non-null values -- an incomplete or malformed
    lineup selection has no legality verdict, not a default "legal" or
    "illegal" one. Never silently treats a missing player's skill level
    as 0, which would understate the real total.
    """
    if len(skill_levels) != LINEUP_SIZE:
        return None
    if any(level is None for level in skill_levels):
        return None
    total = sum(skill_levels)
    return LineupLegality(
        skill_total=total,
        limit=TEAM_SKILL_LEVEL_LIMIT_5,
        is_legal=total <= TEAM_SKILL_LEVEL_LIMIT_5,
    )
