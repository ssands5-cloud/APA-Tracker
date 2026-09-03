"""
full_apa_scrape.py

Local Playwright scraper for the APA Tracker project. Run this on YOUR
machine, in YOUR terminal. It opens a real, visible Chromium window, asks
YOU (locally) for your APA username and password, logs in, then writes a
SANITIZED fixture (field names and value TYPES only, no real values) for
every GraphQL response the site makes while you browse -- organized under
scraper/sanitized_fixtures/<entity type>/<entity id>/<operation>.json.

Your credentials are read by getpass()/input() into local Python variables,
used once to fill the login form, and never written to disk, logged, or
sent anywhere except the real APA login page itself. Nothing in this script
uploads, emails, or otherwise transmits anything to Claude, Copilot, or any
other service.

Every line this script prints is also appended to full_apa_scrape.log next
to it, in case console output scrolls past or gets lost -- this is here
specifically because an earlier run of this script printed "MAIN BLOCK
REACHED" and then stopped with no visible error, no traceback, and no hang.
That is not explained yet. This version cannot fix a cause it cannot see
(this sandbox has no Windows machine to reproduce it on), but it removes
every place that failure could have hidden: the whole run is now wrapped in
a broad except that logs a full traceback, and nothing is printed without
also being written to the log file.
"""

print("FILE LOADED")

import asyncio
import getpass
import json
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

print("IMPORTS OK")

if sys.version_info[:2] == (3, 14):
    print()
    print("WARNING: Python 3.14 has a confirmed bug on Windows where")
    print("asyncio.run() crashes the whole process with zero output and no")
    print("traceback -- reproduced directly with scraper/diagnose_eventloop.py,")
    print("and this script needs asyncio.run() to do anything at all. If it")
    print("dies right after this message with nothing else printed, that is")
    print("almost certainly it. Use Python 3.12 or 3.13 instead: run")
    print("`py -0` to see what's installed, `winget install Python.Python.3.12`")
    print("if 3.12 isn't there, then `py -3.12 -m venv venv` to rebuild the venv.")
    print()

# --- Paths / logging ------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "sanitized_fixtures"
LOG_PATH = SCRIPT_DIR / "full_apa_scrape.log"


def log(message):
    """Prints AND appends to a log file, one line, flushed immediately."""
    print(message)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat()}  {message}\n")
    except Exception:
        pass  # logging must never be the reason the script crashes


# --- Configuration ---------------------------------------------------------

BASE_URL = "https://league.poolplayers.com"
LOGIN_PATH = "/login"
GRAPHQL_HOST = "gql.poolplayers.com"

USERNAME_SELECTORS = (
    "input[name='username'], input[name='email'], input[type='email'], "
    "input[autocomplete='username'], input#username, input#email"
)
PASSWORD_SELECTORS = "input[type='password'], input[name='password'], input#password"
SUBMIT_SELECTORS = (
    "button[type='submit'], button:has-text('Log In'), "
    "button:has-text('Login'), button:has-text('Sign In')"
)

# --- Entity classification --------------------------------------------------
# Built from the real operations confirmed in
# docs/graphql-captures/2026-09-03-shapes.json and parser/apa_graphql.py --
# not guessed. The SAME variable name "id" identifies a different kind of
# thing depending on the operation (divisionsDropdown's $id is a LEAGUE id,
# for example), which is why this is a lookup table keyed on operation name,
# not a rule based on the variable name alone.
#
# No standalone player-scoped operation has been confirmed to exist -- every
# known operation returns player data embedded inside a team's or division's
# roster, never a "give me one player" query on its own. sanitized_fixtures/
# will not have a populated player/ directory until one is found; if you see
# a new operation name while browsing a player's own page, that is the one
# to send back so it can be added here.
OPERATION_ENTITY = {
    "teamPage": "team",
    "teamRoster": "team",
    "teamSchedule": "team",
    "divisionLayout": "division",
    "DivisionContacts": "division",
    "divsionStandings": "division",  # sic -- misspelled on the real API
    "divisionRosters": "division",
    "divisionSchedule": "division",
    "divisionMVP": "division",
    "MatchPage": "match",
}


def classify(operation_name, variables):
    """(entity_type, entity_id) for one captured operation.

    Anything not in OPERATION_ENTITY -- leagueLayout, LeagueInfo,
    sessionsDropdown, leagueDivisions, divisionsDropdown,
    GenerateAccessTokenMutation, TournamentBannerQuery, DivisionContent, and
    any operation not seen before -- is bucketed as "global", not because it
    is unimportant but because its "id" variable (when it has one at all)
    does not identify a division/team/match the way the table above's do.
    """
    entity_type = OPERATION_ENTITY.get(operation_name, "global")
    if entity_type == "global":
        return "global", "global"
    entity_id = (variables or {}).get("id")
    return entity_type, (str(entity_id) if entity_id is not None else "unknown")


