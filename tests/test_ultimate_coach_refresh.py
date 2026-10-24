"""Real fixture replay, SQLite ingestion/reconciliation, engines and both exporters.

Only external acquisition and the platform-specific validators are replaced in
these portable cases. Private acceptance separately runs native Excel/Chromium.
"""
from __future__ import annotations
import copy
import json
import sqlite3
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine

from auth.graphql_client import execute, use_fixture_provider
from database.models import Base
from parser import apa_graphql as queries
from pipeline import ultimate_coach_refresh as refresh
from pipeline.refresh_sources import ResponseFixtures, encoded, sha256
from pipeline.refresh_workbook import validate_structure
from tests.test_division_wide_sync import ROSTERS_PAYLOAD, SCHEDULE_PAYLOAD, MATCH_DETAIL_PAYLOAD, SESSION_NAME


def fixtures(root, *, corrected=False, empty=False, career=False):
    store = ResponseFixtures(root)
    detail = copy.deepcopy(MATCH_DETAIL_PAYLOAD)
    if corrected:
        detail['results'][0]['scores'][0]['winLoss'] = 'L'
        detail['results'][1]['scores'][0]['winLoss'] = 'W'
    if empty:
        detail['results'] = []
    cases = [
        (queries.DIVISION_ROSTERS_QUERY, {'id':300}, {'division':ROSTERS_PAYLOAD}),
        (queries.DIVISION_SCHEDULE_QUERY, {'id':300}, {'division':SCHEDULE_PAYLOAD}),
        (queries.DIVISION_STANDINGS_QUERY, {'id':300}, {'division':{'id':300,'teams':[
            {'id':301,'name':'Fixture Sharks','standing':1,'sessionTotalPoints':71},
            {'id':302,'name':'Fixture Renegades','standing':2,'sessionTotalPoints':63}]}}),
        (queries.MATCH_DETAIL_QUERY, {'id':90401}, {'match':detail}),
    ]
    flat_matches = [m for week in SCHEDULE_PAYLOAD['schedule'] for m in week['matches']]
    for team in ROSTERS_PAYLOAD['teams']:
        cases += [
            (queries.TEAM_PAGE_QUERY, {'id':team['id']}, {'team':{
                'id':team['id'], 'name':team['name'], 'division':{'id':300,'name':'Fixture division','format':'EIGHT'},
                'session':{'id':26,'name':SESSION_NAME}, 'league':{'id':1,'slug':'fixture'}}}),
            (queries.TEAM_ROSTER_QUERY, {'id':team['id']}, {'team':{'roster':team['roster']}}),
            (queries.TEAM_SCHEDULE_QUERY, {'id':team['id']}, {'team':{'matches':flat_matches}}),
        ]
        for row in team['roster']:
            pid=row['member']['id']
            aliases=[{'id':700+pid,'formats':['EIGHT'],'league':{'id':1,'slug':'fixture'}}] if career else []
            cases.append((queries.FORMATS_BY_MEMBER_ID_QUERY, {'memberId':pid,'withMember':True,'withAlias':False,'aliasId':pid}, {'member':{'id':pid,'aliases':aliases}}))
            if career:
                cases.append((queries.GET_EIGHT_BALL_STATS_QUERY,{'id':700+pid},{'alias':{'id':700+pid,'players':[],
                    'EightBallStats':[{'matchesWon':20,'matchesPlayed':40,'lastPlayed':'2026-10-16'}],'NineBallStats':[]}}))
    for query, variables, data in cases:
        store(query, variables, lambda data=data: data)
    store.save_index()
    scope={'viewer_id':'9001','team_ids':['301','302'],
           'divisions':[{'division_id':'300','format':'EIGHT','session_name':SESSION_NAME}],
           'catalog':{'schema':'ultimate-coach-historical-catalog-v1','divisions':[
               {'division_id':'300','catalog_session_name':SESSION_NAME,'league_id':'1','league_slug':'fixture'}]}}
    (root/'scope.json').write_bytes(encoded(scope))
    return root


