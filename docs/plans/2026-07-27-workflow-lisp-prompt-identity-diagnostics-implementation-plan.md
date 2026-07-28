# Workflow Lisp Prompt Identity And Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for every production change. Each task
> receives an independent specification-compliance review followed by a
> distinct implementation-quality review before its exact-path commit. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the accepted Q3 target-2.22 prompt-attempt identity,
content-free role diagnostics, prelaunch evidence, and additive report
projection for direct fragment-backed `provider-result` calls while preserving
all target-2.20/2.21 compiler, runtime, checkpoint, and evidence bytes.

**Architecture:** The compiler emits one target-gated identity-version carrier
and one declaration-ordered binding plan beside the unchanged Q1/Q2 fragment
contract. Runtime owners expose immutable render/composition traces, the
provider executor exposes a closed prepared-policy projection, and a new pure
identity module validates and seals the five roles without parsing prompts or
re-rendering inputs. The existing attempt allocator publishes the closed v2
fragment snapshot after invocation preparation and before launch; report code
strictly validates those persisted records and projects comparison results
without becoming execution or resume authority.

**Tech Stack:** Python 3.11+, immutable dataclasses, canonical JSON and SHA-256,
Workflow Lisp targets 2.20/2.21/2.22, classic and WCC lowering, Surface/Core/
Semantic/Executable IR, persisted surface graphs, lexical checkpoints,
provider-attempt evidence, pytest/pytest-xdist, and tmux for long gates.

---

## Accepted Authority And Plan Status

The implementation authority is:

- commit `9b2aa7ac46c64207c971272c4583c87b90d4c388`;
- `docs/design/workflow_lisp_prompt_identity_diagnostics.md` from that commit;
- the ordered Q3 design and acceptance approvals recorded in that design; and
- the active selector
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`.

Production work may begin only after this exact plan passes ordered independent
specification then quality review and is committed without post-review edits.
No review gate in this document is pre-completed.

If this plan conflicts with the accepted design, correct this plan and repeat
its ordered plan reviews. Do not reinterpret the accepted contract in code.

## Deliberate Cost

This approach adds explicit target-2.22 carriers and closed evidence schemas
instead of making the final prompt or one generic hash authoritative. It makes
future fragment-backed provider operations, new runtime contribution kinds,
new policy fields, or alternate renderer versions require a reviewed schema
and role-version change. That cost is intentional: extending the surface is
harder, while attribution, compatibility, and fail-closed validation remain
auditable.

## Scope And Load-Bearing Constraints

This plan implements only direct fragment-backed `provider-result` at target
2.22:

- optional carrier value
  `workflow_prompt_attempt_identity.v1`, required on that target/surface;
- compiler-owned `compiler_prompt_attempt_binding_plan.v1`;
- the five exact role wrappers and `workflow_prompt_attempt_identity.v1`;
- target-2.22 one-render fragment and runtime-contribution traces;
- target-2.22 typed-input evidence reuse for fragment `value`/`path` slots;
- `workflow_prompt_fragment_snapshot.functional.v2`;
- the closed Q3 invocation-preparation failure record;
- pure fixed-order cross-attempt comparison;
- additive `prompt_context` JSON and Markdown report projection; and
- target/version, normative, authoring, capability, and roadmap closure.

The following constraints are load-bearing:

1. `compiled_prompt_fragment_identity.v1/.v2` and
   `compiler_prompt_fragment_contract.v1/.v2` are never recalculated,
   widened, or byte-changed by Q3.
2. Targets 2.20 and 2.21 omit both Q3 carriers byte-for-byte and preserve their
   compiler artifacts, persisted surfaces, runtime/checkpoint semantics,
   functional-v1 snapshots, and completed-result reuse.
3. Target 2.22 requires the identity-version carrier and binding plan as an
   exact pair through every compiler, persistence, checkpoint, and runtime
   boundary.
4. The binding plan is compiler-owned, declaration ordered, closed, and
   validated against existing Q1 dependency/rendered-slot and Q2
   output-position carriers. Runtime never reconstructs it from source.
5. Each fragment slot is rendered exactly once. Target-2.22 typed evidence
   reuses the same value and raw-renderer digests; it does not call
   `render_view` again.
6. Prompt roles consume existing owners' traces. They never parse the final
   prompt, reopen dependency files, inspect prompt audit logs, or hash ambient
   workspace state.
7. Provider policy comes from the exact successfully prepared invocation and
   contains only provider name, canonical model/effort, timeout, and input
   mode. It is not reconstructed from argv.
8. V2 evidence is one closed, cross-field-consistent record: the retained v1
   projection, Q3 identity, role digests, and composition digest must all
   validate before content-addressed publication.
9. Successful target-2.22 publication occurs after invocation preparation and
   before provider launch. Preparation or publication failure launches no
   provider.
10. Prompt evidence and comparison remain non-authoritative for result,
    checkpoint, resume, retry, cancellation, settlement, or provider liveness.
11. The comparator selects the greatest earlier prompt-snapshot ordinal and
    never skips a newer legacy or invalid candidate to find an older valid v2
    record.
12. Report projection is an intentional additive API effect for every target:
    JSON always gains the exact top-level `prompt_context` sibling, including
    an empty projection when no attempt qualifies. Execution bytes below 2.22
    remain unchanged.
13. No prompt bodies, resolved values, dependency content, argv, environment,
    secrets, or absolute workspace paths enter Q3 persisted records or report
    rows.
14. Q3 adds no Workflow Lisp type, nominal prompt brand, result union, search,
    fitness, judgment value, LSP behavior, coordinated-provider support, or
    arbitrary non-fragment provider identity.

The accepted closed diagnostics remain exact:

- `prompt_attempt_identity_version_missing`
- `prompt_attempt_identity_version_invalid`
- `prompt_attempt_identity_version_mismatch`
- `prompt_attempt_binding_plan_missing`
- `prompt_attempt_binding_plan_invalid`
- `prompt_attempt_binding_plan_mismatch`
- `prompt_attempt_identity_role_invalid`
- `prompt_attempt_identity_policy_invalid`
- `prompt_attempt_identity_final_prompt_mismatch`
- `prompt_attempt_identity_composition_invalid`
- `prompt_identity_composition_mismatch`

Tests assert contracts, identities, byte digests, ordering, and behavior. They
must not assert literal production prompt prose.

## Governing Authorities

Read before implementation:

- `AGENTS.md`
- `docs/index.md`
- `docs/capability_status_matrix.md`
- `docs/design/README.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_lisp_prompt_calculus.md`
- `docs/design/workflow_lisp_prompt_identity_diagnostics.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- `docs/plans/2026-07-26-workflow-lisp-prompt-core-implementation-plan.md`
- `docs/plans/2026-07-26-workflow-lisp-prompt-output-positions-implementation-plan.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/providers.md`
- `specs/state.md`
- `specs/versioning.md`

