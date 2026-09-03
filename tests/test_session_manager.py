"""Regression tests for auth/session_manager.py.

Ported from 01sessionpersistencefix.patch, which targeted a now-removed
auth/login_manager.py. The same defect class -- session state cached with
pickle, at a predictable path, with no protection against a corrupted or
tampered file -- was still present in the current auth/session_manager.py,
just under a different module after the code was reorganised into
auth/login.py + auth/session_manager.py.
"""

from __future__ import annotations

import json
import os
import pickle
import stat
import subprocess

import pytest
import requests

from auth.session_manager import SESSION_FORMAT_VERSION, SessionManager


def _config(cache_path):
    return {
        "site": {"base_url": "https://example.invalid", "standings_path": "/standings"},
        "session": {"cache_path": str(cache_path), "timeout_seconds": 5},
    }


@pytest.fixture
def cache_path(tmp_path):
    return tmp_path / ".session_cache" / "cookies.json"


class TestSaveWritesJSON:
    def test_save_creates_json_file_with_version_and_cookies(self, cache_path):
        mgr = SessionManager(_config(cache_path))
        session = requests.Session()
        session.cookies.set("sid", "abc123", domain="example.invalid", path="/")

        mgr._save_cookies(session)

        assert cache_path.exists()
        payload = json.loads(cache_path.read_text())
        assert payload["version"] == SESSION_FORMAT_VERSION
        assert payload["cookies"] == [
            {
                "name": "sid",
                "value": "abc123",
                "domain": "example.invalid",
                "path": "/",
                "secure": False,
                "expires": None,
            }
        ]

    def test_save_creates_file_at_mode_600(self, cache_path):
        mgr = SessionManager(_config(cache_path))
        mgr._save_cookies(requests.Session())

        if os.name == "nt":
            # os.open(..., 0o600) is a no-op on NTFS -- st_mode always reads
            # back as the default 0o666 regardless. The real protection on
            # Windows is the icacls ACL rewrite in _save_cookies; assert
            # that actually landed instead of a POSIX-only stat bit that
            # Windows has no meaningful equivalent for.
            result = subprocess.run(
                ["icacls", str(cache_path)], capture_output=True, text=True, check=True,
            )
            assert "Everyone" not in result.stdout
            assert "BUILTIN\\Users" not in result.stdout
        else:
            mode = stat.S_IMODE(os.stat(cache_path).st_mode)
            assert mode == 0o600


class TestRoundTrip:
    def test_save_then_load_round_trips_cookies(self, cache_path):
        mgr = SessionManager(_config(cache_path))
        original = requests.Session()
        original.cookies.set("sid", "abc123", domain="example.invalid", path="/")
        mgr._save_cookies(original)

        restored = requests.Session()
        assert mgr._load_cookies(restored) is True
        assert restored.cookies.get("sid", domain="example.invalid") == "abc123"


class TestCorruptOrIncompatibleCacheIsRejectedGracefully:
    """The core of the original defect: a bad cache file must not crash the
    caller. It should be treated as "no usable cache", triggering a fresh
    login instead of raising.
    """

    def test_non_json_file_is_rejected(self, cache_path):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("not json at all")
        mgr = SessionManager(_config(cache_path))

        assert mgr._load_cookies(requests.Session()) is False

    def test_a_pickle_file_from_the_old_format_is_rejected_not_unpickled(self, cache_path):
        """A cache left by an older pickle-based build must never be passed
        to pickle.load -- that was the exact vulnerability being removed.
        """
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("wb") as fh:
            pickle.dump({"sid": "abc123"}, fh)
        mgr = SessionManager(_config(cache_path))

        assert mgr._load_cookies(requests.Session()) is False

    def test_wrong_version_is_rejected(self, cache_path):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"version": 999, "cookies": []}))
        mgr = SessionManager(_config(cache_path))

        assert mgr._load_cookies(requests.Session()) is False

    def test_malformed_cookie_entries_are_rejected(self, cache_path):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "version": SESSION_FORMAT_VERSION,
            "cookies": [{"name": "sid"}],  # missing required "value"
        }))
        mgr = SessionManager(_config(cache_path))

        assert mgr._load_cookies(requests.Session()) is False


class TestGetSessionFallsBackOnBadCache:
    def test_corrupt_cache_triggers_fresh_login_instead_of_raising(self, cache_path, monkeypatch):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("not json")
        mgr = SessionManager(_config(cache_path))

        fresh = requests.Session()
        monkeypatch.setattr("auth.session_manager.login", lambda session, config: fresh)

        result = mgr.get_session()

        assert result is fresh
        assert cache_path.read_text()  # _save_cookies overwrote the corrupt file
