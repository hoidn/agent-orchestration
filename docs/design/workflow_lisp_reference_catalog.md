# Workflow Lisp Reference Catalog

Status: **Historical — archived in place.** Superseded: its `root.steps.*` reference kinds, snapshot entries and catalog validation describe removed code; its live rules (variant-only reads under proof, only the declared return crosses a workflow call, pointer files are not authority) are stated in the frontend specification. The complete original record below, including its original status, present-tense descriptions, schedules and acceptance language, is preserved for provenance. It supplies no current execution admission, work selection or copy-safe recipe. Current authority: [frontend specification §11](workflow_lisp_frontend_specification.md#11-pattern-matching) and [§7.3](workflow_lisp_frontend_specification.md#73-path-types). Where each of its rules went: [rule ledger](../reports/2026-11-13-design-corpus-rule-ledger.md#reference_catalog).

The historical body begins below; original results and qualifications are unchanged.

Status: current typed/reference-kind contract with historical flat reference spellings
Depends on: `docs/design/workflow_lisp_semantic_workflow_ir.md`

## Purpose

`ReferenceCatalog` is the unified registry of values addressable by workflow
references. It prevents frontends from treating artifacts, snapshots, outcomes,
and exit codes as interchangeable strings.

## Reference Kinds

Retained reference kinds; `root.steps.*` spellings below are historical
flat/read formats. Evaluated values use lexical environments and typed memo
results, not a reconstructed `root.steps` execution model:

- `ArtifactRef`: `root.steps.<Step>.artifacts.<name>`
- `SnapshotRef`: `root.steps.<Step>.snapshots.<name>`
- `OutcomeRef`: `root.steps.<Step>.outcome.<field>`
- `ExitCodeRef`: `root.steps.<Step>.exit_code`
- `WorkflowInputRef`: `inputs.<name>` or frontend equivalent
- `WorkflowOutputRef`: declared callee output crossing a call boundary

## Catalog Entries

```python
ArtifactEntry(
    owner_step: StepId,
    name: str,
    contract: TypedContract,
    availability: Availability,
    source_map: SourceMapRef,
)

SnapshotEntry(
    owner_step: StepId,
    name: str,
    schema: Literal["snapshot_diff/v1"],
    candidates: dict[str, SnapshotCandidateContract],
    digest: Literal["sha256"],
    storage: Literal["inline", "sidecar"],
)
```

## Scope Rules

- Artifact refs are usable where existing structured refs are allowed, subject
  to variant availability.
- Snapshot refs are usable only as selector evidence unless a later tranche
  explicitly expands their use.
- Outcome and exit-code refs keep their current DSL behavior.
- Only declared callee outputs cross workflow call boundaries.

## Validation Responsibilities

The catalog validates:

- referenced step exists
- referenced value exists
- reference kind is valid at the use site
- referenced contract is compatible with the consuming contract
- variant-only artifacts are accessed only under proof
- snapshot candidate keys match selector variants

## Required Invariants

- Snapshots are durable evidence, not artifacts.
- Pointer files are not reference authority unless the referenced artifact value
  is explicitly a pointer path.
- Frontend field selection uses checked typed value/catalog identity, never
  an ad hoc string path. Historical catalog validation does not select an executor.

## Open Questions

- How much of the existing YAML ref parser can be reused for Lisp field access.
- Whether catalog entries should include effect provenance for observability.
