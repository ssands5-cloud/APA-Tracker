"""Division standings against the sanitized fixture -- the real division-wide
query (real operation name: divsionStandings), not the single-team fallback.

tests/fixtures/division_standings_response.json is fabricated data shaped to
match the real capture in docs/graphql-captures/2026-09-03-shapes.json. No
live call is made anywhere in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

from database.ingest import ingest_standings
from database.models import Base, StandingsSnapshot
from scraper.graphql_scraper import division_standings_rows

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "division_standings_response.json").read_text()
)
DIVISION = FIXTURE["data"]["division"]


class TestDivisionStandingsRows:
    def test_one_row_per_team_including_the_bye(self):
        rows = division_standings_rows(DIVISION)
        assert len(rows) == 6
        assert {r["team_name"] for r in rows} == {
            "Chalk It Up", "Rack Attack", "Side Pocket Squad",
            "Corner Pocket", "Eight Ballers", "Bye Week",
        }

    def test_rank_and_points_come_straight_from_the_api(self):
        rows = {r["team_name"]: r for r in division_standings_rows(DIVISION)}
        assert rows["Chalk It Up"]["rank"] == 1
        assert rows["Chalk It Up"]["points"] == 142
        assert rows["Rack Attack"]["rank"] == 2
        assert rows["Rack Attack"]["points"] == 138

    def test_tied_teams_share_a_rank(self):
        rows = {r["team_name"]: r for r in division_standings_rows(DIVISION)}
        assert rows["Side Pocket Squad"]["rank"] == rows["Corner Pocket"]["rank"] == 3

    def test_standings_rows_carry_no_win_loss_keys(self):
        """Standings does not carry a win/loss record at all -- APA ranks by
        cumulative points and the query returns no such field, so the keys are
        absent rather than present-and-empty."""
        for row in division_standings_rows(DIVISION):
            assert "wins" not in row
            assert "losses" not in row

    def test_a_bye_team_still_gets_a_row(self):
        rows = {r["team_name"]: r for r in division_standings_rows(DIVISION)}
        bye = rows["Bye Week"]
        assert bye["rank"] is None
        assert bye["points"] == 0

    def test_empty_division_yields_no_rows(self):
        assert division_standings_rows({}) == []
        assert division_standings_rows({"teams": []}) == []


class TestIngestionEndToEnd:
    def test_all_six_teams_land_in_the_database(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            rows = division_standings_rows(DIVISION)
            count = ingest_standings(db, rows)
            assert count == 6

            snapshots = db.query(StandingsSnapshot).all()
            assert len(snapshots) == 6
            by_name = {s.team_name: s for s in snapshots}
            assert by_name["Chalk It Up"].rank == 1
            assert by_name["Chalk It Up"].points == 142
            assert not hasattr(by_name["Chalk It Up"], "wins")
            assert by_name["Bye Week"].points == 0
