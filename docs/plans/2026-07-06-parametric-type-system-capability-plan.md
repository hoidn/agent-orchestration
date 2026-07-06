# Parametric Type System Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the unimplemented contracts of
`docs/design/workflow_lisp_parametric_type_system.md` that gate Tranche 2
(the `backlog-drain` migration): directional constraint field-type
compatibility, type-parameter constraint field types, definition-site
coverage, report-all constraint failures, the diagnostics anatomy for hook
mismatches and instantiated-body failures, minimal-caller fixtures, and a
checkpoint-identity comparison harness.

**Architecture:** All changes extend the existing consumer-name-blind
machinery (`parametric_constraints.py`, `procedure_typecheck.py`,
`procedure_refs.py`, `procedures.py`); no new modules except test/fixture
files. The drain migration itself (generic `backlog-drain-proc` body, macro
re-target, intrinsic retirement) is **out of scope** — it gets its own plan
after this plan's feasibility gates are green, per the design's prerequisite
ordering.

**Tech Stack:** Python 3 (orchestrator frontend), Workflow Lisp `.orc`
fixtures, pytest.

## Scope and Phase-2 Gate

The parent design orders Tranche 2 prerequisites 1–6. This plan implements
prerequisites 1 (both capability gaps) and 2 (diagnostics fixtures), plus the
independent deletions and harnesses the design allows immediately
(dead validators, checkpoint-identity comparison, minimal-caller fixtures).
The follow-on drain-migration plan may be drafted only when Tasks 2, 3, 7,
and 9 of this plan are complete and green — those are the design's declared
feasibility gates.

## Global Constraints

- **Ground truth:** `docs/design/workflow_lisp_parametric_type_system.md` is
  the owning design. Where this plan and that doc disagree, the doc governs;
  raise the conflict rather than improvising.
- **Consumer-name blindness:** no change under `orchestrator/workflow_lisp/`
  may introduce knowledge of consumer names (`backlog-drain`,
  `review-revise-loop`, fixture names) into shared machinery.
- **No verification weakening:** constraint checks may become *directional*
  (accept refinements) exactly as rule 4 specifies, but no check may be
  deleted or bypassed to make a failure disappear.
- **Diagnostics anatomy (design, Diagnostics Contract):** every new or
  modified failure path must render the caller's span, the diagnostic code,
  the failing clause or signature delta, the concrete type(s), and a note
  carrying the definition-side location. Tests assert code + substrings +
  span/note facts, never full literal message text.
- **Concurrent workstream hazard:** the verified-iteration drain workflow is
  actively modifying `orchestrator/workflow_lisp/` (including
  `typecheck_calls.py`) and the working tree carries its uncommitted
  changes. Before starting any task: re-run the task's named suites to
  capture a fresh baseline, and stage commits **by explicit path only** —
  never `git add -A`.
- **Repo rules:** run from repo root; narrowest pytest selectors first;
  `pytest --collect-only` on any new/renamed test module; commit working
  code incrementally; no AI attribution in commit messages.
- **Suite baselines (2026-07-06, re-measure before use):**
  `tests/test_workflow_lisp_procedures.py` (108 tests),
  `tests/test_workflow_lisp_generic_stdlib_composition.py` (6),
  `tests/test_workflow_lisp_build_artifacts.py` (178). The lowering suite
  has known pre-existing failures owned by the drain workstream — do not
  chase them and do not count them against these tasks.

---

## Phase A — Independent deletions and harnesses

### Task 1: Delete the dead shadowed drain validators

**Files:**
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Test: `tests/test_workflow_lisp_procedures.py`,
  `tests/test_workflow_lisp_build_artifacts.py`,
  `tests/test_workflow_lisp_workflow_refs.py`

**Interfaces:**
- Consumes: the imports at `typecheck_dispatch.py:101-110`
  (`_workflow_ref_signature`, `_validate_selector_workflow_ref`,
  `_validate_run_item_workflow_ref`, `_validate_gap_drafter_workflow_ref`
  from `typecheck_calls`).
- Produces: `typecheck_dispatch.py` uses the imported validators everywhere;
  no module-level redefinitions remain.

Background: `typecheck_dispatch.py` imports four validators from
`typecheck_calls` at lines 101–110, then redefines the same names at module
level (`_workflow_ref_signature` 3119–3152, `_validate_selector_workflow_ref`
3155–3213, `_validate_run_item_workflow_ref` 3234–3314,
`_validate_gap_drafter_workflow_ref` 3317–3383). The redefinitions shadow the
imports and are byte-equivalent modulo annotations (verified in review). No
other module imports these names from `typecheck_dispatch`. The design
explicitly allows this deletion "immediately and independently."

