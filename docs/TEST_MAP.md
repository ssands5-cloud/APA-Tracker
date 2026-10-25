# APA Tracker — Test Map

**171 test files.** 106 map 1:1 to a source module by name. 63 are integration, browser, fixture, or cross-cutting tests with no single source owner (listed by category below). 2 are TypeScript (`node:test`); the rest are Python (`pytest`).

**Run all Python tests:** `pytest tests/`  
**Run TypeScript tests:** `node --experimental-strip-types apps/ultimate-coach-web/tests/*.test.ts`  
**Primary CI gate:** `tests/captain-command.test.ts` (TypeScript, captain-command component)

---

## Module → test mapping (1:1)

### `analytics/`

| Module | Test file |
|--------|-----------|
| `analytics/backtest_dataset.py` | `tests/test_backtest_dataset.py` |
| `analytics/baseline_evaluation.py` | `tests/test_baseline_evaluation.py` |
| `analytics/calibration_metrics.py` | `tests/test_calibration_metrics.py` |
| `analytics/captains_edge_summary.py` | `tests/test_captains_edge_summary.py` |
| `analytics/close_match_performance.py` | `tests/test_close_match_performance.py` |
| `analytics/data_coverage.py` | `tests/test_data_coverage.py` |
| `analytics/head_to_head.py` | `tests/test_head_to_head.py` |
| `analytics/lineup_lab.py` | `tests/test_lineup_lab.py` |
| `analytics/lineup_legality.py` | `tests/test_lineup_legality.py` |
| `analytics/lineup_optimizer.py` | `tests/test_lineup_optimizer.py` |
| `analytics/lineup_risk.py` | `tests/test_lineup_risk.py` |
| `analytics/match_night_engine.py` | `tests/test_match_night_engine.py` |
| `analytics/matchup_builder.py` | `tests/test_matchup_builder.py` |
| `analytics/matchup_candidate_model.py` | `tests/test_matchup_candidate_model.py` |
| `analytics/matchups.py` | `tests/test_matchups.py` |
| `analytics/opponent_risk_profile.py` | `tests/test_opponent_risk_profile.py` |
| `analytics/opponent_scouting.py` | `tests/test_opponent_scouting.py` |
| `analytics/opponent_volatility.py` | `tests/test_opponent_volatility.py` |
| `analytics/pairing_evidence.py` | `tests/test_pairing_evidence.py` |
| `analytics/player_matchup_engine.py` | `tests/test_player_matchup_engine.py` |
| `analytics/player_matchup_explorer.py` | `tests/test_player_matchup_explorer.py` |
| `analytics/player_trends.py` | `tests/test_player_trends.py` |
| `analytics/player_vs_player.py` | `tests/test_player_vs_player.py` |
| `analytics/player_vs_player_matrix.py` | `tests/test_player_vs_player_matrix.py` |
| `analytics/prediction_validation.py` | `tests/test_prediction_validation.py` |
| `analytics/rationale.py` | `tests/test_rationale.py` |
| `analytics/scouting_evidence.py` | `tests/test_scouting_evidence.py` |
| `analytics/season_projection.py` | `tests/test_season_projection.py` |
| `analytics/skill_level_trends.py` | `tests/test_skill_level_trends.py` |
| `analytics/team_matchup_engine.py` | `tests/test_team_matchup_engine.py` |
| `analytics/team_stats.py` | `tests/test_team_stats.py` |
| `analytics/team_strength.py` | `tests/test_team_strength.py` |
| `analytics/trend_analyzer.py` | `tests/test_trend_analyzer.py` |
| `analytics/ultimate_coach_all_player_enrichment.py` | `tests/test_ultimate_coach_all_player_enrichment.py` |
| `analytics/ultimate_coach_backtest_readiness.py` | `tests/test_ultimate_coach_backtest_readiness.py` |
| `analytics/ultimate_coach_chronological_gate.py` | `tests/test_ultimate_coach_chronological_gate.py` |
| `analytics/ultimate_coach_cockpit_identity_bridge.py` | `tests/test_ultimate_coach_cockpit_identity_bridge.py` |
| `analytics/ultimate_coach_data_contract.py` | `tests/test_ultimate_coach_data_contract.py` |
| `analytics/ultimate_coach_evaluation_plan.py` | `tests/test_ultimate_coach_evaluation_plan.py` |
| `analytics/ultimate_coach_evidence_quality.py` | `tests/test_ultimate_coach_evidence_quality.py` |
| `analytics/ultimate_coach_excel_payload.py` | `tests/test_ultimate_coach_excel_payload.py` |
| `analytics/ultimate_coach_identity_manifest.py` | `tests/test_ultimate_coach_identity_manifest.py` |
| `analytics/ultimate_coach_identity_namespace_audit.py` | `tests/test_ultimate_coach_identity_namespace_audit.py` |
| `analytics/ultimate_coach_match_day.py` | `tests/test_ultimate_coach_match_day.py` |
| `analytics/ultimate_coach_matchup_evidence.py` | `tests/test_ultimate_coach_matchup_evidence.py` |
| `analytics/ultimate_coach_player_profiles.py` | `tests/test_ultimate_coach_player_profiles.py` |
| `analytics/ultimate_coach_prequential_features.py` | `tests/test_ultimate_coach_prequential_features.py` |
| `analytics/ultimate_coach_scout_compare.py` | `tests/test_ultimate_coach_scout_compare.py` |
| `analytics/ultimate_coach_war_room.py` | `tests/test_ultimate_coach_war_room.py` |
| `analytics/win_probability.py` | `tests/test_win_probability.py` |

