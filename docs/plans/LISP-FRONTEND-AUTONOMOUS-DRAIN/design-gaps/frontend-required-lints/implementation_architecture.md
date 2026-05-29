# Frontend Required Lints Implementation Architecture

## Scope

This design gap covers only the bounded required-lint classification and
enforcement slice for high-level Workflow Lisp `.orc` authoring:

- define one frontend-owned required-lint registry for the lint surface named
  in `docs/design/workflow_lisp_frontend_specification.md` Sections `76.1`,
  `92`, and `93`;
- fold the command-boundary lint codes from
  `docs/design/workflow_command_adapter_contract.md` into the same registry for
  `.orc` workflows where those rules already apply;
- assign each lint code to an existing validation pass, authority layer,
  severity profile, and implemented detection surface;
- integrate lint emission into the current frontend diagnostics/build pipeline
  without adding a second linter, a second diagnostics protocol, or a new
  persisted report artifact;
- distinguish lints that are implementable on the current `.orc` surface from
  codes that must stay reserved until the corresponding authoring surface
  exists.

Out of scope for this tranche:

- new frontend language forms, new stdlib forms, or revisions to macro,
  module, procedure, workflow-ref, phase, resource, drain, or runtime
  semantics;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, queue semantics, or persisted
  runtime state;
- a new `orchestrate lint` CLI, editor/LSP implementation, or a second
  machine-readable diagnostics artifact beyond the existing diagnostics/build
  surfaces;
- new command adapters, legacy-adapter framework work, or runtime-native
  promotion beyond classifying those boundaries honestly;
- replacement of the product design in
  `docs/design/workflow_lisp_frontend_specification.md`.

