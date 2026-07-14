from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
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
    assert result["terminal_run_count"] == 0
    assert result["nonterminal_run_count"] == 1
    assert result["store_terminal_run_count"] == 1
    assert result["store_nonterminal_run_count"] == 1
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


def test_store_scan_discloses_unrelated_nonterminal_run_without_gating_match_counts(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    run = store / "run"
    run.mkdir(parents=True)
    (run / "state.json").write_text(json.dumps({"status": "running"}), encoding="utf-8")

    result = scan_known_state_store(
        store,
        retired_identities={"retired-step"},
        query_version="procedure-identity-store-query.v1",
    )

    assert result["matches"] == ()
    assert result["terminal_run_count"] == 0
    assert result["nonterminal_run_count"] == 0
    assert result["store_terminal_run_count"] == 0
    assert result["store_nonterminal_run_count"] == 1


def test_store_scan_counts_matching_nonterminal_run(tmp_path: Path) -> None:
    store = tmp_path / "store"
    run = store / "run"
    run.mkdir(parents=True)
    (run / "state.json").write_text(
        json.dumps({"status": "running", "step_id": "retired-step"}), encoding="utf-8"
    )

    result = scan_known_state_store(
        store,
        retired_identities={"retired-step"},
        query_version="procedure-identity-store-query.v1",
    )

    assert result["terminal_run_count"] == 0
    assert result["nonterminal_run_count"] == 1
    assert result["store_terminal_run_count"] == 0
    assert result["store_nonterminal_run_count"] == 1


def test_store_scan_separates_unrelated_terminal_from_matching_nonterminal_run(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    terminal = store / "terminal"
    active = store / "active"
    terminal.mkdir(parents=True)
    active.mkdir(parents=True)
    (terminal / "state.json").write_text(
        json.dumps({"status": "completed"}), encoding="utf-8"
    )
    (active / "state.json").write_text(
        json.dumps({"status": "running", "step_id": "retired-step"}), encoding="utf-8"
    )

    result = scan_known_state_store(
        store,
        retired_identities={"retired-step"},
        query_version="procedure-identity-store-query.v1",
    )

    assert result["terminal_run_count"] == 0
    assert result["nonterminal_run_count"] == 1
    assert result["store_terminal_run_count"] == 1
    assert result["store_nonterminal_run_count"] == 1


def test_store_scan_counts_run_once_when_it_contains_several_matches(tmp_path: Path) -> None:
    store = tmp_path / "store"
    run = store / "run"
    run.mkdir(parents=True)
    (run / "state.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "steps": {
                    "retired-step": {"step_id": "retired-step"},
                },
            }
        ),
        encoding="utf-8",
    )

    result = scan_known_state_store(
        store,
        retired_identities={"retired-step"},
        query_version="procedure-identity-store-query.v1",
    )

    assert result["consumer_count"] > 1
    assert result["terminal_run_count"] == 1
    assert result["nonterminal_run_count"] == 0
    assert result["store_terminal_run_count"] == 1
    assert result["store_nonterminal_run_count"] == 0


def test_store_scan_associates_nested_match_with_containing_run_status(tmp_path: Path) -> None:
    store = tmp_path / "store"
    run = store / "run"
    nested = run / "call_frames" / "frame"
    nested.mkdir(parents=True)
    (run / "state.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    (nested / "state.json").write_text(
        json.dumps({"call_frame_id": "retired-frame"}), encoding="utf-8"
    )

    result = scan_known_state_store(
        store,
        retired_identities={"retired-frame"},
        query_version="procedure-identity-store-query.v1",
    )

    assert result["terminal_run_count"] == 1
    assert result["nonterminal_run_count"] == 0
    assert result["store_terminal_run_count"] == 1
    assert result["store_nonterminal_run_count"] == 0


