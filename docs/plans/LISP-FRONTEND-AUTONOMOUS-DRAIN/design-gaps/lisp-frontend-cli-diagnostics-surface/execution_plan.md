# Lisp Frontend CLI Diagnostics Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded Workflow Lisp `.orc` compile/run/explain surface so compiled frontend workflows can be built, inspected, and executed through the existing runtime with deterministic artifacts, machine-readable diagnostics, explicit imported-bundle manifests, persisted source-trace metadata, and runtime provenance.

**Architecture:** Add a frontend-owned build/artifact layer around the existing `compile_stage3_entrypoint(...)` pipeline instead of building a second compiler or executor. Keep YAML behavior unchanged, route only `.orc` entrypoints through explicit manifest-driven compile request normalization, serialize the frontend surfaces the repo already owns today, and attach compiled provenance to `LoadedWorkflowBundle` / runtime observability without redefining shared workflow semantics.

**Tech Stack:** Python 3, `argparse`, `dataclasses`, `json`, `hashlib`, `pathlib.Path`, the existing `orchestrator.workflow_lisp` compiler/lowering/diagnostics modules, `LoadedWorkflowBundle`, runtime observability helpers, pytest, and deterministic `.orc` fixture manifests under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these as implementation authority for this slice:

- `docs/index.md`
- `docs/steering.md`
  - currently empty in this checkout; do not treat that as permission to widen scope
- `docs/design/workflow_lisp_frontend_specification.md`
  - `75. Runtime Observability`
  - `76. Build Artifacts`
  - `76.1 Editor And Lint Tooling Compatibility`
  - `77. Compile`
  - `78. Run`
  - `79. Explain Expansion`
  - `80. Emit Debug YAML`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_lisp_debug_yaml_renderer.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/8/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/8/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/8/selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/8/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
  - currently `{"ledger_version":1,"events":[]}`; there is no prior execution history to reconcile for this gap

## Hard Scope Limits

Implement only the selected CLI/diagnostics slice:

- `orchestrate compile` for `.orc` entrypoints
- `.orc` dispatch in `orchestrate run`
- `orchestrate explain` over implemented frontend surfaces
- explicit and inferred entry-workflow selection
- explicit imported-workflow-bundle manifest inputs for compile/run/explain
- deterministic build-root fingerprints, manifests, and emitted artifacts
- machine-readable diagnostic serialization
- persisted source-trace sidecars built from existing lowering provenance
- runtime provenance transport into observability and persisted run metadata
- optional non-authoritative debug-YAML projection

Explicit non-goals:

- no new frontend language semantics, macros, stdlib forms, parser grammar, or type-system redesign
- no second validator, no YAML-as-authority path, and no second executor
- no redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog, pointer authority, variant proof, queue behavior, or runtime state
- no LSP/editor implementation, compile daemon, or background cache server
- no hidden shell/Python glue, report parsing, or adapter-policy bypasses
- no change to existing YAML CLI behavior except additive `.orc` routing

## Current Baseline

The implementation must extend the repo as it exists now:

- `orchestrator/cli/main.py` only exposes `run`, `resume`, `report`, `dashboard`, and `monitor`.
- `orchestrator/cli/commands/` has no `compile.py` or `explain.py`.
- `orchestrator/cli/commands/run.py` assumes YAML loading and execution only.
- `orchestrator/workflow_lisp/compiler.py` already exposes:
  - `compile_stage1_entrypoint(...)`
  - `compile_stage3_entrypoint(...)`
  - `compile_stage1_module(...)`
  - `compile_stage3_module(...)`
- `compile_stage3_entrypoint(...)` already accepts `imported_workflow_bundles`, so the CLI must preserve an explicit imported-bundle surface instead of inventing ambient resolution.
- `orchestrator/workflow_lisp/diagnostics.py` only renders text diagnostics today.
- `orchestrator/workflow_lisp/` has no build/artifact service or debug-YAML renderer module yet.
- `orchestrator/workflow/surface_ast.py` and `orchestrator/workflow/loaded_bundle.py` already carry provenance, but not the compiled-frontend transport fields required by this slice.
- `tests/test_workflow_lisp_cli.py` and `tests/test_workflow_lisp_build_artifacts.py` do not exist yet.
- `tests/fixtures/workflow_lisp/cli/` does not exist yet.

## File Ownership

Create:

- `orchestrator/cli/commands/compile.py`
- `orchestrator/cli/commands/explain.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/debug_yaml.py`
- `tests/test_workflow_lisp_cli.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- fixture manifests under `tests/fixtures/workflow_lisp/cli/`

Modify:

- `orchestrator/cli/main.py`
- `orchestrator/cli/commands/__init__.py`
- `orchestrator/cli/commands/run.py`
- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/executor.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_runtime_observability_cli.py`

Reuse without broadening ownership:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/modules.py`
- shared runtime/validation modules under `orchestrator/workflow/`, except the narrow provenance/log-display bridge listed above

## Locked Contracts

Do not re-decide these during implementation.

Compile request and entry selection:

- introduce frontend-local request/manifest records instead of passing raw CLI flags through handlers
- require explicit imported-bundle manifests for compile/run/explain when imported YAML or compiled bundles are needed
- infer the entry workflow only when the entry module exports exactly one runnable workflow
- otherwise require `--entry-workflow` and emit a frontend/CLI diagnostic instead of guessing

Build root and fingerprint:

```text
.orchestrate/build/<fingerprint>/
```

`<fingerprint>` must include:

- transitive `.orc` source contents
- resolved source roots
- selected entry workflow
- provider extern manifest contents
- prompt extern manifest contents
- imported-workflow-bundle manifest contents and resolved bundle provenance/fingerprints
- command-boundary manifest contents
- build schema version

Mandatory successful-build artifacts:

- `manifest.json`
- `frontend_ast.json`
- `expanded_frontend_ast.json`
- `typed_frontend_ast.json`
- `lowered_workflows.json`
- `executable_ir.json`
- `source_map.json`
- `diagnostics.json`

Optional artifact:

- `expanded.debug.yaml`

Deferred-but-manifested artifacts:

- `core_workflow_ast`
- `semantic_ir`

Required artifact-status behavior:

```json
{
  "core_workflow_ast": "deferred_shared_contract",
  "semantic_ir": "deferred_shared_contract"
}
```

Runtime provenance bridge fields:

- `frontend_kind: "workflow_lisp"`
- `frontend_build_root`
- `frontend_source_trace_path`
- `frontend_entry_workflow`

Debug-YAML rules:

- render only after shared validation succeeds
- derive from validated `LoadedWorkflowBundle.surface` plus persisted source trace
- mark output as non-authoritative
- never use the debug YAML as run input or imported dependency input

## Task 1: Lock Fixtures And Failing Tests For The CLI/Artifact Slice

**Files:**

- Create: `tests/test_workflow_lisp_cli.py`
- Create: `tests/test_workflow_lisp_build_artifacts.py`
- Create: `tests/fixtures/workflow_lisp/cli/providers.json`
- Create: `tests/fixtures/workflow_lisp/cli/prompts.json`
- Create: `tests/fixtures/workflow_lisp/cli/commands.json`
- Create: `tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json`
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify: `tests/test_runtime_observability_cli.py`

- [ ] **Step 1: Add deterministic extern and imported-bundle fixture manifests**

Create fixture manifests that exercise the exact CLI surfaces from the work-item context:

- provider externs for the `imported_bundle_mix` module graph
- prompt externs for the same graph
- command-boundary declarations
- imported workflow bundle manifest mixing migration-era YAML bundles and compiled bundle-compatible keys on the existing `imported_workflow_bundles` seam

- [ ] **Step 2: Add failing tests for parser wiring, build artifacts, and diagnostics**

In `tests/test_workflow_lisp_cli.py`, add focused tests for:

- `compile` and `explain` subparser registration
- `.orc` dispatch in `run`
- explicit versus inferred entry-workflow selection
- missing `--entry-workflow` diagnostics when a module exports multiple workflows
- imported-bundle manifest loading and missing-entry failure paths
- `.orc` `--dry-run` semantics

In `tests/test_workflow_lisp_build_artifacts.py`, add failing tests for:

- fingerprint stability across identical inputs
- fingerprint changes when the imported-bundle manifest changes
- required artifact presence
- deferred `core_workflow_ast` / `semantic_ir` status entries
- source-trace coverage for lowered step ids and generated input/output/path surfaces

Extend existing suites for:

- JSON diagnostic serialization in `tests/test_workflow_lisp_diagnostics.py`
- compiled-run provenance and authored-source observability in `tests/test_runtime_observability_cli.py`

- [ ] **Step 3: Run collect-only before implementation**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_cli.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_diagnostics.py tests/test_runtime_observability_cli.py -q
```

