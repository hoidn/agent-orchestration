# Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` task by task,
> `superpowers:test-driven-development` for every behavior change, and
> `superpowers:verification-before-completion` before claiming a task or the
> plan complete. Do not create a worktree; this repository forbids worktrees.
> Track execution with the checkbox steps below.

**Goal:** Implement target DSL 2.26 so Workflow Lisp `if` and `cond` accept any
expression whose final static type is exactly `Bool`, execute condition effects
left to right and at most once, short-circuit `and`/`or`, and derive sound
branch-local union proof from typed `.variant` comparisons.

**Architecture:** Add one target-gated typed-frontend normalization pass. It
rewrites effectful operands to compiler-owned `let*` bindings, rewrites Boolean
short circuit and temporary `cond` clauses to ordinary nested `IfExpr`, and
carries singleton branch proof into existing WCC `proof_context`,
`requires_variant`, and checkpoint surfaces. Reuse the existing control join,
pure projection, `WccIf`, state 2.1, Semantic IR, Executable IR, and executor;
do not add a runtime `cond` or another control/evidence model.

**Tech Stack:** Python 3.11+, immutable Workflow Lisp AST/type references,
target DSL 2.26 with target-2.25 compatibility controls, WCC M4, state schema
2.1, pytest/pytest-xdist, deterministic fake providers and commands.

---

## Authority, Scope, And Cost

Read before editing:

- `AGENTS.md`;
- `docs/index.md`;
- `docs/capability_status_matrix.md`;
- `docs/design/README.md`;
- `docs/design/workflow_lisp_strict_boolean_control_flow.md`;
- `docs/design/workflow_lisp_frontend_specification.md`;
- `docs/design/workflow_lisp_proof_graph.md`;
- `docs/design/workflow_language_design_principles.md`;
- `specs/dsl.md`, `specs/versioning.md`, and `specs/state.md`.

The accepted design at commits `6ab34306`, `1b20b29e`, and `2da95dfd` is the
feature authority. Normative specs remain authoritative for already-runnable
targets. If this plan conflicts with either, stop and correct the plan rather
than interpreting the conflict in code.

The deliberately minimal route makes two future features harder: a cond-native
runtime visualization and general alias/correlation-aware occurrence typing.
Clause source maps cover the former; the latter is explicitly outside 2.26.
Do not add either preemptively.

This plan does not remove `match`, add truthiness, infer proof from arbitrary
Boolean functions, add a public discriminant type, or alter provider/command
contracts.

## Execution Contract And Hard Stops

Run every command from the repository root. Preserve unrelated worktree
changes and stage only the exact files owned by the current task. Before every
commit, inspect `git status --short` and `git diff --check`.

For each task:

1. dispatch one implementation subagent with only that task's file ownership;
2. add the smallest behavioral test and run it to observe the intended RED;
3. implement the minimum shared correction;
4. run the task's narrow GREEN and adjacent regressions;
5. collect every new or renamed test module explicitly;
6. request specification-compliance review, resolve material findings, then
   request a distinct implementation-quality review; and
7. commit only the reviewed task paths.

Stop and return to the owner/design if any feasibility fixture requires:

- a new public Core/Semantic/Executable IR node or envelope version;
- a condition-specific runtime node or state family;
- eager execution of a skipped `and`/`or` operand;
- state schema newer than 2.1; or
- weakening runtime variant validation.

The proof task has an additional stop: first test a workflow-input/local union
and a single consumer needing two independent union proofs. Reuse separate
existing guarded leaf/projection steps if that represents both cases. If the
current single-producer `requires_variant` contract still cannot represent
either case, stop and amend the accepted design before broad proof
implementation. Do not silently limit `.variant` proof to provider results.

## Preflight

- [ ] Confirm the accepted design is present and record the starting HEAD:

  ```sh
  git status --short
  git log -1 --oneline
  git log --oneline -- docs/design/workflow_lisp_strict_boolean_control_flow.md
  ```

- [ ] Run the existing manually desugared feasibility control:

  ```sh
  pytest -q tests/test_workflow_lisp_native_returns_e2e.py::test_provider_root_bool_result_drives_branching_persists_and_resumes
  ```

  Expected: `1 passed`. If it fails, diagnose the baseline before editing this
  feature.

