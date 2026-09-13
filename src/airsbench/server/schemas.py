"""Request bodies for the /api routes.

Only requests are modelled. Responses are whatever `probe.score()` and
`Verdict.to_dict()` return — defining their shape a second time here would be
one more copy to drift.

Unknown fields are refused: a typo'd `sourc` must not become a request that
silently scores without its upstream sample.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScoreRequest(_Request):
    task: str = Field("retrieval", description="calibrated weight profile to apply")
    delivered: str = Field(description="JSONL: the records as the pipeline delivers them")
    source: str | None = Field(
        None, description="JSONL: the same records upstream, matched on id. "
                          "Empty or absent leaves consistency unmeasured.")


class GateRequest(ScoreRequest):
    policy: dict[str, Any] = Field(description="an admission policy, as in examples/gate/")
    shadow: bool = Field(False, description="report violations but admit the batch")
