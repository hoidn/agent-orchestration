from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import hashlib
import sys
from pathlib import Path

import pytest
from orchestrator.retirement import safe_io
from orchestrator.retirement import source_bindings as retirement_source_bindings

from orchestrator.retirement.materialization import MaterializationError
from orchestrator.retirement.source_bindings import (
    SourceBindingIssue,
    SourceBindingError,
    _canonical_sha256,
    _derive_final_message_bytes,
    _parse_status,
    _set_digest,
    _write_repository_bytes,
    adopt_bootstrap_workspace,
    build_non_target_sources,
    build_precommit_control,
    capture_workspace_baseline,
    validate_commit_boundary,
    validate_non_target_sources,
    validate_bootstrap_workspace,
    validate_workspace_baseline,
    validate_workspace_record_shape,
    materialize_query,
)


def test_source_binding_issues_sort_by_path_then_code_then_detail() -> None:
    issues = [
        SourceBindingIssue("z-code", "a", "later"),
        SourceBindingIssue("a-code", "b", "first-path-later"),
        SourceBindingIssue("a-code", "a", "z-detail"),
        SourceBindingIssue("a-code", "a", "a-detail"),
    ]

    assert sorted(issues) == [
        SourceBindingIssue("a-code", "a", "a-detail"),
        SourceBindingIssue("a-code", "a", "z-detail"),
        SourceBindingIssue("z-code", "a", "later"),
        SourceBindingIssue("a-code", "b", "first-path-later"),
    ]


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _lineage_path_set_sha256(paths: list[str]) -> str:
    data = b"".join(path.encode("utf-8") + b"\n" for path in sorted(paths))
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _lineage_commit_message(
    subject: str,
    *,
    transaction_id: str | None = None,
    control_sha256: str | None = None,
) -> bytes:
    message = subject.encode("utf-8") + b"\n"
    if transaction_id is None and control_sha256 is None:
        return message
    assert transaction_id is not None and control_sha256 is not None
    return (
        message
        + b"\nRetirement-Control-Schema: precommit_control.v1\n"
        + f"Retirement-Transaction-ID: {transaction_id}\n".encode("ascii")
        + f"Retirement-Control-SHA256: {control_sha256.removeprefix('sha256:')}\n".encode(
            "ascii"
        )
    )


def _commit_lineage_tree(
    repository: Path,
    message: bytes,
    *,
    parents: list[str] | None = None,
    update_head: bool = True,
) -> str:
    tree = _git(repository, "write-tree")
    selected_parents = parents or [_git(repository, "rev-parse", "HEAD")]
    arguments = ["git", "commit-tree", tree]
    for parent in selected_parents:
        arguments.extend(["-p", parent])
    completed = subprocess.run(
        arguments,
        cwd=repository,
        input=message,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    commit = completed.stdout.decode("ascii").strip()
    if update_head:
        _git(repository, "update-ref", "HEAD", commit)
    return commit


def _derive_committed_predecessor_lineage(
    repository: Path,
    *,
    baseline_head: str,
    intended_predecessor_head: str,
    require_uncovered_paths: bool = False,
) -> dict[str, object]:
    helper = getattr(
        retirement_source_bindings, "derive_committed_predecessor_lineage"
    )
    keyword_arguments: dict[str, object] = {
        "baseline_head": baseline_head,
        "intended_predecessor_head": intended_predecessor_head,
    }
    if require_uncovered_paths:
        keyword_arguments["require_uncovered_paths"] = True
    return helper(repository, **keyword_arguments)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "tests@example.invalid")
    _git(root, "config", "user.name", "Tests")
    (root / "tracked.txt").write_text("base\n")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-qm", "base")
    return root


def test_workspace_baseline_detects_same_status_byte_mutation(repository: Path) -> None:
    path = repository / "tracked.txt"
    path.write_text("first\n")
    baseline = capture_workspace_baseline(repository)
    assert validate_workspace_baseline(repository, baseline) == []

    path.write_text("other\n")
    issues = validate_workspace_baseline(repository, baseline)
    assert "dirty_entry_changed" in {issue.code for issue in issues}


def test_workspace_baseline_preserves_punctuation_and_nul_status_paths(
    repository: Path,
) -> None:
    odd = repository / "space tab\tname.txt"
    odd.write_text("odd\n")
    baseline = capture_workspace_baseline(repository)
    assert [row["path"] for row in baseline["status_rows"]] == [odd.name]
    assert baseline["dirty_entries"][0]["path"] == odd.name


def test_workspace_baseline_rejects_symlink_retarget(repository: Path) -> None:
    (repository / "first").write_text("1")
    (repository / "second").write_text("2")
    os.symlink("first", repository / "link")
    baseline = capture_workspace_baseline(repository)
    (repository / "link").unlink()
    os.symlink("second", repository / "link")
    assert "dirty_entry_changed" in {
        issue.code for issue in validate_workspace_baseline(repository, baseline)
    }


def test_workspace_baseline_rejects_symlinked_protected_path_parent(
    repository: Path,
) -> None:
    outside = repository.parent / "outside"
    outside.mkdir()
    (outside / "owner.txt").write_text("outside owner bytes\n")
    (repository / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SourceBindingError, match="repository_path_parent_unreadable"):
        capture_workspace_baseline(repository, ["linked/owner.txt"])


def test_workspace_baseline_revalidates_ignored_protected_regular_file(
    repository: Path,
) -> None:
    (repository / ".gitignore").write_text("ignored/\n")
    _git(repository, "add", ".gitignore")
    _git(repository, "commit", "-qm", "ignore owner state")
    protected = repository / "ignored/state.txt"
    protected.parent.mkdir()
    protected.write_text("owner bytes\n")

    baseline = capture_workspace_baseline(repository, ["ignored/state.txt"])
    assert validate_workspace_baseline(repository, baseline) == []

    protected.write_text("changed owner bytes\n")
    assert "protected_entry_changed" in {
        issue.code for issue in validate_workspace_baseline(repository, baseline)
    }


def test_workspace_baseline_revalidates_ignored_protected_directory_descendants(
    repository: Path,
) -> None:
    (repository / ".gitignore").write_text("ignored/\n")
    _git(repository, "add", ".gitignore")
    _git(repository, "commit", "-qm", "ignore owner directory")
    protected = repository / "ignored"
    protected.mkdir()
    (protected / "child.txt").write_text("owner bytes\n")

    baseline = capture_workspace_baseline(repository, ["ignored"])
    assert validate_workspace_baseline(repository, baseline) == []

    (protected / "child.txt").write_text("changed owner bytes\n")
    assert "protected_entry_changed" in {
        issue.code for issue in validate_workspace_baseline(repository, baseline)
    }


@pytest.mark.parametrize("allowed", ["ignored", "ignored/candidate.json"])
def test_workspace_baseline_rejects_allowed_addition_within_protected_path(
    repository: Path, allowed: str
) -> None:
    (repository / ".gitignore").write_text("ignored/\n")
    _git(repository, "add", ".gitignore")
    _git(repository, "commit", "-qm", "ignore owner directory")
    protected = repository / "ignored"
    protected.mkdir()
    (protected / "child.txt").write_text("owner bytes\n")
    baseline = capture_workspace_baseline(repository, ["ignored"])

    assert "allowed_addition_intersects_protected" in {
        issue.code
        for issue in validate_workspace_baseline(
            repository, baseline, allowed_additions=[allowed]
        )
    }


def test_workspace_baseline_rejects_redigested_nested_and_timestamp_tamper(
    repository: Path,
) -> None:
    (repository / "untracked.txt").write_text("candidate\n")
    baseline = capture_workspace_baseline(repository, ["tracked.txt"])

    status_tamper = json.loads(json.dumps(baseline))
    status_tamper["status_rows"][0]["unexpected"] = True
    status_tamper["normalized_baseline_sha256"] = _canonical_sha256(
        status_tamper, exclude={"normalized_baseline_sha256"}
    )
    assert "status_row_invalid" in {
        issue.code for issue in validate_workspace_baseline(repository, status_tamper)
    }

    timestamp_tamper = json.loads(json.dumps(baseline))
    timestamp_tamper["captured_at"] = 5
    timestamp_tamper["normalized_baseline_sha256"] = _canonical_sha256(
        timestamp_tamper, exclude={"normalized_baseline_sha256"}
    )
    assert "captured_at_invalid" in {
        issue.code
        for issue in validate_workspace_baseline(repository, timestamp_tamper)
    }


def test_workspace_live_validator_returns_shape_issues_before_dereference(
    repository: Path,
) -> None:
    baseline = capture_workspace_baseline(repository)
    baseline["status_rows"] = [{}]
    baseline["normalized_baseline_sha256"] = _canonical_sha256(
        baseline, exclude={"normalized_baseline_sha256"}
    )

    issues = validate_workspace_baseline(repository, baseline)

    assert "status_row_invalid" in {issue.code for issue in issues}


def test_workspace_cli_emits_issue_envelope_for_shape_invalid_json(
    repository: Path,
) -> None:
    baseline = capture_workspace_baseline(repository)
    baseline["status_rows"] = [{}]
    baseline["normalized_baseline_sha256"] = _canonical_sha256(
        baseline, exclude={"normalized_baseline_sha256"}
    )
    record_path = repository / "invalid-workspace.json"
    record_path.write_text(json.dumps(baseline) + "\n")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.retirement.source_bindings",
            "validate-workspace-baseline",
            "--repository-root",
            str(repository),
            "--record",
            record_path.name,
        ],
        cwd=Path(__file__).parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert completed.stderr == ""
    assert json.loads(completed.stdout)["status"] == "rejected"


def test_workspace_baseline_closes_index_dirty_protected_and_bootstrap_rows(
    repository: Path,
) -> None:
    (repository / "untracked.txt").write_text("candidate\n")
    baseline = capture_workspace_baseline(repository, ["tracked.txt"])

    index_tamper = json.loads(json.dumps(baseline))
    index_tamper["index_entries"][0]["unexpected"] = True
    index_tamper["index_entry_set_sha256"] = _set_digest(
        index_tamper["index_entries"]
    )
    index_tamper["normalized_baseline_sha256"] = _canonical_sha256(
        index_tamper, exclude={"normalized_baseline_sha256"}
    )
    assert "index_entry_invalid" in {
        issue.code for issue in validate_workspace_baseline(repository, index_tamper)
    }

    dirty_tamper = json.loads(json.dumps(baseline))
    dirty_tamper["dirty_entries"][0]["unexpected"] = True
    dirty_tamper["dirty_entries"][0]["normalized_entry_sha256"] = _canonical_sha256(
        dirty_tamper["dirty_entries"][0], exclude={"normalized_entry_sha256"}
    )
    dirty_tamper["dirty_entry_set_sha256"] = _set_digest(
        dirty_tamper["dirty_entries"]
    )
    dirty_tamper["normalized_baseline_sha256"] = _canonical_sha256(
        dirty_tamper, exclude={"normalized_baseline_sha256"}
    )
    assert "workspace_entry_invalid" in {
        issue.code for issue in validate_workspace_baseline(repository, dirty_tamper)
    }

    protected_tamper = json.loads(json.dumps(baseline))
    protected_tamper["protected_paths"][0]["unexpected"] = True
    protected_tamper["protected_paths"][0]["normalized_entry_sha256"] = (
        _canonical_sha256(
            protected_tamper["protected_paths"][0],
            exclude={"normalized_entry_sha256"},
        )
    )
    protected_tamper["normalized_baseline_sha256"] = _canonical_sha256(
        protected_tamper, exclude={"normalized_baseline_sha256"}
    )
    assert "workspace_entry_invalid" in {
        issue.code
        for issue in validate_workspace_baseline(repository, protected_tamper)
    }

    enum_tamper = json.loads(json.dumps(baseline))
    enum_tamper["dirty_entries"][0]["existence"] = []
    enum_tamper["dirty_entries"][0]["normalized_entry_sha256"] = _canonical_sha256(
        enum_tamper["dirty_entries"][0], exclude={"normalized_entry_sha256"}
    )
    enum_tamper["dirty_entry_set_sha256"] = _set_digest(
        enum_tamper["dirty_entries"]
    )
    enum_tamper["normalized_baseline_sha256"] = _canonical_sha256(
        enum_tamper, exclude={"normalized_baseline_sha256"}
    )
    assert "workspace_entry_invalid" in {
        issue.code for issue in validate_workspace_baseline(repository, enum_tamper)
    }

    bootstrap = json.loads(json.dumps(baseline))
    bootstrap["schema_version"] = "bootstrap_workspace_baseline.v1"
    bootstrap["bootstrap_capture_bindings"] = {
        "producer_contract_version": 5,
        "head_file_sha256": f"sha256:{'0' * 64}",
        "status_file_sha256": f"sha256:{'0' * 64}",
        "index_entries_file_sha256": f"sha256:{'0' * 64}",
        "index_file_sha256": bootstrap["index_sha256"],
        "archive_sha256": f"sha256:{'0' * 64}",
        "tar_stderr_sha256": f"sha256:{'0' * 64}",
    }
    bootstrap["raw_archive_not_persisted"] = True
    bootstrap["normalized_baseline_sha256"] = _canonical_sha256(
        bootstrap, exclude={"normalized_baseline_sha256"}
    )
    assert "bootstrap_capture_binding_invalid" in {
        issue.code for issue in validate_bootstrap_workspace(repository, bootstrap)
    }


