# Workflow Lisp Staged-Workflow Authoring: Prompt Values, Roles, Timeouts, Lists

- **Status:** Designed (proposed), not implemented. Revised 2026-11-13 after
  an independent review (accept after fixes: 0 blockers, 8 majors, 11 minors)
  and the coordinator's rulings on it. The compiler behaves as the "Result on
  `main`" column of §2; the "after" examples do not compile on `main`.
- **Kind:** language revision. **Created:** 2026-11-13.
- **Direction fixed by the owner** (roadmap decision 15): a typed prompt is a
  first-class value and a role is a generic procedure wrapping
  `provider-result`, partially applied with `bind-proc`; no `role` form. This
  document designs that and reports what it costs (§4.8, §15).
- **Owns, until retired (§14):** what a prompt application denotes outside
  `:prompt`; `Prompt[T]` and `Provider` as parameter types; a call through a
  reference bound over a generic procedure; the `:timeout-sec` operand; the
  typed list literal; three list operators.
- **Records, as deferred and not as rules (§8):** a snapshot fill for living
  documents; an `Agent` bound into a role; prompt values bound by `let*`.
- **Consumes:** [surface coherence](workflow_lisp_surface_coherence.md) (its
  three rules; changes E1, I1, C1, I2a);
  [evaluated execution](workflow_lisp_evaluated_execution.md) §6, §7.2, §8;
  [Agent Sessions](workflow_lisp_agent_sessions.md);
  [closures boundary](workflow_lisp_runtime_closures_boundary.md) §4, §5;
  [edit and continue](workflow_lisp_edit_and_continue.md) §2, §3; the
  [frontend specification](workflow_lisp_frontend_specification.md) §36; the
  versioning rule of the [one-target plan](../plans/2026-11-12-lane-d-stage-4-one-target-plan.md#the-versioning-rule).
- **Plan:** [staged-workflow authoring revisions](../plans/2026-11-13-staged-workflow-authoring-revisions-plan.md).
- **Evidence:** branch `spike/authoring-revisions`, `experiments/authoring_revisions/`:
  probes, a compiler prototype of every change kept here, stand-in runs. No
  provider or model was called. Cost in this document means priced tokens,
  never a count of calls.

## 1. The Rules

Six things were awkward when a compact staged workflow (guides, spec, plan,
milestones with check and review, acceptance) was written in fewer than 50
lines. Each was reproduced before anything was decided (§2). Five rules
follow from them. Each is one sentence here; its exceptions are listed once,
in the section named.

1. **Prompts are values.** A fully applied prompt, `(work :repo repo …)` with
   `work` declared `-> Change`, is a value of type `Prompt[Change]`: it can be
   passed to a `Prompt[T]` parameter of a procedure, and `(provider-result who
   :prompt p)` with `p` that parameter is a call of type `T` (§4.1).
2. **A role is a procedure with its arguments bound.** `(coding (bind-proc
   (proc-ref ask) :who providers.coder :model m :effort e :timeout 3600))`
   binds a role and `(coding (work …))` calls it, because a provider extern
   can be passed to a `Provider` parameter and a reference bound over a
   generic procedure infers the type parameters at each call (§4.4).
3. **A timeout is a value.** `:timeout-sec` takes an `Int` literal, name or
   field, as `:model` and `:effort` take a `String` (§5).
4. **An empty list states its item type where its position does not:**
   `(list :of String)` (§6).
5. **Three pure list operators:** `(list/take xs n)`, `(list/all bools)`,
   `(list/any bools)` (§7).

No program that compiles today changes its closed program, program digest,
effect identities or behaviour (§11).

## 2. Verified Findings

Target 2.40, public command line, stand-in commands and the scripted `claude`
of `tests/agent_session_shims.py`. Class: **(a)** needed for a stated
guarantee, **(b)** unimplemented case, **(c)** historical accident. Paths are
under `orchestrator/`; `wl/` is `workflow_lisp/`. The review reran every row.

| # | Claim | Result on `main` | Decided in | Class |
| --- | --- | --- | --- | --- |
| 1 | A role cannot be bound once for fresh calls | Reproduced, and narrower than stated. `agent` binds model and effort only (`agent_keyword_invalid` for `:timeout-sec`) and a turn refuses both (`agent_turn_policy_override_forbidden`). A procedure per prompt, bound with `bind-proc`, already is a role: it compiles, runs and gives each call site, loop round and map item its own identity. The Python frontend binds a role today (`Provider(name, model=, effort=, timeout_sec=)`) and emits the call in place | `wl/typecheck_effects.py:typecheck_provider_result_expr`; `wl/typecheck_agents.py` | — |
| 1a | A prompt is not a value | `Prompt[T]`: `generic_union_not_generic`. A `Prompt` parameter in `:prompt`: `frontend_parse_error`. An application outside `:prompt`: `procedure_call_unknown`. A fill operand is a literal, a name or a field path (`prompt_fill_identity_unsupported` otherwise) | `wl/expressions.py:_elaborate_provider_result`; `wl/prompts.py` | (b) |
| 1b | A provider extern cannot be an argument | `provider_result_provider_invalid` for a `Provider` parameter, a generic one and a `let*` alias | `typecheck_provider_result_expr` | (b) |
| 1c | A reference to a generic procedure is not generic | `(bind-proc (proc-ref pick) :n 1)` then `(keep x)`: `type_mismatch` "expected `T`". A direct call instantiates. An uncalled reference of this kind compiles; passing one to a `ProcRef` parameter refuses (`proc_ref_signature_invalid`) | `wl/procedure_typecheck.py:typecheck_procedure_call_expr` | (b) |
| 1d | An `Agent` cannot be a `bind-proc` argument | `let_proc_capture_agent_forbidden`, also when written explicitly | `wl/procedure_refs.py:resolve_proc_ref_value` | (a) Agent Sessions: the handle is authority and never enters a parallel worker (§8.2) |
| 1e | A macro cannot wrap the call | `macro_hidden_effect` for a `provider-result` written in the template. A template that calls an effectful procedure or a bound reference compiles and runs (`(defmacro m1 (a) (goe a 2))`, `(defmacro m2 (f) (f 2))`) | `typecheck_provider_result_expr` | (a) kept as the specification's §36 states it (§4.7) |
| 2 | A timeout must be a literal | Reproduced for a provider call and an agent turn (`provider_result_timeout_literal_required`). Enforced three times: typecheck, the closed check and the phased runtime. A composed call already launches with the resolved policy value | `typecheck_provider_result_expr`; `contracts/closed_program/check.py:_check_effect_node`; `workflow/evaluated/phased_providers.py:capture_phased_deadline` | (c) composed; (a) phased: the deadline starts before input reads |
| 3 | An empty list needs a type carrier | Reproduced, and wider. Refused (`list_empty_type_context_required`): a loop's initial state, a `let*` binding, a `continue`, `done` or `:on-exhausted` value, a `defun` argument, a `list/append` or `=` operand, a map source. Accepted: a record or variant field, a procedure or workflow argument, a workflow result, an `if` arm, a loop-state field | `wl/typecheck_structural_values.py:typecheck_structural_value_expr` | (b): the expected type is passed to some positions only |
| 4 | A `:doc` fill on a living document blocks `resume` | Reproduced, and worse with a conversation. A later step rewrote `docs/plan.md`; after a kill `resume` exits 2: `effect_input_diverged … ['dependency:docs/plan.md', 'prompt']`, with a plan that cancels the step that read it and every later one. The same text appears for an edit from outside. When the reader is an agent turn, "no plan can be accepted: `invalidate_coordinator_committed`" and the run cannot continue. With `:path` both cases resume and neither is noticed | `workflow/evaluated/effect_inputs.py:_reuse_effect_commit`; `providers.py:resolve_provider_input` | (a) resume determinism (C6, C7); deferred (§8.1) |
| 5 | Nine milestones run eight, then fail | Reproduced: eight items, then exit 1, `list_map_effect_cap_exceeded`. Correction: `list/length` exists, so a program can refuse a long list before the map today; it cannot shorten one | `wl/typecheck_structural_values.py` (the map's synthetic loop); `workflow/evaluated/machine.py:_loop` | (a) frozen: a run recorded past that point must resume |
| 6 | A list cannot be reduced | Reproduced: no `list/all`, `list/any`, fold or membership; `=` on lists is refused; a cursor loop over `list/rest` works in a workflow or procedure body and not in a `defun` | `workflow/pure_expr.py:PURE_EXPR_OPERATOR_CATALOG` | (b) |

Defects found on the way. None is designed here; the plan's Task 0b owns
those the seeds meet.

| # | Program | Result on `main` |
| --- | --- | --- |
| D1 | A `list/map` whose body is a `match`, used in an `if` condition inside a loop body | `compiler_defect` (`KeyError`); binding it with `let*` first compiles |
| D2 | `(list)` in a `match` arm | `compiler_defect` ("typed list is missing its resolved child types") |
| D3 | A generic procedure called in a `list/map-effect` body | `procedure_call_unknown`, naming an internal specialization; also on the I1 branch. A role call in a map body is such a call |
| D4 | A procedure reference chosen by `if` | `compiler_defect` (`KeyError`); on `feat/coherence-c1` it is `proc_ref_literal_required` |
| D5 | A `bind-proc` written inside a procedure over one of its parameters, passed to a `ProcRef` parameter | `procedure_lowering_unresolved` |
| D6 | `(list :of String)` | An uncaught `TypeError` traceback (a keyword in a positional form; C1 gives that one diagnostic) |
| D7 | A provider extern used as a value in reached code: bound by `let*`, put in a record, passed to a procedure, chosen by `if`, returned | `compiler_defect` after typecheck. A definition that only names the type `Provider` and is not reached compiles |

Also measured: a workflow input takes a literal default (`(coder String
:default "claude-haiku-5-5")`), not a name; a call with no model on a
template that needs one fails at run time (`provider_preparation_failed`).

## 3. Decision

In the order the plan takes them. Sizes are measured on the prototype.

| # | Change | Rule | Compiler | Value |
| --- | --- | --- | --- | --- |
| T | `:timeout-sec` takes a name or a field | 3 | 3 files, +25 | A timeout as an input; a role needs it |
| O | `list/take`, `list/all`, `list/any` | 5 | 4 files, +35 | The cap can be met; verdicts can be read |
| L | `(list :of T)`; expected type to `continue`, a `defun` argument, a `match` arm | 4 | 2 files, +30 for `:of` | One line less in each seed; no carrier |
| P | Prompt values as arguments; `Prompt[T]` and `Provider` parameters; a called reference over a generic procedure; `std/ask` | 1, 2 | 12 files, +270, built and run end to end (§11) | A fresh call is one line; a role's model, effort and timeout are written once |

Deferred, with what is lost (§8): the snapshot fill; an `Agent` bound into a
role and `ask-agent`; prompt values bound by `let*` or `bind-proc`; a `let*`
alias of a provider; a role passed to a procedure. Not done: a fold, an
option on the map for a long list, a `role` form, a conversation option on
`agent`, an effect written in a macro template.

## 4. Prompt Values And Roles

```lisp
;; today: every call repeats the role
(change (provider-result providers.coder :model coder :effort effort :timeout-sec 3600
          :prompt (work :repo repo :milestone m :notes notes)))
;; after
(coding (bind-proc (proc-ref ask) :who providers.coder :model coder :effort coder_effort :timeout 3600))
(change (coding (work :repo repo :milestone m :notes notes)))
```

### 4.1 Prompt values

`Prompt[T]` is formed by applying a `defprompt` declared `-> T` to every slot
exactly once (the existing `prompt_fill_*` and `prompt_slot_*` codes). Bare
`Prompt` stays the type of an extern prompt name. Rule 1 holds with these
exceptions:

- **A prompt value exists only as an argument.** It is written at a call
  whose parameter is `Prompt[T]`, and inside the callee that parameter is
  passed on to another such call or given to `:prompt`. Every other position
  refuses with `prompt_value_escape`: a `let*` binding, a `bind-proc`
  argument, a record or variant field, a list element, loop state, the value
  of `if` or `match`, a procedure result, a `defun` argument, a workflow
  input or result, command or provider data.
- **Where the types may be written.** `Prompt[...]` is the type of a
  `defproc` parameter and of nothing else: in a record or union field, inside
  `List`, `Optional` or `Map`, in a `defworkflow` or `defun` signature, as a
  procedure's result type, as a loop state or inside `ProcRef[...]` it
  refuses with `prompt_value_escape`. `Provider` is an existing type name and
  stays accepted wherever it is written today, so a definition that only
  names it keeps compiling; the rule for it is on values (§4.4). A type
  parameter is never instantiated to either: `(keep (work …))` with `keep
  :forall (T) ((x T)) -> T` refuses with the same code.
- **The head.** `(name :slot value …)` where `name` is a visible `defprompt`
  is a prompt application wherever it is written, whatever else has that
  name. Outside `:prompt` there are two exceptions: when `name` is also a
  language form or an operator, the form is that form or operator; and a
  prompt without slots, `(name)`, is the call when `name` is also a binding,
  a procedure or a function. Both exist so that no program written before
  this rule changes its meaning (§11).
- **Fills.** A fill operand is a literal, a name or a field path
  (`prompt_fill_identity_unsupported` otherwise), so writing an application
  evaluates nothing. Files are read at the call
  (§4.3).
- **Unchanged:** an extern prompt name with `:inputs` and `:returns`; a
  partial application (`prompt_partial_application_unsupported`); a phased
  call and a `request-input` question take the application written in place,
  and a prompt parameter there refuses.

A prompt value is data, not code: it holds a declaration and fill operands,
and storing one would breach nothing in the closures boundary. It is
compile-time here for a different reason: every prompt value is removed by
specialization, so the checked program holds no value of type `Prompt[T]`
and its value format does not change.

### 4.2 How it compiles: owner, name, identity

A procedure with a `Prompt[T]` or `Provider` parameter is specialized for
those arguments as one with a `ProcRef` parameter is. For each distinct
wrapper, type arguments, prompt declaration and provider extern, the checked
program holds one ordinary procedure. Its parameters are the wrapper's value
parameters and one per fill; its `provider-result` node holds the prompt's
template and the extern's provider. No checked construct, node kind or
identity rule is added.

**Owner.** The specialization is a definition of the wrapper's module, as a
library generic procedure specialized with a caller's type or procedure
reference is today. Nothing is resolved against the owner afterwards: a
`defprompt` template is inline in the node and has no source file, and the
fill types are already resolved.

**Name.** The checked key of a definition is its module, kind, declared
name, type arguments, procedure and workflow references, closed values,
captures and signature. It has no component for a prompt or a provider, so
two prompts with equal slots and result type, or one prompt asked of two
externs, gave one key (measured: `compiler_defect`, "contradictory prepared
bodies"). The specialization therefore carries both in its declared name,
`wrapper<prompt@extern>`, with the prompt's qualified name and the extern's
name. The key format does not change, and no definition of a
program that compiles today has such a name. `report` and the dashboard then
show which prompt was asked of which provider:

```text
workflow:milestones::run / loop:notes[1] / plan=procedure:std/ask::ask<milestones::plan@providers.planner>[<64 hex>] / #1
```

The name is identity, not only display. Renaming a prompt, or pointing a role
at another extern, moves the identities of that role's calls; they run again
in either case, since the node changes. A prompt's text, a role's own name,
and its model, effort and timeout move no identity. Shortening the bracketed
digest in displays is outside this design.

**Measured on the prototype** (a wrapper in a library module, three roles,
nine calls: three in sequence, two map items, four in two loop rounds; the
`pv_*` scenarios):

| Question | Result |
| --- | --- |
| Identity of a role call | The identity of the same call written in place, followed by `=procedure:lib::role<work@b>[…] / #1`: `first=…`, `loop:round[2] / again=…`, `mapped / body / loop:#1[1] / else / #1=…`. Nine calls, nine identities |
| The role's name | Contributes nothing: it is a `let*` name |
| Prompt text and the `policy` part | Equal, step for step, to the program written in place |
| `declaration` | The position-free digest of the specialization's node, as for any provider: three specializations, three values. A role's model, effort and timeout are arguments of the call, so they reach `policy` and `values`, not the node |
| A kill inside a role call | `resume` dispatches that call once |
| One role's literal edited after the run | No identity and no `declaration` moves. Plain `resume` prints a plan whose cut is that role's first committed step ("its input changed (parts: policy, values)"). Commits before it are kept and everything after it is cancelled, whatever its role (C10's suffix rule) |
| An input's default edited | No plan: `resume_inputs_changed`. A run's inputs are fixed for its life |

### 4.3 When files are read

Files are read when the effect that uses the prompt resolves its input, at
each attempt's start (C6). A prompt value holds a path, never bytes. Only an
effect has an identity under which a read is recorded and replayed; a prompt
value has no site and advances no ordinal (I4). The parts
`dependency:<path>`, `dependency_rows` and `prompt` therefore belong to the
call, as today, and a prompt parameter given to two calls is read by each.

### 4.4 Roles

```lisp
(defproc ask :forall (T) ((who Provider) (model String) (effort String) (timeout Int) (prompt Prompt[T])) -> T
  (provider-result who :model model :effort effort :timeout-sec timeout :prompt prompt))
```

`std/ask` exports `ask`. Use: `(import std/ask :only (ask))`, then one line
per role. Rule 2 holds with these exceptions:

- **A `Provider` argument is the name of a provider extern,** or a `Provider`
  parameter passed on. A provider is a value nowhere else: bound by `let*`,
  put in a record or a list, chosen by `if` or returned, in code the entry
  reaches, it refuses with `prompt_value_escape` (D7: a `compiler_defect`
  today).
- **A reference over a generic procedure is called where it is bound.**
  `(name (bind-proc (proc-ref g) :x operand …))` in a `let*`, with `g`
  generic, may be called by name in the scope of that `let*`; each call
  infers `g`'s type parameters from its arguments, as a direct call does. Its
  operands are evaluated once, at the binding, in the binding's scope.
  Otherwise it follows the rules of every reference: a bound argument's type
  may not mention a type parameter (`proc_ref_binding_type_invalid`), passing
  the reference to a `ProcRef` parameter refuses
  (`proc_ref_signature_invalid`), and choosing one with `if` refuses
  (`proc_ref_literal_required`, with C1).
- **`ask` takes all four options.** A role without one (the template's
  default model, no timeout) uses another wrapper, two lines of the author's
  own; that is what ordinary partial application is for.
- **No reference crosses `call`,** so a workflow binds its own roles from
  its inputs.
- **An agent turn is written in place:** `(provider-result an-agent
  :timeout-sec … :prompt …)` (§8.2).

How it compiles: the `let*` binds each operand that is not a literal or an
extern name once, under a compiler name, before the reference; a call through
the reference is the direct call of `g` with those names and the call's own
arguments. Measured: a name bound into a role and rebound before the call
keeps its binding-site value; without the pre-binding the rebound value was
launched. Only a reference that is called is rewritten. An uncalled reference
over a generic procedure compiles today, and it keeps its digest (measured).

### 4.5 Metering and the spend cap

The cap is checked before each attempt from the resolved policy
(`workflow/evaluated/spend_cap.py:check_spend_cap`): the model value, or the
template's default, must have rates in the price table. Measured through a
role, with a metered template and a stand-in that reports usage, under
`--max-cost-usd`: each attempt's `usage.json` and the run's and steps' usage
in `report` equal those of the program written in place; an unpriced model
refuses with `spend_cap_unmetered` (`model_unpriced`) before launch. The
timeout does not enter metering.

### 4.6 Typed prompt inputs, prompt identity, the Python frontend

An application written in `:prompt` takes the same path through
`wl/prompts.py`, the fragment renderers and the checked node as today; the
plan's invariant checks gate that. In a specialization each fill reads a
parameter, which the fill-identity rule already admits. The Python frontend
needs no change: its `Provider` object already carries model, effort and
timeout and emits the call in place.

### 4.7 Macros

The rule of the frontend specification §36 is unchanged and this design
amends nothing in it. A provider or command effect written in a macro
template is a hidden effect and refuses (`macro_hidden_effect`). The same
effect written by the caller and passed through the macro is the caller's,
and a call that the template introduces is checked as usual. A macro whose
template calls an effectful procedure or a bound reference therefore
compiles (measured on `main`), and so does `(defmacro as-coder (p) (coding
p))` over a role: the effect is the procedure's, with its frame and its effect summary.
What stays refused is `(defmacro as-coder (p) (provider-result … :prompt p))`.

### 4.8 Alternatives not taken, and what the chosen one costs

| Alternative | Why it lost |
| --- | --- |
| A provider binding with options, `(provider providers.coder :model … :timeout-sec …)`, used as `provider-result`'s first operand | A new form and a second way to bind policy beside `agent`. It is the cheapest (about 2 days: an alias expanded at each call, the checked program of today) and is what the Python frontend does at generation time |
| `agent` with `:conversation fresh` | One form, but the option changes the effect class of every turn (coordinator or not) and what `invalidate` may cancel; the checked class of a turn would depend on a value |
| A `role` form | A form whose only content is partial application |
| A record of call options spliced into calls | Possible today for model and effort (`:model r.model`); it shortens nothing at the call |
| A macro whose template writes the call | `macro_hidden_effect`, kept |
| General generic references (passed, re-bound, instantiated at a `ProcRef` type) | The bound-reference path has three open defects (D4, D5 and the one surface coherence names); the role idiom needs only a reference called where it is bound |

The prototype shows the chosen design needs three capabilities that were
known (a prompt as an argument; `Prompt[T]` and `Provider` parameters; a
called reference over a generic procedure) and two that were not: the
specialization's name must carry the prompt and the extern (§4.2), and a
generic call in a map body must compile (D3). With those it is about 44
hours against about 16 for the provider binding. It saves one or two
lines in a seed with fresh calls and nothing in the seed with conversations
(§11); its lasting value is that prompts become arguments and that a
reference over a generic procedure can be called. Nothing in it breaks a
guarantee.

## 5. Timeouts

```lisp
;; today: provider_result_timeout_literal_required
(provider-result providers.coder :model coder :effort effort :timeout-sec limit :prompt (work …))
```

The operand is typed `Int` and is a literal, a name or a field with no
effect. Exceptions:

- **Phased delivery keeps a literal:** its deadline is read from the checked
  node before any input is resolved.
- **Not a computed expression:** bind it first, as for `:model`.
- **A value below 1** from a name or field refuses the step when it resolves
  its input, with `provider_timeout_nonpositive`: nothing is launched and no
  `started` record is written. A literal is checked at compile time.

The value enters the `policy` part and, as an operand shape, the
`declaration`; a timeout that changes between a run and its resume diverges
the step, as a changed model does. An agent turn takes the same operand.

## 6. Empty Lists

```lisp
;; today: (loop/recur :max 2 :state (loop-state (notes List[String] (list))) … (fn (state) …
;;          (continue (loop-state :like state :notes gap.reasons))
(loop/recur ((notes (list :of String))) :max 2 :on-exhausted …
  … (continue gap.reasons))
```

A position that already states the item type keeps supplying it: a field, an
argument, a workflow result, the other arm of an `if`, a loop-state field, a
`continue` value, a `defun` argument and a `match` arm. The last three are
added by this design (the `match` arm is D2).

- **`:of` is allowed on a non-empty list** and checks its items.
- **`(list :of T)` where the position states `T`** builds the program of
  `(list)` (measured: equal digests); a mismatch is
  `pure_expr_operand_type_mismatch`; `(list :of)` is `list_item_type_invalid`.
- **`loop-state`** remains for a state of several named fields.

Weighed: an annotation on the binder (`((notes List[String] (list)))`) fits
only loops and adds a third shape to rule 2's binder of surface coherence;
inference from the `continue` values needs unification the checker does not
have. A typed literal is one spelling for every position and reads naturally
in the binder. The checker already records an item type on every list; `:of`
sets it before typing.

## 7. Lists And The Map Cap

```lisp
;; today: nine milestones run eight, then the run fails
(built (list/map-effect ((m (list/take plan.milestones 8))) :max 8 …))
(met (list/all (list/map ((v built)) (match v ((MET e) true) ((NOT_MET g) false)))))
```

- `list/take xs n`: `List[T]`, `Int` to `List[T]`; the whole list when `n`
  exceeds its length, the empty list when `n` is below 1.
- `list/all`, `list/any`: `List[Bool]` to `Bool`; `true` and `false` on the
  empty list.
- All three are pure operators of the list group: usable in a `defun` and in
  a `list/map` body, no site, no identity, no provider call. Each is bounded
  by the length of its operand, a value already held.

Exceptions: **the serial map's cap is unchanged** (`:max` items run, then
`list_map_effect_cap_exceeded`); **left out** are a general fold (the
iteration binder has one name and a fold needs two; no seed needs one) and
`list/filter`, `list/contains?`, `list/concat` (the check "every target is
claimed by a milestone" needs all three and stays with the reviewer).

An author has three ways to meet the cap, each an explicit choice: take the
first `n` (`list/take`); refuse a long list before the map (`list/length`,
today); or, with I1, make the list's own length the budget
(`:max (list/length xs)`). An option on the map for a long list was weighed
and dropped: a keyword with two modes where two pure operators serve, on a
form whose recorded behaviour must not move.

## 8. Deferred

Recorded so the next reader does not start from zero. None of this is an
accepted rule and none has a task.

### 8.1 Document fills on living documents

**Problem.** A `:doc` fill makes the file's bytes an input of the step. On
resume every committed step's input is resolved again from the workspace and
compared (C7). That is right for a file nothing in the run changes. For a
document the run itself rewrites, the journal is exactly what an
uninterrupted run produces, and the check fails only because it reads
today's bytes for a step that read yesterday's (§2, row 4).

**Designed rule.** A slot kind `:snapshot`, delivered like `:doc`: the
attempt retains the bytes it read, under their digest, at `started`; every
later comparison for that step reads the retained bytes after they verify,
and never the workspace. It is the confined profile's attempt-snapshot
binding (evaluated execution §7.3) applied on host runs to a slot that asks
for it. `:doc` would keep today's refusal. The slot gives up, for itself,
the report of an edit made from outside between runs, as `:path` does today.

**Why it is not accepted.** The review found the rule incomplete. An agent
turn that completed natively and was killed before its commit is recovered
by resolving its input from the workspace
(`workflow/evaluated/agent_turn_recovery.py:_recovered_attempt`), so a turn
that rewrote its own snapshot document still diverges: the stranding the
rule was meant to remove. A new attempt after an uncommitted provider
attempt also reads the workspace, which the killed attempt may have half
rewritten, as with `:doc` today. A complete rule covers every comparison
with a recorded `started` (commit reuse, pending-turn recovery, the
edited-program plan). `:path` already delivers a living document without
blocking `resume`, and no search dimension needs content delivery yet.

**Standing guidance.** Pass the path (`:path`), or name the document in the
prompt, for any document a later step edits. Use `:doc` only for documents
nothing in the run writes. Never use `:doc` on a living document read by an
agent turn.

### 8.2 An agent bound into a role

**Designed rule.** An `Agent` may be an explicit `bind-proc` argument, and
the library has a second wrapper, `ask-agent`, with the parameters `(who
Agent) (timeout Int) (prompt Prompt[T])`, since an agent turn takes no
`:model` or `:effort`. Two guards keep Agent Sessions' rules: the
reference's agent origins are those of the bound value, and a reference that
holds an `Agent` is refused in a parallel worker exactly where an `Agent`
is, also when it is forwarded through a `ProcRef` parameter or bound again.
`let-proc` capture stays refused. It amends one sentence of Agent Sessions.

**What is lost by deferring.** Switching a role between a fresh call and a
conversation stays an edit of each of its call sites (§9). No current seed
or search space needs it, and in the seed that uses conversations it adds
lines, because `agent` already makes each turn one line.

### 8.3 Prompt values bound by `let*` or `bind-proc`, provider aliases, a role as an argument

None is free with the rest. A `let*`-bound prompt needs a binding that
exists at compile time only and is erased before lowering; a prompt bound by
`bind-proc` needs the same for a reference; a `let*` alias of a provider
opens the escape through `if`; a role passed to a procedure needs
`Prompt[...]` inside `ProcRef[...]` and the bound-reference path with its
open defects. What is lost: naming one prompt and asking it of two roles
(write the application twice); a helper procedure that takes a role (it
takes the model, effort and timeout and binds its own).

## 9. What A Search Mutates

The declared dimensions of the seed search, with the source edit that
realises each. "Sites" are the call sites of one role: in the seeds 3 for
the planner, 1 for the coder and 1 to 2 for the reviewer.

| Dimension | Edit today | Edit after |
| --- | --- | --- |
| Model per role | One token: the literal default of that role's model input | The same |
| Effort per role | One token, once the seed has an effort input per role (two more signature lines; possible today) | The same |
| Timeout per role | One literal at each site | One token: the literal in the role's line, or an input's default |
| Dropping an option of a role (the template's default model; no effort) | Delete the option at each site | Not an edit of the role's line: `ask` takes all four, so the author adds a two-line wrapper without that parameter and points the role at it |
| A second role from one (milestone reviewer and acceptance reviewer) | New inputs, and each site that moves rewritten | One new line; one token at each site that moves |
| A role's literal edited in the middle of a run | `resume` prints a plan; `resume --accept-changes=TOKEN` cancels from the first committed step whose input changed | The same, the cut being that role's first committed step. In both, no plan can be accepted when a committed agent turn lies at or after the cut (`invalidate_coordinator_committed`): start a new run. An edited input default is never resumable |
| Conversation scope: fresh or continued | The `agent` line added or removed, and each site rewritten | The same, by §8.2's deferral: the role's line becomes an `agent` line and each `(coding (work …))` becomes `(provider-result coder :timeout-sec … :prompt (work …))` |
| Conversation scope: per milestone or per run | Move the `agent` line between the map body and the outer `let*`; per run needs I1 | The same |
| Stages present | Delete a binding of two lines, or a `match` | The same; a fresh call is one line; with I1 the milestone level is one block |
| Loop bounds | One `:max` literal | The same |
| Milestone granularity | The map's `:max` and the number in the prompt must agree; a longer plan fails the run | Two tokens that must agree, `(list/take plan.milestones 8)` and `:max 8`; the number in the prompt is advice, and a longer plan is cut |
| What gates a loop | Add or remove the check wrapper (two lines) or the review call | The same; "every milestone met" is one more gate (`list/all`, one line) |
| How a document reaches a call | `:path`, or named in the prompt | The same (§8.1) |
| Prompt wording | One string in a `defprompt` | The same; the identities of its calls do not move, in place or through a role |

What the table says. Inputs with literal defaults are the form to prefer for
model and effort: a harness sets them without touching source, a mutated
program is self-contained, and the edit is one token; a literal in a role's
line is for a person changing a role in the middle of a run of fresh calls.
Model and effort were already one-token edits. The first space the owner
selected (one model, an effort per role) is three such tokens and needs
nothing from this design; its points differ in tokens per call, so they are
compared by priced tokens. What this design changes for a search is the
timeout, the second role and the shorter fresh call. The row that motivated
binding a role once, fresh or continued, does not change until §8.2 is taken
up.

## 10. Fit With Surface Coherence, And What Stays

| Sentence | Effect of this design |
| --- | --- |
| 1. Effects | Unchanged. A prompt application is pure and its operands are literals, names and fields |
| 2. Iteration | Unchanged; the cap exception is kept word for word. `(list :of T)` is a source like any other |
| 3. Callables | Amended: after "a procedure reference is a compile-time name" add "and so are a prompt value and a provider". Its exception list gains: a reference bound over a generic procedure is called where it is bound. The macro exception is unchanged |

| Left alone | Why |
| --- | --- |
| The serial map running `:max` items and then failing | Frozen: a run recorded past that point must resume |
| `agent` as it is | It already binds model and effort for a conversation; a fresh mode would make a turn's effect class depend on a value |
| Literal timeout for phased delivery | Its deadline starts before inputs are read |
| `:doc` | The refusal for an outside edit is what it is for |
| The macro rule | §4.7 |
| Workflow input defaults as literals | A default that names another input adds evaluation order to a signature; the role line covers the need |

## 11. Feasibility, Compatibility And Identity

Every change kept here is prototyped in the compiler on the spike branch.
The prototype is evidence, not the implementation: no tests, no diagnostics
for the refused positions, generic wrappers only.

| Change | Prototype | Result |
| --- | --- | --- |
| T | 3 files | A timeout from an input, a `let*` name, a procedure parameter, a `bind-proc` argument and on an agent turn builds; one from an input runs; a computed expression, a `String` and a literal `0` refuse; an input of `0` refuses before launch |
| L | `:of`, 2 files | Builds and runs as a `let*` binding, a loop's initial state and an operand; `(list :of String)` in a field has the digest of `(list)` |
| O | 4 files | The three operators run, also in a `defun`; a list of nine under `list/take … 8` and `:max 8` completes |
| P | 12 files, +270 | §4.2, §4.4, §4.5. `staged.orc` and `milestones.orc`, written with `std/ask` roles, compile as written and pass the nine scenarios of the seed's own demo with the stand-in, kills and resumes included, with the call counts of the originals |
| D3 | 15 lines | A generic procedure called in a map body runs |

**Nothing that compiles today moves.**

- T, L and O: the three invariants of the
  [stage 3 plan](../plans/2026-11-12-lane-d-stage-3-old-ir-stack-plan.md)
  (corpus snapshot, compile of every tracked `.orc`, run-reference digests)
  are byte-identical between the base and the prototype. The review checked
  it independently on the 59 tracked files that use `:timeout-sec` or
  `(list)`, each compiled with a generated provider externs file: 21 build,
  and every file has the same exit code and digest on both.
- P: the same three invariants between the spike before the prototype and
  with it are byte-identical, the compile this time with a generated
  provider externs file for each source, so that programs with a provider
  call reach typecheck. Of the 635 tracked files 61 build, and 40 of those
  name a provider.
- Seven programs that compile today in which a prompt's name is also a
  binding, a procedure, a form or an operator, or the prompt has no slots,
  keep their digests under the prototype (the head rule of §4.1). An uncalled
  reference over a generic procedure keeps its digest (§4.4).
- Tests that flip assert a refusal this design removes:
  `test_timeout_provider_call_policy_enforces_literal_type_and_positive_domain`
  (one case) and `test_list_traversal_authored_head_inventory_is_exact`.

Under the versioning rule no change adds a target: each admits source that
is refused today and moves no identity of source that compiles; each gets an
entry in the spec's change list.

**Diagnostics.** Nothing legal today becomes refused. New codes, all for
source refused today under another code: `prompt_value_escape`,
`provider_timeout_nonpositive`, `list_item_type_invalid`. Narrowed:
`provider_result_timeout_literal_required` (a computed expression, or a
phased call); `list_empty_type_context_required` (fewer positions);
`provider_result_provider_invalid` and `generic_union_not_generic` no longer
fire for a `Provider` parameter and for `Prompt[T]`.

**Seed sizes** (lines; code lines at most 129 characters). "Per-role inputs"
is today's language with a model and an effort per role as inputs with
defaults, compiled on `main`. "After" is compiled as written on the spike.

| Seed | As written | Per-role inputs | I1, I2a | L | P | O (gate) | Longer lines | After |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `staged.orc` | 40 | 42 | −1 | −1 | −1 | 0 | 0 | 39 |
| `milestones.orc` | 49 | 53 | −7 | −1 | −2 | +1 | 0 | 44 |
| `roles.orc` | 49 | 53 | −7 | −1 | 0 | +1 | +2 | 48 |

The columns between the two compiled end points are an attribution. The gate
line is the `let*` binding that D1 forces; without the defect it is 0.
`roles.orc` keeps its agent turns in place (§8.2); two of them no longer fit
one line once I1 moves the milestone body into the map.

## 12. Verification

Scenarios each change adds, through the public command line with stand-ins:

| Change | Scenario |
| --- | --- |
| T | A timeout from an input reaches the launch and the `policy` part; `0` from an input refuses before `started`; a run recorded with a literal resumes unchanged; a phased call with a name refuses |
| O | Each operator's edge cases; nine items under `list/take` complete, and a run recorded before the change that failed at the cap resumes to the same code |
| L | `(list :of T)` in each position of §2's row 3; equal digests where `(list)` compiles today; `(continue (list))`, `(count (list))` on a `defun` and a `match` arm build |
| P | The head rule: the seven programs keep recorded digests. `ask` bound three times and called in sequence, in a loop and in a map body: distinct identities, the `policy` parts and prompt texts of the program written in place. Two prompts with equal slots get two specializations. A kill between two role calls resumes with one dispatch. One role's literal edited: the plan's cut is that role's first step. A name bound into a role and rebound before the call keeps its binding-site value. An uncalled reference over a generic procedure keeps its recorded digest. Each refused position and type position of §4.1 refuses. `--max-cost-usd` refuses an unpriced model before launch and reports the usage of the program written in place |

## 13. Changes And Their Dependencies

| Change | Where | Depends on |
| --- | --- | --- |
| T | `wl/typecheck_effects.py`; `contracts/closed_program/check.py`; `workflow/evaluated/providers.py` | — |
| O | `workflow/pure_expr.py`; `wl/typecheck_pure_ops.py`; `wl/wcc/elaborate.py`; `wl/result_guidance.py`; `orchestrator/py/trace.py`; three rows of the specification's operator table | — |
| L | `wl/expressions.py` (`_elaborate_list_constructor`); `wl/typecheck_structural_values.py`; `wl/typecheck_dispatch.py`; `wl/wcc/elaborate.py` | C1, E1, I1, I2a merged |
| P1 | `wl/type_env.py`, `wl/expressions.py`, `wl/expression_traversal.py`, `wl/typecheck_dispatch.py`, `wl/typecheck_proofs.py`: the type, the application as an argument, the head rule, the refusals | E1 merged (the same elaboration functions) |
| P2 | `wl/procedure_typecheck.py`, `wl/procedure_specialization.py`, `wl/procedures.py`, `wl/closed/names.py`, `wl/typecheck_effects.py`: `Prompt[T]` and `Provider` parameters; the specialization and its name | P1, T, Task 0b (D3) |
| P3 | `wl/typecheck_dispatch.py`, `wl/procedure_typecheck.py`: a called reference over a generic procedure | P2; C1 merged (D4) |
| P5, P6 | `wl/stdlib_modules/…/std/ask.orc`; the documents of §14 | P3; the stage 4 cut decides the library's target |

## 14. Where The Rules Live

This document is retired to Historical when the receiving entries below carry
each rule with its exception list, the listed text is gone, and each change
of §13 is implemented or dropped. §8 goes with it as a record.

| Rule | [Frontend specification](workflow_lisp_frontend_specification.md) | [Guide](../lisp_workflow_drafting_guide.md) | Text that leaves |
| --- | --- | --- | --- |
| 1 | §8.7.1 `defprompt`: the type, the positions, the head rule; §22.6: `:prompt` takes a prompt parameter | The prompts section, one paragraph | §8.7.1 "A prompt is not a value … Its one use is a direct, fully applied application as the `:prompt` of `provider-result`" and "an application anywhere else is an unknown call" |
| 2 | §7.8 "Procedure References": a called reference over a generic procedure, a `Provider` argument; an entry for `ask` in the library reference | A "Roles" recipe | — |
| 3 | §22.4 "Call-Local Provider Policy" | One sentence | `<positive Int literal>` in the option list |
| 4 | §10.3: the `list` entry | The loops section | The carrier as the only way |
| 5 | §10.2: three rows of the operator table | One paragraph on meeting a map's cap | — |

`specs/providers.md` gains the timeout operand; `specs/dsl.md` and
`specs/versioning.md` one change-list entry per change. The specification
sentences state the rules without "today" or "after".

## 15. Open Decisions For The Owner

| # | Question | Recommendation | Cost of each answer |
| --- | --- | --- | --- |
| 1 | P as decided costs about 44 hours after the prototype and the deferrals (66 before them); a provider binding with options costs about 16 and gives the same rows of §9. Proceed with P? | Yes, as decided: the prototype runs the idiom end to end, and prompts as arguments and called generic references serve more than roles | Yes: about 28 more hours, most of them in specialization. No: a second policy form beside `agent`, and prompts stay second-class |
| 2 | May an `Agent` be a `bind-proc` argument (§8.2)? | **Deferred** by the coordinator's ruling; the rule and its guards are kept | Taken up later: about one day and an Agent Sessions amendment. Until then fresh or continued is an edit of each call site |
| 3 | The snapshot fill (§8.1) | **Deferred**; the rule is incomplete for a pending agent turn | Until then `:path` only for living documents, and `:doc` can still strand an agent run |
| 4 | `list/take` beside `list/length` and a computed `:max` | Accept all three operators | No: a seed must refuse a long plan and replan, at the price of one planning call's tokens |
| 5 | Fix the defects the seeds meet (D1, D2, D3) as the first task? | Yes; D4 arrives with C1; D5 is diagnosed there and becomes a fix or a named limit | Deferred: a `let*` line per use for D1 and D2; no role call in a map body for D3 |
| 6 | Should `report` shorten the bracketed digest in step names? | Not here; the name now says which prompt and provider | — |
