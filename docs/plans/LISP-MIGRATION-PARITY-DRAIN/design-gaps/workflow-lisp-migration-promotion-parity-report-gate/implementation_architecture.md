# Workflow Lisp Migration Promotion Parity Report Gate Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-migration-promotion-parity-report-gate`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected migration-promotion evidence gap:

- add one machine-readable parity-target manifest for the current Workflow Lisp
  migration families;
- add one authoritative JSON parity-report schema and derived report writers for
  per-family reports plus the aggregate parity index;
- add one deterministic promotion command path that executes the approved
  compile, dry-run, smoke-or-integration, and parity-assertion evidence checks;
- compute `non_regressive` from captured evidence instead of allowing authors to
  assert it manually;
- refresh the checked migration evidence for the current migrated workflow
  family (`cycle_guard_demo` and `design_plan_impl_stack`) through that command
  path;
- preserve YAML as primary whenever computed evidence remains regressive.

Out of scope for this slice:

- command-result bundle ownership, review-loop generic composition, review
  findings, workflow input defaults, or reusable-state validation beyond
  reusing the evidence they already produce;
- redesign of Core Workflow AST, Semantic IR, Executable IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, or runtime execution semantics;
- introducing new workflow command adapters, runtime-native effects, inline
  shell/Python workflow glue, or markdown report parsing as semantic authority;
- automatic edits to `workflows/README.md`, catalog status labels, or YAML
  deprecation policy after report generation;
- a general-purpose workflow-diff engine for arbitrary YAML/`.orc` families
  beyond the bounded promotion manifest owned here.

This is a bounded implementation architecture for one selected migration gap
only. It does not replace the parent migration architecture or reopen the
umbrella Workflow Lisp frontend contract.

## Problem Statement

The selected target design already chose the required promotion-evidence model:

- parity promotion must be machine-checked rather than asserted in markdown;
- `non_regressive` must be computed from evidence, not authored by hand;
- required evidence includes compile, shared validation, dry-run, smoke or
  targeted integration, baseline characterization, parity axes, and deprecated
  YAML mechanics;
- optional compiler artifacts must be recorded as `not_implemented` rather than
  silently omitted.

The current checkout still falls short in five concrete ways:

1. `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json` is only a
   historical inventory with manual-looking booleans and paths to markdown
   reports, not a machine-checked promotion report.
2. The per-target parity artifacts are markdown summaries only; there is no
   authoritative JSON report carrying the target design's evidence fields.
3. There is no checked-in manifest that defines the deterministic evidence
   commands, baseline characterization, waiver policy, and deprecated-mechanic
   replacements for the migrated workflow families.
4. There is no CLI command or library module that reruns the evidence, writes
   the report, and computes `non_regressive`.
5. Existing parity-focused tests live in
   `tests/test_workflow_lisp_key_migrations.py`, but nothing packages their
   outcomes into the target design's promotion gate.

The gap is therefore not "invent migration parity" and not "reopen the earlier
compiler/runtime slices." The gap is to turn the current historical parity
artifacts into a deterministic, machine-readable promotion-evidence surface
that reuses the already-implemented compile/runtime/test paths.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Required Changes By Gap`
  - `4. Migration Evidence Layer`
  - `Dependencies And Sequencing`
  - `Evidence And Implementation Boundaries`
  - `Verification Strategy`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 2.2, 18, 45-48, 74-80, 95, 105
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `workflows/README.md`
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `docs/steering.md`

The slice must preserve these guardrails:

- keep structured bundles, validated artifacts, and typed state authoritative;
- keep markdown parity reports, debug YAML, CLI logs, and indexes as derived
  views rather than promotion authority;
- reuse the existing compile/run/test paths instead of recreating workflow
  semantics in a report generator;
- keep deterministic evidence commands explicit and machine-readable; do not
  hide promotion semantics inside ad hoc shell pipelines or prose parsing;
- keep `non_regressive` derived inside code from evidence, never loaded from
  input manifests or hand-edited report files;
- keep the public/internal compiled-workflow input split from the earlier
  parity slices; hidden managed inputs remain implementation detail and must not
  become promotion requirements;
- do not treat the empty `docs/steering.md` file as permission to widen scope.

`docs/design/workflow_command_adapter_contract.md` remains authoritative even
though this slice should not add new workflow command adapters. The parity tool
must not become a loophole for hidden semantic shell glue, pointer-as-state, or
report-authority decisions.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-defworkflow-input-default-parity/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-resume-or-start-reusable-state-validation/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-findings-structured-dataflow/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`

### Decisions Reused

