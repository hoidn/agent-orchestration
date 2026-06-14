# Workflow Lisp Private Runtime Value Flow C2 Observability-Derived Human Summaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Project rule override: do not create a worktree.

**Goal:** Land the bounded C2 Track C slice by deriving deterministic human/operator summaries from typed terminal values and transition audit evidence, emitting run-local `typed-terminal-summary.{json,md}` plus `observability_summary_report.json`, surfacing them through the existing summary hub/report/dashboard as observability-only views, and preserving workflow/output/routing authority boundaries.

**Architecture:** Keep C2 runtime-local and observability-only. Add one Workflow Lisp helper module that consumes the checked C0 human-observability rows, terminal workflow outputs, transition audit helpers, and optional old-writer view paths to build deterministic summary payloads, Markdown, comparison evidence, and authority diagnostics. Wire that helper into the run summary hub at terminal-state time, then project the emitted files through `build_status_snapshot`, `render_status_markdown`, and dashboard summary routes without parsing summary prose as state, without mutating `state.json`, and without introducing a new compile/parity authority lane.

**Tech Stack:** Python 3, Workflow Lisp checked C0 manifest, `orchestrator.workflow.transition_executor` audit helpers, `SummaryObserver`, `WorkflowExecutor`, `orchestrator.observability.report`, `orchestrator.dashboard.server`, pytest, `python -m orchestrator report`

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/README.md`
- `docs/capability_status_matrix.md`
- `docs/work_definition_model.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
- `docs/design/workflow_command_adapter_contract.md`
- `specs/observability.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-c2-observability-derived-human-summaries/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-c0-rendering-census-and-renderer-seam-verification/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-c1-typed-values-as-prompt-inputs/implementation_architecture.md`
- `state/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/progress_ledger.json`
- `state/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/drain/iterations/9/design-gap-architect/work_item_context.md`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.consumer_rendering_census.json`

## Authority Reconciliation

Execute this plan against the selected C2 implementation architecture and current checkout, not against assumptions from the predecessor C0/C1 slices.

- The C2 implementation architecture is authoritative for scope, schema ids, success evidence, diagnostic names, fallback behavior when transition audit evidence is unavailable, and the requirement that summaries stay observability-only.
- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md` owns the C2 acceptance rule: human/operator summaries are rendered at the observability consumer seam from typed terminal values and transition audit evidence rather than producer-owned summary writers or summary paths.
- `docs/design/workflow_lisp_frontend_specification.md` remains authoritative for semantic authority classes, typed workflow outputs, source-map obligations, and the rule that generated/projection surfaces must not become hidden execution authority.
- `specs/observability.md` is normative for summary files, summary indexes, `README.md`, `run-summary.md`, and dashboard summary routes being read-only observability artifacts that must not drive routing, retries, assertions, or status reconciliation.
- `docs/design/workflow_command_adapter_contract.md` forbids solving C2 with scripts, inline Python/shell, command steps, report parsing, or adapter glue. C2 summary derivation must remain in Python runtime/projection code.
- C0 remains the inventory authority for which render-only rows are eligible. C2 consumes rows where `consumer_lane == "human_observability"` or `track_c_decision == "RETIRE_TO_OBSERVABILITY"`; it does not invent a second primary census.
- C1 typed prompt-input evidence is adjacent context only. C2 does not reuse prompt-rendering files as human-summary evidence and does not alter provider prompt composition.
- C2 evidence stays runtime-local in this slice. Do not add a new compile artifact or parity prerequisite unless a targeted failing test proves runtime-visible C0/source-map inputs are insufficient. If that happens, stop and reopen scope explicitly instead of silently expanding into build/parity work.

## Current Checkout Facts

Use these as fixed starting assumptions unless targeted failing tests disprove one:

