from __future__ import annotations

import importlib

import pytest

from tests.test_workflow_lisp_build_artifacts import (
    _persisted_fragment_contracts,
)


def test_core_q2_fragment_pair_rejects_reordered_expected_outputs() -> None:
    core_ast = importlib.import_module("orchestrator.workflow.core_ast")
    surface_ast = importlib.import_module("orchestrator.workflow.surface_ast")
    _, contract, expected_outputs = _persisted_fragment_contracts()
    meta = core_ast.CoreStmtMeta(
        id="q2",
        step_id="q2",
        step_kind="provider",
    )
    valid = core_ast.CoreProviderStep(
        meta=meta,
        common=surface_ast.SurfaceStepCommonConfig(
            expected_outputs=expected_outputs
        ),
        provider="test-provider",
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
            core_ast.CoreProviderStep(
                meta=meta,
                common=surface_ast.SurfaceStepCommonConfig(
                    expected_outputs=mismatched
                ),
                provider="test-provider",
                compiler_prompt_fragment_contract=contract,
                compiled_prompt_fragment_identity=(
                    contract.compiled_prompt_fragment_identity
                ),
            )
