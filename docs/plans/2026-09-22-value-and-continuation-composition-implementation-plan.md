# Value And Continuation Composition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to execute selected tasks, with
> `superpowers:test-driven-development` for behavior changes and
> `superpowers:verification-before-completion` before completion claims.
> Keep one write-capable implementer active at a time for overlapping owners.
> Track execution with the checkboxes below.

**Goal:** Remove demonstrated `.orc` composition friction in independently
useful increments, then add honest portable context and human continuation.

**Architecture:** Extend the existing typed-value, prompt-rendering, loop,
resolved-call, provider, and run-state owners. Reuse the ordinary compiler and
executor path; add no coordinator framework, parallel value store, or generic
memory service. New context and host-I/O contracts have explicit preparation
tasks before their implementation tasks can start.

**Tech Stack:** Python, Workflow Lisp AST/typechecking/WCC/shared executable
validation, existing JSON contracts and run storage, pytest/pytest-xdist,
deterministic provider fixtures, and real adapter checks where required.

---

## Status, Authorities, And Scope

Status: execution requested by the owner on 2026-09-22 using Terra subagents
for implementation, with Astra for design reviews as subsequently requested.
Packages A–E are implemented on `feat/value-continuation-composition` at targets
2.28–2.32 respectively. D includes real normal-tools capture/fresh binding,
ordinary typed carriage and public committed-boundary resume. E includes
imported conversational loops, answer/cancel recovery and the atomic-consumption
interruption boundary. Normal target-2.32 admission passes all four public CLI
scenarios without test overrides. Implementation verification is complete;
real-caller adoption and qualitative utility evaluation remain follow-on work
as distinguished below.
This development work does not launch or fund the separate research study.

Execution location: `.worktrees/value-continuation-composition`, based on
`5e4e761a`. The parent checkout and unrelated work are preserved. Initial narrow
baseline: five controls passed. Tasks 1–6 are complete. Later packages have
separately bounded evidence below.

Read `docs/index.md` and `docs/capability_status_matrix.md` first. Authorities:

- [Incremental design](../design/workflow_lisp_value_and_continuation_composition.md)
  owns increments 1, 2, and 5 and their dependency boundaries.
- [EC-1 pure-call design](../design/workflow_lisp_pure_call_composition.md)
  owns increment 3. Optional effect annotations are not a prerequisite.
- [PC-1 provider-context design](../design/workflow_lisp_provider_context_values.md)
  owns increment 4. This plan covers its portable ordinary-call slice, not native
  continuation or every provider form.
- [Consumer value-flow architecture](../design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md),
  [frontend baseline](../design/workflow_lisp_frontend_specification.md), and
  [state layout](../design/workflow_lisp_state_layout.md) govern existing owners.
- `specs/dsl.md`, `specs/io.md`, `specs/providers.md`, `specs/state.md`,
  `specs/cli.md`, and `specs/versioning.md` govern current runtime behavior.

This is one plan with separately selectable work packages, not a requirement
to implement all five together. The recommended first package is A. Execute B
next for the progressive-execution consumer; C can proceed independently.
D and E need their own preparation results, not completion of all earlier work.

| Package | Tasks | Delivery boundary | Actual prerequisites |
| --- | --- | --- | --- |
| A: whole-union inputs | 1–2 | Union results consumed directly by a provider | Target-aware rendering and active-value transport proof in Task 1 |
| B: rich loop values | 3–4 | Rich lists survive state, exits, and resume | Complete descriptor/projection path; not A |
| C: pure helpers / EC-1 | 5–6 | Resolved inline pure calls compose in expressions | Phase-order and once-only representation decision in Task 5; not EL-1 |
| D: portable context / PC-1 | 7–9 | Captured context composes and binds to supported ordinary calls | Real adapter and value/publication decisions in Task 7; A–C only for demonstrated blockers |
| E: human input | 10–12 | Ask, suspend, answer/cancel, resume in the same run | Host-operation/state/nested-pause decision in Task 10; not D |

What this approach makes harder: it does not immediately unify callable kinds,
admit every collection/control expression, support native checkpoints, or serve
multiple simultaneous human questions. These are revisable limits, not reasons
to add speculative machinery now or abandon useful callers later.

Execution safety is not the motivation or evaluation axis. Tools stay owned by
agents/providers. State integrity and evaluation order below are correctness
requirements for the promised language behavior.

## Shared Execution And Compatibility Rules

- Run from the repository root. Inspect `git status --short` and preserve other
  agents' work; do not stage the whole tree. Execute in the feature worktree
  recorded above, not the concurrently used parent checkout.
- Each implementation task uses: smallest failing behavioral test → confirm
  intended RED → shared-owner correction → narrow GREEN → relevant integration
  and regressions → independent review → scoped commit when execution includes
  committing. Do not combine unrelated package changes in one commit.
- New test paths and selectors below are **proposed** unless explicitly called
  existing. Collect each added/renamed module with `python -m pytest
  --collect-only -q <module>` before using its selectors. Empty selection is not
  a passing check. Existing fixture infrastructure is the starting point, not
  permission to add a mock-only alternate compiler or executor.
- Use the next available DSL target for each independently delivered widening.
  The inspected checkout supports through 2.27, so A proposes 2.28 if still free
  when executed. Do not reserve numbers for B–E now. At each package's first task,
  record its concrete target in the owning design and version tests before
  implementation; if the target changed, update that package's fixtures once.
- New admission uses one capability predicate at its existing owner and passes
  the actual target/type environment through callers. Freeze old-target behavior,
  including prompt bytes for inputs previously omitted/refused. Register only
  the implemented package's capability; do not preallocate gates for later work.
- Preserve old persisted runs and unaffected same-target behavior. For new
  programs, test deterministic compilation and clean/resume equivalence. Moving
  an authored workaround is a source change, not a promise to reuse its old
  checkpoint. Do not build another identity or recovery bureaucracy.
- If a proof needs a new payload, state schema, or executable operation, revise
  its owning contract before implementation. That blocks only the affected
  package; it is not grounds to weaken checks or halt independent fixes.

### Baseline check

Integration checkpoint: the shared carriage/replay/persistence and A–C E2E
sweep passed **480 tests** after correcting an older-target regression. Eight
replay tests passed on clean base `5e4e761a` but failed because new record-local
reconstruction changed 2.18 binding identities. Restricting that path to 2.29+
restored all eight with their original assertions unchanged. The final sweep
also covers the corrected host-input shared contracts; it does not establish
completed D/E public delivery. Local log:
`/tmp/astra-composition-final.KVn2pg/compatibility-final.log`.

Run these existing narrow controls before implementation:

```sh
python -m pytest -q \
  tests/test_workflow_lisp_typed_prompt_inputs.py::test_prompt_fragment_renderer_selection_recurses_only_through_admitted_lists \
  tests/test_workflow_lisp_typed_prompt_inputs.py::test_runtime_smoke_renders_typed_prompt_inputs_without_prompt_materialization \
  tests/test_workflow_lisp_nested_transportable_value.py::test_target_225_native_root_preserves_nested_record_schema \
  tests/test_workflow_loops_exhaustion_state.py::test_arm_update_preferred_over_iteration_entry_binding \
  tests/test_workflow_lisp_native_returns_e2e.py::test_provider_root_bool_result_drives_branching_persists_and_resumes
```

Expected: five passing controls. These passed while drafting this plan; they
prove existing mechanisms, not any proposed capability. Diagnose a later
baseline failure rather than rewriting its assertion to suit the new feature.

## A. Whole-Union Provider Inputs

### Task 1: Preserve And Render The Active Value

**Modify:** `orchestrator/workflow_lisp/typed_prompt_inputs.py`,
`orchestrator/workflow_lisp/prompts.py`,
`orchestrator/workflow_lisp/lowering/phase_scope.py`;
`orchestrator/workflow_lisp/syntax.py` and
`orchestrator/workflow/validation.py` for the selected target.
Inspect `orchestrator/workflow_lisp/contracts.py` and
`orchestrator/workflow/view_renderer.py`; change their shared contracts only if
the fixture proves a gap. Inspection established that flattened unions have no
whole-value artifact reference and the existing resolver eagerly reads inactive
fields. Implement the owning design's `typed_union_projection` source in this
task, including its shared validation and runtime resolution; Task 2 must not
inherit an unresolved compiler-only payload. Astra review rejected the initial
flat pointer map using an already-admitted scalar-versus-record field overlap;
the corrected contract uses explicit variant-shaped source trees and preserves
branch-specific boundary references. Astra re-review accepted that correction.
Include the scalar/record collision as a regression.
Additional owners are
`orchestrator/workflow/prompt_fragment_contract.py`,
`orchestrator/workflow/executor.py`, and phased prompt preparation callers in
`orchestrator/workflow/provider_phased_delivery/runtime_bindings.py`.
Reuse existing descriptors and transport validation, not a second value system.
**Tests:** extend
`tests/test_workflow_lisp_typed_prompt_inputs.py` and
`tests/test_workflow_lisp_prompt_calculus.py`; the disjoint composition evidence
now lives in `tests/test_workflow_lisp_union_input_composition.py`.