def test_store_scan_rejects_nested_match_without_containing_run_state(tmp_path: Path) -> None:
    store = tmp_path / "store"
    nested = store / "run" / "call_frames" / "frame"
    nested.mkdir(parents=True)
    (nested / "state.json").write_text(
        json.dumps({"call_frame_id": "retired-frame"}), encoding="utf-8"
    )

    with pytest.raises(
        ValueError,
        match="procedure_identity_retirement_matching_run_state_missing",
    ):
        scan_known_state_store(
            store,
            retired_identities={"retired-frame"},
            query_version="procedure-identity-store-query.v1",
        )


def test_store_scan_keeps_root_level_identity_metadata_as_non_run_consumer(
    tmp_path: Path,
) -> None:
    store = tmp_path / "store"
    store.mkdir()
    (store / "identity_index.json").write_text(
        json.dumps({"presentation_key": "retired-presentation"}), encoding="utf-8"
    )

    result = scan_known_state_store(
        store,
        retired_identities={"retired-presentation"},
        query_version="procedure-identity-store-query.v1",
    )

    assert result["consumer_count"] == 1
    assert result["terminal_run_count"] == 0
    assert result["nonterminal_run_count"] == 0
    assert result["store_terminal_run_count"] == 0
    assert result["store_nonterminal_run_count"] == 0


@pytest.mark.parametrize("status_payload", [{}, {"status": "paused-unrecognized"}])
def test_store_scan_treats_matching_run_without_known_terminal_status_as_nonterminal(
    tmp_path: Path,
    status_payload: dict[str, str],
) -> None:
    store = tmp_path / "store"
    run = store / "run"
    run.mkdir(parents=True)
    (run / "state.json").write_text(
        json.dumps({**status_payload, "step_id": "retired-step"}), encoding="utf-8"
    )

    result = scan_known_state_store(
        store,
        retired_identities={"retired-step"},
        query_version="procedure-identity-store-query.v1",
    )

    assert result["terminal_run_count"] == 0
    assert result["nonterminal_run_count"] == 1
    assert result["store_terminal_run_count"] == 0
    assert result["store_nonterminal_run_count"] == 1


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

    def new_preserved_without_old(payload: dict[str, Any]) -> None:
        row = payload["identity_delta"][0]
        row.update(old_identity=None, old_disposition=None)

    assert "procedure_identity_retirement_identity_row_invalid" in _issues_for(tmp_path, new_preserved_without_old)

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


PRODUCTION_ARTIFACT_NAMES = (
    "typed_frontend_ast",
    "semantic_ir",
    "executable_ir",
    "runtime_plan",
    "lexical_checkpoint_points",
    "source_map",
)


def _canonical_production_artifact(payload: Any) -> Any:
    if isinstance(payload, dict):
        normalized = {key: _canonical_production_artifact(value) for key, value in payload.items()}
        provenance = normalized.get("provenance")
        if isinstance(provenance, dict) and "frontend_build_root" in provenance:
            provenance["frontend_build_root"] = "<BUILD_ROOT>"
            provenance["frontend_source_trace_path"] = "<BUILD_ROOT>/source_map.json"
        if "bindings" in normalized and "schema_digest" in normalized:
            normalized["schema_digest"] = "<PATH_NORMALIZED_SCHEMA_DIGEST>"
        if "policy_kind" in normalized and "policy_digest" in normalized:
            normalized["policy_digest"] = "<PATH_NORMALIZED_POLICY_DIGEST>"
        if "bundle_path_ref" in normalized and "contract_digest" in normalized:
            normalized["contract_digest"] = "<PATH_NORMALIZED_CONTRACT_DIGEST>"
        if "executable_ir_digest" in normalized and "semantic_ir_digest" in normalized:
            normalized["executable_ir_digest"] = "<PATH_NORMALIZED_IR_DIGEST>"
            normalized["semantic_ir_digest"] = "<PATH_NORMALIZED_IR_DIGEST>"
        return normalized
    if isinstance(payload, list):
        return [_canonical_production_artifact(value) for value in payload]
    if isinstance(payload, str) and "/procedure_identity_retirement/" in payload:
        payload = re.sub(
            r"/(?:[^/\"' ),]+/)*procedure_identity_retirement",
            "<FIXTURE_ROOT>",
            payload,
        )
    if isinstance(payload, str) and payload.startswith("frozenset({") and payload.endswith("})"):
        members = payload[len("frozenset({") : -2].split(", ")
        return "frozenset({" + ", ".join(sorted(members)) + "})"
    return payload


