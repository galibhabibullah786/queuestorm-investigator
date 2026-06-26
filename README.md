# queuestorm-investigator

A production-grade backend API for digital-finance support agents.
A deterministic, rule-based complaint investigator that turns a free-text
complaint, customer context, and a small transaction history into a
structured verdict, classification, routing decision, and language-aware
reply text.

- **Language:** Python 3.14
- **Framework:** FastAPI + Uvicorn
- **Validation:** Pydantic v2 (strict, frozen `Literal` enums)
- **Tests:** `pytest`, `pytest-asyncio`, `httpx`
- **Lint/format:** `ruff`
- **Type check:** `mypy --strict`
- **License:** MIT

The service is stateless — no database, no broker, no sidecar. An optional
LLM adapter is feature-flagged off by default and may only rephrase the
`agent_summary` and `customer_reply` strings; it never decides routing,
verdict, classification, or safety.

---

## Overview

`POST /analyze-ticket` accepts a single complaint, normalises language and
amounts, scores the customer's transaction history, derives a verdict and
case type, routes to a department with a severity, and returns three text
fields (`agent_summary`, `recommended_next_action`, `customer_reply`) in the
same language as the complaint. A built-in safety layer enforces hard
prohibitions — no PINs, OTPs, credentials, refund promises, external phone
numbers, or URLs in any output, ever.

`GET /health` is a liveness probe. `GET /metrics` is a Prometheus
exposition, gated by config.

---

## API at a glance

| Method | Path              | Purpose                      | Notes                       |
|--------|-------------------|------------------------------|-----------------------------|
| GET    | `/health`         | Liveness/readiness           | `< 50 ms`                   |
| POST   | `/analyze-ticket` | Single-ticket analysis       | `< 2 s` typical, 30 s hard  |
| GET    | `/metrics`        | Prometheus exposition        | Optional, gated by config   |

All responses are `application/json; charset=utf-8`. No auth, no cookies,
no sessions.

A full request/response sample is generated under `samples/` from a public
sample case.

---

## Project progress

The project is built in small, test-gated increments. The canonical list
lives in this file; a per-increment log of commands, decisions, and
verification output lives in [`build_log.md`](build_log.md).

| #  | Increment                                  | Status     | Tests | Notes |
|----|--------------------------------------------|------------|-------|-------|
| 0  | Project skeleton + toolchain               | ✅ done    | 2/2   | `create_app()` factory; `ruff`, `mypy --strict`, `pytest` wired |
| 1  | Schemas (Pydantic v2)                      | ✅ done    | 68/68 | Frozen `Literal` enums for request/response; contract tests |
| 2  | Configuration (`pydantic-settings`)        | ✅ done    | 36/36 | Frozen `Settings`, `SecretStr` for LLM key, `shape()` redaction |
| 3  | Logging (`structlog` JSON)                 | ✅ done    | [`build_log.md` §Increment 3](build_log.md#increment-3--logging-structlog-json) | Request-scoped `request_id` contextvar |
| 4  | Errors (typed exceptions + handler)        | ⏳ pending | —     | Bounded error envelope |
| 5  | Safety layer (pure regex)                  | ⏳ pending | —     | Phishing override, credential/PII rewrite |
| 6  | Normalize (text, amounts, time, language)  | ⏳ pending | —     | Bangla/Banglish digit handling |
| 7  | Match (transaction scoring)                | ⏳ pending | —     | Tie-break rules, deterministic |
| 8  | Classify (verdict, case_type, dept, sev)   | ⏳ pending | —     | Phishing short-circuit |
| 9  | Text generation (rule templates)           | ⏳ pending | —     | Language mirroring, locked phishing text |
| 10 | Orchestrator (composition)                 | ⏳ pending | —     | End-to-end pipeline, self-validating |
| 11 | Transport (FastAPI app + endpoints)        | ⏳ pending | —     | Middleware, headers, exception handler |
| 12 | Optional LLM adapter                       | ⏳ pending | —     | Feature-flagged, rule fallback |
| 13 | Metrics (`prometheus_client`)              | ⏳ pending | —     | `/metrics`, RED counters/histograms |
| 14 | Container (multi-stage Dockerfile)         | ⏳ pending | —     | `< 200 MB`, non-root, `tini` PID 1 |
| 15 | Local dev tooling (`compose`, smoke, load) | ⏳ pending | —     | No external dependencies |
| 16 | CI pipeline (reference workflow)           | ⏳ pending | —     | Lint, typecheck, test, audit, build |
| 17 | Reference Kubernetes manifests             | ⏳ pending | —     | Reference only, not default deploy |
| 18 | Operations + roadmap docs                  | ⏳ pending | —     | SLOs, alerts, runbooks, versioning |

**Status legend:** ⏳ pending · 🚧 in progress · ✅ done · ❌ blocked.

An increment closes only when its tests are written, run, and green,
and `ruff check .`, `ruff format --check .`, `mypy --strict app/`, and
`pytest -q` all pass.

---

## Repository layout

```
.
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app factory
│   ├── config.py            # settings (env-driven)
│   ├── logging.py           # structured logging
│   ├── errors.py            # typed error hierarchy
│   ├── api/                 # HTTP routers
│   ├── schemas/             # Pydantic v2 request/response models
│   ├── core/                # pure-Python reasoning pipeline
│   ├── llm/                 # optional text provider
│   └── util/                # clock, hashing, text helpers
├── tests/                   # pytest suite + shared fixtures
├── deploy/                  # Dockerfile, compose, k8s reference
├── scripts/                 # local dev scripts
├── samples/                 # generated sample outputs
├── docs/                    # SLOs, alerts, runbooks
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── LICENSE
├── CHANGELOG.md
└── build_log.md             # per-increment build log
```

---

## Development

```bash
python -m venv .venv
# Windows
. .venv/Scripts/activate
# Linux / macOS
# . .venv/bin/activate

pip install -r requirements-dev.txt

# Verify
ruff check .
ruff format --check .
mypy --strict app/
pytest -q
```

To run the service locally once the transport layer lands:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
curl -sS 127.0.0.1:8000/health
```

---

## Configuration

Configuration is environment-driven. All keys are declared in `.env.example`
once the configuration increment lands. Secrets are stored as `SecretStr`;
their `repr` is redacted. A missing `.env` is not an error.

---

## Safety guarantees

The service never returns text that contains PINs, OTPs, passwords, CVVs,
card numbers, refund promises, "we have reversed", "account unblocked",
"recovered", external phone numbers, or external URLs. Every text field
runs through a final regex rewrite; the rewrite is idempotent and tested
on a public sample bank.

---

## License

MIT. See [`LICENSE`](LICENSE).
