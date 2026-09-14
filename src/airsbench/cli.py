"""`airs` — the command installed by `pip install airs-bench`.

    airs serve
    airs probe   --records delivered.jsonl --source upstream.jsonl --task retrieval
    airs gate    --records delivered.jsonl --policy policy.json
    airs sources sample demo-stale --seed 7

Each subcommand IS the module's own `main`, so `airs probe` and
`python -m airsbench.probe` are one program with one set of exit codes — probe:
0 scored, 1 nothing measurable, 2 bad input; gate: 0 admitted, 1 refused, 2 bad
input. A scheduler that gates on those codes must not see them change because it
was invoked a different way.

Subcommands are imported only when chosen, so `airs gate` running as a pipeline
step loads nothing it does not use — in particular, not the web stack behind
`airs serve`.
"""

from __future__ import annotations

import sys
from typing import Callable, Sequence

COMMANDS = {
    "serve": "open the local web console in a browser (records stay on this machine)",
    "probe": "score a pipeline's readiness from a sample of delivered records",
    "gate": "admit or refuse a batch of records against a declared policy",
    "sources": "list, describe and sample your declared data sources",
}


def _load(command: str) -> Callable[[list[str]], int]:
    if command == "serve":
        from .server.__main__ import main
    elif command == "probe":
        from .probe import main
    elif command == "gate":
        from .gate.__main__ import main
    elif command == "sources":
        from .sources.__main__ import main
    else:
        raise KeyError(command)
    return main


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("airs-bench")
    except PackageNotFoundError:
        from . import __version__
        return __version__


def usage() -> str:
    width = max(map(len, COMMANDS))
    lines = ["usage: airs <command> [options]", "", "commands:"]
    lines += [f"  {name:<{width}}  {summary}" for name, summary in COMMANDS.items()]
    lines += [
        "",
        "Run 'airs <command> --help' for its options.",
        "No command calls a model, needs an API key, or sends data off this machine.",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(usage())
        return 0 if args else 2
    if args[0] == "--version":
        print(f"airs {_version()}")
        return 0
    if args[0] not in COMMANDS:
        print(f"airs: unknown command {args[0]!r}\n\n{usage()}", file=sys.stderr)
        return 2
    return _load(args[0])(args[1:])


if __name__ == "__main__":
    raise SystemExit(main())
