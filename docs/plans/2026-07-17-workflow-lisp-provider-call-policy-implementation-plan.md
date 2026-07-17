# Workflow Lisp Provider-Call Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task-by-task.
> Every task requires a specification-compliance review followed by an
> implementation-quality review before the next task starts. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Add generic, typed `.orc` call-local model, effort, and positive-literal
timeout policy to ordinary `provider-result`, preserve it through compile/run/resume,
and map canonical model/effort values through declarative provider-template data.

**Architecture:** Extend the existing provider-result AST and WCC payload, lower
only authored model/effort values into a closed internal `provider_call_policy`
mapping, and continue using the existing common `timeout_sec` field. Carry that
mapping through Surface/Core/Executable/RuntimeStep, then let the resolved
`ProviderTemplate` translate canonical options to native parameters or conditional
argv fragments before the existing single substitution and command-build path.
Provider identity stays compiler-known; provider-specific knowledge stays in
provider data; public resume continues to rebuild and use existing identity and
checkpoint guards.

**Tech Stack:** Python 3.11+, frozen dataclass AST/IR records, Workflow Lisp WCC
schema 2, shared workflow validation, provider registry/executor, pytest/xdist,
tmux.

**Approved design:**
`docs/plans/2026-07-17-workflow-lisp-provider-call-policy-design.md` at commit
`069b8e79`.

**Execution status:** Task 1 complete; Task 2 is next. This plan is a living, reviewed execution
artifact: every task updates its own completed checkboxes and the status line above,
stages this file with that task's code/tests, and commits the plan update in the same
task commit. A task may mark its implementation/test steps complete before review;
it must not record a review as passed before that verdict exists.

---

## Scope And Deliberate Cost

Implement the smallest generic surface approved by the design:

- `:model` and `:effort` accept exactly typed, effect-free, inline-lowerable
  `String` expressions;
- `:timeout-sec` accepts only a positive `Int` literal;
- `provider_call_policy` is compiler-owned internal step data and is rejected in
  authored YAML/YML;
- `call_policy_bindings` is programmatic/built-in provider data and is rejected
  in authored YAML provider-template configuration;
- absent keywords do not synthesize policy, parameters, defaults, argv fragments,
  or new serialized `null` fields;
- supported canonical options are the closed ordered set `model`, `effort`.

This makes dynamic timeout, arbitrary provider parameters, YAML-authored binding
declarations, and adding a fourth canonical option harder later: each requires a
separate contract plus new validation, identity, compatibility, and provider-data
coverage. That cost is intentional; it prevents the two survivor ports from
turning a bounded parity requirement into an untyped provider escape hatch.

When its exact-tree review and commit sequence completes, this plan closes only the
generic `provider-call-policy-parity` and the separate shared
provider-invocation-profile capability. It does not promote either survivor
workflow, satisfy either family's prompt/artifact proof, or authorize YAML deletion.

## Governing Authorities

Read these before implementation and treat the first applicable durable contract
as authoritative:

- `docs/index.md`
- `docs/capability_status_matrix.md`
- `docs/plans/2026-07-17-workflow-lisp-provider-call-policy-design.md`
- `docs/workflow_yaml_orc_gap_list.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/providers.md`
- `specs/dsl.md`
- `specs/state.md`

## Protected Working-Tree Contract

The following pre-existing paths belong to the user and are outside this plan.
Do not edit, restore, stage, or commit them:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

Two pre-existing untracked plan drafts are also owned by other work. Do not edit or
stage them. They are not part of the candidate index, but Task 8 records their
presence/status/exact bytes in a separate allowed-untracked manifest so the tested
working tree is fully disclosed:

- `docs/plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-design.md`
- `docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md`

Before every commit in this plan, run both commands:

```bash
git diff --cached --name-only -- \
  docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md \
  docs/plans/2026-07-01-workflow-audit-tier-fixes.md \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md \
  state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt \
  tests/test_workflow_non_progress_step_back_demo.py \
  workflows/examples/non_progress_step_back_demo.yaml \
  workflows/library/prompts/workflow_step_back/diagnose_non_progress.md
git diff --cached --check
```

Expected for both: no output. Stage only the exact paths named by the current task;
never use `git add -A`, `git add .`, or a broad directory add.

## File Responsibility Map

### New focused proof surface

- Create `tests/test_workflow_lisp_provider_call_policy.py`: parser, AST,
  diagnostics, traversal, macro normalization, WCC, lowering, typed IR,
  serialization, identity, and unchanged-projection contract tests.
- Create `tests/test_provider_call_policy.py`: provider binding schema,
  registration, built-in/profile data, merge/substitution, actual argv variants,
  unsupported-provider, YAML-provider compatibility, and timeout regression tests.
- Create `tests/test_workflow_lisp_provider_call_policy_e2e.py`: public
  build/run/resume and drift rejection through the ordinary executor.
- Create `tests/fixtures/workflow_lisp/provider_call_policy/keyword_free.orc`:
  stable provider-result with none of the new keywords.
- Create `tests/fixtures/workflow_lisp/provider_call_policy/policy.orc`: root input
  model/effort plus literal timeout fixture.
- Create `tests/fixtures/workflow_lisp/provider_call_policy/procedure_policy.orc`:
  nested inline procedure and loop/control preservation fixture.
- Create `tests/fixtures/workflow_lisp/provider_call_policy/providers.json`:
  compiler-known extern aliases targeting shared built-ins.
- Create `tests/fixtures/workflow_lisp/provider_call_policy/prompts.json` and
  `tests/fixtures/workflow_lisp/provider_call_policy/prompt.md`: prompt extern
  assets without prompt-text assertions.
- Create `tests/fixtures/workflow_lisp/provider_call_policy/finish.py` and
  `tests/fixtures/workflow_lisp/provider_call_policy/commands.json`: deterministic
  downstream interruption/resume boundary for the public E2E proof.
- Create
  `tests/baselines/workflow_lisp/provider_call_policy_keyword_free.json`: canonical
  pre-feature bytes for keyword-free frontend/Core/Executable/RuntimeStep provider
  representations.

### Frontend and WCC owners

- Modify `orchestrator/workflow_lisp/expressions.py`: optional AST fields,
  explicit keyword allowlist, authored-value spans, and literal timeout capture.
- Modify `orchestrator/workflow_lisp/expression_traversal.py`: visit present
  model/effort operands.
- Modify `orchestrator/workflow_lisp/typecheck_effects.py`: exact String typing,
  effect-free/inline-lowerable checks, literal timeout diagnostics, and effect
  aggregation.
- Modify `orchestrator/workflow_lisp/macros.py`: replace provider-result positional
  hygiene assumptions with keyword-aware traversal.
- Modify `orchestrator/workflow_lisp/functions.py`: preserve policy operands in
  expression normalization.
- Modify `orchestrator/workflow_lisp/wcc/elaborate.py`: carry present operands in
  the provider perform payload and preserve them during nested binding extraction.
- Modify `orchestrator/workflow_lisp/wcc/defunctionalize.py`: reconstruct and lower
  the three optional operands on every provider-result route.
- Modify `orchestrator/workflow_lisp/wcc/route.py`: validate present model/effort
  operands in every supported WCC route.
- Modify `orchestrator/workflow_lisp/lowering/effects.py`: extend the one shared
  `LowerableProviderResult` owner and emit canonical policy plus literal timeout.

No production edit is expected in `orchestrator/workflow_lisp/wcc/model.py`:
`WccPerform.operation_payload` already owns typed operation-specific payloads.
No production edit is expected in
`orchestrator/workflow_lisp/procedure_specialization.py`: its local-value
specialization and shared expression traversal are the existing owners; the new
tests must prove that is sufficient rather than add a parallel substitution path.

### Shared workflow IR and runtime owners

- Modify `orchestrator/workflow/elaboration.py`: accept/freeze compiler-generated
  policy only after shared validation permits Workflow Lisp origin.
- Modify `orchestrator/workflow/surface_ast.py`: optional provider policy on
  `SurfaceStep`.
- Modify `orchestrator/workflow/core_ast.py`: optional policy on
  `CoreProviderStep`, round-trip reconstruction, and omission-aware JSON.
- Modify `orchestrator/workflow/lowering.py`: carry policy into
  `ProviderStepConfig`.
- Modify `orchestrator/workflow/executable_ir.py`: optional policy, closed payload
  validation, and a field-local serializer/metadata contract that omits only absent
  policy and emits present policy keys in `model`, then `effort` order without
  changing the global lexical ordering of unrelated mappings.
- Modify `orchestrator/workflow/runtime_step.py`: expose policy only when present.
- Modify `orchestrator/workflow/validation.py`: validate the closed internal map,
  reserve it from YAML/YML, and reserve provider-template binding data from YAML.
- Modify `orchestrator/workflow/executor.py`: pass policy separately into ordinary
  invocation preparation.

No production edit is expected in `orchestrator/workflow/runtime_plan.py`,
`orchestrator/workflow/semantic_ir.py`,
`orchestrator/workflow/persisted_surface.py`, or
`orchestrator/workflow_lisp/source_map.py`; tests must prove those projections do
not become policy authority.

