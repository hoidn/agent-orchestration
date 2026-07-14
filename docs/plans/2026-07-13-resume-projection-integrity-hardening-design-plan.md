# Resume Projection Integrity Hardening Design And Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce and accept a generic target design, normative state/acceptance contract, and independently reviewed detailed implementation plan for checksum-compatible resume projection-integrity auditing.

**Architecture:** Characterize the current root, nested-call, loop, CLI, executor, state-mutation, and observability order before choosing an audit insertion point or persisted-state delta. The accepted target must recursively validate every explicit durable resume identity against the projection that owns its scope while preserving current compatibility for otherwise schema-valid supported rows that omit the optional `step_id`; runtime changes are deferred to the subsequent implementation plan.

**Tech Stack:** Markdown design/specification documents, Python/pytest characterization probes, `WorkflowStateProjection`, `ResumePlanner`, call-frame state, imported workflow bundles, orchestrator CLI, git.

---

## Authority, sequencing, and scope

- Normative state authority: `specs/state.md` and `specs/acceptance/index.md`.
- Design source: `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`, especially **Separate runtime-hardening follow-up**.
- Design structure: `docs/templates/design_template.md`.
- Current implementation evidence:
  - `orchestrator/workflow/resume_planner.py`
  - `orchestrator/workflow/state_projection.py`
  - `orchestrator/workflow/calls.py`
  - `orchestrator/workflow/call_frame_state.py`
  - `orchestrator/cli/commands/resume.py`
  - `orchestrator/workflow/executor.py`
  - `tests/test_workflow_state_projection.py`
  - `tests/test_resume_command.py`
  - `tests/test_subworkflow_calls.py`
- Schedule this work after the internal tracked-plan pilot and before any procedure-first production migration wave. It does not block the internal pilot because changed source is rejected by the existing root checksum guard before the uncovered checksum-compatible path is reached.
- This is a design-and-planning plan, not the runtime implementation plan. Tasks may add characterization/probe tests and update durable documentation, but must not modify runtime Python, state serializers, CLI behavior, workflow sources, or migration evidence.
- Do not create a worktree. Run every command from the repository root.
- The hardening is generic. No design, spec, test selector, diagnostic, code sketch, or later implementation task may select behavior from a workflow, module, procedure, migration family, or basename.
- Procedure-identity retirement records remain evidence-only. The resume CLI, planner, executor, projection resolver, call-frame loader, and state manager must not discover, load, require, or interpret a retirement record.
- Architecture, audit insertion point, persistence/state delta, schema impact, mutation ordering, and observability ordering are unresolved until Tasks 1 and 2 pass independent review. Do not infer any of them from the earlier migration design.

## Protected working-tree guard

The following user-owned dirty paths are outside every task in this plan:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

Before every commit, run `git diff --cached --name-only`, then run:

```bash
git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md'
```

The literal protected-path command must print nothing; the full staged list
must be a subset of the active task's `Files` list. Never stage, restore, or
rewrite a protected path. Record its initial `git status --short` output only
as a guard baseline; user changes to those paths are not plan failures.

## Required target contract

The reviewed design and later implementation plan must preserve all of these requirements:

1. Audit only checksum-compatible ordinary resume. Existing root and callee checksum rejection remain authoritative and are not weakened, bypassed, or replaced.
2. Root-level persisted rows are resolved against the retained entry workflow's current `WorkflowStateProjection`.
3. A persisted call frame's `call_step_id` is resolved against its parent projection and must identify exactly one parent call boundary. That boundary, not the persisted import alias alone, selects the current callee bundle under existing import-resolution and checksum rules.
4. The selected current callee bundle's projection owns the call-frame-local state. Apply the same rules recursively to its explicit step identities and nested call frames.
5. Loop-local and loop-contained call identities use the existing projection-qualified ancestry/runtime-ID APIs. Do not split, normalize, prefix-match, or reconstruct qualified IDs with new ad hoc string parsing.
6. Otherwise schema-valid supported rows that omit the optional `step_id` retain current compatibility through the existing name/order compatibility lane. The audit neither rejects them merely for that omission nor backfills or rewrites them during resume. This compatibility does not admit pre-v2.0 state or pre-`schema_version: "2.1"` reusable-call state: both remain rejected unless a tested upgrader ships with the same tranche.
7. An explicit durable ID that cannot be resolved in its owning scope, resolves outside that scope, or has more than one possible scoped owner fails closed before provider, command, transition, publication, child-workflow, or other workflow effects.
8. The target design explicitly decides the audit placement relative to workflow load, root checksum validation, observability overrides, executor-session open/write, `WorkflowExecutor` construction, managed/runtime-context binding, provider-session quarantine, restart planning, call-frame creation, and callee checksum validation.
9. The target design explicitly decides whether a failed audit mutates `state.json`, run status/error, `updated_at`, executor-session metadata, process metadata, logs, sidecars, backups, or nothing at all; it also decides whether the existing state schema is sufficient. No implementation-plan author may invent this state delta.
10. Failure observability is operator-actionable and stable without leaking private callee state. The design must specify error type, scope path, offending field/value, expected projection owner, ambiguity/missing-resolution reason, CLI exit behavior, and report/status visibility.
11. Projection-integrity auditing has no retirement-record dependency and no workflow-family special case. A negative architecture test must prove the default runtime path does not read retirement evidence.