def _build_procedure_retirement_side(side: str, workspace: Path, fixture_root: Path | None = None):
    fixture_root = fixture_root or FIXTURE.parent
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    request = build.FrontendBuildRequest(
        source_path=fixture_root / side / "source.orc",
        source_roots=(fixture_root / side,),
        entry_workflow="orchestrate",
        provider_externs_path=fixture_root / "providers.json",
        prompt_externs_path=fixture_root / "prompts.json",
        command_boundaries_path=fixture_root / "commands.json",
        emit_debug_yaml=False,
        workspace_root=workspace,
        lowering_route="wcc_m4",
    )
    return build.build_frontend_bundle(request)


@pytest.mark.parametrize("side", ["old", "new"])
def test_checked_retirement_artifacts_reproduce_from_production_build(side: str, tmp_path: Path) -> None:
    result = _build_procedure_retirement_side(side, tmp_path / side)

    assert result.selected_workflow_name == "source::orchestrate"
    for artifact_name in PRODUCTION_ARTIFACT_NAMES:
        checked_path = FIXTURE.parent / side / f"{artifact_name}.json"
        checked = json.loads(checked_path.read_text(encoding="utf-8"))
        rebuilt = json.loads(result.artifact_paths[artifact_name].read_text(encoding="utf-8"))
        assert _canonical_production_artifact(checked) == _canonical_production_artifact(rebuilt)


def test_production_artifact_schemas_and_migration_identities_derive_from_sources(tmp_path: Path) -> None:
    old = _build_procedure_retirement_side("old", tmp_path / "old")
    new = _build_procedure_retirement_side("new", tmp_path / "new")
    old_typed = json.loads(old.artifact_paths["typed_frontend_ast"].read_text(encoding="utf-8"))
    new_typed = json.loads(new.artifact_paths["typed_frontend_ast"].read_text(encoding="utf-8"))
    old_points = json.loads(old.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))
    new_points = json.loads(new.artifact_paths["lexical_checkpoint_points"].read_text(encoding="utf-8"))
    new_source_map = json.loads(new.artifact_paths["source_map"].read_text(encoding="utf-8"))

    assert old_typed["modules"]["source"]["typed_procedures"] == []
    assert any(workflow["definition"]["name"] == "source::internal-phase" for workflow in old_typed["modules"]["source"]["typed_workflows"])
    internal = next(row for row in new_typed["modules"]["source"]["typed_procedures"] if row["definition"]["name"] == "source::internal-phase")
    assert internal["resolved_lowering_mode"] == "inline"
    assert old_points["schema_version"] == "workflow_lisp_lexical_checkpoint_points.v1"
    assert old_points["points"][0]["effect_boundary"]["boundary_kind"] == "call"
    assert new_points["points"][0]["effect_boundary"]["boundary_kind"] == "command"
    notes = json.dumps(new_source_map["workflows"]["source::orchestrate"], sort_keys=True)
    assert "procedure definition at" in notes
    assert "procedure call site at" in notes
    assert json.loads(new.artifact_paths["semantic_ir"].read_text())["schema_version"] == "workflow_semantic_ir.v1"
    assert json.loads(new.artifact_paths["executable_ir"].read_text())["schema_version"] == "workflow_executable_ir.v1"
    assert json.loads(new.artifact_paths["runtime_plan"].read_text())["schema_version"] == "workflow_runtime_plan.v1"
    assert new_source_map["schema_version"] == "workflow_lisp_source_map.v1"
    new_executable = json.loads(new.artifact_paths["executable_ir"].read_text(encoding="utf-8"))
    assert {
        name: (row["kind"], row["value_type"])
        for name, row in new_executable["outputs"].items()
    } == {
        "return__approved": ("scalar", "bool"),
        "return__decision": ("scalar", "enum"),
        "return__report": ("relpath", "relpath"),
    }


