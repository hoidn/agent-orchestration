from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "workflow_lisp"
    / "procedure_identity_retirement"
    / "valid_internal_retirement.json"
)


def _retirement_module():
    from orchestrator.workflow_lisp import procedure_identity_retirement

    return procedure_identity_retirement


def load_retirement_record(path: Path):
    return _retirement_module().load_retirement_record(path)


def validate_retirement_record(record: object, *, repo_root: Path):
    return _retirement_module().validate_retirement_record(record, repo_root=repo_root)


def scan_known_state_store(root: Path, *, retired_identities: set[str], query_version: str):
    return _retirement_module().scan_known_state_store(
        root,
        retired_identities=retired_identities,
        query_version=query_version,
    )


def _payload() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _write_payload(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "retirement.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _issues_for(tmp_path: Path, mutate: Callable[[dict[str, Any]], None]) -> set[str]:
    payload = _payload()
    mutate(payload)
    record = load_retirement_record(_write_payload(tmp_path, payload))
    return {issue.code for issue in validate_retirement_record(record, repo_root=REPO_ROOT).issues}


def test_valid_internal_retirement_record_is_frozen_complete_and_valid() -> None:
    record = load_retirement_record(FIXTURE)

    assert isinstance(record, _retirement_module().ProcedureIdentityRetirementRecord)
    assert record.schema == "workflow_lisp_procedure_identity_retirement.v1"
    assert record.migration["compatibility_class"] == "reviewed_internal_identity_retirement"
    assert record.runtime_directives == ()
    assert {row.identity_kind for row in record.identity_delta} == {
        "workflow",
        "call_frame",
        "executable_node",
        "step",
        "presentation_key",
        "program_point",
        "checkpoint",
        "state_allocation",
        "source_map_origin",
    }
    with pytest.raises(FrozenInstanceError):
        record.schema = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        record.migration["migration_id"] = "changed"  # type: ignore[index]

    result = validate_retirement_record(record, repo_root=REPO_ROOT)
    assert result.valid is True
    assert result.issues == ()


def test_fixture_owner_and_attestation_are_unmistakably_fictional_and_noncopyable() -> None:
    payload = _payload()

    assert "FICTIONAL TEST DATA" in payload["migration"]["test_fixture_notice"]
    store = payload["known_state_stores"][0]
    assert "Fictional Fixture Owner" in store["owner"]
    assert "NEVER COPY" in store["owner"]
    assert "FICTIONAL TEST ATTESTATION" in store["attestation"]
    assert "NEVER COPY" in store["attestation"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.__setitem__("unknown", True), "unknown fields"),
        (lambda payload: payload["callee"].__setitem__("unknown", True), "unknown fields"),
        (lambda payload: payload.__setitem__("known_state_stores", {}), "must be a list"),
        (lambda payload: payload["artifacts"][0].__setitem__("sha256", 42), "must be a string"),
        (lambda payload: payload["identity_delta"][0].__setitem__("old_disposition", 42), "must be"),
    ],
)
def test_parser_rejects_unknown_or_mistyped_structural_fields(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    payload = _payload()
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        load_retirement_record(_write_payload(tmp_path, payload))


@pytest.mark.parametrize(
    "field",
    ["exported", "registered_public_entry", "public", "route_promoted", "route_live"],
)
def test_public_exported_registered_promoted_or_live_callee_fails_closed(tmp_path: Path, field: str) -> None:
    issues = _issues_for(tmp_path, lambda payload: payload["callee"].__setitem__(field, True))

    assert "procedure_identity_retirement_public_boundary" in issues


def test_unowned_known_store_fails_closed(tmp_path: Path) -> None:
    issues = _issues_for(tmp_path, lambda payload: payload["known_state_stores"][0].pop("owner"))

    assert "procedure_identity_retirement_known_store_unowned" in issues


def test_missing_attestation_fails_closed(tmp_path: Path) -> None:
    issues = _issues_for(tmp_path, lambda payload: payload["known_state_stores"][0].pop("attestation"))

    assert "procedure_identity_retirement_attestation_missing" in issues


def test_external_store_absence_claim_fails_closed(tmp_path: Path) -> None:
    issues = _issues_for(tmp_path, lambda payload: payload.__setitem__("external_store_absence", "asserted_absent"))

    assert "procedure_identity_retirement_external_absence_asserted" in issues


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("nonterminal_run_count", "procedure_identity_retirement_supported_state_present"),
        ("call_frame_count", "procedure_identity_retirement_old_identity_consumer_present"),
        ("consumer_count", "procedure_identity_retirement_old_identity_consumer_present"),
    ],
)
def test_supported_nonterminal_or_old_identity_consumer_fails_closed(
    tmp_path: Path,
    field: str,
    code: str,
) -> None:
    issues = _issues_for(tmp_path, lambda payload: payload["known_state_stores"][0].__setitem__(field, 1))

    assert code in issues


