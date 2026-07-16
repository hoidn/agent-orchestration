# Resume Projection-Integrity Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the accepted checksum-compatible resume projection-integrity contract across YAML loading, projection resolution, call-frame selection, root/callee lifecycle boundaries, diagnostics, and public resume behavior.

**Architecture:** Add projection-owned exact resume-slot resolution and one pure scope auditor. Run the root audit once in early CLI preflight and again only in structurally root executors immediately before prologue; run callee audits synchronously at the existing reached-call boundary after the accepted checksum/input guards and before the selected callee manager is created. Preserve distinct checksum envelopes, deterministic Workflow Lisp retry lineage, ordinary ancestor failure persistence, and sticky unchanged projection diagnostics.

**Tech Stack:** Python 3.11, pytest/pytest-xdist, PyYAML, immutable loaded workflow bundles, `WorkflowStateProjection`, `StateManager`, `WorkflowExecutor`, `CallExecutor`, CLI resume integration, tmux.

**Status:** Complete (verified 2026-07-16). Runtime implementation, focused
acceptance evidence, deterministic public CLI smoke, broad baseline comparison,
and independent specification/quality reviews are complete at `fdf1e06b`.
This closes only the generic resume projection-integrity hardening gate; it does
not claim that any procedure-first migration wave or YAML-retirement task is
implemented.

### Execution evidence and commit ledger

- Task 1 loader enforcement: `b095db21`, `af051c79`, `0b5aa4c5`, and
  `fdf1e06b`.
- Task 2 exact projection slots and validation: `d2b190a3`, `4ffa470e`, and
  `9bf3de5f`.
- Task 3 typed retry lineage and collision handling: `eef10140`, `745c6fdd`,
  and `35c97547`.
- Task 4 scoped auditor: `34491e7a`, `38447fd6`, and `86f23c25`.
- Task 5 atomic failure recording and forensic status: `80be1624` and
  `ffab73d1`.
- Task 6 early CLI and structurally-root auditing: `835f0921` and `a11f6ff1`.
- Task 7 reached-callee auditing: `218c4753`.
- Task 8 sticky propagation and original-error preservation: `b017203c` and
  `a5529b68`.
- Task 9 end-to-end and architecture proof: `30474820`, `fa99f9dc`, and
  `5daaedaf`.
- Task 10 verification-found corrections: `e7068d7a`, `ccbfc1cc`, `faef6f70`,
  `98fe51bf`, `0cfc1901`, and `fe640ab4`; the loader corrections above close
  the literal-repeat and merge-mediated import-section bypasses found during
  final review.
- Fresh syntax and focused gate: `python -m compileall -q orchestrator` passed;
  the seven owning modules collected 545 tests; the plan selector passed
  212 tests with 333 deselected.
- Fresh deterministic CLI smoke: a checksum-compatible state with an unknown
  explicit step ID failed closed with exit 1 and
  `unknown_explicit_step_id`; the marker remained `original` and the temporary
  root was removed.
- Fresh broad baseline comparison:
  `pytest -q -n 16 --dist=worksteal` exited 1 with
  `6 failed, 4913 passed, 13 skipped in 72.65s`. The exact six established
  unrelated baseline identities were:
  - `tests/test_workflow_output_contract_integration.py::test_provider_valid_output_bundle_overrides_raw_nonzero_exit`;
  - `tests/test_workflow_semantic_ir.py::test_semantic_ir_adds_typed_prompt_input_lineage_without_runtime_evidence`;
  - `tests/test_workflow_semantic_ir.py::test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys`;
  - `tests/test_workflow_semantic_ir.py::test_compiled_bundle_semantic_ir_preserves_command_boundary_classification`;
  - `tests/test_provider_role_routing.py::test_design_delta_drain_defaults_route_work_to_codex_gpt54`; and
  - `tests/test_neurips_steered_backlog_runtime.py::test_neurips_steered_backlog_runtime_drafts_gap_item_and_continues_without_relaunch`.
  No new hardening failure was introduced. This is a baseline-equivalence
  result, not an all-pass claim.
- Independent final specification and quality reviews approved `fdf1e06b`
  after the repeated and merge-mediated import-section corrections.

---

## Execution Contract

Run every command from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do **not** create or use a worktree. The repository policy for this tranche explicitly requires implementation in the current checkout.

Authoritative inputs:

- Accepted design at commit `52e2b05f`:
  `docs/design/resume_projection_integrity_hardening.md`
- Normative state contract:
  `specs/state.md`, section **Checksum-compatible resume projection integrity**
- Normative acceptance clauses:
  `specs/acceptance/index.md`, clauses 197 and 201-234
- Characterization evidence:
  `tests/test_workflow_state_projection.py`,
  `tests/test_subworkflow_calls.py`, and
  `tests/test_resume_command.py`

The accepted design is closed. This plan must not reopen its insertion points,
failure envelopes, checksum precedence, schema decision, or compatibility lane.

### Required implementation boundaries

- Keep state schema `2.1`.
- Keep the initial public CLI root-checksum mismatch byte-immutable and
  pre-construction.
- Use structured `workflow_checksum_mismatch` only for direct or post-CLI-race
  structurally root executor rechecks.
- Audit the root before CLI observability/session/process/executor mutations and
  rerun the audit immediately before prologue only for a structurally root
  `StateManager`.
- Child `_CallFrameStateManager` executors skip the root guard structurally;
  never pass a bypass flag.
- Keep reached-callee validation inside the existing
  `CallExecutor.execute_call` lifecycle, after the accepted input/write-root/
  checksum/resume-bound ordering and before `_CallFrameStateManager`.
