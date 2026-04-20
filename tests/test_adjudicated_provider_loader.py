from pathlib import Path

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executable_ir import AdjudicatedProviderStepConfig, ExecutableNodeKind
from orchestrator.workflow.surface_ast import SurfaceStepKind


def _write_yaml(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _base_workflow(**step_overrides: object) -> dict:
    step = {
        "name": "Draft",
        "id": "draft",
        "adjudicated_provider": {
            "candidates": [
                {"id": "fake_a", "provider": "fake"},
            ],
            "evaluator": {
                "provider": "fake",
                "input_file": "evaluator.md",
                "evidence_confidentiality": "same_trust_boundary",
            },
        },
        "input_file": "prompt.md",
        "expected_outputs": [
            {
                "name": "result",
                "path": "state/result.txt",
                "type": "string",
            }
        ],
    }
    step.update(step_overrides)
    return {
        "version": "2.11",
        "name": "adjudicated-loader",
        "providers": {
            "fake": {
                "command": ["python", "-c", "print('ok')"],
            },
        },
        "steps": [step],
    }


def _load(workspace: Path, payload: dict):
    return WorkflowLoader(workspace).load_bundle(_write_yaml(workspace / "workflow.yaml", payload))


def _validation_messages(workspace: Path, payload: dict) -> list[str]:
    with pytest.raises(WorkflowValidationError) as exc_info:
        _load(workspace, payload)
    return [str(error.message) for error in exc_info.value.errors]


def test_valid_minimal_adjudicated_step_lowers_to_ir(tmp_path: Path) -> None:
    (tmp_path / "prompt.md").write_text("Draft something useful.", encoding="utf-8")
    (tmp_path / "evaluator.md").write_text("Score it.", encoding="utf-8")

    bundle = _load(tmp_path, _base_workflow())

    step = bundle.surface.steps[0]
    assert step.kind is SurfaceStepKind.ADJUDICATED_PROVIDER
    assert step.adjudicated_provider["candidates"][0]["id"] == "fake_a"

    node = bundle.ir.nodes["root.draft"]
    assert node.kind is ExecutableNodeKind.ADJUDICATED_PROVIDER
    assert isinstance(node.execution_config, AdjudicatedProviderStepConfig)
    assert node.execution_config.adjudicated_provider["evaluator"]["provider"] == "fake"


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("2.10", "requires version '2.11'"),
        ("1.4", "requires version '2.11'"),
    ],
)
def test_adjudicated_provider_is_version_gated(tmp_path: Path, version: str, expected: str) -> None:
    workflow = _base_workflow()
    workflow["version"] = version

    messages = _validation_messages(tmp_path, workflow)

    assert any(expected in message for message in messages)


@pytest.mark.parametrize("field", ["provider", "command", "wait_for"])
def test_adjudicated_provider_is_exclusive_with_other_execution_forms(tmp_path: Path, field: str) -> None:
    workflow = _base_workflow()
    workflow["steps"][0][field] = "fake" if field == "provider" else ["echo", "nope"]

    messages = _validation_messages(tmp_path, workflow)

    assert any("mutually exclusive" in message for message in messages)


