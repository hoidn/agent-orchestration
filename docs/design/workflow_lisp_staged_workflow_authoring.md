# Workflow Lisp Staged-Workflow Authoring: Prompt Values, Roles, Timeouts, Lists, Living Documents

- **Status:** Designed (proposed), not implemented. The compiler behaves as the
  "Today" columns of §2; the "after" examples do not compile on `main`.
- **Kind:** language revision. **Created:** 2026-11-13.
- **Direction fixed by the owner** (roadmap decision 15): a typed prompt is a
  first-class value and a role is a generic procedure wrapping
  `provider-result`, partially applied with `bind-proc`; no `role` form. This
  document designs that and reports what it costs (§4.9, §15).
- **Owns, until retired (§14):** what a prompt application denotes outside
  `:prompt`; what may be a `bind-proc` argument; the `:timeout-sec` operand;
  the typed list literal; three list operators; the `:snapshot` fill kind.
- **Consumes:** [surface coherence](workflow_lisp_surface_coherence.md) (its
  three rules; changes E1, I1, C1, I2a);
  [evaluated execution](workflow_lisp_evaluated_execution.md) §6, §7.2, §8;
  [Agent Sessions](workflow_lisp_agent_sessions.md);
  [closures boundary](workflow_lisp_runtime_closures_boundary.md) §4, §5;
  [edit and continue](workflow_lisp_edit_and_continue.md) §2, §3; the versioning
  rule of the [one-target plan](../plans/2026-11-12-lane-d-stage-4-one-target-plan.md#the-versioning-rule).
- **Plan:** [staged-workflow authoring revisions](../plans/2026-11-13-staged-workflow-authoring-revisions-plan.md).
- **Evidence:** branch `spike/authoring-revisions`, `experiments/authoring_revisions/`
  (probes, prototypes, the lowering script, stand-in runs). No provider or model
  was called; cost in this document means priced tokens, never a count of calls.

## 1. The Rules

Six things were awkward when a compact staged workflow (guides, spec, plan,
milestones with check and review, acceptance) was written in fewer than 50
lines. Each was reproduced before anything was decided (§2). Each rule is one
sentence; what it does not cover is listed under it.

**1. Prompts are values.** A fully applied prompt, `(work :repo repo …)` with
`work` declared `-> Change`, is a value of type `Prompt[Change]`: it can be
passed to a procedure, bound by `let*` or `bind-proc` and forwarded, and
`(provider-result who :prompt p)` with `p : Prompt[T]` is a call of type `T`.

- *A compile-time value, like a procedure reference:* not stored in a record,
  list or loop state, not a workflow input or result, not returned, not chosen
  by `if` or `match`, not a `defun` parameter.
- *Fills are evaluated where the application is written,* once, in written
  order; *files are read at the call* (§4.3).
- *Unchanged:* an extern prompt name with `:inputs` and `:returns`; a partial
  application (`prompt_partial_application_unsupported`); a phased call and a
  `request-input` question take the application written in place.

**2. A role is a procedure with its arguments bound.** `(bind-proc (proc-ref
ask) :who providers.coder :model m :effort e :timeout 3600)` is a role and
`(coding (work …))` is a call of it, because a provider extern can be passed
to a `Provider` parameter, a reference to a generic procedure instantiates its
type parameters at each call, and an `Agent` can be a `bind-proc` argument.

- *A `Provider` parameter is compile-time,* with the limits of rule 1's first
  exception.
- *A reference that holds an `Agent`* stays out of a parallel worker
  (`parallel_agent_boundary`); no reference crosses `call`, so a workflow binds
  its own roles from its inputs.
- *An agent turn takes no `:model` or `:effort`,* so the library has two
  wrappers, `ask` and `ask-agent` (§4.6).
- *A macro still may not hide an effect* (`macro_hidden_effect`, §4.8).

**3. A timeout is a value.** `:timeout-sec` takes an `Int` literal, name or
field, as `:model` and `:effort` take a `String`.

- *Phased delivery keeps a literal:* its deadline is read from the checked
  node before any input is resolved.
- *Not a computed expression:* bind it first, as for `:model`.
- *A value below 1* refuses the step before launch; no attempt is recorded.

**4. An empty list states its item type where its position does not.**
`(list :of String)`; a field, an argument, a workflow result, the other arm of
an `if`, a loop-state field, and (new) a `continue` value, a `defun` argument
and a `match` arm supply it.

- *`:of` is allowed on a non-empty list* and checks its items.
- *`loop-state`* remains for a state of several named fields.

**5. Three pure list operators.** `(list/take xs n)` is the first `n` items,
`(list/all bools)` and `(list/any bools)` reduce a `List[Bool]`.

- *The serial map's cap is unchanged:* `:max` items run, then
  `list_map_effect_cap_exceeded`.
- *Left out:* fold, filter, membership, concatenation (§7).

**6. A document fill can be a snapshot.** A slot of kind `:snapshot` is
delivered like `:doc`, and the step keeps the bytes it read: `resume` replays
it from those bytes, so a later change to the file does not diverge it.

- *`:doc` is unchanged:* pinned to the file as it stands at resume.
- *An edit from outside* is not reported for steps that already read a
  snapshot, as for a `:path` fill today; steps not yet run read the new file.
- *Kept bytes that are missing or altered* refuse resume; the workspace is
  never read in their place.

No program that compiles today changes its closed program, program digest,
effect identities or behaviour (§11).

## 2. Verified Findings

Target 2.40, public command line, stand-in commands and the scripted `claude`
of `tests/agent_session_shims.py`. Class: **(a)** needed for a stated
guarantee, **(b)** unimplemented case, **(c)** historical accident. Paths are
under `orchestrator/`; `wl/` is `workflow_lisp/`.

| # | Claim | Result on `main` | Decided in | Class |
| --- | --- | --- | --- | --- |
| 1 | A role cannot be bound once for fresh calls | Reproduced, and narrower than stated. `agent` binds model and effort only (`agent_keyword_invalid` for `:timeout-sec`) and a turn refuses both (`agent_turn_policy_override_forbidden`). A procedure per prompt, bound with `bind-proc`, already is a role: it compiles, runs and gives each call site, loop round and map item its own identity. A record of model and effort passed as `:model r.model` compiles. The Python frontend binds a role today (`Provider(name, model=, effort=, timeout_sec=)`) and emits the inline call | `wl/typecheck_effects.py:typecheck_provider_result_expr`; `wl/typecheck_agents.py` | — |
| 1a | A prompt is not a value | `Prompt[T]`: `generic_union_not_generic`. A `Prompt` parameter in `:prompt`: `frontend_parse_error` ("requires :inputs and :returns for an extern prompt"). An application outside `:prompt`: `procedure_call_unknown` | `wl/expressions.py:_elaborate_provider_result`; `wl/type_env.py` | (b); the specification's §8.7.1 says "its only use is one fully applied named application" |
| 1b | A provider extern cannot be an argument | `provider_result_provider_invalid` for a `Provider` parameter, a generic one and a `let*` alias | `typecheck_provider_result_expr` | (b) |
| 1c | A reference to a generic procedure is not generic | `(bind-proc (proc-ref pick) :n 1)` then `(keep x)`: `type_mismatch` "expected `T`"; binding an argument of type `T`: `proc_ref_binding_type_invalid`. A direct call instantiates | `wl/procedure_typecheck.py:typecheck_procedure_call_expr` (the bound-reference branch) | (b) |
| 1d | An `Agent` cannot be a `bind-proc` argument | `let_proc_capture_agent_forbidden`, also when written explicitly | `wl/procedure_refs.py:resolve_proc_ref_value` | (a) Agent Sessions: the handle is authority and never enters a parallel worker. Kept by a guard (§4.6) |
| 1e | A macro cannot wrap the call | `macro_hidden_effect` | `typecheck_provider_result_expr` | (a) kept (§4.8) |
| 2 | A timeout must be a literal | Reproduced for a provider call and an agent turn (`provider_result_timeout_literal_required`). Enforced three times: typecheck, the closed check ("provider timeout must be a positive Int literal") and the phased runtime. A composed call already launches with the resolved policy value | `typecheck_provider_result_expr`; `contracts/closed_program/check.py:_check_effect_node`; `workflow/evaluated/phased_providers.py:capture_phased_deadline` | (c) composed; (a) phased: the deadline starts before input reads |
| 3 | An empty list needs a type carrier | Reproduced, and wider. Refused (`list_empty_type_context_required`): a loop's initial state, a `let*` binding, a `continue`, `done` or `:on-exhausted` value, a `defun` argument, a `list/append` or `=` operand, a map source. Accepted: a record or variant field, a procedure or workflow argument, a workflow result, an `if` arm, a loop-state field. **Defect:** in a `match` arm, `compiler_defect` ("typed list is missing its resolved child types") | `wl/typecheck_structural_values.py:typecheck_structural_value_expr` | (b): the expected type is passed to some positions only |
| 4 | A `:doc` fill on a living document blocks `resume` | Reproduced, and worse with a conversation. A later step rewrote `docs/plan.md`; after a kill `resume` exits 2: `effect_input_diverged … input parts changed: ['dependency:docs/plan.md', 'prompt']`, with a plan that cancels the step that read it and every later one (`invalidate`, then `resume --accept-changes`). The same text appears for an edit from outside: the two are not told apart. When the reader is an agent turn, "no plan can be accepted: `invalidate_coordinator_committed`" and `invalidate` refuses: the run cannot continue. With `:path` both cases resume and neither is noticed | `workflow/evaluated/effect_inputs.py:_reuse_effect_commit`; `providers.py:resolve_provider_input` | (a) resume determinism (C6, C7) for a file nothing in the run changes; for a file the run rewrites the check compares with the wrong bytes |
| 5 | Nine milestones run eight, then fail | Reproduced: eight items, then exit 1, `list_map_effect_cap_exceeded`. Correction: `list/length` exists, so a program can refuse a long list before the map today (`(if (> (list/length xs) 8) …)`); it cannot shorten one (`list/take`: `pure_expr_operator_unsupported`) | `wl/typecheck_structural_values.py` (the map's synthetic loop); `workflow/evaluated/machine.py:_loop` | (a) frozen: a run recorded past that point must resume |
| 6 | A list cannot be reduced | Reproduced: no `list/all`, `list/any`, fold or membership; `=` on lists is refused; a cursor loop over `list/rest` works in a workflow or procedure body and not in a `defun` (`pure_function_has_effect`) | `workflow/pure_expr.py:PURE_EXPR_OPERATOR_CATALOG` | (b) |
| D | (New) A `list/map` whose body is a `match`, used in an `if` condition inside a loop body | `compiler_defect` (`KeyError`); binding it with `let*` first compiles | `wl/wcc/elaborate.py` | Defect; not designed here (§15) |

Also measured: a workflow input takes a literal default (`(coder String
:default "claude-haiku-5-5")`), not a name (`workflow_param_default_type_invalid`);
a call with no model on a template that needs one fails at run time
(`provider_preparation_failed`), not at compile time.

## 3. Decision

Ranked by value over cost for the seeds and for ordinary authors. Days are
working days, estimated from the prototypes and from reading the code.

| # | Change | Rule | Compiler | Value |
| --- | --- | --- | --- | --- |
| T | `:timeout-sec` takes a name or a field | 3 | 3 files, +25; prototyped | A timeout as an input; required by P |
| L | `(list :of T)`; expected type to `continue`, a `defun` argument, a `match` arm | 4 | 3 files, about +60; `:of` prototyped | One line less in each seed; no carrier |
| O | `list/take`, `list/all`, `list/any` | 5 | 5 files, about +60; prototyped | The cap can be met; verdicts can be read |
| P | Prompt values; `Provider` parameters; generic references; `Agent` in `bind-proc`; `std/ask` | 1, 2 | About 8 days; not prototyped in the compiler (§11) | A role is one line; conversation scope is edited in one place |
| S | The `:snapshot` fill kind | 6 | About 3 days; not prototyped | Documents can be delivered as content safely; an agent run is not stranded |

Not done: a fold, an option on the map for a long list, a `role` form, a
conversation option on `agent`, effectful macros (§4.9, §7, §10).

## 4. Prompt Values And Roles

```lisp
;; today: every call repeats the role
(change (provider-result providers.coder :model coder :effort effort :timeout-sec 3600
          :prompt (work :repo repo :milestone m :notes notes)))
;; after
(coding (bind-proc (proc-ref ask) :who providers.coder :model coder :effort coder_effort :timeout 3600))
(change (coding (work :repo repo :milestone m :notes notes)))
```

### 4.1 The type and where a prompt value flows

`Prompt[T]` is formed by applying a `defprompt` declared `-> T` to every slot
exactly once (the existing `prompt_fill_*` and `prompt_slot_*` codes). The head
resolves in the prompt namespace unless a lexical binding, a procedure or a
function has that name. Bare `Prompt` stays the type of an extern prompt name.

A prompt value is data, not code: it holds a declaration and fill values, and
storing one would breach nothing in the closures boundary. It is still
compile-time here, for a different reason: every place a prompt value flows is
resolved by specialization, so the checked program holds no value of type
`Prompt[T]` and its format does not change. Storing or choosing one needs a
run-time representation (a template reference and a contract inside a value)
with its own checked form; no consumer needs it yet.

| Position | Rule |
| --- | --- |
| Argument to a `Prompt[T]` parameter of a `defproc` or a local procedure; a `bind-proc` argument; a `let*` binding; forwarding | Admitted |
| `:prompt` of `provider-result`, as a name or written in place | Admitted; the call has type `T`; `:inputs`, `:returns` and `:prompt-dependencies` are refused as for an application written in place |
| Record or variant field, list element, loop state, `if` or `match` value, procedure result, `defun` parameter, workflow input or result, command or provider data | Refused: `prompt_value_escape` |

### 4.2 How it compiles, and identity

A procedure with a `Prompt[T]` or `Provider` parameter is specialized for its
compile-time arguments exactly as one with a `ProcRef` parameter is: for each
distinct procedure, type arguments, prompt declaration, provider extern and
bound values, the checked program holds one ordinary procedure whose
parameters are the remaining values plus one per fill, and whose
`provider-result` node is the one an author would write inside it by hand. No
checked construct, node kind or identity rule is added. The specialization's
name is derived from those five things, as a bound procedure's is today, so
renaming a prompt or a wrapper gives its role calls new identities, as
renaming a procedure does.

Measured on those hand-written specializations (the lowering script of §11
writes them from the source above):

| Question | Result |
| --- | --- |
| One site inside the wrapper, many call sites | One identity per call: `workflow:m::run / ready=procedure:m::ask-…[<digest>] / #1`; per loop round `loop:notes[2] / change=procedure:… / #1`; per map item under `loop:#1[i]`. The frame label is the binding at the call (I2, I4) |
| What the role's name contributes | Nothing: renaming the role keeps the program digest. A comment line moves nothing |
| Prompt text | The five composed prompts of a run are byte-identical to those of the same program written with calls in place, once the result path is normalised |
| Recorded `policy` part | Equal, step for step, to the program written in place: model, effort and timeout reach it as values |
| `declaration` | A bound literal is folded into the specialization's node and so into `declaration`; a bound name becomes a parameter and reaches `policy` through its value |
| Editing one role's bound literal | Only that role's specializations get a new name and node; the others keep both. Plain `resume` prints a plan whose cut is that role's first committed step: commits before it are kept and everything after it is cancelled, whatever its role (C10's suffix rule; not "only that role's steps") |
| Editing an input's default | No plan: `resume_inputs_changed`. A run's inputs are fixed for its life |

### 4.3 When fills are evaluated and when files are read

- **Fill operands** (`:text`, `:value`, `:path`, `:doc`, `:snapshot`) are
  evaluated where the application is written, in written order, once, as any
  argument is (surface coherence, rule 1). An application written in
  `:prompt` is written at the call, so nothing that compiles today changes.
  A `bind-proc` argument is evaluated at the binding, as today.
- **Files** are read when the effect that uses the prompt resolves its input,
  at each attempt's start (C6). A prompt value holds a path, never bytes.
  Reason: only an effect has an identity under which a read is recorded and
  replayed; creating a prompt value is pure, has no site and advances no
  ordinal (I4). The parts `dependency:<path>`, `dependency_rows` and `prompt`
  therefore belong to the call, as today, wherever the prompt was written.
- A prompt value used by two calls has its operands evaluated once and its
  documents read by each call. Rule 6 is independent of all this: the pin, or
  the snapshot, is taken at the call.

### 4.4 Metering and the spend cap

The cap is checked before each attempt from the resolved policy
(`workflow/evaluated/spend_cap.py:check_spend_cap`): the model value, or the
template's default, must have rates in the price table. A model that is a
workflow input is already a run-time value there. Measured through a bound
wrapper with `--max-cost-usd`: an unpriced model refuses with
`spend_cap_unmetered` (`model_unpriced`) and an unmetered template with
`template_unmetered`, both before launch, as for the call written in place.
The timeout does not enter metering. Usage is attributed by the model in the
recorded policy, which is unchanged (§4.2).

### 4.5 Typed prompt inputs, prompt identity, the Python frontend

An application written in `:prompt` takes the same path through
`wl/prompts.py`, the fragment renderers (`wl/typed_prompt_inputs.py`) and the
checked node as today; the plan's invariant checks gate that. In a
specialization the fills are parameters, so each fill is a name, which the
fill-identity rule already admits. The Python frontend needs no change: its
`Provider` object already carries model, effort and timeout and emits the call
in place, and a Python prompt application is already a host value.

### 4.6 Roles, Agent Sessions and the library

```lisp
(defproc ask :forall (T) ((who Provider) (model String) (effort String) (timeout Int) (prompt Prompt[T])) -> T
  (provider-result who :model model :effort effort :timeout-sec timeout :prompt prompt))
(defproc ask-agent :forall (T) ((who Agent) (timeout Int) (prompt Prompt[T])) -> T
  (provider-result who :timeout-sec timeout :prompt prompt))
```

`std/ask` exports both. Use: `(import std/ask :only (ask))`, one line per role.
A role that needs another shape (a default model, a fixed prompt prefix) is a
two-line procedure of the author's own; that is the point of using ordinary
partial application.

- **`Provider` parameter.** The argument is a provider extern name, a
  `Provider` parameter or a `let*` alias of one. Agent origins stay exact: a
  specialization names its extern.
- **Generic references.** `(proc-ref f)` and `bind-proc` over a generic `f`
  keep `f`'s type parameters; each call infers them as a direct call does.
  A bound argument's type may not mention a type parameter (today's
  `proc_ref_binding_type_invalid`, kept). A reference passed to a
  `ProcRef[...]` parameter is instantiated to that type.
