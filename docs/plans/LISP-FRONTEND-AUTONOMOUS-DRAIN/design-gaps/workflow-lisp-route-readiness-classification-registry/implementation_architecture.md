# Workflow Lisp Route/Readiness Classification Registry Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-route-readiness-classification-registry`
Target design: `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected Tranche 0 / Tranche 8 evidence-labeling
gap:

- add one durable route/readiness classification registry for checked-in
  Workflow Lisp `.orc` examples, selected library migration candidates,
  representative compiler fixtures, and migration-parity target references;
- validate that registry against the current checkout so stale, legacy-only,
  or migration-only `.orc` surfaces cannot masquerade as current WCC guidance;
- require route identity to be explicit for registry-covered compiler/lowering
  tests unless the test is intentionally a default-route check;
- connect migration-parity target identity to the same route/readiness
  vocabulary without changing `non_regressive`, promotion eligibility, or
  lowering behavior;
- update the workflow index and Lisp drafting guide to consume registry labels
  rather than inferring copy-safety from filenames, recency, or prose.

Out of scope for this slice:

- changing WCC, legacy lowering, route selection, or lowering schema
  semantics;
- changing Core Workflow AST, Semantic Workflow IR, executable IR, source-map,
  TypeCatalog, variant proof, or pointer authority contracts;
- changing parent backlog-drain behavior, parent-callable readiness evidence,
  private context, typed projection, certified adapter declarations, or
  resource-transition ownership;
- changing the strict migration-parity gate rules for `--require-non-regressive`
  and `--require-promotable`;
- broad legacy YAML lint enforcement;
- certifying or modifying helper scripts, command boundaries, or adapters.

The success condition is narrow: the repo has a machine-checked classification
surface that says which `.orc` examples and fixtures are copy-safe current WCC
guidance, which are legacy compatibility, which are historical/negative, which
are active migration candidates, and which are stale. Route and schema identity
become evidence fields, not tribal knowledge.

## Problem Statement

The post-WCC reconciliation surfaced two related findings:

- UAF-01: stale or legacy-only `.orc` examples can fail under the WCC default
  and look like architecture failures.
- UAF-02: tests and examples need explicit lowering-route classification
  because WCC schema 2 is now the default for new compiles in the migrated
  subset while legacy schema 1 remains a compatibility route.

The current checkout has partial pieces:

- `orchestrator/workflow_lisp/wcc/route.py` defines `LoweringRoute`,
  `DEFAULT_LOWERING_ROUTE`, and route-to-schema mapping.
- frontend build artifacts record `lowering_schema_version` and intentionally
  avoid leaking route names into semantic artifacts.
- `orchestrator/workflow_lisp/migration_parity.py` accepts
  `readiness_label`, `lowering_route`, and `lowering_schema_version` on parity
  targets and validates route identity for required parent-family evidence.
- many tests explicitly pass `LoweringRoute.LEGACY` or `LoweringRoute.WCC_M4`
  after reconciliation.
- `workflows/README.md` and `docs/lisp_workflow_drafting_guide.md` contain
  prose copy-safety guidance.

The missing component is the durable registry and enforcement surface that ties
those pieces together across examples, representative fixtures, and migration
evidence. Today a new `.orc` file can be checked in without a label, a legacy
fixture can be cited as WCC evidence, and a passing test can be read without
knowing whether it proved legacy compatibility, WCC default behavior, or a
stale migration candidate.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`;
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`;
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`;
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  Sections 11, 19, 27.10, and 29;
- `docs/design/workflow_lisp_frontend_specification.md`, especially the
  frontend pipeline, validation/source-map ownership, and migration evidence
  guidance;
