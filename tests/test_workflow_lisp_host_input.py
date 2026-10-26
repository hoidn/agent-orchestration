"""Typed durable host requests use the ordinary checked compiler boundary."""
from pathlib import Path

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.contracts.closed_program.node_walk import _ast_nodes
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.build import build_closed_program
from tests.workflow_lisp_closed_program_helpers import install


def _compile(root: Path, *, answer="Approval", question='question', options=':timeout-sec 60', declarations='', target='2.40', effects='', extra_params='', extra_args='', include_returns=True):
    returns = f':returns {answer} ' if include_returns else ''
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
      (defmodule host/entry) (import std/host :only (HostReply)) (export run)
      (defenum Approval APPROVED DENIED)
      {declarations}
      (defproc ask ((question String){extra_params}) -> HostReply[{answer}] {effects}
        (request-input {question} {returns}{options}))
      (defworkflow run ({extra_params}) -> HostReply[{answer}] (ask "Approve?"{extra_args})))'''
    return _build_source(root, source)


def _build_source(root, source):
    path = install(root, source)
    typed = compile_typed_program(path, entry_workflow='run', command_boundaries={}, source_roots=(root,), workspace_root=root)
    return build_closed_program(typed), path


def _requests(program):
    return [node for body in (program.tree['body'], *(d['body'] for d in program.tree['definitions'].values()))
        for node in _ast_nodes(body) if node.get('class') == 'request_input']


def test_typed_request_compiles_and_roundtrips_without_source(tmp_path):
    program, path = _compile(tmp_path)
    node, = _requests(program)
    assert node['answer']['kind'] == 'enum'
    assert node['answer']['allowed'] == ['APPROVED', 'DENIED']
    assert node['result']['kind'] == 'union'
    assert node['result']['name'].startswith('std/host::HostReply[')
    assert node['site']
    path.unlink()
    restored = ClosedProgram.from_artifact(program.artifact())
    assert restored.digest == program.digest
    assert _requests(restored) == [node]

import json
from copy import deepcopy
import pytest
from orchestrator.contracts.closed_program.program import ClosedProgramInvalid
from orchestrator.contracts.closed_program.check import CheckedFormError, validate
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import HostInputEffect


@pytest.mark.parametrize('answer', ['String', 'Approval', 'Choice'])
def test_supported_full_answer_descriptors(tmp_path, answer):
    program, _ = _compile(tmp_path, answer=answer, declarations='''
      (defpath Report :kind relpath :under "reports" :must-exist true)
      (defrecord Details (report Report) (approvals List[Approval]))
      (defunion Choice (ACCEPT (details Details)) (DECLINE (reason String)))''')
    node, = _requests(program)
    if answer == 'Choice':
        path = node['answer']['variants'][0]['fields'][0]['type']['fields'][0]['type']
        assert path['under'] == 'reports'
        assert path['must_exist_target'] is True
    assert ClosedProgram.from_artifact(program.artifact()).digest == program.digest


@pytest.mark.parametrize(('answer', 'kind', 'declarations'), [
    ('String', 'primitive', ''),
    ('Approval', 'enum', ''),
    ('Choice', 'union', '(defunion Choice (ACCEPT (reason String)) (DECLINE (reason String)))'),
])
def test_declared_prompt_contract_infers_host_answer(tmp_path, answer, kind, declarations):
    program, _ = _compile(tmp_path, answer=answer,
        question='(answer-prompt :summary question)', include_returns=False,
        declarations=f'''{declarations}
          (defprompt answer-prompt (:fills (summary :text)) -> {answer} "{{summary}}")''')
    node, = _requests(program)
    assert node['answer']['kind'] == kind
    assert ClosedProgram.from_artifact(program.artifact()).digest == program.digest


@pytest.mark.parametrize('include_returns', [True, False])
def test_prompt_fills_and_shown_paths_survive_specialization(tmp_path, include_returns):
    program, path = _compile(tmp_path, question='(approval :summary question :report report :choice choice)',
        declarations='''(defpath Report :kind relpath :under "reports" :must-exist true)
          (defprompt approval (:fills (summary :text) (report :doc Report) (choice :value Approval)) -> Approval
            "{summary} {choice}")''', options=':timeout-sec (+ 30 30) :show (report report)', extra_params=' (report Report) (choice Approval)', extra_args=' report choice', include_returns=include_returns)
    node, = _requests(program)
    assert 'question' not in node
    assert node['answer']['name'] == 'host/entry::Approval'
    assert [fill['kind'] for fill in node['prompt']['fills']] == ['text', 'doc', 'value']
    assert len(node['show']) == 2
    assert all(fill['type']['kind'] in {'primitive', 'path', 'enum'} for fill in node['prompt']['fills'])
    assert ClosedProgram.from_artifact(program.artifact()).digest == program.digest


@pytest.mark.parametrize(('answer', 'question', 'options', 'declarations'), [
    ('Int', 'question', '', ''),
    ('Any', 'question', '', ''),
    ('Bad', 'question', '', '(defunion Bad (VALUE (value Any)))'),
    ('Approval', 'false', '', ''),
    ('Approval', 'question', ':timeout-sec false', ''),
    ('Approval', 'question', ':timeout-sec 0', ''),
    ('Approval', 'question', ':timeout-sec -1', ''),
    ('Approval', 'question', ':timeout-sec "60"', ''),
    ('Approval', 'question', ':show ("reports/a.txt")', ''),
    ('Approval', 'question', ':show false', ''),
    ('Approval', 'question', ':unknown true', ''),
    ('Approval', 'question', ':returns Approval', ''),
    ('Approval', '(other :summary question)', '', '(defprompt other (:fills (summary :text)) -> String "{summary}")'),
    ('Approval', '(other)', '', '(defprompt other (:fills (summary :text)) -> Approval "{summary}")'),
])
def test_invalid_request_contracts_refuse(tmp_path, answer, question, options, declarations):
    with pytest.raises(LispFrontendCompileError):
        _compile(tmp_path, answer=answer, question=question, options=options, declarations=declarations)


@pytest.mark.parametrize('effects', [':effects ()', ':effects ((uses-command missing))'])
def test_explicit_ceiling_refuses_host_input(tmp_path, effects):
    with pytest.raises(LispFrontendCompileError):
        _compile(tmp_path, effects=effects)


@pytest.mark.parametrize('mutation', ['answer', 'result', 'question', 'timeout', 'show', 'provider', 'target'])
def test_source_free_checker_refuses_tampered_requests(tmp_path, mutation):
    program, _ = _compile(tmp_path)
    tree = deepcopy(program.tree)
    node, = _requests(type('Program', (), {'tree': tree})())
    if mutation == 'answer':
        node['answer'] = {'kind': 'primitive', 'name': 'Int'}
    elif mutation == 'result':
        node['result']['name'] = 'forged::HostReply[host/entry::Approval]'
    elif mutation == 'question':
        node['question'] = {'k': 'lit', 'v': False, 'type': {'kind': 'primitive', 'name': 'Bool'}}
    elif mutation == 'timeout':
        node['timeout_sec'] = {'k': 'lit', 'v': 0, 'type': {'kind': 'primitive', 'name': 'Int'}}
    elif mutation == 'show':
        node['show'] = [node['question']]
    elif mutation == 'provider':
        node['provider'] = 'accidental-provider-dispatch'
    else:
        tree['target'] = '2.39'
    with pytest.raises(ClosedProgramInvalid):
        ClosedProgram.from_artifact(json.dumps(tree))


def test_target_239_typed_request_has_located_gap(tmp_path):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, target='2.39')
    assert caught.value.diagnostics[0].code == 'closed_program_gap'


def test_target_240_inherits_phased_delivery(tmp_path):
    from tests.test_workflow_lisp_phased_239 import _compile as compile_phased, _source, _provider_effect
    program = compile_phased(tmp_path / 'phased239.orc', _source('2.40'))
    assert _provider_effect(program)['class'] == 'provider_phased'
    assert ClosedProgram.from_artifact(program.artifact()).digest == program.digest


def _graph_source(*, call='(leaf question)', result='HostReply[Approval]', pure=False, parallel=False):
    body = f'(list/map-effect ((worker (list "a"))) :max 1 :parallel 1 :workspace worker {call.replace("question", "worker")})' if parallel else call
    return f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply)) (export run)
      (defenum Approval APPROVED DENIED)
      (defproc leaf ((question String)) -> HostReply[Approval]
        (request-input question :returns Approval))
      (defproc apply ((hook ProcRef[String -> HostReply[Approval]]) (question String)) -> HostReply[Approval]
        (hook question))
      ({'defun' if pure else 'defproc'} helper ((question String)) -> {result} {body})
      (defworkflow run () -> {result} (helper "Approve?")))'''


