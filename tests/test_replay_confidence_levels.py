"""Historical review uses production evidence levels and strictly prior local dates."""
import hashlib
import json
import sqlite3

import pytest

from scripts.replay_confidence_levels import main


def source(tmp_path, formats=('EIGHT', 'EIGHT'), dates=('2026-01-01', '2026-01-02')):
    db = tmp_path / 'history.db'
    with sqlite3.connect(db) as c:
        c.executescript('CREATE TABLE matches(id INTEGER PRIMARY KEY,external_id TEXT,match_date TEXT);'
                        'CREATE TABLE player_head_to_head(player_id INTEGER,opponent_id INTEGER,result TEXT,'
                        'own_skill_level INTEGER,opponent_skill_level INTEGER,format TEXT,match_id INTEGER);')
        for i, (fmt, day) in enumerate(zip(formats, dates), 1):
            c.execute('INSERT INTO matches VALUES(?,?,?)', (i, f'm{i}', day))
            for p, o, result in ((1, 2, 'W'), (2, 1, 'L')):
                c.execute('INSERT INTO player_head_to_head VALUES(?,?,?,?,?,?,?)', (p, o, result, 4, 4, fmt, i))
    return db


@pytest.mark.parametrize('fmt', ['EIGHT', '8-Ball Open', 'NINE', '9-Ball Open'])
def test_replay_accepts_canonical_and_legacy_formats_and_preserves_source(tmp_path, fmt):
    db = source(tmp_path, formats=(fmt, fmt))
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    output = tmp_path / 'review.json'
    main(str(db), str(output))
    result = json.loads(output.read_text())
    prefix = 'EIGHT' if fmt in ('EIGHT', '8-Ball Open') else 'NINE'
    assert result['levels'][prefix + ' Unknown'] == {'n': 2, 'observed_wins': 1, 'observed_losses': 1}
    assert result['levels'][prefix + ' Thin']['n'] == 1
    assert result['levels'][prefix + ' Caution']['n'] == 1
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert result['production_rule'] == 'analytics.ultimate_coach_confidence.pair_confidence'


def test_same_denver_date_never_leaks_the_earlier_game_into_the_later_one(tmp_path):
    db = source(tmp_path, dates=('2026-01-02T00:00:00+00:00', '2026-01-01T23:00:00-07:00'))
    output = tmp_path / 'review.json'
    main(str(db), str(output))
    result = json.loads(output.read_text())
    assert result['levels'] == {'EIGHT Unknown': {'n': 4, 'observed_wins': 2, 'observed_losses': 2}}


def test_exact_exclusion_precedes_history_and_does_not_leak_into_later_days(tmp_path):
    db = source(tmp_path)
    output = tmp_path / 'review.json'
    main(str(db), str(output), exclude_match_external_ids={'m1'})
    result = json.loads(output.read_text())
    assert result['excluded_observations'] == 2
    assert result['levels'] == {'EIGHT Unknown': {'n': 2, 'observed_wins': 1, 'observed_losses': 1}}
    with pytest.raises(ValueError, match='not found'):
        main(str(db), str(output), exclude_match_external_ids={'missing'})


def test_replay_rejects_duplicate_results_instead_of_inflating_evidence(tmp_path):
    db = source(tmp_path)
    with sqlite3.connect(db) as c:
        c.execute('INSERT INTO player_head_to_head SELECT * FROM player_head_to_head LIMIT 1')
    with pytest.raises(ValueError, match='Duplicate'):
        main(str(db), str(tmp_path / 'review.json'))


@pytest.mark.parametrize('sl,expected', [(4, 'Strong'), (5, 'Solid'), (None, 'Strong')])
def test_replay_uses_production_skill_change_and_old_record_rules(tmp_path, sl, expected):
    db = source(tmp_path, formats=('EIGHT',) * 7, dates=('2020-01-01',) * 6 + ('2026-01-01',))
    with sqlite3.connect(db) as c:
        c.execute('UPDATE player_head_to_head SET own_skill_level=? WHERE match_id=7 AND player_id=1', (sl,))
        c.execute('UPDATE player_head_to_head SET opponent_skill_level=? WHERE match_id=7 AND opponent_id=1', (sl,))
    output = tmp_path / 'review.json'
    main(str(db), str(output))
    result = json.loads(output.read_text())
    assert result['levels']['EIGHT ' + expected]['observed_wins'] == 1
    # Current production does not downgrade for age alone or guess an uncaptured SL.
    assert result['observations'] == 14


def test_replay_refuses_empty_or_undated_evidence(tmp_path):
    db = source(tmp_path, formats=('UNSUPPORTED', 'UNSUPPORTED'))
    with pytest.raises(ValueError, match='No supported observations'):
        main(str(db), str(tmp_path / 'empty.json'))
    with sqlite3.connect(db) as c:
        c.execute("UPDATE player_head_to_head SET format='EIGHT'")
        c.execute("UPDATE matches SET match_date='not captured'")
    with pytest.raises(ValueError):
        main(str(db), str(tmp_path / 'undated.json'))
