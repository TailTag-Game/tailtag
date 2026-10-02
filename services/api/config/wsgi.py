"""WSGI entry point for the TailTag API."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from django.core.wsgi import get_wsgi_application

if TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse, WSGIEnvironment

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

# Client-supplied trace context is ignored (#210, #260). Sentry's WSGI
# middleware runs inside WSGIHandler.__call__, so this outer wrapper strips the
# headers first. Names are normalized the same way the Sentry SDK does.
_IGNORED_TRACE_HEADERS = frozenset({"sentry-trace", "baggage"})


def _is_client_trace_header(environ_key: str) -> bool:
    name = environ_key.removeprefix("HTTP_").replace("_", "-").lower()
    return name in _IGNORED_TRACE_HEADERS


def _drop_client_trace_headers[Result](
    wsgi_app: Callable[[WSGIEnvironment, StartResponse], Result],
) -> Callable[[WSGIEnvironment, StartResponse], Result]:
    def application(environ: WSGIEnvironment, start_response: StartResponse) -> Result:
        for key in [key for key in environ if _is_client_trace_header(key)]:
            del environ[key]
        return wsgi_app(environ, start_response)

    return application


application = _drop_client_trace_headers(get_wsgi_application())