- **`Agent` as a `bind-proc` argument.** Admitted when written explicitly; the
  bound reference aliases the agent, as passing it at each call does. Two
  guards keep Agent Sessions' rules: the reference's agent origins are those
  of the bound value, and a reference that holds an `Agent` is refused in a
  parallel worker exactly where an `Agent` is. `let-proc` capture stays
  refused. This amends the sentence "implicit `let-proc`/`bind-proc` capture
  of an agent is rejected" to cover `let-proc` only.
- **Fresh or continued.** The two wrappers differ because an agent turn
  refuses `:model` and `:effort`. Switching a role is an edit of its binding
  lines only; no call site changes (§9). A call of `ask` is an ordinary
  provider effect; a call of `ask-agent` is today's agent turn inside a
  procedure, which Agent Sessions already admits: the coordinator, recovery
  and the rule that a committed turn is never cancelled are untouched.

### 4.7 Step names

`report` and the dashboard show the identity, of the form
`change=procedure:std/ask::ask[<64 hex>] / #1`.
The author's name for the step is the binding at the call (`change`), as for
any procedure call today; the role's name does not appear. The bracketed
digest is long; shortening its display is a presentation change outside this
design.

### 4.8 The macro rule stays

A macro is expanded before any call exists (surface coherence, rule 3). An
effect inside an expansion would have no frame in its identity and no effect
summary at its use, and editing the macro would change steps at every use
with nothing at the use naming it. A procedure has both. With roles as
procedures the reason to want an effectful macro is gone.

