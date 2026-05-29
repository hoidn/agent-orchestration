# Frontend CLI Artifact Emission Implementation Architecture

## Scope

This design gap covers only the bounded user-facing artifact-emission contract
for the existing Workflow Lisp CLI surfaces:

- define one explicit CLI export contract for `orchestrate compile` and
  `orchestrate explain` covering:
  `core_workflow_ast.json`,
  `semantic_ir.json`,
  `source_map.json`,
  and non-authoritative debug YAML;
- keep the existing deterministic build-root artifact set as the canonical
  compiled output and layer explicit user-requested exports on top of it;
- replace the current boolean `--emit-debug-yaml` surface with a path-capable
  export contract;
- make `compile` and `explain` report explicit emitted-export results instead
  of only relying on implicit build-root summaries or console rendering;
- preserve the current frontend compiler, shared validation, shared Core AST,
  shared Semantic IR, runtime-plan, and explain-selection behavior.

Out of scope for this tranche:

- new Workflow Lisp language forms, new stdlib forms, or revisions to parsing,
  typing, macros, procedures, workflow refs, phase/resource/drain lowering, or
  runtime execution behavior;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, or runtime observability;
- changing the deterministic build-root artifact set, build fingerprint model,
  or shared artifact serializers beyond what is required to support explicit
  CLI export requests;
- adding new command adapters, legacy adapters, report parsing, pointer-as-
  state recovery, or runtime-native effect promotion;
- replacing the older full CLI surface architecture in
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
  with a second general CLI redesign.

This is an implementation architecture for exactly the selected
`frontend-cli-artifact-emission` gap. It does not reopen the rest of the
frontend CLI, compiler, or runtime design.

## Design Constraints

The implementation must stay coherent with:

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
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/5/selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/5/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/5/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must also preserve the guardrails established by prior
implementation-architecture documents and the current checkout:

- keep `orchestrator/workflow_lisp/` frontend-owned and keep shared workflow
  meaning under `orchestrator/workflow/`;
- reuse the existing staged path:
  read -> syntax -> expansion -> typing -> lowering -> shared validation ->
  Core AST / Semantic IR / executable bundle emission;
- keep the deterministic build-root artifact bundle as the canonical compiled
  output instead of moving artifact authority into ad hoc CLI export paths;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep explain output derived from real compiled artifacts and persisted source
  lineage, not reconstructed from console text;
- keep command boundaries on the existing `external_tool` versus
  `certified_adapter` contract and surface only declared command-boundary
  metadata.

`docs/design/workflow_command_adapter_contract.md` is authoritative here
because the CLI/export layer must transport already-declared command-boundary
artifacts and explain surfaces without introducing new opaque helper scripts,
inline shell glue, or report parsing. This slice must not introduce:

- hidden Python or shell export helpers that decide workflow meaning;
- ad hoc reconstruction of Core AST, Semantic IR, or source maps from console
  output;
- debug YAML becoming an execution input or semantic authority;
- export behavior that obscures certified command-adapter provenance already
  carried by the canonical compiled artifacts.

`docs/steering.md` is empty in this checkout. That does not widen scope. The
selector bundle, architecture target contract, prior implementation
architectures, and current repo evidence remain the effective local steering
surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/core-workflow-ast-shared-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defun-pure-helper-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-required-lints/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resume-or-start-reusable-state-validation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/semantic-workflow-ir-shared-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the current package ownership split between `orchestrator/cli/` and
  `orchestrator/workflow_lisp/`.
- Reuse the deterministic build-root artifact model from the existing frontend
  build service instead of inventing a second compilation output location.
- Reuse the real shared artifacts already implemented in the current checkout:
  `core_workflow_ast.json`,
  `semantic_ir.json`,
  `runtime_plan.json`,
  and `source_map.json`.
- Reuse explain selection over compiled workflows, procedures, and imported
  call targets without redefining explain subject resolution.
- Reuse the current source-map/runtime-lineage rule that emitted provenance
  must come from persisted compiled artifacts rather than string matching or
  stdout parsing.
- Reuse the command-boundary manifest and certified-adapter metadata as
  already-declared inputs to compilation and explain surfaces.

### New Decisions In This Slice

- Introduce one explicit CLI artifact-export request contract for `compile`
  and `explain` that is separate from the canonical build-root artifact set.
- Treat user-requested exports as projections or copies of canonical compiled
  artifacts, not as new semantic authority surfaces.
- Support path-capable export requests for:
  `core_workflow_ast`,
  `semantic_ir`,
  `source_map`,
  and debug YAML,
  with one shared normalization and emission helper reused by both commands.
- Keep explain console output selection-scoped, but make artifact exports
  compilation-scoped: a selected procedure or imported workflow still exports
  the canonical artifacts for the compiled entrypoint build, not an invented
  partial Core AST or partial Semantic IR schema.
