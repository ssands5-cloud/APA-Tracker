"""GraphQL error classification, especially auth failures.

The expired-token case here is not hypothetical: it is the exact response the
live API returned on 2026-09-03 -- HTTP 200, an `errors` array reading "Your
token is no longer valid", and no extension code at all. The client classified
that as a generic GraphQLError, so the caller's expired-token handling never
ran and the user got a raw traceback instead of "your token expired".
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from auth.graphql_client import (
    GraphQLAuthError,
    GraphQLError,
    GraphQLTransportError,
    execute,
)
from scraper.graphql_scraper import (
    AccessTokenExpired,
    AccessTokenMissing,
    _token,
    fetch_team_data,
)

CONFIG = {"team": {"team_id": "13082948"}, "session": {"timeout_seconds": 5}}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _post(payload, status_code=200):
    return lambda *args, **kwargs: FakeResponse(payload, status_code)


class TestExpiredTokenClassification:
    LIVE_RESPONSE = {"errors": [{"message": "Your token is no longer valid"}]}

    def test_the_real_expired_token_response_is_an_auth_error(self):
        """HTTP 200 + that message + no extension code. The live shape."""
        with patch("requests.post", _post(self.LIVE_RESPONSE)):
            with pytest.raises(GraphQLAuthError):
                execute("query {}", access_token="stale")

    def test_401_is_still_an_auth_error(self):
        with patch("requests.post", _post({"errors": [{"message": "nope"}]}, 401)):
            with pytest.raises(GraphQLAuthError):
                execute("query {}", access_token="stale")

    def test_extension_code_is_still_an_auth_error(self):
        payload = {"errors": [{"message": "x", "extensions": {"code": "UNAUTHENTICATED"}}]}
        with patch("requests.post", _post(payload)):
            with pytest.raises(GraphQLAuthError):
                execute("query {}", access_token="stale")

    def test_an_ordinary_error_is_not_misread_as_an_auth_failure(self):
        payload = {"errors": [{"message": "Team with id 99 was not found"}]}
        with patch("requests.post", _post(payload)):
            with pytest.raises(GraphQLError) as excinfo:
                execute("query {}", access_token="good")
        assert not isinstance(excinfo.value, GraphQLAuthError)

    def test_non_json_body_is_a_transport_error(self):
        with patch("requests.post", _post(None)):
            with pytest.raises(GraphQLTransportError):
                execute("query {}", access_token="good")


class TestFetchTeamDataSurfacesActionableErrors:
    def test_expired_token_becomes_an_explained_error(self, monkeypatch):
        monkeypatch.setenv("APA_ACCESS_TOKEN", "stale-token")
        payload = {"errors": [{"message": "Your token is no longer valid"}]}
        with patch("requests.post", _post(payload)):
            with pytest.raises(AccessTokenExpired) as excinfo:
                fetch_team_data(CONFIG)
        message = str(excinfo.value)
        assert "expires quickly" in message and "APA_ACCESS_TOKEN" in message

    def test_a_non_auth_graphql_error_is_not_relabelled_as_expiry(self, monkeypatch):
        """Misreporting a real API error as "your token expired" sends the
        user off to re-capture a token that was fine."""
        monkeypatch.setenv("APA_ACCESS_TOKEN", "good-token")
        payload = {"errors": [{"message": "Team with id 13082948 was not found"}]}
        with patch("requests.post", _post(payload)):
            with pytest.raises(GraphQLError) as excinfo:
                fetch_team_data(CONFIG)
        assert not isinstance(excinfo.value, AccessTokenExpired)


class TestPlaceholderToken:
    """The instructions show `<token from your logged-in session>`; pasted
    verbatim it otherwise costs a round trip and returns the API's opaque
    "no longer valid", which reads as expiry rather than a paste mistake."""

    @pytest.mark.parametrize("placeholder", [
        "<token from your logged-in session>",
        "<current APA access token>",
        "  <access token>  ",
    ])
    def test_placeholder_is_rejected_before_any_network_call(self, monkeypatch, placeholder):
        monkeypatch.setenv("APA_ACCESS_TOKEN", placeholder)
        with patch("requests.post", side_effect=AssertionError("must not call the API")):
            with pytest.raises(AccessTokenMissing) as excinfo:
                _token({})
        assert "placeholder" in str(excinfo.value)

    def test_a_real_looking_token_passes(self, monkeypatch):
        monkeypatch.setenv("APA_ACCESS_TOKEN", "eyJhbGciOiJIUzI1NiJ9.abc.def")
        assert _token({}) == "eyJhbGciOiJIUzI1NiJ9.abc.def"
