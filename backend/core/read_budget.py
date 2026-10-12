"""One deadline shared by a read operation and all of its database workers."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from time import monotonic

_deadline: ContextVar[float | None] = ContextVar("read_deadline", default=None)


def remaining_read_seconds() -> float | None:
    deadline = _deadline.get()
    if deadline is None:
        return None
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("Recruiter read deadline exceeded.")
    return remaining


@contextmanager
def read_budget(seconds: float = 24):
    existing = _deadline.get()
    token = _deadline.set(min(existing, monotonic() + seconds)
                          if existing is not None else monotonic() + seconds)
    try:
        remaining_read_seconds()
        yield
    finally:
        _deadline.reset(token)


def bounded_read(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with read_budget():
            return function(*args, **kwargs)
    return wrapped
