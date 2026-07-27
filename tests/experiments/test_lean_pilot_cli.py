from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from orchestrator.experiments.contracts import canonical_json_bytes


def test_prepare_cli_forwards_every_explicit_authoring_root(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    cli = importlib.import_module("scripts.experiments.lean_pilot")
    captured: dict[str, object] = {}
    lock = {"record_kind": "pilot_lock.v1", "pilot_id": "fixture"}

    def fake_prepare(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return lock

    monkeypatch.setattr(cli, "prepare_pilot", fake_prepare)
    paths = {
        "source_map_path": (tmp_path / "source-map.json").resolve(),
        "repository_root": (tmp_path / "repository").resolve(),
        "control_root": (tmp_path / "control").resolve(),
        "evidence_root": (tmp_path / "evidence").resolve(),
        "calibration_seal_path": (tmp_path / "seal.json").resolve(),
        "lock_output_path": (tmp_path / "lock.json").resolve(),
    }

    assert (
        cli.main(
            [
                "prepare",
                "--source-map",
                str(paths["source_map_path"]),
                "--repository-root",
                str(paths["repository_root"]),
                "--full-revision",
                "a" * 40,
                "--fresh-control-root",
                str(paths["control_root"]),
                "--fresh-evidence-root",
                str(paths["evidence_root"]),
                "--calibration-seal",
                str(paths["calibration_seal_path"]),
                "--lock-output",
                str(paths["lock_output_path"]),
            ]
        )
        == 0
    )
    assert captured == {
        **paths,
        "apparatus_revision": "a" * 40,
    }
    assert capsys.readouterr().out.startswith("sha256:")


def test_execute_cli_forwards_disjoint_runtime_roots_and_prints_result(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    cli = importlib.import_module("scripts.experiments.lean_pilot")
    lock_path = (tmp_path / "lock.json").resolve()
    lock_path.write_bytes(b"{}")
    captured: dict[str, object] = {}
    result = {
        "status": "STOP_APPARATUS_NOT_VIABLE",
        "attempt_ids": ["smoke"],
        "valid_live_block_ids": [],
    }
    lock = {"record_kind": "pilot_lock.v1", "pilot_id": "fixture"}
    monkeypatch.setattr(cli, "load_record", lambda *_args, **_kwargs: lock)

    def fake_execute(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return result

    monkeypatch.setattr(cli, "execute_pilot", fake_execute)
    runtime = {
        "work_root": (tmp_path / "work").resolve(),
        "evaluation_root": (tmp_path / "evaluation").resolve(),
        "package_root": (tmp_path / "packages").resolve(),
        "reviewer_environment_path": (tmp_path / "reviewer-env.json").resolve(),
    }

    assert (
        cli.main(
            [
                "execute",
                "--lock",
                str(lock_path),
                "--work-root",
                str(runtime["work_root"]),
                "--evaluation-copy-root",
                str(runtime["evaluation_root"]),
                "--package-root",
                str(runtime["package_root"]),
                "--reviewer-environment",
                str(runtime["reviewer_environment_path"]),
            ]
        )
        == 0
    )
    assert captured == {"lock": lock, **runtime}
    assert json.loads(capsys.readouterr().out) == json.loads(
        canonical_json_bytes(result)
    )