### Provider owners

- Modify `orchestrator/providers/types.py`: declarative call-policy binding type,
  one shared **general** command-placeholder extractor that preserves existing
  dotted run/context/loop/steps placeholder names, a separate bare
  provider-target validator used only for `target_param`, structural validation,
  and the optional provider-template binding map.
- Modify `orchestrator/providers/registry.py`: validate built-ins at initialization,
  declare canonical mappings, and add the two shared no-default provider-data
  profiles `codex_unrestricted_workspace` and
  `claude_unrestricted_workspace`.
- Modify `orchestrator/providers/executor.py`: import the general placeholder
  extractor from `types.py`, retain dotted runtime/context placeholder behavior,
  perform generic canonical-to-native mapping, one merge, one substitution pass,
  selected-variant fragment append, bounded unsupported-option failure, and the
  unchanged policy-absent path.
- Modify `orchestrator/providers/__init__.py`: import `CallPolicyBinding` and include
  it in `__all__`; `ProviderTemplate` is already public and programmatic custom
  templates need this explicit public dataclass construction surface.

### Documentation and routing

- Modify `specs/providers.md`, `specs/dsl.md`, and `specs/state.md`.
- Modify `docs/design/workflow_lisp_frontend_specification.md`.
- Modify `docs/lisp_workflow_drafting_guide.md`.
- Modify `docs/capability_status_matrix.md`.
- Modify `docs/workflow_yaml_orc_gap_list.md` only after the complete focused and
  E2E proof is green; add a separate provider-invocation-profile parity row rather
  than hiding unrestricted-workspace argv parity inside call-policy wording.
- Modify `tests/test_workflow_lisp_drain_roadmap_routing.py` to bind the two distinct
  generic closures without claiming either family has promoted.
- Modify `docs/plans/2026-07-17-workflow-lisp-provider-call-policy-design.md` only
  in Task 9's staged closure candidate, after focused/broad/smoke gates. The two
  final reviewers must approve that exact staged status update before it is
  committed unchanged; do not rewrite the accepted design or record nonexistent
  review/commit evidence while preparing the candidate.

## Review Discipline For Every Task

After the implementation subagent completes a task and its narrow tests are green:

1. Check the task's completed red/green boxes, update **Execution status**, and
   stage this plan with the task's exact code/test paths.
2. Dispatch a fresh specification-compliance reviewer with only this plan, the
   approved design, the task number, and the exact staged diff.
3. Resolve every contract finding, rerun the task's selectors, update this plan,
   and restage the exact tree.
4. Dispatch a different implementation-quality reviewer against the corrected
   exact tree.
5. Resolve every quality finding, rerun the selectors, update this plan, and repeat
   both reviews after any staged-tree change.
6. Run the protected-path guard, then commit only the unchanged reviewed task tree,
   including this plan.

Do not let a reviewer waive a failing test, weaken a diagnostic, broaden YAML, or
replace a public-path proof with helper-only inspection.

The final closure has a stricter sequence: finish Tasks 1-7; run and capture the
focused, broad, and public smoke gates in Task 8; prepare and stage the normative
docs, routing assertions, gap/capability closure, design-status closure, and this
plan in Task 9; run one confirming broad pass bound to that exact staged tree plus
the disclosed protected/untracked overlays; then obtain both final reviewers'
approval of that exact tested state; then commit the candidate tree byte-for-byte
unchanged. The staged closure wording is only a
candidate until both verdicts approve it and the unchanged tree is committed. Do
not report the capability implemented, change durable status in an earlier commit,
or claim design closure before that point.

### Task 1: Freeze Keyword-Free Representation Before Production Edits

**Files:**

- Modify: `docs/plans/2026-07-17-workflow-lisp-provider-call-policy-implementation-plan.md`
- Create: `tests/test_workflow_lisp_provider_call_policy.py`
- Create: `tests/fixtures/workflow_lisp/provider_call_policy/keyword_free.orc`
- Create: `tests/fixtures/workflow_lisp/provider_call_policy/providers.json`
- Create: `tests/fixtures/workflow_lisp/provider_call_policy/prompts.json`
- Create: `tests/fixtures/workflow_lisp/provider_call_policy/prompt.md`
- Create: `tests/baselines/workflow_lisp/provider_call_policy_keyword_free.json`

- [x] **Step 1: Add the keyword-free fixture and characterization helper**

  Use a provider-result returning a small transportable record, a compiler-known
  provider extern, and a prompt extern. Do not author `:model`, `:effort`, or
  `:timeout-sec`.

- [x] **Step 2: Build one canonical representation payload**

  The payload must contain the provider-result portion of `_json_data` typed AST,
  `_statement_to_json` Core provider statement, executable provider config JSON,
  and `dict(RuntimeStep(...))`. Use constant source spans/identities so the golden
  is workspace-independent. Canonicalize with sorted keys and compact separators,
  then store those exact bytes in the baseline file.

- [x] **Step 3: Prove the characterization passes before feature code**

  Run:

  ```bash
  pytest -q tests/test_workflow_lisp_provider_call_policy.py::test_keyword_free_provider_result_matches_pre_feature_golden_bytes
  ```

  Expected: PASS on the pre-feature code. This is the compatibility baseline, not
  a red test.

- [x] **Step 4: Prove the runtime/topology exclusions before feature code**

  Add characterization assertions that runtime plan, Semantic IR, persisted graph,
  and source-map subject schemas contain the ordinary provider occurrence but no
  `provider_call_policy` field.

  Run:

  ```bash
  pytest -q tests/test_workflow_lisp_provider_call_policy.py -k 'keyword_free or projection_exclusion'
  ```

  Expected: PASS.

- [x] **Step 5: Review and commit the characterization**

  Check the completed Task 1 boxes and update **Execution status**. Stage this plan
  plus exactly the six characterization files listed in this task, run both reviews
  and the protected-path guard, then commit the unchanged reviewed tree:

  ```bash
  git commit -m "test: characterize keyword-free provider results"
  ```

### Task 2: Parse, Type, Traverse, And Normalize Policy Operands

**Files:**

- Modify: `docs/plans/2026-07-17-workflow-lisp-provider-call-policy-implementation-plan.md`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/expression_traversal.py`
- Modify: `orchestrator/workflow_lisp/typecheck_effects.py`
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `tests/test_workflow_lisp_provider_call_policy.py`

- [ ] **Step 1: Write red parser and AST tests**

  Cover each keyword alone, all three in multiple orders, present-versus-absent
  fields, authored value spans, missing values, duplicate keywords, and an unknown
  keyword. Require `frontend_parse_error` for malformed/duplicate pairs and
  `provider_result_keyword_invalid` for a keyword outside the explicit allowlist.

  Run:

  ```bash
  pytest -q tests/test_workflow_lisp_provider_call_policy.py -k 'parse or keyword or ast'
  ```

  Expected: FAIL because the fields and allowlist do not exist.

- [ ] **Step 2: Add optional AST fields with omission metadata**

  Add `model`, `effort`, and `timeout_sec` to `ProviderResultExpr`. Use
  `json_omit_if_none` metadata so absent fields do not alter public typed-AST bytes.
  Elaborate each present value through the existing expression elaborator and keep
  the timeout as its authored literal node.

- [ ] **Step 3: Add red exact typing and value-domain tests**

  Accept String literal, workflow input, procedure parameter, lexical name, and
  field projection model/effort operands. Typecheck before checking source shape or
  effects: every non-String operand, including a computed expression whose inferred
  result is non-String, must receive `provider_result_model_type_invalid` or
  `provider_result_effort_type_invalid`. Only an operand already proven to have
  exact `String` type may receive
  `provider_result_policy_operand_not_inline_lowerable`; cover String-typed
  computed `if`, pure operators, calls, records, and direct-effect expressions at
  the authored value span.

  Add effect-summary directionality cases. A String-typed operand with empty
  `direct_effects` but nonempty `transitive_effects` must be rejected as not inline
  lowerable. A permitted inline source shape whose summary has empty direct and
  transitive effects but retains `procedure_edges` must remain admissible; procedure
  edges alone are provenance/call-graph metadata, not an effect rejection.

  Accept only positive Int literal timeouts. Cover Bool, Float, numeric String,
  name/reference, computed expression, zero, and negative values with the exact
  three timeout diagnostics from the design.

  Run:

  ```bash
  pytest -q tests/test_workflow_lisp_provider_call_policy.py -k 'type or inline_lowerable or timeout'
  ```

  Expected: FAIL with missing policy type rules.

- [ ] **Step 4: Implement minimal type/effect checks**

  Recurse through each present operand once. First require exactly
  `PrimitiveTypeRef("String")` and emit the field-specific type diagnostic on
  mismatch. Only then restrict source shape to the existing scalar inline route
  (`LiteralExpr`, `NameExpr`, `FieldAccessExpr` after ordinary specialization) and
  require `not summary.direct_effects and not summary.transitive_effects`.
  Deliberately do **not** require equality with `EMPTY_EFFECT_SUMMARY`, because
  `procedure_edges` are allowed. Emit the inline-lowerable diagnostic for either a
  String-typed shape or effect failure. Merge accepted operand summaries into the
  provider-result summary. Validate timeout literal kind/type/positivity at compile
  time; do not add a runtime timeout parser.

- [ ] **Step 5: Add red traversal, macro, and normalization tests**

  Require `iter_child_exprs`, `walk_expr`, function normalization, and macro hygiene
  to preserve model/effort independently of keyword order. Require the timeout node
  to remain authored and unchanged. Include macro-expanded lexical references so a
  hard-coded positional hygiene implementation fails.

  Run:

  ```bash
  pytest -q tests/test_workflow_lisp_provider_call_policy.py -k 'traversal or macro or normalization'
  ```

  Expected: FAIL before the walkers are updated.

- [ ] **Step 6: Update shared traversal and keyword-aware rewrites**

  Append only present model/effort operands to provider-result children. Normalize
  them through the existing expression normalizer. In macro hygiene, locate keyword
  sections and rewrite provider, prompt, inputs, model, and effort by role rather
  than by fixed indices; do not rewrite the type-bearing return declaration or
  literal timeout into a value expression.

- [ ] **Step 7: Run the complete Task 2 selector**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_provider_call_policy.py \
    tests/test_workflow_lisp_expressions.py \
    tests/test_workflow_lisp_structured_results.py \
    tests/test_workflow_lisp_macros.py \
    tests/test_workflow_lisp_functions.py
  ```

  Expected: PASS.

