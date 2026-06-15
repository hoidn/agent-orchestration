from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CONSUMER_RENDERING_CENSUS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.consumer_rendering_census.json"
)
VALUE_FLOW_CENSUS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.value_flow_census.json"
)
COMPATIBILITY_BRIDGES_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.compatibility_bridges.json"
)


def _module():
    return importlib.import_module("orchestrator.workflow_lisp.compatibility_bridges")


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _command_boundaries() -> dict[str, object]:
    return {
        "materialize_lisp_frontend_work_item_inputs": {
            "kind": "certified_adapter",
            "stable_command": [
                "python",
                "workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py",
            ],
            "retirement_label": "keep_bridge",
            "replacement_surface": "SelectionCtx + ItemCtx private bootstrap",
            "bridge_owner": "lisp_frontend_design_delta/work_item",
            "evidence_refs": ["design_delta_work_item_inputs_ok"],
        }
    }


def _subset_consumer_rendering_census(*row_ids: str) -> dict[str, object]:
    payload = dict(_load_json(CONSUMER_RENDERING_CENSUS_PATH))
    wanted = set(row_ids)
    rows = [
        dict(row)
        for row in payload["rows"]
        if isinstance(row, dict) and row.get("row_id") in wanted
    ]
    assert {row["row_id"] for row in rows} == wanted
    payload["rows"] = rows
    return payload


def _subset_value_flow_census(*row_ids: str) -> dict[str, object]:
    payload = dict(_load_json(VALUE_FLOW_CENSUS_PATH))
    wanted = set(row_ids)
    rows = [
        dict(row)
        for row in payload["rows"]
        if isinstance(row, dict) and row.get("row_id") in wanted
    ]
    assert {row["row_id"] for row in rows} == wanted
    payload["rows"] = rows
    return payload


def _manifest_row(
    *,
    bridge_id: str = "bridge.work_item.pointer.selection_bundle",
    c0_row_id: str = "c0.work_item_pointer_selection_bundle_path",
    u0_row_id: str = "work_item.pointer.selection_bundle_path",
    workflow_surface: str = "lisp_frontend_design_delta/work_item::run-work-item",
    bridge_owner: str = "lisp_frontend_design_delta/work_item",
    consumer: str = "materialize_lisp_frontend_work_item_inputs",
    file_shape: str = "pointer_file",
    binding_name: str | None = None,
) -> dict[str, object]:
    row = {
        "bridge_id": bridge_id,
        "c0_row_id": c0_row_id,
        "u0_row_id": u0_row_id,
        "workflow_surface": workflow_surface,
        "bridge_owner": bridge_owner,
        "consumer": consumer,
        "file_shape": file_shape,
        "typed_value_source": {
            "kind": "compatibility_value_ref",
            "ref": "selection_bundle",
        },
        "renderer": {
            "renderer_id": "posix-path-line",
            "renderer_version": 1,
            "accepted_shape": "path_value",
        },
        "target": {
            "kind": "generated_materialized_view",
            "durability": "durable_bridge",
            "authority_class": "compatibility_bridge",
        },
        "retirement": {
            "allowed_when": "typed bootstrap replaces pointer bridge",
            "replacement_target": "SelectionCtx typed bootstrap",
        },
    }
    if binding_name is not None:
        row["command_boundary"] = {
            "binding_name": binding_name,
            "expected_kind": "certified_adapter",
        }
    return row


def _manifest_payload(*, bridges: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_compatibility_bridge_metadata.v1",
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "source_census": {
            "path": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json",
            "schema_version": "workflow_lisp_private_runtime_value_flow_census.v1",
        },
        "source_consumer_rendering_census": {
            "path": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.consumer_rendering_census.json",
            "schema_version": "workflow_lisp_consumer_rendering_census.v1",
        },
        "bridges": bridges
        if bridges is not None
        else [
            _manifest_row(),
            _manifest_row(
                bridge_id="bridge.work_item.command.selection_bundle",
                c0_row_id="c0.work_item_command_selection_bundle_path",
                u0_row_id="work_item.command.selection_bundle_path",
                file_shape="pointer_file",
                binding_name="materialize_lisp_frontend_work_item_inputs",
            ),
        ],
    }


