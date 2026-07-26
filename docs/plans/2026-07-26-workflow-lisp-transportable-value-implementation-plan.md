# Workflow Lisp Transportable `Value` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to execute this plan task by task.
> Every behavior change uses `superpowers:test-driven-development`. Every task
> receives an independent specification-compliance review followed by a
> distinct implementation-quality review before its commit. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the accepted target-2.19 opt-in `Value` transport contract
through Workflow Lisp typechecking, generated contracts, strict runtime
validation, state/resume, classic and WCC execution, and public documentation.

**Architecture:** Install `Value` as a target-gated primitive type whose source
compatibility remains exact, then lower it through the existing direct-root
`__result__` output-bundle carriage with `type: value` and public
`kind: value`. Extend the shared output-contract validator with one recursive
strict-JSON path and teach existing descriptor consumers to pass that kind
opaquely; do not add a second value store, an envelope, coercion, inspection,
or payload-shape specialization.

**Tech Stack:** Python 3.11+, immutable Workflow Lisp AST/type references,
Workflow Lisp target DSL 2.19, Core/Executable/runtime-plan v1, canonical JSON,
state schema 2.1, classic and WCC lowering, pytest/pytest-xdist.

**Accepted design:** `docs/design/workflow_lisp_transportable_value_type.md` at
commit `c35ccf1b2f73c56d0bc8ee9f5d7fc94759ce7b5f`, tree
`b51d67568bdc59ade2d5e3628a5f39f4ffaa98ec`, content digest
`sha256:9f1ba1899bbefa9a71cf8343c5e8e16aaa6f9b9d9c6a80e02e69394966efc0a8`.
That commit records ordered `VALUE_DESIGN_SPEC_APPROVED` /
`VALUE_DESIGN_QUALITY_APPROVED` and the selected successor roadmap.

**Status:** Accepted implementation plan; implementation pending. Ordered plan
review completed with `VALUE_Q0_PLAN_SPEC_APPROVED` then
`VALUE_Q0_PLAN_QUALITY_APPROVED`. No Q0 implementation code began before this
gate.

---

## Scope And Deliberate Cost

This plan implements only:

- the compiler-owned `Value` name at target 2.19 and later;
- exact `Value`-to-`Value` compatibility, with no implicit conversion in
  either direction;
- recursive strict-JSON transport validation;
- direct-root `type: value` output-bundle carriage and public
  `kind: value`;
- `Value` in every position already governed by the shared transportability
  predicate, including nested `Optional`, `List`, and string-keyed `Map`;
- description and format-hint result guidance, with `:example` rejected by
  `value_guidance_example_unsupported`;
- propagation through current input, artifact, state, resume, prompt-input,
  build/debug, classic, and WCC paths; and
- one deterministic provider-to-procedure-to-public-workflow integration,
  including interruption/resume without provider re-execution.

Do not widen `Json`, add a `Value` literal/constructor, infer payload types,
project fields, cast or narrow dynamically, create a JSON union taxonomy, add
an envelope, add nominal wrapper types, change existing record/union
flattening, or implement `defprompt`.

The direct exact-type approach makes future implicit erasure from narrower
types and checked narrowing back out of `Value` harder: either would require a
separate rematerialization/decoder design with explicit artifact and failure
semantics. Opaque `Value` also deliberately makes field inspection and
typecase impossible in this tranche. Those costs are accepted to preserve
Principle 29 and the current artifact identity model.

## Governing Authorities

Read before implementation:

- `AGENTS.md`
- `docs/index.md`
- `docs/capability_status_matrix.md`
- `docs/design/README.md`
- `docs/design/workflow_lisp_transportable_value_type.md`
- `docs/design/workflow_language_design_principles.md`, especially principle
  29
- `docs/design/workflow_lisp_native_transportable_returns.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_lexical_execution_checkpoints.md`
- `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/providers.md`
- `specs/versioning.md`

If this plan conflicts with the accepted design, correct the plan and repeat
its ordered reviews. Do not reinterpret the design in code.

## Execution Contract

Run every command from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do not create a worktree. Preserve all pre-existing user or external changes.
Stage exact task-owned paths only; never use `git add .`, `git add -A`,
destructive checkout/reset, or broad cleanup.

For every task:

1. add the smallest behavioral or contract test;
2. run it and confirm RED for the intended missing behavior;
3. implement only the selected behavior;
4. rerun the narrow selector;
5. run adjacent regression selectors;
6. run `pytest --collect-only -q` for a new or renamed test module;
7. update this plan with fresh verification and truthful `reviews pending`
   status;
8. dispatch a fresh specification reviewer against the accepted design and
   exact task diff;
