# Head-to-Head Advantage Engine

One row per (player, opponent, format, session): the record, a
trend-adjusted score, and three forward-looking estimates — the probability
of winning, the expected 8-ball match points, and the expected 9-ball ball
count.

```
analytics/head_to_head.py      the maths
scripts/build_head_to_head.py  builds every pairing from stored history
player_h2h_advantage           the table it writes
ui/tabs/matchups.py            the demo tab
export_excel.py                the "Head-to-Head" sheet
```

Built entirely from `player_head_to_head` rows — the same per-game rows
`analytics/matchups.py` aggregates — so this engine and the Matchup
Advantage Engine can never disagree about which games happened.

**It does not touch `player_matchups`.** That table belongs to the Matchup
Advantage Engine and is read by Captain's Edge, the workbook, the demo and
the pipeline. This engine writes its own table alongside it.

## Unavailable APA Fields

Two fields the original specification asked for are **not produced**:

| Field | Why |
|---|---|
| `avg_innings` | APA does not expose per-opponent innings. No captured query returns an inning count at any granularity — checked against every operation in `parser/apa_graphql.py`. |
| `avg_defense` | APA does not expose per-opponent defensive shots. A **lifetime** average exists (`defensiveShotAvg`, surfaced as `Career Stats.Defensive Shot Avg`), but there is no per-match or per-opponent figure to aggregate. |

These fields are **intentionally omitted**. No synthetic, placeholder,
estimated, proxy or otherwise fabricated values are used in their place, and
no column exists for them in `player_h2h_advantage`. A test asserts their
absence, so they cannot reappear by accident.

If either turns out to be real and captured after all, the process is the
one every other field in this project went through: cite the exact query and
field in `docs/data-fields.md` first, then wire it in.

## Formulas

### Record

`wins` and `losses` count only games with a **recognised** result (`W`/`L`).
A malformed or missing result is evidence of nothing and is excluded from
both, so `wins + losses == total_matches` always holds. This is the same
rule `analytics/matchups.py` applies.

### Skill-level delta

```
sl_delta = mean(opponent_skill_level - own_skill_level)
```

Positive means the player has been **giving up** skill level in this
pairing. Same sign convention as `PlayerMatchup.sl_delta`. `None` — not
zero — when no game carries both levels: no skill data is a different fact
from an even matchup.

### Trend modifier

`+5` trending up, `-5` trending down, `0` for stable or no data — reusing
`analytics.matchups.trend_modifier` outright rather than defining a second
scale.

The trend itself compares the player's **first** skill level in the pairing
to their **last**, mirroring `analytics.skill_level_trends.skill_level_trend`
— so a dip that fully recovers reads `stable`. It is computed locally only
because head-to-head rows carry `own_skill_level` rather than the
`skill_level` attribute that function expects.

Stored so a sheet can show *why* a score moved, not just that it did.

### Matchup score

Reused directly from `analytics.matchups.matchup_score` — the existing 0–100
score, with its documented win-rate swing, opponent-skill swing, sample-size
weighting and trend modifier. See `docs/matchups.md`.

Volatility is passed as `0`: it is a property of a player's whole season,
which this pairing-scoped view does not have, and `matchup_score` already
treats `0` as "no volatility penalty" rather than as missing data.

## Win-probability model

```
logit(p) = SL_LOG_ODDS_PER_LEVEL * skill_advantage
         + reliability(n) * logit(smoothed_win_rate)

p = clamp(1 / (1 + e^-logit(p)), 0.02, 0.98)
```

| Term | Meaning |
|---|---|
| `skill_advantage` | `-sl_delta` — the player's mean SL minus the opponent's. `sl_delta` is stored opponent-minus-own, so it is negated here. Getting this backwards would invert every prediction; a test pins the direction. |
| `SL_LOG_ODDS_PER_LEVEL` | `0.40`. APA's handicap system is designed so a higher skill level must win *more* games for the same match points, making a one-level edge real but moderate: `+1` SL ≈ 60%, `+3` SL ≈ 77% before any history. |
| `smoothed_win_rate` | `(wins + 1) / (n + 2)` — Laplace smoothing, so a 1–0 record reads as 67% rather than certainty and 0–1 reads as 33% rather than impossible. |
| `reliability(n)` | `analytics.matchups.reliability_weight` — the same `n/(n+3)` damping the matchup score already uses. A 1-game record contributes a quarter of its log-odds; a 10-game record nearly all of it. |
| clamp | Pool has upsets. A stated 0% or 100% would be a claim the data cannot support. |

**This is a transparent, documented model — not a fitted one.** No training
pipeline exists in this project, and no coefficients were learned from data.
The constants above were chosen to match known properties of the APA
handicap system and are stated openly so they can be argued with. Calling it
a "trained model" would misrepresent where the numbers come from.

`None` when there is neither a recognised game nor a skill level: a pairing
with no evidence has no probability, which is different from a 50/50 one.

## Expected points and expected balls

Format-specific and mutually exclusive. `None` means *not this format*,
never zero.

- **`expected_points`** — 8-ball only, from `points_earned` (which carries
  `eightBallMatchPointsEarned`).
- **`expected_balls`** — 9-ball only, from `nine_ball_points`, the real
  captured `nineBallPoints` field.

These are **different measurements**, not two names for one number. In the
current data, ball counts run 5–55 (mean 27) while 9-ball match points run
0–20 (mean 10). Reading one as the other would be silently wrong.

### Weighting

```
estimate = reliability(n) * observed_mean + (1 - reliability(n)) * baseline
```

The baseline is the player's own average across **all** opponents in that
format, computed by the builder. With one game the estimate sits a quarter
of the way from the player's normal output toward that single result; by ten
games it is almost entirely the observed value.

Without a baseline the plain observed mean is returned — shrinking a value
toward itself would be arithmetic theatre.

## Recommendations

A pairing is highlighted only when **both** signals agree:

| Tag | Rule |
|---|---|
| Recommended | `matchup_score >= 60` **and** `win_probability >= 0.60` |
| Avoid | `matchup_score <= 40` **and** `win_probability <= 0.40` |
| Neutral | everything else, including any pairing with no probability |

Either signal alone would mislead: score alone promotes a 1–0 fluke,
probability alone promotes a skill-level mismatch the player has actually
been losing. The demo tab and the Excel sheet use the same thresholds, so
they cannot label a pairing differently.

## Rebuilding

```bash
python -m pipeline                     # ingest + exports
python -m scripts.build_head_to_head   # then this table
```

Upserted on `(player_id, opponent_id, format, session_name)` — always
current, not snapshotted per run. Re-running is idempotent.
