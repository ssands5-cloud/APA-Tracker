"""Shared classification between a genuine, global APA authentication
expiry and a per-scope FORBIDDEN/denied object.

Any Ultimate Coach stage that walks objects an authenticated viewer may
not have blanket visibility into -- most importantly divisions/aliases
discovered through OTHER roster members' own cross-league history, not
just the viewer's own teams -- can hit a real APA FORBIDDEN response for
an object that is genuinely, permanently unavailable to this viewer, even
though the viewer's own token is otherwise completely valid. Distinguishing
that from a real token expiry matters in both directions:

- Trusting a single denial as permanent proof is unsafe: APA's own auth
  rejection wording has been observed to be inconsistent right at the
  token-expiry boundary (see auth/graphql_client.py's own notes), and a
  permanently-checkpointed "source limitation" is never revisited, even
  after a fresh, valid token is obtained moments later.
- Never being ABLE to record a permanent, confirmed denial is equally
  unsafe in the other direction: without one, a genuinely, permanently
  denied scope causes the crawl to fail with an apparent auth expiry
  forever, forcing endless reauthentication with zero forward progress.

This module exists to give every stage the same two-sided answer: retry
once after independently confirming the SAME token is still viewer-valid,
and re-confirm viewer validity again after the retry's own failure before
trusting the denial as permanent.
"""

from __future__ import annotations

from scraper.graphql_scraper import AccessTokenExpired, fetch_dashboard_teams


class ConfirmedScopeDenial(RuntimeError):
    """A scoped call failed twice -- once originally, once retried -- with
    the SAME token independently confirmed still viewer-valid immediately
    before AND immediately after the retry. Only at that point is this
    treated as a real, permanent APA denial rather than a one-off,
    timing-related rejection."""


def viewer_session_still_valid(config: dict) -> bool:
    """Revalidate the SAME token after a scope request reports auth failure.

    APA can use FORBIDDEN for both a dead login and a scope/object denial.
    If dashboardTeams still returns an authenticated viewer with the same
    token, the token is globally valid and only the attempted scope is
    unavailable. If viewer validation also fails, the token really is dead
    and the caller must re-raise so normal resume/reauth semantics apply.
    """
    try:
        viewer = fetch_dashboard_teams(config)
    except AccessTokenExpired:
        return False
    return bool((viewer or {}).get("id"))


def call_with_confirmed_denial_retry(config: dict, fetch_call):
    """Call ``fetch_call()`` (a zero-arg closure), retrying once before a
    scope denial is trusted enough to be treated as permanent.

    Raises the original (or retry's) AccessTokenExpired unchanged -- so
    normal resume/reauth semantics apply -- if the SAME token cannot be
    revalidated as still viewer-valid at EITHER failure. Viewer validity is
    re-checked after the retry's own failure too: the token can genuinely,
    globally expire in the window between the first revalidation and the
    retry call, and treating that second failure as a confirmed denial
    without re-confirming the viewer would reopen the exact same
    permanent-mislabeling risk this function exists to close.

    Raises ConfirmedScopeDenial only after the original call failed, the
    SAME token was confirmed viewer-valid, the retry ALSO failed, and the
    SAME token was confirmed viewer-valid again immediately afterward.
    """
    try:
        return fetch_call()
    except AccessTokenExpired as exc:
        if not viewer_session_still_valid(config):
            raise
        try:
            return fetch_call()
        except AccessTokenExpired as retry_exc:
            if not viewer_session_still_valid(config):
                raise
            raise ConfirmedScopeDenial(str(retry_exc)) from retry_exc
