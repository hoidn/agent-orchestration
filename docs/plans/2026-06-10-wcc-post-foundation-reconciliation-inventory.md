# WCC / Post-Foundation Reconciliation Inventory

Status: active integration inventory
Created: 2026-06-10

## Branches

- Mainline branch: `main`
- WCC branch: `feat/wcc-middle-end`
- WCC remote: `origin/feat/wcc-middle-end`
- WCC local and remote tip: `df7cb09c43c70e1e16d4096dfe6ba0ee6fe44707`
- Merge base: `95255c92c317c8bd072797037c6503afc3f1214f`
- Main-only commits at inventory time: `13`
- WCC-only commits at inventory time: `7`

Verification:

```bash
git fetch origin
git rev-parse feat/wcc-middle-end
git rev-parse origin/feat/wcc-middle-end
test "$(git rev-parse feat/wcc-middle-end)" = "$(git rev-parse origin/feat/wcc-middle-end)"
git rev-list --left-right --count main...feat/wcc-middle-end
```

## Overlap

The branch diff from `main...feat/wcc-middle-end` touches 93 files with about
27k inserted lines. The overlap is not only textual. Mainline post-foundation
work and the WCC branch both changed Workflow Lisp lowering and resume behavior,
so merge resolution must follow the policy in
`docs/plans/2026-06-10-wcc-post-foundation-reconciliation-plan.md`.

### Compiler / Lowering Overlap

Core compiler and lowering files touched by the WCC branch:

- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/loops.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/typecheck_calls.py`
- `orchestrator/workflow_lisp/typecheck_proofs.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/lowering/context.py`
- `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- `orchestrator/workflow_lisp/lowering/control_loops.py`
- `orchestrator/workflow_lisp/lowering/core.py`
- `orchestrator/workflow_lisp/lowering/effects.py`
- `orchestrator/workflow_lisp/lowering/generated_paths.py`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `orchestrator/workflow_lisp/lowering/phase_flow.py`
- `orchestrator/workflow_lisp/lowering/phase_scope.py`
- `orchestrator/workflow_lisp/lowering/procedures.py`
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`

WCC-owned new substrate files:

- `orchestrator/workflow_lisp/wcc/__init__.py`
- `orchestrator/workflow_lisp/wcc/model.py`
- `orchestrator/workflow_lisp/wcc/elaborate.py`
- `orchestrator/workflow_lisp/wcc/anf.py`
- `orchestrator/workflow_lisp/wcc/analysis.py`
- `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- `orchestrator/workflow_lisp/wcc/lower.py`
- `orchestrator/workflow_lisp/wcc/route.py`

Policy:

- WCC wins for new/default nested structured control, loops, stdlib
  `review-revise-loop`, and union normalization.
- Mainline helper-hoisting behavior may remain only as legacy/schema-1
  compatibility or explicit retirement evidence.
- Returned-variant / F3 behavior must be correct on WCC and, if retained, on
  the legacy route.

### Resume / Runtime Overlap

Runtime/resume files touched by the WCC branch:

- `orchestrator/cli/commands/resume.py`
- `orchestrator/cli/commands/run.py`
- `orchestrator/loader.py`
- `orchestrator/workflow/elaboration.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/state_layout.py`
- `tests/test_resume_command.py`

Mainline also contains the stale `repeat_until` resume-state fix from
`9085577`, touching:

- `orchestrator/state.py`
- `orchestrator/workflow/executor.py`
- `orchestrator/workflow/loops.py`
- `tests/test_resume_command.py`

Policy:

- Preserve WCC lowering-schema / mixed-schema resume safety.
- Preserve stale failed nested-loop result clearing via `clear_loop_step`.
- Verify both with focused resume tests before landing the integration.

### Tests / Fixtures Overlap

WCC test and characterization additions:

- `tests/workflow_lisp_characterization.py`
- `tests/test_workflow_lisp_wcc_characterization.py`
- `tests/test_workflow_lisp_wcc_m1.py`
- `tests/test_workflow_lisp_wcc_m2.py`
- `tests/test_workflow_lisp_wcc_m3.py`
- `tests/test_workflow_lisp_wcc_m4.py`
- `tests/test_workflow_lisp_wcc_m5.py`
- `tests/fixtures/workflow_lisp/characterization/**`
- `tests/fixtures/workflow_lisp/valid/wcc_m1_value_union_letstar.orc`

Existing Workflow Lisp regression files touched by WCC:

- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_cli.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_examples.py`
- `tests/test_workflow_lisp_functions.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_source_map.py`

Policy:

- WCC M1-M5 and characterization suites are required merge evidence.
- Mainline parent-callable post-foundation fixtures must compile/smoke under
  the integrated WCC/default route, or a WCC gap must be recorded and the drain
  must not resume implementation from stale assumptions.

### Workflow Config Overlap

The WCC branch also changes the design-delta drain workflow family model
configuration:

- `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- `workflows/library/lisp_frontend_design_delta_selector.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml`

Policy:

- Preserve the intended post-foundation run configuration.
- Dry-run the drain after integration before resuming or relaunching.

## Resumption Requirement

After reconciliation, the repo must be in a state where implementation of
`docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
can resume without another architecture reconciliation pass.

That requires:

- WCC integrated and pushed to `main`;
- post-foundation design updated to consume WCC;
- active work instructions updated to block stale compiler/lowering gaps;
- associated gap designs classified in a post-WCC reconciliation index;
- stale gaps marked as superseded, compatibility-only, or blocked until
  rewritten; and
- the active drain resumed only if its current selected gap is compatible with
  the integrated WCC substrate.

