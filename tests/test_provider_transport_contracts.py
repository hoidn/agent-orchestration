from pathlib import Path

import yaml


CLAUDE_OPUS_STDIN_WORKFLOWS = [
    Path("workflows/examples/lisp_frontend_design_delta_drain.yaml"),
    Path("workflows/library/lisp_frontend_design_delta_done_review.v214.yaml"),
    Path("workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml"),
    Path("workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml"),
    Path("workflows/library/lisp_frontend_design_delta_work_item.v214.yaml"),
    Path("workflows/examples/generic_run_watchdog.yaml"),
]


def test_long_context_claude_opus_providers_use_stdin_transport():
    for workflow_path in CLAUDE_OPUS_STDIN_WORKFLOWS:
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        provider = workflow["providers"]["claude_opus"]

        assert provider["input_mode"] == "stdin", workflow_path
        assert "${PROMPT}" not in provider["command"], workflow_path