- `docs/design/workflow_lisp_core_calculus_middle_end.md`, especially WCC
  schema 2 as the default route for migrated new compiles and the requirement
  that route flips be evidence-backed;
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`;
- `docs/design/workflow_lisp_runtime_migration_foundation.md`, especially the
  strict parity-gate and evidence-freshness rules;
- `docs/design/workflow_command_adapter_contract.md`;
- `docs/lisp_workflow_drafting_guide.md`;
- `workflows/README.md`;
- `specs/dsl.md`, `specs/io.md`, `specs/providers.md`, and `specs/state.md`;
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`;
- `orchestrator/workflow_lisp/wcc/route.py`;
- `orchestrator/workflow_lisp/migration_parity.py`;
- `orchestrator/workflow_lisp/build.py`;
- `orchestrator/cli/main.py` and `orchestrator/cli/commands/migration_parity.py`;
- representative `.orc` tests under `tests/test_workflow_lisp_*.py`.

Guardrails:

- The registry is classification and evidence metadata. It is not semantic
  workflow authority and does not affect compilation output.
- The route enum and schema mapping remain owned by
  `orchestrator/workflow_lisp/wcc/route.py`.
- Migration parity remains the authority for computed `non_regressive` and
  promotion eligibility. The registry may make a report invalid or stale; it
  must not author `non_regressive`.
- Build artifacts continue to record route-neutral `lowering_schema_version`.
  The registry may record a route for evidence classification, but it must not
  force route names into source maps, semantic IR, executable IR, or runtime
  state artifacts.
