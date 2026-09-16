"""Tests for ui/dashboard.py, the static Coach Dashboard that replaces
ui/dashboard_stub.py."""

from __future__ import annotations

import json

from analytics.lineup_lab import LineupLabResult, LineupSlot
from analytics.opponent_risk_profile import OpponentRiskEntry
from analytics.pairing_evidence import EvidenceLabel, PairingEvidence, PairingEvidenceMatrix
from analytics.player_matchup_engine import build_player_matchup_report
from analytics.team_matchup_engine import build_team_matchup_report
from ui.dashboard import render


def _pairing(**overrides) -> PairingEvidence:
    base = dict(
        player_id=1, player_external_id="P1", player_name="Ann", player_skill_level=5,
        opponent_id=2, opponent_external_id="P2", opponent_name="Bob", opponent_skill_level=4,
        format="8-Ball Open", session_name="Fall 2026",
        evidence_label=EvidenceLabel.DIRECT, observed_win_rate=0.75, direct_evidence_count=4,
        modeled_win_probability=0.7, model_source="analytics.head_to_head",
    )
    base.update(overrides)
    return PairingEvidence(**base)


def _matrix() -> PairingEvidenceMatrix:
    pairing = _pairing()
    return PairingEvidenceMatrix(
        our_team_external_id="OUR1", opponent_team_external_id="OPP1",
        format="8-Ball Open", session_name="Fall 2026",
        expected_pairings=((1, 2),), pairings=(pairing,),
        counts={"DIRECT": 1, "INDIRECT": 0, "UNKNOWN": 0, "total_feasible_pairings": 1},
        our_roster_available=True, opponent_roster_available=True,
    )


def _player_report(pairing=None, our_team="OUR1", opponent_team="OPP1", **kwargs):
    return build_player_matchup_report(pairing or _pairing(), our_team, opponent_team, **kwargs)


