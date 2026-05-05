from pathlib import Path

import pytest
import yaml

from orchestrator.managed_jobs.identity import compute_job_identity_hash
from orchestrator.managed_jobs.policy import ManagedJobPolicyError, load_policy


def _write_policy(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _job_metadata() -> dict:
    return {
        "name_template": "{script_stem}-{args_hash}",
        "state_root_template": "state/managed_jobs/{entry_id}/{job_identity_hash}",
        "output_root_arg": "--output-root",
        "verify_files": ["{output_root}/metrics.json"],
        "snapshot_roots": ["scripts", "configs"],
        "config_globs": ["configs/*.yaml"],
    }


def test_policy_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ManagedJobPolicyError, match="does not exist"):
        load_policy(tmp_path / "missing.yaml", workspace=tmp_path)


def test_policy_rejects_unparsable_yaml(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text("entries: [", encoding="utf-8")

    with pytest.raises(ManagedJobPolicyError, match="could not parse"):
        load_policy(path, workspace=tmp_path)


def test_policy_rejects_path_escape_in_managed_entry(tmp_path: Path) -> None:
    path = _write_policy(
        tmp_path,
        {
            "entries": [
                {
                    "id": "train",
                    "mode": "force_managed",
                    "path": "../scripts/train.py",
                    "job": _job_metadata(),
                }
            ]
        },
    )

    with pytest.raises(ManagedJobPolicyError, match="parent directory traversal"):
        load_policy(path, workspace=tmp_path)


def test_policy_rejects_managed_entry_without_metadata_or_extractor(tmp_path: Path) -> None:
    path = _write_policy(
        tmp_path,
        {
            "entries": [
                {
                    "id": "train",
                    "mode": "force_managed",
                    "path": "scripts/train.py",
                }
            ]
        },
    )

    with pytest.raises(ManagedJobPolicyError, match="requires job metadata or extractor"):
        load_policy(path, workspace=tmp_path)


def test_policy_accepts_explicit_managed_job_metadata(tmp_path: Path) -> None:
    path = _write_policy(
        tmp_path,
        {
            "backend_defaults": {"backend": "local"},
            "entries": [
                {
                    "id": "train",
                    "mode": "force_managed",
                    "path": "scripts/train.py",
                    "job": _job_metadata(),
                }
            ],
        },
    )

    policy = load_policy(path, workspace=tmp_path)

    entry = policy.entries[0]
    assert entry.id == "train"
    assert entry.metadata is not None
    assert entry.metadata.state_root_template == "state/managed_jobs/{entry_id}/{job_identity_hash}"
    assert entry.metadata.verify_files == ("{output_root}/metrics.json",)


def test_policy_accepts_named_extractor_metadata(tmp_path: Path) -> None:
    path = _write_policy(
        tmp_path,
        {
            "extractors": {
                "image_suite": {
                    "version": "v1",
                    "job": _job_metadata(),
                }
            },
            "entries": [
                {
                    "id": "suite",
                    "mode": "auto_managed",
                    "path": "scripts/suite.py",
                    "extractor": "image_suite",
                }
            ],
        },
    )

    policy = load_policy(path, workspace=tmp_path)

    entry = policy.entries[0]
    assert entry.metadata is not None
    assert entry.metadata.extractor == "image_suite"
    assert entry.metadata.extractor_version == "v1"


def test_policy_rejects_unknown_extractor(tmp_path: Path) -> None:
    path = _write_policy(
        tmp_path,
        {
            "entries": [
                {
                    "id": "suite",
                    "mode": "auto_managed",
                    "path": "scripts/suite.py",
                    "extractor": "missing",
                }
            ],
        },
    )

    with pytest.raises(ManagedJobPolicyError, match="unknown extractor"):
        load_policy(path, workspace=tmp_path)


def test_identity_hash_changes_with_source_hash() -> None:
    first = compute_job_identity_hash(
        argv=("python", "scripts/train.py"),
        source_hashes={"scripts/train.py": "sha256:a"},
        config_hashes={},
        extractor_id="explicit",
        extractor_version="v1",
        policy_entry_hash="sha256:policy",
        snapshot_inputs=("scripts/train.py",),
    )
    second = compute_job_identity_hash(
        argv=("python", "scripts/train.py"),
        source_hashes={"scripts/train.py": "sha256:b"},
        config_hashes={},
        extractor_id="explicit",
        extractor_version="v1",
        policy_entry_hash="sha256:policy",
        snapshot_inputs=("scripts/train.py",),
    )

    assert first != second