def test_select_compatibility_bridge_rows_uses_checked_c0_inventory() -> None:
    module = _module()
    selected = module.select_compatibility_bridge_rows(
        _load_json(CONSUMER_RENDERING_CENSUS_PATH)
    )

    assert {row["row_id"] for row in selected} == {
        "c0.drain_bridge_architecture_bundle_path",
        "c0.drain_bridge_manifest_path",
        "c0.drain_bridge_progress_ledger_path",
        "c0.work_item_bridge_architecture_bundle_path",
        "c0.work_item_bridge_manifest_path",
        "c0.work_item_bridge_progress_ledger_path",
        "c0.work_item_pointer_selection_bundle_path",
        "c0.work_item_command_selection_bundle_path",
    }


def test_load_compatibility_bridge_manifest_accepts_checked_blocked_row(
    tmp_path: Path,
) -> None:
    module = _module()
    consumer_rendering_census = _subset_consumer_rendering_census(
        "c0.work_item_pointer_selection_bundle_path",
        "c0.work_item_command_selection_bundle_path",
    )
    value_flow_census = _subset_value_flow_census(
        "work_item.pointer.selection_bundle_path",
        "work_item.command.selection_bundle_path",
    )
    manifest_path = _write_json(
        tmp_path / "compatibility_bridges.json",
        _manifest_payload(),
    )

    payload = module.load_compatibility_bridge_manifest(
        manifest_path,
        value_flow_census=value_flow_census,
        consumer_rendering_census=consumer_rendering_census,
        command_boundary_manifest=_command_boundaries(),
    )

    assert payload["schema_version"] == "workflow_lisp_compatibility_bridge_metadata.v1"
    assert {row["c0_row_id"] for row in payload["bridges"]} == {
        "c0.work_item_pointer_selection_bundle_path",
        "c0.work_item_command_selection_bundle_path",
    }


def test_load_compatibility_bridge_manifest_rejects_uncertified_command_boundary(
    tmp_path: Path,
) -> None:
    module = _module()
    consumer_rendering_census = _subset_consumer_rendering_census(
        "c0.work_item_command_selection_bundle_path",
    )
    value_flow_census = _subset_value_flow_census(
        "work_item.command.selection_bundle_path",
    )
    manifest_path = _write_json(
        tmp_path / "compatibility_bridges.json",
        _manifest_payload(
            bridges=[
                _manifest_row(
                    bridge_id="bridge.work_item.command.selection_bundle",
                    c0_row_id="c0.work_item_command_selection_bundle_path",
                    u0_row_id="work_item.command.selection_bundle_path",
                    binding_name="materialize_lisp_frontend_work_item_inputs",
                )
            ]
        ),
    )

    with pytest.raises(ValueError, match="compatibility_bridge_command_boundary_uncertified"):
        module.load_compatibility_bridge_manifest(
            manifest_path,
            value_flow_census=value_flow_census,
            consumer_rendering_census=consumer_rendering_census,
            command_boundary_manifest={
                "materialize_lisp_frontend_work_item_inputs": {
                    "kind": "external_tool",
                    "stable_command": ["python", "script.py"],
                }
            },
        )


def test_load_compatibility_bridge_manifest_requires_typed_value_source_locator(
    tmp_path: Path,
) -> None:
    module = _module()
    consumer_rendering_census = _subset_consumer_rendering_census(
        "c0.work_item_pointer_selection_bundle_path",
    )
    value_flow_census = _subset_value_flow_census(
        "work_item.pointer.selection_bundle_path",
    )
    row = _manifest_row()
    row["typed_value_source"] = {"kind": "compatibility_value_ref"}
    manifest_path = _write_json(
        tmp_path / "compatibility_bridges.json",
        _manifest_payload(bridges=[row]),
    )

    with pytest.raises(ValueError, match="compatibility_bridge_typed_source_missing"):
        module.load_compatibility_bridge_manifest(
            manifest_path,
            value_flow_census=value_flow_census,
            consumer_rendering_census=consumer_rendering_census,
            command_boundary_manifest=_command_boundaries(),
        )