## Task 1: Admit Target 2.26 And Reserve Temporary `cond`

**Files:**

- Modify: `orchestrator/workflow_lisp/syntax.py`
- Modify: `orchestrator/workflow/validation.py`
- Modify: `orchestrator/workflow_lisp/form_registry.py`
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/expression_traversal.py`
- Modify only if traversal requires it before typechecking:
  `orchestrator/workflow_lisp/functions.py`,
  `orchestrator/workflow_lisp/procedure_typecheck.py`, and
  `orchestrator/workflow_lisp/result_guidance.py`
- Modify cumulative 2.25 feature gates:
  `orchestrator/workflow/run_ref/config.py`,
  `orchestrator/workflow/run_ref/path_compile.py`,
  `orchestrator/workflow/run_ref/bundle_transport.py`,
  `orchestrator/workflow/trial/config.py`,
  `orchestrator/workflow/trial/sdk.py`,
  `orchestrator/workflow_lisp/contracts.py`,
  `orchestrator/workflow_lisp/workflows.py`, and
  `orchestrator/workflow_lisp/lowering/core.py`
- Test: `tests/test_workflow_lisp_strict_boolean_control_flow.py`
- Test: `tests/test_workflow_lisp_e1_normative_contract.py`
- Test: `tests/test_workflow_lisp_e2_trial_contract.py`
- Test: `tests/test_workflow_shared_validation.py`

- [ ] Add RED coverage showing:

  ```lisp
  ;; 2.26 reserves cond and retains its source spans.
  (cond
    (true "yes")
    (else "no"))
  ```

  Assert malformed clauses, multiple/non-final `else`, and more than one
  result expression receive stable `cond_*` diagnostics. Assert a declared
  function/procedure named `cond` still resolves normally at target 2.25, while
  target 2.26 selects the special form. Extend the traversal inventory lock for
  the temporary node.

- [ ] Replace the two tests named `test_target_2_26_remains_fail_closed` with a
  2.26 admission assertion and a next-version (`2.27`) fail-closed assertion.
  Add a target-2.26 shared-loader validation assertion.

- [ ] Run RED:

  ```sh
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow.py \
    -k 'version or syntax or reservation or malformed'
  pytest -q \
    tests/test_workflow_lisp_e1_normative_contract.py \
    tests/test_workflow_lisp_e2_trial_contract.py
  pytest -q tests/test_workflow_shared_validation.py -k 'supported_version'
  ```

  Expected: 2.26 is unsupported and `cond` is not registered.

- [ ] Add `2.26` to both frontend and shared validation version catalogs. Add
  one `STRICT_BOOLEAN_CONTROL_FLOW_MIN_TARGET_DSL_VERSION = "2.26"` helper and
  reuse existing numeric target comparison; do not scatter new exact-version
  checks.

- [ ] Add a target-gated `cond` form spec (`min_target_dsl_version="2.26"`,
  `macro_bindable=False`) and make macro reservation query
  `reserved_macro_names(target_dsl_version=...)` instead of relying on the
  static ungated set. Keep unavailable-form fallback through ordinary
  function/procedure resolution.

- [ ] Add parser/elaboration-local immutable `CondClause` and `CondExpr`
  containers plus `_elaborate_cond`. Validate only syntax here; retain a
  missing-else marker for type-aware exhaustiveness. Add only the pre-typecheck
  traversals needed to reach typechecking. No WCC or lowerer may learn a
  `cond` case.

- [ ] Audit every exact `2.25` gate found by:

  ```sh
  rg -n '== "2\.25"|!= "2\.25"|\{"2\.24", "2\.25"\}' orchestrator
  ```

  Convert cumulative nested-transport and trial compiler gates to their
  existing minimum-version predicates so 2.26 inherits 2.25. Preserve an exact
  2.25 restriction only where a public API is intentionally version-specific,
  and lock that exception with a test and comment.

- [ ] Run GREEN and collection:

  ```sh
  pytest --collect-only -q tests/test_workflow_lisp_strict_boolean_control_flow.py
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow.py \
    -k 'version or syntax or reservation or malformed'
  pytest -q \
    tests/test_workflow_lisp_e1_normative_contract.py \
    tests/test_workflow_lisp_e2_trial_contract.py
  pytest -q tests/test_workflow_shared_validation.py -k 'supported_version'
  pytest -q \
    tests/test_workflow_lisp_expressions.py::test_expression_traversal_direct_child_classification_matches_exprnode_union
  ```

- [ ] Commit exact task files:

  ```sh
  git add orchestrator/workflow_lisp/syntax.py orchestrator/workflow/validation.py \
    orchestrator/workflow_lisp/form_registry.py orchestrator/workflow_lisp/macros.py \
    orchestrator/workflow_lisp/expressions.py orchestrator/workflow_lisp/expression_traversal.py \
    orchestrator/workflow/run_ref/config.py orchestrator/workflow/run_ref/path_compile.py \
    orchestrator/workflow/run_ref/bundle_transport.py orchestrator/workflow/trial/config.py \
    orchestrator/workflow/trial/sdk.py \
    orchestrator/workflow_lisp/contracts.py orchestrator/workflow_lisp/workflows.py \
    orchestrator/workflow_lisp/lowering/core.py \
    tests/test_workflow_lisp_strict_boolean_control_flow.py \
    tests/test_workflow_lisp_e1_normative_contract.py \
    tests/test_workflow_lisp_e2_trial_contract.py tests/test_workflow_shared_validation.py
  git commit -m "Admit Workflow Lisp target 2.26 control syntax"
  ```

  Add any actually modified pre-typecheck traversal owner explicitly; do not
  stage it speculatively.

## Task 2: Normalize Arbitrary Strict-Boolean Conditions

**Files:**

- Modify: `orchestrator/workflow_lisp/conditionals.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck_pure_ops.py`
- Modify: `orchestrator/workflow_lisp/lowering/pure_projection.py`
- Modify only if the normalized invariant needs generic join support:
  `orchestrator/workflow_lisp/wcc/elaborate.py` and
  `orchestrator/workflow_lisp/wcc/anf.py`
- Test: `tests/test_workflow_lisp_strict_boolean_control_flow.py`
- Test: `tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py`
- Regression: `tests/test_workflow_lisp_expressions.py`
- Regression: `tests/test_workflow_lisp_native_returns_e2e.py`

- [ ] Add the first three accepted feasibility scenarios as RED tests:

  ```lisp
  ;; Linear extraction: no authored pre-binding.
  (if (= (provider-result providers.review
           :prompt prompts.review
           :inputs ()
           :returns ReviewDecision)
         ReviewDecision.APPROVE)
      (command-result accept
        :argv ("python" "scripts/accept.py")
        :returns Bool)
      (command-result revise
        :argv ("python" "scripts/revise.py")
        :returns Bool))

  ;; Later effects must not execute when dynamically short-circuited.
  (and
    (command-result stop-after-false
      :argv ("python" "scripts/return_false.py")
      :returns Bool)
    (command-result must-not-run
      :argv ("python" "scripts/must_not_run.py")
      :returns Bool))
  (or
    (provider-result providers.stop-after-true
      :prompt prompts.stop-after-true
      :inputs ()
      :returns Bool)
    (provider-result providers.must-not-run
      :prompt prompts.must-not-run
      :inputs ()
      :returns Bool))

  ;; A nested control value remains branch-local.
  (= (if (command-result choose-left
           :argv ("python" "scripts/choose_left.py")
           :returns Bool)
         (command-result left-value
           :argv ("python" "scripts/left_value.py")
           :returns Int)
         (command-result right-value
           :argv ("python" "scripts/right_value.py")
           :returns Int))
     1)
  ```

  Assert authored evaluation order and one invocation per reached effect.
  Dynamically skipped projected nodes must retain the ordinary durable
  `status: skipped` settlement row required by state 2.1, with no visit,
  provider/command attempt, checkpoint, or execution-value payload. A
  statically eliminated operand has no node or row. Assert the selected outer
  branch only and clean/resume equivalence. Force a failure after the condition
  settles and prove resume does not repeat it.

- [ ] Add strictness/failure RED tests: a direct provider/procedure/workflow
  call returning `Bool` is accepted; `Int`, `String`, enum, record, union, and
  `Value` conditions are rejected with `if_condition_not_bool`; an executed
  invalid/failing condition effect fails before either branch runs. Retain
  target-2.25 `if_condition_has_effect` and
  `if_condition_not_projectable` controls.

- [ ] Run RED:

  ```sh
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow.py -k 'strict or linear or short_circuit or nested_control'
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py -k 'linear or short_circuit or nested_control or failure'
  ```

- [ ] Implement one target-2.26 condition normalizer in `conditionals.py`.
  Its typed result must contain the normalized expression, exact type/effect
  summary, and true/false path environments for Task 3. Use stable generated
  names derived from authored form path and operand index.

  Required rewrite rules:

  ```text
  effect/control operand -> compiler-owned let* binding, once, in source order
  (and A B ...)          -> nested if; evaluate next operand only on true
  (or A B ...)           -> nested if; evaluate next operand only on false
  (not A)                -> one evaluation followed by Boolean inversion
  nested if value        -> existing non-linear let binding and WCC join
  terminal Bool          -> literal/ref or existing pure_projection
  ```

  Normalize all target-2.26 `and`/`or`, including pure operands, because the
  shared pure evaluator is eager. Do not change the runtime pure-expression
  evaluator.

- [ ] At target 2.26, remove only `if`'s special purity/projectability and
  run-ref-effect refusals. All expression-owned placement and contract rules
  remain. Include condition effects in the enclosing effect summary and check
  only the exact final `Bool` type. Below 2.26, retain the current checker byte
  behavior.

- [ ] Feed WCC only normalized shapes. First reuse
  `_elaborate_control_binding_to_body` for nested control results. Modify WCC
  only if a generic normalized value still cannot reach the existing join;
  assert that no effectful `and`/`or` reaches `_elaborate_expr_to_value` or the
  eager ANF pure-op path.

- [ ] Run GREEN, collection, and adjacent regressions:

  ```sh
  pytest --collect-only -q \
    tests/test_workflow_lisp_strict_boolean_control_flow.py \
    tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow.py \
    -k 'strict or linear or short_circuit or nested_control'
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py \
    -k 'linear or short_circuit or nested_control or failure'
  pytest -q \
    tests/test_workflow_lisp_expressions.py::test_typecheck_expression_accepts_pure_ops_and_computed_if \
    tests/test_workflow_lisp_wcc_characterization.py::test_wcc_ifexpr_non_tail_binding_uses_control_join_without_unsupported_rewrite \
    tests/test_workflow_lisp_native_returns_e2e.py::test_provider_root_bool_result_drives_branching_persists_and_resumes
  pytest -q tests/test_workflow_pure_expr.py \
    -k 'and_bool or or_bool or not_bool'
  ```

- [ ] Stop for design revision if any of the first three fixtures requires a
  new runtime/public-IR form. Otherwise commit the exact modified paths:

  ```sh
  git add orchestrator/workflow_lisp/conditionals.py \
    orchestrator/workflow_lisp/typecheck_dispatch.py \
    orchestrator/workflow_lisp/typecheck_pure_ops.py \
    orchestrator/workflow_lisp/lowering/pure_projection.py \
    tests/test_workflow_lisp_strict_boolean_control_flow.py \
    tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py
  git commit -m "Normalize strict Boolean Workflow Lisp conditions"
  ```

  Add `orchestrator/workflow_lisp/wcc/elaborate.py` or
  `orchestrator/workflow_lisp/wcc/anf.py` only if the reviewed implementation
  actually changes it.

## Task 3: Prove Union Narrowing End To End

Task 3A and Task 3B are one atomic feasibility tranche owned by one subagent.
Do not commit between them: the guard-shape probes must pass before the broad
proof model becomes a retained change.

### Task 3A: Add Contextual Tags And The Minimum Guard Vertical Slice

**Files:**

- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/typecheck_context.py`
- Modify: `orchestrator/workflow_lisp/typecheck_proofs.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck_pure_ops.py`
- Modify: `orchestrator/workflow_lisp/conditionals.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Test: `tests/test_workflow_lisp_strict_boolean_control_flow.py`
- Test: `tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py`
- Regression: `tests/test_workflow_lisp_variant_proofs.py`

- [ ] Before any production edit, add RED fixtures for all three guard shapes:

  1. one provider-produced union narrowed by `=` and consumed in its branch;
  2. one workflow-input or ordinary-local union narrowed and consumed; and
  3. one leaf effect consuming fields narrowed from two different unions.

  Run them together:

  ```sh
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow.py \
    -k 'requires_variant or input_union or multi_union'
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py \
    -k 'proof_guard or contradiction'
  ```

- [ ] Build only the smallest equality-owned vertical slice needed to carry
  those cases from `.variant` typing through one existing guarded leaf or pure
  projection. Do not implement `!=`, Boolean-composition proof, joins, or
  checkpoint generalization yet. If separate existing guarded projections
  cannot represent the input/local and two-proof cases without a public
  guard/state/runtime change, stop, report the exact failing shape, and amend
  the design and plan. Only after all three shapes lower with existing
  contracts may the remaining steps in 3A proceed.

- [ ] Add RED tests for the closed fact algebra:

  ```lisp
  (= attempt.variant COMPLETED)
  (= COMPLETED attempt.variant)
  (!= attempt.variant BLOCKED)
  (and (= attempt.variant COMPLETED)
       attempt.approved)
  (or (!= attempt.variant BLOCKED)
      (= attempt.variant COMPLETED))
  (not (= attempt.variant BLOCKED))
  ```

  Cover true and false paths, exclusion-to-singleton inference, contradiction
  and unreachable paths, variadic left-to-right composition, and conservative
  joins. A non-recognized Boolean expression must route without narrowing.

- [ ] Add lexical-safety RED tests: same-spelling shadowed `let*` bindings have
  distinct identities; an alias is a fresh identity and receives no proof;
  an existing lexical binding named `COMPLETED` wins over contextual tag
  lookup; unknown, context-free, and cross-union tags fail with their designed
  diagnostics. Compatible discriminant-to-discriminant equality routes but
  proves no variant.

- [ ] Run RED:

  ```sh
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow.py -k 'variant or proof or shadow or alias or contextual'
  pytest -q tests/test_workflow_lisp_variant_proofs.py
  ```

- [ ] Represent a discriminant with an internal nominal type tied to its union.
  Prefer the existing compiler-owned `PrimitiveTypeRef.allowed_values` surface
  if it preserves union identity; otherwise add the smallest private type ref.
  `.variant` is read-only and lowers to the canonical `variant` artifact. It is
  not a source-nameable type.

- [ ] In equality typing, type the contextual operand before ordinary unbound
  `NameExpr` rejection. Resolve a bare tag only when the opposite operand is a
  compatible discriminant and normal lexical resolution failed. Rewrite it to
  a compiler-owned literal/tag representation understood by pure projection.

- [ ] Replace spelling-keyed proof with:

  ```python
  BindingIdentity -> PossibleVariants(frozenset[str])
  ```

  Keep a lexical `name -> BindingIdentity` environment. Allocate stable root,
  parameter, arm, and `let*` binding identities from form path plus binder
  ordinal. Joins union possible sets; an empty set is unreachable; only a
  singleton authorizes a variant-only field. Preserve `match` by expressing
  each arm as the same singleton fact rather than maintaining a second proof
  model.

- [ ] Make the condition analyzer recursively return true/false proof
  environments and typecheck later `and`/`or` operands under only the path on
  which they execute. Add private `true_proof_context` and
  `false_proof_context` fields to typed `IfExpr` (default empty and excluded
  from source-level equality). Key their facts by binding identity, never by
  expression spelling. This keeps proof on the control node WCC consumes and
  avoids a second session-lifecycle mechanism.

- [ ] Run GREEN and regressions:

  ```sh
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow.py \
    -k 'variant or proof or shadow or alias or contextual'
  pytest -q tests/test_workflow_lisp_variant_proofs.py
  pytest -q tests/test_workflow_lisp_expressions.py \
    -k 'equality or if_conditional or computed_if'
  ```

- [ ] Do not commit. Continue directly to Task 3B with the same subagent and
  working diff; the feasibility result is not separable from runtime proof.

### Task 3B: Complete Runtime Guard And Resume Carriage

**Files:**

- Modify: `orchestrator/workflow_lisp/wcc/model.py`
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py`
- Modify: `orchestrator/workflow_lisp/wcc/analysis.py`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `orchestrator/workflow_lisp/lowering/pure_projection.py`
- Modify: `orchestrator/workflow_lisp/lexical_checkpoint_restore.py`
- Modify only if legacy-compatible restore consumption requires it:
  `orchestrator/workflow/executor.py`