## File responsibility map

- `tests/test_workflow_state_projection.py`: projection-resolution and schema-valid optional-`step_id` compatibility probes, including qualified loop ancestry.
- `tests/test_subworkflow_calls.py`: parent-boundary-to-current-callee selection, recursive nested-frame, checksum-order, and ambiguous/missing scoped-resolution probes.
- `tests/test_resume_command.py`: public CLI mutation/observability/executor-construction ordering probes for checksum-compatible resume.
- `docs/design/resume_projection_integrity_hardening.md`: generic target design and the sole design authority for insertion, state delta, failure, recursion, and compatibility decisions.
- `specs/state.md`: normative checksum-compatible resume integrity, compatibility, mutation, and state/schema contract accepted from the design.
- `specs/acceptance/index.md`: public positive and negative acceptance clauses plus executable-proof routing.
- `docs/design/README.md`: target-design discoverability after review.
- `docs/plans/2026-07-13-resume-projection-integrity-hardening-implementation-plan.md`: detailed TDD implementation plan written only after design/spec acceptance.
- `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`: cross-plan order and live selector handoff.
- `docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`: explicit production-wave prerequisite.
- `docs/index.md` and `docs/capability_status_matrix.md`: discoverability and designed-versus-implemented status; neither owns runtime semantics.

### Task 1: Prove Feasibility And Freeze Current Mutation Ordering

**Files:**
- Modify: `tests/test_workflow_state_projection.py`
- Modify: `tests/test_subworkflow_calls.py`
- Modify: `tests/test_resume_command.py`
- Inspect: `orchestrator/workflow/resume_planner.py`
- Inspect: `orchestrator/workflow/state_projection.py`
- Inspect: `orchestrator/workflow/calls.py`
- Inspect: `orchestrator/workflow/call_frame_state.py`
- Inspect: `orchestrator/cli/commands/resume.py`
- Inspect: `orchestrator/workflow/executor.py`

- [ ] **Step 1: Record the clean task baseline and current call order**

Capture `git status --short`, then trace the public resume path from state load through workflow/bundle load, checksum validation, observability override persistence, executor-session persistence, executor construction, executor prologue, restart planning, and nested call entry. Record exact symbol/path anchors in test docstrings or test names, not line-number authority.

- [ ] **Step 2: Add a root/loop projection feasibility matrix**

Use generated temporary workflows and the public `WorkflowStateProjection` APIs. Cover a root completed row with a valid explicit ID, a stale explicit ID, a mismatched presentation key, a finalization row, nested `repeat_until` and `for_each` rows, and a loop-contained call boundary. Prove the existing APIs can enumerate or resolve the qualified ancestry without parsing ID strings. Also cover an otherwise schema-valid supported row that omits the optional `step_id`; record the existing compatibility behavior without adding one. Separately prove that pre-v2.0 state and pre-`schema_version: "2.1"` reusable-call state remain rejected without a tested upgrader.

- [ ] **Step 3: Add current-callee and recursive-frame feasibility probes**

Build generic two-level imported-call fixtures with distinct projections. Prove that the parent call boundary can select exactly one current imported bundle, that its checksum can be evaluated with the existing call checksum rules, and that the selected bundle exposes the projection required to audit its local rows and nested frame. Add missing alias, missing boundary, duplicate/ambiguous scoped candidate, stale caller ID, stale callee-local ID, and nested checksum-mismatch cases. Do not introduce a family-specific fixture or consult retirement evidence.

