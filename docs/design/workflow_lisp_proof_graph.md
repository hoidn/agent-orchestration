# Workflow Lisp Proof Graph

Status: draft internal design  
Depends on: `docs/design/workflow_lisp_reference_catalog.md`

## Purpose

`ProofGraph` records why a variant-specific value is available at a particular
use site. It prevents string predicates and ad hoc conditions from becoming
implicit variant proof.

## Proof Sources

Supported sources:

- `match` over the same discriminant
- explicit `requires_variant`
- compiler-generated proof context from a typed transition

Unsupported in the first tranche:

- arbitrary string predicates
- general boolean expressions
- cross-loop proof carryover
- proof through undeclared workflow call internals

## Proof Entry Shape

```python
VariantProof(
    producer_step: StepId,
    discriminant_artifact: str,
    variant: str,
    scope: ScopeId,
    source: ProofSource,
    source_map: SourceMapRef,
)
```

## Scope Rules

- A `match` arm creates proof only inside that arm.
- `requires_variant` creates proof only for the step it annotates.
- A typed transition may create proof for the value it returns, but the frontend
  must lower that proof into an explicit Core AST or Semantic IR proof entry.
- Proof does not cross a workflow call boundary unless the callee normalizes the
  result into declared outputs.

## Validation Responsibilities

Proof validation checks:

- producer exists
- discriminant artifact exists and is always available
- requested variant is allowed
- referenced field belongs to the proven variant
- use site is inside the proof scope
- runtime guard is retained where needed

## Required Invariants

- A discriminant being readable is not enough to read all variant fields.
- A frontend `if` expression is not proof unless Semantic IR explicitly models
  it as proof.
- Runtime still guards variant access even after static proof succeeds.

## Open Questions

- Whether a later tranche should support proof from typed predicates.
- Whether proof contexts can safely cross bounded loop iterations.
