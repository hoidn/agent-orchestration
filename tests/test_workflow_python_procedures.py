"""Python procedures and bounded control lower to compiler-owned `.orc`."""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from orchestrator.py.diagnostics import PythonFrontendError
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import evaluate_closed_program, site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.test_workflow_python_declarations import compile_source, generate


def _compile_with_commands(root, source, commands, *, providers=None):
    _module, generated, request = generate(
        root, source, providers=providers, name="sample"
    )
    manifest = root / "commands.json"
    manifest.write_text(json.dumps(commands), encoding="utf-8")
    built = build_closed_program_bundle(replace(request, command_boundaries_path=manifest))
    return generated, built, manifest


def _run_orc(root, source_path, manifest, *inputs):
    return subprocess.run(
        [
            sys.executable, "-m", "orchestrator", "run", str(source_path),
            "--entry-workflow", "run", "--command-boundaries-file", str(manifest),
            *(part for value in inputs for part in ("--input", value)),
        ],
        cwd=root,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).parents[1]),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_loop_done_continue_and_zero_exhaustion(tmp_path):
    _, _, built = compile_source(tmp_path, '''
    @record
    class State:
        count: int

    @workflow
    def run(limit: int) -> int:
        return loop(
            state=State(count=0),
            max=limit,
            body=lambda state: when(
                state.count >= 2,
                then=lambda: done(state.count),
                else_=lambda: cont(State(count=state.count + 1)),
            ),
            on_exhausted=lambda exhausted: exhausted.count,
        )
    ''')

    assert evaluate_closed_program(built.program, {"limit": 0}).value == 0
    assert evaluate_closed_program(built.program, {"limit": 1}).value == 1
    assert evaluate_closed_program(built.program, {"limit": 3}).value == 2

    mismatched_control = '''
    @record
    class State:
        count: int
    @workflow
    def run(flag: bool) -> int:
        return loop(
            state=State(count=0), max=1,
            body=lambda state: when(
                flag,
                then=lambda: done(1),
                else_=lambda: done("wrong"),
            ),
            on_exhausted=lambda exhausted: exhausted.count,
        )
    '''
    with pytest.raises(LispFrontendCompileError):
        compile_source(tmp_path / "mismatched-control", mismatched_control)

    mismatched_state = '''
    @record
    class State:
        count: int
    @workflow
    def run(flag: bool) -> int:
        return loop(
            state=State(count=0), max=1,
            body=lambda state: when(
                flag,
                then=lambda: done(0),
                else_=lambda: cont("wrong state type"),
            ),
            on_exhausted=lambda exhausted: exhausted.count,
        )
    '''
    with pytest.raises(LispFrontendCompileError):
        compile_source(tmp_path / "mismatched-state", mismatched_state)

    mixed_control = '''
    @record
    class State:
        count: int
    @workflow
    def run(flag: bool) -> int:
        return loop(
            state=State(count=0), max=1,
            body=lambda state: when(
                flag,
                then=lambda: done(0),
                else_=lambda: state.count,
            ),
            on_exhausted=lambda exhausted: exhausted.count,
        )
    '''
    with pytest.raises(LispFrontendCompileError):
        compile_source(tmp_path / "mixed-control", mixed_control)


