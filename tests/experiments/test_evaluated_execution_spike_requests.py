"""Spike of evaluated execution, iteration 2, item B: the complete request of every effect, on both routes.

Throwaway. Review finding 3: the provider performer did not pass the resolved policy.
A recorder stands in for the provider executor and wraps the command executor, and
records every argument of every call with its defaults filled in, so a keyword that
one route omits shows as a difference. The real workflows and their scripted answers
come from `test_evaluated_execution_spike_programs.py`.

Differences that the design decides, and the test normalizes, are listed in
`DESIGN_DIFFERENCES`; the second test asserts that nothing else differs and that each
of them does occur.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import re
from pathlib import Path

import pytest

from orchestrator.exec.step_executor import StepExecutor
from orchestrator.providers.executor import ProviderExecutor
from tests.experiments.test_evaluated_execution_spike_programs import REAL, ScriptedProviders, _flat_real, _spike_real

# Every field in which the two routes' requests differ, with who must settle it and why.
DESIGN_DIFFERENCES = {
    # A performer reads no run state (section 9.2); the flat route hands the provider its variable namespace.
    "provider.context": ("design", "run state"),
    # Each attempt has its own result path under the run root (section 8, step 2).
    "provider.env": ("design", "result path"),
    "provider.prompt_content": ("design", "result path in the output contract block"),
    "command.env": ("design", "result path"),
    # The attempt's site key: the flat route's visit key, or none inside a call frame; the spike's identity digest.
    "provider.execution_env_overlay": ("design", "site key"),
    # The flat route relies on the process running in the workspace; the spike names it.
    "provider.cwd": ("spike", "working directory named instead of inherited"),
    # A list in `:argv`: `json.dumps` defaults against compact canonical JSON; section 9.1 is silent.
    "command.command": ("design", "JSON separators of a structured argument"),
}


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


_PATH_LINE = re.compile(r"^- path: .*$", re.MULTILINE)


def _result_path(env):
    return {**env, "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": "<result path>"} if isinstance(env, dict) else env


# How each difference of `DESIGN_DIFFERENCES` is normalized: only the part the design decides is replaced.
NORMALIZERS = {
    "provider.context": lambda value: "<run state>",
    "provider.env": _result_path,
    "provider.prompt_content": lambda value: _PATH_LINE.sub("- path: <result path>", value),
    "command.env": _result_path,
    "provider.execution_env_overlay": lambda value: "<site key>",
    "provider.cwd": lambda value: "<workspace>",
    "command.command": lambda value: [_json_tidy(argument) for argument in value],
}


def normalized(request: dict) -> dict:
    out = dict(request)
    for key, normalize in NORMALIZERS.items():
        kind, field = key.split(".")
        if out["kind"] == kind and field in out:
            out[field] = normalize(out[field])
    return out


def _json_tidy(argument: str):
    """A JSON argument compared by its value: the routes separate JSON differently (first report, finding 3)."""

    return json.loads(argument) if argument[:1] in ("[", "{") else argument


def requests_on_both_routes(tmp_path: Path, name: str, monkeypatch: pytest.MonkeyPatch, respond=None) -> dict:
    observed = {}
    for route, run in (("flat", _flat_real), ("spike", _spike_real)):
        recorder = Recorder(REAL[name][4], respond).install(monkeypatch)
        value = json.loads(json.dumps(run(tmp_path / route, name, monkeypatch)))
        observed[route] = (value, [r for r in recorder.requests if not is_generated_helper(r)])
        observed[f"{route} helpers"] = len(recorder.requests) - len(observed[route][1])
    return observed


def differing_fields(flat: list[dict], spiked: list[dict]) -> set[str]:
    return {
        f"{f['kind']}.{key}"
        for f, s in zip(flat, spiked, strict=True)
        for key in {*f, *s}
        if f.get(key) != s.get(key)
    }


@pytest.mark.parametrize("name", list(REAL))
def test_every_effect_receives_the_request_of_the_flat_route_apart_from_what_the_design_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Prompt content, policy, timeout, environment and every keyword of every provider and command call."""

    observed = requests_on_both_routes(tmp_path, name, monkeypatch)

    (flat_value, flat), (spike_value, spiked) = observed["flat"], observed["spike"]
    assert spike_value == flat_value
    assert [normalized(r) for r in spiked] == [normalized(r) for r in flat]
    assert differing_fields(flat, spiked) <= set(DESIGN_DIFFERENCES)


def test_the_differences_between_the_routes_are_exactly_the_listed_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = set()
    for name in REAL:
        observed = requests_on_both_routes(tmp_path / name, name, monkeypatch)
        found |= differing_fields(observed["flat"][1], observed["spike"][1])

    assert found == set(DESIGN_DIFFERENCES)


def test_the_resolved_policy_reaches_the_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    observed = requests_on_both_routes(tmp_path, "reviewed-change", monkeypatch)

    policies = [(r["provider_call_policy"], r["timeout_sec"]) for r in observed["spike"][1] if r["kind"] == "provider"]
    assert policies == [
        ({"model": "claude-sonnet-5-5", "effort": "medium"}, 5400),
        ({"model": "gpt-6-sol", "effort": "high"}, 5400),
        ({"model": "claude-sonnet-5-5", "effort": "medium"}, 5400),
        ({"model": "gpt-6-sol", "effort": "high"}, 5400),
    ]