@pytest.fixture
def setup(tmp_path, monkeypatch):
    seed=tmp_path/'seed.db'
    Base.metadata.create_all(create_engine(f'sqlite:///{seed}'))
    config=tmp_path/'config.yaml'
    config.write_text(yaml.safe_dump({'database':{'path':str(seed)},'refresh':{'source_database':str(seed)}}),encoding='utf-8')
    sources=fixtures(tmp_path/'sources')
    root=tmp_path/'runs'
    calls=[]
    def workbook(path):
        calls.append('workbook')
        return {**validate_structure(path),'portable_structure_checked':True}
    def html(path):
        calls.append('html')
        assert 'Next Send — options against' in path.read_text(encoding='utf-8')
        return {'portable_html_checked':True}
    monkeypatch.setattr('auth.graphql_client._post_with_retries',lambda *a,**k:pytest.fail('offline replay attempted HTTP'))
    def run(**kw):
        return refresh.run_refresh(config_path=config,run_root=root,fixture_source=sources,
            boundary=lambda p:p,workbook_validator=workbook,html_validator=html,**kw)
    return run,root,sources,calls,seed


def test_full_refresh_reaches_database_matchups_trends_workbook_html_and_status(setup,capsys):
    run,root,sources,calls,seed=setup
    before=sha256(seed)
    result=run()
    directory=root/result['run']
    assert calls==['workbook','html']
    with sqlite3.connect(directory/'ultimate_coach_staging.db') as db:
        for table in ('teams','players','matches','player_matches','player_head_to_head','player_matchups','player_trends'):
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]>0,table
        assert db.execute("SELECT rank,points FROM standings_snapshots WHERE team_name='Fixture Sharks' ORDER BY id DESC LIMIT 1").fetchone()==(1,71)
    assert sha256(seed)==before
    assert result['coverage']=='complete' and not result['live_sources_checked']
    assert (directory/'READY').is_file()
    assert json.loads((root/'CURRENT.json').read_text())==result
    text=capsys.readouterr().out
    for message in ('SCRAPE COMPLETE','DATABASE UPDATED','MATCHUPS REBUILT','WORKBOOK REBUILT','HTML REBUILT','ALL REFRESH TASKS COMPLETE'):
        assert message in text
    assert 'APA REFRESH COMPLETE (OFFLINE VALIDATION)' in text
    assert 'Fixtures Loaded: 12' in text
    assert 'Teams Updated: 2' in text and 'Players Updated: 2' in text
    assert 'Matchups Rebuilt: Yes' in text and 'Workbook Built: Yes' in text and 'HTML Built: Yes' in text
    assert str(directory) in text and 'Total Time:' in text


def test_quick_unchanged_sources_reuse_both_outputs_and_derived_generation(setup,monkeypatch,capsys):
    run,root,sources,calls,seed=setup
    first=run();calls.clear()
    monkeypatch.setattr(refresh,'rebuild_database',lambda *a:pytest.fail('unchanged derived data rebuilt'))
    monkeypatch.setattr(refresh,'replay_ingest',lambda *a:pytest.fail('unchanged fixtures reingested'))
    second=run(mode='quick')
    assert calls==[]
    assert set(second['reused'])=={'Ultimate_Coach.xlsx','ultimate_coach.html'}
    assert second['artifacts']==first['artifacts']
    summary=(root/'REFRESH_STATUS.txt').read_text()
    assert 'Teams Updated: 0 (2 checked; database reused)' in summary
    assert 'Players Updated: 0 (2 checked; database reused)' in summary
    assert 'Matchups Rebuilt: No (up to date; reused)' in summary
    assert 'Workbook Built: No (up to date; reused)' in summary
    assert 'HTML Built: No (up to date; reused)' in summary


def test_quick_detects_corrected_player_result_when_team_totals_are_unchanged(setup):
    run,root,sources,calls,seed=setup
    first=run();calls.clear()
    # Authoritative individual result changes; division/team schedule totals stay identical.
    fixtures(sources,corrected=True)
    second=run(mode='quick')
    assert second['source_sha256']!=first['source_sha256']
    assert calls==['workbook','html'] and not second['reused']
    with sqlite3.connect(root/second['run']/'ultimate_coach_staging.db') as db:
        rows=db.execute('SELECT p.external_id,m.result FROM player_matches m JOIN players p ON p.id=m.player_id ORDER BY p.external_id').fetchall()
        assert rows==[('9001','L'),('9002','W')]


