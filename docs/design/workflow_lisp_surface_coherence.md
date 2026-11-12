# Workflow Lisp Surface Coherence: Effects, Iteration, Callables

- **Status:** Accepted 2026-11-12 as the basis for implementation, after an
  independent review (accept with changes; all applied). Not implemented: the
  compiler behaves as the "Today" columns of §2 until the changes of §10
  exist, and the "after" examples do not compile.
- **Owns, until retired (§11):** where an effect may be written; the shape of
  the iteration forms; how each kind of callable is called.
- **Consumes:** [evaluated execution](workflow_lisp_evaluated_execution.md)
  §4.3, §6 and P5; the [closures boundary](workflow_lisp_runtime_closures_boundary.md);
  the versioning rule of the [one-target plan](../plans/2026-11-12-lane-d-stage-4-one-target-plan.md).
- **Prerequisites (§12):** one admitted target with the refused forms deleted;
  the constructor-field capture defect fixed; a reading of the versioning rule.
- **Spec impact (§11):** three sentences of `specs/dsl.md` and one of
  `specs/versioning.md` change; the latter gains an entry per change. The
  closed-program format, the memo and the CLI do not change.

## 1. The Three Rules

An assessment found three edges of the language incoherent; each claim was
reproduced through the public command line before anything was decided (§2).
Most refusals protect nothing: they are rules of the retired flat lowering
route, where a value existed only as a step's output. Each rule below is one
sentence; everything it does not cover is listed under it.

**1. Effects.** An effect may be written wherever a value is expected in a
workflow or procedure body; effects run in the order written, each once, and
`if`, `cond`, `match`, `and` and `or` run only the branch they take.

- *Pure places take no effect:* a `defun` body, a `list/map` body, a parallel
  `:workspace`.
- *A run reference keeps its own placement contract:* not in `:on-exhausted`,
  not in a map source, alone as a map body, with a pure `:commit`.
- *A pure operator waits for its value:* it is computed when the value around
  it is built, after the effects of its sibling operands, and `print` is one.
  `(+ (print 1) (fetch) (print 3))` fetches, then prints `1` and `3`; a `let*`
  binding prints in order.

**2. Iteration.** Every iteration form is `(form ((name source)) option… body)`:
the binder names the loop state or the current item, the source and then
`:max` are evaluated once before the first round, and the body is any
expression, pure in `list/map` and ending every path in `done` or `continue`
in `loop/recur`.

- *The other options are not evaluated before the first round:*
  `:on-exhausted` only when `:max` rounds pass without `done`, with the last
  state bound, wherever it is written; `:workspace` for each item, and pure.
- *A parallel map takes literals:* its `:max` and `:parallel` are positive
  integer literals, stored as integers in the checked program and validated
  before a run; no program needs a computed one.
- *A list longer than `:max`:* a serial map runs its first `:max` items and
  then fails with `list_map_effect_cap_exceeded`; a parallel map fails with
  that code before any item. A serial map is a loop whose budget is `:max`;
  failing earlier would stop a run recorded past that point from resuming.
- *A map body that holds a run reference is exactly one call.*
- *A parallel map* runs items concurrently, so order holds within an item
  only; its body admits no `Agent` crossing the item boundary, no phased
  provider, no host input and no confined run reference.
- *The `fn` form,* `(loop/recur :max n :state init (fn (state) body))`, builds
  the same program and is accepted until the release that removes the older
  targets; its two operands run in the order written.

**3. Callables.** A function, a procedure, a local procedure and a procedure
parameter are called by name with positional arguments; a workflow, which can
also be run from the command line, is called as the command line calls it,
`(call w :input value)`; a procedure reference is a compile-time name, so it
can be passed and bound but not stored, chosen at run time or returned.

- *Locals do not see each other:* a `let-proc` local is called from the
  `let-proc` body, not from another local or itself; `let-proc` does not nest.
- *A local called by name declares its signature;* one without can only be
  passed, once, to a consumer whose parameter type supplies it.
- *A `defun`* takes no procedure parameter and is not a `proc-ref` target.
- *No recursion:* no function, procedure or workflow may reach itself.
- *A workflow reference parameter* is called like a workflow, `(call w :x v)`.
- *A macro is not a callable:* its use is expanded before any call exists and
  has the shape its definition gives it (not assessed here).
- *Defect, not a rule (§12):* a `bind-proc` over a pure procedure cannot carry
  a computed value into another procedure.