def test_supporting_route_label_cannot_replace_substantive_wrapper_evidence(tmp_path: Path) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        payload["retained_wrapper_evidence"]["inventory_path"] = ""
        payload["retained_wrapper_evidence"]["reviewed_call_site"] = ""
        payload["supporting_labels"] = ["migration_evidence_only", "eligible"]

    issues = _issues_for(tmp_path, mutate)

    assert "procedure_identity_retirement_substantive_evidence_missing" in issues


@pytest.mark.parametrize(
    ("side", "expected"),
    [
        ("old", "procedure_identity_retirement_identity_duplicate_old"),
        ("new", "procedure_identity_retirement_identity_duplicate_new"),
    ],
)
def test_duplicate_identity_by_kind_is_rejected(tmp_path: Path, side: str, expected: str) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        row = copy.deepcopy(payload["identity_delta"][0])
        if side == "old":
            row["new_identity"] = "other-new"
            row["new_disposition"] = "new"
        else:
            row["old_identity"] = "other-old"
            row["old_disposition"] = "retired"
        payload["identity_delta"].append(row)

    assert expected in _issues_for(tmp_path, mutate)


@pytest.mark.parametrize(
    ("side", "disposition", "expected"),
    [
        ("old", "retired", "procedure_identity_retirement_identity_conflict_old"),
        ("new", "new", "procedure_identity_retirement_identity_conflict_new"),
    ],
)
def test_identity_cannot_be_both_preserved_and_retired_or_new(
    tmp_path: Path,
    side: str,
    disposition: str,
    expected: str,
) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        row = copy.deepcopy(payload["identity_delta"][0])
        row[f"{side}_disposition"] = disposition
        payload["identity_delta"].append(row)

    assert expected in _issues_for(tmp_path, mutate)


def test_identity_delta_requires_every_persisted_domain(tmp_path: Path) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        payload["identity_delta"] = [row for row in payload["identity_delta"] if row["identity_kind"] != "checkpoint"]

    issues = _issues_for(tmp_path, mutate)

    assert "procedure_identity_retirement_identity_domain_incomplete" in issues


def test_duplicate_artifact_key_without_explicit_count_fails_during_load(tmp_path: Path) -> None:
    payload = _payload()
    duplicate = copy.deepcopy(payload["artifact_multiset"]["old"][0])
    duplicate.pop("count")
    payload["artifact_multiset"]["old"].append(duplicate)

    with pytest.raises(ValueError, match="procedure_identity_retirement_artifact_count_missing"):
        load_retirement_record(_write_payload(tmp_path, payload))


def test_artifact_contract_is_compared_as_a_keyed_multiset(tmp_path: Path) -> None:
    issues = _issues_for(
        tmp_path,
        lambda payload: payload["artifact_multiset"]["new"][0].__setitem__("count", 2),
    )

    assert "procedure_identity_retirement_artifact_multiset_mismatch" in issues


def test_execution_order_is_compared_independently_from_artifact_multiset(tmp_path: Path) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        payload["execution_order"]["new"].reverse()
        for position, row in enumerate(payload["execution_order"]["new"]):
            row["position"] = position

    issues = _issues_for(tmp_path, mutate)

    assert "procedure_identity_retirement_execution_order_mismatch" in issues
    assert "procedure_identity_retirement_artifact_multiset_mismatch" not in issues


@pytest.mark.parametrize(
    "forbidden_key",
    ["runtime_remap", "remap_directive", "identity_aliases", "old_to_new_map"],
)
def test_nested_runtime_remap_vocabulary_is_rejected(tmp_path: Path, forbidden_key: str) -> None:
    payload = _payload()
    payload["checksum_evidence"]["callee"]["nested"] = {forbidden_key: {"old": "new"}}

    with pytest.raises(ValueError, match="procedure_identity_retirement_forbidden_runtime_key"):
        load_retirement_record(_write_payload(tmp_path, payload))


def test_runtime_directives_must_remain_empty(tmp_path: Path) -> None:
    issues = _issues_for(tmp_path, lambda payload: payload.__setitem__("runtime_directives", ["ignore-old-state"]))

    assert "procedure_identity_retirement_runtime_directive_present" in issues


def test_content_addressed_artifact_digest_is_verified(tmp_path: Path) -> None:
    issues = _issues_for(
        tmp_path,
        lambda payload: payload["artifacts"][0].__setitem__(
            "sha256", "sha256:" + "0" * 64
        ),
    )

    assert "procedure_identity_retirement_artifact_digest_mismatch" in issues


def test_old_and_new_production_artifact_roles_are_complete(tmp_path: Path) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        payload["artifacts"] = [
            artifact
            for artifact in payload["artifacts"]
            if not (artifact["side"] == "new" and artifact["role"] == "source_map")
        ]

    issues = _issues_for(tmp_path, mutate)

    assert "procedure_identity_retirement_artifact_role_missing" in issues


@pytest.mark.parametrize("block", ["clean_run", "interruption_resume"])
def test_new_id_clean_and_resume_evidence_are_required(tmp_path: Path, block: str) -> None:
    issues = _issues_for(tmp_path, lambda payload: payload["new_id_evidence"].pop(block))

    assert "procedure_identity_retirement_new_id_evidence_missing" in issues


