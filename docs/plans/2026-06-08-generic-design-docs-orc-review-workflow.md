# Generic Design Docs ORC Review Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable `.orc` review/fix workflow that reviews one target design doc with a typed list of optional context design docs.

**Architecture:** Replace the earlier one-off sibling plan with a generic selected-design-docs workflow. The workflow keeps the real-life-tested review/fix shape, but moves the hardcoded doc trio into typed workflow inputs: `target_doc DesignDocPath`, `context_docs List[DesignDocPath]`, and `review_focus String`.

**Tech Stack:** Workflow Lisp `.orc`, `List[DesignDocPath]`, `std/phase.orc` `review-revise-loop`, prompt JSON bindings, `tests/test_workflow_lisp_examples.py`, `python -m orchestrator` compile/dry-run checks.

---

## Scope

This plan builds a generic `.orc` workflow for targeted design-doc review/fix
loops. It should support both current use cases:

- parametric review/revise stdlib design review;
- runtime migration foundation design review.

The primary design uses first-class typed list input:

```lisp
(context_docs List[DesignDocPath])
```

Callers pass a non-empty list when there are supporting docs and an empty list
when the target design should be reviewed alone. If empty or list-valued CLI
input is not usable end-to-end, that is a useful implementation gap to record.
Do not start with a manifest-file workaround.

## Source Authorities

