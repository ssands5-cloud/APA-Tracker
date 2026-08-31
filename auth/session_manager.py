"""
Persists and reuses an authenticated requests.Session across runs so the
scheduler scripts don't have to log in on every invocation.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

import requests

from auth.login import is_logged_in, login

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, config: dict):
        self.config = config
        self.cache_path = Path(config["session"]["cache_path"])
        self.timeout = config["session"].get("timeout_seconds", 15)

    def get_session(self, force_relogin: bool = False) -> requests.Session:
        """Return an authenticated session, reusing a cached one if still valid."""
        if not force_relogin and self.cache_path.exists():
            session = requests.Session()
            self._load_cookies(session)
            if self._probe_session(session):
                logger.info("Reusing cached session")
                return session
            logger.info("Cached session expired; re-authenticating")

        session = login(requests.Session(), self.config)
        self._save_cookies(session)
        return session

    def _probe_session(self, session: requests.Session) -> bool:
        """Hit a lightweight authenticated page to confirm the session is still live."""
        site = self.config["site"]
        probe_url = site["base_url"].rstrip("/") + site.get("standings_path", "/")
        try:
            resp = session.get(probe_url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Session probe failed: %s", exc)
            return False
        return is_logged_in(resp.text)

    def _save_cookies(self, session: requests.Session) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("wb") as fh:
            pickle.dump(session.cookies, fh)
        logger.debug("Session cookies cached at %s", self.cache_path)

    def _load_cookies(self, session: requests.Session) -> None:
        with self.cache_path.open("rb") as fh:
            session.cookies.update(pickle.load(fh))