- Preserve the existing parent call visit/start publication. Do not add a
  pre-publication seam.
- Keep root audit scope-local. Do not eagerly audit nested callee state at root.
- Use projection-owned candidate generation. No caller may parse, split,
  prefix-match, normalize, reconstruct, remap, or backfill qualified IDs.
- Preserve every recognized schema-supported omitted `steps.*.step_id` fallback
  lane; present IDs remain exact-validated.
- Use typed loaded-bundle `frontend_kind` for Workflow Lisp behavior. Do not
  select by path suffix, basename, workflow/module/procedure name, or migration
  family.
- Never read procedure-migration or identity-retirement evidence.
- Do not introduce receipts, persisted audit caches, schema migrations, or
  unrelated resume refactors.

### File responsibility map

- `orchestrator/loader.py`
  - Reject duplicate classic-YAML import aliases before bundle construction.
- `orchestrator/workflow/lowering.py`
  - Place the current authored import alias on `CallBoundaryProjection`.
- `orchestrator/workflow/state_projection.py`
  - Own typed resume slots, loop progress validation, exact resolution, and
    unclaimed-row detection.
- `orchestrator/workflow/resume_projection_integrity.py` (new)
  - Own diagnostic construction, pure scope audit, typed Workflow Lisp target
    classification, retry-lineage indexing, and sticky result classification.
- `orchestrator/state.py`
  - Own atomic three-field root projection/checksum recorders.
- `orchestrator/cli/commands/resume.py`
  - Own early root audit and public checksum/projection envelopes.
- `orchestrator/workflow/executor.py`
  - Own structural root revalidation, pre-prologue ordering, caller-scope error
    promotion, and sticky terminal routing.
- `orchestrator/workflow/calls.py`
  - Own reached-call revalidation, checksum/audit ordering, retry allocation,
    and unchanged child-error propagation.
- `orchestrator/workflow/loops.py`
  - Propagate sticky projection failure out of loop/container execution.
- `orchestrator/workflow/finalization.py`
  - Keep finalization failures supplemental when the root error is projection
    integrity.
- `orchestrator/observability/report.py`
  - Treat forensic `current_step` as non-live whenever root status/error is the
    accepted failed envelope.
- Existing tests listed in each task
  - Provide all RED/GREEN and public-path proof. Do not create helper-only proof
    that bypasses the default CLI/executor/call paths.

## Protected Working-Tree Guard

These paths are user-owned and outside this plan:

```text
docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md
docs/plans/2026-07-01-workflow-audit-tier-fixes.md
docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md
state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt
tests/test_workflow_non_progress_step_back_demo.py
workflows/examples/non_progress_step_back_demo.yaml
workflows/library/prompts/workflow_step_back/diagnose_non_progress.md
```

Before the first task, record but do not alter their status:

```bash
git status --short
```

Before **every** commit:

```bash
git diff --cached --name-only
git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md'
```

Expected: the first command lists only files named by the active task; the
second command prints nothing. Never stage, restore, rewrite, or clean a
protected path.

## Global Stop Conditions

Stop and return to the accepted design/spec owners if any of these occurs:

- Duplicate classic-YAML import aliases cannot be rejected before a
  last-wins mapping is constructed.
- Exact loop resolution requires parsing qualified ID strings outside
  `WorkflowStateProjection`.
- Legitimate current retry history cannot be represented by one typed lineage
  with deterministic ordinals and at most one running member.
- Failed retry predecessors cannot be checksum/audited in the accepted order.
- Root and child managers cannot be distinguished structurally without a
  caller-supplied bypass flag.
- Direct/post-CLI checksum mismatch cannot preserve the exact structured
  diagnostic and three-field root delta.
- The exact root projection delta requires normalizing or backfilling other
  state fields.
- The reached-callee audit must move ahead of current parent lifecycle or
  behind `_CallFrameStateManager` construction.
- Sticky projection failure cannot preserve ordinary failed records while
  bypassing authored routes, `on_error=continue`, and container continuation.
- Finalization or session closure cannot preserve the exact root diagnostic.
- Any implementation needs a receipt, persisted audit proof, eager nested root
  audit, pre-publication call seam, schema bump, evidence reader, suffix/name/
  family branch, or unrelated refactor.
- A failing test reveals a genuine existing contract regression. Do not weaken
  assertions or change accepted precedence merely to make it pass.

### Task 1: Reject Duplicate Classic-YAML Import Aliases

**Files:**

- Modify: `orchestrator/loader.py`
- Test: `tests/test_loader_validation.py`

- [x] **Step 1: Add RED loader tests**

Add these tests under `TestLoaderValidation`:

```python
def test_duplicate_import_alias_keys_are_rejected_before_bundle_construction(self):
    ...

def test_merge_induced_duplicate_import_alias_is_rejected_before_bundle_construction(self):
    ...
```

Use raw YAML text rather than `yaml.safe_dump`, because dictionaries cannot
represent duplicate authored keys. Assert `WorkflowValidationError` contains a
stable message such as:

```text
imports.child: duplicate import alias
```

Tripwire `build_loaded_workflow_bundle` so the test proves rejection happens
before bundle construction. Retain one positive unique-import test.

- [x] **Step 2: Collect and run the RED tests**

```bash
pytest --collect-only -q tests/test_loader_validation.py
pytest -q \
  tests/test_loader_validation.py::TestLoaderValidation::test_duplicate_import_alias_keys_are_rejected_before_bundle_construction \
  tests/test_loader_validation.py::TestLoaderValidation::test_merge_induced_duplicate_import_alias_is_rejected_before_bundle_construction
```