## Execution Contract

Run every command from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do not create a worktree. Preserve every user and external worktree change.
Tasks execute in order; do not dispatch multiple Q3 implementation agents
against shared files. For every task:

1. dispatch a fresh implementer with the complete task text and the accepted
   design;
2. add the smallest behavioral/contract test first;
3. run it and prove RED for the intended missing Q3 behavior, not a typo,
   collection failure, or unrelated dirty-tree failure;
4. implement only the selected task;
5. rerun the narrow selector GREEN and then the named adjacent regressions;
6. run `pytest --collect-only -q` for every created or renamed test module;
7. capture current `HEAD`, tree, and worktree status before staging;
8. stage only exact task-owned paths or exact hunks into an isolated index;
9. run `git diff --cached --check`, inspect
   `git diff --cached --name-only`, and read the complete staged diff;
10. obtain an independent specification-compliance review against the accepted
    Q3 design and exact candidate diff;
11. resolve every finding and repeat specification review until approved;
12. obtain a distinct implementation-quality review only after specification
    approval;
13. if any byte changes after either review, restart ordered specification then
    quality review on the final exact candidate;
14. commit exactly the reviewed paths/bytes with no post-review edits; and
15. run the task's post-commit selector from fresh command output.

Use one exact-path commit per task. Never use `git add .`, `git add -A`,
destructive checkout/reset, or whole-file staging of a shared dirty path.
Never weaken a test or broaden Q3 to make a failure disappear.

Use the `tmux` skill for any command expected to exceed one minute and for the
closing broad suite. Wait for the configured review provider/model; do not
substitute a faster model.

All security, safety, secrets, and provider-isolation production modules,
tests, and documentation are outside this plan. Do not inspect them as Q3
authorities, modify them, stage them, or include them in focused selectors.

## Concurrent-Edit And Collision Contract

At plan drafting time the following Task 5 production and test files contain
concurrent dirty changes:

```text
orchestrator/providers/types.py
orchestrator/providers/executor.py
orchestrator/workflow/executor.py
orchestrator/workflow/prompt_dependency_evidence.py
tests/test_prompt_dependency_evidence.py
tests/test_provider_attempt_allocation.py
```

Task 5 must begin with a fresh collision audit for each path separately:

```bash
git rev-parse HEAD
git rev-parse HEAD^{tree}
git rev-parse HEAD:<path>
git hash-object <path>
git diff --binary HEAD -- <path>
git diff --stat HEAD -- <path>
```

Store one baseline patch per path under a Q3-specific directory outside the
repository. Compare function-level ownership and current line locations after
the capture. If Q3 and ambient changes touch the same function, reconcile the
current complete function explicitly; do not replay a stale whole-file patch.
Stage with edited patches or an alternate index and verify that ambient hunks
remain unstaged. No whole-file staging is permitted for these six paths.

Repeat the audit if `HEAD` changes, a working-file hash changes unexpectedly,
or an external commit lands before the Task 5 commit. Rerun the task tests and
both ordered reviews after any reconciliation.

Every path that is already dirty when a Q3 task first touches it receives the
same per-path baseline, function/section-level reconciliation, exact-hunk
staging, and exact-candidate review before that task commits. This first-touch
rule applies to production, test, specification, plan, and routing paths, not
only the six Task 5 paths. Q3 must not overwrite the completed L-series status,
the owner-directed roadmap coherence edits, or any other concurrent work.

## M0 Coordination Boundary

The concurrently executing M0 maintenance tranche owns or may touch:

```text
tests/test_at61_at62_wait_for_path_safety.py
tests/test_cli_safety.py
tests/test_secrets.py
tests/test_workflow_semantic_ir.py
tests/test_workflow_output_contract_integration.py
the refusal-diagnosability plan targets
the typecheck owner modules
```

Q3 does not edit the security/safety/secrets entries, the refusal-
diagnosability targets, or the typecheck owner modules. Task 1 must not begin
until M0 completion is recorded because Q3 later adds exact carrier tests to
`tests/test_workflow_semantic_ir.py`. At Task 1 entry, recapture that file's
HEAD/working blobs and inspect the landed M0 diff before adding or staging only
Q3-specific hunks. If a later implementation review identifies a genuine need
for `tests/test_workflow_output_contract_integration.py`, treat it as a new
collision: wait for M0 completion, amend and re-review this plan, and only then
edit it. Merely excluding the first three modules from the broad command does
not grant Q3 authority to inspect or change them.

## File And Responsibility Map

Compiler target, binding plan, and carriage:

- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/prompts.py`
- `orchestrator/workflow_lisp/lowering/phase_scope.py`
- `orchestrator/workflow_lisp/lowering/effects.py`
- `orchestrator/workflow/prompt_fragment_contract.py`
- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/core_ast.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/elaboration.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/validation.py`

Persistence, checkpoint, and runtime carriage:

- `orchestrator/workflow/persisted_surface.py`
- `orchestrator/workflow/runtime_step.py`
- `orchestrator/workflow_lisp/lexical_checkpoints.py`

Pure identity and evidence:

- Create `orchestrator/workflow/prompt_identity.py`
- `orchestrator/workflow/prompt_dependency_evidence.py`
- `orchestrator/workflow/provider_attempts.py` is inspect-only unless an
  exact generic allocator query helper is demonstrably required.

Render and composition owners:

- `orchestrator/workflow/prompting.py`
- `orchestrator/workflow_lisp/typed_prompt_inputs.py`

Prepared policy and execution:

- `orchestrator/providers/types.py`
- `orchestrator/providers/executor.py`
- `orchestrator/workflow/executor.py`

Report projection:

- Create `orchestrator/workflow/prompt_context_report.py`
- `orchestrator/observability/report.py`
- `orchestrator/cli/commands/report.py`

Primary focused tests:

- Create `tests/test_workflow_lisp_prompt_identity_carriage.py`
- Create `tests/test_workflow_lisp_prompt_identity_persistence.py`
- Create `tests/test_workflow_lisp_prompt_identity_render_trace.py`
- Create `tests/test_prompt_identity.py`
- Create `tests/test_workflow_lisp_prompt_identity_runtime.py`
- Create `tests/test_prompt_context_report.py`
- Create `tests/test_workflow_lisp_prompt_identity_e2e.py`

Existing adjacent regression tests are named per task below.

## Reviewed Plan-Acceptance Routing Gate

After this exact plan passes its ordered plan reviews and before Task 1, update
the active routing surfaces to state one truthful transition: the Q3 design and
implementation plan are accepted, Q3 implementation is next and not yet
complete, and Q4 remains blocked on Q3 completion. The exact routing candidate
is limited to:

- `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- `docs/index.md`
- `docs/design/README.md`
- `docs/capability_status_matrix.md`
- `tests/test_workflow_lisp_drain_roadmap_routing.py`
- this implementation plan, if it has not already landed separately.

Apply the first-touch collision audit to every dirty routing path. Preserve all
completed Q/L status, the M0/MR-4/L3 coordination clauses, the owner-directed
coherence edits, and unrelated concurrent hunks. Add behavioral routing
assertions for the accepted-plan/implementation-next state without freezing
prose. Obtain ordered independent specification then quality review of the
exact acceptance-routing candidate and commit those reviewed bytes before any
Task 1–6 implementation begins. This plan may land in an earlier exact-plan
commit or in that routing commit, but no routing surface may claim plan
acceptance before the exact plan is approved.

## Preimplementation Plan And Control Gate

Before Task 1:

- [ ] Obtain independent specification review of this exact plan against the
  accepted Q3 design; resolve every finding and repeat.
- [ ] Obtain distinct implementation-quality review of the exact same plan
  bytes.
- [ ] Either patch-stage only this new file, run `git diff --cached --check`,
  inspect the complete staged plan, and commit the exact reviewed bytes, or
  carry those exact approved bytes into the reviewed plan-acceptance routing
  commit.
- [ ] Complete and commit the Reviewed Plan-Acceptance Routing Gate. Verify that
  every router and capability surface says plan accepted, implementation next,
  and not implemented.
- [ ] Run the active roadmap routing selector:

  ```bash
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py \
    -k 'language_quality or prompt_identity or prompt_calculus or post_stage_8'
  ```

- [ ] Confirm M0 is complete before collecting any comparison baseline. Bind
  the landed M0 completion `HEAD` and tree, inspect its committed path/diff
  inventory, and recapture the HEAD/working blobs plus landed M0 diff for
  `tests/test_workflow_semantic_ir.py`. Do not dispatch Task 1 or reuse any
  pre-M0 collection as the Q3 control.
- [ ] From the bound post-M0, post-routing `HEAD`/tree, run both the exact broad
  non-security collection and suite commands from Task 7 in tmux as the pre-Q3
  control. Record commit/tree, collected node IDs, totals, failing node IDs,
  and dirty-tree inventory. Do not repair excluded or unrelated failures.

## Task 1: Target 2.22 Binding Plan And Compiler/IR Carriage

**Files:**

- Modify: `orchestrator/workflow_lisp/syntax.py`
- Modify: `orchestrator/workflow_lisp/prompts.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`
- Modify: `orchestrator/workflow_lisp/lowering/effects.py`
- Modify: `orchestrator/workflow/prompt_fragment_contract.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/validation.py`
- Create: `tests/test_workflow_lisp_prompt_identity_carriage.py`
- Modify: `tests/test_workflow_lisp_prompt_calculus.py`
- Modify: `tests/test_workflow_shared_validation.py`
- Modify: `tests/test_workflow_surface_ast.py`
- Modify: `tests/test_workflow_core_ast.py`
- Modify: `tests/test_workflow_semantic_ir.py`

- [ ] **Step 1: Write target and plan RED tests.**
  Add target-2.22 admission and target-2.20/2.21 omission controls. At target
  2.22, pair a Q1 fragment without `:out` with a Q2 fragment using `:out`;
  prove the former retains
  `compiled_prompt_fragment_identity.v1`/`compiler_prompt_fragment_contract.v1`
  while the latter retains the corresponding v2 identity/contract. Use the Q2
  case to build one interleaved `doc/text/value/path` fragment with refinement,
  then assert the exact Q3 carrier token, binding-plan schema, contiguous
  declaration ordinals, unique slot names, delivery, output role, runtime
  locators, renderer/null renderer, and canonical `plan_sha256`.
- [ ] **Step 2: Write fail-closed plan RED tests.**
  Reject missing/unpaired carrier or plan, unknown identity version, unknown
  plan schema, extra/missing/reordered/duplicate rows and locators, bad
  renderer version, non-null document renderer, wrong refinement/output role,
  disagreement with Q1 rendered/dependency rows, disagreement with Q2 output
  positions, and independently resealed plan tampering. Bind failures to the
  accepted missing/invalid/mismatch diagnostics and provider-application source
  owner.
- [ ] **Step 3: Prove RED is intentional.**

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_prompt_identity_carriage.py
  pytest -q \
    tests/test_workflow_lisp_prompt_identity_carriage.py \
    tests/test_workflow_lisp_prompt_calculus.py \
    -k 'target_2_22 or binding_plan or prompt_attempt_identity_version'
  ```

  Expected: collection succeeds; new cases fail because 2.22 and Q3 carriage
  do not exist. Frozen Q1/Q2 controls remain green.
- [ ] **Step 4: Add the closed target and compiler-owned plan.**
  Admit 2.22 in syntax/shared validation. Construct one immutable binding-plan
  carrier from the already resolved declaration plus existing Q1 dependency/
  rendered-slot and Q2 output-position rows. Fix rendered renderer version to
  1; bind value/path to their selected typed-input carrier; make text
  `raw-utf8-string` v1 without adding typed evidence; keep document renderer
  null. Digest the closed plan without `plan_sha256`.
- [ ] **Step 5: Carry the pair through classic and WCC compiler paths.**
  Add optional `prompt_attempt_identity_version` and
  `compiler_prompt_attempt_binding_plan` fields to typed provider application,
  Surface, Core, Semantic, and Executable provider configurations. Carry them
  through elaboration and lowering without reconstruction. Require the pair at
  2.22 and omit both below target. Prove classic and WCC produce equal
  carriers, plans, existing Q1/Q2 fragment identities, dependency contracts,
  output positions, source owners, and executable configurations.
- [ ] **Step 6: Add every IR-boundary negative control.**
  For Surface/Core/Semantic/Executable serialization and reconstruction,
  mutate one side at a time: missing version, missing plan, unequal plan
  digest, reordered row, changed locator, extra row, and plan/fragment
  disagreement. Ensure no boundary silently defaults or regenerates data.
