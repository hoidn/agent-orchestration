from __future__ import annotations

from copy import deepcopy
import hashlib
import os
import shutil
import stat
from pathlib import Path

import pytest

from orchestrator.workflow.run_ref.contracts import (
    RepositoryRevisionId,
    canonical_sha256,
)
from orchestrator.workflow.run_ref import delta as delta_module
from orchestrator.workflow.run_ref.delta import (
    DeclaredArtifact,
    MAX_NORMALIZED_DIFF_BYTES,
    MAX_NORMALIZED_TEXT_ENTRY_BYTES,
    RunRefDeltaError,
    build_workspace_delta,
    validate_workspace_delta,
)
from orchestrator.workflow.run_ref.workspace import freeze_tree


_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _base_revision() -> RepositoryRevisionId:
    return RepositoryRevisionId.build(
        normalized_locator="file:///candidate",
        resolved_commit_sha=_COMMIT,
        materializer_version="git-detached-clone-v1",
        submodule_policy="reject-v1",
        lfs_policy="reject-v1",
        authored_setup_identity=canonical_sha256({"commands": []}),
    )


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def test_build_workspace_delta_is_complete_sorted_and_path_independent(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline"
    final = tmp_path / "final"
    baseline.mkdir()
    (baseline / "changed.txt").write_text("old\n", encoding="utf-8")
    (baseline / "deleted.txt").write_text("gone\n", encoding="utf-8")
    (baseline / "unchanged.txt").write_text("same\n", encoding="utf-8")
    (baseline / ".git").mkdir()
    (baseline / ".git" / "ignored").write_text("git", encoding="utf-8")
    (baseline / ".orchestrate").mkdir()
    (baseline / ".orchestrate" / "ignored").write_text("state", encoding="utf-8")
    baseline_manifest = freeze_tree(
        baseline,
        excluded_roots=(".git", ".orchestrate"),
    )

    shutil.copytree(baseline, final, symlinks=True)
    (final / "changed.txt").write_text("new\n", encoding="utf-8")
    (final / "deleted.txt").unlink()
    (final / "artifact.txt").write_text("artifact\n", encoding="utf-8")
    (final / "binary.bin").write_bytes(b"\x00\xff")
    (final / "untracked.txt").write_text("fresh\n", encoding="utf-8")
    (final / "link").symlink_to("artifact.txt")
    (final / ".git" / "ignored").write_text("changed git", encoding="utf-8")
    (final / ".orchestrate" / "ignored").write_text(
        "changed state",
        encoding="utf-8",
    )

    capture = build_workspace_delta(
        base=_base_revision(),
        baseline_root=baseline,
        baseline_manifest=baseline_manifest,
        workspace_root=final,
        declared_artifacts=(
            DeclaredArtifact(name="result", path="artifact.txt"),
            DeclaredArtifact(name="link", path="link"),
        ),
    )

    record = capture.record
    assert record["base"] == {
        "digest": _base_revision().digest,
        **_base_revision().components,
    }
    assert [row["path"] for row in record["changed_files"]] == ["changed.txt"]
    assert [row["path"] for row in record["deleted_files"]] == ["deleted.txt"]
    assert [row["path"] for row in record["untracked_files"]] == [
        "artifact.txt",
        "binary.bin",
        "link",
        "untracked.txt",
    ]
    assert record["changed_files"][0] == {
        "path": "changed.txt",
        "kind": "file",
        "mode": stat.S_IMODE((final / "changed.txt").lstat().st_mode),
        "size": 4,
        "old_sha256": _sha256(b"old\n"),
        "new_sha256": _sha256(b"new\n"),
        "link_target": None,
    }
    assert record["untracked_files"][2]["link_target"] == "artifact.txt"
    assert [row["path"] for row in record["normalized_diff"]["entries"]] == [
        "artifact.txt",
        "changed.txt",
        "deleted.txt",
        "untracked.txt",
    ]
    diffs_by_path = {
        row["path"]: row["text"] for row in record["normalized_diff"]["entries"]
    }
    assert diffs_by_path["changed.txt"] == (
        "--- a/changed.txt\n"
        "+++ b/changed.txt\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    assert record["normalized_diff"]["catalog_digest"] == canonical_sha256(
        {
            "changed_files": record["changed_files"],
            "deleted_files": record["deleted_files"],
            "untracked_files": record["untracked_files"],
        }
    )
    assert record["normalized_diff"]["truncated"] is False
    assert record["normalized_diff"]["omitted_bytes"] == 0
    assert record["normalized_diff"]["omitted_entries"] == 0
    assert record["declared_artifacts"] == [
        {
            "name": "link",
            "path": "link",
            "kind": "symlink",
            "mode": stat.S_IMODE((final / "link").lstat().st_mode),
            "size": len(b"artifact.txt"),
            "sha256": _sha256(b"artifact.txt"),
            "link_target": "artifact.txt",
        },
        {
            "name": "result",
            "path": "artifact.txt",
            "kind": "file",
            "mode": stat.S_IMODE((final / "artifact.txt").lstat().st_mode),
            "size": len(b"artifact\n"),
            "sha256": _sha256(b"artifact\n"),
            "link_target": None,
        },
    ]
    assert capture.digest == canonical_sha256(record)
    assert capture.final_manifest == freeze_tree(
        final,
        excluded_roots=(".git", ".orchestrate"),
    )

    other_baseline = tmp_path / "other-baseline"
    other_final = tmp_path / "other-final"
    shutil.copytree(baseline, other_baseline, symlinks=True)
    shutil.copytree(final, other_final, symlinks=True)
    other = build_workspace_delta(
        base=_base_revision(),
        baseline_root=other_baseline,
        baseline_manifest=baseline_manifest,
        workspace_root=other_final,
        declared_artifacts=(
            DeclaredArtifact(name="result", path="artifact.txt"),
            DeclaredArtifact(name="link", path="link"),
        ),
    )
    assert other.record == record
    assert other.digest == capture.digest


def test_normalized_diff_caps_only_text_and_accounts_for_every_omitted_byte(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline"
    final = tmp_path / "final"
    baseline.mkdir()
    final.mkdir()
    for name in ("a.txt", "b.txt", "c.txt"):
        (baseline / name).write_text(f"old-{name}\n", encoding="utf-8")
        (final / name).write_text("é" * 80 + f"-{name}\n", encoding="utf-8")
    baseline_manifest = freeze_tree(baseline)
    final_manifest = freeze_tree(final)
    baseline_by_path = {entry.path: entry for entry in baseline_manifest.entries}
    final_by_path = {entry.path: entry for entry in final_manifest.entries}
    paths = ("a.txt", "b.txt", "c.txt")

    full = delta_module._build_normalized_diff(
        baseline_root=baseline,
        workspace_root=final,
        baseline_by_path=baseline_by_path,
        final_by_path=final_by_path,
        changed_paths=paths,
        deleted_paths=(),
        untracked_paths=(),
        max_total_bytes=100_000,
        max_entry_bytes=100_000,
    )
    per_entry_limited = delta_module._build_normalized_diff(
        baseline_root=baseline,
        workspace_root=final,
        baseline_by_path=baseline_by_path,
        final_by_path=final_by_path,
        changed_paths=paths,
        deleted_paths=(),
        untracked_paths=(),
        max_total_bytes=100_000,
        max_entry_bytes=45,
    )
    total_limited = delta_module._build_normalized_diff(
        baseline_root=baseline,
        workspace_root=final,
        baseline_by_path=baseline_by_path,
        final_by_path=final_by_path,
        changed_paths=paths,
        deleted_paths=(),
        untracked_paths=(),
        max_total_bytes=55,
        max_entry_bytes=45,
    )

    full_bytes = sum(len(row["text"].encode("utf-8")) for row in full["entries"])
    per_entry_bytes = sum(
        len(row["text"].encode("utf-8")) for row in per_entry_limited["entries"]
    )
    total_bytes = sum(
        len(row["text"].encode("utf-8")) for row in total_limited["entries"]
    )
    assert MAX_NORMALIZED_DIFF_BYTES == 8 * 1024 * 1024
    assert MAX_NORMALIZED_TEXT_ENTRY_BYTES == 256 * 1024
    assert len(per_entry_limited["entries"]) == 3
    assert all(
        len(row["text"].encode("utf-8")) <= 45
        and row["truncated"] is True
        for row in per_entry_limited["entries"]
    )
    assert per_entry_limited["omitted_bytes"] == full_bytes - per_entry_bytes
    assert per_entry_limited["omitted_entries"] == 0
    assert total_bytes <= 55
    assert total_limited["omitted_bytes"] == full_bytes - total_bytes
    assert total_limited["omitted_entries"] == 1
    assert total_limited["truncated"] is True
    assert full["catalog_digest"] == per_entry_limited["catalog_digest"]
    assert full["catalog_digest"] == total_limited["catalog_digest"]


def test_catalog_keeps_directory_rows_while_text_diff_stays_file_only(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline"
    final = tmp_path / "final"
    (baseline / "removed").mkdir(parents=True)
    (baseline / "removed" / "old.txt").write_text("old\n", encoding="utf-8")
    (final / "created").mkdir(parents=True)
    (final / "created" / "new.txt").write_text("new\n", encoding="utf-8")
    baseline_manifest = freeze_tree(baseline)

    capture = build_workspace_delta(
        base=_base_revision(),
        baseline_root=baseline,
        baseline_manifest=baseline_manifest,
        workspace_root=final,
    )

    assert [row["path"] for row in capture.record["deleted_files"]] == [
        "removed",
        "removed/old.txt",
    ]
    assert [row["path"] for row in capture.record["untracked_files"]] == [
        "created",
        "created/new.txt",
    ]
    assert [row["path"] for row in capture.record["normalized_diff"]["entries"]] == [
        "created/new.txt",
        "removed/old.txt",
    ]


def test_validator_rebuilds_the_delta_and_rejects_record_or_digest_tamper(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline"
    final = tmp_path / "final"
    baseline.mkdir()
    final.mkdir()
    (baseline / "result.txt").write_text("old\n", encoding="utf-8")
    (final / "result.txt").write_text("new\n", encoding="utf-8")
    (final / "result-link").symlink_to("result.txt")
    baseline_manifest = freeze_tree(baseline)
    artifacts = (DeclaredArtifact(name="result", path="result-link"),)
    capture = build_workspace_delta(
        base=_base_revision(),
        baseline_root=baseline,
        baseline_manifest=baseline_manifest,
        workspace_root=final,
        declared_artifacts=artifacts,
    )

    assert validate_workspace_delta(
        capture.record,
        expected_digest=capture.digest,
        base=_base_revision(),
        baseline_root=baseline,
        baseline_manifest=baseline_manifest,
        workspace_root=final,
        declared_artifacts=artifacts,
    ) == capture.final_manifest

    tampered_path = deepcopy(capture.record)
    tampered_path["changed_files"][0]["path"] = "../result.txt"
    with pytest.raises(RunRefDeltaError) as path_exc:
        validate_workspace_delta(
            tampered_path,
            expected_digest=canonical_sha256(tampered_path),
            base=_base_revision(),
            baseline_root=baseline,
            baseline_manifest=baseline_manifest,
            workspace_root=final,
            declared_artifacts=artifacts,
        )
    assert path_exc.value.secondary_causes == ("delta_record_mismatch",)

    tampered_link = deepcopy(capture.record)
    tampered_link["declared_artifacts"][0]["link_target"] = "elsewhere"
    with pytest.raises(RunRefDeltaError) as record_exc:
        validate_workspace_delta(
            tampered_link,
            expected_digest=canonical_sha256(tampered_link),
            base=_base_revision(),
            baseline_root=baseline,
            baseline_manifest=baseline_manifest,
            workspace_root=final,
            declared_artifacts=artifacts,
        )
    assert record_exc.value.secondary_causes == ("delta_record_mismatch",)

    with pytest.raises(RunRefDeltaError) as digest_exc:
        validate_workspace_delta(
            capture.record,
            expected_digest="sha256:" + "f" * 64,
            base=_base_revision(),
            baseline_root=baseline,
            baseline_manifest=baseline_manifest,
            workspace_root=final,
            declared_artifacts=artifacts,
        )
    assert digest_exc.value.secondary_causes == ("delta_digest_mismatch",)


def test_baseline_snapshot_and_final_special_entries_fail_closed(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    final = tmp_path / "final"
    baseline.mkdir()
    final.mkdir()
    (baseline / "value.txt").write_text("bound\n", encoding="utf-8")
    (final / "value.txt").write_text("done\n", encoding="utf-8")
    baseline_manifest = freeze_tree(baseline)
    (baseline / "value.txt").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(RunRefDeltaError) as baseline_exc:
        build_workspace_delta(
            base=_base_revision(),
            baseline_root=baseline,
            baseline_manifest=baseline_manifest,
            workspace_root=final,
        )
    assert baseline_exc.value.secondary_causes == ("baseline_snapshot_mismatch",)

    (baseline / "value.txt").write_text("bound\n", encoding="utf-8")
    fifo = final / "unsupported"
    os.mkfifo(fifo)
    try:
        with pytest.raises(RunRefDeltaError) as final_exc:
            build_workspace_delta(
                base=_base_revision(),
                baseline_root=baseline,
                baseline_manifest=baseline_manifest,
                workspace_root=final,
            )
        assert final_exc.value.secondary_causes == ("final_workspace_freeze_failed",)
    finally:
        fifo.unlink()


@pytest.mark.parametrize(
    "path",
    ("/absolute", "../parent", "dot/./entry", "double//entry", "back\\slash"),
)
def test_declared_artifact_paths_are_canonical_relative_posix_text(path: str) -> None:
    with pytest.raises(ValueError, match="canonical relative POSIX"):
        DeclaredArtifact(name="result", path=path)


def test_declared_artifact_name_must_be_utf8_text() -> None:
    with pytest.raises(ValueError, match="UTF-8"):
        DeclaredArtifact(name="\ud800", path="result.txt")


def test_declared_artifacts_reject_missing_reserved_duplicate_and_symlink_traversal(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline"
    final = tmp_path / "final"
    outside = tmp_path / "outside"
    baseline.mkdir()
    final.mkdir()
    outside.mkdir()
    (final / "result.txt").write_text("done\n", encoding="utf-8")
    (outside / "escaped.txt").write_text("outside\n", encoding="utf-8")
    (final / "escape").symlink_to(outside, target_is_directory=True)
    (final / ".orchestrate").mkdir()
    (final / ".orchestrate" / "state.json").write_text("{}", encoding="utf-8")
    baseline_manifest = freeze_tree(baseline)

    cases = (
        (
            (DeclaredArtifact(name="missing", path="missing.txt"),),
            "declared_artifact_missing",
        ),
        (
            (DeclaredArtifact(name="state", path=".orchestrate/state.json"),),
            "declared_artifact_path_invalid",
        ),
        (
            (
                DeclaredArtifact(name="first", path="result.txt"),
                DeclaredArtifact(name="second", path="result.txt"),
            ),
            "declared_artifact_ambiguous",
        ),
        (
            (DeclaredArtifact(name="escaped", path="escape/escaped.txt"),),
            "declared_artifact_missing",
        ),
    )
    for artifacts, expected_cause in cases:
        with pytest.raises(RunRefDeltaError) as excinfo:
            build_workspace_delta(
                base=_base_revision(),
                baseline_root=baseline,
                baseline_manifest=baseline_manifest,
                workspace_root=final,
                declared_artifacts=artifacts,
            )
        assert excinfo.value.secondary_causes == (expected_cause,)
