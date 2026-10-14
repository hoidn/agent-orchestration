"""Tests for the typed surface workflow bundle and authored-shape AST."""


import pytest

from orchestrator.workflow.loaded_bundle import (
    workflow_context,
    workflow_input_contracts,
    workflow_output_contracts,
)
from orchestrator.workflow.surface_ast import (
    SurfaceStep,
    SurfaceStepCommonConfig,
    SurfaceStepKind,
)
from tests.test_workflow_lisp_build_artifacts import (
    _persisted_fragment_contracts,
)


def test_surface_q2_fragment_pair_is_exact_and_ordered() -> None:
    _, contract, expected_outputs = _persisted_fragment_contracts()
    valid = SurfaceStep(
        name="Q2",
        step_id="q2",
        kind=SurfaceStepKind.PROVIDER,
        provider="test-provider",
        common=SurfaceStepCommonConfig(expected_outputs=expected_outputs),
        compiler_prompt_fragment_contract=contract,
        compiled_prompt_fragment_identity=(
            contract.compiled_prompt_fragment_identity
        ),
    )
    assert valid.common.expected_outputs == expected_outputs

    for mismatched in (
        (),
        expected_outputs[:1],
        (*expected_outputs, expected_outputs[0]),
        tuple(reversed(expected_outputs)),
        (
            {**expected_outputs[0], "path": "${inputs.second}"},
            expected_outputs[1],
        ),
    ):
        with pytest.raises(
            ValueError,
            match="prompt_output_position_contract_mismatch",
        ):
            SurfaceStep(
                name="Q2",
                step_id="q2",
                kind=SurfaceStepKind.PROVIDER,
                provider="test-provider",
                common=SurfaceStepCommonConfig(
                    expected_outputs=mismatched
                ),
                compiler_prompt_fragment_contract=contract,
                compiled_prompt_fragment_identity=(
                    contract.compiled_prompt_fragment_identity
                ),
            )


def test_loaded_workflow_helpers_require_loaded_bundle() -> None:
    """Bundle compatibility helpers should reject raw workflow mappings."""
    with pytest.raises(TypeError, match="LoadedWorkflowBundle"):
        workflow_context({"context": {"project": "typed-pipeline"}})

    with pytest.raises(TypeError, match="LoadedWorkflowBundle"):
        workflow_input_contracts({"inputs": {"task_path": {"kind": "relpath"}}})

    with pytest.raises(TypeError, match="LoadedWorkflowBundle"):
        workflow_output_contracts({"outputs": {"report_path": {"kind": "relpath"}}})