def test_bootstrap_validator_allows_only_task_candidate_additions(repository: Path) -> None:
    baseline = capture_workspace_baseline(repository)
    baseline["schema_version"] = "bootstrap_workspace_baseline.v1"
    baseline["bootstrap_capture_bindings"] = {
        "producer_contract_version": "task1_first_write_capture.v1",
        "head_file_sha256": f"sha256:{'0' * 64}",
        "status_file_sha256": f"sha256:{'0' * 64}",
        "index_entries_file_sha256": f"sha256:{'0' * 64}",
        "index_file_sha256": baseline["index_sha256"],
        "archive_sha256": f"sha256:{'0' * 64}",
        "tar_stderr_sha256": f"sha256:{'0' * 64}",
    }
    baseline["raw_archive_not_persisted"] = True
    baseline.pop("normalized_baseline_sha256")
    from orchestrator.retirement.broad_evidence import canonical_sha256

    baseline["normalized_baseline_sha256"] = canonical_sha256(
        baseline, exclude={"normalized_baseline_sha256"}
    )
    baseline_path = repository / (
        "docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/"
        "implementation-commits/task-01-bootstrap/bootstrap-workspace-baseline.json"
    )
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(json.dumps(baseline) + "\n")
    relative_record = baseline_path.relative_to(repository).as_posix()
    assert validate_bootstrap_workspace(repository, baseline, [relative_record]) == []
    completed = subprocess.run(
        [sys.executable, "-m", "orchestrator.retirement.source_bindings", "validate-bootstrap-workspace", "--repository-root", str(repository), "--record", relative_record, "--allowed-addition", relative_record],
        cwd=repository.parent,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1])},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    (repository / "orchestrator").mkdir()
    (repository / "orchestrator" / "retirement").mkdir()
    (repository / "orchestrator" / "retirement" / "new.py").write_text("# task 1\n")
    assert "outside_candidate_change" in {
        issue.code
        for issue in validate_bootstrap_workspace(repository, baseline, [relative_record])
    }
    assert validate_bootstrap_workspace(
        repository,
        baseline,
        [relative_record, "orchestrator/retirement/new.py"],
    ) == []
    assert "allowed_addition_partition_invalid" in {
        issue.code
        for issue in validate_bootstrap_workspace(
            repository,
            baseline,
            [
                "orchestrator/retirement/new.py",
                relative_record,
                "orchestrator/retirement/new.py",
            ],
        )
    }

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.retirement.source_bindings",
            "validate-bootstrap-workspace",
            "--repository-root",
            str(repository),
            "--record",
            relative_record,
            "--allowed-addition",
            relative_record,
            "--allowed-addition",
            "orchestrator/retirement/new.py",
        ],
        cwd=repository.parent,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1])},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    (repository / "outside.txt").write_text("not task 1\n")
    assert "outside_candidate_change" in {
        issue.code
        for issue in validate_bootstrap_workspace(
            repository,
            baseline,
            [relative_record, "orchestrator/retirement/new.py"],
        )
    }


def test_baseline_json_contains_no_dirty_file_bytes(repository: Path) -> None:
    secret = "do-not-persist-this-user-content"
    (repository / "tracked.txt").write_text(secret)
    baseline = capture_workspace_baseline(repository)
    assert secret not in json.dumps(baseline)


def test_special_file_fails_closed(repository: Path) -> None:
    fifo = repository / "pipe"
    os.mkfifo(fifo)
    try:
        with pytest.raises(SourceBindingError, match="unsupported_file_type"):
            capture_workspace_baseline(repository)
    finally:
        fifo.unlink()


def test_query_materializer_derives_paths_and_capture_commit(repository: Path) -> None:
    handoff = repository / "handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "yaml_retirement_handoff": {
                    "schema_version": "procedure_first_yaml_retirement_handoff.v1",
                    "captured_at_commit": "1" * 40,
                    "queues": [
                        {
                            "queue_id": "selected",
                            "paths": ["a/path.yaml", "z/path.yml"],
                        }
                    ],
                }
            }
        )
        + "\n"
    )
    receipt = materialize_query(
        repository,
        handoff.name,
        "selected",
        1,
        "evidence/query.json",
    )
    query = json.loads((repository / "evidence/query.json").read_text())
    assert receipt["generation"] == 1
    assert query["paths"] == ["a/path.yaml", "z/path.yml"]
    assert query["capture_commit"] == "1" * 40

    document = json.loads(handoff.read_text())
    document["yaml_retirement_handoff"]["queues"][0]["paths"].append("zz/new-path.yaml")
    handoff.write_text(json.dumps(document) + "\n")
    with pytest.raises(MaterializationError):
        materialize_query(
            repository,
            handoff.name,
            "selected",
            1,
            "evidence/query.json",
        )


def test_cli_exposes_exact_task_one_command_set(repository: Path) -> None:
    completed = subprocess.run(
        ["python", "-m", "orchestrator.retirement.source_bindings", "--help"],
        cwd=Path(__file__).parents[1],
        text=True,
        capture_output=True,
        check=True,
    )
    command_line = next(
        line.strip() for line in completed.stdout.splitlines() if line.strip().startswith("{")
    )
    assert {item.strip(" {}.") for item in command_line.split(",")} == {
        "capture-workspace-baseline",
        "build-non-target-sources",
        "validate-workspace-baseline",
        "validate-non-target-sources",
        "materialize-query",
        "build-precommit-control",
        "validate-commit-boundary",
        "adopt-bootstrap-workspace",
        "validate-bootstrap-workspace",
    }


def test_workspace_baseline_covers_rename_delete_symlink_and_directory(
    repository: Path,
) -> None:
    old = repository / "old name.txt"
    deleted = repository / "deleted.txt"
    old.write_text("old\n")
    deleted.write_text("delete\n")
    _git(repository, "add", old.name, deleted.name)
    _git(repository, "commit", "-qm", "more")
    _git(repository, "mv", old.name, "new name.txt")
    deleted.unlink()
    os.symlink("tracked.txt", repository / "new-link")
    nested = repository / "untracked-dir"
    nested.mkdir()
    (nested / "child.txt").write_text("child\n")

    baseline = capture_workspace_baseline(repository, ["untracked-dir"])
    dirty = {row["path"]: row for row in baseline["dirty_entries"]}
    assert {"old name.txt", "new name.txt", "deleted.txt", "new-link", "untracked-dir/child.txt"} <= set(dirty)
    assert dirty["old name.txt"]["existence"] == "absent"
    assert dirty["deleted.txt"]["existence"] == "absent"
    assert dirty["new-link"]["file_type"] == "symlink"
    protected = baseline["protected_paths"][0]
    assert protected["file_type"] == "directory"
    assert [row["path"] for row in protected["content_binding"]["descendants"]] == ["child.txt"]
    assert validate_workspace_baseline(repository, baseline) == []


def test_workspace_baseline_rejects_shape_and_digest_tamper(repository: Path) -> None:
    (repository / "tracked.txt").write_text("dirty\n")
    baseline = capture_workspace_baseline(repository)
    baseline["unexpected"] = None
    assert [issue.code for issue in validate_workspace_baseline(repository, baseline)] == [
        "schema_keys_mismatch"
    ]

    baseline.pop("unexpected")
    baseline["normalized_baseline_sha256"] = f"sha256:{'0' * 64}"
    assert "normalized_digest_mismatch" in {
        issue.code for issue in validate_workspace_baseline(repository, baseline)
    }


def test_workspace_baseline_validates_allowed_addition_after_commit(
    repository: Path,
) -> None:
    baseline = capture_workspace_baseline(repository)
    addition = repository / "plan-owned.json"
    addition.write_text("{}\n")
    _git(repository, "add", addition.name)
    _git(repository, "commit", "-qm", "plan addition")
    assert validate_workspace_baseline(
        repository, baseline, [addition.name]
    ) == []


def test_porcelain_copy_tuple_preserves_both_nul_operands() -> None:
    rows = _parse_status(b"C  destination name\0source\tname\0")
    assert rows == [
        {
            "status": "C ",
            "path": "destination name",
            "source_path": "source\tname",
            "path_operands": ["destination name", "source\tname"],
            "row_id": "status-00000001",
        }
    ]


def test_exact_git_porcelain_argv_emits_copy_with_both_operands(
    repository: Path,
) -> None:
    source = repository / "copy-source.txt"
    destination = repository / "copy-destination.txt"
    source.write_text("one\ntwo\nthree\nfour\nfive\n")
    _git(repository, "add", source.name)
    _git(repository, "commit", "-qm", "copy source")
    _git(repository, "config", "status.renames", "copies")
    shutil.copyfile(source, destination)
    source.write_text("changed\ntwo\nthree\nfour\nfive\n")
    _git(repository, "add", source.name, destination.name)
    baseline = capture_workspace_baseline(repository)
    copy_rows = [row for row in baseline["status_rows"] if "C" in row["status"]]
    assert len(copy_rows) == 1
    assert copy_rows[0]["path"] == destination.name
    assert copy_rows[0]["source_path"] == source.name
    assert set(copy_rows[0]["path_operands"]) == {source.name, destination.name}


def test_conflicted_index_stages_are_bound_and_content_drift_rejects(
    repository: Path,
) -> None:
    _git(repository, "checkout", "-qb", "other")
    (repository / "tracked.txt").write_text("other\n")
    _git(repository, "commit", "-qam", "other")
    _git(repository, "checkout", "-q", "master")
    (repository / "tracked.txt").write_text("master\n")
    _git(repository, "commit", "-qam", "master")
    subprocess.run(
        ["git", "merge", "other"], cwd=repository, capture_output=True, check=False
    )
    baseline = capture_workspace_baseline(repository)
    stages = [row["stage"] for row in baseline["dirty_entries"][0]["index_entries"]]
    assert stages == [1, 2, 3]
    assert validate_workspace_baseline(repository, baseline) == []
    (repository / "tracked.txt").write_text("different unresolved bytes\n")
    assert "dirty_entry_changed" in {
        issue.code for issue in validate_workspace_baseline(repository, baseline)
    }


def test_dirty_gitlink_binds_nested_head_and_status(repository: Path) -> None:
    source = repository.parent / "submodule-source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.email", "tests@example.invalid")
    _git(source, "config", "user.name", "Tests")
    (source / "nested.txt").write_text("base\n")
    _git(source, "add", "nested.txt")
    _git(source, "commit", "-qm", "nested")
    subprocess.run(
        ["git", "-c", "protocol.file.allow=always", "submodule", "add", str(source), "linked"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    _git(repository, "commit", "-qam", "gitlink")
    linked_file = repository / "linked/nested.txt"
    linked_file.write_text("first dirty\n")
    baseline = capture_workspace_baseline(repository)
    entry = next(row for row in baseline["dirty_entries"] if row["path"] == "linked")
    assert entry["file_type"] == "gitlink"
    assert entry["content_binding"]["nested_status_sha256"].startswith("sha256:")
    linked_file.write_text("other dirty\n")
    _git(repository / "linked", "config", "user.email", "tests@example.invalid")
    _git(repository / "linked", "config", "user.name", "Tests")
    _git(repository / "linked", "add", "nested.txt")
    _git(repository / "linked", "commit", "-qm", "advance nested head")
    assert "dirty_entry_changed" in {
        issue.code for issue in validate_workspace_baseline(repository, baseline)
    }


def test_bootstrap_adoption_rejects_status_archive_and_index_mismatch(
    repository: Path, tmp_path: Path
) -> None:
    (repository / "tracked.txt").write_text("dirty\n")
    candidate = repository / "orchestrator/retirement/preexisting.py"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("# existed before capture\n")
    capture = tmp_path / "capture"
    capture.mkdir(mode=0o700)
    (capture / "head.txt").write_bytes(
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository)
    )
    (capture / "status.z").write_bytes(
        subprocess.check_output(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=repository,
        )
    )
    (capture / "index-entries.z").write_bytes(
        subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=repository)
    )
    index_path = Path(_git(repository, "rev-parse", "--path-format=absolute", "--git-path", "index"))
    (capture / "index.sha256").write_text(hashlib.sha256(index_path.read_bytes()).hexdigest() + "\n")
    with tarfile.open(capture / "worktree.tar", "w") as archive:
        for path in sorted(repository.iterdir()):
            if path.name != ".git":
                archive.add(path, arcname=path.name, recursive=True)
    archive_bytes = (capture / "worktree.tar").read_bytes()
    (capture / "worktree.tar.sha256").write_text(hashlib.sha256(archive_bytes).hexdigest() + "\n")
    (capture / "tar.stderr").write_bytes(b"")
    assert adopt_bootstrap_workspace(repository, capture)["dirty_entry_count"] == 2
    capture_link = tmp_path / "capture-link"
    capture_link.symlink_to(capture, target_is_directory=True)
    with pytest.raises(SourceBindingError, match="bootstrap_root_unreadable"):
        adopt_bootstrap_workspace(repository, capture_link)

    original_status = (capture / "status.z").read_bytes()
    (capture / "status.z").write_bytes(original_status + b"?? missing.txt\0")
    with pytest.raises(SourceBindingError, match="bootstrap_live_mismatch"):
        adopt_bootstrap_workspace(repository, capture)
    (capture / "status.z").write_bytes(original_status)

    (capture / "status.z").write_bytes(b" M tracked.txt\0")
    with pytest.raises(SourceBindingError, match="archive_status_candidate_mismatch"):
        adopt_bootstrap_workspace(repository, capture)
    (capture / "status.z").write_bytes(original_status)

    original_index_entries = (capture / "index-entries.z").read_bytes()
    (capture / "index-entries.z").write_bytes(b"malformed\0")
    with pytest.raises(SourceBindingError, match="malformed_index_entries"):
        adopt_bootstrap_workspace(repository, capture)
    (capture / "index-entries.z").write_bytes(original_index_entries)

    original_archive_digest = (capture / "worktree.tar.sha256").read_text()
    (capture / "worktree.tar.sha256").write_text("0" * 64 + "\n")
    with pytest.raises(SourceBindingError, match="bootstrap_archive_digest_mismatch"):
        adopt_bootstrap_workspace(repository, capture)
    (capture / "worktree.tar.sha256").write_text(original_archive_digest)

    (repository / "tracked.txt").write_text("other dirty bytes\n")
    with pytest.raises(SourceBindingError, match="bootstrap_live_mismatch"):
        adopt_bootstrap_workspace(repository, capture)

    (repository / "tracked.txt").write_text("dirty\n")
    original_archive = (capture / "worktree.tar").read_bytes()
    with tarfile.open(capture / "worktree.tar", "a") as archive:
        duplicate = tarfile.TarInfo("tracked.txt")
        duplicate.size = 0
        archive.addfile(duplicate)
    changed_archive = (capture / "worktree.tar").read_bytes()
    (capture / "worktree.tar.sha256").write_text(hashlib.sha256(changed_archive).hexdigest() + "\n")
    with pytest.raises(SourceBindingError, match="duplicate_archive_member"):
        adopt_bootstrap_workspace(repository, capture)

    (capture / "worktree.tar").write_bytes(original_archive)
    with tarfile.open(capture / "worktree.tar", "a") as archive:
        hardlink = tarfile.TarInfo("hardlink")
        hardlink.type = tarfile.LNKTYPE
        hardlink.linkname = "tracked.txt"
        archive.addfile(hardlink)
    changed_archive = (capture / "worktree.tar").read_bytes()
    (capture / "worktree.tar.sha256").write_text(hashlib.sha256(changed_archive).hexdigest() + "\n")
    with pytest.raises(SourceBindingError, match="unsupported_file_type:hardlink"):
        adopt_bootstrap_workspace(repository, capture)


