# Unified Player vs Player HTML structure

The target experience is one top-level **Player vs Player** tab with two
presentation subviews:

- **Pair View** — one explicit player/opponent comparison owned by
  `analytics/player_vs_player.py`;
- **Matrix View** — every feasible pair in the selected scope, owned by
  `analytics/player_vs_player_matrix.py`.

The subviews share scope, identity, and provenance, but they do not share or
blend analytics formulas. The current standalone matrix export already embeds
the existing pair fragment at row anchors; the unified tab formalizes that
relationship inside the existing `ui/tabs` composition model.

## Page structure

```text
section#player-vs-player-tab
├── header#pvp-header
│   ├── team / opponent / format / session
│   ├── capture timestamp and source-manifest ID
│   └── model-validation and snapshot banners
├── nav#pvp-subviews (tablist)
│   ├── button#pvp-pair-tab   "Pair View"
│   └── button#pvp-matrix-tab "Matrix View"
├── section#pvp-pair-view (tabpanel)
│   ├── player and opponent selectors
│   ├── evidence / record cards
│   ├── table#pvp-pair-metrics
│   ├── figure#pvp-game-timeline
│   ├── table#pvp-game-history
│   ├── section#pvp-risk-profile
│   └── unavailable-data disclosure
├── section#pvp-matrix-view (tabpanel)
│   ├── player / opponent / evidence filters and Reset
│   ├── figure#pvp-difficulty-heatmap
│   ├── figure#pvp-coverage-chart
│   ├── table#pvp-matrix-table
│   └── matrix-level audit disclosure
└── footer#pvp-provenance
```

Pair View is the default when valid pair IDs are present in the route; Matrix
View is the default when only a scope is present. Switching subviews changes
visibility and URL state only. It never refetches data or recalculates a field.

## Routing model

The future `ui/router.py` owns one navigation entry, `player-vs-player`, with a
`view` parameter:

```text
player-vs-player?view=matrix&our_team_id=...&opponent_team_id=...&format=...&session=...
player-vs-player?view=pair&player_id=...&opponent_id=...&our_team_id=...&opponent_team_id=...&format=...&session=...
```

IDs in the static export may be encoded in fragment state instead of a query
string. In either form, external IDs plus the complete scope are authoritative;
names are display metadata. A pair route is valid only when its key exists in
the already-built matrix. Invalid, ambiguous, or stale state opens Matrix View
with an explicit error and no guessed selection.

Back/forward navigation must restore both subview and selected pair. Selecting
a matrix row changes the subview to Pair View and focuses the pair heading.
Returning to Matrix View restores the previous filters and scroll position.

## Script JSON contract

The orchestrator serializes one escaped JSON document into a non-executable
`<script type="application/json" id="pvp-data">` element. The document contains:

- schema version, run ID, capture time, and source hash;
- canonical scope and expected pair keys;
- ordered matrix rows and counts;
- each row's nested explicit `PlayerVsPlayerSummary` and chronological games;
- source/model status and unavailable-field disclosures;
- descriptive profile fields and the active presentation sort key/direction.
- one difficulty cell per matrix pair with both current skill inputs, shared
  current-skill probability, raw difficulty, formula version, and null reason.

The tab reads this element once with `textContent` and `JSON.parse`. It validates
the schema version and pair-key uniqueness before enabling controls. Script JSON
must use the repository's safe serializer so `<`, `>`, `&`, and script-closing
sequences cannot break out of the element. No captured string is inserted with
`innerHTML`; DOM text uses `textContent` or server-rendered escaped markup.

The browser may select, filter, sort a copy for display, switch subviews, and
draw inline SVG from delivered values. It may not query SQLite, fetch a URL,
call an analytics formula, fill a null, or write a recommendation.

## Pair View

The player and opponent selectors list only canonical matrix identities. The
selected pair shows:

- evidence label, distinct DIRECT matches, and observed win rate;
- an explicit label that Stage 1 evidence is selected-scope while the current
  pair summary is chronological all-history across formats/sessions;
- current roster skill levels, clearly separated from last-recorded game skills;
- recognized games, wins/losses, average skill delta, and reliability;
- last-recorded skill-only probability;
- experimental modeled win probability and identical projection alias;
- full-history and recent trends;
- an **Opponent Risk Profile** panel described below;
- chronological game history and the existing inline-SVG result timeline.

The metric table never collapses observed rate, reliability, skill probability,
and modeled probability into one score. The timeline sits below the evidence
cards and above the game table; it contains one accessible marker per real
game. Missing dates use match ID, not a generated date.

### Opponent Risk Profile

This panel is a sourced descriptive summary, not a classifier or recommendation
engine. It lists evidence class, sample counts, observed record,
last-recorded skill probability, experimental modeled-value status, trends,
availability, and capture time.