No program that compiles today changes its closed program, program digest,
effect identities or behavior (§8).

## 2. Verified Findings

294 programs at target 2.40, compiled and, where the claim is about running,
run with stand-in commands that log their calls, on `main` and on the
prototype (§8). Class: **(a)** needed for a stated guarantee, **(b)**
unimplemented case, **(c)** historical accident, named as such by its owning
design: pure fields and a pure `:on-exhausted` are "rules" of the flat 2.33
route ([composition first](workflow_lisp_composition_first.md) §11.1), the
one-call map body and literal `:max` the "first tranche" of 2.18
([list traversal](workflow_lisp_pure_list_traversal.md)), a local called by
name "deferred" ([let-proc](workflow_lisp_let_proc_local_proc_refs.md) §7.3).
`tsv` is `typecheck_structural_values.py`; paths are under
`orchestrator/workflow_lisp/`, or `orchestrator/` if they start with
`workflow/` or `contracts/`.

### 2.1 Effect placement

The assessment's nine placements all reproduced. It under-counted both ways:
eight more positions refuse an effect (three for a stated guarantee), eleven
more accept one, and three defects surfaced.

| Position | Today | Decided in | Class |
| --- | --- | --- | --- |
| Procedure, function and workflow call argument; operator operand, nested too; `if` and `cond` condition; `and`/`or`/`not`; `match` subject and arm; `list/append` and `record-update` operand; `let*` binding; `done` and `continue` value; loop `:state` and `:max`; command `:argv`; a `bind-proc` value over an effectful procedure | Accepted; calls logged in written order, short-circuit kept | `wcc/elaborate.py:_elaborate_operands_to_values`, `conditionals.py:normalize_condition_expr` | — |
| Record field, variant field | `effect_not_permitted` | `typecheck_dispatch.py:_typecheck` | (c): the lowering of both already goes through `_elaborate_operands_to_values` |
| List element | `effect_not_permitted` | `tsv:typecheck_structural_value_expr` | (b): items are lowered as effect-free blocks |
| `:on-exhausted` value, a pure `defproc` call included | `loop_recur_contract_invalid` | `typecheck_loop_recur.py:typecheck_loop_recur_expr` | (c): the closed loop holds an exhaustion *body*, and evaluated execution §6 already names its path `loop:<label> / exhausted` |
| `list/map-effect` source and call arguments | `list_map_effect_body_unsupported` | `tsv` | (c) |
| `list/map` source; `path/join-under` child | `list_map_body_effect_forbidden`; `effect_not_permitted` | `tsv` | (b) |
| `list/map` body | `list_map_body_effect_forbidden` | `tsv` | (a) effect identity: a pure map is one value with no per-item frame |
| `defun` body | `pure_function_has_effect` | `functions.py` | (a) declared purity, relied on by pure contexts |
| Parallel `:workspace` | `list_map_effect_workspace_invalid` | `parallel_map.py:typecheck_parallel_workspace` | (a) resume determinism: evaluated again for every item on replay |
| Defect: a pure `match` as the operand of a pure operator, `(+ 1 (match …))` | `compiler_defect` ("expected linear WCC value body, found `WccCase`"); the same `match` is accepted as a procedure argument, a list item or beside an effectful sibling | `wcc/elaborate.py:_elaborate_operands_to_values` | (b) |
| Defect: a constructor with a `match` field, when another field holds a `let*` | Wrong value: `(let* ((y 1)) (record Tri :a (let* ((y 7)) y) :b y :c (match …)))` gives `b = 7` | `wcc/elaborate.py:_elaborate_constructor_field_matches_to_body` | Fixed separately; E1 requires the fix (§12) |
| Defect: a `bind-proc` over a pure procedure with a computed bound value, passed to a procedure | `name_unknown` for a pure value, `procedure_call_unknown` for an effectful one; accepted when called in place | Specialization of the pure target | Not about effects (§12) |

Not probed (probes use commands only): a provider's `:inputs`, which share
`wcc/elaborate.py:_prebind_effect_argument_matches` with command operands.

### 2.2 Iteration

