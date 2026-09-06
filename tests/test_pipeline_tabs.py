"""Tests that the pipeline page includes the solved lineup artifact."""

from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import Base
from pipeline.exports import write_tabs


def test_write_tabs_renders_lineup_optimizer_before_other_analysis(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    (tmp_path / "lineups.json").write_text(
        json.dumps({
            "schema_version": 1,
            "lineups": [{
                "team_id": "T1",
                "team_name": "Chalk It Up",
                "opponent_team_id": "T2",
                "opponent_team_name": "Corner Pockets",
                "format": "8-ball",
                "session_name": "Summer 2026",
                "assignments": [{
                    "player_name": "Alice",
                    "opponent_name": "Bob",
                    "matchup_score_raw": 80,
                    "win_probability": 0.8,
                    "confidence": None,
                    "risk_factor": None,
                    "final_score": 0.7,
                    "lineup_rank": 1,
                    "source_pairing": True,
                    "rationale": "Form unknown.",
                }],
            }],
        }),
        encoding="utf-8",
    )

    with Session(engine) as db:
        output = write_tabs(db, tmp_path)

    html = output.read_text(encoding="utf-8")
    assert html.index("Lineup Optimizer") < html.index("Head-to-Head")
    assert "Alice" in html and "Bob" in html
    assert "80" in html
    engine.dispose()