- [ ] **Step 1: Capture baseline.**

```bash
pytest tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_workflow_refs.py -q
```
Expected: record pass/fail counts (fresh baseline; tree is shared with the
drain workstream).

- [ ] **Step 2: Diff the shadowed bodies one more time before deleting.**
Compare each redefinition against its `typecheck_calls.py` original
(`validate_selector_workflow_ref` at ~`typecheck_calls.py:440`,
`validate_run_item_workflow_ref` at ~`:520`, plus `workflow_ref_signature`
and `validate_gap_drafter_workflow_ref`). If any body has drifted from its
`typecheck_calls` counterpart (beyond annotations/imports), STOP and report —
that would mean the "dead" copy is live behavior.

- [ ] **Step 3: Delete the four redefinitions** (lines ~3119–3383, exact
range re-located by function name, not line number — the drain workstream
may have shifted lines). The imported names at 101–110 take over for the
internal uses at ~1848–1879.

- [ ] **Step 4: Re-run the Step 1 suites.**

```bash
pytest tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_workflow_refs.py -q
```
Expected: identical results to Step 1 baseline.

- [ ] **Step 5: Commit.**

```bash
git add orchestrator/workflow_lisp/typecheck_dispatch.py
git commit -m "Delete dead shadowed drain validators"
```

### Task 2: Directional assignment compatibility for constraint field types (rule 4)

**Files:**
- Modify: `orchestrator/workflow_lisp/parametric_constraints.py`
- Create: `tests/fixtures/workflow_lisp/valid/parametric_refined_path_field.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/parametric_refined_path_field_wrong_root.orc`
- Test: `tests/test_workflow_lisp_procedures.py`

**Interfaces:**
- Produces: `constraint_field_type_satisfied(actual: TypeRef, expected: TypeRef) -> bool`
  in `parametric_constraints.py` — the single comparison used by all three
  constraint field-type check sites. Task 3 reuses it for bound-parameter
  comparison.

Background: the three field-type comparisons in `parametric_constraints.py`
(`_check_record_field_constraint` ~line 314, `_check_union_variant_constraint`
~line 374, `_check_shared_union_field_constraint` ~line 433) use raw `!=` on
resolved `TypeRef`s. Rule 4 requires directional compatibility: the concrete
field type must be assignable **to** the constraint type, including
path-refinement narrowing (a refined `defpath` under the same root satisfies
the base path family). No assignability helper exists anywhere in the
frontend today — ordinary calls use strict `type_refs_compatible`
(`type_env.py:941`). This task scopes the directional check to constraint
field types only; ordinary argument typechecking is untouched.

- [ ] **Step 1: Write the failing end-to-end test.** Add to
`tests/test_workflow_lisp_procedures.py` (reuse its existing
`_compile_module_fixture`-style helper and `_assert_diagnostic_code`):

```python
def test_compile_stage3_accepts_refined_path_constraint_field(tmp_path: Path) -> None:
    bundle = _compile_module_fixture(
        FIXTURES / "valid" / "parametric_refined_path_field.orc", tmp_path=tmp_path
    )
    assert bundle is not None


def test_compile_stage3_rejects_refined_path_constraint_field_wrong_root(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_module_fixture(
            FIXTURES / "invalid" / "parametric_refined_path_field_wrong_root.orc",
            tmp_path=tmp_path,
        )
    _assert_diagnostic_code(excinfo, "parametric_constraint_unsatisfied")
    assert "instead of" in excinfo.value.diagnostics[0].message
```

(Adapt helper names to what `test_workflow_lisp_procedures.py` actually
defines; it already compiles fixture modules for the constraint tests at
lines ~955–1023.)

- [ ] **Step 2: Author the two fixtures.** Model the module skeleton on an
existing valid parametric fixture (e.g. the
`generic_stdlib_composition` family). Valid fixture core — a generic
requiring the base family, a caller providing a refinement:

```lisp
(defpath StateNote
  :kind relpath
  :under "state"
  :must-exist false)
(defrecord RefinedCtx
  (note StateNote))
(defproc read-note
  :forall (CtxT)
  ((ctx CtxT))
  :where ((CtxT is-record)
          (CtxT has-field note Path.state-root))
  -> Path.state-root
  ctx.note)
```

