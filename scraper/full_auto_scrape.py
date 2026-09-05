import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import env_loader  # noqa: F401,E402  -- loads .env before anything else

"""Canonical APA league scraper: one run, one full league snapshot.

Contract -- login flow, consent guard, fixture layout, and the operations
expected in each bucket -- is documented in README-scraper.md at the repo
root. Two traps worth knowing before editing:

  * Downstream code must derive ids from the PAYLOAD, never from the
    directory name (see the TeamStat/alias note in that README).
  * Two fixture schemas exist on disk; read `payload.get("response", payload)`.
"""

import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
load_dotenv()

APA_USERNAME = os.environ.get("APA_USERNAME")
APA_PASSWORD = os.environ.get("APA_PASSWORD")

BASE_URL = "https://league.poolplayers.com"
LEAGUE_PATH = "/arapahoecounty"

# YOUR REAL MEMBER + LEAGUE PATH
MEMBER_TEAMS_URL = "https://league.poolplayers.com/arapahoecounty/member/3349374/3224381/teams"

OUTPUT_ROOT = Path(__file__).parent / "sanitized_fixtures"

# How long to let a route's GraphQL settle after networkidle, and how many of
# each entity to walk. The caps keep a single run bounded; raise them when a
# full-season sweep is wanted.
SETTLE_MS = 2500
MAX_TEAMS = 12
MAX_DIVISIONS = 12
MAX_MATCHES = 40
OUTPUT_ROOT.mkdir(exist_ok=True)

# ---------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------
def save_fixture(operation_name, entity_type, entity_id, payload):
    # Plain def on purpose: asyncio.to_thread expects a BLOCKING callable.
    # As an `async def` it returned a coroutine that was never awaited, so
    # every capture silently wrote nothing.
    folder = OUTPUT_ROOT / entity_type / entity_id
    folder.mkdir(parents=True, exist_ok=True)
    out_file = folder / f"{operation_name}.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"CAPTURED: {operation_name}  entity={entity_type}/{entity_id}  -> {out_file}")

# Operations whose responses carry live credentials. These are NEVER written
# to disk: a real run captured a valid deviceRefreshToken JWT into a file
# called "sanitized_fixtures", which it very much was not.
AUTH_OPERATIONS = {
    "login", "authorize", "GenerateAccessTokenMutation",
    "RefreshAccessTokenMutation", "logout",
}


# The real queries pass the entity id as plain `id`, not `teamId`/`divisionId`
# /`matchId`, so the entity has to come from the OPERATION NAME. Keying off the
# variable name alone filed every team and division response under
# global/global -- the routes were visited, the data was captured, and it all
# landed in the wrong folder.
# NOTE the ordering: "teamstat" must be tested against `alias` BEFORE the
# `team` prefixes, or "teamstat".startswith("team") wins and files a member's
# alias id as a team id.
OPERATION_ENTITY = (
    # TeamStat returns data.alias -- a member's identity WITHIN a league, and
    # its id is the alias id (the second id in a /member/<member>/<alias>/
    # URL). It is neither a team id nor the member id. Filing it under team/
    # put 3224381 next to real team ids like 13082948.
    ("alias", ("teamstat", "aliassession", "formatsbymemberid")),
    ("team", ("teampage", "teamroster", "teamschedule")),
    ("division", ("division", "divsionstandings", "divisionstandings")),
    ("match", ("matchpage", "matchdetail", "match")),
)


def classify_operation(op_name, variables):
    """(entity_type, entity_id) for a captured operation.

    Falls back to global/global only when the operation is not entity-scoped
    or carries no id -- never as a way of hiding an unrecognised one.
    """
    variables = variables or {}
    lowered = (op_name or "").lower()

    entity_id = (
        variables.get("id")
        or variables.get("teamId")
        or variables.get("divisionId")
        or variables.get("matchId")
    )

    if entity_id is not None:
        for entity_type, prefixes in OPERATION_ENTITY:
            if any(lowered.startswith(prefix) for prefix in prefixes):
                return (entity_type, str(entity_id))

    # explicit id-bearing variables still win even if the name is unfamiliar
    if "matchId" in variables:
        return ("match", str(variables["matchId"]))
    if "teamId" in variables:
        return ("team", str(variables["teamId"]))
    if "divisionId" in variables:
        return ("division", str(variables["divisionId"]))

    return ("global", "global")


