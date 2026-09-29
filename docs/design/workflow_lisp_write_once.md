# Workflow Lisp: Writing Each Fact Once

## Metadata

- **Status:** proposed target; not implemented and not current syntax
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

That document lists what must be decided before implementation: the target,
name resolution of effect subjects in the defining scope, how the origin of
an authored restriction is carried through specialization, mixed-target
linking, and the editor projection of inferred effects. This design adds one
decision: W2 takes the same target as W1, W3 and W4.

`:lowering` is not part of W2. The clause is optional today. Its default,
`auto`, may choose a private workflow for a procedure with several call
sites, which changes state and resume namespaces. `:lowering inline` records
a choice and stays.

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

`let-proc` defines one local procedure with an explicit capture list. Three
extensions:

1. **Several bindings.** One `let-proc` form binds several local procedures.
   None may refer to another or to itself. Order is source order.
2. **Inferred captures.** When `:captures` is omitted, the captures are the
   free identifiers of the body that are bound in the enclosing scope. An
   authored `:captures` list stays valid and is checked as an upper bound: a
   body that uses a name outside the list is rejected.
3. **Signature from the expected type.** When a local procedure is passed
   directly to a parameter of type `ProcRef[…]`, its parameter types and its
   return type may be omitted where that type fixes them. A type parameter of
   the callee that the local procedure's body determines is bound from the
   body's type.

Captures remain compile-time. The local procedure is converted into a private
procedure specialized with its captures, as today. No runtime closure is
introduced.

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

### 6.6 Dependency

The measured workflow also lost four lines because a nested `if` inside a
hook is rejected, and could not return its own outcome union because a pure
`match` over the helper's result is rejected. Both are compiler defects
recorded in the
[value/effect separation decision brief](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md).
W3 does not repair them.

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
supplies is rejected at compile time with `provider_parameters_missing`.

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
- W1, W2, W3 and W4 enter together at one new target. Older targets accept
  and lower what they do today.
- The change to `improve` in 6.4 replaces its signature; a standard-library
  procedure has one signature. Its one caller, the shipped example, changes
  with it. `std/improve` moves to the new target.
- A program that uses none of the new forms and moves to the new target keeps
  its lowered output.

## 10. Rejected Alternatives

| Alternative | Reason |
| --- | --- |
| General type inference (Hindley-Milner), annotated `let*`, type ascription | The accepted list design excludes them, and W1 needs none: every position in 4.2 has a declared type |
| Resolving a bare variant tag by searching the visible unions | Ambiguous at thirteen of thirty-three sites |
| A result-type clause on `loop/recur` | The loop takes its expected type from its position. A loop bound by `let*` writes its constructors in the explicit form |
| Runtime closures | Owned and excluded by the runtime closures boundary; compile-time capture suffices |
| Provider options as module-level defaults in the program | Model and effort are deployment choices; a program would have to change to run elsewhere |
| Removing `:lowering` | It records a choice of state and resume namespace |
| Replacing `Decision[F B]` by constraints now | No measured caller needs it; section 8.4 |

## 11. Evidence Requirements

Each rule is accepted on these measurements, taken with the scripts of the
census on the same corpus and on the rewrite of `reviewed_change.orc`.

| Rule | Requirement |
| --- | --- |
| W0 | No declaration in the corpus repeats, with identical text, one that an importable module exports. Every name declared with differing text in several files is unified or renamed. Lines of type declarations fall by at least 200 |
| W1 | Every constructor at a position of 4.2 compiles without its type name and produces build artifacts identical to the explicit form, for the corpus and for generic bodies inlined across modules |
| W2 | The acceptance lanes of the effect ledger simplification design |
| W3 | The helper variant of `reviewed_change.orc` keeps every behaviour of the original and is at least 10 % shorter than the hand-written variant in code lines. If it is not, the changes of 6.3 are not adopted |
| W4 | No call in the corpus sets an option that equals its binding's default. Build artifacts of a workflow are identical whether an option is written on the call or taken from the binding |
| All | Older targets: byte-identical build artifacts. Compile, run and resume through the public entry for each new form |

## 12. Feasibility Obligations

Each is an open prerequisite until its fixture passes.

| Claim | Fixture |
| --- | --- |
| The expected type can be passed through `let*` bodies, `with-phase` bodies, `done`, `continue` and `:on-exhausted` without changing the type of any program that compiles today | The corpus compiles to identical artifacts with the expected type threaded and no program using the new forms |
| A loop receives an expected type from its position | A loop at a workflow tail whose `done` and `:on-exhausted` values omit the union name |
| A constructor without its type in a generic body lowers like the explicit form when the body is inlined in another module | `std/improve` rewritten with `(variant APPROVED …)`, called from a module that does not import `Improvement` |
| Captures can be inferred without capturing a name the author did not intend | A local procedure whose body uses a name bound both in the enclosing scope and as its own parameter; the parameter wins, and the capture list shown by the compiler matches |
| A local procedure's signature can be taken from the expected `ProcRef` type while the callee's type parameters are still being bound | `improve` called with `initial` of a record type and two local hooks without written types |
| Binding defaults reach supervision, peer-group and adjudication calls | One call of each kind with options only on the binding |

## 13. Relationship To The Execution Model

W0 to W5 act on declarations, the typechecker, elaboration and provider
configuration. None depends on how a compiled workflow is executed, and none
is changed by the choice recorded as open in the value/effect separation
decision brief.
