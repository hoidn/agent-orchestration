# Workflow Lisp Surface Coherence: Effects, Iteration, Callables

- **Status:** Designed (proposed), not implemented: until a step of §10 lands
  the compiler behaves as the "Today" columns of §2, and the "after" examples
  do not compile.
- **Owns:** where an effect may be written; the shape of the iteration forms;
  how each kind of callable is called.
- **Consumes:** [evaluated execution](workflow_lisp_evaluated_execution.md)
  §4.3, §6 and P5; the [closures boundary](workflow_lisp_runtime_closures_boundary.md).
- **Assumes:** one admitted source target, 2.40. Collapsing targets and
  deleting forms that are registered but refuse belong to
  [lane D step 4](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md);
  §12 says what changes if several targets are still alive.
- **Spec impact:** none on the closed-program format, the memo or the CLI for
  programs that compile today; §8 lists the diagnostics that retire and §11
  the one specification file that gains entries.

## 1. Summary

An assessment found three edges of the language incoherent: effects are allowed
in some value positions and refused in others, the iteration forms differ in
shape and rules, and four kinds of callable use three calling conventions.
Each claim was reproduced through the public command line before anything was
decided (§2). Most refusals protect nothing: they are rules of the retired
flat lowering route, where a value existed only as a step's output, left in
the typechecker. The three rules:

1. **Effects.** An effect may be written wherever a value is expected in a
   workflow or procedure body; operands run left to right, each once, and only
   `if`, `cond`, `match`, `and` and `or` skip any. The three pure places (a
   `defun` body, a `list/map` body, a parallel `:workspace`) take no effect.
2. **Iteration.** Every iteration form is `(form ((name source)) option… body)`:
   the binder names the loop state or the current item, each option is an
   expression evaluated once before the first round, and the body is any
   expression: pure in `list/map`, ending every path in `done` or `continue`
   in `loop/recur`.
3. **Callables.** Whatever a program defines (a function, a procedure, a local
   procedure, a procedure parameter) is called by name with positional
   arguments; a workflow, which can also be run from the command line, is
   called as the command line calls it, `(call w :input value)`; a procedure
   reference is a compile-time name, so it can be passed and bound but not
   stored, chosen at run time or returned.

No program that compiles today changes its closed program, program digest or
any effect identity (§8). A prototype of rules 1 and 2 and of rule 3's local
call is 101 added and 60 deleted lines in seven compiler files.

## 2. Verified Findings

149 programs at target 2.40, compiled and, where the claim is about running,
run with stand-in commands that log their calls. Class: **(a)** needed for a
stated guarantee, **(b)** unimplemented case, **(c)** historical accident. The
owning designs name the accidents: pure fields and a pure `:on-exhausted` are
"rules" of the flat 2.33 route
([composition first](workflow_lisp_composition_first.md) §11.1, whose tables
"do not establish target-2.36 refusals"); the one-call map body and literal
`:max` are the "first tranche" of 2.18, which erased to a `repeat_until` with
a literal bound ([list traversal](workflow_lisp_pure_list_traversal.md)); a
local called by name is "deferred" sugar
([let-proc](workflow_lisp_let_proc_local_proc_refs.md) §7.3, §27.2). `tsv` is
`typecheck_structural_values.py`; paths are under `orchestrator/workflow_lisp/`,
those starting `workflow/` or `contracts/` under `orchestrator/`.

### 2.1 Effect placement

The assessment's nine placements all reproduced. It under-counted both ways:
nine more positions refuse (three for a stated guarantee), eleven more accept.

