"""Unit tests for auth/login_manager.py."""

from __future__ import annotations

import os
import pickle
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from auth.login_manager import AuthenticationError, LoginManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_CONFIG = {
    "site": {
        "base_url": "https://example.com",
        "login_path": "/login",
        "standings_path": "/standings",
    },
    "session": {
        "timeout_seconds": 5,
        "cache_path": "/tmp/test_cookies.pkl",
    },
}

SUCCESS_HTML = "<html><body>Welcome! Log Out</body></html>"
FAIL_HTML = "<html><body>Invalid credentials.</body></html>"
LOGIN_PAGE_HTML = '<html><body><form><input name="csrf_token" value="tok123"/></form></body></html>'


# ---------------------------------------------------------------------------
# Credential loading
# ---------------------------------------------------------------------------

class TestCredentialsFromEnv:
    def test_reads_env_vars(self, monkeypatch):
        monkeypatch.setenv("APA_USERNAME", "alice@example.com")
        monkeypatch.setenv("APA_PASSWORD", "secret")
        mgr = LoginManager(MINIMAL_CONFIG)
        assert mgr.username == "alice@example.com"
        # Password must not be exposed via a public attribute of that name
        assert mgr._password == "secret"

    def test_falls_back_to_none_when_env_absent(self, monkeypatch):
        monkeypatch.delenv("APA_USERNAME", raising=False)
        monkeypatch.delenv("APA_PASSWORD", raising=False)
        mgr = LoginManager(MINIMAL_CONFIG)
        assert mgr.username is None
        assert mgr._password is None

    def test_explicit_args_override_env(self, monkeypatch):
        monkeypatch.setenv("APA_USERNAME", "env@example.com")
        monkeypatch.setenv("APA_PASSWORD", "envpass")
        mgr = LoginManager(MINIMAL_CONFIG, username="bob@example.com", password="override")
        assert mgr.username == "bob@example.com"
        assert mgr._password == "override"


# ---------------------------------------------------------------------------
# login()
# ---------------------------------------------------------------------------

class TestLogin:
    def _make_mgr(self, monkeypatch):
        monkeypatch.setenv("APA_USERNAME", "alice@example.com")
        monkeypatch.setenv("APA_PASSWORD", "pw")
        return LoginManager(MINIMAL_CONFIG)

    def test_successful_login(self, monkeypatch):
        mgr = self._make_mgr(monkeypatch)
        with patch("auth.login_manager.requests.Session") as MockSession:
            mock_session = MagicMock()
            MockSession.return_value = mock_session
            mock_session.get.return_value.text = LOGIN_PAGE_HTML
            mock_session.get.return_value.raise_for_status = MagicMock()
            mock_session.post.return_value.text = SUCCESS_HTML
            mock_session.post.return_value.raise_for_status = MagicMock()

            result = mgr.login(save=False)

        assert result is True
        assert mgr._session is mock_session

    def test_failed_login_raises(self, monkeypatch):
        mgr = self._make_mgr(monkeypatch)
        with patch("auth.login_manager.requests.Session") as MockSession:
            mock_session = MagicMock()
            MockSession.return_value = mock_session
            mock_session.get.return_value.text = LOGIN_PAGE_HTML
            mock_session.get.return_value.raise_for_status = MagicMock()
            mock_session.post.return_value.text = FAIL_HTML
            mock_session.post.return_value.raise_for_status = MagicMock()

            with pytest.raises(AuthenticationError):
                mgr.login(save=False)

    def test_network_error_raises(self, monkeypatch):
        mgr = self._make_mgr(monkeypatch)
        with patch("auth.login_manager.requests.Session") as MockSession:
            mock_session = MagicMock()
            MockSession.return_value = mock_session
            mock_session.get.side_effect = requests.ConnectionError("unreachable")

            with pytest.raises(AuthenticationError):
                mgr.login(save=False)

    def test_csrf_token_sent_in_payload(self, monkeypatch):
        mgr = self._make_mgr(monkeypatch)
        with patch("auth.login_manager.requests.Session") as MockSession:
            mock_session = MagicMock()
            MockSession.return_value = mock_session
            mock_session.get.return_value.text = LOGIN_PAGE_HTML
            mock_session.get.return_value.raise_for_status = MagicMock()
            mock_session.post.return_value.text = SUCCESS_HTML
            mock_session.post.return_value.raise_for_status = MagicMock()

            mgr.login(save=False)

        call_kwargs = mock_session.post.call_args
        payload = call_kwargs[1].get("data") or call_kwargs[0][1]
        assert payload.get("csrf_token") == "tok123"


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------

