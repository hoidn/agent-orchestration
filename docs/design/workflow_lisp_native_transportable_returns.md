# Workflow Lisp Native Transportable Returns And Typed Result Guidance

- **Status:** accepted
- **Kind:** feature and frontend architecture decision
- **Owner:** Workflow Lisp frontend
- **Reviewers:** independent design review approved after three review passes;
  authoring surface approved by the user on 2026-07-10
- **Created:** 2026-07-10
- **Last material update:** 2026-07-13
- **Related docs:**
  - `docs/design/workflow_lisp_frontend_specification.md`
  - `docs/design/workflow_language_design_principles.md`
  - `docs/design/workflow_lisp_runtime_migration_foundation.md`
  - `docs/design/workflow_lisp_source_map.md`
  - `docs/reports/2026-06-19-workflow-lisp-type-runtime-boundary-issues.md`
  - `docs/plans/2026-07-10-workflow-lisp-native-transportable-returns-plan.md`
  - `docs/plans/2026-07-10-workflow-lisp-typed-result-guidance-plan.md`
  - `specs/dsl.md`
  - `specs/io.md`
  - `specs/providers.md`
- **Implementation target:** two independently reviewed implementation plans:
  native transportable returns first, then typed result guidance

## Summary

Workflow Lisp should use one typed return model across pure functions,
procedures, provider and command effects, workflow calls, and public workflow
boundaries. Every type already supported by the structured-result contract
system is valid in every return position. Authors no longer need to wrap a
`Bool`, enum, path, optional, list, or map in a one-field record merely to cross
an effect or workflow boundary.

Non-record and non-union results use a direct JSON root value. The compiler
projects that value through the existing `output_bundle` contract with an
empty JSON pointer and a compiler-owned `__result__` artifact. The provider
writes `true`, not `{"value": true}`. Workflow Lisp code sees the declared
`Bool`; only runtime state and debug projections expose `__result__`.

Optional result guidance is available without changing the return type. Plain
returns remain concise (`-> Bool`, `:returns Bool`). An annotated return uses
`(result Bool ...)`. Record and union fields receive the same description,
format-hint, and typed-example vocabulary. Guidance affects prompts and
human-facing contract information, while declaration metadata is checked at
compile time and never changes runtime value validity.

Overall workflow-return guidance has its own v2.15 top-level
`result_guidance` container. It is a sibling of `outputs`, not an output and
not a pseudo-field. The one container therefore describes the declared return
equally for a direct `__result__`, a flattened record, or a flattened union
without changing any output name, reference, artifact, or runtime value.

## Context And Authority

The parent Workflow Lisp frontend specification owns source-language return
semantics. The normative DSL, IO, and provider specs own executable bundle
shape, target binding, validation timing, and provider prompt delivery. This
document is a design delta; implementation must update those owning documents
rather than treating this file as the final runtime specification.

Current behavior is intentionally uneven:

- `defun` and inline `defproc` can return scalar values;
- `provider-result` and `command-result` reject anything other than a record
  or union;
- Stage-3 `defworkflow` signatures reject anything other than a record or
  union; and
- the lower-level `output_bundle` validator already supports the empty JSON
  pointer, scalar schemas, optionals, lists, maps, enums, and paths.

This design accepts the procedure-first direction that workflows are special
because they are public, resumable, observable effect boundaries, not because
they use a different value semantics.

### Feasibility evidence

The existing runtime already resolves `json_pointer: ""` to the complete JSON
document in `orchestrator/contracts/output_contract.py`. An isolated
2026-07-10 probe validated direct-root `Bool`, `List[Int]`,
`Map[String, Float]`, and `Optional[Bool]` documents through an ordinary
`output_bundle`, each producing `{"__result__": value}`. The probe passed
four of four cases.

This proves the root-value validator substrate. It does not prove compiler,
workflow-call, prompt, checkpoint, adjudication, or public-boundary support;
those remain implementation obligations and must receive production-path
integration evidence.

## Problem

Requiring a record or union at every durable boundary creates artificial data
types such as:

```lisp
(defrecord BoolResult
  (value Bool))
```

The wrapper is not domain structure. It exists only to satisfy a lowering
restriction. It leaks transport shape into source code, makes downstream code
write `.value`, and prevents functions, procedures, effects, and workflows
from sharing ordinary typed return semantics.

Removing only the typecheck guard is unsafe. Contract derivation, executable
bindings, runtime artifacts, workflow calls, source maps, prompt rendering,
resume, adjudication, dashboards, and migration parity currently assume named
record fields or tagged variants in several places. A language-wide change
therefore needs one explicit contract for source values and their runtime
projection.

Scalar returns also lack a field on which to attach semantic guidance. `Bool`
describes representation, but it does not explain whether `true` means
"approved", "retryable", or "complete". Native returns and typed-result
guidance must compose without making guidance part of type identity.

## Goals And Non-Goals