- Command-adapter policy remains unchanged. If a classified surface exercises a
  command-backed adapter, this slice records route/readiness labels only; it
  does not certify or alter the adapter.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The generated architecture index at
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/design-gap-architect/existing-architecture-index.md`
was reviewed. The full index-listed corpus was scanned for scope, ownership,
and conflict sections so this slice does not redefine shared concepts.

Directly constraining slices read closely:

- `workflow-lisp-wcc-ifexpr-work-item-route`;
- `workflow-lisp-phase-family-boundary-rehabilitation-post-ifexpr`;
- `workflow-lisp-parent-backlog-drain-composition-parity`;
- `workflow-lisp-imported-child-returned-variant-work-item-prerequisite`;
- `workflow-lisp-promoted-entry-hidden-reusable-call-binding`;
- `workflow-lisp-design-plan-impl-stack-parity-evidence-refresh`;
- `workflow-lisp-state-layout-path-allocator-foundation`;
- `workflow-boundary-type-flattening`;
- `source-map-runtime-lineage`;
- `semantic-workflow-ir-shared-contract`;
- `executable-ir-runtime-plan`;
- `frontend-validation-diagnostics-pipeline`;
- `frontend-required-lints`;
- `lisp-frontend-cli-diagnostics-surface`.

### Decisions Reused

- Reuse `LoweringRoute` and `lowering_schema_for_route(...)`; do not define a
  second route enum.
- Reuse `readiness_label`, `lowering_route`, and
  `lowering_schema_version` as migration-parity target identity fields.
- Reuse `route_identity` evidence for parent-family parity targets; this slice
  generalizes classification around that field rather than replacing it.
- Reuse strict gate behavior from migration parity:
  `report_valid`, `evidence_complete`, `non_regressive`, and
  `eligible_for_primary_surface` are derived or computed.
- Reuse frontend diagnostics and CLI error conventions for malformed registry
  entries. Validation failure is a deterministic tool/test failure, not a
  runtime warning.
- Reuse docs/index routing: `workflows/README.md` remains the workflow catalog
  and `docs/lisp_workflow_drafting_guide.md` remains author-facing guidance.

### New Decisions In This Slice

- Add a versioned JSON registry at
  `docs/workflow_lisp_route_readiness_registry.json` with schema id
  `workflow_lisp_route_readiness_registry.v1`.
- Add `orchestrator/workflow_lisp/route_readiness.py` as the frontend-owned
  parser and validator for that registry.
- Add a CLI validation command, tentatively
  `python -m orchestrator workflow-lisp-route-readiness --registry docs/workflow_lisp_route_readiness_registry.json --check`,
  that runs the same validation used by tests.
- Treat every `.orc` under `workflows/examples/` and every real Design Delta
  family `.orc` under `workflows/library/lisp_frontend_design_delta/` as
  registry-required.
- Treat test fixtures as registry-required only when they are representative
  evidence surfaces: WCC characterization sources, checked-in migration
  fixtures, parent-callable fixtures, or fixtures cited by migration parity
  and post-foundation architecture docs. Ordinary one-off invalid fixtures do
  not need registry rows unless a doc or report cites them as evidence.
- Add one test-helper convention for registry-covered compiler/lowering tests:
  the test must either compile with the route recorded in the registry or mark
  itself as an intentional default-route check.
- Make migration-parity target loading optionally validate selected targets
  against the registry when the registry path is provided by CLI/default
  configuration. Initial implementation may make this an internal call from
  the parity tests before the CLI flag is exposed.

### Conflicts Or Revisions

No shared semantic concepts are revised. This slice narrows the informal
guidance in `workflows/README.md`: copy-safety for Workflow Lisp examples
should come from the registry label and the generated catalog row, not from
filename recency or a prose-only status.

This slice also tightens the current migration-parity target behavior. Target
rows may still carry route/readiness fields as they do today, but a target that
references a registry-covered `.orc` candidate with mismatched route/schema or
readiness becomes stale evidence for strict gating.

## Ownership Boundaries

This slice owns:

- the route/readiness registry schema and checked-in registry document;
- validation of registry syntax, path existence, label enums, route/schema
  consistency, and coverage for required `.orc` paths;
- comparison between registry route identity and migration-parity target
  route identity;
- a deterministic validation CLI/test helper;
- documentation updates that make the registry the source for `.orc`
  copy-safety labels in `workflows/README.md` and
  `docs/lisp_workflow_drafting_guide.md`;
- focused tests for registry schema validation, missing coverage, route/schema
  mismatch, stale migration target identity, and intentional default-route test
  declarations.

This slice intentionally does not own:

- WCC route implementation or the default route selection;
- legacy-route behavior or retirement;
- lowering schema migration or resume behavior;
- any command adapter certification, script classification, or runtime-native
  promotion;
- parent-drain implementation, parent-callable evidence generation, or
  workflow-family parity logic beyond route/readiness identity checks;
- generated Core AST, Semantic IR, executable IR, runtime-plan, or source-map
  artifact shape.

## Registry Contract

### Schema

The registry is a JSON object:

```json
{
  "schema_version": "workflow_lisp_route_readiness_registry.v1",
  "updated": "2026-06-10",
  "surfaces": [
    {
      "surface_id": "workflows.examples.review_revise_design_docs",
      "path": "workflows/examples/review_revise_design_docs.orc",
      "surface_kind": "workflow_example",
      "route_label": "wcc_default",
      "readiness_label": "leaf_runtime_candidate",
      "lowering_route": "wcc_m4",
      "lowering_schema_version": 2,
      "copy_safety": "preferred_current_guidance",
      "evidence": [
        "tests/test_workflow_lisp_examples.py::test_review_revise_design_docs_example_compiles"
      ],
      "notes": "Current generic design-doc review/fix example."
    }
  ]
}
```

Required fields:

- `surface_id`: stable dotted id, unique within the registry.
- `path`: repo-relative file or evidence path.
- `surface_kind`: one of `workflow_example`, `library_workflow`,
  `test_fixture`, `compiler_test`, `migration_target`, or
  `migration_evidence`.
- `route_label`: one of `wcc_default`, `legacy_schema1_compat`,
  `historical_negative`, `migration_candidate`, or `stale_needs_update`.
- `lowering_route`: a value from `LoweringRoute` when the surface compiles or
  is expected to compile; omitted only for `historical_negative` fixtures that
  are intentionally parse/type/lint failures.
- `lowering_schema_version`: required whenever `lowering_route` is present.
- `readiness_label`: required for migration targets and migration candidates;
  allowed values are the target-design readiness states:
  `leaf_compile_candidate`, `leaf_runtime_candidate`,
  `parent_callable_candidate`, `family_non_regressive`, and
  `promotion_eligible`.
- `evidence`: selectors, reports, or command names that prove the label.

Recommended fields:

- `entry_workflow`;
- `source_roots`;
- `copy_safety`;
- `owner`;
- `notes`;
- `parity_constrained`;
- `replacement_or_retirement_path` for stale or compatibility-only surfaces.

### Label Semantics

`wcc_default` means the surface is expected to compile or run under the current
default route (`LoweringRoute.WCC_M4`, schema 2) and is copy-safe current
guidance when its catalog status also says so.

`legacy_schema1_compat` means the surface is retained to prove or preserve the
legacy route. It must record `lowering_route=legacy` and
`lowering_schema_version=1`. It is not current authoring guidance.

`historical_negative` means the surface is expected to fail for a deliberate
diagnostic or historical reason. It must name the expected diagnostic or
negative-purpose evidence.

`migration_candidate` means the surface is mid-migration. It must carry a
readiness label and route/schema identity. It is not promotable unless
migration parity computes the required evidence.

`stale_needs_update` means the surface is known not to represent current
guidance. It must name an owner or replacement path before it can remain in
the registry.

### Coverage Rules

The validator discovers required paths:

- all `.orc` files directly under `workflows/examples/`;
- all `.orc` files under `workflows/library/lisp_frontend_design_delta/`;
- `.orc` candidates referenced by
  `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`;
- WCC characterization sources under
  `tests/fixtures/workflow_lisp/characterization/sources/`;
- checked-in parent-callable and Design Delta migration fixtures under
  `tests/fixtures/workflow_lisp/valid/design_delta*`;
- any `.orc` fixture explicitly referenced by a registry-covered compiler test.

The validator does not require every one-off invalid fixture under
`tests/fixtures/workflow_lisp/invalid/` to be registered. If a doc, parity
target, or registry-covered test cites an invalid fixture as evidence, then it
must be registered as `historical_negative`.

### Route/Schema Consistency

Validation uses `lowering_schema_for_route(...)`:

- `legacy` must map to schema `1`;
- all WCC routes map to schema `2`;
- `wcc_default` must use the current `DEFAULT_LOWERING_ROUTE`;
- preview routes such as `wcc_m2` or `wcc_m3` may appear only as
  `historical_negative`, `legacy_schema1_compat`, or explicitly scoped
  compatibility evidence, never as default-route evidence.

## Implementation Architecture

### Module Boundary

Add:

```text
orchestrator/workflow_lisp/route_readiness.py
tests/test_workflow_lisp_route_readiness.py
docs/workflow_lisp_route_readiness_registry.json
```

`route_readiness.py` provides:

- dataclasses or typed dictionaries for registry entries;
- enum constants for `route_label`, `surface_kind`, and `readiness_label`;
- `load_route_readiness_registry(path: Path)`;
- `validate_route_readiness_registry(registry, repo_root: Path)`;
- `discover_required_orc_surfaces(repo_root: Path)`;
- `registry_entry_for_path(registry, path: str)`;
- `validate_migration_target_route_identity(target, registry)`.

No compile, lowering, or runtime module imports `route_readiness.py` except
for migration-parity validation and CLI/test entrypoints. This keeps the
registry out of semantic artifacts.

### CLI Boundary

Add a narrow command:

```bash
python -m orchestrator workflow-lisp-route-readiness \
  --registry docs/workflow_lisp_route_readiness_registry.json \
  --check
