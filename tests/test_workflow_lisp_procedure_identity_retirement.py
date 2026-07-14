from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError, replace
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
    before = scan_known_state_store(
        store,
        retired_identities={"old-step"},
        query_version="procedure-identity-store-query.v1",
    )
    state.write_text(json.dumps({"status": "completed", "step_id": "different-step"}), encoding="utf-8")
    after = scan_known_state_store(
        store,
        retired_identities={"old-step"},
        query_version="procedure-identity-store-query.v1",
    )

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


def test_validator_requeries_known_store_and_binds_digest_and_every_count() -> None:
    record = load_retirement_record(FIXTURE)

    result = validate_retirement_record(record, repo_root=REPO_ROOT)

    assert result.valid is True


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("normalized_scan_digest", "sha256:" + "0" * 64, "procedure_identity_retirement_known_store_digest_mismatch"),
        ("terminal_run_count", 99, "procedure_identity_retirement_known_store_count_mismatch"),
        ("nonterminal_run_count", 99, "procedure_identity_retirement_known_store_count_mismatch"),
        ("call_frame_count", 99, "procedure_identity_retirement_known_store_count_mismatch"),
        ("consumer_count", 99, "procedure_identity_retirement_known_store_count_mismatch"),
        ("checkpoint_index_count", 99, "procedure_identity_retirement_known_store_count_mismatch"),
        ("checkpoint_record_count", 99, "procedure_identity_retirement_known_store_count_mismatch"),
        ("retained_manifest_count", 99, "procedure_identity_retirement_known_store_count_mismatch"),
        ("identity_metadata_count", 99, "procedure_identity_retirement_known_store_count_mismatch"),
        ("scanned_file_count", 99, "procedure_identity_retirement_known_store_count_mismatch"),
    ],
)
def test_validator_rejects_stale_known_store_facts(
    tmp_path: Path,
    field: str,
    value: Any,
    code: str,
) -> None:
    issues = _issues_for(tmp_path, lambda payload: payload["known_state_stores"][0].__setitem__(field, value))

    assert code in issues


def test_validator_rejects_duplicate_known_store_roots(tmp_path: Path) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        payload["known_state_stores"].append(copy.deepcopy(payload["known_state_stores"][0]))

    assert "procedure_identity_retirement_known_store_duplicate" in _issues_for(tmp_path, mutate)


@pytest.mark.parametrize(
    ("root", "query_version", "code"),
    [
        ("tests/fixtures/workflow_lisp/procedure_identity_retirement/missing-store", "procedure-identity-store-query.v1", "procedure_identity_retirement_known_store_unavailable"),
        ("../outside-repository", "procedure-identity-store-query.v1", "procedure_identity_retirement_known_store_unsafe_path"),
        ("tests/fixtures/workflow_lisp/procedure_identity_retirement/state_store", "unsupported-query.v2", "procedure_identity_retirement_query_version_unsupported"),
    ],
)
def test_validator_fails_closed_for_unavailable_unsafe_or_unsupported_store(
    tmp_path: Path,
    root: str,
    query_version: str,
    code: str,
) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        store = payload["known_state_stores"][0]
        store["root"] = root
        store["query_version"] = query_version

    assert code in _issues_for(tmp_path, mutate)


@pytest.mark.parametrize(
    "mapping_field",
    ["steps", "completed_steps", "call_frames", "step_visits"],
)
def test_store_scan_finds_retired_identities_in_identity_addressed_mapping_keys(
    tmp_path: Path,
    mapping_field: str,
) -> None:
    store = tmp_path / "store"
    run = store / "run"
    run.mkdir(parents=True)
    (run / "state.json").write_text(
        json.dumps({"status": "completed", mapping_field: {"retired-identity": {"status": "completed"}}}),
        encoding="utf-8",
    )

    result = scan_known_state_store(store, retired_identities={"retired-identity"}, query_version="procedure-identity-store-query.v1")

    assert result["consumer_count"] == 1
    assert result["matches"][0]["identity"] == "retired-identity"
    assert result["matches"][0]["location"].endswith(f"/{mapping_field}/retired-identity")


@pytest.mark.parametrize(
    "field",
    [
        "call_step_id",
        "step_id",
        "node_id",
        "origin_key",
        "source_map_origin_key",
        "execution_frame_id",
        "call_frame_id",
        "checkpoint_id",
        "program_point_id",
        "workflow_id",
        "presentation_key",
        "state_allocation_id",
    ],
)
def test_store_scan_finds_each_supported_identity_value_field(tmp_path: Path, field: str) -> None:
    store = tmp_path / "store"
    run = store / "run"
    run.mkdir(parents=True)
    (run / "state.json").write_text(
        json.dumps({"status": "completed", field: "retired-identity"}), encoding="utf-8"
    )

    result = scan_known_state_store(store, retired_identities={"retired-identity"}, query_version="procedure-identity-store-query.v1")

    assert result["consumer_count"] == 1
    assert result["matches"][0]["field"] == field