| Position | Today | Decided in | Class |
| --- | --- | --- | --- |
| Procedure, function and workflow call argument; operator operand, nested too; `if` and `cond` condition; `and`/`or`/`not`; `match` subject and arm; `list/append` and `record-update` operand; `let*` binding; `done` and `continue` value; loop `:state` and `:max`; command `:argv` | Accepted; calls logged left to right, short-circuit kept | `wcc/elaborate.py:_elaborate_operands_to_values`, `conditionals.py:normalize_condition_expr` | — |
| Record field, variant field | `effect_not_permitted` | `typecheck_dispatch.py:_typecheck` | (c): the lowering of both already goes through `_elaborate_operands_to_values` |
| List element | `effect_not_permitted` | `tsv:typecheck_structural_value_expr` | (b): items are lowered as effect-free blocks |
| `:on-exhausted` value, a pure `defproc` call included | `loop_recur_contract_invalid` | `typecheck_loop_recur.py:typecheck_loop_recur_expr` | (c): the closed loop holds an exhaustion *body*, and evaluated execution §6 already names its path `loop:<label> / exhausted` |
| `list/map-effect` source and call arguments | `list_map_effect_body_unsupported` | `tsv` | (c) |
| `list/map` source; `path/join-under` child | `list_map_body_effect_forbidden`; `effect_not_permitted` | `tsv` | (b) |
| `bind-proc` value when the `bind-proc` is itself an argument (accepted when bound by `let*` first) | `procedure_call_unknown`, "unknown procedure callee `f`" | specialization | (b), wrong message |
| `list/map` body | `list_map_body_effect_forbidden` | `tsv` | (a) effect identity: a pure map is one value with no per-item frame |
| `defun` body | `pure_function_has_effect` | `functions.py` | (a) declared purity, relied on by pure contexts |
| Parallel `:workspace` | `list_map_effect_workspace_invalid` | `parallel_map.py:typecheck_parallel_workspace` | (a) resume determinism: evaluated again for every item on replay |

Not probed (probes use commands only): a provider's `:inputs`, which share
`wcc/elaborate.py:_prebind_effect_argument_matches` with command operands.

### 2.2 Iteration

| Claim | Today | Decided in | Class |
| --- | --- | --- | --- |
| `fn` is valid only as the loop body, with one parameter | Reproduced: `loop_recur_fn_outside_loop`, `loop_recur_fn_invalid` | `expressions.py:_elaborate_loop_body_fn`, `_guard_loop_fn_route` | (c) |
| `:on-exhausted` reads the name the later `fn` introduces | Reproduced, in either keyword order; `:state` cannot | `expressions.py:_elaborate_loop_recur` | (c) |
| A loop body is any expression | Reproduced, with one condition: every path ends in `done` or `continue` (`loop_recur_missing_done`) | `typecheck_loop_recur.py` | (a) bounded execution |
| A `list/map-effect` body must be exactly one call | Reproduced, and stricter: an inlined procedure body must hold exactly one effect | `tsv:_check_map_effect_body`; `closed/build.py:_check_loop_effect_cardinality` | (c). Not an invariant: a workflow-call body runs two effects per item, a procedure holding a nested loop or map passes, and a parallel map accepts a procedure with `let*`, `if` and two effects |
| `:max` takes a variable in `loop/recur`, a literal in `list/map-effect` | Reproduced; a loop takes even an effect there; `:parallel` is literal too | `expressions.py:_elaborate_list_map_effect`; `parallel_map.py:_positive_literal` | (c) serial, (b) parallel. Nothing reads the literal at compile time: a loop budget is a value (`workflow/evaluated/machine.py:_loop`); a parallel map compares and sizes its workers at run time (`machine.py:_parallel_source`, `parallel.py`); only `contracts/closed_program/check.py:_parallel_map_body` requires integers |
| (New) A serial map over a list longer than `:max` | Runs `:max` items, then fails `list_map_effect_cap_exceeded`; a parallel map fails before any item | `machine.py:_loop`, `_parallel_source` | (c) |
| (New) Ruling P12: no confined run-reference site in a map body | Kept | `typecheck_run_ref.py:_refuse_confined_site_in_map_frame` walks the body and every callee it reaches, whatever the body's shape | (a) |

### 2.3 Callables

