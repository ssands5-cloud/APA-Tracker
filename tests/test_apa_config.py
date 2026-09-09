"""Guards a couple of real, deliberate values in the real apa_config.yaml
that no other test touches -- nothing here exercises pipeline behavior
(see tests/test_full_pipeline_integration.py for that); this only pins
config values a future edit could silently revert.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "apa_config.yaml"

# The filenames apa_stats.xlsx has actually been through during the real
# Excel "we found a problem with some content" investigation -- see
# ui/export_excel.py's DataValidation fix and
# tests/test_export_excel.py::TestGeneratedFileOpensWithoutRepair for the
# real, byte-level root cause that was found and fixed. The rename to a
# never-before-used name was a separate, deliberate step on top of that
# fix (to rule out any stale Excel-side state tied to the old name/path),
# not a second bug fix -- see this test's own docstring.
RETIRED_EXCEL_OUTPUT_NAMES = {
    "exports/apa_stats.xlsx",
    "exports/apa_stats_clean.xlsx",
    "exports/apa_stats_final.xlsx",
}


def _load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


class TestRealExportPaths:
    def test_excel_output_path_is_the_current_post_rename_filename(self):
        config = _load_config()
        assert config["export"]["excel_output_path"] == "exports/apa_stats_fresh.xlsx"

    def test_excel_output_path_is_not_a_retired_pre_rename_name(self):
        """Pins the rename itself -- fails loudly if apa_config.yaml is
        ever edited back to a name Excel has already seen under this
        investigation."""
        config = _load_config()
        assert config["export"]["excel_output_path"] not in RETIRED_EXCEL_OUTPUT_NAMES

    def test_json_output_path_was_not_touched_by_the_excel_rename(self):
        """The rename is scoped to the Excel artifact only -- the JSON
        export's own path is a different, unrelated concern."""
        config = _load_config()
        assert config["export"]["json_output_path"] == "exports/apa_data.json"


class TestLineupOptimizerWeights:
    """The real, already-verified weights from analytics/lineup_optimizer.py
    (WEIGHT_MATCHUP_SCORE etc.), made discoverable/overridable here without
    changing the formula's default behavior -- see
    scripts.build_lineups.load_weights_from_config."""

    def test_configured_weights_match_the_modules_own_defaults(self):
        from analytics.lineup_optimizer import DEFAULT_WEIGHTS

        config = _load_config()
        section = config["lineup_optimizer"]
        assert section["weight_matchup_score"] == DEFAULT_WEIGHTS.matchup_score
        assert section["weight_win_probability"] == DEFAULT_WEIGHTS.win_probability
        assert section["weight_confidence"] == DEFAULT_WEIGHTS.confidence
        assert section["weight_risk_penalty"] == DEFAULT_WEIGHTS.risk_penalty

    def test_modeled_win_probability_weight_defaults_to_off(self):
        """0.0 by default: analytics.win_probability's estimate must never
        silently start influencing real lineups just because this section
        exists -- see LineupWeights.modeled_win_probability's own
        docstring."""
        config = _load_config()
        assert config["lineup_optimizer"]["weight_modeled_win_probability"] == 0.0


class TestWinProbabilityWeights:
    """The real, direction-checked-against-real-data weights from
    analytics/win_probability.py -- see docs/win_probability.md for what
    was verified before these defaults were picked, and why there is no
    race-difficulty weight here (a documented v1 gap, not an omission)."""

    def test_configured_weights_match_the_modules_own_defaults(self):
        from analytics.win_probability import DEFAULT_WIN_PROBABILITY_WEIGHTS

        config = _load_config()
        section = config["win_probability"]
        assert section["weight_sl_delta"] == DEFAULT_WIN_PROBABILITY_WEIGHTS.sl_delta
        assert section["weight_wr_sl"] == DEFAULT_WIN_PROBABILITY_WEIGHTS.wr_sl
        assert section["weight_wr_h2h"] == DEFAULT_WIN_PROBABILITY_WEIGHTS.wr_h2h
        assert section["weight_volatility"] == DEFAULT_WIN_PROBABILITY_WEIGHTS.volatility
        assert section["logistic_scale"] == DEFAULT_WIN_PROBABILITY_WEIGHTS.logistic_scale
        assert section["clamp_min"] == DEFAULT_WIN_PROBABILITY_WEIGHTS.clamp_min
        assert section["clamp_max"] == DEFAULT_WIN_PROBABILITY_WEIGHTS.clamp_max

    def test_no_race_difficulty_weight_is_configured(self):
        """Pins the documented v1 gap: no weight_race_difficulty key at
        all, rather than one silently multiplying the fixed 0.0 placeholder
        in analytics.win_probability.race_difficulty()."""
        config = _load_config()
        assert "weight_race_difficulty" not in config["win_probability"]


class TestLineupRiskWeights:
    """analytics/lineup_risk.py's real, team-level risk weights -- see
    docs/lineup_risk.md."""

    def test_configured_weights_match_the_modules_own_defaults(self):
        from analytics.lineup_risk import DEFAULT_LINEUP_RISK_WEIGHTS

        config = _load_config()
        section = config["lineup_risk"]
        assert section["weight_upset_risk"] == DEFAULT_LINEUP_RISK_WEIGHTS.upset_risk
        assert section["weight_anchor_instability"] == DEFAULT_LINEUP_RISK_WEIGHTS.anchor_instability
        assert section["weight_volatility_load"] == DEFAULT_LINEUP_RISK_WEIGHTS.volatility_load
        assert section["weight_danger_count"] == DEFAULT_LINEUP_RISK_WEIGHTS.danger_count
        assert section["danger_threshold"] == DEFAULT_LINEUP_RISK_WEIGHTS.danger_threshold


class TestRationaleToggles:
    """analytics/rationale.py's real toggles -- see docs/lineup_risk.md
    and analytics/rationale.py's own module docstring for why per-pairing
    rationale (already real, already shipped elsewhere) isn't duplicated
    here."""

    def test_configured_toggle_matches_the_modules_own_default(self):
        from analytics.rationale import DEFAULT_RATIONALE_TOGGLES

        config = _load_config()
        section = config["rationale"]
        assert section["include_lineup_rationale"] == DEFAULT_RATIONALE_TOGGLES.include_lineup_rationale


class TestOpponentScoutingThresholds:
    """analytics/opponent_scouting.py's real "this opponent is dangerous"
    thresholds -- see docs/opponent_scouting.md."""

    def test_configured_thresholds_match_the_modules_own_defaults(self):
        from analytics.opponent_scouting import DEFAULT_OPPONENT_SCOUTING_THRESHOLDS

        config = _load_config()
        section = config["opponent_scouting"]
        assert section["win_probability_danger_threshold"] == DEFAULT_OPPONENT_SCOUTING_THRESHOLDS.win_probability_danger
        assert section["volatility_danger_threshold"] == DEFAULT_OPPONENT_SCOUTING_THRESHOLDS.volatility_danger
