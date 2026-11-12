from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.workflow_lisp.build_manifest_io import (
    _json_data,
    _parse_command_boundaries_manifest,
)
from orchestrator.workflow_lisp.command_boundaries import (
    CertifiedAdapterBinding,
    CertifiedAdapterInputField,
    ExternalToolBinding,
)
from orchestrator.workflow_lisp.closed.program import (
    canonical_command_configuration,
    canonical_configuration,
    canonical_digest,
    logical_asset_base_for_module,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.compiler import (
    _command_boundary_fingerprint_payload,
    compile_stage3_entrypoint,
)
from orchestrator.workflow_lisp.stdlib_contracts import STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME
from orchestrator.workflow_lisp.workflows import PromptExtern, ProviderExtern
from tests.test_workflow_lisp_target_234 import _build as _build_target_234
from tests.test_workflow_lisp_target_234 import _write_program as _write_target_234_program


REVIEW_LOOP_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "phase_stdlib_review_loop.orc"
)


def _review_loop_entry(tmp_path: Path) -> Path:
    source = REVIEW_LOOP_FIXTURE.read_text(encoding="utf-8").replace(
        '(:target-dsl "2.14")',
        f'(:target-dsl "{syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")',
        1,
    )
    import_form = (
        "  (import std/phase :only "
        "(ReviewDecision ReviewFindings ReviewLoopResult review-revise-loop with-phase))"
    )
    assert import_form in source
    source = source.replace(
        import_form,
        import_form + "\n  (export review-revise-loop-demo)",
        1,
    )
    entry = tmp_path / "phase_stdlib_review_loop.orc"
    entry.write_text(source, encoding="utf-8")
    return entry


def _review_loop_args(tmp_path: Path, command_boundaries=None):
    entry = _review_loop_entry(tmp_path)
    return entry, {
        "source_roots": (tmp_path,),
        "command_boundaries": command_boundaries or {},
        "provider_externs": {
            "providers.review": "provider-review",
            "providers.fix": "provider-fix",
            "providers.unused": "provider-unused",
        },
        "prompt_externs": {
            "prompts.implementation.review": "prompts/review.md",
            "prompts.implementation.fix": "prompts/fix.md",
            "prompts.unused": "prompts/unused.md",
        },
    }


def test_closure_is_parsed_with_absence_distinct_from_an_empty_declaration(tmp_path: Path) -> None:
    payload = {
        "a": {"kind": "external_tool", "stable_command": ["python", "a.py"], "closure": ["lib/", "b.py"]},
        "b": {"kind": "external_tool", "stable_command": ["python", "b.py"]},
        "c": {"kind": "external_tool", "stable_command": ["python", "c.py"], "closure": []},
    }

    bindings = _parse_command_boundaries_manifest(payload, manifest_path=tmp_path / "commands.json")

    assert [bindings[name].closure for name in "abc"] == [("lib/", "b.py"), None, ()]


@pytest.mark.parametrize("kind", ["external_tool", "certified_adapter"])
@pytest.mark.parametrize("closure", [None, "path", [""], ["bad\x00path"], [2]])
def test_manifest_closure_rejects_null_and_invalid_literal_paths(tmp_path: Path, kind, closure) -> None:
    entry = {"kind": kind, "stable_command": ["python", "tool.py"]}
    if closure != "absent":
        entry["closure"] = closure

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _parse_command_boundaries_manifest({"tool": entry}, manifest_path=tmp_path / "commands.json")

    assert excinfo.value.diagnostics[0].code == "command_boundary_manifest_invalid"


def test_command_configuration_normalizes_only_path_components_without_filesystem_reads() -> None:
    binding = ExternalToolBinding(
        name="retained-name",
        stable_command=("python", "./keep//argv"),
        closure=("a//./b", "a/b", "a/../b", "./", "/./", "a/b/c", r"dir\file"),
    )
    with patch.object(Path, "open", side_effect=AssertionError("configuration must not read files")):
        projected = canonical_command_configuration({"lookup": binding}, origins={})

    assert projected["lookup"]["name"] == "retained-name"
    assert projected["lookup"]["stable_command"] == ["python", "./keep//argv"]
    assert projected["lookup"]["closure"] == [
        {"base": "absolute", "path": "/"},
        {"base": "workspace", "path": "."},
        {"base": "workspace", "path": "a/../b"},
        {"base": "workspace", "path": "a/b"},
        {"base": "workspace", "path": "a/b/c"},
        {"base": "workspace", "path": "dir/file"},
    ]
    assert "closure" not in repr(binding)


