"""Pydantic request models for the analysis endpoint.

Wire enums are frozen ``Literal`` types per the API contract. All
response enums live in :mod:`app.schemas.response` and re-export the
same literals for clarity.

The request models are intentionally permissive at the type level
(``extra="ignore"``) because the public endpoint may receive fields we
do not yet understand; the response models are strict
(``extra="forbid"``, ``frozen=True``) so we never accidentally return
fields the contract does not allow.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Wire enums (frozen literals)
# ---------------------------------------------------------------------------

Language = Literal["en", "bn", "mixed"]
"""Detected language of the complaint text."""

Channel = Literal[
    "in_app_chat",
    "call_center",
    "email",
    "merchant_portal",
    "field_agent",
]
"""Originating channel for the complaint."""

UserType = Literal["customer", "merchant", "agent", "unknown"]
"""Role of the complaining user."""

TxnType = Literal[
    "transfer",
    "payment",
    "cash_in",
    "cash_out",
    "settlement",
    "refund",
]
"""Type of a transaction in the customer's history."""

TxnStatus = Literal["completed", "failed", "pending", "reversed"]
"""Status of a transaction in the customer's history."""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ISO 8601 with a timezone offset (``+00:00`` style). The default
# ``datetime`` parser already accepts this; we narrow it here for
# documentation and to reject naive timestamps.

_MAX_COMPLAINT_CHARS = 8 * 1024
"""Maximum length of the free-text complaint (8 KiB) per §15.1."""

_MAX_TRANSACTION_HISTORY = 50
"""Hard cap on transaction entries per request to bound match work."""

_MIN_AMOUNT_BDT = 1
"""Smallest valid BDT amount; zero-amount rows are rejected."""

_MAX_AMOUNT_BDT = 10_000_000
"""Largest valid BDT amount; 1 crore ceiling per §15.1."""

# E.164: leading ``+`` then 8-15 digits. We accept the common local
# ``01xxxxxxxxx`` form as a courtesy for Bangladeshi numbers.
_E164_PATTERN = r"^\+?[1-9]\d{7,14}$"
_LOCAL_BD_PATTERN = r"^01[3-9]\d{8}$"


def _is_valid_counterparty(value: str) -> bool:
    """Return ``True`` if ``value`` is a phone number or a non-empty ID."""
    import re

    if not value:
        return False
    stripped = value.strip()
    if re.match(_E164_PATTERN, stripped):
        return True
    if re.match(_LOCAL_BD_PATTERN, stripped):
        return True
    # Non-phone counterparty: merchant or agent ID. Must be 1-64 chars,
    # no whitespace, no control characters.
    return not (len(stripped) > 64 or any(ch.isspace() or ord(ch) < 0x20 for ch in stripped))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CustomerContext(BaseModel):
    """Optional metadata about the complaining user."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    user_type: UserType = "unknown"
    """Role of the user submitting the complaint."""

    channel: Channel = "in_app_chat"
    """Channel that received the complaint."""

    language_hint: Language | None = None
    """Optional explicit language hint; the reasoning pipeline may
    re-detect and override this."""


class TransactionEntry(BaseModel):
    """A single transaction in the customer's recent history."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    transaction_id: str = Field(min_length=1, max_length=64)
    """Stable identifier for the transaction (opaque string)."""

    timestamp: str = Field(min_length=10, max_length=40)
    """ISO 8601 timestamp string with timezone offset.

    Stored as a string (not ``datetime``) so the model is JSON-friendly
    and timezone-aware at parse time without leaking ``datetime``
    quirks through the public schema."""

    amount_bdt: int = Field(ge=_MIN_AMOUNT_BDT, le=_MAX_AMOUNT_BDT)
    """Amount in BDT, integer-only (no decimals) per §7.1."""

    type: TxnType
    """Type of transaction."""

    status: TxnStatus
    """Status of the transaction."""

    counterparty: str = Field(min_length=1, max_length=64)
    """Counterparty phone (E.164 or local BD) or merchant/agent ID."""

    note: str | None = Field(default=None, max_length=512)
    """Optional free-text note attached by the upstream system."""

    @field_validator("timestamp")
    @classmethod
    def _validate_timestamp(cls, value: str) -> str:
        """Reject naive timestamps; require a timezone offset."""
        # ``datetime.fromisoformat`` in 3.11+ accepts ``+00:00`` style.
        from datetime import datetime

        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("timestamp must include a timezone offset")
        return value

    @field_validator("counterparty")
    @classmethod
    def _validate_counterparty(cls, value: str) -> str:
        if not _is_valid_counterparty(value):
            raise ValueError("counterparty must be a phone number or a non-empty ID")
        return value


class AnalyzeRequest(BaseModel):
    """Body of ``POST /analyze-ticket``."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    complaint: str = Field(min_length=1, max_length=_MAX_COMPLAINT_CHARS)
    """Free-text complaint from the user. 1 byte to 8 KiB."""

    customer_context: CustomerContext | None = None
    """Optional metadata about the user."""

    transaction_history: list[TransactionEntry] = Field(
        default_factory=list,
        max_length=_MAX_TRANSACTION_HISTORY,
    )
    """Recent transaction history; default is empty."""

    @field_validator("complaint")
    @classmethod
    def _validate_complaint(cls, value: str) -> str:
        # Strip NULs and other ASCII control characters that some
        # upstream clients leak. Whitespace-only complaints are
        # rejected by ``min_length=1`` once stripped.
        cleaned = "".join(ch for ch in value if ord(ch) >= 0x20 or ch in "\n\r\t")
        if not cleaned.strip():
            raise ValueError("complaint must contain non-whitespace content")
        return cleaned


__all__ = [
    "AnalyzeRequest",
    "Channel",
    "CustomerContext",
    "Language",
    "TransactionEntry",
    "TxnStatus",
    "TxnType",
    "UserType",
]
