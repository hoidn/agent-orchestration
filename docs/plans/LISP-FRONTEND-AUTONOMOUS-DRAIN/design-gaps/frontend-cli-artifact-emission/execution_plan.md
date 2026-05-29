# Frontend CLI Artifact Emission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded Workflow Lisp CLI artifact-emission contract so `orchestrate compile` and `orchestrate explain` can export canonical Core AST, Semantic IR, source-map, and debug-YAML artifacts to user-requested paths without changing artifact authority, manifest authority, or deterministic build-root behavior.

**Architecture:** Keep the deterministic build root under `.orchestrate/build/<fingerprint>/` as the only canonical compiled output and add one thin frontend-owned export layer on top of it. Parse explicit emit flags in the CLI, normalize them into a shared export-request model, build the canonical frontend bundle exactly as today, then copy already-emitted canonical artifacts to caller-visible destinations and report those destinations back through command output.

**Tech Stack:** Python 3, `argparse`, `dataclasses`, `enum`, `pathlib.Path`, `json`, `shutil`, `orchestrator/cli/`, `orchestrator/workflow_lisp/build.py`, pytest, and existing Workflow Lisp fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these as implementation authority for this slice:

- `docs/index.md`
- `docs/steering.md`
  - currently empty in this checkout; do not treat that as permission to widen scope
- `docs/design/workflow_lisp_frontend_specification.md`
  - `76. Build Artifacts`
  - `77. Compile`
  - `79. Explain Expansion`
  - `80. Emit Debug YAML`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-cli-artifact-emission/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/5/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
  - currently `{"ledger_version":1,"events":[]}`; there is no prior execution history to reconcile for this gap

## Hard Scope Limits

Implement only the bounded artifact-emission slice:

- explicit `compile` and `explain` emit flags for:
  - `core_workflow_ast.json`
  - `semantic_ir.json`
  - `source_map.json`
  - non-authoritative debug YAML
- one shared frontend-local export-request normalization and destination helper
- path-capable `--emit-debug-yaml` behavior on both commands
- command output that reports emitted export paths separately from canonical build-root paths
- focused CLI/build verification for successful copies, default destinations, export-layer failures, and one narrow real CLI smoke check for the emit surface

Explicit non-goals:

- no new Workflow Lisp language forms, macros, procedures, or stdlib behavior
- no redesign of compilation, lowering, validation, runtime execution, explain subject selection, or shared serializer schemas
- no changes to the deterministic build fingerprint model or canonical build-root artifact set
- no user-selected export destinations recorded in `manifest.json`
- no reserialization of Core AST, Semantic IR, or source maps from console output
- no helper scripts, inline shell glue, report parsing, pointer-as-state recovery, or command-adapter policy changes

## Current Repo Baseline

Assume this exact starting point:

- `docs/steering.md` is empty in this checkout.
- `orchestrator/workflow_lisp/build.py` already emits canonical build-root artifacts including:
  - `core_workflow_ast.json`
  - `semantic_ir.json`
  - `runtime_plan.json`
  - `source_map.json`
  - optional `expanded.debug.yaml`
- `FrontendBuildRequest.emit_debug_yaml` is currently a boolean input to canonical artifact generation.
- `orchestrator/cli/main.py` exposes only a boolean `--emit-debug-yaml` on `compile`; `explain` has no emit flags.
- `orchestrator/cli/commands/compile.py` already prints a JSON summary with `artifact_paths` but no explicit export contract.
- `orchestrator/cli/commands/explain.py` already prints typed/lowered/executable/Core-AST/Semantic-IR/source-trace payloads to stdout but does not export compiled artifacts to files.
- `tests/test_workflow_lisp_cli.py` already covers parser wiring, compile/explain behavior, `.orc` dry-run dispatch, and manifest diagnostics.
- `tests/test_workflow_lisp_build_artifacts.py` already locks the canonical artifact bundle, manifest fields, and debug-YAML canonical emission behavior.

Execution rule for this plan: if current code disagrees with the approved implementation architecture above, the architecture and the tests written from this plan win.

## Locked Contracts

Do not re-decide any of these during implementation.

### Emit Flag Surface

Both `orchestrate compile` and `orchestrate explain` must accept:

```text
--emit-core-ast [PATH]
--emit-semantic-ir [PATH]
--emit-source-map [PATH]
--emit-debug-yaml [PATH]
```

Behavior rules:

- the flag name selects the canonical artifact kind
- if the flag is present without a path, export to the current working directory using the canonical filename:
  - `core_workflow_ast.json`
  - `semantic_ir.json`
  - `source_map.json`
  - `expanded.debug.yaml`