def test_package_origin_applies_only_to_relative_declarations() -> None:
    binding = ExternalToolBinding(
        name="adapter",
        stable_command=("python", "adapter.py"),
        closure=(".", "/opt/package/file.py"),
    )

    projected = canonical_command_configuration(
        {"same-name": binding},
        origins={"same-name": "package:orchestrator"},
    )

    assert projected["same-name"]["closure"] == [
        {"base": "absolute", "path": "/opt/package/file.py"},
        {"base": "package:orchestrator", "path": "."},
    ]


@pytest.mark.parametrize("kind", ["external_tool", "certified_adapter"])
def test_explicit_empty_closure_is_a_valid_configuration(kind: str) -> None:
    if kind == "external_tool":
        binding = ExternalToolBinding(name="empty", stable_command=("python", "tool.py"), closure=())
    else:
        binding = CertifiedAdapterBinding(
            name="empty",
            stable_command=("python", "tool.py"),
            input_contract={"kind": "object"},
            output_type_name="Int",
            effects=("read",),
            path_safety={"safe": True},
            source_map_behavior="preserve",
            fixture_ids=("ok",),
            negative_fixture_ids=("bad",),
            closure=(),
        )

    assert canonical_command_configuration({"empty": binding}, origins={})["empty"]["closure"] == []


@pytest.mark.parametrize("closure", [("",), ("\x00",), (1,), "not-an-array"])
def test_in_memory_closure_uses_the_manifest_literal_path_grammar(closure) -> None:
    binding = ExternalToolBinding(name="bad", stable_command=("python", "tool.py"), closure=closure)

    with pytest.raises(ValueError):
        canonical_command_configuration({"bad": binding}, origins={})


def test_canonical_projection_keeps_the_exact_common_and_certified_rows() -> None:
    source = STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME["validate_review_findings_v1"]
    certified = replace(
        source,
        output_type_name="Unresolved.Output[RawName]",
        input_signature=(
            CertifiedAdapterInputField(
                name="input",
                type_name="Unresolved.Input[RawName]",
                required=False,
                transport_key="input",
            ),
        ),
        input_contract={"nested": [{"@": "semantic", "value": 3}]},
        path_safety={"@": {"meaning": "metadata"}},
    )
    external = ExternalToolBinding(
        name="different-binding-name",
        stable_command=("python", "./keep/argv"),
        closure=("missing/unused.py",),
    )
    before_contract = json.loads(json.dumps(certified.input_contract))

    rows = canonical_command_configuration(
        {"lookup-external": external, "lookup-certified": certified},
        origins={},
    )

    assert len(rows["lookup-external"]) == 12
    assert len(rows["lookup-certified"]) == 30
    assert rows["lookup-external"]["name"] == "different-binding-name"
    assert rows["lookup-external"]["stable_command"] == ["python", "./keep/argv"]
    assert rows["lookup-external"]["closure"] == [
        {"base": "workspace", "path": "missing/unused.py"}
    ]
    assert rows["lookup-certified"]["output_type_name"] == "Unresolved.Output[RawName]"
    assert rows["lookup-certified"]["input_signature"] == [
        {
            "name": "input",
            "type_name": "Unresolved.Input[RawName]",
            "required": False,
            "transport_key": "input",
        }
    ]
    assert rows["lookup-certified"]["input_contract"] == before_contract
    assert rows["lookup-certified"]["path_safety"] == {"@": {"meaning": "metadata"}}
    assert rows["lookup-certified"]["must_not_repeat"] is False
    assert rows["lookup-certified"]["closure"] == [
        {"base": "workspace", "path": "."}
    ]


