# Track A Form Registry And Elaboration Boundary Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce one frontend-owned registry for compiler-known Workflow Lisp heads and route macro reservation, top-level admission, expression elaboration, and live review-loop compatibility-boundary registration through that registry without changing current typecheck/lowering behavior.

**Architecture:** Add `orchestrator/workflow_lisp/form_registry.py` as the single inventory of compiler-known heads, including top-level definitions, core specials, core effects, stdlib extensions, and temporary compiler intrinsics. Use that registry to derive reserved macro names and admitted top-level heads with exact current-policy parity, dispatch `_elaborate_list(...)` through symbolic route keys, and retarget `compiler.py` from dead review-loop string scanners to the live `_augment_review_loop_command_boundaries(...)` registration path using registry/tag queries while preserving the existing `StdlibSpecializationExpr` compatibility bridge.

**Tech Stack:** Python, pytest, Workflow Lisp frontend, existing shared validation/runtime integration.

---

## Scope Guardrails

This plan implements only the selected Stage 3 Track A slice described in:

- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/track-a-form-registry-elaboration-boundary/implementation_architecture.md`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_lisp_refactor_architecture.md`

Keep these boundaries explicit:

- Do not add imported `.orc` inline expansion or specialization.
- Do not remove `StdlibSpecializationExpr`, `_typecheck_stdlib_specialization_expr(...)`, `_validate_review_loop_result_contract(...)`, or review-loop lowering helpers.
- Do not change `.orc` syntax, shared validation behavior, runtime behavior, diagnostics ownership, or source-map contracts beyond the new registry-owned classification errors.
- Do not edit `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`, `orchestrator/workflow_lisp/typecheck.py`, `orchestrator/workflow_lisp/lowering.py`, or shared runtime modules for this slice unless a purely mechanical import change is forced.
- Keep `review-revise-loop` public and macro-bindable; keep `__stdlib-specialization__` reserved and explicitly temporary.

## Files And Responsibilities

- Create: `orchestrator/workflow_lisp/form_registry.py`
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `tests/test_workflow_lisp_macros.py`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

Files intentionally not owned in this slice:

- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/stdlib_contracts.py`
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`

## Registry Contract To Implement

Create a small frontend-owned registry with import-time validation:

```python
class FormKind(Enum):
    TOP_LEVEL_DEFINITION = "top_level_definition"
    CORE_SPECIAL = "core_special"
    CORE_EFFECT = "core_effect"
    STDLIB_EXTENSION = "stdlib_extension"
    TEMP_COMPILER_INTRINSIC = "temp_compiler_intrinsic"


@dataclass(frozen=True)
class FormSpec:
    name: str
    kind: FormKind
    owner_module: str
    introduced_in: str
    remove_by: str | None
    macro_bindable: bool
    admitted_top_level: bool
    elaboration_route: str | None
    feature_tags: frozenset[str]
    rationale: str
```

Required initial inventory:

- Top-level heads:
  `workflow-lisp`, `defenum`, `defpath`, `defschema`, `defrecord`, `defunion`,
  `defworkflow`, `defun`, `defproc`, `defmodule`, `import`, `export`,
  `defmacro`
- Core specials:
  `record`, `variant`, `let*`, `if`, `match`, `loop/recur`, `fn`,
  `continue`, `done`, `call`, `workflow-ref`, `proc-ref`, `bind-proc`,
  `let-proc`
- Core effects:
  `provider-result`, `command-result`
- Stdlib extensions:
  `review-revise-loop`
- Temporary compiler intrinsics:
  `with-phase`, `phase-target`, `run-provider-phase`, `produce-one-of`,
  `provider`, `__stdlib-specialization__`, `resume-or-start`,
  `resource-transition`, `finalize-selected-item`, `backlog-drain`

Required metadata:

- `review-revise-loop`
  - `kind=STDLIB_EXTENSION`
  - `macro_bindable=True`
  - `feature_tags` includes `review_loop_public_surface`
  - `elaboration_route=None`
- `__stdlib-specialization__`
  - `kind=TEMP_COMPILER_INTRINSIC`
  - `macro_bindable=False`
  - `feature_tags` includes `review_loop_compat_bridge`
  - `remove_by` points at later imported `.orc` expansion / bridge retirement

