# Lisp Frontend CLI And Diagnostics Surface Implementation Architecture

## Scope

This design gap covers only the bounded user-facing `.orc` compile/run/explain
surface selected for the Workflow Lisp frontend:

- add `orchestrate compile` support for `.orc` entrypoints, including
  deterministic build-root artifact emission;
- extend `orchestrate run` so `.orc` entrypoints compile through the existing
  frontend and execute through the existing runtime rather than a second
  executor;
- add `orchestrate explain` for expansion/lowering/source-trace inspection of
  `.orc` forms;
- emit machine-readable frontend diagnostics and a persisted source-trace
  artifact suitable for future lint/LSP tooling;
- bridge compiled frontend provenance into runtime observability so compiled
  runs can explain generated step ids in terms of authored `.orc` forms;
- support optional non-authoritative debug-YAML projection for validated
  compiled workflows.

Out of scope for this tranche:

- new language semantics, new frontend forms, or revisions to parsing,
  typing, macro expansion, phase stdlib, resource stdlib, or drain semantics;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, queue semantics, or runtime
  state persistence;
- editor/LSP implementation, background daemons, or persistent compile
  servers;
- runtime-native promotion of any command adapter or new command-boundary
  policy beyond reusing the existing certified-adapter contract;
- replacing YAML CLI behavior, the existing runtime executor, or the shared
  validation seam already used by the frontend.

This is an implementation architecture for the selected CLI/diagnostics gap
only. It does not replace the product design in
`docs/design/workflow_lisp_frontend_specification.md`.

## Design Constraints

The implementation must stay coherent with:

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
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/8/selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/8/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must also preserve the guardrails established by the earlier
implementation architectures and the current codebase:

- keep the frontend in `orchestrator/workflow_lisp/` and shared runtime
  semantics under `orchestrator/workflow/`;
- reuse the current staged pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation;
- reuse the existing authored-mapping ->
  `elaborate_surface_workflow(...)` ->
  `lower_surface_workflow(...)` shared seam rather than generating YAML text
  or adding a second validator;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep `command-result` and adapter-backed stdlib lowering under the existing
  command-boundary classification and certified-adapter contract;
- preserve the existing YAML CLI behavior and add `.orc` support as an
  additional entry surface, not a replacement path.

`docs/design/workflow_command_adapter_contract.md` is authoritative for this
slice because `compile`, `run`, and `explain` must surface existing
`command-result` boundaries and adapter metadata without weakening them. This
slice must not introduce:

- hidden semantic shell or Python glue in CLI command handlers;
- ad hoc report parsing to recover workflow meaning;
- opaque build helpers that normalize semantic state outside the typed
  frontend pipeline;
- debug-YAML generation that becomes an execution input or semantic authority.

