# Workflow Lisp Checked Program Evaluation

- **Status:** proposed, unselected, unimplemented and not copy-safe.
- **Kind:** a bounded extension to evaluated execution, with one proposed
  authored form. The working name is `eval-orc`; syntax is not settled.
- **Authority:** [evaluated execution](workflow_lisp_evaluated_execution.md)
  (EE) owns the closed program, evaluator and memo; [effect ledger
  simplification](workflow_lisp_effect_ledger_simplification.md) (EL-1)
  owns inferred effects and resolved restrictions.
- **Compatibility:** a target after 2.35, still unassigned. This proposal
  neither widens 2.35 nor changes current runtime-loading restrictions.
- **Selection and delivery:** [roadmap CE-1](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#ce-1--checked-program-evaluation-pending-unselected).
- **Use today:** closed `match` dispatch over authored procedures, or
  `run-ref :path` for an admissible effect-free program at a pinned commit.

## 1. Core idea

Let an agent produce source text, check it with the ordinary compiler, then
evaluate it with the ordinary runtime. The parent fixes its input/result
types, permitted imports, effect bound and execution budget before the run.
A rejected program returns diagnostics the parent can feed into a normal
repair loop. An admitted program gets the same result validation, journaled
effects and resume rules as authored code.

This closes the gap between choosing a prewritten branch and hiding an
agent-written program inside one opaque command. It adds no general runtime
procedure values, closures or second interpreter.

The initial surface is one source-taking operation. Separate checking,
approval tokens, scope declarations/catalogs, library search/promotion and a
Python frontend are outside this proposal. Ordinary imports and ordinary
workflow loops are enough to express the first use case.

## 2. Authored contract

The following is illustrative notation, not valid source:

```text
eval-orc source-text
    entry: run
    inputs: goal = goal
    returns: CampaignResult
    imports: lab/types, selected exports of lab/experiments
    effects: the parent's permitted providers, commands and path writes
    budget: effects and iterations
```

`source-text` is an ordinary `String`, commonly from a committed provider
result. It contains a module body; admission supplies the module identity and
the parent's target. The entry is an exported `defworkflow` whose parameter
names/types and result type exactly match the call's contract. Boundary
types must have the same canonical descriptors as the parent's; a fragment
may define private types, but may not return them across that boundary.

Return one typed outcome with these cases:

| Outcome | Meaning |
| --- | --- |
| Success | The declared result value |
| Rejected | Located compiler/admission diagnostics; no fragment effect ran |
| Faulted | A pure evaluation fault inside the fragment, with its location |
| Exhausted | The reached budget and work count; earlier effects stay committed |

Reuse diagnostic codes, spans and remedies where available; a separate
multi-stage rejection taxonomy is unnecessary. A compiler defect remains
explicitly a compiler defect in both the returned diagnostics and the run's
view. A provider or command that fails to produce a valid result still stops
the run under EE's ordinary effect-failure rules. A caught pure fault does
not roll back prior effects.

Exact keyword names, outcome constructors and serialized layout remain
design decisions. The contract does not require a new source wrapper type,
an exposed compiled-program handle, or a check-then-run protocol.

## 3. Fixed imports and resolved authority

The simplest proposed import boundary is a literal selection of the parent's
ordinary modules/exports, fixed when the parent compiles. Retain their
compiled bodies, type descriptors, owner configuration and logical asset
bases using EE §4.2.1's import ownership rules. Admission can use only those
snapshots. It does not search the live library for newer code or accept
fragment-declared externs, configurations or source roots.

Generated definitions use the parent's approved configuration. Imported
definitions keep their owner's configuration. Selected exports carry their
normal transitive dependencies, but those dependencies do not become extra
exports the generated source may import directly. Their reachable effects
still count against the bound. Conflicting snapshots of one canonical
definition follow the existing refusal rule.

This choice intentionally couples library updates to the parent's normal
program identity. A changed library may require a new run under
`resume_program_changed`; adding late-bound library promotion would be a
separate design. The benefit is one fixed authority to validate against,
without an additional scope language or library-version policy.

The effect bound checks resolved operations, not their authored labels.
For providers and commands, compare the actual binding and owner
configuration to authority derived from the parent. Preserve command closure
and repeat policy. Path writes retain their declared path-type/root contract.
Calls contribute their bodies' effects. Empty bounds admit pure fragments.
An allowed provider's own tool use remains subject to the existing provider
boundary; this is not a sandbox for everything that provider might do.

EL-1 delivers definition-origin-aware effect-subject resolution at 2.39;
reuse it where applicable rather than reopening that decision. Its resolved
provider extern keys and command step labels do not establish this proposal’s
parent binding/configuration authority. CE must still prove that bounds over
resolved closed-program `perform` nodes cannot be bypassed by aliases,
imported owners, adapters, paths or specialized hooks. A command’s step name
alone is never its authority. EL-1 does not implement CE admission or its
closed-operation authority checks.

**Open feasibility obligation:** EE retains reached bodies, not necessarily
every export an `eval-orc` call permits. Prove how the parent stores and
checks the permitted snapshot closure and how admission consumes it without
reopening source or silently substituting owner configuration. Reuse the
existing import representation where possible; do not claim that a static
allow-list alone implements this boundary.

## 4. Admission and execution

Elaborate the form to one internal admission effect followed, only on
success, by evaluation of its stored closed fragment under a fragment frame.
Admission runs in process and launches no provider, command or child. This
is one new effect class and one internal evaluator construct, both using
EE's existing machinery.

Before committing success, admission:

1. Checks bounded source/definition/node sizes and parses the supplied module
   body at the parent's target.
2. Compiles against the permitted snapshots with the ordinary frontend.
   Checks the entry signature and matching boundary type descriptors.
3. Builds and validates the closed fragment under EE P1–P7, including complete
   bodies, checked types, finite loops, no recursion and a complete site table.
4. Rejects unsupported forms and any resolved effect outside the parent's
   bound, including effects introduced by a library body or selected hook.
5. Validates and commits the fragment as the admission's result before any
   fragment evaluation or `started` record.

Initially admit commands, portable providers and calls only. No nested eval,
`run-ref`, parallel map, human input, trials, sessions or resource transitions
inside a fragment. An eval itself cannot occur inside a parallel map. Reuse
ordinary existing forms within the subset; do not add a smaller plan language.

The committed admission contains the closed fragment inline, its canonical
digest and the information needed to check its entry and sites. Source and
source-map artifacts live in the admission's attempt directory for diagnostics.
As in EE M5, the inline committed value is authority; an output file alone
never grants permission to execute. The compiled fragment is internal: the
parent cannot pass, return or persist it as a workflow value, and only the
evaluation paired with that admission may enter it.

Admission's input includes the source, entry/types, import selection, bound,
budgets, target and parent configuration. Its stored fragment is never
recompiled on a memo hit. Compiler identity is retained as evidence; the run
must finish under a compatible representation, not reinterpret stored code
using a new compiler's choices.

## 5. Validation is not a checksum

Before execution, on resume preflight and on artifact reads, check the stored
fragment's digest, checked form, signature, boundary descriptors, sites and
admitted operations against the parent's fixed contract. Unsupported or
inconsistent fragments refuse before considering their effects.

Recompute the effect check from the fragment's actual operations and compare
their executable bindings, policies and owner configuration to the parent's
authority. Do not trust a stored effect summary, a module-name claim, or a
fabricated resolved-bound record inside the admission. Imported definitions
must correspond to the permitted fixed snapshots, including specialization;
how to prove that correspondence without recompiling is part of the
feasibility gate. Hashing an edited fragment and storing its new hash is not
an authorization check.

This preserves the existing trust in the parent's checked artifact and run
store; it does not claim protection against an attacker who can replace all
of that authority. Within that model, editing an admission cannot enlarge
the parent's permitted imports, bindings or effects.

## 6. Budgets, identities and recovery

Require finite effect and iteration budgets. Effects count every reached
`perform`, including memo hits, so replay consumes the same budget. Stop
before starting the next effect when its count would exceed the limit.
Iterations count loop continuations and collection traversal items in the
closed representation. Admission's source/node limits bound compilation
separately. Exact defaults and units need fixtures before implementation
selection; static maximum-effect analysis is not required.

A fragment frame identifies the parent eval site and the fragment entry.
Within it, use EE's ordinary call, loop and effect identities and attempt
directories. The admission is a site in the parent; the fragment owns its
own checked site table. Diagnostics point into the stored source and back
to the parent eval form. Existing views can expose that association without
a new inspection service.

Preflight walks the journal in order. A fragment record must map to the
preceding committed admission active for that parent activation at that
journal position, and to a site in its fragment. Later invalidation does not
erase this association for historical records. A missing admission or
incompatible class/site is a memo inconsistency. A memo hit returns the
validated stored fragment; replay then reuses its committed effects. Kills
before admission commit can repeat admission safely; kills after it never
recompile the committed fragment.

Keep the fragment digest out of effect identities: re-admission must not
hide an earlier uncommitted attempt behind a fresh identity. EE's explicit
suffix invalidation needs an additional check when its suffix contains an
admission: refuse if replacing that fragment could bypass an uncommitted
`must_not_repeat` attempt or the C4 implementation-evidence check. A different
fragment may also change site shape, so stable identity alone is insufficient.
Perform the check before any invalidation write. No implicit invalidation or
retry override is introduced.

Prompt files and command closures remain ordinary effect inputs, checked
by content under EE. Pinned compiled code does not freeze their bytes or
authorize ignoring `effect_input_diverged`.

## 7. Evidence required before acceptance

This combines compiler, dynamic fragment entry and memo recovery in an
unproven shape. EE Phases 2–3 are prerequisites. If the owner selects a
feasibility spike, use the existing evaluator spike and public compiler
boundaries; do not introduce a production parallel path.

| Obligation | Minimum convincing evidence |
| --- | --- |
| Ordinary compilation and fixed imports | A generated module calls a permitted export with its original owner configuration; an unavailable export and conflicting snapshot are refused |
| Resolved bound and read validation | Disallowed adapter/provider, imported effect and hook are rejected; edited fragment bindings, policy, signature and imported bodies fail before launch even with recomputed digests |
| Durable admission | A rejected program launches nothing; no fragment `started` precedes admission commit |
| Budget and fault semantics | Exact exhaustion boundary and located pure faults produce the same outcomes on replay; effect failures retain ordinary resume behavior |
| Recovery and invalidation | Kills at admission/fragment journal boundaries return the uninterrupted result without repeating committed work; unsafe suffix invalidation refuses even if replacement code changes site shape |
| Determinism and diagnostics | Fixed source, parent snapshots and compiler produce identical canonical fragments; formatting preserves identity; source locations survive storage |
| Authoring benefit | An agent composes a useful bounded workflow from an allowed library and repairs a rejection; record cost and correctness against a fixed-dispatch or ordinary command baseline |

These are prerequisites, not claims of current support. Failure to establish
snapshot authority, checked fragment entry or retry safety blocks acceptance.
The [authoring improvements plan](../plans/2026-10-02-agent-authoring-improvements-plan.md)
can improve generated source quality independently; simulation and EL-1 are
useful complements, not permission to skip the checks above.

## 8. Boundaries and tradeoffs

If accepted, this amends EE's closed-before-run property to closed-before-
fragment-entry for this operation, adds the admission class/frame and caught
pure-fault/budget behavior, and tightens suffix invalidation. It also amends
the [runtime closures boundary](workflow_lisp_runtime_closures_boundary.md)'s
runtime-loading prohibition for this one case. Workflow references and
`ProcRef` remain compile-time values; no general closure tier follows.

Fixed dispatch remains simpler when the alternatives are known. `run-ref`
remains appropriate for a pinned child program with its own workspace and
journal; eval neither replaces it nor promises child isolation. Generated
source behind a command remains opaque to the workflow's per-effect replay
and bounds, which is the specific gap this design addresses.

Keeping one form means no separate check-and-approve flow. Fixed imports mean
no library updates inside an in-flight run. Dynamic budgets may leave partial
committed work before exhaustion, and typed checks do not establish task
quality. Those limits are deliberate; catalog/search/promotion tooling and
pre-execution review can be reconsidered when a concrete consumer needs them.

Names, target allocation, concrete import representation, limits and the
feasibility work's selection remain open. None is decided by adding this
proposal to the roadmap.