### 4.9 Alternatives not taken, and what the chosen one costs

| Alternative | Why it lost |
| --- | --- |
| A provider binding with options, `(provider providers.coder :model … :timeout-sec …)`, used as `provider-result`'s first operand | A new form and a second way to bind policy beside `agent`. It is the cheapest (about 2 days: an alias expanded at each call, the same checked program as today) and is what the Python frontend does at generation time |
| `agent` with `:conversation fresh` | One form, but the option changes the effect class of every turn (coordinator or not) and what `invalidate` may cancel; the checked class of a turn would depend on a value |
| A `role` form | A form whose only content is partial application |
| A record of call options spliced into calls | Possible today for model and effort (`:model r.model`); it shortens nothing at the call |
| A macro wrapping the call | `macro_hidden_effect`, kept |

The chosen design needs four compiler capabilities that do not exist (§2, 1a
to 1d) besides rule 3, in the specialization pass, the largest part of the
frontend. It saves one or two lines in a seed with fresh calls and costs four
in the seed with conversations (§11); its value is that a role is edited in
one place (§9) and that prompt values and generic partial application are
general. Nothing in it breaks a guarantee, provided the guards of §4.6 hold.

## 5. Timeouts

```lisp
;; today: provider_result_timeout_literal_required
(provider-result providers.coder :model coder :effort effort :timeout-sec limit :prompt (work …))
```

