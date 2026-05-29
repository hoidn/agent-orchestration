# Workflow Lisp Effectful Composition Lowering Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make realistic Workflow Lisp `.orc` workflows with `with-phase`, `review-revise-loop`, `match`, same-file calls, and local records pass shared validation and become runnable through the existing runtime bridge.

**Architecture:** Preserve the existing architecture: `.orc` lowers to ordinary workflow mappings, then through shared validation and runtime execution. The fix is not to weaken shared validation; it is to make frontend-generated managed write roots, phase transport paths, branch outputs, and local record projections explicit in the lowered Core/YAML-equivalent surface that shared validation already accepts.

**Tech Stack:** Python 3, `orchestrator.workflow_lisp`, existing v2.14 workflow loader/shared validation, pytest, `workflows/examples/kiss_backlog_item.orc`, and focused fixtures under `tests/fixtures/workflow_lisp/`.

---

## Scope

This plan resolves the blocker observed when launching:

```bash
python -m orchestrator run workflows/examples/kiss_backlog_item.orc \
  --entry-workflow run-backlog-item \
  --provider-externs-file .orchestrate/tmp/kiss-backlog-item-orc-launch/providers.json \
  --prompt-externs-file .orchestrate/tmp/kiss-backlog-item-orc-launch/prompts.json \
  --input inputs__backlog_item=docs/backlog/active/LISP-PROC-REFS-PARTIAL-APPLICATION/2026-05-28-design-delta-prompt-api-boundary.md \
  --input inputs__work_instructions=docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/work_instructions.md
```

Current failure:

```text
[workflow_boundary_type_invalid]
Reusable workflow step 'ReviewDecision' hard-codes DSL-managed write roots in output_bundle.path; expose them as typed relpath inputs instead
form: workflow-lisp > defworkflow > review-plan-phase
```

Treat `docs/backlog/active/2026-05-29-workflow-lisp-effectful-composition-lowering.md` as the work-item contract.

## Non-Goals

- Do not weaken reusable workflow validation in `orchestrator/loader.py`.
- Do not special-case `kiss_backlog_item.orc` in the CLI or runtime.
- Do not add YAML generation as an execution path.
- Do not redesign provider prompts or review-loop semantics.
- Do not implement new runtime primitives.
- Do not broaden into ProcRef or collection-type work unless a regression test proves direct interaction.

## Files

Modify:

- `orchestrator/workflow_lisp/lowering.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_examples.py`
- `workflows/examples/kiss_backlog_item.orc` only if the source currently relies on behavior the accepted design does not actually promise
- `docs/backlog/active/2026-05-29-workflow-lisp-effectful-composition-lowering.md` only to update plan/status references after implementation