- [ ] **Step 7: Run GREEN and adjacent compiler regressions.**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_prompt_identity_carriage.py \
    tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_shared_validation.py \
    tests/test_workflow_surface_ast.py \
    tests/test_workflow_core_ast.py \
    tests/test_workflow_semantic_ir.py \
    tests/test_workflow_lisp_build_in_memory.py
  ```

- [ ] **Step 8: Review and commit.**
  Stage only the Task 1 paths, inspect the complete exact diff, obtain ordered
  specification then quality approval, commit those exact bytes, and rerun the
  selector from the commit.

**Task 1 completion gate:** Target 2.22 emits one valid paired carrier/plan
through both lowering routes and every named IR boundary; every missing,
malformed, or mismatched dimension fails closed; a target-2.22 Q1 fragment
without `:out` retains v1 fragment identity while a Q2 `:out` fragment retains
v2; and targets 2.20/2.21 retain their exact prior carrier and fragment-identity
bytes.

## Task 2: Persisted Surface V3, Checkpoint, And RuntimeStep Carriage

**Files:**

- Modify: `orchestrator/workflow/persisted_surface.py`
- Modify: `orchestrator/workflow/runtime_step.py`
- Modify: `orchestrator/workflow_lisp/lexical_checkpoints.py`
- Create: `tests/test_workflow_lisp_prompt_identity_persistence.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_build_in_memory.py`
- Modify: `tests/test_runtime_step_lifecycle.py`
- Modify: `tests/test_workflow_lisp_lexical_checkpoints.py`
- Modify: `tests/test_workflow_lisp_checkpoint_identity_comparison.py`
- Modify: `tests/test_workflow_lisp_prompt_calculus_runtime.py`

- [ ] **Step 1: Freeze v1/v2 compatibility bytes before adding v3.**
  Add canonical golden assertions for a target-2.20 Q1 graph, target-2.21 Q1
  graph, target-2.21 Q2 graph, their decoded RuntimeSteps, and representative
  checkpoint program-identity payloads.
- [ ] **Step 2: Write persisted-v3 RED tests.**
  A graph containing a target-2.22 fragment step must use
  `persisted_workflow_surface_graph.v3`; the affected step must carry the exact
  Q3 version/plan pair beside its existing Q1/Q2 fields. Mixed graphs retain
  the exact old step key sets for target-2.20/2.21 and non-fragment steps.
- [ ] **Step 3: Write codec/runtime/checkpoint RED negatives.**
  Test encode and decode rejection for absent/extra/unpaired/malformed/version-
  mismatched/reordered/digest-mismatched data. Test RuntimeStep rejection for a
  dropped or mutated pair. Test checkpoint identity changes on Q3 plan/carrier
  drift, compatible reuse on equality, and ordinary program-identity refusal
  without reading prompt evidence.
- [ ] **Step 4: Prove RED is intentional.**

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_prompt_identity_persistence.py
  pytest -q \
    tests/test_workflow_lisp_prompt_identity_persistence.py \
    tests/test_runtime_step_lifecycle.py \
    -k 'prompt_attempt or persisted_surface_graph_v3 or binding_plan'
  ```

- [ ] **Step 5: Add exact persisted-surface v3 carriage.**
  Encode v3 only when a Q3 pair exists. Decode v1/v2 with their previous closed
  key sets and behavior. Decode v3 with exact per-step key sets and pair
  validation. Never emit empty Q3 fields on older or unrelated steps.
- [ ] **Step 6: Carry and validate through RuntimeStep/checkpoints.**
  Expose immutable RuntimeStep accessors, include the Q3 pair in the existing
  provider configuration/program identity, and preserve lexical checkpoint
  schema/state version. Do not copy attempt evidence into checkpoints.
- [ ] **Step 7: Add completed-boundary independence controls.**
  A compatible completed result reuses without invocation preparation or
  prompt-evidence reads. A pending/failed boundary carries the Q3 config into a
  fresh attempt. Missing/damaged evidence cannot invalidate an otherwise
  compatible completed result.
- [ ] **Step 8: Run GREEN and adjacent persistence regressions.**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_prompt_identity_persistence.py \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_workflow_lisp_build_in_memory.py \
    tests/test_runtime_step_lifecycle.py \
    tests/test_workflow_lisp_lexical_checkpoints.py \
    tests/test_workflow_lisp_checkpoint_identity_comparison.py \
    tests/test_workflow_lisp_prompt_calculus_runtime.py
  ```

- [ ] **Step 9: Review and commit.**
  Stage only Task 2 paths; obtain ordered specification then quality approval;
  commit the exact reviewed bytes and rerun the selector.

**Task 2 completion gate:** Persisted v3, RuntimeStep, and checkpoint carriage
round-trip the exact pair; v1/v2 and state-schema-2.1 bytes remain frozen;
resume compatibility depends on program/configuration carriage only, never Q3
evidence.

## Task 3: One-Render Fragment Trace And Typed-Evidence Reuse

**Files:**

- Modify: `orchestrator/workflow/prompting.py`
- Modify: `orchestrator/workflow_lisp/typed_prompt_inputs.py`
- Create: `tests/test_workflow_lisp_prompt_identity_render_trace.py`
- Modify: `tests/test_workflow_lisp_typed_prompt_inputs.py`
- Modify: `tests/test_workflow_lisp_prompt_calculus_runtime.py`

- [ ] **Step 1: Write one-render RED tests.**
  At target 2.22, render an interleaved fragment with text, value, and path
  slots plus repeated placeholders. Count renderer calls and require exactly
  one call for each value/path slot and no typed-registry call for text.
- [ ] **Step 2: Write exact-byte RED vectors.**
  Assert strict UTF-8 raw text bytes; canonical transport-value digest;
  raw-renderer digest; substitution length/digest; no LF removal for text; and
  removal of exactly one trailing LF for value/path. Include a renderer output
  with no LF and one with multiple trailing LFs.
- [ ] **Step 3: Write trace/evidence both-direction RED negatives.**
  Reject missing, extra, duplicate, reordered, wrong-name, wrong-kind,
  renderer/version, value-digest, raw-renderer-digest, and substitution-digest
  rows. Include trace-present/evidence-missing and evidence-present/trace-
  missing controls. Text must have a trace row and no typed-evidence row.
- [ ] **Step 4: Prove RED and preserve old-target controls.**

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_prompt_identity_render_trace.py
  pytest -q \
    tests/test_workflow_lisp_prompt_identity_render_trace.py \
    tests/test_workflow_lisp_typed_prompt_inputs.py \
    -k 'one_render or fragment_trace or trace_reuse or target_2_22'
  ```

- [ ] **Step 5: Return a target-gated immutable render result.**
  Keep the current string-only behavior below 2.22. At 2.22 return the rendered
  base plus declaration-ordered immutable metadata. Render each slot once,
  retain substitution text only in memory, and persist neither values nor
  bytes.
- [ ] **Step 6: Reuse trace digests for typed evidence.**
  Add a target-2.22 fragment-owned typed-evidence path that validates selected
  typed-input carriers against the trace, then builds the existing typed-input
  evidence key from the trace value/raw-renderer digests without invoking
  `render_view`. Preserve the existing evidence schema.
- [ ] **Step 7: Add negative controls against accidental re-rendering.**
  Monkeypatch the renderer to return different bytes on a second call and
  prove target 2.22 still performs one call; prove targets 2.20/2.21 retain
  their old renderer path and exact outputs.