- Keep build manifests authoritative only for canonical build-root artifacts;
  do not record machine-local ad hoc export destinations in the persisted
  manifest.

### Conflicts Or Revisions

The older CLI/diagnostics architecture assumed:

- `core_workflow_ast` and `semantic_ir` could still be deferred;
- `--emit-debug-yaml` was a boolean compile-only flag;
- explain primarily exposed console-readable provenance and deferred-artifact
  notes.

The current checkout has since implemented real Core AST and Semantic IR
artifacts under the build root and explain already prints both surfaces. This
slice revises the remaining CLI contract narrowly:

- artifact generation is no longer the missing piece;
- explicit user-facing artifact export is the missing piece;
- the new contract sits on top of existing build artifacts instead of changing
  how those artifacts are authored or validated.

The selector rationale still correctly identifies a CLI-surface mismatch, but
its checkout claim is now narrower than "artifacts do not exist":

- `compile` already emits the canonical files under the build root;
- `compile` still lacks explicit `--emit-core-ast`,
  `--emit-semantic-ir`,
  and `--emit-source-map` request surfaces;
- `explain` still lacks a matching export contract;
- `--emit-debug-yaml` still uses a boolean switch instead of a path-addressable
  destination.

No prior slice is revised on shared concepts such as spans, diagnostics, Core
Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority,
or variant proof.

## Ownership Boundaries

This slice owns:

- CLI flag parsing for explicit artifact export requests on `compile` and
  `explain`;
- one frontend-local export request model and path-normalization helper;
- one emission helper that copies or renders already-built canonical artifacts
  to user-requested destinations;
- compile/explain user-visible summaries of requested and emitted exports;
- focused CLI/build tests for export parsing, export-path defaults, debug-YAML
  path handling, and failure behavior.

This slice intentionally does not own:

- Core AST generation or serialization logic in
  `orchestrator/workflow/core_ast.py`;
- Semantic IR generation or serialization logic in
  `orchestrator/workflow/semantic_ir.py`;
- source-map schema design beyond reusing the existing emitted `source_map.json`
  artifact;
- workflow compilation, lowering, validation, imported-bundle linking, or
  explain subject resolution;
- runtime execution, runtime observability, or command-boundary semantics.

## Current Checkout Facts

- `orchestrator/workflow_lisp/build.py` already emits canonical build-root
  artifacts including:
  `core_workflow_ast.json`,
  `semantic_ir.json`,
  `runtime_plan.json`,
  and `source_map.json`.
- `orchestrator/cli/main.py` currently exposes:
  `--entry-workflow`,
  `--source-root`,
  extern manifests,
  imported-bundle manifests,
  command-boundary manifests,
  and a boolean `--emit-debug-yaml` only on `compile`.
- `orchestrator/cli/commands/compile.py` currently prints a JSON summary with
  `artifact_paths`, but it does not accept explicit export requests for Core
  AST, Semantic IR, or source maps.
- `orchestrator/cli/commands/explain.py` currently prints Core AST, Semantic
  IR, and source-trace payloads to stdout, but it does not offer explicit file
  emission for those compiled artifacts.
- `tests/test_workflow_lisp_build_artifacts.py` already verifies the canonical
  build artifacts exist, and `tests/test_workflow_lisp_cli.py` already covers
  compile/explain parsing and explain rendering.

## Architecture

### Canonical Versus Exported Artifacts

This slice keeps a strict two-layer model:

1. Canonical compiled artifacts
   These remain under the deterministic build root and are the authoritative
   compiled outputs referenced by the build manifest.

2. User-requested exported artifacts
   These are convenience copies or projections written to caller-selected
   paths. They never replace build-root artifacts, they are not referenced by
   imported-workflow manifests, and they must not affect execution semantics.

This preserves deterministic compilation while satisfying the full design's
user-facing CLI contract.

### CLI Request Surface

Both `orchestrate compile` and `orchestrate explain` gain one shared export
surface:

```text
--emit-core-ast [PATH]
--emit-semantic-ir [PATH]
--emit-source-map [PATH]
--emit-debug-yaml [PATH]
```

Rules:

- the flag name selects one canonical artifact kind;
- the optional argument is a destination path;
- if the flag is present without a path, the command writes to a stable default
  file in the current working directory using the canonical filename:
  `core_workflow_ast.json`,
  `semantic_ir.json`,
  `source_map.json`,
  or `expanded.debug.yaml`;
- `--emit-debug-yaml` remains valid only when the command has a validated
  workflow bundle available to render;
- YAML workflows do not gain this surface in this slice.

The user-facing contract stays simple while still satisfying the full-design
examples that show flag-style compile emission.

### Shared Export Request Model

Add one frontend-local export request model owned by the CLI/build seam.

Required fields:

- artifact kind
- requested destination, if any
- resolved destination path
- whether the artifact comes from an existing canonical file or from the debug
  YAML renderer

Normalization rules:

