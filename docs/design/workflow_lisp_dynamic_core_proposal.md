# Workflow Lisp: Dynamic Core With Explicit Boundary Contracts

- **Status:** candidate selected for evaluation; adoption undecided and implementation absent.
- **Kind:** architecture proposal, not an accepted language specification or implementation plan.
- **Scope:** ordinary computation, callable values, boundary schemas, and the execution contracts those changes would require.
- **Authority:** current behavior remains defined by the [frontend specification](workflow_lisp_frontend_specification.md), [capability matrix](../capability_status_matrix.md), and applicable `specs/` contracts. This proposal does not change an accepted target's semantics.
- **Plan:** the [dynamic-core evaluation plan](../plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md) owns qualification, bounded experiments, decision gates and changes to prospective delivery. Selection for evaluation is not production adoption.

## 1. Recommendation

Use a small dynamically typed lexical language: ordinary functions and closures,
booleans, immutable records, lists, maps, and scalars. Require reusable schemas at
provider, command, and public workflow boundaries. One schema generates agent
output instructions, strict validation, and the records ordinary code consumes.
Internal helpers need no type parameters, nominal wrappers, or compile-time refs.

The tradeoff is simpler composition with less early error detection and harder
recovery with runtime functions. Recommend evaluation against the proof
obligations below; a shorter example alone does not justify adoption.

Use booleans for binary decisions and tagged alternatives for distinct payloads:
blocked, exhausted, and approved are not synonyms for false and true. Dynamic
computation is not permission to trust malformed agent output.

## 2. Problem And Existing Alternatives

