# Demo exports integration plan

All demo artifacts must be produced from one regenerated SQLite database and
one run configuration. `pipeline/exports.py` remains the composition point;
the future launcher should call it rather than duplicating exporter logic.

## Artifact contract

| Artifact | Builder | Demo role | Required validation |
| --- | --- | --- | --- |
| `captain_first_edge.html` | `scripts/build_captain_first_edge.py` + `ui/tabs/tonights_match.py` | Primary Tonight's Match, Lineup Lab, Data Coverage view | self-contained HTML, scope/evidence reconciliation, no external requests |
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
3. Build Captain's Edge and Lineup Optimizer read-only documents.
4. Append optional workbook sheets only when the source document has real rows.
5. Write analysis tabs after JSON artifacts exist.
6. Build captain-first HTML last so it sees the final database and scope set.
7. Validate every path and hash before presentation.

## Cross-artifact consistency

The manifest must record one database hash (or immutable file hash before
serving) for every artifact. The selected team, opponent, format, and session
must match across HTML controls, JSON scopes, and workbook rows. Observed win
rates and modeled probabilities keep distinct labels everywhere. “No data” and
“unavailable” are display contracts, not missing JSON keys silently interpreted
as zeros.

## Packaging

The generated index should link to relative paths only. A release bundle may
include HTML, JSON, XLSX, the redacted manifest, and a README with the capture
time. It must exclude `.env`, `.session_cache`, raw authenticated fixtures,
browser profiles, SQLite backups containing teammate data, and debug logs with
tokens.

