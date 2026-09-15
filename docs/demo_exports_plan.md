# Demo exports integration plan

All demo artifacts must be produced from one regenerated SQLite database and
one run configuration. `pipeline/exports.py` remains the composition point;
the future launcher should call it rather than duplicating exporter logic.

## Artifact contract

| Artifact | Builder | Demo role | Required validation |
| --- | --- | --- | --- |
| `captain_first_edge.html` | `scripts/build_captain_first_edge.py` + `ui/tabs/tonights_match.py` | Primary Tonight's Match, Lineup Lab, Data Coverage, and descriptive Opponent Risk Profile entry view | self-contained HTML, scope/evidence reconciliation, named single-field ordering, no categorical risk fields, no external requests |
| `player_vs_player.html` | `ui/export_html_player_vs_player.py`, reusing `ui/tabs/player_vs_player.py` | whole-scope matrix, descriptive current-skill difficulty heatmap, and anchored explicit-pair details | exact pair-key parity, UNKNOWN/evidence independence, continuous numeric scale without thresholds, escaping, stable initial pair order, no renderer math |
| `player_vs_player.xlsx` | `ui/export_excel_player_vs_player.py` | whole-matrix handoff, difficulty grid/audit rows, and real game history | openpyxl load, values only, pair/game/heatmap-key parity |
| Player vs Player JSON document | planned Full Production Demo Builder adapter (optional) | versioned matrix parity/source document | pair/game-key reconciliation, source/status fields, null preservation |
| `data_coverage.html` | `scripts/build_data_coverage.py` + `ui/tabs/data_coverage.py` | evidence coverage, missing skills, sample sizes, refresh dates, unavailable fields | escaped/self-contained, zero-total nulls, matrix count parity |
| `data_coverage.xlsx` | `ui/export_excel_data_coverage.py` | `Data_Coverage` and `Sample_Sizes` sheets | openpyxl load, values only, counts/percentages/timestamps/sample parity |
| `team_strength.html` | implemented standalone `scripts/build_team_strength.py` + `ui/tabs/team_strength.py`; production registration pending | offense, defense proxy, depth, composite, and source coverage | formula-version/raw-denominator parity; no strength tiers |
| `team_strength.xlsx` | implemented standalone `ui/export_excel_team_strength.py`; production registration pending | team summary plus roster/match audit rows | three values-only sheets, exact player/match keys, null composite gate |
| `season_projection.html` | implemented standalone `scripts/build_season_projection.py` + `ui/tabs/season_projection.py`; production registration pending | remaining schedule, log5 baseline, and real standings curve | every schedule row retained, source-status and assumption labels |
| `season_projection.xlsx` | implemented standalone `ui/export_excel_season_projection.py`; production registration pending | summary, remaining matches, and standings history | values only, log5/expected-total parity, identity-join disclosure |
| `trend_analyzer.html` | implemented standalone `scripts/build_trend_analyzer.py` + `ui/tabs/trend_analyzer.py`; richer history/demo wiring pending | slope, volatility, trend score, descriptive indicators, and planned history chart | exact spans/gates, canonical initial order, no extrapolation or recommendation |
| `trend_analyzer.xlsx` | implemented standalone `ui/export_excel_trend_analyzer.py`; general `Player Trends` sheet remains compatible | trend summary and chronological skill history | values only, exact player/format/session keys and null gates |
| `opponent_volatility.html` | implemented standalone `scripts/build_opponent_volatility.py` + `ui/tabs/opponent_volatility.py`; richer UX/demo wiring pending | opponent-team median/coverage and player-level variation | exact scoped join, numeric scale, no categorical risk labels |
| `opponent_volatility.xlsx` | implemented standalone `ui/export_excel_opponent_volatility.py`; production registration pending | team median/coverage plus all opponent rows | exact transform/median, null retention, no threshold styling |
| `captains_live_assistant.html` | planned `scripts/build_captains_live_assistant.py` + `ui/tabs/captains_live_assistant.py` | match-night local state over immutable verified analytics | common run/scope/hash, exact Lineup Lab reconciliation, no hidden score |
| `analysis_tabs.html` | `pipeline.exports.write_tabs` + `ui/tabs/*` | supporting Head-to-Head, Player Trends, and available legacy cards | non-empty sections only when real documents exist |
| `apa_data.json` | `ui.export_json.export_to_json` | machine-readable general snapshot | valid JSON, expected top-level keys, source timestamps |
| `apa_stats.xlsx` | `ui.export_excel.export_to_excel` | workbook for captain/operator review | openpyxl load without repair; sheet headers and real rows |
| `captains_edge.html` | `scripts/build_captains_edge.py` | legacy per-player decision view; clearly labeled | HTML safety and source database identity |
| `captains_edge.json` | `scripts/build_captains_edge.py` | legacy decision payload | valid JSON and no fabricated null replacements |
| `captains_edge.xlsx` | `scripts/build_captains_edge.py` | legacy shareable workbook | open without repair |
| `lineups.json` | `scripts/build_lineups.py` | legacy optimizer output, not Stage 3 approval | schema/row provenance and explicit warnings |
| `index.html` | planned Full Production Demo Builder | verified relative links to every available artifact | emitted only after parity/security gates; no remote assets |
| `demo_manifest.json` | planned `scripts/build_full_production_demo.py` | run provenance and release evidence | hashes, relative paths, no secrets |

