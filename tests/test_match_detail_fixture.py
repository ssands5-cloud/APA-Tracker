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

import pytest

from database.ingest import ingest_head_to_head, ingest_match, ingest_match_scores
from database.models import Base, Match, PlayerHeadToHead, PlayerMatch
from scraper.graphql_scraper import head_to_head_rows, match_player_scores

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


class TestHeadToHeadRows:
    """Who a player actually played against, from pairing same-numbered
    matchPositionNumbers across home/away -- see head_to_head_rows'
    docstring and PlayerHeadToHead's in database/models.py for why that's
    reading a documented field, not resolving an ambiguous id."""

    def test_two_rows_per_paired_position_one_per_direction(self):
        rows = head_to_head_rows(MATCH)
        # Position 1 (One vs Four) and position 2 (Two vs Five), both
        # directions -- position 3 (Three) has no away-side partner and is
        # skipped, not guessed at (see the next test).
        assert len(rows) == 4

    def test_a_forfeited_position_with_no_opposing_player_is_skipped(self):
        """Player Three (position 3, matchForfeited) has no away-side
        position 3 in the fixture -- there's nobody to pair against."""
        rows = head_to_head_rows(MATCH)
        assert "Player Three" not in {r["player_name"] for r in rows}
        assert "Player Three" not in {r["opponent_name"] for r in rows}

    def test_each_direction_carries_its_own_perspective(self):
        rows = {(r["player_name"], r["opponent_name"]): r for r in head_to_head_rows(MATCH)}
        one_vs_four = rows[("Player One", "Player Four")]
        assert one_vs_four["result"] == "W"
        assert one_vs_four["points_earned"] == 6
        assert one_vs_four["own_skill_level"] == 5
        assert one_vs_four["opponent_skill_level"] == 5

        four_vs_one = rows[("Player Four", "Player One")]
        assert four_vs_one["result"] == "L"
        assert four_vs_one["points_earned"] == 3

    def test_match_id_is_attached_to_every_row(self):
        assert all(r["match_id"] == "555001" for r in head_to_head_rows(MATCH))

    def test_empty_match_yields_no_rows(self):
        assert head_to_head_rows({}) == []
        assert head_to_head_rows({"results": []}) == []