**Analytics modules with no direct test file** (5 — likely tested indirectly):

| Module | Covered indirectly by |
|--------|-----------------------|
| `analytics/captains_edge.py` | `tests/test_captains_edge_summary.py`, `tests/test_build_captains_edge.py` |
| `analytics/matchup_insights.py` | Integration tests |
| `analytics/player_stats.py` | `tests/test_player_stats_scaffolding_fixture.py` |
| `analytics/ultimate_coach_confidence.py` | `tests/test_confidence_levels.py` |
| `analytics/ultimate_coach_payload.py` | `tests/test_ultimate_coach_cockpit.py`, `tests/test_ultimate_coach_browser.py` |

### `ui/`

| Module | Test file |
|--------|-----------|
| `ui/dashboard.py` | `tests/test_dashboard.py` |
| `ui/export_excel.py` | `tests/test_export_excel.py` |
| `ui/export_excel_data_coverage.py` | `tests/test_export_excel_data_coverage.py` |
| `ui/export_excel_opponent_volatility.py` | `tests/test_export_excel_opponent_volatility.py` |
| `ui/export_excel_player_matchup_engine.py` | `tests/test_export_excel_player_matchup_engine.py` |
| `ui/export_excel_player_vs_player.py` | `tests/test_export_excel_player_vs_player.py` |
| `ui/export_excel_season_projection.py` | `tests/test_export_excel_season_projection.py` |
| `ui/export_excel_team_matchup_engine.py` | `tests/test_export_excel_team_matchup_engine.py` |
| `ui/export_excel_team_strength.py` | `tests/test_export_excel_team_strength.py` |
| `ui/export_excel_trend_analyzer.py` | `tests/test_export_excel_trend_analyzer.py` |
| `ui/export_excel_ultimate_coach.py` | `tests/test_export_excel_ultimate_coach.py` |
| `ui/export_html_player_matchup_engine.py` | `tests/test_export_html_player_matchup_engine.py` |
| `ui/export_html_player_vs_player.py` | `tests/test_export_html_player_vs_player.py` |
| `ui/export_html_team_matchup_engine.py` | `tests/test_export_html_team_matchup_engine.py` |
| `ui/export_json.py` | `tests/test_export_json.py` |
| `ui/export_json_coach_advantage.py` | `tests/test_export_json_coach_advantage.py` |
| `ui/match_night.py` | `tests/test_match_night.py` |
| `ui/tabs/captains_edge.py` | `tests/test_captains_edge_summary.py` (indirect) |
| `ui/tabs/data_coverage.py` | `tests/test_data_coverage_tab.py` |
| `ui/tabs/lineup_optimizer.py` | `tests/test_lineup_optimizer_tab.py` |
| `ui/tabs/matchups.py` | `tests/test_pipeline_tabs.py` (indirect) |
| `ui/tabs/opponent_volatility.py` | `tests/test_opponent_volatility_tab.py` |
| `ui/tabs/player_vs_player.py` | `tests/test_player_vs_player_tab.py` |
| `ui/tabs/player_vs_player_unified.py` | `tests/test_player_vs_player_unified_tab.py` |
| `ui/tabs/season_projection.py` | `tests/test_season_projection_tab.py` |
| `ui/tabs/team_strength.py` | `tests/test_team_strength_tab.py` |
| `ui/tabs/tonights_match.py` | `tests/test_tonights_match_tab.py` |
| `ui/tabs/trend_analyzer.py` | `tests/test_trend_analyzer_tab.py` |
| `ui/tabs/trends.py` | `tests/test_pipeline_tabs.py` (indirect) |

