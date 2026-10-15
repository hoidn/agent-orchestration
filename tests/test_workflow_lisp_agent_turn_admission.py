"""Compile-only proofs: carriage, escape and provider-origin analysis for agent turns at 2.38."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from orchestrator.contracts.closed_program.check import CheckedFormError, validate
from orchestrator.contracts.closed_program.sites import _ast_nodes, _effect_value_children, assign_sites
from orchestrator.workflow.pure_expr import PureExprEvaluationError, coerce_pure_value
from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle_in_memory
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import UsesProviderEffect

HEADER = ('(workflow-lisp (:language "0.1") (:target-dsl "2.38") (defmodule main) (export run)\n'
          '(defrecord Note (text String)) (defrecord Team (lead Agent) (label String))\n'
          '(defprompt ask (:fills (task :text)) -> Note "Task: {task}")\n')
TWO_AGENTS = HEADER + '''(defproc turn ((who Agent) (task String)) -> Note
    :effects ((uses-provider providers.claude) (uses-provider providers.codex))
    (provider-result who :prompt (ask :task task) :timeout-sec 60))
  (defworkflow run ((task String) (pick Bool)) -> Note
    (let* ((designer (agent providers.claude :model "m1" :effort "high"))
           (reviewer (agent providers.codex :model "m2" :effort "high"))
           (team (record Team :lead designer :label "d"))
           (chosen (if pick designer reviewer))
           (a1 (provider-result designer :prompt (ask :task task)))
           (b1 (provider-result reviewer :prompt (ask :task a1.text)))
           (a2 (turn team.lead a1.text))
           (c (provider-result chosen :prompt (ask :task b1.text))))
      c)))'''
ALIAS = HEADER + '''(defworkflow run ((task String)) -> Note
    (let* ((a (agent providers.claude)) (b a)) (provider-result b :prompt (ask :task task)))))'''
CLAUDE, CODEX = "claude_unrestricted_workspace", "codex"
CHILD = HEADER.replace("(defmodule main)", "(defmodule child)") + \
    '(defworkflow run ((who String) (t String)) -> Note (record Note :text t)))'


def _request(root: Path, source: str) -> FrontendBuildRequest:
    files = {
        "main.orc": source, "child.orc": CHILD, "t.py": "", "prompt.md": "P\n",
        "providers.json": json.dumps({"providers.claude": CLAUDE, "providers.codex": CODEX}),
        "prompts.json": json.dumps({"prompts.base": {"asset_file": "prompt.md"}}),
        "commands.json": json.dumps({"tool": {"stable_command": ["python", "t.py"], "closure": ["t.py"]}}),
    }
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    return FrontendBuildRequest(
        source_path=root / "main.orc", source_roots=(root,), workspace_root=root,
        provider_externs_path=root / "providers.json", prompt_externs_path=root / "prompts.json",
        command_boundaries_path=root / "commands.json",
    )


def _performs(tree):
    bodies = [tree["body"], *(d["body"] for d in tree["definitions"].values())]
    return [n for body in bodies for n in _ast_nodes(body) if n.get("k") == "perform"]


def _turns(tree):
    return [n for n in _performs(tree) if n["class"] == "agent_turn"]


def _first_code(root: Path, source: str) -> str:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_closed_program_bundle(_request(root, source))
    return excinfo.value.diagnostics[0].code


def test_two_agents_compile_to_allocations_and_origin_bound_turns(tmp_path: Path) -> None:
    bundle = build_closed_program_bundle(_request(tmp_path, TWO_AGENTS))
    performs = _performs(bundle.program.tree)
    allocations = [n for n in performs if n["class"] == "agent"]
    turns = [n for n in performs if n["class"] == "agent_turn"]
    assert [n["provider"] for n in allocations] == [CLAUDE, CODEX]
    assert all(n["result"] == {"kind": "primitive", "name": "Agent"} and n["repeat"] == "rerun" for n in allocations)
    assert sorted(tuple(n["origins"]) for n in turns) == [
        (CLAUDE,), (CLAUDE, CODEX), (CLAUDE, CODEX), (CODEX,),
    ]  # a1 and b1 exact; the helper turn and the branch-selected turn conservative
    for turn in turns:
        assert _effect_value_children(dict(turn))[0] is turn["agent"]
        assert "provider" not in turn and set(turn["policy"]) <= {"timeout_sec"}
    assert len(bundle.program.sites) == 6


def test_let_alias_keeps_exact_origin_end_to_end(tmp_path: Path) -> None:
    (turn,) = _turns(build_closed_program_bundle(_request(tmp_path, ALIAS)).program.tree)
    assert turn["origins"] == [CLAUDE]


def test_helper_turn_carries_uses_provider_for_every_possible_origin(tmp_path: Path) -> None:
    built = build_frontend_bundle_in_memory(_request(tmp_path, TWO_AGENTS))
    helper = built.compile_result.entry_result.typed_program.procedures["main::turn"]
    subjects = {e.subject for e in helper.direct_effect_summary.direct_effects if isinstance(e, UsesProviderEffect)}
    assert subjects == {("providers", "claude"), ("providers", "codex")}


@pytest.mark.parametrize("body, origins", [
    ('(provider-result (agent providers.codex :model "m") :prompt (ask :task task))', [CODEX]),
    ('(let* ((d (agent providers.claude)) (team (record Team :lead d :label "x")))'
     ' (provider-result team.lead :prompt (ask :task task)))', [CLAUDE, CODEX]),
    ('(let* ((w (if (= task "a") (agent providers.claude) (agent providers.codex))))'
     ' (provider-result w :prompt (ask :task task)))', [CLAUDE, CODEX]),
])
def test_agent_operand_shapes_compile_with_their_origins(tmp_path: Path, body: str, origins: list[str]) -> None:
    source = HEADER + f'(defworkflow run ((task String)) -> Note {body}))'
    (turn,) = _turns(build_closed_program_bundle(_request(tmp_path, source)).program.tree)
    assert turn["origins"] == origins


@pytest.mark.parametrize("mutate, rule", [
    (lambda turn: turn.update(origins=[]), "effect_shape"),
    (lambda turn: turn.update(origins=[CODEX]), "agent_origin_mismatch"),
])
def test_checker_refuses_empty_or_mismatched_origins(tmp_path: Path, mutate, rule: str) -> None:
    tree = deepcopy(build_closed_program_bundle(_request(tmp_path, ALIAS)).program.tree)
    mutate(_turns(tree)[0])
    with pytest.raises(CheckedFormError) as excinfo:
        validate(tree)
    assert excinfo.value.rule == rule


@pytest.mark.parametrize("owner", ["helper", "branch"])
@pytest.mark.parametrize("narrowed", [[CLAUDE], [CODEX]])
def test_checker_refuses_untraced_turn_narrowed_below_every_allocation(tmp_path: Path, owner: str, narrowed) -> None:
    tree = deepcopy(build_closed_program_bundle(_request(tmp_path, TWO_AGENTS)).program.tree)
    body = next(iter(tree["definitions"].values()))["body"] if owner == "helper" else tree["body"]
    (turn,) = [n for n in _ast_nodes(body) if n.get("class") == "agent_turn" and len(n["origins"]) == 2]
    turn["origins"] = narrowed
    with pytest.raises(CheckedFormError) as excinfo:
        validate(tree)
    assert excinfo.value.rule == "agent_origin_mismatch"


def test_checker_refuses_agent_effect_reached_from_a_parallel_worker(tmp_path: Path) -> None:
    control = HEADER + '(defworkflow child ((t String)) -> Note (provider-result providers.claude :prompt (ask :task t))) ' \
        + PAR.format(body='(call child :t item)')
    tree = deepcopy(build_closed_program_bundle(_request(tmp_path, control)).program.tree)
    allocation = build_closed_program_bundle(_request(tmp_path, ALIAS)).program.tree["body"]
    child = next(iter(tree["definitions"].values()))
    child["body"] = {"k": "let", "name": "w", "value": next(n for n in _ast_nodes(allocation) if n.get("class") == "agent"),
                     "body": child["body"]}
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    with pytest.raises(CheckedFormError) as excinfo:
        validate(tree)
    assert excinfo.value.rule == "parallel_agent_boundary"


def test_turn_result_admits_its_provider_bundle_path(tmp_path: Path) -> None:
    source = HEADER.replace("(defrecord Note", '(defpath ResultBundle :kind relpath :under ".orchestrate/runs" '
                            ':must-exist false) (defrecord Note') + D + \
        '(let* ((r (provider-result d :prompt (ask :task task))) (p (provider-bundle-path r :as ResultBundle))) r))))'
    assert len(_turns(build_closed_program_bundle(_request(tmp_path, source)).program.tree)) == 1


TURN = '(defworkflow run ((task String)) -> Note (let* ((designer (agent providers.claude))) {tail})))'


@pytest.mark.parametrize("tail, code", [
    ('(provider-result designer :prompt (ask :task task) :model "x")', "agent_turn_policy_override_forbidden"),
    ('(provider-result designer :prompt (ask :task task) :effort "x")', "agent_turn_policy_override_forbidden"),
    ('(provider-result designer :prompt (ask :task task) :capture-context :portable)', "agent_turn_option_unsupported"),
    ('(provider-result designer :prompt (ask :task task) :session-artifact session)', "agent_turn_option_unsupported"),
    ('(provider-result designer :prompt (ask :task task) :delivery :phased)', "agent_turn_option_unsupported"),
    ('(provider-result designer :prompt (ask :task task) :delivery :phased :materialization-attempts 2)',
     "agent_turn_option_unsupported"),
])
def test_agent_turn_rejects_overrides_and_unbounded_options(tmp_path: Path, tail: str, code: str) -> None:
    assert _first_code(tmp_path, HEADER + TURN.format(tail=tail)) == code


D = '(defworkflow run ((task String)) -> Note (let* ((d (agent providers.claude))) '
PICK = '(defunion Pick (a (lead Agent)) (b (label String))) '
PAR = '(defworkflow run ((items List[String])) -> List[Note] (list/map-effect ((item items)) :max 2 :parallel 2 :workspace "." {body})))'
MK = ('(defproc mk ((t String)) -> Note :effects ((uses-provider providers.claude)) '
      '(let* ((w (agent providers.claude))) (provider-result w :prompt (ask :task t)))) ')
APPLY = '(defproc apply-it ((f ProcRef[String -> Note]) (t String)) -> Note :effects () (f t)) '
RR = ('(run-ref :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567") '
      ':program (:path "child.orc" :entry run) ')
POLICY = ':policy (:environment :deterministic-effect-free :setup ())'


@pytest.mark.parametrize("source, code", [
    # provider data: :inputs, prompt :value fill of a record carrying an Agent
    (HEADER + D + '(provider-result providers.codex :prompt prompts.base :inputs (d) :returns Note))))',
     "agent_transport_forbidden"),
    (HEADER + '(defprompt who (:fills (lead :value Team)) -> Note "x {lead}") ' + D
     + '(let* ((tm (record Team :lead d :label "l"))) (provider-result providers.codex :prompt (who :lead tm))))))',
     "agent_transport_forbidden"),
    # command data: argv and typed inputs
    (HEADER + D + '(let* ((x (command-result tool :argv ("python" "t.py" d) :returns String))) (record Note :text x)))))',
     "agent_transport_forbidden"),
    (HEADER + D + '(let* ((x (command-result tool :argv ("python" "t.py") :inputs ((who d)) :returns String)))'
     ' (record Note :text x)))))', "agent_transport_forbidden"),
    # workflow signature: parameter, return, nested record return, child workflow parameter
    (HEADER + '(defworkflow run ((who Agent)) -> Note (provider-result who :prompt (ask :task "t"))))',
     "workflow_boundary_type_invalid"),
    (HEADER + '(defworkflow run ((task String)) -> Agent (agent providers.claude)))', "workflow_return_type_invalid"),
    (HEADER + '(defworkflow run ((task String)) -> Team (let* ((a (agent providers.claude))) (record Team :lead a :label "l"))))',
     "workflow_return_type_invalid"),
    (HEADER + '(defworkflow run ((t Team)) -> Note (provider-result t.lead :prompt (ask :task "t"))))',
     "workflow_boundary_type_invalid"),
    (HEADER + '(defworkflow child ((t Team)) -> Note (record Note :text t.label)) ' + D
     + '(call child :t (record Team :lead d :label "l")))))', "workflow_boundary_type_invalid"),
    (HEADER + PICK + '(defworkflow run ((p Pick)) -> Note (record Note :text "x")))', "workflow_boundary_type_invalid"),
    # structured results carrying an Agent
    (HEADER + '(defprompt mk (:fills (task :text)) -> Team "T {task}") ' + D
     + '(let* ((x (provider-result providers.codex :prompt (mk :task task)))) (record Note :text x.label)))))',
     "provider_result_return_type_invalid"),
    (HEADER + D + '(let* ((x (command-result tool :argv ("python" "t.py") :returns Team))) (record Note :text x.label)))))',
     "command_result_return_type_invalid"),
    (HEADER + '(defworkflow child ((who Agent)) -> Note (provider-result who :prompt (ask :task "t"))) ' + D
     + '(call child :who d))))', "workflow_boundary_type_invalid"),
    # run-ref input and result refinement
    (HEADER + D + '(let* ((r ' + RR + ':inputs (:who d :t task) :returns Note ' + POLICY + '))) (record Note :text "x")))))',
     "workflow_boundary_type_invalid"),
    (HEADER + D + '(let* ((r ' + RR + ':inputs (:who task :t task) :returns Team ' + POLICY + '))) (record Note :text "x")))))',
     "workflow_boundary_type_invalid"),
    # loop state
    (HEADER + D + '(loop/recur :max 2 :state (loop-state (who Agent d)) (fn (state) (done (record Note :text "x")))))))',
     "loop_state_runtime_transport_forbidden"),
    # parallel worker: free Agent used in the body, Agent allocated in the body, Agent in the result
    (HEADER + '(defworkflow run ((items List[String])) -> List[Note] (let* ((d (agent providers.claude))) '
     '(list/map-effect ((item items)) :max 2 :parallel 2 :workspace "." (provider-result d :prompt (ask :task item))))))',
     "parallel_agent_boundary"),
    (HEADER + '(defproc mk ((t String)) -> Note :effects ((uses-provider providers.claude)) :lowering inline '
     '(let* ((w (agent providers.claude))) (provider-result w :prompt (ask :task t)))) '
     '(defworkflow run ((items List[String])) -> List[Note] (list/map-effect ((item items)) :max 2 :parallel 2 :workspace "." (mk item))))',
     "parallel_agent_boundary"),
    (HEADER + '(defproc mk ((t String)) -> Team :effects ((uses-provider providers.claude)) :lowering inline '
     '(let* ((w (agent providers.claude))) (record Team :lead w :label t))) '
     '(defworkflow run ((items List[String])) -> Note (let* ((teams (list/map-effect ((item items)) :max 2 :parallel 2'
     ' :workspace "." (mk item)))) (record Note :text "x"))))',
     "parallel_agent_boundary"),
    # parallel worker reaching an allocation through a child workflow, a macro, or a ProcRef callee
    (HEADER + '(defworkflow child ((t String)) -> Note (let* ((w (agent providers.claude))) (provider-result w :prompt (ask :task t)))) '
     + PAR.format(body='(call child :t item)'), "parallel_agent_boundary"),
    (HEADER + '(defmacro alloc () (agent providers.claude)) (defproc mk ((t String)) -> Note :effects ((uses-provider providers.claude)) '
     '(let* ((w (alloc))) (provider-result w :prompt (ask :task t)))) ' + PAR.format(body='(mk item)'), "parallel_agent_boundary"),
    (HEADER + MK + APPLY + PAR.format(body='(apply-it (proc-ref mk) item)'), "parallel_agent_boundary"),
    # closure capture: let-proc and bind-proc
    (HEADER + '(defproc use ((who Agent) (t String)) -> Note :effects ((uses-provider providers.claude) (uses-provider providers.codex)) '
     '(provider-result who :prompt (ask :task t))) ' + APPLY + D + '(apply-it (bind-proc (proc-ref use) :who d) task))))',
     "let_proc_capture_agent_forbidden"),
    (HEADER + D + '(let-proc (f ((t String)) -> Note :captures (d) (provider-result d :prompt (ask :task t)))'
     ' (let* ((h (proc-ref f))) (h task))))))', "let_proc_capture_agent_forbidden"),
    # pure handling: equality, print
    (HEADER + D + '(if (= d d) (record Note :text "a") (record Note :text "b")))))', "pure_expr_operand_type_mismatch"),
    (HEADER + D + '(let* ((p (print d))) (record Note :text "a")))))', "pure_expr_operand_type_mismatch"),
])
def test_agent_cannot_escape_its_run_local_positions(tmp_path: Path, source: str, code: str) -> None:
    assert _first_code(tmp_path, source) == code


def test_runtime_agent_value_shape_is_exact() -> None:
    desc = {"kind": "primitive", "name": "Agent"}
    good = {"run_id": "r", "identity": "workflow:main::run / designer", "provider": "codex", "policy": {"model": "m"},
            "config_digest": "sha256:" + "0" * 64}
    assert coerce_pure_value(good, desc) == good
    for bad in ({"run_id": "r"}, "agent:x", {**good, "extra": 1}, {**good, "policy": {"model": 1}},
                {**good, "config_digest": "x"}, {**good, "provider": ""}):
        with pytest.raises(PureExprEvaluationError):
            coerce_pure_value(bad, desc)
