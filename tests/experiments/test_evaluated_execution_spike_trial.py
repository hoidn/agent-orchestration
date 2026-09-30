"""Spike of evaluated execution, iteration 4: a coordinator that is not a run reference, on a shipped workflow.

Throwaway. The coordinator is the trial runtime, unchanged; the workflow is the shipped
`workflows/experiments/qa_placement_effectiveness/qa_placement_trial.orc`, `compare`: four
bundle-mode arms, one visible check, a judge (`scorer`), one rep. The spike compiles it (no
hand-written node) and drives the trial through `experiments/evaluated_execution_spike/trial.py`.

Stand-ins, the same objects on both routes:
- each cell's source materializer is the ES tests' (`_materialize_trial_source`);
- each cell's child run answers by the case: an arm's value, or a failed launch;
- the check runner passes;
- the judge scores from what its prompt shows.
The arms' capsule is the present route's build of the same source.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE = "qa_placement_effectiveness/qa_placement_trial"
ARMS = ("DIRECT", "DESIGN_QA", "PRODUCT_QA", "RICH")
INPUTS = {"task": "Implement the frozen F1 extension-boundary task.",
          "check_contract": "Run the frozen visible F1 check manifest.", "model": "gpt-5.5", "effort": "high"}
# Per case, each arm's child answer (a Bool value, or a failed launch) and the judge's scores.
CASES = {
    "all-pass": {"answers": {arm: True for arm in ARMS}, "scores": (0.8, 0.3)},
    "mixed": {"answers": {"DIRECT": True, "DESIGN_QA": False, "PRODUCT_QA": True, "RICH": "fail"},
              "scores": (0.6, 0.2)},
}


def install(workspace: Path) -> Path:
    """The shipped module and the library it imports, copied; the entry's path."""

    for part in ("workflows/experiments/qa_placement_effectiveness", "workflows/library"):
        shutil.copytree(REPO / part, workspace / part, dirs_exist_ok=True)
    return workspace / "workflows/experiments/qa_placement_effectiveness/qa_placement_trial.orc"


def externs(entry: Path) -> tuple[dict, dict]:
    read = lambda name: json.loads((entry.parent / name).read_text(encoding="utf-8"))  # noqa: E731
    return read("providers.json"), read("prompts.json")


def source_roots(workspace: Path) -> tuple[Path, Path]:
    return workspace / "workflows" / "experiments", workspace / "workflows" / "library"


def build(workspace: Path):
    """The spike's closed program of `compare`, and the arms' capsule (directory, digest) from the present
    route's build of the same source."""

    from experiments.evaluated_execution_spike.closed import build_closed_program
    from experiments.evaluated_execution_spike.frontend import typecheck_program
    from orchestrator.workflow.run_ref.bundle_transport import write_bundle_capsule_directory
    from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle_in_memory
    from orchestrator.workflow_lisp.wcc.route import LoweringRoute

    entry = install(workspace)
    providers, prompts = externs(entry)
    typed = typecheck_program(entry, entry_workflow=f"{MODULE}::compare", source_roots=source_roots(workspace),
                              command_boundaries={}, provider_externs=providers, prompt_externs=prompts)
    built = build_frontend_bundle_in_memory(FrontendBuildRequest(
        source_path=entry, source_roots=source_roots(workspace), entry_workflow="compare",
        provider_externs_path=entry.parent / "providers.json", prompt_externs_path=entry.parent / "prompts.json",
        workspace_root=workspace, lowering_route=LoweringRoute.WCC_M4))
    capsule = workspace / "capsule"
    write_bundle_capsule_directory(capsule, built.run_ref_bundle_capsule)
    return build_closed_program(typed), capsule, built.run_ref_bundle_capsule.capsule_digest


