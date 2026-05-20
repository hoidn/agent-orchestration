# First NeurIPS Implementation-Attempt Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first real Workflow Lisp Stage 4 translation slice: a `.orc` implementation-attempt subworkflow for the NeurIPS implementation phase that uses compiler-owned `with-phase` and `phase-target`, keeps `ImplementationAttempt` as an internal typed union, and proves shared-validation plus bounded runtime equivalence for completed and blocked outcomes.

**Architecture:** Keep all new ownership inside `orchestrator/workflow_lisp/`. `with-phase` is compile-time only: it installs a narrow phase scope derived from `ImplementationAttemptPhaseCtx`, `phase-target` resolves approved relpath targets from that scope, and `provider-result` inside that scope lowers its `variant_output.path` to the authoritative bundle path supplied by phase context rather than to a generated hidden write root. The translated `.orc` workflow still lowers through the existing authored-mapping bridge, validates through the shared elaboration/lowering seam, and executes with the current runtime plus fake-provider fixtures.

**Tech Stack:** Python 3, dataclasses, existing `orchestrator.workflow_lisp` Stage 1-3 modules, `LoadedWorkflowBundle`, `WorkflowExecutor`, `StateManager`, pytest, fake provider fixtures, and `.orc` fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these as the planning and implementation authority:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `21. Phase Context`
  - `22. Provider Result`
  - `26. run-provider-phase`
  - `89. Implementation Phase`
  - `96. Behavioral Equivalence Tests`
  - `103. Stage 5: Phase And Context Library`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `12. First Migration Target`
  - `13. Success Metrics`
  - `14. Implementation Stages`
  - `16. Acceptance Criteria`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Reference current behavioral ground truth from:

- `workflows/library/neurips_backlog_implementation_phase.v214.yaml`
- `tests/fixtures/v214_primitives/implementation_oracle/workflow.yaml`
- `tests/test_v214_runtime_semantics.py`
- `tests/test_neurips_steered_backlog_runtime.py`

## Hard Scope Limits

Implement only the bounded Stage 4 slice from the work-item context:

- one translated `.orc` subworkflow for the NeurIPS implementation attempt;
- minimal compiler-owned `with-phase` and `phase-target` support;
- one local `ImplementationAttemptPhaseCtx` record carrying:
  - `implementation_state_bundle_path`
  - `execution_report_target`
  - `progress_report_target`
- one internal `ImplementationAttempt` union produced by `provider-result`;
- one record-only workflow-boundary projection exporting:
  - `implementation_state`
  - `implementation_state_bundle_path`
- one compiler-generated prompt-input materialization prelude that republishes design, plan, execution-report target, and progress-report target as ordinary shared artifacts for provider `consumes` and `prompt_consumes`;
- shared-validation coverage and bounded runtime equivalence for completed and blocked attempt outcomes.

Explicit non-goals:

- no full implementation-phase translation, review loop, or final phase fan-in;
- no outer pointer or target materialization for the full phase wrapper;
- no macros, modules/imports, `defproc`, generic phase library, `run-provider-phase`, `review-revise-loop`, or drain/resource forms;
- no `.orc` loader or CLI integration;
- no report parsing, pointer-as-state bridges, or inline semantic shell/Python glue.

## Execution Notes

Do not assume the branch is pristine for this slice. Several target files may already exist as partial or stale implementations. Update them in place and reconcile them to this plan rather than deleting them and starting over.

Do not re-decide any of these during execution:

- keep all new frontend ownership inside `orchestrator/workflow_lisp/`;
- `with-phase` is compile-time only and must not lower to its own runtime step;
- `phase-target` is valid only inside an active `with-phase`;
- the only valid phase targets in this slice are `execution-report` and `progress-report`;
- `phase-target` uses unquoted symbols only: `(phase-target execution-report)` and `(phase-target progress-report)`;
- quoted symbols such as `(phase-target 'execution-report)` must remain rejected by the Stage 1 reader with the existing `frontend_parse_error` contract;
- the translated `provider-result` return type is the internal union `ImplementationAttempt`;
- workflow returns stay record-only and must not export the union directly;
- provider and prompt names stay on the existing extern boundary as exact authored symbols `providers.execute` and `prompts.implementation.execute`;
- the translated `.orc` workflow must not reintroduce snapshot-diff outcome inference, report parsing, or command-wrapper glue;
- shared validation and runtime remain authoritative after lowering; do not add a parallel validator or YAML text stage;
- the slice is not complete until a local MVP metrics report records the required authoring-surface measurements and picks one Stage 5 recommendation: `continue`, `revise`, or `stop`.

## File Ownership

Create:

- `tests/fixtures/workflow_lisp/invalid/phase_target_quoted_symbol_invalid.orc`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/mvp_metrics_recommendation_report.md`

Modify:

- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `tests/test_workflow_lisp_reader.py`
- `tests/test_workflow_lisp_phase_translation.py`
- `tests/test_workflow_lisp_workflows.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc`
- `tests/fixtures/workflow_lisp/invalid/phase_target_outside_with_phase.orc`
- `tests/fixtures/workflow_lisp/invalid/phase_context_invalid.orc`

Modify only if a focused failing test proves the need:

- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/workflows.py`

Reuse without broadening ownership:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/contracts.py`
- shared runtime/elaboration/lowering modules under `orchestrator/workflow/`
- `tests/fixtures/bin/fake_provider.py`
- `tests/fixtures/v214_primitives/implementation_oracle/`

## Required New Surface

Keep the new surface narrow and frontend-local.

In `orchestrator/workflow_lisp/expressions.py`:

```python
@dataclass(frozen=True)
class WithPhaseExpr:
    ctx_expr: ExprNode
    phase_name: str
    body: ExprNode
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class PhaseTargetExpr:
    target_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
```

In `orchestrator/workflow_lisp/phase.py` keep `PhaseScope` limited to the bounded slice:

```python
@dataclass(frozen=True)
class PhaseScope:
    context_record_name: str
    phase_name: str
    bundle_path_field: str
    target_fields: Mapping[str, str]
```

Use the exact target mapping:

```python
{
    "execution-report": "execution_report_target",
    "progress-report": "progress_report_target",
}
```

Required diagnostics for this slice:

- `phase_target_outside_with_phase`
- `phase_target_name_invalid`
- `phase_target_unknown`
- `phase_context_invalid`
- `phase_scope_nested_unsupported`
- `phase_translation_body_invalid`

Preserve existing diagnostics where they already fit:

- `frontend_parse_error`
- `workflow_return_type_invalid`
- `provider_result_return_type_invalid`
- `provider_result_provider_invalid`
- `provider_result_prompt_invalid`
- `variant_ref_unproved`
- `shared_validation_error`

## Task 1: Re-Baseline Fixtures And Add Failing Frontend Tests

**Files:**

- Create: `tests/fixtures/workflow_lisp/invalid/phase_target_quoted_symbol_invalid.orc`
- Modify: `tests/fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/phase_target_outside_with_phase.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/phase_context_invalid.orc`
- Modify: `tests/test_workflow_lisp_reader.py`
- Modify: `tests/test_workflow_lisp_phase_translation.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Normalize the fixture surface before changing implementation**

Refresh the valid `.orc` fixture so it is fully self-contained and encodes the exact bounded workflow shape:

- `BlockerClass`
- relpath contracts for design, plan, work reports, and implementation-state bundle
- `ImplementationAttemptInputs`
- `ImplementationAttemptPhaseCtx`
- internal union `ImplementationAttempt`
- boundary record `ImplementationAttemptSurfaceResult`
- `run-implementation-attempt` body shaped as:
  - `with-phase`
  - `let*` binding `attempt` from `provider-result`
  - `match` projecting both variants to `ImplementationAttemptSurfaceResult`