| Claim | Today | Decided in | Class |
| --- | --- | --- | --- |
| `fn` is valid only as the loop body, with one parameter | Reproduced: `loop_recur_fn_outside_loop`, `loop_recur_fn_invalid` | `expressions.py:_elaborate_loop_body_fn`, `_guard_loop_fn_route` | (c) |
| `:on-exhausted` reads the name the later `fn` introduces | Reproduced, in either keyword order; `:state` cannot | `expressions.py:_elaborate_loop_recur` | (c) |
| A loop body is any expression | Reproduced, with one condition: every path ends in `done` or `continue` (`loop_recur_missing_done`) | `typecheck_loop_recur.py` | (a) bounded execution |
| A `list/map-effect` body must be exactly one call | Reproduced, and stricter: an inlined procedure body must hold exactly one effect | `tsv:_check_map_effect_body`; `closed/build.py:_check_loop_effect_cardinality` | (c). Not an invariant: a workflow-call body runs two effects per item, a procedure holding a nested loop or map passes, and a parallel map accepts a procedure with `let*`, `if` and two effects |
| `:max` takes a variable in `loop/recur`, a literal in `list/map-effect` | Reproduced; a loop takes even an effect there; `:parallel` is literal too | `expressions.py:_elaborate_list_map_effect`; `parallel_map.py:_positive_literal` | (c) serial: a loop budget is a value (`workflow/evaluated/machine.py:_loop`). Parallel: the `par-map` node holds integers, checked by `contracts/closed_program/check.py:_parallel_map_body` and read at run time |
| (New) A serial map over a list longer than `:max` | Runs `:max` items, then fails `list_map_effect_cap_exceeded`; a parallel map fails before any item | `machine.py:_loop`, `_parallel_source` | Kept: rule 2, the long-list exception |
| (New) Ruling P12: no confined run-reference site in a map body | Kept | `typecheck_run_ref.py:_refuse_confined_site_in_map_frame` walks the body and every callee it reaches, whatever the body's shape | (a) |

### 2.3 Callables

| Claim | Today | Decided in | Class |
| --- | --- | --- | --- |
| `defun` and `defproc` are called positionally | Reproduced. A keyword there crashes: Python traceback, exit 1 | `expressions.py:_elaborate` | Defect |
| `defworkflow` only through `(call w :x n)` | Reproduced: `(w n)` gives `procedure_call_unknown`, `(call p :x n)` on a procedure gives `workflow_call_unknown`; neither message names the other convention | `expressions.py:_elaborate_list`; `typecheck_calls.py` | By design: workflow inputs are named, may be omitted when defaulted, and are the names `--input` uses |
| A `let-proc` local cannot be called by name | Reproduced (`let_proc_bare_name_invalid`), yet `(let* ((g (proc-ref f))) (g 1))` compiles when `f` has a signature | `expressions.py:_elaborate_list` | (b) |
| (New) A local calling another local, or a nested `let-proc` | Refused: `let_proc_bare_name_invalid`, `let_proc_nested_unsupported` | [Write once](workflow_lisp_write_once.md) §6.3: "do not permit sibling calls" | By design |
| Procedure references cannot be stored or returned | Partly wrong: a reference can be bound by `let*`, forwarded and called. Refused in a record, a list, a workflow input or result, as a procedure's result, or as the value of an `if` | `type_env.py`, `workflows.py`, `typecheck_calls.py` | (a) no runtime closures |
| Recursion is refused | Reproduced (`proc_lowering_cycle`, `function_cycle`); a workflow that calls itself is refused as `compiler_defect` (`RecursionError`) | `closed/build.py` | (a) bounded execution; the workflow diagnostic is a defect |

## 3. Decision

Adopt the three rules and make these changes, ranked by value over cost. Sizes
are measured on the prototype or estimated from it (2026-11-12).

| # | Change | Requires | Compiler | Tests |
| --- | --- | --- | --- | --- |
| E1 | Admit effects in record fields, variant fields, list elements, `:on-exhausted` and a map's source; then `list/map` source and `path/join-under` child. A pure `match` is a value as an operand | The capture fix; the refused forms deleted (§12) | 5 files, about +95 −70 | 6 refusal test functions flip (13 cases); 38 matrix cells move from refused to admitted |
| I1 | A `list/map-effect` body is any expression, one call if it holds a run reference; a serial `:max` is any `Int` expression; a serial map evaluates its source, then `:max` | — | 5 files, about +45 −15 | 2 refusal test functions flip (6 cases) |
| C1 | A `let-proc` local with a signature is called by name; five diagnostics name the cause (§6); a recursive workflow gets a cycle diagnostic | — | 5 files, about +55 −10 | 1 flips; 6 new |
| I2 | `loop/recur` takes the map forms' binder. I2a: accepted beside the `fn` form, building the same program. I2b: `fn` and `:state` are refused | I2b: the release that removes the older targets, and the rewrite (§5) | I2a 2 files, about +50; I2b about −230 | 15 source files (15 loops), 154 test files (277 loops), 22 documents (27) rewritten by the migration script |

