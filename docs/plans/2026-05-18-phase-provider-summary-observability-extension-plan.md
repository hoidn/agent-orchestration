# Phase And Provider Summary Observability Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing advisory step-summary feature so runs can emit agent-drafted summaries and performance judgments for phase boundaries and nontrivial provider steps.

**Architecture:** Keep observability runtime-only and advisory. Reuse the existing `SummaryObserver`, CLI summary configuration, and `.orchestrate/runs/<run_id>/summaries/` directory, but add summary profiles, summary kinds, richer deterministic snapshots, and an index file. Do not add a DSL key and do not let generated summaries affect workflow routing, state contracts, retries, or artifact lineage.

**Tech Stack:** Python stdlib, current `ProviderExecutor`, current `WorkflowExecutor`, current CLI argparse wiring, pytest, normative docs in `specs/`.

---

## Design Decisions

1. **No DSL surface in this tranche.**
   `specs/dsl.md` already says `observability` is not a DSL key. This extension stays behind CLI/runtime config.

2. **Existing behavior remains default.**
   `--step-summaries` continues to produce the current basic per-step summaries unless a new profile is selected.

3. **New profile: `phase-performance`.**
   `--summary-profile phase-performance` enables agent summaries for:
   - authored provider-like steps: `provider` and `adjudicated_provider`;
   - phase-like boundary steps: reusable `call` steps and `repeat_until` frames.

4. **Performance judgments are advisory.**
   The summarizer receives deterministic metrics such as status, exit code, duration, provider name, timeout, output contract surface, artifact names, and error context. It may judge bottlenecks or evidence quality in Markdown, but the runtime never parses that judgment for control flow.

5. **Summary artifacts are discoverable but non-authoritative.**
   Add `.orchestrate/runs/<run_id>/summaries/` as the user-facing hub for the whole run, with an aggregate `index.json`, `README.md`, and `run-summary.md`. Detailed summaries may still live beside nested call-frame state, but the root hub links to them. These files are observability views, not workflow state.

6. **Phase means runtime boundary, not project phase taxonomy.**
   In this tranche, "phase summary" means a reusable `call` step or `repeat_until` frame. The runtime does not infer arbitrary semantic phases from step names.

7. **Nontrivial provider step means authored agent/provider work.**
   In this tranche, summarize provider and adjudicated-provider steps. Command steps are excluded from `phase-performance` unless they are already summarized by the legacy basic profile.

8. **No worktree.**
   Repo policy says not to create worktrees. Implement in the current checkout and keep changes scoped.

## File Structure

- Modify `orchestrator/observability/summary.py`
  - Own summary kinds, prompt profiles, summary filenames, and `index.json` writes.
- Modify `orchestrator/workflow/executor.py`
  - Classify step summary kind and build richer snapshots for provider and phase summaries.
- Modify `orchestrator/cli/main.py`
  - Add `--summary-profile` to `run` and `resume`.
- Modify `orchestrator/cli/commands/run.py`
  - Persist `summary_profile` into runtime observability config.
- Modify `orchestrator/cli/commands/resume.py`
  - Preserve persisted profile and allow resume-time override.
- Modify `specs/cli.md`
  - Document `--summary-profile`.
- Modify `specs/observability.md`
  - Document phase/provider summary semantics, index file, advisory-only boundary, and performance-judgment scope.
- Modify `docs/workflow_drafting_guide.md`
  - Add author guidance for when to use `phase-performance`.
- Modify `tests/test_observability_summary_modes.py`
  - Cover profile prompts, filenames, index writing, and best-effort behavior.
- Modify `tests/test_cli_observability_config.py`
  - Cover CLI parsing/config persistence/resume override.
- Create `tests/test_observability_summary_profiles.py`
  - Unit-test executor snapshot classification without broad workflow runs.
- Optional modify `tests/e2e/test_e2e_observability_status_and_summary_modes.py`
  - Add a narrow smoke check only if existing e2e shape makes this cheap.

## Runtime Config Shape

Current config:

```json
{
  "step_summaries": {
    "enabled": true,
    "mode": "async",
    "provider": "claude_sonnet_summary",
    "timeout_sec": 120,
    "max_input_chars": 12000,
    "best_effort": true
  }
}
```

Extended config:

```json
{
  "step_summaries": {
    "enabled": true,
    "mode": "async",
    "provider": "claude_sonnet_summary",
    "timeout_sec": 120,
    "max_input_chars": 12000,
    "best_effort": true,
    "profile": "phase-performance"
  }
}
```

Supported profiles:

- `basic`: current behavior, one concise factual summary for each emitted step.
- `phase-performance`: provider/phase summaries with explicit advisory performance judgment.

## Summary File Layout

Keep current basic filenames:

```text
.orchestrate/runs/<run_id>/summaries/<Step>.snapshot.json
.orchestrate/runs/<run_id>/summaries/<Step>.summary.md
```

For `phase-performance`, use summary-kind suffixes:

```text
.orchestrate/runs/<run_id>/summaries/<Step>.provider.snapshot.json
.orchestrate/runs/<run_id>/summaries/<Step>.provider.summary.md
.orchestrate/runs/<run_id>/summaries/<Step>.phase.snapshot.json
.orchestrate/runs/<run_id>/summaries/<Step>.phase.summary.md
.orchestrate/runs/<run_id>/summaries/index.json
.orchestrate/runs/<run_id>/summaries/README.md
.orchestrate/runs/<run_id>/summaries/run-summary.md
```

Nested call-frame summaries remain local to the frame, but are also recorded in
the root hub:

```text
.orchestrate/runs/<run_id>/call_frames/<frame>/summaries/<Step>.provider.summary.md
.orchestrate/runs/<run_id>/summaries/index.json
```

Aggregate index shape:

```json
{
  "schema": "orchestrator_summary_index/v1",
  "run_root": ".orchestrate/runs/<run_id>",
  "entries": [
    {
      "step_name": "ExecuteImplementation",
      "kind": "provider",
      "profile": "phase-performance",
      "status": "completed",
      "duration_ms": 12345,
      "frame_root": "call_frames/<frame>",
      "snapshot_path": "call_frames/<frame>/summaries/ExecuteImplementation.provider.snapshot.json",
      "summary_path": "call_frames/<frame>/summaries/ExecuteImplementation.provider.summary.md",
      "error_path": null
    }
  ]
}
```

Paths in the aggregate index are run-root-relative. Per-frame local indexes may
also exist for diagnostic use and keep paths relative to their frame root.

## Task 1: Extend CLI Config For Summary Profiles

**Files:**
- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `tests/test_cli_observability_config.py`

- [ ] **Step 1: Add failing run CLI parse test**

In `tests/test_cli_observability_config.py`, add:

```python
def test_run_parser_accepts_summary_profile():
    parser = create_parser()
    args = parser.parse_args(
        [
            "run",
            "workflow.yaml",
            "--summary-profile",
            "phase-performance",
        ]
    )

    assert args.summary_profile == "phase-performance"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
python -m pytest tests/test_cli_observability_config.py::test_run_parser_accepts_summary_profile -q
```

Expected: FAIL because `--summary-profile` is not registered.

- [ ] **Step 3: Add CLI flags**

In `orchestrator/cli/main.py`, add to both `run_parser` and `resume_parser`:

```python
parser.add_argument(
    "--summary-profile",
    choices=["basic", "phase-performance"],
    help="Summary prompt/snapshot profile. Defaults to basic.",
)
```

For `run_parser`, default should be `"basic"` only if summaries are enabled. It is fine for argparse to store `None` and let config construction default.

- [ ] **Step 4: Add failing config tests**

Add:

```python
def test_build_observability_config_persists_summary_profile():
    args = _base_run_args(Path("workflow.yaml"))
    args.summary_profile = "phase-performance"

    config = build_observability_config(args)

    assert config is not None
    assert config["step_summaries"]["enabled"] is True
    assert config["step_summaries"]["profile"] == "phase-performance"
```

Add a resume override assertion to the existing resume test or a new test:

```python
def test_resume_applies_summary_profile_override(...):
    ...
    assert persisted["observability"]["step_summaries"]["profile"] == "phase-performance"
```

- [ ] **Step 5: Implement config persistence**

In `orchestrator/cli/commands/run.py`, update `build_observability_config`:

```python
summary_profile = getattr(args, "summary_profile", None)
if summary_profile and not step_summaries_enabled:
    step_summaries_enabled = True
...
"profile": summary_profile or "basic",
```

