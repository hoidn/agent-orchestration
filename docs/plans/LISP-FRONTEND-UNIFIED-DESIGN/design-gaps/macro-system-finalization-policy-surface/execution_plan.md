# Macro System Finalization Policy Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current Workflow Lisp `defmacro` checkout behavior into one explicit, test-backed repo contract without expanding macro power, adding new validator layers, or reopening unrelated frontend/runtime design work.

**Architecture:** Implement this slice as a docs-first, regression-first alignment pass. The current macro engine, stage-3 import graph assembly, frontend effect validation, diagnostics rendering, and source-map lineage already provide most of the desired behavior; the work is to codify that bounded surface in one design doc, tighten the tests that prove the contract, and make only narrow implementation fixes in the real owner layer if those tests expose a mismatch in lookup, precedence, effect classification, or provenance behavior.

**Tech Stack:** Markdown docs, Workflow Lisp frontend (`orchestrator/workflow_lisp/`), `pytest`

---

## Scope Guardrails

- Treat `docs/design/workflow_lisp_unified_frontend_design.md` as future-scope target guidance and `docs/design/workflow_lisp_frontend_specification.md` as the baseline umbrella contract.
- Keep the slice bounded to the selected gap: current macro policy surface only.
- Do not add new macro syntax, intentional capture syntax, compile-time evaluation, runtime closures, dynamic dispatch, runtime callable transport, or alternate validator/lowering paths.
- Keep `docs/design/workflow_command_adapter_contract.md` authoritative for command-related macro policy; this slice may reference that contract but must not weaken or restate it as a new semantic authority.
- Shared validation, source-map validation, and runtime behavior remain owned by existing layers. This plan only clarifies ownership and preserves provenance through those layers.
- The progress ledger is currently empty, so there is no prior implementation evidence to reconcile beyond the code/tests/docs in the repo.

## File Map

**Create:**
- `docs/design/workflow_lisp_macro_surface_contract.md`

**Modify:**
- `docs/index.md`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_source_map.py`

**Modify only if new contract tests fail for a real behavior mismatch:**
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/source_map.py`

**Do not touch unless the bounded scope has clearly been misread and you stop for review:**
- shared runtime / semantic IR / executable IR modules

## Implementation Notes

- Reuse the implementation architecture at `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/macro-system-finalization-policy-surface/implementation_architecture.md` as the decomposition baseline.
- The plan should preserve the current distinction between:
  - caller-authored effectful syntax passed through a macro alias; and
  - effectful syntax introduced by the macro template itself.
- Imported macro lookup must stay aligned with `orchestrator/workflow_lisp/modules.py` import-scope rules:
  - local `:only` names when explicitly imported;
  - alias-qualified names like `alias.m`;
  - module-qualified names like `module/name`.
- The required stage-3 imported-macro tests run through `compile_stage3_entrypoint(...)`, `imported_macro_catalog(...)`, and `collect_macro_catalog_with_imports(...)`; narrow fixes in `compiler.py` are in scope if the integration path exposes a real catalog-wiring mismatch.
- The required caller-authored-versus-macro-introduced effect tests exercise the existing `macro_hidden_effect` ownership in `typecheck.py`; narrow fixes there are in scope if the classification or provenance plumbing disagrees with the documented contract.
- Diagnostics must continue to render macro call-site and definition-site provenance from `expansion_stack` / `ExpansionFrame`; do not invent a parallel macro registry.
- If the new contract tests pass without code changes, keep the implementation docs/tests-only.

### Task 1: Lock The Current Macro Contract Into Regression Tests

**Files:**
- Modify: `tests/test_workflow_lisp_macros.py`
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify: `tests/test_workflow_lisp_source_map.py`

- [ ] **Step 1: Add a failing macro-behavior test for caller-authored effect pass-through**

Add a narrow `tests/test_workflow_lisp_macros.py` case proving that a macro alias or wrapper may splice caller-authored `provider-result` or `command-result` syntax without reclassifying it as a macro-introduced hidden effect. Prefer a `tmp_path` fixture-local module over a permanent fixture file unless the test becomes unreadable inline.

Required assertion shape:

```python
result = compile_stage3_module(
    path,
    provider_externs={"providers.execute": "test-provider"},
    prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
    validate_shared=False,
    workspace_root=tmp_path,
)
assert [workflow.definition.name for workflow in result.typed_workflows] == ["..."]
```

- [ ] **Step 2: Add failing module-lookup tests for imported macro visibility and precedence**

Extend `tests/test_workflow_lisp_modules.py` with explicit coverage for the currently supported imported-macro name surfaces and collision ownership:

- alias-qualified invocation such as `helper.m`
- module-qualified invocation such as `demo/helper/m`
- local macro precedence over imported `:only` names
- ambiguous imported accessible macro names staying owned by module import resolution rather than the macro catalog

