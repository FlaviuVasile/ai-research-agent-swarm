"""Wall-clock and monotonic deadlines, including a check immediately after resume."""
import asyncio
from contextlib import contextmanager, suppress
from contextvars import ContextVar
import time

_document = ContextVar("research_document_deadline",default=None)


class BudgetExceeded(ValueError):
    pass


@contextmanager
def document_budget(seconds):
    old=_document.get()
    deadline=(time.time()+seconds,time.monotonic()+seconds)
    if old:
        deadline=(min(old[0],deadline[0]),min(old[1],deadline[1]))
    token=_document.set(deadline)
    try:
        yield
    finally:
        _document.reset(token)


def remaining_document():
    deadline=_document.get()
    return min(deadline[0]-time.time(),deadline[1]-time.monotonic()) if deadline else float("inf")


async def timeboxed(awaitable, seconds, label):
    async def invoke():
        return await awaitable
    task=asyncio.create_task(invoke())
    wall_end=time.time()+seconds
    mono_end=time.monotonic()+seconds
    try:
        while True:
            remaining=min(wall_end-time.time(),mono_end-time.monotonic(),remaining_document())
            if remaining<=0:
                raise BudgetExceeded(f"{label} time budget exceeded. Completed summary steps are saved; retry to resume. "
                                     "The request was cancelled locally; no automatic retry was made.")
            done,_=await asyncio.wait({task},timeout=min(1,remaining))
            # Check wall time again before accepting a result after a machine/process pause.
            if min(wall_end-time.time(),mono_end-time.monotonic(),remaining_document())<=0:
                raise BudgetExceeded(f"{label} time budget exceeded. Completed summary steps are saved; retry to resume.")
            if done:
                return task.result()
    finally:
        if not task.done():
            task.cancel()
            done,_=await asyncio.wait({task},timeout=1)
            if not done:
                # Never turn a deadline into an unbounded await of cancellation.
                task.add_done_callback(lambda finished: finished.exception() if not finished.cancelled() else None)
        if task.done():
            with suppress(asyncio.CancelledError,Exception):
                task.result()