Implementation review exposed three required shared-owner corrections beyond
the initial selector: explicit-source-only reference rewriting/discovery,
lossless terminal refs for imported private returns, and active JSON-pointer
ownership in both output validators. Astra reviewed their design implications.
The private return correction is target-gated; the output-validator correction
fixes existing declared semantics without adding a version flag. No extension
to the pure evaluator or root workflow-input admission is selected by A.

Regression baseline note: a clean detached checkout of `5e4e761a` passed
`test_ordinary_repeat_core_executable_and_runtime_plan_bytes_remain_frozen` but
failed `test_procedure_identity_modes_match_frozen_wcc_m4_observables`. Preserve
that distinction when reporting the broader suite; do not regenerate frozen
expectations to hide a new regression. The implementation's loop snapshot delta
was traced to a restore binding-descriptor digest and remains a repair obligation
until freshly verified.

Task 1 implementation, spec review, and separate code-quality review are
complete. Fresh coordinator check: the seven compiled/runtime
composition cases, frozen old-loop bytes, and lowering-owner control all passed
(nine checks). The loop descriptor regression is fixed. Broader owner regression:
863 passed, with only the baseline procedure-identity failure above remaining.
The quality reviewer also passed 396 changed-owner checks. These checks do not
close Task 2's public CLI/resume delivery obligations.

- [x] Add `test_union_prompt_inputs_preserve_active_payload`, parametrized over
  ordinary `:inputs` and prompt `:value` fills, a payload-bearing variant and an
  empty alternative. Add old-target controls and a literal payload key `ref`.
  Assert the typed binding and canonical JSON data, not prompt prose.
- [x] Run `python -m pytest -q tests/test_workflow_lisp_typed_prompt_inputs.py
  -k union_prompt`; expected RED is unsupported rendering or incorrect whole-value
  lowering, not a missing fixture or unrelated validation error.
- [x] Resolve the version decision above. Trace every call to
  `select_prompt_fragment_renderer`, including refinement/fill validation in
  `prompts.py` and ordinary input selection in `lowering/phase_scope.py`.
  Gate union admission consistently; do not broaden the unversioned selector
  while its consumers still disagree.
- [x] Preserve a reference to the validated whole union. Where an existing
  flattened boundary must reconstruct it, select the discriminant before resolving
  payload fields. Reuse existing normalization and canonical JSON; no alternate
  renderer, unconditional all-variant mapping, or producer-written bridge file.
- [x] Extend the fixture to nested records, `List[union]`, imported/private
  returns, missing active data, and malformed tags. Keep source field-access
  proof rules unchanged. Run the selector again and the existing rendering
  controls; expected GREEN is correct active data with no inactive-field reads.

### Task 2: Prove Delivery And Resume, Then Remove One Workaround

**Create:** `tests/test_workflow_lisp_union_prompt_inputs_e2e.py`.
**Reuse:** public compiler/`WorkflowExecutor` fixture patterns in
`tests/test_workflow_lisp_typed_prompt_inputs.py` and
`tests/test_workflow_lisp_prompt_calculus_e2e.py`.
**Inspect/modify only if needed:** `orchestrator/workflow/executor.py` typed-input
resolution and `orchestrator/workflow/prompting.py` composition.

The public resume test exposed two additional shared owners:
`workflow_lisp/wcc/defunctionalize.py` must not capture a lossy flattened union
as a whole-value restore binding, and `workflow/pure_result_replay.py` must
recognize declared variant-output member addresses during consumer dependency
discovery. Astra reviewed the minimum correction: omit only the redundant
metadata-bearing whole-union binding while retaining proofs; separate declared
address membership from exact typed pure replay contracts. No checkpoint schema
or new replay evaluator is required. Include scalar/record field overlap and
empty alternatives in the resumed path, and check the actual restore payload.

Task 2 passed independent specification and code-quality review. Fresh
coordinator verification: all nine public delivery/resume cases plus the frozen
old-target loop control passed; the implementation owner passed 173 broader
checks. The full suite passed 15,644 tests with 36 skips and 375 failures. Clean
base `5e4e761a` reproduces 270 of those failures; all other 105 arose from the
chosen temporary path (55 research preflight token false positives, 48 Unix
socket path-length failures, and two dependent coordinator failures). Rerunning
all three affected modules under a short neutral path passed 402 tests. No
feature-attributable failure remained in that comparison, but the repository's
full suite is not globally green. Logs are local execution evidence under
`/home/ollie/.cache/orc-union-full-WdkEGx/` and
`/home/ollie/u2qpa/affected-modules.log`, not runtime dependencies.

- [x] Add `test_public_union_prompt_flow_resumes`: fixture provider A writes a
  runtime-selected union result through its real output contract; B consumes it;
  interrupt after B's real committed checkpoint, then ordinary resume delivers
  the union to a later consumer without repeating A or B. The initial failed-once
  boundary wording was incompatible with the existing default fail-closed policy
  for failed effects; use the established post-commit interruption pattern, not
  force-restart or a recovery-policy change to manufacture the reuse proof.
- [x] Capture B's actual invocation input and typed rendering evidence. Check
  one binding/value/block, exact active data, unchanged current output contract,
  phase fallback, and no invocation for malformed input. Do not patch out the
  composition or validation logic under test.
- [x] Run `python -m pytest -q
  tests/test_workflow_lisp_union_prompt_inputs_e2e.py`; expected PASS across clean
  and resumed paths. Include a public CLI run/resume case using deterministic
  provider transport, not only direct executor construction.
- [x] Replace one demonstrated match-and-repackage workaround in a maintained
  consumer, if one exists; otherwise keep a minimal `.orc` regression example
  in this test's fixtures. Do not rewrite the whole progressive-execution demo
  or invent a production consumer to claim adoption.
  Read-only scan of maintained workflows, templates and prompt libraries found
  no such workaround; existing matches express business/control decisions.
  The dedicated nine-case E2E module supplies the minimal source regression.
- [x] Complete the per-package closeout below. A is shippable without B–E.

## B. Rich Loop State And Complete Exits

Selected target: **2.29**, confirmed free after A selected 2.28. Tasks 3–4 are
complete in the development worktree. Preparation history below records the
failures that motivated the shared corrections, not current availability.

Preparation added five `rich_list` selectors in the three Task-3 test modules:
four intentionally fail at current admission/API boundaries, while one preserves
the target-2.28 refusal. Root/nested record lists expose missing descriptor
environment carriage; a defining-environment union probe names the proposed
shared API. These are RED preparation, not implementation evidence. Authored
`List[union]` workflow inputs have an earlier boundary refusal; prove actual
union-list loops from a supported producer path and state the public-input limit
explicitly, rather than treating a helper-only check as complete public support.

### Task 3: Carry Complete Descriptors Through Admission And Lowering

**Modify:** `orchestrator/workflow_lisp/loops.py`,
`orchestrator/workflow_lisp/typecheck_loop_recur.py`,
`orchestrator/workflow_lisp/loop_state.py`, and
`orchestrator/workflow_lisp/lowering/control_loops.py`.
**Shared descriptor owners:** `orchestrator/workflow_lisp/contracts.py`,
`orchestrator/contracts/output_contract.py`.
Review additionally identified `workflow_lisp/workflows.py` return-catalog
analysis and imported workflow boundary matching as complete-return owners.
At 2.29 use recursive return-contract validation there, not a loop-specific
exception; input admission remains unchanged. Astra approved this shared-owner
correction after tracing the actual early refusal (a contracts flag alone is
insufficient). The compiler must also admit literals inside recursive exhaustion
packaging. Further review found accidental old-target admission of rich lists
inside records and incomplete activity handling for nested unions with disjoint
fields. Preserve historical projection environment behavior below 2.29. Astra
reviewed reusing/generalizing the existing union-output metadata owner, shared
value traversal, and discriminant-aware normalization; no separate loop walker
or inactive-field guessing. Task 3 remains under correction/review until these
regressions and strict active-field validation pass. The reviewed contract is
recorded in Increment 2.
The first public runtime smoke passed exhaustion but failed normal `done` for
an outer record containing disjoint union variants: pure projection validated
an inactive list field. Astra approved retaining computed evaluation, adding
shared activity and source-path bundle pointers to ordinary pure projections,
then adapting sparse results to total internal frames through discriminant control.
This applies to seed/continue/done and fresh/reused bundles, not just literals.
Coordinate C's `lowering/pure_projection.py` ownership with B's runtime consumers
in `workflow/executor.py`, `workflow/steps/pure_projection.py`, and
`workflow/steps/runtime.py`. No schema-3 dependency or new evaluator is required.
A subsequent Astra review approved reusing the compiler-owned nested-`if` lane
by letting the existing repeat ownership map contain exact new-target repeat
IDs with empty metadata. Ordinary/WCC capture computes that map once; nested-if
capture consumes membership, not a diagnostic-key test. Shared validation still
requires exact emitted repeats and matching metadata, and grants no ownership
from the frontend name alone. Add no runtime or serialized ownership field.
See Increment 2 for the complete contract and negative controls.
The next counterexample exposed a shared proof representation gap: one producer
can own two independent union groups, while existing proof keys retain only its
name. Astra approved the 2.29 `{ref, allowed}` guard alternative and exact scoped
producer/discriminant proof identity in Increment 2. This supersedes the earlier
assumption that legacy guards alone suffice. Extend the existing normalization,
proof context, scoped-reference binding and runtime guard owners in
`workflow/validation.py`, `elaboration.py`, `lowering.py`, and `executor.py`;
carry the common guard through shared views without a new opcode or proof store.
Use sibling activity-set conditionals at one additional level, not recursive
else chains. Update normative DSL/IO/versioning contracts as a pending target
obligation until the implementation and compatibility evidence pass.
The direct and loop-shaped two-independent-union examples then exposed a
shared return-lowering gap. Astra approved routing new-target structural returns
requiring materialization through the existing pure-projection owner from
`lowering/values.py`, with concrete boundary fields/source paths and sparse
activity handling. Keep only complete direct-ref shortcuts; no generated-name
splitting or caller-specific walker. Test literal/local/mixed/repeated-name
returns, `__` field names and collisions, and an imported specialized sibling.
The simpler one-group example completes via public CLI on both done/exhaustion
paths; that is not proof of two-group composition or Task 4 resume.
The imported provider-fed multi-iteration fixture exposed missing ancestor
visibility in nested branches. Astra reviewed ordered, owner-preserving lexical
forwarding at the existing validation and executable-binding owners; Increment 2
and the 2.29 scope contract record the decision. Preserve defining catalog/node
identity and nearest-producer shadowing, including restrictions and union proofs.
Do not add ref allowances or materialized forwarding steps. The fixture remains
an acceptance RED until real done/exhaustion and committed-resume execution pass;
a build-only test does not prove committed iterations.
Shared catalog owner tests also reproduced dropped explicit materialization
projection metadata. Reusing the existing normalizer fixes that RED; both new
catalog tests pass. Scoped proof/runtime and old-target controls remain required.
**Tests:** extend `tests/test_workflow_lisp_loop_recur.py`,
`tests/test_workflow_lisp_loop_state.py`, and
`tests/test_workflow_lisp_lowering.py`.

