# Workflow Lisp Runtime-Native Drain Family-Specific Compiler Hook Retirement Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-runtime-native-drain-family-specific-compiler-hook-retirement`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected target-design gap:

- retire Design Delta-specific compile/build hooks from core Workflow Lisp
  compiler and build modules;
- make boundary authority, bridge materialization, typed prompt-input evidence,
  rendering evidence, transition evidence, resume-retirement evidence, G8
  deletion evidence, and reference-family conformance load from generic
  family-profile or family-evidence metadata instead of hardcoded
  `lisp_frontend_design_delta/drain::drain` checks;
- preserve the existing Design Delta parent-family compile/build evidence as
  one checked family profile; and
- add source-shape guards so new Design Delta name checks cannot re-enter core
  compiler modules.

Out of scope:

- changing Design Delta `.orc` workflow source shape;
- changing `std/drain`, `std/resource`, `std/phase`, `backlog-drain`, or
  `finalize-selected-item` semantics;
- deleting retained compatibility bridges or command-boundary rows;
- changing provider, command, runtime, Core Workflow AST, Semantic Workflow IR,
  executable IR, source-map, pointer-authority, or variant-proof contracts;
- adding scripts, inline command glue, report parsing, pointer-state reads, or
  compatibility-bundle rereads; and
- claiming YAML-primary promotion.

This is an implementation architecture for one hook-retirement slice. It does
not replace the target runtime-native drain design or the accepted Workflow
Lisp frontend baseline.

## Problem Statement

The target design requires that Design Delta-specific bridge augmentation and
compile-result evidence no longer depend on workflow-name checks inside core
compiler modules. The current checkout has already moved some ownership into a
generic `WorkflowFamilyProfileCatalog`, but build orchestration still contains
Design Delta-only entry gates and helper names.

Current examples in `orchestrator/workflow_lisp/build.py` include:

- `_maybe_load_design_delta_family_profile_catalog(...)` auto-loads only
  `design_delta_parent_drain.family_profile.json` when the source path or entry
  workflow names `lisp_frontend_design_delta`;
- `_maybe_load_design_delta_boundary_authority_registry(...)`,
  `_maybe_load_design_delta_value_flow_census(...)`,
  `_maybe_load_design_delta_consumer_rendering_census(...)`,
  `_maybe_load_design_delta_compatibility_bridge_manifest(...)`,
  `_maybe_load_design_delta_rendering_cleanup_manifest(...)`,
  `_maybe_load_design_delta_rendering_ergonomics_manifest(...)`,
  `_maybe_load_design_delta_transition_authoring_manifest(...)`,
  `_maybe_load_design_delta_resume_plumbing_retirement_manifest(...)`, and
  view dual-run loaders all gate on
  `entry_workflow == "lisp_frontend_design_delta/drain::drain"`;
- `_materialize_design_delta_compatibility_bridge_bundles(...)` and
  `_augment_design_delta_compatibility_bridge_lineage(...)` implement a useful
  generic compatibility-bridge materialization pattern, but their identity,
  allocation ids, diagnostics, and source-map lineage are Design Delta-named;
- `_serialize_design_delta_boundary_authority_report(...)`,
  `_serialize_design_delta_adapter_census(...)`, and
  `_serialize_design_delta_g8_deletion_evidence(...)` emit family evidence from
  hardcoded constants and paths; and
- `build_frontend_bundle(...)` emits parent-drain census alignment and
  reference-family conformance only when the loaded registry says
  `workflow_family == "design_delta_parent_drain"`.

Those hooks conflict with the target design when they remain as the mechanism
for boundary, bridge, rendering, and reference-family evidence. The slice must
turn the current Design Delta evidence lane into one profile-backed family
configuration while preserving its checked behavior.

## Design Constraints

This slice must preserve these contracts:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` Sections 12.1,
  15, and 16 require Design Delta-specific compile-result augmentation hooks to
  leave core compiler modules and any retained bridge/publication behavior to
  be declared through generic boundary syntax or generic build/parity metadata.
- `docs/design/workflow_lisp_frontend_specification.md` requires frontends to
  lower through Core AST, shared validation, Semantic IR, executable IR, and
  source maps without hidden filesystem effects, report parsing, or
  family-name-special lowering.
- `docs/design/workflow_command_adapter_contract.md` is authoritative for any
  command-boundary or adapter evidence touched by this slice. Existing
  certified command adapters may remain, but no command step or script may be
  introduced to manufacture retired-hook evidence.
- Prior runtime-native drain slices already distinguish shared stdlib proof
  work from downstream Design Delta family adoption. This slice only changes
  how family-specific evidence is selected and emitted.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

From the generated architecture index for this request:

- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-gap-drafter-callable-boundary-over-imported-backlog-drain/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-literal-name-stdlib-intrinsic-retirement/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-selector-stdlib-single-ctx-signature-alignment-regression-reopen/implementation_architecture.md`