class StandIns:
    """The cells' and the evaluation's stand-ins; each call is logged to a file under `log_dir` (child processes
    count across a kill) and kept in `calls` (requests compared across routes). `hold` names a call to block on
    when the file `hold` exists: ("child", arm) or ("judge", ordinal)."""

    def __init__(self, case: str, log_dir: Path, hold: tuple | None = None) -> None:
        self.case, self.log_dir, self.hold = case, log_dir, hold
        self.calls: dict[str, list] = {"child": [], "check": [], "judge": []}
        self.lock = threading.Lock()

    def log(self, kind: str, entry: object) -> int:
        with self.lock:
            self.calls[kind].append(entry)
            with open(self.log_dir / f"{kind}.log", "a", encoding="utf-8") as log:
                log.write(json.dumps(entry, default=str) + "\n")
            return len(self.calls[kind])

    def block(self, key: tuple) -> None:
        if self.hold == key and (self.log_dir / "hold").exists():
            (self.log_dir / "marker").write_text(repr(key), encoding="utf-8")
            while True:
                time.sleep(0.05)

    def launch(self, launch):
        from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
        from orchestrator.workflow.run_ref.runtime import RunRefChildProcessResult, RunRefRuntimeError

        arm = next(a for a in ARMS if launch.request_document["target_workflow_name"].endswith(
            {"DIRECT": "direct-treatment", "DESIGN_QA": "design-qa-treatment", "PRODUCT_QA": "product-qa-treatment",
             "RICH": "rich-treatment"}[a]))
        self.log("child", {"arm": arm, "child_run_id": launch.child_run_id, "workspace": str(launch.workspace),
                           "request": launch.request_document})
        self.block(("child", arm))
        answer = CASES[self.case]["answers"][arm]
        if answer == "fail":
            raise RunRefRuntimeError("run_ref_child_launch_failed", "stand_in_arm_failure")
        outputs = {"__result__": answer}
        state_dir = launch.workspace / ".orchestrate" / "runs" / launch.child_run_id
        state_dir.mkdir(parents=True)
        (state_dir / "state.json").write_bytes(canonical_json_bytes(
            {"run_id": launch.child_run_id, "status": "completed", "workflow_outputs": outputs}) + b"\n")
        result = {"schema_version": "run_ref_child_result.v1", "status": "completed",
                  "capsule_digest": launch.request_document["expected_capsule_digest"],
                  "target_workflow_name": launch.request_document["target_workflow_name"],
                  "child_run_id": launch.child_run_id, "workflow_outputs": outputs}
        return RunRefChildProcessResult(returncode=0, stdout=canonical_json_bytes(result) + b"\n", stderr=b"",
                                        duration_ms=1)

    def check(self, command, **kwargs):
        self.log("check", {"command": list(command), "cwd": str(kwargs.get("cwd"))})
        return subprocess.CompletedProcess(args=command, returncode=0, stdout=b"visible checks passed\n", stderr=b"")

    def runtime_dependencies(self):
        from orchestrator.workflow.run_ref.runtime import RunRefRuntimeDependencies
        from orchestrator.workflow.trial.runtime import TrialRuntimeDependencies
        from tests.experiments.test_es_qa_placement_workflows import _materialize_trial_source

        return TrialRuntimeDependencies(run_ref_dependencies=lambda cell, request: RunRefRuntimeDependencies(
            materialize_source=_materialize_trial_source, launch_child=self.launch))

    def evaluation_dependencies(self):
        from orchestrator.workflow.trial.adjudication import TrialEvaluationDependencies
        from tests.experiments.test_es_attempts import _Composer, _Registry

        return TrialEvaluationDependencies(provider_registry=_Registry(), prompt_composer=_Composer(),
                                           provider_executor=Judge(self), check_runner=self.check)


class Judge:
    """The scorer: a score by the case, from whether the packet in its prompt shows a validated `true`."""

    def __init__(self, stand_ins: StandIns) -> None:
        self.stand_ins = stand_ins

    def prepare_invocation(self, provider, params, context, **kwargs):
        prompt = kwargs["prompt_content"]
        ordinal = self.stand_ins.log("judge", {"provider": provider, "params": params.params, "context": context,
                                               "prompt": prompt, **{k: v for k, v in kwargs.items()
                                                                    if k != "prompt_content"}})
        (label,) = dict.fromkeys(re.findall(r"opaque-[0-9a-f]{64}", prompt))
        return (label, prompt, ordinal), None

    def execute(self, invocation, *, cwd):
        from orchestrator.providers.executor import ProviderExecutionResult

        label, prompt, ordinal = invocation
        self.stand_ins.block(("judge", ordinal))
        high, low = CASES[self.stand_ins.case]["scores"]
        score = high if '"kind":"validated_result","value":true' in prompt else low
        return ProviderExecutionResult(exit_code=0, stdout=json.dumps(
            {"candidate_id": label, "score": score, "summary": "scored by the stand-in",
             "citations": ["validated_result"]}).encode("utf-8"), stderr=b"", duration_ms=1)


