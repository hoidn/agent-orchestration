# Typecheck Dispatch Owner-Family Migration Completion (Phase 2)

> **Execution status (active closeout amendment, verified 2026-07-09):** Execution has landed through Tasks 1-6: `bbc22fd1a819b009338b2801d47f55faeae771c1` (`Import typecheck raise helpers directly in family modules`), `6f01104face629a730e0a420162b97bda163ccc5` (`Move shared typecheck helpers into context leaf and drop compat back-imports`), `a124a7b4ec72722ebac8686f0c27714d92723461` (`Retire dispatch-local command argv validation for owner version`), `85556eab1c6298c986dc7705aa3dbb7befaec0cb` (`Retire dispatch-local macro-introduced effect check for owner version`), `6b99ca317503b02a0fda2ad213cb06fcd136539c` (`Extract resume-or-start typecheck into owner module`), `481cd284acff352b7c40aba8131ff031021d855b` (`Extract drain and phase typecheck cluster into owner module`), and `a4d9a3bb8ebfda957f4b4c6f02b72c2b49cbf657` (`Extract resource and view typecheck cluster into owner module`), with follow-up fix `69cce99f` included in the verified code boundary. The three owner modules exist and the legacy `compat` back-import grep is clean. The first closeout attempt passed 398 behavioral tests and the 19-test Design Delta smoke, but exposed a planning gap: the explicit Tasks 1-6 left `typecheck_dispatch.py` at 1,541 lines with dead tail helpers, two live deferred-import ownership residues, and 29 pre-plan pyflakes findings. Task 7 below is the bounded amendment required before the end-of-plan gate can close. Unrelated user work exists in the checkout and must be preserved.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the half-done `typecheck_dispatch.py` owner-family migration so the 3,357-line module shrinks to the dispatcher-plus-core-control-flow (~1,100 lines), each family cluster lives in its owner module, and the deferred `compat` back-import into the `typecheck.py` facade disappears.

**Architecture:** The migration is already test-enforced. Family modules use the uniform handler convention `handler(expr, *, context, recurse, typed_factory)` and dispatch already delegates ~13 branches with `context=context, recurse=recurse, typed_factory=_typed`. This plan (a) replaces the deferred `from . import typecheck as compat` back-imports with module-scope `typecheck_context` imports, (b) absorbs the small dispatch-owned helpers into the `typecheck_context` leaf, (c) resolves four legacy/owner duplicate pairs by semantic diff, and (d) extracts the resume, drain/phase, and resource/view clusters into new owner modules — each move accompanied by one structure-lock-test assertion edit.

**Entry gate:** Task 4 of `docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md` has landed. That task already deleted (do NOT re-plan): the local `_raise_error`/`_raise_required_lint` defs formerly at the bottom of `typecheck_dispatch.py`, the confirmed-dead `_require_union_variant_record_field`, and four shadowed import aliases (`is_macro_introduced_effect`, `typecheck_expected_extern_operand`, `validate_command_argv`, `validate_semantic_command_adapter_usage`) from the `from .typecheck_effects import (...)` block. This plan starts from the brief's increment 3 and does not depend on those deletions still being pending. **Re-anchor every line number below with the given function-name anchor if the tree has shifted** (the working tree carries the user's in-flight changes); all line numbers were verified against the tree on 2026-07-07 and drift from the originating brief is called out inline where it occurred.

## Global Constraints

- Run all commands from the repo root `/home/ollie/Documents/agent-orchestration`.
- The working tree contains the user's in-flight work. **Stage by explicit path only** (`git add <file> <file>`). Never `git add -A`, `git add -u`, or `git commit -a`.
- Commit messages: short imperative sentence, matching repo style (e.g. `Route selector and gap drafting to stronger models`). **No** conventional-commit prefixes, **no** mention of Claude/Claude Code, **no** Co-Authored-By trailers.
- No worktrees. Never use `--no-verify`.
- Narrowest pytest selectors first; treat fresh command output as the verification evidence. After changing any test module, run `pytest --collect-only <module>` on it.
- Do not touch `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*` directories — they are compile-evidence inputs for the certification lane.
- Frozen surfaces (do not modify): `orchestrator/workflow_lisp/lowering/phase_drain.py` lines 592-1979, `orchestrator/workflow_lisp/lowering/drain_terminal.py`, everything gated on the `lisp_frontend_design_delta/drain::drain` entry in `build.py`, `migration_parity.py`.
- If a step's verification fails twice in a row, stop and report instead of forcing it green.

---

## Shared facts (verified 2026-07-07 — re-anchor if the tree shifted)

- `_typecheck` single dispatcher: `def _typecheck(` at :294, body ends at :2459 (`raise TypeError(f"unsupported expression node: {type(expr)!r}")`); helpers begin at :2462 (`def _require_normative_phase_ctx_type`).
- `recurse` closure defined inside `_typecheck` at :326-379 — `def recurse(node, **overrides)`; every override defaults to the dispatcher's own parameter, so a bare `recurse(node)` reproduces a same-context recursion. The 13 already-delegated handlers receive `context=context, recurse=recurse, typed_factory=_typed`.
- Module-level `_typed` at :2782 is the `typed_factory` passed to all delegated handlers.
- Cluster ranges inside `_typecheck` (by first isinstance branch):
  - literals/refs :381-893 (stays — dispatcher core)
  - control flow :894-1185 (`IfExpr` :894, `LoopRecurExpr` :990, `ProcedureCallExpr` :1084, `WithPhaseExpr` :1131) (stays — dispatcher core)
  - resource/view :1186-1787 (`ResourceTransitionExpr` :1186, `MaterializeViewExpr` :1556, `FinalizeSelectedItemExpr` :1646)
  - drain/phase :1788-2238 (`BacklogDrainExpr` :1788, `PhaseTargetExpr` :1961, `RunProviderPhaseExpr` :1977, `ProduceOneOfExpr` :2087)
  - resume :2239-2459 (`ResumeOrStartExpr` :2239)