The local `docs/steering.md` file is empty in this checkout. That is not
permission to broaden scope. The selector bundle, architecture target
contract, and prior implementation architecture set remain the effective local
steering surfaces for this work.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`

### Decisions Reused

- Reuse the existing frontend package ownership split instead of introducing a
  second Lisp compiler package.
- Reuse the current provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax objects,
  expansion stacks,
  `LispFrontendDiagnostic`,
  and `LoweringOriginMap`.
- Reuse `compile_stage1_module(...)`, `compile_stage3_module(...)`,
  `compile_stage1_entrypoint(...)`, and `compile_stage3_entrypoint(...)` as the
  compilation authority surfaces rather than adding a parallel compiler.
- Reuse Stage 3 and later command-boundary classification, extern binding, and
  shared-validation remapping rules unchanged.
- Reuse the current imported-bundle runtime call seam and loaded-bundle
  execution path rather than creating a `.orc`-only runtime transport.
- Reuse Stage 5 and Stage 6 lowering outputs exactly as compiled artifacts; the
  CLI layer does not reopen phase/resource/drain design.
- Reuse migration-era imported YAML bundles as valid explicit dependencies on
  the existing `imported_workflow_bundles` catalog surface rather than forcing
  `.orc` callers to inline or recompile every callee.

### New Decisions In This Slice

- Add a dedicated frontend build/artifact layer that wraps the existing
  frontend compiler results in a deterministic build manifest, emitted files,
  and source-trace sidecars.
- Add first-class CLI surfaces for `.orc`:
  `compile`,
  `.orc`-aware `run`,
  and `explain`,
  while preserving existing YAML commands and semantics.
- Introduce explicit entry-workflow selection for runnable `.orc` modules:
  CLI commands may infer the entry workflow only when the selected entry module
  exposes exactly one runnable workflow; otherwise the user must name it.
- Persist machine-readable diagnostics and source-trace data under the build
  root, then attach the selected trace bundle to runtime observability so
  generated step ids can be explained after compile time.
- Introduce an explicit imported-workflow-bundle manifest input surface for
  `compile`, `run`, and `explain` so the CLI/build layer can feed
  `compile_stage3_entrypoint(..., imported_workflow_bundles=...)` without
  hidden glue.
- Keep debug-YAML emission optional and strictly non-authoritative, generated
  only after shared validation succeeds.
- Use a manifest-status model for artifacts whose shared implementation
  contracts do not yet exist in the repo, instead of inventing fake Core AST or
  Semantic IR serializations.

### Conflicts Or Revisions

The full specification's Sections 76 and 79 describe build artifacts and
explain output in terms of:

- `core_workflow_ast.json`
- `semantic_ir.json`
- `explain` views over Core AST nodes and Semantic IR nodes

The current implementation substrate still compiles through:

- expanded frontend syntax;
- typed workflow/procedure definitions;
- lowered authored workflow mappings;
- shared validated `LoadedWorkflowBundle`;
- executable IR.

This slice therefore revises the implementation path narrowly:

- `compile` emits the artifacts the current codebase actually owns;
- the build manifest records `core_workflow_ast` and `semantic_ir` as deferred
  shared-contract artifacts instead of fabricating them;
- `explain` operates on the existing implemented surfaces:
  expansion provenance,
  typed callables,
  lowered authored mappings,
  validated surface bundle metadata,
  executable step ids,
  and persisted source-trace entries.

Reason:

- the repo does not yet expose a separately implemented, serializable Core AST
  or Semantic IR package for the frontend;
- faking those artifacts would weaken the "semantic authority is real
  structure" rule and create misleading tool contracts.

The full specification also shows `orchestrate run workflow.orc --input ...`
without an explicit workflow-selection flag. The current implementation now
supports multi-workflow modules and cross-module linking, so this slice makes
the selection rule explicit:

- infer the entry workflow only when the entry module exposes exactly one
  runnable workflow;
- otherwise require `--entry-workflow`.

This is an implementation-surface clarification, not a change to frontend
language semantics.

The debug-YAML design note says the renderer should consume Core AST or
Semantic IR plus source maps. Until those shared contracts exist in code, this
slice narrows the implementation bridge:

- the optional debug-YAML projection is emitted from the validated
  `LoadedWorkflowBundle.surface` plus the frontend source-trace sidecar;
- the output must identify itself as non-authoritative and temporary.

That is a bounded bridge choice only. It does not redefine shared concepts such
as spans, diagnostics, Core Workflow AST, Semantic Workflow IR, TypeCatalog,
SourceMap, pointer authority, or variant proof.

## Ownership Boundaries

This slice owns:

- CLI parser additions and command handlers for `.orc` compile/explain and
  `.orc`-aware run dispatch;
- entry-workflow selection and compile-request normalization for `.orc`
  entrypoints;
- deterministic build-root creation, artifact writing, and build-manifest
  emission for frontend compilation results;
- machine-readable serialization of existing frontend diagnostics and lowering
  provenance into a source-trace artifact;
- human-readable `explain` rendering over implemented frontend surfaces;
- optional non-authoritative debug-YAML projection after successful shared
  validation;
- the runtime observability bridge that makes compiled `.orc` step provenance
  visible in logs and persisted run artifacts;
- focused tests for CLI parsing, artifact emission, entry-workflow selection,
  diagnostic serialization, explain output, debug-YAML behavior, and runtime
  observability for compiled workflows.

This slice intentionally does not own:

- reader grammar, macro semantics, type checking, effect summaries, phase
  lowering, resource lowering, or drain lowering rules;
- shared runtime execution semantics, state persistence, queue transitions,
  provider execution, or prompt delivery;
- redesign of shared SourceMap, Core Workflow AST, Semantic Workflow IR, or
  TypeCatalog;
- LSP/editor integration, daemonized compilation, or generalized cache
  invalidation beyond the local build-root manifest;
- any change to certified-adapter input/output/effect contracts beyond
  surfacing them in build metadata and diagnostics.

## Proposed Package Boundary

Extend the current CLI and frontend packages with one bounded build/trace
layer and two CLI command handlers:

```text
orchestrator/
  cli/
    main.py
    commands/
      __init__.py
      run.py
      compile.py                 # new
      explain.py                 # new
  workflow_lisp/
    __init__.py
    build.py                     # new build request/result, manifest, artifact IO
    compiler.py                  # add CLI-facing entrypoint wrappers only
    diagnostics.py               # add JSON serialization helpers and severity mapping
    lowering.py                  # expose serializable lowering-origin/source-trace views
    workflows.py                 # add entry-workflow selection helpers
    debug_yaml.py                # new non-authoritative validated-surface projection
  workflow/
    surface_ast.py               # narrow provenance metadata extension
    loaded_bundle.py             # compatibility accessors for frontend provenance
    executor.py                  # source-form-aware runtime logging for compiled bundles
