# Managed Provider DSL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add version-gated `managed_jobs` provider-step semantics so workflows can transparently wrap write-capable providers, audit launched jobs, recover deterministically, and resume recovery without relaunching the provider.

**Architecture:** Treat `managed_jobs` as a provider-step modifier in the workflow DSL, not as provider YAML or a separate command gate. Validation, AST, IR, and executable node metadata carry the declared policy, while provider execution delegates to a small managed-job runtime that wraps the selected provider command and owns recovery state.

**Tech Stack:** Python orchestrator runtime, workflow DSL loader/elaboration/lowering, provider invocation layer, JSONL audit files, pytest.

---

## Source Context

- Design source: `docs/plans/2026-05-04-transparent-managed-job-auto-classification-design.md`
- Normative docs to update before declaring the feature complete:
  - `specs/dsl.md`
  - `specs/providers.md`
  - `specs/state.md`
  - `specs/cli.md`
  - `specs/acceptance/index.md`
  - `docs/workflow_drafting_guide.md`
- Project constraints:
  - Run commands from repo root.
  - Do not create worktrees. This overrides the generic writing-plans skill worktree recommendation.
  - Keep changes scoped to managed provider DSL and managed-job runtime behavior.
  - Run visible checks before claiming completion.

## Contract Summary

`managed_jobs` is valid only on provider steps in the next DSL version after the currently implemented surface.

Authoring shape:

```yaml
version: "2.13"
steps:
  - name: ExecuteImplementation
    provider: implementation_provider
    timeout_sec: 86400
    managed_jobs:
      policy: workflows/managed_jobs/policy.yaml
      watch_roots:
        - scripts/studies
        - scripts/training
      backend: auto
      poll_budget_sec: 82800
      on:
        complete: ReviewImplementation
        failed: FixImplementation
        invalid: FixImplementation
        outstanding: fail_resumable
```

Initial constraints:

- Valid on `provider` steps only.
- Invalid on `command`, `adjudicated_provider`, `wait_for`, `assert`, `set_scalar`, `increment_scalar`, and `call` steps.
- Invalid with provider `retries` in the first version.
- Managed provider execution must force provider retries to zero even when global provider retries are configured. Recovery, not provider relaunch, is the retry/recovery boundary.
- Invalid with ordinary step-level `on` in the first version. Managed provider steps use `managed_jobs.on` exclusively so `on.always` ordering cannot silently compose with managed outcome routing.
- `managed_jobs.on.complete`, `managed_jobs.on.failed`, and `managed_jobs.on.invalid` are step names validated like ordinary goto targets.
- `managed_jobs.on.outstanding` only accepts `fail_resumable`.
- `policy` and `watch_roots` are relative paths that must pass the existing path-safety model.
- `watch_roots` are active inputs to provider-time watching and auto-classification. They are not decorative metadata.
- `backend` initially accepts `auto`, `local`, and `slurm`.
- `poll_budget_sec` is a positive integer less than or equal to the step `timeout_sec` when a timeout is set.
- Runtime wraps fresh and resume provider-session commands after the existing provider-session command selection has happened.
- Every managed entry must provide deterministic job metadata directly or through a named extractor. The runtime must be able to derive state root, output root handling, verification targets, source/config identity, and snapshot inputs before routing a command as managed.
- Managed provider timeout must terminate the whole guarded process tree. Already-submitted managed jobs are recovered from persisted job state; unsupervised provider child processes are not allowed.
- Slurm jobs must execute an immutable source/config snapshot or verify recorded source/config hashes before running. Live-workspace mutable code is not a valid Slurm execution identity.

## File Map

### DSL, AST, IR, and Lowering

- Modify: `orchestrator/loader.py`
  - Add DSL version gate.
  - Validate `managed_jobs` shape, path safety, provider-only placement, retry incompatibility, and managed route targets.
- Modify: `orchestrator/workflow/surface_ast.py`
  - Add surface AST dataclasses for managed-job config and routing.
- Modify: `orchestrator/workflow/elaboration.py`
  - Parse `managed_jobs` into the surface AST.
- Modify: `orchestrator/workflow/executable_ir.py`
  - Add executable IR dataclasses for managed-job config and outcome routing.
- Modify: `orchestrator/workflow/lowering.py`
  - Lower surface config into provider-step executable config.
  - Add typed transfer metadata for managed-job outcomes.
- Modify: `tests/workflow_bundle_helpers.py`
  - Teach workflow bundle materialization/thaw helpers to preserve `managed_jobs`.

### Managed-Job Runtime

- Create: `orchestrator/managed_jobs/__init__.py`
- Create: `orchestrator/managed_jobs/models.py`
  - Shared enums and dataclasses for audit events, job status, recovery summary, and runtime config.
- Create: `orchestrator/managed_jobs/audit.py`
  - JSONL append/read helpers with strict event validation.
- Create: `orchestrator/managed_jobs/runtime.py`
  - Provider invocation wrapping, audit-path preparation, recovery entrypoint, resume detection, and outcome mapping.
- Create: `orchestrator/managed_jobs/provider_guard.py`
  - CLI/module entrypoint used by the runtime wrapper around provider commands.
- Create: `orchestrator/managed_jobs/recovery.py`
  - Poll and verify audited jobs without resubmitting.
- Create: `orchestrator/managed_jobs/policy.py`
  - Load and validate managed-job policy YAML.
- Create: `orchestrator/managed_jobs/extractors.py`
  - Named extractor registry for deriving job metadata from supported training commands.
- Create: `orchestrator/managed_jobs/identity.py`
  - Compute stable job identity hashes from source, config, extractor, policy-entry, and normalized-argument inputs.
- Create: `orchestrator/managed_jobs/snapshot.py`
  - Materialize immutable execution snapshots and manifests for managed backend execution.
- Create: `orchestrator/managed_jobs/classifier.py`
  - Classify created or edited entrypoints under watched roots against managed-job policy.
- Create: `orchestrator/managed_jobs/pending_policy.py`
  - Maintain the runtime-owned pending-policy sidecar and reconciliation protocol.