Expose helpers from the registry module for:

- `get_form_spec(name: str) -> FormSpec | None`
- `reserved_macro_names() -> frozenset[str]`
- `admitted_top_level_heads() -> frozenset[str]`
- `head_has_feature_tag(name: str, tag: str) -> bool`
- `stdlib_request_kind_has_feature(request_kind: str, tag: str) -> bool`
  This is the narrow helper that maps the current `phase-review-loop` request
  kind to the `review_loop_compat_bridge` tag so `compiler.py` no longer owns
  a raw `"phase-review-loop"` policy branch.

Required policy parity for this slice:

- `reserved_macro_names()` must match the current checkout's reserved set
  exactly:
  `workflow-lisp`, `defenum`, `defpath`, `defschema`, `defrecord`,
  `defunion`, `defworkflow`, `defun`, `defproc`, `defmodule`, `import`,
  `export`, `defmacro`, `record`, `let*`, `match`, `call`,
  `provider-result`, `command-result`, `with-phase`, `phase-target`,
  `run-provider-phase`, `produce-one-of`, `__stdlib-specialization__`,
  `resume-or-start`, `resource-transition`, `finalize-selected-item`,
  `backlog-drain`, and `provider`.
- the following compiler-known heads must remain macro-bindable in this slice
  and therefore stay out of the reserved set:
  `review-revise-loop`, `variant`, `if`, `loop/recur`, `fn`, `continue`,
  `done`, `workflow-ref`, `proc-ref`, `bind-proc`, and `let-proc`.
- `admitted_top_level_heads()` must match the current checkout's accepted
  definition-head set exactly:
  `defenum`, `defpath`, `defschema`, `defrecord`, `defunion`, `defworkflow`,
  `defun`, and `defproc`.

Import-time validation must fail closed for:

- duplicate head names;
- `admitted_top_level=True` on non-definition heads;
- `macro_bindable=False` on `review-revise-loop`;
- missing route keys for compiler-elaborated non-stdlib expression forms.

## Task 1: Add Failing Characterization Tests First

**Files:**
- Modify: `tests/test_workflow_lisp_macros.py`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Add exact reserved-name and top-level parity tests**

Add focused tests that will fail before the registry exists:

- `test_form_registry_reserved_macro_names_match_current_policy_exactly`
- `test_form_registry_admitted_top_level_heads_match_current_policy_exactly`
- `test_form_registry_keeps_current_bindable_compiler_forms_bindable`

The assertions should prove:

- the derived reserved set is exactly today's reserved set from `macros.py`,
  not just a sample subset;
- `review-revise-loop`, `variant`, `if`, `fn`, `continue`, `done`,
  `workflow-ref`, `proc-ref`, `bind-proc`, and `let-proc` remain unreserved;
- admitted top-level heads still match the current accepted definition forms
  exactly.

- [ ] **Step 2: Add expression-level behavior tests for the new boundary**

Add focused expression tests such as:

- `test_elaborate_expression_rejects_stdlib_extension_without_import_route`
- `test_elaborate_expression_rejects_top_level_definition_head_in_expression_position`

For the first test, elaborate a raw `(review-revise-loop ...)` form directly
through `elaborate_expression(...)` and expect a new owned diagnostic code:
`stdlib_extension_missing_import_route`.

- [ ] **Step 3: Characterize the live compiler boundary with stdlib fixtures**

Add or extend focused compiler/stdlib tests so this slice proves the selected
review-loop registry query affects a live compile path:

- `test_review_loop_validator_binding_registers_only_when_review_loop_present`
  should compile both `VALID_REVIEW_LOOP_FIXTURE` and `VALID_RESUME_FIXTURE`
  and assert `validate_review_findings_v1` is present only for the review-loop
  workflow;
- keep the existing
  `tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_specializes_to_ordinary_typed_forms`
  and
  `tests/test_workflow_lisp_phase_stdlib.py::test_shared_validation_accepts_review_revise_loop`
  compatibility checks unchanged apart from any helper reuse needed by the new
  characterization test.

