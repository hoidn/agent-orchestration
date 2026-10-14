from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator._common.io_atomic import (
    atomic_write_text as common_atomic_write_text,
)
from orchestrator.workflow_lisp.adapters import apply_resource_transition


REPO_ROOT = Path(__file__).resolve().parent.parent
DESIGN_DELTA_RUNTIME_TRANSITION_FIXTURE = (
    REPO_ROOT
    / "workflows"
    / "library"
    / "lisp_frontend_design_delta"
    / "runtime_transition_fixture.orc"
)
DESIGN_DELTA_MIGRATION_INPUTS = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
)


def test_resource_transition_bundle_delegates_exact_unframed_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "ORCHESTRATOR_OUTPUT_BUNDLE_PATH",
        "state/results/resource.json",
    )
    writes: list[tuple[Path, str, dict[str, object]]] = []

    def tracking_write(path: Path, text: str, **kwargs) -> None:
        assert path.parent.is_dir()
        writes.append((path, text, kwargs))
        common_atomic_write_text(path, text, **kwargs)

    monkeypatch.setattr(
        apply_resource_transition,
        "atomic_write_text",
        tracking_write,
    )
    result = {"resource-id": "résumé", "to": "done"}

    apply_resource_transition._write_output_bundle(result)

    assert writes == [
        (
            Path("state/results/resource.json"),
            json.dumps(result, sort_keys=True),
            {},
        )
    ]
    assert not writes[0][1].endswith("\n")