- Create: `orchestrator/managed_jobs/watcher.py`
  - Watch configured roots while the provider child process runs and enqueue classification decisions.
- Create: `orchestrator/managed_jobs/runner.py`
  - `run_managed_job` behavior used by shims and explicit launch paths.
- Create: `orchestrator/managed_jobs/backends.py`
  - Local and Slurm backend interfaces, including snapshot-aware Slurm script generation.
- Create: `orchestrator/managed_jobs/shims.py`
  - Shim-directory construction and real executable resolution.

### Executor and State

- Modify: `orchestrator/providers/types.py`
  - Confirm `ProviderInvocation` can carry wrapper metadata and process-tree timeout requirements without changing provider templates. Add a `metadata` field only if current metadata surfaces are insufficient.
- Modify: `orchestrator/providers/executor.py`
  - Support managed invocations that must run in their own process group/session and terminate the full process tree on timeout.
- Modify: `orchestrator/workflow/executor.py`
  - Invoke managed-job runtime for managed provider steps.
  - Force managed provider retry policy to zero even when global provider retries are configured.
  - Run recovery after provider success, provider failure, timeout, or interruption.
  - Route managed outcomes before normal provider success/failure routing.
- Modify: `orchestrator/workflow/outcomes.py`
  - Preserve structured `managed_jobs` result data through `OutcomeRecorder.to_step_result()`.
- Modify: `orchestrator/workflow/resume_planner.py`
  - Preserve restart to the same provider step when a managed step failed resumably during recovery.
- Modify: `orchestrator/state.py`
  - Persist structured `managed_jobs` step result data and recovery phase metadata.

### Tests and Fixtures

- Create: `tests/test_managed_jobs_loader.py`
- Modify: `tests/test_workflow_ir_lowering.py`
- Create: `tests/test_managed_provider_runtime.py`
- Create: `tests/test_managed_provider_execution.py`
- Create: `tests/test_managed_jobs_audit.py`
- Create: `tests/test_managed_jobs_policy.py`
- Create: `tests/test_managed_jobs_watcher.py`
- Create: `tests/test_managed_job_runner.py`
- Create: `tests/test_managed_job_shims.py`
- Modify as needed: `tests/test_provider_execution.py`
- Modify as needed: `tests/test_resume_command.py`
- Create: `workflows/examples/managed_provider_jobs_demo.yaml`

## Implementation Tasks

### Task 1: Pin the DSL Spec and Version Gate

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/providers.md`
- Modify: `specs/state.md`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `orchestrator/loader.py`
- Test: `tests/test_managed_jobs_loader.py`

- [ ] **Step 1: Add failing loader tests for version gating**

Add tests that assert `managed_jobs` is rejected before version `2.13` and accepted at version `2.13` on a provider step.

```python
def test_managed_jobs_requires_v213(tmp_path):
    workflow = {
        "version": "2.12",
        "providers": {"impl": {"command": ["python", "-c", "print('ok')"], "input_mode": "stdin"}},
        "steps": [
            {
                "name": "Execute",
                "provider": "impl",
                "managed_jobs": {
                    "policy": "workflows/managed_jobs/policy.yaml",
                    "watch_roots": ["scripts/training"],
                    "backend": "auto",
                    "poll_budget_sec": 60,
                    "on": {"complete": "Review", "failed": "Fix", "invalid": "Fix", "outstanding": "fail_resumable"},
                },
            },
            {"name": "Review", "command": "true"},
            {"name": "Fix", "command": "true"},
        ],
    }
    with pytest.raises(ValidationError, match="managed_jobs.*version"):
        load_workflow_dict(workflow, base_dir=tmp_path)
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `pytest tests/test_managed_jobs_loader.py::test_managed_jobs_requires_v213 -q`

Expected: FAIL because `managed_jobs` is unknown or not version-gated yet.

- [ ] **Step 3: Add version `2.13` to loader constants**

In `orchestrator/loader.py`, add `2.13` to `SUPPORTED_VERSIONS` and `VERSION_ORDER`. Keep the surrounding ordering style unchanged.

- [ ] **Step 4: Implement minimal schema recognition**

Update step validation so `managed_jobs` is an allowed field only for DSL version `2.13` and later. Do not implement full runtime behavior yet.

- [ ] **Step 5: Run the focused loader test**

Run: `pytest tests/test_managed_jobs_loader.py::test_managed_jobs_requires_v213 -q`

Expected: PASS.

- [ ] **Step 6: Document the version gate**

Add the `managed_jobs` field shape to `specs/dsl.md`. Update `specs/providers.md` to state that the runtime wraps the selected provider command and provider templates remain ordinary provider templates. Update `docs/workflow_drafting_guide.md` with authoring guidance that manual `RecoverManagedJobs` gates are fallback-only.

- [ ] **Step 7: Commit scoped changes**

Only commit if the implementation session is using commits. Stage the loader, tests, and docs changed in this task only.

```bash
git add orchestrator/loader.py tests/test_managed_jobs_loader.py specs/dsl.md specs/providers.md specs/state.md specs/acceptance/index.md docs/workflow_drafting_guide.md
git commit -m "feat: gate managed_jobs provider DSL"
```

### Task 2: Validate `managed_jobs` Shape and Targets

**Files:**
- Modify: `orchestrator/loader.py`
- Test: `tests/test_managed_jobs_loader.py`

- [ ] **Step 1: Add failing validation tests**

Cover these cases:

- `managed_jobs` on command step fails.
- `managed_jobs` on adjudicated provider step fails.
- provider `retries` plus `managed_jobs` fails.
- ordinary step-level `on` plus `managed_jobs` fails in v1.
- missing `policy` fails.
- empty `watch_roots` fails.
- absolute or parent-escaping `policy` fails.
- absolute or parent-escaping `watch_roots` fail.
- invalid `backend` fails.
- `poll_budget_sec <= 0` fails.
- `poll_budget_sec > timeout_sec` fails when `timeout_sec` is present.
- missing `managed_jobs.on.complete`, `failed`, `invalid`, or `outstanding` fails.
- route target names under `complete`, `failed`, and `invalid` must exist.
- `outstanding` rejects anything except `fail_resumable`.