### Decisions Reused

- Reuse the gap-drafter slice's rule that shared stdlib behavior must be
  proved through generic typed lowering and source maps, not Design Delta
  wrappers.
- Reuse the literal-name stdlib intrinsic retirement slice's deletion-evidence
  model: stale compiler-name routes fail through machine-readable evidence
  instead of being accepted as compatibility-tagged promoted behavior.
- Reuse the selector signature-alignment slice's boundary discipline: repair
  stale family wiring through typed calls and metadata, not command glue or
  public path-threading.
- Reuse `WorkflowFamilyProfileCatalog` as the existing generic owner for
  family membership, target workflows, boundary-authority registry paths,
  checked public inputs, hidden context rules, and typed prompt-input rows.

### New Decisions In This Slice

- Introduce one generic build-time family-evidence selection layer, fed by the
  loaded family profile and optional checked evidence manifests, to replace
  direct checks for `lisp_frontend_design_delta/drain::drain`.
- Generalize compatibility-bridge materialization and source-map augmentation
  by bridge metadata, workflow family id, and renderer contract instead of
  Design Delta-specific helper names.
- Keep Design Delta G8 deletion evidence as a family-specific evidence plugin
  or profile-declared evidence role, but invoke it through the generic family
  evidence layer.
- Add a synthetic non-Design-Delta family-profile fixture that exercises the
  generic selection path without loading Design Delta manifests.
- Add source-shape guards against hardcoded Design Delta workflow-name checks
  in core compiler/build modules.

### Conflicts Or Revisions

- The earlier literal-name stdlib intrinsic retirement slice focused on
  registry heads and direct stdlib lowerers. This slice does not revise that
  decision; it makes the surrounding Design Delta evidence selection generic.
- Existing helper names and schema ids may remain Design Delta-named during a
  compatibility window when they serialize a Design Delta-specific evidence
  artifact. The conflict is not the artifact label; the conflict is choosing or
  mutating compiler behavior by hardcoded Design Delta workflow names.
- No shared concepts such as spans, diagnostics, Core Workflow AST, Semantic
  IR, TypeCatalog, SourceMap, pointer authority, variant proof, resource
  transition, or command adapter certification are redefined here.

## Current Checkout Facts