Expected:

- collection succeeds
- the new test modules appear
- implementation tests fail after collection because the CLI/build surface does not exist yet

- [ ] **Step 4: Commit the failing tests and fixture manifests**

```bash
git add tests/test_workflow_lisp_cli.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_diagnostics.py tests/test_runtime_observability_cli.py tests/fixtures/workflow_lisp/cli
git commit -m "test: pin workflow lisp cli artifact surface"
```

## Task 2: Build The Frontend Artifact Service And Diagnostic Serialization

**Files:**

- Create: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Introduce the build request, manifest, and source-trace dataclasses**

Add frontend-local records in `build.py` for at least:

- `FrontendBuildRequest`
- `FrontendEntrySelection`
- `ImportedWorkflowBundleBinding`
- `FrontendBuildManifest`
- `FrontendSourceTrace`
- one build result record that returns:
  - build root
  - manifest path
  - selected workflow name
  - selected validated bundle
  - emitted diagnostics
  - emitted artifact paths

These records own CLI/build normalization only; they do not replace compiler result dataclasses.

- [ ] **Step 2: Implement deterministic manifest loading and fingerprinting**

The build layer must:

1. load provider/prompt/command-boundary/imported-bundle manifest files explicitly
2. resolve imported workflow bundle paths into `LoadedWorkflowBundle` values
3. compute a stable fingerprint from the locked inputs
4. create `.orchestrate/build/<fingerprint>/`
5. refuse to guess imported bundles from source text or workspace scans

- [ ] **Step 3: Serialize the frontend surfaces the repo already owns**

Write serializers for:

- syntax/front-end module view into `frontend_ast.json`
- expanded syntax into `expanded_frontend_ast.json`
- typed workflows/procedures/module summary into `typed_frontend_ast.json`
- lowered authored mappings and generated ids into `lowered_workflows.json`
- selected validated executable bundle / IR view into `executable_ir.json`
- lowering-origin coverage into `source_map.json`
- all diagnostics into `diagnostics.json`

Do not fabricate `core_workflow_ast.json` or `semantic_ir.json`; record them only in `artifact_status`.

- [ ] **Step 4: Add machine-readable diagnostic envelopes without replacing text rendering**

Extend `diagnostics.py` with stable serialization helpers that preserve:

- diagnostic code
- severity
- path / line / column
- form path
- expansion stack
- notes
- phase

Keep `render_diagnostic(...)` and `render_diagnostics(...)` unchanged for human output.

- [ ] **Step 5: Derive source-trace sidecars from the implemented lowering provenance**

Use `LoweringOriginMap` and existing lowered workflow structures to emit trace coverage for:

- each lowered workflow origin
- each generated step id
- each generated input surface
- each generated output surface
- each generated path surface

If the current lowering code does not expose enough structured provenance for one of those categories, add the minimum targeted data plumbing in `lowering.py` instead of inventing new semantics.

- [ ] **Step 6: Run focused artifact and diagnostic tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_diagnostics.py -q
```

Expected:

- artifact manifest, fingerprint, deferred-status, and trace-coverage tests pass
- diagnostic JSON serialization tests pass
- CLI command tests still fail until command wiring is added

- [ ] **Step 7: Commit the build/artifact layer**

```bash
git add orchestrator/workflow_lisp/build.py orchestrator/workflow_lisp/__init__.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/diagnostics.py orchestrator/workflow_lisp/lowering.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_diagnostics.py
git commit -m "feat: add workflow lisp build artifacts and diagnostics"
```

## Task 3: Wire `compile` And `.orc`-Aware `run` Through The Existing Runtime

**Files:**

- Create: `orchestrator/cli/commands/compile.py`
- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/__init__.py`
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `tests/test_workflow_lisp_cli.py`

- [ ] **Step 1: Add parser support for `compile` and `.orc`-specific run flags**

In `main.py`, add:

- `compile` subcommand
- `.orc`-only flags on `run`:
  - `--entry-workflow`
  - `--source-root` (repeatable only if needed by the existing compiler API; otherwise keep it singular and normalize to a tuple)
  - `--provider-externs-file`
  - `--prompt-externs-file`
  - `--imported-workflow-bundles-file`
  - `--command-boundaries-file`
  - `--emit-debug-yaml` only on `compile`

