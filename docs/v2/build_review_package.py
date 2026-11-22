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
    ap.add_argument("--upstream", help="folder holding the source package's build records (history-scope.json, verification.json)")
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
    # Provenance manifest (GA-03): what this review copy is made of, with hashes, next to the HTML (kept local).
    import hashlib, json
    sha = lambda b: hashlib.sha256(b).hexdigest()
    pkg = Path(a.package).resolve()
    head = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(wt), "status", "--porcelain", "--", "ui", "analytics", "docs/v2"], capture_output=True, text=True).stdout.strip()
    upstream = {}
    for f in sorted(pkg.parent.glob("*.json")) + (sorted(Path(a.upstream).glob("*.json")) if a.upstream else []):
        try:
            upstream[f.name] = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    manifest = {
        "review_html": {"path": str(Path(a.out).resolve()), "sha256": sha(Path(a.out).read_bytes())},
        "source_package": {"path": str(pkg), "sha256": sha(pkg.read_bytes()), "embedded_data_sha256": sha(data_before.encode())},
        "code": {"commit": head, "base_rev": a.base, "uncommitted_changes_in_ui_analytics_docs_v2": bool(dirty)},
        "model": {"path": "analytics/uc_v2_model.json", "sha256": sha((wt / "analytics" / "uc_v2_model.json").read_bytes())},
        "label": a.label, "built": a.built,
        "data_provenance_note": ("embedded data copied byte-for-byte from the source package; its upstream build records "
                                 "(base refresh run, catch-up counts, verification) are listed below when present"),
        "upstream_folder": str(Path(a.upstream).resolve()) if a.upstream else None,
        "upstream_records_in_source_folder": {k: v for k, v in upstream.items() if k in ("history-scope.json", "verification.json", "workbook-reuse-provenance.json")},
    }
    Path(str(a.out) + ".manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"applied {blocks} code blocks; data block unchanged -> {a.out} (+ manifest)")


if __name__ == "__main__":
    main()
