from __future__ import annotations

from dataclasses import dataclass, replace
import importlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import MappingProxyType, SimpleNamespace
from typing import Any

import pytest

from orchestrator.providers.executor import (
    ProviderExecutionResult,
    ProviderExecutor,
)
from orchestrator.workflow.run_ref import bundle_transport
from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    compute_compiler_runtime_identity,
)
from orchestrator.workflow_lisp.compiler import (
    LoweringRoute,
    compile_stage3_entrypoint,
)


_FOREIGN_COMPILER_IDENTITY = "sha256:" + "d" * 64
_ASSET_MARKER = "CAPSULE-STAGED-ASSET-MARKER"
_CHILD_MODULE = "orchestrator.workflow.run_ref.child"


@dataclass(frozen=True)
class _CapsuleFixture:
    capsule_dir: Path
    capsule_digest: str
    foreign_capsule_dir: Path
    foreign_capsule_digest: str
    compiler_identity: str
    target_workflow_name: str
    root: Path


def _write_imported_asset_sources(root: Path) -> tuple[Path, Path, Path]:
    source_root = root / "src"
    module_root = source_root / "child_command"
    module_root.mkdir(parents=True)
    child_source = module_root / "asset_child.orc"
    child_source.write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule child_command/asset_child)
  (export render)
  (defworkflow render ((value String)) -> String
    (provider-result providers.render
      :prompt prompts.render
      :inputs (value)
      :returns String)))
""",
        encoding="utf-8",
    )
    entry_source = module_root / "entry.orc"
    entry_source.write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule child_command/entry)
  (import child_command/asset_child :only (render))
  (export run)
  (defworkflow run ((value String)) -> String
    (call render :value value)))
""",
        encoding="utf-8",
    )
    prompt_asset = module_root / "render.md"
    prompt_asset.write_text(
        f"Render the typed value. {_ASSET_MARKER}\n",
        encoding="utf-8",
    )
    return source_root, entry_source, prompt_asset


def _build_capsule(root: Path) -> _CapsuleFixture:
    controller_root = root / "controller"
    source_root, entry_source, prompt_asset = _write_imported_asset_sources(
        controller_root
    )
    compiled = compile_stage3_entrypoint(
        entry_source,
        source_roots=(source_root,),
        entry_workflow="run",
        provider_externs={"providers.render": "local-child-provider"},
        prompt_externs={
            "prompts.render": {"asset_file": prompt_asset.name}
        },
        validate_shared=True,
        workspace_root=controller_root,
        lowering_route=LoweringRoute.WCC_M4,
    )
    target_workflow_name = "child_command/entry::run"
    originals = dict(compiled.validated_bundles_by_name)
    assert target_workflow_name in originals
    import_storage = {name: {} for name in originals}
    catalog = {
        name: replace(
            bundle,
            imports=MappingProxyType(import_storage[name]),
        )
        for name, bundle in originals.items()
    }
    for name, bundle in originals.items():
        import_storage[name].update(
            {
                alias: catalog[imported.surface.name]
                for alias, imported in bundle.imports.items()
            }
        )
    workflow_paths = {
        name: bundle.provenance.workflow_path.relative_to(
            source_root
        ).as_posix()
        for name, bundle in catalog.items()
    }
    source_paths = {
        bundle.provenance.workflow_path.resolve()
        for bundle in catalog.values()
    }
    closure = tuple(
        [
            bundle_transport.BundleCapsuleClosureBlob(
                path=path.relative_to(source_root).as_posix(),
                roles=("orc",),
                payload=path.read_bytes(),
            )
            for path in sorted(source_paths)
        ]
        + [
            bundle_transport.BundleCapsuleClosureBlob(
                path=prompt_asset.relative_to(source_root).as_posix(),
                roles=("prompt_asset",),
                payload=prompt_asset.read_bytes(),
            )
        ]
    )
    compiler_identity = compute_compiler_runtime_identity().digest
    assert compiler_identity != _FOREIGN_COMPILER_IDENTITY
    encoded = bundle_transport.encode_bundle_capsule(
        catalog,
        target_workflow_names=(target_workflow_name,),
        closure=closure,
        workflow_closure_paths=workflow_paths,
        compiler_runtime_identity_digest=compiler_identity,
        lowering_schema_version=2,
    )
    capsule_dir = root / "capsule"
    bundle_transport.write_bundle_capsule_directory(capsule_dir, encoded)
    foreign_encoded = bundle_transport.encode_bundle_capsule(
        catalog,
        target_workflow_names=(target_workflow_name,),
        closure=closure,
        workflow_closure_paths=workflow_paths,
        compiler_runtime_identity_digest=_FOREIGN_COMPILER_IDENTITY,
        lowering_schema_version=2,
    )
    foreign_capsule_dir = root / "foreign-capsule"
    bundle_transport.write_bundle_capsule_directory(
        foreign_capsule_dir,
        foreign_encoded,
    )

    original_paths = (*source_paths, prompt_asset)
    shutil.rmtree(controller_root)
    assert all(not path.exists() for path in original_paths)
    return _CapsuleFixture(
        capsule_dir=capsule_dir,
        capsule_digest=encoded.capsule_digest,
        foreign_capsule_dir=foreign_capsule_dir,
        foreign_capsule_digest=foreign_encoded.capsule_digest,
        compiler_identity=compiler_identity,
        target_workflow_name=target_workflow_name,
        root=root,
    )