- [ ] **Step 8: Re-run the keyword-free byte golden**

  ```bash
  pytest -q tests/test_workflow_lisp_provider_call_policy.py::test_keyword_free_provider_result_matches_pre_feature_golden_bytes
  ```

  Expected: PASS byte-for-byte; do not update the golden after production changes.

- [ ] **Step 9: Review and commit**

  Check the completed Task 2 boxes and update **Execution status**. Stage this plan,
  the five production files, and the focused test file; run both reviews and the
  protected-path guard, then commit the unchanged reviewed tree:

  ```bash
  git commit -m "feat: type provider call policy operands"
  ```

### Task 3: Preserve Policy Through WCC And One Shared Lowering Owner

**Files:**

- Modify: `docs/plans/2026-07-17-workflow-lisp-provider-call-policy-implementation-plan.md`
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `orchestrator/workflow_lisp/wcc/route.py`
- Modify: `orchestrator/workflow_lisp/lowering/effects.py`
- Create: `tests/fixtures/workflow_lisp/provider_call_policy/policy.orc`
- Create: `tests/fixtures/workflow_lisp/provider_call_policy/procedure_policy.orc`
- Modify: `tests/test_workflow_lisp_provider_call_policy.py`

- [ ] **Step 1: Write red WCC payload and reconstruction tests**

  Assert present model/effort values and timeout survive provider-result perform
  elaboration, nested let/match extraction, loop binding reconstruction, and
  defunctionalization. Assert absence remains absence. Cover WCC schema 2 and every
  still-supported compatibility route without adding a new WCC node type.

  Run:

  ```bash
  pytest -q tests/test_workflow_lisp_provider_call_policy.py -k 'wcc and (payload or reconstruct or preserve)'
  ```

  Expected: FAIL because operation payload carries only return guidance.

- [ ] **Step 2: Extend the WCC operation payload and all reconstruction sites**

  Store present model/effort as WCC atomic values and timeout as its validated
  literal payload. Update all three WCC route validators to visit present operands.
  Reconstruct optional fields in every `LowerableProviderResult` and
  `ProviderResultExpr` site in `defunctionalize.py`.

- [ ] **Step 3: Write red direct-versus-WCC lowering tests**

  Require exactly:

  ```json
  {
    "provider_call_policy": {
      "model": "${inputs.model}",
      "effort": "${inputs.effort}"
    },
    "timeout_sec": 7200
  }
  ```

  on the generated provider step, with one-key cases containing only the authored
  key and no empty mapping for no-keyword cases. Compare direct/compatibility and
  WCC provider-step payloads where both routes remain supported. Include a nested
  inline procedure plus loop/control fixture so procedure parameters resolve through
  the ordinary local-value path.

  Run:

  ```bash
  pytest -q tests/test_workflow_lisp_provider_call_policy.py -k 'lowering or direct_wcc or procedure_policy'
  ```

  Expected: FAIL because the lowerable payload has no policy.

- [ ] **Step 4: Extend the shared lowerable provider payload**

  Add optional operands only to `LowerableProviderResult`. Render literal Strings
  as literals and dynamic names/projections with the existing scalar template
  renderer. Insert canonical keys in `model`, then `effort` order. Put timeout only
  in the ordinary top-level `timeout_sec` field. Do not synthesize
  `provider_params`, defaults, a policy adapter step, or family/provider-name logic.

- [ ] **Step 5: Prove specialization uses the existing path**

  Compile `procedure_policy.orc` through public Stage 3 with a procedure parameter
  for each String operand. Assert the lowered templates point to the caller's bound
  inputs and that no new specialization table or hidden runtime value appears.

- [ ] **Step 6: Run WCC/lowering regressions**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_provider_call_policy.py \
    tests/test_workflow_lisp_wcc_m2.py \
    tests/test_workflow_lisp_wcc_m3.py \
    tests/test_workflow_lisp_wcc_m4.py \
    tests/test_workflow_lisp_wcc_m5.py \
    tests/test_workflow_lisp_lowering.py \
    tests/test_workflow_lisp_procedures.py
  ```

  Expected: PASS.

- [ ] **Step 7: Review and commit**

  Check the completed Task 3 boxes and update **Execution status**. Stage this plan,
  exactly the four production files, two new fixtures, and focused test file. Run
  both reviews and the protected-path guard, then commit the unchanged reviewed
  tree:

  ```bash
  git commit -m "feat: lower provider call policy through wcc"
  ```

### Task 4: Carry And Validate Policy Through Typed Workflow IR

**Files:**

- Modify: `docs/plans/2026-07-17-workflow-lisp-provider-call-policy-implementation-plan.md`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/runtime_step.py`
- Modify: `orchestrator/workflow/validation.py`
- Modify: `tests/test_workflow_lisp_provider_call_policy.py`
- Modify: `tests/test_workflow_shared_validation.py`
- Modify: `tests/test_workflow_ir_lowering.py`

- [ ] **Step 1: Write red typed-layer preservation tests**

  Compile `policy.orc` and assert the same closed mapping exists on `SurfaceStep`,
  `CoreProviderStep`, `ProviderStepConfig`, executable IR JSON, content-addressed
  Core/executable artifacts, and `RuntimeStep`. Assert timeout remains in common
  config at every existing layer.

  Run:

  ```bash
  pytest -q tests/test_workflow_lisp_provider_call_policy.py -k 'surface or core or executable or runtime_step'
  ```

  Expected: FAIL because typed provider configs do not carry policy.

- [ ] **Step 2: Add optional typed policy fields and propagation**

  Add `provider_call_policy: Mapping[str, str] | None = None` only to provider
  step/config records. Freeze it during elaboration, preserve it through Core
  reconstruction, and pass it through executable lowering. RuntimeStep must expose
  it only when non-empty; do not fall back to the looser existing
  `provider_params: Any` annotation for this closed typed contract.

- [ ] **Step 3: Write red closed-map validation tests**

  Through `validate_workflow_mapping`, reject empty maps, unknown keys, non-String
  literal/template values, nested values, and `timeout_sec` inside policy. Accept
  one or both canonical String entries only for `frontend_kind="workflow_lisp"`.
  Require ordinary YAML/YML requests to reject step-level
  `provider_call_policy`, even if otherwise well shaped. Require YAML provider
  definitions to reject `call_policy_bindings`.

  Run:

  ```bash
  pytest -q \
    tests/test_workflow_shared_validation.py \
    tests/test_workflow_lisp_provider_call_policy.py \
    -k 'provider_call_policy or yaml_reservation'
  ```

  Expected: FAIL before shared validation owns the distinction.

- [ ] **Step 4: Implement origin-aware shared validation**

  Retain `request.frontend_kind` in the request-scoped validator. Reject the
  internal step field unless it equals `workflow_lisp`; then validate the closed
  mapping before elaboration. Reject `call_policy_bindings` in YAML provider config
  unconditionally in v1. Add policy to variable validation only on the accepted
  compiler-generated route so unresolved runtime templates retain the existing
  substitution owner.

