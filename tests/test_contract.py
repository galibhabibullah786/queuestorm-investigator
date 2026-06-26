"""Contract tests for the Pydantic schemas.

The response contract is the wire-format contract: every field is
required, every enum is a frozen ``Literal``, and the orchestrator
re-parses its own output before returning. These tests pin that
contract so a downstream regression fails loudly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    CaseType,
    Channel,
    CustomerContext,
    Department,
    EvidenceVerdict,
    Language,
    MatchedTransaction,
    ModelVersion,
    Severity,
    TransactionEntry,
    TxnStatus,
    TxnType,
    UserType,
)

# ---------------------------------------------------------------------------
# Literal adapters (catch typo regressions)
# ---------------------------------------------------------------------------

_LANGUAGE_ADAPTER: TypeAdapter[Language] = TypeAdapter(Language)
_CHANNEL_ADAPTER: TypeAdapter[Channel] = TypeAdapter(Channel)
_USER_TYPE_ADAPTER: TypeAdapter[UserType] = TypeAdapter(UserType)
_TXN_TYPE_ADAPTER: TypeAdapter[TxnType] = TypeAdapter(TxnType)
_TXN_STATUS_ADAPTER: TypeAdapter[TxnStatus] = TypeAdapter(TxnStatus)
_EVIDENCE_ADAPTER: TypeAdapter[EvidenceVerdict] = TypeAdapter(EvidenceVerdict)
_CASE_TYPE_ADAPTER: TypeAdapter[CaseType] = TypeAdapter(CaseType)
_SEVERITY_ADAPTER: TypeAdapter[Severity] = TypeAdapter(Severity)
_DEPARTMENT_ADAPTER: TypeAdapter[Department] = TypeAdapter(Department)
_MODEL_VERSION_ADAPTER: TypeAdapter[ModelVersion] = TypeAdapter(ModelVersion)


@pytest.mark.parametrize(
    "adapter, good_values",
    [
        (_LANGUAGE_ADAPTER, ["en", "bn", "mixed"]),
        (
            _CHANNEL_ADAPTER,
            [
                "in_app_chat",
                "call_center",
                "email",
                "merchant_portal",
                "field_agent",
            ],
        ),
        (_USER_TYPE_ADAPTER, ["customer", "merchant", "agent", "unknown"]),
        (
            _TXN_TYPE_ADAPTER,
            [
                "transfer",
                "payment",
                "cash_in",
                "cash_out",
                "settlement",
                "refund",
            ],
        ),
        (_TXN_STATUS_ADAPTER, ["completed", "failed", "pending", "reversed"]),
        (_EVIDENCE_ADAPTER, ["consistent", "inconsistent", "insufficient_data"]),
        (
            _CASE_TYPE_ADAPTER,
            [
                "wrong_transfer",
                "payment_failed",
                "refund_request",
                "duplicate_payment",
                "merchant_settlement_delay",
                "agent_cash_in_issue",
                "phishing_or_social_engineering",
                "other",
            ],
        ),
        (_SEVERITY_ADAPTER, ["low", "medium", "high", "critical"]),
        (
            _DEPARTMENT_ADAPTER,
            [
                "customer_support",
                "dispute_resolution",
                "payments_ops",
                "merchant_operations",
                "agent_operations",
                "fraud_risk",
            ],
        ),
        (_MODEL_VERSION_ADAPTER, ["1.0.0"]),
    ],
)
def test_literal_adapters_accept_canonical_values(
    adapter: TypeAdapter[Any],
    good_values: list[str],
) -> None:
    for value in good_values:
        assert adapter.validate_python(value) == value


@pytest.mark.parametrize(
    "adapter, bad_value",
    [
        (_LANGUAGE_ADAPTER, "fr"),
        (_CHANNEL_ADAPTER, "telegram"),
        (_USER_TYPE_ADAPTER, "admin"),
        (_TXN_TYPE_ADAPTER, "withdrawal"),
        (_TXN_STATUS_ADAPTER, "cancelled"),
        (_EVIDENCE_ADAPTER, "unknown"),
        (_CASE_TYPE_ADAPTER, "fraud"),
        (_SEVERITY_ADAPTER, "extreme"),
        (_DEPARTMENT_ADAPTER, "legal"),
        (_MODEL_VERSION_ADAPTER, "0.9.0"),
    ],
)
def test_literal_adapters_reject_unknown_values(
    adapter: TypeAdapter[Any],
    bad_value: str,
) -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python(bad_value)


# ---------------------------------------------------------------------------
# Request: TransactionEntry
# ---------------------------------------------------------------------------


def _valid_entry(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "transaction_id": "TXN-0001",
        "timestamp": "2026-06-25T10:15:00+06:00",
        "amount_bdt": 1500,
        "type": "transfer",
        "status": "completed",
        "counterparty": "+8801712345678",
    }
    base.update(overrides)
    return base


def test_transaction_entry_accepts_minimal_valid_payload() -> None:
    entry = TransactionEntry(**_valid_entry())
    assert entry.transaction_id == "TXN-0001"
    assert entry.amount_bdt == 1500
    assert entry.type == "transfer"
    assert entry.status == "completed"
    assert entry.note is None


def test_transaction_entry_rejects_zero_amount() -> None:
    with pytest.raises(ValidationError):
        TransactionEntry(**_valid_entry(amount_bdt=0))


def test_transaction_entry_rejects_negative_amount() -> None:
    with pytest.raises(ValidationError):
        TransactionEntry(**_valid_entry(amount_bdt=-100))


def test_transaction_entry_rejects_amount_above_ceiling() -> None:
    with pytest.raises(ValidationError):
        TransactionEntry(**_valid_entry(amount_bdt=10_000_001))


def test_transaction_entry_accepts_amount_boundaries() -> None:
    TransactionEntry(**_valid_entry(amount_bdt=1))
    TransactionEntry(**_valid_entry(amount_bdt=10_000_000))


def test_transaction_entry_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        TransactionEntry(**_valid_entry(timestamp="2026-06-25T10:15:00"))


def test_transaction_entry_accepts_utc_timestamp() -> None:
    entry = TransactionEntry(**_valid_entry(timestamp="2026-06-25T04:15:00+00:00"))
    assert entry.timestamp.startswith("2026-06-25")


@pytest.mark.parametrize(
    "counterparty",
    [
        "+8801712345678",  # BD E.164
        "8801712345678",  # E.164 without +
        "+14155552671",  # US E.164
        "01712345678",  # local BD
        "merchant_42",  # merchant ID
        "agent-007",  # agent ID
    ],
)
def test_transaction_entry_accepts_valid_counterparty(counterparty: str) -> None:
    entry = TransactionEntry(**_valid_entry(counterparty=counterparty))
    assert entry.counterparty == counterparty


@pytest.mark.parametrize(
    "counterparty",
    [
        "",  # empty
        "not a phone",  # whitespace
        "merchant 42",  # internal whitespace
        "x" * 65,  # too long
        "merchant\t42",  # tab in ID
    ],
)
def test_transaction_entry_rejects_invalid_counterparty(counterparty: str) -> None:
    with pytest.raises(ValidationError):
        TransactionEntry(**_valid_entry(counterparty=counterparty))


def test_transaction_entry_is_frozen() -> None:
    entry = TransactionEntry(**_valid_entry())
    with pytest.raises(ValidationError):
        entry.amount_bdt = 2000  # type: ignore[misc]


def test_transaction_entry_ignores_unknown_fields() -> None:
    # Per design: requests are permissive (``extra="ignore"``).
    entry = TransactionEntry(**_valid_entry(unexpected_field="ignored"))
    assert not hasattr(entry, "unexpected_field")


# ---------------------------------------------------------------------------
# Request: CustomerContext
# ---------------------------------------------------------------------------


def test_customer_context_defaults_are_documented() -> None:
    ctx = CustomerContext()
    assert ctx.user_type == "unknown"
    assert ctx.channel == "in_app_chat"
    assert ctx.language_hint is None


def test_customer_context_is_frozen() -> None:
    ctx = CustomerContext(user_type="customer")
    with pytest.raises(ValidationError):
        ctx.user_type = "merchant"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Request: AnalyzeRequest
# ---------------------------------------------------------------------------


def test_analyze_request_accepts_minimal_payload() -> None:
    req = AnalyzeRequest(complaint="I sent money to the wrong number.")
    assert req.complaint.startswith("I sent money")
    assert req.customer_context is None
    assert req.transaction_history == []


def test_analyze_request_rejects_empty_complaint() -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest(complaint="")


def test_analyze_request_rejects_whitespace_only_complaint() -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest(complaint="\n\t  \n")


def test_analyze_request_strips_control_chars_but_keeps_layout() -> None:
    req = AnalyzeRequest(complaint="hello\x00world\nnew line\twith tab")
    assert "\x00" not in req.complaint
    assert "\n" in req.complaint
    assert "\t" in req.complaint


def test_analyze_request_rejects_oversized_complaint() -> None:
    huge = "x" * (8 * 1024 + 1)
    with pytest.raises(ValidationError):
        AnalyzeRequest(complaint=huge)


def test_analyze_request_rejects_too_many_transactions() -> None:
    history = [TransactionEntry(**_valid_entry(transaction_id=f"TXN-{i:04d}")) for i in range(51)]
    with pytest.raises(ValidationError):
        AnalyzeRequest(complaint="anything", transaction_history=history)


def test_analyze_request_round_trips_via_dict() -> None:
    payload: dict[str, Any] = {
        "complaint": "আমি ভুল নম্বরে টাকা পাঠিয়েছি",
        "customer_context": {
            "user_type": "customer",
            "channel": "call_center",
            "language_hint": "bn",
        },
        "transaction_history": [_valid_entry()],
    }
    req = AnalyzeRequest(**payload)
    dumped = req.model_dump()
    rebuilt = AnalyzeRequest(**dumped)
    assert rebuilt == req


# ---------------------------------------------------------------------------
# Response: AnalyzeResponse and MatchedTransaction
# ---------------------------------------------------------------------------


def _valid_response(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "case_type": "wrong_transfer",
        "evidence_verdict": "consistent",
        "severity": "medium",
        "department": "dispute_resolution",
        "relevant_transaction_id": "TXN-0001",
        "relevant_transaction": {
            "transaction_id": "TXN-0001",
            "timestamp": "2026-06-25T10:15:00+06:00",
            "amount_bdt": 1500,
            "type": "transfer",
            "status": "completed",
        },
        "human_review_required": False,
        "agent_summary": "Customer reports a wrong-number transfer of 1500 BDT.",
        "recommended_next_action": "Verify the recipient and initiate dispute.",
        "customer_reply": "We are reviewing your transfer and will follow up.",
        "model_version": "1.0.0",
    }
    base.update(overrides)
    return base


def test_analyze_response_accepts_minimal_payload() -> None:
    resp = AnalyzeResponse(**_valid_response())
    assert resp.model_version == "1.0.0"
    assert resp.case_type == "wrong_transfer"


def test_analyze_response_rejects_extra_fields() -> None:
    payload = _valid_response(unexpected_field="nope")
    with pytest.raises(ValidationError):
        AnalyzeResponse(**payload)


def test_analyze_response_is_frozen() -> None:
    resp = AnalyzeResponse(**_valid_response())
    with pytest.raises(ValidationError):
        resp.severity = "low"  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    [
        "case_type",
        "evidence_verdict",
        "severity",
        "department",
        "relevant_transaction_id",
        "relevant_transaction",
        "human_review_required",
        "agent_summary",
        "recommended_next_action",
        "customer_reply",
    ],
)
def test_analyze_response_requires_all_fields(field: str) -> None:
    # ``model_version`` has a default and is therefore not "required"
    # in the strict sense; the schema-pinning test below asserts its
    # value is always ``"1.0.0"``.
    payload = _valid_response()
    payload.pop(field)
    with pytest.raises(ValidationError):
        AnalyzeResponse(**payload)


def test_analyze_response_self_validates_via_model_validate() -> None:
    """The orchestrator's self-validation step is re-parse round-trip."""
    resp = AnalyzeResponse(**_valid_response())
    raw = resp.model_dump()
    again = AnalyzeResponse.model_validate(raw)
    assert again == resp


