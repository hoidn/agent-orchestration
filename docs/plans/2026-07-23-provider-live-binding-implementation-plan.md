# Provider Live Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan
> task-by-task. Every task uses test-driven development and receives a
> specification-compliance review followed by an implementation-quality
> review before the next dependent task starts. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Implement Stage 7's accepted observation-only provider panes and
two-member `with-live-providers` form, including one fail-closed
`CONTINUE|STEER` provider-session correction and one atomic workflow-result
boundary.

**Architecture:** Keep the existing provider pipe and JSONL transports
authoritative. Add three focused provider-runtime primitives—a shared session
codec with provider-specific resume-boundary observations, a cancellable
process-group control, and an observation-only pane manager—then prove the
real Codex unique-identity + exact-readiness-marker cancellation/resume
boundary before adding a single-writer provider-supervision executable node.
Expose that node through the ordinary Workflow Lisp target-2.16, WCC/schema-2,
Core, Executable, and runtime projection routes; never add a direct
surface-to-runtime escape path.

**Tech Stack:** Python 3.11+, immutable dataclasses, subprocess/POSIX process
groups, tmux, Workflow Lisp WCC schema 2, executable IR v1, state schema 2.1,
pytest/pytest-xdist.

**Accepted design:** The evidence-driven resume-boundary amendment to
`docs/design/workflow_lisp_provider_live_binding.md` at commit
`f01eb670b1fb68590824f2b4b0c9bd887fb329e4`, content digest
`sha256:03ba656da9773ee0e6bdb8527d37edaf943ff9444bf2dc7d0c4ba5d4ff552446`.
The design-only acceptance commit landed first; this bounded plan delta binds
that immutable commit/digest and closes its acceptance metadata. No Task 1R
code began before this binding, and Task 1R code may start only after this
plan commit lands.

**Historical behavior simulation:** The T3 report remains truthful historical
evidence for the pre-clarification design bytes at `99404956` /
`sha256:9c2a2f333eb277154c8a98a0897cf9b390339a42fcf8a7702ce5582824ada113`.
The bound amendment supersedes commit `afd0fec5` as current implementation
authority. The historical simulation does not override the accepted
observable cancellation linearization or the narrower resume-boundary rule.

**Status:** Execution in progress. Tasks 1-6 and the evidence-driven Task 1R
amendment are complete. The real resume-boundary gate passed; Task 7 is next.

**Plan-review evidence:** Independent specification/sequence review: `PASS`.
Independent path/selector/shell-order audit: `PASS` for the pre-amendment plan.
For the readiness amendment, independent specification review:
`SPEC_COMPLIANT`; independent quality/path review: `APPROVED`; behavioral
simulation: `PASS`. The final design acceptance metadata recheck passed. This
pointer-and-acceptance-metadata delta received final bounded independent
specification `PASS` and quality `APPROVED`.

---

## Scope And Deliberate Cost

Implement only the accepted v1:

- one worker and one supervisor;
- one observation edge from supervisor to worker;
- one typed `CONTINUE|STEER` directive, with active-turn `STEER` eligible only
  from a unique, codec-validated resume-boundary-seen, preterminal snapshot
  while both applicable deadlines remain live; clean natural success retains
  its separately proved frozen-boundary path only while the whole-step
  deadline remains live before resume launch;
- at most one replacement session turn;
- process containment only through the runtime-owned POSIX process group;
- one pure settlement expression and one atomic workflow-state/result commit;
- target DSL 2.16 and no YAML surface.

Do not implement provider-native duplex protocols, repeated steering,
N-member groups, effectful settlement, multi-step members, cross-run binding,
filesystem rollback, cgroups/namespaces, detached-child containment, general
background/join primitives, or any security design, implementation, test, or
review work.

This makes arbitrary provider graphs and stronger process/workspace isolation
harder later. That is intentional: each needs a separate lifecycle and
authority design instead of being hidden inside this bounded correction
feature.

## Governing Authorities

Read these before implementation:

- `docs/index.md`
- `docs/capability_status_matrix.md`
- `docs/design/workflow_lisp_provider_live_binding.md`
- `docs/plans/2026-07-23-provider-live-binding-t3-behavior-simulation.md`
- `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_lisp_lexical_execution_checkpoints.md`
- `docs/design/workflow_lisp_native_transportable_returns.md`
- `specs/providers.md`
- `specs/io.md`
- `specs/state.md`
- `specs/versioning.md`
- `specs/observability.md`

If this plan conflicts with the accepted design, the design wins and the plan
must be corrected before implementation continues.

## Execution Contract

Run from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do not create a worktree. Work on the current branch, stage only task-owned
paths, and commit after each reviewed task. Never use `git add .`,
`git add -A`, destructive checkout/reset commands, or broad cleanup.

Use `superpowers:test-driven-development` for every behavior change:

1. add the narrow failing test;
2. run it and record the expected contract failure;
3. add the smallest implementation;
4. rerun the narrow selector;
5. run the task's adjacent regression selector;
6. collect any new/renamed test module;
7. obtain specification review, then quality review;
8. commit the exact reviewed tree.

Use the `tmux` skill for the real Codex probes, smoke runs, and broad pytest
gates. Do not replace a slow model or provider with a faster one while waiting.

Security is excluded by owner direction. Do not edit security modules or
security specifications, dispatch security review, or add security tests. The
closing broad test command must exclude:

```text
tests/test_provider_isolation_policy.py
tests/test_provider_isolation_schema_resources.py
tests/test_secrets.py
```

and use `-k 'not security and not secret and not isolation'` to avoid embedded
security-specific cases.

## Protected Working-Tree Contract

These pre-existing paths are user-owned and outside Stage 7. Do not edit,
restore, stage, or commit them:

```text
docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md
docs/plans/2026-07-01-workflow-audit-tier-fixes.md
docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md
docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md
docs/superpowers/specs/2026-07-22-workflow-lisp-evolution-substrate-and-feature-design.md
state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt
workflows/library/prompts/workflow_step_back/diagnose_non_progress.md
docs/reports/2026-07-22-compelling-example-search-and-effectiveness-doubts.md
```

`docs/design/README.md` and `docs/index.md` contain unrelated user-owned
evolution-design hunks. Stage 7 may update only its own rows/status sentences
and must stage those hunks interactively.

Before every commit:

```bash
git diff --cached --name-only
git diff --cached --check
git diff --cached -- docs/index.md docs/design/README.md
git diff --cached --name-only -- \
  docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md \
  docs/plans/2026-07-01-workflow-audit-tier-fixes.md \
  docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md \
  docs/superpowers/specs/2026-07-22-workflow-lisp-evolution-substrate-and-feature-design.md \
  state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt \
  workflows/library/prompts/workflow_step_back/diagnose_non_progress.md \
  docs/reports/2026-07-22-compelling-example-search-and-effectiveness-doubts.md
```

The third command must show only Stage 7 routing/status hunks, with no
evolution-roadmap or other user-owned text. The last command must print
nothing.

## File Responsibility Map

### Provider runtime substrate

- Create `orchestrator/providers/session_transport.py`: incremental
  metadata-mode JSONL codecs and immutable identity/readiness snapshots.
- Create `orchestrator/providers/control.py`: thread-safe invocation lifecycle,
  cancellation, reaping, PGID-empty proof, and terminal disposition.
- Create `orchestrator/providers/observation.py`: run-scoped tmux observation
  manager and invocation-local display/transcript handles.
- Modify `orchestrator/providers/executor.py`: share the codec, opt into
  controls, fan out display bytes without changing raw transport, and retain
  the exact control-absent path.
