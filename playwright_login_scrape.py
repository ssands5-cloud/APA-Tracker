import env_loader  # noqa: F401,E402  -- loads .env before anything else

import asyncio
import json
import re
from getpass import getpass
from pathlib import Path
from playwright.async_api import async_playwright

# Output directory for sanitized fixtures
FIXTURE_DIR = Path("sanitized_fixtures")
FIXTURE_DIR.mkdir(exist_ok=True)

# GraphQL operation names you want to capture
TARGET_OPERATIONS = {
    "teamPage",
    "teamRoster",
    "teamSchedule",
    "standings",
    "playerHistory"
}

def sanitize_graphql_response(payload):
    """
    Remove private fields, tokens, cookies, and anything sensitive.
    Keep only operationName, variables, and data.
    """
    sanitized = {}

    if "operationName" in payload:
        sanitized["operationName"] = payload["operationName"]

    if "variables" in payload:
        sanitized["variables"] = payload["variables"]

    if "data" in payload:
        sanitized["data"] = payload["data"]

    return sanitized


async def run():
    username = input("APA Username: ").strip()
    password = getpass("APA Password: ").strip()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        page = await context.new_page()

        print("Navigating to login page...")
        await page.goto("https://league.poolplayers.com/login")

        # Fill login form
        await page.fill("input[name='username']", username)
        await page.fill("input[name='password']", password)
        await page.click("button[type='submit']")

        # Wait for navigation after login
        await page.wait_for_load_state("networkidle")

        print("Login successful. Navigating to team page...")

        # Example: navigate to team page (replace with your team ID)
        team_id = "13082948"
        await page.goto(f"https://league.poolplayers.com/team/{team_id}")

        print("Capturing GraphQL traffic...")

        # Intercept network traffic
        async def handle_route(route, request):
            if request.resource_type == "xhr" and "graphql" in request.url:
                try:
                    post_data = request.post_data_json
                    op_name = post_data.get("operationName")

                    if op_name in TARGET_OPERATIONS:
                        print(f"Captured operation: {op_name}")

                        response = await route.fetch()
                        json_body = await response.json()

                        sanitized = sanitize_graphql_response(json_body)

                        out_file = FIXTURE_DIR / f"{op_name}.json"
                        out_file.write_text(json.dumps(sanitized, indent=2))

                except Exception as e:
                    print(f"Error processing request: {e}")

            await route.continue_()

        await context.route("**/*", handle_route)

        print("Interact with the site to trigger GraphQL calls.")
        print("Press Ctrl+C when finished.")

        # Keep browser open for manual navigation
        await asyncio.sleep(999999)


if __name__ == "__main__":
    asyncio.run(run())
