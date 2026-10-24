from pathlib import Path
import json
import pytest
from auth import graphql_client as client
from pipeline.refresh_sources import ResponseFixtures, FixtureError


def test_capture_replays_exact_bytes_without_http_and_never_persists_token(tmp_path, monkeypatch):
    calls = []
    class Response:
        status_code = 200
        def json(self):
            return {"data": {"team": {"id": "10", "roster": [1, None]}}}
    monkeypatch.setattr(client, "_post_with_retries", lambda *a: calls.append(a) or Response())
    capture = ResponseFixtures(tmp_path)
    with client.use_fixture_provider(capture):
        expected = client.execute("query teamPage($id: Int!) { team(id:$id) { id } }", {"id": 10}, "PRIVATE-TOKEN")
    capture.save_index()
    assert len(calls) == 1
    assert all(b"PRIVATE-TOKEN" not in p.read_bytes() for p in tmp_path.rglob("*.json"))
    monkeypatch.setattr(client, "_post_with_retries", lambda *a: pytest.fail("replay attempted live HTTP"))
    with client.use_fixture_provider(ResponseFixtures(tmp_path, replay=True)):
        assert client.execute("query teamPage($id: Int!) { team(id:$id) { id } }", {"id": 10}) == expected
        with pytest.raises(FixtureError, match="missing"):
            client.execute("query Missing { viewer { id } }", {})


def test_failed_auth_is_not_captured_and_context_restores_transport(tmp_path, monkeypatch):
    def failed(*a):
        raise client.GraphQLAuthError([{"message": "invalid token"}], 401)
    monkeypatch.setattr(client, "_execute_http", failed)
    with pytest.raises(client.GraphQLAuthError), client.use_fixture_provider(ResponseFixtures(tmp_path)):
        client.execute("query dashboard { viewer { id } }", {}, "private")
    assert not list(tmp_path.rglob("*.json"))
    assert client._FIXTURE_PROVIDER.get() is None


@pytest.mark.parametrize("query", ["mutation login { login { token } }", "query RefreshAccessTokenQuery { token }"])
def test_credentials_or_mutations_never_become_fixtures(tmp_path, query):
    with pytest.raises(FixtureError):
        ResponseFixtures(tmp_path)(query, {}, lambda: pytest.fail("must reject before HTTP"))
    assert not list(tmp_path.iterdir())


def test_replay_refuses_corrupt_response(tmp_path):
    capture = ResponseFixtures(tmp_path)
    capture("query Team { team { id } }", {}, lambda: {"team": {"id": 1}})
    capture.save_index()
    next((tmp_path / "responses").iterdir()).write_text('{}', encoding='utf-8')
    with pytest.raises(FixtureError, match="checksum"):
        ResponseFixtures(tmp_path, replay=True)("query Team { team { id } }", {}, lambda: {})


def test_career_player_links_require_exact_member_alias_session_and_format(tmp_path):
    from parser.apa_graphql import FORMATS_BY_MEMBER_ID_QUERY, GET_EIGHT_BALL_STATS_QUERY
    capture = ResponseFixtures(tmp_path)
    for member in (101, 102):
        capture(FORMATS_BY_MEMBER_ID_QUERY,
                {'memberId': member, 'withMember': True, 'withAlias': False, 'aliasId': member},
                lambda member=member: {'member': {'id': member, 'aliases': [
                    {'id': member + 1000, 'league': {'id': 7}}]}})
        capture(GET_EIGHT_BALL_STATS_QUERY, {'id': member + 1000},
                lambda member=member: {'alias': {'id': member + 1000, 'players': [
                    {'id': 500, 'session': {'id': 26}, '__typename': 'EightBallPlayer'},
                    {'id': 501, 'session': {'id': 25}, '__typename': 'NineBallPlayer'}]}})
    capture.save_index()
    links = ResponseFixtures(tmp_path, replay=True).exact_player_members()
    # A collision remains explicit; callers cannot silently choose a member.
    assert links[('7', '26', 'EIGHT', '500')] == {'101', '102'}
    assert links[('7', '25', 'NINE', '501')] == {'101', '102'}
    assert ('7', '26', 'NINE', '500') not in links
    assert ('7', '25', 'EIGHT', '500') not in links


def test_career_player_links_reject_response_identity_mismatch(tmp_path):
    from parser.apa_graphql import FORMATS_BY_MEMBER_ID_QUERY
    capture = ResponseFixtures(tmp_path)
    capture(FORMATS_BY_MEMBER_ID_QUERY,
            {'memberId': 101, 'withMember': True, 'withAlias': False, 'aliasId': 101},
            lambda: {'member': {'id': 999, 'aliases': []}})
    capture.save_index()
    with pytest.raises(FixtureError, match='member identity'):
        ResponseFixtures(tmp_path, replay=True).exact_player_members()


@pytest.mark.parametrize('case,expected', [
    ('exact', '101'), ('wrong_team', None), ('wrong_division', None),
    ('wrong_session', None), ('wrong_format', None), ('wrong_league', None),
    ('collision', None), ('no_membership', None), ('missing_team', None),
    ('ambiguous_catalog', None), ('conflicting_current', 'error')])
def test_exact_career_identity_requires_all_scopes_and_keeps_departed_member_historical(case, expected):
    from types import SimpleNamespace
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from database.models import Base, Player, PlayerTeamHistory
    from pipeline.ultimate_coach_refresh import fixture_identity_resolver, RefreshFailed
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    division = {'division_id': '300', 'format': 'EIGHT', 'session_name': 'Fall'}
    context = {**division, 'format': '8-Ball Open', 'type': 'EIGHT',
               'league_id': '7', 'catalog_session_id': '26'}
    catalog = {'divisions': [context]}
    if case == 'ambiguous_catalog':
        catalog['divisions'].append({**context, 'catalog_session_id': '27'})
    key = ('7', '26', 'EIGHT', '500')
    if case == 'wrong_session': key = ('7', '25', 'EIGHT', '500')
    if case == 'wrong_format': key = ('7', '26', 'NINE', '500')
    if case == 'wrong_league': key = ('8', '26', 'EIGHT', '500')
    links = {key: {'101', '102'} if case == 'collision' else {'101'}}
    store = SimpleNamespace(exact_player_members=lambda: links)
    with Session(engine) as db:
        player = Player(external_id='101', name='Same Name')
        db.add(player); db.flush()
        if case != 'no_membership':
            db.add(PlayerTeamHistory(player_id=player.id, team_external_id='' if case == 'missing_team' else ('999' if case == 'wrong_team' else '301'),
                division_id='999' if case == 'wrong_division' else '300', session_name='Fall', is_current=False))
        if case == 'conflicting_current':
            other = Player(external_id='102', name='Same Name')
            db.add(other); db.flush()
            db.add(PlayerTeamHistory(player_id=other.id, team_external_id='301', division_id='300', session_name='Fall', is_current=True))
        db.commit()
        resolver = fixture_identity_resolver(store, catalog, division)
        rows = [{'player_id': '500', 'player_name': 'Same Name', 'team_id': '' if case == 'missing_team' else '301'}]
        if expected == 'error':
            with pytest.raises(RefreshFailed, match='conflicts'):
                resolver(db, 'Fall', rows)
        else:
            mapping, resolved, unresolved = resolver(db, 'Fall', rows)
            assert mapping == ({'500': expected} if expected else {})
            assert (resolved, unresolved) == ((1, 0) if expected else (0, 1))
        assert not db.query(PlayerTeamHistory).filter_by(player_id=player.id, is_current=True).count()
    engine.dispose()
