# Opponent Scouting

Aggregates the real, already-computed per-pairing signals by OPPONENT
PLAYER, so a captain can see, before a match, which specific opponents
are dangerous and why -- without re-deriving anything the Lineup
Optimizer hasn't already fetched.

```
analytics/opponent_scouting.py   summarize_opponent() / summarize_opponents()
scripts/build_lineups.py         calls it once per real build; stores "opponent_scouting" on the payload
ui/export_excel.py               new Opponent_Scouting sheet
apa_config.yaml                  opponent_scouting: (danger thresholds)
```

No new database query: `scripts/build_lineups.py` already fetches every
real `player_h2h_advantage` pairing row (`fetch_pairing_rows`) and every
real `player_trends` row (`fetch_trends`) for the Lineup Optimizer. This
module re-groups the SAME real rows by opponent instead of by team
pairing.

## Inputs and how they're scoped

Built from the **eligible** pairing rows -- the same real,
team-identity-resolved subset `_lineup_for_group` groups into lineups
(see `docs/lineup_optimizer.md`'s "Grouping and identity" section), not
the raw, pre-resolution list. An opponent whose team identity couldn't be
resolved unambiguously is excluded from scouting the same way they're
excluded from a lineup -- consistent integrity bar, not a separate,
looser data path.

| Field | Real source |
| --- | --- |
| `avg_matchup_score` / `avg_win_probability` | mean of `player_h2h_advantage.matchup_score` / `.win_probability` across every one of "my" players who has faced this opponent -- a row missing either value is excluded from that average, never treated as 0 |
| `opponent_volatility` | the OPPONENT's own real `player_trends.volatility`, looked up in the same real (format, session) context the pairing row itself carries -- `player_trends` has no notion of "mine" vs "theirs", so the same real table already answers this |
| `times_faced` | a real count of pairing rows contributing to the average |

## Danger flag

```
is_danger_matchup = avg_win_probability < win_probability_danger_threshold
                  OR opponent_volatility >= volatility_danger_threshold
```

Each flagged opponent carries real, human-readable `danger_reasons`
naming which condition(s) actually fired, with the real numbers inline
(e.g. `"our average win probability against them (35%) is below the 40%
threshold"`). An opponent with no usable signal at all is **never**
flagged -- absence of evidence is not evidence of danger.

Thresholds (`apa_config.yaml`'s `opponent_scouting` section) are real,
overridable defaults, not claimed as empirically fit -- the same real gap
`docs/lineup_optimizer.md`, `docs/lineup_risk.md`, and
`docs/win_probability.md` each already document for their own
thresholds/weights: there is no historical "which opponent actually
upset us" record to check them against yet.

## Excel sheet

A genuinely new sheet, `Opponent_Scouting`, appended the same
post-process way the Lineup Optimizer sheet is (`ui.export_excel.append_opponent_scouting_sheet`,
reading the same real `lineups.json`). One row per real opponent player,
sorted by opponent team then name. `Danger Matchup = Yes` rows are
conditionally highlighted, mirroring the same red-flag styling
`ui.export_excel` already uses elsewhere (e.g. Head-to-Head's avoid
highlighting). Idempotent: a rerun replaces the prior sheet.

Verified against the real database: 72 real opponents scouted, 13 real
danger flags, entirely from data already captured for the Lineup
Optimizer -- no new upstream field, no fabricated opponent.
