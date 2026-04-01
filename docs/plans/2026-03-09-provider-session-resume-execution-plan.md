# Provider Session Resume Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the approved `2.10` provider-session resume slice so workflows can publish a runtime-owned string session handle from a fresh provider step, consume it in later steps, and safely quarantine interrupted session-enabled visits instead of replaying them.

**Architecture:** Land the feature in dependency order: first extend the scalar contract family with exact `string` semantics, then add the `2.10` authored surface (`provider_session`, `session_support`, `${SESSION_ID}` validation), then refactor provider execution so session-enabled steps normalize Codex JSONL before output capture, and only then wire crash-consistent `state.json` finalization, resume quarantine, and observability. Keep the authored DSL provider-agnostic, keep the runtime implementation explicitly Codex-first, and leave all non-session provider behavior unchanged.

**Tech Stack:** YAML specs/workflows, Python loader/runtime/state/CLI, pytest unit and integration suites, orchestrator dry-run smoke checks.

---

## Global Guardrails

- Land tranches in order; later tranches assume earlier contracts already exist.
- Write failing tests first inside each tranche before changing implementation code.
- Keep each tranche reviewable and commit-sized; do not mix example migration into the core runtime refactor tranches.
- Keep the state schema at `2.1` unless implementation proves a schema bump is unavoidable. If a schema bump becomes necessary, stop and update the design/plan before continuing.
- Do not remove or rewrite `workflows/examples/dsl_review_first_fix_loop.yaml` in this release.
- Keep non-session provider behavior byte-for-byte compatible unless the relevant spec tranche explicitly changes it.

## Compatibility And Migration Boundary

- New surfaces are gated at `version: "2.10"`: general scalar `string`, step `provider_session`, provider `session_support`, and resume placeholder validation.
- Existing workflows and provider templates remain valid unchanged; `command` stays the non-session execution path.
- Migration is manual and opt-in: upgrade the workflow version, add `session_support`, and replace shell-glue resume providers with `provider_session`.
- `provider_session` is valid only on provider steps authored directly under the root workflow `steps:` list in v1. Imported workflows, loop bodies, `repeat_until` bodies, and structured branches/cases remain invalid.
- Session handles always enter normal scalar lineage as `type: string` artifacts; unqualified `root.steps.<Step>.artifacts.<name>` refs remain limited to single-visit producers.
- `orchestrator resume` changes behavior only for interrupted session-enabled visits: replay is refused and the visit is quarantined instead.
- No automatic migration is provided for older workflows, provider templates, or in-flight runs.

## Explicit Non-Goals

- Multi-provider runtime support beyond the Codex JSONL path in the first slice.
- Nested `call`, loop, or branch support for `provider_session`.
- Automatic adoption, replay, or rotation of provider-native session handles.
- Automatic retry policies for session-enabled steps beyond authored workflow control flow.
- Multi-session orchestration or generalized chat-thread management.
- Any change to the meaning of workflow-level `resume`.

