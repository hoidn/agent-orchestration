# DSL v2.14 Pointer Authority

## Status

This is a Phase 1 design-authority note for the v2.14 materialization tranche.
It clarifies planning and documentation authority only. It does not change
runtime behavior, loader behavior, or public DSL support.

## Decision Summary

- Published relpath artifact lineage stores the artifact value, not a
  pointer-file path.
- A top-level relpath artifact contract defines the one canonical pointer
  surface for that published artifact.
- A same-step local pointer used to publish that artifact is allowed only when
  it is omitted or exactly equal to the canonical top-level pointer path.
- Additional pointer files for the same published relpath artifact are not
  Phase 1 authority surfaces. New noncanonical sidecar pointers for published
  relpath artifacts are rejected in Phase 1.
- Unpublished local pointers remain allowed as compatibility materializations
  for prompt/script handoff and phase-local workflow plumbing. They do not
  create extra published lineage surfaces.
- Queue metadata such as backlog frontmatter `plan_path` is a recovery or audit
  input, not published artifact authority.
- New v2.14-authored workflows should prefer structured refs and canonical
  published artifacts over duplicate pointer scans or queue-metadata mirrors
  whenever the runtime already exposes the needed value.

## Model

Three surfaces must stay distinct:

- Artifact value: the typed relpath or scalar recorded in workflow state and
  published lineage.
- Pointer file contents: a text file whose contents equal a relpath artifact
  value when that pointer is valid.
- Pointer-file path: the filesystem location of the text file itself.

Phase 1 authority attaches to the artifact value first and to the canonical
top-level pointer only as the on-disk materialization of that same value.
Pointer-file paths are not lineage values.

## Audit Inventory

The inventory below covers the required audit buckets from the execution plan.

| Surface | Representative locations reviewed | Classification | Drift risk and authority note |
| --- | --- | --- | --- |
| DSL artifact contract | `specs/dsl.md` artifact schema, especially `artifacts.<name>.pointer` | canonical top-level artifact pointer | This is the normative runtime contract for relpath artifacts. The pointer path is declared here; published lineage should carry the relpath value, not the pointer-file path. |
| Library workflow artifact registries | `workflows/library/revision_study_design_phase.yaml`, `workflows/library/major_project_roadmap_revision_phase.yaml`, `workflows/library/neurips_backlog_seeded_plan_phase.yaml` | canonical top-level artifact pointer | These workflows declare phase artifacts under `artifacts:` and then publish same-step outputs through them. The artifact contract, not the local output name, owns the canonical pointer path. |
| Same-step publish source | `expected_outputs` plus `publishes.from` in the library workflows above | local step materialization pointer | The local output name is a same-step handle for publication. When it feeds a published relpath artifact, its pointer path must match the canonical top-level pointer or be omitted. |
| Workflow boundary outputs | `outputs.from` refs in the same library workflows and in `workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml` | not a pointer authority surface | Workflow outputs export typed values through structured refs. They should not be treated as separate pointer contracts. |
| Example workflow compatibility reads | `workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml` reads `final_plan_path.txt`, `final_plan_review_report_path.txt`, and other `final_*` files | prompt/script compatibility input | These files are phase-local handoff aids for command logic. They mirror already-selected artifact values but are not top-level lineage authority. |
| Backlog manifest builder | `workflows/library/scripts/build_neurips_backlog_manifest.py` | ambiguous authority surface | The script validates backlog frontmatter `plan_path` and copies it into a manifest. This is queue metadata used for selection and auditing, not artifact lineage. It can drift from the currently approved plan if not reconciled. |
| Selected-item materializer | `workflows/library/scripts/materialize_neurips_selected_item_inputs.py` | prompt/script compatibility input plus ambiguous authority surface | The script writes phase-local pointers such as `check_commands_path.txt`, carries `candidate_plan_path`, and emits future target paths. These are compatibility and planning surfaces, not published artifact authority. |
| Queue reconciliation | `workflows/library/scripts/reconcile_neurips_selected_item.py` | stale compatibility shim | The script rewrites backlog frontmatter `plan_path` when moving an item into `in_progress`. That mirrored field is useful for recovery, but it should not be confused with a published plan artifact. |
| Plan-gate recovery tests | `tests/test_neurips_plan_gate_recovery.py` | stale compatibility shim | Recovery intentionally treats frontmatter `plan_path` as a durable fallback when resuming an already-approved item. That proves recovery behavior, not primary lineage authority. |
| Dataflow precedence tests | `tests/test_artifact_dataflow_integration.py` | canonical top-level artifact pointer | Existing tests already establish that published lineage beats a clobbered pointer file and that newer consume semantics can leave step-owned pointers untouched. |
| Oracle compatibility provider | `tests/fixtures/bin/fake_provider.py` scanning `state/**/plan-phase/plan_path.txt` and similar files | prompt/script compatibility input | The fake provider uses pointer files as a filesystem handoff contract. That is a compatibility consumer of local materialization, not an extra published authority surface. |

## Authority Rule Set For Phase 1

### Published Relpath Artifacts

For any published relpath artifact:

- the published lineage value is the relpath value itself;
- the canonical pointer path is the one declared by the top-level artifact
  contract;
- a same-step local pointer used for publication must be omitted or exactly the
  same path as that canonical pointer;
- any different sidecar pointer for that same published artifact is outside the
  contract and is rejected by the planned Phase 1 runtime work.

This keeps one authority model for publication, consume resolution, and resume.

### Unpublished Local Artifacts

Unpublished local pointers remain allowed when they are only phase-local
materializations for a step, prompt, or helper script. They are compatibility
surfaces only:

- they may help a provider or script discover where to write rich content;
- they do not create top-level lineage entries;
- they must not be treated as permission to invent a second published pointer
  surface for the same relpath artifact.

### Queue And Recovery Metadata

Backlog frontmatter and derived manifest fields such as `plan_path` are allowed
as queue and recovery metadata. They are deliberately separate from artifact
lineage because they track queue state and human-review checkpoints. They can be
used for audited recovery flows, but they are not Phase 1 authority for normal
published relpath artifact resolution.

## Migration Guidance

For new v2.14-authored workflows:

- prefer structured refs between steps, calls, and workflow outputs when the
  runtime already exposes the needed value;
- use canonical top-level artifact contracts for published relpath artifacts;
- keep pointer files only where a provider or command still needs a filesystem
  handoff target;
- avoid adding new queue/frontmatter mirrors of already-published artifact
  values unless the surface is explicitly a recovery or queue-lifecycle
  contract;
- treat any future desire for multiple published pointer surfaces as deferred
  design work, not as implied permission from current compatibility shims.

## Oracle Follow-Up

No extra Phase 0 oracle documentation update is required in this item.
The audit found existing evidence already covering the critical precedence rule:
published artifact lineage remains authoritative even if a pointer file drifts,
and compatibility consumers continue to read pointer files only as handoff
surfaces. Later runtime implementation can add targeted Phase 1 enforcement
tests without reopening this authority decision.