Keep YAML help text and behavior unchanged.

- [ ] **Step 2: Implement `orchestrate compile` as a thin wrapper over the build service**

`orchestrator/cli/commands/compile.py` should:

- reject non-`.orc` inputs with a CLI-request diagnostic
- normalize CLI flags into `FrontendBuildRequest`
- invoke the build service with shared validation on
- print a stable summary containing:
  - fingerprint
  - entry workflow
  - build root
  - imported bundle keys
  - emitted artifact paths
  - diagnostic count

- [ ] **Step 3: Route `.orc` `run` through compile -> validate -> existing executor**

In `run.py`:

- keep the existing YAML path exactly as-is
- branch only when the workflow path ends in `.orc`
- compile through the new build service
- select the validated `LoadedWorkflowBundle`
- preserve existing context/input parsing, linting, and observability config
- execute through the existing runtime executor and session plumbing

`.orc` `--dry-run` must:

- compile
- shared-validate
- lint the validated bundle
- emit artifacts and diagnostics
- skip run-directory creation and provider/command execution

- [ ] **Step 4: Run CLI wiring tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_cli.py tests/test_workflow_lisp_build_artifacts.py -q
```

Expected:

- compile command tests pass
- `.orc` `run --dry-run` tests pass
- entry-workflow selection behavior matches the locked contract
- explain and observability-specific tests may still fail until later tasks land

- [ ] **Step 5: Commit the compile/run wiring**

```bash
git add orchestrator/cli/main.py orchestrator/cli/commands/__init__.py orchestrator/cli/commands/compile.py orchestrator/cli/commands/run.py orchestrator/workflow_lisp/build.py tests/test_workflow_lisp_cli.py tests/test_workflow_lisp_build_artifacts.py
git commit -m "feat: add workflow lisp compile and run cli wiring"
```

## Task 4: Implement `explain` Over The Persisted Frontend Surfaces

**Files:**

- Create: `orchestrator/cli/commands/explain.py`
- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/__init__.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `tests/test_workflow_lisp_cli.py`

- [ ] **Step 1: Define explain lookup rules around the existing build outputs**

`orchestrate explain` must be able to:

- compile from `.orc` inputs when no matching build is already loaded in-process
- select an authored form via `--form`
- report only the implemented surfaces that exist today

Do not imply that `core_workflow_ast` or `semantic_ir` exist. When the manifest marks them deferred, the explain output must say so explicitly.

- [ ] **Step 2: Render explain output from typed callables, lowered ids, executable ids, and source traces**

Implement output sections for:

- expansion frames touching the selected form
- typed workflow/procedure summary
- generated lowered workflow ids and step ids
- executable node ids mapped from the selected lowered steps when available
- source-trace entries with span, form path, and notes

If the selected form names an imported workflow call target, show the canonical imported key and resolved loaded-bundle provenance rather than rediscovering it from source text.

- [ ] **Step 3: Keep explain transport explicit and deterministic**

The command must accept the same compile manifest inputs as `compile` / `.orc` `run`:

- `--entry-workflow`
- `--source-root`
- `--provider-externs-file`
- `--prompt-externs-file`
- `--imported-workflow-bundles-file`
- `--command-boundaries-file`

Explain must never reach into ambient workspace state to guess missing imported bundles.

- [ ] **Step 4: Run explain and CLI tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_cli.py tests/test_workflow_lisp_diagnostics.py -q
```

Expected:

- explain output tests pass
- CLI diagnostics for missing form / missing entry-workflow / missing manifest inputs stay stable
- runtime observability tests may still fail until provenance transport is added

- [ ] **Step 5: Commit the explain command**

```bash
git add orchestrator/cli/main.py orchestrator/cli/commands/__init__.py orchestrator/cli/commands/explain.py orchestrator/workflow_lisp/build.py tests/test_workflow_lisp_cli.py tests/test_workflow_lisp_diagnostics.py
git commit -m "feat: add workflow lisp explain command"
```

## Task 5: Bridge Compiled Provenance Into Runtime Observability And Optional Debug YAML

**Files:**

