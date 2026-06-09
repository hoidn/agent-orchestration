# Workflow Lisp Loop/Recur On-Exhausted Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose optional authored `:on-exhausted` on public `loop/recur`, wiring ordinary local and imported `.orc` code onto the existing typed exhaustion-projection path without changing shared `repeat_until` runtime semantics.

**Architecture:** Keep the change frontend-local in `orchestrator/workflow_lisp/`. Reuse the existing `LoopRecurExpr.on_exhausted_result_expr` carrier, expression traversal, loop typecheck, and loop lowering through `repeat_until.on_exhausted.outputs` plus final typed normalization from loop-frame outputs. The real implementation delta is public elaboration of the optional `:on-exhausted` clause in `expressions.py`, with tests proving the generic authored route exists for both local and imported `.orc` code, preserves deterministic origin-map provenance, and no longer depends exclusively on the review-loop bridge.

**Tech Stack:** Python 3, the existing `orchestrator.workflow_lisp` compiler/typecheck/lowering pipeline, shared `repeat_until` validation/runtime reuse under `orchestrator.workflow`, pytest, and `.orc` fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these artifacts as implementation authority:

- `docs/index.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Section 13 `Loops`
  - Section 44 `Typed Frontend AST`
  - Section 59 `Validation Sequence`
  - Section 63 `Variant Proof Validation`
  - Section 74 `Source Map Requirements`
  - Section 95 `Lowering Tests`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - Section 12.1 `Authorable loop/recur :on-exhausted Dependency`
  - Section 18 `Loop Exhaustion Projection`
  - Stage 7 in the incremental implementation plan
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/work_item_context.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-loop-recur-on-exhausted-projection/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Current checkout facts that should not be rediscovered during execution:

- `docs/steering.md` is empty in this checkout and does not widen scope.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` has no events, so no later recorded implementation supersedes this slice.
- `orchestrator/workflow_lisp/expressions.py` already defines `LoopRecurExpr.on_exhausted_result_expr`, but `_elaborate_loop_recur(...)` still hard-codes the older authored arity and accepts only `:max`, `:state`, and one final loop-body `fn`.
- `orchestrator/workflow_lisp/typecheck_dispatch.py` already typechecks `on_exhausted_result_expr` for exact result-type equality and purity.
- `orchestrator/workflow_lisp/lowering/control_loops.py` already lowers `on_exhausted_result_expr` into `repeat_until.on_exhausted.outputs` and preserves final result reconstruction from loop-frame outputs.
- `orchestrator/workflow_lisp/expression_traversal.py` already walks `on_exhausted_result_expr` when present.
- `orchestrator/workflow_lisp/phase_stdlib_typecheck.py` still synthesizes `on_exhausted_result_expr` for the temporary review-loop bridge, so the bridge is currently the only producer of this field from authored source.
- `tests/test_workflow_lisp_loop_recur.py` already exists for the bounded loop surface, but there are no dedicated `loop_recur_on_exhausted_*` fixtures yet.

## Hard Scope Limits

Implement exactly this bounded prerequisite:

- add optional public authored `:on-exhausted` syntax to `loop/recur`;
- populate `LoopRecurExpr.on_exhausted_result_expr` directly from authored syntax;
- reuse existing loop typecheck rules for result-type equality, proof reset, and purity;
- reuse existing lowering to emit scalar-only `repeat_until.on_exhausted.outputs` and final typed normalization from loop-frame outputs;
- add focused elaboration, loop, lowering, source-map, imported-route, and bridge-regression coverage proving the generic route works without review-loop-only hidden injection.

Explicit non-goals:

- no runtime changes to `repeat_until`, loader semantics, checkpoints, or error classification;
- no redesign of `LoopRecurExpr`, shared Core AST, Semantic IR, Executable IR, state layout, or pointer authority;
- no general loop-state carrier authoring work; that remains the separate parametric loop-state prerequisite;
- no retirement of the review-loop bridge; this slice only removes its exclusivity;
- no new command adapters, inline shell/Python semantics, report parsing, or pointer-as-authority shortcuts;
- no broad refactor of loop lowering or typecheck modules unless a focused failing test proves a real authored-route bug.

Stop condition:

- if implementing public `:on-exhausted` requires new runtime behavior, imported `.orc` expansion work, or generalized loop-state authoring, stop and reopen the relevant prerequisite instead of widening this slice.

## File Ownership

Create:

- `tests/fixtures/workflow_lisp/valid/loop_recur_on_exhausted_record.orc`
- `tests/fixtures/workflow_lisp/valid/loop_recur_on_exhausted_union.orc`
- `tests/fixtures/workflow_lisp/invalid/loop_recur_on_exhausted_impure.orc`
- `tests/fixtures/workflow_lisp/invalid/loop_recur_on_exhausted_type_mismatch.orc`
- `tests/fixtures/workflow_lisp/invalid/loop_recur_on_exhausted_non_scalar_override.orc`
- `tests/fixtures/workflow_lisp/modules/valid/imported_loop_recur_on_exhausted/entry.orc`
- `tests/fixtures/workflow_lisp/modules/valid/imported_loop_recur_on_exhausted/helper.orc`
- `tests/fixtures/workflow_lisp/modules/valid/imported_loop_recur_on_exhausted/types.orc`

Modify:

- `orchestrator/workflow_lisp/expressions.py`
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_loop_recur.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_phase_stdlib.py`

Inspect and keep unchanged unless a targeted failing test proves the need:

- `orchestrator/workflow_lisp/expression_traversal.py`
- `orchestrator/workflow_lisp/typecheck_dispatch.py`
- `orchestrator/workflow_lisp/lowering/control_loops.py`
- `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`
- `tests/test_loader_validation.py`
- `orchestrator/workflow_lisp/form_registry.py`

Do not modify:

- shared runtime or loader modules under `orchestrator/workflow/`
- `specs/`
- unrelated review-loop, parametric-loop-state, or imported-stdlib substrate docs and code

## Required Behavioral Contract

Keep these rules fixed during implementation:

- public `loop/recur` accepts one optional keyword clause: `:on-exhausted <expr>`;
- `:max` and `:state` remain required;
- the loop-body `fn` remains the final positional child of `loop/recur`;
- missing `:on-exhausted` preserves ordinary `repeat_until_iterations_exhausted` runtime failure behavior;
- authored exhaustion expressions must have exactly the same type as the reachable `done` result;
- authored exhaustion expressions must be pure;
- lowering may write only scalar fields into `repeat_until.on_exhausted.outputs`;
- non-scalar result data must continue to come from loop-frame outputs during final normalization;
- source maps for the authored exhaustion expression and generated loop/result steps must remain deterministic;
- bridge-owned review-loop injection may remain temporarily, but the public authored route must become an equivalent generic producer of the same field.

## Task 1: Freeze The Missing Surface With Fixtures And Failing Tests

**Files:**

- Create: `tests/fixtures/workflow_lisp/valid/loop_recur_on_exhausted_record.orc`
- Create: `tests/fixtures/workflow_lisp/valid/loop_recur_on_exhausted_union.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/loop_recur_on_exhausted_impure.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/loop_recur_on_exhausted_type_mismatch.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/loop_recur_on_exhausted_non_scalar_override.orc`
- Create: `tests/fixtures/workflow_lisp/modules/valid/imported_loop_recur_on_exhausted/entry.orc`
- Create: `tests/fixtures/workflow_lisp/modules/valid/imported_loop_recur_on_exhausted/helper.orc`
- Create: `tests/fixtures/workflow_lisp/modules/valid/imported_loop_recur_on_exhausted/types.orc`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] Add two valid fixtures that lock the authored surface.

`loop_recur_on_exhausted_record.orc` should use a record result with scalar exhaustion markers and validate through the existing loop-frame reconstruction path.

`loop_recur_on_exhausted_union.orc` should use a union result so the final projection still depends on loop-frame outputs rather than direct non-scalar exhaustion overrides.

- [ ] Add one imported-module fixture tree that proves an imported helper can author the same surface.

Use `tests/fixtures/workflow_lisp/modules/valid/imported_loop_recur_on_exhausted/entry.orc` as the thin caller and make `helper.orc` the module that actually authors `loop/recur :on-exhausted`. Keep `types.orc` limited to the minimal record or union definitions needed by that helper. The imported proof is only valid if the helper, not the local entrypoint, owns the authored exhaustion clause and the fixture compiles through the normal imported-module path.

- [ ] Add three invalid fixtures for the bounded failure modes.

Use:

- impure exhaustion expression
- exhaustion expression result-type mismatch
- exhaustion expression that would require a disallowed direct non-scalar `repeat_until.on_exhausted.outputs` override

Keep failure fixtures narrowly targeted to this contract. Do not mix them with unrelated loop-body errors already covered elsewhere.

- [ ] Extend elaboration tests before implementation.

Add or extend tests in `tests/test_workflow_lisp_expressions.py` for:

- `test_elaborate_expression_supports_loop_recur_on_exhausted`
- rejection when `:on-exhausted` is malformed or the loop body is no longer the final positional form
- confirmation that the authored exhaustion expression lands on `LoopRecurExpr.on_exhausted_result_expr`

- [ ] Extend loop and lowering tests before implementation.

Add failing tests in `tests/test_workflow_lisp_loop_recur.py` and `tests/test_workflow_lisp_lowering.py` for:

- valid authored `:on-exhausted` compile path
- imported-helper authored `:on-exhausted` compile path
- compile-time rejection of impure exhaustion expressions
- compile-time rejection of result-type mismatch
- lowering of scalar exhaustion markers into `repeat_until.on_exhausted.outputs`
- preservation of non-scalar reconstruction through loop-frame outputs
- direct origin-map coverage for the authored exhaustion form and generated loop/result steps
- imported-route origin-map coverage that records the imported helper path on generated exhaustion/result steps

Suggested test names:

```python
test_elaborate_expression_supports_loop_recur_on_exhausted
test_typecheck_loop_recur_rejects_impure_on_exhausted
test_typecheck_loop_recur_rejects_on_exhausted_type_mismatch
test_compile_stage3_imported_loop_recur_on_exhausted_helper_validates
test_lowering_loop_recur_emits_repeat_until_on_exhausted_outputs
test_lowering_loop_recur_rejects_non_scalar_on_exhausted_override
test_lowering_loop_recur_on_exhausted_preserves_origin_map_for_generated_steps
test_lowering_imported_loop_recur_on_exhausted_helper_preserves_origin_map
test_loop_recur_on_exhausted_fixture_validates_through_shared_repeat_until
```

- [ ] Run collection checks before editing compiler behavior.

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_expressions.py -q
python -m pytest --collect-only tests/test_workflow_lisp_loop_recur.py -q
python -m pytest --collect-only tests/test_workflow_lisp_lowering.py -q
python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py -q
```

