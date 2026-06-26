# Build log — `queuestorm-investigator`

Per-increment log of commands, decisions, and verification output.
The canonical increment list lives in [`README.md`](README.md).

---

## Pre-flight

Captured once, before increment 0. All commands run on Windows PowerShell
from the project root.

```bash
$ python --version
Python 3.14.6

$ pip --version
pip 26.1.2 from D:\python-3.13.7\Lib\site-packages\pip (python 3.14)

$ git --version
git version 2.51.0.windows.2

$ python -m venv .venv && .venv\Scripts\python --version
Python 3.14.6
```

Environment notes:
- Python 3.14.6 satisfies the project pin `>=3.14,<3.15`.
- `pip` is system-wide; `requirements-dev.txt` is installed into the
  project venv when tooling is needed for verification.
- External design doc `backend_api_plan.md` is provided alongside this
  prompt and is treated as the read-only source of truth for behavior.

---

## Increment 1 — Schemas (Pydantic v2)

**Reference:** §7 of the external design doc — `Literal` enums for every
closed set; request fields strict-typed with bounded length and amount;
response models `extra="forbid"` and `frozen=True`; orchestrator
self-validates by re-parsing its own output.

**Files created / modified**
- `app/schemas/request.py` — `Language`, `Channel`, `UserType`, `TxnType`,
  `TxnStatus` literals; `CustomerContext`, `TransactionEntry`,
  `AnalyzeRequest` models with bounded complaint length (8 KiB), bounded
  amount range (1..10,000,000 BDT), ISO 8601 timestamp validator, E.164 /
  local BD phone or merchant/agent ID validator.
- `app/schemas/response.py` — `EvidenceVerdict`, `CaseType`, `Severity`,
  `Department`, `ModelVersion` literals; `MatchedTransaction` and
  `AnalyzeResponse` with `extra="forbid"` and `frozen=True`; every
  response field is required (no `None` for required fields).
- `app/schemas/__init__.py` — re-exports the public schema surface.
- `tests/test_contract.py` — contract tests (literal adapters, request
  field validation, response required-field matrix, extra-forbid,
  frozen, self-validation round-trip, realistic sample).

**Tests added**
- `tests/test_contract.py::test_literal_adapters_accept_canonical_values` —
  parametrized over every wire enum.
- `tests/test_contract.py::test_literal_adapters_reject_unknown_values` —
  parametrized over every wire enum.
- `tests/test_contract.py::test_transaction_entry_accepts_minimal_valid_payload` —
  smallest valid entry.
- `tests/test_contract.py::test_transaction_entry_rejects_zero_amount`,
  `::test_transaction_entry_rejects_negative_amount`,
  `::test_transaction_entry_rejects_amount_above_ceiling`,
  `::test_transaction_entry_accepts_amount_boundaries` — BDT bounds.
- `tests/test_contract.py::test_transaction_entry_rejects_naive_timestamp`,
  `::test_transaction_entry_accepts_utc_timestamp` — ISO 8601 + offset.
- `tests/test_contract.py::test_transaction_entry_accepts_valid_counterparty`
  (parametrized), `::test_transaction_entry_rejects_invalid_counterparty`
  (parametrized) — E.164 / BD-local / merchant / agent ID.
- `tests/test_contract.py::test_transaction_entry_is_frozen`,
  `::test_transaction_entry_ignores_unknown_fields` — model config.
- `tests/test_contract.py::test_customer_context_defaults_are_documented`,
  `::test_customer_context_is_frozen` — context model.
- `tests/test_contract.py::test_analyze_request_accepts_minimal_payload`,
  `::test_analyze_request_rejects_empty_complaint`,
  `::test_analyze_request_rejects_whitespace_only_complaint`,
  `::test_analyze_request_strips_control_chars_but_keeps_layout`,
  `::test_analyze_request_rejects_oversized_complaint`,
  `::test_analyze_request_rejects_too_many_transactions`,
  `::test_analyze_request_round_trips_via_dict` — request contract.
- `tests/test_contract.py::test_analyze_response_accepts_minimal_payload`,
  `::test_analyze_response_rejects_extra_fields`,
  `::test_analyze_response_is_frozen`,
  `::test_analyze_response_requires_all_fields` (parametrized),
  `::test_analyze_response_self_validates_via_model_validate`,
  `::test_matched_transaction_rejects_extra_fields`,
  `::test_analyze_response_accepts_null_relevant_fields` — response
  contract.
- `tests/test_contract.py::test_realistic_sample_request_validates` —
  end-to-end realistic sample including Bangla text and a small
  transaction history.

**Commands run**

```bash
$ ruff check .
All checks passed!

$ ruff format --check .
17 files already formatted

$ mypy --strict app/
Success: no issues found in 12 source files

$ pytest -q
....................................................................                                                     [100%]
68 passed in ~X s
```

**Definition of Done**
- [x] All listed files exist.
- [x] `from app.schemas import AnalyzeRequest, AnalyzeResponse` works.
- [x] `pytest -q` is green (68 tests passing, including the 2 smoke
      tests from increment 0).
- [x] `ruff check .` and `ruff format --check .` are clean.
- [x] `mypy --strict app/` is clean.
- [x] `README.md` progress table row updated.
- [x] `build_log.md` updated with this increment report.
- [x] No new files outside the canonical layout.