tests/
  test_workflow_lisp_cli.py      # new
  test_workflow_lisp_build_artifacts.py   # new
  test_workflow_lisp_diagnostics.py
  test_runtime_observability_cli.py
  fixtures/workflow_lisp/cli/    # new extern/boundary fixtures
```

Responsibilities:

- `workflow_lisp/build.py`
  - define build requests, build manifests, artifact indexes, and source-trace
    sidecars;
  - orchestrate compile -> validate -> artifact write without changing frontend
    semantics.
- `workflow_lisp/debug_yaml.py`
  - render validated surface bundles to YAML with explicit non-authoritative
    headers and optional source-trace comments or sidecar references;
  - never infer semantics from `.orc` text directly.
- `cli/commands/compile.py`
  - parse `.orc` compile inputs,
    invoke the build service,
    print a stable summary,
    and return deterministic exit codes.
- `cli/commands/explain.py`
  - load an existing build artifact set or compile one,
    resolve the requested form selector,
    and render explain output in text or JSON.
- `cli/commands/run.py`
  - preserve existing YAML handling;
  - route `.orc` paths through the build service and execute the validated
    loaded bundle selected by the entry-workflow rule.
- `workflow/surface_ast.py` and `workflow/loaded_bundle.py`
  - carry frontend provenance references without changing workflow semantics.
- `workflow/executor.py`
  - read persisted compiled-workflow provenance and log generated step ids with
    high-level source form context when available.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/effects.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/resource.py`
- `orchestrator/workflow_lisp/resource_stdlib.py`
- `orchestrator/workflow_lisp/drain_stdlib.py`
- shared validation/runtime modules under `orchestrator/workflow/`, except the
  narrow provenance transport and log-display additions listed above

## Data Model

### Compile Request And Entry Selection

Add frontend-local request records instead of passing raw CLI flags throughout
the compiler:

- `FrontendBuildRequest`
  - `source_path`
  - `source_roots`
  - `entry_workflow_name`
  - `provider_externs`
  - `prompt_externs`
  - `imported_workflow_bundle_manifest_path`
  - `imported_workflow_bundles`
  - `command_boundaries`
  - `workspace_root`
  - `emit_debug_yaml`
  - `validate_shared`
- `FrontendEntrySelection`
  - `module_name`
  - `workflow_name`
  - `selection_mode`:
    `explicit` or `single-export-inferred`
  - `span`
- `ImportedWorkflowBundleBinding`
  - `canonical_name`
  - `bundle_path`
  - `bundle_kind`:
    `yaml` or `compiled`
  - `resolved_workflow_name`
  - `bundle_fingerprint`
  - `provenance`

Imported workflow bundles stay explicit manifest-driven compile inputs. The CLI
does not guess them from import syntax or ambient workspace scans. The manifest
maps each canonical imported workflow key used by lowering, such as
`selector-run` or `<module>::<workflow>`, to one already materialized
`LoadedWorkflowBundle`. This keeps earlier module and migration slices intact:
migration-era imported YAML bundles remain valid dependencies, and compiled
frontend bundles may be mixed in when they expose the same typed call surface.

Selection rules:

- if `--entry-workflow` is provided, resolve it against the entry module's
  exported workflows;
- if omitted and the entry module exports exactly one runnable workflow, infer
  it deterministically;
- otherwise emit a dedicated frontend diagnostic rather than guessing.

This keeps multi-workflow and multi-module `.orc` repos runnable without
reopening the language surface.

### Build Fingerprint And Manifest

Build artifacts live under:

```text
.orchestrate/build/<fingerprint>/
```

