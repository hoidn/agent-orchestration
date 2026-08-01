from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass, replace
import importlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
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
    canonical_sha256,
    compute_compiler_runtime_identity,
)
from orchestrator.workflow.run_ref.config import (
    PathProgram,
    ReferenceBinding,
    RunRefInput,
    build_run_ref_static_config,
    encode_run_ref_static_config,
)
from orchestrator.workflow.run_ref.result_contract import (
    RUN_REF_RESULT_CONTRACT_SCHEMA,
    _accounting_descriptor,
    _workspace_delta_descriptor,
)
from orchestrator.workflow.run_ref.source import (
    MaterializedSource,
    SourceRequest,
    materialize_source,
)
from orchestrator.workflow.executable_ir import (
    RunRefStepConfig,
    StepCommonConfig,
)
from orchestrator.workflow_lisp.compiler import (
    LoweringRoute,
    compile_stage3_entrypoint,
)


_FOREIGN_COMPILER_IDENTITY = "sha256:" + "d" * 64
_ASSET_MARKER = "CAPSULE-STAGED-ASSET-MARKER"
_CHILD_MODULE = "orchestrator.workflow.run_ref.child"
_PATH_SITE = "71d55760c27a0d51" + "0" * 48
_STRING_DESCRIPTOR = {"kind": "primitive", "name": "String"}


@dataclass(frozen=True)
class _CapsuleFixture:
    capsule_dir: Path
    capsule_digest: str
    foreign_capsule_dir: Path
    foreign_capsule_digest: str
    compiler_identity: str
    target_workflow_name: str
    root: Path


@dataclass(frozen=True)
class _PathFixture:
    materialized_source: MaterializedSource
    step_config: RunRefStepConfig
    child_run_id: str
    state_dir: Path
    request_path: Path


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
        "test_control": None,
    }
    request_path = fixture.root / f"request-{case}.json"
    return payload, request_path, state_dir


def _child_module():
    spec = importlib.util.find_spec(_CHILD_MODULE)
    assert spec is not None, "the private run-ref child command is missing"
    return importlib.import_module(_CHILD_MODULE)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", repo.as_posix(), *args),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _path_result_descriptor() -> dict[str, object]:
    envelope = {
        "kind": "record",
        "name": f"RunRefResult${_PATH_SITE[:16]}",
        "fields": [
            {"name": "value", "type": _STRING_DESCRIPTOR},
            {"name": "workspace_delta", "type": _workspace_delta_descriptor()},
            {"name": "accounting", "type": _accounting_descriptor()},
        ],
    }
    return {"schema": RUN_REF_RESULT_CONTRACT_SCHEMA, "envelope": envelope}


def _build_path_fixture(
    root: Path,
    *,
    body: str = "payload",
    case: str = "executes",
) -> _PathFixture:
    repository = root / f"repository-{case}"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    (repository / "candidate.orc").write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.24")',
                "  (defmodule candidate)",
                "  (export run)",
                "  (defworkflow run ((payload String)) -> String",
                f"    {body}))",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    _git(repository, "add", "candidate.orc")
    _git(
        repository,
        "-c",
        "user.name=Run Ref Child Test",
        "-c",
        "user.email=run-ref-child@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "fixture",
    )
    commit = _git(repository, "rev-parse", "HEAD")
    source = SourceRequest(locator=repository.resolve().as_uri(), commit=commit)
    run_ref_root = (root / f"run-ref-{case}").resolve()
    workspace = (
        run_ref_root / "runs" / "parent" / "step" / "1" / "workspace"
    ).resolve()
    materialized = materialize_source(
        source,
        run_ref_root=run_ref_root,
        workspace=workspace,
    )
    result_descriptor = _path_result_descriptor()
    static_config = build_run_ref_static_config(
        compiler_runtime_identity_digest=compute_compiler_runtime_identity().digest,
        site_digest=_PATH_SITE,
        source=source,
        program=PathProgram(
            path="candidate.orc",
            entry_name="run",
            return_refinement=_STRING_DESCRIPTOR,
        ),
        inputs=(
            RunRefInput(
                name="payload",
                type_descriptor=_STRING_DESCRIPTOR,
                binding=ReferenceBinding("inputs.payload"),
            ),
        ),
        result_descriptor=result_descriptor,
        result_digest=canonical_sha256(result_descriptor),
    )
    step_config = RunRefStepConfig(
        common=StepCommonConfig(),
        run_ref=static_config,
    )
    return _PathFixture(
        materialized_source=materialized,
        step_config=step_config,
        child_run_id=f"path-child-{case}",
        state_dir=workspace / ".orchestrate" / "runs",
        request_path=root / f"path-request-{case}.json",
    )