### Goals

- Permit every currently transportable Workflow Lisp type in function,
  procedure, effect, workflow-call, and public-workflow return positions.
- Use direct JSON root values for non-record and non-union structured results.
- Reuse `output_bundle` and its empty JSON pointer rather than introduce a
  second runtime value store or a new output primitive.
- Keep the runtime artifact inspectable under a stable compiler-owned name.
- Keep authored expressions typed as their declared return type; do not expose
  `__result__` in Workflow Lisp syntax.
- Preserve existing record and union contracts and behavior.
- Add optional root-return and payload-field guidance with typed examples.
- Preserve source attribution, resume reconstruction, deterministic state,
  validation-before-exposure, and stdout non-authority.
- Widen DSL v2.15's public workflow-output and guidance schemas so
  compiler-generated and authored mappings share one validation surface.
- Specify the normative DSL/provider documentation changes required by the
  generated contract.

### Non-goals

- Expanding the existing definition of transportability.
- Adding records or unions inside collection schemas where they are currently
  unsupported.
- Adding nested unions, arbitrary `Json`, runtime `Provider`, `Prompt`,
  `ProcRef`, `WorkflowRef`, or closure values to result transport.
- Introducing a new `value_output` DSL surface.
- Hiding results in an opaque runtime value store.
- Making return guidance affect type identity, specialization identity,
  routing, effects, optionality, or runtime validation.
- Encoding overall workflow-return guidance as a generated output, distributing
  it over flattened outputs, or adding a runtime value envelope.
- Automatically publishing a returned value as a separately named artifact.
- Adding enum-member or union-variant guidance in the first tranche. Overall
  result guidance and payload-field guidance are sufficient for this design;
  member/variant documentation can be designed separately.

## Decision

Use the existing `output_bundle` contract as the runtime transport for direct
root values. A non-record/non-union result lowers to exactly one generated
field:

```yaml
output_bundle:
  path: .orchestrate/generated/<allocated-result-path>.json
  fields:
    - name: __result__
      json_pointer: ""
      type: bool
```

The provider or command writes:

```json
true
```

`__result__` is compiler-owned but observable. It may appear in executable IR,
runtime plans, state, dashboards, diagnostics, and debug projections. Authored
Workflow Lisp never names or projects it. The compiler binds the validated
artifact directly to the source expression's declared type.

At a reusable/public workflow boundary, the compiler also declares exactly one
generated output named `__result__` for a root-valued return. Its `from` ref
points to the terminal producer artifact of the same name. A `call` copies that
declared callee output onto the outer call-step artifact map under
`__result__`; the Workflow Lisp call expression binds that artifact directly as
the declared type. The name remains invisible in Workflow Lisp even though it
is visible in executable mappings and state.

DSL v2.15 widens public workflow `outputs` to the same transportable
leaf/collection schemas already used by frontend-lowered contracts. This is a
deliberate normative widening, not a compiler-only loader exception. Existing
DSL versions retain their current authored-YAML restrictions. Workflow Lisp
sources using root-valued public returns declare `(:target-dsl "2.15")`.

The alternatives are rejected:

- A new `value_output` contract is semantically clean but duplicates loader,
  runtime, state, adjudication, resume, dashboard, and documentation surfaces.
- A hidden object envelope (`{"value": true}`) reduces compiler work but
  violates direct-wire semantics and retains a transport-only field.
- An artifact-free runtime value store makes state and resume less inspectable
  and creates a second authority path.

## Transportable Result Types

Implementation must define one shared `is_transportable_result_type(type_ref)`
decision derived from structured-result contract lowering, not maintain
separate allowlists for workflows, providers, commands, and procedures.

The accepted first-tranche families are:

- `String`, `Int`, `Float`, and `Bool`;
- enums;
- declared path refinements;
- `Optional[T]` where `T` is supported by the existing structured-result
  schema rules;
- `List[T]` and `Map[String, T]` under the existing collection-element rules;
- records; and
- unions.

Compiler-only, effect-capability, dynamically shaped, or otherwise unsupported
types remain non-transportable. A declaration using one receives a stable
compile-time diagnostic before lowering.

Transportability is about contract derivability. Guidance never makes an
otherwise non-transportable type transportable.

## Return And Wire Mapping

| Declared return | Authoritative JSON root | Executable contract |
| --- | --- | --- |
| `Bool` | JSON boolean | root `output_bundle` field |
| `Int`, `Float` | JSON number | root `output_bundle` field |
| `String`, enum, path | JSON string | root `output_bundle` field |
| `Optional[T]` | `null` or the JSON form of `T` | root optional schema |
| `List[T]` | JSON array | root list schema |
| `Map[String,T]` | JSON object | root map schema |
| record | existing JSON object | existing flattened `output_bundle` |
| union | existing tagged JSON object | existing `variant_output` |

