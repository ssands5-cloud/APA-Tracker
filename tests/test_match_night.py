"""Match Night Deployment Mode (Phase 4D): slim one-fixture package, AES-GCM encryption, installable
offline web app. Synthetic players only (the Excel War Room fixture)."""

from __future__ import annotations

import functools
import http.server
import json
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from tests.test_excel_war_room_formulas import _payload
from ui.match_night import (
    MatchNightError,
    build_site,
    decrypt_package,
    encrypt_package,
    select_fixture,
    slim_payload,
)

BUILT = "2026-10-07 18:00 UTC"
PASS = "correct horse battery staple"


def test_slim_package_holds_only_what_one_fixture_needs():
    payload = _payload()
    pick = select_fixture(payload, "1001", BUILT)
    assert pick["our_scope"] == "sharks-a|d1|Fall 2026" and pick["opp_scope"] == "falcons-a|d1|Fall 2026"
    slim = slim_payload(payload, pick)
    full = {p["id"] for p in slim["players"] if p["team_history"]}
    stubs = {p["id"] for p in slim["players"] if not p["team_history"]}
    assert full == {1, 2, 3, 10, 11}                       # the two rosters
    assert stubs == {12}                                    # Zed: a shared opponent, name + record ID only
    assert 13 not in {p["id"] for p in slim["players"]} and 4 not in {p["id"] for p in slim["players"]}
    assert {r["player_id"] for r in slim["evidence"]} <= full and {r["format"] for r in slim["evidence"]} == {"EIGHT"}
    assert all(h["team_external_id"] in ("sharks-a", "falcons-a") for p in slim["players"] for h in p["team_history"])
    assert len(slim["match_day"]["fixtures"]) == 1 and slim["match_day"]["fixtures"][0]["match_external_id"] == "1"
    assert slim["match_night"]["fixture_label"] == "Sharks · Fall 2026 · 8-Ball vs Falcons · Fall 2026 · 8-Ball"


def test_bye_or_unknown_fixture_is_refused():
    with pytest.raises(MatchNightError, match="no opponent with a captured roster"):
        select_fixture(_payload(), "1001", BUILT, match_id="2")          # the Oct 18 bye
    with pytest.raises(MatchNightError, match="not a fixture"):
        select_fixture(_payload(), "1001", BUILT, match_id="999")


