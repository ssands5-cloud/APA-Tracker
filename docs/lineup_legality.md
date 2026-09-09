# APA Team Skill Level Limit ("the 23-Rule")

Verified against APA's own published rules before this was written, not
assumed from a plausible-sounding name — see
[rules.poolplayers.com/general-rules/team-skill-level-limit](https://rules.poolplayers.com/general-rules/team-skill-level-limit/).

```
analytics/lineup_legality.py   check_lineup_legality()
```

## The real rule

A standard 5-player lineup's combined skill levels must not exceed **23**.
The same cap applies to both 8-Ball Open and 9-Ball Open — APA's rule does
not vary the number by format. A team unable to field 5 legal players may
instead play 4 players totalling **19** or less, forfeiting the 5th match.

## What an earlier draft got wrong

Before this rule was looked up, a draft spec for this feature assumed two
additional constraints: "no more than two SL6+ players" and "at least one
SL3 or below". **Neither appears in APA's actual published rule.** They
were a plausible-sounding guess — the exact kind of unverified claim this
project's whole approach exists to catch before it ships as if
authoritative. They are not implemented, and should not be added back
without their own citation, if APA turns out to publish something like
them somewhere this check didn't find.

## What's implemented

`check_lineup_legality(skill_levels)` — the 5-player, 23-cap case only.
Returns `None` (never a guessed answer) unless given exactly 5 real,
non-null skill levels: an incomplete lineup selection has no legality
verdict, and a missing skill level is never treated as 0, which would
understate the real total and could call an actually-illegal lineup legal.

## What's recorded but not decided yet

`TEAM_SKILL_LEVEL_LIMIT_4 = 19` is a real, sourced constant for the
4-player fallback, but no function here decides *when* a team should fall
back to 4 (or a further 3-player/15 tier a secondary source mentioned less
directly) — that's a captain decision about *which* player to sit, a
harder question than the 5-player total check, and is left for its own
pass with its own tests once a real feature (Lineup Simulator, Next_Match)
actually needs it.