- `orchestrator/workflow_lisp/family_profiles.py` already provides a generic
  `WorkflowFamilyProfileCatalog` and loader for family id, target workflows,
  workflow prefixes, boundary-authority registry path, checked public inputs,
  hidden context rules, and typed prompt-input rows.
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.family_profile.json`
  already declares the Design Delta target workflows, boundary registry, public
  input sets, hidden context rules, and typed prompt-input rows.
- `orchestrator/workflow_lisp/phase_family_boundary.py` uses the generic
  catalog for membership checks, but retains Design Delta-named schema
  constants and functions such as
  `is_design_delta_parent_drain_target_workflow(...)`,
  `load_design_delta_boundary_authority_registry(...)`, and
  `build_design_delta_boundary_authority_expected_rows(...)`.
- `orchestrator/workflow_lisp/build.py` has the hardcoded loaders and
  evidence-report emission described in the problem statement.
- `orchestrator/workflow_lisp/migration_parity.py` loads emitted compile
  artifacts generically by artifact name, but its Design Delta target metadata
  and G8 deletion evidence checks remain family-specific.
- `tests/test_workflow_lisp_build_artifacts.py` contains the strongest current
  coverage for Design Delta build artifacts, G8 deletion evidence, boundary
  authority, compatibility bridge lineage, rendering, transition, resume, and
  reference-family conformance.
- Existing checked Design Delta command-boundary manifests include retained
  certified/legacy adapter rows. This slice must not erase their adapter
  certification requirements.

## Feasibility Proof

This slice is feasible because the hard part already exists in bounded form:

1. The compiler accepts an optional `family_profile_catalog` and passes it into
   compile, boundary classification, lowering, and build projection paths.
2. Family metadata already records the Design Delta target workflows and
   boundary registry path without needing the build layer to parse workflow
   names.
3. Most evidence builders already accept explicit manifests or payloads as
   parameters. The missing piece is generic selection/loading of those payloads,
   not new evidence semantics.
4. Compatibility-bridge materialization is already metadata-driven enough to be
   generalized: bridge rows declare `workflow_surface`, `bridge_id`, renderer,
   target, typed value source, owner, consumer, and retirement metadata.
5. `tests/fixtures/workflow_lisp/family_profiles/generic_phase_family_profile.json`
   and family-profile tests provide a non-Design-Delta fixture lane for
   negative and source-shape proof.

The unproven part is whether all current Design Delta build-artifact tests can
pass after helper extraction without relying on monkeypatches of
`DESIGN_DELTA_PARENT_DRAIN_*` constants. That is an implementation risk to be
covered by focused regression tests and a transition period where compatibility
function names can delegate to generic helpers.

## Owned Components

This slice owns:

- `orchestrator/workflow_lisp/build.py`
  - replace hardcoded `_maybe_load_design_delta_*` entry gates with generic
    profile/evidence loading helpers;
  - generalize compatibility-bridge materialization and source-map lineage;
  - route Design Delta-specific reports through a generic family-evidence
    dispatcher;
  - preserve emitted artifact names for the Design Delta profile unless a
    manifest/schema change explicitly requires otherwise.
- `orchestrator/workflow_lisp/family_profiles.py`
  - add optional evidence-manifest path fields only if current profile metadata
    cannot route build evidence generically;
  - validate any new fields with closed schema diagnostics.
- `orchestrator/workflow_lisp/phase_family_boundary.py`
  - keep generic boundary classification and public/private checks;
  - split Design Delta schema loading/report naming from generic workflow
    family membership where needed.
- Tests in:
  - `tests/test_workflow_lisp_family_profiles.py`;
  - `tests/test_workflow_lisp_build_artifacts.py`;
  - `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`;
  - `tests/test_workflow_lisp_migration_parity.py`; and
  - source-shape guards that grep core modules for retired hardcoded names.
- Checked manifests under
  `workflows/examples/inputs/workflow_lisp_migrations/` only if a new generic
  profile field must reference existing Design Delta evidence paths.

This slice intentionally does not own:

- Design Delta `.orc` modules under
  `workflows/library/lisp_frontend_design_delta/`;
- stdlib `.orc` modules under `orchestrator/workflow_lisp/stdlib_modules/std/`;
- command-boundary certification content except preserving existing validation;
- runtime execution, provider output, command output, resource transition,
  source-map, Semantic IR, or executable IR semantics; or
- parity gate policy for primary-surface promotion.

## Proposed Component Architecture

### 1. Generic Family Evidence Descriptor

Add a small internal descriptor built from the loaded family profile and
checked manifest paths:

```text
FamilyEvidenceProfile
  family_id
  target_workflows
  entry_workflow
  boundary_authority_registry_path
  value_flow_census_path?
  consumer_rendering_census_path?
  compatibility_bridges_path?
  rendering_cleanup_path?
  rendering_ergonomics_path?
  transition_authoring_path?
  resume_plumbing_retirement_path?
  observability_old_writer_comparisons_path?
  view_dual_run_vectors_path?
  view_dual_run_report_path?
  g8_deletion_evidence_policy?
  reference_family_conformance_policy?