- [ ] **Step 4: Characterize the mutation and observability envelope**

For checksum-compatible integrity failures, instrument the public CLI and direct executor paths and snapshot the run tree before/after. Record whether each candidate checkpoint has already allowed:

- observability override persistence;
- executor-session open/write and close/write;
- process metadata writes;
- `WorkflowExecutor` construction;
- entry managed-write-root or runtime-context binding;
- status/error/`updated_at` mutation;
- provider-session quarantine metadata;
- parent step/visit/current-step mutation before a nested failure; and
- child frame or sidecar creation.

Include a default resume with no observability overrides, a resume with overrides, direct executor resume, root explicit-ID corruption, nested caller-ID corruption, and callee-local corruption. These are characterization probes, not the insertion-point decision.

- [ ] **Step 5: Run the feasibility selectors**

```bash
pytest --collect-only -q tests/test_workflow_state_projection.py tests/test_subworkflow_calls.py tests/test_resume_command.py
pytest -q tests/test_workflow_state_projection.py tests/test_subworkflow_calls.py tests/test_resume_command.py -k 'projection and (resume or integrity or call_frame or mutation_order or optional_step_id or schema_boundary)'
```

Expected: collection succeeds and every probe passes while documenting the current gap and exact mutation order. If scoped callee selection or loop-qualified reverse resolution cannot be demonstrated through existing APIs, record that as an explicit design prerequisite; do not add runtime helpers in this task.

- [ ] **Step 6: Review and commit characterization evidence only**

Obtain an independent test/evidence review that checks fixture genericity, checksum compatibility, recursion depth, absence-of-ID compatibility, ambiguity negatives, and before/after mutation snapshots. Resolve findings and rerun the full focused selector.

```bash
git diff --check -- tests/test_workflow_state_projection.py tests/test_subworkflow_calls.py tests/test_resume_command.py
git add tests/test_workflow_state_projection.py tests/test_subworkflow_calls.py tests/test_resume_command.py
git commit -m "Characterize resume projection integrity ordering"
```

### Task 2: Draft And Accept The Generic Target Design

**Files:**
- Create: `docs/design/resume_projection_integrity_hardening.md`
- Modify: `docs/design/README.md`
- Inspect: `docs/templates/design_template.md`
- Inspect: `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`
- Inspect: `docs/design/workflow_lisp_state_layout.md`
- Inspect: Task 1 test evidence

- [ ] **Step 1: Compare insertion architectures from the measured order**

Evaluate at least: CLI pre-executor audit, executor-prologue audit, planner-owned audit, and split root/call-boundary audit. Compare recursive bundle availability, direct-executor coverage, mutation-before-failure, observability behavior, call-frame recursion, checksum ordering, testability, and ownership cohesion. Recommend one architecture; do not select an option merely because it requires the fewest edits.

- [ ] **Step 2: Write the target design from the repository template**

The design must include metadata, context/authority, problem, goals/non-goals, decision and alternatives, recursive control/data flow, contracts, sequencing, invariants/failure modes, operations/observability, compatibility/migration, evidence boundaries, verification, declarative acceptance scenarios, stop/revise criteria, documentation impact, and implementation handoff.

It must settle every item in **Required target contract**, including:

- root entry projection ownership;
- parent call-boundary ownership of caller IDs;
- import/checksum-based current-callee bundle selection;
- recursively callee-owned local state;
- qualified loop ancestry through existing APIs;
- current compatibility for otherwise schema-valid supported rows that omit the optional `step_id`, while retaining pre-v2.0 and pre-`schema_version: "2.1"` reusable-call rejection without a tested upgrader;
- missing/ambiguous resolution failure;
- precise audit insertion and ordering;
- precise failure-state/schema delta;
- observability and operator diagnostics;
- absence of retirement-record/runtime coupling; and
- structural genericity with no family names.

- [ ] **Step 3: Include declarative positive and negative scenarios**

