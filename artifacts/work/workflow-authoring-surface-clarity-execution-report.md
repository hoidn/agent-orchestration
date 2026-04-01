## Completed In This Pass
- Extended `redundant-relpath-boundary-kind` lint to recurse through imported workflow bundles and report alias-qualified paths such as `imports.callee.inputs.design_path`.
- Added a regression test covering imported reusable workflows whose top-level `inputs` and `outputs` redundantly declare both `kind: relpath` and `type: relpath`.
- Kept the change scoped to the review finding; no workflow YAML, prompt files, or runtime semantics were changed.

## Completed Plan Tasks
- Closed the remaining Tranche 3 lint-coverage gap identified in implementation review by covering imported reusable workflows.
- Re-verified the affected imported-workflow example runtimes after the lint traversal change.
- Confirmed there are no remaining unfinished required plan tasks in the approved execution plan.

## Remaining Required Plan Tasks
- None.

## Verification
- `pytest --collect-only tests/test_dsl_linting.py -q` -> 13 tests collected.
- `pytest tests/test_dsl_linting.py -k "relpath or import_output" -v` -> 5 passed.
- `pytest tests/test_workflow_examples_v0.py -k "design_plan_impl_review_stack_v2_call_runtime or dsl_follow_on_plan_impl_review_loop_v2_call_runtime" -v` -> 2 passed.
- `git diff --check` -> no formatting errors.

## Residual Risks
- Verification remained targeted to the imported-boundary lint path and the affected reusable-workflow example runtimes; the full repo test suite was not run.
- Imported-bundle recursion is now covered for redundant relpath boundary warnings, but other lint families still rely on their existing scope by design.