def test_bootstrap_adoption_rejects_dirty_gitlink(
    repository: Path, tmp_path: Path
) -> None:
    source = tmp_path / "nested-source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.email", "tests@example.invalid")
    _git(source, "config", "user.name", "Tests")
    (source / "nested.txt").write_text("base\n")
    _git(source, "add", "nested.txt")
    _git(source, "commit", "-qm", "nested")
    subprocess.run(["git", "-c", "protocol.file.allow=always", "submodule", "add", str(source), "linked"], cwd=repository, check=True, capture_output=True)
    _git(repository, "commit", "-qam", "gitlink")
    (repository / "linked/nested.txt").write_text("dirty\n")
    capture = tmp_path / "gitlink-capture"
    capture.mkdir(mode=0o700)
    (capture / "head.txt").write_bytes(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository))
    (capture / "status.z").write_bytes(subprocess.check_output(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=repository))
    (capture / "index-entries.z").write_bytes(subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=repository))
    index_path = Path(_git(repository, "rev-parse", "--path-format=absolute", "--git-path", "index"))
    (capture / "index.sha256").write_text(hashlib.sha256(index_path.read_bytes()).hexdigest() + "\n")
    with tarfile.open(capture / "worktree.tar", "w") as archive:
        for path in sorted(repository.iterdir()):
            if path.name != ".git":
                archive.add(path, arcname=path.name, recursive=True)
    archive_bytes = (capture / "worktree.tar").read_bytes()
    (capture / "worktree.tar.sha256").write_text(hashlib.sha256(archive_bytes).hexdigest() + "\n")
    (capture / "tar.stderr").write_bytes(b"")
    with pytest.raises(SourceBindingError, match="bootstrap_gitlink_unsupported"):
        adopt_bootstrap_workspace(repository, capture)


def test_non_target_sources_select_and_revalidate_both_binding_lanes(
    repository: Path,
) -> None:
    tracked_paths = [repository / f"tracked-source-{index}.yaml" for index in range(9)]
    protected = repository / "protected-source.yaml"
    for tracked in tracked_paths:
        tracked.write_text(f"{tracked.name}\n")
    protected.write_text("base\n")
    _git(repository, "add", *(path.name for path in tracked_paths), protected.name)
    _git(repository, "commit", "-qm", "sources")
    protected.write_text("owner bytes\n")
    baseline = capture_workspace_baseline(repository, [protected.name])
    baseline_path = repository / "workspace-baseline.json"
    baseline_path.write_text(json.dumps(baseline, sort_keys=True) + "\n")
    handoff_path = repository / "handoff.json"
    handoff_path.write_text(
        json.dumps(
            {
                "yaml_retirement_handoff": {
                    "schema_version": "procedure_first_yaml_retirement_handoff.v1",
                    "captured_at_commit": "1" * 40,
                    "queues": [
                        {
                            "queue_id": "tracked-lane-a",
                            "paths": [path.name for path in tracked_paths[:7]],
                        },
                        {
                            "queue_id": "tracked-lane-b",
                            "paths": [tracked_paths[7].name],
                        },
                        {
                            "queue_id": "tracked-lane-c",
                            "paths": [tracked_paths[8].name],
                        },
                        {"queue_id": "protected-lane", "paths": [protected.name]},
                    ],
                }
            },
            sort_keys=True,
        )
        + "\n"
    )
    record = build_non_target_sources(
        repository,
        handoff_path.name,
        baseline_path.name,
        ["tracked-lane-a", "tracked-lane-b", "tracked-lane-c"],
        "protected-lane",
    )
    assert record["source_count"] == 10
    assert [row["binding_source"] for row in record["source_rows"]].count(
        "tracked_source_binding"
    ) == 9
    assert [row["binding_source"] for row in record["source_rows"]].count(
        "workspace_protected_binding"
    ) == 1
    tracked_queue_counts = sorted(
        sum(
            row["queue_id"] == queue_id
            for row in record["source_rows"]
            if row["binding_source"] == "tracked_source_binding"
        )
        for queue_id in {
            row["queue_id"]
            for row in record["source_rows"]
            if row["binding_source"] == "tracked_source_binding"
        }
    )
    assert tracked_queue_counts == [1, 1, 7]
    assert validate_non_target_sources(repository, record) == []
    record_path = repository / "non-target.json"
    record_path.write_text(json.dumps(record) + "\n")
    completed = subprocess.run(
        [sys.executable, "-m", "orchestrator.retirement.source_bindings", "validate-non-target-sources", "--repository-root", str(repository), "--record", record_path.name],
        cwd=repository.parent,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1])},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    tracked_paths[0].write_text("changed\n")
    assert "tracked_source_changed" in {
        issue.code for issue in validate_non_target_sources(repository, record)
    }


def _recompute_non_target_digests(record: dict[str, object]) -> None:
    rows = record["source_rows"]
    assert isinstance(rows, list)
    record["row_set_sha256"] = _set_digest(rows)
    record["normalized_record_sha256"] = _canonical_sha256(
        record, exclude={"normalized_record_sha256"}
    )


def test_non_target_validator_closes_row_keys_and_queue_membership(
    repository: Path,
) -> None:
    sources = [repository / f"source-{index}.yaml" for index in range(9)]
    holdout = repository / "holdout.yaml"
    for source in sources:
        source.write_text("source\n")
    holdout.write_text("base\n")
    _git(repository, "add", *(path.name for path in sources), holdout.name)
    _git(repository, "commit", "-qm", "sources")
    holdout.write_text("owner\n")
    baseline = capture_workspace_baseline(repository, [holdout.name])
    baseline_path = repository / "baseline.json"
    baseline_path.write_text(json.dumps(baseline) + "\n")
    handoff_path = repository / "handoff.json"
    handoff_path.write_text(json.dumps({"yaml_retirement_handoff": {"schema_version": "procedure_first_yaml_retirement_handoff.v1", "captured_at_commit": "1" * 40, "queues": [{"queue_id": "tracked-a", "paths": [path.name for path in sources[:7]]}, {"queue_id": "tracked-b", "paths": [sources[7].name]}, {"queue_id": "tracked-c", "paths": [sources[8].name]}, {"queue_id": "protected", "paths": [holdout.name]}]}}) + "\n")
    record = build_non_target_sources(repository, handoff_path.name, baseline_path.name, ["tracked-a", "tracked-b", "tracked-c"], "protected")

    row = next(
        row
        for row in record["source_rows"]
        if row["binding_source"] == "tracked_source_binding"
    )
    row["extra"] = None
    _recompute_non_target_digests(record)
    assert "source_rows_invalid" in {
        issue.code for issue in validate_non_target_sources(repository, record)
    }
    row.pop("extra")
    other_row = next(
        candidate
        for candidate in record["source_rows"]
        if candidate.get("queue_id") == "tracked-b"
    )
    row["queue_id"], other_row["queue_id"] = (
        other_row["queue_id"],
        row["queue_id"],
    )
    row["disposition_owner"] = row["queue_id"]
    other_row["disposition_owner"] = other_row["queue_id"]
    _recompute_non_target_digests(record)
    assert "source_queue_membership_mismatch" in {issue.code for issue in validate_non_target_sources(repository, record)}

    record["source_rows"].pop()
    assert "source_partition_mismatch" in {
        issue.code for issue in validate_non_target_sources(repository, record)
    }


def test_cli_resolves_record_paths_from_repository_root(
    repository: Path, tmp_path: Path
) -> None:
    baseline = capture_workspace_baseline(repository)
    (repository / "baseline.json").write_text(json.dumps(baseline) + "\n")
    project_root = Path(__file__).parents[1]
    completed = subprocess.run(
        [sys.executable, "-m", "orchestrator.retirement.source_bindings", "validate-workspace-baseline", "--repository-root", str(repository), "--record", "baseline.json", "--allowed-addition", "baseline.json"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(project_root)},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_source_record_reads_reject_absolute_and_symlink_paths(
    repository: Path,
) -> None:
    baseline = capture_workspace_baseline(repository)
    target = repository / "baseline.json"
    target.write_text(json.dumps(baseline) + "\n")
    os.symlink(target.name, repository / "baseline-link.json")
    (repository / "linked-parent").symlink_to(repository, target_is_directory=True)

    with pytest.raises(SourceBindingError, match="repository_relative"):
        validate_workspace_baseline(repository, target)
    with pytest.raises(SourceBindingError, match="repository_path_unreadable"):
        validate_workspace_baseline(repository, "baseline-link.json")
    with pytest.raises(SourceBindingError, match="repository_path_.*unreadable"):
        validate_workspace_baseline(repository, "linked-parent/baseline.json")


@pytest.mark.parametrize("out", ["../escaped.json", "/tmp/absolute-output.json"])
def test_capture_cli_rejects_non_repository_relative_output(
    repository: Path, out: str
) -> None:
    outside = repository.parent / "escaped.json"
    outside.unlink(missing_ok=True)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.retirement.source_bindings",
            "capture-workspace-baseline",
            "--repository-root",
            str(repository),
            "--out",
            out,
        ],
        cwd=repository,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1])},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "invalid_repository_relative_path" in completed.stdout
    assert not outside.exists()


@pytest.mark.parametrize("link_final", [False, True])
def test_capture_cli_rejects_symlinked_output_component_without_mutating_target(
    repository: Path, link_final: bool
) -> None:
    outside = repository.parent / "outside"
    outside.mkdir()
    target = outside / "out.json"
    target.write_text("owner bytes\n")
    if link_final:
        (repository / "out.json").symlink_to(target)
        output = "out.json"
    else:
        (repository / "linked-output").symlink_to(outside, target_is_directory=True)
        output = "linked-output/out.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.retirement.source_bindings",
            "capture-workspace-baseline",
            "--repository-root",
            str(repository),
            "--out",
            output,
        ],
        cwd=repository,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1])},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "repository_path_" in completed.stdout
    assert target.read_text() == "owner bytes\n"


