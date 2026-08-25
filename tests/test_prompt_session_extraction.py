"""Prompt extraction edge cases for closed OMP text-block arrays."""

import pytest

from orchestrator.prompt_session import PromptSessionError, extract_prompt_bytes
from orchestrator.providers.omp_session import parse_journal_bytes
from tests.test_prompt_session import PRIMARY, _journal, _user


def _extract(content: object) -> bytes:
    journal = parse_journal_bytes(_journal(_user(content)), relpath=PRIMARY)
    return extract_prompt_bytes(journal)


def test_text_array_preserves_empty_member_separator() -> None:
    assert _extract([
        {"type": "text", "text": ""},
        {"type": "text", "text": "hello"},
    ]) == b"\nhello"


def test_text_array_rejects_all_empty_members() -> None:
    with pytest.raises(PromptSessionError, match="prompt_import_invalid"):
        _extract([
            {"type": "text", "text": ""},
            {"type": "text", "text": ""},
        ])
