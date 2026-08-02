from __future__ import annotations

import base64
from dataclasses import replace
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from orchestrator.workflow.executable_ir import TrialStepConfig
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow.trial.config import (
    build_trial_runtime_request,
    build_trial_static_config,
)
from orchestrator.workflow.trial.contracts import (
    build_sealed_opaque_label_map,
    derive_trial_cell_effect_scopes,
)
from orchestrator.workflow.trial.checks import run_trial_checks
from orchestrator.workflow.trial.packets import (
    build_trial_cell_evaluation_packet,
    build_trial_evaluation_packet,
    TrialPacketError,
    validate_trial_cell_evaluation_packet,
)
from tests.test_workflow_trial_runtime import (
    _CellHarnesses,
    _execute,
    _runtime_fixture,
)


class _WritingHarness:
    def __init__(self, *, path: str, text: str) -> None:
        self._base = _CellHarnesses()
        self._path = path
        self._text = text

    def factory(self, cell, request):
        dependencies = self._base.factory(cell, request)
        launch = dependencies.launch_child

        def write_then_launch(child):
            target = child.workspace / self._path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self._text, encoding="utf-8")
            return launch(child)

        return replace(dependencies, launch_child=write_then_launch)


class _NeutralResultHarness:
    def __init__(self, value: str = "candidate output") -> None:
        self._base = _CellHarnesses()
        self._value = value

    def factory(self, cell, request):
        dependencies = self._base.factory(cell, request)
        launch = dependencies.launch_child

        def neutral_launch(child):
            result = launch(child)
            document = json.loads(result.stdout)
            outputs = {"__result__": self._value}
            document["workflow_outputs"] = outputs
            state_path = (
                child.workspace
                / ".orchestrate"
                / "runs"
                / child.child_run_id
                / "state.json"
            )
            state = json.loads(state_path.read_bytes())
            state["workflow_outputs"] = outputs
            state_path.write_bytes(canonical_json_bytes(state) + b"\n")
            return replace(
                result,
                stdout=canonical_json_bytes(document) + b"\n",
            )

        return replace(dependencies, launch_child=neutral_launch)


def _projection_fixture(
    tmp_path: Path,
    *,
    include: tuple[str, ...],
    diff_cap_bytes: int = 4096,
    checks: tuple[dict[str, object], ...] = (),
    resolved_inputs_by_arm: dict[str, dict[str, object]] | None = None,
):
    fixture = _runtime_fixture(tmp_path)
    current = fixture["request"]
    evaluation = current.static_config.evaluation
    evaluation.update(
        observation_include=list(include),
        diff_cap_bytes=diff_cap_bytes,
        checks=list(checks),
        max_item_bytes=65_536,
        max_packet_bytes=262_144,
    )
    static = build_trial_static_config(
        compiler_runtime_identity_digest=(
            current.static_config.compiler_runtime_identity_digest
        ),
        site_digest=current.static_config.site_digest,
        arms=current.static_config.arms,
        reps=current.static_config.reps,
        max_concurrency=current.static_config.max_concurrency,
        evaluation=evaluation,
        budget=current.static_config.budget,
        result_descriptor=current.static_config.result_descriptor,
        result_digest=current.static_config.result_digest,
    )
    step_config = TrialStepConfig(
        common=current.step_config.common,
        trial=static,
        arms=current.step_config.arms,
    )
    request = build_trial_runtime_request(
        step_config=step_config,
        visit=current.visit,
        resolved_inputs_by_arm=(
            current.resolved_inputs_by_arm
            if resolved_inputs_by_arm is None
            else resolved_inputs_by_arm
        ),
    )
    fixture["request"] = request
    fixture["scopes"] = derive_trial_cell_effect_scopes(
        request=request,
        parent_run_root=fixture["parent_run_root"],
        run_ref_root=fixture["run_ref_root"],
    )
    fixture["sealed"] = build_sealed_opaque_label_map(
        request.cell_domain,
        salt=b"task-eight-packet-projection" * 2,
    )
    return fixture


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