def test_package_is_unreadable_without_the_passphrase(tmp_path):
    result = build_site(_payload(), viewer_external_id="1001", passphrase=PASS, built_at=BUILT, out=tmp_path)
    package = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    clear = json.dumps({k: v for k, v in package.items() if k != "ciphertext"})
    site_text = " ".join(p.read_text(encoding="utf-8") for p in tmp_path.glob("*") if p.suffix in (".html", ".json", ".js", ".webmanifest"))
    for secret in ("Ann Archer", "Cam Cole", "Sharks", "Falcons", "1001", "2001"):
        assert secret not in site_text, secret
    assert package["built"] == "Wed Oct 7, 2026" and package["iterations"] == 600_000 and "built" in clear
    html = decrypt_package(package, PASS)
    assert "Ann Archer" in html and "Match Night package" in html and "80000001" not in html
    with pytest.raises(Exception):
        decrypt_package(package, PASS + "x")
    with pytest.raises(MatchNightError, match="at least 16"):
        encrypt_package("x", "short", built="today")
    assert result["package_bytes"] < 2_000_000
    for name in ("index.html", "sw.js", "manifest.webmanifest", ".nojekyll", "icons/icon-192.png",
                 "icons/icon-512.png", "icons/apple-touch-icon.png"):
        assert (tmp_path / name).exists(), name
    manifest = json.loads((tmp_path / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["display"] == "standalone" and manifest["start_url"] == "./"


@pytest.fixture()
def served(tmp_path):
    site = tmp_path / "site"
    build_site(_payload(), viewer_external_id="1001", passphrase=PASS, built_at=BUILT, out=site)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *a, **k: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/"
    httpd.shutdown()


IPHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True,
          "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                        "Version/18.0 Mobile/15E148 Safari/604.1"}


def test_phone_unlock_first_screen_remember_and_offline(served):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(**IPHONE)
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(served)
            assert "Package built Wed Oct 7, 2026" in page.inner_text("#facts")
            page.fill("#pass", "wrong passphrase entirely")
            page.click("#go")
            page.wait_for_function("document.getElementById('status').textContent.includes('does not open')")
            page.fill("#pass", PASS)
            page.click("#go")
            page.wait_for_selector("#tonight .decide-sends", timeout=20000)
            tonight = page.inner_text("#tonight")
            assert "Sun Oct 11, 2026 · 11:00 AM MDT" in tonight and "Falcons" in tonight
            assert "Match Night package" in page.inner_text("body")
            # Freshness describes the whole snapshot, not the one packaged fixture.
            assert "latest recorded result Sun Sep 27, 2026" in page.inner_text(".freshness")
            # Phone first screen: the match, best sends, threats and risks are all visible without scrolling.
            for sel in ("#tonight .when", "#tonight .decide-sends", "#tonight .decide-threats", "#tonight .decide-risks"):
                box = page.locator(sel).bounding_box()
                assert box and box["y"] + box["height"] <= 844, (sel, box)
            assert page.evaluate("document.documentElement.scrollWidth") <= 390
            # Remembered on this device: a reload opens straight into Tonight.
            page.wait_for_timeout(500)
            page.reload()
            page.wait_for_selector("#tonight .decide-sends", timeout=20000)
            # Offline after the first unlock (service worker cache).
            page.evaluate("navigator.serviceWorker.ready.then(() => true)")
            ctx.set_offline(True)
            page.reload()
            page.wait_for_selector("#tonight .decide-sends", timeout=20000)
            assert "Falcons" in page.inner_text("#tonight")
            assert errors == []
        finally:
            browser.close()


class _Toggle(http.server.SimpleHTTPRequestHandler):
    fail_package = False

    def do_GET(self):
        if type(self).fail_package and self.path.split("?")[0].endswith("/package.json"):
            self.send_error(500, "simulated server error")
            return
        super().do_GET()

    def log_message(self, *a, **k):
        pass


def test_demo_label_persists_cache_is_isolated_and_errors_never_replace_the_good_package(tmp_path):
    site = tmp_path / "site"
    build_site(_payload(), viewer_external_id="1001", passphrase=PASS, built_at=BUILT, out=site, demo=True)
    handler = type("H", (_Toggle,), {"fail_package": False})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(handler, directory=str(site)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(**IPHONE)
            page = ctx.new_page()
            page.goto(url)
            # A cache belonging to ANOTHER project on the same origin, created before our worker activates.
            page.evaluate("caches.open('other-project-v1').then(c => c.put('/other.txt', new Response('keep me')))")
            page.fill("#pass", PASS)
            page.click("#go")
            page.wait_for_selector("#tonight .decide-sends", timeout=20000)
            flags = page.locator(".demo-flag")
            assert flags.count() >= 2 and all("synthetic players" in t for t in flags.all_inner_texts())
            assert "DEMO (synthetic players)" in page.inner_text(".mn-banner")
            page.evaluate("document.body.classList.add('print-matchup')")
            page.emulate_media(media="print")
            assert page.locator("#matchup-print .demo-flag").is_visible()     # the printed packet says DEMO too
            page.emulate_media(media="screen")
            page.wait_for_timeout(800)
            # Re-publish (new salt -> new app cache): only our old cache may be removed.
            build_site(_payload(), viewer_external_id="1001", passphrase=PASS, built_at=BUILT, out=site, demo=True)
            page.reload()
            page.wait_for_timeout(1500)
            names = page.evaluate("caches.keys()")
            assert "other-project-v1" in names
            assert sum(1 for n in names if n.startswith("uc-match-night-")) >= 1
            assert page.evaluate("caches.open('other-project-v1').then(c => c.match('/other.txt')).then(r => r.text())") == "keep me"
            # Server error for the package: the last good copy is used, never the error page.
            page.wait_for_selector("#tonight .decide-sends, #pass", timeout=20000)
            handler.fail_package = True
            page.reload()
            page.wait_for_function("document.querySelector('#tonight .decide-sends') || document.querySelector('#pass')", timeout=20000)
            if page.locator("#pass").count():
                page.fill("#pass", PASS)
                page.click("#go")
            page.wait_for_selector("#tonight .decide-sends", timeout=20000)
            assert "Falcons" in page.inner_text("#tonight")
            browser.close()
    finally:
        httpd.shutdown()