- if the flag is present with a path, resolve that path relative to `Path.cwd()`
- repeated requests for the same artifact kind are a CLI-request error, not "last flag wins"
- exported paths are convenience copies only; they do not become workflow inputs, manifest inputs, or semantic authority

### Namespace And Normalization Contract

Implement parser storage so duplicates are detectable before normalization:

- each emit flag should parse into a repeatable list of optional path values
- empty list means "not requested"
- one `None` entry means "requested with default filename in cwd"
- one string entry means "requested with explicit destination"
- more than one entry for the same artifact kind must normalize into a frontend diagnostic and exit code `2`

The shared normalization helper must:

- map raw CLI values to a frontend-local export request model
- resolve destinations relative to the current working directory
- create parent directories for explicit or default destinations
- reject destinations that resolve to existing directories
- stay completely outside build fingerprinting and build-manifest persistence

### Canonical Versus Exported Artifacts

- the deterministic build root remains the only canonical compiled output
- `manifest.json` continues to describe only canonical build-root artifacts
- do not add exported convenience destinations to `result.manifest.artifact_paths`
- do not add exported convenience destinations to `result.artifact_paths`
- debug YAML exports must copy the canonical rendered file; they must not rerender with separate logic
- exported file bytes must match canonical artifact bytes whenever the canonical artifact already exists on disk

### Compile And Explain Behavior

- `compile` must continue to build the canonical bundle first, then export requested artifacts, then print a JSON summary
- `compile` must add an `exported_artifacts` object separate from the canonical `artifact_paths` object
- `explain` must keep current subject-selection and stdout rendering behavior
- `explain` exports are compilation-scoped, not selected-form-scoped
- `explain` must print a short emitted-path summary only when exports were requested
- if compilation/validation fails, no export copying occurs
- if canonical compilation succeeds but export copying fails, the command exits nonzero without deleting the canonical build root

### Debug-YAML Rules

- a debug-YAML export request on either command must force canonical debug-YAML generation for that build
- canonical debug YAML remains optional and non-authoritative
- exported debug YAML must preserve the existing warning text that it is a debug projection and must not be used as execution input

## File Ownership

Modify:

- `orchestrator/cli/main.py`
- `orchestrator/cli/commands/compile.py`
- `orchestrator/cli/commands/explain.py`
- `orchestrator/workflow_lisp/build.py`
- `tests/test_workflow_lisp_cli.py`
- `tests/test_workflow_lisp_build_artifacts.py`

Modify only if a targeted failing test proves wiring requires it:

- `orchestrator/cli/commands/__init__.py`

Do not broaden ownership into shared AST/IR/runtime modules or frontend compiler/lowering modules for this slice.

## Task 1: Lock The Emit-Flag And Output Contract In Tests

**Files:**

- Modify: `tests/test_workflow_lisp_cli.py`

- [ ] **Step 1: Add failing parser tests for the new emit flags**

Extend `tests/test_workflow_lisp_cli.py` so parser coverage proves:

- `compile` accepts all four emit flags
- `explain` accepts all four emit flags
- each flag supports both bare usage and explicit path usage
- parser storage preserves duplicates instead of silently overwriting them

Required assertions:

- bare `--emit-core-ast` parses as one request with no path
- explicit `--emit-source-map out/maps/source_map.json` preserves the provided path
- bare `--emit-debug-yaml` now works on `explain`
- repeated `--emit-core-ast` yields two raw entries so normalization can reject it later

- [ ] **Step 2: Add failing command-behavior tests for compile and explain exports**

Add focused tests that prove:

- `compile` writes default-named exports into `tmp_path` when flags are present without paths
- `compile` writes explicit export destinations and reports them under `exported_artifacts`
- `compile` keeps canonical `artifact_paths` pointing at the build root and does not mix in convenience destinations
- `explain` exports the canonical compiled build artifacts even when `--form` selects a procedure or imported call target
- `explain` prints an emitted-path summary only when exports are requested

- [ ] **Step 3: Add failing command-error tests for export normalization and copy failures**

Cover these failure paths:

- duplicate emit flags for the same artifact kind
- export destination that resolves to an existing directory
- export copy failure after canonical build success

Prefer deterministic tests:

- directory rejection can use a real directory under `tmp_path`
- copy failure can monkeypatch the export helper or `Path.write_bytes` / copy primitive to raise `OSError`