def test_production_artifacts_rebuild_identically_under_two_fixture_roots(tmp_path: Path) -> None:
    roots = [tmp_path / name / "procedure_identity_retirement" for name in ("first", "second")]
    for root in roots:
        shutil.copytree(FIXTURE.parent, root, ignore=shutil.ignore_patterns(".reproduction"))

    for side in ("old", "new"):
        first = _build_procedure_retirement_side(side, tmp_path / "build-first" / side, roots[0])
        second = _build_procedure_retirement_side(side, tmp_path / "build-second" / side, roots[1])
        for artifact_name in PRODUCTION_ARTIFACT_NAMES:
            first_payload = json.loads(first.artifact_paths[artifact_name].read_text(encoding="utf-8"))
            second_payload = json.loads(second.artifact_paths[artifact_name].read_text(encoding="utf-8"))
            assert _canonical_production_artifact(first_payload) == _canonical_production_artifact(second_payload)


def test_identity_table_covers_all_source_map_origins_and_state_allocations() -> None:
    record = load_retirement_record(FIXTURE)
    for side in ("old", "new"):
        source_map = json.loads((FIXTURE.parent / side / "source_map.json").read_text(encoding="utf-8"))
        workflows = source_map["workflows"]
        expected_origins: set[str] = set()

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                if isinstance(value.get("origin_key"), str):
                    expected_origins.add(value["origin_key"])
                for item in value.values():
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        collect(workflows)
        points = json.loads(
            (FIXTURE.parent / side / "lexical_checkpoint_points.json").read_text(encoding="utf-8")
        )["points"]
        expected_allocations = {
            row["allocation_id"]
            for workflow_map in workflows.values()
            for row in workflow_map["generated_path_allocations"]
        } | {point["storage"]["allocation_id"] for point in points}
        identity_attr = f"{side}_identity"
        actual_origins = {
            getattr(row, identity_attr)
            for row in record.identity_delta
            if row.identity_kind == "source_map_origin" and getattr(row, identity_attr) is not None
        }
        actual_allocations = {
            getattr(row, identity_attr)
            for row in record.identity_delta
            if row.identity_kind == "state_allocation" and getattr(row, identity_attr) is not None
        }
        assert actual_origins == expected_origins
        assert actual_allocations == expected_allocations


@pytest.mark.parametrize(
    "mapping_field",
    [
        "artifact_consumes",
        "private_artifact_consumes",
        "_resolved_consumes",
        "_pending_artifact_consumes",
        "_pending_private_artifact_consumes",
        "compatibility_artifact_consumes",
        "public_artifact_consumes",
        "resolved_artifact_consumes",
        "for_each",
        "repeat_until",
    ],
)
def test_store_scan_covers_real_identity_addressed_state_maps(
    tmp_path: Path,
    mapping_field: str,
) -> None:
    store = tmp_path / "store"
    run = store / "run"
    run.mkdir(parents=True)
    (run / "state.json").write_text(
        json.dumps({"status": "completed", mapping_field: {"retired-step": {}}}),
        encoding="utf-8",
    )

    result = scan_known_state_store(
        store,
        retired_identities={"retired-step"},
        query_version="procedure-identity-store-query.v1",
    )

    assert result["consumer_count"] == 1
    assert result["matches"][0]["identity"] == "retired-step"