- [ ] **Step 2: Run collect-only for the new test module**

Run: `pytest tests/test_managed_jobs_loader.py --collect-only -q`

Expected: pytest collects the new tests without import errors.

- [ ] **Step 3: Run the validation tests to verify failures**

Run: `pytest tests/test_managed_jobs_loader.py -q`

Expected: FAIL on the newly asserted validation behavior.

- [ ] **Step 4: Add validation helpers**

In `orchestrator/loader.py`, add a small `_validate_managed_jobs()` helper. Reuse existing path-safety helper logic instead of introducing separate path parsing rules.

Suggested shape:

```python
def _validate_managed_jobs(step: Mapping[str, Any], *, step_names: set[str], version: str, context: str) -> None:
    config = step.get("managed_jobs")
    if config is None:
        return
    if not _version_at_least(version, "2.13"):
        raise ValidationError(f"{context}: managed_jobs requires workflow version 2.13 or later")
    if "provider" not in step or "adjudicated_provider" in step:
        raise ValidationError(f"{context}: managed_jobs is valid only on provider steps")
    if "retries" in step:
        raise ValidationError(f"{context}: managed_jobs cannot be combined with provider retries")
    if "on" in step:
        raise ValidationError(f"{context}: managed_jobs cannot be combined with ordinary on handlers in version 2.13")
    # validate policy, watch_roots, backend, poll_budget_sec, and on routes here
```

- [ ] **Step 5: Wire target validation**

Extend the existing goto target validation path so `managed_jobs.on.complete`, `managed_jobs.on.failed`, and `managed_jobs.on.invalid` are checked with the same target set as ordinary `on.*.goto`.

- [ ] **Step 6: Run the loader test module**

Run: `pytest tests/test_managed_jobs_loader.py -q`

Expected: PASS.

- [ ] **Step 7: Run nearby loader regression tests**

Run: `pytest tests/test_loader_validation.py tests/test_managed_jobs_loader.py -q`

Expected: PASS.

- [ ] **Step 8: Commit scoped changes**

```bash
git add orchestrator/loader.py tests/test_managed_jobs_loader.py
git commit -m "test: validate managed_jobs workflow schema"
```

### Task 3: Carry `managed_jobs` Through AST and Executable IR

**Files:**
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `tests/workflow_bundle_helpers.py`
- Modify: `tests/test_workflow_ir_lowering.py`

- [ ] **Step 1: Add failing IR preservation tests**

Add a workflow lowering test that loads a managed provider step and asserts the executable provider config contains:

- `policy`
- `watch_roots`
- `backend`
- `poll_budget_sec`
- managed outcome route targets

- [ ] **Step 2: Run the focused lowering test**

Run: `pytest tests/test_workflow_ir_lowering.py::test_managed_jobs_lowers_to_provider_config -q`

Expected: FAIL because the AST and IR do not carry `managed_jobs` yet.

- [ ] **Step 3: Add surface dataclasses**

Add focused dataclasses in `orchestrator/workflow/surface_ast.py`:

```python
@dataclass(frozen=True)
class SurfaceManagedJobsRoutes:
    complete: str
    failed: str
    invalid: str
    outstanding: str


@dataclass(frozen=True)
class SurfaceManagedJobsConfig:
    policy: str
    watch_roots: tuple[str, ...]
    backend: str
    poll_budget_sec: int
    on: SurfaceManagedJobsRoutes
```

Add `managed_jobs: SurfaceManagedJobsConfig | None = None` to the surface provider step representation.

- [ ] **Step 4: Parse surface config in elaboration**

Add `_parse_surface_managed_jobs_config()` in `orchestrator/workflow/elaboration.py`. Convert lists to tuples and preserve exact strings after normal workflow substitution parsing.

- [ ] **Step 5: Add executable IR dataclasses**

In `orchestrator/workflow/executable_ir.py`, add equivalent executable config dataclasses:

```python
@dataclass(frozen=True)
class ManagedJobsRoutes:
    complete: str
    failed: str
    invalid: str
    outstanding: str


@dataclass(frozen=True)
class ManagedJobsConfig:
    policy: str
    watch_roots: tuple[str, ...]
    backend: str
    poll_budget_sec: int
    on: ManagedJobsRoutes
```

Add `managed_jobs: ManagedJobsConfig | None = None` to `ProviderStepConfig`.

- [ ] **Step 6: Lower surface to executable config**

In `orchestrator/workflow/lowering.py`, map surface config into `ProviderStepConfig.managed_jobs`.

- [ ] **Step 7: Preserve compatibility projections**

Update `_compatibility_step_definition()` and `tests/workflow_bundle_helpers.py` so serialized/deserialized workflow bundles keep `managed_jobs` intact.

- [ ] **Step 8: Run lowering and bundle tests**

Run: `pytest tests/test_workflow_ir_lowering.py tests/test_workflow_bundle_helpers.py -q`

Expected: PASS. If `tests/test_workflow_bundle_helpers.py` is a helper-only file, run the test module that imports it and covers materialization.

- [ ] **Step 9: Commit scoped changes**

```bash
git add orchestrator/workflow/surface_ast.py orchestrator/workflow/elaboration.py orchestrator/workflow/executable_ir.py orchestrator/workflow/lowering.py tests/workflow_bundle_helpers.py tests/test_workflow_ir_lowering.py
git commit -m "feat: lower managed_jobs into provider IR"
```

### Task 4: Add Managed-Job Models, Audit, and Policy Loading

**Files:**
- Create: `orchestrator/managed_jobs/__init__.py`
- Create: `orchestrator/managed_jobs/models.py`
- Create: `orchestrator/managed_jobs/audit.py`
- Create: `orchestrator/managed_jobs/policy.py`
- Create: `orchestrator/managed_jobs/extractors.py`
- Create: `orchestrator/managed_jobs/identity.py`
- Test: `tests/test_managed_jobs_audit.py`
- Test: `tests/test_managed_jobs_policy.py`