Do not add assertions about prompt wording or rendered YAML text.

- [ ] **Step 4: Collect the touched tests before implementation**

Run:

```bash
pytest --collect-only \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -q
```

Expected: the new tests collect cleanly.

- [ ] **Step 5: Run the new focused selectors and confirm failure**

Run:

```bash
pytest \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  -k "form_registry or stdlib_extension_missing_import_route or validator_binding_registers_only_when_review_loop_present" \
  -q
```

Expected: failures reference missing registry imports, missing diagnostics, or
old unconditional review-loop registration behavior.

- [ ] **Step 6: Commit the failing test tranche**

```bash
git add \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_phase_stdlib.py
git commit -m "test: characterize workflow lisp form registry boundary"
```

## Task 2: Introduce `form_registry.py`

**Files:**
- Create: `orchestrator/workflow_lisp/form_registry.py`
- Test: `tests/test_workflow_lisp_macros.py`

- [ ] **Step 1: Implement the registry data model and inventory**

Create `orchestrator/workflow_lisp/form_registry.py` with:

- `FormKind`
- `FormSpec`
- one canonical immutable registry keyed by head name
- the helper functions listed in the registry contract
- small import-time validation helpers

Keep the module frontend-owned. Do not move this inventory into
`stdlib_contracts.py`.

- [ ] **Step 2: Encode the review-loop public vs. compatibility split**

Model:

- `review-revise-loop` as `STDLIB_EXTENSION`
- `__stdlib-specialization__` as `TEMP_COMPILER_INTRINSIC`
- `phase-review-loop` request-kind tagging inside
  `stdlib_request_kind_has_feature(...)`

Do not add any new lowering/typechecking semantics here. This module is only
classification and query logic.

- [ ] **Step 3: Add import-time fail-closed validation**

Raise a plain import-time `ValueError` or `AssertionError` if:

- any head is declared twice;
- a non-definition form is admitted at top level;
- a non-stdlib compiler-elaborated form has no route key;
- `review-revise-loop` is accidentally reserved.

- [ ] **Step 4: Run the registry invariants**

Run:

```bash
pytest tests/test_workflow_lisp_macros.py -k "form_registry or reserved_macro" -q
```

Expected: exact parity tests pass and no existing reserved-name fixture regresses.

- [ ] **Step 5: Commit the registry module**

```bash
git add orchestrator/workflow_lisp/form_registry.py tests/test_workflow_lisp_macros.py
git commit -m "feat: add workflow lisp form registry"
```

## Task 3: Derive Macro Reservation And Top-Level Admission From The Registry

**Files:**
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `tests/test_workflow_lisp_macros.py`

- [ ] **Step 1: Replace hard-coded head sets**

In `macros.py`, replace `_RESERVED_MACRO_NAMES` and
`_ALLOWED_TOP_LEVEL_HEADS` with imports from `form_registry.py`.

Preferred shape:

```python
from .form_registry import admitted_top_level_heads, reserved_macro_names

_RESERVED_MACRO_NAMES = reserved_macro_names()
_ALLOWED_TOP_LEVEL_HEADS = admitted_top_level_heads()
```

If a local compatibility constant remains temporarily for readability, add an
import-time equality check so the module fails closed on drift.

- [ ] **Step 2: Preserve exact current reserved-name policy**

This task must preserve today's public macro policy exactly:

- no newly reserved compiler-known heads beyond the current set;
- `review-revise-loop` and the currently bindable core heads stay bindable;
- existing user-facing diagnostics stay unchanged for:
  `macro_reserved_name`,
  invalid top-level macro output,
  and duplicate macro definitions.

This task changes authority, not user-visible policy.

- [ ] **Step 3: Re-run the focused macro suite**

Run:

```bash
pytest tests/test_workflow_lisp_macros.py -q
```

Expected: all macro tests pass, including the new registry assertions and the
existing reserved-name fixtures.

- [ ] **Step 4: Commit the macro wiring**

```bash
git add orchestrator/workflow_lisp/macros.py tests/test_workflow_lisp_macros.py
git commit -m "refactor: derive macro head policy from form registry"
```