- Modify `orchestrator/providers/types.py`: add only the accepted structural
  `turn_boundary_resume` capability.
- Modify `orchestrator/providers/registry.py`: opt in only templates that
  actually satisfy the capability after the real proof.
- Modify `orchestrator/providers/__init__.py`: export the public runtime types.

### Provider-supervision executable/runtime

- Create `orchestrator/workflow/provider_supervision/__init__.py`: bounded
  public imports for the internal runtime package.
- Create `orchestrator/workflow/provider_supervision/models.py`: immutable
  node-local records and member/turn identities.
- Create `orchestrator/workflow/provider_supervision/paths.py`: visit-qualified
  evidence and provisional-bundle path derivation.
- Create `orchestrator/workflow/provider_supervision/directive.py`: exact-key
  validated directive parsing.
- Create `orchestrator/workflow/provider_supervision/bindings.py`: immutable
  prepared invocation/attempt bindings.
- Create `orchestrator/workflow/provider_supervision/coordinator.py`: the
  single-writer coordinator and serialized arbiter.
- Modify `orchestrator/workflow/surface_ast.py`,
  `orchestrator/workflow/core_ast.py`,
  `orchestrator/workflow/elaboration.py`, and
  `orchestrator/workflow/lowering.py`: carry the compiler-generated-only
  supervision bridge without accepting an authored classic-YAML spelling.
- Modify `orchestrator/workflow/executable_ir.py`: add
  `ExecutableNodeKind.PROVIDER_SUPERVISION` and its typed config.
- Modify `orchestrator/workflow/runtime_step.py`: expose the node-local config
  without widening ordinary provider mappings.
- Modify `orchestrator/workflow/validation.py`: validate the closed node
  schema and reject authored YAML.
- Modify `orchestrator/workflow/executor.py`: dispatch from the existing
  top-level/nested-step paths, allocate attempts, publish one `current_step`,
  invoke the coordinator, settle through the existing atomic dataflow
  finalizer, and quarantine interrupted visits.
- Modify `orchestrator/workflow/provider_attempts.py`: add only generic
  member/turn scope support needed by the coordinator.
- Modify `orchestrator/workflow/resume_planner.py`: recognize and fail closed
  on the sticky interrupted-visit quarantine before provider launch.
- Modify `orchestrator/cli/commands/resume.py`: surface the sticky quarantine
  through the public resume command while retaining explicit force-restart
  and new-run escape behavior.
- Reuse `StateManager.finalize_step_with_dataflow` unchanged and test it
  through `tests/test_state_manager.py`; a RED test proving it cannot carry
  the accepted group settlement requires a plan correction before editing
  state code. Do not add a second settlement path or schema bump.

### Workflow Lisp frontend and WCC

- Modify `orchestrator/workflow_lisp/syntax.py` and
  `orchestrator/workflow/validation.py`: admit target DSL 2.16 through both
  Workflow Lisp and shared workflow-version validation.
- Modify `orchestrator/workflow_lisp/type_env.py` and definition validation:
  install/reserve `ProviderSteeringDirective` only for target 2.16+.
- Modify `orchestrator/workflow_lisp/compiler.py`: make definition-module
  validation and prelude-name availability target-sensitive.
- Modify `orchestrator/workflow_lisp/expressions.py`: parse and own the
  `with-live-providers` expression and source spans.
- Modify `orchestrator/workflow_lisp/form_registry.py`: register the new
  target-gated expression form without changing unrelated reserved surfaces.
- Modify `orchestrator/workflow_lisp/__init__.py`: export the public
  expression type consistently with existing expression symbols.
- Modify `orchestrator/workflow_lisp/expression_traversal.py`,
  `orchestrator/workflow_lisp/functions.py`, and
  `orchestrator/workflow_lisp/macros.py`: preserve/traverse the new expression
  through existing normalization paths.
- Modify `orchestrator/workflow_lisp/typecheck_dispatch.py`,
  `orchestrator/workflow_lisp/typecheck_effects.py`, and
  `orchestrator/workflow_lisp/effects.py`: enforce the two-member shape,
  directive type, pure settlement, and `LiveSupervisionEffect`.
- Modify `orchestrator/workflow_lisp/wcc/model.py`,
  `orchestrator/workflow_lisp/wcc/elaborate.py`,
  `orchestrator/workflow_lisp/wcc/anf.py`,
  `orchestrator/workflow_lisp/wcc/analysis.py`,
  `orchestrator/workflow_lisp/wcc/defunctionalize.py`, and
  `orchestrator/workflow_lisp/wcc/lower.py`: normalize eligible specialized
  members into one closed `WccProviderSupervision` term and lower it through
  schema 2.
- Reuse
  `orchestrator/workflow_lisp/lowering/pure_projection.py::build_pure_projection_payload`
  unchanged unless a RED integration test demonstrates a missing generic
  input; amend this plan before editing that owner.
- Modify `orchestrator/workflow_lisp/source_map.py`,
  `orchestrator/workflow_lisp/build_artifacts.py`,
  `orchestrator/workflow/runtime_plan.py`, and
  `orchestrator/workflow/semantic_ir.py`. Prove the generic checkpoint route
  first; if that RED proof fails, modify
  `orchestrator/workflow_lisp/lexical_checkpoints.py` and
  `orchestrator/workflow_lisp/lexical_checkpoint_effect_policies.py` within
  Task 12C only. Reuse
  `orchestrator/workflow/pure_expr.py::evaluate_pure_expr`; do not create a
  parallel pure evaluator or direct lowerer.

### Tests and fixtures

- Create `tests/test_provider_session_transport.py`.
- Create `tests/test_provider_execution_control.py`.
- Create `tests/test_provider_observation.py`.
- Create `tests/e2e/test_e2e_codex_provider_session_control.py`.
- Create `tests/test_provider_supervision_ir.py`.
- Create `tests/test_provider_supervision_runtime.py`.
- Create `tests/test_provider_supervision_resume.py`.
- Create `tests/test_workflow_lisp_provider_supervision.py`.
- Create `tests/test_workflow_lisp_provider_supervision_e2e.py`.
- Create `tests/e2e/test_e2e_provider_supervision.py`.
- Create fixtures under
  `tests/fixtures/workflow_lisp/provider_supervision/` and reuse/extend
  `tests/fixtures/bin/fake_provider.py` only when that remains clearer than a
  focused fake session provider.

Tests assert contracts, dataflow, lifecycle, identity, and result authority.
They must not assert literal prompt phrasing.

## Review Discipline

After each task's implementation and narrow tests:

1. dispatch a specification-compliance reviewer with only the accepted design,
   this plan, the task number, and the exact diff;
2. resolve findings and rerun the narrow tests;
3. dispatch a different implementation-quality reviewer;
4. resolve findings and rerun the task regression selector;
5. record both verdicts in the task notes and commit.

No reviewer may broaden into security scope. A review verdict is evidence only
for the bytes reviewed; corrections require the relevant reviewer to recheck
the corrected bytes.

## Phase 1 — Observation And Cancellation Substrate

### Task 1: Shared Real-Codex Session Codec

**Files:**

- Create: `orchestrator/providers/session_transport.py`
- Create: `tests/test_provider_session_transport.py`
- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/providers/__init__.py`
- Test: `tests/test_provider_execution.py`

The central interface is:

```python
@dataclass(frozen=True)
class SessionIdentitySnapshot:
    status: Literal["missing", "unique", "ambiguous", "invalid"]
    session_ids: tuple[str, ...]
    terminal_seen: bool
    error: Mapping[str, Any] | None = None
    resume_boundary_seen: bool = False


