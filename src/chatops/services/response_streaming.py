from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator


ResponseStreamHandler = Callable[[str], None]

_response_stream_handler: ContextVar[ResponseStreamHandler | None] = ContextVar(
    "response_stream_handler",
    default=None,
)


@contextmanager
def response_stream_handler_context(handler: ResponseStreamHandler | None) -> Iterator[None]:
    if handler is None:
        yield
        return

    token = _response_stream_handler.set(handler)
    try:
        yield
    finally:
        _response_stream_handler.reset(token)


def get_response_stream_handler() -> ResponseStreamHandler | None:
    return _response_stream_handler.get()