Expected:

- collection succeeds;
- the new `on_exhausted`, imported-route, and source-map tests collect cleanly;
- any failures after this point are implementation failures, not collection/import errors.

## Task 2: Add The Public `:on-exhausted` Elaboration Route

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`

- [ ] Update `_elaborate_loop_recur(...)` to parse the final positional body separately from keyword sections.

Implementation requirements:

- stop assuming `len(datum.items) == 6`;
- require at least `loop/recur`, one or more keyword items, and a final body form;
- parse keyword sections from `datum.items[1:-1]`;
- keep the final item reserved for the loop-body `fn`.

- [ ] Accept optional `:on-exhausted` as a peer of `:max` and `:state`.

Populate `LoopRecurExpr.on_exhausted_result_expr` by elaborating the authored exhaustion expression in the same pre-loop binding environment used for `:max` and `:state`. Do not introduce a new AST node, request kind, or bridge-only compatibility form.

- [ ] Preserve stable diagnostics and provenance.

Keep existing authored diagnostics centered on:

- `loop_recur_contract_invalid`
- `loop_recur_fn_invalid`

Every error must still point at the authored `loop/recur` span/form path rather than generated lowering internals. Preserve the authored expression's span, form path, and expansion stack on the resulting `on_exhausted_result_expr`.

- [ ] Re-run the focused elaboration tests immediately after the parser/elaborator change.

Run:

```bash
python -m pytest tests/test_workflow_lisp_expressions.py -k "loop_recur and on_exhausted" -q
```

Expected:

- the new elaboration tests pass;
- previously existing `loop/recur` elaboration tests remain green.

## Task 3: Reuse Existing Typecheck And Lowering, Fixing Only Real Authored-Route Gaps

**Files:**

- Inspect first: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Inspect first: `orchestrator/workflow_lisp/lowering/control_loops.py`
- Inspect first: `orchestrator/workflow_lisp/expression_traversal.py`
- Modify only if a targeted failing test proves the need

- [ ] Run the new loop tests after elaboration lands, before changing typecheck or lowering code.

Run:

```bash
python -m pytest tests/test_workflow_lisp_loop_recur.py -k "exhaustion or on_exhausted or repeat_until_iterations_exhausted" -q
```

Expected:

- if the only missing behavior was elaboration, most or all new tests should now pass without touching typecheck or lowering;
- any remaining failures should reveal a concrete authored-route mismatch, not justify speculative refactors.

- [ ] Keep `typecheck_dispatch.py` unchanged unless the new authored route exposes a real bug.

The existing logic already enforces:

- exact type equality between `done` and `:on-exhausted`;
- purity of the exhaustion projection;
- fresh proof scope for loop-body and exhaustion expressions.

Only edit this file if a failing test shows authored provenance or error targeting is wrong once the clause becomes public.

- [ ] Keep `expression_traversal.py` unchanged unless child ordering or coverage fails.

Traversal already includes `on_exhausted_result_expr`. Only touch it if a specific traversal/source-map test proves the new authored field is skipped or ordered incorrectly.

- [ ] Keep `lowering/control_loops.py` unchanged unless a failing test proves the authored route is not equivalent to the bridge route.

If changes are required, keep them minimal and preserve these invariants:

- omit `repeat_until.on_exhausted` entirely when no clause is authored;
- emit only scalar exhaustion overrides;
- continue final union/record reconstruction from loop-frame outputs;
- preserve deterministic step naming and recorded origins.

- [ ] Add or tighten lowering assertions in tests.

Use `tests/test_workflow_lisp_loop_recur.py` and `tests/test_workflow_lisp_lowering.py` to assert:

- authored `:on-exhausted` produces a `repeat_until.on_exhausted.outputs` mapping;
- scalar markers such as status/reason flow through that mapping;
- non-scalar result fields still come from the final projection step rather than direct exhaustion overrides;
- the generated `__loop` and `__result` steps remain present in `origin_map.step_spans`;
- at least one generated exhaustion-related origin preserves the authored `:on-exhausted` form path and span rather than falling back to workflow-level provenance;
- the imported helper fixture records origin-map spans whose source path ends with `imported_loop_recur_on_exhausted/helper.orc`;
- a valid authored fixture compiles with `validate_shared=True`, satisfying the end-to-end usage expectation from Section 95 of the frontend specification.

- [ ] Re-run focused lowering and bridge-adjacent tests once authored lowering is correct.

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_stdlib.py -k "loop_recur or review_loop or on_exhausted or repeat_until" -q
```