Expected: collection succeeds; both tests fail because `PreservingLoader`
currently accepts last-wins duplicate keys.

- [x] **Step 3: Implement import-boundary duplicate detection**

In `orchestrator/loader.py`, add a narrow node-level validator that:

```python
def _duplicate_import_aliases(
    loader: PreservingLoader,
    document: yaml.Node,
) -> tuple[str, ...]:
    """Return duplicate effective aliases from the top-level imports mapping."""
```

Requirements:

- Override `PreservingLoader.get_single_data()` with the same one-document
  control flow as PyYAML: call `get_single_node()` once, validate that composed
  document node, then call `construct_document(document)` once. Do not reopen,
  reread, or separately `yaml.compose()` the source.
- From that pre-construction document node, locate only the top-level
  `imports` value. If it is a mapping node, deep-copy that node, run
  `loader.flatten_mapping()` on the copy to expose YAML `<<` merge-derived
  effective aliases, construct only its key nodes with the active
  `PreservingLoader`, and detect repeated effective string aliases.
- Raise a stable YAML constructor/validation error from
  `PreservingLoader.get_single_data()` before normal document construction
  when duplicates exist. The existing `_load_workflow()` `yaml.load(...,
  Loader=PreservingLoader)` call remains the single source read and converts
  that failure into the normal `WorkflowValidationError` aggregation.
- Inspect only the top-level `imports` mapping.
- Account for direct duplicate scalar keys and YAML merge-derived effective
  duplicates.
- Preserve the existing `PreservingLoader` handling of keys such as `on`.
- The insertion point is the loader's composed-node hook reached by the
  existing `yaml.load` call at the start of `_load_workflow()`. It must reject
  before the constructed `workflow` mapping exists, and therefore before
  `_load_imports(workflow.get("imports"), ...)` and
  `build_loaded_workflow_bundle(...)`.
- Do not globally reject unrelated duplicate YAML mappings in this tranche.

- [x] **Step 4: Run loader verification**

```bash
pytest -q tests/test_loader_validation.py -k 'duplicate and import'
pytest -q tests/test_loader_validation.py -k 'import or call'
```

Expected: duplicate aliases reject before bundle construction; existing valid
classic YAML and Workflow Lisp import tests pass.

- [x] **Step 5: Commit**

```bash
git add orchestrator/loader.py tests/test_loader_validation.py
git diff --cached --check
# Run the protected-path guard from this plan.
git commit -m "Reject duplicate workflow import aliases"
```

### Task 2: Add Projection Resume Slots And Loop Validation

**Files:**

- Modify: `orchestrator/workflow/state_projection.py`
- Modify: `orchestrator/workflow/lowering.py`
- Test: `tests/test_workflow_state_projection.py`

- [x] **Step 1: Add RED typed-slot and loop tests**

Add:

```python
def test_projection_resume_slot_index_resolves_body_finalization_and_optional_omission(...):
    ...

def test_projection_resume_slot_index_accepts_all_repeat_until_progress_forms(...):
    ...

@pytest.mark.parametrize("corruption", [...])
def test_projection_resume_slot_index_rejects_invalid_loop_progress(...):
    ...

def test_projection_resume_slot_index_rejects_stale_loop_local_and_call_ids(...):
    ...

def test_call_boundary_projection_exposes_current_import_alias(...):
    ...
```

Cover:

- root body and finalization rows;
- completed, skipped, failed, and supported running result rows that omit
  `step_id`;
- valid `for_each` progress;
- active, terminal-success, successful-exhaustion, and failed-exhaustion
  `repeat_until` progress;
- boolean indices, duplicate/out-of-range indices, current/completed conflict,
  malformed containers, and invalid terminal combinations;
- stale loop-local and loop-contained call-boundary IDs;
- candidate multiplicity without duplicate-overwriting maps.

- [x] **Step 2: Collect and run RED selectors**

```bash
pytest --collect-only -q tests/test_workflow_state_projection.py
pytest -q tests/test_workflow_state_projection.py -k 'resume_slot_index or invalid_loop_progress or current_import_alias'
```

Expected: FAIL because reverse slot/index APIs and import alias metadata do not
exist.

- [x] **Step 3: Add minimal projection interfaces**

Implement immutable typed records in
`orchestrator/workflow/state_projection.py`:

```python
@dataclass(frozen=True)
class ResumeProjectionSlot: ...

@dataclass(frozen=True)
class ResumeProjectionSlotIndex:
    candidates_by_step_id: Mapping[str, tuple[ResumeProjectionSlot, ...]]
    call_boundaries_by_step_id: Mapping[str, tuple[ResumeProjectionSlot, ...]]
    unclaimed_explicit_rows: tuple[...]

@dataclass(frozen=True)
class ResumeIdentityResolution: ...

@dataclass(frozen=True)
class ResumeCallBoundaryResolution: ...
```

Add public methods:

```python
WorkflowStateProjection.enumerate_resume_slots(state)
WorkflowStateProjection.resolve_resume_step_id(slot_index, step_id, presentation_key=None)
WorkflowStateProjection.resolve_call_boundary(slot_index, call_step_id)
```

Add `import_alias: str` to `CallBoundaryProjection`, populated from the current
call node in `orchestrator/workflow/lowering.py`.

Candidate generation must use the existing forward formatters and validated
finite loop domains. Do not parse qualified IDs.

- [x] **Step 4: Run projection verification**

```bash
pytest -q tests/test_workflow_state_projection.py
pytest -q tests/test_resume_command.py -k 'projection and schema_boundary'
```

Expected: all projection tests pass; pre-v2.0 and pre-`2.1` reusable-call
rejection remains unchanged.