- Create: `orchestrator/workflow_lisp/debug_yaml.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/loaded_bundle.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_runtime_observability_cli.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Extend provenance records with optional compiled-frontend metadata**

Add the narrow transport fields required by the architecture:

- `frontend_kind`
- `frontend_build_root`
- `frontend_source_trace_path`
- `frontend_entry_workflow`

Keep them optional so YAML-loaded bundles remain unaffected.

- [ ] **Step 2: Attach compiled provenance to the selected loaded bundle at build time**

When the build service selects the entry workflow bundle, persist:

- the deterministic build root
- the trace-artifact path
- the selected entry workflow

Do this by extending the existing provenance flow, not by mutating runtime state schemas ad hoc inside CLI handlers.

- [ ] **Step 3: Add runtime log/display support for source-aware compiled steps**

Update the narrow runtime observability path so compiled runs can display:

```text
Running step %run_selected_item.resume_plan
  source: tests/fixtures/workflow_lisp/.../entry.orc:42:5
  form: workflow-lisp > defworkflow > run-selected-item > resume-or-start
```

If a trace entry is missing, execution must continue and fall back to the generated step id only.

- [ ] **Step 4: Implement optional debug-YAML projection**

`debug_yaml.py` should:

- render from validated `LoadedWorkflowBundle.surface`
- optionally annotate or sidecar-link source-trace data
- write the required non-authoritative warning header
- emit only when `--emit-debug-yaml` is requested and validation succeeded

Do not reopen parser/lowering semantics or treat the YAML as importable/executable authority.

- [ ] **Step 5: Run observability and artifact tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py tests/test_runtime_observability_cli.py -q
```

Expected:

- compiled-run provenance is persisted in run metadata
- runtime output/report snapshots include authored source context when trace data exists
- debug-YAML artifact tests pass without changing execution authority

- [ ] **Step 6: Commit the provenance/observability bridge**

```bash
git add orchestrator/workflow_lisp/debug_yaml.py orchestrator/workflow_lisp/build.py orchestrator/workflow/surface_ast.py orchestrator/workflow/loaded_bundle.py orchestrator/workflow/executor.py tests/test_runtime_observability_cli.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_diagnostics.py
git commit -m "feat: add workflow lisp observability provenance"
```

## Task 6: Run The Full Verification Surface And Record Evidence

**Files:**

- Modify: `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/execution_plan.md` only if command names or file ownership changed during implementation

- [ ] **Step 1: Run the required collect-only check**

```bash
python -m pytest --collect-only tests/test_workflow_lisp_cli.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_diagnostics.py tests/test_runtime_observability_cli.py -q
```

Expected:

- collection succeeds for all added/renamed test modules

- [ ] **Step 2: Run the focused pytest suites from the architecture handoff**

```bash
python -m pytest tests/test_workflow_lisp_cli.py tests/test_workflow_lisp_build_artifacts.py -q
python -m pytest tests/test_workflow_lisp_diagnostics.py tests/test_runtime_observability_cli.py -q
python -m pytest tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py tests/test_cli_report_command.py -q
```

Expected:

- new CLI/build/diagnostic/observability tests pass
- key regression surfaces continue to pass

- [ ] **Step 3: Run real CLI smoke checks with the deterministic fixture manifests**

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc --entry-workflow orchestrate --source-root tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --imported-workflow-bundles-file tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json
python -m orchestrator run tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc --entry-workflow orchestrate --source-root tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --imported-workflow-bundles-file tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json --dry-run
python -m orchestrator explain tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc --form orchestrate --entry-workflow orchestrate --source-root tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --imported-workflow-bundles-file tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json
```

Expected:

- `compile` emits the documented artifact set under one deterministic build root
- `.orc` `run --dry-run` proves compile -> validate -> lint -> no execution behavior
- `explain` reports the selected form using implemented typed/lowered/source-trace surfaces

- [ ] **Step 4: Record verification evidence in the implementation handoff**

Capture in the final implementation summary:

- what files changed
- which pytest selectors ran
- which CLI smoke commands ran
- where the emitted build root and manifest landed
- whether debug YAML was emitted

- [ ] **Step 5: Commit the final verified slice**

```bash
git add orchestrator/cli/main.py orchestrator/cli/commands orchestrator/workflow_lisp orchestrator/workflow/surface_ast.py orchestrator/workflow/loaded_bundle.py orchestrator/workflow/executor.py tests
git commit -m "feat: add workflow lisp cli diagnostics surface"
```