| Claim | Today | Decided in | Class |
| --- | --- | --- | --- |
| `defun` and `defproc` are called positionally | Reproduced. A keyword there crashes: Python traceback, exit 1 | `expressions.py:_elaborate` | Defect |
| `defworkflow` only through `(call w :x n)` | Reproduced: `(w n)` gives `procedure_call_unknown`, `(call p :x n)` on a procedure gives `workflow_call_unknown`; neither message names the other convention | `expressions.py:_elaborate_list`; `typecheck_calls.py` | By design: workflow inputs are named, may be omitted when defaulted, and are the names `--input` uses |
| A `let-proc` local cannot be called by name | Reproduced (`let_proc_bare_name_invalid`), yet `(let* ((g (proc-ref f))) (g 1))` compiles when `f` has a signature | `expressions.py:_elaborate_list` | (b) |
| Procedure references cannot be stored or returned | Partly wrong: a reference can be bound by `let*`, forwarded and called. Refused in a record, a list, a workflow input or result, as a procedure's result, or as the value of an `if` | `type_env.py`, `workflows.py`, `typecheck_calls.py` | (a) no runtime closures |
| Recursion is refused | Reproduced (`proc_lowering_cycle`, `function_cycle`); a workflow that calls itself is refused as `compiler_defect` (`RecursionError`) | `closed/build.py` | (a) bounded execution; the workflow diagnostic is a defect |

## 3. Decision

Adopt the three rules and make these changes, ranked by value over cost.

| # | Change | Compiler | Tests |
| --- | --- | --- | --- |
| E1 | Admit effects in record fields, variant fields, list elements, `:on-exhausted` and a map's source; then `list/map` source and `path/join-under` child | 5 files, about +65 −50 | 6 refusal test functions flip (of those in the 22 files run); 38 matrix cells move from refused to admitted |
| I1 | A `list/map-effect` body is any expression; a serial map checks its cap before the first item; a serial `:max` is any `Int` expression | 7 files, about +45 −15 | 2 refusal test functions flip; new body and cap cases |
| C1 | A `let-proc` local with a signature is called by name; three diagnostics name the right convention; a recursive workflow gets a cycle diagnostic | 3 files, about +45 −10 | 1 flips, 4 new |
| I2 | `loop/recur` takes the map forms' binder; `fn` and `:state` leave the language | 4 files, about +45 −230; Python emitter 4 lines | Rewrite 15 source files (15 loops), 154 test files (277 loops), 22 documents (27) |
| I3 | Parallel `:max` and `:parallel` are `Int` expressions | 5 files, about +30 | 4 new |

Rejected: *documenting the refusals instead* (a table of twelve positions, and
`(record R :a (command-result …))`, the first thing a newcomer writes, still
fails); *desugaring at typecheck into generated `let*`* (needs fresh names and
labels the lowering already has); *keeping both loop syntaxes for good* (adds
a form instead of removing one). §7 lists what is not done at all.

## 4. Effects

**Evaluation order.** (1) Operands are evaluated left to right as written:
fields in the order written, not declared; `call` arguments in the order
written; a `record-update` base before its fields; an inner effect before the
effect it is an operand of. (2) `if`, `cond` and `match` evaluate the
condition or subject, then only the selected branch; `and` and `or` stop at
the first operand that decides. (3) All effects of one operand finish before
the next operand starts; the enclosing form is applied last. (4) Each effect
runs once per evaluation of its body: once per loop round or map item. (5) A
pure operator, `print` included, is computed when its enclosing value is
built, after its siblings' effects.

**Identity.** An effect without an authored binding name takes `#k`, its
ordinal among the unnamed effects of its scope (evaluated execution §6, I4);
§4.3 there already says an effectful argument "is bound by a `let` before the
call, in source order" and adds no aggregate position to an identity. This
design applies that to the refused positions and adds no identity rule: `#k`
in evaluation order, `#k / body / then|else|<variant> / …` inside a selected
branch, `loop:<label> / exhausted / …` in `:on-exhausted`. A `let*` name
survives edits that add unnamed effects before it, so binding stays the advice
for a step someone will `invalidate` by name.

