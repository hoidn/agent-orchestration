# Reference-Family Completion Inventory Realignment Implementation Architecture

## Scope

This slice covers exactly the selected gap:

`workflow-lisp-runtime-native-drain-reference-family-completion-inventory-realignment-after-final-gap-closures`

The goal is to make the Design Delta reference-family conformance gate recognize
completed target-design evidence only when the completed-gap inventory is
durable and internally consistent. The slice is an inventory and evidence
realignment, not a new Workflow Lisp language feature.

In scope:

- reconcile the `completion_inventory` surface in the Design Delta
  reference-family conformance profile;
- make completed-gap evidence line up across canonical run state, drain
  summary, per-gap summary artifacts, implementation architecture files, and
  the architecture index consumed by the gate;
- ensure the selected gap has durable implementation architecture evidence at
  both the generated R10 handoff path and the production checked architecture
  root consumed by the Design Delta parent-drain build;
- ensure the production checked architecture index consumed by the conformance
  gate names the selected gap or its production architecture path;
- update focused tests around completed-gap inventory acceptance and failure
  modes; and
- keep the conformance profile diagnostics source-mapped to checked evidence
  paths and the `completion_inventory` surface.

Out of scope:

- changing WCC lowering, Workflow Lisp syntax, stdlib behavior, provider
  result semantics, resource transitions, or runtime execution;
- promoting the `.orc` family to YAML primary;
- reworking unrelated conformance surfaces such as provider inputs, bridge
  metadata, rendering cleanup, command boundary certification, or migration
  parity;
- rewriting run-state history or queue state; and
- using generated reports, markdown, pointer files, or stdout as semantic
  authority.

## Design Constraints

This implementation must stay coherent with:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
  Sections 2.1, 11, 13.4, and 15;
- `docs/design/workflow_lisp_frontend_specification.md`, especially the
  semantic authority, source-map, WCC, and report-as-view rules;
- `docs/design/workflow_command_adapter_contract.md`;
- `docs/steering.md`, which is empty in this checkout and does not widen the
  selected scope; and
- the generated architecture review report, which requires production checked
  architecture-root and architecture-index alignment as part of the target
  completion contract rather than as deferred follow-up.

The active design requires a reference-family conformance profile that does not
confuse parent-callability or compile success with target completion. For this
slice, "completed" means the canonical run-state completed-gap list is matched
by:

- the drain summary's ordered `completed_design_gaps` list;
- one per-gap `*-summary.json` artifact with `item_status: "COMPLETED"` and a
  `run_state_path` matching the checked run-state path;
- one implementation architecture file under the checked implementation
  architecture root; and
- an architecture index that names either the completed gap id or the checked
  architecture file path.

If this slice touches command-boundary manifests or scripts while wiring the
build checks, the command-adapter contract applies. A script used only as a
deterministic validator must be treated as an explicit validator boundary with
declared inputs, stable errors, and tests. It must not become hidden workflow
semantics or parse reports as authority.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The run-local architecture index at
`state/workflow_lisp/calls/20260629T155304Z-p99pkj/root.drain_lisp_frontend_work_0.lisp_frontend_drain_iteration.route_selection.desig_f289187df7d2/lisp-frontend-design-delta-design-gap-architect-v214/de14bca20ef59f36.json/existing-architecture-index.md`
reported:

> No prior implementation architecture documents were found.

For structure only, the general design-gap architecture template was also
consulted. It points to an example path that is not present in this checkout,
so this document follows the bounded implementation-architecture shape used by
nearby Workflow Lisp gap architectures without importing their decisions as
prior R10 decisions.

### Decisions Reused

- Reuse `orchestrator/workflow_lisp/reference_family_conformance.py` as the
  owner of the reference-family conformance aggregation and diagnostics.
- Reuse `orchestrator/workflow_lisp/build.py` as the build-time integration
  point that invokes the conformance profile for the Design Delta parent-drain
  family.
- Reuse the existing `completion_inventory` surface id, question, owner lane,
  and diagnostic codes:
  `reference_family_completed_gap_summary_mismatch` and
  `reference_family_completed_gap_artifact_missing`.
- Reuse the baseline semantic authority model: run state and typed JSON
  evidence are checked inputs; reports and markdown remain views.
- Reuse the existing directory shapes:
  `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/run_state.json`,
  `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain-summary.json`,
  `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/`, and
  `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/`.

### New Decisions In This Slice

- Treat the checked implementation architecture directory and architecture
  index as first-class evidence inputs for the completed-gap inventory gate,
  not as advisory docs.
- Require every gap listed in canonical completed run state to have an
  implementation architecture file at the checked root before
  `completion_inventory` can pass.
- Require the architecture index to mention each completed gap id or the
  corresponding architecture path so the inventory is reviewable without
  scanning the whole tree manually.
- Keep this R10 architecture as the generated handoff for the selected gap, and
  require the implementation slice to backfill the same selected-gap
  architecture contract under the production checked root used by `build.py`:
  `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/<gap-id>/implementation_architecture.md`.