`<fingerprint>` must be stable over:

- transitive entry-module source contents;
- resolved source-root set;
- selected entry-workflow name;
- provider-extern manifest contents;
- prompt-extern manifest contents;
- imported-workflow-bundle manifest contents, including canonical keys and
  resolved bundle provenance/fingerprints;
- command-boundary manifest contents;
- build schema version.

Define:

- `FrontendBuildManifest`
  - `schema_version`
  - `fingerprint`
  - `source_path`
  - `source_roots`
  - `entry_module`
  - `entry_workflow`
  - `imported_workflow_bundle_manifest_path`
  - `imported_workflow_bundles`
  - `compiled_module_names`
  - `validated_bundle_names`
  - `artifact_paths`
  - `artifact_status`
  - `diagnostic_count`
  - `shared_validation_status`
  - `debug_yaml_status`

`artifact_status` is required because this slice must not fake artifacts whose
shared contracts do not yet exist in code.

`imported_workflow_bundles` records the explicit dependency surface consumed by
the build:

- canonical import key;
- source manifest entry path;
- resolved bundle path;
- resolved workflow name;
- bundle kind (`yaml` or `compiled`);
- bundle fingerprint/checksum when available;
- load status or failure code.

This emitted manifest field is required so later `run`, `explain`, and review
work can audit imported call boundaries without reconstructing them from source
text.

### Artifact Set

Mandatory artifacts for successful `.orc` compilation in this slice:

- `manifest.json`
- `frontend_ast.json`
- `expanded_frontend_ast.json`
- `typed_frontend_ast.json`
- `lowered_workflows.json`
- `executable_ir.json`
- `source_map.json`
- `diagnostics.json`

Optional artifacts:

- `expanded.debug.yaml`

Manifest-declared but deferred artifacts:

- `core_workflow_ast`
- `semantic_ir`

Deferred artifacts must appear in `artifact_status` with a stable reason such
as `deferred_shared_contract`; they must not point at fabricated files.

### Diagnostic Envelope

Do not replace `LispFrontendDiagnostic`. Add serialization around it:

- `SerializedFrontendDiagnostic`
  - `code`
  - `severity`
  - `message`
  - `path`
  - `line`
  - `column`
  - `form_path`
  - `expansion_stack`
  - `notes`
  - `phase`:
    `read`,
    `syntax`,
    `typecheck`,
    `lowering`,
    `shared_validation`,
    or `cli_request`

Severity remains frontend-local metadata derived from stable code groups; the
diagnostic code remains the authoritative machine key.

### Source-Trace Artifact

This slice does not redefine the shared future `SourceMap`. It emits a
frontend build sidecar aligned to the current implementation substrate:

- `FrontendSourceTrace`
  - `schema_version`
  - `workflow_path`
  - `entry_workflow`
  - `workflow_origin`
  - `step_entries`
  - `generated_input_entries`
  - `generated_output_entries`
  - `generated_path_entries`

Each entry serializes the currently implemented lowering-origin fields:

- generated id
- authored span
- form path
- expansion stack
- notes

Coverage rules:

- every lowered workflow gets one workflow-origin entry;
- every generated step id written into authored mappings or executable IR gets
  one source-trace entry;
- every generated workflow-boundary input/output/path surface that can trigger
  shared-validation errors gets one source-trace entry.

This artifact is the compatibility bridge for Section 76.1 and Section 75. It
must be explicit that it covers the current lowering bridge, not a fully
implemented shared `SourceMap`.

### Runtime Provenance Bridge

Extend shared provenance narrowly with optional compiled-frontend metadata:

- `frontend_kind`: `"workflow_lisp"` when the loaded bundle comes from `.orc`
- `frontend_build_root`
- `frontend_source_trace_path`
- `frontend_entry_workflow`

These fields exist only to transport already-compiled provenance into runtime
logs and persisted run artifacts. They do not change workflow semantics,
validation, or call behavior.

## CLI Surface

### `orchestrate compile`

Add a new subcommand:

```bash
orchestrate compile workflow.orc \
  --entry-workflow run-selected-item \
  --source-root tests/fixtures/workflow_lisp/modules/valid/callables \
  --provider-externs-file externs/providers.json \
  --prompt-externs-file externs/prompts.json \
  --imported-workflow-bundles-file externs/imported-workflows.json \
  --command-boundaries-file externs/commands.json \
  --emit-debug-yaml
```

Required behavior:

- reject non-`.orc` inputs with a CLI-request diagnostic rather than silently
  invoking the YAML loader;
- load `--imported-workflow-bundles-file` as an explicit mapping from canonical
  import key to bundle path/provenance, then resolve those entries to
  `LoadedWorkflowBundle` values before compilation;
- compile through `compile_stage3_entrypoint(...)` with shared validation on by
  default and pass the resolved `imported_workflow_bundles` mapping through
  unchanged;
- emit the build manifest and artifact set under the deterministic build root;
- print a stable summary that includes:
  fingerprint,
  entry workflow,
  build root,
  imported bundle keys,
  emitted artifact paths,
  and diagnostic count.

### `orchestrate run`

Keep the existing YAML path unchanged. Add `.orc` dispatch only:

- if the `workflow` argument ends in `.orc`, route through the frontend build
  service first;
- execute the selected validated `LoadedWorkflowBundle` through the existing
  runtime executor;
- keep `--context`, `--context-file`, `--input`, `--input-file`,
  `--dry-run`, and observability flags working the same way after frontend
  compilation;
- add `.orc`-only compile inputs:
  `--entry-workflow`,
  `--source-root`,
  `--provider-externs-file`,
  `--prompt-externs-file`,
  `--imported-workflow-bundles-file`,
  `--command-boundaries-file`.

`--dry-run` on `.orc` means:

- compile;
- shared-validate;
- emit diagnostics/artifacts;
- run linting on the validated loaded bundle;
- do not create a runtime run directory or execute providers/commands.

### `orchestrate explain`

Add a new subcommand:

```bash
orchestrate explain workflow.orc \
  --form run-selected-item \
  --entry-workflow run-selected-item \
  --imported-workflow-bundles-file externs/imported-workflows.json
```

Required output:

- expansion frames touching the selected form;
- typed callable summary for the selected workflow/procedure/form;
- generated lowered workflow ids and step ids reachable from the form;
- executable node ids mapped from those step ids where available;
- source-trace entries showing authored span, form path, and notes.

Explain must not invent unavailable stages. When the manifest marks
`core_workflow_ast` or `semantic_ir` as deferred, the explain output should say
that explicitly instead of implying those artifacts exist.

## Compilation And Artifact Pipeline

The compile path for `.orc` entrypoints is:

```text
CLI request
  -> normalize extern/boundary/imported-bundle manifests
  -> resolve explicit imported workflow bundles
  -> compile_stage3_entrypoint(..., imported_workflow_bundles=...)
  -> select one entry workflow
  -> validate selected and imported bundles
  -> serialize artifacts + diagnostics + source trace
  -> optionally emit debug YAML
  -> return build manifest + selected loaded bundle
```

Implementation rules:

- CLI wrappers must not reimplement parsing, macro expansion, type checking, or
  lowering;
- the build layer may read compiler outputs and `LoadedWorkflowBundle`, but it
  must not mutate them;
- build artifact emission must happen after compilation succeeds far enough to
  produce the relevant surface;
- diagnostics from any phase must still be serializable, even when no validated
  bundle exists.

Artifact serialization boundaries:

- `frontend_ast.json`:
  syntax-elaborated module forms after read/syntax handling;
- `expanded_frontend_ast.json`:
  post-macro expanded forms;
- `typed_frontend_ast.json`:
  typed workflow/procedure/module view from Stage 3+;
- `lowered_workflows.json`:
  authored mapping plus generated ids for each lowered workflow;
- `executable_ir.json`:
  selected validated loaded-bundle executable nodes and topology;
- `source_map.json`:
  the frontend source-trace artifact described above.

## Debug-YAML Projection

Debug YAML stays optional and non-authoritative.

Rules:

- emit only when shared validation succeeds for the selected entry workflow;
- render from validated surface bundles plus the source-trace artifact, not
  from `.orc` text;
- write a top-of-file warning that the YAML is a debug projection and not a
  source of truth;
- keep it out of `run` execution inputs and ordinary workflow import surfaces.

The slice does not own golden-test stability for debug YAML beyond stable
ordering good enough for deterministic local inspection and CLI tests.

## Diagnostics And Observability

### Compile-Time Diagnostics

Preserve the current rendering path and add stable machine-readable output:

- text rendering remains `render_diagnostic(...)` /
  `render_diagnostics(...)`;
- JSON rendering is emitted to `diagnostics.json`;
- CLI stderr output for failed compile/explain/run requests must preserve
  authored path, line, column, form path, expansion notes, and any shared
  validation remap notes.