def test_store_scan_finds_supported_jsonl_and_path_encoded_identities(tmp_path: Path) -> None:
    store = tmp_path / "store"
    ledger = store / "run" / "ledgers"
    frames = store / "run" / "call_frames" / "retired-frame"
    ledger.mkdir(parents=True)
    frames.mkdir(parents=True)
    (store / "run" / "state.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    (ledger / "events.jsonl").write_text(
        json.dumps({"step_id": "retired-step"}) + "\n" + json.dumps({"checkpoint_id": "other"}) + "\n",
        encoding="utf-8",
    )
    (frames / "state.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    result = scan_known_state_store(
        store,
        retired_identities={"retired-step", "retired-frame"},
        query_version="procedure-identity-store-query.v1",
    )

    assert {row["identity"] for row in result["matches"]} == {"retired-step", "retired-frame"}
    assert any("events.jsonl#1" in row["location"] for row in result["matches"])
    assert any(row["field"] == "path_component" for row in result["matches"])


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("state.json", "{"),
        ("state.json", "[]"),
        ("events.jsonl", "not-json\n"),
        ("events.jsonl", "[]\n"),
    ],
)
def test_store_scan_rejects_malformed_or_nonobject_supported_content(
    tmp_path: Path,
    filename: str,
    content: str,
) -> None:
    store = tmp_path / "store"
    run = store / "run"
    run.mkdir(parents=True)
    (run / filename).write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="procedure_identity_retirement_store_content_invalid"):
        scan_known_state_store(store, retired_identities=set(), query_version="procedure-identity-store-query.v1")


def test_store_scan_rejects_missing_root_and_symlink_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="procedure_identity_retirement_known_store_unavailable"):
        scan_known_state_store(tmp_path / "missing", retired_identities=set(), query_version="procedure-identity-store-query.v1")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "state.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    store = tmp_path / "store"
    store.mkdir()
    (store / "escaped").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="procedure_identity_retirement_store_symlink_forbidden"):
        scan_known_state_store(store, retired_identities=set(), query_version="procedure-identity-store-query.v1")


@pytest.mark.parametrize(
    ("path", "value", "code"),
    [
        (("migration", "migration_id"), "", "procedure_identity_retirement_metadata_missing"),
        (("migration", "repository_commit"), "not-a-commit", "procedure_identity_retirement_metadata_invalid"),
        (("migration", "compiler_version"), " ", "procedure_identity_retirement_metadata_missing"),
        (("migration", "build_version"), "", "procedure_identity_retirement_metadata_missing"),
        (("migration", "captured_at"), "yesterday", "procedure_identity_retirement_timestamp_invalid"),
        (("known_state_stores", 0, "query_time"), "never", "procedure_identity_retirement_timestamp_invalid"),
        (("known_state_stores", 0, "attested_at"), "", "procedure_identity_retirement_attestation_missing"),
        (("retained_public_entry", "contract_digest"), "sha256:ABC", "procedure_identity_retirement_digest_invalid"),
    ],
)
def test_substantive_metadata_and_digest_facts_are_validated(
    tmp_path: Path,
    path: tuple[Any, ...],
    value: Any,
    code: str,
) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        target: Any = payload
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = value

    assert code in _issues_for(tmp_path, mutate)


@pytest.mark.parametrize(
    ("block", "field", "value", "code"),
    [
        ("clean_run", "run_id", "", "procedure_identity_retirement_new_id_evidence_invalid"),
        ("clean_run", "status", "running", "procedure_identity_retirement_new_id_evidence_invalid"),
        ("interruption_resume", "interruption_point", "", "procedure_identity_retirement_new_id_evidence_invalid"),
        ("interruption_resume", "reused_only_new_id_work", False, "procedure_identity_retirement_new_id_evidence_invalid"),
        ("interruption_resume", "public_contract_digest", "sha256:" + "f" * 64, "procedure_identity_retirement_public_contract_mismatch"),
        ("clean_run", "artifact_multiset_digest", "sha256:" + "f" * 64, "procedure_identity_retirement_artifact_multiset_digest_mismatch"),
    ],
)
def test_new_id_evidence_is_substantive_and_cross_related(
    tmp_path: Path,
    block: str,
    field: str,
    value: Any,
    code: str,
) -> None:
    issues = _issues_for(tmp_path, lambda payload: payload["new_id_evidence"][block].__setitem__(field, value))

    assert code in issues


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("exit_status", 0, "procedure_identity_retirement_root_checksum_proof_invalid"),
        ("command", "", "procedure_identity_retirement_root_checksum_proof_invalid"),
        ("before_tree_digest", "sha256:BAD", "procedure_identity_retirement_root_checksum_proof_invalid"),
        ("after_tree_digest", "sha256:" + "f" * 64, "procedure_identity_retirement_root_checksum_proof_invalid"),
    ],
)
def test_root_checksum_proof_requires_substantive_rejection_evidence(
    tmp_path: Path,
    field: str,
    value: Any,
    code: str,
) -> None:
    assert code in _issues_for(tmp_path, lambda payload: payload["checksum_evidence"]["root"].__setitem__(field, value))