**Becomes legal** (nothing becomes refused; the `let*` spelling stays legal):

```lisp
;; today: effect_not_permitted
(record Outcome
  :words (command-result count :argv ("python" "count.py" file) :returns Int)
  :pads 0)
(list (fetch "a") (fetch "b"))
(variant Decision APPROVE :evidence (review draft))
(loop/recur ((s 0)) :max 3 :on-exhausted (give-up s) (step s))
```

## 5. Iteration

```lisp
(loop/recur ((state init)) :max n [:on-exhausted e] body)   ; every path: done / continue
(list/map ((x xs)) body)                                    ; pure body, no options
(list/map-effect ((x xs)) :max n body)
(list/map-effect ((x xs)) :max n :parallel k :workspace dir body)
```

**Scope and order.** The binder's source, `:max` and `:parallel` are evaluated
once, in the order written, before the first round, and cannot see the binder.
The body, `:on-exhausted` (holding the last state) and `:workspace` (per item,
pure) see it, which makes regular what `:on-exhausted` does today by reading a
name the later `fn` introduces. A map's `:max` caps the list's length and is
checked when the list is known, before any item runs, serial or parallel. A
literal `:max` or `:parallel` below 1 stays a compile error; a computed one
fails the run with that code.

**Becomes legal** (only `(fn …)` and `:state` become refused, after I2's last
step):

```lisp
;; today: list_map_effect_body_unsupported and list_map_effect_max_invalid
(list/map-effect ((repo repos)) :max limit
  (let* ((checked (check repo)))
    (if checked.passed checked (fix repo checked))))
;; today: (loop/recur :max 5 :state 0 :on-exhausted (give-up pads) (fn (pads) …))
(loop/recur ((pads 0)) :max 5 :on-exhausted (give-up pads)
  (if (enough? pads) (done pads) (continue (pad pads))))
```

**What the restrictions protected.** Nothing, for provider, command and call
bodies. A serial map is typed as a `loop/recur` over `{remaining, results}`
(`tsv`), whose body may already be anything; a `par-map` node holds a general
body. Item identity comes from the frame (`loop:#k[i]`, `par-map:<binder>[i]`),
not the body's shape; the item workspace applies to every direct effect; P12
and the parallel `Agent` boundary walk the whole body and its callees. One
dependency is real: for a body containing a run reference,
`closed/build.py:_bind_map_run_ref_result` binds the map's result to a single
producer and evaluated execution §1.2 admits only "the one-effect body".
**Such a body keeps today's one-call shape.**

**The owner's candidate, tested** ("one shape; the body is any expression;
every bound an expression checked at run time"). It holds, with four caveats:

1. A loop body is not any expression: each path ends in `done` or `continue`.
2. A body with a run reference stays one call.
3. The binder precedes `:max`, so the state is evaluated first. A loop written
   `:max E1 :state E2` with both operands effectful runs `E1` first today and
   `E2` first after a mechanical rewrite. No source outside `tests/` has a
   non-atomic `:max`; 15 loops in 6 test files do, on purpose, and either bind
   the budget with `let*` first or accept the new order. The keyword-order
   fact (`operand_evaluation_order`) then leaves the compiler.
4. "Checked when the list is known" is true of parallel maps only; I1 makes a
   too-long serial map fail before spending, not after `:max` items.

**Migration of `loop/recur`, measured.** 17 loop programs rewritten by a
span-based script have the same program digest in both syntaxes. A run of the
tutorial's `grow.orc` started from the `fn` form and stopped at a failed step
resumed from the rewritten source, reusing its committed step under the same
identity. `resume` compiles the source, so a run strands only if its source
is still in the `fn` form when that form is removed.

## 6. Callables

```lisp
;; today: let_proc_bare_name_invalid
(let-proc ((bump ((x Int)) -> Int (+ x step)))
  (+ (bump 1) (bump 2)))
```

