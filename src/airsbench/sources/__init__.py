"""Where the Analyst reads records from — declared, read-only data sources.

A source is one side of a pipeline: what it delivers to the agent, or the system
of record upstream. The Analyst works on a `SourcePair` of the two. Sources are
declared by the person running the tool (`sources.yaml` or command-line flags),
never named in an HTTP request, and none of them writes.

    base.py     the protocol, `SourcePair`, `Sample`, `to_probe_entry`
    demo.py     the bundled ESCI slice, served exactly the way the study served it
    files.py    JSONL, CSV and Parquet files or directories
    inline.py   records given as text — the console's paste box
    config.py   `sources.yaml`, and the demo pairs that are always available

Only `base` is imported here; the adapters load what they need when used.
"""

from .base import (
    FieldInfo,
    Sample,
    Source,
    SourceError,
    SourcePair,
    SourceSchema,
    to_probe_entry,
)

__all__ = [
    "FieldInfo", "Sample", "Source", "SourceError", "SourcePair", "SourceSchema",
    "to_probe_entry",
]