def test_completed_task7_outcome_projects_validated_result_under_exact_label(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    execution = _execute(fixture, _NeutralResultHarness())
    outcome = execution.outcomes[0]
    binding = fixture["sealed"].bindings[0]

    packet = build_trial_cell_evaluation_packet(
        fixture["request"],
        outcome,
        opaque_label_binding=binding,
        trusted_check_results=(),
    )

    assert packet == {
        "schema": "trial.evaluation_packet.v1",
        "evaluation_id": binding.opaque_label,
        "items": [
            {
                "id": "validated_result",
                "kind": "validated_result",
                "value": "candidate output",
            }
        ],
        "citable_item_ids": ["validated_result"],
    }


def test_completed_projection_strips_e1_base_and_uses_only_selected_real_facts(
    tmp_path: Path,
) -> None:
    include = (
        "task_spec",
        "validated_result",
        "workspace_delta",
        "check_results",
        "declared_artifacts",
        "failure_evidence",
    )
    fixture = _projection_fixture(tmp_path, include=include)
    execution = _execute(fixture, _NeutralResultHarness())
    outcome = execution.outcomes[0]

    packet = build_trial_cell_evaluation_packet(
        fixture["request"],
        outcome,
        opaque_label_binding=fixture["sealed"].bindings[0],
        trusted_check_results=(),
    )
    items = {item["id"]: item["value"] for item in packet["items"]}

    assert tuple(items) == (
        "task_spec",
        "validated_result",
        "workspace_delta",
        "check_results",
        "declared_artifacts",
    )
    assert items["task_spec"] == {"inputs": {"payload": "fixed"}}
    assert items["validated_result"] == outcome.envelope["value"]
    assert "base" not in items["workspace_delta"]
    assert set(items["workspace_delta"]) == {
        "changed_files",
        "deleted_files",
        "untracked_files",
        "normalized_diff",
        "declared_artifacts",
    }
    assert items["declared_artifacts"] == []
    assert items["check_results"] == []
    assert "failure_evidence" not in items


def test_failed_projection_contains_only_common_task_and_explicit_failure(
    tmp_path: Path,
) -> None:
    fixture = _projection_fixture(
        tmp_path,
        include=(
            "task_spec",
            "validated_result",
            "workspace_delta",
            "check_results",
            "declared_artifacts",
            "failure_evidence",
        ),
    )
    failed_cell = fixture["request"].cell_domain[0]
    execution = _execute(fixture, _CellHarnesses(failing={failed_cell}))
    outcome = execution.outcomes[0]

    packet = build_trial_cell_evaluation_packet(
        fixture["request"],
        outcome,
        opaque_label_binding=fixture["sealed"].bindings[0],
        trusted_check_results=(),
    )

    assert packet["items"] == [
        {
            "id": "task_spec",
            "kind": "task_spec",
            "value": {"inputs": {"payload": "fixed"}},
        },
        {
            "id": "failure_evidence",
            "kind": "failure_evidence",
            "value": outcome.failure.record,
        },
    ]


def test_workspace_diff_cap_is_utf8_safe_and_records_added_omission(
    tmp_path: Path,
) -> None:
    fixture = _projection_fixture(
        tmp_path,
        include=("workspace_delta",),
        # The generated diff is 40 bytes; byte 37 starts the two-byte `é`.
        diff_cap_bytes=38,
    )
    harness = _WritingHarness(path="x", text="é\n")
    execution = _execute(fixture, harness)
    original = execution.outcomes[0].envelope["workspace_delta"][
        "normalized_diff"
    ]
    assert len(original["entries"][0]["text"].encode("utf-8")) == 40

    packet = build_trial_cell_evaluation_packet(
        fixture["request"],
        execution.outcomes[0],
        opaque_label_binding=fixture["sealed"].bindings[0],
        trusted_check_results=(),
    )
    [item] = packet["items"]
    projected = item["value"]["normalized_diff"]
    [entry] = projected["entries"]

    assert len(entry["text"].encode("utf-8")) == 37
    assert entry["text"].endswith("+")
    assert entry["truncated"] is True
    assert entry["omitted_bytes"] == 3
    assert projected["truncated"] is True
    assert projected["omitted_bytes"] == 3
    assert projected["omitted_entries"] == 0


def test_only_normalized_paths_and_diff_text_exempt_identity_substrings(
    tmp_path: Path,
) -> None:
    fixture = _projection_fixture(
        tmp_path,
        include=("validated_result", "workspace_delta"),
        diff_cap_bytes=4096,
    )
    harness = _WritingHarness(
        path="direct.txt",
        text="file:///workspace scorer direct .orchestrate/runs/example\n",
    )
    execution = _execute(fixture, harness)
    outcome = execution.outcomes[0]

    try:
        build_trial_cell_evaluation_packet(
            fixture["request"],
            outcome,
            opaque_label_binding=fixture["sealed"].bindings[0],
            trusted_check_results=(),
        )
    except TrialPacketError as exc:
        assert exc.code == "trial_blinding_policy_invalid"
    else:
        raise AssertionError("validated-result treatment identity was accepted")

    neutral_envelope = deepcopy(outcome.envelope)
    neutral_envelope["value"] = "candidate output"
    packet = build_trial_cell_evaluation_packet(
        fixture["request"],
        replace(outcome, envelope=neutral_envelope),
        opaque_label_binding=fixture["sealed"].bindings[0],
        trusted_check_results=(),
    )
    items = {item["id"]: item["value"] for item in packet["items"]}

    assert items["validated_result"] == "candidate output"
    assert items["workspace_delta"]["untracked_files"][0]["path"] == (
        "direct.txt"
    )
    assert (
        "file:///workspace scorer direct .orchestrate/runs/example"
        in items["workspace_delta"]["normalized_diff"]["entries"][0]["text"]
    )


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


def test_check_output_blinding_rejects_encoded_sealed_identity(
    tmp_path: Path,
) -> None:
    arguments = _check_packet_arguments(tmp_path)
    arguments["observations"] = {
        "check_results": [
            _check_record_with_output(
                tmp_path,
                stdout=b"selected treatment: direct\n",
            )
        ]
    }

    with pytest.raises(TrialPacketError) as exc_info:
        build_trial_evaluation_packet(**arguments)

    assert exc_info.value.code == "trial_blinding_policy_invalid"


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


def test_completed_projection_accepts_only_exact_config_bound_check_results(
    tmp_path: Path,
) -> None:
    check = {
        "check_id": "correctness",
        "command": ["python", "-c", "print('ok')"],
        "authority": "correctness",
        "required": True,
        "timeout_ms": 1_000,
    }
    fixture = _projection_fixture(
        tmp_path,
        include=("check_results",),
        checks=(check,),
    )
    execution = _execute(fixture, _NeutralResultHarness())
    outcome = execution.outcomes[0]
    results = run_trial_checks(
        fixture["request"].static_config.evaluation["checks"],
        cwd=outcome.settled_result.workspace_path,
        evidence_frozen_digest="sha256:" + "a" * 64,
        max_output_bytes=1024,
    )

    packet = build_trial_cell_evaluation_packet(
        fixture["request"],
        outcome,
        opaque_label_binding=fixture["sealed"].bindings[0],
        trusted_check_results=results,
    )

    assert packet["items"] == [
        {
            "id": "check_results",
            "kind": "check_results",
            "value": [results[0].record],
        }
    ]

    for rejected in ((), (replace(results[0], check_id="other"),)):
        try:
            build_trial_cell_evaluation_packet(
                fixture["request"],
                outcome,
                opaque_label_binding=fixture["sealed"].bindings[0],
                trusted_check_results=rejected,
            )
        except TrialPacketError as exc:
            assert exc.code == "trial_packet_policy_invalid"
        else:
            raise AssertionError("unbound check evidence was accepted")


def test_production_revalidation_enforces_binding_schema_exclusions_and_caps(
    tmp_path: Path,
) -> None:
    fixture = _projection_fixture(
        tmp_path,
        include=("validated_result", "workspace_delta"),
    )
    execution = _execute(fixture, _NeutralResultHarness())
    outcome = execution.outcomes[0]
    binding = fixture["sealed"].bindings[0]
    packet = build_trial_cell_evaluation_packet(
        fixture["request"],
        outcome,
        opaque_label_binding=binding,
        trusted_check_results=(),
    )

    assert validate_trial_cell_evaluation_packet(
        packet,
        request=fixture["request"],
        cell=outcome.cell,
        opaque_label_binding=binding,
    ) == packet

    excluded = deepcopy(packet)
    excluded["items"][0]["value"] = {
        "answer": True,
        "provider_model": "forged",
    }
    state_path = deepcopy(packet)
    state_path["items"][1]["value"]["changed_files"] = [
        {"path": ".orchestrate/state.json"}
    ]
    oversized = deepcopy(packet)
    oversized["items"][0]["value"] = "x" * 70_000
    diff_over_cap = deepcopy(packet)
    diff_over_cap["items"][1]["value"]["normalized_diff"] = {
        "entries": [
            {
                "path": "x",
                "text": "x" * 5_000,
                "truncated": False,
                "omitted_bytes": 0,
            }
        ],
        "catalog_digest": "sha256:" + "a" * 64,
        "truncated": False,
        "omitted_bytes": 0,
        "omitted_entries": 0,
    }
    artifact_name = deepcopy(packet)
    artifact_name["items"][1]["value"]["declared_artifacts"] = [
        {
            "name": "direct-report",
            "path": "artifacts/direct/report.md",
            "kind": "file",
            "mode": 420,
            "size": 1,
            "sha256": "sha256:" + "1" * 64,
            "link_target": None,
        }
    ]
    artifact_runtime_metadata = deepcopy(packet)
    artifact_runtime_metadata["items"][1]["value"]["declared_artifacts"] = [
        {
            "name": "report",
            "path": "artifacts/report.md",
            "kind": "file",
            "mode": 420,
            "size": 1,
            "sha256": "sha256:" + "1" * 64,
            "link_target": ".orchestrate/runs/child",
        }
    ]
    reordered = deepcopy(packet)
    reordered["items"] = list(reversed(reordered["items"]))
    reordered["citable_item_ids"] = list(
        reversed(reordered["citable_item_ids"])
    )

    for tampered in (
        excluded,
        state_path,
        oversized,
        diff_over_cap,
        artifact_name,
        artifact_runtime_metadata,
        reordered,
    ):
        try:
            validate_trial_cell_evaluation_packet(
                tampered,
                request=fixture["request"],
                cell=outcome.cell,
                opaque_label_binding=binding,
            )
        except TrialPacketError:
            pass
        else:
            raise AssertionError("forged production packet was accepted")


def test_projection_rejects_completed_envelope_that_drifts_from_e1_binding(
    tmp_path: Path,
) -> None:
    fixture = _projection_fixture(
        tmp_path,
        include=("workspace_delta",),
    )
    execution = _execute(fixture, _CellHarnesses())
    outcome = execution.outcomes[0]
    envelope = deepcopy(outcome.envelope)
    envelope["workspace_delta"]["untracked_files"] = [
        {"path": "forged.txt"}
    ]

    try:
        build_trial_cell_evaluation_packet(
            fixture["request"],
            replace(outcome, envelope=envelope),
            opaque_label_binding=fixture["sealed"].bindings[0],
            trusted_check_results=(),
        )
    except TrialPacketError as exc:
        assert exc.code == "trial_packet_policy_invalid"
    else:
        raise AssertionError("E1 evidence drift was accepted")


def test_production_revalidation_rejects_tampered_encoded_check_output(
    tmp_path: Path,
) -> None:
    check = {
        "check_id": "correctness",
        "command": ["probe", "correctness"],
        "authority": "correctness",
        "required": True,
        "timeout_ms": 1_000,
    }
    fixture = _projection_fixture(
        tmp_path,
        include=("check_results",),
        checks=(check,),
    )
    execution = _execute(fixture, _NeutralResultHarness())
    outcome = execution.outcomes[0]
    [result] = run_trial_checks(
        fixture["request"].static_config.evaluation["checks"],
        cwd=outcome.settled_result.workspace_path,
        evidence_frozen_digest="sha256:" + "a" * 64,
        max_output_bytes=1_024,
        runner=lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv,
            0,
            stdout=b"neutral output\n",
            stderr=b"",
        ),
    )
    binding = fixture["sealed"].bindings[0]
    packet = build_trial_cell_evaluation_packet(
        fixture["request"],
        outcome,
        opaque_label_binding=binding,
        trusted_check_results=(result,),
    )
    tampered = deepcopy(packet)
    record = tampered["items"][0]["value"][0]
    output = json.loads(record["output_bytes"])
    payload = b"selected treatment: direct\n"
    output["stdout_base64"] = base64.b64encode(payload).decode("ascii")
    output["stdout_size_bytes"] = len(payload)
    record["output_bytes"] = canonical_json_bytes(output).decode("utf-8")

    with pytest.raises(TrialPacketError) as exc_info:
        validate_trial_cell_evaluation_packet(
            tampered,
            request=fixture["request"],
            cell=outcome.cell,
            opaque_label_binding=binding,
        )

    assert exc_info.value.code == "trial_blinding_policy_invalid"


