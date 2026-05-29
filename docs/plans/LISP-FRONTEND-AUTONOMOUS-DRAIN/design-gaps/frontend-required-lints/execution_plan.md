# Workflow Lisp Frontend Required Lints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded required-lint registry, policy, and enforcement slice for Workflow Lisp `.orc` authoring so the frontend can classify required lints, preserve warning/info findings without aborting successful builds, and keep command-boundary and authority-policy violations on the existing diagnostics/build surface.

**Architecture:** Keep all new ownership inside `orchestrator/workflow_lisp/`, add one frontend-owned lint policy layer in `lints.py`, and reuse the existing staged pipeline plus `LispFrontendDiagnostic`, `validation_pass`, `authority_layer`, `LoweringOriginMap`, `diagnostics.json`, and `source_map.json`. Active rules attach to existing owning passes and modules, reserved rules exist only as registry metadata until the authored surface exists, and compile/build blocking is driven by effective severity rather than by the mere presence of any diagnostic.

**Tech Stack:** Python dataclasses, `orchestrator/workflow_lisp`, shared `orchestrator.workflow` validation/runtime surfaces, pytest, existing Workflow Lisp fixtures under `tests/fixtures/workflow_lisp/`, and the existing frontend build artifact path under `.orchestrate/build/`.

---

## Fixed Inputs

Read these before implementation and treat them as authority:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `66. Report-Authority Validation`
  - `76.1 Editor And Lint Tooling Compatibility`
  - `92. Required Lints`
  - `93. Lint Levels`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-required-lints/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/2/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/2/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Reference these implementation seams before editing:

- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/resource_stdlib.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/validation.py`
- `orchestrator/workflow_lisp/workflow_refs.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_resource_stdlib.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/test_workflow_lisp_workflow_refs.py`

## Current Repo Baseline

Assume this exact starting point:

- `docs/steering.md` is empty in this checkout and does not widen scope.
- `progress_ledger.json` is still `{"ledger_version":1,"events":[]}`.
- `orchestrator/workflow_lisp/diagnostics.py` already persists `severity`, `phase`, `validation_pass`, and `authority_layer`, but it does not yet distinguish lint findings from ordinary validation failures.
- `orchestrator/workflow_lisp/validation.py` already orchestrates ordered passes, but `raise_pipeline_diagnostics(...)` still raises on any collected diagnostic and therefore cannot preserve warning-level lints on successful compile/build paths.
- `orchestrator/workflow_lisp/compiler.py` already runs one staged Stage 3 pipeline with `type` covering `effect`, `reference`, `contract`, `proof`, and `authority`, but it does not thread a lint profile or retain non-blocking diagnostics on success.
- `orchestrator/workflow_lisp/build.py` already writes `diagnostics.json`, but successful builds currently pass an empty `diagnostics` tuple into `_write_build_artifacts(...)`.
- The checkout already enforces part of the command/authority surface through existing error diagnostics:
  - `command_adapter_missing_contract`
  - `inline_python_command_in_workflow`
  - `inline_shell_command_in_workflow`
  - `semantic_field_extracted_from_report`
  - `markdown_report_used_as_state`
  - `pointer_used_as_semantic_authority`
  - `legacy_adapter_missing_fixture`
- `workflow_refs.py` already exists and compile-time workflow refs are real in this checkout, so `workflow_call_signature_erased` must hook into the current generic workflow-ref path instead of inventing a new drain-only mechanism.
- The architecture requires `macro_hidden_effect` to participate in the registry. If the current macro path does not already emit that exact code, normalize the existing macro-effect diagnostic surface to it in this slice rather than introducing a parallel alias.

Execution rule for this plan: if current code diverges from the approved implementation architecture, the approved architecture and the failing tests written from this plan win.

## Hard Scope Limits

Implement only the bounded required-lints slice:

- one frontend-owned required-lint registry with active versus reserved status;
- two lint severity profiles:
  - `default`
  - `strict`
- one diagnostic envelope extension:
  - `diagnostic_kind: validation | required_lint`
- severity-aware pipeline behavior so warning/info lints persist without aborting compile/build/run;
- active required-lint detectors on current `.orc` surfaces:
  - command boundary
  - workflow refs
  - macro/effect
  - phase/resource lowering
  - lowered contract shape
  - pointer/report authority
- adopted command-adapter-contract lint codes on the same `.orc` policy surface;
- focused regression coverage and one frontend compile smoke path proving warning persistence through normal artifacts.

Explicit non-goals:

- no new `.orc` language forms or stdlib forms;
- no new `orchestrate lint` command, no editor/LSP transport, and no new persisted lint artifact;
- no shared-validation rewrite, no duplicate runtime legality checks, and no redesign of Core AST, Semantic IR, TypeCatalog, SourceMap, pointer authority, or variant-proof semantics;
- no new command adapters, no legacy-adapter framework redesign, and no runtime-native promotion work;
- no shell-text heuristics beyond the already accepted `python -c` / `python -` / `bash -c` / `sh -c` bans already represented structurally by the frontend.

## Locked Contracts

Do not re-decide any of these during execution:

- `orchestrator/workflow_lisp/lints.py` is policy metadata plus focused rule helpers, not a second top-level compiler or second diagnostics protocol.
- `LispFrontendDiagnostic` remains the only diagnostic record.
- `diagnostic_kind` has exactly two values in this slice:
  - `validation`
  - `required_lint`
- `validation_pass` and `authority_layer` stay authoritative for pass ownership; `diagnostic_kind` only classifies the finding.
- Shared-validation codes remain unchanged. Do not wrap `pointer_authority_conflict`, `contract_refinement_weakened`, `workflow_call_version_mismatch`, or other shared codes in frontend-only lint aliases.
- Reserved lint codes must exist in the registry now, but they must not get fake heuristic detectors before the corresponding authored surface exists.
- Warning/info lints persist in `diagnostics.json` and renderer output but do not abort compile/build/run.
- Error lints remain blocking.
- Successful builds with lints still write the existing `diagnostics.json`; do not add `lint_report.json`.
- Lowered-surface lint findings must remap through `LoweringOriginMap` so authored `.orc` spans remain the user-facing provenance.

## Required Lint Catalog

Implement this registry exactly.

### Active Codes

| Code | Owning Pass | Default | Strict | Primary Surface |
| --- | --- | --- | --- | --- |
| `low_level_state_path_in_high_level_module` | `contract` | `warn` | `error` | typed AST + path/context contracts |
| `semantic_field_extracted_from_report` | `authority` | `error` | `error` | typed AST + command boundary |
| `markdown_report_used_as_state` | `authority` | `error` | `error` | typed AST + lowered shape |
| `variant_output_without_variant_specific_fields` | `contract` | `warn` | `error` | derived record/union contracts |
| `pointer_used_as_semantic_authority` | `authority` | `error` | `error` | typed AST + lowered shape |
| `resource_move_without_transition` | `authority` | `error` | `error` | resource stdlib lowering + command-boundary metadata |
| `recovery_gate_without_resume_or_start` | `authority` | `error` | `error` | phase stdlib lowering + reusable-state metadata |
| `workflow_call_signature_erased` | `reference` | `error` | `error` | workflow-ref resolution and call typing |
| `macro_hidden_effect` | `effect` | `error` | `error` | macro expansion/effect check |
| `command_adapter_missing_contract` | `authority` | `error` | `error` | command-boundary environment |
| `inline_python_command_in_workflow` | `authority` | `error` | `error` | `command-result` argv validation |
| `inline_shell_command_in_workflow` | `authority` | `error` | `error` | `command-result` argv validation |
| `legacy_adapter_missing_fixture` | `authority` | `error` | `error` | adapter metadata |

### Reserved Codes

| Code | Owning Pass | Default | Strict |
| --- | --- | --- | --- |
| `manual_snapshot_name_in_high_level_module` | `contract` | `warn` | `error` |
| `manual_candidate_path_in_high_level_module` | `contract` | `warn` | `error` |
| `line_prefix_extractor_in_workflow` | `authority` | `error` | `error` |
| `manual_when_requires_variant_pair` | `proof` | `warn` | `error` |
| `string_status_gate_without_union_match` | `authority` | `error` | `error` |
| `inline_json_state_rewrite` | `authority` | `error` | `error` |
| `inline_pointer_write` | `authority` | `error` | `error` |
| `inline_subprocess_nested_command` | `authority` | `error` | `error` |

## File Ownership

Create:

- `orchestrator/workflow_lisp/lints.py`
- `tests/fixtures/workflow_lisp/valid/lint_warning_variant_output.orc`

Modify:

- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/resource_stdlib.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/validation.py`
- `orchestrator/workflow_lisp/workflow_refs.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_resource_stdlib.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/test_workflow_lisp_workflow_refs.py`

