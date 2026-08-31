"""
Placeholder for a future interactive dashboard.

Nothing here is wired up yet -- this just sketches the shape so the real
thing (Streamlit, a small Flask app, whatever fits) has an obvious place
to land. Run any real dashboard as its own process against the same
SQLite file the scheduler jobs write to.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError(
        "Dashboard not implemented yet. Options worth considering:\n"
        "  - Streamlit: quickest path to charts over database/queries.py\n"
        "  - Flask + Chart.js: more control, more setup\n"
        "Either way, read from the same SQLite DB the scheduler writes to; "
        "don't scrape from the dashboard process itself."
    )


if __name__ == "__main__":
    main()
