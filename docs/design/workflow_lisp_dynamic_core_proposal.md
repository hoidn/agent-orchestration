# Workflow Lisp: Dynamic Core With Explicit Boundary Contracts

- **Status:** accepted bounded branch-qualified target-3.0 architecture in §9; broader proposal/historical spike sections remain contextual. Full readiness and adoption are open; evidence and decisions belong to the linked plan/report.
- **Kind:** architecture companion and decision record. Normative delivered profile contracts live in specs; this is not a release/adoption or implementation-status authority.
- **Scope:** ordinary computation, callable values, boundary schemas, and the execution contracts those changes would require.
- **Authority:** current behavior remains defined by the [frontend specification](workflow_lisp_frontend_specification.md), [capability matrix](../capability_status_matrix.md), and applicable `specs/` contracts. This proposal does not change an accepted target's semantics.
- **Plan:** the [dynamic-core evaluation plan](../plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md) owns qualification, bounded experiments, decision gates and changes to prospective delivery. Selection for evaluation is not production adoption.

## 1. Recommendation

Use a small dynamically typed lexical language: ordinary functions and closures,
booleans, immutable records, lists, maps, and scalars. Require reusable schemas at
provider, command, and public workflow boundaries. One schema generates agent
output instructions, strict validation, and the records ordinary code consumes.
Internal helpers need no type parameters, nominal wrappers, or compile-time refs.

Retain most of the existing type-to-contract machinery: `defrecord`, `defunion`,
`defpath` and their reusable declarations describe boundary data; the existing
compiler derives prompt guidance, input rendering, result contracts, validation
and transport. Ordinary high-level composition becomes dynamic. This is not a
proposal for a parallel schema language, contract compiler or validator.

The tradeoff is simpler composition with less early error detection and, for
the minimum candidate, no effect analysis or resumable execution. The owner
accepts losing effect tracking and resumability when other advantages offset
the cost. Evaluate that tradeoff explicitly; a shorter example alone does not
justify adoption. Boundary contracts and actual agent/command execution remain
required.

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
| Small dynamic core plus boundary schemas | Functions compose uniformly; internal state and helpers need no nominal taxonomy. Potentially deletes several compiler subsystems. | More failures occur on executed paths; the minimum candidate restarts from entry and may repeat earlier effects/costs. Admission and bounded execution still need proof. Recommended candidate. |
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

