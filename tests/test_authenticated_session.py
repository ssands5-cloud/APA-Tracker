"""Unit tests for scraper/authenticated_session.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scraper.authenticated_session import create_authenticated_session, scrape_with_auth


MINIMAL_CONFIG = {
    "site": {
        "base_url": "https://example.com",
        "login_path": "/login",
        "standings_path": "/standings",
        "match_path_template": "/matches/{match_id}",
    },
    "session": {
        "timeout_seconds": 5,
        "cache_path": "/tmp/test_cookies.pkl",
    },
}


class TestCreateAuthenticatedSession:
    def test_returns_requests_session(self, monkeypatch):
        import requests

        monkeypatch.setenv("APA_USERNAME", "alice@example.com")
        monkeypatch.setenv("APA_PASSWORD", "pw")

        fake_session = requests.Session()
        with patch("scraper.authenticated_session.LoginManager") as MockMgr:
            instance = MockMgr.return_value
            instance.get_session.return_value = fake_session

            session = create_authenticated_session(
                username="alice@example.com", password="pw", config=MINIMAL_CONFIG
            )

        assert session is fake_session
        instance.get_session.assert_called_once_with(force_relogin=False)

    def test_force_relogin_passed_through(self, monkeypatch):
        import requests

        monkeypatch.setenv("APA_USERNAME", "alice@example.com")
        monkeypatch.setenv("APA_PASSWORD", "pw")

        fake_session = requests.Session()
        with patch("scraper.authenticated_session.LoginManager") as MockMgr:
            instance = MockMgr.return_value
            instance.get_session.return_value = fake_session

            create_authenticated_session(
                config=MINIMAL_CONFIG,
                force_relogin=True,
            )

        instance.get_session.assert_called_once_with(force_relogin=True)


class TestScrapeWithAuth:
    def test_fetches_match_url(self, monkeypatch):
        monkeypatch.setenv("APA_USERNAME", "alice@example.com")
        monkeypatch.setenv("APA_PASSWORD", "pw")

        mock_session = MagicMock()
        mock_session.get.return_value.text = "<html>match</html>"
        mock_session.get.return_value.raise_for_status = MagicMock()

        with patch(
            "scraper.authenticated_session.create_authenticated_session",
            return_value=mock_session,
        ):
            html = scrape_with_auth("99999", config=MINIMAL_CONFIG)

        assert html == "<html>match</html>"
        call_args = mock_session.get.call_args
        assert "99999" in call_args[0][0]

    def test_raises_on_http_error(self, monkeypatch):
        import requests as req_lib

        monkeypatch.setenv("APA_USERNAME", "alice@example.com")
        monkeypatch.setenv("APA_PASSWORD", "pw")

        mock_session = MagicMock()
        mock_session.get.return_value.raise_for_status.side_effect = (
            req_lib.HTTPError("404")
        )

        with patch(
            "scraper.authenticated_session.create_authenticated_session",
            return_value=mock_session,
        ):
            with pytest.raises(req_lib.HTTPError):
                scrape_with_auth("bad_id", config=MINIMAL_CONFIG)