Expected:

- authored `loop/recur :on-exhausted` lowering passes;
- imported helper-authored `loop/recur :on-exhausted` lowering passes with imported provenance intact;
- existing review-loop lowering behavior remains unchanged during the transition.

## Task 4: Prove Transitional Compatibility And Final Verification

**Files:**

- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Inspect: `tests/test_loader_validation.py`

- [ ] Add one explicit bridge-regression test in `tests/test_workflow_lisp_phase_stdlib.py`.

The point of this test is not to keep the bridge forever. It is to prove that after public `:on-exhausted` lands, the bridge is merely another producer of the same generic field rather than a separate semantic route.

The regression should compile the existing phase stdlib fixture and assert that the lowered `repeat_until` still carries the expected `on_exhausted.outputs` surface. Do not assert prompt text or other brittle bridge internals.

- [ ] Add one direct source-map acceptance assertion tied to the new public surface.

Place this in `tests/test_workflow_lisp_lowering.py` unless an existing helper in another module is a better fit. Assert at minimum that:

- the authored local `loop/recur :on-exhausted` fixture leaves the generated `__loop` and `__result` steps in `origin_map.step_spans`;
- at least one generated step or output tied to exhaustion projection preserves the authored exhaustion form's span and form path;
- the imported helper fixture shows generated provenance from `imported_loop_recur_on_exhausted/helper.orc`.

This closes the explicit Section 74 and work-item acceptance requirement that source-map coverage include both the authored exhaustion expression and the generated loop/result steps.

- [ ] Use the shared loader validation test as runtime-surface confirmation, not as a place to introduce new semantics.

Re-run the existing loader validation selector:

```bash
python -m pytest tests/test_loader_validation.py -k "repeat_until_on_exhausted" -q
```

This is verification evidence that the authored frontend route still targets the same shared runtime contract already validated for `repeat_until.on_exhausted`.

- [ ] Run the full deterministic command set from the work-item context, plus repo-policy collect-only selectors for every edited test module, before closing the slice.

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_expressions.py -q
python -m pytest --collect-only tests/test_workflow_lisp_loop_recur.py -q
python -m pytest --collect-only tests/test_workflow_lisp_lowering.py -q
python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py -q
python -m pytest tests/test_workflow_lisp_expressions.py -k "loop_recur and on_exhausted" -q
python -m pytest tests/test_workflow_lisp_loop_recur.py -k "exhaustion or on_exhausted or repeat_until_iterations_exhausted" -q
python -m pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_stdlib.py -k "loop_recur or review_loop or on_exhausted or repeat_until" -q
python -m pytest tests/test_loader_validation.py -k "repeat_until_on_exhausted" -q
```

- [ ] Record completion evidence in the implementation summary.

Document:

- which files changed;
- whether `typecheck_dispatch.py`, `lowering/control_loops.py`, and `expression_traversal.py` stayed unchanged or needed minimal authored-route fixes;
- which new local and imported fixtures prove ordinary authored code can reach typed exhaustion projection without bridge-only injection;
- which origin-map assertions proved authored and imported exhaustion provenance remained source-mapped;
- the exact command outputs used as verification evidence.
