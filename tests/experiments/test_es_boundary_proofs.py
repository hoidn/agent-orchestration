from __future__ import annotations

import ast
import copy
import dis
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from types import CodeType, ModuleType
from typing import Any, NoReturn

import pytest
from jsonschema import Draft202012Validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPOSITORY_ROOT / "scripts/experiments/es/boundary_proofs.py"
RUNNER_RELATIVE_PATH = "scripts/experiments/es/boundary_proofs.py"
PINNED_PYTHON = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
PINNED_PYTHON_TARGET = Path(
    "/home/ollie/miniconda3/envs/ptycho311/bin/python3.11"
)
PINNED_PYTEST_CARRIER = Path("/usr/bin/bwrap")
PINNED_PYTEST_CARRIER_SHA256 = (
    "sha256:52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712"
)
PYTEST_CARRIER_AUTHORITY = {
    "pytest_carrier": PINNED_PYTEST_CARRIER,
    "expected_pytest_carrier_sha256": PINNED_PYTEST_CARRIER_SHA256,
}
SAMPLING_RULE = (
    "first_observable_per_provider_and_disposition_witness_class_"
    "in_discovery_order.v1"
)
SELECTOR_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "docs/plans/evidence/es-f1-large-scope-refreeze/preedit-selector-manifest.schema.json"
)
SOURCE_CENSUS_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "docs/plans/evidence/es-f1-large-scope-refreeze/source-census.schema.json"
)
MANDATORY_PROVIDER_MODULES = (
    "tests/torch/test_generator_registry.py",
    "tests/torch/test_construction_consolidation.py",
    "tests/torch/test_generator_adapter.py",
    "tests/torch/test_config_bridge.py",
    "tests/torch/test_model_spec.py",
    "tests/torch/test_model_spec_v2.py",
    "tests/torch/test_lightning_checkpoint.py",
    "tests/torch/test_artifact_schema.py",
    "tests/torch/test_artifact_schema_v2.py",
    "tests/torch/test_workflows_components.py",
    "tests/torch/test_fno_generators.py",
    "tests/torch/test_fno_lightning_integration.py",
    "tests/torch/test_neuralop_uno_generator.py",
    "tests/torch/test_model_output_modes.py",
    "tests/torch/test_model_manager.py",
    "tests/torch/test_model_training.py",
    "tests/torch/test_train_lightning_execution_contract.py",
    "tests/torch/test_object_big_generator_contract.py",
    "tests/torch/test_structural_config_ownership.py",
)

NORMALIZED_AUTOGRAPH_ROWS = (
    (
        "<normalized-runtime-owned:autograph-generated-module:0001>",
        "<normalized-runtime-owned:autograph-generated-origin:0001>",
    ),
    (
        "<normalized-runtime-owned:autograph-generated-module:0002>",
        "<normalized-runtime-owned:autograph-generated-origin:0002>",
    ),
)
NORMALIZED_TORCH_REMOTE_ROW = (
    "_remote_module_non_scriptable",
    "<normalized-runtime-owned:torch-remote-module-non-scriptable-origin>",
)


def _runner() -> ModuleType:
    if not RUNNER_PATH.is_file():
        pytest.skip("Task-0 boundary proof runner is not implemented")
    spec = importlib.util.spec_from_file_location("es_boundary_proofs", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *args),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.decode("utf-8", "strict").strip()


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _inner_process_argv(argv: Any) -> list[str]:
    values = [str(value) for value in argv]
    if values and values[0] == str(PINNED_PYTEST_CARRIER) and "--" in values:
        separator = values.index("--")
        return values[separator + 1 :]
    return values


def _verified_pytest_carrier(runner: ModuleType) -> Any:
    return runner._verify_pytest_carrier(  # pyright: ignore[reportPrivateUsage]
        PINNED_PYTEST_CARRIER,
        expected_sha256=PINNED_PYTEST_CARRIER_SHA256,
    )


def _seal(runner: ModuleType, body: dict[str, Any]) -> dict[str, Any]:
    record = copy.deepcopy(body)
    record["record_sha256"] = runner.compute_record_sha256(record)
    return record


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(repository: Path, message: str) -> str:
    _git(repository, "add", "-A")
    _git(
        repository,
        "-c",
        "user.name=Boundary Proof Tests",
        "-c",
        "user.email=boundary-proofs@example.invalid",
        "commit",
        "-q",
        "-m",
        message,
    )
    return _git(repository, "rev-parse", "HEAD^{tree}")


def _blob(repository: Path, relative_path: str) -> str:
    return _git(repository, "rev-parse", f"HEAD:{relative_path}")


def _physical_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="strict").splitlines())


@dataclass(frozen=True)
class ContractFixture:
    workspace: Path
    manifest: dict[str, Any]
    consumer_rows: list[dict[str, Any]]
    baseline_tree: str
    provider_modules: tuple[str, ...]
    node_ids: tuple[str, ...]
    witness_ids: tuple[str, ...]


def test_task0_boundary_proof_runner_is_present() -> None:
    assert RUNNER_PATH.is_file(), "Task-0 boundary proof runner is not implemented"


def test_task0_runtime_temp_origin_normalization_is_deterministic_and_lossless() -> None:
    runner = _runner()
    retained_rows = [
        ["ordinary_tmp_module", "/tmp/ordinary_tmp_module.py"],
        [
            "es_boundary_probe_plugin",
            "<runtime-owned:es-boundary-probe-plugin>",
        ],
        [
            "es_exact_source_event_observer",
            "<runtime-owned:es-exact-source-event-observer>",
        ],
    ]
    first = [
        ["__autograph_generated_fileaaaaaaaa", "/tmp/__autograph_generated_fileaaaaaaaa.py"],
        ["_remote_module_non_scriptable", "/tmp/tmpbbbbbbbb/_remote_module_non_scriptable.py"],
        ["__autograph_generated_filecccccccc", "/tmp/__autograph_generated_filecccccccc.py"],
        *copy.deepcopy(retained_rows),
    ]
    second = [
        ["__autograph_generated_filedddddddd", "/tmp/__autograph_generated_filedddddddd.py"],
        ["_remote_module_non_scriptable", "/tmp/tmpeeeeeeee/_remote_module_non_scriptable.py"],
        ["__autograph_generated_fileffffffff", "/tmp/__autograph_generated_fileffffffff.py"],
        *copy.deepcopy(retained_rows),
    ]

    normalized_first = runner._normalize_runtime_owned_temporary_origins(  # pyright: ignore[reportPrivateUsage]
        first
    )
    normalized_second = runner._normalize_runtime_owned_temporary_origins(  # pyright: ignore[reportPrivateUsage]
        second
    )

    assert normalized_first == normalized_second
    assert len(normalized_first) == len(first) == len(second)
    assert normalized_first[:3] == [
        list(NORMALIZED_AUTOGRAPH_ROWS[0]),
        list(NORMALIZED_TORCH_REMOTE_ROW),
        list(NORMALIZED_AUTOGRAPH_ROWS[1]),
    ]
    assert normalized_first[3:] == retained_rows
    assert first[0][0] == "__autograph_generated_fileaaaaaaaa"
    assert second[0][0] == "__autograph_generated_filedddddddd"


@pytest.mark.parametrize(
    "row",
    (
        [
            "__autograph_generated_fileaaaaaaaa",
            "/tmp/__autograph_generated_filebbbbbbbb.py",
        ],
        [
            "__autograph_generated_fileaaaaaaa",
            "/tmp/__autograph_generated_fileaaaaaaa.py",
        ],
        [
            "__autograph_generated_fileaaaaaaaa",
            "/tmp/nested/__autograph_generated_fileaaaaaaaa.py",
        ],
        [
            "_remote_module_non_scriptable",
            "/tmp/not-tmpaaaaaaaa/_remote_module_non_scriptable.py",
        ],
        [
            "_remote_module_non_scriptable_extra",
            "/tmp/tmpaaaaaaaa/_remote_module_non_scriptable.py",
        ],
        ["unknown_runtime_module", "/tmp/tmpaaaaaaaa/unknown_runtime_module.py"],
    ),
)
def test_task0_runtime_temp_origin_normalization_retains_near_misses(
    row: list[str],
) -> None:
    runner = _runner()

    assert runner._normalize_runtime_owned_temporary_origins(  # pyright: ignore[reportPrivateUsage]
        [row]
    ) == [row]


def test_selector_schema_json_values_match_integer_only_canonical_loader() -> None:
    schema = json.loads(SELECTOR_SCHEMA_PATH.read_text(encoding="utf-8"))
    json_value_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": schema["$defs"],
        "$ref": "#/$defs/json_value",
    }
    validator = Draft202012Validator(json_value_schema)

    assert list(validator.iter_errors(7)) == []
    assert list(validator.iter_errors(7.25))


@pytest.mark.parametrize("record_kind", ("selector", "census"))
def test_authority_loader_rejects_partial_records_against_closed_schemas(
    record_kind: str,
    tmp_path: Path,
) -> None:
    runner = _runner()
    if record_kind == "selector":
        record = _seal(
            runner,
            {
                "provider_visible_pytest_selectors": [],
                "controller_only_proof_selectors": [],
                "coverage_witnesses": [],
                "desired_state_proof_specs": [],
            },
        )
        schema_path = SELECTOR_SCHEMA_PATH
    else:
        record = _seal(runner, {"consumer_rows": []})
        schema_path = SOURCE_CENSUS_SCHEMA_PATH
    path = (tmp_path / f"partial-{record_kind}.json").resolve()
    raw = runner.canonical_json_bytes(record)
    path.write_bytes(raw)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.load_closed_canonical_record(
            path,
            schema_path=schema_path.resolve(),
            expected_sha256=_sha256(raw),
        )

    assert caught.value.code == "proof_record_schema_invalid"


def test_authority_loader_rejects_stale_self_digest_before_schema_result(
    tmp_path: Path,
) -> None:
    runner = _runner()
    record = _seal(runner, {"consumer_rows": []})
    record["consumer_rows"] = [{"tampered": True}]
    path = (tmp_path / "stale-census.json").resolve()
    raw = runner.canonical_json_bytes(record)
    path.write_bytes(raw)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.load_closed_canonical_record(
            path,
            schema_path=SOURCE_CENSUS_SCHEMA_PATH.resolve(),
            expected_sha256=_sha256(raw),
        )

    assert caught.value.code == "proof_record_digest_invalid"


@pytest.mark.parametrize("tamper", ("census_digest", "policy_digest"))
def test_authority_join_rejects_cross_record_digest_drift(tamper: str) -> None:
    runner = _runner()
    policy_digest = "sha256:" + "1" * 64
    census = _seal(
        runner,
        {
            "preedit_policy_sha256": policy_digest,
            "consumer_rows": [],
        },
    )
    manifest = _seal(
        runner,
        {
            "preedit_policy_sha256": policy_digest,
            "source_census_sha256": census["record_sha256"],
        },
    )
    if tamper == "census_digest":
        manifest["source_census_sha256"] = "sha256:" + "2" * 64
    else:
        manifest["preedit_policy_sha256"] = "sha256:" + "2" * 64
    manifest["record_sha256"] = runner.compute_record_sha256(manifest)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.validate_authority_bindings(manifest, census)

    assert caught.value.code == "proof_authority_binding_mismatch"


def test_runner_pins_git_and_drops_ambient_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    observed: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def fake_run(argv: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        observed.append((argv, kwargs["env"]))
        if argv == ("/usr/bin/git", "--version"):
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=b"git version 2.43.0\n",
                stderr=b"",
            )
        return subprocess.CompletedProcess(argv, 0, stdout=b"pinned\n", stderr=b"")

    monkeypatch.setenv("HOME", "/ambient-home")
    monkeypatch.setenv("PATH", "/ambient-bin")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/ambient-config")
    monkeypatch.setenv("AMBIENT_SENTINEL", "must-not-leak")
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    assert runner._run_git(tmp_path.resolve(), "rev-parse", "HEAD^{tree}") == b"pinned\n"
    expected_env = {
        "HOME": "/",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0",
    }
    assert observed == [
        (("/usr/bin/git", "--version"), expected_env),
        (
            (
                "/usr/bin/git",
                "-C",
                str(tmp_path.resolve()),
                "rev-parse",
                "HEAD^{tree}",
            ),
            expected_env,
        ),
    ]


def test_runner_rejects_unpinned_git_bytes_before_invocation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    fake_git = tmp_path / "git"
    fake_git.write_bytes(b"not the pinned git executable\n")
    monkeypatch.setattr(runner, "PINNED_GIT", fake_git)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner._run_git(tmp_path.resolve(), "rev-parse", "HEAD^{tree}")

    assert caught.value.code == "proof_git_identity_mismatch"