@pytest.mark.parametrize("block", ["root", "callee"])
def test_root_and_callee_checksum_evidence_are_required(tmp_path: Path, block: str) -> None:
    issues = _issues_for(tmp_path, lambda payload: payload["checksum_evidence"].pop(block))

    assert "procedure_identity_retirement_checksum_evidence_missing" in issues


def test_known_state_store_scan_is_normalized_content_addressed_and_evidence_only(tmp_path: Path) -> None:
    store = tmp_path / "runs"
    (store / "terminal").mkdir(parents=True)
    (store / "active" / "call_frames" / "child").mkdir(parents=True)
    (store / "active" / "checkpoints").mkdir(parents=True)
    (store / "active" / "manifests").mkdir(parents=True)
    (store / "active" / "metadata").mkdir(parents=True)
    (store / "terminal" / "state.json").write_text(
        json.dumps({"status": "completed", "workflow_id": "retained-stack"}), encoding="utf-8"
    )
    (store / "active" / "state.json").write_text(
        json.dumps({"status": "running", "current_step": "old-step"}), encoding="utf-8"
    )
    (store / "active" / "call_frames" / "child" / "state.json").write_text(
        json.dumps({"call_frame_id": "old-frame", "caller_step_id": "old-step"}), encoding="utf-8"
    )
    (store / "active" / "checkpoints" / "index.json").write_text(
        json.dumps({"checkpoint_ids": ["old-checkpoint"]}), encoding="utf-8"
    )
    (store / "active" / "checkpoints" / "old-checkpoint.json").write_text(
        json.dumps({"checkpoint_id": "old-checkpoint", "step_id": "old-step"}), encoding="utf-8"
    )
    (store / "active" / "manifests" / "build_manifest.json").write_text(
        json.dumps({"retained_workflow_id": "retained-stack"}), encoding="utf-8"
    )
    (store / "active" / "metadata" / "identity_index.json").write_text(
        json.dumps({"presentation_key": "old-presentation"}), encoding="utf-8"
    )

    result = scan_known_state_store(
        store,
        retired_identities={"old-frame", "old-step", "old-checkpoint", "old-presentation"},
        query_version="procedure-identity-store-query.v1",
    )
    repeated = scan_known_state_store(
        store,
        retired_identities={"old-presentation", "old-checkpoint", "old-step", "old-frame"},
        query_version="procedure-identity-store-query.v1",
    )

    assert result == repeated
    assert result["terminal_run_count"] == 1
    assert result["nonterminal_run_count"] == 1
    assert result["call_frame_count"] == 1
    assert result["checkpoint_index_count"] == 1
    assert result["checkpoint_record_count"] == 1
    assert result["retained_manifest_count"] == 1
    assert result["identity_metadata_count"] == 1
    assert result["consumer_count"] >= 4
    assert result["normalized_scan_digest"].startswith("sha256:")
    assert len(result["normalized_scan_digest"]) == len("sha256:") + 64
    assert "owner" not in result
    assert "attestation" not in result
    assert "external_store_absence" not in result
    assert tuple(result["matches"]) == tuple(sorted(result["matches"], key=lambda row: json.dumps(row, sort_keys=True)))


def test_known_store_scan_digest_changes_when_supported_identity_evidence_changes(tmp_path: Path) -> None:
    store = tmp_path / "runs"
    (store / "run").mkdir(parents=True)
    state = store / "run" / "state.json"
    state.write_text(json.dumps({"status": "completed", "step_id": "old-step"}), encoding="utf-8")
    before = scan_known_state_store(store, retired_identities={"old-step"}, query_version="query.v1")
    state.write_text(json.dumps({"status": "completed", "step_id": "different-step"}), encoding="utf-8")
    after = scan_known_state_store(store, retired_identities={"old-step"}, query_version="query.v1")

    assert before["normalized_scan_digest"] != after["normalized_scan_digest"]
    assert before["consumer_count"] == 1
    assert after["consumer_count"] == 0


@pytest.mark.parametrize(
    "module_name",
    [
        "orchestrator.cli.commands.resume",
        "orchestrator.workflow.executor",
        "orchestrator.workflow.calls",
    ],
)
def test_runtime_and_resume_modules_do_not_import_retirement_evidence(module_name: str) -> None:
    spec = importlib.util.find_spec(module_name)
    assert spec is not None and spec.origin is not None
    source = Path(spec.origin).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert all("procedure_identity_retirement" not in name for name in imported)

    command = (
        "import importlib,sys; "
        f"importlib.import_module({module_name!r}); "
        "assert 'orchestrator.workflow_lisp.procedure_identity_retirement' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", command], cwd=REPO_ROOT, check=True)


def test_fixture_artifact_hashes_are_literal_sha256_of_repository_files() -> None:
    for artifact in _payload()["artifacts"]:
        actual = hashlib.sha256((REPO_ROOT / artifact["path"]).read_bytes()).hexdigest()
        assert artifact["sha256"] == f"sha256:{actual}"