# ---------------------------------------------------------
# SCRAPER
# ---------------------------------------------------------
async def login(page):
    print("NAVIGATING TO LOGIN PAGE")
    await page.goto(BASE_URL + "/login", wait_until="networkidle")

    print("FILLING LOGIN FORM")
    await page.fill("input[name='email']", APA_USERNAME)
    await page.fill("input[name='password']", APA_PASSWORD)

    print("SUBMITTING LOGIN")
    # The button renders disabled until the form hydrates; clicking too early
    # burns the whole retry budget on "element is not enabled".
    submit = page.get_by_role("button", name="Log In")
    await submit.wait_for(state="visible", timeout=30000)
    await page.wait_for_function(
        "() => { const b = [...document.querySelectorAll('button')]"
        ".find(x => x.textContent.trim() === 'Log In'); return b && !b.disabled; }",
        timeout=30000,
    )
    # league.poolplayers.com/login redirects to accounts.poolplayers.com/login,
    # where the submit control carries no type="submit" -- its only stable
    # handle is its accessible name. The class is a hashed CSS-module name
    # (button_button__TIoc7), so it is not safe to target.
    await page.get_by_role("button", name="Log In").click()

    await page.wait_for_timeout(1500)
    await complete_authorization(page)
    print("LOGIN COMPLETE")


# The consent screen that finishes the login handoff. Every condition below
# must hold before anything is clicked -- this button is only ever pressed on
# APA's own Member Services consent, never on an arbitrary prompt that happens
# to have a "Continue" on it.
CONSENT_HOST = "accounts.poolplayers.com"
CONSENT_PATH = "/authorize"
CONSENT_MARKER = "Member Services"


async def complete_authorization(page):
    """Click through APA's own consent screen, once, if it is showing.

    Submitting the login form does not finish the login: the browser lands on
    accounts.poolplayers.com/authorize, and until its "Continue" is pressed
    the league domain never gets an authorized session -- ViewerQuery returns
    viewer:null and every league URL bounces straight back here.

    The URL carries a live deviceRefreshToken JWT, so it is never printed.
    """
    parsed = urlparse(page.url)
    if parsed.hostname != CONSENT_HOST or not parsed.path.startswith(CONSENT_PATH):
        return False

    try:
        body = await page.inner_text("body")
    except Exception:
        return False
    if CONSENT_MARKER not in body:
        print("AUTHORIZE PAGE PRESENT but not the APA Member Services consent -- not clicking")
        return False

    button = page.get_by_role("button", name="Continue")
    if await button.count() == 0:
        print("APA consent screen present but no Continue button -- not clicking")
        return False

    print(f"APA MEMBER SERVICES CONSENT: clicking Continue (host={parsed.hostname})")
    await button.first.click()
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(2000)
    return True

async def capture_graphql(page):
    async def handle_response(response):
        try:
            if "gql.poolplayers.com" not in response.url:
                return

            # post_data_json is a PROPERTY in current Playwright, not a
            # coroutine method -- calling it raised "'dict' object is not
            # callable" on every single response.
            req = response.request.post_data_json
            if not req:
                return

            # The API also accepts BATCHED operations, where both the request
            # and the response are lists aligned by index. A single operation
            # arrives as a plain dict.
            requests = req if isinstance(req, list) else [req]
            payload = await response.json()
            payloads = payload if isinstance(payload, list) else [payload]

            for index, operation in enumerate(requests):
                if not isinstance(operation, dict) or "operationName" not in operation:
                    continue
                op_name = operation["operationName"]
                if op_name in AUTH_OPERATIONS:
                    print(f"SKIPPED (auth payload, not persisted): {op_name}")
                    continue
                variables = operation.get("variables", {})
                body = payloads[index] if index < len(payloads) else payload
                entity_type, entity_id = classify_operation(op_name, variables)
                await asyncio.to_thread(
                    save_fixture, op_name, entity_type, entity_id, body
                )

        except Exception as exc:
            # Never silent: a swallowed error here is indistinguishable from
            # "the site sent nothing", which is how a scrape that captured
            # zero fixtures still printed SCRAPE COMPLETE.
            print(f"CAPTURE FAILED for {response.url[:80]}: {type(exc).__name__}: {exc}")

    page.on("response", handle_response)

