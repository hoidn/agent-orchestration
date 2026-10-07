# Nested union control-summary correction

Status: bounded correction implemented and independently reviewed PASS at `d6adb627` during the early Phase 6a pilot. The [pilot report](../reports/2026-10-07-evaluated-execution-phase-6a-pilot.md#final-campaign-and-compatibility) owns later caller qualification, compatibility/full-suite evidence and closeout status. No language-target or Phase 5 selection.

The pilot's target-2.35 `std/improve` specialization rejects an admitted nested union with `collection_element_type_unsupported`. A scratch instrumented compile reaches `command_control_summary._leaf_output_names` and then `_flatten_boundary_leaf_paths` without a type environment; the contract builder consequently disables nested structural transport. Flattening the workflow's internal data into extra records works, but must not become a required workaround for a compiler defect.

Authorities: [documentation routing](../index.md), [evaluated execution](../design/workflow_lisp_evaluated_execution.md), [nested structural transport](../design/workflow_lisp_frontend_specification.md), and the [pilot plan](2026-10-07-evaluated-execution-phase-6a-pilot-plan.md). Physical evidence belongs in `.superpowers/sdd/2026-10-07-evaluated-execution-phase-6a-pilot-plan/`, under `nested-control-fix/`. The original rejected sources, diagnostics and scratch instrumentation must be retained there before implementation.

Use the existing type environment and control-summary path. Preserve the flat route's existing behavior and artifacts; no global default environment, new schema, output-name framework, duplicated contract builder or compiler-wide cleanup. This scope deliberately leaves unrelated legacy projection limitations for separate evidence and disposition. If preserving the old route or fixing an admitted sibling requires a larger contract decision, return the concrete case to Design before expanding the correction.

## 1. Confirm the shared failure and write the regression

- Inventory callers of `_leaf_output_names`, `_private_procedure_output_names` and `_flatten_boundary_leaf_paths`, including procedure specialization and control-summary consumers. Trace which callers the evaluated route actually reaches; do not indiscriminately change legacy lowering.
- Retain the pilot rejection and reduce it to an executable target-2.35 witness with a nested union in the generic hook result. Cover direct and procedure-return/control-summary entry paths when they share the missing environment; an imported `std/improve` specialization is the motivating public witness.
- Add the smallest meaningful regression in a new focused test owner or an existing suitable owner below its size limit. Run collection and observe the actual diagnostic before changing production code. Distinguish absence of a fixture from a compiler refusal.

## 2. Propagate the environment at the responsible seam

- Modify `orchestrator/workflow_lisp/lowering/command_control_summary.py` and only necessary adjacent callers. Prefer passing the existing `ControlFacts.type_env` through the evaluated control-summary path. The actual trace must determine the fix; this plan does not authorize suppressing the diagnostic or relaxing type/path validation.
- Check the leaf and private-procedure cases together, including nested records/unions and generic specializations. Existing flat-route calls retain their current contract unless an independently reviewed correction proves byte-identical behavior for accepted programs.
- Recompile the original rejected source. Run the regression and the narrow relevant command-control, generic-union and closed-program controls. Keep new functions below default Radon CC 12 and new modules below 500 physical lines; avoid unrelated refactors.

## 3. Prove public behavior and integrate

- Through the public CLI, compile and dry-run the corrected nested-union specimen, then run it with deterministic providers/commands, stop at an actual committed effect, resume and verify no committed redispatch. Reuse existing fixture and stop hooks; no new launcher or live-provider study.
- Retain raw commands, diagnostics, exits, source hashes and resumed result/artifact evidence. Exercise representative accepted old-target controls and compare their raw artifacts when this seam is reached. Any package-identity changes remain explicit; do not normalize or suppress pins.
- Obtain independent code/evidence review and coordinator diff review, then commit by explicit pathspec and integrate into the pilot checkout. Revisit the simplest caller using the corrected type contract, preserving the public `Review`, `Outcome`, refined paths, effect order and final-round no-extra-coder rule. The earlier passing flat-adapter variant remains comparison evidence, not a required language shape.
- The pilot's final affected checks and required full `pytest -q -n 16 --dist=worksteal` campaign in tmux include this correction. Do not duplicate that full campaign for this bounded cut. Prior Phase 3 evidence remains attached to its original code; identify affected owners before reusing any claim.

The implementation worker owns code/tests and narrow verification; the coordinator owns the sole verification window, integration and final campaign. A reviewer distinct from the implementer reviews both the supported-type obligation and the old-route boundary. No canonical consumer, stdlib signature, new target, parallel effect or retirement decision is included.