9. resolve findings and repeat specification review until approved;
10. dispatch a distinct implementation-quality reviewer against the
    spec-approved exact diff;
11. resolve findings and repeat the ordered reviews until quality approval;
12. record both factual verdicts and `commit pending`, then ask the same two
    reviewers to reaffirm the final exact diff in specification-then-quality
    order;
13. stage exact paths, run `git diff --cached --check`, inspect staged names
    and content, and commit the reaffirmed bytes; and
14. update only this plan with the factual implementation commit and make a
    separate plan-only bookkeeping commit.

Do not make an empty implementation commit when a propagation or consumer
test passes without production changes; record the no-change result in this
plan and include it in the next task's reviewed commit.

Use the `tmux` skill for the closing broad suite and any integration selector
that exceeds one minute. Keep the installed/default provider and model; wait
instead of substituting a faster model.

Security and provider-isolation work are outside Q0. Do not edit, test, review,
or claim those surfaces. The closing broad command is:

```bash
pytest -q -n 16 --dist=worksteal \
  --ignore=tests/test_at61_at62_wait_for_path_safety.py \
  --ignore=tests/test_cli_safety.py \
  --ignore=tests/test_execution_safety.py \
  --ignore=tests/test_provider_isolation_policy.py \
  --ignore=tests/test_provider_isolation_schema_resources.py \
  --ignore=tests/test_provider_isolation_environment.py \
  --ignore=tests/test_provider_isolation_environment_cli.py \
  --ignore=tests/test_provider_isolation_backend.py \
  --ignore=tests/test_provider_isolation_candidate.py \
  --ignore=tests/test_provider_isolation_network_preflight.py \
  --ignore=tests/test_provider_isolation_runtime_authority.py \
  --ignore=tests/test_provider_launch_shim.py \
  --ignore=tests/test_secrets.py \
  -k 'not security and not secret and not isolation'
```

## Protected Working Tree

At plan creation, the following paths or families contain owner/external work
and are outside Q0. Do not edit, restore, stage, or commit them:

```text
docs/index.md
  # except exact Q0 status/routing hunks, staged without the owner Evolution hunk
docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md
docs/plans/2026-07-01-workflow-audit-tier-fixes.md
docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md
docs/superpowers/plans/2026-07-23-provider-phase-information-isolation.md
docs/superpowers/specs/2026-07-22-workflow-lisp-evolution-substrate-and-feature-design.md
docs/superpowers/specs/2026-07-23-provider-phase-information-isolation-design.md
orchestrator/providers/
orchestrator/state.py
orchestrator/workflow/call_frame_state.py
orchestrator/workflow/executor_runtime.py
orchestrator/workflow/prompt_dependency_evidence.py
orchestrator/workflow/provider_attempts.py
state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt
tests/test_prompt_dependency_evidence.py
tests/test_provider_attempt_allocation.py
tests/test_provider_isolation_*.py
workflows/library/prompts/workflow_step_back/diagnose_non_progress.md
```

If a RED test proves a protected non-security runtime owner is load-bearing,
pause that task's edits, record the exact collision in this plan, and route
the behavior through an unmodified public seam if possible. Do not overwrite
the external edit.

## File And Responsibility Map

Target/type identity and guidance:

- `orchestrator/workflow_lisp/syntax.py` — target 2.19 support and target
  feature predicate.
- `orchestrator/workflow_lisp/type_env.py` — conditional prelude installation,
  shadowing refusal, exact primitive identity.
- `orchestrator/workflow_lisp/diagnostics.py` — closed diagnostic-code
  registration, if required by the existing catalog.
- `orchestrator/workflow_lisp/result_guidance.py` — the Value-specific
  `:example` refusal before ordinary constant evaluation.

Contract generation and loader:

- `orchestrator/workflow_lisp/contracts.py` — shared transportability,
  `type: value`, `kind: value`, nested collection descriptors, and
  fingerprints.
- `orchestrator/workflow/validation.py` — DSL 2.19 plus version-gated
  `type: value` / `kind: value` validation for workflow boundaries,
  artifacts, and output-bundle fields, including imported-guidance refusal.

Runtime contract:

- `orchestrator/contracts/output_contract.py` — strict JSON loading and
  recursive in-memory Value validation with first-invalid-path diagnostics.
- `orchestrator/contracts/prompt_contract.py` — expected no-change consumer;
  contract rendering must be proven generic and direct-root.

Descriptor consumers found by the required switch scan:

- `orchestrator/workflow/dataflow.py` — pass and validate `kind: value`
  consumes without scalar/collection specialization.
- `orchestrator/workflow/executor.py` — root pure-result materialization;
  change only if a RED test proves the scalar/collection split drops Value.