class CodexExecJsonlAccumulator:
    def feed(self, chunk: bytes) -> None: ...
    def snapshot(self) -> SessionIdentitySnapshot: ...
    def finalize(
        self,
        *,
        expected_session_id: str | None,
        require_terminal: bool,
    ) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]: ...
```

- [x] Write RED tests for arbitrary split/coalesced JSONL chunks, one EOF tail,
  `thread.started.thread_id`, retained `session_id`, cross-key conflict,
  changing/malformed IDs, nested `item.completed.item` agent text, exact
  `turn.completed|response.completed`, and rejection of suffix/status/generic
  terminal lookalikes.
- [x] Run:
  `pytest -q tests/test_provider_session_transport.py`
  and confirm failures are missing codec behavior rather than fixture errors.
- [x] Implement the accumulator and metadata-mode factory without provider-name
  branches.
- [x] Replace the streaming/final parser divergence in
  `ProviderExecutor` with one accumulator; preserve `_parse_codex_jsonl_transport`
  as a compatibility delegator if current tests call it.
- [x] Ensure the callback feeds the accumulator even when
  `stream_output=False`; raw stdout stays byte-identical.
- [x] Run:
  `pytest -q tests/test_provider_session_transport.py tests/test_provider_execution.py -k 'session or codex_jsonl'`.
- [x] Run:
  `pytest --collect-only -q tests/test_provider_session_transport.py`.
- [x] Complete specification review, quality review, and commit:
  `Parse real provider session transport consistently`.

**Task 1 evidence (2026-07-23):** Initial implementation `59326044`;
specification corrections `646f9d03`; quality corrections `02e9e5b7`.
Observed RED: 30 missing-contract failures before production edits, followed
by focused RED reproductions for spool independence, non-string terminal
values, immutable snapshots, lone-surrogate text, and invalid EOF tails.
Final verification: 59 passed/20 deselected in the required selector, 34/34
in the full adjacent provider-execution module, and 45 tests collected.
Independent verdicts: `SPEC_COMPLIANT`; `APPROVED`.

#### Task 1R: Resume-boundary observation amendment

Task 3 proved that a unique `thread.started.thread_id` alone is not a
resumable boundary. Preserve Task 1's accepted parsing work and add only the
codec-owned fact needed by the revised gate.

**Files:**

- Modify: `orchestrator/providers/session_transport.py`
- Modify: `orchestrator/providers/control.py`
- Modify: `tests/test_provider_session_transport.py`
- Modify: `tests/test_provider_execution_control.py`
- Test: `tests/test_provider_execution.py`

- [x] Write RED tests proving `resume_boundary_seen` defaults to false,
  remains false for identity alone and for nested/suffixed/status-like
  lookalikes, becomes true only when the top-level `type` is exactly
  `turn.started` after unique identity and before an exact terminal event, and
  is not applied retroactively when `turn.started` precedes identity. Cover
  split, coalesced, duplicate-marker, and EOF-tail input.
- [x] Add both-direction snapshot tests proving the observation stays true
  after later invalid/ambiguous identity or terminal input. Prove exact
  `turn.failed` before and after the marker sets `terminal_seen`, durably
  fails the transport, and remains nonpromotable even when the child exits
  zero. Prove codecs without a validated marker retain the false default and
  expose no structural resume-boundary-observation capability.
- [x] Add control-copy tests proving both `control.session_snapshot` and
  `ProviderCancellationResult.final_session_snapshot` preserve the codec-owned
  observation. Do not put deadline or active-versus-clean branch policy in the
  codec/control layer; Task 8 owns those coordinator tests.
- [x] Run all new RED tests:

  ```bash
  pytest -q \
    tests/test_provider_session_transport.py \
    tests/test_provider_execution_control.py \
    tests/test_provider_execution.py \
    -k 'resume_boundary or turn_started or turn_failed'
  ```

  Confirm the assertions fail for the intended missing observation,
  propagation, capability, and failed-turn contracts.
- [x] Implement the smallest accumulator change. Validate each event's
  identity fields before considering its exact top-level `type`; do not infer
  readiness from provider names, event suffixes, terminal state, or successful
  parsing alone. Expose a generic codec capability query for later static and
  runtime validation, and copy the new field at every explicit snapshot-copy
  boundary.
- [x] Run:

  ```bash
  PYTHONWARNINGS=error pytest -q \
    tests/test_provider_session_transport.py \
    tests/test_provider_execution_control.py \
    tests/test_provider_execution.py \
    -k 'session or identity or resume_boundary or codex_jsonl'
  ```

- [x] Run:
  `pytest --collect-only -q tests/test_provider_session_transport.py tests/test_provider_execution_control.py tests/test_provider_execution.py`.
- [x] Run the full adjacent warning-strict suite without a selector:

  ```bash
  PYTHONWARNINGS=error pytest -q \
    tests/test_provider_session_transport.py \
    tests/test_provider_execution_control.py \
    tests/test_provider_execution.py
  ```

- [x] Rerun Task 1 specification review and then quality review on the exact
  amendment, resolve findings, and commit:
  `Track provider resume-boundary observations`.

**Task 1R evidence (2026-07-23):** RED produced 14 intended missing-contract
failures, followed by one intended identity-precedence failure. Implementation
`16fa0ab9` passed 23 targeted tests with 152 deselected, 89 warning-strict
focused tests with 86 deselected, collection of 175 tests, and the full
warning-strict adjacent suite of 175 tests. Ordered independent verdicts:
`SPEC_COMPLIANT`; `APPROVED`.

### Task 2: Generic Cancellable Provider Execution

**Files:**

- Create: `orchestrator/providers/control.py`
- Create: `tests/test_provider_execution_control.py`
- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/providers/__init__.py`
- Test: `tests/test_provider_execution.py`

The control must expose `NEW -> BOUND -> TERMINAL` plus spawn-failure
`NEW -> TERMINAL`, cancellation-before-bind latching, immutable session
snapshots, idempotent `cancel_and_reap`, and one frozen terminal proof.

- [x] Write RED tests for cancel-before-bind, spawn failure, natural exit,
  TERM then KILL, same-PGID child cleanup, naturally exited leader with a
  lingering child, repeated cancellation, concurrent natural-exit/cancel,
  capture-thread join, and invalid final identity.
- [x] Run:
  `pytest -q tests/test_provider_execution_control.py`
  and confirm the new control is absent.
- [x] Implement `ProviderExecutionControl` and
  `ProviderCancellationResult`; make the executor thread the sole `Popen.wait`
  owner.
- [x] Add optional `control` to `ProviderExecutor.execute`. Only
  control-enabled calls must use the cancellable Popen path and
  `start_new_session=True`; the control-absent path must retain current
  behavior.
- [x] Return an explicit `cancelled_provisional` classification with raw
  partial transport and no promotable result. Do not swallow failed
  PGID/join proof.
- [x] Run:
  `pytest -q tests/test_provider_execution_control.py tests/test_provider_execution.py -k 'timeout or streaming or session or process_tree'`.
- [x] Complete specification review, quality review, and commit:
  `Add cancellable provider execution control`.

**Task 2 evidence (2026-07-23):** Initial implementation `dbeb9480`;
correctness and lifecycle corrections through `9c6de9ac`; observable
cancellation linearization authority `afd0fec5` with plan rebinding
`24476d92`. Recorded REDs covered pre-bind latching, post-claim
`BaseException`, both causal probe directions, persistent group-signal
failure, descendant-held pipes, failed-bind waiter state, capture/codec
concurrency, and attempted-versus-delivered signal facts. Final verification:
107 tests collected; 107 passed warning-strict both serially and with
`-n 16 --dist=worksteal`; the required focused selector passed 25 with 82
deselected. Independent verdicts: `SPEC_COMPLIANT`; `APPROVED`.