# --- Sanitization -----------------------------------------------------------
# Every value becomes its TYPE, so what lands on disk is a schema, never
# data. Same logic as tools/apa-console-capture.js and
# tools/capture_apa_graphql.py's summarize_shape.

ENUM_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")


def summarize_shape(value):
    if isinstance(value, bool):
        return "bool"  # checked first: bool is a subclass of int in Python
    if value is None:
        return "null"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return value if ENUM_RE.match(value) else "str"
    if isinstance(value, dict):
        return {key: summarize_shape(item) for key, item in value.items()}
    if isinstance(value, list):
        if not value:
            return []
        return [summarize_shape(value[0]), "...%d item(s)" % len(value)]
    return type(value).__name__


def _count_from_shape(shape, path):
    """Reads a list's length back out of a sanitized shape, if present.

    summarize_shape() replaces list ITEMS with their type but keeps the
    length as an explicit "...N item(s)" marker (see above) -- this reads
    that marker back out. Returns None when the path doesn't lead to a list
    at all (a different shape, or the field was absent/null).
    """
    node = shape
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    if isinstance(node, list) and len(node) == 0:
        return 0
    if isinstance(node, list) and len(node) == 2 and isinstance(node[1], str):
        m = re.match(r"\.\.\.(\d+) item\(s\)", node[1])
        if m:
            return int(m.group(1))
    return None


def write_sanitized_fixture(operation_name, variables, query, response_json):
    entity_type, entity_id = classify(operation_name, variables)
    directory = OUTPUT_DIR / entity_type / entity_id
    directory.mkdir(parents=True, exist_ok=True)

    payload = {
        "operationName": operation_name,
        "entityType": entity_type,
        "entityId": entity_id,
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "variables": summarize_shape(variables),
        "query": query,  # the query document itself: schema text, not data
        "response": summarize_shape(response_json),
    }
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", operation_name)
    path = directory / (safe_name + ".json")
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path, entity_type, entity_id


#: Heartbeat counters, so a run where nothing gets captured can say WHY:
#: the listener never seeing traffic (a real bug) looks completely
#: different from it seeing plenty of traffic that just isn't GraphQL, or
#: GraphQL calls with no post_data (neither of which is a bug in this
#: script -- the second is what Apollo's client-side cache produces: a
#: page whose data was already fetched earlier in the session can render
#: with NO new network request at all).
_SEEN = {"total": 0, "graphql_host": 0, "no_post_data": 0, "captured": 0}


async def handle_graphql_response(response):
    """Reads one GraphQL response and writes a sanitized fixture for it.

    Registered on the "response" EVENT (context.on("response", ...)), not a
    page.route() interceptor: route() exists to modify or block a request
    before it completes, which is not the goal here. This only needs to
    OBSERVE traffic that already happened, with zero risk of altering what
    the real site sees or receives.

    Playwright's Python bindings run on pyee's AsyncIOEventEmitter, which
    schedules an async handler passed to .on() as a task automatically --
    confirmed by reading pyee's own emit() implementation, not assumed.

    Wrapped in try/except per its own body: an exception raised inside an
    event handler here must be logged, not left to vanish into an
    unobserved task -- that is exactly the shape of failure that would look
    like "some operations just never got captured, no error, no reason."
    """
    try:
        _SEEN["total"] += 1
        if _SEEN["total"] % 20 == 0:
            log(f"... heartbeat: {_SEEN['total']} response(s) seen total, "
                f"{_SEEN['graphql_host']} to gql.poolplayers.com, "
                f"{_SEEN['captured']} captured so far")

        if GRAPHQL_HOST not in response.url:
            return
        _SEEN["graphql_host"] += 1

        request = response.request
        post_data = request.post_data_json  # a property, not a coroutine
        if not post_data:
            _SEEN["no_post_data"] += 1
            log(f"GRAPHQL RESPONSE WITH NO REQUEST BODY (not capturable): {response.url}")
            return

        try:
            body = await response.json()
        except Exception:
            return  # not a JSON response -- nothing to capture

        items = post_data if isinstance(post_data, list) else [post_data]
        responses = body if isinstance(body, list) else [body]

        for index, item in enumerate(items):
            operation_name = (item or {}).get("operationName")
            if not operation_name:
                continue
            if index < len(responses):
                resp_item = responses[index]
            elif responses:
                resp_item = responses[0]
            else:
                resp_item = None

            path, entity_type, entity_id = write_sanitized_fixture(
                operation_name, item.get("variables"), item.get("query"), resp_item
            )
            _SEEN["captured"] += 1
            log(f"CAPTURED: {operation_name}  entity={entity_type}/{entity_id}  -> {path.relative_to(SCRIPT_DIR)}")

            if entity_type == "team":
                log(f"CAPTURED TEAM {entity_id}")
    except Exception:
        log("EXCEPTION IN GRAPHQL RESPONSE HANDLER:")
        log(traceback.format_exc())