def test_load_compatibility_bridge_manifest_requires_metadata_for_every_selected_c0_row(
    tmp_path: Path,
) -> None:
    module = _module()
    payload = dict(_load_json(COMPATIBILITY_BRIDGES_PATH))
    payload["bridges"] = [
        row
        for row in payload["bridges"]
        if row["c0_row_id"] != "c0.drain_bridge_manifest_path"
    ]
    manifest_path = _write_json(tmp_path / "compatibility_bridges.json", payload)

    with pytest.raises(
        ValueError,
        match=(
            "compatibility_bridge_required_metadata_missing: "
            "selected C0 compatibility rows missing checked bridge metadata: "
            "c0.drain_bridge_manifest_path"
        ),
    ):
        module.load_compatibility_bridge_manifest(
            manifest_path,
            value_flow_census=_load_json(VALUE_FLOW_CENSUS_PATH),
            consumer_rendering_census=_load_json(CONSUMER_RENDERING_CENSUS_PATH),
            command_boundary_manifest=_command_boundaries(),
        )


def test_build_compatibility_bridge_report_preserves_blocked_command_row(
    tmp_path: Path,
) -> None:
    module = _module()
    consumer_rendering_census = _subset_consumer_rendering_census(
        "c0.work_item_pointer_selection_bundle_path",
        "c0.work_item_command_selection_bundle_path",
    )
    value_flow_census = _subset_value_flow_census(
        "work_item.pointer.selection_bundle_path",
        "work_item.command.selection_bundle_path",
    )
    manifest_path = _write_json(
        tmp_path / "compatibility_bridges.json",
        _manifest_payload(),
    )
    manifest = module.load_compatibility_bridge_manifest(
        manifest_path,
        value_flow_census=value_flow_census,
        consumer_rendering_census=consumer_rendering_census,
        command_boundary_manifest=_command_boundaries(),
    )

    report = module.build_compatibility_bridge_report(
        workflow_family="design_delta_parent_drain",
        manifest=manifest,
        consumer_rendering_census=consumer_rendering_census,
        command_boundary_manifest=_command_boundaries(),
        workflow_boundary_projection={
            "workflows": [
                {
                    "workflow_name": "lisp_frontend_design_delta/work_item::run-work-item",
                    "boundary": {
                        "public_input_names": [],
                        "private_compatibility_bridge_inputs": [
                            "selection_bundle_path"
                        ],
                    },
                }
            ]
        },
        source_map_payload={
            "workflows": {
                "lisp_frontend_design_delta/work_item::run-work-item": {
                    "generated_semantic_effects": [
                        {
                            "effect_kind": "materialize_view",
                            "details": {
                                "authority_class": "compatibility_bridge",
                                "allocation_id": "bridge-allocation",
                            },
                        }
                    ],
                    "generated_path_allocations": [
                        {
                            "allocation_id": "bridge-allocation",
                            "semantic_role": "materialized_value_view",
                        }
                    ],
                }
            }
        },
        materialize_view_effects=[],
    )

    assert report["schema_version"] == "workflow_lisp_compatibility_bridge_report.v1"
    assert report["status"] == "pass"
    assert [row["c0_row_id"] for row in report["blocked_bridges"]] == [
        "c0.work_item_command_selection_bundle_path"
    ]
    assert {
        row["c0_row_id"] for row in report["generated_bridges"]
    } == {"c0.work_item_pointer_selection_bundle_path"}
    assert report["contract_isolation"]["workflow_signature_unchanged"] is True