def test_quick_rebuilds_only_a_corrupt_output(setup):
    run,root,sources,calls,seed=setup
    first=run();calls.clear()
    (root/first['run']/'ultimate_coach.html').write_text('damaged',encoding='utf-8')
    second=run(mode='quick')
    assert calls==['html'] and second['reused']==['Ultimate_Coach.xlsx']


def test_html_dependency_change_does_not_rebuild_workbook(setup,monkeypatch):
    run,root,sources,calls,seed=setup
    first=run();calls.clear();real=refresh.sha256
    monkeypatch.setattr(refresh,'sha256',lambda p:'changed-runtime' if Path(p).name=='ultimate_coach_war_room.js' else real(p))
    second=run(mode='quick')
    assert calls==['html'] and second['reused']==['Ultimate_Coach.xlsx']


@pytest.mark.parametrize('stage',['ingest','derived','payload','workbook','html'])
def test_failure_never_replaces_current_complete_bundle(setup,monkeypatch,stage):
    run,root,sources,calls,seed=setup
    first=run();prior=(root/'CURRENT.json').read_bytes();original={p.name:sha256(p) for p in (root/first['run']).iterdir() if p.is_file()}
    def fail(*a,**k):raise RuntimeError('synthetic failure')
    if stage in ('ingest','derived','payload'):
        monkeypatch.setattr(refresh,{'ingest':'replay_ingest','derived':'rebuild_database','payload':'build_payload'}[stage],fail)
        with pytest.raises(RuntimeError):run()
    else:
        from pipeline import refresh_workbook
        monkeypatch.setattr(refresh_workbook,'recalculate_and_validate' if stage=='workbook' else 'validate_html',fail)
        # No injected validators here: run_refresh resolves its real default function.
        config=root.parent/'config.yaml'
        with pytest.raises(RuntimeError):
            refresh.run_refresh(config_path=config,run_root=root,fixture_source=sources,boundary=lambda p:p,
                                **({'html_validator':lambda p:{}} if stage=='workbook' else {'workbook_validator':lambda p:{}}))
    assert (root/'CURRENT.json').read_bytes()==prior
    assert original=={p.name:sha256(p) for p in (root/first['run']).iterdir() if p.is_file()}
    assert 'FAILED AT STEP' in (root/'REFRESH_STATUS.txt').read_text()
    assert 'APA REFRESH COMPLETE' not in (root/'REFRESH_STATUS.txt').read_text()
    assert not (root/'REFRESH.lock').exists()


def test_empty_authoritative_scoresheet_is_reported_and_does_not_replace_saved_pair(setup):
    run,root,sources,calls,seed=setup
    first=run();prior=(root/'CURRENT.json').read_bytes()
    fixtures(sources,empty=True)
    with pytest.raises(refresh.RefreshFailed,match='coverage incomplete'):
        run(mode='quick')
    assert (root/'CURRENT.json').read_bytes()==prior


@pytest.mark.parametrize('problem',['missing_workbook','database','report','pointer'])
def test_quick_detects_invalid_generation_or_missing_output(setup,problem):
    run,root,sources,calls,seed=setup
    first=run(); calls.clear(); folder=root/first['run']
    if problem=='missing_workbook':
        (folder/'Ultimate_Coach.xlsx').unlink()
        second=run(mode='quick')
        assert calls==['workbook'] and second['reused']==['ultimate_coach.html']
        return
    if problem=='database':
        (folder/'ultimate_coach_staging.db').write_bytes(b'broken')
    elif problem=='report':
        (folder/'refresh_report.json').write_bytes(b'{}')
    else:
        pointer=json.loads((root/'CURRENT.json').read_text());pointer['run']='../outside'
        (root/'CURRENT.json').write_bytes(encoded(pointer))
    prior=(root/'CURRENT.json').read_bytes()
    with pytest.raises(refresh.RefreshFailed):run(mode='quick')
    assert (root/'CURRENT.json').read_bytes()==prior and calls==[]


def test_concurrent_refresh_is_refused_without_removing_other_lock(setup):
    run,root,*_=setup
    root.mkdir(); lock=root/'REFRESH.lock';lock.write_text('other-owner')
    with pytest.raises(refresh.RefreshFailed,match='another refresh'):run()
    assert lock.read_text()=='other-owner' and not (root/'CURRENT.json').exists()


