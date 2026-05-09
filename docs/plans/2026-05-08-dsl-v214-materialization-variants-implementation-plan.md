# DSL v2.14 Materialization And Variant Semantics Implementation Plan

## Status

This plan replaces the earlier broad NeurIPS workflow-semantics cleanup direction
with a narrower v2.14 tranche.

Current readiness:

- **Phase 0:** implementation-ready now.
- **Phase 1:** implementation-ready only after the contract/integration details
  in this document are preserved in the implementation PR sequence. After that
  pass, Phase 1 is ready for internal or feature-branch implementation.
- **Phase 2:** blocked until the PR 4 / v2.14 release tranche enables public
  `version: "2.14"` support.

## Current Constraints

- The existing DSL is normative, version-gated, and supported through `2.13`.
  Unknown fields at a declared version are validation errors.
- Existing supported surfaces include typed workflow inputs and outputs, top-level
  artifact contracts, `expected_outputs`, `output_bundle`, `publishes`,
  `consumes`, structured `if`, `match`, `repeat_until`, `call`, and same-version
  restrictions for reusable calls.
- The current state schema is `2.1`, with step results, step artifacts, artifact
  versions, call frames, repeat-until bookkeeping, managed-job sidecars, additive
  step debug payloads, and atomic state writes through temp-file rename.
- Path safety must reuse the existing model: reject absolute paths, reject `..`,
  follow symlinks, reject paths that resolve outside `WORKSPACE`, and keep the
  guarantee scoped to orchestrator-managed paths rather than arbitrary child
  process filesystem effects.
- Testing remains network-free by default, uses fake providers where possible,
  and asserts observable state through `state.json`, logs, and on-disk artifacts
  rather than provider prose.

## Executive Decision

Implement the work in three phases:

1. **Phase 0:** Freeze current behavior with reproducible primitive and NeurIPS
   oracles. Do not enable public `version: "2.14"`.
2. **Phase 1:** Add a narrow v2.14 semantic tranche:
   `materialize_artifacts`, `pre_snapshot`, `variant_output`,
   `select_variant_output`, minimal variant-reference proof, strict artifact
   pointer authority, and same-version v2.14 migration.
3. **Phase 2:** Translate the NeurIPS workflow stack into same-version v2.14 YAML
   and prove behavioral equivalence against the Phase 0 oracle.

Do not add in Phases 0-2:

- `recover_or_run`
- `resource_transition`
- `phase_outcome`
- `review_loop`
- Lisp or `.orc` frontend
- agent, belief, memory, or debate abstractions
- mixed-version calls
- mtime-only freshness
- general expression language
- general `if`/`when` variant proof

## Design Principles

### v2.14 Is Not Public Until Complete

Until the release tranche lands:

- `WorkflowLoader.SUPPORTED_VERSIONS` remains capped at `2.13`.
- Normal CLI and loader paths reject `version: "2.14"`.
- `specs/dsl.md` does not list `2.14` as supported.
- `workflows/library/*.v214.yaml` are not public runnable workflows.

Allowed before release:

- unit tests for `VariantContract`
- unit tests for `SnapshotDiff`
- unit tests for `ArtifactMaterializer`
- unit tests for `AtomicBundleWriter`
- private experimental loader helpers

Not allowed before release:

- `version: "2.14"` in examples, public workflows, acceptance fixtures, or
  ordinary CLI runs.

### No mtime-Only Freshness

`mtime_ns >= phase_started_at_ns` is forbidden as a core selection rule. It may
be recorded as debug metadata only.

Phase 1 uses content-based `snapshot_diff`. A candidate changed when it was
absent before and present after, or present before and after with a different
`sha256`. No changed candidate is a failure. More than one changed candidate is
a failure.

### Validate Before Commit

Any runtime-owned bundle write must:

1. construct the candidate in memory;
2. validate the discriminant;
3. validate selected variant fields;
4. validate forbidden fields;
5. validate relpath constraints;
6. validate target existence;
7. validate enum values;
8. write a temp file in the same directory;
9. atomically rename temp to canonical bundle path;
10. only then expose artifacts and publish lineage.

If validation fails, do not modify the canonical bundle, do not expose candidate
artifacts, and record candidate details only in error/debug context.

### One Variant Schema Source

There are two valid surfaces:

- `variant_output`: validates a JSON bundle produced by a provider, command, or
  adjudicated-provider step.
- `select_variant_output`: deterministically selects one variant and writes a
  valid bundle atomically.

The authored Phase 1 validation surface is `variant_output`. Extending
fixed-shape `output_bundle` with `output_bundle.variants` is rejected by
`docs/design/dsl_v214_variant_surface_decision.md` so existing `output_bundle`
semantics remain unconditional and stable.

Both share the same internal `VariantContract`. A step must not declare both.

### Artifact Value, Pointer File, And Published Artifact Are Separate

- Artifact value: typed value recorded in state, for example
  `docs/plans/foo.md`.
- Pointer file: text file containing that value, for example
  `state/plan_path.txt`.
- Published artifact: top-level artifact lineage entry whose value is the
  artifact value, not the pointer-file path.

For a published relpath artifact there is exactly one canonical pointer surface.
If a local artifact is published to a top-level relpath artifact, the local
pointer must be omitted or exactly equal the top-level artifact pointer.
Noncanonical sidecar pointers for published relpath artifacts are rejected in
Phase 1.

### Source Contracts Are Inherited