- [x] **Step 5: Commit**

```bash
git add \
  orchestrator/workflow/state_projection.py \
  orchestrator/workflow/lowering.py \
  tests/test_workflow_state_projection.py
git diff --cached --check
# Run the protected-path guard from this plan.
git commit -m "Add exact resume projection slots"
```

### Task 3: Add Typed Call-Frame Retry Lineage

**Files:**

- Create: `orchestrator/workflow/resume_projection_integrity.py`
- Modify: `orchestrator/workflow/calls.py`
- Test: `tests/test_subworkflow_calls.py`

- [x] **Step 1: Add RED lineage tests**

Add:

```python
def test_call_frame_retry_lineage_indexes_failed_history_and_next_id(...):
    ...

def test_call_frame_retry_lineage_allows_one_running_member_with_failed_history(...):
    ...

@pytest.mark.parametrize("invalid_lineage", [...])
def test_call_frame_retry_lineage_rejects_ambiguity_and_malformed_ordinals(...):
    ...

def test_workflow_lisp_retry_classification_uses_typed_frontend_kind_not_suffix(...):
    ...
```

Cover base ordinal `0`, `::retry::N`, deterministic next unused ordinal,
multiple running members, mixed bases, duplicate/missing/malformed ordinals,
nested retry markers, caller/alias mismatch, unlimited completed history, and
non-Workflow-Lisp multi-noncompleted ambiguity.

- [x] **Step 2: Collect and run RED selectors**

```bash
pytest --collect-only -q tests/test_subworkflow_calls.py
pytest -q tests/test_subworkflow_calls.py -k 'retry_lineage or typed_frontend_kind'
```

Expected: FAIL because typed lineage APIs do not exist and current selection is
mapping-order/suffix based.

- [x] **Step 3: Implement minimal lineage APIs**

Create `orchestrator/workflow/resume_projection_integrity.py` with:

```python
@dataclass(frozen=True)
class CallFrameMember: ...

@dataclass(frozen=True)
class RetryFrameMember(CallFrameMember):
    ordinal: int

@dataclass(frozen=True)
class CallFrameRetryLineage:
    base_frame_id: str
    completed_members: tuple[CallFrameMember, ...]
    failed_predecessors: tuple[RetryFrameMember, ...]
    running_member: CallFrameMember | None

def index_retry_lineage(boundary_step_id, frame_items, *, frontend_kind):
    ...

def next_unused_retry_frame_id(lineage: CallFrameRetryLineage) -> str:
    ...
```

Move selection policy out of `frame_id_with_overrides`; `CallExecutor` consumes
the typed index. Replace `_is_workflow_lisp_target` suffix behavior with
`LoadedWorkflowBundle.provenance.frontend_kind == "workflow_lisp"`.

- [x] **Step 4: Run lineage and existing call tests**

```bash
pytest -q tests/test_subworkflow_calls.py -k 'retry or call_frame'
```

Expected: typed lineage tests pass; the existing fresh-retry test still
allocates the next deterministic frame.

- [x] **Step 5: Commit**

```bash
git add \
  orchestrator/workflow/resume_projection_integrity.py \
  orchestrator/workflow/calls.py \
  tests/test_subworkflow_calls.py
git diff --cached --check
# Run the protected-path guard from this plan.
git commit -m "Add deterministic call frame retry lineage"
```

### Task 4: Implement The Pure Scoped Auditor

**Files:**

- Modify: `orchestrator/workflow/resume_projection_integrity.py`
- Test: `tests/test_workflow_state_projection.py`
- Test: `tests/test_subworkflow_calls.py`

- [x] **Step 1: Add RED pure-auditor tests**

Add:

```python
def test_resume_projection_auditor_accepts_valid_scope_and_omitted_result_ids(...):
    ...

@pytest.mark.parametrize("reason", [...])
def test_resume_projection_auditor_emits_exact_diagnostic_schema(...):
    ...

def test_resume_projection_auditor_rejects_stale_caller_and_alias_without_mutation(...):
    ...

def test_resume_projection_auditor_does_not_load_or_checksum_child_bundles(...):
    ...
```

Assert exact:

- `error.type == "resume_projection_integrity_error"`;
- `diagnostic_schema == "resume_projection_integrity_error.v1"`;
- every accepted reason enum;
- all required fields and explicit JSON-null values;
- identity-only bounded context;
- input state deep-equality before/after;
- no evidence reads and no child checksum/load.

- [x] **Step 2: Collect and run RED selectors**

```bash
pytest --collect-only -q \
  tests/test_workflow_state_projection.py \
  tests/test_subworkflow_calls.py
pytest -q \
  tests/test_workflow_state_projection.py \
  tests/test_subworkflow_calls.py \
  -k 'resume_projection_auditor'
```

Expected: FAIL because `audit_scope` and exact diagnostics do not exist.

- [x] **Step 3: Implement the pure auditor**

Add:

```python
@dataclass(frozen=True)
class ResumeScopePath: ...

class ResumeProjectionIntegrityError(ValueError):
    error: Mapping[str, Any]

def audit_scope(
    bundle: LoadedWorkflowBundle,
    state: Mapping[str, Any],
    scope_path: ResumeScopePath,
) -> None:
    ...
```

The auditor:

- calls only projection slot/resolution and typed frame-lineage APIs;
- audits local step/current IDs and locally stored frame caller/alias/lineage;
- preserves supported omitted step-result IDs;
- never writes, remaps, backfills, loads evidence, checksums child sources, or
  recursively enters child frame state.

- [x] **Step 4: Run pure-auditor and projection suites**