def test_source_writer_restores_final_entry_raced_after_last_observation(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = repository / "output.json"
    output.write_text("old bytes\n")
    outside = repository.parent / "outside.json"
    outside.write_text("owner bytes\n")
    real_renameat2 = safe_io._renameat2
    raced = False

    def race_after_capture(parent, old_name, new_name, flags):
        nonlocal raced
        if not raced:
            raced = True
            output.unlink()
            output.symlink_to(outside)
        return real_renameat2(parent, old_name, new_name, flags)

    monkeypatch.setattr(safe_io, "_renameat2", race_after_capture)

    with pytest.raises(SourceBindingError, match="concurrent_mutation"):
        _write_repository_bytes(repository, output.name, b"new bytes\n")

    assert output.is_symlink()
    assert output.resolve() == outside
    assert outside.read_bytes() == b"owner bytes\n"


def test_source_writer_rejects_detached_logical_parent(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = repository / "evidence"
    evidence.mkdir()
    output = evidence / "output.json"
    output.write_bytes(b"original bytes\n")
    detached = repository / "detached"
    real_boundary = safe_io._conditional_publish_boundary
    raced = False

    def detach_parent(stage, parent, temporary_name, destination_name):
        nonlocal raced
        if stage == "before_parent_validation" and not raced:
            raced = True
            evidence.rename(detached)
            evidence.mkdir()
        return real_boundary(stage, parent, temporary_name, destination_name)

    monkeypatch.setattr(safe_io, "_conditional_publish_boundary", detach_parent)

    with pytest.raises(SourceBindingError, match="logical_parent_changed"):
        _write_repository_bytes(
            repository, "evidence/output.json", b"publisher bytes\n"
        )

    assert not (evidence / "output.json").exists()
    assert (detached / "output.json").read_bytes() == b"original bytes\n"

def test_non_target_builder_rejects_non_ten_source_partition(repository: Path) -> None:
    source = repository / "one.yaml"
    holdout = repository / "holdout.yaml"
    source.write_text("one\n")
    holdout.write_text("base\n")
    _git(repository, "add", source.name, holdout.name)
    _git(repository, "commit", "-qm", "sources")
    holdout.write_text("owner\n")
    baseline = capture_workspace_baseline(repository, [holdout.name])
    baseline_path = repository / "workspace-baseline.json"
    baseline_path.write_text(json.dumps(baseline) + "\n")
    handoff_path = repository / "handoff.json"
    handoff_path.write_text(
        json.dumps(
            {
                "yaml_retirement_handoff": {
                    "schema_version": "procedure_first_yaml_retirement_handoff.v1",
                    "captured_at_commit": "1" * 40,
                    "queues": [
                        {"queue_id": "tracked", "paths": [source.name]},
                        {"queue_id": "protected", "paths": [holdout.name]},
                    ],
                }
            }
        )
        + "\n"
    )
    with pytest.raises(SourceBindingError, match="non_target_source_count_invalid"):
        build_non_target_sources(
            repository,
            handoff_path.name,
            baseline_path.name,
            ["tracked"],
            "protected",
        )


@pytest.mark.parametrize(
    "tracked_queue_sizes",
    [
        (9,),
        (6, 2, 1),
    ],
)
def test_non_target_builder_rejects_wrong_tracked_queue_partition(
    repository: Path, tracked_queue_sizes: tuple[int, ...]
) -> None:
    sources = [repository / f"source-{index:02d}.yaml" for index in range(9)]
    protected = repository / "protected.yaml"
    for source in sources:
        source.write_text(f"{source.name}\n")
    protected.write_text("base\n")
    _git(repository, "add", *(path.name for path in sources), protected.name)
    _git(repository, "commit", "-qm", "sources")
    protected.write_text("owner\n")
    baseline = capture_workspace_baseline(repository, [protected.name])
    baseline_path = repository / "workspace-baseline.json"
    baseline_path.write_text(json.dumps(baseline) + "\n")

    queues: list[dict[str, object]] = []
    offset = 0
    tracked_queue_ids: list[str] = []
    for index, size in enumerate(tracked_queue_sizes):
        queue_id = f"tracked-{index}"
        tracked_queue_ids.append(queue_id)
        queues.append(
            {
                "queue_id": queue_id,
                "paths": [path.name for path in sources[offset : offset + size]],
            }
        )
        offset += size
    queues.append({"queue_id": "protected", "paths": [protected.name]})
    handoff_path = repository / "handoff.json"
    handoff_path.write_text(
        json.dumps(
            {
                "yaml_retirement_handoff": {
                    "schema_version": "procedure_first_yaml_retirement_handoff.v1",
                    "captured_at_commit": "1" * 40,
                    "queues": queues,
                }
            }
        )
        + "\n"
    )

    with pytest.raises(
        SourceBindingError, match="non_target_queue_partition_invalid"
    ):
        build_non_target_sources(
            repository,
            handoff_path.name,
            baseline_path.name,
            tracked_queue_ids,
            "protected",
        )


@pytest.mark.parametrize("mutation", ["one_tracked_queue", "six_two_one", "shared_protected_queue"])
def test_non_target_shape_requires_exact_queue_partition(mutation: str) -> None:
    record = json.loads(
        Path(
            "tests/fixtures/retirement_broad_evidence/non_target_queue_sources.v1.json"
        ).read_text()
    )
    tracked_rows = [
        row
        for row in record["source_rows"]
        if row["binding_source"] == "tracked_source_binding"
    ]
    protected_row = next(
        row
        for row in record["source_rows"]
        if row["binding_source"] == "workspace_protected_binding"
    )
    if mutation == "one_tracked_queue":
        assignments = ["tracked-a"] * 9
    elif mutation == "six_two_one":
        assignments = ["tracked-a"] * 6 + ["tracked-b"] * 2 + ["tracked-c"]
    else:
        assignments = [row["queue_id"] for row in tracked_rows]
        protected_row["queue_id"] = assignments[0]
        protected_row["disposition_owner"] = assignments[0]
    for row, queue_id in zip(tracked_rows, assignments, strict=True):
        row["queue_id"] = queue_id
        row["disposition_owner"] = queue_id
    _recompute_non_target_digests(record)

    assert "source_partition_mismatch" in {
        issue.code for issue in validate_workspace_record_shape(record)
    }


def test_non_target_live_validation_rejects_unrecorded_selected_queue_path(
    repository: Path,
) -> None:
    sources = [repository / f"source-{index:02d}.yaml" for index in range(10)]
    protected = repository / "protected.yaml"
    for source in sources:
        source.write_text(f"{source.name}\n")
    protected.write_text("base\n")
    _git(repository, "add", *(path.name for path in sources), protected.name)
    _git(repository, "commit", "-qm", "sources")
    protected.write_text("owner\n")
    baseline = capture_workspace_baseline(repository, [protected.name])
    baseline_path = repository / "workspace-baseline.json"
    baseline_path.write_text(json.dumps(baseline) + "\n")
    handoff_path = repository / "handoff.json"
    handoff = {
        "yaml_retirement_handoff": {
            "schema_version": "procedure_first_yaml_retirement_handoff.v1",
            "captured_at_commit": "1" * 40,
            "queues": [
                {"queue_id": "tracked-a", "paths": [path.name for path in sources[:7]]},
                {"queue_id": "tracked-b", "paths": [sources[7].name]},
                {"queue_id": "tracked-c", "paths": [sources[8].name]},
                {"queue_id": "protected", "paths": [protected.name]},
            ],
        }
    }
    handoff_path.write_text(json.dumps(handoff) + "\n")
    record = build_non_target_sources(
        repository,
        handoff_path.name,
        baseline_path.name,
        ["tracked-a", "tracked-b", "tracked-c"],
        "protected",
    )

    handoff["yaml_retirement_handoff"]["queues"][0]["paths"].append(sources[9].name)
    handoff_bytes = (json.dumps(handoff) + "\n").encode()
    handoff_path.write_bytes(handoff_bytes)
    record["handoff_binding"]["sha256"] = (
        "sha256:" + hashlib.sha256(handoff_bytes).hexdigest()
    )
    _recompute_non_target_digests(record)

    assert "source_authority_partition_mismatch" in {
        issue.code for issue in validate_non_target_sources(repository, record)
    }


@pytest.mark.parametrize("invalid_binding", [None, []])
def test_non_target_live_validator_returns_shape_issues_before_dereference(
    repository: Path, invalid_binding: object
) -> None:
    fixture = json.loads(
        Path(
            "tests/fixtures/retirement_broad_evidence/non_target_queue_sources.v1.json"
        ).read_text()
    )
    fixture["handoff_binding"] = invalid_binding
    fixture["normalized_record_sha256"] = _canonical_sha256(
        fixture, exclude={"normalized_record_sha256"}
    )

    issues = validate_non_target_sources(repository, fixture)

    assert "handoff_binding_invalid" in {issue.code for issue in issues}


def test_commit_live_validator_returns_shape_issues_before_dereference(
    repository: Path,
) -> None:
    control = json.loads(
        Path(
            "tests/fixtures/retirement_broad_evidence/precommit_control.v1.json"
        ).read_text()
    )
    control["durable_authority_bindings"] = 0
    control_path = repository / "invalid-control.json"
    control_path.write_text(json.dumps(control) + "\n")

    issues = validate_commit_boundary(repository, control_path=control_path.name)

    assert "durable_authority_invalid" in {issue.code for issue in issues}


def test_workspace_shape_rejects_boolean_directory_descendant_count(
    repository: Path,
) -> None:
    protected = repository / "protected"
    protected.mkdir()
    (protected / "child.txt").write_text("child\n")
    record = capture_workspace_baseline(repository, [protected.name])
    entry = record["protected_paths"][0]
    assert entry["content_binding"]["descendant_count"] == 1
    entry["content_binding"]["descendant_count"] = True
    entry["normalized_entry_sha256"] = _canonical_sha256(
        entry, exclude={"normalized_entry_sha256"}
    )
    record["normalized_baseline_sha256"] = _canonical_sha256(
        record, exclude={"normalized_baseline_sha256"}
    )

    assert "workspace_entry_invalid" in {
        issue.code for issue in validate_workspace_record_shape(record)
    }


@pytest.mark.parametrize(
    ("fixture_name", "field", "value", "expected_code"),
    [
        (
            "non_target_queue_sources.v1.json",
            "source_count",
            10.0,
            "source_partition_mismatch",
        ),
        ("query.v1.json", "path_count", True, "query_partition_invalid"),
        ("query.v1.json", "path_count", 1.0, "query_partition_invalid"),
        (
            "precommit_control.v1.json",
            "allowed_delta_count",
            2.0,
            "allowed_delta_partition_mismatch",
        ),
    ],
)
def test_source_shapes_require_exact_integer_count_types(
    fixture_name: str, field: str, value: object, expected_code: str
) -> None:
    fixture = json.loads(
        (
            Path("tests/fixtures/retirement_broad_evidence") / fixture_name
        ).read_text()
    )
    fixture[field] = value
    digest_field = {
        "non_target_queue_sources.v1.json": "normalized_record_sha256",
        "query.v1.json": "normalized_query_sha256",
        "precommit_control.v1.json": "normalized_control_sha256",
    }[fixture_name]
    exclusions = {digest_field}
    if fixture_name == "precommit_control.v1.json":
        exclusions.add("final_message_binding")
    fixture[digest_field] = _canonical_sha256(fixture, exclude=exclusions)

    assert expected_code in {
        issue.code for issue in validate_workspace_record_shape(fixture)
    }


def _write_valid_durable_authority(path: Path) -> None:
    path.write_bytes(
        Path("tests/fixtures/retirement_broad_evidence/review.v1.json").read_bytes()
    )


def _prepare_precommit_control(
    repository: Path,
) -> tuple[dict[str, object], Path, dict[str, object]]:
    baseline = _bootstrap_workspace_record(capture_workspace_baseline(repository))
    baseline_path = repository / "baseline.json"
    authority_path = repository / "authority.json"
    allowed_path = repository / "allowed.txt"
    baseline_path.write_text(json.dumps(baseline, sort_keys=True) + "\n")
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("allowed\n")
    allowed = [baseline_path.name, authority_path.name, allowed_path.name]
    _git(repository, "add", *allowed)
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Retirement test commit",
        bootstrap_workspace_baseline=baseline_path.name,
    )
    control_path = repository / receipt["control_path"]
    return receipt, control_path, json.loads(control_path.read_text())


def _refresh_control_digest_and_final_message(
    repository: Path, control: dict[str, object]
) -> None:
    control["normalized_control_sha256"] = _canonical_sha256(
        control,
        exclude={"normalized_control_sha256", "final_message_binding"},
    )
    base_message = (
        repository / control["base_message_binding"]["path"]
    ).read_bytes()
    final_message = _derive_final_message_bytes(
        base_message,
        control["transaction_id"],
        control["normalized_control_sha256"],
    )
    final_path = repository / control["final_message_binding"]["path"]
    final_path.write_bytes(final_message)
    control["final_message_binding"].update(
        {
            "sha256": "sha256:" + hashlib.sha256(final_message).hexdigest(),
            "byte_count": len(final_message),
        }
    )


def _commit_prepared_control(
    repository: Path, control: dict[str, object]
) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "--literal-pathspecs",
            "commit",
            "--only",
            "--no-gpg-sign",
            f"--pathspec-from-file={repository / control['pathspec_file_binding']['path']}",
            "--pathspec-file-nul",
            f"--file={repository / control['final_message_binding']['path']}",
            "--cleanup=verbatim",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )


def _commit_with_additional_baseline_records(
    repository: Path,
    baseline: dict[str, object],
    additional_records: list[tuple[str, dict[str, object]]],
) -> None:
    baseline_path = repository / "baseline.json"
    baseline_path.write_text(json.dumps(baseline, sort_keys=True) + "\n")
    additional_paths: list[Path] = []
    for name, record in additional_records:
        path = repository / name
        path.write_text(json.dumps(record, sort_keys=True) + "\n")
        additional_paths.append(path)
    authority_path = repository / "authority.json"
    _write_valid_durable_authority(authority_path)
    allowed_path = repository / "allowed.txt"
    allowed_path.write_text("allowed\n")
    allowed = [
        allowed_path.name,
        authority_path.name,
        baseline_path.name,
        *(path.name for path in additional_paths),
    ]
    _git(repository, "add", *allowed)
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Retirement test commit",
        **(
            {"bootstrap_workspace_baseline": baseline_path.name}
            if baseline["schema_version"]
            == "bootstrap_workspace_baseline.v1"
            else {"workspace_baseline": baseline_path.name}
        ),
    )
    control_path = repository / receipt["control_path"]
    _commit_prepared_control(repository, json.loads(control_path.read_text()))
    shutil.rmtree(control_path.parent)


def _bootstrap_workspace_record(record: dict[str, object]) -> dict[str, object]:
    bootstrap = json.loads(json.dumps(record))
    bootstrap["schema_version"] = "bootstrap_workspace_baseline.v1"
    bootstrap["bootstrap_capture_bindings"] = {
        "producer_contract_version": "task1_first_write_capture.v1",
        "head_file_sha256": f"sha256:{'0' * 64}",
        "status_file_sha256": f"sha256:{'0' * 64}",
        "index_entries_file_sha256": f"sha256:{'0' * 64}",
        "index_file_sha256": bootstrap["index_sha256"],
        "archive_sha256": f"sha256:{'0' * 64}",
        "tar_stderr_sha256": f"sha256:{'0' * 64}",
    }
    bootstrap["raw_archive_not_persisted"] = True
    bootstrap["normalized_baseline_sha256"] = _canonical_sha256(
        bootstrap, exclude={"normalized_baseline_sha256"}
    )
    return bootstrap


def _commit_initial_controlled_baseline(
    repository: Path,
    *,
    bootstrap: bool = True,
    protected_paths: tuple[str, ...] = (),
) -> Path:
    baseline_path = repository / "baseline.json"
    baseline = capture_workspace_baseline(repository, protected_paths)
    if bootstrap:
        baseline = _bootstrap_workspace_record(baseline)
    baseline_path.write_text(json.dumps(baseline, sort_keys=True) + "\n")
    authority_path = repository / "authority.json"
    allowed_path = repository / "allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("allowed\n")
    allowed = [allowed_path.name, authority_path.name, baseline_path.name]
    _git(repository, "add", *allowed)
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Initial retirement test commit",
        **(
            {"bootstrap_workspace_baseline": baseline_path.name}
            if bootstrap
            else {"workspace_baseline": baseline_path.name}
        ),
    )
    control_path = repository / receipt["control_path"]
    _commit_prepared_control(repository, json.loads(control_path.read_text()))
    shutil.rmtree(control_path.parent)
    return baseline_path


def _commit_bootstrap_to_workspace_baseline(repository: Path) -> Path:
    (
        _inherited_baseline_path,
        replacement_baseline_path,
        authority_path,
        _allowed_path,
        allowed,
    ) = _prepare_bootstrap_to_workspace_replacement(
        repository, workspace_drift=None
    )
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Bootstrap adoption retirement test commit",
        workspace_baseline=replacement_baseline_path.name,
    )
    control_path = repository / receipt["control_path"]
    _commit_prepared_control(repository, json.loads(control_path.read_text()))
    shutil.rmtree(control_path.parent)
    return replacement_baseline_path


def test_reconstruction_selects_parent_bound_baseline_among_same_schema_records(
    repository: Path,
) -> None:
    baseline = _bootstrap_workspace_record(capture_workspace_baseline(repository))
    unrelated_fixture = json.loads(json.dumps(baseline))
    unrelated_fixture["head"] = "0" * 40
    unrelated_fixture["normalized_baseline_sha256"] = _canonical_sha256(
        unrelated_fixture, exclude={"normalized_baseline_sha256"}
    )
    assert validate_workspace_record_shape(unrelated_fixture) == []
    _commit_with_additional_baseline_records(
        repository,
        baseline,
        [("same-schema-fixture.json", unrelated_fixture)],
    )

    assert validate_commit_boundary(
        repository,
        expected_commit_subject="Retirement test commit",
        reconstruct=True,
    ) == []


def test_reconstruction_ignores_non_closed_parent_bound_baseline_record(
    repository: Path,
) -> None:
    baseline = _bootstrap_workspace_record(capture_workspace_baseline(repository))
    non_closed_fixture = json.loads(json.dumps(baseline))
    non_closed_fixture["unexpected"] = "fixture-only"
    non_closed_fixture["normalized_baseline_sha256"] = _canonical_sha256(
        non_closed_fixture, exclude={"normalized_baseline_sha256"}
    )
    assert "schema_keys_mismatch" in {
        issue.code for issue in validate_workspace_record_shape(non_closed_fixture)
    }
    _commit_with_additional_baseline_records(
        repository,
        baseline,
        [("non-closed-same-schema-fixture.json", non_closed_fixture)],
    )

    assert validate_commit_boundary(
        repository,
        expected_commit_subject="Retirement test commit",
        reconstruct=True,
    ) == []


