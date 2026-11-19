"""League-wide APA catch-up: fetch every scoresheet the local data is missing.

Read-only against APA and against every local database. Raw APA responses are
saved under tmp/ultimate-coach-release/league-catchup/ in the main checkout
(git-ignored), so APA data never enters git. The access token is never printed
or saved; a temporary copy of the saved APA browser session is used and then
deleted.

What one run collects:
  1. Every division in each league the logged-in account plays in (current
     session), plus every division already saved by earlier runs.
  2. Each division's full schedule.
  3. The scoresheet of every scored match played on or before today.
  4. Scoresheets the archive database is missing (completed matches with no
     game results, and past-dated matches never marked played).
  5. Division rosters, used to map scoresheet player ids to APA member ids.

Resumable and incremental: a scoresheet already saved and finalized is never
fetched again. Unfinished ones are re-checked on the next run.

Usage:  python tools/league_catchup.py [--dry-run] [--archive PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import shutil
import sqlite3
import sys
import time
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import tools.run_ultimate_coach_browser as rb  # noqa: E402
from scraper import graphql_scraper as api  # noqa: E402


def main_checkout() -> Path:
    """The main checkout, even when this file runs from a .worktrees/ copy."""
    for parent in [REPO, *REPO.parents]:
        if parent.name == ".worktrees":
            return parent.parent
    return REPO


MAIN = main_checkout()
DEFAULT_OUT = MAIN / "tmp" / "ultimate-coach-release" / "league-catchup"
DEFAULT_ARCHIVE = MAIN.parent / "APA-Tracker-Ultimate-Coach-Live" / "data" / "ultimate_coach_staging.db"
SESSION_PROFILE = MAIN / ".session_cache" / "apa_chromium"
EARLIER_RUNS = [MAIN / "tmp" / "ultimate-coach-release" / "catchup-20261112"]
PAUSE = 0.3
STALE_DAYS = 21  # unfinalized scoresheets older than this are not re-checked


def log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S} {msg}")


class Apa:
    """Token handling with automatic re-capture when APA expires it."""

    def __init__(self, scratch: Path):
        self.copy = scratch / "profile-copy"
        self.cfg = None

    def login(self) -> None:
        if not SESSION_PROFILE.exists():
            raise SystemExit("NO SAVED APA SESSION: run FULL_APA_REFRESH.bat once and log in, then retry.")
        shutil.rmtree(self.copy, ignore_errors=True)
        shutil.copytree(SESSION_PROFILE, self.copy, ignore=shutil.ignore_patterns("Singleton*", "*.lock", "lockfile"))
        rb.SESSION_PROFILE_DIR = self.copy
        token = rb.capture_access_token_persistent()
        if not token:
            raise SystemExit("NOT LOGGED IN: the saved APA session expired. Run FULL_APA_REFRESH.bat, log in, then retry.")
        self.cfg = {"apa": {"access_token": token}, "session": {"timeout_seconds": 25, "max_retries": 2}}
        log("logged in to APA (token not shown)")

    def call(self, fn, *args):
        for attempt in range(3):
            try:
                result = fn(self.cfg, *args)
                time.sleep(PAUSE)
                return result
            except (api.AccessTokenExpired, api.AccessTokenMissing):
                log("APA token expired; logging in again")
                self.login()
            except Exception as exc:  # report and retry; one bad match must not stop the run
                log(f"error {fn.__name__}{args} attempt {attempt + 1}: {type(exc).__name__}: {str(exc)[:150]}")
                time.sleep(3 * (attempt + 1))
        return None

    def close(self) -> None:
        self.cfg = None
        shutil.rmtree(self.copy, ignore_errors=True)


def archive_gaps(archive: Path, today: str) -> tuple[dict[str, str], set[str]]:
    """Matches the archive holds no game results for, and the ones it already has."""
    if not archive.exists():
        log(f"archive not found, skipping gap check: {archive}")
        return {}, set()
    db = sqlite3.connect(f"file:{archive}?mode=ro", uri=True)
    with_games = {r[0] for r in db.execute("select distinct match_id from player_head_to_head")}
    gaps, have = {}, set()
    for mid, ext, when, status, bye, scored in db.execute(
            "select id, external_id, match_date, status, is_bye, is_scored from matches where external_id is not null"):
        if mid in with_games:
            have.add(str(ext))
            continue
        if bye or not when or str(when)[:10] > today:
            continue
        done = scored or str(status or "").upper() == "COMPLETED"
        gaps[str(ext)] = "missing_scoresheet" if done else "past_unplayed"
    db.close()
    return gaps, have


def saved_match(mid: str, out: Path):
    """Latest saved copy of a scoresheet, from this store or an earlier run."""
    for folder in [out / "matches", *(r / "matches" for r in EARLIER_RUNS)]:
        f = folder / f"{mid}.json"
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8")).get("match")
            except (OSError, ValueError):
                return None
    return None


def is_final(match, today: str) -> bool:
    """Saved and settled: finalized, a bye, or old enough that APA will not change it."""
    if not match:
        return False
    if match.get("isFinalized") or match.get("isBye"):
        return True
    played = str(match.get("startTime") or "")[:10]
    return bool(played) and (date.fromisoformat(today) - date.fromisoformat(played)).days > STALE_DAYS


def alias_map(out: Path) -> dict[str, str]:
    """Scoresheet player id (roster alias) -> APA member id, from every saved roster."""
    mapping = {}
    folders = [out / "rosters", *(r / "rosters" for r in EARLIER_RUNS)]
    for folder in folders:
        for f in glob.glob(str(folder / "*.json")):
            div = json.loads(Path(f).read_text(encoding="utf-8"))
            for team in div.get("teams") or []:
                for p in (team or {}).get("roster") or []:
                    alias, member = str((p or {}).get("id") or ""), str(((p or {}).get("member") or {}).get("id") or "")
                    if alias and member:
                        mapping[alias] = member
    return mapping


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="list what would be fetched, fetch no scoresheets")
    ap.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    out, today = args.out, date.today().isoformat()
    for sub in ("divisions", "matches", "rosters", "runs"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    log(f"saving to {out}")

    apa = Apa(out)
    summary = {"started": datetime.now().isoformat(timespec="seconds"), "dry_run": args.dry_run}
    try:
        apa.login()

        # 1. divisions: every league the account plays in, plus earlier runs
        divisions = set()
        for folder in [out / "divisions", *(r / "divisions" for r in EARLIER_RUNS)]:
            divisions |= {Path(f).stem for f in glob.glob(str(folder / "*.json"))}
        viewer = apa.call(api.fetch_dashboard_teams) or {}
        slugs = sorted({r["league_slug"] for r in api.dashboard_teams_rows(viewer)
                        if r["league_slug"] and not r["is_tournament"]})
        for slug in slugs:
            league = apa.call(api.fetch_league_divisions, slug) or {}
            divisions |= {r["division_id"] for r in api.league_division_rows(league)}
        log(f"leagues: {len(slugs)} | divisions to check: {len(divisions)}")
        if not divisions:
            raise SystemExit("APA returned no divisions; nothing to do.")

        # 2. schedules (always refreshed: they change every week)
        targets: dict[str, str] = {}
        for n, did in enumerate(sorted(divisions), 1):
            sched = apa.call(api.fetch_division_schedule, did)
            if sched is None:
                log(f"division {did}: schedule unavailable")
                continue
            (out / "divisions" / f"{did}.json").write_text(json.dumps(sched, ensure_ascii=False), encoding="utf-8")
            rows = api.division_schedule_rows(sched)
            played = [r for r in rows if r["is_scored"] and not r["is_bye"] and str(r["date"] or "")[:10] <= today]
            for r in played:
                targets[r["match_id"]] = "division_schedule"
            if n % 10 == 0 or n == len(divisions):
                log(f"schedules {n}/{len(divisions)}")

        # 3. archive gaps; matches the archive already holds games for are not refetched
        gaps, have = archive_gaps(args.archive, today)
        targets = {m: t for m, t in targets.items() if m not in have}
        for mid, tag in gaps.items():
            targets.setdefault(mid, tag)

        # 4. skip anything already saved and settled
        todo = {m: t for m, t in targets.items() if not is_final(saved_match(m, out), today)}
        by_tag = {t: sum(1 for v in todo.values() if v == t) for t in sorted(set(targets.values()))}
        log(f"scoresheets known: {len(targets)} | already saved: {len(targets) - len(todo)} | to fetch: {len(todo)} {by_tag}")
        summary.update(divisions=len(divisions), leagues=len(slugs), scoresheets_known=len(targets),
                       already_saved=len(targets) - len(todo), to_fetch=len(todo), to_fetch_by_source=by_tag,
                       archive_gaps=len(gaps))

        fetched = failed = empty = games = 0
        if not args.dry_run:
            for n, (mid, tag) in enumerate(todo.items(), 1):
                m = apa.call(api.fetch_match_detail, mid)
                if m is None:
                    failed += 1
                    continue
                (out / "matches" / f"{mid}.json").write_text(json.dumps({"tag": tag, "match": m}, ensure_ascii=False),
                                                            encoding="utf-8")
                fetched += 1
                if not m:
                    empty += 1
                else:
                    games += sum(1 for r in api.head_to_head_rows(m) if r["result"] in ("W", "L")) // 2
                if n % 50 == 0 or n == len(todo):
                    log(f"scoresheets {n}/{len(todo)} (saved {fetched}, failed {failed})")

            # 5. rosters for player identity
            for n, did in enumerate(sorted(divisions), 1):
                ros = apa.call(api.fetch_division_rosters, did)
                if ros is not None:
                    (out / "rosters" / f"{did}.json").write_text(json.dumps(ros, ensure_ascii=False), encoding="utf-8")
            mapping = alias_map(out)
            (out / "roster_alias_to_member.json").write_text(json.dumps(mapping, indent=0), encoding="utf-8")
            summary["roster_alias_mappings"] = len(mapping)

        summary.update(fetched=fetched, failed=failed, no_such_match=empty, new_games=games,
                       finished=datetime.now().isoformat(timespec="seconds"))
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        (out / "runs" / f"{stamp}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        (out / "LAST_RUN.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        with open(out / "runs" / f"{stamp}-targets.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["match_id", "source", "fetched_this_run"])
            for mid, tag in sorted(targets.items()):
                w.writerow([mid, tag, mid in todo and not args.dry_run])
        log("DONE " + ("(dry run, nothing fetched) " if args.dry_run else "")
            + f"fetched={fetched} failed={failed} new games={games}")
        return 1 if failed else 0
    finally:
        apa.close()
        log(f"temporary session copy deleted: {not apa.copy.exists()}")


if __name__ == "__main__":
    raise SystemExit(main())
