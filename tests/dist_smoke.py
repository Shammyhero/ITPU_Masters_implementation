"""Smoke-test an INSTALLED `airs serve`: start it, call the API and the console, stop it.

Run by `make dist-check` with the throwaway venv's interpreter, against the
installed wheel rather than the source tree. Standard library only, and not
collected by pytest (no `test_` prefix).

    python tests/dist_smoke.py path/to/venv/bin/airs path/to/examples
"""

from __future__ import annotations

import json
import re
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


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.read().decode("utf-8")


def _get_json(url: str):
    return json.loads(_get(url)[1])


def _post_json(url: str, body: dict):
    request = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
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

        # ---- the API --------------------------------------------------------
        result = _post_json(f"{base}/api/score", {
            "task": "retrieval",
            "delivered": (examples / "probe" / "degraded.jsonl").read_text(encoding="utf-8"),
            "source": (examples / "probe" / "source.jsonl").read_text(encoding="utf-8"),
        })
        if result["band"] != "AT RISK":
            raise SystemExit(f"/api/score returned band {result['band']!r} for the degraded sample")
        samples = _get_json(f"{base}/api/samples")
        if not samples["samples"]:
            raise SystemExit("/api/samples is empty: server/data/samples.json "
                             "is missing from the wheel")
        replayed = _post_json(f"{base}/api/replay", {
            "task": "retrieval",
            "policy": {"name": "consistency", "min_dimension": {"consistency": 90.0}},
        })
        rate = replayed["outcome"]["exchange_rate"]
        if rate is None or replayed["corpus"]["runs"] == 0:
            raise SystemExit("/api/replay priced nothing: replay_corpus.json missing or empty")

        # ---- the console ----------------------------------------------------
        if not meta["frontend_built"]:
            raise SystemExit("the installed package has no web console: "
                             "src/airsbench/web/ did not make it into the wheel")
        _, home = _get(f"{base}/")
        # `/` is the conversation (A8); the probe page moved to `/check/`. Assert
        # what each ROUTE serves — "Check my pipeline" also appears in the nav on
        # every page, so matching it alone would pass whatever is at `/`.
        if "Ask your pipeline a question" not in home:
            raise SystemExit("/ did not serve the conversation console")
        _, check = _get(f"{base}/check/")
        if "<h1>Check my pipeline</h1>" not in check:
            raise SystemExit("/check/ did not serve the probe console")
        _, replay = _get(f"{base}/replay/")
        # The replay feed is baked into the page at build time, so this route
        # must work with no API call at all — it is the offline half of the demo.
        if "the study&#x27;s own runs" not in replay and "study" not in replay:
            raise SystemExit("/replay/ did not serve the recorded-runs console")
        _, evidence = _get(f"{base}/evidence/")
        if "Your agent is not going to tell you" not in evidence:
            raise SystemExit("/evidence/ did not serve the evidence page")
        script = re.search(r'src="(/_next/static/[^"]+\.js)"', home)
        if script is None:
            raise SystemExit("/ references no /_next/static script")
        script_status, _ = _get(base + script.group(1))

        print(f"airs serve: /api/meta v{meta['version']}, /api/score {result['band']} "
              f"{result['airs']:.1f}, /api/samples {len(samples['samples'])}, "
              f"/api/replay {rate:.2f} over {replayed['corpus']['runs']} runs; "
              f"console /, /check/, /replay/ and /evidence/ served, "
              f"{script.group(1).rsplit('/', 1)[-1]} {script_status}")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], Path(sys.argv[2])))
