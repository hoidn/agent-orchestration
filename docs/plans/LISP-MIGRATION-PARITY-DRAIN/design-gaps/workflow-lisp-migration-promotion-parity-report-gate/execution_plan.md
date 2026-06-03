# Workflow Lisp Migration Promotion Parity Report Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the bounded machine-readable migration-parity reporting slice for the current Workflow Lisp migration families by checking in one authoritative target manifest, generating one authoritative JSON report per family plus derived markdown/index views, computing `non_regressive` from evidence only, and refreshing the current parity artifacts through one deterministic CLI/library command path.

**Architecture:** Keep promotion evidence manifest-driven and machine-readable. `orchestrator/workflow_lisp/migration_parity.py` owns target-manifest loading, deterministic command execution, compile-artifact extraction from existing Workflow Lisp build manifests, report normalization, `non_regressive` computation, and derived markdown/index rendering; `orchestrator/cli/commands/migration_parity.py` owns the thin CLI wrapper; `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json` owns the current migrated-family evidence commands and baseline characterization. Existing compile, dry-run, smoke, and migration tests remain the evidence substrate; this slice must not recreate workflow semantics, parse prose as authority, or introduce workflow command adapters.

**Tech Stack:** Python 3, existing `orchestrator` CLI commands, Workflow Lisp build manifests, JSON report rendering, `pytest`

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-migration-promotion-parity-report-gate/implementation_architecture.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/5/design-gap-architect/work_item_context.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `docs/steering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `workflows/README.md`
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/5/selector/selection.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/5/design-gap-architect/architecture-targets.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/5/design-gap-architect/existing-architecture-index.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/5/design-gap-architect/check_commands.json`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/cycle_guard_demo.md`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md`
- earlier parity-gap implementation architectures referenced by the selected implementation architecture

Current checkout facts that must not be rediscovered during implementation:

- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is empty, so no later ledger event supersedes this slice.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- There is currently no `migration-parity` CLI command, no `orchestrator/workflow_lisp/migration_parity.py` module, and no checked-in parity-target manifest.
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json` is a historical summary with markdown paths and authored-looking booleans, not a machine-checked promotion record.
- The current per-target parity artifacts are markdown only; there is no authoritative JSON report per target.
- `orchestrator/cli/commands/compile.py` already prints structured JSON including `build_root` and `artifact_paths`; the parity tool should reuse that output and the existing Workflow Lisp build manifest under the emitted build root instead of inventing a second compile-artifact catalog.
- `tests/test_workflow_lisp_key_migrations.py` already contains the current semantic evidence selectors for:
  - `cycle_guard_demo_orc_runtime_materializes_output_bundle`
  - `review_loop_parity_fixture`
  - `resume_or_start_plan_gate_reusable_state_parity_path`
- `cycle_guard_demo` remains a bounded command-result bridge target in this slice, not a promotable high-level YAML replacement; unless a later accepted design adds native bounded-loop parity, this plan must keep that family ineligible for `primary_surface: "orc"` even if its bounded evidence all passes.
- `workflows/README.md` already keeps YAML primary unless `.orc` parity evidence exists; this slice must not auto-promote catalog status.

## Hard Scope Limits

Implement only this bounded slice:

- add one checked-in parity-target manifest for the current migrated Workflow Lisp families;
- add one authoritative per-target JSON report schema plus derived markdown and aggregate index rendering;
- add one deterministic library and CLI path that executes manifest-declared evidence commands with `shell=False`;
- keep manifest-declared dry-run/run evidence on the public entrypoint contract only; authoritative manifest/report surfaces must not require or publish compiler-owned hidden managed write-root bindings such as `__write_root__...`;
- compute `non_regressive` from normalized evidence only and reject authored overrides;
- record required compile artifacts explicitly and optional artifacts as `not_implemented` when absent;
- regenerate the current parity artifacts for `cycle_guard_demo` and `design_plan_impl_stack` via the new command.
- keep `cycle_guard_demo` in the manifest and refreshed reports as bridge evidence only; do not let this slice present it as a promotable `.orc` primary over YAML.

Explicit non-goals:

- do not reopen command-result semantics, review-loop semantics, findings transport, workflow input defaults, reusable-state validation, or YAML deprecation policy;
- do not add new workflow command adapters, inline shell glue, pointer-as-state compatibility, report parsing authority, or a generic workflow semantic diff engine;
- do not change `workflows/README.md` catalog status labels automatically;
- do not replace compile/dry-run/test evidence with custom in-process semantic reimplementation;
- do not widen the manifest beyond the current migrated family.

## File Ownership

Create:

- `orchestrator/workflow_lisp/migration_parity.py`
- `orchestrator/cli/commands/migration_parity.py`
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- `tests/test_workflow_lisp_migration_parity.py`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/cycle_guard_demo.json`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`

Modify:

- `orchestrator/cli/main.py`
- `orchestrator/cli/commands/__init__.py`
- `tests/test_workflow_lisp_cli.py`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/cycle_guard_demo.md`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`

Inspect only if a focused failing test proves the need:

- `tests/test_workflow_lisp_key_migrations.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/cli/commands/compile.py`

Do not modify unless verification proves this plan is incomplete:

- workflow runtime/executor modules
- `workflows/README.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`
- unrelated Workflow Lisp compiler/lowering/runtime slices

## Required Data Contracts

Implement these contract decisions exactly so execution does not need to redesign the slice:

### Parity Target Manifest

Path:

- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`

