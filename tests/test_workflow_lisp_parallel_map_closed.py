from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram, ClosedProgramInvalid
from orchestrator.contracts.closed_program.sites import _ast_nodes
from tests.workflow_lisp_closed_program_helpers import build
from tests.test_workflow_evaluated_provider_io import CONFIG, PRODUCER, _checked, _calls
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from tests.test_workflow_lisp_parallel_map_wcc import MAP as WCC_MAP, COMMAND, source

MAP = WCC_MAP.replace('(list "a" "b")', '(list "a" "b" "c" "d")')


def test_public_parallel_compilation_and_readback(tmp_path):
    program = build(tmp_path, source(MAP))
    loaded = ClosedProgram.from_artifact(program.artifact())
    node, = [n for n in _ast_nodes(loaded.tree['body']) if n['k'] == 'par-map']
    assert (node['max'], node['parallel']) == (4, 2)
    assert node['label'] == 'repo'
    assert node['item_type'] == {'kind': 'primitive', 'name': 'String'}
    assert node['workspace']['k'] == 'block'
    assert loaded.digest == program.digest
    assert any('par-map:repo[*]' in site for _, site in loaded.sites)



def maps(program):
    bodies = [program.tree['body'], *(row['body'] for row in program.tree['definitions'].values())]
    return [node for body in bodies for node in _ast_nodes(body) if node['k'] == 'par-map']


def checked(tmp_path, text, **kwargs):
    program = build(tmp_path, text, **kwargs)
    return ClosedProgram.from_artifact(program.artifact())