async def go_to_member_teams(page):
    print("NAVIGATING TO MEMBER TEAMS PAGE")
    await page.goto(MEMBER_TEAMS_URL, wait_until="domcontentloaded")
    if await complete_authorization(page):
        await page.goto(MEMBER_TEAMS_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

def _read_fixture(*parts):
    """Load a fixture this run already captured, or None."""
    path = OUTPUT_ROOT.joinpath(*parts)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def discover_entities():
    """Team, division and league ids straight out of the dashboardTeams
    payload the authenticated dashboard already returned.

    Deliberately NOT scraped from <a href> tags: the app is a client-rendered
    SPA and renders no anchors for these routes at all -- an earlier DOM-based
    pass found zero links on a fully authorized page. The GraphQL response is
    the real source of truth.
    """
    payload = _read_fixture("global", "global", "dashboardTeams.json")
    viewer = ((payload or {}).get("data") or {}).get("viewer") or {}

    slug, teams, divisions = None, [], []
    for team in viewer.get("leagueTeams") or []:
        team = team or {}
        if team.get("id"):
            teams.append(int(team["id"]))
        division = team.get("division") or {}
        if division.get("id") and division["id"] not in divisions:
            divisions.append(int(division["id"]))
        slug = slug or (team.get("league") or {}).get("slug")

    return slug, teams, divisions


def discover_match_ids(team_id):
    """Match ids from a team's own captured schedule."""
    payload = _read_fixture("team", str(team_id), "teamSchedule.json") or {}
    # Two fixture shapes exist on disk: this scraper writes the raw GraphQL
    # payload, while tools/capture_apa_graphql.py wraps it under "response".
    body = payload.get("response", payload)
    team = ((body or {}).get("data") or {}).get("team") or {}
    ids = []
    for match in team.get("matches") or []:
        match = match or {}
        if match.get("id") and not match.get("isBye"):
            ids.append(int(match["id"]))
    return ids


async def visit(page, url, label):
    """Navigate and let the SPA's GraphQL settle so the response handler sees
    it. networkidle alone is not enough -- the app fires follow-up queries
    after first paint."""
    try:
        await page.goto(url, wait_until="domcontentloaded")
        # A league route can bounce back to the consent screen; clear it and retry.
        if await complete_authorization(page):
            await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(SETTLE_MS)
        print(f"  visited {label} {url.rsplit('/', 1)[-1]}")
        return True
    except Exception as exc:
        print(f"  FAILED {label} {url}: {type(exc).__name__}: {exc}")
        return False


async def scrape_all(page):
    """Walk teams -> divisions -> matches so every entity refreshes in one
    run. The team/division/match GraphQL operations do not fire until their
    own routes are actually visited; waiting on the dashboard only ever
    produced the global queries.
    """
    print("SCRAPING TEAMS / MATCHES / DIVISIONS")

    slug, team_ids, division_ids = discover_entities()
    if not slug or not team_ids:
        print("  no teams found in dashboardTeams -- is the session authorized?")
        return
    league = f"{BASE_URL}/{slug}"
    print(f"  league={slug} teams={team_ids} divisions={division_ids}")

    for team_id in team_ids[:MAX_TEAMS]:
        await visit(page, f"{league}/team/{team_id}", "team")

    for division_id in division_ids[:MAX_DIVISIONS]:
        await visit(page, f"{league}/division/{division_id}", "division")

    match_ids = []
    for team_id in team_ids[:MAX_TEAMS]:
        for match_id in discover_match_ids(team_id):
            if match_id not in match_ids:
                match_ids.append(match_id)
    print(f"  {len(match_ids)} match(es) found across team schedules")
    for match_id in match_ids[:MAX_MATCHES]:
        await visit(page, f"{league}/match/{match_id}", "match")


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
async def main():
    async with async_playwright() as pw:
        print("LAUNCHING BROWSER")
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await capture_graphql(page)
        await login(page)
        await go_to_member_teams(page)
        await scrape_all(page)

        print("SCRAPE COMPLETE")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