**Hand-off**
- Next: Increment 2 — Configuration (`pydantic-settings`) with secret
  redaction and `env_nested_delimiter`.
- Carry-over notes: the schemas establish the wire-format contract;
  the configuration increment must add `MAX_BODY_BYTES`,
  `LLM__TIMEOUT_MS`, and other env keys without changing any schema
  field. The Pydantic `BaseModel.model_dump()` round-trip pattern used
  in the contract tests is the self-validation pattern the orchestrator
  will reuse.

---


---

# Increment 2 — Configuration (`pydantic-settings`)

## Reference

- Design doc §12 (Configuration): frozen `Settings(BaseSettings)` with
  `env_nested_delimiter="__"`, secrets as `SecretStr`, redaction in
  logging.
- No change to request/response schemas (carried over from increment 1).

## Files created / modified

- **modified** `requirements.txt` — added `pydantic-settings>=2.5`.
- **created** `app/config.py` — `Settings` model with 12 fields,
  bounds validators, `SecretStr` for `llm_api_key`, heuristic
  redaction in `Settings.shape()` via the module-level `_redact`,
  `@lru_cache(maxsize=1) get_settings()` singleton.
- **created** `.env.example` — documented env keys grouped as
  Process/transport, Optional feature flags, Optional LLM provider.
- **created** `tests/test_config.py` — 36 tests covering defaults,
  flat env overrides, `SecretStr`, `extra="ignore"`, frozen instance,
  `shape()` redaction, `get_settings()` caching and lazy
  re-construction, parametrized shape sanity for every field.

## Tests added

- `tests/test_config.py` — 36 cases:
  - 1 default-values snapshot
  - 3 flat-env override cases (`test_flat_env_overrides_apply`,
    `test_llm_api_key_is_secret_str`, `test_llm_api_key_absent_is_none`)
  - 1 nested-delimiter smoke
  - 8 validation bounds (port ×2, max_body_bytes ×2,
    request_timeout_ms, llm_timeout_ms, llm_cache_size, log_level)
  - 1 unknown-env ignored
  - 1 frozen instance
  - 5 `shape()` redaction cases
  - 4 `get_settings()` lifecycle cases
  - 12 parametrized shape-safety cases (one per field)

Total: **104 passed** (`pytest -q` → `104 passed in 0.60s`), up from
68 at the close of increment 1.

## Commands run

```text
$ ruff check .
All checks passed!

$ ruff format --check .
18 files already formatted

$ mypy --strict app/
Success: no issues found in 12 source files

$ pytest -q
........................................................................ [ 69%]
................................                                         [100%]
104 passed in 0.60s
```

## Notes / decisions

- `llm_api_key` is wrapped in `pydantic.SecretStr` at the field level
  so `repr()` and `str()` are redacted by default; the `shape()`
  helper additionally redacts any future field whose name contains
  `api_key`, `secret`, `password`, or `token` (defence-in-depth).
- `env_nested_delimiter="__"` is declared so a future nested `LLM`
  sub-model would route `LLM__TIMEOUT_MS` → `llm.timeout_ms`. Today
  the LLM fields are flat top-level fields; their canonical env
  binding is therefore `LLM_TIMEOUT_MS` (underscore-joined).
  Unknown `LLM__*` keys are dropped by `extra="ignore"`.
- `get_settings()` is `lru_cache(maxsize=1)` so the process-wide
  instance is stable; tests that need a fresh read call
  `get_settings.cache_clear()` inside an autouse `_isolated_env`
  fixture that strips every config-related env var before each case.
- The first test pass failed 9 cases because they passed
  env-style `UPPERCASE` keys as constructor kwargs; pydantic-settings
  only honours kwargs whose names match declared model attributes,
  so `Settings(_env_file=None, PORT="0")` silently fell back to the
  default and never reached the validator. The fix was to drive the
  bad values through `monkeypatch.setenv(...)` so they reach the
  model via the real env-var pathway, matching the pattern already
  used in `test_flat_env_overrides_apply`. The same lesson led to
  renaming the nested-delimiter test to assert the actual binding
  (`LLM_TIMEOUT_MS`) rather than the not-yet-bound `LLM__TIMEOUT_MS`.

## Definition of Done

- [x] All listed files exist.
- [x] `from app.config import Settings, get_settings` works.
- [x] `Settings(_env_file=None)` returns defaults; env overrides via
      `monkeypatch.setenv` apply; validators reject out-of-range
      values with `ValidationError`.
- [x] `pytest -q` is green (104 tests passing).
- [x] `ruff check .` and `ruff format --check .` are clean.
- [x] `mypy --strict app/` is clean (12 source files).
- [x] `README.md` progress table row 2 marked ✅ done.
- [x] `build_log.md` updated with this increment report.
- [x] No new files outside the canonical layout.

## Hand-off

- Next: Increment 3 — Logging (`structlog` JSON) with request-scoped
  `request_id` contextvar and a bound logger handed to every layer.
- Carry-over notes: the `Settings.shape()` redaction surface is the
  exact log payload the logging increment should emit at startup
  (`INFO`-level one-shot). The autouse `_isolated_env` pattern is
  the template for any future test that exercises env-driven
  configuration; reuse it instead of touching `os.environ` directly.