### Runtime Observability

When a compiled `.orc` workflow is executed:

- persist the selected build root and source-trace path into run metadata;
- make runtime logs capable of printing:
  generated step id,
  authored source file:line:column,
  and high-level form identifier when the trace entry exists;
- keep runtime execution order and state writes unchanged.

Minimum logging contract for compiled frontend runs:

```text
Running step %run_selected_item.resume_plan
  source: tests/fixtures/workflow_lisp/valid/neurips_selected_item.orc:42:5
  form: workflow-lisp > defworkflow > run-selected-item > resume-or-start
```

If a trace entry is missing, runtime behavior must continue and observability
falls back to the existing generated step id only; the compile artifact and
tests must still treat that as a defect in source-trace coverage.

## Integration Strategy

The slice should land in four ordered pieces:

1. build/artifact service and diagnostic serialization
2. `compile` and `.orc`-aware `run` wiring
3. `explain` command and source-trace serialization
4. runtime observability bridge and optional debug-YAML projection

This ordering keeps the CLI surface usable before the runtime log polish lands
and avoids coupling new command parsing to shared runtime changes.

## Test Strategy

### Frontend Unit And Artifact Tests

Add:

- `tests/test_workflow_lisp_build_artifacts.py`
  - manifest fingerprint stability
  - imported-workflow-bundle manifest entries and fingerprint participation
  - emitted artifact presence/absence rules
  - deferred-artifact status for `core_workflow_ast` and `semantic_ir`
  - source-trace coverage for lowered steps and generated boundary ids
- extend `tests/test_workflow_lisp_diagnostics.py`
  - diagnostic JSON serialization
  - CLI-request diagnostics for missing entry-workflow and missing extern files
  - shared-validation diagnostics preserved in JSON and text forms

### CLI Tests

Add:

- `tests/test_workflow_lisp_cli.py`
  - parser support for `compile` and `explain`
  - `.orc` dispatch in `run`
  - explicit versus inferred entry-workflow selection
  - imported-workflow-bundle manifest loading and missing-entry diagnostics
  - `.orc` dry-run behavior
  - compile failure exit codes and artifact-path reporting
  - explain output for workflow names and generated step ids

### Runtime Observability Tests

Extend:

- `tests/test_runtime_observability_cli.py`
  - compiled `.orc` run records frontend provenance in persisted run state
  - runtime logs/report snapshots include authored source context when the
    source-trace artifact is present

### Existing Regression Surface

Do not regress:

- `tests/test_workflow_lisp_workflows.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_resource_stdlib.py`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_cli_report_command.py`

## Acceptance Conditions

This slice is complete when:

- `orchestrate compile` can compile a valid `.orc` entrypoint, select one entry
  workflow deterministically, preserve explicit imported workflow bundle
  dependencies, and emit the documented build manifest and artifact set;
- `.orc` compilation failures produce stable text diagnostics and
  machine-readable `diagnostics.json`;
- `orchestrate run` preserves current YAML behavior and can execute a compiled
  `.orc` bundle through the existing runtime path while accepting the same
  imported-workflow-bundle manifest surface as `compile`;
- `orchestrate explain` can explain an authored form in terms of expansion,
  typed callables, lowered step ids, executable node ids, and source-trace
  entries, including imported workflow call targets selected through the
  explicit manifest surface;
- runtime observability for compiled `.orc` runs can map generated step ids
  back to authored source context when the trace entry exists;
- optional debug YAML is emitted only as an explicitly marked,
  non-authoritative projection;
- no new hidden command semantics or adapter-policy bypasses are introduced.

## Verification Plan

Deterministic verification for the eventual implementation should include at
least:

- `pytest --collect-only` on the new CLI/build test modules;
- focused pytest runs for CLI parsing/dispatch and build artifacts;
- focused pytest runs for diagnostic serialization and runtime observability;
- one `.orc` compile smoke through the real CLI using fixture extern manifests
  and an imported-workflow-bundle manifest;
- one `.orc` dry-run smoke through the real CLI to prove compile -> validate ->
  lint -> no execution behavior across the same imported-bundle path;
- one `.orc` explain smoke through the real CLI using the same deterministic
  fixture set so `explain` is not verified only indirectly through unit tests.

The exact command list for implementation handoff is recorded in:

- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/8/design-gap-architect/check_commands.json`