def test_proc_pure_and_target_effect_contracts(tmp_path):
    command = {
        "probe": {
            "stable_command": ["python", "probe.py"],
            "closure": ["probe.py"],
        }
    }
    generated, _built, _manifest = _compile_with_commands(tmp_path / "inferred", '''
    probe = Command("probe", returns=int)

    @proc
    def inferred(value: int) -> int:
        return probe("python", "probe.py", value)

    @proc(effects=())
    def restricted(value: int) -> int:
        return value + 1

    @pure
    def increment(value: int) -> int:
        return value + 1

    @workflow
    def run(value: int) -> int:
        return increment(restricted(inferred(value)))
    ''', command)
    source = generated.source_path.read_text(encoding="utf-8")
    assert '(defproc inferred ' in source
    inferred_body = source.split('(defproc inferred ', 1)[1].split('\n  (', 1)[0]
    assert ":effects" not in inferred_body
    assert ":lowering" not in inferred_body
    assert '(defproc restricted ' in source and ':effects ()' in source
    assert '(defun increment ' in source

    generated_old, _built, _manifest = _compile_with_commands(
        tmp_path / "older", '''
        TARGET = "2.38"
        probe = Command("probe", returns=int)

        @workflow
        def child(value: int) -> int:
            return value + 1

        agent = Provider("agent")
        prompt = Prompt(text="Inspect", fills={}, returns=int)

        @proc(effects=(
            uses_command(probe), uses_provider(agent), calls_workflow(child),
        ))
        def effectful(value: int) -> int:
            probe("python", "probe.py", value)
            return child(agent(prompt()))

        @workflow
        def run(value: int) -> int:
            return effectful(value)
        ''', command, providers={"providers.agent": "stub"})
    old_source = generated_old.source_path.read_text(encoding="utf-8")
    assert ':effects ((uses-command probe) (uses-provider providers.agent) (calls-workflow child)) :lowering inline' in old_source

    with pytest.raises(PythonFrontendError, match="python_proc_effects_required"):
        compile_source(tmp_path / "missing-old-restriction", '''
        TARGET = "2.38"
        @proc
        def helper(value: int) -> int:
            return value + 1
        @workflow
        def run(value: int) -> int:
            return helper(value)
        ''')

    effectful_pure = '''
    probe = Command("probe", returns=int)
    @pure
    def helper(value: int) -> int:
        return probe("python", "probe.py", value)
    @workflow
    def run(value: int) -> int:
        return helper(value)
    '''
    with pytest.raises(LispFrontendCompileError):
        _compile_with_commands(tmp_path / "pure-effect", effectful_pure, command)

    recursive_pure = '''
    @pure
    def helper(value: int) -> int:
        return helper(value)
    @workflow
    def run(value: int) -> int:
        return helper(value)
    '''
    with pytest.raises(LispFrontendCompileError):
        compile_source(tmp_path / "pure-recursion", recursive_pure)