Schema requirements:

- root `schema_version` is `workflow_lisp_migration_parity_targets.v1`
- root contains `targets`, an array of target records
- each target record contains:
  - `workflow_family`
  - `candidate`
  - `yaml_primary`
  - `entry_workflow`
  - optional extern-manifest paths:
    - `provider_externs_file`
    - `prompt_externs_file`
    - `command_boundaries_file`
    - `imported_workflow_bundles_file`
  - `baseline_characterization`
    - `inputs`
    - `outputs`
    - `terminal_states`
    - `artifacts`
    - `resume_behavior`
  - `accepted_differences`
  - `deprecated_yaml_mechanics`
  - `promotion_eligibility`
    - `eligible_for_primary_surface`
    - optional `blocked_reason`
  - `compile_artifacts`
    - `required`
    - `optional`
  - `evidence_commands`
    - `compile`
    - `dry_run`
    - `smoke_or_integration`
    - `output_contract_parity`
    - `terminal_state_parity`
    - `artifact_parity`
    - `resume_parity`

Command rules:

- every command is stored as an `argv` array, never a shell string
- manifest-declared dry-run, smoke, or integration commands must use only public entrypoint inputs; reject any `--input` assignment targeting compiler-owned hidden managed write-root names such as `__write_root__...`
- `smoke_or_integration` may carry waiver metadata, but `non_regressive` may not appear anywhere in the manifest
- duplicate `workflow_family` values are invalid
- if `promotion_eligibility.eligible_for_primary_surface == false`, `blocked_reason` is required
- the checked-in `cycle_guard_demo` target must set `eligible_for_primary_surface: false` with a reason that records it is demo-only until native bounded-loop parity is intentionally designed later

### Per-Target JSON Report

Path pattern:

- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/<workflow_family>.json`

Schema requirements:

- `schema_version` is `workflow_lisp_migration_parity_report.v1`
- include:
  - `workflow_family`
  - `candidate`
  - `yaml_primary`
  - `compiler_version`
  - `dsl_version`
  - `generated_at`
  - `generated_by`
  - `report_path`
  - `command_logs`
  - `accepted_differences`
  - `deprecated_yaml_mechanics`
  - `promotion_eligibility`
  - `compile_artifacts`
  - `evidence`
  - `non_regressive`
- `evidence` contains normalized records for:
  - `compile`
  - `shared_validation`
  - `dry_run`
  - `smoke_or_integration`
  - `baseline_characterization`
  - `output_contract_parity`
  - `terminal_state_parity`
  - `artifact_parity`
  - `resume_parity`

Compile-artifact rules:

- required artifact names must come from the existing Workflow Lisp build manifest and be enforced explicitly
- optional artifact names absent from the build manifest must be recorded as `not_implemented`
- do not invent a second artifact inventory outside `build.py` manifest/status data

Authoritative-surface rule:

- JSON reports, derived markdown, and aggregate index entries must not publish compiler-owned hidden managed write-root bindings as part of the supported entrypoint contract; if a historical source artifact contains them, the new manifest/report path must reject them at load time instead of carrying them forward

### Derived Views

Paths:

- markdown summary: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/<workflow_family>.md`
- aggregate index: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`
- command logs: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/logs/<workflow_family>/<role>.stdout.log` and `.stderr.log`

Derived index rules:

- root `schema_version` is `workflow_lisp_migration_parity_index.v1`
- each target row contains:
  - `workflow_family`
  - `candidate`
  - `yaml_primary`
  - `json_report`
  - `markdown_report`
  - `non_regressive`
  - `promotion_eligibility`
  - `primary_surface`
- `primary_surface` is computed:
  - `orc` only when `non_regressive == true` and `promotion_eligibility.eligible_for_primary_surface == true`
  - otherwise `yaml`

### Gate Computation

`non_regressive` is computed in code and is `true` only when all of the following are satisfied:

- `compile.status == "pass"`
- `shared_validation.status == "pass"`
- `dry_run.status == "pass"`
- `smoke_or_integration` either passed or has a valid waiver with owner, expiry, justification, and targeted evidence covering the skipped runtime behavior
- baseline characterization contains non-empty values for inputs, outputs, terminal states, artifacts, and resume behavior
- `output_contract_parity`, `terminal_state_parity`, `artifact_parity`, and `resume_parity` all pass
- every deprecated YAML mechanic has either a concrete replacement or an accepted waiver record
- every required compile artifact is present and passing

Force `non_regressive = false` when any of the following occurs:

- manifest or report input attempts to author `non_regressive`
- a required evidence role is missing
- a waiver is expired, ownerless, or unjustified
- a required compile artifact is missing or `not_implemented`
- report rendering succeeded but any evidence command failed

The command should still write reports for regressive targets. Regressive evidence is expected output, not a command-construction failure.

### Promotion Eligibility Rule

`non_regressive` remains evidence-computed only. Promotion eligibility is a
separate manifest-declared constraint that prevents this slice from presenting
known non-primary demo targets as YAML replacements.

- if `promotion_eligibility.eligible_for_primary_surface == false`, derived
  `primary_surface` must remain `yaml` even when every bounded evidence role
  passes
- for the current bounded manifest, `cycle_guard_demo` must stay ineligible and
  keep YAML primary until a later accepted design intentionally adds native
  bounded-loop parity
- `design_plan_impl_stack` remains eligible to become `orc` only when its
  computed evidence is non-regressive

## Task Checklist

### Task 1: Lock The Report Contract And CLI Surface With Failing Tests

**Files:**

- Create: `tests/test_workflow_lisp_migration_parity.py`
- Modify: `tests/test_workflow_lisp_cli.py`

- [ ] Add manifest-loader tests that reject duplicate `workflow_family`, shell-string commands, missing baseline fields, authored `non_regressive`, and any manifest command argv that exposes compiler-owned hidden managed write-root inputs such as `__write_root__...`.
- [ ] Add report-computation tests that cover:
  - all-pass evidence
  - missing required evidence
  - expired smoke waiver
  - missing required compile artifact
  - optional compile artifact recorded as `not_implemented`
- [ ] Add derived-view tests proving markdown and index render strictly from report data, compute `primary_surface` from `non_regressive` plus `promotion_eligibility`, and keep ineligible targets on YAML.
- [ ] Add CLI parser/dispatch tests for `migration-parity`, including:
  - `--targets-file`
  - `--output-root`
  - optional repeatable `--target`
- [ ] Add a CLI behavior test proving the command rejects manifest-authored `non_regressive` before running any evidence commands.
- [ ] Add a manifest/derived-view test proving `cycle_guard_demo` cannot produce `primary_surface: "orc"` under the current bounded manifest contract.
- [ ] Add a manifest/report test proving authoritative JSON/markdown/index outputs do not publish compiler-owned hidden managed write-root bindings even when historical markdown evidence previously mentioned them.
- [ ] Keep the evidence model bounded: no tests should assert literal markdown prose beyond stable headings/keys.

Suggested test names:

- `test_load_parity_targets_rejects_authored_non_regressive`
- `test_load_parity_targets_rejects_duplicate_workflow_family`
- `test_compute_non_regressive_requires_all_required_evidence`
- `test_compute_non_regressive_allows_optional_artifact_not_implemented`
- `test_render_parity_index_derives_primary_surface`
- `test_render_parity_index_keeps_yaml_for_ineligible_target`
- `test_load_parity_targets_rejects_hidden_managed_write_root_input`
- `test_rendered_parity_surfaces_do_not_publish_hidden_managed_write_root_inputs`
- `test_parser_supports_migration_parity_subcommand`
- `test_migration_parity_cli_rejects_manifest_override`

