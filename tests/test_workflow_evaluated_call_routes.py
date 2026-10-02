from __future__ import annotations

from pathlib import Path

from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from tests.workflow_lisp_closed_program_helpers import TARGET, install


def test_context_call_values_match_x1_and_x2_routes_after_readback(tmp_path: Path) -> None:
    observed_fields = (
        "(run-id RunId) (run-state Path.state-root) "
        "(run-artifacts Path.artifact-root) (phase Symbol) "
        "(state Path.state-root) (artifacts Path.artifact-root) (payload Int)"
    )
    cases = (
        (
            "omitted",
            "(defworkflow entry ((payload Int)) -> Observed (call leaf :payload payload))",
            {"payload": 5},
            "runtime-x1",
            {
                "run-id": "runtime-x1",
                "run-state": "state/run",
                "run-artifacts": "artifacts/run",
                "phase": "plan-gate-wrapper",
                "state": "state/plan-gate-wrapper",
                "artifacts": "artifacts/plan-gate-wrapper",
                "payload": 5,
            },
        ),
        (
            "explicit",
            "(defworkflow entry ((phase-ctx PhaseCtx) (payload Int)) -> Observed (call leaf :phase-ctx phase-ctx :payload payload))",
            {
                "payload": 5,
                "phase-ctx": {
                    "run": {
                        "run-id": "explicit-run",
                        "state-root": "state/explicit-run",
                        "artifact-root": "artifacts/explicit-run",
                    },
                    "phase-name": "caller-phase",
                    "state-root": "state/caller-phase",
                    "artifact-root": "artifacts/caller-phase",
                }
            },
            "unused-runtime-id",
            {
                "run-id": "explicit-run",
                "run-state": "state/explicit-run",
                "run-artifacts": "artifacts/explicit-run",
                "phase": "caller-phase",
                "state": "state/caller-phase",
                "artifacts": "artifacts/caller-phase",
                "payload": 5,
            },
        ),
    )
    for mode, entry, inputs, run_id, expected in cases:
        root = tmp_path / mode
        source_path = install(
            root,
            f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
              (defmodule context_probe)
              (import std/context :only (RunCtx PhaseCtx))
              (import std/phase :only (with-phase))
              (export entry)
              (defrecord Observed {observed_fields})
              {entry}
              (defworkflow leaf ((phase-ctx PhaseCtx) (payload Int)) -> Observed
                (with-phase phase-ctx plan-gate-wrapper
                  (record Observed
                    :run-id phase-ctx.run.run-id
                    :run-state phase-ctx.run.state-root
                    :run-artifacts phase-ctx.run.artifact-root
                    :phase phase-ctx.phase-name
                    :state phase-ctx.state-root
                    :artifacts phase-ctx.artifact-root
                    :payload payload))))''',
        )
        typed = compile_typed_program(
            source_path,
            entry_workflow="context_probe::entry",
            source_roots=(root,),
            command_boundaries={},
            workspace_root=root,
        )
        source_path.unlink()
        program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())

        result = evaluate_closed_program(program, inputs, run_id=run_id)

        assert result.json_value() == expected
        assert _legacy_context_output(
            tmp_path / f"legacy-{mode}", entry, inputs, run_id=run_id
        ) == result.json_value()


def _legacy_context_output(
    root: Path,
    entry: str,
    inputs: dict[str, object],
    *,
    run_id: str,
) -> dict[str, object]:
    from orchestrator.state import StateManager
    from orchestrator.workflow.executor import WorkflowExecutor
    from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
    from orchestrator.workflow.signatures import bind_workflow_inputs
    from tests.workflow_bundle_helpers import bundle_context_dict

    source_path = install(
        root,
        f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule context_probe)
          (import std/context :only (RunCtx PhaseCtx))
          (import std/phase :only (with-phase))
          (export entry)
          (defrecord Observed {"(run-id RunId) (run-state Path.state-root) "
                               "(run-artifacts Path.artifact-root) (phase Symbol) "
                               "(state Path.state-root) (artifacts Path.artifact-root) "
                               "(payload Int)"})
          {entry}
          (defworkflow leaf ((phase-ctx PhaseCtx) (payload Int)) -> Observed
            (with-phase phase-ctx plan-gate-wrapper
              (record Observed
                :run-id phase-ctx.run.run-id
                :run-state phase-ctx.run.state-root
                :run-artifacts phase-ctx.run.artifact-root
                :phase phase-ctx.phase-name
                :state phase-ctx.state-root
                :artifacts phase-ctx.artifact-root
                :payload payload))))''',
    )
    bundle = compile_stage3_entrypoint(
        source_path,
        entry_workflow="context_probe::entry",
        source_roots=(root,),
        validate_shared=True,
        workspace_root=root,
    ).validated_bundles_by_name["context_probe::entry"]
    provided: dict[str, object] = {}

    def flatten(prefix: str, value: object) -> None:
        if isinstance(value, dict):
            for name, nested in value.items():
                flatten(f"{prefix}__{name}", nested)
        else:
            provided[prefix] = value

    for name, value in inputs.items():
        if name == "payload":
            provided[name] = value
        else:
            flatten(name, value)
    if "phase-ctx" not in inputs:
        provided["phase-ctx__run__run-id"] = run_id
    contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(contracts, provided, root)
    state = StateManager(workspace=root, run_id=run_id)
    state.initialize(
        str(source_path),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    outcome = WorkflowExecutor(bundle, root, state, retry_delay_ms=0).execute(
        on_error="stop"
    )
    assert outcome["status"] == "completed"
    fields = (
        "run-id",
        "run-state",
        "run-artifacts",
        "phase",
        "state",
        "artifacts",
        "payload",
    )
    return {
        field: outcome["workflow_outputs"][f"return__{field}"]
        for field in fields
    }