## Ordering

1. Ingest and commit the database session.
2. Build the general JSON/XLSX exports.
3. Obtain the Stage 1 matrix and exact histories, call
   `analytics.player_vs_player_matrix.build_matrix_export` once, and pass the
   same rows to the matrix renderers. The HTML renderer delegates explicit
   details to `ui/tabs/player_vs_player.py` rather than recomputing them.
4. Build one Data Coverage report from the matrix plus query-layer
   standings/career refresh timestamps. Render its HTML/XLSX from the identical
   report. Lineup assignment coverage remains a separate manifest check.
5. Build current-skill heatmap cells from the exact ordered Player-vs-Player
   rows, then build Team Strength, Season Projection, Trend Analyzer, and
   Opponent Volatility from the same locked database/scope. Keep every formula
   version, raw denominator, join status, and null reason. Team Strength is a
   separate context document and is not an input to heatmap analytics.
6. Build Captain's Edge and Lineup Optimizer read-only documents. Captain's
   Edge consumes the already-built matrix document for its Opponent Risk
   Profile; it does not rerun analytics.
7. Build the static Captain's Live Assistant source document from the already-
   built reports; do not blend an assistant score.
8. Append optional workbook sheets only when the source document has real rows.
9. Write analysis tabs after JSON artifacts exist.
10. Build captain-first HTML after the final database and scope set exist.
11. Validate every path, hash, coverage denominator, descriptive sort contract,
   and Player vs Player cross-renderer value before presentation.

## Cross-artifact consistency

The manifest must record one database hash (or immutable file hash before
serving) for every artifact. The selected team, opponent, format, and session
must match across HTML controls, JSON scopes, and workbook rows. Observed win
rates and modeled probabilities keep distinct labels everywhere. “No data” and
“unavailable” are display contracts, not missing JSON keys silently interpreted
as zeros. The matrix keeps Stage 1 distinct-match evidence separate from
`PlayerVsPlayerSummary.total_games`. Its summary rows and embedded explicit
details label the modeled probability and its identical projection alias with
the same audit status.

Captain's Edge risk-profile values must match the selected matrix row by key.
The export contract has no Recommended Avoid/Target, danger/favorable,
risk-tier, traffic-light, or equivalent categorical field. When the profile is
ordered, the artifact records the one visible descriptive source field and
direction; missing values sort last and canonical opponent identity breaks
ties. No renderer evaluates a threshold or blends metrics into a hidden score.
A value or ordering mismatch blocks the bundle.

Data Coverage HTML/XLSX and the manifest must agree on scope,
DIRECT/INDIRECT/UNKNOWN/total counts, raw percentages, missing-skill identities,
sample rows, refresh timestamps, and unavailable-field text. A zero denominator
leaves label percentages null; it is never coerced to 0% or 100%.

Team Strength artifacts must agree on all three components, composite null
gate, formula version, raw W/P and PF/PA values, fifth-player identity, roster
coverage, and source keys. Season Projection artifacts must agree on every
remaining match, actual source rates/status, raw log5 probability, expected
totals, and real standings-history points. Trend/volatility artifacts must
agree on player/format/session keys, sample spans, raw sigma/slope, transformed
indices, nulls, and canonical order.

Heatmap HTML/script JSON carries one value for every matrix pair key. Its
difficulty is derived only from the shared current-skill probability; Excel and
HTML must never substitute the experimental blended probability. Missing skills
remain null/hatched and do not reduce the matrix denominator. HTML and Excel
use the same deterministic continuous 0–100 palette interpolation, never
difficulty bands or semantic thresholds. No reliability weight, row/column/
matrix difficulty index, categorical field, or score-driven order is exported.
Feasible/numeric/null cell counts must reconcile exactly.

Team Strength may appear beside Matrix View only after run, hash, session, and
team-ID reconciliation. Its values stay in the independently versioned Team
Strength document and workbook; they do not appear in
`Match_Difficulty_Data`, affect the heatmap, or explain a pair value.

Implementation status, exact file ownership, and the required build order for
the five remaining modules are defined in
`remaining_analytics_wiring_plan.md`. A renderer may be marked available in the
manifest only when its immutable source document and every required parity
surface pass together.

The controlling heatmap metric, UX, palette, workbook, and audit contract is
`match_difficulty_heatmap.md`.

## Packaging

The generated index should link to relative paths only. A release bundle may
include HTML, JSON, XLSX, the redacted manifest, and a README with the capture
time. It must exclude `.env`, `.session_cache`, raw authenticated fixtures,
browser profiles, SQLite backups containing teammate data, and debug logs with
tokens.
