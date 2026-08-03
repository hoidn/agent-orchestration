from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

import orchestrator.workflow.trial.adjudication as adjudication_module
from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.trial.checks import ensure_trial_checks_frozen
from orchestrator.workflow.trial.evaluation import ensure_trial_evidence_freeze
from orchestrator.workflow.trial.ledger import (
    append_trial_packets_freeze,
    load_trial_event_ledger,
)
from orchestrator.workflow.trial.packet_artifacts import (
    TrialPacketArtifactError,
    publish_trial_packet_artifacts,
)
from orchestrator.workflow.trial.packets import build_trial_cell_evaluation_packet
from tests.test_workflow_trial_adjudication import (
    _Executor,
    _blinded_cell_harnesses,
    _dependencies,
)
from tests.test_workflow_trial_runtime import _execute, _runtime_fixture


def _artifact_root(workspace: Path, request_digest: str) -> Path:
    return (
        workspace
        / "artifacts"
        / "trials"
        / request_digest.removeprefix("sha256:")
        / "packets"
    )


def _frozen_packet_fixture(tmp_path: Path) -> dict[str, object]:
    fixture = _runtime_fixture(tmp_path)
    execution = _execute(fixture, _blinded_cell_harnesses())
    request = fixture["request"]
    ensure_trial_evidence_freeze(execution.ledger_path)
    ensure_trial_checks_frozen(
        execution.ledger_path,
        request=request,
        runner=lambda *_args, **_kwargs: pytest.fail(
            "the fixture authors no deterministic checks"
        ),
    )
    packets = tuple(
        build_trial_cell_evaluation_packet(
            request,
            outcome,
            opaque_label_binding=binding,
            trusted_check_results=(),
        )
        for outcome, binding in zip(
            execution.outcomes,
            fixture["sealed"].bindings,
            strict=True,
        )
    )
    ledger = load_trial_event_ledger(execution.ledger_path)
    append_trial_packets_freeze(
        execution.ledger_path,
        expected_head_digest=ledger.rows[-1].row_digest,
        cell_packets=[
            {
                "cell": cell.record,
                "opaque_label": binding.opaque_label,
                "packet_digest": canonical_sha256(packet),
            }
            for cell, binding, packet in zip(
                request.cell_domain,
                fixture["sealed"].bindings,
                packets,
                strict=True,
            )
        ],
    )
    return {**fixture, "execution": execution, "packets": packets}


def _publish(case: dict[str, object], packets=None) -> dict[str, object]:
    execution = case["execution"]
    return publish_trial_packet_artifacts(
        parent_workspace=case["parent_workspace"],
        request=case["request"],
        sealed_opaque_labels=case["sealed"],
        packets=case["packets"] if packets is None else packets,
        trial_event_ledger_path=execution.ledger_path,
    )


def _rewrite_ledger(path: Path, mutate) -> None:
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    mutate(rows)
    previous = None
    encoded = []
    for sequence, row in enumerate(rows, start=1):
        row["sequence"] = sequence
        row["previous_row_digest"] = previous
        preimage = dict(row)
        preimage.pop("row_digest")
        row["row_digest"] = canonical_sha256(preimage)
        previous = row["row_digest"]
        encoded.append(canonical_json_bytes(row) + b"\n")
    path.write_bytes(b"".join(encoded))


def test_packet_artifacts_are_published_before_the_first_scorer_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    execution = _execute(fixture, _blinded_cell_harnesses())
    dependencies, _ = _dependencies(_Executor())
    original = adjudication_module.evaluate_trial_packets
    observed: list[dict[str, object]] = []

    def assert_artifacts_then_score(**kwargs):
        request = fixture["request"]
        root = _artifact_root(fixture["parent_workspace"], request.digest)
        index_path = root / "index.json"
        assert index_path.is_file()
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index_path.read_bytes() == canonical_json_bytes(index) + b"\n"
        assert index["trial_request_digest"] == request.digest

        ledger = load_trial_event_ledger(execution.ledger_path)
        packets_frozen = next(
            row for row in ledger.rows if row.kind == "packets_frozen"
        )
        assert index["packets_frozen_row_digest"] == packets_frozen.row_digest
        assert index["packet_set_digest"] == packets_frozen.payload[
            "packet_set_digest"
        ]
        assert len(index["packets"]) == len(request.cell_domain)
        for row in index["packets"]:
            packet_path = fixture["parent_workspace"] / row["packet_relpath"]
            assert packet_path.is_file()
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            assert packet_path.read_bytes() == canonical_json_bytes(packet) + b"\n"
        assert kwargs["packets"] == tuple(
            json.loads(
                (fixture["parent_workspace"] / row["packet_relpath"]).read_text(
                    encoding="utf-8"
                )
            )
            for row in index["packets"]
        )
        observed.append(index)
        return original(**kwargs)

    monkeypatch.setattr(
        adjudication_module,
        "evaluate_trial_packets",
        assert_artifacts_then_score,
    )

    adjudication_module.evaluate_trial_execution(
        fixture["request"],
        execution,
        parent_workspace=fixture["parent_workspace"],
        dependencies=dependencies,
    )

    assert len(observed) == 1