def test_three_map_projection_emits_resolved_extern_rows_and_keeps_logical_owner_base() -> None:
    externs = {
        "providers.review": ProviderExtern(
            name="providers.review",
            provider_id="resolved-provider-id",
        ),
        "prompts.review": PromptExtern(
            name="prompts.review",
            source_kind="asset_file",
            path="prompts/./review.md",
        ),
        "prompts.input": PromptExtern(
            name="prompts.input",
            source_kind="input_file",
            path="inputs/review.md",
        ),
    }
    config = canonical_configuration(
        {
            "unused-command": ExternalToolBinding(
                name="unused-command",
                stable_command=("python", "unused.py"),
                closure=("not-present.py",),
            )
        },
        origins={"unused-command": "workspace"},
        externs=externs,
        asset_base=logical_asset_base_for_module("cp/producer"),
    )

    assert set(config) == {"commands", "providers", "prompts"}
    assert config["commands"]["unused-command"]["closure"] == [
        {"base": "workspace", "path": "not-present.py"}
    ]
    assert config["providers"] == {
        "providers.review": {"provider_id": "resolved-provider-id"}
    }
    assert config["prompts"] == {
        "prompts.input": {"source_kind": "input_file", "path": "inputs/review.md"},
        "prompts.review": {
            "source_kind": "asset_file",
            "path": "prompts/./review.md",
            "asset_base": "cp",
        },
    }
    assert logical_asset_base_for_module("root") == "."


def test_three_map_producer_rows_deduplicate_by_semantics_and_keep_unused_identity() -> None:
    externs = {
        "providers.review": ProviderExtern(name="providers.review", provider_id="provider-a"),
        "prompts.review": PromptExtern(
            name="prompts.review",
            source_kind="asset_file",
            path="prompts/review.md",
        ),
    }
    binding = ExternalToolBinding(
        name="shared",
        stable_command=("python", "shared.py"),
        closure=("lib//./helper.py", "lib/helper.py", "lib/../helper.py"),
    )
    first = canonical_configuration(
        {
            "same-lookup": binding,
            "unused": ExternalToolBinding(
                name="unused", stable_command=("python", "unused.py"), closure=("unused.py",)
            ),
        },
        origins={"same-lookup": "workspace", "unused": "workspace"},
        externs=externs,
        asset_base=logical_asset_base_for_module("cp/producer"),
    )
    equal = canonical_configuration(
        {
            "same-lookup": replace(binding, closure=("lib/../helper.py", "lib/helper.py")),
            "unused": ExternalToolBinding(
                name="unused", stable_command=("python", "unused.py"), closure=("unused.py",)
            ),
        },
        origins={"same-lookup": "workspace", "unused": "workspace"},
        externs=externs,
        asset_base=logical_asset_base_for_module("cp/producer"),
    )
    unequal = canonical_configuration(
        {
            "same-lookup": binding,
            "unused": ExternalToolBinding(
                name="unused", stable_command=("python", "changed.py"), closure=("unused.py",)
            ),
        },
        origins={"same-lookup": "workspace", "unused": "workspace"},
        externs={
            **externs,
            "providers.review": ProviderExtern(
                name="providers.review", provider_id="provider-b"
            ),
        },
        asset_base=logical_asset_base_for_module("cp/other_producer"),
    )

    assert first == equal
    assert canonical_digest(first) == canonical_digest(equal)
    assert canonical_digest(first) != canonical_digest(unequal)
    assert first["commands"]["unused"]["name"] == "unused"


