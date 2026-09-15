# Production demo flow diagram

The production demo is a one-way, fail-closed flow. The browser is opened only
after the data build and artifact checks succeed.

```mermaid
flowchart TD
    A[Operator chooses live or fixture mode] --> B[Preflight]
    B -->|Python/dependencies/config valid| C{Live scrape?}
    B -->|Failure| Z[Stop with actionable report]
    C -->|Yes| D[Authenticated login and consent]
    C -->|No| E[Use selected fixture tree]
    D -->|Authorized| F[Scrape teams, divisions, matches, aliases]
    D -->|Expired/unauthorized| Z
    F --> G[Validate fixture manifest and sensitive-file rules]
    E --> G
    G --> H[Create fresh scratch SQLite]
    H --> I[Ingest rosters, schedules, scores, TeamStat history]
    I --> J[Rebuild matchup and trend aggregates]
    J --> K[Run schema, referential, and coverage checks]
    K -->|Fail| Z
    K --> L[Build general JSON, XLSX, Lineup Lab, and analysis tabs]
    L --> PVPA[Build Player vs Player Matrix from Stage 1 plus exact histories]
    PVPA --> DCA[Build denominated Data Coverage report]
    DCA --> PVPJ[Encode escaped Player vs Player and Coverage script JSON]
    PVPJ --> PVPM[Render Player vs Player and Data Coverage HTML/Excel]
    PVPM --> M[Build Captain's Edge and captain-first HTML from same matrix]
    M --> N[Check manifest, HTML safety, and cross-export parity]
    N -->|Fail| Z
    N --> O[Open static demo index / captain-first page]
    O --> P[Walk through Tonight's Match]
    P --> PVPT[Open unified Player vs Player tab]
    PVPT --> PVPMV[Matrix View: inspect every feasible pair]
    PVPMV --> PVP[Pair View: inspect one explicit comparison]
    PVP --> RISK[Opponent Risk Profile and flag status]
    RISK --> Q[Lineup Lab]
    Q --> DC[Data Coverage: denominators, gaps, and source status]
    DC --> R[Export review and evidence capture]
    R --> S[Archive manifest and release notes]
```

## Operator timeline

1. Select a mode and output directory. The production launcher must require
   an explicit choice so a rehearsal cannot silently make a live network call.
2. Run preflight: repository root, Python 3.12/3.13, pinned dependencies,
   Playwright browser (live mode), config, output permissions, and absence of
   credentials in the output tree.
3. In live mode, complete login and the guarded “Continue to Member Services”
   consent step. In fixture mode, verify the fixture manifest instead.
4. Build a new database in scratch space. Never reuse an old database merely
   because it exists; an older file can lack `player_team_history.team_external_id`.
5. Ingest and rebuild analytics. Commit timestamps, source IDs, and row counts
   to the run manifest.
6. Build all artifacts, including the unified Player vs Player tab and matrix
   workbook from one escaped JSON/source document; validate containment and
   cross-renderer parity before opening a browser.
7. Present `captain_first_edge.html` first, open Player vs Player, inspect
   Matrix View, switch to Pair View, review Opponent Risk Profile status, then
   show Lineup Lab, Data Coverage, analysis tabs, and workbooks.
8. Preserve the manifest and checksums as the demo evidence package. Remove
   temporary credentials and browser state; retain only approved outputs.

## Failure branches

- Authentication failure: stop; do not fall back to a stale database.
- Missing current-roster identity: keep the real scope visible as unavailable;
  do not infer membership from historical `PlayerMatch` rows.
- Stale schema: report the missing model columns and require regeneration.
- No scoreable Lineup Lab edges: show the matrix and explicit unassigned lists;
  do not manufacture a lineup.
- Matrix or explicit-pair parity failure: stop; do not present HTML and Excel
  that disagree about a pair, label, null, game, or probability.
- HTML or artifact validation failure: do not open the page as a “best effort.”
