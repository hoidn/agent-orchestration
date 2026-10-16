# Workflow Lisp: Writing Each Fact Once

## Metadata

- **Status:** W3 is implemented at target 2.36; W2 is delivered by EL-1 at
  target 2.39. W0/W1/W4 remain unselected proposals and W5 remains deferred.
- **Kind:** language and standard-library contract, with one authoring rule
  that needs no language change
- **Owner:** Workflow Lisp frontend
- **Created:** 2026-09-29
- **Evidence:** [repetition census](../reports/2026-09-29-workflow-lisp-repetition-census.md)
- **Plan:** [repetition reduction plan](../plans/2026-09-29-workflow-lisp-repetition-reduction-plan.md)
- **Related:**
  [design principles](workflow_language_design_principles.md) 15, 25, 26, 29
  and 30,
  [effect ledger simplification](workflow_lisp_effect_ledger_simplification.md),
  [local ProcRef bindings](workflow_lisp_let_proc_local_proc_refs.md),
  [parametric type system](workflow_lisp_parametric_type_system.md),
  [composition-first procedures](workflow_lisp_composition_first.md),
  [pure list traversal](workflow_lisp_pure_list_traversal.md)

## 1. Summary

An author states a fact at the declaration that owns it. Every other place
derives it. Six rules apply that idea to the repetition the census measured.

| Rule | The fact | Stated once at | Derived at |
| --- | --- | --- | --- |
| W0 | A type's definition | The module that exports it | Every module that uses it, by import |
| W1 | The type of a constructed value | The declaration that fixes the position's type | The constructor |
| W2 | The effects of a procedure | The effectful forms in its body | The procedure's summary |
| W3 | The context a hook needs | The enclosing scope | The hook, by capture |
| W4 | The options of a provider | The provider binding | Each call to that provider |
| W5 | What a helper needs from a caller's union | The helper's constraints | The caller's own union |

The rules are ordered by measured repetition removed. W0 needs no language
change and removes the most.

## 2. Principles That Govern This Design

| Principle | Consequence here |
| --- | --- |
| 29. Constraints over names; structurally sufficient shapes are admissible without re-wrapping | W3 and W5. A helper must not make a caller build records or unions only to satisfy its signature |
| 29. Nominal types where names carry contracts | Outcomes that callers route on stay nominal. W5 does not apply to a helper's result |
| 15. Explicit to validation and IR does not mean handwritten on every wrapper | W2 |
| 30. An obligation the deterministic side can carry is not the author's | W1, W2 and W4 |
| 25. Lints detect semantic smells | W0 is enforced by a lint |
| 26. A construct that only reduces punctuation is not sufficient | Each rule names the correctness burden it removes. A rule with none is rejected |

## 3. W0: A Declaration Is Imported, Not Repeated

### 3.1 Rule

A module does not declare a record, union, path family or enum that a module
it can import already exports with the same definition.

### 3.2 Ownership

- The standard library owns the types its procedures use. `std/phase` already
  exports the review report paths, `BlockerClass` and `ReviewFindings`.
- A type shared by workflows of one family and unused by the standard library
  is owned by one module of that family, which exports it.
- A type used by one module stays in that module.

### 3.3 Same name, different definition

`DesignDocPath`, `BlockerClass` and `ReviewDecision` are declared in five to
seven files with differing text. Records and plain unions are compatible by
short name and shape, so two definitions under one name can be confused for
one another wherever a value crosses modules. Each such name is resolved one
of two ways: the definitions are unified and imported, or the differing one
is renamed for what it means.

### 3.4 Lint

`declaration_repeats_importable`, a warning: a local declaration has the same
definition as one exported by the standard library or by a module the file
already imports. The message names the module to import from.

### 3.5 Correctness burden removed

Copies of one contract drift apart. The census found eleven enum
declarations that repeat a name, and ten of them differ.

## 4. W1: Construction From The Expected Type

### 4.1 Rule

Where a declaration fixes the type of a position, a constructor may omit the
type name.

```lisp
(record :title "draft" :score 0)
(variant APPROVED :value state.current :evidence a.evidence)
(variant EMPTY)
```

The explicit forms `(record T …)` and `(variant U V …)` stay valid everywhere
and mean what they mean today.

### 4.2 Positions that carry an expected type