- [ ] **Step 4: Run collect-only on the touched module**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_cli.py -q
```

Expected: collection succeeds and the new emit/export tests are listed.

- [ ] **Step 5: Run the narrow CLI selectors and confirm they fail first**

Run:

```bash
python -m pytest tests/test_workflow_lisp_cli.py -k "emit or exported_artifacts or explain_workflow" -q
```

Expected: FAIL because the parser, command summaries, and export normalization contract do not exist yet.

## Task 2: Add The Shared Frontend Export Request Model And Emission Helper

**Files:**

- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Add failing helper-level tests for normalization and canonical-copy rules**

Extend `tests/test_workflow_lisp_build_artifacts.py` with focused tests for a frontend-owned helper API in `build.py` that covers:

- normalization of raw CLI emit requests into one structured request per artifact kind
- default destination selection in the current working directory
- automatic parent-directory creation
- duplicate-request rejection
- directory-destination rejection
- exported bytes matching canonical bytes for:
  - `core_workflow_ast`
  - `semantic_ir`
  - `source_map`
  - `expanded_debug_yaml`
- manifest and canonical `artifact_paths` remaining unchanged after export copying

- [ ] **Step 2: Run the focused artifact selector and confirm it fails**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "export or debug_yaml or manifest" -q
```

Expected: FAIL because `build.py` does not yet expose a shared export-request model or export-copy helper.

- [ ] **Step 3: Implement the export request model in `build.py`**

Add frontend-local types and helpers directly in `orchestrator/workflow_lisp/build.py`:

- one artifact-kind enum or equivalent closed set for:
  - `core_workflow_ast`
  - `semantic_ir`
  - `source_map`
  - `expanded_debug_yaml`
- one dataclass representing a normalized export request
- one normalization helper that converts raw optional-path lists plus `cwd` into structured requests
- one emission helper that accepts `FrontendBuildResult` plus normalized requests and copies canonical artifact files to requested destinations

Required implementation rules:

- keep export destinations out of `FrontendBuildRequest` so they cannot leak into fingerprinting
- source existing JSON exports from `result.artifact_paths[...]`
- source debug YAML export from the canonical `expanded_debug_yaml` path already produced by the build
- create parent directories before copying
- raise `LispFrontendCompileError` with `_cli_request_diagnostic(...)`-style diagnostics for duplicate requests, directory destinations, and copy failures

- [ ] **Step 4: Preserve canonical build behavior and manifest authority**

While implementing the helper:

- do not change the canonical filenames or canonical artifact set
- do not change `result.manifest.artifact_paths`
- do not change `result.manifest.debug_yaml_status` semantics
- do not change `result.artifact_paths`
- do not change the build fingerprint or canonical build-root layout

- [ ] **Step 5: Re-run the focused helper selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "export or debug_yaml or manifest" -q
```

Expected: PASS with the shared export model enforcing default destinations, copy semantics, and manifest isolation.

## Task 3: Wire The New Emit Surface Into CLI Parsing And Compile/Explain Commands

**Files:**

- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/compile.py`
- Modify: `orchestrator/cli/commands/explain.py`
- Modify: `tests/test_workflow_lisp_cli.py`

- [ ] **Step 1: Update CLI parsing to preserve repeatable optional-path emit flags**

In `orchestrator/cli/main.py`:

- replace the boolean `--emit-debug-yaml` compile-only flag with the new optional-path surface
- add matching emit flags to `explain`
- use parser settings that preserve duplicates for later normalization rather than silently overwriting them

Keep all non-frontend commands unchanged.

- [ ] **Step 2: Normalize export requests before building**

In both command handlers:

- call the shared normalization helper with `Path.cwd()`
- detect whether debug YAML is among the requested exports
- set `FrontendBuildRequest.emit_debug_yaml` from that normalized request set so canonical debug YAML exists before export copying

Do not put raw export destinations on `FrontendBuildRequest`.

- [ ] **Step 3: Update `compile` to emit requested exports and return a stable summary**

In `orchestrator/cli/commands/compile.py`:

- export requested artifacts after `build_frontend_bundle(...)` succeeds
- keep the existing canonical summary fields:
  - `fingerprint`
  - `entry_workflow`
  - `build_root`
  - `imported_bundle_keys`
  - `artifact_paths`
  - `diagnostic_count`
- add a new `exported_artifacts` map of artifact kind to emitted destination path
- keep canonical `artifact_paths` build-root-relative-to-result behavior unchanged

If export copying fails, return `2` after logging the frontend diagnostic.

- [ ] **Step 4: Update `explain` to emit canonical compiled artifacts after normal stdout rendering**

In `orchestrator/cli/commands/explain.py`:

- keep existing explain subject selection and payload printing untouched
- export requested compiled artifacts only after successful explain rendering data is available
- treat exports as compilation-scoped even when `--form` points at:
  - a local procedure
  - an imported call target
  - a non-entry local workflow
- print one short emitted-path section only when exports were requested

Recommended output shape:

```text
Exported artifacts:
{
  "core_workflow_ast": "/abs/path/..."
}
```