- Test: `tests/test_workflow_lisp_strict_boolean_control_flow.py`
- Test: `tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py`
- Regression: `tests/test_workflow_lisp_wcc_m4.py`
- Regression: `tests/test_workflow_lisp_lexical_checkpoint_restore.py`

- [ ] Add the fourth accepted feasibility fixture: a provider-produced union is
  tested with `(= attempt.variant COMPLETED)`, and the selected branch sends
  `attempt.execution_report` to an effect. Assert the exact consuming leaf has:

  ```python
  {"requires_variant": {"step": producer_step_id, "value": "COMPLETED"}}
  ```

  Mutate the persisted producer discriminant before consumption and assert the
  executor fails closed. Force/resume inside the branch and assert the restored
  proof descriptor binds the exact producer and variant.

- [ ] Rerun the still-RED runtime/resume portion after Task 3A's guard-shape
  gate:

  ```sh
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow.py -k 'requires_variant or multi_union or input_union'
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py -k 'proof_guard or contradiction or proof_resume'
  ```

- [ ] Carry true/false singleton facts on `WccIf` metadata using the existing
  `proof_context` slot or the smallest private branch fields. While elaborating
  a proven branch, narrow only its exact binding identity for field type
  inference. Proof ends at the branch join.

- [ ] Extract the existing `requires_variant` contract builder from
  `_guard_hoisted_case_steps` and reuse it for the leaf/projection that first
  consumes each narrowed field. Keep `when` routing separate from proof. A
  missing guard for an accepted singleton field is a compiler error.