- [ ] **Step 5: Write red omission and canonical-order tests**

  Assert absent policy is `None` in typed records but omitted from Core and
  executable JSON rather than serialized as `null`. Build stable minimal Core and
  executable provider records with policy inserted in both source orders; serialize
  each to compact UTF-8 JSON bytes and compare the complete resulting bytes against
  explicit full expected byte strings whose policy segment is exactly
  `"provider_call_policy":{"model":"m","effort":"e"}`. A substring or decoded-map
  equality assertion is insufficient because it cannot prove the complete Core and
  executable serialization contract. Re-run the frozen keyword-free combined
  golden.

  In `tests/test_workflow_ir_lowering.py`, serialize an unrelated mapping field such
  as `depends_on` from reverse insertion order and assert its existing executable-IR
  bytes remain lexically ordered. This test must fail if implementation globally
  changes `_json_value` mapping order merely to make policy serialize model-first.

  Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_provider_call_policy.py \
    tests/test_workflow_ir_lowering.py \
    -k 'omit or canonical_order or keyword_free or unrelated_mapping_order'
  ```

  Expected: FAIL if absent policy is emitted, policy uses global lexical
  effort-before-model ordering, or the fix changes unrelated mapping ordering.

- [ ] **Step 6: Add a field-local policy serializer without changing global map order**

  In Core `_statement_to_json`, conditionally add `provider_call_policy` only when
  non-`None`, constructing a fresh dict by the closed canonical tuple
  `("model", "effort")` and including every present key. In executable IR, give only
  `ProviderStepConfig.provider_call_policy` metadata for `json_omit_if_none` plus a
  field-local serializer role/callable. Extend the dataclass branch of `_json_value`
  to honor those two metadata entries for that field; its serializer constructs the
  same canonical-order dict and fails closed on an unexpected key rather than
  dropping it.

  Do **not** change `_json_value`'s existing `Mapping` branch: it must continue
  lexically sorting every unrelated mapping, which would otherwise place `effort`
  before `model`. Do not globally omit `None`, change unrelated dataclass fields, or
  rewrite old artifact schemas.

- [ ] **Step 7: Prove unchanged non-authority projections and identity behavior**

  Assert runtime plan topology, persisted dashboard graph, Semantic IR schema, and
  source-map subjects do not gain policy fields. Compile sources differing in one
  literal, binding expression, added keyword, and removed keyword; assert source,
  build/program composite, and workflow-checksum identity changes through existing
  inputs without changing the identity algorithms.

- [ ] **Step 8: Run typed IR/build regressions**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_provider_call_policy.py \
    tests/test_workflow_shared_validation.py \
    tests/test_workflow_ir_lowering.py \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_workflow_lisp_runtime_source_map.py \
    tests/test_persisted_workflow_surface.py
  ```

  Expected: PASS, including the unchanged byte golden.

- [ ] **Step 9: Review and commit**

  Check the completed Task 4 boxes and update **Execution status**. Stage this plan,
  exactly the seven production files and three test files. Run both reviews and the
  protected-path guard, then commit the unchanged reviewed tree:

  ```bash
  git commit -m "feat: preserve provider policy in executable workflow"
  ```

### Task 5: Add Declarative Provider Bindings And Shared No-Default Profiles

**Files:**

- Modify: `docs/plans/2026-07-17-workflow-lisp-provider-call-policy-implementation-plan.md`
- Modify: `orchestrator/providers/types.py`
- Modify: `orchestrator/providers/registry.py`
- Modify: `orchestrator/providers/__init__.py`
- Create: `tests/test_provider_call_policy.py`
- Modify: `tests/test_provider_execution.py`

- [ ] **Step 1: Write red binding-schema tests**

  Cover the closed canonical keys, unique targets, bare identifier grammar,
  reserved runtime-context names, malformed/non-string fragments, and escaped
  placeholder handling. Direct bindings must consume exactly one unescaped target
  in every applicable command/fresh/resume variant. Fragment-backed bindings must
  consume zero in each base variant and exactly one matching target in the fragment,
  with no other dynamic placeholder.

  Include zero, duplicate, mismatched, extra, `${PROMPT}`, `${SESSION_ID}`, and
  context-placeholder negative cases. Separately characterize the shared general
  command-placeholder extractor: after escape processing it must preserve and
  return bare provider names plus existing dotted `${run.*}`, `${context.*}`,
  `${loop.*}`, and `${steps.*}` names. Those dotted names are valid general command
  placeholders even though they are invalid as a call-policy `target_param`.

  Run:

  ```bash
  pytest -q tests/test_provider_call_policy.py -k 'binding_validation or placeholder'
  ```

  Expected: FAIL because `ProviderTemplate` has no binding declaration.

- [ ] **Step 2: Add the shared general extractor, separate target validator, and binding dataclass**

  In `types.py`, add one general command-placeholder extractor that applies
  `escape_provider_command_token` and returns every unescaped `${...}` name without
  narrowing the existing command language. It must retain dotted run/context/loop/
  steps placeholders. Add a separate bare-provider-target predicate/validator for
  `CallPolicyBinding.target_param`; only that field uses the bare identifier grammar
  and reserved-name rejection. Use the general extractor for exact binding
  consumption counts and fragment validation. Keep canonical option order in one
  closed constant. Do not import the bare target validator into command execution or
  reinterpret all command placeholders as provider parameters.

- [ ] **Step 3: Write the red public construction test**

  Import both `CallPolicyBinding` and `ProviderTemplate` from
  `orchestrator.providers`, construct a custom public `ProviderTemplate` with a
  `CallPolicyBinding(target_param="effort", argv_fragment=["--effort",
  "${effort}"])`, and require template validation plus later registration to accept
  it. Assert `CallPolicyBinding` appears in `orchestrator.providers.__all__`. Do not
  use a private `orchestrator.providers.types` import or dict coercion in this test.

  ```bash
  pytest -q \
    tests/test_provider_call_policy.py::test_public_call_policy_binding_constructs_custom_template
  ```

  Expected: FAIL because the public package does not export the new dataclass.

- [ ] **Step 4: Export the explicit public dataclass API**

  Import `CallPolicyBinding` from `.types` in
  `orchestrator/providers/__init__.py` and add its name to `__all__`. Keep
  `ProviderTemplate.call_policy_bindings` typed as a mapping from canonical String
  key to `CallPolicyBinding`; v1 does not add undocumented dict-to-dataclass
  coercion. This is the supported programmatic custom-template construction
  contract.

- [ ] **Step 5: Write red registry validation tests**

  Require programmatic `register()` and built-in initialization to apply identical
  validation. Monkeypatch an invalid built-in declaration and assert registry
  construction fails closed. Confirm a provider with no declarations remains valid.

- [ ] **Step 6: Validate built-ins during registry initialization**

  Validate the dictionary returned by `_load_builtin_providers` before storing it.
  Do not route built-ins around `ProviderTemplate.validate()`.

- [ ] **Step 7: Write red built-in mapping/profile data tests**

  Require these declarations:

  - Codex built-ins: `model -> model`, `effort -> reasoning_effort` on existing
    base/fresh/resume placeholders.
  - Claude and both Claude summary built-ins: `model -> model`; `effort -> effort`
    with conditional `--effort ${effort}` fragment.
  - Gemini: no call-policy capability.
  - `codex_unrestricted_workspace`: no defaults, stdin, exact unrestricted
    workspace flags including `--dangerously-bypass-approvals-and-sandbox` and
    `--skip-git-repo-check`, direct model/reasoning-effort placeholders, canonical
    bindings.
  - `claude_unrestricted_workspace`: no defaults, stdin, exact
    `--permission-mode bypassPermissions`, direct model/effort placeholders,
    canonical bindings.

  The two profile names and their data are shared provider capabilities. Tests must
  not mention either survivor family.

  Run:

  ```bash
  pytest -q tests/test_provider_call_policy.py -k 'builtin or unrestricted_workspace or no_default'
  ```

  Expected: FAIL because declarations/profiles are absent.

- [ ] **Step 8: Add declarative built-in/profile data**

  Preserve all existing built-in defaults and keyword-free commands. Add Claude
  effort only as an optional fragment. Add the two unrestricted profiles with
  `defaults={}` so caller-authored policy is required rather than hidden in profile
  data.

- [ ] **Step 9: Run provider type/registry regressions**

  ```bash
  pytest -q \
    tests/test_provider_call_policy.py \
    tests/test_provider_execution.py::TestProviderRegistry
  ```

  Expected: PASS.

- [ ] **Step 10: Review and commit**

  Check the completed Task 5 boxes and update **Execution status**. Stage this plan,
  provider types, registry, the required public export, and the two test files.
  Run both reviews and the protected-path guard, then commit the unchanged reviewed
  tree:

  ```bash
  git commit -m "feat: declare provider call policy bindings"
  ```

### Task 6: Map Canonical Policy Through The Existing Provider Executor

**Files:**