A local without a signature still needs one consumer that supplies it, and is
told "give `f` a signature to call it by name". `(w n)` on a workflow says
"`w` is a workflow; call it as `(call w :x …)`"; `(call p …)` on a procedure
says "`p` is a procedure; call it as `(p …)`"; a keyword in a positional call
gets that message, not a traceback; a workflow that reaches itself gets a
cycle diagnostic, as procedures have.

## 7. What Stays, And Why

| Left alone | Why |
| --- | --- |
| The three pure places | (a), §2.1 |
| Run references: refused in `:on-exhausted` and a map source, one call as a map body | Owned by evaluated execution §1.2; not assessed here |
| `list/map` beside `list/map-effect` | The pure one is a value, usable in a `defun`, with no bound and no identity |
| A serial map's step names, `loop:#k[i] / else / …` (one-based; `par-map` is zero-based) | They expose the lowering, but renaming them moves every serial map's identities in every recorded run |
| Two calling conventions | A workflow's inputs are a public contract: named, with defaults a caller may omit, the names `--input` uses and a compiled import is addressed by. A positional workflow call or a keyword procedure call adds a second way to call something and removes nothing |
| `defun` beside `defproc` | A `defun` declares a callable pure, checked and expanded inline. Folding it into `defproc` turns expansions into call nodes and moves the digest of every program that uses one |
| Stored, selected or returned procedure references | A runtime callable value; the closures boundary (§4, §5) forbids adding one as a small feature, and no consumer needs it. Not reopened |
| Recursion; sibling and self calls of locals | P5: evaluation terminates because no call is recursive and every loop has a budget |
| `loop-state`, `done`, `continue` | Unaffected |

## 8. Feasibility, Compatibility And Identity

| Change | Existing path it relies on | Prototype result |
| --- | --- | --- |
| Effects in record and variant fields | Their lowering already calls `_elaborate_operands_to_values`, the function behind operator operands | Two checks deleted. Fields run in written order, short-circuit intact; shadowed names and a `match` in a sibling field keep their values |
| Effects in list elements | The same function, selected by a typechecker-set flag on `ListExpr` (beside `item_type_refs`) so pure lists keep today's lowering | Runs in order; pure lists keep their digest |
| Effectful `:on-exhausted`, map source | The closed loop's exhaustion body; the loop-state seed | Checks deleted; identity `loop:s / exhausted / #1` |
| The three placements across helper kinds | Totality matrix | The 24 field cells and 14 `:on-exhausted` cells that refuse today pass as admitted (native value, ordered command log) for inline, same-module and imported helpers |
| Map body is any expression | A serial map is a `loop/recur`; a `par-map` body is general | Serial and parallel maps ran `if`, a `let*` of two effects, a record of two effects, a `match`, a nested map, a nested loop and a pure body; identities such as `loop:#1[2] / else / z=procedure:…` and `par-map:x[0] / b / body / then / #1=…` |
| Cap checked before the first item | `machine.py:_loop`, keyed on the code the serial map's loop already carries | 4 lines; closed program unchanged |
| Serial `:max` expression | The map passes `:max` to its loop as the budget, and budgets are values | Not prototyped |
| Binder form | The same `LoopRecurExpr` | 45-line parser; see §5 for digests and resume |
| Local called by name | The alias form that compiles today | 14 lines; an effectful local called twice ran under `#1=procedure:…f` and `#2=procedure:…f` |
| `list/map` source, `path/join-under` child, the `bind-proc` defect, I3 | The list case; §12 | Not prototyped |

