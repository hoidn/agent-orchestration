"""Honest, archive-free review repositories; temporary sources and fake providers only."""
import json
import subprocess
from pathlib import Path

import pytest

from experiments.compare import pool, repos
from tests.experiments.compare_harness_support import world  # noqa: F401

ARCHIVE = 'docs/plans/evidence'


def source(world):
    repos.git(world.main, 'checkout', '-q', '--detach', world.base)
    criterion = json.loads(world.criterion.read_text())
    criterion.update(purpose='calibration', calibration_kind='task_difficulty', anchors=[])
    world.criterion.write_text(json.dumps(criterion))
    files = {f'{ARCHIVE}/report.txt': 'unique archived evidence\n',
             f'{ARCHIVE}-other/visible.txt': 'keep boundary sibling\n',
             'bin/tool': '#!/bin/sh\nexit 0\n', 'remove.txt': 'candidate may remove this\n'}
    for name, text in files.items():
        path = world.main / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
    (world.main / 'bin/tool').chmod(0o755)
    (world.main / 'data.bin').write_bytes(b'\x00old binary\xff')
    (world.main / 'code-link').symlink_to('pkg/calc.py')
    repos.git(world.main, 'add', '-A')
    repos.git(world.main, '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'fixture archive')
    source_base = repos.git(world.main, 'rev-parse', 'HEAD')
    original = world.outside / 'original'
    base = repos.build_candidate(world.runtime, source_base, world.task / 'seed', original)
    ref = {'main': str(world.main), 'runtime': str(world.runtime), 'base': source_base, 'compare_base': base}
    return original, ref


def write(world, original, ref, *, exclude=(ARCHIVE,)):
    patch = repos.patch_of(original, ref['compare_base'])
    diff = world.outside / 'candidate.diff'; diff.write_bytes(patch)
    record = {'arm': 'direct_task', 'patches': {'final': str(diff)}}
    qualification = {'retained': 'qualification proof'}
    out = world.outside / 'review-pool'
    mapping = pool.write_pool(world.task, world.criterion, out, ['judge-a'], ref, {},
                              [[('original-record-id', record, ['final'])]],
                              qualification=qualification, review_exclude=exclude)
    return out, mapping, patch


def test_review_baseline_is_new_exact_tree_without_archive_objects(world, monkeypatch):
    original, ref = source(world)
    archive_blob = repos.git(original, 'rev-parse', f"HEAD:{ARCHIVE}/report.txt")
    (original / 'pkg/calc.py').write_text('def add(a, b):\n    return a + b\n')
    (original / 'added.py').write_text('new = True\n')
    (original / 'remove.txt').unlink()
    (original / 'data.bin').write_bytes(b'\x00new binary\xfe')
    template = world.outside / 'template'; (template / 'objects/info').mkdir(parents=True)
    (template / 'objects/info/alternates').write_text(str(original / '.git/objects') + '\n')
    monkeypatch.setenv('GIT_TEMPLATE_DIR', str(template))
    out, mapping, raw = write(world, original, ref, exclude=('./docs/plans/evidence/',))
    assert mapping['review'] == {'source_compare_base': ref['compare_base'], 'excluded_paths': [ARCHIVE]}
    assert mapping['qualification'] == {'retained': 'qualification proof'}
    assert mapping['compare_base'] != ref['compare_base']
    for cid, entry in mapping['clones'].items():
        clone = out / 'clones' / cid
        assert repos.git(clone, 'rev-parse', 'HEAD') == mapping['compare_base']
        assert len(repos.git(clone, 'rev-list', '--all').splitlines()) == 1
        assert not (clone / '.git/objects/info/alternates').exists()
        assert repos.git(clone, 'remote') == ''
        for oid in (archive_blob, ref['compare_base']):
            assert subprocess.run(['git', '-C', str(clone), 'cat-file', '-e', oid], capture_output=True).returncode != 0
        assert not (clone / ARCHIVE).exists()
        assert (clone / f'{ARCHIVE}-other/visible.txt').read_bytes() == b'keep boundary sibling\n'
        assert (clone / 'bin/tool').stat().st_mode & 0o111 == 0o111
        assert (clone / 'code-link').is_symlink() and (clone / 'code-link').readlink() == Path('pkg/calc.py')
        assert all(not line.startswith(('S ', 's ')) for line in repos.git(clone, 'ls-files', '-v').splitlines())
        if entry['run'] is not None:
            assert entry['run'] == 'original-record-id' and entry['labels'] == ['final']
            assert (out / f'records/patches/{cid}.diff').read_bytes() == raw
    pool.verify_pool(out)
    assert (original / f'{ARCHIVE}/report.txt').read_bytes() == b'unique archived evidence\n'


def test_review_excludes_a_declared_symlink_without_following_it(world):
    original, ref = source(world)
    out, mapping, _ = write(world, original, ref, exclude=(ARCHIVE, 'code-link'))
    for cid in mapping['clones']:
        clone = out / 'clones' / cid
        assert not (clone / 'code-link').is_symlink()
        assert (clone / 'pkg/calc.py').is_file()


@pytest.mark.parametrize('change', ['edit', 'add', 'delete', 'rename_in', 'rename_out'])
def test_review_rejects_either_endpoint_of_real_archive_changes(world, change):
    original, ref = source(world)
    report = original / ARCHIVE / 'report.txt'
    if change == 'edit':
        report.write_text('candidate changed archive\n')
    elif change == 'add':
        (report.parent / 'new.txt').write_text('new archived answer\n')
    elif change == 'delete':
        report.unlink()
    elif change == 'rename_in':
        repos.git(original, 'mv', 'pkg/calc.py', f'{ARCHIVE}/moved.py')
    else:
        repos.git(original, 'mv', f'{ARCHIVE}/report.txt', 'outside-report.txt')
    with pytest.raises(SystemExit, match='excluded'):
        write(world, original, ref)


@pytest.mark.parametrize('excluded', ['', '.', '..', '../outside', '/absolute', '.git', 'docs/../../outside'])
def test_review_exclusions_refuse_roots_and_path_escapes(world, excluded):
    original, ref = source(world)
    with pytest.raises(SystemExit, match='relative'):
        write(world, original, ref, exclude=(excluded,))


def test_review_exclusions_require_a_sequence_instead_of_iterating_a_string():
    with pytest.raises(SystemExit, match='sequence'):
        repos.review_exclusions(ARCHIVE)


def test_review_refuses_existing_d8_patch_rewriting(world):
    original, ref = source(world)
    path = original / 'docs/design/change.md'; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('change')
    with pytest.raises(SystemExit, match='exact.*patch'):
        write(world, original, ref)


def test_review_verification_restores_original_patch_against_review_base(world):
    original, ref = source(world)
    (original / 'pkg/calc.py').write_text('def add(a, b):\n    return a + b\n')
    out, mapping, raw = write(world, original, ref)
    cid = next(cid for cid, entry in mapping['clones'].items() if entry['run'] is not None)
    clone = out / 'clones' / cid
    (clone / 'pkg/calc.py').write_text('judge changed it\n')
    with pytest.raises(SystemExit, match='restored'):
        pool.verify_pool(out)
    assert repos.patch_of(clone, mapping['compare_base']) == raw
    assert not (clone / ARCHIVE).exists()
    assert json.loads((out / 'records/mapping.json').read_text())['review'] == mapping['review']
    pool.verify_pool(out)