### `pipeline/`

| Module | Test file |
|--------|-----------|
| `pipeline/ingest.py` | `tests/test_pipeline_ingest.py`, `tests/test_ingest.py` |
| `pipeline/refresh_progress.py` | `tests/test_refresh_progress.py` |
| `pipeline/refresh_sources.py` | `tests/test_refresh_sources.py` |
| `pipeline/refresh_summary.py` | `tests/test_refresh_summary.py` |
| `pipeline/ultimate_coach_refresh.py` | `tests/test_ultimate_coach_refresh.py` |
| `pipeline/exports.py` | `tests/test_pipeline_exports.py` |

### `database/`

| Module | Test file |
|--------|-----------|
| `database/engine.py` | `tests/test_engine_schema.py` |
| `database/ingest.py` | `tests/test_ingest.py` |
| `database/models.py` | `tests/test_engine_schema.py`, `tests/test_foreign_key_enforcement.py` |

### `scraper/`

| Module | Test file |
|--------|-----------|
| `scraper/auth_classification.py` | `tests/test_auth_classification.py` |
| `scraper/graphql_scraper.py` | `tests/test_graphql_scraper.py` |
| `scraper/historical_archive.py` | `tests/test_historical_archive.py` |
| `scraper/historical_catalog.py` | `tests/test_historical_catalog.py` |
| `scraper/historical_graph.py` | `tests/test_historical_graph.py` |
| `scraper/player_enrichment.py` | `tests/test_player_enrichment.py` |

### `scripts/`

| Module | Test file |
|--------|-----------|
| `scripts/backfill_player_identity.py` | `tests/test_backfill_player_identity.py` |
| `scripts/build_captain_first_edge.py` | `tests/test_build_captain_first_edge.py` |
| `scripts/build_captains_edge.py` | `tests/test_build_captains_edge.py` |
| `scripts/build_coach_advantage_bundle.py` | `tests/test_build_coach_advantage_bundle.py` |
| `scripts/build_coherent_demo.py` | `tests/test_build_coherent_demo.py` |
| `scripts/build_data_coverage.py` | `tests/test_build_data_coverage.py` |
| `scripts/build_demo.py` | `tests/test_build_demo.py` |
| `scripts/build_full_production_demo.py` | `tests/test_build_full_production_demo.py` |
| `scripts/build_lineups.py` | `tests/test_build_lineups.py` |
| `scripts/build_matchups.py` | `tests/test_build_matchups.py` |
| `scripts/build_opponent_volatility.py` | `tests/test_build_opponent_volatility.py` |
| `scripts/build_player_vs_player_export.py` | `tests/test_build_player_vs_player_export.py` |
| `scripts/build_season_projection.py` | `tests/test_build_season_projection.py` |
| `scripts/build_team_strength.py` | `tests/test_build_team_strength.py` |
| `scripts/build_trend_analyzer.py` | `tests/test_build_trend_analyzer.py` |
| `scripts/build_ultimate_coach_production.py` | `tests/test_build_ultimate_coach_production.py` |
| `scripts/publish_match_night.py` | `tests/test_publish_match_night.py` |
| `scripts/refresh_ultimate_coach_current_session.py` | `tests/test_refresh_ultimate_coach_current_session.py` |
| `scripts/render_demo_html.py` | `tests/test_render_demo_html.py` |
| `scripts/replay_confidence_levels.py` | `tests/test_replay_confidence_levels.py` |
| `scripts/repo_boundary.py` | `tests/test_repo_boundary.py` |
| `scripts/reproducible_build.py` | `tests/test_reproducible_build.py` |
| `scripts/run_game_night.py` | `tests/test_game_night_launcher.py` |
| `scripts/run_production_demo.py` | `tests/test_run_production_demo.py` |
| `scripts/scrape_and_ingest.py` | `tests/test_scrape_and_ingest.py` |

**Scripts with no direct test** (one-off tools, research scripts, or covered by integration tests):
`build_head_to_head`, `build_historical_catalog`, `build_historical_dashboard_snapshot`, `build_match_night_package`, `build_player_matchup_explorer`, `build_player_trends`, `build_ultimate_coach_archive`, `build_ultimate_coach_excel`, `build_ultimate_coach_html`, `check_release_candidate`, `enrich_ultimate_coach_players`, `evaluate_ultimate_coach_backtest`, `expand_ultimate_coach_history`, `export_ultimate_coach_data`, `match_night_scale_sensitivity`, `protect_dashboard_snapshot`, `repair_ultimate_coach_historical_identities`, `replay_evidence_rules`, `replay_ordering_rules`, `train_ultimate_coach_candidate`, `validate_predictions`

