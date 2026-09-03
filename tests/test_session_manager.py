from __future__ import annotations

import json
import os

import requests

from auth.session_manager import SessionManager


def test_session_manager_saves_and_loads_json_cookies(tmp_path):
    cache = tmp_path / "session.json"
    config = {"session": {"cache_path": str(cache)}, "site": {"base_url": "https://example.test", "standings_path": "/standings"}}
    manager = SessionManager(config)

    session = requests.Session()
    session.cookies.set_cookie(requests.cookies.create_cookie(name="sessionid", value="abc123", domain="example.test", path="/"))
    session.cookies.set_cookie(requests.cookies.create_cookie(name="csrf", value="token", domain="example.test", path="/"))

    manager._save_cookies(session)
    assert cache.exists()
    assert os.stat(cache).st_mode & 0o777 == 0o600

    payload = json.loads(cache.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert {c["name"] for c in payload["cookies"]} == {"sessionid", "csrf"}

    restored = requests.Session()
    manager._load_cookies(restored)
    assert restored.cookies.get("sessionid") == "abc123"
    assert restored.cookies.get("csrf") == "token"


def test_session_manager_ignores_invalid_cache_data(tmp_path):
    cache = tmp_path / "session.json"
    cache.write_text("not valid json", encoding="utf-8")
    config = {"session": {"cache_path": str(cache)}, "site": {"base_url": "https://example.test", "standings_path": "/standings"}}
    manager = SessionManager(config)
    restored = requests.Session()
    manager._load_cookies(restored)
    assert list(restored.cookies) == []