### Task 3: Early Real Codex Resume-Boundary Gate

**Files:**

- Modify: `tests/e2e/test_e2e_codex_provider_session_control.py`
- Test: `orchestrator/providers/registry.py`
- Test: `orchestrator/providers/executor.py`

**Structural stop/revise evidence (2026-07-23):**

| Installed version | Exact event at cancellation gate | Unique identity | `resume_boundary_seen` | `terminal_seen` | Complete process boundary | Exact-identity resume succeeded |
| --- | --- | --- | --- | --- | --- | --- |
| Codex `0.145.0` | `thread.started` | true | false | false | true | false |
| Codex `0.145.0` | `turn.started` | true | true | false | true | true |

The first row is the immediate-failure incident. The test introduced at
`7e3f869f` waited only for unique identity and is not accepted gate evidence.
The second row proves the narrower feasibility boundary. These records retain
no session id, prompt, raw event, raw output, or response content.
`turn.started` makes an attempt eligible; only this successful
exact-identity resume proves the real boundary.

- [x] Complete Task 1R and both of its ordered reviews before changing the
  Task 3 gate.
- [x] Amend the E2E test so its active-turn wait requires one immutable
  snapshot with `status == "unique"`, one id,
  `resume_boundary_seen is True`, and `terminal_seen is False` before either
  applicable deadline. Identity-only `thread.started` must not release the
  wait.
- [x] Keep the existing temporary-Git-repository, builtin fresh/resume
  commands, owned process-boundary proof, exact-identity check, and non-empty
  normalized assistant-result assertions. After cancellation and capture
  join, require the final killed-turn snapshot to retain the same unique
  identity and `resume_boundary_seen is True` while
  `terminal_seen is False`.
- [x] Run:
  `pytest --collect-only -q tests/e2e/test_e2e_codex_provider_session_control.py`.
- [x] Run it in tmux:
  `ORCHESTRATE_E2E=1 pytest -q tests/e2e/test_e2e_codex_provider_session_control.py::test_real_codex_thread_identity_cancel_and_resume -s`.
- [x] If the real provider cannot expose unique identity plus the exact
  preterminal readiness marker, reaches either deadline first, cannot prove
  the complete owned boundary, or cannot resume the killed turn under the
  exact identity, stop Stage 7 before Tasks 4-15 and return to the design's
  stop/revise branch. Do not weaken the assertion or substitute fixture
  evidence.
- [x] If green, record only the command, exit, installed provider version, and
  structural event types/booleans; do not persist the identity, prompt, raw
  events/output, or response content.
- [x] Rerun Task 3 specification review and then quality review on the exact
  revised test and bound Task 1R behavior, resolve findings, and commit:
  `Prove real provider resume boundary`.

**Task 3 evidence (2026-07-23):** Installed provider:
`codex-cli 0.145.0`. The private-tmux command executed the exact test node
with `ORCHESTRATE_E2E=1`, `PYTHONWARNINGS=error`, `-q`, `-s`, disabled pytest
traceback/summary/capture/cache output, and retained its output only in shell
memory. Result: `1 passed`; pytest exit `0`; sanitized gate exit `0`; private
socket removed. Structural facts proved by the passing assertions: exact
`turn.started` resume-boundary observation true while identity was unique and
terminal false; TERM sent; leader reaped; owned PGID empty; capture and
execution joined; cancellation proof complete; same opaque identity resumed;
resume terminal true; normal/promotable result; non-empty normalized assistant
output. No identity, prompt, raw event/output, or response content was
persisted. Ordered independent verdicts: `SPEC_COMPLIANT`; `APPROVED`.

### Task 4: Observation-Only Pane Lifecycle

**Files:**

- Create: `orchestrator/providers/observation.py`
- Create: `tests/test_provider_observation.py`
- Modify: `orchestrator/providers/__init__.py`

- [x] Write RED tests for one run-scoped server, unique invocation panes,
  pre-created display files, tail startup, opaque target access, transcript
  finalization, independent teardown, allocation/tail/tmux loss, concurrent
  handles, and a real local tmux tail smoke when tmux exists.
- [x] Run:
  `pytest -q tests/test_provider_observation.py`.
- [x] Implement a locked `ProviderObservationManager` and
  `ProviderObservationHandle`. The display/transcript file—not
  `capture-pane`—is evidence authority.
- [x] Keep socket/target strings process-local; persisted pane records contain
  stable invocation/member/turn identities and paths only.
- [x] Run:
  `pytest -q tests/test_provider_observation.py`.
- [x] Complete specification review, quality review, and commit:
  `Add provider observation pane lifecycle`.

**Task 4 evidence (2026-07-23):** Initial RED failed collection because the
observation module was absent. Review-driven REDs then exposed untyped display
precreation, incomplete loss/teardown coverage, concurrent-close early return,
and an unretryable live-server teardown. Final verification collected 13
tests; all 13 passed warning-strict serially and with
`-n 4 --dist=worksteal`, including the isolated real-tmux tail/cleanup smoke.
Ordered independent verdicts: `SPEC_COMPLIANT`; `APPROVED`.

### Task 5: Observation Non-Interference Across Every Provider Route

**Files:**

- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/providers/observation.py`
- Modify: `orchestrator/observability/summary.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/calls.py`
- Test: `tests/test_provider_execution.py`
- Create: `tests/test_provider_observation_execution.py`
- Create: `tests/test_provider_observation_workflow.py`
- Create: `tests/test_provider_observation_adjudicated_route.py`
- Test: `tests/test_provider_observation.py`
- Test: `tests/test_observability_summary_modes.py`
- Test: `tests/test_adjudicated_provider_runtime.py`
- Test: `tests/test_managed_provider_execution.py`
- Test: `tests/test_at72_provider_state_persistence.py`
- Test: `tests/test_workflow_executor_characterization.py`

- [x] Write RED parity tests for ordinary non-stream, stream, session JSONL,
  timeout, adjudicated candidate/evaluator, managed-provider wrapper, and
  imported child-executor paths, defining the intended keyword as
  `provider_observation_enabled` and parametrizing every new parity/failure
  test over `(False, True)`.
- [x] Add failure-direction tests for allocation, tail, callback, tmux-server,
  transcript, and teardown failures. Outside the live form, provider raw
  output/result/metadata must remain authoritative and unchanged.
- [x] Prove the Task 5 negative boundary: live targets never enter workflow
  values, bundles, `state.json`, result diagnostics, or the stable pane
  record. The positive assertion that the target appears only in the actual
  supervisor execution prompt and permitted debug evidence remains the
  explicit Task 7 coordinator gate, because no supervisor executable exists
  at this plumbing-only boundary.
- [x] Keep ordinary automatic observation behind an internal disabled-by-
  default `provider_observation_enabled` flag in this task. The ordinary
  default flips only after Task 14's real smoke proves the complete boundary.
- [x] Run and confirm only observation plumbing is missing:

  ```bash
  pytest -q tests/test_provider_execution.py \
    -k 'observation or session or stream or timeout'
  pytest -q tests/test_adjudicated_provider_runtime.py \
    -k 'observation or candidate or evaluator'
  pytest -q tests/test_managed_provider_execution.py \
    -k 'observation or managed'
  pytest -q \
    tests/test_at72_provider_state_persistence.py \
    tests/test_workflow_executor_characterization.py \
    -k 'provider_session or provider_step or imported'
  ```
- [x] Add the keyword-only internal
  `provider_observation_enabled: bool = False` construction flag shared by
  the run-level `WorkflowExecutor` and its `ProviderExecutor`/imported child
  executors.
- [x] Inject one observation manager at run construction and share it with
  imported child executors. Let `ProviderExecutor.execute` auto-open ordinary
  handles or accept a pre-opened group handle.
- [x] Fan raw bytes to the authoritative buffer first, then independent
  display sinks. Session panes receive codec-normalized assistant output, not
  raw JSONL. Record sink failures without substituting output.
- [x] Run:
  `pytest -q tests/test_provider_execution.py -k 'observation or session'`.
- [x] Rerun all four concrete commands above; their required parametrization
  covers the flag disabled and enabled.
- [x] Complete specification review, quality review, and commit:
  `Mirror provider execution without changing transport`.

**Task 5 evidence (2026-07-23):** The first RED collected 15 tests and failed
on the absent keyword-only construction flag. Review-driven REDs then exposed
an unread-large-stdin timeout bypass, manager-local identity collisions,
masked process-control exceptions, early manager acquisition, and teardown
racing async summary-provider work. The corrected implementation uses a
run-scoped locked invocation ordinal, concurrent bounded stdin delivery,
caller-owned pre-opened handles, late manager acquisition, and dependent
summary settlement before root-only teardown. Final verification passed 74
warning-strict focused tests and 141 integrated xdist-selected tests; all 41
initial changed/new tests collected before the review corrections, and the
expanded provider/workflow modules collected 78 tests cleanly afterward. Ordered
cross-specification verdicts: `PROVIDER_SPEC_PASS`,
`WORKFLOW_SPEC_PASS`. Ordered cross-quality verdicts after corrections:
`PROVIDER_QUALITY_APPROVED`, `WORKFLOW_QUALITY_APPROVED`.

## Phase 2 — Executable Node And Single-Writer Coordinator

### Task 6: Closed Provider-Supervision Executable Contract

**Files:**

- Create: `orchestrator/workflow/provider_supervision/__init__.py`
- Create: `orchestrator/workflow/provider_supervision/models.py`
- Create: `orchestrator/workflow/provider_supervision/paths.py`
- Create: `orchestrator/workflow/provider_supervision/directive.py`
- Create: `tests/test_provider_supervision_ir.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/runtime_step.py`
- Modify: `orchestrator/workflow/validation.py`

- [x] Write RED hand-built IR tests for the exact
  `provider_supervision.v1` schema, two fixed members, one observation edge,
  worker/directive/result contracts, pure settlement payload, timeouts,
  `max_steers: 1`, source ownership, and unknown/missing/extra-field rejection.
- [x] Add round-trip tests proving existing executable/runtime envelope
  versions stay unchanged, the generated Surface/Core bridge projects
  deterministically, and classic authored YAML cannot construct the node.
- [x] Run:
  `pytest -q tests/test_provider_supervision_ir.py`.
- [x] Add the typed executable kind/config and mapping view; keep the node-local
  schema closed and generic.
- [x] Run:
  `pytest -q tests/test_provider_supervision_ir.py tests/test_workflow_ir_lowering.py tests/test_workflow_executor_characterization.py -k 'executable_ir or runtime_step or provider_supervision'`.
- [x] Complete specification review, quality review, and commit:
  `Define provider supervision executable node`.

**Task 6 evidence (2026-07-23):** The primitive RED first failed on the
absent provider-supervision package, and the generated-projection RED then
failed on the absent Core statement. Review-driven REDs exposed two
fail-closed gaps: a same-name but structurally false supervisor directive
contract, and raw descriptor-decoding exceptions from malformed hand-built
member or settlement contracts. The final contract uses one immutable
compiler-owned `CONTINUE|STEER(guidance: String)` descriptor, exact contract
identity and shape checks, translated malformed-descriptor failures, fixed
derived turn paths, and a generated-only Surface/Core bridge while retaining
`workflow_executable_ir.v1`. Fresh verification collected and passed 41
warning-strict focused tests, passed all 111 affected three-module tests, and
passed 17 additional Surface/Core/shared-validation selectors. Ordered final
review verdicts: `TASK6_SPEC_APPROVED`, then `TASK6_QUALITY_APPROVED`.

### Task 7: CONTINUE Coordinator And Atomic Settlement

**Files:**

- Create: `orchestrator/workflow/provider_supervision/bindings.py`
- Create: `orchestrator/workflow/provider_supervision/coordinator.py`
- Create: `tests/test_provider_supervision_runtime.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/provider_attempts.py`
- Test: `tests/test_provider_attempt_allocation.py`
- Test: `tests/test_state_manager.py`

- [x] Write RED tests proving concurrent wall-clock overlap, immutable member
  requests, coordinator-only `StateManager` access, unique member paths,
  `current_step` publication before panes/processes/attempts, distinct
  attempts/snapshots, exact directive key validation, `CONTINUE` selection,
  and one `finalize_step_with_dataflow`-equivalent commit.
- [x] Prove both initial panes are allocated before prompt composition, the
  supervisor receives only the worker's process-local observation target plus
  structural injection metadata, and both member output contracts bind their
  own provisional paths.
- [x] Add both-direction business-bundle tests: `CONTINUE` requires a valid
  fresh bundle; an invalid/missing fresh bundle fails with no publication.
- [x] Add both-direction compatibility tests proving an existing six-field
  persisted `ProviderAttemptScope` remains accepted and canonical; new
  member/turn scopes cannot collide with each other; and existing direct,
  loop, adjudication, and call-frame scopes serialize unchanged under state
  schema 2.1.
- [x] Run:
  `pytest -q tests/test_provider_supervision_runtime.py -k 'continue or single_writer or settlement'`.
- [x] Implement the serial coordinator and member thread boundary using the
  existing output-contract validators and deterministic runtime-step/attempt
  identities. Member
  threads may call only low-level provider execution and append member-local
  evidence.
- [x] Keep supervisor and worker panes alive through directive arbitration.
  Initial pane loss before the directive is load-bearing; later mirror loss is
  evidence-only.
- [x] Settle the pure expression and selected attempt/result/artifact dataflow
  in one state transaction.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_provider_supervision_runtime.py \
    tests/test_provider_attempt_allocation.py \
    -k 'provider_supervision or continue or single_writer or settlement or attempt_scope'
  pytest -q tests/test_state_manager.py -k 'finalize_step_with_dataflow'
  ```
- [x] Complete specification review, quality review, and commit:
  `Coordinate provider supervision CONTINUE path`.

**Task 7 evidence (2026-07-24):** The runtime RED first failed because the
coordinator and workflow-owned bindings did not exist. Review-driven coverage
then closed legacy qualifier-prefix compatibility, directive persistence,
prompt-suffix ordering, concrete missing/invalid-bundle rejection, both pane
loss boundaries, and the production `WorkflowExecutor.execute()` cursor
ordering proof. Fresh verification passed 41 focused Task 7 selectors, all
146 affected runtime/attempt/state tests, 27 adjacent dataflow tests, and 6
executor characterizations. Ordered final verdicts:
`TASK7_SPEC_APPROVED`, then `TASK7_BINDINGS_QUALITY_APPROVED` and
`TASK7_INTEGRATION_QUALITY_APPROVED`.

### Task 8: STEER, Result Authority, And Race Closure

**Files:**

