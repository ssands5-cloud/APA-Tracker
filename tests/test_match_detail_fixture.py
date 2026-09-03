"""Player match-history/statistics query against the sanitized fixture.

tests/fixtures/match_detail_response.json is fabricated data shaped to match
the real MatchPage capture (docs/graphql-captures/2026-09-03-shapes.json),
trimmed the same way parser.apa_graphql.MATCH_DETAIL_QUERY is: no fees, no
orderItems/order/member (billing and real names have no reason to be stored
here). No live call is made anywhere in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

from database.ingest import ingest_match_scores
from database.models import Base, PlayerMatch
from scraper.graphql_scraper import match_player_scores

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "match_detail_response.json").read_text()
)
MATCH = FIXTURE["data"]["match"]


class TestMatchPlayerScores:
    def test_one_row_per_player_across_both_teams(self):
        rows = match_player_scores(MATCH)
        assert len(rows) == 5  # 3 home + 2 away, per the fixture
        assert {r["player_name"] for r in rows} == {
            "Player One", "Player Two", "Player Three", "Player Four", "Player Five",
        }

    def test_team_identity_is_attached_per_side(self):
        rows = {r["player_name"]: r for r in match_player_scores(MATCH)}
        assert rows["Player One"]["team_name"] == "Chalk It Up"
        assert rows["Player One"]["team_id"] == "90001"
        assert rows["Player Four"]["team_name"] == "Rack Attack"
        assert rows["Player Four"]["team_id"] == "90002"

    def test_win_loss_and_points_are_read_correctly(self):
        rows = {r["player_name"]: r for r in match_player_scores(MATCH)}
        assert rows["Player One"]["result"] == "W"
        assert rows["Player One"]["points_earned"] == 6
        assert rows["Player Two"]["result"] == "L"
        assert rows["Player Two"]["points_earned"] == 3

    def test_forfeit_is_flagged_not_dropped(self):
        """A forfeited row is still a participation record. Dropping it would
        undercount matches played, not just matches won."""
        rows = {r["player_name"]: r for r in match_player_scores(MATCH)}
        forfeited = rows["Player Three"]
        assert forfeited["forfeited"] is True
        assert forfeited["result"] == "L"
        assert forfeited["points_earned"] == 0

    def test_incomplete_is_flagged_not_dropped(self):
        rows = {r["player_name"]: r for r in match_player_scores(MATCH)}
        assert rows["Player Five"]["incomplete"] is True
        # An incomplete match can still carry a result and points -- the two
        # flags are independent facts, not substitutes for each other.
        assert rows["Player Five"]["result"] == "W"

    def test_match_id_is_attached_to_every_row(self):
        rows = match_player_scores(MATCH)
        assert all(r["match_id"] == "555001" for r in rows)

    def test_empty_match_yields_no_rows(self):
        assert match_player_scores({}) == []
        assert match_player_scores({"results": []}) == []

    def test_a_result_with_no_scores_yields_no_rows_for_that_side(self):
        assert match_player_scores({"results": [{"homeAway": "HOME", "scores": []}]}) == []


class TestIngestionEndToEnd:
    def test_all_five_scores_land_in_the_database(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            rows = match_player_scores(MATCH)
            created, updated = ingest_match_scores(db, 555001, rows)
            assert (created, updated) == (5, 0)

            records = db.query(PlayerMatch).filter_by(match_id=555001).all()
            assert len(records) == 5
            by_ext_id = {r.player.external_id: r for r in records}
            assert by_ext_id["501"].result == "W"
            assert by_ext_id["501"].points_earned == 6
            assert by_ext_id["501"].team_name == "Chalk It Up"

    def test_rerunning_updates_rather_than_duplicates(self, tmp_path):
        """Re-fetching after a match goes from unfinalized to finalized must
        update the existing rows, not skip them or add duplicates."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            rows = match_player_scores(MATCH)
            ingest_match_scores(db, 555001, rows)

            # Simulate the result changing on a re-fetch (e.g. a correction).
            revised = [dict(r) for r in rows]
            revised[0]["result"] = "L"
            revised[0]["points_earned"] = 0

            created, updated = ingest_match_scores(db, 555001, revised)
            assert (created, updated) == (0, 5)
            assert db.query(PlayerMatch).filter_by(match_id=555001).count() == 5

            changed = (
                db.query(PlayerMatch)
                .join(PlayerMatch.player)
                .filter_by(external_id="501")
                .one()
            )
            assert changed.result == "L"