```bash
pytest -q tests/test_workflow_state_projection.py tests/test_subworkflow_calls.py -k 'projection or auditor or call_frame'
```

Expected: all focused tests pass with no state mutation.

- [x] **Step 5: Commit**

```bash
git add \
  orchestrator/workflow/resume_projection_integrity.py \
  tests/test_workflow_state_projection.py \
  tests/test_subworkflow_calls.py
git diff --cached --check
# Run the protected-path guard from this plan.
git commit -m "Add scoped resume projection auditor"
```

### Task 5: Add Atomic Root Failure Recorders

**Files:**

- Modify: `orchestrator/state.py`
- Modify: `orchestrator/observability/report.py`
- Test: `tests/test_state_manager.py`
- Test: `tests/test_observability_report.py`

- [x] **Step 1: Add RED recorder and forensic-status tests**

Under `TestStateManager`, add:

```python
def test_projection_failure_recorder_changes_exactly_three_root_fields(...):
    ...

@pytest.mark.parametrize("reason", [...])
def test_checksum_mismatch_recorder_persists_exact_structured_error(...):
    ...
```

In `tests/test_observability_report.py`, add:

```python
def test_failed_projection_envelope_treats_unchanged_current_step_as_forensic(...):
    ...
```

Snapshot the raw JSON object and whole run tree. Assert the recorder preserves
steps, visits, loops, frames, unknown compatible rows, omitted IDs,
observability, sidecars, backups, and child directories.

- [x] **Step 2: Collect and run RED selectors**

```bash
pytest --collect-only -q tests/test_state_manager.py tests/test_observability_report.py
pytest -q tests/test_state_manager.py tests/test_observability_report.py -k 'projection_failure_recorder or checksum_mismatch_recorder or forensic'
```

Expected: FAIL because dedicated recorders do not exist and `fail_run` mutates
`current_step`.

- [x] **Step 3: Implement atomic recorders**

Add to `StateManager`:

```python
def record_resume_projection_integrity_failure(self, error: Mapping[str, Any]) -> None:
    """Atomically change only status, error, and updated_at."""

def record_workflow_checksum_mismatch(
    self,
    *,
    workflow_file: str | None,
    persisted_checksum: str | None,
    current_checksum: str | None,
    reason: str,
) -> None:
    ...
```

Use one lock and one atomic state-file replacement. Do not call `fail_run`.
Preserve all other deserialized state exactly. Update report/status projection
so root failed status/error prevents a retained running `current_step` from
being presented as live.

- [x] **Step 4: Run recorder/report verification**

```bash
pytest -q tests/test_state_manager.py tests/test_observability_report.py
```

Expected: exact delta and diagnostic tests pass; existing report behavior
remains stable.

- [x] **Step 5: Commit**

```bash
git add \
  orchestrator/state.py \
  orchestrator/observability/report.py \
  tests/test_state_manager.py \
  tests/test_observability_report.py
git diff --cached --check
# Run the protected-path guard from this plan.
git commit -m "Add atomic resume integrity failure recorders"
```

### Task 6: Wire Early CLI And Structurally Root Executor Audits

**Files:**

- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/executor_runtime.py`
- Test: `tests/test_resume_command.py`

- [x] **Step 1: Replace characterization expectations with RED target tests**

Add or retarget:

```python
def test_projection_resume_root_cli_audit_precedes_override_session_process_and_executor(...):
    ...

def test_projection_resume_root_direct_executor_rechecks_checksum_and_audit_before_prologue(...):
    ...

def test_projection_resume_child_executor_skips_root_guard_structurally(...):
    ...

def test_projection_resume_post_cli_identity_race_uses_three_field_delta_and_closes_session(...):
    ...

@pytest.mark.parametrize("reason", [...])
def test_projection_resume_root_executor_checksum_mismatch_envelope(...):
    ...

@pytest.mark.parametrize(
    "entrypoint",
    ["resume_workflow", "default_cli"],
)
@pytest.mark.parametrize(
    "row_shape",
    ["completed", "skipped", "failed", "supported_running_loop_result"],
)
def test_public_resume_supported_omitted_step_id_is_not_backfilled(
    entrypoint,
    row_shape,
    ...,
):
    ...
```

Retain `test_default_resume_root_checksum_mismatch_is_pre_executor_and_byte_immutable`.
Tripwire prologue, planner, provider, command, call, logs, backups, and evidence
readers. For each omitted-ID case, build a recognized schema-valid `steps.*`
row that the existing presentation/name/order fallback supports, remove only
that row's optional `step_id`, and invoke the real public `resume_workflow`
function or the default CLI command. Assert the audit passes, the fixture's
normal resume control-flow/result/exit behavior occurs, and the persisted row
still has no `step_id`; do not accept a backfill as success.

- [x] **Step 2: Collect and run RED selectors**

```bash
pytest --collect-only -q tests/test_resume_command.py
pytest -q tests/test_resume_command.py -k 'projection_resume_root or root_executor_checksum or post_cli_identity_race or default_resume_root_checksum'
pytest -q tests/test_resume_command.py -k 'public_resume_supported_omitted_step_id'
```

Expected: target-order tests fail against the characterized late current
behavior. The omitted-ID selector is a positive compatibility guard: it may
already pass before wiring, but it must stay green throughout implementation
and must fail if the new public audit rejects or backfills any supported row.

- [x] **Step 3: Implement early CLI root audit**

In `resume_workflow`:

1. load state and apply existing schema rejection;
2. load the current root bundle and lowering-schema guard;
3. run the existing byte-immutable CLI checksum precheck;
4. call `audit_scope` before observability overrides/session/process/executor;
5. record root projection failure with the dedicated recorder, print the stable
   message, and return `1`;
6. continue existing lifecycle on success.

Do not alter force restart.

- [x] **Step 4: Implement structural executor revalidation**

Use the runtime-checkable `CallFrameStateManager` protocol plus defensive
`frame_id` check:

```python
def _is_structurally_root_state_manager(state_manager: Any) -> bool:
    ...