- Modify: `docs/plans/2026-07-17-workflow-lisp-provider-call-policy-implementation-plan.md`
- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_provider_call_policy.py`
- Modify: `tests/test_workflow_lisp_provider_call_policy.py`
- Modify: `tests/test_provider_execution.py`

- [ ] **Step 1: Write red generic merge/substitution tests**

  Pass policy separately to `prepare_invocation`. Assert precedence is defaults <
  ordinary native step params < translated canonical overrides. Assert unrelated
  native params survive. Instrument `_substitute_params` and require exactly one
  call over the fully merged native mapping. Assert unresolved dynamic policy uses
  the existing single `substitution_error` shape.

  Run:

  ```bash
  pytest -q tests/test_provider_call_policy.py -k 'merge or one_pass or substitution_error'
  ```

  Expected: FAIL because the executor does not accept policy separately.

- [ ] **Step 2: Write red general-placeholder compatibility tests**

  Exercise `_build_command` through public preparation with provider parameters and
  runtime context containing representative dotted `${run.id}`,
  `${context.workspace}`, `${loop.item}`, and `${steps.prepare.output}` names, plus
  an escaped literal. Require the same substitution and missing-placeholder behavior
  as before this feature. This guards against accidentally applying the bare
  `target_param` grammar to the general command language.

  ```bash
  pytest -q tests/test_provider_call_policy.py tests/test_provider_execution.py \
    -k 'dotted_placeholder or escaped_placeholder'
  ```

  Expected: the legacy characterization cases PASS before executor edits; the new
  shared-extractor ownership assertion fails until `_build_command` imports it.

- [ ] **Step 3: Import the general extractor and implement canonical translation**

  Import the general placeholder extractor from `types.py` into `executor.py` and
  remove its private `r'\$\{([^}]+)\}'` parsing copy; do not import or apply the bare
  target validator there. Validate policy keys against the closed contract and
  selected template's binding map. Translate without substitution, merge once, call
  the existing `_substitute_params` once, select the actual command variant, append
  only present fragments in canonical order, and call the existing `_build_command`.
  When policy is absent, retain the exact old merge/selection/build route and all
  dotted context-placeholder behavior.

- [ ] **Step 4: Write red actual argv/session/custom capture tests**

  Assert actual prepared invocation argv for:

  - Codex base, fresh, and resume variants with authored model and effort mapped to
    native `reasoning_effort`;
  - Claude base with authored effort and without effort, proving conditional
    fragment presence/absence;
  - both Claude summary templates;
  - both no-default unrestricted profiles;
  - a programmatic custom fragment-backed provider across base/fresh/resume;
  - a custom provider with two optional fragments declared in reverse order,
    proving actual append order remains model then effort.

  Test commands/parameters, not prompt prose.

- [ ] **Step 5: Write red unsupported-provider and bounded-context tests**

  Use a provider lacking effort capability. Require
  `provider_call_policy_unsupported`, workflow exit `2`, and zero process/session
  launches. At the provider-executor boundary, require bounded error context to
  contain only the resolved provider ID and canonical option: no policy value,
  prompt, secret, step/form fields, or authored span. In a separate ordinary
  Workflow Lisp run assertion, prove the enclosing provider-result step/form
  provenance already remains available through the existing runtime/source-map
  path while no field-level policy provenance is claimed. Do not require the
  provider error mapping itself to manufacture or carry that provenance.

- [ ] **Step 6: Implement bounded failure before invocation creation**

  Return the existing executor error mapping with type
  `provider_call_policy_unsupported` and context containing exactly provider ID plus
  canonical option. Let the workflow executor retain its normal preparation-failure
  exit-2 conversion. Do not add or claim a new origin-remapping step, field-level
  provenance, or second process path; existing enclosing provenance is proved
  independently.

- [ ] **Step 7: Pass RuntimeStep policy separately from WorkflowExecutor**

  Keep ordinary `ProviderParams` construction unchanged and add
  `provider_call_policy=step.get("provider_call_policy")` to the one ordinary
  provider `prepare_invocation` call. Do not modify adjudicated-provider/session
  bindings that are outside v1.

- [ ] **Step 8: Prove YAML and legacy native-parameter compatibility**

  Run a YAML-local provider with ordinary `provider_params` and no internal policy;
  assert identical argv and unused-param behavior. Assert existing Codex native
  `reasoning_effort` default and explicit override behavior remains. Assert
  keyword-free built-in Claude argv has no effort fragment. Reassert dotted
  run/context/loop/steps placeholders and escaped literals through actual argv.

- [ ] **Step 9: Prove timeout remains the existing owner**

  Assert the literal compiled timeout reaches `ProviderInvocation.timeout_sec`.
  Re-run the existing elapsed-timeout exit-124 tests; do not implement timeout logic
  in policy translation.

  ```bash
  pytest -q \
    tests/test_provider_call_policy.py \
    tests/test_provider_execution.py::TestProviderExecutor::test_provider_timeout \
    tests/test_provider_execution.py::TestProviderExecutor::test_managed_invocation_timeout_terminates_process_tree
  ```

- [ ] **Step 10: Run the Task 6 focused regression set**

  ```bash
  pytest -q \
    tests/test_provider_call_policy.py \
    tests/test_provider_execution.py \
    tests/test_provider_integration.py \
    tests/test_at44_provider_params_nested.py \
    tests/test_at72_provider_state_persistence.py \
    tests/test_workflow_lisp_provider_call_policy.py \
    tests/test_workflow_executor_characterization.py
  ```

  Expected: PASS.

- [ ] **Step 11: Review and commit**

  Check the completed Task 6 boxes and update **Execution status**. Stage this plan,
  the two production files, and three test files. Run both reviews and the
  protected-path guard, then commit the unchanged reviewed tree:

  ```bash
  git commit -m "feat: map provider call policy at invocation"
  ```

### Task 7: Prove Public Compile, Run, Resume, And Drift Rejection

**Files:**

- Modify: `docs/plans/2026-07-17-workflow-lisp-provider-call-policy-implementation-plan.md`
- Create: `tests/test_workflow_lisp_provider_call_policy_e2e.py`
- Create: `tests/fixtures/workflow_lisp/provider_call_policy/finish.py`
- Create: `tests/fixtures/workflow_lisp/provider_call_policy/commands.json`
- Modify: `tests/fixtures/workflow_lisp/provider_call_policy/policy.orc`
- Modify: `tests/fixtures/workflow_lisp/provider_call_policy/providers.json`
- Modify: `tests/fixtures/workflow_lisp/provider_call_policy/prompts.json`

- [ ] **Step 1: Add the public E2E fixture**

  The workflow must accept root String model/effort inputs, name a compiler-known
  provider extern, author a positive literal timeout, return a validated structured
  provider result, then reach a deterministic command-result boundary that fails
  until a marker exists. The command writes only to the runtime-bound bundle path.

- [ ] **Step 2: Collect the new tests before running them**

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_provider_call_policy.py \
    tests/test_provider_call_policy.py \
    tests/test_workflow_lisp_provider_call_policy_e2e.py
  ```

  Expected: all intended node IDs collect with no import/fixture error.

- [ ] **Step 3: Write the red public compile/run acceptance test**

  Name the parameterized public test exactly
  `test_public_compile_run_resume_uses_call_policy`; its two cases are the shared
  Codex and Claude no-default profiles so later smoke selection cannot silently
  collect zero tests.

  Use `build_frontend_bundle` for public compilation and `run_workflow` for actual
  execution. Keep real `ProviderExecutor.prepare_invocation`; patch only process
  execution to capture the prepared invocation and write the declared bundle.
  Parameterize the compiler-known extern binding over
  `codex_unrestricted_workspace` and `claude_unrestricted_workspace`. Assert actual
  argv, bound model/effort, literal timeout, one normal provider invocation, normal
  bundle validation/commit, and the expected downstream interruption.

  Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_provider_call_policy_e2e.py::test_public_compile_run_resume_uses_call_policy
  ```

  Expected: both parameter cases collect and FAIL until the complete public path is
  wired; a zero-test selection is a failure, never a passing smoke.

- [ ] **Step 4: Make only fixture/test corrections needed by the public path**

  Do not add an E2E-only compiler, registry, or executor hook. Any production defect
  found here returns to the owning earlier task and must receive focused red/green
  coverage there before this task continues.

- [ ] **Step 5: Write the unchanged-policy resume test**

  After the provider boundary commits and the downstream command fails, create the
  marker and call public `resume_workflow` with the same run ID. Assert resume calls
  `build_frontend_bundle`, reuses persisted root inputs, selects the validated prior
  boundary through normal checkpoint logic, does not invoke the provider a second
  time, completes the command result, and commits the typed workflow result.

- [ ] **Step 6: Write both-direction drift tests**

  From equivalent interrupted runs, change one literal policy value, one binding
  expression, add one keyword, and remove one keyword. Public resume must reject each
  through normal source/build/program/checksum guards before provider/command launch.
  Preserve the run tree/state bytes except for already-authorized diagnostic state
  written by the existing resume contract. Do not bypass checksums to construct a
  passing case.

- [ ] **Step 7: Prove debug/projection data is not resume authority**

  Tamper with emitted debug YAML, runtime-plan display data, and source-map views
  while leaving authoritative source/state unchanged; unchanged resume still follows
  the existing authoritative rebuild/checkpoint route. Then tamper authoritative
  source policy and prove view files cannot make it pass.

- [ ] **Step 8: Run public E2E and resume regressions**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_provider_call_policy_e2e.py \
    tests/test_workflow_lisp_cli.py \
    tests/test_resume_command.py \
    tests/test_workflow_lisp_lexical_checkpoint_default_resume.py \
    tests/test_workflow_lisp_lexical_checkpoint_restore.py
  ```

  Expected: PASS.