@pytest.mark.parametrize('call', ['(leaf question)', '(apply (proc-ref leaf) question)'])
def test_transitive_and_specialized_host_effect_inference(tmp_path, call):
    path = install(tmp_path, _graph_source(call=call))
    typed = compile_typed_program(path, entry_workflow='run', command_boundaries={}, source_roots=(tmp_path,), workspace_root=tmp_path)
    helper = typed.procedures['host/entry::helper']
    assert HostInputEffect() in helper.transitive_effect_summary.transitive_effects
    assert _requests(build_closed_program(typed))


@pytest.mark.parametrize('call', ['(leaf question)', '(apply (proc-ref leaf) question)'])
def test_parallel_transitive_host_input_refuses(tmp_path, call):
    with pytest.raises(LispFrontendCompileError) as caught:
        _build_source(tmp_path, _graph_source(call=call, result='List[HostReply[Approval]]', parallel=True))
    assert caught.value.diagnostics[0].code == 'parallel_host_input_boundary'


def test_pure_function_transitive_host_input_refuses(tmp_path):
    with pytest.raises(LispFrontendCompileError):
        _build_source(tmp_path, _graph_source(pure=True))


@pytest.mark.parametrize('projection', ['answer.value', 'answer.by', 'cancel.by'])
def test_reply_match_refinement(tmp_path, projection):
    answered = projection if projection.startswith('answer.') else 'answer.value'
    cancelled = projection if projection.startswith('cancel.') else 'cancel.by'
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply)) (export run)
      (defworkflow run () -> String
        (let* ((reply (request-input "Explain" :returns String)))
          (match reply ((ANSWERED answer) {answered}) ((CANCELLED cancel) {cancelled}) ((EXPIRED expired) "expired")))))'''
    program, _ = _build_source(tmp_path, source)
    assert ClosedProgram.from_artifact(program.artifact()).digest == program.digest


@pytest.mark.parametrize('field', ['text', 'absent'])
def test_answered_does_not_expose_historical_or_unknown_fields(tmp_path, field):
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply)) (export run)
      (defworkflow run () -> String
        (let* ((reply (request-input "Explain" :returns String)))
          (match reply ((ANSWERED a) a.{field}) ((CANCELLED c) c.by) ((EXPIRED e) "expired")))))'''
    with pytest.raises(LispFrontendCompileError):
        _build_source(tmp_path, source)


