# Staged-Workflow Authoring Revisions: Implementation Plan

**Status: Plan, drafted 2026-11-13; not reviewed, not accepted.** Implements stage 6 of
[Lane D](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#lane-d-delete-and-unify-background-time-boxed)
(owner decisions 14 and 15). Its specification is the design
[Staged-Workflow Authoring](../design/workflow_lisp_staged_workflow_authoring.md) ("the design"
below); this page does not restate it and assumes it is accepted as written. This page owns the
order of work, the tests and the gates. Behavior is owned by `specs/`, the
[frontend specification](../design/workflow_lisp_frontend_specification.md) and
[evaluated execution](../design/workflow_lisp_evaluated_execution.md); until a task lands those
documents and the code describe the checkout, and nothing here is copy-safe guidance. No provider
call is made or authorized by any task. Planned against `main` at `4bae0a7c`; the spike branch
last merged `main` at `7d286ce0`.

**Goal:** an author binds each role (provider, model, effort, timeout) once and calls it with a
prompt; a timeout can be an input; an empty list needs no carrier; a list can be shortened and
reduced; a document a later step rewrites can be delivered as content without blocking `resume`.

**Approach:** first-class prompts and roles first, in steps that each merge alone: the type and
the value; the timeout operand, where the wrapper needs it; `Prompt[T]` and `Provider` as
compile-time parameters, so `provider-result` accepts a prompt value; generic references; an
`Agent` as a bound argument; the library wrapper and the role idiom; the documents. The snapshot
fill follows the fill-evaluation rule that P1 fixes. The typed list literal and the list operators
are independent of all of it and are prototyped. What this makes harder is listed
[below](#what-this-makes-harder).

**Headline exit test** (`tests/test_staged_authoring_e2e.py`, installed command line, scripted
`claude`): `test_three_roles_bound_once_run_a_staged_workflow_and_resume_after_a_kill`. A program
with `std/ask` roles for a planner, a coder and a reviewer, a timeout from an input, a loop that
starts from `(list :of String)`, a map over `(list/take plan.milestones 8)` and a `list/all` gate
runs to `DONE`, is killed inside a role call and resumes with one dispatch of that call. Today it
fails to compile at the first role line (`generic_union_not_generic`).

## Global Constraints

- **Nothing that compiles today may move.** Every task ends with the three invariant files
  byte-identical to the base recorded in Task 0 (the corpus snapshot, the compile of every tracked
  `.orc`, the run-reference program digests; method of the
  [stage 3 plan](2026-11-12-lane-d-stage-3-old-ir-stack-plan.md) ledger), both trees exported to
  the same path. A task that cannot show this stops.
- No task changes the serial map's behaviour at its cap, the `agent` form, `:doc`, or what a
  phased call accepts. No task adds a checked construct or an identity rule; O adds three operator
  names and S one slot kind to the checked program, both only in programs that use them.
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
  new module, `orchestrator/workflow_lisp/prompt_values.py`; the oversized modules get calls only.

## What Must Merge First

| Work in flight | Files it edits that this plan also edits | Rule |
| --- | --- | --- |
| Surface coherence C1 (`feat/coherence-c1`) | `expressions.py`, `procedure_typecheck.py`, `typecheck_calls.py`, `compiler_session.py`, `closed/build.py` | Before L (a keyword in a positional form gets one diagnostic) and before P3 (a local called by name is the alias path generic references extend) |
| Surface coherence E1 (`feat/coherence-e1`) | `typecheck_dispatch.py`, `typecheck_structural_values.py`, `expressions.py`, `wcc/elaborate.py` | Before Task 0b, L and O (the same functions) |
| Surface coherence I1 (`feat/coherence-i1`) | `typecheck_structural_values.py`, `expressions.py` | Before L; the exit test's map body needs it |
| Surface coherence I2a (`feat/coherence-i2a`) | `expressions.py`, `orchestrator/py/emit.py` | Before L (the binder is where `(list :of T)` reads best) |
| Stage 4 cut (one target; the `fn` form removed) | every tracked `.orc`; the packaged library's target | `std/ask` (P5) is written at 2.40 and merges after Task 4a of that plan; no source in this plan uses the `fn` form |
| Corpus consolidation (TR, wave 1) | §7.8, §8.7.1, §10.2, §10.3, §22.4, §22.6 of the frontend specification | Each task's specification sentence is added through that plan's blocked-files list; P6 lands after TR so the reference test covers the new entries |

`macros.py` is not edited by this plan.

## Tasks

Order: Task 0, then 0b. Then the prompt group in sequence: P1, T, P2, P3; P4 and P5 after P3; P6
last. S0, S1 and S2 after P1. L and O are independent of both groups and may run beside them from
the start: L shares `expressions.py` with P1 (different functions; merge L first if both are
open) and O shares `wcc/elaborate.py` with Task 0b (merge 0b first).

| Task | Files | Hours | Waits on |
| --- | --- | --- | --- |
| 0 Baselines | scratch only | 3 | — |
| 0b Two defects | `wcc/elaborate.py`, `typecheck_structural_values.py` | 6 | E1 merged; owner decision 5 |
| P1 Prompt type and value | `type_env.py`, `expressions.py`, `prompts.py`, `typecheck_effects.py`, new `prompt_values.py` | 12 | E1 merged |
| T Timeout operand | `typecheck_effects.py`, `contracts/closed_program/check.py`, `workflow/evaluated/providers.py` | 4 | — (needed by P2; may land before P1) |
| P2 Compile-time parameters | `procedure_typecheck.py`, `procedure_specialization.py`, `closed/names.py`, `typecheck_effects.py`, `prompt_values.py` | 20 | P1, T |
| P3 Generic references | `procedure_typecheck.py`, `procedure_refs.py`, `procedure_specialization.py` | 14 | P2, C1 merged |
| P4 `Agent` as a bound argument | `procedure_refs.py`, `typecheck_agents.py`, `closed/agent_effects.py` | 8 | P3; owner decision 2 |
| P5 `std/ask` and the role idiom | `stdlib_modules/w3/std/ask.orc`, `workflows/examples/`, the registry row | 6 | P3 (P4 for `ask-agent`); stage 4 Task 4a |
| P6 Documents | the specification entries, guide, library reference, `specs/` change lists, Agent Sessions | 6 | P5; corpus TR |
| S0 Snapshot probe | scratch only | 4 | P1; owner decision 3 |
| S1 `:snapshot` | `prompts.py`, `closed/effects.py`, `contracts/closed_program/check.py`, `workflow/evaluated/{providers,effect_inputs,agent_turns}.py` | 16 | S0 |
| S2 Snapshot documents | `specs/providers.md`, evaluated execution §7.3, guide | 3 | S1 |
| L Typed list literal | `expressions.py`, `typecheck_structural_values.py`, `typecheck_dispatch.py`, `functions.py` | 6 | C1, E1, I1, I2a merged |
| O List operators | `workflow/pure_expr.py`, `typecheck_pure_ops.py`, `wcc/elaborate.py`, `result_guidance.py`, `orchestrator/py/trace.py` | 6 | owner decision 4 |
| F Closeout | the exit test, ledger | 4 | all |

Total about 118 hours: prompts and roles 70 (T included); snapshot 23; L and O 12; the rest 13.

### Task 0: Baselines (3 h)

- [ ] Export `main` to a scratch path and make the three invariant files with the kit under
      `experiments/authoring_revisions/inv/` of branch `spike/authoring-revisions` (see
      [Baselines](#baselines-recorded-while-planning)); record their hashes in the ledger.
- [ ] Record `python experiments/authoring_revisions/probe.py step1_spec.py` output as the
      "today" table every later task flips rows of.

### Task 0b: Two defects (6 h)

- [ ] `tests/test_workflow_lisp_staged_authoring.py::test_map_with_a_match_body_is_a_condition_inside_a_loop`:
      `(if (list/empty? (list/map ((v vs)) (match v …))) (done 1) (continue …))` in a `loop/recur`
      body builds and runs to the value the `let*` spelling gives. Today: `compiler_defect`
      (`KeyError: 'v'`).
- [ ] `::test_empty_list_in_a_match_arm_is_typed_by_the_other_arm`: builds; today
      `compiler_defect` ("typed list is missing its resolved child types").
- [ ] Invariants identical. Both programs are `compiler_defect` today, so nothing that builds can
      move; show it.
- Reviewer: the first defect's cause was not found while planning. Attack whether the fix is in
  the condition normalisation or in the map's binder scope, and whether a `cond` and an `and`
  operand share it.

### Task P1: The prompt type and the prompt value (12 h)

A prompt application becomes an expression of type `Prompt[T]`; it can be bound by `let*` and
given to `:prompt` in the same body. No procedure parameter yet.

- [ ] `tests/test_workflow_lisp_prompt_values.py::test_prompt_application_has_type_prompt_of_its_result`;
      `::test_let_bound_prompt_in_prompt_position_builds_the_program_of_the_application_written_in_place`
      (equal `program_digest` and site list);
      `::test_prompt_value_escapes_are_refused` (parametrized over a record field, a list element,
      loop state, an `if` value, a procedure result, a `defun` parameter, a workflow input and
      result: `prompt_value_escape`);
      `::test_prompt_name_is_shadowed_by_a_binding_a_procedure_and_a_function`;
      `::test_partial_application_and_proc_ref_of_a_prompt_stay_refused`
      (`prompt_partial_application_unsupported`).
- [ ] `tests/test_workflow_lisp_prompt_identity_runtime.py` and
      `tests/test_workflow_lisp_prompt_calculus*.py` pass unedited.
- [ ] Invariants identical.
- Reviewer: fill operands with an effect (E1 admits them): written order, once, when the value is
  bound twice; a prompt value in a `:delivery phased` call and in `request-input` must refuse
  with a message that names the in-place spelling.

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
- [ ] Invariants identical.
- Reviewer: a timeout that differs between run and resume (an input cannot change; a field of an
  effect's result can) must diverge through `policy`; the refusal must precede the attempt
  directory; `report` must show the resolved value.

### Task P2: `Prompt[T]` and `Provider` as compile-time parameters (20 h)

- [ ] `::test_wrapper_called_with_three_prompts_builds_three_specializations` (one checked
      procedure per prompt declaration and provider extern; parameters are the values plus one per
      fill);
      `::test_wrapper_call_has_the_policy_part_and_prompt_text_of_the_call_written_in_place`
      (stand-in run of both spellings; equal `policy` parts; byte-equal prompt text once the
      result path is normalised);
      `::test_wrapper_site_has_one_identity_per_call_site_loop_round_and_map_item`;
      `::test_provider_parameter_takes_an_extern_a_parameter_and_an_alias` and refuses a `String`;
      `::test_agent_origins_of_a_specialization_name_its_extern`.
- [ ] `tests/test_workflow_evaluated_spend_cap.py::test_cap_refuses_an_unpriced_model_through_a_wrapper_before_launch`.
- [ ] `tests/test_workflow_evaluated_prompt_values.py::test_kill_between_two_wrapper_calls_resumes_with_one_dispatch`.
- [ ] Invariants identical; `tests/test_workflow_lisp_let_proc_bindings.py` and the procedure
      specialization tests pass unedited.
- Reviewer: the specialization key (two prompts with equal slot lists must not share one; two
  calls with the same prompt must); a wrapper that forwards its prompt to another wrapper; a
  wrapper with two prompt parameters; `:effects` ceilings on the wrapper; source positions of
  diagnostics raised inside a specialization.

### Task P3: A reference to a generic procedure instantiates at the call (14 h)

- [ ] `tests/test_workflow_lisp_generic_references.py::test_alias_of_a_generic_procedure_is_called_at_two_types`;
      `::test_bound_generic_procedure_is_called_at_two_types` (today `type_mismatch`);
      `::test_binding_an_argument_whose_type_is_a_type_parameter_stays_refused`
      (`proc_ref_binding_type_invalid`);
      `::test_generic_reference_passed_to_a_procref_parameter_is_instantiated_to_it`;
      `::test_bound_reference_call_builds_the_program_of_the_direct_call` (digest and sites of
      `(pick 1 x)`).
- [ ] `tests/test_workflow_lisp_prompt_values.py::test_role_bound_once_is_called_with_prompts_of_three_result_types`;
      `::test_editing_one_roles_literal_moves_only_that_roles_specializations`;
      `tests/test_workflow_evaluated_prompt_values.py::test_edited_role_literal_plans_a_cut_at_that_roles_first_step`
      (plain `resume` after the edit: the plan keeps the commits before that role's first step).
- [ ] Invariants identical; `tests/test_workflow_lisp_callables_coherence.py` passes unedited.
- Reviewer: this is a general change to procedure references, not a role feature: a generic
  reference stored through `let-proc` capture, forwarded twice, or bound twice; whether two calls
  at one type share a specialization; error text when inference fails at a reference call.

### Task P4: An `Agent` as an explicit `bind-proc` argument (8 h; waits on owner decision 2)

- [ ] `tests/test_workflow_evaluated_agent_composition.py::test_agent_bound_into_a_reference_is_the_same_conversation_at_every_call`
      (three calls, one conversation, the predecessor chain of passing the agent directly);
      `::test_reference_holding_an_agent_is_refused_in_a_parallel_worker`
      (`parallel_agent_boundary`, for the reference free in the body and for one reached through a
      callee); `::test_let_proc_capture_of_an_agent_stays_refused`;
      `::test_agent_origins_of_a_bound_reference_are_those_of_the_agent`.
- [ ] `tests/test_workflow_evaluated_agent_turn_recovery.py` and
      `test_workflow_evaluated_agent_invalidate.py` pass unedited.
- [ ] Invariants identical.
- Reviewer: every row of Agent Sessions' position table, with "a reference that holds an agent"
  in place of "an agent": loop state, a workflow boundary, a branch join, a second `bind-proc`
  over the first.

### Task P5: `std/ask` and the role idiom (6 h)

- [ ] `orchestrator/workflow_lisp/stdlib_modules/w3/std/ask.orc`: `ask` and `ask-agent` with the
      signatures of design §4.6.
- [ ] `tests/test_workflow_lisp_std_ask.py::test_ask_and_ask_agent_are_importable_and_bindable_across_modules`;
      `::test_fresh_and_continued_roles_have_identical_call_sites` (two programs that differ only
      in their role lines; the second runs in one conversation per role).
- [ ] One example under `workflows/examples/` with its registry row and a stand-in smoke run.
- Reviewer: a role with a template that needs no model; the import line's cost in a short
  program; whether `ask-agent` should exist at all if decision 2 is "no".

### Task P6: Documents (6 h)

- [ ] The specification entries of design §14, each as one sentence and its codes; the sentences
      listed under "Text that leaves" removed; `tests/test_workflow_lisp_reference_coverage.py`
      passes with the new codes (`prompt_value_escape`, `provider_timeout_nonpositive`,
      `list_item_type_invalid`) and operator heads.
- [ ] Guide: a "Roles" recipe, the loops section with `(list :of T)`, meeting a map's cap. Library
      reference: `std/ask`. Agent Sessions: the capture sentence. Change-list entries in
      `specs/dsl.md` and `specs/versioning.md`; the timeout operand in `specs/providers.md`.
- [ ] `docs/index.md` and the capability matrix rows.
- Reviewer: any sentence that tells an author to pass a path "because `:doc` blocks resume" must
  match the state of S.

### Task S0: Probe the snapshot rule (4 h; waits on owner decision 3)

- [ ] In scratch: retain a `:doc` fill's bytes at `started`, resolve a committed step from them,
      and run the strict replay for a provider and for an agent turn on the living-document
      scenario (`experiments/authoring_revisions/scenarios.py`, `f4_doc_living*`). Report whether
      the confined profile's snapshot reader serves a host run unchanged. No feature code.
- Stop condition: if replay needs a second authority for the bytes beyond the attempt directory,
  return to the design.

### Task S1: The `:snapshot` slot kind (16 h)

- [ ] `tests/test_workflow_evaluated_prompt_files.py::test_snapshot_fill_resumes_after_a_later_step_rewrites_the_document`
      (provider) and `…_for_an_agent_turn` (today: no plan can be accepted);
      `::test_doc_fill_still_refuses_an_outside_edit` and
      `::test_doc_fill_still_refuses_a_change_made_by_a_later_step` (unchanged code and plan
      text); `::test_snapshot_bytes_missing_or_altered_refuse_without_reading_the_workspace`;
      `::test_snapshot_fill_records_the_parts_of_a_doc_fill`;
      `tests/test_workflow_evaluated_prompt_edit_continue.py::test_edited_program_plan_reads_snapshot_bytes`.
- [ ] Invariants identical; a run recorded with `:doc` by the base build resumes unchanged.
- Reviewer: a phased call with `:snapshot` (refuse); size of retained bytes and `report`; a
  snapshot slot in a prompt used through a wrapper (the slot kind travels with the declaration).

### Task L: The typed list literal (6 h)

- [ ] `tests/test_workflow_lisp_list_traversal.py::test_typed_empty_list_in_every_position`
      (parametrized over a `let*` binding, a loop's initial state in both loop forms, `continue`,
      `done`, `:on-exhausted`, a `list/append` operand, a map source, an `=` operand);
      `::test_typed_list_has_the_digest_of_the_contextual_list` (a field, an argument, an `if`
      arm); `::test_typed_list_checks_its_items_and_its_context`
      (`pure_expr_operand_type_mismatch`, `type_unknown`, `list_item_type_invalid`);
      `::test_empty_list_takes_its_type_from_continue_and_a_defun_argument`.
- [ ] The Python frontend emits `(list :of T)` where it emits a `loop-state` carrier only for
      typing an empty list (`tests/test_python_frontend_emit.py`, one case); emitted programs that
      build today keep their digest.
- [ ] Invariants identical.
- Reviewer: `:of` inside a generic procedure (the type name is a type parameter); a macro that
  produces `(list :of T)`; `(list :of)`.

### Task O: Three list operators (6 h)

- [ ] `tests/test_workflow_pure_expr.py`: golden vectors for `list/take` (0, n, more than the
      length, negative), `list/all` and `list/any` (empty, mixed); the operator justification
      fixture gains three rows.
- [ ] `tests/test_workflow_lisp_list_traversal.py::test_list_traversal_authored_head_inventory_is_exact`
      gains the three heads; `::test_reduction_operators_are_pure_everywhere` (a `defun`, a
      `list/map` body, a condition).
- [ ] `tests/test_workflow_evaluated_loops.py::test_take_keeps_a_long_list_under_the_map_cap`
      (nine items, `list/take … 8`, `:max 8`: eight logged calls, exit 0) and
      `::test_run_that_failed_at_the_cap_before_the_change_resumes_to_the_same_code` (the recorded
      root `tests/fixtures/map_effect_cap_pre_change` of I1).
- [ ] Python frontend: `take`, `all_of`, `any_of` in `orchestrator/py/trace.py`, one emit test.
- [ ] Invariants identical.
- Reviewer: an old build reading a program with a new operator must fail closed
  (`pure_expr_operator_unsupported`), not misread it; `list/take` with a `Float` count.

### Task F: Closeout (4 h)

- [ ] The headline exit test. The three seeds of `spike/long-horizon-seed`, rewritten as in
      `experiments/authoring_revisions/seeds/`, compile without the lowering script and pass
      their demo.
- [ ] Ledger: each task's commit, review result and the invariant hashes.

## Baselines Recorded While Planning

Prototype of T, the `:of` part of L, and O: branch `spike/authoring-revisions`, commit `fd527d04`
on base `4bae0a7c`. The invariant files of both, each tree exported to the same path and made by
`experiments/authoring_revisions/inv/inv.sh`, are byte-identical (`cmp`):

| Invariant | Base `4bae0a7c` and prototype `fd527d04` |
| --- | --- |
| Corpus snapshot (55 rows, 11 built) | `810baec5c6db3bf8fb22989a4c2cdc2fdff076c71ca5416f0c44b6f9df2a1ce0` |
| Compile of every tracked `.orc` (634 files: 45 exit 0, 589 exit 2), raw output | `18e2cf6f9998c4afa057b58437ebcb16c598d5a8cc4284d9ad8a12e9d8727966` |
| Same, normalized hashes of the 45 built programs | `a2fce34d1e244872c305003dc931d3af3668cace9d351cefdd1b02d257fe9690` |
| Run-reference program digests (249 files, 125 test folders, 128 programs; basetemp `/tmp/lr-tmp/rr`) | `04939fb6f2c2fabcebef837438f65d7fa44196238db81dc1289e27735f30d801` |

The first three equal the values the surface-coherence branches recorded for the same base. The
serial run-reference test run that produces the fourth had 1 failure on the base and 2 on the
prototype, all cases of `test_workflow_evaluated_run_ref_kills.py::test_kill_at_parent_settlement_gap_recovers`,
which the [test baseline](../reports/2026-11-11-test-baseline.md) lists as load-sensitive (load
average above 80 during both runs); rerun alone, each case passed at least once on both trees.

Narrow run on the spike tip (I1 and I2a merged): 372 tests of the provider-policy, phased,
pure-expression, list-traversal and corpus modules; 370 pass; the 2 failures are the flips named
in Tasks T and O.

## What This Makes Harder

- **Finding a program's prompts.** A prompt is no longer used only inside `provider-result`:
  source-site inspection, the language server and any tool that lists prompts by scanning calls
  must follow a prompt value to its consumer.
- **Reading a step's prompt from its name.** A role call's identity names the wrapper
  (`ask[<digest>]`), not the prompt; the binding label is the only authored name in it.
- **The specialization pass.** Two more kinds of compile-time argument and generic bound
  references multiply its cases; a diagnostic raised inside a specialization must still point at
  the author's call.
- **Agent Sessions' boundary rules.** A bound reference is one more carrier of an `Agent`; every
  later rule about where an agent may go must name it.
- **A run-time prompt value later.** Storing or choosing a prompt would relax the compile-time
  rule position by position and add a checked value kind.
- **Static budgets.** A timeout that is an input is not known at compile time; a tool that sums
  literal timeouts sees a name.
- **Two input-binding regimes on host runs** (`:doc` pinned, `:snapshot` retained); `report` must
  say which a step used.
- **Three spellings for a list's type** (context, `:of`, the carrier) until the carrier's
  single-field use is migrated.
- **The operator table.** Each new operator is five code sites, golden vectors, a Python name and
  a reference row.

## Not Verified While Planning

- **P1 to P4 in the compiler.** Nothing was built. The identities, digests, parts and runs of
  design §4.2 were measured on specializations written by `lower.py`, with today's canonical
  names (`procedure:<module>::ask-coder-work[…]`), not the names the real pass will give.
- Binding an imported generic procedure across modules; a wrapper with an `:effects` ceiling; a
  generic reference through `let-proc`.
- An effect written inside a `bind-proc` argument (`:who (agent …)`): only an agent bound by its
  own `let*` line was run.
- The cause of the loop-condition defect (Task 0b).
- S: nothing was run beyond the reproduction; the retained prompt's digest was compared by hand
  for one step.
- `request-input :timeout-sec`: the probe failed on an import and was not repeated.
- The Python frontend with a name as timeout, with `(list :of T)` and with the new operators.
- The language server, the REPL and source-site inspection on any new form.
- E1 and C1 together with these changes: the spike merged I1 and I2a only. One sampled broad run
  on the spike tip (`--sample 10`, seed 755050, load average above 80): 1,484 passed, 102 skipped,
  3 failed in provider execution control, terminal recovery and the confined wall budget; the
  three passed when rerun alone. The whole suite was not run.
- The per-change columns of the design's size table are an attribution between two compiled end
  points (today's language with per-role inputs; the revised seeds through `lower.py`), not
  separate compiled versions.
- That `(list :of T)` inside a generic procedure substitutes the type parameter.
- Wording of every new diagnostic.

## Rulings Made While Planning

| # | Ruling | Reason | Cost if wrong |
| --- | --- | --- | --- |
| 1 | A prompt value is compile-time, resolved by specialization | No checked construct is added; `ProcRef` is the precedent | A consumer that stores or chooses prompts needs a checked value kind and a relaxation of design §4.1 |
| 2 | Files are read at the call, never when the prompt value is created | Only an effect can record a read | None found |
| 3 | Two wrappers (`ask`, `ask-agent`), not one | An agent turn refuses `:model` and `:effort` | One wrapper needs Agent Sessions to accept a restated policy |
| 4 | `(list :of T)`, not a typed binder | One spelling for every position | A second spelling if a binder annotation is added later |
| 5 | `list/all` and `list/any` take a `List[Bool]`; no binder form | `list/map` already maps; rule 2's binder has one name | `(list/all (list/map …))` is longer than a binder form at each use |
| 6 | `:snapshot` is a slot kind, not an option on `:doc` | The kind decides delivery and binding today | A rename before release |
| 7 | A computed timeout below 1 refuses the step; it is not clamped | A silent clamp changes what the author wrote | A run that would have continued stops |
| 8 | The library module is `std/ask` | One import line names both wrappers | A rename |
| 9 | L and O are scheduled beside the prompt group, not after it | They are prototyped, share one file each with it, and remove two findings in a day and a half | A merge conflict in `expressions.py` or `wcc/elaborate.py` to resolve by hand |
| 10 | The lowering script is evidence for the checked form and its identities, not for the compiler change | It cannot show the cost or the diagnostics of the pass | P2 and P3 estimates are the least certain here; P2 has a stop point after its first test |

## Ledger

| Date | Entry |
| --- | --- |
