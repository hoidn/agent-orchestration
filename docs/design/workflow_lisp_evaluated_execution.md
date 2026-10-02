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
- **Created:** 2026-09-29. **Revised:** 2026-09-30, after gate G1, independent design/Phase 2
  contract review, and the supplied compiled-import contract amendment.
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
fixes the exact nine-element JSON array, reference bindings, capture routes,
residual signature and source-independent checks. Binding maps use declared
formal names, or `["local", index]` for a generated local's captured formal;
local selectors sort by index before ordinary strings sorted by name.
Ordered type arguments, residual parameter types and record fields retain
declaration order. The residual signature excludes the capture prefix.

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
| Procedure reference | The recursively canonical target key, residual signature and each bound argument's formal selector, type and binding; bound rows biject with the target's bound-formal facts, including category, value or mapped capture route. All views derive from one resolved binding; forwarding resolves to that target, not an alias |
| Workflow reference | The canonical workflow key and its resolved extern-rebinding plan, by formal extern name and exact provider/prompt row from the shared schema; no unresolved alias or opaque payload |
| Value binding | The checked, closed expression substituted into the specialized body, with canonical types and alpha-normalized local names; tagged literals preserve distinctions such as `Bool`, `Int` and `Float` |
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
| X4 | `provider-bundle-path` | The committed attempt's result file, relative to the workspace (§8.2): a `result_path` value read from the memo, so it is the same on every resume. At the new target the form is typed as a path under the run root, so the value meets its root; both routes today type it under `state` and refuse their own value (`outside_under_root`) |

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
| `terminal` | `completed` only after `halt`, every reached effect committed and every committed coordinator settled; `failed` after an attempt or evaluation fails, with no unsettled committed coordinator | no identity; `completed` with the value of `halt`, or `failed` with the code and message |

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
| C2 | The resolved input of a command binds, by content: each stable-command token that names a workspace path, and each closure entry. The normalized declaration and file evidence use the common encoding below. Modification times are not bound |
| C3 | The interpreter, the first token of a stable command when it is a bare name, is resolved on `PATH` once, when the run starts. The run header records its resolved path and digest. Every attempt of the run launches the resolved path, not the name. The interpreter does not enter any effect's resolved input: a changed digest at resume is reported as `interpreter_changed` and the run continues on the recorded path; a missing path refuses the resume with `resume_interpreter_missing` |
| C4 | A closure is read-only. Rehash before commit and fail the attempt with `command_closure_written` if its declared files changed. Before retrying an uncommitted attempt, compare the current implementation-file evidence with its `started` evidence and refuse any change (§8.1), even if no failure record survived. A resume that finds a committed effect's declared file changed also refuses (C7). Caches and outputs, including generated adapter input documents and attempt files, live outside every closure. Commands are launched with `PYTHONDONTWRITEBYTECODE=1` |
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