- Require the production checked architecture index at
  `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/iterations/12/done-review/design-gap-architect/existing-architecture-index.md`
  to be regenerated or updated from checked production architecture files
  before the `completion_inventory` surface can pass.
- Make test fixtures exercise both aligned inventory and stale/missing
  inventory failure modes.

### Conflicts Or Revisions

There are no prior R10 implementation architectures to revise.

This slice does not revise shared concepts such as spans, diagnostics, Core
Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority,
variant proof, WCC lowering, or command-adapter certification.

## Current Checkout Facts

- `orchestrator/workflow_lisp/reference_family_conformance.py` already includes
  the `completion_inventory` surface and reconciles completed gaps through
  `_reconcile_completed_gaps`.
- The reconciliation compares canonical run-state completed gaps with the drain
  summary, per-gap summary artifacts, implementation architecture files, and
  architecture index text.
- `orchestrator/workflow_lisp/build.py` wires the Design Delta parent-drain
  build to:
  - `REFERENCE_FAMILY_RUN_STATE_PATH`;
  - `REFERENCE_FAMILY_DRAIN_SUMMARY_PATH`;
  - `REFERENCE_FAMILY_DESIGN_GAP_SUMMARY_ROOT`;
  - `REFERENCE_FAMILY_IMPLEMENTATION_ARCHITECTURE_ROOT`; and
  - `REFERENCE_FAMILY_ARCHITECTURE_INDEX_PATH`.
- In this checkout, those production checked architecture paths resolve to:
  - `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/`; and
  - `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/iterations/12/done-review/design-gap-architect/existing-architecture-index.md`.
- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/run_state.json`
  currently lists the selected gap in `completed_design_gaps`.
- `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-reference-family-completion-inventory-realignment-after-final-gap-closures-summary.json`
  exists and records the selected gap as `COMPLETED` against the canonical
  run-state path.
- The selected run's `progress_ledger.json` is empty, so it cannot be used as
  evidence that supersedes the checked run-state and artifact inventory.
- The selected run-local architecture index reports no prior implementation
  architecture documents, so this document is the first architecture for this
  R10 selected gap.
- The architecture review report has decision `REVISE` because the draft
  deferred production checked architecture-root and index alignment even though
  the target completion gate requires durable completed-gap evidence at those
  checked conformance roots.

## Proposed Implementation

### 1. Inventory Contract

Keep the conformance profile's completed-gap reconciliation rooted in the
existing checked inputs. The implementation should make the expected contract
explicit in code comments or helper naming, but it should not introduce a
second authority file that can disagree with run state.

For each gap id in `run_state.payload.completed_design_gaps`, the
`completion_inventory` gate accepts only if:

- `drain_summary.payload.completed_design_gaps` is the same ordered list;
- `design_gap_summary_root/<gap-id>-summary.json` exists;
- that summary JSON has:
  - `work_item_id == <gap-id>`;
  - `work_item_source == "DESIGN_GAP"`;
  - `item_status == "COMPLETED"`; and
  - `run_state_path` equal to the checked run-state path relative to the repo;
- `implementation_architecture_root/<gap-id>/implementation_architecture.md`
  exists; and
- `architecture_index_path` text contains either `<gap-id>` or the repo-relative
  implementation architecture path.

The gate should continue to fail closed when any input is missing, malformed,
or stale.

### 2. Architecture Inventory Backfill

Keep the selected gap architecture at the generated R10 handoff path:

`docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R10/design-gaps/workflow-lisp-runtime-native-drain-reference-family-completion-inventory-realignment-after-final-gap-closures/implementation_architecture.md`

The implementation slice must also add or realign the matching production
checked architecture file consumed by `REFERENCE_FAMILY_IMPLEMENTATION_ARCHITECTURE_ROOT`:

`docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-reference-family-completion-inventory-realignment-after-final-gap-closures/implementation_architecture.md`

That production file is required evidence. It is the architecture document that
the Design Delta parent-drain build checks against canonical completed-gap run
state. The R10 file remains the generated handoff for this selected draft/review
step; it is not sufficient by itself for the production `completion_inventory`
surface.

The architecture index consumed by the production conformance gate must be
regenerated or updated from checked production architecture files:

`state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/iterations/12/done-review/design-gap-architect/existing-architecture-index.md`

It must name either the selected gap id or the repo-relative production
architecture path above. The implementation must not leave this index as a
stale run-local prompt artifact whose contents no longer cover the completed
run-state inventory.

### 3. Conformance Profile Wiring

Keep `build_reference_family_conformance_profile(...)` as the single
aggregation function. Changes should be limited to the completed-gap inventory
lane unless an adjacent helper must be made more explicit.

Expected behavior:

- `completed_gap_reconciliation.status == "pass"` only when all completed-gap
  inventory checks pass;
- `completion_inventory` surface rows expose the evidence paths from run state,
  drain summary, summary root, implementation architecture root, and
  architecture index;
- stale per-gap summary metadata remains reported as
  `reference_family_completed_gap_artifact_missing`;
- ordered-list drift between run state and drain summary remains reported as
  `reference_family_completed_gap_summary_mismatch`; and
- missing implementation architecture files or index coverage remain part of
  the same completed-gap artifact diagnostic.

Wire `missing_from_architecture_index` into the diagnostic/status path with the
same `completion_inventory` surface id. Index drift must make
`completed_gap_reconciliation.status` fail, just like a missing architecture
file, instead of allowing a pass based only on file existence.

### 4. Tests

Add or update focused tests in:

- `tests/test_workflow_lisp_reference_family_conformance.py`; and
- `tests/test_workflow_lisp_build_artifacts.py` if the build integration path
  changes.

Required cases:

- aligned fixture passes with the selected gap represented in run state, drain
  summary, summary artifact, implementation architecture file, and architecture
  index;
- missing per-gap summary artifact fails with
  `reference_family_completed_gap_artifact_missing`;
- stale per-gap summary metadata fails with
  `reference_family_completed_gap_artifact_missing`;
- missing implementation architecture file fails with
  `reference_family_completed_gap_artifact_missing`;
- missing architecture index coverage fails the reconciliation status and emits
  the completed-gap artifact diagnostic details needed by the build profile;
- the selected gap has production checked architecture evidence under
  `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/`, not only
  under the generated R10 handoff root;
- production Design Delta parent-drain build emits a conformance profile whose
  `completion_inventory` surface has nonempty evidence paths when the aligned
  fixture paths are supplied.

The tests should use temporary fixture roots for destructive or negative cases.
They must not mutate checked run-state, queue state, or production artifacts.

## Files And Components

This slice is expected to change:

- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R10/design-gaps/workflow-lisp-runtime-native-drain-reference-family-completion-inventory-realignment-after-final-gap-closures/implementation_architecture.md`
  for this architecture;
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-reference-family-completion-inventory-realignment-after-final-gap-closures/implementation_architecture.md`
  for the production checked architecture evidence consumed by the conformance
  gate;
- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/iterations/12/done-review/design-gap-architect/existing-architecture-index.md`
  so the production checked index covers the selected completed gap;
