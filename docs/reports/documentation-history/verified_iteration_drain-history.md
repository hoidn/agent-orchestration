# Verified Iteration Drain: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [verified_iteration_drain.md](../../design/verified_iteration_drain.md).

## Original delivery metadata

The promoted authoring and launch surface is
`workflows/library/verified_iteration_drain/drain.orc`, entry
`verified_iteration_drain/drain::drain`. Its final typed parity report is
`artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final/verified_iteration_drain.json`.
The historical YAML twin was retired after its Stage 6 Task 6 reference and
supported-run deletion gates passed.

The sections below describe the implemented baseline. The
[accepted history-input extension](../../design/verified_iteration_drain.md#accepted-extension-prepare-selected-history-input)
changes the canonical consumer in both execution routes and is implemented on
both: Phase 3 Task 13D (`4acd38ec`) revised the shared source, its two
prompts and the Prepare script, extended the legacy-route tests and added the
public target-2.35 copy with its fixture
(`tests/test_workflow_evaluated_verified_drain.py`); the maintained consumer
programs followed at 2.35 (`ad6498d9`), and Task 14 proved the drain's argv
parity beside the watchdog handoff (`f8f2d150`). The owners are named in
[evaluated execution §9.1.2](../../design/workflow_lisp_evaluated_execution.md#912-artifact-handoff-within-the-admitted-release).
Historical parity evidence above does not verify that extension.
