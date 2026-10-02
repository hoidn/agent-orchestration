# Workflow Lisp: Dynamic Core With Explicit Boundary Contracts

- **Status:** experimental source functions/closures and compiled leaves implemented; feasibility evidence reviewed; DC-F owner decision, public target and adoption remain pending.
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
