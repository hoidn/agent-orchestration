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
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ARMS = ("DIRECT", "DESIGN_QA", "PRODUCT_QA", "RICH")
INPUTS = {"task": "Implement the frozen F1 extension-boundary task.",
          "check_contract": "Run the frozen visible F1 check manifest.", "model": "gpt-5.5", "effort": "high"}
# Per case, each arm's child answer (a Bool value, or a failed launch) and the judge's scores.
CASES = {
    "all-pass": {"answers": {arm: True for arm in ARMS}, "scores": (0.8, 0.3)},
    "mixed": {"answers": {"DIRECT": True, "DESIGN_QA": False, "PRODUCT_QA": True, "RICH": "fail"},
              "scores": (0.6, 0.2)},
}


class StandIns:
    """The cells' and the evaluation's stand-ins; each call is logged to a file under `log_dir` (child processes
    count across a kill) and kept in `calls` (requests compared across routes). `hold` names a call to block on
    when the file `hold` exists: ("child", arm), ("judge", ordinal), or ("runtime", boundary)."""

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

        return TrialRuntimeDependencies(
            run_ref_dependencies=lambda cell, request: RunRefRuntimeDependencies(
                materialize_source=_materialize_trial_source, launch_child=self.launch),
            crash_hook=lambda event: self.block(("runtime", event)))

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


# 2. Kills of the spike from outside, and the present route interrupted -----------------------------------

# Window: how the child stops; the memo's attempts after resume.
# `hold`: a stand-in blocks inside the trial's `prepare` (a cell's child launch, the second judge call).


if __name__ == "__main__" and sys.argv[1:2] == ["child"]:
    child(sys.argv[2])