def test_reconstruction_ignores_parent_bound_baseline_modified_in_commit(
    repository: Path,
) -> None:
    preexisting_fixture = repository / "preexisting-same-schema-fixture.json"
    seeded_record = capture_workspace_baseline(repository)
    seeded_record["head"] = "0" * 40
    seeded_record["normalized_baseline_sha256"] = _canonical_sha256(
        seeded_record, exclude={"normalized_baseline_sha256"}
    )
    preexisting_fixture.write_text(json.dumps(seeded_record, sort_keys=True) + "\n")
    _git(repository, "add", preexisting_fixture.name)
    _git(repository, "commit", "-qm", "seed same-schema fixture")

    baseline = _bootstrap_workspace_record(capture_workspace_baseline(repository))
    preexisting_fixture.write_text(json.dumps(baseline, sort_keys=True) + "\n")
    _commit_with_additional_baseline_records(
        repository,
        baseline,
        [(preexisting_fixture.name, baseline)],
    )

    assert validate_commit_boundary(
        repository,
        expected_commit_subject="Retirement test commit",
        reconstruct=True,
    ) == []


def test_reconstruction_rejects_two_parent_bound_closed_baselines(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _bootstrap_workspace_record(capture_workspace_baseline(repository))
    second_baseline = json.loads(json.dumps(baseline))
    assert validate_workspace_record_shape(second_baseline) == []
    monkeypatch.setattr(
        retirement_source_bindings,
        "_validate_precommit_workspace_baseline_selection",
        lambda *args, **kwargs: None,
    )
    _commit_with_additional_baseline_records(
        repository,
        baseline,
        [("second-eligible-baseline.json", second_baseline)],
    )

    assert validate_commit_boundary(
        repository,
        expected_commit_subject="Retirement test commit",
        reconstruct=True,
    ) == [
        SourceBindingIssue(
            "commit_reconstruction_failed",
            detail="commit_workspace_baseline_not_unique",
        )
    ]


def test_precommit_builder_rejects_replacing_inherited_baseline(
    repository: Path,
) -> None:
    baseline_path = _commit_initial_controlled_baseline(repository)
    baseline_path.write_text(
        json.dumps(capture_workspace_baseline(repository), sort_keys=True) + "\n"
    )
    authority_path = repository / "replacement-authority.json"
    allowed_path = repository / "replacement-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("replacement\n")
    allowed = [allowed_path.name, authority_path.name, baseline_path.name]
    _git(repository, "add", *allowed)
    control_root = repository / ".git/retirement-commit-controls"
    before_controls = set(control_root.iterdir()) if control_root.exists() else set()

    with pytest.raises(
        SourceBindingError,
        match="workspace_baseline_inheritance_invalid",
    ):
        build_precommit_control(
            repository,
            allowed_paths=allowed,
            durable_authority_paths=[authority_path.name],
            commit_subject="Replacement retirement test commit",
            workspace_baseline=baseline_path.name,
        )
    assert (
        set(control_root.iterdir()) if control_root.exists() else set()
    ) == before_controls


def test_precommit_builder_rejects_new_baseline_candidate_with_inherited_selection(
    repository: Path,
) -> None:
    baseline_path = _commit_bootstrap_to_workspace_baseline(repository)
    extra_baseline_path = repository / "extra-baseline.json"
    extra_baseline_path.write_text(
        json.dumps(capture_workspace_baseline(repository), sort_keys=True) + "\n"
    )
    authority_path = repository / "second-authority.json"
    allowed_path = repository / "second-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("second\n")
    allowed = [allowed_path.name, authority_path.name, extra_baseline_path.name]
    _git(repository, "add", *allowed)
    control_root = repository / ".git/retirement-commit-controls"
    before_controls = set(control_root.iterdir()) if control_root.exists() else set()

    with pytest.raises(
        SourceBindingError,
        match="workspace_baseline_candidate_set_invalid",
    ):
        build_precommit_control(
            repository,
            allowed_paths=allowed,
            durable_authority_paths=[authority_path.name],
            commit_subject="Second retirement test commit",
            workspace_baseline=baseline_path.name,
        )
    assert (
        set(control_root.iterdir()) if control_root.exists() else set()
    ) == before_controls


def _prepare_bootstrap_to_workspace_replacement(
    repository: Path, *, workspace_drift: str | None
) -> tuple[Path, Path, Path, Path, list[str]]:
    bound_path = repository / "tracked.txt"
    bound_path.write_text("inherited dirty bytes\n")
    inherited_baseline_path = _commit_initial_controlled_baseline(
        repository, bootstrap=True
    )
    if workspace_drift == "same_status_bytes":
        bound_path.write_text("replacement dirty bytes\n")
    elif workspace_drift == "delete":
        bound_path.unlink()
    elif workspace_drift == "mode":
        bound_path.chmod(0o755)
    elif workspace_drift is not None:
        raise AssertionError(workspace_drift)
    replacement_baseline_path = repository / "replacement-baseline.json"
    replacement_baseline_path.write_text(
        json.dumps(capture_workspace_baseline(repository), sort_keys=True) + "\n"
    )
    authority_path = repository / "replacement-authority.json"
    allowed_path = repository / "replacement-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("replacement\n")
    allowed = [
        allowed_path.name,
        authority_path.name,
        replacement_baseline_path.name,
    ]
    _git(repository, "add", "--", *allowed)
    return (
        inherited_baseline_path,
        replacement_baseline_path,
        authority_path,
        allowed_path,
        allowed,
    )


def _prepare_new_baseline_candidate(
    repository: Path,
    *,
    schema: str,
    prefix: str,
) -> tuple[Path, Path, list[str]]:
    record = capture_workspace_baseline(repository)
    if schema == "bootstrap_workspace_baseline.v1":
        record = _bootstrap_workspace_record(record)
    elif schema != "workspace_baseline.v1":
        raise AssertionError(schema)
    baseline_path = repository / f"{prefix}-baseline.json"
    baseline_path.write_text(json.dumps(record, sort_keys=True) + "\n")
    authority_path = repository / f"{prefix}-authority.json"
    allowed_path = repository / f"{prefix}-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text(f"{prefix}\n")
    allowed = [baseline_path.name, authority_path.name, allowed_path.name]
    _git(repository, "add", "--", *allowed)
    return baseline_path, authority_path, allowed


def test_precommit_builder_allows_first_bootstrap_baseline(
    repository: Path,
) -> None:
    _commit_initial_controlled_baseline(repository, bootstrap=True)

    assert validate_commit_boundary(
        repository,
        expected_commit_subject="Initial retirement test commit",
        reconstruct=True,
    ) == []


def test_precommit_builder_rejects_first_workspace_baseline(
    repository: Path,
) -> None:
    baseline_path, authority_path, allowed = _prepare_new_baseline_candidate(
        repository,
        schema="workspace_baseline.v1",
        prefix="initial-workspace",
    )

    with pytest.raises(
        SourceBindingError,
        match="workspace_baseline_transition_invalid",
    ):
        build_precommit_control(
            repository,
            allowed_paths=allowed,
            durable_authority_paths=[authority_path.name],
            commit_subject="Invalid initial workspace retirement test commit",
            workspace_baseline=baseline_path.name,
        )


def test_reconstruction_rejects_first_workspace_baseline(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline_path, authority_path, allowed = _prepare_new_baseline_candidate(
        repository,
        schema="workspace_baseline.v1",
        prefix="initial-workspace",
    )
    monkeypatch.setattr(
        retirement_source_bindings,
        "_validate_precommit_workspace_baseline_selection",
        lambda *args, **kwargs: None,
    )
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Forged initial workspace retirement test commit",
        workspace_baseline=baseline_path.name,
    )
    control_path = repository / receipt["control_path"]
    _commit_prepared_control(repository, json.loads(control_path.read_text()))
    shutil.rmtree(control_path.parent)

    assert validate_commit_boundary(
        repository,
        expected_commit_subject="Forged initial workspace retirement test commit",
        reconstruct=True,
    ) == [
        SourceBindingIssue(
            "commit_reconstruction_failed",
            detail="workspace_baseline_transition_invalid",
        )
    ]


def test_precommit_builder_rejects_inherited_bootstrap_reuse(
    repository: Path,
) -> None:
    baseline_path = _commit_initial_controlled_baseline(
        repository, bootstrap=True
    )
    authority_path = repository / "reuse-authority.json"
    allowed_path = repository / "reuse-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("reuse\n")
    allowed = [authority_path.name, allowed_path.name]
    _git(repository, "add", "--", *allowed)

    with pytest.raises(
        SourceBindingError,
        match="workspace_baseline_transition_invalid",
    ):
        build_precommit_control(
            repository,
            allowed_paths=allowed,
            durable_authority_paths=[authority_path.name],
            commit_subject="Invalid bootstrap reuse retirement test commit",
            bootstrap_workspace_baseline=baseline_path.name,
        )


def test_reconstruction_rejects_inherited_bootstrap_reuse(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline_path = _commit_initial_controlled_baseline(
        repository, bootstrap=True
    )
    authority_path = repository / "reuse-authority.json"
    allowed_path = repository / "reuse-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("reuse\n")
    allowed = [authority_path.name, allowed_path.name]
    _git(repository, "add", "--", *allowed)
    monkeypatch.setattr(
        retirement_source_bindings,
        "_validate_precommit_workspace_baseline_selection",
        lambda *args, **kwargs: None,
    )
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Forged bootstrap reuse retirement test commit",
        bootstrap_workspace_baseline=baseline_path.name,
    )
    control_path = repository / receipt["control_path"]
    _commit_prepared_control(repository, json.loads(control_path.read_text()))
    shutil.rmtree(control_path.parent)

    assert validate_commit_boundary(
        repository,
        expected_commit_subject="Forged bootstrap reuse retirement test commit",
        reconstruct=True,
    ) == [
        SourceBindingIssue(
            "commit_reconstruction_failed",
            detail="workspace_baseline_transition_invalid",
        )
    ]


def test_precommit_builder_rejects_bootstrap_to_bootstrap_replacement(
    repository: Path,
) -> None:
    _commit_initial_controlled_baseline(repository, bootstrap=True)
    baseline_path, authority_path, allowed = _prepare_new_baseline_candidate(
        repository,
        schema="bootstrap_workspace_baseline.v1",
        prefix="replacement-bootstrap",
    )

    with pytest.raises(
        SourceBindingError,
        match="workspace_baseline_transition_invalid",
    ):
        build_precommit_control(
            repository,
            allowed_paths=allowed,
            durable_authority_paths=[authority_path.name],
            commit_subject="Invalid bootstrap replacement retirement test commit",
            bootstrap_workspace_baseline=baseline_path.name,
        )


def test_reconstruction_rejects_bootstrap_to_bootstrap_replacement(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _commit_initial_controlled_baseline(repository, bootstrap=True)
    baseline_path, authority_path, allowed = _prepare_new_baseline_candidate(
        repository,
        schema="bootstrap_workspace_baseline.v1",
        prefix="replacement-bootstrap",
    )
    monkeypatch.setattr(
        retirement_source_bindings,
        "_validate_precommit_workspace_baseline_selection",
        lambda *args, **kwargs: None,
    )
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Forged bootstrap replacement retirement test commit",
        bootstrap_workspace_baseline=baseline_path.name,
    )
    control_path = repository / receipt["control_path"]
    _commit_prepared_control(repository, json.loads(control_path.read_text()))
    shutil.rmtree(control_path.parent)

    assert validate_commit_boundary(
        repository,
        expected_commit_subject=(
            "Forged bootstrap replacement retirement test commit"
        ),
        reconstruct=True,
    ) == [
        SourceBindingIssue(
            "commit_reconstruction_failed",
            detail="workspace_baseline_transition_invalid",
        )
    ]


def test_precommit_builder_allows_bootstrap_to_workspace_replacement_with_preserved_rows(
    repository: Path,
) -> None:
    (
        inherited_baseline_path,
        replacement_baseline_path,
        authority_path,
        _allowed_path,
        allowed,
    ) = _prepare_bootstrap_to_workspace_replacement(
        repository, workspace_drift=None
    )
    inherited = json.loads(inherited_baseline_path.read_text())
    replacement = json.loads(replacement_baseline_path.read_text())
    assert replacement["dirty_entries"] == inherited["dirty_entries"]
    assert replacement["protected_paths"] == inherited["protected_paths"]

    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Replacement retirement test commit",
        workspace_baseline=replacement_baseline_path.name,
    )
    control_path = repository / receipt["control_path"]
    control = json.loads(control_path.read_text())
    assert control["workspace_baseline_binding"]["path"] == replacement_baseline_path.name
    _commit_prepared_control(repository, control)
    shutil.rmtree(control_path.parent)

    assert validate_commit_boundary(
        repository,
        expected_commit_subject="Replacement retirement test commit",
        reconstruct=True,
    ) == []


def test_bootstrap_to_workspace_replacement_may_extend_protected_rows(
    repository: Path,
) -> None:
    first_protected = repository / "first-protected.txt"
    added_protected = repository / "added-protected.txt"
    first_protected.write_text("first\n")
    added_protected.write_text("added\n")
    inherited_baseline_path = _commit_initial_controlled_baseline(
        repository,
        protected_paths=(first_protected.name,),
    )
    inherited = json.loads(inherited_baseline_path.read_text())
    replacement = capture_workspace_baseline(
        repository,
        [first_protected.name, added_protected.name],
    )
    replacement_baseline_path = repository / "replacement-baseline.json"
    replacement_baseline_path.write_text(
        json.dumps(replacement, sort_keys=True) + "\n"
    )
    authority_path = repository / "replacement-authority.json"
    allowed_path = repository / "replacement-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("replacement\n")
    allowed = [
        replacement_baseline_path.name,
        authority_path.name,
        allowed_path.name,
    ]
    _git(repository, "add", "--", *allowed)

    assert replacement["dirty_entries"] == inherited["dirty_entries"]
    assert len(replacement["protected_paths"]) == (
        len(inherited["protected_paths"]) + 1
    )
    assert all(
        row in replacement["protected_paths"]
        for row in inherited["protected_paths"]
    )
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Protected extension retirement test commit",
        workspace_baseline=replacement_baseline_path.name,
    )
    control_path = repository / receipt["control_path"]
    _commit_prepared_control(repository, json.loads(control_path.read_text()))
    shutil.rmtree(control_path.parent)

    assert validate_commit_boundary(
        repository,
        expected_commit_subject="Protected extension retirement test commit",
        reconstruct=True,
    ) == []