### `auth/`

| Module | Test file |
|--------|-----------|
| `auth/session_manager.py` | `tests/test_session_manager.py` |
| `auth/login.py` | `tests/test_scrape_and_ingest.py` (indirect via auth flow) |

### `parser/`

| Module | Test file |
|--------|-----------|
| `parser/apa_page_map.py` | `tests/test_apa_page_map.py` |
| `parser/html_parser.py` | `tests/test_html_parser.py` |

### `scheduler/`

| Module | Test file |
|--------|-----------|
| `scheduler/graphql_sync.py` | `tests/test_graphql_sync.py` |

---

## Integration and cross-cutting tests (63 orphan tests)

These don't map 1:1 to a module — they test multi-module flows, browser behavior, fixtures, or feature contracts.

### Integration / pipeline
`test_analytics_integration.py`, `test_full_pipeline_integration.py`, `test_pipeline_ingest.py`, `test_pipeline_exports.py`, `test_pipeline_run_all.py`, `test_pipeline_tabs.py`, `test_incremental_maintenance_scope.py`, `test_live_sync_matchup_rebuild.py`, `test_division_wide_rows.py`, `test_division_wide_sync.py`

### Browser / UI rendering
`test_coach_cockpit_browser.py`, `test_dashboard_browser.py`, `test_match_night_fallback_browser.py`, `test_ultimate_coach_browser.py`, `test_ultimate_coach_browser_runner.py`, `test_ultimate_coach_war_room_browser.py`

### UI tabs (multi-file)
`test_data_coverage_tab.py`, `test_lineup_optimizer_tab.py`, `test_opponent_volatility_tab.py`, `test_player_vs_player_tab.py`, `test_player_vs_player_unified_tab.py`, `test_season_projection_tab.py`, `test_team_strength_tab.py`, `test_tonights_match_tab.py`, `test_trend_analyzer_tab.py`

### Fixture / data loading
`test_dashboard_teams_fixture.py`, `test_division_standings_fixture.py`, `test_match_detail_fixture.py`, `test_matches_by_viewer_fixture.py`, `test_player_stats_scaffolding_fixture.py`, `test_viewer_sync_fixture.py`

### Excel formula
`test_captains_edge_summary_excel.py`, `test_excel_war_room_formulas.py`, `test_lineup_excel.py`, `test_opponent_scouting_excel.py`

### Ultimate Coach multi-module
`test_ultimate_coach_cockpit.py`, `test_ultimate_coach_entrypoints.py`, `test_ultimate_coach_evidence_identity_hardening.py`, `test_ultimate_coach_historical_identity_repair.py`, `test_ultimate_coach_script_entrypoints.py`, `test_ultimate_coach_temporal_integrity.py`, `test_coach_cockpit_data_coverage.py`, `test_cross_surface_trust.py`

### Feature / design contracts
`test_captain_decision_review.py`, `test_captains_decision.py`, `test_confidence_levels.py`, `test_match_night_design_review.py`, `test_next_send_boundaries.py`, `test_recommendation_quality_risks.py`, `test_lineup_fallback_release.py`, `test_live_scope_selection.py`

### Live / scraper
`test_capture_apa_graphql_live_flow.py`, `test_capture_shapes.py`, `test_player_scraper_match_tables.py`, `test_graphql_client_errors.py`

### Infrastructure / config
`test_apa_config.py`, `test_engine_schema.py`, `test_foreign_key_enforcement.py`, `test_game_night_launcher.py`, `test_historical_dashboard_snapshot.py`, `test_release_gate_checker.py`, `test_resolve_roster_identity.py`, `test_career_history_backfill.py`, `test_backfill_player_identity.py` (also in 1:1 map above)

---

## TypeScript tests (`apps/ultimate-coach-web/tests/`)

| File | What it tests |
|------|---------------|
| `captain-command.test.ts` | **Primary CI gate** — CaptainCommand component rendering, snapshot display, evidence labels |
| `browser_smoke.py` | End-to-end browser smoke test |
| `captain-command-layout.py` | Layout and DOM order (aside before .workspace invariant) |
| `private_access.py` | Role-gated access — admin/coach/reviewer/pending paths |