def spike_route(workspace: Path, case: str, program, capsule: tuple, stand_ins: StandIns, *, hook=None):
    from experiments.evaluated_execution_spike.evaluator import evaluate
    from experiments.evaluated_execution_spike.trial import TrialCoordinator

    coordinator = TrialCoordinator(workspace, workspace / "run", (workspace.parent / f"{workspace.name}-run-ref").resolve(),
                                   capsule[0], capsule[1], stand_ins.runtime_dependencies(),
                                   stand_ins.evaluation_dependencies())
    return evaluate(program, inputs=INPUTS, workspace=workspace, run_root=workspace / "run", hook=hook,
                    coordinators={"trial": coordinator})


def flat_route(workspace: Path, case: str, stand_ins: StandIns, monkeypatch: pytest.MonkeyPatch):
    """The present route through the public run entry, with the same stand-ins: (exit code, outputs)."""

    from orchestrator.cli.commands.run import run_workflow
    from orchestrator.workflow.executor import WorkflowExecutor
    from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args, _run_argv

    entry = install(workspace)
    monkeypatch.setattr(WorkflowExecutor, "_trial_runtime_dependencies", stand_ins.runtime_dependencies(), raising=False)
    monkeypatch.setattr(WorkflowExecutor, "_trial_evaluation_dependencies", stand_ins.evaluation_dependencies(),
                        raising=False)
    roots = source_roots(workspace)
    files = {"source": entry, "source_root": roots[0], "providers": entry.parent / "providers.json",
             "prompts": entry.parent / "prompts.json"}
    (workspace / "inputs.json").write_text(json.dumps(INPUTS), encoding="utf-8")
    args = _run_args(files, input_file=workspace / "inputs.json")
    args.entry_workflow, args.source_root = "compare", [str(root) for root in roots]
    args.run_ref_root, args.emit_debug_yaml = str((workspace.parent / f"{workspace.name}-run-ref").resolve()), False
    argv = [a for a in _run_argv(files) if a != "--emit-debug-yaml"] + ["--source-root", str(roots[1])]
    argv[argv.index("--entry-workflow") + 1] = "compare"
    monkeypatch.chdir(workspace)
    with patch.object(sys, "argv", argv):
        result = run_workflow(args)
    return result.exit_code, dict(result.workflow_outputs)


# Kills from outside ---------------------------------------------------------------------------------------


def child(config_path: str) -> None:
    """Run or resume the trial in the configured workspace; block at the configured moment."""

    from experiments.evaluated_execution_spike.sites import ClosedProgram

    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    workspace = Path(config["workspace"])
    if config.get("pause_after_prepared"):
        from orchestrator.workflow.trial import runtime

        append = runtime.append_trial_cell_settlement

        def pause_after_prepared(*args, **kwargs):
            marker = workspace / "marker"
            if not marker.exists():
                marker.write_text("prepared", encoding="utf-8")
                while True:
                    time.sleep(0.05)
            return append(*args, **kwargs)

        runtime.append_trial_cell_settlement = pause_after_prepared
    hold = tuple(config["hold"]) if config.get("hold") else None
    stand_ins = StandIns(config["case"], workspace, hold)
    program = ClosedProgram.from_artifact(Path(config["program"]).read_text(encoding="utf-8"))

    def hook(event: str, identity: str) -> None:
        if event == config.get("window"):
            (workspace / "marker").write_text(event, encoding="utf-8")
            while True:
                time.sleep(0.05)
        if event == "started" and hold:
            (workspace / "hold").write_text("", encoding="utf-8")

    os.chdir(workspace)
    result = spike_route(workspace, config["case"], program, (Path(config["capsule"]), config["capsule_digest"]),
                         stand_ins, hook=hook)
    print(json.dumps({"value": stable(result.value)}))


