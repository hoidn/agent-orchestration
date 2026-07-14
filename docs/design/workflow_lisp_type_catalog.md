# Workflow Lisp Type Catalog

Status: draft internal design  
Depends on: `docs/design/workflow_lisp_semantic_workflow_ir.md`

## Purpose

`TypeCatalog` maps frontend types to workflow contracts, JSON bundle schemas,
variant-output contracts, and semantic IR values.

## Type Families

Required families:

- scalar primitives: `String`, `Int`, `Float`, `Bool`, `Json`, `TimestampNs`,
  `RunId`, `Symbol`
- enums
- path refinements
- records
- unions
- optionals
- lists
- maps
- workflow references

## Contract Mapping

Examples:

```text
String -> scalar string contract
ReviewDecision -> scalar enum contract
Path.execution-report -> relpath contract with under/must-exist rules
Record -> product schema or structured bundle schema
Union -> tagged variant contract
WorkflowRef[A -> B] -> compile-time callable signature
```

## Root/Direct Return Contract

A non-record/non-union ("root") result type maps to one generated
`output_bundle` field named `__result__` with `json_pointer: ""`, so the
runtime document is the direct JSON value rather than an object:

```text
Bool -> root output_bundle field, JSON boolean
Int, Float -> root output_bundle field, JSON number
String, enum, path -> root output_bundle field, JSON string
Optional[T] -> root optional schema, null or the JSON form of T
List[T] -> root list schema, JSON array
Map[String, T] -> root map schema, JSON object
Record, Union -> unchanged: flattened output_bundle / variant_output
```

`result_shape` (`root_value` | `record_value` | `union_value`) is the
structural, type-driven classification behind this split; it never branches
on workflow, provider, procedure, module, or domain names. See
[Workflow Lisp Native Transportable Returns And Typed Result Guidance](workflow_lisp_native_transportable_returns.md)
for the full contract and public DSL v2.15 wire schema.

## Result Guidance

Every return occurrence accepts either plain `T`, redundant `(result T)`, or
an annotated return:

```lisp
(result Bool
  :description "True only when no blockers remain."
  :format-hint "JSON boolean."
  :example true)
```

Record and union payload fields accept the same optional keys after their
type. Examples must be closed pure constants of the declared type. Guidance is
immutable declaration metadata: schema inclusion, imports, re-exports,
specialization, record flattening, and union sharing preserve it, while type
identity and runtime validity ignore it. Public DSL v2.15 carries occurrence
guidance in effect contracts and overall-return guidance in top-level
`result_guidance`.

## Path Types

Path types represent artifact values, not pointer files. Pointer materialization
is a separate effect.

Path refinement must follow the contract-narrowing rule:

- child `under` roots are allowed
- expanded `under` roots are rejected
- `must_exist_target: false -> true` is allowed
- `must_exist_target: true -> false` is rejected

## Union Types

Each union defines:

- discriminant name
- allowed variants
- shared fields
- variant-specific fields
- forbidden fields per variant, if needed
- availability metadata for variant fields

## Validation Responsibilities

Type validation checks:

- names resolve
- record fields exist
- union variants exist
- workflow call signatures match
- pure helpers return declared types
- output bundle fields match their declared schemas
- variant output fields match selected variant schemas

## Required Invariants

- Type checking must happen before lowering into validation surfaces that depend
  on field availability.
- Type erasure may occur only after Semantic IR has recorded enough contract and
  source-map information for diagnostics.

## Open Questions

- Whether `Optional[T]`, `List[T]`, and `Map[K,V]` are supported in artifact
  refs in the first tranche or only inside structured bundles.
- Whether record-valued workflow inputs are flattened at Core AST or kept until
  executable IR lowering.
