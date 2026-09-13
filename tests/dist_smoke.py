"""Smoke-test an INSTALLED `airs serve`: start it, call the API, stop it.

Run by `make dist-check` with the throwaway venv's interpreter, against the
installed wheel rather than the source tree. Standard library only, and not
collected by pytest (no `test_` prefix).

    python tests/dist_smoke.py path/to/venv/bin/airs path/to/examples
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _free_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def _wait_for(url: str, process: subprocess.Popen, timeout: float = 20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(f"airs serve exited early:\n{process.stdout.read()}")
        try:
            return _get_json(url)
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.2)
    raise SystemExit(f"airs serve did not answer {url} within {timeout:.0f}s")


def main(airs: str, examples: Path) -> int:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    process = subprocess.Popen([airs, "serve", "--no-browser", "--port", str(port)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        meta = _wait_for(f"{base}/api/meta", process)
        body = json.dumps({
            "task": "retrieval",
            "delivered": (examples / "probe" / "degraded.jsonl").read_text(encoding="utf-8"),
            "source": (examples / "probe" / "source.jsonl").read_text(encoding="utf-8"),
        }).encode()
        request = urllib.request.Request(f"{base}/api/score", data=body,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.load(response)
        if result["band"] != "AT RISK":
            raise SystemExit(f"/api/score returned band {result['band']!r} for the degraded sample")
        samples = _get_json(f"{base}/api/samples")
        if not samples["samples"]:
            raise SystemExit("/api/samples is empty: server/data/samples.json "
                             "is missing from the wheel")
        with urllib.request.urlopen(f"{base}/", timeout=10) as page:
            status = page.status
        print(f"airs serve: /api/meta v{meta['version']}, /api/score {result['band']} "
              f"{result['airs']:.1f}, /api/samples {len(samples['samples'])}, / {status} "
              f"(web console built: {meta['frontend_built']})")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], Path(sys.argv[2])))