def stable(value: dict) -> dict:
    """What a trial decides, without the parts drawn per run (labels, child run ids, times, paths)."""

    return {"outcomes": [{"arm_id": o["arm_id"], "rep": o["rep"], "variant": o["variant"], "value": o.get("value"),
                          "score": (o.get("evidence") or {}).get("score"),
                          "failure": (o.get("failure") or {}).get("code")} for o in value["outcomes"]],
            "aggregate_scores": value["verdict"]["aggregate_scores"],
            "per_repetition": value["verdict"]["per_repetition"],
            "disposition": {k: v for k, v in value["verdict"].items()
                            if k not in ("aggregate_scores", "per_repetition", "budget_accounting")}}


def _spawn(config: dict, root: Path) -> subprocess.Popen:
    path = root / f"config-{time.monotonic_ns()}.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.Popen([sys.executable, __file__, "child", str(path)], cwd=REPO, env=env, start_new_session=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def run_child(config: dict, root: Path) -> dict:
    """The child's result, or the last line of its error."""

    out, err = _spawn(config, root).communicate(timeout=300)
    if not out.strip():
        return {"error": re.sub(r"\x1b\[[0-9;]*m", "", err).strip().splitlines()[-1]}
    return json.loads(out.strip().splitlines()[-1])


def kill_child(config: dict, root: Path) -> None:
    process = _spawn(config, root)
    marker = Path(config["workspace"]) / "marker"
    deadline = time.monotonic() + 120
    while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert marker.exists(), process.communicate()[1][-3000:]
    time.sleep(0.3)  # let the other cells or judge calls in flight reach what they reach
    os.killpg(process.pid, signal.SIGKILL)
    process.communicate()
    marker.unlink()
    (Path(config["workspace"]) / "hold").unlink(missing_ok=True)


def ledger_rows(workspace: Path) -> list[dict]:
    paths = list(workspace.rglob("trial-events.jsonl"))  # the spike's run root, or the present route's run
    return [json.loads(line) for path in paths for line in path.read_text(encoding="utf-8").splitlines()]


def lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []




# 1. Both routes --------------------------------------------------------------------------------------------

RUN_ID, DIGEST, LABEL = r"run-ref-[0-9a-f]{40}", r"sha256:[0-9a-f]{64}", r"opaque-[0-9a-f]{64}"


def differences(flat, spike, path=""):
    """(path, flat, spike) for each leaf where the two values differ."""

    if isinstance(flat, dict) and isinstance(spike, dict):
        for key in sorted({*flat, *spike}):
            yield from differences(flat.get(key), spike.get(key), f"{path}.{key}")
    elif isinstance(flat, list) and isinstance(spike, list) and len(flat) == len(spike):
        for index, (a, b) in enumerate(zip(flat, spike)):
            yield from differences(a, b, f"{path}[{index}]")
    elif flat != spike:
        yield path, flat, spike


def labels(workspace: Path) -> set[str]:
    header = next(row for row in ledger_rows(workspace) if row["kind"] == "header")["payload"]
    return {row["opaque_label"] for row in header["sealed_opaque_label_map"]["bindings"]}


def assert_value_differences(flat: dict, spike: dict, workspaces: dict[str, Path]) -> set[str]:
    """Rules for the trial's value. A child run id derives from the visit (its run and step), an evaluation
    label from a salt drawn per run, a packet identity covers its label, times come from the clock, and the
    verdict's path from the request's digest, which covers the visit. Every other field must be equal:
    each arm's variant, value, score, failure, the aggregate scores, the ranking and the disposition."""

    found = set()
    for path, a, b in differences(flat, spike):
        field = path.rsplit(".", 1)[-1]
        found.add(re.sub(r"\[\d+\]", "[*]", path))
        if field == "child_run_id":
            launched = {route: {c["child_run_id"] for c in lines(workspaces[route] / "child.log")} for route in workspaces}
            assert a in launched["flat"] and b in launched["spike"] and re.fullmatch(RUN_ID, a), path
        elif field == "evaluation_label":
            assert a in labels(workspaces["flat"]) and b in labels(workspaces["spike"]), path
        elif field == "packet_identity":
            assert re.fullmatch(DIGEST, a) and re.fullmatch(DIGEST, b), path
        elif field.endswith("elapsed_ms"):  # an accounting's or the verdict's budget accounting's
            assert type(a) is int and type(b) is int, path
        elif re.fullmatch(r"\.return__outcomes\[\d+\]\.evidence\.check_results\[\d+\]\.duration_ms", path):
            assert all(type(value) is int and value >= 0 for value in (a, b)), path
        elif field == "return__verdict_artifact":
            assert all(re.fullmatch(r"artifacts/trials/[0-9a-f]{64}/verdict\.json", v) and (workspaces[r] / v).is_file()
                       for r, v in (("flat", a), ("spike", b))), path
        else:
            raise AssertionError(f"undeclared difference at {path}: {a!r} against {b!r}")
    return found


