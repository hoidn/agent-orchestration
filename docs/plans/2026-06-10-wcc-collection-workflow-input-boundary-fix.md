# WCC Collection Workflow Input Boundary Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `workflows/examples/review_revise_design_docs.orc` compile and dry-run through the default WCC route by allowing lowerable collection-typed workflow inputs without reopening collection returns or runtime procedure transport.

**Architecture:** The frontend already has a private collection lane for `List[DesignDocPath]` under the legacy route, and the runtime input binder can validate and bind the JSON list. The fix is to move WCC's public workflow-parameter policy to the same lowerable-input capability while keeping output/return and `WorkflowRef` collection transport rejected. This avoids a schema-1 launch wrapper and keeps the current target-design review workflow on the accepted WCC path.

**Tech Stack:** Python, pytest, Workflow Lisp `.orc`, WCC lowering schema 2, `build_workflow_catalog`, `compile_stage3_module`, `build_frontend_bundle`, orchestrator CLI dry-run.

---

## Current Context

The default CLI path fails before runtime:

```bash
python -m orchestrator run workflows/examples/review_revise_design_docs.orc --dry-run ...
```

Observed diagnostic:

```text
workflow_boundary_collection_unsupported:
workflow boundary `review_revise_design_docs::review-revise-design-docs`
cannot transport collection type `None` in Stage 3
```

Root cause:

- `review_revise_design_docs.orc` has public input `context_docs List[DesignDocPath]`.
- `orchestrator/workflow_lisp/compiler.py` passes `allow_collection_boundaries=True` only for `LoweringRoute.LEGACY`.
- `orchestrator/workflow_lisp/workflows.py` uses one flag for both workflow parameters and workflow returns.
- Existing example tests in `tests/test_workflow_lisp_examples.py` pin `compile_stage3_module(..., lowering_route="legacy")`, so they do not protect the default WCC path.
- Existing build-artifact tests for the private artifact catalog also pin `LoweringRoute.LEGACY`.

The desired behavior is narrower than "collections everywhere":

- WCC should accept lowerable collection-typed workflow inputs, including `List[DesignDocPath]`.
- WCC should keep collection-typed workflow returns rejected until return transport has an explicit design and runtime contract.
- WCC should keep collection types inside `WorkflowRef[...]` runtime signatures rejected, because workflow/procedure refs remain compile-time-only and must not become runtime transport payloads.

## Files

- Modify: `orchestrator/workflow_lisp/workflows.py`
  - Split the collection boundary capability into input and return policy, or add a parameter-side override while preserving return rejection.
- Modify: `orchestrator/workflow_lisp/compiler.py`
  - Pass the WCC-compatible collection-input policy to `build_workflow_catalog` in both single-module and linked-entrypoint compilation paths.
- Modify: `tests/test_workflow_lisp_workflows.py`
  - Convert the current collection-input negative fixture into a default-WCC positive compile test.
  - Keep collection-return and `WorkflowRef[List[...]]` negative coverage.
- Modify: `tests/test_workflow_lisp_examples.py`
  - Stop globally defaulting the local helper to legacy, or add explicit WCC/default tests for `review_revise_design_docs.orc`.
  - Preserve legacy pins only for examples that are intentionally legacy/historical.
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
  - Remove `LoweringRoute.LEGACY` from private collection catalog tests for `review_revise_design_docs.orc`, or duplicate them under default WCC before deleting the legacy pin.
- Optional docs update: `docs/reports/2026-06-10-wcc-post-foundation-unplanned-architecture-findings.md`
  - If the implementation fully closes UAF-01 for this example, add a short "resolved by" note rather than rewriting the report.
- Do not modify active drain state/artifacts unless a test or workflow run intentionally generates new evidence.

## Task 1: Add Failing WCC Boundary Tests

- [ ] **Step 1: Add a default-WCC positive input-boundary test**

In `tests/test_workflow_lisp_workflows.py`, replace or supplement `test_workflow_boundary_rejects_collection_typed_params` with:

```python
def test_workflow_boundary_accepts_lowerable_collection_typed_params_under_wcc(tmp_path: Path) -> None:
    result = compile_stage3_module(
        INVALID_FIXTURES / "workflow_boundary_collection_invalid.orc",
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert result.typed_workflows[0].signature.params[0][0] == "attempt_ids"
```