Preparation: Astra reviewed the existing projection/checkpoint owners. Use the
existing `state_value` map with `""` for exact root `state`; keep record keys.
Gate root capture/comparison/overlay and corrected exhaustion/result mappings
at B's selected target using existing workflow-version metadata. Older targets
can have empty root projection maps and must retain their existing restore
behavior. Do not confuse whole state with final outputs. The owning design's
Increment 2 records these accepted rules; Task 4 now records their runtime proof.

- [x] Add `rich_list` cases for root `List[record]`/`List[union]` state and the
  same list inside a state record. Use a defined record/union requiring the
  owning type environment, not just scalar aliases. Lock old-target refusals.
- [x] Run `python -m pytest -q tests/test_workflow_lisp_loop_recur.py
  tests/test_workflow_lisp_loop_state.py -k rich_list`; confirm intended RED.
- [x] Thread the actual target/type environment through
  `ensure_loop_projectable_type`, `project_loop_value`,
  `build_loop_lowering_plan`, their callers, and final-result normalization.
  Keep generic checks deferred only until real specialization. Use existing
  whole-list descriptors, retaining nested tags/fields and existing limits.
- [x] Extend exhaustion construction to direct state values and recursive
  record/variant packaging, including renamed fields and existing scalar
  literals. Reuse the existing updated-`continue` result construction/final-frame
  publication. For the new target, remove same-variant state substitution on
  normal `done`; preserve actual result payloads. Add no exhaustion evaluator and no
  index-specific flattening. Arbitrary computed/effectful exhaustion expressions
  and top-level Optional/Map state remain explicit follow-ons.
- [x] Add `rich_list` lowering cases that inspect complete generated input,
  frame, output, and exhaustion descriptors. Run `python -m pytest -q
  tests/test_workflow_lisp_lowering.py -k rich_list`; require GREEN before claiming
  admission. Typechecking alone is insufficient.
- [x] Cover record → union → record with disjoint variant fields, dynamic state
  refs and two independent nested unions. Retain active metadata through shared
  projection/materialization and final normalization; never dereference a proven
  inactive field. Include inactive required relpath success versus active missing
  relpath failure, with runtime evidence in Task 4. Keep whole structured
  collection descriptors and existing projection-collision diagnostics intact.
- [x] Preserve computed record and `record-update` carriage through every pure
  seed/state/result path. Generate bundle pointers from source paths, share
  activity-aware extraction on fresh/reused bundles, and adapt sparse outputs
  to total loop frames using discriminant control. Test independent union groups
  without multiplying cases and retain whole-root/old-target controls.
- [x] Cover deeper generated totalization conditionals in ordinary no-diagnostic
  loops through both lowering routes. Validate exact repeat/if ownership, empty
  metadata only at the new target, invalid/missing/duplicate IDs and metadata,
  wrong frontend and prior-target rejection. Do not widen nested-match admission.
- [x] Repair exact scoped discriminant proof and runtime checking through shared
  owners. Test two groups on one producer (including equal tag spellings),
  same-named producers in different scopes, partially shared fields, three or
  more variants, malformed/mixed guards, inaccessible refs, ambiguous legacy
  guards, contradictory proofs, and wrong-group reads. Preserve <=2.28 behavior;
  prove current-iteration and restored/replayed guard resolution in Task 4.

### Task 4: Prove Latest-State Exhaustion And Nested Resume

Complete. Astra accepted the expanded public run/resume evidence and requested
one final runtime correction: a new-target legacy guard must not infer an
undeclared discriminant from a conventional artifact name. The coordinator
reproduced and fixed it with a 2.28 compatibility control; the two B E2E/proof
modules then collected and passed **31 tests**. Terra's preceding broad owner
sweep passed **496 tests**. These prove provider-fed root lists and record-held
lists, imported updates, distinct done/exhaustion data, malformed union rejection,
failed-iteration behavior and two independent union groups across committed
resume without repeating seed work.

Limit: default resume of a pure-only loop with no prior semantic boundary still
rejects with `lexical_default_resume_prior_boundary_missing`. This package does
not relax that existing resume policy or add a checkpoint just for the test.
The resume evidence uses actual provider-produced state and committed boundaries.
No production caller was rewritten for this delivery; the regression programs
are its concrete consumers, not an adoption claim.

**Create:** `tests/test_workflow_lisp_rich_loop_values_e2e.py`.
**Inspect/modify if the test exposes a gap:** `orchestrator/workflow/loops.py`,
`orchestrator/workflow_lisp/lexical_checkpoint_restore.py`, and the loop-value
overlay in `orchestrator/workflow/executor.py`. Inspection already established
that exact root `state` is omitted by current snapshot/comparison paths.
The nested-union review additionally requires final `materialize_artifacts`
normalization to consume carried activity metadata through existing structured
output helpers before resolving/validating inactive fields. The current executor
has the bounded materializer consumer and its active/inactive relpath check;
ordinary pure projections and their sparse-to-total frame boundary remain under
correction. Keep internal loop projections total and authored active contracts
strict; metadata-only compiler checks are not runtime proof.
**Existing controls:** `tests/test_workflow_loops_exhaustion_state.py`,
`tests/test_workflow_lisp_imported_stdlib_loop_exhaustion_post_loop_terminal.py`,
`tests/test_workflow_lisp_nested_transportable_value.py`.

- [x] Add `test_public_rich_loop_exits_and_resumes`: a fixture provider supplies
  rich tasks at runtime; an imported procedure changes remaining tasks for two
  iterations; exercise both `done` and explicit exhaustion and compare clean
  versus interrupted/resumed execution. Parameterize root/record-contained lists.
- [x] Include empty/singleton lists, variant changes, `record-update`, malformed
  nested data, and a failed iteration distinct from exhaustion. Expected values
  are the latest successfully committed list, never the iteration-entry copy.
- [x] Cover renamed/nested exhaustion packaging and normal `done` using the
  exhaustion variant with different payload data. Reject a new-target root-state
  snapshot mismatch, including empty lists; preserve an old-target empty root
  projection snapshot as a restore compatibility control.
- [x] Run `python -m pytest -q
  tests/test_workflow_lisp_rich_loop_values_e2e.py`. Inspect root `state` versus
  `state__*` snapshot selection in both runtime and lexical restore; repair the
  existing owner if the fixture fails, rather than introducing a rich-list-only
  state path. Confirm no replay of completed provider work.
- [x] Add public CLI compile/run/resume coverage to the new module, reusing its
  deterministic transport. Run the existing branched exhaustion controls and
  malformed nested-contract controls; do not replace them with new-only cases.
- [x] Remove displaced serialization/state-copying in a real selected caller
  where available, then complete the per-package closeout. B does not need A.

## C. Pure Helper Expression Composition (EC-1)

### Task 5: Resolve Phase Placement And Once-Only Representation

Selected target: **2.30**, following B's 2.29. Tasks 5–6 are complete and its
catalog gate is admitted in the development worktree. Preparation probes used
the prior target to expose actual
composition failures rather than an unsupported-version error; Task 6 switches
new-admission tests to 2.30 when its gate lands and retains old-target controls.

This is a bounded implementation-preparation task, not authorization to relax
purity guards. The EC-1 design requires its result before implementation.