@pytest.mark.parametrize("field", ["command", "mismatch_identity", "parent_metadata_delta"])
def test_callee_checksum_characterization_requires_nonempty_metadata(tmp_path: Path, field: str) -> None:
    issues = _issues_for(tmp_path, lambda payload: payload["checksum_evidence"]["callee"].__setitem__(field, ""))

    assert "procedure_identity_retirement_callee_checksum_proof_invalid" in issues


def test_identity_kind_set_is_exact_and_rows_have_canonical_shapes(tmp_path: Path) -> None:
    def unknown(payload: dict[str, Any]) -> None:
        payload["identity_delta"][0]["identity_kind"] = "unknown-domain"

    assert "procedure_identity_retirement_identity_domain_unknown" in _issues_for(tmp_path, unknown)

    def all_null(payload: dict[str, Any]) -> None:
        row = payload["identity_delta"][0]
        row.update(old_identity=None, old_disposition=None, new_identity=None, new_disposition=None)

    assert "procedure_identity_retirement_identity_row_invalid" in _issues_for(tmp_path, all_null)

    def changed_preserved(payload: dict[str, Any]) -> None:
        payload["identity_delta"][0]["new_identity"] = "renamed-retained-stack"

    assert "procedure_identity_retirement_identity_row_invalid" in _issues_for(tmp_path, changed_preserved)

    def retired_with_new(payload: dict[str, Any]) -> None:
        row = payload["identity_delta"][1]
        row.update(new_identity="illegal-new", new_disposition="new")

    assert "procedure_identity_retirement_identity_row_invalid" in _issues_for(tmp_path, retired_with_new)


def test_artifact_roles_are_unique_exact_and_role_appropriate(tmp_path: Path) -> None:
    def duplicate(payload: dict[str, Any]) -> None:
        payload["artifacts"].append(copy.deepcopy(payload["artifacts"][0]))

    assert "procedure_identity_retirement_artifact_role_duplicate" in _issues_for(tmp_path, duplicate)

    def relabel(payload: dict[str, Any]) -> None:
        payload["artifacts"][0]["role"] = "semantic_ir"

    issues = _issues_for(tmp_path, relabel)
    assert "procedure_identity_retirement_artifact_role_duplicate" in issues
    assert "procedure_identity_retirement_artifact_role_missing" in issues
    assert "procedure_identity_retirement_artifact_role_path_mismatch" in issues


def test_artifact_path_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "source_map.json"
    link.symlink_to(target)
    record = load_retirement_record(FIXTURE)
    artifact = replace(
        record.artifacts[0],
        role="source_map",
        path="source_map.json",
        sha256=f"sha256:{hashlib.sha256(target.read_bytes()).hexdigest()}",
    )
    mutated = replace(record, artifacts=(artifact, *record.artifacts[1:]))

    issues = {issue.code for issue in validate_retirement_record(mutated, repo_root=tmp_path).issues}

    assert "procedure_identity_retirement_artifact_symlink_forbidden" in issues


def test_artifact_multiset_rows_and_execution_order_must_be_coherent(tmp_path: Path) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        payload["execution_order"]["new"][0]["name"] = "not-in-artifact-multiset"

    assert "procedure_identity_retirement_artifact_order_incoherent" in _issues_for(tmp_path, mutate)


def test_parser_rejects_duplicate_json_keys_at_every_depth(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    source = FIXTURE.read_text(encoding="utf-8")
    source = source.replace(
        '"migration_id": "fictional-internal-phase-retirement",',
        '"migration_id": "first", "migration_id": "second",',
        1,
    )
    path.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match="procedure_identity_retirement_duplicate_json_key"):
        load_retirement_record(path)


def test_loaded_record_is_deeply_independent_from_source_payload(tmp_path: Path) -> None:
    payload = _payload()
    path = _write_payload(tmp_path, payload)
    record = load_retirement_record(path)
    payload["migration"]["migration_id"] = "mutated"
    payload["new_id_evidence"]["clean_run"]["run_id"] = "mutated"

    assert record.migration["migration_id"] == "fictional-internal-phase-retirement"
    assert record.new_id_evidence["clean_run"]["run_id"] == "fixture-clean-new-ids"


def test_validation_issue_order_is_deterministic_and_deduplicated(tmp_path: Path) -> None:
    payload = _payload()
    payload["callee"]["public"] = True
    payload["callee"]["exported"] = True
    record = load_retirement_record(_write_payload(tmp_path, payload))

    first = validate_retirement_record(record, repo_root=REPO_ROOT).issues
    second = validate_retirement_record(record, repo_root=REPO_ROOT).issues

    assert first == second
    assert len(first) == len({(issue.code, issue.path, issue.message) for issue in first})