def test_imported_helper_and_same_memo_workflow_keep_host_type(tmp_path):
    helper = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/helper) (import std/host :as host :only (HostReply)) (export Approval ask run)
      (defenum Approval APPROVED DENIED)
      (defproc ask ((question String)) -> host.HostReply[Approval]
        (request-input question :returns Approval))
      (defworkflow run ((question String)) -> host.HostReply[Approval] (ask question)))'''
    install(tmp_path, helper)
    main = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply))
      (import host/helper :as helper :only (Approval ask run)) (export run)
      (defworkflow run () -> HostReply[helper.Approval]
        (let* ((first (helper.ask "First"))) (call helper.run :question "Next"))))'''
    program, _ = _build_source(tmp_path, main)
    assert len(_requests(program)) == 1
    calls = [node for body in (program.tree["body"], *(d["body"] for d in program.tree["definitions"].values()))
        for node in _ast_nodes(body) if node.get("k") == "call"]
    assert len(calls) >= 3
    assert {node['result']['name'] for node in _requests(program)} == {'std/host::HostReply[host/helper::Approval]'}
    assert ClosedProgram.from_artifact(program.artifact()).digest == program.digest


@pytest.mark.parametrize("unrelated_union", [False, True])
def test_compiled_capsule_retains_canonical_host_reply_without_source(tmp_path, unrelated_union):
    producer_path = install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/producer) (import std/host :only (HostReply)) (export run)
      (defworkflow run () -> HostReply[String] (request-input "Explain" :returns String)))''')
    producer = compile_typed_program(producer_path, entry_workflow='run', command_boundaries={}, source_roots=(tmp_path,), workspace_root=tmp_path)
    producer_path.unlink()
    local = '(defunion LocalReply (ANSWERED (value String) (by String)) (CANCELLED (by String)) (EXPIRED))' if unrelated_union else ''
    path = install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply)) (export run)
      {local}
      (defworkflow run () -> HostReply[String] (call child)))''')
    typed = compile_typed_program(path, entry_workflow='run', command_boundaries={}, imported_programs={'child': producer},
        source_roots=(tmp_path,), workspace_root=tmp_path)
    program = build_closed_program(typed)
    node, = _requests(program)
    assert node['result']['name'] == 'std/host::HostReply[String]'
    path.unlink()
    assert ClosedProgram.from_artifact(program.artifact()).digest == program.digest


@pytest.mark.parametrize('erase_summary', [False, True])
def test_external_child_admission_refuses_checked_host_sites(tmp_path, erase_summary):
    from types import SimpleNamespace
    from orchestrator.workflow.run_ref.closed_path import _require_closed_effects
    from orchestrator.workflow.run_ref.path_contracts import RunRefPathCompileRefusal
    from orchestrator.workflow_lisp.effects import EMPTY_EFFECT_SUMMARY
    program, path = _compile(tmp_path, answer='String')
    typed = compile_typed_program(path, entry_workflow='run', command_boundaries={}, source_roots=(tmp_path,), workspace_root=tmp_path)
    built = SimpleNamespace(program=program, entry_effect_summary=EMPTY_EFFECT_SUMMARY if erase_summary else typed.entry.effect_summary)
    step = SimpleNamespace(run_ref=SimpleNamespace(program=SimpleNamespace(environment='candidate')))
    with pytest.raises(RunRefPathCompileRefusal) as caught:
        _require_closed_effects(built, step)
    assert 'closed_child_effects_not_empty' in caught.value.secondary_causes


