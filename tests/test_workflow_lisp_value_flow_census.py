from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def _module():
    return importlib.import_module("orchestrator.workflow_lisp.value_flow_census")


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _valid_row(**overrides: object) -> dict[str, object]:
    row = {
        "row_id": "drain.input.baseline_design_path",
        "workflow_surface": "lisp_frontend_design_delta/drain::drain",
        "source_kind": "public_input",
        "symbol_or_field": "baseline_design_path",
        "path_or_contract": "BaselineDesignPath",
        "plumbing_class": "public_authored",
        "boundary_authority_class": "public_authored",
        "track_owner": "shared",
        "current_consumer": "workflow_entry",
        "semantic_owner": "caller",
        "source_evidence": [
            {
                "kind": "compiled_boundary_projection",
                "path": ".orchestrate/build/example/workflow_boundary_projection.json",
            }
        ],
        "replacement_target": None,
        "command_boundary": None,
        "bridge": None,
        "notes": "",
    }
    row.update(overrides)
    return row


def _valid_payload(*, rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_private_runtime_value_flow_census.v1",
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "source_design": "docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md",
        "coverage": {
            "workflow_surfaces": ["lisp_frontend_design_delta/drain::drain"],
            "required_source_kinds": ["public_input"],
        },
        "rows": rows or [_valid_row()],
    }


def test_load_value_flow_census_accepts_minimal_valid_design_delta_payload(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(tmp_path / "value_flow_census.json", _valid_payload())

    payload = module.load_value_flow_census(path)

    assert payload["schema_version"] == "workflow_lisp_private_runtime_value_flow_census.v1"
    assert payload["target_family"] == "lisp_frontend_design_delta_parent_drain"
    assert payload["coverage"]["required_source_kinds"] == ["public_input"]
    assert [row["row_id"] for row in payload["rows"]] == [
        "drain.input.baseline_design_path"
    ]


def test_load_value_flow_census_rejects_duplicate_row_id(tmp_path: Path) -> None:
    module = _module()
    payload = _valid_payload(
        rows=[
            _valid_row(),
            _valid_row(symbol_or_field="target_design_path"),
        ]
    )
    path = _write_json(tmp_path / "duplicate-row-id.json", payload)

    with pytest.raises(ValueError, match="duplicate row_id"):
        module.load_value_flow_census(path)


def test_load_value_flow_census_rejects_unknown_source_kind(tmp_path: Path) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "unknown-source-kind.json",
        _valid_payload(rows=[_valid_row(source_kind="not_a_real_source_kind")]),
    )

    with pytest.raises(ValueError, match="unknown source_kind"):
        module.load_value_flow_census(path)


def test_load_value_flow_census_rejects_unknown_plumbing_class(tmp_path: Path) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "unknown-plumbing-class.json",
        _valid_payload(rows=[_valid_row(plumbing_class="not_a_real_plumbing_class")]),
    )

    with pytest.raises(ValueError, match="unknown plumbing_class"):
        module.load_value_flow_census(path)


def test_load_value_flow_census_rejects_unknown_boundary_authority_class(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "unknown-boundary-authority-class.json",
        _valid_payload(
            rows=[_valid_row(boundary_authority_class="not_a_real_authority_class")]
        ),
    )

    with pytest.raises(ValueError, match="unknown boundary_authority_class"):
        module.load_value_flow_census(path)


def test_load_value_flow_census_rejects_pointer_path_classified_as_semantic_authority(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "pointer-path-authority.json",
        _valid_payload(
            rows=[
                _valid_row(
                    row_id="drain.pointer.selection_bundle",
                    source_kind="pointer_path",
                    symbol_or_field="selection_bundle_path",
                    path_or_contract="SelectionBundlePointer",
                    plumbing_class="compatibility_bridge",
                    boundary_authority_class="public_authored",
                    current_consumer="legacy_reader",
                    bridge={
                        "bridge_owner": "lisp_frontend_design_delta/drain",
                        "consumer": "legacy_reader",
                        "file_shape": "pointer_file",
                        "retirement_condition": "remove when typed lineage replaces pointer file reads",
                    },
                )
            ],
        ),
    )

    with pytest.raises(ValueError, match="pointer_path.*semantic authority"):
        module.load_value_flow_census(path)


def test_load_value_flow_census_rejects_render_only_row_without_current_consumer(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "render-without-consumer.json",
        _valid_payload(
            rows=[
                _valid_row(
                    row_id="drain.prompt.work_item_inputs",
                    source_kind="prompt_input_file",
                    symbol_or_field="work_item_inputs_prompt_path",
                    path_or_contract="PromptInputFile",
                    plumbing_class="prompt_rendering",
                    current_consumer=None,
                )
            ],
        ),
    )

    with pytest.raises(ValueError, match="current_consumer"):
        module.load_value_flow_census(path)


def test_load_value_flow_census_rejects_command_boundary_rows_without_command_evidence(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "command-without-boundary.json",
        _valid_payload(
            rows=[
                _valid_row(
                    row_id="work-item.adapter.review_findings",
                    workflow_surface="lisp_frontend_design_delta/work_item::run-work-item",
                    source_kind="command_adapter_input",
                    symbol_or_field="review_findings_target_path",
                    path_or_contract="ReviewFindingsPath",
                    plumbing_class="genuine_external_io",
                    boundary_authority_class="compatibility_bridge",
                    current_consumer="validate_review_findings_v1",
                    command_boundary=None,
                )
            ],
        ),
    )

    with pytest.raises(ValueError, match="command-boundary evidence"):
        module.load_value_flow_census(path)


def test_load_value_flow_census_rejects_compatibility_bridge_without_bridge_metadata(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "bridge-without-metadata.json",
        _valid_payload(
            rows=[
                _valid_row(
                    row_id="drain.bridge.manifest_path",
                    source_kind="bridge_file",
                    symbol_or_field="manifest_path",
                    path_or_contract="ManifestPointerPath",
                    plumbing_class="compatibility_bridge",
                    boundary_authority_class="compatibility_bridge",
                    current_consumer="legacy_reader",
                    bridge={"bridge_owner": "lisp_frontend_design_delta/drain"},
                )
            ],
        ),
    )

    with pytest.raises(ValueError, match="bridge metadata"):
        module.load_value_flow_census(path)
