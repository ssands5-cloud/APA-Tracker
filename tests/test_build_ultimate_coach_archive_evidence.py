from scripts.build_ultimate_coach_archive_evidence import add_archive_evidence
from copy import deepcopy


def test_archive_adds_verified_games_by_member_id_without_replacing_current_fixtures():
    current = {
        "players": [{"id": 1, "external_id": "member-a", "team_history": [{"is_current": True}]}],
        "match_day": {"fixtures": [{"match_external_id": "refreshed"}]},
        "evidence": [],
        "counts": {"all_games": 0},
        "trust": {"identity_verified_game_count": 0, "total_all_games_rows": 0},
    }
    archive = {
        "players": [
            {"id": 10, "external_id": "member-a"},
            {"id": 1, "external_id": "member-b", "team_history": [{"is_current": True}]},
            {"id": 11, "external_id": "member-c"},
        ],
        "evidence": [
            {"player_id": player, "opponent_id": opponent, "match_external_id": match,
             "match_date": date, "game_key": match, "format": "EIGHT"}
            for player, opponent, match, date in (
                (10, 1, "old", "2025-11-09"),
                (1, 10, "old", "2025-11-09"),
                (10, 1, "refreshed", "2026-11-01"),
                (10, 1, "future", "2027-01-01"),
                (1, 11, "unrelated", "2025-11-09"),
            )
        ],
    }
    assert add_archive_evidence(current, archive, "2026-11-12") == 1
    assert current["players"] == [
        {"id": 1, "external_id": "member-a", "team_history": [{"is_current": True}]},
        {"id": 2, "external_id": "member-b", "team_history": []},
    ]
    assert [(r["player_id"], r["opponent_id"], r["game_key"]) for r in current["evidence"]] == [
        (1, 2, "archive:old"), (2, 1, "archive:old"),
    ]
    assert current["match_day"]["fixtures"] == [{"match_external_id": "refreshed"}]
    assert current["counts"] == {"players": 2, "head_to_head_rows": 2, "all_games": 1}


def test_captured_result_for_previously_unplayed_fixture_is_used_once():
    current = {
        "players": [{"id": 1, "external_id": "a"}, {"id": 2, "external_id": "b"}],
        "match_day": {"fixtures": [{"match_external_id": "42"}]},
        "evidence": [], "counts": {"all_games": 0},
        "trust": {"identity_verified_game_count": 0, "total_all_games_rows": 0},
    }
    archive = {
        "players": deepcopy(current["players"]),
        "evidence": [
            {"player_id": a, "opponent_id": b, "match_external_id": "42",
             "match_date": "2026-11-15", "game_key": "catchup:42:1", "format": "EIGHT"}
            for a, b in ((1, 2), (2, 1))
        ],
    }
    assert add_archive_evidence(current, archive, "2026-11-18") == 1
    assert len(current["evidence"]) == 2
    assert add_archive_evidence(current, archive, "2026-11-18") == 0
    assert len(current["evidence"]) == 2


def test_builder_can_use_full_history_refresh_without_reading_an_extra_archive(tmp_path, monkeypatch):
    import json
    import sys
    from types import SimpleNamespace
    from scripts import build_ultimate_coach_archive_evidence as builder

    root = tmp_path / 'runs'
    run = root / 'run-complete'
    run.mkdir(parents=True)
    database = run / 'ultimate_coach_staging.db'
    database.write_bytes(b'verified fixture database')
    (run / 'READY').write_text('{}')
    (root / 'CURRENT.json').write_text(json.dumps({
        'run': run.name, 'coverage': 'complete', 'checked_at': '2026-11-19T12:00:00+00:00',
        'artifacts': {database.name: builder.sha256(database)}}))
    current = {'players': [{'id': 1, 'external_id': 'a'}, {'id': 2, 'external_id': 'b'}],
               'match_day': {'fixtures': []},
               'evidence': [
                   {'player_id': player, 'opponent_id': opponent, 'game_key': 'existing-history'}
                   for player, opponent in ((1, 2), (2, 1))],
               'counts': {'all_games': 1},
               'trust': {'identity_verified_game_count': 1, 'total_all_games_rows': 1}}
    reads = []
    def read(path, timezone):
        reads.append(path)
        return current
    def workbook(payload, path, **kwargs):
        assert payload['evidence'][0]['game_key'] == 'existing-history'
        path.write_bytes(b'workbook')
    monkeypatch.setattr(builder, 'read_payload', read)
    monkeypatch.setattr(builder, 'load_match_day_settings', lambda path: SimpleNamespace(
        timezone='America/Denver', viewer_member_external_id=None, viewer_card_number=None))
    monkeypatch.setattr(builder, 'render', lambda payload, **kwargs: 'html')
    monkeypatch.setattr(builder, 'write_workbook', workbook)
    monkeypatch.setattr(builder.refresh_workbook, 'validate_html', lambda path: {})
    monkeypatch.setattr(builder.refresh_workbook, 'recalculate_and_validate', lambda path: {})
    out = tmp_path / 'out'
    monkeypatch.setattr(sys, 'argv', ['build', '--refresh-root', str(root), '--config', str(tmp_path/'config.yaml'), '--out', str(out)])
    builder.main()
    assert reads == [database]
    assert current['counts']['all_games'] == 1
    assert json.loads((out/'history-scope.json').read_text())['extra_archive_supplied'] is False
