"""Native private scaffold tamper and descriptor failure boundaries."""

import os

import pytest

from orchestrator.prompt_session import PromptSessionError
from orchestrator.prompt_session_scaffold import verify_private_scaffold
from tests.test_prompt_session import _real_private_resolved


def test_native_private_scaffold_rejects_preplanted_prompt_bytes(tmp_path):
    resolved, private = _real_private_resolved(tmp_path)
    prompt = private / "prompt.md"
    prompt.chmod(0o600)
    prompt.write_bytes(b"planted")
    prompt.chmod(0o400)
    descriptor = os.open(private, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with pytest.raises(PromptSessionError, match="session_link_invalid"):
            verify_private_scaffold(descriptor, resolved.link)
    finally:
        os.close(descriptor)
    assert prompt.read_bytes() == b"planted"


def test_native_private_scaffold_fstat_failure_closes_owned_descriptor(tmp_path, monkeypatch):
    from orchestrator._common import safe_tree

    resolved, private = _real_private_resolved(tmp_path)
    descriptor = os.open(private, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    original_close = os.close
    closed = []
    try:
        with monkeypatch.context() as patch:
            def tracked_close(owned):
                closed.append(owned)
                original_close(owned)

            def failed_fstat(_descriptor):
                raise OSError("fstat failed")

            patch.setattr(safe_tree.os, "close", tracked_close)
            patch.setattr(safe_tree.os, "fstat", failed_fstat)
            with pytest.raises(PromptSessionError, match="session_link_invalid"):
                verify_private_scaffold(descriptor, resolved.link)
        assert closed
        assert descriptor not in closed
        for owned in closed:
            with pytest.raises(OSError):
                os.fstat(owned)
        assert os.fstat(descriptor)
    finally:
        original_close(descriptor)
