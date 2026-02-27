# Workflow Observability Status + Async-Default Summaries Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add human-readable workflow progress reporting (global + per-step input/output) and optional LLM step summaries with `async` as the default summary mode and explicit deterministic `sync` mode, without changing deterministic workflow execution semantics.

**Non-goal:** Do not add observability fields to workflow DSL. Observability controls live in runtime CLI/config only so workflow YAML stays focused on execution logic.

**Architecture:** Build a two-lane observability system. Lane 1 is deterministic and local: generate markdown/JSON status from `state.json`, workflow DSL, prompt-audit files, and captured outputs. Lane 2 is optional: run a summary provider per completed step using a frozen snapshot, write summary artifacts under run-root observability paths, and never feed those summaries into control flow, consumes/publishes, or contracts.

**Tech Stack:** `orchestrator/workflow/executor.py`, `orchestrator/state.py`, `orchestrator/cli/commands/run.py`, `orchestrator/cli/commands/resume.py`, `orchestrator/cli/main.py`, `orchestrator/providers/registry.py`, new `orchestrator/observability/*`, pytest.

---

## Implementation Contract (Must Hold)

1. Existing step execution, `goto`, `strict_flow`, `expected_outputs`, `output_bundle`, `publishes/consumes`, and resume behavior remain authoritative and unchanged.
2. Observability output is never consumed by `consumes` and never used for gates.
3. Summary mode defaults to `async` when summaries are enabled; explicit `sync` mode is supported and deterministic.
4. Deterministic report always works without LLM access.
5. Per-step input section includes post-substitution prompt when prompt-audit files exist (`--debug`).
6. Summary artifacts are isolated under `.orchestrate/runs/<run_id>/summaries/`.
7. `async` summary failures/timeouts never change step success/failure when `best_effort=true` (default).

Execution note: implementation should follow @superpowers:test-driven-development and @superpowers:verification-before-completion.

---

### Task 1: Runtime Observability Config (CLI/State, No DSL Surface)

**Files:**
- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/state.py`
- Create: `tests/test_cli_observability_config.py`

**Step 1: Add failing tests**

Add tests for runtime config parsing/persistence:
- `--step-summaries` enables summaries.
- `--summary-mode` supports `async|sync` with default `async` when summaries enabled.
- `--summary-provider`/`--summary-timeout-sec`/`--summary-max-input-chars` parsing.
- config persists to run state metadata and resume reloads it.
- invalid mode values reject cleanly.

**Step 2: Run red tests**

Run:
```bash
pytest tests/test_cli_observability_config.py -v
```
Expected: FAIL.

**Step 3: Implement runtime config plumbing**

Add run/resume config surface (example):
```bash
orchestrate run <workflow> \
  --step-summaries \
  --summary-mode async \
  --summary-provider claude_sonnet_summary \
  --summary-timeout-sec 120 \
  --summary-max-input-chars 12000
