# Lineup Risk Scoring

Elevates the Lineup Optimizer's per-PAIRING signals to a per-LINEUP
summary: how dangerous is this whole lineup, where is the upset risk
concentrated, and is it stable enough to anchor a match.

```
analytics/lineup_risk.py    compute_lineup_risk() and its four components
scripts/build_lineups.py    calls it once per solved lineup; stores "lineup_risk" on the payload
ui/export_excel.py          renders it as the Lineup Optimizer sheet's footer
apa_config.yaml             lineup_risk: (weights + danger_threshold)
```

No new sheet, no new solver, no new artifact type: the metrics ride along
on the lineup payload `scripts/build_lineups.py` already writes to
`exports/lineups.json`, and appear below the existing per-pairing table on
the existing `Lineup Optimizer` sheet.

## Inputs

Every input is a real, already-computed pairing signal read back off the
solved lineup -- this module queries nothing:

| Input | Real source |
| --- | --- |
| `modeled_win_probability` | `analytics.win_probability.compute_win_probability` (see `docs/win_probability.md`) -- always a real, clamped float on a real solved assignment |
| `volatility` | the raw `player_trends.volatility` reading, carried through `PairingCandidate` → `AssignmentEntry` specifically so this module can read it without a second database pass |
| `risk_factor` | `analytics.captains_edge.risk_factor` -- used only as an anchor tie-break |

A missing `volatility` contributes **0**, the same convention
`analytics.win_probability` already uses for this identical signal.

## The five metrics

```
URI (Upset Risk Index)      = sum( (1 - P(win)) * Volatility )
ASS (Anchor Stability)      = P(win) - Volatility, for the anchor
LVL (Lineup Volatility Load)= sum( Volatility )
DMC (Danger Matchup Count)  = count( P(win) < danger_threshold )

LRS (Lineup Risk Score)     = weight_upset_risk        * URI
                            + weight_anchor_instability * (1 - ASS)
                            + weight_volatility_load   * LVL
                            + weight_danger_count      * DMC
```

**The anchor** is the assigned player with the highest real
`modeled_win_probability`, ties broken by lower `risk_factor` then
lexicographically by name (the same deterministic tie-break shape
`solve_lineup_assignment` already uses). This is an operational
definition this module picks from the available real signals -- it is
*not* a further claimed APA rule the way the 23-Rule in
`docs/lineup_legality.md` is. An empty lineup has no anchor: `ASS` and
`anchor_player_name` are both `None`, never a guessed stand-in.

**ASS can be negative.** It is `P(win) - Volatility` with no lower bound,
so a genuinely swingy anchor scores below zero -- confirmed against real
data (one real Fall 2026 lineup's anchor scores `-0.168`). That is a real
reading, not a bug.

## What this is and isn't

A transparent decision-support scalar, **not a fitted model.** There is no
historical record of which lineup a captain actually played, so there is
nothing to check `LRS`'s ranking against -- the same real gap
`docs/lineup_optimizer.md` documents for the optimizer's own combined
score. The default weights (0.30 / 0.30 / 0.20 / 0.20) are a reasoned,
roughly-equal starting split, not an empirically fit one.

**The four components deliberately overlap.** `URI` already contains
volatility, and `LVL` sums the same volatility again; `ASS` re-reads the
anchor's own two signals. That is intentional for a captain-facing
dashboard -- a total, a concentration, a worst-case count, and a
single-player check are four different questions about the same lineup,
and seeing them separately is the point. It does mean `LRS` is not a
statistically clean composite, and it should not be read as one.

## Config

```yaml
lineup_risk:
  weight_upset_risk: 0.30
  weight_anchor_instability: 0.30
  weight_volatility_load: 0.20
  weight_danger_count: 0.20
  danger_threshold: 0.40
```

A missing section, or any one missing key, falls back to that key's own
module default (`scripts.build_lineups.load_lineup_risk_weights_from_config`).
`danger_threshold` is strict (`<`, not `<=`).

## Excel footer

`ui.export_excel.append_lineup_optimizer_sheet` writes one summary row per
solved lineup below the per-pairing table, under a bold `Lineup Risk`
heading, separated by a blank spacer row. The sheet's `auto_filter` is set
from the data rows alone and deliberately excludes the footer -- a captain
filtering the pairing table must never accidentally filter away the rows
explaining it. A lineup whose payload has no `lineup_risk` block (an older
document, written before this existed) is skipped rather than rendered
with blanks; a present-but-`None` value inside a block shows as `No data`,
the same convention the pairing table already uses.

## Rationale

Each `lineup_risk` block also carries a real `rationale` sentence --
`analytics.rationale.lineup_risk_rationale`, a plain-language description
of the numbers already in the block (the anchor, their stability, the
danger count, the overall volatility level, the combined score). Not a
new formula, not a fabricated verdict -- see `analytics/rationale.py`'s
own module docstring for why per-pairing rationale (already real, already
shipped in `analytics.captains_edge` and `analytics.lineup_optimizer`)
isn't duplicated here. Controlled by `apa_config.yaml`'s
`rationale.include_lineup_rationale` (default `true`); when off, the
`rationale` key is `None` rather than omitted, so consumers can rely on
the key always being present.
