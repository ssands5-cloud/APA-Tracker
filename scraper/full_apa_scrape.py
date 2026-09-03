"""
full_apa_scrape.py

Local Playwright scraper for the APA Tracker project. Run this on YOUR
machine, in YOUR terminal. It opens a real, visible Chromium window, asks
YOU (locally) for your APA username and password, logs in, then writes a
SANITIZED fixture (field names and value TYPES only, no real values) for
every GraphQL response the site makes while you browse -- into
scraper/sanitized_fixtures/.

Your credentials are read by getpass()/input() into local Python variables,
used once to fill the login form, and never written to disk, logged, or
sent anywhere except the real APA login page itself. Nothing in this script
uploads, emails, or otherwise transmits anything to Claude, Copilot, or any
other service.
"""

print("FILE LOADED")

import asyncio
import getpass
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright

print("IMPORTS OK")

# --- Configuration ------------------------------------------------------

BASE_URL = "https://league.poolplayers.com"
LOGIN_PATH = "/login"
GRAPHQL_HOST = "gql.poolplayers.com"

OUTPUT_DIR = Path(__file__).resolve().parent / "sanitized_fixtures"

# Login form selectors. UNVERIFIED against the live site -- see
# parser/apa_page_map.py's own docstring: the portal is a client-side app,
# so a classic server-rendered <form> may not even exist. Each is a
# comma-separated CSS selector list; Playwright's Locator tries the whole
# selector and .first picks the first match, so listing several plausible
# selectors here means one of them is likely to hit without guessing wrong
# and failing silently. type="password" is the one near-universal bet: a
# real login page needs it for password managers to work at all.
USERNAME_SELECTORS = (
    "input[name='username'], input[name='email'], input[type='email'], "
    "input[autocomplete='username'], input#username, input#email"
)
PASSWORD_SELECTORS = "input[type='password'], input[name='password'], input#password"
SUBMIT_SELECTORS = (
    "button[type='submit'], button:has-text('Log In'), "
    "button:has-text('Login'), button:has-text('Sign In')"
)

# --- Sanitization ---------------------------------------------------------
# Identical logic to tools/apa-console-capture.js and
# tools/capture_apa_graphql.py's summarize_shape: every value becomes its
# TYPE, so what lands on disk is a schema, never data. Kept as its own
# well-tested block rather than re-derived here, because this is the one
# function standing between "safe to look at" and "has real names in it."

# A short ALL_CAPS string is a GraphQL enum (COMPLETED, HOME, EIGHT_BALL),
# not personal data -- kept verbatim because it IS the schema. Anchored and
# length-capped so a name or id cannot accidentally match.
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


def write_sanitized_fixture(operation_name, variables, query, response_json):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "operationName": operation_name,
        "variables": summarize_shape(variables),
        "query": query,  # the query document itself: schema text, not data
        "response": summarize_shape(response_json),
    }
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", operation_name)
    path = OUTPUT_DIR / (safe_name + ".json")
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


async def handle_graphql_response(response):
    """Reads one GraphQL response and writes a sanitized fixture for it.

    Registered on the "response" EVENT (context.on("response", ...)), not a
    page.route() interceptor: route() exists to modify or block a request
    before it completes, which is not the goal here. This only needs to
    OBSERVE traffic that already happened, with zero risk of altering what
    the real site sees or receives.

    Playwright's Python bindings run on pyee's AsyncIOEventEmitter, which
    schedules an async handler passed to .on() as a task automatically --
    confirmed by reading pyee's own emit() implementation, not assumed. No
    manual asyncio.create_task() wrapping is needed here.
    """
    if GRAPHQL_HOST not in response.url:
        return

    request = response.request
    post_data = request.post_data_json  # a property, not a coroutine
    if not post_data:
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
        write_sanitized_fixture(
            operation_name, item.get("variables"), item.get("query"), resp_item
        )
        print("CAPTURED:", operation_name)


async def main():
    print("MAIN STARTED")

    username = input("APA username: ")
    password = getpass.getpass("APA password: ")

    print("LAUNCHING BROWSER")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        print("BROWSER LAUNCHED")

        context = await browser.new_context()
        print("CONTEXT CREATED")

        # Attached to the CONTEXT, not one page: login can redirect through
        # a second domain (accounts.poolplayers.com) and land in a new tab,
        # which a page-level listener would silently miss.
        context.on("response", handle_graphql_response)
        print("GRAPHQL CAPTURE READY")

        page = await context.new_page()
        print("PAGE CREATED")

        print("NAVIGATING TO LOGIN PAGE")
        await page.goto(BASE_URL + LOGIN_PATH)
        await page.wait_for_load_state("networkidle")

        print("FILLING LOGIN FORM")
        try:
            await page.locator(USERNAME_SELECTORS).first.fill(username, timeout=8000)
            await page.locator(PASSWORD_SELECTORS).first.fill(password, timeout=8000)
        except Exception as exc:
            print("COULD NOT FIND LOGIN FIELDS AUTOMATICALLY:", exc)
            print("The real login form's field names are unverified (see")
            print("parser/apa_page_map.py) -- log in by hand in the open")
            print("browser window instead. Capture keeps working either way.")

        print("SUBMITTING LOGIN")
        try:
            await page.locator(SUBMIT_SELECTORS).first.click(timeout=8000)
        except Exception as exc:
            print("COULD NOT FIND A SUBMIT BUTTON AUTOMATICALLY:", exc)
            print("Click Log In by hand in the browser window.")

        await page.wait_for_load_state("networkidle")
        print("LOGIN COMPLETE")

        # Deliberately NOT hardcoding division/team/player URLs below. Only
        # the GraphQL OPERATION names are confirmed (teamPage, divisionLayout,
        # divsionStandings, ...) -- the browser URL paths that trigger them
        # were never captured, and a wrong guessed URL fails in the worst
        # way: it loads *something* without erroring, so a silently wrong
        # page looks like success. Navigating home and then waiting for a
        # human to click is the same approach this project's prior DevTools
        # capture script used, and it is what actually worked.
        await page.goto(BASE_URL)

        print()
        print("Browser is open. Click through to your DIVISION page, your")
        print("TEAM page, and a PLAYER or MATCH page. Each GraphQL response")
        print("is captured and written to scraper/sanitized_fixtures/ as you")
        print("go -- watch that folder fill in while you click.")
        print()

        # Run in a worker thread, not the main thread: a plain blocking
        # input() call here would also block asyncio's event loop, and
        # Playwright needs that loop running to keep processing the
        # browser's CDP connection -- so a plain input() would pause
        # capturing (not lose it, just delay it until you press Enter,
        # since the OS still buffers the traffic, but that defeats the
        # point of capturing WHILE you browse).
        await asyncio.to_thread(input, "Press Enter here when you are done browsing... ")

        await browser.close()

    print("SCRAPE COMPLETE")


if __name__ == "__main__":
    print("MAIN BLOCK REACHED")
    asyncio.run(main())