Read-only tracing selected pre-typecheck function expansion into the existing
procedure effect fixed point, followed by final resolved-call normalization and
strict rechecking. It also established that existing pure-projection `let*`
substitution cannot preserve once-only arguments. The owning design now specifies
a schema-3 ordered lexical `let` and hygienic argument temporaries. Independent Terra design
review accepted the selected ordering after adding final strict-Boolean
normalization and recognized procedure-expansion provenance. Subsequent Astra
review required provisional container deferral across procedure/workflow
inference and specialization discovery from uncalled function bodies; the owning
design now includes both and Astra re-review accepted the amended contract.
Ten runnable preparation fixtures now live under
`tests/fixtures/workflow_lisp/pure_call_composition_preparation/`. At target 2.27,
early and uncalled `defun` procedure calls fail `pure_function_has_effect`;
aggregate/map and procedure-argument probes fail `effect_not_permitted`.
Existing `defun` controls compile but expose actual evaluation bugs: with caller
`x = 9`, the aggregate returns `(18, 9, 2)` instead of `(20, 9, 9)`, and an unused
fallible argument is suppressed. Astra review confirmed that a separate bare
value-`and` map probe characterizes existing eager non-condition behavior, not a
strict-Boolean normalization defect. Condition-position controls and calls whose
expanded procedure bodies introduce Boolean structure must independently prove
skipped-work preservation. The coordinator independently reproduced the
incorrect aggregate result through the public run command. These are diagnostic
probes, not passing semantic controls or EC-1 implementation evidence. The
corrected `defun` condition controls produce `[false]` / `[true]` on a fallible
skipped path and `[]` on empty input. Procedure-body Boolean counterparts still
reject with `list_map_body_effect_forbidden`; they introduce the Boolean form
only after procedure expansion and must become runtime controls in Task 6.
Task 5 preparation is complete: `test_workflow_lisp_pure_call_composition.py`
exercises all ten fixtures at the admitted 2.29 target plus imported/nested
rejection and independently correct explicit bindings. Coordinator verification
collected and passed all eleven characterization checks. Those passes establish
the current refusals/bugs and working controls, not EC-1 implementation. Task 6
must replace new-target refusal expectations with successful semantic assertions
while preserving old-target characterization and adding once-only instrumentation.

**Read/trace:** `orchestrator/workflow_lisp/compiler.py`,
`orchestrator/workflow_lisp/functions.py`,
`orchestrator/workflow_lisp/procedure_typecheck.py`,
`orchestrator/workflow_lisp/procedure_specialization.py`,
`orchestrator/workflow_lisp/typecheck_dispatch.py`,
`orchestrator/workflow_lisp/typecheck_structural_values.py`,
`orchestrator/workflow_lisp/wcc/elaborate.py`,
`orchestrator/workflow_lisp/wcc/anf.py`, and
`orchestrator/workflow/pure_expr.py`.
**Update:** `docs/design/workflow_lisp_pure_call_composition.md` and this plan's C
tasks with the resolved owner/representation.
**Create:** `tests/test_workflow_lisp_pure_call_composition.py`.

- [x] Add failing constant and dynamic-argument examples in a record/list, map,
  and `defun`, with independently verified explicit-binding controls. Existing
  `defun` expansion is not a trusted dynamic-argument reference; use the
  preparation probes to distinguish its bugs from the proposed call admission. Run
  `python -m pytest -q tests/test_workflow_lisp_pure_call_composition.py` and
  distinguish source rejection from payload representation failure.
- [x] Map resolution, specialization, final effect inference, early
  `_validate_pure_function_expr`, typed normalization, and WCC ordering.
  Trace both single-module and linked/imported-module compilation.
  `functions.py` currently rejects a procedure before later normalization can
  help. Start from `normalize_function_calls` and its cloning/binding machinery;
  identify one shared resolved-call conversion that all consumers can use.
- [x] Demonstrate once-only arguments, including a formal used twice and an
  unused formal whose argument can fail. Keep calls inside selected branches
  and per-element map scope. Inspect whether existing pure payloads can bind
  arguments locally; WCC sequencing outside a map is not a substitute.
- [x] Record the exact normalization insertion point, payload/WCC change if
  necessary, source attribution, and target policy in EC-1. Review that decision
  before Task 6. If a representation extension is needed, amend its owner and
  the task list; do not silently ship only the constant case as full EC-1.

### Task 6: Implement The Reviewed Normalization And Prove Composition

In progress: the runtime-owned schema-3 lexical `let` slice is implemented in
`workflow/pure_expr.py` and passed independent spec and quality review after
correcting once-only instrumentation and a stale unknown-schema test. The
combined pure-expression/list-traversal owner suite passes 336 checks. Redundant
static validation was removed; the existing complete static type pass remains
authoritative. The initial compiler slice now admits 2.30, expands selected
helpers with hygienic bindings and emits schema-3 payloads. Nineteen focused
tests pass, covering retained old-target characterizations, direct/nested/map
use, capture and eager arguments, skipped Boolean work, uncalled generic
specialization and imported entry execution. The coordinator independently passed
those tests plus two loop/materializer controls (21 checks). A 304-pass historical
owner selector retains the independently established frozen procedure-identity
baseline failure; it is not newly attributed to C. A later strict-recheck slice
passed 204 focused checks and 416 broader owner checks with the same baseline
failure. A selected-hook probe then exposed normalization losing the selected
body's hook context, not a missing environment in the retyping owner. Astra
review requires shared exact specialization selection and normalization under
the callee's bindings before transplantation; full strict retyping stays in
both compiler paths, including generic bases. That correction, representation
diagnostics, hook/negative coverage and public committed-boundary resume remain
pending. This is a bounded milestone, not completed EC-1 support
or package closure.

The next slice passed 27 focused tests and 424 owner checks (the same frozen
identity baseline failure remains). Coordinator checks confirmed exact multi-hook
selection, bound residual arguments, separate private/effect diagnostics and a
real public post-commit interruption/resume without state fabrication. Final
Astra review nevertheless requires corrections before closure: preserve complete
arguments on non-inline fallback; never expand unresolved hook templates; apply
settled purity/representation validation to uncalled functions too; provisionally
admit calls inside function aggregates before strict validation; and diagnose
unsupported pure bodies instead of raising a cloning `TypeError`. Add executable
counterexamples and compiled once-only/eager-unused argument checks. Passing
scalar output controls and the schema-3 evaluator unit suite alone do not prove
that the compiler emits the required evaluation behavior.

Those five findings now have executable corrections: 36 focused checks and
585 owner checks pass, with the same independently verified baseline identity
failure. Astra's next review found the WCC terminal-suffix reconstruction still
loses eager arguments before effects/control, merges legal shadowed bindings,
and drops binding/call attribution. Replace that workaround at the existing
binding/projection owner for both functions and procedures; do not add another
terminal special case. Require actual evaluation counts and a pure call before
the committed interruption in public resume coverage. The shared binding-owner
correction passes 44 focused tests and 593 owner controls, with the known frozen
identity baseline failure. Coordinator reran the 44 tests with D's 14 type tests
(58 passed). Astra's recheck still finds structured actuals containing mixed
deferred fields and direct refs or nested literal records failing projection.
Correct those representations at the shared conversion owner; the exact single
computed-field regression alone was insufficient. Task 6 remained open at that
intermediate checkpoint; the following closeout supersedes it.

**Final closeout supersedes the intermediate open findings above.** All 48 focused
checks pass. Mixed direct/deferred fields, nested literal records and legal
`Box.ref` fields now use the shared declared-field-aware conversion. The old-target
phase-resource control exercises that conversion, matches canonical executable
IR from clean `5e4e761a`, and fails when the former unconditional record
classification is restored. Astra independently verified those facts and approved
the bounded target-2.30 implementation, without requesting more normalization
machinery. Coordinator compiler/restore/semantic/lowering checks pass; the
separate concurrent D prompt regression does not invalidate C. The historical
procedure-identity baseline mismatch remains separately documented.

The real-caller scan found no justified redundant production helper to remove;
none was rewritten merely to manufacture adoption. The committed-interruption
integration verifies public compile/run/resume and once-only evaluation, not
superior reuse ergonomics, whole-task quality or research utility. Those claims
remain for the separate unselected EC-1 study.

**Modify:** only the shared resolution/typechecking/normalization owners chosen
in Task 5, including the affected callers above. Do not add per-container
normalizers or a runtime procedure interpreter.
**Extend:** `tests/test_workflow_lisp_pure_call_composition.py`.
**Public integration:** the compile/run/resume control is colocated in
`tests/test_workflow_lisp_pure_call_composition.py`; a separate e2e module is not
required.
**Existing controls:** `tests/test_workflow_lisp_functions.py`,
`tests/test_workflow_lisp_procedures.py`,
`tests/test_workflow_lisp_list_traversal.py`,
`tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py`.

- [x] Implement the reviewed conversion for resolved effect-free inline calls,
  preserving defining-module lookup, generic/hook specialization, types, source
  order, branch proof, and exactly-once evaluation. Keep current effect syntax.
- [x] Test imported/nested helpers and eligible resolved hooks in direct,
  record/union, list, map, and `defun` positions. Use runtime arguments and
  instrumented evaluator checks/error cases for duplication, suppression, and
  eager skipped work, including empty maps and Boolean short circuit;
  successful scalar equality alone is not enough.