@pytest.mark.parametrize('kind', ['workflow', 'inline', 'private-workflow', 'imported-workflow'])
def test_parallel_helper_bodies_roundtrip(tmp_path, kind):
    command = '(command-result fetch :argv ("python" "probe.py" "fetch" repo) :returns Box)'
    declaration = f'(defworkflow worker ((repo String)) -> Box {command})'
    call = '(call worker :repo repo)'
    if kind in ('inline', 'private-workflow'):
        declaration = f'(defproc worker ((repo String)) -> Box :effects ((uses-command fetch)) :lowering {kind} {command})'
        call = '(worker repo)'
    text = source(MAP.replace(command, call), declarations=declaration)
    kwargs = {}
    if kind == 'imported-workflow':
        text = {'parallel.orc': source(MAP.replace(command, '(call h.worker :repo repo)'),
            imports='(import helper :as h :only (worker Box))', result='List[h.Box]'),
            'helper.orc': f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
                (defmodule helper) (export worker Box) (defrecord Box (n Int)) {declaration})'''}
        kwargs['entry_path'] = 'parallel.orc'
    program = checked(tmp_path, text, **kwargs)
    node, = maps(program)
    assert node['result']['kind'] == 'list'
    assert any(n['k'] in ('call', 'perform') for n in _ast_nodes(node['body']))
    assert any('par-map:repo[*]' in (n.get('frame') or n.get('site') or '') for n in _ast_nodes(node['body']))


def test_pure_workspace_helper_and_map_value(tmp_path):
    declarations = '''(defproc cwd ((value String)) -> String :effects () :lowering inline
        (let* ((copy value)) (string/concat copy "/work")))'''
    body = f'(let* ((batch {MAP.replace(":workspace repo", ":workspace (cwd repo)")})) (list/length batch))'
    program = checked(tmp_path, source(body, declarations=declarations, result='Int'))
    node, = maps(program)
    assert node['workspace']['body']['k'] == 'let'
    assert node['result']['kind'] == 'list'
    assert program.tree['result'] == {'kind': 'primitive', 'name': 'Int'}


def test_path_workspace_is_checked(tmp_path):
    body = MAP.replace(':workspace repo', ':workspace root')
    program = checked(tmp_path, source(body, declarations='(defpath Repo :kind relpath :under "repos" :must-exist false)', params='(root Repo)'))
    assert maps(program)[0]['workspace']['k'] == 'block'


def test_homonymous_captured_binder_roundtrip(tmp_path):
    mapped = MAP.replace('(command-result fetch :argv ("python" "probe.py" "fetch" repo) :returns Box)', '(hook repo)')
    declarations = f'''(defproc apply ((hook ProcRef[String -> String])) -> List[String]
        :effects () :lowering inline {mapped})'''
    body = '''(let* ((repo "creation"))
        (let-proc (remember ((value String)) -> String :captures (repo) repo)
            (apply (proc-ref remember))))'''
    program = checked(tmp_path, source(body, declarations=declarations, result='List[String]'))
    node, = maps(program)
    assert node['label'] == 'repo'
    capture = program.tree['body']['body']
    assert capture['value']['n'] == program.tree['body']['name']
    assert node['body']['value']['n'] == capture['name']
    assert capture['name'] != node['binder']
    assert any(n['k'] == 'lit' and n['v'] == 'creation' for n in _ast_nodes(program.tree['body']))


@pytest.mark.parametrize('kind', ['direct', 'helper', 'nested'])
def test_map_owned_command_index_scopes(tmp_path, kind):
    command = '(command-result fetch :argv ("python" "probe.py" "${loop.index}") :returns Box)'
    mapped = MAP.replace('(command-result fetch :argv ("python" "probe.py" "fetch" repo) :returns Box)', command)
    declarations = ''
    result = 'List[Box]'
    if kind == 'helper':
        loop = '(loop/recur :max 1 :state 0 :on-exhausted own (fn (state) (done own)))'
        declarations = f'(defproc worker ((repo String)) -> Box :effects ((uses-command fetch)) :lowering inline (let* ((own {command})) {loop}))'
        mapped = MAP.replace('(command-result fetch :argv ("python" "probe.py" "fetch" repo) :returns Box)', '(worker repo)')
    if kind == 'nested':
        inner = mapped.replace('repo', 'inner')
        declarations = f'(defproc worker ((repo String)) -> List[Box] :effects ((uses-command fetch)) :lowering inline (let* ((own {command})) {inner}))'
        mapped = MAP.replace(COMMAND, '(worker repo)')
        result = 'List[List[Box]]'
    program = checked(tmp_path, source(mapped, declarations=declarations, result=result))
    nodes = maps(program)
    assert all('index' in node for node in nodes)
    assert len({node['index'] for node in nodes}) == len(nodes)
    for node in nodes:
        forged = deepcopy(program.tree)
        bodies = [forged['body'], *(r['body'] for r in forged['definitions'].values())]
        target = next(n for body in bodies for n in _ast_nodes(body) if n['k'] == 'par-map' and n['index'] == node['index'])
        target['index'] = target['binder']
        with pytest.raises(ClosedProgramInvalid):
            ClosedProgram.from_artifact(json.dumps(forged))


def test_nested_map_and_loop_sites(tmp_path):
    command = '(command-result fetch :argv ("python" "probe.py" "fetch" repo) :returns Box)'
    loop = f'(loop/recur :max 2 :state (loop-state (n Int 0)) :on-exhausted (record Box :n 0) (fn (state) (done {command})))'
    inner = MAP.replace(command, '(call leaf :repo repo)')
    declarations = f'(defworkflow leaf ((repo String)) -> Box {loop}) (defworkflow worker ((root String)) -> List[Box] {inner})'
    program = checked(tmp_path, source(MAP.replace(command, '(call worker :root repo)'), declarations=declarations, result='List[List[Box]]'))
    assert len(maps(program)) == 2
    assert any('loop:state[*]' in site for _, site in program.sites)
    assert sum('par-map:repo[*]' in n.get('frame', '') for body in [program.tree['body'], *(r['body'] for r in program.tree['definitions'].values())] for n in _ast_nodes(body)) == 2


def test_imported_provider_carrier_under_parallel_map(tmp_path):
    original = tmp_path / "original" / "cp" / "producer.orc"
    original.parent.mkdir(parents=True)
    original.write_text(PRODUCER)
    staged = compile_stage3_entrypoint(original, source_roots=(tmp_path / "original",),
        workspace_root=tmp_path / "original", **CONFIG).entry_result.typed_program
    staged = replace(staged, entry=staged.workflows["cp/producer::run"])
    imports = {}
    for side in ("left", "right"):
        selected = tmp_path / side / "cp" / "producer.orc"
        selected.parent.mkdir(parents=True)
        selected.write_text(PRODUCER)
        imports[side] = replace(staged, _io_source_paths={"cp/producer": selected})
    original.unlink()
    text = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
      (defmodule main) (export run) (defrecord Box (n Int))
      (defworkflow worker ((input Box)) -> Box
          (let* ((a (call left :input input)) (b (call right :input a))) b))
      (defworkflow run ((input Box)) -> List[Box]
        (list/map-effect ((repo (list "a" "b"))) :max 4 :parallel 2 :workspace repo
          (call worker :input input))))'''
    source_path = tmp_path / "main.orc"
    source_path.write_text(text)
    typed = compile_typed_program(source_path, entry_workflow="run",
        source_roots=(tmp_path,), workspace_root=tmp_path,
        imported_programs=imports, **CONFIG)
    program, io = _checked(typed)
    outer, = _calls(program.tree['body'])
    assert 'par-map:repo[*]' in outer['frame']
    worker = io.call(program.tree['entry'], outer['frame'], io.entry)
    a, b = _calls(program.tree['definitions'][outer['callee']]['body'])
    assert a['callee'] == b['callee']
    for call, side in ((a, 'left'), (b, 'right')):
        child = io.call(worker.owner, call['frame'], worker)
        assert child.reader.workflow_path == imports[side]._io_source_paths["cp/producer"]
    with pytest.raises(ValueError, match='carrier does not match'):
        replace(io, calls={}).bind(program)


