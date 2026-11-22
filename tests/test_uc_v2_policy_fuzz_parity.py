"""Independent review of PR #121 (Claude): randomized browser-vs-Python policy parity.

Seeded and deterministic. Random roster sizes, skill levels (including unknown), caps, prior spend on both sides,
games left, and realistic probabilities with near-ties (recorded form, recent form, direct records), in 8-Ball and
9-Ball. Each state compares the full stable-ID decision trace of the real browser policy with analytics.uc_v2_policy.
"""
import random

from playwright.sync_api import sync_playwright

from analytics.uc_v2_pair_model import win_probability
from analytics.uc_v2_policy import V2Policy
from tests.test_uc_v2_candidate import _render
from tests.test_uc_v2_policy_parity import PROJECT, browser_values, compare

N_STATES = 150          # per format


def _state(rng, fmt):
    n_o, n_t = rng.randint(2, 8), rng.randint(2, 8)
    sls = [None, 2, 3, 3, 4, 4, 5, 5, 6, 7] if fmt == "EIGHT" else [None, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    ours = [{"id": f"o{k}", "name": f"O{k}", "sl": rng.choice(sls)} for k in range(n_o)]
    theirs = [{"id": f"t{k}", "name": f"T{k}", "sl": rng.choice(sls)} for k in range(n_t)]
    games = rng.randint(1, min(5, n_o, n_t))
    cap = rng.choice([None, 19, 22, 23, 23, 23, 25])
    used = rng.choice([0, 0, 3, 7, 11]) if games < 5 else 0
    opp_used = rng.choice([0, 0, 4, 9]) if games < 5 else 0
    form = {p["id"]: (rng.randint(0, 60), rng.randint(0, 120)) for p in ours + theirs}
    form = {k: (min(w, g), g) for k, (w, g) in form.items()}
    p = {}
    for o in ours:
        for t in theirs:
            direct = None
            if rng.random() < 0.3:
                g = rng.randint(1, 4); direct = (rng.randint(0, g), g)
            if o["sl"] is None or t["sl"] is None:
                # unknown skill: the model's average skill-pair effect is applied inside win_probability
                pass
            p[(o["id"], t["id"])] = win_probability(fmt, o["sl"], t["sl"], direct=direct,
                                                     form_p=form[o["id"]], form_o=form[t["id"]],
                                                     recent_p=(min(form[o["id"]][0], 5), min(form[o["id"]][1], 10)),
                                                     recent_o=(min(form[t["id"]][0], 5), min(form[t["id"]][1], 10)))
    # force some exact and near ties (the hardest cases for tie-breaks)
    keys = list(p)
    for _ in range(rng.randint(0, 3)):
        a, b = rng.sample(keys, 2)
        p[b] = p[a] + rng.choice([0.0, 0.0, 1e-13, 0.004, 0.0099])
        p[b] = min(max(p[b], 0.0), 1.0)
    return ours, theirs, p, games, cap, used, opp_used


def test_randomized_browser_policy_matches_python(tmp_path):
    rng = random.Random(20261122)
    checked = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(_render(tmp_path).as_uri())
            for fmt in ("EIGHT", "NINE"):
                for _ in range(N_STATES):
                    ours, theirs, p, games, cap, used, opp_used = _state(rng, fmt)
                    try:
                        expected = V2Policy(ours, theirs, p, games, cap, used, opp_used).trace()
                    except ValueError:
                        continue          # invalid state for the reference (e.g. no legal response) - not compared
                    actual = page.evaluate(PROJECT, [ours, theirs, browser_values(p), games, cap, used, opp_used])
                    for k in ("policy", "opponent_cap_relaxed", "cap_incomplete", "opponent_cap_incomplete"):
                        expected.pop(k)
                    compare(expected, actual)
                    checked += 1
        finally:
            browser.close()
    assert checked >= 250, f"only {checked} states compared"