- [ ] **Step 8: Run GREEN and adjacent render regressions.**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_prompt_identity_render_trace.py \
    tests/test_workflow_lisp_typed_prompt_inputs.py \
    tests/test_workflow_lisp_prompt_calculus_runtime.py \
    tests/test_prompt_contract_injection.py
  ```

- [ ] **Step 9: Review and commit.**
  Stage only Task 3 paths; obtain ordered specification then quality approval;
  commit the exact reviewed bytes and rerun the selector.

**Task 3 completion gate:** Every target-2.22 non-document slot has one exact
trace row, each value/path renderer is called once even with typed evidence,
all correspondence tampering fails before evidence publication, and older
targets retain byte-compatible string-only behavior.

## Task 4: Pure Roles, V2 Record Validation, Comparator, And Failure Schema

**Files:**

- Create: `orchestrator/workflow/prompt_identity.py`
- Create: `tests/test_prompt_identity.py`

- [ ] **Step 1: Write canonical role RED vectors.**
  Cover the five exact wrapper schema tokens, closed payload keys, canonical
  JSON rule, lower-case SHA-256, fixed declaration/composition order, and
  rejection of every extra/missing/malformed/mis-tokened role field.
- [ ] **Step 2: Write role-ownership RED cases.**
  Build fragment-program, resolved-bindings, injected-dependencies, runtime-
  contributions, and provider-policy roles from already-owned projections.
  Assert document `renderer=null`, evaluated-relpath value identity, shown-only
  dependency groups, exact contribution order, and absence of bodies/values/
  argv/environment/absolute paths. Prove a referenced lexical/import input is
  included while an unused lexical binding or unreferenced imported constant
  is excluded and cannot change the resolved-bindings digest. Cover complete,
  truncated, and omitted dependency projections in both directions: complete
  and truncated shown groups plus their exact prepared bytes/summary affect the
  injected-dependencies role; omitted content and bytes beyond a shown prefix
  do not unless they change prepared prompt material.
- [ ] **Step 3: Write v2 cross-field RED cases.**
  Make the pure Q3 validator consume an already validated retained-v1
  projection, then require exact equality for final prompt, fragment
  identity/version, document authored-row subsequence, canonical shown groups,
  and injection. Reseal one mismatch for every relation to prove cross-field
  validation catches internally sealed tamper. Separately reject role and
  composition digest tamper. Task 5's composite evidence validator must call
  the existing functional-v1 validator first and only then call this pure Q3
  validator; this split avoids a circular dependency between the identity and
  evidence-publication modules without weakening the v1-first rule.
- [ ] **Step 4: Write preparation-failure RED cases.**
  Accept only
  `workflow_prompt_fragment_preparation_failure.functional.v1` with the exact
  fragment/failure/provider-call objects. Tamper every field and prove the
  record cannot contain error messages, parameters, command material, or
  guessed policy.
- [ ] **Step 5: Write comparator RED matrix.**
  Cover every single role and multi-role difference in fixed order, unchanged
  context, no predecessor, missing current, invalid current/previous, legacy
  predecessor, unresolved policy, equal roles with unequal final prompt, and
  composition-seal tamper. Prove the greatest earlier prompt-snapshot
  candidate is selected without skipping a newer legacy/invalid snapshot.
  Prove a valid same-`ProviderAttemptScope` pair with a strictly increasing
  ordinal compares, while cross-scope pairs and equal or decreasing ordinals
  are refused fail-closed.
- [ ] **Step 6: Prove RED is intentional.**

  ```bash
  pytest --collect-only -q tests/test_prompt_identity.py
  pytest -q tests/test_prompt_identity.py
  ```

- [ ] **Step 7: Implement the pure closed module.**
  Use immutable values and side-effect-free builders/validators/comparator.
  Keep filesystem publication, allocator mutation, provider preparation,
  runtime status, and report rendering out of this module.
- [ ] **Step 8: Add instruction/input attribution controls.**
  A template-only program change classifies only `instruction_drift`; a
  resolved binding change classifies only `input_drift`; equal role digests
  plus unequal final prompt returns only the closed composition-mismatch
  unavailability reason.
- [ ] **Step 9: Run GREEN.**

  ```bash
  pytest -q tests/test_prompt_identity.py
  ```

- [ ] **Step 10: Review and commit.**
  Stage only the new production module and its test; obtain ordered
  specification then quality approval; commit exact reviewed bytes.

**Task 4 completion gate:** Pure builders and validators enforce every closed
schema and cross-field equality; comparison is deterministic and fixed-order;
no function reads files, mutates runtime, prepares/launches providers, or
parses prompt text.

## Task 5: Segment Trace, Prepared Policy, And Prelaunch Publication

**Files:**

- Modify exact isolated hunks only:
  `orchestrator/providers/types.py`
- Modify exact isolated hunks only:
  `orchestrator/providers/executor.py`
- Modify exact isolated hunks only:
  `orchestrator/workflow/executor.py`
- Modify exact isolated hunks only:
  `orchestrator/workflow/prompt_dependency_evidence.py`
- Modify: `orchestrator/workflow/prompting.py`
- Create: `tests/test_workflow_lisp_prompt_identity_runtime.py`
- Modify: `tests/test_provider_call_policy.py`
- Modify: `tests/test_provider_execution.py`
- Modify: `tests/test_prompt_contract_injection.py`
- Modify exact isolated hunks only:
  `tests/test_prompt_dependency_evidence.py`
- Modify exact isolated hunks only:
  `tests/test_provider_attempt_allocation.py`
- Modify: `tests/test_workflow_lisp_prompt_calculus_runtime.py`

- [ ] **Step 1: Perform the mandatory fresh collision audit.**
  Capture separate current baselines for all six named dirty production/test
  files using the Concurrent-Edit And Collision Contract. Reconcile each
  working blob against its HEAD blob and baseline patch before editing. Inspect
  current definitions and tests around `ProviderInvocation`,
  `prepare_invocation`, fragment evidence building/publication, fragment
  rendering/typed evidence, attempt allocation, prompt completion, and provider
  execution. Stop this task locally if exact Q3 hunks cannot be isolated; do
  not overwrite or stage ambient changes.
- [ ] **Step 2: Write runtime-contribution trace RED tests.**
  Cover consumed-artifact prepend/append, disabled/empty/no-shown-value
  negatives, output-position only, structured-result only, both suffixes, and
  exact consumed-before-output-position-before-structured-result order.
  Require one separator-inclusive trace row per non-empty inserted segment and
  none for empty contributions.
- [ ] **Step 3: Write segment-trace tamper RED negatives.**
  Reject missing/extra/reordered/duplicate rows, wrong position/kind/ordinal,
  byte length/digest mismatch, and final-prompt gap/overlap. Count composer
  calls to prove consumed rendering and each output block occur once.
- [ ] **Step 4: Write prepared-policy RED tests.**
  Require the closed provider name/model/effort/timeout/input-mode projection
  from the successfully prepared invocation. Cover each field changed and
  null canonical model/effort/timeout. Reject unknown/extra fields, nonpositive
  timeout, unknown input mode, session-only additions, and any argv-derived
  reconstruction.
- [ ] **Step 5: Write ordering and zero-launch RED tests.**
  Assert target-2.22 order: validate carriers; allocate; resolve/snapshot/
  compose; prepare invocation/policy; build/validate v2; publish and append
  existing event; launch. Preparation failure publishes the exact Q3 failure
  record and launches zero times. Snapshot/role/composition/publication failure
  launches zero times. Publication failure leaves allocation-only state.
- [ ] **Step 6: Write compatibility and scope RED negatives.**
  Targets 2.20/2.21 retain v1 evidence bytes and prior prepare/launch behavior.
  Extern-backed evidence stays unchanged. Non-fragment provider calls and
  provider session/supervision/peer operations do not gain Q3 identity.
  Dependency failures retain their existing schema. A target-2.22 fragment
  never silently publishes v1.
- [ ] **Step 7: Prove RED is intentional.**

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_prompt_identity_runtime.py
  pytest -q \
    tests/test_workflow_lisp_prompt_identity_runtime.py \
    tests/test_prompt_dependency_evidence.py \
    tests/test_provider_call_policy.py \
    -k 'prompt_identity or prepared_policy or prelaunch or preparation_failure'
  ```

