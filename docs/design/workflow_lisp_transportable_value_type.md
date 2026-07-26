# Workflow Lisp Transportable `Value` Type

- **Status:** accepted prerequisite (owner-selected 2026-07-26)
- **Review:** `VALUE_DESIGN_SPEC_APPROVED`, then
  `VALUE_DESIGN_QUALITY_APPROVED`
- **Kind:** language and transport contract
- **Owner:** Workflow Lisp frontend plus shared output-contract runtime
- **Target:** DSL `2.19`
- **Selected consumer:** the first prompt-calculus tranche, whose unstated
  return type defaults to `Value`
- **Related authority:**
  - `docs/design/workflow_language_design_principles.md`, principle 29
  - `docs/design/workflow_lisp_native_transportable_returns.md`
  - `docs/design/workflow_lisp_frontend_specification.md`
  - `docs/design/workflow_lisp_prompt_calculus.md`
  - `specs/dsl.md`
  - `specs/io.md`
  - `specs/providers.md`
  - `specs/versioning.md`

## Decision

Add `Value` as an opt-in top type for values that cross Workflow Lisp
transport boundaries. `Value` accepts any JSON value:

- `null`;
- a boolean;
- an integer or finite floating-point number;
- a string;
- a list whose members are recursively valid `Value` values; or
- an object with string keys and recursively valid `Value` values.

`Value` is deliberately loose. Declaring it chooses only the guarantee that
the value is transportable JSON. It provides no record fields, union variants,
path containment, enum membership, or collection-element contract.

The compiler lowers `Value` through the existing direct-root carriage:

```yaml
output_bundle:
  path: .orchestrate/generated/<allocated-result-path>.json
  fields:
    - name: __result__
      json_pointer: ""
      type: value
```

The producer writes the value directly. An object is written as an object, a
boolean as a boolean, and `null` as `null`; there is no authored or hidden
`{"value": ...}` envelope. Runtime state and debug projections may expose the
existing compiler-owned `__result__` artifact name, while Workflow Lisp source
sees only `Value`.

`value` becomes a public output-contract descriptor at DSL `2.19`. Earlier
targets reject both the source type and the descriptor. Existing narrower
descriptors and their validation are unchanged.

At public workflow boundaries, the corresponding contract kind is
`kind: value`. Reusing `scalar` or `collection` is rejected because the
classification would depend on one attempt's payload shape. `kind: value` is
target-gated with the `value` descriptor and means opaque pass-through under
the recursive transport contract; it grants no scalar or collection
operations.

## Why A New Type

The existing prelude name `Json` is not this contract. `Json` is intentionally
excluded from workflow boundaries and structured-result contracts. Widening it
would retroactively change existing programs and erase the distinction between
an internal opaque JSON carrier and an authored transport promise.

A generated union of every transportable family is also rejected. It would
turn a loose boundary into a mandatory taxonomy, require new variants whenever
the language gains a transportable shape, and conflict with principle 29.

`Value` is a distinct, target-gated contract whose looseness is visible where
the author chooses it.

## Type Rules

### Introduction

`Value` is a top **transport contract**, not an implicit source-language
subtyping rule. A provider, command, workflow input, or callable explicitly
declared as `Value` introduces a `Value`; that value may be forwarded,
returned, persisted, and resumed through other positions declared `Value`.

Source compatibility remains exact:

```text
Value -> Value     accepted
T -> Value         rejected for every narrower T
Value -> T         rejected for every narrower T
```

The first rejection is intentional. Records and unions currently cross public
boundaries through flattened/variant carriage. Silently treating either as a
whole-root `Value` would require a new rematerialization and coercion subsystem,
change artifact identity, and hide runtime work behind an apparent type
relation. No selected prompt-calculus consumer needs that conversion.

The second rejection preserves fail-closed narrowing. A `Value` expression may
not flow into `Bool`, a record, a union, a path family, or any other narrower
position without a separately designed checked narrowing operation. This
tranche adds no cast, decoder, field projection, match proof, dynamic type
test, or source constructor that erases a narrower value to `Value`.