def _path_request(fixture: _PathFixture) -> dict[str, object]:
    child = _child_module()
    static_config_bytes = encode_run_ref_static_config(
        fixture.step_config.run_ref
    )
    return {
        "schema_version": "run_ref_path_child_request.v1",
        "clone_root": fixture.materialized_source.workspace_path.as_posix(),
        "child_state_dir": fixture.state_dir.as_posix(),
        "child_run_id": fixture.child_run_id,
        "materialized_source": child.materialized_source_record(
            fixture.materialized_source
        ),
        "run_ref_static_config_base64": base64.b64encode(
            static_config_bytes
        ).decode("ascii"),
        "expected_step_config_digest": fixture.step_config.step_config_digest,
        "inputs": {"payload": "mode2-child-input"},
        "test_control": None,
    }


def _child_crash_control(
    clone_root: Path,
    *,
    boundary: str,
) -> tuple[dict[str, object], Path]:
    progress_path = (
        clone_root.parent / "run-ref-child-boundary-progress.json"
    ).resolve()
    return (
        {
            "schema_version": "run_ref_child_test_control.v1",
            "boundary": boundary,
            "progress_path": progress_path.as_posix(),
        },
        progress_path,
    )


def _invoke_path(
    payload: dict[str, object],
    request_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    request_path.write_bytes(canonical_json_bytes(payload))
    return_code = _child_module().main(
        ["--path-request", request_path.as_posix()]
    )
    captured = capsys.readouterr()
    return return_code, captured.out, captured.err


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


def test_mode2_child_full_compiles_and_executes_under_run_writer_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    child = _child_module()
    fixture = _build_path_fixture(tmp_path)
    payload = _path_request(fixture)
    active_lock_roots: set[Path] = set()
    lock_events: list[tuple[str, Path]] = []
    compile_calls: list[str] = []
    original_compile = child.compile_and_admit_path_program
    original_initialize = child.StateManager.initialize
    original_execute = child.WorkflowExecutor.execute

    @contextmanager
    def observed_writer_lock(run_root: Path):
        canonical_root = Path(run_root).resolve()
        lock_events.append(("enter", canonical_root))
        active_lock_roots.add(canonical_root)
        try:
            yield
        finally:
            active_lock_roots.remove(canonical_root)
            lock_events.append(("exit", canonical_root))

    def observed_compile(*args, **kwargs):
        compile_calls.append("inside-path-child")
        return original_compile(*args, **kwargs)

    def observed_initialize(manager, *args, **kwargs):
        assert manager.run_root in active_lock_roots
        return original_initialize(manager, *args, **kwargs)

    def observed_execute(executor, *args, **kwargs):
        assert executor.state_manager.run_root in active_lock_roots
        return original_execute(executor, *args, **kwargs)

    monkeypatch.setattr(child, "run_writer_lock", observed_writer_lock)
    monkeypatch.setattr(
        child,
        "compile_and_admit_path_program",
        observed_compile,
    )
    monkeypatch.setattr(child.StateManager, "initialize", observed_initialize)
    monkeypatch.setattr(child.WorkflowExecutor, "execute", observed_execute)

    return_code, stdout, stderr = _invoke_path(
        payload,
        fixture.request_path,
        capsys,
    )

    assert return_code == 0
    assert stderr == ""
    result = _assert_canonical_document(stdout)
    assert result["schema_version"] == "run_ref_path_child_result.v1"
    assert result["status"] == "completed"
    assert result["step_config_digest"] == fixture.step_config.step_config_digest
    assert result["target_workflow_name"] == "candidate::run"
    assert result["child_run_id"] == fixture.child_run_id
    assert result["workflow_outputs"] == {"__result__": "mode2-child-input"}
    assert result["path_compile"]["signature"] == {
        "inputs": [
            {
                "name": "payload",
                "required": True,
                "type": _STRING_DESCRIPTOR,
            }
        ],
        "return": _STRING_DESCRIPTOR,
    }
    assert result["path_compile"]["effect_facts"] == {
        "direct": [],
        "transitive": [],
        "procedure_edges": [],
    }
    assert result["path_compile"]["evidence"]["step_config_digest"] == (
        fixture.step_config.step_config_digest
    )
    run_root = fixture.state_dir / fixture.child_run_id
    assert compile_calls == ["inside-path-child"]
    assert lock_events == [("enter", run_root), ("exit", run_root)]
    persisted = json.loads((run_root / "state.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "completed"
    assert persisted["workflow_outputs"] == result["workflow_outputs"]


@pytest.mark.parametrize(
    "tamper",
    ("materialized_source", "static_config", "step_config_digest", "extra"),
)
def test_mode2_child_rejects_tampered_or_open_request_before_compile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tamper: str,
) -> None:
    child = _child_module()
    fixture = _build_path_fixture(tmp_path, case=f"tamper-{tamper}")
    payload = _path_request(fixture)
    if tamper == "materialized_source":
        materialized = dict(payload["materialized_source"])
        materialized["verified_git_tree"] = "git-tree:" + "f" * 40
        payload["materialized_source"] = materialized
    elif tamper == "static_config":
        payload["run_ref_static_config_base64"] = "not-canonical-base64!"
    elif tamper == "step_config_digest":
        payload["expected_step_config_digest"] = "sha256:" + "0" * 64
    else:
        payload["unexpected"] = "open-envelope"

    def reject_compile(*_args, **_kwargs):
        pytest.fail("invalid path requests must reject before compilation")

    monkeypatch.setattr(child, "compile_and_admit_path_program", reject_compile)

    return_code, stdout, stderr = _invoke_path(
        payload,
        fixture.request_path,
        capsys,
    )

    assert return_code != 0
    assert stdout == ""
    diagnostic = _assert_canonical_document(stderr)
    assert diagnostic == {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "run_ref_child_launch_failed",
        "reason": "request_invalid",
    }
    assert not (fixture.state_dir / fixture.child_run_id).exists()


def test_mode2_compile_refusal_preserves_structured_machine_diagnostic(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = _build_path_fixture(
        tmp_path,
        body="missing_name",
        case="compile-refusal",
    )
    payload = _path_request(fixture)

    return_code, stdout, stderr = _invoke_path(
        payload,
        fixture.request_path,
        capsys,
    )

    assert return_code != 0
    assert stdout == ""
    diagnostic = _assert_canonical_document(stderr)
    assert diagnostic["schema_version"] == "run_ref_child_diagnostic.v1"
    assert diagnostic["status"] == "rejected"
    assert diagnostic["code"] == "trial_program_compile_rejected"
    assert diagnostic["reason"] == "path_compile_rejected"
    assert diagnostic["secondary_causes"] == ["name_unknown"]
    assert diagnostic["rejected_value"] == {
        "program": fixture.step_config.run_ref.program.record,
        "compile_diagnostics": diagnostic["compile_diagnostics"],
    }
    assert diagnostic["compile_diagnostics"]["status"] == "rejected"
    assert [
        row["code"] for row in diagnostic["compile_diagnostics"]["diagnostics"]
    ] == ["name_unknown"]
    assert not (fixture.state_dir / fixture.child_run_id).exists()


def test_mode2_structural_refusal_without_compile_document_has_closed_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.workflow.run_ref.path_compile import (
        RunRefPathCompileRefusal,
    )

    child = _child_module()
    fixture = _build_path_fixture(tmp_path, case="structural-refusal")
    payload = _path_request(fixture)
    rejected_value = fixture.step_config.run_ref.program.record

    def refuse(*_args, **_kwargs):
        raise RunRefPathCompileRefusal(
            "trial_program_missing",
            rejected_value,
            secondary_causes=("program_missing",),
        )

    monkeypatch.setattr(child, "compile_and_admit_path_program", refuse)

    return_code, stdout, stderr = _invoke_path(
        payload,
        fixture.request_path,
        capsys,
    )

    assert return_code == 2
    assert stdout == ""
    assert _assert_canonical_document(stderr) == {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "trial_program_missing",
        "reason": "path_compile_rejected",
        "rejected_value": rejected_value,
        "secondary_causes": ["program_missing"],
    }


def test_mode2_malformed_structural_failure_authority_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.workflow.run_ref.path_compile import (
        RunRefPathCompileRefusal,
    )

    child = _child_module()
    fixture = _build_path_fixture(tmp_path, case="malformed-authority")
    payload = _path_request(fixture)
    malformed_diagnostics = {
        "schema_version": "workflow_lisp_compile_diagnostics.v1",
        "status": "rejected",
        "diagnostics": [],
        "unexpected": "open-machine-authority",
    }

    def refuse(*_args, **_kwargs):
        raise RunRefPathCompileRefusal(
            "trial_program_compile_rejected",
            {
                "program": fixture.step_config.run_ref.program.record,
                "compile_diagnostics": malformed_diagnostics,
            },
            secondary_causes=("name_unknown",),
            compile_diagnostics_document=malformed_diagnostics,
        )

    monkeypatch.setattr(child, "compile_and_admit_path_program", refuse)

    return_code, stdout, stderr = _invoke_path(
        payload,
        fixture.request_path,
        capsys,
    )

    assert return_code == 1
    assert stdout == ""
    assert _assert_canonical_document(stderr) == {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "run_ref_child_result_invalid",
        "reason": "child_failure_authority_invalid",
    }


def test_child_diagnostic_validator_is_pure_and_rejects_open_runtime_details() -> None:
    child = _child_module()
    source = {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "run_ref_child_launch_failed",
        "reason": "request_invalid",
    }

    validated = child.validate_child_diagnostic_document(source)
    source["code"] = "changed-after-validation"

    assert validated == {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "run_ref_child_launch_failed",
        "reason": "request_invalid",
    }
    with pytest.raises(ValueError, match="runtime child diagnostic authority"):
        child.validate_child_diagnostic_document(
            {**validated, "unexpected": "open-machine-authority"}
        )


def test_child_test_control_is_closed_and_mode_specific(
    capsule_fixture: _CapsuleFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload, request_path, state_dir = _request(
        capsule_fixture,
        case="wrong-test-boundary",
    )
    control, progress_path = _child_crash_control(
        Path(payload["clone_root"]),
        boundary="mode_2_compile",
    )
    payload["test_control"] = control

    return_code, stdout, stderr = _invoke(payload, request_path, capsys)

    assert return_code == 2
    assert stdout == ""
    assert _assert_canonical_document(stderr) == {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "run_ref_child_launch_failed",
        "reason": "request_invalid",
    }
    assert not progress_path.exists()
    assert not (state_dir / payload["child_run_id"]).exists()


def test_parent_launched_mode1_child_crashes_after_actual_decode_boundary(
    capsule_fixture: _CapsuleFixture,
) -> None:
    payload, request_path, state_dir = _request(
        capsule_fixture,
        case="crash-after-decode",
    )
    control, progress_path = _child_crash_control(
        Path(payload["clone_root"]),
        boundary="mode_1_decode",
    )
    payload["test_control"] = control
    request_path.write_bytes(canonical_json_bytes(payload))

    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            _CHILD_MODULE,
            "--request",
            request_path.as_posix(),
        ),
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 86
    assert completed.stdout == b""
    assert completed.stderr == b""
    assert json.loads(progress_path.read_text(encoding="utf-8")) == {
        "schema_version": "run_ref_child_boundary_progress.v1",
        "boundary": "mode_1_decode",
    }
    assert not (state_dir / payload["child_run_id"]).exists()


def test_parent_launched_mode2_child_crashes_after_actual_compile_boundary(
    tmp_path: Path,
) -> None:
    fixture = _build_path_fixture(tmp_path, case="crash-after-compile")
    payload = _path_request(fixture)
    control, progress_path = _child_crash_control(
        fixture.materialized_source.workspace_path,
        boundary="mode_2_compile",
    )
    payload["test_control"] = control
    fixture.request_path.write_bytes(canonical_json_bytes(payload))

    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            _CHILD_MODULE,
            "--path-request",
            fixture.request_path.as_posix(),
        ),
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 86
    assert completed.stdout == b""
    assert completed.stderr == b""
    assert json.loads(progress_path.read_text(encoding="utf-8")) == {
        "schema_version": "run_ref_child_boundary_progress.v1",
        "boundary": "mode_2_compile",
    }
    assert not (fixture.state_dir / fixture.child_run_id).exists()