- `orchestrator/workflow_lisp/lexical_checkpoint_restore.py` — retain declared
  `Value` identity without payload specialization.
- `orchestrator/workflow_lisp/lowering/phase_scope.py` — preserve Value in
  workflow surface projections and typed prompt-input eligibility.
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py` — preserve Value in
  structured-field-to-surface projection.
- `orchestrator/workflow/provider_supervision/contracts.py` and
  `orchestrator/workflow/provider_supervision/bindings.py` — expected
  no-change output-bundle consumers; prove generic iteration/validation.
- `orchestrator/workflow/adjudication/evidence.py`,
  `orchestrator/workflow/adjudication/promotion.py`, and
  `orchestrator/workflow/adjudication_helpers.py` — expected no-change
  bundle/pointer consumers; prove empty-root handling.
- `orchestrator/dashboard/server.py`,
  `orchestrator/dashboard/projection.py`, and state/report projections —
  expected no-change value displays; prove mixed JSON survives.
- `orchestrator/workflow/signatures.py`,
  `orchestrator/workflow/surface_ast.py`,
  `orchestrator/workflow/core_ast.py`,
  `orchestrator/workflow/semantic_ir.py`,
  `orchestrator/workflow/executable_ir.py`,
  `orchestrator/workflow/runtime_plan.py`, and
  `orchestrator/workflow/persisted_surface.py` — expected no-change generic
  contract/value carriers; test first and do not edit absent RED evidence.

Classic and WCC lowering:

- `orchestrator/workflow_lisp/lowering/core.py`
- `orchestrator/workflow_lisp/lowering/pure_projection.py`
- `orchestrator/workflow_lisp/lowering/phase_scope.py`
- `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- `orchestrator/workflow_lisp/build.py`

Focused verification:

- Create `tests/test_workflow_lisp_transportable_value.py` for target,
  typing, lowering, loader, guidance, classic/WCC, and consumer-switch
  matrices.
- Create `tests/test_output_contract_value.py` for strict JSON and recursive
  runtime validation.
- Create
  `tests/fixtures/workflow_lisp/valid/transportable_value_provider_resume.orc`
  and `tests/test_workflow_lisp_transportable_value_e2e.py` for the real
  compile/run/resume path.
- Reuse adjacent tests named in the tasks below; do not duplicate their
  harnesses.

---

### Task 1: Add target-gated exact `Value` type identity and guidance refusal

**Files:**

- Modify: `orchestrator/workflow_lisp/syntax.py`
- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py` if its catalog is closed
- Modify: `orchestrator/workflow_lisp/result_guidance.py`
- Create: `tests/test_workflow_lisp_transportable_value.py`
- Test: `tests/test_workflow_lisp_workflows.py`
- Test: `tests/test_workflow_lisp_structured_results.py`
- Test: `tests/test_workflow_lisp_result_guidance_e2e.py`

**Task 1 status:** Complete at implementation commit `4379f0f5`.

**Task 1 preliminary reviews:** `VALUE_Q0_TASK1_SPEC_APPROVED`, then
`VALUE_Q0_TASK1_QUALITY_APPROVED`.

**Task 1 final exact-byte reviews:** `VALUE_Q0_TASK1_SPEC_REAFFIRMED`, then
`VALUE_Q0_TASK1_QUALITY_REAFFIRMED`.

**Changed paths:**

- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/result_guidance.py`
- `tests/test_workflow_lisp_transportable_value.py`
- `tests/test_workflow_lisp_list_traversal.py` — advanced the unknown-future
  target sentinel from newly supported `2.19` to unsupported `2.20`; no list
  behavior changed.

**Fresh TDD and verification evidence:**

- collection: `33 tests collected`;
- intended RED after correcting the list-operator harness target context:
  `12 failed, 21 passed`; failures were the absent target constant/predicate,
  target-2.19 rejection, pre-2.19 generic `type_unknown`, missing all-target
  `Value` reservation, and ordinary guidance evaluation occurring before the
  required `Value` refusal;
- focused GREEN: `33 passed`;
- exact Task-1 adjacent selector: `75 passed, 145 deselected`;
- unfiltered adjacent frontend/guidance set: `220 passed`;
- closing target-sentinel plus full Value module: `34 passed`.

- [x] **Step 1: Write failing target, shadowing, and exact-typing tests**

Add table-driven tests proving:

```python
assert syntax.VALUE_MIN_TARGET_DSL_VERSION == "2.19"
assert "Value" not in prelude_type_names_for_target("2.18")
assert "Value" in prelude_type_names_for_target("2.19")
assert type_refs_compatible(
    PrimitiveTypeRef(name="Value"),
    PrimitiveTypeRef(name="Value"),
)
assert not type_refs_compatible(
    PrimitiveTypeRef(name="Value"),
    PrimitiveTypeRef(name="Bool"),
)
assert not type_refs_compatible(
    PrimitiveTypeRef(name="Bool"),
    PrimitiveTypeRef(name="Value"),
)
```

Compile representative target-2.18 and target-2.19 occurrences so the older
target fails at the authored type with `value_type_requires_dsl_2_19`, local
and imported definitions cannot shadow `Value`, and ordinary typechecking
rejects narrower scalar/path/record/union/optional/list/map values in a
`Value` position and the reverse direction with existing `type_mismatch`.

Add operation-specific negative cases proving a `Value` cannot serve as a
Bool condition, match/variant subject, field projection receiver, rooted path,
numeric operand, or narrower list/collection operand. Assert the existing
operation-owned diagnostic in each case; do not introduce one generic dynamic
Value-operation error that erases the violated rule.

Add a result-guidance test proving description and format hint remain valid
while `(result Value :example ...)` fails with
`value_guidance_example_unsupported` before constant-expression evaluation.

- [x] **Step 2: Run RED and collection checks**

```bash
pytest --collect-only -q tests/test_workflow_lisp_transportable_value.py
pytest -q tests/test_workflow_lisp_transportable_value.py \
  -k 'target or shadow or compatibility or guidance'
```

Expected: collection succeeds; behavioral tests fail because target 2.19 and
`Value` are unknown.

- [x] **Step 3: Implement the minimal target/type/guidance surface**

Add `"2.19"` to the validated target set, define
`VALUE_MIN_TARGET_DSL_VERSION` and `target_dsl_supports_value`, and install
`Value` only through `prelude_type_names_for_target`. Keep
`PRELUDE_PRIMITIVE_TYPE_NAMES` for always-present primitives rather than
making `Value` resolvable to older targets. Reserve the compiler-owned name
for local/import shadow checks at every target while resolving an otherwise
authored pre-2.19 occurrence to the required version diagnostic. Preserve
exact `PrimitiveTypeRef` compatibility.

Reject a guidance example when the resolved expected type is exactly
`PrimitiveTypeRef(name="Value")`; do not add a Value constant evaluator.

- [x] **Step 4: Run focused and adjacent suites**

```bash
pytest -q tests/test_workflow_lisp_transportable_value.py \
  tests/test_workflow_lisp_workflows.py \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_result_guidance_e2e.py \
  -k 'value or target_dsl or shadow or guidance or compatibility'
```

Expected: PASS; existing `Json` refusals remain unchanged.

- [x] **Step 5: Complete ordered reviews and commit — `4379f0f5`**

Expected implementation commit subject:

```text
Add target-gated Workflow Lisp Value type
```

### Task 2: Derive and load `type: value` / `kind: value` contracts

**Status:** implementation and unfiltered adjacent verification complete;
preliminary ordered reviews approved; final exact-byte reaffirmations pending;
implementation commit pending.

**Preliminary reviews:** `VALUE_Q0_TASK2_SPEC_APPROVED`, then
`VALUE_Q0_TASK2_QUALITY_APPROVED`.

**Changed paths:**

- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow/validation.py`
- `tests/test_workflow_lisp_transportable_value.py`

**TDD evidence:**

- first RED slice: 3 failed, covering direct-root `type: value`, public
  `kind: value`, and the coded target-2.19 loader gate;
- second RED slice: 3 failed and 1 characterization passed, covering nested
  descriptors, all loader surfaces, literal fingerprint identity, and retained
  nontransportability for `Json`, capabilities, and refs;
- closure RED: `kind: value` initially admitted enum-only `allowed`, and the
  first classic-route pass-through probe exposed the existing Stage-3
  pure-name export limitation; the bounded source-level proof therefore uses
  the WCC route, while direct provider-result and command-result return
  typechecking covers both effect forms; a final two-case loader RED proved
  direct and nested Value guidance examples lacked the required early coded
  refusal before schema/runtime validation;
- specification-finding RED: the seven-row narrower-schema-key matrix produced
  6 failures and 1 existing pass, proving exact `type: value` still admitted
  `under`, `must_exist_target`, `item`, `items`, `keys`, and `values`; the
  shared schema validator now rejects all seven narrower-family keys;
- GREEN: 51 passed in the full Value module; 461 passed across the unfiltered
  Value, structured-result, workflow, and loader modules.

**Files:**

- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow/validation.py`
- Modify: `tests/test_workflow_lisp_transportable_value.py`
- Test: `tests/test_workflow_lisp_structured_results.py`
- Test: `tests/test_workflow_lisp_workflows.py`
- Test: `tests/test_loader_validation.py`

