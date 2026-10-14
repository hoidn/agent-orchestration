from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from orchestrator.workflow.run_ref import wire
from tests.workflow_evaluated_run_ref_helpers import (
    _build_path_fixture,
    _path_request,
)

from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
)


_CHILD_MODULE = "orchestrator.workflow.run_ref.child"


def _child_module():
    spec = importlib.util.find_spec(_CHILD_MODULE)
    assert spec is not None, "the private run-ref child command is missing"
    return importlib.import_module(_CHILD_MODULE)


def _child_crash_control(
    clone_root: Path,
    *,
    boundary: str,
) -> tuple[dict[str, object], Path]:
    progress_path = (
        clone_root.parent / "run-ref-child-boundary-progress.json"
    ).resolve()
    return (
        {
            "schema_version": "run_ref_child_test_control.v1",
            "boundary": boundary,
            "progress_path": progress_path.as_posix(),
        },
        progress_path,
    )


def _invoke_path(
    payload: dict[str, object],
    request_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    request_path.write_bytes(canonical_json_bytes(payload))
    return_code = _child_module().main(
        ["--path-request", request_path.as_posix()]
    )
    captured = capsys.readouterr()
    return return_code, captured.out, captured.err


def _assert_canonical_document(stream: str) -> dict[str, Any]:
    assert stream.count("\n") == 1
    document = json.loads(stream)
    assert stream.encode("utf-8") == canonical_json_bytes(document) + b"\n"
    return document


@pytest.mark.parametrize(
    "tamper",
    ("materialized_source", "static_config", "step_config_digest", "extra"),
)
def test_mode2_child_rejects_tampered_or_open_request_before_compile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tamper: str,
) -> None:
    child = _child_module()
    fixture = _build_path_fixture(tmp_path, case=f"tamper-{tamper}")
    payload = _path_request(fixture)
    if tamper == "materialized_source":
        materialized = dict(payload["materialized_source"])
        materialized["verified_git_tree"] = "git-tree:" + "f" * 40
        payload["materialized_source"] = materialized
    elif tamper == "static_config":
        payload["run_ref_static_config_base64"] = "not-canonical-base64!"
    elif tamper == "step_config_digest":
        payload["expected_step_config_digest"] = "sha256:" + "0" * 64
    else:
        payload["unexpected"] = "open-envelope"

    def reject_compile(*_args, **_kwargs):
        pytest.fail("invalid path requests must reject before compilation")

    monkeypatch.setattr(child, "_admit_path_request", reject_compile)

    return_code, stdout, stderr = _invoke_path(
        payload,
        fixture.request_path,
        capsys,
    )

    assert return_code != 0
    assert stdout == ""
    diagnostic = _assert_canonical_document(stderr)
    assert diagnostic == {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "run_ref_child_launch_failed",
        "reason": "request_invalid",
    }
    assert not (fixture.state_dir / fixture.child_run_id).exists()


