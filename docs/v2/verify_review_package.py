"""Verify an OWNER REVIEW V2 package before handing it back (prints local names; keep output local).

Checks: embedded data identical to the source package; M3-mode answers identical to the source package; the file
opens on V2 even after M3 was chosen and an old stored preference exists (same browser profile, reopened); engine
badge shows V2 with build label/time; the four Team Status features render; no page errors and no horizontal
scroll at 1280 and 390 px; prints the answer to one put-up for the given cap values.

    python docs/v2/verify_review_package.py --review <review html> --package <source html> --ours <scope> --theirs <scope> \
        --opponent "<their player display name>" [--shots <dir>]
"""
import argparse
import hashlib
import re
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright


def data_hash(p):
    s = Path(p).read_text(encoding="utf-8")
    return hashlib.sha256(re.search(r'<script id="uc-data" type="application/json">(.*?)</script>', s, re.S).group(1).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review", required=True)
    ap.add_argument("--package", required=True)
    ap.add_argument("--ours", required=True)
    ap.add_argument("--theirs", required=True)
    ap.add_argument("--opponent", required=True)
    ap.add_argument("--shots")
    a = ap.parse_args()
    review, package = Path(a.review).resolve(), Path(a.package).resolve()
    problems = []
    same_data = data_hash(review) == data_hash(package)
    print("data identical:", same_data)
    problems += [] if same_data else ["data differs"]
    print("review sha256:", hashlib.sha256(review.read_bytes()).hexdigest())
    print("package sha256:", hashlib.sha256(package.read_bytes()).hexdigest())
    with sync_playwright() as pw, tempfile.TemporaryDirectory() as prof:
        b = pw.chromium.launch()
        def m3_answers(path, eng):
            pg = b.new_page(); pg.goto(path.as_uri()); pg.wait_for_selector("#bc-team-a")
            arg = f",{eng!r}" if eng else ""
            p = pg.evaluate(f"window.__ucPlanFor({a.ours!r},{a.theirs!r},'EIGHT',null,null,0,0,23{arg})"); pg.close()
            return (p["lead"]["our"], [(r["their"], r["our"], r["level"]) for r in p["responses"]])
        same_m3 = m3_answers(package, None) == m3_answers(review, "m3")
        print("M3 answers identical:", same_m3)
        problems += [] if same_m3 else ["M3 answers differ"]
        b.close()
        for width, tag in ((1280, "desktop"), (390, "phone")):
            ctx = pw.chromium.launch_persistent_context(prof + tag, viewport={"width": width, "height": 1000})
            pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(review.as_uri()); pg.wait_for_selector("#bc-team-a")
            pg.locator("#uc-engine-badge [data-engine='m3']").click()
            pg.evaluate("localStorage.setItem('ultimate-coach:engine','m3')")
            ctx.close()
            ctx = pw.chromium.launch_persistent_context(prof + tag, viewport={"width": width, "height": 1000})
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(review.as_uri()); pg.wait_for_selector("#bc-team-a")
            engine, badge = pg.evaluate("window.__ucEngine()"), pg.inner_text("#uc-engine-badge").replace("\n", " ")
            print(tag, "reopened engine:", engine, "| badge:", badge[:160])
            if engine != "v2" or "ENGINE: V2 CANDIDATE" not in badge:
                problems.append(f"{tag}: did not reopen on V2")
            pg.select_option("#bc-team-a", a.ours); pg.select_option("#bc-team-b", a.theirs)
            pg.wait_for_selector(".matchup-row[data-their]")
            for cap in ("23", "22", ""):
                pg.evaluate("v => { const c = document.getElementById('bc-cap'); c.value = v; c.dispatchEvent(new Event('input', {bubbles: true})); }", cap)
                row = next((r for r in pg.evaluate("() => window.UC_BC_LAST.rows") if r["their"] == a.opponent), None)
                print(tag, f"cap {cap or 'cleared'}: {a.opponent} ->", row and row["our"], row and row["level"])
            pg.evaluate("() => { const c = document.getElementById('bc-cap'); c.value = '23'; c.dispatchEvent(new Event('input', {bubbles: true})); }")
            pg.locator(".matchup-row[data-their]", has_text=a.opponent).first.click(); pg.wait_for_selector(".send-hero")
            print(tag, "send card:", pg.locator(".send-hero .send-name").first.inner_text())
            if a.shots:
                pg.screenshot(path=str(Path(a.shots) / f"verify_send_card_{tag}.png"))
            pg.click("a.nav-tab[data-tab=team]"); pg.wait_for_timeout(400)
            pids = [s.get_attribute("data-pid") for s in pg.locator('#lineup-lab select[data-plan="lineup"]').all()]
            for pid in pids[:5]:
                pg.select_option(f'#lineup-lab select[data-plan="lineup"][data-pid="{pid}"]', "Planned")
            feats = {s: pg.locator(s).first.is_visible() for s in ("#ll-five-check", "#ll-briefing", "#ll-swap", "#team-rosters")}
            print(tag, "features:", feats)
            problems += [f"{tag}: {k} missing" for k, v in feats.items() if not v]
            hs = pg.evaluate("document.documentElement.scrollWidth > innerWidth")
            print(tag, "errors:", errs, "| horizontal scroll:", hs)
            problems += ([f"{tag}: page errors"] if errs else []) + ([f"{tag}: horizontal scroll"] if hs else [])
            pg.evaluate("localStorage.clear()"); ctx.close()
    print("RESULT:", "PASS" if not problems else "FAIL " + "; ".join(problems))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