def test_matched_transaction_rejects_extra_fields() -> None:
    payload = {
        "transaction_id": "TXN-0001",
        "timestamp": "2026-06-25T10:15:00+06:00",
        "amount_bdt": 1500,
        "type": "transfer",
        "status": "completed",
        "extra": "nope",
    }
    with pytest.raises(ValidationError):
        MatchedTransaction(**payload)


def test_analyze_response_accepts_null_relevant_fields() -> None:
    payload = _valid_response(
        relevant_transaction_id=None,
        relevant_transaction=None,
        case_type="phishing_or_social_engineering",
        severity="critical",
        department="fraud_risk",
        evidence_verdict="insufficient_data",
        human_review_required=True,
    )
    resp = AnalyzeResponse(**payload)
    assert resp.relevant_transaction_id is None
    assert resp.relevant_transaction is None


# ---------------------------------------------------------------------------
# End-to-end: a realistic sample request validates
# ---------------------------------------------------------------------------


def test_realistic_sample_request_validates() -> None:
    now = datetime.now(tz=UTC).isoformat()
    payload: dict[str, Any] = {
        "complaint": ("আমি গতকাল ৫০০০ টাকা ভুল নাম্বারে পাঠিয়েছি। Please help me get the money back."),
        "customer_context": {
            "user_type": "customer",
            "channel": "in_app_chat",
            "language_hint": "mixed",
        },
        "transaction_history": [
            {
                "transaction_id": "TXN-2026-0001",
                "timestamp": now,
                "amount_bdt": 5000,
                "type": "transfer",
                "status": "completed",
                "counterparty": "+8801712345678",
                "note": "user says wrong number",
            },
            {
                "transaction_id": "TXN-2026-0002",
                "timestamp": now,
                "amount_bdt": 250,
                "type": "cash_in",
                "status": "completed",
                "counterparty": "agent-007",
            },
        ],
    }
    req = AnalyzeRequest(**payload)
    assert len(req.transaction_history) == 2
    assert req.customer_context is not None
    assert req.customer_context.user_type == "customer"
