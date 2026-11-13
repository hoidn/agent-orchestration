# Workflow Lisp Proof Graph

Status: **Historical — archived in place.** Superseded: its proof rules are now stated, with their diagnostic codes, in the frontend specification; its `VariantProof` entries, `requires_variant` steps and typed-transition proof describe removed code. The complete original record below, including its original status, present-tense descriptions, schedules and acceptance language, is preserved for provenance. It supplies no current execution admission, work selection or copy-safe recipe. Current authority: [frontend specification §11](workflow_lisp_frontend_specification.md#11-pattern-matching) for `match` proof, the runtime check and workflow calls; [§7.5](workflow_lisp_frontend_specification.md#75-unions) and [§12](workflow_lisp_frontend_specification.md#12-conditionals) for unions and discriminant tests. Where each of its rules went: [rule ledger](../reports/2026-11-13-design-corpus-rule-ledger.md#proof_graph).

The historical body begins below; original results and qualifications are unchanged.

Status: current typed proof/analysis contract; historical executable projections
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
- a typed `.variant` discriminant comparison (`(= x.variant V)` /
  `(!= x.variant V)`) at target DSL 2.26, analyzed through the closed
  binding-identity possible-set algebra

Not a proof source:

- arbitrary string predicates
- general Boolean expressions that are not typed discriminant comparisons
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
- A frontend `if` expression establishes proof only when its condition is a
  typed `.variant` discriminant comparison; every other Boolean condition is
  proof-neutral and does not unlock variant-only fields.
- Runtime still guards variant access even after static proof succeeds.

## Open Questions

- Whether a later tranche should support proof from typed predicates.
- Whether proof contexts can safely cross bounded loop iterations.
