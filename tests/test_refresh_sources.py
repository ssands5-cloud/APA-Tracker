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