@pytest.mark.parametrize(
    "field",
    [
        "producer",
        "source_step_id",
        "storage_allocation_id",
        "producer_step_id",
        "call_presentation_key",
        "caller_node_id",
    ],
)
def test_store_scan_covers_real_artifact_version_and_call_identity_fields(tmp_path: Path, field: str) -> None:
    store = tmp_path / "store"
    run = store / "run"
    run.mkdir(parents=True)
    state = {"status": "completed", "artifact_versions": {"report": [{field: "retired-id"}]}}
    (run / "state.json").write_text(json.dumps(state), encoding="utf-8")

    result = scan_known_state_store(
        store,
        retired_identities={"retired-id"},
        query_version="procedure-identity-store-query.v1",
    )

    assert result["consumer_count"] == 1
    assert result["matches"][0]["field"] == field


def test_store_scan_handles_real_runstate_and_lexical_checkpoint_shapes(tmp_path: Path) -> None:
    from orchestrator.state import ForEachState, RunState, StepResult

    store = tmp_path / "store"
    run = store / "run"
    checkpoints = run / "checkpoints"
    checkpoints.mkdir(parents=True)
    state = RunState(
        schema_version="2.1",
        run_id="fixture-run",
        workflow_file="workflow.orc",
        workflow_checksum="sha256:" + "0" * 64,
        started_at="2026-07-14T00:00:00+00:00",
        updated_at="2026-07-14T00:00:00+00:00",
        status="completed",
        steps={"retired-step": StepResult(status="completed", step_id="retired-step")},
        for_each={"retired-loop": ForEachState(items=[])},
        repeat_until={"retired-repeat": {"iteration": 1}},
        artifact_versions={
            "report": [{"producer": "retired-producer", "source_step_id": "retired-source"}]
        },
    )
    (run / "state.json").write_text(json.dumps(state.to_dict()), encoding="utf-8")
    point = json.loads((FIXTURE.parent / "new" / "lexical_checkpoint_points.json").read_text())["points"][0]
    record = {
        "schema_version": "workflow_lisp_lexical_checkpoint.v1",
        "checkpoint_id": point["checkpoint_id"],
        "program_point_id": point["program_point_id"],
        "record_id": "retired-record",
        "storage_allocation_id": point["storage"]["allocation_id"],
        "origin_key": point["source_lineage"]["origin_key"],
    }
    (checkpoints / "record.json").write_text(json.dumps(record), encoding="utf-8")
    retired = {
        "retired-step",
        "retired-loop",
        "retired-repeat",
        "retired-producer",
        "retired-source",
        point["checkpoint_id"],
        point["program_point_id"],
        point["storage"]["allocation_id"],
        point["source_lineage"]["origin_key"],
    }

    result = scan_known_state_store(
        store,
        retired_identities=retired,
        query_version="procedure-identity-store-query.v1",
    )

    assert retired.issubset({row["identity"] for row in result["matches"]})