| Position | Expected type comes from |
| --- | --- |
| Tail of a procedure or workflow body | The declared return type |
| Body of `let*` and of `with-phase` | The position of the enclosing form |
| Arm of `match`, `if` or `cond` | The position of the enclosing form |
| Value of `done` and of `:on-exhausted` | The expected type of the enclosing `loop/recur` |
| Field of `loop-state`, and of `loop-state :like` under `continue` | The field's declared type |
| Field value inside a constructor | The field's declared type |
| Argument of a call | The parameter's declared type, when it contains no type parameter of the callee |
| Request of a resource transition | The transition's declared request type |

### 4.3 Positions that carry none

A `let*` binding, a `match` subject, and an argument whose parameter type
contains a type parameter of the callee. In these positions a constructor
without a type name is rejected with `constructor_type_context_required`,
which names the position and shows the explicit form.

This design adds no annotated binding, no type ascription form and no
inference beyond passing a declared type down to the forms listed in 4.2. It
follows the rule already accepted for the empty `(list)`.

### 4.4 Variant tags

A tag without a union name is resolved against the expected union only. The
compiler never searches the visible unions for a tag: thirteen of
thirty-three variant constructor sites in the census write a tag that more
than one visible union declares. A tag the expected union does not declare is
rejected with `constructor_variant_not_in_expected_union`, naming the union
and its tags.

### 4.5 Syntax

| Form | Read as |
| --- | --- |
| `(record :k v …)` | Record of the expected type. The first element is a keyword |
| `(record T :k v …)` | Record of type `T`, as today |
| `(variant V :k v …)` and `(variant V)` | Variant `V` of the expected union. One symbol, then keywords or nothing |
| `(variant U V …)` | Variant `V` of union `U`, as today. Two symbols |

Inside `trial` sections `(record :key value)` is untyped compile-time data.
That context has its own parser and is unchanged.

### 4.6 Generic bodies

In a generic body the expected type is a resolved type reference, for example
the declared return type `Improvement[S F B]` under the specialization's
bindings. The constructor takes that reference. It carries no type text to be
resolved again where the body is inlined.

### 4.7 Lowered output

A constructor written without its type lowers to exactly what the explicit
form lowers to: the same typed node, the same steps, the same identities.
Replacing one spelling by the other changes no build artifact.

### 4.8 Correctness burden removed

- A type name at a constructor can only agree with the declaration or be an
  error. It carries no information.
- Type text in a generic body is resolved a second time in another module
  when the body is inlined. That produced the defect in which a generic
  procedure could not construct a union over its own type parameter.

### 4.9 What it does not remove

Lines. The census counts 1,583 characters at 76 sites and no whole line.

## 5. W2: Effects Are Inferred

This design adopts
[effect ledger simplification](workflow_lisp_effect_ledger_simplification.md)
without change: an omitted `:effects` clause means the inferred set; an
authored clause is an upper bound that is checked; an explicit empty clause
asserts no tracked effect, also after specialization.

EL-1 delivers this contract at target 2.39, including defining-scope subject
resolution, restriction-origin preservation through specialization/imports,
and compiler-derived inspection. W1 and W4 retain their own unselected
proposals; W3 is separately implemented at 2.36. No shared future target is
required to use W2.

The same 2.39 frontend contract rejects authored `:lowering` and makes new
procedures caller-owned inline composition. Imported definitions originating
at 2.35–2.38 retain their mandatory/exact effect rules, specialization
exceptions, and declared/default lowering policy. At those older origins,
`:lowering inline` still records caller-owned identity. An intentional boundary
in new 2.39 source uses `defworkflow` plus `call`, with concrete transportable
inputs/results; converting an old private procedure creates a new identity
and does not promise cross-version resume.

Correctness burden removed: a change to a helper's body forces an edit to the
`:effects` clause of every procedure that calls it, directly or not.

## 6. W3: Hooks See Their Context

### 6.1 The problem

A helper that takes procedures as hooks passes them only what its signature
names. `improve` therefore has a parameter `inputs I` whose only purpose is to
carry the caller's context to the hooks. The caller packs its inputs into a
record, declares the record, and restates it in every hook signature. In the
measured workflow that is one record of four lines, one constructor, and the
types `S`, `I` and `F` written eleven times.

### 6.2 Rule

A hook is a local procedure that captures the names it uses from the scope
where it is written. A helper's signature names only what the helper itself
reads or produces.

### 6.3 Language changes to `let-proc`

Through target 2.35, `let-proc` defines one fully annotated local procedure with an explicit
capture list. W3 at target 2.36 extends the existing representation and
specialization path; both spellings have one consumer expression:

```lisp
(let-proc
  (name ((arg ArgType)) -> ResultType :captures (context) body)
  consumer)
(let-proc
  ((review (candidate) body)
   (revise (candidate feedback) body))
  consumer)
```

A binding is `(name (parameter ...) [-> ReturnType]
[:captures (name ...)] body)`, with clauses in that order. A parameter is a
bare name or `(name Type)`; omitted types require the bounded expectation
below. The outer list spelling starts with a list, rather than a name.
Empty lists, duplicate local/parameter names and malformed clauses are
located errors. The three extensions are:

1. **Several bindings.** One `let-proc` form binds several local procedures.
   None may refer to another or to itself. All bodies see the same creator
   environment; only the consumer sees local ProcRefs. Source order governs
   declarations and diagnostics, not inference success.
2. **Inferred captures.** When `:captures` is omitted, the captures are the
   free identifiers of the body that are bound in the enclosing scope. An
   authored `:captures` list is a checked upper bound: reject missing used
   names, unknown entries and duplicates. Capture field roots, and lexical
   ProcRefs used as callees, with parameter/local-binder shadowing applied;
   top-level procedures, types, field labels and declared provider/prompt
   externs are not captures. Externs remain available when typing the body;
   actual lexical Provider/Prompt parameters or aliases remain eligible only
   under existing admission rules, without new runtime capability transport.
   Resolve values and their lexical binding identities in the creator scope.
   At 2.36, both spellings retain only used captures, ordered deterministically
   by resolved name, including when an explicit list is a reordered superset.
   Existing targets retain authored capture order and behavior.
3. **Signature from the expected type.** When a local procedure is passed
   directly to a parameter of type `ProcRef[…]`, its parameter types and its
   return type may be omitted where that type fixes them. A type parameter of
   the callee that the local procedure's body determines is bound from the
   body's type. If any residual parameter type or return type is omitted,
   the local requires exactly **one authored direct consumer call site** in
   the complete lexical consumer body. Several direct `(proc-ref local)`
   arguments of that call share one site and must satisfy every expectation;
   loop iterations and other repeated runtime activations are still one site.
   Zero sites, two authored calls (including alternative branches), or a local
   ProcRef literal outside a direct procedure-call argument position are refused
   before consumer typechecking. Aliases, `bind-proc`, conditional values and
   returned values do not transport an enclosing call's expected signature to
   an incomplete local. A direct call's own resolved parameter signature may
   complete the local even when that call returns its reference; existing
   nonescape checks still apply to the complete `let-proc` consumer. A resolved
   lexical ProcRef callee supplies its residual signature under the same rule.
   Fully annotated signatures retain ordinary reuse and forwarding, even with
   inferred captures.

At the one eligible call, check arity, then type ordinary arguments and fully
annotated ProcRefs, then bind the callee's type parameters through the existing unifier.
Group pending occurrences by lexical local binding and collect all expected
positions before checking a body. A local becomes ready when every residual
parameter type is concrete, from annotations or expectations. Type its body
once in its creator environment plus parameters, using a concrete expected
return when available; otherwise infer its ordinary result and unify it with
the expected return. New bindings may make another local ready. Repeat until
complete or no progress; reject missing/conflicting expectations with located
diagnostics requesting explicit annotations. Do not guess, backtrack, choose
the first occurrence's signature or cache evidence across authored calls.
The review/revise pair resolves `S` from `initial`, `F/B` from review's result,
then revise's `S/F` parameters, regardless of declaration/argument order.
Constructors and effect restrictions keep their existing rules.

Count direct sites by structural occurrence paths within this consumer,
resolved to its lexical local bindings, before rewriting/specialization.
Names, equal spans, AST object identity, normalization copies and runtime
activation counts are not site identities. Disjoint same-named locals remain
separate. Any temporary pending-local/site state is compile-scoped and
restored on exit; completed signatures feed existing generated definitions,
ProcRef binding and specialization before closed-program construction.

Captures remain compile-time. The local procedure is converted into a private
procedure specialized with its captures, as today. No runtime closure is
introduced.

Captured values retain their defining lexical binding; a later invocation-site
binder cannot replace them. A parameter shadows an enclosing name and is not
a capture. Capturing an already computed effect result forwards its value
without evaluating the effect again, including across committed-boundary resume.
Missing or conflicting expected signatures require explicit types with a
located diagnostic. Multiple bindings do not permit sibling calls, recursion,
nested local-procedure definitions or runtime dispatch. W3 does not change
effect-annotation rules; those remain W2's separate responsibility.