def test_nested_reply_payload_match_and_field_constraints(tmp_path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply)) (export run)
      (defenum Approval APPROVED DENIED)
      (defunion Decision (APPROVE (approval Approval)) (DENY (reason String)))
      (defworkflow run () -> String
        (let* ((reply (request-input "Decide" :returns Decision)))
          (match reply
            ((ANSWERED answer) (match answer.value ((APPROVE decision) answer.by) ((DENY denial) denial.reason)))
            ((CANCELLED cancel) cancel.by) ((EXPIRED expired) "expired")))))'''
    program, _ = _build_source(tmp_path, source)
    assert _requests(program)[0]['answer']['variants'][0]['fields'][0]['type']['allowed'] == ['APPROVED', 'DENIED']
    assert ClosedProgram.from_artifact(program.artifact()).digest == program.digest


def test_independent_checker_refuses_parallel_request_without_frontend_gate(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp.closed import build as build_module
    monkeypatch.setattr(build_module, 'refuse_parallel_effects', lambda tree: None)
    captured = []
    monkeypatch.setattr(build_module, 'validate', lambda tree: captured.append(deepcopy(tree)))
    _build_source(tmp_path, _graph_source(result='List[HostReply[Approval]]', parallel=True))
    assert len(captured) == 1
    with pytest.raises(CheckedFormError) as caught:
        validate(captured[0])
    assert caught.value.rule == 'parallel_host_input_boundary'


@pytest.mark.parametrize('call', ['(leaf question)', '(apply (proc-ref leaf) question)'])
def test_transitive_host_effect_respects_empty_ceiling(tmp_path, call):
    source = _graph_source(call=call).replace('(defproc helper ((question String)) -> HostReply[Approval]',
        '(defproc helper ((question String)) -> HostReply[Approval] :effects ()')
    with pytest.raises(LispFrontendCompileError) as caught:
        _build_source(tmp_path, source)
    assert caught.value.diagnostics[0].code == 'procedure_effect_ceiling_exceeded'


def test_confined_child_refuses_typed_host_request_transitively(tmp_path):
    from tests.test_workflow_lisp_run_ref_workflow_program import _confined
    with pytest.raises(LispFrontendCompileError) as caught:
        _confined(tmp_path,
            ('(:target-dsl "2.38")', '(:target-dsl "2.40")'),
            ('(export run)', '(import std/host :only (HostReply)) (export run)'),
            (':workflow candidate-body', ':workflow bad'),
            extra='''(defworkflow asker ((seed Int) (task String)) -> Int
                (let* ((reply (request-input "Decide" :returns String))) seed))
              (defworkflow bad ((seed Int) (task String)) -> Int (call asker :seed seed :task task))''')
    assert caught.value.diagnostics[0].code == 'run_ref_environment_effect_unsupported'


def test_prompt_without_declared_return_uses_request_answer_contract(tmp_path):
    program, _ = _compile(tmp_path, question='(question-prompt :summary question)',
        declarations='(defprompt question-prompt (:fills (summary :text)) "{summary}")')
    assert _requests(program)[0]['answer']['kind'] == 'enum'


def test_prompt_explicit_value_return_does_not_match_enum_answer(tmp_path):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, question='(question-prompt :summary question)',
            declarations='(defprompt question-prompt (:fills (summary :text)) -> Value "{summary}")')
    assert caught.value.diagnostics[0].code == 'request_input_prompt_return_invalid'


def test_raw_host_question_still_requires_returns(tmp_path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply)) (export run)
      (defworkflow run () -> HostReply[String] (request-input "Explain")))'''
    with pytest.raises(LispFrontendCompileError) as caught:
        _build_source(tmp_path, source)
    assert caught.value.diagnostics[0].code == 'request_input_keyword_invalid'


def test_unresolved_prompt_still_requires_returns(tmp_path):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, question='(missing-prompt :summary question)', include_returns=False)
    assert caught.value.diagnostics[0].code == 'request_input_keyword_invalid'


def test_prompt_without_declared_return_still_requires_returns(tmp_path):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, question='(question-prompt :summary question)', include_returns=False,
            declarations='(defprompt question-prompt (:fills (summary :text)) "{summary}")')
    assert caught.value.diagnostics[0].code == 'request_input_keyword_invalid'