Read as authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/providers.md`
- `specs/io.md`
- `tests/test_subworkflow_calls.py::test_reusable_workflow_rejects_hard_coded_dsl_managed_write_root`

## Design Decision

The principled fix is to treat generated paths created by phase stdlib forms exactly like generated structured-result write roots:

- generated bundle paths must cross reusable workflow boundaries as explicit relpath inputs;
- call sites must bind those generated inputs to deterministic, non-colliding paths;
- source maps must blame the authored Lisp form, not the generated step;
- shared validation remains the final authority.

For `review-revise-loop`, this means the review decision bundle path currently computed as:

```python
review_contract_path = _join_ref_path(
    context.phase_scope.candidate_root_ref or "inputs.phase-ctx__state-root",
    "review-loop/review-result.json",
)
```

must instead lower to a hidden generated workflow input when the value is used as an `output_bundle.path` inside a reusable workflow:

```python
review_bundle_input = f"__write_root__{review_step_id}__result_bundle"
review_output_bundle["path"] = f"${{inputs.{review_bundle_input}}}"
terminal.hidden_inputs[review_bundle_input] = origin
```

Caller-side existing same-file call logic already binds callee `__write_root__...` inputs to deterministic paths under `.orchestrate/workflow_lisp/calls/...`. Reuse that mechanism.

`phase_prompt_transport` hidden inputs remain separate from `managed_write_root` hidden inputs. Do not collapse these reasons; dashboard/source-map/debug behavior relies on the distinction.

## Task 1: Lock The Current Failure With A Shared-Validation Test

**Files:**

- Modify: `tests/test_workflow_lisp_examples.py`

- [ ] **Step 1: Change the KISS example test to require shared validation**

Replace the current compile-only assertion:

```python
result = compile_stage3_module(
    WORKFLOWS / "kiss_backlog_item.orc",
    provider_externs={...},
    prompt_externs={...},
    validate_shared=False,
    workspace_root=tmp_path,
)
```

with:

```python
result = compile_stage3_module(
    WORKFLOWS / "kiss_backlog_item.orc",
    provider_externs={...},
    prompt_externs={...},
    validate_shared=True,
    workspace_root=tmp_path,
)
```

- [ ] **Step 2: Run the focused test and confirm the current failure**

Run:

```bash
python -m pytest tests/test_workflow_lisp_examples.py::test_kiss_backlog_item_orc_compiles_to_typed_phase_stack -q
```

Expected before implementation: FAIL with `workflow_boundary_type_invalid` mentioning `ReviewDecision` and `DSL-managed write roots`.

- [ ] **Step 3: Keep the existing shape assertions**

Do not remove assertions that the lowered workflows include:

- `draft-plan-phase`
- `review-plan-phase`
- `execute-implementation-phase`
- `review-implementation-phase`
- `run-approved-plan`
- `run-backlog-item`

The test should prove both shared-validation success and preservation of the ergonomic `.orc` lowering shape.

## Task 2: Parameterize `review-revise-loop` Review Bundle Write Roots

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Add a focused phase-stdlib regression test**

In `tests/test_workflow_lisp_phase_stdlib.py`, add a test near `test_shared_validation_accepts_review_revise_loop`:

```python
def test_review_revise_loop_review_bundle_path_is_generated_write_root(tmp_path: Path) -> None:
    result = _compile(
        VALID_REVIEW_LOOP_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "review-revise-loop-demo"
    )
    authored = lowered.authored_mapping
    repeat_step = next(step for step in authored["steps"] if "repeat_until" in step)
    review_step = next(
        step
        for step in _iter_nested_steps(repeat_step["repeat_until"]["steps"])
        if step.get("name") == "ReviewDecision"
    )

    hidden_inputs = authored["inputs"]
    review_path = review_step["output_bundle"]["path"]

    assert review_path.startswith("${inputs.__write_root__")
    assert review_path.endswith("__result_bundle}")
    assert review_path.removeprefix("${inputs.").removesuffix("}") in hidden_inputs
    assert {
        item.generated_name: item.reason
        for item in lowered.boundary_projection.generated_internal_inputs
    }[review_path.removeprefix("${inputs.").removesuffix("}")] == "managed_write_root"
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_review_revise_loop_review_bundle_path_is_generated_write_root -q
```

Expected before implementation: FAIL because `ReviewDecision.output_bundle.path` is derived from `inputs.phase-ctx__state-root` or a phase candidate root, not a generated write-root input.

- [ ] **Step 3: Change `_lower_review_revise_loop` to use a hidden managed write root**

In `orchestrator/workflow_lisp/lowering.py`, inside `_lower_review_revise_loop`:

1. Compute the review step id before building `review_output_bundle`.
2. Build a hidden input name from that step id:

```python
review_step_name = "ReviewDecision"
review_step_id = "review_decision"
review_hidden_input = f"__write_root__{review_step_id}__result_bundle"
```

If the hidden input name must be globally unique across multiple review loops in one workflow, include the enclosing `context.step_name_prefix`:

```python
review_hidden_input = f"__write_root__{repeat_step_id}__review_decision__result_bundle"
```

Prefer the globally unique form if tests show collisions.

3. Set:

```python
review_contract_path = f"${{inputs.{review_hidden_input}}}"
```

4. Add the input to the existing `hidden_inputs` returned by `_build_phase_stdlib_prompt_input_prelude`:

```python
hidden_inputs[review_hidden_input] = _origin_from_context_source(context, expr)
context.internal_generated_input_reasons.setdefault(review_hidden_input, "managed_write_root")
```

- [ ] **Step 4: Preserve prompt transport hidden input behavior**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_labels_phase_prompt_hidden_inputs_distinct_from_write_roots -q
```

