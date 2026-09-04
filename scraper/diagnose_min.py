"""
diagnose_min.py

Bisects the silent-exit bug in full_apa_scrape.py, where "MAIN BLOCK
REACHED" prints and then the process ends -- no error, no traceback, not
even caught by a bare `except BaseException` wrapped around asyncio.run().
That means whatever is happening is not a normal Python exception at all:
either something outside Python is killing the process (antivirus/EDR is
a real candidate), or something is crashing at a level below Python's own
exception handling.

This script does almost nothing, in isolated stages, so whichever STEP
number is the LAST one printed tells us exactly which layer is responsible:

  STEP 0-2   plain asyncio, zero Playwright involved
  STEP 3-4   asyncio.run() itself
  STEP 5-7   Playwright's driver process starting (no browser yet)
  STEP 8-9   an actual headless Chromium launching
  STEP 10-11 an actual NON-headless Chromium launching (this is what
             full_apa_scrape.py does -- if everything above this line
             passes but this one doesn't, the bug is specifically about
             showing a visible browser window, not Playwright itself)

Run exactly as-is, nothing to edit:
    python diagnose_min.py

Then send back the LAST numbered STEP line that printed (and whether
anything after it -- error text or nothing at all -- appeared).
"""

print("STEP 0: FILE LOADED, PYTHON STARTING")

import asyncio
import sys

print("STEP 1: ASYNCIO IMPORTED")
print("  Python:", sys.version)
print("  Platform:", sys.platform)


async def tiny():
    print("STEP 2: INSIDE A PLAIN COROUTINE -- if you see this, asyncio.run() itself works")


if __name__ == "__main__":
    print("STEP 3: ABOUT TO CALL asyncio.run() ON A TRIVIAL COROUTINE")
    asyncio.run(tiny())
    print("STEP 4: asyncio.run() RETURNED NORMALLY -- plain asyncio is fine on this machine")

    print("STEP 5: IMPORTING PLAYWRIGHT")
    from playwright.async_api import async_playwright

    print("STEP 6: PLAYWRIGHT IMPORTED -- ABOUT TO START ITS DRIVER (NO BROWSER YET)")

    async def playwright_only():
        print("STEP 7: INSIDE THE PLAYWRIGHT COROUTINE")
        async with async_playwright() as p:
            print("STEP 8: PLAYWRIGHT DRIVER STARTED OK -- about to launch a HEADLESS browser")
            browser = await p.chromium.launch(headless=True)
            print("STEP 9: HEADLESS CHROMIUM LAUNCHED OK")
            await browser.close()
            print("STEP 10: HEADLESS CHROMIUM CLOSED OK -- about to launch a VISIBLE browser")
            browser2 = await p.chromium.launch(headless=False)
            print("STEP 11: VISIBLE (non-headless) CHROMIUM LAUNCHED OK")
            await browser2.close()
            print("STEP 12: ALL DIAGNOSTICS PASSED. The bug is not reproducible by this script --")
            print("         it is specific to something full_apa_scrape.py does beyond this.")

    asyncio.run(playwright_only())