def test_command_uses_manifest_authority_and_native_arguments(tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "input.txt").write_text("input", encoding="utf-8")
    probe_script = tmp_path / "probe.py"
    probe_script.write_text(textwrap.dedent('''
    import json
    import os
    import sys
    from pathlib import Path

    count, report, ratio, inputs_path = sys.argv[1:]
    document = json.loads(Path(inputs_path).read_text(encoding="utf-8"))
    with Path("dispatches.jsonl").open("a", encoding="utf-8") as marker:
        marker.write(json.dumps({"argv": [count, report, ratio], "inputs": document}) + "\\n")
    output = {
        "count": int(count), "report": report, "ratio": float(ratio),
    }
    Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
        json.dumps(output), encoding="utf-8"
    )
    '''), encoding="utf-8")
    command = {"probe": {
        "stable_command": ["python", "probe.py"],
        "closure": ["probe.py"],
    }}
    source = '''
    class Report(RelPath, under="reports", must_exist=True):
        pass
    @record
    class Receipt:
        count: int
        report: Report
        ratio: float
    probe = Command("probe", returns=Receipt)
    @workflow
    def run(count: int, report: Report, ratio: float, note: str) -> Receipt:
        probe("python", "probe.py", count, report, ratio, inputs={"note": note})
        result = probe("python", "probe.py", count + 1, report, ratio,
                       inputs={"note": note})
        return Receipt(count=result.count + result.count,
                       report=result.report, ratio=result.ratio)
    '''
    generated, built, manifest = _compile_with_commands(
        tmp_path, source, command
    )
    emitted = generated.source_path.read_text(encoding="utf-8")
    assert ':argv ("python" "probe.py" count report ratio) :inputs ((note note))' in emitted
    assert ':argv ("python" "probe.py" (+ count 1) report ratio) :inputs ((note note))' in emitted
    assert built.program.sites

    result = _run_orc(
        tmp_path, generated.source_path, manifest,
        "count=5", "report=reports/input.txt", "ratio=0.5", "note=hello",
    )
    assert result.returncode == 0, result.stderr
    dispatches = [json.loads(row) for row in (tmp_path / "dispatches.jsonl").read_text().splitlines()]
    assert dispatches == [
        {"argv": ["5", "reports/input.txt", "0.5"], "inputs": {"note": "hello"}},
        {"argv": ["6", "reports/input.txt", "0.5"], "inputs": {"note": "hello"}},
    ]
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert snapshot.terminal.data == {"record": "terminal", "outcome": "completed",
        "value": {"count": 12, "report": "reports/input.txt", "ratio": 0.5}}
    assert len(snapshot.active_commits) == 2

    with pytest.raises(LispFrontendCompileError, match="command_adapter_missing_contract"):
        _compile_with_commands(tmp_path / "missing", source, {})
    with pytest.raises(LispFrontendCompileError, match="command_result_argv_invalid"):
        _compile_with_commands(tmp_path / "prefix", source, {
            "probe": {"stable_command": ["python", "other.py"], "closure": []}
        })

    invalid_result = '''
    probe = Command("probe", returns=object)
    @workflow
    def run() -> int:
        return probe("python", "probe.py")
    '''
    with pytest.raises(PythonFrontendError, match="python_annotation_unsupported"):
        _compile_with_commands(tmp_path / "bad-result", invalid_result, command)

    empty_inputs, _built, _manifest = _compile_with_commands(
        tmp_path / "empty-inputs", '''
        probe = Command("probe", returns=int)
        @workflow
        def run() -> int:
            probe("python", "probe.py", inputs={})
            return 0
        ''', command,
    )
    assert ':inputs () :returns Int' in empty_inputs.source_path.read_text(encoding="utf-8")


def test_nested_loop_control_ownership(tmp_path):
    _, _, built = compile_source(tmp_path, '''
    @record
    class State:
        count: int

    @workflow
    def run(limit: int) -> int:
        return loop(
            state=State(count=0), max=limit,
            body=lambda outer: when(
                outer.count >= 5,
                then=lambda: done(outer.count),
                else_=lambda: cont(State(count=loop(
                    state=State(count=0), max=3,
                    body=lambda inner: when(
                        inner.count >= 1,
                        then=lambda: done(inner.count),
                        else_=lambda: cont(State(count=inner.count + 1)),
                    ),
                    on_exhausted=lambda exhausted: exhausted.count,
                ) + 5)),
            ),
            on_exhausted=lambda exhausted: exhausted.count,
        )
    ''')
    assert evaluate_closed_program(built.program, {"limit": 2}).value == 6

    escaped_control = '''
    @record
    class State:
        count: int

    def run_inner(outer_stop):
        return loop(
            state=State(count=0), max=1,
            body=lambda inner: outer_stop,
            on_exhausted=lambda exhausted: exhausted.count,
        )

    @workflow
    def run() -> int:
        def outer_body(outer):
            outer_stop = done(outer.count)
            return run_inner(outer_stop)
        return loop(
            state=State(count=0), max=1,
            body=outer_body,
            on_exhausted=lambda exhausted: exhausted.count,
        )
    '''
    with pytest.raises(PythonFrontendError, match="python_loop_control_owner_mismatch"):
        compile_source(tmp_path / "escaped-control", escaped_control)