The result bundle file is always required. For `Optional[T]`, `null` means
`None`; absence of the file is still a contract failure. A direct path return
is a JSON string and retains all declared path-root and existence validation.

## Language Surface

### Plain returns

Unannotated returns retain existing syntax:

```lisp
(defproc is-approved
  ((review ReviewResult))
  -> Bool
  :effects ()
  :lowering inline
  review.approved)
```

```lisp
(provider-result providers.review
  :prompt prompts.review
  :inputs (patch)
  :returns Bool)
```

`(result Bool)` without annotations is accepted but canonical authoring and
debug rendering should simplify it to `Bool`.

### Guided returns

`result` is a return-position annotation form, not a general type constructor:

```lisp
(provider-result providers.review
  :prompt prompts.review
  :inputs (patch)
  :returns
    (result Bool
      :description "True only when no blocking findings remain."
      :format-hint "Write a JSON boolean, not a quoted string."
      :example true))
```

The same form is valid after `->` in `defun`, `defproc`, and `defworkflow`.
It elaborates to a `ReturnSpec` containing a type reference plus optional
guidance. Typechecking and downstream expressions see only the type reference.

Effect-boundary guidance and workflow-return guidance have different audiences
and do not implicitly overwrite each other:

- guidance on `provider-result` or `command-result` describes the value the
  external producer must write;
- guidance on `defworkflow` describes the caller/public boundary; and
- guidance on a helper or procedure documents its callable result.

When a `defworkflow` or effectful `defproc` becomes a shared workflow mapping,
its overall return guidance lowers to top-level `result_guidance`. It does not
move onto `outputs.__result__` for a scalar and is not repeated on
`return__*` outputs for a record or union. Effect-boundary guidance remains on
the producing step's `output_bundle` or `variant_output`; the two containers
may coexist because they describe different boundaries.

### Field guidance

Record and union payload fields accept the corresponding optional metadata:

```lisp
(defrecord ReviewResult
  (approved Bool
    :description "True exactly when the review found no blockers."
    :example true)
  (score Float
    :description "Confidence in the decision, from 0.0 through 1.0."
    :format-hint "Inclusive range [0, 1]."
    :example 0.91))
```

Accepted keys are `:description`, `:format-hint`, and `:example`. Unknown or
duplicate keys fail compilation at the authored annotation. Description and
format-hint values are non-empty strings.

An example is a compile-time constant expression. It must evaluate without
effects or runtime references and must validate against the declared type's
structured-result schema. Composite examples are accepted only when the
existing constant-expression surface can represent them. A path example is
checked for type and path safety but does not require its target to exist at
compile time. Unsupported example syntax receives a guidance-specific
diagnostic; it never weakens the value contract.

Guidance declaration validation may reject a source program. Once valid,
guidance does not change the return type, requiredness, accepted runtime values,
specialization identity, semantic fingerprints, proof rules, routing, effects,
or resume behavior.

### Guidance composition

Guidance belongs to the authored declaration that contains it. Composition is
deterministic:

- a `defschema` field retains its guidance when included in a record or union
  variant;
- schema inclusion does not create an override layer; an included field and a
  local field with the same name remain a duplicate-field error under the
  existing schema rules;
- imports and generic specialization preserve guidance without adding it to
  type or specialization identity;
- a flattened leaf retains its own guidance, while guidance from annotated
  record-valued ancestor fields is carried separately as an ordered
  `guidance_context` keyed by authored field path; strings are never
  concatenated implicitly;
- an ancestor example, when valid, remains an example of that ancestor value
  and is not reinterpreted as a leaf example; and
- runtime shared-field classification ignores guidance metadata. If the same
  shared union field has different guidance in different variants, the
  executable contract retains one runtime field schema plus
  `guidance_by_variant`. Identical guidance may be deterministically deduplicated.

Variant-specific fields keep their own guidance. A selected variant controls
runtime validation and source attribution, while the provider prompt presents
variant-keyed guidance before the provider chooses the discriminant. Guidance
differences must never turn one structurally shared field into conflicting
active/inactive runtime fields.

## Compiler And IR Design

### Shared return checking

`defworkflow`, effectful `defproc` lowering, `provider-result`,
`command-result`, and workflow calls must consume the same transportability and
result-contract derivation APIs. Removing individual record/union guards
without consolidating these APIs is not conforming implementation.

The compiler classifies each result contract as one of:

- `root_value`;
- `record_value`; or
- `union_value`.

This classification is structural and type-driven. It must not branch on
workflow, provider, procedure, module, or domain names.

The classification is a new `result_shape` contract property. It is distinct
from the existing `WorkflowBoundaryProjection.return_kind` compatibility key:
that key retains `record` and `union` for existing projections and adds `root`
for the new boundary. Consumers must not silently reinterpret the old key as
the new three-value classification.

### Binding and projection