The operand is typed `Int` and must be a literal, a name or a field with no
effect. A literal is checked positive at compile time as today. A name or
field is checked when the step resolves its input: a value below 1 refuses the
step before launch with `provider_timeout_nonpositive`, and no `started`
record is written. The value enters the `policy` part and, as an operand
shape, the `declaration`; a timeout that changes between a run and its resume
diverges the step, as a changed model does. An agent turn takes the same
operand. A phased call keeps the literal.

## 6. Empty Lists

```lisp
;; today: (loop/recur :max 2 :state (loop-state (notes List[String] (list))) … (fn (state) …
;;          (continue (loop-state :like state :notes gap.reasons))
(loop/recur ((notes (list :of String))) :max 2 :on-exhausted …
  … (continue gap.reasons))
```

Weighed: an annotation on the binder (`((notes List[String] (list)))`) fits
only loops and adds a third shape to rule 2's binder; inference from the
`continue` values needs unification the checker does not have; the carrier is
what the finding is about. A typed literal is one spelling for every position
(a `let*` binding, an operand of `list/append`, a map source) and reads
naturally in the binder. The checker already records an item type on every
list; `:of` sets it before typing. `(list :of T)` where the position already
states `T` builds the same program as `(list)` (measured: equal digests); a
mismatch is `pure_expr_operand_type_mismatch`. The three positions added to
rule 4 have a declared type that is not passed down today; the `match` arm is
the defect of §2.

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
- All three are pure operators of the list group: usable in a `defun` and in a
  `list/map` body, no site, no identity, no provider call. Each is bounded by
  the length of its operand, a value already held.