def test_loop_context_reaches_done_and_ignored_region_calls(tmp_path):
    _, _, built = compile_source(tmp_path, '''
    @variant
    class A:
        value: int
    @variant
    class B:
        value: int
    @variant
    class C:
        value: int
    First = A | B
    Second = A | C
    choice = A(value=1)

    @pure
    def inspect(value: First) -> int:
        return 0

    @workflow
    def run(limit: int) -> First:
        def body(state: int):
            inspect(choice)
            return done(A(value=2))

        def exhausted(state: int):
            inspect(choice)
            return B(value=3)

        return loop(state=0, max=limit, body=body, on_exhausted=exhausted)
    ''')
    assert evaluate_closed_program(built.program, {"limit": 1}).value == {
        "variant": "A", "value": 2,
    }
    assert evaluate_closed_program(built.program, {"limit": 0}).value == {
        "variant": "B", "value": 3,
    }


def test_generated_mirror_preserves_digest_and_sites(tmp_path):
    command = {"probe": {
        "stable_command": ["python", "probe.py"],
        "closure": ["probe.py"],
    }}
    source = '''
    probe = Command("probe", returns=int)
    @proc(effects=(uses_command(probe),))
    def fetch(value: int) -> int:
        return probe("python", "probe.py", value)
    @workflow
    def run(value: int) -> int:
        left = fetch(value)
        right = fetch(value + 1)
        return left + right
    '''
    generated, built, _manifest = _compile_with_commands(
        tmp_path / "generated", source, command
    )
    mirror_root = tmp_path / "mirror"
    mirror_root.mkdir()
    mirror_path = mirror_root / "py" / "sample.orc"
    mirror_path.parent.mkdir(parents=True)
    mirror = mirror_path
    mirror.write_text('''
    (workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule py/sample) (export fetch run)
      (defproc fetch ((value Int)) -> Int
        :effects ((uses-command probe))
        (let* ((_e0 (command-result probe :argv ("python" "probe.py" value) :returns Int))) _e0))
      (defworkflow run ((value Int)) -> Int
        (let* ((_e0 (fetch value))
               (_e1 (fetch (+ value 1))))
          (+ _e0 _e1))))
    ''', encoding="utf-8")
    manifest = mirror_root / "commands.json"
    manifest.write_text(json.dumps(command), encoding="utf-8")
    mirror_request = FrontendBuildRequest(
        source_path=mirror,
        source_roots=(mirror_root,),
        workspace_root=mirror_root,
        entry_workflow="run",
        command_boundaries_path=manifest,
    )
    mirrored = build_closed_program_bundle(mirror_request)
    assert generated.module_name == "py/sample"
    assert built.program.digest == mirrored.program.digest
    assert built.program.sites == mirrored.program.sites


@pytest.mark.parametrize("discarded", [
    'done(agent(p()))',
    'cont(state + 1)',
    'when(flag, then=lambda: done(agent(p())), else_=lambda: done(1))',
    'match(choice, A=lambda a: done(agent(p())), B=lambda b: done(1))',
])
def test_discarded_terminal_controls_refuse_instead_of_dropping_effects(tmp_path, discarded):
    source = f'''
    @variant
    class A: pass
    @variant
    class B: pass
    Outcome = A | B
    p = Prompt(text="Inspect", fills={{}}, returns=int)
    agent = Provider("trace")
    @workflow
    def run(flag: bool, choice: Outcome) -> int:
        def body(state):
            {discarded}
            return done(0)
        return loop(state=0, max=1, body=body, on_exhausted=lambda state: state)
    '''
    with pytest.raises(PythonFrontendError, match="python_loop_control_not_tail"):
        compile_source(tmp_path, source, providers={"providers.trace": "stub"})


@pytest.mark.parametrize("control", ["done(1)", "cont(1)"])
def test_discarded_loop_control_outside_loop_refuses(tmp_path, control):
    with pytest.raises(PythonFrontendError, match="python_loop_control_owner_mismatch"):
        compile_source(tmp_path, f'@workflow\ndef run() -> int:\n    {control}\n    return 1\n')