- `state/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/progress_ledger.json` is still empty.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- `orchestrator/workflow_lisp/consumer_rendering_census.py` and the checked `design_delta_parent_drain.consumer_rendering_census.json` already exist. The known C2 row is `c0.drain_summary_report_target_final_summary_view`, and the manifest already contains multiple `RETIRE_TO_OBSERVABILITY` rows in the Design Delta family.
- `orchestrator/workflow/transition_executor.py` already exposes read-only audit helpers: `read_transition_audit_rows`, `read_pending_transition_replay`, `load_transition_resource_state*`, and `transition_audit_file_digest`.
- `orchestrator.observability.summary.SummaryObserver` already owns `RUN_ROOT/summaries/index.json`, `README.md`, and `run-summary.md`, but it only emits provider-backed per-step summaries today and does not yet have a deterministic terminal-summary entry path.
- `orchestrator.observability.report.build_status_snapshot` and `render_status_markdown` already surface run state, workflow outputs, and prompt-audit observability without depending on summary prose.
- `orchestrator/dashboard/server.py` already serves the summary hub HTML plus `/runs/<workspace>/<run>/summaries/live.json`, and those routes are specified as read-only GUI projections.
- The existing real-CLI feasibility helper for `runtime_transition_fixture.orc` succeeds only after staging both required workflow inputs (`run_state.json` and `drain_summary.json`) in a dedicated fixture area before invoking `python -m orchestrator run`; reusing the smoke command without that setup fails input binding in the current checkout.
- No current compile/build lane emits `observability_summary_report.json`. The C2 architecture allows this slice to keep the report under `RUN_ROOT/summaries/`.

## Hard Scope Limits

Implement only this bounded C2 slice:

- one Workflow Lisp helper for C2 row selection, typed terminal normalization, transition-audit projection, deterministic JSON/Markdown rendering, old-writer comparison, and authority diagnostics;
- one runtime summary-hub integration that writes `typed-terminal-summary.json`, `typed-terminal-summary.md`, `observability_summary_report.json`, and an additive `typed_terminal` summary-index entry;
- one report integration that links/surfaces C2 facts without using summary prose as state;
- one dashboard integration that previews/exposes C2 facts read-only; and
- one reference-family verification lane that compiles or dry-runs the Design Delta parent-drain entrypoint, confirms the checked C0/C1 prerequisite reports remain passing, and proves the real report/dashboard observability surfaces against a persisted smoke run; and
- focused unit/integration/runtime tests proving observability-only behavior.

Explicit non-goals:

- no C3 entry-boundary publication work;
- no C4 compatibility bridge metadata/generation work;
- no C5 durable-vs-ephemeral rendering cleanup or body-level writer deletion;
- no Track R checkpoint/restore/effect-policy/resume changes;
- no provider or command structured-output authority changes;
- no command adapters, scripts, inline Python/shell glue, or report parsing;
- no compile-artifact or migration-parity promotion change unless explicitly reopened;
- no workflow source rewrite to remove summary writers in this slice; and
- no `specs/` changes unless a failing verification step proves an existing normative gap.

## File Ownership

Create:

- `orchestrator/workflow_lisp/observability_summaries.py`
- `tests/test_workflow_lisp_observability_summaries.py`

Modify:

- `orchestrator/observability/summary.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/observability/report.py`
- `orchestrator/dashboard/server.py`
- `tests/test_cli_report_command.py`
- `tests/test_observability_summary_modes.py`
- `tests/test_observability_summary_runtime.py`
- `tests/test_observability_report.py`
- `tests/test_dashboard_server.py`

Inspect and modify only if targeted failing tests prove it is required:

