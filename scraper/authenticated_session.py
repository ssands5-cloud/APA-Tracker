"""
Convenience wrappers that supply an authenticated :class:`requests.Session`
to the scraper modules.

The resolution order is:

1. Environment variables (``APA_USERNAME`` / ``APA_PASSWORD``) — preferred
   for CI and automation.
2. Saved session on disk (``~/.apa_tracker/sessions/<user>.pkl``).
3. Interactive prompt if nothing else works.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests
import yaml

from auth.login_manager import LoginManager

logger = logging.getLogger(__name__)

_CONFIG_PATH = "apa_config.yaml"


def _load_config(config_path: str = _CONFIG_PATH) -> dict:
    with open(config_path, "r") as fh:
        return yaml.safe_load(fh)


def create_authenticated_session(
    username: Optional[str] = None,
    password: Optional[str] = None,
    config: Optional[dict] = None,
    force_relogin: bool = False,
) -> requests.Session:
    """Return an authenticated :class:`requests.Session` ready for scraping.

    Credential resolution order:
    1. ``username`` / ``password`` arguments.
    2. ``APA_USERNAME`` / ``APA_PASSWORD`` environment variables.
    3. Saved session file in ``~/.apa_tracker/sessions/``.
    4. Interactive prompt (if running in a TTY).

    Args:
        username:     Override username (email).
        password:     Override password.
        config:       Pre-loaded config dict; loaded from ``apa_config.yaml``
                      if omitted.
        force_relogin: Skip any cached session and perform a fresh login.

    Returns:
        A :class:`requests.Session` whose cookie jar is authenticated.
    """
    if config is None:
        config = _load_config()

    mgr = LoginManager(config, username=username, password=password)
    return mgr.get_session(force_relogin=force_relogin)


def scrape_with_auth(
    match_id: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    config: Optional[dict] = None,
) -> str:
    """Fetch a match detail page using an authenticated session.

    This is a convenience wrapper that:
    1. Creates (or reuses) an authenticated session.
    2. Builds the match URL from the config.
    3. Returns the raw HTML body.

    Args:
        match_id: The APA match identifier.
        username: Optional username override.
        password: Optional password override.
        config:   Pre-loaded config dict; loaded from file if omitted.

    Returns:
        Raw HTML string of the match page.
    """
    if config is None:
        config = _load_config()

    session = create_authenticated_session(username=username, password=password, config=config)
    site = config["site"]
    timeout = config.get("session", {}).get("timeout_seconds", 15)

    match_path = site.get("match_path_template", "/matches/{match_id}").format(
        match_id=match_id
    )
    url = site["base_url"].rstrip("/") + match_path
    logger.info("Fetching match page: %s", url)
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text
