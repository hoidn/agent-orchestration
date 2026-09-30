"""Spike of evaluated execution, iteration 2, item B: the complete request of every effect, on both routes.

Throwaway. Review finding 3: the provider performer did not pass the resolved policy.
A recorder stands in for the provider executor and wraps the command executor, and
records every argument of every call with its defaults filled in, so a keyword that
one route omits shows as a difference. The real workflows and their scripted answers
come from `test_evaluated_execution_spike_programs.py`.

Iteration 3, item F: nothing is normalized. Each field in which the routes differ has a
rule, in `EXPECTED_DIFFERENCES`, that gives the value each route must send; a field not
listed must be equal, so a new difference fails. A structured argument is now rendered as
the flat route renders it (`json.dumps` defaults), so that difference is gone. Iteration 4:
the interpreter is pinned for the run and launched by its path (`command.command`).
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import os
import re
import shutil
from pathlib import Path

import pytest

from orchestrator.exec.step_executor import StepExecutor
from orchestrator.providers.executor import ProviderExecutor
from tests.experiments.test_evaluated_execution_spike_programs import REAL, ScriptedProviders, _flat_real, _spike_real

def _plain(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _plain(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


# The executors' own functions, taken before any test replaces them.
_PREPARE = inspect.signature(ProviderExecutor.prepare_invocation)
_EXECUTE = inspect.signature(ProviderExecutor.execute)
_COMMAND = StepExecutor.execute_command
_COMMAND_SIGNATURE = inspect.signature(StepExecutor.execute_command)


def _record(kind: str, signature: inspect.Signature, args: tuple, kwargs: dict) -> dict:
    bound = signature.bind(None, *args, **kwargs)
    bound.apply_defaults()
    return {"kind": kind, **{k: _plain(v) for k, v in bound.arguments.items() if k != "self"}}


class Recorder(ScriptedProviders):
    """Scripted provider answers; every provider and command request recorded with all its arguments."""

    def __init__(self, payloads: dict[str, list[dict]], respond=None) -> None:
        super().__init__(payloads, respond)
        self.requests: list[dict] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> "Recorder":
        prepare, execute = self.prepare_invocation, self.execute

        def recorded_prepare(executor, *args, **kwargs):
            self.requests.append(_record("provider", _PREPARE, args, kwargs))
            return prepare(*args, **kwargs)

        def recorded_execute(executor, invocation, **kwargs):
            call = _record("provider", _EXECUTE, (invocation,), kwargs)
            self.requests[-1].update({k: v for k, v in call.items() if k not in ("kind", "invocation")})
            return execute(invocation, **kwargs)

        def recorded_command(executor, *args, **kwargs):
            call = _record("command", _COMMAND_SIGNATURE, args, kwargs)
            self.requests.append({**call, "step_name": None, "output_capture": str(call["output_capture"])})
            return _COMMAND(executor, *args, **kwargs)

        monkeypatch.setattr(ProviderExecutor, "prepare_invocation", recorded_prepare)
        monkeypatch.setattr(ProviderExecutor, "execute", recorded_execute)
        monkeypatch.setattr(StepExecutor, "execute_command", recorded_command)
        return self


def is_generated_helper(request: dict) -> bool:
    """A command the flat route generates for itself (inline Python writing managed write roots); not an effect."""

    return request["kind"] == "command" and request["command"][:2] == ["python", "-c"]


BUNDLE, SITE_KEY = "ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY"
_FLAT_RESULT_PATH = re.compile(r"\.orchestrate/workflow_lisp/(entry|calls)/.+\.json")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


@dataclasses.dataclass(frozen=True)
class Where:
    """What the expected values depend on: the spike effect's identity and result path, and each route's run."""

    identity: str
    result_path: str  # relative to the spike's workspace
    workspace: Path
    flat_run_id: str


# Item F's rules. For each field in which the routes' requests differ, the value each route must send; a
# field not listed here must be equal. Each function asserts both sides.


def _context(flat: dict, spike: dict, where: Where) -> None:
    """Rule: a request carries no run state. The flat route passes its variable namespace, which a provider
    template or parameter can name as `${run.id}` or `${inputs.x}`; the built-in templates name none. On the
    spike a template naming one fails the attempt with missing placeholders."""

    assert {"run", "inputs"} <= set(flat["context"]) and flat["context"]["run"]["id"] == where.flat_run_id
    assert spike["context"] == {}


def _env(flat: dict, spike: dict, where: Where) -> None:
    """Rule: the result path is the attempt's own (identity and attempt), given relative to the workspace as
    the flat route gives its bundle path. A provider or command writes there and can read or quote it."""

    assert set(flat["env"]) == {BUNDLE} and _FLAT_RESULT_PATH.fullmatch(flat["env"][BUNDLE])
    assert spike["env"] == {BUNDLE: where.result_path}


def _prompt(flat: dict, spike: dict, where: Where) -> None:
    """Rule: the output contract block names the same result path as the environment; nothing else differs."""

    def rest(request: dict, path: str) -> str:
        line = f"- path: {path}\n"
        assert request["prompt_content"].count(line) == 1
        return request["prompt_content"].replace(line, "")

    assert rest(flat, flat["env"][BUNDLE]) == rest(spike, where.result_path)


def _site_key(flat: dict, spike: dict, where: Where) -> None:
    """Rule: the attempt's site key is the digest of the effect's identity, the same across attempts and
    resumes, as the flat route's is the digest of its run-independent visit site. The flat route sends
    none inside a call frame (`std/improve`'s procedures); a consumer (the ES provider boundary) then
    cannot attribute the attempt."""

    overlay = flat["execution_env_overlay"]
    assert overlay is None or (set(overlay) == {SITE_KEY} and _DIGEST.fullmatch(overlay[SITE_KEY]))
    assert spike["execution_env_overlay"] == {SITE_KEY: "sha256:" + hashlib.sha256(where.identity.encode()).hexdigest()}


def _cwd(flat: dict, spike: dict, where: Where) -> None:
    """Rule: the provider runs in the workspace, named. The flat route passes none and inherits the process's
    working directory, which is the workspace when the run is launched from it."""

    assert (flat["cwd"], spike["cwd"]) == (None, repr(where.workspace))


def _command(flat: dict, spike: dict, where: Where) -> None:
    """Rule: a program a command names bare (`python`) is the one PATH gave when the run started, pinned for
    the run and launched by its path; the rest of the command line is equal."""

    assert "/" not in flat["command"][0] and spike["command"][0] == shutil.which(flat["command"][0])
    assert flat["command"][1:] == spike["command"][1:]


EXPECTED_DIFFERENCES = {
    "provider.context": _context,
    "provider.env": _env,
    "provider.prompt_content": _prompt,
    "provider.execution_env_overlay": _site_key,
    "provider.cwd": _cwd,
    "command.env": _env,
    "command.command": _command,
}


def requests_on_both_routes(tmp_path: Path, name: str, monkeypatch: pytest.MonkeyPatch, respond=None) -> dict:
    """Per route: (value, effect requests); the flat route's generated helpers; where each spike request was."""

    from experiments.evaluated_execution_spike.memo import read_records
    from tests.experiments.test_evaluated_execution_spike import run_root

    observed = {}
    for route, run in (("flat", _flat_real), ("spike", _spike_real)):
        recorder = Recorder(REAL[name][4], respond).install(monkeypatch)
        value = json.loads(json.dumps(run(tmp_path / route, name, monkeypatch)))
        observed[route] = (value, [r for r in recorder.requests if not is_generated_helper(r)])
        observed[f"{route} helpers"] = [r for r in recorder.requests if is_generated_helper(r)]
    workspace = (tmp_path / "spike").resolve()
    flat_run_id = next((tmp_path / "flat" / ".orchestrate" / "runs").iterdir()).name
    observed["where"] = [Where(r["identity"], os.path.relpath(run_root(workspace) / r["result_path"], workspace),
                               workspace, flat_run_id)
                         for r in read_records(run_root(workspace)) if r["record"] == "started"]
    return observed


def assert_request_differences(flat: list[dict], spiked: list[dict], where: list[Where]) -> set[str]:
    """Each differing field is one of `EXPECTED_DIFFERENCES`, with the value its rule gives on each route."""

    found = set()
    for f, s, w in zip(flat, spiked, where, strict=True):
        for key in sorted({*f, *s}):
            field = f"{f['kind']}.{key}"
            if f.get(key) != s.get(key):
                assert field in EXPECTED_DIFFERENCES, (field, f.get(key), s.get(key))
                EXPECTED_DIFFERENCES[field](f, s, w)
                found.add(field)
    return found


@pytest.mark.parametrize("name", list(REAL))
def test_every_effect_receives_the_request_of_the_flat_route_apart_from_the_fields_the_rules_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Prompt content, policy, timeout, environment, argv and every keyword of every provider and command
    call, as sent: nothing is normalized."""

    observed = requests_on_both_routes(tmp_path, name, monkeypatch)

    (flat_value, flat), (spike_value, spiked) = observed["flat"], observed["spike"]
    assert spike_value == flat_value
    assert_request_differences(flat, spiked, observed["where"])


def test_each_listed_difference_occurs_and_a_structured_argument_is_sent_as_the_flat_route_sends_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    found, arguments = set(), {}
    for name in REAL:
        observed = requests_on_both_routes(tmp_path / name, name, monkeypatch)
        found |= assert_request_differences(observed["flat"][1], observed["spike"][1], observed["where"])
        arguments[name] = [(f["command"], s["command"]) for f, s in zip(observed["flat"][1], observed["spike"][1])
                           if f["kind"] == "command"]

    assert found == set(EXPECTED_DIFFERENCES)
    assert arguments["improve-example"][0][1][-1] == '[{"name": "seed", "value": 1}]'  # `json.dumps` defaults


def test_the_flat_routes_generated_helpers_write_call_frame_inputs_and_the_spike_runs_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule: none. They write the managed write roots of a call frame, a JSON map from hidden input names to
    bundle paths, under the orchestrator's own directory; a provider or command sees them only by reading it."""

    helpers = {name: requests_on_both_routes(tmp_path / name, name, monkeypatch) for name in REAL}

    assert {name: (len(o["flat helpers"]), len(o["spike helpers"])) for name, o in helpers.items()} == {
        "improve-example": (3, 0), "reviewed-change": (0, 0), "best-of-n": (2, 0)}
    for observed in helpers.values():
        for helper in observed["flat helpers"]:
            out, names = helper["command"][3], helper["command"][4::2]
            assert out.startswith(".orchestrate/workflow_lisp/") and names
            assert all(n.startswith("__write_root__") for n in names)


def test_the_resolved_policy_reaches_the_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    observed = requests_on_both_routes(tmp_path, "reviewed-change", monkeypatch)

    policies = [(r["provider_call_policy"], r["timeout_sec"]) for r in observed["spike"][1] if r["kind"] == "provider"]
    assert policies == [
        ({"model": "claude-sonnet-5-5", "effort": "medium"}, 5400),
        ({"model": "gpt-6-sol", "effort": "high"}, 5400),
        ({"model": "claude-sonnet-5-5", "effort": "medium"}, 5400),
        ({"model": "gpt-6-sol", "effort": "high"}, 5400),
    ]