- `orchestrator/workflow_lisp/consumer_rendering_census.py`
- `orchestrator/dashboard/projection.py`
- `orchestrator/cli/commands/report.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/migration_parity.py`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.consumer_rendering_census.json`

Do not modify in this slice unless verification proves the plan is incomplete:

- workflow source files under `workflows/library/lisp_frontend_design_delta/`
- provider or command manifests
- Track R modules or design docs
- parity target manifests
- `specs/`

## Required Contract Decisions

These decisions are fixed for implementation and should not be reopened while coding:

- The summary payload schema id is exact: `workflow_lisp_observability_summary.v1`.
- The report schema id is exact: `workflow_lisp_observability_summary_report.v1`.
- The runtime-local artifact paths are exact:
  - `RUN_ROOT/summaries/typed-terminal-summary.json`
  - `RUN_ROOT/summaries/typed-terminal-summary.md`
  - `RUN_ROOT/summaries/observability_summary_report.json`
- The summary-index entry contract is exact:
  - `step_name: "workflow-terminal"`
  - `kind: "typed_terminal"`
  - `profile: "workflow-lisp-c2"`
  - `authority: "observability_only"`
- C2 row selection is exact: only rows where `consumer_lane == "human_observability"` or `track_c_decision == "RETIRE_TO_OBSERVABILITY"` participate.
- Terminal-value source precedence is exact:
  - first `state.workflow_outputs`;
  - if unavailable, a validated terminal projection already persisted in step outcomes;
  - never old summary Markdown, pointer files, or summary-path text files.
- Transition audit facts must be obtained only through `transition_executor` read helpers or narrow wrappers over them. If audit paths cannot be located for the run, emit a terminal-only summary plus `observability_summary_transition_audit_missing`; do not reconstruct audit facts from old summary prose.
- Old-writer comparison is evidence only. It must not become workflow output authority, parity semantic output, routing input, retry input, or dashboard control state.
- Dashboard summary routes remain pure/read-only. Report markdown may preview/link to the summary JSON/Markdown files, but neither report nor dashboard may parse summary prose to determine status, outputs, or retries.
- C2 evidence stays out of compile-artifact/parity gating in this slice. Build/parity files are inspect-only unless a blocker is proven by tests.
- Diagnostic codes must use the architecture names when applicable:
  - `observability_summary_c0_row_missing`
  - `observability_summary_terminal_value_missing`
  - `observability_summary_terminal_value_invalid`
  - `observability_summary_transition_audit_missing`
  - `observability_summary_transition_audit_invalid`
  - `observability_summary_source_map_missing`
  - `observability_summary_used_as_state`
  - `observability_summary_dashboard_mutation`
  - `observability_summary_old_writer_comparison_missing`
  - `observability_summary_command_glue_forbidden`

## Task 1: Lock The C2 Regression Surface Before Adding Runtime Summary Logic

**Files:**

- Create: `tests/test_workflow_lisp_observability_summaries.py`
- Modify: `tests/test_cli_report_command.py`
- Modify: `tests/test_observability_summary_modes.py`
- Modify: `tests/test_observability_summary_runtime.py`
- Modify: `tests/test_observability_report.py`
- Modify: `tests/test_dashboard_server.py`

- [ ] Add `tests/test_workflow_lisp_observability_summaries.py` with focused unit coverage for:
  - positive selection of C2 rows from the checked Design Delta C0 manifest;
  - positive terminal-value normalization and digest generation from `state.workflow_outputs`;
  - positive transition-audit projection using a JSONL audit log and digest;
  - positive deterministic JSON/Markdown rendering with the required schema/version/path fields;
  - positive old-writer comparison payload generation for a `RETIRE_TO_OBSERVABILITY` row;
  - negative missing terminal value;
  - negative malformed terminal value that cannot be canonicalized;
  - negative unreadable/invalid transition audit rows;
  - negative summary payload used as semantic state/output authority; and
  - negative missing old-writer comparison evidence for a retirement row.

- [ ] Extend `tests/test_observability_summary_modes.py` with failing expectations for a provider-free deterministic summary-index entry path in `SummaryObserver`, including:
  - additive `kind: "typed_terminal"` entry writing;
  - preservation of `README.md` / `run-summary.md` hub generation;
  - stable `authority: "observability_only"` metadata; and
  - no provider invocation for deterministic C2 emission.

- [ ] Extend `tests/test_observability_summary_runtime.py` with one focused runtime smoke that:
  - creates a deterministic run id;
  - persists a typed terminal workflow output shaped like a Design Delta terminal union/result;
  - writes at least one transition audit JSONL row;
  - triggers C2 summary emission through the runtime summary path; and
  - asserts `typed-terminal-summary.json`, `typed-terminal-summary.md`, `observability_summary_report.json`, and the `typed_terminal` summary-index entry all exist and are observability-only.

- [ ] Extend `tests/test_observability_report.py` with failing expectations that:
  - `build_status_snapshot` exposes `run.observability_summaries.typed_terminal`;
  - `render_status_markdown` links/previews the typed terminal summary from JSON facts rather than Markdown parsing; and
  - report status reconciliation behavior stays unchanged.

- [ ] Extend `tests/test_cli_report_command.py` with one failing command-surface proof that:
  - renders `python -m orchestrator report --run-id <run_id> --runs-root <smoke_runs_root> --format json` for a persisted C2 smoke run;
  - asserts the JSON payload exposes `run.observability_summaries.typed_terminal`;
  - asserts the surfaced paths point to `summaries/typed-terminal-summary.{json,md}` plus `summaries/observability_summary_report.json`; and
  - proves the report command remains read-only and does not infer state from summary prose.

- [ ] Extend `tests/test_dashboard_server.py` with failing expectations that:
  - the summary hub page shows the typed terminal summary entry and links to JSON/Markdown files;
  - `/summaries/live.json` exposes typed-terminal metadata or links when the files exist;
  - summary hub preview logic tolerates missing/invalid C2 files as display states; and
  - dashboard routes do not mutate `state.json` while rendering C2 data.

- [ ] Run collection and capture the expected pre-implementation failures:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_observability_summaries.py -q
python -m pytest --collect-only tests/test_observability_summary_runtime.py -q
python -m pytest --collect-only tests/test_observability_report.py -q
python -m pytest --collect-only tests/test_cli_report_command.py -q
python -m pytest --collect-only tests/test_dashboard_server.py -q
python -m pytest tests/test_workflow_lisp_observability_summaries.py -q
python -m pytest tests/test_observability_summary_modes.py -k typed_terminal -q
python -m pytest tests/test_observability_summary_runtime.py -k typed_terminal -q
python -m pytest tests/test_observability_report.py -k typed_terminal -q
python -m pytest tests/test_cli_report_command.py -k typed_terminal -q
python -m pytest tests/test_dashboard_server.py -k typed_terminal -q
```