At minimum cover: valid root resume; stale root completed ID; an otherwise schema-valid supported root row that omits the optional `step_id`; rejection of pre-v2.0 state without a tested upgrader; rejection of pre-`schema_version: "2.1"` reusable-call state without a tested upgrader; loop-local valid/stale ID; valid one-level and two-level call frames; stale parent caller ID; missing/ambiguous call boundary; missing/ambiguous imported bundle; callee checksum mismatch preserving its existing boundary; stale callee-local ID; nested stale ID; and proof that retirement evidence is absent and unread.

- [ ] **Step 4: Obtain independent specification and architecture reviews**

The specification review checks every required contract and compatibility claim against `specs/state.md` and Task 1 evidence. The architecture review independently challenges insertion point, recursive ownership, current-callee selection, state/schema delta, mutation envelope, and observability order. A separate quality pass checks stable terminology, genericity, testability, and absence of family names or hidden retirement coupling. Fix and rerun the whole review set until all pass.

- [ ] **Step 5: Accept and commit the design only**

Set design status to `accepted` only after all reviews pass and no core decision remains in Open Questions.

```bash
git diff --check -- docs/design/resume_projection_integrity_hardening.md docs/design/README.md
git add docs/design/resume_projection_integrity_hardening.md docs/design/README.md
git commit -m "Design resume projection integrity hardening"
```

### Task 3: Merge The Accepted State And Acceptance Contract

**Files:**
- Modify: `specs/state.md`
- Modify: `specs/acceptance/index.md`
- Inspect: `docs/design/resume_projection_integrity_hardening.md`

- [ ] **Step 1: Add the normative state contract**

Promote the accepted durable behavior, not live scheduling: checksum-compatible audit scope, recursive projection ownership, explicit-ID fail-closed behavior, current compatibility for otherwise schema-valid supported rows that omit the optional `step_id`, chosen mutation/state delta, schema decision, diagnostic surface, and observability ordering. Explicitly preserve rejection of pre-v2.0 state and pre-`schema_version: "2.1"` reusable-call state unless a tested upgrader ships with the same tranche. Preserve the distinct existing root- and callee-checksum contracts.

- [ ] **Step 2: Add acceptance clauses and executable-proof routing**

Add positive, negative, recursive, loop-qualified, schema-valid optional-`step_id` compatibility, schema-boundary rejection, current-callee selection, mutation-order, and no-retirement-read clauses. Map each clause to the public CLI/integration tests that the later implementation plan must produce; do not treat Task 1 characterization of the gap as implementation proof.

- [ ] **Step 3: Run a focused contract-drift sweep**

```bash
rg -n "projection.integrity|checksum.compatible|call.frame|durable.*id|retirement" specs/state.md specs/acceptance/index.md docs/design/resume_projection_integrity_hardening.md docs/design/workflow_lisp_procedure_migration_identity_compatibility.md
git diff --check -- specs/state.md specs/acceptance/index.md
```

Expected: one coherent contract, no claim that the hardening is already implemented, and no weakening of checksum rules, pre-v2.0 rejection, or pre-`schema_version: "2.1"` reusable-call rejection.

- [ ] **Step 4: Obtain independent normative and quality reviews, then commit**

The normative review checks the spec delta against the accepted design and every acceptance scenario. The quality review checks authority placement, non-duplication, terminology, and executable-proof routing. Resolve findings and rerun both whole reviews.

```bash
git add specs/state.md specs/acceptance/index.md
git commit -m "Specify resume projection integrity auditing"
```

### Task 4: Write And Accept The Detailed Runtime Implementation Plan

**Files:**
- Create: `docs/plans/2026-07-13-resume-projection-integrity-hardening-implementation-plan.md`
- Inspect: `docs/design/resume_projection_integrity_hardening.md`
- Inspect: `specs/state.md`
- Inspect: `specs/acceptance/index.md`
- Inspect: Task 1 characterization tests

- [ ] **Step 1: Invoke `superpowers:writing-plans` against the accepted authorities**

Draft a standalone implementation plan with the required checkbox header, exact runtime/test/doc paths, RED/GREEN ordering, small commits, expected failure messages, exact commands, and stop conditions. Do not use a worktree. The plan must be executable by an engineer with no access to this meta-plan's reasoning.

- [ ] **Step 2: Preserve design decisions rather than reopening them**