This is an implementation architecture for exactly the selected
`frontend-required-lints` gap. It does not broaden into general validation,
CLI, or runtime redesign.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `66. Report-Authority Validation`
  - `76.1 Linter And LSP Compatibility`
  - `92. Required Lints`
  - `93. Lint Levels`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/steering.md`

The slice must also preserve the guardrails established by earlier
implementation architectures and the current checkout:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime/validation semantics under `orchestrator/workflow/`;
- reuse `LispFrontendDiagnostic`, `validation_pass`, `authority_layer`,
  `LoweringOriginMap`, persisted `diagnostics.json`, and persisted
  `source_map.json` rather than inventing a parallel lint transport;
- reuse the current staged pipeline:
  read -> syntax -> macro expansion -> definitions/callables ->
  typecheck/effects -> lowering -> shared validation -> semantic/runtime
  artifacts;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep shared validation authoritative for lowered path safety, pointer
  publication conflicts, contract refinement, workflow-call versioning, and
  executable/runtime semantics.

`docs/design/workflow_command_adapter_contract.md` is authoritative here
because this slice classifies and enforces command-boundary lint rules for
`command-result`, adapter-backed stdlib lowering, and legacy-adapter debt. The
lint layer must not become a loophole for:

- inline semantic Python or shell glue;
- report parsing as workflow authority;
- pointer-file authority;
- uncataloged semantic scripts hidden behind ordinary commands.

`docs/steering.md` is empty in this checkout. That does not widen scope. The
selector bundle, target contract, prior implementation architectures, and
current repo evidence remain the effective steering surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse `LispFrontendDiagnostic` as the single diagnostic record and keep
  `validation_pass` plus `authority_layer` as the existing machine-readable
  ownership fields.
- Reuse the frontend validation pipeline and attach lints to existing owning
  passes instead of inventing a separate top-level lint pass.
- Reuse `LoweringOriginMap` and source-map remapping for lints that are
  detected after lowering.
- Reuse the command-boundary classification already established by Stage 3,
  Stage 5, and Stage 6:
  `external_tool` versus `certified_adapter`, with adapter metadata taken from
  declared contracts rather than shell text.
- Reuse the honesty rule from the CLI/build and source-map slices:
  do not fabricate authoring surfaces that the repo does not yet expose just
  to say a lint exists.

### New Decisions In This Slice

- Add one explicit required-lint registry with per-code ownership,
  severity-profile mapping, and surface-availability status.
- Extend diagnostics with one narrow classification field,
  `diagnostic_kind`, so tooling can distinguish ordinary validation failures
  from required-lint findings without relying on code-name heuristics.
- Make the validation/build pipeline severity-aware:
  warning and info lints are preserved in diagnostics/build artifacts but do
  not fail compilation; error lints remain blocking.
- Treat the full-design lint list as two groups:
  - `active` rules that can be detected on the current implemented `.orc`
    surface;
  - `reserved` rules whose codes and metadata exist now, but whose detectors
    activate only when the relevant authored surface exists.
- Adopt the command-adapter-contract lint codes into the same registry for
  high-level `.orc` workflows, with `.orc` default severity staying `error`
  for hidden semantic glue.

### Conflicts Or Revisions

The frontend validation/diagnostics slice treated all diagnostics as
effectively blocking because the pipeline raises on any accumulated diagnostic.
This slice revises that behavior narrowly:

- blocking is now severity-driven rather than “any diagnostic means failure”;
- only diagnostics whose effective severity is `error` abort compile/build/run;
- warning and info lints remain visible in CLI/build output and persisted
  `diagnostics.json`.

The macro slice already owns `macro_hidden_effect` as a macro validation error.
This slice does not reimplement macro checking. It only registers
`macro_hidden_effect` as one of the required lint codes so lint tooling and
policy profiles can treat it consistently with the rest of the required-lint
surface.

No prior slice is revised on shared concepts such as spans, diagnostics, Core
Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority,
or variant proof.

## Ownership Boundaries

This slice owns:

- the required-lint registry, severity profiles, and activation status for the
  Workflow Lisp frontend;
- the frontend diagnostic-kind/severity policy needed to preserve warnings
  without aborting successful compile/build paths;
- rule runners over existing frontend-owned surfaces:
  typed expressions, workflow/procedure signatures, macro-expanded syntax,
  phase/resource/drain stdlib lowering metadata, and lowered workflow mappings;
- the code-to-pass ownership map for both full-design required lints and the
  adopted command-boundary lint codes;
- focused tests for lint classification, warning-versus-error behavior,
  persisted diagnostics serialization, and rule activation/deactivation on
  current versus deferred surfaces.

This slice intentionally does not own:

- new authoring forms solely to make a lint implementable;
- shared validation of lowered pointer publication conflicts, snapshot refs,
  contract refinement, or workflow version compatibility;
- new command adapters, legacy adapters, or runtime-native effects;
- editor/LSP transport, a new standalone lint CLI, or a second diagnostics
  artifact.

## Current Checkout Facts

- `orchestrator/workflow_lisp/diagnostics.py` already has `severity`,
  `validation_pass`, and `authority_layer`, but it does not distinguish lint
  findings from ordinary validation failures.
- `orchestrator/workflow_lisp/validation.py` has no dedicated required-lint
  registry and still raises aggregate compile errors on any emitted diagnostic.
- The current checkout already enforces a partial authority-lint subset:
  `command_adapter_missing_contract`,
  `inline_python_command_in_workflow`,
  `inline_shell_command_in_workflow`,
  `semantic_field_extracted_from_report`,
  `markdown_report_used_as_state`,
  `pointer_used_as_semantic_authority`,
  `legacy_adapter_missing_fixture`.
- Repo tests already prove that partial subset through
  `tests/test_workflow_lisp_diagnostics.py`,
  `tests/test_workflow_lisp_structured_results.py`, and
  `tests/test_workflow_lisp_resource_stdlib.py`.
- Most required lints named by full-design Section `92` do not yet have a
  registry entry, severity policy, or test coverage in code.
- `docs/lisp_workflow_drafting_guide.md` already documents part of the lint
  intent, so the remaining gap is compiler classification/enforcement rather
  than pure documentation.

## Proposed Package Boundary

Extend the frontend package with one explicit lint-policy layer and narrow
diagnostic/pipeline changes:

```text
orchestrator/workflow_lisp/
  lints.py              # new registry, profiles, rule runners, activation
  diagnostics.py        # add diagnostic_kind + severity/profile helpers
  validation.py         # error-only blocking and lint result collection
  compiler.py           # thread lint profile through staged compilation
  build.py              # persist warnings/info in diagnostics.json on success
  typecheck.py          # reuse for type/reference/authority lint hooks
  macros.py             # reuse macro_hidden_effect classification
  workflows.py          # reuse command-boundary and boundary-shape hooks
  phase_stdlib.py       # reuse resume-or-start lint hooks
  resource_stdlib.py    # reuse resource-transition lint hooks
  workflow_refs.py      # reuse workflow-call signature-erasure hooks
  lowering.py           # reuse lowered-shape lint hooks + source-map remap
  contracts.py          # reuse variant-contract lint hooks