def test_build_compatibility_bridge_report_fails_closed_when_manifest_omits_selected_row(
    tmp_path: Path,
) -> None:
    module = _module()
    manifest = dict(_load_json(COMPATIBILITY_BRIDGES_PATH))
    manifest["bridges"] = [
        dict(row)
        for row in manifest["bridges"]
        if row["c0_row_id"] != "c0.drain_bridge_manifest_path"
    ]

    report = module.build_compatibility_bridge_report(
        workflow_family="design_delta_parent_drain",
        manifest=manifest,
        consumer_rendering_census=_load_json(CONSUMER_RENDERING_CENSUS_PATH),
        command_boundary_manifest=_command_boundaries(),
        workflow_boundary_projection={
            "workflows": [
                {
                    "workflow_name": "lisp_frontend_design_delta/drain::drain",
                    "boundary": {
                        "public_input_names": [],
                        "private_compatibility_bridge_inputs": [],
                    },
                },
                {
                    "workflow_name": "lisp_frontend_design_delta/work_item::run-work-item",
                    "boundary": {
                        "public_input_names": [],
                        "private_compatibility_bridge_inputs": [
                            "selection_bundle_path"
                        ],
                    },
                },
            ]
        },
        source_map_payload={
            "workflows": {
                "lisp_frontend_design_delta/drain::drain": {
                    "generated_semantic_effects": [
                        {
                            "effect_kind": "materialize_view",
                            "details": {
                                "authority_class": "compatibility_bridge",
                                "allocation_id": "bridge-drain",
                            },
                        }
                    ],
                    "generated_path_allocations": [
                        {
                            "allocation_id": "bridge-drain",
                            "semantic_role": "materialized_value_view",
                        }
                    ],
                },
                "lisp_frontend_design_delta/work_item::run-work-item": {
                    "generated_semantic_effects": [
                        {
                            "effect_kind": "materialize_view",
                            "details": {
                                "authority_class": "compatibility_bridge",
                                "allocation_id": "bridge-work-item",
                            },
                        }
                    ],
                    "generated_path_allocations": [
                        {
                            "allocation_id": "bridge-work-item",
                            "semantic_role": "materialized_value_view",
                        }
                    ],
                },
            }
        },
        materialize_view_effects=[],
    )

    assert report["status"] == "fail"
    assert {
        row["row_id"] for row in report["selected_c0_rows"]
    } == {
        "c0.drain_bridge_architecture_bundle_path",
        "c0.drain_bridge_manifest_path",
        "c0.drain_bridge_progress_ledger_path",
        "c0.work_item_bridge_architecture_bundle_path",
        "c0.work_item_bridge_manifest_path",
        "c0.work_item_bridge_progress_ledger_path",
        "c0.work_item_pointer_selection_bundle_path",
        "c0.work_item_command_selection_bundle_path",
    }
    assert {
        (diagnostic["code"], diagnostic["c0_row_id"])
        for diagnostic in report["diagnostics"]
    } == {
        (
            "compatibility_bridge_required_metadata_missing",
            "c0.drain_bridge_manifest_path",
        )
    }


def test_build_compatibility_bridge_report_fails_without_state_layout_allocation_evidence(
    tmp_path: Path,
) -> None:
    module = _module()
    consumer_rendering_census = _subset_consumer_rendering_census(
        "c0.work_item_pointer_selection_bundle_path",
    )
    value_flow_census = _subset_value_flow_census(
        "work_item.pointer.selection_bundle_path",
    )
    manifest_path = _write_json(
        tmp_path / "compatibility_bridges.json",
        _manifest_payload(
            bridges=[
                _manifest_row(),
            ]
        ),
    )
    manifest = module.load_compatibility_bridge_manifest(
        manifest_path,
        value_flow_census=value_flow_census,
        consumer_rendering_census=consumer_rendering_census,
        command_boundary_manifest=_command_boundaries(),
    )

    report = module.build_compatibility_bridge_report(
        workflow_family="design_delta_parent_drain",
        manifest=manifest,
        consumer_rendering_census=consumer_rendering_census,
        command_boundary_manifest=_command_boundaries(),
        workflow_boundary_projection={
            "workflows": [
                {
                    "workflow_name": "lisp_frontend_design_delta/work_item::run-work-item",
                    "boundary": {
                        "public_input_names": [],
                        "private_compatibility_bridge_inputs": [
                            "selection_bundle_path"
                        ],
                    },
                }
            ]
        },
        source_map_payload={
            "workflows": {
                "lisp_frontend_design_delta/work_item::run-work-item": {
                    "generated_semantic_effects": [
                        {
                            "effect_kind": "materialize_view",
                            "details": {
                                "authority_class": "compatibility_bridge",
                            },
                        }
                    ],
                    "generated_path_allocations": [],
                }
            }
        },
        materialize_view_effects=[],
    )

    assert report["status"] == "fail"
    assert {
        diagnostic["code"] for diagnostic in report["diagnostics"]
    } == {"compatibility_bridge_contract_leak"}