### 6.4 Standard library change

`improve` loses `inputs I`.

```lisp
(defproc improve
  :forall (S F B)
  ((initial S)
   (review ProcRef[(S) -> Decision[F B]])
   (revise ProcRef[(S F) -> S])
   (limit Int))
  :where ((S is-record))
  -> Improvement[S F B]
  …)
```

A caller that has top-level hooks with a context parameter applies them
partially with `bind-proc`, which exists today.

### 6.5 Correctness burden removed

Manual state management: a record that exists only to move values the hooks
could read directly, and a constructor that must list every one of them.

### 6.6 Before And After

Illustrative fragments; domain types, agent operations, imports and effect
annotations are omitted in both versions, so these fragments are not standalone
programs. The after form uses the selected 2.36 grammar and the single authored
call that supplies both incomplete hooks' expectations. The maintained
[proposal recipe](../lisp_workflow_drafting_guide.md#137-improve) supplies the
actual provider bodies, imports and execution prerequisites.

```lisp
; Before: context is packed solely for the helper to forward.
(defrecord ReviewInputs (goal String) (rubric String))
(defproc review ((candidate Proposal) (inputs ReviewInputs))
  -> Decision[Feedback Blocker]
  (review-agent candidate inputs.goal inputs.rubric))
(defproc revise
  ((candidate Proposal) (inputs ReviewInputs) (feedback Feedback))
  -> Proposal
  (revise-agent candidate feedback inputs.goal))
; Inside the caller, with initial, goal and rubric in scope:
(improve initial (record ReviewInputs :goal goal :rubric rubric)
  (proc-ref review) (proc-ref revise) 3)

; After: each local hook uses its enclosing lexical context.
(let-proc
  ((review (candidate)
     (review-agent candidate goal rubric))
   (revise (candidate feedback)
     (revise-agent candidate feedback goal)))
  (improve initial (proc-ref review) (proc-ref revise) 3))
```

`review` captures `goal` and `rubric`; `revise` captures only `goal`.
`Proposal` comes from `initial`; the review result supplies the feedback and
blocker types, including the expected feedback parameter of `revise`.
Reusing either incomplete local at a second authored call is refused; write
its full signature or use distinct local bindings for that call. For example,
`need<T>(ProcRef[(T)->T])->Int` and
`seed<T>(T, ProcRef[(T)->T])->Int` cannot infer one `h(x)=x` shared by
`need(h)` and `seed(1,h)` in either order. Fully annotating `h` as
`(Int)->Int` admits both calls through existing rules.
Adding another enclosing value used by one hook requires no context-record,
constructor or helper-signature edit. Records with independent domain uses
remain domain values; only forwarding scaffolding is removed.

### 6.7 Execution Prerequisites

The [composition-first contract](workflow_lisp_composition_first.md#11-known-defects-and-rules-at-target-233)
records current-route placement limits and the remaining live-provider
settlement-capture defect. The [pure correction report](../reports/2026-10-07-workflow-lisp-pure-capture-correction.md)
records the repaired creator-scope/duplicate-producer cases and their bounded
compatibility evidence.
The maintained target-2.39 proposal and target-2.36 reviewed-change fixture
exercise lexical captures, final values and committed-boundary resume through public CLI
harnesses in `tests/test_workflow_evaluated_consumers.py`. Exact compatibility
and package-bound phase qualification evidence are recorded in the
[closeout](../reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md).
Successful specialization or an illustrative rewrite does not establish
general composition coverage. The exact remaining evaluated composition
limits are scoped in [composition-first §11.4](workflow_lisp_composition_first.md#114-evaluated-w3-boundaries).

## 7. W4: Provider Options Are Bound Once

### 7.1 Rule

A provider binding may carry default call options. A call may override any of
them. A call that sets none uses the binding's.

### 7.2 Surface

The provider externs file accepts, for each name, either a provider template
name, as today, or an object:

```json
{
  "providers.coder": {
    "provider": "claude_unrestricted_workspace",
    "model": "claude-sonnet-5-5",
    "effort": "medium",
    "timeout_sec": 5400
  },
  "providers.reviewer": "codex_unrestricted_workspace"
}
```

Model, effort and time limit are choices of a deployment, so they belong with
the binding and not in the program.

### 7.3 Order of precedence

The call's own option, then the binding's default, then the provider
template's default. A parameter the template requires and none of the three
supplies fails the call when it is reached, with `provider_preparation_failed`
(the flat route's compile-time `provider_parameters_missing` check was retired
with that route on 2026-10-13).

### 7.4 Identity

The options in force at a call are part of the compiled call, as they are
when written on the call. Changing a binding's default changes the build
artifacts of the workflows that use it, and a resume detects it as a source
change.

### 7.5 Correctness burden removed

Copies of one setting drift: three calls to one provider with three sets of
options, by accident.

## 8. W5: A Helper Constrains, It Does Not Name

### 8.1 What exists

A helper can already accept a caller's own union:

```lisp
(review ProcRef[(S) -> D])
:where ((D has-union-variant APPROVE (evidence F))
        (D has-union-variant REVISE (feedback F))
        (D has-union-variant BLOCKED (reason B)))
```

This compiles today when every type parameter in a constraint also appears in
a parameter or `ProcRef` position.

### 8.2 Language change

A type parameter that appears only in constraints is bound by them. When
`(D has-union-variant BLOCKED (reason B))` is checked against the union bound
to `D`, `B` is bound to the declared type of `reason`. Two constraints that
bind one parameter to different types are rejected.

### 8.3 Scope

W5 applies to what a helper receives. What a helper returns stays nominal:
callers route on it with proof, which is the case principle 29 reserves for
names.

### 8.4 Condition for adoption

The census found six decision unions with three spellings of the request for
changes and two of the blocking variant. A constraint matches by variant
name, so W5 helps only unions that already use the names the helper asks
for. W5 is adopted when a caller, after W0 to W4, still needs an adapter
between two unions of the same shape. Until then the existing generic unions
serve.

## 9. Targets And Compatibility

- W0 applies to every target. It changes no language rule.
- W1 and W4 retain their separate unselected target proposals. W2 uses the
  delivered 2.39 EL-1 contract and preserves imported 2.35–2.38 semantics. W3 is
  selected for 2.36 on the evaluated route and implemented;
  the [closeout](../reports/2026-10-07-evaluated-execution-phase-4c-w3-closeout.md) owns qualification evidence. Existing targets retain their
  admitted syntax and lowering.
- One `std/improve` API is selected for each **source import graph** by its
  entry target. Admitted entries at 2.35 use the five-argument
  `stdlib_modules/std/improve.orc` bytes and path. At 2.36 (and later supported
  compatible targets), replace only that builtin candidate with the no-context
  `stdlib_modules/w3/std/improve.orc`, using its actual alternate source root.
  Both packaged variants have source header 2.35 and retain that origin’s
  effect/lowering rules, including in 2.39 graphs. Syntax admission still
  follows each defining module. Other imports and user-root ambiguity rules are unchanged;
  do not expose both builtin variants or adopt first-match resolution.
- Every source module in a new graph sees that one API. Retargeting requires
  migrating any source dependency that still calls five-argument `improve`,
  with a located migration diagnostic. Every source module and typed-program
  capsule in the transitive import closure must meet the 2.35 floor; older
  type-only source or capsule bytes are not admitted. Among admitted origins,
  preserve existing compatibility rules.
  Inventory source producers, fixtures and indirect callers as well as `.orc`
  imports. No parallel `improve-v2`, per-importer versions or hidden old-call
  rewriting is part of W3.
- Complete imported snapshots retain their producer's checked authority;
  graph selection does not reopen or retarget their sources. A sole old
  `std/improve` snapshot authority remains valid. Differing canonical overlap
  retains the existing `compiled_workflow_snapshot_conflict` refusal.
- Preserve old module/source identities and resume recipes. Prove raw old-target
  artifact identity with fixed paths, seed and identity inputs, and actual
  resume of a compatible retained run. Truthful package/command-closure pins
  and the program-digest guard remain authoritative; genuine pin changes and
  retargeted/migrated source may correctly refuse. Refusal alone is not proof
  of successful checkpoint compatibility, and W3 promises no unconditional
  resume after a package upgrade.
- Inferred and explicit forms have equivalent semantics and canonical output
  on the same execution route. Cross-route checks compare values, effects and
  resume behavior, not flat artifacts with closed-program artifacts.

## 10. Rejected Alternatives

| Alternative | Reason |
| --- | --- |
| General type inference (Hindley-Milner), annotated `let*`, type ascription | The accepted list design excludes them, and W1 needs none: every position in 4.2 has a declared type |
| Resolving a bare variant tag by searching the visible unions | Ambiguous at thirteen of thirty-three sites |
| A result-type clause on `loop/recur` | The loop takes its expected type from its position. A loop bound by `let*` writes its constructors in the explicit form |
| Runtime closures | Owned and excluded by the runtime closures boundary; compile-time capture suffices |
| Provider options as module-level defaults in the program | Model and effort are deployment choices; a program would have to change to run elsewhere |
| Erasing an intentional workflow boundary | At 2.39, use explicit `defworkflow` plus `call`; 2.35–2.38 definitions retain authored lowering policy |
| Replacing `Decision[F B]` by constraints now | No measured caller needs it; section 8.4 |

## 11. Evidence Requirements

Each rule is accepted on these measurements, taken with the scripts of the
census on the same corpus and on the rewrite of `reviewed_change.orc`.

| Rule | Requirement |
| --- | --- |
| W0 | No declaration in the corpus repeats, with identical text, one that an importable module exports. Every name declared with differing text in several files is unified or renamed. Lines of type declarations fall by at least 200 |
| W1 | Every constructor at a position of 4.2 compiles without its type name and produces build artifacts identical to the explicit form, for the corpus and for generic bodies inlined across modules |
| W2 | The acceptance lanes of the effect ledger simplification design |
| W3 | Preserve behavior while removing context-only records/constructors, helper forwarding and restated hook signatures. Review actual callers, capture clarity and edit locality when a hook needs another enclosing value. Report line counts as evidence, not a percentage adoption gate |
| W4 | No call in the corpus sets an option that equals its binding's default. Build artifacts of a workflow are identical whether an option is written on the call or taken from the binding |
| All | Older targets: raw byte-identical artifacts with identical identity inputs; report genuine pin differences separately under §9. Compile, run and resume through the public entry for each new form |

## 12. Feasibility Obligations

Each is an open prerequisite until its fixture passes.

| Claim | Fixture |
| --- | --- |
| The expected type can be passed through `let*` bodies, `with-phase` bodies, `done`, `continue` and `:on-exhausted` without changing the type of any program that compiles today | The corpus compiles to identical artifacts with the expected type threaded and no program using the new forms |
| A loop receives an expected type from its position | A loop at a workflow tail whose `done` and `:on-exhausted` values omit the union name |
| A constructor without its type in a generic body lowers like the explicit form when the body is inlined in another module | `std/improve` rewritten with `(variant APPROVED …)`, called from a module that does not import `Improvement` |
| Captures can be inferred without capturing a name the author did not intend | A local procedure whose body uses a name bound both in the enclosing scope and as its own parameter; the parameter wins, and the capture list shown by the compiler matches |
| Captures retain definition-site values without repeating effects | Two helper calls use distinct inferred locals or fully annotated reused locals and capture different values; later binders cannot change them; an effect-produced captured value is obtained once fresh and reused on committed-boundary resume |
| A local procedure's signature can be taken from the expected `ProcRef` type while the callee's type parameters are still being bound | Typed `initial` and two unannotated local hooks at one call; review fixes revise's feedback type in either declaration/argument order, with one body check per hook. Missing/conflicting expectations produce located diagnostics |
| Signature inference is independent of consumer traversal order | Reject both `need`/`seed` orders for one incomplete local; accept full annotations in both orders. Accept repeated agreeing arguments at one site and repeated activations; reject conflicting same-site expectations, zero/multiple/indirect sites before inference, and isolate disjoint same-name locals |
| Explicit capture restrictions and inference canonicalize equally at 2.36 | Compare canonical definitions/programs for omitted, reordered and superset captures; cover field roots, lexical ProcRef callees and shadowing, preserving old-target authored capture output |
| Removing `inputs I` preserves existing consumers under the selected graph migration | Inventory maintained imports/fixtures; qualify old/new builtin source roots, package/LSP parity, user-root ambiguity, migrated/old/type-only source callers, sole-old snapshots and canonical overlap refusal; prove raw old-target identity and actual compatible retained-run resume |
| Binding defaults reach supervision, peer-group and adjudication calls | One call of each kind with options only on the binding |

## 13. Relationship To The Execution Model

W0 to W5 act on declarations, the typechecker, elaboration and provider
configuration. They add no evaluator. W3 reuses the selected route's ordinary
procedure/capture representation; on evaluated execution that is the
[closed-program definition and capture contract](workflow_lisp_evaluated_execution.md#4-the-closed-program).
Public runtime evidence on that route must establish the behavior above;
compiler acceptance alone is insufficient.