def test_injected_package_origin_survives_public_standalone_and_graph_snapshots(
    tmp_path: Path,
) -> None:
    entry, args = _review_loop_args(tmp_path)
    standalone = compile_typed_program(
        entry,
        entry_workflow="review-revise-loop-demo",
        **args,
    )
    graph = compile_stage3_entrypoint(
        entry,
        **args,
        validate_shared=False,
        workspace_root=tmp_path,
    ).entry_result.typed_program

    for typed in (standalone, graph):
        assert typed is not None
        rows = canonical_command_configuration(
            typed.command_boundaries,
            origins=typed.command_boundary_origins,
        )
        assert rows["validate_review_findings_v1"]["closure"] == [
            {"base": "package:orchestrator", "path": "."}
        ]
        assert rows["apply_resource_transition"]["closure"] == [
            {"base": "package:orchestrator", "path": "."}
        ]
        assert "site-packages" not in json.dumps(rows)
        module_origins = typed.configuration_bindings["used_command_boundary_origins"]
        assert module_origins["std/phase"]["validate_review_findings_v1"] == (
            "package:orchestrator"
        )
        assert module_origins["phase_stdlib_review_loop"]["validate_review_findings_v1"] == (
            "package:orchestrator"
        )
        assert typed.configuration_bindings["provider_externs"]["providers.unused"] == (
            "provider-unused"
        )
        assert typed.configuration_bindings["prompt_externs"]["prompts.unused"] == (
            "prompts/unused.md"
        )
        projected = canonical_configuration(
            typed.command_boundaries,
            origins=typed.command_boundary_origins,
            externs=typed.externs,
            asset_base=logical_asset_base_for_module(typed.entry_module),
        )
        assert projected["providers"]["providers.unused"] == {
            "provider_id": "provider-unused"
        }
        assert projected["prompts"]["prompts.unused"] == {
            "source_kind": "asset_file",
            "path": "prompts/unused.md",
            "asset_base": ".",
        }


@pytest.mark.parametrize("override_kind", ["external", "certified"])
def test_effective_same_name_binding_controls_the_trusted_origin(
    tmp_path: Path,
    override_kind: str,
) -> None:
    builtin = STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME["validate_review_findings_v1"]
    if override_kind == "external":
        override = ExternalToolBinding(
            name="validate_review_findings_v1",
            stable_command=builtin.stable_command,
            closure=("manifest-override.py",),
            retirement_class="validation",
            retirement_label="keep_certified_system",
            replacement_surface="typed review findings validation",
            bridge_owner="std/phase",
            expiry_condition="retain for the compatibility test",
            evidence_refs=("validate_review_findings_v1",),
        )
        expected_base, expected_path = "package:orchestrator", "."
    else:
        override = replace(
            builtin,
            closure=("manifest-override.py",),
        )
        expected_base, expected_path = "workspace", "manifest-override.py"

    entry, args = _review_loop_args(
        tmp_path,
        {"validate_review_findings_v1": override},
    )
    typed = compile_typed_program(
        entry,
        entry_workflow="review-revise-loop-demo",
        **args,
    )
    row = canonical_command_configuration(
        typed.command_boundaries,
        origins=typed.command_boundary_origins,
    )["validate_review_findings_v1"]

    assert row["closure"] == [{"base": expected_base, "path": expected_path}]
    assert typed.command_boundary_origins["validate_review_findings_v1"] == expected_base


def test_closure_stays_out_of_legacy_serialization_repr_and_fingerprint() -> None:
    first = ExternalToolBinding(
        name="fetch",
        stable_command=("python", "fetch.py"),
        closure=("first.py",),
    )
    second = replace(first, closure=("second.py",))

    assert "closure" not in repr(first)
    assert "closure" not in _json_data(first)
    assert _command_boundary_fingerprint_payload(first) == _command_boundary_fingerprint_payload(
        second
    )
    assert _json_data({"closure": ["raw-manifest-data"]}) == {
        "closure": ["raw-manifest-data"]
    }


def test_234_build_artifacts_ignore_an_explicit_closure_manifest_field(
    tmp_path: Path,
) -> None:
    root = tmp_path / "program"
    root.mkdir()
    files = _write_target_234_program(root, "2.34")
    key_without_closure, without_closure = _build_target_234(
        files,
        tmp_path / "out-without-closure",
    )
    manifest = json.loads(files["commands"].read_text(encoding="utf-8"))
    (binding_name,) = manifest
    manifest[binding_name]["closure"] = ["unused/closure.py"]
    files["commands"].write_text(json.dumps(manifest), encoding="utf-8")
    key_with_closure, with_closure = _build_target_234(
        files,
        tmp_path / "out-with-closure",
    )

    assert key_without_closure != key_with_closure
    assert set(without_closure) == set(with_closure)
    assert {
        name: content.replace(key_without_closure.encode(), b"<build-key>")
        for name, content in without_closure.items()
    } == {
        name: content.replace(key_with_closure.encode(), b"<build-key>")
        for name, content in with_closure.items()
    }