@pytest.mark.parametrize("protected_change", ["remove", "change"])
def test_bootstrap_to_workspace_replacement_preserves_inherited_protected_rows(
    repository: Path,
    protected_change: str,
) -> None:
    inherited_baseline_path = _commit_initial_controlled_baseline(
        repository,
        protected_paths=("tracked.txt",),
    )
    inherited = json.loads(inherited_baseline_path.read_text())
    replacement = capture_workspace_baseline(repository, ["tracked.txt"])
    if protected_change == "remove":
        replacement["protected_paths"] = []
    else:
        replacement["protected_paths"][0]["lstat_mode"] = 0o755
        replacement["protected_paths"][0][
            "normalized_entry_sha256"
        ] = _canonical_sha256(
            replacement["protected_paths"][0],
            exclude={"normalized_entry_sha256"},
        )
    replacement["normalized_baseline_sha256"] = _canonical_sha256(
        replacement,
        exclude={"normalized_baseline_sha256"},
    )
    assert replacement["dirty_entries"] == inherited["dirty_entries"]
    assert validate_workspace_record_shape(replacement) == []
    replacement_baseline_path = repository / "replacement-baseline.json"
    replacement_baseline_path.write_text(
        json.dumps(replacement, sort_keys=True) + "\n"
    )
    authority_path = repository / "replacement-authority.json"
    allowed_path = repository / "replacement-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("replacement\n")
    allowed = [
        replacement_baseline_path.name,
        authority_path.name,
        allowed_path.name,
    ]
    _git(repository, "add", "--", *allowed)

    with pytest.raises(
        SourceBindingError,
        match="workspace_baseline_inheritance_invalid",
    ):
        build_precommit_control(
            repository,
            allowed_paths=allowed,
            durable_authority_paths=[authority_path.name],
            commit_subject="Invalid protected replacement retirement test commit",
            workspace_baseline=replacement_baseline_path.name,
        )


def test_precommit_builder_allows_inherited_workspace_reuse(
    repository: Path,
) -> None:
    workspace_baseline_path = _commit_bootstrap_to_workspace_baseline(
        repository
    )
    authority_path = repository / "reuse-workspace-authority.json"
    allowed_path = repository / "reuse-workspace-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("reuse workspace\n")
    allowed = [authority_path.name, allowed_path.name]
    _git(repository, "add", "--", *allowed)
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Workspace reuse retirement test commit",
        workspace_baseline=workspace_baseline_path.name,
    )
    control_path = repository / receipt["control_path"]
    _commit_prepared_control(repository, json.loads(control_path.read_text()))
    shutil.rmtree(control_path.parent)

    assert validate_commit_boundary(
        repository,
        expected_commit_subject="Workspace reuse retirement test commit",
        reconstruct=True,
    ) == []


@pytest.mark.parametrize(
    "workspace_drift", ["same_status_bytes", "delete", "mode"]
)
def test_precommit_builder_rejects_workspace_drift_hidden_by_replacement_baseline(
    repository: Path, workspace_drift: str
) -> None:
    (
        _inherited_baseline_path,
        replacement_baseline_path,
        authority_path,
        _allowed_path,
        allowed,
    ) = _prepare_bootstrap_to_workspace_replacement(
        repository, workspace_drift=workspace_drift
    )

    with pytest.raises(
        SourceBindingError,
        match="workspace_baseline_inheritance_invalid",
    ):
        build_precommit_control(
            repository,
            allowed_paths=allowed,
            durable_authority_paths=[authority_path.name],
            commit_subject="Replacement retirement test commit",
            workspace_baseline=replacement_baseline_path.name,
        )


def test_precommit_builder_rejects_second_workspace_baseline_replacement(
    repository: Path,
) -> None:
    _commit_bootstrap_to_workspace_baseline(repository)
    replacement_baseline_path = repository / "second-replacement-baseline.json"
    replacement_baseline_path.write_text(
        json.dumps(capture_workspace_baseline(repository), sort_keys=True) + "\n"
    )
    authority_path = repository / "second-replacement-authority.json"
    allowed_path = repository / "second-replacement-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("replacement\n")
    allowed = [
        allowed_path.name,
        authority_path.name,
        replacement_baseline_path.name,
    ]
    _git(repository, "add", "--", *allowed)

    with pytest.raises(
        SourceBindingError,
        match="workspace_baseline_transition_invalid",
    ):
        build_precommit_control(
            repository,
            allowed_paths=allowed,
            durable_authority_paths=[authority_path.name],
            commit_subject="Second replacement retirement test commit",
            workspace_baseline=replacement_baseline_path.name,
        )


def test_reconstruction_rejects_replacement_that_refreshes_inherited_dirty_bytes(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        _inherited_baseline_path,
        replacement_baseline_path,
        authority_path,
        _allowed_path,
        allowed,
    ) = _prepare_bootstrap_to_workspace_replacement(
        repository, workspace_drift="same_status_bytes"
    )
    monkeypatch.setattr(
        retirement_source_bindings,
        "_validate_precommit_workspace_baseline_selection",
        lambda *args, **kwargs: None,
    )
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Forged replacement retirement test commit",
        workspace_baseline=replacement_baseline_path.name,
    )
    control_path = repository / receipt["control_path"]
    _commit_prepared_control(repository, json.loads(control_path.read_text()))
    shutil.rmtree(control_path.parent)

    assert validate_commit_boundary(
        repository,
        expected_commit_subject="Forged replacement retirement test commit",
        reconstruct=True,
    ) == [
        SourceBindingIssue(
            "commit_reconstruction_failed",
            detail="workspace_baseline_semantic_inheritance_invalid",
        )
    ]


def test_reconstruction_rejects_second_workspace_baseline_replacement(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _commit_bootstrap_to_workspace_baseline(repository)
    replacement_baseline_path = repository / "second-replacement-baseline.json"
    replacement_baseline_path.write_text(
        json.dumps(capture_workspace_baseline(repository), sort_keys=True) + "\n"
    )
    authority_path = repository / "second-replacement-authority.json"
    allowed_path = repository / "second-replacement-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("replacement\n")
    allowed = [
        allowed_path.name,
        authority_path.name,
        replacement_baseline_path.name,
    ]
    _git(repository, "add", "--", *allowed)
    monkeypatch.setattr(
        retirement_source_bindings,
        "_validate_precommit_workspace_baseline_selection",
        lambda *args, **kwargs: None,
    )
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Forged second replacement retirement test commit",
        workspace_baseline=replacement_baseline_path.name,
    )
    control_path = repository / receipt["control_path"]
    _commit_prepared_control(repository, json.loads(control_path.read_text()))
    shutil.rmtree(control_path.parent)

    assert validate_commit_boundary(
        repository,
        expected_commit_subject=(
            "Forged second replacement retirement test commit"
        ),
        reconstruct=True,
    ) == [
        SourceBindingIssue(
            "commit_reconstruction_failed",
            detail="workspace_baseline_transition_invalid",
        )
    ]


def test_reconstruction_rejects_mode_only_inherited_baseline_change(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inherited_baseline_path = _commit_initial_controlled_baseline(
        repository, bootstrap=True
    )
    authority_path = repository / "mode-authority.json"
    allowed_path = repository / "mode-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("mode change\n")
    inherited_baseline_path.chmod(0o755)
    allowed = [
        allowed_path.name,
        authority_path.name,
        inherited_baseline_path.name,
    ]
    _git(repository, "add", "--", *allowed)
    monkeypatch.setattr(
        retirement_source_bindings,
        "_validate_precommit_workspace_baseline_selection",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        retirement_source_bindings,
        "_bound_workspace_issues",
        lambda *args, **kwargs: [],
    )
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Forged mode retirement test commit",
        bootstrap_workspace_baseline=inherited_baseline_path.name,
    )
    control_path = repository / receipt["control_path"]
    _commit_prepared_control(repository, json.loads(control_path.read_text()))
    shutil.rmtree(control_path.parent)

    assert validate_commit_boundary(
        repository,
        expected_commit_subject="Forged mode retirement test commit",
        reconstruct=True,
    ) == [
        SourceBindingIssue(
            "commit_reconstruction_failed",
            detail="workspace_baseline_changed_since_prior_control",
        )
    ]


@pytest.mark.parametrize("index_change", ["delete", "different_blob"])
def test_precommit_builder_rejects_changed_inherited_baseline_index_entry(
    repository: Path, index_change: str
) -> None:
    inherited_baseline_path = _commit_initial_controlled_baseline(repository)
    inherited_bytes = inherited_baseline_path.read_bytes()
    replacement_baseline_path = repository / "replacement-baseline.json"
    replacement_baseline_path.write_text(
        json.dumps(capture_workspace_baseline(repository), sort_keys=True) + "\n"
    )
    authority_path = repository / "replacement-authority.json"
    allowed_path = repository / "replacement-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("replacement\n")
    if index_change == "delete":
        subprocess.run(
            ["git", "rm", "--cached", "--", inherited_baseline_path.name],
            cwd=repository,
            check=True,
            capture_output=True,
        )
    else:
        inherited_baseline_path.write_bytes(b'{"staged":"different"}\n')
        _git(repository, "add", "--", inherited_baseline_path.name)
        inherited_baseline_path.write_bytes(inherited_bytes)
    allowed = [
        allowed_path.name,
        authority_path.name,
        inherited_baseline_path.name,
        replacement_baseline_path.name,
    ]
    _git(
        repository,
        "add",
        "--",
        allowed_path.name,
        authority_path.name,
        replacement_baseline_path.name,
    )

    with pytest.raises(
        SourceBindingError,
        match="workspace_baseline_inheritance_invalid",
    ):
        build_precommit_control(
            repository,
            allowed_paths=allowed,
            durable_authority_paths=[authority_path.name],
            commit_subject="Replacement retirement test commit",
            workspace_baseline=replacement_baseline_path.name,
        )


@pytest.mark.parametrize("inherited_change", ["mutate", "delete"])
def test_precommit_builder_rejects_changed_inherited_baseline_during_replacement(
    repository: Path,
    inherited_change: str,
) -> None:
    inherited_baseline_path = _commit_initial_controlled_baseline(repository)
    replacement_baseline_path = repository / "replacement-baseline.json"
    replacement_baseline_path.write_text(
        json.dumps(capture_workspace_baseline(repository), sort_keys=True) + "\n"
    )
    authority_path = repository / "replacement-authority.json"
    allowed_path = repository / "replacement-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("replacement\n")
    if inherited_change == "mutate":
        inherited_baseline_path.write_text('{"changed":true}\n')
    else:
        inherited_baseline_path.unlink()
    allowed = [
        allowed_path.name,
        authority_path.name,
        inherited_baseline_path.name,
        replacement_baseline_path.name,
    ]
    _git(repository, "add", "-A", "--", *allowed)
    control_root = repository / ".git/retirement-commit-controls"
    before_controls = set(control_root.iterdir()) if control_root.exists() else set()

    with pytest.raises(
        SourceBindingError,
        match="workspace_baseline_inheritance_invalid",
    ):
        build_precommit_control(
            repository,
            allowed_paths=allowed,
            durable_authority_paths=[authority_path.name],
            commit_subject="Replacement retirement test commit",
            workspace_baseline=replacement_baseline_path.name,
        )

    assert (
        set(control_root.iterdir()) if control_root.exists() else set()
    ) == before_controls


@pytest.mark.parametrize("inherited_change", ["mutate", "delete"])
def test_reconstruction_rejects_changed_inherited_baseline_during_replacement(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    inherited_change: str,
) -> None:
    inherited_baseline_path = _commit_initial_controlled_baseline(repository)
    replacement_baseline_path = repository / "replacement-baseline.json"
    replacement_baseline_path.write_text(
        json.dumps(capture_workspace_baseline(repository), sort_keys=True) + "\n"
    )
    authority_path = repository / "replacement-authority.json"
    allowed_path = repository / "replacement-allowed.txt"
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("replacement\n")
    if inherited_change == "mutate":
        inherited_baseline_path.write_text('{"changed":true}\n')
    else:
        inherited_baseline_path.unlink()
    allowed = [
        allowed_path.name,
        authority_path.name,
        inherited_baseline_path.name,
        replacement_baseline_path.name,
    ]
    _git(repository, "add", "-A", "--", *allowed)
    monkeypatch.setattr(
        retirement_source_bindings,
        "_validate_precommit_workspace_baseline_selection",
        lambda *args, **kwargs: None,
    )
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Replacement retirement test commit",
        workspace_baseline=replacement_baseline_path.name,
    )
    control_path = repository / receipt["control_path"]
    _commit_prepared_control(repository, json.loads(control_path.read_text()))
    shutil.rmtree(control_path.parent)

    assert validate_commit_boundary(
        repository,
        expected_commit_subject="Replacement retirement test commit",
        reconstruct=True,
    ) == [
        SourceBindingIssue(
            "commit_reconstruction_failed",
            detail="workspace_baseline_changed_since_prior_control",
        )
    ]


@pytest.mark.parametrize("lane", ["pathspec", "final-message"])
def test_precommit_control_rejects_self_rebound_external_derivation_drift(
    repository: Path, lane: str
) -> None:
    receipt, control_path, control = _prepare_precommit_control(repository)
    if lane == "pathspec":
        binding = control["pathspec_file_binding"]
        external = repository / binding["path"]
        changed = b"wrong-path\0" * binding["row_count"]
        external.write_bytes(changed)
        binding.update({"sha256": "sha256:" + hashlib.sha256(changed).hexdigest(), "byte_count": len(changed)})
        expected_code = "pathspec_derivation_mismatch"
    else:
        binding = control["final_message_binding"]
        external = repository / binding["path"]
        changed = b"trailer-free final bytes\n"
        external.write_bytes(changed)
        binding.update({"sha256": "sha256:" + hashlib.sha256(changed).hexdigest(), "byte_count": len(changed)})
        expected_code = "final_message_derivation_mismatch"
    control["normalized_control_sha256"] = _canonical_sha256(
        control,
        exclude={"normalized_control_sha256", "final_message_binding"},
    )
    control_path.write_text(json.dumps(control, sort_keys=True) + "\n")

    issues = validate_commit_boundary(
        repository,
        control_path=receipt["control_path"],
        expected_commit_subject="Retirement test commit",
    )

    assert expected_code in {issue.code for issue in issues}


@pytest.mark.parametrize(
    "binding_field",
    ["pathspec_file_binding", "base_message_binding", "final_message_binding"],
)
def test_precommit_control_rejects_self_rebound_external_coordinate(
    repository: Path, binding_field: str
) -> None:
    receipt, control_path, control = _prepare_precommit_control(repository)
    binding = control[binding_field]
    original_path = repository / binding["path"]
    alternate_path = original_path.with_name(f"alternate-{original_path.name}")
    original_path.rename(alternate_path)
    binding["path"] = alternate_path.relative_to(repository).as_posix()
    _refresh_control_digest_and_final_message(repository, control)
    control_path.write_text(json.dumps(control, sort_keys=True) + "\n")

    issues = validate_commit_boundary(
        repository,
        control_path=receipt["control_path"],
        expected_commit_subject="Retirement test commit",
    )

    assert f"{binding_field}_invalid" in {issue.code for issue in issues}


