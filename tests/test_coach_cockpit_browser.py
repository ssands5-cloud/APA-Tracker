"""Real-browser mobile regression for the one-stop Coach Cockpit."""

from __future__ import annotations

import shutil

import pytest

from scripts import build_coach_advantage_bundle as builder
from scripts.build_coherent_demo import build as build_coherent
from scripts.build_full_production_demo import FIXTURE_SCOPE

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright


@pytest.fixture(scope="module")
def dashboard_path(tmp_path_factory):
    db = build_coherent(str(tmp_path_factory.mktemp("coach_cockpit_browser") / "demo_coherent.db"))
    root = builder.PROJECT_ROOT / "coach-advantage-runs" / "pytest-cockpit-browser"
    target = root / "fixture-test"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    try:
        builder.run_build(db, FIXTURE_SCOPE["our_team_id"], target, root)
        path = target / "html" / "dashboard.html"
        assert path.is_file()
        yield path
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_expanded_data_coverage_stays_page_safe_at_phone_width(dashboard_path):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        console_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: console_errors.append(str(exc)))
        try:
            page.goto(dashboard_path.as_uri())
            details = page.locator(".dc-embedded").first
            assert details.count() == 1
            details.locator("summary").click()
            assert "Evidence coverage" in details.inner_text()
            assert "Refresh dates" in details.inner_text()

            document_metrics = page.evaluate(
                "() => ({clientWidth: document.documentElement.clientWidth, "
                "scrollWidth: document.documentElement.scrollWidth})"
            )
            local_metrics = details.evaluate(
                "el => ({clientWidth: el.clientWidth, scrollWidth: el.scrollWidth, "
                "right: el.getBoundingClientRect().right, "
                "overflowX: getComputedStyle(el).overflowX})"
            )

            assert document_metrics["scrollWidth"] <= document_metrics["clientWidth"] + 1
            assert local_metrics["right"] <= document_metrics["clientWidth"] + 1
            assert local_metrics["overflowX"] == "auto"
            assert local_metrics["scrollWidth"] >= local_metrics["clientWidth"]
            assert console_errors == []
        finally:
            page.close()
            browser.close()
