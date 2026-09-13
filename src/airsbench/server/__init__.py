"""The local web console behind `airs serve` — the only package that imports FastAPI.

`airsbench.probe`, `airsbench.gate` and the `airs` command stay importable
without it (`tests/test_server.py` pins that), so a pipeline step running
`airs gate` never loads a web framework.
"""

from .app import create_app

__all__ = ["create_app"]
