"""Prompt scaffold slug behavior split from the primary CLI seam tests."""

from tests.test_cli_prompt import (
    TASK_TEXT,
    _exit,
    _generated_scaffold,
    fake_runtime,
)


def test_inline_prompt_slug_is_literal_prompt(tmp_path, monkeypatch, fake_runtime):
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    assert _generated_scaffold(tmp_path).name.startswith("prompt-")


def test_prompt_file_slug_is_normalized_lowercase_stem(
    tmp_path, monkeypatch, fake_runtime
):
    prompt_file = tmp_path / "My Meeting Notes v2.md"
    prompt_file.write_bytes(TASK_TEXT.encode("utf-8"))
    code = _exit(
        ["prompt", "run", "--prompt-file", str(prompt_file),
         "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    scaffold = _generated_scaffold(tmp_path)
    assert scaffold.name.startswith("my-meeting-notes-v2-"), scaffold.name


def test_external_workspace_rerun_is_refused_before_execution(
    tmp_path, monkeypatch, fake_runtime
):
    prompt_file = tmp_path / "My Meeting Notes v2.md"
    prompt_file.write_bytes(TASK_TEXT.encode("utf-8"))
    code = _exit(
        ["prompt", "run", "--prompt-file", str(prompt_file),
         "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    scaffold = _generated_scaffold(tmp_path)
    fake_runtime.executed.clear()
    rerun_workspace = tmp_path / "slug-rerun"
    rerun_workspace.mkdir()
    code = _exit(
        ["prompt", "run", "--scaffold", str(scaffold)],
        rerun_workspace,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []
    assert not (rerun_workspace / ".orchestrate").exists()
