"""
Handles authentication against the APA league portal.

Credentials are read from environment variables (APA_USERNAME / APA_PASSWORD)
never from apa_config.yaml or source control. See README.md for setup.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

from parser.apa_page_map import LOGIN_FORM

logger = logging.getLogger(__name__)


class LoginError(RuntimeError):
    """Raised when authentication against the league portal fails."""


@dataclass
class Credentials:
    username: str
    password: str

    @classmethod
    def from_env(cls) -> "Credentials":
        username = os.environ.get("APA_USERNAME")
        password = os.environ.get("APA_PASSWORD")
        if not username or not password:
            raise LoginError(
                "APA_USERNAME and APA_PASSWORD must be set in the environment. "
                "Copy .env.example to .env and fill in your league portal credentials."
            )
        return cls(username=username, password=password)


def _extract_csrf_token(html: str, field_name: str) -> Optional[str]:
    """Pull a hidden CSRF/verification token out of the login form, if present.

    Many portals embed a per-request token (csrf_token,
    __RequestVerificationToken, etc.) that must be echoed back with the
    login POST. Adjust `field_name` in parser/apa_page_map.py once you've
    inspected the real login form's markup.
    """
    soup = BeautifulSoup(html, "html.parser")
    token_input = soup.find("input", {"name": field_name})
    return token_input["value"] if token_input else None


def login(session: requests.Session, config: dict, credentials: Optional[Credentials] = None) -> requests.Session:
    """Authenticate `session` against the configured league portal.

    Returns the same session, now carrying an authenticated cookie jar.
    Raises LoginError on failure.
    """
    credentials = credentials or Credentials.from_env()
    site = config["site"]
    timeout = config.get("session", {}).get("timeout_seconds", 15)
    login_url = site["base_url"].rstrip("/") + site["login_path"]

    logger.info("Fetching login page: %s", login_url)
    get_resp = session.get(login_url, timeout=timeout)
    get_resp.raise_for_status()

    csrf_token = _extract_csrf_token(get_resp.text, LOGIN_FORM["csrf_field_name"])

    payload = {
        LOGIN_FORM["username_field"]: credentials.username,
        LOGIN_FORM["password_field"]: credentials.password,
    }
    if csrf_token:
        payload[LOGIN_FORM["csrf_field_name"]] = csrf_token

    logger.info("Submitting login form for user %s", credentials.username)
    post_resp = session.post(login_url, data=payload, timeout=timeout)
    post_resp.raise_for_status()

    if not is_logged_in(post_resp.text):
        raise LoginError(
            "Login submitted but session does not appear authenticated. "
            "Check credentials, or update LOGIN_FORM in parser/apa_page_map.py "
            "if the real form's field names differ."
        )

    logger.info("Login successful")
    return session


def is_logged_in(html: str) -> bool:
    """Heuristic check that a page reflects an authenticated session.

    Looks for any of LOGIN_FORM['success_markers'] in the page text.
    Update that list in parser/apa_page_map.py once you know what a real
    logged-in page looks like (e.g. a 'Log out' link or account nav item).
    """
    return any(marker in html for marker in LOGIN_FORM["success_markers"])