def test_trial_value_comparison_allows_only_check_clock_variance() -> None:
    def result(field, value):
        return {"return__outcomes": [{"evidence": {"check_results": [{field: value}]}}]}

    assert assert_value_differences(result("duration_ms", 0), result("duration_ms", 1), {}) == {
        ".return__outcomes[*].evidence.check_results[*].duration_ms"
    }
    for field, value in (("duration_ms", -1), ("duration_ms", "1"), ("duration_ms", True), ("score", 1)):
        with pytest.raises(AssertionError):
            assert_value_differences(result(field, 0), result(field, value), {})
    with pytest.raises(AssertionError):
        assert_value_differences({"duration_ms": 0}, {"duration_ms": 1}, {})


LAUNCH_DIFFERENCES = {"child_run_id", "request.child_run_id", "workspace", "request.clone_root",
                      "request.child_state_dir", "request.capsule_dir", "request.expected_capsule_digest"}


def assert_launch_differences(flat: dict, spike: dict, capsules: dict[str, tuple], run_ref_roots: dict[str, Path]):
    """Rules for a cell's child launch. Its run id and workspace derive from the visit and the cell's effect
    scope, under each route's run-ref root; the capsule is each route's own build of the same source, and its
    digest depends on where it was built (measured: two builds of one source in two directories differ)."""

    fields = lambda launch: {"child_run_id": launch["child_run_id"], "workspace": launch["workspace"],  # noqa: E731
                             **{f"request.{k}": v for k, v in launch["request"].items()}}
    routes = {"flat": fields(flat), "spike": fields(spike)}
    differing = {k for k in {*routes["flat"], *routes["spike"]} if routes["flat"].get(k) != routes["spike"].get(k)}
    assert differing == LAUNCH_DIFFERENCES, differing ^ LAUNCH_DIFFERENCES
    for route, launch in routes.items():
        assert launch["child_run_id"] == launch["request.child_run_id"] and re.fullmatch(RUN_ID, launch["child_run_id"])
        assert launch["workspace"] == launch["request.clone_root"]
        assert launch["request.child_state_dir"] == launch["workspace"] + "/.orchestrate/runs"
        assert Path(launch["workspace"]).is_relative_to(run_ref_roots[route])
        assert (launch["request.capsule_dir"], launch["request.expected_capsule_digest"]) == capsules[route]


def present_route_capsule(workspace: Path) -> tuple[str, str]:
    """The capsule the present route's run used: its build directory, and the digest of a build of the same
    source in the same workspace."""

    from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle_in_memory
    from orchestrator.workflow_lisp.wcc.route import LoweringRoute

    entry = workspace / "workflows/experiments/qa_placement_effectiveness/qa_placement_trial.orc"
    built = build_frontend_bundle_in_memory(FrontendBuildRequest(
        source_path=entry, source_roots=source_roots(workspace), entry_workflow="compare",
        provider_externs_path=entry.parent / "providers.json", prompt_externs_path=entry.parent / "prompts.json",
        workspace_root=workspace, lowering_route=LoweringRoute.WCC_M4))
    (directory,) = (workspace / ".orchestrate" / "build").glob("*/run_ref_bundle_capsule.v1")
    return str(directory), built.run_ref_bundle_capsule.capsule_digest