- [x] **Step 1: Write failing transportability and contract-shape tests**

Assert an exact root contract:

```python
assert contract.contract_kind == "output_bundle"
assert len(contract.payload["fields"]) == 1
field = contract.payload["fields"][0]
assert {
    "name": field["name"],
    "json_pointer": field["json_pointer"],
    "type": field["type"],
} == {"name": "__result__", "json_pointer": "", "type": "value"}
assert field["source_map_subject"]["subject_kind"] == "output_bundle_field"
assert field["source_map_subject"]["subject_name"].endswith(
    "::root-result::__result__"
)
assert workflow_output["__result__"]["kind"] == "value"
assert workflow_output["__result__"]["type"] == "value"
```

Cover provider, command, procedure, workflow-call, public workflow, record and
union fields, `Optional[Value]`, `List[Value]`, and
`Map[String, Value]`. Continue to reject `Json`, capabilities, refs, and
closures.

Add both-direction loader cases:

- 2.18 rejects authored/imported `type: value` and `kind: value` with
  `value_contract_requires_dsl_2_19`;
- 2.19 accepts the descriptor in inputs, outputs, artifacts, and
  output-bundle fields;
- legacy file-backed `expected_outputs` continues to reject `value`; Q0 uses
  structured output bundles for direct JSON roots;
- `kind: scalar` plus `type: value` and `kind: value` plus a narrower type are
  rejected; and
- the `value` descriptor participates literally in canonical contract
  fingerprints and checkpoint identity.

- [x] **Step 2: Run RED selectors**

```bash
pytest -q tests/test_workflow_lisp_transportable_value.py \
  tests/test_loader_validation.py \
  -k 'contract or loader or nested or fingerprint'
```

Expected: FAIL because `value` is not a supported descriptor or contract kind.

- [x] **Step 3: Implement one shared descriptor derivation**

Teach `_field_contract_definition`,
`_structured_result_field_definition`,
`_workflow_boundary_contract_definition`, and
`_workflow_boundary_contract_from_structured_field` to preserve exact
`Value` as `{"type": "value"}` and classify it only as `kind: value`.
Do not classify by a runtime payload.

Extend workflow validation version support to 2.19. Add `value` to supported
output types only at 2.19+, admit `kind: value` only with `type: value`, and
forbid path/collection-only descriptor keys. Emit the coded version refusal
rather than a generic invalid-kind error when a pre-2.19 contract uses it.
Audit the imported-guidance validation path so an imported Value example
receives the same `value_guidance_example_unsupported` refusal rather than
being accepted as an arbitrary JSON example.

- [x] **Step 4: Run contract and loader regressions**

```bash
pytest -q tests/test_workflow_lisp_transportable_value.py \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_workflows.py \
  tests/test_loader_validation.py \
  -k 'value or output or artifact or boundary or fingerprint'
```

Expected: PASS, including unchanged narrower descriptor behavior.

- [ ] **Step 5: Complete ordered reviews and commit — reviews pending**

Expected implementation commit subject:

```text
Lower Value through direct-root contracts
```

### Task 3: Validate strict recursive JSON values

**Files:**

- Modify: `orchestrator/contracts/output_contract.py`
- Create: `tests/test_output_contract_value.py`
- Test: `tests/test_output_contract.py`
- Test: `tests/test_output_contract_collections.py`

- [ ] **Step 1: Write failing file-backed and in-memory validation tests**

Parameterize direct-root success over `null`, booleans, integers, finite
floats, strings, lists, objects, and a nested mixed object. Assert exact Python
value/type preservation, including that booleans do not become integers and
JSON `null` is present as `None`.

Add runtime success and nested-failure cases for descriptors generated from
`List[Value]` and `Map[String, Value]`. These must recurse through each
container's existing descriptor and report the first invalid Value leaf
without changing list order or map keys.

Add failures for:

- `NaN`, `Infinity`, and `-Infinity` in file-backed JSON;
- nested non-finite in-memory floats;
- bytes, tuples, sets, non-string object keys, and arbitrary objects;
- a missing bundle file and malformed JSON; and
- a missing non-root pointer.

For recursive failures assert `invalid_transportable_value` and the first
invalid JSON-style path, such as `/items/2/value`.

- [ ] **Step 2: Run RED and collect the new module**

```bash
pytest --collect-only -q tests/test_output_contract_value.py
pytest -q tests/test_output_contract_value.py
```

Expected: collection succeeds; tests fail with unsupported `value` and
non-standard constants currently being accepted by `json.loads`.

