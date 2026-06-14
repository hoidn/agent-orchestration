# Workflow Lisp Private Runtime Value Flow C2 Observability-Derived Human Summaries Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-private-runtime-state-and-consumer-value-flow-c2-observability-derived-human-summaries`
Target design: `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected C2 gap:

- generate human/operator summaries for the Design Delta parent-drain family
  from typed terminal values and transition audit evidence;
- expose those summaries through existing report and dashboard observability
  surfaces under the run summary hub;
- prove that summary files and summary payloads are observability artifacts
  only and are never consumed for workflow routing, retry, assertions, status
  reconciliation, parity semantic output, or provider/command output authority;
- consume C0 rows whose `consumer_lane` is `human_observability` or whose
  `track_c_decision` is `RETIRE_TO_OBSERVABILITY`;
- provide dual-run comparison against old summary writer behavior before any
  later slice retires that behavior; and
- emit machine-readable C2 evidence that later C3-C5 slices can consume without
  claiming entrypoint publication, compatibility bridge metadata, or durable
  rendering cleanup behavior.

Out of scope for this slice:

- adding entrypoint `:publish` syntax or terminal-boundary publication
  lowering;
- generating compatibility bridge files from metadata or deleting bridge files;
- deleting existing body-level `materialize-view` calls, summary writer
  adapters, public output fields, or bridge files;
- changing workflow routing, retry, `match`, `if`, `assert`, status
  reconciliation, provider structured-output target binding, or command bundle
  validation;
- changing renderer byte formats used by `materialize-view` or prompt-input
  rendering;
- adding scripts, inline Python/shell, command steps, or certified adapters for
  summary derivation;
- changing checkpoint schema, restore behavior, effect-boundary policies,
  transition-aware resume, or default-resume selection; and
- redefining Core Workflow AST, Semantic Workflow IR, Executable IR,
  TypeCatalog, SourceMap, pointer authority, variant proof, provider output
  authority, command-adapter policy, or transition semantics.

This is an implementation architecture for one Track C behavior slice. It is
not a replacement product design and it does not complete C3, C4, or C5.

## Problem Statement

C0 classified render-only surfaces and proved renderer seams. C1 added typed
prompt-input rendering. The selected gap is the next consumer lane:
human/operator summaries should come from typed values and transition audit at
the observability seam, not from producer-owned summary paths or summary writer
commands embedded in the workflow body.

The current checkout already has observability surfaces:

1. `orchestrator.observability.report` builds deterministic status snapshots
   from `state.json`, loaded workflow projections, step outputs, and run
   metadata.
2. `orchestrator.observability.summary.SummaryObserver` writes
   `RUN_ROOT/summaries/index.json`, `README.md`, and `run-summary.md`, but its
   summaries are step/provider snapshots and optional agent prose rather than
   typed terminal-value summaries.
3. `orchestrator/dashboard/server.py` serves the summary hub and live summary
   payloads from `RUN_ROOT/summaries/` and request-time run state.
4. C0 rows such as
   `c0.drain_summary_report_target_final_summary_view` already classify legacy
   summary report targets as `human_observability` and
   `RETIRE_TO_OBSERVABILITY`.
5. Resource transitions already record audit evidence, but report/dashboard
   surfaces do not yet derive a family-level human summary from terminal typed
   result plus transition audit rows.

C2 should add an observability-only derivation layer over those existing
surfaces. It should not move publication to workflow entry boundaries, generate
legacy bridges, or treat summaries as typed semantic inputs.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`
  Sections 7.2, 8, 10 C2, 11, 12, 13, 14, 15, 16.4, and 17;
- `docs/design/workflow_lisp_frontend_specification.md` Sections 17, 18,
  18.1, 19.2, 20, 47, 48, 59, 62, 65, 66, 74, 75, 76.1, and 78.1;
- `specs/observability.md` for the normative rule that summary files, summary
  indexes, `README.md`, and `run-summary.md` are observability artifacts only
  and must not drive routing, retries, assertions, or status reconciliation;
- `docs/design/workflow_command_adapter_contract.md` for the rule that summary
  derivation must not be implemented as hidden command glue, report parsing, or
  uncertified scripts;