Prefer `compile_stage3_entrypoint(...)` coverage so the test exercises graph resolution, imported macro catalog construction, expansion, and stage-3 compilation together.

- [ ] **Step 3: Add failing diagnostic/source-map tests for policy ownership**

Tighten `tests/test_workflow_lisp_diagnostics.py` and `tests/test_workflow_lisp_source_map.py` so they explicitly prove:

- macro-template-introduced command/provider effects still surface as `macro_hidden_effect`
- downstream non-macro validation failures keep their original diagnostic code while preserving macro provenance notes
- macro-origin executable/source-map lineage failures keep the existing source-map validator ownership instead of collapsing into generic macro failures

Use assertions on `diagnostic.code`, `serialize_diagnostic(...)` metadata where relevant, and the ordered rendered provenance notes.

- [ ] **Step 4: Collect the new/renamed tests before implementing fixes**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_source_map.py -q
```

Expected: the new test names are discoverable and there are no collection errors.

- [ ] **Step 5: Run the focused failing selectors**

Run only the new tests or the narrowest selectors that cover them. Start with targeted node ids where practical; fall back to `-k` only if the node ids are unstable while editing.

Examples:

```bash
pytest tests/test_workflow_lisp_macros.py::test_compile_stage3_allows_caller_authored_effect_spliced_through_macro_alias -q
pytest tests/test_workflow_lisp_modules.py::test_compile_stage3_entrypoint_accepts_imported_macros_via_alias_and_module_qualified_names -q
pytest tests/test_workflow_lisp_diagnostics.py::test_compile_stage3_preserves_macro_provenance_without_reclassifying_downstream_validation_failures -q
pytest tests/test_workflow_lisp_source_map.py::test_source_map_validator_preserves_macro_origin_ownership_for_unmapped_executable_nodes -q
```

Expected: at least one test fails before any implementation change, or all pass and the contract gap is docs-only.

### Task 2: Write The Current-Surface Macro Contract And Index It

**Files:**
- Create: `docs/design/workflow_lisp_macro_surface_contract.md`
- Modify: `docs/index.md`

- [ ] **Step 1: Draft the contract doc with bounded current-checkout scope**

Create `docs/design/workflow_lisp_macro_surface_contract.md` and keep it explicitly narrower than the umbrella/future macro sections. Include these sections in this order:

1. Purpose and scope boundary
2. Supported current macro model
3. Hygiene and capture policy
4. Imported visibility, qualification, and local precedence
5. Validation ownership matrix
6. Active vs reserved/deferred macro diagnostics
7. Source-map and explain/provenance obligations
8. Relationship to command-adapter policy and future macro work

The doc must explicitly say that the current surface is template-based, deterministic, hygienic for macro-introduced names, and does not support intentional capture or runtime macro values.

- [ ] **Step 2: Encode the effect-visibility distinction precisely**

Document the current rule in the contract doc using concrete language that matches the checkout:

- caller-authored effectful syntax passed through a macro alias remains caller-authored and follows the ordinary validator path
- provider/command/state-affecting syntax introduced by the macro template itself is hidden effect surface and must fail through the existing frontend effect validation path

Reference `docs/design/workflow_command_adapter_contract.md` when describing command-result boundaries.

- [ ] **Step 3: Encode the validation-ownership and diagnostic-status matrix**

Include a table mapping each failure class to the current owner:

- macro parse/shape/cycle/reserved-name issues -> macro/frontend layer
- imported alias ambiguity -> module/import layer
- hidden macro-introduced effects -> frontend effect validation
- downstream lowered/shared validation failures -> existing downstream validators
- source-map lineage omissions -> source-map validator

Also mark current checkout diagnostic names as either active or reserved/deferred. Do not imply that paper-only future error codes are currently emitted unless you have code/test proof.

- [ ] **Step 4: Add the design-doc index entry**

Update `docs/index.md` with a concise entry for `docs/design/workflow_lisp_macro_surface_contract.md` that makes it discoverable from the Workflow Lisp design area.

The entry should describe:

- that it is the bounded current-surface contract for `defmacro`
- that it covers hygiene, lookup/precedence, validation ownership, and provenance
- that it should be read when aligning implementation/test behavior with the current macro surface

- [ ] **Step 5: Run a direct documentation sanity check**

Run:

```bash
rg -n "workflow_lisp_macro_surface_contract|macro surface contract|defmacro" docs/index.md docs/design/workflow_lisp_macro_surface_contract.md
```

Expected: the new doc exists, the index entry references it, and the contract language mentions the bounded current-surface scope rather than promising future macro features.

### Task 3: Align Implementation Only Where The New Contract Tests Expose A Real Mismatch

**Files:**
- Modify only if required: `orchestrator/workflow_lisp/macros.py`
- Modify only if required: `orchestrator/workflow_lisp/modules.py`
- Modify only if required: `orchestrator/workflow_lisp/compiler.py`
- Modify only if required: `orchestrator/workflow_lisp/typecheck.py`
- Modify only if required: `orchestrator/workflow_lisp/diagnostics.py`
- Modify only if required: `orchestrator/workflow_lisp/source_map.py`

- [ ] **Step 1: Triage failing tests by owner before editing code**

Use the failing assertions from Task 1 to classify the mismatch:

- imported macro graph assembly / accessible imported names / qualification / precedence -> `compiler.py`, `modules.py`, and possibly `macros.py`
- caller-authored versus macro-introduced hidden effect classification -> `typecheck.py`
- missing or unstable expansion-note ordering / metadata normalization -> `diagnostics.py`
- missing macro-origin lineage in built source-map artifacts -> `source_map.py`

If the failure points into shared runtime, Semantic IR, Executable IR, or a new validator surface outside the existing frontend/source-map pipeline, stop and confirm scope before editing; that likely means the plan uncovered a broader semantics bug, not this bounded policy gap.

- [ ] **Step 2: Apply the minimal code change that matches the documented contract**

Keep changes narrow:

- in `compiler.py`, preserve the existing stage-3 pipeline while tightening only the imported-macro catalog plumbing, qualification, or precedence handoff needed for the supported name surfaces
- in `modules.py`, preserve local-over-imported macro precedence while tightening qualified name registration only if one of the supported imported name surfaces is missing or inconsistent
- in `macros.py`, preserve the existing template expander and deterministic expansion ids; do not add compile-time evaluation or new syntax
- in `typecheck.py`, preserve the current frontend effect-validation owner while tightening only the caller-authored-versus-template-introduced effect classification or attached macro provenance
- in `diagnostics.py`, preserve downstream diagnostic codes while ensuring macro provenance notes remain attached and stable
- in `source_map.py`, preserve validator ownership while tightening only the missing lineage/plumbing needed for macro-origin entries

Do not widen the macro surface to make a test easier to satisfy.

- [ ] **Step 3: Re-run only the failing selectors until green**

Run the exact failing selectors from Task 1 after each code adjustment.

Expected: the targeted failures turn green without introducing new behavior outside the documented contract.

- [ ] **Step 4: Re-check that the implementation still matches the docs-first scope**

Before moving on, confirm all code edits can be explained by one of these contract statements:

- current hygienic introduced-name behavior
- imported visibility / qualification / local precedence
- validator ownership / provenance continuity

If not, revert the conceptual direction and narrow the change.

### Task 4: Run Focused Verification And Record Evidence

**Files:**
- Test: `tests/test_workflow_lisp_macros.py`
- Test: `tests/test_workflow_lisp_modules.py`
- Test: `tests/test_workflow_lisp_diagnostics.py`
- Test: `tests/test_workflow_lisp_source_map.py`
- Test: `tests/test_workflow_lisp_workflows.py`

- [ ] **Step 1: Run the full focused macro/frontend regression slice**

Run:

```bash
pytest \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_diagnostics.py \
  tests/test_workflow_lisp_source_map.py \
  tests/test_workflow_lisp_workflows.py -q
