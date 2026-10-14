"""Parser options retained by evaluated run and resume commands."""

from orchestrator.cli.main import create_parser


def test_parser_accepts_stream_output_on_run_and_resume() -> None:
    parser = create_parser()

    run_args = parser.parse_args(["run", "workflow.orc", "--stream-output"])
    resume_args = parser.parse_args(["resume", "run-123", "--stream-output"])
    run_default_args = parser.parse_args(["run", "workflow.orc"])

    assert run_args.stream_output is True
    assert resume_args.stream_output is True
    assert run_default_args.stream_output is False


def test_parser_accepts_state_dir_on_run_and_resume() -> None:
    parser = create_parser()

    run_args = parser.parse_args(
        ["run", "workflow.orc", "--state-dir", "/tmp/custom-runs"]
    )
    resume_args = parser.parse_args(
        ["resume", "run-123", "--state-dir", "/tmp/custom-runs"]
    )

    assert run_args.state_dir == "/tmp/custom-runs"
    assert resume_args.state_dir == "/tmp/custom-runs"
