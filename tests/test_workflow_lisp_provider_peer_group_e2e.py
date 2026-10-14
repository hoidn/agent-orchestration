from __future__ import annotations









from pathlib import Path










import pytest


























from orchestrator.workflow.prompt_dependency_contract import PromptDependencyOriginKind, PromptDependencyPosition, _build_compiler_prompt_dependency_contract, serialize_compiler_prompt_dependency_contract




















_PUBLIC_FIXTURE_ROOT = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "provider_peer_group"
)


_PUBLIC_FIXTURE_FILES = (
    "provider_peer_group_three.orc",
    "providers.json",
    "prompts.json",
    "real_adapter_prompt.md",
)


_PUBLIC_MESSAGE = "Review this literal 🌍 payload.\nSecond line: Ω"


_PEER_MEMBER_IDS = (
    "planner",
    "reviewer",
    "builder",
    "tester",
    "analyst",
    "editor",
    "auditor",
    "publisher",
)


def test_peer_implicit_empty_prompt_contract_is_evidence_valid_and_closed() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        _validate_contract,
    )

    contract = _build_compiler_prompt_dependency_contract(
        required_binding_refs=(),
        optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND,
        instruction=None,
        source_origin_key="peer-group:member",
        source_workflow_bytes=b"(workflow-lisp)",
        origin_kind=(
            PromptDependencyOriginKind
            .WORKFLOW_LISP_PROVIDER_PEER_GROUP_MEMBER_IMPLICIT_EMPTY
        ),
    )
    wire = serialize_compiler_prompt_dependency_contract(contract)

    assert _validate_contract(wire) == wire
    with pytest.raises(ValueError, match="forbid dependency refs"):
        _build_compiler_prompt_dependency_contract(
            required_binding_refs=("unexpected",),
            optional_binding_refs=(),
            position=PromptDependencyPosition.PREPEND,
            instruction=None,
            source_origin_key="peer-group:invalid-member",
            source_workflow_bytes=b"(workflow-lisp)",
            origin_kind=(
                PromptDependencyOriginKind
                .WORKFLOW_LISP_PROVIDER_PEER_GROUP_MEMBER_IMPLICIT_EMPTY
            ),
        )