@pytest.fixture(scope="module")
def capsule_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> _CapsuleFixture:
    return _build_capsule(tmp_path_factory.mktemp("run-ref-child"))


def _request(
    fixture: _CapsuleFixture,
    *,
    case: str,
    inputs: dict[str, object] | None = None,
) -> tuple[dict[str, object], Path, Path]:
    clone_root = fixture.root / f"clone-{case}"
    clone_root.mkdir()
    state_dir = clone_root / ".orchestrate" / "runs"
    payload: dict[str, object] = {
        "schema_version": "run_ref_child_request.v1",
        "clone_root": clone_root.resolve().as_posix(),
        "capsule_dir": fixture.capsule_dir.resolve().as_posix(),
        "expected_capsule_digest": fixture.capsule_digest,
        "expected_compiler_runtime_identity_digest": fixture.compiler_identity,
        "target_workflow_name": fixture.target_workflow_name,
        "child_run_id": f"child-{case}",
        "child_state_dir": state_dir.resolve().as_posix(),
        "inputs": {"value": "typed-child-input"} if inputs is None else inputs,
    }
    request_path = fixture.root / f"request-{case}.json"
    return payload, request_path, state_dir


def _child_module():
    spec = importlib.util.find_spec(_CHILD_MODULE)
    assert spec is not None, "the private run-ref child command is missing"
    return importlib.import_module(_CHILD_MODULE)