Refresh the invalid fixtures so they cover:

- `phase-target` used outside `with-phase`;
- `with-phase` given a non-`ImplementationAttemptPhaseCtx` context;
- quoted-symbol rejection with `(phase-target 'execution-report)` remaining a reader failure.

- [ ] **Step 2: Add failing reader and frontend tests for the bounded phase surface**

In `tests/test_workflow_lisp_reader.py`, add a failing reader test that opens `phase_target_quoted_symbol_invalid.orc` and asserts the existing `frontend_parse_error` contract remains intact.

In `tests/test_workflow_lisp_phase_translation.py`, add or refresh failing tests for:

- elaboration of `with-phase` and `phase-target`;
- rejection of `phase-target` outside `with-phase`;
- rejection of invalid phase-context type;
- rejection of nested `with-phase`;
- rejection of non-symbol or malformed `phase-target` arguments with `phase_target_name_invalid`;
- successful typing of the translated workflow while keeping `ImplementationAttempt` internal;
- continued extern-symbol resolution through `providers.execute` and `prompts.implementation.execute`.

Use or keep these test names where they fit:

```python
def test_elaborate_phase_translation_fixture_builds_with_phase_and_phase_target_nodes() -> None: ...
def test_typecheck_rejects_phase_target_outside_with_phase() -> None: ...
def test_typecheck_rejects_invalid_phase_context_record() -> None: ...
def test_typecheck_rejects_nested_with_phase() -> None: ...
```

- [ ] **Step 3: Add failing lowering and workflow-boundary expectations**

In `tests/test_workflow_lisp_lowering.py`, add or refresh failing assertions that the translated workflow lowers to:

- one compiler-generated prompt-input materialization prelude;
- one provider step with `variant_output`;
- `variant_output.path` sourced from the flattened phase-context bundle-path input;
- provider/prompt resolution via externs, not workflow inputs;
- workflow outputs limited to `return__implementation_state` and `return__implementation_state_bundle_path`;
- no hidden `__write_root__...` input for the translated phase workflow while existing Stage 3 fixtures still require those hidden inputs outside the slice.

In `tests/test_workflow_lisp_workflows.py`, keep one focused extern-symbol regression compatible with the stored selector:

```python
def test_phase_translation_fixture_uses_extern_symbols_without_workflow_transport() -> None: ...
```

- [ ] **Step 4: Run the narrowest pre-implementation checks**

Run:

```bash
python -m pytest tests/test_workflow_lisp_reader.py -q
python -m pytest --collect-only tests/test_workflow_lisp_phase_translation.py -q
```

Expected:

- the reader suite covers the quoted-symbol rejection contract;
- the new phase-translation module collects successfully;
- the new or changed assertions fail only for the missing phase implementation, not because of broken fixture syntax or missing test discovery.

## Task 2: Implement Phase AST Elaboration And Typechecking

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/phase.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `tests/test_workflow_lisp_phase_translation.py`

- [ ] **Step 1: Teach expression elaboration about `with-phase` and `phase-target`**

In `expressions.py`:

- extend `ExprNode` with `WithPhaseExpr` and `PhaseTargetExpr`;
- parse `(with-phase ctx phase-name body)` with:
  - `ctx` as a general expression;
  - `phase-name` as one authored symbol;
  - exactly one body expression;
- parse `(phase-target execution-report)` and `(phase-target progress-report)` as one-symbol target forms;
- reject strings, lists, keywords, or extra arguments with `phase_target_name_invalid`;
- preserve authored span and form-path data on both nodes.

Do not broaden the Stage 1 reader to support quoted symbols.

- [ ] **Step 2: Keep phase-scope metadata minimal and data-only**

In `phase.py`, implement or reconcile one small helper surface that:

- validates the exact `ImplementationAttemptPhaseCtx` record shape needed by this slice;
- exposes the allowed target-name to context-field mapping;
- exposes the bundle-path field name used by lowering;
- stays frontend-local and compile-time only.