class TestSessionPersistence:
    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APA_USERNAME", "alice@example.com")
        monkeypatch.setenv("APA_PASSWORD", "pw")
        # Point session path to tmp directory
        monkeypatch.setattr(
            "auth.credentials.Path.home", lambda: tmp_path
        )
        mgr = LoginManager(MINIMAL_CONFIG)

        # Inject a fake session
        fake_session = requests.Session()
        mgr._session = fake_session

        # Save
        path = mgr.save_session()
        assert path.exists()
        assert oct(path.stat().st_mode)[-3:] == "600"

        # Load into a new manager
        mgr2 = LoginManager(MINIMAL_CONFIG, username="alice@example.com")
        # Patch is_authenticated so we don't need a real server
        with patch.object(mgr2, "is_authenticated", return_value=True):
            loaded = mgr2.load_session(path)
        assert loaded is True

    def test_load_nonexistent_returns_false(self, monkeypatch):
        monkeypatch.delenv("APA_USERNAME", raising=False)
        monkeypatch.delenv("APA_PASSWORD", raising=False)
        mgr = LoginManager(MINIMAL_CONFIG, username="ghost@example.com")
        result = mgr.load_session(Path("/tmp/does_not_exist_xyz.pkl"))
        assert result is False


# ---------------------------------------------------------------------------
# is_authenticated / refresh_if_needed
# ---------------------------------------------------------------------------

class TestIsAuthenticated:
    def test_returns_false_when_no_session(self, monkeypatch):
        monkeypatch.delenv("APA_USERNAME", raising=False)
        monkeypatch.delenv("APA_PASSWORD", raising=False)
        mgr = LoginManager(MINIMAL_CONFIG)
        assert mgr.is_authenticated() is False

    def test_returns_true_on_success_marker(self, monkeypatch):
        monkeypatch.setenv("APA_USERNAME", "alice@example.com")
        monkeypatch.setenv("APA_PASSWORD", "pw")
        mgr = LoginManager(MINIMAL_CONFIG)
        mgr._session = MagicMock()
        mgr._session.get.return_value.text = SUCCESS_HTML
        mgr._session.get.return_value.raise_for_status = MagicMock()
        assert mgr.is_authenticated() is True


class TestRefreshIfNeeded:
    def test_no_refresh_when_alive(self, monkeypatch):
        monkeypatch.setenv("APA_USERNAME", "alice@example.com")
        monkeypatch.setenv("APA_PASSWORD", "pw")
        mgr = LoginManager(MINIMAL_CONFIG)
        with patch.object(mgr, "is_authenticated", return_value=True):
            result = mgr.refresh_if_needed()
        assert result is True

    def test_refreshes_when_expired(self, monkeypatch):
        monkeypatch.setenv("APA_USERNAME", "alice@example.com")
        monkeypatch.setenv("APA_PASSWORD", "pw")
        mgr = LoginManager(MINIMAL_CONFIG)
        with patch.object(mgr, "is_authenticated", return_value=False):
            with patch.object(mgr, "login", return_value=True) as mock_login:
                result = mgr.refresh_if_needed()
        mock_login.assert_called_once_with(save=True)
        assert result is True