In `orchestrator/cli/commands/resume.py`, merge the override into persisted config:

```python
if overrides.get("summary_profile") is not None:
    step_cfg["profile"] = overrides["summary_profile"]
```

- [ ] **Step 6: Run focused config tests**

Run:

```bash
python -m pytest tests/test_cli_observability_config.py -k "summary_profile or observability_config or resume_uses_persisted_observability" -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add orchestrator/cli/main.py orchestrator/cli/commands/run.py orchestrator/cli/commands/resume.py tests/test_cli_observability_config.py
git commit -m "feat: add summary observability profiles"
```

## Task 2: Add Summary Kinds, Prompt Profiles, And Index Writes

**Files:**
- Modify: `orchestrator/observability/summary.py`
- Modify: `tests/test_observability_summary_modes.py`

- [ ] **Step 1: Add failing tests for profile-specific filenames**

In `tests/test_observability_summary_modes.py`, add:

```python
def test_phase_performance_provider_summary_uses_kind_specific_files(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-profile"
    observer = SummaryObserver(
        run_root=run_root,
        provider_executor=_FakeProviderExecutor(result=_FakeProviderResult(stdout=b"profile summary")),
        provider_name="summary_provider",
        mode="sync",
        timeout_sec=30,
        best_effort=True,
        max_input_chars=12000,
        profile="phase-performance",
    )

    observer.emit(
        "ExecuteImplementation",
        {"step": {"name": "ExecuteImplementation", "summary_kind": "provider", "output": {"status": "completed"}}},
        summary_kind="provider",
    )

    assert (run_root / "summaries" / "ExecuteImplementation.provider.snapshot.json").exists()
    assert (run_root / "summaries" / "ExecuteImplementation.provider.summary.md").read_text() == "profile summary\n"
```

- [ ] **Step 2: Add failing test for index writes**

Add:

```python
def test_summary_observer_writes_index_entries(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-index"
    observer = SummaryObserver(
        run_root=run_root,
        provider_executor=_FakeProviderExecutor(),
        provider_name="summary_provider",
        mode="sync",
        timeout_sec=30,
        best_effort=True,
        max_input_chars=12000,
        profile="phase-performance",
    )

    observer.emit("PlanPhase", {"step": {"name": "PlanPhase", "summary_kind": "phase"}}, summary_kind="phase")

    index = json.loads((run_root / "summaries" / "index.json").read_text())
    assert index["schema"] == "orchestrator_summary_index/v1"
    assert index["entries"][0]["step_name"] == "PlanPhase"
    assert index["entries"][0]["kind"] == "phase"
    assert index["entries"][0]["profile"] == "phase-performance"
```

- [ ] **Step 3: Run tests and verify failure**

Run:

```bash
python -m pytest tests/test_observability_summary_modes.py -k "phase_performance or index" -q
```

Expected: FAIL because `profile`, `summary_kind`, kind-specific filenames, and index writes do not exist.

- [ ] **Step 4: Extend `SummaryObserver` constructor**

In `orchestrator/observability/summary.py`, add:

```python
profile: str = "basic",
```

Normalize invalid profile values to `"basic"`:

```python
self.profile = profile if profile in {"basic", "phase-performance"} else "basic"
```

- [ ] **Step 5: Extend `emit` signature**

Change:

```python
def emit(self, step_name: str, snapshot: Dict[str, Any]) -> None:
```

to:

```python
def emit(self, step_name: str, snapshot: Dict[str, Any], *, summary_kind: str = "step") -> None:
```

Normalize `summary_kind`:

```python
if summary_kind not in {"step", "provider", "phase"}:
    summary_kind = "step"
```

- [ ] **Step 6: Add filename helper**

Use current filenames for `basic`/`step`; use kind suffixes otherwise:

```python
def _file_stem(self, safe_step_name: str, summary_kind: str) -> str:
    if self.profile == "basic" and summary_kind == "step":
        return safe_step_name
    return f"{safe_step_name}.{summary_kind}"
```

- [ ] **Step 7: Add profile-specific prompt builder**

Change `_build_prompt(snapshot)` to `_build_prompt(snapshot, summary_kind=...)`.

Basic prompt remains current text.

For provider:

```text
Summarize this provider step in concise, factual markdown.
Include:
- what the provider was asked to do;
- whether it completed, failed, or was skipped;
- key artifacts or outputs;
- an advisory performance judgment covering duration, timeout pressure, retry/fix risk, and evidence sufficiency.

This summary is observability-only. Do not suggest workflow control-flow decisions as if they have already happened.
```

For phase:

```text
Summarize this workflow phase boundary in concise, factual markdown.
Include:
- phase outcome and notable child outputs if present;
- what work advanced;
- blocking or follow-up signals;
- an advisory performance judgment covering elapsed time, retries/failures, and whether evidence is sufficient for a human reviewer.

This summary is observability-only and must not be treated as workflow state.
```

- [ ] **Step 8: Add atomic-enough index update**

Implement `_update_index(...)`:

```python
def _update_index(self, entry: dict[str, Any]) -> None:
    index_path = self.summaries_dir / "index.json"
    if index_path.exists():
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {"schema": "orchestrator_summary_index/v1", "entries": []}
    else:
        payload = {"schema": "orchestrator_summary_index/v1", "entries": []}
    entries = payload.setdefault("entries", [])
    entries.append(entry)
    tmp_path = index_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(index_path)
```

This is observability-only. It does not need to coordinate across processes in this tranche.

- [ ] **Step 9: Run focused summary tests**

Run:

```bash
python -m pytest tests/test_observability_summary_modes.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add orchestrator/observability/summary.py tests/test_observability_summary_modes.py
git commit -m "feat: add summary profiles and index"
```

## Task 3: Classify Provider And Phase Summaries In The Executor

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Create: `tests/test_observability_summary_profiles.py`

- [ ] **Step 1: Add tests for summary kind selection**

Create `tests/test_observability_summary_profiles.py` with focused helper tests that instantiate an executor with a fake `StateManager` enough to call private helpers.

Test provider classification:

```python
def test_summary_kind_for_provider_step():
    executor = _make_executor_with_summary_profile("phase-performance")

    assert executor._summary_kind_for_step({"provider": "codex"}) == "provider"
    assert executor._summary_kind_for_step({"adjudicated_provider": {"candidates": []}}) == "provider"
```

Test phase classification:

```python
def test_summary_kind_for_phase_boundaries():
    executor = _make_executor_with_summary_profile("phase-performance")

    assert executor._summary_kind_for_step({"call": "plan_phase"}) == "phase"
    assert executor._summary_kind_for_step({"repeat_until": {"steps": []}}) == "phase"
```

Test exclusions:

```python
def test_phase_performance_profile_skips_plain_command_steps():
    executor = _make_executor_with_summary_profile("phase-performance")

    assert executor._summary_kind_for_step({"command": ["true"]}) is None
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m pytest tests/test_observability_summary_profiles.py -q
```

Expected: FAIL because helper methods do not exist.

- [ ] **Step 3: Add summary profile helpers**

In `WorkflowExecutor`, add:

```python
def _summary_profile(self) -> str:
    cfg = self.observability.get("step_summaries") if isinstance(self.observability, dict) else {}
    if not isinstance(cfg, dict):
        return "basic"
    profile = str(cfg.get("profile", "basic"))
    return profile if profile in {"basic", "phase-performance"} else "basic"
```

Add:

```python
def _summary_kind_for_step(self, step: Dict[str, Any]) -> Optional[str]:
    profile = self._summary_profile()
    if profile == "basic":
        return "step"
    if "provider" in step or "adjudicated_provider" in step:
        return "provider"
    if "call" in step or "repeat_until" in step:
        return "phase"
    return None
```

- [ ] **Step 4: Update `_emit_step_summary`**

Change `_emit_step_summary` to skip when kind is `None` and pass kind into observer:

```python
summary_kind = self._summary_kind_for_step(step)
if summary_kind is None:
    return
snapshot = self._build_step_summary_snapshot(step_name, step, result, summary_kind=summary_kind)
self.summary_observer.emit(step_name, snapshot, summary_kind=summary_kind)
```

- [ ] **Step 5: Update snapshot builder signature**

Change:

```python
def _build_step_summary_snapshot(self, step_name, step, result):
```

to:

```python
def _build_step_summary_snapshot(self, step_name, step, result, *, summary_kind: str = "step"):
```

