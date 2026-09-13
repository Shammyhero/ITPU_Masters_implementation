"""`create_app` — the FastAPI application behind `airs serve`.

One process serves the API under /api and the static web console at /. It is
built for one person on one machine, and for records that may be customer data:

- **Loopback by default, and a Host-header allowlist.** Binding to 127.0.0.1 is
  not enough on its own: any web page the user visits could use DNS rebinding to
  reach this server under its own origin and read the scores of whatever was
  pasted in. Requests addressed to any other host name are refused.
- **No CORS** unless `dev=True`, which admits the Next.js dev server on :3000
  while the frontend is being worked on.
- **A request-body cap**, so a mistaken multi-gigabyte paste fails at once with a
  message rather than exhausting memory.
- **No outbound requests**, and no path parameter that reads a file: records
  reach the server only in a request body or through `airs serve --records`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .. import __version__
from .api import InputError, error_response, router

WEB_DIR = Path(__file__).parents[1] / "web"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
DEV_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")
MAX_BODY_BYTES = 64 * 1024 * 1024

NOT_BUILT = """<!doctype html>
<title>AIRS — console not built</title>
<body style="font: 16px/1.5 system-ui, sans-serif; max-width: 40rem; margin: 4rem auto">
<h1>The AIRS API is running, but the web console is not in this install.</h1>
<p>This happens with an editable install from a source checkout. Build it with
<code>make web</code> and restart <code>airs serve</code>. The API itself works:
see <a href="/api/docs">/api/docs</a>.</p>
</body>
"""


def _size(n: int) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{n / 1e3:.0f} KB"


class BodyLimit:
    """Refuse a request whose declared body is larger than `limit` bytes."""

    def __init__(self, app, limit: int) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            length = dict(scope["headers"]).get(b"content-length", b"")
            if length.isdigit() and int(length) > self.limit:
                response = error_response(
                    None,
                    f"the request is {_size(int(length))} and the limit is "
                    f"{_size(self.limit)}; score a sample of the records, "
                    f"not the whole table",
                    status=413,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(
    *,
    web_dir: Path = WEB_DIR,
    allowed_hosts: tuple[str, ...] = LOOPBACK_HOSTS,
    dev: bool = False,
    preloaded: dict[str, Any] | None = None,
    max_body_bytes: int = MAX_BODY_BYTES,
) -> FastAPI:
    app = FastAPI(title="AIRS", version=__version__, docs_url="/api/docs",
                  redoc_url=None, openapi_url="/api/openapi.json")
    web_dir = Path(web_dir)
    app.state.frontend_built = (web_dir / "index.html").is_file()
    app.state.preloaded = preloaded

    @app.exception_handler(InputError)
    async def refused_input(request: Request, exc: InputError):
        return error_response(exc.input_name, exc.message)

    @app.exception_handler(RequestValidationError)
    async def malformed_request(request: Request, exc: RequestValidationError):
        problem = exc.errors()[0] if exc.errors() else {}
        location = [str(part) for part in problem.get("loc", ()) if part != "body"]
        field = ".".join(location) or "request body"
        return error_response(location[0] if location else None,
                              f"{field}: {problem.get('msg', 'invalid request')}")

    app.include_router(router)

    if app.state.frontend_built:
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    else:
        @app.get("/", include_in_schema=False, response_class=HTMLResponse)
        def console_not_built():
            return NOT_BUILT

    # Added innermost first: the host check runs before anything else sees a request.
    if dev:
        app.add_middleware(CORSMiddleware, allow_origins=list(DEV_ORIGINS),
                           allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    app.add_middleware(BodyLimit, limit=max_body_bytes)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))
    return app