Not done at all: the rows of §7. Rejected: *documenting the refusals instead*
(eleven positions, and `(record R :a (command-result …))`, the first thing a
newcomer writes, still fails); *desugaring at typecheck into generated `let*`*
(needs fresh names and labels the lowering already has); *keeping both loop
syntaxes for good*.

Review minors: all six are applied, two with a correction. Minor 2: the six
tests it lists as outside the measured files were inside them and are among
the 20 of §8; its substance, that four fixtures change their refusal, is item
2 of §12. Minor 3: the changes and prerequisites are not moved to a plan,
because none exists yet to carry them; they stay here dated and unscheduled.

## 4. Effects

**Evaluation order.** (1) Effects run in the order their expressions are
written: fields in the order written, not declared; `call` arguments in the
order written; a `record-update` base before its fields; an inner effect
before the effect it is an operand of. (2) `if`, `cond` and `match` evaluate
the condition or subject, then the selected branch; `and` and `or` stop at the
first operand that decides. (3) All effects of one operand finish before the
next operand's start; the enclosing form is applied last. (4) Each effect runs
once per evaluation of its body: once per loop round or map item.

**Identity.** An effect without an authored binding name takes `#k`, its
ordinal among the unnamed effects of its scope (evaluated execution §6, I4);
§4.3 there already binds an effectful argument "by a `let` before the call, in
source order" and adds no aggregate position to an identity. This design
applies that to the refused positions and adds no identity rule: `#k` in
evaluation order, `#k / body / then|else|<variant> / …` inside a selected
branch, `loop:<label> / exhausted / …` in `:on-exhausted`. Only a `let*` in
statement position keeps its name: `(let* ((z E)) (+ z 1))` names the step
`z`, `(+ (let* ((z E)) z) 1)` names it `#1`; bind there the step someone will
`invalidate` by name. A field's effect must be named the same whether or not a
sibling field is a `match` (§12, item 1).

**Becomes legal** (nothing becomes refused; the `let*` spelling stays legal):

```lisp
;; today: effect_not_permitted
(record Outcome
  :words (command-result count :argv ("python" "count.py" file) :returns Int)
  :pads 0)
(list (fetch "a") (fetch "b"))
(loop/recur ((s 0)) :max 3 :on-exhausted (give-up s) (step s))
;; today: compiler_defect
(+ 1 (match shape ((CIRCLE c) c.r) ((SQUARE s) 0)))
```

## 5. Iteration

```lisp
(loop/recur ((state init)) :max n [:on-exhausted e] body)   ; every path: done / continue
(list/map ((x xs)) body)                                    ; pure body, no options
(list/map-effect ((x xs)) :max n body)
(list/map-effect ((x xs)) :max n :parallel k :workspace dir body)
```

**Order, exactly.** For a loop and for a serial map: (1) the effects of the
binder's source, the initial state or the list; (2) the effects of `:max`;
(3) the remaining pure parts, `:max`'s before the source's as today, which
shows only in which of two failing pure expressions is reported; (4) the
rounds. Neither the source nor `:max` sees the binder. `:on-exhausted` is
evaluated only when `:max` rounds pass without `done`, with the last state
bound; where it is written among the options changes nothing. `:workspace` is
evaluated per item and is pure. A `:max` below 1 gives a loop no round, and a
serial map then fails with `list_map_effect_cap_exceeded`; a literal below 1
on a map stays a compile error. Existing programs are unaffected: a serial
map's `:max` is a literal today, so running its source first reorders nothing
and digests stay while `:max` is pure; a `:max` with an effect exists only in
new programs, where it follows the source's effects (measured: `ints, 7, 1, 2,
3`); a `fn`-form loop keeps its keyword order while that form compiles.

**Becomes legal:**

```lisp
;; today: list_map_effect_body_unsupported and list_map_effect_max_invalid
(list/map-effect ((repo repos)) :max limit
  (let* ((checked (check repo)))
    (if checked.passed checked (fix repo checked))))
