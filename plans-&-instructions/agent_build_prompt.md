# Agentic Build Prompt — `queuestorm-investigator` Backend

> A modular, increment-gated build prompt for an autonomous coding agent.
> The agent builds the `queuestorm-investigator` backend end-to-end, from
> the smallest unit upward, with tests required at every increment
> transition.

---

## 0. Meta

| Field | Value |
|---|---|
| External design doc | `backend_api_plan.md` — lives outside the remote repo; treat as read-only reference |
| Internal progress | `README.md` (increment table) and `build_log.md` (per-increment log) — both ship with the repo |
| Source of truth for the public API | The schema tests + `README.md` API table |
| Mode | Autonomous, increment-gated |
| Operating principle | The external design doc is the contract for behavior. The repo is the contract for state. Any deviation from the external doc requires explicit user approval. |
| Output target | `app/`, `tests/`, `deploy/`, `scripts/`, `samples/`, plus project root files |
| Test runner | `pytest` |
| Lint/format | `ruff` (lint + format) |
| Type check | `mypy --strict` |
| Python | 3.14 |

### 0.1 Your role

You are a senior backend engineer building a production-grade API. You work
autonomously, increment by increment. You never skip an increment. You never
invent features. You never rename files from the layout in this prompt. You
stop and ask the user only when the external doc is silent or contradictory
on a non-trivial decision, or when the user has explicitly said to pause.

### 0.2 Workspace

Project root: the directory containing this prompt file. All paths below are
relative to that root unless noted otherwise.

### 0.3 Project name

`queuestorm-investigator`. Use this name in:

- `pyproject.toml` `project.name`
- Docker image tag
- Log `service` field
- The `service` Prometheus label

---

## 1. Source-of-truth contract

The external design doc governs behavior; the repo governs state.

Before writing any code in an increment, you must:

1. Re-read the **specific sections** of the external doc that the increment
   refers to. Summarise the relevant requirement in one sentence in the
   increment report.
2. Verify the increment's scope against the canonical layout in §3 and the
   files-locked list of that increment.

You may not:

- Add endpoints, fields, or enum values not in the external doc.
- Change response field names.
- Invent a database, message broker, or external cache.
- Add sidecars, init containers, or service-mesh components.
- Promote the k8s manifests to the default deploy target.
- Mark the LLM path as required or default-on.
- Embed increment numbers, phase numbers, or design-doc section numbers in
  source code comments, docstrings, error messages, log keys, or
  metric names. Source code references the *concept*, not the *plan*.

You may:

- Add internal helper modules under `app/core/` if they keep the public
  API unchanged.
- Add `__init__.py` exports.
- Add fixtures under `tests/fixtures/`.
- Add developer scripts under `scripts/`.

The repo is the source of truth for progress: the increment table in
`README.md` and the per-increment log in `build_log.md` are updated by the
agent at every increment close.

---

## 2. Operating principles

1. **Tests are part of "done".** No increment closes without its tests
   written, run, and passing.
2. **Tests are written alongside code, not after.** In each increment,
   write tests for the public surface immediately after the implementation,
   in the same increment.
3. **One increment at a time.** Do not start the next increment until the
   current increment's Done Criteria are met and the increment transition
   protocol (§4) has been recorded in `build_log.md`.
4. **Show your work.** Every increment report includes the actual commands
   run and their actual output excerpts.
5. **No silent failures.** If a test fails, the increment is **not** done.
   Fix the code or fix the test (with justification), then re-run.
6. **Boring, deterministic, fast.** Match the external doc's principles
   exactly.
7. **Stop on ambiguity.** If the external doc is silent or contradictory,
   stop and ask the user with a structured question.

---

## 3. Increment model (smallest → large)

The build proceeds in 19 increments. Each increment has a single
objective, a fixed set of files, a fixed set of tests, and a Definition of
Done. Increments 1–18 below map one-to-one to the design doc's 19
sections; this prompt does not restate the design content — it states the
mechanics.