- [ ] Commit the red test scaffold once the failure surface matches the C2 architecture exactly.

## Task 2: Implement The C2 Helper Module And Runtime-Local Evidence Contracts

**Files:**

- Create: `orchestrator/workflow_lisp/observability_summaries.py`
- Modify: `tests/test_workflow_lisp_observability_summaries.py`

- [ ] Create `orchestrator/workflow_lisp/observability_summaries.py` with:
  - schema constants for the payload/report versions;
  - a loader/selector for the checked C0 manifest rows relevant to C2;
  - terminal-value normalization and deterministic digest helpers;
  - transition-audit projection helpers using `read_transition_audit_rows` and `transition_audit_file_digest`;
  - deterministic Markdown rendering that includes the observability-only disclaimer;
  - summary-index entry construction for `kind: "typed_terminal"`;
  - old-writer comparison payload construction for retirement rows; and
  - report payload construction with pass/fail status plus diagnostics buckets.

- [ ] Keep the helper API explicit and pure. Preferred shape:
  - input: run root, workflow name/family, state snapshot, optional workflow bundle/source-map lineage, checked manifest path, and optional old-writer file paths;
  - output: normalized JSON payload, rendered Markdown string, summary-index entry, report payload, and zero or more diagnostics.

- [ ] Fail closed on authority mistakes:
  - reject attempts to treat summary files as workflow outputs/artifacts/state;
  - reject missing/invalid manifest rows for required C2 coverage;
  - reject audit parsing failures with stable diagnostics; and
  - reject any code path that requires reading summary Markdown to recover facts.

- [ ] Keep source-map lineage additive rather than blocking:
  - accept source-map origin keys when runtime integration can provide them;
  - if not available, emit `observability_summary_source_map_missing` in the report rather than inventing fake lineage.