Do not introduce a generic phase library.

- [ ] **Step 3: Thread active phase scope through typechecking**

In `typecheck.py`:

- add an optional active `PhaseScope` parameter through recursive checking;
- on `WithPhaseExpr`:
  - require the context expression to typecheck to `ImplementationAttemptPhaseCtx`;
  - reject nested phase scopes with `phase_scope_nested_unsupported`;
  - typecheck the body with the active scope installed;
- on `PhaseTargetExpr`:
  - reject when no phase scope is active with `phase_target_outside_with_phase`;
  - reject unknown target names with `phase_target_unknown`;
  - resolve the target to the corresponding relpath field type from the active context.

- [ ] **Step 4: Preserve the bounded return-shape rule inside phase bodies**

Keep the workflow boundary record-only. The translated body must consume the internal union inside `match` and project it to `ImplementationAttemptSurfaceResult`.

Reject any attempt to:

- return `ImplementationAttempt` directly from the workflow body;
- read variant-only fields outside `match`;
- use `phase-target` to derive any target other than `execution-report` or `progress-report`.

- [ ] **Step 5: Run the focused phase-form suite**

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_translation.py -q
```

Expected: the phase-form elaboration and typing tests pass before lowering changes begin.

## Task 3: Lower Phase-Scoped Provider Results Through The Existing Stage 3 Bridge

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_workflows.py`

- [ ] **Step 1: Make `with-phase` a compile-time-only lowering wrapper**

In `lowering.py`:

- lower `WithPhaseExpr` by lowering only its body;
- pass a lowering-local phase-scope object alongside the existing local-value context;
- record enough origin metadata that generated refs sourced from phase-context fields still remap shared-validation failures back to authored `.orc` spans.

- [ ] **Step 2: Lower `phase-target` to phase-context field refs**

Implement lowering rules so:

- `(phase-target execution-report)` resolves to the active context field `execution_report_target`;
- `(phase-target progress-report)` resolves to the active context field `progress_report_target`.

Do not lower `phase-target` into any helper command, pointer write, or derived-path script.

- [ ] **Step 3: Generate the prompt-input publication prelude**

Extend `provider-result` lowering inside active phase scope so the translated workflow gets one compiler-generated `materialize_artifacts` prelude that republishes:

- `design`
- `plan`
- `execution_report_target`
- `progress_report_target`

The provider step must then use ordinary:

- `consumes: [design, plan, execution_report_target, progress_report_target]`
- `prompt_consumes` in the same authored order

Do not invent a frontend-only prompt transport channel.

- [ ] **Step 4: Override the default structured-result bundle path only inside active phase scope**

When a union-returning `provider-result` executes inside an active `with-phase`:

- `variant_output.path` must come from `phase_ctx.implementation_state_bundle_path`;
- the translated workflow must not synthesize a hidden write-root input for that provider result;
- authored workflow outputs must still export only the boundary record fields.

Outside active phase scope, preserve current Stage 3 behavior unchanged.

- [ ] **Step 5: Keep compile entrypoints additive**

`compile_stage3_module(...)` remains the public compile entrypoint for this slice. Do not create a Stage 4-only compiler API. Export the new phase dataclasses from `__init__.py` only after the suite passes.

