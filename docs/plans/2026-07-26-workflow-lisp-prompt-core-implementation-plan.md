# Workflow Lisp Prompt Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for every production change. Complete
> an ordered specification-compliance review and then an implementation-quality
> review before committing each task.

**Goal:** Implement the accepted Q1 prompt core: target-2.20 `defprompt`
declarations, fully applied fragment-backed provider calls, prompt-owned return
contracts, deterministic rendering and identity carriage, the existing
schema-2.1 prompt-snapshot publication path, and one real migrated consumer.

**Architecture:** A new prompt frontend owner parses and validates declarations,
placeholders, applications, renderer eligibility, and the closed identity
projection. Module resolution gives prompts a distinct compile-time namespace.
Classic and WCC lowering carry the validated fragment application and one
compiled identity through Semantic and Executable IR. Runtime rendering produces
one in-memory base prompt and reuses the existing typed-input, dependency,
output-contract, schema-2.1 attempt allocator, and prompt-snapshot owners. No
runtime prompt object or second result authority is introduced.

**Approved design:** `docs/design/workflow_lisp_prompt_calculus.md` at commit
`5cab2160`, exact SHA-256
`8410274c6681f406d14854265705156a73a1936e55f559cd9badee71fead611a`.

**Execution status:** accepted for execution after ordered independent plan
review: specification `Q1_IMPLEMENTATION_PLAN_SPEC_APPROVED`, quality
`Q1_IMPLEMENTATION_PLAN_QUALITY_APPROVED`, and post-quality specification
reaffirmation `Q1_IMPLEMENTATION_PLAN_SPEC_REAFFIRMED`. No Q1 implementation is
claimed until every task and the closing gates below pass.

**Deliberate cost:** Q1's direct, closed expression identity grammar and
fragment-specific schema-2.1 snapshot make arbitrary prompt composition,
partial application, runtime prompt references, and schema-2.2 unification
harder. Those changes remain separate, reviewed migrations rather than implicit
extensions of Q1.

## Scope And Invariants

The implementation must preserve these accepted boundaries:

- `defprompt` and fragment use require `(:target-dsl "2.20")`;
- prompts occupy a distinct compile-time import/export namespace;
- only one direct, fully applied named prompt is accepted in
  `provider-result :prompt`;
- fragment-backed calls forbid authored `:inputs`, `:prompt-dependencies`, and
  `:returns`;
- the declaration's sole `ReturnSpec` remains result authority and defaults to
  exact `Value`;
- slot kinds are delivery constraints, not nominal types or conversions;
- only literal, lexical-name, and lexical-rooted field-path fills enter the
  identity projection;
- Semantic IR, Executable IR, and attempt evidence carry byte-equal
  `compiled_prompt_fragment_identity` values before provider launch;
- fragment attempts publish
  `workflow_prompt_fragment_snapshot.functional.v1` through the current public
  schema-2.1 attempt allocator and terminal validator;
- extern-backed evidence and successful artifact bytes remain unchanged;
- no schema-2.2, provider-isolation, security-hardening, Q2 output-position, Q3
  diagnostic-comparison, or Q4 judgment-view work belongs to this plan; and
- tests assert structures, identities, dataflow, and behavior, never literal
  production prompt prose.

## Concurrent Working-Tree Contract

The working tree contains owner work for provider isolation, output contracts,
workflow recovery, experiment reports, and documentation routing. Preserve it
byte-for-byte unless one exact hunk is independently required by this plan.

In particular, these Q1-adjacent paths contain ambient schema-2.2 or
provider-isolation edits:

- `orchestrator/state.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/workflow/provider_attempts.py`
- `orchestrator/workflow/prompt_dependency_evidence.py`
- `orchestrator/providers/executor.py`
- `orchestrator/contracts/output_contract.py`

Q1 is designed against each path's committed `HEAD` behavior. Prefer new files
and narrowly owned hunks. Before every commit:

```bash
git diff --cached --check
git diff --cached --name-only
```

Stage exact paths or exact hunks only. Never use `git add .`, `git add -A`, or
stage a whole shared file without comparing the staged blob to the intended
task patch. Security/provider-isolation tests are outside the verification set.

## Task 1: Target Gate, Declarations, And Placeholder Contract

**Files:**

