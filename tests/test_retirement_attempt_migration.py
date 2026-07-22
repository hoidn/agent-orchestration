from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest


def test_attempt_migration_module_exists() -> None:
    assert importlib.util.find_spec("orchestrator.retirement.attempt_migration") is not None


def test_attempt_migration_public_api_is_complete() -> None:
    from orchestrator.retirement import attempt_migration

    assert {
        "AttemptMigrationError",
        "apply",
        "capture",
        "main",
        "postvalidate",
        "validate",
    } <= set(dir(attempt_migration))


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write(root: Path, relative: str, data: bytes, mode: int = 0o644) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)


def _git(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    return completed.stdout


def _git_with_index(root: Path, index_path: Path, *arguments: str) -> bytes:
    environment = dict(os.environ)
    environment["GIT_INDEX_FILE"] = str(index_path)
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    return completed.stdout


def _review(
    kind: str,
    subject_path: str,
    subject_data: bytes,
    reviewer: str,
    *,
    subject_kind: str = "attempt_migration_authority",
    subject_sha256: str | None = None,
) -> bytes:
    record = {
        "claims_not_made": ["This review grants no mutation authority by itself."],
        "issues": [],
        "result": "approved",
        "review_kind": kind,
        "reviewed_at": (
            "2026-07-22T12:00:00+00:00"
            if kind == "specification"
            else "2026-07-22T12:01:00+00:00"
        ),
        "reviewer": {"identity": reviewer},
        "schema_version": "review.v1",
        "subject": {
            "kind": subject_kind,
            "path": subject_path,
            "sha256": subject_sha256 or _digest(subject_data),
        },
    }
    return _canonical(record) + b"\n"


def _file_binding(root: Path, relative: str, *, full: bool = False) -> dict[str, object]:
    path = root / relative
    binding: dict[str, object] = {
        "path": relative,
        "size": path.stat().st_size,
        "sha256": _digest(path.read_bytes()),
    }
    if full:
        binding.update(
            {
                "file_type": "regular",
                "lstat_mode": stat.S_IMODE(path.stat().st_mode),
            }
        )
    return binding


AUTHORITY_CLAIMS_NOT_MADE = [
    "This subject authorizes only review of the bound generic migration mechanism and synthetic verification evidence.",
    "This subject does not itself authorize relocation, owner adoption, workflow execution, or completion.",
]


def _make_migration_repository(
    tmp_path: Path, *, attempt_path_count: int = 9, protected_path_count: int = 1
) -> dict[str, object]:
    assert attempt_path_count >= 9
    assert protected_path_count >= 1
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "tests@example.invalid")
    _git(root, "config", "user.name", "Attempt Migration Tests")

    source_root = "evidence/live-attempt"
    archive_root = "evidence/archive"
    governing = "plans/governing.md"
    migration = "plans/correction.md"
    authority_subject = "authority/subject.json"
    authority_spec = "authority/specification-review.json"
    authority_quality = "authority/quality-review.json"
    manifest = "authority/expected-paths.txt"
    protected = [
        f"protected/local-notes-{index:02d}.md"
        for index in range(protected_path_count)
    ]
    mechanism = "implementation/attempt_migration.py"
    mechanism_test = "implementation/test_attempt_migration.py"
    verification_evidence = {
        "candidate_manifest": "verification/candidate-manifest.json",
        "exact_diff": "verification/exact.diff",
        "focused_test_evidence": "verification/focused-tests.txt",
        "broad_test_evidence": "verification/broad-tests.txt",
    }
    g5_request = "evidence/foundation/g5-request.json"
    g5_snapshot = "evidence/foundation/g5-snapshot.json"
    live_ledger = f"{source_root}/execution-ledger.json"
    g11_request = f"{source_root}/g11-request.json"
    g11_snapshot = f"{source_root}/g11-snapshot.json"
    baseline = f"{source_root}/baseline.json"
    baseline_spec = f"{source_root}/baseline-specification.json"
    baseline_quality = f"{source_root}/baseline-quality.json"
    pending_request = f"{source_root}/pending-request.json"
    pending_snapshot = f"{source_root}/pending-snapshot.json"
    pending_record = f"{source_root}/pending.json"
    disposition = "evidence/migration/disposition.json"
    disposition_spec = "evidence/migration/specification-review.json"
    disposition_quality = "evidence/migration/quality-review.json"
    post_report = "evidence/migration/post-report.json"

    g5 = b'{"generation":5}\n'
    _write(root, governing, b"governing plan\n")
    _write(root, g5_request, b'{"request":5}\n')
    _write(root, g5_snapshot, g5)
    _write(root, live_ledger, g5)
    for index, protected_path in enumerate(protected):
        _write(root, protected_path, f"original notes {index}\n".encode(), 0o640)
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "source state")
    source_commit = _git(root, "rev-parse", "HEAD").decode().strip()
    source_tree = _git(root, "rev-parse", "HEAD^{tree}").decode().strip()

    expected_paths = sorted(
        [
            live_ledger,
            g11_request,
            g11_snapshot,
            baseline,
            baseline_spec,
            baseline_quality,
            pending_request,
            pending_snapshot,
            pending_record,
        ]
        + [
            f"{source_root}/extra/row-{index:03d}.json"
            for index in range(attempt_path_count - 9)
        ]
    )
    _write(root, migration, b"corrective plan\n")
    _write(root, manifest, ("\n".join(expected_paths) + "\n").encode())
    _write(root, mechanism, b"generic mechanism bytes\n")
    _write(root, mechanism_test, b"generic synthetic tests\n")
    for evidence_path in verification_evidence.values():
        _write(root, evidence_path, f"evidence for {evidence_path}\n".encode())
    for index, protected_path in enumerate(protected):
        _write(root, protected_path, f"dirty notes {index}\n".encode(), 0o640)

    manifest_binding = _file_binding(root, manifest)
    manifest_binding.update(
        {
            "row_count": len(expected_paths),
            "normalized_path_set_sha256": _digest(_canonical(expected_paths)),
        }
    )
    subject = {
        "schema_version": "attempt_migration_authority_subject.v1",
        "governing_plan_binding": _file_binding(root, governing),
        "migration_plan_binding": _file_binding(root, migration),
        "expected_paths_manifest_binding": manifest_binding,
        "protected_path_bindings": [
            _file_binding(root, path, full=True) for path in protected
        ],
        "mechanism_binding": _file_binding(root, mechanism, full=True),
        "test_binding": _file_binding(root, mechanism_test, full=True),
        "evidence_bindings": {
            role: _file_binding(root, path, full=True)
            for role, path in verification_evidence.items()
        },
        "normalized_subject_sha256": "",
        "claims_not_made": AUTHORITY_CLAIMS_NOT_MADE,
    }
    subject["normalized_subject_sha256"] = _digest(
        _canonical(
            {
                key: value
                for key, value in subject.items()
                if key != "normalized_subject_sha256"
            }
        )
    )
    subject_data = _canonical(subject) + b"\n"
    _write(root, authority_subject, subject_data)
    _write(
        root,
        authority_spec,
        _review("specification", authority_subject, subject_data, "spec-reviewer"),
    )
    _write(
        root,
        authority_quality,
        _review("code_quality", authority_subject, subject_data, "quality-reviewer"),
    )
    _git(
        root,
        "add",
        "--",
        migration,
        manifest,
        authority_subject,
        authority_spec,
        authority_quality,
        mechanism,
        mechanism_test,
        *verification_evidence.values(),
    )
    _git(root, "commit", "-qm", "migration authority")

    g11 = b'{"generation":11}\n'
    baseline_data = b'{"baseline":true}\n'
    attempt_payloads = {
        live_ledger: g11,
        g11_request: b'{"request":11}\n',
        g11_snapshot: g11,
        baseline: baseline_data,
        baseline_spec: _review(
            "specification",
            baseline,
            baseline_data,
            "baseline-spec-reviewer",
            subject_kind="implementation_failure_baseline",
        ),
        baseline_quality: _review(
            "code_quality",
            baseline,
            baseline_data,
            "baseline-quality-reviewer",
            subject_kind="implementation_failure_baseline",
        ),
        pending_request: b'{"request":"pending"}\n',
        pending_snapshot: b'{"pending":true}\n',
        pending_record: b'{"pending":true}\n',
    }
    for path, data in attempt_payloads.items():
        _write(root, path, data)
    for path in expected_paths:
        if path not in attempt_payloads:
            _write(root, path, f"payload for {path}\n".encode())

    return {
        "root": root,
        "source_root": source_root,
        "archive_root": archive_root,
        "governing_plan_path": governing,
        "migration_plan_path": migration,
        "authority_subject_path": authority_subject,
        "authority_specification_review_path": authority_spec,
        "authority_quality_review_path": authority_quality,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "expected_paths_manifest_path": manifest,
        "expected_paths": expected_paths,
        "protected_paths": protected,
        "generation5_request_path": g5_request,
        "generation5_snapshot_path": g5_snapshot,
        "generation11_request_path": g11_request,
        "generation11_snapshot_path": g11_snapshot,
        "live_ledger_path": live_ledger,
        "baseline_path": baseline,
        "baseline_specification_review_path": baseline_spec,
        "baseline_quality_review_path": baseline_quality,
        "pending_request_path": pending_request,
        "pending_snapshot_path": pending_snapshot,
        "pending_record_path": pending_record,
        "disposition_path": disposition,
        "disposition_specification_review_path": disposition_spec,
        "disposition_quality_review_path": disposition_quality,
        "post_report_path": post_report,
    }


@pytest.fixture
def migration_repository(tmp_path: Path) -> dict[str, object]:
    return _make_migration_repository(tmp_path)


def _retirement_fixture(name: str) -> dict[str, object]:
    path = Path("tests/fixtures/retirement_broad_evidence") / name
    return json.loads(path.read_text())