- [ ] **Step 6: Re-run the Stage 3 boundary and lowering regressions**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflows.py -k 'workflow_return_type_invalid or extern_symbols' -q
python -m pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q
```

Expected: existing Stage 3 regressions still pass while the translated phase fixture lowers through the shared seam.

## Task 4: Add Bounded Runtime Equivalence Coverage For Completed And Blocked Attempts

**Files:**

- Modify: `tests/test_workflow_lisp_phase_translation.py`
- Reuse: `tests/fixtures/v214_primitives/implementation_oracle/expected/completed.json`
- Reuse: `tests/fixtures/v214_primitives/implementation_oracle/expected/blocked.json`
- Reuse: `tests/fixtures/bin/fake_provider.py`

- [ ] **Step 1: Add one compile-and-execute helper for the translated fixture**

In `tests/test_workflow_lisp_phase_translation.py`, add a helper that:

- compiles `neurips_implementation_attempt.orc` through `compile_stage3_module(...)`;
- supplies externs:
  - `providers.execute -> fake`
  - `prompts.implementation.execute -> prompts/implementation/execute.md`
- validates the lowered workflow bundle;
- executes the validated bundle with `WorkflowExecutor` and `StateManager`.

Bind workflow inputs so the translated workflow receives:

- authoritative relpath inputs for design and plan placeholders;
- a phase-context bundle target path under the test workspace;
- execution and progress report targets under `artifacts/work`.

- [ ] **Step 2: Prove completed and blocked boundary behavior**

Add one runtime test per outcome:

- completed fake-provider scenario:
  - workflow output `implementation_state == "COMPLETED"`;
  - returned `implementation_state_bundle_path` points to an existing committed bundle;
  - committed bundle contains the execution-report path and no blocker payload.
- blocked fake-provider scenario:
  - workflow output `implementation_state == "BLOCKED"`;
  - committed bundle contains the progress-report path plus blocker class;
  - variant-only fields remain inside the committed bundle, not on the workflow boundary.

- [ ] **Step 3: Compare against the existing oracle expectations**

Assert that the translated workflow’s committed bundle shape matches the stable observations already encoded in:

- `tests/fixtures/v214_primitives/implementation_oracle/expected/completed.json`
- `tests/fixtures/v214_primitives/implementation_oracle/expected/blocked.json`

Do not compare literal prompt text or reintroduce report parsing into the test harness.

- [ ] **Step 4: Run the bounded runtime regressions**

Run:

```bash
python -m pytest tests/test_v214_runtime_semantics.py -k implementation_state -q
python -m pytest tests/test_neurips_steered_backlog_runtime.py -k implementation_phase_materializes_state_from_execution_report -q
```

Expected: the translated slice and the existing NeurIPS-family smoke still agree with the current behavior envelope.

## Task 5: Measure MVP Success Metrics And Record The Stage 5 Recommendation

**Files:**

- Create: `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/mvp_metrics_recommendation_report.md`
- Reuse: `workflows/library/neurips_backlog_implementation_phase.v214.yaml`
- Reuse: `tests/fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc`
- Reuse: `tests/test_workflow_lisp_phase_translation.py`
- Reuse: `tests/test_v214_runtime_semantics.py`
- Reuse: `tests/test_neurips_steered_backlog_runtime.py`

- [ ] **Step 1: Capture the required authoring-surface measurements with explicit baselines**

Measure and record, at minimum:

- authored line count for the equivalent YAML slice only:
  - `ExecuteImplementation`
  - `SelectImplementationOutcome`
  - `PublishCompletedExecutionReport`
  - `PublishBlockedProgressReport`
- authored line count for `tests/fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc`;
- manual state-path count in the translated `.orc` slice versus that same YAML slice;
- pointer-file count on the translated `.orc` surface;
- manually paired variant-check count on the translated `.orc` surface;
- markdown/text extractor count kept on the translated `.orc` surface;
- shell/Python glue command count kept on the translated `.orc` surface.

Use deterministic shell evidence where possible, for example:

```bash
python - <<'PY'
import pathlib

workflow_path = pathlib.Path("workflows/library/neurips_backlog_implementation_phase.v214.yaml")
step_names = {
    "ExecuteImplementation",
    "SelectImplementationOutcome",
    "PublishCompletedExecutionReport",
    "PublishBlockedProgressReport",
}

lines = workflow_path.read_text(encoding="utf-8").splitlines()
capture = False
captured = []
for line in lines:
    if line.startswith("  - name: "):
        capture = line.removeprefix("  - name: ").strip() in step_names
    if capture:
        captured.append(line)