```

At the beginning of `WorkflowExecutor.execute(resume=True)`, before
`_execute_prologue`:

- structurally root only: rederive provenance workflow path, checksum, and
  rerun `audit_scope`;
- checksum failure: exact structured checksum recorder and failed state;
- projection failure: exact projection recorder and failed state;
- child manager: skip the entire root guard without a flag.

- [x] **Step 5: Run root integration tests**

```bash
pytest -q tests/test_resume_command.py -k 'checksum or projection_resume or schema_boundary or public_resume_supported_omitted_step_id'
```

Expected: initial CLI mismatch remains byte-identical; direct/post-CLI
structured envelopes and early audits pass; prologue/effects are not reached
on rejection; all completed/skipped/failed/supported-running omission cases
take normal public resume paths and remain absent without backfill.

- [x] **Step 6: Commit**

```bash
git add \
  orchestrator/cli/commands/resume.py \
  orchestrator/workflow/executor.py \
  orchestrator/workflow/executor_runtime.py \
  tests/test_resume_command.py
git diff --cached --check
# Run the protected-path guard from this plan.
git commit -m "Audit root resume before mutable execution"
```

### Task 7: Insert The Audit At The Actual Reached-Call Boundary

**Files:**

- Modify: `orchestrator/workflow/calls.py`
- Modify: `orchestrator/workflow/call_frame_state.py`
- Modify: `orchestrator/workflow/executor.py`
- Test: `tests/test_subworkflow_calls.py`

- [x] **Step 1: Add RED reached-call ordering tests**

Add:

```python
def test_reached_call_revalidates_boundary_alias_and_lineage_before_child_manager(...):
    ...

def test_reached_call_checksum_precedes_local_projection_failure(...):
    ...

def test_reached_call_running_workflow_lisp_guards_precede_failed_history_audit(...):
    ...

@pytest.mark.parametrize("status", ["running", "failed"])
@pytest.mark.parametrize(
    "winning_guard",
    ["call_resume_checksum_mismatch", "call_resume_bound_input_mismatch"],
)
def test_reached_call_non_workflow_lisp_resumable_guards_precede_local_audit(
    status,
    winning_guard,
    ...,
):
    ...

def test_reached_call_fresh_retry_audits_all_failed_history_before_allocation(...):
    ...

def test_reached_call_projection_failure_does_not_mutate_selected_callee(...):
    ...
```

Use real root/middle/leaf bundles. Assert the exact accepted order:

```text
bundle -> authored inputs -> lineage -> finalized inputs -> write root
-> running checksum/bound guards when present
-> failed-history checksum/audit in ordinal order
-> non-Workflow-Lisp resumable checksum then persisted resume-bound-input validation
-> resumable local audit
-> retry allocation
-> child manager -> child executor
```

For both the unique `running` member and the unique `failed`
non-Workflow-Lisp resumable member, seed a stale local projection identity plus
the selected checksum or persisted bound-input defect. Assert checksum is
checked first, persisted resume-bound-input validation is checked second when
checksum passes, and either mismatch wins unchanged without invoking the local
auditor or constructing the child manager.

- [x] **Step 2: Collect and run RED selectors**

```bash
pytest --collect-only -q tests/test_subworkflow_calls.py
pytest -q tests/test_subworkflow_calls.py -k 'reached_call or failed_history or selected_callee or non_workflow_lisp_resumable_guards'
```

Expected: FAIL because current call selection is map-order based and no local
audit occurs before child manager construction.

- [x] **Step 3: Integrate typed call revalidation**

Refactor `CallExecutor.execute_call` narrowly:

- derive current boundary from projection and current step identity;
- select bundle from boundary `import_alias`;
- cross-check persisted alias;
- reindex frames for race protection;
- preserve authored/finalized/write-root ordering;
- apply running checksum/resume-bound guards before history;
- checksum/audit failed predecessors ordinally;
- for the unique running or failed non-Workflow-Lisp resumable member, run the
  existing callee checksum validation first and its persisted
  resume-bound-input validation second; return either existing mismatch
  unchanged before any local audit;
- audit resumable local state;
- allocate fresh retry only after history passes;
- create `_CallFrameStateManager` only after all accepted guards pass.

Do not add a second child audit or mutate the selected frame on failure.

- [x] **Step 4: Run call integration**

```bash
pytest -q tests/test_subworkflow_calls.py -k 'projection_resume or call_frame or checksum or retry or non_workflow_lisp_resumable_guards'
```

Expected: missing/stale/ambiguous callers and aliases fail closed; checksum
and persisted resume-bound-input precedence remain distinct for unique running
and failed non-Workflow-Lisp frames; no selected-callee frame/effect mutation
occurs.

- [x] **Step 5: Commit**

```bash
git add \
  orchestrator/workflow/calls.py \
  orchestrator/workflow/call_frame_state.py \
  orchestrator/workflow/executor.py \
  tests/test_subworkflow_calls.py
