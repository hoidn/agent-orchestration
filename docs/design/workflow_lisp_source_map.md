# Workflow Lisp Source Map

- **Status:** accepted
- **Kind:** architecture decision and component contract
- **Created:** 2026-05-30
- **Last material update:** 2026-07-09
- **Related docs / plans:** `workflow_lisp_frontend_specification.md`,
  `workflow_lisp_core_workflow_ast.md`,
  `../plans/2026-07-08-boundary-report-followups.md`
- **Implementation target:** canonical build source-map sidecar and runtime
  diagnostic remapping, including authored union variant fields

## Summary

The Workflow Lisp source map connects authored forms to generated Core AST,
Semantic IR, Executable IR, runtime steps, validation subjects, and runtime
contract violations. Generated behavior is acceptable only when a diagnostic
can explain its authored origin without recompiling the source or making a
generated representation semantic authority.

Runtime structured-result violations require field-level lineage. A generated
variant-output contract therefore carries stable source-map subject references,
while the canonical source-map sidecar owns the authored file, exact field
span, form path, expansion stack, and generated-name explanation. Runtime
diagnostics resolve those subjects through the compiled frontend index and
fall back to the enclosing generated step when reading older artifacts.

## Context And Authority

The frontend specification owns the language-level provenance obligations.
This document owns the component architecture that satisfies them. Runtime
contract behavior remains normative in `specs/`; the source map adds origin
information without changing whether a bundle is valid.

The existing implementation already persists workflow, step, generated input,
generated output, generated path, Core-node, executable-node, command-boundary,
and shared-validation lineage in `source_map.json`. It also uses
`ValidationSubjectRef` to carry stable semantic identities across shared
validation. This design extends that same mechanism to authored union fields;
it does not introduce a parallel provenance model.

## Problem

`variant_required_field_missing` and `variant_forbidden_field_present` identify
the selected variant, field name, and JSON pointer, but those runtime
violations cannot currently identify the authored `defunion` field. The
persisted source map retains the generated step origin but not the individual
variant-field spans, and the runtime frontend index resolves only steps and
executable nodes.

Step-level fallback is insufficient for the boundary-report case: two variants
may contain fields with the same name, and a shared runtime field may have a
different authored declaration in each variant. Reconstructing lineage from a
runtime contract or recompiling the `.orc` source would duplicate compiler
authority and make diagnostics sensitive to mutable source.

## Goals And Non-Goals

Goals:

- attribute missing selected-variant and forbidden inactive-variant fields to
  the exact authored union field;
- preserve distinct lineage when variants repeat a field name;
- reuse structured validation subjects and the canonical source-map sidecar;
- retain useful step-level diagnostics for older builds and YAML workflows;
- keep contract validity, type authority, and runtime execution semantics
  unchanged.

Non-goals:

- attributing a missing or invalid discriminant to an individual field;
- adding runtime procedure values, runtime typechecking, or source
  recompilation;
- changing variant-output acceptance/rejection rules or diagnostic codes;
- backfilling historical source-map sidecars;
- exposing source-map metadata as workflow-authored output data.

## Decision

Use one stable validation-subject identity per authored union variant field.
The subject kind is `variant_output_field`; its name is a deterministic,
compiler-owned identity containing the generated step, union type, variant,
and flattened field identities. The canonical workflow is carried separately
by `ValidationSubjectRef.workflow_name`. Consumers must treat the subject name
as opaque and compare it only for equality.

Lowering derives field subjects at the same point that it derives a generated
structured-result contract. It records each subject-to-origin binding in the
lowering origin map and places only the corresponding subject reference in the
generated runtime contract. The source-map builder persists the authored
origin in a `contract_fields` section and persists the ordinary
`validation_subjects` binding from the subject to that origin.

At runtime, variant-output validation attaches the relevant subject reference
to each field violation. `CompiledFrontendIndex` resolves the reference to a
source-map entry and the executor adds that structured origin to the individual
violation. If no subject or origin is available, existing enclosing-step
attribution remains the compatibility fallback.

Rejected alternatives:

- **Infer origins from field names at runtime.** Ambiguous for repeated and
  shared fields, and duplicates compiler knowledge.
- **Recompile source at runtime.** Makes a persisted run depend on mutable
  source and creates a second compilation authority.
- **Use only the generated step origin.** Does not satisfy exact authored-field
  attribution and hides the declaration that must be fixed.

## Design Details

### Compile and lowering flow

1. Structured-result contract derivation visits the resolved union definition.
2. For every `(variant, field)` declaration it creates a deterministic
   `ValidationSubjectRef` and retains that field's exact `SourceSpan` and
   compiler form path in a lowering-owned origin binding.
3. The generated contract field specification carries the subject reference
   needed for its runtime role:
   - variant-specific fields carry their one field subject;
   - shared fields carry a subject keyed by selected variant, because each
     variant declaration may have a distinct origin;
   - inactive-variant field specifications retain the inactive declaration's
     subject for forbidden-field diagnostics.
