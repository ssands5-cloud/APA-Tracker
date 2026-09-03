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
    headers = {"Content-Type": "application/json"}
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

    if not isinstance(payload, dict):
        raise GraphQLTransportError(
            f"GraphQL response JSON was {type(payload).__name__}, expected an object with 'data' or 'errors'"
        )

    errors = payload.get("errors")
    if errors:
        if not isinstance(errors, list):
            raise GraphQLTransportError(f"GraphQL errors field was {type(errors).__name__}, expected a list")
        codes = {(e.get("extensions") or {}).get("code") for e in errors if isinstance(e, dict)}
        if resp.status_code in _AUTH_STATUS_CODES or codes & _AUTH_EXTENSION_CODES:
            raise GraphQLAuthError(errors, status_code=resp.status_code)
        raise GraphQLError(errors, status_code=resp.status_code)

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