- [ ] **Step 1: Write failing audit tests**

Test that audit helpers:

- create parent directories;
- append JSONL events with required fields;
- reject unknown event types;
- read valid events back in order;
- fail on malformed JSON with a useful error.

- [ ] **Step 2: Write failing policy tests**

Test that policy loading:

- rejects missing policy files;
- rejects unparsable YAML;
- rejects path escapes in managed entries;
- rejects `force_managed` or `auto_managed` entries that provide neither explicit job metadata nor a named extractor;
- rejects managed entries whose `state_root_template`, `verify_files`, or `output_root_arg` cannot be derived;
- rejects named extractors that are unknown, unversioned, or missing required metadata outputs;
- accepts explicit job metadata with `name_template`, `state_root_template`, `output_root_arg`, `verify_files`, and declared snapshot inputs;
- accepts a named extractor that derives state root, output root handling, verification targets, config paths, and snapshot inputs;
- accepts a minimal unmanaged policy entry with backend defaults.

- [ ] **Step 3: Run collect-only**

Run: `pytest tests/test_managed_jobs_audit.py tests/test_managed_jobs_policy.py --collect-only -q`

Expected: pytest collects the new tests.

- [ ] **Step 4: Run tests to verify failures**

Run: `pytest tests/test_managed_jobs_audit.py tests/test_managed_jobs_policy.py -q`

Expected: FAIL because modules do not exist yet.

- [ ] **Step 5: Implement models**

In `models.py`, define enums and dataclasses used by runtime and tests.

```python
class ManagedJobOutcome(str, Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    INVALID = "INVALID"
    OUTSTANDING = "OUTSTANDING"


@dataclass(frozen=True)
class ManagedJobsRuntimeConfig:
    policy_path: Path
    watch_roots: tuple[Path, ...]
    backend: str
    poll_budget_sec: int
    audit_path: Path
```

Also define the managed-entry metadata contract:

```python
@dataclass(frozen=True)
class ManagedJobMetadata:
    name_template: str
    state_root_template: str
    output_root_arg: str | None
    verify_files: tuple[str, ...]
    snapshot_roots: tuple[str, ...]
    config_globs: tuple[str, ...]
    extractor: str | None = None
    extractor_version: str | None = None
```

Policy loading must fail a managed entry when this metadata cannot be produced directly or through a named extractor.

- [ ] **Step 6: Implement audit helpers**

Keep `audit.py` narrow: append validated dict events and read them back. Do not put recovery polling here.

- [ ] **Step 7: Implement policy loader**

Use the repo's existing YAML dependency and path-safety conventions. Return a typed policy object with no side effects. Managed entries must normalize into `ManagedJobMetadata`; entries that cannot produce deterministic state and verification metadata are invalid.

- [ ] **Step 8: Implement extractor and identity primitives**

In `extractors.py`, define a registry interface for named extractors. In `identity.py`, add helpers that compute stable hashes from:

- normalized payload command and arguments;
- source file content;
- declared config files;
- extractor id and version;
- policy entry content;
- snapshot manifest inputs.

- [ ] **Step 9: Run audit and policy tests**

Run: `pytest tests/test_managed_jobs_audit.py tests/test_managed_jobs_policy.py -q`

Expected: PASS.

- [ ] **Step 10: Commit scoped changes**

```bash
git add orchestrator/managed_jobs tests/test_managed_jobs_audit.py tests/test_managed_jobs_policy.py
git commit -m "feat: add managed job audit and policy primitives"
```

### Task 5: Add Watcher and Pending Policy Classification

**Files:**
- Create: `orchestrator/managed_jobs/classifier.py`
- Create: `orchestrator/managed_jobs/pending_policy.py`
- Create: `orchestrator/managed_jobs/watcher.py`
- Modify: `orchestrator/managed_jobs/models.py`
- Modify: `orchestrator/managed_jobs/policy.py`
- Test: `tests/test_managed_jobs_watcher.py`

- [ ] **Step 1: Write failing watcher tests**

Cover:

- a new Python entrypoint created under a configured `watch_root` is classified before the provider child exits;
- an edited existing entrypoint under a configured `watch_root` is reclassified;
- files outside configured `watch_roots` are ignored;
- path escapes through symlinks or `..` are rejected;
- a heavy training entrypoint that matches managed policy writes a pending-policy record before it can be executed through a shim;
- a heavy training entrypoint that lacks derivable `ManagedJobMetadata` is recorded as invalid and causes managed routing to fail rather than run unmanaged;
- explicit `force_local` or unmanaged policy entries are preserved with a reason;
- conflicting policy decisions fail the managed provider step before recovery routing.

- [ ] **Step 2: Run collect-only**

Run: `pytest tests/test_managed_jobs_watcher.py --collect-only -q`

Expected: pytest collects the new watcher tests.

- [ ] **Step 3: Run tests to verify failures**

Run: `pytest tests/test_managed_jobs_watcher.py -q`

Expected: FAIL because watcher and pending-policy modules do not exist.

- [ ] **Step 4: Implement deterministic classification**

In `classifier.py`, implement a pure function that accepts a path, file content metadata, base policy, and watched roots. It returns a typed decision such as `managed`, `unmanaged`, `force_local`, or `invalid`. Keep heuristic classification behind a small function so later policy changes do not leak into watcher lifecycle code.

If classification returns `managed`, it must include a complete `ManagedJobMetadata` object or named extractor output. If metadata cannot be derived, classification returns `invalid`.

- [ ] **Step 5: Implement pending-policy sidecar**

In `pending_policy.py`, append and read classification decisions from a run-owned sidecar. Use atomic replace or append-with-fsync semantics consistent with existing state-writing style. The sidecar should record source path, decision, reason, timestamp, and policy version/hash when available.

- [ ] **Step 6: Implement watcher lifecycle**

In `watcher.py`, provide a polling watcher by default so tests do not need platform-specific filesystem notification dependencies. It should:

- snapshot watched roots before provider launch;
- poll for creates and edits while the child provider runs;
- classify changed files;
- append pending-policy decisions;
- surface invalid/conflicting decisions to the supervising guard.

- [ ] **Step 7: Run watcher tests**

Run: `pytest tests/test_managed_jobs_watcher.py tests/test_managed_jobs_policy.py -q`

Expected: PASS.

- [ ] **Step 8: Commit scoped changes**

```bash
git add orchestrator/managed_jobs/classifier.py orchestrator/managed_jobs/pending_policy.py orchestrator/managed_jobs/watcher.py orchestrator/managed_jobs/models.py orchestrator/managed_jobs/policy.py tests/test_managed_jobs_watcher.py
git commit -m "feat: classify watched provider job entrypoints"
```

### Task 6: Wrap Provider Invocations Without Changing Provider Templates

**Files:**
- Create: `orchestrator/managed_jobs/runtime.py`
- Create: `orchestrator/managed_jobs/provider_guard.py`
- Modify: `orchestrator/providers/types.py`
- Modify: `orchestrator/providers/executor.py`
- Test: `tests/test_managed_provider_runtime.py`

- [ ] **Step 1: Write failing wrapper tests**

Test that `ManagedProviderRuntime.wrap_invocation()`:

- keeps prompt, input mode, timeout, output path, and environment from the original invocation;
- prefixes the selected provider command with the provider guard entrypoint;
- passes policy path, audit path, watch roots, backend, state root, shim directory, and pending-policy sidecar path;
- does not expand or alter `${SESSION_ID}` itself;
- wraps a resume provider-session command exactly the same way as a fresh command once the provider layer has selected it;
- marks the invocation as requiring process-group/session termination on timeout.

- [ ] **Step 2: Run the focused wrapper test**

Run: `pytest tests/test_managed_provider_runtime.py::test_wraps_provider_invocation_with_guard -q`

Expected: FAIL because runtime wrapper does not exist.

- [ ] **Step 3: Implement runtime config resolution**

In `runtime.py`, add a resolver that receives:

- run root;
- workflow base directory;
- step name;
- step visit count;
- executable `ManagedJobsConfig`;
- selected provider invocation.

It should create a deterministic audit path like:

```text
.orchestrate/runs/<run_id>/managed_jobs/<step-name>/<visit-count>/managed_job_events.jsonl
```

- [ ] **Step 4: Implement invocation wrapping**

Add `wrap_invocation()` that returns a copied `ProviderInvocation` with a wrapped command and merged environment.

Suggested command shape:

```python
[
    sys.executable,
    "-m",
    "orchestrator.managed_jobs.provider_guard",
    "--policy", str(policy_path),
    "--audit-path", str(audit_path),
    "--state-root", str(state_root),
    "--pending-policy", str(pending_policy_path),
    "--backend", backend,
    "--shim-dir", str(shim_dir),
    "--watch-root", str(watch_root_1),
    "--watch-root", str(watch_root_2),
    "--",
    *original.command,
]
```

- [ ] **Step 5: Implement guard CLI argument parsing**

Before implementing guard parsing, add process-tree timeout support in `orchestrator/providers/executor.py`. Managed invocations should carry a flag such as `terminate_process_tree=True`; the executor must start those invocations in their own process group/session. On timeout, graceful termination and hard-kill fallback must target the process group, not only the direct guard PID.

Add a test that launches a guard-like parent which starts a child process and sleeps. The timeout assertion must prove the child process is gone after timeout. Already-submitted managed jobs are not killed through this path; they are recovered from persisted managed-job and scheduler state.

In `provider_guard.py`, parse arguments, install the managed environment variables, prepend shim directory to `PATH`, start the watcher, spawn the child provider process, reconcile watcher/pending-policy state, and exit with the child provider status unless watcher or reconciliation failures require a managed infrastructure failure. Do not `exec` the provider in v1: `exec` would replace the guard process and drop live watcher supervision before the provider runs.

- [ ] **Step 6: Run wrapper tests**

Run: `pytest tests/test_managed_provider_runtime.py tests/test_provider_execution.py -q`

Expected: PASS.

- [ ] **Step 7: Commit scoped changes**

```bash
git add orchestrator/managed_jobs/runtime.py orchestrator/managed_jobs/provider_guard.py orchestrator/providers/types.py orchestrator/providers/executor.py tests/test_managed_provider_runtime.py tests/test_provider_execution.py
git commit -m "feat: wrap provider invocations for managed jobs"
```

### Task 7: Add Managed Recovery Semantics

**Files:**
- Create: `orchestrator/managed_jobs/recovery.py`
- Modify: `orchestrator/managed_jobs/runtime.py`
- Test: `tests/test_managed_provider_runtime.py`

- [ ] **Step 1: Write failing recovery tests**

Cover:

- no audited jobs returns `COMPLETE`;
- completed and verified jobs return `COMPLETE`;
- jobs whose state lacks required metadata such as `job_identity_hash`, `state_root`, snapshot manifest, or `verify_files` return `INVALID`;
- jobs whose verification targets cannot be tied to the recorded identity return `INVALID`;
- terminal failed jobs return `FAILED`;
- malformed or policy-invalid events return `INVALID`;
- jobs still pending after poll budget return `OUTSTANDING`;
- recovery never calls a submit/resubmit function for existing audited jobs.

- [ ] **Step 2: Run recovery tests to verify failures**

Run: `pytest tests/test_managed_provider_runtime.py::test_recovery_no_audited_jobs_is_complete -q`

Expected: FAIL because recovery does not exist.

- [ ] **Step 3: Implement recovery summary type**

Use a structured summary with at least:

```json
{
  "managed_job_outcome": "COMPLETE",
  "recovery_status": "COMPLETE",
  "audit_path": ".orchestrate/runs/.../managed_job_events.jsonl",
  "jobs": []
}
```

- [ ] **Step 4: Implement recovery polling**

Keep the first implementation deterministic and testable:

- read audit events;
- group by job state path or job id;
- inspect local state files when present;
- map terminal state to `COMPLETE`, `FAILED`, or `INVALID`;
- sleep only through an injectable clock/sleeper so tests do not wait in real time.

- [ ] **Step 5: Run recovery tests**

Run: `pytest tests/test_managed_provider_runtime.py -q`

Expected: PASS.

- [ ] **Step 6: Commit scoped changes**

```bash
git add orchestrator/managed_jobs/recovery.py orchestrator/managed_jobs/runtime.py tests/test_managed_provider_runtime.py
git commit -m "feat: recover managed provider jobs"
```

### Task 8: Integrate Managed Runtime into Provider Step Execution

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/lowering.py`
- Test: `tests/test_managed_provider_execution.py`
- Modify as needed: `tests/test_provider_execution.py`

- [ ] **Step 1: Write failing executor tests**

Use a fake provider executor and fake managed runtime to assert:

- provider invocation is wrapped when `ProviderStepConfig.managed_jobs` is present;
- provider invocation is not wrapped when absent;
- managed provider retry policy is forced to zero even when `self.max_retries` is non-zero;
- recovery runs after provider success;
- recovery runs after provider non-zero exit;
- recovery runs after timeout/interruption paths that currently create provider failure results;
- managed outcome `COMPLETE` routes to `managed_jobs.on.complete`;
- `FAILED` routes to `managed_jobs.on.failed`;
- `INVALID` routes to `managed_jobs.on.invalid`.

- [ ] **Step 2: Run the focused executor test**

Run: `pytest tests/test_managed_provider_execution.py::test_managed_provider_wraps_invocation -q`

Expected: FAIL because executor is not wired to the managed runtime.

- [ ] **Step 3: Add a managed runtime seam in executor**

In `orchestrator/workflow/executor.py`, create or inject `ManagedProviderRuntime` at the point where the provider invocation has already been prepared and before `_execute_provider_invocation()` runs.

- [ ] **Step 4: Wrap selected invocation only**

Ensure wrapping happens after existing provider-session fresh/resume command selection. Do not wrap provider template commands earlier in provider config loading.

- [ ] **Step 5: Disable provider relaunch retries for managed steps**

In `orchestrator/workflow/executor.py`, change provider retry policy construction so managed provider steps use `RetryPolicy.for_command(0)` regardless of global provider retry settings. This must happen before `_execute_provider_invocation()` so a guarded provider timeout or non-zero exit cannot relaunch the provider child before managed recovery runs.

The behavior being fixed is the current default branch:

```python
retry_policy = RetryPolicy.for_provider(
    max_retries=self.max_retries,
    delay_ms=self.retry_delay_ms,
)
```

Managed provider steps must bypass that branch.

- [ ] **Step 6: Run recovery before normal provider routing**

After provider execution returns, call managed recovery if the step is managed. Persist the recovery summary into the step result before control-flow routing.

- [ ] **Step 7: Add managed transfers**

In `orchestrator/workflow/lowering.py`, add typed transfers for managed outcomes so executor routing can select them without parsing raw YAML.

Suggested transfer keys:

```python
"managed_jobs_complete_goto"
"managed_jobs_failed_goto"
"managed_jobs_invalid_goto"
```

- [ ] **Step 8: Extend control-flow routing**

In `orchestrator/workflow/executor.py`, update the route resolver so a managed provider result with `managed_job_outcome` uses managed transfers. Since v1 validation rejects ordinary step-level `on` on managed provider steps, there is no `on.always` composition to preserve for managed steps.

- [ ] **Step 9: Run executor tests**

Run: `pytest tests/test_managed_provider_execution.py tests/test_provider_execution.py -q`

Expected: PASS.

- [ ] **Step 10: Commit scoped changes**

```bash
git add orchestrator/workflow/executor.py orchestrator/workflow/lowering.py tests/test_managed_provider_execution.py tests/test_provider_execution.py
git commit -m "feat: execute managed provider recovery routes"
```

### Task 9: Persist Managed Recovery State and Resume Without Relaunch

**Files:**
- Modify: `orchestrator/state.py`
- Modify: `orchestrator/workflow/outcomes.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/resume_planner.py`
- Test: `tests/test_managed_provider_execution.py`
- Modify: `tests/test_resume_command.py`

- [ ] **Step 1: Write failing resume tests**

Simulate a managed provider step that reaches `OUTSTANDING` after poll budget. Assert:

- state marks the current step as resumable recovery, not as a provider relaunch;
- `orchestrator resume <run_id>` re-enters recovery for the same step visit;
- provider executor is not called on resume;
- recovery is called with the same audit path;
- `OutcomeRecorder.to_step_result()` preserves `managed_jobs.phase == "recovery"` into the final persisted `state.json`;
- if recovery later returns `COMPLETE`, routing continues to `managed_jobs.on.complete`.

- [ ] **Step 2: Run the focused resume test**

Run: `pytest tests/test_resume_command.py::test_managed_provider_resume_reenters_recovery_without_relaunch -q`

Expected: FAIL because state and resume planner do not distinguish recovery phase yet.

- [ ] **Step 3: Extend step result schema**

In `orchestrator/state.py`, add a structured optional field:

```python
managed_jobs: Optional[Dict[str, Any]] = None
```

Keep backward compatibility in state loading. Unknown older state should continue loading with `managed_jobs=None`.

- [ ] **Step 4: Preserve managed_jobs through outcome recording**

In `orchestrator/workflow/outcomes.py`, update `OutcomeRecorder.to_step_result()` to pass `managed_jobs=result.get("managed_jobs")` into `StepResult`. Add a regression assertion that a dict result converted through `OutcomeRecorder.to_step_result()` and persisted into `state.json` still contains the managed recovery phase metadata.

- [ ] **Step 5: Persist recovery phase metadata**

When recovery returns `OUTSTANDING`, persist enough state to resume recovery:

```json
{
  "managed_jobs": {
    "phase": "recovery",
    "audit_path": ".../managed_job_events.jsonl",
    "outcome": "OUTSTANDING",
    "poll_budget_sec": 82800
  }
}
```

- [ ] **Step 6: Teach executor to resume recovery**

At provider-step start, detect current step metadata indicating `managed_jobs.phase == "recovery"`. If present, skip provider invocation and call recovery directly with the saved audit path.

- [ ] **Step 7: Keep resume planner behavior narrow**

Prefer not to rewrite resume planning if the existing planner already restarts the non-terminal current step. Only add planner metadata handling if tests prove the planner loses the current managed step.

- [ ] **Step 8: Run resume tests**

Run: `pytest tests/test_resume_command.py tests/test_managed_provider_execution.py -q`

Expected: PASS.

- [ ] **Step 9: Commit scoped changes**

```bash
git add orchestrator/state.py orchestrator/workflow/outcomes.py orchestrator/workflow/executor.py orchestrator/workflow/resume_planner.py tests/test_resume_command.py tests/test_managed_provider_execution.py
git commit -m "feat: resume managed provider recovery"
```

### Task 10: Implement Runner and Shim Behavior

**Files:**
- Create: `orchestrator/managed_jobs/runner.py`
- Create: `orchestrator/managed_jobs/backends.py`
- Create: `orchestrator/managed_jobs/snapshot.py`
- Create: `orchestrator/managed_jobs/shims.py`
- Modify: `orchestrator/managed_jobs/provider_guard.py`
- Test: `tests/test_managed_job_runner.py`
- Test: `tests/test_managed_job_shims.py`
- Test: `tests/test_managed_job_snapshot.py`

- [ ] **Step 1: Write failing shim tests**

Cover:

- shim directory is created under the run-owned managed-jobs directory;
- shim `python` can find the real Python executable;
- `conda run ... python ...` is parsed and routed through the managed runner when the payload is supported;
- `uv run python ...` is parsed and routed through the managed runner when the payload is supported;
- `uv run torchrun ...` is parsed and routed through the managed runner when the payload is supported;
- unsupported `conda` and `uv` forms fail closed with a clear unmanaged/unsupported diagnostic rather than bypassing management silently;
- guard environment includes `MANAGED_JOB_SHIM_DIR`;
- runner reads pending-policy decisions produced by the watcher before falling back to base policy;
- `conda activate ... && python ...` can be supported only when the managed shell helper restores the shim directory after activation.

- [ ] **Step 2: Write failing runner tests**

Cover:

- policy-managed entrypoint writes audit events and job state;
- explicitly unmanaged entrypoint runs locally;
- `force_local` with reason bypasses management;
- conflicting policy entries fail before launching;
- managed entries without complete job metadata or named extractor output fail before launching;
- job identity includes normalized payload arguments, source hashes, config hashes, extractor identity, policy-entry hash, and snapshot manifest inputs;
- local backend records the same identity metadata as Slurm backend;
- backend `local` runs through local subprocess;
- backend `slurm` builds a submission request without requiring a live Slurm cluster in unit tests;
- generated Slurm scripts run from an immutable snapshot workspace or verify recorded source/config hashes before executing.

- [ ] **Step 3: Run collect-only**

Run: `pytest tests/test_managed_job_runner.py tests/test_managed_job_shims.py tests/test_managed_job_snapshot.py --collect-only -q`

Expected: pytest collects the new tests.

- [ ] **Step 4: Run tests to verify failures**

Run: `pytest tests/test_managed_job_runner.py tests/test_managed_job_shims.py tests/test_managed_job_snapshot.py -q`

Expected: FAIL because runner and shims do not exist.

- [ ] **Step 5: Implement shim materialization**

Create shims as small scripts that call `orchestrator.managed_jobs.runner`. Keep generated script contents deterministic so tests can inspect them without relying on prompt text. Include parser coverage for `python`, `python3`, `torchrun`, supported `conda run ... <payload>`, and supported `uv run ... <payload>` forms.

- [ ] **Step 6: Implement runner decision flow**

Runner flow:

1. Load policy.
2. Load pending-policy sidecar decisions for the current run.
3. Classify target command or script path, with pending-policy decisions taking precedence over generic heuristics and with explicit policy conflicts treated as invalid.
4. Resolve complete managed job metadata from explicit policy fields or a named extractor.
5. If metadata is missing or incomplete for a managed decision, fail invalid before launching.
6. Compute job identity from normalized argv, source/config/extractor/policy hashes, and snapshot manifest inputs.
7. If unmanaged, execute locally.
8. If managed, create job state directory under the derived `state_root`.
9. Materialize an immutable execution snapshot for managed backend execution.
10. Append audit event and write `job_state.json` with identity, snapshot, backend, and verification metadata.
11. Submit through selected backend.
12. Wait or return according to configured mode.

- [ ] **Step 7: Implement backend interfaces narrowly**

For the first implementation, keep backend code behind small functions or classes that can be tested without Slurm:

```python
class ManagedJobBackend(Protocol):
    def submit(self, request: ManagedJobRequest) -> ManagedJobSubmission:
        ...