- Create: `tests/test_provider_supervision_resume.py`
- Modify: `orchestrator/workflow/provider_supervision/coordinator.py`
- Modify: `orchestrator/workflow/provider_supervision/models.py`
- Modify: `orchestrator/workflow/provider_supervision/paths.py`
- Modify: `orchestrator/workflow/provider_supervision/directive.py`
- Modify: `orchestrator/workflow/provider_supervision/bindings.py`
- Modify: `orchestrator/workflow/executor.py`

- [x] Write RED tests for early `STEER`, bounded resume-boundary wait,
  identity-only refusal, exact-marker readiness, cancel-before-bind, active
  cancellation requiring `terminal_seen: false`, clean natural success using
  its complete frozen terminal boundary, natural nonzero exit, exact
  `turn.failed` precedence, terminal observation concurrent with cancellation,
  clean natural completion both before and after whole-step deadline expiry
  (timeout wins after expiry),
  lingering same-PGID child, invalid final identity, sticky-marker plus
  invalid/ambiguous-identity refusal, resume mismatch, a marker followed by an
  exact-identity native-resume failure, completed resume output with
  `terminal_seen: true`,
  supervisor/worker/whole-step timeout, second-steer rejection, and all
  directive/worker completion orders.
- [x] Add stale-preimage, distinct fresh/resume path, missing resume bundle,
  stale fresh bundle, and selected-only authority tests. A valid `STEER` must
  not read an invalid/missing unselected fresh business bundle.
- [x] Run:
  `pytest -q tests/test_provider_supervision_resume.py`.
- [x] Implement one serialized `STEER` path that always invokes the idempotent
  boundary verifier, allocates a new attempt/path only after proof, renders a
  fresh typed output contract into the guidance prompt, and selects only the
  resumed bundle. The active-cancellation branch requires unique identity,
  `resume_boundary_seen: true`, `terminal_seen: false`, and live deadlines;
  the clean-natural-success branch requires its frozen complete boundary,
  unique identity, the sticky readiness observation, and a live whole-step
  deadline immediately before resume launch.
- [x] Ensure all group invocations have controls and all failure paths cancel
  and join active siblings before terminal failure publication.
- [x] Run:
  `pytest -q tests/test_provider_supervision_runtime.py tests/test_provider_supervision_resume.py`.
- [x] Complete specification review, quality review, and commit:
  `Add bounded provider supervision STEER path`.

**Task 8 evidence (2026-07-24):** TDD coverage closed early directive
arbitration, both eligible resume boundaries, deadline and terminal-result
races, exact session identity, lazy resume allocation, selected-only result
authority, and bounded fail-closed sibling cleanup. Review-driven regressions
also proved that a frozen terminal proof waits for member-result authority, a
late structurally valid cancelled boundary reports the worker timeout, and a
provider-raised `TimeoutError` is not rewritten as a coordinator timeout.
Fresh verification passed 86 runtime/resume tests, 121 attempt/state tests,
53 provider-control/execution selectors, 33 observation-execution tests, and
6 executor characterizations. Ordered verdicts:
`TASK8_BINDINGS_SPEC_APPROVED`, `TASK8_COORDINATOR_SPEC_APPROVED`, then
`TASK8_INTEGRATION_QUALITY_APPROVED`, `TASK8_CLEANUP_QUALITY_APPROVED`, and
`TASK8_RACE_QUALITY_APPROVED`.

### Task 9: Interrupted-Visit Quarantine And Retry Boundary

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/resume_planner.py`
- Modify: `orchestrator/workflow/provider_supervision/coordinator.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Test: `tests/test_provider_supervision_resume.py`
- Test: `tests/test_resume_command.py`
- Test: `tests/test_at68_resume_force_restart.py`

- [x] Write RED tests for crash after `current_step` and before group terminal
  commit, visit-qualified running evidence, sticky
  `provider_supervision_interrupted_visit_quarantined`, exact current-step
  clearance, older-result preservation, no ordinary-resume provider launch,
  repeated ordinary-resume failure, and explicit force-restart/new-run escape.
- [x] Add a live-coordinator authored retry test proving retry is allowed only
  after all members and capture work are joined and the failed visit is
  durable.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_provider_supervision_resume.py \
    tests/test_resume_command.py \
    tests/test_at68_resume_force_restart.py \
    -k 'supervision or quarantine or force_restart'
  ```
- [x] Implement pre-restart-index quarantine and sticky routing without
  durable session/pane reuse or a state-schema bump.
- [x] Run:
  `pytest -q tests/test_provider_supervision_resume.py tests/test_resume_command.py tests/test_at68_resume_force_restart.py -k 'supervision or quarantine or force_restart'`.
- [x] Complete specification review, quality review, and commit:
  `Quarantine interrupted provider supervision visits`.

**Task 9 evidence (2026-07-24):** RED coverage first exposed the missing
provider-supervision detector, atomic quarantine writer, and sticky CLI
route; the live-coordinator retry characterization confirmed that Task 8
already joins all members and capture work before durable failed-visit
publication. The implementation creates visit-bound `running`/`pending`
metadata before `current_step`, panes, attempts, or providers; quarantines
only an exact running supervision visit without an exact terminal result; and
preserves older results while clearing only the matching current visit.
Review-driven tests closed one-sided projection/type fail-open behavior,
missing projection identity, positive non-boolean visit qualification, and
post-commit secondary-metadata failure authority. Fresh verification passed
169 affected runtime/resume/CLI tests, 121 attempt/state tests, and 53
provider-control/execution selectors. Ordered verdicts:
`TASK9_METADATA_SPEC_APPROVED`, `TASK9_RESUME_SPEC_APPROVED`, then
`TASK9_METADATA_QUALITY_APPROVED` and `TASK9_RESUME_QUALITY_APPROVED`.

## Phase 3 — Workflow Lisp Target 2.16

### Task 10: Version-Gated Prelude Directive

**Files:**

- Modify: `orchestrator/workflow_lisp/syntax.py`
- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/definitions.py`
- Modify: `orchestrator/workflow_lisp/modules.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow/validation.py`
- Create: `tests/test_workflow_lisp_provider_supervision.py`

- [x] Write RED tests proving target 2.16 is accepted through both version
  validators, 2.16 installs the exact union, 2.16 rejects
  authored/import/type-parameter/schema shadowing, and targets below 2.16
  neither install nor reserve the same authored name. The form-specific 2.15
  rejection belongs to Task 11 after that form exists.
- [x] Add union construction, match exhaustiveness, variant proof, structural
  compatibility, and exact `variant_output` contract tests.
- [x] Run:
  `pytest -q tests/test_workflow_lisp_provider_supervision.py -k 'directive or target or shadow'`.