The conceptual syntax below is illustrative, not a complete runnable consumer.
Section 9 owns the accepted branch-qualified profile; use the
[actual guide examples](../lisp_workflow_drafting_guide.md#2b-dynamic-composition-on-the-qualified-branch)
for implemented source forms, bindings and reproduction.
Keep the existing module/import and effect vocabulary where they fit; do not add
a second public launch API or hide a new evaluator inside old typed lowering.

| Surface | Candidate rule |
| --- | --- |
| Values | Null, strict booleans, integers, finite numbers, strings, lists, string-keyed maps, records, and internal callable values. Preserve established numeric semantics unless separately revised. |
| Functions | Lexical `fn` and named definitions; ordinary application, capture, return, and passage through internal collections. One function body serves different compatible values without monomorphization. |
| Control | Strict boolean `if`, short-circuit boolean operators, sequencing, and explicit bounded iteration. Other values are not implicitly truthy. |
| Records | Immutable named-field products; local construction needs no declaration. Missing field access fails at its source location. Functional updates produce new records. |
| Maps | Explicit key lookup with an explicit missing-key policy; records do not silently return null for misspelled fields. |
| Schemas | Reuse existing type declarations as statically declared boundary data contracts; no new `defschema` syntax, runtime schema synthesis or gradual static type system. |
| Effects | Only registered operations with linked provider/command bindings and declared contracts. An ordinary function may invoke these operations. |

Ordinary records carry fields, not schema evidence. Contracted records use the
same immutable representation after validation, associated with the boundary's
schema identity at its validated boundary. No second runtime class hierarchy or
permanent internal typechecker is required.

Local constructors and updates check basic record formation, not every possible
schema. Updating a validated record does not confer validation on the new value.
Every provider/command input and public entry/return is checked against its
declared schema; provider/command outputs are checked before publication and exposure.
Explicit local validation is available by calling the same validator when useful.
No implicit coercion, repeated JSON parsing at each field access, or mutable
alias can turn a previously checked external value into different accepted data.

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
(defrecord Review (approved Bool) (feedback String))
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
materialization route. Validate, publish, and return the record; no handwritten
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
result. Any repair or retry policy must be explicitly authored through supported
boundary behavior; a fresh restart is not a recovered execution.

### Preserve the prompt's document and output roles

Preserve the [showcase's](../../experiments/orc_vs_python_showcase/README.md) prompt/file connection:

```lisp
;; Existing boundary declarations and delivery roles are retained.
(defpath DesignDoc :kind relpath :under "docs" :must-exist true)
(defpath ReportTarget :kind relpath :under "artifacts/review" :must-exist false)
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
without claiming rollback of provider-written files. The minimum candidate
offers no completed-effect reuse: a new execution validates its newly obtained
outputs. Neither `:out` nor
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

## 6. Closed Code, Dynamic Calls, And Effects

The proposed architecture has one path:

```text
source + linked definitions + schemas + registered effect bindings
  -> checked closed program with lexical functions and registered effect bindings
  -> bounded evaluator with ordinary calls and fresh execution
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
Exclude mutable captured cells and cyclic data graphs. A closure survives an
effect in memory, including one capturing a validated provider result. Ordinary
capture/pass/selection after actual effects remains a feasibility obligation.

The minimum candidate has no effect memo, checkpoint reconstruction or `resume`.
A fresh invocation starts at entry with fresh inputs and its full step budget;
earlier external effects may execute again. Do not silently resume a stopped
candidate, adopt leftover output files, or describe a fresh run as recovery.
Within an invocation, honor registered operations' existing retry rules. A fresh
restart has no cross-run no-repeat guarantee; retained typed runs still own
their existing recovery contract. No exactly-once or automatic rollback claim
follows.

Call context and optional effect traces serve diagnostics and comparison only.
They do not establish static effect summaries, dependency tracking, replay-site
identity or a durable state authority. Report lost early checks and repeated
work/cost beside composition gains. A resumable candidate would need a separate
consumer justification and reviewed shared integration; it is not a prerequisite
for feasibility, utility or adoption of this minimum candidate.

P5 must be replaced for this profile, not disabled: scope, lexical code targets,
declared schemas, valid payloads, linked effect classes,
and artifact/version integrity remain checked at build and artifact read. Whole
program value-type consistency, statically resolved callees, and generic
specialization no longer describe the accepted representation.

Dynamic self-application defeats a direct-call acyclicity check even without a
recursive declaration. Candidate policy therefore uses a deterministic evaluation
step budget pinned with the program/run configuration, as well as explicit loop
limits. Charge calls and evaluated operands; effects do not reset the budget
within an invocation. A deliberately fresh invocation gets a fresh budget;
there is no cross-run budget/replay guarantee. Exact accounting, practical
limits and diagnostics still need proof. This changes the accepted typed
evaluator's no-budget termination argument.

There is no automatic static purity guarantee for function parameters. The closed
operation vocabulary and dispatcher enforce effect authority. If a read-only
execution context is offered, it rejects effects before dispatch; losing static
tracking does not authorize effects from such a context. Inventory consumers
requiring static purity and report the unsupported guarantee rather than
silently recreating the old effect/type system.

### 6.1 Bounded Pure Mechanism Contract

This experimental subprofile qualifies lexical values and checked admission
independently of effect integration. It is not a production target, `.orc`
frontend or evidence of authoring ergonomics. The [evaluation plan](../plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md)
owns its finite cases and later admission; actual effect/boundary obligations above
remain unsatisfied by pure execution.

**Artifact.** Accept strict JSON text with exactly these top-level fields:

```text
schema      = "workflow-lisp/dynamic-spike/1"
entry       = code identifier
budget      = positive integer, excluding Bool
schemas     = {schema identifier: existing normalized transport descriptor}
inputs      = [[parameter name, schema identifier], ...]
result      = schema identifier
definitions = {code identifier: {params: [name, ...], captures: [name, ...], body: node}}
```

Identifiers and binders are nonempty strings. Duplicate JSON keys, unknown keys,
non-finite numbers, malformed rows and references outside the closed tables are
refused. The entry's ordered parameters equal `inputs` names and it has no
captures. Parameter/capture names are unique and disjoint. Validate every body
and schema, including unreachable ones, before evaluation. Nodes have exactly
`k` plus the fields in this table; child evaluation is left-to-right:

| `k` | Fields and meaning |
| --- | --- |
| `lit` | `v`: null, Bool, Int, finite Float or String; no aggregate/code object disguised as a literal |
| `name` | `n`: a lexically bound name |
| `let` | `bindings`: ordered `[name, node]` pairs; `body`: node. Sequential `let*` scope, unique names in this binding list; nested scopes may shadow outer names |
| `fn` | `code`: declared code identifier; `captures`: nodes aligned with that definition's capture names |
| `call` | `callee`: node yielding a closure; `args`: nodes. Evaluate callee then all arguments left-to-right, then check callable/arity before entering the body |
| `if` | `cond`, `then`, `else`: nodes; require an actual Bool and evaluate only the selected arm |
| `record` | `fields`: ordered `[nonempty field name, node]` pairs with unique names |
| `field` | `base`: node; `name`: nonempty field name; require a record/map and that field |
| `list` | `items`: nodes; internal lists may contain closures |
| `at` | `base`, `index`: nodes; require a list and an actual nonnegative Int less than its length |
| `op` | `name`: admitted primitive; `args`: nodes |

The primitive set is `+`, `-`, `*`, `/`, `<`, `<=`, `>`, `>=`, `=`, `!=`,
`not`, `string/concat`, and `string/empty?`. Check catalog arity, then derive
primitive operand descriptors from actual scalar kinds and call the existing
`pure_expr.evaluate_pure_operator`; do not duplicate arithmetic or infer generic
signatures. Preserve its mixed-type refusals, signed-64-bit arithmetic,
division and Float-equality rules. Candidate Int formation uses the existing
`coerce_pure_value` Int check, including integers nested in input data; Float
formation refuses non-finite values. Record/list operations need no nominal
descriptor. Loops, maps with computed keys, updates, other primitives, source
imports and effects are outside this first subprofile, not silently supported.

**Admission and representation.** A definition body sees only its declared
parameters/captures and local binders. Check each `fn` code and capture count;
its capture expressions are checked in the creation scope. Do not statically
type internal values or resolve a dynamic call's callee. Cycles among code
references are allowed: self-application is bounded by evaluation, not a static
call-graph ban. Cyclic syntax/data containers and host objects are not admitted.
Catch parser/traversal recursion limits as an admission refusal; never mistake
them for the runtime's budget proof.

Store an immutable snapshot of the checked artifact and values, using tuples
and read-only mappings. A closure is only `(code identifier, immutable capture
values)`; creating it evaluates each capture once. Invocation binds those
values plus arguments, with no caller-environment fallback or mutable cells.
Closures can be captured by other closures without introducing cyclic values.
Input snapshots and captured records cannot be changed through caller aliases.
Canonical serialization includes budget and all schema/code bytes; reuse
`closed.program.canonical_digest`, not the typed-AST `program_digest` walker.
There is no source provenance field in this subprofile. Whitespace, JSON object
key order and file location do not alter its digest; semantic edits may.

**Budget and diagnostics.** Debit one step immediately before evaluating every
node, including literals, names, closure creation, calls and each evaluated
operand. A budget of N admits N node entries and refuses entry N+1. A call body
consumes ordinary node steps; returning a value adds none. Unselected branches
consume no steps. Use an iterative work stack so Python recursion exhaustion
cannot substitute for the deterministic budget. Every independent evaluation
starts with the pinned budget; this proves repeatability, not restart/replay.

Errors use `EvaluatedValueError` with an RFC 6901 artifact expression pointer as location:
`dynamic_spike_invalid` for admission, `dynamic_boundary_invalid` for entry/return
validation, `dynamic_not_callable`, `dynamic_call_arity`,
`dynamic_condition_type`, `dynamic_field_missing`, `dynamic_index_invalid`,
`dynamic_operand_type`, and `dynamic_budget_exhausted` for runtime failures.
Retain existing pure-catalog error codes for arithmetic failures. Include the
current call context; do not expose raw boundary values in diagnostics.

**Identity scope.** A pure invocation frame is `(caller code, expression pointer
within that body, selected code)`, appended to the parent activation. Recursive
invocations remain distinct by the full activation path. Capture values do not
name code; filenames, spans, addresses and clocks do not enter frames. Derived
call traces may be inspected in tests but are not state authority. This fixes
pure call-context identity only; it is not a journal/replay identity contract.
It supplies no promise that inserting an
expression preserves existing anonymous identities.

**Boundary reuse.** `schemas` contains the existing normalized descriptors,
not a second schema format. Admit only primitive Bool/Int/Float/String/Value,
enum, optional, list, string-keyed map, record and union descriptors, recursively
checked by `type_descriptor.validate_compiler_normalized_type_descriptor`.
Use `validate_transport_value(..., allow_nested_structures=True)` on ordinary
JSON data before entry and after return; never use the string-coercing
`output_contract.validate_contract_value` as the strict gate. This existing
kernel rejects wrong Bool/string scalars, missing/extra and inactive fields,
cycles and host objects. Float accepts an Int and normalizes it to Float;
strings and Bools never become numbers. Closures fail every data boundary.
Reject missing/extra entry arguments. Apply declared-schema normalization before
dynamic value formation and freezing: an integer `2**63` at a Float input becomes
a finite Float, whereas the same input under Int or Value remains an integer
and fails this subprofile's Int64 formation check. On return, thaw data and
validate/normalize against the declared result schema. Under
`dynamic_boundary_invalid`, retain the shared validator's complete safe
diagnostic, including its field path, without exposing the rejected leaf value.
Keep the artifact location structured; do not infer a separate field-path API
by splitting the validator's diagnostic prose, since field names can contain
the same words as error messages.
Path descriptors are refused in this subprofile: the shared kernel without a
path-owner callback checks only that a path is a string, not containment or
existence. No path-safety, document/output or provider claim follows.

For later authored boundaries retain `contracts.derive_structured_result_contract`
and `derive_prompt_guided_structured_result_contract`,
`type_descriptor.transport_schema_for_descriptor`/`compiled_boundary_rows`,
`typed_prompt_inputs` rendering, and the existing output-contract/path owners.
`defprompt` guidance and `:doc`/`:path :out` roles continue to derive from those
same declarations. The pure fixture's normalized descriptors are a mechanism
input; hand-authoring JSON is not the replacement authoring experience.

**Shared integration boundary.** The typed `ClosedProgram`/`RunAuthority` and
memo do not admit this artifact, and the minimum candidate does not need to
adapt or use them. Reuse the existing command/provider dispatch, request,
validation, path/sandbox and output owners, including reviewed upstream
improvements, through the smallest agreed call boundary. Do not make typed
Task 8 or a dynamic memo/site bridge a prerequisite. Missing shared performer
capability belongs with its upstream owner, not a duplicate local performer.
Do not fabricate typed artifacts, synthesize successful journal records, or use
a test callback as evidence of an actual provider/command boundary. Ordinary
`.orc` authoring and closures composed with real validated effects remain full
DC-F/DC-U obligations; this pure subprofile cannot waive them. Its original
value/schema/admission/budget cases do not change when resume is omitted.

### 6.2 Fresh Compiled-Leaf Boundary Contract

The next bounded slice links dynamic composition to existing, fixed `.orc`
boundary leaves. It reuses the full workflow executor, not just its subprocess
launcher. This retains the existing compiler, prompt/document/output contracts
and leaf-local state; their invocation and maintenance cost is part of the
comparison. It creates no public target, candidate memo or recovery capability.

**Closed experimental operation.** Artifact `workflow-lisp/dynamic-spike/2`
retains §6.1 and adds exactly `effects`, a list of unique nonempty operation
identifiers. Its additional node is
`{"k":"effect","name":identifier,"inputs":node}`. Check its identifier
against the declared list in every body, including unreachable bodies. Version 1
keeps its pure vocabulary. Execution links the complete list to an explicitly
supplied trusted leaf registry before evaluating any node; missing/extra or
non-leaf bindings refuse `dynamic_effect_unlinked`. The artifact alone does not
pin or authorize external implementations: the execution input is the artifact
plus this registered, freshly compiled leaf set. Record their source/binding
identities with evidence; do not imply checkpoint-compatible linking.

Evaluate the inputs node once, require an ordinary record keyed by the leaf's
public wire input names, and reject closures at this boundary. Charge the effect
node and evaluated operands by §6.1; dispatch and return do not reset the budget.
A read-only invocation refuses `dynamic_effect_forbidden` before dispatch,
including effects reached through closures. Use one synchronous `LeafBridge`
owned by the experiment, not a generic callback/plugin backend. Registry lookup,
input validation and dispatch have no host-call escape exposed to the program.

**Leaf qualification and ownership.** Compile through
`compile_stage3_entrypoint(..., validate_shared=True)`. Select a real
`LoadedWorkflowBundle` and its corresponding typed workflow. This slice admits
only a direct `ProviderResultExpr` or `CommandResultExpr` body with exactly one
ordinary effect; no child runs, sessions, coordinator policies, loops or further
effectful computation inside the leaf. Pure argument/prompt construction and
the compiler's output projections remain owned by that compiler. Derive the
whole return descriptor from `typed_workflow.signature.return_type_ref` using
`compiler_normalized_type_descriptor` and `linked_module_type_environment` from
that same compilation. Never accept a separately authored return schema.

Use `workflow_public_input_contracts` to exclude private runtime bindings;
derive strict input descriptors with `transport_descriptor_for_schema`, check
ordinary values using `validate_transport_value`, then call `bind_workflow_inputs`
with `finite_floats=True`. This first check prevents the CLI-oriented binder from
coercing strings to numbers/Bool. The existing binder and executor still own
path containment/existence, private inputs and document/output obligations;
the shape kernel alone is not a path validator. Missing/extra arguments fail
before any leaf launch.

Create a fresh `StateManager` for each call, initialize it with the real source
path, `workflow_context(bundle)` and bound inputs, then use
`WorkflowExecutor(..., max_retries=0).execute(on_error="stop")` without resume.
Register deterministic subprocess providers through the existing provider
registry; never mock `prepare_invocation`/`execute` to claim real transport.
Each call has a fresh run/bundle location. Preserve the executor's existing
within-invocation retry, path, environment and execution permissions.

**Strict output before publication, with one snapshot.** Legacy output contracts
can coerce scalar strings and project away extra record fields. Checking their
already-normalized `workflow_outputs` cannot prove a strict dynamic boundary.
A narrow experimental executor adapter therefore guards the existing
`_apply_expected_outputs_contract` hook for its one admitted effect:

1. For a successful external action, resolve its runtime-bound bundle path using
   the executor's existing resolver and read bytes through its `WorkspaceFiles`.
   Missing/wrong-path/nonregular files fail; stdout and caller-supplied bytes
   cannot supply the snapshot. Reuse the experiment's strict JSON decoding rules
   for duplicate keys/nonfinite data, then call the existing strict kernel with
   the compiled whole return descriptor. Preserve path checks in their owners.
2. Pass **those same bytes** to the original hook. The only shared production
   extension is an optional `document_bytes` keyword on that hook, forwarded to
   the already snapshot-capable `validate_output_bundle` and
   `validate_variant_output_bundle`. Its default preserves every existing caller.
   Do not duplicate the method, validator, projection or publication machinery.
3. A strict failure returns a failed/exit-code-2 result without successful
   artifacts; otherwise the original hook still checks required `:out` files,
   paths, variants and joint publication. The snapshot consumed by that owner
   must be the one checked strictly, even if the file changes after capture.

Only a completed leaf returns its validated `workflow_outputs` as an immutable
dynamic record. Keep the existing wire keys, including generated return names;
do not invent an inverse projection or claim this wire-shaped adapter is the
final authoring interface. Failure raises `dynamic_effect_failed` with operation,
leaf run identity, artifact expression location and dynamic call context; do not
return a domain false/blocked value or leak raw output through diagnostics.
Invalid input uses `dynamic_boundary_invalid`. Leaf state, logs and partial
external writes may remain after failure; none is a candidate checkpoint, and
a fresh candidate invocation may repeat earlier effects.

The [evaluation plan](../plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md)
owns the finite E01–E12 cases and the explicit shared-hook ownership transfer.
Candidate code stays in `program.py`, `evaluator.py` and one `leaf_bridge.py`
under `experiments/dynamic_core_evaluation/`; real leaf/provider fixtures and
their test module belong to that finite scope. Full DC-F additionally requires
the immediately following authored-surface slice: reuse `reader.read_sexpr_text`
for one experimental `.orc` composition specimen with unannotated ordinary
helpers, inferred lexical captures and first-class closures, lowered to the
same checked artifact. Keep boundary declarations in the existing compiled leaf
module. Freeze that small grammar before coding it; JSON authoring and fixed
typed leaf syntax alone cannot satisfy this source-level obligation.

### 6.3 Minimal Authored Composition Contract

The next source slice makes ordinary composition visible before DC-F. One
experimental `source.py` reuses `reader.read_sexpr_text`; it lowers to the same
§6.2 artifact and calls `DynamicProgram.from_artifact` before returning it. No
production parser, target, module system or alternate evaluator is introduced.
`compile_source(text, *, source_path, type_env)` returns that admitted program.
The caller supplies the existing linked type environment from the trusted leaf
compilation and supplies the registered leaves separately at execution.

The reader's document wrapper contains exactly one outer `dynamic-core` form,
with exactly one each of these headers, in this order, followed by zero or more
helper definitions and one final `run`:

```lisp
(dynamic-core
  (:budget 200)
  (:inputs (goal String) (rubric String))
  (:result Value)
  (:effects review revise)
  (define (identity x) x)
  (define (make-reviser goal rubric)
    (fn (reviewed)
      (fn (candidate)
        (effect revise
          (record (text (field candidate "title"))
                  (goal goal) (rubric rubric)
                  (feedback (field reviewed "return__feedback")))))))
  (run
    (let* ((seed (identity (record (title "draft"))))
           (count (identity 1))
           (reviewed (effect review (record (text (field seed "title")))))
           (next (if (field reviewed "return__approved")
                     (fn (candidate) candidate)
                     ((make-reviser goal rubric) reviewed)))
           (callbacks (record (next next))))
      ((field callbacks "next") seed))))
```

The checked-in specimen uses actual input/output wire names from its compiled
leaves; the example above fixes composition behavior, not new public names.
Its deterministic review requests revision, so the returned, selected and
stored closure actually invokes the second leaf. A small ordinary application
helper in that specimen also passes the closure as a value. The same `identity`
body accepts an integer and an internal record without specialization. Capture
`goal`, `rubric` and the review result lexically; authors never write a capture
list or a context-carrier type. Boundary declarations and prompt contracts stay
in the existing typed leaf module.

**Finite grammar.** A helper is `(define (name parameter...) expression)` and a
callable literal is `(fn (parameter...) expression)`. There is one body
expression, no return/type/effect annotation and no second `lambda` spelling.
Expressions are the reader's Bool/Int/Float/String literals, lexical symbols,
ordinary `(callee argument...)` application, `let*`, strict `if`, `record`,
`field`, `list`, `at`, the thirteen §6.1 primitive calls, and `effect`:

- `(let* ((name expression)...) body)` binds sequentially; each initializer sees
  earlier bindings. `(if condition consequent alternative)` selects one arm.
- `(record (field-name expression)...)`, `(field base "field-name")`,
  `(list expression...)` and `(at base index)` map directly to their existing
  nodes. A record key is a literal nonempty symbol or String; field access
  requires a literal nonempty String. Neither accepts a computed field name.
  Empty records/lists and zero-argument functions
  are valid; duplicate record fields, parameters or names within one binding
  list are invalid.
- `(effect operation-id input-expression)` uses a literal declared symbol ID.
  The runtime registry, read-only refusal and validation remain exactly §6.2.
  Primitive calls use the existing operator allowlist; this slice does not
  expose primitive operators as callable values.

Reserve the form names and primitive names in binder positions. Distinct nested
scopes may shadow ordinary names. Top-level helpers are mutually visible
lexical code references with no captured entry inputs; their bodies see their
parameters, local bindings and other helpers. The `run` body additionally sees
declared inputs. A local binding shadows a helper of the same name. Infer each
`fn`'s free local variables, including those needed by nested functions, and
capture immutable values in sorted name order. Resolve helper references to
ordinary function values; do not specialize a body by call site or argument
shape. Stable definition IDs use helper names and structural expression paths,
never line/column offsets or the source filename. Whitespace/comments and
renaming the file therefore leave the admitted artifact digest unchanged.

Headers require a positive integer budget, unique input/effect/helper names,
and a single existing type-name symbol per public input/result. Resolve each
type through `type_env.resolve_type` using its source span, then derive its
descriptor through `compiler_normalized_type_descriptor`; admission still
enforces §6.1's supported transport kinds. This is not a new schema grammar.
Reject unsupported forms, malformed special-form arity, duplicate declarations
and unbound names in every body, including unreachable helpers. Ordinary call
arity, primitive arity and operand types remain their existing runtime checks.
Reader/type diagnostics
retain their existing source positions; source-lowering refusals use
`dynamic_source_invalid` with the offending source position. Runtime diagnostics
retain artifact expression paths in this finite slice; complete source mapping
is not claimed. There are no imports, macros, mutation, implicit truthiness,
new literals or unbounded frontend features in this slice.

An experiment README supplies a runnable command and a small before/after
composition excerpt grounded in `std/improve` and its actual caller fixtures.
Do not claim the typed route needs a record for one captured string: its
String-input caller already avoids that wrapper. Show the generic signature,
explicit procedure references and context arguments that the dynamic specimen
replaces in equivalent partial callback wiring, while retaining genuine
domain/boundary declarations on both sides. Do not compare the complete improve
implementation's size to this one-pass specimen. This is a
finite source-and-boundary proof, not the complete improve utility comparison.
The plan owns its case inventory and file scope; DC-U still requires full
improve and MLEvolve behavior, authoring and failure-cost comparisons.

### 6.4 Bounded Complete-Consumer Comparison

The complete `std/improve` and paired-search comparisons use the same admitted
artifact, source frontend and compiled-leaf route. Ordinary recursive helpers
already express their control flow; this slice adds no loop, pattern matching,
module system, schema compiler, performer or recovery mechanism. Preserve the
existing type-to-contract, prompt and strict result owners. The additions below
are experimental utility mechanisms, not a public language target.

**Version and container operations.** Emit
`workflow-lisp/dynamic-spike/3` from `compile_source`. Its top-level fields and
effect registry are exactly `/2`'s. Read back `/1` and `/2` under their original
closed node/operator vocabularies: none of the following additions is admitted
by changing a shared allowlist for those versions. Effect linking and read-only
refusal apply to both `/2` and `/3`. There is no caller-selectable source profile.

| `/3` source and artifact | Meaning and refusal |
| --- | --- |
| `(list/append items value)`; existing `op` node with name `list/append` | Exactly two operands, evaluated left to right. Require an internal list and return a new list with one additional value; preserve order and the original list. Mixed values and closures remain legal internally. |
| `(list/length items)`; existing `op` node with name `list/length` | Exactly one list operand; return its length through the existing checked Int owner. |
| `(record-update base (field-name expression)...)`; `{"k":"record-update","base":node,"fields":[[name,node],...]}` | Require at least one unique literal field name, using `record`'s Symbol/String key syntax. Evaluate the base once, require a record and all named fields to exist, then evaluate replacements once in written order. Return a new immutable record retaining every other field. A replacement may change the internal value kind, including a closure. |
| `(fail "reason_code")`; `{"k":"fail","reason":"reason_code"}` | A literal nonempty reason String, with no evaluated payload, immediately raises `dynamic_explicit_failure`; the diagnostic includes that reason, the existing error location, steps and ordinary call context. No result or implicit effect is produced. An unselected branch does not fail. |

Container operand/arity failures use `dynamic_operand_type`; an unknown update
field uses `dynamic_field_missing`, before evaluating its replacement. Malformed
syntax, duplicate keys, wrong artifact fields and invalid reason literals fail
the existing source/artifact admission checks, including in unreachable bodies.
Every new node consumes the same one-node debit before execution; its evaluated
children incur their normal debits. Containers and recursion do not reset the
budget. Immutable values, closure transport refusal and boundary validation stay
unchanged.

Reuse `pure_expr.PURE_EXPR_OPERATOR_CATALOG` for the two list operator arities
and the existing scalar evaluator for all thirteen earlier primitives. The
typed list evaluator requires a homogeneous transport descriptor and cannot
carry a dynamic closure; do not fabricate such a descriptor or introduce
internal type inference to call it. Native tuple append/length and a copied,
immutable mapping implement these dynamic container operations. The retained
typed `record-update` owner establishes the unchanged-field/unknown-field
behavior; it continues to enforce its own declared field types. This bounded
dynamic difference is an added runtime responsibility to count. Do not expose
the rest of the pure catalog speculatively. Use existing strict `if` instead of
adding `and`/`or` syntax or eager/short-circuit ambiguities.

**Real leaf reuse.** In addition to ordinary direct command results, the trusted
registry may admit a workflow whose whole body is one direct
`command-result :adapter ...`. Accept existing `CertifiedAdapterBinding`
alongside `ExternalToolBinding` at `LeafBridge.compile`; remove only the
candidate's extra adapter exclusion. The same compiler and shared validation
must validate its binding, input signature, invocation protocol and output
contract. A direct certified leaf already compiles through
`compile_stage3_entrypoint(..., validate_shared=True)`; the maintained
`experiments/mlevolve_pair/commands_compact.json` and
`tests/experiments/test_evaluated_execution_spike_programs.py::compact_controller`
own the adapter declarations and their current use. The implementation proof
must execute this shape through the real bridge, including strict invalid-input
and invalid-result cases, before claiming runtime reuse.

Reuse that manifest and its `json_object_positional_arg` protocol for proposal
and evaluation leaves. Reuse the existing improve command probes and the
paired-search scenario script/answers; fixture installation may copy them into
an isolated workspace. Do not add a Python controller or an argv-to-JSON
replacement adapter. The existing snapshot guard, required-output validation,
workflow outputs, run state, fresh attempts and failed-publication behavior
apply without a second output path. Runtime `return__…` wire keys remain the
bridge's output: small authored helpers reconstruct only the domain values they
consume, and this adaptation cost belongs in the comparison. No generic inverse
projection or new decoder is required.

Keep the domain declarations in one typed `utility_leaves.orc` module, using
distinct names for the improve draft and search candidate. Import existing
`std/improve` `Decision`/`Improvement` declarations for the improve boundary;
retain real `Candidate`, `Evaluation`, `Trial` and `SearchResult` schemas for
search. Resolve applied boundary types through the same linked type environment
and existing reader, including an `Improvement[Draft Feedback Blocker]` result.
The candidate's internal search state needs no new nominal declaration. Check
complete final domain results against those existing compiled descriptors;
`Value` must not replace the final consumer contracts to make parity pass.

**Authored policies and reuse limits.** `fixtures/improve.orc` holds ordinary
helper definitions once. The helper accepts the current value, review/revise
function values and a positive limit; caller closures capture goal, rubric or
other context, and the helper does not acquire a mandatory context-carrier
argument or type. Reject a nonpositive initial limit with `fail` before invoking
either hook. Preserve every review/revision, latest candidate, reason/evidence,
and final-revision failure specified by the existing improve tests. An exhausted
positive limit returns the last revision without an extra review. The dynamic
zero-limit diagnostic occurs at runtime before effects; report the difference
from the typed compiler rejection.

The experiment driver assembles the shared definition fragment with explicit
headers and a caller into one `dynamic-core` document, then uses normal source
compilation and serialized artifact read-back. This is visible fixture tooling,
not implemented `.orc` imports. Count the assembler and its locations/diagnostic
limitations. Compare fresh ordered calls with both real typed inline/imported
controls; do not call two assembled candidate documents imported-module proof.
The helper-extraction edit exercises ordinary lexical helper extraction, with
this module-reuse limitation stated in the utility result.

`fixtures/search.orc` contains the complete search policy as ordinary helpers,
including a recursive controller, immutable state updates and complete trial
history. Preserve the Python and compact `.orc` rules rather than improving
their policy while porting it: strict score improvement, invalid-score handling,
one repair on the failed branch, stall/fusion behavior and stop order all remain
observable. A bounded authored controller counter preserves the compact source's
loop-exhaustion result; the low-counter test is an explicit source variant, not
a new public option or the evaluator's node-budget error. Python has no separate
controller-counter outcome, so use the typed compact control for that case.

The four paired author edits retain genuine boundary declarations on both sides.
Use complete-consumer checks after each edit and include source/contract repair,
internal errors before and after actual effects, fresh-restart repeated work,
and the lack of static tracking/resume. Credit already available typed
`record-update`, String context inputs and ordinary helpers; label W1/W3
counterfactuals as proposed. Source size alone and removing legitimate domain
types are not utility gains.

For utility interpretation, distinguish value arguments from type parameters:
ordinary helpers still take initial values, hook functions and limits. The
candidate removes internal generic **type** arguments and compile-time ProcRef
wiring, not ordinary argument passing. The existing typed helper already
forwards active payloads opaquely. Count caller `return__…` reconstruction and
field/input repairs as real costs; payload-independent generic behavior and
pure-helper extraction alone are not unique dynamic gains. Count preexisting
context-carrier forwarding as retained behavior rather than a new edit.

Late error and restart comparisons must retain their successful prefix outputs
and count calls across both invocations. A fresh run that repeats two successful
prefix leaves and then executes six completion leaves has eight actual leaf runs;
typed committed-iteration resume may make six total calls by reusing the prefix.
This cost is compatible with the proposed non-resuming profile but must remain
visible. Every leaf still owns its compiled legacy state and startup work.
Only actual production removal, with old-target and run dispositions, qualifies
as net simplification; bypassing specialization inside experiment fixtures does
not remove its production owner. The
[single execution report's utility packet](../reports/2026-10-02-workflow-lisp-dynamic-core-evaluation.md#dc-u-evidence-packet)
owns the observations and recommendation, and the plan owns readiness selection.

The [evaluation plan](../plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md#dc-2-full-utility-comparison-and-gate-dc-u)
owns the exact finite file/case handoff and receipts. Implementation is limited
to the existing candidate files, these consumer fixtures, their shared test
support and focused test modules; shared production owners need no change for
this contract. Full consumer parity, authored edits and an independent utility
review precede DC-U's owner disposition. No adoption follows automatically.

## 7. Errors, Owners, And Deletions

| Check | Candidate timing and consequence |
| --- | --- |
| Syntax, unbound lexical names, missing imports, unknown effect classes, malformed schemas, prompt slot declarations | Build/artifact admission; these need no whole-program static typing. |
| Wrong dynamic argument count, non-callable application, wrong primitive operand, missing record field, non-boolean condition | Runtime at the source expression, before dispatch if it occurs while preparing that effect. An earlier effect may already have cost money. |
| External input/result shape, path safety, required output, schema identity | Validate at the declared boundary; reject before launch or before result publication as appropriate. |
| Unhandled tag or changed internal helper protocol | Executed branch/helper runtime check; no universal exhaustive-match promise. |
| Interrupted or changed candidate execution | No saved-effect reuse or resume; a new invocation validates its current declared boundaries and may repeat prior work. Existing typed runs retain their own versioned recovery contract. |

An editor retains syntax/name/declaration checks, not former type guarantees.
Runtime diagnostics name the expression, expected operation/schema, actual value
kind, and call/effect context without exposing secrets. A latent branch typo
after an expensive agent call is a real regression risk.

| Owner | Retain or revise | Displaced responsibility to delete on migration |
| --- | --- | --- |
| Frontend and closed-program checker | Existing boundary type declarations/contract compilation, names, modules, source maps, closed admission, lexical code identity and diagnostic locations | Internal nominal unification, generic specialization, `ProcRef`/`bind-proc` specialization and capture forwarding machinery, static variant-proof plumbing; retain any of this machinery still needed to derive declared boundary contracts. |
| Shared boundary validator and prompt compiler | Existing type-to-schema authority, generated guidance, input rendering, `:doc`/`:out`, decoding, strict validation and transport | Parallel handwritten JSON schema, parser, or postcondition implementations; do not introduce them. |
| Evaluator owner | Runtime value operations, diagnostic call frames and per-invocation budget | Static-call-only assumptions and type-driven environment/call projections for the new profile; no candidate memo or replay engine is required. |
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
or this schema/budget model. Shared memo/recovery delivery remains valuable for
the typed route but does not gate this non-resumable candidate.

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
automatic schema migration is proposed. The candidate's availability must
explicitly state that resume and effect tracking are absent; it need not acquire
a resumable state profile merely to reach an adoption decision.

Preserve [IO](../../specs/io.md), [provider](../../specs/providers.md),
[state](../../specs/state.md), [dependency](../../specs/dependencies.md), and
[security](../../specs/security.md) guarantees through their existing owners:
validated-before-publication results, declared artifact lineage/freshness, snapshots, path
containment, secret handling, and coordinator settlement. Current `state.json`
authority and the accepted evaluated target's memo authority remain their own
versioned profiles; the candidate does not reinterpret them or claim their
recovery guarantees. Dynamic records grant neither filesystem authority nor a
sandbox for subprocesses.

| Required evidence | What would qualify the candidate |
| --- | --- |
| Full `improve` behavior | Preserve [existing behavioral checks](../../tests/test_workflow_lisp_improve_stdlib.py): approval, blocked and exhaustion values; invalid hook output rejected before consumption; final-iteration revision failure remains failure; zero limit remains rejected before any hook; imported/inline order agrees. Keep the typed committed-hook/no-replay and effect-summary checks as explicit lost-capability controls, not candidate pass criteria. Credit W1/W3 as qualified in §2. |
| MLEvolve behavior | Port the policy in [search_compact.orc](../../experiments/mlevolve_pair/search_compact.orc) against the [paired-search rules](../../experiments/mlevolve_pair/README.md): seed ranking, strict improvement, ties, invalid evaluation, one repair on the same branch, stalls, one fusion, complete trial history, budget/score stops, invalid budget, and loop exhaustion. Distinguish schema-invalid transport from a valid `valid=false` evaluation. |
| Authoring and diagnostics | Paired edits adding a state field, changing review payload, capturing context, and extracting a helper; count concepts, duplicated facts, touched sites, repair effort, and errors detected before the first paid effect. Report lost static detections and the cost of effects already performed before a later error. |
| Boundary integration | Generated instructions and validation agree; strict booleans, nested lists, unknown fields, missing/wrong-path bundles, document snapshots, required reports, path escapes, atomic publication and lineage checks preserve their declared contracts. |
| Closures and restart tradeoff | Create/return/store/pass closures, choose one from validated agent data and capture a returned value before another actual effect. Demonstrate the declared fresh-start behavior after interruption, including repeated effects/cost and no adoption of stale output; report the lack of resume, automatic safe retry and static tracking. These losses may be accepted when the utility evidence offsets them. |
| Closed-program and budget proof | Reject forged code references, undeclared hosts, invalid schema/code bindings, nontransportable public values, and self-application exceeding its deterministic budget. Establish artifact read-back and per-invocation accounting independently of compiler generation; no replay or cross-run budget claim. |
| Total complexity | Count deleted and retained modules, specialization paths, identity forms, validators, state authorities, compatibility routes, and tests, alongside new runtime responsibilities; source LOC alone cannot establish simplification. |
| Production qualification | Resolve target/program versions, imports, stdlib replacement and existing-run disposition. Publish exact execution/inspection support and explicit absence of candidate resume/tracking; qualify admitted boundaries, artifacts and coordinators through existing owners. Identify consumers accepting this tradeoff, one migration destination and deletions; experimental parity alone does not authorize migration or retirement. |

The paired search uses scripted leaves; its Python controller lacks matching
durable recovery. Existing spike evidence supports evaluated execution, not
runtime closures. Establish behavior with deterministic fixtures first; any later
live comparison must separate authoring, model quality/cost, and recovery claims.

Mechanism evidence, schema compatibility, real boundary integration, owner
amendments and net utility still govern adoption. The absence of effect tracking
or resume is a permitted cost to assess, not an automatic rejection. Retain the
incumbent when the measured tradeoffs exceed the gain over W1/W3.

## 9. Complete-Consumer Production Candidate

This section records the accepted bounded DC-3 candidate contract. Target 3.0
is registered and its source/public route, shared boundaries, fresh authority
and full native consumers are qualified on the development branch. Durable
normative behavior is incorporated in [Versioning](../../specs/versioning.md#branch-qualified-target-30),
[CLI](../../specs/cli.md#dynamic-execution), [State](../../specs/state.md#dynamic-fresh-run-authority),
[IO](../../specs/io.md#dynamic-boundary-io) and
[Providers](../../specs/providers.md#dynamic-composed-provider-boundary).
Full readiness remains open; the [readiness plan](../plans/2026-10-02-workflow-lisp-dynamic-core-readiness-plan.md)
and [evaluation plan](../plans/2026-10-02-workflow-lisp-dynamic-core-evaluation-plan.md#dc-3-production-readiness-and-gate-dc-p)
own evidence and decisions. Branch qualification does not select a default,
release/adoption or consumer migration; DC-P remains separate.

### 9.1 Scope And Choice Of Destination

The first candidate executes sequential ordinary functions, closures and the
complete improve/search policies. Its external classes are ordinary commands
(external tools and certified adapters) and portable composed provider results,
including declared prompt documents and required output files. It retains
boundary schemas, command implementation evidence, filesystem containment,
dependency snapshots and validated-before-publication results. It adds neither
static effect inference nor cross-run reuse.

Refuse parallel effects, run references/child runs, trials, resource transitions,
materialized views, human-input suspension, provider sessions/context capture,
phased/live providers and versioned `consumes`/`publishes` before execution,
including in unreachable bodies. These classes require their own qualification;
they are not executed through a legacy fallback. In particular, a checked path
and a captured document do not imply artifact-version lineage or freshness.
This scope preserves those guarantees where admitted, and refuses their
unimplemented declaration forms. Do not remove their existing typed support.

| Route | What it achieves | What remains to maintain |
| --- | --- | --- |
| Retain typed evaluated execution; qualify W3 separately | Existing domain contracts, early checks and recovery; W3 can reduce context forwarding without dynamic values. | Typed specialization/proofs and pending shared runtime delivery; the dynamic evaluation can remain historical evidence. |
| Promote the experimental leaf bridge | Already executes both policies with fresh local effects; lowest immediate integration work. | Two frontends, source assembly, per-effect legacy workflows/state, caller wire reconstruction and all old compiler machinery. It preserves DC-2's adverse edit costs and removes no production owner. Reject as the final topology. |
| Dynamic composition calling shared boundary owners directly | Ordinary functions plus one declared-schema pipeline; domain results return without wire reconstruction or per-effect child workflows. | A dynamic frontend/admission/evaluator and a small fresh-run state profile, shared performer work, and explicitly retained old-target compatibility. Qualified branch destination; full readiness/adoption remain open. |

Name **`experiments/mlevolve_pair/search_compact.orc`, entry `run-search`**, as
the single maintained application migration destination after DC-P. Preserve
its module identity, `commands_compact.json`, CLI entry, full `SearchResult`
contract and the complete search policy. The frozen comparison sources remain
historical evidence, not a second maintained runtime implementation. The
ordinary improve helper is the minimum library integration; its deterministic
provider consumer is a qualification fixture, not a second application migration.
Do not also migrate the typed destination or the broader workflow estate.

### 9.2 Proposed Source And Public Use

Use the existing `workflow-lisp` wrapper, language header, `defmodule`, `import`,
`export`, boundary declarations, `defprompt` and `defworkflow`. Branch-qualified target
**`"3.0"`** selects dynamic composition; do not add a profile flag to each
command or a second `dynamic run` entry. Its major target distinguishes the
incompatible internal-call, validation and recovery contracts. Examples in this
design explain the contract; use the [complete tested guide](../lisp_workflow_drafting_guide.md#2b-dynamic-composition-on-the-qualified-branch)
for actual source, bindings and workspace prerequisites.

The entry module supplies one positive integer `(:budget N)`; libraries omit it.
The selected entry's budget covers its entire invocation, including imported
bodies. `defworkflow` retains typed public inputs/defaults and a required result
schema. `define`/`fn`, the §6.4 record/list/update forms and ordinary application
have no internal signature annotations. Strict `if` and the qualified primitive
set remain sufficient; no macros, automatic match exhaustiveness, new truthiness
or general Scheme compatibility is implied. Named workflow calls validate their
declared arguments/result in memory; ordinary helpers do not acquire schemas.

For example, a normal composed provider call returns the declared record itself:

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "3.0")
  (:budget 10000)
  (defmodule examples/review)
  (export review)
  (defrecord Review (approved Bool) (feedback String))
  (defprompt review-prompt (:fills (draft :text)) -> Review
    "Review {draft}. Approve only if it meets the supplied requirements.")
  (define (review-text draft)
    (provider-result providers.review
      :prompt (review-prompt :draft draft)))
  (defworkflow review ((draft String)) -> Review
    (review-text draft)))
```

The provider extern remains supplied by the existing provider
binding/configuration owner, not declared by an
arbitrary runtime string. `Review` still owns instructions and validation.

An advanced composition uses a library function and separate captured contexts.
Here `review-prompt` returns `Decision[Feedback Blocker]`, `revise-prompt` returns
`Draft`, and both are ordinary declared `defprompt` values in the caller's module:

```lisp
(import std/improve :only (Decision Improvement))
(import std/dynamic/improve :only (improve))

(defrecord Draft (title String) (score Int))
(defrecord Feedback (note String))
(defrecord Blocker (reason String))
(defprompt review-prompt
  (:fills (draft :value Draft) (goal :text) (rubric :text))
  -> Decision[Feedback Blocker]
  "Review {draft} against {goal} using {rubric}.")
(defprompt revise-prompt
  (:fills (draft :value Draft) (feedback :value Feedback) (goal :text))
  -> Draft
  "Revise {draft} toward {goal}, addressing {feedback}.")

(defworkflow improve-draft
  ((draft Draft) (goal String) (rubric String) (limit Int :default 3))
  -> Improvement[Draft Feedback Blocker]
  (improve draft
    (fn (current)
      (provider-result providers.review
        :prompt (review-prompt :draft current :goal goal :rubric rubric)))
    (fn (current feedback)
      (provider-result providers.revise
        :prompt (revise-prompt :draft current :feedback feedback :goal goal)))
    limit))
```

The helper returns the existing domain shape, for example
`{"variant":"EXHAUSTED","value":{"title":"draft+r","score":1}}`.
There are no authored `return__…` names, generic helper type arguments,
`ProcRef`/`bind-proc`, carrier records or registry/leaf declarations.
The helper still takes ordinary value arguments and performs the complete §5
protocol, including invalid-hook and nonpositive-limit failures.

Use existing CLI doors and manifest flags. After the proposed migration, the
maintained search commands are:

```bash
python -m orchestrator compile experiments/mlevolve_pair/search_compact.orc \
  --entry-workflow run-search --source-root experiments \
  --command-boundaries-file experiments/mlevolve_pair/commands_compact.json
python -m orchestrator run experiments/mlevolve_pair/search_compact.orc \
  --entry-workflow run-search --source-root experiments \
  --command-boundaries-file experiments/mlevolve_pair/commands_compact.json \
  --input max_evaluations=12 --input target_score=0.0 --dry-run
# Removing --dry-run creates a fresh run with those same declared inputs.
python -m orchestrator report --run-id RUN_ID --format json
```

`compile` checks all admitted bodies and writes the checked artifact/source map;
it does not execute helpers. `run --dry-run` additionally resolves bindings,
permissions, input defaults and initial path checks without creating an effect
attempt or evaluating latent dynamic branches. It cannot promise that a future
arity/field/operand check will pass. Ordinary `run` reads back the checked
artifact and creates a fresh root. `report` includes the profile and
`resumable: false`. `resume RUN_ID` and invalidation refuse
`dynamic_resume_unsupported`/`dynamic_invalidation_unsupported` without writes,
compilation or dispatch; the diagnostic points to a fresh `run` and its repeat
cost. Existing typed commands retain their behavior.

CLI `--input` retains intentional schema-directed textual parsing at the CLI
edge; the resulting logical value then passes the strict boundary validator.
An input-file JSON string `"false"` is not a Bool. Missing/extra inputs and
invalid defaults refuse before run creation. No CLI coercion is available to
provider output or dynamic function values.

The qualified run options are frontend binding/source/entry flags, inputs,
`--state-dir`, `--dry-run` and ordinary logging/streaming. Dynamic runs stop on
error and default to zero runtime retries; explicit `--on-error continue` or
nonzero `--max-retries` refuses. Preserve old profiles' retry defaults. Profile
option validation distinguishes omitted parser defaults from explicit requests;
it refuses legacy context injection, run-ref roots, cleanup/archive actions,
backup-state, step summaries/live-agent notes, retry-delay overrides and flat
debug-YAML export before creating a run. Compile diagnostics/source-map export
remain supported. Do not silently ignore a requested legacy feature or start
auxiliary summary providers under this qualification scope.

### 9.3 Source Owners And Target Call Graph

The following records the source ownership and accepted candidate limits.
Referenced shared work is owned by
[Phase 3 Tasks 6–7/12](../plans/2026-10-02-workflow-lisp-evaluated-execution-phase-3-plan.md#source-map-and-ownership);
its reviewed shared implementations are consumed and locally qualified, not
recreated on this branch. Full upstream phase qualification remains separate.

```text
existing compile/run CLI + FrontendBuildRequest
  -> existing reader / module discovery / binding manifests / boundary type env
  -> target-selected dynamic source lowering and independent artifact admission
  -> dynamic evaluator: ordinary values, closures, budget
  -> shared resolved command/provider request + path/snapshot/contract owners
  -> StepExecutor or ProviderExecutor -> one captured result bundle
  -> shared strict root validation + required outputs -> native domain value
  -> dynamic continuation or checked public return
```

| Existing owner | Candidate responsibility / precise limit |
| --- | --- |
| `reader.py`, `syntax.py`, `modules.py`, `FrontendBuildRequest` and manifest/configuration loaders | Reuse reading, spans, root resolution, imports/exports and trusted bindings. Add target-selected `define`/budget handling and declaration-only import admission. Their current typed elaboration is not the dynamic frontend. |
| `type_env.py`, `normalized_type_descriptor.py`, `contracts.py`, `typed_prompt_inputs.py` | Retain schema type applications, refinements, guidance, fill roles and contract compilation. Internal helper calls bypass type unification/specialization; boundary types do not. |
| `closed/effects.py`, `closed/check.py` and shared request builders | Extract only reusable declaration/contract checks needed by both representations. Existing checked typed effects and P5 stay unchanged; a dynamic artifact is never passed off as a typed `ClosedProgram`. |
| `workflow_lisp/dynamic/` source/admission owner and `workflow/dynamic/` evaluator/run owner | Own the moved/revised core, replacing the historical source wrapper, hand-linked effects and artifact versions. No second maintained copy under `experiments/`; no new general backend/plugin interface. |
| Delivered `evaluated/commands.py`, `prompts.py`, `providers.py`, `inputs.py` | Consume resolved values and declaration-owned request data without reading a typed memo or dynamic state. Their native whole-root strict result mode, plain validated-value provider preparation and certified inline serialization are qualified. The dynamic caller supplies strict input checks and publication. Shared `inputs.py` owns external document path-token transport and plain document preparation/serialization; `_prepare_command_document_fields`, `_serialize_command_document` and `_command_document_argv` retain their typed consumers. |
| `StepExecutor`, `ProviderExecutor`, `WorkspaceFiles`, content-snapshot/output-contract owners | Keep dispatch, process controls, sandbox/permissions, pinned reads/writes and result validation. The candidate does not call a stateful `WorkflowExecutor` for each effect. |
| `evaluated/attempts.py`, `authority.py`, `runtime.py` | Preserve typed memo/authority. `allocate_attempt` appends memo records and `attempt_paths` consumes `MemoSnapshot`; neither is a memo-free allocator. Reuse lower filesystem/lock helpers, or one owner-approved shared extraction with both real callers; do not synthesize a memo. |
| CLI/state/report/dashboard/monitor readers | Route by exact profile before typed/legacy checks. Share data presentation and log-path handling; the fresh profile supplies its own truthful state interpretation, not typed pure replay. |

Target dispatch selects typed `2.35` and dynamic `3.0` exactly, with independent
loaders/representations; known older targets retain their owners and unknown
targets refuse before execution or creation. Persisted profile selection precedes
`StateManager` or typed authority loading; no secondary target flag, fallback or
conversion is introduced. [Versioning](../../specs/versioning.md#branch-qualified-target-30)
owns the durable profile routing.

A public CLI source read/header failure before target selection refuses without invoking
any backend or allocating state. Preserve the reader/header diagnostic and
existing CLI request/export diagnostic precedence. Configuration that has not
been loaded cannot supply an elaborated compile-request identity; do not load
or compile imports to reconstruct it. Source errors therefore precede errors
in that unobserved configuration. The [LSP parity contract](workflow_lisp_language_server.md#compile-request-and-diagnostic-parity)
separates this refusal evidence from full F2 for actual compilation attempts.

Each effect is one request to an existing performer, not a compiled leaf workflow
or child run. Shared callable boundaries receive immutable resolved inputs and
the allocated attempt files. State transitions belong to the calling run owner;
performers do not read or publish either profile's state. If a delivered shared
performer still depends on typed memo/`EvaluatedValue` internals, its owner must
separate that dependency before this call graph is claimed executable.

### 9.4 Closed Artifact, Values And Admission

Propose artifact schema **`workflow-lisp/dynamic-program/1`**, distinct from
`closed-program/1`, `table/1` and all `dynamic-spike` schemas. Its immutable
semantic content is the selected target, entry identifier, ordered public
inputs/defaults/result descriptors, budget, lexical definitions, boundary-schema
catalog and closed effect/configuration payloads. A lexical definition retains
ordered parameter/capture names and one body. Source-module ownership and logical
asset bases are explicit for definitions/prompts; caller location cannot rebase
an imported document. Schema entries are the existing compiler-normalized
descriptors with their canonical declaration identities, not a new schema format.

The checked envelope admits exactly `schema`, `target`, `entry`, `budget`,
`definitions`, `schemas`, `bindings`, `sources` and `source_map`. The last two
are provenance; all other fields participate in the semantic digest.
`definitions` maps canonical code IDs to exactly `params`, `captures`, `body`,
`owner` and `boundary`. `owner` binds the module/logical asset base; `boundary`
is null for an ordinary helper, otherwise ordered parameter/schema/default
rows and a result schema reference for a declared workflow. Entry has no
captures and a non-null boundary. `bindings` holds the existing normalized,
closed command/provider configuration with explicit owning modules; no host
callable or external leaf registry is supplied at execution. `sources` pins
the exact consumed source bytes; `source_map` indexes nodes and boundary subjects
to those sources. Dynamic functions do not acquire expression-wide type fields.

Retain §6.1/§6.4's scalar, record, list, update, call, closure and failure nodes
and their exact evaluation order. Replace the spike's string registry `effect`
with admitted command/provider nodes: their static payload is the shared closed
request declaration; dynamic child expressions occupy its documented operand
positions. A boundary operand has an expected descriptor from its declaration,
not an inferred type for the expression. The shared operand walk determines
written evaluation order. There is no extra slot language, synthesized typed
function body, hidden source concatenation or runtime host callback in the file.
Dynamic admission independently checks the common static payload contract and
every operand; extracting those checks is a prerequisite, not permission to skip
typed P5 or claim its type proofs for dynamic nodes.

Bindings are indexed by canonical module. Each row contains exactly `owner`
(`module`, `asset_base`), `configuration` (the existing canonical `commands`,
`providers`, `prompts` rows), and `types`. The last maps certified bindings'
used `input_signature`/`output_type_name` names to schema-catalog references,
resolved by that module's type environment. It is not inferred from runtime
values or added to binding manifests. Pure programs may have no binding rows.
Include exactly the type associations needed by certified commands used in any
included body, including unreachable bodies; unused configuration rows need none.

A dynamic command `perform` retains `k`, `class`, `result`, `repeat`, `boundary`,
`command`, `closure`, `contract` and `argv`, with optional `document` and
`input_type`. External documents require both optional fields together;
certified documents use their binding signatures and forbid `input_type`.
A dynamic provider `perform` retains `k`, `class`, `result`, `repeat`, `provider`,
`prompt`, `inputs`, `dependencies`, `policy` and `contract`, plus `prompt_owner`
(`module`, `asset_base`). Its `inputs` is empty; composed prompt fills retain
their existing declaration metadata and dynamic `value` operand. These exact
envelopes omit typed `site`, `@` and `argv_transport`; typed admission keeps
its own required fields and proofs unchanged. Result, input and fill descriptors
must agree with the shared schema catalog.

The definition owner selects command/provider configuration; `prompt_owner`
selects prompt configuration and the prompt reader's logical source location.
Map the effect and fill-value expressions to their caller, but prompt/template,
fill-declaration and prompt-result subjects to the defining prompt module.
An extern prompt's explicit call-authored result annotation stays caller-owned.
Every subject remains an actual artifact pointer with pinned source provenance.
Use the shared effect operand walk, with ordinary `let` bindings when needed to
preserve written evaluation order before signature/declaration ordering. Normalize
policy object traversal to canonical key order; object serialization order must
not change the meaning of a semantic digest.
Policy model/effort operands have a `String` boundary; timeout remains a positive
literal `Int`, delivery is absent or literal `"composed"`, and
`materialization_attempts` is not admitted. These static restrictions do not
restrict ordinary dynamic expressions in model/effort or dependency positions.

Admission requires exact fields/version, strict finite JSON, unique declarations,
resolved lexical names/code IDs, capture arity, valid defaults/descriptors,
closed authorized effect classes/bindings, and valid module/source-map references.
Check all included bodies, including unreachable ones; runtime call arity and
value shape are not statically inferred. Re-derive root output contracts from
the declared descriptors and compare semantic contract data on read-back rather
than trusting a copied result schema. Reject forged request classes, schema
references, filesystem/code bindings and runtime import/eval instructions.
No missing or unknown version falls through to typed or legacy loading.

Values remain strict scalars, tuples and immutable string-keyed records/maps;
the admitted operations initially expose the record/list subset. Closures are
`(program-owned code ID, frozen captures)`, with no mutable cells, Python
callables or serializable executable capability. Freeze inputs/captures once;
functional updates invalidate any previous validation assumption. Internal
functions and collections may contain closures; every data boundary rejects
them recursively. Tagged outcomes use the shared descriptor's `variant` and
active fields, without a parallel union runtime class. Int64/finite numeric
semantics and the one-node-entry budget rule remain §6.1's; calls/effects never
reset the budget. Execution uses an iterative machine, including self-application.

Use canonical semantic digests from `closed.program.canonical_digest` over the
checked semantic content, excluding source positions. An independently pinned
source-map/source-byte digest binds diagnostic provenance. Import/source/config
snapshots enter build/run provenance using `SourceReadTrace`; neither semantic
identity nor a reader depends on reopening a live source file. Experiment `/1`,
`/2`, `/3` artifacts are not production imports or old production run profiles.
Port applicable behavioral checks to the production owner; archive spike-format
read-back tests with their revision and receipts instead of leaving active tests
importing a deleted experimental package. Do not add production compatibility
decoders or an automatic conversion command merely to keep those tests live.

### 9.5 One Boundary Pipeline, Native Results

`contracts.py::derive_prompt_guided_structured_result_contract` already accepts
`whole_value=True`, which produces one `__result__` at JSON pointer `""` for a
record/union as well as other transportable values. This is the candidate's
result contract. `output_contract.validate_output_bundle` can return that
validated root value. The dynamic evaluator consumes the existing owner's
`__result__` value and freezes it; it never splits `return__…` names or builds an
inverse projection. `evaluated/calls.py::call_result` handles checked typed
caller/native views and is not such an inverse converter. Existing typed
`closed/effects.py` generation and `closed/check.py` read-back retain their
current flattened contracts.

| Boundary | Input/type authority | Result and failure rule |
| --- | --- | --- |
| Public workflow | Declared parameters/defaults and result type | Strict entry values before run creation; strict result before terminal publication. Imported named workflow calls apply the same data check in memory. |
| `defprompt` provider | Declared fill refinements; `:text` uses `String`, unrefined `:value` uses `Value`; `:doc`/`:path` require an explicit existing `defpath` refinement; prompt-owned return schema | Runtime values checked before rendering/launch. Same snapshot dependencies, path aliases and required-file checks; native root result after all output checks. |
| Extern-backed provider | Explicit `:returns`, with no nonempty `:inputs` | Current extern bindings declare no input schemas. Reject nonempty inputs during admission, including unreachable bodies; use `defprompt` fills for data inputs. Never infer schemas from observed values. |
| Certified command adapter | Existing `input_signature`, signature-ordered transport keys and invocation protocol; explicit `:returns` | Strict checks precede existing canonical inline JSON construction; no argv wrapper or replacement adapter. |
| External command argv | Existing command binding and the built-in argv contract of strict transportable data: scalars, records, unions, lists, optionals and paths; never closures/host objects | Preserve the shared renderer's request rules, including literal/runtime Bool spelling and JSON aggregate rendering. Runtime values are rendered once; a dynamic string is not reinterpreted as a reference/template. This transport contract does not validate a tool's semantic arguments; use a declared document schema where their shape matters. |
| External command document | Proposed `:input-type InputRecord` alongside existing `:inputs ((field expression) ...)`; explicit `:returns` | One existing record schema replaces the typed target's inferred field descriptors. Required when `:inputs` is present, forbidden otherwise and for certified adapters. Exact fields, even for an empty record; reuse Task 12's document bytes/path transport. |

The last row is one necessary annotation at an otherwise untyped external data
boundary, not another schema language or new binding-manifest format:

```lisp
(defrecord EvalInput (candidate Candidate) (history List[Trial]))
(command-result evaluate
  :argv ("python" "evaluate.py")
  :inputs ((candidate current) (history trials))
  :input-type EvalInput :returns Evaluation)
```

Argv literals retain the existing scalar literal renderer (`True`/`False` for
Bool); computed values use the shared value renderer (`true`/`false`, JSON for
aggregates). A dynamic alias is a computed value. Strings remain opaque values,
without template/reference reinterpretation. Fill schemas come from declared
refinements rather than the filled expression's inferred type; requiring a
`defpath` refinement for `:doc`/`:path` avoids inventing nominal path types.

Missing/extra fields, wrong Bool, inactive union fields, nonfinite numbers,
closure/host values and path escapes fail before launch or exposure as appropriate.
Retain the existing strict kernel's Int-to-Float normalization; never accept a
numeric string by scalar coercion. Strict JSON decoding rejects duplicate keys
before validating the raw root. Thread one runtime-owned captured byte snapshot
through that strict check and the existing root/required-output/path checks.
Select strict policy under the new profile at the shared boundary owner, keeping
old defaults unchanged; a second parser/validator implementation inside the
dynamic evaluator is forbidden. Reuse or move the experimental strict decoder
to that owner if no existing shared decoder supplies the exact rule.

Only after every declared check succeeds may the run publish success and return
the normalized root. A required report failure publishes no successful result
map even if the structured JSON is valid. Preserve the existing
`omp_json_stdout` materialization route where its registered provider owns it;
ordinary stdout is never a substitute bundle. External files already written
may remain after failure, and path existence is not an authorship/freshness proof.
No general `consumes`/`publishes` lineage is claimed by this first profile.

### 9.6 Modules And The Minimum Standard Library

Reuse existing search roots, canonical module/member names, `:as`/`:only`, export
visibility, ambiguity/cycle refusals and source-read snapshots. A dynamic source
module can import dynamic `define` helpers as ordinary function values; bodies
are linked once by canonical owner, without specializing on caller values.
No runtime import/loading, mutable module state or automatic network resolution
is admitted. Closure code references resolve within the one closed program.

An old-target source module can supply selected `defrecord`/`defunion`/`defpath`
and `defprompt` declarations plus their declaration dependencies. Resolve that
selected closure before executable-body checking; do not accidentally elaborate
or copy every `defproc` in the source. This is a required module-loader delta,
not a capability already proved by DC-2's source assembler. A prompt/declaration
whose dependency requires an inadmissible executable form is refused with its
import chain. Explicitly selecting an old `defproc`, workflow, macro, `ProcRef`
or compiled typed bundle refuses `dynamic_import_incompatible`; there is no
implicit translation or leaf bridge. Older-target entries likewise cannot import
dynamic code. This release links source imports only and refuses supplied
compiled bundles of every profile, including dynamic ones. A helper library has
no entry or budget and needs no separately serialized library format. The
complete linked program can still execute from its closed artifact without
source reads. Conflicting snapshots of one canonical source member refuse
rather than coexist under invented identities; declarations/prompts retain
their defining module's configuration and asset base. The public manifest stays
with its current owner; compiled-library import is a later consumer requirement,
not an implicit feature of the complete-program artifact.

The only new maintained library module in this slice is
`stdlib_modules/std/dynamic/improve.orc`, canonical `std/dynamic/improve`, exporting
the ordinary four-argument `improve` helper. Move its qualified policy from the
experiment; replace fragment assembly with a real import. Reuse the existing
`std/improve` `Decision`/`Improvement` declarations via explicit declaration-only
imports. Do not duplicate their schemas, silently select a different `std/improve`
body by target, or translate its typed helper. The distinct helper name/path
records an incompatible callable API; old imports remain stable. At retirement,
the old helper body can disappear while its useful boundary declarations retain
their identities. No forwarding alias or mandatory later rename is needed.

### 9.7 Fresh Run Authority And Read-Only Inspection

The branch-qualified profile uses exact state routing pair `schema_version: "3.1"` with
`result_persistence_profile: "dynamic_execution.v1"`. The immutable `run.json`
pins the checked `closed_program.json`, target/entry, semantic and provenance
digests, bound inputs, budget, workspace/configuration and runtime/interpreter
identity. These filenames reuse the public run-root convention, not the typed
`RunAuthority` schema. The mutable **`state.json` is authoritative for fresh-run
progress and terminal publication** in this profile; it is not a memo-derived
cache. No memo, environment checkpoint, resume plan or replay is created.

| File | Exact fields and interpretation |
| --- | --- |
| `run.json` | `schema_version`, `result_persistence_profile`, `run_id`, `workflow_file`, `workflow_checksum`, `started_at`, `program_digest`, `input_digest`, `bound_inputs`, `representation`, `interpreters`, `workspace`, `runtime_pin`, `provenance_digest`. Existing checksum/input/interpreter conventions remain with their owners; `representation` is `dynamic/1`. Target/entry/budget and resolved binding configuration are pinned through the program, not copied again. `workspace` is the canonical execution workspace; `runtime_pin` uses the existing package identity owner. |
| `state.json` | `schema_version`, `result_persistence_profile`, `run_id`, `program_digest`, `updated_at`, `status`, `steps_used`, `current_effect`, `effects`, `workflow_outputs`, `error`. Stored status is `running`, `completed` or `failed`; interruption is a read-time liveness result. Result/error/current fields are present and null when absent. |
| Each `effects` row | `ordinal`, `definition`, `location`, `effect_class`, `status`, `result_path`, `stdout_path`, `stderr_path`, `prompt_path`, `started_at`, `finished_at`, `error`. `definition`/`location` identify checked code and its expression pointer; class is `command` or `provider`; status is `running`, `completed` or `failed`. Command prompt paths, unfinished timestamps and absent errors are null. Paths are runtime-owned, run-relative and checked through the pinned file owner. |

Readers reject unknown keys and inconsistent identities/digests, noncontiguous
positive ordinals, steps outside `0..budget`, multiple/nonfinal running rows,
invalid source references, and paths outside the prescribed attempt directories.
`current_effect` is the final running row's ordinal or null. A completed state
has only completed rows, a schema-valid terminal result and no error; failed
state has an error and no result. An effect failure closes its row before the
run's failed terminal; a pure failure can follow completed rows. No checks treat
file hashes as evidence of host-authenticated history or infer missing progress
from external files.

The minimal state contains its profile/run/program identity, timestamps, status,
steps consumed at the last transition, ordered effect rows, current row and
optional terminal result/error. A row has a monotonically increasing invocation
ordinal, source code/expression location, command/provider class, status,
attempt-file paths, timing and safe error information. Persist no captured
closures, static summaries, legacy call frames/step visits, next-effect prediction
or duplicate copy of every successful result. `workflow_outputs` is the checked
native terminal value, possibly a scalar, under this profile's schema.

Under the existing writer/workspace locks, durably publish program/header and an
initial running state before executing. For each invocation: resolve and check
inputs and command evidence, atomically record the next row as running, create
its attempt directory exclusively through `WorkspaceFiles`, dispatch once,
validate the captured result and required files, then atomically complete/fail
the row. Use run-local ordinal directories such as `effects/1/attempt-1`; the
ordinal is evidence identity, not a reusable static site or checkpoint key.
This release has no runtime retry: one performer dispatch per invocation, with
executor retry settings fixed accordingly. A later retry policy would need
explicit fresh attempt locations; it is not an implicit use of the current
CLI's legacy retry default. A collision refuses without adopting existing files.

Atomic state-write/allocation failure stops before another dispatch; a command
may already have produced partial output. A kill after external completion but
before state publication leaves an interrupted run, never an adopted success.
Terminal completion requires no active/failed effect and a strict public result;
failure retains earlier rows/files. A new invocation always has a new run ID,
inputs and budget and may repeat all earlier work. Command closure/disjointness,
interpreter resolution and before/after execution checks reuse their shared
owners; a fresh run cannot claim typed replay's file-change guarantees.

Readers validate the exact profile, immutable pins and state/result shape, read
an atomic state snapshot and inspect lock liveness. Stored running plus absent
writer means `interrupted`; a valid completed/failed terminal remains terminal.
Missing/corrupt state is `dynamic_state_invalid`, not reconstructible from logs,
attempt bundles or re-evaluation. Readers neither write nor execute anything.
Report/dashboard show ordered invocations, reached source location, result/error
and captured files; no unevaluated future graph or legacy heartbeat is fabricated.
Monitor/usage-limit readers recognize active/interrupted/terminal states and
attempt log paths. Watchdogs must expose `resumable: false` and stop/escalate an
interruption instead of automatically invoking resume or a fresh run. Qualify
these public readers before availability; notifications and scheduling are not
part of the tests.

### 9.8 Diagnostics And Compatibility

Map every admitted expression, definition and boundary subject to its original
module's source span/form path using the existing source-map vocabulary. Runtime
errors carry code, safe value kind/expected contract, module/span, artifact
pointer, dynamic call stack, invocation/attempt if reached and budget used.
Imported helper failures name both the definition and caller. Source-free
execution uses the persisted map; a missing or invalid required mapping refuses
artifact admission rather than reporting an unrelated current file. Locations
and call frames are diagnostic and do not serialize captures or secret values.
Retain the shared validator's field-path diagnostic without parsing its prose.

| Input/run | Disposition |
| --- | --- |
| Existing source/compiled artifact at targets through 2.34 | Original admission, bytes for identical identity inputs, workflow runtime and resume remain. Real package-pin changes remain visible. |
| Typed target 2.35 and `evaluated_execution.v1` runs | Original typed program, memo and readers/recovery contract; no dynamic semantics or schema-strengthening applied retroactively. |
| Branch-qualified target 3.0 / dynamic program major 1 | Only the classes and source forms in this profile; strict independent read-back and fresh-run public state. Unsupported forms fail before external work. |
| Supplied compiled import of any profile; incompatible source import; unknown target/profile/schema; mixed header/program; forged provenance | Refuse explicitly without fallback, conversion, new run creation or dispatch. |
| Existing interrupted or completed typed run | Keep its original environment/runtime pins and route it to its retained owner; never convert checkpoints to captures or restart it under the dynamic profile. |
| Historical dynamic-spike artifact/leaf run | Preserve evidence under its experimental/legacy owner; not a migratable production dynamic run. |

The compatibility cost lasts until an explicit Phase 7 run-retirement decision.
Branch registration does not delete retained typed code or promise that old runs can
be resumed by a future binary after their original runtime is retired.

### 9.9 Removal Ledger And Executable Qualification

| Addition/revision | What it replaces; what remains |
| --- | --- |
| Production dynamic source/admission/evaluator | Moves the qualified experiment core; delete its live second implementation and driver source concatenation when the selected route is maintained. Port behavioral checks, archive spike-format read-back tests at their recorded revision with receipts, and remove active imports of deleted experiment modules; add no production `/1`–`/3` loaders. |
| Direct shared request/performer calls and native root results | Remove `LeafBridge`, `_GuardedWorkflowExecutor`, leaf registries, wrapper workflows and caller normalizers from the maintained route; no per-effect `StateManager`/legacy checkpoint. The small shared `document_bytes` seam remains useful and is not duplicated. |
| Real dynamic module import and `std/dynamic/improve` | Replace the assembled helper fragment and caller copies; retain `std/improve` schemas and its typed body while old consumers need them. |
| Fresh state/reader adapter | Replaces per-leaf run state for the dynamic application; adds one explicit authority profile. Typed memo/state authorities remain for their own runs. Count this addition as compatibility cost. |
| Migrated search application | Removes its internal `SearchState` nominal taxonomy, generic/callable wiring where present and corresponding dynamic-route specializations. Retain `Candidate`, `Evaluation`, `Trial`, `SearchResult`, command bindings and policy tests. |
| Whole production compiler retirement | No immediate removal claim. `ProcRef`, specialization, variant proofs, typed evaluator, legacy lowering and resume still serve retained targets. Only a later caller/run inventory and retirement decision can remove their owners. |

One maintained application and one ordinary helper do not establish net deletion
of the compiler. Report removed call paths and retained production owners
separately. Keeping the incumbent is preferable if the new frontend/state and
compatibility cost outweigh removal of the bridge and simpler composition.

The following are finite proofs of this architecture, not another evaluator
spike or permission for paid calls. Reuse the existing Phase 3 evidence matrix
and exact shared owner tests; the readiness plan records selectors and outcomes.

| Proof | Existing base and missing executable observation |
| --- | --- |
| Q1 — root contract | Existing `whole_value=True`, normalized descriptors and output-bundle validators. Derive record/applied-union roots; send one captured byte snapshot through strict validation and actual shared output publication; observe native values, required-output failure, wrong Bool/extra/inactive-field refusal, no authored normalizer and unchanged typed artifacts. Pure contract proof alone does not qualify a performer. |
| Q2 — selective modules | Existing module roots/export resolution and source tracing. Import `Decision`/`Improvement` without typed `improve`, import an ordinary helper with captures, close source-free artifacts and prove owner-relative documents, full diagnostic spans, conflict/cycle/version refusals and no source assembly. This selection-before-elaboration path is a new prerequisite. |
| Q3 — direct command/provider path | Import shared Tasks 6–7/12 delivery. Through actual public source/CLI, perform a certified command, external document command, composed deterministic subprocess provider, and closure chosen after its result. Compare request fields, complete native results and permission/path failures. Instrument legacy `WorkflowExecutor` construction to fail if this route reaches it. No callback or legacy-leaf stand-in qualifies. |
| Q4 — fresh state/public readers | Real public run/report/dashboard/monitor/probe/usage-limit readers; kill before dispatch, during execution and after output before state publication. Observe interruption, immutable old files, refused resume/invalidation and extra calls on a new run. No stale completed projection, dispatch from a reader or successful orphan adoption. |
| Q5 — retained behavior/removal | Complete improve/search controls and the four author edits on the direct route, plus affected old-target artifact/run/resume selectors. Root-schema errors and source maps must improve the demonstrated wire/diagnostic costs without erasing late runtime failures. Inspect actual module/call-path removal and compatibility owners, not LOC alone. |

DC-3 planning can close the contract while Q2–Q4 still require implementation;
it cannot mark those proofs passed or declare production readiness. Missing
shared performers, a memo-free boundary call seam, declaration-only linking,
dynamic source maps or profile-aware readers are named owner prerequisites.
Implement their bounded deltas under the reviewed handoff, periodically importing
shared progress; do not re-create shared runtimes to avoid waiting. Live-provider
cost/quality and paid qualification remain a separately allocated gap before any
release claim that needs them.

The owner-facing DC-P choice is adoption of this exact fresh-only, sequential
profile and the one application destination versus retaining the typed route.
Proposed version numbers, strict input-document annotation, explicit stdlib name
and state schema are reviewable design choices inside readiness work. They do
not independently select migration, old-run retirement or a second feature
programme. The material costs remain later errors, repeat work after interruption,
unavailable effect classes and temporarily retained execution machinery.