4. Lowering merges these bindings into `LoweringOriginMap` alongside existing
   workflow, step, input, output, and path subjects. The classic and WCC
   context constructors own the same mutable field-origin catalog; inline
   procedure child contexts share it rather than copying it.
5. Source-map construction emits a `contract_fields` entry for every bound
   field and validates that every persisted field subject resolves to exactly
   one origin entry.

Every lowering-owned call that attaches a derived structured-result contract
to a generated step must register the returned field-origin bindings
immediately. This includes provider, command, match, phase/resource, stdlib,
flow, scope, and value lowering paths. A derivation used only for static
projection or reusable-state analysis need not register runtime lineage unless
its payload is attached to an executable step.

Both classic lowering and WCC defunctionalization copy the shared catalog into
their independently constructed `LoweringOriginMap`. When a generated drain
workflow is cloned under an alias, the clone operation rekeys the field origins
and rewrites the embedded subject references' `workflow_name` together; it must
not rebuild only the standard validation bindings and drop custom fields.

The full authored span is never embedded in the runtime contract. This keeps
the source-map sidecar authoritative and prevents contract payloads from
becoming provenance copies.

### Runtime flow

1. The existing variant-output validator determines the active contract rule.
2. When it emits a field violation, it copies the rule's subject reference into
   the violation. Shared-field lookup uses the selected variant.
3. The executor passes serialized subjects to the compiled frontend index.
4. The index resolves the subject through `validation_subjects` and then the
   corresponding `contract_fields` origin entry.
5. The executor preserves the violation code and context and adds the resolved
   structured source origin. Multiple violations retain independent origins.
6. If resolution is impossible, the diagnostic remains valid and uses the
   existing generated-step origin when available.

### Wire shapes

Variant-specific generated field:

```json
{
  "name": "report",
  "json_pointer": "/report",
  "type": "string",
  "source_map_subject": {
    "subject_kind": "variant_output_field",
    "subject_name": "execute::Decision::ACCEPTED::report",
    "workflow_name": "demo/module::entry"
  }
}
```

Shared generated field, preserving one authored declaration per variant:

```json
{
  "name": "report",
  "json_pointer": "/report",
  "type": "string",
  "source_map_subjects_by_variant": {
    "ACCEPTED": {
      "subject_kind": "variant_output_field",
      "subject_name": "execute::Decision::ACCEPTED::report",
      "workflow_name": "demo/module::entry"
    },
    "REJECTED": {
      "subject_kind": "variant_output_field",
      "subject_name": "execute::Decision::REJECTED::report",
      "workflow_name": "demo/module::entry"
    }
  }
}
```

Serialized field violation before and after runtime origin resolution:

```json
{
  "type": "variant_required_field_missing",
  "message": "...",
  "context": {
    "variant": "ACCEPTED",
    "name": "report",
    "json_pointer": "/report"
  },
  "subject_refs": [
    {
      "subject_kind": "variant_output_field",
      "subject_name": "execute::Decision::ACCEPTED::report",
      "workflow_name": "demo/module::entry"
    }
  ],
  "source_origins": [
    {
      "origin_key": "demo/module::entry::variant_output_field::execute::Decision::ACCEPTED::report",
      "entity_kind": "variant_output_field",
      "workflow_name": "demo/module::entry",
      "path": "demo/module.orc",
      "line": 12,
      "column": 5,
      "end_line": 12,
      "end_column": 20,
      "form_path": ["workflow-lisp", "defunion", "Decision", "ACCEPTED", "report"]
    }
  ]
}
```

`subject_refs` and `source_origins` are ordered arrays with stable
first-seen de-duplication. A field violation normally has one subject and one
origin. Subject-free violations omit both keys. An unresolved subject remains
in `subject_refs`; if the enclosing generated step resolves, `source_origins`
contains that step origin as the compatibility fallback. The fallback origin
does not pretend to be a `variant_output_field` origin.

### Source map entry

All persisted origins use the existing `SourceMapEntry` shape:

```python
SourceMapEntry(
    origin_key: str,
    entity_kind: str,
    workflow_name: str,
    path: str,
    line: int,
    column: int,
    end_line: int,
    end_column: int,
    form_path: tuple[str, ...],
    module_name: str | None,
    expansion_stack: tuple[object, ...],
    notes: tuple[str, ...],
    generated_name_origin: str | None,
)
```

Contract-field entries use `entity_kind = "variant_output_field"`. Their
`generated_name_origin` is the stable subject name, while their span and form
path point to the authored field declaration.

## Contracts And Interfaces

The persisted per-workflow source map gains an additive `contract_fields`
mapping. The existing `validation_subjects` section gains
`variant_output_field` subjects whose `origin_key` resolves into that mapping.
The schema identifier remains `workflow_lisp_source_map.v1`: this is an
additive optional section, existing readers already tolerate unknown or absent
sections, and new readers must tolerate old v1 maps without it.

`ContractViolation` gains optional structured subject references. Serialization
omits the field when there are no subjects so unrelated diagnostics retain
their current payload. Resolved source information is additive and belongs to
the individual violation, not only its enclosing executor error.