- [ ] Generalize `_collect_restore_match_descriptors` into explicit variant
  proof descriptor collection. New descriptors carry binding identity, union,
  producer/discriminant, singleton variant, proof origin, and source span.
  Preserve legacy `match_branch` descriptors and the existing
  `active_variant_proofs` state family. Capture/revalidate predicate proof from
  the producer discriminant artifact rather than parsing generated match step
  names.

- [ ] Run GREEN and adjacent guard/restore regressions:

  ```sh
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow.py \
    -k 'requires_variant or multi_union or input_union'
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py \
    -k 'proof_guard or contradiction or proof_resume'
  pytest -q tests/test_workflow_lisp_wcc_m4.py \
    -k 'hoists_effectful_match_arm_steps or lexical_checkpoint_extraction'
  pytest -q tests/test_workflow_lisp_lexical_checkpoint_restore.py \
    -k 'proof or selector or resume_requires_restored'
  ```

- [ ] Commit exact task paths only after the feasibility gate passes:

  ```sh
  git add orchestrator/workflow_lisp/wcc/model.py \
    orchestrator/workflow_lisp/wcc/elaborate.py \
    orchestrator/workflow_lisp/wcc/analysis.py \
    orchestrator/workflow_lisp/wcc/defunctionalize.py \
    orchestrator/workflow_lisp/lowering/pure_projection.py \
    orchestrator/workflow_lisp/lexical_checkpoint_restore.py \
    orchestrator/workflow_lisp/type_env.py \
    orchestrator/workflow_lisp/typecheck_context.py \
    orchestrator/workflow_lisp/typecheck_proofs.py \
    orchestrator/workflow_lisp/typecheck_dispatch.py \
    orchestrator/workflow_lisp/typecheck_pure_ops.py \
    orchestrator/workflow_lisp/conditionals.py \
    orchestrator/workflow_lisp/expressions.py \
    tests/test_workflow_lisp_strict_boolean_control_flow.py \
    tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py \
    tests/test_workflow_lisp_wcc_m4.py \
    tests/test_workflow_lisp_lexical_checkpoint_restore.py
  git commit -m "Carry Boolean predicate proof through runtime guards"
  ```

  Add `orchestrator/workflow/executor.py` only if legacy-compatible restore
  consumption changed.