## Task 4: Route Expression Elaboration Through The Registry

**Files:**
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `tests/test_workflow_lisp_expressions.py`

- [ ] **Step 1: Add a symbolic elaboration route table**

In `expressions.py`, keep the existing elaborator functions but replace the
literal head chain in `_elaborate_list(...)` with:

1. resolve the head symbol;
2. query `get_form_spec(head.resolved_name)`;
3. if no spec exists, keep the current same-file function/procedure/local-proc
   fallback behavior;
4. if a spec exists:
   - reject `TOP_LEVEL_DEFINITION` in expression position;
   - reject `STDLIB_EXTENSION` with
     `code="stdlib_extension_missing_import_route"`;
   - dispatch all other forms through a route-key-to-function table.

- [ ] **Step 2: Preserve existing context-sensitive guard behavior**

Do not flatten away the current guard logic for:

- `fn` outside `loop/recur`
- `continue` outside `loop/recur`
- `done` outside `loop/recur`
- nested `let-proc`

Implement these as guarded route handlers instead of raw direct calls so the
new registry boundary preserves the old diagnostics.

- [ ] **Step 3: Keep the public stdlib surface out of direct elaboration**

The current checkout no longer has a direct
`head.resolved_name == "review-revise-loop"` branch in `_elaborate_list(...)`.
Keep it that way during the registry refactor:

- do not reintroduce a direct public `review-revise-loop` elaboration branch;
- keep the live `__stdlib-specialization__` compatibility path, but route it
  through the registry-owned `TEMP_COMPILER_INTRINSIC` classification instead
  of a one-off literal-policy cleanup step;
- do not delete `_elaborate_stdlib_specialization(...)` in this slice.

- [ ] **Step 4: Keep non-registry fallbacks unchanged**

After the registry miss path, preserve the current order:

1. same-file function call
2. same-file procedure call
3. local proc rejection
4. bound-name bare-expression rejection / field access behavior

This is required so the slice does not claim imported `.orc` expansion or
general callable resolution changes.

- [ ] **Step 5: Run focused elaboration tests**

Run:

```bash
pytest tests/test_workflow_lisp_expressions.py -q
```

Expected: existing expression tests pass, and the new stdlib-extension error
test passes with the owned diagnostic code.

- [ ] **Step 6: Commit the elaboration refactor**

```bash
git add orchestrator/workflow_lisp/expressions.py tests/test_workflow_lisp_expressions.py
git commit -m "refactor: route workflow lisp elaboration through form registry"
```

## Task 5: Route Live Review-Loop Adapter Registration Through Registry Queries

**Files:**
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Retarget the live command-boundary registration path**

Update `_augment_review_loop_command_boundaries(...)` so it uses its
`expressions` argument instead of registering `validate_review_findings_v1`
unconditionally:

- if the caller already provided `validate_review_findings_v1`, keep the
  existing override behavior;
- if no review-loop public surface or compat bridge is present in the supplied
  expressions, return the environment unchanged;
- if a review-loop route is present, register the certified adapter exactly as
  today.

This retargets the selected compiler boundary to a live compile surface instead
of the currently unused helper alone.

- [ ] **Step 2: Make review-loop detection registry-backed**

Update `_workflow_contains_review_revise_loop(...)` so:

- `SyntaxList` heads use `head_has_feature_tag(...)` instead of raw string
  comparisons for `review-revise-loop` and `__stdlib-specialization__`;
- `StdlibSpecializationExpr` uses
  `stdlib_request_kind_has_feature(expr.request_kind, "review_loop_compat_bridge")`
  instead of a raw `"phase-review-loop"` check.

Do not broaden this task into a generic walker rewrite for unrelated helper
functions.

- [ ] **Step 3: Keep resume-or-start detection unchanged**

Do not refactor `_workflow_contains_resume_or_start(...)` in this slice unless
the compiler import changes force a mechanical edit. The selected work item is
the review-loop classification boundary.

- [ ] **Step 4: Re-run the review-loop integration selectors**

Run:

```bash
pytest \
  tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_validator_binding_registers_only_when_review_loop_present \
  tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_specializes_to_ordinary_typed_forms \
  tests/test_workflow_lisp_phase_stdlib.py::test_shared_validation_accepts_review_revise_loop \
  -q
```