- [x] Preserve selected-hook context through normalization. Cover generic and
  nonparametric wrappers, nested selection, defining-module name collisions,
  uncalled generic bases, and pure versus effectful selections. Reuse settled
  specialization rows; never infer selected purity from a template, skip generic
  retyping, or resolve a local hook against a caller/global name.
- [x] Test separate diagnostics for real effects and unrepresentable/private
  frames. `auto` lowering is eligible only after its actual lowering is chosen;
  never silently erase an explicit private boundary or a cycle restriction.
- [x] Run `python -m pytest -q
  tests/test_workflow_lisp_pure_call_composition.py`. The integration control must execute
  public compile/run/resume with dynamic input around a committed provider
  boundary, checking values, call provenance, and no repeated completed work.
- [x] Delete displaced duplicate helpers/manual prebindings in a real caller
  where possible. Complete closeout independently of optional effects or PC-1.

## D. Portable Context (PC-1 Ordinary-Call Slice)

### Task 7: Settle The Adapter, Event, And Publication Contract

Preparation: Astra reviewed materialized inline portable context, one spellable
structural `Contextual[T]` constructor, and atomic typed `result`/`context`
artifacts. The owning design records the closed schema, existing limits,
wrapper-only inference/canonical specialization fixes, shared structural-ref
projection correction, and Codex JSONL codec scope. A real two-call Codex/Terra
probe captured a command/result relationship and bound that structured history
to a fresh call; it does not yet prove typed/public `.orc` capture. Target 2.31
is selected but not admitted. Astra re-review accepted the corrected schema and
the optional `provider_context` map/propagation owners. Task 7 preparation is
complete; Task 8 starts with failing contract tests. No native or second-provider
support is claimed.

**Read:** `orchestrator/providers/types.py`,
`orchestrator/providers/executor.py`, `orchestrator/providers/omp_session.py`,
`orchestrator/providers/omp_templates.py`, `orchestrator/prompt_session.py`,
`orchestrator/workflow_lisp/lowering/effects.py`, and
`orchestrator/workflow/executor.py`.
**Update:** `docs/design/workflow_lisp_provider_context_values.md`; reconcile
`docs/design/workflow_lisp_provider_prompt_queue.md` without implementing it.
**Existing tests to reuse:** `tests/test_provider_omp_session.py` and
`tests/test_workflow_lisp_session_artifact.py`.

- [x] Inventory actual exposed conversation capture and destination import for
  a named installed adapter. A scalar session handle, content-free prompt digest,
  or user-only prompt extraction is not capture. Check a settled conversation,
  including tool-call/result relationships, through its adapter-owned codec.
- [x] Specify the first portable event/coverage schema, authored construction,
  immutable storage/reference representation, structural wrapper type, binding
  projection, unsupported-content behavior, and exact ownership of loading.
  Keep the current task/tools/output contract distinct from historical material.
  Specify reference lifetime and how the existing program/input/value identity
  owners include context selection, representation, transformations, and content.
  No new identity registry; serialization alone does not make run-local content
  available after deletion or on another host.
- [x] Demonstrate real capture and a real destination bind on a small ordinary
  call before claiming adapter support. This is an adapter check within the
  implementation's provider scope, not a research study or
  reason to use tool-less author agents. Drafting this plan launches no call.
  If live execution is unavailable, record that missing evidence and continue
  independent work; do not claim adapter support from mocks alone.
- [x] Resolve atomic result/context publication, retry after capture failure,
  completed-boundary reuse, current `:session-artifact` incompatibility, and the
  exact parser/type/WCC/executable fields. Capture stays off by default. Native,
  phased, peer, supervised, and adjudicated capture are not implicitly admitted.
- [x] Amend PC-1 and the D task file map with the concrete schema/adapter design
  and review it before Task 8. A missing provider capability, missing adapter,
  and language transport gap have different next actions; do not conflate them.

### Task 8: Deliver One Ordinary Call's Runtime-Owned Result/Context Pair

Bounded codec/value leaf: `providers/portable_context.py` now owns the fixed
ordinary descriptor and semantic event/coverage/lineage validation. The opt-in
settled decoder in `providers/session_transport.py` preserves task/assistant/
command history and source JSONL positions, explicitly omits reasoning and
rejects unsupported or inconsistent event lifecycles. Default session decoding
is unchanged. Preserved real Codex dummy traces decode successfully; no new live
call was needed. The implementer passed 105 focused checks and 3,442 broader
provider checks with eight skips. Coordinator review additionally caught and
fixed Unicode separators being treated as JSONL record boundaries (three RED
then GREEN checks). This leaf is not capture publication, frontend exposure,
inherited-history assembly or completed Task 8; target 2.31 stays unadmitted.

The bounded in-memory provider-map carriage has three passing direct tests;
it does not establish validated executable support. Astra reviewed the necessary
closed persisted graph v5 extension: select it iff reachable context is present,
deep-freeze decoding, preserve v1-v4 absent bytes, and retain Q2/Q3/Q5/trial
carriage and admission. Implement in `persisted_surface.py` through shared
configuration validation; test nested/finalization/reachable-import placement,
unused imports, mixed feature graphs, malformed maps/schema mismatch, and
dashboard/observability acceptance. Keep executable validation and public
compiler/runtime delivery separate; the owning context design records the exact
contract and reader compatibility cost.

The configuration/persistence leaf now has 31 passing direct checks, including
all three maps, deep freeze, nested/finalization/import decode and a v5 graph
mixing Q2/Q3/Q5/trial carriage. Coordinator rerun plus corrected unsupported-target
controls passed 33. An obsolete trial test assumed newly admitted 2.30 was still
unsupported; it now uses an explicitly unsupported sentinel, without weakening
the separate parent/arm target-matching check. This is not a baseline failure.
Coordinator also reproduced ordinary `__`-prefixed record fields being dropped
by pure binding conversion; exact compiler-metadata filtering passes the new
public compile/run regression and six projection controls. Whole structural refs,
private-return path collisions and the public context surface remain outstanding.

The type foundation passed Astra re-review and 14 independent tests after fixing
imported wrapper identity and malformed comma arguments. Terra's bounded frontend
slice now carries `:context` / `:capture-context :portable` through expression,
type/effect, WCC and provider lowering; 281 focused frontend/type/provider controls
pass in its run. Model T and expression Contextual[T] remain distinct. Shared
binding now replaces executable `input.ref` with an ordinary bound address while
preserving source/persisted strings; its initial source-authority/mutation tests
pass. Astra reviewed the required independent semantic lowering check, complete
recursive reference schemas and shared fixed capture artifact contracts. Full
reference/member/type validation, descriptor agreement, runtime atomic publication,
first-class carriage and public resume evidence were still open at this leaf
checkpoint. Target 2.31 was not yet admitted; these leaves alone did not
establish executable provider-context support. Task 9 closes those obligations.

Astra approved capture-only whole-root model contracts: one mandatory
`output_bundle.__result__` at pointer `""`, with the complete schema of T and no
variant/conditional projection. The existing validator returns T directly; no
new document-return API or second file read is needed. Frontend derivation must
preserve recursive field/variant guidance and root source attribution; the shared
prompt renderer describes the full schema. Root Bool retains existing coercion;
nested structural booleans/keys are strict. Source, executable and runtime owners
use one descriptor/contract agreement check before launch. Coordinator checks for
carriage, malformed root contracts, recursive prompt rendering and collections
pass 61 tests; 103 carriage/prompt/pure-call tests collect. These are bounded
checks, not yet the public capture/bind proof.

The runtime/shared-contract slice passed Astra review: bound input resolution,
configured-adapter checks, fresh JSONL capture, inherited-history merge before
prompt sealing, combined typed-pair validation, and existing top-level/nested
atomic dataflow finalizers. Terra's runtime/prompt/executor sweep passed 169;
coordinator's compiler/restore/semantic/lowering/prompt/carriage rerun passed 631.
Subsequent runtime checks cover root Bool (including existing string coercion),
union/nested/colliding-name records, nested path constraints and combined
size/depth refusal: 23 tests pass. Binding is recorded as quoted-JSON lineage,
not native session reproduction. A deterministic `.orc` capture→bind and
imported generic wrapper execute through shared validation; full private/loop/
branch/public-resume carriage remains Task 9, so target 2.31 stays unadmitted.

Default resume proof uses a genuine interruption after the pair commits, with
pending downstream work. It does not change the existing semantics of invoking
resume on a fully completed workflow, which can restart work. No new completed-
run cache or recovery policy is introduced for context capture.

Task 9 public capture/private-helper/bind/interrupted-resume now passes, alongside
collection, branch and loop carriage. Private flattened boundaries still reject
legal names that collide (`a__b` versus nested `a.b`); provider capture preserves
them, but transparent private carriage is not claimed. Astra rechecked explicit
capture dispatch (ordinary uncaptured `Contextual[T]` keeps its normal record
projection) and one-pass schema derivation, with 14 fresh bounded controls.

