"""Validate the win-probability model against real recorded outcomes.

Reporter/builder for :mod:`analytics.prediction_validation`. Reads the
``player_head_to_head`` table already populated by the ingest pipeline,
runs both validation analyses described in that module's docstring, and
writes a full evaluation report to ``exports/prediction_validation.json``.

This is a standalone diagnostic, not part of the captain-facing pipeline
(``python -m pipeline``): it answers "is the model any good", which is a
question for whoever is maintaining the analytics, not something a captain
needs recomputed on every sync. Re-run it by hand after a sync to see
whether accumulating real data has changed the picture -- see
docs/prediction_validation.md.

Usage::

    python scripts/validate_predictions.py
    python -m scripts.validate_predictions
    python scripts/validate_predictions.py --bins 10 --out-dir exports
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import env_loader  # noqa: F401  -- loads .env before anything reads it

from sqlalchemy.orm import Session

from analytics.prediction_validation import (
    ScoredPrediction,
    ValidationSummary,
    format_label,
    group_summaries,
    naive_baseline,
    prior_games_label,
    score_all_pairings,
    score_skill_only,
    skill_direction_label,
    summarize,
)
from database.engine import create_db_engine
from database.models import Player
from scheduler.graphql_sync import load_config
from scripts.build_head_to_head import group_by_pairing, ordered_rows

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = PROJECT_ROOT / "exports"
JSON_NAME = "prediction_validation.json"
SCHEMA_VERSION = 1


def _player_names(db: Session) -> dict[int, str]:
    """(player.id -> display name), for turning FK ids in the report into
    something a human reading the JSON can recognise without a second
    lookup. Falls back to external_id if name is somehow blank -- never
    fabricates a name."""
    return {
        player.id: (player.name or player.external_id or str(player.id))
        for player in db.query(Player).all()
    }


def _prediction_to_dict(prediction: ScoredPrediction, names: dict[int, str]) -> dict[str, Any]:
    payload = asdict(prediction)
    payload["player_name"] = names.get(prediction.player_id, str(prediction.player_id))
    payload["opponent_name"] = names.get(prediction.opponent_id, str(prediction.opponent_id))
    return payload


def _summary_to_dict(summary: ValidationSummary) -> dict[str, Any]:
    return asdict(summary)


def build_payload(db: Session, bins: int = 5) -> dict[str, Any]:
    """Run both analyses and assemble the full JSON-serialisable report."""

    rows = ordered_rows(db)
    groups = group_by_pairing(rows)
    names = _player_names(db)

    analysis_a = score_skill_only(rows)
    analysis_b = score_all_pairings(groups)
    baseline_a = naive_baseline(analysis_a, probability=0.5)

    summary_a = summarize("Analysis A: skill-level term only (cross-sectional)", analysis_a, bins=bins)
    baseline_summary_a = summarize("Baseline: always predict 0.5", baseline_a, bins=bins)
    summary_b = summarize("Analysis B: full model, historical-record walk-forward", analysis_b, bins=bins)

    by_format_a = group_summaries(analysis_a, format_label, bins=bins)
    by_skill_direction_a = group_summaries(analysis_a, skill_direction_label, bins=bins)
    by_prior_games_b = group_summaries(analysis_b, prior_games_label, bins=bins)
    by_format_b = group_summaries(analysis_b, format_label, bins=bins)

    rematch_groups = [pair_rows for pair_rows in groups.values() if len(pair_rows) >= 2]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "methodology": (
            "See docs/prediction_validation.md. Analysis A grades the "
            "skill-level term alone against every real head-to-head row "
            "(non-circular: posted skill levels predate the match they "
            "describe). Analysis B walk-forward-grades the full model "
            "(skill + historical record) on the k-th meeting of a pairing "
            "using only its rows[:k] -- strictly earlier games -- so it "
            "can only produce output for pairs that have met at least "
            "twice."
        ),
        "data_summary": {
            "total_head_to_head_rows": len(rows),
            "total_pairings": len(groups),
            "pairings_with_a_rematch": len(rematch_groups),
        },
        "analysis_a_skill_only": {
            "overall": _summary_to_dict(summary_a),
            "baseline_always_0.5": _summary_to_dict(baseline_summary_a),
            "by_format": {k: _summary_to_dict(v) for k, v in by_format_a.items()},
            "by_skill_direction": {k: _summary_to_dict(v) for k, v in by_skill_direction_a.items()},
            "predictions": [_prediction_to_dict(p, names) for p in analysis_a],
        },
        "analysis_b_full_model_walk_forward": {
            "overall": _summary_to_dict(summary_b),
            "by_format": {k: _summary_to_dict(v) for k, v in by_format_b.items()},
            "by_prior_games": {k: _summary_to_dict(v) for k, v in by_prior_games_b.items()},
            "predictions": [_prediction_to_dict(p, names) for p in analysis_b],
            "note": (
                None if analysis_b else
                "0 pairings have met twice yet in this database, so the "
                "historical-record term has zero held-out predictions to "
                "grade. This is a real data gap, not a bug -- re-run this "
                "script after rematches accumulate."
            ),
        },
    }


def write_report_json(payload: dict[str, Any], path: Path | str) -> Path:
    """Atomically replace a prior report -- same pattern as
    scripts.build_lineups.write_lineups_json, so a crash mid-write can never
    leave a half-written report where a caller expects a complete one."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    return destination


def run(config_path: str = "apa_config.yaml", out_dir: Optional[str] = None, bins: int = 5) -> Path:
    config = load_config(config_path)
    engine = create_db_engine(config)
    with Session(engine) as db:
        payload = build_payload(db, bins=bins)

    directory = Path(out_dir) if out_dir else DEFAULT_OUT_DIR
    return write_report_json(payload, directory / JSON_NAME)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="apa_config.yaml")
    parser.add_argument("--out-dir", help=f"output directory (default: {DEFAULT_OUT_DIR})")
    parser.add_argument("--bins", type=int, default=5, help="calibration-curve bucket count")
    args = parser.parse_args()

    output = run(args.config, args.out_dir, args.bins)

    with open(output, encoding="utf-8") as handle:
        payload = json.load(handle)

    a = payload["analysis_a_skill_only"]["overall"]
    b = payload["analysis_b_full_model_walk_forward"]["overall"]
    print(f"\nWrote {output}")
    print(f"\nAnalysis A (skill-level only, n={a['n']}):")
    print(f"  Brier: {a['brier']}   Log loss: {a['log_loss']}   Accuracy: {a['accuracy']}")
    print(f"\nAnalysis B (full model, walk-forward, n={b['n']}):")
    if b["n"]:
        print(f"  Brier: {b['brier']}   Log loss: {b['log_loss']}   Accuracy: {b['accuracy']}")
    else:
        print(f"  {payload['analysis_b_full_model_walk_forward']['note']}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