- [ ] **Step 8: Expose immutable one-call composition segments.**
  Extend target-2.22 composer results without changing below-target string
  APIs. Trace the exact inserted bytes at their existing owners, validate
  segment coverage against final prompt composition, and persist only length
  and digest metadata.
- [ ] **Step 9: Add the closed prepared-policy projection.**
  Extend the resolved invocation context with an immutable Q3 policy
  projection produced from merged/substituted canonical values. Keep command,
  environment, secret resolution, session variants, and provider registry
  internals out of it. Preserve existing invocation behavior and API below the
  Q3 consumer.
- [ ] **Step 10: Integrate v2 and preparation-failure publication.**
  Reuse the Task 4 pure builders. Extend the existing functional evidence owner
  with one composite v2 validator that first validates the exact retained v1
  projection using the existing v1 owner and then applies Task 4's Q3
  cross-field checks. Publish closed v2 records and exact Q3 preparation
  failures through the existing allocator, content-addressed path, lock,
  immutable write, and `evidence_published` event. Do not add a second
  allocator or evidence root.
- [ ] **Step 11: Reorder target-2.22 execution only.**
  Feed the Task 3 trace and Task 5 segment/policy traces into roles, compare the
  exact prepared prompt bytes for stdin or argv substitution, publish before
  launch, and stop fail-closed on every error. Preserve retry allocation and
  completed-result reuse semantics.
- [ ] **Step 12: Run GREEN and adjacent runtime regressions.**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_prompt_identity_runtime.py \
    tests/test_provider_call_policy.py \
    tests/test_provider_execution.py \
    tests/test_prompt_contract_injection.py \
    tests/test_prompt_dependency_evidence.py \
    tests/test_provider_attempt_allocation.py \
    tests/test_workflow_lisp_prompt_calculus_runtime.py \
    tests/test_workflow_lisp_typed_prompt_inputs.py
  ```

- [ ] **Step 13: Audit staged isolation, review, and commit.**
  Build an isolated exact-path/hunk index. Prove the staged diff contains no
  ambient changes from the six collision paths and no security/safety/
  secrets/provider-isolation path. Obtain ordered specification then quality
  approval of that exact candidate. Commit exactly those reviewed hunks and
  rerun the selector.

**Task 5 completion gate:** The five roles derive from one render/composition/
preparation path; target-2.22 v2 evidence is valid and published before launch;
every failure launches zero providers; old targets and non-consumers preserve
their existing behavior/bytes; all six dirty-file integrations are
hunk-isolated and independently reviewed.

## Task 6: JSON And Markdown Prompt-Context Report Projection

**Files:**

- Create: `orchestrator/workflow/prompt_context_report.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `orchestrator/cli/commands/report.py`
- Create: `tests/test_prompt_context_report.py`
- Modify: `tests/test_observability_report.py`
- Modify: `tests/test_cli_report_command.py`

- [ ] **Step 1: Write exact top-level report RED tests.**
  For authored-workflow and state-only report paths, require exact top-level
  keys `run`, `progress`, `steps`, `prompt_context` and the closed empty
  `workflow_prompt_context_report.v1` projection when no scope qualifies.
  Cover target 2.20, 2.21, 2.22, mixed-target, and no-qualified-attempt runs.
- [ ] **Step 2: Write qualification/order RED tests.**
  Qualify only from strictly validated fragment snapshots, strictly validated
  existing fragment-origin failure records, or strictly validated Q3
  preparation failures. Reject inference from step names, paths, record kind
  alone, and unvalidated schema claims. Order rows by terminal prompt-index
  `(runtime_step_id UTF-8 bytes, visit_key, ordinal)` for terminal and running
  reports. In every qualified scope, use the allocator as the row domain and
  require exactly one report row for every allocated ordinal. Cover contiguous
  and gapped allocations, and prove duplicate publications/records cannot
  duplicate a row while an allocated ordinal with no record still produces one
  `allocation_only` row.
- [ ] **Step 3: Write closed row/status RED matrix.**
  Cover `snapshot`, `legacy_snapshot`, `failure`, `allocation_only`, and
  `invalid`; exact nullability of `record_sha256`/`identity`; every available
  and unavailable comparison reason; no predecessor; and all five ordered role
  digests. Include running, failed, completed, and state-only snapshots.
- [ ] **Step 4: Write predecessor-selection RED negatives.**
  A newer legacy or invalid prompt snapshot must block fallback to an older
  valid v2 snapshot. Failure publications and allocation-only gaps are skipped
  as predecessor candidates. Invalid claimed digests are never echoed in the
  report.
- [ ] **Step 5: Write content-free Markdown RED tests.**
  Add `Prompt context` after ordinary steps with the same order/status/role/
  classification data. Assert absence of sentinel prompt text, resolved
  values, dependency bytes, commands, environment, and absolute paths without
  freezing prose.
- [ ] **Step 6: Prove RED is intentional.**

  ```bash
  pytest --collect-only -q tests/test_prompt_context_report.py
  pytest -q \
    tests/test_prompt_context_report.py \
    tests/test_observability_report.py \
    tests/test_cli_report_command.py \
    -k 'prompt_context'
  ```

- [ ] **Step 7: Implement one pure read-only projection owner.**
  Read allocator state and run-owned evidence, validate records with Task 4,
  produce exact closed rows and comparisons, and make no writes or runtime
  decisions. Share it between loaded-workflow and state-only reports.
- [ ] **Step 8: Add the intentional API and Markdown projection.**
  Always attach `prompt_context` after `steps` in JSON construction. Render one
  content-free Markdown section after steps. Do not alter run/progress/step
  semantics.
