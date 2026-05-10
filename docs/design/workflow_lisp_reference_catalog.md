# Workflow Lisp Reference Catalog

Status: draft internal design  
Depends on: `docs/design/workflow_lisp_semantic_workflow_ir.md`

## Purpose

`ReferenceCatalog` is the unified registry of values addressable by workflow
references. It prevents frontends from treating artifacts, snapshots, outcomes,
and exit codes as interchangeable strings.

## Reference Kinds

Required kinds:

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
- A frontend field-selection expression must lower to a catalog lookup, not an
  ad hoc string path.

## Open Questions

- How much of the existing YAML ref parser can be reused for Lisp field access.
- Whether catalog entries should include effect provenance for observability.