- `docs/index.md`: documentation routing.
- `docs/lisp_workflow_drafting_guide.md`: `.orc` authoring guidance, `:default` limitations, and current example status.
- `docs/capability_status_matrix.md`: current example/capability routing.
- `workflows/README.md`: workflow catalog and copy guidance.
- `workflows/examples/review_revise_parametric_design_docs.orc`: proven one-off `.orc` review/fix shape.
- `tests/test_workflow_lisp_collection_types.py`: current `List[T]` type surface evidence.
- `tests/test_workflow_lisp_examples.py`: existing validation test pattern for examples.
- `prompts/workflows/review_revise_parametric_design_docs/`: prompt shape reference.
- `docs/design/workflow_lisp_runtime_migration_foundation.md`: runtime foundation target use case.
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`: parametric target use case.

## File Map

- Create: `workflows/examples/review_revise_design_docs.orc`
  - Generic `.orc` workflow that reviews/fixes one target design doc with optional typed context docs.
- Create: `prompts/workflows/review_revise_design_docs/review.md`
  - Generic review prompt that accepts target doc, context docs, review focus, checks report, and target artifact paths.
- Create: `prompts/workflows/review_revise_design_docs/fix.md`
  - Generic fix prompt that revises the target doc from structured findings while treating context docs as authorities/context.
- Create: `.orchestrate/tmp/review-revise-design-docs-parametric/prompts.json`
  - Launch binding for the parametric design-docs use case.
- Create: `.orchestrate/tmp/review-revise-design-docs-parametric/providers.json`
  - Provider binding for the parametric design-docs use case.
- Create: `.orchestrate/tmp/review-revise-design-docs-runtime-foundation/prompts.json`
  - Launch binding for the runtime migration foundation use case.
- Create: `.orchestrate/tmp/review-revise-design-docs-runtime-foundation/providers.json`
  - Provider binding for the runtime migration foundation use case.
- Modify: `tests/test_workflow_lisp_examples.py`
  - Add constants and compile/shared-validation tests for the generic workflow with non-empty and empty context lists.
- Modify: `workflows/README.md`
  - Catalog the generic workflow and explain how it relates to one-off examples.
- Modify: `docs/capability_status_matrix.md`
  - Point Workflow Lisp review/fix copy guidance at the generic workflow after it validates.
- Modify: `docs/lisp_workflow_drafting_guide.md`
  - Replace “use the one-off review workflow as the model” with “use the generic design-doc review workflow; the one-off parametric workflow is historical/tested precedent.”

## Non-Goals

- Do not implement variable-length context through a JSON/markdown manifest unless direct `List[DesignDocPath]` is proven blocked.
- Do not add new Workflow Lisp language features unless tests expose a small missing boundary required to pass list-valued workflow inputs.
- Do not change `review-revise-loop` semantics.
- Do not mutate `review_revise_parametric_design_docs.orc` in this pass except optional catalog notes.
- Do not claim YAML parity promotion for this workflow.
- Do not make this a production drain.

## Implementation Tasks

### Task 1: Add Generic Review/Fix Prompt Assets

**Files:**
- Create: `prompts/workflows/review_revise_design_docs/review.md`
- Create: `prompts/workflows/review_revise_design_docs/fix.md`

- [ ] **Step 1: Read the existing prompt shape**

  Run:

  ```bash
  sed -n '1,220p' prompts/workflows/review_revise_parametric_design_docs/review.md
  sed -n '1,220p' prompts/workflows/review_revise_parametric_design_docs/fix.md
  ```

  Expected: The existing prompt contract, output path expectations, structured
  findings expectations, and relpath guidance are visible.

- [ ] **Step 2: Create the generic review prompt**

  Create `prompts/workflows/review_revise_design_docs/review.md` by adapting
  the existing review prompt. The main instruction must be generic:

  ```text
  Review the target design doc from the point of view described by
  review_focus. Use context_docs as supporting context and authority. The design
  may be considered implementation-ready only if it improves ergonomics and the
  long-term maintainability, extensibility, and internal architecture of the
  implementation.
  ```

  Required prompt responsibilities:

  - inspect `target_doc`;
  - inspect every path in `context_docs`;
  - use `review_focus` as the task-specific review lens;
  - produce a structured review decision: `APPROVE`, `REVISE`, or `BLOCKED`;
  - write the review report to `review_report_target_path`;
  - write structured findings to the expected findings path used by the
    existing `ReviewFindings` contract;
  - treat `checks_report` as carried evidence, not provider-authored evidence.

- [ ] **Step 3: Create the generic fix prompt**

  Create `prompts/workflows/review_revise_design_docs/fix.md` by adapting the
  existing fix prompt. The main instruction must be generic:

  ```text
  Revise target_doc in response to the structured review findings and
  review_focus. Treat context_docs as supporting authority. Do not rewrite
  context docs unless a finding explicitly identifies a contradiction that must
  be fixed there.
  ```

  Required prompt responsibilities:

  - revise the target doc only by default;
  - preserve the design doc's current authority/status boundaries;
  - write a revision report to `revision_report_target_path`;
  - keep findings traceable to the review report.

- [ ] **Step 4: Verify prompt files and stale wording**

  Run:

  ```bash
  test -f prompts/workflows/review_revise_design_docs/review.md
  test -f prompts/workflows/review_revise_design_docs/fix.md
  rg "parametric|runtime migration foundation|structural constraints|compile-time parametric" prompts/workflows/review_revise_design_docs
  ```

  Expected: `test` commands pass. `rg` should return no matches unless the line
  explicitly describes example launch profiles rather than generic prompt
  behavior.

### Task 2: Add Generic `.orc` Workflow

**Files:**
- Create: `workflows/examples/review_revise_design_docs.orc`

- [x] **Step 1: Copy the proven review-loop skeleton**

  Start from `workflows/examples/review_revise_parametric_design_docs.orc`.
  Rename module/workflow/type names:

  - module: `review_revise_design_docs`
  - export: `review-revise-design-docs`
  - completed record: `DesignDocReviewSubject`
  - input record: `DesignDocReviewInputs`
  - result union: `DesignDocReviewLoopResult`

- [x] **Step 2: Use generic target/context inputs**

  Use these records:

  ```lisp
  (defrecord DesignDocReviewSubject
    (target_doc DesignDocPath)
    (context_docs List[DesignDocPath]))

  (defrecord DesignDocReviewInputs
    (target_doc DesignDocPath)
    (context_docs List[DesignDocPath])
    (review_focus String)
    (checks_report WorkReportPath)
    (review_report_target_path ReviewReportTargetPath)
    (revision_report_target_path WorkReportTargetPath))
  ```

- [x] **Step 3: Define workflow boundary**

  Use this public workflow boundary:

  ```lisp
  (defworkflow review-revise-design-docs
    ((phase-ctx PhaseCtx)
     (target_doc DesignDocPath)
     (context_docs List[DesignDocPath])
     (review_focus String)
     (checks_report WorkReportPath)
     (review_report_target_path ReviewReportTargetPath)
     (revision_report_target_path WorkReportTargetPath))
    -> DesignDocReviewLoopResult
    ...)
  ```

  Do not add a `:default` for `context_docs`; collection defaults are not part
  of the safe current authoring surface. The current stdlib macro accepts a
  literal `:max` value, so this pass uses `:max 20` rather than a dynamic
  `max_iterations` workflow input.

- [x] **Step 4: Use generic provider/prompt externs through ProcRefs**

  Use:

  ```lisp
  :review (proc-ref review-design-docs)
  :fix (proc-ref fix-design-doc)
  :max 20
  ```

  The selected ProcRefs use generic provider and prompt extern names, so launch
  profiles can bind the same workflow to different prompt/provider assets
  without editing `.orc`.

- [x] **Step 5: Preserve terminal result authority**

  Keep the result union shape from the parametric workflow:

  - `APPROVED` carries `checks_report`, `review_report`, `review_decision`,
    and `findings`;
  - `BLOCKED` carries `progress_report`, `blocker_class`, and `findings`;
  - `EXHAUSTED` carries `last_review_report`, `reason`, and `findings`.

  The final projection must copy `checks_report` from carried input/state, not
  from provider output.

- [ ] **Step 6: Verify stale hardcoding is gone**

  Run:

  ```bash
  rg "Parametric|parametric|runtime_migration|integration_doc|structural_constraints_doc|parametric_specialization_doc|foundation_doc" workflows/examples/review_revise_design_docs.orc
  rg "target_doc|context_docs|review_focus|review-revise-design-docs|DesignDocReview" workflows/examples/review_revise_design_docs.orc
  ```

  Expected: first command returns no stale hardcoded fields; second command
  shows the generic inputs and type names.

### Task 3: Add Launch Profiles

**Files:**
- Create: `.orchestrate/tmp/review-revise-design-docs-parametric/prompts.json`
- Create: `.orchestrate/tmp/review-revise-design-docs-parametric/providers.json`
- Create: `.orchestrate/tmp/review-revise-design-docs-runtime-foundation/prompts.json`
- Create: `.orchestrate/tmp/review-revise-design-docs-runtime-foundation/providers.json`

- [ ] **Step 1: Create shared provider bindings**

  Create both provider files with:

  ```json
  {
    "providers.design-docs.review": "codex",
    "providers.design-docs.fix": "codex"
  }
  ```

- [ ] **Step 2: Create parametric prompt bindings**

  Create `.orchestrate/tmp/review-revise-design-docs-parametric/prompts.json`:

  ```json
  {
    "prompts.design-docs.review": "prompts/workflows/review_revise_design_docs/review.md",
    "prompts.design-docs.fix": "prompts/workflows/review_revise_design_docs/fix.md"
  }
  ```

- [ ] **Step 3: Create runtime foundation prompt bindings**

  Create `.orchestrate/tmp/review-revise-design-docs-runtime-foundation/prompts.json`
  with the same generic prompt bindings:

  ```json
  {
    "prompts.design-docs.review": "prompts/workflows/review_revise_design_docs/review.md",
    "prompts.design-docs.fix": "prompts/workflows/review_revise_design_docs/fix.md"
  }
  ```

- [ ] **Step 4: Validate JSON**

  Run:

  ```bash
  python -m json.tool .orchestrate/tmp/review-revise-design-docs-parametric/providers.json >/dev/null
  python -m json.tool .orchestrate/tmp/review-revise-design-docs-parametric/prompts.json >/dev/null
  python -m json.tool .orchestrate/tmp/review-revise-design-docs-runtime-foundation/providers.json >/dev/null
  python -m json.tool .orchestrate/tmp/review-revise-design-docs-runtime-foundation/prompts.json >/dev/null
  ```

  Expected: all commands exit `0`.

### Task 4: Add Compile/Shared-Validation Test Coverage

**Files:**
- Modify: `tests/test_workflow_lisp_examples.py`

- [ ] **Step 1: Add constants**

  Near the existing parametric constants, add:

  ```python
  DESIGN_DOCS_REVIEW_EXAMPLE = WORKFLOWS / "review_revise_design_docs.orc"
  DESIGN_DOCS_REVIEW_PROMPT = (
      REPO_ROOT / "prompts" / "workflows" / "review_revise_design_docs" / "review.md"
  )
  DESIGN_DOCS_FIX_PROMPT = (
      REPO_ROOT / "prompts" / "workflows" / "review_revise_design_docs" / "fix.md"
  )
  ```

- [ ] **Step 2: Add non-empty context-list validation test**

  Add:

  ```python
  def test_review_revise_design_docs_example_validates_with_context_docs(tmp_path: Path) -> None:
      assert DESIGN_DOCS_REVIEW_PROMPT.is_file()
      assert DESIGN_DOCS_FIX_PROMPT.is_file()

      design_root = tmp_path / "docs" / "design"
      design_root.mkdir(parents=True)
      for name in (
          "workflow_lisp_runtime_migration_foundation.md",
          "workflow_lisp_key_migration_parity_architecture.md",
          "workflow_command_adapter_contract.md",
          "workflow_lisp_state_layout.md",
      ):
          (design_root / name).write_text(f"# {name}\n", encoding="utf-8")

      checks_report = (
          tmp_path
          / "artifacts"
          / "work"
          / "LISP-MIGRATION-PARITY-DRAIN"
          / "review-revise-design-docs-checks.md"
      )
      checks_report.parent.mkdir(parents=True)
      checks_report.write_text("# Review checks\n", encoding="utf-8")

      compile_stage3_module(
          DESIGN_DOCS_REVIEW_EXAMPLE,
          provider_externs={
              "providers.design-docs.review": "codex",
              "providers.design-docs.fix": "codex",
          },
          prompt_externs={
              "prompts.design-docs.review": DESIGN_DOCS_REVIEW_PROMPT.relative_to(REPO_ROOT).as_posix(),
              "prompts.design-docs.fix": DESIGN_DOCS_FIX_PROMPT.relative_to(REPO_ROOT).as_posix(),
          },
          validate_shared=True,
          workspace_root=tmp_path,
          input_overrides={
              "target_doc": "workflow_lisp_runtime_migration_foundation.md",
              "context_docs": [
                  "workflow_lisp_key_migration_parity_architecture.md",
                  "workflow_command_adapter_contract.md",
                  "workflow_lisp_state_layout.md",
              ],
              "review_focus": "implementation readiness and architectural soundness",
              "checks_report": "artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-checks.md",
              "review_report_target_path": "artifacts/review/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-review.md",
              "revision_report_target_path": "artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-revision.md",
          },
      )
  ```

  If `compile_stage3_module` does not accept `input_overrides`, inspect the
  helper signature and adapt the test to the existing supported input-binding
  mechanism. Do not silently drop the list-valued input test.

- [ ] **Step 3: Add empty context-list validation test**

  Add a second test with:

  ```python
  "context_docs": []
  ```

  Expected: the generic workflow validates with no supporting docs.

- [ ] **Step 4: If list-valued workflow inputs fail, capture the precise gap**

  If either list test fails because workflow-boundary list inputs cannot yet be
  represented, do not switch to a manifest silently. Add a focused expected
  failure or diagnostic test that records the current limitation, then decide
  whether to implement the smallest list-input support needed for this workflow.

- [ ] **Step 5: Run collect-only**

  Run:

  ```bash
  pytest --collect-only tests/test_workflow_lisp_examples.py -q
  ```

  Expected: collection succeeds and includes both new tests.

- [ ] **Step 6: Run targeted tests**

  Run:

  ```bash
  pytest tests/test_workflow_lisp_examples.py::test_review_revise_design_docs_example_validates_with_context_docs -q
  pytest tests/test_workflow_lisp_examples.py::test_review_revise_design_docs_example_validates_with_empty_context_docs -q
  ```

  Expected: both tests pass, or one exposes a precise list-input limitation
  that is documented before any fallback is considered.

### Task 5: Add CLI/Dry-Run Profiles

**Files:**
- No source changes expected unless command examples are added to docs.

- [ ] **Step 1: Ensure real checks reports exist**

  Run:

  ```bash
  mkdir -p artifacts/work/LISP-MIGRATION-PARITY-DRAIN
  test -f artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-runtime-foundation-checks.md \
    || printf '# Runtime migration foundation review checks\n' > artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-runtime-foundation-checks.md
  test -f artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-parametric-checks.md \
    || printf '# Parametric design docs review checks\n' > artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-parametric-checks.md
  ```

- [ ] **Step 2: Dry-run runtime foundation profile**

  Run, adapting list input syntax to the current CLI if needed:

  ```bash
  python -m orchestrator run \
    workflows/examples/review_revise_design_docs.orc \
    --entry review-revise-design-docs \
    --provider-externs .orchestrate/tmp/review-revise-design-docs-runtime-foundation/providers.json \
    --prompt-externs .orchestrate/tmp/review-revise-design-docs-runtime-foundation/prompts.json \
    --dry-run \
    --input phase-ctx__run__run-id=review-revise-design-docs-runtime-foundation \
    --input phase-ctx__run__state-root=state/review-revise-design-docs-runtime-foundation \
    --input phase-ctx__run__artifact-root=artifacts \
    --input phase-ctx__phase-name=design-review \
    --input phase-ctx__state-root=state/review-revise-design-docs-runtime-foundation/design-review \
    --input phase-ctx__artifact-root=artifacts \
    --input target_doc=workflow_lisp_runtime_migration_foundation.md \
    --input context_docs='["workflow_lisp_key_migration_parity_architecture.md","workflow_command_adapter_contract.md","workflow_lisp_state_layout.md"]' \
    --input review_focus='Review consistency, implementation readiness, architectural soundness, and whether command structured-output authority, migration promotion gates, and StateLayout/PathAllocator responsibilities compose cleanly.' \
    --input checks_report=artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-runtime-foundation-checks.md \
    --input review_report_target_path=artifacts/review/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-runtime-foundation-review.md \
    --input revision_report_target_path=artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-runtime-foundation-revision.md
  ```

  Expected: workflow validates/dry-runs without executing providers.

- [ ] **Step 3: Dry-run parametric profile**

  Run the same command shape with:

  ```text
  target_doc=workflow_lisp_review_revise_stdlib_parametric_integration.md
  context_docs=[
    "workflow_lisp_structural_parametric_constraints.md",
    "workflow_lisp_compile_time_parametric_specialization.md"
  ]
  review_focus=Review consistency/correctness and architectural soundness of the parametric review/revise stdlib integration.
  ```

  Expected: workflow validates/dry-runs without executing providers.

- [ ] **Step 4: If CLI list input syntax fails, inspect CLI help**

  Run:

  ```bash
  python -m orchestrator run --help
  ```

  Record the exact current limitation. If CLI cannot pass list-valued `.orc`
  workflow inputs, keep the compile/shared-validation tests and document launch
  as blocked on list-input CLI binding. Do not replace `context_docs` with a
  manifest unless explicitly accepted as a fallback.

### Task 6: Catalog And Guidance Updates

**Files:**
- Modify: `workflows/README.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`

- [ ] **Step 1: Catalog the generic workflow**

  Add a `workflows/README.md` row:

  ```markdown
  | `workflows/examples/review_revise_design_docs.orc` | Workflow Lisp generic review/fix workflow; input-required | `2.14` | `review-revise-design-docs` | Generic `.orc` workflow that reviews one target design doc with a typed list of context design docs, review focus text, and explicit artifact targets. Use it as the current model for targeted design-doc review/fix loops; keep YAML drains authoritative for production queue/drain behavior. |
  ```

- [ ] **Step 2: Update "Which Example Should I Copy?"**

  Distinguish:

  - current target-design/gap drain YAML:
    `workflows/examples/lisp_frontend_design_delta_drain.yaml`;
  - generic `.orc` design-doc review/fix:
    `workflows/examples/review_revise_design_docs.orc`;
  - smallest `.orc` teaching example:
    `workflows/examples/kiss_backlog_item.orc`;
  - old one-off parametric workflow:
    `workflows/examples/review_revise_parametric_design_docs.orc` as proven
    precedent, not the preferred generic starting point.

- [ ] **Step 3: Update capability matrix**

  In `docs/capability_status_matrix.md`:

  - set Workflow Lisp `.orc` copyable examples to include
    `review_revise_design_docs.orc` and `kiss_backlog_item.orc`;
  - set `review-revise-loop` copyable example to
    `review_revise_design_docs.orc`;
  - describe `review_revise_parametric_design_docs.orc` as the earlier
    one-off tested model if mentioned.

- [ ] **Step 4: Update Lisp drafting guide**

  Replace the current wording that promotes the one-off parametric workflow as
  the real tested model. New wording:

  ```text
  For targeted design-doc review/fix, start with
  workflows/examples/review_revise_design_docs.orc. It is the generic version
  of the real-life-tested parametric design-doc review loop and accepts a
  target design doc plus a typed list of context docs.
  ```

- [ ] **Step 5: Verify no stale routing**

  Run:

  ```bash
  rg "review_revise_design_docs|review_revise_parametric_design_docs|kiss_backlog_item|main `.orc` model|smallest Workflow Lisp" workflows/README.md docs/capability_status_matrix.md docs/lisp_workflow_drafting_guide.md
  git diff --check -- workflows/README.md docs/capability_status_matrix.md docs/lisp_workflow_drafting_guide.md
  ```

  Expected: generic workflow is preferred for design-doc review/fix;
  `kiss_backlog_item.orc` remains only the teaching example; no whitespace
  errors.

### Task 7: Optional Real Run

**Files:**
- No source changes expected unless run docs are updated.

- [ ] **Step 1: Launch only after compile/shared-validation and dry-run pass**

  Launch the runtime foundation profile without `--dry-run`. Use current
  workflow-launching conventions: disable summarization/notes, run under tmux
  if long-running, and start a watchdog only if needed.

- [ ] **Step 2: Inspect outputs**

  Run:

  ```bash
  python -m orchestrator report --run-id <run_id>
  ```

  Expected terminal outcomes:

  - `APPROVED`: design was accepted after zero or more fixes;
  - `BLOCKED`: only for a major unresolvable ambiguity in intention or an
    environment issue requiring user intervention;
  - `EXHAUSTED`: loop reached max iterations and needs human review.

- [ ] **Step 3: Review provider edits before committing**

  If the workflow revises a design doc, inspect the diff manually. Do not treat
  provider output as accepted merely because the workflow completed.

### Task 8: Final Verification And Commit

**Files:**
- All files touched by prior tasks.

- [ ] **Step 1: Run focused verification**

  Run:

  ```bash
  pytest --collect-only tests/test_workflow_lisp_examples.py -q
  pytest tests/test_workflow_lisp_examples.py::test_review_revise_design_docs_example_validates_with_context_docs -q
  pytest tests/test_workflow_lisp_examples.py::test_review_revise_design_docs_example_validates_with_empty_context_docs -q
  git diff --check
  ```

  Expected: all commands pass, or list-valued workflow-boundary input has a
  precise documented blocker and no manifest fallback was silently introduced.

- [ ] **Step 2: Review scoped diff**

  Run:

  ```bash
  git diff -- workflows/examples/review_revise_design_docs.orc \
    prompts/workflows/review_revise_design_docs \
    .orchestrate/tmp/review-revise-design-docs-parametric \
    .orchestrate/tmp/review-revise-design-docs-runtime-foundation \
    tests/test_workflow_lisp_examples.py \
    workflows/README.md \
    docs/capability_status_matrix.md \
    docs/lisp_workflow_drafting_guide.md
  ```

  Expected: diff only contains the generic workflow, prompts, launch profiles,
  test coverage, and catalog/guidance updates.

- [ ] **Step 3: Commit**

  Stage only files from this plan:

  ```bash
  git add \
    workflows/examples/review_revise_design_docs.orc \
    prompts/workflows/review_revise_design_docs/review.md \
    prompts/workflows/review_revise_design_docs/fix.md \
    .orchestrate/tmp/review-revise-design-docs-parametric/providers.json \
    .orchestrate/tmp/review-revise-design-docs-parametric/prompts.json \
    .orchestrate/tmp/review-revise-design-docs-runtime-foundation/providers.json \
    .orchestrate/tmp/review-revise-design-docs-runtime-foundation/prompts.json \
    tests/test_workflow_lisp_examples.py \
    workflows/README.md \
    docs/capability_status_matrix.md \
    docs/lisp_workflow_drafting_guide.md
  git commit -m "workflow_lisp: add generic design docs review workflow"
  ```

  Expected: commit succeeds without staging unrelated dirty files.

## Fallback Policy

The primary implementation must try `List[DesignDocPath]` first. If that fails:

1. identify whether the failure is type parsing, boundary flattening, CLI input
   binding, prompt injection, lowering, shared validation, or runtime binding;
2. add the narrowest failing test that captures the gap;
3. decide whether to implement that missing boundary or explicitly defer the
   generic workflow launch surface.

Only use a `context_manifest` file if the typed list route is explicitly
accepted as blocked for this tranche. If used, keep it documented as a
compatibility fallback, not the target architecture.
