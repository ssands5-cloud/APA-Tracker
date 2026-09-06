"""Tests for the self-contained Lineup Optimizer HTML tab."""

from __future__ import annotations

from ui.tabs.lineup_optimizer import COLUMNS, load_rows, render


def document():
    return {
        "schema_version": 1,
        "lineups": [
            {
                "team_id": "T1",
                "team_name": "Chalk It Up",
                "opponent_team_id": "T2",
                "opponent_team_name": "Corner Pockets",
                "format": "8-ball",
                "session_name": "Summer 2026",
                "roster_resolution": "team_id",
                "players_considered": 2,
                "opponents_considered": 2,
                "assignments": [
                    {
                        "player_name": "Bob",
                        "opponent_name": "Xavier",
                        "matchup_score_raw": 70,
                        "win_probability": 0.7,
                        "confidence": None,
                        "risk_factor": 0.2,
                        "final_score": 0.64,
                        "lineup_rank": 2,
                        "source_pairing": True,
                        "rationale": "Form unknown.",
                    },
                    {
                        "player_name": "Alice",
                        "opponent_name": "Yara",
                        "matchup_score_raw": None,
                        "win_probability": None,
                        "confidence": 0.8,
                        "risk_factor": None,
                        "final_score": 0.55,
                        "lineup_rank": 1,
                        "source_pairing": False,
                        "rationale": "No matchup history.",
                    },
                ],
            },
            {
                "team_id": "T9",
                "team_name": "Other Team",
                "opponent_team_id": "T8",
                "opponent_team_name": "Other Opponent",
                "format": "9-ball",
                "session_name": "Fall 2026",
                "assignments": [
                    {
                        "player_name": "Cara",
                        "opponent_name": "Zed",
                        "lineup_rank": 1,
                        "source_pairing": True,
                    }
                ],
            },
        ],
    }


class TestLoadRows:
    def test_rows_are_ranked_and_carry_group_context(self):
        rows = load_rows(document())
        assert [row["player_name"] for row in rows] == ["Alice", "Bob", "Cara"]
        assert rows[0]["team_name"] == "Chalk It Up"
        assert rows[0]["format"] == "8-ball"
        assert rows[0]["source_pairing"] is False

    def test_filters_are_independent(self):
        rows = load_rows(document(), team_id="T1", opponent_team_id="T2",
                         format_="8-ball", session_name="Summer 2026")
        assert [row["player_name"] for row in rows] == ["Alice", "Bob"]
        assert load_rows(document(), team_id="missing") == []


class TestRender:
    def test_headers_match_the_display_contract(self):
        assert [label for _, label, _ in COLUMNS] == [
            "Player", "Opponent", "Matchup Score", "Win Probability",
            "Confidence", "Risk", "Final Score", "Rank", "Rationale",
        ]

    def test_raw_values_and_missing_data_are_explicit(self):
        html = render(document())
        assert "70" in html
        assert "No data" in html
        assert 'class="unobserved"' in html
        assert "Neutral defaults are used only inside the optimizer" in html

    def test_names_are_escaped_and_page_has_no_external_dependency(self):
        payload = document()
        payload["lineups"][0]["team_name"] = "<unsafe>"
        html = render(payload)
        assert "&lt;unsafe&gt;" in html
        assert "http://" not in html
        assert "https://" not in html

    def test_empty_document_explains_why_no_card_is_shown(self):
        html = render({"lineups": [], "resolution_warnings": ["unresolved"]})
        assert "No resolved lineup yet" in html
        assert "warning(s)" in html