```

The command prints a JSON summary with:

- `schema_version`;
- `registry_path`;
- `surfaces_checked`;
- `missing_required_surfaces`;
- `route_schema_mismatches`;
- `migration_target_mismatches`;
- `overall_pass`.

It exits:

- `0` when the registry is valid;
- `1` when validation fails;
- `2` for malformed input or unreadable files.

The command is validation only. It does not compile workflows and does not
write derived catalog files in this slice.

### Migration-Parity Integration

Keep `migration_parity.py` as the promotion evidence authority. Add a small
validation hook that can be called after `load_parity_targets(...)`:

```text
validate_parity_targets_against_route_readiness(
  targets,
  registry,
  repo_root
)
```

The hook checks:

- every target candidate path has a registry entry;
- target `readiness_label` matches the registry when present;
- target `lowering_route` and `lowering_schema_version` match the registry;
- `required_family_evidence_roles` are not cited for a target whose registry
  label is only `leaf_compile_candidate` or `leaf_runtime_candidate`;
- `promotion_eligible` registry entries agree with
  `promotion_eligibility.eligible_for_primary_surface=true`.

Initial implementation may run this hook from
`tests/test_workflow_lisp_route_readiness.py` before exposing a
`migration-parity --route-readiness-registry` flag. If exposed later, the flag
must fail closed before report generation when target identity is stale.

### Test Helper Convention

Add a helper used by registry-covered compiler/lowering tests:

```python
compile_registered_route_case(
    registry_id: str,
    *,
    source_path: Path,
    default_route_check: bool = False,
    **compile_kwargs,
)
```

Behavior:

- looks up the registry entry;
- if `default_route_check` is false, injects or verifies the entry's
  `lowering_route`;
- if `default_route_check` is true, asserts the registry entry's route equals
  `DEFAULT_LOWERING_ROUTE` and does not override the compiler default;
- asserts the compile/build result's reported `lowering_schema_version` equals
  the registry schema;
- exposes the entry metadata for the test assertion.

Existing tests do not need to be rewritten wholesale in this slice. The first
implementation should convert the representative tests named by the registry:
WCC characterization, build-artifact route/schema checks, example compile
tests, Design Delta feasibility tests, and migration parity tests.

### Documentation Projection

Update:

- `workflows/README.md`: add a "Workflow Lisp Route/Readiness Labels" section
  and make `.orc` catalog rows cite registry labels for current examples.
- `docs/lisp_workflow_drafting_guide.md`: state that `.orc` copy safety comes
  from the registry label plus parity evidence, not filename recency.

The registry remains source metadata. Markdown rows are views and may be
checked by tests, but they are not the authority for route identity.

## Current Checkout Facts And Feasibility Proof

### Current Checkout Facts

- `LoweringRoute.LEGACY` maps to schema 1; WCC routes map to schema 2.
- `DEFAULT_LOWERING_ROUTE` is `LoweringRoute.WCC_M4`.
- `build_frontend_bundle(...)` records `lowering_schema_version` in its
  manifest and has tests ensuring route names do not leak into source-map or
  semantic artifacts.
- `migration_parity.py` already stores `readiness_label`, `lowering_route`,
  and `lowering_schema_version` on `ParityTarget`.
- `compute_non_regressive(...)` already requires matching route identity for
  parent-family evidence roles.
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
  has a `parent_callable_candidate` label and route identity for
  `design_delta_parent_drain`, but older targets have no label.
- `workflows/README.md` has prose statuses for `.orc` examples but no
  machine-readable route labels.
- `tests/test_workflow_lisp_examples.py` currently wraps
  `compile_stage3_module` to default to legacy for that module, which proves
  UAF-02: a passing example test may be legacy evidence unless explicitly
  classified.

### Feasibility Proof

This slice depends on no unimplemented lowering capability. The needed
mechanisms already exist:

- route normalization and schema mapping are implemented in
  `orchestrator/workflow_lisp/wcc/route.py`;
- build manifests expose route-neutral schema evidence;
- migration parity already validates selected target identity and parent-route
  identity;
- tests already pin routes directly in many modules.

The new registry is a metadata and validation layer over those existing
capabilities. It is feasible without changing compiler semantics. The only
open prerequisite is policy coverage: deciding the initial registry rows and
which representative tests must migrate to the helper in the first patch.

## Diagnostics And Failure Modes

New validation failures should use stable codes in JSON summaries and test
assertions:

- `route_readiness_registry_schema_invalid`;
- `route_readiness_surface_missing`;
- `route_readiness_path_unknown`;
- `route_readiness_label_invalid`;
- `route_readiness_route_unknown`;
- `route_readiness_schema_mismatch`;
- `route_readiness_default_route_mismatch`;
- `route_readiness_migration_target_missing`;
- `route_readiness_migration_target_mismatch`;
- `route_readiness_stale_surface_without_owner`;
- `route_readiness_evidence_self_referential`;
- `route_readiness_test_route_unpinned`.

Failure examples:

- a new `workflows/examples/foo.orc` has no registry row;
- a row says `wcc_default` but `lowering_route` is `legacy`;
- a parity target says `parent_callable_candidate` but the registry says
  `leaf_compile_candidate`;
- a test marked as default-route evidence passes `LoweringRoute.LEGACY`;
- a stale surface lacks replacement or owner metadata.

## Verification Strategy

Add focused tests:

- registry accepts the checked-in initial registry;
- registry rejects missing required workflow example coverage;
- registry rejects route/schema mismatch;
- registry rejects `wcc_default` entries not using `DEFAULT_LOWERING_ROUTE`;
- registry rejects stale entries without owner or replacement;
- migration target route/readiness mismatch fails validation;
- representative compiler helper injects the registered route;
- default-route helper does not override the default and asserts WCC M4/schema
  2;
- markdown guidance mentions registry labels without becoming the authority.

Run at least:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_route_readiness.py tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_build_artifacts.py -q
python -m pytest tests/test_workflow_lisp_route_readiness.py -q
python -m pytest tests/test_workflow_lisp_migration_parity.py -k "route_identity or readiness_label or promotable or non_regressive" -q
python -m pytest tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_build_artifacts.py -k "route or schema or example" -q
python -m orchestrator workflow-lisp-route-readiness --registry docs/workflow_lisp_route_readiness_registry.json --check
git diff --check
```

