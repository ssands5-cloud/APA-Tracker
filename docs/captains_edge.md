# Captain's Decision Engine

Turns the other engines' outputs into one ranked answer: which of my players
should take which opponent, in what order, and how much to trust each call.

```
analytics/captains_edge.py       the maths
scripts/build_captains_edge.py   builds exports/captains_edge.json
ui/tabs/captains_edge.py         the demo tab
export_excel.py                  the "Captain's Edge" sheet
```

**Purely derived.** It invents no metric and writes to no table. Every input
is already computed and stored by something else.

## Where the inputs actually come from

| Input | Source table | Engine |
|---|---|---|
| `win_probability`, `expected_points`, `expected_balls` | `player_h2h_advantage` | Head-to-Head Advantage |
| `volatility`, `sl_stability`, `regression_slope`, `hot_cold_flag` | `player_trends` | Player Trend Analyzer |

The specification named `analytics.matchups` as the source of the first
three. **They are not there.** `player_matchups` carries `win_rate` and
`matchup_score`; `expected_points`, `expected_balls` and `win_probability`
are the Head-to-Head Advantage Engine's columns. This module reads them from
where they live.

## Composite matchup score

```
score = 0.6·win_probability + 0.3·points_norm + 0.1·balls_norm
```

Win probability dominates because it is the only component that answers
*will this player win*. The expected-output terms describe *by how much*,
which breaks ties rather than deciding.

### Normalisation

Min–max, **population-relative**, across every pairing in the build:

```
norm(v) = (v − min) / (max − min)
```

An "expected 3 points" means nothing until you know whether 3 is the best or
the worst on the board. The bounds used are recorded in the JSON under
`normalization`, so a reader can tell what a 0.7 was measured against.

A **degenerate range** (every value identical) normalises to `1.0` rather
than dividing by zero: if every candidate expects the same output, none is
disadvantaged by that component.

### NULL components are skipped, and the weights renormalise

The spec says "NULL → skip component". It does not say whether the remaining
weights renormalise. **They do**, and that is a deliberate interpretation:

> A 9-ball pairing has no `expected_points` by construction. Without
> renormalising, it would score up to 0.3 lower than an identical 8-ball
> pairing purely for lacking a field that does not apply to it — making the
> two formats incomparable.

So a pairing with only `win_probability` scores exactly its win probability,
not 0.6 of it.

A pairing where **every** component is NULL has **no score** (`None`), which
is different from a score of zero.

## Risk factor

```
risk = clamp(volatility · (1 − sl_stability), 0, 1)
```

Both terms come from the Player Trend Analyzer, and they are related —
stability is `1/(1+volatility)` — so this is effectively
`volatility²/(1+volatility)`. Risk therefore climbs *faster* than volatility
alone, which is the intent: a player whose skill level swings is a gamble
twice over, once for the swing and once for not knowing which way.

`None` when either input is missing.

## Confidence

```
HOT     → 0.75 + slope
NEUTRAL → 0.50 + slope
COLD    → 0.25 + slope
```

clamped to 0–1.

The flag sets the base and the slope nudges it, so a COLD player who has
started climbing is not written off entirely, and a HOT player who has begun
to slide loses ground before the flag catches up.

`None` when either input is missing, **or when the flag is not one the
Player Trend Analyzer produces** — an unrecognised flag is a bug upstream,
and guessing a base for it would hide that.

## Lineup recommendation

- **One entry per player**, not per pairing. A player has many possible
  opponents; the lineup answers *which one they should play*, so each player
  keeps their single best-scoring pairing.
- **Ranked by `matchup_score` descending.**
- **`recommended_order` runs 1..N** over the scored players. It is **not
  padded to 5** — a team with three scored players gets three
  recommendations, and inventing two more would be fabrication.
- **Unscored players are listed but unranked** (`recommended_order = None`).
  Ordering a player with no score would imply a judgement the evidence does
  not support.
- **`rationale`** is one short sentence naming the opponent, the score, and
  whichever of form or stability is notable — including saying plainly when
  either is unknown. A recommendation a captain cannot interrogate is one
  they should not follow.

## A known defect this engine has to work around

**Team membership and pairings live in different id spaces.** The same person
exists as several `Player` rows:

```
roster ingest  keys on member.id        Paul Smith -> 3349374   (has team_id)
scoresheets    key on a per-format id   Paul Smith -> 92612611  (no team_id)
                                        Paul Smith -> 92828300  (no team_id)
```

Verified against the live database: **14 rostered players, 72 with pairings,
zero overlap by id.** 30 names carry multiple `Player` rows, some four.

`ui/export_excel.py` predicted exactly this in a docstring — *"two different
external_ids got assigned to one real person, a separate bug worth
chasing"*. It is now happening at scale.

**Consequence:** a `team_id` join returns nothing, so a lineup would be
empty. Until the id spaces are unified — an ingest change with wide blast
radius, and not this module's scope — the roster is resolved **by player
name**, and only for a name that is unambiguous among rostered players. Two
different people sharing a name would otherwise have one person's form
attached to the other's lineup slot.

How the resolution happened is reported in every document and shown in the
tab, so no reader mistakes a name match for an id join:

```json
"roster_resolution": "player_name (id spaces do not join -- see docs/captains_edge.md)",
"unresolved_rostered_players": ["Dave Gallardo", "Kaiden Fitzgerald"]
```

## NULL behaviour

NULL means *not enough evidence* and is never a fabricated zero:

- `matchup_score = None` — no component had a value
- `risk_factor = None` — no volatility or stability for that player
- `confidence = None` — no slope, no flag, or an unrecognised flag
- `recommended_order = None` — unscored, therefore unranked

Both the tab and the sheet render NULL as **"No data"**, never blank and
never zero, and it always sorts last.

## Storage and rebuilds

The document is `exports/captains_edge.json`, **rewritten whole** on every
build. That is the pruning guarantee: a lineup for a team that no longer has
pairings cannot survive a rebuild, because nothing is merged forward.

Rebuilding is idempotent — the document derives entirely from current rows.

```bash
python -m pipeline    # ingest, rebuild engines, then all exports
```

## Limitations

- **Form data is mostly absent.** `confidence` needs `hot_cold_flag`, which
  the Player Trend Analyzer only emits at 5+ observations. No player has
  more than 4 yet, so confidence is `None` across the board and the rationale
  says "form unknown (needs 5+ matches)". It populates as the season runs.
- **Rankings currently rest on `win_probability` alone** for most pairings,
  since `expected_points`/`expected_balls` are thin at this sample size.
- **Name-based roster resolution is a workaround, not a design.** It is
  correct for the 12 rostered players whose names are unambiguous, and it
  omits the rest rather than guessing.
- **Opponent assignment is intentionally independent here.** Each player is
  given their own best opponent, so two players can be recommended against the
  *same* opponent. A real lineup card assigns each opponent once; the separate
  Lineup Optimizer now solves that whole-card assignment exactly and writes
  `exports/lineups.json` (see `docs/lineup_optimizer.md`).
- **No validation against outcomes.** Nothing here has been checked against
  whether the recommended lineup actually won.
