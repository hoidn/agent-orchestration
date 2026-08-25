"""Source-private scaffold single-capture agreement regressions."""

import os
from dataclasses import replace

import pytest

from orchestrator.prompt_session import PromptSessionError
from orchestrator.prompt_session_scaffold import verify_private_scaffold
from tests.test_cli_prompt_import import _real_private_resolved


def test_private_verifier_rejects_same_identity_manifest_swap(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator import prompt_session_scaffold

    resolved, private = _real_private_resolved(tmp_path)
    original = prompt_session_scaffold.verify_occupant

    def swapped(*args, **kwargs):
        verified = original(*args, **kwargs)
        return replace(verified, manifest_bytes=b'{"different":true}\n')

    monkeypatch.setattr(prompt_session_scaffold, "verify_occupant", swapped)
    descriptor = os.open(private, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with pytest.raises(PromptSessionError, match="session_link_invalid"):
            verify_private_scaffold(descriptor, resolved.link)
    finally:
        os.close(descriptor)


def test_private_no_tools_verifier_never_reopens_packaged_neutral(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator import prompt_scaffold

    resolved, private = _real_private_resolved(tmp_path, provider="omp_no_tools")
    monkeypatch.setattr(
        prompt_scaffold,
        "_neutral_conf_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("neutral conf reopened")),
    )
    descriptor = os.open(private, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        assert verify_private_scaffold(descriptor, resolved.link).provider == "omp_no_tools"
    finally:
        os.close(descriptor)


def test_public_scaffold_inputs_cannot_claim_source_conf_authority() -> None:
    import hashlib

    from orchestrator.prompt_contract import default_semantic_contract
    from orchestrator.prompt_scaffold import ScaffoldInputs
    from orchestrator.prompt_session_scaffold import _snapshot_from_bytes
    from orchestrator.providers.omp_pin import OMP_BINARY_PIN

    conf = _snapshot_from_bytes({
        "config.yml": b"advisor: {enabled: false}\nmemory: {backend: off}\ntask: {maxConcurrency: 1, maxRecursionDepth: 1, disabledAgents: []}\n"
    })
    with pytest.raises(ValueError, match="internal source-conf authority"):
        ScaffoldInputs(
            prompt_sha256=hashlib.sha256(b"x").hexdigest(),
            contract=default_semantic_contract(),
            provider="omp_no_tools",
            model="gpt-5.6-sol",
            conf_manifest=conf,
            slug="prompt",
            pin=OMP_BINARY_PIN,
            _source_conf_authority=object(),
        )
