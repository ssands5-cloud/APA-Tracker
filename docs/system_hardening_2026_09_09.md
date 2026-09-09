# System Hardening Pass — 2026-09-09

A full audit of everything shipped in this session's Captain's Edge
roadmap (win-probability model, Lineup Risk Scoring, per-lineup
rationale, Opponent Scouting, Season Projection, Captains_Edge_Summary)
before moving on. Real findings and real fixes below, not a checklist
rubber-stamp.

## Analytics consistency

Checked: every new pure module (`analytics/win_probability.py`,
`analytics/lineup_risk.py`, `analytics/rationale.py`,
`analytics/opponent_scouting.py`, `analytics/season_projection.py`,
`analytics/captains_edge_summary.py`) follows the same architecture
`analytics/lineup_optimizer.py` established: no database access, no
config reads, a frozen `*Weights`/`*Thresholds`/`*Toggles` dataclass with
a `DEFAULT_*` module-level instance, real inputs in, a real dataclass
result out. Confirmed no `analytics/*` module imports from `scripts/`
(the layering stays one-directional: analytics ← builder scripts ←
pipeline). No circular imports among the new modules -- the only
cross-module import is `analytics.rationale` → `analytics.lineup_risk`
(for its `LineupRiskMetrics`/`LineupRiskWeights` types), which is correct
since rationale describes risk, not the reverse.

**Two real gaps found and fixed:**

- `analytics.opponent_scouting.summarize_opponent([], ...)` raised a bare
  `IndexError: list index out of range` for an empty `rows` list --
  `summarize_opponents` never constructs an empty group internally, but
  the public function had no guard against a caller passing one directly.
  Now raises a clear `ValueError`.
- `analytics.lineup_risk.anchor_stability_score`'s tie-break (lower
  `risk_factor` wins among equal win probabilities) had no test for the
  case where one tied candidate's `risk_factor` is `None` -- confirmed
  the existing `1.0` fallback correctly treats missing risk as "sorts
  last, never assumed equal to or better than a real reading."

## Config defaults

Every new `apa_config.yaml` section (`win_probability`, `lineup_risk`,
`rationale`, `opponent_scouting`, plus `lineup_optimizer`'s new
`weight_modeled_win_probability` key) has its default value pinned by a
real test in `tests/test_apa_config.py`, checked against that same
module's own `DEFAULT_*` constant -- confirmed no drift exists between
the shipped config file and the code's own defaults.

`analytics.season_projection` and `analytics.captains_edge_summary`
correctly have NO config section -- documented explicitly in each
module's own docs as scoped-out-for-now or an explicit function
parameter (`n`, not a config value), not an oversight.

## Naming conventions

`weight_*` is used consistently, and ONLY, for a linear-combination
coefficient (a number that gets multiplied into a sum) -- `logistic_scale`,
`clamp_min`/`clamp_max`, `danger_threshold`,
`win_probability_danger_threshold`/`volatility_danger_threshold`, and
`include_lineup_rationale` correctly do NOT use that prefix, since none
of them are combination weights.

One real, intentional (not a bug) difference: `lineup_risk`'s single
`danger_threshold` vs. `opponent_scouting`'s two, more verbosely-named
`*_danger_threshold` keys. `lineup_risk` only ever needs one danger
cutoff (on win probability); `opponent_scouting` needs two, on two
different metrics, so its keys must disambiguate by name. Not
unified into one shared pattern, since the two modules' real needs
differ.

Every `load_*_from_config` function in `scripts/build_lineups.py` has a
matching `_configured_*` CLI wrapper, and both are actually called from
every real entry point (`build()`, `main()`, `pipeline/exports.py`) --
confirmed no orphaned loader exists.

## Reproducible-build compatibility

Ran `scripts/reproducible_build.py` (the other process's own staged
file -- executed, never modified) end-to-end after this session's roadmap
work: fresh pinned venv, all 27 locked dependencies verified exact, full
1,008-test suite green inside that fresh interpreter, real pipeline run
against the CI sample fixtures producing all 7 expected artifacts
(including a real `lineups.json` with the new `opponent_scouting` key and
every lineup's `lineup_risk` block populated), `BUILD_INFO.json` written
against the correct commit. No incompatibility found.

## Tests added by this pass

- `tests/test_opponent_scouting.py`: the empty-`rows` `ValueError`.
- `tests/test_lineup_risk.py`: the `risk_factor=None` anchor tie-break.
- `tests/test_lineup_optimizer.py`: extended the existing
  `test_invalid_unit_inputs_are_rejected` parametrization to cover
  `modeled_win_probability`, which the original list omitted.
- `tests/test_captains_edge_summary.py`: `top_danger_matchups`'s
  volatility tie-break, both with two real values and with one missing.

## Documentation drift found and fixed

`docs/future_sheets_upstream_gaps.md`'s "Lineup Simulator" and "Captain
Summary" sections were written before this session's win-probability and
lineup-risk work existed, and had gone stale: both said the "5-player
combination aggregation formula" was "not started." It's now real and
shipped (`analytics.win_probability` + `analytics.lineup_risk`) -- the
genuinely remaining gap is a combination-selection interface for a
HYPOTHETICAL lineup, not a missing formula. Also clarified that the new
`Captains_Edge_Summary` sheet is a real but DIFFERENTLY-scoped delivery
against whole-league data today, not a replacement for the
`Next_Match`-scoped Captain Summary that section originally asked for.
