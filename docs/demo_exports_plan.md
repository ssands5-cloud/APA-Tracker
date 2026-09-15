# Demo exports integration plan

All demo artifacts must be produced from one regenerated SQLite database and
one run configuration. `pipeline/exports.py` remains the composition point;
the future launcher should call it rather than duplicating exporter logic.

## Artifact contract

| Artifact | Builder | Demo role | Required validation |
| --- | --- | --- | --- |
| `captain_first_edge.html` | `scripts/build_captain_first_edge.py` + `ui/tabs/tonights_match.py` | Primary Tonight's Match, Lineup Lab, Data Coverage, and Opponent Risk Profile entry view | self-contained HTML, scope/evidence reconciliation, nullable flag status, no external requests |
| `player_vs_player.html` | `ui/export_html_player_vs_player.py`, reusing `ui/tabs/player_vs_player.py` | whole-scope matrix plus anchored explicit-pair details | UNKNOWN visibility, escaping, stable initial pair order, no renderer math |
| `player_vs_player.xlsx` | `ui/export_excel_player_vs_player.py` | whole-matrix handoff plus real game history | openpyxl load, values only, pair/game-key parity |
| Player vs Player JSON document | planned `demo.py` adapter (optional) | versioned matrix parity/source document | pair/game-key reconciliation, source/status fields, null preservation |
| `analysis_tabs.html` | `pipeline.exports.write_tabs` + `ui/tabs/*` | supporting Head-to-Head, Player Trends, and available legacy cards | non-empty sections only when real documents exist |
| `apa_data.json` | `ui.export_json.export_to_json` | machine-readable general snapshot | valid JSON, expected top-level keys, source timestamps |
| `apa_stats.xlsx` | `ui.export_excel.export_to_excel` | workbook for captain/operator review | openpyxl load without repair; sheet headers and real rows |
| `captains_edge.html` | `scripts/build_captains_edge.py` | legacy per-player decision view; clearly labeled | HTML safety and source database identity |
| `captains_edge.json` | `scripts/build_captains_edge.py` | legacy decision payload | valid JSON and no fabricated null replacements |
| `captains_edge.xlsx` | `scripts/build_captains_edge.py` | legacy shareable workbook | open without repair |
| `lineups.json` | `scripts/build_lineups.py` | legacy optimizer output, not Stage 3 approval | schema/row provenance and explicit warnings |
| `demo_manifest.json` | future orchestrator | run provenance and release evidence | hashes, relative paths, no secrets |

## Ordering

1. Ingest and commit the database session.
2. Build the general JSON/XLSX exports.
3. Obtain the Stage 1 matrix and exact histories, call
   `analytics.player_vs_player_matrix.build_matrix_export` once, and pass the
   same rows to the matrix renderers. The HTML renderer delegates explicit
   details to `ui/tabs/player_vs_player.py` rather than recomputing them.
4. Build Captain's Edge and Lineup Optimizer read-only documents. Captain's
   Edge consumes the already-built matrix document for its Opponent Risk
   Profile; it does not rerun analytics.
5. Append optional workbook sheets only when the source document has real rows.
6. Write analysis tabs after JSON artifacts exist.
7. Build captain-first HTML after the final database and scope set exist.
8. Validate every path, hash, flag status, and Player vs Player cross-renderer value before
   presentation.

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
Recommended Avoid/Target fields remain null with
`UNAVAILABLE_NOT_VALIDATED` until a versioned, approved threshold exists. If a
future approved flag is present, every artifact must carry the same boolean,
threshold version, capture time, and availability state. A mismatch blocks the
bundle.

## Packaging

The generated index should link to relative paths only. A release bundle may
include HTML, JSON, XLSX, the redacted manifest, and a README with the capture
time. It must exclude `.env`, `.session_cache`, raw authenticated fixtures,
browser profiles, SQLite backups containing teammate data, and debug logs with
tokens.