A root-valued provider or command step produces the runtime artifact
`__result__`. WCC/classic lowering, lexical checkpoints, join points, workflow
calls, and procedure composition bind that artifact directly as the typed
source value. No authored `.value` or `.__result__` projection is introduced.

A scalar-returning workflow call therefore behaves as an ordinary expression:

```lisp
(let* ((approved (call review-change :patch patch)))
  (if approved ...))
```

The same rule applies at a public `defworkflow` boundary. Public/resumable
workflow behavior remains special operationally, but its returned value uses
the same type and contract derivation as an internal procedure.

The executable workflow boundary is explicit rather than inferred:

```yaml
outputs:
  __result__:
    kind: scalar
    type: bool
    from:
      ref: root.steps.<terminal-step>.artifacts.__result__
```

Optional/list/map roots use the widened collection output schema; paths use the
existing relpath output schema. A pure literal, pure expression, conditional
join, or loop result that lacks an existing producing artifact is materialized
through the ordinary compiler-generated typed projection step. That step writes
the direct JSON root and exposes `artifacts.__result__`; it does not introduce
an object envelope. Persisted workflow outputs are finalized only under the
existing success/finalization rules, and resumed calls reconstruct the outer
call artifact from the declared callee output exactly as for existing named
outputs.

Returning a value does not by itself add a separately named publication. Any
public artifact publication remains explicit boundary policy over the returned
typed value.

### Semantic and executable representations

Semantic IR records the authored type and optional return guidance. It does not
pretend the source value is a record with a `__result__` field.

The normalized public/callable-boundary payload is carried without
reinterpretation through the shared pipeline:

- `SurfaceWorkflow.result_guidance` owns the validated authored-shape payload;
- `CoreWorkflowAST.result_guidance` preserves it as workflow-root metadata;
- `SemanticWorkflow.result_guidance` records it beside that workflow's output
  contract identifiers; and
- `ExecutableWorkflow.result_guidance` preserves the validated metadata for
  executable/build inspection while runtime execution ignores it.

The Core, Semantic, and Executable JSON projections emit `result_guidance`
only when it is present. This is an additive optional metadata field, so their
current internal `*.v1` schema identifiers remain unchanged and unannotated
serialized artifacts remain byte-equivalent. There is no runtime-plan copy.
Any future reader that makes those projection schemas closed must trigger a
separate schema-version review before this field is added to that reader.

Executable IR and runtime-plan projections may record:

- result shape `root_value`;
- generated bundle path;
- hidden artifact name `__result__`;
- JSON pointer `""`;
- schema; and
- source-map subject.

Debug YAML is a projection of this executable contract and is never semantic
authority.

### Source maps and diagnostics

Root and fixed-bundle fields extend the accepted contract-field lineage with
`subject_kind = "output_bundle_field"`. The stable root subject name is:

```text
<generated-step-id>::root-result::__result__
```

`ValidationSubjectRef.workflow_name` continues to carry canonical workflow
identity, so the subject name is opaque outside equality and lookup. A root
subject's origin is the authored `(result ...)` form when present, otherwise
the authored return type token in `:returns` or after `->`.

The source-map builder persists these subjects in the existing additive
`contract_fields` section with `entity_kind = "output_bundle_field"`, and
`validation_subjects` maps each subject to that origin. Classic and WCC origin
maps, inline procedure child contexts, clone/rekey logic, the Semantic IR
source-map bridge, and `CompiledFrontendIndex` must support both
`variant_output_field` and `output_bundle_field`. Older v1 maps without the new
subjects remain valid; unresolved subjects retain the enclosing-step fallback.

The generated workflow boundary output separately uses the existing
`generated_output` subject and points to the same authored return occurrence.
Runtime value violations resolve through `output_bundle_field`; call/export
boundary diagnostics resolve through `generated_output`. Runtime diagnostics
should display "return value" and the authored type rather than requiring users
to understand `__result__`.

Diagnostics must distinguish:

- a non-transportable declared return type;
- malformed result guidance;
- an example incompatible with the declared type;
- a missing or invalid root bundle; and
- a runtime root value that violates its schema.

Expansion stacks, module ownership, specialization origins, and generated-step
identity remain available through the normal source-map path.

## Output Contract And Prompt Design

The `output_bundle` contract remains the only runtime authority for root-valued
provider and command results. `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` target binding,
parent preparation, post-success validation, wrong-path failure, and stdout
non-authority remain unchanged.

The prompt renderer must stop assuming every `output_bundle` is a JSON object.
For a root field it renders one JSON value and its root schema, for example:

```text
Write one JSON value to ORCHESTRATOR_OUTPUT_BUNDLE_PATH.
Expected root type: bool.
Description: True only when no blocking findings remain.
Example: true
```

Examples are rendered as canonical JSON, not Python representations. Optional,
list, map, enum, and path constraints come from the same schema used at runtime.

Generated wire guidance uses:

- field-level `description`, `format_hint`, and JSON-native `example` for a
  root `__result__` field or a record/variant payload field; and
