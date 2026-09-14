"""The paste box as a source: records given as text, held in memory.

It touches no file and opens no connection, which is why the console may build
one from a request body — unlike every other source, which must be declared.
The text is the probe's JSONL contract, validated by `probe.parse_records`.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from ..probe import ProbeError, parse_records
from .files import EntrySource, SourceError


class InlineSource(EntrySource):
    def __init__(self, name: str, text: str, *, unique_ids: bool = False,
                 clock: Callable[[], float] = time.time) -> None:
        super().__init__(name, id_field="id", unique_ids=unique_ids, clock=clock)
        self._text = text

    def _read(self) -> list[dict[str, Any]]:
        try:
            return parse_records(self._text, self.name, unique_ids=self.unique_ids)
        except SourceError:
            raise
        except ProbeError as exc:
            raise SourceError(str(exc)) from None