- [ ] Re-run the new helper unit tests until they pass cleanly:

```bash
python -m pytest tests/test_workflow_lisp_observability_summaries.py -q
```

- [ ] Commit the helper module and unit-test green state.

## Task 3: Wire Deterministic Terminal Summary Emission Into The Summary Hub

**Files:**

- Modify: `orchestrator/observability/summary.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_observability_summary_modes.py`
- Modify: `tests/test_observability_summary_runtime.py`

- [ ] Extend `SummaryObserver` with one deterministic, provider-free emission path for observability summaries. Do not overload provider-backed `emit()` with hidden branching; add a narrow method or helper that:
  - writes the JSON payload, Markdown file, and report JSON;
  - appends the `typed_terminal` entry to `summaries/index.json`;
  - regenerates `README.md` and `run-summary.md`; and
  - never calls `provider_executor`.

- [ ] Add a terminal-state hook in `WorkflowExecutor` that invokes the C2 helper only after workflow outputs/finalization state are stable enough to be observed. The hook must:
  - run after canonical terminal state is persisted;
  - use current run root and workflow/state context;
  - write only under `RUN_ROOT/summaries/`;
  - tolerate missing transition audit inputs by emitting terminal-only diagnostics; and
  - never affect routing, retries, failures, or workflow outputs.

- [ ] Keep the integration bounded:
  - do not create summaries before terminal outputs exist;
  - do not require `phase-performance` provider summaries to be enabled for C2 to work if the executor can emit deterministic summaries directly;
  - do not mutate `state.json` or step results to store C2 summary facts.

- [ ] If the current executor lifecycle cannot expose a safe terminal hook without broader churn, stop after proving the gap with a failing test and evaluate whether a summary-hub-finalization helper in `executor.py` is sufficient. Do not route C2 through dashboard request handling as a workaround.

- [ ] Re-run the summary observer/runtime smoke selectors until green:

```bash
python -m pytest tests/test_observability_summary_modes.py -k typed_terminal -q
python -m pytest tests/test_observability_summary_runtime.py -k typed_terminal -q
```

- [ ] Commit the runtime emission integration once the focused runtime smoke passes.

## Task 4: Project C2 Evidence Through Report And Dashboard Without Widening Authority

**Files:**

- Modify: `orchestrator/observability/report.py`
- Modify: `orchestrator/dashboard/server.py`
- Modify: `tests/test_cli_report_command.py`
- Modify: `tests/test_observability_report.py`
- Modify: `tests/test_dashboard_server.py`

- [ ] Update `build_status_snapshot` to read C2 JSON/report files when present and expose one additive block at `run.observability_summaries.typed_terminal` with:
  - availability/status;
  - summary and payload relative paths;
  - `authority: "observability_only"`;
  - optionally compact variant/audit facts derived from the JSON payload only.

- [ ] Update `render_status_markdown` to surface a short typed-terminal summary section or links based on the JSON payload. Do not parse the Markdown file and do not let C2 facts change run status or progress accounting.

- [ ] Extend the CLI report coverage in `tests/test_cli_report_command.py` so the command path proves the same read-only C2 payload surfaced by `build_status_snapshot`:
  - use a persisted smoke run under an explicit runs root;
  - invoke the report command with `--format json`;
  - assert the typed-terminal block is present with `authority: "observability_only"`; and
  - assert the command does not rewrite `state.json` or reconcile status from summary files.

- [ ] Update dashboard summary-hub rendering and `/summaries/live.json` projection so users can discover:
  - the typed terminal summary entry in the summary table;
  - a preview/link to `typed-terminal-summary.md`;
  - a link to `typed-terminal-summary.json`;
  - a link to `observability_summary_report.json` when present; and
  - read-only audit/old-writer comparison context when available.

- [ ] Preserve dashboard purity:
  - no state mutation;
  - no provider calls;
  - no recovery/resume controls derived from C2 payloads; and
  - invalid/missing C2 files remain display warnings only.

- [ ] Re-run the projection/UI selectors until green:

```bash
python -m pytest tests/test_observability_report.py -k typed_terminal -q
python -m pytest tests/test_cli_report_command.py -k typed_terminal -q
python -m pytest tests/test_dashboard_server.py -k typed_terminal -q
```

- [ ] Commit the report/dashboard projection changes once the new assertions pass.

## Task 5: Full Verification And Bounded Regression Sweep

**Files:**

- Modify only if a failing verification command proves the prior tasks missed required coverage.

- [ ] Run the focused C2 suite end-to-end:

```bash
python -m pytest tests/test_workflow_lisp_observability_summaries.py -q
python -m pytest tests/test_observability_summary_modes.py -k typed_terminal -q
python -m pytest tests/test_observability_summary_runtime.py -k typed_terminal -q
python -m pytest tests/test_observability_report.py -k typed_terminal -q
python -m pytest tests/test_cli_report_command.py -k typed_terminal -q
python -m pytest tests/test_dashboard_server.py -k typed_terminal -q
```

- [ ] Re-run the Design Delta prerequisite and family smoke lane because C2 depends on the checked C0/C1 reports and the reference-family terminal/audit surfaces:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "consumer_rendering_census_report or typed_prompt_input_report or design_delta_parent_drain" -q
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_parent_drain_smokes_runtime_transition_fixture_emits_audit_handoff or design_delta_parent_drain_smokes_selected_item_completed_path or design_delta_parent_drain_smokes_selector_done_path" -q
```

- [ ] Confirm the final Design Delta compile/build evidence still contains passing `consumer_rendering_census_report.json` and `typed_prompt_input_report.json` prerequisite artifacts, and that C2 continues to treat them as prerequisites rather than as new semantic authority.

- [ ] Run one real persisted C2 smoke, then prove both the report and dashboard read-only surfaces against that smoke run:

```bash
SMOKE_WORKSPACE=.orchestrate/tmp/c2-observability-dashboard-workspace
SMOKE_RUNS_ROOT="$SMOKE_WORKSPACE/.orchestrate/runs"
SMOKE_FIXTURE_ROOT=.orchestrate/tmp/c2-observability-smoke-fixtures
SMOKE_DASHBOARD_PAYLOAD=.orchestrate/tmp/c2-observability-dashboard-live.json
rm -rf "$SMOKE_WORKSPACE" "$SMOKE_FIXTURE_ROOT" "$SMOKE_DASHBOARD_PAYLOAD"
mkdir -p "$SMOKE_RUNS_ROOT" "$SMOKE_FIXTURE_ROOT/state" "$SMOKE_FIXTURE_ROOT/artifacts/work"
printf '%s\n' '{"schema":"lisp_frontend_autonomous_drain_run_state/v1","completed_items":[],"completed_design_gaps":[],"blocked_items":{},"blocked_design_gaps":{},"history":[]}' > "$SMOKE_FIXTURE_ROOT/state/run_state.json"
printf '%s\n' '{"status":"BLOCKED","reason":"runtime_native_fixture"}' > "$SMOKE_FIXTURE_ROOT/artifacts/work/drain_summary.json"
python -m orchestrator run workflows/library/lisp_frontend_design_delta/runtime_transition_fixture.orc --entry-workflow run-runtime-transition-fixture --source-root workflows/library --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json --input fixture_run_state_path="$SMOKE_FIXTURE_ROOT/state/run_state.json" --input summary_path="$SMOKE_FIXTURE_ROOT/artifacts/work/drain_summary.json" --state-dir "$SMOKE_RUNS_ROOT"
SMOKE_RUN_ID="$(basename "$(find "$SMOKE_RUNS_ROOT" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)")"
STATE_JSON="$SMOKE_RUNS_ROOT/$SMOKE_RUN_ID/state.json"
STATE_SHA_BEFORE_REPORT="$(sha256sum "$STATE_JSON" | awk '{print $1}')"
python -m orchestrator report --run-id "$SMOKE_RUN_ID" --runs-root "$SMOKE_RUNS_ROOT" --format json
STATE_SHA_AFTER_REPORT="$(sha256sum "$STATE_JSON" | awk '{print $1}')"
test "$STATE_SHA_BEFORE_REPORT" = "$STATE_SHA_AFTER_REPORT"
export SMOKE_WORKSPACE SMOKE_RUN_ID SMOKE_DASHBOARD_PAYLOAD
python - <<'PY'
import json
import os
from pathlib import Path