The profile may display opponents in canonical name/ID order or let the user
sort by one visible source field at a time. The heading must state the active
field and direction, for example “Sorted by direct matches, descending —
descriptive only.” Nulls sort last and ties use canonical opponent name/external
ID. No composite risk score, hidden weighting, or browser calculation exists.

There are no Recommended Avoid, Recommended Target, danger, favorable, risk-
tier, traffic-light, or equivalent categorical flags. In particular,
`modeled_win_probability`, trend, volatility, observed rate, and reliability
cannot be thresholded into a category. The experimental modeled value may be
shown as a separately labeled fact but is not the default ranking field.

## Matrix View

The initial table order is structural: session, 8-ball before 9-ball, player
name/external ID, then opponent name/external ID. The required columns are:

1. Player and current SL
2. Opponent and current SL
3. Evidence label
4. Distinct DIRECT matches
5. Observed win rate
6. Recognized games and W-L record
7. History reliability
8. Last-recorded skill probability
9. Modeled win probability (experimental)
10. Full/recent trend
11. Details action

The coverage chart sits above the table and shows counts—not scores—for DIRECT,
INDIRECT, and UNKNOWN. It is an accessible inline SVG or semantic bar group with
the numeric counts repeated in text. It never ranks players.

### Match Difficulty Heatmap

The heatmap sits between the filters and evidence-coverage chart. Rows are our
players; columns are opponents. Its cell value is the precomputed
`100 * (1 - current_skill_probability)` from the shared validated
`skill_only_win_probability` function and current matrix skill levels. The
browser only maps delivered values to fixed presentation bins.

The sequential numeric legend is 0–<20 `#eff3ff`, 20–<40 `#bdd7e7`, 40–<60
`#6baed6`, 60–<80 `#3182bd`, and 80–100 `#08519c`. Range labels remain numeric;
there are no easy/hard, danger/favorable, Avoid/Target, or traffic-light labels.
The full formula and “current-skill-only baseline” label appear next to the
legend.

Each cell prints a whole-number difficulty value, has an accessible label with
both player identities/current skills/evidence label/raw source probability,
and opens the existing Pair View. DIRECT uses a solid outline, INDIRECT a
dashed outline, and UNKNOWN/missing-skill data a gray hatched `No data` cell.
The border communicates evidence only; it does not change the fill value.

Default axes use canonical player/opponent name and external-ID order. A user
may sort an axis by its visible name or current skill header, nulls last, with
identity tie-breaks. Cells, observed results, modeled probability, trends, and
volatility cannot drive axis order. Reset restores canonical order and the
previous Pair View selection remains addressable by pair key.

The heatmap never consumes the experimental history-blended
`modeled_win_probability`. A null current-skill probability remains `No data`,
not 50, and is excluded from numeric-bin counts. The evidence matrix still
contains every feasible pair, including UNKNOWN.

Filters hide rows only by explicit user action. Reset restores every row and
the canonical source order. Sorting is keyboard-operable, declares direction,
places `No data` last, and never changes the exported source order. Details
opens the same row in Pair View.

## UNKNOWN and missing data

UNKNOWN rows remain visible by default. A no-history pair shows 0 games, 0-0,
zero reliability, null probabilities, `no data` trends, and no timeline
markers. A missing value displays `No data` plus a reason; a measured zero stays
numeric zero. There is no 50% fallback.

Innings, per-opponent defense, per-opponent break/run rate, and pair-specific
numeric volatility are named unavailable fields. The UI never substitutes
lifetime defense. A separately joined Opponent Volatility Profile may show
overall player/format/session skill-level variation only with a visible **not
pair-specific** label; it does not fill the pair-specific gap. Missing roster
identity blocks matrix construction instead of inferring membership from
historical play.

### Data Coverage bridge

Matrix View's evidence-count heading and every UNKNOWN row include a
presentation link to the unified Data Coverage tab. Pair View links missing
skill, sample-size, refresh, and unavailable-field disclosures to the matching
Data Coverage section. The route carries only a stable section/pair key; the
coverage report is already embedded and is never recalculated or narrowed at
the source. Returning to Player vs Player restores the prior subview, selection,
filters, and scroll position.

## Accessibility, safety, and deterministic formatting

- Subview controls implement tab/tabpanel roles, keyboard arrows, focus
  management, and visible focus.
- Tables use captions, scoped headers, and a horizontal overflow container.
- Evidence uses text/icons as well as color; profile rows use no risk-category
  color coding.
- HTML is UTF-8 and self-contained, with no external scripts, fonts, images, or
  runtime network requests.
- Percentages display as whole percentages to match the current renderer;
  reliability and skill delta use three decimals. Parity uses raw values before
  rounding.
- IDs, element order, disclosures, and initial row order derive from stable
  source keys, never random values or the viewer's clock.