- [ ] **Step 3: Implement strict parsing and one recursive validator**

Add a recursive descriptor scan that detects whether an ordinary or variant
output contract contains `type: value`, including underneath optional/list/map
and variant field descriptors. Only those Value-bearing bundle parses use a
`parse_constant` callback that rejects all non-standard numeric constants;
pre-2.19 and narrower-only bundles retain their existing parsing and
validation behavior byte-for-byte. Add a recursive helper that accepts only:

```python
None
bool
int
finite float
str
list[Value]
dict[str, Value]
```

Check `bool` before `int`, use `math.isfinite`, preserve values rather than
coercing them, and carry an RFC-6901-escaped first-invalid path in the
violation context. Route both `validate_output_bundle` and
`validate_contract_value` through that helper for `type: value`.

- [ ] **Step 4: Run runtime-contract regressions**

```bash
pytest -q tests/test_output_contract_value.py \
  tests/test_output_contract.py \
  tests/test_output_contract_collections.py
```

Expected: PASS; existing narrower coercion and validation behavior is
unchanged.

- [ ] **Step 5: Complete ordered reviews and commit — final reaffirmations
      pending; commit pending**

Expected implementation commit subject:

```text
Validate recursive transportable Value payloads
```

### Task 4: Propagate `kind: value` through consumers, state, and resume

**Files:**

- Modify: `orchestrator/workflow/dataflow.py` if RED
- Modify: `orchestrator/workflow/executor.py` if RED and not externally dirty
- Modify: `orchestrator/workflow_lisp/lexical_checkpoint_restore.py` if RED
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py` if RED
- Modify: `orchestrator/workflow_lisp/lowering/phase_stdlib.py` if RED
- Modify: `tests/test_workflow_lisp_transportable_value.py`
- Test: `tests/test_artifact_dataflow_integration.py`
- Test: `tests/test_resume_command.py`
- Test: `tests/test_workflow_lisp_lexical_checkpoint_default_resume.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`
- Test: `tests/test_workflow_state_projection.py`
- Test: `tests/test_dashboard_projection.py`
- Test: `tests/test_workflow_lisp_provider_supervision.py`

- [ ] **Step 1: Add consumer-switch and persistence tests**

Compile or construct one mixed `Value` artifact and prove:

- input/output/artifact refs and consumes preserve it opaquely;
- dataflow validates it through the shared contract validator;
- runtime plans, semantic/executable IR, and build manifests retain the
  declared `kind/type: value` contract without storing attempt payload bytes;
- runtime state, reports, and dashboard projections retain the exact
  attempt payload through their existing artifact-value surfaces;
- checkpoint restore compares the declared `Value` type, not the old payload
  shape;
- a second attempt may produce a different JSON shape under the same
  signature;
- typed prompt input canonical rendering accepts the resolved Value without
  granting field/path operations; and
- provider-supervision and adjudication output-bundle consumers remain
  generic.

- [ ] **Step 2: Run RED consumer matrix**

```bash
pytest -q tests/test_workflow_lisp_transportable_value.py \
  tests/test_artifact_dataflow_integration.py \
  tests/test_resume_command.py \
  tests/test_workflow_lisp_lexical_checkpoint_default_resume.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_state_projection.py \
  tests/test_dashboard_projection.py \
  tests/test_workflow_lisp_provider_supervision.py \
  -k 'value_kind or transportable_value'
```

Expected: FAIL only at descriptor switches that currently enumerate
relpath/scalar/collection.

- [ ] **Step 3: Patch only failing switches**

For `kind: value`, call `validate_contract_value` and pass the result through
without scalar, collection, or relpath behavior. In checkpoint restore,
associate it with authored type `Value`. In surface projections, preserve
`kind: value`; in typed prompt inputs, classify it only as an opaque pure
value. Do not add a parallel store or infer a concrete type.

If `orchestrator/workflow/executor.py` has concurrent external edits, first
prove whether the existing generic output-bundle path already handles Value.
Do not touch it unless the RED test is load-bearing and the edit can be
isolated without overwriting the external work.

- [ ] **Step 4: Run adjacent state/resume/consumer suites**

```bash
pytest -q tests/test_artifact_dataflow_integration.py \
  tests/test_resume_command.py \
  tests/test_workflow_lisp_lexical_checkpoint_default_resume.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_state_projection.py \
  tests/test_dashboard_projection.py \
  tests/test_workflow_lisp_provider_supervision.py
