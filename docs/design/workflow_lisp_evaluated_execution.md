# Workflow Lisp Evaluated Execution

## Metadata

- **Status:** accepted for the first release at gate G1 on 2026-09-29;
  Phase 2 closed-program compilation is implemented at target 2.35.
  `orchestrator compile` writes the checked artifact; `run` and `resume`
  refuse with `evaluated_execution_unavailable` until the open Phase 3
  evaluator is implemented. Evidence:
  [public compile tests](../../tests/test_workflow_lisp_closed_program_compile_cli.py),
  [target refusal tests](../../tests/test_workflow_lisp_target_evaluated_execution.py)
  and [Phase 2 status](../plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md#status-authorities-and-scope).
  Phase-wide checks and the completed red-suite diagnosis are recorded in
  the [closeout report](../reports/2026-10-02-workflow-lisp-evaluated-execution-phase-2-closeout.md);
  Phase 2 compiler closeout is complete: code/verification PASS `17049e79`,
  documentation PASS `a6efc7e7` and integration `a7b157d8`. The spike under
  `experiments/evaluated_execution_spike/` remains separate runtime evidence.
- **Kind:** execution model, run state and compiler output contract
- **Owner:** Workflow Lisp frontend and runtime
- **Created:** 2026-09-29. **Revised:** 2026-10-02, including the Phase 3
  input-document, profile, invalidation-entry, artifact-handoff, command
  transport and shared-union field-proof clarifications.
- **Evidence:**
  [gate report](../reports/2026-09-29-evaluated-execution-spike.md), cited
  below as "gate report";
  [execution facts](../reports/2026-09-29-workflow-lisp-execution-facts.md);
  [value/effect separation decision brief](../reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md).
  The spike's reports for its four iterations and the three independent
  reviews are kept in the plan's working directory, outside the repository
  (gate report, §10); they are cited below as "spike iteration N"
- **Plan:** [evaluated execution plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md).
  Its decisions 5 and 7 fix the architecture and the scope of the first
  release; decision 6 selects target 2.35 (owner, 2026-09-30).
  Delivery order and consumer migration are owned by that plan, not this
  execution contract.
- **Amends when the first release lands:**
  [core calculus middle-end](workflow_lisp_core_calculus_middle_end.md)
  (§10.1 constructs, §11.4 identity, §15 alternatives, §16 deferred work),
  `specs/state.md`, `specs/io.md`, `specs/cli.md`, `specs/versioning.md`,
  and the command boundary manifest of the
  [command adapter contract](workflow_command_adapter_contract.md)
- **Related:** [numeric surface](workflow_lisp_numeric_surface.md),
  [writing each fact once](workflow_lisp_write_once.md),
  [lexical execution checkpoints](workflow_lisp_lexical_execution_checkpoints.md),
  [pure-result replay](workflow_lisp_pure_result_replay.md),
  [design principles](workflow_language_design_principles.md) 5, 6, 10, 15,
  17, 27 and 28

## 1. Summary

A compiled workflow is a program in the workflow core calculus. The runtime
evaluates that program. Values live in a lexical environment and are
computed. Effects have an identity and are recorded in a memo. Resume
evaluates the program again from its entry and takes each recorded result
from the memo.

Five rules follow.

| Rule | Statement |
| --- | --- |
| E1 | A value is the result of evaluating an expression. It has no step, no name in run state and no stored copy |
| E2 | An effect is identified by its site in its definition and the path of activations that reached it. Nothing else enters the identity |
| E3 | An effect runs only when the memo holds no committed result for its identity. A committed result is returned without running anything |
| E4 | What a reader sees as steps is a view derived from the memo and the program |
| E5 | An effect receives any transportable value as input, and returns one. A value does not have to be flattened to reach a command |

### 1.1 The first release

The owner's decision of 2026-09-29 (plan, decisions 5 and 7): evaluated
execution is built in stages, at target 2.35. Targets through 2.34 keep the
flat route.

The first release covers four classes of effect: commands (external tools
and certified adapters), composed providers, calls of workflows and
procedures, and path-mode run references. Within composed providers it covers the
portable subset: no session, no context capture, no managed job, no secrets.
Every other class (trials, provider supervision, peer groups, phased
providers, adjudication, requests for human input, resource transitions,
materialized views, parallel map) and every form left out above enters
later, each with its own adapter and its own evidence through the public run
and resume entries. A program at the new target that uses a class or form
outside the release is refused at build with `closed_program_gap`, naming
the form and its source location. This target-aware admission check is part
of accepting a typed program at the new target; a defect closing an admitted
form is a compiler defect, not permission to shrink this release's scope.
Calls include the existing compile-time `WorkflowRef`, `ProcRef`, `bind-proc`
and bounded `let-proc` forms. Explicit supplied compiled imports require the
matching producer-owned typed snapshot (§4.2.1); ordinary source calls remain
admitted. This input precondition does not authorize a new call-form gap.
Portable composed providers include both prompt
extern source kinds and the admitted `defprompt` slot kinds (§9.4).

The conditions of the gate report, section 6, bind the first release. Each
is a rule of this design.

| Condition | Rule |
| --- | --- |
| Invalidation covers every later committed effect, in journal order, until dependence through files is declared | C8, C9 |
| Every command boundary declares what it runs, even when that is nothing | C1 |
| What a command declares is read-only, and the run's interpreter is fixed for the run | C3, C4 |
| A view checks the terminal record against the settlements it implies | V3 |
| The request a provider or a command receives is a contract | R1 to R12 |
| Every form and every coordinator in the release has evidence through the public run and resume entries | K9, section 17 |
| Behaviour that depends on a file's modification time is outside any promise that binds bytes | C5 |

### 1.2 Ordinary path run-reference placement at 2.35

The accepted placement clarification uses the existing
`CompilerSession.closed_program`, selected by the entry target across its
source graph. Path-mode run references participate directly or transitively
through calls in ordinary effect-admitting control: bounded loop bodies,
budgets and seeds, `match` subjects, and the one-effect body of serial
`list/map-effect`. Preserve ordinary types, union/arm proofs, structural
evaluation order, collection transportability and traversal bounds. A direct
path run reference is also an admitted one-effect map body; the map source
and body arguments remain pure. This does not select general or parallel map.

`:on-exhausted` remains a pure projection at 2.35: retain both its specific
run-ref/trial guard and its rejection of any nonempty effect summary. Other
pure contexts, including source-module rules in older imported helpers,
remain pure. Trials, bundle-mode references and effectful E1 children remain
excluded. Older entries retain their existing placement and settlement;
an older helper consumed by an evaluated entry gains this scoped placement
permission without retargeting its other language rules (§13).

**Implementation and public evidence are pending.** This accepted contract
does not establish compilation or execution of these combinations. The
[Phase 3 plan](../plans/2026-10-02-workflow-lisp-evaluated-execution-phase-3-plan.md#task-9-run-reference-coordinator-and-evaluated-children)
requires a separate frontend cut and the public repetition/recovery gates
before Task 9 closes. No new flag, registry, effect system or identity rule
is introduced; §6 and K7–K9 supply the existing protocol.

## 2. Problem

At run time a value exists only as the output of a step. The decision brief
states the consequences. Measurements since then:

| Evidence | Result |
| --- | --- |
| Totality matrix, 120 combinations of value form and position, after the shared defect repairs | 34 combinations typecheck and then fail. Every one needs a repair in code that serves only the flat step route |
| A search controller with a 14-field state, written five ways | Refused three times on the present route: the state update was 361 nodes against a bound of 256 (95 once bound values are shared in a payload); then a loop inside an `if` branch; then, in the compact form, a `let*` binding `parents` whose value is an `if` over two lists (`workflow_return_not_exportable`). An `if` over two records in a procedure called in a loop compiles and fails at run time with `pure_expr_payload_invalid`. On the spike the compact form, source unchanged, makes the decisions of its Python reference on 72 pairs of leaf scenario and budget (gate report, §2, criterion 2) |
| Rewrite of a review workflow with a library helper | A pure `match` over the helper's result is rejected; a nested `if` in a hook is rejected |
| Identity | Step ids, checkpoint ids and schema digests change when two blank lines are added or the file is moved (execution facts, A.5) |

The execution facts report lists 23 properties of the current system that an
evaluator would have to rebuild or that depend on steps being flat. This
design answers each. The gate report, section 3, lists eleven programs that
typecheck, that the present route refuses through its public entry, and that
the spike runs.

## 3. Goals And Non-Goals

Goals:

- Every program admitted at this target runs. No rule of the language depends on
  where a value is used.
- Structured control nests without limit: a loop in a branch, a loop in a
  loop, a branch in a hook.
- Resume never runs an effect that committed a result.
- Effect sites and their contracts are known before a run starts.
- Identity survives formatting edits and moving the repository.
- Older targets keep their behavior and exact serialized bytes for identical
  identity inputs; truthful compiler-package pins remain binding (§13).

Non-goals:

- Replaying arbitrary code. The language stays closed: bounded loops, no
  first-class procedures, no recursion, a fixed effect vocabulary.
- Exactly-once effects in the world. An effect without a committed result
  runs again, unless its boundary declares `must_not_repeat`.
- Capturing or rolling back workspace files. A committed child run is
  therefore never superseded (C8, K8).
- Binding what a command reads beyond the files its boundary declares (C5).
- Changing YAML workflows or targets that exist today.

## 4. The Closed Program

The evaluator needs a program that is complete. Today part of what execution
needs is computed after the calculus, during lowering, and is keyed by step
name. The compiler therefore produces a closed program, with these
properties.

### 4.1 Properties

| # | Property | Flat route (targets through 2.34) |
| --- | --- | --- |
| P1 | Whole program. The body of every `call` target is present once, specialized, in the table of definitions (§4.2). Nothing is elaborated after the program is built | Callee bodies are elaborated during lowering |
| P2 | Only calculus. No node holds a surface expression | Loop state, lists, `list/map`, `path/join-under`, bundle paths and several effect payloads are surface objects |
| P3 | Complete effects. Each effect node carries its operation class, its resolved target, its inputs as atoms, its result type, the output contract derived from that type, its prompt assembly, its policy, its declared closure (C1) and its repeat rule (`must_not_repeat`) | Contracts, result paths, prompt rows, policy rendering and timeouts are computed in lowering |
| P4 | Sites. The program carries a table of its effect sites: one per `perform` node of each definition, named by the definition and the local path. Two call sites of one procedure are two frames over one site (§6) | One node identity is shared by every inlined copy; an ordinal from a counter tells them apart |
| P5 | Checked form. A validator checks the normal form at build and artifact read: names in scope, `jump` and `continue` targets, a `continue` naming the loop it is in, the site-table bijection (§6), no recursive call, a budget on every loop, valid operator payloads, and type consistency for every value, effect result, call argument/result and entry result | Only tests check it |
| P6 | Provenance. Every node keeps its source span and form path under one key. Provenance never enters an identity or the program digest | Spans and type text with file paths enter several identities |
| P7 | An artifact. The closed program is written as canonical JSON, with its site table, representation version and canonical configuration contribution (§7.3). Its digest, taken without provenance, is the program identity | No such artifact |

The spike demonstrated parts of P1 to P7 outside the elaborator (gate report,
§4); §18 names the remaining proofs. It measured what must change: attach
normalized bodies
at `call` and `workflow_call`, elaborate `done` values and surface objects,
move contract, prompt and boundary resolution into elaboration, record the
declaring module on type definitions, and derive specialization names from
canonical identities. Each is at the new target only.

### 4.2 A table of definitions

The closed program is a table: the entry's parameters, defaults and body,
and one definition per canonical callee name, each body stored once. A
`call` names its callee and carries its call site as a frame. A site is
local to its definition. An identity at run time is the activation path
(the frames, with loop iterations filled in) and the local site (§6).

A canonical definition key is the following tuple, serialized as canonical
JSON (UTF-8, sorted object keys, compact separators, finite numbers only):

```text
(declaring module, definition kind, declared name or local-definition key,
 type bindings, procedure-reference bindings, workflow-reference bindings,
 value bindings, capture parameters, residual parameter and result types)
```

The [Phase 2 shared key schema](../plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md#canonical-definition-keys)
fixes the nine-element base JSON array, reference bindings, capture routes,
residual signature and source-independent checks. Ordinary binding selectors
use declared formal names, or `["local", index]` for a generated local's captured formal;
local selectors sort by index before ordinary strings sorted by name.
Only K6 additionally admits the residual projected-static selector and ordering
defined in [§9.1.3](#projected-static-facts-in-k6); it is not a reference-formal selector.
Ordered type arguments, residual parameter types and record fields retain
declaration order. The residual signature excludes the capture prefix.
The bounded command-transport specialization in §9.1.3 appends a tenth
component only to definitions whose command transport needs it; it also
defines the corresponding typed capture routes. The base nine components
and existing keys without that component keep their meaning.

The readable base is `kind + ":" + module + "::" + declared_name`, where
`kind` is `procedure` or `workflow`; the entry uses the workflow kind. A
local callable uses its authored local name in that position and retains
its enclosing declaration and ordinal in the key. An unspecialized top-level
callable uses the base alone; every local, specialized or capture-converted
callable appends `[<full lowercase SHA-256 of the canonical JSON key>]`.
Kind qualification is unconditional: same-name procedures and workflows
are admitted and must occupy distinct entries, independently of what else
is present. The tuple is retained with the definition; names must derive
from their keys, and equal names with unequal keys are refused. The pure
key-to-name operation in `closed/names.py` is shared by builder and checker.

| Component | Canonical content |
| --- | --- |
| Module and definition | The declared module identity, carried from linking, and the declared callable name; an unmoduled standalone entry uses a fixed entry namespace. Import aliases, source paths, spans, generated flat-route names and `repr(TypeRef)` are never identity |
| Types | Nominals use declaring module, declared name and recursively canonical arguments, including private nominals; structural constructors use their kind and canonical children. The same rule applies recursively to every descriptor in the artifact, not only to specialization keys |
| Procedure reference | The recursively canonical target key, residual signature and each bound argument's formal selector, type and binding; bound rows biject with the target's complete bound-formal facts, including category, value or mapped capture route. Projected-static K6 rows describe residual parameters, not complete bindings, and do not enter `PRef.bound`. All views derive from one resolved binding; forwarding resolves to that target, not an alias |
| Workflow reference | The canonical workflow key and its resolved extern-rebinding plan, by formal extern name and exact provider/prompt row from the shared schema; no unresolved alias or opaque payload |
| Value binding | A complete binding is the checked, closed expression substituted into the specialized body, with canonical types and alpha-normalized local names. K6 also admits the typed literal projection of a parameter that remains residual, using the exclusive selector/wire in §9.1.3; that row neither substitutes the compound nor erases its parameter. Tagged literals preserve distinctions such as `Bool`, `Int` and `Float` |
| Captured runtime value | An explicit typed parameter in the closed definition and a value argument at the call. The key records the capture's owning formal/argument route and type, not the captured runtime value or a caller's local spelling. Evaluation at the binding's lexical scope happens once, before forwarding; later calls pass that value |
| Local `let-proc` definition | The enclosing declared definition, lexical local-procedure scope/name (same-name local declarations disambiguated in that scope), residual signature and capture schema; never the existing span-derived generated name or a digest of the body. Pure-binding insertion/renaming must not change this local key |

Closure conversion supplies capture parameters before computing the key.
Two captured values using one converted body share a definition and differ
in call inputs; two different substituted expressions or reference targets
have different keys. No surface expression or runtime procedure reference
survives. The existing [partial application](workflow_lisp_proc_refs_partial_application.md)
and [local procedure](workflow_lisp_let_proc_local_proc_refs.md) contracts
govern lexical capture and forwarding. The spike's refusals of value,
workflow and bound-reference specializations are missing evidence (§18),
not additional exclusions.

Capture rows are `{type, routes}` in native prefix order; their indexes bind
the converted parameters without caller-local names or runtime values.
Direct/local/reference routes identify semantic formals. Context routes
identify original declarations, per-callee static call occurrences and
typed source/native field paths, never a converted name/key that contains
the same capture. Intermediate wrappers carry route suffixes; the caller's
canonical nominal descriptor is preserved. P5 checks prefix types/order,
reference-binding agreement and actual forwarding/terminal transfers as
specified in the shared schema. Inserting unrelated pure bindings or calls
to another declaration changes no route occurrence. Inserting an earlier
call to the same declaration can change its later occurrences, just as an
earlier same-name local declaration can change retained local ordinals.

Compiler-generated run-reference result types and static configuration use
position-free identities: their configuration/type `site_digest` combines
the containing definition's canonical lexical site with the canonical
input/result structural signature. The existing neutral generated-name
rule derives the result name from that digest; the effect site and runtime
identity remain those of §6. Do not copy the current span-derived `site_digest`
or `RunRefResult$…` name. The enclosing definition key uses that generated
type's structural signature, avoiding a cycle between key and site. P5 checks
the descriptors against their definitions and producers; recalculating a
digest alone is not artifact validation.

The [Phase 2 shared signature schema](../plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md#run-reference-structural-signatures)
defines that structural signature exactly: ordered input name/descriptor rows
and the full neutral result contract with only its own outer envelope name
omitted. Nested generated envelopes use their producer's recursively derived
signature, preserving other nominal and fixed runtime identities. The checker
derives a unique lexical-producer inventory, rejects missing/ambiguous/cyclic
dependencies and checks all 64 digest characters against actual typed inputs,
results and sites. Equal signatures do not identify equal producer sites;
construction/finalization retains producer context through calls and copied
specializations, never a global generated-name replacement. Task 5 owns the
pure projection helpers shared by typed construction and finalization.
The containing definition in the site-digest tuple is its canonical name
string (`entry` or the `definitions` map key), never the retained key tuple.

The [shared applied-identity grammar](../plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md#applied-nominal-identities-and-interned-generated-views)
keeps runtime nominal names as strings but structurally projects every applied
name in key descriptors, including phantom arguments with no payload field.
It preserves template/argument order and ordinary identities; generated atoms
use the same complete S marker. Typed construction retains real type arguments;
read-back checks canonical spelling, concrete registered descriptors and their
projected inventory. Origin dependencies include generated atoms inside those
arguments, rejecting phantom-only cycles. No runtime descriptor/codec field
or persisted origin table is added.

Compiler-generated loop-state records retain their nominal seed family. A family
is the declaring callable's declaration-only identity and the semantic ordinal
of the carrier introduction in its expanded declaration, retained through
specialization and imports. `:like` preserves that family; the existing list-map
expansion inherits its source constructor's introduction. The closed carrier
name uses the shared applied identity grammar: its qualified head hashes the
family and ordered field names/key-projected complete field descriptors, and its
ordered arguments are the concrete canonical field type identities. Generated
run-reference names are projected through the existing structural S before
hashing, and concrete producer associations remain available for final
argument/descriptor rewriting. Formatting, source relocation and unrelated pure
bindings do not alter a family. Neither body hashes, canonical callee keys/sites
nor legacy generated names define it. Distinct seed families remain distinct
even with equal payload shape; no source-admission rule changes.

Equal-key candidates keep the first native representative in deterministic
semantic call traversal. Later calls retain their own concrete signature
views, using the checked generated boundary below when necessary. Preserve
source/snapshot/configuration and projected-body conflict checks. Candidate
copies of one interned body are not extra lexical producers; finalization
rewrites every concrete occurrence and boundary endpoint by its actual
producer, including atoms in applied identities.

Size evidence (gate report, §9.2; spike iteration 2, F, and iteration 3,
D3; 52 shipped workflows, 38 built):

| Program | Tree form, nodes | Table form, nodes |
| --- | --- | --- |
| `experiments/mlevolve_pair/search.orc` | 5,571 | 5,572 |
| `experiments/mlevolve_pair/search_compact.orc` | 4,065 | 2,574 |
| `workflows/experiments/repository_task_pilot/task_loop.orc` | 2,659 | 1,284 |
| `workflows/examples/kiss_backlog_item.orc` | 900 | 568 |
| A synthetic program, each level calling the next three times, depth 4 | 652 | 87 |

The tree form grows with call nesting; the table form stores each distinct
specialized body once. It need not be linear in unspecialized source when
specializations multiply. On all 123 test programs the two forms name the same effects in the
same order. The table form is the one representation of the first release.

### 4.2.1 Supplied compiled imports and source ownership

An explicit compiled import at target 2.35 supplies the selected producer's
complete `TypedProgram`: native bodies/signatures, transitive definitions,
type environments, externs, configuration, logical asset base and digests of
the exact source bytes its producer consumed. Source-produced old-target
bundles retain that snapshot in a compile-only `LoadedWorkflowBundle` field
when all compiled dependencies supply their original snapshots. An old-target
producer with an opaque compiled dependency still compiles under its existing
contract, but leaves its complete snapshot absent; importing that result at
2.35 fails the missing-snapshot precondition below.
Its state is omitted from legacy pickle/capsule serialization; targets through
2.34 retain their existing bundle admission and execution behavior.

The original old-target snapshot also retains a frozen final structural
boundary map for its source-produced workflows, captured after validation.
It includes input/output contracts and semantic public/private projection
and binding facts. Pairing compares those original facts, including default
and union-projection presence and values, without reconstructing private
lowering or comparing diagnostic provenance. The map stays transient; a
typed-only producer that never made a flat bundle may leave it empty.

An older decoded bundle can be paired explicitly with its matching original
snapshot. Missing/incomplete or structurally mismatched pairing is refused
before call admission with `compiled_workflow_source_required`, naming the
binding, workflow and source/manifest location. The caller must supply the
matching original snapshot: selected workflow and boundary checks prove
structural consistency, not historical body authenticity, because old bundles
contain no typed-body digest. Explicit recompilation from supplied source and
configuration creates a replacement import; never silently reopen the live
source path of an accepted bundle or reconstruct a body from flat steps.
Once admitted, a missing body is a compiler defect.

Keep one `TypedProgram` type. Its `imported_programs` maps explicit bindings
to selected complete snapshots, while `module_workflow_signatures` retains
each declaring module's caller-visible catalog signatures. The body keeps
its native signature. An alias resolves to the selected producer's canonical
entry when closing the call; source imports still use the existing import
scope. Every reachable definition uses its source owner's environments,
configuration and asset base, not those of the consuming entry.

Before interning a canonical module/callee, compare retained source revision
and captured semantic context, including bindings and logical asset base.
Equal source/context may share a definition; unequal snapshots of that same
canonical definition, including overlap with a source import, are refused as
`compiled_workflow_snapshot_conflict`, naming both origins. No last-write-wins
or simultaneous versioned identities are introduced. Different caller nominal
views with compatible boundary contracts are not this conflict (§4.2.2).

Direct source producers create a `SourceReadTrace` before their first read if
none was supplied, forward one supplied trace unchanged, and derive snapshot
digests from its records after their final reads, before attaching snapshots.
No attachment-time source reread is permitted. Independently compiled imports
retain their own evidence; those bytes are not claimed as reads of the caller.
A non-`None` typed snapshot on an old producer never selects the new route:
the actual entry target selects all lowering/validation gates (§13).

### 4.2.2 Compiled call boundary views

The existing compiled-bundle catalog reconstructs types from boundary
contracts in the caller's environment. It admits distinct nominal records
and dynamic paths with compatible contracts. It can also expose one caller
record argument for multiple native parameters (`a: Pair(x, y)` for
`a__x: Int, a__y: Int`). Retaining a native body does not remove this contract.

An explicit compiled call carries an optional `boundary` annotation: its
caller-view parameter descriptors, caller/native input and output projection
rows, and `direct` argument/native-parameter index pairs for strict transfers.
The exact shared schema is in the [Phase 2 plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md). `args[i]` is checked against
`boundary.params[i]`; native parameters are bound through the declared
relation, not an assumed equal-length positional list. Captures precede
caller formals; a caller-only private formal promoted to a capture appears
once, omitted from the later caller-formal section. Native-only generated
contexts follow in native order.
Defaults, captures and X1/X2 values are resolved from existing binding facts.
Source/ANF evaluation order is retained in preceding `let`s, before any
argument permutation. Direct and projected slots form disjoint exhaustive
partitions on both sides; projection may map one argument to several native
parameters. Ordinary unannotated calls keep their strict positional rule.

A bundle may expose a private context formal absent from its native source
signature. Closure conversion must give that value an explicit context/capture
parameter and forward it to the exact omitted bindings in the retained body,
including through intermediate calls. Preserve the native source signature;
the converted definition carries the extra parameter. An explicitly supplied
context is evaluated once and wins over generated X1/X2/default values. No
caller slot may be dropped or left outside the checked boundary relation.
The capture retains the caller's canonical descriptor. Its existing capture
schema records canonical recipient/formal routes and that type, excluding
runtime values, aliases, generated wire prefixes and source positions. Values
with the same type/routes share a converted body; different nominal capture
types may require distinct keys. Preserve explicit native bindings/defaults;
resolve every admitted omitted recipient from the actual retained calls,
semantic private groups and typed field paths. Diagnostic provenance and
flattened-name splitting cannot establish recipients. Defaults specify
omission generation and do not constrain supplied runtime values.

A converted internal call injecting such a capture into a different compatible
native nominal may use the same `boundary` annotation. This narrow case
retains complete ordinary residual input and both output projections, even
when those residual types are identical; `direct` remains restricted to
strict-compatible captures/generated/context values. Intermediate calls with
exact types may stay positional. No source-call admission is widened.

Same-key interning can also retain a native signature with different generated
run-reference nominal identities. **Construction** of an ordinary generated-only
view must prove equality of the whole ordered caller/native signature under
the shared checked D projection: captures, residuals, result and phantom
arguments. Ordinary heads/arguments, refinements and S stay exact; capture
count/order/routes align. At least one generated identity differs. This case
adds no permutation or 1:N conversion. For admitted compiled/context calls,
retain the independently established relation and compose the representative
change in the same annotation, with original caller slots and once-only transfer.

**Read-back** checks the final annotated relation, which has no source-history
mode. It cannot distinguish a valid ordinary nominal crossing composed with a
generated view from an ordinary call purported to require only the latter.
Consequently, a complete-signature ordinary nominal difference can be accepted
by P5 as a valid composition while being rejected by the generated-only
constructor. This is an explicit clarification of the earlier undifferentiated
whole-signature reader requirement, not a source-authenticity claim.

Before accepting equal wire contracts, independently compare complete protected
units: generated envelopes, generated-bearing applied identities/discriminants
(including phantom arguments), and atomic row-terminal descriptors containing
generated dependencies. Each unit's complete D, exact footprint of wire names
and relative structural paths, and enclosing union-branch activation must agree.
Compare active multisets branch by branch, preserving multiplicity. Generated
units can move intact through ordinary wrapper/1:N projections; they cannot be
split into unmarked leaves, moved between branches, or lose ordinary nominal
facts inside a protected applied/collection unit. Missing origins fail. The
[Phase 2 plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md#generated-boundary-construction-and-read-back)
defines the exact predicate and implementation gates; no admitted source that
requires protected-unit erasure has been demonstrated.

Preserve both exact endpoint wire contracts, independently derived rows,
coverage, paths, topology and union activity. Only after the complete-unit
checks may equal contracts pass. Unequal contracts require equal full D for
the same paired row's terminal descriptors using that branch correspondence,
with an actual generated dependency. This permits exact distinct List[A]/List[B]
schemas without granting permission from an unrelated matching descriptor.
Changed captures use projection rows; `direct` stays strict. No boundary mode,
extra effect/site or general nominal cast is introduced. P5 derives producer
signatures before deferred view checks and accepts only after all key/name/site
and boundary checks succeed. Unannotated calls remain strict.

P5 independently validates every descriptor against canonical nominal facts,
every projection path and complete field/active-variant coverage, matching
wire contracts, exact path/enum constraints and direct/capture alignment.
Neither matching copied labels nor whole-record nominal erasure is a proof.
Reuse the existing boundary projections and neutral transport descriptors;
no general cast or global relaxation of nominal compatibility is added.
A malformed relation fails checked read-back with `call_boundary`.

Phase 3 evaluates each argument once, applies the checked projection/direct
relation to cached values, evaluates the native body, and projects its result
back to the caller view. Dynamic paths retain their string value and checked
constraints. This is an in-memory call, not another effect, site or journal
entry. Phase 2 persists and checks the relation; it does not implement its
evaluator. Union activity, legacy structural paths and inactive-path relaxation
require independent artifact read-back proof, not only compiler generation.

### 4.2.3 Shared-union field projection

The [parametric type-system constraint vocabulary](workflow_lisp_parametric_type_system.md#constraint-vocabulary)
owns source admission: `has-shared-union-field f T` proves that every variant
of a nonempty concrete union has `f` assignable **to** `T`. It grants exactly
that projection, with result type `T`; it does not prove a particular variant.
The closed program must preserve this already admitted operation. For example,
two distinct nominal `ReportPath` and `ArtifactPath` fields can both satisfy
`Path.state-root` without being mutually compatible. Selecting the first
variant's type or requiring pairwise equality loses the declared result type.

Retain the checked projection in the existing `field` value. Do not lower it
to `case`/`join`: those constructs currently require compatible arm/parameter
types too, and widening their relation would spread this permission beyond
the operation that owns it. The cost of retaining it is a bounded addition to
field serialization, descriptor traversal and definition-key checking; no
new source form, runtime value class, effect or general cast is introduced.

**Typed retention.** `typecheck_field_access_expr` retains the exact resolved
constraint `TypeRef` at each path segment where it consumes a shared-union
capability, alongside the typed base. Ordinary segments have no such proof.
Use an optional aligned tuple `shared_field_types` on `FieldAccessExpr` and
`WccFieldAccessAtom`; empty means no shared projection. A nonempty tuple has
one entry per segment, each either that segment's checked target `TypeRef` or
`None`, and at least one target. The specialization's concrete re-typecheck
replaces provisional facts; unresolved `TypeParamRef`s never reach closed
construction. Keep these internal facts out of frontend repr, semantic
identity and old-route serialization using the existing omission conventions.
They are not a new procedure-wide capability lookup in WCC.

WCC inference walks the path using these retained targets at certified
segments and its ordinary field rule elsewhere; its final metadata type is
the last segment's result. Copy/rewrite/ANF and retained frontend values keep
the tuple. Concatenating paths concatenates their aligned tuples, padding an
uncertified prefix/suffix with `None`; merely replacing a base name preserves
alignment. Never recover a target by looking up its spelling in the consuming
module. Source imports and complete older-target typed snapshots retain the
same resolved owners (§4.2.1); neither construction nor read-back rereads a
deleted source root to recover a proof.

**Wire.** The only additional field is optional `shared` on the existing
closed `field` node. When present it is a JSON array aligned with `path`,
containing canonical target descriptors or `null`, with at least one
descriptor. Thus `choice.selection.item-id`, where only `selection` uses a
shared proof, carries `path: ["selection", "item-id"]` and
`shared: [<canonical Payload descriptor>, null]`. A terminal shared path
carries its declared `Path.state-root` descriptor. There is no redundant
union name, field name, final type, capability table or frontend trust token.
Absent `shared` keeps the existing wire bytes and meaning. Reject an empty,
all-null, misaligned or otherwise malformed array. The closed schema and
`table/1` representation remain unchanged: this is optional checked evidence
on an existing value; old readers fail closed on the new field.

**Independent segment check.** Starting from the independently inferred base
descriptor, P5 visits `path` in order:

| Segment | Required proof and resulting descriptor |
| --- | --- |
| No target (`shared` absent or this entry `null`) | Apply the existing ordinary field rule: record/proven-variant field, union discriminant, or common union field with canonically equal descriptors in every variant. The result is that ordinary descriptor; there is no implicit constraint-type inference |
| Target `T` | Current descriptor must be a nonempty union, the segment must name a payload field rather than `variant`, and every declared variant must contain that field. Validate `T` and every actual field descriptor against the closed nominal catalog; require the directional relation below for each actual field. The segment result is exactly `T`, used as the base of the next segment |

**Local assignment relation.** Source admission remains owned by
`constraint_field_type_satisfied(actual, expected)`, including its first call
to `type_refs_compatible(expected, actual)`, not the stricter closed
`_descriptors_match`. Let `C(T, A)` be the local compatibility below over
validated closed type facts, and `F(A, T)` the shared-field assignment. For
source-declarable types it preserves the source relation. Compiler-internal
cases/discriminants additionally require the proof-preserving rules below:
the frontend's symmetric union/case boolean is not independent evidence of
variant activity.
For body checking those facts are canonical runtime descriptors (`C_R`);
for key-value checking they are the existing key-type projection of those
descriptors (`C_K`). The ordinary rules below apply in both domains; the
generated distinction below is not elided by calling both relations `C`:

```text
F(A, T) = C(T, A)
          or (A and T are paths and A.under == T.under
              and (A.must_exist_target or not T.must_exist_target))
```

The final clause is **direct only**; recursive positions in `C` call `C`,
never `F`. All admitted path declarations are `relpath`; the wire's
`must_exist_target` is the source `PathDef.must_exist`. A refined path may
satisfy a base path constraint, but that does not by itself make
`List[ReportPath]` satisfy `List[Path.state-root]`, or relax a path nested in a
record. No additional conversion is inferred from runtime JSON shape.

Compute `C` from the registered complete descriptors and canonical identity
grammar, with the following source-owner rules. Exact type equality is the
first case. For an ordinary unapplied declared nominal, *basename* uses the
source owner's `_named_type_basename` on that individual name; it is a
comparison operand only,
never a replacement descriptor or catalog key. Declaration equality means
the same canonical declaring module/name, not equal source spans. Maps of
field/variant names compare as sets as in the source owner; descriptor bytes
retain declaration order. Ordered enum values and applied arguments remain
ordered. Different type families do not match except for forgetting an
already proved case to a union as specified below.

| Type facts | Compatibility `C(T, A)` after exact equality |
| --- | --- |
| Builtin primitive | Same primitive name; no Bool/Int, numeric or Value/Json coercion |
| Declared enum (`PrimitiveTypeRef` with allowed values) | Same declared basename and exactly the same ordered allowed values |
| Path | Same declared basename, root and existence requirement (the direct `F` clause above is separate) |
| Ordinary record, including a structural private context | Same declared basename, exactly the same field names and `C` for every corresponding field; source aliases of the same declaration resolve through its canonical owner. Equal shape with a different basename does not pass |
| Unapplied union | Same declared basename, exactly the same variant names and each variant's field names, and `C` for every corresponding field. Declaration aliases resolve through their canonical owner; equal tags alone do not pass |
| Applied union | Same fully qualified template declaration and same arity; `C` for each ordered argument, including phantom arguments. Read arguments through the checked applied-identity grammar and registered type facts, not by stripping qualification from the rendered application. Every instantiated payload descriptor must separately match its catalog definition |
| Optional / List | Same constructor and `C` for the item |
| Map | `C` for key and value, preserving the Map constructor |

Thus a field of `entry::Payload(item-id: String)` satisfies a constraint
`helper::Payload(item-id: String)`, even though those canonical descriptors
remain different. A different basename, field set, or incompatible recursive
field does not. The result of the certified segment is still the complete
`helper::Payload` descriptor. This existing source permission applies to the
whole checked field view, including nested enums, unions and containers; it
is not permission to rewrite either catalog declaration or other values.

**Internal proof conservation.** A catalog-valid `variant_case` target says
that the variant exists; it does not prove that the projected value has that
tag. The independently inferred **actual** descriptor must already carry any
case proof that the result retains. For example, the existing checked `case`
arm binds its subject with that arm's exact variant descriptor. Looking up a
variant in the catalog, seeing a union with one variant, or inspecting one
runtime input does not create such a proof in a certified field. No new
activity annotation or variant-conversion wire is introduced.

Cases and discriminants retain their internal family and owning union, rather
than becoming declared enums/records because their wire shapes resemble one.
Resolve the complete owner from the validated catalog in the current domain.
The necessary owner-name comparison is the source owner's rule: two unapplied
owners have the same basename; applied owners have the same fully qualified
template declaration and arity and `C`-compatible ordered arguments. This
comparison alone grants no payload or tag permission. In addition require:

| Actual `A` → target `T` | Local permission, including at every recursive `C` position |
| --- | --- |
| Union → case | Refuse: the actual type carries no active-variant proof, even if the target is a real case of that exact union |
| Case → case | The owner-name comparison above, the same variant tag, exactly the same payload field names and `C` for corresponding payload descriptors. This preserves the already proved tag; individual catalog validity or equal owner basenames alone are insufficient |
| Case → union | The owner-name comparison above, presence of the actual case's tag in the target union, exactly the same field names in that target variant and `C` for each corresponding payload descriptor. Only the existing narrowing is forgotten; no other target variant is asserted active |
| Discriminant → discriminant | The owner-name comparison above and exactly equal complete ordered tag lists derived from both registered unions. A common basename alone does not equate their tag sets; payload compatibility is not inferred from a tag value |
| Discriminant ↔ declared enum, or any other internal-family crossing | Refuse; matching wire `kind`, spelling or values does not merge source families |

Identify discriminants from the existing owner/member identity grammar and
the `U.variant` descriptors derived from cataloged unions, with the same
ordered tags as ordinary union-discriminant projection. In key space use the
existing projection of that owner and descriptor. A plausible `.variant`
suffix or a separately valid enum row is insufficient. This uses the existing
catalog, not a persisted origin table or new declaration syntax. Both complete
endpoints remain catalog-checked; cross-owner case permissions additionally
compare the selected payloads, and discriminant permissions compare both tag
lists. Equal tags never prove a payload variant active.

Apply these guards wherever `C` recurses: records, union payloads, containers,
applied arguments and case payloads. In particular, a container or record
cannot hide union→case narrowing. `C_R` uses complete runtime owners;
`C_K` uses their validated projected owners and payloads. Key equality does
not supply runtime activity, and body checking remains independent. An
argument/owner identity ending in `.variant` is not a case proof: only an
independently validated actual `variant_case` descriptor provides its tag and
payload. Do not recover a missing case fact from an identity projection.
Existing checked case bindings, same-case projections and forgetting a proved case to
its owning union remain valid. These internal types do not become
source-nameable, and compile-time refs or unresolved parameters do not become
transportable fields.

Generated units are not ordinary basenames. In `C_R`, a run-reference
envelope or loop carrier retains its complete validated canonical identity
and descriptor; a common generated prefix, payload shape or signature alone
does not equate distinct runtime identities. Existing representative changes
remain governed by the checked generated boundary relation of §4.2.2, not by
a new implicit conversion in `field`. In `C_K`, `closed/names.py::key_type_descriptor`
already replaces a generated run-reference envelope by its full S marker and
recursively projects generated arguments in applied identities; compare those
complete markers for equality after the checker derives/validates their
producer signatures. Carrier heads and their ordered projected arguments
remain exact. This existing projection may identify different concrete
producer names with one key type; it neither erases ordinary nominal owners
inside S nor proves `C_R` for distinct runtime endpoints. Check the body
relation independently; do not recover one arbitrary runtime endpoint from S
or use key equality as runtime assignment permission.

No admitted shared-field specimen requiring a new cross-generated runtime
conversion has been demonstrated. Existing generated identity/catalog/key
invariants are retained, not a claim that an unspecified algorithm transports
such a new pair. A concrete admitted source counterexample must return to
Design before repair completion, without excluding the source or changing
the constraint oracle. No new origin metadata is added in anticipation of it.

Implement `C`/`F` once for the certified-field checker and use it in bodies
and keys. Keep the source functions unchanged as the admission oracle; test
positive and negative parity for admitted source types across their recursive
branches, including the same-name imported-record case. For internal types,
test proof conservation rather than copying the source's symmetric boolean.
The union→case counterexample is a forged-artifact negative, not evidence of
an admitted source case constraint being removed. Do not approximate the
oracle by a list of fixture types or broaden recursive path assignment. No change to global
call, join, branch, operator or ordinary-field compatibility is authorized.
An admitted mismatch is a repair obligation, never a new gap, allowlist or
typecheck restriction. P5 validates both endpoints independently before this
local relation; acceptance does not make their canonical nominal identities
equal.

P5 checks the relation from the artifact's types, not retained Python objects
or a frontend assertion. Wrong field/segment, scalar/proven-variant base,
absent variant field or failed assignment refuses with `field_path`; malformed
shape and invalid/forged nominal descriptors retain the existing `node_shape`,
`type_descriptor` and `nominal_definition` rules. In a definition-key closed
expression the corresponding failures use `definition_key`. Changing and
rehashing the artifact must not bypass these checks. Conversely, a different
target that independently satisfies the relation is a different valid typed
program, not evidence of the original source author's constraint.

**Keys, identities and execution.** Emit every target through the existing
source-owned descriptor registration/finalization path. Key value bindings
and bound-reference values keep `shared` during alpha-normalization and apply
the existing recursive key-type projection, including applied arguments and
generated S markers. Their shape, marker, nominal-inventory and type inference
checks visit every non-null target. Derive the key-domain nominal inventory
by the existing key-type projection of the validated runtime catalog and
derived producer signatures; a descriptor with a plausible name but altered
fields is invalid in either domain. Key shape/marker checks alone are not
this catalog agreement. Runtime and key checkers use the same segment
relation in their respective validated descriptor domains, parsing structured
applied identities before choosing the source compatibility branch. Never
strip the evidence while computing a key, neutralize away an ordinary nominal,
or add a persisted origin table. The annotation contributes to the semantic
program/key bytes where present; provenance does not. It introduces no new
value child or lexical site: traversal still visits only `base`.

The evaluator evaluates `base` once and walks the active value's fields in
order. At each certified segment it uses the checked target descriptor;
otherwise it derives the ordinary descriptor. Coercion/shape checks remain
pure, preserving the value, the declared projected type and all base
dependencies. No branch duplication, extra frame/site/memo entry, filesystem
existence check or referent read occurs. Initial input and new effect boundary
checks keep their existing ownership. Formatting, pure-binding insertion and
source/package relocation preserve keys/sites for the same typed program.

Required evidence covers identical `Int`, distinct nominal paths satisfying
one declared base path, and shared concrete-record fields followed by ordinary
projection, including equal-basename records from different modules and an
incompatible nested-field control; recursive enum/union/container compatibility,
applied template/argument/phantom distinctions and generated projection parity;
body/key rejection of fabricated case activity, including recursive positions,
and cross-owner internal tag/payload mismatches, alongside existing case-proof
and compatible payload/tag positives;
both active variants and an ordinary prefix before a certified
segment; old-source imported helpers with conflicting same-spelled private
types, construction/read-back after source deletion and relocation; key-bound
values; structural tampering after rehash; once-only ordered execution and
committed-boundary public resume. A constraint field type bound from another
`:forall` is subject to its existing source admission: a specimen refused
during typecheck proves no WCC failure and this amendment does not change that
frontend boundary. The Phase 3 plan owns runnable checks and evidence status.

### 4.3 Constructs

The accepted calculus design lists ten constructs and requires an amendment
for each addition. The closed program has these:

| Construct | Role |
| --- | --- |
| `atom` | literal, name, field access, record construction, list construction, pure operator application |
| `inject` | variant introduction |
| `select` | conditional value; each arm carries a prefix of bindings and a value |
| `block` | a body evaluated for its value, where a value position holds control (a `match` held in a loop-state field) |
| `context` | a value the run supplies (§4.4): `run-id` |
| `result_path` | the result file of a committed effect, as a value (§4.4) |
| `let` | sequencing |
| `perform` | one effect |
| `call` | evaluation of a definition's body with the arguments bound |
| `case` | variant elimination |
| `if` | branch on a strict `Bool` |
| `join`, `jump` | second-class continuation |
| `loop`, `continue`, `done` | bounded iteration, with its budget and its exhaustion body |
| `par-map` | bounded parallel iteration over a list (§11; a later release) |
| `halt` | result |

Rules of elaboration into this form:

- `record_update` and `list_nonempty_head` are operators of the pure
  catalog, not constructs. Loop-state seeds elaborate to records, updates to
  `record_update`, variant tags to literals.
- A `halt` that reaches a `join` from the join's body is the join's value.
  This is how a loop in tail position of a join body gives its value.
- An effectful expression in an argument position (of a call, a workflow
  call, a command's argv or adapter document, a provider's input) is bound by
  a `let` before the call, in source order. The present route refuses this
  form as `compiler_defect`; the spike binds it and runs `(fetch (inc 4))`
  as `fetch 4` then `fetch 5` (spike iteration 3, D1).
- A `done` value that is an effect or a `match` is bound by a `let` before
  the `done`.
- A `continue` names the loop it is in; the elaborator's retargeting
  descends into joins.
- `phase-target` is elaborated at its `with-phase` site to the field access
  or path join it denotes (X3). The atom does not survive the normal form.
- An effect-containing `select` or `block` in an aggregate, operator operand,
  condition or terminal value is bound before that value is used. Hoisting
  stays within the selected arm or loop iteration, preserving evaluation
  order and short-circuiting. Its arm prefixes and body remain admitted;
  they are not silently restricted to pure bindings. This makes §6's site
  walk total without adding aggregate-field positions to effect identities.
- A loop's budget and initial state evaluate in expanded structural keyword
  order. Retain this parser fact through typed conversion, including imported
  older bodies; macro argument source spans do not establish that order.
  Compiler-generated loops retain their construction order. This transient
  fact does not enter legacy AST serialization, repr, or callable identity;
  only the closed route changes evaluation behavior.
  When condition normalization factors operands into binding prefixes,
  retain its already-checked full semantic input on the generated `let*`.
  Before closed elaboration scans, restore that input and use the existing
  normalizer with an explicit closed policy: order head prefixes physically
  by the parser fact and keep body/exhaustion prefixes inside their loop.
  Restore nested retained inputs inside a condition before normalizing that
  condition once; select branch/result inputs independently. Ordinary
  operands, including pure loops under operators, use this same normalizer.
  The retained input belongs to the wrapper's incoming lexical scope;
  semantic substitution, cloning and constructor-type resolution must reach
  it there. Populate it for independently compiled older typed bodies too,
  without reopening source. Global ordinary traversal still sees only the
  legacy view. The alternate is transient, excluded from repr, equality,
  hash, JSON and callable identity, and consumed only by the closed route.
  Legacy normalization and consumption stay unchanged. No local-row
  permutation or name/span-based scope recovery is needed.

### 4.4 Values the run supplies

Four forms name something that only exists at run time. Each is a value in
the closed program, supplied by the evaluator, the same on every resume.

| Rule | Form | Value |
| --- | --- | --- |
| X1 | A call that leaves out a compiler-supplied `RunCtx` parameter | The record `{run-id, state-root: "state/run", artifact-root: "artifacts/run"}`, the present route's constants. `run-id` is the run's id, which is the run root's name (`specs/state.md`: `RUN_ROOT` is `.orchestrate/runs/<run_id>`). It is a `context` value; the run's identity reaches a program only this way (R1) |
| X2 | A call that leaves out a compiler-supplied `PhaseCtx` parameter | The record `{run: <the caller's RunCtx>, phase-name, state-root: state/<phase>, artifact-root: artifacts/<phase>}`, built at the call site from the caller's context value and the phase name, with the phase-scoped roots the [state layout](workflow_lisp_state_layout.md) derives. The closed program holds it as an ordinary record; no hidden parameter exists at run time. For admitted derived-child omissions, retain the existing `carried_input_sources` relation, including `ItemCtx.run`, and the child phase constants; an explicit context wins and a carried run is never replaced by a fresh X1 value. Its equality with the present route's value is an open evidence item (§19) |
| X3 | `phase-target` | The named target's field of the phase context in scope, or the path join `<artifact-root>/<phase>/<target>.md` for a generic `PhaseCtx`, elaborated at the `with-phase` site (§4.3) |
| X4 | `provider-bundle-path` | The committed attempt's result file, relative to the workspace (§8.2): the header's immutable `result_root` joined with the committed record's run-relative `result_path` (§8.4, *Immutable result root*), so it is the same on every resume and equals the destination the performer received (R2). At the new target the form is typed as a path under `.orchestrate/runs` and meets that root whenever the run root lies under `<workspace>/.orchestrate/runs`; both legacy routes type it under `state` and refuse their own value (`outside_under_root`) |

## 5. Values

A value is immutable and typed. The evaluator holds values in an environment:
a chain of frames, one per `let`, `case` arm, `join`, loop iteration and
`call`.

Pure operators have one implementation, the catalog of
`orchestrator/workflow/pure_expr.py`, applied to values. The typechecker reads
the same catalog. A pure operator that cannot produce a value, on overflow,
division by zero or a non-finite result, fails the run with a diagnostic
located at the expression, printing its operands.

No bound applies to the size of an expression. The bound of 256 nodes limits
a serialized payload, and no payload exists. Evaluation terminates because
the checked form (P5) refuses a recursive call and a loop without a budget.
There is no evaluation budget: the spike never needed one, and a budget
would guard against a defect the checked form already refuses.

The run's inputs are bound before anything is evaluated: declared defaults
applied, then each value checked against its declared type by the catalog's
coercion. The run's input digest is taken over the bound inputs. A missing,
undeclared or ill-typed input is refused before the run root holds a record.

## 6. Effect Identity

```text
identity        = (activation path, site)
site            = (definition, local path)
activation path = frames from the entry to the definition
```

| Rule | Statement |
| --- | --- |
| I1 | The site is the definition that contains the `perform` node and the path from the definition's body to it. Two call sites of one definition are two frames over one site |
| I2 | A frame is a call site, written `<label>=<callee>` with the callee's canonical name (§4.2), a loop iteration `loop:<state label>[<i>]`, or, in a later release, a parallel map item `[<index>]` |
| I3 | Local paths follow the traversal table below. Each effect ends in its binding's I4 label, and each effectful call has a frame at its binding. The separator in the presentation is ` / ` |
| I4 | A binding without an authored label takes `#<k>`, its ordinal among the anonymous bindings of its scope whose value performs an effect. A named binding uses its retained authored label even if hygiene changes its lexical name. Pure bindings advance neither anonymous nor repeated-label counters, so a pure refactoring moves no identity. A repeated authored label takes `<name>#<k>` |
| I5 | An attempt is an ordinal under an identity. Attempts never change the identity |
| I6 | The canonical text of an identity is its presentation key: the entry, then each segment, with each `[*]` replaced by the iteration reached. Example: `workflow:search::run-search / loop:state[3] / repair=workflow:search::repair-one / propose` |
| I7 | The canonical text never names a file. A path derived from an identity uses a digest of the text (§8.2) |

Nothing else enters: no source span, no file path, no text of a type, no
position among steps, no visit count.

Lexical names resolve values; authored labels identify effects and control
segments. The compiler retains binding origin before hygiene and never
infers it from `__`, `%`, a hash suffix, or a source location. For example,
a hoisted inner `x` may need a fresh lexical name to avoid capturing an
outer `x`, while its effect label remains `x`. The closed representation's
optional overrides and validation rules are defined once in the Phase 2
plan's [binding-label schema](../plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md#binding-labels).
Labels are semantic data outside diagnostic provenance and participate in
the program digest. Read-back checks internal consistency, not source
authenticity. An unrelated pure edit can change the program digest while
leaving sites and call frames unchanged.

| Construct/edge | Local path and scope |
| --- | --- |
| Definition body | Start at its canonical name; fresh binder scope |
| `let` value / continuation | `perform` ends at the I4 label; `call` records `<label>=<callee>` as its frame, not a site-table row. A bound control value descends under that label. The continuation keeps the enclosing prefix and binder scope; lexical lookup uses the binding's name |
| `if` arms / `case` arms | Append `then` or `else` / the variant; each arm starts a binder scope |
| Bound `select` | Under its I4 label append `then` or `else`; walk that arm's prefix with the same binding-label rule as sequential `let`s in one scope, then its value. Nested effect-containing values are bound in that arm by §4.3 |
| Bound `block` | Under its I4 label append `block`; walk its body in a new scope |
| `join` body / continuation | The first release has exactly one bound-result parameter. Walk the body under that parameter's I4 label and `body`, in a new scope; the continuation keeps the enclosing prefix and scope. The generated continuation target is not the label. Thus a body effect cannot collide with a continuation effect. Jumps add no site or frame |
| `loop` body / exhaustion | Append `loop:<state label>[*]` / `loop:<state label> / exhausted`, each with a new scope; anonymous state parameters use the loop's I4 ordinal. The generated loop target is not the state label. Seeds, budgets and `continue`/`done` operands obey §4.3 |
| Later `par-map` body | Append `par-map:<binder>[*]`; the activation substitutes the input-list index, never completion order. Its input and workspace expressions are evaluated before the body as their contracts require |
| Effect-free value children, `halt`, `jump`, `continue`, `done` | No site; recursively validate their values and targets. No hidden `perform` or effectful `call` may remain outside the walked bindings |

Segments are tagged values internally; presentation escapes literal `%`,
`/`, `=`, `#`, `[` and `]` within authored names using their UTF-8 percent
encoding, so names cannot impersonate separators or generated ordinals.
P5 independently counts every `perform` in each definition and requires a
bijection with the site table, plus one frame per effectful call. It rejects
both an unvisited effect and a call masquerading as a site. Normalization,
validation and evaluation must agree on every child edge in this table.

| Edit | Identity |
| --- | --- |
| Blank lines, comments, reformatting | Unchanged |
| The repository or the package moves | Unchanged |
| A pure binding is added, removed or renamed | Unchanged |
| An authored effect label is renamed, or an effect moves to another branch | Changes |
| An unnamed effect is added before another in the same scope | The second changes. Naming the binding keeps it stable |
| A pure callee gains an effect | The caller's next unnamed effect changes; named effects do not |

Evidence: identities and the program digest are unchanged under blank lines,
under a move of the program and under a move of the orchestrator package;
the ordinal rule's moves are measured against the alternative (gate report,
§2, criterion 5; spike iteration 2, F(c)).

## 7. The Effect Memo

### 7.1 The journal

| Rule | Statement |
| --- | --- |
| M1 | The memo is an append-only journal of JSON lines under the run root, `memo.jsonl`. One writer holds an exclusive lock on it for the life of a run or resume. A second writer is refused with `memo_busy` |
| M2 | Each record is written and synchronized to disk before the evaluator proceeds. No record may be appended until the program artifact, header, empty journal and their directory entries have been durably published (§8.4) |
| M3 | A final line without its newline was never written whole and is not a record. The next writer truncates it before appending |
| M4 | A result exists only as a `committed` record that no later `invalidated` range covers (C8). A file at a path, however valid and however recent, is not one |
| M5 | The `committed` record holds the validated value inline, beside the result file's path and digest. The value is the authority; the file is evidence |
| M6 | A command that writes to the memo from outside a run (the answer of a request for input, an invalidation) takes the writer's lock and appends under it |

| Record | Written | Content |
| --- | --- | --- |
| `started` | Synchronized before exclusive creation of the attempt directory; reserves the ordinal, not proof of a launch | identity, attempt ordinal, digest of the resolved input and of each of its parts, declared implementation-file evidence (C2), result path, time |
| `committed` | After the result passed its contract | identity, attempt ordinal, input digest and parts, the validated value, result path and digest, the digests of the declared files (C2), the identities its input read (C9), `effect_class` from the checked site and the coordinator's proof when required (K5), time |
| `failed` | After an attempt ended without a valid result | identity, attempt ordinal, code, exit information, the contract violations if any |
| `suspended` | When an effect waits for a person (a later release) | identity, attempt ordinal, the request |
| `settled` | After a coordinator's final commit (`by: settle`), or its reconciliation on a memo hit (`by: reconcile`) | identity, attempt ordinal |
| `invalidated` | Once for the whole suffix, by the explicit continuation (C8) | `from_commit`: byte offset of the chosen active `committed` record's first byte; time. No per-effect records; affected identities/attempts are reconstructed from the preceding journal prefix |
| `terminal` | `completed` only after `halt`, every reached effect committed and every committed coordinator settled; `failed` after an attempt or evaluation fails, with no pending start or unsettled committed coordinator | no identity; `completed` with the value of `halt`, or `failed` with the code and message |

A failed terminal does not require the failed effect to have committed.
Failure during settlement leaves a committed, unsettled effect and no new
terminal; resume must reconcile it. The checked program maps each
`effect_class` to ordinary or coordinator execution (only `run_ref` is a
coordinator in the first release). The record's class must agree with its
site, and coordinator proof is required, not inferred from an optional field.

A terminal is reopened by `invalidated`, or, after a failed terminal, the
next `started` record. Preflight refusals and a repeated
pure failure without new journal activity return diagnostics without
appending another terminal. A clean completed resume returns the existing
terminal unchanged (§8.4). Adjacent terminal records are inconsistent.

`state.json` stays. For this profile it is a view (§10), rewritten from the
memo after each record. It is not the authority for any result.

### 7.2 The resolved input

The resolved input of an effect is everything that determines what the
effect is asked to do: its arguments, its assembled prompt with the digests
of its tagged prompt source and of every file the prompt reads, its contract, its
provider binding with the policy in force, and for a command the digests of
what it declares (C2). Its digest, and the digest of each part, enter the
`started` and `committed` records. A divergence names the parts and the
files that differ.

### 7.3 What a command boundary declares

| Rule | Statement |
| --- | --- |
| C1 | Every supplied external-tool and certified-adapter binding (including unused rows), and every used compiler-injected binding retained for emission, declares `closure`, using the common rules below. An empty list is a declaration, not a fallback for unknown implementation files. An absent field is refused at build with `command_boundary_closure_missing`; `null` is not an empty declaration. No build option or builtin exception weakens this rule |
| C2 | The resolved input of a command binds, by content: each stable-command token selected as a workspace path by the conservative rules below, and each closure entry. The normalized declaration and file evidence use the common encoding below. Modification times are not bound |
| C3 | The interpreter, the first token of a stable command when it is a bare name, is resolved on `PATH` once, when the run starts. The run header records its resolved path and digest. Every attempt of the run launches the resolved path, not the name. The interpreter does not enter any effect's resolved input: a changed digest at resume is reported as `interpreter_changed` and the run continues on the recorded path; a missing path refuses the resume with `resume_interpreter_missing` |
| C4 | A command must treat its closure as read-only. Before starting its attempt, check that the concrete runtime destinations for that attempt are disjoint from that command's closure, as below. Rehash before commit and fail the attempt with `command_closure_written` if its declared files changed. Before retrying an uncommitted attempt, compare the current implementation-file evidence with its `started` evidence and refuse any change (§8.1), even if no failure record survived. A resume that finds a committed effect's declared file changed also refuses (C7). The local check does not protect closures from startup, other effects or rejection bookkeeping (§8.2). Commands are launched with `PYTHONDONTWRITEBYTECODE=1` |
| C5 | Outside the promise: modification times; the environment; a file opened by a computed name or imported without declaration; the network; the clock; the provider template behind a provider id and the model behind it; workspace files no boundary declares. A command whose behaviour depends on one of these may be reused with a result no fresh run would give. The promise binds bytes of declared files, nothing else |
| C6 | A provider's prompt source (`asset_file`, `input_file` or document fill) and its prompt dependency files are always bound by content digest |
| C7 | A semantically changed manifest or stable command changes the program identity: a fresh build is compared with the header, and resume is refused with `resume_program_changed` before any memo record is read. A changed bound file diverges only the effects that bind it: preflight checks the active committed prefix in journal order and refuses at the first divergence with `effect_input_diverged`, before any launch or reconciliation (§8.4) |

At build, the implemented C1 checks explicit declarations and the C2 projection
records canonical logical paths in configuration/program identity. It does
not read closure bytes. C2 content hashes, C3 interpreter pinning, C4
read-only/retry enforcement and filesystem evidence remain open runtime work.
Evidence: `orchestrator/workflow_lisp/closed/effects.py::require_command_closures`,
`closed/program.py::_canonical_closure` and `closed/artifact.py` (same directory),
[closure tests](../../tests/test_workflow_lisp_command_boundary_closure.py)
and [public compile tests](../../tests/test_workflow_lisp_closed_program_compile_cli.py).

Automatic C2 selection examines stable-command tokens spelled relative to the
workspace, or absolute tokens whose lexical components have the workspace
root as a prefix. The prefix comparison uses the common separator/`.`
normalization and is component-wise (`/work` does not include `/work-other`),
without resolving symlinks or collapsing `..`.
That normalization also supplies logical evidence spelling;
it must not replace filesystem lookup with a rewritten path. Lookup uses the
original token spelling and ordinary path resolution, including intermediate
symlinks and `..`; argv is unchanged. A relative path or a symlink may resolve
outside the workspace and binds that target under the existing encoding.
An absolute spelling outside the lexical workspace prefix is not selected
automatically; an explicit closure declaration can bind it.

The bare first token belongs only to C3's automatic interpreter pin, even when
a workspace entry has the same name. A workspace-relative slashed or
workspace-prefixed absolute executable token is mandatory C2 evidence even
when missing. An external absolute executable adds no automatic C2 evidence;
its launchability and any explicit declaration still apply. For the remaining
tokens in the automatic scope, select an existing final filesystem entry
using `lstat` semantics, with no inference of argv roles, options, modules,
extensions or executable-specific syntax. Thus a final dangling symlink is
selected and fails when resolved for evidence. Initial `ENOENT` or `ENOTDIR`
means no final entry is selected unless it is mandatory through an explicit
declaration or prior evidence; no empty hash is created. Other lookup errors,
including `EACCES` and `ELOOP`, fail closed with path and reason. An initially
missing token after argv[0], including an endpoint below a dangling parent
symlink, has no automatic file guarantee: declare it explicitly to require it
from the start. In particular, C2 does not infer an absent script in
`python probe.py` from its operand position or extension.

Every explicit closure entry remains mandatory, and `closure: []` does not
disable automatic selection. At each resolution or rehash, union the current
automatic selection and explicit closure with the relevant prior evidence:
the active commit being checked for reuse, the latest uncommitted `started`
for retry, or that attempt's `started` before commit. Preserve its logical
base/path and token position using the same evidence format. Do not union all
history: a start that committed and whose commit was later invalidated does
not pin authorized re-execution to its old bytes (§8.1); a newer uncommitted
start still does. A previously bound path that disappears remains mandatory
and fails closed; a newly appearing entry changes the evidence map and cannot
pass comparison silently. Restoration follows the existing retry rule.

This conservative selection intentionally binds existing literal homonyms,
including directories such as `.`. They incur the same hashing and C4
read-only/destination-disjointness rules as explicit declarations, even when
the command treats them as data. For example, a selected workspace `.`
covers the concrete attempt/journal destinations beneath `.orchestrate/runs`;
C4 refuses the command before its `started`, attempt-directory creation or
dispatch. Initial authority, caches and locks may already exist; the refusal
does not promise that the initial run root was never created. This cost is
accepted without a semantic-role exception or a new class/form admission
restriction. It does not promise success for every literal command or permit
a new `closed_program_gap`.

The manifest grammar is `"closure": [<path string>, ...]` for both boundary
kinds. Each entry is a nonempty literal path without NUL; there are no globs,
exclusions or environment expansion. Relative paths are based on the command's
workspace, not the manifest directory or entry module. Absolute paths retain
their declared location. Normalize redundant separators and `.` components
to POSIX spelling, preserve `..` until filesystem resolution (a preceding
symlink can change its meaning), then sort and deduplicate the declaration.
Overlapping directory/file entries are allowed and do not create exclusions.
This normalization does not rewrite stable-command argv or change its existing
path resolution. An explicitly absolute declaration remains location-bound;
moving source files alone does not rewrite it.

Compiler-supplied adapters have an authoritative checked-in path array beside
their existing binding declaration (`stdlib_contracts.py` for the stdlib
catalog; the existing compiler factory for other injected adapters). Its
relative base is the installed `orchestrator` package directory, not the
workspace. No new user field chooses this base: trusted binding origin,
preserved during injection, determines it. A retained manifest override keeps
manifest semantics even when its name matches a builtin. Origin follows the
effective binding instance, including an existing injector replacement.
Normalize both origins into closed rows `(base, path)`, where base is `workspace`, `absolute`, or the fixed
logical package identity `package:orchestrator`; the hashing and read-only
rules are otherwise shared. An injected adapter without the checked-in
declaration refuses with `command_boundary_closure_missing`; supply the
declaration to admit it, rather than exclude its command class.

For the current builtin `validate_review_findings_v1`, the bounded initial
declaration is `["."]` under `package:orchestrator`. Importing its parent
package loads the compiler, and its result helper imports shared contracts
and I/O code, so the leaf adapter file alone is not its implementation.
Declaring the package directory avoids an import-discovery system or a guessed
empty closure; it intentionally makes other package-file changes diverge too.
A smaller future checked-in closure needs evidence for its complete package
dependencies. All package caches must therefore be disabled or outside that
directory in both evaluator and child processes; existing caches are not
excluded from directory hashing.

Resolve this logical base through the loaded package location already used
by `_builtin_stdlib_source_root` and the command executor's package/PYTHONPATH
seam. The absolute installation prefix is launch-time location, not program
or input identity: evidence paths/targets within that package use
`package:orchestrator/<relative path>`, while a symlink escaping it retains its
absolute resolved target under C2. Identical package bytes moved together keep
the digest; changing those bytes diverges. Before dispatch, the builtin
module's resolved launch origin must be this declared package tree (including
workspace/PYTHONPATH shadowing checks); hashing one installation and executing
another is forbidden. Keep the existing module command and resolver seam,
with a fail-closed origin check, not a second adapter loader or a user knob.

The exact canonical row variants and writer/reader correspondence are in
[the Phase 2 plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md#canonical-command-configuration).
Both binding kinds retain every semantic model field, explicit defaults and
normalized closure; certified rows retain raw signature type strings and
promoted-field presence. No old-target fingerprint projection changes.
Source input/return checks still resolve types in the caller's environment;
`owner_module` metadata is not a resolver. The reader checks complete row
shape, selected scope, stable tokens, repeat/closure agreement, admitted
protocol and ordered document keys, and independently validates closed values
and result/output contracts. It does not reconstruct alias history or
manifest-input assignability from raw type strings: a document row contains
no expected input descriptor. Preserve admitted duplicate signature rows
and omit unresolved optional inputs without inventing a new restriction.
This is an explicit internal-consistency contract, not source authenticity.

At build, grammar and presence are checked; filesystem contents belong to
resolved inputs at run/resume, because the workspace may not yet exist.
Both binding models preserve absence separately from `[]`. The closed
artifact includes the canonical normalized command configuration for **all**
manifest entries, including unused ones, and injected bindings actually used
by the program, beside the resolved extern bindings. Package declarations
contribute logical base/path rows, never their installation prefixes.
Thus changing an unused boundary changes the program digest (C7), not only a
build-cache key; JSON whitespace or key order alone does not. The same
canonical type/configuration rules apply to in-memory bindings. Independent
compiled producers retain those same canonical configuration maps under
`configuration.imports`, keyed by their semantic configuration digest. Each
imported definition selects its scope; an unscoped definition uses the root
configuration. The checked form verifies scope resolution and each effect's
binding against that scope. Identical configurations may share a row; caller
bindings never overwrite producer bindings, and unused producer bindings
still enter the program digest. No incidental source/install path or old bundle
fingerprint is added by this scoping rule; authored semantic paths remain. Source-read
and module identity facts must come from the compile that built the program,
not a later reread that can race a source edit. Raw source-byte fingerprints
belong to the build cache; they do not enter the semantic program digest and
undo P6's formatting invariance.

Runtime evidence is an ordinary map, `{}` when empty, with no wrapper or
version. Each key is the canonical JSON string of `[base, path, position]`
(the serialization used by `closed/program.py::canonical_digest`),
where base is `workspace`, `absolute` or `package:orchestrator`, path follows
the normalized declaration rules above (relative for workspace/package,
absolute for absolute), and position is `null` for a declaration or a
nonnegative integer, never Bool, for a stable-command token. Serialize keys
in sorted order. Declarations and token positions are distinct obligations.
Every exterior value has exactly `kind` (`file` or `directory`) and `digest`
(`sha256:` followed by 64 lowercase hexadecimal digits), plus only the
optional `target` described below. File digests bind the regular file bytes.

For an entry whose lookup traverses symlinks, `target` binds its final resolved
destination, not link text or a list of intermediate links. Targets are
nonempty, NUL-free strings in canonical resolved POSIX spelling. A target
within its workspace base uses the relative path from that base (`.` for its
root); within its package base it uses `package:orchestrator/<relative path>`
(`package:orchestrator/.` for its root). Outside that base, or for an absolute
base, it uses the absolute resolved path. Relative targets do not escape with
`..`; resolved spellings have no redundant separators or unresolved `.`/`..`
components except the stated root forms. Moving a package and its internal
targets together preserves these logical spellings. Changing link text or
an intermediate link without changing the final target or bytes does not
alone require divergence.

A directory's digest uses `closed/program.py::canonical_digest` on one flat
list of the following exact rows, sorted uniquely by normalized relative
POSIX `path` within that directory:

| Traversed entry | Internal row hashed in the directory list |
| --- | --- |
| Regular file | `{"path": p, "kind": "file", "digest": d}`, with only optional `target` when its lookup traverses symlinks; digest and target use the exterior rules |
| Internal symlink resolving to a directory | `{"path": p, "kind": "directory", "target": t}`, with no `digest`; target uses the declaration's base encoding |
| Ordinary directory | No row of its own; traverse its children |

All files, including dotfiles and caches, participate. Ordinary empty
directories contribute no rows. Each internal directory symlink contributes
its identity row even when its target is empty, then its target's files are
traversed under the logical path through that symlink; nested directory
symlinks contribute their own rows. Do not add another recursive digest for
the identity row. A declared root reached through a symlink records its
target in the exterior value, without a duplicate internal `path: "."` row.
Different logical aliases to the same target keep distinct rows and are not
by themselves cycles. A duplicate internal path is an error, never an
overwrite. Resolve and validate the target before emitting a row:
cycles, missing/dangling entries, unsupported file kinds and unreadable files
fail closed. No absent path is hashed as an empty file. On a memo hit these
failures are divergences; before a first attempt they are closure-resolution
failures. The path and reason are reported.

The writer and journal reader enforce this same exterior shape, reversible
canonical keys, valid bases/paths/positions, digests and target grammar;
extra fields, alternate key spellings and internal identity rows used as
exterior values are refused. The internal list is not persisted. A reader's
shape check cannot certify symlink presence, filesystem contents or a hash's
material. The same live resolver reconstructs evidence for initial binding,
precommit, retry and reuse and compares it with the relevant prior map;
a stored opaque digest never substitutes for fresh resolution/rehash.

For a command that needs a new attempt, its concrete runtime destinations
must not equal a file in that command's closure or lie beneath one of its
directories, including resolved symlink aliases. During that same
live walk, retain transient resolved coverage of closure directory roots,
traversed directory-symlink targets and regular leaves. C4 consumes this
coverage and resolves destinations through their existing ancestors before
creation: a new descendant under an external empty directory-symlink target
is covered even though it has no file row. Do not infer this coverage from an
opaque digest, persist a target list or discover it with a second resolver.
The caller computes the next ordinal and paths in memory after the memo's
reuse/divergence/retry decisions. Pass the current command, its closure and
explicit destinations to the filesystem helper: directories to create,
`inputs.json` when applicable, `result.json`, stdout/stderr, known runtime
caches and bookkeeping paths to modify during the attempt (`memo.jsonl`,
`state.json`). Check before `started`, mkdir or constructing `StepExecutor`,
whose constructor prepares capture. A replacement temporary whose name is
only determined later is checked before creation through the same safe file
mechanism; its parent is not reserved as a whole tree. A nonconflicting leaf
inside the run root is not rejected merely for belonging to that namespace.
A memo hit creates no attempt and needs no preventive destination check.

This is a local check of the command being prepared. The helper receives
paths, not the checked program, sites, effect identities, memo or reachability.
It does not trace the effects that produced inputs, inventory future commands,
preview the entry, accumulate earlier closures or sweep them around every
write. A branch never reached adds no C4 filesystem check to startup or a
clean completed resume; C1 and C3 retain their independent scopes. Startup
publication and earlier effects may already have written within a closure
only discovered later. No rollback, retroactive protection or snapshot against
external filesystem changes is promised. Bookkeeping of a local refusal is
permitted under the memo transition rules even inside the rejected closure
(§8.2); the workspace need not remain byte-identical. C2/C7 still detect
pertinent changes, including writes by another command.

A token absent at preparation may appear during the attempt: precommit C2
rehash selects it and refuses a changed evidence map rather than committing
silently. A command that writes an undeclared cache in its closure violates
C4 and its changed closure refuses resume. There is no ignored-cache rule.
The adapter's positional JSON input remains value data (§9.1), never an
implicit closure entry. These rules alter only the new target's identity and
runtime route; targets through 2.34 omit `closure` from binding serialization
and identity payloads even when supplied (§13). Their existing build-cache
fingerprint of raw manifest bytes stays unchanged as an algorithm: editing
the file can still change that cache key. No compatibility shim is needed.

The spike's evidence for C1 to C5 is its five-case table (spike iteration
3, B): with the closure declared, a changed second script, a changed
directory, a changed `PATH` program and a retargeted symbolic link
each refuse; a change of modification time alone reuses. Without a
declaration, the second script was reused silently (gate report, §6);
C1 makes the declaration required. The spike bound the interpreter per
effect, which made an upgrade refuse every resume (gate report, §6); C3
fixes it for the run instead. The spike offered `declared`, `strict` and
`trusting`; this design keeps one rule, C1, because an option that reuses
undeclared work is the defect the last review found.

C3 deliberately does not re-resolve a bare interpreter name on resume. A
different `PATH` entry alone emits no `interpreter_changed`; that diagnostic
means the bytes at the recorded executable path changed. The recorded path
must still be launchable; a missing or unusable executable refuses with
`resume_interpreter_missing`. Absolute/slashed stable-command executables
keep their existing resolution and declared-file rules.

The header's `interpreters` map has exactly one entry per distinct literal
`command[0]` without `/` in emitted `perform` nodes of class `command`,
across the entry body and all definition bodies, including unexecuted branches.
Its key is that exact token; its value has only `path` (an absolute path without
NUL) and `digest` (`sha256:` followed by 64 lowercase hexadecimal digits).
Resolve each name once before authority publication and preserve the selected
path spelling, including symlinks and `..`. Configuration without an emitted
site and embedded child run-reference programs add no parent-run pins.
Loading authority validates exact key coverage and pin shape without resolving
`PATH` or observing executables; live interpreter checks belong to resume.
Attempts select the recorded path by the original `command[0]`. This map is
independent of effect input identity and local C4 checks.

## 8. Evaluation And Resume

### 8.1 What the memo decides

Evaluation of `perform` at identity `i` with resolved input `x`:

These actions follow §8.4's preflight and clean-terminal return; a read-only
view never invokes reconciliation.

| Memo holds for `i` | Action |
| --- | --- |
| A committed result with input digest equal to the digest of `x`, not invalidated | Return the result. Run nothing. For a coordinator effect, `reconcile` first (K3) |
| A committed result with another input digest | Stop with `effect_input_diverged`, located at the site, showing both digests, which parts of the input differ and which files |
| A `started` or `failed` attempt with no commit | Before retry, enforce C4's implementation-file comparison below. If the boundary declares `must_not_repeat`, stop with `lexical_restore_pending_effect_unsafe` regardless. Otherwise record `effect_rerun`, naming the identity and its earlier attempts, and run the next attempt |
| An `invalidated` range covers the last commit, with no newer uncommitted attempt | Run the next attempt. No rerun diagnostic |
| A `suspended` record and no commit | Stop and report the pending request |
| Nothing | Run the first attempt |

`must_not_repeat` is the manifest field that exists today
(`specs/state.md`; command adapter contract). The spike stood in for it with
a build option; the field is the declaration.

For a command whose latest `started` has no corresponding `committed`, the
implementation-file evidence in that start is the retry baseline. This covers
explicit `command_closure_written`, any other failed attempt, and a crash
before the failure record, including before dispatch. Compare all C2-bound
implementation paths, including package closures and stable-command files,
but not C3's interpreter. Changed, missing or unreadable evidence stops resume
with `effect_input_diverged` before another `started` or launch. Restoring the
original bytes/targets permits the ordinary next-attempt rule, still subject
to `must_not_repeat`. No override or additional approval surface is introduced.
An invalidation may cancel committed results, but cannot forgive a newer
uncommitted attempt's closure mismatch. A start that did commit and was later
invalidated does not pin that explicitly authorized re-execution to old bytes.

### 8.2 Running an attempt

1. Under the writer lock choose one more than the greatest `started` ordinal
   for this identity (1 if absent), including failed and invalidated attempts.
   Derive `effects/<digest of the identity>/attempt-<n>/` and its result path
   in memory. For a command, resolve C2 and check the explicit destinations
   against its current closure (§7.3) before `started`, directory creation or
   capture/`StepExecutor` construction. Append and synchronize `started`
   **before** creating that directory.
2. Create the directory exclusively and synchronize its parent. If it exists,
   preserve it, append `failed` with `effect_attempt_path_exists`, and stop.
   Other allocation failures also fail the reserved attempt. Never launch
   until allocation succeeds; a failed append/synchronization also stops.
3. Launch through the performer of the effect's class (§9.2), or through
   the coordinator's `prepare` (§9.3), with the result path
   `<attempt directory>/result.json`.
4. Validate the result against the contract. Project it to the declared
   type: undeclared keys are dropped.
5. Append `committed`, or `failed`. Only after a coordinator's `committed`,
   call `settle` and append `settled`.

The file of an earlier attempt is never removed or overwritten. Each attempt
has its own directory, so the evidence of a failed attempt stays beside the
result of the one that succeeded. The attempt directory also holds the
attempt's `stdout.txt`, `stderr.txt` and, for a provider, `prompt.txt` (V6).

A failed attempt stops the run, as `on_error=stop` does today: the memo gets
the attempt's `failed` record and, only when no pending start or unsettled
coordinator remains, a `terminal` record with outcome `failed`.
A resume runs the next attempt unless `must_not_repeat` refuses it. For
commands and portable providers, one memo attempt permits one external
dispatch: bypass internal executor retries. Retryable failures still stop
this run; resume reserves the next ordinal. A coordinator's child attempts
remain governed by its existing ledger and K2 to K4.

Local path refusal bookkeeping may be persisted even when its destinations
fall inside the rejected closure. It authorizes no new attempt or dispatch;
it follows the actual memo state, not an unconditional catch-all terminal:

| State when preparation/path checking fails | Allowed persistence |
| --- | --- |
| Before a new start; no pending/unsettled effect or terminal preventing append | Ordinary failed terminal and view may be written; never invent `failed` for an attempt without a start |
| Resume readonly preflight or pertinent baseline comparison refuses | Diagnostic only; preserve authority, memo, attempts and views |
| Retry `n+1` rejected before its start while `started(n)` remains pending | Diagnostic only; preserve that start, its baseline and the next ordinal. No terminal, `started(n+1)` or fabricated `failed`; do not close `n` artificially to permit a terminal |
| Existing failed terminal without new activity | Do not duplicate it |
| A later-named destination fails after the current attempt's real start | Do not create that destination; fail the already reserved attempt using its actual ordinal. Add a terminal only when no pending/unsettled effect remains and no prior terminal forbids it |

A post-command closure rehash failure uses the same normal failure persistence,
even if new coverage reaches the journal/view. Never replace the start's
evidence, adopt orphan output or bypass the retry baseline because no `failed`
record survived.

### 8.3 What a stop leaves, and what resume does

| The process stops | The memo holds | Resume |
| --- | --- | --- |
| Before `started` is appended | No record or directory for this attempt | Allocate from the complete records |
| During append/synchronization of `started` | A complete or torn line may survive; no directory created by this attempt | A surviving complete record consumes its ordinal; discard only a torn line (M3). Apply the next-ordinal and `must_not_repeat` rules if a complete `started` survived |
| After `started` is synchronized, before or during directory creation | `started`; directory may be absent or empty | Reserve the next ordinal; never reuse/delete the old directory. `must_not_repeat` refuses conservatively even though launch may not have occurred |
| After exclusive creation, before launch | `started` and the attempt directory | Same next-ordinal rule; preserve all prior evidence |
| While the effect runs, or while it writes its result | `started` | Treats the attempt as one without a committed result. A partial file does not parse or does not validate, so it is never a result |
| After the effect finished and before `committed` is written | `started`, and a complete result file | Same as above: the file is evidence, not a result. Only `committed` makes a result |
| After `committed`, before a coordinator's `settle` | `committed` with the proof | Returns the result; `reconcile` completes the coordinator's commit (K3) |
| After `committed` | `committed` | Returns the result |

Resume is evaluation from the entry with the memo of the run. Because
evaluation is a function of the program, the inputs and the committed
results, it reaches the same effects in the same order up to the first effect
without a commit. Evidence: 168 stops inside the process and 96 kills from
outside, each resumed to the uninterrupted value with no committed effect
run twice (gate report, §2, criterion 3).

### 8.4 The run header and the representation

The exact evaluated selector is
`result_persistence_profile: "evaluated_execution.v1"`, with
`schema_version: "3.0"`, in both `run.json` and its derived `state.json`.
These name the memo-backed run contract; the independent closed-artifact
schema remains `workflow-lisp/closed-program/1`, representation `table/1`.
There is no per-record version or second runtime selector. Schema 2.1 with
an absent profile, or `derived_pure_replay.v1`, retains its existing route.
Unknown profiles or unsupported versions in authoritative run metadata fail
closed; they never select the flat route. Dispatch recognizes the header
before applying legacy state/status checks. A missing, stale or contradictory
view is reconstructed from the header, checked program and memo, not used
to infer or upgrade the profile. A missing header with journal activity
remains `memo_inconsistent`. No legacy state is converted.

The run root holds `run.json`, written before the first record: the program
digest, the input digest, the bound inputs, the representation version of
the closed program (§4.2), and the interpreters fixed for the run (C3). The
program artifact is written beside it.

Every newly published evaluated header also records `resume_request`, the immutable recipe for rebuilding the public entry. It has exactly `source_roots` (an ordered array), `entry_workflow` (the originally requested nonempty, NUL-free name or null), `provider_externs_path`, `prompt_externs_path`, `imported_workflow_bundles_path`, `command_boundaries_path`, `input_file` (each a locator or null), and `input_overrides` (a finite JSON object of explicitly supplied values before input binding). `workflow_file` is the source locator; the effective workspace of the run/resume entry supplies `workspace_root`. The remaining compiler options retain this public route's fixed defaults; resume emits no debug build artifacts. Capture the effective invocation, not process argv, monitor metadata, build-cache state or configuration recovered from the stored program.

Persist normalized paths relative to that workspace when within it, and absolute otherwise; use `.` for its root, preserve source-root order and multiplicity, and preserve an omitted entry selection as null. Locators are nonempty, NUL-free canonical POSIX paths, with no parent components in relative paths. Resolve relative locators under the effective workspace on resume, without expanding environment variables or `~`; absolute locators retain their absolute destination. Header validation checks their shape without opening their targets. Process-descriptor paths are not durable locators: a reserved-root caller must supply stable logical locators while retaining its existing descriptor authority and identity checks for access/publication. A logical workflow locator alone does not supply the roots or manifest locators. Normalization preserves the initially resolved destination; retargeting the original flag's symlink spelling does not change the recorded locator. Subsequent reads follow the existing loaders, with no global confinement or relocation promise for external absolute paths.

Reserved-root callers supply a complete pair of logical and physical `FrontendBuildRequest` values, built from the same retained snapshot. Source, ordered roots, entry, compiler options and manifest presence agree; `input_file` is paired separately through its existing recipe field, since it is not part of `FrontendBuildRequest`. Each physical FD locator has an explicit logical counterpart before publication. Initial compile, file reading and binding use the retained descriptors; logical locators supply only durable spellings. Do not infer missing locators from `logical_workflow_path`, use `readlink`/`Path.resolve` on FD aliases, or reopen logical paths to recover physical authority. The two reserved prompt callers retain target 2.27 and their existing restrictions: materialized source `snapshot.run_orc`, roots `[snapshot.root]`, entry null, providers/prompts at `snapshot.root/{providers,prompts}.json`; inference source `prompt_inputs/infer-output-contract.orc`, roots `[prompt_inputs]`, entry null, providers/prompts under `prompt_inputs`. Their other two manifests and input-file are null; their actual explicit overrides remain unchanged.

Publication and all subsequent header/artifact/memo/evidence IO under a reserved root retain its writer lock, `(dev, ino)` checks and directory descriptor throughout. Use descriptor-relative `WorkspaceFiles(root_fd=...)` operations, including memo append/repair and terminal/failure publication; checking the FD then writing by path is insufficient. Never close a borrowed FD or persist it in a recipe/header/request. A snapshot-path replacement must still read the original snapshot FD; a detected run-root replacement refuses without writing into the substitute. IO between a check and an external swap can access only the retained root, not the substitute; this is not a transaction against external swaps. A new resume acquires ordinary locks and physical root authority anew; explicit locators beneath it can resolve relative to that descriptor, while external locators retain their existing loaders and missing/changed sources retain their fresh refusals.

CLI overrides preserve the parser's values before binding: strings for `--input`, with the last duplicate name winning. An admitted service caller preserves its explicitly supplied JSON values before binding. Read the indicated input file anew, then apply these overrides and bind against the freshly built program; do not seed that operation from historical `bound_inputs` or copy applied defaults into the recipe. Missing or invalid requested files remain preflight failures even if overrides cover their fields. Compare the fresh program digest before binding inputs; only an equal program proceeds to the fresh input-digest comparison. The same recipe supplies initial binding and every resume, without a second read solely for publication; normalize `input_file` before that initial read and use that same locator. With no file or overrides, bind the fresh program's defaults again. The recipe itself adds no program/input identity component and no snapshot guarantee against concurrent file changes.

Previously published headers without `resume_request` remain valid stored authority for read-only projection and invalidation. Resume refuses them with `resume_request_missing` before reading memo records or changing authority, memo, attempts or views; no recipe is inferred or backfilled. A present but malformed recipe is `memo_inconsistent`: its eight fields are mandatory and exact, including string keys and finite JSON-transportable override values; null for the object, missing/unknown fields or invalid locators are not historical absence. New publication requires a valid explicit recipe, validated before creating the run root. This preserves the existing profile/schema and does not convert or retire a run representation. Invalidation never requires current source/configuration/input equality or a rebuild recipe; ordinary stored-authority and journal validation still apply. A caller that selects additional semantic compiler options must have their preservation concretely specified before admission; the ordinary entry's fixed defaults do not silently cover such a caller.

#### Immutable run-reference root

Every newly published evaluated header records `run_ref_root`: the canonical absolute string returned by `resolve_run_ref_root` for the effective request, including the default. It is outside the unchanged eight-field `resume_request`, program/input digests and representation. Capture it without creating its directory, materializing a child, checking overlap or scanning effects. Overlap and physical-root checks remain local to coordinator use. Legacy runs retain lazy root binding. Resume uses the published root even if HOME changes or no flag is supplied; after a valid recipe is established, an explicit equivalent flag is permitted and a different root refuses `resume_run_ref_root_changed` in header/option preflight (exit 2), before evidence writes or replay. A valid header without a recipe first refuses `resume_request_missing`. Allocation, bindings, proof and ledger must agree with that root; monitor metadata, derived state or an environment-selected ledger cannot supply it.

A present root is checked by spelling only: absolute normalized POSIX, nonempty and NUL-free, with no parent components or process-FD aliases. Do not resolve/open/create it merely to validate header shape. A malformed present root is `memo_inconsistent`, including read-only loading and invalidation. Readers admit historical presence/absence combinations of recipe, root and result root (below) using the same validators; absence does not make the internal fields of a present recipe optional. Schema `3.0`, profile `evaluated_execution.v1` and artifact `table/1` remain unchanged. Update strict readers and publication together; older readers may reject the new fields, never reinterpret them as legacy. Do not backfill historical headers; writers/readers needing the root consult the header, with no view duplication required.

A historical missing root is neither a default nor authority to infer/backfill one from a new flag or ledger. Read-only loading, invalidation and a replay whose reached path needs no run-reference remain permitted. A missing recipe still refuses `resume_request_missing` before memo; otherwise preserve fresh program → fresh inputs → stored artifact → pertinent replay. Missing root is decided at one of two boundaries, without extending that replay beyond its first uncommitted effect:

1. A run-reference reached as an active commit or the first uncommitted effect during authorized replay refuses `resume_run_ref_root_missing`, exit 2, before tail/view repair, writes, dispatch or reconcile.
2. A run-reference reached only after continuation executes new commands/providers refuses the same code locally, exit 1, before reserving its `started`/attempt or calling its coordinator prepare. Preserve legitimate prior repairs, attempts, results and commits; there is no global no-write or rollback promise. The existing failed-terminal guard appends only without pending/unsettled effects or a prior blocking terminal, and never duplicates an unchanged failed terminal or invents a run-reference start/failure. The next resume that now reaches this boundary in replay refuses exit 2 without another terminal.

A dormant branch does not block completed/pure resume. Do not scan future coordinator sites, preexecute effect results or change C4's checks immediately before the reached mutable command attempt. Missing historical root does not weaken fresh-source/input error priority or cause early memo reads.

#### Immutable result root

Every newly published evaluated header records `result_root`: the run root relative to the effective workspace, the one coordinate X4 needs that no other stored fact supplies. The run root's position under the workspace is not recoverable from the run root alone; the same physical tree reads differently against different workspaces, and the memo deliberately stores run-relative result paths. Default `.orchestrate/runs/<run_id>`; with `--state-dir DIR` (`specs/cli.md`), the relative spelling of the resolved `DIR/<run_id>` against the workspace, for example `.orchestrate/runs/custom/<run_id>` for a nested override and `../state/runs/<run_id>` for one outside the workspace. It is one string outside the eight-field `resume_request`, `run_ref_root`, the digests and the representation.

Canonical form, checked by spelling only: a nonempty, NUL-free, relative POSIX path in normalized form (`os.path.normpath` leaves it unchanged: no `.` or empty component, no trailing separator, parent components only as a leading run) whose last component equals the header's `run_id`. Absolute spellings, and with them every process-descriptor alias, are rejected. Nothing is resolved, opened or created to validate it. A present malformed value is `memo_inconsistent` in every loader, so resume, read-only views and invalidation refuse before any memo record is read.

Who writes it, and from which facts:

- The public run entry: the resolved effective workspace and the state manager's logical run root, under the default or overridden runs root. A reserved-root caller supplies that same logical spelling; its retained descriptor is IO authority, never a header value.
- The path-mode child (`_execute_closed_path`): the request's `clone_root` and `child_state_dir / child_run_id`, which the request decoders already fix to `.orchestrate/runs/<child_run_id>`.
- The publication API takes the value explicitly and validates it before the run root is created or the program published, beside the recipe and locator checks. A direct caller that names no workspace may omit it; the header then lacks the field and the run behaves as a historical run below. Neither production publisher omits it.

Both publishers and resume derive the relationship with the lexical relative-path function R2 already uses for the performer destination; no filesystem access, no current-directory guess.

One lexical derivation supplies X4: `<result_root>/<result_path>`, the string join of the validated header fact and the committed record's run-relative `result_path`. Fresh execution, both reuse paths (prefix replay and a reached commit) and view replay, whether synchronized publication or source-free load, use that join and nothing else: no filesystem IO, no current directory, no source recipe, no provider output document. Memo rows, effect identity, input and result digests, the physical destination handed to the performer and the typed root the checker requires (`.orchestrate/runs`) do not change; `state.json` does not duplicate the field. A run whose root is not under `<workspace>/.orchestrate/runs`, whether inside the workspace elsewhere (`--state-dir state` gives `state/<run_id>`) or outside it with leading parent components, refuses at the reached form with the existing path refinement `pure_expr_operand_type_mismatch`, never a plausible default path. X4's refinement failure is an evaluated value error located at the form, like a pure operator's refinement failure: view replay stops there as at any pure failure before its terminal, the runtime appends the ordinary failed terminal, and read-only loaders then report a failed run rather than inconsistent authority. Programs that reach no X4 run under any state directory.

Resume compares the current relationship, the relative spelling of the selected run root against the resolved resume workspace, with the stored value in header/option preflight, after `resume_run_ref_root_changed` and before the fresh build. A difference refuses `resume_result_root_changed` (exit 2) without reading or writing evidence. The comparison is unconditional and independent of whether the program reaches X4: a resume from a workspace whose relationship to the run root differs refuses even a pure or command-only program. Relocating the whole workspace with the run root inside it keeps the relationship and is accepted, as is an explicit `--state-dir` that names the same relationship.

Historical absence is lazy, as for the run-reference root. The header loads; read-only projection, invalidation and resume of a run whose reached program needs no X4 proceed unchanged; nothing is inferred from the current directory or backfilled. Effect values of such a run carry no workspace-relative result path, and only a reached X4 refuses, with `result_root_missing`: during resume preflight replay, exit 2 before tail repair, dispatch or any write; after continuation has committed new effects, through the existing failed-terminal guard (exit 1), after which the next resume's replay refuses again with exit 2 and duplicates nothing. Read-only replay stops at that form as at any pure failure before its terminal, with no error row. A completed terminal whose replay reaches such an X4 is refused by resume with `result_root_missing` (exit 2) and reported `memo_inconsistent` by read-only replay under V3; genuine publication never produces it, because headers without `result_root` are published only where X4 refuses before any terminal.

Initial publication is durable:

1. Create the run root and empty journal, hold the writer lock, and synchronize
   every newly created ancestor's directory entry, including the run root's
   entry in its parent. No attempt or external dispatch is allowed yet.
2. Publish the checked program artifact via a same-directory temporary file:
   write, synchronize the file, atomically rename to its final name, and
   synchronize the containing directory. Publish `run.json` the same way,
   after the program artifact, binding its digest. Reuse the existing durable
   atomic-write helper; ordinary atomic replacement without synchronization
   is insufficient.
3. Synchronize the empty journal and the run-root directory containing all
   three entries. Only after every operation succeeds may any journal record
   become durable or an attempt be allocated/dispatched. Never replace the
   header or program after journal activity begins.

A crash during publication may leave an incomplete initialization, but no
effect has been dispatched. Resume launches nothing until both authority files
are valid and durably present. A nonempty journal with missing/invalid
authority is `memo_inconsistent`; never rebuild missing authority from current
source or overwrite it. This uses the header's existing readiness role, not
an additional initialization journal or marker.

Resume takes the existing writer locks without changing authority, memo,
attempts or views. Lock-file ownership publication retains its existing
operational seam and legacy defaults; it is not an exception allowing writes
to that evidence, nor a new protocol requiring pre-existing locks. First
validate the header/profile/version/run identity and the shapes of any present
recipe/run-reference root/result root, without loading the stored artifact or
any memo record. Malformed
stored authority retains `memo_inconsistent`. A valid header without a recipe
refuses `resume_request_missing`. With a valid recipe, check any explicit
run-reference root-option mismatch, then the result-root relationship
(*Immutable result root*), before continuing to the fresh build.
Resolve the recipe's source, ordered roots and manifests under the effective
workspace and freshly build the authored entry in memory with their current
configuration, without publishing or recovering build caches. Compare the
fresh program digest first; only after program equality read the requested
input file, apply its explicit overrides, bind against that fresh program and
compare the input digest. A mismatch refuses with
`resume_program_changed` or `resume_inputs_changed` before reading any memo record or mutating run
evidence. An invalid fresh build is also a preflight refusal. Formatting and
provenance-only changes are allowed by P6, not raw source-byte equality.

Then validate the stored artifact's checked form and header digest; execute
that stored artifact after equality is established. Rebind the physical
provider context derived by the fresh build to this validated stored artifact;
it is not replacement program authority. Check C3's recorded interpreter paths
before any memo record. Fresh-build/file/binding errors are public preflight
refusals (exit 2), not tracebacks or failed-terminal publication.
Read complete memo records
without repairing them yet and validate their classes, sites and settlements.
Before any mutation of authority/memo/attempts/views, launch or coordinator
reconciliation, replay the active committed prefix using stored result values,
freshly resolving every input and checking it in commit order. This supplies later inputs dependent on earlier
results. At the first uncommitted effect, also check any latest command
`started` implementation-file evidence under §8.1 before stopping preflight.
For a provider with a pending start, resolve its pertinent local C6 inputs in
memory before permitting torn-tail repair. A required source or dependency
that is missing or unreadable refuses without changing authority, memo,
attempts, views, the prior baseline or the next ordinal. This preparation does
not reserve/start an attempt, prepare the provider executor, publish evidence
or check other providers. Readable changed C6 may supply the new retry; there
is no provider C4 implementation-file baseline comparison. An active
later commit that replay cannot reach is inconsistent, not permission to
launch past it. Only
after preflight passes may M3 repair a torn tail and evaluation continue.
This preflight and evaluation share one interpreter; they are not separate
resume planners. Fresh-build preparation in memory belongs to resume
preflight. Run startup retains its publication route above; C4 checks only a command needing an attempt (§7.3).
Files changed concurrently after preflight remain outside a snapshot guarantee;
an input is checked again on encounter before reuse.

If the last complete record is a valid completed terminal, replay must reach
the same `halt` value, with all settlements present. Return that terminal
without modifying authority/memo/attempts/views, repairing a torn tail,
appending records or launching/reconciling work. There is no global closure
location/hash check or new condition for a never-reached command; C3 and
the pertinent replay checks still apply. An unchanged failed terminal with no
new activity is likewise not duplicated.

The representation is part of the program identity. A run started under one
representation is finished, resumed or abandoned under it; a memo is never
converted. The first release ships one representation, the table form, so
the rule bites only when a later release changes the form: then a run in
flight completes on the release that started it.

### 8.5 Explicit continuation after a divergence

The public entry is `orchestrator invalidate RUN_ID IDENTITY [--state-dir DIR]`
(also `python -m orchestrator invalidate ...`). `RUN_ID` and `--state-dir`
resolve exactly as for `resume`: the current workspace's
`.orchestrate/runs/RUN_ID`, or `DIR/RUN_ID`. `IDENTITY` is one shell argument
containing the exact canonical text shown by `report`, not a label, prefix,
digest or filename. For example:

```sh
python -m orchestrator invalidate "$run_id" 'workflow:search::run-search / evaluate'
python -m orchestrator resume "$run_id"
```

The command takes the same run-writer lock as execution, validates stored
authority and the complete journal prefix, then applies C8. It does not
freshly compile source or demand equality of current effect inputs: the
purpose is to authorize continuation after those inputs diverge. Program
and input checks still apply on the subsequent resume. It launches nothing
and does not resume automatically. No force, cascade or alternate-scope
option exists. Success prints the appended range record as JSON and exits
0; refusal prints its diagnostic and exits 2, following the existing
out-of-band `input` command convention. An old-profile run refuses with
`invalidate_profile_unsupported`; malformed evaluated authority refuses with
`memo_inconsistent`. All C8 refusal checks precede tail repair or any write.

A resume that stops with `effect_input_diverged` does not rerun anything.
For a committed result, the continuation is C8. For an uncommitted attempt's
implementation mismatch, restore its `started` evidence under C4; invalidation
does not bypass that guard.

| Rule | Statement |
| --- | --- |
| C8 | `invalidate <run> <identity>` atomically cancels the chosen active commit and every later active commit in journal order with **one** synchronized `invalidated` range record. The next resume runs those effects again; every earlier commit stays. Under the writer lock, validate the whole suffix before writing anything. Refuse `memo_busy` for another writer, `invalidate_not_committed` for a chosen identity without an active commit, and `invalidate_coordinator_committed` if the suffix contains any committed coordinator: a committed child run is never superseded (K8) |
| C9 | Each `committed` record keeps `depends_on`: the identities whose results its resolved input read, through names, arguments, results, loop state, join parameters, `case` bindings and the conditions that chose a value; an effect inside a branch does not depend on the branch's condition. `depends_on` is computed per value, not per field: a record, list or loop state carries the union of its parts' dependencies and a field or item taken from it keeps them all (§4.2.3). It is therefore a superset of the identities actually read and never omits one; in a serial `list/map-effect`, whose items pass through a loop state that also accumulates their results, each item depends on every earlier item. Evidence that one effect consumed another's output rests on C6 read digests, not on `depends_on` alone. Narrowing `depends_on` to the parts actually read is an entry condition of the release that scopes invalidation by C9. In the first release this is evidence, not the scope of an invalidation: a dependence through a file, where one effect writes a path that a later one reads, leaves no trace in values, and a shipped workflow has that shape (`workflows/library/verified_iteration_drain/drain.orc`). Narrowing an invalidation to dependents through values and declared files is a later release, entered when command boundaries declare the files they read and write, with the file-dependence fixture of §17 as its evidence |

The range's `from_commit` names the chosen commit's immutable byte offset in
`memo.jsonl`. On replay, inspect the complete prefix immediately before the
range record and cancel precisely the commits active in that prefix whose
offset is at or after the anchor. The record itself closes the range; later
retry commits are not canceled by it. Validate that the anchor names an active
commit and that its suffix contains no coordinator commit, or report
`memo_inconsistent`. Derive the chosen identity and affected attempts from
those records, without storing a second list or emitting per-effect records.

One complete range record reopens the preceding terminal and changes every
affected row's status to `invalidated`. A crash before it or during a torn
line cancels nothing; a surviving complete record cancels the entire suffix,
including after an acknowledgment is lost. Retrying the command may report
`invalidate_not_committed` because the operation already took effect, but the
run remains resumable with the whole suffix canceled. There is no partially
applied invalidation to repair and no batch-intent protocol.

The spike followed values only and reran one of two file-dependent effects,
mixing old and new results (gate report, §6); C8 is the last review's
rule. A changed program file that diverges several effects needs one
invalidation, at the first: the suffix covers the rest.

## 9. Effect Inputs, Performers, Coordinators And Requests

### 9.1 Inputs

An effect takes values. Any transportable value is admitted: scalars,
records, unions, lists, optionals and paths, nested to any depth.

| Value | How a command or provider receives it |
| --- | --- |
| A value in `:argv` | Preserve the present route's distinction between a literal surviving its actual materialization decision and a runtime value (§9.1.3). A literal is first rendered with `str`: literal `Bool` gives `True`/`False`; static string templates are substituted once. A runtime string is inserted verbatim, runtime `Bool` gives `true`/`false`, numbers use decimal text, and records/lists use `json.dumps` defaults with keys in value order. Neither route reparses an inserted runtime string |
| A certified adapter's inputs | One JSON object, fields in signature order, as the last argv token, as today. The document carries the declared inputs only, each projected to its declared type |
| An external tool's `:inputs` (§9.1.1) | One typed input document in JSON, written in the attempt's directory. Its path is the last argv token. The document is validated against the checked field types before launch |
| A value that is large, or that a person should be able to read | A materialized view (a later release). The effect receives the path of the view |
| A prompt fill | As the prompt calculus defines: the `defprompt` template with each fill rendered by its renderer, then the typed prompt inputs, each assigned a unique input label under the rule below and rendered by the default renderer |

Provider input labels prefer the existing typed-input name (a field access's
last field, or the retained canonical binding name for a name atom). Compute
all preferred labels before allocation and reserve them. In input order, keep
the first occurrence of each preferred label `p`; subsequent occurrences use
`p__N`, with a per-`p` counter starting at 2 and increasing past every
reserved label. Reserve each assigned label. Preserve every ordered input row,
including repeated expressions, and its renderer/value. Generated bindings use
their retained Renamer names before disambiguation; authored lookalikes are not
reclassified. The allocation is local to the provider and independent of
source location.

Every document an effect receives is serialized deterministically. Its
digest is part of the resolved input (§7.2). The document carries values;
it carries no run state and no path of the orchestrator's private
directories.

A file that carries data to an effect is a representation of a value. It is
never read back to decide what the workflow does next. The workflow decides
from values in the environment and from committed results.

An expression in an argument position is evaluated like any other. The author
does not have to find a name that happens to hold the same value.

### 9.1.1 Typed command input documents

At target 2.35 an external-tool `command-result` may combine `:argv` with
`:inputs ((field expression) ...)`. This reuses the certified-adapter pair
grammar: field names are distinct nonempty symbols and expressions are
ordinary expressions. The command's label still selects its external-tool
manifest binding, and the existing stable-command prefix rule still applies.
`:adapter` remains mutually exclusive with `:argv`; a certified binding does
not acquire the external-tool file protocol by using its name in argv mode.
No new manifest signature, invocation protocol, placeholder or environment
variable is introduced. The expression's checked static type is the field's
contract; type declarations already present in the program are not repeated.
Every transportable type from §9.1 is admitted, including nested unions and
lists. `:inputs ()` explicitly sends `{}`; omitting `:inputs` adds no document
or token. Preserve that presence distinction through compilation.

For `candidate: Candidate` and `trials: List[Trial]`, the argv form sends two
JSON argument strings:

```lisp
(command-result evaluate
  :argv ("python" "scripts/evaluate.py" candidate trials)
  :returns Evaluation)
```

Its file-input form, for a tool that accepts an input document, is:

```lisp
(command-result evaluate
  :argv ("python" "scripts/evaluate.py")
  :inputs ((candidate candidate) (trials trials))
  :returns Evaluation)
```

The latter launches the stable command followed by one path token, for
example `.orchestrate/runs/RUN_ID/effects/DIGEST/attempt-1/inputs.json`.
That file contains `{"candidate":{"a":1,"b":2},"trials":[]}` for those
values. Extra authored argv remains before the path; a tool requiring a
named option can end authored argv with its existing option name. There is
one delivery rule, not a configurable insertion position.

The closed command reuses its optional `document` field, an ordered array
of `[field, closed_value]` pairs. `argv` retains only the arguments after the
stable command. The selected configuration row's existing `kind` determines
document delivery: `external_tool` allows argv plus the file document;
`certified_adapter` retains empty argv plus its signature-ordered inline
JSON document. Existing argv-only invocations of either kind stay unchanged.
Absence versus `document: []` remains significant. P5 checks
external document keys and transportability, derives each field descriptor
from the checked expression and lexical signature, and validates every argv
and document value. Runtime uses those same derived descriptors; no second
type schema is authored or serialized. Existing certified signature/key
checks and optional-input omission remain unchanged. At 2.35 its typed inputs
also use recursive transport validation instead of the old scalar-only
projection restriction; its positional JSON protocol does not change.

Evaluate all operand expressions once in expanded structural source order,
including effects in argv or input fields, before validating this command's
resolved input. Within each list retain authored order. Keyword reordering
does not reorder the assembled argv or JSON keys; it can reorder operand
effects. For external documents, project each value to its checked type and
validate recursive shape, active union fields, finite numbers and path
constraints with the existing transport/contract owners. Malformed or
duplicate source pairs and nontransportable input types refuse at build with
`command_result_inputs_invalid`; a runtime value violation is
`effect_input_invalid`, with the field/value path and existing contract
violation code. Both point at the authored form. Runtime validation precedes
this command's `started` record and any launch. When re-resolving a committed
effect for reuse, a failed input contract instead reports
`effect_input_diverged` with that same field/path evidence, before mutation.

Serialize external documents as the existing canonical finite JSON encoding
(UTF-8, sorted object keys, compact separators, no trailing newline). Bind
the exact byte digest as the `document` resolved-input part, with the ordered
checked field contract; never hash the allocated attempt path as input.
The path is transport metadata, derived only after reserving the attempt;
otherwise a retry would change its own input identity. After exclusive
attempt allocation, publish `inputs.json` through the pinned run-root file
owner, rejecting an existing file, unsafe path or closure overlap before
launch. Pass its workspace-relative POSIX path, using the same external
run-root handling as R2. A publication failure fails the reserved attempt.
Memo hits neither read nor regenerate that file: values and byte digests are
recomputed in memory. Editing an old generated document cannot change the
workflow or authorize reuse. User path values remain paths; this protocol
does not read/hash their referents or turn them into closure entries.

This is distinct from the CLI `--input-file` (workflow parameter binding),
provider `input_file`/`asset_file` (prompt sources, with their existing bases),
prompt dependencies/document fills (file-content reads under C6), and a
certified adapter's inline JSON argument. None is renamed, rebased or silently
converted to the external command's generated document.

### 9.1.2 Artifact handoff within the admitted release

The parent plan's preservation rule applies to each consumer's actual
artifact contract. Ordinary typed result paths retain their declared root,
active-variant and `must_exist` checks before commit, and the same path value
passes through calls, loop state and later inputs. Their external files stay
where the author declared them; an attempt's `result.json` does not replace
them. `must_exist` does not promise newly written bytes, a version increment,
or `since_last_consume` freshness. Returning a value does not implicitly
publish a named public artifact (frontend specification, §16.2–17).

For a declared document consumer, preserve C6's immutable attempt read/render
snapshot, path/content evidence and changed-file refusal on resume. Retain
producer and consumer identities/attempts, typed result-field provenance and
the actual declared-read path/digest in the memo-derived evidence. The
checked contracts, stored results, resolved-input parts and C9 lineage are
the owners of those facts; a second mutable artifact ledger is unnecessary
for this handoff. C9 alone proves value dependence, not a file read, and no
declared dependency attests to all files an agent actually opened. C8 still
invalidates the entire later committed suffix for untracked file dependence.

The `std/improve` proposal and compact search nominees carry typed values;
the single-call comparison workflows additionally return `ReviewReport` or
`SelectionReport` paths with `must_exist`. Their sources author no public
registry or versioned-consume policy. A stronger first-release handoff fixture
is the admitted [watchdog](../../workflows/library/generic_run_watchdog/watchdog.orc):
probe produces `watch_bundle_path`, the provider reads it through required
prompt dependencies, and the publisher writes the final watchdog artifact.
Preserve the actual files, order, dependency freshness and once-only publish
on resume asserted by `test_watchdog_orc_both_branches_preserve_artifact_lineage`
and `test_watchdog_orc_resume_reuses_provider_and_publishes_once` in
[its owner tests](../../tests/test_workflow_lisp_generic_run_watchdog.py), and the
corresponding handoff/retry checks in
[verified-drain tests](../../tests/test_workflow_lisp_verified_iteration_drain.py).
Repeat an admitted producer-to-consumer handoff through public evaluated
run/resume; compilation alone is not this evidence. Preserve R12 for authored
argv substitutions in these sources rather than rewriting the fixture to
hide a parity gap.

Verified-drain has one accepted consumer-preservation exception: its shared
canonical source at target 2.15 gains the Prepare-selected history input
specified in [the drain design](verified_iteration_drain.md#accepted-extension-prepare-selected-history-input).
The public evaluated fixture copies that same revised source, changing only
the target to 2.35 and supplying the required manifests/closures. Both routes
use the existing `LedgerPath` for the additional `PrepareResult.ledger_input_path`;
Work and iteration-review read that captured input, while Record keeps
appending to `ledger_path`. Retry of Work retains the history selected by
Prepare; the target-design dependency remains fresh per attempt. This changes
the shared source, two prompts, history freshness and artifact inventory in
both routes. It adds no runtime history selection, new effect or fork.

Preserve the original source/oracles and receipts as historical evidence;
compare both routes over the revised common source rather than demanding
unchanged historical prompts or a 19-file-only inventory. Continue→done must
retain all 19 original files plus the two distinct history inputs, with exact
path/byte/digest assertions, the existing roles/results/counts and no committed
redispatch. The drain design owns publication, retention and the bounded
Prepare-commit invalidation conditions. C6/C7, C8 and command-local C4 remain
unchanged; legacy acquires no evaluated invalidation or completed-resume
validation policy. Implementation and public preservation evidence remain
obligations of Tasks 13D/14 in the [Phase 3 plan](../plans/2026-10-02-workflow-lisp-evaluated-execution-phase-3-plan.md#task-13d-canonical-verified-drain-history-input).

No generic `artifacts`/`publishes`/`consumes` metadata is added to the closed
program or V9 by this clarification. Before migrating a consumer with a
stronger named-publication, version/freshness or specialized effect contract,
carry and test that contract through its owning effect. Consumer-conditioned
Phase 4a closes such additional needs; it cannot defer the admitted result,
declared-read or handoff obligations above, or replace artifact evidence with
a claim that memoized values already provide it.

### 9.1.3 Closed command templates and transport scope

R12 preserves successful legacy argv bytes, including the literal/runtime
Bool distinction. It does not normalize legacy spelling or repair old targets.
The selected authored placeholders are `${inputs.*}` and `${loop.index}`;
`loop.total` is only a legacy scope discriminator. Runtime strings, documents,
environments and prompts do not acquire recursive interpolation.

#### Classification at the actual materialization boundary

A scalar is a template only if the existing command renderer receives a
literal after the actual route's binding decisions. Resolving an expression
to a literal is insufficient: materialization first turns that result into a
runtime reference. Preserve `str` for a surviving literal and tokenize those
bytes; render materialized/runtime values using the shared substitution
coercion. Do not add constant folding. The public target-2.34 oracle is:

```lisp
:argv ("python" "probe.py" true (let* ((x true)) x)
       (if true true false) (let* ((s "${inputs.n}")) s))
; n = 7: ["True", "True", "true", "7"]
```

The `if` becomes `WccSelect`, is bound by ANF, and the WCC binding owner emits
a projection even when its resolver selects a literal. The two `let*` aliases
in that example do not materialize. Nor does every hoisted binding imply a
runtime value. Extract the decision, with its precedence, from
`wcc/defunctionalize._defunctionalize_body`: expansion-owned pure projection
(except an existing direct reference), run-ref demand's resolver override,
provider-context whole-value projection, request-input alias/projection, then
the `IfExpr` projection and ordinary resolved alias. Reuse
`_wcc_continuation_binding_demands`; a command-only free-name approximation
would miss a second consumer that forces materialization.

The surface binding owner is `control_dispatch._normalize_let_binding`:
its inline-binding predicate preserves the resolved alias; otherwise
`_lower_effectful_binding_expr` chooses match, pure projection or expression
emission. The same expression can therefore require a different decision
when processed by a different owner. A native/private boundary terminates
literal propagation: its bound parameters are runtime values. Inline
argument aliases retain the selected binding facts, including specialization
and imported typed bodies. Captures evaluate actual arguments once.

Put these small pure decisions in
`lowering/command_transport_decisions.py` and make both legacy owners call
them. Inputs are existing typed expressions/binding facts, type environments,
expansion ownership and continuation demands; outputs describe alias versus
materialized value, not emitted steps or reference strings. A binding fact
retains its descriptor and static literal/structural alias, or that it is a
materialized root with its available typed projections. It is a compiler-local
symbol table over existing bindings, not another AST, runtime environment or
serialized namespace. It needs no Python-id/source-span lookup table.

Use the `typed_body` already retained by `_build_procedure`/`_build_workflow`,
the existing condition retained-input facilities, and the normalized WCC
bindings. `_prebind_effect_argument_matches` retains its selection in a join;
ANF retains a selection's bound `WccSelect`. Follow those bindings with the
shared materialization decision before assembling each command plan. No
`argv_origins` field, parser change, source-expression copy, legacy snapshot
schema change or new semantic-hygiene path is selected. If a future concrete
counterexample loses a required fact before these owners, return that first
loss to Design; it is not permission to add an anticipatory shadow AST.

`closed/command_templates.py` performs this finite analysis and attaches only
the resulting `Value`/`Template` plans to `WccPerform.operation_payload` after
ordinary ANF, before `closed/effects.translate_perform`. The original argv
and document operands remain the only evaluated source operands. A plan's
slots refer to those bindings and typed scope roots. ANF retains payloads
when revisited; it never interprets a template or creates effects for it.

#### Projected static facts in K6

After the actual materialization decision, every retained compound actual,
whether partly runtime or wholly constant, keeps its original residual
parameter and operand. Do not reconstruct a constructor from a Mapping or
promote a new Record/Union actual to a complete value binding. Existing scalar
`LiteralExpr` promotion and historical complete bindings, including bound
reference values, retain their semantics. Native/private or materialized
boundaries still terminate literal propagation.

For an inline edge with bottom-up `command_fact_demand`, retain the already
selected literal leaves and union tag of its compound facts in K6. Walk the
remaining real formals after scalar promotion, paired to actuals by retained
argument indices. Opaque, unknown and runtime leaves emit no rows; do not fold
expressions, resolve an old Name/FieldAccess again, or inspect runtime elements
of List/Map/Optional. Keep all retained literal leaves under that callable
demand, without adding field liveness analysis. A forwarding inline wrapper
uses its own formal/index; it does not copy the child's body or K6 into K10.
Runtime captures retain their existing propagation boundary.

The exact additional K6 wire is:

```text
ProjectedSelector = ["projection", formal, residual_index, Projection]
Projection = {"path": [field, ...]}
           | {"path": [field, ...], "shared": [D_or_null, ...]}
ProjectedRow = [ProjectedSelector, D, {"k":"lit", "v":literal, "type":D}]
```

`formal` is the existing declared string or `["local", n]` of that real
parameter. `residual_index` is a nonnegative integer, excluding Bool, indexing
`K[8].params` after scalar promotions and excluding the K7 capture prefix.
`path` has one or more nonempty field names. All `D` values are runtime
descriptors in the key domain, not compile-time reference signatures.
`shared` uses the existing closed-field per-segment relation: its length equals
`path`, entries are null or projected descriptors, and at least one is non-null.
Omit an all-null array; no redundant shared destination is allowed for a record
or variant-case view. There are no caller names, fictitious leaf formals or
runtime/capture selectors in this row.

For example, a retained Choice parameter `value` at residual position 0 can
carry this row while its runtime field `n` has no static row:

```json
[["projection","value",0,{"path":["label"]}],
 {"kind":"primitive","name":"String"},
 {"k":"lit","v":"before","type":{"kind":"primitive","name":"String"}}]
```

Changing the retained label to `after` changes K6. Its known union tag has a
separate `path:["variant"]` row with the existing discriminant descriptor and
enum literal. K8 and the original compound argument remain unchanged.

Complete K6 rows come first in their existing local-index/string-name order.
Projected rows follow, ordered by `(residual_index, existing_formal_order,
tuple(path))`; shared destinations, types and values never break a tie. A
formal maps to exactly one residual position and a position to exactly one
formal. Distinct paths of one formal are allowed; duplicate logical paths,
including identical rows or rows with different shared destinations, and a
literal leaf plus its descendant are invalid. The producer may coalesce
identical discoveries, but contradictory discoveries fail integrity. A
projected formal cannot also be completely bound in K6, bound in K4/K5 or
converted to a direct K7 capture. Type-variable names do not become value
formals. This grammar/order is exclusive to K6: K3/K4/K5, reference-formal
paths and `PRef.bound` retain ordinary selectors. Without projections, K6
bytes do not change.

Validate each path from the descriptor `K[8].params[residual_index]` with the
existing `_shared_field_type(..., key_domain=True)`, `_key_field_type`, nominal
catalog and local C_K/F relation. At a union prefix `p`, a valid discriminant row of the same
root at `p+["variant"]` selects the existing `variant_case` descriptor with
exactly that member's catalog fields for payload traversal; shared must be
null in that segment. The discriminant row itself is checked from the full
union, not narrowed by itself. Its enum, allowed values and literal must
agree; dependencies are strictly shorter prefixes and may be validated by
depth independently of wire order. A retained union tag always emits its row,
even for runtime-only payload or an empty variant.

Without that row, a full union allows only a uniform field or a checked shared
destination. Use the selected specialization's existing
`SharedUnionFieldCapability`/`shared_field_types`, not the first variant's
type. A residual variant-case descriptor already holds its proof: traverse
payload fields without adding a discriminant. Nested records/unions repeat
these rules. This reduction checks a static key fact; it does not narrow the
body parameter or authorize a new field access. The original argv access
keeps its own proof, shared destination and type, even when the key leaf has
a narrower variant type.

After validating row shape, K8, catalog and S, the checker validates roots,
positions, exclusions, every segment and shared destination, tag/case and
final type. `D` and `ClosedValue.type` must equal that final type. Reuse closed
literal validation/inference, existing literal coercion and key-type checks;
only `k=lit` is admitted here. Nominals, applied identities, generated markers
and every shared target must agree with the catalog. This is typed artifact
consistency, not source authentication or a runtime equality assertion.
Executing the program does not evaluate a key projection.

Creation and memo consume one transient `RetainedExpressionFact`, placed next
to `RUNTIME_REFERENCE` in `command_transport_decisions.py`. It replaces a
retained raw record/union constructor in the closed symbol table; it is not a
parallel source cache and does not implement Mapping. Its finite content is
`form` (`record`, `union`, `opaque`), the Bool `projection_candidate` from the
existing `is_pure_projection_expr`, ordered selected field facts and a union
tag Literal where applicable. An opaque leaf has no fields/tag and keeps its
own candidate bit. It holds no source Expr, Name/FieldAccess, textual type name,
frame, source position, operand identity or producer. Literal, runtime
sentinel, existing typed references, Mapping and Unknown representations stay
distinct; Unknown is None only when the creating resolver obtained None.

The existing `_resolve_inline_expr_value` and `_resolve_inline_let_bindings`
create this fact through a closed-only option, off by default and propagated
through recursion while the real Let/If locals exist. A RecordExpr result
already selected as Mapping stays Mapping; only a constructor otherwise
retained as Expr becomes the fact. A residual nonliteral Expr leaf becomes
opaque with its exact candidate category, without evaluation or retained AST.
Reading an existing fact or field returns the frozen fact/leaf, without a
later relookup. Install the candidate only when the actual binding/ANF/edge
decision retains alias; otherwise discard it for the existing typed runtime
binding fact. Original WCC operands are still the only evaluated computation.

Enable that option at closed initial bindings, `CommandScopeContext.bind`,
`compile_time_bind`, `prepare_call`, and the existing `facts.closed_program`
creators in `command_control_summary`: `_binding_control_fact`,
`_effectful_binding_control_fact`, `_let_control_fact`, `_procedure_control_fact`
inline actuals and their inline-let field shortcuts. `capture_source` copies
the real retained binding fact; `narrow` preserves static leaves and updates
only its runtime shape/proof. The pure-projection candidate uses the fact's
bit, including each subconstructor/opaque leaf. Its non-direct/non-Mapping
category preserves the old Expr distinction for provider whole-value demand;
outputs/nested-local shortcuts that required Mapping still do not cross it.
Materialization discards the candidate and uses the original Expr for
outputs/types, so no legacy emitter receives the fact. Use a local import in
`values.py`; no new module, registry or expression walker is selected.

Preparation normalizes that same fact as
`["retained-expression", form, projection_candidate, tag_or_null, normalized_fields]`
in typed field order before the existing memo lookup. Preserve the other
Literal/runtime/Mapping/Unknown alternatives. No Name/FieldAccess spelling or
source-expression identity is added to actual memo inputs, and constructors
are not resolved under later caller locals. A creator's runtime input differs
from Literal(9) under a later shadow=9, while renaming/aliasing that runtime
operand preserves the input. An escaped raw Name/FieldAccess is a missing
creation ingress to repair, not permission for a universal runtime fallback or
new admission refusal. No-demand reuse may still omit the actuals component.

The request carries `binding_facts["static_projections"]` with the real formal,
final residual position, path, selected literal and original TypeRefs/owners.
Key construction consumes it even without a specialization, projects both row
type and literal type into the same D, and retains compound signature,
arguments and indices. Projections alone require no second elaboration; scalar
promotion retains its existing re-preparation. Complete K6 and the unchanged
pure conflict guard precede interning/publication, without advancing another
elaboration ahead of memo lookup. A PRef invocation uses its prepared request;
its shared binding target/bound receives no new application facts. Projection
indices in a target stay target-residual indices, never enclosing captures.

The existing `CallableRequest` also holds an optional, default-empty tuple of
projection type obligations `(residual_formal, TypeRef, typed_owner)`, coalesced
and ordered by formal/canonical key descriptor. It contains no producers or
second value table. Before definition emission, register types used only by
projections, including discriminants/shared targets, through `Builder.desc`
with the current residual parameter's freshly instantiated producers. Prepared
comparison uses each original owner's key type projection, not Python identity;
key construction/memo lookup does not call `desc` or register descriptors.

The existing `_run_ref_type_refs` walker visits a DiscriminantTypeRef's
`owner_union or applied_union`, in the same preference as canonical identity,
using its existing Union recursion, phantom arguments, seen set and deduplication.
Construct the tag discriminant from the real typed union with its retained
owner; do not recover types from names or reopen source. This lets existing
finalization reconstruct registered descriptors with the current residual
argument's producers and re-register the catalog. K6 already contains S and
is not patched after naming. Only rows, their name/digest contribution and
ordinary catalog descriptors persist; creation facts, requests, owners, type
obligations and memo do not. No runtime, source AST, legacy/capsule codec or
generic serialization change is selected.

#### Exact scope selection, including composition

The substitution scope is separate from lexical locals:

| Edge | Input roots | Loop index / materialization |
| --- | --- | --- |
| Entry or native workflow | Its declared parameters under native boundary projection | Reset to absent; parameters runtime |
| Ordinary let/branch/join | Inherit; shadowing does not replace native roots | Inherit |
| Inline procedure | Inherit; actual binding facts propagate | Inherit; own loop shadows only in its body |
| Selected private procedure edge | Its own parameter roots and source names | Reset to absent; parameters runtime |
| Selected composition case arm | Ordered lexical roots in the arm certificate below | Reset to absent; roots runtime; preserve composition origin for descendant selection |
| Loop body / exit | Same roots | Bind zero-based index / restore enclosing index |

Selection follows the actual owner, not source nesting. The default CLI uses
WCC. `_lower_wcc_procedure_call` processes an inline body through WCC without
the surface iteration override; a native/private child starts WCC again.
`_defunctionalize_case` performs guarded hoisting, not a composition namespace
reset. `_defunctionalize_rec_join` hands its body through
`_frontend_expr_from_wcc_loop_body` to the surface loop emitter. Within that
body, let bindings use `_normalize_let_binding`; direct loop-tail if/match
uses `_lower_loop_body_expr` and its guarded loop cases. A value-bound match
or a surface-inline procedure body can reach `_control_lower_match_expr_impl`.
Its selected arms, unlike guarded WCC/loop cases, may acquire composition
boundaries. Explicit schema1 enters the surface owners directly; it is a
separate oracle, not the default CLI route. The analysis follows these owner
transitions over the existing WCC/typed nodes; no route selector is persisted
in the program/key and no defunctionalizer or emitter runs in `closed`.

Producer selection is retained configuration, including for compiled imports.
`Stage3CompileResult.lowering_schema_version` and `FrontendBuildManifest`
already distinguish schema1 from schema2; `TypedProgram` currently drops it.
At both existing `typed_program_from_graph` calls, in
`compiler.py::compile_stage3_module` and `_compile_stage3_graph`, pass
`lowering_schema_for_route(normalized_lowering_route)` into a required
compiler-only `TypedProgram.producer_lowering_schema`: a strict integer 1 or
2, not Bool or an unknown/default state. The first loss is those constructor
calls, not parsing, snapshot import or artifact decoding. Source attachment,
entry selection and dataclass replacements preserve the fact. Default 2.35
typed construction selects 2 as its predecessor transport schema. Schema2 uses WCC
owner rules; schema1 uses surface owner rules, with the same shared decisions.
Preserve each imported definition's owning snapshot through specialization;
equal source bytes do not justify substituting the caller's schema. The scalar
is neither a closed field nor another key component: only the effective
categorical decisions below survive closure.

The admitted ingress inventory fixes where this fact comes from:

| Ingress | Existing authority and transfer |
| --- | --- |
| Source through `compile_stage3_module` or `compile_stage3_entrypoint`; typed-only `compile_typed_program` | Both Stage3 snapshot construction sites already have the normalized route. `compile_typed_program` uses that same entrypoint with `lowering_route=None`; it does not construct another snapshot. Attach the required schema before returning or attaching the snapshot |
| Explicit `imported_programs` or a source-produced bundle's `typed_program` | `_require_explicit_source_snapshots` already requires the complete original producer snapshot. Its required schema and retained configuration travel with that snapshot; entry selection, imported-program maps and `_attach_typed_programs_to_source_bundles` preserve the owner |
| File-based imported-bundle manifest | `build.py::_iter_compiled_import_entries` requires `kind: compiled` and a `.orc` path. `_load_imported_workflow_bundle_manifest` compiles it through `_build_frontend_bundle_in_memory` with the supplied lowering route. This is a source constructor path, not a historical snapshot decoder |
| Older decoded bundle explicitly paired with its original snapshot | `LoadedWorkflowBundle.__getstate__` omits `typed_program`. The existing complete, selected, structurally matching original snapshot is supplied at pairing (§4.2.1); it carries the schema with its bodies/configuration. An old bundle does not need to acquire a new persisted field, reopen its source or locate a build directory |
| Valid bundle capsule plus the matching original snapshot | The existing capsule decoder verifies its envelope and bundle catalog. The paired original snapshot supplies each producer's schema and retained configuration, under the same §4.2.1 structural-pairing contract. The capsule's global schema2 does not establish the schema of each imported producer |

A valid schema2 capsule can contain a schema1 child imported by its schema2
parent. Keep the child's schema1 on its original snapshot and the parent's
schema2 on its own snapshot after decode and pairing. The global capsule
schema comes from the controller's construction context; it is not per-owner
authority. Capsule encoding/decoding, `LoadedWorkflowBundle`, its pickle state
and `_typed_program_matches_bundle` retain their existing contracts. No bundle
schema field, decoder transfer or capsule/snapshot schema comparison is added.
Pairing checks structural consistency, not historical body authenticity (§4.2.1).

These cover the existing supported compiler entrypoints. `TypedProgram` has
no persisted snapshot format or historical snapshot reader; its explicit
in-memory original is not reconstructed from an old pickle. Consequently no
origin-recovery API, optional producer-manifest input, checkpoint scan,
dual-schema analysis or route-neutral mode is selected. Missing this required
fact on a compiler-produced snapshot is a producer invariant defect, not a
new `compiled_workflow_source_required` branch. That diagnostic keeps its
existing missing/incomplete/mismatched original-snapshot meaning. Existing
closed-program artifacts keep the annotation compatibility rules below.
Neither source deletion nor relocation introduces a new refusal or an
external metadata lookup; never read `frontend_build_root/manifest.json`
to recover producer configuration.

The concrete same-source producer witness has two successful runs: schema2
emits `["PROCEDURE", "WORKFLOW"]`, schema1 emits
`["PROCEDURE", "PROCEDURE"]`. Retaining the scalar at construction preserves
this distinction without persisting a new route selector. Test both Stage3
construction paths, direct typed imports, manifest source construction and
restored capsule pairing, including conflicting caller configuration. Delete
source and the original build directory, relocate the supplied artifacts and
read back/run using the retained snapshots; no supplied external manifest is
required. Include the positive mixed-catalog case (schema1 child, schema2
parent, schema2 capsule) paired with each original snapshot; preserve each
owner's transport decisions. Keep the existing missing/incompatible-snapshot
negative controls without changing valid capsule admission.

For a surface procedure call, reuse the full
`_schema1_iteration_private_override_applies` predicate: resolved inline mode,
iteration present, outside composition, no procedure-owned `LoopRecurExpr`,
and both private boundary/body eligibility checks. A source `if`/`match` or
loop alone does not select a private or composition edge. Imports preserve
the owning definition's typed/configuration context.

The composition selector is the following pure **top-level control summary**.
It shares decision functions with the named legacy owners; it does not emit
steps or retain a control graph. `S` is one boolean, composed by OR for a
sequence. Typed alias/materialization facts are threaded in lexical order.

| Actual owner/decision | Summary at the caller's top level |
| --- | --- |
| `_lower_conditional_branch_expr` / let-tail direct-output shortcut succeeds for every required projected result leaf | False; the result is references, with no emitted control |
| Surface inline let binding | False; update its alias facts |
| Selected pure/structural projection, command/provider/native call or projection anchor | False; update the materialized result facts; these emit no top-level if/match/repeat |
| Surface non-inline let binding followed by its body | OR of selected binding emission and selected tail; do not count syntax bypassed by either shortcut |
| Surface inline call | Its specialized body's summary under actual aliases and the selected scope; a selected private call instead contributes False |
| Surface `_control_lower_if_expr_impl`, `_control_lower_match_expr_impl`, `_emit_repeat_until_from_emitter_input` reached after the shortcuts | True: respectively a top-level if, match or repeat; nested arm contents are not separately counted in this result |
| Reached `phase_flow._phase_stdlib_lower_produce_one_of_impl`, `_phase_stdlib_lower_resume_or_start_impl`, or `phase_resource._phase_stdlib_lower_finalize_selected_item_impl` | True: these owners emit a top-level match even though the source intrinsic is not a match; this classification does not broaden their admission |
| Direct WCC case / loop-tail guarded case | No composition certificate at this arm; retain its ordinary child analysis, and apply the surface rule only at a real surface-value-match owner below it |

The direct-output test shares the leaf/reference-availability decision from
`core._inline_output_refs_for_expr`; it uses typed projection availability,
not fabricated `root.steps.*` names. Pure-projection selection shares
`_pure_projection_binding_candidate`; the command implementing such a
projection contributes False even if its **data payload** contains an `if`.
Generated control counts only when its emitter actually contributes a
first-level control statement; use the explicit intrinsic rows above, not a
recursive scan of payload JSON. `run-provider-phase` and resource transition
are leaf emitters for this summary; their surrounding admitted WCC expansion
is analyzed normally. The loop seed/current-state/sparse-projection helpers
can also emit if/match, but are under an already-True loop emission. This
accounts for the current control-emitting owners; a new operation requires
an explicit summary rule and cannot silently default to False.

At `_control_lower_match_expr_impl`, select a reset for an arm exactly when
its selected pre-hoist branch summary is True. This is equivalent to
`fragment_requires_helper_boundary` by induction over the table: direct refs
and leaf/projection emitters add none of its three keys; sequence concatenates;
inline calls expose their selected body; private calls hide it; each reached
structured emitter contributes one such key. The legacy fragment test stays
an independent verification oracle while extraction is tested. No successful
case is excluded because it arose through WCC's surface bridge.

There is a public default-CLI witness: target 2.32, a loop let-binding of an
effectful match whose A arm contains an if and inline helper calls, followed
by `done` of a constant result. It executes a generated composition child and
emits `["PROCEDURE", "WORKFLOW"]`. Returning the bound match value instead
refuses during legacy result projection; adding a nested owned loop also
refuses in WCC conversion. Those failures do not prove unreachability. The
successful witness and the prior WCC guarded-hoist witness exercise distinct
owners. At 2.35 the selected control forms remain admitted even when legacy
refused; the summary is defined on their typed nodes and never imports the
legacy effectful-control-value refusal or requires a flat terminal/step id.

The first required new datum is the selected local arm reset and its ordered
roots. Construct it at the shared match-arm selection before losing that
arm correspondence, retaining it as `WccCaseArm.command_scope`, a tuple of
`(source_formal, WccValue)` roots; absence means inheritance, an empty tuple
means an empty reset. Preserve it on the existing arm through any ANF copying.
`closed/build.tail` emits the optional exact arm field:

```text
"command_scope": [[source_formal, closed_root], ...]
```

Roots are exactly `_helper_capture_names`' lexical free roots, ordered by the
current ordered typed local-binding table. Sequential lets/shadowing and arm
binders use that owner's rules. A placeholder string is not a lexical free
name and never adds a root to rescue a missing input. Retain references to
the existing bindings, not a helper definition or new call. For a
`VariantCaseTypeRef` root, use `_helper_capture_boundary_type`'s field-only
record projection: the closed root keeps its checked `variant_case` type;
a pure projection view derives rows from those payload fields without a new
nominal record, discriminant input or source-derived generated record name.

The checker enters the arm's ordinary variant binder first, validates every
root as an in-scope pure value in that environment, and derives the root
projection table. It then resets its command-scope checking context only for
that arm. The evaluator needs no dynamic namespace/reset frame: slots and
ordinary captures already name the values. Root certificate operands are
checked/traversed but are not independently evaluated as effects. Native
children reset composition origin; inline descendants retain it, including
inside their own loops. Exiting the arm restores the prior scope.

#### Closed templates, whole roots and inactive union projection

Every newly compiled command has `argv_transport`, parallel to its tail-only
`argv`. Certified inline-document commands have `[]`; documents themselves
are never templates. Exact rows and parts are:

```text
{"kind": "value"}
{"kind": "template", "parts": [part, ...]}

part = {"kind": "text", "text": string}
     | {"kind": "slot", "name": name, "path": [string, ...],
        "filters": [string, ...], "value": closed_value}
     | {"kind": "missing", "expression": string}
name = ["input", source_formal, native_wire_name] | ["loop-index"]
```

An input slot's `value` is the **whole typed native root**, not a projected
leaf. `native_wire_name` selects exactly one row derived for `source_formal`
from that root's descriptor. Derive row path, leaf contract and activity from
`derive_workflow_boundary_fields`/`compiled_boundary_rows` and the descriptor;
never split `pair__x` or serialize a guessed field path. Extract the pure
row-selection/activity operation into `workflow/type_descriptor.py`. Walking
its derived path follows the actual discriminant at every union: a field
absent in the active variant yields Missing before suffix/filter application.
Do not assume input-mode `compiled_boundary_rows` supplies output-only
`active_variants`, use an unconditional `field` on a union, or erase the root
to `Value`. A variant-case root uses the field-only view above.

For `choice: Choice = A(x Int) | B`, the closed root parameter `p` has the full
Choice descriptor. A slot is:

```text
{"kind":"slot", "name":["input","choice","choice__x"],
 "path":[], "filters":[], "value":{"k":"name","n":"p"}}
```

With `p` as parameter zero, the native certificate is
`command_params: [["choice", 0]]`. In A(7),
the derived row selects `x` and renders `7`; in B it produces
`undefined_variables` at the reached command. The artifact is well-typed for
both values. An inline descendant captures `p: Choice` via
`["command-input", "choice"]`, reads that root in the same slot, and receives
the whole Choice as an ordinary argument. Read-back derives `choice__x` from
the checked Choice, rejects a different-root/leaf-Int capture or invented row,
and accepts B until resolution. The checker never requires a universal
`Choice.x` field.

`path` is only the dictionary suffix after selection of that row. Thus a
Value root `payload` can resolve `${inputs.payload.z}` by selecting its root
row and then dictionary key `z`. Missing keys, non-dictionary intermediates
and None are Missing. No list indexing, new general field operator on Value
or runtime namespace lookup is introduced. A statically impossible root/row
becomes a `missing` part, not an artifact-check failure for an unchosen arm.

Reuse/extract `VariableSubstitutor`'s pure tokenization, dictionary lookup,
filters and coercion: protect `$$`, recognize `${...}`, omit empty filter
segments, apply filters in order, insert once, then restore escaped dollars.
Preserve `$${`, `$$${`, default JSON spacing/ASCII escaping and `|json` compact
UTF-8/insertion-order bytes. Unknown filters stay checked strings and fail
only when reached. Missing/inactive/None/filter failures report
`undefined_variables` before started/dispatch; committed input re-resolution
uses `effect_input_diverged` with that cause. No flat state object is required.

A value row renders the evaluated argv value; a template retains that
operand's once-only evaluation, source order and dependencies but renders its
parts. Text parts are canonical: merge adjacent text, omit empty text; an
empty template is an empty argument. Parts have no `@`; their closed value
children use normal AST provenance. Slot/certificate operands contain no
perform or effectful call. Effects already belong to ANF bindings.

#### Captures, index and minimal contextual specialization

Capture whole roots using exactly `["command-input", source_formal]` and
`["command-loop-index"]`. Preserve their complete descriptors; index is
strict Int. Deduplicate by root in an interface, keep ordinary captures first,
then command routes in canonical order. Missing roots get no dummy capture.
Propagate demands through inline intermediates and resolved reference
forwarding; native/private/arm resets stop inherited roots and supply their
own. Root values may differ between calls sharing a body.

A native definition's optional `command_params` is
`[[source_formal, parameter_index], ...]` in native signature order, selecting
only demanded roots after capture conversion. Presence denotes the native
reset, including `[]` if only a missing-root/index demand reaches it; absence
on an inline definition means inheritance. Entry follows the same rule. The
checker validates unique names/indexes, root descriptors/projections and
actual alias/capture forwarding. It is a finite binding certificate, not
source-history authentication. Include it in that definition's residual
signature key object; no other signature object accepts it.

A demanded loop index adds optional `index: wire_name` to the existing loop
node. It is fresh and distinct from state/target names, bound as zero-based
Int only in `body`, with no dependencies. It is not in that loop's seed,
budget or exhaustion scope; an outer index still in scope is available there.
Continue rebinds it. No frame/site string changes, identity parsing, counter
effect or persisted loop context supplies this value.

The previous proposed three raw context bits are not part of the schema.
Use one optional tenth key component containing **contextual decision rows**:

```text
{"command_decisions": [row, ...]}
row = ["arg", command_ordinal, tail_argv_index, arg_choice]
    | ["arm", command_case_ordinal, variant, "reset"]
    | ["call", original_declaration_identity, occurrence, child_variant_digest]
arg_choice = ["value"] | ["template", [lookup_choice, ...]]
lookup_choice = ["missing"]
              | ["input", root_origin, native_wire_name]
              | ["loop-index", root_origin]
root_origin = ["native", source_formal]
            | ["capture", command_capture_route]
            | ["arm", command_case_ordinal, variant, source_formal]
            | ["loop", demanded_loop_ordinal]
```

This is a bounded vector of categorical choices, not a body hash, copied AST
or control graph. Arg rows contain no template text, filters, expressions or
root values. Arm rows contain no arm body/root expressions. The ordered local
inventory counts commands and command-bearing cases only: a case is counted
when an arm contains a command or a call with a command descendant.
Unrelated pure bindings/conditions are not counted. Calls use the existing
original-declaration/static-occurrence selector, ignoring calls to other
declarations. Rows use deterministic semantic traversal; no spans, names
allocated by lowering, or runtime values appear.

Include one arg row per tail argv operand, derived from its checked
`argv_transport`. Template lookup choices follow non-text parts in order;
text/filter/suffix spelling is ordinary body data. Root origins are inferred
from checked root certificates/capture forwarding, following pure aliases;
they are not another serialized origin map. Only index binders actually used
by command slots/captures receive demanded-loop ordinals. A mode-only
value/template bit would miss a template changing from a missing lookup to a
root, or switching between a native and arm-local root. Runtime A versus B
of the same Choice root changes neither lookup choice nor specialization. Even a context-invariant literal uses that categorical
row; it adds no specialization when contexts agree, and avoids another
source-only sensitivity certificate. Emit an arm row only for a present
`command_scope`; absence is the canonical inherited outcome. Include a call
row only if its child has command decisions or command root/index demands.
A child's `child_variant_digest` is SHA-256 of canonical JSON of exactly
`{"native": native_rows_or_null, "captures": capture_rows, "decisions": rows}`.
`native` is null for inheritance or ordered `[source_formal, parameter_index,
key_projected_root_descriptor]` rows (possibly empty) for its `command_params`;
`captures` is ordered `[command_route, key_projected_descriptor]` rows,
excluding ordinary capture routes. `decisions` is that child's vector. The
preimage excludes its ordinary body/captures/value bindings, configuration
and name.
Those already belong to the nine-component key/program digest. Do not expand
child rows into a caller. Omit the tenth component when the local inventory
is empty; no raw iteration/composition/route flag is recorded. Static inline
scalar actuals continue to use complete tagged literal value-binding rows;
retained compounds use the projected K6 rows above and keep their residual
operands. Both are in K6, not a second literal store. Entry keeps its declared
name; it has no tenth-key field, and its semantic command/arm data already
enters program digest.

A same-nine-components pair for the call dimension is an inline `outer(s,
flag)` that reads `${inputs.state_root}` itself and owns a loop in one arm,
calling `helper(s)` in the other. The owned loop prevents private promotion
of outer; its direct command fixes the same input capture interface in both
contexts. Outside versus inside a caller loop, the descendant helper can
inherit versus reset under the surface predicate. Only the child command
interface/decision digest differs. An additional inline wrapper with its own
loop and the same direct input demand requires a changed child digest even
when its immediate edge stays inline. These are admitted 2.35 key tests, not
claims that legacy executed the nested-loop specimens.

For the arm dimension, place the same producer-backed match/if body in that
non-promotable inline outer, reached as an ordinary WCC call versus through
the surface loop bridge: the nine-component parameter/capture interface can
be identical, while the match arm inherits versus has a composition reset.
The actual two route owners and successful surface/guarded witnesses above
establish the distinction; the same-declaration pair is a required typed
construction test. For the arg dimension, an expansion-owned pure alias
binding used by a command has WCC projection versus surface inline-alias
selection with identical typed binding and nine-component interface. A
shared materialization-rule test must exercise both owners; the public
`if`/`let` oracle separately fixes their non-interchangeability. An unrelated
pure binding or changing only a literal template's text in the declared body
changes none of these categorical decisions; the latter changes program digest
without requiring a K10 change. A retained literal of an actual instead
distinguishes K6 under the rules above.

This vector is sufficient because the original nine components supply all
complete literal substitutions, projected static literals of residual actuals,
root/capture interfaces and types; the remaining
context-sensitive choices are argument materialization and selected lookup
roots, local reset selection and descendants' command interfaces/choices. Compute children
bottom-up over the already finite closed call graph before interning. The
stored size is O(local argv/lookup decisions + command arms + relevant call edges)
per specialization, with one fixed-size digest per edge, not transitively
expanded bodies. P5 derives row outcomes and child interface digests from the
checked command/arm/callee certificates, validates selector uniqueness/order,
and checks the name from the complete key. It cannot authenticate source
history or infer that an otherwise valid decision inventory was once authored
elsewhere. Retain one body per complete key and the projected-body conflict
check; no new specialization differing only in raw ambient context is allowed.

#### Traversal, dependencies and artifact compatibility

The command child relation is all argv values, all slot values in argv/part
order, and all document values. A case arm additionally has its certificate
root values, checked in the arm binder scope before the body. Each occurrence
is traversed once. Document presence never hides argv. Implement this relation
in `closed/sites._effect_value_children`/`_ast_nodes` and independently in
`closed/check._effect_children` plus its case-arm walks; include it in
run-reference finalization, source-owner/demand/type/key walks and provenance
stripping. Generic JSON hashing does not replace AST traversal.

ANF owns original expanded keyword evaluation order. Slot reads reuse cached
immutable root values; union the original argv, slot and document dependencies,
including dependencies of a selected value, into resolved input. Digest final
argv bytes. Certificate-only checks add neither dispatch nor dependencies.
Replay/read-only resolution does not revalidate committed files on disk.
Templates, root certificates, contextual decisions and index binders are
semantic data; containers accept no `@`. Moving/formatting source cannot leave
nested provenance in the digest or advance effect counters. Task 6 owns this
joint traversal; Task 12 reuses it for document admission.

Keep `workflow-lisp/closed-program/1` and `table/1`. Earlier Phase 2 commands
without `argv_transport` remain valid compile-only artifacts. Readiness scans
all commands before new run authority and refuses absence as
`command_transport_required`, requesting explicit rebuild from the original
source/typed snapshot. Stored evaluated authority with absent annotation is
`memo_inconsistent`; never guess literal transport or repair it. Phase 2 made
no 2.35 runs to migrate; runtime representation/profile pins still apply.
An old reader may refuse new fields. Old-target serialization/admission and
requests stay unchanged; shared decision extraction must prove their parity.

### 9.2 Performers

A performer executes one class of effect. It receives the effect node of the
closed program, the resolved input, the result path and the workspace. It
returns a result or a failure. It reads no run state and writes none. A
coordinator (§9.3) is a performer with a ledger of its own.

| Class | First release | Performer built from | Notes |
| --- | --- | --- | --- |
| Command | Yes | `StepExecutor.execute_command` | Independent of the executor today |
| Provider, composed delivery, portable subset | Yes | `ProviderExecutor.prepare_invocation` and `execute`, with prompt assembly moved out of the executor | The prompt is assembled as the present route assembles it, with the differences of R2 and R3 only (spike iteration 2, B) |
| Workflow or procedure call | Yes | None. A call is evaluation | Activation frames (§6), no child executor or persisted flat-route call frame |
| Run reference, path mode | Yes | Reuse the run-ref runtime and ledger behind a changed caller adapter (K7) | The child run is a separate run in its own workspace |
| Run reference, bundle mode | Later | The same runtime; the capsule is the child's closed program, built by the parent's build | |
| Request for input | Later | New | `suspended`, then `committed` by the answer command (M6) |
| Resource transition | Later | `execute_transition` | Independent today. Its idempotency key stays |
| Materialized view | Later | The existing step function | Reads its value from the environment |
| Trial | Later | The trial runtime behind the coordinator protocol | Has the pair of commits today (K6) |
| Provider, phased delivery; supervision; peer group; adjudication | Later | The existing coordinators, each changed to expose the pair of commits (K6) | One effect, one identity, its own ledger |
| Provider, authored sequential native-session turns | Later | Existing session/turn transports with a bounded coordinator | The [queue design](workflow_lisp_provider_prompt_queue.md) requires qualified turn-prefix recovery; neither composed delivery nor K4's restart rule supplies it |

A program at the new target that uses a class marked later is refused at
build (§1.1). At older targets it runs as today.

### 9.3 Coordinators

A coordinator runs an effect that has a ledger of its own and a child that
the run must never start twice. Today each coordinator commits into the
run's state; the memo replaces that commit.

| Rule | Statement |
| --- | --- |
| K1 | A coordinator receives the effect node and the resolved input as values, keeps its ledger under the run root, and reads and writes no run state |
| K2 | The protocol has three calls. `prepare(node, resolved, identity, attempt)` runs the effect to the coordinator's pending commit and returns the value and a proof. The evaluator validates the value and appends `committed` with the proof. `settle(node, identity, proof)` makes the coordinator's final commit; the evaluator then appends `settled` |
| K3 | On a memo hit, `reconcile(node, resolved, identity, proof)` completes a pending final commit from the proof, and the evaluator appends `settled` (`by: reconcile`) when the memo lacks it |
| K4 | The memo's `committed` record lies between the coordinator's two commits. Killed after the pending commit, resume discards the pending attempt and starts one more child; killed after the memo's commit, resume starts none. A coordinator that makes its final commit before the memo's is a defect: killed between the two, the run cannot continue (spike iteration 2, D1) |
| K5 | The proof is the coordinator's settled result record and its artifacts, stored inline in the `committed` record. It is what `settle` and `reconcile` need, and nothing else |
| K6 | Which coordinators have the pair of commits today, and which must change, by the inventory of the execution facts, B.1, and the gate report, §7: run references reuse pending ledger record, final commit and reconcile call through the K7 adapter; trials (prepared and final parent settlement) need their own adapter; phased providers make one authoritative commit, supervision and peer groups finalize directly into parent state, adjudication's parent result is committed by the caller, and human input commits reply and result together into `state.json`. Each of these five must give that up and expose `prepare`, `settle` and `reconcile` before it enters a release |
| K7 | A run reference: its static configuration is built at build time, each input bound as the reference `inputs.<name>`; the name rule of the child's inputs is the reference rule, so no valid name is unsafe. The coordinator resolves the references against a parent state that holds only the resolved input values. The visit key is derived from the identity: parent run id the run root's name, execution frame `root`, no call frame, step id `root.<digest of the identity>`, visit count 1. The runtime's ledger, `run-ref-attempts.jsonl`, retains its wire contract; physical IO and child authority follow §9.3.1 |
| K8 | A committed coordinator effect is never superseded in the first release: no new visit key or attempt for an identity that committed through a coordinator, and no rollback of the child's workspace delta (§3) |
| K9 | Every coordinator in a release has evidence through the public run and resume entries: a compiled program killed from outside at each of its two gaps, resumed to the uninterrupted value, with no committed child started twice, and refused before any launch after a declared file changes |

For §1.2's repeated placements, each iteration instantiates the complete
activation identity (§6), hence a distinct K7 step id and visit with count 1,
even for identical inputs/configuration. A request or proof bound to one
activation cannot authorize another. A discarded attempt of the same visit
is replaced at the previous attempt ordinal plus one; a new visit starts
at ordinal 1. Each activation has its own child/workspace and memo
commit/settlement. These are applications of the existing protocol, with
public two-iteration execution, resume and both K4 gaps still required.

#### 9.3.1 Path child admission, authority and return

The evaluated adapter constructs the path request from checked `RunAuthority`, the reached evaluator node, resolved inputs and the actual memo attempt under the retained parent writer lock. A caller-controlled boolean/profile, child target or constructed dataclass is not permission. K1 excludes mutable run state: the child may read the parent's checked header/artifact/memo solely to verify launch authority; the synthetic state for input references still holds only resolved inputs.

The private `run_ref_path_child_request.v1` and mode1 remain unchanged. Only the checked evaluated adapter emits `run_ref_path_child_request.v2`: existing fields plus the exact object `parent_authority = {run_root, identity, attempt}`, with logical absolute parent root, exact evaluated identity and positive memo attempt ordinal. The launcher supplies the retained parent-root FD separately through an ephemeral private argument and `pass_fds`, never through durable bytes or digests. A v1 with that FD argument, or v2 without verifiable authority, refuses; mode1 never consumes it. New readers admit only these exact private shapes; older readers reject v2 without v1 fallback. The trust boundary remains runtime files/descriptors, not authentication between operating-system users.

Parent admission precedes launch; child admission repeats before full compile/dispatch. The child reads checked parent header/artifact and reduces its memo through that same FD, readonly without another writer lock. Exact evaluated profile, run-id and site config must match; there must be a pending `started` for this run-ref identity/attempt without incompatible commit/terminal. Derive precisely K7's visit. Validate the complete ledger and require its **current head**, `rows[-1]`, to be `stage="launched", status="in_progress"`, matching visit, allocated ledger ordinal, child run-id, materialized workspace/root/config and `child_launch_digest` of the entire request including `parent_authority`. A historical launched row followed by completion, discard or another ordinal is not authority. Memo and ledger ordinals are independent, linked by visit/request/child rather than numeric equality. Execution is serial with the parent writer lock retained; acknowledgment also compares the exact just-published head-row digest. A detected root swap, including after sync, cannot authorize launch.

The parent `WorkspaceFiles` may be retained in `RunRefRuntimeRequest` only in memory and is mandatory for evaluated callers. All ledger IO uses it: allocation/revalidation, advance/persistence, acknowledgment re-read, discard, finalize, recovery/reconcile/reuse, and child admission. Parent root, ledger path, event `effect_instance_root`, bindings and proof retain logical spellings only; evaluated `effect_instance_root` equals that parent root, with no trial scope. Factor a single bytes parser from `load_attempt_ledger`, shared with legacy path loading; absence means empty, but an existing empty/truncated/nonregular/malformed ledger still refuses. `WorkspaceFiles.read("run-ref-attempts.jsonl")` and `write_atomic` preserve regular/no-follow reads, canonical bytes, durability, transitions, counters and wire. No shadow ledger, parser or path reopening; retain the borrowed FD through all operations. Legacy callers without this in-memory access keep their path behavior.

An admitted child whose target requires evaluated execution uses Task 8's single ordinary in-memory `FrontendBuildRequest` preparation and common binder/publisher/runtime: clone root, requested entry, four manifests null, `boundary_admission_profile=None`, default lint, `lowering_route=None`, no debug, no flat builder/fake bundle/second publication build. WCC_M4 is already the ordinary default, not a separate evaluated choice to add to recipe8. Preserve legacy `TRANSPORTABLE_CHILD`/WCC_M4 compilation, normalized flat identity and shared `_execute_bundle` refusals. Ordinary public closed admission, including old imported modules that can distinguish boundary profiles, is the child admission; a graph requiring the legacy global transportable profile remains rejected. Check materialized source/compiler/config, exact transportable signature/refinements and E1 `empty` environment with empty real direct/transitive effect summary, regardless of the parent's admitted effects.

For a new path child, `workflow_file=program.path` relative to clone, recipe `source_roots=["."]`, requested entry, four manifests and `input_file=null`. Preserve the explicit JSON `input_overrides` after `resolve_run_ref_inputs` path-copy and before child binding/defaults; never fill omissions from bound inputs. Initial binding/publication and public child resume share this recipe. Resume resolves it under the clone and follows §8.4, using stored artifact after fresh comparisons; no snapshot promise. The child's direct public resume needs only its own authority, not a still-pending parent. Parent recovery nevertheless retains K4 discard/rerun before memo commit; invoking child resume is no replacement for that rule.

##### Private closed result and compile identity

A legacy child, even for an admitted request v2, returns unchanged `run_ref_path_child_result.v1`. An evaluated child returns `run_ref_path_child_result.v2` only for an admitted request v2. Its exact exterior keys are `schema_version`, `status`, `step_config_digest`, `target_workflow_name`, `child_run_id`, `workflow_outputs`, `path_compile`; status is `completed`, workflow name is checked `program.tree["entry"]`, and run-id/config match the request. `path_compile` has exactly the following five keys:

| Key | Checked v2 contract |
| --- | --- |
| `program_identity` | Exactly `{schema_version, compiler_runtime_identity, program_digest, digest}`; schema `run_ref_closed_program_identity.v1`; compiler identity computed at initial child admission equals static `compiler_runtime_identity_digest`; `program_digest=ClosedProgram.digest`; `digest=canonical_sha256` of the other three keys |
| `signature` | Existing `{inputs, return}`; rows in checked `tree.params` order, each `{name, required, type}`, required iff absent from `tree.defaults`; return `tree.result`. Keep complete recursive nominal descriptors, transportability and exact static refinement checks |
| `effect_facts` | Exactly `{direct: [], transitive: []}`; initial typed summary and checked `site_classes(program)` both empty, later artifact rederives empty sites. No fabricated flat `procedure_edges` |
| `diagnostics` | Array of real closed-build diagnostic rows using the existing row serializer/validator, possibly empty; no accepted flat-identity wrapper |
| `evidence` | Existing exact `run_ref_path_compile_evidence.v1` fields, all hashes recalculated from these facts and materialized/static source/revision/tree/config/compiler/environment; canonical final digest excludes its own `digest` |

Keep the two digest layers explicit:

```text
evidence.program_identity_digest == program_identity.digest
program_identity.program_digest == run.json.program_digest == ClosedProgram.digest
```

The identity-object digest is not the semantic program digest. Shared child/parent validators discriminate on the private result v2, reject unknown/mixed shapes, rederive signature/effect facts and check artifact representation/schema/target/entry. Recovery compares compiler identity to recorded static authority rather than the currently installed package. Real compile refusals retain `workflow_lisp_compile_diagnostics.v1/rejected`; later signature/environment refusals put facts/codes in `rejected_value` and omit the optional accepted flat `compile_diagnostics`, without widening public flat identity validation.

##### One readonly terminal/value proof

Initial settlement and `_validate_bound_authority` for finalize/recovery/reuse call the same readonly helper returning validated direct value, authority path and terminal digest. Derive child root only from ledger/request-bound `workspace/.orchestrate/runs/child_run_id`, open and retain its FD, and capture once the bytes of `run.json`, `closed_program.json`, `memo.jsonl`. Apply existing unique header/artifact/input loaders and memo reducer to those same bytes; no source/current-config/input-file reading, fresh build, resume, repair, prepare, dispatch or reconcile, and no Task 10 view dependency.

In order validate exact header/profile/schema/run-id/recipe/root; checked `ClosedProgram.from_artifact` with header digest/representation, bound inputs/input digest/pins; closed identity/signature/evidence and complete explicit child recipe/request; then strict memo. A new v2 child requires recipe and root, without historical-absence exceptions. Bind defaults plus request JSON overrides purely, without another path-copy/relocalization. Require `site_classes(program)=={}` and exactly one complete `terminal/completed` record with no other records, pending or unsettled effect. `evaluate_closed_program` with checked inputs and actual run-id must reach halt without effects; `coerce_evaluated_value` against checked `tree.result` must yield canonical equality of original terminal, coerced value and halt, preserving distinctions such as Bool versus Int. Committed results receive no new filesystem `must_exist` observation.

With `H(b) = "sha256:" + sha256(b).hexdigest()`, retain the existing proof/ledger field names with these evaluated meanings:

```text
child_terminal_state_digest = canonical_sha256({
  "domain": "run_ref_evaluated_child_terminal.v1",
  "header_sha256": H(header_bytes),
  "program_sha256": H(artifact_bytes),
  "memo_sha256": H(memo_bytes[:snapshot.complete_bytes])
})
paths.child_state = <child_run_root>/run.json
```

That exact path anchors all three fixed siblings, not an arbitrary manifest target or hash of header alone. Hash all original header/artifact bytes and exact complete memo prefix including newlines, never reserialized JSON or partial tail. Complete corruption refuses before a digest/proof or `child_completed` update; incomplete tail is ignored without repair. Private v2 plus checked child profile discriminate this semantics; legacy retains its `state.json` digest. An absent/altered `state.json` view has no evaluated authority.

V2 transports exactly `workflow_outputs={"__result__": direct_validated_JSON_value}`, for scalars and nested record/union/list/optional/map values alike. Parent requires this sole key, canonical equality with checked terminal/halt, and pure coercion against the static result-value descriptor. Preserve finite JSON, schema/refinements, normalized paths and recursively exact nominal identities; homonymous types from different modules do not become equal by deleting names. Do not call flat `extract_run_ref_value`, create `return__...` leaves or flatten tags. Preserve the same tree under existing envelope `value`, with existing `workspace_delta`/`accounting`; initial capture and later validation of delta/declared artifacts retain their separate E1 checks. `flatten_run_ref_result_artifacts` still projects that final envelope, with no proof/artifact wire change.

The run reference was shown this way, compiled from `.orc` source, with two
commands and a provider beside it (gate report, §5; spike iteration 3, E).
Spike iteration 4 tested the shipped `qa_placement_trial::compare` with
stand-in children/judges through both routes and 18 external kills. It is
bounded feasibility evidence for later trials, not first-release admission:
that iteration found a trial runtime `KeyError: 'cell'` after evaluation
starts and used a test-process repair to exercise the two commit gaps. The
Phase 0 integration correction selects the active attempt's ledger rows for
recovery and terminal validation, also excluding discarded preparations; the
regressions now exercise the production runtime without that patch. A kill
during judging still spends in-flight attempts and can change the decision.
The settlement adapter supplies synthetic parent state to an existing state
validator; this does not prove independent validation of memo commit authority.

Before trials or bundle mode enter, evidence must retain that recovery coverage
and establish an explicit interrupted-judge budget policy, settlement against
the actual memo commit/proof, distinct per-arm input bindings, and location-independent
child capsules built by the parent's compiler. A trial's sealed-label salt
may remain in its own durable ledger; K5's proof must bind the ledger authority
needed for replay, rather than redraw it. Phased delivery still needs its own
adapter: treating it as an ordinary composed call, as the spike did, proves
no parity and must be refused at admission. None of this changes C3's
diagnostic-only interpreter upgrade rule or K8's no-supersession rule.

Authored native-session turns are another later class. Their
[recovery contract](workflow_lisp_provider_prompt_queue.md#recovery-contract)
retains completed turn progress before the parent result commits. K4's
discard-and-restart rule does not provide that behavior: admission requires
a reviewed, evidenced refinement for this class, including the binding of
turn progress across attempts and the final K2–K5 settlement gaps. This
prerequisite changes neither K4 for the first release nor the admission of
any existing class.

### 9.4 The request contract

A request is what a provider or a command receives. Each field has one
value, given by a rule. A field not listed here is equal on both routes.

| Rule | Field | Value |
| --- | --- | --- |
| R1 | `provider.context` | Empty. A request carries no run state: no run id, no timestamp, no run root, no inputs, no steps. A provider template that names a run variable fails the attempt as a missing placeholder does today. The run's identity reaches a program only as the `RunCtx` value (X1) |
| R2 | `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, in the environment of a provider and of a command | The attempt's own result path (§8.2), relative to the workspace, as the present route gives its path |
| R3 | The prompt's `- path:` line, in the output contract block | The same path as R2. Nothing else in the prompt differs from the present route's assembly |
| R4 | `provider.prompt_content` | Assembled through the existing composition pipeline ([Providers](../../specs/providers.md)): form the tagged prompt extern source or rendered `defprompt` base; apply prompt dependencies to that base at their declared position (`doc` fills use fixed `prepend`); append the separate typed prompt-input block for extern-backed calls; append the output contract through the runtime's existing renderer. `defprompt` text/value/path fills are already rendered in its base and do not add a second typed-input block. Prompt bytes differ only as R3 specifies |
| R5 | `ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY`, in the provider's environment overlay | `sha256:` and the digest of the identity's canonical text. The same across attempts and resumes, present inside call frames as well; the present route sends none inside a call frame |
| R6 | `provider.cwd` | The workspace, named. The present route inherits the orchestrator's working directory |
| R7 | `provider_call_policy` and `timeout_sec` | The effect node's policy: `model`, `effort`, `timeout_sec` |
| R8 | `params`, `session_request`, `provider_session_dir`, `provider_session_identity`, `secrets` | The parameters the effect node declares; none of the others in the first release (§1.1) |
| R9 | `command.command` | The stable command tokens, the interpreter replaced by its resolved path (C3), then the rendered argv (§9.1); append a certified adapter's inline input document, or an external tool's generated input-document path when `:inputs` is present (§9.1.1) |
| R10 | `command.env` | R2 and `PYTHONDONTWRITEBYTECODE=1` (C4) |
| R11 | Generated helper commands | None. The present route runs inline Python steps that write managed write roots under `.orchestrate/workflow_lisp/`; the model has no write roots and no call frames, so nothing writes them |
| R12 | A value in a command argument | Rendered by §§9.1/9.1.3 with checked static-template/value classification and explicit scope captures; preserve successful legacy bytes, including literal `True`/`False` versus substituted `true`/`false`, single-pass runtime strings and selected native/private scope resets |

P3 preserves a prompt extern as `source_kind` (`asset_file` or `input_file`)
and its exact path with the present source's lookup semantics. An input file
must not be converted into an asset or rebased to the entry module. A
`defprompt` carries its checked template/slot structure and fills, including
document slots: each document fill retains its document assembly/reference
and content dependencies instead of requiring a scalar renderer. Runtime
assembly and C6 bind all files actually read. The closed form must use the
existing prompt calculus's typed representation, or demonstrate an equivalent
closed encoding; the spike's document-slot refusal is not a release exclusion.
Validation-contract parity compares result schemas and runtime validation
rules; source-map subjects belong to provenance, not semantic equality.

Evidence: the two routes' requests were compared field by field without
normalising, on the `std/improve` example, the two single-call workflows and
the decisive program; every difference is one of R1, R2, R3, R5, R6 and R11,
with the value its rule gives (spike iteration 3, F).

## 10. Views

Readers of run state depend on rows named by step, on one current step and
on order. For this profile the runtime derives views by these rules.

| Rule | Statement |
| --- | --- |
| V1 | A view is derived from the memo and the program. Rows come from the records. The run's position comes from evaluating the program against the memo without launching anything: a `halt` value leaves no record before the terminal record, so a projection of the memo alone cannot say where the run stands |
| V2 | The run's status: `completed` or `failed` when the last record is `terminal`; otherwise `settling` when a writer holds the lock and every effect the program reaches is committed; otherwise `running` when a writer holds the lock; otherwise `interrupted`. A later release adds `suspended`, for a pending request |
| V3 | A `terminal` record is checked against §7.1: every active coordinator commit, identified by its checked `effect_class`, must have a matching `settled` record for that identity and attempt before the terminal. A completed terminal additionally requires replay to reach the same `halt` with no missing commit; a failed terminal may have an uncommitted failure. Missing proof, class mismatch, missing settlement or adjacent terminals yield `memo_inconsistent`, with no completed outputs |
| V4 | Liveness comes from the writer's lock, not from a heartbeat: a process that died released it, and the view says `interrupted` at once. The present report says `running` until a heartbeat is 300 seconds old |
| V5 | `steps`: one row per effect identity, keyed by its canonical text, in order of first `started`. Status, result, error and timing come from the records: `running` from `started`, `completed` from `committed`, `settling` for a coordinator effect between `committed` and `settled`, `failed` from `failed`, `invalidated` for every commit covered by a range record (C8). `current_step` is the effect in flight; `next_effect` is the first uncommitted effect when nothing is in flight. `workflow_outputs` is the terminal record's value |
| V6 | Per-attempt files live in the attempt's directory (§8.2): `result.json`, `stdout.txt`, `stderr.txt`, and `prompt.txt` for a provider. A row's output preview reads them. Nothing is named by step name; nothing is overwritten by a later attempt |
| V7 | The memo does not carry, and the view does not report: `step_visits`, `transition_count`, `call_frames`, the prompt-context audit, judgment views, observability summaries, provider sessions and observation files, the heartbeat. The readers that need them (the resume planner, the projection integrity audit, the dashboard cursor's frame walk, the human-input guard, the prompt session lookup, the monitor email's log lookup by step name) are not used at the new target, or are adapted to V6 when their class enters. Sessions and observation files enter with the classes that need them, named by identity digest and attempt |
| V8 | A view launches or reconciles nothing and may be taken while the writer holds the lock. Cost is the journal scan plus pure replay of the reached program; no linear bound in memo length covers unbounded pure work. The spike measured 0.17 seconds for its 5,000-effect specimen (gate report, §5) |
| V9 | `state.json` is an atomically replaced derived view after each synchronized record, with the header keys `schema_version`, `result_persistence_profile`, `run_id`, `workflow_file`, `workflow_checksum`, `started_at`, `updated_at`, `status`, plus `error`, `workflow_outputs`, `bound_inputs` and effect rows. The exact schema/profile pair in §8.4 routes readers to the adapters below; writing old header keys alone does not establish compatibility |

The view's integer `memo_offset` is the exclusive end byte offset of the
complete journal prefix it represents (zero for an empty journal). Concurrent
readers snapshot a complete-line prefix, ignore a torn tail, and use lock
liveness for V2; they never append or repair run files. A stale/missing view
is reconstructed in memory. Only the writer repairs it on resume. If atomic
view replacement fails after a journal append, the append remains authority;
stop with an I/O diagnostic before another dispatch, without undoing a commit.
No reader may treat an older completed snapshot as the current terminal.

| Reader | First-release adapter obligation |
| --- | --- |
| `RunState`/state loading | Recognize the evaluated profile before the flat-route status/schema checks. Preserve V2 statuses in this profile; older targets retain their current four statuses |
| Monitor classifier | Map evaluated `completed`/`failed` to terminal events, `interrupted` to a stopped/interrupted event using lock liveness, and `running`/`settling` to active; do not infer a stalled writer from an absent legacy heartbeat |
| Watchdog and usage-limit watcher | Treat `running`/`settling` as live, `interrupted` as resumable interruption, and only validated terminal records as terminal. Derive attempt errors/log locations from V5/V6 |
| Report and dashboard cursor | Render effect order, current/next identity, errors, result and per-attempt previews directly from V1–V6; replace their step/frame walk for this profile. The current state-only renderer is not sufficient evidence |
| Trial SDK | Outside the first release with trials. Its required unique completed `steps[*].trial` envelope must be supplied/tested when that class enters; generic effect rows do not serve it |

These are Phase 3 reader changes with public integration prerequisites (§18),
not an assertion that the current readers already understand the profile.

The spike's view reproduced the present report's rows for a run killed
during its second command, and said `interrupted` where the present report
said `running` (gate report, §5; spike iteration 2, D2). A hand-edited memo
with a terminal record and no settlement was reported as completed (gate
report, §6); V3 is the last review's rule.

## 11. Parallel Effects

`par-map` is a later release (plan, Phase 5). Its rules are fixed here so
that identity and the memo need no change when it enters.

`par-map` evaluates a body once per item of a list, with at most `n` items in
evaluation at a time.

- Each item's body is evaluated in sequence. Items are independent.
- Identity includes the item index (I2), so it does not depend on which
  item finishes first.
- The result is a list in the order of the input.
- One writer appends to the memo (M1). Evaluations send it records; they
  never write.
- When an item fails, the others run to completion and their results are
  committed. The map then fails. Resume runs only the items without a
  commit.
- Every effect of an item runs in a working directory given by the map as an
  expression over the item. Before launch the runtime checks that no two
  items resolve to the same directory, and refuses with
  `parallel_workspace_shared` if they do.

Surface form:

```lisp
(list/map-effect ((repo repos)) :max 8 :parallel 4 :workspace repo
  (call implement-one :task task :repo repo))
```

Without `:parallel` the form means what it means today.

Limits, stated so that the form is not taken for more than it is:

- It evaluates a batch. The list is fixed before the first item starts, and
  the map returns when every item has settled. A policy that chooses its next
  candidate after seeing each result is a different policy; running it in
  parallel changes what it decides. This form does not express it.
- A budget counted in effects is charged per item, before the item starts. An
  item that would exceed the budget does not start.
- There is no cancellation in this version. A running item is not stopped
  when another fails.
- It is adopted when a workflow needs it. It does not repair any failure of
  sequential programs.

## 12. Diagnostics

- A refusal that compares a value with a limit prints the value and the
  limit.
- A failure after typecheck says that it is a compiler defect, names the
  stage and points at the authored form.
- A run-time failure of a pure operator points at the expression and prints
  its operands.
- `effect_input_diverged` prints which parts of the resolved input differ
  and which declared files, not only that something does.

Codes this design introduces or keeps, and where each is raised:

| Code | Raised |
| --- | --- |
| `closed_program_gap` | At target-aware admission: a form or effect class explicitly outside this release (§1.1); not a fallback for a missing implementation of an admitted form |
| `compiled_workflow_source_required` | Before admitting an explicit compiled import at 2.35: the matching complete original typed snapshot is missing or structurally mismatched (§4.2.1); not a historical-authenticity check |
| `compiled_workflow_snapshot_conflict` | At closure admission: different source/context under one canonical definition, naming both origins (§4.2.1) |
| `command_boundary_closure_missing` | At build: a boundary without a `closure` field (C1) |
| `command_boundary_manifest_invalid` | At build: a malformed closure declaration, including `null` (C1) |
| `command_closure_unreadable` | Before a first attempt: a missing, unreadable or unsupported declared path, with path/reason (C2); when comparing a prior start/commit use `effect_input_diverged` |
| `command_closure_written` | Before commit: declared closure evidence changed during the command attempt (C4) |
| `command_result_inputs_invalid` | At build: malformed, duplicate or nontransportable external-tool `:inputs` (§9.1.1) |
| `command_transport_required` | Before new run authority: a valid compile-only Phase 2 command lacks `argv_transport`; rebuild explicitly (§9.1.3) |
| `undefined_variables` | At reached command input resolution: a missing template binding/dictionary key, `None` or invalid filter; no start/dispatch (§9.1.3) |
| `effect_input_invalid` | Before reserving a command attempt: a typed input value violates its checked contract, with field/value path and the existing violation code (§9.1.1) |
| `workflow_input_missing`, `workflow_input_unknown`, `workflow_input_invalid` | Before the run root holds a record (§5) |
| `resume_program_changed`, `resume_inputs_changed`, `resume_interpreter_missing` | At resume, before any record is read (§8.4, C3) |
| `resume_request_missing` | At resume before any memo record or evidence mutation: a previously published evaluated header lacks its durable rebuild recipe (§8.4); read-only projection and invalidation remain permitted |
| `resume_run_ref_root_changed` | Header/option preflight (exit 2): an explicit resume root differs from the immutable evaluated header root (§8.4); no evidence mutation |
| `resume_run_ref_root_missing` | Historical evaluated header lacks root: pertinent replay refuses readonly (exit 2); a later reached coordinator after new command/provider continuation refuses locally before start/prepare (exit 1), preserving legitimate earlier commits (§8.4) |
| `resume_result_root_changed` | Header/option preflight (exit 2): the selected run root's relationship to the resume workspace differs from the immutable header `result_root` (§8.4); no evidence is read or written |
| `result_root_missing` | A reached `provider-bundle-path` in a run whose header lacks `result_root`, historical or a direct publication that names no workspace (§8.4): preflight replay refuses readonly (exit 2); continuation after new commits fails the run through the ordinary failed-terminal guard (exit 1); read-only replay stops at the form |
| `interpreter_changed` | A diagnostic, not a refusal, at resume (C3) |
| `memo_busy` | A second writer (M1, C8) |
| `memo_inconsistent` | Missing authority with journal activity or a present malformed rebuild recipe/run-reference root/result root (§8.4), an invalid range anchor/suffix (C8), or memo/terminal checks failing (V3) |
| `effect_input_diverged` | At the first committed effect whose input differs, or before retrying an uncommitted command whose implementation evidence differs from `started` (§8.1) |
| `effect_rerun` | A diagnostic in the run's result and the view, naming the identity and its earlier attempts (§8.1) |
| `lexical_restore_pending_effect_unsafe` | An uncommitted attempt of a `must_not_repeat` boundary (§8.1); the present code, kept |
| `effect_attempt_path_exists` | Exclusive allocation collides after the ordinal's synchronized `started`; append `failed`, preserve the directory, launch nothing (§8.2) |
| `invalidate_not_committed`, `invalidate_coordinator_committed` | The explicit continuation (C8) |
| `invalidate_profile_unsupported` | Public invalidation selects a legacy profile; no write occurs (§8.5) |
| `parallel_workspace_shared` | A later release (§11) |

## 13. Targets And Compatibility

- Evaluated execution applies from target 2.35 (plan decision 6, selected
  by the owner on 2026-09-30). A program at that target runs on the evaluator
  only once the evaluator is delivered; Phase 2 provides compilation only.
- Until explicitly retired under plan decision 8, programs at older targets
  compile and run as they do. Require raw byte-identical artifacts for
  identical identity inputs. The existing compiler/runtime identity hashes
  the installed package bytes; changes to those bytes truthfully change its
  pin and dependent run-ref artifacts, including at older targets. Preserve
  that pin. Report real-pin differences separately from a fixed-identity
  serialization comparison; do not normalize artifacts or describe the
  controlled comparison as real-pin byte equality.
- While its profile is retained, a run started under one profile is resumed
  under it; a run started under one representation of the closed program is
  resumed under it (§8.4). Retiring existing runs requires an explicit
  disposition under plan decision 8, not silent conversion to another profile.
- A module at the new target may import a module at an older target when the
  imported definitions use only forms the closed program can express. The
  import is compiled under the new target's rules. An evaluated-entry build
  skips flat lowering across its source graph, consuming the imported typed
  signatures, effects and bodies through the existing imported-signature
  and workflow-catalog path. It must not require those bodies to lower
  successfully to flat steps first or fabricate a validated bundle; no new
  signature abstraction is required.
  An older-target entry still takes its existing build/lowering route and
  validation profile, even when its source producer retains a typed snapshot.
  Gate on the actual entry target, never snapshot presence.
- Explicit supplied compiled imports follow §4.2.1. The `kind=compiled`
  manifest remains `.orc`-only: an old-target producer supplies its runnable
  bundle and snapshot; a 2.35 producer supplies its selected typed snapshot
  without manufacturing a runnable bundle. The evaluated build selects this
  loader before the legacy initializer eagerly compiles imports. Both use
  the existing manifest validation, export selection and configuration owners;
  the build key includes producer source/configuration contributions.
- A module at an older target may not call a module at the new target. The
  two run on different runtimes.
- The command boundary manifest gains the field `closure` (C1). At older
  targets through 2.34 the field is accepted and ignored by binding
  serialization and effect identity, including when explicitly supplied;
  absence emits no new field. Existing raw-manifest cache hashing stays as is.
- External-tool `:argv` plus `:inputs` is a target-2.35 source form; older
  entries retain the existing `command_result_adapter_invalid` refusal for
  that combination. Existing argv-only and certified inline-document forms
  retain their source meanings, absent-field serialization and request bytes.
  The additive closed `document` use does not change the schema/representation
  for existing checked artifacts; the earlier Phase 2 reader refuses the new
  external-document combination. It never executed target-2.35 runs. Once
  runtime runs exist, §8.4's profile/representation pin applies without
  conversion.

## 14. What Is Preserved

| Guarantee | How |
| --- | --- |
| A result is validated before it becomes canonical state | Step 4 of §8.2, before `committed` |
| No committed provider call or child run runs again | Rule E3; K2 to K4 for a coordinator |
| A changed semantic program/configuration is refused before run-evidence mutation | Fresh build and header comparison (§8.4), with provenance-only edits admitted; changed declared inputs refuse before any launch or reconciliation (C7) |
| Effect sites are known before a run | The site table, P4 |
| Wrong-path writes fail closed; stdout is not a result channel | The performer reads only its result path |
| Refusals name their rule | §12 |
| One run at a time in a workspace | The workspace lock; one writer per memo (M1) |
| Runs can be inspected from the filesystem | The memo, the attempt directories and the derived views are files |
| `must_not_repeat` stops a resume at an uncommitted effect | §8.1, the present code |

## 15. What The New Target Does Not Use

Defunctionalization to steps, the older lowerers, positional resume, the
projection integrity audit, lexical checkpoints, pure projection steps, the
pure-result replay index, managed write roots, generated helper commands,
call frames in run state, and the rule that structured control is top-level
only. They stay in the repository for older targets.

## 16. Alternatives

| Alternative | Decision | Reason |
| --- | --- | --- |
| Repair the flat route position by position | Rejected at gate G1 | Four rounds of repair on one class of defect and 34 of 120 matrix cells still failing (gate report, §8). Every remaining defect has a second layer under it |
| Keep flat steps and evaluate pure expressions on demand | Not chosen | Removes the producer rule. Keeps defunctionalization, positional resume and one iteration ordinal per key |
| Restore a serialized environment at a checkpoint | Not chosen | Needs every value to be serializable at every point and an identity for every program point. Evaluation from the entry needs neither |
| Journal replay of arbitrary code | Rejected in 2026, and still | This design is not that. The language is closed, sites are listed before a run, every memo hit is checked against the input, and no effect runs unless the memo lacks its result |
| A workflow library in a host language | Rejected | Loses checks before a run and the bound on what an authored workflow can do |
| A closed program as a tree, one callee body per call path | Not chosen | Grows with call nesting: 652 nodes against 87 at depth 4 (§4.2). The table names the same effects |
| Invalidation by value dependence alone | Not chosen for the first release | Misses a dependence through a file (C9) |
| Binding the interpreter per effect | Not chosen | An upgrade of an ambient tool refuses every resume (C3) |

Two measures on the flat route were taken in Phase 0 of the plan and do not
change this design: a bound value shared in a pure payload, and a result path
per call that does not exist before the call.

The earlier rejection of journal replay gave three reasons: static effect
visibility, validation before commit, and parity evidence that a machine can
compare. The first two are kept by P4 and by §8. The third changes.
Evidence of parity between the two routes is behavioral: for the same
program, inputs and effect results, the same ordered effect identities, input
digests, result digests and final value, and a request equal field by field
apart from R1 to R12.

## 17. Evidence Requirements

Each requirement holds for the first release through the public run and
resume entries. Where the spike met it, the reference is the measure to
repeat.

| Requirement | Measure | Spike |
| --- | --- | --- |
| Totality | Every cell admitted at this target runs; refusals name only the release exclusions. No known defect remains among admitted forms. The matrix covers each form directly, through a same-module helper and through an imported helper | Met on 100 typechecking cells of 120, the 32 the present route fails among them (gate report, §2, criterion 1) |
| Real programs | The `std/improve` example and the two workflows of the single-call comparison run to their expected result, unchanged in source apart from the target | Met with stand-in providers (gate report, §2, criterion 1) |
| The search controller | The MLEvolve-inspired controller makes the decisions of its Python reference, in the same order, with the same budget spent, and returns the same result. Its form is the compact one, with one helper for both branches | Met on 72 pairs of leaf scenario and budget (gate report, §2, criterion 2) |
| Growth | Doubling the fields of the controller's state and the number of its branches leaves it running. No limit depends on the size of an expression | Open |
| Structured inputs | Public compile/run/resume of external `:inputs`: a candidate record and list of records of unions round-trip; wrong shape, non-finite and invalid nested path values fail before dispatch; source operand effects run once in order; empty versus absent documents, read-back tampering, stable digests across attempts and unchanged legacy/certified argv are checked | Open: Phase 3, exact contract in §9.1.1 |
| Artifact handoff | A real file-producing command returns a typed path, a provider reads its declared document dependency, and the final publisher writes its declared file; assert path/producer/consumer evidence, required-file validation, fresh dependency bytes on retry, changed-byte refusal and no repeated committed provider/publisher on resume | Open: repeat the watchdog/verified-drain owner behavior through public evaluated entries (§9.1.2); neither a path string nor C9 alone is file-read evidence |
| Nesting | A loop in a branch, a loop in a loop, and a branch in a hook run | Met (gate report, §3) |
| Resume | For each real program, killing the process from outside in each window of each effect and resuming gives the final value of the uninterrupted run, with no committed effect run twice | Met: 96 kills (gate report, §2, criterion 3) |
| Identity | Adding blank lines, and moving the program and the package, change no identity | Met (gate report, §2, criterion 5) |
| Sites | Independent `perform`-node/site-table bijection and one frame per effectful call; fixtures cover `select` prefixes, nested `block`, `join` body/continuation, exhaustion and control in aggregate/terminal positions. Every memo identity instantiates one site and its frames | Existing corpus instances met (gate report, §2, criterion 6); total traversal beyond that corpus remains a prerequisite |
| Parity | On programs both routes accept, the effect traces are equal and the requests are equal apart from R1 to R12 | Met on 68 matrix cells, the shipped examples and a reduced decisive program (gate report, §2, criterion 7) |
| Older targets | Byte-identical build artifacts | Open: held by construction in the spike, no byte comparison run |
| A dependence through a file | Command A writes a path that command B reads by a fixed name, with no value between them. After A's input changes and `invalidate A`, the resume gives the value of a fresh run, and B ran again | Failed on the value-only rule; iteration 4 reproduced and corrected it with suffix invalidation. Public-entry evidence remains required |
| A read-only closure with external caches | A Python package command resumes with cache files absent from the closure (disabled or outside it); assert that placement. A changed authored script refuses resume, and a command modifying its closure fails before commit | Iteration 4 measured both cache placement and write detection; repeat through public entries |
| The interpreter fixed for the run | Changing `PATH` alone launches the recorded executable with no change diagnostic. Changing bytes at that path emits `interpreter_changed` and continues on it; a missing/unlaunchable recorded path refuses. No interpreter digest enters effect-input identity | Iteration 4 demonstrated PATH pinning but retained digest-based refusal; the accepted C3 changed-bytes policy remains to prove |
| An undeclared closure | A boundary without a `closure` field is refused at build, and a wrapper whose second script changed is never reused | Met for the refusal under `strict` (spike iteration 3, B); C1 makes it the only rule |
| A terminal record without its settlements | A memo with a terminal record and a coordinator commit lacking `settled` is reported `memo_inconsistent`, with no outputs | Failed on the spike (gate report, §6); V3 is the rule to test |
| A coordinator other than a run reference (later admission) | One shipped workflow through both routes, killed at both gaps, plus its internal interruption semantics and proof authority | Iteration 4's trial specimen, with production recovery coverage after the Phase 0 correction; changed-decision/settlement/capsule limits in §9.3 remain prerequisites |
| The request contract | Every field of every request compared without normalising; a field not in R1 to R12 is equal | Met (spike iteration 3, F) |
| Attempt allocation | External kills before/after the synchronized `started`, after exclusive directory creation and before dispatch; next ordinal on resume, old evidence unchanged, no dispatch on collision, and conservative refusal for `must_not_repeat` | Open; the spike did not implement the design's original pre-`started` allocation order |
| Durable run authority | Fault injection before/after each program/header write, file sync, rename and directory sync, including run-root creation and empty-journal sync. Model unsynchronized writes disappearing: either valid authority survives for every durable record, or no effect was dispatched. Missing authority with a nonempty journal refuses without reconstruction | Open; this is a crash/power-loss contract, not a demonstrated production failure |
| Retry after a closure change | A command modifies its declared script and exits: C4 fails it; resume with unchanged `.orc` source launches nothing until original implementation evidence is restored. Repeat with a kill after modification but before `failed`, with a changed package helper, and with `must_not_repeat` | Open; the missing guard was a contract counterexample, not a demonstrated production failure |
| Atomic suffix invalidation | Kill before append, within a torn range line, after a complete write/before sync, after sync and before acknowledgment. Each recovered memo cancels none or the entire selected suffix; no later commit is stranded, future retry commits survive, and a coordinator anywhere in the suffix refuses before append | Open; one range record replaces the per-effect invalidation writes |
| Clean terminal resume | Resume a completed effectful run and a pure-only run twice: identical memo bytes and results; failed-attempt resume appends `started` before a later terminal; repeated preflight/pure failure adds no duplicate terminal | Open; iteration 3 appended adjacent completed terminals |
| Dispatch accounting | Command/provider executor configured to retry receives a retryable failure: one external dispatch, one `started`, one directory, then `failed`; explicit resume reserves the next attempt or refuses `must_not_repeat` | Open |
| Early divergence | Change a declared file bound by a later committed effect whose inputs depend on earlier results; refuse before launch, reconciliation, tail repair or view replacement, with the first divergent commit in journal order | Open; the spike's on-encounter check alone is insufficient |
| Workspace-relative result path | Public paused and uninterrupted X4 runs return exactly the R2 destination; a nested `--state-dir .orchestrate/runs/custom` run returns its actual path, not the default spelling; completed and committed-boundary resumes redispatch nothing; source-free view load opens no recipe or result file; whole-workspace relocation keeps the value and resumes; a run root not under `<workspace>/.orchestrate/runs` fails at the reached form with a failed terminal that read-only loaders report and invalidation can reopen; malformed and absent headers take their §8.4 dispositions; both production publishers (the public entry under a nested `--state-dir`, the path-mode child) publish the fact; old-route and refinement controls are unchanged | Open: Phase 3, exact contract in §8.4, *Immutable result root* |

## 18. Feasibility Obligations

These rows distinguish historical spike evidence from implemented Phase 2
compiler evidence. Public runtime/recovery fixtures remain open; the [Phase 2 plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md#status-authorities-and-scope)
owns task completion.

| Claim | Fixture | Evidence and remaining work |
| --- | --- | --- |
| The closed program can be built for the corpus | P1 to P7 hold for every workflow whose forms/classes are admitted; inventory every refusal against §1.1, including stdlib command closures. Never seed an unknown implementation closure as empty merely to pass | Historical spike: 38 of 52 built in iteration 3, 39 in iteration 4; phased calls were treated as ordinary calls. Implemented Phase 2 corpus: 37 Built, 10 Gap, 4 Refused, 1 NotSynthesizable, owned by `tests/test_workflow_lisp_closed_program_corpus.py`; every Built artifact is validated/read back and its perform/site bijection checked. Neither count establishes runtime parity |
| A lexical path distinguishes every effect site, across inlined copies | A procedure with one effect, called from three arms of one `match`, in a loop | Met (gate report, §2, criterion 6) |
| Prompt assembly can run outside the executor | Public compile/run fixtures distinguish `asset_file` and `input_file` using different texts at their lookup locations; a document-slot `defprompt` and dependency snapshots assemble the same prompt as the flat route, apart from R3 | Asset/template/typed-input/contract-block specimens met; source-kind distinction, document slots and dependency snapshots remain prerequisites |
| Evaluation is a function of program, inputs and committed results | Two evaluations with one memo give the same trace and launch nothing the second time | Met (spike iteration 1, commit `92d47fe0`). Open: path existence checks, variant selection by workspace digest and secrets are each an effect or part of a resolved input; secrets are not designed |
| The views satisfy their readers | Every V9 adapter reads the evaluated profile through its public entry, including concurrent partial-tail/stale-view cases and a failed atomic view replacement after commit | Only report-shaped in-memory rows/status shown in iteration 2; durable publication, status adapters and public-reader integration remain prerequisites |
| A run-reference adapter can reuse its runtime and ledger | A compiled path-mode run reference, killed at both gaps, with the changed caller adapter | Met in the spike (iteration 3, E); public evaluator integration remains required |
| The context forms have a closed value equal to the present route's | One program per form (X1 to X4), run on both routes | Met for X1 and X4; X2 and X3 open |
| Non-finite numbers cannot reach an input digest | The numeric surface's boundary rule, implemented at target 2.34 | Owned by the [numeric surface](workflow_lisp_numeric_surface.md) |
| A typed input document can carry records, unions and lists | One command that receives a list of records of unions and returns it unchanged | Open: Phase 3 of the plan |
| The checked form refuses a tampered type | Tamper a non-operator value, nested nominal descriptor, effect result, entry result and call argument/result in the stored artifact; structural/type validation refuses each, not merely a digest mismatch | Implemented: checker/artifact read-back reject those tamperings, including public CLI artifacts; `tests/test_workflow_lisp_closed_program_artifact.py` and `tests/test_workflow_lisp_closed_program_compile_cli.py` |
| Complete canonical specialization | Same base/types with different proc targets, value bindings, bound proc arguments and workflow references coexist; captured values retain lexical once-only binding through forwarding and local procedures. Public builds after formatting and relocation have identical keys/digests | Implemented compiler evidence: canonical keys distinguish selected targets/bindings and retain lexical creation bindings. Public formatting/relocation builds preserve keys/digests in `tests/test_workflow_lisp_closed_program_compile_cli.py`; runtime once-only evaluation remains open |
| Imported admitted control avoids flat lowering | A new-target entry imports an older-target helper with a typechecked loop in a branch that the flat route refuses; public closed compilation succeeds from typed interfaces/bodies, without first making a flat validated bundle. The old entry route remains byte-identical at identical identity inputs (§13); an old entry calling a new-target module is refused | Implemented public compile: the evaluated entry skips flat lowering across selected imported typed bodies; old entries retain their route and refuse evaluated dependencies. `tests/test_workflow_lisp_closed_program_compile_cli.py` and `tests/test_workflow_lisp_target_evaluated_execution.py` |
| Position-free generated identities | Public path-mode run-ref and `let-proc` builds after blank lines/source relocation; imported private same-named types remain distinct recursively in keys and entry/effect/nested descriptors | Implemented: local callable identities, private nominal descriptors and finalized run-reference signatures omit paths/positions while preserving owners; public relocation/read-back coverage is in `tests/test_workflow_lisp_closed_program_effects.py` and `tests/test_workflow_lisp_closed_program_compile_cli.py` |
| Common command configuration | Both binding kinds: absent versus empty, malformed/null, normalized duplicates, directory/symlink changes, unreadable entries and output overlap. An unused manifest-entry change changes the program digest. Targets ≤2.34 remain byte-identical for unchanged identity inputs (§13) and ignore closure in binding payloads when supplied | Implemented declaration/build checks for both kinds, unused configuration identity, and public CLI carriage; `tests/test_workflow_lisp_command_boundary_closure.py` and `tests/test_workflow_lisp_closed_program_compile_cli.py`. Compile reads no closure bytes. Filesystem/content-hash/recovery checks remain open in Phase 3 |
| Builtin adapter closure | Public compilation automatically injecting `validate_review_findings_v1` carries its checked-in package declaration; removing it refuses, never substitutes `[]`. A moved byte-identical package keeps logical/input digests, changed adapter/shared-helper bytes refuse reuse/retry, and workspace/PYTHONPATH shadowing refuses before dispatch. Check package caches remain outside the closure and old-target artifacts stay unchanged | Implemented public compile: used injected declarations retain trusted package origin and explicit closure through construction/read-back; `tests/test_workflow_lisp_closed_program_compile_cli.py` and `tests/test_workflow_lisp_closed_program_build.py`. Runtime launch-origin, changed-byte, retry and cache-placement checks remain open |

## 19. Decisions Still Open

The first three iterations' 38 decisions are rules above. Later-admission
questions from iteration 4 and remaining feasibility evidence do not change
the first-release architecture. Target-number question 1 was resolved by
the owner on 2026-09-30; the remaining questions below stay open.

| # | Question | Answered by |
| --- | --- | --- |
| 1 | The number of the new target — resolved | 2.35, owner decision of 2026-09-30 (plan, decision 6) |
| 2 | When older targets are retired | The owner: plan, decision 8. After the maintained workflows run at the new target |
| 3 | Whether K1 to K5 hold for a coordinator that is not a run reference | Iteration 4 supplies bounded trial evidence; §9.3 prerequisites must pass before that class enters |
| 4 | Whether the compiler's `PhaseCtx` (X2) and `phase-target` (X3) values equal the present route's | One program per context form, run on both routes, with the equality asserted on the values (§18) |
| 5 | Whether prompt dependency snapshots render as the present route renders them | The two routes' prompts compared on a workflow with prompt dependencies (§18) |
| 6 | When invalidation may narrow to dependents through values and declared files (C9) | A later release, when command boundaries declare the files they read and write, tested by the file-dependence fixture of §17 |
| 7 | How sessions, observation files and secrets are named and resumed | Not designed. Each enters with the class that needs it, with its own evidence (§1.1) |
| 8 | Whether an interrupted, unsettled judge attempt spends a trial's budget | Owner decision before trial admission: preserve the current charged-at-allocation policy (a crash may change the decision), or change charging/retry semantics with explicit evidence. This design selects neither; trials remain later |