- `docs/design/workflow_lisp_state_layout.md` for generated path allocation
  ownership, which this slice does not widen;
- `docs/design/workflow_lisp_runtime_migration_foundation.md` for private
  value transport and fail-closed structured-output behavior;
- the U0 shared-census architecture;
- the C0 rendering-census architecture and checked C0 manifest/report;
- the C1 typed-prompt architecture and reports, as adjacent Track C context;
- the R1 through R6 implementation architectures as completed Track R context
  that C2 must not reopen; and
- `docs/index.md`, `docs/design/README.md`, and
  `docs/capability_status_matrix.md` for routing and current capability
  status.

Guardrails:

- Typed terminal values, structured bundles, resources, and transition audit
  remain semantic authority.
- Observability summaries are derived views. They are not workflow artifacts,
  public workflow outputs, typed semantic inputs, checkpoint data, parity
  semantic output, or provider/command output evidence.
- C2 eligibility starts from checked C0 rows. Do not infer retirement or
  summary ownership from field names alone.
- Report/dashboard summary rendering may read typed terminal values from
  `state.workflow_outputs`, step output outcomes, compiled workflow output
  projections, and transition audit evidence. It must not parse old summary
  Markdown to recover status, variants, blocker classes, or routing decisions.
- Existing `orchestrate report` self-healing behavior for stale running status
  must not be expanded. Dashboard routes remain read-only and pure.
- Summary generation may be deterministic and local. If optional agent-written
  narrative remains enabled through existing `SummaryObserver` profiles, it is
  advisory prose over the deterministic snapshot and not the C2 authority
  surface.