### Tranche 1: Ship `string` As The Prerequisite Scalar Contract

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/io.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/contracts/output_contract.py`
- Modify: `orchestrator/workflow/signatures.py`
- Modify: `orchestrator/workflow/predicates.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_output_contract.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_typed_predicates.py`
- Modify: `tests/test_workflow_output_contract_integration.py`

**Work:**
- Add `2.10` to the supported DSL/versioning tables.
- Extend typed contract validation to accept scalar `string` anywhere the ADR requires it: workflow inputs/outputs, top-level scalar artifacts, `expected_outputs`, `output_bundle.fields`, and `set_scalar`.
- Preserve exact string values end-to-end. Remove implicit trimming only for `type: string`; preserve existing parsing behavior for `enum|integer|float|bool|relpath`.
- Allow typed predicates to compare strings only with `eq` and `ne`; reject ordering operators on string operands.
- Keep `kind: relpath` semantics unchanged and reject `kind: relpath` plus `type: string`.
- Add acceptance bullets and tests that pin exact whitespace-preserving behavior, empty-string validity for general strings, and workflow-boundary/export validation.

**Verification:**
```bash
pytest tests/test_loader_validation.py tests/test_output_contract.py tests/test_artifact_dataflow_integration.py tests/test_typed_predicates.py tests/test_workflow_output_contract_integration.py -k "string" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/workflow_signature_demo.yaml --dry-run
```

**Checkpoint:** Do not start provider-session work until the string contract passes in loader, runtime, and workflow-boundary surfaces.

### Tranche 2: Add The Authored `2.10` Surface And Strict Loader Validation

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/providers.md`
- Modify: `specs/versioning.md`
- Modify: `specs/acceptance/index.md`
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/providers/types.py`
- Modify: `orchestrator/providers/registry.py`
- Modify: `orchestrator/workflow/prompting.py`
- Modify: `orchestrator/workflow/dataflow.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_provider_execution.py`
- Modify: `tests/test_prompt_contract_injection.py`
- Modify: `tests/test_artifact_dataflow_integration.py`

**Work:**
- Gate `provider_session` and `session_support` at `2.10`.
- Validate the tagged union exactly: `mode: fresh` requires `publish_artifact`, `mode: resume` requires `session_id_from`, and the two shapes are mutually exclusive.
- Validate `session_support.metadata_mode`, `fresh_command`, and `resume_command`, including exactly one `${SESSION_ID}` placeholder for resume-capable templates.
- Restrict `provider_session` to provider steps authored directly under the root workflow `steps:` list.
- Enforce the reserved consume rules for `session_id_from`: it must match exactly one `consumes[*]`, must use `freshness: any` or omit freshness, and must be excluded from prompt injection and `consume_bundle`.
- Reserve `publish_artifact` as a runtime-owned local artifact key and reject collisions with `expected_outputs`, `output_bundle.fields`, and `publishes.from`.
- Reject `persist_artifacts_in_state: false` on fresh session steps at load time so the runtime-owned `steps.<Step>.artifacts.<publish_artifact>` surface is always contractually available.
- Reject `retries` on session-enabled steps in the loader before runtime execution.

**Verification:**
```bash
pytest tests/test_loader_validation.py tests/test_provider_execution.py tests/test_prompt_contract_injection.py tests/test_artifact_dataflow_integration.py -k "provider_session or SESSION_ID or consume_bundle or prompt_consumes or persist_artifacts_in_state" -v
```

**Checkpoint:** All invalid authored shapes must fail at load time, and reserved session consumes must stay out of prompt/bundle outputs before runtime execution changes land.

### Tranche 3: Refactor Provider Execution Around Session-Aware Command Compilation And Normalized Stdout

**Files:**
- Modify: `orchestrator/providers/types.py`
- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `specs/providers.md`
- Modify: `specs/io.md`
- Modify: `specs/observability.md`
- Modify: `tests/test_provider_execution.py`
- Modify: `tests/test_at72_provider_state_persistence.py`
- Modify: `tests/test_output_capture.py`

**Work:**
- Introduce one provider-command compilation path that can build `command`, `session_support.fresh_command`, and `session_support.resume_command` with the same substitution and validation rules.
- Thread the reserved session handle into resume invocations only through `${SESSION_ID}`; never through prompt text or workspace files.
- Add a session-aware execution result shape so provider execution can return raw transport, normalized stdout, stderr, parsed metadata summary, and session-handle candidates to the workflow executor.
- For `codex_exec_jsonl_stdout`, parse stdout as JSONL, extract the authoritative session id and normalized assistant text, and fail on malformed transport, conflicting thread ids, missing terminal markers, or mismatched resume thread ids.
- Ensure `--stream-output` and `--debug` emit only normalized assistant text for session-enabled steps, while raw stderr keeps its current live-stream behavior.
- Disable implicit provider retries for session-enabled steps while leaving ordinary provider retries untouched.

**Verification:**
```bash
pytest tests/test_provider_execution.py tests/test_at72_provider_state_persistence.py tests/test_output_capture.py -k "provider_session or codex or stream_output or jsonl" -v
```

**Checkpoint:** Normalized stdout must be identical across captured state and console streaming for successful session-enabled steps before state-publication work begins.

### Tranche 4: Make Fresh-Session Publication Crash-Consistent And Lineage-Correct

**Files:**
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/dataflow.py`
- Modify: `specs/state.md`
- Modify: `specs/dsl.md`
- Modify: `specs/acceptance/index.md`
- Modify: `tests/test_state_manager.py`
- Modify: `tests/test_artifact_dataflow_integration.py`
- Modify: `tests/test_workflow_executor_characterization.py`

**Work:**
- Add one state-manager/executor finalization path for session-enabled top-level steps that commits the exact visit's final `steps.<Step>` payload, every new `artifact_versions` append from that visit, and exact-match `current_step` clearance in one `state.json` rewrite.
- Publish fresh session handles only after normalized stdout and all deterministic output contracts have succeeded.
- Materialize successful fresh handles on `steps.<Step>.artifacts.<publish_artifact>` and in `artifact_versions`, but never republish or rotate handles from resume steps.
- Make successful fresh session steps eligible producers for normal `consumes.producers` validation and runtime filtering even though the session-handle publication is runtime-owned.
- Keep the existing single-visit structured-ref rule unchanged, and rely on the loader-enforced `persist_artifacts_in_state` guardrail so successful fresh session steps always materialize their runtime-owned local artifact surface in persisted step state.