Add fields:

```python
"summary": {
    "schema": "orchestrator_step_summary_snapshot/v2",
    "kind": summary_kind,
    "profile": self._summary_profile(),
    "advisory_only": True,
},
```

For provider steps, include deterministic provider metadata:

```python
input_payload["provider"] = step.get("provider") or step.get("adjudicated_provider")
input_payload["timeout_sec"] = step.get("timeout_sec")
input_payload["has_variant_output"] = "variant_output" in step
input_payload["has_output_bundle"] = "output_bundle" in step
input_payload["has_expected_outputs"] = "expected_outputs" in step
input_payload["prompt_sources"] = {
    "input_file": step.get("input_file"),
    "asset_file": step.get("asset_file"),
    "prompt_consumes": step.get("prompt_consumes"),
}
```

For phase summaries, include boundary metadata:

```python
input_payload["phase_boundary"] = {
    "call": step.get("call"),
    "repeat_until": "repeat_until" in step,
    "step_id": step.get("id"),
}
```

For output, add:

```python
"duration_ms": result.get("duration_ms"),
"outcome": result.get("outcome"),
"debug": result.get("debug"),
"artifacts": result.get("artifacts"),
"error": result.get("error"),
```

- [ ] **Step 6: Make `_create_summary_observer` pass profile**

In `_create_summary_observer`, read `profile` from config and pass to `SummaryObserver`.

- [ ] **Step 7: Add snapshot tests**

Add tests asserting:

```python
snapshot = executor._build_step_summary_snapshot(
    "ExecuteImplementation",
    {"provider": "codex", "timeout_sec": 7200, "variant_output": {"path": "state/x.json"}},
    {"status": "completed", "duration_ms": 1000, "artifacts": {"implementation_state": "COMPLETED"}},
    summary_kind="provider",
)

assert snapshot["summary"]["kind"] == "provider"
assert snapshot["summary"]["advisory_only"] is True
assert snapshot["step"]["input"]["has_variant_output"] is True
assert snapshot["step"]["output"]["duration_ms"] == 1000
```

- [ ] **Step 8: Run focused tests**

Run:

```bash
python -m pytest tests/test_observability_summary_profiles.py tests/test_observability_summary_modes.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add orchestrator/workflow/executor.py tests/test_observability_summary_profiles.py
git commit -m "feat: summarize provider and phase boundaries"
```

## Task 4: Document The Runtime Contract

**Files:**
- Modify: `specs/cli.md`
- Modify: `specs/observability.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `tests/test_cli_observability_config.py` or add doc tests if existing docs tests cover these files.

- [ ] **Step 1: Update `specs/cli.md`**

Add `--summary-profile basic|phase-performance` to the runtime observability section.

State:

```text
`--summary-profile phase-performance` enables advisory provider-step and phase-boundary summaries with performance judgments. It implies step summaries if `--step-summaries` was not otherwise provided.
```

- [ ] **Step 2: Update `specs/observability.md`**

Add a subsection under Progress and Metrics:

```markdown
- Advisory agent summaries
  - `--step-summaries` may emit summary snapshots and agent-drafted markdown under `RUN_ROOT/summaries/`.
  - `--summary-profile basic` preserves legacy per-step factual summaries.
  - `--summary-profile phase-performance` emits summaries for provider-like steps and phase boundaries, including advisory performance judgments.
  - Summary files and `summaries/index.json` are observability artifacts only. They are not workflow artifacts, are not published through artifact lineage, and must not drive routing, retries, assertions, or status reconciliation.
  - Phase boundaries are currently reusable `call` steps and `repeat_until` frames.