def test_rebuild_removes_h2h_advantage_after_last_underlying_game_deleted(setup):
    run,root,*_=setup
    result=run(); dbpath=root/result['run']/'ultimate_coach_staging.db'
    with sqlite3.connect(dbpath) as db:
        assert db.execute('SELECT COUNT(*) FROM player_h2h_advantage').fetchone()[0]>0
        db.execute('DELETE FROM player_head_to_head');db.commit()
    refresh.rebuild_database({},dbpath)
    with sqlite3.connect(dbpath) as db:
        assert db.execute('SELECT COUNT(*) FROM player_h2h_advantage').fetchone()[0]==0


def test_current_pointer_failure_preserves_old_bundle(setup,monkeypatch):
    run,root,*_=setup
    run(); prior=(root/'CURRENT.json').read_bytes(); real=refresh.atomic_json
    def fail_pointer(path,doc):
        if Path(path).name=='CURRENT.json':raise OSError('simulated pointer failure')
        return real(path,doc)
    monkeypatch.setattr(refresh,'atomic_json',fail_pointer)
    with pytest.raises(OSError):run()
    assert (root/'CURRENT.json').read_bytes()==prior
    assert 'FAILED AT STEP 8' in (root/'REFRESH_STATUS.txt').read_text()


@pytest.mark.parametrize('scored_count',[1,45])
def test_actual_acquisition_captures_every_scored_sheet_and_exact_current_context(tmp_path,monkeypatch,scored_count):
    from pipeline.refresh_sources import acquire_current_sources
    baseline=fixtures(tmp_path/'baseline')
    responses={}
    for file in (baseline/'responses').glob('*.json'):
        body=json.loads(file.read_text()); responses[ResponseFixtures.key(body['query'],body['variables'])]=body['response']['data']
    viewer={'id':9001,'leagueTeams':[{'id':301,'name':'Fixture Sharks',
        'division':{'id':300,'type':'EIGHT'},'session':{'name':SESSION_NAME},'league':{'id':1,'slug':'fixture'}}]}
    responses[ResponseFixtures.key(queries.DASHBOARD_TEAMS_QUERY,{})]={'viewer':viewer}
    schedule=copy.deepcopy(SCHEDULE_PAYLOAD)
    first=schedule['schedule'][0]['matches'][0]
    for index in range(1,scored_count):
        match=copy.deepcopy(first);match['id']=90410+index;schedule['schedule'][0]['matches'].append(match)
        detail=copy.deepcopy(MATCH_DETAIL_PAYLOAD);detail['id']=match['id']
        responses[ResponseFixtures.key(queries.MATCH_DETAIL_QUERY,{'id':match['id']})]={'match':detail}
    responses[ResponseFixtures.key(queries.DIVISION_SCHEDULE_QUERY,{'id':300})]={'division':schedule}
    fetched=[]
    def remote(query,variables,*args):
        key=ResponseFixtures.key(query,variables);fetched.append(key)
        assert key in responses, 'unexpected uncaptured operation'
        return responses[key]
    monkeypatch.setattr('auth.graphql_client._execute_http',remote)
    output=ResponseFixtures(tmp_path/'captured')
    scope=acquire_current_sources({'apa':{'access_token':'synthetic'}},None,output)
    assert scope['team_ids']==['301','302']
    assert scope['divisions'][0]['league_id']=='1'
    assert scope['catalog']['divisions'][0]['context_source']=='dashboardTeams'
    assert sum(e['operation']=='MatchPage' for e in output.entries.values())==scored_count
    assert len(fetched)==len(set(fetched))  # recording cache; no second HTTP pass
    for path in (tmp_path/'captured'/'responses').glob('*.json'):
        assert 'synthetic' not in path.read_text()


def test_new_current_league_must_be_proven_before_any_catalog_fetch(tmp_path,monkeypatch):
    from pipeline.refresh_sources import acquire_current_sources,FixtureError
    from scraper import graphql_scraper as api
    monkeypatch.setattr(api,'fetch_dashboard_teams',lambda c:{'id':9001,'leagueTeams':[
        {'id':301,'division':{'id':300,'type':'EIGHT'},'session':{'name':SESSION_NAME}}]})
    with pytest.raises(FixtureError,match='exact division'):
        acquire_current_sources({'apa':{}},None,ResponseFixtures(tmp_path/'capture'))


