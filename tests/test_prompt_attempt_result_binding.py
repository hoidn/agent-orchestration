"""Pure result-binding construction over retained prompt-attempt authority."""

from __future__ import annotations

import importlib
from typing import Any

import pytest


def _module():
    try:
        return importlib.import_module(
            "orchestrator.workflow.prompt_attempt_result_binding"
        )
    except ModuleNotFoundError:
        pytest.fail(
            "prompt-attempt result-binding module is absent during RED",
            pytrace=False,
        )


def _assert_code(expected: str):
    return pytest.raises(
        _module().PromptAttemptResultBindingError,
        match=f"^{expected}:",
    )


@pytest.mark.parametrize(
    "candidate",
    (
        None,
        {},
        {
            "schema_version": (
                "workflow_prompt_attempt_result_binding.v1"
            ),
            "scope_sha256": "sha256:" + "0" * 64,
            "attempt_ordinal": 1,
            "evidence_relative_path": "evidence.json",
            "evidence_file_sha256": "sha256:" + "1" * 64,
            "record_kind": "prompt_snapshot",
            "extra": None,
        },
        {
            "schema_version": (
                "workflow_prompt_attempt_result_binding.v1"
            ),
            "scope_sha256": "sha256:" + "0" * 64,
            "attempt_ordinal": True,
            "evidence_relative_path": "evidence.json",
            "evidence_file_sha256": "sha256:" + "1" * 64,
            "record_kind": "prompt_snapshot",
        },
        {
            "schema_version": (
                "workflow_prompt_attempt_result_binding.v1"
            ),
            "scope_sha256": "sha256:" + "0" * 64,
            "attempt_ordinal": 1,
            "evidence_relative_path": "../evidence.json",
            "evidence_file_sha256": "sha256:" + "1" * 64,
            "record_kind": "prompt_snapshot",
        },
    ),
)
def test_closed_locator_validator_rejects_invalid_shape(
    candidate: Any,
) -> None:
    with _assert_code("judgment_result_binding_invalid"):
        _module().validate_prompt_attempt_result_binding(candidate)