```

Preferred source:

- extend `workflow_lisp_family_profile.v1` additively with optional
  `evidence_manifests` and `evidence_policies` maps; or
- create a separate checked family-evidence manifest referenced by the family
  profile.

The additive profile route is simpler but makes the family profile carry more
build-specific metadata. A separate manifest keeps profile membership smaller
but adds one more checked file and freshness input. The implementation should
choose one; it must not infer evidence paths from filename conventions.

What this makes harder later: any new family evidence lane must be declared in
metadata before the build can emit it. That is intentional because the target
design rejects implicit family-name hooks.

### 2. Generic Evidence Loading

Replace per-file loaders like `_maybe_load_design_delta_value_flow_census(...)`
with one family-aware loader set:

```text
load_family_evidence_profile(...)
load_optional_family_manifest(profile, role, loader, required_inputs...)
```

Each loader must:

- return `None` when the family profile does not declare the role;
- validate schema with the existing role-specific loader;
- attach provenance fields such as `__manifest_path__` and
  `__manifest_sha256__`; and
- raise diagnostics against the declared manifest path, not against a hardcoded
  Design Delta constant.

Design Delta compatibility shims may remain temporarily as wrappers around
generic loaders if tests still patch old helper names. They must not contain
workflow-name conditions.

### 3. Generic Compatibility-Bridge Materialization

Rename and generalize:

- `_materialize_design_delta_compatibility_bridge_bundles(...)` to
  `_materialize_family_compatibility_bridge_bundles(...)`;
- `_augment_design_delta_compatibility_bridge_lineage(...)` to
  `_augment_family_compatibility_bridge_lineage(...)`; and
- `_compatibility_bridge_value_document(...)` to resolve typed value sources
  from metadata rather than a hardcoded `known_refs` table.

The bridge metadata must be the authority for:

- source typed value reference;
- renderer id and version;
- target binding;
- workflow surface;
- owner/consumer/retirement metadata; and
- source-map form path.

If a retained Design Delta bridge still needs a compatibility alias such as
`drain.architecture_bundle`, that alias must live in checked bridge metadata or
a family evidence descriptor, not in a core build helper table.

### 4. Generic Family Report Dispatch

Build orchestration should emit optional reports by declared family evidence
roles:

```text
boundary_authority_report
value_flow_census_report
consumer_rendering_census_report
typed_prompt_input_report
observability_summary_report
entry_publication_report
compatibility_bridge_report
rendering_cleanup_report
rendering_ergonomics_report
transition_authoring_report
resume_plumbing_retirement_report
parent_drain_census_alignment_report
reference_family_conformance_profile
g8_deletion_evidence
```

The Design Delta profile can still declare the full current set. A synthetic
fixture profile should declare only a small subset, proving the build layer no
longer assumes Design Delta paths when a family profile exists.

G8 deletion evidence remains Design Delta-specific in content because it names
removed Design Delta rows and helper symbols. It should be implemented as a
declared `evidence_policy` for the `design_delta_parent_drain` family, not as a
hardcoded `if workflow_family == "design_delta_parent_drain"` branch in the
core build path.

### 5. Boundary Authority Naming Cleanup

`phase_family_boundary.py` may keep existing schema ids for checked Design
Delta manifests, but generic membership and target-workflow detection should
use `WorkflowFamilyProfileCatalog` directly.

Implementation options:

- leave Design Delta schema loader functions in place but call them only from
  the Design Delta family-evidence policy; or
- rename them to generic boundary-authority registry loaders while preserving
  the accepted Design Delta schema id for compatibility.

The first option is lower risk. The second option is cleaner but touches more
tests. The bounded implementation should prefer the lower-risk option unless
the source-shape guards cannot distinguish a schema-specific loader from a core
workflow-name branch.

### 6. Source-Shape Guard

Add a deterministic guard that fails if core modules regain hardcoded Design
Delta workflow names or constants outside allowed compatibility declarations.

Initial guard targets:

- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/phase_family_boundary.py`
- `orchestrator/workflow_lisp/lowering/`
- `orchestrator/workflow_lisp/typecheck_dispatch.py`

Allowed occurrences should be narrow and documented:

- Design Delta-specific schema ids or constants inside explicit
  Design Delta evidence-policy modules;
- tests and fixtures;
- checked Design Delta manifests; and
- user-facing report labels in emitted Design Delta artifacts.

The guard must not ban the string from workflows, tests, or checked metadata.
It must ban workflow-name dispatch in core compiler/build code.

## Data And Control Flow

1. `build_frontend_bundle(...)` resolves the request, externs, command
   boundaries, and imported bundles as today.
2. It loads a `WorkflowFamilyProfileCatalog` from explicitly supplied or
   discoverable profile paths.
3. After selecting the entry workflow, it resolves the matching family profile.
4. If the family profile declares evidence metadata for the entry workflow, the
   build layer loads those manifests by role.
5. Compile and lowering receive the same `family_profile_catalog` as today.
6. Boundary projection and source-map serialization run normally.
7. Compatibility bridges are materialized by generic bridge metadata.
8. Optional reports are emitted by declared role, and Design Delta-specific
   reports run only through the Design Delta evidence policy.