- The empty `docs/steering.md` file in this checkout does not widen scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-u0-shared-census/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-c0-rendering-census-and-renderer-seam-verification/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-c1-typed-values-as-prompt-inputs/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r1-checkpoint-schema-shadow-emission/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r2-restore-for-pure-and-structured-regions/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r3-effect-boundary-resume-policies/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r4-transition-aware-resume/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r5-resume-only-authored-plumbing-retirement/implementation_architecture.md`
- `docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/workflow-lisp-private-runtime-state-and-consumer-value-flow-r6-default-flip-and-legacy-cleanup/implementation_architecture.md`

### Decisions Reused

- Reuse U0's checked value-flow census as the inventory authority for
  render-only path plumbing.
- Reuse C0's `workflow_lisp_consumer_rendering_census.v1` rows to identify
  human-observability candidates. C2 does not create a second primary census.
- Reuse C0 consumer lanes and durability classes. C2 selects rows where
  `consumer_lane == "human_observability"` or
  `track_c_decision == "RETIRE_TO_OBSERVABILITY"`.
- Reuse `orchestrator/workflow_lisp/consumer_rendering_census.py` and its C0
  report as prerequisite evidence.
- Reuse `orchestrator.workflow.view_renderer` for deterministic value-to-bytes
  primitives where canonical JSON or path-line evidence is needed, but do not
  change materialize-view renderer contracts in this slice.
- Reuse existing report/dashboard observability surfaces:
  `build_status_snapshot`, `render_status_markdown`,
  `SummaryObserver` summary-index generation, and dashboard summary-hub routes.
- Reuse transition audit as the durable mutation evidence. C2 reads audit facts
  for summary display; it does not own transition execution, idempotency,
  replay, conflict detection, or audit format.
- Reuse C1's typed prompt-input evidence as adjacent prompt-rendering evidence
  only. Prompt evidence is not a human summary and is not C2 completion
  evidence.
- Reuse R1-R6 checkpoint/resume decisions by leaving checkpoint reports,
  default-resume policy, and resume-only cleanup untouched.
- Reuse the command-adapter contract by keeping C2 summary derivation out of
  command steps and adapter scripts.

### New Decisions In This Slice

- Add a C2 summary derivation schema:
  `workflow_lisp_observability_summary.v1`.
- Add a C2 evidence/report schema:
  `workflow_lisp_observability_summary_report.v1`.
- Add one observability helper module, proposed
  `orchestrator/workflow_lisp/observability_summaries.py`, that selects C0
  rows, normalizes typed terminal values, reads transition audit facts, renders
  deterministic summary payloads, and validates that outputs remain
  observability-only.
- Add a deterministic terminal summary artifact under `RUN_ROOT/summaries/`,
  proposed `typed-terminal-summary.json` plus
  `typed-terminal-summary.md`. These files are run-local observability
  artifacts and are not published through workflow artifact lineage.
- Add summary-index entries with `kind: "typed_terminal"` and explicit
  `authority: "observability_only"`.
- Add a report/dashboard projection that includes links and previews for C2
  summaries without parsing their prose as workflow state.
- Add a dual-run comparison lane for old summary writer behavior. The
  comparison checks that old summary writer outputs remain representationally
  comparable to the typed terminal summary before later retirement; it does not
  delete the old writer.

### Conflicts Or Revisions

C0 left `human_observability` rows as classification and prerequisite evidence
only. C2 consumes those rows and implements the observability rendering lane.
That is an additive continuation of C0, not a replacement of its census schema.

C1 implemented prompt-seam rendering and intentionally left C2 out of scope.
C2 does not reuse prompt evidence as human-summary evidence and does not change
provider prompt composition.

Existing `SummaryObserver` can call a provider to draft advisory prose. C2 does
not remove that feature, but it introduces a deterministic typed-summary
payload as the authority for this slice's evidence. Provider-authored summary
prose remains optional and advisory.

No R1-R6 checkpoint/resume decision is revised. No shared concepts are
redefined. Core Workflow AST, Semantic Workflow IR, Executable IR, TypeCatalog,
SourceMap, pointer authority, variant proof, provider/command output
authority, command-adapter policy, and resource-transition semantics remain
owned by their existing documents and modules.

## Ownership Boundaries

This slice owns:

- a C2 helper module, proposed
  `orchestrator/workflow_lisp/observability_summaries.py`, for schema
  constants, row selection from C0, terminal-value normalization, transition
  audit projection, deterministic Markdown/JSON rendering, report construction,
  and diagnostics;
- additive integration in `orchestrator/observability/report.py` so
  `build_status_snapshot` can expose a typed terminal summary block when C2
  evidence exists or can be derived;
- additive integration in `orchestrator/observability/summary.py` so the run
  summary hub can include deterministic typed terminal summaries and index
  entries;
- additive dashboard integration in `orchestrator/dashboard/server.py` so the
  existing summary hub can display C2 summaries and their evidence links;
- build or run-artifact integration that joins C0 human-observability rows with
  compiled Design Delta outputs and emits
  `observability_summary_report.json`;
- optional dual-run comparison helpers for old summary writer outputs versus
  typed terminal summary payloads;
- diagnostics for missing C0 rows, missing terminal values, missing or
  unreadable transition audit evidence, summary-as-state violations, missing
  source-map lineage, stale old-writer comparisons, and route/dashboard
  mutation attempts; and
- focused tests for schema validation, deterministic rendering, report
  integration, dashboard read-only behavior, dual-run comparison, and negative
  authority cases.

This slice intentionally does not own:

- renderer byte format changes for `materialize-view` or typed prompt inputs;
- entrypoint `:publish` syntax or publication lowering;
- compatibility bridge metadata, bridge generation, or bridge deletion;
- body-level `materialize-view` retirement;
- command-adapter certification, command-boundary manifests, adapter
  execution, or adapter retirement status changes;
- provider/command structured-output validation internals;
- transition execution, audit append semantics, idempotency, replay, conflict
  detection, or resource state storage;
- checkpoint schema, checkpoint restore, effect policies, transition-aware
  resume, default-resume selection, or resume-only cleanup;
- migration promotion thresholds or primary-surface selection; or
- shared Core Workflow AST, Semantic Workflow IR, Executable IR, TypeCatalog,
  SourceMap, pointer authority, or variant-proof semantics.

## Proposed Data Model

### Observability Summary Payload

Add one deterministic run-local JSON payload:

```text
RUN_ROOT/summaries/typed-terminal-summary.json
```

Top-level shape:

```json
{
  "schema_version": "workflow_lisp_observability_summary.v1",
  "authority": "observability_only",
  "target_family": "lisp_frontend_design_delta_parent_drain",
  "workflow_name": "lisp_frontend_design_delta/drain::drain",
  "run_id": "20260614T000000Z-example",
  "terminal_value": {
    "source": "state.workflow_outputs",
    "type_name": "DrainResult",
    "variant": "DONE",
    "value_digest": "sha256:...",
    "value": {}
  },
  "transition_audit": {
    "rows": [],
    "audit_digests": []
  },
  "c0_rows": [
    {
      "c0_row_id": "c0.drain_summary_report_target_final_summary_view",
      "u0_row_id": "drain.summary_report_target.final_summary_view",
      "consumer_lane": "human_observability",
      "track_c_decision": "RETIRE_TO_OBSERVABILITY"
    }
  ],
  "source_map": {
    "origin_keys": []
  },
  "rendered_markdown_path": "summaries/typed-terminal-summary.md"
}
```

The `terminal_value.value` field is the normalized typed value that the runtime
already persisted as workflow output or an equivalent validated terminal
projection. The `value_digest` is deterministic and is used only for evidence
matching and drift detection.

### Markdown Summary View

Add one deterministic Markdown view:

```text
RUN_ROOT/summaries/typed-terminal-summary.md
```

It is generated from the JSON payload above. It should include:

- workflow and run identity;
- terminal variant/status;
- selected scalar fields from the terminal value;
- transition count and latest relevant transition outcomes;
- links to old summary writer outputs or compatibility views when present; and
- an explicit sentence that the file is observability-only.

The Markdown file is not parsed by the runtime. If the dashboard needs facts, it
reads the JSON payload and run state, not the Markdown prose.

### Summary Index Entry

Add entries to `RUN_ROOT/summaries/index.json` using the existing summary hub:

```json
{
  "step_name": "workflow-terminal",
  "kind": "typed_terminal",
  "profile": "workflow-lisp-c2",
  "status": "completed",
  "summary_path": "summaries/typed-terminal-summary.md",
  "snapshot_path": "summaries/typed-terminal-summary.json",
  "error_path": null,
  "authority": "observability_only",
  "source": {
    "terminal_value": "state.workflow_outputs",
    "transition_audit": "runtime_transition_audit"
  }
}
```

The summary hub may render this entry like any other summary entry, but routes
must not use it to change status, retry behavior, or workflow outputs.

### Observability Summary Report

Emit a build/runtime evidence report:

```text
.orchestrate/build/<hash>/observability_summary_report.json
```

or, for runtime-only evidence:

```text
RUN_ROOT/summaries/observability_summary_report.json
```

Top-level shape:

```json
{
  "schema_version": "workflow_lisp_observability_summary_report.v1",
  "status": "pass",
  "target_family": "lisp_frontend_design_delta_parent_drain",
  "source_census": {},
  "consumer_rendering_census": {},
  "selected_c0_rows": [],
  "terminal_value_sources": [],
  "transition_audit_sources": [],
  "summary_artifacts": [],
  "old_writer_comparisons": [],
  "authority_checks": [],
  "diagnostics": []
}
```

The report fails when:

- a selected C0 `human_observability` row has no matching terminal-value source
  or summary evidence;
- a row marked `RETIRE_TO_OBSERVABILITY` still has no dual-run comparison plan
  for old summary writer behavior;
- the summary renderer attempts to read old summary prose as semantic input;
- a summary path is exposed as a workflow output or artifact lineage value;
- a dashboard or report route mutates `state.json` while rendering C2 summary
  content; or
- C2 evidence is used as migration semantic parity output rather than
  observability evidence.

## Derivation Flow

1. C2 eligibility starts from the checked C0 report. Select rows with
   `consumer_lane: human_observability` and rows with
   `track_c_decision: RETIRE_TO_OBSERVABILITY`.
2. Resolve the terminal typed value from `state.workflow_outputs` when present.
   For focused fixtures that expose terminal values through step outcomes, use
   the compiled workflow output projection to find the equivalent validated
   terminal value.
3. Read transition audit facts only through existing transition/audit helper
   APIs or checked audit paths already recorded by runtime evidence. Do not
   infer resource state by parsing summary Markdown or pointer files.
4. Normalize the terminal value and transition audit projection into one
   deterministic JSON document.
5. Render Markdown from the JSON document with a local deterministic renderer
   in the C2 helper. The renderer has no filesystem reads beyond explicit input
   payloads and no provider or command calls.
6. Write the JSON and Markdown under `RUN_ROOT/summaries/` and append one
   `typed_terminal` entry to the existing summary index.
7. `orchestrate report` may include the typed terminal summary payload or a
   link to it. Dashboard summary routes may preview it and expose the JSON
   payload. Both remain observability views.
8. Emit `observability_summary_report.json` with selected rows, source
   digests, summary paths, dual-run comparison status, and authority checks.

If a run has no terminal typed value yet, C2 may emit a pending diagnostic or
skip the terminal summary. It must not create a synthetic workflow outcome from
partial step summaries.

## Old Summary Writer Comparison

C2 does not retire old summary writers. It adds comparison evidence so a later
slice can safely retire them.

Comparison input:

- the typed terminal summary JSON payload;
- old summary writer output paths listed by C0 rows or existing view dual-run
  vectors;
- renderer id/version or file-shape metadata from C0; and
- source-map or manifest lineage for the row being compared.

Comparison output:

```json
{
  "comparison_id": "drain-summary-old-writer-vs-typed-terminal",
  "c0_row_id": "c0.drain_summary_report_target_final_summary_view",
  "old_writer_path": "artifacts/work/drain_summary.json",
  "typed_summary_digest": "sha256:...",
  "old_writer_digest": "sha256:...",
  "comparison_status": "non_regressive",
  "accepted_differences": [
    "formatting",
    "observability_only_header"
  ]
}
```

The comparison is evidence for later retirement only. It is not a workflow
decision, a public artifact, or a semantic parity replacement for typed output.

## Report And Dashboard Integration

### `orchestrate report`

`orchestrator.observability.report.build_status_snapshot` may expose a
`run.observability_summaries` block:

```json
{
  "typed_terminal": {
    "status": "available",
    "summary_path": "summaries/typed-terminal-summary.md",
    "payload_path": "summaries/typed-terminal-summary.json",
    "authority": "observability_only"
  }
}
```

`render_status_markdown` may link to that summary and include a short factual
preview derived from the JSON payload. It must not parse the Markdown file to
determine run status or outputs.

The existing report command's stale-running self-heal path remains unchanged.
C2 summary rendering must not add new self-healing conditions.

### Dashboard

The dashboard summary hub may:

- show a "Typed Terminal Summary" section when C2 JSON exists;
- preview the deterministic Markdown view;
- link to selected transition-audit evidence files through existing
  run-scoped file routes; and
- expose C2 payload facts through the existing live summary endpoint or a
  small additive field on that endpoint.

The dashboard must not:

- write `state.json`;
- execute provider calls for C2 summary rendering;
- parse C2 Markdown prose into workflow state;
- expose C2 summary files as workflow artifacts; or
- offer recovery/control actions from C2 summary content.

## Diagnostics

Add stable diagnostics:

- `observability_summary_c0_row_missing`: a required C0
  human-observability row is absent or stale.
- `observability_summary_terminal_value_missing`: no validated terminal typed
  value is available for the selected workflow/run.
- `observability_summary_terminal_value_invalid`: terminal value cannot be
  normalized under the declared type/shape.
- `observability_summary_transition_audit_missing`: transition audit evidence
  required for a selected row is unavailable.
- `observability_summary_transition_audit_invalid`: transition audit evidence
  cannot be parsed through the existing audit helpers.
- `observability_summary_source_map_missing`: source-map or row lineage is
  missing for a generated summary artifact.
- `observability_summary_used_as_state`: a C2 summary file or payload is used
  as typed semantic input, workflow output authority, routing input, retry
  input, assertion input, or parity semantic output.
- `observability_summary_dashboard_mutation`: dashboard rendering attempted to
  mutate run state or invoke control behavior.
- `observability_summary_old_writer_comparison_missing`: a
  `RETIRE_TO_OBSERVABILITY` row lacks old-writer comparison evidence.
- `observability_summary_command_glue_forbidden`: summary derivation attempts
  to use inline shell/Python, an uncertified script, or report parsing.

Diagnostics should include workflow name, run id when runtime evidence exists,
C0 row id, U0 row id, terminal value source, transition audit source,
source-map origin key when available, and summary artifact path when relevant.

## Feasibility Proof

This slice relies on existing capabilities:

- C0 can identify human-observability rows and rows intended for
  observability retirement.
- `build_status_snapshot` already reads run state and workflow outputs without
  changing workflow semantics.
- `SummaryObserver` already owns the `RUN_ROOT/summaries/` hub and can be
  extended with deterministic non-provider summary entries.
- Dashboard summary routes already read the summary hub and are specified as
  read-only observability views.
- Transition audit helpers already expose audit rows and digests for R4
  checkpoint-resume checks.

Implementation must add one narrow proof before broad Design Delta use:

- a minimal run fixture with a typed terminal `DrainResult` or equivalent
  union-shaped terminal value;
- transition audit evidence with at least one committed or replayed transition
  row;
- C2 summary generation producing JSON, Markdown, summary index entry, and
  `observability_summary_report.json`;
- report/dashboard checks proving the C2 summary is visible and read-only; and
- a negative fixture proving C2 summaries cannot be consumed as workflow state.

If the current runtime cannot reliably locate transition audit paths for the
reference family, the implementation must first record the missing audit-source
link as a C2 prerequisite and still generate a terminal-value-only summary with
an explicit diagnostic. It must not parse old summary files to reconstruct the
missing audit facts.

## Verification Plan

Focused checks:

- unit tests for `observability_summaries.py` schema validation, terminal-value
  normalization, transition-audit projection, deterministic JSON/Markdown
  rendering, and summary-index entry construction;
- tests proving C0 `human_observability` and `RETIRE_TO_OBSERVABILITY` rows
  are selected and stale/missing rows fail;
- report tests proving `build_status_snapshot` and `render_status_markdown`
  expose C2 summary links/facts without changing status reconciliation;
- dashboard tests proving the summary hub and live payload expose C2 facts
  read-only and do not mutate `state.json`;
- dual-run comparison tests for old summary writer output versus typed
  terminal summary payload;
- negative tests for summary Markdown parsed as state, summary paths exposed as
  workflow outputs/artifacts, missing terminal typed value, missing transition
  audit evidence, and command-glue summary derivation; and
- regression tests proving provider/command output bundle authority is
  unchanged.

Family-level checks:

- build or dry-run the Design Delta parent-drain entrypoint with checked U0,
  C0, C1, command-boundary, provider, and prompt manifests;
- assert `consumer_rendering_census_report.json` and
  `typed_prompt_input_report.json` remain passing prerequisites;
- run a C2 summary smoke that writes `RUN_ROOT/summaries/typed-terminal-*` and
  `observability_summary_report.json`;
- run `orchestrate report --run-id <run> --format json` against the smoke run
  and assert C2 summary facts are observability-only; and
- exercise the dashboard summary payload helper against the smoke run without
  mutating state.

Suggested deterministic commands are recorded in the generated
`check_commands.json` for this work item.

## Implementation Handoff

Expected touched source modules for implementation:

- `orchestrator/workflow_lisp/observability_summaries.py`
- `orchestrator/observability/report.py`
- `orchestrator/observability/summary.py`
- `orchestrator/dashboard/server.py`
- `orchestrator/workflow_lisp/build.py` only if C2 build evidence is emitted
  during compile/build rather than runtime summary generation
- tests under `tests/test_workflow_lisp_observability_summaries.py`,
  `tests/test_observability_report.py`, and dashboard summary tests
- checked input manifest updates under
  `workflows/examples/inputs/workflow_lisp_migrations/` only if C0 rows need
  additive C2 lineage metadata

Expected implementation must not touch:

- workflow source files to add summary writer steps for C2;
- provider or command execution semantics;
- command-boundary certification or adapter execution;
- renderer byte formats for existing `materialize-view` or C1 prompt inputs;
- checkpoint/restore modules from R1-R6;
- entrypoint publication or compatibility bridge metadata; or
- queue/backlog/run-state files.

Completion evidence should include the C2 report path, its schema version,
`status: pass`, selected C0 row ids, terminal value digest, transition audit
digests or explicit terminal-only diagnostics, old-writer comparison ids, and
the commands used to verify it.