## Task 4: Erase `cond` With Typed Exhaustiveness

**Files:**

- Modify: `orchestrator/workflow_lisp/conditionals.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck_proofs.py`
- Test: `tests/test_workflow_lisp_strict_boolean_control_flow.py`
- Test: `tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py`

- [ ] Add RED tests for ordered clauses, compatible result types, required
  final `else`, pure-static-true exhaustiveness, and closed-union
  exhaustiveness. Assert a no-`else` form with a reachable false environment
  fails `cond_non_exhaustive`.

- [ ] Add the fifth accepted runtime fixture:

  ```lisp
  (cond
    ((= attempt.variant COMPLETED)
     (command-result consume-completed
       :argv ("python" "scripts/consume_completed.py"
              attempt.execution_report)
       :returns Bool))
    ((or (provider-result providers.last-check
           :prompt prompts.last-check
           :inputs ()
           :returns Bool)
         (= attempt.variant BLOCKED))
     (command-result consume-blocked
       :argv ("python" "scripts/consume_blocked.py"
              attempt.blocker_reason)
       :returns Bool)))
  ```

  On the second clause, assert the provider executes exactly once, the terminal
  equality is skipped when it returns true, the body executes in both valid
  paths, and resume neither repeats the provider nor changes the result. Assert
  each clause's field-consuming command carries the matching
  `requires_variant` guard; this proves `cond`-derived narrowing reaches the
  same runtime proof path as `if`.