- Family modules and their deferred-import back-references into the facade (`from . import typecheck as compat`): `typecheck_calls` 14, `typecheck_effects` 6, `typecheck_proofs` 2, `typecheck_pure_ops` 1.
- `typecheck.py` facade re-exports from `typecheck_dispatch` in the block at :22-37; the dispatch-private names are the 14 individual imports at :23-36 (`_derive_resume_metadata`, `_derive_resume_producer_fingerprint_basis`, `_derive_resume_public_input_hash_basis`, `_effect_subject`, `_generated_relpath_seed_expr`, `_literal_type_name`, `_require_normative_phase_ctx_type`, `_require_phase_scope_name_match`, `_require_resume_binding`, `_type_label`, `_type_refs_compatible`, `_typed`, `_unify_loop_control_types`, `typecheck_expression`).
- `typecheck_context.py` already exports `raise_error` (:181), `raise_required_lint` (:160), `TypecheckContext`, `TypedExpr`, `get_session_state`/`snapshot_session_state`/`restore_session_state`; its module-scope imports are all leaves (`diagnostics`, `effects`, `expressions`, `lints`, `loops`, `parametric_constraints`, `procedure_refs`, `procedures`, `spans`, `type_env`) — no cycle with dispatch or any family module.

**Structure-lock tests** (all read `typecheck_dispatch.py` source and/or the `typecheck` facade top-level names and assert ownership; `_typecheck_top_level_names()` / `_module_top_level_names()` helpers parse the AST top-level `def`/`class` names):
- `tests/test_workflow_lisp_procedures.py:239` (`test_typecheck_facade_keeps_generated_local_procedure_helpers_after_let_proc_split`)
- `tests/test_workflow_lisp_phase_stdlib.py:4135` (`test_review_loop_owner_split_moves_stdlib_bridge_typing_out_of_typecheck_facade`)
- `tests/test_workflow_lisp_workflow_refs.py:114` (`test_workflow_ref_owner_split_moves_non_procedure_call_typing_out_of_typecheck_facade`)
- `tests/test_workflow_lisp_expressions.py:156` (`test_typecheck_facade_reexports_public_entrypoints_after_owner_split`)
- `tests/test_workflow_lisp_variant_proofs.py:52` (`test_variant_proof_owner_split_moves_proof_types_out_of_typecheck_facade`)
- `tests/test_workflow_lisp_structured_results.py:94` (`test_effect_owner_split_moves_command_and_provider_typecheck_out_of_facade`)