def test_declared_invalid_prompt_return_is_not_inferred_as_host_answer(tmp_path):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, question='(question-prompt :summary question)', include_returns=False,
            declarations='(defprompt question-prompt (:fills (summary :text)) -> Value "{summary}")')
    assert caught.value.diagnostics[0].code == 'request_input_answer_type_invalid'


def test_target_239_does_not_infer_prompt_host_answer(tmp_path):
    with pytest.raises(LispFrontendCompileError):
        _compile(tmp_path, target='2.39', question='(question-prompt :summary question)',
            include_returns=False,
            declarations='(defprompt question-prompt (:fills (summary :text)) -> Approval "{summary}")')


def test_imported_aliased_prompt_infers_its_canonical_answer_type(tmp_path):
    install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/prompts) (export approval Approval)
      (defenum Approval PROMPT_YES PROMPT_NO)
      (defprompt approval (:fills (summary :text)) -> Approval "{summary}"))''')
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply))
      (import host/prompts :as p :only (approval Approval)) (export run)
      (defenum Approval CALLER_ONLY)
      (defworkflow run () -> HostReply[p.Approval]
        (request-input (p.approval :summary "Decide"))))'''
    program, _ = _build_source(tmp_path, source)
    node, = _requests(program)
    assert node['answer']['name'] == 'host/prompts::Approval'
    assert node['result']['name'] == 'std/host::HostReply[host/prompts::Approval]'


