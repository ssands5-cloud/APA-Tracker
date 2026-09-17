"""Fail-closed source-level release gates for APA Tracker 1.0.

This is intentionally small and deterministic. It does not pretend fixture CI
is a live-data acceptance run and it does not pretend repository protection is
configured. Those operational gates live in docs/release_1_0_hardening.md.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"RELEASE GATE FAILED: {message}")


def main() -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    require(version == "1.0.0-rc1", f"unexpected pre-release version {version!r}")

    rules = (ROOT / "analytics" / "lineup_legality.py").read_text(encoding="utf-8")
    require("TEAM_SKILL_LEVEL_LIMIT_4 = 19" in rules, "4-player/19 rule constant missing")
    require("FALLBACK_LINEUP_SIZE = 4" in rules, "4-player fallback size missing")
    require("def assess_completion_options(" in rules, "4-player fallback assessment missing")
    require("requires_forfeit" in rules, "fallback forfeit signal missing")

    dashboard = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")
    require("var MN_LIMIT_4 = 19;" in dashboard, "Match Night 4-player skill limit missing")
    require("var MN_SIZE_4 = 4;" in dashboard, "Match Night fallback lineup size missing")
    require("function mnAssessCompletionOptions(" in dashboard, "Match Night fallback assessment missing")
    require("assessCompletionOptions: mnAssessCompletionOptions" in dashboard, "Match Night fallback test hook missing")
    require("Match 5 must be forfeited" in dashboard, "captain-facing fallback forfeit messaging missing")

    browser_tests = ROOT / "tests" / "test_match_night_fallback_browser.py"
    require(browser_tests.is_file(), "Match Night fallback browser regression suite missing")
    test_source = browser_tests.read_text(encoding="utf-8")
    require(
        test_source.count("    def test_") >= 10,
        "Match Night fallback browser suite must contain at least 10 deterministic tests",
    )

    print("Source release gates: PASS")
    print("Operational gates still require direct evidence: main protection + live-data acceptance")
    return 0


if __name__ == "__main__":
    sys.exit(main())