def test_precommit_control_requires_canonical_control_json_coordinate(
    repository: Path,
) -> None:
    _, control_path, _ = _prepare_precommit_control(repository)
    alternate = repository / ".git/alternate-control.json"
    alternate.write_bytes(control_path.read_bytes())

    issues = validate_commit_boundary(
        repository,
        control_path=alternate.relative_to(repository),
        expected_commit_subject="Retirement test commit",
    )

    assert "control_path_mismatch" in {issue.code for issue in issues}


@pytest.mark.parametrize(
    ("lane", "expected_code"),
    [
        ("allowed-row", "allowed_delta_rows_mismatch"),
        ("pre-index", "pre_commit_index_binding_mismatch"),
        ("expected-tree", "expected_commit_tree_mismatch"),
    ],
)
def test_precommit_control_rederives_live_index_and_tree_fields(
    repository: Path, lane: str, expected_code: str
) -> None:
    receipt, control_path, control = _prepare_precommit_control(repository)
    if lane == "allowed-row":
        control["allowed_delta_rows"][0]["after"]["oid"] = "0" * 40
    elif lane == "pre-index":
        control["pre_commit_index_binding"] = {
            "entry_count": 0,
            "entry_set_sha256": "sha256:" + "0" * 64,
        }
    else:
        control["expected_commit_tree_oid"] = "0" * 40
    _refresh_control_digest_and_final_message(repository, control)
    control_path.write_text(json.dumps(control, sort_keys=True) + "\n")

    issues = validate_commit_boundary(
        repository,
        control_path=receipt["control_path"],
        expected_commit_subject="Retirement test commit",
    )

    assert expected_code in {issue.code for issue in issues}