| Question | Answer | Evidence |
| --- | --- | --- |
| Does a program that compiles today change its closed program, digest or an effect identity under E1, I1, C1 or I2? | No | 76 of the 149 probes compile today: 0 digest changes under the prototype, 24 more compile, none newly refused. The closed-program corpus (55 rows, 11 built) has identical digests. Of 1014 tests in 19 files that pin elaboration, sites, loops, maps and procedures, 982 pass; the 32 failures are in 11 functions asserting a refusal the prototype removed, 12 of them the run-reference bodies this design keeps refused |
| Does behavior change for such a program? | Once: a serial map over a list longer than `:max` fails before its first item, with the same code and closed program | §5 |
| Is anything legal today refused? | The `fn` form and `:state`, after I2's last step | §5 |
| I3 | A `par-map` node keeps a bare integer for a literal, so digests stay; a non-literal becomes a pure value there | §12 |
| Which diagnostics retire? | `effect_not_permitted` for fields, elements and the path child; `list_map_effect_body_unsupported` except for run-reference bodies and malformed clauses; `loop_recur_contract_invalid` for an effectful exhaustion; `let_proc_bare_name_invalid`; with I2, `loop_recur_fn_invalid` and `loop_recur_fn_outside_loop` | `list_map_effect_max_invalid` remains for a missing `:max` or a literal below 1 |

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

Scenarios each step adds through the public CLI with stand-in commands. E1:
`(record R :b E2 :a E1)` logs `E2` then `E1`; an `and` in a field skips its
second effect; the same record in a `defun` or `list/map` body refuses; a run
killed between the two field effects resumes with one dispatch. I1: a map body
of two bound effects, killed after the first effect of item 2, resumes with
one dispatch; a list of 3 under `:max 2` logs no call; a run reference in a
`let*` body still refuses. I2: every rewritten source keeps its recorded
digest, and a run started before the rewrite resumes after it. C1: a local
called twice has two frames; `(w 1)` on a workflow names `call`.

## 10. Implementation Handoff

Ordered; each step ships alone and leaves the suite green. No step may add a
lowering route, a closed construct or an identity rule.

1. **E1a** `typecheck_dispatch.py`: delete the two field purity checks.
   `typecheck_loop_recur.py`: delete the exhaustion purity check, keep the
   run-reference guard. Drop the three matching rules from `cell_refusal`
   (`tests/workflow_evaluated_totality_helpers.py`) and `RULES`
   (`tests/workflow_lisp_totality_matrix_sources.py`); flip the refusal tests.
2. **E1b** `expressions.py` (`ListExpr`, `ListMapExpr`, `PathJoinUnderExpr`):
   one typechecker-set flag each, outside semantic identity as
   `item_type_refs` is. `typecheck_structural_values.py`: set it instead of
   refusing; delete the map-source check. `wcc/elaborate.py`
   (`_elaborate_expr_to_value`): when set, lower through
   `_elaborate_operands_to_values`. Select by the flag, not by
   `conditionals._contains_effect`, which counts every procedure call and
   would change the lowering of pure lists.
3. **I1** `typecheck_structural_values.py`: apply `_check_map_effect_body`,
   the argument-purity check and `single_iteration_effect_kinds` only when the
   typed body's summary contains a run reference; pass a typed `:max` as the
   synthetic loop's budget; keep that loop's `list_map_effect_cap_exceeded`
   code, which P12 reads. `expressions.py` (`ListMapEffectExpr`): an optional
   `max_expr` child, handled as `workspace_expr` is in
   `expression_traversal.py`, `procedure_typecheck.py` and `closed/names.py`.
   `workflow/evaluated/machine.py` (`_loop`): the cap check.
4. **C1** `expressions.py` (`_elaborate_list`, `_elaborate`): the local call,
   the workflow-called-positionally message and the keyword diagnostic.
   `typecheck_calls.py`: the procedure-under-`call` message. `closed/build.py`:
   the workflow cycle diagnostic.
5. **I2a** `expressions.py`: accept the binder form beside `fn`, warning on
   `fn`. `orchestrator/py/emit.py`: emit the binder form. Rewrite the 15
   sources (4 are packaged `std` modules), the guide and the tutorial by
   script, comparing digests.
6. **I2b** Rewrite the tests; delete the `fn` route, `LoopBodyFnExpr`,
   `:state`, `operand_evaluation_order` and the `fn` registry row.
