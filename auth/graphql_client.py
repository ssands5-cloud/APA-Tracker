"""
Thin HTTP client for the APA / CPA "Member Services" GraphQL API.

The whole platform (login, token refresh, standings, rosters, player
stats, match details, ...) is served from one GraphQL endpoint -- there
is no server-rendered HTML to scrape and no separate REST API for any of
this. See parser/apa_graphql.py for where the endpoint and documents
came from.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests

from parser.apa_graphql import GRAPHQL_ENDPOINT

logger = logging.getLogger(__name__)

_AUTH_STATUS_CODES = {401, 403}
_AUTH_EXTENSION_CODES = {"UNAUTHENTICATED", "FORBIDDEN"}

#: Observed against the live API on 2026-09-03: a rejected token comes back as
#: HTTP 200 with {"errors": [{"message": "Your token is no longer valid"}]} and
#: no UNAUTHENTICATED extension code. Status and extension checks alone
#: therefore classified it as a generic GraphQL error, and callers watching for
#: GraphQLAuthError never saw it. The message is the only signal this API gives.
#:
#: A second, DIFFERENT phrasing showed up the same way running run_all_teams()
#: for real for the first time: "Login session has expired" -- "session", not
#: "token", so none of the existing markers matched and it surfaced as a raw
#: traceback instead of the friendly "get a fresh token" message. This API
#: appears to have more than one wording for the same underlying rejection;
#: expect this list to keep growing as new ones turn up, not to be complete.
_AUTH_MESSAGE_MARKERS = (
    "token is no longer valid",
    "invalid token",
    "token is invalid",
    "token expired",
    "expired token",
    "session has expired",
    "session expired",
    "not authenticated",
    "unauthenticated",
    "unauthorized",
    "not authorized",
)


def _is_auth_failure(errors: list[dict[str, Any]], status_code: Optional[int]) -> bool:
    """Whether a GraphQL error array means "your token is no good"."""
    if status_code in _AUTH_STATUS_CODES:
        return True
    codes = {(e.get("extensions") or {}).get("code") for e in errors}
    if codes & _AUTH_EXTENSION_CODES:
        return True
    text = " ".join((e.get("message") or "") for e in errors).lower()
    return any(marker in text for marker in _AUTH_MESSAGE_MARKERS)


class GraphQLError(RuntimeError):
    """Raised when a GraphQL response includes a top-level `errors` array,
    or an HTTP error status with no usable GraphQL error payload."""

    def __init__(self, errors: list[dict[str, Any]], status_code: Optional[int] = None):
        self.errors = errors
        self.status_code = status_code
        messages = "; ".join(e.get("message", "unknown error") for e in errors)
        super().__init__(f"GraphQL request failed (HTTP {status_code}): {messages}")


class GraphQLAuthError(GraphQLError):
    """Raised specifically when the server indicates the access token is
    missing, expired, or invalid -- HTTP 401/403, or a GraphQL error with
    an UNAUTHENTICATED/FORBIDDEN extension code. Callers (session_manager)
    key off this type alone to decide whether to refresh and retry."""


class GraphQLTransportError(RuntimeError):
    """Raised for failures below the GraphQL layer: a non-JSON response
    body, a network error after retries are exhausted, or an HTTP error
    status with no parseable GraphQL error payload."""


def execute(
    query: str,
    variables: Optional[dict[str, Any]] = None,
    access_token: Optional[str] = None,
    timeout: float = 15,
    max_retries: int = 0,
) -> dict[str, Any]:
    """POST a GraphQL query/mutation and return its `data` payload.

    The auth header is lowercase `authorization` holding the raw access
    token -- NOT `Authorization: Bearer <token>`. Confirmed from the
    real app's Apollo Client setup; do not "fix" this to the more common
    Bearer-prefixed convention, it will not work against this API.

    `max_retries` only covers transient transport failures (connection
    errors, timeouts) with a short exponential backoff -- it does not
    retry on GraphQL errors or HTTP 4xx/5xx, those are raised directly.
    """
    headers = {
        "Content-Type": "application/json",
        # gql.poolplayers.com is a different subdomain from
        # league.poolplayers.com (where the token is captured), making this
        # a cross-origin request. A real browser sends Origin/Referer on
        # that automatically; requests does not add them on its own. First
        # real live run without these got "Login session has expired" on a
        # token captured seconds earlier -- too fast to be real expiry, and
        # consistent with a same-origin/session check on the backend that a
        # bearer-token-only request without these headers fails. Unverified
        # as THE fix until confirmed against the live API, but it's the
        # most concrete, honest difference between what the browser sent
        # (and which worked) and what this client was sending (which didn't).
        "Origin": "https://league.poolplayers.com",
        "Referer": "https://league.poolplayers.com/",
    }
    if access_token:
        headers["authorization"] = access_token

    resp = _post_with_retries(query, variables, headers, timeout, max_retries)

    try:
        payload = resp.json()
    except ValueError as exc:
        if resp.status_code in _AUTH_STATUS_CODES:
            raise GraphQLAuthError(
                [{"message": f"HTTP {resp.status_code}, non-JSON body"}], status_code=resp.status_code
            ) from exc
        raise GraphQLTransportError(f"Non-JSON response body (HTTP {resp.status_code})") from exc

    if payload.get("errors"):
        if _is_auth_failure(payload["errors"], resp.status_code):
            raise GraphQLAuthError(payload["errors"], status_code=resp.status_code)
        raise GraphQLError(payload["errors"], status_code=resp.status_code)

    if resp.status_code in _AUTH_STATUS_CODES:
        raise GraphQLAuthError(
            [{"message": f"HTTP {resp.status_code} with no errors array"}], status_code=resp.status_code
        )

    if resp.status_code >= 400:
        raise GraphQLTransportError(f"HTTP {resp.status_code} with no errors array: {payload!r}")

    return payload.get("data") or {}


def _post_with_retries(
    query: str,
    variables: Optional[dict[str, Any]],
    headers: dict[str, str],
    timeout: float,
    max_retries: int,
) -> requests.Response:
    attempt = 0
    while True:
        try:
            logger.debug("POST %s (auth=%s, attempt=%d)", GRAPHQL_ENDPOINT, "authorization" in headers, attempt + 1)
            return requests.post(
                GRAPHQL_ENDPOINT,
                json={"query": query, "variables": variables or {}},
                headers=headers,
                timeout=timeout,
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            attempt += 1
            if attempt > max_retries:
                raise GraphQLTransportError(f"Network error after {attempt} attempt(s): {exc}") from exc
            backoff = min(0.5 * 2 ** (attempt - 1), 5.0)
            logger.warning(
                "Transient network error (attempt %d/%d), retrying in %.1fs: %s",
                attempt,
                max_retries,
                backoff,
                exc,
            )
            time.sleep(backoff)