```

Expected: PASS, or retain only documented pre-existing external failures.

- [ ] **Step 5: Complete ordered reviews and commit**

Expected implementation commit subject:

```text
Carry Value through state and resume
```

### Task 5: Prove classic/WCC contract, guidance, and lowering parity

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/core.py` if RED
- Modify: `orchestrator/workflow_lisp/lowering/pure_projection.py` if RED
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py` if RED
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py` if RED
- Modify: `orchestrator/contracts/prompt_contract.py` if RED
- Modify: `tests/test_workflow_lisp_transportable_value.py`
- Test: `tests/test_workflow_lisp_lowering.py`
- Test: `tests/test_workflow_lisp_wcc_m4.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`
- Test: `tests/test_prompt_contract_injection.py`
- Test: `tests/test_workflow_lisp_result_guidance_e2e.py`

- [ ] **Step 1: Add exact classic/WCC parity tests**

Compile provider-result, command-result, procedure pass-through, workflow call,
public workflow return, and nested collection cases through both routes.
Compare semantic and executable contracts and assert:

```python
field["name"] == "__result__"
field["json_pointer"] == ""
field["type"] == "value"
public_output["kind"] == "value"
public_output["type"] == "value"
```

Provider guidance must describe one direct JSON document root, include the
authored description/format hint, and never invent field names or
`{"value": ...}`. Do not assert literal prompt phrasing; assert the parsed
contract block's path, field count, pointer, type, and guidance dataflow.

- [ ] **Step 2: Run RED parity selectors**

```bash
pytest -q tests/test_workflow_lisp_transportable_value.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_wcc_m4.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_prompt_contract_injection.py \
  tests/test_workflow_lisp_result_guidance_e2e.py \
  -k 'transportable_value or value_contract'
```

Expected: PASS where lowering is already generic and FAIL only at
scalar/collection classifications that omit Value.

- [ ] **Step 3: Implement only evidence-backed parity fixes**

Reuse the existing `GeneratedBundleContract` and direct-root machinery.
Preserve literal `value` in typed/Core/semantic/executable/build/source-map
surfaces. Do not add a Value-specific effect node or branch.

- [ ] **Step 4: Run complete adjacent lowering suites**

```bash
pytest -q tests/test_workflow_lisp_transportable_value.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_wcc_m4.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_prompt_contract_injection.py \
  tests/test_workflow_lisp_result_guidance_e2e.py
```

Expected: PASS.

- [ ] **Step 5: Complete ordered reviews and commit if production changed**

Expected implementation commit subject:

```text
Preserve Value across classic and WCC lowering
```

If all production paths were already generic, record the passing parity
evidence without an empty commit.

### Task 6: Execute provider-to-procedure-to-workflow Value and resume E2E

**Files:**

- Create:
  `tests/fixtures/workflow_lisp/valid/transportable_value_provider_resume.orc`
- Create: `tests/test_workflow_lisp_transportable_value_e2e.py`
- Modify: production owners from Tasks 3-5 only if the real RED path exposes
  a missing generic seam
- Test: `tests/test_workflow_lisp_native_returns_e2e.py`
- Test: `tests/test_workflow_lisp_pure_projection_runtime.py`

- [ ] **Step 1: Add the deterministic end-to-end fixture**

Author target-2.19 source in which a deterministic provider returns a mixed
object as `Value`, a procedure accepts and returns that exact `Value`, and the
public workflow returns it. The source must never spell `__result__` and may
not project or narrow the value.

The test harness must:

- write the mixed object directly as the bundle document;
- compile and execute through classic and WCC;
- assert equal executable contracts and exact runtime payloads;
- interrupt after the committed provider boundary but before downstream
  completion;
- resume through the production default-resume path;
- prove the provider invocation count remains one;
- prove checkpoint/state/report surfaces restore the identical Value; and
- prove a clean second run may return a different JSON shape without changing
  the declared contract identity.

- [ ] **Step 2: Run RED and collect the new module**

```bash
pytest --collect-only -q tests/test_workflow_lisp_transportable_value_e2e.py
pytest -q tests/test_workflow_lisp_transportable_value_e2e.py
```

Expected: collection succeeds; the first run fails at the remaining
integration seam, not because the fixture uses an implicit conversion.

- [ ] **Step 3: Implement the minimal integration fix**

Patch only an existing generic seam named by the RED trace. Preserve
validation-before-exposure, direct-root carriage, provider-boundary commit
semantics, and the existing default-resume selection/validation guards.

- [ ] **Step 4: Run E2E and native-return regressions**

```bash
pytest -q tests/test_workflow_lisp_transportable_value_e2e.py \
  tests/test_workflow_lisp_native_returns_e2e.py \
  tests/test_workflow_lisp_pure_projection_runtime.py
```

Expected: PASS.

- [ ] **Step 5: Complete ordered reviews and commit**

