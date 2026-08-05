from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator, ValidationError


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPOSITORY_ROOT / "scripts/experiments/es/feasibility_proofs.py"


def _runner() -> ModuleType:
    assert RUNNER_PATH.is_file(), "Task-0 feasibility proof runner is not implemented"
    spec = importlib.util.spec_from_file_location("es_feasibility_proofs", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _tool_environment() -> dict[str, str]:
    return {
        "HOME": "/",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }


def _live_executable_binding(
    literal_path: Path,
    *version_args: str,
) -> dict[str, object]:
    literal = Path(literal_path)
    real = literal.resolve(strict=True)
    completed = subprocess.run(
        (str(literal), *version_args),
        cwd=Path("/"),
        env=_tool_environment(),
        check=False,
        shell=False,
        timeout=5,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert completed.returncode == 0
    return {
        "literal_path": str(literal),
        "real_path": str(real),
        "sha256": _sha256(real.read_bytes()),
        "version_argv": [str(literal), *version_args],
        "version_output": completed.stdout.decode("utf-8", "strict"),
    }


def _git(
    git_path: Path,
    *args: str,
    input_bytes: bytes | None = None,
) -> bytes:
    completed = subprocess.run(
        (str(git_path), *args),
        cwd=Path("/"),
        env=_tool_environment(),
        check=False,
        shell=False,
        timeout=5,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    return completed.stdout


def _bare_object_fixture(
    tmp_path: Path,
    *,
    blob_payload: bytes = b"fixture payload\n",
) -> tuple[Path, str, bytes, str, bytes]:
    git_path = Path("/usr/bin/git")
    repository = (tmp_path / "objects.git").resolve()
    _git(git_path, "init", "--bare", str(repository))
    blob_oid = _git(
        git_path,
        "--git-dir",
        str(repository),
        "hash-object",
        "-w",
        "--stdin",
        input_bytes=blob_payload,
    ).decode("ascii").strip()
    tree_input = f"100644 blob {blob_oid}\tfixture.txt\n".encode("ascii")
    tree_oid = _git(
        git_path,
        "--git-dir",
        str(repository),
        "mktree",
        input_bytes=tree_input,
    ).decode("ascii").strip()
    tree_payload = b"100644 fixture.txt\0" + bytes.fromhex(blob_oid)
    return repository, blob_oid, blob_payload, tree_oid, tree_payload


def _write_git_object(repository: Path, object_type: str, payload: bytes) -> str:
    return _git(
        Path("/usr/bin/git"),
        "--git-dir",
        str(repository),
        "hash-object",
        "-t",
        object_type,
        "-w",
        "--stdin",
        input_bytes=payload,
    ).decode("ascii").strip()


def _pytest_ledger_fixture(
    runner: ModuleType,
    *,
    elapsed_ns: int = 1_000_000,
) -> object:
    project_root = "/tmp/es-feasibility-project"
    node_id = "tests/test_feature.py::test_cross_cluster"
    git = runner.ExecutableIdentity(
        literal_path="/usr/bin/git",
        real_path="/usr/bin/git",
        sha256="sha256:" + "1" * 64,
        version_argv=("/usr/bin/git", "--version"),
        version_output="git version fixture\n",
    )
    python = runner.ExecutableIdentity(
        literal_path="/opt/ptycho311/bin/python",
        real_path="/opt/ptycho311/bin/python3.11",
        sha256="sha256:" + "2" * 64,
        version_argv=("/opt/ptycho311/bin/python", "--version"),
        version_output="Python 3.11 fixture\n",
    )
    return runner.PytestExecutionLedger(
        ledger_id="green:0",
        ordinal=2,
        role="green",
        role_index=0,
        slice_id=None,
        runner_sha256="sha256:" + "3" * 64,
        git=git,
        python=python,
        variant_id="full",
        project_root=project_root,
        cwd=project_root,
        argv=(python.literal_path, "-m", "pytest", "-q", "tests"),
        execution_envelope=runner.PytestExecutionEnvelope(
            kind="direct",
            launcher=None,
            launcher_argv=(python.literal_path, "-m", "pytest", "-q", "tests"),
            runtime_project_root=project_root,
            home_root=None,
            tmp_root=None,
            writable_mounts=(),
        ),
        environment=(
            ("CUDA_VISIBLE_DEVICES", ""),
            ("LANG", "C"),
            ("LC_ALL", "C"),
            ("PATH", "/usr/bin:/bin"),
            ("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1"),
            ("PYTHONDONTWRITEBYTECODE", "1"),
            ("PYTHONHASHSEED", "0"),
            ("PYTHONNOUSERSITE", "1"),
        ),
        expected_tree="4" * 40,
        pre_tree="4" * 40,
        post_tree="4" * 40,
        collected_node_ids=(node_id,),
        node_outcomes=(runner.NodeOutcome(node_id, "passed", None),),
        outcome_counts=runner.OutcomeCounts(
            passed=1,
            failed=0,
            skipped=0,
            errors=0,
        ),
        exit_code=0,
        project_origins=(
            runner.ProjectOrigin(
                module_name="pkg.feature",
                resolved_path=f"{project_root}/pkg/feature.py",
            ),
        ),
        call_transitions=(
            runner.CallTransition(
                edge_id="edge-feature",
                pytest_node_id=node_id,
                outcome="passed",
                caller_path="pkg/consumer.py",
                caller_line=8,
                callee_path="pkg/feature.py",
                callee_name="feature",
                callee_first_line=3,
                callee_line_hits=(3, 4),
            ),
        ),
        elapsed_ns=elapsed_ns,
    )


def _pytest_capture_project(tmp_path: Path) -> Path:
    project = (tmp_path / "capture-project").resolve()
    (project / "pkg").mkdir(parents=True)
    (project / "tests").mkdir()
    (project / "pkg/__init__.py").write_text("", encoding="utf-8")
    (project / "pkg/producer.py").write_text(
        "def produce(value):\n"
        "    doubled = value * 2\n"
        "    return doubled\n",
        encoding="utf-8",
    )
    (project / "pkg/consumer.py").write_text(
        "from pkg.producer import produce\n"
        "\n"
        "def consume(value):\n"
        "    return produce(value)\n",
        encoding="utf-8",
    )
    (project / "tests/test_spine.py").write_text(
        "import pytest\n"
        "\n"
        "from pkg.consumer import consume\n"
        "\n"
        "\n"
        "def test_first():\n"
        "    assert consume(2) == 4\n"
        "\n"
        "\n"
        "def test_second():\n"
        "    pytest.skip('fixture skip')\n",
        encoding="utf-8",
    )
    return project


def _capture_bindings() -> tuple[dict[str, object], dict[str, object]]:
    return (
        _live_executable_binding(Path("/usr/bin/git"), "--version"),
        _live_executable_binding(Path(sys.executable), "--version"),
    )


def _capture_origins(runner: ModuleType, project: Path) -> tuple[object, ...]:
    return (
        runner.ProjectOrigin("pkg", str(project / "pkg/__init__.py")),
        runner.ProjectOrigin("pkg.consumer", str(project / "pkg/consumer.py")),
        runner.ProjectOrigin("pkg.producer", str(project / "pkg/producer.py")),
        runner.ProjectOrigin("test_spine", str(project / "tests/test_spine.py")),
    )


def _capture_call(
    runner: ModuleType,
    project: Path,
    *,
    role: str = "green",
    pytest_args: tuple[str, ...] = (
        "-q",
        "-p",
        "no:cacheprovider",
        "tests/test_spine.py",
    ),
    expected_tree: str | None = None,
    expected_origins: tuple[object, ...] | None = None,
    bwrap_binding: dict[str, object] | None = None,
    writable_mounts: tuple[object, ...] = (),
    sandbox_home_root: Path | None = None,
    sandbox_tmp_root: Path | None = None,
    include_trace: bool = True,
) -> dict[str, object]:
    git_binding, python_binding = _capture_bindings()
    tree_oid = (
        runner.snapshot_project_tree_oid(project)
        if expected_tree is None
        else expected_tree
    )
    return runner.capture_pytest_execution_ledger(
        ledger_id=f"{role}:0",
        ordinal=0,
        role=role,
        role_index=0,
        slice_id="fixture-slice" if role in {"baseline", "remove_one"} else None,
        runner_path=RUNNER_PATH,
        git_binding=git_binding,
        python_binding=python_binding,
        variant_id="fixture",
        project_root=project,
        expected_tree=tree_oid,
        pytest_args=pytest_args,
        expected_project_origins=(
            _capture_origins(runner, project)
            if expected_origins is None
            else expected_origins
        ),
        call_trace_specs=(
            runner.CallTraceSpec(
                edge_id="edge-produce",
                pytest_node_id="tests/test_spine.py::test_first",
                caller_path="pkg/consumer.py",
                caller_line=4,
                callee_path="pkg/producer.py",
                callee_name="produce",
                callee_first_line=1,
            ),
        ) if role != "collection" and include_trace else (),
        bwrap_binding=bwrap_binding,
        writable_mounts=writable_mounts,
        sandbox_home_root=sandbox_home_root,
        sandbox_tmp_root=sandbox_tmp_root,
        timeout_seconds=30,
    )


def test_writable_mount_snapshot_accepts_empty_root(tmp_path: Path) -> None:
    runner = _runner()
    writable_root = (tmp_path / "empty-writable-root").resolve()
    writable_root.mkdir()

    assert runner.snapshot_writable_mount_tree_oid(writable_root) == (
        "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    )


def test_writable_mount_snapshot_matches_nonempty_project_tree(
    tmp_path: Path,
) -> None:
    runner = _runner()
    writable_root = (tmp_path / "nonempty-writable-root").resolve()
    writable_root.mkdir()
    (writable_root / "result.txt").write_text("captured\n", encoding="utf-8")

    assert runner.snapshot_writable_mount_tree_oid(
        writable_root
    ) == runner.snapshot_project_tree_oid(writable_root)


def test_pytest_capture_runner_records_exact_process_observations(
    tmp_path: Path,
) -> None:
    runner = _runner()
    project = _pytest_capture_project(tmp_path)

    record = _capture_call(runner, project)

    assert runner.validate_pytest_execution_ledger_record(record) == record
    assert record["argv"] == [
        str(Path(sys.executable)),
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "tests/test_spine.py",
    ]
    environment = dict(record["environment"])
    assert environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["CUDA_VISIBLE_DEVICES"] == ""
    assert record["collected_node_ids"] == [
        "tests/test_spine.py::test_first",
        "tests/test_spine.py::test_second",
    ]
    assert record["node_outcomes"] == [
        {
            "node_id": "tests/test_spine.py::test_first",
            "outcome": "passed",
            "failure_phase": None,
        },
        {
            "node_id": "tests/test_spine.py::test_second",
            "outcome": "skipped",
            "failure_phase": None,
        },
    ]
    assert record["outcome_counts"] == {
        "passed": 1,
        "failed": 0,
        "skipped": 1,
        "errors": 0,
    }
    assert record["exit_code"] == 0
    assert record["pre_tree"] == record["expected_tree"] == record["post_tree"]
    assert record["project_origins"] == [
        {"module_name": row.module_name, "resolved_path": row.resolved_path}
        for row in _capture_origins(runner, project)
    ]
    assert record["call_transitions"] == [
        {
            "edge_id": "edge-produce",
            "pytest_node_id": "tests/test_spine.py::test_first",
            "outcome": "passed",
            "caller_path": "pkg/consumer.py",
            "caller_line": 4,
            "callee_path": "pkg/producer.py",
            "callee_name": "produce",
            "callee_first_line": 1,
            "callee_line_hits": [2, 3],
        }
    ]
    assert type(record["elapsed_ns"]) is int and record["elapsed_ns"] > 0


def test_pytest_capture_runner_records_collection_without_terminal_outcomes(
    tmp_path: Path,
) -> None:
    runner = _runner()
    project = _pytest_capture_project(tmp_path)

    record = _capture_call(
        runner,
        project,
        role="collection",
        pytest_args=(
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/test_spine.py",
        ),
    )

    assert record["collected_node_ids"] == [
        "tests/test_spine.py::test_first",
        "tests/test_spine.py::test_second",
    ]
    assert record["node_outcomes"] == []
    assert record["outcome_counts"] == {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
    }
    assert record["call_transitions"] == []


def test_pytest_capture_runner_records_call_phase_failure(
    tmp_path: Path,
) -> None:
    runner = _runner()
    project = _pytest_capture_project(tmp_path)
    (project / "tests/test_spine.py").write_text(
        (project / "tests/test_spine.py").read_text(encoding="utf-8")
        + "\n\ndef test_expected_failure():\n"
        + "    assert False, 'expected fixture failure'\n",
        encoding="utf-8",
    )

    record = _capture_call(
        runner,
        project,
        role="baseline",
        pytest_args=(
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/test_spine.py::test_expected_failure",
        ),
        include_trace=False,
    )

    assert record["exit_code"] == 1
    assert record["node_outcomes"] == [
        {
            "node_id": "tests/test_spine.py::test_expected_failure",
            "outcome": "failed",
            "failure_phase": "call",
        }
    ]
    assert record["outcome_counts"] == {
        "passed": 0,
        "failed": 1,
        "skipped": 0,
        "errors": 0,
    }


def test_pytest_capture_runner_fails_closed_when_pytest_cannot_start(
    tmp_path: Path,
) -> None:
    runner = _runner()
    project = _pytest_capture_project(tmp_path)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        _capture_call(
            runner,
            project,
            pytest_args=(
                "-q",
                "-p",
                "no:cacheprovider",
                "--definitely-not-a-pytest-option",
            ),
            include_trace=False,
        )

    assert caught.value.code == "feasibility_pytest_capture_invalid"
    assert caught.value.detail in {"process", "worker_response"}


def test_pytest_capture_runner_fails_closed_on_project_tree_mutation(
    tmp_path: Path,
) -> None:
    runner = _runner()
    project = _pytest_capture_project(tmp_path)
    (project / "tests/test_spine.py").write_text(
        (project / "tests/test_spine.py").read_text(encoding="utf-8")
        + "\n\ndef test_mutates_project():\n"
        + "    from pathlib import Path\n"
        + "    Path('created.txt').write_text('mutation\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )

    with pytest.raises(runner.FeasibilityProofError) as caught:
        _capture_call(
            runner,
            project,
            pytest_args=(
                "-q",
                "-p",
                "no:cacheprovider",
                "tests/test_spine.py::test_mutates_project",
            ),
        )

    assert caught.value.code == "feasibility_pytest_capture_invalid"
    assert caught.value.detail == "tree_immutability"


def test_pytest_capture_runner_records_declared_bwrap_writable_mount_delta(
    tmp_path: Path,
) -> None:
    runner = _runner()
    project = _pytest_capture_project(tmp_path)
    (project / "training_outputs").mkdir()
    (project / "tests/test_spine.py").write_text(
        (project / "tests/test_spine.py").read_text(encoding="utf-8")
        + "\n\ndef test_writes_declared_output():\n"
        + "    from pathlib import Path\n"
        + "    Path('training_outputs/result.txt').write_text(\n"
        + "        'captured\\n', encoding='utf-8'\n"
        + "    )\n",
        encoding="utf-8",
    )
    artifact_root = (tmp_path / "external-artifacts").resolve()
    home_root = (tmp_path / "external-home").resolve()
    runtime_tmp_root = (tmp_path / "external-tmp").resolve()
    artifact_root.mkdir()
    home_root.mkdir()
    runtime_tmp_root.mkdir()
    expected_tree = runner.snapshot_project_tree_oid(project)

    record = _capture_call(
        runner,
        project,
        pytest_args=(
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/test_spine.py::test_writes_declared_output",
        ),
        expected_tree=expected_tree,
        bwrap_binding=_live_executable_binding(Path("/usr/bin/bwrap"), "--version"),
        writable_mounts=(
            runner.WritableMountSpec(
                relative_path="training_outputs",
                host_path=str(artifact_root),
            ),
        ),
        sandbox_home_root=home_root,
        sandbox_tmp_root=runtime_tmp_root,
        include_trace=False,
    )

    assert record["expected_tree"] == record["pre_tree"] == record["post_tree"]
    assert (artifact_root / "result.txt").read_text(encoding="utf-8") == "captured\n"
    envelope = record["execution_envelope"]
    assert envelope["kind"] == "bwrap_ro_project.v1"
    assert envelope["launcher"]["literal_path"] == "/usr/bin/bwrap"
    assert envelope["launcher_argv"][0] == "/usr/bin/bwrap"
    assert envelope["launcher_argv"][-len(record["argv"]) :] == record["argv"]
    assert envelope["runtime_project_root"] == "/run/orc-pytest-project"
    assert record["project_root"] == str(project)
    assert record["cwd"] == envelope["runtime_project_root"]
    assert envelope["home_root"] == str(home_root)
    assert envelope["tmp_root"] == str(runtime_tmp_root)
    assert envelope["writable_mounts"] == [
        {
            "relative_path": "training_outputs",
            "host_path": str(artifact_root),
            "pre_tree": "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
            "post_tree": runner.snapshot_project_tree_oid(artifact_root),
        }
    ]
    false_host_cwd = deepcopy(record)
    false_host_cwd["cwd"] = record["project_root"]
    false_host_cwd = _resign_pytest_ledger_record(runner, false_host_cwd)
    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_pytest_execution_ledger_record(false_host_cwd)
    assert caught.value.code == "feasibility_pytest_ledger_invalid"


def _pytest_ledger_authority_from_record(
    runner: ModuleType,
    record: dict[str, object],
) -> object:
    ledger = runner._pytest_execution_ledger_from_record(record)
    return runner.PytestLedgerAuthority(
        ledger_id=ledger.ledger_id,
        ordinal=ledger.ordinal,
        role=ledger.role,
        role_index=ledger.role_index,
        slice_id=ledger.slice_id,
        runner_path=str(RUNNER_PATH),
        runner_sha256=ledger.runner_sha256,
        git=ledger.git,
        python=ledger.python,
        variant_id=ledger.variant_id,
        project_root=ledger.project_root,
        expected_tree=ledger.expected_tree,
        argv=ledger.argv,
        execution_envelope=ledger.execution_envelope,
        expected_project_origins=ledger.project_origins,
        call_trace_specs=tuple(
            runner.CallTraceSpec(
                edge_id=value.edge_id,
                pytest_node_id=value.pytest_node_id,
                caller_path=value.caller_path,
                caller_line=value.caller_line,
                callee_path=value.callee_path,
                callee_name=value.callee_name,
                callee_first_line=value.callee_first_line,
            )
            for value in ledger.call_transitions
        ),
    )


def _replace_record_environment(
    record: dict[str, object],
    values: dict[str, str],
) -> None:
    record["environment"] = [
        [key, value]
        for key, value in sorted(
            values.items(),
            key=lambda item: item[0].encode("utf-8", "strict"),
        )
    ]


def test_authorized_pytest_ledger_rejects_redigested_authority_substitutions(
    tmp_path: Path,
) -> None:
    runner = _runner()
    project = _pytest_capture_project(tmp_path)
    record = _capture_call(runner, project)
    authority = _pytest_ledger_authority_from_record(runner, record)

    assert runner.validate_authorized_pytest_execution_ledger_record(
        record,
        authority=authority,
        reobserve_executables=False,
    ) == record
    assert runner.validate_authorized_pytest_execution_ledger_record(
        record,
        authority=authority,
        reobserve_executables=True,
    ) == record

    substitutions: list[dict[str, object]] = []
    all_trees = deepcopy(record)
    for name in ("expected_tree", "pre_tree", "post_tree"):
        all_trees[name] = "0" * 40
    substitutions.append(all_trees)
    python = deepcopy(record)
    python["python"]["sha256"] = "sha256:" + "1" * 64
    python["python"]["version_output"] = "Python substituted\n"
    substitutions.append(python)
    git = deepcopy(record)
    git["git"]["sha256"] = "sha256:" + "2" * 64
    git["git"]["version_output"] = "git version substituted\n"
    substitutions.append(git)
    origin = deepcopy(record)
    origin["project_origins"][0]["resolved_path"] = str(
        project / "substituted.py"
    )
    substitutions.append(origin)
    trace = deepcopy(record)
    trace["call_transitions"][0]["caller_line"] += 1
    substitutions.append(trace)
    for environment_tamper in ("extra", "missing", "fixed", "request"):
        changed = deepcopy(record)
        environment = dict(changed["environment"])
        if environment_tamper == "extra":
            environment["UNDECLARED"] = "1"
        elif environment_tamper == "missing":
            environment.pop("HOME")
        elif environment_tamper == "fixed":
            environment["PATH"] = "/bin"
        else:
            environment["ORC_FEASIBILITY_PYTEST_CAPTURE_REQUEST_B64"] = "e30K"
        _replace_record_environment(changed, environment)
        substitutions.append(changed)

    for changed in substitutions:
        changed = _resign_pytest_ledger_record(runner, changed)
        assert runner.validate_pytest_execution_ledger_record(changed) == changed
        with pytest.raises(runner.FeasibilityProofError) as caught:
            runner.validate_authorized_pytest_execution_ledger_record(
                changed,
                authority=authority,
                reobserve_executables=False,
            )
        assert caught.value.code == "feasibility_pytest_ledger_authority_mismatch"


def test_authorized_pytest_ledger_rejects_redigested_bwrap_authority_substitution(
    tmp_path: Path,
) -> None:
    runner = _runner()
    project = _pytest_capture_project(tmp_path)
    (project / "training_outputs").mkdir()
    (project / "tests/test_spine.py").write_text(
        (project / "tests/test_spine.py").read_text(encoding="utf-8")
        + "\n\ndef test_writes_declared_output():\n"
        + "    from pathlib import Path\n"
        + "    Path('training_outputs/result.txt').write_text(\n"
        + "        'captured\\n', encoding='utf-8'\n"
        + "    )\n",
        encoding="utf-8",
    )
    roots = tuple((tmp_path / name).resolve() for name in ("artifacts", "home", "tmp"))
    for root in roots:
        root.mkdir()
    record = _capture_call(
        runner,
        project,
        pytest_args=(
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/test_spine.py::test_writes_declared_output",
        ),
        bwrap_binding=_live_executable_binding(Path("/usr/bin/bwrap"), "--version"),
        writable_mounts=(
            runner.WritableMountSpec("training_outputs", str(roots[0])),
        ),
        sandbox_home_root=roots[1],
        sandbox_tmp_root=roots[2],
        include_trace=False,
    )
    authority = _pytest_ledger_authority_from_record(runner, record)
    replacement_root = str((tmp_path / "substituted-artifacts").resolve())
    changed = deepcopy(record)
    original_root = changed["execution_envelope"]["writable_mounts"][0]["host_path"]
    changed["execution_envelope"]["writable_mounts"][0]["host_path"] = replacement_root
    changed["execution_envelope"]["launcher_argv"] = [
        replacement_root if value == original_root else value
        for value in changed["execution_envelope"]["launcher_argv"]
    ]
    changed = _resign_pytest_ledger_record(runner, changed)

    assert runner.validate_pytest_execution_ledger_record(changed) == changed
    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_authorized_pytest_execution_ledger_record(
            changed,
            authority=authority,
            reobserve_executables=False,
        )
    assert caught.value.code == "feasibility_pytest_ledger_authority_mismatch"


def test_pytest_capture_runner_fails_closed_on_project_origin_mismatch(
    tmp_path: Path,
) -> None:
    runner = _runner()
    project = _pytest_capture_project(tmp_path)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        _capture_call(
            runner,
            project,
            expected_origins=_capture_origins(runner, project)[:-1],
        )

    assert caught.value.code == "feasibility_pytest_capture_invalid"
    assert caught.value.detail == "project_origins"


@pytest.mark.parametrize(
    ("stdout", "stderr"),
    ((b"", b""), (b"not a worker response\n", b"")),
)
def test_pytest_capture_worker_response_rejects_missing_or_malformed_schema(
    stdout: bytes,
    stderr: bytes,
) -> None:
    runner = _runner()

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner._decode_pytest_capture_response(stdout, stderr)

    assert caught.value.code == "feasibility_pytest_capture_invalid"
    assert caught.value.detail == "worker_response"


def test_pytest_execution_ledger_builds_and_round_trips_canonical_record() -> None:
    runner = _runner()
    ledger = _pytest_ledger_fixture(runner)

    record = runner.pytest_execution_ledger_record(ledger)
    normalized = runner.validate_pytest_execution_ledger_record(record)

    assert normalized == record
    assert normalized is not record
    assert normalized["schema_version"] == "pytest_execution_ledger.v1"
    assert normalized["node_outcomes"] == [
        {
            "node_id": "tests/test_feature.py::test_cross_cluster",
            "outcome": "passed",
            "failure_phase": None,
        }
    ]
    assert normalized["outcome_counts"] == {
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
    }
    assert runner.canonical_json_bytes(normalized)
    with pytest.raises(FrozenInstanceError):
        ledger.role = "baseline"


def test_pytest_execution_ledger_separates_elapsed_from_deterministic_digest() -> None:
    runner = _runner()
    first = runner.pytest_execution_ledger_record(
        _pytest_ledger_fixture(runner, elapsed_ns=1_000_000)
    )
    second = runner.pytest_execution_ledger_record(
        _pytest_ledger_fixture(runner, elapsed_ns=2_000_000)
    )

    assert first["deterministic_sha256"] == second["deterministic_sha256"]
    assert first["record_sha256"] != second["record_sha256"]
    deterministic_projection = dict(first)
    deterministic_projection.pop("elapsed_ns")
    deterministic_projection.pop("deterministic_sha256")
    deterministic_projection.pop("record_sha256")
    assert first["deterministic_sha256"] == _sha256(
        runner.canonical_json_bytes(deterministic_projection)
    )
    record_projection = dict(first)
    record_projection.pop("record_sha256")
    assert first["record_sha256"] == _sha256(
        runner.canonical_json_bytes(record_projection)
    )


def _resign_pytest_ledger_record(
    runner: ModuleType,
    record: dict[str, object],
) -> dict[str, object]:
    resigned = deepcopy(record)
    resigned.pop("deterministic_sha256", None)
    resigned.pop("record_sha256", None)
    deterministic_projection = deepcopy(resigned)
    deterministic_projection.pop("elapsed_ns")
    resigned["deterministic_sha256"] = _sha256(
        runner.canonical_json_bytes(deterministic_projection)
    )
    resigned["record_sha256"] = _sha256(runner.canonical_json_bytes(resigned))
    return resigned


def test_pytest_execution_ledger_rejects_outcomes_outside_collection_order() -> None:
    runner = _runner()
    ledger = _pytest_ledger_fixture(runner)
    first_node_id = ledger.collected_node_ids[0]
    unreported_node_id = "tests/test_feature.py::test_unreported"
    final_node_id = "tests/test_feature.py::test_final"
    ledger = replace(
        ledger,
        collected_node_ids=(first_node_id, unreported_node_id, final_node_id),
        node_outcomes=(
            runner.NodeOutcome(first_node_id, "passed", None),
            runner.NodeOutcome(final_node_id, "skipped", None),
        ),
        outcome_counts=runner.OutcomeCounts(1, 0, 1, 0),
    )
    ordered = runner.pytest_execution_ledger_record(ledger)
    swapped = deepcopy(ordered)
    swapped["node_outcomes"] = list(reversed(swapped["node_outcomes"]))
    swapped = _resign_pytest_ledger_record(runner, swapped)

    assert swapped["deterministic_sha256"] != ordered["deterministic_sha256"]
    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_pytest_execution_ledger_record(swapped)

    assert caught.value.code == "feasibility_pytest_ledger_invalid"


def test_pytest_execution_ledger_accepts_collection_and_failure_records() -> None:
    runner = _runner()
    green = _pytest_ledger_fixture(runner)
    collection = replace(
        green,
        ledger_id="collection:0",
        ordinal=0,
        role="collection",
        collected_node_ids=("tests/test_feature.py::test_cross_cluster",),
        node_outcomes=(),
        outcome_counts=runner.OutcomeCounts(0, 0, 0, 0),
        call_transitions=(),
        elapsed_ns=1,
    )
    baseline = replace(
        green,
        ledger_id="baseline:cluster-a",
        ordinal=1,
        role="baseline",
        slice_id="cluster-a",
        node_outcomes=(
            runner.NodeOutcome(
                "tests/test_feature.py::test_cross_cluster",
                "failed",
                "call",
            ),
        ),
        outcome_counts=runner.OutcomeCounts(0, 1, 0, 0),
        exit_code=1,
        call_transitions=(),
    )

    assert runner.validate_pytest_execution_ledger_record(
        runner.pytest_execution_ledger_record(collection)
    )["role"] == "collection"
    assert runner.validate_pytest_execution_ledger_record(
        runner.pytest_execution_ledger_record(baseline)
    )["role"] == "baseline"


@pytest.mark.parametrize(
    "tamper",
    (
        "missing_field",
        "extra_field",
        "schema_version",
        "ledger_id_empty",
        "ledger_id_non_utf8",
        "ordinal_bool",
        "ordinal_negative",
        "role_unknown",
        "role_index_bool",
        "role_index_negative",
        "slice_required",
        "slice_forbidden",
        "runner_sha256",
        "git_not_object",
        "git_extra",
        "git_literal_relative",
        "git_literal_noncanonical",
        "git_real_relative",
        "git_sha256",
        "git_version_argv_type",
        "git_version_argv_empty",
        "git_version_argv_first",
        "git_version_output_empty",
        "python_extra",
        "variant_empty",
        "project_root_relative",
        "project_root_noncanonical",
        "cwd_mismatch",
        "argv_type",
        "argv_empty",
        "argv_item_empty",
        "envelope_extra",
        "envelope_direct_launcher",
        "envelope_direct_argv",
        "environment_type",
        "environment_row_type",
        "environment_row_width",
        "environment_key_empty",
        "environment_value_empty",
        "environment_required_missing",
        "environment_required_value",
        "environment_cuda_nonempty",
        "environment_unsorted",
        "environment_duplicate",
        "tree_format",
        "tree_mismatch",
        "collected_type",
        "collected_duplicate",
        "node_outcomes_type",
        "node_outcomes_empty",
        "node_outcome_extra",
        "node_outcome_duplicate",
        "node_outcome_unknown",
        "node_outcome_bad_value",
        "passed_failure_phase",
        "failed_failure_phase_missing",
        "failure_phase_unknown",
        "counts_extra",
        "counts_bool",
        "counts_mismatch",
        "exit_code_bool",
        "origins_type",
        "origins_empty",
        "origin_extra",
        "origin_order",
        "origin_duplicate",
        "origin_escape",
        "origin_relative",
        "transitions_type",
        "transition_extra",
        "transition_duplicate",
        "transition_order",
        "transition_unknown_node",
        "transition_nonpassed",
        "transition_line_bool",
        "transition_hits_type",
        "elapsed_bool",
        "elapsed_zero",
    ),
)
def test_pytest_execution_ledger_rejects_redigested_semantic_tamper(
    tamper: str,
) -> None:
    runner = _runner()
    record = runner.pytest_execution_ledger_record(_pytest_ledger_fixture(runner))
    if tamper == "missing_field":
        record.pop("variant_id")
    elif tamper == "extra_field":
        record["unexpected"] = "value"
    elif tamper == "schema_version":
        record["schema_version"] = "pytest_execution_ledger.v2"
    elif tamper == "ledger_id_empty":
        record["ledger_id"] = ""
    elif tamper == "ledger_id_non_utf8":
        record["ledger_id"] = "\ud800"
    elif tamper == "ordinal_bool":
        record["ordinal"] = True
    elif tamper == "ordinal_negative":
        record["ordinal"] = -1
    elif tamper == "role_unknown":
        record["role"] = "other"
    elif tamper == "role_index_bool":
        record["role_index"] = False
    elif tamper == "role_index_negative":
        record["role_index"] = -1
    elif tamper == "slice_required":
        record["role"] = "remove_one"
        record["slice_id"] = None
    elif tamper == "slice_forbidden":
        record["slice_id"] = "cluster-a"
    elif tamper == "runner_sha256":
        record["runner_sha256"] = "3" * 64
    elif tamper == "git_not_object":
        record["git"] = []
    elif tamper == "git_extra":
        record["git"]["extra"] = "value"
    elif tamper == "git_literal_relative":
        record["git"]["literal_path"] = "usr/bin/git"
    elif tamper == "git_literal_noncanonical":
        record["git"]["literal_path"] = "/usr/../usr/bin/git"
    elif tamper == "git_real_relative":
        record["git"]["real_path"] = "usr/bin/git"
    elif tamper == "git_sha256":
        record["git"]["sha256"] = "sha256:" + "A" * 64
    elif tamper == "git_version_argv_type":
        record["git"]["version_argv"] = ()
    elif tamper == "git_version_argv_empty":
        record["git"]["version_argv"] = []
    elif tamper == "git_version_argv_first":
        record["git"]["version_argv"][0] = "/bin/git"
    elif tamper == "git_version_output_empty":
        record["git"]["version_output"] = ""
    elif tamper == "python_extra":
        record["python"]["extra"] = "value"
    elif tamper == "variant_empty":
        record["variant_id"] = ""
    elif tamper == "project_root_relative":
        record["project_root"] = "tmp/project"
    elif tamper == "project_root_noncanonical":
        record["project_root"] = "/tmp/./es-feasibility-project"
    elif tamper == "cwd_mismatch":
        record["cwd"] = "/tmp"
    elif tamper == "argv_type":
        record["argv"] = ()
    elif tamper == "argv_empty":
        record["argv"] = []
    elif tamper == "argv_item_empty":
        record["argv"][1] = ""
    elif tamper == "envelope_extra":
        record["execution_envelope"]["extra"] = "value"
    elif tamper == "envelope_direct_launcher":
        record["execution_envelope"]["launcher"] = deepcopy(record["git"])
    elif tamper == "envelope_direct_argv":
        record["execution_envelope"]["launcher_argv"].append("--extra")
    elif tamper == "environment_type":
        record["environment"] = {}
    elif tamper == "environment_row_type":
        record["environment"][0] = {"key": "LANG", "value": "C"}
    elif tamper == "environment_row_width":
        record["environment"][0] = ["LANG"]
    elif tamper == "environment_key_empty":
        record["environment"][0][0] = ""
    elif tamper == "environment_value_empty":
        next(
            row for row in record["environment"] if row[0] == "LANG"
        )[1] = ""
    elif tamper == "environment_required_missing":
        record["environment"] = [
            row
            for row in record["environment"]
            if row[0] != "PYTHONNOUSERSITE"
        ]
    elif tamper == "environment_required_value":
        next(
            row
            for row in record["environment"]
            if row[0] == "PYTHONDONTWRITEBYTECODE"
        )[1] = "0"
    elif tamper == "environment_cuda_nonempty":
        next(
            row
            for row in record["environment"]
            if row[0] == "CUDA_VISIBLE_DEVICES"
        )[1] = "0"
    elif tamper == "environment_unsorted":
        record["environment"] = list(reversed(record["environment"]))
    elif tamper == "environment_duplicate":
        record["environment"] = [record["environment"][0]] * 2
    elif tamper == "tree_format":
        record["expected_tree"] = "sha1:" + "4" * 40
    elif tamper == "tree_mismatch":
        record["post_tree"] = "5" * 40
    elif tamper == "collected_type":
        record["collected_node_ids"] = ()
    elif tamper == "collected_duplicate":
        record["collected_node_ids"] *= 2
    elif tamper == "node_outcomes_type":
        record["node_outcomes"] = ()
    elif tamper == "node_outcomes_empty":
        record["node_outcomes"] = []
        record["outcome_counts"]["passed"] = 0
        record["call_transitions"] = []
    elif tamper == "node_outcome_extra":
        record["node_outcomes"][0]["extra"] = "value"
    elif tamper == "node_outcome_duplicate":
        record["node_outcomes"] *= 2
        record["outcome_counts"]["passed"] = 2
    elif tamper == "node_outcome_unknown":
        record["node_outcomes"][0]["node_id"] = "tests/test_other.py::test_other"
    elif tamper == "node_outcome_bad_value":
        record["node_outcomes"][0]["outcome"] = "xfailed"
    elif tamper == "passed_failure_phase":
        record["node_outcomes"][0]["failure_phase"] = "call"
    elif tamper == "failed_failure_phase_missing":
        record["node_outcomes"][0]["outcome"] = "failed"
        record["node_outcomes"][0]["failure_phase"] = None
        record["outcome_counts"] = {"passed": 0, "failed": 1, "skipped": 0, "errors": 0}
        record["call_transitions"] = []
    elif tamper == "failure_phase_unknown":
        record["node_outcomes"][0]["outcome"] = "error"
        record["node_outcomes"][0]["failure_phase"] = "report"
        record["outcome_counts"] = {"passed": 0, "failed": 0, "skipped": 0, "errors": 1}
        record["call_transitions"] = []
    elif tamper == "counts_extra":
        record["outcome_counts"]["extra"] = 0
    elif tamper == "counts_bool":
        record["outcome_counts"]["failed"] = False
    elif tamper == "counts_mismatch":
        record["outcome_counts"]["passed"] = 2
    elif tamper == "exit_code_bool":
        record["exit_code"] = False
    elif tamper == "origins_type":
        record["project_origins"] = ()
    elif tamper == "origins_empty":
        record["project_origins"] = []
    elif tamper == "origin_extra":
        record["project_origins"][0]["extra"] = "value"
    elif tamper == "origin_order":
        record["project_origins"].append(
            {"module_name": "aaa", "resolved_path": "/tmp/es-feasibility-project/aaa.py"}
        )
    elif tamper == "origin_duplicate":
        record["project_origins"] *= 2
    elif tamper == "origin_escape":
        record["project_origins"][0]["resolved_path"] = "/tmp/outside.py"
    elif tamper == "origin_relative":
        record["project_origins"][0]["resolved_path"] = "pkg/feature.py"
    elif tamper == "transitions_type":
        record["call_transitions"] = ()
    elif tamper == "transition_extra":
        record["call_transitions"][0]["extra"] = "value"
    elif tamper == "transition_duplicate":
        record["call_transitions"] *= 2
    elif tamper == "transition_order":
        extra = deepcopy(record["call_transitions"][0])
        extra["edge_id"] = "edge-alpha"
        record["call_transitions"].append(extra)
    elif tamper == "transition_unknown_node":
        record["call_transitions"][0]["pytest_node_id"] = "tests/test_other.py::test_other"
    elif tamper == "transition_nonpassed":
        record["call_transitions"][0]["outcome"] = "failed"
    elif tamper == "transition_line_bool":
        record["call_transitions"][0]["caller_line"] = True
    elif tamper == "transition_hits_type":
        record["call_transitions"][0]["callee_line_hits"] = (3, 4)
    elif tamper == "elapsed_bool":
        record["elapsed_ns"] = True
    elif tamper == "elapsed_zero":
        record["elapsed_ns"] = 0
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)

    if tamper != "ledger_id_non_utf8":
        record = _resign_pytest_ledger_record(runner, record)
    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_pytest_execution_ledger_record(record)

    assert caught.value.code == "feasibility_pytest_ledger_invalid"


@pytest.mark.parametrize(
    "tamper",
    (
        "collection_exit",
        "collection_empty_ids",
        "collection_outcome",
        "collection_counts",
        "collection_transition",
    ),
)
def test_pytest_execution_ledger_rejects_collection_contract_tamper(
    tamper: str,
) -> None:
    runner = _runner()
    record = runner.pytest_execution_ledger_record(_pytest_ledger_fixture(runner))
    record["role"] = "collection"
    record["node_outcomes"] = []
    record["outcome_counts"] = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    record["call_transitions"] = []
    if tamper == "collection_exit":
        record["exit_code"] = 1
    elif tamper == "collection_empty_ids":
        record["collected_node_ids"] = []
    elif tamper == "collection_outcome":
        record["node_outcomes"] = [
            {"node_id": record["collected_node_ids"][0], "outcome": "passed", "failure_phase": None}
        ]
    elif tamper == "collection_counts":
        record["outcome_counts"]["passed"] = 1
    elif tamper == "collection_transition":
        record["call_transitions"] = deepcopy(
            runner.pytest_execution_ledger_record(_pytest_ledger_fixture(runner))[
                "call_transitions"
            ]
        )
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)
    record = _resign_pytest_ledger_record(runner, record)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_pytest_execution_ledger_record(record)

    assert caught.value.code == "feasibility_pytest_ledger_invalid"


@pytest.mark.parametrize(
    "tamper",
    ("stale_body", "deterministic_digest", "record_digest", "complete_self_hash"),
)
def test_pytest_execution_ledger_rejects_digest_tamper(tamper: str) -> None:
    runner = _runner()
    record = runner.pytest_execution_ledger_record(_pytest_ledger_fixture(runner))
    if tamper == "stale_body":
        record["ledger_id"] = "green:changed"
    elif tamper == "deterministic_digest":
        record["deterministic_sha256"] = "sha256:" + "0" * 64
        record["record_sha256"] = _sha256(
            runner.canonical_json_bytes(
                {key: value for key, value in record.items() if key != "record_sha256"}
            )
        )
    elif tamper == "record_digest":
        record["record_sha256"] = "sha256:" + "0" * 64
    elif tamper == "complete_self_hash":
        record["record_sha256"] = _sha256(runner.canonical_json_bytes(record))
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_pytest_execution_ledger_record(record)

    assert caught.value.code == "feasibility_pytest_ledger_invalid"


@pytest.mark.parametrize(
    "tamper",
    ("ledger_object", "ordinal_bool", "git_mapping", "argv_list", "environment_row_list"),
)
def test_pytest_execution_ledger_builder_rejects_malformed_runtime_types(
    tamper: str,
) -> None:
    runner = _runner()
    ledger: object = _pytest_ledger_fixture(runner)
    if tamper == "ledger_object":
        ledger = object()
    elif tamper == "ordinal_bool":
        ledger = replace(ledger, ordinal=True)
    elif tamper == "git_mapping":
        ledger = replace(ledger, git={"literal_path": "/usr/bin/git"})
    elif tamper == "argv_list":
        ledger = replace(ledger, argv=list(ledger.argv))
    elif tamper == "environment_row_list":
        ledger = replace(ledger, environment=(["LANG", "C"],))
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.pytest_execution_ledger_record(ledger)

    assert caught.value.code == "feasibility_pytest_ledger_invalid"


def test_feasibility_proof_runner_is_present() -> None:
    assert RUNNER_PATH.is_file(), "Task-0 feasibility proof runner is not implemented"


def test_canonical_json_is_ascii_sorted_integer_only_and_lf_terminated() -> None:
    runner = _runner()

    assert runner.canonical_json_bytes(
        {"z": [1, True, None], "a": "caf\N{LATIN SMALL LETTER E WITH ACUTE}"}
    ) == b'{"a":"caf\\u00e9","z":[1,true,null]}\n'
    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.canonical_json_bytes({"value": 1.25})

    assert caught.value.code == "feasibility_json_value_invalid"


def test_runner_sha256_binds_exact_regular_non_symlink_bytes(tmp_path: Path) -> None:
    runner = _runner()

    assert runner.runner_sha256() == _sha256(RUNNER_PATH.read_bytes())
    symlink = tmp_path / "runner.py"
    symlink.symlink_to(RUNNER_PATH)
    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.runner_sha256(symlink)

    assert caught.value.code == "feasibility_runner_unreadable"


@pytest.mark.parametrize(
    ("operation", "expected_code"),
    (
        ("runner", "feasibility_runner_unreadable"),
        ("record", "feasibility_record_path_invalid"),
    ),
)
def test_fifo_is_rejected_before_any_blocking_read(
    operation: str,
    expected_code: str,
    tmp_path: Path,
) -> None:
    fifo = (tmp_path / f"{operation}.fifo").resolve()
    os.mkfifo(fifo)
    child = (
        "from pathlib import Path\n"
        "from scripts.experiments.es import feasibility_proofs as runner\n"
        f"path = Path({str(fifo)!r})\n"
        "try:\n"
        + (
            "    runner.runner_sha256(path)\n"
            if operation == "runner"
            else (
                "    runner.load_pinned_canonical_json(\n"
                "        path, expected_sha256='sha256:' + '0' * 64\n"
                "    )\n"
            )
        )
        + "except runner.FeasibilityProofError as exc:\n"
        "    print(exc.code)\n"
        "else:\n"
        "    raise SystemExit('FIFO unexpectedly accepted')\n"
    )

    completed = subprocess.run(
        (sys.executable, "-c", child),
        cwd=REPOSITORY_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=2,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    assert completed.stdout.decode("utf-8", "strict").strip() == expected_code


@pytest.mark.parametrize(
    ("operation", "expected_code"),
    (
        ("runner", "feasibility_runner_unreadable"),
        ("record", "feasibility_record_path_invalid"),
    ),
)
def test_stable_reader_rejects_atomic_path_replacement_after_open(
    operation: str,
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    if operation == "runner":
        raw = b"stable runner bytes\n"
        target = (tmp_path / "runner.py").resolve()
    else:
        raw = runner.canonical_json_bytes({"status": "passed"})
        target = (tmp_path / "record.json").resolve()
    target.write_bytes(raw)
    replacement = (tmp_path / "replacement").resolve()
    replacement.write_bytes(raw)
    real_open = os.open
    replaced = False

    def replacing_open(path: object, flags: int, mode: int = 0o777) -> int:
        nonlocal replaced
        descriptor = real_open(path, flags, mode)
        if Path(path) == target and not replaced:
            os.replace(replacement, target)
            replaced = True
        return descriptor

    monkeypatch.setattr(os, "open", replacing_open)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        if operation == "runner":
            runner.runner_sha256(target)
        else:
            runner.load_pinned_canonical_json(
                target,
                expected_sha256=_sha256(raw),
            )

    assert replaced is True
    assert caught.value.code == expected_code


def test_pinned_loader_accepts_only_exact_canonical_regular_file(
    tmp_path: Path,
) -> None:
    runner = _runner()
    value = {"ordinal": 1, "status": "passed"}
    raw = runner.canonical_json_bytes(value)
    record = (tmp_path / "record.json").resolve()
    record.write_bytes(raw)

    assert runner.load_pinned_canonical_json(
        record,
        expected_sha256=_sha256(raw),
    ) == value

    with pytest.raises(runner.FeasibilityProofError) as digest_caught:
        runner.load_pinned_canonical_json(
            record,
            expected_sha256="sha256:" + "0" * 64,
        )
    assert digest_caught.value.code == "feasibility_record_digest_mismatch"

    noncanonical = (tmp_path / "noncanonical.json").resolve()
    noncanonical_raw = json.dumps(value, indent=2).encode("utf-8")
    noncanonical.write_bytes(noncanonical_raw)
    with pytest.raises(runner.FeasibilityProofError) as canonical_caught:
        runner.load_pinned_canonical_json(
            noncanonical,
            expected_sha256=_sha256(noncanonical_raw),
        )
    assert canonical_caught.value.code == "feasibility_record_noncanonical"

    symlink = (tmp_path / "record-link.json").resolve()
    symlink.symlink_to(record)
    with pytest.raises(runner.FeasibilityProofError) as symlink_caught:
        runner.load_pinned_canonical_json(
            symlink,
            expected_sha256=_sha256(raw),
        )
    assert symlink_caught.value.code == "feasibility_record_path_invalid"


@pytest.mark.parametrize(
    "raw",
    (
        b'{"ordinal":1,"ordinal":2}\n',
        b'{"value":1.5}\n',
        b'[1,2,3]\n',
    ),
)
def test_pinned_loader_rejects_duplicate_float_and_non_object_json(
    raw: bytes,
    tmp_path: Path,
) -> None:
    runner = _runner()
    record = (tmp_path / "invalid.json").resolve()
    record.write_bytes(raw)

    with pytest.raises(runner.FeasibilityProofError):
        runner.load_pinned_canonical_json(
            record,
            expected_sha256=_sha256(raw),
        )


def test_pinned_loader_normalizes_oversized_integer_parse_failure(
    tmp_path: Path,
) -> None:
    runner = _runner()
    raw = b'{"value":' + b"9" * 5000 + b"}\n"
    record = (tmp_path / "oversized-integer.json").resolve()
    record.write_bytes(raw)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.load_pinned_canonical_json(
            record,
            expected_sha256=_sha256(raw),
        )

    assert caught.value.code == "feasibility_record_invalid"


@pytest.mark.parametrize(
    ("role", "literal_path"),
    (
        ("git", Path("/usr/bin/git")),
        (
            "python",
            Path("/home/ollie/miniconda3/envs/ptycho311/bin/python"),
        ),
    ),
)
def test_verify_executable_binding_accepts_live_exact_toolchain(
    role: str,
    literal_path: Path,
) -> None:
    runner = _runner()
    binding = _live_executable_binding(literal_path, "--version")

    normalized = runner.verify_executable_binding(binding, role=role)

    assert normalized == binding
    assert normalized is not binding
    assert runner.canonical_json_bytes(normalized)


@pytest.mark.parametrize(
    "tamper",
    ("real_path", "sha256", "version_output", "version_argv", "empty_argv", "extra"),
)
def test_verify_executable_binding_rejects_closed_binding_tamper(
    tamper: str,
) -> None:
    runner = _runner()
    binding = _live_executable_binding(
        Path("/home/ollie/miniconda3/envs/ptycho311/bin/python"),
        "--version",
    )
    if tamper == "real_path":
        binding["real_path"] = str(Path("/usr/bin/git").resolve(strict=True))
    elif tamper == "sha256":
        binding["sha256"] = "sha256:" + "0" * 64
    elif tamper == "version_output":
        binding["version_output"] = str(binding["version_output"]) + "stale"
    elif tamper == "version_argv":
        binding["version_argv"] = [str(binding["real_path"]), "--version"]
    elif tamper == "empty_argv":
        binding["version_argv"] = []
    elif tamper == "extra":
        binding["unchecked"] = True
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.verify_executable_binding(binding, role="python")

    assert caught.value.code == "feasibility_executable_binding_invalid"


def test_verify_executable_binding_rejects_nonregular_real_path_before_read(
    tmp_path: Path,
) -> None:
    runner = _runner()
    fifo = (tmp_path / "tool.fifo").resolve()
    os.mkfifo(fifo)
    binding = {
        "literal_path": str(fifo),
        "real_path": str(fifo),
        "sha256": "sha256:" + "0" * 64,
        "version_argv": [str(fifo), "--version"],
        "version_output": "unused\n",
    }

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.verify_executable_binding(binding, role="fifo")

    assert caught.value.code == "feasibility_executable_binding_invalid"


@pytest.mark.parametrize("failure", ("timeout", "nonzero"))
def test_verify_executable_binding_normalizes_process_failure(
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    tool = (tmp_path / f"{failure}-tool").resolve()
    if failure == "timeout":
        tool.write_text("#!/bin/sh\nsleep 2\nprintf 'tool\\n'\n", encoding="utf-8")
    else:
        tool.write_text("#!/bin/sh\nprintf 'tool\\n'\nexit 7\n", encoding="utf-8")
    tool.chmod(0o755)
    binding = {
        "literal_path": str(tool),
        "real_path": str(tool),
        "sha256": _sha256(tool.read_bytes()),
        "version_argv": [str(tool)],
        "version_output": "tool\n",
    }
    monkeypatch.setattr(runner, "_EXECUTABLE_VERSION_TIMEOUT_SECONDS", 0.05)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.verify_executable_binding(binding, role=failure)

    assert caught.value.code == "feasibility_executable_binding_invalid"


def test_verify_executable_binding_rejects_atomic_replacement_during_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    tool = (tmp_path / "version-tool").resolve()
    tool.write_text("#!/bin/sh\nprintf 'tool\\n'\n", encoding="utf-8")
    tool.chmod(0o755)
    binding = _live_executable_binding(tool)
    replacement = (tmp_path / "replacement-tool").resolve()
    replacement.write_text(
        "#!/bin/sh\n# replacement bytes\nprintf 'tool\\n'\n",
        encoding="utf-8",
    )
    replacement.chmod(0o755)
    real_run = runner.subprocess.run
    replaced = False

    def replacing_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal replaced
        if not replaced:
            os.replace(replacement, tool)
            replaced = True
        return real_run(*args, **kwargs)

    monkeypatch.setattr(runner.subprocess, "run", replacing_run)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.verify_executable_binding(binding, role="replace-during-version")

    assert replaced is True
    assert caught.value.code == "feasibility_executable_binding_invalid"


def test_git_object_store_reads_blob_from_one_canonical_bare_repository(
    tmp_path: Path,
) -> None:
    runner = _runner()
    repository, blob_oid, blob_payload, _, _ = (
        _bare_object_fixture(tmp_path)
    )
    store = runner.GitObjectStore(
        repository,
        _live_executable_binding(Path("/usr/bin/git"), "--version"),
    )

    assert store.read(blob_oid) == runner.GitObject(
        oid=blob_oid,
        object_type="blob",
        payload=blob_payload,
    )


def test_git_object_store_reads_tree_from_one_canonical_bare_repository(
    tmp_path: Path,
) -> None:
    runner = _runner()
    repository, _, _, tree_oid, tree_payload = _bare_object_fixture(tmp_path)
    store = runner.GitObjectStore(
        repository,
        _live_executable_binding(Path("/usr/bin/git"), "--version"),
    )

    assert store.read(tree_oid) == runner.GitObject(
        oid=tree_oid,
        object_type="tree",
        payload=tree_payload,
    )


def test_git_object_store_and_pair_read_many_in_one_ordered_batch(
    tmp_path: Path,
) -> None:
    runner = _runner()
    binding = _live_executable_binding(Path("/usr/bin/git"), "--version")
    primary_root = tmp_path / "primary"
    fallback_root = tmp_path / "fallback"
    primary_root.mkdir()
    fallback_root.mkdir()
    primary_path, primary_oid, primary_payload, primary_tree_oid, _ = (
        _bare_object_fixture(primary_root, blob_payload=b"primary\n")
    )
    fallback_path, fallback_oid, fallback_payload, _, _ = _bare_object_fixture(
        fallback_root,
        blob_payload=b"fallback\n",
    )
    primary = runner.GitObjectStore(primary_path, binding)
    fallback = runner.GitObjectStore(fallback_path, binding)
    pair = runner.GitObjectPair(primary, fallback)

    assert primary.read_many((primary_oid, primary_tree_oid)) == (
        runner.GitObject(primary_oid, "blob", primary_payload),
        primary.read(primary_tree_oid),
    )
    assert pair.read_many((fallback_oid, primary_oid)) == (
        runner.GitObject(fallback_oid, "blob", fallback_payload),
        runner.GitObject(primary_oid, "blob", primary_payload),
    )


@pytest.mark.parametrize(
    ("oid", "expected_code"),
    (
        ("not-an-oid", "feasibility_git_oid_invalid"),
        ("0" * 40, "feasibility_git_object_missing"),
    ),
)
def test_git_object_store_rejects_invalid_or_missing_oid(
    oid: str,
    expected_code: str,
    tmp_path: Path,
) -> None:
    runner = _runner()
    repository, _, _, _, _ = _bare_object_fixture(tmp_path)
    store = runner.GitObjectStore(
        repository,
        _live_executable_binding(Path("/usr/bin/git"), "--version"),
    )

    with pytest.raises(runner.FeasibilityProofError) as caught:
        store.read(oid)

    assert caught.value.code == expected_code


@pytest.mark.parametrize("repository_kind", ("missing", "non_bare", "symlink"))
def test_git_object_store_rejects_invalid_repository(
    repository_kind: str,
    tmp_path: Path,
) -> None:
    runner = _runner()
    if repository_kind == "missing":
        repository = (tmp_path / "missing.git").resolve()
    elif repository_kind == "non_bare":
        repository = (tmp_path / "not-bare").resolve()
        repository.mkdir()
    else:
        target, _, _, _, _ = _bare_object_fixture(tmp_path)
        repository = (tmp_path / "store-link.git").resolve()
        repository.symlink_to(target, target_is_directory=True)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.GitObjectStore(
            repository,
            _live_executable_binding(Path("/usr/bin/git"), "--version"),
        )

    assert caught.value.code == "feasibility_git_store_invalid"


@pytest.mark.parametrize("tamper", ("corrupt_payload", "trailing"))
def test_git_object_store_rejects_corrupt_or_trailing_batch_output(
    tamper: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    repository, blob_oid, blob_payload, _, _ = _bare_object_fixture(tmp_path)
    store = runner.GitObjectStore(
        repository,
        _live_executable_binding(Path("/usr/bin/git"), "--version"),
    )
    payload = (
        bytes([blob_payload[0] ^ 1]) + blob_payload[1:]
        if tamper == "corrupt_payload"
        else blob_payload
    )
    trailing = b"" if tamper == "corrupt_payload" else b"trailing"
    corrupt = subprocess.CompletedProcess(
        args=(),
        returncode=0,
        stdout=(
            f"{blob_oid} blob {len(blob_payload)}\n".encode("ascii")
            + payload
            + b"\n"
            + trailing
        ),
        stderr=b"",
    )
    monkeypatch.setattr(store, "_run", lambda *args, **kwargs: corrupt)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        store.read(blob_oid)

    assert caught.value.code == "feasibility_git_object_invalid"


def test_git_object_store_rejects_git_replacement_after_construction(
    tmp_path: Path,
) -> None:
    runner = _runner()
    repository, blob_oid, _, _, _ = _bare_object_fixture(tmp_path)
    tool = (tmp_path / "git-wrapper").resolve()
    tool.write_text(
        '#!/bin/sh\nexec /usr/bin/git "$@"\n',
        encoding="utf-8",
    )
    tool.chmod(0o755)
    binding = _live_executable_binding(tool, "--version")
    store = runner.GitObjectStore(repository, binding)
    replacement = (tmp_path / "git-wrapper-replacement").resolve()
    replacement.write_text(
        '#!/bin/sh\n# replacement bytes\nexec /usr/bin/git "$@"\n',
        encoding="utf-8",
    )
    replacement.chmod(0o755)
    os.replace(replacement, tool)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        store.read(blob_oid)

    assert caught.value.code in {
        "feasibility_executable_binding_invalid",
        "feasibility_git_command_failed",
    }


def test_git_object_store_rejects_promisor_configuration(
    tmp_path: Path,
) -> None:
    runner = _runner()
    repository, _, _, _, _ = _bare_object_fixture(tmp_path)
    _git(
        Path("/usr/bin/git"),
        "--git-dir",
        str(repository),
        "config",
        "remote.origin.promisor",
        "true",
    )

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.GitObjectStore(
            repository,
            _live_executable_binding(Path("/usr/bin/git"), "--version"),
        )

    assert caught.value.code == "feasibility_git_store_invalid"


def test_git_object_pair_reads_only_two_explicit_temporary_stores(
    tmp_path: Path,
) -> None:
    runner = _runner()
    binding = _live_executable_binding(Path("/usr/bin/git"), "--version")
    primary_root = tmp_path / "primary"
    fallback_root = tmp_path / "fallback"
    primary_root.mkdir()
    fallback_root.mkdir()
    primary_path, primary_oid, _, _, _ = _bare_object_fixture(primary_root)
    fallback_path, fallback_oid, _, _, _ = _bare_object_fixture(
        fallback_root,
        blob_payload=b"fallback payload\n",
    )
    primary = runner.GitObjectStore(primary_path, binding)
    fallback = runner.GitObjectStore(fallback_path, binding)
    pair = runner.GitObjectPair(primary, fallback)

    assert pair.read(primary_oid).oid == primary_oid
    assert pair.read(fallback_oid).oid == fallback_oid
    with pytest.raises(runner.FeasibilityProofError) as primary_only:
        pair.read_primary(fallback_oid)
    assert primary_only.value.code == "feasibility_git_object_missing"

    with pytest.raises(runner.FeasibilityProofError) as same_store:
        runner.GitObjectPair(primary, primary)
    assert same_store.value.code == "feasibility_git_store_pair_invalid"


def test_git_object_pair_does_not_fallback_on_primary_validation_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    binding = _live_executable_binding(Path("/usr/bin/git"), "--version")
    primary_root = tmp_path / "primary"
    fallback_root = tmp_path / "fallback"
    primary_root.mkdir()
    fallback_root.mkdir()
    primary_path, _, _, _, _ = _bare_object_fixture(primary_root)
    fallback_path, fallback_oid, _, _, _ = _bare_object_fixture(
        fallback_root,
        blob_payload=b"fallback payload\n",
    )
    primary = runner.GitObjectStore(primary_path, binding)
    fallback = runner.GitObjectStore(fallback_path, binding)
    pair = runner.GitObjectPair(primary, fallback)
    fallback_called = False
    fallback_read = fallback.read

    def invalid_primary(oid: str) -> object:
        raise runner.FeasibilityProofError("feasibility_git_object_invalid", oid)

    def observed_fallback(oid: str) -> object:
        nonlocal fallback_called
        fallback_called = True
        return fallback_read(oid)

    monkeypatch.setattr(primary, "read", invalid_primary)
    monkeypatch.setattr(fallback, "read", observed_fallback)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        pair.read(fallback_oid)

    assert caught.value.code == "feasibility_git_object_invalid"
    assert fallback_called is False


def test_read_tree_leaves_traverses_explicit_primary_then_fallback(
    tmp_path: Path,
) -> None:
    runner = _runner()
    binding = _live_executable_binding(Path("/usr/bin/git"), "--version")
    fallback_root = tmp_path / "fallback"
    primary_root = tmp_path / "primary"
    fallback_root.mkdir()
    primary_root.mkdir()
    fallback_path, fallback_blob_oid, _, fallback_tree_oid, _ = _bare_object_fixture(
        fallback_root
    )
    primary_path, primary_blob_oid, _, _, _ = _bare_object_fixture(
        primary_root,
        blob_payload=b"primary payload\n",
    )
    full_payload = (
        b"100644 added.txt\0"
        + bytes.fromhex(primary_blob_oid)
        + b"40000 base\0"
        + bytes.fromhex(fallback_tree_oid)
    )
    full_tree_oid = _write_git_object(primary_path, "tree", full_payload)
    primary = runner.GitObjectStore(primary_path, binding)
    fallback = runner.GitObjectStore(fallback_path, binding)
    pair = runner.GitObjectPair(primary, fallback)

    assert runner.read_tree_leaves(pair, full_tree_oid) == (
        runner.TreeLeaf(
            path="added.txt",
            mode="100644",
            blob_oid=primary_blob_oid,
        ),
        runner.TreeLeaf(
            path="base/fixture.txt",
            mode="100644",
            blob_oid=fallback_blob_oid,
        ),
    )
    with pytest.raises(runner.FeasibilityProofError) as primary_only:
        runner.read_tree_leaves(primary, full_tree_oid)
    assert primary_only.value.code == "feasibility_git_object_missing"


@pytest.mark.parametrize(
    "tamper",
    (
        "root_is_blob",
        "unsupported_mode",
        "wrong_child_type",
        "noncanonical_order",
        "duplicate_name",
        "invalid_component",
        "invalid_utf8",
        "directory_sentinel_order",
        "malformed_entry",
    ),
)
def test_read_tree_leaves_rejects_malformed_or_unsupported_tree(
    tamper: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    repository, _, _, _, _ = _bare_object_fixture(tmp_path)
    store = runner.GitObjectStore(
        repository,
        _live_executable_binding(Path("/usr/bin/git"), "--version"),
    )
    root_oid = "1" * 40
    blob_oid = "2" * 40
    other_oid = "3" * 40
    objects = {
        blob_oid: runner.GitObject(blob_oid, "blob", b"payload\n"),
        other_oid: runner.GitObject(other_oid, "blob", b"other\n"),
    }
    if tamper == "root_is_blob":
        root = runner.GitObject(root_oid, "blob", b"payload\n")
    elif tamper == "unsupported_mode":
        root = runner.GitObject(
            root_oid,
            "tree",
            b"160000 nested-repository\0" + bytes.fromhex(blob_oid),
        )
    elif tamper == "wrong_child_type":
        objects[blob_oid] = runner.GitObject(blob_oid, "tree", b"")
        root = runner.GitObject(
            root_oid,
            "tree",
            b"100644 file.py\0" + bytes.fromhex(blob_oid),
        )
    elif tamper == "noncanonical_order":
        root = runner.GitObject(
            root_oid,
            "tree",
            b"100644 z.py\0"
            + bytes.fromhex(blob_oid)
            + b"100644 a.py\0"
            + bytes.fromhex(other_oid),
        )
    elif tamper == "duplicate_name":
        root = runner.GitObject(
            root_oid,
            "tree",
            b"100644 same.py\0"
            + bytes.fromhex(blob_oid)
            + b"100644 same.py\0"
            + bytes.fromhex(other_oid),
        )
    elif tamper == "invalid_component":
        root = runner.GitObject(
            root_oid,
            "tree",
            b"100644 bad\\name.py\0" + bytes.fromhex(blob_oid),
        )
    elif tamper == "invalid_utf8":
        root = runner.GitObject(
            root_oid,
            "tree",
            b"100644 bad-\xff.py\0" + bytes.fromhex(blob_oid),
        )
    elif tamper == "directory_sentinel_order":
        objects[blob_oid] = runner.GitObject(blob_oid, "tree", b"")
        root = runner.GitObject(
            root_oid,
            "tree",
            b"40000 a\0"
            + bytes.fromhex(blob_oid)
            + b"100644 a.b\0"
            + bytes.fromhex(other_oid),
        )
    elif tamper == "malformed_entry":
        root = runner.GitObject(root_oid, "tree", b"100644 truncated\0short")
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)
    objects[root_oid] = root

    def read_fixture(oid: str) -> object:
        return objects[oid]

    def read_many_fixture(oids: tuple[str, ...]) -> tuple[object, ...]:
        return tuple(objects[oid] for oid in oids)

    monkeypatch.setattr(store, "read", read_fixture)
    monkeypatch.setattr(store, "read_many", read_many_fixture)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.read_tree_leaves(store, root_oid)

    assert caught.value.code == "feasibility_git_tree_invalid"


def test_read_tree_leaves_preserves_git_directory_sentinel_path_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    repository, _, _, _, _ = _bare_object_fixture(tmp_path)
    store = runner.GitObjectStore(
        repository,
        _live_executable_binding(Path("/usr/bin/git"), "--version"),
    )
    root_oid = "1" * 40
    subtree_oid = "2" * 40
    dotted_oid = "3" * 40
    nested_oid = "4" * 40
    suffix_oid = "5" * 40
    objects = {
        root_oid: runner.GitObject(
            root_oid,
            "tree",
            b"100644 a.b\0"
            + bytes.fromhex(dotted_oid)
            + b"40000 a\0"
            + bytes.fromhex(subtree_oid)
            + b"100644 a0\0"
            + bytes.fromhex(suffix_oid),
        ),
        subtree_oid: runner.GitObject(
            subtree_oid,
            "tree",
            b"100644 inside\0" + bytes.fromhex(nested_oid),
        ),
        dotted_oid: runner.GitObject(dotted_oid, "blob", b"dotted\n"),
        nested_oid: runner.GitObject(nested_oid, "blob", b"nested\n"),
        suffix_oid: runner.GitObject(suffix_oid, "blob", b"suffix\n"),
    }
    monkeypatch.setattr(store, "read", lambda oid: objects[oid])
    monkeypatch.setattr(
        store,
        "read_many",
        lambda oids: tuple(objects[oid] for oid in oids),
    )

    leaves = runner.read_tree_leaves(store, root_oid)

    assert isinstance(leaves, tuple)
    assert tuple(leaf.path for leaf in leaves) == ("a.b", "a/inside", "a0")
    assert tuple(leaf.path.encode("utf-8") for leaf in leaves) == tuple(
        sorted(leaf.path.encode("utf-8") for leaf in leaves)
    )


def test_read_tree_leaves_preserves_executable_and_symlink_blob_modes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    repository, _, _, _, _ = _bare_object_fixture(tmp_path)
    store = runner.GitObjectStore(
        repository,
        _live_executable_binding(Path("/usr/bin/git"), "--version"),
    )
    root_oid = "1" * 40
    executable_oid = "2" * 40
    symlink_oid = "3" * 40
    objects = {
        root_oid: runner.GitObject(
            root_oid,
            "tree",
            b"100755 executable\0"
            + bytes.fromhex(executable_oid)
            + b"120000 link\0"
            + bytes.fromhex(symlink_oid),
        ),
        executable_oid: runner.GitObject(executable_oid, "blob", b"#!/bin/sh\n"),
        symlink_oid: runner.GitObject(symlink_oid, "blob", b"target"),
    }
    monkeypatch.setattr(
        store,
        "read_many",
        lambda oids: tuple(objects[oid] for oid in oids),
    )

    leaves = runner.read_tree_leaves(store, root_oid)

    assert tuple((leaf.path, leaf.mode) for leaf in leaves) == (
        ("executable", "100755"),
        ("link", "120000"),
    )


def test_read_tree_leaves_uses_bounded_batch_reads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    repository, _, _, _, _ = _bare_object_fixture(tmp_path)
    store = runner.GitObjectStore(
        repository,
        _live_executable_binding(Path("/usr/bin/git"), "--version"),
    )
    root_oid = "1" * 40
    first_oid = "2" * 40
    second_oid = "3" * 40
    objects = {
        root_oid: runner.GitObject(
            root_oid,
            "tree",
            b"100644 first\0"
            + bytes.fromhex(first_oid)
            + b"100644 second\0"
            + bytes.fromhex(second_oid),
        ),
        first_oid: runner.GitObject(first_oid, "blob", b"first\n"),
        second_oid: runner.GitObject(second_oid, "blob", b"second\n"),
    }
    batch_sizes: list[int] = []

    def read_many(oids: tuple[str, ...]) -> tuple[object, ...]:
        batch_sizes.append(len(oids))
        return tuple(objects[oid] for oid in oids)

    monkeypatch.setattr(store, "read", lambda oid: (_ for _ in ()).throw(
        AssertionError(f"single read used for {oid}")
    ))
    monkeypatch.setattr(store, "read_many", read_many, raising=False)

    leaves = runner.read_tree_leaves(store, root_oid)

    assert tuple(leaf.path for leaf in leaves) == ("first", "second")
    assert batch_sizes == [1, 2]
    assert max(batch_sizes) <= 64


@pytest.mark.parametrize("shape", ("deep", "cycle"))
def test_read_tree_leaves_is_iterative_and_rejects_cycles(
    shape: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    repository, _, _, _, _ = _bare_object_fixture(tmp_path)
    store = runner.GitObjectStore(
        repository,
        _live_executable_binding(Path("/usr/bin/git"), "--version"),
    )
    depth = 1100
    root_oid = f"{1:040x}"
    blob_oid = f"{depth + 2:040x}"
    objects: dict[str, object] = {
        blob_oid: runner.GitObject(blob_oid, "blob", b"leaf\n")
    }
    if shape == "cycle":
        objects[root_oid] = runner.GitObject(
            root_oid,
            "tree",
            b"40000 loop\0" + bytes.fromhex(root_oid),
        )
    else:
        for ordinal in range(1, depth + 1):
            oid = f"{ordinal:040x}"
            child_oid = (
                blob_oid if ordinal == depth else f"{ordinal + 1:040x}"
            )
            mode = b"100644" if ordinal == depth else b"40000"
            objects[oid] = runner.GitObject(
                oid,
                "tree",
                mode + b" node\0" + bytes.fromhex(child_oid),
            )

    def read_many(oids: tuple[str, ...]) -> tuple[object, ...]:
        return tuple(objects[oid] for oid in oids)

    monkeypatch.setattr(store, "read", lambda oid: objects[oid])
    monkeypatch.setattr(store, "read_many", read_many, raising=False)

    if shape == "cycle":
        with pytest.raises(runner.FeasibilityProofError) as caught:
            runner.read_tree_leaves(store, root_oid)
        assert caught.value.code == "feasibility_git_tree_invalid"
    else:
        leaves = runner.read_tree_leaves(store, root_oid)
        assert len(leaves) == 1
        assert leaves[0].blob_oid == blob_oid


def test_derive_overlay_tree_reconstructs_expected_tree_without_writes(
    tmp_path: Path,
) -> None:
    runner = _runner()
    binding = _live_executable_binding(Path("/usr/bin/git"), "--version")
    base_root = tmp_path / "base"
    overlay_root = tmp_path / "overlay"
    base_root.mkdir()
    overlay_root.mkdir()
    base_path, base_blob_oid, _, base_tree_oid, _ = _bare_object_fixture(base_root)
    overlay_path, overlay_blob_oid, _, _, _ = _bare_object_fixture(
        overlay_root,
        blob_payload=b"overlay\n",
    )
    expected_payload = (
        b"100644 fixture.txt\0"
        + bytes.fromhex(base_blob_oid)
        + b"100644 new.txt\0"
        + bytes.fromhex(overlay_blob_oid)
    )
    expected_tree_oid = _write_git_object(overlay_path, "tree", expected_payload)
    primary = runner.GitObjectStore(overlay_path, binding)
    fallback = runner.GitObjectStore(base_path, binding)
    pair = runner.GitObjectPair(primary, fallback)
    base_leaves = runner.read_tree_leaves(fallback, base_tree_oid)
    overlay = (
        runner.OverlayRow("new.txt", "100644", overlay_blob_oid),
    )

    first = runner.derive_overlay_tree(
        pair,
        base_leaves=base_leaves,
        overlay=overlay,
        expected_tree_oid=expected_tree_oid,
    )
    second = runner.derive_overlay_tree(
        pair,
        base_leaves=base_leaves,
        overlay=overlay,
        expected_tree_oid=expected_tree_oid,
    )

    assert first == second
    assert first.tree_oid == expected_tree_oid
    assert tuple(leaf.path for leaf in first.leaves) == ("fixture.txt", "new.txt")
    assert first.generated_tree_objects[0] == runner.GitObject(
        expected_tree_oid,
        "tree",
        expected_payload,
    )


@pytest.mark.parametrize(
    "tamper",
    (
        "reordered",
        "duplicate",
        "base_overlap",
        "wrong_mode",
        "absolute_path",
        "dot_component",
        "backslash",
        "missing_blob",
        "wrong_object_type",
        "wrong_expected_tree",
    ),
)
def test_derive_overlay_tree_rejects_non_addition_or_authority_tamper(
    tamper: str,
    tmp_path: Path,
) -> None:
    runner = _runner()
    binding = _live_executable_binding(Path("/usr/bin/git"), "--version")
    base_root = tmp_path / "base"
    overlay_root = tmp_path / "overlay"
    base_root.mkdir()
    overlay_root.mkdir()
    base_path, _, _, base_tree_oid, _ = _bare_object_fixture(base_root)
    overlay_path, first_oid, _, overlay_tree_oid, _ = _bare_object_fixture(
        overlay_root,
        blob_payload=b"first\n",
    )
    second_oid = _write_git_object(overlay_path, "blob", b"second\n")
    primary = runner.GitObjectStore(overlay_path, binding)
    fallback = runner.GitObjectStore(base_path, binding)
    pair = runner.GitObjectPair(primary, fallback)
    base_leaves = runner.read_tree_leaves(fallback, base_tree_oid)
    overlay = [
        runner.OverlayRow("a.txt", "100644", first_oid),
        runner.OverlayRow("b.txt", "100644", second_oid),
    ]
    expected_tree_oid: str | None = None
    if tamper == "reordered":
        overlay.reverse()
    elif tamper == "duplicate":
        overlay[1] = overlay[0]
    elif tamper == "base_overlap":
        overlay[0] = runner.OverlayRow("fixture.txt", "100644", first_oid)
    elif tamper == "wrong_mode":
        overlay[0] = runner.OverlayRow("a.txt", "100755", first_oid)
    elif tamper == "absolute_path":
        overlay[0] = runner.OverlayRow("/a.txt", "100644", first_oid)
    elif tamper == "dot_component":
        overlay[0] = runner.OverlayRow("a/../b.txt", "100644", first_oid)
    elif tamper == "backslash":
        overlay[0] = runner.OverlayRow("a\\b.txt", "100644", first_oid)
    elif tamper == "missing_blob":
        overlay[0] = runner.OverlayRow("a.txt", "100644", "0" * 40)
    elif tamper == "wrong_object_type":
        overlay[0] = runner.OverlayRow("a.txt", "100644", overlay_tree_oid)
    elif tamper == "wrong_expected_tree":
        expected_tree_oid = "f" * 40
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.derive_overlay_tree(
            pair,
            base_leaves=base_leaves,
            overlay=tuple(overlay),
            expected_tree_oid=expected_tree_oid,
        )

    assert caught.value.code == "feasibility_git_overlay_invalid"


@pytest.mark.parametrize("row_scope", ("base", "overlay"))
@pytest.mark.parametrize("field", ("path", "mode", "blob_oid"))
def test_derive_overlay_tree_normalizes_malformed_runtime_row_fields(
    row_scope: str,
    field: str,
    tmp_path: Path,
) -> None:
    runner = _runner()
    binding = _live_executable_binding(Path("/usr/bin/git"), "--version")
    base_root = tmp_path / "base"
    overlay_root = tmp_path / "overlay"
    base_root.mkdir()
    overlay_root.mkdir()
    base_path, _, _, base_tree_oid, _ = _bare_object_fixture(base_root)
    overlay_path, overlay_oid, _, _, _ = _bare_object_fixture(
        overlay_root,
        blob_payload=b"overlay\n",
    )
    primary = runner.GitObjectStore(overlay_path, binding)
    fallback = runner.GitObjectStore(base_path, binding)
    pair = runner.GitObjectPair(primary, fallback)
    base_leaves = runner.read_tree_leaves(fallback, base_tree_oid)
    overlay = (runner.OverlayRow("new.txt", "100644", overlay_oid),)
    bad_value: object = [] if field == "mode" else 1
    if row_scope == "base":
        source = base_leaves[0]
        malformed = runner.TreeLeaf(
            bad_value if field == "path" else source.path,
            bad_value if field == "mode" else source.mode,
            bad_value if field == "blob_oid" else source.blob_oid,
        )
        base_leaves = (malformed,)
    else:
        source = overlay[0]
        overlay = (
            runner.OverlayRow(
                bad_value if field == "path" else source.path,
                bad_value if field == "mode" else source.mode,
                bad_value if field == "blob_oid" else source.blob_oid,
            ),
        )

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.derive_overlay_tree(
            pair,
            base_leaves=base_leaves,
            overlay=overlay,
            expected_tree_oid=None,
        )

    assert caught.value.code == "feasibility_git_overlay_invalid"


def test_overlay_partition_derives_full_test_only_and_remove_one_variants(
    tmp_path: Path,
) -> None:
    runner = _runner()
    binding = _live_executable_binding(Path("/usr/bin/git"), "--version")
    base_root = tmp_path / "base"
    overlay_root = tmp_path / "overlay"
    base_root.mkdir()
    overlay_root.mkdir()
    base_path, _, _, base_tree_oid, _ = _bare_object_fixture(base_root)
    overlay_path, first_oid, _, _, _ = _bare_object_fixture(
        overlay_root,
        blob_payload=b"a\nb\n",
    )
    second_oid = _write_git_object(overlay_path, "blob", b"x")
    test_oid = _write_git_object(
        overlay_path,
        "blob",
        b"test\n\n# comment\nlast",
    )
    primary = runner.GitObjectStore(overlay_path, binding)
    fallback = runner.GitObjectStore(base_path, binding)
    pair = runner.GitObjectPair(primary, fallback)
    base_leaves = runner.read_tree_leaves(fallback, base_tree_oid)
    overlay = (
        runner.OverlayRow("prod/a.py", "100644", first_oid),
        runner.OverlayRow("prod/b.py", "100644", second_oid),
        runner.OverlayRow("tests/test_feature.py", "100644", test_oid),
    )
    test_slice = runner.OverlaySlice("tests", 0, ("tests/test_feature.py",))
    clusters = (
        runner.OverlaySlice("cluster_a", 1, ("prod/a.py",)),
        runner.OverlaySlice("cluster_b", 2, ("prod/b.py",)),
    )

    first = runner.derive_overlay_variants(
        pair,
        base_leaves=base_leaves,
        overlay=overlay,
        test_slice=test_slice,
        cluster_slices=clusters,
        expected_full_tree_oid=None,
    )
    second = runner.derive_overlay_variants(
        pair,
        base_leaves=base_leaves,
        overlay=overlay,
        test_slice=test_slice,
        cluster_slices=clusters,
        expected_full_tree_oid=None,
    )

    assert first == second
    assert tuple(item.variant_id for item in first) == (
        "full",
        "test_only",
        "remove_one:cluster_a",
        "remove_one:cluster_b",
    )
    assert tuple(len(item.tree.leaves) for item in first) == (4, 2, 3, 3)
    assert first[1].included_overlay_paths == ("tests/test_feature.py",)
    assert first[2].included_overlay_paths == (
        "prod/b.py",
        "tests/test_feature.py",
    )
    assert first[3].included_overlay_paths == (
        "prod/a.py",
        "tests/test_feature.py",
    )

    numstat = runner.derive_addition_numstat(
        pair,
        base_leaves=base_leaves,
        overlay=overlay,
    )
    assert numstat == (
        runner.NumstatRow("prod/a.py", 2, 0, 2),
        runner.NumstatRow("prod/b.py", 1, 0, 1),
        runner.NumstatRow("tests/test_feature.py", 4, 0, 4),
    )


def test_overlay_partition_accepts_explicit_semantic_ordinals_and_unicode() -> None:
    runner = _runner()
    overlay = (
        runner.OverlayRow("prod/a.py", "100644", "1" * 40),
        runner.OverlayRow("prod/é.py", "100644", "2" * 40),
        runner.OverlayRow("tests/test_é.py", "100644", "3" * 40),
    )

    runner.validate_overlay_partition(
        overlay,
        test_slice=runner.OverlaySlice(
            "tésts",
            0,
            ("tests/test_é.py",),
        ),
        cluster_slices=(
            runner.OverlaySlice("cluster_a", 1, ("prod/a.py",)),
            runner.OverlaySlice("clüster_b", 2, ("prod/é.py",)),
        ),
    )


@pytest.mark.parametrize(
    "ordinals",
    (
        (0, 1, 1),
        (0, 1, 3),
        (0, 2, 1),
        (1, 2, 3),
        (-1, 0, 1),
        (False, 1, 2),
        ("0", 1, 2),
    ),
)
def test_overlay_partition_rejects_noncontiguous_or_malformed_ordinals(
    ordinals: tuple[object, object, object],
) -> None:
    runner = _runner()
    overlay = (
        runner.OverlayRow("prod/a.py", "100644", "1" * 40),
        runner.OverlayRow("prod/b.py", "100644", "2" * 40),
        runner.OverlayRow("tests/test.py", "100644", "3" * 40),
    )

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_overlay_partition(
            overlay,
            test_slice=runner.OverlaySlice(
                "tests",
                ordinals[0],
                ("tests/test.py",),
            ),
            cluster_slices=(
                runner.OverlaySlice("a", ordinals[1], ("prod/a.py",)),
                runner.OverlaySlice("b", ordinals[2], ("prod/b.py",)),
            ),
        )

    assert caught.value.code == "feasibility_git_partition_invalid"


@pytest.mark.parametrize("field", ("slice_id", "path"))
def test_overlay_partition_normalizes_malformed_unicode(
    field: str,
) -> None:
    runner = _runner()
    overlay = (
        runner.OverlayRow("prod/a.py", "100644", "1" * 40),
        runner.OverlayRow("tests/test.py", "100644", "2" * 40),
    )
    test_slice = runner.OverlaySlice(
        "\ud800" if field == "slice_id" else "tests",
        0,
        ("\ud800",) if field == "path" else ("tests/test.py",),
    )

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_overlay_partition(
            overlay,
            test_slice=test_slice,
            cluster_slices=(
                runner.OverlaySlice("cluster", 1, ("prod/a.py",)),
            ),
        )

    assert caught.value.code == "feasibility_git_partition_invalid"


def test_overlay_partition_normalizes_malformed_overlay_path() -> None:
    runner = _runner()
    overlay = (
        runner.OverlayRow("\ud800", "100644", "1" * 40),
        runner.OverlayRow("prod/a.py", "100644", "2" * 40),
    )

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_overlay_partition(
            overlay,
            test_slice=runner.OverlaySlice("tests", 0, ("\ud800",)),
            cluster_slices=(
                runner.OverlaySlice("cluster", 1, ("prod/a.py",)),
            ),
        )

    assert caught.value.code == "feasibility_git_partition_invalid"


@pytest.mark.parametrize("path", ("../tests/test.py", "/tests/test.py"))
def test_overlay_partition_validates_slice_paths_with_canonical_leaf_rules(
    path: str,
) -> None:
    runner = _runner()
    overlay = (
        runner.OverlayRow("prod/a.py", "100644", "1" * 40),
        runner.OverlayRow("tests/test.py", "100644", "2" * 40),
    )

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_overlay_partition(
            overlay,
            test_slice=runner.OverlaySlice("tests", 0, (path,)),
            cluster_slices=(
                runner.OverlaySlice("cluster", 1, ("prod/a.py",)),
            ),
        )

    assert caught.value.code == "feasibility_git_partition_invalid"
    cause = caught.value.__cause__
    assert isinstance(cause, runner.FeasibilityProofError)
    assert cause.code == "feasibility_git_overlay_invalid"


@pytest.mark.parametrize(
    "tamper",
    ("missing", "overlap", "duplicate_id", "unknown", "empty", "reordered"),
)
def test_overlay_partition_rejects_non_closed_slice_assignment(
    tamper: str,
) -> None:
    runner = _runner()
    overlay = (
        runner.OverlayRow("prod/a.py", "100644", "1" * 40),
        runner.OverlayRow("prod/b.py", "100644", "2" * 40),
        runner.OverlayRow("tests/test.py", "100644", "3" * 40),
    )
    test_slice = runner.OverlaySlice("tests", 0, ("tests/test.py",))
    clusters = [
        runner.OverlaySlice("a", 1, ("prod/a.py",)),
        runner.OverlaySlice("b", 2, ("prod/b.py",)),
    ]
    if tamper == "missing":
        clusters.pop()
    elif tamper == "overlap":
        clusters[1] = runner.OverlaySlice("b", 2, ("prod/a.py",))
    elif tamper == "duplicate_id":
        clusters[1] = runner.OverlaySlice("a", 2, ("prod/b.py",))
    elif tamper == "unknown":
        clusters[1] = runner.OverlaySlice("b", 2, ("prod/unknown.py",))
    elif tamper == "empty":
        test_slice = runner.OverlaySlice("tests", 0, ())
    elif tamper == "reordered":
        clusters = [
            runner.OverlaySlice("all", 1, ("prod/b.py", "prod/a.py")),
        ]
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_overlay_partition(
            overlay,
            test_slice=test_slice,
            cluster_slices=tuple(clusters),
        )

    assert caught.value.code == "feasibility_git_partition_invalid"


def test_addition_numstat_separates_git_lf_additions_from_physical_lines(
    tmp_path: Path,
) -> None:
    runner = _runner()
    binding = _live_executable_binding(Path("/usr/bin/git"), "--version")
    base_root = tmp_path / "base"
    overlay_root = tmp_path / "overlay"
    base_root.mkdir()
    overlay_root.mkdir()
    base_path, _, _, base_tree_oid, _ = _bare_object_fixture(base_root)
    overlay_path, blob_oid, _, _, _ = _bare_object_fixture(
        overlay_root,
        blob_payload=b"alpha\rbeta",
    )
    primary = runner.GitObjectStore(overlay_path, binding)
    fallback = runner.GitObjectStore(base_path, binding)
    pair = runner.GitObjectPair(primary, fallback)

    rows = runner.derive_addition_numstat(
        pair,
        base_leaves=runner.read_tree_leaves(fallback, base_tree_oid),
        overlay=(runner.OverlayRow("new.py", "100644", blob_oid),),
    )

    assert rows == (runner.NumstatRow("new.py", 1, 0, 2),)


def test_addition_numstat_normalizes_malformed_overlay_path(
    tmp_path: Path,
) -> None:
    runner = _runner()
    binding = _live_executable_binding(Path("/usr/bin/git"), "--version")
    base_root = tmp_path / "base"
    overlay_root = tmp_path / "overlay"
    base_root.mkdir()
    overlay_root.mkdir()
    base_path, _, _, base_tree_oid, _ = _bare_object_fixture(base_root)
    overlay_path, blob_oid, _, _, _ = _bare_object_fixture(overlay_root)
    primary = runner.GitObjectStore(overlay_path, binding)
    fallback = runner.GitObjectStore(base_path, binding)
    pair = runner.GitObjectPair(primary, fallback)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.derive_addition_numstat(
            pair,
            base_leaves=runner.read_tree_leaves(fallback, base_tree_oid),
            overlay=(runner.OverlayRow("\ud800", "100644", blob_oid),),
        )

    assert caught.value.code == "feasibility_git_numstat_invalid"


@pytest.mark.parametrize("payload", (b"binary\0payload", b"invalid-utf8-\xff"))
def test_derive_addition_numstat_rejects_binary_or_non_utf8_blob(
    payload: bytes,
    tmp_path: Path,
) -> None:
    runner = _runner()
    binding = _live_executable_binding(Path("/usr/bin/git"), "--version")
    base_root = tmp_path / "base"
    overlay_root = tmp_path / "overlay"
    base_root.mkdir()
    overlay_root.mkdir()
    base_path, _, _, base_tree_oid, _ = _bare_object_fixture(base_root)
    overlay_path, blob_oid, _, _, _ = _bare_object_fixture(
        overlay_root,
        blob_payload=payload,
    )
    primary = runner.GitObjectStore(overlay_path, binding)
    fallback = runner.GitObjectStore(base_path, binding)
    pair = runner.GitObjectPair(primary, fallback)
    base_leaves = runner.read_tree_leaves(fallback, base_tree_oid)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.derive_addition_numstat(
            pair,
            base_leaves=base_leaves,
            overlay=(runner.OverlayRow("new.bin", "100644", blob_oid),),
        )

    assert caught.value.code == "feasibility_git_numstat_invalid"


def _directed_ast_fixture(
    tmp_path: Path,
) -> tuple[ModuleType, object, tuple[object, ...], tuple[object, ...]]:
    runner = _runner()
    source_a = (
        b"def marker(function):\n"
        b"    return function\n"
        b"\n"
        b"@marker\n"
        b"def alpha(value):\n"
        b"    return value + 1\n"
        b"\n"
        b"def use_beta(value):\n"
        b"    return peer.beta(value)\n"
        b"\n"
        b"def local_alpha(value):\n"
        b"    return alpha(value)\n"
    )
    source_b = (
        b"def beta(value):\n"
        b"    return value * 2\n"
        b"\n"
        b"def use_alpha(value):\n"
        b"    return alpha(value)\n"
    )
    binding = _live_executable_binding(Path("/usr/bin/git"), "--version")
    primary_root = tmp_path / "primary"
    fallback_root = tmp_path / "fallback"
    primary_root.mkdir()
    fallback_root.mkdir()
    primary_path, source_a_oid, _, _, _ = _bare_object_fixture(
        primary_root,
        blob_payload=source_a,
    )
    source_b_oid = _write_git_object(primary_path, "blob", source_b)
    fallback_path, _, _, _, _ = _bare_object_fixture(
        fallback_root,
        blob_payload=b"def unrelated():\n    return None\n",
    )
    reader = runner.GitObjectPair(
        runner.GitObjectStore(primary_path, binding),
        runner.GitObjectStore(fallback_path, binding),
    )
    node_id = "tests/test_round_trip.py::test_round_trip"
    edges = (
        runner.DirectedAstEdge(
            edge_id="edge-alpha",
            producer=runner.AstNodeRef(
                path="pkg/a.py",
                blob_oid=source_a_oid,
                node_type="FunctionDef",
                name="alpha",
                span=runner.AstSpan(5, 0, 6, 20),
            ),
            consumer=runner.AstNodeRef(
                path="pkg/b.py",
                blob_oid=source_b_oid,
                node_type="Call",
                name="alpha",
                span=runner.AstSpan(5, 11, 5, 23),
            ),
            pytest_node_id=node_id,
        ),
        runner.DirectedAstEdge(
            edge_id="edge-beta",
            producer=runner.AstNodeRef(
                path="pkg/b.py",
                blob_oid=source_b_oid,
                node_type="FunctionDef",
                name="beta",
                span=runner.AstSpan(1, 0, 2, 20),
            ),
            consumer=runner.AstNodeRef(
                path="pkg/a.py",
                blob_oid=source_a_oid,
                node_type="Call",
                name="beta",
                span=runner.AstSpan(9, 11, 9, 27),
            ),
            pytest_node_id=node_id,
        ),
    )
    transitions = (
        runner.CallTransition(
            edge_id="edge-alpha",
            pytest_node_id=node_id,
            outcome="passed",
            caller_path="pkg/b.py",
            caller_line=5,
            callee_path="pkg/a.py",
            callee_name="alpha",
            callee_first_line=4,
            callee_line_hits=(5, 6),
        ),
        runner.CallTransition(
            edge_id="edge-beta",
            pytest_node_id=node_id,
            outcome="passed",
            caller_path="pkg/a.py",
            caller_line=9,
            callee_path="pkg/b.py",
            callee_name="beta",
            callee_first_line=1,
            callee_line_hits=(1, 2),
        ),
    )
    return runner, reader, edges, transitions


def test_directed_ast_edges_accept_two_directions_and_decorated_definition(
    tmp_path: Path,
) -> None:
    runner, reader, edges, transitions = _directed_ast_fixture(tmp_path)

    runner.validate_directed_ast_edges(
        reader,
        edges=edges,
        transitions=transitions,
    )

    with pytest.raises(FrozenInstanceError):
        edges[0].producer.span.start_line = 4


@pytest.mark.parametrize(
    ("callee_line_hit", "accepted"),
    ((1, False), (2, False), (3, False), (4, True)),
)
def test_directed_ast_edge_requires_body_statement_line_hit(
    callee_line_hit: int,
    accepted: bool,
    tmp_path: Path,
) -> None:
    runner, reader, edge_values, transition_values = _directed_ast_fixture(tmp_path)
    source = (
        b"def alpha(\n"
        b"    value: int = 1,\n"
        b") -> int:\n"
        b"    return value + 1\n"
    )
    producer_oid = _write_git_object(reader._primary.repository, "blob", source)
    edge = replace(
        edge_values[0],
        producer=replace(
            edge_values[0].producer,
            path="pkg/multiline.py",
            blob_oid=producer_oid,
            span=runner.AstSpan(1, 0, 4, 20),
        ),
    )
    transition = replace(
        transition_values[0],
        callee_path="pkg/multiline.py",
        callee_first_line=1,
        callee_line_hits=(callee_line_hit,),
    )

    if accepted:
        runner.validate_directed_ast_edges(
            reader,
            edges=(edge, edge_values[1]),
            transitions=(transition, transition_values[1]),
        )
    else:
        with pytest.raises(runner.FeasibilityProofError) as caught:
            runner.validate_directed_ast_edges(
                reader,
                edges=(edge, edge_values[1]),
                transitions=(transition, transition_values[1]),
            )

        assert caught.value.code == "feasibility_ast_edge_invalid"


@pytest.mark.parametrize(
    "tamper",
    (
        "swapped_endpoints",
        "missing_transition",
        "extra_transition",
        "duplicate_transition",
        "reordered_transition",
        "non_passed",
        "same_path",
        "same_blob",
        "reordered_edges",
        "duplicate_edge",
    ),
)
def test_directed_ast_edges_reject_closed_edge_transition_tamper(
    tamper: str,
    tmp_path: Path,
) -> None:
    runner, reader, edge_values, transition_values = _directed_ast_fixture(tmp_path)
    edges = tuple(edge_values)
    transitions = tuple(transition_values)
    first_edge = edges[0]
    first_transition = transitions[0]
    if tamper == "swapped_endpoints":
        edges = (
            replace(
                first_edge,
                producer=first_edge.consumer,
                consumer=first_edge.producer,
            ),
            edges[1],
        )
        transitions = (
            replace(
                first_transition,
                caller_path=first_edge.producer.path,
                caller_line=5,
                callee_path=first_edge.consumer.path,
                callee_name=first_edge.consumer.name,
                callee_first_line=5,
                callee_line_hits=(5,),
            ),
            transitions[1],
        )
    elif tamper == "missing_transition":
        transitions = transitions[:1]
    elif tamper == "extra_transition":
        transitions = (*transitions, transitions[0])
    elif tamper == "duplicate_transition":
        transitions = (transitions[0], transitions[0])
    elif tamper == "reordered_transition":
        transitions = tuple(reversed(transitions))
    elif tamper == "non_passed":
        transitions = (replace(first_transition, outcome="failed"), transitions[1])
    elif tamper == "same_path":
        edges = (
            replace(
                first_edge,
                producer=replace(
                    first_edge.producer,
                    path=first_edge.consumer.path,
                ),
            ),
            edges[1],
        )
        transitions = (
            replace(first_transition, callee_path=first_edge.consumer.path),
            transitions[1],
        )
    elif tamper == "same_blob":
        edges = (
            replace(
                first_edge,
                consumer=replace(
                    first_edge.consumer,
                    blob_oid=first_edge.producer.blob_oid,
                    span=runner.AstSpan(12, 11, 12, 23),
                ),
            ),
            edges[1],
        )
        transitions = (
            replace(first_transition, caller_line=12),
            transitions[1],
        )
    elif tamper == "reordered_edges":
        edges = tuple(reversed(edges))
        transitions = tuple(reversed(transitions))
    elif tamper == "duplicate_edge":
        edges = (edges[0], edges[0])
        transitions = (transitions[0], transitions[0])
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_directed_ast_edges(
            reader,
            edges=edges,
            transitions=transitions,
        )

    assert caught.value.code == "feasibility_ast_edge_invalid"


@pytest.mark.parametrize(
    "tamper",
    (
        "producer_path",
        "consumer_path",
        "producer_oid",
        "consumer_oid",
        "producer_type",
        "consumer_type",
        "producer_name",
        "consumer_name",
        "producer_span",
        "consumer_span",
        "caller_path",
        "caller_line",
        "callee_path",
        "callee_name",
        "callee_first_line",
        "line_hit_outside",
        "line_hit_empty",
        "line_hit_reordered",
        "line_hit_duplicate",
    ),
)
def test_directed_ast_edges_reject_endpoint_and_transition_field_tamper(
    tamper: str,
    tmp_path: Path,
) -> None:
    runner, reader, edge_values, transition_values = _directed_ast_fixture(tmp_path)
    edges = tuple(edge_values)
    transitions = tuple(transition_values)
    edge = edges[0]
    transition = transitions[0]
    if tamper == "producer_path":
        edge = replace(edge, producer=replace(edge.producer, path="pkg/../a.py"))
        transition = replace(transition, callee_path="pkg/../a.py")
    elif tamper == "consumer_path":
        edge = replace(edge, consumer=replace(edge.consumer, path="/pkg/b.py"))
        transition = replace(transition, caller_path="/pkg/b.py")
    elif tamper == "producer_oid":
        edge = replace(edge, producer=replace(edge.producer, blob_oid="0" * 40))
    elif tamper == "consumer_oid":
        edge = replace(edge, consumer=replace(edge.consumer, blob_oid="f" * 40))
    elif tamper == "producer_type":
        edge = replace(
            edge,
            producer=replace(edge.producer, node_type="AsyncFunctionDef"),
        )
    elif tamper == "consumer_type":
        edge = replace(edge, consumer=replace(edge.consumer, node_type="Name"))
    elif tamper == "producer_name":
        edge = replace(edge, producer=replace(edge.producer, name="other"))
        transition = replace(transition, callee_name="other")
    elif tamper == "consumer_name":
        edge = replace(edge, consumer=replace(edge.consumer, name="other"))
    elif tamper == "producer_span":
        edge = replace(
            edge,
            producer=replace(edge.producer, span=runner.AstSpan(5, 0, 6, 19)),
        )
    elif tamper == "consumer_span":
        edge = replace(
            edge,
            consumer=replace(edge.consumer, span=runner.AstSpan(5, 11, 5, 22)),
        )
    elif tamper == "caller_path":
        transition = replace(transition, caller_path="pkg/elsewhere.py")
    elif tamper == "caller_line":
        transition = replace(transition, caller_line=4)
    elif tamper == "callee_path":
        transition = replace(transition, callee_path="pkg/elsewhere.py")
    elif tamper == "callee_name":
        transition = replace(transition, callee_name="other")
    elif tamper == "callee_first_line":
        transition = replace(transition, callee_first_line=5)
    elif tamper == "line_hit_outside":
        transition = replace(transition, callee_line_hits=(4, 7))
    elif tamper == "line_hit_empty":
        transition = replace(transition, callee_line_hits=())
    elif tamper == "line_hit_reordered":
        transition = replace(transition, callee_line_hits=(6, 5))
    elif tamper == "line_hit_duplicate":
        transition = replace(transition, callee_line_hits=(5, 5))
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)
    edges = (edge, edges[1])
    transitions = (transition, transitions[1])

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_directed_ast_edges(
            reader,
            edges=edges,
            transitions=transitions,
        )

    assert caught.value.code == "feasibility_ast_edge_invalid"


@pytest.mark.parametrize(
    "tamper",
    (
        "edge_list",
        "transition_list",
        "empty_edges",
        "empty_transitions",
        "edge_object",
        "transition_object",
        "producer_object",
        "consumer_object",
        "span_object",
        "span_float",
        "span_bool_column",
        "pytest_id_empty",
        "pytest_id_non_utf8",
        "pytest_id_integer",
        "path_non_utf8",
        "caller_float",
        "callee_first_float",
        "line_hits_list",
        "line_hit_bool",
        "line_hit_zero",
    ),
)
def test_directed_ast_edges_reject_malformed_runtime_types(
    tamper: str,
    tmp_path: Path,
) -> None:
    runner, reader, edge_values, transition_values = _directed_ast_fixture(tmp_path)
    edges: object = tuple(edge_values)
    transitions: object = tuple(transition_values)
    edge = edge_values[0]
    transition = transition_values[0]
    if tamper == "edge_list":
        edges = list(edge_values)
    elif tamper == "transition_list":
        transitions = list(transition_values)
    elif tamper == "empty_edges":
        edges = ()
    elif tamper == "empty_transitions":
        transitions = ()
    elif tamper == "edge_object":
        edges = (object(),)
    elif tamper == "transition_object":
        transitions = (object(), object())
    elif tamper == "producer_object":
        edges = (replace(edge, producer=object()), edge_values[1])
    elif tamper == "consumer_object":
        edges = (replace(edge, consumer=object()), edge_values[1])
    elif tamper == "span_object":
        edges = (
            replace(edge, producer=replace(edge.producer, span=object())),
            edge_values[1],
        )
    elif tamper == "span_float":
        edges = (
            replace(
                edge,
                producer=replace(
                    edge.producer,
                    span=runner.AstSpan(5.0, 0, 6, 20),
                ),
            ),
            edge_values[1],
        )
    elif tamper == "span_bool_column":
        edges = (
            replace(
                edge,
                producer=replace(
                    edge.producer,
                    span=runner.AstSpan(5, False, 6, 20),
                ),
            ),
            edge_values[1],
        )
    elif tamper in {"pytest_id_empty", "pytest_id_non_utf8", "pytest_id_integer"}:
        node_id: object = {
            "pytest_id_empty": "",
            "pytest_id_non_utf8": "\ud800",
            "pytest_id_integer": 1,
        }[tamper]
        edges = (replace(edge, pytest_node_id=node_id), edge_values[1])
        transitions = (
            replace(transition, pytest_node_id=node_id),
            transition_values[1],
        )
    elif tamper == "path_non_utf8":
        edges = (
            replace(edge, producer=replace(edge.producer, path="\ud800")),
            edge_values[1],
        )
        transitions = (
            replace(transition, callee_path="\ud800"),
            transition_values[1],
        )
    elif tamper == "caller_float":
        transitions = (replace(transition, caller_line=5.0), transition_values[1])
    elif tamper == "callee_first_float":
        transitions = (
            replace(transition, callee_first_line=4.0),
            transition_values[1],
        )
    elif tamper == "line_hits_list":
        transitions = (
            replace(transition, callee_line_hits=[5, 6]),
            transition_values[1],
        )
    elif tamper == "line_hit_bool":
        transitions = (
            replace(transition, callee_line_hits=(True, 5)),
            transition_values[1],
        )
    elif tamper == "line_hit_zero":
        transitions = (
            replace(transition, callee_line_hits=(0, 5)),
            transition_values[1],
        )
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_directed_ast_edges(
            reader,
            edges=edges,
            transitions=transitions,
        )

    assert caught.value.code == "feasibility_ast_edge_invalid"


@pytest.mark.parametrize(
    "tamper",
    ("non_utf8", "syntax", "empty_source", "non_blob", "fallback_only"),
)
def test_directed_ast_edges_reject_unauthenticated_or_malformed_source(
    tamper: str,
    tmp_path: Path,
) -> None:
    runner, reader, edge_values, transitions = _directed_ast_fixture(tmp_path)
    edge = edge_values[0]
    repository = (
        reader._fallback.repository
        if tamper == "fallback_only"
        else reader._primary.repository
    )
    if tamper == "non_utf8":
        oid = _write_git_object(repository, "blob", b"invalid-\xff")
    elif tamper == "syntax":
        oid = _write_git_object(repository, "blob", b"def broken(:\n")
    elif tamper == "empty_source":
        oid = _write_git_object(repository, "blob", b"")
    elif tamper == "non_blob":
        oid = _write_git_object(repository, "tree", b"")
    elif tamper == "fallback_only":
        oid = _write_git_object(
            repository,
            "blob",
            b"def alpha(value):\n    return value\n",
        )
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)
    edges = (
        replace(edge, producer=replace(edge.producer, blob_oid=oid)),
        edge_values[1],
    )

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_directed_ast_edges(
            reader,
            edges=edges,
            transitions=transitions,
        )

    assert caught.value.code == "feasibility_ast_edge_invalid"


def test_feasibility_capture_manifest_record_validator_is_callable() -> None:
    runner = _runner()

    assert callable(
        getattr(runner, "validate_feasibility_capture_manifest_record", None)
    )


def test_feasibility_facts_deriver_is_callable() -> None:
    runner = _runner()

    assert callable(getattr(runner, "derive_feasibility_facts", None))


def _capture_manifest_fixture(
    runner: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    repository = (tmp_path / "authority-repository").resolve()
    ledger_root = repository / Path(
        "docs/plans/evidence/es-f1-large-scope-refreeze/"
        "feasibility-capture/ledgers"
    )
    ledger_root.mkdir(parents=True)
    monkeypatch.setattr(runner, "_REPOSITORY_ROOT", repository)
    sha = lambda character: "sha256:" + character * 64
    oid = lambda character: character * 40
    git = deepcopy(runner._FEASIBILITY_GIT_IDENTITY)
    python = deepcopy(runner._FEASIBILITY_PYTHON_IDENTITY)
    wrapper = deepcopy(runner._FEASIBILITY_BWRAP_IDENTITY)
    clusters = (
        "IDENTITY_CONFIG",
        "CONSTRUCTION_ADAPTERS",
        "PERSISTENCE_REBUILD",
        "INFERENCE_WORKFLOWS",
    )
    slice_ids = ("TEST_WITNESSES", *clusters)
    overlay_paths = (
        "tests/test_feature.py",
        "pkg/identity.py",
        "pkg/construction.py",
        "pkg/persistence.py",
        "pkg/inference.py",
    )
    overlay = [
        {
            "slice_id": slice_id,
            "ordinal": index,
            "path": path,
            "mode": "100644",
            "blob_oid": oid(str(index + 1)),
        }
        for index, (slice_id, path) in enumerate(zip(slice_ids, overlay_paths))
    ]
    variants = []
    variant_ids = (
        "full",
        "test_only",
        *(f"remove_one:{value}" for value in clusters),
    )
    for index, variant_id in enumerate(variant_ids):
        included = (
            list(slice_ids)
            if variant_id == "full"
            else [slice_ids[0]]
            if variant_id == "test_only"
            else [
                value
                for value in slice_ids
                if value != variant_id.removeprefix("remove_one:")
            ]
        )
        variants.append(
            {
                "variant_id": variant_id,
                "tree_oid": oid(chr(ord("a") + index)),
                "leaf_count": 10 + len(included),
                "included_slice_ids": included,
            }
        )
    source_roots = [
        (tmp_path / "retained" / f"source-{index}").resolve()
        for index in range(6)
    ]
    object_store = (tmp_path / "retained" / "objects.git").resolve()
    roots = []
    for path, variant in zip(source_roots, variants):
        root_id = runner._capture_root_id(
            root_kind="source_tree",
            canonical_path=str(path),
            variant_id=variant["variant_id"],
            content_name="tree_oid",
            content_value=variant["tree_oid"],
        )
        roots.append(
            {
                "root_id": root_id,
                "root_kind": "source_tree",
                "canonical_path": str(path),
                "variant_id": variant["variant_id"],
                "pre_purge_lstat": "directory",
                "tree_oid": variant["tree_oid"],
            }
        )
    store_snapshot = sha("4")
    roots.append(
        {
            "root_id": runner._capture_root_id(
                root_kind="git_object_store",
                canonical_path=str(object_store),
                variant_id=None,
                content_name="snapshot_sha256",
                content_value=store_snapshot,
            ),
            "root_kind": "git_object_store",
            "canonical_path": str(object_store),
            "pre_purge_lstat": "directory",
            "snapshot_sha256": store_snapshot,
        }
    )
    contracts = [
        {
            "cluster_id": cluster,
            "ordinal": index + 1,
            "primary_production_paths": [f"existing/{index}-{cluster.lower()}.py"],
            "responsibility_ids": [f"RESPONSIBILITY_{index}"],
            "baseline_ledger_id": f"baseline:{index}",
            "remove_one_ledger_id": f"remove_one:{index}",
        }
        for index, cluster in enumerate(clusters)
    ]
    edge_specs = (
        ("edge-construction-persistence", 2, 3, 1),
        ("edge-identity-construction", 1, 2, 0),
        ("edge-persistence-inference", 3, 4, 2),
    )
    transitions = [
        {
            "edge_id": edge_id,
            "pytest_node_id": f"tests/test_feature.py::test_cluster_{node_index}",
            "outcome": "passed",
            "caller_path": overlay_paths[consumer_index],
            "caller_line": 4,
            "callee_path": overlay_paths[producer_index],
            "callee_name": f"produce_{producer_index}",
            "callee_first_line": 1,
            "callee_line_hits": [1, 2],
        }
        for edge_id, producer_index, consumer_index, node_index in edge_specs
    ]
    roles = (
        "collection",
        *("baseline" for _ in range(4)),
        "green",
        "green",
        *("remove_one" for _ in range(4)),
        "adjacent",
    )
    role_indices = (0, 0, 1, 2, 3, 0, 1, 0, 1, 2, 3, 0)
    variant_for_ledger = (
        "test_only",
        *("test_only" for _ in range(4)),
        "full",
        "full",
        *(f"remove_one:{value}" for value in clusters),
        "full",
    )
    slice_for_ledger = (None, *clusters, None, None, *clusters, None)
    nodes = [f"tests/test_feature.py::test_cluster_{index}" for index in range(4)]
    ledgers = []
    for index, (role, role_index, variant_id, slice_id) in enumerate(
        zip(roles, role_indices, variant_for_ledger, slice_for_ledger)
    ):
        ledger_id = f"{role}:{role_index}"
        if role == "collection":
            selected_nodes = nodes
            node_outcomes = []
            counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
            exit_code = 0
        elif role in {"baseline", "remove_one"}:
            selected_nodes = [nodes[role_index]]
            node_outcomes = [
                {
                    "node_id": selected_nodes[0],
                    "outcome": "failed",
                    "failure_phase": "call",
                }
            ]
            counts = {"passed": 0, "failed": 1, "skipped": 0, "errors": 0}
            exit_code = 1
        elif role == "green":
            selected_nodes = nodes
            node_outcomes = [
                {"node_id": value, "outcome": "passed", "failure_phase": None}
                for value in selected_nodes
            ]
            counts = {"passed": 4, "failed": 0, "skipped": 0, "errors": 0}
            exit_code = 0
        else:
            selected_nodes = list(runner._FEASIBILITY_ADJACENT_NODE_IDS)
            node_outcomes = [
                {
                    "node_id": node_id,
                    "outcome": "passed",
                    "failure_phase": None,
                }
                for node_id in selected_nodes
            ]
            counts = {"passed": 2, "failed": 0, "skipped": 0, "errors": 0}
            exit_code = 0
        variant = next(value for value in variants if value["variant_id"] == variant_id)
        project_root = str(source_roots[variant_ids.index(variant_id)])
        target_argv = [python["literal_path"], "-m", "pytest", "-q", "tests"]
        if role == "adjacent":
            target_argv = [
                python["literal_path"],
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                *runner._FEASIBILITY_ADJACENT_NODE_IDS,
            ]
            home_root = str((tmp_path / "sandbox-home").resolve())
            tmp_root = str((tmp_path / "sandbox-tmp").resolve())
            cache_root = str((tmp_path / "sandbox-cache").resolve())
            artifact_root = str((tmp_path / "sandbox-artifacts").resolve())
            writable_mounts = [
                {
                    "relative_path": "memoized_data",
                    "host_path": cache_root,
                    "pre_tree": "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
                    "post_tree": "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
                },
                {
                    "relative_path": "training_outputs",
                    "host_path": artifact_root,
                    "pre_tree": "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
                    "post_tree": "9" * 40,
                }
            ]
            launcher_argv = list(
                runner._expected_bwrap_launcher_argv(
                    launcher_path=wrapper["literal_path"],
                    project_root=project_root,
                    home_root=home_root,
                    tmp_root=tmp_root,
                    writable_mounts=(
                        runner.WritableMountEvidence(
                            relative_path="memoized_data",
                            host_path=cache_root,
                            pre_tree="4b825dc642cb6eb9a060e54bf8d69288fbee4904",
                            post_tree="4b825dc642cb6eb9a060e54bf8d69288fbee4904",
                        ),
                        runner.WritableMountEvidence(
                            relative_path="training_outputs",
                            host_path=artifact_root,
                            pre_tree="4b825dc642cb6eb9a060e54bf8d69288fbee4904",
                            post_tree="9" * 40,
                        ),
                    ),
                    target_argv=tuple(target_argv),
                )
            )
            execution_envelope = {
                "kind": "bwrap_ro_project.v1",
                "launcher": wrapper,
                "launcher_argv": launcher_argv,
                "runtime_project_root": "/run/orc-pytest-project",
                "home_root": home_root,
                "tmp_root": tmp_root,
                "writable_mounts": writable_mounts,
            }
        else:
            execution_envelope = {
                "kind": "direct",
                "launcher": None,
                "launcher_argv": target_argv,
                "runtime_project_root": project_root,
                "home_root": None,
                "tmp_root": None,
                "writable_mounts": [],
            }
        active_transitions = (
            sorted(
                transitions,
                key=lambda value: (value["pytest_node_id"], value["edge_id"]),
            )
            if role == "green"
            else []
        )
        trace_specs = [
            {
                "edge_id": value["edge_id"],
                "pytest_node_id": value["pytest_node_id"],
                "caller_path": value["caller_path"],
                "caller_line": value["caller_line"],
                "callee_path": value["callee_path"],
                "callee_name": value["callee_name"],
                "callee_first_line": value["callee_first_line"],
            }
            for value in active_transitions
        ]
        authority = {
            "slice_id": slice_id,
            "runner_path": str(repository / runner.RUNNER_RELATIVE_PATH),
            "runner_sha256": sha("5"),
            "git": git,
            "python": python,
            "variant_id": variant_id,
            "project_root": project_root,
            "expected_tree": variant["tree_oid"],
            "argv": target_argv,
            "execution_envelope": execution_envelope,
            "expected_project_origins": [
                {"module_name": "pkg", "resolved_path": f"{project_root}/pkg.py"}
            ],
            "call_trace_specs": trace_specs,
        }
        envelope_value = runner._pytest_execution_envelope_from_record(
            execution_envelope
        )
        trace_values = tuple(
            runner.CallTraceSpec(
                edge_id=value["edge_id"],
                pytest_node_id=value["pytest_node_id"],
                caller_path=value["caller_path"],
                caller_line=value["caller_line"],
                callee_path=value["callee_path"],
                callee_name=value["callee_name"],
                callee_first_line=value["callee_first_line"],
            )
            for value in trace_specs
        )
        request = runner._pytest_capture_request_bytes(
            project_root=project_root,
            runtime_project_root=envelope_value.runtime_project_root,
            role=role,
            call_trace_specs=trace_values,
        )
        ledger_value = runner.PytestExecutionLedger(
            ledger_id=ledger_id,
            ordinal=index,
            role=role,
            role_index=role_index,
            slice_id=slice_id,
            runner_sha256=sha("5"),
            git=runner._executable_identity_from_record(git, label="git"),
            python=runner._executable_identity_from_record(python, label="python"),
            variant_id=variant_id,
            project_root=project_root,
            cwd=envelope_value.runtime_project_root,
            argv=tuple(target_argv),
            execution_envelope=envelope_value,
            environment=runner._pytest_capture_environment(
                Path(authority["runner_path"]),
                request,
                sandboxed=role == "adjacent",
            ),
            expected_tree=variant["tree_oid"],
            pre_tree=variant["tree_oid"],
            post_tree=variant["tree_oid"],
            collected_node_ids=tuple(selected_nodes),
            node_outcomes=tuple(
                runner.NodeOutcome(
                    value["node_id"], value["outcome"], value["failure_phase"]
                )
                for value in node_outcomes
            ),
            outcome_counts=runner.OutcomeCounts(**counts),
            exit_code=exit_code,
            project_origins=(
                runner.ProjectOrigin("pkg", f"{project_root}/pkg.py"),
            ),
            call_transitions=tuple(
                runner.CallTransition(
                    edge_id=value["edge_id"],
                    pytest_node_id=value["pytest_node_id"],
                    outcome=value["outcome"],
                    caller_path=value["caller_path"],
                    caller_line=value["caller_line"],
                    callee_path=value["callee_path"],
                    callee_name=value["callee_name"],
                    callee_first_line=value["callee_first_line"],
                    callee_line_hits=tuple(value["callee_line_hits"]),
                )
                for value in active_transitions
            ),
            elapsed_ns=1000 + index,
        )
        ledger = runner.pytest_execution_ledger_record(ledger_value)
        path = runner._FEASIBILITY_LEDGER_RELATIVE_PATHS[index]
        raw = runner.canonical_json_bytes(ledger)
        (repository / path).write_bytes(raw)
        ledgers.append(
            {
                "ledger_id": ledger_id,
                "ordinal": index,
                "role": role,
                "role_index": role_index,
                "path": path,
                "sha256": _sha256(raw),
                "deterministic_sha256": ledger["deterministic_sha256"],
                "elapsed_ns": ledger["elapsed_ns"],
                "authority": authority,
            }
        )
    edges = [
        {
            "edge_id": edge_id,
            "from_cluster": clusters[producer_index - 1],
            "to_cluster": clusters[consumer_index - 1],
            "producer": {
                "path": overlay_paths[producer_index],
                "blob_oid": overlay[producer_index]["blob_oid"],
                "node_type": "FunctionDef",
                "name": f"produce_{producer_index}",
                "span": {
                    "start_line": 1,
                    "start_column": 0,
                    "end_line": 2,
                    "end_column": 10,
                },
            },
            "consumer": {
                "path": overlay_paths[consumer_index],
                "blob_oid": overlay[consumer_index]["blob_oid"],
                "node_type": "Call",
                "name": f"produce_{producer_index}",
                "span": {
                    "start_line": 4,
                    "start_column": 4,
                    "end_line": 4,
                    "end_column": 20,
                },
            },
            "pytest_node_id": f"tests/test_feature.py::test_cluster_{node_index}",
            "ledger_id": "green:0",
        }
        for edge_id, producer_index, consumer_index, node_index in edge_specs
    ]
    manifest = {
        "schema_version": "es_f1_feasibility_capture_manifest.v1",
        "capture_id": "capture-" + "0" * 32,
        "captured_at": "2026-07-31T12:00:00-07:00",
        "lifecycle": "retained_pending_ordered_reviews",
        "bindings": {
            "runner_path": runner.RUNNER_RELATIVE_PATH,
            "runner_sha256": sha("5"),
            "git": git,
            "python": python,
            "execution_wrapper": wrapper,
            "frozen_base": deepcopy(runner._FEASIBILITY_FROZEN_BASE),
            "object_store": {
                "canonical_path": str(object_store),
                "snapshot_sha256": store_snapshot,
            },
        },
        "disposable_roots": roots,
        "tree_algebra": {
            "overlay": overlay,
            "cluster_contracts": contracts,
            "variants": variants,
            "numstat": [
                {
                    "path": path,
                    "additions": 10 + index,
                    "deletions": 0,
                    "physical_line_count": 10 + index,
                }
                for index, path in enumerate(overlay_paths)
            ],
        },
        "ledgers": ledgers,
        "directed_ast_edges": edges,
        "volatile_fields": [
            "captured_at",
            "ledgers.*.elapsed_ns",
            "ledgers.*.sha256",
        ],
        "deterministic_sha256": sha("7"),
        "record_sha256": sha("8"),
    }
    manifest["capture_id"] = runner._capture_expected_id(manifest)
    manifest["deterministic_sha256"] = _sha256(
        runner.canonical_json_bytes(runner._capture_deterministic_projection(manifest))
    )
    manifest["record_sha256"] = runner._capture_record_sha256(manifest)
    return manifest


def test_capture_manifest_validates_closed_bindings_and_derives_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    manifest = _capture_manifest_fixture(runner, tmp_path, monkeypatch)

    assert runner.validate_feasibility_capture_manifest_record(
        manifest,
        reobserve_roots=False,
    ) == manifest
    facts = runner.derive_feasibility_facts(manifest)

    assert facts["source_tree_before"] == "e64f3c05f5a0894f41c047d128a9040a2cda6764"
    assert facts["source_tree_after"] == "a" * 40
    assert [row["cluster_id"] for row in facts["unmet_clusters"]] == [
        "IDENTITY_CONFIG",
        "CONSTRUCTION_ADAPTERS",
        "PERSISTENCE_REBUILD",
        "INFERENCE_WORKFLOWS",
    ]
    assert facts["delta"] == {
        "implementation_additions": 50,
        "implementation_deletions": 0,
        "physical_line_count": 50,
        "changed_production_paths": [
            "pkg/identity.py",
            "pkg/construction.py",
            "pkg/persistence.py",
            "pkg/inference.py",
        ],
    }
    assert facts["non_collapse"] == {
        "distinct_production_blob_count": 4,
        "distinct_cluster_path_sets": 4,
    }


@pytest.mark.parametrize("substitution", ("leaf_symlink", "ancestor_symlink"))
def test_capture_manifest_rejects_symlinked_canonical_ledger_path_components(
    substitution: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    manifest = _capture_manifest_fixture(runner, tmp_path, monkeypatch)
    ledger = runner._REPOSITORY_ROOT / manifest["ledgers"][0]["path"]
    if substitution == "leaf_symlink":
        target = runner._REPOSITORY_ROOT / "identical-ledger-target.json"
        target.write_bytes(ledger.read_bytes())
        ledger.unlink()
        ledger.symlink_to(target)
    else:
        ledger_parent = ledger.parent
        target = ledger_parent.with_name("ledgers-real")
        ledger_parent.rename(target)
        ledger_parent.symlink_to(target, target_is_directory=True)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_feasibility_capture_manifest_record(
            manifest,
            reobserve_roots=False,
        )

    assert caught.value.code == "feasibility_capture_manifest_invalid"
    assert caught.value.detail == "ledgers[0]"


def _resign_capture_manifest(runner: ModuleType, manifest: dict[str, object]) -> None:
    manifest["capture_id"] = runner._capture_expected_id(manifest)
    manifest["deterministic_sha256"] = _sha256(
        runner.canonical_json_bytes(runner._capture_deterministic_projection(manifest))
    )
    manifest["record_sha256"] = runner._capture_record_sha256(manifest)


def test_capture_manifest_fixture_conforms_to_published_closed_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    manifest = _capture_manifest_fixture(runner, tmp_path, monkeypatch)
    schema = json.loads(
        (
            REPOSITORY_ROOT
            / "docs/plans/evidence/es-f1-large-scope-refreeze/feasibility-capture-manifest.schema.json"
        ).read_text(encoding="utf-8")
    )

    Draft202012Validator(schema).validate(manifest)


def test_capture_manifest_schema_rejects_noncanonical_ledger_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    manifest = _capture_manifest_fixture(runner, tmp_path, monkeypatch)
    schema = json.loads(
        (
            REPOSITORY_ROOT
            / "docs/plans/evidence/es-f1-large-scope-refreeze/feasibility-capture-manifest.schema.json"
        ).read_text(encoding="utf-8")
    )
    manifest["ledgers"][0]["path"] = "evidence/decoy-collection.json"

    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(manifest)


@pytest.mark.parametrize(
    "tamper",
    (
        "auth_argv",
        "auth_tree",
        "collection_extra",
        "derived_facts",
        "duplicate_ledger_path",
        "edge_blob",
        "ledger_role",
        "missing_variant",
        "noncanonical_ledger_path",
        "pinned_base",
        "repeated_witness",
        "root_tree",
        "adjacent_direct",
        "adjacent_extra_mount",
        "adjacent_extra_node",
        "adjacent_missing_mount",
        "adjacent_one_node",
        "adjacent_unchanged_training_mount",
        "adjacent_wrong_mount",
        "self_digest",
    ),
)
def test_capture_manifest_rejects_structural_and_authority_tamper(
    tamper: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()
    manifest = _capture_manifest_fixture(runner, tmp_path, monkeypatch)
    if tamper == "auth_argv":
        manifest["ledgers"][0]["authority"]["argv"] = [
            *manifest["ledgers"][0]["authority"]["argv"],
            "--substituted",
        ]
    elif tamper == "auth_tree":
        manifest["ledgers"][0]["authority"]["expected_tree"] = "0" * 40
    elif tamper == "collection_extra":
        binding = manifest["ledgers"][0]
        ledger_path = runner._REPOSITORY_ROOT / binding["path"]
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger["collected_node_ids"].append("tests/test_feature.py::test_extra")
        ledger = _resign_pytest_ledger_record(runner, ledger)
        raw = runner.canonical_json_bytes(ledger)
        ledger_path.write_bytes(raw)
        binding["sha256"] = _sha256(raw)
        binding["deterministic_sha256"] = ledger["deterministic_sha256"]
    elif tamper == "derived_facts":
        manifest["derived_facts"] = {"status": "passed"}
    elif tamper == "duplicate_ledger_path":
        manifest["ledgers"][1]["path"] = manifest["ledgers"][0]["path"]
    elif tamper == "edge_blob":
        manifest["directed_ast_edges"][0]["producer"]["blob_oid"] = "0" * 40
    elif tamper == "ledger_role":
        manifest["ledgers"][1]["role"] = "green"
    elif tamper == "missing_variant":
        manifest["tree_algebra"]["variants"].pop()
    elif tamper == "noncanonical_ledger_path":
        manifest["ledgers"][0]["path"] = "evidence/decoy-collection.json"
    elif tamper == "pinned_base":
        manifest["bindings"]["frozen_base"]["commit"] = "0" * 40
    elif tamper == "repeated_witness":
        first_node = "tests/test_feature.py::test_cluster_0"
        for ledger_index in (2, 3, 4, 8, 9, 10):
            binding = manifest["ledgers"][ledger_index]
            ledger_path = runner._REPOSITORY_ROOT / binding["path"]
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["collected_node_ids"] = [first_node]
            ledger["node_outcomes"][0]["node_id"] = first_node
            ledger = _resign_pytest_ledger_record(runner, ledger)
            raw = runner.canonical_json_bytes(ledger)
            ledger_path.write_bytes(raw)
            binding["sha256"] = _sha256(raw)
            binding["deterministic_sha256"] = ledger["deterministic_sha256"]
    elif tamper == "root_tree":
        manifest["disposable_roots"][0]["tree_oid"] = "0" * 40
    elif tamper == "adjacent_direct":
        authority = manifest["ledgers"][11]["authority"]
        authority["execution_envelope"] = {
            "kind": "direct",
            "launcher": None,
            "launcher_argv": list(authority["argv"]),
            "runtime_project_root": authority["project_root"],
            "home_root": None,
            "tmp_root": None,
            "writable_mounts": [],
        }
    elif tamper in {"adjacent_one_node", "adjacent_extra_node"}:
        binding = manifest["ledgers"][11]
        ledger_path = runner._REPOSITORY_ROOT / binding["path"]
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        if tamper == "adjacent_one_node":
            ledger["collected_node_ids"].pop()
            ledger["node_outcomes"].pop()
            ledger["outcome_counts"]["passed"] = 1
        else:
            extra = "tests/torch/test_workflows_components.py::test_decoy"
            ledger["collected_node_ids"].append(extra)
            ledger["node_outcomes"].append(
                {"node_id": extra, "outcome": "passed", "failure_phase": None}
            )
            ledger["outcome_counts"]["passed"] = 3
        ledger = _resign_pytest_ledger_record(runner, ledger)
        raw = runner.canonical_json_bytes(ledger)
        ledger_path.write_bytes(raw)
        binding["sha256"] = _sha256(raw)
        binding["deterministic_sha256"] = ledger["deterministic_sha256"]
    elif tamper == "adjacent_wrong_mount":
        mount = manifest["ledgers"][11]["authority"]["execution_envelope"][
            "writable_mounts"
        ][0]
        mount["relative_path"] = "other_outputs"
    elif tamper == "adjacent_missing_mount":
        manifest["ledgers"][11]["authority"]["execution_envelope"][
            "writable_mounts"
        ].pop(0)
    elif tamper == "adjacent_extra_mount":
        mounts = manifest["ledgers"][11]["authority"]["execution_envelope"][
            "writable_mounts"
        ]
        extra = deepcopy(mounts[-1])
        extra["relative_path"] = "zz_other_outputs"
        extra["host_path"] = str((tmp_path / "other-outputs").resolve())
        mounts.append(extra)
    elif tamper == "adjacent_unchanged_training_mount":
        mount = manifest["ledgers"][11]["authority"]["execution_envelope"][
            "writable_mounts"
        ][1]
        mount["post_tree"] = mount["pre_tree"]
    elif tamper == "self_digest":
        manifest["record_sha256"] = "sha256:" + "0" * 64
    else:  # pragma: no cover - exhaustive parameter guard
        raise AssertionError(tamper)
    if tamper != "self_digest":
        _resign_capture_manifest(runner, manifest)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.validate_feasibility_capture_manifest_record(
            manifest,
            reobserve_roots=False,
        )

    assert caught.value.code == "feasibility_capture_manifest_invalid"
    if tamper == "repeated_witness":
        assert caught.value.detail == "ledgers.cluster_witness_independence"