@pytest.mark.parametrize('argument', ['Approval', 'List[Approval]', 'Optional[Approval]', 'Map[String, Approval]', 'Report'])
@pytest.mark.parametrize('owner', ['producer', 'third-module'])
def test_imported_prompt_generic_answer_keeps_argument_owners(tmp_path, argument, owner):
    if owner == 'third-module':
        install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
          (defmodule host/types) (export Approval Report)
          (defenum Approval PROMPT_YES PROMPT_NO)
          (defpath Report :kind relpath :under "reports" :must-exist true))''')
        producer_import = '(import host/types :as original :only (Approval Report))'
        producer_types = ''
        producer_argument = argument.replace('Approval', 'original.Approval').replace('Report', 'original.Report')
        caller_types = '(import host/types :as actual :only (Approval Report))'
        caller_argument = argument.replace('Approval', 'actual.Approval').replace('Report', 'actual.Report')
        owner_module = 'host/types'
        exported_types = ''
    else:
        producer_import = ''
        producer_types = '(defenum Approval PROMPT_YES PROMPT_NO) (defpath Report :kind relpath :under "reports" :must-exist true)'
        producer_argument = argument
        caller_types = ''
        caller_argument = argument.replace('Approval', 'p.Approval').replace('Report', 'p.Report')
        owner_module = 'host/prompts'
        exported_types = 'Approval Report'
    install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/prompts) {producer_import} (export approval Box {exported_types})
      {producer_types}
      (defunion Box :forall (T) (SOME (value T)) (NONE))
      (defprompt approval (:fills (summary :text)) -> Box[{producer_argument}] "{{summary}}"))''')
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply))
      (import host/prompts :as p :only (approval Box {exported_types})) {caller_types} (export run)
      (defenum Approval CALLER_ONLY)
      (defpath Report :kind relpath :under "caller" :must-exist false)
      (defworkflow run () -> HostReply[p.Box[{caller_argument}]]
        (request-input (p.approval :summary "Decide") {{returns}})))'''
    forms = []
    for returns in (f':returns p.Box[{caller_argument}]', ''):
        path = install(tmp_path, source.format(returns=returns))
        typed = compile_typed_program(path, entry_workflow='run', command_boundaries={}, source_roots=(tmp_path,), workspace_root=tmp_path)
        forms.append((typed, build_closed_program(typed)))
    (explicit_typed, explicit), (inferred_typed, inferred) = forms
    explicit_node, = _requests(explicit)
    inferred_node, = _requests(inferred)
    assert inferred_node['answer'] == explicit_node['answer']
    assert inferred_node['result'] == explicit_node['result']
    assert inferred_typed.entry.effect_summary == explicit_typed.entry.effect_summary
    canonical_argument = argument.replace('Approval', f'{owner_module}::Approval').replace('Report', f'{owner_module}::Report')
    assert inferred_typed.entry.typed_body.expr.answer_type_name == f'host/prompts::Box[{canonical_argument}]'
    assert inferred_node['answer']['name'] == f'host/prompts::Box[{canonical_argument.replace(", ", ",")}]'
    path.unlink()
    (tmp_path / 'host/prompts.orc').unlink()
    if owner == 'third-module':
        (tmp_path / 'host/types.orc').unlink()
    assert ClosedProgram.from_artifact(inferred.artifact()).digest == inferred.digest


@pytest.mark.parametrize('answer', ['Approval', 'Box[Approval]'])
def test_imported_prompt_private_answer_cannot_rebind_to_caller_type(tmp_path, answer):
    install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/prompts) (export approval Box)
      (defenum Approval YES NO)
      (defunion Box :forall (T) (SOME (value T)) (NONE))
      (defprompt approval (:fills (summary :text)) -> {answer} "{{summary}}"))''')
    caller_answer = answer.replace('Box', 'p.Box')
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply))
      (import host/prompts :as p :only (approval Box)) (export run)
      (defenum Approval YES NO)
      (defworkflow run () -> HostReply[{caller_answer}]
        (request-input (p.approval :summary "Decide"))))'''
    with pytest.raises(LispFrontendCompileError):
        _build_source(tmp_path, source)


def test_specialization_result_analysis_keeps_typed_reply(tmp_path):
    from orchestrator.workflow_lisp.procedure_specialization import _private_workflow_result_type_for_expr
    _, path = _compile(tmp_path)
    typed = compile_typed_program(path, entry_workflow='run', command_boundaries={}, source_roots=(tmp_path,), workspace_root=tmp_path)
    ask = typed.procedures['host/entry::ask']
    actual = _private_workflow_result_type_for_expr(ask.typed_body.expr,
        local_type_bindings=dict(ask.signature.params), typed_procedures_by_name=typed.procedures,
        type_env=typed.procedure_type_env(ask))
    assert actual == ask.signature.return_type_ref


def test_retained_generic_reply_hint_cannot_fall_back_to_another_nominal_type(tmp_path):
    from orchestrator.workflow_lisp.workflows import _flattened_boundary_contracts, _match_boundary_type_from_contracts
    _, path = _compile(tmp_path, declarations='''(defunion LocalReply
        (ANSWERED (value String) (by String)) (CANCELLED (by String)) (EXPIRED))''')
    typed = compile_typed_program(path, entry_workflow="run", command_boundaries={}, source_roots=(tmp_path,), workspace_root=tmp_path)
    ask = typed.procedures["host/entry::ask"]
    env = typed.procedure_type_env(ask)
    location = dict(span=ask.definition.span, form_path=ask.definition.form_path)
    other = env.resolve_type("LocalReply", **location)
    contracts = _flattened_boundary_contracts(other, generated_name="return", type_env=env, **location)
    with pytest.raises(LispFrontendCompileError) as caught:
        _match_boundary_type_from_contracts(contracts, type_env=env, generated_name="return", allow_union=True,
            type_hint=ask.signature.return_type_ref, **location)
    assert caught.value.diagnostics[0].code == "workflow_call_signature_erased"


def test_erased_reply_contract_still_refuses_ambiguous_authored_types(tmp_path):
    from orchestrator.workflow_lisp.workflows import _flattened_boundary_contracts, _match_boundary_type_from_contracts
    shape = '(ANSWERED (value String) (by String)) (CANCELLED (by String)) (EXPIRED)'
    _, path = _compile(tmp_path, declarations=f'(defunion FirstReply {shape}) (defunion SecondReply {shape})')
    typed = compile_typed_program(path, entry_workflow='run', command_boundaries={}, source_roots=(tmp_path,), workspace_root=tmp_path)
    ask = typed.procedures['host/entry::ask']
    env = typed.procedure_type_env(ask)
    location = dict(span=ask.definition.span, form_path=ask.definition.form_path)
    contracts = _flattened_boundary_contracts(env.resolve_type('FirstReply', **location),
        generated_name='return', type_env=env, **location)
    with pytest.raises(LispFrontendCompileError) as caught:
        _match_boundary_type_from_contracts(contracts, type_env=env, generated_name='return', allow_union=True, **location)
    assert caught.value.diagnostics[0].code == 'workflow_call_signature_erased'


@pytest.mark.parametrize("collision", ["", "(defunion Box (OTHER (count Int)))",
    "(defunion Box :forall (T) (OTHER (count T)))"])
def test_capsule_generic_nominal_type_absent_in_caller_keeps_erased_matching(tmp_path, collision):
    producer_path = install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule producer) (export run)
      (defunion Box :forall (T) (SOME (value T)) (NONE))
      (defworkflow run () -> Box[String] (variant Box[String] SOME :value "ok")))''')
    producer = compile_typed_program(producer_path, entry_workflow='run', command_boundaries={}, source_roots=(tmp_path,), workspace_root=tmp_path)
    producer_path.unlink()
    path = install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule consumer) (export run)
      {collision}
      (defunion Local (SOME (value String)) (NONE))
      (defworkflow run () -> Local (call child)))''')
    typed = compile_typed_program(path, entry_workflow='run', command_boundaries={}, imported_programs={'child': producer},
        source_roots=(tmp_path,), workspace_root=tmp_path)
    program = build_closed_program(typed)
    assert program.tree['result']['name'] == 'consumer::Local'
    path.unlink()
    assert ClosedProgram.from_artifact(program.artifact()).digest == program.digest


def test_capsule_generic_argument_absent_in_caller_keeps_erased_matching(tmp_path):
    producer_path = install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/producer) (import std/host :only (HostReply)) (export run)
      (defenum Private YES NO)
      (defworkflow run () -> HostReply[Private] (request-input "Decide" :returns Private)))''')
    producer = compile_typed_program(producer_path, entry_workflow='run', command_boundaries={}, source_roots=(tmp_path,), workspace_root=tmp_path)
    producer_path.unlink()
    path = install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply)) (export run)
      (defenum Public YES NO)
      (defunion LocalReply (ANSWERED (value Public) (by String)) (CANCELLED (by String)) (EXPIRED))
      (defworkflow run () -> LocalReply (variant LocalReply EXPIRED)))''')
    typed = compile_typed_program(path, entry_workflow='run', command_boundaries={},
        source_roots=(tmp_path,), workspace_root=tmp_path)
    from orchestrator.workflow_lisp.workflows import _signature_from_imported_typed_program
    signature = _signature_from_imported_typed_program('child', producer, type_env=typed.type_env)
    assert signature.return_type_ref == typed.entry.signature.return_type_ref
    program = build_closed_program(producer)
    assert _requests(program)[0]['result']['name'] == 'std/host::HostReply[host/producer::Private]'
    assert ClosedProgram.from_artifact(program.artifact()).digest == program.digest


@pytest.mark.parametrize('answer', ['Approval', 'Decision'])
@pytest.mark.parametrize('route', ['direct', 'helper', 'workflow-ref'])
@pytest.mark.parametrize('include_returns', [True, False])
def test_typed_capsule_keeps_shared_nominal_answer_after_producer_source_removal(tmp_path, answer, route, include_returns):
    install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/types) (export Approval Decision Report)
      (defpath Report :kind relpath :under "reports" :must-exist true)
      (defenum Approval APPROVED DENIED)
      (defunion Decision (ACCEPT (approval Approval)) (DECLINE (reason String))))''')
    returns_clause = f':returns p.{answer}' if include_returns else ''
    producer_path = install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/producer) (import std/host :only (HostReply))
      (import host/types :as p :only (Approval Decision Report)) (export run)
      (defprompt decision (:fills (summary :text) (evidence :doc p.Report)) -> p.{answer} "{{summary}}")
      (defworkflow run ((n Int) (report p.Report)) -> HostReply[p.{answer}]
        (request-input (decision :summary "Decide" :evidence report) {returns_clause} :show (report))))''')
    producer = compile_typed_program(producer_path, entry_workflow='run', command_boundaries={}, source_roots=(tmp_path,), workspace_root=tmp_path)
    producer_path.unlink()
    install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/utility) (export one) (defun one () -> Int 1))''')
    helper_import = ''
    call = '(call child :n 1)'
    if route != 'direct':
        helper_import = '(import host/caller :only (ask))'
        call = '(ask report)'
        helper_body = '(call child :n 1 :report report)' if route == 'helper' else '(invoke (workflow-ref child) report)'
        install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
          (defmodule host/caller) (import std/host :only (HostReply))
          (import host/types :as t :only (Approval Decision Report)) (export ask)
          (defproc invoke ((hook WorkflowRef[(Int t.Report) -> HostReply[t.{answer}]]) (report t.Report)) -> HostReply[t.{answer}]
            (call hook :n 1 :report report))
          (defproc ask ((report t.Report)) -> HostReply[t.{answer}] {helper_body}))''')
    path = install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (import std/host :only (HostReply))
      (import host/types :as c :only (Approval Decision Report))
      (import host/utility :only (one)) {helper_import} (export run)
      (defworkflow run ((report c.Report)) -> HostReply[c.{answer}] (let* ((n (one)))
        {'(call child :n 1 :report report)' if route == 'direct' else call})))''')
    typed = compile_typed_program(path, entry_workflow='run', command_boundaries={}, imported_programs={'child': producer},
        source_roots=(tmp_path,), workspace_root=tmp_path)
    path.unlink()
    (tmp_path / 'host/types.orc').unlink()
    (tmp_path / 'host/utility.orc').unlink()
    if route != 'direct':
        (tmp_path / 'host/caller.orc').unlink()
    program = build_closed_program(typed)
    node, = _requests(program)
    assert node['answer']['name'] == f'host/types::{answer}'
    assert node['result'] == program.tree['result']
    assert node['result']['name'] == f'std/host::HostReply[host/types::{answer}]'
    assert [fill['kind'] for fill in node['prompt']['fills']] == ['text', 'doc']
    assert len(node['show']) == 1
    assert ClosedProgram.from_artifact(program.artifact()).digest == program.digest

    if answer == 'Decision':
        for wire_name in ('return__value', 'return__variant'):
            tree = deepcopy(program.tree)
            call_node = next(node for body in (tree['body'], *(d['body'] for d in tree['definitions'].values()))
                for node in _ast_nodes(body) if node.get('callee') == 'workflow:host/producer::run')
            wire = next(row for row in call_node['boundary']['outputs']['caller'] if row['name'] == wire_name)
            if wire_name == 'return__value':
                wire['contract']['discriminant']['allowed'].append('FORGED')
            else:
                wire['contract']['allowed'].append('FORGED')
            with pytest.raises(ClosedProgramInvalid):
                ClosedProgram.from_artifact(json.dumps(tree))