def test_validator_allows_explicit_external_known_store_with_fresh_facts(tmp_path: Path) -> None:
    external = tmp_path / "external-runs"
    run = external / "run"
    run.mkdir(parents=True)
    (run / "state.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    record = load_retirement_record(FIXTURE)
    retired = {row.old_identity for row in record.identity_delta if row.old_disposition == "retired" and row.old_identity}
    observed = scan_known_state_store(
        external,
        retired_identities=retired,
        query_version="procedure-identity-store-query.v1",
    )
    store = replace(
        record.known_state_stores[0],
        root=str(external),
        normalized_scan_digest=observed["normalized_scan_digest"],
        **{field: observed[field] for field in (
            "terminal_run_count", "nonterminal_run_count", "call_frame_count", "consumer_count",
            "checkpoint_index_count", "checkpoint_record_count", "retained_manifest_count",
            "identity_metadata_count", "scanned_file_count",
        )},
    )

    result = validate_retirement_record(replace(record, known_state_stores=(store,)), repo_root=REPO_ROOT)

    assert result.valid is True


@pytest.mark.parametrize("mutation", ["add", "remove", "replace", "mutate"])
def test_store_scan_rejects_concurrent_tree_addition_or_removal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    module = _retirement_module()
    store = tmp_path / "store"
    run = store / "run"
    run.mkdir(parents=True)
    state = run / "state.json"
    state.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    original = module._read_stable_bytes
    changed = False

    def mutate_tree(path: Path) -> bytes:
        nonlocal changed
        content = original(path)
        if not changed:
            changed = True
            if mutation == "add":
                (run / "added.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
            elif mutation == "remove":
                state.unlink()
            elif mutation == "replace":
                replacement = run / "replacement.json"
                replacement.write_text(json.dumps({"status": "completed"}), encoding="utf-8")
                replacement.replace(state)
            else:
                state.write_text(json.dumps({"status": "failed", "changed": True}), encoding="utf-8")
        return content

    monkeypatch.setattr(module, "_read_stable_bytes", mutate_tree)

    with pytest.raises(ValueError, match="procedure_identity_retirement_known_store_tree_changed"):
        scan_known_state_store(
            store,
            retired_identities=set(),
            query_version="procedure-identity-store-query.v1",
        )


def test_store_scan_ignores_unrelated_output_json_outside_state_surfaces(tmp_path: Path) -> None:
    store = tmp_path / "store"
    run = store / "run"
    outputs = run / "outputs"
    outputs.mkdir(parents=True)
    (run / "state.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    (outputs / "scalar.json").write_text("true", encoding="utf-8")
    (outputs / "list.json").write_text("[1, 2, 3]", encoding="utf-8")

    result = scan_known_state_store(
        store,
        retired_identities=set(),
        query_version="procedure-identity-store-query.v1",
    )

    assert result["terminal_run_count"] == 0
    assert result["nonterminal_run_count"] == 0
    assert result["store_terminal_run_count"] == 1
    assert result["store_nonterminal_run_count"] == 0
    assert result["consumer_count"] == 0


def test_cross_row_identity_table_rejects_retire_then_recreate(tmp_path: Path) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        retired = copy.deepcopy(payload["identity_delta"][1])
        recreated = {
            "identity_kind": retired["identity_kind"],
            "old_identity": None,
            "old_disposition": None,
            "new_identity": retired["old_identity"],
            "new_disposition": "new",
        }
        payload["identity_delta"].append(recreated)

    assert "procedure_identity_retirement_identity_recreated" in _issues_for(tmp_path, mutate)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda payload: payload["new_id_evidence"]["interruption_resume"].__setitem__("interruption_point", "not-a-new-point"), "procedure_identity_retirement_interruption_point_unknown"),
        (lambda payload: payload["new_id_evidence"]["interruption_resume"].__setitem__("run_id", payload["new_id_evidence"]["clean_run"]["run_id"]), "procedure_identity_retirement_new_id_run_ids_not_distinct"),
        (lambda payload: payload["checksum_evidence"]["callee"].__setitem__("mismatch_identity", "different-callee"), "procedure_identity_retirement_callee_identity_mismatch"),
        (lambda payload: payload["lineage_notes"][0].__setitem__("executable_node", "unknown-node"), "procedure_identity_retirement_lineage_identity_mismatch"),
        (lambda payload: payload["lineage_notes"][0].__setitem__("source_map_origin", "unknown-origin"), "procedure_identity_retirement_lineage_identity_mismatch"),
    ],
)
def test_production_identity_evidence_cross_relations_fail_closed(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    code: str,
) -> None:
    assert code in _issues_for(tmp_path, mutation)


def test_retained_inventory_is_separate_content_addressed_evidence(tmp_path: Path) -> None:
    payload = _payload()
    assert payload["retained_wrapper_evidence"]["inventory_path"].endswith("retained_inventory.json")
    inventory_path = REPO_ROOT / payload["retained_wrapper_evidence"]["inventory_path"]
    assert payload["retained_wrapper_evidence"]["inventory_sha256"] == (
        "sha256:" + hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    )

    payload["retained_wrapper_evidence"]["inventory_sha256"] = "sha256:" + "0" * 64
    record = load_retirement_record(_write_payload(tmp_path, payload))
    issues = {issue.code for issue in validate_retirement_record(record, repo_root=REPO_ROOT).issues}
    assert "procedure_identity_retirement_inventory_digest_mismatch" in issues