The compiled frontend index gains subject-resolution behavior. It must accept
both in-memory `ValidationSubjectRef` values and their serialized mapping form,
and it must not require source files to remain present.

The Semantic IR source-map bridge is also a required consumer. Its declared
origin sections include optional `contract_fields`, and its supported subject
set includes the `variant_output_field` keys declared by that section. It
continues to accept an older v1 payload with neither the section nor those
subjects. New field subjects that do not resolve through the new section remain
`semantic_ir_invalid`, matching the current fail-closed behavior for other
source-map subjects.

## Dependencies And Sequencing

This design depends on the existing generated structured-result contract,
lowering origin map, canonical source-map builder, Semantic IR source-map
bridge, validation-subject type, and compiled frontend index. Implementation
must cover classic lowering, WCC defunctionalization, inline procedure context
sharing, and drain clone/rekey behavior before boundary-report Task 5 case 5
can pass. That boundary plan's Task 6 and final gate must then close before the
parametric drain migration begins.

## Invariants And Failure Modes

- Contract validation remains the sole authority for accepting or rejecting a
  runtime bundle.
- Each persisted field subject resolves to exactly one authored origin within
  its workflow.
- Repeated field names across variants never overwrite one another.
- Shared fields resolve according to the active variant.
- Runtime execution never reads or recompiles `.orc` source to obtain lineage.
- Provenance-only subject metadata is excluded from semantic contract digests,
  reusable-state fingerprints, and checkpoint identity comparisons.
- Missing, old, or malformed optional field lineage does not turn a valid
  contract failure into an executor crash; it degrades to step-level origin.
- Source-map validation fails the build for dangling or duplicate field
  bindings emitted by a new compile.
- The Semantic IR bridge accepts every field subject emitted by a valid new
  source map and still accepts an old v1 source map that lacks field lineage.
- Diagnostic message wording is not a compatibility contract; diagnostic
  codes, field context, subjects, and structured origin are.

## Security, Operations, And Performance

No new authority, credentials, or external data access are introduced. Source
paths and spans are already persisted by source maps. The additional storage
and lookup cost is linear in authored structured-result fields and negligible
relative to existing build artifacts. Runtime resolution is an indexed lookup,
not a source scan.

## Evidence And Implementation Boundaries

The production compile/build route must generate the field subjects and source
map; tests must not hand-author the only passing metadata. The runtime executor
must enrich a real contract failure through `CompiledFrontendIndex`; direct
unit calls to a remapping helper are necessary but not sufficient evidence.

Debug YAML, test fixtures, rendered reports, and runtime contract payloads are
representations or evidence. `source_map.json` remains the persisted provenance
authority, and the authored union definition remains the compile-time type
authority.

## Compatibility And Migration

New builds include field lineage. Existing v1 sidecars, YAML workflows, and
generated contracts without subjects continue to produce the existing
step-level diagnostic. No backfill or artifact migration is required. The
extension can be rolled back by ignoring the optional section and subjects;
contract validity is unchanged.

## Verification Strategy

- source-map unit tests prove distinct entries and exact spans for repeated
  names across variants;
- classic, WCC, inline-procedure, and alias/rekey tests prove field bindings
  survive every production lowering route that can emit the contract;
- contract-validator tests prove subject selection for missing active,
  forbidden inactive, and shared fields;
- Semantic IR tests prove new field subjects bridge successfully and old v1
  sidecars remain accepted;
- frontend-index tests prove subject resolution and old-v1 fallback;
- an executor integration test compiles a real `.orc` union, triggers a runtime
  missing-field failure, and observes the authored field origin;
- source-map validation tests reject dangling field subjects;
- relevant output-contract, source-map, build, and executor suites plus one
  orchestrator smoke protect adjacent behavior.

## Declarative Acceptance Scenario

Given a real `.orc` module whose `ACCEPTED` and `REJECTED` variants both declare
a `report` field on different source lines, compile it through the normal build
entrypoint and execute a provider result selecting `ACCEPTED` while omitting
`report`. The runtime must emit `variant_required_field_missing` with
`variant = ACCEPTED`, `name = report`, the expected JSON pointer, a
`variant_output_field` subject, and a structured source origin pointing to the
`ACCEPTED.report` declaration. It must not point to `REJECTED.report`, infer the
origin from the field name, recompile the source, or change contract validity.

If a union field's type is a nested `defrecord`, every flattened runtime leaf
under that union field resolves to the union variant-field declaration (the
site that includes the record), not to the nested record schema declaration.
Nested schema-declaration lineage is a separate possible extension and is not
required for this acceptance gate. Likewise, any future union-field inclusion
surface that injects declarations from `defschema` must make its own
include-site-versus-schema-site attribution decision before it joins promoted
runtime lineage coverage.

## Success Criteria

- the declarative acceptance scenario passes through production compile and
  runtime paths;
- boundary-report Task 5 case 5 cites the integration test as coverage;
- compatibility tests demonstrate unchanged behavior for old sidecars and
  subject-free YAML contracts;
- the boundary follow-up final gate passes, unblocking the drain migration.
