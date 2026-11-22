"""Build ONE Ultimate Coach release candidate from ONE verified database snapshot: HTML (broadcast UI, V2 engine),
workbook (.xlsx) and live V2 workbook (.xlsm), all from the same payload, each validated, with a manifest of hashes.

    python scripts/build_ultimate_coach_release.py --db <verified archive db> --out <new folder> [--config apa_config.yaml]

The source database is only read (a consistent SQLite snapshot is taken and its hash checked before and after); the
output folder must not exist (never overwrites). No APA login, no network. Same payload builder, renderer, workbook
exporter and validators as the refresh (pipeline/ultimate_coach_refresh.py).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=ROOT / "apa_config.yaml")
    a = ap.parse_args(argv)
    from analytics.uc_v2_inputs import load_compact_from_html
    from analytics.uc_v2_policy import POLICY_VERSION
    from analytics.ultimate_coach_match_day import load_match_day_settings
    from pipeline.refresh_workbook import recalculate_and_validate, validate_html
    from pipeline.ultimate_coach_refresh import build_payload, check_database
    from scripts.build_ultimate_coach_production import _snapshot_sqlite
    from ui.excel_v2_coach import install
    from ui.export_excel_ultimate_coach import write_workbook
    from ui.ultimate_coach import render

    out = a.out.resolve()
    if out.exists():
        raise SystemExit(f"refused: {out} exists (never overwritten)")
    out.mkdir(parents=True)
    log = []
    def step(msg):
        line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        log.append(line)
    t0 = time.time()
    settings = load_match_day_settings(a.config.resolve())
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        snap = Path(tmp) / "snapshot.db"
        step(f"SNAPSHOT {a.db}")
        src_sha, snap_sha = _snapshot_sqlite(a.db.resolve(), snap)
        check_database(snap)
        step(f"SNAPSHOT OK source {src_sha} snapshot {snap_sha} (integrity + foreign keys ok)")
        payload = build_payload(snap, settings)
        step(f"PAYLOAD players {payload['counts'].get('players')} head-to-head {payload['counts'].get('head_to_head_rows')}")
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    xlsx, html, xlsm = out / "Ultimate_Coach.xlsx", out / "Ultimate_Coach.html", out / "Ultimate_Coach_V2.xlsm"
    write_workbook(payload, xlsx, built_at=built_at, source_db=a.db.name,
                   viewer_member_external_id=settings.viewer_member_external_id, viewer_card_number=settings.viewer_card_number)
    step("WORKBOOK written; native Excel recalculation and validation")
    v_xlsx = recalculate_and_validate(xlsx)
    step(f"WORKBOOK VALID {json.dumps(v_xlsx)[:200]}")
    html.write_text(render(payload, built_at=built_at, consume_evidence=False, ui="broadcast", engine="v2",
                           viewer_member_external_id=settings.viewer_member_external_id,
                           viewer_card_number=settings.viewer_card_number), encoding="utf-8")
    step("HTML written; Chromium validation")
    v_html = validate_html(html)
    step(f"HTML VALID {json.dumps(v_html)[:200]}")
    info = install(xlsx, load_compact_from_html(html), xlsm, meta={"data_snapshot": snap_sha, "code_commit": commit})
    trace = json.loads(info.pop("trace") or "{}")
    step(f"V2 WORKBOOK built; default-state engine status {trace.get('status')!r}")
    manifest = {
        "schema": "ultimate-coach-release-v1", "built_at_utc": built_at, "code_commit": commit,
        "code_tree_clean": not dirty, "source_database": str(a.db), "source_database_sha256": src_sha,
        "snapshot_sha256": snap_sha, "source_database_promoted": False, "policy": POLICY_VERSION,
        "model_sha256": info["model_sha256"], "engine_sha256": info["engine_sha256"],
        "v2_inputs_sha256": info["v2_inputs_sha256"], "counts": payload.get("counts"),
        "artifacts": {p.name: sha256(p) for p in (html, xlsx, xlsm)},
        "validation": {"Ultimate_Coach.xlsx": v_xlsx, "Ultimate_Coach.html": v_html,
                       "Ultimate_Coach_V2.xlsm": {"default_state": trace.get("status"), "roster_rows": info["roster_rows"],
                                                  "pair_rows": info["pair_rows"]}},
        "build_seconds": round(time.time() - t0, 1), "log": log,
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    step(f"DONE {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