def _copied_retirement_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    copied = repo / FIXTURE.relative_to(REPO_ROOT).parent
    shutil.copytree(FIXTURE.parent, copied, ignore=shutil.ignore_patterns(".reproduction"))
    return repo, copied


def test_production_identity_inventory_rejects_extra_and_relabelled_rows(tmp_path: Path) -> None:
    def extra(payload: dict[str, Any]) -> None:
        payload["identity_delta"].append(
            {
                "identity_kind": "executable_node",
                "old_identity": None,
                "old_disposition": None,
                "new_identity": "fabricated-node",
                "new_disposition": "new",
            }
        )

    assert "procedure_identity_retirement_identity_artifact_mismatch" in _issues_for(tmp_path, extra)

    def relabel(payload: dict[str, Any]) -> None:
        row = next(
            row
            for row in payload["identity_delta"]
            if row["identity_kind"] == "checkpoint" and row["old_disposition"] == "retired"
        )
        row.update(new_identity=row["old_identity"], new_disposition="preserved", old_disposition="preserved")

    assert "procedure_identity_retirement_identity_artifact_mismatch" in _issues_for(tmp_path, relabel)


def test_content_addressed_production_json_must_be_an_object(tmp_path: Path) -> None:
    repo, copied = _copied_retirement_repo(tmp_path)
    record_path = copied / "valid_internal_retirement.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    semantic_path = copied / "new" / "semantic_ir.json"
    semantic_path.write_text("true\n", encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(semantic_path.read_bytes()).hexdigest()
    next(
        row for row in payload["artifacts"] if row["side"] == "new" and row["role"] == "semantic_ir"
    )["sha256"] = digest
    record_path.write_text(json.dumps(payload), encoding="utf-8")

    issues = validate_retirement_record(load_retirement_record(record_path), repo_root=repo).issues

    assert "procedure_identity_retirement_artifact_content_invalid" in {issue.code for issue in issues}


@pytest.mark.parametrize(
    ("role", "schema", "code"),
    [
        (
            "semantic_ir",
            "workflow_semantic_ir.v1",
            "procedure_identity_retirement_semantic_ir_structure_invalid",
        ),
        (
            "runtime_plan",
            "workflow_runtime_plan.v1",
            "procedure_identity_retirement_runtime_plan_structure_invalid",
        ),
    ],
)
def test_schema_only_production_ir_cannot_satisfy_evidence(
    tmp_path: Path,
    role: str,
    schema: str,
    code: str,
) -> None:
    repo, copied = _copied_retirement_repo(tmp_path)
    record_path = copied / "valid_internal_retirement.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    artifact_path = copied / "new" / f"{role}.json"
    artifact_path.write_text(json.dumps({"schema_version": schema}), encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    next(
        row for row in payload["artifacts"] if row["side"] == "new" and row["role"] == role
    )["sha256"] = digest
    manifest_path = copied / "new" / "build_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"][role]["sha256"] = digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    next(
        row
        for row in payload["artifacts"]
        if row["side"] == "new" and row["role"] == "build_manifest"
    )["sha256"] = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    record_path.write_text(json.dumps(payload), encoding="utf-8")

    issues = validate_retirement_record(load_retirement_record(record_path), repo_root=repo).issues

    assert code in {issue.code for issue in issues}


@pytest.mark.parametrize(
    ("role", "mutation", "code"),
    [
        (
            "semantic_ir",
            lambda artifact: artifact["workflows"]["source::orchestrate"]["executable_bridge"].__setitem__("node_ids", None),
            "procedure_identity_retirement_semantic_ir_structure_invalid",
        ),
        (
            "runtime_plan",
            lambda artifact: artifact.__setitem__("ordered_node_ids", [{}]),
            "procedure_identity_retirement_runtime_plan_structure_invalid",
        ),
        (
            "runtime_plan",
            lambda artifact: artifact.__setitem__("lexical_checkpoint_points", [{"checkpoint_id": {}}]),
            "procedure_identity_retirement_runtime_plan_structure_invalid",
        ),
    ],
)
def test_malformed_nested_production_ir_returns_issues_instead_of_raising(
    tmp_path: Path,
    role: str,
    mutation: Callable[[dict[str, Any]], None],
    code: str,
) -> None:
    repo, copied = _copied_retirement_repo(tmp_path)
    record_path = copied / "valid_internal_retirement.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    artifact_path = copied / "new" / f"{role}.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    mutation(artifact)
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    next(
        row for row in payload["artifacts"] if row["side"] == "new" and row["role"] == role
    )["sha256"] = digest
    manifest_path = copied / "new" / "build_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"][role]["sha256"] = digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    next(
        row
        for row in payload["artifacts"]
        if row["side"] == "new" and row["role"] == "build_manifest"
    )["sha256"] = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    record_path.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_retirement_record(load_retirement_record(record_path), repo_root=repo)

    assert code in {issue.code for issue in result.issues}