If the fixture name is misleading after the behavior change, either rename it in a separate small patch or keep it and add a comment explaining it is a historical fixture that now verifies the accepted input path.

- [ ] **Step 2: Keep return rejection explicit**

Leave `test_workflow_boundary_rejects_collection_typed_returns` as a negative test. It should still fail with `workflow_boundary_collection_unsupported`.

- [ ] **Step 3: Keep `WorkflowRef` collection rejection explicit**

Leave `test_workflow_boundary_rejects_collections_inside_workflow_ref_signatures` as a negative test. It should still fail with `workflow_boundary_collection_unsupported` or a more precise runtime-transport diagnostic if the implementation reveals one.

- [ ] **Step 4: Run the focused tests and verify the new test fails**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflows.py -k "collection_typed_params or collection_typed_returns or collections_inside_workflow_ref" -q
```

Expected before implementation: the new positive input-boundary test fails with `workflow_boundary_collection_unsupported`; the two negative tests pass.

## Task 2: Split Input And Return Collection Boundary Policy

- [ ] **Step 1: Update `build_workflow_catalog` signature**

In `orchestrator/workflow_lisp/workflows.py`, replace the single `allow_collection_boundaries: bool = False` parameter with direction-specific policy, for example:

```python
allow_collection_input_boundaries: bool = False
allow_collection_return_boundaries: bool = False
```

Keep backward compatibility only if needed for current call sites. Prefer updating call sites directly if the parameter is internal-only.

- [ ] **Step 2: Apply return policy to return diagnostics**

For the return type diagnostic:

```python
return_diagnostic = _boundary_diagnostic(
    ...,
    allow_collection_boundaries=allow_collection_return_boundaries,
)
```

Default remains `False`.

- [ ] **Step 3: Apply input policy to parameter diagnostics**

For workflow parameter diagnostics:

```python
param_diagnostic = _boundary_diagnostic(
    ...,
    allow_collection_boundaries=allow_collection_input_boundaries,
)
```

WCC will set this true for lowerable collection inputs.

- [ ] **Step 4: Preserve nested forbidden surfaces**

Do not change `_boundary_diagnostic` behavior for:

- `Json`
- `Provider`
- `Prompt`
- `WorkflowRef`
- `ProcRef`
- unions crossing non-return boundaries

Only the `analysis.lowerable and analysis.contains_collection` case should be affected for workflow input parameters.

- [ ] **Step 5: Update compiler call sites**

In `orchestrator/workflow_lisp/compiler.py`, update both calls to `build_workflow_catalog`:

- `_run_stage3_validation_pipeline(...)`
- the linked module graph compile path around the second `build_workflow_catalog(...)` call

Use:

```python
allow_collection_input_boundaries=True
allow_collection_return_boundaries=normalized_lowering_route is LoweringRoute.LEGACY
```

If legacy return collections are not actually supported and only inputs relied on the old flag, tighten legacy too:

```python
allow_collection_input_boundaries=True
allow_collection_return_boundaries=False
```

Choose the second option only after running current tests and confirming no accepted legacy fixture depends on collection returns.

- [ ] **Step 6: Run focused tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflows.py -k "collection_typed_params or collection_typed_returns or collections_inside_workflow_ref" -q
```

Expected: all selected tests pass.

## Task 3: Move The Design-Docs Review Example Onto Default WCC

- [ ] **Step 1: Adjust the local test helper cautiously**

In `tests/test_workflow_lisp_examples.py`, the helper currently forces every example compile through legacy:

```python
def compile_stage3_module(*args, **kwargs):
    kwargs.setdefault("lowering_route", "legacy")
    return _compile_stage3_module(*args, **kwargs)
```

Do not blindly remove this if older examples still need legacy. Instead, update only the `review_revise_design_docs.orc` tests to call `_compile_stage3_module(...)` directly with no `lowering_route`, or add a helper named `compile_stage3_module_default_wcc(...)`.

- [ ] **Step 2: Update the parameterized context-docs test**