- Reuse the command-result slice's public/internal compiled-workflow input split
  and runtime-owned managed-write-root policy; promotion evidence must not
  require users to bind internal `__write_root__...` names.
- Reuse the input-default slice's rule that authored defaults propagate through
  the existing workflow input contract rather than through a second metadata
  channel.
- Reuse the reusable-state slice's `resume-or-start` parity fixtures and
  sidecar-backed validation behavior as evidence inputs rather than rechecking
  reusable-state semantics inside the promotion tool.
- Reuse the review-loop generic-composition and structured-findings slices as
  the authority for review/fix loop semantics and findings transport.
- Reuse the existing Workflow Lisp build-manifest artifact surface in
  `orchestrator/workflow_lisp/build.py`, especially `artifact_paths` and
  `artifact_status`, instead of inventing a parallel compile-artifact catalog.
- Reuse the existing migration test suite as the semantic evidence substrate
  where focused parity assertions are already encoded and safe to rerun.

### New Decisions In This Slice

- Introduce one checked-in parity-target manifest as the authoritative source
  for target ids, deterministic evidence commands, baseline characterization,
  deprecated YAML mechanics, and waiver metadata.
- Make per-target JSON reports authoritative and treat markdown summaries plus
  the aggregate `index.json` as derived views.
- Compute `non_regressive` only from the recorded evidence object and reject any
  manifest/report input that tries to author it directly.
- Keep parity-axis evaluation bounded by explicit deterministic checks declared
  in the manifest rather than inventing a generic workflow semantic diff engine.
- Regenerate the existing migrated-family reports through the promotion command
  even when the computed outcome remains `false`.

### Conflicts Or Revisions

The current historical parity artifacts implicitly treat markdown and the
aggregate `index.json` as the durable record of migration status. This slice
revises that assumption narrowly:

- per-target JSON reports become the authoritative promotion record;
- markdown summaries and the aggregate index become deterministic projections of
  those JSON reports;
- `non_regressive` in generated artifacts is always computed, never copied from
  hand-authored source.

The earlier parity-gap slices explicitly excluded promotion reporting. This
slice does not revise their semantic decisions; it consumes their evidence and
turns it into the parent design's promotion gate.

No shared concepts are redefined. Core Workflow AST, Semantic IR, TypeCatalog,
SourceMap, pointer authority, variant proof, and runtime execution ownership
remain with their existing owners.

## Ownership Boundaries

This slice owns:

- one source-controlled parity-target manifest for the current Workflow Lisp
  migration families;
- one Workflow Lisp promotion-report library that loads manifests, executes
  evidence commands, normalizes results, computes parity status, and renders
  report projections;
- one CLI command that invokes that library and writes refreshed reports and
  aggregate indexes;
- report-schema validation, waiver validation, and `non_regressive`
  computation;
- focused tests for manifest parsing, report computation, derived views, CLI
  behavior, and current migrated-family refresh.

This slice intentionally does not own:

- compile, dry-run, smoke, reusable-state, or review-loop semantics themselves;
- runtime workflow execution, bundle validation, or shared validation logic;
- new workflow command adapters, review providers, prompt contracts, or runtime
  state layouts;
- automatic promotion of `.orc` surfaces in workflow catalogs or deprecation of
  YAML primaries;
- general parity tooling for unrelated workflow families outside the selected
  Workflow Lisp migration targets.

## Current Checkout Facts

The current checkout already contains substrate this slice should reuse:

- `orchestrator/workflow_lisp/build.py` emits deterministic build manifests with
  `artifact_paths` and `artifact_status`.
- `orchestrator/cli/main.py` already exposes compile, run, explain, resume, and
  report command families, so one additional promotion-report command can fit
  the existing CLI structure.
- `tests/test_workflow_lisp_key_migrations.py` already contains focused
  migration evidence for command-result runtime behavior, review-loop parity,
  and reusable-state parity.
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
  already records the historical migrated targets and their regressive status.

The same checkout also shows the exact missing promotion-gate behavior:

- there is no module under `orchestrator/workflow_lisp/` or `orchestrator/cli/`
  that generates machine-readable promotion reports or computes
  `non_regressive`;
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json` contains only
  target ids, paths, and booleans, not the target design's evidence object;
- the per-target parity artifacts are markdown summaries only;
- repo search shows no checked-in parity-target manifest or promotion command;
- the progress ledger for this drain remains empty, so no later recorded event
  supersedes the selector rationale.

This makes the slice feasible without a new runtime primitive. The missing
pieces are one manifest, one report library, one CLI command, and the tests
that prove they compute the gate from evidence instead of from hand-authored
status.

## Proposed Architecture

### 1. Add One Checked-In Parity-Target Manifest

Add a source-controlled manifest at:

`workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`

The manifest is the authoritative configuration for the bounded promotion
surface. It should include, per target family:

- `workflow_family`
- `candidate`
- `yaml_primary`
- `entry_workflow`
- extern-manifest paths when applicable
- baseline characterization:
  - `inputs`
  - `outputs`
  - `terminal_states`
  - `artifacts`
  - `resume_behavior`
- deprecated YAML mechanics with either:
  - a concrete replacement, or
  - an accepted-risk waiver with owner and expiry
- deterministic evidence commands grouped by role:
  - `compile`
  - `dry_run`
  - `smoke_or_integration`
  - parity assertions for:
    - `output_contract_parity`
    - `terminal_state_parity`
    - `artifact_parity`
    - `resume_parity`
- compile-artifact expectations, split into:
  - required artifacts
  - optional artifacts that may be recorded as `not_implemented`

Manifest commands should be stored as `argv` arrays, not shell strings, so the
promotion tool can execute them deterministically without `shell=True` or
string-splitting heuristics.

This keeps the promotion logic bounded:

- the manifest declares what evidence must exist;
- the promotion code executes and records it;
- the gate computation remains generic and deterministic.

### 2. Make JSON Reports Authoritative And Markdown/Index Derived

For each target family, the tool writes:

- authoritative JSON report:
  `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/<workflow_family>.json`
- derived markdown summary:
  `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/<workflow_family>.md`

The tool also writes a derived aggregate index:

- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`

Report schema requirements:

- include the target design's minimum fields:
  `workflow_family`, `candidate`, `yaml_primary`, `compiler_version`,
  `dsl_version`, `evidence`, `deprecated_yaml_mechanics`, `non_regressive`
- add bounded implementation metadata:
  - `schema_version`
  - `generated_at`
  - `generated_by`
  - `report_path`
  - `command_logs`
  - `accepted_differences`
- include optional compiler-artifact entries with explicit statuses such as
  `pass`, `fail`, or `not_implemented`

The markdown summary is a convenience projection only. It must be rendered from
the JSON report and must not carry any authority that is not already present in
the JSON.

The aggregate index remains a narrow summary surface. It should list:

- target id
- candidate/yaml paths
- authoritative JSON report path
- derived markdown path
- computed `non_regressive`
- computed `primary_surface`

`primary_surface` is derived:

- `orc` only when `non_regressive == true`
- otherwise `yaml`

This preserves the current index affordance while moving authority to the
per-target JSON reports.

### 3. Execute Deterministic Evidence Roles, Do Not Reimplement Semantics

The promotion tool should execute the manifest's evidence commands directly and
record their outcomes. It should not reconstruct workflow semantics from prose,
run-state fragments, or ad hoc filesystem guesses.

Execution model:

- each command runs as explicit `argv` with `shell=False`;
- stdout/stderr are captured to deterministic log files under the parity
  artifact root;
- exit code and elapsed time are recorded for every command;
- the compile command's JSON stdout is parsed when present so the report can
  record build artifact paths and statuses;
- evidence commands may be CLI invocations (`python -m orchestrator ...`) or
  focused `pytest` selectors when the parity obligation already lives in tests.

This is intentionally bounded. The tool does not need a new generic runtime
runner if the existing CLI or focused tests already provide the right evidence.

Role ownership:

- `compile`
  - proves build success and records compiler artifacts;
  - shared validation status is derived from compile success plus emitted build
    manifest status.
- `dry_run`
  - proves the current entrypoint validates and binds inputs without execution.
- `smoke_or_integration`
  - may be a real runtime smoke or a targeted integration command;
  - waivers are manifest-driven and must be validated for owner, expiry, and
    justification.
- parity assertions
  - stay explicit and deterministic;
  - current targets may satisfy them through focused pytest selectors rather
    than a new generic comparator.

This keeps the slice honest about current repo capabilities and satisfies the
design-spec feasibility trigger: no unproven generic parity engine is assumed.

### 4. Compute The Gate From Evidence Only

`non_regressive` is computed by code after all evidence has been normalized.

Computation rules in this slice must match the parent design:

- require `compile`, `shared_validation`, and `dry_run` to pass;
- require `smoke_or_integration` to pass, or require a valid waiver plus the
  targeted evidence declared by that waiver policy;
- require `baseline_characterization` to be present and complete;
- require the parity axes
  `output_contract_parity`,
  `terminal_state_parity`,
  `artifact_parity`, and
  `resume_parity`
  to pass;