@pytest.mark.parametrize("case", list(CASES))
def test_both_routes_run_the_shipped_trial_and_differ_only_in_named_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    from tests.experiments.test_evaluated_execution_spike import outputs

    program, capsule, digest = build(tmp_path / "program")
    workspaces = {"flat": tmp_path / "flat", "spike": tmp_path / "spike"}
    stand_ins = {route: StandIns(case, workspace) for route, workspace in workspaces.items()}
    for workspace in workspaces.values():
        workspace.mkdir()
    with monkeypatch.context() as local:
        code, flat_value = flat_route(workspaces["flat"], case, stand_ins["flat"], local)
    monkeypatch.chdir(workspaces["spike"])
    spike_value = outputs(spike_route(workspaces["spike"], case, program, (capsule, digest), stand_ins["spike"]).value)
    flat_value = json.loads(json.dumps(flat_value, default=dict))  # the present route keeps mapping proxies

    assert code == 0
    assert_value_differences(flat_value, json.loads(json.dumps(spike_value)), workspaces)
    decided = {route: stable({"outcomes": value["return__outcomes"], "verdict": {
        k.removeprefix("return__verdict__"): v for k, v in value.items() if k.startswith("return__verdict__")
        and "__" not in k.removeprefix("return__verdict__")}}) for route, value in (("flat", flat_value),
                                                                                   ("spike", spike_value))}
    assert decided["flat"] == decided["spike"]
    assert decided["flat"]["outcomes"] == EXPECTED_DECISIONS[case]["outcomes"]
    calls = {route: s.calls for route, s in stand_ins.items()}
    capsules = {"flat": present_route_capsule(workspaces["flat"]), "spike": (str(capsule), digest)}
    run_ref_roots = {route: (tmp_path / f"{route}-run-ref").resolve() for route in workspaces}
    by_arm = {route: {c["arm"]: c for c in calls[route]["child"]} for route in calls}
    assert sorted(by_arm["flat"]) == sorted(by_arm["spike"]) == sorted(ARMS)
    for arm in ARMS:
        assert_launch_differences(by_arm["flat"][arm], by_arm["spike"][arm], capsules, run_ref_roots)
    # Checks: the same command line, in each route's cell workspace.
    for route in calls:
        assert all(Path(c["cwd"]).is_relative_to(run_ref_roots[route]) for c in calls[route]["check"])
    assert sorted(c["command"] for c in calls["flat"]["check"]) == sorted(c["command"] for c in calls["spike"]["check"])
    # The judge: the same provider, parameters and empty context; the same prompts but for each run's labels.
    unlabel = lambda call: {**call, "prompt": re.sub(LABEL, "<label>", call["prompt"])}  # noqa: E731
    as_sent = {route: sorted(json.dumps(unlabel(c), sort_keys=True) for c in calls[route]["judge"]) for route in calls}
    assert as_sent["flat"] == as_sent["spike"] and len(as_sent["flat"]) == 4


EXPECTED_DECISIONS = {
    "all-pass": {"outcomes": [{"arm_id": arm, "rep": 1, "variant": "Completed", "value": True, "score": 0.8,
                               "failure": None} for arm in ARMS]},
    "mixed": {"outcomes": [
        {"arm_id": "DIRECT", "rep": 1, "variant": "Completed", "value": True, "score": 0.6, "failure": None},
        {"arm_id": "DESIGN_QA", "rep": 1, "variant": "Completed", "value": False, "score": 0.2, "failure": None},
        {"arm_id": "PRODUCT_QA", "rep": 1, "variant": "Completed", "value": True, "score": 0.6, "failure": None},
        {"arm_id": "RICH", "rep": 1, "variant": "Failed", "value": None, "score": None,
         "failure": "run_ref_child_launch_failed"}]},
}



# 2. Kills of the spike from outside, and the present route interrupted -----------------------------------

# Window: how the child stops; what a resume gives with the runtime as it is; the memo's attempts after it.
# `hold`: a stand-in blocks inside the trial's `prepare` (a cell's child launch, the second judge call).
KILLS = {
    "resolved": ({"window": "resolved"}, [1]),
    "during a child run": ({"hold": ["child", "DESIGN_QA"]}, [1, 2]),
    "after cell preparation before settlement": ({"pause_after_prepared": True}, [1, 2]),
    "during the judge": ({"hold": ["judge", 2]}, [1, 2]),
    "after the trial's pending commit": ({"window": "finished"}, [1, 2]),
    "after the memo's commit": ({"window": "committed"}, [1]),
    "after the trial's final commit": ({"window": "settled"}, [1]),
}