In `test_review_revise_design_docs_example_validates_with_parameterized_context_docs`, compile with the default WCC route.

Expected assertions remain:

- selected workflow is `review_revise_design_docs::review-revise-design-docs`;
- `private_artifact_ids == ("context_docs",)`;
- `context_docs` lowers to a collection input contract;
- `context_docs` and `review_focus` artifacts are not pointer-based.

- [ ] **Step 3: Update the runtime private collection lane test**

In `test_review_revise_design_docs_runtime_private_collection_lane`, compile with default WCC.

Keep the runtime assertions unchanged unless the WCC route intentionally changes generated IDs. If IDs change, assert semantic properties rather than exact route-specific strings.

- [ ] **Step 4: Run focused example tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_examples.py -k "review_revise_design_docs" -q
```

Expected: all selected tests pass under default WCC.

## Task 4: Move Build Artifact Coverage Onto Default WCC

- [ ] **Step 1: Remove legacy route pin from private artifact catalog build**

In `tests/test_workflow_lisp_build_artifacts.py`, update `test_build_artifacts_emit_private_artifact_catalog` so the `FrontendBuildRequest` for `review_revise_design_docs.orc` does not pass `lowering_route=LoweringRoute.LEGACY`.

- [ ] **Step 2: Remove legacy route pin from Semantic IR bridge build**

Update `test_semantic_ir_private_artifact_catalog_bridge` the same way.

- [ ] **Step 3: Preserve route metadata invariant**

These tests should continue to avoid asserting route names in emitted artifacts. WCC route metadata is compile/build metadata, not runtime semantic output.

- [ ] **Step 4: Run focused build artifact tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "private_artifact_catalog" -q
```

Expected: private artifact catalog and Semantic IR bridge tests pass under default WCC.

## Task 5: Verify CLI Dry-Run On The Current Target Design

- [ ] **Step 1: Ensure the checks artifact exists**

Run:

```bash
mkdir -p artifacts/work/LISP-MIGRATION-PARITY-DRAIN artifacts/review/LISP-MIGRATION-PARITY-DRAIN
test -f artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-post-foundation-current-checks.md \
  || printf '# Post-foundation design review checks\n' > artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-post-foundation-current-checks.md
```

- [ ] **Step 2: Run the exact default-WCC dry-run**

Run:

```bash
python -m orchestrator run workflows/examples/review_revise_design_docs.orc \
  --entry-workflow review-revise-design-docs \
  --provider-externs-file workflows/examples/inputs/review_revise_design_docs/providers.json \
  --prompt-externs-file workflows/examples/inputs/review_revise_design_docs/prompts.json \
  --dry-run \
  --input phase-ctx__run__run-id=review-revise-design-docs-post-foundation-current \
  --input phase-ctx__run__state-root=state/review-revise-design-docs-post-foundation-current \
  --input phase-ctx__run__artifact-root=artifacts \
  --input phase-ctx__phase-name=design-review \
  --input phase-ctx__state-root=state/review-revise-design-docs-post-foundation-current/design-review \
  --input phase-ctx__artifact-root=artifacts \
  --input target_doc=workflow_lisp_post_foundation_composition_stdlib_migration.md \
  --input context_docs='["workflow_lisp_frontend_specification.md","workflow_lisp_runtime_migration_foundation.md","workflow_lisp_core_calculus_middle_end.md","workflow_command_adapter_contract.md","workflow_lisp_state_layout.md"]' \
  --input review_focus='Review the post-foundation composition and stdlib migration target design against the current WCC middle-end route and active Design Delta Drain implementation state. Check consistency, implementation readiness, stale legacy-route assumptions, parent-callable workflow-family migration requirements, private context, typed projection, certified adapter/resource transition boundaries, parity evidence, and whether the design remains a coherent guide for continuing implementation.' \
  --input checks_report=artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-post-foundation-current-checks.md \
  --input review_report_target_path=artifacts/review/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-post-foundation-current-review.md \
  --input revision_report_target_path=artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-post-foundation-current-revision.md
```

Expected:

```text
[DRY RUN] Workflow validation successful
```

No `workflow_boundary_collection_unsupported` diagnostic should appear.

