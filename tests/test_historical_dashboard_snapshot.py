"""Public display projection and offline historical-export boundaries; synthetic fixtures only."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_historical_dashboard_snapshot import build_snapshot, historical_payload, write_snapshot
from tests.test_excel_war_room_formulas import _payload
from ui.match_night import select_fixture, slim_payload
from ui.ultimate_coach import render
from analytics.match_night_engine import plan_for_war_room
from analytics.ultimate_coach_excel_payload import build_team_rosters, build_player_vs_player_pairs
from analytics.ultimate_coach_matchup_evidence import members_by_scope, build_pair_index
from analytics.ultimate_coach_war_room import war_room_pair, meetings_index, sl_bucket_index

BUILT = '2026-10-07 18:00 UTC'


def fixture():
    payload = _payload()
    pick = select_fixture(payload, '1001', BUILT)
    slim = slim_payload(payload, pick, BUILT)
    return slim, pick


def test_display_projection_uses_existing_m3_and_evidence_without_identity_fields():
    payload, pick = fixture()
    payload['secret'] = 'DO-NOT-PUBLISH-SENTINEL'
    result = build_snapshot(payload, pick, built_at=BUILT, latest_result='Historical fixture', cap=23)
    members = members_by_scope(build_team_rosters(payload),payload['players'])
    ids = {p['id'] for p in payload['players']}
    wr = war_room_pair(members[pick['our_scope']],members[pick['opp_scope']],
        build_pair_index(build_player_vs_player_pairs(payload)),pick['fixture']['format'],
        sl_index=sl_bucket_index(payload['evidence'],ids),
        meetings=meetings_index(payload['evidence'],ids,payload['match_day']['display_timezone']),
        players_by_id={p['id']:p for p in payload['players']},session_name=pick['fixture'].get('session_name') or '')
    plan = plan_for_war_room(wr,cap=23)
    assert result['plan']['lead']['player'] == plan['lead']['our']
    assert result['plan']['bestBoard'] == plan['best_board']
    assert result['plan']['safestBoard'] == plan['safest_board']
    assert result['plan']['holds'] == plan['holds']
    assert result['totals']['meetings'] == sum(r['direct'][1] for b in wr['blocks'] for r in b['rows'] if r['direct'])
    raw=json.dumps(result)
    assert 'DO-NOT-PUBLISH-SENTINEL' not in raw
    for key in ('external_id','player_id','card_number','evidence_index','strings'):
        assert f'"{key}":' not in raw
    assert all(p['id'].startswith('our-') for p in result['players'])
    assert result['label']=='REALISTIC DEMO USING HISTORICAL DATA'


def test_historical_compact_round_trip_and_hash_tamper_refusal(tmp_path):
    payload=_payload()
    out=tmp_path/'historical.html'
    out.write_text(render(payload,built_at=BUILT,viewer_member_external_id='1001',consume_evidence=False),encoding='utf-8')
    digest=hashlib.sha256(out.read_bytes()).hexdigest()
    decoded,pick,built,latest=historical_payload(out,digest)
    result=build_snapshot(decoded,pick,built_at=built,latest_result=latest,cap=23)
    assert result['totals']['directPairs']>0
    out.write_text(out.read_text(encoding='utf-8')+'changed',encoding='utf-8')
    with pytest.raises(ValueError,match='hash'):
        historical_payload(out,digest)


@pytest.mark.parametrize('key',['external_id','card_number','cookie','password','access_token','source_db'])
def test_forbidden_field_does_not_replace_last_good_snapshot(tmp_path,key):
    out=tmp_path/'snapshot.json'
    out.write_text('last good snapshot',encoding='utf-8')
    with pytest.raises(ValueError,match='Forbidden'):
        write_snapshot({key:'DO-NOT-PUBLISH'},out)
    assert out.read_text()=='last good snapshot'


def test_output_outside_repository_refused_without_writes():
    with pytest.raises(RuntimeError,match='not inside'):
        write_snapshot({},Path('C:/outside-apa-snapshot.json'))


@pytest.mark.parametrize('cap',[0,-1,None,23.5])
def test_invalid_simulation_cap_refused(cap):
    payload,pick=fixture()
    with pytest.raises(ValueError,match='positive integer'):
        build_snapshot(payload,pick,built_at=BUILT,latest_result='Historical',cap=cap)
