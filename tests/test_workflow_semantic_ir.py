from dataclasses import replace

import pytest

from orchestrator.workflow.semantic_ir import SemanticPromptSurface
from orchestrator.workflow.executable_ir import ProviderStepConfig, StepCommonConfig
from tests.test_workflow_lisp_build_artifacts import _persisted_fragment_contracts


def test_semantic_and_executable_q2_boundaries_require_exact_expected_outputs() -> None:
    q1, q2, expected_outputs = _persisted_fragment_contracts()
    for contract in (q1, q2):
        surface = SemanticPromptSurface(prompt_surface_id="prompt", workflow_name="historical",
            statement_id="provider", provider_name="test-provider",
            compiler_prompt_fragment_contract=contract,
            compiled_prompt_fragment_identity=contract.compiled_prompt_fragment_identity)
        assert surface.compiler_prompt_fragment_contract is contract
        with pytest.raises(ValueError, match="compiled_prompt_fragment_identity_mismatch" if contract is q1 else "prompt_output_position_contract_mismatch"):
            replace(surface, compiled_prompt_fragment_identity="sha256:" + "5" * 64)
    config = ProviderStepConfig(common=StepCommonConfig(expected_outputs=expected_outputs),
        compiler_prompt_fragment_contract=q2,
        compiled_prompt_fragment_identity=q2.compiled_prompt_fragment_identity)
    assert config.common.expected_outputs == expected_outputs
    for outputs in ((), expected_outputs[:1], (*expected_outputs, expected_outputs[0]),
        tuple(reversed(expected_outputs)),
        ({**expected_outputs[0], "path": "${inputs.second}"}, expected_outputs[1])):
        with pytest.raises(ValueError, match="prompt_output_position_contract_mismatch"):
            replace(config, common=replace(config.common, expected_outputs=outputs))