- Create: `orchestrator/workflow_lisp/prompts.py`
- Modify: `orchestrator/workflow_lisp/syntax.py`
- Modify: `orchestrator/workflow_lisp/form_registry.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Create: `tests/test_workflow_lisp_prompt_calculus.py`

- [ ] Write failing tests for the 2.20 target gate; declaration shape; slot
  kinds/refinements; duplicate slots; exact brace/placeholder grammar;
  rendered-slot completeness; forbidden document placeholders; default
  `Value`; and result guidance parsing.
- [ ] Run collection and the narrow tests to prove RED:

  ```bash
  pytest --collect-only -q tests/test_workflow_lisp_prompt_calculus.py
  pytest -q tests/test_workflow_lisp_prompt_calculus.py
  ```

- [ ] Implement immutable prompt declaration/slot/template models and one parser
  owner. Reuse `ReturnSpec`, existing target comparison, type syntax, spans, and
  diagnostic constructors.
- [ ] Keep `defprompt` unreserved as a general expression below 2.20 while
  diagnosing its Q1 form with `prompt_calculus_requires_dsl_2_20`.
- [ ] Run the narrow tests GREEN.
- [ ] Obtain ordered spec then quality review of the exact staged diff.
- [ ] Commit the reviewed task.

## Task 2: Prompt Namespace, Applications, Types, And Identity

**Files:**

- Modify: `orchestrator/workflow_lisp/prompts.py`
- Modify: `orchestrator/workflow_lisp/modules.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify the narrow typecheck/traversal owners selected by the existing
  provider-result dispatcher.
- Modify: `orchestrator/workflow_lisp/typed_prompt_inputs.py`
- Modify: `tests/test_workflow_lisp_prompt_calculus.py`
- Modify: `tests/test_workflow_lisp_typed_prompt_inputs.py`

- [ ] Write failing tests for local/imported/exported prompt resolution,
  ambiguity and missing names; fully applied named fills; duplicate/unknown/
  missing fills; kind/refinement compatibility; forbidden call-site
  redeclarations; prompt-owned result typing including default exact `Value`
  and one explicit structured `ReturnSpec`; the exact admitted fill expression
  grammar; canonical identity stability and change sensitivity; and
  malformed/unsupported identity refusal.
- [ ] Exercise every code in the design's closed Q1 refusal table and the
  accepted diagnostic precedence with competing failures. Explicitly reject
  residual/partial application, fragment-valued or nested fragment use,
  `:out`, prompt-as-value, `proc-ref` of a prompt, and call-site `:returns`,
  `:inputs`, and `:prompt-dependencies`.
- [ ] Add both-direction renderer tests for the recursive Q1 `List[T]` rule,
  including `List[DesignDocPath]`, and negative Optional/Map/union cases.
- [ ] Implement a prompt prepass/catalog and a distinct module namespace without
  making prompts values or `ProcRef`s.
- [ ] Parse prompt applications only in provider prompt position. Normalize
  named fills into declaration order after resolution and typecheck.
- [ ] Reuse the existing normalized type descriptor and result-guidance payload
  when constructing `compiled_prompt_fragment_identity.v1`; do not use spans,
  source spelling, `repr`, runtime values, or absolute paths.
- [ ] Add raw UTF-8 string selection for `:text` only through the fragment
  renderer contract; do not widen the ordinary authored `:inputs` surface.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_lisp_typed_prompt_inputs.py
  ```

- [ ] Obtain ordered spec then quality review and commit.

## Task 3: Classic And WCC Lowering Plus Typed IR Carriage

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/effects.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Create: `orchestrator/workflow/prompt_fragment_contract.py`
- Modify: `orchestrator/workflow/prompt_dependency_contract.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/runtime_step.py`
- Modify focused lowering, WCC, semantic-IR, executable-IR, source-map, and
  prompt-input tests.

- [ ] Write failing classic/direct and WCC tests proving identical normalized
  fragment application, rendered typed inputs/document rows, derived result
  contract, and identity.
- [ ] Write fail-closed IR validation and round-trip tests for missing,
  malformed, and mismatched identities, plus an absence-sensitive extern
  control.
- [ ] Introduce the closed frozen
  `CompilerPromptFragmentContract`/`CompilerPromptFragmentRenderedSlot` runtime
  carrier in `prompt_fragment_contract.py`. It owns exact template UTF-8,
  ordered rendered-slot name/kind/type/renderer/value-source/placeholder rows,
  and canonical serialization/validation. It does not own provider policy,
  runtime values, document bytes, or output-contract text.
- [ ] Carry that program as `compiler_prompt_fragment_contract` and its separate
  exact digest as `compiled_prompt_fragment_identity` on `SurfaceStep`,
  `CoreProviderStep`, `ProviderStepConfig`, and `SemanticPromptSurface`.
  `ProviderResultExpr` retains the resolved compile-time application; these four
  dataclasses are the executable/semantic boundary and must reject a contract
  without its matching digest or a digest without its contract.
- [ ] Add the closed `workflow_lisp_prompt_fragment` dependency origin now,
  before lowering document slots: zero-or-more required exact paths, no
  optional paths or authored instruction, and fixed prepend position.
- [ ] Carry typed fragment structure only as far as compilation needs it; carry
  the closed digest in Semantic and Executable IR under the exact accepted
  field name.
- [ ] Lower `:doc` slots into the existing required/prepend compiler dependency
  contract with declaration-order provenance. Lower rendered slots through the
  selected registry renderers.
- [ ] Preserve classic/WCC parity, source-map ownership, build determinism, and
  byte-for-byte extern absence behavior.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_lisp_wcc_m1.py \
    tests/test_workflow_lisp_wcc_m4.py \
    tests/test_workflow_semantic_ir.py \
    tests/test_workflow_lisp_source_map.py \
    tests/test_workflow_lowering_invariants.py
  ```