- [ ] **Step 9: Prove runtime/resume independence.**
  Monkeypatch report projection to fail and show normal execution/resume does
  not import/call it. Missing/damaged evidence affects only the closed report
  status/reason.
- [ ] **Step 10: Run GREEN and adjacent report regressions.**

  ```bash
  pytest -q \
    tests/test_prompt_context_report.py \
    tests/test_observability_report.py \
    tests/test_cli_report_command.py \
    tests/test_provider_attempt_allocation.py \
    tests/test_prompt_dependency_evidence.py
  ```

- [ ] **Step 11: Review and commit.**
  Stage only Task 6 paths; obtain ordered specification then quality approval;
  commit exact reviewed bytes and rerun the selector.

**Task 6 completion gate:** Both report paths always expose the exact additive
API; every attempt status/comparison case is deterministic and content-free;
each qualified scope has exactly one row per allocated ordinal;
running/failed/completed/state-only projections agree; runtime and resume do
not depend on report validation.

## Task 7: E2E Compatibility, Normative/Authoring Closure, And Final Gates

**Files:**

- Create: `tests/test_workflow_lisp_prompt_identity_e2e.py`
- Modify: `tests/test_workflow_lisp_prompt_calculus_e2e.py`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify: `specs/dsl.md`
- Modify: `specs/io.md`
- Modify: `specs/providers.md`
- Modify: `specs/state.md`
- Modify: `specs/versioning.md`
- Modify: `specs/index.md`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_prompt_calculus.md`
- Modify: `docs/design/README.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md`
- Modify:
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- Modify:
  `docs/plans/2026-07-27-workflow-lisp-prompt-identity-diagnostics-implementation-plan.md`

- [ ] **Step 1: Capture every shared dirty path before editing.**
  Record separate HEAD/working blobs and binary patches. Reconcile completed
  L-series and owner-directed roadmap text. Stage only Q3 hunks; never
  whole-file stage a shared dirty doc/test.
- [ ] **Step 2: Write deterministic retry E2E RED.**
  Compile and execute one direct fragment-backed target-2.22 call with a
  scripted provider. Force a retry with independently changed bindings,
  dependency shown bytes, runtime contribution, and provider policy across
  controlled cases. Assert exactly one v2 record per attempt, prelaunch
  publication, fixed classifications, terminal report, and no prompt bodies.
- [ ] **Step 3: Write compatibility E2E RED/controls.**
  Execute representative target-2.20 Q1 and target-2.21 Q2 fragments; compare
  frozen compiled fragment identities/contracts, persisted graphs, checkpoints,
  v1 evidence, provider prompts/calls, results, and completed-boundary reuse.
  Their reports intentionally gain only the additive `prompt_context` API
  effect: a strictly validated v1 fragment snapshot projects as
  `legacy_snapshot`, while the empty projection remains the exact control for
  a run with no qualified fragment-backed attempt.
- [ ] **Step 4: Prove RED is intentional.**

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_prompt_identity_e2e.py
  pytest -q \
    tests/test_workflow_lisp_prompt_identity_e2e.py \
    tests/test_workflow_lisp_prompt_calculus_e2e.py
  ```

- [ ] **Step 5: Update normative and authoring surfaces.**
  Document target 2.22, exact carriers/diagnostics, v2 evidence, preparation
  failure, prelaunch ordering, content-free role meanings, additive report API,
  compatibility/non-authority boundaries, and direct-fragment-only scope.
  Keep the accepted design as the detailed authority; do not duplicate its
  full schema into every guide.
- [ ] **Step 6: Update capability and routing truthfully.**
  Mark Q3 implemented only after Tasks 1–6 and E2E are green. Preserve Q4 and
  all unselected stages as future/unselected. Preserve completed Q/L stages and
  owner coherence edits. Add behavioral routing assertions rather than literal
  prose assertions.