**Blocking verification after Task 1:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_cli.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_migration_parity.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_cli.py -k "migration_parity or parity_report" -q`

Expected before implementation: these tests fail because no parity-report module or CLI surface exists yet.

### Task 2: Implement Manifest Loading, Evidence Execution, And Report Computation

**Files:**

- Create: `orchestrator/workflow_lisp/migration_parity.py`
- Create: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Modify if needed: `tests/test_workflow_lisp_migration_parity.py`

- [ ] Add typed manifest/report helpers in `migration_parity.py`. Use dataclasses or equivalent explicit structures for target config, command outcome, compile artifact status, evidence record, and rendered report payload.
- [ ] Implement manifest loading and validation against the fixed contract above. Reject:
  - duplicate targets
  - authored `non_regressive`
  - shell-string commands
  - manifest command argv that expose compiler-owned hidden managed write-root inputs such as `__write_root__...`
  - malformed or incomplete waiver metadata
- [ ] Implement deterministic command execution with `subprocess.run(..., shell=False, cwd=repo_root)` and captured stdout/stderr written to the deterministic log paths under the parity output root.
- [ ] For the `compile` role, parse the existing `python -m orchestrator compile ...` JSON stdout, derive the build manifest path from `build_root`, and read compile artifact paths/status from the existing Workflow Lisp build manifest.
- [ ] Derive `shared_validation` from compile success plus the build manifest's shared-validation status instead of rerunning validation through a second path.
- [ ] Normalize all evidence roles into one report payload, including command argv, exit code, elapsed seconds, log paths, and pass/fail/not_implemented status.
- [ ] Implement `non_regressive` computation exactly from normalized evidence.
- [ ] Render derived markdown and aggregate index from the authoritative JSON payload only.
- [ ] Check in `parity_targets.json` covering exactly:
  - `cycle_guard_demo`
  - `design_plan_impl_stack`
- [ ] Populate the manifest with:
  - compile and dry-run CLI commands for both families
  - targeted smoke or integration evidence for the family where it is safe
  - focused `pytest` selectors for parity axes already encoded in tests
  - baseline characterization and deprecated YAML mechanics carried from the current migration docs/artifacts
- [ ] Encode only public entrypoint inputs in manifest-declared run/dry-run commands. Historical markdown may mention hidden managed write-root bindings, but the new authoritative manifest must not preserve or reproduce them.
- [ ] Mark `cycle_guard_demo` as promotion-ineligible in the manifest with an explicit bounded-loop parity blocker so its refreshed report can stay useful evidence without becoming a false `.orc` primary.
- [ ] Keep commands as `argv` arrays matching repo-root execution. Do not store shell quoting.
- [ ] Keep rendered JSON/markdown/index views free of compiler-owned hidden managed write-root bindings so the authoritative parity surface does not restate a forbidden public API.

Recommended helper surface:

```python
def load_parity_targets(path: Path) -> list[ParityTarget]: ...
def run_parity_target(target: ParityTarget, *, output_root: Path, repo_root: Path) -> ParityReport: ...
def compute_non_regressive(report: ParityReport, *, today: date) -> bool: ...
def render_parity_markdown(report: ParityReport) -> str: ...
def render_parity_index(reports: Sequence[ParityReport]) -> dict[str, object]: ...
```

Implementation guardrails:

- do not call workflow internals to infer semantic parity from run state or markdown
- do not duplicate the Workflow Lisp build-artifact catalog
- do not let a failed evidence command abort the whole refresh before writing the target report unless the failure is manifest-validation or file-write infrastructure
- do not use current wall-clock wording like “today” inside reports; write ISO timestamps

**Blocking verification after Task 2:**

- [ ] `python -m pytest tests/test_workflow_lisp_migration_parity.py -q`

Expected after Task 2: manifest parsing, evidence normalization, artifact-status extraction, report rendering, and gate computation all pass in isolation.
CLI parser/dispatch and command-behavior coverage remain expected red until Task 3 adds `orchestrator/cli/commands/migration_parity.py` and wires the `migration-parity` subcommand into the existing CLI surface.

### Task 3: Add The CLI Command And Wire It Into The Existing CLI Surface

**Files:**

- Create: `orchestrator/cli/commands/migration_parity.py`
- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/__init__.py`
- Modify: `tests/test_workflow_lisp_cli.py`