def test_asymmetric_inputs_block_only_a_selected_task_spec(tmp_path: Path) -> None:
    asymmetric = {
        "direct": {"payload": "left"},
        "orc": {"payload": "right"},
    }
    result_only = _projection_fixture(
        tmp_path / "result-only",
        include=("validated_result",),
    )
    result_execution = _execute(result_only, _NeutralResultHarness())
    result_request = build_trial_runtime_request(
        step_config=result_only["request"].step_config,
        visit=result_only["request"].visit,
        resolved_inputs_by_arm=asymmetric,
    )

    packet = build_trial_cell_evaluation_packet(
        result_request,
        result_execution.outcomes[0],
        opaque_label_binding=result_only["sealed"].bindings[0],
        trusted_check_results=(),
    )
    assert packet["citable_item_ids"] == ["validated_result"]

    task_visible = _projection_fixture(
        tmp_path / "task-visible",
        include=("task_spec",),
    )
    task_execution = _execute(task_visible, _CellHarnesses())
    task_request = build_trial_runtime_request(
        step_config=task_visible["request"].step_config,
        visit=task_visible["request"].visit,
        resolved_inputs_by_arm=asymmetric,
    )
    try:
        build_trial_cell_evaluation_packet(
            task_request,
            task_execution.outcomes[0],
            opaque_label_binding=task_visible["sealed"].bindings[0],
            trusted_check_results=(),
        )
    except TrialPacketError as exc:
        assert exc.code == "trial_packet_policy_invalid"
    else:
        raise AssertionError("asymmetric task_spec was evaluator-visible")