The invalid twin declares `(note ArtifactNote)` with
`:under "artifacts/work"` — wrong root, must fail. Adjust the exact
`Path.state-root` spelling and any required workflow scaffolding to match
how existing valid fixtures reference base path families (check
`std/context.orc` usage and an existing fixture before authoring; if
`Path.state-root` and a caller `defpath` differ in `kind`, the helper in
Step 4 must treat the base-family kind as compatible with `relpath`
refinements under the same root — resolve against reality, and record what
the type catalog actually produces in the test).

- [ ] **Step 3: Run the new tests; confirm the valid-fixture test FAILS**
(strict equality rejects the refinement) and the invalid one passes for the
wrong reason or fails-to-compile as expected.

```bash
pytest tests/test_workflow_lisp_procedures.py -k refined_path -v
```
Expected: valid-fixture test FAILS with `parametric_constraint_unsatisfied`.

- [ ] **Step 4: Implement the helper and swap the three sites.** In
`parametric_constraints.py`:

```python
def constraint_field_type_satisfied(actual: TypeRef, expected: TypeRef) -> bool:
    """Directional rule-4 check: `actual` (the caller's concrete field type)
    is assignable to `expected` (the constraint's field type).
    Contract: docs/design/workflow_lisp_parametric_type_system.md,
    Constraint Vocabulary rule 4."""
    if type_refs_compatible(expected, actual):
        return True
    if isinstance(expected, PathTypeRef) and isinstance(actual, PathTypeRef):
        return (
            actual.definition.under == expected.definition.under
            and (actual.definition.must_exist or not expected.definition.must_exist)
        )
    return False
```

Replace `if actual_type != requirement.field_type_ref:` /
`if actual_type != constraint.field_type_ref:` at the three check sites with
`if not constraint_field_type_satisfied(actual_type, ...):`. Keep the
existing failure messages ("has type A instead of B") unchanged. If Step 2's
reality check showed `kind` must participate, extend the path branch
accordingly and say so in the commit message.

- [ ] **Step 5: Run the new tests plus the constraint regression set.**

```bash
pytest tests/test_workflow_lisp_procedures.py -k "refined_path or constraint" -v
pytest tests/test_workflow_lisp_generic_stdlib_composition.py -q
```
Expected: all pass; pre-existing constraint tests unaffected (equal types
still satisfy via `type_refs_compatible`).

- [ ] **Step 6: Commit.**

```bash
git add orchestrator/workflow_lisp/parametric_constraints.py \
  tests/fixtures/workflow_lisp/valid/parametric_refined_path_field.orc \
  tests/fixtures/workflow_lisp/invalid/parametric_refined_path_field_wrong_root.orc \
  tests/test_workflow_lisp_procedures.py
git commit -m "Make constraint field-type checks directional per rule 4"
```

### Task 3: Type-parameter constraint field types (rule 3)

**Files:**
- Modify: `orchestrator/workflow_lisp/parametric_constraints.py`
- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py` (call sites of
  the two entry points, if signatures change)
- Create: `tests/fixtures/workflow_lisp/valid/parametric_type_param_constraint_field.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/parametric_type_param_constraint_field_mismatch.orc`
- Test: `tests/test_workflow_lisp_procedures.py`

**Interfaces:**
- Consumes: `constraint_field_type_satisfied` from Task 2;
  `evaluate_parametric_constraints(..., type_bindings=...)` already receives
  the fully-bound `type_bindings` mapping (`procedure_typecheck.py:582`).
- Produces: `:where` clauses whose field-type position names a `:forall`
  parameter, e.g. `(SelectionT has-union-variant SELECTED (selection SelPayloadT))`.

Background: `_normalize_constraint` and `_normalize_field_requirement`
(`parametric_constraints.py` ~lines 134–221) eagerly call
`type_env.resolve_type(field_type_name)`, so a `:forall` name in field-type
position fails as an unknown type today. This is the design's flagged
feasibility gap. Since normalization runs per call site with
`type_bindings` in scope, the fix is to resolve type-parameter names from
the bindings instead of the type environment.

- [ ] **Step 1: Write the failing tests.**

```python
def test_compile_stage3_accepts_type_param_constraint_field(tmp_path: Path) -> None:
    bundle = _compile_module_fixture(
        FIXTURES / "valid" / "parametric_type_param_constraint_field.orc",
        tmp_path=tmp_path,
    )
    assert bundle is not None


