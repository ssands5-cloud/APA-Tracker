"""
Persists and reuses an authenticated requests.Session across runs so the
scheduler scripts don't have to log in on every invocation.

Sessions are serialised as JSON, not pickle. Only the cookie fields needed to
rebuild the jar are stored, so loading a cache file can never execute code
from it -- which a pickle at a predictable path could (a corrupted or
tampered cache file becomes a fresh login, not a crash or a code-execution
risk).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import requests

from auth.login import is_logged_in, login

logger = logging.getLogger(__name__)

#: Bumped when the on-disk cache layout changes. A file written by an older
#: build is ignored rather than half-read, and the caller just logs in again.
SESSION_FORMAT_VERSION = 1


def _cookies_to_list(jar) -> list:
    """Flatten a cookie jar into JSON-serialisable dicts."""
    return [
        {
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain,
            "path": cookie.path,
            "secure": bool(cookie.secure),
            "expires": cookie.expires,
        }
        for cookie in jar
    ]


def _cookies_from_list(items):
    """Rebuild cookie objects from :func:`_cookies_to_list` output."""
    for item in items:
        yield requests.cookies.create_cookie(
            name=item["name"],
            value=item["value"],
            domain=item.get("domain", ""),
            path=item.get("path", "/"),
            secure=bool(item.get("secure", False)),
            expires=item.get("expires"),
        )


class SessionManager:
    def __init__(self, config: dict):
        self.config = config
        self.cache_path = Path(config["session"]["cache_path"])
        self.timeout = config["session"].get("timeout_seconds", 15)

    def get_session(self, force_relogin: bool = False) -> requests.Session:
        """Return an authenticated session, reusing a cached one if still valid."""
        if not force_relogin and self.cache_path.exists():
            session = requests.Session()
            if self._load_cookies(session) and self._probe_session(session):
                logger.info("Reusing cached session")
                return session
            logger.info("Cached session missing, invalid, or expired; re-authenticating")

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
        """Write the session cookies to disk as JSON, mode 0600.

        The file is created with mode 0600 up front via os.open() rather than
        opened normally and chmod-ed afterwards: a file created at the
        default umask is world-readable for as long as the write takes, and
        if the write raised, a trailing chmod would never run at all.
        """
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SESSION_FORMAT_VERSION,
            "cookies": _cookies_to_list(session.cookies),
        }
        fd = os.open(self.cache_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        logger.debug("Session cookies cached at %s", self.cache_path)

    def _load_cookies(self, session: requests.Session) -> bool:
        """Load cached cookies into `session`. Returns whether it succeeded.

        A cache file from an older (pickle-based) build, or one that is
        truncated/corrupted/tampered with, is not valid JSON -- it is
        rejected gracefully here rather than raising, so the caller just
        falls back to a fresh login instead of crashing.
        """
        try:
            with self.cache_path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError) as exc:
            logger.warning("Failed to load cached session from %s: %s", self.cache_path, exc)
            return False

        version = payload.get("version") if isinstance(payload, dict) else None
        if version != SESSION_FORMAT_VERSION:
            logger.warning(
                "Ignoring session cache %s: unsupported format version %r",
                self.cache_path, version,
            )
            return False

        try:
            for cookie in _cookies_from_list(payload.get("cookies") or []):
                session.cookies.set_cookie(cookie)
        except (KeyError, TypeError) as exc:
            logger.warning("Session cache %s is malformed: %s", self.cache_path, exc)
            return False

        return True