An author has three ways to meet the cap, each an explicit choice: take the
first `n` (`list/take`); refuse a long list before the map (`list/length`,
today); or, with I1, make the list's own length the budget
(`:max (list/length xs)`). An option on the map for a long list was weighed
and dropped: it would add a keyword with two modes where two pure operators
serve, and the map's recorded behaviour must not move.

Left out: a general fold (rule 2's binder has one name; a fold needs two, and
no seed needs one); `list/filter`, `list/contains?`, `list/concat` (the check
"every target is claimed by a milestone" needs all three; it stays with the
reviewer). `list/map` bodies stay pure for the reason surface coherence gives.

## 8. Document Fills On Living Documents

```lisp
(defprompt work (:fills (repo :text) (plan :snapshot DocPath) (notes :value List[String])) -> Change "…")
```

**The question.** A `:doc` fill makes the file's bytes an input of the step.
On resume every committed step's input is resolved again from the workspace
and compared (C7). That is right for a file nothing in the run changes, and it
is the wrong comparison for a document the run itself rewrites: the journal is
exactly what an uninterrupted run produces, and the check fails only because
it reads today's bytes for a step that read yesterday's.

**The rule.** For a `:snapshot` slot the attempt retains the bytes it read,
under their digest, in its attempt directory at `started`. A committed step's
input is resolved from the retained bytes after they verify against the
recorded digest; a mismatch or a missing file refuses (`memo_inconsistent`),
never falls back to the workspace. Recorded parts are those of `:doc`. This is
the confined profile's attempt-snapshot binding (evaluated execution §7.3,
amendment) applied on host runs to a slot that asks for it. The composed
prompt, document included, is already retained per attempt (`prompt.txt`,
whose digest is the `prompt` part: measured).

