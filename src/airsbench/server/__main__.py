"""`airs serve` — open the AIRS console in a browser, on this machine only.

    airs serve
    airs serve --records delivered.jsonl --source upstream.jsonl --task retrieval
    airs serve --sources sources.yaml
    airs serve --port 8080 --no-browser

Records named with --records and --source are validated before the server
starts and offered to the page. Data sources are declared with --sources (see
`airsbench.sources.config`) and validated at startup too. The page never asks
the server to read a path or open a connection, so no web page can use this
server to reach files or systems on the machine. It binds to 127.0.0.1 unless
told otherwise. Its only outbound requests go where the person running it
pointed: an `http` source's DECLARED url (A10), and a model provider whose key is
in the environment (A5) — never an address named in a request.

Exit status: 0 after a clean stop, 2 if the records, the sources, the task or the
port are unusable — reported before anything listens.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

from ..probe import ProbeError, parse_records, read_jsonl, score

LOOPBACK = ("127.0.0.1", "localhost")


def preload(records: Path | None, source: Path | None, task: str) -> dict[str, Any] | None:
    """Read and fully score the named files, so a problem stops `airs serve` at once.

    The page receives the file text exactly as written — ISO timestamps stay ISO —
    so what it sends back to /api/score is what the probe validated here.
    """
    if source is not None and records is None:
        raise ProbeError("--source needs --records: consistency compares the delivered "
                         "records against their upstream versions")
    if records is None:
        return None
    delivered_text = read_jsonl(records)
    source_text = read_jsonl(source) if source is not None else None
    score(parse_records(delivered_text, str(records)),
          parse_records(source_text, str(source), unique_ids=True)
          if source_text is not None else None,
          task)
    return {
        "label": records.name + (f" against {source.name}" if source else ""),
        "task": task,
        "delivered": delivered_text,
        "source": source_text,
        "records_path": str(records.resolve()),
        "source_path": str(source.resolve()) if source else None,
    }


def _port_is_free(host: str, port: int) -> None:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as candidate:
        candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        candidate.bind((host, port))


def _open_when_started(server, url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if server.started:
        webbrowser.open(url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="airs serve", description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1",
                        help="interface to bind (default 127.0.0.1: this machine only)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--records", type=Path, default=None,
                        help="JSONL of delivered records to open the console with")
    parser.add_argument("--source", type=Path, default=None,
                        help="JSONL of the same records upstream, matched on 'id'")
    parser.add_argument("--sources", type=Path, default=None,
                        help="a sources.yaml declaring your data sources")
    parser.add_argument("--task", default="retrieval",
                        help="calibrated weight profile for the preloaded records")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    parser.add_argument("--dev", action="store_true",
                        help="allow the Next.js dev server on :3000 to call the API (CORS)")
    args = parser.parse_args(argv)

    try:
        preloaded = preload(args.records, args.source, args.task)
        declared = None
        if args.sources is not None:
            from ..sources.config import load_sources

            declared = load_sources(args.sources)
    except ProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        _port_is_free(args.host, args.port)
    except OSError as exc:
        print(f"error: cannot listen on {args.host}:{args.port} ({exc.strerror or exc}); "
              f"pass --port to choose another", file=sys.stderr)
        return 2

    import uvicorn

    from .app import create_app

    loopback = args.host in LOOPBACK
    if not loopback:
        print(f"warning: binding {args.host} makes the console, and every record pasted "
              f"into it, reachable from other machines on this network", file=sys.stderr)
    app = create_app(allowed_hosts=LOOPBACK if loopback else ("*",),
                     dev=args.dev, preloaded=preloaded, sources=declared)

    shown_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{shown_host}:{args.port}/"
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port,
                                           log_level="warning"))
    if not args.no_browser:
        threading.Thread(target=_open_when_started, args=(server, url), daemon=True).start()

    print(f"AIRS console at {url}   (Ctrl+C to stop)")
    if loopback:
        print("Listening on this machine only. No model is called and nothing is sent anywhere.")
    if declared is not None:
        print(f"Validated {len(declared)} data sources from {args.sources} "
              f"(`airs sources list` shows them).")
    if not app.state.frontend_built:
        print("The web console is not built into this install; the API is up at /api/docs.")
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
