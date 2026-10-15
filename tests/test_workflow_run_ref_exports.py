"""Typed confined exports use real fd copies and no-overwrite publication."""
import os
from pathlib import Path

import pytest

from orchestrator.workflow.run_ref.runtime import RunRefRuntimeError

PATH = {'kind': 'path', 'name': 'Artifact', 'under': 'out', 'must_exist_target': True}


def _export(tmp_path, value, descriptor, *, hook=lambda boundary: None, events=None, **limits):
    from orchestrator.workflow.run_ref.confined_exports import export_value
    clone, parent = tmp_path / 'clone', tmp_path / 'parent'
    clone.mkdir(exist_ok=True); parent.mkdir(exist_ok=True)
    events = [] if events is None else events
    return export_value(value, descriptor, clone=clone, parent=parent, parent_run='parent-run',
        activation='activation', attempt=1, max_bytes=limits.pop('max_bytes', 1024),
        prepared_events=events, persist=lambda event: events.append(event), crash_hook=hook, **limits)


def test_typed_exports_share_identical_aliases_and_compatible_tree_overlap(tmp_path):
    (tmp_path / 'clone/out/tree/empty').mkdir(parents=True)
    (tmp_path / 'clone/out/tree/item').write_bytes(b'abc')
    descriptor = {'kind': 'record', 'name': 'Bundle', 'fields': [
        {'name': 'tree', 'type': PATH}, {'name': 'aliases', 'type': {'kind': 'list', 'item': PATH}}]}
    value = {'tree': 'out/tree', 'aliases': ['out/tree/item', 'out/tree/item']}
    rebased, proof = _export(tmp_path, value, descriptor)
    prefix = 'out/.run-ref-exports/parent-run/activation/1/'
    assert rebased == {'tree': prefix + 'tree', 'aliases': [prefix + 'tree/item'] * 2}
    assert (tmp_path / 'parent' / rebased['tree'] / 'empty').is_dir()
    assert (tmp_path / 'parent' / rebased['aliases'][0]).read_bytes() == b'abc'
    assert proof['bytes'] == 3
    assert len(proof['entries']) == 3
    assert len(proof['paths']) == 3
    import shutil
    other = tmp_path / 'permuted'
    shutil.copytree(tmp_path / 'clone', other / 'clone')
    reordered = {**descriptor, 'fields': list(reversed(descriptor['fields']))}
    rebased_again, proof_again = _export(other, value, reordered)
    assert rebased_again == rebased and proof_again['entries'] == proof['entries']


@pytest.mark.parametrize('change', ['descriptor', 'hardlink', 'symlink', 'reserved', 'missing', 'bytes', 'entries', 'depth'])
def test_exports_refuse_unsafe_sources_and_aggregate_limits(tmp_path, change):
    clone = tmp_path / 'clone'
    (clone / 'out/dir').mkdir(parents=True)
    (clone / 'out/dir/a').write_bytes(b'abc')
    value, descriptor, limits = 'out/dir', PATH, {}
    if change == 'descriptor':
        descriptor = {'kind': 'record', 'name': 'Bundle', 'fields': [
            {'name': 'a', 'type': PATH}, {'name': 'b', 'type': {**PATH, 'name': 'Other'}}]}
        value = {'a': 'out/dir', 'b': 'out/dir'}
    elif change == 'hardlink':
        os.link(clone / 'out/dir/a', clone / 'out/dir/b')
    elif change == 'symlink':
        (clone / 'out/dir/b').symlink_to('a')
    elif change == 'reserved':
        value = '.git/a'; descriptor = {**PATH, 'under': '.git'}
    elif change == 'missing':
        value = 'out/absent'
    elif change == 'bytes':
        limits['max_bytes'] = 2
    elif change == 'entries':
        limits['max_entries'] = 1
    elif change == 'depth':
        limits['max_depth'] = 0
    with pytest.raises(RunRefRuntimeError, match='run_ref_export_invalid'):
        _export(tmp_path, value, descriptor, **limits)
    assert not list((tmp_path / 'parent').rglob('a'))