class TestIngestHeadToHead:
    def _seeded_db(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        engine = create_engine(f"sqlite:///{tmp_path / 'h2h.db'}")
        Base.metadata.create_all(engine)
        db = Session(engine)
        ingest_match(
            db, match_id="555001", home_team_id="90001", away_team_id="90002",
            home_team_name="Chalk It Up", away_team_name="Rack Attack",
        )
        return db

    def test_all_four_rows_land_in_the_database(self, tmp_path):
        db = self._seeded_db(tmp_path)
        count = ingest_head_to_head(db, head_to_head_rows(MATCH))
        assert count == 4
        assert db.query(PlayerHeadToHead).count() == 4

    def test_a_specific_pairing_carries_the_right_values(self, tmp_path):
        db = self._seeded_db(tmp_path)
        ingest_head_to_head(db, head_to_head_rows(MATCH))

        row = (
            db.query(PlayerHeadToHead)
            .join(PlayerHeadToHead.player)
            .filter_by(external_id="501")
            .one()
        )
        assert row.opponent.external_id == "601"
        assert row.result == "W"
        assert row.points_earned == 6
        assert row.own_skill_level == 5
        assert row.opponent_skill_level == 5

    def test_rerunning_updates_rather_than_duplicates(self, tmp_path):
        db = self._seeded_db(tmp_path)
        rows = head_to_head_rows(MATCH)
        ingest_head_to_head(db, rows)
        ingest_head_to_head(db, rows)
        assert db.query(PlayerHeadToHead).count() == 4

    def test_a_corrected_scoresheet_replaces_the_old_pairing_not_just_adds_to_it(self, tmp_path):
        """P1-7: a per-row upsert keyed on (player_id, match_id) can't fix
        this -- if position 2's away player changes (a lineup correction),
        the NEW pairing has the same key as the old one (same match,
        same home-side player_id) but a different opponent, so the old
        (player, opponent) row for that match must be gone, not left
        stale alongside the corrected one."""
        db = self._seeded_db(tmp_path)
        ingest_head_to_head(db, head_to_head_rows(MATCH))
        original = (
            db.query(PlayerHeadToHead)
            .join(PlayerHeadToHead.player).filter_by(external_id="502")  # Player Two
            .one()
        )
        assert original.opponent.external_id == "602"  # originally paired with Player Five

        # Corrected capture of the SAME match: position 2's away player is
        # now a different real person (a substitution correction), same
        # match_id, same home-side player_id -- everything else unchanged.
        corrected_match = json.loads(json.dumps(MATCH))  # deep copy
        for score in corrected_match["results"][1]["scores"]:  # AWAY side
            if score["matchPositionNumber"] == 2:
                score["player"] = {"id": 999, "displayName": "Substitute Player"}

        ingest_head_to_head(db, head_to_head_rows(corrected_match))

        rows = db.query(PlayerHeadToHead).join(PlayerHeadToHead.player).filter_by(external_id="502").all()
        assert len(rows) == 1, "the old pairing must be gone, not left alongside the corrected one"
        assert rows[0].opponent.external_id == "999"

        # The old opponent (Player Five, 602) must no longer show a
        # pairing for THIS match either -- only the new substitute does.
        stale_pairing = (
            db.query(PlayerHeadToHead)
            .join(PlayerHeadToHead.player).filter_by(external_id="602")
            .join(PlayerHeadToHead.match).filter_by(external_id="555001")
            .one_or_none()
        )
        assert stale_pairing is None

    def test_a_match_not_in_this_call_keeps_its_existing_rows(self, tmp_path):
        """Reconciliation is scoped to the match_ids actually present in
        `rows` -- ingesting one match's corrected data must not touch a
        different match's already-ingested rows."""
        db = self._seeded_db(tmp_path)
        ingest_match(
            db, match_id="555002", home_team_id="90001", away_team_id="90002",
            home_team_name="Chalk It Up", away_team_name="Rack Attack",
        )
        other_match = json.loads(json.dumps(MATCH))
        other_match["id"] = 555002
        ingest_head_to_head(db, head_to_head_rows(MATCH))
        ingest_head_to_head(db, head_to_head_rows(other_match))
        assert db.query(PlayerHeadToHead).count() == 8  # 4 per match, both intact

        # Re-ingesting ONLY the first match must leave the second's rows alone.
        ingest_head_to_head(db, head_to_head_rows(MATCH))
        assert db.query(PlayerHeadToHead).count() == 8

    def test_a_row_with_no_opponent_id_is_skipped_not_crashed(self, tmp_path):
        db = self._seeded_db(tmp_path)
        count = ingest_head_to_head(db, [
            {"match_id": "555001", "player_id": "501", "player_name": "Player One",
             "opponent_id": "", "opponent_name": "", "own_skill_level": 5,
             "opponent_skill_level": None, "result": "W", "points_earned": 6},
        ])
        assert count == 0
        assert db.query(PlayerHeadToHead).count() == 0


class TestIngestionEndToEnd:
    def _seeded_db(self, tmp_path):
        """A DB with the Match row already present, as any real caller has:
        ingest_match() always runs (from the schedule) before match detail is
        ever fetched for that match."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
        Base.metadata.create_all(engine)
        db = Session(engine)
        ingest_match(
            db, match_id="555001", home_team_id="90001", away_team_id="90002",
            home_team_name="Chalk It Up", away_team_name="Rack Attack",
        )
        return db

    def test_all_five_scores_land_in_the_database(self, tmp_path):
        db = self._seeded_db(tmp_path)
        rows = match_player_scores(MATCH)
        created, updated = ingest_match_scores(db, "555001", rows)
        assert (created, updated) == (5, 0)

        match_pk = db.query(Match).filter_by(external_id="555001").one().id
        records = db.query(PlayerMatch).filter_by(match_id=match_pk).all()
        assert len(records) == 5
        by_ext_id = {r.player.external_id: r for r in records}
        assert by_ext_id["501"].result == "W"
        assert by_ext_id["501"].points_earned == 6
        assert by_ext_id["501"].team_name == "Chalk It Up"

    def test_the_foreign_key_actually_resolves(self, tmp_path):
        """Regression test for a real bug: ingest_match_scores originally
        stored APA's match id directly as PlayerMatch.match_id, which
        foreign-keys to Match.id -- a SEPARATE autoincrement primary key.
        SQLite does not enforce foreign keys by default, so the mismatch
        (PlayerMatch.match_id == "555001" while the real row's id was 1)
        never raised; `.match` just silently returned None."""
        db = self._seeded_db(tmp_path)
        ingest_match_scores(db, "555001", match_player_scores(MATCH))

        pm = db.query(PlayerMatch).first()
        assert pm.match is not None, "PlayerMatch.match must resolve to a real Match row"
        assert pm.match.external_id == "555001"

    def test_opponent_is_the_other_side_not_the_players_own_team(self, tmp_path):
        """head_to_head() in analytics/team_stats.py filters on `opponent`;
        this ingestion path never set it, so it silently matched nothing."""
        db = self._seeded_db(tmp_path)
        ingest_match_scores(db, "555001", match_player_scores(MATCH))

        by_ext_id = {r.player.external_id: r for r in db.query(PlayerMatch).all()}
        assert by_ext_id["501"].opponent == "Rack Attack"    # home player
        assert by_ext_id["601"].opponent == "Chalk It Up"    # away player

    def test_match_date_is_filled_in_for_chronological_ordering(self, tmp_path):
        """database.queries.player_match_history() orders by match_date;
        left NULL, a GraphQL-sourced row would sort arbitrarily instead of
        chronologically, and analytics.player_stats.recent_form() (which
        slices the last N) would return an arbitrary N, not the recent ones."""
        db = self._seeded_db(tmp_path)
        ingest_match_scores(db, "555001", match_player_scores(MATCH))

        pm = db.query(PlayerMatch).first()
        match = db.query(Match).filter_by(external_id="555001").one()
        assert pm.match_date == match.match_date

    def test_rerunning_updates_rather_than_duplicates(self, tmp_path):
        """Re-fetching after a match goes from unfinalized to finalized must
        update the existing rows, not skip them or add duplicates."""
        db = self._seeded_db(tmp_path)
        rows = match_player_scores(MATCH)
        ingest_match_scores(db, "555001", rows)

        # Simulate the result changing on a re-fetch (e.g. a correction).
        revised = [dict(r) for r in rows]
        revised[0]["result"] = "L"
        revised[0]["points_earned"] = 0

        created, updated = ingest_match_scores(db, "555001", revised)
        assert (created, updated) == (0, 5)

        match_pk = db.query(Match).filter_by(external_id="555001").one().id
        assert db.query(PlayerMatch).filter_by(match_id=match_pk).count() == 5

        changed = (
            db.query(PlayerMatch)
            .join(PlayerMatch.player)
            .filter_by(external_id="501")
            .one()
        )
        assert changed.result == "L"

    def test_scores_for_an_unknown_match_raise_rather_than_orphaning(self, tmp_path):
        """The exact shape of the original bug: calling this before
        ingest_match() must fail loudly, not create a foreign key to nothing."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        engine = create_engine(f"sqlite:///{tmp_path / 'test2.db'}")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            with pytest.raises(ValueError, match="555001"):
                ingest_match_scores(db, "555001", match_player_scores(MATCH))