Expected: review-loop bindings appear only when needed, and the imported stdlib
compatibility route still compiles and lowers unchanged.

- [ ] **Step 5: Re-run the key migration parity selector**

Run:

```bash
pytest \
  tests/test_workflow_lisp_key_migrations.py::test_review_loop_parity_fixture_compiles_to_resume_safe_repeat_until_via_imported_stdlib_route \
  tests/test_workflow_lisp_key_migrations.py::test_review_loop_imported_stdlib_route_resumes_after_revise_checkpoint \
  -q
```

Expected: the compatibility bridge still preserves the imported stdlib
review-loop parity route after the live registration path becomes
presence-sensitive.

- [ ] **Step 6: Commit the compiler helper change**

```bash
git add \
  orchestrator/workflow_lisp/compiler.py \
  tests/test_workflow_lisp_phase_stdlib.py
git commit -m "refactor: query workflow lisp review loop boundary from registry"
```

## Task 6: Final Verification And Handoff

**Files:**
- Review all touched files

- [ ] **Step 1: Run the narrow owned suite**

Run:

```bash
pytest \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_key_migrations.py \
  -q
```

Expected: the owned regression surface passes.

- [ ] **Step 2: Run a frontend-wide import sanity check**

Run:

```bash
python -m compileall orchestrator/workflow_lisp
```

Expected: compileall succeeds for the frontend package.

- [ ] **Step 3: Run the required visible repo check**

Run:

```bash
git diff --check
```

Expected: no whitespace or patch-format errors.

- [ ] **Step 4: Record the bounded outcome**

In the implementation handoff or completion note, explicitly record:

- created `form_registry.py`;
- moved macro reservation and top-level admission authority to the registry;
- routed `_elaborate_list(...)` through registry lookup;
- replaced review-loop string scanning with registry/tag queries;
- did not implement imported `.orc` expansion;
- did not remove review-loop-specific typecheck/lowering helpers.

- [ ] **Step 5: Confirm the owned file set is clean after tranche commits**

```bash
git status --short \
  orchestrator/workflow_lisp/form_registry.py \
  orchestrator/workflow_lisp/macros.py \
  orchestrator/workflow_lisp/expressions.py \
  orchestrator/workflow_lisp/compiler.py \
  tests/test_workflow_lisp_macros.py \
  tests/test_workflow_lisp_expressions.py \
  tests/test_workflow_lisp_phase_stdlib.py
```

Expected: no entries remain for the owned file list because the tranche commits
from Tasks 1-5 already captured this slice. Do not stage broad globs under
`orchestrator/workflow_lisp` or `tests` for an extra aggregate commit.

## Acceptance Checklist

- [ ] `orchestrator/workflow_lisp/form_registry.py` exists and owns the full
      compiler-known head inventory used by macro reservation or expression
      elaboration.
- [ ] `review-revise-loop` is classified as `STDLIB_EXTENSION`, remains public,
      and is not in the reserved macro-name set.
- [ ] `__stdlib-specialization__` is classified as temporary compatibility,
      remains reserved, and carries explicit removal metadata.
- [ ] `macros.py` derives or validates reserved macro names and admitted
      top-level heads against the registry while preserving exact current
      reserved-name and top-level-head policy.
- [ ] `_elaborate_list(...)` consults the registry before any compiler-known
      form dispatch and errors on direct stdlib-extension elaboration.
- [ ] same-file function/procedure/local-proc fallback still happens only after
      registry lookup misses.
- [ ] `_augment_review_loop_command_boundaries(...)` no longer registers
      `validate_review_findings_v1` unconditionally; it only registers the
      adapter when registry-detected review-loop behavior is present.
- [ ] `_workflow_contains_review_revise_loop(...)` no longer matches raw
      `review-revise-loop` or `phase-review-loop` strings as policy.
- [ ] focused stdlib/key-migration integration tests still prove the current
      compatibility bridge works.
- [ ] the slice does not claim imported `.orc` expansion, denylist
      enforcement, or review-loop de-specialization.