- optional bundle-level `guidance` for overall record or union return
  guidance.

The loader and shared validation layer must validate guidance metadata even
though runtime result validation ignores it. This keeps authored YAML and
compiler-generated executable mappings on one checked contract surface.

Bundle and field guidance is additive public DSL v2.15 support, not
compiler-only metadata. That version adds:

- `description`, `format_hint`, and JSON-native `example` to
  `output_bundle.fields`, `variant_output.shared_fields`, and variant fields;
- `guidance_by_variant` for structurally shared union fields whose authored
  guidance differs;
- ordered `guidance_context` for flattened nested-field ancestry; and
- optional bundle-level `guidance` for overall record/union return guidance.

### Guidance wire schema

The v2.15 guidance containers use one closed `GuidancePayload` vocabulary:

```yaml
description: string       # optional, non-empty
format_hint: string       # optional, non-empty
example: <JSON value>     # optional
guidance_context:         # optional, field payloads only
  - json_pointer: /parent # required RFC 6901 pointer
    description: string   # optional, non-empty
    format_hint: string   # optional, non-empty
    example: <JSON value> # optional
```

A payload must contain at least one of `description`, `format_hint`, `example`,
or a non-empty `guidance_context`. Unknown keys are invalid. Every context row
must contain at least one guidance value in addition to `json_pointer`.

At a provider or command effect boundary, overall record/union result guidance
appears at bundle level:

```yaml
output_bundle:
  path: ...
  guidance:
    description: Complete review result.
    example:
      approved: true
      score: 0.91
  fields: ...
```

`variant_output.guidance` has the same shape. Bundle-level `guidance_context`
is forbidden because the bundle guidance already describes the root.

Overall workflow/callable-return guidance instead appears once at workflow
root, alongside `outputs`:

```yaml
version: "2.15"
name: review-change
outputs:
  return__approved:
    kind: scalar
    type: bool
    from: {ref: root.steps.review.artifacts.approved}
  return__score:
    kind: scalar
    type: float
    from: {ref: root.steps.review.artifacts.score}
result_guidance:
  description: Complete review result.
  format_hint: Return the final adjudicated review.
  example:
    approved: true
    score: 0.91
```

`result_guidance` uses the same closed root payload vocabulary:
`description`, `format_hint`, and JSON-native `example`. It must be a non-empty
mapping; descriptions and format hints must be non-empty strings; unknown keys
and `guidance_context` are invalid. The `example` key counts as present even
when its value is JSON `null`. The container requires at least one declared
workflow output but does not require a particular output count or name.

The shared loader checks only JSON compatibility for a top-level example,
because flattened public outputs do not retain one unflattened record/union
schema. Workflow Lisp compilation additionally checks the example against the
authored declared return type before lowering. The container is accepted only
for DSL v2.15 and later; earlier versions reject it as an unknown/versioned
field. It is caller- and human-facing metadata, not provider-step prompt
guidance, and never participates in output validation, call binding,
publication, routing, resume, checkpoint identity, or runtime state.

An ordinary fixed/root field places guidance keys directly on its field spec:

```yaml
fields:
  - name: __result__
    json_pointer: ""
    type: bool
    description: True only when no blocking findings remain.
    example: true
```

Nested ancestry remains a separate ordered list:

```yaml
fields:
  - name: blocker__class
    json_pointer: /blocker/class
    type: enum
    allowed: [MISSING_RESOURCE, EXTERNAL_DEPENDENCY]
    guidance_context:
      - json_pointer: /blocker
        description: The blocker preventing completion.
    description: Stable blocker classification.
```

Context `json_pointer` values use decoded authored field paths encoded as
ordinary RFC 6901 pointers. Each must be a unique proper prefix of the field's
own pointer. Rows are ordered from the shallowest prefix to the deepest; the
loader rejects duplicates, non-prefixes, equal-to-leaf pointers, and
out-of-order depths. A root field (`json_pointer: ""`) cannot declare
`guidance_context`.

When a structurally shared union field has different complete guidance payloads
across variants, the field uses `guidance_by_variant`:

```yaml
shared_fields:
  - name: score
    json_pointer: /score
    type: float
    guidance_by_variant:
      APPROVED:
        description: Confidence in the approval decision.
        example: 0.95
      REVISE:
        description: Confidence that revision is necessary.
        example: 0.80
```

Each key must be one of the discriminant's declared variants. Keys are emitted
in discriminant `allowed` order. Omitted variants have no guidance. Every
variant payload follows the field `GuidancePayload` schema, including optional
`guidance_context`, and each `example` is checked against the shared field
schema.

`guidance_by_variant` is mutually exclusive with direct `description`,
`format_hint`, `example`, and `guidance_context` on the same shared field.
Compiler canonicalization compares complete normalized payloads using deep JSON
equality with absent optional keys omitted:

- if every variant has the same non-empty payload, emit it once as direct field
  guidance and omit `guidance_by_variant`;
- otherwise emit `guidance_by_variant` for exactly the variants with non-empty
  payloads and omit all direct field guidance; and
- if no variant has guidance, emit neither form.

For field and variant payloads, the loader validates `example` through that
field's declared schema. For bundle-level guidance, the loader validates only
that `example` is JSON-compatible because the public DSL does not carry one
unflattened record/union schema; Workflow Lisp compilation additionally checks
the example against the authored return type before lowering. Context examples
receive the same two-layer treatment: JSON compatibility in the loader and
typed ancestor-field validation in the Workflow Lisp compiler.

The loader validates this metadata and rejects it on older authored DSL
versions. Prompt composition renders it; output-contract value validation
ignores it. Compiler-generated and authored mappings therefore share one
normative schema and do not depend on unknown-key tolerance.

Native returns and typed result guidance are one v2.15 release contract even
though implementation is split into sequential plans. The v2.15 capability is
not promoted as complete until both plans and their shared normative spec gate
pass; this prevents a released version from changing its accepted guidance
keys between the two implementation waves.

## Contracts And Interfaces

### Workflow Lisp frontend

Old:

- `defworkflow`, `provider-result`, and `command-result` require a record or
  union return.

New:

- all return sites accept any currently transportable type;
- `(result T ...)` optionally annotates a return occurrence; and
- record/union payload fields may carry typed guidance.

### Executable DSL

Old documentation describes `output_bundle` as a JSON object containing named
field pointers.

New documentation must explicitly allow any JSON document root and define
`json_pointer: ""` as selecting that root. Field and bundle guidance are
prompt-only metadata with schema validation but no value-validation impact.
Top-level `result_guidance` is the separate overall workflow-return metadata
container and is not part of any output definition.

DSL v2.15 also widens public `outputs` contract definitions to optional, list,
and map schemas under the same element restrictions as the frontend contract
system. Existing scalar, enum, relpath, record-flattened, and union-flattened
boundaries remain compatible. This widening is required for a public Workflow
Lisp workflow returning a collection to cross an ordinary `call` boundary
without a compiler-private validation path. Workflow input widening is outside
this design; existing Workflow Lisp/compiler-private collection input rules
remain governed by their current contract.

### Runtime state

Root-valued results are persisted as ordinary step artifacts:

```json
{
  "steps": {
    "<generated-step>": {
      "artifacts": {
        "__result__": true
      }
    }
  }
}
```

This name is observable but compiler-owned. Workflow Lisp authors bind the
typed expression result and do not reference this state path.

For a reusable workflow, the callee's finalized output map and the caller's
outer call-step artifact map both use the same generated `__result__` key. The
compiler consumes that key when rebuilding the typed call expression; authored
Workflow Lisp and public publication names remain independent of it.

## Dependencies And Sequencing

The design depends on the existing output-bundle validator, runtime-owned
bundle target, typed contract derivation, source-map field lineage, and WCC
value binding substrate. The root validator feasibility is proven; the other
cross-boundary paths require implementation tests.

Implementation should be split into two independently reviewable plans:

1. **Native transportable returns:** return checking, root contract derivation,
   lowering, value binding, runtime consumers, source maps, compatibility, and
   end-to-end evidence.
2. **Typed result guidance:** `(result ...)`, field annotations, compile-time
   metadata validation, prompt rendering, normative guidance schema, and docs.

The native-return substrate must land first. Typed result guidance then uses
the accepted root contract instead of inventing a parallel transport. Both
must complete before a procedure-first pilot depends on direct scalar returns.
Native-return acceptance fixtures use plain `:returns T` / `-> T` and contain
no guidance metadata; guidance fixtures are added only by the dependent plan.

Within typed-guidance implementation, canonical provider/command bundle
guidance and top-level `result_guidance` carriage must land before the public
v2.15 loader schema and renderer promotion. The loader cannot validate a
container the frontend cannot yet carry through Surface, Core, Semantic, and
Executable IR.

Structural contract derivation also has two explicit production APIs. The
ordinary `derive_structured_result_contract(...)` is guidance-free: it never
reads root or definition-field guidance and never requires a type environment.
Provider and command prompt contracts use
`derive_prompt_guided_structured_result_contract(...)`, which requires the
resolved type environment and may normalize root, field, ancestor, and variant
guidance. Both delegate to one structural derivation implementation. This
keeps reusable-state fingerprints, materialization contracts, phase helpers,
and other runtime-only callers independent of authoring metadata while making
guided callers opt in visibly.

Planning may be drafted before the active migration sequence completes, but
implementation must honor the roadmap's compiler/runtime freeze and rebaseline
against the post-migration owning modules before execution.

## Invariants And Failure Modes

