"""agentic_faults — record-level fault injection for agentic AI benchmarks.

The technical core of the thesis "Characterizing the Data Infrastructure
Gap for Agentic AI Systems". Four composable injectors cover the four
AIRS dimensions:

- FreshnessInjector          -> freshness (staleness)
- LatencyInjector            -> latency (delivery delay)
- SchemaDriftInjector        -> consistency (schema/value drift)
- SemanticStrippingInjector  -> semantic completeness (meaning removal)

Unlike chaos-engineering tools (Toxiproxy, Chaos Mesh), these operate on
individual records, enabling semantic-level manipulation.
"""

from .base import FaultChain, FaultInjector, Record
from .freshness import FreshnessInjector
from .latency import LatencyInjector
from .schema_drift import SchemaDriftInjector
from .semantic_stripping import SemanticStrippingInjector
from .verification import VerificationResult, verify_freshness, verify_latency

__version__ = "0.1.0"

__all__ = [
    "FaultChain",
    "FaultInjector",
    "FreshnessInjector",
    "LatencyInjector",
    "Record",
    "SchemaDriftInjector",
    "SemanticStrippingInjector",
    "VerificationResult",
    "verify_freshness",
    "verify_latency",
]