```

Slurm backend requirements:

- generated Slurm scripts must `cd` into the snapshot workspace and execute staged payload paths, or must perform a preflight hash check for every recorded source/config input before executing;
- the script records snapshot manifest path, job identity hash, submission nonce, stdout/stderr paths, and scheduler id into job state;
- recovery refuses to verify a job whose scheduler state or verification artifacts cannot be tied back to the recorded job identity.

- [ ] **Step 8: Run runner and shim tests**

Run: `pytest tests/test_managed_job_runner.py tests/test_managed_job_shims.py tests/test_managed_job_snapshot.py -q`

Expected: PASS.

- [ ] **Step 9: Commit scoped changes**

```bash
git add orchestrator/managed_jobs/runner.py orchestrator/managed_jobs/backends.py orchestrator/managed_jobs/snapshot.py orchestrator/managed_jobs/shims.py orchestrator/managed_jobs/provider_guard.py tests/test_managed_job_runner.py tests/test_managed_job_shims.py tests/test_managed_job_snapshot.py
git commit -m "feat: add managed job runner and shims"
```

### Task 11: Add Example Workflow and Smoke Coverage

**Files:**
- Create: `workflows/examples/managed_provider_jobs_demo.yaml`
- Create or modify fixture files under `tests/fixtures/managed_jobs/`
- Modify: `specs/acceptance/index.md`
- Modify: `docs/workflow_drafting_guide.md`

- [ ] **Step 1: Add an example workflow**

Create a minimal example with one managed provider step, one review step, and one fix step. Use a local fake provider command and a temporary test root so the example does not require a real Slurm cluster.

- [ ] **Step 2: Add a smoke test for the example**

Add a test that loads and validates the example workflow. If the repo has an existing example workflow smoke suite, add this workflow there instead of creating a new test runner.

- [ ] **Step 3: Run example validation**

Run: `pytest tests/test_managed_jobs_loader.py tests/test_workflow_ir_lowering.py -q`

Expected: PASS.

- [ ] **Step 4: Run a local orchestrator smoke**

Run the narrowest available smoke command for examples in this repo. Prefer an existing smoke test if present. If using the CLI directly, run from repo root and use a fake/local provider configuration.

Expected: The workflow reaches the managed provider step, writes a managed-job audit sidecar, runs recovery, and routes according to `managed_jobs.on.complete`.

- [ ] **Step 5: Update acceptance criteria**

In `specs/acceptance/index.md`, add acceptance bullets for:

- schema validation;
- provider wrapping;
- provider process-tree timeout cleanup;
- watcher classification and pending-policy reconciliation;
- managed-entry metadata or extractor validation;
- immutable source/config snapshot or preflight hash verification for Slurm jobs;
- supported `conda run` and `uv run` shim payload forms;
- recovery after success/failure/timeout;
- outcome routing;
- resumable outstanding jobs;
- no provider relaunch on resume.

- [ ] **Step 6: Commit scoped changes**

```bash
git add workflows/examples/managed_provider_jobs_demo.yaml tests/fixtures/managed_jobs specs/acceptance/index.md docs/workflow_drafting_guide.md
git commit -m "docs: add managed provider example and acceptance"
```

### Task 12: Full Verification Pass

**Files:**
- No new files expected.

- [ ] **Step 1: Run collect-only for added and changed tests**

Run:

```bash
pytest tests/test_managed_jobs_loader.py tests/test_managed_jobs_audit.py tests/test_managed_jobs_policy.py tests/test_managed_jobs_watcher.py tests/test_managed_provider_runtime.py tests/test_managed_provider_execution.py tests/test_managed_job_runner.py tests/test_managed_job_shims.py tests/test_managed_job_snapshot.py --collect-only -q
```

Expected: pytest collects all new tests without import errors.

- [ ] **Step 2: Run focused managed-job suite**

Run:

```bash
pytest tests/test_managed_jobs_loader.py tests/test_managed_jobs_audit.py tests/test_managed_jobs_policy.py tests/test_managed_jobs_watcher.py tests/test_managed_provider_runtime.py tests/test_managed_provider_execution.py tests/test_managed_job_runner.py tests/test_managed_job_shims.py tests/test_managed_job_snapshot.py -q
```

Expected: PASS.

- [ ] **Step 3: Run adjacent regression tests**

Run:

```bash
pytest tests/test_loader_validation.py tests/test_workflow_ir_lowering.py tests/test_provider_execution.py tests/test_resume_command.py -q
```

Expected: PASS.

- [ ] **Step 4: Run orchestrator/demo smoke**

Run the existing orchestrator or example smoke check that is narrowest for workflow execution. Record the exact command and output in the implementation notes.

Expected: PASS, with a managed-job audit path and recovery summary visible in run artifacts or test output.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git status --short
git diff --stat
git diff --check
```