@pytest.mark.parametrize('boundary', ['export_prepared', 'export_renamed'])
def test_export_foreign_identical_destination_is_preserved(tmp_path, boundary):
    (tmp_path / 'clone/out').mkdir(parents=True)
    (tmp_path / 'clone/out/a').write_bytes(b'abc')
    destination = tmp_path / 'parent/out/.run-ref-exports/parent-run/activation/1/a'
    def substitute(point):
        if point == boundary:
            if destination.exists():
                destination.rename(destination.with_name('displaced'))
            destination.write_bytes(b'abc')
    with pytest.raises(RunRefRuntimeError, match='run_ref_export_invalid'):
        _export(tmp_path, 'out/a', PATH, hook=substitute)
    assert destination.read_bytes() == b'abc'


def test_export_recovers_own_rename_with_lost_acknowledgement(tmp_path):
    (tmp_path / 'clone/out').mkdir(parents=True)
    (tmp_path / 'clone/out/a').write_bytes(b'abc')
    events = []
    def crash(point):
        if point == 'export_renamed':
            raise RuntimeError('controller crash')
    with pytest.raises(RuntimeError, match="controller crash"):
        _export(tmp_path, 'out/a', PATH, hook=crash, events=events)
    destination = tmp_path / 'parent/out/.run-ref-exports/parent-run/activation/1/a'
    inode = destination.stat().st_ino
    value, proof = _export(tmp_path, 'out/a', PATH, events=events)
    assert (tmp_path / 'parent' / value).stat().st_ino == inode
    assert len(events) == 1 and proof['bytes'] == 3


@pytest.mark.parametrize('phase', ['inspect', 'copy'])
def test_growing_export_source_is_bounded_during_read(tmp_path, monkeypatch, phase):
    from orchestrator.workflow.run_ref import confined_exports as exports
    clone = tmp_path / 'clone'; clone.mkdir()
    source = clone / 'item'; source.write_bytes(b'abc')
    parent = tmp_path / 'parent'; parent.mkdir()
    root = os.open(clone, os.O_RDONLY | os.O_DIRECTORY)
    destination = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        expected = exports._inspect(root, 'item', max_bytes=3)
        real_read, observed, grown = os.read, [], []
        identity = source.stat().st_ino
        def grow(fd, maximum):
            result = real_read(fd, maximum)
            if os.fstat(fd).st_ino == identity:
                observed.append(len(result))
                if not grown:
                    grown.append(True)
                    with source.open('ab') as stream:
                        stream.write(b'x' * 4096)
            return result
        monkeypatch.setattr(exports.os, 'read', grow)
        with pytest.raises(RunRefRuntimeError):
            if phase == 'inspect':
                exports._inspect(root, 'item', max_bytes=3)
            else:
                exports._copy_file(root, 'item', destination, 'staged', expected)
        assert sum(observed) <= 4
        if phase == 'copy':
            assert (parent / 'staged').stat().st_size <= 3
    finally:
        os.close(root); os.close(destination)


def test_nested_optional_union_map_paths_keep_every_location_and_nominal_alias(tmp_path):
    (tmp_path / 'clone/out').mkdir(parents=True)
    (tmp_path / 'clone/out/a').write_bytes(b'abc')
    nested = {'kind': 'map', 'key': {'kind': 'primitive', 'name': 'String'},
              'value': {'kind': 'map', 'key': {'kind': 'primitive', 'name': 'String'}, 'value': PATH}}
    descriptor = {'kind': 'union', 'name': 'Choice', 'variants': [
        {'name': 'YES', 'fields': [{'name': 'paths', 'type': nested},
                                  {'name': 'maybe', 'type': {'kind': 'optional', 'item': PATH}}]},
        {'name': 'NO', 'fields': []}]}
    value = {'variant': 'YES', 'paths': {'a][b': {'c': 'out/a'}, 'a': {'b][c': 'out/a'}}, 'maybe': None}
    rebased, proof = _export(tmp_path, value, descriptor)
    assert rebased['paths']['a][b']['c'] == rebased['paths']['a']['b][c']
    assert rebased['maybe'] is None and proof['bytes'] == 3
    assert len(proof['paths']) == len({row['location'] for row in proof['paths']}) == 2
    assert all(row['descriptor'] == PATH for row in proof['paths'])