def terminal_cells(rows: list[dict]) -> set[str]:
    return {row["payload"]["cell"]["arm_id"] for row in rows if row["kind"] in ("cell_e1_committed", "cell_failed")}


def unsettled_judged(rows: list[dict]) -> set[str]:
    """The arms whose evaluator attempt was allocated and not settled."""

    header = next(row for row in rows if row["kind"] == "header")["payload"]
    arm = {b["opaque_label"]: b["cell"]["arm_id"] for b in header["sealed_opaque_label_map"]["bindings"]}
    allocated = {row["payload"]["opaque_label"] for row in rows if row["kind"] == "evaluator_attempt_allocated"}
    settled = {row["payload"]["opaque_label"] for row in rows if row["kind"] == "evaluator_attempt_settled"}
    return {arm[label] for label in allocated - settled}


@pytest.mark.parametrize("case", list(CASES))
def test_every_kill_of_the_spike_and_what_its_resume_gives(tmp_path: Path, case: str) -> None:
    """A child is launched again only for a cell with no terminal record at the kill; no judge call repeats;
    the trial's visit is prepared and committed once. A kill during the judge spends each judge attempt in
    flight: the trial's evaluator budget (4 attempts, 4 packets) has none left."""

    from experiments.evaluated_execution_spike.memo import read_records
    from experiments.evaluated_execution_spike.sites import ClosedProgram
    from experiments.evaluated_execution_spike.view import derive_state

    program, capsule, digest = build(tmp_path / "program")
    (tmp_path / "program.json").write_text(program.artifact(), encoding="utf-8")

    def config(name: str, **extra) -> dict:
        (tmp_path / name).mkdir()
        return {"workspace": str(tmp_path / name), "program": str(tmp_path / "program.json"), "case": case,
                "capsule": str(capsule), "capsule_digest": digest, **extra}

    once = run_child(config("once"), tmp_path)["value"]
    for name, (stop, attempts) in KILLS.items():
        slug = re.sub(r"\W+", "-", name)
        stopped = config(slug, **stop)
        kill_child(stopped, tmp_path)
        workspace = tmp_path / slug
        at_kill = ledger_rows(workspace)
        if name == "after cell preparation before settlement":
            assert any(row["kind"] == "cell_prepared" for row in at_kill)
            assert not any(row["kind"] == "cell_settled" for row in at_kill)
        launched_at_kill = Counter(c["arm"] for c in lines(workspace / "child.log"))
        judged_at_kill = len(lines(workspace / "judge.log"))
        resumed = run_child({k: v for k, v in stopped.items() if k not in stop}, tmp_path)
        children = Counter(c["arm"] for c in lines(workspace / "child.log"))
        started = [r["attempt"] for r in read_records(workspace / "run") if r["record"] == "started"]

        expected = once
        if name == "during the judge":  # each attempt in flight is spent; the budget has no retry left
            spent = unsettled_judged(at_kill)
            expected = {**once, "outcomes": [
                {**o, "variant": "Failed", "value": None, "score": None, "failure": "trial_evaluator_attempts_exhausted"}
                if o["arm_id"] in spent and o["variant"] == "Completed" else o for o in once["outcomes"]]}
            assert resumed["value"]["outcomes"] == expected["outcomes"], name
        else:
            assert resumed == {"value": once}, name
        relaunched = {arm for arm in launched_at_kill if arm not in terminal_cells(at_kill)}
        kinds = Counter(row["kind"] for row in ledger_rows(workspace))
        assert children == Counter({arm: 1 + (arm in relaunched) for arm in ARMS}), name
        assert (len(lines(workspace / "judge.log")), started) == (4, attempts), name
        assert (kinds["trial_prepared"], kinds["trial_parent_committed"]) == (1, 1), name
        assert derive_state(ClosedProgram.from_artifact(program.artifact()), workspace / "run")["status"] == "completed"
        if name == "after cell preparation before settlement":
            from orchestrator.workflow.trial.runtime import _prepared_binding
            from orchestrator.workflow.trial.contracts import TrialCellKey
            from orchestrator.workflow.trial.ledger import _active_rows_for_cell, load_trial_event_ledger

            rows = ledger_rows(workspace)
            prepared = Counter(row["payload"]["cell"]["arm_id"] for row in rows
                               if row["kind"] == "cell_prepared")
            discarded = {row["payload"]["cell"]["arm_id"] for row in rows
                         if row["kind"] == "cell_discarded"}
            committed = {row["payload"]["cell"]["arm_id"] for row in rows
                         if row["kind"] == "cell_e1_committed"}
            duplicate_prepared = {arm for arm, count in prepared.items() if count > 1}
            assert duplicate_prepared & discarded
            assert sum(prepared.values()) > len(committed)
            ledger_path = next(workspace.rglob("trial-events.jsonl"))
            for arm in duplicate_prepared:
                cell = TrialCellKey(arm_id=arm, rep=1)
                binding = _prepared_binding(ledger_path, cell)
                active = _active_rows_for_cell(load_trial_event_ledger(ledger_path), cell)
                current = [row for row in active if row.kind == "cell_prepared"]
                assert len(current) == 1
                assert binding.record == current[0].payload["settled_result"]