`materialize_artifacts` must not re-declare or weaken source contracts.

For `source: {input: steering_path}`, the source inherits the workflow input
contract. Allowed refinements include:

- `must_exist_target: false -> true`
- `under: docs -> docs/plans`
- enum allowed set -> strict subset
- additional description or format hints

Rejected refinements include:

- type changes
- `relpath -> scalar` changes
- incompatible `under` changes
- `must_exist_target: true -> false`
- enum expansion

The same rule applies to `source.ref` when the referenced artifact has a known
contract. A `literal` source without a known source contract must declare a full
contract rather than using `inherit: source`.

### Variant-Specific References Require Proof

Variant fields are conditional. Example:

- `implementation_state`: always available
- `execution_report_path`: available only when
  `implementation_state == COMPLETED`
- `progress_report_path` and `blocker_class`: available only when
  `implementation_state == BLOCKED`

Phase 1 supports two proof mechanisms:

1. `match` over the same discriminant;
2. explicit `requires_variant`.

Runtime still guards access and fails pre-execution with `variant_unavailable`
if the asserted variant is not selected.

Deferred:

- general `if`/`when` predicate proof
- compound boolean reasoning
- proof across loops and calls

## Runtime Integration Map

Phase 1 work must touch the current architecture deliberately. Do not start in
the executor and build around half-defined YAML shapes.

### Version Gating And Top-Level Validation

Modify:

- `orchestrator/loader.py`
- `orchestrator/workflow/signatures.py`
- `orchestrator/workflow/runtime_types.py`

Responsibilities:

- reject `version: "2.14"` until the release gate;
- parse `materialize_artifacts`;
- parse `pre_snapshot`;
- parse `variant_output`;
- parse `select_variant_output`;
- parse `requires_variant`;
- validate execution-form mutual exclusion;
- validate same-version calls.

### Reference Parsing And Catalog

Modify:

- `orchestrator/workflow/references.py`
- `orchestrator/workflow/elaboration.py`
- `orchestrator/workflow/conditions.py`
- `orchestrator/workflow/predicates.py`

Responsibilities:

- add `SnapshotRef`;
- build a loader-visible `ReferenceCatalog`;
- track artifact availability;
- propagate `ProofContext` into `match` cases;
- attach `ProofContext` from `requires_variant`;
- reject unsupported `if`/`when` proof;
- emit explicit variant/snapshot ref errors.

### Dataflow And Publishing

Modify:

- `orchestrator/workflow/dataflow.py`
- `orchestrator/workflow/pointers.py`

Responsibilities:

- keep `publishes.from` as a same-step local artifact name;
- publish canonical artifact values, not pointer paths;
- enforce canonical pointer authority;
- validate relpath top-level artifact pointer consistency.

The current DSL dataflow contract remains authoritative: `publishes.from` names
a same-step local output, while workflow `outputs.from` uses structured
`{ref: ...}` syntax.

### Contract Validation And Prompt Injection

Modify or add:

- `orchestrator/contracts/output_contract.py`
- `orchestrator/contracts/prompt_contract.py`
- `orchestrator/workflow/prompting.py`

Responsibilities:

- implement `VariantContract`;
- validate `variant_output` bundles;
- format the `variant_output` prompt suffix;
- inject variant contracts for provider and adjudicated-provider steps;
- do not inject variant contracts for command steps;
- enforce `expected_outputs` / `output_bundle` / `variant_output` /
  `select_variant_output` mutual exclusion.

Variant contracts belong in the contracts package rather than in ad hoc workflow
code.

### IR Lowering

Modify:

- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/runtime_step.py`

Responsibilities:

- lower `materialize_artifacts` to a deterministic IR step;
- attach `pre_snapshot` metadata to the producer step IR;
- lower `select_variant_output` to a deterministic IR step;
- carry `VariantContract` and `SnapshotRef` metadata into runtime;
- preserve authored stable IDs.

### Runtime Dispatch And Execution

Modify:

- `orchestrator/workflow/executor.py`
- `orchestrator/exec/step_executor.py`
- `orchestrator/workflow/runtime_context.py`

Add:

- `execute_materialize_artifacts`;
- `capture_pre_snapshot`;
- `execute_select_variant_output`;
- `validate_variant_output_after_step_success`;
- runtime guard for `requires_variant`.

### Snapshot Persistence And State

Modify:

- `orchestrator/state.py`
- `orchestrator/workflow/runtime_context.py`

Responsibilities:

- store `steps.<Step>.snapshots.<name>`;
- write snapshot sidecars when needed;
- verify sidecar hashes on resume;
- preserve atomic state/bundle writes.

The state spec already documents atomic writes for state files. v2.14 bundle and
snapshot writes must follow the same temp-write/rename discipline.

### Security And Path Safety

Modify or reuse:

- `orchestrator/security/*`
- `orchestrator/workflow/pointers.py`

Responsibilities:

- validate pointer paths;
- validate candidate paths;
- reject directories for snapshot candidates;
- reject symlink escapes;
- reject absolute and parent-escaping paths;
- apply hash-size limits.

These checks apply to orchestrator-managed paths only, not arbitrary
child-process filesystem effects.

### Observability And Reporting

Modify:

- `orchestrator/runtime_observability.py`
- `orchestrator/observability/*`
- `orchestrator/workflow/outcomes.py`

Responsibilities:

- surface selected variant in reports;
- surface snapshot evidence summaries without dumping large hashes unless debug
  mode requests them;
- surface contract-refinement and variant errors;
- record atomic-commit failures clearly.

## New Reference Semantics

Current structured references are centered on step artifacts, exit codes, and
outcome fields. v2.14 introduces a new namespace:

```text
root.steps.<Step>.snapshots.<name>
```

That namespace must be explicitly modeled and must not be treated as an
artifact namespace.

### Reference Kinds

Add a loader-visible taxonomy:

```text
ArtifactRef:
  root.steps.<Step>.artifacts.<name>

SnapshotRef:
  root.steps.<Step>.snapshots.<name>

OutcomeRef:
  root.steps.<Step>.outcome.<field>

ExitCodeRef:
  root.steps.<Step>.exit_code
```

Phase 1 rules:

- `ArtifactRef`: usable anywhere current structured artifact refs are usable,
  subject to variant-availability checks.
- `SnapshotRef`: usable only in
  `select_variant_output.evidence.snapshot.ref`. It is not publishable,
  consumable, prompt-injected, or valid as `materialize_artifacts.source.ref`.
- `OutcomeRef` / `ExitCodeRef`: unchanged.

### Loader Catalog Entries

Add a `ReferenceCatalog` or equivalent internal structure with:

```text
ArtifactEntry:
  step_id: str
  name: str
  contract: TypedContract
  availability: Availability

SnapshotEntry:
  step_id: str
  name: str
  schema: Literal["snapshot_diff/v1"]
  candidates: dict[str, SnapshotCandidateContract]
  digest: Literal["sha256"]
  storage: Literal["inline", "sidecar"]

OutcomeEntry:
  step_id: str
  field: str
```

`SnapshotEntry` is registered by the step that declares `pre_snapshot`.

### Snapshot Ref Resolver

Phase 1 adds snapshot refs:

```yaml
ref: root.steps.ExecuteImplementation.snapshots.implementation_outcome_before
```

Snapshots are not artifacts. Loader validation must maintain a separate snapshot
catalog so artifact refs and snapshot refs do not blur. Runtime resolution must
return the persisted snapshot record or sidecar descriptor.

For:

```yaml
evidence:
  mode: snapshot_diff
  snapshot:
    ref: root.steps.ExecuteImplementation.snapshots.implementation_outcome_before
```

the resolver checks:

- step exists;
- step declares a snapshot with that name;
- snapshot schema is `snapshot_diff/v1`;
- snapshot digest is `sha256`;
- candidate keys match the `select_variant_output` variants/candidates;
- snapshot is in scope for the referencing step.

### Snapshot State Projection

Snapshots are durable runtime evidence:

```text
steps.<Step>.snapshots.<name>
```

State shape:

```json
{
  "steps": {
    "ExecuteImplementation": {
      "snapshots": {
        "implementation_outcome_before": {
          "schema": "snapshot_diff/v1",
          "digest": "sha256",
          "captured_at": "pre_step",
          "candidates": {
            "COMPLETED": {
              "path": "artifacts/work/execution_report.md",
              "exists": false,
              "size": null,
              "sha256": null,
              "mtime_ns": null
            }
          }
        }
      }
    }
  }
}
```

If the snapshot is too large for inline state, store a sidecar:

```text
.orchestrate/runs/<run_id>/snapshots/<step_id>/<snapshot_name>.json
```

and project this into state:

```json
{
  "schema": "snapshot_diff/v1",
  "sidecar": "snapshots/execute_implementation/implementation_outcome_before.json",
  "sha256": "..."
}
```

### Snapshot Reference Errors

Use explicit errors:

- `snapshot_ref_unknown_step`
- `snapshot_ref_unknown_name`
- `snapshot_ref_not_snapshot_diff`
- `snapshot_ref_out_of_scope`
- `snapshot_ref_candidate_mismatch`
- `snapshot_state_missing`
- `snapshot_sidecar_missing`
- `snapshot_sidecar_hash_mismatch`

### Variant Artifact Refs

`variant_output` and `select_variant_output` expose:

- always-available discriminant artifacts;
- selected-variant artifacts only for the selected variant.

Static loader validation rejects variant-specific artifact refs without proof.
Runtime also guards them in case state and proof diverge after resume.

## Variant Field Availability Model

The loader needs a concrete availability model.

When a step declares `variant_output` or `select_variant_output`, register:

```text
VariantProducer:
  step_id: str
  discriminant_artifact: str
  variants: dict[str, VariantSpec]
```

Each exposed field gets availability metadata:

```text
ArtifactEntry(
  name="implementation_state",
  availability=AlwaysAvailable()
)

ArtifactEntry(
  name="execution_report_path",
  availability=VariantOnly(
    producer_step="SelectImplementationOutcome",
    discriminant="implementation_state",
    variant="COMPLETED"
  )
)

ArtifactEntry(
  name="progress_report_path",
  availability=VariantOnly(
    producer_step="SelectImplementationOutcome",
    discriminant="implementation_state",
    variant="BLOCKED"
  )
)
```

### Proof Context

Add a loader proof context:

```text
ProofContext:
  variants: dict[producer_step_id, selected_variant]
```

The context is propagated structurally. Supported in Phase 1:

- `match` over the exact discriminant artifact;
- explicit `requires_variant`.

Not supported yet:

- general `if`/`when` predicate proof;
- compound predicates;
- proof through arbitrary loops;
- proof across reusable-call boundaries.

### Proof Through `match`

If the loader sees:

```yaml
match:
  ref: root.steps.SelectImplementationOutcome.artifacts.implementation_state
  cases:
    COMPLETED:
      steps: [...]
```

then inside the `COMPLETED` case:

```text
ProofContext[SelectImplementationOutcome] = COMPLETED
```

A reference to:

```text
root.steps.SelectImplementationOutcome.artifacts.execution_report_path
```

is valid only in that context.

### Proof Through `requires_variant`

For:

```yaml
requires_variant:
  step: SelectImplementationOutcome
  value: COMPLETED
```

the loader attaches:

```text
ProofContext[SelectImplementationOutcome] = COMPLETED
```

to that step.

Runtime must still verify:

```text
steps.SelectImplementationOutcome.artifacts.implementation_state == "COMPLETED"
```

before executing. If state disagrees, fail before execution.

### Variant Reference Errors

Use explicit errors:

- `variant_ref_unproved`
- `variant_ref_wrong_variant`
- `variant_ref_unknown_producer`
- `variant_ref_unknown_field`
- `variant_ref_discriminant_missing`
- `variant_unavailable`

`variant_unavailable` is the runtime guard failure. The others are loader or
validation failures.

### Call-Boundary Rule

Phase 1 does not propagate variant proof through reusable workflow calls. Only
declared callee outputs cross a call boundary. Variant-only internal artifacts
do not cross unless normalized into ordinary workflow outputs inside the callee.

## Error Taxonomy

Add these error classes before implementation so tests assert exact failures.

Version / exposure:

- `unsupported_dsl_version`
- `experimental_dsl_version_not_enabled`
- `mixed_version_call_unsupported`

Materialization / contracts:

- `materialize_source_unknown`
- `materialize_ref_unresolved`
- `contract_source_unknown`
- `contract_required_for_literal`
- `contract_refinement_weakened`
- `contract_refinement_type_conflict`
- `contract_refinement_kind_conflict`
- `contract_refinement_incompatible_under`
- `contract_field_invalid_for_type`
- `pointer_not_allowed_for_scalar`
- `pointer_authority_conflict`
- `unsafe_path`
- `target_missing`

Snapshot refs / evidence:

- `snapshot_ref_unknown_step`
- `snapshot_ref_unknown_name`
- `snapshot_ref_not_snapshot_diff`
- `snapshot_ref_out_of_scope`
- `snapshot_ref_candidate_mismatch`
- `snapshot_candidate_oversize`
- `snapshot_candidate_is_directory`
- `snapshot_candidate_unsafe_path`
- `snapshot_state_missing`
- `snapshot_sidecar_missing`
- `snapshot_sidecar_hash_mismatch`
- `snapshot_candidate_unchanged`
- `snapshot_candidate_ambiguous`

Variant contracts:

- `invalid_variant_bundle`
- `variant_discriminant_missing`
- `variant_discriminant_invalid`
- `variant_required_field_missing`
- `variant_forbidden_field_present`
- `variant_field_type_invalid`
- `variant_field_target_missing`
- `variant_extractor_failed`
- `variant_extractor_value_invalid`
- `variant_unavailable`

Variant reference proof:

- `variant_ref_unproved`
- `variant_ref_wrong_variant`
- `variant_ref_unknown_producer`
- `variant_ref_unknown_field`
- `variant_ref_discriminant_missing`
- `unsupported_variant_proof`

Atomic commit:

- `atomic_commit_failed`
- `bundle_commit_aborted_invalid_candidate`

## Phase 0: Freeze Behavior With Reproducible Oracles

### Objective

Build behavioral oracles before changing DSL semantics. Phase 0 is safe to start
immediately. It must not enable v2.14.

### Deliverables

- `docs/design/dsl_v214_materialization_variants_draft.md`
- `docs/design/neurips_v214_behavior_matrix.md`
- `tests/golden_state.py`
- `tests/test_v214_primitive_oracle.py`
- `tests/test_neurips_v214_equivalence_oracle.py`
- `tests/fixtures/v214_primitives/`
- `tests/fixtures/neurips_minimal/`
- `tests/fixtures/bin/fake_provider.py`

The v2.14 document is draft and non-normative during Phase 0.

### Phase 0 Boundaries

Phase 0 must not contain runnable v2.14 workflows.

Allowed:

- current supported-version workflows;
- old glue workflows that emulate future semantics;
- fixtures asserting `version: "2.14"` is rejected;
- draft non-normative docs;
- unit fixtures for current behavior;
- fake providers;
- golden observation helpers.

Not allowed:

- public v2.14 YAML examples that run through the normal loader;
- `workflows/library/*.v214.yaml`;
- `specs/dsl.md` listing `2.14` as supported;
- acceptance tests expecting normal v2.14 execution.

The `old_materialization_equivalent` fixtures use the current supported DSL and
current glue, not draft v2.14 syntax.

### Phase 0.1: Inventory Current Brittle Patterns

Create a measured inventory of current workflows. Output:

- workflow file
- line count
- command-step count
- inline Bash/Python line count
- pointer-file writes
- `output_bundle` optional fields
- mtime/freshness checks
- custom helper scripts called
- phase-finalizer steps

Map current patterns to future handling:

| Current pattern | Future handling |
| --- | --- |
| Input path -> pointer file -> publish | `materialize_artifacts` |
| Target path setup | `materialize_artifacts` |
| mtime-based outcome selection | `pre_snapshot` + `select_variant_output` |
| Flat optional bundle used as tagged union | `variant_output` / `select_variant_output` |
| Review/revise loops | defer to macro/library phase |
| Plan-gate recovery | defer |
| Queue/resource transitions | defer |
| Outcome recording | defer |

### Phase 0.2: Primitive-Oracle Fixtures

Create current-version fixtures, not public v2.14 workflows:

```text
tests/fixtures/v214_primitives/
  docs/
    steering.md
    design.md
  artifacts/
    work/
      stale_execution_report.md
  state/
  prompts/
  workflows/
    old_materialization_equivalent.yaml
    old_variant_completed_equivalent.yaml
    old_variant_blocked_equivalent.yaml
```

Primitive oracle scenarios:

| Scenario | Expected result |
| --- | --- |
| Materialize valid input | pointer written; state artifact value equals input value |
| Missing required input target | contract failure |
| Weaker contract refinement | loader error |
| Stricter contract refinement | accepted |
| Snapshot then one candidate changes | variant selected |
| Snapshot then no candidate changes | contract failure |
| Snapshot then both candidates change | contract failure |
| Invalid bundle candidate | canonical bundle not committed |
| Completed variant bundle | completed-only fields exposed |
| Blocked variant bundle | blocked-only fields exposed |
| Variant-specific ref without proof | loader error |
| Variant-specific ref under match | accepted |
| Variant-specific ref with `requires_variant` | accepted |

### Phase 0.3: Minimal NeurIPS Fixtures

Create:

```text
tests/fixtures/neurips_minimal/
  docs/
    steering.md
    plans/
      design.md
      roadmap.md
    backlog/
      active/
        item-001.md
      in_progress/
      done/
  artifacts/
    work/
    checks/
    review/
  state/
    progress_ledger.md
    run_state.json
```

Keep this much smaller than the full project. It captures path shapes and
workflow behavior, not the research corpus.

### Phase 0.4: Fake Provider

Add `tests/fixtures/bin/fake_provider.py`.

Supported scenarios:

- `completed`: writes `artifacts/work/execution_report.md`
- `blocked`: writes `artifacts/work/progress_report.md` with
  `Blocker Class: missing_resource`
- `both_reports`: writes both candidate files
- `neither_report`: writes neither file
- `review_approve`
- `review_revise`

### Phase 0.5: Golden Observation Schema

Create a normalized observation format:

```json
{
  "schema": "workflow_golden_observation/v1",
  "workflow_outputs": {},
  "steps": {
    "StepName": {
      "status": "completed",
      "outcome_class": "completed"
    }
  },
  "artifacts": {
    "implementation_state": {
      "value": "COMPLETED",
      "type": "enum"
    },
    "execution_report_path": {
      "value": "artifacts/work/execution_report.md",
      "type": "relpath"
    }
  },
  "snapshots": {
    "ExecuteImplementation.implementation_outcome_before": {
      "candidate_keys": ["COMPLETED", "BLOCKED"],
      "digest": "sha256"
    }
  },
  "files": {
    "artifacts/work/execution_report.md": {
      "exists": true,
      "sha256": "..."
    }
  },
  "queue": {
    "active": [],
    "in_progress": [],
    "done": ["item-001.md"]
  },
  "domain_state": {
    "completed_items": ["item-001"],
    "blocked_items": [],
    "history_event_types": ["select", "complete"]
  },
  "error": null
}
```

Normalize away run IDs, absolute temp paths, timestamps, durations, log paths,
and incidental ordering. Retain final outputs, artifact values, selected
variant, file hashes, queue state, domain-state summary, failure class, contract
violations, and snapshot candidate keys.

### Phase 0.6: NeurIPS Regression Scenarios

| Scenario | Expected result |
| --- | --- |
| Plan context inputs exist | published artifact values match current workflow |
| Missing plan context input | fails before provider execution |
| Implementation completed | `COMPLETED`; execution report exists; no blocked-only fields |
| Implementation blocked | `BLOCKED`; progress report exists; blocker class valid |
| Both reports produced | failure |
| Neither report produced | failure |
| Recovered approved plan gate | fresh plan phase skipped |
| Missing recovered plan gate | fresh plan phase runs |
| Completed selected item | item reaches done; run state records completion |
| Blocked selected item | item does not falsely complete; blocked state recorded |

### Phase 0 Acceptance Criteria

- default tests require no network and no secrets;
- fake provider drives all primitive and NeurIPS scenarios;
- golden observation normalizer exists;
- primitive oracle and NeurIPS regression oracle are separate;
- current behavior is captured before semantic changes;
- no public v2.14 workflow support is enabled.

## Phase 1: Add Narrow v2.14 Semantics

### Objective

Add a precise semantic tranche that removes high-risk glue without overfitting
NeurIPS.

The Phase 1 primitive set:

- `materialize_artifacts`
- `pre_snapshot`
- `variant_output`
- `select_variant_output`
- `requires_variant`
- match-based variant proof

### State-Schema Decision

Prefer to keep `schema_version: "2.1"` because snapshots and variant metadata
can be additive step payloads and run-root sidecars. A new state schema is
required only if resume needs a new top-level durable structure that cannot be
represented additively.

### Primitive: `materialize_artifacts`

`materialize_artifacts` is a deterministic execution form for resolving typed
values, writing optional canonical pointers, creating parent directories,
exposing local artifacts, and optionally publishing them. It replaces the
earlier split ideas `bind_inputs_as_artifacts` and `materialize_targets`.

Example:

```yaml
- name: MaterializeImplementationInputs
  id: materialize_implementation_inputs
  materialize_artifacts:
    values:
      - name: design_path
        source: { input: design_path }
        contract: { inherit: source }
        pointer:
          path: ${inputs.state_root}/design_path.txt

      - name: execution_report_target_path
        source: { input: execution_report_target_path }
        contract:
          inherit: source
          refine:
            must_exist_target: false
        pointer:
          path: ${inputs.state_root}/execution_report_target_path.txt
        ensure_parent: true
  publishes:
    - artifact: design
      from: design_path
```

Allowed source forms:

- `source: {input: input_name}`
- `source: {ref: root.steps.SomeStep.artifacts.some_artifact}`
- `source: {literal: "artifacts/work/report.md"}`
- `source: {runtime: now_ns}`

No general expression language in Phase 1. Derived paths should remain workflow
inputs, small legacy commands, or future constrained path-derivation work.

`materialize_artifacts` produces same-step local artifacts.
`publishes.from` names those local artifacts exactly as current DSL requires. No
extension to `publishes.from` is needed in Phase 1.

#### Contract Requiredness

For `source: input` or `source: ref`, this is sufficient:

```yaml
contract:
  inherit: source
```

For `source: literal`, an explicit full contract is required:

```yaml
contract:
  type: relpath
  under: artifacts/work
  must_exist_target: false
```

For `source: runtime: now_ns`, the built-in contract is:

```yaml
type: integer
kind: scalar
```

For `runtime: now_ns`, `contract: {inherit: source}` or omitted `contract` is
acceptable. `pointer.path` is not allowed for `runtime: now_ns` in Phase 1.

#### `must_exist_target` Ordering

Ordering:

```text
absent / false < true
```

Allowed:

- source absent/false -> refine true;
- source true -> refine true;
- source absent/false -> explicit false as no-op.

Rejected:

- source true -> refine false.

Error: `contract_refinement_weakened`.

#### `under` Subset Comparison

Normalize both paths as workspace-relative path components.

Allowed:

- source `under: docs` -> refine `under: docs/plans`;
- source `under: artifacts` -> refine `under: artifacts/work`.

Rejected:

- source `under: docs/plans` -> refine `under: docs`;
- source `under: docs` -> refine `under: artifacts/work`;
- refine `under` contains `..`;
- refine `under` resolves outside workspace.

Errors:

- `contract_refinement_weakened`
- `contract_refinement_incompatible_under`
- `unsafe_path`

#### Enum Subset Comparison

For enum contracts, `refine.allowed` must be a subset of `source.allowed`.

Allowed:

- source allowed `[A, B, C]` -> refine allowed `[A, B]`

Rejected:

- source allowed `[A, B]` -> refine allowed `[A, B, C]`

Error: `contract_refinement_weakened`.

For non-enum contracts, `allowed` is invalid. Error:
`contract_field_invalid_for_type`.

#### Type And Kind Compatibility

Rejected:

- source type `relpath` -> refine type `string`;
- source kind `relpath` -> refine kind `scalar`;
- source type `integer` -> `pointer.path` present.

Errors:

- `contract_refinement_type_conflict`
- `contract_refinement_kind_conflict`
- `pointer_not_allowed_for_scalar`

#### Pointer Rule

`pointer.path` is allowed only for relpath materialized values.

If a local relpath artifact is published to a top-level relpath artifact:

- local pointer omitted: publish uses/verifies the canonical top-level pointer;
- local pointer present: `pointer.path` must exactly equal the top-level artifact
  pointer;
- otherwise: `pointer_authority_conflict`.

This avoids noncanonical sidecars in the first tranche.

### Primitive: `pre_snapshot`

`pre_snapshot` is a producer-step modifier that captures durable before-state
evidence for candidate output paths immediately before provider, command, or
adjudicated-provider execution.

Example:

```yaml
- name: ExecuteImplementation
  id: execute_implementation
  pre_snapshot:
    name: implementation_outcome_before
    digest: sha256
    max_bytes_per_candidate: 16777216
    candidates:
      COMPLETED:
        ref: root.steps.MaterializeImplementationInputs.artifacts.execution_report_target_path
      BLOCKED:
        ref: root.steps.MaterializeImplementationInputs.artifacts.progress_report_target_path
  provider: "${inputs.implementation_execute_provider}"
  asset_file: prompts/neurips_backlog_implementation_phase/implement_implementation.md
```

Snapshots live under:

```text
root.steps.<StepName>.snapshots.<snapshot_name>
```

not under artifacts.

Inline state is acceptable for small records. Large records use run-root
sidecars:

```text
.orchestrate/runs/<run_id>/snapshots/<step_id>/<snapshot_name>.json
```

Cost policy:

- `digest: sha256` required;
- hashing must be streaming;
- default `max_bytes_per_candidate`: 16 MiB;
- maximum override: 64 MiB;
- oversize policy: reject;
- directories rejected;
- symlink escapes rejected through existing path-safety rules;
- mtime recorded only as debug metadata.

### Primitive: `variant_output`

`variant_output` is a tagged-union output contract for a step that writes a JSON
bundle. Required and forbidden fields depend on the discriminant.

Provider and adjudicated-provider steps receive prompt output-contract injection.
Command steps validate output but receive no prompt injection.

### Primitive: `select_variant_output`

`select_variant_output` deterministically selects one variant using durable
snapshot evidence and atomically writes a validated bundle. It replaces
`observe_exactly_one_fresh_output`.

Selection semantics:

- exactly one changed candidate: select that variant;
- zero changed candidates: `snapshot_candidate_unchanged`;
- more than one changed candidate: `snapshot_candidate_ambiguous`;
- invalid candidate path, directory, or oversized file: `snapshot_candidate_invalid`.

Commit semantics:

1. select candidate;
2. construct bundle in memory;
3. validate against `VariantContract`;
4. write temporary JSON file;
5. atomic rename to bundle path;
6. record artifacts;
7. publish only after successful commit.

Phase 1 supports one minimal generic extractor:

```yaml
extract:
  from: candidate_path
  line_prefix: "Blocker Class:"
  strip: ["`", "-"]
```

No NeurIPS-specific parser is allowed in the core DSL.

### Variant-Reference Safety

Supported proof form 1: `match`.

Supported proof form 2: `requires_variant`.

General `when` proof is rejected in Phase 1, even for obvious equality checks.

### Phase 1 Tests

Add:

- `tests/test_v214_materialize_artifacts.py`
- `tests/test_v214_pre_snapshot.py`
- `tests/test_v214_variant_output.py`
- `tests/test_v214_select_variant_output.py`
- `tests/test_v214_variant_reference_safety.py`
- `tests/test_v214_version_exposure.py`
- `tests/test_v214_prompt_contract_injection.py`

Minimum assertions:

- v2.14 rejected by normal loader before release;
- materialize input inherits contract;
- materialize rejects weaker refinement;
- materialize accepts stricter refinement;
- materialize writes pointer atomically;
- published relpath pointer mismatch rejected;
- parent directory creation works;
- pre_snapshot stores durable evidence;
- pre_snapshot rejects oversized candidate;
- pre_snapshot hashes streaming content;
- select_variant_output selects created file;
- select_variant_output selects hash-changed file;
- select_variant_output rejects no changed candidates;
- select_variant_output rejects multiple changed candidates;
- select_variant_output does not commit invalid bundle;
- variant_output accepts completed shape;
- variant_output accepts blocked shape;
- variant_output rejects forbidden fields;
- variant_output exposes only selected fields;
- variant-specific ref rejected without proof;
- variant-specific ref accepted under `match`;
- variant-specific ref accepted with `requires_variant`;
- provider prompt injection includes variant contract;
- adjudicated-provider prompt injection includes variant contract;
- command `variant_output` validates without prompt injection;
- `expected_outputs`, `output_bundle`, `variant_output`, and
  `select_variant_output` mutual exclusion is enforced.

### Normative v2.14 Release Gate

Only after loader, runtime, and tests pass:

- update `specs/dsl.md`;
- update `specs/versioning.md`;
- update `specs/state.md` if needed;
- update `specs/security.md` if path wording changes;
- update `specs/acceptance/index.md`;
- add `2.14` to supported versions;
- enable normal CLI/loader support for `version: "2.14"`.

Phase 1 is complete only when normative docs and runtime support land together.

## Phase 2: Translate NeurIPS Workflows Into v2.14 YAML

Phase 2 starts only after the normative v2.14 release gate lands.

Phase 2 entry condition:

- `specs/dsl.md` lists `2.14` as supported;
- normal loader accepts `version: "2.14"`;
- `materialize_artifacts`, `pre_snapshot`, `variant_output`, and
  `select_variant_output` are implemented;
- variant proof rules are implemented;
- v2.14 tests pass.

Only then create `workflows/library/*v214.yaml`. Before that, those files may
exist only on the feature branch as draft fixtures.

### Objective

Create side-by-side v2.14 workflows and prove equivalence against Phase 0. Do
not delete old workflows yet.

Suggested files:

- `workflows/library/neurips_backlog_roadmap_sync.v214.yaml`
- `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml`
- `workflows/library/neurips_backlog_implementation_phase.v214.yaml`
- `workflows/library/neurips_selected_backlog_item.v214.yaml`

### Same-Version Stack Rule

A v2.14 workflow calls only v2.14 workflows.

### Phase 2.1: Translate Implementation Phase First

This exercises `materialize_artifacts`, `pre_snapshot`,
`select_variant_output`, and variant-reference safety.

Remove or reduce:

- `phase_started_at_ns` as selection authority;
- mtime-only report selection;
- custom `implementation_state.json` writer;
- flat optional `output_bundle` variant emulation;
- ad hoc conditional publish commands.

Keep for now:

- review/fix loop;
- check-suite runner;
- final workflow-output normalization if still needed.

### Phase 2.2: Translate Seeded Plan Phase

Replace old plan-context input pointer commands with `materialize_artifacts`.
Keep plan review loop, plan revise loop, and final plan output normalization.

### Phase 2.3: Translate Roadmap Sync As Compatibility v2.14

Create `neurips_backlog_roadmap_sync.v214.yaml` as a v2.14-compatible copy with
minimal semantic refactor. The purpose is to avoid mixed-version calls.

### Phase 2.4: Translate Selected Item Conservatively

Create `neurips_selected_backlog_item.v214.yaml`. Replace Tier-1-compatible
boilerplate only:

- input materialization;
- target pointer materialization;
- simple artifact publication;
- variant-safe references to implementation outputs.

Keep domain-shaped logic:

- `recover_neurips_plan_gate_outputs.py`
- `reconcile_neurips_selected_item.py`
- `move_neurips_backlog_item.py`
- `update_neurips_backlog_run_state.py`
- `RecordCompletedItem`
- `RecordPlanBlocked`
- `RecordRoadmapBlocked`

These are future candidates for `recover_or_run`, `resource_transition`, and
`phase_outcome`, but not Phase 2.

### Phase 2.5: Differential Tests

Parameterize old and v2.14 stacks:

```python
@pytest.mark.parametrize("workflow_stack", ["old", "v214"])
def test_implementation_completed_equivalence(workflow_stack, tmp_path):
    ...
```

Equivalent:

- final workflow outputs;
- artifact values;
- selected variant;
- variant bundle shape;
- file hashes;
- queue state;
- domain run-state summary;
- failure class;
- contract violations.

Not necessarily equivalent:

- intermediate step names;
- number of commands;
- exact debug payload shape;
- timestamps;
- run IDs;
- old pointer-copy files that no longer exist.

### Phase 2.6: Metrics

Measure locally:

- YAML line count;
- inline Bash/Python line count;
- command-based pointer writes;
- optional `output_bundle` fields used as variant emulation;
- custom helper scripts still required;
- variant refs protected by `match`/`requires_variant`;
- equivalence scenarios passing.

Do not use GitHub-rendered size claims.

## PR Sequence

Phase 1 implementation ordering:

1. Add pure contract/ref/snapshot/variant dataclasses and unit tests.
2. Add loader validation and catalog registration.
3. Add runtime execution.
4. Add prompt injection.
5. Only then wire public v2.14 version support.

### PR 0: Phase 0 Oracle And Draft Design

- add draft/non-normative design doc;
- add primitive fixtures;
- add NeurIPS minimal fixtures;
- add fake provider;
- add golden observation helper;
- add current-behavior oracle tests;
- do not enable `version: "2.14"`;
- do not update `specs/dsl.md` as supported.

### PR 1: Internal Materialization/Snapshot Components

- implement `ArtifactMaterializer`;
- implement `ContractRefinement`;
- implement `SnapshotDiff`;
- implement `SnapshotStore`;
- unit-test internals;
- keep APIs private if this lands before v2.14 exposure.

### PR 2: Internal Variant Components

- implement `VariantContract`;
- implement `VariantOutputValidator`;
- implement `AtomicBundleWriter`;
- test validate-before-commit;
- test forbidden/required fields;
- test selected-field exposure.

### PR 3: Internal Selector/Proof Components

- implement `select_variant_output` executor;
- implement `match`/`requires_variant` proof;
- implement runtime variant guard;
- test snapshot-diff selection;
- test no-change and multi-change failures;
- test variant refs with and without proof.

### PR 4: Normative v2.14 Release Tranche

- enable `version: "2.14"` in normal loader/CLI;
- update DSL/version/state/security specs as needed;
- update acceptance tests;
- add public v2.14 fixtures;
- run full relevant unit/integration suite.

This is the first PR where public workflows may declare `version: "2.14"`.

### PR 5: v2.14 Implementation Phase

- add `neurips_backlog_implementation_phase.v214.yaml`;
- replace mtime/custom bundle writer with `pre_snapshot` +
  `select_variant_output`;
- add old/v2.14 equivalence tests.

### PR 6: v2.14 Plan Phase

- add `neurips_backlog_seeded_plan_phase.v214.yaml`;
- replace plan-context pointer boilerplate with `materialize_artifacts`;
- add equivalence tests.

### PR 7: v2.14 Roadmap + Selected-Item Stack

- add `neurips_backlog_roadmap_sync.v214.yaml`;
- add `neurips_selected_backlog_item.v214.yaml`;
- ensure all calls are same-version v2.14;
- add selected-item equivalence tests.

## Final Acceptance Criteria

### Phase 0

- behavior oracle exists;
- primitive and NeurIPS regression tests are separate;
- fake provider drives all scenarios;
- golden observation schema normalizes volatile fields;
- no public v2.14 support is enabled.

### Phase 1

- v2.14 support lands only with runtime, docs, and tests;
- `materialize_artifacts` cannot weaken source contracts;
- published relpath artifacts have one canonical pointer;
- `pre_snapshot` is durable under `steps.<step>.snapshots`;
- snapshot hashing is bounded and streaming;
- mtime is diagnostic only;
- `variant_output` validates tagged unions;
- `select_variant_output` validates before atomic commit;
- invalid bundles are never committed;
- variant-specific refs require `match` or `requires_variant`;
- runtime guards unavailable variant fields;
- provider/adjudicated-provider prompt injection is tested;
- command validation without prompt injection is tested.

### Phase 2

- v2.14 NeurIPS stack calls only v2.14 workflows;
- implementation phase uses `pre_snapshot` + `select_variant_output`;
- plan phase uses `materialize_artifacts` for input binding;
- selected-item workflow migrates conservatively;
- old and v2.14 stacks are behaviorally equivalent on golden scenarios;
- recovery/resource/outcome/review-loop abstractions remain deferred.

## Deferred Issues

- mixed-version call compatibility;
- receipt-manifest evidence mode;
- producer nonce or completion-marker evidence mode;
- large-file hash caching;
- metadata-only snapshot mode;
- general expression language for path derivation;
- general `if`/`when` variant proof;
- `recover_or_run`;
- `resource_transition`;
- `phase_outcome`;
- review/revise macro;
- Lisp or `.orc` frontend;
- agent/belief/memory libraries.