- resolve explicit destinations relative to the process working directory;
- create parent directories as needed;
- reject destinations that point at directories;
- treat repeated requests for the same artifact kind as a CLI-request error;
- keep all destination handling outside fingerprinting and build-manifest
  determinism.

This model belongs in the frontend build/export layer, not in shared workflow
semantics.

### Compile Flow

`compile` keeps its existing build behavior:

```text
parse request
  -> build canonical frontend bundle under deterministic build root
  -> optionally render canonical build-root debug YAML
  -> export requested artifacts to caller-visible destinations
  -> print JSON summary
```

Changes in this slice:

- artifact export happens after canonical build artifacts exist;
- the compile summary adds an `exported_artifacts` map separate from the
  canonical `artifact_paths` map;
- if no explicit export flags are passed, current behavior stays unchanged
  except for the new path-capable `--emit-debug-yaml` parsing contract.

No export should happen when compilation or shared validation fails.

### Explain Flow

`explain` keeps its existing subject-selection and console-rendering behavior,
then optionally exports canonical compiled artifacts:

```text
parse request
  -> build canonical frontend bundle under deterministic build root
  -> select one explain subject
  -> print explain payloads for that subject
  -> export requested canonical artifacts for the compiled build
```

Important rule:

- explain exports are compilation-scoped, not subject-scoped.

Reason:

- the repo already owns canonical module/build artifacts for Core AST,
  Semantic IR, and source maps;
- the repo does not own a separate durable schema for "partial Core AST of one
  procedure" or "partial Semantic IR for one imported target";
- inventing such schemas would broaden the slice and risk a second authority
  surface.

If export flags are used, explain should print a short emitted-path summary
after the normal explain content.

### Debug-YAML Contract

Debug YAML stays optional and non-authoritative.

New behavior:

- `--emit-debug-yaml` becomes path-capable on `compile` and `explain`;
- the canonical build-root `expanded.debug.yaml` may still be produced when
  requested as part of canonical build output handling;
- exported debug YAML is a copy of the canonical rendered file, not a second
  render with potentially diverging options.

Rules preserved from prior slices:

- render only from validated compiled artifacts plus persisted source lineage;
- write a clear top-of-file warning that the YAML is a debug projection;
- never use debug YAML as execution input, import input, or semantic authority.

### Failure And Overwrite Semantics

Artifact export failure is a CLI/export-layer failure, not a workflow semantic
failure.

Rules:

- compilation/validation errors still surface as frontend diagnostics first;
- if canonical compilation succeeds but an export copy fails, the command exits
  nonzero and reports which requested export failed;
- partial user-visible exports are allowed only when earlier requested exports
  already completed successfully, but the canonical build root remains valid;
- the command must not delete the canonical build root just because an external
  export path failed.

This keeps semantic compilation evidence durable even when a user-selected copy
destination is bad.

### Persisted Versus Ephemeral Metadata

The persisted manifest continues to describe only canonical build-root
artifacts.

Do not add user-selected export destinations to `manifest.json` because:

- they are machine-local and nondeterministic;
- they are not needed to reload or import a compiled workflow bundle;
- they would blur the difference between canonical artifacts and convenience
  exports.

Instead:

- `compile` returns exported paths in its JSON summary;
- `explain` prints exported paths when requested;
- tests assert those command outputs directly.

### Files And Components

Expected owned implementation files:

- `orchestrator/cli/main.py`
- `orchestrator/cli/commands/compile.py`
- `orchestrator/cli/commands/explain.py`
- `orchestrator/workflow_lisp/build.py`
- focused CLI/build tests in:
  `tests/test_workflow_lisp_cli.py`
  and `tests/test_workflow_lisp_build_artifacts.py`

Shared components intentionally reused without redesign:

- `orchestrator/workflow/core_ast.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/lowering.py`

## Verification Strategy

Keep verification narrow and deterministic:

- parser/CLI tests for the new optional-path emit flags;
- compile-command tests that prove `exported_artifacts` paths are reported and
  the copied files match canonical build-root artifacts;
- explain-command tests that prove export flags work without changing explain
  selection semantics;
- debug-YAML tests that prove path-addressable emission replaces the boolean
  contract without changing non-authoritative status;
- failure-path tests for duplicate emit flags, directory destinations, and
  failed copy destinations.

No orchestrator runtime smoke check is required for this slice because it does
not change execution behavior, workflow semantics, or run-state contracts.

## Implementation Notes

- keep the older build-root artifact set intact to avoid churn in prior slices
  and tests;
- add the explicit export contract as a thin layer over existing artifact paths
  rather than teaching CLI handlers to reserialize Core AST, Semantic IR, or
  source maps themselves;
- keep emitted export bytes identical to canonical artifact bytes whenever the
  artifact already exists on disk;
- keep command-boundary manifests and adapter metadata observable through the
  exported canonical artifacts, never through extra ad hoc helper output.
