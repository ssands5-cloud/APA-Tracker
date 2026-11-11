"""Run the existing browser/render suites against the broadcast UI (UC_TEST_UI=broadcast).

    set UC_TEST_UI=broadcast
    python -m pytest -p tests.uc_broadcast_plugin tests/test_ultimate_coach_war_room_browser.py

`render()` defaults to ui="broadcast" and every page opens on #bc-all (all views visible), so the suites exercise
the same controls and DOM the classic page has. Without the variable this plugin does nothing.
"""

import os


def pytest_configure(config):
    if os.environ.get("UC_TEST_UI") != "broadcast":
        return
    import ui.ultimate_coach as uc
    original = uc.render

    def render(*args, **kwargs):
        kwargs.setdefault("ui", "broadcast")
        return original(*args, **kwargs)

    uc.render = render
    from playwright.sync_api import Page
    goto = Page.goto

    def open_all(self, url, *args, **kwargs):
        if isinstance(url, str) and url.startswith("file:") and "#" not in url:
            url += "#bc-all"
        return goto(self, url, *args, **kwargs)

    Page.goto = open_all