The first real three-call comparison, run `20260922T203008Z-r9a9kw` under
`/tmp/context-handoff-comparison.iCRJcl`, failed capture after the agent completed
its investigation: its ordinary result write produced an unsupported
`file_change`. No continuation arm ran, so this is adapter-gap evidence, not a
handoff comparison result. Astra approved the typed terminal FILE_CHANGE
extension documented in PC-1, preserving metadata without inventing patch bytes.
Implement/review that correction and repeat the same normal-tools probe before
admitting target 2.31; do not restrict tool choice to obtain success.
The second run, `20260922T204007Z-vg5h0k`, exposed a stale completion-only comment
in the pinned schema: the actual publisher emits file-change starts as well.
The correction validates the shared lifecycle and retains terminal metadata;
neither failed probe reached a continuation arm.

The corrected real run `20260922T204631Z-u0lftt` completed all three ordinary
Codex/Terra calls with normal tools and no retries. The investigation published
10 portable events including commands and file-change metadata. Its fresh-bound
continuation published 17 events with two distinct origins, retained the seed
once, and recorded `bind-as-quoted-json` lineage; the result-only arm had its
own nine-event history. Both follow-ups correctly calculated 120 seconds and
identified the unenforced 90-second deadline. Raw JSONL and run state remain
under `/tmp/context-handoff-comparison.iCRJcl`.

This proves adapter/public runtime mechanics, not a context utility advantage:
the seed result already contained the needed answer, both agents re-read the
source files, and the result-only arm's broad search also encountered probe
logs in the shared workspace. Consequently neither quality nor token/time
differences are an isolated comparison. Keep simple result/artifact handoffs
for this case. The two failed development runs remain part of the effort
record; they are not hidden retries or successful continuation evidence.

Final D admission: Astra approved the corrected lifecycle and scoped context
materialization; coordinator reproduced the target rejection without test-only
admission, registered 2.31 in existing catalogs, then reran all nine E2E checks
successfully without an override. Normal CLI dry-run also passes. The values
module's 21 tests now use normal admission; 288 run-ref gate controls pass.
Whole-project regression results remain separately reported, not implied green.

| Adapter / representation | Implemented coverage | Limit |
| --- | --- | --- |
| Ordinary Codex 0.155.1 JSONL, portable | Supplied task, assistant text, completed command exchanges, terminal file-change metadata; inherited context and explicit lineage | Reasoning omitted; patch bytes unavailable; other item kinds reject |
| OMP / other portable adapters | Not admitted | Installed OMP version and reviewed pin differ; no transfer evidence |
| Native / phased / peers / supervised / adjudicated | Not admitted | No native checkpoint, multi-process or cross-provider fidelity claim |

**Expected existing owners:** `orchestrator/workflow_lisp/expressions.py`,
`orchestrator/workflow_lisp/type_expressions.py`,
`orchestrator/workflow_lisp/type_env.py`,
`orchestrator/workflow_lisp/procedure_typecheck.py`,
`orchestrator/workflow_lisp/procedure_specialization.py`,
`orchestrator/workflow_lisp/typecheck_effects.py`,
`orchestrator/workflow_lisp/contracts.py`,
`orchestrator/workflow_lisp/lowering/values.py`,
`orchestrator/workflow_lisp/lowering/pure_projection.py`,
`orchestrator/workflow_lisp/lowering/effects.py`,
`orchestrator/workflow_lisp/wcc/elaborate.py`,
`orchestrator/workflow_lisp/wcc/defunctionalize.py`,
`orchestrator/providers/session_transport.py`,
`orchestrator/providers/types.py`, `orchestrator/providers/executor.py`,
`orchestrator/workflow/executor.py`, and `orchestrator/state.py`.
Task 7 must name the exact WCC and codec changes and the affected shared owners
in `orchestrator/workflow/core_ast.py`, `orchestrator/workflow/surface_ast.py`,
`orchestrator/workflow/executable_ir.py`,
`orchestrator/workflow/persisted_surface.py`, and
`orchestrator/workflow/validation.py` before editing. The reviewed map also
requires `workflow/elaboration.py`, `workflow/lowering.py`, `runtime_step.py`,
`semantic_ir.py`, and existing reference/dependency discovery. Keep it off common
step configuration; compose history before final prompt identity is sealed.
Integrate publication with
the existing `StateManager.finalize_step_with_dataflow` boundary.
**Create:** `tests/test_workflow_lisp_provider_context_values.py` and
`tests/test_workflow_provider_context.py`.

- [x] Write failing tests against the reviewed schema: context consumption with
  ordinary `T` return, capture with runtime-produced `Contextual[T]`, unsupported
  adapter/content, capture disabled, and contradictory session publication.
- [x] Implement through ordinary compiler/provider/storage owners. Validate the
  model-authored `T` through the capture-only whole-root contract, capture and validate exposed history,
  then publish the pair as one successful boundary. The model never authors its
  context descriptor. Preserve tagged/direct-root results.
- [x] Prove root Bool/union/nested-record results, simultaneous `a__b` and `a.b`,
  nested path constraints, complete recursive schema/guidance and source
  attribution, schema disagreement rejection, combined pair limits, and unchanged
  uncaptured/provider-command contract bytes. Do not infer projection shape from
  `GeneratedBundleContract.result_shape`, which classifies T itself.
- [x] Inject result failure, capture failure, missing/corrupt content, and an
  interruption before commit. Assert no half-published success or hidden rerun
  to repair capture; explicit retry uses the same immutable input and normal
  at-least-once semantics. Do not claim rollback of external tool work.
- [x] Run `python -m pytest -q
  tests/test_workflow_lisp_provider_context_values.py
  tests/test_workflow_provider_context.py`; require GREEN plus unchanged-call
  controls. Treat this as an internal vertical slice, not first-class release.

### Task 9: Prove First-Class Carriage, Branching, And Useful Handoff

**Create:** `tests/test_workflow_lisp_provider_context_e2e.py`.
**Modify only as demonstrated:** existing procedure/aggregate/loop transport
owners from B/C, not a context-only global artifact bypass.

- [x] Execute an imported generic procedure returning result/context; carry its
  context through a record, supported collection and loop; perform an ordinary
  materialized-content transformation; bind the same snapshot to two consumers.
  Distinguish pure edits from storage loads and provider-assisted summaries.
- [x] Assert equal seed content, distinct branch continuations, preserved event
  relationships, explicit loss/conversion, and no sibling-history inclusion.
  Resume after a committed pair must neither call the provider nor export again.
  Changing supplied context must reject incompatible checkpoint reuse through
  the existing identity contract, not silently replace the old input.
- [x] Rebind history containing earlier instructions, tool schemas, and output
  destinations. Inspect the actual destination invocation: its current task,
  tools, result schema and bundle destination still govern, and historical tool
  events are not executed. Include unsupported content and unavailable referenced
  data; explicit conversion or rejection must occur before invocation.
- [x] Add public CLI integration and run `python -m pytest -q
  tests/test_workflow_lisp_provider_context_e2e.py`. A deterministic adapter proves
  mechanics only. Repeat capture/bind with each real adapter to be advertised;
  a different-provider claim specifically needs two real adapters.
- [x] Compare one actual continuation with a simple artifact handoff, including
  missing context, reconstruction effort, latency/tokens, and useful inspection.
  Report observations, not a fabricated reuse score. Remove replaced handoff
  packaging only where this is genuinely simpler; otherwise narrow the feature.
- [x] Complete closeout with an explicit adapter/coverage matrix. Native context
  remains separately planned, and an unsupported provider remains unsupported.

## E. One Host-Mediated Human Question

### Task 10: Resolve The Host Operation And Nested Suspension Contract

**Read:** `orchestrator/state.py`, `orchestrator/run_lock.py`,
`orchestrator/workflow/executor.py`, `orchestrator/workflow/calls.py`,
`orchestrator/workflow/loops.py`, `orchestrator/cli/commands/resume.py`, and
the WCC/shared executable owners.
**Update:** increment 5 in
`docs/design/workflow_lisp_value_and_continuation_composition.md`.

Astra reviewed the concrete preparation contract now recorded in Increment 5:
one `request-input` / `HumanReply` / `host-input` operation; one optional root
request record with latest-request idempotency; root-only suspension with
unchanged running child frames; and reuse of the existing aggregate transaction
and resume paths. Implementation must extend the shared scoped mutation owner
for atomic root/leaf changes and refresh manager plus executor projections.
Preserve enclosing call/loop visits before allocating or starting steps. No
child-frame status expansion or separate request store is needed. At this
preparation checkpoint, target 2.32 was selected but not admitted and E had not
started. Astra re-review approved the concrete question-source/union-result
leaf contract recorded in Increment 5. Tasks 11–12 below supersede that status.
The leaf review identified two concrete integration obligations, now recorded
in the design: prefix-preserving question sequencing before WCC's atomic
boundary, and fixed bundle-free reply contracts throughout durable replay/member
validation. A keyword atom or artifact-name allowlist alone is insufficient.

- [x] Select source spelling, typed answer union, one host-I/O effect, lowered
  operation, executable validation, pending/replied representation, and schema
  compatibility. Keep replies text-or-cancellation and one outstanding request
  per run. Diagnose overlap; never overwrite a pending question.
- [x] Define one runtime API for querying the pending request and submitting an
  exact-request answer/cancellation. Choose the CLI grammar as a thin client.
  Submission records data; ordinary `resume` consumes it. No provider process,
  polling workflow, event bus, approval framework, or new UI is required.
