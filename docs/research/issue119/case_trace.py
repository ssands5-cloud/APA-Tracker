"""Reproduce one Match Night answer from a built captain file and score every alternative (issue #119).

Read-only. Needs the locally built Broadcast HTML (private data, not in the repository) and the team names as
they appear in its team picker. Prints the M3 answer, every legal alternative's points now plus rest of night,
and a sensitivity check on the Unknown value. Prints names; keep its output local.

Usage: python -I case_trace.py --html <Ultimate_Coach_Broadcast.html> --ours "<team>" --theirs "<team>" [--format EIGHT] [--cap 23]
"""
import argparse
import sys
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--html", required=True)
ap.add_argument("--ours", required=True)
ap.add_argument("--theirs", required=True)
ap.add_argument("--format", default="EIGHT", choices=["EIGHT", "NINE"])
ap.add_argument("--cap", type=int, default=23)
a = ap.parse_args()
for parent in Path(__file__).resolve().parents:
    if (parent / "analytics" / "match_night_engine.py").exists():
        sys.path.insert(0, str(parent))
        break
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402
from analytics.match_night_engine import _Night  # noqa: E402
from analytics.ultimate_coach_confidence import LEVEL_POINTS  # noqa: E402

with sync_playwright() as pw:
    b = pw.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 900})
    page.goto(Path(a.html).resolve().as_uri())
    page.wait_for_selector("#bc-team-a", timeout=120000)
    opts = page.eval_on_selector_all("#bc-team-a option", "els => els.map(e => [e.value, e.textContent.trim()])")
    ok, tk = next(v for v, t in opts if t == a.ours), next(v for v, t in opts if t == a.theirs)
    page.select_option("#bc-team-a", ok); page.select_option("#bc-team-b", tk); page.wait_for_timeout(1500)
    lab = page.evaluate("""() => ({
      our: [...document.querySelectorAll('#lineup-lab select[data-plan="lineup"]')].map(s => { const r = s.closest('tr');
             return {id: s.dataset.pid, name: r.cells[0].innerText.trim(), sl: r.cells[1].innerText.trim()}; }),
      opp: [...document.querySelectorAll('#lineup-lab input[data-plan="played"]')].map(s => { const r = s.closest('tr');
             return {id: s.dataset.pid, name: r.cells[0].innerText.trim(), sl: r.cells[1].innerText.trim()}; })})""")
    conf = page.evaluate("([x, y, f]) => window.__ucConfidence(x, y, f)", [ok, tk, a.format])
    b.close()

sl = lambda s: int(s) if s.strip().isdigit() else None  # noqa: E731
ours = [{"id": p["id"], "name": p["name"], "sl": sl(p["sl"])} for p in lab["our"]]
theirs = [{"id": p["id"], "name": p["name"], "sl": sl(p["sl"])} for p in lab["opp"]]
value = {}
for j, row in enumerate(conf):
    for i, text in enumerate(row):
        level = text.split(" — ")[0].strip()
        value[(ours[i]["id"], theirs[j]["id"])] = {"level": level, "points": LEVEL_POINTS[level], "text": text}
top = max(range(len(theirs)), key=lambda j: (theirs[j]["sl"] or 0, -j))
night = _Night(ours, theirs, value, 5, a.cap, 0, a.cap, 0)
om, tm = night.full_ours, night.full_theirs
print(f"They put up {theirs[top]['name']} (SL{theirs[top]['sl']}); every legal answer:")
rows = sorted(((night.pair(k, top) + night.solve(om & ~(1 << k), tm & ~(1 << top), True)), -k, k) for k in night.legal_ours(om))[::-1]
for total, _, k in rows:
    v = value[(ours[k]["id"], theirs[top]["id"])]
    print(f"  {ours[k]['name']:24s} SL{ours[k]['sl']}  now {v['points']:+d} ({v['level']})  total {total:+d}  | {v['text']}")
for u in (0, -1, -2, -3):
    v2 = {k: dict(x, points=(u if x["level"] == "Unknown" else x["points"])) for k, x in value.items()}
    n2 = _Night(ours, theirs, v2, 5, a.cap, 0, a.cap, 0)
    i, t = n2.best_answer(n2.full_ours, n2.full_theirs, top)
    print(f"Unknown scored {u:+d}: answer {ours[i]['name']} (total {t:+d})")