git diff --cached --check
# Run the protected-path guard from this plan.
git commit -m "Audit selected callee before child construction"
```

### Task 8: Make Projection Failure Sticky Through Callers And Containers

**Files:**

- Modify: `orchestrator/workflow/resume_projection_integrity.py`
- Modify: `orchestrator/workflow/calls.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/loops.py`
- Modify: `orchestrator/workflow/finalization.py`
- Modify: `orchestrator/workflow/outcomes.py`
- Test: `tests/test_subworkflow_calls.py`
- Test: `tests/test_runtime_step_lifecycle.py`
- Test: `tests/test_resume_command.py`

- [x] **Step 1: Add RED sticky-propagation tests**

Add:

```python
def test_nested_projection_error_is_not_wrapped_in_call_failed(...):
    ...

def test_projection_error_bypasses_failure_success_always_and_on_error_continue(...):
    ...

def test_projection_error_exits_for_each_and_repeat_until_without_next_iteration(...):
    ...

def test_projection_error_finalization_failure_is_supplemental(...):
    ...

def test_projection_error_survives_epilogue_and_executor_session_close(...):
    ...
```

Use exact diagnostic deep equality across one- and two-level calls. Assert
ordinary parent step/current/visit/frame snapshots still persist.

- [x] **Step 2: Collect and run RED selectors**

```bash
pytest --collect-only -q \
  tests/test_subworkflow_calls.py \
  tests/test_runtime_step_lifecycle.py \
  tests/test_resume_command.py
pytest -q \
  tests/test_subworkflow_calls.py \
  tests/test_runtime_step_lifecycle.py \
  tests/test_resume_command.py \
  -k 'sticky_projection or projection_error or nested_projection'
```

Expected: FAIL because current calls wrap child failures as `call_failed`,
ordinary routing may continue, and successful epilogue may clear the error.

- [x] **Step 3: Implement typed sticky classification**

In `resume_projection_integrity.py`, add:

```python
class TerminalResultClass(Enum):
    STICKY_PROJECTION_INTEGRITY_FAILURE = ...
    ...

def projection_integrity_failed_result(error: Mapping[str, Any]) -> dict: ...
def classify_terminal_result(result: Mapping[str, Any]) -> TerminalResultClass: ...
```

Integrate it so:

- `CallExecutor` returns the exact child projection error, not `call_failed`;
- each caller promotes the same value to its scope/run error;
- `_handle_control_flow` recognizes sticky failure before authored routes and
  `on_error`;
- loop executors terminate the current container immediately;
- finalization may run but cannot replace/clear the projection error;
- failed epilogue and CLI session closure preserve the diagnostic.

Do not use an exception unwind.

- [x] **Step 4: Run lifecycle verification**

```bash
pytest -q \
  tests/test_subworkflow_calls.py \
  tests/test_runtime_step_lifecycle.py \
  tests/test_resume_command.py \
  -k 'projection or call_failed or on_error or finalization or session'
```

Expected: sticky tests pass and non-projection call/finalization behavior remains
unchanged.

- [x] **Step 5: Commit**

```bash
git add \
  orchestrator/workflow/resume_projection_integrity.py \
  orchestrator/workflow/calls.py \
  orchestrator/workflow/executor.py \
  orchestrator/workflow/loops.py \
  orchestrator/workflow/finalization.py \
  orchestrator/workflow/outcomes.py \
  tests/test_subworkflow_calls.py \
  tests/test_runtime_step_lifecycle.py \
  tests/test_resume_command.py
git diff --cached --check
# Run the protected-path guard from this plan.
git commit -m "Propagate sticky resume projection failures"
```

### Task 9: Prove Recursion, Negative Architecture, And Public Smoke

**Files:**

- Modify: `tests/test_workflow_state_projection.py`
- Modify: `tests/test_subworkflow_calls.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_loader_validation.py`
- Test: `tests/test_state_manager.py`
- Test: `tests/test_observability_report.py`

- [x] **Step 1: Add final RED/default-path proof**

Add integration tests covering:

```python
def test_projection_integrity_two_level_failure_preserves_exact_root_diagnostic(...):
    ...

def test_projection_integrity_loop_contained_call_uses_exact_boundary_candidate(...):
    ...

def test_projection_integrity_public_paths_never_call_retirement_readers(...):
    ...

def test_resume_projection_integrity_module_has_no_receipt_or_persisted_audit_cache(...):
    ...

def test_resume_projection_integrity_module_does_not_import_or_call_retirement_readers(...):
    ...

def test_retry_target_and_projection_resolution_functions_use_typed_identity_only(...):
    ...
```

Use behavioral tripwires around the known retirement/migration evidence-reader
entrypoints while exercising the real public loader, `resume_workflow`,
structurally root executor, and reached-call paths. Separately use scoped
static/AST assertions:

- parse only the new
  `orchestrator/workflow/resume_projection_integrity.py` module to assert it
  contains no receipt/cache imports or calls and no imports/calls to the known
  retirement or procedure-migration evidence readers;
- inspect only the exact typed retry-target classifier/lineage functions in
  `resume_projection_integrity.py` and the exact resume-slot/call-boundary
  resolution methods added to `WorkflowStateProjection`;
- reject suffix/basename/workflow-name/module-name/procedure-name/family
  selection and caller-side split/prefix parsing inside those exact functions,
  while allowing unrelated pre-existing runtime code outside the new seams;
- keep the behavioral public-path tripwires as the proof that no indirect
  retirement reader is reached.

Do not scan the whole runtime for generic words such as `family`, `name`, or
`suffix`, and do not refactor unrelated existing code merely to satisfy an
architecture test.

- [x] **Step 2: Collect and run focused proof**

```bash
pytest --collect-only -q \
  tests/test_workflow_state_projection.py \
  tests/test_subworkflow_calls.py \
  tests/test_resume_command.py \
  tests/test_loader_validation.py \
  tests/test_state_manager.py \
  tests/test_observability_report.py