- [ ] Add a `migration-parity` subcommand to `create_parser()` with:
  - `--targets-file` required
  - `--output-root` required
  - `--target` repeatable optional filter
- [ ] Implement a thin command wrapper that:
  - loads the manifest
  - filters by `--target` when provided
  - runs the selected targets in deterministic manifest order
  - writes per-target JSON + markdown + aggregate index
  - returns success when report generation completes, even if one or more targets remain regressive
- [ ] Reserve nonzero exit codes for invalid CLI usage, manifest validation failures, or write/parse infrastructure failures.
- [ ] Print one compact JSON summary to stdout containing:
  - `targets_processed`
  - `reports_written`
  - `non_regressive_targets`
  - `regressive_targets`
  - `index_path`
- [ ] Keep the implementation thin. All report logic stays in `orchestrator/workflow_lisp/migration_parity.py`.

**Blocking verification after Task 3:**

- [ ] `python -m pytest tests/test_workflow_lisp_cli.py -k "migration_parity or parity_report" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_migration_parity.py -q`

Expected after Task 3: the CLI parser, dispatch, summary output, target filtering, and manifest-error handling all work without changing any runtime workflow semantics.

### Task 4: Refresh The Checked-In Parity Artifacts And Prove The Bounded Slice End To End

**Files:**

- Modify via generated output:
  - `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/cycle_guard_demo.json`
  - `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/cycle_guard_demo.md`
  - `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
  - `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md`
  - `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`

- [ ] Run the new command against the checked-in manifest and output root so the current migrated-family reports are regenerated through the same path future refreshes will use.
- [ ] Inspect the JSON reports to confirm:
  - `non_regressive` is present and computed
  - required evidence roles are recorded
  - required compile artifacts are explicit
  - optional compile artifacts are present as `not_implemented` where appropriate
  - `cycle_guard_demo` carries explicit promotion ineligibility metadata
  - no command argv or supported-input surface publishes compiler-owned hidden managed write-root bindings such as `__write_root__...`
  - deprecated YAML mechanics are carried as data, not prose-only commentary
- [ ] Inspect the derived markdown and index to confirm they reflect the JSON reports, keep YAML as primary when targets remain regressive, and keep `cycle_guard_demo` on YAML even if its bounded bridge evidence passes.
- [ ] Grep the regenerated authoritative parity surface for `__write_root__` and treat any hit in the checked-in manifest/JSON/index/markdown outputs as a blocker.
- [ ] Do not hand-edit the parity artifacts after generation; if output is wrong, fix the library/manifest and rerun the command.

**Required finish-gate verification:**

- [ ] Run the exact recorded collect-only command:
  - `python -m pytest --collect-only tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_cli.py tests/test_workflow_lisp_key_migrations.py -q`
- [ ] Run the exact recorded parity unit suite:
  - `python -m pytest tests/test_workflow_lisp_migration_parity.py -q`
- [ ] Run the exact recorded CLI coverage:
  - `python -m pytest tests/test_workflow_lisp_cli.py -k "migration_parity or parity_report" -q`
- [ ] Run the focused hidden-input regression coverage:
  - `python -m pytest tests/test_workflow_lisp_migration_parity.py -k "hidden_managed_write_root or write_root" -q`
- [ ] Run the exact recorded migration evidence reuse:
  - `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "cycle_guard_demo_orc_runtime_materializes_output_bundle or review_loop_parity_fixture or resume_or_start_plan_gate_reusable_state_parity_path" -q`
- [ ] Run the exact recorded end-to-end artifact refresh:
  - `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity`
- [ ] Run the authoritative-surface leakage check:
  - `rg "__write_root__" workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/*.json artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/*.md artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`

Expected finish state:

- the repo contains one checked-in parity-target manifest for the two current families
- the repo contains authoritative JSON reports plus derived markdown/index outputs
- authored `non_regressive` values are rejected
- `cycle_guard_demo` remains recorded as bridge evidence but cannot appear as `primary_surface: "orc"` in this tranche
- refreshed reports may still be regressive, but they are deterministic, machine-checked, and reproducible from the manifest-driven command

## Completion Notes For The Implementer

- Record in the implementation summary which files changed and paste the fresh command results for every required finish-gate command.
- If one of the current families remains regressive, treat that as expected evidence unless the new report disagrees with existing migration facts.
- If a required parity axis cannot be represented by the current checked-in test selectors, stop and tighten the bounded migration tests first; do not paper over the gap with prose in the report.