Two assertion flavors are used: (1) `"<name>" not in top_level_names` (checks the `typecheck` facade's re-export surface — a moved-out helper must NOT be re-exported), and (2) `"if isinstance(expr, <Node>):" not in dispatch_source` / `"<owner_call>(" in dispatch_source` (checks the dispatcher delegates rather than inlines).

**Behavioral coverage** flows through `typecheck_expression` and the compile path (`tests/test_workflow_lisp_expressions.py`, `tests/test_workflow_lisp_phase_stdlib.py`, `tests/test_workflow_lisp_variant_proofs.py`, `tests/test_workflow_lisp_structured_results.py`) and is move-insensitive — moving a handler does not change its behavior, only its home.

---

## Task 1 (brief increment 3): Replace deferred `compat._raise_*` back-imports with module-scope `typecheck_context` imports

The family modules currently reach `_raise_error`/`_raise_required_lint` through the deferred `from . import typecheck as compat` and `compat._raise_error(...)`. The facade sources those two names from `typecheck_context` (`typecheck.py:16-17`), NOT from dispatch — so the family modules can import them directly from `typecheck_context` at module scope, removing the indirection. This does not yet delete the `compat` import (a few `compat._type_label`-class uses remain until Task 2).

**Verified counts (drift from brief):** `compat._raise_error` + `compat._raise_required_lint` sites are **89 total**, not ~58: `typecheck_calls` 36, `typecheck_effects` 32, `typecheck_proofs` 14, `typecheck_pure_ops` 7. Confirm with the Step-1 grep before editing.

**Files:**
- Modify: `orchestrator/workflow_lisp/typecheck_calls.py`
- Modify: `orchestrator/workflow_lisp/typecheck_effects.py`
- Modify: `orchestrator/workflow_lisp/typecheck_proofs.py`
- Modify: `orchestrator/workflow_lisp/typecheck_pure_ops.py`

**Interfaces:** No public-surface change. After this task each family module has a module-scope `from .typecheck_context import raise_error, raise_required_lint` and all `compat._raise_error(` / `compat._raise_required_lint(` sites become bare `raise_error(` / `raise_required_lint(`.

- [ ] **Step 1: Re-verify the per-module counts**

```bash
for m in typecheck_calls typecheck_effects typecheck_proofs typecheck_pure_ops; do
  echo "$m: $(grep -cE 'compat\._raise_error|compat\._raise_required_lint' orchestrator/workflow_lisp/$m.py)"
done
```
Expected (re-anchor if drifted): `typecheck_calls: 36`, `typecheck_effects: 32`, `typecheck_proofs: 14`, `typecheck_pure_ops: 7`.

- [ ] **Step 2: Add the module-scope import to each family module**

In each of the four modules, add near the existing module-scope relative imports:
```python
from .typecheck_context import raise_error, raise_required_lint
```
(Place it with the other `from .` imports; these modules do not import `typecheck_context` at module scope today — verified.)

- [ ] **Step 3: Rewrite the call sites in each module**

Replace every `compat._raise_error(` → `raise_error(` and every `compat._raise_required_lint(` → `raise_required_lint(` in that module. Do NOT touch other `compat.*` uses yet (`compat._type_label`, `compat._resolve_field_access`, etc.). Confirm none remain:
```bash
for m in typecheck_calls typecheck_effects typecheck_proofs typecheck_pure_ops; do
  echo "$m still raising via compat: $(grep -cE 'compat\._raise_error|compat\._raise_required_lint' orchestrator/workflow_lisp/$m.py)"
done
```
Expected: `0` for all four.

- [ ] **Step 4: Verify import + behavior**

```bash
python -c "import orchestrator.workflow_lisp.typecheck_calls, orchestrator.workflow_lisp.typecheck_effects, orchestrator.workflow_lisp.typecheck_proofs, orchestrator.workflow_lisp.typecheck_pure_ops"
pyflakes orchestrator/workflow_lisp/typecheck_calls.py orchestrator/workflow_lisp/typecheck_effects.py orchestrator/workflow_lisp/typecheck_proofs.py orchestrator/workflow_lisp/typecheck_pure_ops.py
pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_structured_results.py -q
```
Expected: imports OK; pyflakes silent for the touched names; tests PASS.

(No structure-lock-test edit here — no helper moves out of dispatch in this task.)

- [ ] **Step 5: Commit**

```bash
git add orchestrator/workflow_lisp/typecheck_calls.py orchestrator/workflow_lisp/typecheck_effects.py \
        orchestrator/workflow_lisp/typecheck_proofs.py orchestrator/workflow_lisp/typecheck_pure_ops.py
git commit -m "Import typecheck raise helpers directly in family modules"
```

---

## Task 2 (brief increment 4): Absorb the small dispatch-owned helpers into `typecheck_context`; drop the deferred `compat` imports and the facade re-exports

Move the dispatch-private helpers the family modules still reach through `compat` into the `typecheck_context` leaf, so the deferred `from . import typecheck as compat` imports disappear entirely and the facade's dispatch re-exports shrink.

**Verified drift from brief:** the only dispatch-owned helper the family modules reach via `compat` is `_type_label` (10 sites, not ~5): `typecheck_calls.py:809,810,900,901`, `typecheck_proofs.py:122,241,248,249`, `typecheck_pure_ops.py:267,268`. `typecheck_proofs` also uses `compat._resolve_field_access` (:178 region) — that is a proofs-owned function (`resolve_field_access` in `typecheck_proofs.py`), not dispatch-owned, so it converts to a same-module direct call, not a context import. Confirm the full `compat.*` residue per module in Step 1 and handle each residual name by its true owner.

Helpers to relocate from `typecheck_dispatch.py` into `typecheck_context.py`: `_typed` (:2782), `_type_label` (:2973), `_type_refs_compatible` (:2941), `_literal_type_name` (:2931), `_span_contains` (:3309), `_literal_string` (:3105), `_variant_has_field` (:3111), `_union_has_any_field` (:3115). Move each as `_typed`/`_type_label`/... keeping the leading underscore (the facade already re-exports them under those names and other dispatch code calls them by that name). `typecheck_context` already imports the types these need (`TypeRef`, `EffectSummary`, `ExprNode`, `SourceSpan`, `LoopControlTypeRef`); add any missing type imports (e.g. `UnionTypeRef`, `VariantCaseTypeRef`) from `type_env` at module scope in `typecheck_context.py`.

**Files:**
- Modify: `orchestrator/workflow_lisp/typecheck_context.py` (add the 8 helpers + any missing type imports)
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py` (delete the 8 local defs; import them from `.typecheck_context`)
- Modify: `orchestrator/workflow_lisp/typecheck_calls.py`, `typecheck_proofs.py`, `typecheck_pure_ops.py` (rewrite `compat._type_label` sites; drop the now-unused `from . import typecheck as compat`)
- Modify: `orchestrator/workflow_lisp/typecheck_effects.py` (drop the now-unused `compat` import if no residual `compat.*` remains)
- Modify: `orchestrator/workflow_lisp/typecheck.py` (drop the dispatch-private re-exports that moved)

**Interfaces:** Produces `from .typecheck_context import _typed, _type_label, _type_refs_compatible, _literal_type_name, _span_contains, _literal_string, _variant_has_field, _union_has_any_field` — signatures unchanged. `_typed(*, expr, type_ref, effect) -> TypedExpr`; `_type_label(type_ref) -> str`. Dispatch keeps passing `typed_factory=_typed` and calling `_type_label(...)` — now resolved through the context import.

- [ ] **Step 1: Enumerate the residual `compat.*` uses per module**

```bash
for m in typecheck_calls typecheck_effects typecheck_proofs typecheck_pure_ops; do
  echo "== $m =="; grep -nE 'compat\.' orchestrator/workflow_lisp/$m.py
done
```
Decision rule: for each residual name, classify by true owner — `_type_label` → moving to `typecheck_context` (import it); `_resolve_field_access` in `typecheck_proofs` → its own module function (call `resolve_field_access(` directly, drop the `compat.` prefix); anything else unexpected → STOP and report before proceeding.

- [ ] **Step 2: Copy the 8 helper defs into `typecheck_context.py`**

Move (cut) the exact bodies of `_typed`, `_type_label`, `_type_refs_compatible`, `_literal_type_name`, `_span_contains`, `_literal_string`, `_variant_has_field`, `_union_has_any_field` from `typecheck_dispatch.py` into `typecheck_context.py`. Add the type imports they reference to `typecheck_context.py`'s module-scope `from .type_env import (...)` block (find with `grep -nE 'UnionTypeRef|VariantCaseTypeRef|OptionalTypeRef' orchestrator/workflow_lisp/typecheck_dispatch.py | head`; use the same source modules dispatch imports them from).

- [ ] **Step 3: Import the 8 helpers into `typecheck_dispatch.py`**

Extend the `from .typecheck_context import (...)` block (:111) with the 8 names. Delete the 8 local defs from dispatch. Verify none are still defined locally:
```bash
grep -nE '^def _typed\b|^def _type_label\b|^def _type_refs_compatible\b|^def _literal_type_name\b|^def _span_contains\b|^def _literal_string\b|^def _variant_has_field\b|^def _union_has_any_field\b' orchestrator/workflow_lisp/typecheck_dispatch.py
```
Expected: no output.

- [ ] **Step 4: Rewrite `compat._type_label` sites and drop the deferred imports**

In `typecheck_calls.py`, `typecheck_proofs.py`, `typecheck_pure_ops.py`: replace `compat._type_label(` → `_type_label(` and add `from .typecheck_context import _type_label` at module scope (append to the existing `typecheck_context` import added in Task 1 rather than a second import line). Handle any other residual (e.g. proofs `_resolve_field_access`) per Step-1 classification. Then delete the deferred `from . import typecheck as compat` line from every function body in all four modules. Verify:
```bash
grep -rn 'from . import typecheck as compat\|compat\.' orchestrator/workflow_lisp/typecheck_calls.py orchestrator/workflow_lisp/typecheck_effects.py orchestrator/workflow_lisp/typecheck_proofs.py orchestrator/workflow_lisp/typecheck_pure_ops.py
```
Expected: no output.

- [ ] **Step 5: Shrink the `typecheck.py` facade re-exports**

In `typecheck.py`, remove the moved names from the `from .typecheck_dispatch import (...)` block (:22-37). The names `_literal_type_name`, `_type_label`, `_type_refs_compatible`, `_typed` moved to `typecheck_context`; if any consumer still imports them *from the facade*, re-export them from `typecheck_context` instead. Verify no external importer breaks:
```bash
grep -rn 'from orchestrator.workflow_lisp.typecheck import\|from .typecheck import' orchestrator/ tests/ | grep -E '_typed|_type_label|_type_refs_compatible|_literal_type_name'
```
For each hit, point it at `typecheck_context` (or keep a facade re-export sourced from `typecheck_context`). Decision rule: prefer NOT to keep dead re-exports — only re-export a name the facade if a live importer needs it.

- [ ] **Step 6: Update the structure-lock test**

`tests/test_workflow_lisp_expressions.py::test_typecheck_facade_reexports_public_entrypoints_after_owner_split` (:156) currently asserts `inspect.getsourcefile(typecheck_module.TypedExpr) == str(context_path)` and reads `dispatch_source`. Add an assertion that `_type_label` (and `_typed`) now resolve to `typecheck_context`, mirroring the existing `TypedExpr` assertion style. Quote/extend from the existing block:
```python
assert inspect.getsourcefile(typecheck_module.TypedExpr) == str(context_path)
```
Add (same style):
```python
from orchestrator.workflow_lisp import typecheck_context as _ctx
assert inspect.getsourcefile(_ctx._type_label) == str(context_path)
assert inspect.getsourcefile(_ctx._typed) == str(context_path)
```
Then run collection on the edited module:
```bash
pytest --collect-only tests/test_workflow_lisp_expressions.py
```

- [ ] **Step 7: Verify**

```bash
python -c "import orchestrator.workflow_lisp.typecheck, orchestrator.workflow_lisp.typecheck_dispatch, orchestrator.workflow_lisp.typecheck_context"
pyflakes orchestrator/workflow_lisp/typecheck_dispatch.py orchestrator/workflow_lisp/typecheck_context.py orchestrator/workflow_lisp/typecheck_calls.py orchestrator/workflow_lisp/typecheck_effects.py orchestrator/workflow_lisp/typecheck_proofs.py orchestrator/workflow_lisp/typecheck_pure_ops.py
pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_procedures.py -q
```
Expected: imports OK; pyflakes silent for touched names; tests PASS.

- [ ] **Step 8: Commit**

```bash
git add orchestrator/workflow_lisp/typecheck_context.py orchestrator/workflow_lisp/typecheck_dispatch.py \
        orchestrator/workflow_lisp/typecheck.py orchestrator/workflow_lisp/typecheck_calls.py \
        orchestrator/workflow_lisp/typecheck_effects.py orchestrator/workflow_lisp/typecheck_proofs.py \
        orchestrator/workflow_lisp/typecheck_pure_ops.py tests/test_workflow_lisp_expressions.py
git commit -m "Move shared typecheck helpers into context leaf and drop compat back-imports"
```

---

## Task 3 (brief increment 5): Resolve the four legacy/owner duplicate pairs by semantic diff — one pair per commit

Four helpers exist in BOTH `typecheck_dispatch.py` (local, legacy) and `typecheck_effects.py` (owner, migrated convention). Task 4 of the Phase-1 plan already removed the shadowing *import aliases*, so today the dispatch locals are what run. Each pair needs a semantic diff before the dispatch branch is repointed to the owner and the local deleted. **If a diff shows the dispatch local carries behavior the owner lacks, STOP that pair and record it — do not silently pick one.**

Verified anchors (dispatch local vs `typecheck_effects` owner, char counts as a divergence signal):
- `_typecheck_expected_extern_operand` dispatch :2821 (1,456ch) vs `typecheck_expected_extern_operand` :25 (453ch) — large size gap; diff carefully.
- `_validate_command_argv` dispatch :2986 (3,507ch) vs `validate_command_argv` :55 (3,545ch).
- `_validate_semantic_command_adapter_usage` dispatch :3070 (1,294ch) vs `validate_semantic_command_adapter_usage` :141 (1,369ch).
- `_is_macro_introduced_effect` dispatch :3298 (297ch) vs `is_macro_introduced_effect` :186 (284ch).

**Files (per pair):**
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py` (delete the local, repoint its call sites/branch to the owner)
- Possibly Modify: `orchestrator/workflow_lisp/typecheck_effects.py` (only if the diff proves the owner must absorb dispatch-local behavior)

**Interfaces:** After each pair, dispatch calls the owner (`typecheck_effects.typecheck_expected_extern_operand`, `.validate_command_argv`, `.validate_semantic_command_adapter_usage`, `.is_macro_introduced_effect`) via a module-scope import alias (dispatch already imports these owner names — check the `from .typecheck_effects import (...)` block; Phase-1 Task 4 removed the *shadowed* aliases, so re-add an alias if the call site needs one, or call the owner name directly).

- [ ] **Step 1 (per pair): Semantic diff**

For each pair run (example for the first):
```bash
python - <<'EOF'
import ast, difflib
def seg(path, name):
    src = open(path).read()
    for n in ast.parse(src).body:
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return ast.get_source_segment(src, n).splitlines(keepends=True)
D='orchestrator/workflow_lisp/typecheck_dispatch.py'
E='orchestrator/workflow_lisp/typecheck_effects.py'
a = seg(D, '_typecheck_expected_extern_operand')
b = seg(E, 'typecheck_expected_extern_operand')
print(''.join(difflib.unified_diff(a, b, 'dispatch_local', 'effects_owner', n=2)))
EOF
```
Decision rule: the owner uses the migrated convention (`context`/`recurse`/`typed_factory` params or `raise_error` directly) while the dispatch local uses the old closure spellings (`_raise_error`, direct env access). If the only differences are those mechanical spellings **and** the same validations/branches are present, the owner is a safe replacement. If the dispatch local performs an extra check, raises a code the owner does not, or reads state the owner does not receive → STOP that pair, record the divergence in the commit-less report, move to the next pair.

- [ ] **Step 2 (per pair): Repoint dispatch and delete the local**

If the diff clears: find the dispatch call sites of the local (`grep -n '<local_name>(' orchestrator/workflow_lisp/typecheck_dispatch.py`), repoint them to the owner (add/keep a `from .typecheck_effects import <owner_name> as <local_name>` alias so call sites need no edit, OR rename the call sites to the owner name — prefer the alias to minimize the diff), then delete the local def. Confirm the local def is gone:
```bash
grep -nE '^def _typecheck_expected_extern_operand\b' orchestrator/workflow_lisp/typecheck_dispatch.py
```
Expected: no output.

- [ ] **Step 3 (per pair): Update the structure-lock test**

`tests/test_workflow_lisp_structured_results.py::test_effect_owner_split_moves_command_and_provider_typecheck_out_of_facade` (:94) already asserts these four names are absent from the facade top-level names:
```python
assert "_typecheck_expected_extern_operand" not in top_level_names
assert "_validate_command_argv" not in top_level_names
assert "_validate_semantic_command_adapter_usage" not in top_level_names
assert "_is_macro_introduced_effect" not in top_level_names
```
Those assertions target `_typecheck_top_level_names()` (the *facade*), which is already satisfied. Add a `dispatch_source`-level assertion per pair that the dispatch local def is gone, mirroring the file's existing `"... not in dispatch_source"` style — for the first pair:
```python
assert "def _typecheck_expected_extern_operand(" not in dispatch_source
```
Add the matching line as each pair lands. Run:
```bash
pytest --collect-only tests/test_workflow_lisp_structured_results.py
```

- [ ] **Step 4 (per pair): Verify**

```bash
python -c "import orchestrator.workflow_lisp.typecheck_dispatch"
pyflakes orchestrator/workflow_lisp/typecheck_dispatch.py
pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_expressions.py -q
```
Expected: PASS. `tests/test_workflow_lisp_structured_results.py` exercises command/provider/extern typing behaviorally, so a behavior change from picking the wrong twin surfaces here.

- [ ] **Step 5 (per pair): Commit** (one commit per pair; if a pair was stopped, skip its commit and note it)

```bash
git add orchestrator/workflow_lisp/typecheck_dispatch.py tests/test_workflow_lisp_structured_results.py
git commit -m "Retire dispatch-local extern operand typecheck for owner version"
```
(Analogous one-line messages for the other three: `Retire dispatch-local command argv validation for owner version`, `Retire dispatch-local semantic command adapter check for owner version`, `Retire dispatch-local macro-introduced effect check for owner version`.)

---

## Task 4 (brief increment 6): Extract the resume cluster into `typecheck_resume.py`

Move the `ResumeOrStartExpr` cluster (:2239-2459 of `_typecheck`, plus its dedicated helpers `_require_resume_binding` :2688, `_derive_resume_metadata` :2710, `_derive_resume_public_input_hash_basis` :2733, `_derive_resume_producer_fingerprint_basis` :2742) into a new owner module using the family handler convention. The cluster currently recurses via direct multi-kwarg `_typecheck(...)` calls (:2252-2265, :2278-2291) — **verified 12 kwargs, not 13**; every kwarg equals the dispatcher default, so each converts to a single-arg `recurse(node)` (mechanical, matches the already-delegated branches).

**Files:**
- Create: `orchestrator/workflow_lisp/typecheck_resume.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py` (replace the inlined `ResumeOrStartExpr` branch with a delegated call; delete the moved helpers)
- Modify: `orchestrator/workflow_lisp/typecheck.py` (drop the `_require_resume_binding`, `_derive_resume_metadata`, `_derive_resume_producer_fingerprint_basis`, `_derive_resume_public_input_hash_basis` re-exports at :23-31 if no live importer remains; verify with grep)
- Modify: a structure-lock test (see Step 4)

**Interfaces:** Produces `typecheck_resume_or_start_expr(expr, *, context, recurse, typed_factory)` returning `TypedExpr`; imports `typecheck_context` at module scope (for `raise_error`, `TypedExpr`, `_typed`, etc.), never imports `typecheck_dispatch`. The resume helpers (`_require_resume_binding`, `_derive_resume_*`) become module-private functions of `typecheck_resume.py`.

- [ ] **Step 1: Confirm the resume cluster is self-contained**

```bash
# Cross-references from the resume branch into other dispatch helpers:
sed -n '2239,2459p' orchestrator/workflow_lisp/typecheck_dispatch.py | grep -nE '_require_|_derive_|_typecheck\(|recurse\(|_typed\(|_type_label\(|_require_normative_phase_ctx_type|_require_phase_scope_name_match'
```
Decision rule: `_require_normative_phase_ctx_type` (:2462) and `_require_phase_scope_name_match` are shared dispatch helpers used by resume; they stay in dispatch and the resume module receives their results through `recurse`/`context` OR imports them if they are pure and phase-owned. Record which shared helpers resume depends on; if any is dispatch-private and NOT movable, pass it in via `context` or keep it importable. `_require_resume_binding`/`_derive_resume_*` are resume-only (verified their only call sites are inside the resume branch) and move wholesale.

- [ ] **Step 2: Create `typecheck_resume.py`**

Write the new module: module docstring, `from __future__ import annotations`, module-scope imports (`from .typecheck_context import TypedExpr, raise_error, _typed, _type_label` and the expression/type-env types the cluster uses — copy the exact type imports the cluster references from `typecheck_dispatch.py`), then `def typecheck_resume_or_start_expr(expr, *, context, recurse, typed_factory):` containing the moved body with each direct `_typecheck(node, type_env=..., ...)` rewritten to `recurse(node)`, and the four helper defs. Cross-reference the IDL contract in the implementation architecture docs per the repo convention (add a docstring pointer to `docs/design/README.md`'s typecheck-family entry).

- [ ] **Step 3: Delegate from dispatch**

Replace the `if isinstance(expr, ResumeOrStartExpr):` body (:2239) with:
```python
    if isinstance(expr, ResumeOrStartExpr):
        return typecheck_resume_or_start_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
```
Add `from .typecheck_resume import typecheck_resume_or_start_expr` to dispatch's imports. Delete `_require_resume_binding`, `_derive_resume_metadata`, `_derive_resume_public_input_hash_basis`, `_derive_resume_producer_fingerprint_basis` from dispatch. Confirm:
```bash
grep -nE '^def _require_resume_binding|^def _derive_resume_' orchestrator/workflow_lisp/typecheck_dispatch.py
```
Expected: no output. Then drop the now-orphaned facade re-exports in `typecheck.py` (verify no live importer first: `grep -rn '_require_resume_binding\|_derive_resume_' orchestrator/ tests/ | grep -v typecheck_resume`).

- [ ] **Step 4: Update the structure-lock test**

No existing lock test names the resume cluster. Add an assertion to the closest-fit facade lock test — `tests/test_workflow_lisp_expressions.py::test_typecheck_facade_reexports_public_entrypoints_after_owner_split` (:156) — in the established `dispatch_source` style:
```python
assert (package_dir / "typecheck_resume.py").is_file()
assert "if isinstance(expr, ResumeOrStartExpr):" in dispatch_source
assert "typecheck_resume_or_start_expr(" in dispatch_source
assert "def _require_resume_binding(" not in dispatch_source
```
(The `if isinstance(expr, ResumeOrStartExpr):` line remains — it now guards the delegating call, matching the workflow-refs lock test which asserts `"typecheck_call_expr(" in dispatch_source` alongside the retained guard. Confirm by reading how `test_workflow_ref_owner_split_...` pairs `"if isinstance(expr, CallExpr):" not in dispatch_source` with `"typecheck_call_expr(" in dispatch_source` — CallExpr uses `type(expr) is CallExpr` at the call site so its `isinstance` string is genuinely absent; for resume the guard stays as `isinstance`, so assert the delegate call presence, not guard absence.)
```bash
pytest --collect-only tests/test_workflow_lisp_expressions.py
```

- [ ] **Step 5: Verify**

```bash
python -c "import orchestrator.workflow_lisp.typecheck_resume, orchestrator.workflow_lisp.typecheck_dispatch, orchestrator.workflow_lisp.typecheck"
pyflakes orchestrator/workflow_lisp/typecheck_resume.py orchestrator/workflow_lisp/typecheck_dispatch.py
pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_phase_stdlib.py -q -k "resume or Resume or expression or facade"
pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py -q
```
Expected: imports OK; pyflakes silent; tests PASS. (Resume-or-start behavior is exercised through the phase-stdlib compile path.)

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow_lisp/typecheck_resume.py orchestrator/workflow_lisp/typecheck_dispatch.py \
        orchestrator/workflow_lisp/typecheck.py tests/test_workflow_lisp_expressions.py
git commit -m "Extract resume-or-start typecheck into owner module"
```

---

## Task 5 (brief increment 7): Extract the drain/phase cluster into `typecheck_drain_phase.py`; consolidate `_backlog_drain_blocker_class_type`

Move the drain/phase cluster (:1788-2238: `BacklogDrainExpr` :1788, `PhaseTargetExpr` :1961, `RunProviderPhaseExpr` :1977, `ProduceOneOfExpr` :2087) into a new owner module. **Verified drift from brief:** the `_require_union_variant_*` helpers (`_require_union_variant_field` :3137, `_require_union_variant_path_field` :3156, `_require_union_variant_exact_type` :3185, `_require_union_variant_exact_field_names` :3214) are consumed by the **drain/phase** cluster (BacklogDrainExpr body :1891-1929), NOT the resource/view cluster — the brief mis-assigned them to `typecheck_resource_view.py`. They move here with the drain/phase cluster. Also consolidate the duplicated `_backlog_drain_blocker_class_type` (dispatch :3119, 429ch vs `typecheck_calls.py:516`, 386ch — **differ by 43 chars; diff first**).

**Files:**
- Create: `orchestrator/workflow_lisp/typecheck_drain_phase.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py` (delegate the four branches; delete moved helpers)
- Possibly Modify: `orchestrator/workflow_lisp/typecheck_calls.py` (if the consolidated `_backlog_drain_blocker_class_type` owner lands there — see Step 1 decision)
- Modify: a structure-lock test (Step 5)

**Interfaces:** Produces four handlers `typecheck_backlog_drain_expr`, `typecheck_phase_target_expr`, `typecheck_run_provider_phase_expr`, `typecheck_produce_one_of_expr`, each `(expr, *, context, recurse, typed_factory) -> TypedExpr`; the `_require_union_variant_*` helpers become module-private to `typecheck_drain_phase.py`. Imports `typecheck_context` at module scope.

- [ ] **Step 1: Diff and consolidate `_backlog_drain_blocker_class_type`**

```bash
python - <<'EOF'
import ast, difflib
def seg(p, n):
    src = open(p).read()
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == n:
            return ast.get_source_segment(src, node).splitlines(keepends=True)
a = seg('orchestrator/workflow_lisp/typecheck_dispatch.py', '_backlog_drain_blocker_class_type')
b = seg('orchestrator/workflow_lisp/typecheck_calls.py', '_backlog_drain_blocker_class_type')
print(''.join(difflib.unified_diff(a, b, 'dispatch', 'calls', n=3)))
EOF
```
Decision rule: if the 43-char difference is a superset (one handles a blocker class the other omits, or one uses the migrated `raise_error` spelling) → keep the superset copy as the single owner. The natural home is `typecheck_calls.py` (already has a copy at :516 used by two call sites there :576,:656). If the dispatch copy is a strict subset of calls' copy, delete the dispatch copy and have `typecheck_drain_phase.py` import from `typecheck_calls`. If they diverge in behavior (not just spelling) → STOP and record. Record the resolution in the commit body.

- [ ] **Step 2: Create `typecheck_drain_phase.py`**

Write the module (docstring + IDL doc cross-reference, `from __future__ import annotations`, module-scope imports from `typecheck_context` and the expression/type-env/phase/resource types the cluster references — copy the exact imports the four branches use from dispatch, including the `phase`/`resource`/`phase_stdlib` imports the drain branch reaches). Move the four branch bodies into the four handlers (rewriting any direct `_typecheck(...)` into `recurse(...)`, though the drain/phase branches largely already use `recurse`/`context` since they are near the delegated region — confirm during the move). Move the four `_require_union_variant_*` helpers in as module-private functions. Resolve `_backlog_drain_blocker_class_type` per Step 1.

- [ ] **Step 3: Delegate from dispatch**

Replace the four `if isinstance(expr, <Node>):` bodies with delegating calls in the established shape (`return typecheck_<node>_expr(expr, context=context, recurse=recurse, typed_factory=_typed)`), add `from .typecheck_drain_phase import (...)` to dispatch, delete the four `_require_union_variant_*` helpers from dispatch, and delete the dispatch `_backlog_drain_blocker_class_type` if Step 1 consolidated onto calls. Confirm:
```bash
grep -nE '^def _require_union_variant_|^def _backlog_drain_blocker_class_type' orchestrator/workflow_lisp/typecheck_dispatch.py
```
Expected: no output (or only the survivor if you kept one here — but the plan direction is to move them out).

- [ ] **Step 4: Verify no orphaned union-variant references remain in dispatch**

```bash
grep -nE '_require_union_variant_' orchestrator/workflow_lisp/typecheck_dispatch.py
```
Expected: no output (all four helpers and their five call sites moved with the drain branch).

- [ ] **Step 5: Update the structure-lock test**

No existing lock test names the drain cluster by isinstance string. Extend `tests/test_workflow_lisp_expressions.py::test_typecheck_facade_reexports_public_entrypoints_after_owner_split` (or add a new focused test in the same file following the pattern) with:
```python
assert (package_dir / "typecheck_drain_phase.py").is_file()
assert "typecheck_backlog_drain_expr(" in dispatch_source
assert "def _require_union_variant_field(" not in dispatch_source
```
Run `pytest --collect-only tests/test_workflow_lisp_expressions.py`.

- [ ] **Step 6: Verify**

```bash
python -c "import orchestrator.workflow_lisp.typecheck_drain_phase, orchestrator.workflow_lisp.typecheck_dispatch, orchestrator.workflow_lisp.typecheck_calls"
pyflakes orchestrator/workflow_lisp/typecheck_drain_phase.py orchestrator/workflow_lisp/typecheck_dispatch.py orchestrator/workflow_lisp/typecheck_calls.py
pytest tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_expressions.py -q
```
Expected: PASS. (Backlog-drain and phase-target typing are exercised through `test_workflow_lisp_phase_stdlib.py` and `test_workflow_lisp_variant_proofs.py`.)

- [ ] **Step 7: Commit**

```bash
git add orchestrator/workflow_lisp/typecheck_drain_phase.py orchestrator/workflow_lisp/typecheck_dispatch.py \
        orchestrator/workflow_lisp/typecheck_calls.py tests/test_workflow_lisp_expressions.py
git commit -m "Extract drain and phase typecheck cluster into owner module"
```

---

## Task 6 (brief increment 8): Extract the resource/view cluster into `typecheck_resource_view.py`

Move the largest cluster (:1186-1787: `ResourceTransitionExpr` :1186, `MaterializeViewExpr` :1556, `FinalizeSelectedItemExpr` :1646, ~600 lines) into a new owner module, plus `_materialize_view_path_contracts_compatible` (:222, used at :1623 inside the `MaterializeViewExpr` branch). **Note:** the `_require_union_variant_*` helpers do NOT belong here (Task 5 corrected this — they serve drain/phase). Verify the resource/view cluster references no `_require_union_variant_*` before the move.

**Files:**
- Create: `orchestrator/workflow_lisp/typecheck_resource_view.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py` (delegate three branches; delete `_materialize_view_path_contracts_compatible`)
- Modify: a structure-lock test (Step 4)

**Interfaces:** Produces `typecheck_resource_transition_expr`, `typecheck_materialize_view_expr`, `typecheck_finalize_selected_item_expr`, each `(expr, *, context, recurse, typed_factory) -> TypedExpr`; `_materialize_view_path_contracts_compatible` becomes module-private. Imports `typecheck_context` + the `resource` module types at module scope.

- [ ] **Step 1: Confirm the cluster boundary and its dependencies**

```bash
sed -n '1186,1787p' orchestrator/workflow_lisp/typecheck_dispatch.py | grep -nE '_require_union_variant|_materialize_view_path_contracts_compatible|_typecheck\(|recurse\(|from \.'
```
Expected: `_materialize_view_path_contracts_compatible` referenced; NO `_require_union_variant_*` (verified). Record any dispatch-shared helper the cluster reaches (e.g. `_type_label` now in `typecheck_context` — import it) and the `resource` module imports it needs.

- [ ] **Step 2: Create `typecheck_resource_view.py`**

Write the module (docstring + IDL doc cross-reference, module-scope imports from `typecheck_context` and `resource`/`type_env`/`expressions` as the cluster requires — copy the exact imports the three branches use), move the three branch bodies into three handlers (rewrite any direct `_typecheck(...)` to `recurse(...)`), and move `_materialize_view_path_contracts_compatible` in as module-private.

- [ ] **Step 3: Delegate from dispatch**

Replace the three branch bodies with delegating calls (`return typecheck_resource_transition_expr(expr, context=context, recurse=recurse, typed_factory=_typed)`, etc.), add `from .typecheck_resource_view import (...)` to dispatch, delete `_materialize_view_path_contracts_compatible` from dispatch. Confirm:
```bash
grep -nE '^def _materialize_view_path_contracts_compatible' orchestrator/workflow_lisp/typecheck_dispatch.py
```
Expected: no output.

- [ ] **Step 4: Update the structure-lock test**

Extend the facade lock test in `tests/test_workflow_lisp_expressions.py` with:
```python
assert (package_dir / "typecheck_resource_view.py").is_file()
assert "typecheck_resource_transition_expr(" in dispatch_source
assert "typecheck_materialize_view_expr(" in dispatch_source
assert "def _materialize_view_path_contracts_compatible(" not in dispatch_source
```
Run `pytest --collect-only tests/test_workflow_lisp_expressions.py`.

- [ ] **Step 5: Verify (and confirm the target line count)**

```bash
python -c "import orchestrator.workflow_lisp.typecheck_resource_view, orchestrator.workflow_lisp.typecheck_dispatch"
pyflakes orchestrator/workflow_lisp/typecheck_resource_view.py orchestrator/workflow_lisp/typecheck_dispatch.py
wc -l orchestrator/workflow_lisp/typecheck_dispatch.py   # expect ~1,100 lines after all extractions
pytest tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_structured_results.py -q
```
Expected: PASS; `typecheck_dispatch.py` now ~1,100 lines (dispatcher + literals/refs + core control flow + shared phase helpers). Resource-transition / materialize-view / finalize-selected-item typing is exercised through `test_workflow_lisp_phase_stdlib.py` and the resource stdlib fixtures.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow_lisp/typecheck_resource_view.py orchestrator/workflow_lisp/typecheck_dispatch.py \
        tests/test_workflow_lisp_expressions.py
git commit -m "Extract resource and view typecheck cluster into owner module"
```

---

## Task 7 (2026-07-09 closeout amendment): Retire omitted dispatch-tail ownership residue

The first end-of-plan closeout found that Tasks 1-6 achieved their named
family extractions but could not achieve the plan's own dispatcher-size and
static-cleanliness goals. All 29 pyflakes findings reproduce at the pre-plan
revision, so they are baseline debt rather than regressions; nevertheless the
plan explicitly requires a silent pyflakes gate. The tail also contains two
live deferred-import round trips and eight helpers with zero repository
callers. This task closes only that measured gap; it does not redesign typing
semantics or move the retained `_typecheck` core-control-flow dispatcher.

**Files:**
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/loop_state.py`
- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/typecheck_calls.py`
- Modify: `orchestrator/workflow_lisp/typecheck_proofs.py`
- Modify: `tests/test_workflow_lisp_expressions.py`

- [ ] **Step 1: Add and run a failing ownership structure test.** Extend the
  existing typecheck owner-split structure test to require: no dispatch-local
  definitions for `_generated_procedure_signature`,
  `_generated_procedure_definition`, `_typecheck_generated_procedure`,
  `_register_generated_record_type`, `_register_generated_union_type`,
  `_generated_relpath_seed_expr`, `_resolve_field_access_impl`,
  `_validate_semantic_command_adapter_usage`, or
  `_temporary_procedure_catalog`; no deferred import of generated-record
  registration from `loop_state.py`; no deferred import of the temporary
  catalog from `procedure_typecheck.py`; and a dispatcher size of at most 1,250
  lines. Run collection, then the focused test and confirm it fails for the
  omitted ownership residue before changing production code.

- [ ] **Step 2: Move the two live helpers to their owners.** Move
  `_register_generated_record_type` (and its tiny `_type_name` helper) into
  `loop_state.py`, remove the deferred dispatch import, and call the local owner
  directly. Move `_temporary_procedure_catalog` into
  `procedure_typecheck.py`, remove `_temporary_procedure_catalog_owner`, and
  call the owner directly. Preserve signatures and bodies; add no compatibility
  re-export because repository-wide grep shows only the two owner call paths.

- [ ] **Step 3: Delete only proven-dead tail helpers.** Delete the seven
  zero-caller generated/union/field-access helpers named in Step 1 plus the
  dispatch-local semantic-command-adapter validator. The validator was retained
  by Task 3's semantic-difference STOP rule, but the closeout audit proves it
  has no caller; deleting dead code avoids choosing between the differing
  behaviors. Remove the dead `_generated_relpath_seed_expr` facade import.
  Re-run repository-wide greps before deletion; any newly discovered caller is
  a STOP-and-report condition.

- [ ] **Step 4: Clear the measured static residue.** Remove only the imports
  and duplicate binding reported by pyflakes in `typecheck_dispatch.py`,
  `typecheck_calls.py`, and `typecheck_proofs.py`. Do not make opportunistic
  formatting or ownership changes. `pyflakes` on the nine modules named by the
  end gate must be silent.

- [ ] **Step 5: Verify green before committing.** Run the focused ownership
  test, `pytest --collect-only tests/test_workflow_lisp_expressions.py`, import
  checks, pyflakes, the exact seven-module typecheck selector, and the Design
  Delta smoke. Confirm `typecheck_dispatch.py` is at most 1,250 lines.

- [ ] **Step 6: Commit.** Stage only the seven files listed above and commit
  with `Retire omitted typecheck dispatch tail residue`.

After Task 7, rerun the full suite in tmux. Compare its failure identities to
the six pre-plan failures recorded by the 2026-07-09 closeout audit.

---

## Verification strategy

**Per-task selectors (narrowest first, run after each task's edits):**

- Task 1: `pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_structured_results.py -q` + `pyflakes` on the four family modules.
- Task 2: `pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_procedures.py -q` + `pyflakes` on the six touched modules + `pytest --collect-only tests/test_workflow_lisp_expressions.py`.
- Task 3 (per pair): `pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_expressions.py -q` + `pytest --collect-only tests/test_workflow_lisp_structured_results.py`.
- Task 4: `pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py -q` and the resume-focused phase-stdlib slice + `pytest --collect-only tests/test_workflow_lisp_expressions.py`.
- Task 5: `pytest tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_expressions.py -q` + `pytest --collect-only tests/test_workflow_lisp_expressions.py`.
- Task 6: `pytest tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_structured_results.py -q` + `wc -l` gate (~1,100) + `pytest --collect-only tests/test_workflow_lisp_expressions.py`.

Each task also runs the relevant `pyflakes` on files it touched and a bare `python -c "import ..."` cycle check.

**End-of-plan full gate (run once after Task 6, long-running — use the tmux skill):**

```bash
pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py \
       tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_procedures.py \
       tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_phase_stdlib.py \
       tests/test_workflow_lisp_drain_stdlib.py -q
pytest -q   # full suite; compare failures-before vs failures-after if the tree carried pre-existing in-flight failures
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q -k "smoke"
```
Expected: all six structure-lock tests green (they now encode the full decomposition), full suite no new failures, certification smoke PASS. Report: lines removed from `typecheck_dispatch.py` (3,357 → ~1,100), the four new/updated owner modules, any duplicate pair that was STOPPED in Task 3, and the `_backlog_drain_blocker_class_type` consolidation resolution. Do not push; leave commits local for review.
