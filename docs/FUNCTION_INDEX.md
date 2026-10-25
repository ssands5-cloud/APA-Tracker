# APA Tracker — Function Index

The 30 most-referenced functions across the codebase. Sorted by layer, then importance.

---

## Pipeline entry points

### `run_game_night.main()`
`scripts/run_game_night.py`  
Primary operator workflow. Stages DB → builds cockpit → validates → promotes. Start here when working on the end-to-end refresh flow.

### `acquire_current_sources(config, seed_database)`
`pipeline/refresh_sources.py`  
Downloads or loads cached APA fixture JSON. Returns a `FixtureStore`. Entry point for the data acquisition layer.

### `replay_ingest(config, fixtures)`
`pipeline/ultimate_coach_refresh.py`  
Reproduces the UC staging DB from captured fixtures. Core of the reproducible-build path.

### `run(db)`
`pipeline/ingest.py`  
Ingests teams, matches, history from a `FixtureStore` into a `Session`. Calls `rebuild_matchups` and `rebuild_analytics` at the end.

---

## Database layer

### `create_db_engine(config)`
`database/engine.py`  
Creates the SQLite engine, enables FK constraints, checks schema version. Raises `StaleSchemaError` if columns are missing. Called at every script startup.

### `check_schema(engine) → list[str]`
`database/engine.py`  
Returns descriptions of model columns the file lacks. Empty = schema OK.

### `ingest_match(db, match_data)`
`database/ingest.py`  
Upserts one match and all its `PlayerMatch` rows. The write boundary for match data.

### `player_match_history(db, player_id) → list[PlayerMatch]`
`database/queries.py`  
Primary read path for per-player match records used by every analytics engine.

---

## Analytics — identity and evidence

### `build_contract(db) → DataContract`
`analytics/ultimate_coach_data_contract.py`  
Canonical data contract for Ultimate Coach. All downstream UC analytics start here. Returns normalized game rows, team matches, and player identity index.

### `build_verified_identity_manifest(contract) → IdentityManifest`
`analytics/ultimate_coach_identity_manifest.py`  
Resolves every player to VERIFIED_UNIQUE canonical identity. Suspect/ambiguous identities are quarantined — never silently dropped.

### `build_verified_cockpit_payload(contract, manifest, audit) → dict`
`analytics/ultimate_coach_cockpit_identity_bridge.py`  
Wires identity gate into the full cockpit payload. Only VERIFIED_UNIQUE identities are selectable; quarantined games are counted and surfaced, never hidden.

### `build_ultimate_coach_payload(db) → dict`
`analytics/ultimate_coach_payload.py`  
Full UC payload — all pairings, all evidence, all players. Used by HTML and Excel builders.

### `build_scouting_evidence(db, our_team_id, opponent_team_id) → ScoutingEvidence`
`analytics/scouting_evidence.py`  
Cross-references shared opponents to build indirect evidence between our players and theirs. Foundation for `PairingEvidenceMatrix`.

---

## Analytics — lineup recommendations

### `match_plan(ours, theirs, grid, scale) → Plan`
`analytics/match_night_engine.py`  
Core lineup recommendation engine. Returns `Plan` with `lead`, `holds`, `protect`, `bestBoard`, `safestBoard`. Called by War Room.

### `plan_for_war_room(war_room) → WarRoomPlan`
`analytics/match_night_engine.py`  
Adapts `match_plan` output for the live War Room decision flow.

### `check_lineup_legality(lineup, format) → LineupLegality`
`analytics/lineup_legality.py`  
Validates a proposed lineup against the 23-Rule and format requirements. Returns legality status and violations.

### `matchup_score(win_probability, risk_factor) → int`
`analytics/captains_edge.py`  
Composite score for one pairing. Input to the optimizer and ranking tables.

### `risk_factor(volatility, direct_evidence_count) → float`
`analytics/captains_edge.py`  
Penalizes pairings with high variance and thin direct evidence.

### `pair_confidence(direct, shared, sl_delta) → ConfidenceLevel`
`analytics/ultimate_coach_confidence.py`  
Evidence-weighted confidence for a specific pairing. Used to populate `evidence[our][their].level`.

---

## Analytics — evidence labels

### `evidenceLabel(level: string) → string`
`apps/ultimate-coach-web/src/lib/evidence-label.ts`  
**Must be called on every evidence level before display.** Maps: Strong/Solid/Thin → "X Evidence"; Unknown/Caution/Conflicted pass through unchanged. Never use raw `level` strings in UI.

### `EvidenceLabel` (enum)
`analytics/pairing_evidence.py`  
Python-side equivalent. Values: STRONG, SOLID, THIN, UNKNOWN, CAUTION, CONFLICTED.

---

## Analytics — player/team stats

### `summarize_player(player_name, db) → PlayerStatLine`
`analytics/player_stats.py`  
Win/loss record, average SL, recent form for one player. Used by multiple tabs.

### `skill_level_trend(matches) → float`
`analytics/skill_level_trends.py`  
Regression slope over recent skill levels. Positive = improving. Used in player trend cards.

### `build_report(db, team_id, session) → TeamStrengthReport`
`analytics/team_strength.py`  
Offense/defense/depth scores for the team. Used by Team Strength tab.

### `build_ranked_opponents(matrix) → list[RankedOpponent]`
`analytics/team_matchup_engine.py`  
Ranks opponents by pooled direct record and reliability-weighted skill probability. The Team Matchup Engine output.

---

## Web app — server-side

### `authorizedSnapshot(userId, snapshotId) → SnapshotResult`
`apps/ultimate-coach-web/src/lib/server/historical-snapshot.ts`  
Server-only. Checks role, decrypts snapshot, returns `Snapshot` or error. **Never call from client components.**

### `historicalAccess(userId) → AccessResult`
`apps/ultimate-coach-web/src/lib/server/authorization.ts`  
Server-only role gate. Returns allowed access level. Admin page uses this to return 404 to non-admins.

### `decryptSnapshot(enc: string) → Snapshot`
`apps/ultimate-coach-web/src/lib/server/snapshot-crypto.ts`  
AES-256-GCM decryption using `UC_SNAPSHOT_KEY`. Only called server-side.

### `execute(sql, args) → ResultSet`
`apps/ultimate-coach-web/src/lib/db/client.ts`  
Turso HTTP client. All DB reads/writes in the web app go through this. Uses `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN`.

---

## Web app — output

### `build_verified_cockpit_payload(...)` → Python → JSON → `_browser_payload(...)`
`ui/ultimate_coach.py` → `_browser_payload(payload)`  
Serializes the Python payload as a `<script>` JSON block embedded in the HTML artifact. The `_StringTable` deduplicates repeated strings for size. **Never puts snapshot URL in the payload.**

### `write_site(out, payload, passphrase)`
`ui/match_night.py`  
Encrypts the Match Night HTML artifact with AES-256-GCM and writes a self-contained static site. The captain opens this at the venue; it decrypts in-browser with the passphrase.

---

## Utility / guards

### `ensure_data_dirs()`
`scripts/paths.py`  
Creates all 11 `D:\APA-Tracker-Data\` subdirectories if absent. Call at script startup before any file I/O.

### `run_git(cwd, *args) → str` / `same(a, b) → bool`
`scripts/repo_boundary.py`  
Boundary checks used by the publish script and UAT. Prevents writes to wrong worktrees.

### `sha256_file(path) → str`
Multiple scripts (e.g. `scripts/build_ultimate_coach_production.py`)  
SHA-256 checksum of a file. Used for artifact integrity verification at every promotion step.