def test_packet_artifact_index_is_closed_ordered_and_exact_existing_is_idempotent(
    tmp_path: Path,
) -> None:
    case = _frozen_packet_fixture(tmp_path)
    first = _publish(case)
    root = _artifact_root(case["parent_workspace"], case["request"].digest)
    paths = sorted(path for path in root.iterdir() if path.is_file())
    before = {path: (path.stat().st_ino, path.read_bytes()) for path in paths}

    second = _publish(case)

    assert second == first
    assert set(first) == {
        "schema_version",
        "trial_request_digest",
        "header_row_digest",
        "evidence_frozen_row_digest",
        "checks_frozen_row_digest",
        "packets_frozen_row_digest",
        "sealed_opaque_label_map_digest",
        "packet_set_digest",
        "packets",
    }
    assert [row["cell"] for row in first["packets"]] == [
        cell.record for cell in case["request"].cell_domain
    ]
    assert {path: (path.stat().st_ino, path.read_bytes()) for path in paths} == before


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "duplicate", "label_swap", "malformed", "digest_drift"],
)
def test_packet_artifact_publication_rejects_every_packet_domain_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    case = _frozen_packet_fixture(tmp_path)
    packets = list(deepcopy(case["packets"]))
    if mutation == "missing":
        packets.pop()
    elif mutation == "extra":
        packets.append(deepcopy(packets[0]))
    elif mutation == "duplicate":
        packets[1] = deepcopy(packets[0])
    elif mutation == "label_swap":
        packets.reverse()
    elif mutation == "malformed":
        packets[0]["unexpected"] = True
    else:
        packets[0]["items"][0]["value"] = "digest-drift"

    with pytest.raises(ValueError):
        _publish(case, packets=tuple(packets))


def test_invalid_packet_set_is_rejected_before_any_artifact_is_published(
    tmp_path: Path,
) -> None:
    case = _frozen_packet_fixture(tmp_path)
    packets = list(deepcopy(case["packets"]))
    packets[1] = deepcopy(packets[0])

    with pytest.raises(ValueError):
        _publish(case, packets=tuple(packets))

    assert not os.path.lexists(case["parent_workspace"] / "artifacts")


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_packet_artifact_publication_rejects_missing_or_duplicate_freeze(
    tmp_path: Path,
    mutation: str,
) -> None:
    case = _frozen_packet_fixture(tmp_path)
    ledger_path = case["execution"].ledger_path

    def change(rows):
        [packet_row] = [row for row in rows if row["kind"] == "packets_frozen"]
        if mutation == "missing":
            rows.remove(packet_row)
        else:
            rows.append(deepcopy(packet_row))

    _rewrite_ledger(ledger_path, change)

    with pytest.raises(ValueError):
        _publish(case)


@pytest.mark.parametrize(
    "collision",
    ["packet_overwrite", "packet_symlink", "packet_directory", "malformed_index"],
)
def test_packet_artifact_publication_rejects_aliased_nonregular_or_changed_files(
    tmp_path: Path,
    collision: str,
) -> None:
    case = _frozen_packet_fixture(tmp_path)
    index = _publish(case)
    root = _artifact_root(case["parent_workspace"], case["request"].digest)
    packet_path = case["parent_workspace"] / index["packets"][0]["packet_relpath"]
    if collision == "packet_overwrite":
        packet_path.write_bytes(b"{}\n")
    elif collision == "packet_symlink":
        packet_path.unlink()
        packet_path.symlink_to(root / "index.json")
    elif collision == "packet_directory":
        packet_path.unlink()
        packet_path.mkdir()
    else:
        (root / "index.json").write_bytes(b"{}\n")

    with pytest.raises(TrialPacketArtifactError):
        _publish(case)


def test_packet_artifact_publication_rejects_a_symlinked_directory_component(
    tmp_path: Path,
) -> None:
    case = _frozen_packet_fixture(tmp_path)
    workspace = case["parent_workspace"]
    outside = (tmp_path / "outside-artifacts").resolve()
    outside.mkdir()
    artifacts = workspace / "artifacts"
    assert not os.path.lexists(artifacts)
    artifacts.symlink_to(outside, target_is_directory=True)

    with pytest.raises(TrialPacketArtifactError):
        _publish(case)

    assert list(outside.iterdir()) == []