def validate_fixtures():
    """Reads back every fixture just written and checks it, for real.

    This checks internal consistency (valid JSON, required keys present,
    the id recorded inside a file matches the folder it was filed under) --
    everything this script can actually verify without a live connection to
    the site. It CANNOT confirm the counts below match what the APA site
    itself currently shows: that comparison needs a human looking at both
    side by side, and is marked BLOCKED below rather than assumed.
    """
    log("")
    log("=== POST-SCRAPE VALIDATION ===")
    if not OUTPUT_DIR.exists():
        log("FAIL: sanitized_fixtures/ does not exist -- nothing was captured.")
        return

    all_files = sorted(OUTPUT_DIR.rglob("*.json"))
    log(f"Found {len(all_files)} fixture file(s) under {OUTPUT_DIR.relative_to(SCRIPT_DIR)}")

    divisions, teams, matches, global_ops = {}, {}, {}, set()
    broken = []

    for path in all_files:
        rel = path.relative_to(OUTPUT_DIR)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            broken.append((str(rel), f"invalid JSON: {exc}"))
            continue

        for required_key in ("operationName", "variables", "query", "response"):
            if required_key not in payload:
                broken.append((str(rel), f"missing key: {required_key}"))

        entity_type = payload.get("entityType")
        entity_id = payload.get("entityId")

        # Internal consistency only: does the folder this file lives in
        # match the entity type/id recorded INSIDE the file? This cannot
        # catch a wrong id (that needs the live site); it catches this
        # script's own bookkeeping being wrong.
        parts = rel.parts
        if len(parts) >= 2:
            folder_type, folder_id = parts[0], parts[1]
            if entity_type != folder_type or str(entity_id) != folder_id:
                broken.append(
                    (str(rel), f"folder says {folder_type}/{folder_id} but file says {entity_type}/{entity_id}")
                )

        op = payload.get("operationName")
        response = payload.get("response") or {}

        if entity_type == "division":
            divisions.setdefault(entity_id, set()).add(op)
            n = _count_from_shape(response, ("data", "division", "teams"))
            if n is not None:
                log(f"FOUND {n} TEAMS in division {entity_id} (from {op})")
        elif entity_type == "team":
            teams.setdefault(entity_id, set()).add(op)
            n = _count_from_shape(response, ("data", "team", "roster"))
            if n is not None:
                log(f"FOUND {n} ROSTER ENTRIES for team {entity_id} (from {op})")
        elif entity_type == "match":
            matches.setdefault(entity_id, set()).add(op)
        else:
            global_ops.add(op)

    log("")
    log(
        f"SUMMARY: {len(divisions)} division(s), {len(teams)} team(s), "
        f"{len(matches)} match(es), {len(global_ops)} global operation(s) captured"
    )
    for division_id, ops in sorted(divisions.items()):
        log(f"  division {division_id}: {sorted(ops)}")
    for team_id, ops in sorted(teams.items()):
        log(f"  team {team_id}: {sorted(ops)}")
    for match_id, ops in sorted(matches.items()):
        log(f"  match {match_id}: {sorted(ops)}")
    if global_ops:
        log(f"  global: {sorted(global_ops)}")

    log("")
    if broken:
        log(f"FAIL: {len(broken)} fixture file(s) have a problem:")
        for rel, reason in broken:
            log(f"  {rel}: {reason}")
    else:
        log("PASS: every fixture file is valid JSON, has the required keys, "
            "and its folder matches its own recorded entity type/id.")

    log("")
    log("BLOCKED (this script cannot check this): whether the counts above")
    log("match what the live APA site currently shows. This script only")
    log("knows what it captured -- confirming it against the site itself")
    log("needs a human comparing the two side by side.")


