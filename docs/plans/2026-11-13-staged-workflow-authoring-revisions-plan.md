# Staged-Workflow Authoring Revisions: Implementation Plan

**Status: Plan, revised 2026-11-13 after an independent review (accept after fixes: 0 blockers, 8
majors, 11 minors) and the coordinator's rulings on it; not yet accepted.** Implements stage 6 of
[Lane D](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#lane-d-delete-and-unify-background-time-boxed)
(owner decisions 14 and 15). Its specification is the design
[Staged-Workflow Authoring](../design/workflow_lisp_staged_workflow_authoring.md) ("the design"
below); this page does not restate it and assumes it is accepted as written. This page owns the
order of work, the tests and the gates. Behavior is owned by `specs/`, the
[frontend specification](../design/workflow_lisp_frontend_specification.md) and
[evaluated execution](../design/workflow_lisp_evaluated_execution.md); until a task lands those
documents and the code describe the checkout, and nothing here is copy-safe guidance. No provider
call is made or authorized by any task. Planned against `main` at `4bae0a7c`, revised against
`b9b5680d`.

**Goal:** an author binds each role of fresh calls (provider, model, effort, timeout) once and
calls it with a prompt; a timeout can be an input; an empty list needs no carrier; a list can be
shortened and reduced.

**Not in this plan** (design §8, each with what is lost): the snapshot fill for living documents;
an `Agent` bound into a role and `ask-agent`; prompt values bound by `let*` or `bind-proc`; a
`let*` alias of a provider; a role passed to a procedure.

**Approach:** the timeout operand and the list operators first: both are prototyped and wait on
nothing. The typed list literal after the four surface-coherence branches merge. Then the defects
the seeds meet, then prompts and roles in four steps that each merge alone (the prompt as an
argument; `Prompt[T]` and `Provider` parameters; a called reference over a generic procedure; the
library wrapper), then the documents. Every change is prototyped on `spike/authoring-revisions`,
and the seeds compile and run there as written. What this makes harder is listed
[below](#what-this-makes-harder).

**Headline exit test** (`tests/test_staged_authoring_e2e.py`, installed command line, scripted
`claude`): `test_three_roles_bound_once_run_a_staged_workflow_and_resume_after_a_kill`. A program
with `std/ask` roles for a planner, a coder and a reviewer, a timeout from an input, a loop that
starts from `(list :of String)`, a map over `(list/take plan.milestones 8)` whose body calls two
roles, and a `list/all` gate runs to `DONE`, is killed inside a role call and resumes with one
dispatch of that call. Today it does not compile: `std/ask` does not exist, and its wrapper is
refused (`generic_union_not_generic`).

## Global Constraints

- **Nothing that compiles today may move.** Every task ends with the three invariant files
  byte-identical to the base recorded in Task 0 (the corpus snapshot, the compile of every tracked
  `.orc`, the run-reference program digests; method of the
  [stage 3 plan](2026-11-12-lane-d-stage-3-old-ir-stack-plan.md) ledger), both trees exported to
  the same path. A task that cannot show this stops.
- **The compile invariant must reach the code a task changes.** A bare compile stops every program
  with a provider call at `provider_result_provider_invalid`, before typecheck reaches timeouts,
  prompts or providers. The kit therefore gives each compile a generated provider externs file
  naming every `providers.<x>` the source mentions, and prints how many files build and how many
  of those name a provider (`experiments/authoring_revisions/inv/compile_all.py` on the spike
  branch). A task reports those two counts with its hashes.
- No task changes the serial map's behaviour at its cap, the `agent` form, `:doc`, the macro rule
  of the specification's §36, or what a phased call accepts. No task adds a checked construct, a
  component of the checked definition key or an identity rule; O adds three operator names to the
  checked program, only in programs that use them.
- Versioning: each change admits source refused today and moves no identity of source that
  compiles, so none adds a target (the versioning rule, point 2); each adds one entry to the
  change list of `specs/versioning.md`.
- Tests first: see each new test fail for its stated reason, then implement. Tests assert
  behaviour, diagnostic codes and values, never prompt text. New `.orc` test sources declare
  `(:target-dsl "2.40")`. Provider-launching tests use the stand-ins and `closed_path(...)` of
  `tests/agent_session_shims.py`.
- Pathspec commits; no assistant attribution; no `git stash`; a separate worktree per task;
  `PYTHONPATH` set to the working tree; `experiments/thread_m/no_provider` first on `PATH`;
  `mkdir -m 700` for any basetemp.
- **Gate for every merge:** the task's narrow run, `pytest --collect-only` on each module added or
  edited, `pytest -q -n 16 --dist=worksteal --sample 10`, and before the merge the whole suite; no
  failure outside the ids of the [test baseline](../reports/2026-11-11-test-baseline.md).
- Function cyclomatic complexity at most 12 for new code. New logic for prompt values goes in one
  new module, `orchestrator/workflow_lisp/prompt_values.py`; the large modules get calls only.

## What Must Merge First

| Work in flight | Files it edits that this plan also edits | Rule |
| --- | --- | --- |
| Surface coherence C1 (`feat/coherence-c1`) | `expressions.py`, `procedure_typecheck.py`, `typecheck_calls.py`, `compiler_session.py`, `closed/build.py` | Before L (a keyword in a positional form gets one diagnostic), before 0b (it turns D4 into `proc_ref_literal_required`) and before P3 |
| Surface coherence E1 (`feat/coherence-e1`) | `typecheck_dispatch.py`, `typecheck_structural_values.py`, `expressions.py`, `wcc/elaborate.py` | Before L, 0b and P1 (the same functions) |
| Surface coherence I1 (`feat/coherence-i1`) | `typecheck_structural_values.py`, `expressions.py` | Before L and 0b; D3's test and the exit test use a map body that is not one call |
| Surface coherence I2a (`feat/coherence-i2a`) | `expressions.py`, `orchestrator/py/emit.py` | Before L (the binder is where `(list :of T)` reads best) |
| Stage 4 cut (one target; the `fn` form removed) | every tracked `.orc`; the packaged library's target | `std/ask` (P5) is written at 2.40 and merges after Task 4a of that plan; no source in this plan uses the `fn` form |
| Corpus consolidation | The frontend specification; the files that plan lists under "Blocked files" (another session's uncommitted edits: the guide, `docs/index.md`, Agent Sessions, evaluated execution among them) | The reference coverage test is on `main`, so O adds its three operator rows in its own merge. P6 edits a blocked file only once `git status` shows it clean on `main` |

T and O wait on none of these. `macros.py` is not edited by this plan.

## Tasks

Order: Task 0; T and O, in parallel (disjoint files); L, once C1, E1, I1 and I2a are merged; then
0b, P1, P2, P3, P5, P6, F in sequence.

| Task | Files | Hours | Waits on |
| --- | --- | --- | --- |
| 0 Baselines and the kit | scratch; the kit | 4 | — |
| T Timeout operand | `typecheck_effects.py`, `contracts/closed_program/check.py`, `workflow/evaluated/providers.py` | 4 | — |
| O List operators | `workflow/pure_expr.py`, `typecheck_pure_ops.py`, `wcc/elaborate.py`, `result_guidance.py`, `orchestrator/py/trace.py`, three rows of the specification's §10.2 | 7 | — |
| L Typed list literal | `expressions.py`, `typecheck_structural_values.py`, `typecheck_dispatch.py`, `functions.py` | 6 | C1, E1, I1, I2a merged |
| 0b Defects the seeds meet | `wcc/elaborate.py`, `typecheck_structural_values.py`, `procedure_typecheck.py` | 10 | C1, E1, I1 merged |
| P1 A prompt as an argument | `type_env.py`, `expressions.py`, `expression_traversal.py`, `typecheck_dispatch.py`, `typecheck_proofs.py`, new `prompt_values.py` | 10 | 0b |
| P2 `Prompt[T]` and `Provider` parameters | `procedure_typecheck.py`, `procedure_specialization.py`, `procedures.py`, `specialization_typecheck.py`, `closed/names.py`, `typecheck_effects.py`, `prompt_values.py` | 16 | P1, T |
| P3 A called reference over a generic procedure | `typecheck_dispatch.py`, `procedure_typecheck.py`, `prompt_values.py` | 8 | P2 |
| P5 `std/ask` and the role idiom | `stdlib_modules/w3/std/ask.orc`, `workflows/examples/`, the registry row | 4 | P3; stage 4 Task 4a |
| P6 Documents | the specification entries, guide, library reference, `specs/` change lists, capability matrix | 6 | P5; blocked files clean |
| F Closeout | the exit test, ledger | 4 | all |

Total about 79 hours: T, O and L 17; prompts and roles 44; defects 10; the rest 8.

The basis of the prompt estimates is the prototype (12 files, 270 lines, built and run in one
working session, [below](#baselines-recorded-while-planning)), not a reading of the code. What it
leaves out is what the hours are for: the non-generic call path, the refusals and their messages,
exact effect summaries, tests. P1 to P3 were 46 hours before the prototype, with P3 a general
change to procedure references; they are 34 now, with P3 narrowed to a reference called where it
is bound.

### Task 0: Baselines and the kit (4 h)

- [ ] Move the kit of `experiments/authoring_revisions/inv/` (spike branch) to the task's scratch.
      Export `main` to a scratch path and make the three invariant files; record their hashes, the
      number of files that build and the number of those that name a provider in the ledger.
- [ ] Record `python experiments/authoring_revisions/probe.py step1_spec.py` output as the
      "today" table every later task flips rows of.
- Reviewer: a tracked program whose provider names are not of the form `providers.<x>`, or that
  needs a commands file to reach typecheck; say how many such files the gate still cannot see.

### Task T: The timeout operand (4 h)

- [ ] `tests/test_workflow_lisp_provider_call_policy.py`: the case
      `timeout_value … provider_result_timeout_literal_required` of
      `test_timeout_provider_call_policy_enforces_literal_type_and_positive_domain` becomes
      `test_timeout_accepts_a_name_or_a_field` (a workflow input, a `let*` name, a record field, a
      procedure parameter, a `bind-proc` argument, an agent turn all build);
      `test_timeout_refuses_a_computed_expression` keeps the code for `(+ t 1)`;
      `test_phased_timeout_stays_a_literal` (in `test_workflow_lisp_phased_239.py`, unchanged
      code).
- [ ] `tests/test_workflow_evaluated_provider_timeout.py::test_timeout_from_an_input_reaches_the_launch_and_the_policy_part`
      (the stand-in records the timeout it was launched with; the committed `policy` part equals
      that of the literal spelling);
      `::test_nonpositive_timeout_refuses_before_started` (code `provider_timeout_nonpositive`,
      exit 2, no `started` record, no provider call);
      `::test_run_recorded_with_a_literal_timeout_resumes_unchanged` (a run root recorded by the
      base build, never regenerated).
- [ ] Closed check: `test_closed_check_admits_an_inline_timeout_for_a_composed_call_only` (a
      `name` operand on `provider_phased` fails `effect_shape`).
- [ ] `tests/test_python_frontend_emit.py`: a Python provider whose `timeout_sec` is a workflow
      input emits a name and the program builds.
- [ ] Invariants identical.
- Reviewer: a timeout that differs between run and resume (an input cannot change; a field of an
  effect's result can) must diverge through `policy`; the refusal must precede the attempt
  directory; `report` must show the resolved value.

### Task O: Three list operators (7 h)

- [ ] `tests/test_workflow_pure_expr.py`: golden vectors for `list/take` (0, n, more than the
      length, negative), `list/all` and `list/any` (empty, mixed); the operator justification
      fixture gains three rows.
- [ ] `tests/test_workflow_lisp_list_traversal.py::test_list_traversal_authored_head_inventory_is_exact`
      gains the three heads; `::test_reduction_operators_are_pure_everywhere` (a `defun`, a
      `list/map` body, a condition).
- [ ] `tests/test_workflow_evaluated_loops.py::test_take_keeps_a_long_list_under_the_map_cap`
      (nine items, `list/take … 8`, `:max 8`: eight logged calls, exit 0) and
      `::test_run_that_failed_at_the_cap_before_the_change_resumes_to_the_same_code` (a run root
      recorded by the base build).
- [ ] The three operators are registered heads, so the specification's operator table (§10.2)
      gains their three rows in this task and
      `tests/test_workflow_lisp_reference_coverage.py` passes at this merge.
- [ ] Python frontend: `take`, `all_of`, `any_of` in `orchestrator/py/trace.py`, one emit test.
- [ ] Invariants identical.
- Reviewer: an old build reading a program with a new operator must fail closed
  (`pure_expr_operator_unsupported`), not misread it; `list/take` with a `Float` count.

### Task L: The typed list literal (6 h)

- [ ] `tests/test_workflow_lisp_list_traversal.py::test_typed_empty_list_in_every_position`
      (parametrized over a `let*` binding, a loop's initial state in both loop forms, `continue`,
      `done`, `:on-exhausted`, a `list/append` operand, a map source, an `=` operand). Before the
      change each case is the one diagnostic C1 gives a keyword in a positional form; on `main`
      without C1 it is an uncaught `TypeError`, which is why L waits on C1.
      `::test_typed_list_has_the_digest_of_the_contextual_list` (a field, an argument, an `if`
      arm); `::test_typed_list_checks_its_items_and_its_context`
      (`pure_expr_operand_type_mismatch`, `type_unknown`, and `list_item_type_invalid` for
      `(list :of)`); `::test_empty_list_takes_its_type_from_continue_and_a_defun_argument`.
- [ ] The Python frontend emits `(list :of T)` where it emits a `loop-state` carrier only for
      typing an empty list (`tests/test_python_frontend_emit.py`, one case); emitted programs that
      build today keep their digest.
- [ ] Invariants identical.
- Reviewer: `:of` inside a generic procedure (the type name is a type parameter); a macro that
  produces `(list :of T)`.

### Task 0b: The defects the seeds meet (10 h)

The numbers are those of the design's §2.

- [ ] D1, `tests/test_workflow_lisp_staged_authoring.py::test_map_with_a_match_body_is_a_condition_inside_a_loop`:
      builds and runs to the value the `let*` spelling gives. Today: `compiler_defect`
      (`KeyError`).
- [ ] D2, `::test_empty_list_in_a_match_arm_is_typed_by_the_other_arm`: builds; today
      `compiler_defect`.
- [ ] D3, `::test_generic_procedure_called_in_a_map_body_runs_once_per_item` (two items, two
      logged commands, the list of results); today `procedure_call_unknown` naming an internal
      specialization. Prototyped: a typed call already rewritten to a specialization requested in
      the same pass is that specialization's call (15 lines in `procedure_typecheck.py`).
- [ ] D4, `::test_reference_chosen_by_if_refuses_with_one_diagnostic`
      (`proc_ref_literal_required`): passes once C1 is merged; this task only pins it, for a plain
      reference and for one over a generic procedure.
- [ ] D5, `::test_bound_reference_over_a_parameter_passed_on`: first find the cause (4 hours at
      most). If the fix is local, the program builds and runs; if not, the test pins one named
      refusal that is not a compiler-owned message, and the defect goes to the roadmap's open
      list. The role idiom does not pass through this path.
- [ ] Invariants identical. D1 to D3 are refused today, so nothing that builds can move; show it.
- Reviewer: D1's cause was not found while planning: is the fix in the condition normalisation or
  in the map's binder scope, and do `cond` and an `and` operand share it; D3 inside a parallel
  map and inside a `let-proc` local.

### Task P1: A prompt as an argument (10 h)

A prompt application becomes an expression of type `Prompt[T]`, and `Prompt[T]` and `Provider`
become parameter types. Nothing consumes a prompt value until P2: after this task a call that
passes one still refuses, now with `prompt_value_escape`. The task ships the type, the
expression node, the head rule and the refusals, and must show that nothing else moved.

- [ ] `tests/test_workflow_lisp_prompt_values.py::test_programs_whose_prompt_shares_a_name_keep_their_digests`:
      seven programs with digests recorded by the base build: a `let*` binding named like the
      prompt, used in `:prompt`; the same with the binding's value a provider call; a procedure
      named like the prompt; a prompt without slots; a prompt without slots named like a
      procedure, both used; a prompt named like a form (`record`); a prompt named like an operator
      (`list/length`). The first three are the review's.
- [ ] `::test_prompt_application_has_type_prompt_of_its_result` (through a refusal that prints the
      type); `::test_prompt_value_positions_refuse` (parametrized over a `let*` binding, a
      `bind-proc` argument, a record field, a list element, loop state, an `if` value, a procedure
      result, a `defun` argument, a workflow input and result: `prompt_value_escape`);
      `::test_prompt_type_is_a_parameter_type_only` (a record field, a union field,
      `List[Prompt[X]]`, a workflow parameter, a `defun` parameter, a result type, inside
      `ProcRef[...]`: `prompt_value_escape`);
      `::test_provider_used_as_a_value_refuses_with_one_diagnostic` (D7: a `let*` binding, a
      record field, an `if` value, a procedure result, in reached code: `prompt_value_escape`
      where the base build gives `compiler_defect`);
      `::test_unreached_definition_that_names_provider_keeps_its_digest` (six programs recorded
      by the base build: `Provider` in a record field, a list item, a `defun` parameter, a result
      type, a `ProcRef` type and a `defproc` parameter);
      `::test_partial_application_and_proc_ref_of_a_prompt_stay_refused`.
- [ ] `tests/test_workflow_lisp_prompt_identity_runtime.py` and
      `tests/test_workflow_lisp_prompt_calculus*.py` pass unedited.
- [ ] Invariants identical.
- Reviewer: the application is a new expression node: every traversal that enumerates node
  classes, and `typecheck_proofs.py:_kept_match_subject`, which keeps the authored subject of a
  `match` unless it is on a list (the prototype needed one more entry there); a prompt value in a
  phased call and in `request-input`.

### Task P2: `Prompt[T]` and `Provider` as compile-time parameters (16 h)

- [ ] `::test_wrapper_called_with_three_prompts_builds_three_specializations` (one checked
      procedure per prompt declaration and provider extern, in the wrapper's module; parameters
      are the values plus one per fill);
      `::test_two_prompts_with_equal_slots_get_two_specializations` and
      `::test_one_prompt_asked_of_two_externs_gets_two_specializations` (the prototype's first
      version failed both with "contradictory prepared bodies");
      `::test_specialization_name_carries_the_prompt_and_the_extern` (qualified names);
      `::test_wrapper_imported_from_another_module_holds_the_callers_prompt`;
      `::test_prompt_parameter_forwarded_to_another_wrapper`;
      `::test_non_generic_wrapper_with_a_prompt_parameter`;
      `::test_provider_argument_is_an_extern_name_or_a_forwarded_parameter` (a `String`, a `let*`
      alias and an `if` refuse).
- [ ] `tests/test_workflow_evaluated_prompt_values.py::test_wrapper_calls_have_the_policy_parts_and_prompt_texts_of_calls_written_in_place`
      (stand-in run of both spellings: three calls in sequence, two map items, four in two loop
      rounds; nine distinct identities, each the in-place identity followed by the
      specialization's frame);
      `::test_kill_inside_a_wrapper_call_resumes_with_one_dispatch`.
- [ ] `tests/test_workflow_evaluated_spend_cap.py::test_cap_refuses_an_unpriced_model_through_a_wrapper_before_launch`;
      `tests/test_workflow_evaluated_provider_usage.py::test_wrapper_call_reports_the_usage_of_the_call_written_in_place`.
- [ ] Invariants identical; `tests/test_workflow_lisp_let_proc_bindings.py` and the procedure
      specialization tests pass unedited.
- Stop point: after the first three tests pass, compare the size of the change with the
  prototype's; more than about three times its lines for the same behaviour goes back to the
  coordinator before the rest is written.
- Reviewer: the effect summary of a generic wrapper (the prototype types the call provisionally
  and names no provider until specialized: what does an `:effects` ceiling on the wrapper see);
  a wrapper with two prompt parameters; source positions of diagnostics raised inside a
  specialization; a prompt declared in a third module.

### Task P3: A reference over a generic procedure is called where it is bound (8 h)

- [ ] `tests/test_workflow_lisp_generic_references.py::test_bound_generic_procedure_is_called_at_two_types`
      (today `type_mismatch`);
      `::test_role_bound_once_is_called_with_prompts_of_three_result_types`;
      `::test_name_bound_into_a_reference_and_rebound_before_the_call_keeps_its_binding_site_value`
      (the stand-in records the model it was launched with; the prototype without the
      pre-binding launched the rebound value);
      `::test_operand_with_an_effect_runs_once_at_the_binding` (one logged command, two calls);
      `::test_uncalled_reference_over_a_generic_procedure_keeps_its_digest` (recorded by the base
      build; the prototype's first version moved it);
      `::test_bound_generic_reference_passed_to_a_procref_parameter_stays_refused`
      (`proc_ref_signature_invalid`);
      `::test_binding_an_argument_whose_type_is_a_type_parameter_stays_refused`;
      `::test_type_parameter_is_never_a_prompt_or_a_provider` (`(keep (work …))`:
      `prompt_value_escape`);
      `::test_role_bound_inside_a_procedure_from_its_parameter`.
- [ ] `tests/test_workflow_evaluated_prompt_values.py::test_edited_role_literal_plans_a_cut_at_that_roles_first_step`
      (plain `resume` after the edit: no identity moves; the cut names `policy` and `values`; the
      commits before it are kept).
- [ ] Invariants identical; `tests/test_workflow_lisp_callables_coherence.py` passes unedited.
- Reviewer: a reference called only inside a nested `let*`, a loop body, a map body or a
  `let-proc` local (the prototype decides "called" by walking the `let*` it is bound in); two
  roles over one wrapper sharing an operand name; a role bound in a macro expansion.

### Task P5: `std/ask` and the role idiom (4 h)

- [ ] `orchestrator/workflow_lisp/stdlib_modules/w3/std/ask.orc`: `ask`, with the signature of
      design §4.4.
- [ ] `tests/test_workflow_lisp_std_ask.py::test_ask_is_importable_and_bindable_across_modules`;
      `::test_macro_over_a_role_call_compiles_and_a_template_that_writes_the_call_refuses`
      (`macro_hidden_effect` for the second).
- [ ] One example under `workflows/examples/` with its registry row and a stand-in smoke run.
- Reviewer: a role with a template that needs no model; the import line's cost in a short
  program.

### Task P6: Documents (6 h)

- [ ] The specification entries of design §14, each as one sentence and its codes, stated without
      "today" or "after"; the sentences listed under "Text that leaves" removed;
      `tests/test_workflow_lisp_reference_coverage.py` passes with the new codes
      (`prompt_value_escape`, `provider_timeout_nonpositive`, `list_item_type_invalid`).
- [ ] Guide: a "Roles" recipe, the loops section with `(list :of T)`, meeting a map's cap, and the
      standing guidance of design §8.1 on living documents. Library reference: `std/ask`.
      Change-list entries in `specs/dsl.md` and `specs/versioning.md`; the timeout operand in
      `specs/providers.md`. Surface coherence: the amendment of design §10.
- [ ] `docs/index.md` and the capability matrix: one row for prompt values and roles, and one that
      records the language server, the REPL and source-site inspection as not updated for prompt
      values.
- Reviewer: every sentence about `:doc` on a living document must match design §8.1.

### Task F: Closeout (4 h)

- [ ] The headline exit test. The three seeds of `experiments/authoring_revisions/seeds/` compile
      as written and pass the seed's demo.
- [ ] Ledger: each task's commit, review result, the invariant hashes and the two counts.

## Baselines Recorded While Planning

Spike branch `spike/authoring-revisions`; every tree exported to the same path; kit under
`experiments/authoring_revisions/inv/`.

**T, the `:of` part of L, and O** (prototype `fd527d04` on base `4bae0a7c`, bare compile): the
invariant files are byte-identical.

| Invariant | Base `4bae0a7c` and prototype `fd527d04` |
| --- | --- |
| Corpus snapshot (55 rows, 11 built) | `810baec5c6db3bf8fb22989a4c2cdc2fdff076c71ca5416f0c44b6f9df2a1ce0` |
| Compile of every tracked `.orc` (634 files: 45 exit 0, 589 exit 2), raw output | `18e2cf6f9998c4afa057b58437ebcb16c598d5a8cc4284d9ad8a12e9d8727966` |
| Same, normalized hashes of the 45 built programs | `a2fce34d1e244872c305003dc931d3af3668cace9d351cefdd1b02d257fe9690` |
| Run-reference program digests (249 files, 125 test folders, 128 programs) | `04939fb6f2c2fabcebef837438f65d7fa44196238db81dc1289e27735f30d801` |

None of the 45 files that build bare uses `:timeout-sec` or `(list)`. The review therefore
compiled the 59 tracked files that do, on the same two commits, each with a generated provider
externs file: 21 build, and every file has the same exit code and program digest on both. That
result is the baseline for T, L and O until Task 0 re-records with the changed kit.

**Prompts and roles** (prototype `bf4fed6b`, 12 files and 270 lines over `7efd102b`, the spike
with T, L, O, I1 and I2a; kit with generated provider externs):

| Invariant | `7efd102b` and `bf4fed6b` |
| --- | --- |
| Corpus snapshot (55 rows, 11 built) | `810baec5c6db3bf8fb22989a4c2cdc2fdff076c71ca5416f0c44b6f9df2a1ce0` |
| Run-reference program digests (249 files, 125 test folders, 128 programs) | `04939fb6f2c2fabcebef837438f65d7fa44196238db81dc1289e27735f30d801` |
| Compile of every tracked `.orc` outside the probe directory, each with a generated provider externs file (635 files; 61 build, 40 of them name a provider), raw output | identical; rows hash `b51ae26fe9298101d3b05541ad3190b18a915e6550ef74a18c2027db015f1a21` |
| Same, normalized hashes of the 61 built programs | identical; rows hash `30ef3badbfadba24077a7879f9f613b7d004fb53c54ddbb866ec6da6bb9f9b28` |

The first two files are byte-identical and equal those of `4bae0a7c` above. The two trees differ
in the probe directory itself, so `inv/cmp_inv.py` compares the compile rows of every other file
and prints the hash of the compared rows. With a bare compile 45 files build and none names a
provider; with generated externs 40 programs with provider calls are inside the gate. The spike
tip `4aca9f81` adds two lines after `bf4fed6b`, on a path only a unit test without an extern
environment reaches.

Runs with the stand-in on the prototype (`experiments/authoring_revisions/README.md` names each
scenario):

- A wrapper in a library module, three roles, nine calls (three in sequence, two map items, four
  in two loop rounds): nine identities; `policy` parts and prompt texts equal, step for step, to the program
  written in place; a kill resumes with one dispatch; an edited role literal plans a cut at that
  role's first step.
- With a metered template and a stand-in that reports usage, under `--max-cost-usd`: `usage.json`
  rows and `report` usage equal to the program written in place; an unpriced model refuses
  before launch.
- `staged.orc` (39 lines) and `milestones.orc` (44), written with `std/ask` roles, and
  `roles.orc` (48, agent turns in place) compile as written and pass the 14 scenarios of the
  seed's own demo with the call and conversation counts of the originals.
- Narrow run on the spike tip `a84ff86e`, 462 tests of the prompt calculus, prompt identity,
  structured results, `let-proc`, provider policy, agent composition, corpus and site modules:
  461 pass; the failure is the flip named in Task T.
- Sampled broad run on `bf4fed6b` (`--sample 10`, seed 548290): 1,486 passed, 102 skipped, 1
  failed, a unit test that calls the provider typecheck without an extern environment; the tip
  fixes that path (two lines) and the test passes. The whole suite was not run.

## What This Makes Harder

- **Finding a program's prompts.** A prompt is no longer used only inside `provider-result`:
  source-site inspection, the language server and any tool that lists prompts by scanning calls
  must follow a prompt argument into the wrapper.
- **A definition's name is now more than its declaration.** A specialization's declared name
  carries a prompt and an extern; anything that parses a canonical name, or assumes one declared
  name per source procedure, must allow `<…>`.
- **Renaming a prompt or switching a role's extern moves identities,** where the same edit to a
  call written in place moves only its `declaration`.
- **The specialization pass.** Two more kinds of compile-time argument; a diagnostic raised inside
  a specialization must still point at the author's call.
- **A `let*` that binds a called generic reference also binds its operands.** Tools that show a
  workflow's bindings see compiler names there.
- **Relaxing the argument-only rule later.** A `let*`-bound prompt, a prompt in `bind-proc`, a role
  as an argument and an agent in a role (design §8) each relax one refusal and add a case to the
  passes above.
- **Static budgets.** A timeout that is an input is not known at compile time; a tool that sums
  literal timeouts sees a name.
- **Three spellings for a list's type** (context, `:of`, the carrier) until the carrier's
  single-field use is migrated.
- **The operator table.** Each new operator is five code sites, golden vectors, a Python name and
  a reference row.

## Not Verified While Planning

- **The prototype is not the implementation.** It handles generic wrappers only; it has no
  diagnostics for the refused positions and types of design §4.1 and admits some of them; it
  prints short names (`role<work@b>`) where the design asks for qualified ones.
- A non-generic wrapper with a `Prompt[X]` parameter; a wrapper with an `:effects` ceiling; a
  prompt declared in a third module; `std/ask` supplied through a compiled import (the seeds
  supplied it from a source root).
- A role call inside a parallel map and inside a `let-proc` local; a role bound in a macro
  expansion.
- An operand with an effect bound into a role: the pre-binding makes it run once by construction;
  no run checked it.
- The causes of D1 and D5 (Task 0b).
- `request-input :timeout-sec`: the probe failed on an import and was not repeated.
- The language server, the REPL and source-site inspection on any new form.
- E1 and C1 together with these changes: the spike merged I1 and I2a only. The whole suite was
  never run on the spike; two sampled runs were (before and after the prompt prototype).
- The per-change columns of the design's size table are an attribution between two compiled end
  points, not separate compiled versions.
- That `(list :of T)` inside a generic procedure substitutes the type parameter.
- Wording of every new diagnostic.

## Rulings

Coordinator's rulings on the review, 2026-11-13:

| # | Ruling | Applied as |
| --- | --- | --- |
| M1 | One resolution rule for a prompt head, chosen so every program that compiles today keeps its meaning and digest | Design §4.1; seven pinned programs in P1 |
| M2 | The macro rule is the specification's §36, not widened | Design §4.7; the amendment is gone; a test in P5 |
| M3 | The snapshot fill is deferred | Design §8.1; S0 to S2 removed |
| M4 | The compile invariant generates provider externs | Global constraints; Task 0; the kit on the spike |
| M5 | Feasibility of the specialization settled by probe before acceptance | The prototype and its results above; P2 and P3 re-estimated; D3, D4 and D5 in Task 0b |
| M6 | Design §9 true edit by edit | Design §9 |
| M7 | One type-formation rule with its diagnostic | Design §4.1; tests in P1 and P3 |
| M8 | An `Agent` in `bind-proc` and `ask-agent` deferred; the `let*` provider alias dropped; `let*`-bound prompts kept only if free | Design §8.2 and §8.3: they are not free, so deferred; P4 removed |
| 9 | T and O first; L after the four branches; then 0b, P1, P2, P3, P5, P6, F | Tasks |
| 10 | Decide whether the specialization is named after the prompt | Yes, and after the extern: design §4.2. The name is identity, and no program that compiles today has such a definition |
| 11 | Minors | m1 to m6 and m9 to m11 applied; m7 and m8 fall with the deferred snapshot and their content is in design §8.1 |

Planner's rulings, with the cost if wrong:

| # | Ruling | Reason | Cost if wrong |
| --- | --- | --- | --- |
| 1 | A prompt value exists only as an argument | Every other position needs a compile-time binding that is erased, or a run-time value; no seed needs one | A relaxation of design §4.1, position by position |
| 2 | Files are read at the call | Only an effect can record a read | None found |
| 3 | The prompt and the extern go in the specialization's declared name, not in a new key component | The key format and its checker stay as they are, and step names gain what they lacked | A rename moves identities; a later key component would move them once more |
| 4 | A generic reference is rewritten only when called, by pre-binding its operands | Sound for rebinding and for effects; touches nothing that compiles today; avoids the bound-reference path with its open defects | A role cannot be passed on; taking that up means that path |
| 5 | `(list :of T)`, not a typed binder | One spelling for every position | A second spelling if a binder annotation is added later |
| 6 | `list/all` and `list/any` take a `List[Bool]`; no binder form | `list/map` already maps | `(list/all (list/map …))` is longer than a binder form at each use |
| 7 | A timeout below 1 from a name refuses the step; it is not clamped | A silent clamp changes what the author wrote | A run that would have continued stops |
| 8 | The library module is `std/ask`, with one wrapper | One import line; a second wrapper arrives with design §8.2 | A rename |

## Ledger

| Date | Entry |
| --- | --- |
| 2026-11-13 | Design and plan committed as proposed (`a0de5902`). Independent review: accept after fixes, 0 blockers, 8 majors, 11 minors. Coordinator's rulings recorded above. Scope cut to what the seed and the search need: the snapshot fill, an `Agent` bound into a role and `ask-agent` are deferred with no task; total from about 118 to about 79 hours. No provider spend |
| 2026-11-13 | M5 settled by probe on `spike/authoring-revisions` (`bf4fed6b`): a compiler prototype of prompt values and roles, 12 files and 270 lines, builds and runs the role idiom over a wrapper in a library module and the three seeds as written. The specialization belongs to the wrapper's module; identities are the caller's with the specialization's frame; `policy` parts, prompt texts and reported usage equal the program written in place. Found on the way: the definition key needs the prompt and the extern (carried in the declared name); a generic call in a map body is refused on `main` (D3); a rebound operand needs pre-binding; an uncalled generic reference must not be rewritten. The three invariants, the compile with generated provider externs, are identical before and after the prototype. P1 to P3 re-estimated from 46 to 34 hours |