Expected: PASS. If it fails, the change accidentally relabeled `phase_prompt_transport`.

- [ ] **Step 5: Run phase stdlib tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -q
```

Expected: PASS.

## Task 3: Ensure Same-File Call Sites Bind New Phase Stdlib Write Roots

**Files:**

- Modify: `tests/test_workflow_lisp_examples.py`
- Modify: `orchestrator/workflow_lisp/lowering.py` only if existing same-file call binding logic misses the new input

- [ ] **Step 1: Add assertions for caller-bound review-loop write roots**

In `tests/test_workflow_lisp_examples.py`, after `lowered_by_name` is built, inspect `run-backlog-item` and `run-approved-plan` call steps:

```python
run_backlog_item = lowered_by_name["run-backlog-item"]
run_approved_plan = lowered_by_name["run-approved-plan"]

review_plan_call = next(
    step for step in run_backlog_item["steps"]
    if step.get("call") == "review-plan-phase"
)
review_impl_call = next(
    step for step in run_approved_plan["steps"]
    if step.get("call") == "review-implementation-phase"
)

assert any(name.startswith("__write_root__") for name in review_plan_call["with"])
assert any(name.startswith("__write_root__") for name in review_impl_call["with"])
assert all(
    str(value).startswith(".orchestrate/workflow_lisp/calls/")
    for name, value in review_plan_call["with"].items()
    if name.startswith("__write_root__")
)
```

- [ ] **Step 2: Run the example test**

Run:

```bash
python -m pytest tests/test_workflow_lisp_examples.py::test_kiss_backlog_item_orc_compiles_to_typed_phase_stack -q
```

Expected after Task 2: PASS, unless same-file call binding misses the new hidden input.

- [ ] **Step 3: If call binding fails, fix `_managed_inputs_from_mapping`/call lowering only**

If the new hidden input is present in `review-plan-phase.authored_mapping["inputs"]` but absent from caller `with`, inspect:

- `_managed_inputs_from_mapping`
- `_managed_inputs_from_bundle`
- `_lower_call_expr`
- private-workflow call handling around `.orchestrate/workflow_lisp/calls/...`

The correct fix is to make all generated internal inputs with reason `managed_write_root` visible to the existing call-binding path. Do not hand-code `review-revise-loop` names at call sites.

## Task 4: Make The `.orc` Runtime Launch Reach Runtime Execution

**Files:**

- Modify: `tests/test_workflow_lisp_cli.py` if a dry-run regression belongs there
- Modify: no source files unless the dry-run reveals a separate frontend/runtime bridge defect

- [ ] **Step 1: Create launch externs under `.orchestrate/tmp`**

Run:

```bash
mkdir -p .orchestrate/tmp/kiss-backlog-item-orc-launch
cat > .orchestrate/tmp/kiss-backlog-item-orc-launch/providers.json <<'JSON'
{
  "providers.plan": "codex",
  "providers.plan-review": "codex",
  "providers.plan-fix": "codex",
  "providers.implementation": "codex",
  "providers.implementation-review": "codex",
  "providers.implementation-fix": "codex"
}
JSON
cat > .orchestrate/tmp/kiss-backlog-item-orc-launch/prompts.json <<'JSON'
{
  "prompts.plan.draft": "workflows/library/prompts/design_plan_impl_stack_v2_call/draft_plan.md",
  "prompts.plan.review": "workflows/library/prompts/design_plan_impl_stack_v2_call/review_plan.md",
  "prompts.plan.fix": "workflows/library/prompts/design_plan_impl_stack_v2_call/revise_plan.md",
  "prompts.implementation.execute": "workflows/library/prompts/design_plan_impl_stack_v2_call/implement_plan.md",
  "prompts.implementation.review": "workflows/library/prompts/design_plan_impl_stack_v2_call/review_implementation.md",
  "prompts.implementation.fix": "workflows/library/prompts/design_plan_impl_stack_v2_call/fix_implementation.md"
}
JSON
```

- [ ] **Step 2: Compile the `.orc` workflow through shared validation**

Run:

```bash
python -m orchestrator compile workflows/examples/kiss_backlog_item.orc \
  --entry-workflow run-backlog-item \
  --provider-externs-file .orchestrate/tmp/kiss-backlog-item-orc-launch/providers.json \
  --prompt-externs-file .orchestrate/tmp/kiss-backlog-item-orc-launch/prompts.json \
  --emit-debug-yaml .orchestrate/tmp/kiss-backlog-item-orc-launch/expanded.debug.yaml \
  --emit-core-ast .orchestrate/tmp/kiss-backlog-item-orc-launch/core_workflow_ast.json \
  --emit-semantic-ir .orchestrate/tmp/kiss-backlog-item-orc-launch/semantic_ir.json \
  --emit-source-map .orchestrate/tmp/kiss-backlog-item-orc-launch/source_map.json