- [ ] Obtain ordered spec then quality review and commit.

## Task 4: Runtime Fragment Rendering And Schema-2.1 Snapshot

**Files:**

- Modify only Q1-owned hunks in:
  `orchestrator/workflow/prompt_dependency_evidence.py`
- Modify: `orchestrator/workflow/prompting.py`
- Modify only Q1-owned hunks in: `orchestrator/workflow/executor.py`
- Modify the smallest provider-preparation/runtime-step owner required by the
  landed Task 3 carrier.
- Modify: `tests/test_prompt_dependency_evidence.py`
- Create: `tests/test_workflow_lisp_prompt_calculus_runtime.py`

- [ ] Write failing tests for
  `workflow_prompt_fragment_snapshot.functional.v1`, including zero-document
  snapshots, closed keys, identity shape/equality, canonical digesting,
  publication, terminal indexing/validation, and tamper rejection.
- [ ] Add a negative-control golden proving existing
  `workflow_prompt_dependency_evidence.functional.v1` success records are
  byte-identical.
- [ ] Render the fragment base prompt exactly once, then reuse dependency,
  consumed-artifact, output-contract, and provider-transport composition owners.
- [ ] Reject missing/malformed/mismatched Semantic/Executable/evidence identity
  before provider preparation. Do not read evidence as resume authority.
- [ ] Use the committed schema-2.1 allocator and `prompt_snapshot` record kind;
  do not depend on or stage ambient schema-2.2/provider-isolation changes.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_prompt_calculus_runtime.py \
    tests/test_prompt_dependency_evidence.py \
    tests/test_runtime_step_lifecycle.py \
    tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py
  ```

- [ ] Obtain ordered spec then quality review and commit exact hunks only.

## Task 5: Build, Resume, And Real Consumer Proof

**Files:**

- Create:
  `tests/test_workflow_lisp_prompt_calculus_e2e.py`
- Modify the smallest existing lexical-checkpoint test owner if shared
  checkpoint coverage is clearer there.
- Modify: `workflows/examples/review_revise_design_docs.orc`
- Modify:
  `workflows/examples/inputs/review_revise_design_docs/prompts.json`
- Delete: `prompts/workflows/review_revise_design_docs/review.md`
- Modify focused example/build/procedure-first migration tests.

- [ ] Write an end-to-end fixture with a capturing provider that proves exact
  rendered dataflow, prompt-owned typed return validation, fragment snapshot
  publication, clean completion, interruption after a committed provider
  boundary, and default resume without duplicate provider execution.
- [ ] Add a checkpoint-identity change test and an unchanged-identity reuse
  control.
- [ ] Migrate only `review-design-docs` to target 2.20 `defprompt`, preserving
  all five inputs and `ReviewDecision`; keep `fix-design-doc` extern-backed and
  behaviorally unchanged.
- [ ] Remove only the now-unused review prompt manifest row and prompt file.
- [ ] Compile the real consumer through classic and WCC/schema-2 paths, retaining
  preferred-current guidance. Assert all five typed/dependency contributions
  structurally, not by production prose.
- [ ] Bind a pre-migration fixture/golden and prove intentional equivalence of
  the composed base/dependency/input/output-contract bytes apart from the
  reviewed placeholder normalization that makes the fragment explicit.
- [ ] Prove provider selection, model, effort, timeout, result contract, bundle
  authority, retry/resume, and review-loop behavior are unchanged, and prove
  the fix call and its extern prompt remain unchanged.
- [ ] Run a genericity scan/test that rejects any migrated
  workflow/procedure/module/provider/prompt key or asset name in generic
  compiler and runtime machinery.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_lisp_prompt_calculus_runtime.py \
    tests/test_workflow_lisp_prompt_calculus_e2e.py \
    tests/test_workflow_lisp_examples.py \
    tests/test_workflow_lisp_procedure_first_migrations.py
  ```