def test_current_career_stats_reach_database_and_payload(setup):
    run,root,sources,calls,seed=setup
    fixtures(sources,career=True)
    result=run()
    assert result['career_counts']['league_stat_format_rows_written']==2
    assert result['career_counts']['unresolved_scopes']==0
    with sqlite3.connect(root/result['run']/'ultimate_coach_staging.db') as db:
        assert db.execute('SELECT matches_won,matches_played FROM player_league_career_stats').fetchall()==[(20,40),(20,40)]


@pytest.mark.parametrize('damage',['missing','empty'])
def test_bad_standings_cannot_advance_current_bundle(setup,damage):
    run,root,sources,*_=setup
    run(); prior=(root/'CURRENT.json').read_bytes()
    key=ResponseFixtures.key(queries.DIVISION_STANDINGS_QUERY,{'id':300})
    if damage=='missing':
        (sources/'responses'/f'{key}.json').unlink()
    else:
        store=ResponseFixtures(sources)
        # Recreate the fixture with an explicit authenticated-but-empty table.
        store(queries.DIVISION_STANDINGS_QUERY,{'id':300},lambda:{'division':{'teams':[]}})
        index=json.loads((sources/'sources.json').read_text())
        index['entries'][key]=store.entries[key]
        from pipeline.refresh_sources import digest
        index['content_sha256']=digest(index['entries'])
        (sources/'sources.json').write_bytes(encoded(index))
    with pytest.raises(Exception):run(mode='quick')
    assert (root/'CURRENT.json').read_bytes()==prior
    assert ('FAILED AT STEP 2' if damage=='missing' else 'FAILED AT STEP 3') in (root/'REFRESH_STATUS.txt').read_text()


def test_live_mode_auth_retry_keeps_successful_fixture_capture_and_token_private(setup,monkeypatch):
    from scraper.graphql_scraper import AccessTokenExpired
    run,root,sources,*_=setup
    attempts=[];tokens=[]
    documents=[json.loads(p.read_text()) for p in (sources/'responses').glob('*.json')]
    def acquire(config,seed,store):
        attempts.append(1)
        for body in documents:
            store(body['query'],body['variables'],lambda body=body:body['response']['data'])
        if len(attempts)==1:raise AccessTokenExpired('synthetic expiry')
        return json.loads((sources/'scope.json').read_text())
    def token():tokens.append(1);return 'private-synthetic-token'
    monkeypatch.delenv('APA_ACCESS_TOKEN',raising=False)
    result=refresh.run_refresh(config_path=root.parent/'config.yaml',run_root=root,boundary=lambda p:p,
        acquire=acquire,token_loader=token,workbook_validator=lambda p:validate_structure(p),html_validator=lambda p:{})
    assert len(attempts)==len(tokens)==2 and result['live_sources_checked']
    assert all(b'private-synthetic-token' not in p.read_bytes() for p in (root/result['run']).rglob('*.json'))
    prior=(root/'CURRENT.json').read_bytes()
    with pytest.raises(refresh.RefreshFailed,match='offline verification cannot replace'):
        run(mode='quick')
    assert (root/'CURRENT.json').read_bytes()==prior


def test_post_commit_status_log_error_does_not_falsely_report_refresh_failure(setup,monkeypatch):
    run,root,*_=setup
    original=refresh.atomic_json; committed=[]; real_open=Path.open
    def observe_pointer(path,document):
        original(path,document)
        if Path(path).name=='CURRENT.json':committed.append(True)
    def failing_log(path,*args,**kwargs):
        if committed and Path(path).name=='REFRESH_STATUS.txt':raise OSError('simulated log unavailable')
        return real_open(path,*args,**kwargs)
    monkeypatch.setattr(refresh,'atomic_json',observe_pointer)
    monkeypatch.setattr(Path,'open',failing_log)
    result=run()
    assert json.loads((root/'CURRENT.json').read_text())==result
    assert not (root/result['run']/'FAILED.json').exists()


