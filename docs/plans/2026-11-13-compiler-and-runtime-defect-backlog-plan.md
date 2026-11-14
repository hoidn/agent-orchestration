# Compiler And Runtime Defect Backlog: Implementation Plan

**Status: Plan, proposed 2026-11-13; not reviewed, not accepted.** It plans the fixes for the open
defect list of
[Lane D, stage 5](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#lane-d-delete-and-unify-background-time-boxed)
("Compiler and runtime defects found by probes on the way", eight dated batches). It is a plan, not
a contract and not copy-safe guidance. Behavior is owned by `specs/`, the
[frontend specification](../design/workflow_lisp_frontend_specification.md) and
[evaluated execution](../design/workflow_lisp_evaluated_execution.md); until a task lands, those
documents and the code describe the checkout. No task makes or authorizes a provider or model call.
Planned against `main` at `59f727db` (the first probe pass ran on `a58e5b17`; `main` moved while
planning, when I1 merged as `624ff688`, and every probe was run again; `main` at `801bd6d2`, merged
into this branch, differs from `59f727db` in three documents only).

**Goal:** no known program makes a paid call it should not, launches a child a guard forbids, or
gets a wrong answer from the effect analysis; a program the language admits does not crash the
compiler; and every reproduction lives in the repository as a test, not in a scratch file.

**Approach:** first put the reproductions and the three invariant checks into the repository. Then
fix by cause, not by item: 51 rows reduce to 16 fixes here, plus the cut's. Order: class A
(spends or launches), C (unsound analysis), B (silent wrong value), D (crash), E (no effect,
misleading, absent). What this makes harder is listed [below](#what-this-makes-harder).

**Not in this plan, only listed:** the nine changes of the
[one-target cut](2026-11-12-lane-d-stage-4-one-target-plan.md#changes-assigned-to-the-cuts-release-on-2026-11-13-not-yet-sized)
(they refuse or change source that compiles, or move identity); the missing prompt file (branch
`fix/missing-prompt-file`, another agent); the defects owned by
[Task 0b](2026-11-13-staged-workflow-authoring-revisions-plan.md#task-0b-the-defects-the-seeds-meet-10-h)
of the staged-authoring plan; the crashes that `feat/coherence-e1` closes.

## Scope Cut (owner, 2026-11-13)

The owner read the size below (120 hours, two and a half to three weeks) and said: "cut it down by
removing the ones i dont care about (like effect analysis". The coordinator's reading, recorded as
a ruling: a task stays when its defect can spend provider money or commit a wrong output, or when a
short staged seed or a mechanical mutant of one would plausibly write the shape and crash the
compiler. Every other task is dropped from this plan. A dropped defect keeps its row in the table
and its reproduction in Task T0's known-defect list, so it stays visible and tested as known; it
returns only when the mutant generator of the roadmap (Phase 6, R3) or a real workflow hits it.

| Task | Hours | Decision | Reason |
| --- | ---: | --- | --- |
| T0 Reproductions and invariants | 5 | Keep | It is the record of every row, kept or dropped |
| TA2 Output slots before launch | 5 | Keep | A paid call that is then refused; two outputs served by one file |
| TP1 Typecheck in the boundary | 2 | Keep | Turns every remaining crash into a coded outcome, which a search needs |
| TD2 Subject read in an arm | 6 | Keep | A natural thing to write; passes the typechecker, then crashes |
| TD1 Control forms as operands | 5 | Keep | Mostly pins what E1 closes; fixes `:max (match …)` |
| TD5 Local with a loop | 4 | Keep | A natural shape in a staged seed; ends in a traceback |
| TF Closeout | 2 | Keep, reduced | |
| TC1 Imported summaries | 10 | **Dropped** | Effect analysis: named by the owner. The one consumer a probe showed wrong is the declared `:effects` ceiling |
| TA3 P12 through references | 8 | **Dropped** (borderline) | Needs a run reference reached through a procedure reference inside a map body; no tracked source has it. What goes wrong at run time was not established |
| TD3 Binder scope | 10 | **Dropped** (borderline) | Binding the inner form with `let*` first builds; the seed's own instance is fixed by Task 0b of the staged-authoring plan |
| TD6 Local capturing a reference | 8 | **Dropped** (borderline) | Returns if the role binding of the staged-authoring plan meets it |
| TD4, TD7, TD8 | 13 | **Dropped** | Contrived shapes or a crash where a refusal is meant |
| TE1 to TE4 | 23 | **Dropped** | Refusals of good source with a known rewrite, or a misleading code |
| TE5 Dead code | 10 | **Dropped** | No behaviour; a deletion that can ride any later change to those files |
| TP2 Grid | 8 | **Dropped** | Prevention for positions nobody is fixing now |

Kept: 29 hours in seven tasks (about 50 agent-hours with reviews), against 120. The missing prompt
file (A1) is fixed on its own branch and is not in either figure. Of open decision O1's three
changes only the two-slot alias check (in TA2) remains. The sections below are the plan as written
before the cut; the tasks marked dropped here are not executed.

## How To Read The Reproductions

Every program is the body of one module at `(:target-dsl "2.40")`, module `m`, entry `run`, compiled
and run through the public command line (`python -m orchestrator compile|run m.orc --entry-workflow
m::run --command-boundaries-file commands.json`). `commands.json` binds `c` to `python c.py`; the
stand-in `c.py LABEL VALUE` appends `LABEL` to a log and writes `VALUE` to
`$ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. Subprocesses get a closed `PATH` (`closed_path` in
`tests/agent_session_shims.py`, with `experiments/thread_m/no_provider` first). Shorthand:

```lisp
E(label, v, T) = (command-result c :argv ("python" "c.py" "label" "v") :returns T)
U    = (defunion U (A (n Int)) (B (why String)))
INC  = (defproc increment ((value Int)) -> Int (+ value 1))
DBL  = (defproc dbl ((value Int)) -> Int (* value 2))
AP   = (defproc apply1 ((f ProcRef[Int -> Int]) (v Int)) -> Int (f v))
STEP = (defproc step ((n Int)) -> Int E(step, 1, Int))
CHK  = (defproc check ((n Int)) -> Bool E(check, true, Bool))
```

"Today" is the result on `59f727db`. "Crash" means exit 2 with `compiler_defect`, the internal
exception in brackets; "traceback" means exit 1 with an uncaught Python traceback.

## Classes

| Class | Harm | Rows | Re-run on `59f727db` | Still open after the re-run |
| --- | --- | ---: | ---: | ---: |
| A | Spends money or launches work it should not | 3 | 3 | 3 |
| B | Silent wrong value or wrong callee | 6 | 6 | 6 |
| C | Unsound analysis that other checks rely on | 1 | 1 | 1 |
| D | Crash on source the language admits | 18 | 16 | 13 open (3 of them closed on the E1 branch), 2 closed, 1 not reproduced; 2 not re-run |
| E | Accepted form with no effect, misleading message, documented thing that does not exist | 23 | 20 | 16 open, 4 closed or not defects; 3 not re-run |
| **Total** | | **51** | **46** | |

The roadmap's list has about 40 items; the 51 rows come from splitting items that hold several
programs, from nine defects that the reviews, the rule ledger and the staged-authoring design
recorded and the roadmap did not copy (D1, D4, D17, D18, E3, E7, E8, E16, E23), and from one
found while planning (E9).

## Defect Table

"Cut" in the identity column means: the fix refuses or changes source that compiles today, or moves
an identity, so by [the versioning rule](2026-11-12-lane-d-stage-4-one-target-plan.md#the-versioning-rule)
it belongs to the cut's list and is not planned here. "None" means the fix only turns a crash or a
wrong refusal into a refusal or a correct result, or acts at run time before launch.

### Class A

| Id | Defect | Status | Identity | Task | Pinning test |
| --- | --- | --- | --- | --- | --- |
| A1 | A prompt whose `input_file` is missing does not fail; the provider runs with no authored prompt | Reproduced on `59f727db`: exit 0, one launch, the prompt holds only "Typed Prompt Input" and "Output Contract" | None (run time, before launch) | Listed only: `fix/missing-prompt-file` (uncommitted edits to `workflow/prompting.py`, `workflow/evaluated/providers.py`, `tests/test_workflow_evaluated_prompt_files.py`) | That branch's |
| A2 | The guard that forbids a confined run-reference site in a map body (ruling P12) does not see one reached through a procedure-reference parameter or a `let-proc` local, serial and parallel | Reproduced on `59f727db`: C, G and M build; the named control is refused `run_ref_placement_invalid` | Refuses three program shapes that build today: needs [decision O1](#open-decisions-for-the-coordinator) | TA3 | `tests/test_workflow_lisp_run_ref_workflow_program.py::test_confined_site_behind_a_reference_in_a_map_frame_is_refused[param,let-proc,parallel]` |
| A3 | An output slot named like a field of the structured result is found only after the provider has run | Reproduced on `59f727db`: compile exit 0; run launches the provider once, then `provider_result_invalid` (`duplicate_artifact_name`) | None if refused at run time before launch; the compile-time refusal is a cut candidate (O2) | TA2 | `tests/test_workflow_evaluated_providers.py::test_output_slot_named_like_a_result_field_is_refused_before_launch` |

### Class B

| Id | Defect | Status | Identity | Task | Pinning test |
| --- | --- | --- | --- | --- | --- |
| B1 | Two `:out` slots filled with the same path commit; one file serves both outputs | Reproduced on `59f727db`: exit 0, committed | None (run time, before launch); a run that commits today fails after the fix (O1 covers it) | TA2 | `::test_two_output_slots_with_one_destination_are_refused_before_launch` |
| B2 | An inner binding that is not a procedure reference does not hide an outer procedure reference of the same name (`let*`, a `match` arm binder, loop state) | Reproduced on `59f727db`: `let*` gives 2 (calls `increment` though `g` is 5); the arm binder gives 2 | Cut (row 2) | Cut | The cut's |
| B3 | A `let-proc` local named like a `defun` or a form: the by-name call reaches the function or form | Reproduced on `59f727db`: 100 (the `defun`), and 1 for a local named `print` | Cut (row 1) | Cut | The cut's |
| B4 | Macro hygiene in head position: a template-bound name at the head of a list is not renamed, so a caller's binding answers the template's call | Reproduced on `59f727db`: 10, intended 6; without the caller's binding `procedure_call_unknown` | Cut (row 4) | Cut | The cut's |
| B5 | Macro hygiene never renames a template's `let-proc` binder; caller code passed to the macro calls the template's local | Reproduced on `59f727db`: builds, 6, by name and by `(proc-ref bump)` | Cut (row 3) | Cut | The cut's |
| B6 | A `Bool` result accepts the JSON strings `"true"` and `"false"` in any case | Reproduced on `59f727db`: the string `"TRUE"` commits `true` | Refusing it changes what a run accepts | **Not fixed**: see [Not Worth Fixing](#not-worth-fixing) | Specification §8.10 states it |

### Class C

| Id | Defect | Status | Identity | Task | Pinning test |
| --- | --- | --- | --- | --- | --- |
| C1 | Effect summaries are unsound for imported workflows: the fixpoint keeps an imported workflow's summary for its first round only, and a missing summary reads as "no effects" | Reproduced on `59f727db` through the declared ceiling: a procedure declared `:effects ((calls-workflow lib-w))` over an imported workflow that runs command `c` builds and runs; the same with a local workflow is refused `procedure_effect_ceiling_exceeded` | No digest moved in four sample programs; it refuses under-declared ceilings that build today: O1 | TC1 | `tests/test_workflow_lisp_effect_ceilings.py::test_ceiling_counts_the_effects_of_an_imported_workflow`; `::test_a_workflow_call_without_a_summary_is_not_read_as_pure` |

### Class D

| Id | Defect | Status | Identity | Task | Pinning test |
| --- | --- | --- | --- | --- | --- |
| D1 | A pure `match` under a shadowing `let*`, used as an operand | Crash on `59f727db`; **builds on `feat/coherence-e1` (`94236abf`)** | None | TD1 pins it after E1 | Grid row `operand x match` |
| D2 | A loop's `continue` value holding an effectful `if` inside an operand | Crash on `59f727db`; on E1 refused `effect_not_permitted` (fn form probed; E1 is 49 commits behind `main` and has no binder form) | None | TD1 pins | E1's grid, `continue` rows |
| D3 | A map inside a `continue` argument of a procedure specialized by a reference | Crash on `59f727db`; on E1 refused `effect_not_permitted` | None | TD1 pins | Grid row `continue x nested-map`, specialized |
| D4 | `:max (match …)` on a loop | Crash on `59f727db` **and on E1** | None | TD1 fixes | Grid row `:max x match` |
| D5 | Reading a variant field on the `match` subject instead of the arm's binder passes typecheck | Crash on `59f727db` | None | TD2 | `tests/test_workflow_lisp_match_subject_calls.py::test_field_read_on_the_subject_inside_its_arm` |
| D6 | A variant-only field read when the tested name is rebound in one operand while a sibling operand tests it | Crash on `59f727db` | None | TD4 | `tests/test_workflow_lisp_if_variant_field_lowering.py::test_sibling_operand_rebinds_the_tested_name[both orders]` |
| D7 | A nested loop with commands used directly as an operand, with or without a macro | Crash on `59f727db` (both); bound with `let*` first it builds | None | TD3 | `tests/test_workflow_lisp_loop_recur.py::test_nested_loop_is_an_operand` |
| D8 | A `list/map` with a `match` body used directly as an `if` condition inside a loop body | Crash on `59f727db`, both loop forms | None | TD3 owns the cause; Task 0b (its D1) pins the seed's program | Task 0b's `test_map_with_a_match_body_is_a_condition_inside_a_loop` |
| D9 | A `let-proc` local whose body is a loop with a `loop-state` | Traceback on `59f727db` (exit 1), fn form, binder form, called by name or by reference | None | TD5 | `tests/test_workflow_lisp_let_proc_bindings.py::test_local_whose_body_is_a_loop_with_state` |
| D10 | A `let-proc` local that forwards a captured outer procedure reference | Crash on `59f727db` | None | TD6 | `::test_local_forwards_a_captured_reference` |
| D11 | A one-call map body that is such a local | Crash on `59f727db` (a different site from D10) | None | TD6 | `::test_local_capturing_a_reference_is_a_map_body` |
| D12 | A `defworkflow` with a workflow-reference parameter, used as the entry or called | Crash on `59f727db`, three sites; declared and never called it builds | None if refused at the use, which crashes today | TD7 | `tests/test_workflow_lisp_workflow_refs.py::test_workflow_formal_reference_is_refused_at_its_use[entry,literal,bare]` |
| D13 | An `Int` literal beyond 64 bits | Crash on `59f727db`; folded arithmetic of the same size is refused `pure_expr_overflow` | None | TD8 | `tests/test_workflow_pure_expr.py::test_int_literal_beyond_64_bits_is_refused` |
| D14 | An empty `(list)` in a `match` arm (Task 0b's D2) | **Not reproduced** as a crash in twelve shapes, on `59f727db` or on the tree the design was written against: it builds where the position states the type and is refused `list_empty_type_context_required` where it does not | — | Task 0b | Task 0b's |
| D15 | A parallel map written directly in a `loop/recur` body | **No longer reproduces**: closed by I1 (`624ff688`); crashed on `a58e5b17` | — | T0 pins | Backlog module, row `D15` |
| D16 | A procedure reference chosen with `if` | **No longer reproduces**: closed by C1 (`b6646fde`), `proc_ref_literal_required` | — | T0 pins | Backlog module, row `D16` |
| D17 | A `bind-proc` value that holds a serial map | **Not re-run** (I1 first review: crash on its base and tip, "typed list/map expression is missing its result element type") | None | TD6 re-runs it first | — |
| D18 | A provider extern used as a value in reached code | **Not re-run** (staged-authoring design §2, D7) | None | Staged-authoring P1 and P2 | Theirs |

### Class E

| Id | Defect | Status | Identity | Task | Pinning test |
| --- | --- | --- | --- | --- | --- |
| E1 | `(and (= u.variant A) …)` and the `or` mirror grant no proof in a module compile, though the expression typechecker grants it | Reproduced on `59f727db`: `variant_ref_unproved` | None (admits refused source) | TE1 | `tests/test_workflow_lisp_variant_proofs.py::test_compound_test_proves_a_read_in_a_module` |
| E2 | A discriminant proof reaches a parallel `list/map-effect` body and a pure `list/map` body, not a serial `list/map-effect` body | Reproduced on `59f727db` | None | TE1 | `::test_proof_reaches_a_serial_map_body` |
| E3 | The `variant_ref_unproved` message says a proof does not reach into a map | Reproduced (the message of E1 and E2) | None | TE1 | Code only; no message assertion |
| E4 | In a generic procedure a discriminant test on a value of a type parameter is refused `variant_tag_union_mismatch`, naming two "incompatible unions" | Reproduced on `59f727db` | None (a code on a refused program) | TE4 | `::test_discriminant_test_on_a_type_parameter_has_its_own_code` |
| E5 | `cond`, `if` and `match` can be bound as names | Reproduced on `59f727db`: all three build and run | Reserving them refuses source that compiles | **Not fixed** | — |
| E6 | A `defproc` parameter of procedure-reference type forwarded through `let*` | Reproduced on `59f727db`: `name_unknown`; the uncalled procedure builds | None | TE2 | `tests/test_workflow_lisp_callables_coherence.py::test_reference_parameter_forwarded_through_let` |
| E7 | A generic procedure called in a `list/map-effect` body | Reproduced on `59f727db`: `procedure_call_unknown` naming `%parametric-call.m.gstep.…` | None | Task 0b (its D3) | Task 0b's |
| E8 | A `bind-proc` over a procedure's own parameter, passed to a `ProcRef` parameter | Reproduced on `59f727db`: `procedure_lowering_unresolved` | None | Task 0b (its D5) | Task 0b's |
| E9 | **Found while planning.** A pure procedure whose body is a loop, passed by `proc-ref` to a pure procedure that calls it | Reproduced on `59f727db`: `procedure_call_unknown`, "unknown procedure callee `f`"; it builds when either procedure has an effect, and when called directly | None | TE3 | `::test_pure_loop_procedure_is_called_through_a_reference` |
| E10 | A free name in a macro template binds to the caller's local | Reproduced on `59f727db` (6 for `y = 5`) | Changing it changes meaning | **Not fixed**: specification §34 now states it | — |
| E11 | A workflow defined by a macro gets its parameters renamed and cannot be called or used as an entry | Reproduced on `59f727db`: `workflow_signature_mismatch` | Cut (row 5) | Cut | The cut's |
| E12 | `defpath` ignores an unknown keyword | Reproduced on `59f727db` | Cut (row 6) | Cut | The cut's |
| E13 | Return guidance on a workflow, procedure or function is checked and discarded | Reproduced on `59f727db`: equal digests with and without | Cut (row 7) | Cut | The cut's |
| E14 | `TimestampNs` was documented as a type | `type_unknown` on `59f727db`; **closed by the documentation** (corpus T3a removed it from specification §7.1) | — | None | — |
| E15 | A prompt extern's path is checked when the call runs, not at compile | Reproduced on `59f727db`: a missing or outside `asset_file` compiles; the run fails before launch | A compile refusal refuses source that compiles: cut candidate (O2) | Not planned | — |
| E16 | A missing prompt file is reported as a bare `[Errno 2]` | Reproduced (E15's run) | None | With A1's branch if it takes it; else TA2 | — |
| E17 | Dead code: the prompt snapshot and attempt-identity builders, the fragment-identity projection, `render_prompt_fragment_base`, `structural_bootstrap_plan`, two lints that nothing raises, inert remnants of `requires_variant` | Confirmed by `grep` on `59f727db`: no caller in `orchestrator/` | None expected; TE5 proves it | TE5 | The removal test (`tests/test_retired_executors_removed.py`), extended |
| E18 | `list/map` inside a macro template | **Not a defect**: `list_map_binder_invalid` only when the binder has the name of a template local, which the same program written in place also gets | — | T0 pins both | Backlog module |
| E19 | A call to a `let-proc` local inside a macro template | **No longer reproduces**: closed by C1 (4 on `59f727db`); the reference-local half is B4 | — | T0 pins | Backlog module |
| E20 | A template's `cond` test captured by the caller | **No longer reproduces**: closed by I2a (`bdf49443`), 1 on `59f727db` | — | T0 pins | Backlog module |
| E21 | A pure operand of an operator renames the effects beside it | Not re-run (E1's second review) | Cut (row 8) | Cut | — |
| E22 | Local and generated names are part of the program digest | Not re-run | Cut (row 9), with roadmap R2 | Cut | — |
| E23 | `bind-proc :fixed tmp` over a local `tmp` | Not re-run (I2a's second re-review, minor 10: `name_unknown`) | None | TE2 re-runs it first | — |

Not defects, for the record: result guidance on a provider or command effect is part of program
identity (a specification correction, made); a computed `:max` below 1 over an empty list fails by
design.

## Reproductions

| Id | Program | Today | Where in the code |
| --- | --- | --- | --- |
| A1 | Fixture `_fixture`/`_cli` of `tests/test_workflow_evaluated_providers.py`, its `SOURCE` at 2.40, prompt manifest `{"prompts.base": {"input_file": "nope.md"}}`, stand-in `codex` | Exit 0; one request | `workflow/prompting.py:read_prompt_source_with_sha256`, the `input_file` branch (`if input_path.exists()`) |
| A2 | The `CONFINED` controller of `tests/test_workflow_lisp_run_ref_workflow_program.py` at 2.40 with `MAP_CALLEES`, plus `(defproc hide1r ((n Int)) -> Int (call one :seed n :revision "r"))`, `(defproc viaparam1 ((f ProcRef[Int -> Int]) (xs List[Int])) -> Int (list/length (list/map-effect ((x xs)) :max 2 (f x))))`, `(defproc par1 ((f ProcRef[Int -> Int])) -> Int (list/length (list/map-effect ((repo (list "a"))) :max 1 :parallel 1 :workspace repo (f 1))))`. Bodies replacing `MAP_RUN_BODY`: **C** `(let* ((xs (viaparam1 (proc-ref hide1r) (list 1 2)))) 1)`; **G** `(let* ((xs (let-proc ((h ((n Int)) -> Int (call one :seed n :revision "r"))) (viaparam1 (proc-ref h) (list 1 2))))) 1)`; **M** `(let* ((xs (par1 (proc-ref hide1r)))) 1)`; control `(list/length (list/map-effect ((x (list 1 2))) :max 2 (hide1r x)))` | C, G, M build; the control is refused | `typecheck_run_ref.py:_refuse_confined_site_in_map_frame` and `_callees`: a `ProcedureCallExpr` is followed only when its name is in `program.procedures`; a reference parameter `f` is not, and the `proc-ref` literal sits in the caller, outside the frame |
| A3 | Same provider fixture. `(defpath Report :kind relpath :under "artifacts" :must-exist false) (defrecord Result (ok Bool) (report Report)) (defprompt review (:fills (report :path :out Report)) -> Result "Report={report}") (defworkflow run ((message String) (report Report)) -> Result (provider-result providers.review :prompt (review :report report)))`, input `report=artifacts/report.txt` (the file exists), stand-in result `{"ok":true,"report":"artifacts/report.txt"}` | One launch, then exit 1 | `workflow/evaluated/providers.py:provider_result` (the overlap check runs after the result is read); `resolve_provider_input` knows both name sets before launch |
| B1 | Same, with `(defrecord Result (ok Bool))` and `(defprompt review (:fills (a :path :out Report) (b :path :out Report)) -> Result "A={a} B={b}")`, called `(review :a report :b report)` | Exit 0, committed | `contracts/output_contract.py:validate_prompt_output_position_destinations` has no caller outside `tests/test_output_contract.py` |
| B2 | `INC`; `() -> Int (let* ((g (proc-ref increment))) (let* ((g 5)) (g 1)))`. Arm binder: `U INC`; `((u U)) -> Int (let* ((g (proc-ref increment))) (match u ((A g) (g 1)) ((B b) 0)))` | 2; 2 | `typecheck_dispatch.py:_typecheck`, the `let*` branch (`local_proc_ref_env` is never cleared by a binding that is not a reference) |
| B3 | `(defun f ((n Int)) -> Int (* n 100))`; `() -> Int (let-proc ((f ((x Int)) -> Int (+ x 1))) (f 1))` | 100 | `expressions.py:_elaborate_local_hooks` (the collision set lacks function names and form heads); `_elaborate_list` resolves forms and functions before locals |
| B4 | `INC DBL (defmacro mm (x) (let* ((f (proc-ref increment))) (f x)))`; `() -> Int (let* ((f (proc-ref dbl))) (+ 0 (mm 5)))` | 10 | `macros.py:_apply_hygiene`, `_hygienic_generic_list` (item 0 of a list is not renamed); what a head names is known only to the resolver |
| B5 | `(defmacro with-bump (k body) (let-proc ((bump ((x Int)) -> Int (+ x k))) body))`; `((n Int)) -> Int (with-bump 5 (bump n))` | 6 for `n = 1` | `macros.py:_hygienic_let_proc` |
| B6 | `() -> Bool E(strb, TRUE, Bool)` with a stand-in that writes the JSON string `"TRUE"` | `true` | `contracts/output_contract.py:_parse_output_bundle_value` (`value_type == "bool"`) |
| C1 | `lib.orc`: `(defmodule lib) (export lib-w) (defworkflow lib-w ((n Int)) -> Int E(libw, 7, Int))`. `m.orc`: `(import lib :only (lib-w))`, `(defproc p ((n Int)) -> Int :effects ((calls-workflow lib-w)) (call lib-w :n n))`, `(defworkflow run () -> Int (p 1))`. Control: `lib-w` defined in `m` | Builds, runs `libw`, 7. Control: `procedure_effect_ceiling_exceeded`, "does not cover (uses-command(c))". With `:effects ()` the imported case reports `(calls-workflow(lib::lib-w))` only, the local one also `uses-command(c)` | `compiler.py:_infer_stage3_effect_summaries` (`next_workflow_effects` is rebuilt from the module's own `typed_workflows`; imported procedures have `imported_procedure_effects`, workflows have no counterpart); `typecheck_calls.py:typecheck_call_expr` (`workflow_effects_by_name.get(name, EMPTY_EFFECT_SUMMARY)`) |
| D1 | `(defunion Shape (CIRCLE (r Int)) (SQUARE (side Int)))`; `() -> Int (let* ((c 1000)) (+ c (let* ((c 5)) (match (variant Shape SQUARE :side 2) ((CIRCLE k) k.r) ((SQUARE s) c)))))` | Crash (`TypeError: expected linear WCC value body, found WccCase`) | `wcc/elaborate.py:_body_to_prefix_and_value`, from `_elaborate_operands_to_values` |
| D2 | `((n Int)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (> s 0) (done s) (continue (+ (if (> n 0) E(e, 1, Int) 0) 9))))` | Crash (`… found WccIf`) | Same |
| D3 | `STEP (defproc via-cont ((f ProcRef[Int -> Int]) (xs List[Int])) -> Int (loop/recur :max 3 :state 0 :on-exhausted 0 (fn (s) (if (= s 0) (continue (list/length (list/map-effect ((x xs)) :max 2 (f x)))) (done s)))))`; `() -> Int (via-cont (proc-ref step) (list 1 2))` | Crash (`… found WccRecJoin`) | Same |
| D4 | `U`; `((u U)) -> Int (loop/recur ((s 0)) :max (match u ((A a) a.n) ((B b) 1)) :on-exhausted 0 (done s))` | Crash (`TypeError: unsupported WCC elaboration node: MatchExpr`) | `wcc/elaborate.py:_elaborate_loop_recur_to_body` to `_elaborate_expr_to_value` |
| D5 | `U`; `((u U)) -> Int (match u ((A a) u.n) ((B b) 0))` | Crash (`TypeError: expected record type while resolving u.n`) | `wcc/elaborate.py:_elaborate_match_case_with_subject` to `_infer_expr_type` |
| D6 | `U`; `((u U)) -> Int (+ (let* ((u (variant U A :n 1))) (if (= u.variant A) u.n 0)) (if (= u.variant A) u.n 0))` | Crash (`CheckedFormError: union field 'n' is absent or has variant-dependent types`) | Raised in `contracts/closed_program/check.py:_field_type`; cause in `wcc/hygiene.py` (it renames the hoisted binding and its atoms, not the `(binding, union, tag)` proof triples of `WccIf`/`WccSelect`) |
| D7 | `STEP CHK`; `() -> Int (let* ((tmp (step 3))) (+ tmp (let* ((tmp (step 1))) (loop/recur :max 2 :state tmp :on-exhausted s (fn (s) (if (check s) (done s) (continue (loop/recur :max 1 :state (+ s tmp) :on-exhausted u (fn (u) (done (step u)))))))))))` | Crash (`KeyError: 'u'`); with the inner `let*` hoisted into the outer binding list it builds | `wcc/elaborate.py:_infer_expr_type`, reached from `_elaborate_atomic_value` |
| D8 | `U`; `((u U)) -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (if (= (list/length (list/map ((v (list u u))) (match v ((A a) a.n) ((B b) 0)))) 2) (done 1) (continue (+ s 1))))` | Crash (`KeyError: 'v'`) | `wcc/elaborate.py:_infer_expr_type`, reached from `closed/command_templates.py:_effectful_binding_control_fact` through `binding_type_for_elaboration` |
| D9 | `AP`; `((n Int)) -> Int (let-proc ((h ((v Int)) -> Int (loop/recur ((s (loop-state (i Int 0)))) :max 1 :on-exhausted 0 (done s.i)))) (h n))` | Traceback (`RuntimeError: typed loop-state carrier has no retained expanded-declaration family`) | `loop_state.py:_typecheck_loop_state_seed`; raised in typecheck, outside `diagnostics.py:compiler_defect_boundary` |
| D10 | `INC`; `() -> Int (let* ((p (proc-ref increment))) (let-proc ((f ((x Int)) -> Int (p x))) (f 1)))` | Crash (`ValueError: command capture has no retained binder in its lexical frame`) | `closed/command_templates.py:bind`, from `wcc/elaborate.py:_command_bound_bindings` |
| D11 | `STEP (defproc via ((f ProcRef[Int -> Int]) (xs List[Int])) -> Int (list/length (list/map-effect ((x xs)) :max 2 (f x))))`; `() -> Int (let* ((g (proc-ref step))) (let-proc ((h ((n Int)) -> Int (g n))) (via (proc-ref h) (list 1 2))))` | Crash (`TypeError: unhashable type: 'list'`) | `workflow/evaluated/provider_io.py:bind`, from `closed/build.py:_bind_provider_io` |
| D12 | `(defrecord Box (n Int)) (defworkflow helper ((b Box)) -> Box b) (defworkflow invoke ((runner WorkflowRef[Box -> Box])) -> Box (record Box :n 1))`. (a) `invoke` as the entry; (b) `() -> Box (call invoke :runner (workflow-ref helper))`; (c) `:runner helper` | (a) `CanonicalNameError: canonical identity is missing owner facts`; (b) `TypeError: unsupported WCC elaboration node: WorkflowRefLiteralExpr`; (c) `KeyError: 'helper'` | (a) `closed/names.py:canonical_type_descriptor`; (b) `wcc/elaborate.py:_elaborate_expr_to_value`; (c) `wcc/elaborate.py:_infer_expr_type`, both from `_elaborate_workflow_call_binding_value` |
| D13 | `() -> Int 9223372036854775808` | Crash (`CheckedFormError: literal does not match its descriptor`) | Raised in `contracts/closed_program/check.py:_value`; the typechecker accepts the literal |
| D14 | Tried: the arm in a result, a record field, a procedure argument, an `if` arm, a command subject, a `let*` binding, a loop `done`, both orders of arms | Builds, or `list_empty_type_context_required` | The crash text of the design ("typed list is missing its resolved child types") is at `wcc/elaborate.py:_elaborate_expr_to_value`, the `ListExpr` branch |
| D15 | `() -> Int (loop/recur ((s 0)) :max 2 :on-exhausted 0 (done (list/length (list/map-effect ((r (list "a" "b"))) :max 2 :parallel 2 :workspace r E(p, 1, Int)))))` | Builds | — |
| D16 | `INC`; `((n Int)) -> Int (let* ((g (if (> n 0) (proc-ref increment) (proc-ref increment)))) (g 1))` | `proc_ref_literal_required` | — |
| E1 | `U`; `((u U) (r Bool)) -> Int (if (and (= u.variant A) r) u.n 0)`; mirror `(if (or (!= u.variant A) r) 0 u.n)` | `variant_ref_unproved` | `conditionals.py:_normalize_short_circuit` hoists the condition into a generated binding; the final `if` is checked on a bare name with no facts |
| E2 | `U`; `((u U)) -> List[Int] (if (= u.variant A) (list/map-effect ((y (list 1 2))) :max 2 (command-result c :argv ("python" "c.py" "m" u.n) :returns Int)) (list 0))`. Controls: the same with `:parallel 1 :workspace y` over `(list "a")`; `(list/map ((y (list 1 2))) (+ y u.n))` | Refused; both controls build | `typecheck_structural_values.py:typecheck_structural_value_expr` types a serial map as a synthetic loop, and a proof does not enter a loop body (`typecheck_loop_recur.py:typecheck_loop_recur_expr`) |
| E4 | `(defunion U (OK (n Int)) (BAD (why String))) (defproc pick :forall (T) ((x T)) :where ((T has-union-variant OK (n Int)) (T has-union-variant BAD (why String))) -> Int (if (= x.variant OK) 1 0))`; `((u U)) -> Int (pick u)` | `variant_tag_union_mismatch` | `typecheck_pure_ops.py:_typecheck_ordinary_equality` |
| E5 | `((x Int)) -> Int (let* ((if 1)) if)`; the same with `cond`, `match` | 1 | No reserved-name check on binders (`expressions.py`) |
| E6 | `INC (defproc fw ((p ProcRef[Int -> Int]) (x Int)) -> Int (let* ((g p)) (g x)))`; `() -> Int (fw (proc-ref increment) 1)` | `name_unknown` (`p`) | `typecheck_dispatch.py:_typecheck`, the `let*` branch, in the specialized copy |
| E7 | `(defproc gstep :forall (T) ((v T)) -> T (let* ((x E(g, 1, Int))) v))`; `() -> Int (list/length (list/map-effect ((x (list 1 2))) :max 2 (gstep x)))` | `procedure_call_unknown` | `procedure_typecheck.py:typecheck_procedure_call_expr` |
| E8 | `AP (defproc add ((n Int) (x Int)) -> Int (+ n x)) (defproc outer ((k Int)) -> Int (apply1 (bind-proc (proc-ref add) :n k) 1))`; `() -> Int (outer 2)` | `procedure_lowering_unresolved` | `functions.py:select_materialized_procedure`; `procedure_specialization.py` |
| E9 | `AP (defproc h ((v Int)) -> Int (loop/recur ((s v)) :max 1 :on-exhausted 0 (done s)))`; `((n Int)) -> Int (apply1 (proc-ref h) n)`. Builds: `(h n)` directly; `h` with `(done E(e, 4, Int))`; `apply1` with an effect before `(f v)` | `procedure_call_unknown`, callee `f` | Message at `procedure_typecheck.py:typecheck_procedure_call_expr`; cause not found (the pure-call path, `functions.py`, is the suspect) |
| E10 | `(defmacro uses-y () (+ y 1))`; `((y Int)) -> Int (uses-y)` | 6 for `y = 5` | `macros.py:_apply_hygiene` (free names are left alone by design) |
| E11 | `(defmacro mk (name) (defworkflow name ((n Int)) -> Int (+ n 1))) (mk child)`; `() -> Int (call child :n 2)` | `workflow_signature_mismatch` | `macros.py:_apply_hygiene` |
| E12 | `(defpath P :kind relpath :under "state" :must-exist true :must-exist-target false)` | Builds | `definitions.py:_elaborate_defpath` |
| E13 | `(defun f ((x Int)) -> (result Int :description "fmarker") x)` against `-> Int` | Equal `program_digest` | `result_guidance.py:parse_return_spec`, used by `workflows.py`, `procedures.py`, `functions.py` |
| E15 | Provider fixture, manifest `{"prompts.base": {"asset_file": "missing.md"}}` or `"../outside.md"` | `compile` exit 0; `run` exit 1 before launch | `workflow_lisp/build_manifest_io.py` (no path check); read in `workflow/evaluated/providers.py:_read_source` |
| E17 | `grep` for a caller in `orchestrator/` | None for `validate_compiled_prompt_fragment_identity`, `render_prompt_fragment_base`, `apply_typed_prompt_input_injection`, `structural_bootstrap_plan`; `prompt_identity.py` (1,972 lines) and `prompt_dependency_evidence.py` (1,587) are imported only by each other and, for `_attempt` and `_validate_attempt`, by `provider_phased_delivery/ledger.py` | `workflow/prompt_identity.py`, `workflow/prompt_dependency_evidence.py`, `workflow_lisp/prompts.py`, `workflow/prompting.py`, `workflow/prompt_fragment_contract.py`, `workflow/typed_prompt_inputs.py`, `workflow_lisp/context_classification.py`, `workflow_lisp/lints.py` (`legacy_adapter_missing_fixture`, `manual_when_requires_variant_pair`), `workflow/run_ref/step_config.py` |
| E18 | `(defmacro mm (x) (let* ((v (list x x))) (list/length (list/map ((v v)) (+ v 1)))))`; in place `(let* ((v (list 1 1))) (list/length (list/map ((v v)) (+ v 1))))` | Both `list_map_binder_invalid`; with a different binder name the macro gives 2 | — |
| E19 | `(defmacro twice (a) (let-proc ((h ((x Int)) -> Int (+ x 1))) (+ (h a) (h a))))`; `() -> Int (twice 1)` | 4 | — |
| E20 | `(defmacro mm (x) (let* ((flag true)) (cond (flag 1) (true 0))))`; `() -> Int (let* ((flag false)) (mm 1))` | 1 | — |

## Common Causes

| Cause | Rows | One fix |
| --- | --- | --- |
| K1. A check on prompt outputs exists and nothing calls it before launch | A3, B1 | TA2 |
| K2. A call through a procedure reference has no name the typed walk can follow; only the specialized program knows the callee | A2 (and it was I1's blocker, fixed there by scanning the closed tree) | TA3: scan the closed tree, as `closed/build.py:refuse_map_bodies_beside_run_refs` does |
| K3. Imported workflows have no kept summary, and a missing summary is the empty one | C1; it was I1's third-review blocker | TC1 |
| K4. A control form (`if`, `cond`, `match`, a loop, a map) reaches an operand position that expects a linear value body | D1, D2, D3, D4; E1 (the branch) fixes the cause for fields, operands and `continue` | TD1: pin what E1 closes, fix `:max` |
| K5. Type re-inference at elaboration runs outside the scope of a binder (a loop's state name, a map's item name) | D7, D8, the macro spelling of D7 | TD3 |
| K6. Variant proof facts are keyed to a surface name or shape that a later pass rewrites: the hoisted condition binding, the serial map's synthetic loop, the hygiene rename | E1, E2, E3, D6 | TE1 (the two refusals) and TD4 (the crash): two tasks, because TD4's obvious fix gives a wrong value unless the read is keyed too |
| K7. A `let-proc` local is typed in a context that lacks what a named procedure has: the loop-state declaration family, a retained binder for a captured reference | D9, D10, D11, D17 | TD5 (loop state), TD6 (captured reference) |
| K8. Hygiene is syntactic and resolution is not: binders in head position, `let-proc` binders, workflow parameters, non-reference bindings that should hide a reference | B2, B3, B4, B5, E11 | The cut: one resolver-aware change. Two attempts inside the hygiene pass were withdrawn |
| K9. A form is parsed and its content dropped or ignored | E12, E13 | The cut |
| K10. A reference to a procedure is resolved only in some binding shapes | E6, E8, E9, E23 | TE2, TE3; E8 is Task 0b's |

## Global Constraints

- Pathspec commits (`git commit -- <paths>`); no assistant attribution; no `--no-verify`; no
  `git stash`. One worktree per lane; `PYTHONPATH` set to the working tree;
  `experiments/thread_m/no_provider` first on `PATH`; `mkdir -m 700` for any basetemp.
- Tests assert behavior, diagnostic codes and values, never message text. New `.orc` test sources
  declare `(:target-dsl "2.40")`. A new test fails first for its stated reason. Function complexity
  at most 12 for added code.
- **Identity check, for every task that touches `orchestrator/`:** the three invariant files of
  Task T0 are byte-identical between the task's base and its tip, or the task's ledger entry names
  every row that differs and why. A task that only admits refused source or turns a crash into a
  result expects no row to differ among sources that build.
- **Gate:** the task's narrow run, then `pytest -q -n 16 --dist=worksteal --sample 10`;
  `pytest --collect-only` on each test module added or edited; before each merge to `main` the
  whole suite, run by the coordinator, which may batch several of these branches on one integration
  branch.
- A fix that would refuse source that builds today, or move a digest, stops at that point and goes
  to the coordinator; it is not merged under this plan except by decision O1.

## Order And File Ownership

Order of priority: T0; class A (TA2, TA3); class C (TC1); class B has no task of its own (B1 rides
TA2, B2 to B5 are the cut's, B6 is not fixed); class D by how likely an ordinary workflow meets it
(TD2, TD1, TD3, TD5, TD6, TD4, TD8, TD7); class E (TE1, TE2, TE3, TE4, TE5); TP2; TF.

| Lane | Tasks, in order | Files | Waits on |
| --- | --- | --- | --- |
| 0 | T0, then TP1 | new `tests/test_workflow_lisp_defect_backlog.py`, new `scripts/invariants/`; `diagnostics.py`, `compiler.py` (the boundary only) | — |
| 1 Provider run time | TA2, TE5 | `workflow/evaluated/providers.py`, `contracts/output_contract.py`; then the dead prompt modules | `fix/missing-prompt-file` merged (same two files); staged-authoring Task T edits `providers.py` too: one after the other |
| 2 Run references | TA3 | `closed/build.py`, `typecheck_run_ref.py` | Decision O1 |
| 3 Effect summaries | TC1 | `compiler.py` (the fixpoint), `typecheck_calls.py` | Decision O1; after TP1 (same file) |
| 4 Elaboration | TD2, TD1, TD3, TD7, TP2 | `wcc/elaborate.py`, `closed/names.py`, `closed/command_templates.py` | `feat/coherence-e1` merged (it rewrites 378 lines of `wcc/elaborate.py`); one task at a time, the file is shared |
| 5 Locals and proofs | TD5, TD6, TD4, TD8 | `loop_state.py`, `closed/command_templates.py` (`bind`), `workflow/evaluated/provider_io.py`, `wcc/hygiene.py`, `typecheck_pure_ops.py` | TD6 after lane 4's TD3 if both edit `command_templates.py` |
| 6 Typecheck | TE1, TE2, TE3, TE4 | `conditionals.py`, `typecheck_proofs.py`, `typecheck_dispatch.py`, `typecheck_loop_recur.py`, `procedure_typecheck.py`, `functions.py` | E1 merged (it edits `typecheck_dispatch.py`, `typecheck_proofs.py`, `typecheck_loop_recur.py`, `typecheck_structural_values.py`); Task 0b edits `procedure_typecheck.py`: TE3 before or after it, not beside |

Lanes 0, 1, 2, 3 and 5 can start now and run in parallel. Lanes 4 and 6 wait for E1. The
staged-authoring plan's tasks start after E1 too and share lanes 4 and 6's files; the coordinator
interleaves them.

## Tasks

### Task T0: Reproductions and invariant checks into the repository (5 h)

- [ ] `tests/test_workflow_lisp_defect_backlog.py`: every program of the Reproductions table that
      this plan fixes or that is closed, through the public command line with the stand-in command
      and `closed_path`. Each row states the outcome wanted (a value, a refusal code, "builds").
      Rows that fail today are in a dictionary `KNOWN` (id to today's outcome kind: `crash`,
      `traceback`, a refusal code, a value); the test asserts a known row still fails that way and
      every other row gives the wanted outcome. `KNOWN` may only shrink: a fix removes its row. The
      closed rows (D15, D16, E18, E19, E20) are regression pins from the start. The cut's rows (B2
      to B5, E11 to E13) are not in the module; the cut owns their tests.
- [ ] `scripts/invariants/`: `compile_all.py`, `digests.py`, `program_digests.py`, the normalizer
      and one wrapper, taken from `experiments/authoring_revisions/inv/` on
      `spike/authoring-revisions` (`4aca9f81`), which generates provider externs so that sources
      naming a provider reach the build (staged-authoring ruling M4). They exist today only there
      and in session scratch. The wrapper takes a revision and an output directory and hard-codes
      no path. A `README` states the three cautions: never run the compile check inside the
      repository (it writes `.orchestrate/build/`); run the run-reference tests serially with a
      fixed `--basetemp`; drop `compiler_runtime_identity_digest` and `resolved_commit_sha`.
- [ ] Record in the ledger, for `main`: the three SHA-256 values, files compiled and built (635 and
      34 without generated externs on `59f727db`), corpus rows, run-reference programs.
- [ ] The staged-authoring plan's Task 0 uses the same kit: do it once, here or there.
- Failing first: the module's `KNOWN` starts empty and the test fails on each open row; then the
  rows are entered.
- Reviewer: that a `KNOWN` row cannot pass by failing in a new way (the outcome kind is compared,
  for a crash also the exception class); that the module takes under a minute at `-n 8`, else it
  is sampled.

### Task TA2: Output slots are checked before launch (A3, B1, E16) (5 h)

- [ ] In `workflow/evaluated/providers.py:resolve_provider_input`, after the expected outputs are
      known: refuse when a slot name equals a field of the structured result that publishes an
      artifact, and when two slots resolve to one destination. Use
      `validate_prompt_output_position_destinations`, or delete it and write the five lines if its
      signature does not fit; do not keep both.
- [ ] Tests (fail today): the two named in the table; each asserts exit 1, the violation type, and
      **no request received by the stand-in provider**. A control with two slots and two paths
      still commits.
- [ ] If `fix/missing-prompt-file` did not give a missing `asset_file` a coded failure with the
      source kind, do it here (E16); else drop this item.
- [ ] `specs/providers.md` and `specs/io.md`: the two refusals, in the change list.
- Identity: invariants identical (no compile path changes). Reviewer: an agent turn and a phased
  provider call (`phased_providers.py`) take the same check; a slot on a path that does not exist
  yet; resume of a run that committed under the old behavior (it must replay, not re-validate).

### Task TA3: Ruling P12 holds through references (A2) (8 h)

- [ ] Refuse a confined site reached from a `list/map-effect` iteration by scanning the final
      closed tree, where references are resolved, beside
      `closed/build.py:refuse_map_bodies_beside_run_refs`. Keep the typed walk
      (`typecheck_run_ref.py`) for the cases it sees, because its message points at the body.
- [ ] Tests (fail today): programs C, G, M refuse `run_ref_placement_invalid`; a reference to a
      procedure with a path-mode (not confined) run reference in a one-call body still builds; a
      confined site in a procedure that is passed by reference and never reaches a map still
      builds.
- Identity: the run-reference digests and the compile check identical; no tracked source has the
  shape (the I1 reviews searched). Needs O1 before merge.
- Reviewer: a reference passed through two procedures, through `bind-proc`, and from an imported
  module; that the scan does not refuse a confined site beside a map (only inside its iteration);
  how a confined site is marked in the closed tree (not verified while planning).

### Task TC1: Imported workflows keep their summaries (C1) (10 h)

- [ ] `compiler.py:_infer_stage3_effect_summaries`: keep the summaries of workflows compiled in
      earlier modules in every round, as `imported_procedure_effects` does for procedures. A
      scratch patch of four lines made the reproduction refuse with the full effect set and left
      the digests of four building programs equal.
- [ ] `typecheck_calls.py:typecheck_call_expr`: a workflow call whose callee has no summary is not
      read as pure. Where the summary is legitimately absent (the first round, for a local workflow
      not yet typed) keep the provisional path that exists for procedures; anywhere else raise.
- [ ] Audit by test, one case per consumer, each with an imported workflow two modules deep:

| Consumer | Site | Can it be wrong today? |
| --- | --- | --- |
| Declared `:effects` ceiling | `compiler.py:_validate_procedure_effects_and_cycles` | **Yes, shown**: an under-declared ceiling builds |
| Inferred-effects display | `procedures.py:procedure_effect_inspection`; the REPL (`repl_expr.py`, `repl_inspect.py`) | Yes, from the code: it prints the incomplete set |
| Run reference in a live-provider member | `typecheck_effects.py:typecheck_with_live_providers_expr`, `typecheck_with_live_provider_peers_expr` (the member loop) | Yes, from the code: no "any effect" check follows; not probed |
| Summary exported to an importing module | `compiler.py`, `workflow.effect_summary` | Yes, from the code: the hole compounds across modules |
| Run reference in `:on-exhausted`, a map source, a pure function, a guidance example, a settlement body | `typecheck_loop_recur.py`, `typecheck_structural_values.py`, `functions.py:rewrite`, `result_guidance.py`, `typecheck_effects.py` | Only the code: an "any effect" check follows and the call itself is a direct effect, so the program is still refused, with the general code |
| Purity checks (`defun`, `list/map` body, agent policy, provider dependencies) | `functions.py`, `typecheck_structural_values.py`, `typecheck_agents.py`, `typecheck_effects.py` | No: probed for `defun` and `list/map`; the call is a direct effect |
| Confined child effects | `typecheck_run_ref.py:_child_refusal` | No: it walks each imported program with that program's own summaries |
| Map bodies beside run references (I1) | `closed/build.py:refuse_map_bodies_beside_run_refs` | No: it scans the closed tree |

- Identity: all three invariants. Measured while planning with the scratch patch: the compile of
  every tracked `.orc` is byte-identical to the base (635 rows, 34 build, without generated provider
  externs). The other two were not run. Needs O1.
- Reviewer: an import cycle of summaries; a module that imports a workflow and shadows its name;
  whether any stored field of the closed program is derived from a summary (four samples say no).

### Task TP1: Typecheck failures inside the defect boundary (2 h)

- [ ] An internal exception raised during typecheck (D9's `RuntimeError`) is reported as
      `compiler_defect` with stage `typecheck`, by `diagnostics.py:compiler_defect_boundary`,
      instead of a traceback and exit 1. Diagnostics pass unchanged.
- [ ] Test: D9's program exits 2 with `compiler_defect`; its `KNOWN` row changes from `traceback`
      to `crash`.
- Reviewer: that no test relies on a typecheck exception escaping; `MemoryError` and
  `KeyboardInterrupt` still pass.

### Task TD2: A field read on the `match` subject inside its arm (D5) (6 h)

- [ ] Decide by reading the typechecker which it means: if it narrows the subject in the arm (it
      accepts the read), elaboration reads the field from the arm's binder; if the acceptance is an
      accident, the typechecker refuses with `variant_ref_unproved`. The first is consistent with
      `(if (= u.variant A) u.n 0)`, which works.
- [ ] Tests: the read gives the binder's value; a read of the other variant's field is refused;
      the subject rebound inside the arm reads the new binding.
- Identity: invariants identical. Reviewer: a subject that is an effect result, a subject shadowed
  by the arm binder of the same name, nested `match` on the same subject.

### Task TD1: Control forms as operands, the rest (D1 to D4) (5 h; after E1)

- [ ] After E1 merges, re-run D1, D2, D3 on `main` in both loop forms; move them out of `KNOWN`
      with the outcome E1 gives (D1 builds; D2 and D3 are refused `effect_not_permitted`).
- [ ] D4: `:max` takes a `match` or `cond` by the route E1 gives other operands, or is refused with
      `loop_recur_contract_invalid`. Tests for a loop and for a serial map's `:max`.
- Identity: invariants identical. Reviewer: `:on-exhausted` and `:state` with the same shapes.

### Task TD3: Binder scope in type re-inference (D7, D8) (10 h; after E1)

- [ ] Find the cause first (four hours at most): both crashes are a `KeyError` on a binder name in
      `wcc/elaborate.py:_infer_expr_type`, reached while an expression that holds the binder is
      typed again outside it. If one fix serves both, make it; if not, fix D7 here and report D8's
      cause to Task 0b.
- [ ] Tests: D7 in place and through a macro gives the value of the `let*` spelling; D8 builds and
      runs to the value the `let*` spelling gives.
- Identity: invariants identical. Reviewer: the same shapes inside a `let-proc` local and a
  specialized procedure; a `cond` test and an `and` operand in D8's position.

### Task TD5: A `let-proc` local whose body is a loop with state (D9) (4 h)

- [ ] `loop_state.py:_typecheck_loop_state_seed` finds the declaration family for a seed inside a
      local, or the local is typed where the family is retained. Tests: by name, by reference,
      both loop forms, and a serial map inside a local (it lowers to the same seed).
- Identity: invariants identical. Reviewer: two locals with loops in one `let-proc`.

### Task TD6: A `let-proc` local that captures a procedure reference (D10, D11, D17) (8 h)

- [ ] Re-run D17 first and record it. Then: a captured outer reference is a compile-time binding of
      the local, not a command capture (`closed/command_templates.py:bind`) and not a provider
      input (`workflow/evaluated/provider_io.py:bind`). If the two crashes have two causes, fix
      D10 and return D11 with its cause.
- [ ] Tests: D10 gives 2; D11 runs two commands; the alias spelling gives the same digest as the
      by-name spelling.
- Identity: invariants identical. Reviewer: a captured `bind-proc` value; capture across two
  nested locals; run references behind the captured reference (TA3's rule must still hold).

### Task TD4: Proof names under the hygiene rename (D6) (6 h)

- [ ] `wcc/hygiene.py`: rename the proof triples when the binding is renamed, **and** key the
      narrowed reads by the field-access atom, not by the shared base atom. The variant-fix
      re-review tried the first half alone: its program `join_rebound_effect2` changed digest and
      returned `[5, 5, 0]` for `[10, 0, 0]`.
- [ ] Tests: D6 in both operand orders and nested in a proven branch; the re-review's
      `hyg_sibling_plain`; a renamed binding used as a whole value in the narrowed branch.
- Identity: invariants identical, and the digests of the variant-fix tests' programs unchanged.
- Reviewer: a wrong value is worse than this crash; if the second half cannot be made safe, turn
  the crash into a coded refusal and stop.

### Task TD8: The `Int` literal range (D13) (2 h)

- [ ] The typechecker refuses an `Int` literal outside signed 64 bits with `pure_expr_overflow`.
      The frontend specification gets the sentence (no owner states the range today).
- Reviewer: the negative bound; a literal in a `defun` default and in a workflow input default.

### Task TD7: A workflow-reference parameter of a workflow (D12) (5 h; after E1)

- [ ] Refuse at the use, where it crashes today: selecting such a workflow as the entry, and a
      `call` that binds the parameter. One code. A workflow that declares the parameter and is
      never called keeps building (refusing the declaration would refuse source that compiles).
- [ ] The frontend specification's section 108 says such parameters are supported; correct it. The
      fixture `tests/fixtures/workflow_lisp/valid/workflow_refs_same_file.orc` has the crashing
      shape; see what reads it.
- Identity: invariants identical. Reviewer: the `defproc` form, which works, is untouched.

### Task TE1: Variant proofs survive desugaring (E1, E2, E3) (10 h; after E1)

- [ ] `conditionals.py:_normalize_short_circuit`: the facts `analyze_condition` grants travel with
      the generated binding, so the final `if` is checked with them. The test that pins the
      refusal today, `test_compound_boolean_proof_is_refused_by_the_typechecker`
      (`tests/test_workflow_lisp_strict_boolean_control_flow.py`), is replaced by the new one.
- [ ] A serial `list/map-effect` body is checked with the proofs of its enclosing branch, as the
      parallel body and the pure map body are; an authored `loop/recur` body is not (its state can
      rebind the name between rounds).
- [ ] The message no longer names "map"; `specs/versioning.md` v2.26 and specification §12.2 are
      corrected.
- Identity: invariants identical (both programs are refused today). Reviewer: a proof must not
  survive a rebinding inside the map body or an `or` whose other operand leaves the variant open;
  the effect order of the hoisted condition is unchanged.

### Task TE2: A reference parameter forwarded through `let*` (E6, E23) (5 h; after E1)

- [ ] `(let* ((g p)) (g x))` over a `ProcRef` parameter builds in the specialized procedure, as the
      uncalled procedure already does. Re-run E23 first; fix it here only if the cause is the same.
- Identity: invariants identical. Reviewer: the forward must not reopen B2 (a non-reference
  binding of the same name).

### Task TE3: A pure loop procedure through a reference (E9) (6 h)

- [ ] Find the cause (three hours at most), then make the program build, or refuse it with a code
      that names the loop. Tests: the four spellings of the reproduction row.
- Reviewer: whether the pure-call path inlines what it cannot inline, and what else it meets (a
  pure `match`, a pure map).

### Task TE4: The code of a discriminant test on a type parameter (E4) (2 h)

- [ ] Its own code; the specification's §12.2 already states the limit. Lowest priority.

### Task TE5: Delete the dead prompt identity code and the other remnants (E17) (10 h)

- [ ] Remove what the row lists, keeping `_attempt` and `_validate_attempt` (moved beside their one
      caller) and the tests of live behavior. About 3,500 production lines. Extend the removal test
      (`tests/test_retired_executors_removed.py`) with the module names.
- Identity: all three invariants; the fragment-identity projection is computed onto the typed
  prompt application and must be shown to reach no stored field.
- Reviewer: every deleted test names the code it covered; nothing under
  `provider_phased_delivery/` changes behavior.

### Task TP2: The placement grid, generalised (8 h; after E1)

- [ ] Extend `tests/test_workflow_lisp_effect_placement_grid.py` (E1) from "places E1 opens by
      shapes of effect" to every operand position by every control shape, pure and effectful. New
      positions: `:max`, `:state`, `:on-exhausted`, a loop or `if` condition, a `continue` and
      `done` value, a map source and body, a `let-proc` local's body, a procedure specialized by a
      reference, a macro template. New shapes: a pure `match`, a pure `cond`, a nested loop, a
      map with a `match` body, a discriminant read. A cell runs with the right value and log, or is
      refused with a code; a crash or a traceback fails it. Cells that fail today carry a backlog
      id in a list that may only shrink.
- [ ] The default suite runs a seeded sample of cells; the whole grid runs under a marker.
- Reviewer: that a refused cell names a code this plan or the specification accepts as intended.

### Task TF: Closeout (3 h)

- [ ] The roadmap's paragraph is replaced by a pointer to this plan; `docs/index.md` gets the row;
      the specification's change lists get one line per admitted or refused shape; the ledger
      states for each row: fixed (commit), moved to the cut, or left, with `KNOWN`'s final content.

## Prevention

| What would have caught these | As a task or pointer |
| --- | --- |
| Positions crossed with shapes. D1 to D8 are one table with holes; E1's grid found eleven of them in review instead of in use | TP2 |
| A fuzz of mechanical mutants | Roadmap Phase 6, readiness item R3. Until it exists, T0's module is the fixed corpus. See below for how R3 orders this backlog |
| The whole suite before each merge. The coordinator's brief records that it caught one real bug two reviews missed | Already a rule (`AGENTS.md`); no task. The sampled run is not a substitute, and a batch of branches gets one run on an integration branch |
| A crash that is not reported as one | TP1 |
| A default that reads "missing" as "none" | TC1 removes this one. Its reviewer greps for other `.get(…, EMPTY_EFFECT_SUMMARY)` and `or {}` defaults on analysis results and lists them in the ledger |
| A check that only its tests call | TA2. TE5's reviewer lists every public function of `contracts/` with no caller in `orchestrator/` |

**How R3's generator orders this backlog.** Each mutant that ends in `compiler_defect` or a
traceback gives a signature: the exception class and the innermost `orchestrator/` function. The
Reproductions table gives the signature of every D row. R3's readout is a count per signature; the
D and E tasks not yet started are re-ordered by that count, a signature with no row becomes a new
row, and a row no mutant hits in a few hundred mutants over the declared dimensions drops below
every row that is hit. Classes A and C are not re-ordered by it: a mutant that spends wrongly does
not crash.

## Size

| Task | Hours | Class | Starts |
| --- | ---: | --- | --- |
| T0 Reproductions and invariants | 5 | — | Now |
| TA2 Output slots before launch | 5 | A, B | After `fix/missing-prompt-file` |
| TA3 P12 through references | 8 | A | Now; merge needs O1 |
| TC1 Imported summaries | 10 | C | Now; merge needs O1 |
| TP1 Typecheck in the boundary | 2 | Prevention | After T0 |
| TD2 Subject read in an arm | 6 | D | After E1 |
| TD1 Control forms as operands | 5 | D | After E1 |
| TD3 Binder scope | 10 | D | After E1 |
| TD5 Local with a loop | 4 | D | Now |
| TD6 Local capturing a reference | 8 | D | Now |
| TD4 Proof names under rename | 6 | D | Now |
| TD8 `Int` literal | 2 | D | Now |
| TD7 Workflow-reference parameter | 5 | D | After E1 |
| TE1 Proofs through desugaring | 10 | E | After E1 |
| TE2 Forwarded reference | 5 | E | After E1 |
| TE3 Pure loop through a reference | 6 | E | Now |
| TE4 Generic test code | 2 | E | Any time |
| TE5 Dead code | 10 | E | After `fix/missing-prompt-file` |
| TP2 Grid | 8 | Prevention | After E1 |
| TF Closeout | 3 | — | Last |
| **Total** | **120** | | 20 tasks, 19 code changes |

The 120 hours are implementation and its own tests. At this repository's pace each code change
also gets an independent review and one or two fix rounds (C1, I2a and I1 each took two or three
rounds and merged one to two days after they started), which adds about three quarters: about 210
agent-hours. With three or four worktrees in parallel that is **two and a half to three weeks**
elapsed, set by lane 4 (26 hours on one file and 8 for the grid, after E1) and by one
whole-suite run per merge or batch. Classes A and C fit in the first three or four days. Three tasks open with a search for the
cause (TD3, TD6, TE3) and may return a refusal instead of a fix. The cut's nine changes and Task
0b's ten hours are not in the total.

## Not Worth Fixing

| Row | Why |
| --- | --- |
| B6 `Bool` strings | A provider that writes `"true"` means true; refusing it fails runs for no gain. Specification §8.10 states the behavior |
| E5 `cond`, `if`, `match` as binding names | Harmless (the form still works) and reserving them refuses source that compiles |
| E10 free names in a template | Specification §34 states call-site resolution; definition-site resolution is a language change, not a fix |
| E14 `TimestampNs` | The documentation was the defect, and it is corrected |
| E15 extern path at compile | The run fails before launch at no cost; a compile check would have to know which `input_file` a run creates. Add a row to the cut only if an author is bitten |
| E18 `list/map` in a template | Not a defect |
| D12, as an implementation | A workflow-reference parameter on a `defproc` works; build the `defworkflow` form when a workflow needs it. Refuse at the use (TD7) |
| E4 | Worth two hours only because the code names the wrong thing; drop it first if time is short |

Deleting is the fix for E17, and for `validate_prompt_output_position_destinations` if TA2 does not
use it.

## What This Makes Harder

- **Programs that build today stop building** under TA3 (a confined site behind a reference in a
  map body) and TC1 (a ceiling that does not list what an imported workflow does). A run recorded
  from such a program cannot be rebuilt for `resume`.
- **A provider call that commits today fails before launch** under TA2 when two slots share a
  destination.
- **A second place to edit.** Each fix removes a `KNOWN` row and adds its behavior test; a fix that
  forgets the row fails the backlog module.
- **Suite time.** The backlog module and the grid are command-line runs; both must be sampled in
  the default suite.
- **Typecheck failures change exit code** from 1 to 2 (TP1); a script that tells a crash from a
  refusal by exit code no longer can, and must read the code.
- **Rebuilding a prompt-snapshot or prompt-identity feature** starts from the archive tag after
  TE5, not from the checkout.
- **Admitting compound proofs (TE1)** widens what a mutant can write and what R3 must cover.
- **Lane 4 is serial.** Every elaboration fix edits `wcc/elaborate.py`; the staged-authoring tasks
  O and 0b do too.

## Not Verified While Planning

- No fix was written except the four-line scratch patch for C1. With it the compile of every
  tracked `.orc` is byte-identical to the base (635 files, 34 build, 601 refuse; SHA-256
  `de1dcb27…065d52` on both sides), run without generated provider externs, so the sources that
  name a provider did not reach the build. The corpus snapshot and the run-reference digests were
  not run for it, and no test was run on the patched tree.
- The causes of D7 and D8 (assumed one), of D10 and D11 (assumed related), and of E9.
- D14 was not reproduced; the exact program of the staged-authoring design was not found in
  scratch or on the spike branch.
- D17, D18, E21, E22 and E23 were not re-run.
- How a confined site is marked in the closed tree, and that TA3's scan can tell an iteration body
  from its surroundings there.
- The live-provider rows of TC1's audit are from reading the code; no live-provider program was
  compiled.
- That E1 closes D1 to D3 on `main`: probed on the branch tip `94236abf`, which is 49 commits
  behind `main` and lacks the binder form, with fn-form programs for D2 and D3.
- That no tracked source or test depends on A2's, B1's or C1's present behavior: no search was run
  beyond the I1 reviews' note that the P12 gap is not pinned.
- That the kit on `spike/authoring-revisions` runs unchanged on `main`.
- The hours. They are read from the size of the crash sites and of the reviews' prototypes, not
  from a trial.
- The bug the whole suite caught and two reviews missed: taken from the coordinator's brief; its
  ledger entry was not located.
- The whole suite and the sampled suite were not run; this change is one document.

## Rulings

Planner's rulings, with the cost if wrong:

| # | Ruling | Reason | Cost if wrong |
| --- | --- | --- | --- |
| 1 | A row's class is the worst thing the program does today, not the size of its fix | The order is by harm | A cheap E fix waits behind a dear D one |
| 2 | A3 is class A: a provider call whose result is certain to be refused is money spent | The name clash is static | It moves one place down |
| 3 | A refusal at run time before launch is not a change to what source means | It moves no digest and no compile outcome; A1's fix sets the precedent | TA2 goes to the cut's list |
| 4 | One fix per cause; K6 is split in two because the obvious fix of D6 returns a wrong value | The variant-fix re-review measured it | TD4 folds into TE1 |
| 5 | The reproductions live in one test module with a list that may only shrink | Scratch files do not survive; the one-target guard test uses the same device | A fix forgets the row and the module fails: cheap |
| 6 | TD3 owns the cause of D8; Task 0b keeps its test | One owner per cause | Whichever lands second pins only |
| 7 | D12 is refused at its use, not built | No workflow needs it; the `defproc` form works | Five hours spent on a refusal that a later implementation removes |
| 8 | The cut's rows are listed and not re-planned, though four of them are class B | The versioning rule; two patches inside the hygiene pass were withdrawn | Silent wrong callees stay until the cut |

## Open Decisions For The Coordinator

| # | Decision | Planner's recommendation |
| --- | --- | --- |
| O1 | TA3, TC1 and B1 (in TA2) each make something that builds or commits today stop. Versioning rule 2 sends "source that stops compiling" to the cut | Merge at once. Each enforces a rule the specification already states (ruling P12; the `:effects` ceiling; one destination per output), through a hole in the checker; no tracked source changes; each gets an entry in the specification's change list and a row in the cut's table marked "taken early". If rule 2 is applied strictly, the three ride Task 4b and their tests stay as `KNOWN` rows until then |
| O2 | Add rows to the cut's table: a compile-time refusal of an output slot named like a result field (A3's static half); the `asset_file` check at compile (E15); reserving `cond`, `if`, `match` as binder names (E5) | The first: yes. The other two: no |
| O3 | Whether TE5's deletion runs under this plan or with the stage 4 leftovers | Here: it removes the uncalled check that K1 is about |
| O4 | E9 goes on the roadmap's list | Yes |
| O5 | Task 0b's D2 (D14 here) does not reproduce as a crash | Task 0b re-runs its own program before spending on it |

## Ledger

| Date | Entry |
| --- | --- |
| 2026-11-13 | Plan written as proposed, against `main` at `59f727db`; `main` at `801bd6d2` merged into the branch afterwards (three documents changed, no code, so the probes stand). 51 rows; 46 re-run on that commit through the public command line with stand-in commands and a stand-in `codex` on a closed `PATH`; no provider or model call. First pass on `a58e5b17`; I1 merged meanwhile (`624ff688`) and closed D15, the only row whose result changed. Found while planning: E9 (a pure loop procedure through a reference); C1 shown on `main` through the declared ceiling, with its cause confirmed by a four-line scratch patch that leaves the compile of all 635 tracked `.orc` files byte-identical; D14 not reproduced; D1 closed by the E1 branch, D4 not. No code change, no spend |