- [x] Add 2.16 and the target-scoped prelude union using existing union types;
  make compiler definition-module validation target-sensitive, and do not add
  a bespoke runtime value representation.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_provider_supervision.py \
    tests/test_workflow_lisp_modules.py \
    tests/test_workflow_lisp_procedures.py \
    -k 'directive or target or shadow or prelude or union'
  ```
- [x] Complete specification review, quality review, and commit:
  `Add target-gated steering directive type`.

**Task 10 evidence (2026-07-24):** RED tests first proved both version
validators rejected 2.16, the directive type was absent, and all eight
target-scoped shadowing cases failed open. The implementation admits 2.16,
installs the exact compiler-owned directive through ordinary union machinery,
preserves 2.15 authored-name behavior, and rejects local type/schema,
type-parameter, import-alias, and unqualified type/schema collisions. A
quality-review negative control corrected over-reservation so a non-type
import may retain the same spelling in its separate namespace. Fresh
verification passed 22 Task 10 tests, 41 combined
directive/target/shadow/prelude/union tests, 39 structured-result
union/guidance tests, and 3 shared-version tests. Ordered verdicts:
`TASK10_CORE_SPEC_APPROVED`, `TASK10_SHADOW_SPEC_APPROVED`, then
`TASK10_CORE_QUALITY_APPROVED` and `TASK10_SHADOW_QUALITY_APPROVED`.

### Task 11: `with-live-providers` Surface, Types, And Effects

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/form_registry.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `orchestrator/workflow_lisp/expression_traversal.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck_effects.py`
- Modify: `orchestrator/workflow_lisp/effects.py`
- Test: `tests/test_workflow_lisp_provider_supervision.py`

- [x] Write RED parser/span/traversal/type/effect tests for exactly two
  bindings, exactly one valid `:observes` edge, worker type `T`, supervisor
  directive type, pure settlement result, and
  `LiveSupervisionEffect(supervisor, worker)`.
- [x] Add diagnostics for wrong arity, duplicate/missing/unknown edge,
  wrong supervisor type, effectful body, and unsupported form position.
- [x] Add a target-2.15 test that parses the now-known form and rejects it with
  the specific version-gate diagnostic code/span rather than an unknown-form
  error. Add registry tests for the 2.16 elaboration route and reserved macro
  name.
- [x] Run and verify diagnostic codes/spans, not literal messages:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_provider_supervision.py \
    tests/test_workflow_lisp_expressions.py \
    tests/test_workflow_lisp_macros.py \
    -k 'live_provider or provider_supervision or form_registry or target_2_15'
  ```
- [x] Implement the smallest AST/traversal/type/effect surface while preserving
  existing macro/function normalization.
- [x] Run:
  `pytest -q tests/test_workflow_lisp_provider_supervision.py -k 'parse or type or effect or diagnostic'`.
- [x] Complete specification review, quality review, and commit:
  `Type bounded live provider supervision`.

**Task 11 evidence (2026-07-24):** RED coverage established the new
two-member AST, one sibling observation edge, target gate, exact supervisor
type, transportable worker, pure settlement, and inferred live-supervision
effect. Specification review corrected malformed-clause span ownership and
added the public pure-helper-position diagnostic. Quality review then closed
raw `StopIteration` and silent-collision paths by revalidating exported AST
invariants before role selection. Fresh verification passed all 52 provider
supervision tests and all 97 adjacent expression, macro, and function tests.
Ordered final verdicts: `AST_SPEC_APPROVED`, `TYPE_SPEC_APPROVED`, then
`AST_QUALITY_APPROVED` and `TYPE_QUALITY_APPROVED`.

### Task 12A: WCC Member Normalization And Eligibility

**Files:**

- Modify: `orchestrator/workflow_lisp/wcc/model.py`
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py`
- Modify: `orchestrator/workflow_lisp/wcc/anf.py`
- Modify: `orchestrator/workflow_lisp/wcc/analysis.py`
- Modify: `orchestrator/workflow_lisp/wcc/route.py`
- Test: `tests/test_workflow_lisp_provider_supervision.py`
- Test: `tests/test_workflow_lisp_wcc_m3.py`
- Test: `tests/test_workflow_lisp_wcc_m4.py`

- [ ] Write RED WCC tests for direct provider members and recursively inlined
  monomorphic thin procedures declared `:lowering inline`, whose canonical
  bodies are straight-line `WccLet/WccHalt` with one unconditional provider
  `WccPerform` and pure projections. Prove authored `(call ...)` workflow
  boundaries are rejected as members.
- [ ] Write negative tests for residual `WccCall`, private boundary, case/if,
  `:lowering auto`, loop/recursion, second perform, non-provider effect, or
  effectful settlement, with authored-source ownership.
- [ ] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_provider_supervision.py \
    tests/test_workflow_lisp_wcc_m3.py \
    tests/test_workflow_lisp_wcc_m4.py \
    -k 'provider_supervision or live_providers or inline'
  ```

- [ ] Add `WccProviderSupervisionMember` and `WccProviderSupervision`, reuse
  existing specialization substitution/source provenance, recursively
  normalize direct procedure calls, and verify the canonical member shape in
  WCC.
- [ ] Rerun the concrete command above.
- [ ] Complete specification review, quality review, and commit:
  `Normalize live provider supervision members`.

### Task 12B: Defunctionalization And Core/Executable Projection

**Files:**

- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `orchestrator/workflow_lisp/wcc/lower.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/runtime_step.py`
- Test: `tests/test_workflow_lisp_provider_supervision.py`
- Test: `tests/test_workflow_ir_lowering.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] Write RED tests for defunctionalizing the closed WCC term through the
  ordinary schema-2 route into exactly one Core and executable
  `PROVIDER_SUPERVISION` node, while preserving source ownership and
  unchanged executable/runtime envelope versions.
- [ ] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_provider_supervision.py \
    tests/test_workflow_ir_lowering.py \
    tests/test_workflow_lisp_build_artifacts.py \
    -k 'provider_supervision or live_providers or executable'
  ```

- [ ] Implement the smallest schema-2 defunctionalization/Core/executable
  projection; do not add a direct surface-to-runtime route.
- [ ] Rerun the concrete command above.
- [ ] Complete specification review, quality review, and commit:
  `Project live provider supervision into executable IR`.

### Task 12C: Runtime, Semantic, Source-Map, Checkpoint, And Build Projection

**Files:**

- Modify: `orchestrator/workflow/runtime_plan.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `orchestrator/workflow_lisp/source_map.py`
- Modify: `orchestrator/workflow_lisp/build_artifacts.py`
- Modify only if the generic-checkpoint RED proof fails:
  `orchestrator/workflow_lisp/lexical_checkpoints.py`
- Modify only if the generic-checkpoint RED proof fails:
  `orchestrator/workflow_lisp/lexical_checkpoint_effect_policies.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`
- Test: `tests/test_workflow_lisp_lexical_checkpoints.py`
- Test: `tests/test_workflow_lisp_source_map.py`
- Test: `tests/test_workflow_lisp_projection_dual_run.py`

- [ ] Add executable/runtime-plan/semantic/source-map/checkpoint/build
  projection tests for one `PROVIDER_SUPERVISION` node and unchanged envelope
  versions.
- [ ] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_workflow_lisp_lexical_checkpoints.py \
    tests/test_workflow_lisp_source_map.py \
    tests/test_workflow_lisp_projection_dual_run.py \
    -k 'provider_supervision or live_providers or checkpoint or source_map'
  ```

- [ ] First prove the existing generic completed-effect/checkpoint route
  projects the new group without a special case. If the RED proof fails,
  implement only the missing generic case in the two explicitly listed
  checkpoint owners and rerun the command.
- [ ] Implement runtime-plan, Semantic IR, source-map, and build-artifact
  projections without changing their envelope versions.
- [ ] Rerun the concrete command above.
- [ ] Complete specification review, quality review, and commit:
  `Project live provider supervision build artifacts`.

### Task 13: Fixture End-To-End Compile, Run, And Resume

**Files:**