def _retained_host_capsule(root):
    path = install(root, '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/producer) (import std/host :only (HostReply)) (export run)
      (defenum Approval APPROVED DENIED)
      (defworkflow run () -> HostReply[Approval] (request-input "Decide" :returns Approval)))''')
    typed = compile_typed_program(path, entry_workflow='run', command_boundaries={}, source_roots=(root,), workspace_root=root)
    path.unlink()
    return typed


@pytest.mark.parametrize('shadow', ['parameter', 'let', 'local-workflow', 'source-import'])
def test_capsule_reference_discovery_preserves_lexical_and_source_precedence(tmp_path, shadow):
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    producer = _retained_host_capsule(tmp_path)
    definitions = '(defrecord Number (n Int)) (defworkflow local ((n Int)) -> Number (record Number :n n))'
    imports = ''
    if shadow == 'parameter':
        definitions += '(defproc forward ((child WorkflowRef[Int -> Number])) -> Number (call child :n 7))'
        body = '(forward (workflow-ref local))'
    elif shadow == 'let':
        body = '(let* ((child (workflow-ref local))) (call child :n 7))'
    elif shadow == 'local-workflow':
        definitions += '(defworkflow child ((n Int)) -> Number (record Number :n n))'
        body = '(call child :n 7)'
    else:
        install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
          (defmodule host/source) (export child Number) (defrecord Number (n Int)) (defworkflow child ((n Int)) -> Number (record Number :n n)))''')
        imports = '(import host/source :only (child Number))'
        definitions = ''
        body = '(call child :n 7)'
    path = install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) {imports} (export run) {definitions}
      (defworkflow run () -> Number {body}))''')
    typed = compile_typed_program(path, entry_workflow='run', command_boundaries={}, imported_programs={'child': producer},
        source_roots=(tmp_path,), workspace_root=tmp_path)
    assert typed.imported_programs['child'] is producer
    if shadow == 'let':
        baseline = compile_typed_program(path, entry_workflow='run', command_boundaries={},
            source_roots=(tmp_path,), workspace_root=tmp_path)
        assert 'child' not in typed.module_workflow_signatures['host/entry']
        assert typed.entry.typed_body == baseline.entry.typed_body
        return  # This frontend-accepted let-bound WorkflowRef already fails WCC without any capsule.
    program = build_closed_program(typed)
    assert not _requests(program)
    assert evaluate_closed_program(program, {}).json_value() == {'n': 7}


@pytest.mark.parametrize('mode', ['bundle', 'workflow'])
def test_capsule_reference_discovery_covers_run_ref_program_selection(tmp_path, monkeypatch, mode):
    from orchestrator.workflow_lisp import workflows
    from tests.test_workflow_lisp_run_ref_workflow_program import POLICY
    path = install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/producer) (export run) (defworkflow run ((n Int)) -> Int n))''')
    producer = compile_typed_program(path, entry_workflow='run', command_boundaries={}, source_roots=(tmp_path,), workspace_root=tmp_path)
    path.unlink()
    selected = []
    original = workflows._signature_from_imported_typed_program
    def observe(alias, program, *, type_env):
        selected.append((type_env.module_name, alias))
        return original(alias, program, type_env=type_env)
    monkeypatch.setattr(workflows, '_signature_from_imported_typed_program', observe)
    policy = '(:setup ())' if mode == 'bundle' else POLICY
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
      (defmodule host/entry) (export run)
      (defworkflow run () -> Int
        (let* ((result (run-ref :source (:repo "file:///srv/project.git" :commit "{'a' * 40}")
          :program (:{mode} child) :inputs (:n 7) :policy {policy}))) 7)))'''
    path = install(tmp_path, source)
    typed = compile_typed_program(path, entry_workflow='run', command_boundaries={}, imported_programs={'child': producer},
        source_roots=(tmp_path,), workspace_root=tmp_path)
    assert 'child' in typed.module_workflow_signatures['host/entry']
    assert ('host/entry', 'child') in selected
