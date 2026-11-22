"""Build an OWNER REVIEW copy of a real-data Ultimate Coach package with this branch's front-end code (review only).

The real-data package's evidence comes from a build source that is not reproducible on disk (finding D1), so this
tool does not rebuild data. It renders the synthetic test payload twice -- with <base_rev> (the commit the package
was built from) and with this worktree (engine="v2") -- takes every changed block of page code and replaces it in
the package. Every block must match exactly once; same-shaped lines that also carry data are patched in place.
The embedded data block is never touched, and the source package is never modified.

    python docs/v2/build_review_package.py --worktree <path> --base <rev> --package <real html> --out <review html> \
        --label "<build label>" --built "<local time text>"

Then verify: embedded data identical to the package, M3-mode answers identical, engine badge V2 (see README).
"""
import argparse
import difflib
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

CODE = ('import sys; sys.path.insert(0, sys.argv[1])\n'
        'from tests.test_excel_war_room_formulas import _payload\n'
        'from ui.ultimate_coach import render\n'
        'kw = {"engine": "v2"} if sys.argv[3] == "v2" else {}\n'
        'open(sys.argv[2],"w",encoding="utf-8").write(render(_payload(), built_at="2026-11-11 12:00 UTC", '
        'viewer_member_external_id="1001", ui="broadcast", **kw))\n')
OLD_FOOT = ("This page shows recorded APA facts and derived comparisons only. No matchup probability is displayed until a "
            "separately back-tested calibration gate passes.")
NEW_FOOT = ("V2 CANDIDATE build: shows back-tested win-chance estimates from the V2 pairing model next to the M3 baseline; "
            "estimates, not guarantees.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worktree", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--package", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--built", required=True)
    a = ap.parse_args()
    wt = Path(a.worktree).resolve()
    env = dict(os.environ, UC_BUILD_LABEL=a.label)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        arc = subprocess.run(["git", "-C", str(wt), "archive", a.base], capture_output=True, check=True).stdout
        tarfile.open(fileobj=io.BytesIO(arc)).extractall(tmp / "base", filter="data")
        subprocess.run([sys.executable, "-c", CODE, str(tmp / "base"), str(tmp / "old.html"), "m3"], check=True, cwd=tmp / "base", env=env)
        subprocess.run([sys.executable, "-c", CODE, str(wt), str(tmp / "new.html"), "v2"], check=True, cwd=wt, env=env)
        old = (tmp / "old.html").read_text(encoding="utf-8").splitlines(keepends=True)
        new = (tmp / "new.html").read_text(encoding="utf-8").splitlines(keepends=True)
    html = Path(a.package).read_text(encoding="utf-8")
    data_before = re.search(r'<script id="uc-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    blocks = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        a0, a1 = max(0, i1 - 1), min(len(old), i2 + 1)
        b0, b1 = max(0, j1 - 1), min(len(new), j2 + 1)
        before, after = "".join(old[a0:a1]), "".join(new[b0:b1])
        if "Version:" in before and "Build date" in before:
            continue
        if OLD_FOOT in before:
            assert html.count(OLD_FOOT) == 1
            html = html.replace(OLD_FOOT, NEW_FOOT)
            blocks += 1
            continue
        if html.count(before) == 1:
            html = html.replace(before, after)
            blocks += 1
            continue
        if tag != "replace" or (i2 - i1) != (j2 - j1):
            sys.exit(f"block {blocks} found {html.count(before)} times: {before[:160]!r}")
        for lo, ln in zip(old[i1:i2], new[j1:j2]):
            for t2, x1, x2, y1, y2 in reversed(difflib.SequenceMatcher(None, lo, ln, autojunk=False).get_opcodes()):
                if t2 == "equal":
                    continue
                ctx_a = lo[max(0, x1 - 40):min(len(lo), x2 + 40)]
                ctx_b = lo[max(0, x1 - 40):x1] + ln[y1:y2] + lo[x2:min(len(lo), x2 + 40)]
                if html.count(ctx_a) != 1:
                    sys.exit(f"in-line patch found {html.count(ctx_a)} times: {ctx_a[:120]!r}")
                html = html.replace(ctx_a, ctx_b)
        blocks += 1
    html, n = re.subn(r'UC_BUILD_INFO=\{"version":"([^"]*)","built":"[^"]*"\}',
                      lambda m: 'UC_BUILD_INFO={"version":"%s","built":"built %s"}' % (m.group(1), a.built), html)
    assert n == 1, "build info not found"
    html, n = re.subn(r"<title>", "<title>OWNER REVIEW ONLY - V2 CANDIDATE - ", html, count=1)
    m = re.search(r"<body[^>]*>", html)
    html = (html[:m.end()] + '<div id="owner-review-banner" style="background:#8f251b;color:#fff;font:700 13px/1.4 system-ui,sans-serif;'
            'padding:8px 16px;text-align:center">OWNER REVIEW ONLY · not for league-night use · always opens on the V2 engine '
            '(see the green ENGINE bar)</div>' + html[m.end():])
    data_after = re.search(r'<script id="uc-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    assert data_before == data_after, "embedded data changed"
    Path(a.out).write_text(html, encoding="utf-8")
    print(f"applied {blocks} code blocks; data block unchanged -> {a.out}")


if __name__ == "__main__":
    main()