The implementation plan must name the accepted insertion point and state delta, recursive resolver ownership, exact public integration tests, observability behavior, checksum order, the current lane for otherwise schema-valid supported rows that omit the optional `step_id`, explicit tests preserving pre-v2.0 and pre-`schema_version: "2.1"` reusable-call rejection without a tested upgrader, and missing/ambiguous failures. It must forbid ID string parsing, retirement-record loading, schema invention, family-specific branches, and unrelated resume refactors.

- [ ] **Step 3: Require TDD and end-to-end evidence**

Start with RED tests derived from the normative acceptance clauses. Include focused unit tests, root CLI integration, recursive nested-frame integration, loop-contained call integration, before/after persisted-tree assertions, provider/command non-execution assertions, no-retirement-read architecture test, and an orchestrator resume smoke check. End with the repository broad suite in tmux:

```bash
pytest -q -n 16 --dist=worksteal
```

- [ ] **Step 4: Obtain independent plan-document review**

Review the complete plan against the accepted design and normative specs. Independently check task granularity, exact paths, RED/GREEN sequence, recursive coverage, mutation/observability assertions, schema fidelity, commit isolation, and full-suite/smoke gates. Fix and rereview the entire plan until approved.

- [ ] **Step 5: Commit the reviewed implementation plan only**

```bash
git diff --check -- docs/plans/2026-07-13-resume-projection-integrity-hardening-implementation-plan.md
git add docs/plans/2026-07-13-resume-projection-integrity-hardening-implementation-plan.md
git commit -m "Plan resume projection integrity implementation"
```

Do not execute the runtime implementation plan in this design-and-planning tranche.

### Task 5: Route The Reviewed Hardening Before Production Migration Waves

**Files:**
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify: `docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`
- Modify: `docs/index.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/plans/2026-07-13-resume-projection-integrity-hardening-design-plan.md`

- [ ] **Step 1: Add the explicit roadmap gate**

Keep the internal pilot unblocked. Route this reviewed design/spec/implementation-plan tranche immediately after the pilot, then route execution of its accepted implementation plan before procedure-first production migration waves. Make the migration-wave plan fail its prerequisite gate if the hardening implementation and its acceptance evidence are incomplete.

- [ ] **Step 2: Update discoverability and status without claiming implementation**

Route the accepted design and both plans from `docs/index.md`. Add a capability-matrix row or update the closest row to distinguish `designed/planned` from `implemented`. Do not put live selector status into the durable design or normative state spec.

- [ ] **Step 3: Obtain final holistic specification and quality reviews**

Review the target design, spec/acceptance delta, detailed implementation plan, roadmap dependency, mutation-order evidence, and protected-path discipline as one set. Require explicit PASS for: generic recursive contract; insertion/state/observability decision completeness; compatibility for otherwise schema-valid supported rows that omit the optional `step_id`; preserved pre-v2.0 and pre-`schema_version: "2.1"` reusable-call rejection without a tested upgrader; fail-closed ambiguity; no retirement/runtime coupling; no family names; pilot non-blocking; and production-wave blocking.

- [ ] **Step 4: Run final validation**

Run the focused characterization suite, then the broad suite in tmux as required by repository policy:

```bash
pytest -q tests/test_workflow_state_projection.py tests/test_subworkflow_calls.py tests/test_resume_command.py -k 'projection and (resume or integrity or call_frame or mutation_order or optional_step_id or schema_boundary)'
pytest -q -n 16 --dist=worksteal
```

Expected: focused and broad suites pass. Record fresh command output; inspection alone is not completion evidence.

- [ ] **Step 5: Commit the roadmap handoff and close this plan**

Mark this plan complete only after the target design, normative contract, implementation plan, reviews, routing, and tests are accepted. Do not mark runtime hardening implemented.

```bash
git diff --check -- docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md docs/plans/2026-07-13-procedure-first-migration-waves-plan.md docs/index.md docs/capability_status_matrix.md docs/plans/2026-07-13-resume-projection-integrity-hardening-design-plan.md
git add docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md docs/plans/2026-07-13-procedure-first-migration-waves-plan.md docs/index.md docs/capability_status_matrix.md docs/plans/2026-07-13-resume-projection-integrity-hardening-design-plan.md
git commit -m "Route resume projection integrity hardening"
git status --short
```

Expected: the roadmap orders pilot, reviewed hardening implementation, then production migration waves; the capability matrix still says implementation is pending; and the protected dirty-path baseline is unchanged.