The "contracts may only narrow" principle applies across authored contract
revisions: an exploratory `Value` result may later be changed to a concrete
type once consumers need that guarantee. It does not authorize an unchecked
same-program conversion from `Value` to that type.

### Availability And Shadowing

`Value` is a compiler-owned prelude type only for target `2.19` and later. A
local or imported definition may not shadow it. Use on an older target fails
at the authored type occurrence with `value_type_requires_dsl_2_19`.

`Value` is transportable but is not a capability type, reference type, prompt
type, procedure type, workflow-reference type, or nominal identity. It does
not satisfy record/union structural constraints because it makes none of
their guarantees.

### Type Identity

`Value` remains visible in typed AST, Core AST, semantic IR, build manifests,
source maps, callable signatures, and checkpoint identities. It is not
normalized to `Json`, to an anonymous union, or to the concrete runtime shape
observed on one attempt.

Runtime contents never specialize a `Value` signature. Two executions that
produce different JSON shapes retain the same authored type identity while
their ordinary artifact bytes and value digests remain different.

## Where `Value` Is Allowed

At target `2.19`, an exact `Value` declaration is valid anywhere the shared
transportability decision is the governing rule:

- function and procedure parameters and returns;
- workflow parameters and public returns;
- `provider-result` and `command-result` returns;
- workflow-call arguments and results;
- record and union payload fields;
- `Optional[Value]`, `List[Value]`, and `Map[String, Value]`; and
- typed prompt inputs whose existing carriage accepts the resolved value.

Existing form-specific restrictions still apply. For example, a control form
that requires `Bool` does not accept `Value`, a `match` subject still requires
variant proof, a rooted-path consumer still requires its declared path type,
and a loop-state or provider-group surface does not become eligible merely
because its payload is labeled `Value`.

## Runtime Validation

The shared output-contract runtime owns recursive `value` validation. It
returns an equivalent JSON-like Python value without string coercion:

- booleans stay booleans rather than integers;
- integers stay integers;
- finite floats stay floats;
- strings remain exact strings;
- lists preserve order; and
- objects preserve keys and recursively validated values.

Bundle parsing is strict JSON. The `Value` path must reject the non-standard
Python JSON constants `NaN`, `Infinity`, and `-Infinity` at parse time, and the
recursive validator must independently reject non-finite in-memory floats.
This closes both file-backed and internal validation entry points. A
recursively non-transportable value fails with
`invalid_transportable_value`, including the first invalid value path.

`null` is a valid `Value`, unlike absence:

- a bundle containing JSON `null` at the selected pointer succeeds;
- a missing required bundle file fails;
- a missing non-root JSON pointer fails; and
- optional-field absence keeps its existing `Optional` semantics.

The loader admits `type: value` and public-boundary `kind: value` for workflow
inputs, outputs, artifacts, and structured output-bundle fields only at target
`2.19` or later. Every switch that currently partitions `scalar`,
`collection`, and `relpath` must either pass `kind: value` through opaquely or
issue a coded refusal when a narrower operation is requested. The same
descriptor flows through input resolution, artifact refs, state, resume
reconstruction, imported bundles, dashboard/debug projection, and
semantic/executable IR without a second value store.

## Provider Contract And Guidance

Provider contract rendering describes `Value` as one direct JSON value and
does not invent fields. Optional root guidance remains allowed:

```lisp
(result Value
  :description "Return any JSON value useful to the exploratory caller."
  :format-hint "Write one JSON value at the document root.")
```

The Q0 tranche does not admit `:example` on `Value`. Existing examples are
typed source expressions; with exact source compatibility and no erasing
constructor, an ordinary literal cannot truthfully have type `Value`.
Inventing a JSON-constant constructor only for guidance would expand the
language without a runtime consumer. Such an annotation fails with
`value_guidance_example_unsupported`. Guidance never narrows the runtime
contract. A later authored change from `Value` to a concrete return type
changes both validation and the rendered provider contract through the
existing `ReturnSpec` owner; no parallel guidance owner is added.

## Compatibility And Failure Boundaries