| #  | Increment                                  | Files touched                                    | Tests added                 |
|----|--------------------------------------------|--------------------------------------------------|-----------------------------|
| 0  | Project skeleton + toolchain               | root + empty `app/` + smoke test                 | `test_smoke.py`             |
| 1  | Schemas (Pydantic v2)                      | `app/schemas/`                                   | `test_contract.py`          |
| 2  | Configuration (`pydantic-settings`)        | `app/config.py`, `.env.example`                  | `test_config.py`            |
| 3  | Logging (`structlog` JSON)                 | `app/logging.py`, `app/util/clock.py`            | `test_logging.py`           |
| 4  | Errors (typed exceptions + handler)        | `app/errors.py`, `app/main.py`                   | `test_errors.py`            |
| 5  | Safety layer (pure regex)                  | `app/core/safety.py`                             | `test_safety.py`            |
| 6  | Normalize (pure)                           | `app/core/normalize.py`                          | `test_normalize.py`         |
| 7  | Match (pure)                               | `app/core/match.py`                              | `test_match.py`             |
| 8  | Classify (pure)                            | `app/core/classify.py`                           | `test_classify.py`          |
| 9  | Text generation (rules)                    | `app/core/textgen.py`                            | `test_textgen.py`           |
| 10 | Orchestrator (composition)                 | `app/core/orchestrator.py`                       | `test_orchestrator.py`      |
| 11 | Transport (FastAPI app + endpoints)        | `app/main.py`, `app/api/health.py`, `app/api/analyze.py` | `test_health.py`, `test_analyze_endpoint.py` |
| 12 | Optional LLM module                        | `app/llm/`, `app/core/textgen.py`                | `test_llm_*.py`             |
| 13 | Metrics (`prometheus_client`)              | `app/api/metrics.py`                             | `test_metrics.py`           |
| 14 | Container (multi-stage Dockerfile)         | `deploy/Dockerfile`, `.dockerignore`, `scripts/run_local.sh` | `test_container.py` |
| 15 | Local dev tooling                          | `deploy/docker-compose.yml`, `scripts/smoke.sh`, `scripts/load_test.py` | `test_smoke_script.py`, `test_load_test.py` |
| 16 | CI pipeline (reference workflow)           | `.github/workflows/ci.yml`, `.github/dependabot.yml` | `test_ci_workflow.py` |
| 17 | Reference Kubernetes manifests             | `deploy/k8s/`                                    | `test_k8s_manifests.py`     |
| 18 | Operations + roadmap docs                  | `docs/`                                          | `test_docs.py`              |

After completing each increment, mark the row in `README.md`'s
**Project progress** table as ✅ done and note the test count.

---

## 4. Increment transition protocol

For every increment, you must produce an **Increment Report** with the
following structure before moving to the next increment. Append the report
to `build_log.md`; update the `README.md` progress table in the same turn.

```markdown
### Increment N — <Title>

**Reference:** <one-sentence summary of the relevant external-doc requirement>

**Files created / modified**
- `path/to/file.py` — <one-line purpose>

**Tests added**
- `tests/test_X.py::test_y` — <one-line purpose>

**Commands run**
```bash
$ <command>
<actual output excerpt>
```

```bash
$ <command>
<actual output excerpt>
```

**Definition of Done**
- [ ] All checkboxes for the increment are ticked
- [ ] `ruff check . && ruff format --check .` clean
- [ ] `mypy --strict app/` clean
- [ ] `pytest -q` green
- [ ] `README.md` progress table row updated
- [ ] No new files outside the canonical layout

**Hand-off**
- Next: Increment N+1 — <Title>
- Carry-over notes: <any context the next increment needs>
```

If the Increment Report's Done Criteria are not all ticked, **do not**
proceed. Fix and re-run.

---

## 5. Verification protocol (per increment)

Before marking any increment done, run the following in order and paste the
output excerpt into the Increment Report:

1. **Lint + format check**
   ```bash
   ruff check .
   ruff format --check .
   ```
2. **Type check**
   ```bash
   mypy --strict app/
   ```
   If `app/` is not yet populated in the current increment, skip this and
   note it.
3. **Test run** — full suite if `app/` is importable; otherwise the
   increment-specific tests only.
   ```bash
   pytest -q
   ```
4. **Coverage delta** (from the safety increment onward, where `app/core/`
   exists)
   ```bash
   pytest --cov=app --cov-report=term-missing
   ```
   Coverage targets are **not** enforced until the final increment. Each
   increment must not decrease coverage.

If any command fails, the increment is not done. Diagnose, fix, re-run.

---

## 6. Reporting protocol

At the **end of every increment**, output to the user:

1. The full Increment Report markdown (per §4) — also appended to
   `build_log.md` and reflected in `README.md`.
2. A one-line summary: "Increment N complete. Next: Increment N+1 —
   <Title>. Proceeding." (or "Pausing for review" if the user requested
   pauses).