- [ ] **Step 7: Run routing, authoring, and focused Q3 gates.**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_drain_roadmap_routing.py \
    tests/test_workflow_lisp_examples.py \
    tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_lisp_prompt_calculus_runtime.py \
    tests/test_workflow_lisp_prompt_calculus_e2e.py \
    tests/test_workflow_lisp_prompt_identity_carriage.py \
    tests/test_workflow_lisp_prompt_identity_persistence.py \
    tests/test_workflow_lisp_prompt_identity_render_trace.py \
    tests/test_prompt_identity.py \
    tests/test_workflow_lisp_prompt_identity_runtime.py \
    tests/test_prompt_context_report.py \
    tests/test_workflow_lisp_prompt_identity_e2e.py \
    tests/test_prompt_dependency_evidence.py \
    tests/test_provider_attempt_allocation.py \
    tests/test_workflow_lisp_typed_prompt_inputs.py \
    tests/test_observability_report.py \
    tests/test_cli_report_command.py
  ```

- [ ] **Step 8: Run exact broad non-security collection in tmux.**
  Save collected node IDs and compare them with the pre-Q3 control, explaining
  every added/removed node.

  ```bash
  pytest --collect-only -q \
    --ignore=tests/test_at61_at62_wait_for_path_safety.py \
    --ignore=tests/test_cli_safety.py \
    --ignore=tests/test_execution_safety.py \
    --ignore=tests/test_provider_isolation_attestation.py \
    --ignore=tests/test_provider_isolation_backend.py \
    --ignore=tests/test_provider_isolation_backend_identity_negatives.py \
    --ignore=tests/test_provider_isolation_bundle_broker.py \
    --ignore=tests/test_provider_isolation_candidate.py \
    --ignore=tests/test_provider_isolation_controller_lifecycle.py \
    --ignore=tests/test_provider_isolation_environment.py \
    --ignore=tests/test_provider_isolation_environment_cli.py \
    --ignore=tests/test_provider_isolation_execution.py \
    --ignore=tests/test_provider_isolation_network_preflight.py \
    --ignore=tests/test_provider_isolation_policy.py \
    --ignore=tests/test_provider_isolation_runtime_authority.py \
    --ignore=tests/test_provider_isolation_schema_resources.py \
    --ignore=tests/test_provider_isolation_workflow_continuation.py \
    --ignore=tests/test_provider_isolation_workflow_lifecycle.py \
    --ignore=tests/test_provider_launch_shim.py \
    --ignore=tests/test_secrets.py \
    --ignore=tests/test_workflow_provider_isolation_integration.py \
    -k 'not security and not secret and not isolation and not safety'
  ```

- [ ] **Step 9: Run the exact broad non-security suite in tmux.**

  ```bash
  pytest -q -n 16 --dist=worksteal \
    --ignore=tests/test_at61_at62_wait_for_path_safety.py \
    --ignore=tests/test_cli_safety.py \
    --ignore=tests/test_execution_safety.py \
    --ignore=tests/test_provider_isolation_attestation.py \
    --ignore=tests/test_provider_isolation_backend.py \
    --ignore=tests/test_provider_isolation_backend_identity_negatives.py \
    --ignore=tests/test_provider_isolation_bundle_broker.py \
    --ignore=tests/test_provider_isolation_candidate.py \
    --ignore=tests/test_provider_isolation_controller_lifecycle.py \
    --ignore=tests/test_provider_isolation_environment.py \
    --ignore=tests/test_provider_isolation_environment_cli.py \
    --ignore=tests/test_provider_isolation_execution.py \
    --ignore=tests/test_provider_isolation_network_preflight.py \
    --ignore=tests/test_provider_isolation_policy.py \
    --ignore=tests/test_provider_isolation_runtime_authority.py \
    --ignore=tests/test_provider_isolation_schema_resources.py \
    --ignore=tests/test_provider_isolation_workflow_continuation.py \
    --ignore=tests/test_provider_isolation_workflow_lifecycle.py \
    --ignore=tests/test_provider_launch_shim.py \
    --ignore=tests/test_secrets.py \
    --ignore=tests/test_workflow_provider_isolation_integration.py \
    -k 'not security and not secret and not isolation and not safety'
  ```

  Classify every non-pass against the pre-Q3 control and task ownership.
  Never repair excluded security/safety/secrets/provider-isolation work under
  this plan.
- [ ] **Step 10: Build one exact closure candidate.**
  Update this plan only with factual task commits, fresh test outcomes, and
  review results. Stage exact Q3 docs/tests plus that factual record. Run
  `git diff --cached --check`, inspect names, and read the complete diff.
- [ ] **Step 11: Obtain ordered final reviews.**
  First obtain independent holistic specification-compliance review against
  the accepted design and all seven task commits. Only after approval, obtain
  a distinct holistic implementation-quality review. Any byte change restarts
  both reviews in order.
- [ ] **Step 12: Commit exact reviewed closure and verify.**
  Commit the reviewed closure with no post-review edits. Rerun routing and the
  focused Q3 selector from the committed tree.

**Task 7 completion gate:** One deterministic retry E2E proves role
attribution and report projection; target-2.20/2.21 compatibility is fresh and
byte-specific; normative/authoring/routing surfaces agree; broad non-security
results are recorded and classified; and ordered holistic specification then
quality review approves the exact final tree.

### Pre-Review Execution Record

This record is factual through the exact pre-review closure candidate. Final
ordered review and the reviewed closure commit remain pending.

- Tasks 1–6 landed as `507e4b58`, `a4304c91`, `f29aab84`, `4b03b317`,
  `d3e5031c`, the persisted-authority correction `1e3b32dc`, and
  `63eefda5`.
- The Task 7 deterministic retry E2E and the target-2.20/2.21 compatibility
  controls pass. The compatibility contract was corrected before closure:
  a validated v1 fragment snapshot projects as `legacy_snapshot`; only a run
  without a qualified fragment-backed attempt projects the empty control.
- The first exact broad candidate exposed twelve deterministic Q3
  compatibility failures. Both-direction replay passed all twelve at the
  bound pre-Q3 control `bf5d7758` and failed them at the Q3 candidate.
  Auditable bisects attributed the stale target control to `507e4b58`, the
  stale persisted-schema controls to `a4304c91`, and legacy fractional-timeout
  rejection to `d3e5031c`.
- The landed minimal generic seven-path correction is
  `d9e038ef3d1528308b9b6368e5c0a6ba2923c70a`, tree
  `3a52dfa377e0f614253be889b4b7b6192cba7a52`, with parent
  `45468c550e1e195e82b54ed1199cd20edd6fee59`. It advances only stale unknown
  target/schema controls and accepts exact positive integers, including huge
  integers without float conversion, plus finite positive floats. Booleans,
  non-finite values, and nonpositive values still fail closed. Ordered
  `Q3_TIMEOUT` specification then quality review approved the exact
  correction, and its six affected modules passed 615 tests.
- The exact focused Task 7 selector passed 793 tests against the repaired
  pre-record candidate.
- The final pre-record closure candidate is
  `f3f2efef3d4552c2712f6574129cfb7761375ba6`, tree
  `4531e10d4d8d9987073c03be1e26cbc0d4211f9a`. Collection selected 9,943 of
  9,961 nodes with 18 deselected. Against the bound 9,435-node pre-Q3 control,
  the raw delta is 555 additions and 47 removals. Its complete semantic
  partition is Q3 +377/-2 (two versioned-sentinel renames; normalized +375
  genuine), L5/current-parent +74/-1 (one routing rename; normalized +73),
  and lean/current-parent +104/-44 (43 parameter-ID renames and one genuine
  replaced test; normalized +61/-1), with zero unexplained rows.
- The exact broad suite completed in 156.05 seconds with 9,884 passed, 38
  failed, 21 skipped, zero errors, and 33 warnings. Against the 101 pre-Q3
  nonpasses, 37 are common and 64 resolved. The remaining new row was an
  xdist-only LSP build-digest race that passed its clean isolated replay 1/1
  in 3.71 seconds, leaving zero new deterministic nonpasses.
- The collection log SHA-256 is
  `1ce6cf898eeb3f237866c3c0125682cb13475de9966c028d60589cfabb00671f`;
  the suite log SHA-256 is
  `b1728fcbcb2358c80b931a0fe572b0a44679f562d2ca554cfc2e212f06ab93aa`.

## Final Completion Checklist

Q3 is complete only when all of the following are true:

1. target 2.22 is the only target that requires and carries the exact Q3 pair;
2. classic and WCC carriage agree through Surface/Core/Semantic/Executable,
   persisted v3, RuntimeStep, and checkpoint program identity;
3. all missing/invalid/mismatch cases fail closed at their owning boundary;
4. target-2.22 fragment rendering and typed evidence share one renderer call;
5. runtime contribution and provider-policy roles come from exact existing
   owners without prompt parsing, file reopening, or argv inference;
6. v2 success and Q3 preparation-failure records are closed, sealed,
   content-free, allocator-consistent, and published before any launch;
7. comparison and report projection cover every accepted status/reason and
   never become execution/resume authority;
8. report JSON has the intentional additive `prompt_context` key for every
   target and Markdown remains content-free;
9. target-2.20/2.21 compiler/runtime/checkpoint/provider/evidence bytes and
   completed-result reuse remain compatible;
10. no coordinated-provider, non-fragment, search, judgment, LSP, nominal-type,
    security, safety, secrets, or provider-isolation scope entered the diff;
11. each task has its own exact-path commit after ordered specification then
    quality review;
12. focused, E2E, routing, and exact broad non-security gates have fresh
    evidence; and
13. ordered holistic specification then quality review approves the exact
    final committed bytes.