## Implementation Notes

Suggested first patch order:

1. Add `route_readiness.py` with schema constants, dataclasses, loader, and
   pure validation helpers.
2. Add the initial registry covering `workflows/examples/*.orc`, the Design
   Delta library `.orc` files, WCC characterization sources, and migration
   parity candidates.
3. Add `tests/test_workflow_lisp_route_readiness.py` for schema, coverage, and
   migration-target checks.
4. Add the CLI command and parser tests.
5. Convert representative tests to the registry helper.
6. Update `workflows/README.md` and `docs/lisp_workflow_drafting_guide.md`.

Keep the first implementation data-driven. Avoid adding route-label logic to
the compiler or lowerers. Avoid using regex over generated artifact JSON for
semantic proof; compare typed registry fields, route enums, and existing
manifest fields.

## Acceptance

- Every required checked-in `.orc` example and Design Delta library candidate
  has a registry entry.
- Registry validation fails closed for missing coverage, unknown labels,
  route/schema mismatch, stale surfaces without owner/replacement, and
  migration target mismatch.
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
  cannot cite route/readiness identity that disagrees with the registry for a
  registry-covered candidate.
- Representative compiler/lowering tests either compile with an explicit
  registered route or declare that they intentionally exercise the default
  route.
- The workflow index and Lisp drafting guide direct authors to registry labels
  for `.orc` copy-safety.
- No semantic artifact gains lowering-route names; route names remain evidence
  metadata, while `lowering_schema_version` remains the artifact/runtime
  compatibility field.
- No WCC, legacy lowering, parent-drain, command-adapter, or promotion-gate
  behavior changes are required for the registry to pass.
