"""Pydantic response models for the analysis endpoint.

The response contract is strict: ``extra="forbid"`` and ``frozen=True``.
Every field is required (no ``None`` for required fields per §7.1). The
orchestrator self-validates by re-parsing its own output before
returning (§7.3).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.request import TxnStatus, TxnType

# ---------------------------------------------------------------------------
# Wire enums (frozen literals, re-exported for caller convenience)
# ---------------------------------------------------------------------------

EvidenceVerdict = Literal["consistent", "inconsistent", "insufficient_data"]
"""How the transaction evidence lines up with the complaint."""

CaseType = Literal[
    "wrong_transfer",
    "payment_failed",
    "refund_request",
    "duplicate_payment",
    "merchant_settlement_delay",
    "agent_cash_in_issue",
    "phishing_or_social_engineering",
    "other",
]
"""Categorisation of the complaint intent."""

Severity = Literal["low", "medium", "high", "critical"]
"""Operational severity for routing and SLA."""

Department = Literal[
    "customer_support",
    "dispute_resolution",
    "payments_ops",
    "merchant_operations",
    "agent_operations",
    "fraud_risk",
]
"""Department that should pick up the case."""

ModelVersion = Literal["1.0.0"]
"""Schema version of the response. Bumped on breaking changes only."""


# ---------------------------------------------------------------------------
# Matched transaction reference
# ---------------------------------------------------------------------------


class MatchedTransaction(BaseModel):
    """Pointer to the transaction the verdict is about, if any."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    transaction_id: str = Field(min_length=1, max_length=64)
    """Stable identifier for the matched transaction."""

    timestamp: str = Field(min_length=10, max_length=40)
    """ISO 8601 timestamp string with timezone offset."""

    amount_bdt: int = Field(ge=1, le=10_000_000)
    """Amount in BDT, integer-only."""

    type: TxnType
    """Type of the matched transaction."""

    status: TxnStatus
    """Status of the matched transaction."""


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------


class AnalyzeResponse(BaseModel):
    """Body of a successful ``POST /analyze-ticket`` response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_type: CaseType
    """Categorised complaint intent."""

    evidence_verdict: EvidenceVerdict
    """How the evidence lines up with the complaint."""

    severity: Severity
    """Operational severity."""

    department: Department
    """Department that should pick up the case."""

    relevant_transaction_id: str | None
    """Identifier of the transaction the verdict refers to, or ``None``
    when no transaction was matched."""

    relevant_transaction: MatchedTransaction | None
    """Optional structured echo of the matched transaction. ``None``
    when ``relevant_transaction_id`` is ``None``. This is informational
    and does not affect routing; the orchestrator populates both fields
    together so consumers can rely on either."""

    human_review_required: bool
    """Whether a human agent must review this case before action."""

    agent_summary: str = Field(min_length=1, max_length=2000)
    """One- or two-sentence summary for the support agent."""

    recommended_next_action: str = Field(min_length=1, max_length=1000)
    """Short next-step instruction for the agent."""

    customer_reply: str = Field(min_length=1, max_length=2000)
    """Reply to send to the customer, in the complaint's language."""

    model_version: ModelVersion = "1.0.0"
    """Schema version of the response payload."""


__all__ = [
    "AnalyzeResponse",
    "CaseType",
    "Department",
    "EvidenceVerdict",
    "MatchedTransaction",
    "ModelVersion",
    "Severity",
]