## Task 6: Broader Regression And Docs

- [ ] **Step 1: Run focused WCC regression selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_wcc_m4.py tests/test_workflow_lisp_wcc_m5.py -q
```

Expected: pass.

- [ ] **Step 2: Run the targeted build/examples/workflow suite**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_workflows.py \
  tests/test_workflow_lisp_examples.py \
  tests/test_workflow_lisp_build_artifacts.py \
  -k "collection_typed or review_revise_design_docs or private_artifact_catalog or wcc_default_schema" \
  -q
```

Expected: pass.

- [ ] **Step 3: Check whether docs need a resolution note**

If the dry-run now passes under default WCC, update `docs/reports/2026-06-10-wcc-post-foundation-unplanned-architecture-findings.md` with a short note under UAF-01:

```markdown
Resolution note: default WCC now accepts lowerable collection-typed workflow
inputs, so `review_revise_design_docs.orc` no longer requires legacy schema 1
for `context_docs`. Collection returns and collection-bearing workflow refs
remain outside the supported runtime boundary.
```

Do not remove the rest of UAF-01 if stale/historical example classification remains unresolved.

- [ ] **Step 4: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

## Task 7: Launch The Review Workflow Through Default WCC

- [ ] **Step 1: Use tmux and no legacy wrapper**

After Task 5 dry-run passes, launch the workflow with the same command but without `--dry-run`, in a tmux session such as `rr-postfound-current-wcc`.

Use:

```bash
tmux -S /tmp/claude-tmux-sockets/claude.sock new-session -d -s rr-postfound-current-wcc \
  "cd /home/ollie/Documents/agent-orchestration && export PYTHONPATH=/home/ollie/Documents/agent-orchestration\${PYTHONPATH:+:\$PYTHONPATH}; python -m orchestrator run workflows/examples/review_revise_design_docs.orc ... --stream-output"
```

Use the full input list from Task 5.

- [ ] **Step 2: Capture the run id**

Run:

```bash
tmux -S /tmp/claude-tmux-sockets/claude.sock capture-pane -p -J -t rr-postfound-current-wcc:0.0 -S -120
```

Record `Created new run: <run_id>`.

- [ ] **Step 3: Confirm state exists**

Run:

```bash
test -f .orchestrate/runs/<run_id>/state.json
python -m orchestrator report --run-id <run_id>
```

Expected: run is `running`, `completed`, or in a real provider/review step; it must not fail during compile/dry-run setup.

- [ ] **Step 4: Start a watchdog only after the run id is known**

If the review is expected to run unattended, start `workflows/examples/generic_run_watchdog.yaml` as a real loop targeting the new run id, with target-specific state and evidence roots.

## Task 8: Commit

- [ ] **Step 1: Inspect dirty state**

Run:

```bash
git status --short
```

There are active-drain changes in this workspace. Stage only files touched by this fix and any intentional review artifacts from Task 7 if the user asks for them.

- [ ] **Step 2: Commit the fix**

Recommended staged files:

```bash
git add \
  orchestrator/workflow_lisp/workflows.py \
  orchestrator/workflow_lisp/compiler.py \
  tests/test_workflow_lisp_workflows.py \
  tests/test_workflow_lisp_examples.py \
  tests/test_workflow_lisp_build_artifacts.py \
  docs/reports/2026-06-10-wcc-post-foundation-unplanned-architecture-findings.md
```

Omit the docs report if unchanged.

Commit:

```bash
git commit -m "Allow WCC collection workflow inputs"
```

## Final Verification Checklist

- [ ] Default-WCC compile accepts lowerable collection workflow parameters.
- [ ] Default-WCC compile still rejects collection workflow returns.
- [ ] Default-WCC compile still rejects collection-bearing `WorkflowRef` runtime transport.
- [ ] `review_revise_design_docs.orc` tests run under default WCC.
- [ ] Private artifact catalog and Semantic IR bridge still expose `context_docs` as a private collection artifact.
- [ ] CLI dry-run for the current target design passes without `workflow_boundary_collection_unsupported`.
- [ ] Live launch uses `python -m orchestrator run`, not the temporary legacy wrapper.
- [ ] `git diff --check` passes.
