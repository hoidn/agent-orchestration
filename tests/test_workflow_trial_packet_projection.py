from __future__ import annotations

import base64
import json
from pathlib import Path
import subprocess

import pytest

from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow.trial.checks import run_trial_checks
from orchestrator.workflow.trial.packets import (
    build_trial_evaluation_packet,
    TrialPacketError,
)


def _check_record_with_output(
    tmp_path: Path,
    *,
    stdout: bytes = b"",
    stderr: bytes = b"",
) -> dict[str, object]:
    [result] = run_trial_checks(
        (
            {
                "check_id": "correctness",
                "command": ["probe", "correctness"],
                "authority": "correctness",
                "required": True,
                "timeout_ms": 1_000,
            },
        ),
        cwd=tmp_path.resolve(),
        evidence_frozen_digest="sha256:" + "a" * 64,
        max_output_bytes=1_024,
        runner=lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv,
            0,
            stdout=stdout,
            stderr=stderr,
        ),
    )
    return result.record


def _check_packet_arguments(tmp_path: Path) -> dict[str, object]:
    return {
        "opaque_label": "opaque-" + "e" * 64,
        "observation_include": ("check_results",),
        "observations": {
            "check_results": [
                _check_record_with_output(tmp_path, stdout=b"neutral output\n")
            ]
        },
        "sealed_identity_values": ("direct",),
        "max_item_bytes": 4_096,
        "max_packet_bytes": 8_192,
    }


def test_blinding_identity_match_uses_stable_token_boundaries() -> None:
    arguments = {
        "opaque_label": "opaque-" + "d" * 64,
        "observation_include": ("validated_result",),
        "sealed_identity_values": ("direct",),
        "max_item_bytes": 4_096,
        "max_packet_bytes": 8_192,
    }

    packet = build_trial_evaluation_packet(
        **arguments,
        observations={"validated_result": {"kind": "directory"}},
    )
    assert packet["items"][0]["value"] == {"kind": "directory"}

    for leaked in (
        "direct",
        "direct_output",
        {"direct_output": "opaque"},
        "selected/direct/result",
    ):
        with pytest.raises(TrialPacketError) as exc_info:
            build_trial_evaluation_packet(
                **arguments,
                observations={"validated_result": leaked},
            )
        assert exc_info.value.code == "trial_blinding_policy_invalid"
        assert exc_info.value.rejected_value == "direct"


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "arm_id",
        "base",
        "treatment",
        "treatment_id",
        "run_ref_source_locator",
        "source_locator",
        "normalized_locator",
        "resolved_commit_sha",
        "authored_setup_identity",
        "program_selector",
        "workflow_source",
        "workflow_source_text",
        "workflow_filename",
        "proposer_id",
        "proposer_lineage",
        "candidate_id",
        "candidate_lineage",
        "child_completion_order",
        "evaluator_completion_order",
        "completion_order",
        "run_log",
        "run_logs",
        "prior_score",
        "previous_score",
        "provider_identity",
        "provider_model",
        "evaluator_provider",
        "evaluator_model",
        "model_identity",
    ),
)
def test_every_forbidden_identity_field_rejects_with_exact_diagnostic(
    forbidden_key: str,
) -> None:
    with pytest.raises(TrialPacketError) as exc_info:
        build_trial_evaluation_packet(
            opaque_label="opaque-" + "f" * 64,
            observation_include=("validated_result",),
            observations={
                "validated_result": {
                    "nested": [{forbidden_key: "otherwise-neutral"}],
                }
            },
            sealed_identity_values=("sealed-treatment",),
            max_item_bytes=4_096,
            max_packet_bytes=8_192,
        )

    assert exc_info.value.code == "trial_blinding_policy_invalid"
    assert exc_info.value.rejected_value == forbidden_key


def test_declared_artifact_exempts_only_relpath_not_name_or_runtime_metadata() -> None:
    arguments = {
        "opaque_label": "opaque-" + "f" * 64,
        "observation_include": ("declared_artifacts",),
        "sealed_identity_values": ("direct",),
        "max_item_bytes": 4096,
        "max_packet_bytes": 8192,
    }
    permitted = {
        "name": "report",
        "path": "artifacts/direct/result.md",
        "kind": "file",
        "mode": 420,
        "size": 1,
        "sha256": "sha256:" + "1" * 64,
        "link_target": None,
    }

    packet = build_trial_evaluation_packet(
        **arguments,
        observations={"declared_artifacts": [permitted]},
    )
    assert packet["items"][0]["value"][0]["path"] == (
        "artifacts/direct/result.md"
    )

    for artifact in (
        {**permitted, "name": "direct-report"},
        {**permitted, "link_target": ".orchestrate/runs/child"},
    ):
        try:
            build_trial_evaluation_packet(
                **arguments,
                observations={"declared_artifacts": [artifact]},
            )
        except TrialPacketError as exc:
            assert exc.code == "trial_blinding_policy_invalid"
        else:
            raise AssertionError("non-relpath artifact identity was accepted")


def test_check_output_blinding_uses_identity_token_boundaries(
    tmp_path: Path,
) -> None:
    arguments = _check_packet_arguments(tmp_path)

    arguments["observations"] = {
        "check_results": [
            _check_record_with_output(
                tmp_path,
                stdout=b"kind=directory\n\xff",
            )
        ]
    }
    packet = build_trial_evaluation_packet(**arguments)
    assert packet["items"][0]["id"] == "check_results"

    for leaked in (b"direct", b"direct_output", b"selected/direct/result"):
        arguments["observations"] = {
            "check_results": [
                _check_record_with_output(tmp_path, stdout=leaked)
            ]
        }
        with pytest.raises(TrialPacketError) as exc_info:
            build_trial_evaluation_packet(**arguments)
        assert exc_info.value.code == "trial_blinding_policy_invalid"
        assert exc_info.value.rejected_value == "direct"


def test_check_output_blinding_rejects_encoded_runtime_state_path(
    tmp_path: Path,
) -> None:
    arguments = _check_packet_arguments(tmp_path)
    arguments["observations"] = {
        "check_results": [
            _check_record_with_output(
                tmp_path,
                stderr=b"read .orchestrate/runs/child/state.json\n",
            )
        ]
    }

    with pytest.raises(TrialPacketError) as exc_info:
        build_trial_evaluation_packet(**arguments)

    assert exc_info.value.code == "trial_blinding_policy_invalid"


def test_check_output_blinding_accepts_neutral_bytes_without_decoding_other_fields(
    tmp_path: Path,
) -> None:
    arguments = _check_packet_arguments(tmp_path)
    encoded_identity = base64.b64encode(b"direct").decode("ascii")
    arguments["observation_include"] = ("validated_result", "check_results")
    arguments["observations"] = {
        "validated_result": {"opaque_blob": encoded_identity},
        **arguments["observations"],
    }

    packet = build_trial_evaluation_packet(**arguments)

    assert packet["items"][0]["value"] == {"opaque_blob": encoded_identity}
    assert packet["items"][1]["id"] == "check_results"


def test_check_output_blinding_rejects_malformed_base64_schema(
    tmp_path: Path,
) -> None:
    arguments = _check_packet_arguments(tmp_path)
    record = arguments["observations"]["check_results"][0]
    output = json.loads(record["output_bytes"])
    output["stdout_base64"] = "not base64!"
    record["output_bytes"] = canonical_json_bytes(output).decode("utf-8")

    with pytest.raises(TrialPacketError) as exc_info:
        build_trial_evaluation_packet(**arguments)

    assert exc_info.value.code == "trial_packet_policy_invalid"