from orchestrator.dashboard.scanner import RunScanner
from orchestrator.dashboard.server import DashboardApp

workspace = Path(os.environ["SMOKE_WORKSPACE"])
run_id = os.environ["SMOKE_RUN_ID"]
payload_path = Path(os.environ["SMOKE_DASHBOARD_PAYLOAD"])
response = DashboardApp(RunScanner([workspace])).handle(
    "GET",
    f"/runs/w0/{run_id}/summaries/live.json",
)
if response.status != 200:
    raise SystemExit(f"dashboard live payload failed: HTTP {response.status}")
payload = json.loads(response.body.decode("utf-8"))
payload_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(payload_path)
PY
STATE_SHA_AFTER_DASHBOARD="$(sha256sum "$STATE_JSON" | awk '{print $1}')"
test "$STATE_SHA_AFTER_REPORT" = "$STATE_SHA_AFTER_DASHBOARD"
```

- [ ] Inspect the persisted smoke outputs and assert:
  - `RUN_ROOT/summaries/typed-terminal-summary.json`, `typed-terminal-summary.md`, and `observability_summary_report.json` exist under the smoke run;
  - the report command exposes `run.observability_summaries.typed_terminal` with `authority: "observability_only"` and run-local summary/report paths;
  - the dashboard live payload captured at `$SMOKE_DASHBOARD_PAYLOAD` exposes the typed-terminal entry or links from the real `/summaries/live.json` route;
  - the smoke run keeps `state.workflow_outputs` authoritative, `state.json` unchanged across the report command, and `state.json` unchanged again across the dashboard helper call; and
  - missing transition-audit inputs, when forced by a negative test, degrade to explicit diagnostics instead of summary reconstruction from prose.

- [ ] Run one broader observability regression sweep to ensure C2 did not break existing summary/report behavior:

```bash
python -m pytest tests/test_observability_summary_modes.py -q
python -m pytest tests/test_observability_report.py -q
```

- [ ] If `executor.py` changes touched summary lifecycle semantics beyond the typed-terminal path, run the existing runtime smoke module too:

```bash
python -m pytest tests/test_observability_summary_runtime.py -q
```

- [ ] Produce visible evidence that the C2 payloads are observability-only:
  - assert the runtime smoke leaves `state.workflow_outputs` unchanged;
  - assert summary/report paths do not appear under workflow artifact lineage;
  - assert the CLI report command and the persisted-smoke dashboard helper payload stay read-only over the same run, with matching `state.json` digests before/after each surface invocation;
  - assert the dashboard tests prove no `state.json` mutation; and
  - assert missing transition audit input degrades to explicit diagnostics instead of silent summary fabrication.

- [ ] Do **not** add compile/build/parity verification in this slice unless code changes were forced into `orchestrator/workflow_lisp/build.py` or `migration_parity.py`. If that happens, append the narrowest additional selector proving the change and document why runtime-local C2 was insufficient.

- [ ] Record completion evidence in the implementation report with:
  - the Design Delta compile command and smoke commands used;
  - emitted C2 summary/report paths;
  - summary/report schema ids;
  - the smoke workspace, smoke run id, runs root, and persisted dashboard payload path used for the real report/dashboard checks;
  - confirmation that `consumer_rendering_census_report.json` and `typed_prompt_input_report.json` stayed passing prerequisites;
  - selected C0 row ids;
  - terminal value digest;
  - transition audit digests or explicit terminal-only diagnostics;
  - the `state.json` digests captured before/after the persisted report command and before/after the persisted dashboard helper invocation;
  - old-writer comparison ids/statuses; and
  - the exact verification commands run.