print(len(captured))
PY
wc -l tests/fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc
rg -n "state_path|bundle_path|execution_report_target|progress_report_target" workflows/library/neurips_backlog_implementation_phase.v214.yaml tests/fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc
rg -n "pointer|extract|markdown|python -c|python3 -c|bash -c|sh -c" workflows/library/neurips_backlog_implementation_phase.v214.yaml tests/fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc
```

When using the full YAML file for `rg` evidence, count only occurrences inside the four-step equivalent slice and record excluded hits explicitly.

- [ ] **Step 2: Tie the metrics to behavior-equivalence evidence already produced by the focused suite**

Record the passing evidence from:

```bash
python -m pytest tests/test_workflow_lisp_phase_translation.py -q
python -m pytest tests/test_v214_runtime_semantics.py -k implementation_state -q
python -m pytest tests/test_neurips_steered_backlog_runtime.py -k implementation_phase_materializes_state_from_execution_report -q
```

Summarize which observations prove the translated slice still matches the current behavior envelope for completed and blocked outcomes.

- [ ] **Step 3: Write the MVP metrics and recommendation report**

In `mvp_metrics_recommendation_report.md`, include:

- a short scope statement confirming the report covers only the implementation-attempt translation slice;
- an explicit note that the authored-LOC and manual-boilerplate baseline is the four-step equivalent YAML slice, not the full implementation-phase workflow;
- a metric table for every item required by MVP Section 13;
- a pass/fail statement for each minimum success-bar requirement from MVP Section 13;
- a brief explanation of whether the `.orc` surface is materially less brittle than the equivalent YAML slice;
- one explicit final recommendation choosing exactly one:
  - `continue toward defmacro and procedural library work`
  - `revise the MVP`
  - `stop and invest in YAML ergonomics instead`

If the metrics do not clear the success bar, record that result and recommend `revise` or `stop`. Do not compensate by broadening implementation scope.

## Final Verification

Run this exact sequence before claiming the work complete:

```bash
python -m pytest tests/test_workflow_lisp_reader.py -q
python -m pytest --collect-only tests/test_workflow_lisp_phase_translation.py -q
python -m pytest tests/test_workflow_lisp_phase_translation.py -q
python -m pytest tests/test_workflow_lisp_workflows.py -k 'workflow_return_type_invalid or extern_symbols' -q
python -m pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q
python -m pytest tests/test_v214_runtime_semantics.py -k implementation_state -q
python -m pytest tests/test_neurips_steered_backlog_runtime.py -k implementation_phase_materializes_state_from_execution_report -q
```

If any selector fails:

- fix the implementation or the test expectation;
- do not weaken verification;
- do not broaden scope into the full implementation phase.

## Acceptance Checklist

The slice is complete only when all of the following are true:

- one real `.orc` workflow translates the NeurIPS implementation-attempt slice;
- `with-phase` and `phase-target` exist only to the bounded extent defined here;
- `phase-target` stays on the reader-compatible unquoted-symbol surface;
- quoted-symbol `phase-target` forms still fail at reader time;
- the translated workflow lowers through shared validation without YAML text;
- `provider-result` inside active phase scope writes its typed union bundle to the authoritative bundle path supplied by phase context;
- provider-result input expressions lower through the generated prompt-input materialization prelude plus ordinary provider-step `consumes` and `prompt_consumes`;
- completed and blocked runs both produce the expected boundary record and committed bundle contents;
- invalid phase-target usage, malformed phase-target names, and invalid phase-context usage fail at compile time;
- provider and prompt references stay on the existing extern boundary;
- the local `mvp_metrics_recommendation_report.md` records all MVP Section 13 metrics and one explicit Stage 5 recommendation;
- no new report parsing, pointer-as-state behavior, or inline semantic command glue appears on the `.orc` surface.