def test_commit_boundary_binds_the_independent_expected_subject_pre_and_post(
    repository: Path,
) -> None:
    receipt, control_path, control = _prepare_precommit_control(repository)
    assert "expected_commit_subject_missing" in {
        issue.code
        for issue in validate_commit_boundary(
            repository, control_path=receipt["control_path"]
        )
    }
    (repository / control["base_message_binding"]["path"]).write_bytes(
        b"Different subject\n"
    )
    control["base_message_binding"].update(
        {
            "sha256": "sha256:"
            + hashlib.sha256(b"Different subject\n").hexdigest(),
            "byte_count": len(b"Different subject\n"),
        }
    )
    _refresh_control_digest_and_final_message(repository, control)
    control_path.write_text(json.dumps(control, sort_keys=True) + "\n")

    pre_issues = validate_commit_boundary(
        repository,
        control_path=receipt["control_path"],
        expected_commit_subject="Retirement test commit",
    )
    assert "base_message_subject_mismatch" in {
        issue.code for issue in pre_issues
    }

    subprocess.run(
        [
            "git",
            "--literal-pathspecs",
            "commit",
            "--only",
            "--no-gpg-sign",
            f"--pathspec-from-file={repository / control['pathspec_file_binding']['path']}",
            "--pathspec-file-nul",
            f"--file={repository / control['final_message_binding']['path']}",
            "--cleanup=verbatim",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    post_issues = validate_commit_boundary(
        repository,
        control_path=receipt["control_path"],
        expected_commit_subject="Retirement test commit",
        post_commit=True,
    )
    assert "base_message_subject_mismatch" in {
        issue.code for issue in post_issues
    }


@pytest.mark.parametrize(
    ("lane", "expected_code"),
    [
        ("pathspec", "pathspec_derivation_mismatch"),
        ("final-message", "final_message_derivation_mismatch"),
    ],
)
def test_postcommit_validation_uses_canonical_inverse_control_reconstruction(
    repository: Path, lane: str, expected_code: str
) -> None:
    receipt, control_path, control = _prepare_precommit_control(repository)
    subprocess.run(
        [
            "git",
            "--literal-pathspecs",
            "commit",
            "--only",
            "--no-gpg-sign",
            f"--pathspec-from-file={repository / control['pathspec_file_binding']['path']}",
            "--pathspec-file-nul",
            f"--file={repository / control['final_message_binding']['path']}",
            "--cleanup=verbatim",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    binding = control[
        "pathspec_file_binding" if lane == "pathspec" else "final_message_binding"
    ]
    external = repository / binding["path"]
    changed = (
        b"wrong-path\0" * binding["row_count"]
        if lane == "pathspec"
        else b"trailer-free final bytes\n"
    )
    external.write_bytes(changed)
    binding.update(
        {
            "sha256": "sha256:" + hashlib.sha256(changed).hexdigest(),
            "byte_count": len(changed),
        }
    )
    control["normalized_control_sha256"] = _canonical_sha256(
        control,
        exclude={"normalized_control_sha256", "final_message_binding"},
    )
    control_path.write_text(json.dumps(control, sort_keys=True) + "\n")

    issues = validate_commit_boundary(
        repository,
        control_path=receipt["control_path"],
        expected_commit_subject="Retirement test commit",
        post_commit=True,
    )

    codes = {issue.code for issue in issues}
    assert expected_code in codes
    assert "commit_reconstruction_mismatch" in codes


@pytest.mark.parametrize(
    ("lane", "expected_code"),
    [
        ("baseline", "workspace_binding_mismatch"),
        ("authority", "durable_authority_binding_mismatch"),
    ],
)
def test_precommit_validation_reopens_every_durable_authority(
    repository: Path, lane: str, expected_code: str
) -> None:
    receipt, _, control = _prepare_precommit_control(repository)
    binding = (
        control["bootstrap_workspace_baseline_binding"]
        if lane == "baseline"
        else control["durable_authority_bindings"][0]
    )
    (repository / binding["path"]).write_bytes(
        (repository / binding["path"]).read_bytes() + b"\n"
    )

    issues = validate_commit_boundary(
        repository,
        control_path=receipt["control_path"],
        expected_commit_subject="Retirement test commit",
    )

    assert expected_code in {issue.code for issue in issues}


def test_precommit_validation_requires_current_head_to_equal_base_head(
    repository: Path,
) -> None:
    receipt, _, _ = _prepare_precommit_control(repository)
    base = _git(repository, "rev-parse", "HEAD")
    tree = _git(repository, "rev-parse", "HEAD^{tree}")
    child = subprocess.check_output(
        ["git", "commit-tree", tree, "-p", base],
        cwd=repository,
        input=b"unrelated child\n",
    ).decode("ascii").strip()
    _git(repository, "update-ref", "HEAD", child, base)

    assert "base_head_mismatch" in {
        issue.code
        for issue in validate_commit_boundary(
            repository,
            control_path=receipt["control_path"],
            expected_commit_subject="Retirement test commit",
        )
    }


def test_precommit_builder_and_validator_reject_allowed_worktree_index_drift(
    repository: Path,
) -> None:
    baseline = _bootstrap_workspace_record(capture_workspace_baseline(repository))
    baseline_path = repository / "baseline.json"
    authority_path = repository / "authority.json"
    allowed_path = repository / "allowed.txt"
    baseline_path.write_text(json.dumps(baseline, sort_keys=True) + "\n")
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("staged\n")
    allowed = [baseline_path.name, authority_path.name, allowed_path.name]
    _git(repository, "add", *allowed)
    allowed_path.write_text("unstaged\n")

    with pytest.raises(SourceBindingError, match="allowed_path_worktree_index_mismatch"):
        build_precommit_control(
            repository,
            allowed_paths=allowed,
            durable_authority_paths=[authority_path.name],
            commit_subject="Retirement test commit",
            bootstrap_workspace_baseline=baseline_path.name,
        )

    allowed_path.write_text("staged\n")
    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Retirement test commit",
        bootstrap_workspace_baseline=baseline_path.name,
    )
    allowed_path.write_text("unstaged again\n")

    assert "allowed_path_worktree_index_mismatch" in {
        issue.code
        for issue in validate_commit_boundary(
            repository,
            control_path=receipt["control_path"],
            expected_commit_subject="Retirement test commit",
        )
    }


def test_postcommit_validation_requires_commit_parent_to_equal_base_head(
    repository: Path,
) -> None:
    receipt, _, control = _prepare_precommit_control(repository)
    subprocess.run(
        [
            "git",
            "--literal-pathspecs",
            "commit",
            "--only",
            "--no-gpg-sign",
            f"--pathspec-from-file={repository / control['pathspec_file_binding']['path']}",
            "--pathspec-file-nul",
            f"--file={repository / control['final_message_binding']['path']}",
            "--cleanup=verbatim",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    parent = _git(repository, "rev-parse", "HEAD")
    tree = _git(repository, "rev-parse", "HEAD^{tree}")
    child = subprocess.check_output(
        ["git", "commit-tree", tree, "-p", parent],
        cwd=repository,
        input=b"unrelated child\n",
    ).decode("ascii").strip()

    assert "commit_parent_mismatch" in {
        issue.code
        for issue in validate_commit_boundary(
            repository,
            control_path=receipt["control_path"],
            commit=child,
            expected_commit_subject="Retirement test commit",
            post_commit=True,
        )
    }


def test_postcommit_validation_requires_the_controlled_commit_to_be_head(
    repository: Path,
) -> None:
    receipt, _, control = _prepare_precommit_control(repository)
    subprocess.run(
        [
            "git",
            "--literal-pathspecs",
            "commit",
            "--only",
            "--no-gpg-sign",
            f"--pathspec-from-file={repository / control['pathspec_file_binding']['path']}",
            "--pathspec-file-nul",
            f"--file={repository / control['final_message_binding']['path']}",
            "--cleanup=verbatim",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    controlled_commit = _git(repository, "rev-parse", "HEAD")
    _git(repository, "commit", "--allow-empty", "-qm", "later commit")

    assert "post_commit_head_mismatch" in {
        issue.code
        for issue in validate_commit_boundary(
            repository,
            control_path=receipt["control_path"],
            commit=controlled_commit,
            expected_commit_subject="Retirement test commit",
            post_commit=True,
        )
    }


@pytest.mark.parametrize("staged", [False, True], ids=["unstaged", "staged"])
def test_postcommit_validation_rejects_live_drift_on_committed_allowed_path(
    repository: Path, staged: bool
) -> None:
    receipt, _, control = _prepare_precommit_control(repository)
    subprocess.run(
        [
            "git",
            "--literal-pathspecs",
            "commit",
            "--only",
            "--no-gpg-sign",
            f"--pathspec-from-file={repository / control['pathspec_file_binding']['path']}",
            "--pathspec-file-nul",
            f"--file={repository / control['final_message_binding']['path']}",
            "--cleanup=verbatim",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    (repository / "allowed.txt").write_text("post-commit drift\n")
    if staged:
        _git(repository, "add", "allowed.txt")

    issues = validate_commit_boundary(
        repository,
        control_path=receipt["control_path"],
        expected_commit_subject="Retirement test commit",
        post_commit=True,
    )

    codes = {issue.code for issue in issues}
    assert {
        "workspace_binding_live_invalid",
        "index_binding_mismatch",
    } & codes


@pytest.mark.parametrize(
    "authority_kind",
    ["plain-text", "duplicate", "unregistered", "outside-allowed"],
)
def test_precommit_builder_rejects_unreconstructible_durable_authority_set(
    repository: Path, authority_kind: str
) -> None:
    baseline = _bootstrap_workspace_record(capture_workspace_baseline(repository))
    baseline_path = repository / "baseline.json"
    authority_path = repository / "authority.json"
    allowed_path = repository / "allowed.txt"
    baseline_path.write_text(json.dumps(baseline, sort_keys=True) + "\n")
    allowed_path.write_text("allowed\n")
    if authority_kind == "plain-text":
        authority_path.write_text("plain text\n")
    elif authority_kind == "unregistered":
        authority_path.write_text('{"schema_version":"unknown.v1"}\n')
    else:
        _write_valid_durable_authority(authority_path)
    allowed = [baseline_path.name, allowed_path.name]
    if authority_kind != "outside-allowed":
        allowed.append(authority_path.name)
    _git(repository, "add", *allowed)
    authority_paths = (
        [authority_path.name, authority_path.name]
        if authority_kind == "duplicate"
        else [authority_path.name]
    )

    with pytest.raises(SourceBindingError, match="durable_authority"):
        build_precommit_control(
            repository,
            allowed_paths=allowed,
            durable_authority_paths=authority_paths,
            commit_subject="Retirement test commit",
            bootstrap_workspace_baseline=baseline_path.name,
        )

    assert not (repository / ".git/retirement-commit-controls").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda control: control["durable_authority_bindings"][0].__setitem__(
            "schema_version", None
        ),
        lambda control: control["durable_authority_bindings"][0].__setitem__(
            "schema_version", "unknown.v1"
        ),
        lambda control: control["durable_authority_bindings"].append(
            dict(control["durable_authority_bindings"][0])
        ),
        lambda control: control["durable_authority_bindings"][0].__setitem__(
            "path", "not-in-allowed.json"
        ),
    ],
)
def test_precommit_control_shape_rejects_unreconstructible_authorities(
    mutation,
) -> None:
    control = json.loads(
        Path(
            "tests/fixtures/retirement_broad_evidence/precommit_control.v1.json"
        ).read_text()
    )
    mutation(control)
    authority_digest = _set_digest(control["durable_authority_bindings"])
    control["durable_authority_set_sha256"] = authority_digest
    control["transaction_id"] = hashlib.sha256(
        b"precommit-control.v1\0"
        + control["base_head"].encode("ascii")
        + b"\0"
        + authority_digest.removeprefix("sha256:").encode("ascii")
    ).hexdigest()
    control["normalized_control_sha256"] = _canonical_sha256(
        control,
        exclude={"normalized_control_sha256", "final_message_binding"},
    )

    assert "durable_authority_invalid" in {
        issue.code for issue in validate_workspace_record_shape(control)
    }


def test_precommit_control_preserves_unrelated_stage_and_rejects_tamper(
    repository: Path,
) -> None:
    unrelated = repository / "tracked.txt"
    unrelated.write_text("pre-existing stage\n")
    _git(repository, "add", unrelated.name)
    baseline = _bootstrap_workspace_record(capture_workspace_baseline(repository))
    baseline_path = repository / "baseline.json"
    authority_path = repository / "authority.json"
    allowed_path = repository / "allowed.txt"
    baseline_path.write_text(json.dumps(baseline, sort_keys=True) + "\n")
    _write_valid_durable_authority(authority_path)
    allowed_path.write_text("allowed\n")
    allowed = [baseline_path.name, authority_path.name, allowed_path.name]
    _git(repository, "add", *allowed)

    receipt = build_precommit_control(
        repository,
        allowed_paths=allowed,
        durable_authority_paths=[authority_path.name],
        commit_subject="Retirement test commit",
        bootstrap_workspace_baseline=baseline_path.name,
    )
    control_path = repository / receipt["control_path"]
    assert validate_commit_boundary(
        repository,
        control_path=receipt["control_path"],
        expected_commit_subject="Retirement test commit",
    ) == []
    assert unrelated.name in _git(repository, "diff", "--cached", "--name-only").splitlines()

    control = json.loads(control_path.read_text())
    final_message = repository / control["final_message_binding"]["path"]
    original_final_message = final_message.read_bytes()
    final_message.write_bytes(original_final_message + b"drift")
    assert "final_message_binding_mismatch" in {
        issue.code
        for issue in validate_commit_boundary(
            repository,
            control_path=receipt["control_path"],
            expected_commit_subject="Retirement test commit",
        )
    }
    final_message.write_bytes(original_final_message)
    subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "--literal-pathspecs",
            "commit",
            "--only",
            "--no-gpg-sign",
            f"--pathspec-from-file={repository / control['pathspec_file_binding']['path']}",
            "--pathspec-file-nul",
            f"--file={final_message}",
            "--cleanup=verbatim",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    assert validate_commit_boundary(
        repository,
        control_path=receipt["control_path"],
        expected_commit_subject="Retirement test commit",
        post_commit=True,
    ) == []
    assert unrelated.name in _git(repository, "diff", "--cached", "--name-only").splitlines()
    original_control_bytes = control_path.read_bytes()
    shutil.rmtree(control_path.parent)
    clone = repository.parent / "fresh-clone"
    subprocess.run(["git", "clone", "-q", str(repository), str(clone)], check=True)
    assert validate_commit_boundary(
        clone,
        expected_commit_subject="Retirement test commit",
        reconstruct=True,
    ) == []
    cloned_control = clone / receipt["control_path"]
    assert cloned_control.is_file()
    assert cloned_control.read_bytes() == original_control_bytes

    replacement_baseline = capture_workspace_baseline(repository)
    replacement_baseline_path = repository / "workspace-baseline.json"
    replacement_baseline_path.write_text(
        json.dumps(replacement_baseline, sort_keys=True) + "\n"
    )
    second_authority = repository / "second-authority.json"
    second_allowed = repository / "second-allowed.txt"
    _write_valid_durable_authority(second_authority)
    second_allowed.write_text("second\n")
    second_paths = [
        replacement_baseline_path.name,
        second_authority.name,
        second_allowed.name,
    ]
    _git(repository, "add", *second_paths)
    allowed_path.write_text("unstaged historical drift\n")
    with pytest.raises(
        SourceBindingError,
        match="workspace_baseline_inheritance_invalid",
    ):
        build_precommit_control(
            repository,
            allowed_paths=second_paths,
            durable_authority_paths=[second_authority.name],
            commit_subject="Second retirement test commit",
            workspace_baseline=replacement_baseline_path.name,
        )
    allowed_path.write_text("allowed\n")
    second_receipt = build_precommit_control(
        repository,
        allowed_paths=second_paths,
        durable_authority_paths=[second_authority.name],
        commit_subject="Second retirement test commit",
        workspace_baseline=replacement_baseline_path.name,
    )
    second_control_path = repository / second_receipt["control_path"]
    second_control = json.loads(second_control_path.read_text())
    assert second_control["prior_control_trailers"] == []
    tampered_control = dict(second_control)
    tampered_control["prior_control_trailers"] = [
        {
            "commit": _git(repository, "rev-parse", "HEAD"),
            "transaction_id": control["transaction_id"],
            "normalized_control_sha256": control[
                "normalized_control_sha256"
            ],
        }
    ]
    tampered_control["normalized_control_sha256"] = _canonical_sha256(
        tampered_control,
        exclude={"normalized_control_sha256", "final_message_binding"},
    )
    second_control_path.write_text(json.dumps(tampered_control, sort_keys=True) + "\n")
    assert "prior_control_trailer_chain_mismatch" in {
        issue.code
        for issue in validate_commit_boundary(
            repository,
            control_path=second_receipt["control_path"],
            expected_commit_subject="Second retirement test commit",
        )
    }
    second_control_path.write_text(json.dumps(second_control, sort_keys=True) + "\n")
    subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "--literal-pathspecs", "commit", "--only", "--no-gpg-sign", f"--pathspec-from-file={repository / second_control['pathspec_file_binding']['path']}", "--pathspec-file-nul", f"--file={repository / second_control['final_message_binding']['path']}", "--cleanup=verbatim"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    shutil.rmtree(second_control_path.parent)
    second_clone = repository.parent / "second-fresh-clone"
    subprocess.run(["git", "clone", "-q", str(repository), str(second_clone)], check=True)
    assert validate_commit_boundary(
        second_clone,
        expected_commit_subject="Second retirement test commit",
        reconstruct=True,
    ) == []
    reconstructed_second = second_clone / second_receipt["control_path"]
    assert json.loads(reconstructed_second.read_text())["prior_control_trailers"] == second_control["prior_control_trailers"]


@pytest.mark.parametrize(
    "message",
    [
        b"base\nRetirement-Control-Schema: precommit_control.v1\nRetirement-Transaction-ID: " + b"0" * 64 + b"\nRetirement-Control-SHA256: " + b"1" * 64 + b"\n",
        b"base\r\n\r\nRetirement-Control-Schema: precommit_control.v1\r\nRetirement-Transaction-ID: " + b"0" * 64 + b"\r\nRetirement-Control-SHA256: " + b"1" * 64 + b"\r\n",
        b"base\n\nRetirement-Control-SHA256: " + b"1" * 64 + b"\nRetirement-Transaction-ID: " + b"0" * 64 + b"\nRetirement-Control-Schema: precommit_control.v1\n",
        b"base\n\nRetirement-Control-Schema: precommit_control.v1\nRetirement-Transaction-ID: " + b"0" * 64 + b"\nRetirement-Control-SHA256: " + b"1" * 64 + b"\n\nRetirement-Control-Schema: precommit_control.v1\nRetirement-Transaction-ID: " + b"0" * 64 + b"\nRetirement-Control-SHA256: " + b"1" * 64 + b"\n",
    ],
    ids=["missing-separator", "crlf", "reordered", "duplicated"],
)
def test_reconstruction_rejects_malformed_control_message(
    repository: Path, message: bytes
) -> None:
    tree = _git(repository, "rev-parse", "HEAD^{tree}")
    parent = _git(repository, "rev-parse", "HEAD")
    completed = subprocess.run(
        ["git", "commit-tree", tree, "-p", parent, "-F", "-"],
        cwd=repository,
        input=message,
        capture_output=True,
        check=True,
    )
    commit = completed.stdout.decode("ascii").strip()
    issues = validate_commit_boundary(repository, commit=commit, reconstruct=True)
    assert [issue.code for issue in issues] == ["commit_reconstruction_failed"]


def test_committed_predecessor_lineage_projects_controlled_and_uncovered_paths(
    repository: Path,
) -> None:
    baseline_head = _git(repository, "rev-parse", "HEAD")
    transaction_id = "1" * 64
    control_sha256 = "sha256:" + "2" * 64
    controlled_message = _lineage_commit_message(
        "controlled predecessor change",
        transaction_id=transaction_id,
        control_sha256=control_sha256,
    )
    (repository / "controlled.txt").write_text("controlled\n")
    _git(repository, "add", "controlled.txt")
    controlled_commit = _commit_lineage_tree(repository, controlled_message)

    ordinary_message = _lineage_commit_message("ordinary predecessor change")
    (repository / "README.md").write_text("ordinary\n")
    _git(repository, "add", "README.md")
    intended_predecessor_head = _commit_lineage_tree(
        repository, ordinary_message
    )

    controlled_paths = ["controlled.txt"]
    uncovered_paths = ["README.md"]
    changed_paths = sorted(controlled_paths + uncovered_paths)
    commit_rows = [
        {
            "commit": controlled_commit,
            "parent": baseline_head,
            "tree": _git(repository, "rev-parse", f"{controlled_commit}^{{tree}}"),
            "raw_message_sha256": "sha256:"
            + hashlib.sha256(controlled_message).hexdigest(),
            "changed_paths": controlled_paths,
            "changed_path_set_sha256": _lineage_path_set_sha256(
                controlled_paths
            ),
            "control_coordinates": {
                "transaction_id": transaction_id,
                "normalized_control_sha256": control_sha256,
            },
        },
        {
            "commit": intended_predecessor_head,
            "parent": controlled_commit,
            "tree": _git(
                repository,
                "rev-parse",
                f"{intended_predecessor_head}^{{tree}}",
            ),
            "raw_message_sha256": "sha256:"
            + hashlib.sha256(ordinary_message).hexdigest(),
            "changed_paths": uncovered_paths,
            "changed_path_set_sha256": _lineage_path_set_sha256(
                uncovered_paths
            ),
            "control_coordinates": None,
        },
    ]
    expected = {
        "baseline_head": baseline_head,
        "intended_predecessor_head": intended_predecessor_head,
        "intended_predecessor_tree": _git(
            repository,
            "rev-parse",
            f"{intended_predecessor_head}^{{tree}}",
        ),
        "first_parent_commits": commit_rows,
        "commit_count": 2,
        "changed_paths": changed_paths,
        "changed_path_count": 2,
        "changed_path_set_sha256": _lineage_path_set_sha256(changed_paths),
        "controlled_paths": controlled_paths,
        "controlled_path_set_sha256": _lineage_path_set_sha256(
            controlled_paths
        ),
        "uncovered_paths": uncovered_paths,
        "uncovered_path_set_sha256": _lineage_path_set_sha256(
            uncovered_paths
        ),
    }
    expected["normalized_projection_sha256"] = _canonical_sha256(expected)

    projection = _derive_committed_predecessor_lineage(
        repository,
        baseline_head=baseline_head,
        intended_predecessor_head=intended_predecessor_head,
    )

    assert projection == expected


def test_committed_predecessor_lineage_rejects_non_ancestor_heads(
    repository: Path,
) -> None:
    common_parent = _git(repository, "rev-parse", "HEAD")
    (repository / "intended.txt").write_text("intended\n")
    _git(repository, "add", "intended.txt")
    intended_predecessor_head = _commit_lineage_tree(
        repository, _lineage_commit_message("intended branch")
    )
    _git(repository, "reset", "--hard", common_parent)
    (repository / "sibling.txt").write_text("sibling\n")
    _git(repository, "add", "sibling.txt")
    sibling_head = _commit_lineage_tree(
        repository, _lineage_commit_message("sibling branch")
    )

    with pytest.raises(SourceBindingError):
        _derive_committed_predecessor_lineage(
            repository,
            baseline_head=sibling_head,
            intended_predecessor_head=intended_predecessor_head,
        )


def test_committed_predecessor_lineage_rejects_merge_ambiguity(
    repository: Path,
) -> None:
    baseline_head = _git(repository, "rev-parse", "HEAD")
    (repository / "first-parent.txt").write_text("first parent\n")
    _git(repository, "add", "first-parent.txt")
    first_parent = _commit_lineage_tree(
        repository, _lineage_commit_message("first parent")
    )

    _git(repository, "reset", "--hard", baseline_head)
    (repository / "second-parent.txt").write_text("second parent\n")
    _git(repository, "add", "second-parent.txt")
    second_parent = _commit_lineage_tree(
        repository, _lineage_commit_message("second parent")
    )

    _git(repository, "reset", "--hard", first_parent)
    merge_head = _commit_lineage_tree(
        repository,
        _lineage_commit_message("ambiguous merge"),
        parents=[first_parent, second_parent],
    )

    with pytest.raises(SourceBindingError):
        _derive_committed_predecessor_lineage(
            repository,
            baseline_head=baseline_head,
            intended_predecessor_head=merge_head,
        )


def test_committed_predecessor_lineage_rejects_malformed_control_trailer(
    repository: Path,
) -> None:
    baseline_head = _git(repository, "rev-parse", "HEAD")
    (repository / "malformed.txt").write_text("malformed\n")
    _git(repository, "add", "malformed.txt")
    malformed_message = (
        b"malformed control\n\n"
        b"Retirement-Control-Schema: precommit_control.v1\n"
        b"Retirement-Transaction-ID: short\n"
        b"Retirement-Control-SHA256: " + b"2" * 64 + b"\n"
    )
    intended_predecessor_head = _commit_lineage_tree(
        repository, malformed_message
    )

    with pytest.raises(SourceBindingError):
        _derive_committed_predecessor_lineage(
            repository,
            baseline_head=baseline_head,
            intended_predecessor_head=intended_predecessor_head,
        )


def test_committed_predecessor_lineage_rejects_duplicate_path_projection(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline_head = _git(repository, "rev-parse", "HEAD")
    (repository / "duplicate.txt").write_text("duplicate\n")
    _git(repository, "add", "duplicate.txt")
    intended_predecessor_head = _commit_lineage_tree(
        repository, _lineage_commit_message("duplicate projection")
    )
    original_git = retirement_source_bindings._git

    def duplicate_diff_tree_paths(
        root: Path,
        *arguments: str,
        input_bytes: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> bytes:
        output = original_git(
            root, *arguments, input_bytes=input_bytes, env=env
        )
        if arguments and arguments[0] == "diff-tree" and output:
            return output + output
        return output

    monkeypatch.setattr(
        retirement_source_bindings, "_git", duplicate_diff_tree_paths
    )

    with pytest.raises(SourceBindingError):
        _derive_committed_predecessor_lineage(
            repository,
            baseline_head=baseline_head,
            intended_predecessor_head=intended_predecessor_head,
        )


def test_committed_predecessor_lineage_rejects_missing_git_object(
    repository: Path,
) -> None:
    with pytest.raises(SourceBindingError):
        _derive_committed_predecessor_lineage(
            repository,
            baseline_head=_git(repository, "rev-parse", "HEAD"),
            intended_predecessor_head="0" * 40,
        )


def test_committed_predecessor_lineage_requires_uncovered_invalidating_gap(
    repository: Path,
) -> None:
    baseline_head = _git(repository, "rev-parse", "HEAD")
    (repository / "controlled-only.txt").write_text("controlled only\n")
    _git(repository, "add", "controlled-only.txt")
    intended_predecessor_head = _commit_lineage_tree(
        repository,
        _lineage_commit_message(
            "controlled-only predecessor",
            transaction_id="3" * 64,
            control_sha256="sha256:" + "4" * 64,
        ),
    )

    with pytest.raises(SourceBindingError):
        _derive_committed_predecessor_lineage(
            repository,
            baseline_head=baseline_head,
            intended_predecessor_head=intended_predecessor_head,
            require_uncovered_paths=True,
        )