def _invoke(
    payload: dict[str, object],
    request_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    request_path.write_bytes(canonical_json_bytes(payload))
    return_code = _child_module().main(["--request", request_path.as_posix()])
    captured = capsys.readouterr()
    return return_code, captured.out, captured.err


def _assert_canonical_document(stream: str) -> dict[str, Any]:
    assert stream.count("\n") == 1
    document = json.loads(stream)
    assert stream.encode("utf-8") == canonical_json_bytes(document) + b"\n"
    return document


def test_mode1_child_executes_staged_import_and_prompt_asset_without_frontend(
    capsule_fixture: _CapsuleFixture,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.workflow_lisp import compiler, reader

    def reject_frontend(*_args, **_kwargs):
        pytest.fail("mode-1 child execution may not invoke the frontend")

    monkeypatch.setattr(
        compiler,
        "compile_stage3_entrypoint",
        reject_frontend,
    )
    monkeypatch.setattr(reader, "read_sexpr_file", reject_frontend)
    prompts: list[str] = []

    def prepare_invocation(_self, *_args, **kwargs):
        prompt = kwargs.get("prompt_content", "")
        prompts.append(prompt)
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=prompt,
                env=kwargs.get("env") or {},
            ),
            None,
        )

    def execute_provider(
        provider_executor: ProviderExecutor,
        invocation: SimpleNamespace,
        **_kwargs,
    ) -> ProviderExecutionResult:
        print("local provider stdout must remain private")
        print(
            "local provider stderr must remain private",
            file=sys.stderr,
        )
        assert _ASSET_MARKER in invocation.prompt
        assert "typed-child-input" in invocation.prompt
        output_path = (
            provider_executor.workspace
            / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps("staged-import-and-asset-ok") + "\n",
            encoding="utf-8",
        )
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"provider sidecar output",
            stderr=b"",
            duration_ms=1,
        )

    monkeypatch.setattr(
        ProviderExecutor,
        "prepare_invocation",
        prepare_invocation,
    )
    monkeypatch.setattr(ProviderExecutor, "execute", execute_provider)
    payload, request_path, state_dir = _request(
        capsule_fixture,
        case="executes",
    )

    return_code, stdout, stderr = _invoke(payload, request_path, capsys)

    assert return_code == 0
    assert stderr == ""
    result = _assert_canonical_document(stdout)
    assert result == {
        "schema_version": "run_ref_child_result.v1",
        "status": "completed",
        "capsule_digest": capsule_fixture.capsule_digest,
        "target_workflow_name": capsule_fixture.target_workflow_name,
        "child_run_id": "child-executes",
        "workflow_outputs": {"__result__": "staged-import-and-asset-ok"},
    }
    assert len(prompts) == 1
    persisted = json.loads(
        (state_dir / "child-executes" / "state.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted["status"] == "completed"
    assert persisted["workflow_outputs"] == result["workflow_outputs"]


@pytest.mark.parametrize(
    ("field", "bad_value"),
    (
        ("expected_capsule_digest", "sha256:" + "0" * 64),
        (
            "expected_compiler_runtime_identity_digest",
            _FOREIGN_COMPILER_IDENTITY,
        ),
    ),
)
def test_child_rejects_digest_mismatch_before_execution(
    capsule_fixture: _CapsuleFixture,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    field: str,
    bad_value: str,
) -> None:
    def reject_execution(*_args, **_kwargs):
        pytest.fail("digest rejection must precede workflow execution")

    monkeypatch.setattr(ProviderExecutor, "execute", reject_execution)
    payload, request_path, state_dir = _request(
        capsule_fixture,
        case=f"digest-{field}",
    )
    payload[field] = bad_value

    return_code, stdout, stderr = _invoke(payload, request_path, capsys)

    assert return_code != 0
    assert stdout == ""
    diagnostic = _assert_canonical_document(stderr)
    assert diagnostic["schema_version"] == "run_ref_child_diagnostic.v1"
    assert diagnostic["status"] == "rejected"
    assert diagnostic["code"] == "run_ref_capsule_invalid"
    assert diagnostic["reason"] == "capsule_validation_failed"
    assert not (state_dir / payload["child_run_id"]).exists()


def test_child_rejects_foreign_runtime_identity_even_when_request_and_manifest_agree(
    capsule_fixture: _CapsuleFixture,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reject_execution(*_args, **_kwargs):
        pytest.fail("local runtime identity rejection must precede execution")

    monkeypatch.setattr(ProviderExecutor, "execute", reject_execution)
    payload, request_path, state_dir = _request(
        capsule_fixture,
        case="foreign-runtime",
    )
    payload.update(
        {
            "capsule_dir": (
                capsule_fixture.foreign_capsule_dir.resolve().as_posix()
            ),
            "expected_capsule_digest": (
                capsule_fixture.foreign_capsule_digest
            ),
            "expected_compiler_runtime_identity_digest": (
                _FOREIGN_COMPILER_IDENTITY
            ),
        }
    )

    return_code, stdout, stderr = _invoke(payload, request_path, capsys)

    assert return_code != 0
    assert stdout == ""
    diagnostic = _assert_canonical_document(stderr)
    assert diagnostic["code"] == "run_ref_capsule_invalid"
    assert diagnostic["reason"] == "capsule_validation_failed"
    assert not (state_dir / payload["child_run_id"]).exists()


def test_child_rejects_foreign_manifest_under_real_runtime_request(
    capsule_fixture: _CapsuleFixture,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reject_execution(*_args, **_kwargs):
        pytest.fail("manifest identity rejection must precede execution")

    monkeypatch.setattr(ProviderExecutor, "execute", reject_execution)
    payload, request_path, state_dir = _request(
        capsule_fixture,
        case="foreign-manifest",
    )
    payload.update(
        {
            "capsule_dir": (
                capsule_fixture.foreign_capsule_dir.resolve().as_posix()
            ),
            "expected_capsule_digest": (
                capsule_fixture.foreign_capsule_digest
            ),
        }
    )

    return_code, stdout, stderr = _invoke(payload, request_path, capsys)

    assert return_code != 0
    assert stdout == ""
    diagnostic = _assert_canonical_document(stderr)
    assert diagnostic["code"] == "run_ref_capsule_invalid"
    assert diagnostic["reason"] == "capsule_validation_failed"
    assert not (state_dir / payload["child_run_id"]).exists()


def test_child_rejects_target_outside_decoded_targets(
    capsule_fixture: _CapsuleFixture,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reject_execution(*_args, **_kwargs):
        pytest.fail("target rejection must precede workflow execution")

    monkeypatch.setattr(ProviderExecutor, "execute", reject_execution)
    payload, request_path, state_dir = _request(
        capsule_fixture,
        case="target",
    )
    payload["target_workflow_name"] = "child_command/entry::missing"

    return_code, stdout, stderr = _invoke(payload, request_path, capsys)

    assert return_code != 0
    assert stdout == ""
    diagnostic = _assert_canonical_document(stderr)
    assert diagnostic["code"] == "run_ref_capsule_invalid"
    assert diagnostic["reason"] == "target_not_declared"
    assert not (state_dir / payload["child_run_id"]).exists()


@pytest.mark.parametrize(
    "inputs",
    (
        {},
        {"value": "ok", "unknown": True},
        {"value": 7},
    ),
)
def test_child_rejects_invalid_typed_inputs_before_state_initialization(
    capsule_fixture: _CapsuleFixture,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    inputs: dict[str, object],
) -> None:
    def reject_execution(*_args, **_kwargs):
        pytest.fail("input rejection must precede workflow execution")

    monkeypatch.setattr(ProviderExecutor, "execute", reject_execution)
    case = f"inputs-{len(inputs)}-{type(inputs.get('value')).__name__}"
    payload, request_path, state_dir = _request(
        capsule_fixture,
        case=case,
        inputs=inputs,
    )

    return_code, stdout, stderr = _invoke(payload, request_path, capsys)

    assert return_code != 0
    assert stdout == ""
    diagnostic = _assert_canonical_document(stderr)
    assert diagnostic["code"] == "run_ref_child_launch_failed"
    assert diagnostic["reason"] == "input_binding_rejected"
    assert not (state_dir / payload["child_run_id"]).exists()


def test_child_request_is_closed_and_versioned(
    capsule_fixture: _CapsuleFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload, request_path, state_dir = _request(
        capsule_fixture,
        case="closed-request",
    )
    payload["unexpected"] = "not admitted"

    return_code, stdout, stderr = _invoke(payload, request_path, capsys)

    assert return_code != 0
    assert stdout == ""
    diagnostic = _assert_canonical_document(stderr)
    assert diagnostic["code"] == "run_ref_child_launch_failed"
    assert diagnostic["reason"] == "request_invalid"
    assert not (state_dir / payload["child_run_id"]).exists()