- [ ] Run RED:

  ```sh
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow.py -k 'cond or exhaustive'
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py -k 'cond or exhaustive'
  ```

- [ ] Typecheck clauses sequentially. Each condition is analyzed under the
  residual false environment of earlier clauses; each body is checked under
  its true environment. Unify reachable body result types exactly as `if`
  does. General Boolean expressions do not count as exhaustive unless they
  fold to true or the possible-set environment becomes unreachable.

- [ ] Rewrite ordinary clauses to nested normalized `IfExpr`. For an exhaustive
  no-`else` final condition, discard it only when effect-free. Otherwise bind
  its Boolean result once (preserving its nested short-circuit structure) and
  continue to the final body; do not synthesize a runtime-unreachable branch.
  Retain clause spans on generated nodes. Assert no `CondExpr` reaches WCC.

- [ ] Run GREEN and collection:

  ```sh
  pytest --collect-only -q \
    tests/test_workflow_lisp_strict_boolean_control_flow.py \
    tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow.py \
    -k 'cond or exhaustive'
  pytest -q tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py \
    -k 'cond or exhaustive'
  pytest -q tests/test_workflow_lisp_variant_proofs.py
  ```

- [ ] Commit exact task paths:

  ```sh
  git add orchestrator/workflow_lisp/conditionals.py \
    orchestrator/workflow_lisp/typecheck_dispatch.py \
    orchestrator/workflow_lisp/typecheck_proofs.py \
    tests/test_workflow_lisp_strict_boolean_control_flow.py \
    tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py
  git commit -m "Lower typed Workflow Lisp cond expressions"
  ```

