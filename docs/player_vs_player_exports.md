# Player vs Player export integration

`analytics/player_vs_player.py` owns one deliberately selected comparison.
`analytics/player_vs_player_matrix.py` owns whole-scope composition. The
implemented export is the whole matrix with the explicit pair fragments
embedded as drill-down details; the analytics ownership remains separate.

## Architecture and data sources

`database.queries.head_to_head_history(db, player_id, opponent_id)` is the
authoritative chronological game source for an explicit comparison. It returns
real `PlayerHeadToHead` rows across all available formats/sessions for the two
IDs; it does not apply the matrix scope. Optional dates come from a query-layer
`Match.match_date` map because the analytics module does not own database I/O.

`analytics/player_vs_player.py::summarize` consumes one exact-pair history and
returns one `PlayerVsPlayerSummary`. It owns recognized record arithmetic,
average skill delta, reliability, skill-only/full probabilities, trends,
projection alias, and `GameRecord` values.

`analytics/pairing_evidence.py::build_pairing_evidence_matrix` owns current
roster cross-product, scope identity, DIRECT/INDIRECT/UNKNOWN labels, distinct
DIRECT-match counts, and observed rates. Then
`analytics/player_vs_player_matrix.py::build_matrix_export` combines that
already-built matrix with a caller-supplied history map. It does not query the
database, rebuild rosters, or create another score.

`scripts/build_player_vs_player_export.py` is the implemented read-only query
and assembly boundary. It fetches Stage 1 evidence, exact histories, and real
dates once, then sends one row sequence to the HTML and Excel renderers.

This scope asymmetry is visible: the matrix label/rate belong to the selected
team/opponent/format/session, while the nested explicit comparison is labeled
all-history and each game retains its own format/session. A renderer must not
describe the pair summary as selected-format/session history unless a future
query explicitly filters and records that filter.

## Artifacts and inputs

The implemented matrix artifacts are:

- `exports/player_vs_player.html` — every feasible pair plus an anchored
  explicit-pair detail for each row;
- `exports/player_vs_player.xlsx` — the same matrix and its real game history.

The export adapter receives the stable `PlayerVsPlayerExportRow` sequence from
the matrix module. Each row nests one `PlayerVsPlayerSummary`. Renderers do not
query data or call analytics.

## Analytics consumption

The summary supplies DIRECT exact-pair game history and these values:

- `total_games`, `wins`, and `losses` over recognized game rows;
- `sl_delta`, the average posted opponent-minus-own skill difference;
- `reliability`, delegated to `reliability_weight(total_games)`;
- `skill_only_probability`, labeled **Last recorded skill probability** because
  it uses the last real game's posted skill levels;
- `modeled_win_probability`, the existing history-plus-last-recorded-skill
  result, shown only as experimental context;
- `trend` and `recent_trend` over the full and recent explicit-pair histories;
- `next_match_projection`, an exact alias of `modeled_win_probability`, not a
  schedule-aware forecast;
- chronological `GameRecord` values.

The selected matrix row may add Stage 1 evidence label, distinct DIRECT-match
count, observed rate, current roster skill levels, and team/scope identity.
Those fields remain attributed to Stage 1 and are not recomputed.

Innings, per-opponent defense average, per-opponent break/run rate, and numeric
volatility are not produced by the explicit-pair analytics contract. Exports
show named unavailable disclosures and never substitute a proxy.

## Ordering and no-data rules

Matrix rows keep the module's structural order; game records keep the
analytics-provided chronological order. A pair is fixed by external IDs plus
format/session; names never establish identity. A pair with no recognized
history still produces an honest detail state: 0 games, 0-0 record, zero
reliability, null probabilities and projection, `no data` trends, and no
timeline entries.

If its matrix evidence label is UNKNOWN, that label remains visible. UNKNOWN
does not become observed 0%, 50%, or a modeled recommendation.

Recommended Avoid (`danger_flag`) and Recommended Target (`favorable_flag`)
are reserved, audit-gated export fields. Current validation does not establish
a held-out rematch threshold for either flag, so they remain null with status
`UNAVAILABLE_NOT_VALIDATED`. No renderer may manufacture them from modeled
probability, trend, volatility, or color.

## Deterministic formatting and audit constraints

- HTML/JSON are UTF-8 and Excel external IDs are stored as text.
- Current HTML percentages display as whole percentages and reliability/skill
  delta use three decimals; Excel retains raw numeric values. Parity compares
  source values before HTML rounding.
- Captured text is escaped; workbook widths/styles and column order are fixed.
- No volatile formulas, random identifiers, viewer-clock values, external
  links, macros, or hidden helper sheets.
- No fabricated values, heuristic blending, renderer math, name-based joins,
  or schedule claims.
- The modeled probability and identical projection alias carry the same
  experimental validation warning and may not drive recommendations.
- A future flag requires a versioned threshold specification, named training
  and holdout cohorts, calibration/decision metrics, approval, and provenance.
  Until then Captain's Edge may show the risk evidence profile but no
  Recommended Avoid/Target assertion.

## Planned wiring

| Module | Responsibility |
| --- | --- |
| `analytics/player_vs_player.py` | Existing pure computation for one explicit pair |
| `analytics/player_vs_player_matrix.py` | Existing pure whole-matrix composition |
| `ui/tabs/player_vs_player.py` | Existing explicit-pair HTML fragment |
| `ui/export_html_player_vs_player.py` | Existing matrix HTML that embeds each explicit fragment |
| `ui/export_excel_player_vs_player.py` | Existing matrix workbook renderer |
| `scripts/build_player_vs_player_export.py` | Existing read-only database builder for one scope |
| `exports/html_builder.py` | Future demo wrapper delegates to the existing HTML renderer |
| `exports/excel_builder.py` | Future demo wrapper delegates to the existing Excel renderer |
| `ui/router.py` | Future navigation resolves a matrix scope and row/detail anchor |
| `demo.py` | Future orchestration invokes the matrix build once and registers/verifies both artifacts |

The whole-matrix renderer must consume only matrix rows. The explicit-pair
renderer remains independently callable as a component and must never infer or
rebuild the cross-product. Full matrix details live in
`player_vs_player_matrix.md`.
