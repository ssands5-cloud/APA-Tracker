"""UI package compatibility guards.

The release Match Night work intentionally changed the planner's rule language,
but it must not regress three long-standing captain-facing guarantees that the
browser/unit suite already enforced: estimates are not promises, legal choices
show a concrete finish, and illegal choices plainly say that no combination
works. Keep those phrases in the rendered page while retaining the more
specific 5/23 and 4/19 wording added by the release branch.

The release browser coverage also exercises a 390px phone viewport. The base
page's 24px desktop body margin leaves too little usable width once Match Night's
new fallback text is present, so the release renderer adds a small-screen layout
rule that reduces the page gutter and permits flex children to shrink/wrap. It
does not mask overflow with ``overflow-x: hidden``; content must genuinely fit.

All substitutions are deliberately anchored and fail closed. If the canonical
renderer changes so an expected anchor no longer occurs exactly once, rendering
raises rather than silently dropping a disclosure relied on by the captain UX.
"""

from __future__ import annotations

from . import dashboard as dashboard

_base_render = dashboard.render


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"dashboard compatibility guard expected one {label} anchor, found {count}")
    return text.replace(old, new, 1)


def _render_with_release_compat(*args, **kwargs):
    html = _base_render(*args, **kwargs)

    html = _replace_once(
        html,
        "verified four-player/19 fallback, which requires forfeiting match 5.</p>",
        "verified four-player/19 fallback, which requires forfeiting match 5. "
        "A skill-level estimate is not a promise, and skill-level movement is not a winning "
        "streak -- both are shown as what they really are, not as a verdict.</p>",
        "estimate disclaimer",
    )
    html = _replace_once(
        html,
        "A valid 5-player / 23 finish:",
        "A valid finish: 5-player / 23:",
        "concrete completion wording",
    )
    html = _replace_once(
        html,
        " leaves no legal 5-player / 23 completion and no legal 4-player / 19 fallback from the remaining Available players.",
        " -- No combination of tonight's remaining Available players produces a legal "
        "5-player / 23 completion or 4-player / 19 fallback.",
        "no-combination explanation",
    )
    html = _replace_once(
        html,
        "</style></head><body>",
        "@media (max-width: 600px) {\n"
        "  body { margin: 12px; }\n"
        "  .cd-cols > div { min-width: 0; }\n"
        "  .mn-sticky > span { min-width: 0; overflow-wrap: anywhere; }\n"
        "}\n"
        "</style></head><body>",
        "small-screen layout",
    )
    return html


dashboard.render = _render_with_release_compat

__all__ = ["dashboard"]