def _make_invalidated_adopted_repository(
    tmp_path: Path, *, controlled_predecessor: bool = False
) -> dict[str, object]:
    from orchestrator.retirement.broad_evidence import (
        build_broad_known_failure_baseline,
        build_broad_outcome,
        canonical_sha256,
        validate_bound_record,
        validate_record,
    )
    from orchestrator.retirement.source_bindings import capture_workspace_baseline
    from tests import test_retirement_broad_evidence as broad_fixtures

    root = tmp_path / "repository"
    root.mkdir()
    candidate, ledger = broad_fixtures._producer_candidate_and_ledger(root)
    source_root = "evidence"
    governing_plan_path = "plans/governing.md"
    migration_plan_path = "plans/correction.md"
    manifest_path = "authority/expected-paths.txt"
    workspace_baseline_path = (
        "evidence/implementation-baseline/workspace-baseline.json"
    )
    _write(root, governing_plan_path, b"governing plan\n")
    _write(root, migration_plan_path, b"corrective implementation plan\n")
    _git(root, "add", "--", governing_plan_path, migration_plan_path)
    _git(root, "commit", "-qm", "bind incident plans")
    workspace_baseline = capture_workspace_baseline(root)
    _write(root, workspace_baseline_path, _canonical(workspace_baseline) + b"\n")

    _write(root, "README.md", b"ordinary predecessor change\n")
    _git(root, "add", "--", "README.md")
    if controlled_predecessor:
        _git(
            root,
            "commit",
            "-qm",
            "controlled predecessor",
            "-m",
            "\n".join(
                [
                    "Retirement-Control-Schema: precommit_control.v1",
                    "Retirement-Transaction-ID: " + "3" * 64,
                    "Retirement-Control-SHA256: " + "4" * 64,
                ]
            ),
        )
    else:
        _git(root, "commit", "-qm", "ordinary predecessor")
    intended_predecessor_head = _git(root, "rev-parse", "HEAD").decode().strip()
    intended_predecessor_tree = _git(
        root, "rev-parse", "HEAD^{tree}"
    ).decode().strip()
    broad_fixtures._bind_candidate_to_repository(root, candidate)
    raw_paths = broad_fixtures._producer_raw_broad(root)
    snapshot_digest = canonical_sha256([])
    outcome = build_broad_outcome(
        repository_root=root,
        candidate_binding=candidate,
        execution_ledger_binding=ledger,
        collection_argv=["pytest", "--collect-only", "-q"],
        broad_argv=["pytest", "-q", "-rs", "-n", "16", "--dist=worksteal"],
        environment={
            "LC_ALL": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTEST_DEBUG_TEMPROOT": None,
        },
        run_root_snapshots=[
            {
                "root_path": (root / "runs").as_posix(),
                "root_path_sha256": canonical_sha256((root / "runs").as_posix()),
                "scope_basis": "planning_candidate",
                "before_snapshot_sha256": snapshot_digest,
                "after_snapshot_sha256": snapshot_digest,
            }
        ],
        **raw_paths,
    )
    outcome_path = broad_fixtures._write_producer_json(
        root, "evidence/implementation-baseline/outcome.json", outcome
    )
    ownership_classifications = [
        {
            "node_id": node_id,
            "ownership_class": "queue_owned",
            "ownership_basis": ["source.py"],
            "authorized_remediation_scope": ["source.py"],
        }
        for node_id in broad_fixtures._PRODUCER_FAILURE_NODE_IDS
    ]
    baseline = build_broad_known_failure_baseline(
        repository_root=root,
        broad_outcome_path=outcome_path.relative_to(root),
        ownership_classifications=ownership_classifications,
    )
    baseline_path = "evidence/implementation-baseline/known-failure-baseline.json"
    broad_fixtures._write_producer_json(root, baseline_path, baseline)
    specification_binding, quality_binding = (
        broad_fixtures._publish_producer_review_pair(
            root,
            evidence_root=Path(source_root),
            subject_path=Path(baseline_path),
            subject_kind="implementation_failure_baseline",
            specification_name="reviews/implementation-baseline-specification.json",
            quality_name="reviews/implementation-baseline-quality.json",
        )
    )

    pending = _retirement_fixture(
        "broad_failure_baseline_attestation.pending.v1.json"
    )
    pending["baseline_binding"] = {
        "path": baseline_path,
        "sha256": _digest((root / baseline_path).read_bytes()),
        "schema_version": "broad_known_failure_baseline.v1",
        "candidate_path_set_sha256": baseline["candidate_binding"][
            "candidate_path_set_sha256"
        ],
    }
    pending["failure_set_binding"] = {
        "failure_count": len(baseline["failures"]),
        "normalized_failure_set_sha256": baseline[
            "normalized_failure_set_sha256"
        ],
    }
    pending["normalization_binding"] = {
        "schema_version": baseline["failure_normalization"]["schema_version"],
        "normalized_contract_sha256": baseline["failure_normalization"][
            "normalized_contract_sha256"
        ],
    }
    pending["classification_summary"] = baseline["classification_summary"]
    pending["specification_review_binding"] = specification_binding
    pending["quality_review_binding"] = quality_binding
    assert validate_record(pending) == []
    assert validate_bound_record(pending, root) == []
    pending_data = _canonical(pending) + b"\n"
    pending_snapshot_path = (
        "evidence/attestations/pre-implementation/pending-snapshot.json"
    )
    owner_attestation_path = (
        "evidence/attestations/pre-implementation/broad-failure-baseline.json"
    )
    _write(root, pending_snapshot_path, pending_data)

    confirmed = deepcopy(pending)
    confirmed.update(
        {
            "evidence_status": "owner_confirmed",
            "owner": {"identity": "Fixture Owner", "role": "owner"},
            "owner_confirmations": {
                "classification_partition_confirmed": True,
                "comparison_only_confirmed": True,
                "confirmed_at": "2026-01-01T00:00:00+00:00",
                "exact_failure_table_confirmed": True,
                "no_out_of_scope_repair_confirmed": True,
                "normalization_contract_confirmed": True,
                "reviews_confirmed": True,
            },
            "owner_adoption": {
                "adopted_at": "2026-01-01T00:00:00+00:00",
                "identity": "Fixture Owner",
                "statement": (
                    "I personally adopt this exact baseline for comparison only."
                ),
            },
        }
    )
    assert validate_record(confirmed) == []
    assert validate_bound_record(confirmed, root) == []
    _write(root, owner_attestation_path, _canonical(confirmed) + b"\n")

    status = _git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--",
        source_root,
    )
    expected_paths = sorted(
        row[3:].decode("utf-8") for row in status.split(b"\0") if row
    )
    _write(root, manifest_path, ("\n".join(expected_paths) + "\n").encode())
    _git(root, "add", "--", manifest_path)
    _git(root, "commit", "-qm", "freeze invalidated attempt manifest")

    return {
        "root": root,
        "source_root": source_root,
        "governing_plan_path": governing_plan_path,
        "migration_plan_path": migration_plan_path,
        "expected_paths_manifest_path": manifest_path,
        "workspace_baseline_path": workspace_baseline_path,
        "owner_attestation_path": owner_attestation_path,
        "pending_attestation_snapshot_path": pending_snapshot_path,
        "known_failure_baseline_path": baseline_path,
        "intended_predecessor_head": intended_predecessor_head,
        "intended_predecessor_tree": intended_predecessor_tree,
        "expected_paths": expected_paths,
        "pending_attestation": pending,
        "confirmed_attestation": confirmed,
    }


def _build_incident(arguments: dict[str, object]) -> dict[str, object]:
    from orchestrator.retirement import attempt_migration

    builder = getattr(attempt_migration, "build_attempt_migration_incident")
    return builder(
        arguments["root"],
        governing_plan_path=arguments["governing_plan_path"],
        migration_plan_path=arguments["migration_plan_path"],
        workspace_baseline_path=arguments["workspace_baseline_path"],
        owner_attestation_path=arguments["owner_attestation_path"],
        pending_attestation_snapshot_path=arguments[
            "pending_attestation_snapshot_path"
        ],
        known_failure_baseline_path=arguments["known_failure_baseline_path"],
        expected_paths_manifest_path=arguments[
            "expected_paths_manifest_path"
        ],
        source_root=arguments["source_root"],
        intended_predecessor_head=arguments["intended_predecessor_head"],
    )


def _validate_incident(
    arguments: dict[str, object], record: dict[str, object]
) -> dict[str, object]:
    from orchestrator.retirement import attempt_migration

    validator = getattr(attempt_migration, "validate_attempt_migration_incident")
    return validator(arguments["root"], record)


def _capture(arguments: dict[str, object]) -> dict[str, object]:
    from orchestrator.retirement.attempt_migration import capture

    parameters = dict(arguments)
    root = parameters.pop("root")
    parameters.pop("expected_paths")
    parameters.pop("disposition_specification_review_path")
    parameters.pop("disposition_quality_review_path")
    parameters.pop("post_report_path")
    return capture(root, **parameters)


