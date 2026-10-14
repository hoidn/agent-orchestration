"""Retained scaffold directory identity naming without retired publication."""

from pathlib import Path

from orchestrator.prompt_scaffold import scaffold_dir_name, slugify
from tests.test_prompt_scaffold import _inputs


def test_inline_prompt_identity_slug_is_literal_prompt():
    inputs = _inputs(b"p", provider="omp_no_tools", slug="prompt")
    assert scaffold_dir_name(inputs).startswith("prompt-")


def test_prompt_file_identity_slug_is_normalized_lowercase_stem():
    stem = Path("My Meeting Notes v2.md").stem
    inputs = _inputs(b"p", provider="omp_no_tools", slug=slugify(stem))
    assert scaffold_dir_name(inputs).startswith("my-meeting-notes-v2-")