- [ ] **Step 9: Review and commit**

  Check the completed Task 7 boxes and update **Execution status**. Stage this plan,
  exactly the E2E test and five fixture/profile files. Run both reviews and the
  protected-path guard, then commit the unchanged reviewed tree:

  ```bash
  git commit -m "test: prove provider call policy run and resume"
  ```

### Task 8: Run Focused, Broad, And Public Smoke Gates Before Closure Docs

**Files:**

- Modify: `docs/plans/2026-07-17-workflow-lisp-provider-call-policy-implementation-plan.md`
- Verify only: implementation and test files from Tasks 1-7

- [ ] **Step 1: Collect the exact public smoke node and focused feature set**

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_provider_call_policy_e2e.py::test_public_compile_run_resume_uses_call_policy
  pytest --collect-only -q \
    tests/test_workflow_lisp_provider_call_policy.py \
    tests/test_provider_call_policy.py \
    tests/test_workflow_lisp_provider_call_policy_e2e.py
  ```

  Expected: the named public smoke node collects both Codex and Claude parameter
  cases, and all intended feature tests collect with no import/fixture error. Zero
  collected tests is a hard failure.

- [ ] **Step 2: Run the complete focused feature set**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_provider_call_policy.py \
    tests/test_provider_call_policy.py \
    tests/test_workflow_lisp_provider_call_policy_e2e.py \
    tests/test_workflow_shared_validation.py \
    tests/test_provider_execution.py \
    tests/test_provider_integration.py \
    tests/test_at44_provider_params_nested.py \
    tests/test_at72_provider_state_persistence.py \
    tests/test_workflow_lisp_expressions.py \
    tests/test_workflow_lisp_structured_results.py \
    tests/test_workflow_lisp_wcc_m2.py \
    tests/test_workflow_lisp_wcc_m3.py \
    tests/test_workflow_lisp_wcc_m4.py \
    tests/test_workflow_lisp_wcc_m5.py \
    tests/test_workflow_lisp_lowering.py \
    tests/test_workflow_lisp_procedures.py \
    tests/test_workflow_ir_lowering.py \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_workflow_lisp_cli.py \
    tests/test_resume_command.py \
    tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

  Expected: PASS with the keyword-free byte golden unchanged and existing routing
  still unclosed.

- [ ] **Step 3: Run the exact public compile/run/resume smoke**

  Keep real `ProviderExecutor.prepare_invocation`, capture the actual
  `ProviderInvocation`, and let only the deterministic fake process writer replace
  external Codex/Claude binaries.

  ```bash
  pytest -q \
    tests/test_workflow_lisp_provider_call_policy_e2e.py::test_public_compile_run_resume_uses_call_policy
  ```

  Expected: both no-default profile cases PASS; pytest reports a nonzero case count.

- [ ] **Step 4: Launch the broad suite in persistent tmux**

  Use the `tmux` skill. The tested state is not merely `git write-tree`: it is the
  tuple `(HEAD, candidate index tree, protected-overlay manifest,
  allowed-untracked-plan manifest)`. The protected overlay is test-relevant because
  it includes a collected test and workflow. Every launch and poll block below is
  self-contained: it assigns literal `SOCKET`/`SESSION` values and reads expected
  identity from tmux session environment plus immutable attempt files. No shell
  variable is assumed to survive into a later tool call.

  Before launch, stage the complete intended candidate. In the initial Task 8 pass
  the Tasks 1-7 commits may leave the index equal to HEAD; in Task 9 reruns the
  corrected closure candidate must be fully staged. The only permitted unstaged
  tracked paths are the seven protected paths. The only permitted untracked paths
  are the two separately owned plan drafts named below; by Task 8 this implementation
  plan must already be tracked/staged, not treated as an exception.

  Run this self-contained launch block from repo root:

  ```bash
  set -euo pipefail
  SOCKET="${TMPDIR:-/tmp}/claude-tmux-sockets/provider-policy.sock"
  SESSION="provider-policy-broad"
  EVIDENCE_ROOT="${TMPDIR:-/tmp}/provider-policy-broad-evidence"
  PROTECTED_PATHS=(
    docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md
    docs/plans/2026-07-01-workflow-audit-tier-fixes.md
    docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md
    state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt
    tests/test_workflow_non_progress_step_back_demo.py
    workflows/examples/non_progress_step_back_demo.yaml
    workflows/library/prompts/workflow_step_back/diagnose_non_progress.md
  )
  ALLOWED_UNTRACKED_PLANS=(
    docs/plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-design.md
    docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md
  )
  mkdir -p "$(dirname "$SOCKET")" "$EVIDENCE_ROOT"
  git diff --cached --quiet -- "${PROTECTED_PATHS[@]}" || {
    echo "protected path staged in candidate" >&2
    exit 1
  }
  git diff --cached --quiet -- "${ALLOWED_UNTRACKED_PLANS[@]}" || {
    echo "separately owned plan staged in candidate" >&2
    exit 1
  }

  if tmux -S "$SOCKET" has-session -t "$SESSION" 2>/dev/null; then
    PRIOR_ENV="$(tmux -S "$SOCKET" show-environment -t "$SESSION" RUN_KEY)"
    test "${PRIOR_ENV%%=*}" = "RUN_KEY"
    PRIOR_KEY="${PRIOR_ENV#*=}"
    test -n "$PRIOR_KEY"
    tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":broad.0 -S -100000 \
      > "$EVIDENCE_ROOT/$PRIOR_KEY.pane.txt"
    PRIOR_STATE="$(tmux -S "$SOCKET" display-message -p \
      -t "$SESSION":broad.0 '#{pane_dead} #{pane_dead_status}')"
    printf 'run_key=%s\npane_state=%s\n' "$PRIOR_KEY" "$PRIOR_STATE" \
      > "$EVIDENCE_ROOT/$PRIOR_KEY.status.txt"
    test "${PRIOR_STATE%% *}" = "1" || {
      echo "refusing to replace live broad run: $PRIOR_STATE" >&2
      exit 1
    }
    tmux -S "$SOCKET" kill-server
  fi

  while IFS= read -r path; do
    allowed=false
    for expected in "${PROTECTED_PATHS[@]}"; do
      test "$path" = "$expected" && allowed=true
    done
    $allowed || { echo "unexpected unstaged path: $path" >&2; exit 1; }
  done < <(git diff --name-only | LC_ALL=C sort)
  while IFS= read -r path; do
    allowed=false
    for expected in "${ALLOWED_UNTRACKED_PLANS[@]}"; do
      test "$path" = "$expected" && allowed=true
    done
    $allowed || { echo "unexpected untracked path: $path" >&2; exit 1; }
  done < <(git ls-files --others --exclude-standard | LC_ALL=C sort)

  VERIFY_HEAD="$(git rev-parse HEAD)"
  VERIFY_TREE="$(git write-tree)"
  SNAPSHOT_DIR="$EVIDENCE_ROOT/snapshot.$$"
  mkdir -p "$SNAPSHOT_DIR"
  for path in "${PROTECTED_PATHS[@]}"; do
    status="$(git status --porcelain=v1 -- "$path" | cut -c1-2)"
    test -n "$status" || status="CLEAN"
    if test -f "$path"; then
      bytes_sha="$(sha256sum -- "$path" | awk '{print $1}')"
    else
      bytes_sha="MISSING"
    fi
    printf '%s\t%s\t%s\n' "$path" "$status" "$bytes_sha"
  done | LC_ALL=C sort > "$SNAPSHOT_DIR/protected.tsv"
  for path in "${ALLOWED_UNTRACKED_PLANS[@]}"; do
    if test -f "$path"; then
      status="$(git status --porcelain=v1 -- "$path" | cut -c1-2)"
      test -n "$status" || status="TRACKED"
      bytes_sha="$(sha256sum -- "$path" | awk '{print $1}')"
    else
      status="ABSENT"
      bytes_sha="MISSING"
    fi
    printf '%s\t%s\t%s\n' "$path" "$status" "$bytes_sha"
  done | LC_ALL=C sort > "$SNAPSHOT_DIR/allowed-untracked.tsv"
  PROTECTED_SHA="$(sha256sum "$SNAPSHOT_DIR/protected.tsv" | awk '{print $1}')"
  UNTRACKED_SHA="$(sha256sum "$SNAPSHOT_DIR/allowed-untracked.tsv" | awk '{print $1}')"
  BASE_KEY="${VERIFY_HEAD:0:12}-${VERIFY_TREE:0:12}-${PROTECTED_SHA:0:12}-${UNTRACKED_SHA:0:12}"
  ATTEMPT=1
  while test -e "$EVIDENCE_ROOT/$BASE_KEY-attempt-$ATTEMPT.identity.txt"; do
    ATTEMPT=$((ATTEMPT + 1))
  done
  RUN_KEY="$BASE_KEY-attempt-$ATTEMPT"
  mv "$SNAPSHOT_DIR/protected.tsv" "$EVIDENCE_ROOT/$RUN_KEY.protected.tsv"
  mv "$SNAPSHOT_DIR/allowed-untracked.tsv" "$EVIDENCE_ROOT/$RUN_KEY.allowed-untracked.tsv"
  rmdir "$SNAPSHOT_DIR"
  printf 'VERIFY_HEAD=%s\nVERIFY_TREE=%s\nPROTECTED_SHA=%s\nUNTRACKED_SHA=%s\nRUN_KEY=%s\n' \
    "$VERIFY_HEAD" "$VERIFY_TREE" "$PROTECTED_SHA" "$UNTRACKED_SHA" "$RUN_KEY" \
    > "$EVIDENCE_ROOT/$RUN_KEY.identity.txt"

  tmux -S "$SOCKET" new-session -d -s "$SESSION" -n broad -c "$PWD"
  tmux -S "$SOCKET" set-option -w -t "$SESSION":broad remain-on-exit on
  tmux -S "$SOCKET" set-environment -t "$SESSION" VERIFY_HEAD "$VERIFY_HEAD"
  tmux -S "$SOCKET" set-environment -t "$SESSION" VERIFY_TREE "$VERIFY_TREE"
  tmux -S "$SOCKET" set-environment -t "$SESSION" PROTECTED_SHA "$PROTECTED_SHA"
  tmux -S "$SOCKET" set-environment -t "$SESSION" UNTRACKED_SHA "$UNTRACKED_SHA"
  tmux -S "$SOCKET" set-environment -t "$SESSION" RUN_KEY "$RUN_KEY"
  BROAD_COMMAND="printf 'VERIFY_HEAD=%s\\nVERIFY_TREE=%s\\nPROTECTED_SHA=%s\\nUNTRACKED_SHA=%s\\nRUN_KEY=%s\\n' '$VERIFY_HEAD' '$VERIFY_TREE' '$PROTECTED_SHA' '$UNTRACKED_SHA' '$RUN_KEY'; exec pytest -q -n 16 --dist=worksteal"
  tmux -S "$SOCKET" send-keys -t "$SESSION":broad.0 -l -- "$BROAD_COMMAND"
  tmux -S "$SOCKET" send-keys -t "$SESSION":broad.0 Enter
  ```

  Poll at intervals under 60 seconds with this separate, self-contained block. It
  reloads expected identity from tmux, rejects any new overlay, regenerates both
  manifests, and compares them byte-for-byte with the attempt files before accepting
  pane status:

  ```bash
  set -euo pipefail
  SOCKET="${TMPDIR:-/tmp}/claude-tmux-sockets/provider-policy.sock"
  SESSION="provider-policy-broad"
  EVIDENCE_ROOT="${TMPDIR:-/tmp}/provider-policy-broad-evidence"
  PROTECTED_PATHS=(
    docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md
    docs/plans/2026-07-01-workflow-audit-tier-fixes.md
    docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md
    state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt
    tests/test_workflow_non_progress_step_back_demo.py
    workflows/examples/non_progress_step_back_demo.yaml
    workflows/library/prompts/workflow_step_back/diagnose_non_progress.md
  )
  ALLOWED_UNTRACKED_PLANS=(
    docs/plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-design.md
    docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md
  )
  read_tmux_env() {
    line="$(tmux -S "$SOCKET" show-environment -t "$SESSION" "$1")"
    test "${line%%=*}" = "$1"
    printf '%s\n' "${line#*=}"
  }
  VERIFY_HEAD="$(read_tmux_env VERIFY_HEAD)"
  VERIFY_TREE="$(read_tmux_env VERIFY_TREE)"
  PROTECTED_SHA="$(read_tmux_env PROTECTED_SHA)"
  UNTRACKED_SHA="$(read_tmux_env UNTRACKED_SHA)"
  RUN_KEY="$(read_tmux_env RUN_KEY)"
  test "$(git rev-parse HEAD)" = "$VERIFY_HEAD"
  test "$(git write-tree)" = "$VERIFY_TREE"

  while IFS= read -r path; do
    allowed=false
    for expected in "${PROTECTED_PATHS[@]}"; do
      test "$path" = "$expected" && allowed=true
    done
    $allowed || { echo "unexpected unstaged path: $path" >&2; exit 1; }
  done < <(git diff --name-only | LC_ALL=C sort)
  while IFS= read -r path; do
    allowed=false
    for expected in "${ALLOWED_UNTRACKED_PLANS[@]}"; do
      test "$path" = "$expected" && allowed=true
    done
    $allowed || { echo "unexpected untracked path: $path" >&2; exit 1; }
  done < <(git ls-files --others --exclude-standard | LC_ALL=C sort)

  CURRENT_DIR="$EVIDENCE_ROOT/current.$$"
  mkdir -p "$CURRENT_DIR"
  for path in "${PROTECTED_PATHS[@]}"; do
    status="$(git status --porcelain=v1 -- "$path" | cut -c1-2)"
    test -n "$status" || status="CLEAN"
    test -f "$path" && bytes_sha="$(sha256sum -- "$path" | awk '{print $1}')" || bytes_sha="MISSING"
    printf '%s\t%s\t%s\n' "$path" "$status" "$bytes_sha"
  done | LC_ALL=C sort > "$CURRENT_DIR/protected.tsv"
  for path in "${ALLOWED_UNTRACKED_PLANS[@]}"; do
    if test -f "$path"; then
      status="$(git status --porcelain=v1 -- "$path" | cut -c1-2)"
      test -n "$status" || status="TRACKED"
      bytes_sha="$(sha256sum -- "$path" | awk '{print $1}')"
    else
      status="ABSENT"
      bytes_sha="MISSING"
    fi
    printf '%s\t%s\t%s\n' "$path" "$status" "$bytes_sha"
  done | LC_ALL=C sort > "$CURRENT_DIR/allowed-untracked.tsv"
  test "$(sha256sum "$CURRENT_DIR/protected.tsv" | awk '{print $1}')" = "$PROTECTED_SHA"
  test "$(sha256sum "$CURRENT_DIR/allowed-untracked.tsv" | awk '{print $1}')" = "$UNTRACKED_SHA"
  cmp "$CURRENT_DIR/protected.tsv" "$EVIDENCE_ROOT/$RUN_KEY.protected.tsv"
  cmp "$CURRENT_DIR/allowed-untracked.tsv" "$EVIDENCE_ROOT/$RUN_KEY.allowed-untracked.tsv"
  rm "$CURRENT_DIR/protected.tsv" "$CURRENT_DIR/allowed-untracked.tsv"
  rmdir "$CURRENT_DIR"

  tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":broad.0 -S -100000 \
    | tee "$EVIDENCE_ROOT/$RUN_KEY.pane.txt"
  PANE_STATE="$(tmux -S "$SOCKET" display-message -p \
    -t "$SESSION":broad.0 '#{pane_dead} #{pane_dead_status}')"
  printf 'VERIFY_HEAD=%s\nVERIFY_TREE=%s\nPROTECTED_SHA=%s\nUNTRACKED_SHA=%s\nRUN_KEY=%s\nPANE_STATE=%s\n' \
    "$VERIFY_HEAD" "$VERIFY_TREE" "$PROTECTED_SHA" "$UNTRACKED_SHA" "$RUN_KEY" "$PANE_STATE" \
    | tee "$EVIDENCE_ROOT/$RUN_KEY.status.txt"
  ```

  Continue until `pane_dead` is `1`. Require `pane_dead_status` to be `0`, rerun the
  self-contained poll once after death, and save that final capture/status under the
  `RUN_KEY`. A live pane, missing session identity, changed HEAD/index, changed
  protected bytes/status, changed allowed-untracked manifest, unexpected overlay, or
  capture from another run key is not a pass.

  Task 9 corrections use the same launch block. It first captures the prior dead run
  under its persisted run key and kills only the dedicated socket, then snapshots
  the newly staged candidate plus current protected/allowed overlays. Every required
  broad rerun therefore carries its own exact tested-state identity.

- [ ] **Step 5: Record verification progress and commit only the plan update**

  Check the completed Task 8 gate boxes and set **Execution status** to “Tasks 1-8
  verified; closure docs not yet prepared.” Stage only this plan, run both task-level
  reviews and the protected-path guard, and commit the unchanged reviewed plan:

  ```bash
  git commit -m "test: verify provider call policy acceptance gates"
  ```

  Do not edit capability/gap/design status in this task and do not report the
  feature implemented yet.

### Task 9: Stage Closure Docs, Obtain Both Final Reviews, Then Commit Unchanged

**Files:**

- Modify: `docs/plans/2026-07-17-workflow-lisp-provider-call-policy-implementation-plan.md`
- Modify: `specs/providers.md`
- Modify: `specs/dsl.md`
- Modify: `specs/state.md`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/workflow_yaml_orc_gap_list.md`
- Modify: `docs/plans/2026-07-17-workflow-lisp-provider-call-policy-design.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [ ] **Step 1: Write red closure-routing assertions**

  Require the gap list to distinguish the proposed final closures:

  - `common.provider-call-policy`: typed model/effort/literal timeout with public
    compile/run/resume evidence; and
  - `common.provider-invocation-profile`: shared no-default unrestricted
    Codex/Claude provider data with exact argv/profile evidence.

  Require both rows to remain generic and state that family parity/promotion and
  YAML deletion remain pending.

  ```bash
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py \
    -k 'provider_call_policy or provider_invocation_profile'
  ```

  Expected: FAIL because the second row and closure wording are not present.

- [ ] **Step 2: Prepare normative and author-facing closure content**

  Update provider/DSL/state contracts with the closed canonical keys, declarative
  binding/fragment validation, general-versus-bare placeholder distinction, merge
  precedence, the public `CallPolicyBinding` dataclass construction/import contract,
  single substitution ownership, bounded unsupported-option failure, policy absence,
  YAML reservations, positive literal timeout, identity participation, and normal
  resume guards. Keep runtime plan, reports, debug YAML, and source maps
  non-authoritative. Update the frontend spec and drafting guide with exact grammar
  and one generic example; do not add survivor-family source or claim family parity.

- [ ] **Step 3: Prepare the final status/routing candidate after Task 8 is green**

  In the staged candidate, update the capability row and
  `common.provider-call-policy` to `implemented`, add the separate implemented
  `common.provider-invocation-profile` row, and replace the design's stale proposed
  status with the precise reviewed-implementation status that will be true only
  after Steps 6-8 complete. The staged text is a proposed closure, not a durable or
  user-facing implementation claim before review. Do not commit it, announce it as
  implemented, promote either survivor, or mark YAML deletable at this point.

- [ ] **Step 4: Run the closure consistency gates**

  ```bash
  rg -n "provider-call-policy-parity|provider-invocation-profile|common.provider-call-policy|common.provider-invocation-profile|codex_unrestricted_workspace|claude_unrestricted_workspace" \
    docs specs tests orchestrator/providers
  pytest -q \
    tests/test_workflow_lisp_drain_roadmap_routing.py \
    tests/test_workflow_lisp_provider_call_policy.py \
    tests/test_provider_call_policy.py \
    tests/test_workflow_lisp_provider_call_policy_e2e.py
  ```

  Expected: the concept footprint is coherent and all tests PASS. Classify old
  “provider-result has no policy” wording as `stale_duplicate`; retain only wording
  explicitly labeled historical. Keep the generic implementation closure distinct
  from family promotion/deletion status.

- [ ] **Step 5: Update plan progress and stage the complete closure candidate**

  Check Task 9 Steps 1-4 and the applicable final checklist items. Set
  **Execution status** to “Closure candidate staged; completion conditional on two
  final approvals and byte-identical commit.” Stage exactly this plan, the eight
  docs/specs, and the routing test. Run the protected-path guard and record:

  ```bash
  git diff --cached --check
  git diff --cached --name-only
  git write-tree
  ```

  Re-run Task 8 Step 4's launch/poll protocol once against this exact fully staged
  closure tree, even though the pre-doc broad gate already passed. This confirming
  run exists to bind final review to the exact candidate plus disclosed overlays;
  it does not move closure docs before the required pre-doc gates.

  Supply the staged tree ID, Task 8 focused/smoke output, and this confirming broad
  `RUN_KEY`, exact HEAD/tree, protected-overlay manifest/digest,
  allowed-untracked-plan manifest/digest, pane capture, and dead status to each
  reviewer. Describe the broad-tested state as “candidate index tree plus the two
  disclosed overlay manifests,” never as a clean tree. From this point, any staged
  tree or manifest change invalidates every prior final verdict.

- [ ] **Step 6: Obtain final independent specification approval of the staged tree**

  Give a fresh reviewer the approved design, this plan, exact staged tree ID,
  tree-bound overlay manifests, and gate outputs without conversation history.
  Require explicit verdicts for
  syntax/type diagnostic ordering, direct/transitive effect handling with procedure
  edges allowed, WCC/direct equivalence, keyword-free bytes, YAML reservation,
  general/bare placeholder separation, declarative mapping, one-pass substitution,
  actual argv, bounded error context versus existing enclosing provenance, public
  resume both directions, and closure claim boundaries.

- [ ] **Step 7: Obtain final independent implementation-quality approval of the same staged tree**

  Use a different reviewer and the identical staged tree ID and overlay manifest
  digests. Require explicit checks for narrowed dotted placeholders,
  provider/family-name branches, duplicate
  substitution/executor paths, secret-bearing errors, invented origin remapping,
  global serializer drift, unused abstractions, brittle prompt assertions, tmux
  evidence, and protected-path contamination.

  If either reviewer requests any change, unstage the closure candidate as needed,
  fix it in the owning task, rerun affected narrow tests plus Task 8 focused/public
  gates when production or shared tests changed, update and restage this plan, and
  record a new `git write-tree`. Because every staged change creates a new candidate
  tree, rerun the Task 8 broad launch/poll protocol even for docs/plan-only fixes,
  then restart **both** final reviews on that same new tree and overlay identity.

- [ ] **Step 8: Commit the byte-identical reviewed closure tree**

  Re-run `git write-tree` and require exact equality with the tree ID approved by
  both reviewers. Immediately rerun Task 8's self-contained dead-pane poll block and
  require the same HEAD, `RUN_KEY`, protected-overlay manifest, allowed-untracked
  manifest, and successful pane status approved by both reviewers. Do not edit
  checkboxes, status prose, docs, code, or tests after
  the final verdicts; the conditional staged status becomes true by the approvals
  plus this unchanged commit, avoiding a self-invalidating post-review plan edit.
  Run the protected-path guard, then:

  ```bash
  git commit -m "docs: close provider call policy parity"
  ```

  Record commit/tree IDs and both verdicts in the execution handoff. Kill the tmux
  server only after its final capture:

  ```bash
  set -euo pipefail
  SOCKET="${TMPDIR:-/tmp}/claude-tmux-sockets/provider-policy.sock"
  SESSION="provider-policy-broad"
  FINAL_STATE="$(tmux -S "$SOCKET" display-message -p \
    -t "$SESSION":broad.0 '#{pane_dead} #{pane_dead_status}')"
  test "$FINAL_STATE" = "1 0"
  tmux -S "$SOCKET" kill-server
  git status --short
  ```

  Expected: the committed tree is byte-identical to both reviewed staged trees. Only
  generic provider-call-policy and provider-invocation-profile capability are
  closed; survivor parity, promotion, and YAML deletion remain pending.

## Final Acceptance Checklist

- [ ] Parser accepts exactly the three optional keywords and rejects malformed,
  duplicate, and unknown keywords with stable diagnostics.
- [ ] Model/effort type diagnostics precede inline-subset diagnostics; accepted
  operands are exact String with empty direct/transitive effects, while procedure
  edges alone remain allowed. Timeout is a positive Int literal only.
- [ ] Traversal, macro hygiene, procedure specialization, WCC, and all lowering
  routes preserve presence and absence.
- [ ] Canonical policy reaches Surface/Core/Executable/RuntimeStep and timeout stays
  on the existing common field.
- [ ] Core and executable bytes omit absent policy and emit present policy as model
  then effort through a field-local serializer; unrelated executable mappings retain
  their existing lexical ordering.
- [ ] Keyword-free bytes match the pre-feature golden exactly; no new `null` appears.
- [ ] YAML reserves both internal step policy and provider binding declarations.
- [ ] Provider binding declarations validate exact placeholder consumption after
  escape processing; a shared general extractor preserves dotted runtime/context
  placeholders while only `target_param` uses the separate bare-name validator.
- [ ] `CallPolicyBinding` is exported from `orchestrator.providers.__all__`, and a
  public-import custom `ProviderTemplate` construction/registration test passes.
- [ ] Both shared no-default unrestricted provider profiles exist and their actual
  argv matches the retained YAML operational flags.
- [ ] Runtime performs one merge, one substitution pass, one existing command build,
  and no provider/family compiler branch.
- [ ] Unsupported canonical options fail before process/session creation with bounded
  context; unresolved values retain `substitution_error`; timeout retains exit 124.
- [ ] Public compile/run/resume proves unchanged reuse and changed-policy rejection
  through normal guards.
- [ ] Runtime plan, Semantic IR field schema, source-map subject schema, dashboard
  graph, reports, and debug YAML remain non-authoritative.
- [ ] Focused, broad, and named public smoke gates pass before closure docs; the
  persistent tmux pane records dead status `0` plus exact HEAD/index tree and
  normalized byte-exact protected/allowed-untracked manifests, no undisclosed
  overlay exists, deterministic cleanup permits state-bound reruns, and both final
  reviewers approve the exact staged closure candidate and overlay identity before
  the candidate is committed byte-identically.
- [ ] Gap/capability docs close only generic policy and invocation-profile support;
  survivor family promotion and YAML deletion remain pending their own gates.