def test_build_compatibility_bridge_report_rejects_non_bridge_materialize_view_evidence(
    tmp_path: Path,
) -> None:
    module = _module()
    consumer_rendering_census = _subset_consumer_rendering_census(
        "c0.work_item_pointer_selection_bundle_path",
    )
    value_flow_census = _subset_value_flow_census(
        "work_item.pointer.selection_bundle_path",
    )
    manifest_path = _write_json(
        tmp_path / "compatibility_bridges.json",
        _manifest_payload(
            bridges=[
                _manifest_row(),
            ]
        ),
    )
    manifest = module.load_compatibility_bridge_manifest(
        manifest_path,
        value_flow_census=value_flow_census,
        consumer_rendering_census=consumer_rendering_census,
        command_boundary_manifest=_command_boundaries(),
    )

    report = module.build_compatibility_bridge_report(
        workflow_family="design_delta_parent_drain",
        manifest=manifest,
        consumer_rendering_census=consumer_rendering_census,
        command_boundary_manifest=_command_boundaries(),
        workflow_boundary_projection={
            "workflows": [
                {
                    "workflow_name": "lisp_frontend_design_delta/work_item::run-work-item",
                    "boundary": {
                        "public_input_names": [],
                        "private_compatibility_bridge_inputs": [
                            "selection_bundle_path"
                        ],
                    },
                }
            ]
        },
        source_map_payload={
            "workflows": {
                "lisp_frontend_design_delta/work_item::run-work-item": {
                    "generated_semantic_effects": [
                        {
                            "effect_kind": "materialize_view",
                            "details": {
                                "authority_class": "public_artifact",
                                "allocation_id": "pub-1",
                            },
                        }
                    ],
                    "generated_path_allocations": [
                        {
                            "allocation_id": "pub-1",
                            "semantic_role": "materialized_value_view",
                        }
                    ],
                }
            }
        },
        materialize_view_effects=[
            {
                "workflow_surface": "lisp_frontend_design_delta/work_item::run-work-item",
                "step_id": "root.some_view",
            }
        ],
    )

    assert report["status"] == "fail"
    assert report["contract_isolation"]["typed_steps_do_not_consume_bridge_views"] is False
    assert {
        diagnostic["code"] for diagnostic in report["diagnostics"]
    } == {"compatibility_bridge_contract_leak"}


def test_build_compatibility_bridge_report_requires_compiled_bridge_effect_evidence(
    tmp_path: Path,
) -> None:
    module = _module()
    consumer_rendering_census = _subset_consumer_rendering_census(
        "c0.work_item_pointer_selection_bundle_path",
    )
    value_flow_census = _subset_value_flow_census(
        "work_item.pointer.selection_bundle_path",
    )
    manifest_path = _write_json(
        tmp_path / "compatibility_bridges.json",
        _manifest_payload(
            bridges=[
                _manifest_row(),
            ]
        ),
    )
    manifest = module.load_compatibility_bridge_manifest(
        manifest_path,
        value_flow_census=value_flow_census,
        consumer_rendering_census=consumer_rendering_census,
        command_boundary_manifest=_command_boundaries(),
    )

    report = module.build_compatibility_bridge_report(
        workflow_family="design_delta_parent_drain",
        manifest=manifest,
        consumer_rendering_census=consumer_rendering_census,
        command_boundary_manifest=_command_boundaries(),
        workflow_boundary_projection={
            "workflows": [
                {
                    "workflow_name": "lisp_frontend_design_delta/work_item::run-work-item",
                    "boundary": {
                        "public_input_names": [],
                        "private_compatibility_bridge_inputs": [
                            "selection_bundle_path"
                        ],
                    },
                }
            ]
        },
        source_map_payload={
            "workflows": {
                "lisp_frontend_design_delta/work_item::run-work-item": {
                    "generated_semantic_effects": [],
                    "generated_path_allocations": [
                        {
                            "allocation_id": "bridge-allocation",
                            "privacy": "compatibility_view",
                            "semantic_role": "compatibility_pointer_view",
                        }
                    ],
                }
            }
        },
        materialize_view_effects=[],
    )

    assert report["status"] == "fail"
    assert report["contract_isolation"]["typed_steps_do_not_consume_bridge_views"] is False
    assert {
        diagnostic["code"] for diagnostic in report["diagnostics"]
    } == {"compatibility_bridge_contract_leak"}
