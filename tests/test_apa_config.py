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