pytest -q \
  tests/test_workflow_state_projection.py \
  tests/test_subworkflow_calls.py \
  tests/test_resume_command.py \
  tests/test_loader_validation.py \
  tests/test_state_manager.py \
  tests/test_observability_report.py \
  -k 'projection_integrity or resume_projection or retry_target_and_projection_resolution or duplicate_import'
```

Expected: all accepted clauses have executable default-path proof.

- [x] **Step 3: Run deterministic CLI smoke in a dedicated temporary root**

Run from the repository root:

```bash
set -euo pipefail
REPO_ROOT="$PWD"
SMOKE_ROOT="$(mktemp -d)"
trap 'rm -rf "$SMOKE_ROOT"' EXIT

mkdir -p "$SMOKE_ROOT/workspace"
printf '%s\n' \
  'version: "2.0"' \
  'name: resume-projection-smoke' \
  'steps:' \
  '  - name: WriteMarker' \
  '    id: write_marker' \
  '    command: ["bash", "-lc", "printf original > marker.txt"]' \
  > "$SMOKE_ROOT/workspace/workflow.yaml"

(
  cd "$SMOKE_ROOT/workspace"
  PYTHONPATH="$REPO_ROOT" python -m orchestrator run \
    workflow.yaml \
    --state-dir "$SMOKE_ROOT/runs"
)

STATE_FILE="$(find "$SMOKE_ROOT/runs" -mindepth 2 -maxdepth 2 -name state.json -print -quit)"
test -n "$STATE_FILE"
RUN_ID="$(basename "$(dirname "$STATE_FILE")")"

python - "$STATE_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
state = json.loads(path.read_text(encoding="utf-8"))
row = state["steps"]["WriteMarker"]
row["step_id"] = "root.removed_write_marker"
path.write_text(json.dumps(state, indent=2), encoding="utf-8")
PY

set +e
SMOKE_OUTPUT="$(
  cd "$SMOKE_ROOT/workspace"
  PYTHONPATH="$REPO_ROOT" python -m orchestrator resume \
    "$RUN_ID" \
    --state-dir "$SMOKE_ROOT/runs" 2>&1
)"
SMOKE_RC=$?
set -e

test "$SMOKE_RC" -eq 1
printf '%s\n' "$SMOKE_OUTPUT" | grep -iF 'resume projection'
python - "$STATE_FILE" <<'PY'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert state["status"] == "failed"
assert state["error"]["type"] == "resume_projection_integrity_error"
assert state["steps"]["WriteMarker"]["step_id"] == "root.removed_write_marker"
PY
test "$(cat "$SMOKE_ROOT/workspace/marker.txt")" = "original"
```

Expected: initial run succeeds; checksum-compatible corrupted resume exits `1`
with the projection diagnostic; the completed command is not executed again.

- [x] **Step 4: Commit integration proof**

```bash
git add \
  tests/test_workflow_state_projection.py \
  tests/test_subworkflow_calls.py \
  tests/test_resume_command.py \
  tests/test_loader_validation.py
git diff --cached --check
# Run the protected-path guard from this plan.
git commit -m "Prove resume projection integrity end to end"
```

### Task 10: Run Full Verification And Handoff

**Files:**

- Verify only; do not create a verification-only source commit.

- [x] **Step 1: Run syntax, collection, and focused suites**

```bash
python -m compileall -q orchestrator
pytest --collect-only -q \
  tests/test_loader_validation.py \
  tests/test_workflow_state_projection.py \
  tests/test_subworkflow_calls.py \
  tests/test_resume_command.py \
  tests/test_state_manager.py \
  tests/test_runtime_step_lifecycle.py \
  tests/test_observability_report.py
pytest -q \
  tests/test_loader_validation.py \
  tests/test_workflow_state_projection.py \
  tests/test_subworkflow_calls.py \
  tests/test_resume_command.py \
  tests/test_state_manager.py \
  tests/test_runtime_step_lifecycle.py \
  tests/test_observability_report.py \
  -k 'projection or checksum or call_frame or retry or loop or finalization or duplicate_import'
```

Expected: compilation and collection succeed; focused suite passes.

- [x] **Step 2: Run the orchestrator smoke again**

Repeat Task 9 Step 3 from a new `mktemp -d` root.

Expected: deterministic exit `1`, exact root projection diagnostic, and no
effect replay.

- [x] **Step 3: Run the broad suite in tmux**

Use the `tmux` skill to open a repository-root pane. Run exactly:

```bash
pytest -q -n 16 --dist=worksteal
```

Keep the command in tmux until it exits. Record the fresh command, exit code,
pass/fail count, and any warnings. Do not infer success from prior runs or
inspection.

- [x] **Step 4: Inspect the final diff and protected paths**

```bash
git status --short
git diff --check
git diff --stat
git diff --name-only
git diff --cached --name-only
```

Expected:

- no whitespace errors;
- no staged files after the task commits;
- protected dirty paths remain user-owned and untouched;
- implementation changes are limited to files named in this plan;
- no receipt, schema bump, evidence reader, family/suffix selector, eager nested
  root audit, pre-publication seam, or unrelated refactor.

- [x] **Step 5: Produce the execution handoff**

Report:

- commits created by Tasks 1-9;
- focused and broad verification results;
- deterministic smoke result and temporary-root cleanup;
- exact accepted failure envelopes exercised;
- any remaining warnings;
- `git status --short`, explicitly separating pre-existing protected dirt from
  task changes.

Do not create a verification-only commit. If Task 10 exposes a defect, return
to the smallest owning task, add a RED regression test, implement the minimal
fix, rerun that task and Task 10, and commit the fix with the same protected-path
guard.