```

Planned test surface:

```text
tests/
  test_workflow_lisp_diagnostics.py
  test_workflow_lisp_structured_results.py
  test_workflow_lisp_phase_stdlib.py
  test_workflow_lisp_resource_stdlib.py
  test_workflow_lisp_workflow_refs.py
  test_workflow_lisp_macros.py
  test_workflow_lisp_build_artifacts.py
  test_workflow_lisp_lowering.py
```

Responsibilities:

- `lints.py`
  - define the required-lint registry and severity profiles;
  - expose rule metadata and activation status;
  - provide helpers that emit `LispFrontendDiagnostic` with
    `diagnostic_kind = required_lint`.
- `diagnostics.py`
  - serialize and render `diagnostic_kind`;
  - compute effective severity from lint profile plus rule metadata.
- `validation.py`
  - treat warnings/info as non-blocking;
  - preserve them in pipeline results and aggregate serialization;
  - keep pass ordering unchanged.
- existing feature modules
  - remain the authorities for their owned authored surfaces;
  - call the lint helpers instead of inventing ad hoc lint severity logic.

Do not add a new persisted `lint_report.json`. `diagnostics.json` remains the
machine-readable surface for both validation failures and lint findings.

## Diagnostic And Policy Model

### Required Lint Rule Record

Add a frontend-owned rule model:

```text
RequiredLintRule(
  code,
  summary,
  owning_pass,
  authority_layer,
  default_severity,
  strict_severity,
  surface_status,        # active | reserved
  primary_surface,       # typed_ast | lowered_surface | macro | workflow_ref | command_boundary
  replacement_hint,
)
```

This is policy metadata, not a second diagnostic type. Emitted findings still
use `LispFrontendDiagnostic`.

### Diagnostic Envelope Extension

Extend `LispFrontendDiagnostic` and serialized `diagnostics.json` payloads with
one new field:

```text
diagnostic_kind: validation | required_lint
```

Reason:

- future lint/LSP tooling needs a stable way to distinguish lint findings from
  ordinary invalid-program diagnostics;
- severity alone is insufficient because several required-lint codes are
  intentionally errors.

### Severity Profiles

Define two frontend profiles for this slice:

- `default`
  - warnings stay warnings for the ergonomic/high-level authoring lints named
    as warnings in full-design Section `93`;
  - command-boundary, authority, macro-hidden-effect, and signature-erasure
    lints remain errors.
- `strict`
  - escalates the default-warning required lints to errors;
  - leaves existing default-error lints unchanged.

No separate lint CLI is required. The compiler/build APIs take an optional
`lint_profile` parameter, defaulting to `default`.

## Required Lint Inventory

### Active On The Current `.orc` Surface

| Code | Owning Pass | Default | Strict | Primary Detection Surface | Notes |
| --- | --- | --- | --- | --- | --- |
| `low_level_state_path_in_high_level_module` | `contract` | `warn` | `error` | typed AST + context/path contracts | Detect authored low-level state-root/phase-state path spelling in ordinary user modules instead of derived context/layout helpers. |
| `semantic_field_extracted_from_report` | `authority` | `error` | `error` | typed AST + command boundary | Keep current report-parsing ban. |
| `markdown_report_used_as_state` | `authority` | `error` | `error` | typed AST + lowered shape | Keep current report-as-authority ban. |
| `variant_output_without_variant_specific_fields` | `contract` | `warn` | `error` | derived record/union contracts | Emit when a union lowers with no variant-exclusive fields and should instead be a record plus enum. |
| `pointer_used_as_semantic_authority` | `authority` | `error` | `error` | typed AST + lowered shape | Keep current pointer-authority ban. |
| `resource_move_without_transition` | `authority` | `error` | `error` | resource stdlib lowering + command-boundary metadata | Emit when queue/ledger movement is authored outside `resource-transition` or a certified `resource_transition` adapter. |
| `recovery_gate_without_resume_or_start` | `authority` | `error` | `error` | phase stdlib lowering + reusable-state metadata | Emit when reusable-state gating is authored outside `resume-or-start` or an explicit certified `resume_state_reuse` adapter bridge. |
| `workflow_call_signature_erased` | `reference` | `error` | `error` | workflow-ref resolution and call typing | Emit when a workflow ref/call operand loses its typed signature and falls back to an opaque handle. |
| `macro_hidden_effect` | `effect` | `error` | `error` | macro expansion/effect check | Reuse existing macro diagnostic. |
| `command_adapter_missing_contract` | `authority` | `error` | `error` | command-boundary environment | Adopted from command adapter contract. |
| `inline_python_command_in_workflow` | `authority` | `error` | `error` | `command-result` argv validation | Adopted from command adapter contract. |
| `inline_shell_command_in_workflow` | `authority` | `error` | `error` | `command-result` argv validation | Adopted from command adapter contract. |
| `legacy_adapter_missing_fixture` | `authority` | `error` | `error` | adapter metadata | Active as soon as any legacy adapter binding is permitted. |

### Reserved Until The Authored Surface Exists

| Code | Future Owning Pass | Default | Strict | Activation Condition |
| --- | --- | --- | --- | --- |
| `manual_snapshot_name_in_high_level_module` | `contract` | `warn` | `error` | Activate when authored snapshot naming or low-level snapshot interop becomes legal on `.orc`. |
| `manual_candidate_path_in_high_level_module` | `contract` | `warn` | `error` | Activate when authored candidate-path surfaces exist beyond compiler-owned lowering. |
| `line_prefix_extractor_in_workflow` | `authority` | `error` | `error` | Activate when explicit extractor or legacy-adapter syntax exists; until then direct violations continue to map to `semantic_field_extracted_from_report`. |
| `manual_when_requires_variant_pair` | `proof` | `warn` | `error` | Activate when authored `if`/`when` or explicit proof-guard surfaces exist. |
| `string_status_gate_without_union_match` | `authority` | `error` | `error` | Activate when authored string-comparison gate surfaces exist. |
| `inline_json_state_rewrite` | `authority` | `error` | `error` | Activate when command AST or adapter metadata can honestly expose JSON state rewrites. |
| `inline_pointer_write` | `authority` | `error` | `error` | Activate when inline pointer-writing commands can be identified structurally rather than by shell-text guesswork. |
| `inline_subprocess_nested_command` | `authority` | `error` | `error` | Activate when command-boundary metadata can expose nested subprocess launch patterns explicitly. |

Reserved means:

- the code exists in the registry now;
- diagnostics tooling can recognize the code and its intended policy;
- the compiler does not fabricate a heuristic detector until the relevant
  authored surface actually exists.

## Detection Architecture

### 1. Typed-Authoring Lints

Run after type/reference/proof checking succeeds for authored forms that are
already represented structurally in the frontend AST:

- low-level state path authoring;
- workflow-ref signature erasure;
- union shapes that collapse to “record plus enum”;
- report-as-state or pointer-as-authority forms already visible in typed
  authoring structures.

These rules emit diagnostics directly from frontend spans and form paths.

### 2. Lowered-Surface Lints

Run after lowering when the relevant violation is only visible once stdlib
forms are elaborated into lowered workflow mappings:

- resource movement outside `resource-transition`;
- reusable-state gates outside `resume-or-start`;
- pointer/report authority violations introduced through adapter-backed helper
  lowering;
- candidate/state-path spelling that survives as authored low-level data.

These rules must remap through `LoweringOriginMap` so diagnostics still point
to authored `.orc` forms rather than generated helper steps.

### 3. Command-Boundary Lints

Keep command-boundary linting declarative:

- read only declared adapter/tool metadata and structured argv tokens already
  modeled by the frontend;
- never inspect shell text for hidden semantics beyond the existing
  first-token/second-token ban on inline `python -c`, `python -`, `bash -c`,
  and `sh -c`;
- for `resource_move_without_transition` and
  `recovery_gate_without_resume_or_start`, use the command-adapter contract’s
  behavior classes:
  `resource_transition` and `resume_state_reuse`.

If a command is workflow-semantic and does not declare the required adapter
metadata, emit `command_adapter_missing_contract` rather than a weaker advisory.

### 4. Shared Validation Boundary

The lint layer does not duplicate shared-validation errors. When the shared
validator already owns a lower-level semantic failure, preserve the shared code
and add no parallel required-lint code. Examples:

- `pointer_authority_conflict`
- `contract_refinement_weakened`
- `workflow_call_version_mismatch`

Required lints cover high-level authoring policy. Shared validation remains the
authority on lowered runtime legality.

## Enforcement Model

- `diagnostic_kind = required_lint` plus effective severity `error`
  behaves like current blocking diagnostics.
- `diagnostic_kind = required_lint` plus severity `warn` or `info`
  is persisted and rendered but does not abort compile/build/run.
- successful builds with warnings still emit `diagnostics.json`.
- CLI/build rendering should keep the existing deterministic sort order and add
  a short lint label only through `diagnostic_kind`, not a second free-form
  message style.

No general allowlist is introduced for new high-level `.orc` workflows in this
slice. If a future legacy or migration surface needs one, it must reuse the
replacement/owner/expiry metadata model required by
`docs/design/workflow_command_adapter_contract.md` rather than a silent local
suppression.

## Acceptance Criteria

This slice is complete when:

1. every full-design required lint and adopted command-boundary lint code has a
   registry entry with owning pass, authority layer, severity policy, and
   `active` versus `reserved` status;
2. `diagnostics.json` distinguishes `validation` from `required_lint` findings
   and preserves warning-level lint findings on successful compile/build paths;
3. warning-level lints no longer abort the validation pipeline, while
   error-level lints still do;
4. active lint rules cover the current implemented `.orc` surfaces for command
   boundaries, workflow refs, macro hidden effects, resource transitions,
   resume-or-start, pointer authority, report authority, and union-contract
   shape;
5. reserved lint codes are registered without fabricating fake detectors for
   missing authoring surfaces;
6. focused tests cover severity policy, serialization, and at least one active
   detector in each owned surface family:
   command boundary, workflow refs, macro/effect, phase/resource lowering, and
   lowered contract shape.

## Verification

Deterministic commands for the eventual implementation are recorded in:

- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/2/design-gap-architect/check_commands.json`

Those checks should stay narrow:

- collect the focused lint-related test modules first;
- run the diagnostics/structured-results tests that already cover the current
  authority lint subset;
- run targeted phase/resource/workflow-ref/macro regressions for the newly
  classified required-lint surface;
- finish with one compile smoke command that proves warning-level findings can
  persist through the normal frontend build path without inventing a second
  artifact.