- [ ] Obtain ordered spec then quality review and commit.

## Task 6: Normative And Authoring Surface Closure

**Files:**

- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_semantic_workflow_ir.md`
- Modify: `docs/design/workflow_lisp_executable_ir.md`
- Modify: `specs/providers.md`
- Modify: `specs/state.md`
- Modify the Workflow Lisp drafting/authoring guide selected by `docs/index.md`
- Modify exact Q1-owned hunks in:
  `docs/capability_status_matrix.md`,
  `docs/design/README.md`, and `docs/index.md`
- Modify routing/authoring tests.

- [ ] Update durable specs from shipped behavior only: 2.20 surface,
  diagnostics, renderer selection, result ownership, fragment identity,
  schema-2.1 snapshot, resume semantics, and Q2/Q3/Q4 exclusions.
- [ ] Check the Lisp workflow drafting guide for coherent current syntax,
  targets, examples, and routing; remove stale Q1 proposal wording without
  copying future surfaces into shipped guidance.
- [ ] Update capability/routing surfaces to `implemented` only after focused
  implementation evidence exists.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py \
    tests/test_workflow_lisp_route_readiness.py \
    tests/test_workflow_yaml_orc_gap_list.py \
    tests/test_monitor_docs.py \
    tests/test_workflow_lisp_examples.py
  ```

- [ ] Obtain ordered spec then quality review and commit exact hunks only.

## Task 7: Closing Gates And Roadmap Handoff

**Files:**

- Modify:
  `docs/plans/2026-07-26-workflow-lisp-prompt-core-implementation-plan.md`
- Modify exact Q1-owned hunks in:
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`

- [ ] Run focused Q1 tests and one full collection:

  ```bash
  pytest --collect-only -q
  pytest -q tests/test_workflow_lisp_prompt_calculus.py \
    tests/test_workflow_lisp_prompt_calculus_runtime.py \
    tests/test_workflow_lisp_prompt_calculus_e2e.py \
    tests/test_prompt_dependency_evidence.py \
    tests/test_workflow_lisp_typed_prompt_inputs.py
  ```

- [ ] In tmux, run the broad non-security suite:

  ```bash
  pytest -q -n 16 --dist=worksteal \
    --ignore=tests/test_provider_isolation_backend.py \
    --ignore=tests/test_provider_isolation_bundle_broker.py \
    --ignore=tests/test_provider_isolation_schema_resources.py \
    --ignore=tests/test_provider_isolation_attestation.py \
    --ignore=tests/test_provider_isolation_controller_lifecycle.py \
    --ignore=tests/test_provider_isolation_execution.py \
    --ignore=tests/test_provider_isolation_workflow_continuation.py \
    --ignore=tests/test_provider_isolation_workflow_lifecycle.py \
    --ignore=tests/test_workflow_provider_isolation_integration.py
  ```

- [ ] Classify every failure against the pre-Q1 baseline; fix Q1 regressions and
  rerun the relevant gate. Do not repair unrelated/security failures.
- [ ] Freeze the exact contiguous commit range from the reviewed plan commit
  through Task 6 and obtain final ordered specification then quality review of
  that committed range/tree. There is no second implementation commit: Tasks
  1–6 already landed their individually reviewed changes.
- [ ] In one plan-only closure commit, record the exact implementation
  commits/tree, focused/broad outcomes, final review tokens, and mark Q1
  complete. Route the roadmap to L0 without starting Q2.

## Completion Contract

Q1 is complete only when:

1. every Q1 diagnostic and positive/negative contract above has executable
   coverage;
2. classic and WCC builds agree;
3. the real generic-review consumer is migrated, one clean and one
   interrupted/resumed capturing-provider run pass without duplicate provider
   work, and its obsolete review prompt asset is removed, while composed prompt
   delivery, WCC/schema-2 status, preferred guidance, provider policy,
   result/bundle authority, retry/resume, review-loop behavior, and the
   extern-backed fix call satisfy the accepted equivalence gate;
4. existing extern behavior and evidence bytes remain unchanged;
5. generic compiler/runtime machinery contains no migrated consumer, family,
   module, provider, prompt-key, or prompt-asset name;
6. durable docs and the drafting guide match shipped behavior;
7. focused and broad non-security gates are freshly classified;
8. every task and the final committed range/tree have ordered independent spec then
   quality approval; and
9. the plan-only closure commit routes the roadmap to L0.