Expected implementation commit subject:

```text
Execute and resume transportable Value results
```

### Task 7: Close Q0 normative, routing, and broad verification

**Files:**

- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_type_catalog.md`
- Modify: `docs/design/README.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify: `specs/dsl.md`
- Modify: `specs/io.md`
- Modify: `specs/providers.md`
- Modify: `specs/versioning.md`
- Modify: `docs/capability_status_matrix.md`
- Modify:
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- Modify:
  `docs/plans/2026-07-26-workflow-lisp-transportable-value-implementation-plan.md`
- Modify: `docs/index.md` only through an exact Q0 routing hunk
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Test: all Q0 focused modules

- [ ] **Step 1: Write the failing routing/capability assertions**

Update the routing test to require:

- Q0 status is complete and Q1 is the next active Q-series design-correction
  stage;
- L0 remains the ready L-series item, L1–L4 retain their existing blockers,
  and no L-series behavior is relabeled implemented by Q0 closure;
- capability and design routers say `Value` is implemented at target 2.19;
- the drafting guide distinguishes `Value` from `Json` and from concrete
  record/union contracts;
- direct-root/no-envelope, exact typing, opacity, strict JSON, guidance, and
  version rules appear in the normative owners; and
- the parked evolution roadmap, unselected E0, Q3-only E4P ownership, and
  deferred P1–P5/runtime-debugging boundary are unchanged.

Assert semantic relationships and coded behavior, not literal prompt text.

- [ ] **Step 2: Run the RED routing selector**

```bash
pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py \
  -k 'post_stage_8_successor or transportable_value'
```

Expected: FAIL because Q0 still says designed/active and the normative owners
do not yet describe implemented target 2.19.

- [ ] **Step 3: Update normative and routing owners**

Document only implemented behavior. Mark the accepted target design and Q0
plan complete, promote the capability matrix row to Implemented, and route
the Q-series successor to Q1 design correction/review. Preserve L0 as ready,
L1–L4 as blocked in their selected order, and every shipped-v1 versus planned
L-series distinction. Add no prompt-calculus or language-server implementation
claim.

For `docs/index.md`, stage a generated or interactive exact hunk that updates
only Q0/Value/Q-series-successor lines. Verify the owner-authored Evolution and
L-series routing hunks remain unstaged.

- [ ] **Step 4: Run focused, adjacency, and routing verification**

```bash
pytest -q \
  tests/test_workflow_lisp_transportable_value.py \
  tests/test_output_contract_value.py \
  tests/test_workflow_lisp_transportable_value_e2e.py \
  tests/test_workflow_lisp_structured_results.py \
  tests/test_workflow_lisp_workflows.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_wcc_m4.py \
  tests/test_workflow_lisp_native_returns_e2e.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
```

Expected: PASS.

- [ ] **Step 5: Run the closing non-security broad suite in tmux**

Use the exact broad command in the Execution Contract. Record collected,
passed, skipped, failed, and error totals. Compare any failure against fresh
pre-Q0 identities; do not weaken tests or silently absorb a new failure.

- [ ] **Step 6: Complete final ordered reviews and commit**

The final specification reviewer must verify the accepted design, all task
commits, direct-root wire shape, exact typing, strict JSON failures,
classic/WCC/runtime/resume evidence, normative docs, and successor routing.
The distinct quality reviewer runs only after specification approval and
reviews the exact final diff plus fresh verification.

Expected implementation commit subject:

```text
Complete Workflow Lisp transportable Value
```

- [ ] **Step 7: Record factual closure separately**

After the reviewed implementation commit, update only this plan and the
successor roadmap with exact commit hashes, test totals, and review tokens.
Confirm the follow-up diff has no production, test, fixture, normative, or
other documentation change, then create one plan-only bookkeeping commit.

## Final Completion Gate

Q0 is complete only when all of the following are true:

- all seven tasks are complete under TDD;
- every behavior-bearing task received ordered independent specification then
  quality review over its exact committed bytes;
- `Value` is available only at target 2.19+ and is unshadowable;
- source compatibility is exact in both directions;
- direct-root `type: value` / `kind: value` carriage has no envelope;
- strict file-backed and in-memory validation rejects non-finite and
  non-JSON-like values with the required diagnostic;
- description/format-hint guidance works and `:example` fails closed;
- classic and WCC produce equivalent contracts and values;
- real execution and interruption/resume preserve the Value without provider
  re-execution;
- narrower contracts and `Json` behavior remain unchanged;
- focused, adjacent, routing, and closing non-security broad verification are
  fresh; and
- Q0 is marked complete while Q1 is only routed to its required design
  correction and review, not claimed implemented.
