"""Retained prompt argparse boundaries and native resume grammar."""

from pathlib import Path

from orchestrator.cli.main import main

INFERENCE_PROVIDER = "omp_conf_inference"
TASK_TEXT = "source capture"


def _exit(main_argv: list[str], tmp_path: Path, monkeypatch) -> int:
    """Run the real CLI; argparse failures surface as SystemExit(2)."""
    monkeypatch.chdir(tmp_path)
    try:
        return main(main_argv)
    except SystemExit as exc:
        return int(exc.code)


def _invoke_main(argv: list[str]) -> int:
    try:
        return main(argv)
    except SystemExit as exc:
        return int(exc.code)


def test_prompt_parser_rejects_non_public_provider_choices(tmp_path, monkeypatch):
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", INFERENCE_PROVIDER],
              tmp_path, monkeypatch)
        == 2
    )
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", "bogus"],
              tmp_path, monkeypatch)
        == 2
    )
    assert not (tmp_path / ".orchestrate").exists()


def test_positional_extras_fail(tmp_path, monkeypatch):
    assert (
        _exit(["prompt", "run", "extra", "--prompt", "x",
               "--provider", "omp_no_tools"],
              tmp_path, monkeypatch)
        == 2
    )
    assert not (tmp_path / ".orchestrate").exists()


def test_prompt_parser_errors_precede_handler_and_destination_creation(
    tmp_path, monkeypatch
):
    def forbidden(_args):
        raise AssertionError("invalid argparse input reached prompt handler")

    monkeypatch.setattr("orchestrator.cli.commands.prompt_workflow", forbidden)
    bad_argv = [
        ["prompt", "run", "--prompt", "x", "--provider", INFERENCE_PROVIDER],
        ["prompt", "run", "--prompt", "x", "--provider", "omp_no_tools", "extra"],
    ]
    for argv in bad_argv:
        assert _exit(argv, tmp_path, monkeypatch) == 2, argv
        assert not (tmp_path / ".orchestrate").exists(), argv


def test_abbreviated_prompt_long_options_are_rejected(
    tmp_path, monkeypatch
):
    """Unique prefixes such as --scaf/--ret/--provide are unrecognized:
    verified rerun and generation accept exactly the named flags, so any
    abbreviation must exit 2 before provider calls or destination creation."""
    def forbidden(_args):
        raise AssertionError("abbreviated option reached prompt handler")

    monkeypatch.setattr("orchestrator.cli.commands.prompt_workflow", forbidden)
    prompt_file = tmp_path / "abbrev.md"
    prompt_file.write_bytes(TASK_TEXT.encode("utf-8"))
    bad_argv = [
        # --scaf abbreviates --scaffold on the rerun branch.
        ["prompt", "run", "--scaf", str(tmp_path / "missing-scaffold")],
        # --ret abbreviates --returns on the generation branch.
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools",
         "--ret", '{"mode":"scalar","type":"String"}'],
        # --provide abbreviates --provider.
        ["prompt", "run", "--prompt", TASK_TEXT, "--provide", "omp_no_tools"],
        # --prompt-f abbreviates --prompt-file.
        ["prompt", "run", "--prompt-f", str(prompt_file),
         "--provider", "omp_no_tools"],
    ]
    for argv in bad_argv:
        assert _exit(argv, tmp_path, monkeypatch) == 2, argv
        assert not (tmp_path / ".orchestrate").exists(), argv
        assert not (tmp_path / "workflows" / "generated").exists(), argv


def test_prompt_resume_grammar_is_exactly_id_and_in_place() -> None:
    # Valid grammar under a non-TTY dispatch must reach the TTY gate (exit 1),
    # never argparse (exit 2) and never a launch.
    assert _invoke_main(["prompt", "resume", "run-1"]) == 1
    assert _invoke_main(["prompt", "resume", "run-1", "--in-place"]) == 1


def test_prompt_resume_rejects_unknown_repeated_and_extra_grammar() -> None:
    assert _invoke_main(["prompt", "resume"]) == 2
    assert _invoke_main(["prompt", "resume", "run-1", "--extra"]) == 2
    assert _invoke_main(["prompt", "resume", "run-1", "positional"]) == 2
    assert _invoke_main(["prompt", "resume", "run-1", "--in-place", "--in-place"]) == 2
    assert _invoke_main(["prompt", "resume", "run-1", "--fork"]) == 2
    assert _invoke_main(["prompt", "resume", "run-1", "--in-place", "--model", "x"]) == 2