def _commit_disposition_reviews(
    arguments: dict[str, object],
    *,
    wrong_subject_digest: bool = False,
    commit_reviews: bool = True,
    subject_kind: str = "attempt_migration_disposition",
) -> None:
    root = arguments["root"]
    disposition_path = arguments["disposition_path"]
    specification_path = arguments["disposition_specification_review_path"]
    quality_path = arguments["disposition_quality_review_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    assert isinstance(specification_path, str)
    assert isinstance(quality_path, str)
    disposition_data = (root / disposition_path).read_bytes()
    subject_digest = "sha256:" + "0" * 64 if wrong_subject_digest else None
    _write(
        root,
        specification_path,
        _review(
            "specification",
            disposition_path,
            disposition_data,
            "disposition-spec-reviewer",
            subject_kind=subject_kind,
            subject_sha256=subject_digest,
        ),
    )
    _write(
        root,
        quality_path,
        _review(
            "code_quality",
            disposition_path,
            disposition_data,
            "disposition-quality-reviewer",
            subject_kind=subject_kind,
            subject_sha256=subject_digest,
        ),
    )
    _git(root, "add", "--", disposition_path)
    if commit_reviews:
        _git(root, "add", "--", specification_path, quality_path)
    _git(root, "commit", "-qm", "commit exact disposition authority")


def _rewrite_disposition(root: Path, path: str, record: dict[str, object]) -> None:
    record["normalized_disposition_sha256"] = _digest(
        _canonical(
            {
                key: value
                for key, value in record.items()
                if key != "normalized_disposition_sha256"
            }
        )
    )
    (root / path).write_bytes(_canonical(record) + b"\n")


def _mutate_disposition_nested_type(record: dict[str, object], mutation: str) -> None:
    attempt = record["attempt_binding"]
    row = record["attempt_rows"][0]
    state = record["pre_move_repository_state"]
    projection = state["status_projection"]
    status_row = projection["rows"][0]
    lineage = record["ledger_lineage"]
    if mutation == "attempt_source_commit":
        attempt["source_commit"] = {"not": "a commit"}
    elif mutation == "attempt_source_tree":
        attempt["source_tree"] = 7
    elif mutation == "attempt_source_root":
        attempt["source_root"] = []
    elif mutation == "attempt_archive_root":
        attempt["archive_root"] = 7
    elif mutation == "manifest_path":
        attempt["expected_paths_manifest_binding"]["path"] = []
    elif mutation == "manifest_count":
        attempt["expected_paths_manifest_binding"]["row_count"] = float(
            attempt["expected_paths_manifest_binding"]["row_count"]
        )
    elif mutation == "manifest_digest":
        attempt["expected_paths_manifest_binding"][
            "normalized_path_set_sha256"
        ] = 7
    elif mutation == "row_original_path":
        row["original_path"] = []
    elif mutation == "row_archive_path":
        row["archive_path"] = 7
    elif mutation == "row_tracked_state":
        row["tracked_state"] = []
    elif mutation == "row_file_type":
        row["file_type"] = 7
    elif mutation == "row_mode":
        row["lstat_mode"] = "0644"
    elif mutation == "row_mode_bool":
        row["lstat_mode"] = True
    elif mutation == "row_size":
        row["size"] = "1"
    elif mutation == "row_size_bool":
        row["size"] = True
    elif mutation == "row_digest":
        row["sha256"] = 7
    elif mutation == "attempt_count":
        record["attempt_path_count"] = float(record["attempt_path_count"])
    elif mutation == "attempt_path_digest":
        record["attempt_path_set_sha256"] = []
    elif mutation == "archive_path_digest":
        record["archive_path_set_sha256"] = {}
    elif mutation == "row_set_digest":
        record["normalized_row_set_sha256"] = 7
    elif mutation == "authority_binding":
        record["authority_review_bindings"]["specification"] = []
    elif mutation == "artifact_binding":
        attempt["artifact_bindings"]["baseline"] = []
    elif mutation == "generation5_binding":
        lineage["generation_5"]["request_binding"] = []
    elif mutation == "generation5_value":
        lineage["generation_5"]["generation"] = 5.0
    elif mutation == "generation5_value_bool":
        lineage["generation_5"]["generation"] = True
    elif mutation == "generation11_value":
        lineage["generation_11"]["generation"] = 11.0
    elif mutation == "generation11_value_bool":
        lineage["generation_11"]["generation"] = True
    elif mutation == "restoration_source_path":
        lineage["restoration_binding"]["source_path"] = []
    elif mutation == "restoration_target_path":
        lineage["restoration_binding"]["target_path"] = 7
    elif mutation == "restoration_source_commit":
        lineage["restoration_binding"]["source_commit"] = []
    elif mutation == "state_head":
        state["head"] = 7
    elif mutation == "state_tree":
        state["tree"] = {}
    elif mutation == "state_index_digest":
        state["index_sha256"] = 7
    elif mutation == "status_rows":
        projection["rows"] = {}
    elif mutation == "status_count":
        projection["row_count"] = float(projection["row_count"])
    elif mutation == "status_digest":
        projection["normalized_rows_sha256"] = 7
    elif mutation == "status_row":
        projection["rows"][0] = []
    elif mutation == "status_path":
        status_row["path"] = 7
    elif mutation == "status_source_path":
        status_row["source_path"] = []
    elif mutation == "status_code":
        status_row["status"] = 7
    elif mutation == "protected_binding":
        record["protected_path_bindings"][0] = []
    else:  # pragma: no cover - parameter table is closed below
        raise AssertionError(mutation)
    if mutation in {"status_row", "status_path", "status_source_path", "status_code"}:
        projection["normalized_rows_sha256"] = _digest(
            _canonical(projection["rows"])
        )


def _migration_path_states(
    root: Path, record: dict[str, object]
) -> dict[str, tuple[bytes, int] | None]:
    paths = {
        *[row["original_path"] for row in record["attempt_rows"]],
        *[row["archive_path"] for row in record["attempt_rows"]],
    }
    states: dict[str, tuple[bytes, int] | None] = {}
    for path in paths:
        candidate = root / path
        states[path] = (
            (candidate.read_bytes(), stat.S_IMODE(candidate.stat().st_mode))
            if candidate.exists()
            else None
        )
    return states


def _commit_rewritten_authority_subject(
    arguments: dict[str, object], subject: dict[str, object]
) -> None:
    root = arguments["root"]
    subject_path = arguments["authority_subject_path"]
    assert isinstance(root, Path)
    assert isinstance(subject_path, str)
    subject["normalized_subject_sha256"] = _digest(
        _canonical(
            {
                key: value
                for key, value in subject.items()
                if key != "normalized_subject_sha256"
            }
        )
    )
    subject_data = _canonical(subject) + b"\n"
    _write(root, subject_path, subject_data)
    review_paths = [
        arguments["authority_specification_review_path"],
        arguments["authority_quality_review_path"],
    ]
    for review_path in review_paths:
        review = json.loads((root / review_path).read_text())
        review["subject"]["sha256"] = _digest(subject_data)
        (root / review_path).write_bytes(_canonical(review) + b"\n")
    _git(root, "add", "--", subject_path, *review_paths)
    _git(root, "commit", "-qm", "rewrite authority subject")


def _apply_real_nonexecutive_modes(arguments: dict[str, object]) -> None:
    root = arguments["root"]
    subject_path = arguments["authority_subject_path"]
    assert isinstance(root, Path)
    assert isinstance(subject_path, str)
    subject = json.loads((root / subject_path).read_text())
    full_bindings = [
        subject["mechanism_binding"],
        subject["test_binding"],
        *subject["evidence_bindings"].values(),
    ]
    for binding in full_bindings:
        os.chmod(root / binding["path"], 0o664)
        binding["lstat_mode"] = 0o664
    _commit_rewritten_authority_subject(arguments, subject)

    authority_paths = {
        arguments["governing_plan_path"],
        arguments["migration_plan_path"],
        arguments["expected_paths_manifest_path"],
        subject_path,
        arguments["authority_specification_review_path"],
        arguments["authority_quality_review_path"],
        *(binding["path"] for binding in full_bindings),
    }
    for authority_path in authority_paths:
        os.chmod(root / authority_path, 0o664)
    for key in (
        "generation5_request_path",
        "generation5_snapshot_path",
        "live_ledger_path",
    ):
        os.chmod(root / arguments[key], 0o600)


def test_capture_writes_a_closed_canonical_disposition_and_validate_reopens_it(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import validate

    record = _capture(migration_repository)
    root = migration_repository["root"]
    assert isinstance(root, Path)
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(disposition_path, str)

    assert set(record) == {
        "schema_version",
        "disposition",
        "governing_plan_binding",
        "migration_plan_binding",
        "authority_review_bindings",
        "attempt_binding",
        "pre_move_repository_state",
        "protected_path_bindings",
        "ledger_lineage",
        "attempt_rows",
        "attempt_path_count",
        "attempt_path_set_sha256",
        "archive_path_set_sha256",
        "normalized_row_set_sha256",
        "normalized_disposition_sha256",
        "claims_not_made",
    }
    assert record["schema_version"] == "attempt_migration_disposition.v1"
    assert record["attempt_path_count"] == len(migration_repository["expected_paths"])
    assert [row["original_path"] for row in record["attempt_rows"]] == migration_repository[
        "expected_paths"
    ]
    assert (root / disposition_path).read_bytes() == _canonical(record) + b"\n"
    assert validate(root, disposition_path) == record
    assert stat.S_IMODE((root / disposition_path).stat().st_mode) == 0o644


def test_capture_rejects_authority_reviews_with_the_wrong_subject_kind(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    assert isinstance(root, Path)
    review_paths = [
        migration_repository["authority_specification_review_path"],
        migration_repository["authority_quality_review_path"],
    ]
    for review_path in review_paths:
        review = json.loads((root / review_path).read_text())
        review["subject"]["kind"] = "different_authority_kind"
        (root / review_path).write_bytes(_canonical(review) + b"\n")
    _git(root, "add", "--", *review_paths)
    _git(root, "commit", "-qm", "change authority review subject kind")

    with pytest.raises(AttemptMigrationError, match="review_subject_kind_mismatch"):
        _capture(migration_repository)


def test_capture_rejects_closed_authority_subject_drift(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    subject_path = migration_repository["authority_subject_path"]
    assert isinstance(root, Path)
    assert isinstance(subject_path, str)
    subject = json.loads((root / subject_path).read_text())
    subject["unexpected"] = True
    _commit_rewritten_authority_subject(migration_repository, subject)

    with pytest.raises(AttemptMigrationError, match="authority_subject_keys_mismatch"):
        _capture(migration_repository)


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("missing", "authority_subject_evidence_roles_invalid"),
        ("extra", "authority_subject_evidence_roles_invalid"),
        ("renamed", "authority_subject_evidence_roles_invalid"),
        ("one_arbitrary", "authority_subject_evidence_roles_invalid"),
        ("duplicate_paths", "authority_subject_binding_path_duplicate"),
        ("not_full", "file_binding_keys_mismatch"),
    ],
)
def test_capture_rejects_incomplete_authority_evidence_role_maps(
    migration_repository: dict[str, object], mutation: str, error: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    subject_path = migration_repository["authority_subject_path"]
    assert isinstance(root, Path)
    assert isinstance(subject_path, str)
    subject = json.loads((root / subject_path).read_text())
    evidence = subject["evidence_bindings"]
    if mutation == "missing":
        evidence.pop("broad_test_evidence")
    elif mutation == "extra":
        evidence["unexpected_role"] = dict(evidence["broad_test_evidence"])
    elif mutation == "renamed":
        evidence["broad_evidence"] = evidence.pop("broad_test_evidence")
    elif mutation == "one_arbitrary":
        subject["evidence_bindings"] = {
            "arbitrary": dict(subject["mechanism_binding"])
        }
    elif mutation == "duplicate_paths":
        for role in list(evidence):
            evidence[role] = dict(subject["mechanism_binding"])
    else:
        evidence["focused_test_evidence"].pop("lstat_mode")
    _commit_rewritten_authority_subject(migration_repository, subject)

    with pytest.raises(AttemptMigrationError, match=error):
        _capture(migration_repository)


@pytest.mark.parametrize(
    "alias_target",
    [
        "governing_plan_binding",
        "migration_plan_binding",
        "expected_paths_manifest_binding",
        "protected_path_binding",
        "mechanism_binding",
        "test_binding",
    ],
)
def test_capture_rejects_evidence_aliasing_any_other_authority_role(
    migration_repository: dict[str, object], alias_target: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    subject_path = migration_repository["authority_subject_path"]
    assert isinstance(root, Path)
    assert isinstance(subject_path, str)
    subject = json.loads((root / subject_path).read_text())
    if alias_target == "protected_path_binding":
        target_binding = subject["protected_path_bindings"][0]
    else:
        target_binding = subject[alias_target]
    subject["evidence_bindings"]["candidate_manifest"] = _file_binding(
        root, target_binding["path"], full=True
    )
    _commit_rewritten_authority_subject(migration_repository, subject)

    with pytest.raises(
        AttemptMigrationError, match="authority_subject_binding_path_duplicate"
    ):
        _capture(migration_repository)


@pytest.mark.parametrize("reverse_role", ["mechanism_binding", "test_binding"])
def test_capture_rejects_an_authority_role_aliasing_an_evidence_path(
    migration_repository: dict[str, object], reverse_role: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    subject_path = migration_repository["authority_subject_path"]
    assert isinstance(root, Path)
    assert isinstance(subject_path, str)
    subject = json.loads((root / subject_path).read_text())
    subject[reverse_role] = dict(
        subject["evidence_bindings"]["candidate_manifest"]
    )
    _commit_rewritten_authority_subject(migration_repository, subject)

    with pytest.raises(
        AttemptMigrationError, match="authority_subject_binding_path_duplicate"
    ):
        _capture(migration_repository)


def test_capture_reopens_each_committed_authority_evidence_binding(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    subject_path = migration_repository["authority_subject_path"]
    assert isinstance(root, Path)
    assert isinstance(subject_path, str)
    subject = json.loads((root / subject_path).read_text())
    evidence_path = subject["evidence_bindings"]["broad_test_evidence"]["path"]
    _write(root, evidence_path, b"different committed broad evidence\n")
    _git(root, "add", "--", evidence_path)
    _git(root, "commit", "-qm", "change bound broad evidence")

    with pytest.raises(AttemptMigrationError, match="authority_subject_bound_file_mismatch"):
        _capture(migration_repository)


def test_capture_accepts_nonexecutive_committed_permission_variants(
    migration_repository: dict[str, object],
) -> None:
    root = migration_repository["root"]
    subject_path = migration_repository["authority_subject_path"]
    assert isinstance(root, Path)
    assert isinstance(subject_path, str)
    _apply_real_nonexecutive_modes(migration_repository)

    record = _capture(migration_repository)

    assert stat.S_IMODE((root / subject_path).stat().st_mode) == 0o664
    assert record["ledger_lineage"]["generation_5"]["request_binding"][
        "lstat_mode"
    ] == 0o600
    assert record["ledger_lineage"]["generation_5"]["snapshot_binding"][
        "lstat_mode"
    ] == 0o600
    assert record["ledger_lineage"]["generation_11"]["live_binding"][
        "lstat_mode"
    ] == 0o600
    assert record["ledger_lineage"]["restoration_binding"]["lstat_mode"] == 0o600


@pytest.mark.parametrize("mismatch", ["committed_live", "restoration_source"])
def test_capture_rejects_executable_class_mismatches(
    migration_repository: dict[str, object], mismatch: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    assert isinstance(root, Path)
    if mismatch == "committed_live":
        path = migration_repository["governing_plan_path"]
        error = "committed_mode_mismatch"
        os.chmod(root / path, 0o755)
    else:
        path = migration_repository["generation5_snapshot_path"]
        error = "restoration_mode_mismatch"
        os.chmod(root / path, 0o755)
        _git(root, "add", "--", path)
        _git(root, "commit", "-qm", "make restoration snapshot executable")

    with pytest.raises(AttemptMigrationError, match=error):
        _capture(migration_repository)


@pytest.mark.parametrize(
    ("alias_role", "target_role"),
    [
        ("generation5_request_path", "generation5_snapshot_path"),
        ("generation11_request_path", "pending_request_path"),
        ("generation11_snapshot_path", "live_ledger_path"),
        ("pending_snapshot_path", "pending_record_path"),
    ],
)
def test_capture_rejects_semantic_coordinate_aliases(
    migration_repository: dict[str, object], alias_role: str, target_role: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    migration_repository[alias_role] = migration_repository[target_role]

    with pytest.raises(AttemptMigrationError, match="semantic_coordinate_alias"):
        _capture(migration_repository)


@pytest.mark.parametrize(
    "alias_role",
    [
        "generation5_snapshot",
        "generation11_request",
        "generation11_snapshot",
        "generation11_live",
        "baseline",
        "baseline_specification_review",
        "baseline_quality_review",
        "pending_request",
        "pending_snapshot",
        "pending_record",
    ],
)
def test_validate_rejects_redigested_semantic_coordinate_alias_drift(
    migration_repository: dict[str, object], alias_role: str
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    record = _capture(migration_repository)
    anchor = dict(
        record["ledger_lineage"]["generation_5"]["request_binding"]
    )
    if alias_role == "generation5_snapshot":
        record["ledger_lineage"]["generation_5"]["snapshot_binding"] = anchor
    elif alias_role.startswith("generation11_"):
        binding_name = alias_role.removeprefix("generation11_") + "_binding"
        record["ledger_lineage"]["generation_11"][binding_name] = anchor
    else:
        record["attempt_binding"]["artifact_bindings"][alias_role] = anchor
    _rewrite_disposition(root, disposition_path, record)

    with pytest.raises(AttemptMigrationError, match="semantic_coordinate_alias"):
        validate(root, disposition_path)


@pytest.mark.parametrize(
    "role",
    [
        "generation11_request",
        "generation11_snapshot",
        "generation11_live",
        "baseline",
        "baseline_specification_review",
        "baseline_quality_review",
        "pending_request",
        "pending_snapshot",
        "pending_record",
    ],
)
def test_validate_rejects_semantic_bindings_not_exactly_cross_linked_to_rows(
    migration_repository: dict[str, object], role: str
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    record = _capture(migration_repository)
    if role.startswith("generation11_"):
        binding_name = role.removeprefix("generation11_") + "_binding"
        binding = record["ledger_lineage"]["generation_11"][binding_name]
    else:
        binding = record["attempt_binding"]["artifact_bindings"][role]
    binding["size"] += 1
    _rewrite_disposition(root, disposition_path, record)

    with pytest.raises(
        AttemptMigrationError, match="semantic_coordinate_row_binding_mismatch"
    ):
        validate(root, disposition_path)


@pytest.mark.parametrize(
    ("restoration_field", "alias_binding"),
    [
        ("source_path", "request_binding"),
        ("target_path", "snapshot_binding"),
    ],
)
def test_validate_rejects_restoration_aliases_outside_the_two_permitted_roles(
    migration_repository: dict[str, object],
    restoration_field: str,
    alias_binding: str,
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    record = _capture(migration_repository)
    generation = (
        "generation_5" if restoration_field == "source_path" else "generation_11"
    )
    record["ledger_lineage"]["restoration_binding"][restoration_field] = record[
        "ledger_lineage"
    ][generation][alias_binding]["path"]
    _rewrite_disposition(root, disposition_path, record)

    with pytest.raises(
        AttemptMigrationError, match="semantic_restoration_coordinate_mismatch"
    ):
        validate(root, disposition_path)


@pytest.mark.parametrize(
    ("mismatch", "error"),
    [
        ("generation11_snapshot_live", "generation11_snapshot_live_mismatch"),
        ("pending_snapshot_record", "pending_snapshot_record_mismatch"),
    ],
)
def test_capture_rejects_semantic_content_metadata_mismatches(
    migration_repository: dict[str, object], mismatch: str, error: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    assert isinstance(root, Path)
    path = migration_repository[
        "generation11_snapshot_path"
        if mismatch == "generation11_snapshot_live"
        else "pending_snapshot_path"
    ]
    _write(root, path, b'{"different":true}\n')

    with pytest.raises(AttemptMigrationError, match=error):
        _capture(migration_repository)


@pytest.mark.parametrize(
    ("mismatch", "error"),
    [
        ("generation11_snapshot_live", "generation11_snapshot_live_mismatch"),
        ("pending_snapshot_record", "pending_snapshot_record_mismatch"),
        ("restoration_generation5", "semantic_restoration_metadata_mismatch"),
    ],
)
def test_validate_rejects_redigested_semantic_content_metadata_drift(
    migration_repository: dict[str, object], mismatch: str, error: str
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    record = _capture(migration_repository)
    if mismatch == "restoration_generation5":
        record["ledger_lineage"]["restoration_binding"]["size"] += 1
    else:
        role = (
            "generation11_snapshot"
            if mismatch == "generation11_snapshot_live"
            else "pending_snapshot"
        )
        row_path = (
            record["ledger_lineage"]["generation_11"]["snapshot_binding"]["path"]
            if role == "generation11_snapshot"
            else record["attempt_binding"]["artifact_bindings"][role]["path"]
        )
        row = next(
            item for item in record["attempt_rows"] if item["original_path"] == row_path
        )
        row["size"] += 1
        if role == "generation11_snapshot":
            record["ledger_lineage"]["generation_11"]["snapshot_binding"][
                "size"
            ] += 1
        else:
            record["attempt_binding"]["artifact_bindings"][role]["size"] += 1
        record["normalized_row_set_sha256"] = _digest(
            _canonical(record["attempt_rows"])
        )
    _rewrite_disposition(root, disposition_path, record)

    with pytest.raises(AttemptMigrationError, match=error):
        validate(root, disposition_path)


@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_capture_rejects_an_extra_or_missing_source_path(
    migration_repository: dict[str, object], mutation: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    source_root = migration_repository["source_root"]
    expected_paths = migration_repository["expected_paths"]
    assert isinstance(root, Path)
    assert isinstance(source_root, str)
    assert isinstance(expected_paths, list)
    if mutation == "extra":
        _write(root, f"{source_root}/unexpected.json", b"{}\n")
    else:
        (root / expected_paths[-1]).unlink()

    with pytest.raises(AttemptMigrationError, match="source_set_mismatch"):
        _capture(migration_repository)


@pytest.mark.parametrize("direction", ["source_to_outside", "outside_to_source"])
def test_capture_rejects_cross_boundary_status_rows_before_publication(
    migration_repository: dict[str, object], direction: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    live_path = migration_repository["live_ledger_path"]
    protected_path = migration_repository["protected_paths"][0]
    source_root = migration_repository["source_root"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    if direction == "source_to_outside":
        source, destination = live_path, "outside/capture-moved-live.json"
    else:
        source, destination = protected_path, f"{source_root}/capture-moved-in.json"
    (root / destination).parent.mkdir(parents=True, exist_ok=True)
    _git(root, "mv", "--", source, destination)

    with pytest.raises(
        AttemptMigrationError, match="status_projection_boundary_crossing"
    ):
        _capture(migration_repository)

    assert not (root / disposition_path).exists()


@pytest.mark.parametrize("mutation", ["bytes", "mode"])
def test_validate_rejects_attempt_byte_or_mode_drift(
    migration_repository: dict[str, object], mutation: str
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    _capture(migration_repository)
    root = migration_repository["root"]
    baseline_path = migration_repository["baseline_path"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(baseline_path, str)
    assert isinstance(disposition_path, str)
    if mutation == "bytes":
        (root / baseline_path).write_bytes(b"changed\n")
    else:
        (root / baseline_path).chmod(0o600)

    with pytest.raises(AttemptMigrationError, match="attempt_row_state_invalid"):
        validate(root, disposition_path)


def test_validate_rejects_protected_byte_drift_even_when_git_status_is_unchanged(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    _capture(migration_repository)
    root = migration_repository["root"]
    protected_path = migration_repository["protected_paths"][0]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(protected_path, str)
    assert isinstance(disposition_path, str)
    status_before = _git(root, "status", "--porcelain=v1", "--", protected_path)
    _write(root, protected_path, b"different dirty bytes\n", 0o640)
    status_after = _git(root, "status", "--porcelain=v1", "--", protected_path)
    assert status_after == status_before

    with pytest.raises(AttemptMigrationError, match="protected_path_changed"):
        validate(root, disposition_path)


def test_capture_rejects_restoration_bytes_that_do_not_match_the_source_commit(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    snapshot_path = migration_repository["generation5_snapshot_path"]
    assert isinstance(root, Path)
    assert isinstance(snapshot_path, str)
    _write(root, snapshot_path, b'{"generation":"not-five"}\n')
    _git(root, "add", "--", snapshot_path)
    _git(root, "commit", "-qm", "alter restoration snapshot")

    with pytest.raises(AttemptMigrationError, match="restoration_bytes_mismatch"):
        _capture(migration_repository)


def test_validate_reopens_restoration_source_commit_executable_class(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    root = migration_repository["root"]
    source_commit = migration_repository["source_commit"]
    live_path = migration_repository["live_ledger_path"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(source_commit, str)
    assert isinstance(live_path, str)
    assert isinstance(disposition_path, str)
    alternate_index = root.parent / "alternate-source.index"
    _git_with_index(root, alternate_index, "read-tree", source_commit)
    source_blob = _git(root, "rev-parse", f"{source_commit}:{live_path}").decode().strip()
    _git_with_index(
        root,
        alternate_index,
        "update-index",
        "--cacheinfo",
        f"100755,{source_blob},{live_path}",
    )
    alternate_tree = _git_with_index(root, alternate_index, "write-tree").decode().strip()
    alternate_commit = _git(
        root,
        "commit-tree",
        alternate_tree,
        "-p",
        source_commit,
        "-m",
        "alternate executable source",
    ).decode().strip()
    current_head = _git(root, "rev-parse", "HEAD").decode().strip()
    current_tree = _git(root, "rev-parse", "HEAD^{tree}").decode().strip()
    merge_head = _git(
        root,
        "commit-tree",
        current_tree,
        "-p",
        current_head,
        "-p",
        alternate_commit,
        "-m",
        "bind alternate source ancestry",
    ).decode().strip()
    _git(root, "update-ref", "HEAD", merge_head, current_head)

    record = _capture(migration_repository)
    record["attempt_binding"]["source_commit"] = alternate_commit
    record["attempt_binding"]["source_tree"] = alternate_tree
    restoration = record["ledger_lineage"]["restoration_binding"]
    restoration["source_commit"] = alternate_commit
    restoration["source_tree"] = alternate_tree
    _rewrite_disposition(root, disposition_path, record)

    with pytest.raises(AttemptMigrationError, match="restoration_mode_mismatch"):
        validate(root, disposition_path)


def test_capture_rejects_a_source_commit_outside_the_capture_head_lineage(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    source_tree = migration_repository["source_tree"]
    assert isinstance(root, Path)
    assert isinstance(source_tree, str)
    unrelated_commit = _git(
        root, "commit-tree", source_tree, "-m", "unrelated source commit"
    ).decode().strip()
    arguments = dict(migration_repository)
    arguments["source_commit"] = unrelated_commit

    with pytest.raises(AttemptMigrationError, match="source_commit_not_ancestor"):
        _capture(arguments)


@pytest.mark.parametrize("field", ["source_commit", "source_tree"])
def test_capture_rejects_non_string_source_identities_without_raw_exceptions(
    migration_repository: dict[str, object], field: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    migration_repository[field] = 7

    with pytest.raises(AttemptMigrationError, match="source_identity_invalid"):
        _capture(migration_repository)


def test_capture_rejects_a_non_approved_attempt_review_pair(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    review_path = migration_repository["baseline_specification_review_path"]
    assert isinstance(root, Path)
    assert isinstance(review_path, str)
    review = json.loads((root / review_path).read_text())
    review["result"] = "rejected"
    review["issues"] = [
        {"code": "not-approved", "message": "not approved", "path": "$"}
    ]
    (root / review_path).write_bytes(_canonical(review) + b"\n")

    with pytest.raises(AttemptMigrationError, match="review_not_approved"):
        _capture(migration_repository)


def test_capture_rejects_a_non_string_bound_review_kind_without_raw_exceptions(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    review_path = migration_repository["baseline_specification_review_path"]
    assert isinstance(root, Path)
    assert isinstance(review_path, str)
    review = json.loads((root / review_path).read_text())
    review["review_kind"] = []
    (root / review_path).write_bytes(_canonical(review) + b"\n")

    with pytest.raises(AttemptMigrationError, match="review_kind_invalid"):
        _capture(migration_repository)


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("role_swap", "review_pair_order_invalid"),
        ("unrelated_reviews", "review_subject_path_mismatch"),
    ],
)
def test_validate_reopens_baseline_review_semantics_from_bound_attempt_rows(
    migration_repository: dict[str, object], mutation: str, error: str
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    record = _capture(migration_repository)
    artifacts = record["attempt_binding"]["artifact_bindings"]
    if mutation == "role_swap":
        artifacts["baseline_specification_review"], artifacts[
            "baseline_quality_review"
        ] = (
            artifacts["baseline_quality_review"],
            artifacts["baseline_specification_review"],
        )
    else:
        unrelated = b'{"unrelated":true}\n'
        for role, kind, reviewer in (
            ("baseline_specification_review", "specification", "unrelated-spec"),
            ("baseline_quality_review", "code_quality", "unrelated-quality"),
        ):
            binding = artifacts[role]
            data = _review(
                kind,
                "unrelated/baseline.json",
                unrelated,
                reviewer,
                subject_kind="implementation_failure_baseline",
            )
            _write(root, binding["path"], data, binding["lstat_mode"])
            row = next(
                item
                for item in record["attempt_rows"]
                if item["original_path"] == binding["path"]
            )
            row["size"] = len(data)
            row["sha256"] = _digest(data)
            binding["size"] = len(data)
            binding["sha256"] = _digest(data)
        record["normalized_row_set_sha256"] = _digest(
            _canonical(record["attempt_rows"])
        )
    _rewrite_disposition(root, disposition_path, record)

    with pytest.raises(AttemptMigrationError, match=error):
        validate(root, disposition_path)


def test_validate_reopens_baseline_review_pair_from_full_archive_post_state(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import apply, validate

    _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    apply(
        root,
        disposition_path,
        migration_repository["disposition_specification_review_path"],
        migration_repository["disposition_quality_review_path"],
    )

    validate(root, disposition_path)


def test_capture_requires_an_empty_archive_destination(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    archive_root = migration_repository["archive_root"]
    baseline_path = migration_repository["baseline_path"]
    assert isinstance(root, Path)
    assert isinstance(archive_root, str)
    assert isinstance(baseline_path, str)
    archive_path = f"{archive_root}/{baseline_path}"
    _write(root, archive_path, (root / baseline_path).read_bytes())

    with pytest.raises(AttemptMigrationError, match="archive_not_empty"):
        _capture(migration_repository)


def test_capture_requires_protected_paths_to_cover_every_outside_status_operand(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    arguments = dict(migration_repository)
    arguments["protected_paths"] = []

    with pytest.raises(AttemptMigrationError, match="protected_status_coverage_mismatch"):
        _capture(arguments)


def test_capture_rejects_an_unprotected_outside_status_operand(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    assert isinstance(root, Path)
    _write(root, "outside/unbound.txt", b"unbound\n")

    with pytest.raises(AttemptMigrationError, match="protected_status_coverage_mismatch"):
        _capture(migration_repository)


@pytest.mark.parametrize("location", ["source", "archive", "original"])
def test_capture_rejects_an_output_path_inside_the_migration_sets_before_publication(
    migration_repository: dict[str, object], location: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    root = migration_repository["root"]
    assert isinstance(root, Path)
    if location == "source":
        output_path = f"{migration_repository['source_root']}/generated-disposition.json"
    elif location == "archive":
        output_path = f"{migration_repository['archive_root']}/generated-disposition.json"
    else:
        output_path = migration_repository["expected_paths"][0]
    arguments = dict(migration_repository)
    arguments["disposition_path"] = output_path
    existed_before = (root / output_path).exists()

    with pytest.raises(AttemptMigrationError, match="output_path_overlaps_migration"):
        _capture(arguments)
    assert (root / output_path).exists() is existed_before


@pytest.mark.parametrize("location", ["source", "archive", "original"])
def test_postvalidate_rejects_an_output_path_inside_the_migration_sets_before_publication(
    migration_repository: dict[str, object], location: str
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        apply,
        postvalidate,
    )

    record = _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    root = migration_repository["root"]
    assert isinstance(root, Path)
    apply(
        root,
        migration_repository["disposition_path"],
        migration_repository["disposition_specification_review_path"],
        migration_repository["disposition_quality_review_path"],
    )
    if location == "source":
        report_path = f"{migration_repository['source_root']}/generated-report.json"
    elif location == "archive":
        report_path = f"{migration_repository['archive_root']}/generated-report.json"
    else:
        report_path = record["attempt_rows"][0]["original_path"]
    assert not (root / report_path).exists()

    with pytest.raises(AttemptMigrationError, match="output_path_overlaps_migration"):
        postvalidate(
            root,
            migration_repository["disposition_path"],
            migration_repository["disposition_specification_review_path"],
            migration_repository["disposition_quality_review_path"],
            report_path,
        )
    assert not (root / report_path).exists()


def test_apply_archives_exact_bytes_restores_the_tracked_file_and_replays(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import apply, postvalidate

    record = _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    specification_path = migration_repository["disposition_specification_review_path"]
    quality_path = migration_repository["disposition_quality_review_path"]
    report_path = migration_repository["post_report_path"]
    snapshot_path = migration_repository["generation5_snapshot_path"]
    live_path = migration_repository["live_ledger_path"]
    assert isinstance(root, Path)
    assert all(
        isinstance(value, str)
        for value in (
            disposition_path,
            specification_path,
            quality_path,
            report_path,
            snapshot_path,
            live_path,
        )
    )

    apply(root, disposition_path, specification_path, quality_path)
    for row in record["attempt_rows"]:
        archive = root / row["archive_path"]
        assert archive.is_file()
        assert _digest(archive.read_bytes()) == row["sha256"]
        assert stat.S_IMODE(archive.stat().st_mode) == row["lstat_mode"]
        if row["tracked_state"] == "untracked":
            assert not (root / row["original_path"]).exists()
    assert (root / live_path).read_bytes() == (root / snapshot_path).read_bytes()

    # A complete post-state is a valid no-op replay.
    apply(root, disposition_path, specification_path, quality_path)
    report = postvalidate(
        root, disposition_path, specification_path, quality_path, report_path
    )
    assert report["schema_version"] == "attempt_migration_post_report.v1"
    assert report["result"] == "passed"
    assert (root / report_path).read_bytes() == _canonical(report) + b"\n"
    assert (
        postvalidate(root, disposition_path, specification_path, quality_path, report_path)
        == report
    )


def test_apply_resumes_when_an_identical_archive_was_published_before_the_source_move(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import apply

    record = _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    root = migration_repository["root"]
    assert isinstance(root, Path)
    row = next(row for row in record["attempt_rows"] if row["tracked_state"] == "untracked")
    archive = root / row["archive_path"]
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes((root / row["original_path"]).read_bytes())
    archive.chmod(row["lstat_mode"])

    apply(
        root,
        migration_repository["disposition_path"],
        migration_repository["disposition_specification_review_path"],
        migration_repository["disposition_quality_review_path"],
    )
    assert archive.is_file()
    assert not (root / row["original_path"]).exists()


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("add", "outside_status_projection_changed"),
        ("remove", "protected_path_changed"),
        ("status", "outside_status_projection_changed"),
        ("cross_boundary_rename_out", "status_projection_boundary_crossing"),
        ("cross_boundary_rename_in", "archive_binding_mismatch"),
    ],
)
def test_apply_rejects_late_outside_status_drift_before_migration_mutation(
    migration_repository: dict[str, object], mutation: str, error: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError, apply

    record = _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    root = migration_repository["root"]
    protected_path = migration_repository["protected_paths"][0]
    live_path = migration_repository["live_ledger_path"]
    assert isinstance(root, Path)
    assert isinstance(protected_path, str)
    assert isinstance(live_path, str)
    if mutation == "add":
        _write(root, "outside/late-add.txt", b"late\n")
    elif mutation == "remove":
        (root / protected_path).unlink()
    elif mutation == "status":
        _git(root, "add", "--", protected_path)
    elif mutation == "cross_boundary_rename_out":
        destination = "outside/moved-live.json"
        (root / destination).parent.mkdir(parents=True, exist_ok=True)
        _git(root, "mv", "--", live_path, destination)
    else:
        destination = record["attempt_rows"][0]["archive_path"]
        (root / destination).parent.mkdir(parents=True, exist_ok=True)
        _git(root, "mv", "--", protected_path, destination)
    before = _migration_path_states(root, record)

    with pytest.raises(AttemptMigrationError, match=error):
        apply(
            root,
            migration_repository["disposition_path"],
            migration_repository["disposition_specification_review_path"],
            migration_repository["disposition_quality_review_path"],
        )

    assert _migration_path_states(root, record) == before


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("untracked_source_add", "migration_index_classification_changed"),
        ("modified_source_add", "migration_index_classification_changed"),
        ("archive_add", "migration_index_classification_changed"),
        ("internal_rename", "status_projection_boundary_crossing"),
    ],
)
def test_apply_rejects_staged_migration_classification_before_mutation(
    migration_repository: dict[str, object], mutation: str, error: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError, apply

    record = _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    root = migration_repository["root"]
    assert isinstance(root, Path)
    untracked = next(
        row for row in record["attempt_rows"] if row["tracked_state"] == "untracked"
    )
    modified = next(
        row for row in record["attempt_rows"] if row["tracked_state"] == "modified"
    )
    if mutation == "untracked_source_add":
        _git(root, "add", "--", untracked["original_path"])
    elif mutation == "modified_source_add":
        _git(root, "add", "--", modified["original_path"])
    elif mutation == "archive_add":
        _write(
            root,
            untracked["archive_path"],
            (root / untracked["original_path"]).read_bytes(),
            untracked["lstat_mode"],
        )
        _git(root, "add", "--", untracked["archive_path"])
    else:
        (root / modified["archive_path"]).parent.mkdir(parents=True, exist_ok=True)
        _git(root, "mv", "--", modified["original_path"], modified["archive_path"])
    before = _migration_path_states(root, record)

    with pytest.raises(AttemptMigrationError, match=error):
        apply(
            root,
            migration_repository["disposition_path"],
            migration_repository["disposition_specification_review_path"],
            migration_repository["disposition_quality_review_path"],
        )

    assert _migration_path_states(root, record) == before


def test_apply_rejects_a_committed_archive_before_the_full_post_state(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError, apply

    record = _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    root = migration_repository["root"]
    assert isinstance(root, Path)
    row = next(
        item for item in record["attempt_rows"] if item["tracked_state"] == "untracked"
    )
    _write(
        root,
        row["archive_path"],
        (root / row["original_path"]).read_bytes(),
        row["lstat_mode"],
    )
    _git(root, "add", "--", row["archive_path"])
    _git(root, "commit", "-qm", "commit one archive before migration completion")
    before = _migration_path_states(root, record)

    with pytest.raises(
        AttemptMigrationError, match="migration_index_classification_changed"
    ):
        apply(
            root,
            migration_repository["disposition_path"],
            migration_repository["disposition_specification_review_path"],
            migration_repository["disposition_quality_review_path"],
        )

    assert _migration_path_states(root, record) == before


def test_apply_rejects_modified_source_committed_at_reviewed_pre_bytes_before_mutation(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError, apply

    record = _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    root = migration_repository["root"]
    assert isinstance(root, Path)
    modified = next(
        row for row in record["attempt_rows"] if row["tracked_state"] == "modified"
    )
    _git(root, "add", "--", modified["original_path"])
    _git(root, "commit", "-qm", "accidentally commit reviewed modified source")
    before = _migration_path_states(root, record)

    with pytest.raises(
        AttemptMigrationError, match="migration_index_classification_changed"
    ):
        apply(
            root,
            migration_repository["disposition_path"],
            migration_repository["disposition_specification_review_path"],
            migration_repository["disposition_quality_review_path"],
        )

    assert _migration_path_states(root, record) == before


def test_apply_replays_a_clean_fully_committed_post_state(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import apply

    _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    root = migration_repository["root"]
    assert isinstance(root, Path)
    apply(
        root,
        migration_repository["disposition_path"],
        migration_repository["disposition_specification_review_path"],
        migration_repository["disposition_quality_review_path"],
    )
    _git(
        root,
        "add",
        "-A",
        "--",
        migration_repository["source_root"],
        migration_repository["archive_root"],
    )
    _git(root, "commit", "-qm", "commit complete migration post state")

    apply(
        root,
        migration_repository["disposition_path"],
        migration_repository["disposition_specification_review_path"],
        migration_repository["disposition_quality_review_path"],
    )


def test_apply_preserves_a_raced_replacement_and_rejects_the_source_removal(
    migration_repository: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.retirement import safe_io
    from orchestrator.retirement.attempt_migration import AttemptMigrationError, apply

    record = _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    raced_bytes = b"raced replacement\n"
    injected: list[str] = []

    def inject_replacement(
        stage: str, parent_fd: int, destination_name: str, quarantine_name: str
    ) -> None:
        del stage, quarantine_name
        if injected:
            return
        descriptor = os.open(
            destination_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o644,
            dir_fd=parent_fd,
        )
        try:
            os.write(descriptor, raced_bytes)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        injected.append(destination_name)

    monkeypatch.setattr(safe_io, "_conditional_quarantine_boundary", inject_replacement)
    with pytest.raises(AttemptMigrationError, match="source_removal_failed"):
        apply(
            migration_repository["root"],
            migration_repository["disposition_path"],
            migration_repository["disposition_specification_review_path"],
            migration_repository["disposition_quality_review_path"],
        )

    assert len(injected) == 1
    raced_row = next(
        row
        for row in record["attempt_rows"]
        if Path(row["original_path"]).name == injected[0]
    )
    assert (
        Path(migration_repository["root"]) / raced_row["original_path"]
    ).read_bytes() == raced_bytes


def test_apply_rejects_an_archive_destination_conflict(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError, apply

    record = _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    root = migration_repository["root"]
    assert isinstance(root, Path)
    row = record["attempt_rows"][0]
    _write(root, row["archive_path"], b"conflict\n")

    with pytest.raises(AttemptMigrationError, match="archive_binding_mismatch"):
        apply(
            root,
            migration_repository["disposition_path"],
            migration_repository["disposition_specification_review_path"],
            migration_repository["disposition_quality_review_path"],
        )


def test_apply_rejects_uncommitted_disposition_reviews(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError, apply

    _capture(migration_repository)
    _commit_disposition_reviews(migration_repository, commit_reviews=False)

    with pytest.raises(AttemptMigrationError, match="authority_not_committed_at_head"):
        apply(
            migration_repository["root"],
            migration_repository["disposition_path"],
            migration_repository["disposition_specification_review_path"],
            migration_repository["disposition_quality_review_path"],
        )


def test_apply_rejects_committed_reviews_over_the_wrong_disposition_digest(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError, apply

    _capture(migration_repository)
    _commit_disposition_reviews(migration_repository, wrong_subject_digest=True)

    with pytest.raises(AttemptMigrationError, match="review_subject_digest_mismatch"):
        apply(
            migration_repository["root"],
            migration_repository["disposition_path"],
            migration_repository["disposition_specification_review_path"],
            migration_repository["disposition_quality_review_path"],
        )


def test_apply_rejects_committed_reviews_with_the_wrong_subject_kind(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError, apply

    _capture(migration_repository)
    _commit_disposition_reviews(
        migration_repository, subject_kind="different_disposition_kind"
    )

    with pytest.raises(AttemptMigrationError, match="review_subject_kind_mismatch"):
        apply(
            migration_repository["root"],
            migration_repository["disposition_path"],
            migration_repository["disposition_specification_review_path"],
            migration_repository["disposition_quality_review_path"],
        )


def test_postvalidate_rejects_extra_archive_coverage(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        apply,
        postvalidate,
    )

    _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    root = migration_repository["root"]
    assert isinstance(root, Path)
    apply(
        root,
        migration_repository["disposition_path"],
        migration_repository["disposition_specification_review_path"],
        migration_repository["disposition_quality_review_path"],
    )
    _write(root, f"{migration_repository['archive_root']}/extra.json", b"{}\n")

    with pytest.raises(AttemptMigrationError, match="archive_contains_unreviewed_path"):
        postvalidate(
            root,
            migration_repository["disposition_path"],
            migration_repository["disposition_specification_review_path"],
            migration_repository["disposition_quality_review_path"],
            migration_repository["post_report_path"],
        )


def test_postvalidate_rejects_a_cross_boundary_rename_projection(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        apply,
        postvalidate,
    )

    record = _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    root = migration_repository["root"]
    live_path = migration_repository["live_ledger_path"]
    report_path = migration_repository["post_report_path"]
    assert isinstance(root, Path)
    assert isinstance(live_path, str)
    assert isinstance(report_path, str)
    apply(
        root,
        migration_repository["disposition_path"],
        migration_repository["disposition_specification_review_path"],
        migration_repository["disposition_quality_review_path"],
    )
    destination = "outside/postvalidate-moved-live.json"
    (root / destination).parent.mkdir(parents=True, exist_ok=True)
    _git(root, "mv", "--", live_path, destination)
    before = _migration_path_states(root, record)

    with pytest.raises(
        AttemptMigrationError, match="status_projection_boundary_crossing"
    ):
        postvalidate(
            root,
            migration_repository["disposition_path"],
            migration_repository["disposition_specification_review_path"],
            migration_repository["disposition_quality_review_path"],
            report_path,
        )

    assert _migration_path_states(root, record) == before
    assert not (root / report_path).exists()


def test_validate_rejects_closed_schema_drift_even_with_a_recomputed_digest(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    record = _capture(migration_repository)
    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    record["unexpected"] = True
    record["normalized_disposition_sha256"] = _digest(
        _canonical(
            {
                key: value
                for key, value in record.items()
                if key != "normalized_disposition_sha256"
            }
        )
    )
    (root / disposition_path).write_bytes(_canonical(record) + b"\n")

    with pytest.raises(AttemptMigrationError, match="disposition_keys_mismatch"):
        validate(root, disposition_path)


def test_validate_reopens_the_stored_capture_head_tree_relationship(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    record = _capture(migration_repository)
    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    record["pre_move_repository_state"]["tree"] = migration_repository["source_tree"]
    _rewrite_disposition(root, disposition_path, record)

    with pytest.raises(AttemptMigrationError, match="capture_head_tree_mismatch"):
        validate(root, disposition_path)


def test_validate_rejects_malformed_nested_status_rows(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    record = _capture(migration_repository)
    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    projection = record["pre_move_repository_state"]["status_projection"]
    projection["rows"][0]["status"] = 7
    projection["normalized_rows_sha256"] = _digest(_canonical(projection["rows"]))
    _rewrite_disposition(root, disposition_path, record)

    with pytest.raises(AttemptMigrationError, match="status_projection_row_invalid"):
        validate(root, disposition_path)


def test_validate_rejects_duplicate_nested_status_rows(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    record = _capture(migration_repository)
    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    projection = record["pre_move_repository_state"]["status_projection"]
    projection["rows"].insert(0, dict(projection["rows"][0]))
    projection["row_count"] = len(projection["rows"])
    projection["normalized_rows_sha256"] = _digest(_canonical(projection["rows"]))
    _rewrite_disposition(root, disposition_path, record)

    with pytest.raises(AttemptMigrationError, match="status_projection_row_duplicate"):
        validate(root, disposition_path)


@pytest.mark.parametrize("direction", ["source_to_outside", "outside_to_source"])
def test_validate_rejects_redigested_cross_boundary_status_rows(
    migration_repository: dict[str, object], direction: str
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    source_root = migration_repository["source_root"]
    protected_path = migration_repository["protected_paths"][0]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    assert isinstance(source_root, str)
    assert isinstance(protected_path, str)
    record = _capture(migration_repository)
    projection = record["pre_move_repository_state"]["status_projection"]
    if direction == "source_to_outside":
        row = next(item for item in projection["rows"] if item["path"].startswith(source_root))
        row["source_path"] = "outside/redigested-origin.json"
    else:
        row = next(item for item in projection["rows"] if item["path"] == protected_path)
        row["source_path"] = migration_repository["expected_paths"][0]
    row["status"] = "R "
    projection["rows"].sort(
        key=lambda item: (item["path"], item["source_path"] or "", item["status"])
    )
    projection["normalized_rows_sha256"] = _digest(
        _canonical(projection["rows"])
    )
    _rewrite_disposition(root, disposition_path, record)

    with pytest.raises(
        AttemptMigrationError, match="status_projection_boundary_crossing"
    ):
        validate(root, disposition_path)


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("attempt_source_commit", "attempt_source_identity_invalid"),
        ("attempt_source_tree", "attempt_source_identity_invalid"),
        ("attempt_source_root", "path_invalid"),
        ("attempt_archive_root", "path_invalid"),
        ("manifest_path", "path_invalid"),
        ("manifest_count", "expected_manifest_count_invalid"),
        ("manifest_digest", "expected_manifest_digest_invalid"),
        ("row_original_path", "path_invalid"),
        ("row_archive_path", "path_invalid"),
        ("row_tracked_state", "attempt_row_tracked_state_invalid"),
        ("row_file_type", "file_binding_metadata_invalid"),
        ("row_mode", "file_binding_metadata_invalid"),
        ("row_mode_bool", "file_binding_metadata_invalid"),
        ("row_size", "file_binding_size_invalid"),
        ("row_size_bool", "file_binding_size_invalid"),
        ("row_digest", "file_binding_digest_invalid"),
        ("attempt_count", "attempt_path_count_mismatch"),
        ("attempt_path_digest", "attempt_path_set_digest_mismatch"),
        ("archive_path_digest", "archive_path_set_digest_mismatch"),
        ("row_set_digest", "attempt_row_set_digest_mismatch"),
        ("authority_binding", "file_binding_keys_mismatch"),
        ("artifact_binding", "file_binding_keys_mismatch"),
        ("generation5_binding", "file_binding_keys_mismatch"),
        ("generation5_value", "generation5_value_invalid"),
        ("generation5_value_bool", "generation5_value_invalid"),
        ("generation11_value", "generation11_value_invalid"),
        ("generation11_value_bool", "generation11_value_invalid"),
        ("restoration_source_path", "path_invalid"),
        ("restoration_target_path", "path_invalid"),
        ("restoration_source_commit", "restoration_coordinates_mismatch"),
        ("state_head", "repository_state_identity_invalid"),
        ("state_tree", "repository_state_identity_invalid"),
        ("state_index_digest", "repository_state_identity_invalid"),
        ("status_rows", "status_projection_invalid"),
        ("status_count", "status_projection_invalid"),
        ("status_digest", "status_projection_invalid"),
        ("status_row", "status_projection_row_invalid"),
        ("status_path", "status_projection_row_invalid"),
        ("status_source_path", "status_projection_row_invalid"),
        ("status_code", "status_projection_row_invalid"),
        ("protected_binding", "file_binding_keys_mismatch"),
    ],
)
def test_validate_and_cli_reject_nested_type_mutations_without_raw_exceptions(
    migration_repository: dict[str, object],
    capsys: pytest.CaptureFixture[str],
    mutation: str,
    error: str,
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        main,
        validate,
    )

    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    record = _capture(migration_repository)
    _mutate_disposition_nested_type(record, mutation)
    _rewrite_disposition(root, disposition_path, record)

    with pytest.raises(AttemptMigrationError, match=error):
        validate(root, disposition_path)
    exit_status = main(
        [
            "validate",
            "--repository-root",
            str(root),
            "--disposition-path",
            disposition_path,
        ]
    )
    captured = capsys.readouterr()
    assert exit_status == 1
    assert error in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_validate_requires_stored_source_status_to_cover_attempt_rows_exactly(
    migration_repository: dict[str, object], mutation: str
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    source_root = migration_repository["source_root"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    assert isinstance(source_root, str)
    record = _capture(migration_repository)
    projection = record["pre_move_repository_state"]["status_projection"]
    if mutation == "missing":
        projection["rows"].remove(
            next(row for row in projection["rows"] if row["path"].startswith(source_root))
        )
    else:
        projection["rows"].append(
            {
                "path": f"{source_root}/unreviewed-extra.json",
                "source_path": None,
                "status": "??",
            }
        )
        projection["rows"].sort(
            key=lambda row: (row["path"], row["source_path"] or "", row["status"])
        )
    projection["row_count"] = len(projection["rows"])
    projection["normalized_rows_sha256"] = _digest(
        _canonical(projection["rows"])
    )
    _rewrite_disposition(root, disposition_path, record)

    with pytest.raises(AttemptMigrationError, match="source_status_coverage_mismatch"):
        validate(root, disposition_path)


def test_validate_rejects_a_current_head_outside_the_capture_head_lineage(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    _capture(migration_repository)
    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    current_tree = _git(root, "rev-parse", "HEAD^{tree}").decode().strip()
    unrelated_commit = _git(
        root, "commit-tree", current_tree, "-m", "unrelated current head"
    ).decode().strip()
    _git(root, "reset", "--soft", unrelated_commit)

    with pytest.raises(AttemptMigrationError, match="capture_head_not_ancestor"):
        validate(root, disposition_path)


def test_validate_rejects_disposition_mode_drift(
    migration_repository: dict[str, object],
) -> None:
    from orchestrator.retirement.attempt_migration import (
        AttemptMigrationError,
        validate,
    )

    _capture(migration_repository)
    root = migration_repository["root"]
    disposition_path = migration_repository["disposition_path"]
    assert isinstance(root, Path)
    assert isinstance(disposition_path, str)
    (root / disposition_path).chmod(0o600)

    with pytest.raises(AttemptMigrationError, match="disposition_mode_invalid"):
        validate(root, disposition_path)


def test_cli_validate_emits_the_canonical_record(
    migration_repository: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    from orchestrator.retirement.attempt_migration import main

    record = _capture(migration_repository)
    exit_status = main(
        [
            "validate",
            "--repository-root",
            str(migration_repository["root"]),
            "--disposition-path",
            str(migration_repository["disposition_path"]),
        ]
    )
    captured = capsys.readouterr()
    assert exit_status == 0
    assert captured.err == ""
    assert json.loads(captured.out) == record


def test_applicability_fixture_captures_exactly_34_rows_and_7_protected_paths(
    tmp_path: Path,
) -> None:
    arguments = _make_migration_repository(
        tmp_path, attempt_path_count=34, protected_path_count=7
    )
    _apply_real_nonexecutive_modes(arguments)

    record = _capture(arguments)

    assert record["attempt_path_count"] == 34
    assert len(record["attempt_rows"]) == 34
    assert len(record["protected_path_bindings"]) == 7
    assert record["ledger_lineage"]["restoration_binding"]["lstat_mode"] == 0o600


def test_apply_reads_the_live_disposition_only_once(
    migration_repository: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.retirement import attempt_migration

    _capture(migration_repository)
    _commit_disposition_reviews(migration_repository)
    disposition_path = migration_repository["disposition_path"]
    original_read = attempt_migration._read_regular
    reads = 0

    def counting_read(
        repository_root: Path,
        relative_path: Path | str,
        *,
        missing_ok: bool = False,
    ) -> dict[str, object] | None:
        nonlocal reads
        if str(relative_path) == disposition_path:
            reads += 1
        return original_read(repository_root, relative_path, missing_ok=missing_ok)

    monkeypatch.setattr(attempt_migration, "_read_regular", counting_read)
    attempt_migration.apply(
        migration_repository["root"],
        disposition_path,
        migration_repository["disposition_specification_review_path"],
        migration_repository["disposition_quality_review_path"],
    )

    assert reads == 1


def test_cli_smoke_covers_capture_validate_apply_and_postvalidate(
    migration_repository: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    from orchestrator.retirement.attempt_migration import main

    capture_arguments = [
        "capture",
        "--repository-root",
        str(migration_repository["root"]),
        "--disposition-path",
        str(migration_repository["disposition_path"]),
        "--source-root",
        str(migration_repository["source_root"]),
        "--archive-root",
        str(migration_repository["archive_root"]),
        "--governing-plan-path",
        str(migration_repository["governing_plan_path"]),
        "--migration-plan-path",
        str(migration_repository["migration_plan_path"]),
        "--authority-subject-path",
        str(migration_repository["authority_subject_path"]),
        "--authority-specification-review-path",
        str(migration_repository["authority_specification_review_path"]),
        "--authority-quality-review-path",
        str(migration_repository["authority_quality_review_path"]),
        "--source-commit",
        str(migration_repository["source_commit"]),
        "--source-tree",
        str(migration_repository["source_tree"]),
        "--expected-paths-manifest-path",
        str(migration_repository["expected_paths_manifest_path"]),
        "--generation5-request-path",
        str(migration_repository["generation5_request_path"]),
        "--generation5-snapshot-path",
        str(migration_repository["generation5_snapshot_path"]),
        "--generation11-request-path",
        str(migration_repository["generation11_request_path"]),
        "--generation11-snapshot-path",
        str(migration_repository["generation11_snapshot_path"]),
        "--live-ledger-path",
        str(migration_repository["live_ledger_path"]),
        "--baseline-path",
        str(migration_repository["baseline_path"]),
        "--baseline-specification-review-path",
        str(migration_repository["baseline_specification_review_path"]),
        "--baseline-quality-review-path",
        str(migration_repository["baseline_quality_review_path"]),
        "--pending-request-path",
        str(migration_repository["pending_request_path"]),
        "--pending-snapshot-path",
        str(migration_repository["pending_snapshot_path"]),
        "--pending-record-path",
        str(migration_repository["pending_record_path"]),
    ]
    for protected_path in migration_repository["protected_paths"]:
        capture_arguments.extend(["--protected-path", str(protected_path)])
    assert main(capture_arguments) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == (
        "attempt_migration_disposition.v1"
    )

    common = [
        "--repository-root",
        str(migration_repository["root"]),
        "--disposition-path",
        str(migration_repository["disposition_path"]),
    ]
    assert main(["validate", *common]) == 0
    assert json.loads(capsys.readouterr().out)["disposition"] == (
        "archive_failed_pre_adoption_attempt_and_restore_tracked_files"
    )

    _commit_disposition_reviews(migration_repository)
    reviews = [
        "--specification-review-path",
        str(migration_repository["disposition_specification_review_path"]),
        "--quality-review-path",
        str(migration_repository["disposition_quality_review_path"]),
    ]
    assert main(["apply", *common, *reviews]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == (
        "attempt_migration_disposition.v1"
    )
    assert (
        main(
            [
                "postvalidate",
                *common,
                *reviews,
                "--report-path",
                str(migration_repository["post_report_path"]),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["schema_version"] == (
        "attempt_migration_post_report.v1"
    )


def test_incident_v1_builds_from_owner_confirmed_invalidated_attempt(
    tmp_path: Path,
) -> None:
    arguments = _make_invalidated_adopted_repository(tmp_path)

    record = _build_incident(arguments)

    assert record["schema_version"] == "attempt_migration_incident.v1"
    assert record["intended_predecessor"] == {
        "head": arguments["intended_predecessor_head"],
        "tree": arguments["intended_predecessor_tree"],
    }
    assert record["predecessor_projection"]["uncovered_paths"] == ["README.md"]
    assert record["workspace_baseline_binding"]["path"] == arguments[
        "workspace_baseline_path"
    ]
    assert record["owner_attestation_binding"] == _file_binding(
        arguments["root"], arguments["owner_attestation_path"]
    )
    assert record["expected_paths_manifest_binding"]["row_count"] == len(
        arguments["expected_paths"]
    )
    assert _validate_incident(arguments, record) == record


@pytest.mark.parametrize("lifecycle_defect", ["pending", "identity_mismatch"])
def test_incident_v1_rejects_non_owner_confirmed_lifecycle(
    tmp_path: Path, lifecycle_defect: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    arguments = _make_invalidated_adopted_repository(tmp_path)
    root = arguments["root"]
    owner_attestation_path = arguments["owner_attestation_path"]
    if lifecycle_defect == "pending":
        replacement = arguments["pending_attestation"]
    else:
        replacement = deepcopy(arguments["confirmed_attestation"])
        replacement["owner_adoption"]["identity"] = "Different Owner"
    _write(root, owner_attestation_path, _canonical(replacement) + b"\n")

    with pytest.raises(AttemptMigrationError):
        _build_incident(arguments)


def test_incident_v1_rejects_failure_baseline_candidate_head_mismatch(
    tmp_path: Path,
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    arguments = _make_invalidated_adopted_repository(tmp_path)
    root = arguments["root"]
    arguments["intended_predecessor_head"] = _git(
        root, "rev-parse", "HEAD"
    ).decode().strip()
    arguments["intended_predecessor_tree"] = _git(
        root, "rev-parse", "HEAD^{tree}"
    ).decode().strip()

    with pytest.raises(AttemptMigrationError):
        _build_incident(arguments)


def test_incident_v1_requires_an_uncovered_predecessor_path(tmp_path: Path) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    arguments = _make_invalidated_adopted_repository(
        tmp_path, controlled_predecessor=True
    )

    with pytest.raises(AttemptMigrationError):
        _build_incident(arguments)


@pytest.mark.parametrize(
    "tamper",
    [
        "normalized_digest",
        "commit_coordinate",
        "changed_path_set",
        "raw_message_digest",
        "nested_binding_type",
    ],
)
def test_incident_v1_rejects_canonical_and_nested_tamper(
    tmp_path: Path, tamper: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    arguments = _make_invalidated_adopted_repository(tmp_path)
    record = _build_incident(arguments)
    if tamper == "normalized_digest":
        record["normalized_incident_sha256"] = "sha256:" + "0" * 64
    elif tamper == "commit_coordinate":
        record["predecessor_projection"]["first_parent_commits"][0][
            "commit"
        ] = "0" * 40
    elif tamper == "changed_path_set":
        record["predecessor_projection"]["changed_path_set_sha256"] = (
            "sha256:" + "0" * 64
        )
    elif tamper == "raw_message_digest":
        record["predecessor_projection"]["first_parent_commits"][0][
            "raw_message_sha256"
        ] = "sha256:" + "0" * 64
    else:
        record["owner_attestation_binding"]["size"] = "not-an-integer"
    if tamper != "normalized_digest":
        record["normalized_incident_sha256"] = _digest(
            _canonical(
                {
                    key: value
                    for key, value in record.items()
                    if key != "normalized_incident_sha256"
                }
            )
        )

    with pytest.raises(AttemptMigrationError):
        _validate_incident(arguments, record)


@pytest.mark.parametrize("binding_role", ["manifest", "owner_attestation"])
def test_incident_v1_reopens_manifest_and_owner_attestation_bytes(
    tmp_path: Path, binding_role: str
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    arguments = _make_invalidated_adopted_repository(tmp_path)
    record = _build_incident(arguments)
    path = (
        arguments["expected_paths_manifest_path"]
        if binding_role == "manifest"
        else arguments["owner_attestation_path"]
    )
    absolute = arguments["root"] / path
    absolute.write_bytes(absolute.read_bytes() + b"tamper\n")

    with pytest.raises(AttemptMigrationError):
        _validate_incident(arguments, record)


def test_incident_v1_allows_later_corrective_commit_but_not_attempt_drift(
    tmp_path: Path,
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    arguments = _make_invalidated_adopted_repository(tmp_path)
    record = _build_incident(arguments)
    root = arguments["root"]
    _write(root, "notes/later-correction.md", b"later correction\n")
    _git(root, "add", "--", "notes/later-correction.md")
    _git(root, "commit", "-qm", "later corrective commit")

    assert _validate_incident(arguments, record) == record

    changed_attempt_path = arguments["known_failure_baseline_path"]
    absolute = root / changed_attempt_path
    absolute.write_bytes(absolute.read_bytes() + b"changed\n")
    with pytest.raises(AttemptMigrationError):
        _validate_incident(arguments, record)


def test_incident_v1_rejects_current_head_outside_predecessor_ancestry(
    tmp_path: Path,
) -> None:
    from orchestrator.retirement.attempt_migration import AttemptMigrationError

    arguments = _make_invalidated_adopted_repository(tmp_path)
    root = arguments["root"]
    workspace = json.loads(
        (root / arguments["workspace_baseline_path"]).read_text()
    )
    sibling_tree = _git(
        root, "rev-parse", f"{workspace['head']}^{{tree}}"
    ).decode().strip()
    sibling = _git(
        root,
        "commit-tree",
        sibling_tree,
        "-p",
        workspace["head"],
        "-m",
        "sibling corrective history",
    ).decode().strip()
    _git(root, "update-ref", "HEAD", sibling)

    with pytest.raises(AttemptMigrationError):
        _build_incident(arguments)