def test_inventory_exports_cannot_contradict_internal_callee(tmp_path: Path) -> None:
    repo, copied = _copied_retirement_repo(tmp_path)
    record_path = copied / "valid_internal_retirement.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    inventory_path = copied / "retained_inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["exported_entries"].append("internal-phase")
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    payload["retained_wrapper_evidence"]["inventory_sha256"] = (
        "sha256:" + hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    )
    record_path.write_text(json.dumps(payload), encoding="utf-8")

    issues = validate_retirement_record(load_retirement_record(record_path), repo_root=repo).issues

    assert "procedure_identity_retirement_inventory_content_mismatch" in {issue.code for issue in issues}


def test_source_and_build_manifest_cannot_be_readdressed_away_from_compiler_outputs(tmp_path: Path) -> None:
    repo, copied = _copied_retirement_repo(tmp_path)
    record_path = copied / "valid_internal_retirement.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    source_path = copied / "old" / "source.orc"
    source_path.write_text("(workflow-lisp (:language \"0.1\") (:target-dsl \"2.15\") (defworkflow other () -> Unit (return)))\n", encoding="utf-8")
    source_digest = "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
    next(row for row in payload["artifacts"] if row["side"] == "old" and row["role"] == "source")["sha256"] = source_digest
    manifest_path = copied / "old" / "build_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["inputs"]["source"]["sha256"] = source_digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    next(row for row in payload["artifacts"] if row["side"] == "old" and row["role"] == "build_manifest")["sha256"] = (
        "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    )
    record_path.write_text(json.dumps(payload), encoding="utf-8")

    issues = validate_retirement_record(load_retirement_record(record_path), repo_root=repo).issues

    assert "procedure_identity_retirement_source_build_mismatch" in {issue.code for issue in issues}


def test_unsafe_artifact_is_not_opened_by_downstream_relation_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _retirement_module()
    record = load_retirement_record(FIXTURE)
    unsafe = tmp_path / "must-not-open.orc"
    unsafe.write_text("sensitive", encoding="utf-8")
    source = next(row for row in record.artifacts if row.side == "old" and row.role == "source")
    changed = replace(source, path=str(unsafe))
    artifacts = tuple(changed if row is source else row for row in record.artifacts)
    original = module._read_stable_bytes

    def guarded(path: Path) -> bytes:
        if path == unsafe:
            raise AssertionError("unsafe artifact was opened")
        return original(path)

    monkeypatch.setattr(module, "_read_stable_bytes", guarded)
    issues = validate_retirement_record(replace(record, artifacts=artifacts), repo_root=REPO_ROOT).issues

    assert "procedure_identity_retirement_artifact_path_outside_repository" in {issue.code for issue in issues}