- The declared source type is semantic authority; `__result__` is transport.
- The bundle file is authority; stdout and prompt prose are not.
- The bundle is validated before artifacts become visible or resumable.
- A missing bundle fails even for `Optional[T]`; JSON `null` represents `None`.
- Wrong root type fails closed and points to the authored return declaration.
- Guidance declaration validation is compile-time; valid guidance never changes
  runtime value validation.
- Top-level `result_guidance` is metadata beside `outputs`; it never creates,
  renames, wraps, or changes an output.
- Guidance-free contract derivation cannot evaluate examples or require a
  `FrontendTypeEnvironment`; prompt-guided derivation must receive one.
- Record and union variant proof rules are unchanged.
- Existing record/union routes must not silently switch contract shapes.
- Hidden artifacts retain source ownership, debug visibility, and resume
  reconstruction.
- Classic and WCC lowering must agree or the feature cannot be promoted.
- No consumer may special-case a workflow or domain name to support root
  values.

## Security, Operations, And Performance

The design adds no provider authority, filesystem permission, credential, or
network surface. Bundle path safety and runtime-owned target binding remain
unchanged.

Prompt guidance may contain author-supplied text and examples. It is already
inside the trusted workflow prompt-authoring boundary and must be rendered as
data, not interpreted as runtime configuration. Dashboards must continue
escaping displayed values and guidance.

Each result still uses one bundle file and one validation pass. Scalar roots
reduce JSON structure slightly; no meaningful performance cost is expected.
Build artifacts gain small result-shape and guidance metadata.

## Evidence And Implementation Boundaries

Conforming evidence must exercise production compilation through shared
validation and the ordinary executor. Direct calls to
`validate_output_bundle(...)` prove only validator feasibility.

The following do not prove completion by themselves:

- a hand-authored YAML root bundle;
- a direct validator unit test;
- debug YAML containing `__result__`;
- a compiler fixture that never executes;
- a mock that writes a wrapper object; or
- stdout containing the expected scalar.

Promotion evidence must show an authored `.orc` program producing a root-valued
provider or command contract, executing it through the runtime, reconstructing
the typed value, and consuming it in source-language control flow.

## Compatibility And Migration

The change is additive for source authoring. Existing record and union programs
remain valid. Their generated contracts, artifact names, output paths, source
identities, checkpoint identities, and runtime behavior should remain
byte-equivalent where deterministic serialization makes that measurable.

The current validator already understands empty JSON pointers, but a v2.14
runtime does not accept the new DSL version, widened public outputs, or guidance
schema. Native-return workflows therefore require a v2.15-capable compiler,
loader, and runtime. Existing v2.14 record/union workflows remain on their
current contracts and do not acquire new metadata implicitly.

Build/executable artifact schema versions must be bumped only if persisted IR
shape actually changes; the implementation plan must audit readers rather than
assume either compatibility or incompatibility. The DSL version decision is
not open: the public contract changes are v2.15.

No existing wrapper record is automatically rewritten. Authors may migrate a
one-field wrapper to a direct return deliberately after downstream callers and
parity expectations are updated.

Rollback consists of returning callers to wrapper types. Existing record and
union behavior must not depend on the new root-valued route, so rollback does
not require runtime state conversion for unchanged workflows.

## Verification Strategy

### Type and contract tests

- Positive cases for every currently transportable family at each newly
  widened return boundary.
- Negative cases for capability types, `Json`, unsupported composite shapes,
  and incompatible body/result types.
- Contract derivation for scalar, enum, path, optional, list, and map roots.
- Record and union contract-regression comparisons.

### Lowering and composition tests

- Classic and WCC `provider-result` and `command-result` routes.
- Pure and effectful procedure returns.
- Same-file and imported workflow calls returning a root value.
- Nested `let*`, `if`, `match`, loop/join, and procedure composition where the
  existing expression surface permits the returned type.
- No authored projection through `__result__`.

### Runtime and state tests

- Direct root JSON validation and artifact exposure.
- Missing file, invalid JSON, wrong type, invalid enum, unsafe path, malformed
  collection, and optional `null` failures/successes.
- Resume and lexical-checkpoint reconstruction.
- Runtime plan and dashboard handling of empty JSON pointers.
- Adjudicated provider evidence, promotion, rollback, and resume.
- Migration parity and artifact-lineage projections.

### Guidance tests

- Plain return syntax remains canonical and unchanged.
- `(result T ...)` parsing, elaboration, type erasure, and diagnostics.
- Field annotation propagation through schemas, imports, specialization,
  nested-record flattening, and union shared/variant fields.
- Typed examples and canonical JSON prompt rendering.
- Annotated and unannotated contracts accept exactly the same runtime values.
- Tests assert structured metadata and behavior, not literal prompt prose.

### Integration and end-to-end checks

- Compile and run a real `.orc` provider workflow returning `Bool`.
- Branch directly on the returned value.
- Compile and call a workflow returning a collection root.
- Run one command-result root case.
- Run one adjudicated-provider root case.
- Exercise the production build, shared loader, prompt composition, executor,
  state persistence, and resume path.