```

Expected: PASS. The emitted debug YAML must show `ReviewDecision.output_bundle.path` as an `${inputs.__write_root__...}` reference in both review workflows.

- [ ] **Step 3: Dry-run the `.orc` runtime bridge**

Run:

```bash
python -m orchestrator run workflows/examples/kiss_backlog_item.orc \
  --entry-workflow run-backlog-item \
  --provider-externs-file .orchestrate/tmp/kiss-backlog-item-orc-launch/providers.json \
  --prompt-externs-file .orchestrate/tmp/kiss-backlog-item-orc-launch/prompts.json \
  --dry-run \
  --input inputs__backlog_item=docs/backlog/active/LISP-PROC-REFS-PARTIAL-APPLICATION/2026-05-28-design-delta-prompt-api-boundary.md \
  --input inputs__work_instructions=docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/work_instructions.md
```

Expected: PASS validation. If it fails because the CLI input names differ, inspect emitted Core AST and use the actual flattened names; do not change the compiler unless the flattened input names are wrong or undocumented.

## Task 5: Support General Effectful Branch Composition

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_examples.py`

This task handles the broader backlog item if Task 2 only unblocks `review-revise-loop` reusable validation.

- [ ] **Step 1: Add a fixture or inline test where `match` arm bodies contain effectful expressions**

Use a small `.orc` fixture that:

- calls `provider-result` returning a union;
- `match`es the union;
- runs a review-loop or same-file call only in the `COMPLETED` branch;
- returns a shared record result.

Expected before implementation if unsupported: `workflow_return_not_exportable` or equivalent branch-lowering error.

- [ ] **Step 2: Generalize `_lower_match_expr` branch lowering**

Find `_lower_match_expr` in `orchestrator/workflow_lisp/lowering.py`.

The target behavior:

- each branch gets a child lowering context with the existing variant proof/local binding;
- branch body lowers through `_lower_expression`, not only record-literal projection;
- branch outputs are projected through `_conditional_case_outputs` or an equivalent helper;
- branch `hidden_inputs` are merged into the enclosing terminal hidden inputs;
- source maps for branch-generated steps point back to the branch body and `match` form.

Do not make string predicates imply variant proof.

- [ ] **Step 3: Add a test where `with-phase` is bound in `let*`**

The test should prove this shape is legal:

```lisp
(let* ((review
         (with-phase phase-ctx implementation-review
           (review-revise-loop ...))))
  ...)
```

Expected: PASS shared validation.

- [ ] **Step 4: Add a test where a locally constructed record is passed to a same-file call**

The test should cover:

```lisp
(call helper
  :inputs
    (record ImplementationInputs
      :backlog_item backlog_item
      :work_instructions work_instructions
      :plan_path plan.plan_path))
```

If this still fails with `workflow_signature_mismatch`, fix `_render_call_binding_ref` / `_resolve_inline_field_value` so every record leaf lowers to an existing input ref, step artifact ref, or generated local ref.

