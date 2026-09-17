"""Spend caps in the request path: checked before the call, not around it.

A hosted answer costs real money, and the failure mode to design against is not
one expensive question — it is a loop that asks a thousand. So every hosted call
passes a `Budget` first: the projected cost of *this* call is added to what the
session and the day have already spent, and if either ceiling would be crossed
the call does not happen and the refusal says by how much.

Two ceilings, because they fail differently:

    session   this process, this run of `airs analyst` — a runaway loop
    day       every session today, persisted in ~/.airs/spend.json — a runaway week

The day file lives in the user's directory, never in `results/runs/`: live traffic
is quarantined from the corpus (invariant 7, brief correction 9). It records only
dates, models and totals — never a key, a question or a record.

Local models never consult a budget: nothing is billed for them, which is exactly
why `llm.py` leaves them out of `PRICING`. An unpriced *hosted* model is refused by
`require_price` before it reaches here, so a cap is never applied to a cost the
tool cannot compute.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from ..agents.llm import is_local_model, require_price

SPEND_FILE = Path.home() / ".airs" / "spend.json"
DEFAULT_SESSION_USD = 0.50
DEFAULT_DAY_USD = 2.00


def usd(amount: float) -> str:
    """Money, at a precision that does not round a real cap away to $0.00."""
    return f"${amount:.4f}" if 0 < amount < 0.01 else f"${amount:.2f}"


class SpendRefused(RuntimeError):
    """A call that would cross a ceiling. Nothing was sent, nothing was spent."""


def cost_of(model: str, input_tokens: int, output_tokens: int) -> float:
    """What these tokens cost on this model. 0.0 for a local one; refuses unpriced."""
    price = require_price(model)
    if price is None:
        return 0.0
    return input_tokens * price["input"] + output_tokens * price["output"]


@dataclass
class DayLedger:
    """Today's hosted spend, across sessions. JSON, one date at a time."""

    path: Path = SPEND_FILE
    today: Callable[[], str] = lambda: date.today().isoformat()

    def _read(self) -> dict[str, Any]:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return document if isinstance(document, dict) else {}

    def spent(self) -> float:
        day = self._read().get(self.today())
        return float(day.get("usd", 0.0)) if isinstance(day, dict) else 0.0

    def add(self, model: str, charge: float) -> float:
        """Record spend and return the new day total. Never raises on a bad file."""
        document = self._read()
        day = document.get(self.today())
        if not isinstance(day, dict):
            day = {"usd": 0.0, "models": {}}
        day["usd"] = round(float(day.get("usd", 0.0)) + charge, 8)
        models = day.get("models")
        day["models"] = models if isinstance(models, dict) else {}
        day["models"][model] = round(float(day["models"].get(model, 0.0)) + charge, 8)
        # Only the last 30 days: this is a ceiling, not an accounting record.
        document[self.today()] = day
        document = dict(sorted(document.items())[-30:])
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass  # a cap that cannot persist still holds for this session
        return day["usd"]


@dataclass
class Budget:
    """Ceilings for one session, and for the day it runs in."""

    session_usd: float = DEFAULT_SESSION_USD
    day_usd: float = DEFAULT_DAY_USD
    ledger: DayLedger = field(default_factory=DayLedger)
    spent_usd: float = 0.0
    calls: int = 0

    def check(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """The projected cost of this call, or `SpendRefused` before it is made."""
        projected = cost_of(model, input_tokens, output_tokens)
        if projected <= 0.0:
            return 0.0
        session_after = self.spent_usd + projected
        if session_after > self.session_usd:
            raise SpendRefused(
                f"refused before calling {model}: this question costs about "
                f"{usd(projected)}, which would take the session to "
                f"{usd(session_after)} against a {usd(self.session_usd)} cap. "
                f"Raise it with --max-cost, or answer with a local model "
                f"(--answerer ollama/<name>, $0)")
        day_after = self.ledger.spent() + projected
        if day_after > self.day_usd:
            raise SpendRefused(
                f"refused before calling {model}: today's hosted spend is "
                f"{usd(self.ledger.spent())} and this question would take it to "
                f"{usd(day_after)}, against a {usd(self.day_usd)} daily cap "
                f"({self.ledger.path}). Raise it with --max-cost-day, or use a "
                f"local model ($0)")
        return projected

    def record(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Charge what the call actually used — the estimate is never the bill."""
        charge = cost_of(model, input_tokens, output_tokens)
        self.calls += 1
        if charge <= 0.0:
            return 0.0
        self.spent_usd = round(self.spent_usd + charge, 8)
        self.ledger.add(model, charge)
        return charge

    def remaining(self) -> dict[str, float]:
        return {"session": round(self.session_usd - self.spent_usd, 6),
                "day": round(self.day_usd - self.ledger.spent(), 6)}

    def to_dict(self, model: str | None = None) -> dict[str, Any]:
        free = model is not None and is_local_model(model)
        return {
            "session_cap_usd": self.session_usd,
            "day_cap_usd": self.day_usd,
            "session_spent_usd": self.spent_usd,
            "day_spent_usd": self.ledger.spent(),
            "calls": self.calls,
            "free": free,
        }
