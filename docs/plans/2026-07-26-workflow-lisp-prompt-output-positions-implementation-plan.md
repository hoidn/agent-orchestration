# Workflow Lisp Prompt Output Positions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for every production change. Each task
> receives an independent specification-compliance review followed by a
> distinct implementation-quality review before commit. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Implement the accepted Q2 target-2.21 prompt output-position surface:
one `(slot :path :out [PathType])` declaration drives prompt path rendering,
one required UTF-8 file postcondition, and the existing prompt-owned structured
result without changing target-2.20 Q1 bytes or adding another result channel.

**Architecture:** Extend the prompt frontend with one normalized output-role
record and use it to derive both `compiled_prompt_fragment_identity.v2` and
`compiler_prompt_fragment_contract.v2`. The v2 carrier projects ordinary
`expected_outputs` rows and is pair-validated against those rows at every IR
boundary. Generic output-contract owners admit and render exactly one file
contract plus one structured bundle, resolve all destinations before provider
launch, and validate both into local maps before one disjoint atomic merge.

**Tech stack:** Python 3.11+, immutable dataclasses, canonical JSON and SHA-256
identity projections, Workflow Lisp targets 2.20/2.21, Surface/Core/Semantic/
Executable IR, state schema 2.1, pytest/pytest-xdist.

**Accepted design:** `docs/design/workflow_lisp_prompt_calculus.md` and
`docs/design/workflow_lisp_frontend_specification.md` at commit
`c79cee2cc0dee6eaeb86c4f96a7bb6364fa91945`, tree
`5819265e77fc2ff3447af5210589c792e4549c47`, with respective SHA-256 values
`580b260e0c197ebbb0dd5c70314777de682ce4705ca00799e9e34d7d076eedec`
and
`8a6c53a91a8bb25402c3f12c2863a89f5d527a21d1ea675d1964872ad3100b47`.
That commit records ordered `Q2_DESIGN_SPEC_REAPPROVED` then
`Q2_DESIGN_QUALITY_APPROVED`. Production work may begin only after this plan
receives ordered independent plan reviews and is committed.

**Execution status:** accepted for execution after ordered independent
`Q2_PLAN_SPEC_APPROVED` then `Q2_PLAN_QUALITY_APPROVED`.

**Deliberate cost:** Q2 implements one closed
`required_string_file` output role rather than a role registry, optional-output
algebra, or file-schema hierarchy. That makes later optional, directory, glob,
dynamic-name, or schema-rich outputs require a new reviewed language change.
The generic composition owner accepts one file-contract set plus one structured
bundle, not arbitrary contract lists; expanding that cardinality later must
revisit ordering, collision, and atomicity explicitly.

## Scope And Invariants

This plan implements only:

- additive target-2.21 `(slot :path :out [PathType])` syntax;
- target-2.20 rejection with the accepted Q2 diagnostic precedence;
- workspace-relative `relpath`, `must_exist=false` refinement and fill checks;
- one compiler-owned required `type: string` expected-output row per output
  slot, in declaration order;
- exact binding-ref/literal path-template derivation from the same normalized
  Q1 runtime binding used by the renderer;
- byte-identical Q1 v1 identity and carrier serialization at targets 2.20 and
  2.21 when no `:out` slot occurs;
- `compiled_prompt_fragment_identity.v2` and
  `compiler_prompt_fragment_contract.v2` only when at least one `:out` slot
  occurs;
- exact carrier/identity/`expected_outputs` pair validation through compiler,
  IR, persisted configuration, runtime, checkpoint, and resume boundaries;
- generic `expected_outputs` plus exactly one `output_bundle` or
  `variant_output` composition, with fixed prompt and validation order;
- pre-provider artifact-name, output-destination, bundle-destination, and
  rendered-path equality checks;
- state-atomic validation and artifact-map merge;
- the `review-design-docs` call as the first real consumer; and
- normative, authoring, capability, and active-roadmap closure.

This plan does not implement arbitrary file content schemas, optional files,
directories, globs, dynamic output names or sets, caller-side output
declarations, result-field inference, new artifact/result/snapshot/checkpoint
channels, Q3 role-separated identity diagnostics, Q4 judgments, provider
isolation, security behavior, or security tests.

The following accepted invariants are load-bearing:

1. target-2.20 source, diagnostics, canonical identity input, v1 digest, v1
   carrier JSON, runtime behavior, and resume compatibility remain unchanged;
2. `:out` occurs at most once, immediately after `:path`, and is neither a type
   nor a caller keyword;
3. one normalized slot-role record feeds identity and carrier construction;
4. one normalized Q1 value-source binding feeds both path rendering and
   expected-output path-template derivation;
