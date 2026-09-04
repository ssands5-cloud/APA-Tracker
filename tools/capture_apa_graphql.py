"""Capture APA GraphQL traffic from a browser you log into yourself.

Replaces the DevTools -> "save HAR with content" -> PowerShell dance. It opens
a real Chromium window, you log into APA by hand, and every GraphQL call the
site makes while you browse is recorded.

WHAT THIS DOES NOT DO
  - It never asks for, reads, stores or transmits your password. You type it
    into the real APA login page in the browser window; this script cannot see
    the keystrokes and never touches the field.
  - It never writes your access token or cookies to disk, and never prints
    them. The token is held in memory only, and only to let --sync reuse the
    session you already opened.
  - It sends nothing anywhere. Both output files are written locally.

WHAT IT WRITES
  apa-capture-shapes.json   Field names and TYPES only -- no values. This is
                            the file that is safe to share: it is the response
                            schema, with every name, score and id replaced by
                            "str" / "int" / "float". Short ALL_CAPS strings are
                            kept verbatim because they are enum values like
                            "COMPLETED" and a person's name cannot look like
                            one.
  apa-capture-full.json     The real responses, for building local fixtures.
                            STAYS ON YOUR MACHINE. Gitignored. Contains
                            teammates' names.

USAGE
    pip install playwright
    python -m playwright install chromium

    python tools/capture_apa_graphql.py           # capture only
    python tools/capture_apa_graphql.py --sync    # capture, then sync live

Be a normal user while it runs: visit the pages you want captured, at the pace
you would anyway. This is not a crawler and must not be used as one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Running this as `python tools/capture_apa_graphql.py` puts tools/ on sys.path,
# not the repo root, so --sync could not import scheduler.graphql_sync at all.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

GRAPHQL_HOST = "gql.poolplayers.com"
LEAGUE_URL = "https://league.poolplayers.com"

SHAPES_PATH = Path("apa-capture-shapes.json")
FULL_PATH = Path("apa-capture-full.json")

#: A short, all-caps token is a GraphQL enum ("COMPLETED", "HOME", "THURSDAY"),
#: not anyone's data. Keeping these makes the shape file far more useful for
#: writing mappings, and no name, email or phone number can match it.
_ENUM_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")


def summarize_shape(value: Any) -> Any:
    """Replace every value with its type, keeping keys and structure.

    This is the guarantee that makes the shapes file shareable, so it is
    deliberately total: anything not explicitly handled degrades to its type
    name rather than passing a value through.
    """
    if isinstance(value, bool):
        return "bool"
    if value is None:
        return "null"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return value if _ENUM_PATTERN.match(value) else "str"
    if isinstance(value, dict):
        return {key: summarize_shape(item) for key, item in value.items()}
    if isinstance(value, list):
        if not value:
            return []
        # One representative element is enough to describe the shape, and the
        # count says whether the list was populated without exposing rows.
        return [summarize_shape(value[0]), f"...{len(value)} item(s)"]
    return type(value).__name__


def _record(captures: dict, operation: str, variables: Any, query: str, response: Any) -> None:
    captures[operation] = {
        "operationName": operation,
        "variables": variables,
        "query": query,
        "response": response,
    }


def capture(sync: bool = False) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "Playwright is not installed. Run these two commands, then try again:\n"
            "    pip install playwright\n"
            "    python -m playwright install chromium"
        )

    captures: dict[str, dict] = {}
    token_holder: dict[str, str] = {}

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False)
        except Exception as exc:
            # Playwright installs the library and the browser binary in two
            # separate steps, and missing the second one is the common case.
            sys.exit(
                f"Could not start Chromium: {exc}\n\n"
                "If it says the browser is not installed, run:\n"
                "    python -m playwright install chromium"
            )
        context = browser.new_context()
        page = context.new_page()

        def on_response(response) -> None:
            if GRAPHQL_HOST not in response.url:
                return
            request = response.request
            try:
                body = request.post_data_json
            except Exception:
                return
            if not body:
                return

            # Held in memory only, never written or printed: it lets --sync
            # reuse the session you just opened instead of you pasting a token.
            auth = request.headers.get("authorization")
            if auth:
                token_holder["token"] = auth

            for item in body if isinstance(body, list) else [body]:
                operation = (item or {}).get("operationName")
                if not operation:
                    continue
                try:
                    payload = response.json()
                except Exception:
                    continue
                _record(captures, operation, item.get("variables"), item.get("query"), payload)
                print(f"  captured: {operation}")

        # Listening on the context, not the page: logging in redirects through
        # accounts.poolplayers.com and can land in a new tab, and a page-level
        # listener would silently miss everything that happens there.
        context.on("response", on_response)

        print(__doc__.split("USAGE")[0])
        print("=" * 70)
        print("A browser window is opening. In it:")
        print("  1. Log into APA as you normally would.")
        print("  2. Visit your TEAM page (roster + schedule).")
        print("  3. Visit your DIVISION STANDINGS page.")
        print("  4. Come back here and press Enter.")
        print("=" * 70)
        page.goto(LEAGUE_URL)

        try:
            input("\nPress Enter when you have visited those pages... ")
        except (EOFError, KeyboardInterrupt):
            pass

        browser.close()

    if not captures:
        print("\nNo GraphQL operations were captured.")
        print("That usually means the pages did not finish loading before you")
        print("pressed Enter, or you were not logged in. Nothing was written.")
        return {}

    shapes = {
        name: {
            "operationName": name,
            "variables": summarize_shape(item["variables"]),
            "query": item["query"],          # the document itself: schema, not data
            "response": summarize_shape(item["response"]),
        }
        for name, item in captures.items()
    }

    SHAPES_PATH.write_text(json.dumps(shapes, indent=2), encoding="utf-8")
    FULL_PATH.write_text(json.dumps(captures, indent=2), encoding="utf-8")

    print(f"\nCaptured {len(captures)} operation(s): {', '.join(sorted(captures))}")
    print(f"\n  {SHAPES_PATH}  <- SAFE TO SHARE (names and types only, no values)")
    print(f"  {FULL_PATH}  <- keep local; has real names. Gitignored.")

    if sync:
        _run_sync(token_holder.get("token"))

    return captures


def _run_sync(token: str | None) -> None:
    """Run the live sync with the in-memory token, without writing it down."""
    if not token:
        print("\nNo access token was seen, so --sync has nothing to use.")
        return

    import os

    print("\nRunning the live sync with the session you just opened...")
    os.environ["APA_ACCESS_TOKEN"] = token   # this process only; never persisted
    try:
        from scheduler.graphql_sync import run

        run()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Sync failed: {type(exc).__name__}: {exc}")
    finally:
        os.environ.pop("APA_ACCESS_TOKEN", None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture APA GraphQL traffic.")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="After capturing, run the live sync using the open session.",
    )
    capture(sync=parser.parse_args().sync)
