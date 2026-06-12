from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


def _module():
    return importlib.import_module("orchestrator.workflow.view_renderer")


def test_canonical_json_renderer_v1_emits_golden_bytes_for_typed_record_value() -> None:
    renderer = _module()
    value_document = {
        "status": "BLOCKED",
        "reason": "missing_resource",
        "completed_items": 2,
        "paths": {
            "run_state_path": "state/run-state.json",
            "summary_target_path": "artifacts/work/summary.json",
        },
    }

    rendered = renderer.render_view("canonical-json", 1, value_document)

    assert rendered == (
        b'{"completed_items":2,"paths":{"run_state_path":"state/run-state.json",'
        b'"summary_target_path":"artifacts/work/summary.json"},"reason":"missing_resource",'
        b'"status":"BLOCKED"}\n'
    )


def test_posix_path_line_renderer_v1_emits_single_trailing_newline() -> None:
    renderer = _module()

    rendered = renderer.render_view("posix-path-line", 1, "state/drain_summary_path.txt")

    assert rendered == b"state/drain_summary_path.txt\n"
    assert rendered.count(b"\n") == 1


def test_view_digest_and_evidence_key_are_repeatable_and_cross_process_stable() -> None:
    renderer = _module()
    value_document = {
        "status": "DONE",
        "run_state_path": "state/final-run-state.json",
    }

    rendered = renderer.render_view("canonical-json", 1, value_document)
    digest = renderer.view_bytes_digest(rendered)
    evidence_key = renderer.view_evidence_key(
        "canonical-json",
        1,
        renderer.VIEW_RENDERER_SCHEMA_VERSION,
        digest,
    )

    assert digest == f"sha256:{hashlib.sha256(rendered).hexdigest()}"
    assert renderer.view_bytes_digest(rendered) == digest
    assert (
        renderer.view_evidence_key(
            "canonical-json",
            1,
            renderer.VIEW_RENDERER_SCHEMA_VERSION,
            digest,
        )
        == evidence_key
    )
    assert (
        renderer.view_evidence_key(
            "canonical-json",
            2,
            renderer.VIEW_RENDERER_SCHEMA_VERSION,
            digest,
        )
        != evidence_key
    )

    script = """
import json
from orchestrator.workflow.view_renderer import (
    VIEW_RENDERER_SCHEMA_VERSION,
    render_view,
    view_bytes_digest,
    view_evidence_key,
)

value_document = {
    "status": "DONE",
    "run_state_path": "state/final-run-state.json",
}
rendered = render_view("canonical-json", 1, value_document)
digest = view_bytes_digest(rendered)
print(json.dumps({
    "digest": digest,
    "evidence_key": view_evidence_key("canonical-json", 1, VIEW_RENDERER_SCHEMA_VERSION, digest),
}))
""".strip()
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["digest"] == digest
    assert payload["evidence_key"] == evidence_key


@pytest.mark.parametrize(
    ("renderer_id", "renderer_version", "value_document", "expected_code"),
    [
        ("canonical-json", 1, object(), "view_value_shape_invalid"),
        ("canonical-json", 1, {"payload": b"not-json"}, "view_value_shape_invalid"),
        ("posix-path-line", 1, {"path": "state/file.txt"}, "view_value_shape_invalid"),
        ("posix-path-line", 1, 7, "view_value_shape_invalid"),
    ],
)
def test_render_view_rejects_unsupported_value_shapes(
    renderer_id: str,
    renderer_version: int,
    value_document: object,
    expected_code: str,
) -> None:
    renderer = _module()

    with pytest.raises(renderer.ViewRendererError) as excinfo:
        renderer.render_view(renderer_id, renderer_version, value_document)

    assert excinfo.value.code == expected_code


def test_render_view_rejects_unknown_renderer_id_or_version() -> None:
    renderer = _module()

    with pytest.raises(renderer.ViewRendererError) as excinfo:
        renderer.render_view("canonical-json", 999, {"status": "DONE"})

    assert excinfo.value.code == "view_renderer_unknown"