```

Expected: PASS. This is the main evidence bundle because it covers macro expansion, module import scope, downstream diagnostics, source-map lineage, and workflow-boundary checks for macro-origin compile-time-only values.

- [ ] **Step 2: Run one stage-3 integration path explicitly**

Run one targeted stage-3 entrypoint/integration test that exercises imported macros through the real compilation pipeline, for example:

```bash
pytest tests/test_workflow_lisp_modules.py::test_compile_stage3_entrypoint_accepts_imported_macros_via_alias_and_module_qualified_names -q
```

If you chose a different new integration test name, run that exact node id instead.

Expected: PASS. This satisfies the repo requirement for frontend/integration evidence beyond inspection-only reasoning.

- [ ] **Step 3: Re-run source-map validator coverage directly**

Run:

```bash
pytest tests/test_workflow_lisp_source_map.py -k "macro or executable_node" -q
```

Expected: PASS. This confirms the macro policy still survives the build-time provenance validator rather than relying only on rendered diagnostics.

- [ ] **Step 4: Record the final evidence in the implementation summary / handoff**

Capture:

- files changed
- whether Task 3 code edits were needed or the slice stayed docs/tests-only
- exact pytest commands run
- whether any reserved/deferred diagnostic names were documented without implementation changes

Do not claim completion from inspection alone.

## Done Criteria

- `docs/design/workflow_lisp_macro_surface_contract.md` exists and is indexed from `docs/index.md`
- the doc clearly distinguishes current checkout behavior from broader future macro aspirations
- tests explicitly cover imported macro lookup surfaces, local precedence, caller-authored effect pass-through, macro-hidden-effect rejection, and source-map/diagnostic provenance continuity
- any code edits stay inside the bounded optional file set, with `compiler.py` and `typecheck.py` touched only when failing contract tests prove the real owner mismatch
- focused verification passes and includes at least one stage-3 integration path