7. **I3**, when a consumer needs it: `parallel_map.py`, `wcc/model.py`,
   `closed/build.py`, `contracts/closed_program/check.py`, `machine.py`.

## 11. Documentation Impact

The changes below remove about 180 lines from six documents and add this one.
The corpus shrinks only if this is not one more place to read the rules: §1
and the order and scope statements of §4–§6 belong in the frontend
specification and the guide; once there, this is a historical decision record.

| Document | Change |
| --- | --- |
| [List traversal](workflow_lisp_pure_list_traversal.md) | "Bounded effectful binder" with its three subsections (lines 234–335 of 460) is superseded by §5 and deleted; the pure half stays the owner of list typing and `path/join-under` |
| [Frontend specification](workflow_lisp_frontend_specification.md) | §13.1 "Required behavior" (30 lines on `repeat_until` exhaustion projection) becomes the binder form and two sentences; §10.3's "exactly one supported effectful call" bullet goes |
| [Composition first](workflow_lisp_composition_first.md) | §11.1's rule on pure fields and `:on-exhausted` and §11.3's `on-exhausted-call-edge` row are deleted |
| [let-proc](workflow_lisp_let_proc_local_proc_refs.md) | §7.3, §27.2 and the direct-call bullets of §21, §22 and §27 are superseded by §6 |
| [Evaluated execution](workflow_lisp_evaluated_execution.md) | §1.2's "`:on-exhausted` remains a pure projection" keeps only the run-reference guard; §4.3's argument-position bullet points here; with I2 the keyword-order sentences of its last bullet go |
| [Drafting guide](../lisp_workflow_drafting_guide.md) | §18 gains rule 1 as one paragraph; §17 opens with rule 2, its two loop examples lose `fn`, §17.2's restriction paragraph and §17.3's literal sentence go; §6 opens with rule 3; the §2A row "one admitted effect per body" goes |
| [Tutorial](../tutorial_first_pipeline.md) | With I2, `grow.orc` uses the binder form; its printed digest does not change |
| `specs/` | Nothing shortens. `specs/versioning.md` gains one entry per shipped step; `specs/dsl.md`'s run-reference placement text ("the one-effect body of a serial `list/map-effect`", pure exhaustion guards) stays true |

## 12. Open Prerequisites And Stop Criteria

| # | Prerequisite | Blocks |
| --- | --- | --- |
| 1 | Several targets are still admitted. E1, I1 and C1 move no identity, so they can apply to every admitted target; the versioning rule the roadmap assigns to lane D step 4 decides | Nothing if decided "all targets"; otherwise E1, I1 and C1 wait for the collapse |
| 2 | Removing `fn` refuses old source, and `resume` compiles source. Needs the rewrite script as a maintained tool, a release accepting both forms, and the same rewrite in consumer repositories | I2b |
| 3 | The rewrite script handles `.orc` files; the 277 loops inside Python test strings need it extended or a hand pass | I2b |
| 4 | A run-reference map body with several producers; owner: evaluated execution §1.2 | Only the exception in §5 |
| 5 | `bind-proc` with an effectful bound value passed directly: a fix, or a diagnostic naming the cause | Nothing; rule 1 is false at that one position until then |
| 6 | Calling a local without a signature needs its parameter types inferred from the call | Nothing |
| 7 | I3 changes what the closed-program check accepts in a `par-map` node and needs the same edit where that node is specified | I3 |

Stop and revise if a step changes a digest in the corpus comparison, needs a
new closed construct or identity segment, or the matrix shows an admitted
placement whose command log is not in written order. The prototype (worktree
`.worktrees/spike-coherence`, branch `spike/surface-coherence`, uncommitted)
is evidence, not the implementation: it accepts both loop syntaxes, guards the
run-reference body only in `closed/build.py` and adds no tests. The 38
admitted cells reproduce from tracked code alone: apply step 1 and run the
first command of §9.