3. **A conventional git commit message in a code-block** that summarises
   the changes made in this increment. The commit message is the artefact
   the user reads when reviewing the diff, so write it accordingly:

   - **Subject line**: ≤ 72 characters, imperative mood
     (`"Add"`, `"Wire"`, `"Refactor"`), no trailing period.
   - **Body**: wrapped at 72 columns, blank line after the subject, then
     a short "why" paragraph followed by bullet points for each
     meaningful change.
   - **Tone**: professional and conventional — what a reviewer expects to
     see in `git log --oneline` and `git show`.
   - **Forbidden content**: do **not** mention the originating challenge,
     competition, organiser, team name, qualifying round, increment
     number, phase number, or any reference to the build prompt or
     external design doc. The commit describes the code, not the
     provenance.
   - **Required content**: the subject states the increment's effect;
     the body states what was added, what was tested, and what was
     verified (lint, type, tests).
   - Example shape (do not include the increment number in the body):

     ```
     Add safety layer with credential and refund-promise rewriting

     Introduces app/core/safety.py with a pure, idempotent text
     rewriter that strips PINs, OTPs, passwords, card numbers, refund
     promises, "we have reversed", external phone numbers, and
     external URLs from any text field before it leaves the service.

     - app/core/safety.py: pre_scan() flags unsafe inputs,
       rewrite() normalises outputs, both regex-only
     - tests/test_safety.py: covers 12 sample cases plus
       rewrite idempotency
     - tests/fixtures/safety_samples.json: 12 cases (8 unsafe,
       4 clean)

     Verified: ruff check . clean, mypy --strict app/ clean,
     pytest -q green.
     ```

---

## 7. Stop conditions

Stop and ask the user (do **not** proceed) if:

- The external doc is silent on a needed decision.
- The external doc contains an internal contradiction you cannot resolve
  by re-reading.
- A test failure persists after two attempts to fix (one fix the code,
  one fix the test).
- A required dependency is unavailable in the environment.
- A change would require modifying the external doc.

Format the question precisely:

```
<one-paragraph context>
Question: <the precise decision needed>
Options:
  A) <option 1>
  B) <option 2>
  C) <option 3>
Default: <A|B|C> if no reply
```

---

## 8. Anti-patterns (forbidden)

- ❌ Creating files outside the canonical layout in §3.
- ❌ Adding `requirements.txt` entries not declared in the external doc.
- ❌ Inventing new endpoints, fields, or enum values.
- ❌ Using `print()` for logging.
- ❌ Using `Any` in Pydantic models without a justification comment.
- ❌ Logging the full complaint text, transaction amounts, or any PII.
- ❌ Making the LLM path the default or required.
- ❌ Skipping tests "to come back later".
- ❌ Marking an increment done with failing tests.
- ❌ Refactoring across increments (stay within the current increment).
- ❌ Adding CI runners, linters, or tools not mentioned in the external doc.
- ❌ Using `dict` for response models (use Pydantic).
- ❌ Using `str` for closed sets (use `Literal`).
- ❌ Skipping `pytest -q` after every increment.
- ❌ Embedding increment numbers, phase numbers, or external-doc section
  numbers in source code comments, docstrings, error messages, log keys,
  or metric names. Source code references concepts, not the plan.
- ❌ Editing the external doc.
- ❌ Mentioning the originating challenge, competition, organiser, team
  name, qualifying round, increment number, or any reference to the
  build prompt in commit messages or PR descriptions. Commits describe
  the code, not the provenance.

---

## 9. Pre-flight (run once, before increment 0)

Run these and capture output in `build_log.md`:

```bash
python --version            # must be 3.14.x; if not, stop and ask
pip --version
git --version
```

Verify the external doc is reachable (it lives outside the remote repo;
the prompt does not need to be able to open it, only confirm it has been
provided once and is read-only).

Verify Python can create a venv:

```bash
python -m venv .venv && .venv/bin/python --version || .venv\Scripts\python --version
```

If any of these fail, stop and ask the user to remediate.

---

## 10. Increment 0 — Project skeleton + toolchain

### Reference
The external doc's tech stack, project structure, testing, and local
development sections.

### Objective
Bootstrap the project tree, toolchain config, and an empty but importable
`app/`.

### Files to create

**Root**
- `pyproject.toml` — project metadata; tool config for `ruff`, `mypy`,
  `pytest`. Pin Python 3.14. Single source of truth for tooling.
- `requirements.txt` — runtime deps (start with none; populate as
  increments add deps).