```

Rules:
- no workflow DSL changes.
- `--step-summaries` default mode = `async`.
- explicit `--summary-mode sync` supported.
- persist config in state metadata for resume determinism.

**Step 4: Re-run tests**

Run:
```bash
pytest tests/test_cli_observability_config.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/cli/main.py orchestrator/cli/commands/run.py orchestrator/cli/commands/resume.py orchestrator/state.py tests/test_cli_observability_config.py
git commit -m "feat(cli): add runtime observability config with async-default summaries"
```

---

### Task 2: Deterministic Run Status Reporter (No LLM Dependency)

**Files:**
- Create: `orchestrator/observability/report.py`
- Create: `tests/test_observability_report.py`

**Step 1: Write failing report tests**

Add tests for:
- global progress counts from workflow + state.
- per-step input extraction:
  - provider steps: post-substitution prompt from `logs/<Step>.prompt.txt` when present.
  - command steps: rendered command.
- per-step output extraction:
  - exit code, duration, output preview, artifacts.
- current-step inference when state is between step writes.

**Step 2: Run red tests**

Run:
```bash
pytest tests/test_observability_report.py -v
```
Expected: FAIL.

**Step 3: Implement deterministic renderer**

Implement pure functions:
- `build_status_snapshot(workflow, state, run_root, run_log_path=None) -> dict`
- `render_status_markdown(snapshot) -> str`

Snapshot fields:
- run metadata (`run_id`, `status`, times, workflow path)
- progress totals
- ordered step list with:
  - status
  - declared consumes/expected outputs
  - input payload (prompt/command)
  - output payload summary
  - deterministic summary line

**Step 4: Re-run tests**

Run:
```bash
pytest tests/test_observability_report.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/observability/report.py tests/test_observability_report.py
git commit -m "feat(observability): add deterministic workflow status reporter"
```

---

### Task 3: Add CLI `report` Command for Human-Readable Status

**Files:**
- Modify: `orchestrator/cli/main.py`
- Create: `orchestrator/cli/commands/report.py`
- Modify: `orchestrator/cli/commands/__init__.py`
- Create: `tests/test_cli_report_command.py`

**Step 1: Add CLI red tests**

Add tests for:
- `orchestrate report --run-id <id>` prints markdown report.
- default behavior chooses latest run when `--run-id` omitted.
- `--format json|md` support.
- `--output <path>` writes file.

**Step 2: Run red tests**

Run:
```bash
pytest tests/test_cli_report_command.py -v
```
Expected: FAIL.

**Step 3: Implement command**

Add `report` subcommand:
- inputs: `--run-id`, `--runs-root`, `--format`, `--output`
- loads state/workflow
- invokes deterministic reporter
- prints or writes output

**Step 4: Re-run tests**

Run:
```bash
pytest tests/test_cli_report_command.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/cli/main.py orchestrator/cli/commands/report.py orchestrator/cli/commands/__init__.py tests/test_cli_report_command.py
git commit -m "feat(cli): add report command for workflow observability status"
```

---

### Task 4: Add Summary Observer With Async Default + Deterministic Sync Option

**Files:**
- Create: `orchestrator/observability/summary.py`
- Modify: `orchestrator/workflow/executor.py`
- Create: `tests/test_observability_summary_modes.py`

**Step 1: Add red tests for modes/semantics**

Add tests:
- `async` dispatch happens after step completion and does not block step completion.
- `sync` executes inline and blocks until summary result/error is recorded.
- `async` failure does not change step result when `best_effort=true`.
- summary timeout handling for both modes.
- summary artifacts written under run-root.
- summary artifacts excluded from `artifact_versions` and `artifact_consumes`.

Mock provider execution to simulate success/failure/timeout.

**Step 2: Run red tests**

Run:
```bash
pytest tests/test_observability_summary_modes.py -v
```
Expected: FAIL.

**Step 3: Implement observer + executor integration**

Implement `SummaryObserver`:
- accepts frozen step snapshot payload.
- `mode=async`: submit background worker (`ThreadPoolExecutor`).
- `mode=sync`: run inline deterministically.
- writes:
  - `.orchestrate/runs/<run_id>/summaries/<step>.snapshot.json`
  - `.orchestrate/runs/<run_id>/summaries/<step>.summary.md`
  - `.orchestrate/runs/<run_id>/summaries/<step>.error.json` on failures

Executor integration:
- after step result persists, emit snapshot and run observer by configured mode.
- default mode is `async` when summaries enabled.

**Step 4: Re-run tests**

Run:
```bash
pytest tests/test_observability_summary_modes.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/observability/summary.py orchestrator/workflow/executor.py tests/test_observability_summary_modes.py
git commit -m "feat(observability): add async-default and sync summary modes"
```

---

### Task 5: Add Sonnet Summary Provider Alias + Prompt Contract

**Files:**
- Modify: `orchestrator/providers/registry.py`
- Modify: `specs/providers.md`
- Create: `tests/test_summary_provider_alias.py`

**Step 1: Add red tests**

Add tests:
- built-in provider `claude_sonnet_summary` exists.
- default model is Sonnet 4.6 identifier.
- provider uses expected prompt transport mode.

**Step 2: Run red tests**

Run:
```bash
pytest tests/test_summary_provider_alias.py -v
```
Expected: FAIL.

**Step 3: Implement provider alias**

Add built-in provider:
```python
"claude_sonnet_summary": ProviderTemplate(
    name="claude_sonnet_summary",
    command=["claude", "-p", "${PROMPT}", "--model", "${model}"],
    defaults={"model": "claude-sonnet-4-6"},
    input_mode=InputMode.ARGV,
)
```

Document this alias as observability-only (no gate/control usage).

**Step 4: Re-run tests**

Run:
```bash
pytest tests/test_summary_provider_alias.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/providers/registry.py specs/providers.md tests/test_summary_provider_alias.py
git commit -m "feat(providers): add claude sonnet summary provider alias"
```

---

### Task 6: End-to-End Integration Test for Report + Summary Modes

**Files:**
- Create: `tests/e2e/test_e2e_observability_status_and_summary_modes.py`
- Modify: `workflows/examples/` (minimal fixture workflow)

**Step 1: Add failing E2E tests**

Scenarios:
- workflow with one command step and one provider step.
- run with `--step-summaries --summary-mode async`.
- run with `--step-summaries --summary-mode sync`.
- mock summary provider in CI.

Assertions:
- normal step results/control flow succeed.
- `report` output includes per-step input/output sections.
- summary files exist.
- async summary failure does not fail workflow when best-effort is on.

**Step 2: Run red tests**

Run:
```bash
pytest tests/e2e/test_e2e_observability_status_and_summary_modes.py -v
```
Expected: FAIL.

**Step 3: Make tests green**

Wire any missing integration behavior.

**Step 4: Run targeted suite**

Run:
```bash
pytest tests/test_cli_observability_config.py tests/test_observability_report.py tests/test_cli_report_command.py tests/test_observability_summary_modes.py tests/test_summary_provider_alias.py tests/e2e/test_e2e_observability_status_and_summary_modes.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/e2e/test_e2e_observability_status_and_summary_modes.py workflows/examples
git commit -m "test(e2e): verify status reporting and summary modes without control-flow impact"
```

---

### Task 7: Documentation + Runbook Updates (Runtime Config, Not DSL)

**Files:**
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `README.md`
- Modify: `specs/providers.md`

**Step 1: Document semantics clearly**

Document:
- observability plane vs execution plane
- summaries are advisory only and not consumed by contracts
- runtime flags:
  - `--step-summaries`
  - `--summary-mode async|sync` (`async` default when enabled)
  - provider/timeout/input-size flags
- status reporting usage:
  - `orchestrate report --run-id <id>`

**Step 2: Run doc/smoke checks**

Run:
```bash
python -m orchestrator.cli.main run --help
python -m orchestrator.cli.main report --help
pytest tests/test_cli_report_command.py -v
```
Expected: PASS.

**Step 3: Commit**

```bash
git add docs/workflow_drafting_guide.md README.md specs/providers.md
git commit -m "docs: define runtime observability config and summary mode semantics"
```

---

## Final Verification

Run:
```bash
pytest tests/test_cli_observability_config.py tests/test_observability_report.py tests/test_cli_report_command.py tests/test_observability_summary_modes.py tests/test_summary_provider_alias.py -v
pytest tests/e2e/test_e2e_observability_status_and_summary_modes.py -v
```

Manual smoke:
```bash
python -m orchestrator.cli.main run workflows/examples/<fixture>.yaml --debug --step-summaries --summary-mode async
python -m orchestrator.cli.main report --run-id <run_id> --format md
python -m orchestrator.cli.main run workflows/examples/<fixture>.yaml --debug --step-summaries --summary-mode sync
```

Expected:
- Report includes run-level progress plus per-step input/output blocks.
- Summary artifacts appear under run-root summaries directory.
- `async` failures do not alter workflow exit code.
- `sync` behaves deterministically and blocks until summary outcome is written.
