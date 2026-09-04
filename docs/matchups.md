# Matchup Advantage Engine

Gives a captain a per-opponent read on each player: real head-to-head
record, how it's trending, and a single 0-100 score to sort by when
setting a lineup.

## Where it comes from

No new query, no new scrape. A team match's `MatchPage` already returns,
per individual game, `matchPositionNumber`/`playerPosition` on both the
home and away side. Standard APA team format plays same-numbered positions
against each other (position 1 home vs. position 1 away, and so on), so
pairing those rows tells you exactly who played whom — not just which two
teams faced off.

- `scraper/graphql_scraper.py::head_to_head_rows(match)` does the pairing,
  from real captured field names — see its docstring and
  `database/models.py`'s `PlayerHeadToHead` for why this is reading a
  documented field, not guessing at an ambiguous id the way the career-stats
  alias id was.
- `database/ingest.py::ingest_head_to_head()` writes one raw row per
  (player, match) into `player_head_to_head` — both directions of a
  pairing, since each side has its own result/points/skill level.
- `scripts/build_matchups.py` groups those raw rows by (player, opponent),
  scores each pair (`analytics/matchups.py`), and upserts the aggregate
  into `player_matchups`. Run it any time after a sync or the demo build
  has produced head-to-head rows — it never touches the network itself.
  `scripts/build_demo.py` also calls it directly so the demo/Excel/JSON
  outputs always include real matchup data, not a separate manual step.

## How the score is computed

`analytics/matchups.py::matchup_score(rows, trend, volatility)`:

```
score = 50
       + (win_rate - 0.5) * 80      # the real head-to-head record: ±40 swing
       + trend_modifier(trend)      # +5 up / -5 down / 0 stable or no data
       - volatility_penalty(vol)    # 3 points per real change, capped at 15
clamped to [0, 100]
```

- **Win rate** is the actual won/lost record against *that specific*
  opponent (from `player_head_to_head`), not a season-wide average.
- **Trend** and **volatility** are about the *player*, not the pair — the
  same signal the Skill Level tab shows (`analytics/skill_level_trends.py`),
  reused here rather than recomputed. A player trending up gets a small
  boost across every matchup; one whose skill level keeps bouncing around
  gets a small penalty across every matchup.
- **`avg_opponent_skill_level`** is reported next to the score, not folded
  into it. APA's own point-per-skill-level handicap already compensates for
  a skill gap in the scoring itself; adding a second, unverified adjustment
  on top risked double-counting a correction the league already makes. Use
  it as context for your own judgment, not as a hidden factor in the number.
- **No history yet** → score is `50` (neutral), not a guess in either
  direction.

## Two things this deliberately doesn't include

The original spec for this feature asked for "average innings" and
"defensive shots vs. each opponent." Neither is a real field:

- **Innings** has never appeared in any query this API returns (checked
  every captured operation in `parser/apa_graphql.py`) — not an APA
  8-ball/9-ball stat this app has ever seen.
- **Defensive shot average** only exists as a career-wide number
  (`PlayerCareerStats.defensive_shot_avg`, from `getEightBallStats`), never
  per-opponent — there's nothing to average per matchup.

Rather than invent numbers for either, `avg_points_earned` and
`avg_opponent_skill_level` stand in: real, per-opponent, and actually
present in the data.

## A known limitation, inherited rather than new

Opponent identity here relies on the same `member`/roster id resolution
used everywhere else in this app. A real person who ends up mapped to two
different ids (a gap flagged, but not yet confirmed, in
`docs/graphql-captures/*/HANDOFF.md`) will show up as two separate,
incomplete opponents here rather than one merged one — smaller sample
sizes, not wrong numbers. This isn't a new bug from the Matchup Advantage
Engine; it's the same open question this project has already been
tracking, just now visible in a new place.

## Using it as a captain

1. Run a sync (`python -m scheduler.graphql_sync`) or the demo build.
2. Run `python scripts/build_matchups.py` (safe to re-run any time; it
   upserts).
3. Open the "Matchups" sheet in the Excel export, or the "Matchups" tab in
   the demo/dashboard page, for each of your players.
4. "Recommended opponents" (score ≥ 65) and "opponents to be cautious of"
   (score ≤ 35) are the standout cases — most matchups will sit in the
   middle with only one or two games of history, which is real information
   too (there just isn't a strong signal yet).

A low match count is the biggest caveat on any of this: a 1-0 head-to-head
record scores identically to a 10-0 one (`matchup_score` doesn't currently
weight by sample size). Treat an early-season score as a starting point for
your own judgment, not a verdict.