Modify only if a targeted failing test proves it is necessary:

- `orchestrator/workflow_lisp/__init__.py`
- `tests/test_workflow_lisp_workflows.py`

Do not broaden ownership into `reader.py`, `syntax.py`, `definitions.py`, shared runtime modules under `orchestrator/workflow/`, or CLI argument parsing unless a failing test demonstrates that the approved lint-policy contract cannot be satisfied without a narrow patch there.

## Task 1: Lock The Lint Registry And Diagnostic Envelope

**Files:**

- Create: `orchestrator/workflow_lisp/lints.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Add failing diagnostics tests for the registry and `diagnostic_kind`**

Extend `tests/test_workflow_lisp_diagnostics.py` so it asserts:

- the registry contains every active and reserved code listed in this plan;
- active codes expose owning pass, authority layer, default severity, strict severity, and surface status;
- reserved codes serialize as policy metadata only and do not require detectors;
- serialized diagnostics include:
  - `diagnostic_kind`
  - `severity`
  - `phase`
  - `validation_pass`
  - `authority_layer`
- an adopted command-boundary code such as `command_adapter_missing_contract` serializes as:
  - `diagnostic_kind = "required_lint"`
  - `validation_pass = "authority"`
  - `authority_layer = "frontend"`
- an ordinary non-lint code such as `workflow_call_version_mismatch` still serializes as:
  - `diagnostic_kind = "validation"`
  - `validation_pass = "shared_validation"`

- [ ] **Step 2: Run collection on the touched diagnostics module**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_diagnostics.py -q
```

Expected: collection succeeds and the new registry/serialization tests appear.

- [ ] **Step 3: Run the narrow selector and confirm it fails first**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "diagnostic_kind or required_lint or registry or severity_profile" -q
```

Expected: FAIL because the registry does not exist yet and serialized diagnostics do not yet carry `diagnostic_kind`.

- [ ] **Step 4: Implement the lint policy module and diagnostic helpers**

In `orchestrator/workflow_lisp/lints.py`, add the frontend-owned policy model:

```text
RequiredLintRule
LintSeverityProfile
REQUIRED_LINT_RULES
ACTIVE_REQUIRED_LINT_CODES
RESERVED_REQUIRED_LINT_CODES
required_lint_rule(code)
required_lint_effective_severity(code, profile)
make_required_lint(...)
```

In `orchestrator/workflow_lisp/diagnostics.py`:

- add `diagnostic_kind` to `LispFrontendDiagnostic`;
- default non-lint findings to `validation`;
- use the registry to classify required-lint codes without changing their stable codes;
- keep render order and human-readable formatting deterministic.

- [ ] **Step 5: Re-run the selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py -k "diagnostic_kind or required_lint or registry or severity_profile" -q
```

Expected: PASS with the registry and serialized lint classification in place.

## Task 2: Make The Validation Pipeline Severity-Aware

**Files:**

- Modify: `orchestrator/workflow_lisp/validation.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Add failing tests for warning-versus-error behavior**

Add targeted tests that prove:

- a required lint whose effective severity is `warn` is retained in pipeline results but does not stop later passes;
- a required lint whose effective severity is `error` still stops the pipeline;
- `compile_stage3_module(...)` and `compile_stage3_entrypoint(...)` can run under:
  - `lint_profile="default"`
  - `lint_profile="strict"`
- a warning-only frontend build writes a non-empty `diagnostics.json` on success;
- the same warning escalates to a compile error under `strict`.

Prefer one synthetic pipeline unit test in `tests/test_workflow_lisp_diagnostics.py` and one real build-path test in `tests/test_workflow_lisp_build_artifacts.py`.

- [ ] **Step 2: Run collection on the touched modules**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_build_artifacts.py -q
```

Expected: collection succeeds and the new warning/strict-profile tests are listed.

