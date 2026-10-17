"""Flushed operator progress during a blocking stage; never runs work in the timer thread."""
from contextlib import contextmanager
import threading
import time


@contextmanager
def progress_span(notify, label, *, interval=5.0):
    if notify is None:
        yield
        return
    started = time.monotonic()
    finished = threading.Event()
    notify(f"START {label}")

    def heartbeat():
        while not finished.wait(interval):
            try:
                notify(f"STILL RUNNING {label} ({time.monotonic()-started:.0f}s elapsed)")
            except Exception:
                # Main-thread status writes still report/fail normally. A
                # diagnostic timer must not replace the worker's exception.
                return

    timer = threading.Thread(target=heartbeat, name="refresh-progress", daemon=True)
    timer.start()
    try:
        yield
    except BaseException as exc:
        finished.set()
        timer.join()
        notify(f"FAILED {label}: {type(exc).__name__}")
        raise
    else:
        finished.set()
        timer.join()
        notify(f"DONE {label} ({time.monotonic()-started:.1f}s)")