- `requirements-dev.txt` — `pytest`, `pytest-asyncio`, `pytest-cov`,
  `httpx`, `ruff`, `mypy`, `pip-audit`, `pre-commit`.
- `.gitignore` — Python + IDE + OS junk.
- `.editorconfig` — UTF-8, LF, 4-space indent (Python).
- `.dockerignore` — empty for now; populated with the container increment.
- `.env.example` — empty placeholders, populated with the configuration
  increment.
- `README.md` — overview, API table, **Project progress** table, layout,
  dev quickstart, configuration note, safety note, license. The progress
  table is updated at every increment close.
- `LICENSE` — MIT, placeholder author.
- `CHANGELOG.md` — single `0.1.0` entry.
- `build_log.md` — pre-flight section + per-increment reports.

**`app/`**
- `app/__init__.py` — empty, exports `__version__ = "0.1.0"`.
- `app/main.py` — `def create_app() -> FastAPI: return FastAPI(...)`.
  No middleware, no routes yet.
- `app/config.py` — empty placeholder; expanded with the configuration
  increment.
- `app/logging.py` — placeholder; expanded with the logging increment.
- `app/errors.py` — placeholder; expanded with the errors increment.
- `app/api/__init__.py` — empty.
- `app/schemas/__init__.py` — empty.
- `app/core/__init__.py` — empty.
- `app/llm/__init__.py` — empty.
- `app/util/__init__.py` — empty.

**`tests/`**
- `tests/__init__.py` — empty.
- `tests/conftest.py` — imports `pytest`, no fixtures yet.
- `tests/test_smoke.py` — verifies `create_app()` returns a `FastAPI`
  with the expected `title` and `version`, and that two factory calls
  return distinct instances.
- `tests/fixtures/__init__.py` — empty.

### Commands to run

```bash
python -m venv .venv
. .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pre-commit install                   # optional; non-fatal if missing
ruff check .
ruff format --check .
mypy --strict app/                   # empty package: must pass trivially
pytest -q
```

### Definition of Done
- [ ] All listed files exist.
- [ ] `from app.main import create_app` works.
- [ ] `pytest -q` is green (≥ 2 tests).
- [ ] `ruff check .` and `ruff format --check .` are clean.
- [ ] `mypy --strict app/` is clean.
- [ ] `README.md` progress table has increment 0 marked ✅ done.
- [ ] `build_log.md` exists with the pre-flight section and the increment
      0 report.

---

## 11. Increments 1–18

Each of the following increments follows the same template as Increment 0
(§10), with one change: the increment number and title vary, the reference
section cites the relevant external-doc sections, and the file list, tests,
and Definition of Done are tailored to that increment. The increment
table in §3 is the canonical index; the external doc is the canonical
specification.

If you find yourself needing an external-doc section not listed for the
current increment, you are out of scope. Stop.

---

## 12. Final acceptance

After increment 18, run the external doc's final acceptance checklist
end-to-end. Every box must be checkable. If any box fails, return to the
offending increment and fix.

Additionally, before declaring the project done, the agent must:

1. Run `pytest -q` and `pytest --cov=app` and paste the coverage table.
2. Run `ruff check . && ruff format --check . && mypy --strict app/` and
   paste the clean output.
3. Run `python scripts/load_test.py` against the local app and paste the
   report.
4. Boot uvicorn locally, hit `/health` with `curl`, and paste the response.
5. Hand-off: produce a `## Build complete` section in `build_log.md`
   summarising the final state.

---

## 13. Escalation rules

When in doubt:

1. Re-read the relevant external-doc section. If it answers the question,
   proceed.
2. If the external doc is silent, choose the **most boring** option
   (boring-and-deterministic principle) and document the decision in
   `build_log.md`.
3. If the external doc is contradictory after re-reading, stop and ask
   the user with the question format in §7.
4. Never invent a third path silently.

---

## Appendix A — Quick commands

```bash
# Increment 0+
ruff check . && ruff format --check .

# Increment 0+
mypy --strict app/

# Increment 0+
pytest -q

# Safety increment onward
pytest --cov=app --cov-report=term-missing

# Transport increment onward
uvicorn app.main:app --host 127.0.0.1 --port 8000
curl -sS 127.0.0.1:8000/health

# LLM increment onward
LLM_ENABLED=true LLM_API_KEY=sk-test python -m pytest tests/test_llm_orchestrator.py -q

# Local-dev-tools increment onward
python scripts/load_test.py --target http://127.0.0.1:8000 --requests 1000 --concurrency 32
```