## Declarative Acceptance Scenarios

### Provider boolean drives control flow

Given an authored workflow containing:

```lisp
(let* ((approved
         (provider-result providers.review
           :prompt prompts.review
           :inputs (patch)
           :returns
             (result Bool
               :description "True only when no blocking findings remain."
               :example true))))
  (if approved approved-result revise-result))
```

when the provider writes the JSON document `true` to the runtime-owned bundle
path, the output contract validates, runtime state records
`artifacts.__result__ = true`, the source binding has type `Bool`, and the
approved branch executes. No wrapper object, stdout parsing, authored hidden
artifact reference, or name-specific lowering is involved.

When the provider writes `{"value": true}`, validation fails because the JSON
root is not a boolean. The diagnostic resolves to the authored return spec.

### Optional collection workflow return

Given a workflow returning `Optional[List[String]]`, JSON `null` produces
`None`, a JSON array of strings produces the typed list, and a missing bundle
fails. A caller receives the direct typed value without a one-field record.

The compiled callee declares `outputs.__result__` from the terminal producer's
`artifacts.__result__`. The runtime call step exposes the same artifact key, and
the caller compiler binds it as `Optional[List[String]]`. A pure or join-produced
list first passes through the ordinary typed materialization step; no test-only
adapter or object envelope may satisfy the scenario.

### Existing union remains unchanged

Given an existing provider workflow returning a tagged union, compilation and
execution continue through `variant_output`, with identical discriminant,
shared-field, variant-field, proof, and forbidden-field behavior. The new root
route is not selected.

## Success Criteria

- One shared transportability decision governs every widened return boundary.
- All currently transportable types are accepted in those positions.
- Direct roots use one `output_bundle` field named `__result__` and pointer
  `""`.
- Authored code receives the declared type and never references the hidden
  artifact.
- Provider and command prompts accurately request a JSON root value.
- Root and field guidance are validated, source-mapped, and rendered without
  changing runtime validity.
- Scalar, record, union, and private-procedure workflow returns retain one
  overall `result_guidance` payload through Surface, Core, Semantic, and
  Executable IR without changing the output map.
- Public workflow calls, runtime state, resume, adjudication, dashboards, and
  parity consumers handle root values.
- Existing record and union behavior is non-regressive.
- Normative DSL, IO/provider, frontend, drafting, status, and roadmap documents
  agree on the contract.
- Production-path integration and end-to-end checks pass with fresh output.

## Stop / Revise Criteria

Revise this design if implementation requires any of the following:

- a second runtime value authority outside output contracts and artifacts;
- provider stdout as a result fallback;
- authored access to `__result__` in Workflow Lisp;
- name-specific compiler branches;
- weakened record/union validation or variant proof;
- checkpoint identity changes for unchanged programs without a reviewed
  compatibility decision;
- treating guidance as runtime semantic authority; or
- expanding composite transport beyond current rules without a separate
  accepted design.

## Documentation Impact

Implementation requires coordinated updates to:

- `docs/design/workflow_lisp_frontend_specification.md`;
- `docs/design/workflow_lisp_type_catalog.md`;
- `docs/design/workflow_lisp_source_map.md`;
- `docs/lisp_workflow_drafting_guide.md`;
- `specs/dsl.md`;
- `specs/io.md` when root-target or command wording needs clarification;
- `specs/providers.md`;
- `specs/versioning.md` and the v2.15 accepted-version/schema tables;
- `docs/capability_status_matrix.md`;
- `docs/design/README.md` and `docs/index.md`;
- executable/debug schema documentation if serialized IR changes; and
- the procedure-first roadmap and its plan routing.

## Implementation Handoff

The safe first implementation step is to add declarative RED tests for a
root-valued `Bool` across frontend typechecking, contract derivation, prompt
metadata, runtime validation, source attribution, and workflow-call binding.
Then introduce the shared transportability/result-contract model before
widening individual effect or workflow guards.

Suggested native-return phases:

1. shared result type and contract model;
2. provider/command root lowering and prompt shape;
3. workflow/procedure/call binding across classic and WCC routes;
4. source maps, runtime plans, state, resume, dashboard, and adjudication;
5. compatibility and end-to-end evidence; and
6. normative and authoring documentation.

Suggested guidance phases:

1. `ReturnSpec` and field metadata syntax;
2. compile-time metadata/example validation;
3. schema/import/specialization/flattening propagation;
4. executable guidance schema and prompt rendering;
5. runtime-neutrality and end-to-end evidence; and
6. documentation and capability promotion.

Plans must name exact owning modules after the current migration sequence and
must use narrow tests before integration, smoke, parity, and broader gates.

## Open Questions

No open question blocks the core design. The implementation plans must still
audit whether persisted frontend/executable artifact schemas require a version
bump and record the evidence-based decision before changing serialization.