Expected: only scoped managed provider DSL/runtime/docs changes are present, and `git diff --check` reports no whitespace errors.

- [ ] **Step 6: Final commit if using commits**

```bash
git add orchestrator/managed_jobs orchestrator/loader.py orchestrator/workflow orchestrator/providers specs docs workflows tests
git commit -m "feat: add managed provider job semantics"
```

## Risks and Review Notes

- Provider-session wrapping must happen after the existing provider-session command selection. Wrapping provider templates earlier risks breaking `${SESSION_ID}` behavior.
- Managed provider steps must force provider retry policy to zero. Global provider retry settings must not relaunch a guarded provider before recovery runs.
- `OUTSTANDING` is not a routeable success outcome in the first version. It is a resumable failed state.
- Recovery must not resubmit audited jobs. It may poll and verify only.
- Managed routing must fail closed when state root, output root handling, verification files, source/config identity, or extractor metadata cannot be derived.
- `watch_roots` require a live supervised watcher while the provider child runs. The guard must spawn and supervise the provider child rather than `exec` it.
- Provider timeout must terminate the guarded process group/session. Killing only `provider_guard` is insufficient because the provider child could continue without watcher supervision.
- Slurm execution must use an immutable snapshot workspace or a generated script preflight hash check. Recovery state cannot claim identity for a job that ran mutable live-workspace code.
- Shim coverage includes supported `conda run ... python ...`, `uv run python ...`, and `uv run torchrun ...` forms in v1. Unsupported nested launcher forms fail closed.
- Ordinary step-level `on` is rejected for managed provider steps in v1. `managed_jobs.on` is the only routing surface for managed outcomes.
- Structured `managed_jobs` state must survive `OutcomeRecorder.to_step_result()` and final `state.json` persistence.
- The implementation should avoid broad prompt text assertions. Tests should assert behavior, state, routes, and artifact lineage.
- Keep managed-job policy YAML as policy data only. The workflow DSL owns the step-level runtime semantics.
- Do not broaden `consumes` to represent audit sidecars. The audit is runtime-owned state for the managed provider step.

## Execution Handoff

Recommended implementation mode is task-by-task with `superpowers:subagent-driven-development` when the user explicitly authorizes subagents, or `superpowers:executing-plans` for inline execution. The current repo instruction forbids worktrees, so implement from the existing checkout and keep commits scoped if commits are used.
