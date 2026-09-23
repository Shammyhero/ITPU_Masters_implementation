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
    freshness_target_s: float | None = Field(
        None, gt=0, description="the age, in seconds, at which freshness stops scoring 100; "
                                "set it to the source's update cadence (default: the "
                                "calibrated 1s)")


class GateRequest(ScoreRequest):
    policy: dict[str, Any] = Field(description="an admission policy, as in examples/gate/")
    shadow: bool = Field(False, description="report violations but admit the batch")


class ReplayRequest(_Request):
    task: str = Field("retrieval", description="which task's runs to replay the policy over")
    policy: dict[str, Any] = Field(description="an admission policy, as in examples/gate/")


class SessionRequest(_Request):
    """Open a live session. The source is named by its DECLARED id, never a path.

    No credential is ever accepted here: a hosted model is chosen only if its
    provider key is already in the server's environment (`GET /api/models` says
    which are), so no secret travels in a request body (author decision, 19 Sep).
    """

    source: str = Field("inline", description="id of a declared source, from GET "
                                              "/api/sources — or 'inline' with records")
    records: str | None = Field(
        None, description="JSONL: records as your pipeline delivers them. Makes an "
                          "in-memory `inline` source for this session only.")
    upstream: str | None = Field(
        None, description="JSONL: the same records from the system of record. Without "
                          "it, answers cannot be verified and the session says so.")
    answerer: str = Field("literal", description="literal, ollama/<name>, or a hosted "
                                                 "<provider>/<model> whose key is configured")
    policy: dict[str, Any] | None = Field(
        None, description="an admission policy, as in examples/gate/. Absent admits everything.")
    refetch: str = Field("gate", description="who may re-read upstream: gate, agent or off")
    task: str = Field("retrieval", description="calibrated weight profile to apply")
    max_cost: float | None = Field(None, description="USD cap for this session")
    max_cost_day: float | None = Field(None, description="USD cap across today's sessions")
    strip_semantics: bool = Field(
        False, description="run the study's semantic-stripping injector over this "
                           "session's records: context removed, field names made opaque. "
                           "Applied by the server, not by your pipeline; every Tick says so.")


class AskRequest(_Request):
    session_id: str = Field(description="from POST /api/session")
    question: str | None = Field(None, description="wording; needs plan unless the source "
                                                   "has a built-in question")
    plan: dict[str, Any] | None = Field(None, description="the question's checkable plan")
    n: int | None = Field(None, description="records to draw for this question")


class RecommendRequest(_Request):
    """Ask for a policy to start from, priced on the study's runs."""

    task: str = Field("retrieval", description="calibrated weight profile to price against")
    session_id: str | None = Field(
        None, description="an open session, so policies its pipeline could never clear "
                          "are filtered out. The floors themselves never come from it.")