- [x] Use existing run/frame/visit identity to distinguish repeated loop
  questions. Specify atomic submission using existing writer locking and state
  transactions: same reply is idempotent, stale/conflicting replies reject,
  unanswered resume stays suspended, and original run inputs remain unchanged.
- [x] Trace nested suspension to the root. `workflow/calls.py` currently treats
  non-completed children as call failures; current SIGINT suspension does not
  establish a pending host-operation protocol. Name changes to child calls,
  loop progress, executor finalization, and checkpoint restore before coding.
  Include `orchestrator/workflow/call_frame_state.py`'s root-aggregated persistence
  so the submission lock protects the actual authoritative nested request.
- [x] Review this concrete contract and update Tasks 11–12 with exact operation,
  API, CLI, and schema owners. If the existing state substrate cannot represent
  it, revise that owner rather than inventing a file-polling side channel. Until
  then the application fallback remains `NeedsInput` plus a new invocation.

### Task 11: Implement Durable Pending/Reply And Propagate Suspension

Runtime closeout: Astra's final bounded review approved reached-scope call
validation, atomic positive-visit reply publication, and compiled downstream
failure / pre-checkpoint interruption recovery. The separate checkpoint review
approved exact node/scope/iteration/visit lookup and full fixed-reply evidence.
The runtime owner reran 198 state-carriage/runtime/public-CLI/resume controls;
the strengthened public recovery selector passed all three cases. Normal
target-2.32 admission subsequently passed four public scenarios plus the current
catalog check (five tests). All three E test modules now use the normal catalog;
their 28 tests collect without admission shims. Final compatibility verification
is recorded in the final integration evidence below.

**Expected owners:** `orchestrator/state.py`, `orchestrator/run_lock.py`,
`orchestrator/workflow/executor.py`, `orchestrator/workflow/calls.py`,
`orchestrator/workflow/loops.py`, `orchestrator/workflow/call_frame_state.py`,
the aggregate-owner helpers in `orchestrator/workflow/provider_attempts.py`,
and existing resume planning. Frontend/shared owners include
`workflow_lisp/expressions.py`, `expression_traversal.py`, `type_env.py`,
`effects.py`, typecheck dispatch/effects, WCC model/elaboration/defunctionalization,
and shared semantic/executable validation and dispatch. Add no lock or storage
service and no alternate nested-state traversal.
The concrete frontend map also includes `form_registry.py` and the builtin
type prelude; shared propagation includes surface/core/executable classes and
conversions, elaboration/lowering, persisted surface, runtime-step views, semantic
coherence and dependency discovery. Keep the single operation name
`request_input`; do not copy provider/trial bundle machinery for its fixed reply.
Include `workflow/elaboration.py`, `workflow/runtime_plan.py`, `wcc/anf.py`,
and `workflow/pure_result_replay.py` explicitly. The existing compiled-node
contract owner must expose the fixed bundle-free reply to member admission,
durable dependency type checking and retrieval. State serializers must preserve
the optional root field in both directions and omit it for unaffected runs.
**Create:** `tests/test_workflow_human_input.py`.
The exact state/API shape passed Astra review and is recorded in Increment 5.
Use `workflow/human_input.py` with record/get/submit/consume entrypoints and
existing scope/visit/loop records; no provider-attempt impersonation. Extend
`_mutate_scoped_state` with exactly-one leaf/scoped callback and root support.
Extract one non-writing result/dataflow mutation helper used by existing root,
loop and call-frame finalizers and the atomic human-input consumer. Preserve
existing guards/cursor rules. The bounded state/API leaf may precede executor
integration, but cannot claim runnable `request-input` or admit target 2.32.
Test root-only record ownership, both loop placements, idempotency after consumed
without an active old cursor, write failures before/after replacement, and
manager refresh. Full ancestor execution-position validation and detached
executor refresh remain mandatory integration work.
Historical leaf checkpoints (superseded by runtime closeout above): the
state/API slice passed 22 focused checks (independently rerun); the preceding
slice passed 173 state/call-frame/provider-allocation controls. It does not
implement the operation. Astra found wrong loop-result placement and rejected
answered-request re-entry; both have reproduced REDs and corrections. Loop
consumption now requires the existing iteration projection and compiled nested
node ID, not matching display/runtime-name spellings. Tests cover one-write
publication of result plus public/private dataflow, nested before/after-replacement
failure recovery, both loop placements and settled-request idempotency. Astra's
final leaf recheck approved these corrections. Coordinator's broad state,
compatibility and provider-allocation rerun passed 195 tests. Executor/frontend
integration and full ancestor execution-position validation were still open at
that historical leaf checkpoint; the runtime closeout above supersedes it.
Shared leaf carriage is now active. Astra approved the necessary closed graph
v6 extension: select it exactly for structurally reachable request-input,
require the map exactly on the new kind with the containing node's target gate,
preserve earlier absent-field bytes, and retain feature-specific context/trial/
Q2/Q3/Q5 checks in mixed graphs. The owning Increment 5 defines exact presence,
reachability and mismatch diagnostics. No new run-state schema or store is added.
Astra's shared-carriage review found and verified corrections for proof-checked
question references, complete durable-reply validation, conflicting result
contracts and null-carriage diagnostics. Its bounded recheck passed 18 in-memory
controls; coordinator carriage/state/context checks passed 110 before two further
Context proof controls passed. Frontend/runtime integration remains separate.
The public CLI imported-loop check now passes answer/cancel across two questions
without repeating its initial provider. It exposed and corrected missing loop
dispatch, private-return admission, suspended-run exit handling and preservation
of original launch extern arguments across repeated resume. These checks do not
close E: completed host replies still require truthful checkpoint classification.
Astra approved the bounded `reuse_validated_human_reply` amendment in Increment 5,
owned by `lexical_checkpoint_effect_policies.py`, WCC defunctionalization,
`lexical_checkpoints.py`, `lexical_checkpoint_restore.py`, and the fixed contract
in `workflow/human_input.py`. Reuse state projections for exact identity lookup;
never fabricate provider bundles or use the latest root request as history.
**Existing controls:** `tests/test_run_lock.py`, `tests/test_state_manager.py`,
`tests/test_resume_command.py`, and `tests/test_subworkflow_calls.py`.

- [x] Add failing state-transition tests for pending → answered/cancelled →
  consumed, unanswered resume, duplicate/stale/conflicting submission, and a
  second outstanding request. Include restart and competing submissions.
- [x] Implement the reviewed operation and one submission API at the shared
  owner. Persist pending state before exposing the question; persist the reply
  before reporting acceptance. Reuse writer locking and state transactions;
  extend the existing scoped mutation owner for root scope and root/leaf atomic
  writes. Commit consumption with the complete ordinary/loop leaf result and
  dataflow. Refresh live managers and active execution projections after commits
  and rollback. Inject write failures to prove there is no consumed-without-result
  window.
- [x] Propagate pending through nested calls/loops without marking them failed
  or completed. Resume consumes the recorded reply into its ordinary union
  result and does not replay completed upstream providers. Failure and user
  cancellation remain different outcomes.
- [x] Preserve question-producing prefixes before WCC's atomic boundary. Test
  literal, computed pure and effectful String questions, including `let*` and
  selected control branches. Already-completed question-producing effects must
  not repeat after restart. Test fixed-reply direct return, matching, imported
  return and downstream pure replay for both variants; empty text is valid and
  cancellation has no inactive text artifact. Reject malformed sources, runtime
  non-Strings, invalid tags, missing active text and unknown artifact refs.
- [x] Run `python -m pytest -q tests/test_workflow_human_input.py`; require GREEN
  with narrow lock/resume controls. Keep SIGINT and old-run behavior unchanged.
- [x] Implement and review the fixed durable-reply checkpoint policy; prove
  provider-free answer/cancel followed by downstream failure/resume, historical
  replies after a second request, exact nested/iteration identity, malformed
  evidence rejection, and the consumption-before-checkpoint interruption window.

### Task 12: Add The CLI Client And Prove An Imported Conversational Loop

**Modify:** `orchestrator/cli/commands/resume.py` only as required for pending
semantics, `orchestrator/cli/main.py`, and a thin input-command module using the
existing run lookup and `--state-dir` convention. Register/export that module
through the existing `cli/commands/__init__.py` path as well.
**Create:** `tests/test_workflow_lisp_human_input_e2e.py`.

The thin CLI leaf is implemented: `input get`, `input answer --text`, and
`input cancel`, with the existing `--state-dir` convention. Five real-state API
integration tests passed independently; Terra's adjacent CLI selector passed 38.
Submission does not resume execution. The completed integration now creates
questions from `.orc` and preserves nested conversational resume through normal
public admission, including downstream-failure and interrupted-consumption
recovery. The guide's complete `host_question` example also ran, accepted a
reply, and completed through real CLI processes without any provider mock.

- [x] Implement query/submit CLI calls as clients of Task 11's API, not duplicate
  state mutation paths. Submitted answers do not launch execution implicitly.
- [x] Add public compile/run/query/submit/resume tests for an imported procedure
  in a loop asking two sequential questions. Restart while pending; answer one,
  cancel another; verify per-visit identity, caller-visible cancellation,
  unchanged initial inputs, and no replay of prior provider calls.
  Assert root `suspended`, child frames `running`, and unchanged enclosing
  call/loop visits and frame IDs while waiting and after answering.