def test_all_current_divisions_share_one_latest_standings_snapshot(setup):
    """Rows from earlier divisions must not disappear from latest_standings()."""
    from collections import Counter
    run,root,sources,_,_=setup
    store=ResponseFixtures(sources)
    store.entries=json.loads((sources/'sources.json').read_text())['entries']
    cases=[
        (queries.DIVISION_ROSTERS_QUERY,{'id':400},{'division':{'id':400,'teams':[{'id':401,'name':'Fixture Others','roster':[]}]}}),
        (queries.DIVISION_SCHEDULE_QUERY,{'id':400},{'division':{'id':400,'schedule':[]}}),
        (queries.DIVISION_STANDINGS_QUERY,{'id':400},{'division':{'id':400,'teams':[{'id':401,'name':'Fixture Others','standing':1,'sessionTotalPoints':29}]}}),
        (queries.TEAM_PAGE_QUERY,{'id':401},{'team':{'id':401,'name':'Fixture Others','division':{'id':400,'name':'Second fixture division','format':'EIGHT'},'session':{'id':26,'name':SESSION_NAME},'league':{'id':1,'slug':'fixture'}}}),
        (queries.TEAM_ROSTER_QUERY,{'id':401},{'team':{'roster':[]}}),
        (queries.TEAM_SCHEDULE_QUERY,{'id':401},{'team':{'matches':[]}}),
    ]
    for query,variables,data in cases:store(query,variables,lambda data=data:data)
    store.save_index()
    scope=json.loads((sources/'scope.json').read_text());scope['team_ids'].append('401')
    scope['divisions'].append({'division_id':'400','format':'EIGHT','session_name':SESSION_NAME})
    scope['catalog']['divisions'].append({'division_id':'400','catalog_session_name':SESSION_NAME,'league_id':'1','league_slug':'fixture'})
    (sources/'scope.json').write_bytes(encoded(scope))
    result=run()
    with sqlite3.connect(root/result['run']/'ultimate_coach_staging.db') as db:
        latest=db.execute('SELECT team_name,rank,points FROM standings_snapshots WHERE captured_at=(SELECT MAX(captured_at) FROM standings_snapshots)').fetchall()
    assert Counter(latest)==Counter([('Fixture Sharks',1,71),('Fixture Renegades',2,63),('Fixture Others',1,29)])


def test_incomplete_latest_standings_snapshot_cannot_replace_complete_bundle(setup,monkeypatch):
    from database import ingest
    run,root,*_=setup
    first=run();prior=(root/'CURRENT.json').read_bytes()
    hashes={p.name:sha256(p) for p in (root/first['run']).iterdir() if p.is_file()}
    original=ingest.ingest_standings
    def incomplete(db,rows,captured_at=None):
        original(db,rows[:-1],captured_at=captured_at)
        return len(rows)
    monkeypatch.setattr(ingest,'ingest_standings',incomplete)
    with pytest.raises(refresh.RefreshFailed,match='latest standings snapshot'):
        run()
    assert (root/'CURRENT.json').read_bytes()==prior
    assert hashes=={p.name:sha256(p) for p in (root/first['run']).iterdir() if p.is_file()}
    assert 'APA REFRESH COMPLETE' not in (root/'REFRESH_STATUS.txt').read_text()


def test_unresolved_identity_failure_explains_scope_and_report_without_success(setup,capsys):
    run,root,sources,*_=setup
    first=run();prior=(root/'CURRENT.json').read_bytes();capsys.readouterr()
    detail=copy.deepcopy(MATCH_DETAIL_PAYLOAD)
    detail['results'][0]['scores'][0]['player']['id']=19999
    detail['results'][0]['scores'][0]['player']['displayName']='Fixture Unresolved Participant'
    store=ResponseFixtures(sources);store.entries=json.loads((sources/'sources.json').read_text())['entries']
    key=store.key(queries.MATCH_DETAIL_QUERY,{'id':90401});store.entries.pop(key)
    store(queries.MATCH_DETAIL_QUERY,{'id':90401},lambda:{'match':detail});store.save_index()
    with pytest.raises(refresh.RefreshFailed,match='no new workbook or HTML built'):
        run()
    text=capsys.readouterr().out
    assert 'SOURCE REVIEW REQUIRED' in text and 'unresolved row identities' in text
    assert 'refresh_report.json' in text and 'no identity was guessed' in text
    assert 'APA REFRESH COMPLETE' not in text
    assert (root/'CURRENT.json').read_bytes()==prior
