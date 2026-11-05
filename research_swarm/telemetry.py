"""Optional task-local events. Workers never call Streamlit APIs."""
from contextlib import contextmanager
from contextvars import ContextVar

_listener = ContextVar("research_progress_listener", default=None)
_cached = ContextVar("research_last_call_cached",default=False)


def cache_flag(value=None):
    if value is not None:
        _cached.set(value)
    return _cached.get()


def observed():
    return _listener.get() is not None


def emit(kind, **fields):
    listener = _listener.get()
    if listener:
        listener(kind, **fields)


@contextmanager
def observe(listener):
    token = _listener.set(listener)
    try:
        yield
    finally:
        _listener.reset(token)