- [x] Check resume-before-answer, repeated submission, stale answer for the
  earlier iteration, and overlap diagnostics. Tests assert state/results and
  delivered question/answer data, not prose formatting.
- [x] Run `python -m pytest -q
  tests/test_workflow_lisp_human_input_e2e.py`; complete closeout. Replace manual
  question/restart glue in an actual caller only after this path works. Context
  is optional data shown with a question, not a dependency of the operation.

## Per-Package Closeout And Consequent Actions

Each package owns its own completion; do not wait for an unrelated later package.

- [x] Run new tests narrowly, collect added/renamed modules, then use the tmux
  skill for broader/slow checks. Broad pytest commands must use
  `python -m pytest -q -n 16 --dist=worksteal <relevant modules>`. Follow with the
  full suite when shared compiler/executor changes warrant it; preserve and
  investigate unrelated failures rather than weakening tests.
- [x] Run at least one public-entry smoke/integration check for the package,
  including resume where promised. Deterministic fixtures suffice for A–C and
  host mechanics; D additionally needs real capture/import evidence. Existing
  scalar/list, strict-Boolean, result-contract, prompt, and checkpoint cases are
  regression controls, not optional just because the new example passes.
- [x] Update only affected current contracts after implementation: A updates
  typed inputs/prompt rendering and consumer value flow; B loop/state/result
  projection; C EC-1 plus function/effect/WCC contracts; D PC-1 plus provider,
  IO, state and transport; E host effect, CLI, state/resume and executable forms.
  Update `specs/versioning.md`, `docs/capability_status_matrix.md`, and
  `docs/lisp_workflow_drafting_guide.md` with honest supported-target examples.
  Keep future/partial behavior marked as such.
- [ ] Inspect the actual caller diff: what manual repackaging, serialization,
  copying, duplicate helpers, handoff construction, or restart glue disappeared?
  Retain the simpler fallback if the new abstraction adds burden. No mandatory
  new report hierarchy, wrapper taxonomy, or all-five-features demo.
- [ ] Review the five axes separately through real usage: composition,
  ergonomic reuse, introspection, self-programmability, and useful program-space
  alternatives. Passing fixtures proves mechanics, not reuse quality or ORC
  superiority. Use reasoned review, optionally LLM-assisted, rather than fixed
  wording, pass-count, or contrived maintenance scores.
- [x] When a useful case remains awkward, locate the shared limitation and
  consider principled expansion or redesign of types, callable roles, effects,
  provider binding, or recursion. Do not turn the first bounded subset into a
  permanent language axiom. If the benefit does not survive reasonable revision,
  retire the unsuccessful machinery and remove its scaffolding while retaining
  independently useful fixes. Ordinary interface repairs are not experiment
  budget events.
- [x] Obtain independent review, inspect the scoped diff and fresh verification,
  and record what is implemented, still conditional, or deliberately deferred.
  No roadmap selection or study allocation changes as a side effect of closure.

### Final Integration Evidence

The normal-admission full run used
`python -m pytest -q -n 16 --dist=worksteal` with a fresh `/dev/shm` basetemp
and completed: **16,036 passed, 403 failed, 36 skipped**, in 467.51 seconds.
All 270 failures independently reproduced earlier on clean base `5e4e761a`
remain, with unchanged exception categories. The additional 133 failure IDs
are all covered by a fresh ordinary-filesystem rerun of the six affected
modules: **581 passed, 3 skipped, zero failures/errors**. Of those 133, 132
depend on provider filesystem assumptions incompatible with `/dev/shm`; the
remaining phased-provider deadline case passed on rerun. No goldens, assertions
or skip rules were relaxed to obtain those results.

Evidence: `/home/ollie/vf.OhiQxQ/final-results.xml` and `final.log`;
`/home/ollie/vc.Z9RFuU/results.xml` and `results.log`; baseline comparison
`/home/ollie/.cache/orc-union-full-WdkEGx/baseline-results.xml`. This is a full
run plus targeted environmental reruns, **not a claim of a green full suite**.
Two earlier runs exhausted ordinary disk with duplicated module-scoped
calibration fixtures; their incomplete results were not treated as final proof.
The special failed-only fixture retention option also caused five teardown
errors on both baseline and feature; the final checks use default retention.

The full run exposed a real performance regression despite functional passage:
the existing oversized-record rejection took 446.131 seconds (earlier feature
run: 156.395). Profiling traced it to new repeated whole-WCC scans for context
and host-input consumers, even on target 2.14. The owning-layer correction
precomputes exact continuation demand sets once per immutable normalized body,
instead of scanning the remaining tree for each binding. A subsequent ordinary
filesystem sweep of all Workflow Lisp modules plus adjacent shared runtime,
call/state/context/CLI checks completed: **5,852 passed, 16 failed, 1 skipped**
in 96.34 seconds. All 16 failures are in the independently verified baseline
set; none is new. The oversized compilation took **0.517 seconds** in that
report. Evidence: `/home/ollie/wc.YPJSQI/results.xml` and `results.log`.
Astra accepted the selection/scope behavior but required sharing unchanged
immutable demand sets to avoid retained copies along pure prefixes. That final
correction has a RED-to-GREEN regression checking sharing, exact operand
selection and branch locality. Astra's final recheck approved it; its 8,000-name
probe stayed near 2.2 MiB across 40/80/160 pure bindings, rather than growing
from 10.4 to 40.4 MiB. The coordinator independently ran ten focused public
context/host/imported-prompt/collector controls, all passing, then repeated the
complete compiler/runtime sweep on the final source: **5,853 passed, 16 baseline
failures, 1 skipped**, in 91.04 seconds. All 16 exact failure IDs were checked
against the independent baseline; zero are new. Final artifacts are
`/home/ollie/wc.YPJSQI/sharing-results.xml` and `sharing-results.log`.
No implementation-verification item remains open. The 23 GiB full-suite fixture
scratch was removed after retaining reports; it is reproducible test data.

Other final controls: 107 old judgment/prompt/example/context tests; 136
imported-prompt/context tests; 156 prompt contract/callback tests; frozen phased
and prompt-dependency snapshots unchanged. An imported prompt's resolved return
type is preserved rather than re-resolved in its caller's scope. The guide's
actual CLI run `20260922T212349Z-e2nyu5`, under `/dev/shm/vd.tz8UvG/state`,
completed with `ANSWERED("yes")` and the matching consumed request. This
provider-free host example used no test mocks.

Astra's separate final checkpoint, runtime, lifecycle and compatibility reviews
are in `/tmp/astra-composition-final.KVn2pg/`. Read-only review sandboxes could
not allocate pytest temporary directories for some reviews; those reports
distinguish source/in-memory probes from the coordinator's runnable evidence.
No feature source or user-owned parent changes were staged or committed.

### Practical Review And Follow-On Decisions

The delivered changes remove concrete adapters: whole unions no longer need
caller-authored matching/repackaging for prompts; rich loop state no longer
needs scalar projection helpers; resolved pure calls no longer require a
separate authored binding at every expression position. Supported portable
capture replaces manual transcript packaging, while the result-only handoff
remains a useful simpler alternative. Host input permits same-run answer/cancel
continuation instead of returning a question and relaunching a coordinator.
The progressive-execution application itself remains a draft, not a delivered
framework, and no unrelated production caller was migrated as a demonstration.
The unchecked real-caller adaptation and five-axis usage items above remain
explicit follow-on work: regression examples and the limited live context
probe do not substitute for that qualitative evaluation.

| Axis | What this implementation establishes | Consequent action, not an automatic expansion |
| --- | --- | --- |
| Composition / programmability | Ordinary typed inputs, calls, loop values, context and host replies compose through the public path. | Use them in one actual progressive-execution caller; fix a shared boundary if adapters still dominate. Do not add framework-specific forms. |
| Ergonomic reuse | Less mechanical conversion is required; private and imported helpers have concrete carriage tests. | Judge the edits and concepts needed to adapt a real caller. Tests do not prove ergonomic reuse. Keep explicit result/artifact handoffs where simpler. |
| Introspection | Context exposes captured events, origin/coverage and transformations; host requests and replies are inspectable in ordinary run state. | Extend only information genuinely missing for a debugging or comparison task. Do not add a parallel ledger; unavailable provider internals remain unavailable. |
| Self-programmability | Programs can construct/transform context and pass ordinary decisions and replies. | This is not generated executable topology or a synthesis loop. Add source generation only when an actual caller needs different control structure; reuse the existing compiler. |
| Program-space search | More useful variations in composition, context selection and continuation policy are expressible. | No search or superiority result has been demonstrated. Compare meaningful alternatives only when selected; abandon policies whose benefit does not justify their overhead. |

Current ceilings are explicit: resolved inline pure calls only, bounded loops,
supported ordinary Codex context events only, existing private flattened-field
collision rejection, and one outstanding text question per run. They are
revisable design choices. If a useful caller is blocked by types, effects,
callable roles, or bounded recursion, reconsider that underlying design rather
than declaring the use case invalid or adding another adapter layer. If a
capability remains unhelpful after reasonable revision, simplify or remove it
while retaining independently useful fixes. No search infrastructure, universal
memory, simultaneous-question service, or study allocation was added here.