5. a v2 carrier's nested rows equal provider `expected_outputs` exactly and in
   order at every boundary;
6. output contracts validate only after a successful provider process;
7. both contracts validate before either artifact map enters state;
8. all destination and name collisions fail before provider launch; and
9. tests assert contracts, identities, dataflow, and behavior, never literal
   production prompt prose.

The closed Q2 diagnostic matrix is also load-bearing:

- `prompt_output_positions_require_dsl_2_21` — primary `:out` token;
- `prompt_output_position_syntax_invalid` — primary offending token or slot;
- `prompt_output_position_kind_invalid` — primary `:out`, related kind;
- `prompt_output_position_refinement_invalid` — primary refinement, related
  `:out`;
- `prompt_output_position_fill_invalid` — primary fill, related slot;
- `prompt_output_position_contract_collision` — primary output slot, related
  structured-result field;
- `prompt_output_position_destination_collision` — both colliding fills, or
  fill plus structured-bundle/provider-application origin; and
- `prompt_output_position_contract_mismatch` — the boundary's provider
  application/source-map owner.

Every task below that can produce one of these refusals names the exact code,
primary/related owners, and its position in the accepted precedence. Existing
runtime file violations such as `invalid_output_path` and
`missing_output_file` remain unchanged and point back to the Q2 fill/slot
origins.

## Governing Authorities

Read before implementation:

- `AGENTS.md`
- `docs/index.md`
- `docs/capability_status_matrix.md`
- `docs/design/README.md`
- `docs/design/workflow_lisp_prompt_calculus.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- `docs/plans/2026-07-26-workflow-lisp-prompt-core-implementation-plan.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/providers.md`
- `specs/state.md`
- `specs/versioning.md`

If this plan conflicts with the accepted design, correct the plan and repeat
its ordered plan reviews. Do not reinterpret the accepted contract in code.

## Execution Contract

Run every command from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do not create a worktree. Preserve all user and external changes. Q2 tasks
execute in order; do not dispatch multiple Q2 implementation agents at once.
For every task:

1. dispatch a fresh implementer with the complete task text and governing
   design excerpts;
2. add the smallest behavioral or contract test first;
3. run it and confirm RED for the intended absent Q2 behavior, not a typo or
   unrelated failure;
4. implement only the selected task;
5. rerun the narrow selector GREEN, then the task's adjacent regressions;
6. run `pytest --collect-only -q` for each created or renamed test module;
7. stage exact task-owned paths or exact hunks only;
8. run `git diff --cached --check`, inspect
   `git diff --cached --name-only`, and read the complete staged diff;
9. dispatch an independent specification reviewer against the accepted Q2
   design and the exact staged diff;
10. resolve every finding and repeat specification review until approved;
11. dispatch a distinct implementation-quality reviewer only after
    specification approval;
12. if quality review causes any byte change, repeat specification review and
    then quality review on the final exact staged diff;
13. commit the exact reviewed bytes without post-review edits; and
14. record the factual commit and review tokens in this plan only during the
    final closure task.

Never use `git add .`, `git add -A`, destructive checkout/reset, or a whole-file
stage of a shared dirty path. No task may weaken tests or broaden Q2 to make a
failure disappear.

Use the `tmux` skill for the closing broad suite and any integration command
that runs longer than one minute. Wait for the configured provider/model during
reviews; do not substitute a faster model.

## Protected Working Tree

The shared tree contains unrelated owner work. At plan drafting time these Q2-
adjacent paths are already modified and are protected:

```text
orchestrator/contracts/output_contract.py
orchestrator/workflow/executor.py
orchestrator/providers/executor.py
tests/test_output_contract.py
docs/capability_status_matrix.md
docs/design/README.md
docs/index.md
```

Before the first Q2 edit to any protected or shared dirty path, capture that
path independently. Record:

- `git rev-parse HEAD` and `git rev-parse HEAD^{tree}`;
- the path's exact `git rev-parse HEAD:<path>` blob;
- the current working-file `git hash-object <path>` digest;
- its own `git diff --binary -- <path>` in a per-path `/tmp` baseline; and
- its own `git diff --stat -- <path>`.

Apply that procedure to all paths in the block above plus the then-dirty shared
roadmap, frontend design/specification, docs router/index, capability matrix,
and routing test before their first Task-7 edit. Never combine multiple
protected paths into one baseline patch. If a path is clean at capture time,
record the equal HEAD/working digests and the empty patch explicitly.

Task 5 may add exact Q2 hunks to the first, second, and fourth paths only after
the implementer reconciles against their then-current contents.
`orchestrator/providers/executor.py` is inspect-only and must not be edited,
staged, or committed. Stage Q2 hunks from protected files interactively or via
an edited patch, then verify that all pre-existing ambient hunks remain
unstaged. If an external commit lands during the task, rebase the task's
understanding on the new `HEAD`, rerun RED/GREEN, and repeat both reviews; do
not overwrite or silently absorb the external change.

All `orchestrator/providers/isolation_*`,
`orchestrator/workflow/provider_isolation_*`, security/safety/secrets files,
their tests, experiment-control work, and unrelated documentation are outside
this plan. Do not inspect them as implementation authorities, modify them,
stage them, or include them in verification.

## Disjoint Ownership From L1

Q2 owns prompt declarations, fragment identity/carriage, generic output
contract composition, the review-design-docs consumer, and the Q2 tests named
below.

L1 owns compiler-authored symbol projection, language-server navigation and
completion, LSP presentation, and `orchestrator/lsp/**` plus LSP tests. Q2 must
not edit those paths. L1 must not edit Q2 compiler/runtime/test paths while a
Q2 task is active.

`orchestrator/workflow_lisp/syntax.py` is shared. L1 Task 1 runs first and
commits only its `ModuleDirective.name_span` carrier hunk. Q2 Task 1 may begin
only after that commit, must reconcile against it, and owns only the separate
target/version and prompt-slot syntax hunks. The two tasks never edit or stage
that file concurrently.

`tests/test_workflow_lisp_build_artifacts.py` is also shared. L1 Task 1 first
commits only its explicit `frontend_ast.json` module-name-span contract hunk.
Q2 Task 3 then reconciles against that landed test and owns only its persisted
Q2 v2 wire-format hunks. The two tasks never edit or stage that test
concurrently.

Shared routing and design surfaces are serialized:

- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/capability_status_matrix.md`
- `docs/design/README.md`
- `docs/index.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- `tests/test_workflow_lisp_drain_roadmap_routing.py`

Task 7 begins only when no L1 agent owns those paths. It preserves the factual
completed L1 status already present and stages only Q2 hunks. The fixed closure
order is L1 Task 5 first, then Q2 Task 7.

## File And Responsibility Map

Frontend and lowering:

- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/prompts.py`
- `orchestrator/workflow_lisp/lowering/phase_scope.py`
- `orchestrator/workflow_lisp/lowering/effects.py`
- `orchestrator/workflow_lisp/lowering/origins.py`

Carrier and IR boundaries:

- `orchestrator/workflow/prompt_fragment_contract.py`
- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/core_ast.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/elaboration.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/runtime_step.py`
- `orchestrator/workflow/persisted_surface.py` for byte-stable Q1 v1 graphs
  and explicit Q2 v2 fragment-pair carriage/codec validation
- `orchestrator/workflow_lisp/source_map.py`

Generic validation, prompting, and execution:

- `orchestrator/workflow/validation.py`
- `orchestrator/workflow/prompting.py`
- `orchestrator/contracts/output_contract.py`
- `orchestrator/workflow/executor.py`

Primary tests:

- `tests/test_workflow_lisp_prompt_calculus.py`
- `tests/test_workflow_lisp_prompt_calculus_runtime.py`
- `tests/test_workflow_lisp_prompt_calculus_e2e.py`
- `tests/test_workflow_shared_validation.py`
- `tests/test_prompt_contract_injection.py`
- `tests/test_output_contract.py`
- `tests/test_workflow_output_contract_integration.py`
- `tests/test_workflow_surface_ast.py`
- `tests/test_workflow_core_ast.py`
- `tests/test_workflow_semantic_ir.py`
- `tests/test_workflow_lisp_source_map.py`
- `tests/test_runtime_step_lifecycle.py`

## Preimplementation Plan, Routing, And Control Gate

Before Task 1:

- [ ] Obtain independent `Q2_PLAN_SPEC_APPROVED` against this exact plan and
      accepted design; resolve every finding and repeat.
- [ ] Obtain a distinct `Q2_PLAN_QUALITY_APPROVED`.
- [ ] Record accepted-for-execution status and both ordered tokens without
      changing task scope, then patch-stage only this new plan and the exact Q2
      routing hunks selected by the parent roadmap executor.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py \
    -k 'language_quality or prompt_calculus or post_stage_8'
  ```

- [ ] Obtain final ordered specification then quality reaffirmation against
      the exact staged plan/status/routing bytes. Commit those exact reviewed
      bytes without post-review edits before any production change.
- [ ] At that landed plan-gate commit and before any Q2 production edit, run
      the active roadmap's exact broad non-security command in tmux. Record
      `HEAD`, `HEAD^{tree}`, dirty-tree inventory, collected-node identity set,
      collection/pass/failure/skip totals, and exact failing node IDs as the
      fresh pre-Q2 control. The pre-L1 run may be reused only if it binds this
      identical commit/tree and no L1/Q2 production edit preceded it.

## Task 1: Target Gate, Closed Syntax, Types, And Identity Selection

**Files:**

- Modify: `orchestrator/workflow_lisp/syntax.py`
- Modify: `orchestrator/workflow_lisp/prompts.py`
- Modify: `orchestrator/workflow/validation.py`
- Modify: `tests/test_workflow_lisp_prompt_calculus.py`
- Modify: `tests/test_workflow_shared_validation.py`

- [ ] Write RED tests for target-2.20 refusal; target-2.21 positive syntax;
  duplicated/misplaced `:out`; non-path use; existing-path refinement;
  unrefined wrong fill; explicit wrong fill; missing fill; caller override; and
  competing-error precedence.
- [ ] Bind the Q2-owned cases to the exact codes and owners:
  `prompt_output_positions_require_dsl_2_21`,
  `prompt_output_position_syntax_invalid`,
  `prompt_output_position_kind_invalid`,
  `prompt_output_position_refinement_invalid`, and
  `prompt_output_position_fill_invalid`. Bind missing output fill to the
  existing `prompt_slot_undischarged` code with the application primary and
  missing declaration related. Bind a caller-side `:out`/override keyword to
  existing `prompt_fill_unknown` with that fill keyword primary. Assert the
  target gate precedes Q1 tail/refinement errors; at target 2.21
  multiplicity/placement precedes kind, then normalized Q1
  duplicate/kind/refinement/placeholder checks precede Q2 refinement, then Q1
  fill-name/completeness and type/renderer checks precede Q2 fill
  compatibility. For each competing fixture, removing the higher-priority
  defect exposes the next exact code and source owner. Slots without `:out`
  retain Q1 codes and order.
- [ ] Add target 2.21 to the Workflow Lisp and shared runtime version
  inventories without changing acceptance below 2.21.
- [ ] Begin only after L1 Task 1 has committed its shared
  `ModuleDirective.name_span` hunk. Reconcile `syntax.py` against that commit
  and patch-stage only Q2's target/version and prompt-slot hunks.
- [ ] Add one closed output-role enum/value and retain the `:out` token span.
  Normalize `(slot :path :out [PathType])` before ordinary Q1 slot checks so
  the Q2 target and syntax diagnostics remain reachable.
- [ ] Require both refinement and resolved fill, when present, to be a
  workspace-relative `relpath` contract with `must_exist=false`. Do not convert
  `String`, weaken existing-path types, or create a nominal type.
- [ ] Select identity v1 when no output-role slot exists, even at target 2.21.
  Select v2 only when at least one output-role slot exists; v2 adds
  `output_role` to every declaration slot and changes no other field or order.
- [ ] Add frozen-byte controls for the implemented target-2.20 Q1 canonical
  projection/digest and v1 carrier, plus the same Q1 source compiled at 2.21.
- [ ] Run RED/GREEN and adjacent regressions:

  ```bash
  pytest --collect-only -q tests/test_workflow_lisp_prompt_calculus.py
  pytest -q tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_shared_validation.py \
    -k 'prompt_output_position or prompt_fragment_identity or target_dsl'
  ```

- [ ] Obtain ordered specification then quality approval of the exact staged
  diff and commit.

## Task 2: V2 Carrier, Compiler-Owned Row, And Source Ownership

**Files:**

- Modify: `orchestrator/workflow/prompt_fragment_contract.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`
- Modify: `orchestrator/workflow_lisp/lowering/effects.py`
- Modify: `orchestrator/workflow_lisp/lowering/origins.py`
- Modify: `orchestrator/workflow_lisp/source_map.py`
- Modify: `tests/test_workflow_lisp_prompt_calculus.py`
- Modify: `tests/test_workflow_lisp_source_map.py`

- [ ] Write RED tests for the exact v2 carrier keys, at-least-one-row rule,
  unique names, declaration-relative order, role/kind correspondence, and
  nested expected-output object.
- [ ] Keep the existing v1 carrier class and serializer byte-for-byte
  unchanged. Add a separate v2 carrier with ordered `output_positions`; do not
  make v1 serialize an empty v2 field.
- [ ] Derive a path template only from the already normalized Q1 value source:
  exact `{"ref": R}` becomes `${R}` and an admitted string literal remains
  that exact validated literal. Reject source spelling, AST representation,
  and any second path reconstruction.
- [ ] Construct one normalized slot-role lowering record and use that same
  record for v2 identity input and v2 carrier output rows.
- [ ] Install the nested expected-output objects on the provider step in
  declaration order. Neither call syntax nor the result contract may provide a
  substitute row.
- [ ] Preserve existing generic expected-output carriage instead of adding a
  second IR field or runtime channel.
- [ ] Give each compiler-projected expected output one generic validation
  subject owned primarily by its fill, with the slot and `:out` token retained
  as related origins. Prove runtime subject lookup and source-map round-trip
  without consumer-specific names.
- [ ] Prove classic/WCC lowering produces the same declaration-ordered
  expected-output rows, result bundle, source subjects, identity, and v2
  carrier before the generic IR boundary work begins.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_lisp_source_map.py
  ```

- [ ] Obtain ordered specification then quality approval of the exact staged
  diff and commit.

## Task 3: IR Pair Validation, Persisted Carriage, And Checkpoint Identity

**Files:**

- Modify: `orchestrator/workflow/prompt_fragment_contract.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/runtime_step.py`
- Modify: `orchestrator/workflow/persisted_surface.py`
- Modify: `tests/test_workflow_lisp_prompt_calculus.py`
- Modify: `tests/test_workflow_surface_ast.py`
- Modify: `tests/test_workflow_core_ast.py`
- Modify: `tests/test_workflow_semantic_ir.py`
- Modify: `tests/test_runtime_step_lifecycle.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_build_in_memory.py`
- Modify: `tests/test_workflow_lisp_prompt_calculus_runtime.py`

- [ ] Write RED both-direction tests at each carrier boundary for missing,
  extra, reordered, unequal, v1/v2-mismatched, and unpaired
  identity/carrier/`expected_outputs` data. Every v2 boundary refusal uses
  `prompt_output_position_contract_mismatch` with the provider
  application/source-map owner; ordinary malformed standalone Q1 carriers
  retain their existing Q1 errors.
- [ ] Extend the dedicated fragment pair validator to compare v2 nested rows
  exactly and in order with provider `expected_outputs`. A v1 pair must retain
  its current bytes and behavior; a non-fragment provider's ordinary
  `expected_outputs` must not be mistaken for Q2 carriage.
- [ ] Invoke the pair validator at Surface, Core, Semantic, Executable,
  persisted provider-configuration, and receiving runtime-step boundaries so
  defects fail before provider preparation.
- [ ] Make persisted wire evolution explicit. Preserve
  `persisted_workflow_surface_graph.v1` bytes exactly for every Q1-only and
  non-fragment graph. A graph containing any Q2 carrier writes
  `persisted_workflow_surface_graph.v2`; its affected step carries the existing
  common `expected_outputs` plus the generic
  `compiler_prompt_fragment_contract` and
  `compiled_prompt_fragment_identity` fields as one atomic pair. Decode v1
  with its exact old key set. Decode v2 with the new exact schema, requiring
  each Q2 pair and nested output-position rows to match its common
  `expected_outputs` exactly; reject missing, extra, reordered, unequal, or
  v1/v2-mismatched carriage on both serialization and decode. Do not emit the
  new fields or v2 schema for a Q1 carrier.
- [ ] Define mixed-graph v2 step schemas exactly: a Q2-affected provider step
  has its unchanged v1 step key set plus common `expected_outputs`,
  `compiler_prompt_fragment_contract`, and
  `compiled_prompt_fragment_identity`; a Q1 fragment step and a non-fragment
  step retain their exact prior step key sets and carry neither empty nor
  inferred Q2 fields even though the enclosing graph schema is v2. Add one
  canonical mixed Q2/Q1/non-fragment golden, decode/encode round trip, and
  per-step key-set assertion.
- [ ] Add persisted codec/build-artifact tests in
  `tests/test_workflow_lisp_build_artifacts.py` and
  `tests/test_workflow_lisp_build_in_memory.py`: frozen Q1 v1 canonical bytes;
  positive Q2 v2 canonical round trip; and one tamper test for every missing,
  extra, reordered, unequal, wrong-schema, and unpaired dimension.
- [ ] Prove classic/WCC Semantic and Executable IR parity and exact round trips
  for the result contract, expected-output rows, v2 carrier, source-map
  subjects, and identity.
- [ ] Prove checkpoint program identity includes the paired Q2 data, compatible
  completed-boundary reuse remains valid, and v1/v2 or projected-row drift is
  rejected as ordinary program drift.
- [ ] Prove receiving-attempt agreement without changing
  `workflow_prompt_fragment_snapshot.functional.v1`: a valid attempt records
  its exact existing `compiled_prompt_fragment_identity` field with the Q2 v2
  identity after the receiving runtime config has pair-validated carrier,
  rows, and sources. Missing/tampered/unpaired v2 data fails before provider
  preparation and creates/publishes no attempt snapshot or provider
  invocation evidence.
- [ ] Do not add a Q2-only persisted or evidence field: reuse common
  `expected_outputs`, generic fragment carrier/identity names, and the existing
  functional snapshot identity field.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_surface_ast.py \
    tests/test_workflow_core_ast.py \
    tests/test_workflow_semantic_ir.py \
    tests/test_runtime_step_lifecycle.py \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_workflow_lisp_build_in_memory.py \
    tests/test_workflow_lisp_prompt_calculus_runtime.py
  ```

- [ ] Obtain ordered specification then quality approval of the exact staged
  diff and commit.

## Task 4: Generic Contract Admission, Name Checks, And Prompt Order

**Files:**

- Modify: `orchestrator/workflow/validation.py`
- Modify: `orchestrator/workflow/prompting.py`
- Modify: `tests/test_workflow_shared_validation.py`
- Modify: `tests/test_prompt_contract_injection.py`
- Modify: `tests/test_workflow_output_contract_integration.py`

- [ ] Write RED table tests admitting only
  `expected_outputs + output_bundle` and
  `expected_outputs + variant_output`; reject every combination involving both
  structured contracts, `select_variant_output`, or any third contract.
- [ ] Extract artifact names from all possible structured fields, including
  variant discriminant, shared fields, and every variant field. Reject overlap
  with expected-output names before provider launch using
  `prompt_output_position_contract_collision`; the output slot is primary and
  the structured-result field origin is related.
- [ ] Keep the admission logic generic: it may inspect contract structure but
  contains no prompt, workflow, module, provider, or consumer name.
- [ ] Change prompt completion from exclusive selection to deterministic block
  composition: expected-output block exactly once, then structured-result
  block exactly once. Preserve every single-contract and no-contract byte.
- [ ] Ensure runtime-resolved contract copies retain both members of an
  admitted pair; do not use `if/elif` selection that leaves one member
  unresolved.
- [ ] Add both-direction competing-error controls for the middle diagnostic
  chain: structured-return incompatibility wins over name collision; name
  collision wins over a simultaneously malformed v2 carrier; removing the
  higher-priority defect exposes the next exact diagnostic. Keep declaration
  refinement and application-fill checks at their distinct Task-1 positions.
- [ ] Add positive/negative prompt tests by parsed blocks and ordering, not by
  asserting literal production prompt prose.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_shared_validation.py \
    tests/test_prompt_contract_injection.py \
    tests/test_workflow_output_contract_integration.py \
    -k 'output_contract or expected_outputs or variant_output'
  ```

- [ ] Obtain ordered specification then quality approval of the exact staged
  diff and commit.

## Task 5: Prelaunch Path Equality And Atomic Dual Validation

**Files:**

- Modify exact protected hunks in:
  `orchestrator/contracts/output_contract.py`
- Modify exact protected hunks in:
  `orchestrator/workflow/executor.py`
- Modify exact protected hunks in:
  `tests/test_output_contract.py`
- Modify: `tests/test_workflow_lisp_prompt_calculus_runtime.py`
- Modify: `tests/test_workflow_output_contract_integration.py`
- Modify: `tests/test_workflow_lisp_runtime_source_map.py`

- [ ] Record and inspect the protected-path baseline described above. Confirm
  the RED test fails on current reconciled code before editing production.
- [ ] Write RED path tests for ref-derived and literal-derived equality,
  canonical path normalization, pairwise expected-output destination aliasing,
  aliasing with `output_bundle.path`, aliasing with `variant_output.path`, and
  distinct names that still alias one destination.
- [ ] Bind rendered/resolved inequality to
  `prompt_output_position_contract_mismatch`, owned by the boundary's provider
  application/source-map origin. Bind only destination aliases to
  `prompt_output_position_destination_collision`, with both fills or the fill
  plus structured-bundle/provider-application origin attached. These
  preparation-time diagnostics follow carrier/name validation and precede
  provider launch.
- [ ] Add a competing-error control proving a malformed v2 carrier wins over a
  simultaneous path-equality or destination-alias defect; removing the carrier
  defect exposes the exact mismatch or collision diagnostic.
- [ ] Before provider launch, resolve all admitted contract paths, compare each
  v2 output slot's typed POSIX path-line value to its resolved expected-output
  path, and reject any mismatch or destination alias with the accepted Q2
  diagnostics and source owners.
- [ ] Validate expected outputs first and the structured bundle second into
  separate local mappings. If either raises, return one failed step and attach
  neither map. On joint success, require disjoint names and merge once.
- [ ] Preserve provider-written files on failure; state atomicity is not file
  rollback.
- [ ] Add both-direction runtime coverage:
  required file + valid bundle succeeds; missing file + valid bundle fails;
  required file + missing/invalid bundle fails; neither failure publishes a
  partial artifact map.
- [ ] Ensure existing expected-output runtime violations resolve to the Q2 fill
  subject while preserving all non-Q2 violation shapes and single-contract
  behavior.
- [ ] Do not edit `orchestrator/providers/executor.py` or any isolation path.
- [ ] Run:

  ```bash
  pytest -q tests/test_output_contract.py \
    tests/test_workflow_output_contract_integration.py \
    tests/test_workflow_lisp_prompt_calculus_runtime.py \
    tests/test_workflow_lisp_runtime_source_map.py
  ```

- [ ] Inspect the staged and unstaged protected diffs independently, obtain
  ordered specification then quality approval of the exact staged Q2 hunks,
  and commit.

## Task 6: Real Review Consumer, Checkpoint Drift, And Resume

**Files:**

- Modify: `workflows/examples/review_revise_design_docs.orc`
- Modify: `tests/test_workflow_lisp_prompt_calculus_e2e.py`
- Modify: `tests/test_workflow_lisp_examples.py`
- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Create:
  `tests/fixtures/workflow_lisp/valid/prompt_q1_target_2_20_resume.orc`

- [ ] Write the real-consumer RED assertion before changing the example:
  `review-design-doc.review_report_target_path` is `:path :out
  ReviewReportTargetPath`, the workflow targets 2.21, and one authored fill
  supplies rendering plus required-file validation while `ReviewDecision`
  remains the only structured result authority.
- [ ] Change only the target version and the review fragment's output role.
  Keep the fill, provider selection/policy, result type, review loop, and
  extern-backed fix call unchanged.
- [ ] Before converting that consumer, add an independent target-2.20 Q1
  capturing-provider control using the frozen fixture. Prove one clean run and
  one interrupted/resumed run produce the existing runtime artifacts and v1
  fragment identity/carrier, with exactly one provider execution per committed
  boundary and no Q2 fields. Keep this control after the real consumer moves
  to target 2.21.
- [ ] Extend the capturing provider fixture to write the required UTF-8 review
  file and the structured result bundle. Assert the returned
  `ReviewDecision.review_report` is the intended same path without teaching the
  compiler a general result-field mapping.
- [ ] Prove classic/WCC build parity, one clean completion, interruption after
  the committed review boundary, default resume with no second provider call,
  compatible checkpoint reuse, and rejection of v1/v2 identity or projected
  contract drift. Drift at a live boundary uses
  `prompt_output_position_contract_mismatch`; persisted/checkpoint program
  drift retains the existing program-drift envelope.
- [ ] Add a genericity scan over Q2 compiler/runtime files that rejects all
  consumer workflow, procedure, module, provider, prompt-key, and fixture
  names.
- [ ] Use structural assertions for fragment slots, contract rows, bundle
  fields, provider-call count, artifacts, and checkpoint identity. Do not
  retain a production-prompt-text oracle.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_lisp_prompt_calculus_runtime.py \
    tests/test_workflow_lisp_prompt_calculus_e2e.py \
    tests/test_workflow_lisp_examples.py \
    tests/test_workflow_lisp_procedure_first_migrations.py
  ```

- [ ] Treat this capturing-provider E2E as the required orchestrator/demo smoke
  for the reusable DSL/runtime change.
- [ ] Obtain ordered specification then quality approval of the exact staged
  diff and commit.

## Task 7: Normative Closure, Broad Gate, And Q3 Handoff

**Files:**

- Modify: `specs/index.md`
- Modify: `specs/versioning.md`
- Modify: `specs/dsl.md`
- Modify: `specs/io.md`
- Modify: `specs/providers.md`
- Modify: `specs/state.md`
- Modify: `docs/design/workflow_lisp_prompt_calculus.md`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_semantic_workflow_ir.md`
- Modify: `docs/design/workflow_lisp_executable_ir.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify exact Q2 hunks in: `docs/capability_status_matrix.md`
- Modify exact Q2 hunks in: `docs/design/README.md`
- Modify exact Q2 hunks in: `docs/index.md`
- Modify exact Q2 hunks in:
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- Modify:
  `docs/plans/2026-07-26-workflow-lisp-prompt-output-positions-implementation-plan.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify the narrow authoring/spec tests selected by the existing docs
  contracts.

- [ ] Wait until L1 releases all shared routing/docs paths. Preserve its
  factual status and every owner-authored ambient hunk.
- [ ] Update normative specs from shipped behavior only: target 2.21, the
  admitted contract pair, fixed prompt/validation order, collision rules,
  state atomicity, v2 carrier/identity, checkpoint/resume behavior, and Q2
  exclusions.
- [ ] Update the Workflow Lisp drafting guide with the one available `:path
  :out` form and its first consumer. Check the surrounding prompt/result/output
  guidance for coherence; do not copy Q3/Q4 future surfaces into authoring
  guidance.
- [ ] Mark Q2 implemented in capability and design indexes only after Tasks
  1–5 have reviewed commits and fresh evidence.
- [ ] Record exact Task 1–6 commits, focused outcomes, and per-task review
  tokens in this plan. Route the Q-series to the Q3 design gate while
  preserving the current L-series selector.
- [ ] Run routing and authoring closure:

  ```bash
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py \
    tests/test_workflow_lisp_route_readiness.py \
    tests/test_workflow_yaml_orc_gap_list.py \
    tests/test_monitor_docs.py \
    tests/test_workflow_lisp_examples.py
  ```

- [ ] Run the complete focused Q2 selector:

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_lisp_prompt_calculus_runtime.py \
    tests/test_workflow_lisp_prompt_calculus_e2e.py \
    tests/test_workflow_shared_validation.py \
    tests/test_prompt_contract_injection.py \
    tests/test_output_contract.py \
    tests/test_workflow_output_contract_integration.py \
    tests/test_workflow_surface_ast.py \
    tests/test_workflow_core_ast.py \
    tests/test_workflow_semantic_ir.py \
    tests/test_workflow_lisp_source_map.py \
    tests/test_workflow_lisp_runtime_source_map.py \
    tests/test_runtime_step_lifecycle.py \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_workflow_lisp_build_in_memory.py
  pytest -q tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_lisp_prompt_calculus_runtime.py \
    tests/test_workflow_lisp_prompt_calculus_e2e.py \
    tests/test_workflow_shared_validation.py \
    tests/test_prompt_contract_injection.py \
    tests/test_output_contract.py \
    tests/test_workflow_output_contract_integration.py \
    tests/test_workflow_surface_ast.py \
    tests/test_workflow_core_ast.py \
    tests/test_workflow_semantic_ir.py \
    tests/test_workflow_lisp_source_map.py \
    tests/test_workflow_lisp_runtime_source_map.py \
    tests/test_runtime_step_lifecycle.py \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_workflow_lisp_build_in_memory.py
  ```

- [ ] In tmux, run the broad non-security suite:

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

- [ ] Compare like-for-like with the recorded pre-Q2 control: same
  authoritative command and exact outcomes on the stable-node intersection.
  Enumerate every added, removed, or changed node identity. Classify
  L1-owned additions/changes against L1's ordered reviewed task and closing
  evidence, and classify Q2-owned additions/changes against this plan's
  reviewed task evidence; do not silently fold either into the pre-Q2 totals.
  Fix Q2 regressions and rerun affected gates; classify unrelated deltas
  without repairing excluded security/safety/provider-isolation work.
- [ ] Obtain a final ordered specification review and then quality review of
  the ordered exact Q2 task commit set, a path-limited aggregate diff containing
  only those commits, and the staged closure diff. L1 interleaving is excluded
  from the review input rather than treated as part of a contiguous Q2 range.
  Resolve findings and repeat in order until both approve.
- [ ] Stage only exact Q2 documentation/routing hunks, verify the staged tree,
  and commit the reviewed closure without post-review edits.

## Completion Contract

Q2 is complete only when:

1. every closed Q2 diagnostic has both-direction executable coverage and the
   accepted precedence is preserved;
2. target-2.20 Q1 identity input, digest, carrier bytes, runtime behavior, and
   resume controls remain exact;
3. target-2.21 v2 identity, carrier, expected-output projection, and source
   ownership are exact and classic/WCC-equal;
4. every compiler, IR, persisted, runtime, checkpoint, and resume boundary
   rejects missing, extra, reordered, unequal, or unpaired Q2 carriage before
   provider preparation;
5. shared validation admits only the two accepted contract pairs and rejects
   every other multi-contract combination and name overlap;
6. runtime proves rendered-path equality, destination disjointness, fixed
   prompt/validation order, and state-atomic dual validation;
7. the real review consumer passes clean and interrupted/resumed
   capturing-provider E2Es with one provider execution per committed boundary;
8. generic compiler/runtime machinery contains no consumer, workflow, module,
   provider, prompt-key, or fixture name;
9. durable specs, design status, capability routing, and the drafting guide
   match shipped behavior;
10. focused and broad non-security gates are freshly run and classified;
11. every task commit and the final ordered Q2 task commit set/tree have
    ordered independent specification then quality approval; and
12. the active roadmap marks Q2 complete and selects Q3's design gate without
    disturbing the concurrent L-series route.