def test_adjudicated_provider_rejects_provider_session(tmp_path: Path) -> None:
    workflow = _base_workflow(provider_session={"mode": "fresh", "publish_artifact": "session"})

    messages = _validation_messages(tmp_path, workflow)

    assert any("provider_session is invalid with adjudicated_provider" in message for message in messages)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda step: step["adjudicated_provider"].update({"candidates": []}), "candidates must be a non-empty list"),
        (
            lambda step: step["adjudicated_provider"].update(
                {"candidates": [{"id": "dup", "provider": "fake"}, {"id": "dup", "provider": "fake"}]}
            ),
            "duplicate candidate id 'dup'",
        ),
        (
            lambda step: step["adjudicated_provider"].update(
                {"candidates": [{"id": "bad/path", "provider": "fake"}]}
            ),
            "candidate id must match",
        ),
        (
            lambda step: step["adjudicated_provider"].update(
                {"candidates": [{"id": "fake_a", "provider": "missing"}]}
            ),
            "unknown candidate provider 'missing'",
        ),
        (
            lambda step: step["adjudicated_provider"].update(
                {
                    "candidates": [
                        {
                            "id": "fake_a",
                            "provider": "fake",
                            "asset_file": "candidate.md",
                            "input_file": "candidate.md",
                        }
                    ]
                }
            ),
            "candidate prompt override may use only one",
        ),
        (
            lambda step: step["adjudicated_provider"].update(
                {"candidates": [{"id": "fake_a", "provider": "fake", "consumes": []}]}
            ),
            "candidate field 'consumes' is not supported",
        ),
        (lambda step: step.pop("input_file"), "must declare one base prompt source"),
    ],
)
def test_candidate_validation(tmp_path: Path, mutation, expected: str) -> None:
    workflow = _base_workflow()
    mutation(workflow["steps"][0])

    messages = _validation_messages(tmp_path, workflow)

    assert any(expected in message for message in messages)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda step: step["adjudicated_provider"]["evaluator"].pop("provider"), "evaluator.provider is required"),
        (
            lambda step: step["adjudicated_provider"]["evaluator"].update({"provider": "missing"}),
            "unknown evaluator provider 'missing'",
        ),
        (
            lambda step: step["adjudicated_provider"]["evaluator"].update(
                {"asset_file": "eval.md", "input_file": "eval.md"}
            ),
            "evaluator prompt source may use only one",
        ),
        (
            lambda step: step["adjudicated_provider"]["evaluator"].update(
                {"rubric_asset_file": "rubric.md", "rubric_input_file": "rubric.md"}
            ),
            "evaluator rubric source may use only one",
        ),
        (
            lambda step: step["adjudicated_provider"]["evaluator"].pop("evidence_confidentiality"),
            "evidence_confidentiality is required",
        ),
        (
            lambda step: step["adjudicated_provider"]["evaluator"].update({"evidence_confidentiality": "masked"}),
            "evidence_confidentiality must be same_trust_boundary",
        ),
        (
            lambda step: step["adjudicated_provider"]["evaluator"].update(
                {"evidence_limits": {"max_item_bytes": 10, "max_packet_bytes": 9}}
            ),
            "max_packet_bytes must be greater than or equal to max_item_bytes",
        ),
        (
            lambda step: step["adjudicated_provider"]["evaluator"].update(
                {"evidence_limits": {"max_item_bytes": "${inputs.limit}"}}
            ),
            "max_item_bytes must be a literal positive integer",
        ),
    ],
)
def test_evaluator_validation(tmp_path: Path, mutation, expected: str) -> None:
    workflow = _base_workflow()
    mutation(workflow["steps"][0])

    messages = _validation_messages(tmp_path, workflow)

    assert any(expected in message for message in messages)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda step: step.pop("expected_outputs"), "must declare exactly one of expected_outputs or output_bundle"),
        (
            lambda step: step.update({"output_bundle": {"path": "state/bundle.json", "fields": []}}),
            "must declare exactly one of expected_outputs or output_bundle",
        ),
        (lambda step: step.update({"output_file": "state/stdout.txt"}), "output_file is invalid"),
        (lambda step: step.update({"output_capture": "json"}), "output_capture is invalid"),
        (lambda step: step.update({"allow_parse_error": True}), "allow_parse_error is invalid"),
        (
            lambda step: step["adjudicated_provider"].update({"selection": {"tie_break": "score_then_name"}}),
            "selection.tie_break must be candidate_order",
        ),
        (
            lambda step: step["adjudicated_provider"].update(
                {"selection": {"require_score_for_single_candidate": "false"}}
            ),
            "selection.require_score_for_single_candidate must be boolean",
        ),
        (
            lambda step: step["adjudicated_provider"].update({"score_ledger_path": "state/scores.jsonl"}),
            "score_ledger_path must be under artifacts/",
        ),
        (
            lambda step: step["adjudicated_provider"].update({"score_ledger_path": "state/result.txt"}),
            "score_ledger_path must be under artifacts/",
        ),
        (
            lambda step: step["adjudicated_provider"].update({"score_ledger_path": "artifacts/../state/result.txt"}),
            "score_ledger_path must be under artifacts/",
        ),
        (
            lambda step: step["adjudicated_provider"].update({"score_ledger_path": "artifacts/scores.jsonl"})
            or step["expected_outputs"][0].update({"path": "${run.root}/result.txt"}),
            "must not depend on ${run.root}",
        ),
    ],
)
def test_step_level_adjudicated_validation(tmp_path: Path, mutation, expected: str) -> None:
    workflow = _base_workflow()
    mutation(workflow["steps"][0])

    messages = _validation_messages(tmp_path, workflow)

    assert any(expected in message for message in messages)