async def main():
    log("MAIN STARTED")

    username = input("APA username: ")
    password = getpass.getpass("APA password: ")

    log("LAUNCHING BROWSER")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        log("BROWSER LAUNCHED")

        context = await browser.new_context()
        log("CONTEXT CREATED")

        # Attached to the CONTEXT, not one page: login can redirect through
        # a second domain (accounts.poolplayers.com) and land in a new tab,
        # which a page-level listener would silently miss.
        context.on("response", handle_graphql_response)
        log("GRAPHQL CAPTURE READY")

        page = await context.new_page()
        log("PAGE CREATED")

        log("NAVIGATING TO LOGIN PAGE")
        await page.goto(BASE_URL + LOGIN_PATH)
        await page.wait_for_load_state("networkidle")

        log("FILLING LOGIN FORM")
        try:
            await page.locator(USERNAME_SELECTORS).first.fill(username, timeout=8000)
            await page.locator(PASSWORD_SELECTORS).first.fill(password, timeout=8000)
        except Exception:
            log("COULD NOT FIND LOGIN FIELDS AUTOMATICALLY:")
            log(traceback.format_exc())
            log("The real login form's field names are unverified (see")
            log("parser/apa_page_map.py) -- log in by hand in the open")
            log("browser window instead. Capture keeps working either way.")

        log("SUBMITTING LOGIN")
        try:
            await page.locator(SUBMIT_SELECTORS).first.click(timeout=8000)
        except Exception:
            log("COULD NOT FIND A SUBMIT BUTTON AUTOMATICALLY:")
            log(traceback.format_exc())
            log("Click Log In by hand in the browser window.")

        await page.wait_for_load_state("networkidle")
        log("LOGIN COMPLETE")

        # NAVIGATING TO DIVISION is logged here as an instruction TO YOU, not
        # as something this script does automatically: only the GraphQL
        # OPERATION names are confirmed (divisionLayout, divsionStandings,
        # ...), not the browser URL route that triggers them. A wrong
        # guessed URL fails in the worst way -- it loads *something* without
        # erroring, so a silently wrong page looks like success. Navigating
        # home and waiting for a human to click is what actually worked
        # before, so it stays: capturing continues in the background the
        # entire time you are clicking.
        await page.goto(BASE_URL)
        log("NAVIGATING TO DIVISION (manual step -- see instructions below)")

        print()
        print("Browser is open. Click through to your DIVISION/standings page,")
        print("your TEAM page, and a MATCH or player page. Every GraphQL")
        print("response is captured and written under scraper/sanitized_fixtures/")
        print("as you go -- watch that folder fill in, and watch this console")
        print("for CAPTURED / FOUND N TEAMS / FOUND N ROSTER ENTRIES lines.")
        print()

        # Run in a worker thread, not the main thread: a plain blocking
        # input() call would also block asyncio's event loop, which
        # Playwright needs running to keep processing the browser's
        # connection -- so a plain input() would pause capturing (delay it
        # until you press Enter; the OS still buffers the traffic, so
        # nothing is lost, but nothing would print live either).
        await asyncio.to_thread(input, "Press Enter here when you are done browsing... ")

        await browser.close()

    log(
        f"NETWORK SUMMARY: {_SEEN['total']} response(s) seen total, "
        f"{_SEEN['graphql_host']} to gql.poolplayers.com "
        f"({_SEEN['no_post_data']} with no request body, not capturable), "
        f"{_SEEN['captured']} operation(s) captured."
    )
    if _SEEN["total"] == 0:
        log("Zero responses of ANY kind were seen. The listener itself never fired --")
        log("that would point at something wrong with how it was registered, not at")
        log("which pages were visited.")
    elif _SEEN["graphql_host"] == 0:
        log("Traffic was seen, but none of it went to gql.poolplayers.com. Either the")
        log("pages visited don't use the GraphQL API, or the browser ended up on a")
        log("different host (e.g. redirected to a logged-out/marketing page).")
    elif _SEEN["captured"] == 0:
        log("GraphQL calls were seen but none had a capturable request body -- see the")
        log("'GRAPHQL RESPONSE WITH NO REQUEST BODY' lines above, if any.")

    validate_fixtures()
    log("SCRAPE COMPLETE")


if __name__ == "__main__":
    print("MAIN BLOCK REACHED")
    try:
        asyncio.run(main())
    except BaseException:
        # Catches EVERYTHING, including things that are not plain
        # Exception, and both prints and logs the full traceback -- added
        # specifically because a previous run of this script produced no
        # error output of any kind after "MAIN BLOCK REACHED". If that
        # happens again, this is where it will now be visible.
        log("UNHANDLED ERROR -- FULL TRACEBACK BELOW:")
        log(traceback.format_exc())
        log(f"Python: {sys.version}")
        log(f"Executable: {sys.executable}")
        input("An error occurred (see above and in full_apa_scrape.log). Press Enter to close... ")
        sys.exit(1)
