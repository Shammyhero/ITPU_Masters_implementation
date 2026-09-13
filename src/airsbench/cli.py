"""`airs` — the command installed by `pip install airs-bench`.

    airs probe --records delivered.jsonl --source upstream.jsonl --task retrieval
    airs gate  --records delivered.jsonl --policy policy.json

Each subcommand IS the module's own `main`, so `airs probe` and
`python -m airsbench.probe` are one program with one set of exit codes — probe:
0 scored, 1 nothing measurable, 2 bad input; gate: 0 admitted, 1 refused, 2 bad
input. A scheduler that gates on those codes must not see them change because it
was invoked a different way.

Subcommands are imported only when chosen, so `airs gate` running as a pipeline
step loads nothing it does not use.
"""

from __future__ import annotations

import sys
from typing import Callable, Sequence

COMMANDS = {
    "probe": "score a pipeline's readiness from a sample of delivered records",
    "gate": "admit or refuse a batch of records against a declared policy",
}


def _load(command: str) -> Callable[[list[str]], int]:
    if command == "probe":
        from .probe import main
    elif command == "gate":
        from .gate.__main__ import main
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
        "No command calls a model, needs an API key, or uses the network.",
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