```

- [ ] **Step 3: Update `docs/workflow_drafting_guide.md`**

Extend the existing summary note around `--step-summaries`:

```markdown
Use `--summary-profile phase-performance` when a long workflow needs human-readable phase and provider-step judgments. Do not encode prompt instructions that ask the summarizer to decide routing or write workflow state; summaries are post-step observability.
```

- [ ] **Step 4: Run docs-related tests**

Run:

```bash
python -m pytest tests/test_cli_observability_config.py tests/test_observability_summary_modes.py tests/test_observability_summary_profiles.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add specs/cli.md specs/observability.md docs/workflow_drafting_guide.md
git commit -m "docs: document phase performance summaries"
```

## Task 5: Add A Narrow Runtime Smoke Test

**Files:**
- Modify: `tests/test_observability_summary_modes.py` or create `tests/test_observability_summary_runtime.py`

- [ ] **Step 1: Add smoke test workflow**

Use a temporary workflow with:

- one command step;
- one provider step using a fake provider command that prints deterministic summary-compatible output;
- one `repeat_until` or call boundary if a compact fixture already exists.

Prefer not to rely on external CLIs.

Example provider template in test workflow:

```yaml
providers:
  fake_provider:
    command: ["bash", "-lc", "cat >/dev/null; printf '{\"status\":\"ok\"}\\n'"]
    input_mode: "stdin"
  fake_summary:
    command: ["bash", "-lc", "cat >/dev/null; printf 'summary ok\\n'"]
    input_mode: "stdin"
```

- [ ] **Step 2: Execute with phase-performance profile**

In the test, instantiate `WorkflowExecutor` directly with:

```python
observability={
    "step_summaries": {
        "enabled": True,
        "mode": "sync",
        "provider": "fake_summary",
        "timeout_sec": 30,
        "best_effort": True,
        "max_input_chars": 12000,
        "profile": "phase-performance",
    }
}
```

- [ ] **Step 3: Assert provider summary exists and command summary does not**

Assert:

```python
assert (run_root / "summaries" / "ProviderWork.provider.summary.md").exists()
assert not (run_root / "summaries" / "CommandWork.summary.md").exists()
```

If the fixture includes a repeat/call boundary, assert:

```python
assert (run_root / "summaries" / "LoopWork.phase.summary.md").exists()
```

- [ ] **Step 4: Run the smoke test**

Run:

```bash
python -m pytest tests/test_observability_summary_runtime.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_observability_summary_runtime.py
git commit -m "test: cover phase performance summary runtime"
```

## Task 6: Full Focused Verification

**Files:**
- No new files unless a failure reveals a targeted fix.

- [ ] **Step 1: Run summary and CLI tests**

Run:

```bash
python -m pytest \
  tests/test_cli_observability_config.py \
  tests/test_observability_summary_modes.py \
  tests/test_observability_summary_profiles.py \
  tests/test_observability_summary_runtime.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run related observability/report tests**

Run:

```bash
python -m pytest \
  tests/test_observability_report.py \
  tests/test_runtime_observability.py \
  tests/test_runtime_observability_cli.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run a dry-run smoke on the Lisp workflow**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/lisp_frontend_autonomous_drain.yaml \
  --dry-run \
  --input steering_path=docs/steering.md \
  --summary-profile phase-performance
```

Expected: validation succeeds; no workflow execution.

- [ ] **Step 4: Inspect generated summary docs**

If a runtime smoke was run, inspect:

```bash
find .orchestrate/runs -path '*/summaries/*' -maxdepth 5 -type f | tail -50
```

Expected: provider/phase summary filenames appear only for runs that enabled the profile.

- [ ] **Step 5: Final commit**

If Task 6 needed fixes:

```bash
git add <changed-files>
git commit -m "fix: stabilize summary profile verification"
```

## Acceptance Criteria

- `--summary-profile basic` preserves current summary behavior.
- `--summary-profile phase-performance` implicitly enables summaries and emits provider/phase summaries only.
- Provider summary snapshots include deterministic provider metadata, output contract indicators, duration, status, artifacts, and errors.
- Phase summary snapshots cover reusable call steps and repeat-until frames.
- Summary markdown asks for advisory performance judgments without implying routing authority.
- `summaries/index.json` lists emitted summaries using run-root-relative paths.
- Summary generation remains best-effort by default.
- Summary failures do not alter step result, artifact lineage, workflow outputs, routing, retry behavior, or persisted terminal status.
- Docs state that summaries are observability-only.
- Focused CLI, summary observer, executor classification, and runtime smoke tests pass.

## Deferred Work

- Workflow-authored summary policies in DSL.
- Semantic phase labels beyond call/repeat boundaries.
- Machine-readable agent performance judgments.
- Dashboard rendering of `summaries/index.json`.
- Summary retention policy.
- Provider-step cost accounting beyond existing duration/timeout metadata.