## Task 5: Close Diagnostics, Source Maps, And Acceptance Coverage

**Files:**

- Modify as evidence requires: `orchestrator/workflow_lisp/source_map.py`
- Modify as diagnostics require:
  `orchestrator/workflow_lisp/diagnostics.py` and the owning frontend modules
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify: `tests/test_workflow_lisp_source_map.py`
- Modify: `tests/test_workflow_lisp_strict_boolean_control_flow.py`
- Modify: `tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py`

- [ ] Complete the accepted matrix: literals, refs, pure expressions, direct
  provider/command/workflow/procedure calls, comparisons, nested conditionals,
  strict non-Bool rejection, failure-before-routing, left-to-right execution,
  at-most-once execution, unselected branch absence, and clean/resume
  equivalence.

- [ ] Assert generated diagnostics and source-map entries point at the authored
  operand or `cond` clause, never a compiler binding. Assert contracts,
  artifact lineage, step/attempt counts, and source ownership rather than
  generated step spellings or serialized implementation details.

- [ ] Run the complete focused surface and adjacent regressions:

  ```sh
  pytest --collect-only -q \
    tests/test_workflow_lisp_strict_boolean_control_flow.py \
    tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py
  pytest -q \
    tests/test_workflow_lisp_strict_boolean_control_flow.py \
    tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py \
    tests/test_workflow_lisp_variant_proofs.py \
    tests/test_workflow_lisp_expressions.py \
    tests/test_workflow_lisp_wcc_characterization.py \
    tests/test_workflow_lisp_wcc_m4.py \
    tests/test_workflow_lisp_lowering.py \
    tests/test_workflow_lisp_pure_projection_runtime.py \
    tests/test_workflow_lisp_lexical_checkpoints.py \
    tests/test_workflow_lisp_lexical_checkpoint_restore.py \
    tests/test_workflow_lisp_source_map.py \
    tests/test_workflow_lisp_diagnostics.py \
    tests/test_workflow_lisp_native_returns_e2e.py
  ```

