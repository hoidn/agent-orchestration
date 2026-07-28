"""CLI contracts for the private provider materialization submit client."""

from __future__ import annotations

import json
from pathlib import Path
import ast
import inspect

import pytest

from orchestrator.cli.commands import provider_materialization
from orchestrator.cli.main import main
from orchestrator.workflow.provider_phased_delivery.diagnostics import (
    DiagnosticSource,
    PhasedDeliveryDiagnostic,
    RejectedValue,
    diagnostic_definition,
)
from orchestrator.workflow.provider_phased_delivery.models import SubmitReceipt
from orchestrator.workflow.provider_phased_delivery.protocol import (
    MAX_CLIENT_REQUEST_ID_BYTES,
)


def _digest(byte: str) -> str:
    return "sha256:" + byte * 64


def _receipt(request_id: str, *, status: str) -> SubmitReceipt:
    diagnostic = None
    if status == "failed":
        definition = diagnostic_definition("submit_lifecycle_invalid")
        diagnostic = PhasedDeliveryDiagnostic(
            code=definition.code,
            reason=definition.reason,
            rejected_value=RejectedValue(
                type=definition.value_type,
                canonical_value=None,
                summary=definition.reason,
            ),
            primary_source=DiagnosticSource(
                kind="runtime_attempt",
                owner="submit_endpoint",
                path=None,
                span=None,
            ),
            related_sources=(
                DiagnosticSource(
                    kind="runtime_attempt",
                    owner="runtime_step",
                    path=None,
                    span=None,
                ),
                DiagnosticSource(
                    kind="runtime_attempt",
                    owner="phase_lifecycle",
                    path=None,
                    span=None,
                ),
            ),
        )
    return SubmitReceipt(
        status=status,
        attempt_scope_sha256=_digest("a"),
        client_request_id=request_id,
        submission_ordinal=1,
        configured_total=2,
        remaining_submissions=1,
        diagnostic=diagnostic,
    )


def test_cli_command_accepts_no_positional_or_locator_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        main(["provider-materialization-submit", "run-id"])
    assert "unrecognized arguments" in capsys.readouterr().err

    for forbidden in (
        "--run-id",
        "--step",
        "--ordinal",
        "--path",
        "--pane",
        "--endpoint",
    ):
        with pytest.raises(SystemExit):
            main(["provider-materialization-submit", forbidden, "value"])


def test_cli_sends_one_bounded_request_and_prints_canonical_receipt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def submit(*, request_id: str) -> SubmitReceipt:
        calls.append(request_id)
        return _receipt(request_id, status="accepted_closing")

    monkeypatch.setattr(
        provider_materialization,
        "submit_materialization",
        submit,
    )
    monkeypatch.chdir(tmp_path)
    before = tuple(tmp_path.iterdir())

    assert main(["provider-materialization-submit"]) == 0

    assert len(calls) == 1
    assert 0 < len(calls[0].encode("ascii")) <= MAX_CLIENT_REQUEST_ID_BYTES
    output = capsys.readouterr().out
    assert output.endswith("\n")
    assert json.loads(output)["status"] == "accepted_closing"
    assert tuple(tmp_path.iterdir()) == before


def test_cli_returns_failure_for_closed_failed_receipt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        provider_materialization,
        "submit_materialization",
        lambda *, request_id: _receipt(request_id, status="failed"),
    )

    assert main(["provider-materialization-submit"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


def test_cli_protocol_error_is_stderr_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(*, request_id: str) -> SubmitReceipt:
        del request_id
        raise ValueError("binding unavailable")

    monkeypatch.setattr(
        provider_materialization,
        "submit_materialization",
        fail,
    )

    assert main(["provider-materialization-submit"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "binding unavailable" in captured.err


def test_private_cli_imports_no_state_ledger_adapter_or_coordinator_owner(
) -> None:
    tree = ast.parse(inspect.getsource(provider_materialization))
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert not any(
        forbidden in module
        for module in imported
        for forbidden in (
            ".ledger",
            ".coordinator",
            "state",
            "interactive_terminal",
        )
    )