;; today: (loop/recur :max 5 :state 0 :on-exhausted (give-up pads) (fn (pads) …))
(loop/recur ((pads 0)) :max 5 :on-exhausted (give-up pads)
  (if (enough? pads) (done pads) (continue (pad pads))))
```

**What the body restriction protected.** Nothing, for provider, command and
call bodies: item identity comes from the frame (`loop:#k[i]`,
`par-map:<binder>[i]`), the item workspace applies to every direct effect, and
P12 and the parallel `Agent` boundary walk the whole body and its callees. One
dependency is real, hence rule 2's run-reference exception: for a body with a
run reference, `closed/build.py:_bind_map_run_ref_result` binds the map's
result to a single producer, and evaluated execution §1.2 admits only "the
one-effect body".

**The binder form of `loop/recur`: contract.** Both forms build the same
program. The `fn` form is removed in the release that removes the older
targets, the one release that already refuses existing source. A run started
under the `fn` form resumes from the rewritten source; `resume` compiles
source, so after that release it does not resume from unrewritten source.
Evidence: 17 loop programs here, and in the review the 27 tracked programs
with loops and the four packaged library modules with their importers, keep
digest and site list when rewritten; a run of the tutorial's `grow.orc`,
stopped at a failed step under the `fn` form, resumed from the rewritten
source and reused its committed step.