def test_compile_stage3_rejects_type_param_constraint_field_mismatch(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_module_fixture(
            FIXTURES / "invalid" / "parametric_type_param_constraint_field_mismatch.orc",
            tmp_path=tmp_path,
        )
    _assert_diagnostic_code(excinfo, "parametric_constraint_unsatisfied")
    diagnostic = excinfo.value.diagnostics[0]
    assert "SELECTED" in diagnostic.message
    assert any("constraint declared at" in note for note in diagnostic.notes)
```

- [ ] **Step 2: Author the fixtures.** Valid fixture core (a miniature of
the flagship's cross-hook contract — the payload type binds from a hook
parameter and is compared against the union's variant field):

```lisp
(defrecord Payload
  (item-id String))
(defunion Selection
  (EMPTY)
  (SELECTED
    (selection Payload)))
(defproc consume
  ((payload Payload))
  -> String
  payload.item-id)
(defproc pick-and-run
  :forall (SelectionT SelPayloadT)
  ((choice SelectionT)
   (run ProcRef[(SelPayloadT) -> String]))
  :where ((SelectionT is-union)
          (SelectionT has-union-variant SELECTED (selection SelPayloadT)))
  -> String
  (match choice
    (SELECTED s (run s.selection))
    (EMPTY e "empty")))
```

The invalid twin declares a second record `OtherPayload` and a `run` hook
over `OtherPayload` while `Selection.SELECTED.selection` stays `Payload` —
the bound `SelPayloadT` (= `OtherPayload`) must fail against the concrete
variant field (`Payload`). Match the `match`-syntax and module scaffolding
of existing generic fixtures before authoring; the semantic content above is
normative, the surface syntax follows the fixture family.

- [ ] **Step 3: Run and confirm both fail today** (unknown type at
normalization).

```bash
pytest tests/test_workflow_lisp_procedures.py -k type_param_constraint_field -v
```
Expected: FAIL — evidence the capability is unlanded.

- [ ] **Step 4: Implement deferred resolution.** In
`parametric_constraints.py`:
  - Thread `type_bindings: Mapping[str, TypeRef]` into
    `_normalize_constraint` and `_normalize_field_requirement` from
    `evaluate_parametric_constraints`.
  - In both: `if field_type_name in type_bindings: field_type_ref =
    type_bindings[field_type_name]` else resolve via `type_env` as today.
    Keep `authored_type_name` as the parameter name so failure messages read
    "instead of `SelPayloadT`".
  - `provisional_shared_union_field_capabilities` (the definition-scoped
    pass at `parametric_constraints.py:31`, called from
    `procedure_typecheck.py:180` with no bindings): add a
    `type_param_names: frozenset[str]` parameter (available from the
    signature at the call site) and **skip** resolution for
    `has-shared-union-field` clauses whose field type names a type
    parameter — the call-site pass covers them. Do not silently swallow
    other unknown names.
  - Comparison uses `constraint_field_type_satisfied` (Task 2) — for a
    bound-parameter field type this is the design's "compare the concrete
    variant field type against the bound parameter" semantics.

- [ ] **Step 5: Run the new tests, the full procedures suite, and the
composition suite.**

```bash
pytest tests/test_workflow_lisp_procedures.py -q
pytest tests/test_workflow_lisp_generic_stdlib_composition.py -q
```
Expected: new tests pass; suites at Task-start baseline plus new tests.

- [ ] **Step 6: Prove specialization end to end.** Confirm the valid
fixture's compile in Step 1 ran with `validate_shared=True` through the same
stage-3 entry as the composition tests (that is the "specialization +
lowering" evidence the design's prerequisite 1 demands). If the fixture
compile stops short of lowering, extend the test to the composition suite's
`compile_stage3_module` pattern.

- [ ] **Step 7: Commit.**

```bash
git add orchestrator/workflow_lisp/parametric_constraints.py \
  orchestrator/workflow_lisp/procedure_typecheck.py \
  tests/fixtures/workflow_lisp/valid/parametric_type_param_constraint_field.orc \
  tests/fixtures/workflow_lisp/invalid/parametric_type_param_constraint_field_mismatch.orc \
  tests/test_workflow_lisp_procedures.py
git commit -m "Support type-parameter constraint field types"
```

### Task 4: Definition-site coverage check for `:forall` parameters

**Files:**
- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py`
  (`typecheck_procedure_definitions`, starts line ~122)
- Modify: `orchestrator/workflow_lisp/diagnostics.py` (code registry)
- Create: `tests/fixtures/workflow_lisp/invalid/parametric_type_param_unbindable.orc`
- Test: `tests/test_workflow_lisp_procedures.py`

**Interfaces:**
- Produces: diagnostic code `procedure_type_param_unbindable`, raised once
  per offending `defproc` during definition typechecking (not at call
  sites). Design contract: Core Model, "Definition-site coverage".

Background: a `:forall` parameter appearing in no parameter or
`ProcRef`-signature position can never be bound; today the failure surfaces
at each caller as `parametric_type_binding_unresolved`. The design moves it
to definition time. Definition-scoped validation with resolved `TypeRef`s is
available in `typecheck_procedure_definitions`, where signature params carry
`TypeParamRef` occurrences — a `TypeRef`-tree walk there is simpler and less
brittle than a syntax walk in `procedures.py` elaboration, and still fires
at definition compile time.

- [ ] **Step 1: Write the failing test.**

```python
def test_typecheck_rejects_unbindable_type_param_at_definition(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_module_fixture(
            FIXTURES / "invalid" / "parametric_type_param_unbindable.orc",
            tmp_path=tmp_path,
        )
    _assert_diagnostic_code(excinfo, "procedure_type_param_unbindable")
```

The fixture declares a generic whose type param appears only in its `:where`
clause (no parameter, no `ProcRef` position) — and, critically, contains
**no call site** for it, so the failure can only come from definition-time
checking:

```lisp
(defproc orphan
  :forall (T)
  ((seed String))
  :where ((T is-record))
  -> String
  seed)
```

- [ ] **Step 2: Implement.** In `typecheck_procedure_definitions`, for each
signature with `type_params`: collect `TypeParamRef` names reachable from
`signature.params` type refs (recursing through `ProcRefTypeRef`
param/return positions, `Optional`/`List`/`Map` element types); every
declared type param absent from that set raises
`procedure_type_param_unbindable` with the definition's span and a message
naming the parameter and the rule ("appears in no parameter or ProcRef
signature position; it can never be inferred"). Register the code in
`diagnostics.py`'s known-code registry (alongside
`procedure_type_param_unknown`).

- [ ] **Step 3: Verify no existing valid fixture regresses** (a valid
generic whose param appears only via ProcRef must still compile):

```bash
pytest tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_generic_stdlib_composition.py tests/test_workflow_lisp_phase_stdlib.py -q
```
Expected: baseline + new test passing. If any shipped stdlib generic trips
the new check, STOP — that is a design-vs-reality conflict to report, not
suppress.

- [ ] **Step 4: Commit.**

```bash
git add orchestrator/workflow_lisp/procedure_typecheck.py \
  orchestrator/workflow_lisp/diagnostics.py \
  tests/fixtures/workflow_lisp/invalid/parametric_type_param_unbindable.orc \
  tests/test_workflow_lisp_procedures.py
git commit -m "Reject unbindable type parameters at definition time"
```

### Task 5: Report all failing constraints per call site

**Files:**
- Modify: `orchestrator/workflow_lisp/parametric_constraints.py`
- Test: `tests/test_workflow_lisp_procedures.py`
- Create: `tests/fixtures/workflow_lisp/invalid/parametric_multiple_constraint_failures.orc`

**Interfaces:**
- Produces: one `LispFrontendCompileError` carrying one diagnostic **per
  failing clause** for a given call site (design: Diagnostics Contract,
  report-all). `LispFrontendCompileError` already accepts a tuple
  (`diagnostics.py:254`); `render_diagnostics` joins them.

Background: `_raise_unsatisfied_constraint` raises on the first failing
clause, so a caller failing several of the flagship's 18 clauses learns them
one compile at a time. The accumulation point is the clause loop in
`evaluate_parametric_constraints` (`parametric_constraints.py:93-131`).

- [ ] **Step 1: Write the failing test.** Fixture: a generic with three
`:where` clauses (`has-field a String`, `has-field b Int`,
`has-union-variant DONE` on a second param) and a caller whose types fail
all three.

```python
def test_constraint_failures_report_all_clauses(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_module_fixture(
            FIXTURES / "invalid" / "parametric_multiple_constraint_failures.orc",
            tmp_path=tmp_path,
        )
    codes = [d.code for d in excinfo.value.diagnostics]
    assert codes.count("parametric_constraint_unsatisfied") >= 2
```

- [ ] **Step 2: Implement accumulation.** In
`evaluate_parametric_constraints`, wrap the per-clause normalize+check in
`try/except LispFrontendCompileError`, extend a `collected` list with
`error.diagnostics`, and continue to the next clause; after the loop,
`if collected: raise LispFrontendCompileError(tuple(collected))`.
Justification for the try/except: every check site already raises the
correctly-shaped diagnostic; catching at the loop boundary accumulates
without rewriting ten raise sites. Malformed/unknown-constraint diagnostics
(`parametric_constraint_malformed`/`_unknown`) participate in accumulation
the same way — they are clause-scoped.

- [ ] **Step 3: Run.**

```bash
pytest tests/test_workflow_lisp_procedures.py -q
pytest tests/test_workflow_lisp_generic_stdlib_composition.py -q
```
Expected: baseline + new test. Existing single-failure tests still pass
(`diagnostics[0]` indexing is unaffected for single-clause failures).

- [ ] **Step 4: Commit.**

```bash
git add orchestrator/workflow_lisp/parametric_constraints.py \
  tests/fixtures/workflow_lisp/invalid/parametric_multiple_constraint_failures.orc \
  tests/test_workflow_lisp_procedures.py
git commit -m "Report all failing parametric constraints per call site"
```

### Task 6: Hook signature mismatch diagnostics (Diagnostics Contract point 5)

**Files:**
- Modify: `orchestrator/workflow_lisp/procedure_refs.py`
  (`validate_proc_ref_signature` lines ~149–177, `validate_proc_ref_value`
  ~180–201)
- Test: `tests/test_workflow_lisp_procedures.py` (or the module that
  currently covers `proc_ref_signature_invalid` — locate by
  `grep -rn proc_ref_signature_invalid tests/`)

**Interfaces:**
- Consumes: `render_type_ref` (`type_env.py:893`) which already renders
  `ProcRefTypeRef` as `ProcRef[(A B) -> C]`.
- Produces: `proc_ref_signature_invalid` diagnostics whose message renders
  the expected `ProcRef` type, the actual signature rendered in the same
  form, and the first mismatching position (parameter index+name, arity, or
  `return`).

- [ ] **Step 1: Write the failing test.** Reuse an existing fixture or
inline module that passes a wrong-signatured proc as a `ProcRef` argument:

```python
def test_proc_ref_mismatch_renders_expected_actual_and_position(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_module_fixture(HOOK_MISMATCH_FIXTURE, tmp_path=tmp_path)
    message = excinfo.value.diagnostics[0].message
    assert "expected" in message and "ProcRef[" in message
    assert "parameter 1" in message or "return" in message
```

- [ ] **Step 2: Implement.** In `validate_proc_ref_signature`, compute the
first mismatch while checking (arity; else first `zip` position failing
`type_refs_compatible`; else return). Build the actual rendering as
`ProcRef[(...) -> ...]` from `actual_params` + `actual_signature.return_type_ref`
via `render_type_ref`. Message shape:
`procedure ref `X` does not match `Y`: expected `<rendered expected>`, got
`<rendered actual>`; first mismatch at <position>`. Apply the same treatment
to `validate_proc_ref_value` using `value.residual_type_ref`.

- [ ] **Step 3: Run the covering module plus procedures suite.**

```bash
pytest tests/test_workflow_lisp_procedures.py -q
```
Expected: baseline + new test. Existing tests asserting the old message
substring (`does not match`) still pass — the prefix is preserved.

- [ ] **Step 4: Commit.**

```bash
git add orchestrator/workflow_lisp/procedure_refs.py tests/test_workflow_lisp_procedures.py
git commit -m "Render signature delta in proc ref mismatch diagnostics"
```

### Task 7: Diagnostics anatomy regression tests

**Files:**
- Modify: `tests/test_workflow_lisp_procedures.py`,
  `tests/test_workflow_lisp_generic_stdlib_composition.py`
- Possibly modify: `orchestrator/workflow_lisp/specialization_typecheck.py`
  (only if Step 2's assertion is red)

**Interfaces:**
- Consumes: fixtures and failure paths from Tasks 2–6.
- Produces: the design's Diagnostics Contract regression set — the gate that
  instantiate-then-typecheck never degrades into errors pointing inside
  substituted bodies.

- [ ] **Step 1: Constraint-failure anatomy test.** Extend one existing
unsatisfied-constraint test (e.g.
`test_compile_stage3_rejects_unsatisfied_has_field_constraint`) to assert
all three anatomy points on the first diagnostic: `diagnostic.span` is the
caller fixture's path (call site, point 2); the message contains the
rendered failing clause and the concrete type name (point 3); a note
contains `constraint declared at` with the definition's path (point 1).

- [ ] **Step 2: Instantiated-body call-site anchoring.** Extend
`test_compile_stage3_rechecks_instantiated_generic_match_exhaustiveness`
(`test_workflow_lisp_generic_stdlib_composition.py:330`) to additionally
assert the rendered diagnostic locates the generic **call site**: the
diagnostic's span path or one of its notes must reference the caller
location, not only the generic body. `origin_span` is already threaded
through the specialization request (`specialization_typecheck.py:55`). If
the assertion is red, attach a note
(`instantiated from <path>:<line>:<column>`) to diagnostics raised while
typechecking a specialized procedure, sourcing it from the specialization
request's `origin_span` — implement in `specialization_typecheck.py` at the
point that re-raises/collects instantiated-body diagnostics.

- [ ] **Step 3: Collect-only + run both modules.**

```bash
pytest --collect-only tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_generic_stdlib_composition.py -q
pytest tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_generic_stdlib_composition.py -q
```
Expected: all pass.

- [ ] **Step 4: Commit** (include `specialization_typecheck.py` only if
touched).

```bash
git add tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_generic_stdlib_composition.py
git commit -m "Assert diagnostics anatomy for parametric failures"
```

### Task 8: Minimal-caller fixtures for shipped stdlib generics

**Files:**
- Create: `tests/fixtures/workflow_lisp/valid/minimal_caller_review_revise_loop.orc`
- Create: `tests/fixtures/workflow_lisp/valid/minimal_caller_finalize_selected_item.orc`
- Test: `tests/test_workflow_lisp_generic_stdlib_composition.py`

**Interfaces:**
- Consumes: the declared `:where` blocks of `std/phase.orc`
  `review-revise-loop-proc` (line ~83) and `std/resource.orc`
  `finalize-selected-item-proc` (line ~107) — read them first; they are the
  complete requirements list.
- Produces: per stdlib generic, a caller whose types provide **exactly** the
  declared constraints and nothing more (design, Acceptance Checks:
  mechanical enforcement that requirements are exactly the declared
  clauses).

- [ ] **Step 1: Read both stdlib signatures and transcribe their `:where`
clauses into fixture types.** Each record gets only the constrained fields;
each union only the constrained variants with only the constrained fields.
No extra fields, no extra variants — minimality is the point: if a stdlib
body reads anything undeclared, these fixtures fail at stdlib-edit time.

- [ ] **Step 2: Add compile tests.**

```python
def test_minimal_caller_satisfies_review_revise_loop_declared_constraints(tmp_path: Path) -> None:
    assert _compile_module_fixture(
        FIXTURES / "valid" / "minimal_caller_review_revise_loop.orc", tmp_path=tmp_path
    ) is not None


def test_minimal_caller_satisfies_finalize_selected_item_declared_constraints(tmp_path: Path) -> None:
    assert _compile_module_fixture(
        FIXTURES / "valid" / "minimal_caller_finalize_selected_item.orc", tmp_path=tmp_path
    ) is not None
```

- [ ] **Step 3: Run + collect-only.**

```bash
pytest --collect-only tests/test_workflow_lisp_generic_stdlib_composition.py -q
pytest tests/test_workflow_lisp_generic_stdlib_composition.py -q
```
Expected: all pass. If a minimal caller fails to compile, the stdlib body
uses an undeclared capability — report it as a design-conformance finding
(do not widen the fixture types to make it pass).

- [ ] **Step 4: Commit.**

```bash
git add tests/fixtures/workflow_lisp/valid/minimal_caller_review_revise_loop.orc \
  tests/fixtures/workflow_lisp/valid/minimal_caller_finalize_selected_item.orc \
  tests/test_workflow_lisp_generic_stdlib_composition.py
git commit -m "Add minimal-caller fixtures for stdlib generics"
```

### Task 9: Checkpoint-identity comparison harness

**Files:**
- Create: `tests/test_workflow_lisp_checkpoint_identity_comparison.py`

**Interfaces:**
- Consumes: `compile_stage3_entrypoint` + `WorkflowExecutor` pattern from
  `tests/test_workflow_lisp_lexical_checkpoints.py:30-51`;
  `executor.runtime_plan.lexical_checkpoint_points` (each point carries
  `.checkpoint_id`, `.workflow_name`, `.point_kind`, `.details`).
- Produces: `checkpoint_identity_map(bundle_or_executor) -> dict` — the
  reusable comparison surface the Phase-2 drain migration gate will use to
  compare intrinsic-route vs generic-route compiles (design, Tranche 2
  prerequisite 4).

- [ ] **Step 1: Write the harness helper + stability test.**

```python
def checkpoint_identity_map(executor) -> dict[tuple[str, str], str]:
    """(workflow_name, origin_key) -> checkpoint_id for every lexical point."""
    return {
        (point.workflow_name, point.origin_key): point.checkpoint_id
        for point in executor.runtime_plan.lexical_checkpoint_points
    }


def test_checkpoint_identity_stable_across_recompiles(tmp_path: Path) -> None:
    first = _executor_for_fixture(tmp_path / "a")
    second = _executor_for_fixture(tmp_path / "b")
    assert checkpoint_identity_map(first) == checkpoint_identity_map(second)
```

`_executor_for_fixture` follows the `_compile_fixture` pattern from
`test_workflow_lisp_lexical_checkpoints.py` against
`tests/fixtures/workflow_lisp/valid/lexical_checkpoint_shadow_points.orc`
(already exercises checkpoints), constructing a `WorkflowExecutor` without
running the workflow. If `origin_key` is not exposed directly on the point,
key on `point.program_point_id` and note which field was used.

- [ ] **Step 2: Run + collect-only.**

```bash
pytest --collect-only tests/test_workflow_lisp_checkpoint_identity_comparison.py -q
pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -v
```
Expected: pass — same source, same route, identical ids. (This test is the
tooling proof; the Phase-2 gate reuses `checkpoint_identity_map` to diff
intrinsic-vs-generic compiles of drain consumers.)

- [ ] **Step 3: Commit.**

```bash
git add tests/test_workflow_lisp_checkpoint_identity_comparison.py
git commit -m "Add checkpoint identity comparison harness"
```

### Task 10: Documentation sync and integration evidence

**Files:**
- Modify: `docs/design/workflow_lisp_parametric_type_system.md`
  (implementation-status notes only — the normative content is settled)
- Modify: `docs/capability_status_matrix.md` (parametric constraint rows, if
  present)
- Reference: `.superpowers/sdd/progress.md`

**Interfaces:**
- Consumes: outcomes of Tasks 1–9.

- [ ] **Step 1: Update the design doc's implementation-status parentheticals.**
Rule 4's "Implementation status: … strict type equality" note, the Core
Model note about call-site reporting of unbindable parameters, and the
Diagnostics Contract's "current implementation fails fast" and "current
message names only the two procedures" parentheticals now describe landed
behavior — rewrite each to state the capability is implemented, keeping the
design text itself unchanged. Update the landed-diagnostics code list with
`procedure_type_param_unbindable`.

- [ ] **Step 2: Integration evidence (repo rule: DSL/frontend changes need
an end-to-end check).** Run the production-consumer feasibility suite and
the build-artifacts suite:

```bash
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
pytest tests/test_workflow_lisp_build_artifacts.py -q
```
Expected: at Task-1 baseline counts (re-measured; the drain workstream may
have moved them — compare against the freshest baseline, not this plan's
snapshot).

- [ ] **Step 3: Commit.**

```bash
git add docs/design/workflow_lisp_parametric_type_system.md docs/capability_status_matrix.md
git commit -m "Record landed parametric capabilities in design docs"
```

---

## Phase B — Drain migration (deferred to its own plan)

Explicitly out of scope here. When Tasks 2, 3, 7, and 9 are green, draft
`docs/plans/<date>-backlog-drain-generic-migration-plan.md` covering the
design's Tranche 2 prerequisites 3–6: the authored `backlog-drain-proc` body
in `std/drain.orc`, the macro re-target (keyword surface frozen), the
checkpoint-identity gate using Task 9's harness against
`lisp_frontend_design_delta` consumers, parity gates, and intrinsic
retirement (`lowering/phase_drain.py`, `lowering/drain_terminal.py`
intrinsic paths, the form-specific monomorphizer, the live name-keyed
validators in `typecheck_calls.py`). That plan must be written against the
then-current tree — the verified-iteration drain workstream is concurrently
rewriting the same region.