def test_terminal_control_variable_retained_through_when_and_match(tmp_path):
    _, _, built = compile_source(tmp_path, '''
    @variant
    class A: pass
    @variant
    class B: pass
    Outcome = A | B
    @workflow
    def run(flag: bool, choice: Outcome) -> int:
        def body(state):
            stop = done(state)
            return when(flag,
                then=lambda: match(choice, A=lambda a: stop, B=lambda b: stop),
                else_=lambda: cont(state + 1))
        return loop(state=0, max=1, body=body, on_exhausted=lambda state: state)
    ''')
    for variant in ("A", "B"):
        assert evaluate_closed_program(built.program,
            {"flag": True, "choice": {"variant": variant}}).value == 0
        assert evaluate_closed_program(built.program,
            {"flag": False, "choice": {"variant": variant}}).value == 1


def test_continue_uses_state_context_independently_of_loop_result(tmp_path):
    _, _, built = compile_source(tmp_path, '''
    @variant
    class A:
        value: int
    @variant
    class B:
        value: int
    @variant
    class C:
        value: int
    First = A | B
    Second = A | C
    @workflow
    def run(initial: First, stop: bool) -> int:
        return loop(state=initial, max=1,
            body=lambda state: when(stop, then=lambda: done(0),
                                    else_=lambda: cont(A(value=2))),
            on_exhausted=lambda state: match(state,
                A=lambda a: a.value, B=lambda b: b.value))
    ''')
    assert evaluate_closed_program(built.program,
        {"initial": {"variant": "B", "value": 1}, "stop": False}).value == 2


@pytest.mark.parametrize("decorator", ["pure", "proc(effects=())"])
def test_helper_defaults_are_filled_at_python_call_binding(tmp_path, decorator):
    _, _, built = compile_source(tmp_path, f'''
    @{decorator}
    def helper(value: int = 4) -> int:
        return value + 1
    @workflow
    def run(value: int = 2) -> int:
        return helper() + helper(value)
    ''')
    assert evaluate_closed_program(built.program, {"value": 2}).value == 8


def test_effect_descriptor_makes_private_workflow_subject_reachable(tmp_path):
    module, _, built = compile_source(tmp_path, '''
    __all__ = ["run"]
    calls = []
    @workflow
    def _child() -> int:
        calls.append("child")
        return 1
    @proc(effects=(calls_workflow(_child),))
    def helper() -> int:
        return 2
    @workflow
    def run() -> int:
        return helper()
    ''')
    assert module.calls == ["child"]
    assert evaluate_closed_program(built.program, {}).value == 2


@pytest.mark.parametrize("expression", ["done(1) + 1", "done(done(1))", "cont(done(1))"])
def test_loop_controls_embedded_in_values_are_not_tail(tmp_path, expression):
    with pytest.raises(PythonFrontendError, match="python_loop_control_not_tail"):
        compile_source(tmp_path, f'''
        @workflow
        def run() -> int:
            return loop(state=0, max=1, body=lambda state: {expression},
                on_exhausted=lambda state: state)
        ''')


def test_command_wrong_json_output_fails_without_committing_result(tmp_path):
    (tmp_path / "probe.py").write_text(textwrap.dedent('''
    import json
    import os
    from pathlib import Path
    Path("dispatch-marker").write_text("ran")
    Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
        json.dumps({"count": "not-an-integer"}))
    '''), encoding="utf-8")
    command = {"probe": {"stable_command": ["python", "probe.py"], "closure": ["probe.py"]}}
    generated, _, manifest = _compile_with_commands(tmp_path, '''
    @record
    class Receipt:
        count: int
    probe = Command("probe", returns=Receipt)
    @workflow
    def run() -> Receipt:
        return probe("python", "probe.py")
    ''', command)
    result = _run_orc(tmp_path, generated.source_path, manifest)
    assert result.returncode == 1, result.stderr
    assert (tmp_path / "dispatch-marker").read_text() == "ran"
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    assert not snapshot.active_commits
    assert [entry.data["record"] for entry in snapshot.entries] == ["started", "failed", "terminal"]
    failure = next(entry.data for entry in snapshot.entries if entry.data["record"] == "failed")
    assert failure["violations"]
    assert snapshot.terminal.data["outcome"] == "failed"