**The rewrite.** One case changes order: a `fn` loop written `:max E1 :state
E2` with an effect in both runs `E1` first, and the binder form runs `E2`
first. No loop outside `tests/` has a non-atomic `:max` (15 loops, read with
the compiler's reader); 15 loops in 6 test files do. The migration script
therefore compares the program hash before and after each loop it rewrites.
Equal, as for every loop with a pure `:max`: done. Different: it leaves that
loop in the `fn` form and lists it. A listed test whose subject is the keyword
order goes with the `fn` form and `operand_evaluation_order`. Any other is
rewritten by hand with the budget bound first, `(let* ((budget E1))
(loop/recur ((s E2)) :max budget …))`: the effects keep their order and the
two steps `#1`, `#2` become `budget`, `#1`, an expected structure change.

## 6. Callables

```lisp
;; today: let_proc_bare_name_invalid
(let-proc ((bump ((x Int)) -> Int (+ x step)))
  (+ (bump 1) (bump 2)))
```

The call is positional, as rule 3 requires. It reverses the syntax the
let-proc design deferred, `(call run-impl :selected selected)` (§27.2 there),
and stays compile-time: it is the alias form `(let* ((g (proc-ref f))) (g a))`
that compiles today.

| Source | Diagnostic |
| --- | --- |
| A local without a signature, called by name | "give `f` a signature to call it by name" |
| A local called from another local | "the locals of one `let-proc` do not see each other; define `f` with `defproc`" |
| `(w n)` on a workflow | "`w` is a workflow; call it as `(call w :x …)`" |
| `(call p …)` on a procedure | "`p` is a procedure; call it as `(p …)`" |
| A keyword in a positional call | The same message, instead of a traceback |
| A workflow that reaches itself | A cycle diagnostic, as procedures and functions have |

## 7. What Stays, And Why

| Left alone | Why |
| --- | --- |
| The exceptions listed under the rules, among them literal parallel options and the serial map's cap timing | The pure places are class (a), §2.1; run references are owned by evaluated execution §1.2 and were not assessed; the others carry their reason in §1 |
| When a pure operator is computed | Hoisting `print` before a later sibling's effect changes the closed program of every program that mixes them; `let*` already gives the order |
| `list/map` beside `list/map-effect` | The pure one is a value, usable in a `defun`, with no bound and no identity |
| A serial map's step names, `loop:#k[i] / else / …` (one-based; `par-map` is zero-based) | They expose the lowering, but renaming them moves every serial map's identities in every recorded run |
| Two calling conventions | A workflow's inputs are a public contract: named, with defaults a caller may omit, the names `--input` uses and a compiled import is addressed by. A positional workflow call or a keyword procedure call adds a second way to call something and removes nothing |
| `defun` beside `defproc` | A `defun` declares a callable pure, checked and expanded inline. Folding it into `defproc` turns expansions into call nodes and moves the digest of every program that uses one |
| Stored, selected or returned procedure references | A runtime callable value; the closures boundary (§4, §5) forbids adding one as a small feature, and no consumer needs it. Not reopened |

## 8. Feasibility, Compatibility And Identity

The prototype is the branch `spike/surface-coherence`, with the probe
programs, their harness and results under `experiments/surface_coherence/`. It
is evidence, not the implementation: no tests, no capture fix.

| Change | Existing path it relies on | Prototype result |
| --- | --- | --- |
| Effects in record and variant fields | Their lowering already calls `_elaborate_operands_to_values`, the function behind operator operands | Two checks deleted; fields run in written order, short-circuit intact. With a `match` in a sibling field the capture defect of §2.1 applies until fixed |
| Effects in list elements | The same function, selected by a typechecker-set flag on `ListExpr` (beside `item_type_refs`) so pure lists keep today's lowering | Runs in order; pure lists keep their digest |
| Effectful `:on-exhausted`, map source | The closed loop's exhaustion body; the loop-state seed | Checks deleted; identity `loop:s / exhausted / #1` |
| The three placements across helper kinds | Totality matrix | The 24 field cells and 14 `:on-exhausted` cells that refuse today pass as admitted (native value, ordered command log) for inline, same-module and imported helpers |
| A pure `match` as an operand | The block value a list item already uses | 20 lines in `_elaborate_operands_to_values`; 9 programs that are `compiler_defect` today build, and the 3 that already build keep their digest |
| Map body is any expression | A serial map is a `loop/recur`; a `par-map` body is general | Serial and parallel maps ran `if`, a `let*` of two effects, a record of two effects, a `match`, a nested map, a nested loop and a pure body; the run-reference body tests still refuse |
| Serial `:max` expression, source first | The map passes `:max` to its loop as the budget, and budgets are values; an optional `max_expr` child, as `workspace_expr` is one | 26 lines; a variable, a pure expression, an effect and a procedure parameter all run |
| Binder form | The same `LoopRecurExpr` | 45-line parser; §5 |
| Local called by name; local-to-local diagnostic | The alias form that compiles today | 30 lines; an effectful local called twice ran under `#1=procedure:…f` and `#2=procedure:…f` |
| `list/map` source, `path/join-under` child | The list case | Not prototyped |

| Question | Answer | Evidence |
| --- | --- | --- |
| Does a program that compiles today change its closed program, digest, an effect identity or its behavior? | No | Of the 294 probe programs, 113 compile on `main`: none changes digest on the prototype, 101 more compile, none is newly refused. The closed-program corpus (55 rows, 11 built) has identical digests. All 690 tracked `.orc` files, compiled by the prototype's base and by the prototype: the 42 that build without generated externs keep their digest, and the only other differences are the four fixtures of §12, item 2. The review, generating externs, built 88 on the prototype as reviewed: same digest and site list. Of 1,210 tests in 25 files that pin elaboration, sites, loops, maps, procedures and run-reference placement, 1,189 pass and 1 is an expected failure; the 20 failures are 9 functions asserting a refusal this design removes |
| Kill and failure inside one expression? | As the `let*` spelling | The review killed a run between two field effects, between list elements, between two effects of one map item and in `:on-exhausted`: the first effect is reused and the second runs once on resume; `must_not_repeat` still refuses re-dispatch |
| Is anything legal today refused? | The `fn` form and `:state`, with I2b | §5 |
| Which diagnostics retire? | `effect_not_permitted` for fields, elements and the path child; `list_map_effect_body_unsupported` except for run-reference bodies and malformed clauses; `loop_recur_contract_invalid` for an effectful exhaustion; `let_proc_bare_name_invalid`; with I2b, `loop_recur_fn_invalid` and `loop_recur_fn_outside_loop` | `list_map_effect_max_invalid` remains for a missing or non-`Int` `:max` and a literal below 1 |

## 9. Verification

From the repository root, no provider on `PATH`. In order: placements (native
value and ordered command log); no digest or identity move; loops and maps;
parallel kill and resume; run-reference refusals with P12; the sample.

```bash
pytest -q tests/test_workflow_evaluated_totality.py tests/test_workflow_lisp_totality_matrix.py
pytest -q tests/test_workflow_lisp_closed_program_{corpus,elaboration,sites}.py
pytest -q tests/test_workflow_lisp_loop_recur.py tests/test_workflow_evaluated_loops.py tests/test_workflow_lisp_parallel_map{,_closed}.py
pytest -q tests/test_workflow_evaluated_parallel.py tests/test_workflow_evaluated_parallel_kill_resume.py
pytest -q tests/test_workflow_lisp_closed_run_ref_placement.py tests/test_workflow_lisp_run_ref_workflow_program.py
pytest -q -n 16 --dist=worksteal --sample 10   # the whole suite before merging
```

Scenarios each change adds, through the public CLI with stand-in commands:

| Change | Scenario |
| --- | --- |
| Capture fix, before E1 | `(let* ((y 1)) (record Tri :a (let* ((y 7)) y) :b y :c (match (variant Shape CIRCLE :r n) ((CIRCLE c) c.r) ((SQUARE s) 0))))` returns `b = 1`, also with `:c` written first, and with an effect bound in `:a` once E1 admits it; that effect has the same identity with and without the `match` field |
| E1 | `(record R :b E2 :a E1)` logs `E2` then `E1`; an `and` in a field skips its second effect; the same record in a `defun` or `list/map` body refuses; a run killed between the two field effects resumes with one dispatch; `(+ 1 (match …))` builds; `(+ (print 1) E (print 3))` prints after `E` |
| I1 | A map body of two bound effects, killed after the first effect of item 2, resumes with one dispatch; a body holding a run reference in a `let*` refuses; `:max` from a workflow input runs; with an effect in the source and in `:max`, the source's runs first; a list of 3 under `:max 2` logs two calls and fails, and a run recorded before the change that failed there resumes to the same code |
| I2 | Every rewritten source keeps its recorded digest; a run started before the rewrite resumes after it; a loop with an effect in both `:max` and `:state` is listed, not reordered |
| C1 | A local called twice has two frames; each row of §6's table gets its message |

## 10. Changes And Their Dependencies

No change may add a lowering route, a closed construct or an identity rule, or
move a digest in the corpus comparison of §9.

| Change | Where | Notes |
| --- | --- | --- |
| E1a, after the capture fix | `typecheck_dispatch.py`: delete the two field purity checks. `typecheck_loop_recur.py`: delete the exhaustion purity check, keep the run-reference guard | The three matching rules leave `cell_refusal` (`tests/workflow_evaluated_totality_helpers.py`) and `RULES` (`tests/workflow_lisp_totality_matrix_sources.py`) |
| E1b | `expressions.py` (`ListExpr`, `ListMapExpr`, `PathJoinUnderExpr`): one typechecker-set flag each, outside semantic identity as `item_type_refs` is. `typecheck_structural_values.py`: set it instead of refusing; delete the map-source check. `wcc/elaborate.py:_elaborate_expr_to_value`: when set, lower through `_elaborate_operands_to_values` | Select by the flag, not by `conditionals._contains_effect`, which counts every procedure call and would change the lowering of pure lists |
| E1c | `wcc/elaborate.py:_elaborate_operands_to_values`: an effect-free operand whose body is not linear becomes a block value | Only programs that are `compiler_defect` today change |
| I1 | `typecheck_structural_values.py`: apply `_check_map_effect_body`, the argument-purity check and `single_iteration_effect_kinds` only when the typed body's summary contains a run reference; pass a typed `:max` as the synthetic loop's budget, in the order source then `:max`. `expressions.py` (`ListMapEffectExpr`): an optional `max_expr` child, handled as `workspace_expr` is in `expression_traversal.py`, `procedure_typecheck.py` and `closed/names.py` | Keep the synthetic loop's `list_map_effect_cap_exceeded` code, which P12 reads; report a non-`Int` `:max` as `list_map_effect_max_invalid`. The runtime does not change |
| C1 | `expressions.py` (`_elaborate_list`, `_elaborate`) and `compiler_session.py`: the local call and the second, third and fifth messages of §6. `procedure_typecheck.py`: the first. `typecheck_calls.py`: the fourth. `closed/build.py`: the cycle diagnostic | A local calling itself keeps `let_proc_recursive_unsupported` |
| I2a | `expressions.py`: the binder form beside `fn`. `orchestrator/py/emit.py`: emit it. The one-target plan's migration script gains the loop rewrite of §5, for `.orc` files and for sources inside test strings | One pass then rewrites headers and loops |
| I2b, with the removal of the older targets | Delete the `fn` route, `LoopBodyFnExpr`, `:state`, `operand_evaluation_order` and the `fn` registry row | Under a recorded owner ruling (§12); the refusal names the rewrite |

## 11. Where The Rules Live

This document is retired to Historical when the receiving sections below
carry the rules with their exception lists, the listed text is gone, and each
change of §10 is implemented or dropped; nothing may then cite it as authority.

| Rule | [Frontend specification](workflow_lisp_frontend_specification.md) | [Guide](../lisp_workflow_drafting_guide.md) | Text that leaves |
| --- | --- | --- | --- |
| 1 | A new subsection of §16 "Effect System": the sentence, its exceptions, §4's order and identity | §18 "Effects", one paragraph | Specification: §9's list of where pure expressions "may appear"; §10.3's "exactly one supported effectful call" bullet and "general effectful map bodies … remain outside"; §13.1 from "This adds neither an exhaustion evaluator" through the "Required behavior" list. Guide: the §2A rows "Pure contexts" (loses `:on-exhausted`) and "Serial `list/map-effect`"; §17.2's restriction paragraph |
| 2 | §13.1 "Bounded Loop": the form, the order, the `fn` form until removed. §10.3: the map forms and their exceptions | §17 "Loops" opens with it; its two loop examples use the binder | Specification: §13.1's `fn` block and "Lowering options". Guide: nothing more; §17.3's literal sentence stays true |
| 3 | §14 "Workflow Calls": the two conventions. §7.8 "Procedure References": locals called by name, the exceptions | §6 opens with it | Specification: §7.8's paragraph on V1 `let-proc` and `(proc-ref local-name)`. Guide: §16's two paragraphs on references become a pointer to §6 |

| Document | Change | Becomes Historical |
| --- | --- | --- |
| `specs/dsl.md` | It has no section for these forms and gains none. In "Workflow Lisp rich loop values": "not an exhaustion-time evaluator" and "arbitrary computed/effectful exhaustion expressions remain unsupported" become "`:on-exhausted` is an expression evaluated on exhaustion with the last state in scope; top-level Optional/Map state remains unsupported". In the run-reference placement note: "exhaustion guards and other pure contexts stay pure" becomes "a run reference stays refused in `:on-exhausted`, a map source and the pure places" | No |
| `specs/versioning.md` | The same run-reference sentence; one compatibility entry per change, none moving an identity | No |
| [List traversal](workflow_lisp_pure_list_traversal.md) | Loses "Bounded effectful binder" with its subsections | When the specification's §10.3, which defers to it today, carries its operator, constructor-typing, `list/map` and `path/join-under` rules |
| [let-proc](workflow_lisp_let_proc_local_proc_refs.md) | §7.3 and §27.2 are reversed by §6 here | When the release that removes the older targets removes the V1 form it specifies; write once §6.3 and the specification's §7.8 are then the contract |
| [Composition first](workflow_lisp_composition_first.md) | Loses §11.1's rule on pure fields and `:on-exhausted` and §11.3's `on-exhausted-call-edge` row | No |
| [Evaluated execution](workflow_lisp_evaluated_execution.md) | §1.2's "`:on-exhausted` remains a pure projection" keeps only the run-reference guard; §4.3's argument-position bullet points to the specification's §16; with I2b the keyword-order sentences of its last bullet go | No |
| [Tutorial](../tutorial_first_pipeline.md) | With I2, `grow.orc` uses the binder form; the rewrite does not move its digest | No |

## 12. Prerequisites And Open Decisions

| # | Item | Blocks |
| --- | --- | --- |
| 1 | The capture defect of §2.1 is fixed, with the scenario of §9, so that both constructor routes rename hoisted bindings and name a field's effects alike | E1 |
| 2 | The forms that are registered but refuse are deleted (one-target plan). Otherwise four fixtures that put `materialize-view` or `resource-transition` in a newly admitted position stop refusing in the typechecker and refuse later as `closed_program_gap` | E1 |
| 3 | A recorded reading of the versioning rule's "a change … to whether it compiles adds a target". E1, I1 and C1 admit source that is refused today and change no source that compiles; this design reads the rule as protecting source that compiles, so they add no target. Under the literal reading each adds one. **Ruled 2026-11-12: this reading holds;** the one-target plan's rule 2 is worded accordingly | E1, I1, C1 |
| 4 | The owner ruling that the release removing the older targets also removes the `fn` form. Without it both forms stay and rule 2's `fn`-form exception has no end. **Coordinator default, 2026-11-12: removed in that release;** the owner may keep both forms until it lands | I2b |
| 5 | The `bind-proc` defect of §2.1; it belongs to pure-call composition, not to this design | Nothing; rule 3 names it until fixed |
| 6 | A run-reference map body with several producers; owner: evaluated execution §1.2 | Only rule 2's run-reference exception |