- [ ] **Step 3: Run the narrow pipeline/build selector and confirm failure**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_build_artifacts.py -k "warning or strict or diagnostics_json or lint_profile" -q
```

Expected: FAIL because any emitted diagnostic still aborts compilation and successful builds still persist an empty diagnostics payload.

- [ ] **Step 4: Implement severity-aware aggregation without changing pass order**

In `orchestrator/workflow_lisp/validation.py`:

- preserve the existing pass order;
- classify pass diagnostics by effective severity after metadata attachment;
- set `ValidationPassResult.blocking` from the presence of at least one effective-`error` diagnostic, not from raw diagnostic count;
- make `raise_pipeline_diagnostics(...)` raise only the blocking subset;
- keep warning/info findings available through `collect_pipeline_diagnostics(...)`.

In `orchestrator/workflow_lisp/compiler.py`:

- add an optional `lint_profile` parameter, defaulting to `default`;
- thread the profile into pipeline execution and lint helper calls;
- retain collected non-blocking diagnostics on successful compile results, preferably by adding a `diagnostics` tuple to the Stage 3 result dataclasses instead of inventing a parallel result object.

In `orchestrator/workflow_lisp/build.py`:

- add `lint_profile` to `FrontendBuildRequest`;
- pass compile-time diagnostics from the successful compile result into `_write_build_artifacts(...)`;
- keep `diagnostics.json` as the only machine-readable diagnostics artifact.

- [ ] **Step 5: Re-run the selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_build_artifacts.py -k "warning or strict or diagnostics_json or lint_profile" -q
```

Expected: PASS with default warnings non-blocking, strict escalation blocking, and successful warning builds still emitting `diagnostics.json`.

## Task 3: Register And Emit Typed-Surface Required Lints

**Files:**

- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/workflow_refs.py`
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_workflow_refs.py`
- Modify: `tests/test_workflow_lisp_macros.py`

- [ ] **Step 1: Add failing typed-surface regressions before wiring new helpers**

Cover at least these cases:

- `command_adapter_missing_contract`, `inline_python_command_in_workflow`, and `inline_shell_command_in_workflow` now serialize as required lints rather than ordinary validation findings;
- `workflow_call_signature_erased` is emitted when a workflow-ref/call path loses its typed signature and would otherwise degrade to an opaque handle;
- `variant_output_without_variant_specific_fields` is emitted as a warning under `default` when a union result lowers with no variant-exclusive fields;
- `macro_hidden_effect` is emitted through the macro/effect path using the registry-managed severity.

Use existing workflow-ref and structured-result fixtures where possible. Add inline `tmp_path` modules only for cases not already represented in stable fixtures.

- [ ] **Step 2: Run the narrow surface selector and confirm it fails**

Run:

```bash
python -m pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_macros.py -k "required_lint or signature_erased or variant_output_without_variant_specific_fields or macro_hidden_effect" -q
```

Expected: FAIL because those codes are either unregistered, still classified as ordinary validation failures, or not emitted yet.

- [ ] **Step 3: Reuse existing authorities and replace ad hoc severity decisions**

Implement the typed-surface hooks in the modules that already own those semantics:

- `workflows.py`
  - keep `build_command_boundary_environment(...)` as the authority for adapter metadata completeness;
  - convert command-boundary completeness failures into required-lint diagnostics through the shared helper rather than open-coding severity/classification.
- `typecheck.py`
  - keep `_validate_command_argv(...)` as the authority for inline Python/shell bans;
  - emit required-lint diagnostics for command-boundary and report/pointer authority surfaces already visible during typing;
  - add the active `low_level_state_path_in_high_level_module` detector only where the authored high-level path usage is structurally visible today.
- `workflow_refs.py`
  - emit `workflow_call_signature_erased` at the point a typed workflow-ref would otherwise collapse to an opaque call target.
- `contracts.py`
  - emit `variant_output_without_variant_specific_fields` from the union-contract derivation seam, not from string inspection of lowered YAML-shaped data.
- `macros.py`
  - normalize the macro effect diagnostic path to `macro_hidden_effect` if the current checkout does not already emit that exact code.

- [ ] **Step 4: Re-run the selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_macros.py -k "required_lint or signature_erased or variant_output_without_variant_specific_fields or macro_hidden_effect" -q
```

Expected: PASS with the typed-surface active lint family registered and emitted through the shared policy surface.

## Task 4: Add Lowered-Surface Lint Hooks With Source-Mapped Provenance

**Files:**

- Modify: `orchestrator/workflow_lisp/lints.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/phase_stdlib.py`
- Modify: `orchestrator/workflow_lisp/resource_stdlib.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_resource_stdlib.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Add failing lowered-surface regressions**

Cover at least one active detector in each lowering-owned family:

- `recovery_gate_without_resume_or_start`
- `resource_move_without_transition`
- one pointer/report-authority violation that is only visible after lowering or stdlib elaboration
- one span-remap assertion proving the lint points back to the authored `.orc` form rather than a generated helper step

Keep shared-validation ownership intact: if the current failure is already a shared code such as `pointer_authority_conflict`, assert that no parallel frontend lint is emitted.

- [ ] **Step 2: Run the narrow lowering selector and confirm it fails**

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_lowering.py -k "resume_or_start or resource_transition or pointer_authority or source_map or required_lint" -q
```

Expected: FAIL because the active lowering-surface lint family is not yet emitted or remapped through the required-lint registry.

- [ ] **Step 3: Implement post-lowering lint collection without duplicating shared validation**

In `orchestrator/workflow_lisp/lints.py`, add focused rule runners that accept typed/lowered workflow structures plus `LoweringOriginMap` provenance and return `LispFrontendDiagnostic` records classified as required lints.

Use them from `lowering.py` and the stdlib-owned lowering seams so that:

- `resource-transition` remains the only allowed queue/resource transition surface unless a certified `resource_transition` adapter explicitly declares that behavior class;
- `resume-or-start` remains the only allowed reusable-state gate unless a certified `resume_state_reuse` adapter explicitly declares that behavior class;
- pointer/report authority violations detected after elaboration still point to authored forms;
- no lints are invented for reserved codes whose authored surfaces do not yet exist.

- [ ] **Step 4: Re-run the selector and require a pass**

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_lowering.py -k "resume_or_start or resource_transition or pointer_authority or source_map or required_lint" -q
```

Expected: PASS with lowered-surface required lints source-mapped back to authored `.orc` spans.

## Task 5: Add The Warning-Fixture Build Path And Final Artifact Coverage

**Files:**

- Create: `tests/fixtures/workflow_lisp/valid/lint_warning_variant_output.orc`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Create one stable warning-only fixture**

Add `tests/fixtures/workflow_lisp/valid/lint_warning_variant_output.orc` with one minimal `provider-result` workflow whose union return type has no variant-exclusive fields, so it deterministically triggers:

- `variant_output_without_variant_specific_fields`
- severity `warn` under `default`
- severity `error` under `strict`

Keep it valid for shared validation so the default-profile compile/build path succeeds.

- [ ] **Step 2: Add failing build-artifact assertions for the warning fixture**

Extend `tests/test_workflow_lisp_build_artifacts.py` so a successful default-profile build:

- writes `diagnostics.json`;
- persists the warning diagnostic with:
  - `diagnostic_kind = "required_lint"`
  - `severity = "warn"`
  - correct `validation_pass` and `authority_layer`;
- leaves the rest of the emitted artifact set unchanged.

Add a companion strict-profile test that confirms the same fixture raises `LispFrontendCompileError`.

- [ ] **Step 3: Run collection on every touched test module**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_lowering.py -q
```

Expected: collection succeeds for every targeted module.

- [ ] **Step 4: Run the focused regression commands from the work-item bundle**

Run:

```bash
python -m pytest tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_structured_results.py -k "command_adapter_missing_contract or inline_python or inline_shell or pointer_authority or warning" -q
```

Expected: PASS.

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_macros.py -k "resume_or_start or resource_transition or workflow_ref or macro_hidden_effect" -q
```

Expected: PASS.

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_lowering.py -k "diagnostics or source_map or shared_validation" -q
```

Expected: PASS.

- [ ] **Step 5: Run one frontend compile smoke command for warning persistence**

Run:

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/lint_warning_variant_output.orc --entry-workflow orchestrate --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json
```

Expected:

- command exits successfully under the default lint profile;
- the emitted build root contains `diagnostics.json`;
- `diagnostics.json` contains the warning required lint instead of staying empty;
- no second lint-specific artifact appears.

## Completion Checklist

Do not claim completion until all of these are true:

- every code listed in the active and reserved tables exists in the registry;
- active detectors emit through the registry-managed required-lint surface instead of ad hoc severity logic;
- warning/info required lints do not abort successful compile/build paths;
- error required lints still abort compilation;
- `diagnostics.json` distinguishes `validation` from `required_lint`;
- shared-validation failures still use shared codes with no duplicate frontend lint aliases;
- the focused pytest commands above pass;
- the warning fixture smoke compile succeeds and leaves a non-empty `diagnostics.json`.