@pytest.mark.parametrize("stop", ["judge", "prepared"])
def test_the_present_route_resuming_a_trial_interrupted_after_its_evaluation_began(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop: str
) -> None:
    """The same runtime on the present route: the run stops in process during the second judge call, or after
    the trial's pending commit (at the parent's state commit); `orchestrator resume` completes as the spike's
    resume does."""

    from orchestrator.cli.commands.resume import resume_workflow
    from orchestrator.state import StateManager
    from orchestrator.workflow.executor import WorkflowExecutor

    class Stop(BaseException):
        pass

    workspace = tmp_path / "flat"
    workspace.mkdir()
    with monkeypatch.context() as stopping:
        if stop == "judge":
            execute = Judge.execute
            stopping.setattr(Judge, "execute", lambda self, invocation, *, cwd: (_ for _ in ()).throw(Stop())
                             if invocation[2] == 2 else execute(self, invocation, cwd=cwd))
        else:
            finalize = StateManager.finalize_step_with_dataflow
            stopping.setattr(StateManager, "finalize_step_with_dataflow", lambda self, *a, **k: (
                (_ for _ in ()).throw(Stop()) if k.get("expected_step_type") == "trial" else finalize(self, *a, **k)))
        with pytest.raises(Stop):
            flat_route(workspace, "mixed", StandIns("mixed", workspace), stopping)
    at_stop = ledger_rows(workspace)
    resumed = StandIns("mixed", workspace)
    monkeypatch.setattr(WorkflowExecutor, "_trial_runtime_dependencies", resumed.runtime_dependencies(), raising=False)
    monkeypatch.setattr(WorkflowExecutor, "_trial_evaluation_dependencies", resumed.evaluation_dependencies(),
                        raising=False)
    monkeypatch.chdir(workspace)
    run_id = next((workspace / ".orchestrate" / "runs").iterdir()).name

    code = resume_workflow(run_id=run_id, retry_delay_ms=0)

    state = json.loads((workspace / ".orchestrate" / "runs" / run_id / "state.json").read_text(encoding="utf-8"))
    launches = {kind: len(calls) for kind, calls in resumed.calls.items()}
    outcomes = [{"arm_id": o["arm_id"], "variant": o["variant"], "failure": (o.get("failure") or {}).get("code")}
                for o in state["workflow_outputs"]["return__outcomes"]]
    spent = unsettled_judged(at_stop) if stop == "judge" else set()
    expected = [{"arm_id": o["arm_id"], "variant": "Failed" if o["arm_id"] in spent and o["variant"] == "Completed"
                 else o["variant"], "failure": "trial_evaluator_attempts_exhausted" if o["arm_id"] in spent
                 and o["variant"] == "Completed" else o["failure"]} for o in EXPECTED_DECISIONS["mixed"]["outcomes"]]
    assert (code, outcomes, launches) == (0, expected, {"child": 0, "check": 0, "judge": 0})


if __name__ == "__main__" and sys.argv[1:2] == ["child"]:
    child(sys.argv[2])
