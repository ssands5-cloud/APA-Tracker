"""
LoginManager: session lifecycle management with per-user persistence.

Each user's authenticated session is stored in
``~/.apa_tracker/sessions/<username>.json`` with mode 0600 so that only
the owning OS account can read the file.

Typical usage::

    mgr = LoginManager(config)
    session = mgr.get_session()   # handles load/login/refresh automatically
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from auth.credentials import (
    get_credentials_from_env,
    get_credentials_from_prompt,
    get_user_session_path,
    save_credentials_option,
)
from parser.apa_page_map import LOGIN_FORM

logger = logging.getLogger(__name__)


class AuthenticationError(RuntimeError):
    """Raised when login against the APA portal fails."""


class LoginManager:
    """Manage authentication and session persistence for a single APA user.

    Args:
        config:   The loaded ``apa_config.yaml`` dictionary.
        username: Override the username; falls back to env var then prompt.
        password: Override the password; falls back to env var then prompt.
    """

    def __init__(
        self,
        config: dict,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self.config = config
        self._session: Optional[requests.Session] = None

        # Resolve credentials: explicit > env > prompt
        env_user, env_pass = get_credentials_from_env()
        self.username = username or env_user
        self._password = password or env_pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_session(self, force_relogin: bool = False) -> requests.Session:
        """Return an authenticated :class:`requests.Session`.

        Tries, in order:
        1. In-memory session (same process run)
        2. Saved session from disk (if still valid)
        3. Fresh login

        Args:
            force_relogin: Skip cached sessions and always log in fresh.
        """
        if not force_relogin and self._session and self.is_authenticated():
            return self._session

        if not force_relogin and self.username:
            session_path = get_user_session_path(self.username)
            if session_path.exists():
                loaded = self.load_session(session_path)
                if loaded:
                    logger.info("✓ Loaded cached session for %s", self.username)
                    print(f"✓ Loaded cached session for {self.username}")
                    return self._session  # type: ignore[return-value]
                logger.info("Cached session for %s has expired; re-logging in", self.username)

        self.login()
        return self._session  # type: ignore[return-value]

    def login(self, save: Optional[bool] = None) -> bool:
        """Perform a full login against the APA portal.

        Prompts for credentials if they were not supplied at construction
        time and are not in the environment.

        Args:
            save: If ``True``, always persist the session.  If ``False``,
                  never persist.  If ``None`` (default), ask the user when
                  running interactively; skip the prompt when env vars are
                  in use.

        Returns:
            ``True`` on success.  Raises :class:`AuthenticationError` on
            failure.
        """
        # Ensure we have credentials before touching the network.
        prompted = False
        if not self.username or not self._password:
            self.username, self._password = get_credentials_from_prompt()
            prompted = True

        session = requests.Session()
        site = self.config["site"]
        timeout = self.config.get("session", {}).get("timeout_seconds", 15)
        login_url = site["base_url"].rstrip("/") + site["login_path"]

        logger.info("Fetching login page: %s", login_url)
        try:
            get_resp = session.get(login_url, timeout=timeout)
            get_resp.raise_for_status()
        except requests.RequestException as exc:
            raise AuthenticationError(f"Could not reach login page: {exc}") from exc

        csrf_token = self._extract_csrf_token(get_resp.text, LOGIN_FORM["csrf_field_name"])

        payload: dict = {
            LOGIN_FORM["username_field"]: self.username,
            LOGIN_FORM["password_field"]: self._password,
        }
        if csrf_token:
            payload[LOGIN_FORM["csrf_field_name"]] = csrf_token

        logger.info("Submitting login form for user %s", self.username)
        try:
            post_resp = session.post(login_url, data=payload, timeout=timeout)
            post_resp.raise_for_status()
        except requests.RequestException as exc:
            raise AuthenticationError(f"Login request failed: {exc}") from exc

        if not self._check_success(post_resp.text):
            raise AuthenticationError(
                "Login submitted but session does not appear authenticated. "
                "Check credentials or update LOGIN_FORM in parser/apa_page_map.py."
            )

        self._session = session
        logger.info("Login successful for %s", self.username)

        # Decide whether to save the session.
        env_user, _ = get_credentials_from_env()
        using_env = bool(env_user)
        if save is None:
            if using_env:
                save = True  # Auto-save when running via env vars (CI)
            elif prompted:
                save = save_credentials_option()
            else:
                save = False

        if save:
            path = self.save_session()
            print(f"✓ Login successful! Session saved to {path}")
        else:
            print(f"✓ Login successful for {self.username}")

        return True

    def is_authenticated(self) -> bool:
        """Check whether the current in-memory session is still valid.

        Sends a lightweight probe request to the standings page and looks
        for logged-in markers in the response body.
        """
        if self._session is None:
            return False
        site = self.config["site"]
        timeout = self.config.get("session", {}).get("timeout_seconds", 15)
        probe_url = site["base_url"].rstrip("/") + site.get("standings_path", "/")
        try:
            resp = self._session.get(probe_url, timeout=timeout)
            resp.raise_for_status()
            return self._check_success(resp.text)
        except requests.RequestException as exc:
            logger.warning("Session probe failed: %s", exc)
            return False

    def save_session(self) -> Path:
        """Pickle the current session cookies to disk.

        The file is written with mode 0600 so only the current OS user can
        read it.

        Returns:
            The :class:`~pathlib.Path` where the file was written.
        """
        if not self.username:
            raise AuthenticationError("Cannot save session: username is unknown.")
        if self._session is None:
            raise AuthenticationError("Cannot save session: not logged in.")

        path = get_user_session_path(self.username)
        with path.open("wb") as fh:
            pickle.dump(self._session.cookies, fh)
        path.chmod(0o600)
        logger.debug("Session saved to %s", path)
        return path

    def load_session(self, path: Optional[Path] = None) -> bool:
        """Restore a session from a pickle file.

        Args:
            path: Explicit path to the pickle.  Defaults to the standard
                  user session path derived from :attr:`username`.

        Returns:
            ``True`` if the restored session passes a liveness probe.
        """
        if path is None:
            if not self.username:
                return False
            path = get_user_session_path(self.username)

        if not path.exists():
            return False

        session = requests.Session()
        try:
            with path.open("rb") as fh:
                session.cookies.update(pickle.load(fh))
        except Exception as exc:
            logger.warning("Failed to load session from %s: %s", path, exc)
            return False

        self._session = session
        return self.is_authenticated()

    def refresh_if_needed(self) -> bool:
        """Re-login if the current session has expired.

        Returns:
            ``True`` if the session is valid (either still alive or
            successfully refreshed).  ``False`` if refresh failed.
        """
        if self.is_authenticated():
            return True
        logger.info("Session expired; attempting refresh for %s", self.username)
        try:
            self.login(save=True)
            return True
        except AuthenticationError as exc:
            logger.error("Session refresh failed: %s", exc)
            return False

    def clear_session(self) -> None:
        """Delete the saved session file for this user, if it exists."""
        if not self.username:
            return
        path = get_user_session_path(self.username)
        if path.exists():
            path.unlink()
            logger.info("Cleared session file: %s", path)
            print(f"✓ Session cleared for {self.username}")
        else:
            print(f"No saved session found for {self.username}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_csrf_token(html: str, field_name: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        token_input = soup.find("input", {"name": field_name})
        return token_input["value"] if token_input else None  # type: ignore[index]

    @staticmethod
    def _check_success(html: str) -> bool:
        return any(marker in html for marker in LOGIN_FORM["success_markers"])