def test_parallel_path_run_ref_result_descriptor_lineage(tmp_path):
    run_ref = '''(run-ref :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567")
        :program (:path "child.orc" :entry child) :inputs (:n 1) :returns Int
        :policy (:environment :deterministic-effect-free :setup ()))'''
    mapped = MAP.replace(COMMAND, run_ref)
    body = f'(let* ((batch {mapped})) (list/map ((out batch)) out.value))'
    program = checked(tmp_path, source(body, result='List[Int]'))
    node, = maps(program)
    effect, = [n for n in _ast_nodes(node['body']) if n['k'] == 'perform']
    assert effect['class'] == 'run_ref'
    assert node['result']['item'] == effect['result']
    assert 'RunRefResult$' in node['result']['item']['name']
    assert program.tree['result'] == {'kind': 'list', 'item': {'kind': 'primitive', 'name': 'Int'}}


def test_parameterized_source_and_once_only_pure_source(tmp_path):
    empty = checked(tmp_path / 'empty', source(MAP.replace('(list "a" "b" "c" "d")', 'repos'), params='(repos List[String])'))
    node, = maps(empty)
    assert node['source']['n'] == empty.tree['params'][0][0]
    once = MAP.replace('(list "a" "b" "c" "d")', '(let* ((one root)) (list one one))')
    program = checked(tmp_path / 'once', source(once, params='(root String)'))
    node, = maps(program)
    assert program.tree['body']['k'] == 'let'
    assert program.tree['body']['value']['n'] == program.tree['params'][0][0]
    assert node['source']['k'] == 'list'
    assert node['source']['items'][0]['n'] == node['source']['items'][1]['n']


def test_authored_map_label_percent_escaping(tmp_path):
    label = 'repo%/=#[]'
    program = checked(tmp_path, source(MAP.replace('repo', label)))
    node, = maps(program)
    assert node['label'] == label
    assert any('par-map:repo%25%2F%3D%23%5B%5D[*]' in site for _, site in program.sites)


def test_public_cli_compiles_actual_parallel_control(tmp_path):
    from tests.test_workflow_lisp_closed_program_compile_cli import _write_workspace, _compile

    files = _write_workspace(tmp_path, target='2.37')
    files['source'].write_text(source(MAP.replace('fetch', 'probe_revise').replace('probe.py', 'probe_revise.py')).replace('(defmodule parallel)', '(defmodule grt/entry)'))
    completed = _compile(files)
    assert completed.returncode == 0, completed.stderr
    artifact = json.loads(completed.stdout)['build_root']
    program = ClosedProgram.from_artifact((tmp_path / artifact / 'closed_program.json').read_text())
    assert len(maps(program)) == 1
    assert program.tree['target'] == '2.37'


def test_effectful_bound_capture_keeps_creation_binding_under_map(tmp_path):
    declaration = f'''(defproc apply ((hook ProcRef[String -> Box])) -> List[Box]
        :effects () :lowering inline {MAP.replace(COMMAND, '(hook repo)')})'''
    body = f'''(let* ((repo root))
      (let-proc (remember ((value String)) -> Box :captures (repo)
        {COMMAND}) (apply (proc-ref remember))))'''
    program = checked(tmp_path, source(body, declarations=declaration, params="(root String)"))
    node, = maps(program)
    calls = [n for n in _ast_nodes(node['body']) if n['k'] == 'call']
    assert calls
    call = calls[0]
    assert call['args'][0]['n'] != node['binder']
    assert program.tree['definitions'][call['callee']]['key'][7]


PURE_NESTED_INLINE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule parallel) (export run)
  (defproc identity ((value String)) -> String :effects () :lowering inline value)
  (defproc worker ((root String)) -> List[String] :effects () :lowering inline
    (list/map-effect ((child (list root))) :max 1 :parallel 1 :workspace child
      (identity child)))
  (defworkflow run () -> List[List[String]]
    (list/map-effect ((repo (list "a"))) :max 1 :parallel 1 :workspace repo
      (worker repo))))'''


def test_pure_nested_inline_helper_retains_checked_maps(tmp_path):
    program = checked(tmp_path, PURE_NESTED_INLINE)
    assert len(maps(program)) == 2
    assert program.sites == ()


@pytest.mark.parametrize('body', [
    '(worker (command-result fetch :argv ("python" "probe.py") :returns String))',
    '(list/map-effect ((other (list repo))) :max 1 :parallel 1 :workspace other (identity other))',
    '(let* ((copy repo)) (worker copy))',
    '(if true (worker repo) (worker repo))',
])
def test_nested_inline_fix_preserves_authored_call_and_pure_argument_rules(tmp_path, body):
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError

    text = PURE_NESTED_INLINE.replace('(worker repo)', body)
    with pytest.raises(LispFrontendCompileError) as error:
        checked(tmp_path, text)
    assert error.value.diagnostics[0].code == 'list_map_effect_body_unsupported'