- [ ] Commit exact task paths:

  ```sh
  git add orchestrator/workflow_lisp/source_map.py \
    tests/test_workflow_lisp_diagnostics.py \
    tests/test_workflow_lisp_source_map.py \
    tests/test_workflow_lisp_strict_boolean_control_flow.py \
    tests/test_workflow_lisp_strict_boolean_control_flow_e2e.py
  git commit -m "Verify strict Boolean control-flow behavior"
  ```

  Add only the diagnostic-owning production files that actually changed.

## Task 6: Publish 2.26 And Run Repository Verification

**Files:**

- Modify: `docs/design/workflow_lisp_strict_boolean_control_flow.md`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_proof_graph.md`
- Modify: `docs/design/workflow_lisp_reference_catalog.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `specs/dsl.md`
- Modify: `specs/versioning.md`
- Modify: `specs/index.md`
- Modify only if routing changes: `docs/index.md` and `docs/design/README.md`

- [ ] Update governing documents from designed to implemented only after Tasks
  1-5 are green. Document exact-Bool semantics, effect ordering, short circuit,
  `cond`, contextual tags, closed fact algebra, proof guards, resume, target
  gating, diagnostics, and the retained `match` compatibility surface. Cite
  behavioral test selectors as copy-safety evidence.

- [ ] Run documentation/status consistency selectors found from the capability
  matrix and routing tests:

  ```sh
  rg -n '2\.26|strict Boolean|condition|cond|variant proof' \
    docs/capability_status_matrix.md specs docs/design docs/lisp_workflow_drafting_guide.md
  pytest -q \
    tests/test_workflow_lisp_e1_normative_contract.py \
    tests/test_workflow_lisp_e2_trial_contract.py \
    tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

- [ ] Read and use the `tmux` skill, then run the broad suite in tmux as
  required by `AGENTS.md`:

  ```sh
  tmux new-session -d -s strict-bool-2-26 \
    'cd /home/ollie/Documents/agent-orchestration && pytest -q -n 16 --dist=worksteal 2>&1 | tee .tmp/strict-bool-2-26-pytest.log'
  tmux attach-session -t strict-bool-2-26
  ```

  Record the fresh pass/fail/skip totals. Diagnose every failure; do not weaken
  tests to obtain a green summary.

- [ ] Request final independent specification-compliance review, then a
  separate implementation-quality review over the complete diff. Rerun the
  affected focused selectors after every material correction.

- [ ] Commit only the exact documentation/spec paths after verification:

  ```sh
  git add docs/design/workflow_lisp_strict_boolean_control_flow.md \
    docs/design/workflow_lisp_frontend_specification.md \
    docs/design/workflow_lisp_proof_graph.md \
    docs/design/workflow_lisp_reference_catalog.md \
    docs/lisp_workflow_drafting_guide.md docs/capability_status_matrix.md \
    specs/dsl.md specs/versioning.md specs/index.md
  git commit -m "Document Workflow Lisp 2.26 Boolean control flow"
  ```

  Add `docs/index.md` or `docs/design/README.md` only if routing changed.

## Completion Evidence

The feature is complete only when all of the following are recorded from fresh
commands:

- both new test modules collect successfully;
- all five feasibility scenarios pass on clean execution and resume;
- target 2.25 compatibility and target 2.27 fail-closed controls pass;
- proof guards fail closed under contradictory persisted state;
- no temporary `CondExpr` reaches WCC and no new runtime/public-IR/state form
  exists;
- focused frontend/WCC/lowering/restore/source-map suites pass;
- the broad `pytest -q -n 16 --dist=worksteal` run is green, or every inherited
  failure is independently reproduced and explicitly reported; and
- capability/spec docs describe only the behavior demonstrated by those tests.
