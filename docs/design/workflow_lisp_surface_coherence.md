# Workflow Lisp Surface Coherence: Effects, Iteration, Callables

- **Status:** Accepted 2026-11-12 as the basis for implementation, after an
  independent review (accept with changes; all applied). Partly implemented:
  changes C1 (callables called by name), I1 (any expression as a map body, in programs
  with no run reference; a computed serial `:max`, in every program) and I2a (the binder form of
  `loop/recur`) are on `main` since 2026-11-13, and E1 (a direct effect in a field,
  payload, element, path child, `match` subject, map source or `continue` value
  whose other parts are simple; narrower than first accepted, see §13) since
  2026-11-14. For I2b the compiler behaves as the "Today" column of §2. Where this page and the merged behaviour differ, the
  [frontend specification](workflow_lisp_frontend_specification.md) and
  `specs/versioning.md` ("Source admitted without a new target") state what
  compiles; §13 lists where the merged changes depart from the accepted text.
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

- *A field, a list element, a path child, a map source and `:on-exhausted`
  take an effect only in a simple value:* a literal, a name, a field read, or
  an effect form (a provider, command, agent or workflow call), an operator
  application other than `and`, `or` and `not`, or a record, variant, list or
  `path/join-under`, over simple parts. No call of a procedure, a `let-proc`
  local or a `defun` is simple, whatever the callee holds. Every part of the
  value must be simple, the one with the effect and the ones beside it; any
  other value there stays refused, with the code the place gave before, and
  so does such a place inside a call's argument or a `let-proc` local's body
  (§4, §13).
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
  A computed `:max` below 1 fails with that code before any item when the
  list has one; an empty list gives the empty list whatever its `:max`.
- *Beside a run reference a map body is one call:* in a program that contains
  a run reference anywhere, every `list/map-effect` iteration is exactly one
  call with pure arguments, whether or not it reaches the run reference. The
  program is the final closed program, so a definition that nothing calls
  does not count. A later change may admit more bodies by analysing each
  iteration (§5).
- *A parallel map* runs items concurrently, so order holds within an item
  only; its body admits no `Agent` crossing the item boundary, no phased
  provider, no host input and no confined run reference (the guard for the
  last has an open defect, §2.2).
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
- *A local does not shadow a function or a form:* `(f …)` calls the `defun`
  or the built-in form named `f`, not a local of that name. Refusing such a
  local at its definition stops source that compiles, so only the release
  that removes the older targets may do it (§13).
- *A bound reference is a literal or a forwarded one:* a `let*` binding of a
  reference chosen by `if`, `cond` or `match`, or returned by a procedure, is
  refused at the binding, also in a procedure that nothing calls (§6).
- *A `defun`* takes no procedure parameter and is not a `proc-ref` target.
- *No recursion:* no function or procedure may reach itself, nor may a
  workflow that the entry reaches.
- *A workflow reference parameter* is called like a workflow, `(call w :x v)`.
- *A macro is not a callable:* its use is expanded before any call exists and
  has the shape its definition gives it (not assessed here).
- *Defect, not a rule (§12):* a `bind-proc` over a pure procedure cannot carry
  a computed value into another procedure.
