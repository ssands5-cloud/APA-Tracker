import json

from pipeline.captured_scoresheet_evidence import add_captured_scoresheets


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