Runtime evidence is a sorted map keyed by the declared logical base/path (and
the stable-command token's position where applicable). A regular file row
contains `kind: file` and `sha256:<digest of bytes>`. A directory row contains
`kind: directory` and the SHA-256 of canonical JSON rows of its files, sorted
by relative POSIX path, each carrying the file evidence. All files, including
dotfiles and caches, participate; empty directories contribute no file rows.
For paths through symlinks, each row additionally binds the resolved target,
relative to its workspace/package base when inside that base and absolute
otherwise. Directory traversal follows declared symlink targets and records
their target identity;
cycles, missing/dangling entries, unsupported file kinds and unreadable files
fail closed. No absent path is hashed as an empty file. On a memo hit these
failures are divergences; before a first attempt they are closure-resolution
failures. The path and reason are reported.

Input/result/cache destinations must not equal a closure file or lie beneath
a closure directory, including resolved symlink aliases. Check runtime-owned
destinations before creation; a command that writes an undeclared cache there
violates C4 and its changed closure refuses resume. There is no ignored-cache
rule. The adapter's positional JSON input remains value data (§9.1), never an
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
   Derive `effects/<digest of the identity>/attempt-<n>/` and its result path.
   Append and synchronize `started` **before** creating that directory.
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
the attempt's `failed` record and a `terminal` record with outcome `failed`.
A resume runs the next attempt unless `must_not_repeat` refuses it. For
commands and portable providers, one memo attempt permits one external
dispatch: bypass internal executor retries. Retryable failures still stop
this run; resume reserves the next ordinal. A coordinator's child attempts
remain governed by its existing ledger and K2 to K4.

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

The run root holds `run.json`, written before the first record: the program
digest, the input digest, the bound inputs, the representation version of
the closed program (§4.2), and the interpreters fixed for the run (C3). The
program artifact is written beside it. Initial publication is durable:

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

Resume takes the writer lock without
changing the journal, freshly builds the authored entry with the current
manifests/configuration, and compares that program digest and the newly bound
input digest with the header. A mismatch refuses with `resume_program_changed`
or `resume_inputs_changed` before reading any memo record or mutating run
evidence. An invalid fresh build is also a preflight refusal. Formatting and
provenance-only changes are allowed by P6, not raw source-byte equality.

Then validate the stored artifact's checked form and header digest; execute
that stored artifact after equality is established. Read complete memo records
without repairing them yet and validate their classes, sites and settlements.
Before any mutation, launch or coordinator reconciliation, replay the active
committed prefix using stored result values, freshly resolving every input and
checking it in commit order. This supplies later inputs dependent on earlier
results. At the first uncommitted effect, also check any latest `started`
implementation-file evidence under §8.1 before stopping preflight. An active
later commit that replay cannot reach is inconsistent, not permission to
launch past it. Only
after preflight passes may M3 repair a torn tail and evaluation continue.
This preflight and evaluation share one interpreter; they are not separate
resume planners. Files changed concurrently after preflight remain outside a
snapshot guarantee; an input is checked again on encounter before reuse.

If the last complete record is a valid completed terminal, replay must reach
the same `halt` value, with all settlements present. Return that terminal
without appending records, creating attempts or launching/reconciling work.
An unchanged failed terminal with no new activity is likewise not duplicated.

The representation is part of the program identity. A run started under one
representation is finished, resumed or abandoned under it; a memo is never
converted. The first release ships one representation, the table form, so
the rule bites only when a later release changes the form: then a run in
flight completes on the release that started it.

### 8.5 Explicit continuation after a divergence

A resume that stops with `effect_input_diverged` does not rerun anything.
For a committed result, the continuation is C8. For an uncommitted attempt's
implementation mismatch, restore its `started` evidence under C4; invalidation
does not bypass that guard.

| Rule | Statement |
| --- | --- |
| C8 | `invalidate <run> <identity>` atomically cancels the chosen active commit and every later active commit in journal order with **one** synchronized `invalidated` range record. The next resume runs those effects again; every earlier commit stays. Under the writer lock, validate the whole suffix before writing anything. Refuse `memo_busy` for another writer, `invalidate_not_committed` for a chosen identity without an active commit, and `invalidate_coordinator_committed` if the suffix contains any committed coordinator: a committed child run is never superseded (K8) |
| C9 | Each `committed` record keeps `depends_on`: the identities whose results its resolved input read, through names, arguments, results, loop state, join parameters, `case` bindings and the conditions that chose a value; an effect inside a branch does not depend on the branch's condition. In the first release this is evidence, not the scope of an invalidation: a dependence through a file, where one effect writes a path that a later one reads, leaves no trace in values, and a shipped workflow has that shape (`workflows/library/verified_iteration_drain/drain.orc`). Narrowing an invalidation to dependents through values and declared files is a later release, entered when command boundaries declare the files they read and write, with the file-dependence fixture of §17 as its evidence |

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
| A value in `:argv` | Rendered as the present route's variable substitution renders it: a string as itself, a number as its decimal text, a `Bool` as `true` or `false`, a record or list as JSON with the substitution's spacing (`json.dumps` defaults), keys in the value's order. Both routes give the same argv bytes (spike iteration 3, F) |
| A certified adapter's inputs | One JSON object, fields in signature order, as the last argv token, as today. The document carries the declared inputs only, each projected to its declared type |
| Any value bound in `:inputs` (Phase 3 of the plan) | One typed input document in JSON, written in the attempt's directory. The command receives the path. The document is validated against the declared types before launch |
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
| K7 | A run reference: its static configuration is built at build time, each input bound as the reference `inputs.<name>`; the name rule of the child's inputs is the reference rule, so no valid name is unsafe. The coordinator resolves the references against a parent state that holds only the resolved input values. The visit key is derived from the identity: parent run id the run root's name, execution frame `root`, no call frame, step id `root.<digest of the identity>`, visit count 1. The runtime's ledger, `run-ref-attempts.jsonl`, is unchanged |
| K8 | A committed coordinator effect is never superseded in the first release: no new visit key or attempt for an identity that committed through a coordinator, and no rollback of the child's workspace delta (§3) |
| K9 | Every coordinator in a release has evidence through the public run and resume entries: a compiled program killed from outside at each of its two gaps, resumed to the uninterrupted value, with no committed child started twice, and refused before any launch after a declared file changes |

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
| R4 | `provider.prompt_content` | Assembled in this order: the tagged prompt extern source or the rendered `defprompt` template; the typed prompt inputs; the prompt dependencies, at the position the declaration gives; the output contract block, rendered by the runtime's own renderer |
| R5 | `ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY`, in the provider's environment overlay | `sha256:` and the digest of the identity's canonical text. The same across attempts and resumes, present inside call frames as well; the present route sends none inside a call frame |
| R6 | `provider.cwd` | The workspace, named. The present route inherits the orchestrator's working directory |
| R7 | `provider_call_policy` and `timeout_sec` | The effect node's policy: `model`, `effort`, `timeout_sec` |
| R8 | `params`, `session_request`, `provider_session_dir`, `provider_session_identity`, `secrets` | The parameters the effect node declares; none of the others in the first release (§1.1) |
| R9 | `command.command` | The stable command tokens, the interpreter replaced by its resolved path (C3), then the rendered argv (§9.1), then for a certified adapter the input document |
| R10 | `command.env` | R2 and `PYTHONDONTWRITEBYTECODE=1` (C4) |
| R11 | Generated helper commands | None. The present route runs inline Python steps that write managed write roots under `.orchestrate/workflow_lisp/`; the model has no write roots and no call frames, so nothing writes them |
| R12 | A value in a command argument | Rendered as §9.1 states; equal to the present route's bytes |

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
| V9 | `state.json` is an atomically replaced derived view after each synchronized record, with the header keys `schema_version`, `run_id`, `workflow_file`, `workflow_checksum`, `started_at`, `updated_at`, `status`, plus `error`, `workflow_outputs`, `bound_inputs` and effect rows. Its schema/profile discriminant routes readers to the adapters below; writing old header keys alone does not establish compatibility |

The view records the complete journal byte offset it represents. Concurrent
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
| `workflow_input_missing`, `workflow_input_unknown`, `workflow_input_invalid` | Before the run root holds a record (§5) |
| `resume_program_changed`, `resume_inputs_changed`, `resume_interpreter_missing` | At resume, before any record is read (§8.4, C3) |
| `interpreter_changed` | A diagnostic, not a refusal, at resume (C3) |
| `memo_busy` | A second writer (M1, C8) |
| `memo_inconsistent` | Missing authority with journal activity (§8.4), an invalid range anchor/suffix (C8), or memo/terminal checks failing (V3) |
| `effect_input_diverged` | At the first committed effect whose input differs, or before retrying an uncommitted command whose implementation evidence differs from `started` (§8.1) |
| `effect_rerun` | A diagnostic in the run's result and the view, naming the identity and its earlier attempts (§8.1) |
| `lexical_restore_pending_effect_unsafe` | An uncommitted attempt of a `must_not_repeat` boundary (§8.1); the present code, kept |
| `effect_attempt_path_exists` | Exclusive allocation collides after the ordinal's synchronized `started`; append `failed`, preserve the directory, launch nothing (§8.2) |
| `invalidate_not_committed`, `invalidate_coordinator_committed` | The explicit continuation (C8) |
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
| Structured inputs | A command receives a candidate record and the list of earlier trials, with their types, and rejects a document of another shape | Open: typed input documents are Phase 3 of the plan (§9.1) |
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