- [ ] **Step 5: Re-run the narrow CLI selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_cli.py -k "emit or exported_artifacts or explain_workflow" -q
```

Expected: PASS with parser wiring, compile JSON output, explain export summaries, and deterministic export failures all covered.

## Task 4: Close The Regression Gaps Around Canonical Debug YAML And Manifest Isolation

**Files:**

- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_cli.py`
- Modify: `orchestrator/workflow_lisp/build.py`

- [ ] **Step 1: Add regression tests for debug-YAML export semantics**

Prove all of these:

- a debug-YAML export request on `compile` still yields canonical `expanded.debug.yaml` under the build root
- the exported debug YAML bytes equal the canonical build-root file bytes
- the exported debug YAML still contains the non-authoritative warning text
- a run without any debug-YAML request still removes stale canonical debug YAML for the same fingerprint as today

- [ ] **Step 2: Add regression tests for manifest isolation**

Prove that after successful exports:

- `manifest.json` contains only canonical artifact paths
- no user-chosen export destination appears in `manifest.json`
- no user-chosen export destination appears in `artifact_paths`
- `exported_artifacts` appears only in `compile` command output and explain stdout, not in persisted build metadata

- [ ] **Step 3: Run the focused full-module suites**

Run:

```bash
python -m pytest tests/test_workflow_lisp_cli.py tests/test_workflow_lisp_build_artifacts.py -q
```

Expected: PASS with canonical build behavior preserved and the new export layer covered end-to-end.

## Task 5: Final Verification And Evidence Capture

**Files:**

- No new code files; verification only

- [ ] **Step 1: Re-run collect-only on all touched test modules**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_cli.py tests/test_workflow_lisp_build_artifacts.py -q
```

Expected: collection succeeds and no accidental parser/test-name regressions remain.

- [ ] **Step 2: Run the final deterministic pytest verification commands**

Run:

```bash
python -m pytest tests/test_workflow_lisp_cli.py -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -q
```

Expected: both suites PASS.

- [ ] **Step 3: Run narrow real CLI smoke checks for the new emit surface**

Run:

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc --entry-workflow orchestrate --source-root tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --imported-workflow-bundles-file tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json --emit-core-ast .orchestrate/tmp/frontend-cli-artifact-emission-smoke/compile/core_workflow_ast.json --emit-semantic-ir .orchestrate/tmp/frontend-cli-artifact-emission-smoke/compile/semantic_ir.json --emit-source-map .orchestrate/tmp/frontend-cli-artifact-emission-smoke/compile/source_map.json --emit-debug-yaml .orchestrate/tmp/frontend-cli-artifact-emission-smoke/compile/expanded.debug.yaml
python -m orchestrator explain tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix/neurips/entry.orc --form orchestrate --entry-workflow orchestrate --source-root tests/fixtures/workflow_lisp/modules/valid/imported_bundle_mix --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --imported-workflow-bundles-file tests/fixtures/workflow_lisp/cli/imported_workflow_bundles.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json --emit-source-map .orchestrate/tmp/frontend-cli-artifact-emission-smoke/explain/source_map.json --emit-debug-yaml .orchestrate/tmp/frontend-cli-artifact-emission-smoke/explain/expanded.debug.yaml
```

Expected:

- `compile` reports canonical build-root `artifact_paths` plus a separate emitted-export surface for the requested destinations
- `explain` preserves the existing selected-form explanation output and prints the emitted-path summary only because emit flags were requested
- the requested export files are created under `.orchestrate/tmp/frontend-cli-artifact-emission-smoke/` without becoming canonical manifest/build-root authority

- [ ] **Step 4: Record implementation evidence in the completion handoff**

The implementation handoff must state:

- which files changed
- the exact emit-flag contract implemented
- that canonical build-root artifacts remained authoritative
- that exported destinations were not persisted into `manifest.json`
- the exact pytest and CLI smoke commands run and whether they passed
- the canonical build root reported by the smoke compile command and the emitted export paths reported by both smoke commands

## Notes For The Implementer

- Prefer adding the shared export helper to `orchestrator/workflow_lisp/build.py` rather than teaching each CLI command to copy files itself.
- Keep the command-boundary provenance already present in canonical Core AST / Semantic IR / source-map artifacts untouched; the export layer should only move bytes, not reinterpret them.
- If a test suggests adding export requests to the fingerprint or manifest to "make verification easier," the test is wrong for this slice and should be corrected.
- Because this slice changes the user-visible Workflow Lisp artifact-emission contract, final verification must include at least one real `python -m orchestrator` CLI smoke check in addition to pytest coverage.
- Keep that smoke coverage compile/explain-scoped. No `.orc` `run --dry-run` smoke command is required unless implementation unexpectedly changes runtime execution behavior or command dispatch outside the bounded emit surface.