- require every deprecated YAML mechanic to have either:
  - a replacement, or
  - an accepted-risk waiver with owner and unexpired expiry;
- require every required compile artifact to exist and every optional artifact
  to be explicitly classified as present or `not_implemented`.

Hard-failure rules:

- if the manifest or a generated report supplies `non_regressive` directly, the
  tool fails;
- if a required evidence role is missing, `non_regressive` becomes `false`;
- if a waiver is expired, ownerless, or unjustified, `non_regressive` becomes
  `false`;
- if a required artifact is absent or a parity assertion command fails,
  `non_regressive` becomes `false`.

The report should still be written for regressive targets. The point of the
tool is to make regression explicit and reproducible, not to write reports only
for passing candidates.

### 5. Refresh The Current Migrated Workflow Family Through One Command

The initial manifest owned by this slice should cover exactly the current
migrated family:

- `cycle_guard_demo`
- `design_plan_impl_stack`

Each target should record:

- the current `.orc` candidate path;
- the current YAML primary path;
- the deterministic compile and dry-run commands already used in the migration
  tranche;
- the smoke or targeted integration evidence appropriate for that target;
- the baseline characterization and currently accepted differences;
- the deprecated YAML mechanics and their replacements.

The promotion command should support:

- `--targets-file <path>`
- optional `--target <workflow_family>` filtering
- optional `--output-root <path>` override for artifact emission

Default artifact root for the checked migration family should remain:

`artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/`

This preserves the current evidence location while upgrading its contents from
historical markdown to authoritative JSON plus derived projections.

### 6. Keep Failure Surfaces Explicit

Promotion reporting must fail explicitly when the evidence surface is malformed.

Required diagnostics in this slice:

- manifest schema invalid
- duplicate `workflow_family`
- missing required command role
- invalid command `argv`
- attempted authored `non_regressive`
- invalid or expired waiver
- required compile artifact missing
- compile stdout not parseable as JSON when the compile role is declared
  machine-readable
- derived index generation attempted without per-target JSON reports

These are promotion-tool diagnostics, not runtime workflow semantics. They
should point at the manifest/report path and target id rather than at unrelated
workflow files.

## Proposed Code Footprint

- `orchestrator/workflow_lisp/migration_parity.py`
- `orchestrator/cli/commands/migration_parity.py`
- `orchestrator/cli/main.py`
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- `tests/test_workflow_lisp_migration_parity.py`
- `tests/test_workflow_lisp_cli.py`
- `tests/test_workflow_lisp_key_migrations.py`

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/build.py`
- `orchestrator/cli/commands/compile.py`
- `orchestrator/cli/commands/run.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/signatures.py`
- `orchestrator/workflow/executor.py`
- the earlier parity-gap implementations and their fixtures

## Acceptance Conditions

- a checked-in manifest defines the current migrated workflow family and the
  deterministic evidence commands for each target;
- the promotion command writes one authoritative JSON report per target plus
  derived markdown and aggregate index outputs;
- the JSON report includes the target design's required evidence fields and
  computes `non_regressive` in code;
- authored `non_regressive` values in inputs are rejected;
- required compile artifacts are recorded explicitly, while optional missing
  artifacts are reported as `not_implemented`;
- current migrated-family reports can be regenerated through the command even
  when the computed outcome remains regressive;
- `primary_surface` in the aggregate index is derived from the computed report
  rather than authored manually;
- no new workflow command adapters, report-parsing authority, pointer-as-state
  behavior, or hidden shell glue is introduced.

## Verification Strategy

Focused verification for this slice should cover:

- manifest parsing and duplicate-target rejection;
- report-schema validation and derived markdown/index rendering;
- `non_regressive` computation for:
  - all-pass evidence
  - missing required evidence
  - expired waiver
  - required artifact missing
  - optional artifact `not_implemented`
- CLI behavior for:
  - full target refresh
  - single-target filtering
  - attempted manual `non_regressive`
- refresh of the current migrated workflow family using the checked-in manifest
  and deterministic evidence commands;
- at least one end-to-end command invocation that regenerates the parity
  artifacts under `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/`.

The command should reuse the current migration tests for semantic evidence
rather than duplicating those assertions inside the report code.

## Summary

The bounded promotion-report gate should be implemented as one manifest-driven,
machine-readable evidence layer over the existing Workflow Lisp migration
compile/run/test substrate.

The authoritative surfaces after this slice are:

- one source-controlled target manifest;
- one per-target JSON promotion report;
- one computed `non_regressive` gate.

Markdown summaries and the aggregate index remain useful, but only as derived
views of the authoritative JSON reports.