- Create: `tests/fixtures/workflow_lisp/provider_supervision/`
- Create: `tests/test_workflow_lisp_provider_supervision_e2e.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/build_artifacts.py`
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/observability/report.py`

Any failure that requires a different production owner pauses this task for a
reviewed amendment to this plan; it does not authorize post-hoc scope
expansion.

- [ ] Add deterministic fake worker/supervisor fixtures for `CONTINUE`,
  `STEER`, invalid directive, missing identity, lingering child, stale bundle,
  settlement failure, and interrupted-visit quarantine.
- [ ] Run:
  `pytest --collect-only -q tests/test_workflow_lisp_provider_supervision_e2e.py`.
- [ ] Run RED public compile/run tests:

  ```bash
  pytest -q tests/test_workflow_lisp_provider_supervision_e2e.py \
    -k 'compile or run or report or continue or steer or quarantine'
  ```

  Confirm failures cross the ordinary CLI/compiler/executor path rather than
  helper-only construction.
- [ ] Complete missing public-path integration only in the listed
  `build.py`, compiler, build-artifact, CLI run/resume, and report owners,
  without prompt-text assertions or name-keyed branches. Reuse the source-map
  projection completed in Task 12C and
  `StateManager.finalize_step_with_dataflow` unchanged. A required source-map,
  state, or other unlisted production edit requires a reviewed plan amendment.
- [ ] Run:
  `pytest -q tests/test_workflow_lisp_provider_supervision_e2e.py`.
- [ ] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_design_delta_smoke.py \
    tests/test_workflow_lisp_native_returns_e2e.py \
    tests/test_workflow_lisp_provider_call_policy.py \
    tests/test_workflow_lisp_provider_call_policy_e2e.py \
    tests/test_workflow_lisp_lexical_checkpoints.py \
    tests/test_workflow_lisp_source_map.py \
    -k 'not security and not secret and not isolation'
  ```
- [ ] Complete specification review, quality review, and commit:
  `Run provider supervision end to end`.

## Phase 4 — Capability Promotion, Real Smoke, And Closeout

### Task 14: Structural Capability And Real Supervisor Smoke

**Files:**

- Modify: `orchestrator/providers/types.py`
- Modify: `orchestrator/providers/registry.py`
- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/workflow/validation.py`
- Create: `tests/e2e/test_e2e_provider_supervision.py`
- Test: `tests/test_provider_execution.py`
- Test: `tests/test_loader_validation.py`
- Test: `tests/test_workflow_lisp_provider_supervision_e2e.py`

- [ ] Write RED validation tests for `turn_boundary_resume: true`: fresh and
  resume commands required, exactly one `${SESSION_ID}`, a metadata codec with
  a generic `supports_resume_boundary_observation` capability, no exact
  `--ephemeral` argument in either command (with near-lookalike controls),
  requested identity equality, and cancellable lifecycle. Prove provider name,
  TTY, input mode, or stable identity alone never implies capability.
- [ ] Add negative compile/load/runtime tests for an unsupported worker, plus
  positive tests proving a supervisor needs no session capability.
- [ ] Run the new RED capability tests:

  ```bash
  pytest -q \
    tests/test_provider_execution.py::test_turn_boundary_resume_capability_is_structural \
    tests/test_loader_validation.py::test_loader_validates_turn_boundary_resume_session_contract \
    tests/test_workflow_lisp_provider_supervision_e2e.py::test_compile_rejects_worker_without_turn_boundary_resume \
    tests/test_workflow_lisp_provider_supervision_e2e.py::test_compile_accepts_supported_worker_and_supervisor
  ```

- [ ] Implement the structural field and opt in only the real template proven
  by Task 3.
- [ ] Rerun the four-node capability command above.
- [ ] Add one real E2E where a real supervisor observes a real session-capable
  worker, returns `STEER`, and the resumed typed result differs as intended.
- [ ] Run the real smoke in tmux:
  `ORCHESTRATE_E2E=1 pytest -q tests/e2e/test_e2e_provider_supervision.py -s`.
- [ ] If the real supervisor cannot make the correction or the complete
  boundary cannot be proved, do not claim/shipping-enable live correction;
  follow the accepted stop/revise criterion.
- [ ] After the real smoke passes, enable the observation manager as the
  ordinary invocation default and rerun Task 5's complete parity/failure
  matrix using all four concrete Task 5 commands; their parametrization still
  covers explicit disabled and enabled construction. Do not flip the
  `provider_observation_enabled` default before this point.
- [ ] Complete specification review, quality review, and commit:
  `Promote verified provider supervision capability`.

### Task 15: Normative Docs, Full Verification, And Stage 7 Closure

**Files:**

- Modify: `specs/providers.md`
- Modify: `specs/io.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/observability.md`
- Modify: `specs/index.md`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_executable_ir.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify: `docs/workflow_monitoring.md`
- Modify: `docs/design/README.md`
- Modify: `docs/index.md`
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify: this plan

- [ ] Update normative specs from the implemented behavior and mark the
  capability implemented only after Tasks 1-14, including Tasks 12A-12C, are
  green.
- [ ] Check the drafting guide for coherent/current target-2.16 examples,
  typed directive guidance, two-member eligibility, pure settlement, and the
  distinction between panes and result transport.
- [ ] Run `python -m compileall -q orchestrator`.
- [ ] Run:

  ```bash
  pytest --collect-only -q \
    tests/test_provider_session_transport.py \
    tests/test_provider_execution_control.py \
    tests/e2e/test_e2e_codex_provider_session_control.py \
    tests/test_provider_observation.py \
    tests/test_provider_supervision_ir.py \
    tests/test_provider_supervision_runtime.py \
    tests/test_provider_supervision_resume.py \
    tests/test_workflow_lisp_provider_supervision.py \
    tests/test_workflow_lisp_provider_supervision_e2e.py \
    tests/e2e/test_e2e_provider_supervision.py
  ```
- [ ] Run the complete focused Stage 7 selector:

  ```bash
  pytest -q \
    tests/test_provider_session_transport.py \
    tests/test_provider_execution_control.py \
    tests/test_provider_observation.py \
    tests/test_provider_supervision_ir.py \
    tests/test_provider_supervision_runtime.py \
    tests/test_provider_supervision_resume.py \
    tests/test_workflow_lisp_provider_supervision.py \
    tests/test_workflow_lisp_provider_supervision_e2e.py
  ```

- [ ] Rerun both real E2E modules in tmux with `ORCHESTRATE_E2E=1`.
- [ ] Run the broad non-security suite in tmux:

  ```bash
  pytest -q -n 16 --dist=worksteal \
    --ignore=tests/test_provider_isolation_policy.py \
    --ignore=tests/test_provider_isolation_schema_resources.py \
    --ignore=tests/test_secrets.py \
    -k 'not security and not secret and not isolation'
  ```

- [ ] Compare any failures by exact test identity with the latest accepted
  non-security baseline. Fix Stage 7 regressions; do not weaken tests or repair
  unrelated failures.
- [ ] Run independent holistic specification and quality reviews on the exact
  closing tree, then rerun affected selectors after any correction.
- [ ] Mark this plan complete, record commit/test/review evidence, update the
  Stage 7 roadmap gate, and commit:
  `Complete Stage 7 provider live binding`.
- [ ] Immediately advance to Stage 8's live language-server design review and
  implementation planning without requesting confirmation.

## Global Stop / Revise Conditions

Stop dependent Stage 7 implementation and follow the accepted design's revise
path if:

- the real Codex Task 3 boundary cannot prove unique identity plus the exact
  readiness marker while preterminal and within deadline, complete
  leader/PGID/future/capture cleanup, and exact-identity session resume;
- observation changes raw stdout/stderr, timeout, exit, metadata, or result
  semantics;
- any member thread must mutate `WorkflowExecutor` or `StateManager`;
- an interrupted live visit cannot quarantine before any later provider
  launch;
- a replacement turn cannot receive a distinct runtime-owned bundle path and
  freshly rendered typed output contract;
- the form cannot lower through WCC/schema 2 without a direct frontend escape
  path;
- implementation requires provider/workflow/family/module/domain-name
  branching; or
- a genuine existing contract regression appears.

Do not reinterpret a stop condition as permission to weaken a gate.