**Verification:**
```bash
pytest tests/test_state_manager.py tests/test_artifact_dataflow_integration.py tests/test_workflow_executor_characterization.py -k "provider_session or artifact_versions or current_step or visit_count" -v
```

**Checkpoint:** No session handle may appear in persisted lineage unless the matching step result, same-visit artifact ledger updates, and `current_step` clearance are committed together.

### Tranche 5: Add Prelaunch Metadata Creation, Quarantine-On-Resume, And Operator-Facing Observability

**Files:**
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/providers/executor.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/resume_planner.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/observability/report.py`
- Modify: `orchestrator/cli/commands/report.py`
- Modify: `specs/state.md`
- Modify: `specs/observability.md`
- Modify: `specs/cli.md`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_at68_resume_force_restart.py`
- Modify: `tests/test_at72_provider_state_persistence.py`
- Modify: `tests/test_observability_report.py`
- Modify: `tests/test_cli_report_command.py`
- Modify: `tests/test_provider_execution.py`

**Work:**
- Create the canonical visit-scoped metadata file and stable masked transport-spool path before `current_step` is persisted for any session-enabled visit.
- Durably append masked raw transport to that stable spool while a session-enabled provider step is in flight, without re-exposing metadata transport on parent-console stdout.
- Record masked metadata updates across running, completed, failed, and quarantined visit states without letting metadata publication get ahead of `state.json`.
- Apply the retention matrix explicitly during terminal finalization and quarantine: delete the spool only after successful non-debug completion once masked summary metadata is updated, and retain it for debug, failure, or quarantined visits with capture counters reflected in metadata/report surfaces.
- Teach resume planning to detect interrupted session-enabled visits by exact `current_step.step_id` plus `visit_count`, ignore older same-name results, and quarantine instead of replaying the provider.
- Project quarantine into authoritative run state by clearing `current_step`, setting run `status: failed`, and writing a durable run-level error that includes the metadata path, spool path, and synthesis flag.
- Keep `--force-restart` as the explicit escape hatch and expose the quarantine state cleanly in report/status surfaces.

**Verification:**
```bash
pytest tests/test_resume_command.py tests/test_at68_resume_force_restart.py tests/test_at72_provider_state_persistence.py tests/test_observability_report.py tests/test_cli_report_command.py tests/test_provider_execution.py -k "provider_session or quarantined or current_step or force_restart or transport_spool or debug" -v
```

**Checkpoint:** Interrupted session-enabled visits must never be replayed on resume, operators must always get a stable metadata/spool path to inspect, and successful non-debug visits must clean up the spool only after metadata finalization.

### Tranche 6: Migrate One Example Workflow And Close The Docs/Runbook Gap

**Files:**
- Create: `workflows/examples/dsl_review_first_fix_loop_provider_session.yaml`
- Create: `prompts/workflows/dsl_review_fix_loop_provider_session/review.md`
- Create: `prompts/workflows/dsl_review_fix_loop_provider_session/fix.md`
- Modify: `workflows/README.md`
- Modify: `workflows/examples/README_v0_artifact_contract.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `tests/test_workflow_examples_v0.py`

**Work:**
- Add one new `2.10` example that replaces the hard-coded `codex exec resume ...` provider with `provider_session.mode: fresh` and `provider_session.mode: resume`.
- Keep `workflows/examples/dsl_review_first_fix_loop.yaml` unchanged as the legacy shell-glue reference.
- Make the new example demonstrate the intended migration path: fresh session creation, review or gating, session-handle consume, resume or fix step, and bounded control flow.
- Update workflow docs and runbooks to explain when to use provider-session resume, why `session_id_from` never appears in prompts, and how resume quarantine differs from workflow resume.

**Verification:**
```bash
pytest tests/test_workflow_examples_v0.py -k "provider_session or review_first_fix" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_review_first_fix_loop_provider_session.yaml --dry-run
```

**Checkpoint:** The new example must validate and document the manual migration path without implying broader provider or nested-scope support than the runtime actually ships.

## Final Integration Gate

Run this only after all tranches pass independently:

```bash
pytest tests/test_loader_validation.py tests/test_output_contract.py tests/test_artifact_dataflow_integration.py tests/test_provider_execution.py tests/test_state_manager.py tests/test_resume_command.py tests/test_observability_report.py tests/test_cli_report_command.py tests/test_workflow_examples_v0.py -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_review_first_fix_loop_provider_session.yaml --dry-run
```

Release is ready only when all tranche verifications pass, the new example works, the legacy shell-based example still validates, and the docs/specs consistently distinguish workflow `resume` from provider-session `resume`.