def test_runner_rejects_unpinned_git_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()

    def fake_run(argv: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert argv == ("/usr/bin/git", "--version")
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=b"git version 9.99.0\n",
            stderr=b"",
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner._run_git(tmp_path.resolve(), "rev-parse", "HEAD^{tree}")

    assert caught.value.code == "proof_git_identity_mismatch"


def test_cli_rejects_stale_runner_before_reading_any_proof_input(
    tmp_path: Path,
) -> None:
    missing = (tmp_path / "unreadable.json").resolve()
    completed = subprocess.run(
        (
            str(Path(sys.executable).resolve()),
            str(RUNNER_PATH),
            "baseline",
            "--selector-manifest",
            str(missing),
            "--expected-selector-manifest-sha256",
            "sha256:" + "0" * 64,
            "--selector-manifest-schema",
            str(missing),
            "--source-census",
            str(missing),
            "--expected-source-census-sha256",
            "sha256:" + "0" * 64,
            "--source-census-schema",
            str(missing),
            "--python",
            str(Path(sys.executable).resolve()),
            "--workspace",
            str(tmp_path.resolve()),
            "--expected-tree",
            "0" * 40,
            "--expected-runner-sha256",
            "sha256:" + "0" * 64,
            "--pytest-carrier",
            str(PINNED_PYTEST_CARRIER),
            "--expected-pytest-carrier-sha256",
            PINNED_PYTEST_CARRIER_SHA256,
            "--report-path",
            str((tmp_path / "report.json").resolve()),
            "--output",
            str((tmp_path / "output.json").resolve()),
        ),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode == 2
    assert completed.stderr.decode("utf-8", "strict").startswith(
        "proof_runner_digest_mismatch:"
    )


def test_runner_pins_literal_python_symlink_target_bytes_and_version() -> None:
    runner = _runner()

    assert runner._verify_pinned_python(PINNED_PYTHON) == (
        PINNED_PYTHON,
        PINNED_PYTHON_TARGET,
    )


@pytest.mark.parametrize(
    "substitute",
    (PINNED_PYTHON_TARGET, Path(sys.executable).resolve()),
)
def test_runner_rejects_python_path_substitution(substitute: Path) -> None:
    runner = _runner()

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner._verify_pinned_python(substitute)

    assert caught.value.code == "proof_python_identity_mismatch"


def test_runner_rejects_alternate_symlink_to_pinned_python_target(
    tmp_path: Path,
) -> None:
    runner = _runner()
    substitute = (tmp_path / "python").resolve()
    substitute.symlink_to(PINNED_PYTHON_TARGET)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner._verify_pinned_python(substitute)

    assert caught.value.code == "proof_python_identity_mismatch"


def test_baseline_rejects_substitute_python_before_pytest(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.capture_baseline(
            contract_fixture.manifest,
            consumer_rows=contract_fixture.consumer_rows,
            python=Path(sys.executable).resolve(),
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            report_path=(tmp_path / "substitute-python-report.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_python_identity_mismatch"


def _consumer_row(
    repository: Path,
    *,
    consumer_id: str,
    match_id: str,
    path: str,
    start_line: int,
    end_line: int,
    column_start: int = 0,
    column_end: int = 0,
    proof_kind: str,
    selector_id: str,
    witness_kind: str,
    witness_id: str,
) -> dict[str, Any]:
    dispositions = {
        "boundary_runtime": "route_through_boundary",
        "non_cdi_static": "compatibility_adapter",
        "reference_absence": "remove",
    }
    return {
        "consumer_id": consumer_id,
        "match_id": match_id,
        "caller_path": path,
        "caller_object_id": _blob(repository, path),
        "span": {
            "line_start": start_line,
            "column_start": column_start,
            "line_end": end_line,
            "column_end": column_end,
        },
        "proposed_disposition": dispositions[proof_kind],
        "required_proof_kind": proof_kind,
        "selector_id": selector_id,
        "witness_kind": witness_kind,
        "coverage_status": "required",
        "coverage_witness_ids": [witness_id],
    }


def _expected_callable_source_event(
    *,
    source: str,
    source_path: Path,
    consumer_path: str,
    caller_object_id: str,
    function_name: str,
    span: dict[str, int],
    binding: dict[str, Any],
) -> dict[str, Any]:
    assert source_path.read_text(encoding="utf-8") == source
    encoded_name = function_name.encode("utf-8")
    first_line = source.splitlines()[span["line_start"] - 1].encode("utf-8")
    assert first_line[span["column_start"] : span["column_end"]] == encoded_name
    tree = ast.parse(source, filename=str(source_path))
    definitions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    assert len(definitions) == 1
    definition = definitions[0]
    root_code = compile(
        source,
        str(source_path),
        "exec",
        dont_inherit=True,
        optimize=0,
    )
    code_objects: list[CodeType] = []
    pending = [root_code]
    while pending:
        code = pending.pop(0)
        code_objects.append(code)
        pending.extend(
            value for value in code.co_consts if isinstance(value, CodeType)
        )
    first_definition_line = min(
        [definition.lineno]
        + [decorator.lineno for decorator in definition.decorator_list]
    )
    matches = [
        code
        for code in code_objects
        if code.co_name == function_name
        and code.co_firstlineno == first_definition_line
    ]
    assert len(matches) == 1
    code = matches[0]
    return {
        "event_kind": binding["event_kind"],
        "phase": binding["phase"],
        "attribution": copy.deepcopy(binding["attribution"]),
        "consumer_path": consumer_path,
        "caller_object_id": caller_object_id,
        "span": copy.deepcopy(span),
        "hit_count": 1,
        "callable_entry": {
            "code_qualname": code.co_qualname,
            "code_name": code.co_name,
            "code_firstlineno": code.co_firstlineno,
            "definition_span": {
                "line_start": definition.lineno,
                "column_start": definition.col_offset,
                "line_end": definition.end_lineno,
                "column_end": definition.end_col_offset,
            },
        },
    }


@pytest.fixture
def contract_fixture(tmp_path: Path) -> ContractFixture:
    runner = _runner()
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    _git(workspace, "init", "-q")
    _write(workspace / "pkg/__init__.py", "")

    provider_modules: list[str] = []
    node_ids: list[str] = []
    provider_consumers: list[tuple[str, str, str, str]] = []
    for ordinal, test_path in enumerate(MANDATORY_PROVIDER_MODULES, start=1):
        suffix = f"{ordinal:02d}"
        consumer_path = f"pkg/consumer_{suffix}.py"
        node_id = f"{test_path}::test_consumer_{suffix}"
        _write(
            workspace / consumer_path,
            f"def consumer_{suffix}():\n    return 'boundary-{suffix}'\n",
        )
        _write(
            workspace / test_path,
            (
                f"from pkg.consumer_{suffix} import consumer_{suffix}\n\n"
                f"def test_consumer_{suffix}():\n"
                f"    assert consumer_{suffix}() == 'boundary-{suffix}'\n"
            ),
        )
        provider_modules.append(test_path)
        node_ids.append(node_id)
        provider_consumers.append(
            (f"consumer-{suffix}", f"match-{suffix}", consumer_path, node_id)
        )

    _write(workspace / "pkg/compat.py", "VALUE = 1\n")
    _write(workspace / "pkg/remove_me.py", "DEPRECATED = True\n")
    _write(
        workspace / "pkg/runtime_target.py",
        (
            "def exercise(value):\n"
            "    return {'boundary': 'delegated', 'value': value}\n"
        ),
    )
    _write(
        workspace / "pkg/runtime_import.py",
        "from pkg.consumer_01 import consumer_01\n",
    )
    _write(workspace / "proof_inputs/contract.json", "{}\n")
    baseline_tree = _commit(workspace, "baseline")

    runner_digest = runner.runner_sha256()
    provider_rows: list[dict[str, Any]] = []
    witnesses: list[dict[str, Any]] = []
    specs: list[dict[str, Any]] = []
    consumer_rows: list[dict[str, Any]] = []

    for ordinal, (consumer_id, match_id, consumer_path, node_id) in enumerate(
        provider_consumers,
        start=1,
    ):
        selector_id = f"provider-{ordinal:02d}"
        witness_id = f"w-provider-{ordinal:02d}"
        test_path = provider_modules[ordinal - 1]
        consumer_source_path = (workspace / consumer_path).resolve()
        consumer_source = consumer_source_path.read_text(encoding="utf-8")
        consumer_blob = _blob(workspace, consumer_path)
        consumer_span = {
            "line_start": 1,
            "column_start": 4,
            "line_end": 1,
            "column_end": 15,
        }
        binding = {
            "event_kind": "callable_entry",
            "phase": "call",
            "attribution": {
                "attribution_kind": "pytest_node",
                "pytest_node_id": node_id,
            },
        }
        expected = _expected_callable_source_event(
            source=consumer_source,
            source_path=consumer_source_path,
            consumer_path=consumer_path,
            caller_object_id=consumer_blob,
            function_name=f"consumer_{ordinal:02d}",
            span=consumer_span,
            binding=binding,
        )
        provider_rows.append(
            {
                "selector_id": selector_id,
                "ordinal": ordinal,
                "pytest_module_path": test_path,
                "projection_blob_id": _blob(workspace, test_path),
                "mode": "100644",
                "physical_line_count": _physical_lines(workspace / test_path),
                "pytest_node_ids": [node_id],
                "coverage_witness_ids": [witness_id],
            }
        )
        consumer_rows.append(
            _consumer_row(
                workspace,
                consumer_id=consumer_id,
                match_id=match_id,
                path=consumer_path,
                start_line=1,
                end_line=1,
                column_start=4,
                column_end=15,
                proof_kind="boundary_runtime",
                selector_id=selector_id,
                witness_kind="pytest_runtime",
                witness_id=witness_id,
            )
        )
        witnesses.append(
            {
                "witness_id": witness_id,
                "selector_id": selector_id,
                "consumer_id": consumer_id,
                "proof_kind": "boundary_runtime",
                "witness_kind": "pytest_runtime",
                "runner_sha256": runner_digest,
                "consumer_path": consumer_path,
                "caller_object_id": consumer_blob,
                "start_line": 1,
                "column_start": 4,
                "end_line": 1,
                "column_end": 15,
                "match_id": match_id,
                "source_event_binding": binding,
                "expected_event": expected,
            }
        )
        specs.append(
            {
                "proof_id": f"proof-{ordinal:02d}",
                "ordinal": ordinal,
                "selector_id": selector_id,
                "witness_id": witness_id,
                "consumer_id": consumer_id,
                "proof_kind": "boundary_runtime",
                "expected_result": expected,
            }
        )

    input_binding = {
        "path": "proof_inputs/contract.json",
        "sha256": _sha256((workspace / "proof_inputs/contract.json").read_bytes()),
    }
    runtime_probe = {
        "action": "call",
        "module": "pkg.runtime_target",
        "callable": "exercise",
        "args": [7],
        "kwargs": {},
        "return_value": "ignore",
        "expected_outcome": {"status": "returned"},
    }
    runtime_consumer_path = "pkg/runtime_target.py"
    runtime_source_path = (workspace / runtime_consumer_path).resolve()
    runtime_source = runtime_source_path.read_text(encoding="utf-8")
    runtime_blob = _blob(workspace, runtime_consumer_path)
    runtime_span = {
        "line_start": 1,
        "column_start": 4,
        "line_end": 1,
        "column_end": 12,
    }
    runtime_binding = {
        "event_kind": "callable_entry",
        "phase": "residual",
        "attribution": {
            "attribution_kind": "residual_action",
            "action_sha256": _sha256(runner.canonical_json_bytes(runtime_probe)),
        },
    }
    runtime_expected_event = _expected_callable_source_event(
        source=runtime_source,
        source_path=runtime_source_path,
        consumer_path=runtime_consumer_path,
        caller_object_id=runtime_blob,
        function_name="exercise",
        span=runtime_span,
        binding=runtime_binding,
    )
    controller_cases = (
        (
            "controller-static",
            "non_cdi_static",
            "w-static",
            "consumer-static",
            "match-static",
            "pkg/compat.py",
            {
                "witness_kind": "static_ast",
                "query": {
                    "query_kind": "forbidden_syntax_absent",
                    "forbidden_names": ["ModelSpec", "resolve_generator"],
                    "forbidden_attributes": ["load_torch_bundle"],
                    "forbidden_string_literals": ["cnn"],
                },
                "expected_result": {"matches": []},
            },
        ),
        (
            "controller-absence",
            "reference_absence",
            "w-absence",
            "consumer-absence",
            "match-absence",
            "pkg/remove_me.py",
            {
                "witness_kind": "static_ast",
                "query": {"query_kind": "path_absent"},
                "expected_result": {"path_absent": True},
            },
        ),
        (
            "controller-runtime",
            "boundary_runtime",
            "w-runtime",
            "consumer-runtime",
            "match-runtime",
            runtime_consumer_path,
            {
                "witness_kind": "runtime_probe",
                "probe": runtime_probe,
                "source_event_binding": runtime_binding,
                "expected_event": runtime_expected_event,
            },
        ),
    )
    controller_rows: list[dict[str, Any]] = []
    for controller_ordinal, case in enumerate(controller_cases, start=1):
        (
            selector_id,
            proof_kind,
            witness_id,
            consumer_id,
            match_id,
            consumer_path,
            specific,
        ) = case
        controller_rows.append(
            {
                "selector_id": selector_id,
                "ordinal": controller_ordinal,
                "proof_kind": proof_kind,
                "execution_kind": (
                    "isolated_probe"
                    if specific["witness_kind"] == "runtime_probe"
                    else "static_ast"
                ),
                "runner_path": RUNNER_RELATIVE_PATH,
                "runner_sha256": runner_digest,
                "argv": [proof_kind, "--selector-id", selector_id],
                "input_bindings": [input_binding],
                "coverage_witness_ids": [witness_id],
            }
        )
        if consumer_path == runtime_consumer_path:
            span = runtime_span
        else:
            span = {
                "line_start": 1,
                "column_start": 0,
                "line_end": 1,
                "column_end": 0,
            }
        consumer_rows.append(
            _consumer_row(
                workspace,
                consumer_id=consumer_id,
                match_id=match_id,
                path=consumer_path,
                start_line=span["line_start"],
                end_line=span["line_end"],
                column_start=span["column_start"],
                column_end=span["column_end"],
                proof_kind=proof_kind,
                selector_id=selector_id,
                witness_kind=specific["witness_kind"],
                witness_id=witness_id,
            )
        )
        common = {
            "witness_id": witness_id,
            "selector_id": selector_id,
            "consumer_id": consumer_id,
            "proof_kind": proof_kind,
            "witness_kind": specific["witness_kind"],
            "runner_sha256": runner_digest,
            "consumer_path": consumer_path,
            "caller_object_id": _blob(workspace, consumer_path),
            "start_line": span["line_start"],
            "column_start": span["column_start"],
            "end_line": span["line_end"],
            "column_end": span["column_end"],
            "match_id": match_id,
        }
        if specific["witness_kind"] == "static_ast":
            common.update(
                {
                    "query": specific["query"],
                    "expected_result": specific["expected_result"],
                }
            )
            expected_result = specific["expected_result"]
        else:
            common.update(
                {
                    "probe": specific["probe"],
                    "source_event_binding": specific["source_event_binding"],
                    "expected_event": specific["expected_event"],
                }
            )
            expected_result = specific["expected_event"]
        witnesses.append(common)
        proof_ordinal = len(specs) + 1
        specs.append(
            {
                "proof_id": f"proof-{proof_ordinal:02d}",
                "ordinal": proof_ordinal,
                "selector_id": selector_id,
                "witness_id": witness_id,
                "consumer_id": consumer_id,
                "proof_kind": proof_kind,
                "expected_result": expected_result,
            }
        )

    manifest = {
        "provider_visible_pytest_selectors": provider_rows,
        "controller_only_proof_selectors": controller_rows,
        "coverage_witnesses": witnesses,
        "desired_state_proof_specs": specs,
    }
    return ContractFixture(
        workspace=workspace,
        manifest=manifest,
        consumer_rows=consumer_rows,
        baseline_tree=baseline_tree,
        provider_modules=tuple(provider_modules),
        node_ids=tuple(node_ids),
        witness_ids=tuple(row["witness_id"] for row in witnesses),
    )


def _task1j_consumer_rows(fixture: ContractFixture) -> list[dict[str, Any]]:
    rows = copy.deepcopy(fixture.consumer_rows)
    witnesses = {
        row["consumer_id"]: row for row in fixture.manifest["coverage_witnesses"]
    }
    dispositions = {
        "boundary_runtime": "route_through_boundary",
        "non_cdi_static": "compatibility_adapter",
        "reference_absence": "remove",
    }
    for row in rows:
        witness = witnesses[row["consumer_id"]]
        row.update(
            {
                "proposed_disposition": dispositions[row["required_proof_kind"]],
                "selector_id": witness["selector_id"],
                "witness_kind": witness["witness_kind"],
                "coverage_status": "required",
                "coverage_witness_ids": [witness["witness_id"]],
            }
        )
    return rows


def _task1j_open_consumer(
    rows: list[dict[str, Any]], *, consumer_id: str = "consumer-open"
) -> dict[str, Any]:
    row = copy.deepcopy(rows[0])
    row.update(
        {
            "consumer_id": consumer_id,
            "match_id": f"match-{consumer_id}",
            "coverage_status": "open",
            "coverage_witness_ids": [],
        }
    )
    return row


def test_task1j_validate_contract_accepts_explicit_open_consumer(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    consumers = _task1j_consumer_rows(contract_fixture)
    consumers.append(_task1j_open_consumer(consumers))

    contract = runner.validate_contract(
        contract_fixture.manifest,
        consumer_rows=consumers,
        expected_runner_sha256=runner.runner_sha256(),
    )

    assert {row.consumer_id for row in contract.consumers} == {
        row["consumer_id"] for row in consumers
    }


def test_task1j_validate_contract_requires_exact_required_consumer_witness_domain(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    consumers = _task1j_consumer_rows(contract_fixture)
    required = copy.deepcopy(consumers[0])
    required.update(
        {
            "consumer_id": "consumer-required-unmapped",
            "match_id": "match-required-unmapped",
            "coverage_witness_ids": ["w-required-unmapped"],
        }
    )
    consumers.append(required)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.validate_contract(
            contract_fixture.manifest,
            consumer_rows=consumers,
            expected_runner_sha256=runner.runner_sha256(),
        )

    assert caught.value.code == "proof_required_consumer_domain_mismatch"


def test_task1j_validate_contract_rejects_witness_attached_to_open_consumer(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    consumers = _task1j_consumer_rows(contract_fixture)
    consumers[0]["coverage_status"] = "open"
    consumers[0]["coverage_witness_ids"] = []

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.validate_contract(
            contract_fixture.manifest,
            consumer_rows=consumers,
            expected_runner_sha256=runner.runner_sha256(),
        )

    assert caught.value.code == "proof_witness_attached_to_open_consumer"


def test_task1j_validate_contract_allows_controller_argv_to_reuse_provider_modules(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    manifest = copy.deepcopy(contract_fixture.manifest)
    consumers = _task1j_consumer_rows(contract_fixture)
    controller = manifest["controller_only_proof_selectors"][0]
    controller.update(
        {
            "proof_kind": "boundary_runtime",
            "execution_kind": "pytest_aggregate",
            "argv": [
                str(PINNED_PYTHON),
                "-m",
                "pytest",
                "-q",
                contract_fixture.provider_modules[0],
            ],
        }
    )
    witness = next(
        row for row in manifest["coverage_witnesses"] if row["consumer_id"] == "consumer-static"
    )
    witness.pop("query")
    witness.pop("expected_result")
    witness.update(
        {
            "proof_kind": "boundary_runtime",
            "witness_kind": "controller_pytest_runtime",
            "source_event_binding": {
                "event_kind": "callable_entry",
                "phase": "collection",
                "attribution": {
                    "attribution_kind": "selector_module",
                    "pytest_module_path": contract_fixture.provider_modules[0],
                },
            },
            "expected_event": {"consumer_span_hit": True, "status": "passed"},
        }
    )
    consumer = next(row for row in consumers if row["consumer_id"] == "consumer-static")
    consumer.update(
        {
            "required_proof_kind": "boundary_runtime",
            "proposed_disposition": "route_through_boundary",
            "witness_kind": "controller_pytest_runtime",
        }
    )
    spec = next(
        row
        for row in manifest["desired_state_proof_specs"]
        if row["consumer_id"] == "consumer-static"
    )
    spec.update(
        {
            "proof_kind": "boundary_runtime",
            "expected_result": {"consumer_span_hit": True, "status": "passed"},
        }
    )

    contract = runner.validate_contract(
        manifest,
        consumer_rows=consumers,
        expected_runner_sha256=runner.runner_sha256(),
    )

    assert contract.controller_selectors[0].argv[-1] == contract_fixture.provider_modules[0]


def _bootstrap_records(
    runner: ModuleType,
    fixture: ContractFixture,
    *,
    include_controller_pytest_runtime: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = copy.deepcopy(fixture.manifest)
    consumers = copy.deepcopy(fixture.consumer_rows)
    if include_controller_pytest_runtime:
        controller = manifest["controller_only_proof_selectors"][0]
        controller.update(
            {
                "proof_kind": "boundary_runtime",
                "execution_kind": "pytest_aggregate",
                "argv": [
                    str(PINNED_PYTHON),
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    fixture.provider_modules[0],
                ],
            }
        )
        witness = next(
            row
            for row in manifest["coverage_witnesses"]
            if row["consumer_id"] == "consumer-static"
        )
        witness.pop("query")
        witness.pop("expected_result")
        witness.update(
            {
                "proof_kind": "boundary_runtime",
                "witness_kind": "controller_pytest_runtime",
                "source_event_binding": {
                    "event_kind": "callable_entry",
                    "phase": "collection",
                    "attribution": {
                        "attribution_kind": "selector_module",
                        "pytest_module_path": fixture.provider_modules[0],
                    },
                },
                "expected_event": {
                    "consumer_span_hit": True,
                    "status": "passed",
                },
            }
        )
        consumer = next(
            row for row in consumers if row["consumer_id"] == "consumer-static"
        )
        consumer.update(
            {
                "required_proof_kind": "boundary_runtime",
                "proposed_disposition": "route_through_boundary",
                "witness_kind": "controller_pytest_runtime",
            }
        )
        desired = next(
            row
            for row in manifest["desired_state_proof_specs"]
            if row["consumer_id"] == "consumer-static"
        )
        desired.update(
            {
                "proof_kind": "boundary_runtime",
                "expected_result": copy.deepcopy(witness["expected_event"]),
            }
        )
    consumers_by_id = {row["consumer_id"]: row for row in consumers}
    for row in consumers:
        row["anchor_id"] = "anchor-" + row["consumer_id"]
        row["coverage_witness_ids"] = [
            witness["witness_id"]
            for witness in manifest["coverage_witnesses"]
            if witness["consumer_id"] == row["consumer_id"]
        ]

    compact_witnesses: list[dict[str, Any]] = []
    for witness in manifest["coverage_witnesses"]:
        consumer = consumers_by_id[witness["consumer_id"]]
        spec: dict[str, Any] = {"anchor_id": consumer["anchor_id"]}
        if witness["witness_kind"] in {
            "pytest_runtime",
            "controller_pytest_runtime",
        }:
            binding = witness["source_event_binding"]
            attribution = copy.deepcopy(binding["attribution"])
            if attribution["attribution_kind"] == "pytest_node":
                attribution = {
                    "attribution_kind": "pytest_node",
                    "pytest_node_pattern": re.escape(attribution["pytest_node_id"]),
                }
            spec.update(
                {
                    "event_kind": binding["event_kind"],
                    "phase": binding["phase"],
                    "attribution": attribution,
                    "expected_event": copy.deepcopy(witness["expected_event"]),
                }
            )
        elif witness["witness_kind"] == "static_ast":
            spec.update(
                {
                    "query": copy.deepcopy(witness["query"]),
                    "expected_event": copy.deepcopy(witness["expected_result"]),
                }
            )
        else:
            binding = witness["source_event_binding"]
            spec.update(
                {
                    "event_kind": binding["event_kind"],
                    "phase": binding["phase"],
                    "attribution": copy.deepcopy(binding["attribution"]),
                    "probe": copy.deepcopy(witness["probe"]),
                    "expected_event": copy.deepcopy(witness["expected_event"]),
                }
            )
        compact_witnesses.append(
            {
                "witness_id": witness["witness_id"],
                "witness_kind": witness["witness_kind"],
                "selector_id": witness["selector_id"],
                "consumer_id": witness["consumer_id"],
                "required_proof_kind": witness["proof_kind"],
                "spec": spec,
            }
        )

    policy = _seal(
        runner,
        {
            "schema_version": "test_preedit_policy.v1",
            "selector_policy": {
                "sampling_rule": SAMPLING_RULE,
                "pytest_carrier": {
                    "executable": str(PINNED_PYTEST_CARRIER),
                    "sha256": PINNED_PYTEST_CARRIER_SHA256,
                    "version": "bubblewrap 0.9.0",
                    "tmp_isolation": "private_tmpfs",
                },
                "provider_visible_pytest_selectors": [
                    {
                        "selector_id": row["selector_id"],
                        "ordinal": row["ordinal"],
                        "pytest_module_path": row["pytest_module_path"],
                    }
                    for row in manifest["provider_visible_pytest_selectors"]
                ],
                "controller_only_proof_selectors": copy.deepcopy(
                    manifest["controller_only_proof_selectors"]
                ),
                "coverage_witness_specs": compact_witnesses,
                "desired_state_proof_specs": [
                    {
                        "proof_spec_id": row["proof_id"],
                        "witness_id": row["witness_id"],
                        "proof_kind": row["proof_kind"],
                        "expected_result": copy.deepcopy(row["expected_result"]),
                    }
                    for row in manifest["desired_state_proof_specs"]
                ],
            },
        },
    )
    census = _seal(
        runner,
        {
            "schema_version": "test_source_census.v1",
            "preedit_policy_sha256": policy["record_sha256"],
            "consumer_rows": consumers,
            "leaf_rows": [
                {
                    "path": row["pytest_module_path"],
                    "mode": row["mode"],
                    "object_id": row["projection_blob_id"],
                    "text": {
                        "is_strict_utf8": True,
                        "physical_line_count": row["physical_line_count"],
                    },
                }
                for row in fixture.manifest["provider_visible_pytest_selectors"]
            ],
        },
    )
    return policy, census


def test_task1j_bootstrap_join_accepts_empty_open_consumer_backpointer(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    policy, census = _bootstrap_records(runner, contract_fixture)
    consumers = census["consumer_rows"]
    witnesses = {
        row["consumer_id"]: row
        for row in policy["selector_policy"]["coverage_witness_specs"]
    }
    dispositions = {
        "boundary_runtime": "route_through_boundary",
        "non_cdi_static": "compatibility_adapter",
        "reference_absence": "remove",
    }
    for row in consumers:
        witness = witnesses[row["consumer_id"]]
        row.update(
            {
                "proposed_disposition": dispositions[row["required_proof_kind"]],
                "selector_id": witness["selector_id"],
                "witness_kind": witness["witness_kind"],
                "coverage_status": "required",
            }
        )
    consumers.append(_task1j_open_consumer(consumers, consumer_id="bootstrap-open"))
    selector_policy = policy["selector_policy"]
    controllers = runner._parse_controller_selectors(  # pyright: ignore[reportPrivateUsage]
        selector_policy["controller_only_proof_selectors"],
        actual_runner_sha256=runner.runner_sha256(),
    )

    contract = runner._build_bootstrap_contract(  # pyright: ignore[reportPrivateUsage]
        selector_policy=selector_policy,
        providers=selector_policy["provider_visible_pytest_selectors"],
        controllers=controllers,
        source_census=census,
        consumer_rows=consumers,
        collected_node_ids=contract_fixture.node_ids,
        runner_digest=runner.runner_sha256(),
    )

    assert {row.consumer_id for row in contract.consumers} == {
        row["consumer_id"] for row in consumers
    }


def test_task1j_bootstrap_authority_requires_frozen_sampling_rule(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    policy, census = _bootstrap_records(runner, contract_fixture)

    selector_policy, _, _, _ = runner._bootstrap_authority_inputs(  # pyright: ignore[reportPrivateUsage]
        policy,
        census,
        runner_digest=runner.runner_sha256(),
    )

    assert selector_policy["sampling_rule"] == SAMPLING_RULE

    tampered = copy.deepcopy(policy)
    tampered.pop("record_sha256")
    tampered["selector_policy"]["sampling_rule"] = "all_consumers.v0"
    tampered = _seal(runner, tampered)
    rebound_census = _rebind_census(runner, census, tampered)
    with pytest.raises(runner.BoundaryProofError) as caught:
        runner._bootstrap_authority_inputs(  # pyright: ignore[reportPrivateUsage]
            tampered,
            rebound_census,
            runner_digest=runner.runner_sha256(),
        )

    assert caught.value.code == "proof_selector_sampling_rule_invalid"


def test_task1j_bootstrap_builds_controller_pytest_runtime_witness(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    policy, census = _bootstrap_records(
        runner,
        contract_fixture,
        include_controller_pytest_runtime=True,
    )
    selector_policy, providers, controllers, consumers = (
        runner._bootstrap_authority_inputs(  # pyright: ignore[reportPrivateUsage]
            policy,
            census,
            runner_digest=runner.runner_sha256(),
        )
    )

    contract = runner._build_bootstrap_contract(  # pyright: ignore[reportPrivateUsage]
        selector_policy=selector_policy,
        providers=providers,
        controllers=controllers,
        source_census=census,
        consumer_rows=consumers,
        collected_node_ids=contract_fixture.node_ids,
        runner_digest=runner.runner_sha256(),
    )

    witness = next(
        row
        for row in contract.witnesses
        if row.witness_kind == "controller_pytest_runtime"
    )
    assert witness.source_event_binding == {
        "event_kind": "callable_entry",
        "phase": "collection",
        "attribution": {
            "attribution_kind": "selector_module",
            "pytest_module_path": contract_fixture.provider_modules[0],
        },
    }

    node_bound = copy.deepcopy(selector_policy)
    node_witness = next(
        row
        for row in node_bound["coverage_witness_specs"]
        if row["witness_kind"] == "controller_pytest_runtime"
    )
    node_witness["spec"].update(
        {
            "phase": "call",
            "attribution": {
                "attribution_kind": "pytest_node",
                "pytest_node_pattern": re.escape(contract_fixture.node_ids[0]),
            },
        }
    )
    node_contract = runner._build_bootstrap_contract(  # pyright: ignore[reportPrivateUsage]
        selector_policy=node_bound,
        providers=providers,
        controllers=controllers,
        source_census=census,
        consumer_rows=consumers,
        collected_node_ids=contract_fixture.node_ids,
        runner_digest=runner.runner_sha256(),
    )
    node_event = next(
        row
        for row in node_contract.witnesses
        if row.witness_kind == "controller_pytest_runtime"
    ).source_event_binding
    assert node_event == {
        "event_kind": "callable_entry",
        "phase": "call",
        "attribution": {
            "attribution_kind": "pytest_node",
            "pytest_node_id": contract_fixture.node_ids[0],
        },
    }

    wrong_lane = copy.deepcopy(selector_policy)
    compact = next(
        row
        for row in wrong_lane["coverage_witness_specs"]
        if row["witness_kind"] == "controller_pytest_runtime"
    )
    compact["selector_id"] = providers[0]["selector_id"]
    wrong_consumers = copy.deepcopy(consumers)
    next(
        row
        for row in wrong_consumers
        if row["consumer_id"] == compact["consumer_id"]
    )["selector_id"] = providers[0]["selector_id"]
    with pytest.raises(runner.BoundaryProofError) as caught:
        runner._build_bootstrap_contract(  # pyright: ignore[reportPrivateUsage]
            selector_policy=wrong_lane,
            providers=providers,
            controllers=controllers,
            source_census=census,
            consumer_rows=wrong_consumers,
            collected_node_ids=contract_fixture.node_ids,
            runner_digest=runner.runner_sha256(),
        )

    assert caught.value.code == "proof_selector_cross_lane_duplicate"


def _rebind_census(
    runner: ModuleType,
    census: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    rebound = copy.deepcopy(census)
    rebound.pop("record_sha256", None)
    rebound["preedit_policy_sha256"] = policy["record_sha256"]
    return _seal(runner, rebound)


def _write_test_closed_schema(path: Path, record: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": sorted(record),
                "properties": {
                    key: (
                        {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
                        if key == "record_sha256"
                        else {}
                    )
                    for key in record
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_bootstrap_baseline_matches_final_selector_capture(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    policy, census = _bootstrap_records(runner, contract_fixture)

    bootstrapped = runner.capture_bootstrap_baseline(
        policy,
        source_census=census,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=contract_fixture.baseline_tree,
        report_path=(tmp_path / "bootstrap-origin.json").resolve(),
        expected_runner_sha256=runner.runner_sha256(),
        **PYTEST_CARRIER_AUTHORITY,
    )
    final_selector_capture = runner.capture_baseline(
        contract_fixture.manifest,
        consumer_rows=contract_fixture.consumer_rows,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=contract_fixture.baseline_tree,
        report_path=(tmp_path / "final-selector-origin.json").resolve(),
        expected_runner_sha256=runner.runner_sha256(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    assert bootstrapped == final_selector_capture
    assert bootstrapped["schema_version"] == "es_f1_boundary_baseline.v1"
    assert bootstrapped["aggregate_pytest_argv"][-19:] == list(
        MANDATORY_PROVIDER_MODULES
    )


def _controller_pytest_runtime_records(
    runner: ModuleType,
    fixture: ContractFixture,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    manifest = copy.deepcopy(fixture.manifest)
    consumers = copy.deepcopy(fixture.consumer_rows)
    selector = manifest["controller_only_proof_selectors"][0]
    selector_id = "CO-PYTEST-01"
    witness_id = "w-static"
    consumer_id = "consumer-static"
    module_path = fixture.provider_modules[0]
    node_id = fixture.node_ids[0]
    consumer_path = "pkg/consumer_01.py"
    source_path = (fixture.workspace / consumer_path).resolve()
    source = source_path.read_text(encoding="utf-8")
    caller_object_id = _blob(fixture.workspace, consumer_path)
    span = {
        "line_start": 1,
        "column_start": 4,
        "line_end": 1,
        "column_end": 15,
    }
    binding = {
        "event_kind": "callable_entry",
        "phase": "call",
        "attribution": {
            "attribution_kind": "pytest_node",
            "pytest_node_id": node_id,
        },
    }
    expected_event = _expected_callable_source_event(
        source=source,
        source_path=source_path,
        consumer_path=consumer_path,
        caller_object_id=caller_object_id,
        function_name="consumer_01",
        span=span,
        binding=binding,
    )
    selector.update(
        {
            "selector_id": selector_id,
            "proof_kind": "boundary_runtime",
            "execution_kind": "pytest_aggregate",
            "argv": [
                str(PINNED_PYTHON),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                module_path,
            ],
            "input_bindings": [
                {
                    "path": module_path,
                    "sha256": _sha256((fixture.workspace / module_path).read_bytes()),
                }
            ],
            "coverage_witness_ids": [witness_id],
        }
    )
    witness = next(
        row
        for row in manifest["coverage_witnesses"]
        if row["witness_id"] == witness_id
    )
    witness.pop("query")
    witness.pop("expected_result")
    witness.update(
        {
            "selector_id": selector_id,
            "proof_kind": "boundary_runtime",
            "witness_kind": "controller_pytest_runtime",
            "consumer_path": consumer_path,
            "caller_object_id": caller_object_id,
            "start_line": span["line_start"],
            "column_start": span["column_start"],
            "end_line": span["line_end"],
            "column_end": span["column_end"],
            "source_event_binding": binding,
            "expected_event": expected_event,
        }
    )
    consumer = next(row for row in consumers if row["consumer_id"] == consumer_id)
    consumer.update(
        {
            "caller_path": consumer_path,
            "caller_object_id": caller_object_id,
            "span": span,
            "proposed_disposition": "route_through_boundary",
            "required_proof_kind": "boundary_runtime",
            "selector_id": selector_id,
            "witness_kind": "controller_pytest_runtime",
        }
    )
    desired = next(
        row
        for row in manifest["desired_state_proof_specs"]
        if row["witness_id"] == witness_id
    )
    desired.update(
        {
            "selector_id": selector_id,
            "proof_kind": "boundary_runtime",
            "expected_result": expected_event,
        }
    )
    return manifest, consumers, expected_event


def test_task3_controller_aggregate_runs_in_a_separate_process_and_emits_result(
    contract_fixture: ContractFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    manifest, consumers, expected_event = _controller_pytest_runtime_records(
        runner, contract_fixture
    )
    real_run = runner.subprocess.run
    pytest_calls: list[tuple[list[str], str, str]] = []

    def recording_run(argv: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        values = _inner_process_argv(argv)
        if len(values) >= 3 and values[1:3] == ["-m", "pytest"]:
            pytest_calls.append(
                (
                    values,
                    kwargs["env"]["ES_BOUNDARY_CONFIG"],
                    kwargs["env"]["ES_BOUNDARY_REPORT"],
                )
            )
        return real_run(argv, **kwargs)

    monkeypatch.setattr(runner.subprocess, "run", recording_run)
    baseline = runner.capture_baseline(
        manifest,
        consumer_rows=consumers,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=contract_fixture.baseline_tree,
        report_path=(tmp_path / "provider-origin.json").resolve(),
        expected_runner_sha256=runner.runner_sha256(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    assert len(pytest_calls) == 2
    provider_call, controller_call = pytest_calls
    assert provider_call[0] == baseline["aggregate_pytest_argv"]
    assert controller_call[0] == manifest["controller_only_proof_selectors"][0][
        "argv"
    ]
    assert provider_call[1:] != controller_call[1:]
    assert baseline["aggregate_pytest_argv"][-19:] == list(
        MANDATORY_PROVIDER_MODULES
    )
    assert baseline["controller_selector_results"] == [
        {
            "selector_id": "CO-PYTEST-01",
            "execution_kind": "pytest_aggregate",
            "argv": controller_call[0],
            "collected_node_ids": [contract_fixture.node_ids[0]],
            "collected_node_sha256": _sha256(
                runner.canonical_json_bytes([contract_fixture.node_ids[0]])
            ),
            "collection_total": 1,
            "outcomes": {"errors": 0, "failed": 0, "passed": 1, "skipped": 0},
            "origin_isolation": baseline["controller_selector_results"][0][
                "origin_isolation"
            ],
            "trace_sha256": _sha256(
                runner.canonical_json_bytes(
                    [
                        {
                            "witness_id": "w-static",
                            "source_event": expected_event,
                            "node_outcome": {
                                "witness_id": "w-static",
                                "pytest_node_id": contract_fixture.node_ids[0],
                                "outcome": "passed",
                            },
                        }
                    ]
                )
            ),
            "coverage_witness_ids": ["w-static"],
            "coverage_witness_node_outcomes": [
                {
                    "witness_id": "w-static",
                    "pytest_node_id": contract_fixture.node_ids[0],
                    "outcome": "passed",
                }
            ],
        }
    ]
    result = next(
        row for row in baseline["witness_results"] if row["witness_id"] == "w-static"
    )
    assert result["source_event"] == expected_event
    assert result["observation"] == expected_event
    assert result["passed"] is True


def _task3_bootstrap_controller_records(
    runner: ModuleType,
    fixture: ContractFixture,
) -> tuple[dict[str, Any], dict[str, Any], str, dict[str, Any]]:
    policy, census = _bootstrap_records(runner, fixture)
    consumer_path = "pkg/controller_observed.py"
    module_path = "tests/private/test_controller_observed.py"
    node_id = module_path + "::test_controller_observed"
    source = "def controller_observed():\n    return 'controller-only'\n"
    _write(fixture.workspace / consumer_path, source)
    _write(
        fixture.workspace / module_path,
        "from pkg.controller_observed import controller_observed\n\n"
        "def test_controller_observed():\n"
        "    assert controller_observed() == 'controller-only'\n",
    )
    expected_tree = _commit(fixture.workspace, "add controller-only aggregate")
    caller_object_id = _blob(fixture.workspace, consumer_path)
    span = {
        "line_start": 1,
        "column_start": 4,
        "line_end": 1,
        "column_end": 23,
    }
    binding = {
        "event_kind": "callable_entry",
        "phase": "call",
        "attribution": {
            "attribution_kind": "pytest_node",
            "pytest_node_id": node_id,
        },
    }
    expected_event = _expected_callable_source_event(
        source=source,
        source_path=(fixture.workspace / consumer_path).resolve(),
        consumer_path=consumer_path,
        caller_object_id=caller_object_id,
        function_name="controller_observed",
        span=span,
        binding=binding,
    )
    selector = policy["selector_policy"]["controller_only_proof_selectors"][0]
    selector.update(
        {
            "selector_id": "CO-PYTEST-01",
            "proof_kind": "boundary_runtime",
            "execution_kind": "pytest_aggregate",
            "argv": [
                str(PINNED_PYTHON),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                module_path,
            ],
            "input_bindings": [
                {
                    "path": module_path,
                    "sha256": _sha256((fixture.workspace / module_path).read_bytes()),
                }
            ],
            "coverage_witness_ids": ["w-static"],
        }
    )
    compact = next(
        row
        for row in policy["selector_policy"]["coverage_witness_specs"]
        if row["witness_id"] == "w-static"
    )
    compact.update(
        {
            "selector_id": "CO-PYTEST-01",
            "required_proof_kind": "boundary_runtime",
            "witness_kind": "controller_pytest_runtime",
            "spec": {
                "anchor_id": compact["spec"]["anchor_id"],
                "event_kind": "callable_entry",
                "phase": "call",
                "attribution": {
                    "attribution_kind": "pytest_node",
                    "pytest_node_pattern": re.escape(node_id),
                },
                "expected_event": expected_event,
            },
        }
    )
    consumer = next(
        row for row in census["consumer_rows"] if row["consumer_id"] == "consumer-static"
    )
    consumer.update(
        {
            "caller_path": consumer_path,
            "caller_object_id": caller_object_id,
            "span": span,
            "proposed_disposition": "route_through_boundary",
            "required_proof_kind": "boundary_runtime",
            "selector_id": "CO-PYTEST-01",
            "witness_kind": "controller_pytest_runtime",
        }
    )
    desired = next(
        row
        for row in policy["selector_policy"]["desired_state_proof_specs"]
        if row["witness_id"] == "w-static"
    )
    desired.update(
        {
            "proof_kind": "boundary_runtime",
            "expected_result": expected_event,
        }
    )
    policy.pop("record_sha256")
    policy = _seal(runner, policy)
    census = _rebind_census(runner, census, policy)
    return policy, census, expected_tree, expected_event


def test_task3_bootstrap_collects_controller_nodes_in_the_controller_lane(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    policy, census, expected_tree, expected_event = (
        _task3_bootstrap_controller_records(runner, contract_fixture)
    )

    baseline = runner.capture_bootstrap_baseline(
        policy,
        source_census=census,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=expected_tree,
        report_path=(tmp_path / "bootstrap-provider-origin.json").resolve(),
        expected_runner_sha256=runner.runner_sha256(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    controller = baseline["controller_selector_results"][0]
    assert controller["collected_node_ids"] == [
        "tests/private/test_controller_observed.py::test_controller_observed"
    ]
    result = next(
        row for row in baseline["witness_results"] if row["witness_id"] == "w-static"
    )
    assert result["source_event"] == expected_event


@pytest.mark.parametrize(
    ("tamper", "expected_code"),
    (
        ("skipped", "proof_witness_unobserved"),
        ("unknown_node", "proof_pytest_node_unknown"),
        ("outcome_total", "proof_pytest_report_invalid"),
        ("forbidden_origin", "proof_origin_isolation_failed"),
        ("selector_echo", "proof_pytest_report_invalid"),
    ),
)
def test_task3_controller_report_tamper_fails_closed(
    contract_fixture: ContractFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
    expected_code: str,
) -> None:
    runner = _runner()
    manifest, consumers, _ = _controller_pytest_runtime_records(
        runner, contract_fixture
    )
    real_run = runner.subprocess.run
    pytest_call_count = 0

    def tampering_run(argv: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal pytest_call_count
        values = _inner_process_argv(argv)
        is_pytest = len(values) >= 3 and values[1:3] == ["-m", "pytest"]
        completed = real_run(argv, **kwargs)
        if not is_pytest:
            return completed
        pytest_call_count += 1
        if pytest_call_count != 2:
            return completed
        report_path = Path(kwargs["env"]["ES_BOUNDARY_REPORT"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if tamper == "skipped":
            report["outcomes"] = {
                "errors": 0,
                "failed": 0,
                "passed": 0,
                "skipped": 1,
            }
            report["node_outcomes"][0]["outcome"] = "skipped"
        elif tamper == "unknown_node":
            report["pytest_node_ids"] = ["tests/private/unknown.py::test_unknown"]
            report["node_outcomes"][0]["pytest_node_id"] = (
                "tests/private/unknown.py::test_unknown"
            )
        elif tamper == "outcome_total":
            report["outcomes"]["passed"] = 2
        elif tamper == "forbidden_origin":
            report["forbidden_origin_rows"] = [
                ["forbidden.controller", "/outside/controller.py"]
            ]
        else:
            report["selectors"] = ["tests/private/substituted.py"]
        report_path.write_bytes(runner.canonical_json_bytes(report))
        return completed

    monkeypatch.setattr(runner.subprocess, "run", tampering_run)
    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.capture_baseline(
            manifest,
            consumer_rows=consumers,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            report_path=(tmp_path / f"provider-{tamper}.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("tamper", "expected_code"),
    (
        ("argv", "proof_controller_argv_invalid"),
        ("module_binding", "proof_controller_module_binding_mismatch"),
    ),
)
def test_task3_controller_policy_tamper_fails_closed(
    contract_fixture: ContractFixture,
    tmp_path: Path,
    tamper: str,
    expected_code: str,
) -> None:
    runner = _runner()
    manifest, consumers, _ = _controller_pytest_runtime_records(
        runner, contract_fixture
    )
    selector = manifest["controller_only_proof_selectors"][0]
    if tamper == "argv":
        selector["argv"].insert(4, "--maxfail=1")
    else:
        selector["input_bindings"] = [
            {
                "path": "proof_inputs/contract.json",
                "sha256": _sha256(
                    (contract_fixture.workspace / "proof_inputs/contract.json").read_bytes()
                ),
            }
        ]

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.capture_baseline(
            manifest,
            consumer_rows=consumers,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            report_path=(tmp_path / f"provider-{tamper}.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == expected_code


def test_task3_controller_unhit_witness_fails_closed(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    manifest, consumers, _ = _controller_pytest_runtime_records(
        runner, contract_fixture
    )
    consumer_path = "pkg/consumer_02.py"
    source_path = (contract_fixture.workspace / consumer_path).resolve()
    caller_object_id = _blob(contract_fixture.workspace, consumer_path)
    span = {
        "line_start": 1,
        "column_start": 4,
        "line_end": 1,
        "column_end": 15,
    }
    binding = {
        "event_kind": "callable_entry",
        "phase": "call",
        "attribution": {
            "attribution_kind": "pytest_node",
            "pytest_node_id": contract_fixture.node_ids[0],
        },
    }
    expected_event = _expected_callable_source_event(
        source=source_path.read_text(encoding="utf-8"),
        source_path=source_path,
        consumer_path=consumer_path,
        caller_object_id=caller_object_id,
        function_name="consumer_02",
        span=span,
        binding=binding,
    )
    witness = next(
        row for row in manifest["coverage_witnesses"] if row["witness_id"] == "w-static"
    )
    witness.update(
        {
            "consumer_path": consumer_path,
            "caller_object_id": caller_object_id,
            "source_event_binding": binding,
            "expected_event": expected_event,
        }
    )
    consumer = next(row for row in consumers if row["consumer_id"] == "consumer-static")
    consumer.update(
        {
            "caller_path": consumer_path,
            "caller_object_id": caller_object_id,
        }
    )
    desired = next(
        row
        for row in manifest["desired_state_proof_specs"]
        if row["witness_id"] == "w-static"
    )
    desired["expected_result"] = expected_event

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.capture_baseline(
            manifest,
            consumer_rows=consumers,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            report_path=(tmp_path / "provider-unhit.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_witness_unobserved"


def test_task3_desired_state_executes_controller_and_residual_lanes(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    manifest, consumers, expected_event = _controller_pytest_runtime_records(
        runner, contract_fixture
    )
    (contract_fixture.workspace / "pkg/remove_me.py").unlink()
    desired_tree = _commit(contract_fixture.workspace, "apply desired absence")

    rows = runner.execute_desired_state(
        manifest,
        consumer_rows=consumers,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=desired_tree,
        expected_runner_sha256=runner.runner_sha256(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    controller = next(row for row in rows if row["witness_id"] == "w-static")
    residual = next(row for row in rows if row["witness_id"] == "w-runtime")
    assert controller["source_event"] == expected_event
    assert controller["passed"] is True
    assert residual["source_event"] == residual["observation"]
    assert residual["passed"] is True


def _task4_observation_records(
    runner: ModuleType,
    fixture: ContractFixture,
    *,
    disposition: str = "route_through_boundary",
    provider_runtime: bool = False,
    controller_runtime: bool = False,
    runtime_import: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str]]:
    discovery_input = {
        "schema_version": "es_f1_preedit_discovery_input.v1",
        "authority_status": "NON_AUTHORITATIVE_INPUT",
        "projection": {"tree": fixture.baseline_tree},
        "provider_visible_pytest_selectors": (
            [
                {
                    "selector_id": f"PV-{ordinal:02d}",
                    "ordinal": ordinal,
                    "pytest_module_path": module,
                }
                for ordinal, module in enumerate(
                    MANDATORY_PROVIDER_MODULES, start=1
                )
            ]
            if provider_runtime
            else []
        ),
    }
    discovery_input_sha256 = _sha256(runner.canonical_json_bytes(discovery_input))
    candidate: dict[str, Any] = {
        "anchor_id": "RUNTIME_TARGET",
        "callee_or_dispatch_form": "pkg.runtime_target.exercise",
        "caller_object_id": _blob(fixture.workspace, "pkg/runtime_target.py"),
        "caller_path": "pkg/runtime_target.py",
        "consumer_id": "consumer-task4-open",
        "detector_id": "PYTHON_BOUNDARY_AST",
        "detector_version": "v1",
        "match_id": "match-task4-open",
        "responsibility_ids": ["CONSTRUCTION"],
        "span": {
            "line_start": 1,
            "column_start": 4,
            "line_end": 1,
            "column_end": 12,
        },
    }
    if disposition == "compatibility_adapter":
        candidate.update(
            {
                "callee_or_dispatch_form": "value",
                "span": {
                    "line_start": 2,
                    "column_start": 46,
                    "line_end": 2,
                    "column_end": 51,
                },
            }
        )
    if provider_runtime:
        candidate.update(
            {
                "callee_or_dispatch_form": "pkg.consumer_01.consumer_01",
                "caller_object_id": _blob(
                    fixture.workspace, "pkg/consumer_01.py"
                ),
                "caller_path": "pkg/consumer_01.py",
                "consumer_id": "consumer-task4-provider",
                "match_id": "match-task4-provider",
                "span": {
                    "line_start": 1,
                    "column_start": 4,
                    "line_end": 1,
                    "column_end": 15,
                },
            }
        )
    if controller_runtime:
        controller_path = runner._FROZEN_CONTROLLER_MODULE_ORDER[  # pyright: ignore[reportPrivateUsage]
            len(MANDATORY_PROVIDER_MODULES)
        ]
        candidate.update(
            {
                "callee_or_dispatch_form": "controller_boundary",
                "caller_object_id": _blob(fixture.workspace, controller_path),
                "caller_path": controller_path,
                "consumer_id": "consumer-task4-controller",
                "match_id": "match-task4-controller",
                "span": {
                    "line_start": 1,
                    "column_start": 4,
                    "line_end": 1,
                    "column_end": 23,
                },
            }
        )
    if runtime_import:
        candidate.update(
            {
                "callee_or_dispatch_form": "pkg.consumer_01.consumer_01",
                "caller_object_id": _blob(
                    fixture.workspace, "pkg/runtime_import.py"
                ),
                "caller_path": "pkg/runtime_import.py",
                "consumer_id": "consumer-task4-runtime-import",
                "match_id": "match-task4-runtime-import",
                "span": {
                    "line_start": 1,
                    "column_start": 28,
                    "line_end": 1,
                    "column_end": 39,
                },
            }
        )
    discovery_output = {
        "schema_version": "es_f1_source_census_discovery.v1",
        "authority_status": "NON_AUTHORITATIVE_DISCOVERY",
        "discovery_input_sha256": discovery_input_sha256,
        "projection": {"tree": fixture.baseline_tree},
        "candidate_set_sha256": _sha256(
            runner.canonical_json_bytes([candidate])
        ),
        "consumer_candidates": [candidate],
    }
    discovery_output_sha256 = _sha256(
        runner.canonical_json_bytes(discovery_output)
    )
    assignment = (
        {
            "proposed_disposition": "remove",
            "required_proof_kind": "reference_absence",
            "selector_id": "CO-ABS-01",
            "witness_kind": "static_ast",
            "spec_strategy": "path_absent_on_desired_tree",
        }
        if disposition == "remove"
        else {
            "proposed_disposition": "compatibility_adapter",
            "required_proof_kind": "non_cdi_static",
            "selector_id": "CO-NCDI-01",
            "witness_kind": "static_ast",
            "spec_strategy": "path_specific_forbidden_syntax_absence",
        }
        if disposition == "compatibility_adapter"
        else {
            "proposed_disposition": "route_through_boundary",
            "required_proof_kind": "boundary_runtime",
            "selector_id": "PV-01" if provider_runtime else "CO-BR-01",
            "witness_kind": "pytest_runtime" if provider_runtime else "runtime_probe",
            "spec_strategy": (
                "exact_provider_source_event"
                if provider_runtime
                else "requires_explicit_action"
            ),
        }
    )
    decision = {
        **candidate,
        "authority_status": "NEUTRAL_RECOMMENDATION_ONLY",
        "baseline_expected_to_pass": False if disposition == "remove" else None,
        "coverage_witness_ids": ["W-TASK4-OPEN"],
        **assignment,
    }
    draft = {
        "schema_version": "es_f1_policy_path_decisions_candidate.v1",
        "authority_status": "NON_AUTHORITATIVE_NEUTRAL_RECOMMENDATION",
        "source_discovery": {
            "raw_sha256": discovery_output_sha256,
            "candidate_set_sha256": discovery_output["candidate_set_sha256"],
            "consumer_candidate_count": 1,
            "projection_tree": fixture.baseline_tree,
        },
        "consumer_decisions": [decision],
    }
    draft["candidate_sha256"] = _sha256(runner.canonical_json_bytes(draft))
    draft_sha256 = _sha256(runner.canonical_json_bytes(draft))
    return (
        discovery_input,
        discovery_output,
        draft,
        {
            "discovery_input": discovery_input_sha256,
            "discovery_output": discovery_output_sha256,
            "draft_dispositions": draft_sha256,
        },
    )


def _task4_controller_fixture(
    runner: ModuleType,
    fixture: ContractFixture,
    *,
    skipped: bool = False,
    failed: bool = False,
    unrelated_nonpass: bool = False,
) -> ContractFixture:
    modules = runner._FROZEN_CONTROLLER_MODULE_ORDER  # pyright: ignore[reportPrivateUsage]
    target = modules[len(MANDATORY_PROVIDER_MODULES)]
    unrelated = modules[len(MANDATORY_PROVIDER_MODULES) + 1]
    for ordinal, module in enumerate(modules, start=1):
        if module in MANDATORY_PROVIDER_MODULES:
            continue
        if module == target:
            marker = (
                "import pytest\n\n@pytest.mark.skip(reason='controller diagnostic skip')\n"
                if skipped
                else ""
            )
            _write(
                fixture.workspace / module,
                "def controller_boundary():\n"
                "    return 'controller-observed'\n\n"
                + marker
                + "def test_controller_boundary():\n"
                + (
                    "    assert controller_boundary() == 'different'\n"
                    if failed
                    else "    assert controller_boundary() == 'controller-observed'\n"
                ),
            )
        elif module == unrelated and unrelated_nonpass:
            _write(
                fixture.workspace / module,
                "import pytest\n\n"
                "def test_unrelated_controller_failure():\n"
                "    assert False\n\n"
                "@pytest.mark.skip(reason='disclosed unrelated skip')\n"
                "def test_unrelated_controller_skip():\n"
                "    assert True\n",
            )
        else:
            _write(
                fixture.workspace / module,
                f"def test_controller_driver_{ordinal:02d}():\n"
                "    assert True\n",
            )
    tree = _commit(fixture.workspace, "add frozen controller driver modules")
    return replace(fixture, baseline_tree=tree)


def _run_task4_generated_pytest_origin_case(
    runner: ModuleType,
    fixture: ContractFixture,
    tmp_path: Path,
    *,
    test_source: str,
    report_name: str,
) -> dict[str, Any]:
    test_relative = "tests/test_forbidden_name_origin.py"
    node_id = f"{test_relative}::test_forbidden_name_origin"
    _write(fixture.workspace / test_relative, test_source)
    return runner._run_pytest_child(  # pyright: ignore[reportPrivateUsage]
        python=PINNED_PYTHON,
        workspace=fixture.workspace,
        report_path=(tmp_path / report_name).resolve(),
        forbidden_roots=(),
        selectors=(test_relative,),
        source_event_targets=(),
        project_owned_module_prefixes=("ptycho",),
        pytest_argv=(
            str(PINNED_PYTHON),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            test_relative,
        ),
        expected_node_ids=(node_id,),
        pytest_carrier=_verified_pytest_carrier(runner),
        python_target=PINNED_PYTHON_TARGET,
    )


def test_task0_bootstrap_baselines_normalize_provider_and_controller_temp_origins(
    contract_fixture: ContractFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    policy, census, expected_tree, _ = _task3_bootstrap_controller_records(
        runner, contract_fixture
    )
    real_run = runner.subprocess.run
    pytest_call_count = 0

    def injecting_run(argv: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal pytest_call_count
        completed = real_run(argv, **kwargs)
        values = _inner_process_argv(argv)
        if len(values) < 3 or values[1:3] != ["-m", "pytest"]:
            return completed
        pytest_call_count += 1
        autograph_token = f"{pytest_call_count:08d}"
        torch_token = f"{pytest_call_count + 100:08d}"
        report_path = Path(kwargs["env"]["ES_BOUNDARY_REPORT"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["module_origin_rows"].extend(
            [
                [
                    f"__autograph_generated_file{autograph_token}",
                    f"/tmp/__autograph_generated_file{autograph_token}.py",
                ],
                [
                    "_remote_module_non_scriptable",
                    f"/tmp/tmp{torch_token}/_remote_module_non_scriptable.py",
                ],
            ]
        )
        report_path.write_bytes(runner.canonical_json_bytes(report))
        return completed

    monkeypatch.setattr(runner.subprocess, "run", injecting_run)
    captures = [
        runner.capture_bootstrap_baseline(
            policy,
            source_census=census,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=expected_tree,
            report_path=(tmp_path / f"bootstrap-provider-{ordinal}.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )
        for ordinal in (1, 2)
    ]

    assert captures[0] == captures[1]
    first = captures[0]
    provider_origin = first["origin_isolation"]
    controller_origin = first["controller_selector_results"][0]["origin_isolation"]
    assert provider_origin is not controller_origin
    for origin in (provider_origin, controller_origin):
        rows = origin["module_origin_rows"]
        assert list(NORMALIZED_AUTOGRAPH_ROWS[0]) in rows
        assert list(NORMALIZED_TORCH_REMOTE_ROW) in rows
        assert [
            "es_boundary_probe_plugin",
            "<runtime-owned:es-boundary-probe-plugin>",
        ] in rows
        assert [
            "es_exact_source_event_observer",
            "<runtime-owned:es-exact-source-event-observer>",
        ] in rows
    assert captures[0]["origin_isolation"]["report_sha256"] == captures[1][
        "origin_isolation"
    ]["report_sha256"]
    assert captures[0]["controller_selector_results"][0]["origin_isolation"][
        "report_sha256"
    ] == captures[1]["controller_selector_results"][0]["origin_isolation"][
        "report_sha256"
    ]

    drifted = copy.deepcopy(first)
    drifted["origin_isolation"]["projected_origin_rows"].append(
        ["project.drift", "/workspace/project/drift.py"]
    )
    assert runner.canonical_json_bytes(drifted) != runner.canonical_json_bytes(first)


def test_task4_generated_pytest_allows_forbidden_name_projected_from_workspace(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    _write(contract_fixture.workspace / "ptycho/__init__.py", "")
    projected = contract_fixture.workspace / "ptycho/evaluation.py"
    _write(projected, "VALUE = 'projected'\n")

    report = _run_task4_generated_pytest_origin_case(
        runner,
        contract_fixture,
        tmp_path,
        test_source=(
            "import ptycho.evaluation\n\n"
            "def test_forbidden_name_origin():\n"
            "    assert ptycho.evaluation.VALUE == 'projected'\n"
        ),
        report_name="projected-forbidden-name.json",
    )

    assert report["origin"]["loaded_forbidden_modules"] == []
    assert ["ptycho.evaluation", str(projected.resolve())] in report["origin"][
        "projected_origin_rows"
    ]


@pytest.mark.parametrize("origin_kind", ("missing", "outside"))
def test_task4_generated_pytest_rejects_forbidden_name_without_projected_origin(
    contract_fixture: ContractFixture,
    tmp_path: Path,
    origin_kind: str,
) -> None:
    runner = _runner()
    origin_assignment = (
        ""
        if origin_kind == "missing"
        else "    module.__file__ = '/outside/ptycho/evaluation.py'\n"
    )
    test_source = (
        "import sys\n"
        "import types\n\n"
        "def test_forbidden_name_origin():\n"
        "    module = types.ModuleType('ptycho.evaluation')\n"
        f"{origin_assignment}"
        "    sys.modules['ptycho.evaluation'] = module\n"
        "    assert module.__name__ == 'ptycho.evaluation'\n"
    )

    with pytest.raises(runner.BoundaryProofError) as caught:
        _run_task4_generated_pytest_origin_case(
            runner,
            contract_fixture,
            tmp_path,
            test_source=test_source,
            report_name=f"{origin_kind}-forbidden-name.json",
        )

    assert caught.value.code == "proof_origin_isolation_failed"
    assert caught.value.detail["loaded"] == ("ptycho.evaluation",)


def test_task4_controller_candidate_discloses_unrelated_nonpass_nodes(
    contract_fixture: ContractFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    fixture = _task4_controller_fixture(
        runner, contract_fixture, unrelated_nonpass=True
    )
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, fixture, controller_runtime=True
    )
    real_child = runner._run_pytest_child  # pyright: ignore[reportPrivateUsage]
    reports: list[dict[str, Any]] = []

    def recording_child(**kwargs: Any) -> dict[str, Any]:
        report = real_child(**kwargs)
        reports.append(copy.deepcopy(report))
        return report

    monkeypatch.setattr(runner, "_run_pytest_child", recording_child)
    result = runner.observe_candidates(
        discovery_input,
        discovery_output=discovery_output,
        draft_dispositions=draft,
        expected_discovery_input_sha256=digests["discovery_input"],
        expected_discovery_output_sha256=digests["discovery_output"],
        expected_draft_dispositions_sha256=digests["draft_dispositions"],
        python=PINNED_PYTHON,
        workspace=fixture.workspace,
        expected_tree=fixture.baseline_tree,
        expected_runner_sha256=runner.runner_sha256(),
        forbidden_roots=(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    assert result["counts"] == {
        "ambiguous": 0,
        "observable": 1,
        "open": 0,
        "total": 1,
    }
    assert len(reports) == 3
    for report in reports[1:]:
        assert report["outcomes"]["failed"] == 1
        assert report["outcomes"]["skipped"] == 1
        selected = result["candidate_rows"][0]["executable_choices"][0]["spec"][
            "attribution"
        ]["pytest_node_id"]
        assert next(
            row for row in report["node_outcomes"]
            if row["pytest_node_id"] == selected
        ) == {"pytest_node_id": selected, "outcome": "passed"}


@pytest.mark.parametrize("tamper", ("missing", "reordered"))
def test_task4_controller_candidate_rejects_node_outcome_row_tamper(
    contract_fixture: ContractFixture,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    runner = _runner()
    fixture = _task4_controller_fixture(runner, contract_fixture)
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, fixture, controller_runtime=True
    )
    real_run = runner.subprocess.run
    pytest_calls = 0

    def tampering_run(argv: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal pytest_calls
        completed = real_run(argv, **kwargs)
        values = _inner_process_argv(argv)
        if len(values) < 3 or values[1:3] != ["-m", "pytest"]:
            return completed
        pytest_calls += 1
        if pytest_calls != 2:
            return completed
        report_path = Path(kwargs["env"]["ES_BOUNDARY_REPORT"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if tamper == "missing":
            report["node_outcomes"].pop()
        else:
            report["node_outcomes"].reverse()
        report_path.write_bytes(runner.canonical_json_bytes(report))
        return completed

    monkeypatch.setattr(runner.subprocess, "run", tampering_run)
    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.observe_candidates(
            discovery_input,
            discovery_output=discovery_output,
            draft_dispositions=draft,
            expected_discovery_input_sha256=digests["discovery_input"],
            expected_discovery_output_sha256=digests["discovery_output"],
            expected_draft_dispositions_sha256=digests["draft_dispositions"],
            python=PINNED_PYTHON,
            workspace=fixture.workspace,
            expected_tree=fixture.baseline_tree,
            expected_runner_sha256=runner.runner_sha256(),
            forbidden_roots=(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_pytest_report_invalid"


def test_task4_observe_candidates_discovers_controller_event_in_separate_lane(
    contract_fixture: ContractFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    fixture = _task4_controller_fixture(runner, contract_fixture)
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, fixture, controller_runtime=True
    )
    real_run = runner.subprocess.run
    pytest_calls: list[tuple[list[str], str]] = []

    def recording_run(argv: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        values = _inner_process_argv(argv)
        if len(values) >= 3 and values[1:3] == ["-m", "pytest"]:
            pytest_calls.append((values, kwargs["env"]["ES_BOUNDARY_REPORT"]))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(runner.subprocess, "run", recording_run)
    result = runner.observe_candidates(
        discovery_input,
        discovery_output=discovery_output,
        draft_dispositions=draft,
        expected_discovery_input_sha256=digests["discovery_input"],
        expected_discovery_output_sha256=digests["discovery_output"],
        expected_draft_dispositions_sha256=digests["draft_dispositions"],
        python=PINNED_PYTHON,
        workspace=fixture.workspace,
        expected_tree=fixture.baseline_tree,
        expected_runner_sha256=runner.runner_sha256(),
        forbidden_roots=(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    modules = tuple(runner._FROZEN_CONTROLLER_MODULE_ORDER)  # pyright: ignore[reportPrivateUsage]
    expected_argv = [
        str(PINNED_PYTHON),
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        *modules,
    ]
    assert len(pytest_calls) == 3
    assert pytest_calls[0][0] == [
        *expected_argv[:3],
        "--collect-only",
        *expected_argv[3:],
    ]
    assert pytest_calls[1][0] == expected_argv
    assert pytest_calls[2][0] == expected_argv
    assert len({report_path for _, report_path in pytest_calls}) == 3
    assert not any(
        call == [
            str(PINNED_PYTHON),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            *MANDATORY_PROVIDER_MODULES,
        ]
        for call, _ in pytest_calls
    )

    assert result["counts"] == {
        "ambiguous": 0,
        "observable": 1,
        "open": 0,
        "total": 1,
    }
    row = result["candidate_rows"][0]
    assert row["reason_code"] == "controller_exact_event_replayed"
    assert row["executable_choices"] == [
        {
            "selector_id": "CO-PYTEST-01",
            "proof_kind": "boundary_runtime",
            "witness_kind": "controller_pytest_runtime",
            "spec": {
                "event_kind": "callable_entry",
                "phase": "call",
                "attribution": {
                    "attribution_kind": "pytest_node",
                    "pytest_node_id": (
                        modules[len(MANDATORY_PROVIDER_MODULES)]
                        + "::test_controller_boundary"
                    ),
                },
                "expected_event": row["executable_choices"][0]["spec"][
                    "expected_event"
                ],
            },
        }
    ]
    event = row["executable_choices"][0]["spec"]["expected_event"]
    assert event["consumer_path"] == modules[len(MANDATORY_PROVIDER_MODULES)]
    assert event["span"] == row["span"]
    assert result["input_bindings"]["controller_module_input_bindings"] == [
        {
            "path": module,
            "projection_blob_id": _blob(fixture.workspace, module),
            "sha256": _sha256((fixture.workspace / module).read_bytes()),
        }
        for module in modules
    ]
    selector_candidate = result["input_bindings"][
        "controller_pytest_selector_candidate"
    ]
    assert selector_candidate == {
        "selector_id": "CO-PYTEST-01",
        "ordinal": 1,
        "proof_kind": "boundary_runtime",
        "execution_kind": "pytest_aggregate",
        "runner_path": RUNNER_RELATIVE_PATH,
        "runner_sha256": runner.runner_sha256(),
        "argv": expected_argv,
        "input_bindings": [
            {
                "path": module,
                "sha256": _sha256((fixture.workspace / module).read_bytes()),
            }
            for module in modules
        ],
        "projection_bindings": [
            {
                "path": module,
                "projection_blob_id": _blob(fixture.workspace, module),
            }
            for module in modules
        ],
    }
    assert "coverage_witness_ids" not in selector_candidate


def test_task4_controller_candidate_replay_mismatch_fails_closed(
    contract_fixture: ContractFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    fixture = _task4_controller_fixture(runner, contract_fixture)
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, fixture, controller_runtime=True
    )
    real_child = runner._run_pytest_child  # pyright: ignore[reportPrivateUsage]
    child_calls = 0

    def tampering_child(**kwargs: Any) -> dict[str, Any]:
        nonlocal child_calls
        child_calls += 1
        report = real_child(**kwargs)
        if child_calls == 3:
            report = copy.deepcopy(report)
            event = next(iter(report["source_events"].values()))
            event["hit_count"] += 1
        return report

    monkeypatch.setattr(runner, "_run_pytest_child", tampering_child)
    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.observe_candidates(
            discovery_input,
            discovery_output=discovery_output,
            draft_dispositions=draft,
            expected_discovery_input_sha256=digests["discovery_input"],
            expected_discovery_output_sha256=digests["discovery_output"],
            expected_draft_dispositions_sha256=digests["draft_dispositions"],
            python=PINNED_PYTHON,
            workspace=fixture.workspace,
            expected_tree=fixture.baseline_tree,
            expected_runner_sha256=runner.runner_sha256(),
            forbidden_roots=(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert child_calls == 3
    assert caught.value.code == "proof_candidate_event_replay_mismatch"


def test_task4_controller_candidate_leaves_skipped_selected_driver_open(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    fixture = _task4_controller_fixture(runner, contract_fixture, skipped=True)
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, fixture, controller_runtime=True
    )

    result = runner.observe_candidates(
        discovery_input,
        discovery_output=discovery_output,
        draft_dispositions=draft,
        expected_discovery_input_sha256=digests["discovery_input"],
        expected_discovery_output_sha256=digests["discovery_output"],
        expected_draft_dispositions_sha256=digests["draft_dispositions"],
        python=PINNED_PYTHON,
        workspace=fixture.workspace,
        expected_tree=fixture.baseline_tree,
        expected_runner_sha256=runner.runner_sha256(),
        forbidden_roots=(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    assert result["counts"] == {
        "ambiguous": 0,
        "observable": 0,
        "open": 1,
        "total": 1,
    }
    assert result["candidate_rows"][0]["executable_choices"] == []


def test_task4_controller_candidate_leaves_failed_selected_driver_open(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    fixture = _task4_controller_fixture(runner, contract_fixture, failed=True)
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, fixture, controller_runtime=True
    )

    result = runner.observe_candidates(
        discovery_input,
        discovery_output=discovery_output,
        draft_dispositions=draft,
        expected_discovery_input_sha256=digests["discovery_input"],
        expected_discovery_output_sha256=digests["discovery_output"],
        expected_draft_dispositions_sha256=digests["draft_dispositions"],
        python=PINNED_PYTHON,
        workspace=fixture.workspace,
        expected_tree=fixture.baseline_tree,
        expected_runner_sha256=runner.runner_sha256(),
        forbidden_roots=(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    assert result["counts"] == {
        "ambiguous": 0,
        "observable": 0,
        "open": 1,
        "total": 1,
    }
    assert result["candidate_rows"][0]["executable_choices"] == []


def test_task4_observe_candidates_discovers_and_replays_exact_provider_event(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, contract_fixture, provider_runtime=True
    )

    result = runner.observe_candidates(
        discovery_input,
        discovery_output=discovery_output,
        draft_dispositions=draft,
        expected_discovery_input_sha256=digests["discovery_input"],
        expected_discovery_output_sha256=digests["discovery_output"],
        expected_draft_dispositions_sha256=digests["draft_dispositions"],
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=contract_fixture.baseline_tree,
        expected_runner_sha256=runner.runner_sha256(),
        forbidden_roots=(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    assert result["counts"] == {
        "ambiguous": 0,
        "observable": 1,
        "open": 0,
        "total": 1,
    }
    row = result["candidate_rows"][0]
    assert row["consumer_id"] == "consumer-task4-provider"
    assert row["observation_status"] == "observable"
    assert row["reason_code"] == "provider_exact_event_replayed"
    assert len(row["executable_choices"]) == 1
    choice = row["executable_choices"][0]
    assert choice["selector_id"] == "PV-01"
    assert choice["proof_kind"] == "boundary_runtime"
    assert choice["witness_kind"] == "pytest_runtime"
    spec = choice["spec"]
    assert spec["event_kind"] == "callable_entry"
    assert spec["phase"] == "call"
    assert spec["attribution"] == {
        "attribution_kind": "pytest_node",
        "pytest_node_id": (
            "tests/torch/test_generator_registry.py::test_consumer_01"
        ),
    }
    assert spec["expected_event"]["consumer_path"] == "pkg/consumer_01.py"
    candidate_span = {
        "line_start": 1,
        "column_start": 4,
        "line_end": 1,
        "column_end": 15,
    }
    assert spec["expected_event"]["span"] == candidate_span
    assert spec["expected_event"]["callable_entry"]["definition_span"] == {
        "line_start": 1,
        "column_start": 0,
        "line_end": 2,
        "column_end": 24,
    }
    assert row["span"] == candidate_span


def test_task4_observe_candidates_discovers_and_replays_import_action(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, contract_fixture, runtime_import=True
    )

    result = runner.observe_candidates(
        discovery_input,
        discovery_output=discovery_output,
        draft_dispositions=draft,
        expected_discovery_input_sha256=digests["discovery_input"],
        expected_discovery_output_sha256=digests["discovery_output"],
        expected_draft_dispositions_sha256=digests["draft_dispositions"],
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=contract_fixture.baseline_tree,
        expected_runner_sha256=runner.runner_sha256(),
        forbidden_roots=(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    row = result["candidate_rows"][0]
    assert row["observation_status"] == "observable"
    assert row["reason_code"] == "residual_exact_event_replayed"
    assert row["executable_choices"] == [
        {
            "selector_id": "CO-BR-01",
            "proof_kind": "boundary_runtime",
            "witness_kind": "runtime_probe",
            "spec": {
                "event_kind": "import_alias_opcode",
                "phase": "residual",
                "attribution": {
                    "attribution_kind": "residual_action",
                    "action_sha256": row["executable_choices"][0]["spec"][
                        "attribution"
                    ]["action_sha256"],
                },
                "probe": {
                    "action": "import_module",
                    "module": "pkg.runtime_import",
                    "expected_outcome": {"status": "returned"},
                },
                "expected_event": row["executable_choices"][0]["spec"][
                    "expected_event"
                ],
            },
        }
    ]
    expected_event = row["executable_choices"][0]["spec"]["expected_event"]
    assert expected_event["consumer_path"] == "pkg/runtime_import.py"
    assert expected_event["event_kind"] == "import_alias_opcode"
    assert expected_event["import_alias_opcode"]["name"] == "consumer_01"


@pytest.mark.parametrize(
    "failure_code",
    ("proof_origin_isolation_failed", "proof_runtime_probe_failed"),
)
def test_task4_residual_diagnostic_does_not_hide_integrity_failure(
    contract_fixture: ContractFixture,
    monkeypatch: pytest.MonkeyPatch,
    failure_code: str,
) -> None:
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, contract_fixture, runtime_import=True
    )

    def fail_runtime(*_args: object, **_kwargs: object) -> tuple[object, str]:
        raise runner.BoundaryProofError(failure_code, "injected")

    monkeypatch.setattr(runner, "_runtime_observation", fail_runtime)
    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.observe_candidates(
            discovery_input,
            discovery_output=discovery_output,
            draft_dispositions=draft,
            expected_discovery_input_sha256=digests["discovery_input"],
            expected_discovery_output_sha256=digests["discovery_output"],
            expected_draft_dispositions_sha256=digests["draft_dispositions"],
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            expected_runner_sha256=runner.runner_sha256(),
            forbidden_roots=(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == failure_code


def test_task4_provider_diagnostic_rejects_skipped_node(
    contract_fixture: ContractFixture,
) -> None:
    test_module = contract_fixture.workspace / MANDATORY_PROVIDER_MODULES[0]
    with test_module.open("a", encoding="utf-8") as stream:
        stream.write(
            "\nimport pytest\n\n"
            "@pytest.mark.skip(reason='diagnostic skip')\n"
            "def test_skipped_provider_node():\n"
            "    raise AssertionError('must not execute')\n"
        )
    tree = _commit(contract_fixture.workspace, "add skipped provider node")
    fixture = replace(contract_fixture, baseline_tree=tree)
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, fixture, provider_runtime=True
    )

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.observe_candidates(
            discovery_input,
            discovery_output=discovery_output,
            draft_dispositions=draft,
            expected_discovery_input_sha256=digests["discovery_input"],
            expected_discovery_output_sha256=digests["discovery_output"],
            expected_draft_dispositions_sha256=digests["draft_dispositions"],
            python=PINNED_PYTHON,
            workspace=fixture.workspace,
            expected_tree=tree,
            expected_runner_sha256=runner.runner_sha256(),
            forbidden_roots=(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_pytest_failed"


def test_task4_replay_comparison_ignores_ephemeral_module_inventory_only() -> None:
    runner = _runner()
    first = {
        "raw_sha256": "sha256:" + "1" * 64,
        "argv": ["python", "-m", "pytest"],
        "source_events": {"witness": {"hit_count": 1}},
        "origin": {
            "report_sha256": "sha256:" + "2" * 64,
            "project_owned_module_prefixes": ["project"],
            "module_origin_rows": [
                ["__generated_first", "/tmp/__generated_first.py"]
            ],
            "projected_origin_rows": [["project.module", "/workspace/project.py"]],
            "forbidden_origin_rows": [],
            "outside_project_origin_rows": [],
        },
    }
    second = copy.deepcopy(first)
    second["raw_sha256"] = "sha256:" + "3" * 64
    second["source_events"] = {"other-witness": {"hit_count": 1}}
    second["origin"]["report_sha256"] = "sha256:" + "4" * 64
    second["origin"]["module_origin_rows"] = [
        ["__generated_second", "/tmp/__generated_second.py"]
    ]

    assert runner._pytest_reports_match_except_events(first, second)  # pyright: ignore[reportPrivateUsage]
    assert first["origin"]["module_origin_rows"] == [
        ["__generated_first", "/tmp/__generated_first.py"]
    ]

    second["origin"]["projected_origin_rows"] = [
        ["project.module", "/outside/project.py"]
    ]
    assert not runner._pytest_reports_match_except_events(first, second)  # pyright: ignore[reportPrivateUsage]


def test_task4_observe_candidates_retains_unresolved_row_as_open_without_payload(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, contract_fixture
    )

    result = runner.observe_candidates(
        discovery_input,
        discovery_output=discovery_output,
        draft_dispositions=draft,
        expected_discovery_input_sha256=digests["discovery_input"],
        expected_discovery_output_sha256=digests["discovery_output"],
        expected_draft_dispositions_sha256=digests["draft_dispositions"],
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=contract_fixture.baseline_tree,
        expected_runner_sha256=runner.runner_sha256(),
        forbidden_roots=(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    assert set(result) == {
        "schema_version",
        "authority_status",
        "input_bindings",
        "counts",
        "candidate_rows",
    }
    assert result["schema_version"] == "es_f1_witness_observation_candidates.v1"
    assert result["authority_status"] == "NON_AUTHORITATIVE"
    assert "record_sha256" not in result
    assert "adoption" not in result
    assert result["counts"] == {
        "ambiguous": 0,
        "observable": 0,
        "open": 1,
        "total": 1,
    }
    row = result["candidate_rows"][0]
    assert row["consumer_id"] == "consumer-task4-open"
    assert row["observation_status"] == "open"
    assert row["reason_code"] == "explicit_runtime_action_missing"
    assert row["executable_choices"] == []
    assert not {"spec", "event", "probe", "query"}.intersection(row)
    assert result == runner.observe_candidates(
        discovery_input,
        discovery_output=copy.deepcopy(discovery_output),
        draft_dispositions=copy.deepcopy(draft),
        expected_discovery_input_sha256=digests["discovery_input"],
        expected_discovery_output_sha256=digests["discovery_output"],
        expected_draft_dispositions_sha256=digests["draft_dispositions"],
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=contract_fixture.baseline_tree,
        expected_runner_sha256=runner.runner_sha256(),
        forbidden_roots=(),
        **PYTEST_CARRIER_AUTHORITY,
    )


def test_task4_observe_candidates_emits_closed_removal_choice(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, contract_fixture, disposition="remove"
    )

    result = runner.observe_candidates(
        discovery_input,
        discovery_output=discovery_output,
        draft_dispositions=draft,
        expected_discovery_input_sha256=digests["discovery_input"],
        expected_discovery_output_sha256=digests["discovery_output"],
        expected_draft_dispositions_sha256=digests["draft_dispositions"],
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=contract_fixture.baseline_tree,
        expected_runner_sha256=runner.runner_sha256(),
        forbidden_roots=(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    assert result["counts"] == {
        "ambiguous": 0,
        "observable": 1,
        "open": 0,
        "total": 1,
    }
    assert result["candidate_rows"][0]["executable_choices"] == [
        {
            "selector_id": "CO-ABS-01",
            "proof_kind": "reference_absence",
            "witness_kind": "static_ast",
            "spec": {
                "query": {"query_kind": "path_absent"},
                "expected_event": {"path_absent": True},
            },
        }
    ]


def test_task4_observe_candidates_derives_nonvacuous_static_choice(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, contract_fixture, disposition="compatibility_adapter"
    )

    result = runner.observe_candidates(
        discovery_input,
        discovery_output=discovery_output,
        draft_dispositions=draft,
        expected_discovery_input_sha256=digests["discovery_input"],
        expected_discovery_output_sha256=digests["discovery_output"],
        expected_draft_dispositions_sha256=digests["draft_dispositions"],
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=contract_fixture.baseline_tree,
        expected_runner_sha256=runner.runner_sha256(),
        forbidden_roots=(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    row = result["candidate_rows"][0]
    assert row["observation_status"] == "observable"
    assert row["executable_choices"] == [
        {
            "selector_id": "CO-NCDI-01",
            "proof_kind": "non_cdi_static",
            "witness_kind": "static_ast",
            "spec": {
                "query": {
                    "query_kind": "forbidden_syntax_absent",
                    "forbidden_names": ["value"],
                    "forbidden_attributes": [],
                    "forbidden_string_literals": [],
                },
                "expected_event": {"matches": []},
            },
        }
    ]


def test_task4_observe_candidates_allows_ignored_nonleaf_runtime_artifact(
    contract_fixture: ContractFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ignored_relative = "runtime-artifacts/result.bin"
    _write(contract_fixture.workspace / ".gitignore", "runtime-artifacts/\n")
    tree = _commit(contract_fixture.workspace, "ignore runtime artifacts")
    fixture = replace(contract_fixture, baseline_tree=tree)
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, fixture, disposition="compatibility_adapter"
    )
    real_static_choice = runner._static_candidate_choice  # pyright: ignore[reportPrivateUsage]

    def create_ignored_artifact(*args: object, **kwargs: object) -> object:
        artifact = fixture.workspace / ignored_relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"runtime output\n")
        return real_static_choice(*args, **kwargs)

    monkeypatch.setattr(runner, "_static_candidate_choice", create_ignored_artifact)
    result = runner.observe_candidates(
        discovery_input,
        discovery_output=discovery_output,
        draft_dispositions=draft,
        expected_discovery_input_sha256=digests["discovery_input"],
        expected_discovery_output_sha256=digests["discovery_output"],
        expected_draft_dispositions_sha256=digests["draft_dispositions"],
        python=PINNED_PYTHON,
        workspace=fixture.workspace,
        expected_tree=tree,
        expected_runner_sha256=runner.runner_sha256(),
        forbidden_roots=(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    assert result["candidate_rows"][0]["observation_status"] == "observable"
    assert (fixture.workspace / ignored_relative).read_bytes() == b"runtime output\n"
    assert _git(fixture.workspace, "status", "--porcelain=v1") == ""


def test_task4_observe_candidates_rejects_persistent_unignored_addition(
    contract_fixture: ContractFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, contract_fixture, disposition="compatibility_adapter"
    )
    real_static_choice = runner._static_candidate_choice  # pyright: ignore[reportPrivateUsage]

    def create_unignored_source(*args: object, **kwargs: object) -> object:
        _write(contract_fixture.workspace / "pkg/new_source.py", "VALUE = 1\n")
        return real_static_choice(*args, **kwargs)

    monkeypatch.setattr(runner, "_static_candidate_choice", create_unignored_source)
    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.observe_candidates(
            discovery_input,
            discovery_output=discovery_output,
            draft_dispositions=draft,
            expected_discovery_input_sha256=digests["discovery_input"],
            expected_discovery_output_sha256=digests["discovery_output"],
            expected_draft_dispositions_sha256=digests["draft_dispositions"],
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            expected_runner_sha256=runner.runner_sha256(),
            forbidden_roots=(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_tree_dirty"


def test_task4_observe_candidates_rejects_frozen_leaf_write_then_restore(
    contract_fixture: ContractFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, contract_fixture, disposition="compatibility_adapter"
    )
    real_static_choice = runner._static_candidate_choice  # pyright: ignore[reportPrivateUsage]
    target = contract_fixture.workspace / "pkg/compat.py"

    def touch_and_restore_source(*args: object, **kwargs: object) -> object:
        original = target.read_bytes()
        identity = target.stat()
        target.write_bytes(original + b"# transient write\n")
        target.write_bytes(original)
        os.utime(
            target,
            ns=(identity.st_atime_ns, identity.st_mtime_ns),
        )
        return real_static_choice(*args, **kwargs)

    monkeypatch.setattr(runner, "_static_candidate_choice", touch_and_restore_source)
    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.observe_candidates(
            discovery_input,
            discovery_output=discovery_output,
            draft_dispositions=draft,
            expected_discovery_input_sha256=digests["discovery_input"],
            expected_discovery_output_sha256=digests["discovery_output"],
            expected_draft_dispositions_sha256=digests["draft_dispositions"],
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            expected_runner_sha256=runner.runner_sha256(),
            forbidden_roots=(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert _git(contract_fixture.workspace, "status", "--porcelain=v1") == ""
    assert caught.value.code == "proof_tree_dirty"


def test_task4_source_identity_guard_validates_in_finally_after_observation_failure(
    contract_fixture: ContractFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, contract_fixture, disposition="compatibility_adapter"
    )

    def mutate_then_fail(*_args: object, **_kwargs: object) -> NoReturn:
        _write(contract_fixture.workspace / "pkg/new_source.py", "VALUE = 1\n")
        raise runner.BoundaryProofError("proof_injected_observation_failure")

    monkeypatch.setattr(runner, "_static_candidate_choice", mutate_then_fail)
    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.observe_candidates(
            discovery_input,
            discovery_output=discovery_output,
            draft_dispositions=draft,
            expected_discovery_input_sha256=digests["discovery_input"],
            expected_discovery_output_sha256=digests["discovery_output"],
            expected_draft_dispositions_sha256=digests["draft_dispositions"],
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            expected_runner_sha256=runner.runner_sha256(),
            forbidden_roots=(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_tree_dirty"
    assert isinstance(caught.value.__context__, runner.BoundaryProofError)
    assert caught.value.__context__.code == "proof_injected_observation_failure"


def test_task4_observe_candidates_rejects_stale_input_binding(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, contract_fixture
    )

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.observe_candidates(
            discovery_input,
            discovery_output=discovery_output,
            draft_dispositions=draft,
            expected_discovery_input_sha256="sha256:" + "0" * 64,
            expected_discovery_output_sha256=digests["discovery_output"],
            expected_draft_dispositions_sha256=digests["draft_dispositions"],
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            expected_runner_sha256=runner.runner_sha256(),
            forbidden_roots=(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_candidate_input_binding_mismatch"


def test_task4_observe_candidates_rejects_frozen_controller_module_substitution(
    contract_fixture: ContractFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, contract_fixture
    )
    monkeypatch.setattr(
        runner,
        "_FROZEN_CONTROLLER_MODULE_ORDER",
        ("tests/private/substituted.py",),
        raising=False,
    )

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.observe_candidates(
            discovery_input,
            discovery_output=discovery_output,
            draft_dispositions=draft,
            expected_discovery_input_sha256=digests["discovery_input"],
            expected_discovery_output_sha256=digests["discovery_output"],
            expected_draft_dispositions_sha256=digests["draft_dispositions"],
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            expected_runner_sha256=runner.runner_sha256(),
            forbidden_roots=(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_controller_module_order_mismatch"


def test_task4_cli_exposes_closed_observe_candidates_arguments(tmp_path: Path) -> None:
    runner = _runner()
    args = runner._parser().parse_args(  # pyright: ignore[reportPrivateUsage]
        [
            "observe-candidates",
            "--discovery-input",
            str(tmp_path / "input.json"),
            "--expected-discovery-input-sha256",
            "sha256:" + "1" * 64,
            "--discovery-output",
            str(tmp_path / "discovery.json"),
            "--expected-discovery-output-sha256",
            "sha256:" + "2" * 64,
            "--draft-dispositions",
            str(tmp_path / "draft.json"),
            "--expected-draft-dispositions-sha256",
            "sha256:" + "3" * 64,
            "--python",
            str(PINNED_PYTHON),
            "--workspace",
            str(tmp_path / "workspace"),
            "--expected-tree",
            "a" * 40,
            "--expected-runner-sha256",
            "sha256:" + "4" * 64,
            "--pytest-carrier",
            str(PINNED_PYTEST_CARRIER),
            "--expected-pytest-carrier-sha256",
            PINNED_PYTEST_CARRIER_SHA256,
            "--forbidden-root",
            str(tmp_path / "forbidden"),
            "--report-path",
            str(tmp_path / "report.json"),
            "--output",
            str(tmp_path / "output.json"),
        ]
    )

    assert args.command == "observe-candidates"
    assert args.forbidden_root == [tmp_path / "forbidden"]
    assert args.pytest_carrier == PINNED_PYTEST_CARRIER
    assert args.expected_pytest_carrier_sha256 == PINNED_PYTEST_CARRIER_SHA256


@pytest.mark.parametrize(
    "omitted",
    ("--pytest-carrier", "--expected-pytest-carrier-sha256"),
)
def test_task4_cli_requires_explicit_pytest_carrier_authority(
    tmp_path: Path,
    omitted: str,
) -> None:
    runner = _runner()
    argv = [
        "observe-candidates",
        "--discovery-input",
        str(tmp_path / "input.json"),
        "--expected-discovery-input-sha256",
        "sha256:" + "1" * 64,
        "--discovery-output",
        str(tmp_path / "discovery.json"),
        "--expected-discovery-output-sha256",
        "sha256:" + "2" * 64,
        "--draft-dispositions",
        str(tmp_path / "draft.json"),
        "--expected-draft-dispositions-sha256",
        "sha256:" + "3" * 64,
        "--python",
        str(PINNED_PYTHON),
        "--workspace",
        str(tmp_path / "workspace"),
        "--expected-tree",
        "a" * 40,
        "--expected-runner-sha256",
        "sha256:" + "4" * 64,
        "--pytest-carrier",
        str(PINNED_PYTEST_CARRIER),
        "--expected-pytest-carrier-sha256",
        PINNED_PYTEST_CARRIER_SHA256,
        "--report-path",
        str(tmp_path / "report.json"),
        "--output",
        str(tmp_path / "output.json"),
    ]
    option_index = argv.index(omitted)
    del argv[option_index : option_index + 2]

    with pytest.raises(SystemExit):
        runner._parser().parse_args(argv)  # pyright: ignore[reportPrivateUsage]


def test_task4_pytest_carrier_verifies_exact_identity_and_setup() -> None:
    runner = _runner()

    carrier = runner._verify_pytest_carrier(  # pyright: ignore[reportPrivateUsage]
        PINNED_PYTEST_CARRIER,
        expected_sha256=PINNED_PYTEST_CARRIER_SHA256,
    )

    assert carrier.as_record() == {
        "executable": str(PINNED_PYTEST_CARRIER),
        "sha256": PINNED_PYTEST_CARRIER_SHA256,
        "version": "bubblewrap 0.9.0",
        "tmp_isolation": "private_tmpfs",
    }


def test_task4_pytest_carrier_digest_tamper_fails_before_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    calls: list[object] = []

    def unexpected_run(*args: object, **kwargs: object) -> NoReturn:
        calls.append((args, kwargs))
        raise AssertionError("carrier subprocess must not run after identity drift")

    monkeypatch.setattr(runner.subprocess, "run", unexpected_run)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner._verify_pytest_carrier(  # pyright: ignore[reportPrivateUsage]
            PINNED_PYTEST_CARRIER,
            expected_sha256="sha256:" + "0" * 64,
        )

    assert caught.value.code == "proof_pytest_carrier_identity_mismatch"
    assert calls == []


def test_task4_pytest_carrier_setup_failure_precedes_inner_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    calls: list[tuple[str, ...]] = []

    def failing_setup(
        argv: tuple[str, ...], **kwargs: Any
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(argv)
        if argv == (str(PINNED_PYTEST_CARRIER), "--version"):
            return subprocess.CompletedProcess(
                argv, 0, stdout=b"bubblewrap 0.9.0\n", stderr=b""
            )
        assert "pytest" not in argv
        return subprocess.CompletedProcess(
            argv, 1, stdout=b"", stderr=b"bwrap: setup failed\n"
        )

    monkeypatch.setattr(runner.subprocess, "run", failing_setup)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner._verify_pytest_carrier(  # pyright: ignore[reportPrivateUsage]
            PINNED_PYTEST_CARRIER,
            expected_sha256=PINNED_PYTEST_CARRIER_SHA256,
        )

    assert caught.value.code == "proof_pytest_carrier_setup_failed"
    assert len(calls) == 2


def test_task4_pytest_carrier_hides_host_tmp_and_discards_child_tmp(
    tmp_path: Path,
) -> None:
    runner = _runner()
    carrier = runner._verify_pytest_carrier(  # pyright: ignore[reportPrivateUsage]
        PINNED_PYTEST_CARRIER,
        expected_sha256=PINNED_PYTEST_CARRIER_SHA256,
    )
    token = hashlib.sha256(str(tmp_path).encode("utf-8")).hexdigest()
    host_sentinel = Path("/tmp") / f"boundary-host-{token}"
    child_sentinel = Path("/tmp") / f"boundary-child-{token}"
    visible_input = tmp_path / "visible-input"
    visible_output = tmp_path / "visible-output"
    visible_input.write_text("visible", encoding="utf-8")
    host_sentinel.write_text("host", encoding="utf-8")
    try:
        completed = runner._run_private_tmp_child(  # pyright: ignore[reportPrivateUsage]
            carrier,
            (
                str(PINNED_PYTHON),
                "-c",
                (
                    "from pathlib import Path; "
                    f"host=Path({str(host_sentinel)!r}); "
                    f"child=Path({str(child_sentinel)!r}); "
                    f"visible_input=Path({str(visible_input)!r}); "
                    f"visible_output=Path({str(visible_output)!r}); "
                    "assert not host.exists(); assert not child.exists(); "
                    "assert visible_input.read_text() == 'visible'; "
                    "child.write_text('child', encoding='utf-8'); "
                    "visible_output.write_text('written', encoding='utf-8'); "
                    "assert child.read_text(encoding='utf-8') == 'child'; "
                    "print('private-tmp-ok')"
                ),
            ),
            cwd=tmp_path.resolve(),
            env={"LANG": "C", "LC_ALL": "C"},
            preserved_paths=(tmp_path.resolve(),),
        )
        assert completed.returncode == 0
        assert completed.stdout == b"private-tmp-ok\n"
        assert host_sentinel.read_text(encoding="utf-8") == "host"
        assert not child_sentinel.exists()
        assert visible_output.read_text(encoding="utf-8") == "written"
    finally:
        host_sentinel.unlink(missing_ok=True)
        child_sentinel.unlink(missing_ok=True)


def test_task4_pytest_carrier_isolates_concurrent_identical_tmp_paths(
    tmp_path: Path,
) -> None:
    runner = _runner()
    carrier = runner._verify_pytest_carrier(  # pyright: ignore[reportPrivateUsage]
        PINNED_PYTEST_CARRIER,
        expected_sha256=PINNED_PYTEST_CARRIER_SHA256,
    )
    shared_path = Path("/tmp/boundary-concurrent-same-name")
    shared_path.unlink(missing_ok=True)

    def one_child(value: str) -> subprocess.CompletedProcess[bytes]:
        return runner._run_private_tmp_child(  # pyright: ignore[reportPrivateUsage]
            carrier,
            (
                str(PINNED_PYTHON),
                "-c",
                (
                    "from pathlib import Path; import sys, time; "
                    f"path=Path({str(shared_path)!r}); "
                    "assert not path.exists(); path.write_text(sys.argv[1]); "
                    "time.sleep(0.2); assert path.read_text() == sys.argv[1]"
                ),
                value,
            ),
            cwd=tmp_path.resolve(),
            env={"LANG": "C", "LC_ALL": "C"},
            preserved_paths=(tmp_path.resolve(),),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        completed = list(pool.map(one_child, ("first", "second")))

    assert [row.returncode for row in completed] == [0, 0]
    assert not shared_path.exists()


def test_task4_observe_candidates_binds_exact_execution_scope(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, contract_fixture, disposition="compatibility_adapter"
    )
    forbidden_root = (tmp_path / "forbidden-root").resolve()

    result = runner.observe_candidates(
        discovery_input,
        discovery_output=discovery_output,
        draft_dispositions=draft,
        expected_discovery_input_sha256=digests["discovery_input"],
        expected_discovery_output_sha256=digests["discovery_output"],
        expected_draft_dispositions_sha256=digests["draft_dispositions"],
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=contract_fixture.baseline_tree,
        expected_runner_sha256=runner.runner_sha256(),
        forbidden_roots=(forbidden_root,),
        **PYTEST_CARRIER_AUTHORITY,
    )

    assert result["input_bindings"]["forbidden_roots"] == [str(forbidden_root)]
    assert result["input_bindings"]["python_execution"] == {
        "executable": str(PINNED_PYTHON),
        "link_target": runner.PINNED_PYTHON_LINK_TARGET,
        "resolved_executable": str(PINNED_PYTHON_TARGET),
        "sha256": runner.PINNED_PYTHON_SHA256,
        "version": runner.PINNED_PYTHON_VERSION,
    }
    assert result["input_bindings"]["pytest_carrier"] == {
        "executable": str(PINNED_PYTEST_CARRIER),
        "sha256": PINNED_PYTEST_CARRIER_SHA256,
        "version": "bubblewrap 0.9.0",
        "tmp_isolation": "private_tmpfs",
    }


def test_task4_cli_publishes_deterministic_non_authoritative_candidates(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    discovery_input, discovery_output, draft, digests = _task4_observation_records(
        runner, contract_fixture, disposition="compatibility_adapter"
    )
    input_path = (tmp_path / "input.json").resolve()
    discovery_path = (tmp_path / "discovery.json").resolve()
    draft_path = (tmp_path / "draft.json").resolve()
    input_path.write_bytes(runner.canonical_json_bytes(discovery_input))
    discovery_path.write_bytes(runner.canonical_json_bytes(discovery_output))
    draft_path.write_bytes(runner.canonical_json_bytes(draft))

    outputs: list[bytes] = []
    for ordinal in (1, 2):
        report_path = (tmp_path / f"report-{ordinal}.json").resolve()
        output_path = (tmp_path / f"output-{ordinal}.json").resolve()
        exit_code = runner.main(
            [
                "observe-candidates",
                "--discovery-input",
                str(input_path),
                "--expected-discovery-input-sha256",
                digests["discovery_input"],
                "--discovery-output",
                str(discovery_path),
                "--expected-discovery-output-sha256",
                digests["discovery_output"],
                "--draft-dispositions",
                str(draft_path),
                "--expected-draft-dispositions-sha256",
                digests["draft_dispositions"],
                "--python",
                str(PINNED_PYTHON),
                "--workspace",
                str(contract_fixture.workspace),
                "--expected-tree",
                contract_fixture.baseline_tree,
                "--expected-runner-sha256",
                runner.runner_sha256(),
                "--pytest-carrier",
                str(PINNED_PYTEST_CARRIER),
                "--expected-pytest-carrier-sha256",
                PINNED_PYTEST_CARRIER_SHA256,
                "--report-path",
                str(report_path),
                "--output",
                str(output_path),
            ]
        )
        assert exit_code == 0
        output_raw = output_path.read_bytes()
        output = json.loads(output_raw)
        assert output_raw == runner.canonical_json_bytes(output)
        assert output["authority_status"] == "NON_AUTHORITATIVE"
        assert "record_sha256" not in output
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["counts"] == output["counts"]
        outputs.append(output_raw)

    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("authority", ("policy", "census"))
def test_bootstrap_baseline_rejects_stale_policy_or_census(
    contract_fixture: ContractFixture,
    tmp_path: Path,
    authority: str,
) -> None:
    runner = _runner()
    policy, census = _bootstrap_records(runner, contract_fixture)
    stale = policy if authority == "policy" else census
    stale["schema_version"] = "stale.v0"

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.capture_bootstrap_baseline(
            policy,
            source_census=census,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            report_path=(tmp_path / f"stale-{authority}.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_record_digest_invalid"


def test_bootstrap_baseline_rejects_census_bound_to_another_policy(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    policy, census = _bootstrap_records(runner, contract_fixture)
    census["preedit_policy_sha256"] = "sha256:" + "0" * 64
    census = _seal(runner, census)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.capture_bootstrap_baseline(
            policy,
            source_census=census,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            report_path=(tmp_path / "misbound-census.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_authority_binding_mismatch"


def test_bootstrap_baseline_rejects_ambiguous_policy_node_pattern(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    policy, census = _bootstrap_records(runner, contract_fixture)
    first_module = contract_fixture.workspace / MANDATORY_PROVIDER_MODULES[0]
    first_module.write_text(
        first_module.read_text(encoding="utf-8")
        + "\ndef test_consumer_01_second():\n    assert True\n",
        encoding="utf-8",
    )
    changed_tree = _commit(contract_fixture.workspace, "ambiguous node")
    policy.pop("record_sha256")
    policy["selector_policy"]["coverage_witness_specs"][0]["spec"][
        "attribution"
    ]["pytest_node_pattern"] = (
        re.escape(MANDATORY_PROVIDER_MODULES[0]) + r"::test_consumer_01.*"
    )
    policy = _seal(runner, policy)
    census = _rebind_census(runner, census, policy)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.capture_bootstrap_baseline(
            policy,
            source_census=census,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=changed_tree,
            report_path=(tmp_path / "ambiguous-node.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_pytest_node_ambiguous"


def test_bootstrap_baseline_rejects_missing_policy_node_pattern(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    policy, census = _bootstrap_records(runner, contract_fixture)
    policy.pop("record_sha256")
    policy["selector_policy"]["coverage_witness_specs"][0]["spec"][
        "attribution"
    ]["pytest_node_pattern"] = (
        re.escape(MANDATORY_PROVIDER_MODULES[0]) + r"::test_missing"
    )
    policy = _seal(runner, policy)
    census = _rebind_census(runner, census, policy)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.capture_bootstrap_baseline(
            policy,
            source_census=census,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            report_path=(tmp_path / "missing-node.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_pytest_node_missing"


def test_bootstrap_baseline_rejects_policy_runner_digest_substitution(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    policy, census = _bootstrap_records(runner, contract_fixture)
    policy.pop("record_sha256")
    policy["selector_policy"]["controller_only_proof_selectors"][0][
        "runner_sha256"
    ] = "sha256:" + "0" * 64
    policy = _seal(runner, policy)
    census = _rebind_census(runner, census, policy)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.capture_bootstrap_baseline(
            policy,
            source_census=census,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            report_path=(tmp_path / "runner-substitution.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_runner_digest_mismatch"


def test_bootstrap_baseline_rejects_provider_lane_substitution(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    policy, census = _bootstrap_records(runner, contract_fixture)
    policy.pop("record_sha256")
    policy["selector_policy"]["provider_visible_pytest_selectors"][0][
        "pytest_module_path"
    ] = RUNNER_RELATIVE_PATH
    policy = _seal(runner, policy)
    census = _rebind_census(runner, census, policy)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.capture_bootstrap_baseline(
            policy,
            source_census=census,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            report_path=(tmp_path / "lane-substitution.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_provider_selector_modules_invalid"


@pytest.mark.parametrize(
    "field",
    ("caller_object_id", "column_start", "column_end"),
)
def test_contract_binds_complete_caller_object_and_span(
    contract_fixture: ContractFixture,
    field: str,
) -> None:
    runner = _runner()
    manifest = copy.deepcopy(contract_fixture.manifest)
    witness = manifest["coverage_witnesses"][0]
    witness[field] = (
        "0" * 40 if field == "caller_object_id" else int(witness[field]) + 1
    )

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.validate_contract(
            manifest,
            consumer_rows=contract_fixture.consumer_rows,
            expected_runner_sha256=runner.runner_sha256(),
        )

    assert caught.value.code == "proof_witness_consumer_binding_mismatch"


def test_baseline_rejects_consumer_blob_drift(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    compat = contract_fixture.workspace / "pkg/compat.py"
    compat.write_text(compat.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
    drifted_tree = _commit(contract_fixture.workspace, "consumer drift")

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.capture_baseline(
            contract_fixture.manifest,
            consumer_rows=contract_fixture.consumer_rows,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=drifted_tree,
            report_path=(tmp_path / "consumer-drift-report.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_witness_blob_drift"


def test_static_observation_is_scoped_to_exact_consumer_columns(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    source = "ModelSpec = 0; resolve_generator = 1\n"
    compat = contract_fixture.workspace / "pkg/compat.py"
    compat.write_text(source, encoding="utf-8")
    _commit(contract_fixture.workspace, "two same-line syntax matches")
    manifest = copy.deepcopy(contract_fixture.manifest)
    consumers = copy.deepcopy(contract_fixture.consumer_rows)
    consumer = next(row for row in consumers if row["consumer_id"] == "consumer-static")
    start_column = source.index("resolve_generator")
    end_column = start_column + len("resolve_generator")
    consumer["caller_object_id"] = _blob(contract_fixture.workspace, "pkg/compat.py")
    consumer["span"]["column_start"] = start_column
    consumer["span"]["column_end"] = end_column
    witness = next(
        row
        for row in manifest["coverage_witnesses"]
        if row["witness_id"] == "w-static"
    )
    expected = {
        "matches": [
            {
                "column": start_column,
                "kind": "name",
                "line": 1,
                "value": "resolve_generator",
            }
        ]
    }
    witness["caller_object_id"] = consumer["caller_object_id"]
    witness["column_start"] = start_column
    witness["column_end"] = end_column
    witness["expected_result"] = expected
    spec = next(
        row
        for row in manifest["desired_state_proof_specs"]
        if row["witness_id"] == "w-static"
    )
    spec["expected_result"] = expected

    contract = runner.validate_contract(
        manifest,
        consumer_rows=consumers,
        expected_runner_sha256=runner.runner_sha256(),
    )
    parsed_witness = next(
        row for row in contract.witnesses if row.witness_id == "w-static"
    )

    observation, _ = runner._static_observation(
        parsed_witness,
        contract_fixture.workspace,
    )
    assert observation == expected


def _task4_runtime_origin_witness(
    runner: ModuleType,
    fixture: ContractFixture,
    *,
    source: str,
    additional_files: tuple[tuple[str, str], ...] = (),
) -> Any:
    contract = runner.validate_contract(
        fixture.manifest,
        consumer_rows=fixture.consumer_rows,
        expected_runner_sha256=runner.runner_sha256(),
    )
    witness = next(row for row in contract.witnesses if row.witness_id == "w-runtime")
    for relative, content in additional_files:
        _write(fixture.workspace / relative, content)
    _write(fixture.workspace / "pkg/runtime_target.py", source)
    _commit(fixture.workspace, "configure runtime forbidden-name origin")
    return replace(
        witness,
        caller_object_id=_blob(fixture.workspace, "pkg/runtime_target.py"),
    )


def test_runtime_probe_allows_forbidden_name_projected_from_workspace(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    witness = _task4_runtime_origin_witness(
        runner,
        contract_fixture,
        source=(
            "def exercise(value):\n"
            "    import ptycho.evaluation\n"
            "    return {'boundary': ptycho.evaluation.VALUE, 'value': value}\n"
        ),
        additional_files=(
            ("ptycho/__init__.py", ""),
            ("ptycho/evaluation.py", "VALUE = 'projected'\n"),
        ),
    )

    event, blob = runner._runtime_observation(  # pyright: ignore[reportPrivateUsage]
        witness,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        forbidden_roots=(),
        project_owned_module_prefixes=("pkg", "ptycho"),
    )

    assert event["event_kind"] == "callable_entry"
    assert blob == witness.caller_object_id


@pytest.mark.parametrize("origin_kind", ("missing", "outside"))
def test_runtime_probe_rejects_forbidden_name_without_projected_origin(
    contract_fixture: ContractFixture,
    origin_kind: str,
) -> None:
    runner = _runner()
    origin_assignment = (
        ""
        if origin_kind == "missing"
        else "    module.__file__ = '/outside/ptycho/evaluation.py'\n"
    )
    witness = _task4_runtime_origin_witness(
        runner,
        contract_fixture,
        source=(
            "def exercise(value):\n"
            "    import sys\n"
            "    import types\n"
            "    module = types.ModuleType('ptycho.evaluation')\n"
            f"{origin_assignment}"
            "    sys.modules['ptycho.evaluation'] = module\n"
            "    return {'boundary': 'delegated', 'value': value}\n"
        ),
    )

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner._runtime_observation(  # pyright: ignore[reportPrivateUsage]
            witness,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            forbidden_roots=(),
            project_owned_module_prefixes=("pkg", "ptycho"),
        )

    assert caught.value.code == "proof_origin_isolation_failed"
    assert caught.value.detail["loaded"] == ("ptycho.evaluation",)


def test_runtime_probe_rejects_any_loaded_module_from_forbidden_root(
    contract_fixture: ContractFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    external_root = (tmp_path / "external-runtime").resolve()
    external_root.mkdir()
    _write(external_root / "ambient_boundary_dependency.py", "VALUE = 'ambient'\n")
    runtime_path = contract_fixture.workspace / "pkg/runtime_target.py"
    _write(
        runtime_path,
        (
            "def exercise(value):\n"
            "    import os\n"
            "    import sys\n"
            "    sys.path.insert(0, os.environ['ES_TEST_EXTERNAL_ROOT'])\n"
            "    __import__('ambient_boundary_dependency')\n"
            "    return {'boundary': 'delegated', 'value': value}\n"
        ),
    )
    tree = _commit(contract_fixture.workspace, "load forbidden runtime module")
    manifest = copy.deepcopy(contract_fixture.manifest)
    consumers = copy.deepcopy(contract_fixture.consumer_rows)
    consumer = next(row for row in consumers if row["consumer_id"] == "consumer-runtime")
    consumer["caller_object_id"] = _blob(
        contract_fixture.workspace,
        "pkg/runtime_target.py",
    )
    consumer["span"]["line_end"] = 6
    witness = next(
        row
        for row in manifest["coverage_witnesses"]
        if row["witness_id"] == "w-runtime"
    )
    witness["caller_object_id"] = consumer["caller_object_id"]
    witness["end_line"] = 6
    monkeypatch.setenv("ES_TEST_EXTERNAL_ROOT", str(external_root))

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.capture_baseline(
            manifest,
            consumer_rows=consumers,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=tree,
            report_path=(tmp_path / "runtime-origin-report.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            forbidden_roots=(external_root,),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_origin_isolation_failed"


def test_runtime_probe_disables_ambient_user_site_configuration(
    contract_fixture: ContractFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    user_base = (tmp_path / "user-base").resolve()
    site_packages = (
        user_base
        / "lib"
        / "python3.11"
        / "site-packages"
    )
    site_packages.mkdir(parents=True)
    marker = (tmp_path / "ambient-site-loaded.txt").resolve()
    _write(
        site_packages / "sitecustomize.py",
        (
            "import os\n"
            "from pathlib import Path\n"
            "Path(os.environ['ES_TEST_SITE_MARKER']).write_text('loaded', encoding='utf-8')\n"
        ),
    )
    monkeypatch.setenv("PYTHONUSERBASE", str(user_base))
    monkeypatch.setenv("ES_TEST_SITE_MARKER", str(marker))
    contract = runner.validate_contract(
        contract_fixture.manifest,
        consumer_rows=contract_fixture.consumer_rows,
        expected_runner_sha256=runner.runner_sha256(),
    )
    witness = next(row for row in contract.witnesses if row.witness_id == "w-runtime")

    event, _ = runner._runtime_observation(
        witness,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        forbidden_roots=(),
        project_owned_module_prefixes=runner._project_prefixes(contract),
    )

    assert event == witness.expected_result
    assert not marker.exists()


def test_capture_baseline_runs_one_aggregate_lane_and_records_truthful_witnesses(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()

    result = runner.capture_baseline(
        contract_fixture.manifest,
        consumer_rows=contract_fixture.consumer_rows,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=contract_fixture.baseline_tree,
        report_path=(tmp_path / "baseline-report.json").resolve(),
        expected_runner_sha256=runner.runner_sha256(),
        **PYTEST_CARRIER_AUTHORITY,
    )

    assert result["schema_version"] == "es_f1_boundary_baseline.v1"
    assert result["runner_sha256"] == runner.runner_sha256()
    assert result["pre_tree"] == contract_fixture.baseline_tree
    assert result["post_tree"] == contract_fixture.baseline_tree
    assert result["aggregate_pytest_argv"] == [
        str(PINNED_PYTHON),
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        *contract_fixture.provider_modules,
    ]
    assert result["collected_node_ids"] == list(contract_fixture.node_ids)
    assert result["collected_node_sha256"] == _sha256(
        runner.canonical_json_bytes(list(contract_fixture.node_ids))
    )
    assert result["outcomes"] == {
        "errors": 0,
        "failed": 0,
        "passed": 19,
        "skipped": 0,
    }
    assert result["origin_isolation"]["forbidden_origin_rows"] == []
    assert result["origin_isolation"]["outside_project_origin_rows"] == []
    assert result["origin_isolation"]["cache_artifacts"] == []
    rows = result["witness_results"]
    assert [row["witness_id"] for row in rows] == list(contract_fixture.witness_ids)
    assert all(row["mechanically_observed"] is True for row in rows)
    consumers_by_id = {
        row["consumer_id"]: row for row in contract_fixture.consumer_rows
    }
    assert all(
        row["target_blob_id"]
        == consumers_by_id[row["consumer_id"]]["caller_object_id"]
        for row in rows
    )
    assert next(row for row in rows if row["witness_id"] == "w-absence")[
        "passed"
    ] is False
    assert all(
        row["passed"] is True for row in rows if row["witness_id"] != "w-absence"
    )


def test_desired_state_executes_every_spec_and_replays_exact_rows(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    (contract_fixture.workspace / "pkg/remove_me.py").unlink()
    desired_tree = _commit(contract_fixture.workspace, "desired")
    digest_before = runner.runner_sha256()

    result_rows = runner.execute_desired_state(
        contract_fixture.manifest,
        consumer_rows=contract_fixture.consumer_rows,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=desired_tree,
        expected_runner_sha256=digest_before,
        **PYTEST_CARRIER_AUTHORITY,
    )

    assert [row["proof_id"] for row in result_rows] == [
        row["proof_id"]
        for row in contract_fixture.manifest["desired_state_proof_specs"]
    ]
    assert all(row["passed"] is True for row in result_rows)
    assert all(row["target_tree"] == desired_tree for row in result_rows)
    assert runner.runner_sha256() == digest_before
    assert runner.execute_desired_state(
        contract_fixture.manifest,
        consumer_rows=contract_fixture.consumer_rows,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=desired_tree,
        expected_runner_sha256=digest_before,
        expected_result_rows=copy.deepcopy(result_rows),
        **PYTEST_CARRIER_AUTHORITY,
    ) == result_rows


def _task6_all_lanes_contract(
    runner: ModuleType,
    fixture: ContractFixture,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = copy.deepcopy(fixture.manifest)
    consumers = copy.deepcopy(fixture.consumer_rows)
    workspace = fixture.workspace

    controller_source_path = "pkg/controller_target.py"
    controller_source = (
        "def controller_boundary():\n"
        "    return 'controller-observed'\n"
    )
    controller_module = "tests/controller/test_controller_observer.py"
    controller_node = f"{controller_module}::test_controller_observer"
    _write(workspace / controller_source_path, controller_source)
    _write(
        workspace / controller_module,
        (
            "from pkg.controller_target import controller_boundary\n\n"
            "def test_controller_observer():\n"
            "    assert controller_boundary() == 'controller-observed'\n"
        ),
    )

    import_source_path = "pkg/import_observed.py"
    import_source = 'IMPORT_MARKER = "observed-during-import"\n'
    _write(workspace / import_source_path, import_source)
    _commit(workspace, "add all-lanes observation drivers")

    runner_digest = runner.runner_sha256()
    controller_blob = _blob(workspace, controller_source_path)
    controller_span = {
        "line_start": 1,
        "column_start": 4,
        "line_end": 1,
        "column_end": 23,
    }
    controller_binding = {
        "event_kind": "callable_entry",
        "phase": "call",
        "attribution": {
            "attribution_kind": "pytest_node",
            "pytest_node_id": controller_node,
        },
    }
    controller_event = _expected_callable_source_event(
        source=controller_source,
        source_path=(workspace / controller_source_path).resolve(),
        consumer_path=controller_source_path,
        caller_object_id=controller_blob,
        function_name="controller_boundary",
        span=controller_span,
        binding=controller_binding,
    )
    controller_selector_id = "controller-pytest"
    controller_witness_id = "w-controller-pytest"
    manifest["controller_only_proof_selectors"].append(
        {
            "selector_id": controller_selector_id,
            "ordinal": len(manifest["controller_only_proof_selectors"]) + 1,
            "proof_kind": "boundary_runtime",
            "execution_kind": "pytest_aggregate",
            "runner_path": RUNNER_RELATIVE_PATH,
            "runner_sha256": runner_digest,
            "argv": [
                str(PINNED_PYTHON),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                controller_module,
            ],
            "input_bindings": [
                {
                    "path": controller_module,
                    "sha256": _sha256((workspace / controller_module).read_bytes()),
                }
            ],
            "coverage_witness_ids": [controller_witness_id],
        }
    )
    consumers.append(
        _consumer_row(
            workspace,
            consumer_id="consumer-controller-pytest",
            match_id="match-controller-pytest",
            path=controller_source_path,
            start_line=controller_span["line_start"],
            end_line=controller_span["line_end"],
            column_start=controller_span["column_start"],
            column_end=controller_span["column_end"],
            proof_kind="boundary_runtime",
            selector_id=controller_selector_id,
            witness_kind="controller_pytest_runtime",
            witness_id=controller_witness_id,
        )
    )
    manifest["coverage_witnesses"].append(
        {
            "witness_id": controller_witness_id,
            "selector_id": controller_selector_id,
            "consumer_id": "consumer-controller-pytest",
            "proof_kind": "boundary_runtime",
            "witness_kind": "controller_pytest_runtime",
            "runner_sha256": runner_digest,
            "consumer_path": controller_source_path,
            "caller_object_id": controller_blob,
            "start_line": controller_span["line_start"],
            "column_start": controller_span["column_start"],
            "end_line": controller_span["line_end"],
            "column_end": controller_span["column_end"],
            "match_id": "match-controller-pytest",
            "source_event_binding": controller_binding,
            "expected_event": controller_event,
        }
    )
    manifest["desired_state_proof_specs"].append(
        {
            "proof_id": (
                f"proof-{len(manifest['desired_state_proof_specs']) + 1:02d}"
            ),
            "ordinal": len(manifest["desired_state_proof_specs"]) + 1,
            "selector_id": controller_selector_id,
            "witness_id": controller_witness_id,
            "consumer_id": "consumer-controller-pytest",
            "proof_kind": "boundary_runtime",
            "expected_result": controller_event,
        }
    )

    import_path = (workspace / import_source_path).resolve()
    import_tree = ast.parse(import_source, filename=str(import_path))
    marker = next(
        node
        for node in ast.walk(import_tree)
        if isinstance(node, ast.Constant)
        and node.value == "observed-during-import"
    )
    import_span = _task2_span(marker)
    import_code = compile(import_source, str(import_path), "exec")
    import_instructions = [
        instruction
        for instruction in dis.get_instructions(import_code)
        if instruction.opname == "LOAD_CONST"
        and instruction.argval == "observed-during-import"
        and instruction.positions is not None
        and {
            "line_start": instruction.positions.lineno,
            "column_start": instruction.positions.col_offset,
            "line_end": instruction.positions.end_lineno,
            "column_end": instruction.positions.end_col_offset,
        }
        == import_span
    ]
    assert len(import_instructions) == 1
    import_instruction = import_instructions[0]
    import_probe = {
        "action": "import_module",
        "module": "pkg.import_observed",
        "expected_outcome": {"status": "returned"},
    }
    import_binding = {
        "event_kind": "opcode_exact_span",
        "phase": "residual",
        "attribution": {
            "attribution_kind": "residual_action",
            "action_sha256": _sha256(runner.canonical_json_bytes(import_probe)),
        },
    }
    import_blob = _blob(workspace, import_source_path)
    import_event = {
        "event_kind": "opcode_exact_span",
        "phase": "residual",
        "attribution": copy.deepcopy(import_binding["attribution"]),
        "consumer_path": import_source_path,
        "caller_object_id": import_blob,
        "span": import_span,
        "hit_count": 1,
        "opcode_exact_span": {
            "code_qualname": import_code.co_qualname,
            "code_firstlineno": import_code.co_firstlineno,
            "instruction_offset": import_instruction.offset,
            "opname": import_instruction.opname,
            "argrepr_sha256": _sha256(import_instruction.argrepr.encode("utf-8")),
        },
    }
    import_selector_id = "controller-import"
    import_witness_id = "w-import-action"
    manifest["controller_only_proof_selectors"].append(
        {
            "selector_id": import_selector_id,
            "ordinal": len(manifest["controller_only_proof_selectors"]) + 1,
            "proof_kind": "boundary_runtime",
            "execution_kind": "isolated_probe",
            "runner_path": RUNNER_RELATIVE_PATH,
            "runner_sha256": runner_digest,
            "argv": [
                "boundary_runtime",
                "--selector-id",
                import_selector_id,
            ],
            "input_bindings": [
                {
                    "path": "proof_inputs/contract.json",
                    "sha256": _sha256(
                        (workspace / "proof_inputs/contract.json").read_bytes()
                    ),
                }
            ],
            "coverage_witness_ids": [import_witness_id],
        }
    )
    consumers.append(
        _consumer_row(
            workspace,
            consumer_id="consumer-import-action",
            match_id="match-import-action",
            path=import_source_path,
            start_line=import_span["line_start"],
            end_line=import_span["line_end"],
            column_start=import_span["column_start"],
            column_end=import_span["column_end"],
            proof_kind="boundary_runtime",
            selector_id=import_selector_id,
            witness_kind="runtime_probe",
            witness_id=import_witness_id,
        )
    )
    manifest["coverage_witnesses"].append(
        {
            "witness_id": import_witness_id,
            "selector_id": import_selector_id,
            "consumer_id": "consumer-import-action",
            "proof_kind": "boundary_runtime",
            "witness_kind": "runtime_probe",
            "runner_sha256": runner_digest,
            "consumer_path": import_source_path,
            "caller_object_id": import_blob,
            "start_line": import_span["line_start"],
            "column_start": import_span["column_start"],
            "end_line": import_span["line_end"],
            "column_end": import_span["column_end"],
            "match_id": "match-import-action",
            "probe": import_probe,
            "source_event_binding": import_binding,
            "expected_event": import_event,
        }
    )
    manifest["desired_state_proof_specs"].append(
        {
            "proof_id": (
                f"proof-{len(manifest['desired_state_proof_specs']) + 1:02d}"
            ),
            "ordinal": len(manifest["desired_state_proof_specs"]) + 1,
            "selector_id": import_selector_id,
            "witness_id": import_witness_id,
            "consumer_id": "consumer-import-action",
            "proof_kind": "boundary_runtime",
            "expected_result": import_event,
        }
    )
    return manifest, consumers


def test_occurrence_observability_end_to_end_all_lanes_and_desired_replay(
    contract_fixture: ContractFixture,
) -> None:
    runner = _runner()
    manifest, consumers = _task6_all_lanes_contract(runner, contract_fixture)
    (contract_fixture.workspace / "pkg/remove_me.py").unlink()
    desired_tree = _commit(contract_fixture.workspace, "all-lanes desired state")
    runner_digest = runner.runner_sha256()

    result_rows = runner.execute_desired_state(
        manifest,
        consumer_rows=consumers,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=desired_tree,
        expected_runner_sha256=runner_digest,
        **PYTEST_CARRIER_AUTHORITY,
    )

    witnesses = {
        row["witness_id"]: row for row in manifest["coverage_witnesses"]
    }
    assert any(row["witness_kind"] == "pytest_runtime" for row in result_rows)
    assert any(
        row["witness_kind"] == "controller_pytest_runtime"
        for row in result_rows
    )
    assert any(row["witness_kind"] == "static_ast" for row in result_rows)
    assert {
        witnesses[row["witness_id"]]["probe"]["action"]
        for row in result_rows
        if row["witness_kind"] == "runtime_probe"
    } == {"call", "import_module"}
    assert all(row["mechanically_observed"] is True for row in result_rows)
    assert all(row["passed"] is True for row in result_rows)

    assert runner.execute_desired_state(
        manifest,
        consumer_rows=consumers,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=desired_tree,
        expected_runner_sha256=runner_digest,
        expected_result_rows=copy.deepcopy(result_rows),
        **PYTEST_CARRIER_AUTHORITY,
    ) == result_rows


@pytest.mark.parametrize(
    ("tamper", "code"),
    (
        ("runner_sha", "proof_runner_digest_mismatch"),
        ("cross_lane_selector", "proof_selector_cross_lane_duplicate"),
        ("backpointer", "proof_witness_backpointer_mismatch"),
        ("proof_kind", "proof_kind_mismatch"),
        ("unmapped_consumer", "proof_consumer_unmapped"),
        ("unknown_node", "proof_pytest_node_unknown"),
    ),
)
def test_contract_validation_fails_closed_for_mapping_and_lane_tamper(
    contract_fixture: ContractFixture,
    tamper: str,
    code: str,
) -> None:
    runner = _runner()
    manifest = copy.deepcopy(contract_fixture.manifest)
    consumers = copy.deepcopy(contract_fixture.consumer_rows)
    if tamper == "runner_sha":
        manifest["coverage_witnesses"][0]["runner_sha256"] = "sha256:" + "0" * 64
    elif tamper == "cross_lane_selector":
        manifest["controller_only_proof_selectors"][0]["selector_id"] = (
            manifest["provider_visible_pytest_selectors"][0]["selector_id"]
        )
    elif tamper == "backpointer":
        manifest["provider_visible_pytest_selectors"][0][
            "coverage_witness_ids"
        ] = [manifest["coverage_witnesses"][1]["witness_id"]]
    elif tamper == "proof_kind":
        manifest["desired_state_proof_specs"][0]["proof_kind"] = "non_cdi_static"
    elif tamper == "unmapped_consumer":
        consumers.pop()
    elif tamper == "unknown_node":
        manifest["coverage_witnesses"][0]["source_event_binding"]["attribution"][
            "pytest_node_id"
        ] += "-unknown"
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.validate_contract(
            manifest,
            consumer_rows=consumers,
            expected_runner_sha256=runner.runner_sha256(),
        )

    assert caught.value.code == code


def test_baseline_rejects_blob_and_input_binding_drift(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    manifest = copy.deepcopy(contract_fixture.manifest)
    manifest["provider_visible_pytest_selectors"][0]["projection_blob_id"] = (
        "0" * 40
    )
    with pytest.raises(runner.BoundaryProofError) as blob_caught:
        runner.capture_baseline(
            manifest,
            consumer_rows=contract_fixture.consumer_rows,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            report_path=(tmp_path / "blob-report.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )
    assert blob_caught.value.code == "proof_selector_blob_drift"

    manifest = copy.deepcopy(contract_fixture.manifest)
    manifest["controller_only_proof_selectors"][0]["input_bindings"][0][
        "sha256"
    ] = "sha256:" + "0" * 64
    with pytest.raises(runner.BoundaryProofError) as binding_caught:
        runner.capture_baseline(
            manifest,
            consumer_rows=contract_fixture.consumer_rows,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            report_path=(tmp_path / "binding-report.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )
    assert binding_caught.value.code == "proof_input_binding_drift"


def test_baseline_rejects_echoed_or_unobserved_runtime_witness(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    manifest = copy.deepcopy(contract_fixture.manifest)
    witness = manifest["coverage_witnesses"][0]
    witness["source_event_binding"]["phase"] = "setup"
    witness["expected_event"]["phase"] = "setup"
    manifest["desired_state_proof_specs"][0]["expected_result"]["phase"] = "setup"

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.capture_baseline(
            manifest,
            consumer_rows=contract_fixture.consumer_rows,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=contract_fixture.baseline_tree,
            report_path=(tmp_path / "unobserved-report.json").resolve(),
            expected_runner_sha256=runner.runner_sha256(),
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == "proof_witness_unobserved"


@pytest.mark.parametrize(
    ("tamper", "code"),
    (
        ("missing", "proof_result_missing"),
        ("extra", "proof_result_extra"),
        ("reordered", "proof_result_reordered"),
        ("blob", "proof_result_blob_drift"),
        ("boolean_ordinal", "proof_result_shape_invalid"),
        ("unobserved", "proof_result_unobserved"),
        ("unmapped", "proof_result_unmapped"),
    ),
)
def test_desired_state_rejects_invalid_result_rows_before_execution(
    contract_fixture: ContractFixture,
    tamper: str,
    code: str,
) -> None:
    runner = _runner()
    (contract_fixture.workspace / "pkg/remove_me.py").unlink()
    desired_tree = _commit(contract_fixture.workspace, "desired")
    result_rows = runner.execute_desired_state(
        contract_fixture.manifest,
        consumer_rows=contract_fixture.consumer_rows,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        expected_tree=desired_tree,
        expected_runner_sha256=runner.runner_sha256(),
        **PYTEST_CARRIER_AUTHORITY,
    )
    expected = copy.deepcopy(result_rows)
    if tamper == "missing":
        expected.pop()
    elif tamper == "extra":
        extra = copy.deepcopy(expected[-1])
        extra["proof_id"] = "proof-extra"
        expected.append(extra)
    elif tamper == "reordered":
        expected[0], expected[1] = expected[1], expected[0]
    elif tamper == "blob":
        expected[0]["target_blob_id"] = "0" * 40
    elif tamper == "boolean_ordinal":
        expected[0]["ordinal"] = True
    elif tamper == "unobserved":
        expected[0]["mechanically_observed"] = False
    elif tamper == "unmapped":
        expected[0]["consumer_id"] = "consumer-unknown"
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)

    with pytest.raises(runner.BoundaryProofError) as caught:
        runner.execute_desired_state(
            contract_fixture.manifest,
            consumer_rows=contract_fixture.consumer_rows,
            python=PINNED_PYTHON,
            workspace=contract_fixture.workspace,
            expected_tree=desired_tree,
            expected_runner_sha256=runner.runner_sha256(),
            expected_result_rows=expected,
            **PYTEST_CARRIER_AUTHORITY,
        )

    assert caught.value.code == code


def test_cli_loads_digest_pinned_records_and_publishes_canonical_baseline(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    manifest_path = tmp_path / "selector-manifest.json"
    census_path = tmp_path / "source-census.json"
    manifest_schema_path = tmp_path / "selector-manifest.schema.json"
    census_schema_path = tmp_path / "source-census.schema.json"
    output_path = tmp_path / "baseline.json"
    report_path = tmp_path / "origin.json"
    policy_digest = "sha256:" + "1" * 64
    census = _seal(
        runner,
        {
            "schema_version": "test_source_census.v1",
            "preedit_policy_sha256": policy_digest,
            "consumer_rows": contract_fixture.consumer_rows,
        },
    )
    manifest = _seal(
        runner,
        {
            "schema_version": "test_selector_manifest.v1",
            "preedit_policy_sha256": policy_digest,
            "source_census_sha256": census["record_sha256"],
            **contract_fixture.manifest,
            "baseline_characterization": {},
            "feasibility_spike": {},
        },
    )
    manifest_raw = runner.canonical_json_bytes(manifest)
    census_raw = runner.canonical_json_bytes(census)
    manifest_path.write_bytes(manifest_raw)
    census_path.write_bytes(census_raw)
    for path, record in (
        (manifest_schema_path, manifest),
        (census_schema_path, census),
    ):
        path.write_text(
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "additionalProperties": False,
                    "required": sorted(record),
                    "properties": {
                        key: (
                            {
                                "type": "string",
                                "pattern": "^sha256:[0-9a-f]{64}$",
                            }
                            if key == "record_sha256"
                            else {}
                        )
                        for key in record
                    },
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    completed = subprocess.run(
        (
            str(Path(sys.executable).resolve()),
            str(RUNNER_PATH),
            "baseline",
            "--selector-manifest",
            str(manifest_path.resolve()),
            "--expected-selector-manifest-sha256",
            _sha256(manifest_raw),
            "--selector-manifest-schema",
            str(manifest_schema_path.resolve()),
            "--source-census",
            str(census_path.resolve()),
            "--expected-source-census-sha256",
            _sha256(census_raw),
            "--source-census-schema",
            str(census_schema_path.resolve()),
            "--python",
            str(PINNED_PYTHON),
            "--workspace",
            str(contract_fixture.workspace),
            "--expected-tree",
            contract_fixture.baseline_tree,
            "--expected-runner-sha256",
            runner.runner_sha256(),
            "--pytest-carrier",
            str(PINNED_PYTEST_CARRIER),
            "--expected-pytest-carrier-sha256",
            PINNED_PYTEST_CARRIER_SHA256,
            "--report-path",
            str(report_path.resolve()),
            "--output",
            str(output_path.resolve()),
        ),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    raw = output_path.read_bytes()
    value = json.loads(raw)
    assert raw == runner.canonical_json_bytes(value)
    assert value["collected_node_ids"] == list(contract_fixture.node_ids)


def test_cli_bootstrap_baseline_accepts_policy_and_census_without_selector_artifact(
    contract_fixture: ContractFixture,
    tmp_path: Path,
) -> None:
    runner = _runner()
    policy, census = _bootstrap_records(runner, contract_fixture)
    policy_path = (tmp_path / "preedit-policy.json").resolve()
    census_path = (tmp_path / "source-census.json").resolve()
    policy_schema_path = (tmp_path / "preedit-policy.schema.json").resolve()
    census_schema_path = (tmp_path / "source-census.schema.json").resolve()
    output_path = (tmp_path / "bootstrap-baseline.json").resolve()
    report_path = (tmp_path / "bootstrap-origin.json").resolve()
    policy_raw = runner.canonical_json_bytes(policy)
    census_raw = runner.canonical_json_bytes(census)
    policy_path.write_bytes(policy_raw)
    census_path.write_bytes(census_raw)
    _write_test_closed_schema(policy_schema_path, policy)
    _write_test_closed_schema(census_schema_path, census)

    completed = subprocess.run(
        (
            str(Path(sys.executable).resolve()),
            str(RUNNER_PATH),
            "bootstrap-baseline",
            "--preedit-policy",
            str(policy_path),
            "--expected-preedit-policy-sha256",
            _sha256(policy_raw),
            "--preedit-policy-schema",
            str(policy_schema_path),
            "--source-census",
            str(census_path),
            "--expected-source-census-sha256",
            _sha256(census_raw),
            "--source-census-schema",
            str(census_schema_path),
            "--python",
            str(PINNED_PYTHON),
            "--workspace",
            str(contract_fixture.workspace),
            "--expected-tree",
            contract_fixture.baseline_tree,
            "--expected-runner-sha256",
            runner.runner_sha256(),
            "--pytest-carrier",
            str(PINNED_PYTEST_CARRIER),
            "--expected-pytest-carrier-sha256",
            PINNED_PYTEST_CARRIER_SHA256,
            "--report-path",
            str(report_path),
            "--output",
            str(output_path),
        ),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    raw = output_path.read_bytes()
    value = json.loads(raw)
    assert raw == runner.canonical_json_bytes(value)
    assert value["schema_version"] == "es_f1_boundary_baseline.v1"
    assert value["collected_node_ids"] == list(contract_fixture.node_ids)
    assert "selector_manifest" not in value
    assert not (tmp_path / "preedit-selector-manifest.json").exists()


def test_task1b_boundary_parser_accepts_closed_controller_pytest_runtime_and_rejects_lane_crossed() -> None:
    runner = _runner()
    runner_digest = runner.runner_sha256()
    node_id = "tests/torch/test_model.py::test_boundary"
    controller_row = {
        "selector_id": "CO-PYTEST-01",
        "ordinal": 1,
        "proof_kind": "boundary_runtime",
        "execution_kind": "pytest_aggregate",
        "runner_path": RUNNER_RELATIVE_PATH,
        "runner_sha256": runner_digest,
        "argv": [
            str(PINNED_PYTHON),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/torch/test_model.py",
        ],
        "input_bindings": [
            {
                "path": "tests/torch/test_model.py",
                "sha256": "sha256:" + "1" * 64,
            }
        ],
        "coverage_witness_ids": ["w-controller"],
    }
    selectors = runner._parse_controller_selectors(  # pyright: ignore[reportPrivateUsage]
        [controller_row], actual_runner_sha256=runner_digest
    )
    assert selectors[0].execution_kind == "pytest_aggregate"

    source_event_binding = {
        "event_kind": "opcode_exact_span",
        "phase": "call",
        "attribution": {
            "attribution_kind": "pytest_node",
            "pytest_node_id": node_id,
        },
    }
    witness = {
        "witness_id": "w-controller",
        "selector_id": "CO-PYTEST-01",
        "consumer_id": "consumer-controller",
        "proof_kind": "boundary_runtime",
        "witness_kind": "controller_pytest_runtime",
        "runner_sha256": runner_digest,
        "consumer_path": "pkg/model.py",
        "caller_object_id": "a" * 40,
        "start_line": 4,
        "column_start": 11,
        "end_line": 4,
        "column_end": 24,
        "match_id": "match-controller",
        "source_event_binding": source_event_binding,
        "expected_event": {"status": "passed"},
    }
    parsed = runner._parse_witnesses(  # pyright: ignore[reportPrivateUsage]
        [witness], runner_digest=runner_digest
    )
    assert parsed[0].witness_kind == "controller_pytest_runtime"
    assert parsed[0].source_event_binding == source_event_binding

    lane_crossed = copy.deepcopy(witness)
    lane_crossed["witness_kind"] = "pytest_runtime"
    with pytest.raises(runner.BoundaryProofError):
        runner._parse_witnesses(  # pyright: ignore[reportPrivateUsage]
            [lane_crossed], runner_digest=runner_digest
        )


def test_task1b_boundary_runtime_probe_parser_accepts_closed_actions_and_rejects_placeholder() -> None:
    runner = _runner()
    import_action = {
        "action": "import_module",
        "module": "pkg.model",
        "expected_outcome": {"status": "returned"},
    }
    call_action = {
        "action": "call",
        "module": "pkg.model",
        "callable": "Factory.build",
        "args": [1, True, None, {"count": 2}],
        "kwargs": {"enabled": False},
        "return_value": "ignore",
        "expected_outcome": {
            "status": "raised",
            "exception_type": "builtins.ValueError",
        },
    }

    runner._validate_runtime_probe(import_action)  # pyright: ignore[reportPrivateUsage]
    runner._validate_runtime_probe(call_action)  # pyright: ignore[reportPrivateUsage]

    old_placeholder = {
        "module": "pkg.model",
        "callable": "Factory.build",
        "args": [],
        "kwargs": {},
    }
    with pytest.raises(runner.BoundaryProofError) as caught:
        runner._validate_runtime_probe(  # pyright: ignore[reportPrivateUsage]
            old_placeholder
        )
    assert caught.value.code == "proof_runtime_probe_invalid"


def test_task1e_provider_pytest_rich_witness_requires_source_event_binding() -> None:
    runner = _runner()
    runner_digest = runner.runner_sha256()
    node_id = "tests/torch/test_model.py::test_boundary"
    source_event_binding = {
        "event_kind": "opcode_exact_span",
        "phase": "call",
        "attribution": {
            "attribution_kind": "pytest_node",
            "pytest_node_id": node_id,
        },
    }
    witness = {
        "witness_id": "w-provider",
        "selector_id": "provider-01",
        "consumer_id": "consumer-provider",
        "proof_kind": "boundary_runtime",
        "witness_kind": "pytest_runtime",
        "runner_sha256": runner_digest,
        "consumer_path": "pkg/model.py",
        "caller_object_id": "a" * 40,
        "start_line": 4,
        "column_start": 11,
        "end_line": 4,
        "column_end": 24,
        "match_id": "match-provider",
        "source_event_binding": source_event_binding,
        "expected_event": {"status": "passed"},
    }

    parsed = runner._parse_witnesses(  # pyright: ignore[reportPrivateUsage]
        [witness], runner_digest=runner_digest
    )
    assert parsed[0].source_event_binding == source_event_binding

    legacy = copy.deepcopy(witness)
    legacy.pop("source_event_binding")
    legacy.update(
        {
            "pytest_node_id": node_id,
            "event_id": "pytest_node_consumer_span.v1",
        }
    )
    with pytest.raises(runner.BoundaryProofError) as caught:
        runner._parse_witnesses(  # pyright: ignore[reportPrivateUsage]
            [legacy], runner_digest=runner_digest
        )
    assert caught.value.code == "proof_witnesses_invalid"


def test_task1e_runtime_probe_rich_witness_requires_source_event_binding() -> None:
    runner = _runner()
    runner_digest = runner.runner_sha256()
    probe = {
        "action": "call",
        "module": "pkg.model",
        "callable": "Factory.build",
        "args": [],
        "kwargs": {},
        "return_value": "ignore",
        "expected_outcome": {"status": "returned"},
    }
    source_event_binding = {
        "event_kind": "callable_entry",
        "phase": "residual",
        "attribution": {
            "attribution_kind": "residual_action",
            "action_sha256": _sha256(runner.canonical_json_bytes(probe)),
        },
    }
    witness = {
        "witness_id": "w-probe",
        "selector_id": "controller-probe",
        "consumer_id": "consumer-probe",
        "proof_kind": "boundary_runtime",
        "witness_kind": "runtime_probe",
        "runner_sha256": runner_digest,
        "consumer_path": "pkg/model.py",
        "caller_object_id": "b" * 40,
        "start_line": 4,
        "column_start": 11,
        "end_line": 4,
        "column_end": 24,
        "match_id": "match-probe",
        "probe": probe,
        "source_event_binding": source_event_binding,
        "expected_event": {"status": "returned"},
    }

    parsed = runner._parse_witnesses(  # pyright: ignore[reportPrivateUsage]
        [witness], runner_digest=runner_digest
    )
    assert parsed[0].source_event_binding == source_event_binding

    missing_binding = copy.deepcopy(witness)
    missing_binding.pop("source_event_binding")
    with pytest.raises(runner.BoundaryProofError) as caught:
        runner._parse_witnesses(  # pyright: ignore[reportPrivateUsage]
            [missing_binding], runner_digest=runner_digest
        )
    assert caught.value.code == "proof_witnesses_invalid"


_TASK2_ACTION_SHA256 = "sha256:" + "a" * 64


def _task2_span(node: ast.AST) -> dict[str, int]:
    assert node.lineno is not None
    assert node.col_offset is not None
    assert node.end_lineno is not None
    assert node.end_col_offset is not None
    return {
        "line_start": node.lineno,
        "column_start": node.col_offset,
        "line_end": node.end_lineno,
        "column_end": node.end_col_offset,
    }


def _task2_git_blob_id(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def _task2_source(
    tmp_path: Path,
    source: str,
) -> tuple[Path, Path, bytes, ast.Module]:
    workspace = (tmp_path / "task2-workspace").resolve()
    path = (workspace / "consumer.py").resolve()
    _write(path, source)
    raw = source.encode("utf-8")
    return workspace, path, raw, ast.parse(source, filename=str(path))


def _task2_binding(event_kind: str) -> dict[str, Any]:
    return {
        "event_kind": event_kind,
        "phase": "residual",
        "attribution": {
            "attribution_kind": "residual_action",
            "action_sha256": _TASK2_ACTION_SHA256,
        },
    }


def _task2_target(
    *,
    witness_id: str,
    raw: bytes,
    span: dict[str, int],
    event_kind: str,
) -> dict[str, Any]:
    return {
        "witness_id": witness_id,
        "consumer_path": "consumer.py",
        "caller_object_id": _task2_git_blob_id(raw),
        "span": copy.deepcopy(span),
        "source_event_binding": _task2_binding(event_kind),
    }


def _task2_observer_module(runner: ModuleType) -> ModuleType:
    source = runner._exact_source_event_observer_source()  # pyright: ignore[reportPrivateUsage]
    assert isinstance(source, str)
    name = "es_exact_source_event_observer_task2"
    module = ModuleType(name)
    module.__file__ = f"<{name}>"
    sys.modules[name] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def _task2_capture(
    observer_module: ModuleType,
    *,
    workspace: Path,
    targets: list[dict[str, Any]],
    action: Any,
) -> dict[str, dict[str, Any]]:
    observer = observer_module.ExactSourceEventObserver(
        workspace=str(workspace),
        targets=targets,
    )
    observer.install()
    try:
        binding = targets[0]["source_event_binding"]
        observer.set_attribution(
            phase=binding["phase"],
            attribution=binding["attribution"],
        )
        action()
    finally:
        observer.uninstall()
    events = observer.source_events()
    assert isinstance(events, dict)
    return events


def test_task2_exact_opcode_event_uses_equal_ast_and_pep657_span(
    tmp_path: Path,
) -> None:
    runner = _runner()
    observer_module = _task2_observer_module(runner)
    source = "def target(value):\n    return value.upper()\n"
    workspace, path, raw, tree = _task2_source(tmp_path, source)
    call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call))
    target = _task2_target(
        witness_id="w-call",
        raw=raw,
        span=_task2_span(call),
        event_kind="opcode_exact_span",
    )
    namespace: dict[str, Any] = {}
    exec(compile(source, str(path), "exec"), namespace)

    events = _task2_capture(
        observer_module,
        workspace=workspace,
        targets=[target],
        action=lambda: namespace["target"]("value"),
    )

    event = events["w-call"]
    assert {
        key: event[key]
        for key in ("event_kind", "phase", "attribution")
    } == target["source_event_binding"]
    assert event["consumer_path"] == target["consumer_path"]
    assert event["caller_object_id"] == target["caller_object_id"]
    assert event["span"] == target["span"]
    assert event["hit_count"] == 1
    payload = event["opcode_exact_span"]
    assert payload["opname"] in {"CALL", "CALL_FUNCTION_EX"}
    instruction = next(
        row
        for row in dis.get_instructions(namespace["target"])
        if row.offset == payload["instruction_offset"]
    )
    assert instruction.positions is not None
    assert {
        "line_start": instruction.positions.lineno,
        "column_start": instruction.positions.col_offset,
        "line_end": instruction.positions.end_lineno,
        "column_end": instruction.positions.end_col_offset,
    } == target["span"]


def test_task2_same_line_calls_and_names_do_not_cross_credit(
    tmp_path: Path,
) -> None:
    runner = _runner()
    observer_module = _task2_observer_module(runner)
    source = (
        "def first(): return 'first'\n"
        "def second(): return 'second'\n"
        "def choose(first_branch):\n"
        "    return first() if first_branch else second()\n"
    )
    workspace, path, raw, tree = _task2_source(tmp_path, source)
    calls = sorted(
        (node for node in ast.walk(tree) if isinstance(node, ast.Call)),
        key=lambda node: node.col_offset,
    )
    assert len(calls) == 2
    targets: list[dict[str, Any]] = []
    for label, call in zip(("first", "second"), calls, strict=True):
        assert isinstance(call.func, ast.Name)
        targets.extend(
            (
                _task2_target(
                    witness_id=f"w-{label}-name",
                    raw=raw,
                    span=_task2_span(call.func),
                    event_kind="opcode_exact_span",
                ),
                _task2_target(
                    witness_id=f"w-{label}-call",
                    raw=raw,
                    span=_task2_span(call),
                    event_kind="opcode_exact_span",
                ),
            )
        )
    namespace: dict[str, Any] = {}
    exec(compile(source, str(path), "exec"), namespace)

    events = _task2_capture(
        observer_module,
        workspace=workspace,
        targets=targets,
        action=lambda: namespace["choose"](True),
    )

    assert set(events) == {"w-first-name", "w-first-call"}


def test_task2_multi_alias_import_does_not_credit_alias_after_failure(
    tmp_path: Path,
) -> None:
    runner = _runner()
    observer_module = _task2_observer_module(runner)
    source = (
        "import json as first_alias, "
        "task2_missing_import as broken_alias, math as later_alias\n"
    )
    workspace, path, raw, tree = _task2_source(tmp_path, source)
    statement = tree.body[0]
    assert isinstance(statement, ast.Import)
    targets = [
        _task2_target(
            witness_id=f"w-import-{ordinal}",
            raw=raw,
            span=_task2_span(alias),
            event_kind="import_alias_opcode",
        )
        for ordinal, alias in enumerate(statement.names)
    ]

    def execute_import() -> None:
        with pytest.raises(ModuleNotFoundError):
            exec(compile(source, str(path), "exec"), {})

    events = _task2_capture(
        observer_module,
        workspace=workspace,
        targets=targets,
        action=execute_import,
    )

    assert set(events) == {"w-import-0", "w-import-1"}
    first = events["w-import-0"]["import_alias_opcode"]
    broken = events["w-import-1"]["import_alias_opcode"]
    assert (first["alias_ordinal"], first["argval"], first["opname"]) == (
        0,
        "json",
        "IMPORT_NAME",
    )
    assert (broken["alias_ordinal"], broken["argval"], broken["opname"]) == (
        1,
        "task2_missing_import",
        "IMPORT_NAME",
    )
    assert first["statement_span"] == _task2_span(statement)
    assert broken["statement_span"] == _task2_span(statement)


@pytest.mark.skipif(
    sys.version_info[:2] != (3, 11),
    reason="observer bytecode contract is pinned to CPython 3.11",
)
def test_task2_import_from_named_aliases_and_star_map_in_source_order_without_cross_credit(
    tmp_path: Path,
) -> None:
    runner = _runner()
    observer_module = _task2_observer_module(runner)
    workspace = (tmp_path / "import-from-workspace").resolve()
    workspace.mkdir()
    package = "task2_import_contract_pkg"
    _write(workspace / package / "__init__.py", "")
    _write(
        workspace / package / "support.py",
        "first = 'first'\nlater = 'later'\n",
    )
    _write(
        workspace / package / "star_source.py",
        "__all__ = ['STAR_VALUE']\nSTAR_VALUE = 'star'\n",
    )
    named_relative = "named_consumer.py"
    named_source = (
        f"from {package}.support import first as first_alias, "
        "missing as missing_alias, later as later_alias\n"
    )
    star_relative = "star_consumer.py"
    star_source = f"from {package}.star_source import *\n"
    sources = (
        (named_relative, named_source),
        (star_relative, star_source),
    )
    targets: list[dict[str, Any]] = []
    statements: dict[str, ast.ImportFrom] = {}
    compiled: dict[str, Any] = {}
    instruction_rows: dict[str, list[Any]] = {}
    for relative, source in sources:
        path = (workspace / relative).resolve()
        _write(path, source)
        raw = source.encode("utf-8")
        tree = ast.parse(source, filename=str(path))
        statement = tree.body[0]
        assert isinstance(statement, ast.ImportFrom)
        statements[relative] = statement
        code = compile(source, str(path), "exec")
        compiled[relative] = code
        instruction_rows[relative] = [
            row
            for row in dis.get_instructions(code)
            if row.opname in {"IMPORT_NAME", "IMPORT_FROM", "IMPORT_STAR"}
        ]
        for ordinal, alias in enumerate(statement.names):
            targets.append(
                _task2_target_with_binding(
                    witness_id=(
                        f"w-named-{ordinal}"
                        if relative == named_relative
                        else "w-star"
                    ),
                    raw=raw,
                    span=_task2_span(alias),
                    event_kind="import_alias_opcode",
                    binding=_task2_binding("import_alias_opcode"),
                    consumer_path=relative,
                )
            )

    assert [
        (row.opname, row.argval) for row in instruction_rows[named_relative]
    ] == [
        ("IMPORT_NAME", f"{package}.support"),
        ("IMPORT_FROM", "first"),
        ("IMPORT_FROM", "missing"),
        ("IMPORT_FROM", "later"),
    ]
    assert [
        (row.opname, row.argval) for row in instruction_rows[star_relative]
    ] == [
        ("IMPORT_NAME", f"{package}.star_source"),
        ("IMPORT_STAR", None),
    ]

    observer = observer_module.ExactSourceEventObserver(
        workspace=str(workspace),
        targets=targets,
    )
    observer.install()
    sys.path.insert(0, str(workspace))
    try:
        binding = targets[0]["source_event_binding"]
        observer.set_attribution(
            phase=binding["phase"],
            attribution=binding["attribution"],
        )
        with pytest.raises(ImportError):
            exec(compiled[named_relative], {})
        exec(compiled[star_relative], {})
    finally:
        sys.path.remove(str(workspace))
        observer.uninstall()
        for module_name in tuple(sys.modules):
            if module_name == package or module_name.startswith(package + "."):
                sys.modules.pop(module_name, None)

    events = observer.source_events()
    assert list(events) == ["w-named-0", "w-named-1", "w-star"]
    assert "w-named-2" not in events
    named_statement_span = _task2_span(statements[named_relative])
    star_statement_span = _task2_span(statements[star_relative])
    expected_payloads = {
        "w-named-0": {
            "alias_ordinal": 0,
            "module": f"{package}.support",
            "name": "first",
            "asname": "first_alias",
            "level": 0,
            "opname": "IMPORT_FROM",
            "argval": "first",
            "statement_span": named_statement_span,
        },
        "w-named-1": {
            "alias_ordinal": 1,
            "module": f"{package}.support",
            "name": "missing",
            "asname": "missing_alias",
            "level": 0,
            "opname": "IMPORT_FROM",
            "argval": "missing",
            "statement_span": named_statement_span,
        },
        "w-star": {
            "alias_ordinal": 0,
            "module": f"{package}.star_source",
            "name": "*",
            "asname": None,
            "level": 0,
            "opname": "IMPORT_STAR",
            "argval": "*",
            "statement_span": star_statement_span,
        },
    }
    for witness_id, expected in expected_payloads.items():
        payload = events[witness_id]["import_alias_opcode"]
        assert {key: payload[key] for key in expected} == expected
        instructions = instruction_rows[
            named_relative if witness_id.startswith("w-named") else star_relative
        ]
        import_name = instructions[0]
        alias_instruction = next(
            row for row in instructions if row.offset == payload["instruction_offset"]
        )
        assert import_name.opname == "IMPORT_NAME"
        assert import_name.offset < alias_instruction.offset


def test_task2_ambiguous_import_instruction_mapping_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    source = "import json as alias\n"
    workspace, _, raw, tree = _task2_source(tmp_path, source)
    statement = tree.body[0]
    assert isinstance(statement, ast.Import)
    target = _task2_target(
        witness_id="w-import",
        raw=raw,
        span=_task2_span(statement.names[0]),
        event_kind="import_alias_opcode",
    )
    real_get_instructions = dis.get_instructions

    def ambiguous_instructions(code: Any, *args: Any, **kwargs: Any) -> Any:
        rows = list(real_get_instructions(code, *args, **kwargs))
        for index, row in enumerate(rows):
            if row.opname == "IMPORT_NAME":
                rows.insert(index + 1, row._replace(offset=row.offset + 1_000))
                break
        return iter(rows)

    monkeypatch.setattr(dis, "get_instructions", ambiguous_instructions)
    observer_module = _task2_observer_module(runner)

    with pytest.raises(observer_module.SourceEventObserverError) as caught:
        observer_module.ExactSourceEventObserver(
            workspace=str(workspace),
            targets=[target],
        )

    assert caught.value.code == "proof_source_event_import_mapping_ambiguous"


def test_task2_postponed_annotations_have_no_runtime_source_event(
    tmp_path: Path,
) -> None:
    runner = _runner()
    observer_module = _task2_observer_module(runner)
    source = (
        "from __future__ import annotations\n"
        "def annotated(value: MissingAnnotation) -> ReturnedAnnotation:\n"
        "    return value\n"
    )
    workspace, path, raw, tree = _task2_source(tmp_path, source)
    annotations = sorted(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and node.id in {"MissingAnnotation", "ReturnedAnnotation"}
        ),
        key=lambda node: node.col_offset,
    )
    assert len(annotations) == 2
    targets = [
        _task2_target(
            witness_id=f"w-annotation-{ordinal}",
            raw=raw,
            span=_task2_span(node),
            event_kind="opcode_exact_span",
        )
        for ordinal, node in enumerate(annotations)
    ]

    events = _task2_capture(
        observer_module,
        workspace=workspace,
        targets=targets,
        action=lambda: exec(compile(source, str(path), "exec"), {}),
    )

    assert events == {}


def test_task2_callable_entry_is_credited_on_call_not_definition(
    tmp_path: Path,
) -> None:
    runner = _runner()
    observer_module = _task2_observer_module(runner)
    source = "def regex_detector(value):\n    return value\n"
    workspace, path, raw, tree = _task2_source(tmp_path, source)
    definition = tree.body[0]
    assert isinstance(definition, ast.FunctionDef)
    name_start = source.encode("utf-8").index(b"regex_detector")
    name_span = {
        "line_start": 1,
        "column_start": name_start,
        "line_end": 1,
        "column_end": name_start + len(b"regex_detector"),
    }
    target = _task2_target(
        witness_id="w-callable",
        raw=raw,
        span=name_span,
        event_kind="callable_entry",
    )
    observer = observer_module.ExactSourceEventObserver(
        workspace=str(workspace),
        targets=[target],
    )
    namespace: dict[str, Any] = {}
    observer.install()
    try:
        binding = target["source_event_binding"]
        observer.set_attribution(
            phase=binding["phase"],
            attribution=binding["attribution"],
        )
        exec(compile(source, str(path), "exec"), namespace)
        assert observer.source_events() == {}
        namespace["regex_detector"]("value")
    finally:
        observer.uninstall()

    event = observer.source_events()["w-callable"]
    payload = event["callable_entry"]
    assert payload["code_name"] == "regex_detector"
    assert payload["code_qualname"] == "regex_detector"
    assert payload["code_firstlineno"] == 1
    assert payload["definition_span"] == _task2_span(definition)


def test_task2_missing_pep657_positions_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    source = "def target(value):\n    return value.upper()\n"
    workspace, _, raw, tree = _task2_source(tmp_path, source)
    call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call))
    target = _task2_target(
        witness_id="w-call",
        raw=raw,
        span=_task2_span(call),
        event_kind="opcode_exact_span",
    )
    real_get_instructions = dis.get_instructions

    def instructions_without_positions(
        code: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return iter(
            row._replace(positions=dis.Positions(None, None, None, None))
            if row.opname == "CALL"
            else row
            for row in real_get_instructions(code, *args, **kwargs)
        )

    monkeypatch.setattr(dis, "get_instructions", instructions_without_positions)
    observer_module = _task2_observer_module(runner)

    with pytest.raises(observer_module.SourceEventObserverError) as caught:
        observer_module.ExactSourceEventObserver(
            workspace=str(workspace),
            targets=[target],
        )

    assert caught.value.code == "proof_source_event_position_missing"


def test_task2_unsupported_ast_opcode_mapping_fails_closed(
    tmp_path: Path,
) -> None:
    runner = _runner()
    observer_module = _task2_observer_module(runner)
    source = "def target(value):\n    return value + 1\n"
    workspace, _, raw, tree = _task2_source(tmp_path, source)
    binary = next(node for node in ast.walk(tree) if isinstance(node, ast.BinOp))
    target = _task2_target(
        witness_id="w-binary",
        raw=raw,
        span=_task2_span(binary),
        event_kind="opcode_exact_span",
    )

    with pytest.raises(observer_module.SourceEventObserverError) as caught:
        observer_module.ExactSourceEventObserver(
            workspace=str(workspace),
            targets=[target],
        )

    assert caught.value.code == "proof_source_event_opcode_unsupported"


def _task2_target_with_binding(
    *,
    witness_id: str,
    raw: bytes,
    span: dict[str, int],
    event_kind: str,
    binding: dict[str, Any],
    consumer_path: str = "consumer.py",
) -> dict[str, Any]:
    target = _task2_target(
        witness_id=witness_id,
        raw=raw,
        span=span,
        event_kind=event_kind,
    )
    target["consumer_path"] = consumer_path
    target["source_event_binding"] = copy.deepcopy(binding)
    return target


def _task2_record_wrapper_observer_binding(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    *,
    substitute_report_lane: str | None = None,
) -> list[dict[str, Any]]:
    expected_source = runner._exact_source_event_observer_source().encode(  # pyright: ignore[reportPrivateUsage]
        "utf-8"
    )
    expected_digest = runner._exact_source_event_observer_sha256()  # pyright: ignore[reportPrivateUsage]
    real_run = runner.subprocess.run
    observations: list[dict[str, Any]] = []

    def recording_run(argv: Any, *args: Any, **kwargs: Any) -> Any:
        env = kwargs.get("env")
        if not isinstance(env, dict):
            return real_run(argv, *args, **kwargs)
        if "ES_BOUNDARY_CONFIG" in env:
            lane = "pytest"
            config_path = Path(env["ES_BOUNDARY_CONFIG"])
            report_path = Path(env["ES_BOUNDARY_REPORT"])
        elif "ES_BOUNDARY_RUNTIME_CONFIG" in env:
            lane = "residual"
            config_path = Path(env["ES_BOUNDARY_RUNTIME_CONFIG"])
            report_path = Path(env["ES_BOUNDARY_RUNTIME_RESULT"])
        else:
            return real_run(argv, *args, **kwargs)

        config = json.loads(config_path.read_text(encoding="utf-8"))
        assert config["source_event_observer_sha256"] == expected_digest
        artifact_paths = [
            path
            for path in config_path.parent.iterdir()
            if path.is_file() and path.read_bytes() == expected_source
        ]
        assert len(artifact_paths) == 1

        completed = real_run(argv, *args, **kwargs)
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            assert report["source_event_observer_sha256"] == expected_digest
            observations.append(
                {
                    "artifact_raw": artifact_paths[0].read_bytes(),
                    "config_digest": config["source_event_observer_sha256"],
                    "lane": lane,
                    "report_digest": report["source_event_observer_sha256"],
                }
            )
            if lane == substitute_report_lane:
                report["source_event_observer_sha256"] = "sha256:" + "0" * 64
                report_path.write_bytes(runner.canonical_json_bytes(report))
        return completed

    monkeypatch.setattr(runner.subprocess, "run", recording_run)
    return observations


def test_task2_direct_observer_attributes_module_and_class_body_phases(
    tmp_path: Path,
) -> None:
    runner = _runner()
    observer_module = _task2_observer_module(runner)
    workspace = (tmp_path / "phase-workspace").resolve()
    workspace.mkdir()
    cases = (
        (
            "bootstrap",
            "bootstrap_module.py",
            'BOOTSTRAP_MARKER = "bootstrap"\n',
            "bootstrap",
        ),
        (
            "collection",
            "collection_module.py",
            'class Collected:\n    MARKER = "collection"\n',
            "collection",
        ),
    )
    targets: list[dict[str, Any]] = []
    compiled: list[tuple[str, Path, Any, dict[str, Any]]] = []
    for witness_id, relative, source, phase in cases:
        path = (workspace / relative).resolve()
        _write(path, source)
        raw = source.encode("utf-8")
        tree = ast.parse(source, filename=str(path))
        marker = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and node.value == phase
        )
        binding = {
            "event_kind": "opcode_exact_span",
            "phase": phase,
            "attribution": {
                "attribution_kind": "selector_module",
                "pytest_module_path": relative,
            },
        }
        targets.append(
            _task2_target_with_binding(
                witness_id=f"w-{witness_id}",
                raw=raw,
                span=_task2_span(marker),
                event_kind="opcode_exact_span",
                binding=binding,
                consumer_path=relative,
            )
        )
        compiled.append((phase, path, compile(source, str(path), "exec"), binding))

    observer = observer_module.ExactSourceEventObserver(
        workspace=str(workspace),
        targets=targets,
    )
    observer.install()
    try:
        for phase, _, code, binding in compiled:
            observer.set_attribution(
                phase=phase,
                attribution=binding["attribution"],
            )
            exec(code, {"__name__": f"task2_{phase}"})
    finally:
        observer.uninstall()

    events = observer.source_events()
    assert set(events) == {"w-bootstrap", "w-collection"}
    for target in targets:
        event = events[target["witness_id"]]
        assert {
            key: event[key] for key in ("event_kind", "phase", "attribution")
        } == target["source_event_binding"]
        assert event["opcode_exact_span"]["opname"] == "LOAD_CONST"


def test_task2_observer_auto_bootstrap_requires_matching_selector_module_path(
    tmp_path: Path,
) -> None:
    runner = _runner()
    observer_module = _task2_observer_module(runner)
    workspace = (tmp_path / "auto-bootstrap-workspace").resolve()
    workspace.mkdir()
    cases = (
        (
            "w-bootstrap-matching",
            "matching_module.py",
            'MARKER = "matching"\n',
            "matching_module.py",
        ),
        (
            "w-bootstrap-different",
            "different_module.py",
            'MARKER = "different"\n',
            "another_module.py",
        ),
    )
    targets: list[dict[str, Any]] = []
    compiled: list[Any] = []
    for witness_id, relative, source, bound_module in cases:
        path = (workspace / relative).resolve()
        _write(path, source)
        raw = source.encode("utf-8")
        marker = next(
            node
            for node in ast.walk(ast.parse(source, filename=str(path)))
            if isinstance(node, ast.Constant)
        )
        targets.append(
            _task2_target_with_binding(
                witness_id=witness_id,
                raw=raw,
                span=_task2_span(marker),
                event_kind="opcode_exact_span",
                binding={
                    "event_kind": "opcode_exact_span",
                    "phase": "bootstrap",
                    "attribution": {
                        "attribution_kind": "selector_module",
                        "pytest_module_path": bound_module,
                    },
                },
                consumer_path=relative,
            )
        )
        compiled.append(compile(source, str(path), "exec"))

    observer = observer_module.ExactSourceEventObserver(
        workspace=str(workspace),
        targets=targets,
    )
    observer.install()
    try:
        for code in compiled:
            exec(code, {})
    finally:
        observer.uninstall()

    events = observer.source_events()
    assert set(events) == {"w-bootstrap-matching"}
    assert events["w-bootstrap-matching"]["attribution"] == {
        "attribution_kind": "selector_module",
        "pytest_module_path": "matching_module.py",
    }


def test_task2_direct_observer_tracks_exact_pytest_phases_without_node_cross_credit(
    tmp_path: Path,
) -> None:
    runner = _runner()
    observer_module = _task2_observer_module(runner)
    source = (
        "def setup_driver(): return sink('setup')\n"
        "def call_driver(): return sink('call')\n"
        "def teardown_driver(): return sink('teardown')\n"
        "def other_driver(): return sink('other')\n"
    )
    workspace, path, raw, tree = _task2_source(tmp_path, source)
    calls = {
        node.args[0].value: node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    selected_node = "tests/test_lifecycle.py::test_selected"
    other_node = "tests/test_lifecycle.py::test_other"
    targets: list[dict[str, Any]] = []
    for phase in ("setup", "call", "teardown"):
        binding = {
            "event_kind": "opcode_exact_span",
            "phase": phase,
            "attribution": {
                "attribution_kind": "pytest_node",
                "pytest_node_id": selected_node,
            },
        }
        targets.append(
            _task2_target_with_binding(
                witness_id=f"w-{phase}",
                raw=raw,
                span=_task2_span(calls[phase]),
                event_kind="opcode_exact_span",
                binding=binding,
            )
        )
    targets.append(
        _task2_target_with_binding(
            witness_id="w-other-node",
            raw=raw,
            span=_task2_span(calls["other"]),
            event_kind="opcode_exact_span",
            binding={
                "event_kind": "opcode_exact_span",
                "phase": "call",
                "attribution": {
                    "attribution_kind": "pytest_node",
                    "pytest_node_id": other_node,
                },
            },
        )
    )
    namespace = {"sink": lambda value: value}
    exec(compile(source, str(path), "exec"), namespace)
    observer = observer_module.ExactSourceEventObserver(
        workspace=str(workspace),
        targets=targets,
    )
    observer.install()
    try:
        for phase in ("setup", "call", "teardown"):
            observer.set_attribution(
                phase=phase,
                attribution={
                    "attribution_kind": "pytest_node",
                    "pytest_node_id": selected_node,
                },
            )
            namespace[f"{phase}_driver"]()
        observer.set_attribution(
            phase="call",
            attribution={
                "attribution_kind": "pytest_node",
                "pytest_node_id": selected_node,
            },
        )
        namespace["other_driver"]()
    finally:
        observer.uninstall()

    events = observer.source_events()
    assert set(events) == {"w-setup", "w-call", "w-teardown"}
    assert [events[f"w-{phase}"]["phase"] for phase in ("setup", "call", "teardown")] == [
        "setup",
        "call",
        "teardown",
    ]


def test_task2_residual_import_action_observes_source_before_module_import(
    contract_fixture: ContractFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    observations = _task2_record_wrapper_observer_binding(runner, monkeypatch)
    relative = "pkg/import_observed.py"
    source = 'IMPORT_MARKER = "observed-during-import"\n'
    path = contract_fixture.workspace / relative
    _write(path, source)
    _commit(contract_fixture.workspace, "add import-observed module")
    raw = source.encode("utf-8")
    marker = next(
        node
        for node in ast.walk(ast.parse(source, filename=str(path)))
        if isinstance(node, ast.Constant) and node.value == "observed-during-import"
    )
    probe = {
        "action": "import_module",
        "module": "pkg.import_observed",
        "expected_outcome": {"status": "returned"},
    }
    binding = {
        "event_kind": "opcode_exact_span",
        "phase": "residual",
        "attribution": {
            "attribution_kind": "residual_action",
            "action_sha256": _sha256(runner.canonical_json_bytes(probe)),
        },
    }
    span = _task2_span(marker)
    witness = runner.WitnessContract(
        witness_id="w-import-observed",
        selector_id="controller-runtime",
        consumer_id="consumer-import-observed",
        proof_kind="boundary_runtime",
        witness_kind="runtime_probe",
        consumer_path=relative,
        caller_object_id=_task2_git_blob_id(raw),
        start_line=span["line_start"],
        column_start=span["column_start"],
        end_line=span["line_end"],
        column_end=span["column_end"],
        match_id="match-import-observed",
        expected_result={},
        source_event_binding=binding,
        probe=probe,
    )

    event, blob = runner._runtime_observation(  # pyright: ignore[reportPrivateUsage]
        witness,
        python=PINNED_PYTHON,
        workspace=contract_fixture.workspace,
        forbidden_roots=(),
        project_owned_module_prefixes=("pkg",),
    )

    assert blob == witness.caller_object_id
    assert {
        key: event[key] for key in ("event_kind", "phase", "attribution")
    } == binding
    assert event["opcode_exact_span"]["opname"] == "LOAD_CONST"
    assert observations == [
        {
            "artifact_raw": runner._exact_source_event_observer_source().encode(  # pyright: ignore[reportPrivateUsage]
                "utf-8"
            ),
            "config_digest": runner._exact_source_event_observer_sha256(),  # pyright: ignore[reportPrivateUsage]
            "lane": "residual",
            "report_digest": runner._exact_source_event_observer_sha256(),  # pyright: ignore[reportPrivateUsage]
        }
    ]


def _task2_one_node_provider_contract(
    runner: ModuleType,
    workspace: Path,
) -> Any:
    relative = "pkg/provider_target.py"
    source = "def observed():\n    return 'ok'\n"
    target_path = workspace / relative
    test_relative = "tests/test_provider_observer.py"
    _write(workspace / "pkg/__init__.py", "")
    _write(target_path, source)
    _write(
        workspace / test_relative,
        "from pkg.provider_target import observed\n\n"
        "def test_observed():\n"
        "    assert observed() == 'ok'\n",
    )
    name_start = source.encode("utf-8").index(b"observed")
    node_id = f"{test_relative}::test_observed"
    binding = {
        "event_kind": "callable_entry",
        "phase": "call",
        "attribution": {
            "attribution_kind": "pytest_node",
            "pytest_node_id": node_id,
        },
    }
    witness = runner.WitnessContract(
        witness_id="w-provider-observed",
        selector_id="provider-observed",
        consumer_id="consumer-provider-observed",
        proof_kind="boundary_runtime",
        witness_kind="pytest_runtime",
        consumer_path=relative,
        caller_object_id=_task2_git_blob_id(source.encode("utf-8")),
        start_line=1,
        column_start=name_start,
        end_line=1,
        column_end=name_start + len(b"observed"),
        match_id="match-provider-observed",
        expected_result={},
        source_event_binding=binding,
        pytest_node_id=node_id,
    )
    selector = runner.SelectorContract(
        selector_id="provider-observed",
        ordinal=1,
        lane="provider_visible_pytest",
        proof_kind="boundary_runtime",
        coverage_witness_ids=(witness.witness_id,),
        pytest_module_path=test_relative,
        pytest_node_ids=(node_id,),
    )
    return runner.ProofContract(
        provider_selectors=(selector,),
        controller_selectors=(),
        witnesses=(witness,),
        desired_specs=(),
        consumers=(),
        runner_sha256=runner.runner_sha256(),
    )


def test_task2_generated_observer_artifact_and_wrapper_digests_are_bound(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    source_raw = runner._exact_source_event_observer_source().encode(  # pyright: ignore[reportPrivateUsage]
        "utf-8"
    )
    expected = runner._exact_source_event_observer_sha256()  # pyright: ignore[reportPrivateUsage]
    assert expected == _sha256(source_raw)
    for name in ("first.py", "second.py"):
        artifact = (tmp_path / name).resolve()
        assert runner._write_exact_source_event_observer(artifact) == expected  # pyright: ignore[reportPrivateUsage]
        assert artifact.read_bytes() == source_raw

    workspace = (tmp_path / "provider-workspace").resolve()
    workspace.mkdir()
    contract = _task2_one_node_provider_contract(runner, workspace)
    observations = _task2_record_wrapper_observer_binding(
        runner,
        monkeypatch,
        substitute_report_lane="pytest",
    )
    with pytest.raises(runner.BoundaryProofError) as caught:
        runner._run_pytest_observation(  # pyright: ignore[reportPrivateUsage]
            contract,
            python=PINNED_PYTHON,
            workspace=workspace,
            report_path=(tmp_path / "provider-observation.json").resolve(),
            forbidden_roots=(),
            pytest_carrier=_verified_pytest_carrier(runner),
        )

    assert observations[0]["artifact_raw"] == source_raw
    assert observations[0]["config_digest"] == expected
    assert observations[0]["report_digest"] == expected
    assert caught.value.code == "proof_source_event_observer_digest_mismatch"


@pytest.mark.parametrize("raised", (False, True))
def test_task2_observer_restores_existing_trace_hooks(
    tmp_path: Path,
    raised: bool,
) -> None:
    runner = _runner()
    observer_module = _task2_observer_module(runner)
    source = "def target():\n    return 'ok'\n"
    workspace, _, raw, tree = _task2_source(tmp_path, source)
    definition = tree.body[0]
    assert isinstance(definition, ast.FunctionDef)
    name_start = source.encode("utf-8").index(b"target")
    target = _task2_target(
        witness_id="w-hook-restoration",
        raw=raw,
        span={
            "line_start": 1,
            "column_start": name_start,
            "line_end": 1,
            "column_end": name_start + len(b"target"),
        },
        event_kind="callable_entry",
    )
    original_sys_trace = sys.gettrace()
    original_thread_trace = threading.gettrace()

    def prior_sys_trace(frame: Any, event: str, arg: Any) -> Any:
        return prior_sys_trace

    def prior_thread_trace(frame: Any, event: str, arg: Any) -> Any:
        return prior_thread_trace

    sys.settrace(prior_sys_trace)
    threading.settrace(prior_thread_trace)
    try:
        observer = observer_module.ExactSourceEventObserver(
            workspace=str(workspace),
            targets=[target],
        )
        observer.install()
        try:
            if raised:
                raise RuntimeError("task2 action failed")
        except RuntimeError:
            assert raised
        finally:
            observer.uninstall()
        assert sys.gettrace() is prior_sys_trace
        assert threading.gettrace() is prior_thread_trace
    finally:
        sys.settrace(original_sys_trace)
        threading.settrace(original_thread_trace)
