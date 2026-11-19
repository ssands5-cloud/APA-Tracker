import json

from pipeline.captured_scoresheet_evidence import add_captured_scoresheets
from pipeline.captured_scoresheet_evidence import update_captured_fixtures
import pytest


def test_exact_team_identity_and_repeated_pairing_positions(tmp_path):
    def write(folder, name, data):
        path = tmp_path / folder
        path.mkdir(exist_ok=True)
        (path / name).write_text(json.dumps(data))

    write("rosters", "1.json", {"teams": [
        {"id": 10, "roster": [{"id": 100, "displayName": "Home", "member": {"id": 1}}]},
        {"id": 20, "roster": [{"id": 200, "displayName": "Away", "member": {"id": 2}}]},
    ]})

    def score(player, position, result):
        return {"player": {"id": player}, "matchPositionNumber": position, "winLoss": result, "eightBallWins": 1}

    write("matches", "42.json", {"match": {
        "id": 42, "isFinalized": True, "startTime": "2026-11-10",
        "home": {"id": 10}, "away": {"id": 20},
        "results": [
            {"homeAway": "HOME", "scores": [score(100, 1, "W"), score(100, 2, "L"), score(200, 3, "W")]},
            {"homeAway": "AWAY", "scores": [score(200, 1, "L"), score(200, 2, "W"), score(200, 3, "L")]},
        ],
    }})
    archive = {"players": [], "evidence": []}
    report = add_captured_scoresheets({"evidence": []}, archive, tmp_path, "2026-11-12")
    assert report["counts"]["accepted_pairs"] == 2
    assert report["counts"]["unresolved_identity"] == 1
    assert len(archive["evidence"]) == 4
    assert {row["game_key"] for row in archive["evidence"]} == {"catchup:42:1", "catchup:42:2"}
    assert {row["format"] for row in archive["evidence"]} == {"EIGHT"}


def test_captured_schedule_replaces_unplayed_facts_and_rejects_wrong_team(tmp_path):
    folder = tmp_path / "divisions"
    folder.mkdir()
    match = {"id": 42, "home": {"id": 10}, "away": {"id": 20},
             "startTime": "2026-11-16T02:00:00Z", "status": "PLAYED",
             "isScored": True, "isFinalized": True,
             "results": [{"homeAway": "HOME", "points": {"total": 8}},
                         {"homeAway": "AWAY", "points": {"total": 4}}]}
    (folder / "1.json").write_text(json.dumps({"schedule": [{"weekOfPlay": 15, "matches": [match]}]}))
    fixture = {"match_external_id": "42", "home_team_id": "10", "away_team_id": "20",
               "status": "UNPLAYED", "home_score": None, "away_score": None}
    current = {"match_day": {"fixtures": [fixture]}}
    assert update_captured_fixtures(current, tmp_path, "America/Denver") == 1
    assert (fixture["status"], fixture["home_score"], fixture["away_score"]) == ("PLAYED", 8, 4)
    assert fixture["local_date"] == "2026-11-15"
    assert fixture["is_finalized"] is True
    fixture["away_team_id"] = "different-team"
    with pytest.raises(ValueError, match="team mismatch"):
        update_captured_fixtures(current, tmp_path, "America/Denver")
