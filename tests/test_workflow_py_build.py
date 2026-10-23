"""Retained Python source bundles are deterministic and fail closed."""
import importlib
import json
from pathlib import Path

import pytest

from tests.test_workflow_py_frontend import load, compile_source, PREFIX


SIMPLE = PREFIX + '@workflow(returns=str)\ndef run(value: str): return value\n'


def test_repeated_build_and_source_line_edit_have_correct_identity(tmp_path):
    from orchestrator.py import build
    module, first = compile_source(tmp_path, SIMPLE)
    before = {p.name: p.read_bytes() for p in first.source_path.parent.iterdir()}
    second = build(module.run, workspace=tmp_path)
    assert second.source_path == first.source_path
    assert second.closed_result.program.digest == first.closed_result.program.digest
    assert {p.name: p.read_bytes() for p in second.source_path.parent.iterdir()} == before
    module = load(tmp_path, '# added source line\n' + SIMPLE)
    third = build(module.run, workspace=tmp_path)
    assert third.source_path != first.source_path
    source_map = json.loads(third.source_map_path.read_text())
    assert list(source_map['sources']) == ['author.py']
    assert all(not Path(entry['file']).is_absolute() for entry in source_map['entries'])
    module = load(tmp_path, '# edited source line\n' + SIMPLE)
    fourth = build(module.run, workspace=tmp_path)
    assert fourth.source_path != third.source_path


@pytest.mark.parametrize('mutation', ['source', 'map', 'extra', 'missing', 'symlink'])
def test_existing_bundle_exact_reuse_refuses_corruption_without_overwrite(tmp_path, mutation):
    from orchestrator.py import build
    module, built = compile_source(tmp_path, SIMPLE)
    root = built.source_path.parent
    if mutation == 'source': built.source_path.write_text('corrupted')
    elif mutation == 'map': built.source_map_path.write_text('{}')
    elif mutation == 'extra': (root / 'unexpected').write_text('extra')
    elif mutation == 'missing': built.source_map_path.unlink()
    else:
        built.source_map_path.unlink()
        target = tmp_path / 'map-target'
        target.write_text('{}')
        built.source_map_path.symlink_to(target)
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(Exception): build(module.run, workspace=tmp_path)
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
    if mutation == 'symlink': assert built.source_map_path.is_symlink()


@pytest.mark.parametrize('component', ['.orchestrate', 'generated', 'run'])
def test_generation_root_symlink_is_refused(tmp_path, component):
    from orchestrator.py import build
    module = load(tmp_path, SIMPLE)
    names = ['.orchestrate', 'generated', 'run']
    root = tmp_path
    for name in names[:names.index(component)]:
        root /= name
        root.mkdir()
    target = tmp_path / 'outside'
    target.mkdir()
    (root / component).symlink_to(target, target_is_directory=True)
    with pytest.raises(Exception): build(module.run, workspace=tmp_path)
    assert not list(target.iterdir())


def test_failed_publication_selects_no_partial_bundle(tmp_path, monkeypatch):
    from orchestrator.py import build
    build_module = importlib.import_module('orchestrator.py.build')
    module = load(tmp_path, SIMPLE)
    def interrupted(*args): raise OSError('injected install failure')
    monkeypatch.setattr(build_module, 'rename_noreplace_at', interrupted)
    with pytest.raises(OSError, match='injected'): build(module.run, workspace=tmp_path)
    assert not list((tmp_path / '.orchestrate' / 'generated' / 'run').iterdir())
    assert not (tmp_path / '.orchestrate' / 'build').exists()
    assert not (tmp_path / '.orchestrate' / 'runs').exists()


def test_compile_rejection_preserves_generated_and_original_locations(tmp_path):
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
    source = PREFIX + '''@proc(returns=HostReply[str], effects=[])
def pure_question(): return ask("question", returns=str)
@workflow(returns=HostReply[str])
def run(): return pure_question()
'''
    with pytest.raises(LispFrontendCompileError) as error:
        compile_source(tmp_path, source)
    diagnostic, *_ = error.value.diagnostics
    assert Path(diagnostic.span.start.path).suffix == '.orc'
    assert any('author.py:' in note and 'pure_question' in note for note in diagnostic.notes)
    assert not (tmp_path / '.orchestrate' / 'runs').exists()
    assert list((tmp_path / '.orchestrate' / 'generated').rglob('*.orc'))


def test_template_snapshot_changes_new_build_without_mutating_old_source(tmp_path):
    from orchestrator.py import build
    template = tmp_path / 'question.md'
    template.write_text('{text}')
    source = PREFIX + '''prompt = Prompt(file="question.md", fills={"text": Text}, returns=str)
@workflow(returns=HostReply[str])
def run(text: str): return ask(prompt(text=text), returns=str)
'''
    module = load(tmp_path, source)
    # Explicit workspace owns relative build inputs, independent of this test's cwd.
    first = build(module.run, workspace=tmp_path)
    before = first.source_path.read_bytes()
    template.write_text('changed {text}')
    second = build(module.run, workspace=tmp_path)
    assert first.source_path != second.source_path
    assert first.source_path.read_bytes() == before


def test_source_roots_keep_generated_module_valid_and_manifest_paths_unchanged(tmp_path):
    providers = tmp_path / 'providers.json'
    providers.write_text('{}')
    _, built = compile_source(tmp_path, SIMPLE, source_roots=(tmp_path,), provider_externs_file=providers)
    assert built.request.source_roots[0] == built.source_path.parent
    assert built.request.source_roots[1] == tmp_path
    assert built.request.provider_externs_path == providers


@pytest.mark.parametrize('loader', ['cli', 'direct'])
def test_workspace_source_containment_normalizes_parent_components(tmp_path, loader):
    from orchestrator.cli.commands.python import load_workflow
    from orchestrator.py import build
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    outside = tmp_path / 'outside.py'
    outside.write_text(SIMPLE)
    path = workspace / '..' / 'outside.py'
    if loader == 'cli':
        entry = load_workflow(path)
    else:
        namespace = {'__name__': 'outside'}
        exec(compile(SIMPLE, str(path), 'exec'), namespace)
        entry = namespace['run']
    with pytest.raises(ValueError, match='inside the workspace'):
        build(entry, workspace=workspace)
    assert not (workspace / '.orchestrate').exists()


def test_inside_source_parent_components_have_canonical_attribution(tmp_path):
    from orchestrator.cli.commands.python import load_workflow
    from orchestrator.py import build
    (tmp_path / 'a').mkdir()
    source = tmp_path / 'source.py'
    source.write_text(SIMPLE)
    entry = load_workflow(tmp_path / 'a' / '..' / 'source.py')
    built = build(entry, workspace=tmp_path)
    assert entry.fn.__code__.co_filename == str(source)
    source_map = json.loads(built.source_map_path.read_bytes())
    assert list(source_map['sources']) == ['source.py']
    assert all(entry['file'] == 'source.py' for entry in source_map['entries'])