The current [type system, §7](workflow_lisp_frontend_specification.md#7-types)
checks records, union access, generic constraints, and callable signatures.
`ProcRef` is specialized away before executable IR. Existing `Value` is an exact,
opaque strict-JSON transport type: it grants no field access, arithmetic, or
collection operations and does not implicitly interoperate with narrower types.
Changing every annotation to `Value` would therefore not produce this language.

[Principle 29](workflow_language_design_principles.md#29-types-are-opt-in-constraints-not-mandatory-taxonomies)
already favors optional constraints over mandatory taxonomies. This proposal
takes that direction further than current rules permit. Principles 11–12 and 21
would need an explicit amendment: internal structural substitution and runtime
field/tag checks replace some static narrowing, variant proof, and signature
requirements. Boundary validation and contract identity remain mandatory.

The accepted [evaluated execution design, §§3–9](workflow_lisp_evaluated_execution.md#3-goals-and-non-goals)
removes positional lowering restrictions while preserving static typing. Its
closed program requires specialized definitions, type consistency throughout
P5, no runtime procedure values, and termination through nonrecursive calls and
bounded loops. Static closure of the code inventory is separable from static
typing, but that separation is a substantive redesign of this checked IR.

| Candidate | Benefit | Cost and limit |
| --- | --- | --- |
| Incumbent plus evaluated execution and W1/W3 | Removes positional failures, repeated constructor names, and explicit hook context forwarding while retaining static diagnostics. | Keeps nominal identities, generic specialization, expected-type inference, and compile-time reference machinery. Lowest migration risk. |
| Small dynamic core plus boundary schemas | Functions compose uniformly; internal state and helpers need no nominal taxonomy. Potentially deletes several compiler subsystems. | More failures occur on executed paths; closure identity, admission, budgets, and replay need new proofs. Recommended candidate. |
| Embed full Scheme | Starts with established lexical functions and a general-purpose language implementation. | Requires an enforceable restriction of host I/O, mutation, evaluation, continuations, and library loading, plus durable-effect integration. Language implementation reuse does not prove orchestration simplicity. |

[Writing Each Fact Once](workflow_lisp_write_once.md) remains a serious control:
W1 removes repeated constructor type names; W3 removes context-only records and
`inputs I`; W2/W4 simplify effects and provider options independently; W5 adds
constraint inference only where a real caller needs it. Credit those gains to
the incumbent before attributing all improvements to dynamic typing.
Use the best executable typed control; label unimplemented W1/W3 rewrites as
counterfactual evidence, without requiring both candidates to ship first. Keep
useful domain types and schemas in the comparison. Simpler binary decisions
already expressible with booleans are not a unique gain of the dynamic core.

Scheme supplies a precedent for lexical scope and first-class procedures
in a dynamic language, not a compatibility requirement
([R7RS introduction](https://standards.scheme.org/r7rs-html5/index.html)).
Choose a bounded workflow runtime. The engine choice remains open; an existing
interpreter qualifies only if its restricted embedding is demonstrably smaller.

## 3. Candidate Language And Boundary Model

All syntax below is illustrative and unavailable in current `.orc` targets.
Keep the existing module/import and effect vocabulary where they fit; do not add
a second public launch API or hide a new evaluator inside old typed lowering.

| Surface | Candidate rule |
| --- | --- |
| Values | Null, strict booleans, integers, finite numbers, strings, lists, string-keyed maps, records, and internal callable values. Preserve established numeric semantics unless separately revised. |
| Functions | Lexical `fn` and named definitions; ordinary application, capture, return, and passage through internal collections. One function body serves different compatible values without monomorphization. |
| Control | Strict boolean `if`, short-circuit boolean operators, sequencing, and explicit bounded iteration. Other values are not implicitly truthy. |
| Records | Immutable named-field products; local construction needs no declaration. Missing field access fails at its source location. Functional updates produce new records. |
| Maps | Explicit key lookup with an explicit missing-key policy; records do not silently return null for misspelled fields. |
| Schemas | Statically declared reusable data contracts, referenced by boundary declarations; no runtime schema synthesis or gradual static type system. |
| Effects | Only registered operations with linked provider/command bindings and declared contracts. An ordinary function may invoke these operations. |

Ordinary records carry fields, not schema evidence. Contracted records use the
same immutable representation after validation, associated with the boundary's
schema identity in the committed result. No second runtime class hierarchy or
permanent internal typechecker is required.

Local constructors and updates check basic record formation, not every possible
schema. Updating a validated record does not confer validation on the new value.
Every provider/command input and public entry/return is checked against its
declared schema; provider/command outputs are checked before commit and exposure.
Explicit local validation is available by calling the same validator when useful.
No implicit coercion, repeated JSON parsing at each field access, or mutable
alias can turn a previously checked external value into different committed data.

Public boundaries must declare a schema, but it may deliberately accept generic
strict-JSON data where shape does not matter. This is an explicit weak contract,
not an inferred schema or the current opaque source type `Value`. Closures,
host objects, cycles, and non-finite numbers cannot cross data boundaries.

Candidate schema defaults are closed fields and strict scalar/list validation:
missing or extra fields fail; null is valid only when declared; a string is not
coerced to a boolean or number. Tagged schemas validate their active payload and
reject inactive fields. These defaults strengthen some current wire checks:
older union boundaries permit unrelated extra keys, and some numeric channels
coerce values. Such changes require a versioned contract and migration evidence,
not retroactive claims that existing boundaries already behave this way.

## 4. Instructions Become Ordinary Values

For a two-way review whose outcomes share a payload, a boolean is enough.
Current ORC already supports boolean records and `if`; that choice does not need
this redesign. The subtraction proposed here concerns internal helper typing and
specialization, while boundary schemas preserve the existing contract connection.
This conceptual before/after has one review and at most one revision;
`accept` and `revise` are surrounding application functions with the same behavior
in both versions. It is not a replacement for the full `std/improve` protocol.

```lisp
;; Current conceptual fragment: two variants, each carrying the same feedback.
(defunion Review
  (APPROVE (feedback String))
  (REVISE (feedback String)))
(defprompt review-prompt (:fills (draft :text)) -> Review
  "Approve if no blocking defects remain; otherwise request revision. Draft: {draft}")
(let* ((review (provider-result providers.review
                :prompt (review-prompt :draft draft))))
  (match review
    ((APPROVE r) (accept draft r.feedback))
    ((REVISE r) (revise draft r.feedback))))

;; Proposed fragment: one contract declaration, ordinary boolean consumption.
(defschema Review (record (approved Bool) (feedback String)))
(defprompt review-prompt (:fills (draft :text)) -> Review
  "Set approved true if no blocking defects remain; explain your judgment. Draft: {draft}")
(let* ((review (provider-result providers.review
                :prompt (review-prompt :draft draft))))
  (if review.approved
      (accept draft review.feedback)
      (revise draft review.feedback)))
```

The schema describes shape; prose describes judgment. Derive instructions and
validation from `Review`. Existing transport delivers/materializes the result at
its runtime-owned destination, including the registered `omp_json_stdout` parent
materialization route. Validate, commit, and return the record; no handwritten
JSON schema or parser, or arbitrary stdout result channel, is introduced.

| Answer or failure | Candidate behavior before any consumer sees `review` |
| --- | --- |
| `{"approved":true,"feedback":"Ready"}` | Return a record with a boolean and string. |
| `{"approved":"false","feedback":"Fix tests"}` | Reject `/approved`; never route using string truthiness. |
| `{"approved":false}` | Reject missing `/feedback`. |
| `{"approved":false,"feedback":7}` | Reject the field type. |
| Valid fields plus `"debug":"x"` | Reject the undeclared field under this candidate's closed schema. |
| Malformed JSON, a missing bundle, or a write at another path | Fail the boundary; expose no result and retain failure evidence. |

Lists validate every element. Schema success does not prove that an agent's
judgment is correct; it proves the declared data contract. Invalid output is an
effect failure, never an implicit `false`, approval, or domain-level blocked
result. Any repair policy must be explicitly authored through supported recovery.

### Preserve the prompt's document and output roles

Preserve the [showcase's](../../experiments/orc_vs_python_showcase/README.md) prompt/file connection:

```lisp
;; Proposed schemas; the delivery roles retain their existing meaning.
(defschema DesignDoc (relpath :under "docs" :must-exist true))
(defschema ReportTarget (relpath :under "artifacts/review" :must-exist false))
(defprompt review-design
  (:fills (doc :doc DesignDoc)
          (checks :value (List String))
          (report :path :out ReportTarget))
  -> Review
  "Review the injected document against {checks}; write the report to {report}.")
```

`:doc` still delivers the required document through the dependency snapshot;
`:value` renders canonical data; `:path :out` derives both the rendered path and
its required UTF-8 file postcondition from one fill. Validate dynamic fill values
before launch. Preserve duplicate/alias checks and the runtime-owned bundle path.
Validate the report and structured result together before publishing either map,
without claiming rollback of provider-written files. Compatible completed reuse
returns committed results without reopening the output file. Neither `:out` nor
`:doc` establishes freshness, authorship, or `consumes`/`publishes` lineage.

## 5. Ordinary Generic Helpers, Without Losing Domain Outcomes

The real [std/improve source](../../orchestrator/workflow_lisp/stdlib_modules/std/improve.orc)
declares four type parameters, compile-time hook signatures, `inputs I`, and
`S is-record`, although its body does not inspect fields of `S`. The latter is a
candidate representation restriction to remove, subject to caller evidence.

An ordinary dynamic helper could have this signature and retain its full policy:

```lisp
(define (improve initial review revise limit) ...)
(improve draft
  (fn (current) (review-for-improvement current checks report-target))
  (fn (current feedback) (revise-draft current feedback requirements))
  3)
```

The two surrounding application functions implement the hooks below; the closures
capture caller values. `improve` needs no context record, `ProcRef`, `:forall`,
`bind-proc`, or special compiler rule. This is composition syntax, not an
executable port or measured reduction. Preserve the full iteration policy:

| Review decision | Full helper behavior |
| --- | --- |
| `APPROVE(evidence)` | Return `APPROVED(value, evidence)` without revision. |
| `REVISE(feedback)` | Invoke revision, then use that returned value for the next iteration. |
| `BLOCKED(reason)` | Return `BLOCKED(value, reason)` without revision. |
| Limit reached | Return `EXHAUSTED(value)` with the latest value; never imply approval. |

Use tagged records for this protocol. Provider-facing variants have explicit
schemas; internal hooks must meet the helper's runtime protocol checks. Unknown
tags or missing payload fields fail explicitly. Dynamic `match` can require an
explicit fallback, but cannot claim the incumbent's compile-time exhaustiveness
or proof-based field access without reintroducing static analysis.

## 6. Closed Code, Dynamic Calls, Durable Effects

The proposed architecture has one path:

```text
source + linked definitions + schemas + registered effect bindings
  -> checked closed program with lexical functions and effect sites
  -> bounded evaluator + effect memo
  -> existing effect performers/coordinators and shared boundary validation
```

Keep one closed inventory of executable bodies, schema contracts, and effect
bindings before launch. Runtime selection may choose among those functions;
agent output cannot create a body, host function, provider binding, or command.
No dynamic `eval`, arbitrary imports, unknown effect hosts, or Python-function
serialization is admitted. Passing a closure across an internal function call
is allowed; passing one to a provider, command, child run, or public result is not.

Represent a closure with a program-owned lexical code identifier and immutable
captures, including admitted closures; never a serialized Python callable.
Exclude mutable captured cells and cyclic data graphs. A closure can survive
an effect in memory, including one capturing a committed provider result.
Proving reconstruction and invocation after restart is mandatory.

Candidate identity extends the accepted definition/site and activation-path
model: each dynamic invocation frame records its lexical call site and actual
selected code identifier; loops contribute iteration indexes. Captured values
flow into resolved effect inputs where used, rather than defining effect sites.
No address, source span, or wall-clock value enters identity. Runtime calls need
frames even where their effects cannot be established statically. The exact
canonical form, repeated invocation disambiguation, and stability under harmless
edits are unproven. In particular, do not promise that insertion of an apparently
pure call leaves anonymous identities unchanged without an effect analysis.

Retain entry reevaluation with memoized effects as the checkpoint strategy;
do not serialize the environment or invent a second state authority. Replay
reconstructs local records and closures from pinned code, inputs, and committed
values. A committed compatible effect is reused; divergence stops before launch;
an interrupted uncommitted effect follows its repeat policy, including
`must_not_repeat`. No claim of exactly-once external execution follows.

P5 must be replaced for this profile, not disabled: scope, lexical code targets,
effect-site bijection, declared schemas, valid payloads, linked effect classes,
and artifact/version integrity remain checked at build and artifact read. Whole
program value-type consistency, statically resolved callees, and generic
specialization no longer describe the accepted representation.

Dynamic self-application defeats a direct-call acyclicity check even without a
recursive declaration. Candidate policy therefore uses a deterministic evaluation
step budget pinned with the program/run configuration, as well as explicit loop
limits. Charge calls and reevaluation, including memo hits; effects do not reset
the budget. Resume from entry must consume the same prefix budget and cannot
evade exhaustion by restarting. Exact accounting, practical limits, diagnostic
behavior, and interruption safety are adoption-blocking proofs. This changes
the accepted evaluator's no-budget termination argument.

There is no automatic static purity guarantee for function parameters. The closed
operation vocabulary and dispatcher enforce effect authority; read-only contexts
reject effects before dispatch. Inventory any consumers requiring static purity
rather than silently recreating the old effect/type system.

## 7. Errors, Owners, And Deletions

| Check | Candidate timing and consequence |
| --- | --- |
| Syntax, unbound lexical names, missing imports, unknown effect classes, malformed schemas, prompt slot declarations | Build/artifact admission; these need no whole-program static typing. |
| Wrong dynamic argument count, non-callable application, wrong primitive operand, missing record field, non-boolean condition | Runtime at the source expression, before dispatch if it occurs while preparing that effect. An earlier effect may already have cost money. |
| External input/result shape, path safety, required output, schema identity | Validate at the declared boundary; reject before launch or before commit as appropriate. |
| Unhandled tag or changed internal helper protocol | Executed branch/helper runtime check; no universal exhaustive-match promise. |
| Changed program, schema, inputs, declared implementation bytes, or incompatible journal | Refuse incompatible reuse according to the owning versioned recovery contract. |

An editor retains syntax/name/declaration checks, not former type guarantees.
Runtime diagnostics name the expression, expected operation/schema, actual value
kind, and call/effect context without exposing secrets. A latent branch typo
after an expensive agent call is a real regression risk.

| Owner | Retain or revise | Displaced responsibility to delete on migration |
| --- | --- | --- |
| Frontend and closed-program checker | Names, modules, schemas, source maps, closed admission, lexical code/site identity | Internal nominal unification, generic specialization, `ProcRef`/`bind-proc` specialization and capture forwarding machinery, static variant-proof plumbing. |
| Shared boundary validator and prompt compiler | One reusable schema authority, generated instructions, input rendering, `:doc`/`:out`, strict decoding | Parallel handwritten JSON schema, parser, or postcondition implementations; do not introduce them. |
| Evaluator and memo owner | Runtime value operations, callable frames, deterministic budget, recovery | Static-call-only assumptions and type-driven environment/call projections for the new profile. |
| Existing performer/coordinator owners | Provider transport, command execution, run references, isolation, settlement, artifacts | No replacement orchestration backend, state shim, or report-as-state adapter. |
| Stdlib and consumers | Ordinary helpers with domain protocols and boundary schemas | Context-only records, redundant internal type declarations, nominal conversion adapters proven unnecessary by migrated callers. |

These are deletion obligations, not proven savings. Count old-target code and new
machinery too. Reject a permanent dynamic facade over equivalent new-target
compiler paths or silent specialization back into the incumbent model.

## 8. Compatibility And Evidence Required Before Adoption

The [existing delivery plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#delivery-order-and-preserved-capabilities)
provides useful composition, memo, performer, and caller evidence. Its Phase 4c
W3 hooks remain compile-time references. Command implementation closure evidence
pins files; it does not prove lexical function closures. Reusing the typed
compiler or evaluator does not establish dynamic calls, replacement P5 admission,
or this schema/budget model.

The [evaluation plan](../plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md)
owns gates **DC-F** (feasibility), **DC-U** (utility) and **DC-P** (production
readiness and migration), their order and owner dispositions. The obligations
below distinguish mechanism proof, complete consumer benefit and production
qualification: passing one supplies no automatic approval of the others.

Adoption would need a distinct target and program representation version, an
inventory of maintained callers/imports, and explicit contract-owner amendments.
Existing runs remain pinned to their original compiler/program/state semantics;
never reinterpret old checkpoints as dynamic environments or loosen saved
schemas. Old-target compatibility has a real maintenance cost and needs a
retirement policy before claiming net deletion. No new live-run conversion or
automatic schema migration is proposed.

Preserve [IO](../../specs/io.md), [provider](../../specs/providers.md),
[state](../../specs/state.md), [dependency](../../specs/dependencies.md), and
[security](../../specs/security.md) guarantees through their existing owners:
validated-before-commit results, artifact lineage/freshness, snapshots, path
containment, secret handling, and coordinator settlement. Current `state.json`
authority and the accepted evaluated target's memo authority remain distinct
versioned profiles. Dynamic records grant neither filesystem authority nor a
sandbox for subprocesses.

| Required evidence | What would qualify the candidate |
| --- | --- |
| Full `improve` parity | Preserve [existing behavioral checks](../../tests/test_workflow_lisp_improve_stdlib.py): approval, blocked and exhaustion values; invalid hook output rejected before consumption; final-iteration revision failure remains failure; zero limit remains rejected before any hook; imported/inline order agrees; committed hooks do not replay. Use matched policy, boundary contracts and recovery obligations; credit W1/W3 as qualified in §2. Replace selected-hook effect-summary guarantees explicitly, not silently. |
| MLEvolve behavior | Port the policy in [search_compact.orc](../../experiments/mlevolve_pair/search_compact.orc) against the [paired-search rules](../../experiments/mlevolve_pair/README.md): seed ranking, strict improvement, ties, invalid evaluation, one repair on the same branch, stalls, one fusion, complete trial history, budget/score stops, invalid budget, and loop exhaustion. Distinguish schema-invalid transport from a valid `valid=false` evaluation. |
| Authoring and diagnostics | Paired edits adding a state field, changing review payload, capturing context, and extracting a helper; count concepts, duplicated facts, touched sites, repair effort, and errors detected before the first paid effect. Report lost static detections and the cost of effects already performed before a later error. |
| Boundary integration | Generated instructions and validation agree; strict booleans, nested lists, unknown fields, missing/wrong-path bundles, document snapshots, required reports, path escapes, atomic publication and lineage checks preserve their declared contracts. |
| Closure and recovery proof | Create/return/store/pass closures, choose one from committed data, capture a committed value, interrupt before/after another commit, and resume. Equal traces must reuse committed effects; changed schema/program/input or declared-file bytes must refuse divergent reuse. Cover coordinators and unsafe pending effects when admitted. |
| Closed-program and budget proof | Reject forged code references, undeclared hosts, invalid schema/site tables, nontransportable public values, and self-application exceeding its deterministic budget. Establish artifact read-back and replay accounting independently of compiler generation. |
| Total complexity | Count deleted and retained modules, specialization paths, identity forms, validators, state authorities, compatibility routes, and tests, alongside new runtime responsibilities; source LOC alone cannot establish simplification. |
| Production qualification | Resolve target/program/profile versions, imports, stdlib replacement and existing-run disposition. Qualify public execution, recovery, operational readers, artifacts and admitted coordinators through the existing owners. Identify one maintained-consumer destination and deletions; experimental parity alone does not authorize migration or retirement. |

The paired search uses scripted leaves; its Python controller lacks matching
durable recovery. Existing spike evidence supports evaluated execution, not
runtime closures. Establish behavior with deterministic fixtures first; any later
live comparison must separate authoring, model quality/cost, and recovery claims.

No prototype or tests accompany this proposal. Closure/site identity, budget and
replay, schema compatibility, owner amendments, and net deletion remain adoption
prerequisites. Retain the incumbent if those costs exceed the gain over W1/W3.