- *Defects, not rules (the roadmap's open list, §13):* a procedure-reference
  parameter forwarded through `let*` fails with `name_unknown` when its
  procedure is called; an inner binding that is not a reference does not hide
  an outer reference of the same name.

No program that compiles today changes its closed program, program digest,
effect identities or behavior (§8), with the two exceptions that C1 and I2a
made and §13 records.

## 2. Verified Findings

294 programs at target 2.40, compiled and, where the claim is about running,
run with stand-in commands that log their calls, on `main` and on the
prototype (§8). Class: **(a)** needed for a stated guarantee, **(b)**
unimplemented case, **(c)** historical accident, named as such by its owning
design: pure fields and a pure `:on-exhausted` are "rules" of the flat 2.33
route ([composition first](workflow_lisp_composition_first.md) §11.1), the
one-call map body and literal `:max` the "first tranche" of 2.18
([list traversal](workflow_lisp_pure_list_traversal.md), historical record), a local called by
name "deferred" ([let-proc](workflow_lisp_let_proc_local_proc_refs.md) §7.3).
`tsv` is `typecheck_structural_values.py`; paths are under
`orchestrator/workflow_lisp/`, or `orchestrator/` if they start with
`workflow/` or `contracts/`. "Today" in the tables is `main` on 2026-11-12,
before any change of §3; C1, I1 and I2a have since changed the rows they
address, and E1 the refused rows of §2.1: each of those positions now takes an
effect in a simple value (§4) and keeps its code for every other value.

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
| (New) Ruling P12: no confined run-reference site in a map body | Kept | `typecheck_run_ref.py:_refuse_confined_site_in_map_frame` walks the body and every callee it reaches, whatever the body's shape. Open defect: it does not follow a call of a procedure-reference parameter, so a confined site passed in as a reference, a `let-proc` local's included, is not seen | (a) |

### 2.3 Callables

| Claim | Today | Decided in | Class |
| --- | --- | --- | --- |
| `defun` and `defproc` are called positionally | Reproduced. A keyword there crashes: Python traceback, exit 1 | `expressions.py:_elaborate` | Defect |
| `defworkflow` only through `(call w :x n)` | Reproduced: `(w n)` gives `procedure_call_unknown`, `(call p :x n)` on a procedure gives `workflow_call_unknown`; neither message names the other convention | `expressions.py:_elaborate_list`; `typecheck_calls.py` | By design: workflow inputs are named, may be omitted when defaulted, and are the names `--input` uses |
| A `let-proc` local cannot be called by name | Reproduced (`let_proc_bare_name_invalid`), yet `(let* ((g (proc-ref f))) (g 1))` compiles when `f` has a signature | `expressions.py:_elaborate_list` | (b) |
| (New) A local calling another local, or a nested `let-proc` | Refused: `let_proc_bare_name_invalid`, `let_proc_nested_unsupported` | [Write once](workflow_lisp_write_once.md) §6.3: "do not permit sibling calls" | By design |
| Procedure references cannot be stored or returned | Partly wrong: a reference can be bound by `let*`, forwarded and called. Refused in a record, a list, a workflow input or result, as a procedure's result, or as the value of an `if` (the last by a `compiler_defect` when probed; C1 refuses it with a code, §6) | `type_env.py`, `workflows.py`, `typecheck_calls.py` | (a) no runtime closures |
| Recursion is refused | Reproduced (`proc_lowering_cycle`, `function_cycle`); a workflow that calls itself is refused as `compiler_defect` (`RecursionError`) | `closed/build.py` | (a) bounded execution; the workflow diagnostic is a defect |

## 3. Decision

Adopt the three rules and make these changes, ranked by value over cost. Sizes
are measured on the prototype or estimated from it (2026-11-12).

| # | Change | Requires | Compiler | Tests |
| --- | --- | --- | --- | --- |
| E1 | Admit effects, in a simple value (§4), in record fields, variant fields, list elements, `:on-exhausted` and a map's source; then `list/map` source and `path/join-under` child. A pure `match` is a value as an operand | The capture fix; the refused forms deleted (§12) | 5 files, about +95 −70 | 6 refusal test functions flip (13 cases); 38 matrix cells move from refused to admitted |
| I1 | A `list/map-effect` body is any expression in a program that contains no run reference, and one call with pure arguments in a program that contains one; a serial `:max` is any `Int` expression; a serial map evaluates its source, then `:max` | — | 5 files, about +45 −15 | 2 refusal test functions flip (6 cases) |
| C1 | A `let-proc` local with a signature is called by name; five diagnostics name the cause (§6); a recursive workflow gets a cycle diagnostic; a reference bound after being chosen at run time is refused with a code | — | 5 files, about +55 −10 | 1 flips; 6 new |
| I2 | `loop/recur` takes the map forms' binder. I2a: accepted beside the `fn` form, building the same program, with the migration tool. I2b: `fn` and `:state` are refused and the Python frontend emits the binder | I2b: the release that removes the older targets, and the rewrite (§5) | I2a 2 files, about +50; I2b about −230 | 15 source files (15 loops), 154 test files (277 loops), 22 documents (27) rewritten by the migration tool, or by hand where it lists a loop or does not read the file (§5) |

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
`invalidate` by name.

**In a simple value only.** A record or variant field, a list element, a
`path/join-under` child, a `list/map` or `list/map-effect` source and an
`:on-exhausted` value take an effect when every part of the value is simple
(rule 1; the definition is the frontend specification's §16.3). A simple value
has no branch, so its effects are named by ordinal alone: the same whether an
authored `let*` binds the value first or not, whatever simple parts stand
beside the effect and in whatever order. Any other value that holds an effect
there (an `if`, `cond`, `match`, `let*`, `and`, `or`, a loop, a map, a run
reference, or a call of a procedure, a `let-proc` local or a `defun`, as the
part with the effect or beside it) is refused as before, at the part to bind
first; `:on-exhausted`, which has no place to bind first, calls a workflow.
The reason is identity: with a branch in the value, an effect's name depended
on whether a `let*` bound the value and on the pure parts beside it (§13).

A procedure call is not simple even when the procedure holds the effect: the
compiler knows what a callee holds only after its provisional passes, and it
replaces a pure procedure's call by the procedure's body in one pass and not
in another, so no test of the call gives one answer in every place. For the
same reason a call's arguments and a `let-proc` local's body admit nothing
new: a field, an element, a path child, a map source or an `:on-exhausted`
value that holds an effect stays refused anywhere inside an argument of a
procedure, `let-proc` local or `defun` call and anywhere in a local's body.
The effect, or the value, is bound with `let*` first. A top-level `defproc`
body takes these places as a workflow body does.

**Becomes legal** (nothing becomes refused; the `let*` spelling stays legal):

```lisp
;; today: effect_not_permitted
(record Outcome
  :words (command-result count :argv ("python" "count.py" file) :returns Int)
  :pads 0)
(list (call fetch :key "a") (call fetch :key "b"))      ; `fetch` is a workflow
(loop/recur ((s 0)) :max 3 :on-exhausted (call give-up :s s)
  (if (> s 5) (done s) (continue (call step :s s))))
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
evaluated per item and is pure. A `:max` below 1 gives a loop no round. A
serial map whose computed `:max` is below 1 fails with
`list_map_effect_cap_exceeded` before any item when its list has one, and
returns the empty list when the list is empty, as a literal `:max` over an
empty list always did; a literal below 1 on a map stays a compile error.
Existing programs are unaffected: a serial map's `:max` is a literal today,
so running its source first reorders nothing and digests stay while `:max`
is pure; a `:max` with an effect exists only in new programs, where it
follows the source's effects (measured: `ints, 7, 1, 2, 3`; a map source
holds an effect only with E1, so I1 alone gives `:max` nothing to follow); a
`fn`-form loop keeps its keyword order while that form compiles.

**Becomes legal:**

```lisp
;; today: list_map_effect_body_unsupported and list_map_effect_max_invalid
;; (legal where the program contains no run reference)
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
P12 and the parallel `Agent` boundary walk the whole body and its callees
(P12 with the open defect of §2.2). One dependency is real, hence rule 2's
run-reference exception: for a body with a run reference,
`closed/build.py:_bind_map_run_ref_result` binds the map's result to a single
producer, and evaluated execution §1.2 admits only "the one-effect body".

**Why the exception is drawn around the program.** Nothing available decides
soundly whether one iteration reaches a run reference. An effect summary
describes a whole definition, not an iteration, and an imported workflow's
summary is lost after the first round of the effect fixpoint and then reads
as "no effects" (open defect). So the closed build looks for a run-reference
effect in the final closed program, entry and definitions, and when it finds
one holds every map to the one-call shape that every such program had before
I1. This refuses general bodies that reach no run reference; admitting them
needs an analysis of each iteration that is sound for imported workflows
(§12, item 6). What compiles: specification §10.3.

**The binder form of `loop/recur`: contract.** Both forms build the same
program. The `fn` form is removed in the release that removes the older
targets, the one release that already refuses existing source. A run started
under the `fn` form resumes from the rewritten source; `resume` compiles
source, so after that release it does not resume from unrewritten source.
Evidence: 17 loop programs here, and in the review the 27 tracked programs
with loops and the four packaged library modules with their importers, keep
digest and site list when rewritten; a run of the tutorial's `grow.orc`,
stopped at a failed step under the `fn` form, resumed from the rewritten
source and reused its committed step. What the binder form refuses:
specification §13.1.

**In a macro template.** The loop state is a binding of the template in both
forms: it is renamed for the expansion and bound in the body and in
`:on-exhausted`, while the initial state and the other options are read in
the enclosing scope. Without this a binder loop in a template read a
caller's value or failed with `name_unknown`. The same pass treats a
`let-proc` parameter as a binding and every item of a `cond` clause as an
expression. A template that bound such a name itself compiled before with
the wrong binding, and its value and digest change (§13). A name at the head
of a list is not renamed: what a head names is the resolver's knowledge, and
renaming it in the hygiene pass let a template local beat a function, a
macro or a form. So a caller's binding can still answer a call a template
meant for its own local (open defect).

**The rewrite.** One case changes order: a `fn` loop written `:max E1 :state
E2` with an effect in both runs `E1` first, and the binder form runs `E2`
first. No loop outside `tests/` has a non-atomic `:max` (15 loops, read with
the compiler's reader); 15 loops in 6 test files do. The migration tool,
`scripts/migrate_orc_sources.py`, therefore rewrites a loop without compiling
it only where the order cannot change: `:state` is written before `:max`, or
`:max` is an atom, or the initial state is an atom or a constant constructor.
Any other loop it compiles before and after, and rewrites only when every
exported workflow of the source builds and keeps its program hash and the
loop sits inside one of them or in a template the source uses: a hash proves
nothing about a loop that no built workflow reaches, and most test sources
(fragments, formatted strings, library modules) do not build alone. Every
loop it does not rewrite stays in
the `fn` form and is listed with its reason, as is text it does not treat as
source: strings assembled or matched by a test, and Python outside `tests/`
and `experiments/`. A listed test whose subject is the keyword
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
that compiles today, and builds that form's program. The one case where it
is not the alias call is a local named like a `defun` or a built-in form:
those names resolved to the function or the form before C1, so `(f …)` keeps
reaching them and the local is not called. An inner binding of the local's
name wins over the local, as lexical scope says. The specification's §7.8
table says what `(f …)` reaches for every collision.

| Source | Diagnostic |
| --- | --- |
| A local without a signature, called by name | "give `f` a signature to call it by name" |
| A local called from another local | "the locals of one `let-proc` do not see each other; define `f` with `defproc`" |
| `(w n)` on a workflow | "`w` is a workflow; call it as `(call w :x …)`" |
| `(call p …)` on a procedure | "`p` is a procedure; call it as `(p …)`" |
| A keyword in a positional call | The same message, instead of a traceback |
| A workflow that reaches itself | A cycle diagnostic, as procedures and functions have, for a workflow the entry reaches; a cycle that passes through a procedure or a workflow reference parameter is reported as that procedure's cycle |
| A `let*` binding of a reference chosen by `if`, `cond` or `match`, or returned by a procedure | "a procedure reference is a compile-time name", at the binding (`proc_ref_literal_required`), instead of a `compiler_defect` |

The last row is the one refusal of C1 that reaches source which compiled
before. The check runs where the procedure is defined, so a procedure that
binds such a reference is refused even when nothing calls it; before, it
compiled exactly when nothing called it, and every call of it was refused or
crashed. A reference forwarded unchanged (`(let* ((h g)) …)`, or a
procedure-reference parameter) passes this check. Codes, and where each
message is not yet given (a module-qualified workflow name, a compile with
imported workflow bundles): specification §7.8 and §14.

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
| The three placements across helper kinds | Totality matrix | The 24 field cells and 14 `:on-exhausted` cells that refuse today pass as admitted (native value, ordered command log) for inline, same-module and imported helpers. As merged (§13): the cells whose effect stands behind a procedure call keep their refusal; the command forms written inline are admitted |
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
| Is anything legal today refused? | The `fn` form and `:state`, with I2b; with C1, a procedure that nothing calls and that binds a reference chosen at run time | §5, §6 |
| Which diagnostics retire? | For a simple value only (§4): `effect_not_permitted` for fields, elements and the path child; `list_map_effect_body_unsupported` and `list_map_body_effect_forbidden` for a source; `loop_recur_contract_invalid` for an effectful exhaustion. Each stays for a value that is not simple. `list_map_effect_body_unsupported` also stays in a program that contains a run reference and for malformed clauses; `let_proc_bare_name_invalid`; with I2b, `loop_recur_fn_invalid` and `loop_recur_fn_outside_loop` | `list_map_effect_max_invalid` remains for a missing or non-`Int` `:max` and a literal below 1 |

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
pytest -q tests/test_workflow_lisp_callables_coherence.py tests/test_workflow_lisp_map_effect_{general,run_ref}_body.py
pytest -q tests/test_workflow_lisp_loop_recur_binder.py tests/test_workflow_lisp_macro_hygiene_bindings.py tests/test_migrate_orc_sources.py
pytest -q -n 16 --dist=worksteal --sample 10   # the whole suite before merging
```

Scenarios each change adds, through the public CLI with stand-in commands:

| Change | Scenario |
| --- | --- |
| Capture fix, before E1 | `(let* ((y 1)) (record Tri :a (let* ((y 7)) y) :b y :c (match (variant Shape CIRCLE :r n) ((CIRCLE c) c.r) ((SQUARE s) 0))))` returns `b = 1`, also with `:c` written first. With an effect in `:a` the record is refused: a `let*` and a `match` are not simple (§4) |
| E1 | `(record R :b E2 :a E1)` logs `E2` then `E1`, and names its effects `#1` and `#2` bound by `let*` or not; a field that is an `if`, a `match`, a `let*` or an `and` over an effect, or that stands beside the effect, refuses with `effect_not_permitted` at that field; the same record in a `defun` or `list/map` body refuses; a run killed between the two field effects resumes with one dispatch; `(+ 1 (match …))` builds; `(+ (print 1) E (print 3))` prints after `E` |
| I1 | A map body of two bound effects, killed after the first effect of item 2, resumes with one dispatch; a body that is not one call refuses when a run reference reaches it by any route (written in it, a procedure reference, `bind-proc`, a local, a generic procedure, a macro, an imported workflow), and also when it reaches none and the program holds a run reference elsewhere; `:max` from a workflow input runs; with an effect in the source and in `:max`, the source's runs first (once E1 admits the first); a list of 3 under `:max 2` logs two calls and fails, and a run recorded before the change that failed there resumes to the same code; a computed `:max` of 0 returns the empty list over an empty list and fails over one item |
| I2 | Every rewritten source keeps its recorded digest; a run started before the rewrite resumes after it; a loop with an effect in both `:max` and `:state`, `:max` first, is listed, not reordered; in a template whose local has the loop state's name both forms read the state and build one program; a frozen Python build pinned before I2a still builds |
| C1 | A local called twice has two frames; each row of §6's table gets its message; an inner binding of the local's name is what `(f …)` calls; a local named like a `defun` calls the function; a procedure that forwards a reference parameter through `let*` and is never called still compiles |

## 10. Changes And Their Dependencies

No change may add a lowering route, a closed construct or an identity rule, or
move a digest in the corpus comparison of §9.

| Change | Where | Notes |
| --- | --- | --- |
| E1a, after the capture fix | `typecheck_dispatch.py`: delete the two field purity checks. `typecheck_loop_recur.py`: delete the exhaustion purity check, keep the run-reference guard | The three matching rules leave `cell_refusal` (`tests/workflow_evaluated_totality_helpers.py`) and `RULES` (`tests/workflow_lisp_totality_matrix_sources.py`) |
| E1b | `expressions.py` (`ListExpr`, `ListMapExpr`, `PathJoinUnderExpr`): one typechecker-set flag each, outside semantic identity as `item_type_refs` is. `typecheck_structural_values.py`: set it instead of refusing; delete the map-source check. `wcc/elaborate.py:_elaborate_expr_to_value`: when set, lower through `_elaborate_operands_to_values` | Select by the flag, not by `conditionals._contains_effect`, which counts every procedure call and would change the lowering of pure lists |
| E1c | `wcc/elaborate.py:_elaborate_operands_to_values`: an effect-free operand whose body is not linear becomes a block value | Only programs that are `compiler_defect` today change |
| I1 | `typecheck_structural_values.py`: refuse at typing a body that is not one call with pure arguments when its own summary contains a run reference, and record for every other map whether it has that shape; pass a typed `:max` as the synthetic loop's budget, in the order source then `:max`. `closed/build.py`: when the assembled closed program holds a run-reference effect, refuse the first map that is not one call with pure arguments or whose iteration runs more than one effect (§5). `expressions.py` (`ListMapEffectExpr`): an optional `max_expr` child, handled as `workspace_expr` is in `expression_traversal.py`, `procedure_typecheck.py` and `closed/names.py`. `closed/command_templates.py`: a parallel map written directly in a serial map or loop body is lowered as it is behind a procedure call | Keep the synthetic loop's `list_map_effect_cap_exceeded` code, which P12 reads; report a non-`Int` `:max` as `list_map_effect_max_invalid`. The runtime changes only where no program that compiled before reaches it (`workflow/evaluated/machine.py`): a serial map whose `:max` is below 1 and whose list is empty gets the one round that finds the list empty, and the cap failure says which bound the list passed |
| C1 | `expressions.py` (`_elaborate_list`, `_elaborate`), `compiler_session.py` and `workflows.py` (which names the module's workflows to elaboration): the local call and the second, third and fifth messages of §6. `procedure_typecheck.py`: the first. `typecheck_calls.py`: the fourth. `closed/build.py`: the cycle diagnostic. `typecheck_dispatch.py`: the refusal of a `let*` binding of a reference that is neither a literal nor forwarded | A local calling itself keeps `let_proc_recursive_unsupported`. The call by name is elaborated as the alias call under a reserved binding name, so it adds no route and no identity |
| I2a | `expressions.py`: the binder form beside `fn`. `macros.py`: the loop state, `let-proc` parameters and `cond` clause items as bindings or expressions of a template (§5). `scripts/migrate_orc_sources.py`: the one-target plan's header and clause migration with the loop rewrite of §5, for `.orc` files and for sources in Python strings under `tests/` and `experiments/` | One pass rewrites headers and loops and lists what it leaves. The Python frontend keeps emitting the `fn` form (I2b) |
| I2b, with the removal of the older targets | Delete the `fn` route, `LoopBodyFnExpr`, `:state`, `operand_evaluation_order` and the `fn` registry row. `orchestrator/py/emit.py`: emit the binder form | Under a recorded owner ruling (§12); the refusal names the rewrite. The emitter changes here, not in I2a, because a frozen Python build hashes the emitted text: a pin made before the change refuses (`python_frozen_changed`) until it is rebuilt, although the program digest is the same |

## 11. Where The Rules Live

This document is retired to Historical when the receiving sections below
carry the rules with their exception lists, the listed text is gone, and each
change of §10 is implemented or dropped; nothing may then cite it as authority.

Three things keep it current. Rule 1 has no receiving section until E1 is
merged. Rule 2's `fn` form, with its text in the specification's §13.1,
stands until I2b lands in the release that removes the older targets. The
guide carries none of the three rules. Rules 2 and 3 are in the
specification with their exception lists (§10.3 and §13.1; §7.8 and §14),
and `specs/versioning.md` has the entries of C1, I1 and I2a; where those
sections and this page differ, they state what compiles. Of the text listed
under rule 1 below, the two sentences of the specification's §10.3 left with
I1, and the guide's two serial-map sentences will state rule 2's
run-reference exception instead of leaving.

| Rule | [Frontend specification](workflow_lisp_frontend_specification.md) | [Guide](../lisp_workflow_drafting_guide.md) | Text that leaves |
| --- | --- | --- | --- |
| 1 | A new subsection of §16 "Effect System": the sentence, its exceptions, §4's order and identity | §18 "Effects", one paragraph | Specification: §9's list of where pure expressions "may appear"; §10.3's "exactly one supported effectful call" bullet and "general effectful map bodies … remain outside"; §13.1 from "This adds neither an exhaustion evaluator" through the "Required behavior" list. Guide: the §2A rows "Pure contexts" (loses `:on-exhausted`) and "Serial `list/map-effect`"; §17.2's restriction paragraph |
| 2 | §13.1 "Bounded Loop": the form, the order, the `fn` form until removed. §10.3: the map forms and their exceptions | §17 "Loops" opens with it; its two loop examples use the binder; §17.2 and the §2A row on serial maps state the run-reference exception | Specification: §13.1's `fn` block and "Lowering options", with I2b. Guide: nothing more; §17.3's literal sentence stays true |
| 3 | §14 "Workflow Calls": the two conventions. §7.8 "Procedure References": locals called by name, the exceptions, what a local's name reaches | §6 opens with it | Specification: §7.8's paragraph on V1 `let-proc` and `(proc-ref local-name)`. Guide: §16's two paragraphs on references become a pointer to §6 |

| Document | Change | Becomes Historical |
| --- | --- | --- |
| `specs/dsl.md` | It has no section for these forms and gains none. In "Workflow Lisp rich loop values": "not an exhaustion-time evaluator" and "arbitrary computed/effectful exhaustion expressions remain unsupported" become "`:on-exhausted` is an expression evaluated on exhaustion with the last state in scope; top-level Optional/Map state remains unsupported". In the run-reference placement note: "exhaustion guards and other pure contexts stay pure" becomes "a run reference stays refused in `:on-exhausted`, a map source and the pure places" | No |
| `specs/versioning.md` | The same run-reference sentence; one compatibility entry per change under "Source admitted without a new target (surface coherence)", none moving an identity of source that still compiles; C1's entry states its one refusal; the macro templates of §13 are not in I2a's entry | No |
| [List traversal](workflow_lisp_pure_list_traversal.md) (historical record since 2026-11-14) | I1 corrected the body, `:max` and code sentences of "Bounded effectful binder" in place; the section leaves with the document | Done: the specification's §10.3 carries its operator, constructor-typing, `list/map` and `path/join-under` rules and no longer defers to it |
| [let-proc](workflow_lisp_let_proc_local_proc_refs.md) | §7.3 and §27.2 are reversed by §6 here | When the release that removes the older targets removes the V1 form it specifies; write once §6.3 and the specification's §7.8 are then the contract |
| [Composition first](workflow_lisp_composition_first.md) | Loses §11.1's rule on pure fields and `:on-exhausted` and §11.3's `on-exhausted-call-edge` row | No |
| [Evaluated execution](workflow_lisp_evaluated_execution.md) | §1.2's map-body sentence states rule 2's run-reference exception (done with I1); §1.2's "`:on-exhausted` remains a pure projection" keeps only the run-reference guard; §4.3's argument-position bullet points to the specification's §16; with I2b the keyword-order sentences of its last bullet go | No |
| [Tutorial](../tutorial_first_pipeline.md) | With the rewrite of I2 (the one-target plan's sweep), `grow.orc` uses the binder form; the rewrite does not move its digest | No |

## 12. Prerequisites And Open Decisions

| # | Item | Blocks |
| --- | --- | --- |
| 1 | The capture defect of §2.1 is fixed, with the scenario of §9, so that both constructor routes rename hoisted bindings and name a field's effects alike | E1 |
| 2 | The forms that are registered but refuse are deleted (one-target plan). Otherwise four fixtures that put `materialize-view` or `resource-transition` in a newly admitted position stop refusing in the typechecker and refuse later as `closed_program_gap` | E1 |
| 3 | A recorded reading of the versioning rule's "a change … to whether it compiles adds a target". E1, I1 and C1 admit source that is refused today and change no source that compiles; this design reads the rule as protecting source that compiles, so they add no target. Under the literal reading each adds one. **Ruled 2026-11-12: this reading holds;** the one-target plan's rule 2 is worded accordingly | E1, I1, C1 |
| 4 | The owner ruling that the release removing the older targets also removes the `fn` form. Without it both forms stay and rule 2's `fn`-form exception has no end. **Coordinator default, 2026-11-12: removed in that release;** the owner may keep both forms until it lands | I2b |
| 5 | The `bind-proc` defect of §2.1; it belongs to pure-call composition, not to this design | Nothing; rule 3 names it until fixed |
| 6 | A run-reference map body with several producers; owner: evaluated execution §1.2. Before it, an analysis of each map iteration that is sound for imported workflows (their effect summaries are an open defect), so that a program holding a run reference may use general bodies where no run reference is reached | Only rule 2's run-reference exception |

## 13. Departures From The Accepted Text (2026-11-13)

C1, I1 and I2a merged on 2026-11-13 after their reviews; the E1 rows state
what its branch holds. Each row is a place
where the merged change differs from the text accepted on 2026-11-12, with
the ruling that decided it; the sections above state the rule as merged.

| Change | Departure | Decided by |
| --- | --- | --- |
| C1 | A local named like a `defun` or a built-in form does not shadow it, and its call by name is then not its alias call (rule 3, §6) | Coordinator ruling on finding M1 of the first callables review: keep and state it; refusing such a local at its definition goes to the release that removes the older targets |
| C1 | A `let*` binding of a reference that is neither a literal nor forwarded is refused with `proc_ref_literal_required`, also in a procedure that nothing calls: the one place where C1 refuses source that compiled (rule 3, §6, §8) | Finding M3 of the first callables review for the refusal; coordinator ruling MA2 on the second review for the never-called procedure, stated in C1's versioning entry |
| C1 | A workflow cycle is refused only for workflows the entry reaches, and a cycle through a procedure or a workflow reference parameter is reported as that procedure's cycle; the message for `(w n)` is not given for a module-qualified name or in a compile with imported workflow bundles (rule 3, §6) | First callables review, minors m4 to m6, applied in the round the coordinator ruled on and stated in the specification's §14 |
| C1 | Caller code passed to a macro can call the template's `let-proc` local by name: hygiene does not rename that binder, and the alias form already reached it | Coordinator ruling MA1 on the second callables review: accepted; the fix changes macro programs that compile and goes to the release that removes the older targets |
| E1 | In a simple value no procedure call is simple, a call's arguments and a `let-proc` local's body admit nothing new, and a run reference is not simple: an effect behind a `defproc`, a `let-proc` local or a `defun` call is bound with `let*` first, as before E1. The examples of §4 call workflows (rule 1, §4) | Coordinator adjudication of the fifth effect-placement review (2026-11-13), findings B1 to B3 and J1: programs `main` refuses by name must not reach an older defect or rename an effect; where a pure and an effectful callee cannot be told apart at the point of the check, no procedure call is simple |
| E1 | A field, a list element, a path child, a map source and `:on-exhausted` take an effect only in a simple value; every other value there stays refused with its earlier code. The accepted text admitted any expression ("nothing becomes refused" still holds: no program that compiled is refused) (rule 1, §4, §8, §9) | Coordinator ruling A on the fourth effect-placement review (2026-11-13): effect names must not depend on whether a `let*` binds the value or on a pure edit beside the effect, and what cannot guarantee it is not admitted |
| E1 | A `continue` value with a conditional, a loop or a map below its top is refused with `effect_not_permitted` where it was a `compiler_defect`, also when it is an `if` whose branch is an `if` or `cond` holding a command or an effectful call of a workflow, a `defproc` or a `let-proc` local (defect backlog D19); a `match` subject whose effect lowers to a join runs as its `let*`-bound spelling (D20), and a subject holding a `cond` the compiler reaches builds, with a map in its argument too; a subject with a map and no `cond` stays a `compiler_defect` (rows D20-map-argument, D4-subject-argument, D20-let-proc-subject open); a parallel map whose binder a macro template introduces stays refused when its source holds an effect | Rulings B and C on the same review: no program that builds on `main` is refused, and a program `main` refuses by name is never left in a defect; the two older defects were listed, not fixed; the defect backlog plan's Task TD1 fixed them |
| I1 | The run-reference exception covers the program, not the body: general bodies only in a program that contains no run reference (rule 2, §3, §5, §10) | Coordinator ruling after the third map-bodies review (its findings R2-B1 and R2-M1): the per-iteration decision was unsound for imported workflows |
| I1 | The runtime changes for a serial map with a `:max` below 1 over an empty list, and the cap failure names the bound passed (§5, §10) | Coordinator ruling 4 on the first map-bodies review |
| I1 | A parallel map may be written directly in a serial map or loop body | Finding M1 of the first map-bodies review, fixed instead of refused; it was a `compiler_defect`, so no program that compiled moves |
| I2a | The Python frontend's emitter change moved to I2b (§3, §10) | Coordinator ruling on concern 1 of the loop-binder report: a frozen pin hashes emitted text |
| I2a | The migration tool rewrites by a syntactic rule first and by a hash comparison only inside an exported workflow of a source that builds; it reads Python only under `tests/` and `experiments/` (§5) | Coordinator rulings 1 to 7 on the first tool report; finding R3 of the third loop-binder review |
| I2a | Macro hygiene for the loop state (both forms), `let-proc` parameters and `cond` clause items; a template that bound such a name itself changes value and digest (§1, §5) | Kept by the coordinator at the merge (one-target plan ledger, 2026-11-13: the three kept classes). Ruling 2026-11-13: kept as a correction of a silent wrong value and stated as an exception in the I2a entry of [`specs/versioning.md`](../../specs/versioning.md); not moved to the cut |
| I2a | No rename of a name at the head of a list in a template | The coordinator withdrew its own round-2 ruling after the third loop-binder review; head-position hygiene is an open defect |

Changes that the reviews assigned to the release that removes the older
targets, because each stops source from compiling, changes its meaning or
moves an identity, are listed in the
[one-target plan](../plans/2026-11-12-lane-d-stage-4-one-target-plan.md#changes-assigned-to-the-cuts-release-on-2026-11-13-not-yet-sized);
they are not changes of this design. The open defects these rules meet are on
the [roadmap's list](../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#lane-d-delete-and-unify-background-time-boxed);
a sentence here that one of them contradicts says so where it stands.