- [ ] **Step 5: Run composition tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_examples.py -q
```

Expected: PASS.

## Task 6: Runtime Smoke Launch In tmux

**Files:**

- No source changes expected

- [ ] **Step 1: Launch the `.orc` workflow in tmux**

Use the `tmux` skill. Run:

```bash
python -m orchestrator run workflows/examples/kiss_backlog_item.orc \
  --entry-workflow run-backlog-item \
  --provider-externs-file .orchestrate/tmp/kiss-backlog-item-orc-launch/providers.json \
  --prompt-externs-file .orchestrate/tmp/kiss-backlog-item-orc-launch/prompts.json \
  --stream-output \
  --step-summaries \
  --summary-mode async \
  --summary-provider claude_sonnet_summary \
  --live-agent-notes \
  --live-agent-note-provider claude_haiku_summary \
  --input inputs__backlog_item=docs/backlog/active/LISP-PROC-REFS-PARTIAL-APPLICATION/2026-05-28-design-delta-prompt-api-boundary.md \
  --input inputs__work_instructions=docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/work_instructions.md
```

- [ ] **Step 2: Poll for early failures**

Check:

```bash
tmux -S /tmp/claude-tmux-sockets/claude.sock capture-pane -p -J -t <session>:0.0 -S -200
find .orchestrate/runs -maxdepth 2 -name state.json -printf '%T@ %p\n' | sort -nr | head
python -m orchestrator report <run_id>
```

Expected: the workflow creates a run and enters provider execution, rather than failing during `.orc` compilation/shared validation.

- [ ] **Step 3: If a provider later makes a bad semantic judgment, do not treat it as a frontend lowering failure**

This plan’s runtime acceptance is reaching normal workflow execution. Provider quality issues belong to prompts/workflow design, not the lowering fix, unless they reveal missing output contracts or bad prompt injection from `.orc` lowering.

## Task 7: Docs And Backlog Closure

**Files:**

- Modify: `docs/backlog/active/2026-05-29-workflow-lisp-effectful-composition-lowering.md`
- Modify: `workflows/README.md` only if `kiss_backlog_item.orc` is now runtime-ready
- Modify: `docs/lisp_workflow_drafting_guide.md` only if the authoring guidance changes

- [ ] **Step 1: Update the backlog item with the plan path**

Change:

```markdown
- Plan: none yet
```

to:

```markdown
- Plan: `docs/plans/2026-05-29-workflow-lisp-effectful-composition-lowering-fix-plan.md`
```

- [ ] **Step 2: Update workflow catalog wording only after runtime dry-run succeeds**

If Task 4 passes, update `workflows/README.md` so `kiss_backlog_item.orc` is no longer described as shared-validation-blocked. Be precise: if full provider execution was not completed, say it is shared-validation/runtime-bridge ready, not production-proven.

- [ ] **Step 3: Run final verification**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_phase_stdlib.py -q
python -m pytest tests/test_workflow_lisp_examples.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_lowering.py::test_compile_stage3_module_labels_phase_prompt_hidden_inputs_distinct_from_write_roots -q
python -m orchestrator compile workflows/examples/kiss_backlog_item.orc \
  --entry-workflow run-backlog-item \
  --provider-externs-file .orchestrate/tmp/kiss-backlog-item-orc-launch/providers.json \
  --prompt-externs-file .orchestrate/tmp/kiss-backlog-item-orc-launch/prompts.json \
  --emit-debug-yaml .orchestrate/tmp/kiss-backlog-item-orc-launch/expanded.debug.yaml
```

Expected: all pass.

## Implementation Notes

- The first fix should be narrow: make `review-revise-loop` use generated managed write-root inputs for provider output bundles.
- If that unblocks `kiss_backlog_item.orc`, stop and verify before broadening.
- Only implement Task 5 if tests still expose the broader composition failures or if the KISS example requires those behaviors to pass shared validation.
- Keep source-map coverage strict. If adding hidden inputs, update `context.generated_input_spans` through the existing `terminal.hidden_inputs` path rather than bypassing it.
- Do not hide generated paths in pointer files. The hidden relpath inputs are semantic workflow boundary inputs, not pointer authority.