class TestRender:
    def test_a_self_contained_page_with_no_external_resources(self):
        html = render(
            [_player_report()],
            [build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")],
            [],
            "Mark It Up",
        )
        assert "<html" in html
        assert "http://" not in html
        assert "https://" not in html

    def test_choosing_a_player_narrows_the_opponent_selector(self):
        report_a = _player_report()
        report_b = _player_report(_pairing(player_id=3, player_name="Carol", opponent_id=4, opponent_name="Dave"))
        html = render([report_a, report_b], [], [], "Mark It Up")

        start = html.index('id="cd-player-opponent-index">') + len('id="cd-player-opponent-index">')
        end = html.index("</script>", start)
        index = json.loads(html[start:end])
        assert [c["label"] for c in index["1"]] == ["Bob — OPP1 (8-Ball Open, Fall 2026)"]
        assert [c["label"] for c in index["3"]] == ["Dave — OPP1 (8-Ball Open, Fall 2026)"]

    def test_opponent_risk_profile_rows_are_purely_descriptive(self):
        entry = OpponentRiskEntry(
            opponent_team_external_id="OPP1", opponent_team_name="Corner Pockets",
            total_pairings=1, direct_pairing_count=1, direct_win_rate=0.75,
            sample_size=4, reliability_weighted_skill_probability=0.7,
        )
        html = render([], [], [entry], "Mark It Up")
        assert "Corner Pockets" in html
        assert "75.0%" in html
        # The page explains, in prose, that it never emits a categorical
        # verdict -- it must not actually emit one for this real entry.
        assert "Corner Pockets</td><td>Danger" not in html
        assert "Corner Pockets</td><td>Favored" not in html

    def test_an_empty_risk_profile_says_no_data_not_a_blank_table(self):
        html = render([], [], [], "Mark It Up")
        assert "No data" in html

    def test_a_name_containing_a_script_close_tag_cannot_break_out(self):
        html = render(
            [_player_report(_pairing(player_name="</script><script>alert(1)</script>"))],
            [], [], "Mark It Up",
        )
        assert "<script>alert(1)</script>" not in html

    def test_both_engines_embedded_json_is_present_and_valid(self):
        player_report = _player_report()
        team_report = build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")
        html = render([player_report], [team_report], [], "Mark It Up")

        for element_id in ("cd-player-data", "cd-player-opponent-index", "cd-team-data"):
            start = html.index(f'id="{element_id}">') + len(f'id="{element_id}">')
            end = html.index("</script>", start)
            json.loads(html[start:end])  # must not raise

    def test_the_opponent_ranking_never_narrates_a_toughest_or_favorable_verdict(self):
        html = " ".join(render(
            [], [build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")], [], "Mark It Up",
        ).split())
        assert "experimental" in html.lower()
        # The prose note explaining WHY it's descriptive-only may say
        # "not a tactical verdict"; the generated summary itself must not
        # narrate a specific opponent as toughest/favorable.
        assert "toughest real matchup" not in html.lower()
        assert "most favorable real matchup" not in html.lower()

    def test_opponent_filter_controls_are_present(self):
        """Directive: skill level / streak(trend) / volatility filters on
        the Player vs Player selector."""
        html = render([_player_report()], [], [], "Mark It Up")
        assert 'id="pme-filter-sl-min"' in html
        assert 'id="pme-filter-sl-max"' in html
        assert 'id="pme-filter-vol-min"' in html
        assert 'class="pme-filter-trend"' in html

    def test_captains_edge_card_is_purely_descriptive(self):
        html = " ".join(render(
            [], [build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")], [], "Mark It Up",
        ).split())
        assert "Captain's Edge" in html
        assert "Evidence coverage" in html
        # The card may explain, in prose, that it never emits a verdict --
        # it must not actually narrate a specific opponent as one.
        assert "is favored" not in html.lower()
        assert "danger player" not in html.lower()

    def test_reading_dates_are_embedded_for_the_browser_sparkline_caption(self):
        """GPT audit follow-up (2026-09-16): a sparkline needs the real
        reading count/date context alongside the chart, not just the
        plotted shape, since it's independently scaled per player. The
        caption itself is built client-side (see
        tests/test_dashboard_browser.py for the real rendered check) --
        this test only proves the real dates reach the embedded JSON the
        browser reads from."""
        from analytics.player_matchup_engine import SkillTrendInfo

        report = _player_report(
            player_trend=SkillTrendInfo(
                trend="up", volatility=2, last_change=None,
                readings=(4, 5, 6),
                reading_dates=("2026-06-01", "2026-07-01", "2026-08-01"),
            ),
        )
        html = render([report], [], [], "Mark It Up")
        assert "2026-06-01" in html
        assert "2026-08-01" in html
        assert "reading_dates" in html

    def test_lineup_table_carries_score_and_score_basis_context(self):
        """GPT audit P2 / directive: lineup context (score, score basis,
        direct evidence) must be visible on the Coach Dashboard's own
        lineup table, not only in the standalone Team Matchup Engine
        export."""
        html = render([], [build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")], [], "Mark It Up")
        assert "Score" in html
        assert "Score basis" in html
        assert "Direct evidence" in html

    def test_lineup_score_basis_is_the_real_score_source_not_the_pairings_model_source(self):
        """GPT audit follow-up (2026-09-16): analytics.lineup_lab.pairing_score
        deliberately excludes DIRECT history from lineup selection --
        lineup_score is ALWAYS the validated skill-only score
        (lineup_score_source), even for a DIRECT slot whose own
        model_source says "direct-history-and-skill". An earlier version
        rendered model_source next to the score under "Model basis",
        wrongly implying DIRECT history influenced it. This fixture uses a
        DIRECT slot where the two sources genuinely differ, and asserts
        the rendered basis column shows the real score source."""
        lineup_result = LineupLabResult(
            assignments=(
                LineupSlot(
                    player_id=1, player_name="Ann", player_skill_level=5,
                    opponent_id=2, opponent_name="Bob", opponent_skill_level=4,
                    evidence_label=EvidenceLabel.DIRECT, observed_win_rate=0.75,
                    direct_evidence_count=4,
                    modeled_win_probability=0.62,
                    model_source="analytics.head_to_head:direct-history-and-skill",
                    lineup_score=0.62,
                    lineup_score_source="analytics.head_to_head:validated-skill-only",
                ),
            ),
            unassigned_players=(), unassigned_opponents=(),
            total_score=0.62, skill_total=5, is_legal=True, blocked_reason=None,
        )
        report = build_team_matchup_report(
            _matrix(), "Mark It Up", "Corner Pockets", lineup_result=lineup_result,
        )
        html = " ".join(render([], [report], [], "Mark It Up").split())

        assert "analytics.head_to_head:validated-skill-only" in html
        # The DIRECT slot's own model_source must still be visible (as real
        # evidence context), just not conflated with the score's basis.
        assert "analytics.head_to_head:direct-history-and-skill" in html


class TestMatchNight:
    """Directive: a "Match Night" workflow -- "who should I send" plus a
    live lineup planner. These tests check the static HTML surface (element
    ids the browser-driven tests in tests/test_dashboard_browser.py hook
    into, and that the page never references data.our_roster.trend/etc as
    verdict language); the real interactive behavior needs a live DOM, so
    it's covered there, not here."""

    def test_the_match_night_controls_are_present(self):
        html = render(
            [_player_report()],
            [build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")],
            [], "Mark It Up",
        )
        for element_id in ("mn-scope", "mn-match", "mn-opponent", "mn-roster", "mn-scouting",
                            "mn-comparison", "mn-lineup", "mn-warning", "mn-reset", "mn-print",
                            "mn-sticky"):
            assert f'id="{element_id}"' in html

    def test_bundle_generated_time_is_shown_when_built_at_is_given(self):
        """GPT audit follow-up (2026-09-16, a226bd1): this must say when the
        bundle was *built*, not claim to be when the underlying data was
        *captured* -- those are different real facts, and rebuilding an
        unchanged database would otherwise make stale data look freshly
        captured."""
        html = render(
            [_player_report()],
            [build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")],
            [], "Mark It Up", built_at="2026-09-16T19:14:44.743930+00:00",
        )
        assert "Bundle generated:" in html
        assert "2026-09-16 19:14 UTC" in html
        assert "Data last captured" not in html
        assert "not necessarily when the underlying data" in html

    def test_bundle_generated_time_is_honest_when_built_at_is_not_given(self):
        html = render(
            [_player_report()],
            [build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")],
            [], "Mark It Up",
        )
        assert "Bundle generated: not available" in html

    def test_match_night_never_narrates_a_verdict(self):
        html = " ".join(render(
            [_player_report()],
            [build_team_matchup_report(_matrix(), "Mark It Up", "Corner Pockets")],
            [], "Mark It Up",
        ).split())
        assert "is favored" not in html.lower()
        assert "danger player" not in html.lower()
        assert "guaranteed" not in html.lower()

    def test_the_page_states_an_estimate_is_not_a_promise(self):
        """Directive: 'a matchup estimate is not a promise' must be made
        obvious on the page itself, not just true in the underlying data."""
        html = render([_player_report()], [], [], "Mark It Up")
        assert "not a promise" in html.lower() or "not a winning streak" in html.lower()

    # The scouting card's own disclosure text ("never treated as a loss",
    # "Coach notes ... not calculated") is built by client-side JS only
    # once an opponent is selected -- checking it against this module's
    # raw page *source* would be fragile (it'd depend on incidental JS
    # string-literal line-wrapping, not real rendered behavior) and
    # contradicts this class's own stated split with the browser suite.
    # See tests/test_dashboard_browser.py's TestOpponentScoutingCard for
    # the real, rendered-DOM check.