9. The build manifest records family profile and evidence manifest provenance.
10. Migration parity reads emitted compile artifacts by artifact name as it does
    today.

No report, pointer file, stdout payload, debug YAML, or compatibility bridge
becomes semantic authority for workflow routing.

## Command Adapter Policy

No new command adapter is proposed. Existing Design Delta command-boundary rows
remain governed by `docs/design/workflow_command_adapter_contract.md`.

If implementation changes any command-boundary manifest or adapter census
behavior, the retained boundary must still declare typed inputs, typed outputs,
effects, artifacts, state writes, path-safety expectations, error taxonomy,
fixtures, negative fixtures, source-map behavior, owner module, and retirement
path. This slice must not replace family-specific compiler hooks with scripts,
inline Python, shell, report parsing, or pointer-as-state.

## Verification Strategy

Minimum deterministic checks for the later implementation:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_family_profiles.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_migration_parity.py
python -m pytest tests/test_workflow_lisp_family_profiles.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "family_profile or design_delta_parent_drain or boundary_authority or compatibility_bridge or g8_deletion_evidence or reference_family" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_parent_drain" -q
python -m pytest tests/test_workflow_lisp_migration_parity.py -k "design_delta_parent_drain or g8_deletion_evidence or boundary_authority" -q
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
rg -n "lisp_frontend_design_delta/drain::drain|entry_workflow != \"lisp_frontend_design_delta/drain::drain\"|entry_workflow == \"lisp_frontend_design_delta/drain::drain\"|_maybe_load_design_delta" orchestrator/workflow_lisp/build.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/lowering orchestrator/workflow_lisp/typecheck_dispatch.py
```

Expected evidence:

- Design Delta parent-family compile still emits the same required compile
  artifact roles;
- emitted artifact payloads record family profile and manifest provenance;
- compatibility bridge materialization appears in executable, Semantic IR, and
  source-map lineage through generic bridge metadata;
- G8 deletion evidence is still emitted and still fails when retired registry
  heads or deleted manifest rows are reintroduced;
- a synthetic non-Design-Delta profile fixture can load without Design Delta
  manifests or workflow-name checks;
- source-shape guards find no core workflow-name dispatch for
  `lisp_frontend_design_delta/drain::drain`; and
- no new command-boundary rows or uncertified adapters are introduced.

## Acceptance Conditions

This slice is complete when:

- `build_frontend_bundle(...)` no longer chooses Design Delta evidence by
  hardcoded `lisp_frontend_design_delta/drain::drain` checks;
- family profile or family evidence metadata declares every Design Delta
  evidence manifest consumed by the build path;
- boundary authority, value-flow, consumer-rendering, typed-prompt,
  observability, entry-publication, compatibility-bridge, rendering-cleanup,
  rendering-ergonomics, transition-authoring, resume-retirement,
  parent-census, reference-family, and G8 evidence are emitted through a
  generic role dispatcher;
- compatibility-bridge materialization and source-map lineage use checked
  bridge metadata rather than a hardcoded Design Delta reference table;
- Design Delta-specific G8 deletion evidence remains available only as a
  declared family evidence policy;
- existing Design Delta parent-family compile, build-artifact, migration
  feasibility, and parity tests remain green;
- a non-Design-Delta family-profile fixture proves the generic path does not
  auto-load Design Delta manifests;
- source-shape guards prevent reintroducing Design Delta workflow-name branches
  in core compiler/build/lowering modules; and
- no source code, test, or manifest change weakens command-adapter
  certification, structured bundle authority, pointer authority, variant proof,
  source-map coverage, or migration-promotion gates.

## Implementation Handoff

The later implementation plan should:

1. add failing source-shape tests for hardcoded Design Delta workflow-name gates
   in core build/compiler modules;
2. add or extend a generic family evidence descriptor and fixture profile;
3. replace `_maybe_load_design_delta_*` entry gates with metadata-driven
   optional family evidence loading;
4. generalize compatibility-bridge materialization and source-map augmentation;
5. route Design Delta G8 deletion and reference-family conformance through a
   declared family evidence policy;
6. keep compatibility wrappers only as temporary delegators if needed by tests;
7. rerun focused Design Delta build/parity selectors and the synthetic
   non-Design-Delta profile checks; and
8. stop before changing `.orc` source shape, stdlib semantics, command adapter
   certification, runtime behavior, or YAML-primary promotion.