def test_mode2_compile_refusal_preserves_structured_machine_diagnostic(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = _build_path_fixture(
        tmp_path,
        body="missing_name",
        case="compile-refusal",
    )
    payload = _path_request(fixture)

    return_code, stdout, stderr = _invoke_path(
        payload,
        fixture.request_path,
        capsys,
    )

    assert return_code != 0
    assert stdout == ""
    diagnostic = _assert_canonical_document(stderr)
    assert diagnostic["schema_version"] == "run_ref_child_diagnostic.v1"
    assert diagnostic["status"] == "rejected"
    assert diagnostic["code"] == "trial_program_compile_rejected"
    assert diagnostic["reason"] == "path_compile_rejected"
    assert diagnostic["secondary_causes"] == ["name_unknown"]
    assert diagnostic["rejected_value"] == {
        "program": fixture.step_config.run_ref.program.record,
        "compile_diagnostics": diagnostic["compile_diagnostics"],
    }
    assert diagnostic["compile_diagnostics"]["status"] == "rejected"
    assert [
        row["code"] for row in diagnostic["compile_diagnostics"]["diagnostics"]
    ] == ["name_unknown"]
    assert not (fixture.state_dir / fixture.child_run_id).exists()


def test_mode2_structural_refusal_without_compile_document_has_closed_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.workflow.run_ref.path_compile import (
        RunRefPathCompileRefusal,
    )

    child = _child_module()
    fixture = _build_path_fixture(tmp_path, case="structural-refusal")
    payload = _path_request(fixture)
    rejected_value = fixture.step_config.run_ref.program.record

    def refuse(*_args, **_kwargs):
        raise RunRefPathCompileRefusal(
            "trial_program_missing",
            rejected_value,
            secondary_causes=("program_missing",),
        )

    monkeypatch.setattr(child, "_admit_path_request", refuse)

    return_code, stdout, stderr = _invoke_path(
        payload,
        fixture.request_path,
        capsys,
    )

    assert return_code == 2
    assert stdout == ""
    assert _assert_canonical_document(stderr) == {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "trial_program_missing",
        "reason": "path_compile_rejected",
        "rejected_value": rejected_value,
        "secondary_causes": ["program_missing"],
    }


def test_mode2_malformed_structural_failure_authority_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.workflow.run_ref.path_compile import (
        RunRefPathCompileRefusal,
    )

    child = _child_module()
    fixture = _build_path_fixture(tmp_path, case="malformed-authority")
    payload = _path_request(fixture)
    malformed_diagnostics = {
        "schema_version": "workflow_lisp_compile_diagnostics.v1",
        "status": "rejected",
        "diagnostics": [],
        "unexpected": "open-machine-authority",
    }

    def refuse(*_args, **_kwargs):
        raise RunRefPathCompileRefusal(
            "trial_program_compile_rejected",
            {
                "program": fixture.step_config.run_ref.program.record,
                "compile_diagnostics": malformed_diagnostics,
            },
            secondary_causes=("name_unknown",),
            compile_diagnostics_document=malformed_diagnostics,
        )

    monkeypatch.setattr(child, "_admit_path_request", refuse)

    return_code, stdout, stderr = _invoke_path(
        payload,
        fixture.request_path,
        capsys,
    )

    assert return_code == 1
    assert stdout == ""
    assert _assert_canonical_document(stderr) == {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "run_ref_child_result_invalid",
        "reason": "child_failure_authority_invalid",
    }


def test_child_diagnostic_validator_is_pure_and_rejects_open_runtime_details() -> None:
    source = {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "run_ref_child_launch_failed",
        "reason": "request_invalid",
    }

    validated = wire.validate_child_diagnostic_document(source)
    source["code"] = "changed-after-validation"

    assert validated == {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "run_ref_child_launch_failed",
        "reason": "request_invalid",
    }
    with pytest.raises(ValueError, match="runtime child diagnostic authority"):
        wire.validate_child_diagnostic_document(
            {**validated, "unexpected": "open-machine-authority"}
        )


def test_parent_launched_mode2_child_crashes_after_actual_compile_boundary(
    tmp_path: Path,
) -> None:
    fixture = _build_path_fixture(tmp_path, case="crash-after-compile")
    payload = _path_request(fixture)
    control, progress_path = _child_crash_control(
        fixture.materialized_source.workspace_path,
        boundary="mode_2_compile",
    )
    payload["test_control"] = control
    fixture.request_path.write_bytes(canonical_json_bytes(payload))

    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            _CHILD_MODULE,
            "--path-request",
            fixture.request_path.as_posix(),
        ),
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 86
    assert completed.stdout == b""
    assert completed.stderr == b""
    assert json.loads(progress_path.read_text(encoding="utf-8")) == {
        "schema_version": "run_ref_child_boundary_progress.v1",
        "boundary": "mode_2_compile",
    }
    assert not (fixture.state_dir / fixture.child_run_id).exists()
