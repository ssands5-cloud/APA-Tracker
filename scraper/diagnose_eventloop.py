"""
diagnose_eventloop.py

Follow-up to diagnose_min.py's finding: asyncio.run() died with zero output
on this machine, before the coroutine body ever ran (its own STEP 2 never
printed) -- meaning whatever crashes is inside asyncio.run()'s own setup,
not in anything this project's code does. sys._is_gil_enabled() came back
True, which rules out a free-threaded build as the cause.

This isolates further: does bare event LOOP CONSTRUCTION crash, or only
actually RUNNING something on the Windows-default ProactorEventLoop (the
one with subprocess support, which Playwright's driver needs)?

Run exactly as-is:
    python diagnose_eventloop.py

Send back the last lettered STEP that printed.
"""

import sys

print("A: FILE LOADED")
print("A: Python", sys.version)

import asyncio

print("B: ASYNCIO IMPORTED")

print("C: CREATING A NEW EVENT LOOP DIRECTLY (no running anything on it yet)")
loop = asyncio.new_event_loop()
print("D: EVENT LOOP OBJECT CREATED OK:", type(loop).__name__)
loop.close()
print("E: EVENT LOOP CLOSED OK")

print("F: NOW CALLING asyncio.run() ON A TRIVIAL COROUTINE -- the exact call that died before")


async def tiny():
    print("G: INSIDE THE COROUTINE (this is the line that never printed last time)")


asyncio.run(tiny())
print("H: asyncio.run() RETURNED NORMALLY")

print("I: NOW FORCING THE SELECTOR EVENT LOOP INSTEAD OF THE DEFAULT PROACTOR ONE")
print("   (Selector cannot run subprocesses on Windows, so this is diagnostic")
print("   only -- it would not be a usable fix for the real scraper.)")
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def tiny2():
    print("J: INSIDE THE COROUTINE, UNDER THE SELECTOR EVENT LOOP")


asyncio.run(tiny2())
print("K: ALL DONE. If you see this: Selector works, so the earlier crash is Proactor-specific.")