**How the neighbours treat a changed file.** Script-fix retry accepts a
changed script only for an attempt that did not commit, and only on evidence
taken at the failure that nothing of the run was alive and the files were as
at `started` (§8.1); it says nothing about a committed step. Edit and continue
rehashes the bound files of kept commits "in the workspace as it is now" and
names this case: a later step rewrote a file an earlier commit bound, "the
normal case for agent steps", and the cut moves back to that commit (§3). A
`:path` fill binds the path value and no bytes.

**What is not weakened.** `:doc` keeps today's refusal for any change. A
`:snapshot` slot gives up, for that slot, the report of an edit from outside
between runs; `:path` gives that up today with no evidence at all. For a
living document that edit is usually the point: the author corrects the plan
and wants the remaining steps to read it, with the finished ones standing.

**Not chosen: telling a run's own change from an outside one without new
syntax.** It needs every effect to record the digest of each bound file after
it commits, and a rule for a change made by a killed attempt, which is
indistinguishable from an outside edit made after the kill. It would also
change what `resume` does for programs that compile today.

**Evidence still missing** (the plan's first step for S): strict replay
passing from retained bytes for a provider and for an agent turn, and the
edited-program plan's fifth condition reading them. **Until S lands:** pass
the path (`:path`) for any document a later step edits; use `:doc` only for
documents nothing in the run writes; never `:doc` on a living document read by
an agent turn.

## 9. What A Search Mutates

The declared dimensions of the seed search, with the source edit that realises
each. "Sites" are the call sites of one role: in the seeds 3 for the planner,
1 for the coder and 1 to 2 for the reviewer.

| Dimension | Edit today | Edit after |
| --- | --- | --- |
| Model per role | One token, when the model is an input with a literal default (possible today); else one token at each site | One token: the input's default, or the literal in the role's line |
| Effort per role | The seeds share one `effort`: two more lines of inputs and one token at each site, once; then one token | One token, as for the model |
| Adding or removing a role's own model, effort or timeout | Each site | The role's line |
| A second role from one (milestone reviewer and acceptance reviewer) | New inputs and each site that moves | One new line; one token at each site that moves |
| Conversation scope: fresh or continued | Each site rewritten, plus the `agent` line | The role's lines only (one line becomes two); no site |
| Conversation scope: per milestone or per run | Move the `agent` lines; per run needs I1 | Move the role's lines between the map body and the outer `let*` |
| Stages present | Delete a binding of two lines, or a `match` | The same, one line per call; with I1 the milestone level is one block |
| Loop bounds | One `:max` literal | Unchanged |
| Milestone granularity | The map's `:max` and the number in the prompt must agree; a longer plan fails the run | One number: `(list/take plan.milestones cap)`, `:max cap`, and `{cap}` as a prompt fill |
| What gates a loop | Add or remove the check wrapper (two lines) or the review call | The same; "every milestone met" becomes a gate (`list/all`) |
| How a document reaches a call | `:path` or named in the prompt; `:doc` is unsafe | `:path` or `:snapshot`: one token |

Two answers the table gives. Inputs with literal defaults are the form to
prefer for model and effort: a harness sets them without touching source, a
mutated program is self-contained, and the edit is one token; a literal in
the role's line is for a person changing a role in the middle of a run, since
an edited default cannot be resumed (§4.2). And model and effort were already
one-token edits: what binding a role once changes is the structural rows. The
first space the owner selected (one model, an effort per role) is three such
tokens; it needs per-role effort inputs, which today's language already
allows, and nothing else from this design. Points of that space differ in
tokens per call, so they are compared by priced tokens, not by calls.

## 10. Fit With Surface Coherence, And What Stays

| Sentence | Effect of this design |
| --- | --- |
| 1. Effects | Unchanged. A prompt application is pure; its operands follow the sentence |
| 2. Iteration | Unchanged; the cap exception is kept word for word. `(list :of T)` is a source like any other |
| 3. Callables | Amended: after "a procedure reference is a compile-time name" add "and so are a prompt value and a provider"; the exception "a macro is not a callable" gains "and may not contain an effect" |

| Left alone | Why |
| --- | --- |
| The serial map running `:max` items and then failing | Frozen: a run recorded past that point must resume |
| `agent` as it is | It already binds model and effort for a conversation; a fresh mode would make a turn's effect class depend on a value |
| Literal timeout for phased delivery | Its deadline starts before inputs are read |
| `:doc` | The refusal for an outside edit is what it is for |
| Workflow input defaults as literals | A default that names another input adds evaluation order to a signature; the role line covers the need |
| Stored or chosen prompt values | Needs a run-time representation; no consumer |

## 11. Feasibility, Compatibility And Identity

| Change | Evidence | Result |
| --- | --- | --- |
| T | Prototype, 3 files | A timeout from an input, a `let*` name, a procedure parameter, a `bind-proc` argument and on an agent turn builds; one from an input and one bound by `bind-proc` run; a computed expression, a `String` and a literal `0` refuse; a run with an input of `0` refuses before launch with no provider call |
| L | Prototype of `:of`, 2 files | Builds and runs as a `let*` binding, a loop's initial state and an operand; `(list :of String)` in a field has the digest of `(list)` |
| O | Prototype, 4 files | The three operators run, also in a `defun`; a list of nine under `list/take … 8` and `:max 8` completes |
| P | **Not built in the compiler.** `lower.py` rewrites the role idiom into the specializations §4.2 describes, which today's compiler (with T) accepts | The three seeds, lowered, build and pass all 14 scenarios of the seed's own demo with the stand-in, kills and resumes included, with the call and conversation counts of the originals. Unknown: the cost and the diagnostics of the specialization pass itself |
| S | Reading only | The retained prompt has the recorded digest; the confined profile already replays from an attempt snapshot |

**Nothing that compiles today moves.** T, L and O admit source that is refused
today and touch no path of source that compiles. Checked with the three
invariants of the [stage 3 plan](../plans/2026-11-12-lane-d-stage-3-old-ir-stack-plan.md)
on the prototype commit `fd527d04` against its base `4bae0a7c`, both exported
to one path: the corpus snapshot (55 rows, 11 built), the compile of all 634
tracked `.orc` files (45 build) and the run-reference digests (128 programs)
are byte-identical; the hashes are in the plan under "Baselines recorded
while planning". Two tests flip, both asserting a refusal this design removes
(`test_timeout_provider_call_policy_enforces_literal_type_and_positive_domain`,
one case; `test_list_traversal_authored_head_inventory_is_exact`). P changes
the meaning of no source that compiles: a prompt application outside `:prompt`,
`Prompt[T]`, a `Provider` parameter, a call through a generic reference and an
`Agent` in `bind-proc` are all refused today. Under the versioning rule no
change adds a target; each gets an entry in the spec's change list.

**Diagnostics.** Nothing legal today becomes refused. New codes, all for
source that is refused today under another code: `prompt_value_escape`,
`provider_timeout_nonpositive`, `list_item_type_invalid`. Narrowed:
`provider_result_timeout_literal_required` (a computed expression, or a phased
call); `list_empty_type_context_required` (fewer positions);
`let_proc_capture_agent_forbidden` (`let-proc` only);
`provider_result_provider_invalid` and `generic_union_not_generic` no longer
fire for a `Provider` parameter and for `Prompt[T]`.

**Seed sizes** (lines; code lines at most 129 characters; "per-role inputs" is
today's language with a model and an effort per role as inputs with defaults,
compiled on `main`):

| Seed | As written | Per-role inputs | I1, I2a | L | P | O (gate) | After |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `staged.orc` | 40 | 42 | −1 | −1 | −1 | 0 | 39 |
| `milestones.orc` | 49 | 53 | −7 | −1 | −2 | +1 | 44 |
| `roles.orc` | 49 | 53 | −7 | −1 | +4 | +1 | 50 |

The two end points are compiled (the per-role inputs on `main`; the result
through `lower.py` on the spike); the columns between them are an attribution.
The gate line is the `let*` binding the defect of §2 forces; without the
defect it is 0. In `roles.orc` each role is an `agent` line and a binding
line, and `agent` already made each turn one line: P costs lines there.

## 12. Verification

Scenarios each change adds, through the public command line with stand-ins:

| Change | Scenario |
| --- | --- |
| T | A timeout from an input reaches the launch and the `policy` part; `0` from an input refuses before `started`; a run recorded with a literal resumes unchanged; a phased call with a name refuses |
| L | `(list :of T)` in each position of §2's row 3; equal digests where `(list)` compiles today; `(continue (list))`, `(count (list))` on a `defun` and a `match` arm build |
| O | Each operator's edge cases; nine items under `list/take` complete and a run recorded before the change that failed at the cap resumes to the same code |
| P | `ask` bound three times and called at five sites, in a loop and in a map body: distinct identities, the recorded `policy` of the program written in place, byte-equal prompts; killed between two role calls, resumed with one dispatch; one role's literal edited: the plan's cut is that role's first step; a role over an `Agent` in a parallel map body refuses; each position of §4.1's last row refuses; `--max-cost-usd` refuses an unpriced model before launch |
| S | The living-document run of §2 resumes with `:snapshot`, for a provider and for an agent turn; an outside edit of a `:doc` file still refuses; retained bytes altered refuse |

## 13. Changes And Their Dependencies

| Change | Where | Depends on |
| --- | --- | --- |
| T | `wl/typecheck_effects.py`; `contracts/closed_program/check.py`; `workflow/evaluated/providers.py` | — |
| L | `wl/expressions.py` (`_elaborate_list_constructor`); `wl/typecheck_structural_values.py`; `wl/typecheck_dispatch.py`; `wl/wcc/elaborate.py` | C1 (a keyword in a positional form gets one diagnostic); reads best with I2a |
| O | `workflow/pure_expr.py`; `wl/typecheck_pure_ops.py`; `wl/wcc/elaborate.py`; `wl/result_guidance.py`; `orchestrator/py/trace.py` | — |
| P1 | `wl/type_env.py`, `wl/expressions.py`, `wl/prompts.py`: the type and the application as an expression | E1 (the same elaboration functions) |
| P2 | `wl/procedure_typecheck.py`, `wl/procedure_specialization.py`, `wl/closed/names.py`, `wl/typecheck_effects.py`: `Prompt[T]` and `Provider` parameters | P1, T |
| P3 | `wl/procedure_typecheck.py`, `wl/procedure_refs.py`: generic references | P2; C1 (a local called by name is the same alias path) |
| P4 | `wl/procedure_refs.py`, `wl/typecheck_agents.py`, `wl/closed/agent_effects.py`: `Agent` in `bind-proc` | P3 |
| P5, P6 | `wl/stdlib_modules/…/std/ask.orc`; the documents of §14 | P3; the stage 4 cut decides the library's target; the corpus plan's reference test |
| S | `wl/prompts.py`, `wl/closed/effects.py`, `contracts/closed_program/check.py`, `workflow/evaluated/providers.py`, `effect_inputs.py`, `agent_turns.py` | P1 (the fill rule of §4.3) |

## 14. Where The Rules Live

This document is retired to Historical when the receiving entries below carry
each rule with its exception list, the listed text is gone, and each change of
§13 is implemented or dropped.

| Rule | [Frontend specification](workflow_lisp_frontend_specification.md) | [Guide](../lisp_workflow_drafting_guide.md) | Text that leaves |
| --- | --- | --- | --- |
| 1 | §8.7.1 `defprompt`: the type, the positions, the fill rule; §22.6: `:prompt` takes a value | The prompts section, one paragraph | §8.7.1 "is not a runtime value … its only use is one fully applied named application"; §22.6 "nested, or value-position applications fail closed" and "does not add residual prompt values … procedure/provider substitution" |
| 2 | §7.8 "Procedure References": generic references, `Provider` and `Agent` arguments; an entry for `ask` in the library reference | A "Roles" recipe | Agent Sessions "implicit `let-proc`/`bind-proc` capture" becomes `let-proc` only |
| 3 | §22.4 "Call-Local Provider Policy" | One sentence | "requires an integer literal" |
| 4 | §10.3: the `list` entry | The loops section | The carrier as the only way |
| 5 | §10.2: three rows of the operator table | One paragraph on meeting a map's cap | — |
| 6 | §8.7.1 slot kinds; §22.6 delivery | The guidance of §8 here replaces "pass the path" | — |

`specs/providers.md` gains the timeout operand and the `:snapshot` binding;
`specs/dsl.md` and `specs/versioning.md` one change-list entry per change;
evaluated execution §7.3 states the host snapshot beside the confined one.

## 15. Open Decisions For The Owner

| # | Question | Recommendation | Cost of each answer |
| --- | --- | --- | --- |
| 1 | P as decided costs about 8 days and four capabilities; a provider binding with options costs about 2 and gives the edits of §9, the scope switch as one word. Proceed with P? | Yes, as decided: prompt values and generic partial application serve more than roles. Review P3 as the general change to procedure references that it is; T, L and O do not depend on P and can land beside it | Yes: the specialization pass grows and is the riskiest work here. No: a second policy form beside `agent`, and prompts stay second-class |
| 2 | May an `Agent` be a `bind-proc` argument (amending Agent Sessions)? | Yes, explicit only, with the two guards | Yes: one more position the parallel check must cover. No: a continued role passes its agent at every call, so fresh or continued is again an edit of each site |
| 3 | The name and the trade of `:snapshot` | Accept; the name says what resume does | Yes: outside edits to declared living documents go unreported for finished steps. No: `:path` only; a document cannot be delivered as content to a step whose file later changes, and `:doc` keeps stranding agent runs |
| 4 | `list/take` beside `list/length` and a computed `:max` | Accept all three operators | No: a seed must refuse a long plan and replan, at the price of one planning call's tokens |
| 5 | Fix the loop-condition defect (§2, D) and the `match`-arm defect here? | Yes, as the first task; both block natural spellings of rules 4 and 5 | Deferred: a `let*` line per use |
| 6 | Should `report` shorten the bracketed digest in step names? | Not here; raise with the dashboard | — |