def test_export_limits_are_aggregate_and_count_source_ancestors_once(tmp_path):
    (tmp_path / 'clone/out/dir/empty').mkdir(parents=True)
    (tmp_path / 'clone/out/dir/a').write_bytes(b'ab')
    (tmp_path / 'clone/out/dir/b').write_bytes(b'cd')
    shape = {'kind': 'list', 'item': PATH}
    value = ['out/dir/a', 'out/dir/b', 'out/dir/empty']
    rebased, proof = _export(tmp_path, value, shape, max_bytes=4, max_entries=4, max_depth=2)
    assert proof['bytes'] == 4 and len(proof['entries']) == 4
    other = tmp_path / 'over'; (other / 'clone/out/dir/empty').mkdir(parents=True)
    for name in ('a', 'b'):
        (other / 'clone/out/dir' / name).write_bytes(b'ab')
    with pytest.raises(RunRefRuntimeError, match='export_byte_bound'):
        _export(other, value, shape, max_bytes=3, max_entries=4)


@pytest.mark.parametrize('side', ['source', 'destination'])
def test_export_refuses_same_device_nested_mount_even_when_empty(tmp_path, monkeypatch, side):
    from orchestrator.workflow.run_ref import confined_exports as exports
    (tmp_path / 'clone/out/empty').mkdir(parents=True)
    (tmp_path / 'parent/out').mkdir(parents=True)
    real = exports._statx_mount_id
    seen = []
    def mounted(fd, *args):
        actual = Path(os.readlink(f'/proc/self/fd/{fd}'))
        path = actual / args[0] if args else actual
        victim = tmp_path / ('clone/out/empty' if side == 'source' else 'parent/out')
        if path == victim:
            seen.append(os.fstat(fd).st_dev)
            return real(fd, *args) + 1
        return real(fd, *args)
    monkeypatch.setattr(exports, '_statx_mount_id', mounted)
    with pytest.raises(RunRefRuntimeError, match='nested_mount'):
        _export(tmp_path, 'out/empty', PATH)
    assert seen and (tmp_path / 'clone').stat().st_dev == (tmp_path / 'parent').stat().st_dev


def test_multiple_export_subtrees_recover_after_partial_publication(tmp_path):
    (tmp_path / 'clone/out').mkdir(parents=True)
    for name in ('a', 'b'):
        (tmp_path / 'clone/out' / name).write_bytes(name.encode())
    events = []
    def crash(point):
        if point == 'export_renamed':
            raise RuntimeError('publication interrupted')
    with pytest.raises(RuntimeError, match='interrupted'):
        _export(tmp_path, ['out/a', 'out/b'], {'kind': 'list', 'item': PATH}, events=events, hook=crash)
    first = tmp_path / 'parent/out/.run-ref-exports/parent-run/activation/1/a'
    inode = first.stat().st_ino
    rebased, proof = _export(tmp_path, ['out/a', 'out/b'], {'kind': 'list', 'item': PATH}, events=events)
    assert first.stat().st_ino == inode and len(events) == 2
    assert [(tmp_path / 'parent' / value).read_bytes() for value in rebased] == [b'a', b'b']


@pytest.mark.parametrize('count', [1024, 2048])
def test_export_independent_roots_check_only_their_path_ancestors(count):
    from orchestrator.workflow.run_ref.confined_exports import _publication_roots
    class Descriptors(dict):
        lookups = 0
        def get(self, path):
            self.lookups += 1
            return super().get(path)
    paths = [f'out/item-{index:04d}' for index in range(count)]
    shapes = Descriptors.fromkeys(paths, PATH)
    assert _publication_roots(paths, shapes) == paths
    assert shapes.lookups == count * 2  # 'out' and '.', never another returned sibling.


def test_export_roots_compare_each_ancestor_and_preserve_canonical_order():
    from orchestrator.workflow.run_ref.confined_exports import _publication_roots
    paths = ['out/a', 'out/a/b', 'out/a/b/item', 'out/z']
    shapes = dict.fromkeys(paths, PATH)
    assert _publication_roots(paths, shapes) == ['out/a', 'out/z']
    shapes['out/a'] = {**PATH, 'under': 'other'}
    with pytest.raises(RunRefRuntimeError, match='overlap_mapping_conflict'):
        _publication_roots(paths, shapes)
