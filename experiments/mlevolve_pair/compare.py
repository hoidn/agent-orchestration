"""Run matched Python transports and capture the public ORC compile/run result."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from itertools import count
from pathlib import Path

from .search import run_search

ROOT = Path(__file__).resolve().parents[2]
PAIR = ROOT / "experiments" / "mlevolve_pair"


def _subprocess_leaves(workspace: Path):
    serial = count()

    def call(mode: str, request: dict[str, object]) -> object:
        bundle = workspace / f"leaf-{next(serial)}.json"
        environment = os.environ.copy()
        environment["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] = str(bundle)
        result = subprocess.run(
            [sys.executable, str(PAIR / "leaves.py"), mode,
             json.dumps(request, separators=(",", ":"))],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode or not bundle.is_file():
            raise RuntimeError(
                f"{mode} leaf failed ({result.returncode}): "
                f"{(result.stderr or result.stdout)[-2000:]}"
            )
        return json.loads(bundle.read_text(encoding="utf-8"))

    def proposal(operation: str, branch: str, candidate_a: int, candidate_b: int,
                 other_a: int, other_b: int, history_size: int) -> dict[str, int]:
        return call("proposal", {
            "operation": operation, "branch": branch,
            "candidate_a": candidate_a, "candidate_b": candidate_b,
            "other_a": other_a, "other_b": other_b,
            "history_size": history_size,
        })  # type: ignore[return-value]

    def evaluator(a: int, b: int) -> dict[str, object]:
        return call("evaluate", {"a": a, "b": b})  # type: ignore[return-value]

    return proposal, evaluator


def compare_python(max_evaluations: int = 12) -> dict[str, object]:
    started = time.perf_counter()
    direct = run_search(max_evaluations)
    direct_ms = (time.perf_counter() - started) * 1000
    with tempfile.TemporaryDirectory(prefix="mlevolve-python-") as temporary:
        proposal, evaluator = _subprocess_leaves(Path(temporary))
        started = time.perf_counter()
        transported = run_search(max_evaluations, proposal=proposal, evaluator=evaluator)
        subprocess_ms = (time.perf_counter() - started) * 1000
    return {
        "budget": max_evaluations,
        "same": direct == transported,
        "direct_ms": direct_ms,
        "subprocess_ms": subprocess_ms,
        "direct": direct,
        "subprocess": transported,
    }


def _run_orchestrator(workspace: Path, command: list[str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(ROOT) + (os.pathsep + pythonpath if pythonpath else "")
    return subprocess.run(
        [sys.executable, "-m", "orchestrator", *command],
        cwd=workspace,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _state_result(state_dir: Path) -> object | None:
    for path in state_dir.rglob("state.json"):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        outputs = state.get("workflow_outputs")
        if isinstance(outputs, dict):
            return outputs.get("__result__", outputs)
    return None


def _unflatten(value: object) -> object:
    if isinstance(value, list):
        return [_unflatten(item) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, object] = {}
    for key, item in value.items():
        parts = (key.removeprefix("return__")).split("__")
        target = result
        for part in parts[:-1]:
            nested = target.setdefault(part, {})
            if not isinstance(nested, dict):
                raise ValueError(f"conflicting flattened result path: {key}")
            target = nested
        target[parts[-1]] = _unflatten(item)
    return result


def compare_orc() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="mlevolve-orc-") as temporary:
        workspace = Path(temporary)
        target = workspace / "experiments" / "mlevolve_pair"
        target.mkdir(parents=True)
        for name in ("search.orc", "commands.json", "leaves.py"):
            shutil.copy2(PAIR / name, target / name)

        started = time.perf_counter()
        compilation = _run_orchestrator(workspace, [
            "compile", "experiments/mlevolve_pair/search.orc",
            "--entry-workflow", "run-search", "--source-root", "experiments",
            "--command-boundaries-file", "experiments/mlevolve_pair/commands.json",
            "--diagnostics-json",
        ])
        compile_ms = (time.perf_counter() - started) * 1000
        try:
            diagnostic: object = json.loads(compilation.stdout)
        except json.JSONDecodeError:
            diagnostic = {
                "stdout_tail": compilation.stdout[-3000:],
                "stderr_tail": compilation.stderr[-5000:],
            }
        result: dict[str, object] = {
            "status": "compiled" if compilation.returncode == 0 else "compile_failed",
            "compile_ms": compile_ms,
            "returncode": compilation.returncode,
            "diagnostic": diagnostic,
            "run": {"status": "not_run_compile_failed"},
        }
        if compilation.returncode:
            return result

        inputs = workspace / "inputs.json"
        inputs.write_text(json.dumps({"max_evaluations": 12, "target_score": 0.0}), encoding="utf-8")
        state_dir = workspace / "state"
        started = time.perf_counter()
        execution = _run_orchestrator(workspace, [
            "run", "experiments/mlevolve_pair/search.orc",
            "--entry-workflow", "run-search", "--source-root", "experiments",
            "--command-boundaries-file", "experiments/mlevolve_pair/commands.json",
            "--input-file", str(inputs), "--state-dir", str(state_dir), "--quiet",
        ])
        run_ms = (time.perf_counter() - started) * 1000
        output = _state_result(state_dir)
        result["run"] = {
            "status": "completed" if execution.returncode == 0 else "runtime_failed",
            "run_ms_including_compile": run_ms,
            "returncode": execution.returncode,
            "diagnostic": (execution.stderr or execution.stdout)[-3000:],
            "result": _unflatten(output),
        }
        result["same_as_python_default"] = _unflatten(output) == run_search()
        return result


def collect(budgets: list[int]) -> dict[str, object]:
    python_runs = [compare_python(budget) for budget in budgets]
    orc = compare_orc()
    files = {
        "orc_controller": PAIR / "search.orc",
        "python_controller": PAIR / "search.py",
        "command_config": PAIR / "commands.json",
        "shared_leaves": PAIR / "leaves.py",
        "harness_and_tests": (PAIR / "compare.py", ROOT / "tests/experiments/test_mlevolve_pair.py"),
    }
    source_lines = {
        name: sum(len(path.read_text(encoding="utf-8").splitlines()) for path in paths)
        if isinstance(paths, tuple) else len(paths.read_text(encoding="utf-8").splitlines())
        for name, paths in files.items()
    }
    return {
        "schema_version": "mlevolve_pair_evidence.v1",
        "working_directory": str(ROOT),
        "python_runs": python_runs,
        "orc": orc,
        "source_lines": source_lines,
        "limits": {
            "history": "typed trial list is controller state; the proposal leaf receives its scalar length",
            "python_recovery": "not implemented in this specimen",
            "provider_evidence": "scripted deterministic leaves only",
            "concurrency": "not measured; this comparison is sequential",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budgets", nargs="+", type=int, default=[3, 7, 12])
    parser.add_argument("--output", type=Path, default=PAIR / "evidence.json")
    args = parser.parse_args()
    payload = collect(args.budgets)
    evidence = json.dumps(payload, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(evidence + "\n", encoding="utf-8")
    if any(not row["same"] for row in payload["python_runs"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