- DSL `2.18` and earlier behavior is byte-for-byte unchanged.
- `Json` remains non-transportable.
- A narrower declaration retains its exact existing validation; `Value` never
  acts as a wildcard during comparison of two concrete declared types.
- A producer returning `Value` cannot satisfy a caller expecting a narrower
  type.
- Checkpoint and resume validation compare the declared `Value` contract, not
  the incidental prior payload shape.
- Contract fingerprints include the literal `value` descriptor.
- Existing direct-root `__result__` authority and validation-before-exposure
  ordering are unchanged.

The following coded refusals are required:

| Code | Condition |
| --- | --- |
| `value_type_requires_dsl_2_19` | Authored `Value` appears before target `2.19`. |
| `value_contract_requires_dsl_2_19` | Authored or imported `type: value` or `kind: value` appears before DSL `2.19`. |
| `invalid_transportable_value` | Recursive runtime validation encounters a non-JSON-like value. |
| `value_guidance_example_unsupported` | `:example` is authored for `Value` before a checked Value-constant surface exists. |
| existing `type_mismatch` | A `Value` expression is used where a narrower type is required. |
| existing operation-specific diagnostic | A field, variant, path, numeric, or other typed operation is attempted on `Value`. |

## Feasibility

The design extends proven seams rather than creating a new carrier:

- `orchestrator/workflow_lisp/contracts.py` already centralizes
  `is_transportable_result_type`, direct-root `__result__` derivation, and
  workflow-boundary contracts.
- `orchestrator/contracts/output_contract.py` already validates recursive
  optional/list/map JSON and returns typed values before exposure.
- `orchestrator/workflow/validation.py` already gates contract descriptors by
  DSL version.
- native-return tests already prove provider, command, workflow-call, public
  boundary, resume, dashboard, and ordinary-loader direct-root carriage.
- `PrimitiveTypeRef` already preserves compiler-owned prelude type identity
  through the frontend and WCC.

The required delta is therefore one target-gated prelude type, one explicit
contract descriptor, exact `Value` identity compatibility, and propagation
through existing descriptor switches. Recompiling or interpreting payload
shape to recover a narrower source type is forbidden.

## Verification Contract

Implementation must use TDD and cover both directions.

Focused compile-time checks:

- `Value` resolves only at target `2.19+` and cannot be shadowed;
- representative narrower scalar, path, record, union, optional, list, and map
  values are not implicitly assignable to `Value`;
- `Value` is not assignable to those narrower types;
- operations requiring those narrower types reject `Value`; and
- `Json`, provider/prompt capabilities, refs, and closures remain
  non-transportable.

Contract/runtime checks:

- loader accepts `type: value` / `kind: value` only at DSL `2.19+`;
- direct root `null`, boolean, integer, float, string, list, and object values
  validate and persist without an envelope;
- recursive mixed JSON validates through `List[Value]` and
  `Map[String, Value]`;
- missing bundles and malformed JSON retain existing failures;
- `NaN`, positive/negative infinity, and nested non-finite values fail closed;
- the in-memory validator rejects a non-JSON-like leaf with its value path;
  and
- narrower existing contracts still reject mismatched shapes.

End-to-end checks:

- one deterministic provider returns a mixed object as `Value`, a workflow
  passes it through a procedure and public workflow boundary, and state/report
  surfaces preserve the value;
- interruption after the committed provider boundary resumes without
  re-executing the provider and reconstructs the same `Value`; and
- classic and WCC routes emit equivalent executable contracts and runtime
  results.

The implementation plan must name all descriptor consumers found by a
repository switch scan and include an end-to-end usage check. Security work
and unrelated provider-isolation work are outside this tranche.

## Non-Goals

- Replacing, aliasing, or widening `Json`.
- Inferring a concrete type from a `Value` payload.
- Field projection, dynamic casts, schema decoding, reflection, or runtime
  typecase over `Value`.
- Making existing APIs accept `Value` when they require a specific semantic
  contract.
- Adding nominal wrappers, new outcome unions, prompt values, procedure
  references, workflow references, or closures to runtime transport.
- Changing record, union, path, enum, optional, list, or map validation.
- Implementing `defprompt`; this design is its prerequisite only.