- the selected run-local work-item context and check-command files;
- `orchestrator/workflow_lisp/reference_family_conformance.py` to make
  architecture-index omissions participate in fail-closed status and
  diagnostics if the current implementation still reports them without failing;
- `orchestrator/workflow_lisp/build.py` only if the existing production checked
  architecture paths are wrong; the preferred route is to align the checked
  files at the paths already referenced by the build constants;
- `tests/test_workflow_lisp_reference_family_conformance.py`; and
- `tests/test_workflow_lisp_build_artifacts.py` for build integration coverage.

This slice relies on but should not redefine:

- Core Workflow AST;
- Semantic Workflow IR;
- Executable IR;
- TypeCatalog;
- SourceMap;
- variant proof;
- pointer authority;
- WCC lowering; and
- the command-adapter contract.

## Outside-Use Rule

The completed-gap inventory helpers and constants are used by both direct
reference-family conformance tests and the Design Delta parent-drain build
artifact path. Any outside use must follow the same rule:

Do not treat membership in `completed_design_gaps` as sufficient completion
evidence. A completed gap counts for the reference-family conformance profile
only when canonical run state, drain summary, per-gap summary artifact,
implementation architecture file, and architecture index coverage all agree.

Outside callers may supply alternate roots for tests or controlled builds, but
they must preserve the same fail-closed validation semantics and diagnostic
surface ids.

## Failure Modes

- If run state and drain summary disagree, fail with
  `reference_family_completed_gap_summary_mismatch`.
- If a per-gap summary is missing, malformed, stale, or tied to the wrong
  run-state path, fail with `reference_family_completed_gap_artifact_missing`.
- If a completed gap has no implementation architecture file under the checked
  root, fail with `reference_family_completed_gap_artifact_missing`.
- If the architecture index omits a completed gap, fail on the
  `completion_inventory` surface, set reconciliation status to `fail`, and
  include the missing gap ids in diagnostic details.
- If a future implementation tries to satisfy the gate by parsing markdown
  reports, pointer files, stdout, or provider prose, reject that route as
  outside the semantic authority contract.

## Verification

Use the deterministic commands in the generated `check_commands.json` for the
implementation plan. The minimum verification set is:

- focused conformance-profile unit tests for completed-gap inventory;
- build-artifact tests proving Design Delta parent-drain emits the reference
  family conformance profile and fails on inventory drift; and
- a Design Delta parent-drain compile/build check because this slice requires
  production checked architecture-root and architecture-index evidence
  realignment.

## Handoff Notes

The implementation should start from the existing conformance helpers rather
than adding a parallel inventory validator. The narrowest likely code change is
to make architecture-index coverage participate in the same fail-closed
diagnostic/status path as missing summary or architecture artifacts, then align
the production checked architecture file and production checked architecture
index at the paths already consumed by `build.py`.

Production evidence alignment is required for this slice. Do it as explicit
checked artifact/doc updates. Do not silently rewrite historical run state,
route the build to the generated R10 handoff path, or make compile success
stand in for durable completion evidence.
