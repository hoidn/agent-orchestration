"""Private transport script retirement, never reads script bytes for authority."""
import importlib
import os
from pathlib import Path

import pytest


def module():
    try:
        return importlib.import_module('orchestrator.workflow.run_ref.holder_scripts')
    except ModuleNotFoundError:
        pytest.fail('verified script retirement is not implemented')


def fixture_tree(tmp_path):
    root = tmp_path/'runref-owned'
    root.mkdir(mode=0o700)
    leaf = root/'leaf'
    leaf.mkdir(mode=0o700)
    script = leaf/'leaf.sh'
    script.write_bytes(b'private-fixture-capability')
    script.chmod(0o600)
    return root, leaf, script


def identity(path):
    info = path.lstat()
    return info.st_dev, info.st_ino


def test_live_script_retirement_verifies_identity_and_absence_without_removing_root(tmp_path):
    root, leaf, script = fixture_tree(tmp_path)
    m = module()
    expected = identity(root)
    m.retire_leaf(root, 'leaf', parent_identity=identity(tmp_path), root_identity=expected,
                  leaf_identity=identity(leaf))
    assert root.is_dir() and not list(root.iterdir())
    m.retire_leaf(root, 'leaf', parent_identity=identity(tmp_path), root_identity=expected,
                  leaf_identity=(0,0))


@pytest.mark.parametrize('kind',['root-symlink','leaf-symlink','script-symlink','extra','mode','replacement','parent'])
def test_invalid_script_tree_is_preserved_and_recovery_does_not_follow_it(tmp_path, kind):
    root, leaf, script = fixture_tree(tmp_path)
    m = module()
    expected = identity(root)
    foreign = tmp_path/'foreign'
    foreign.mkdir(mode=0o700)
    (foreign/'keep').write_bytes(b'preserve')
    if kind == 'root-symlink':
        root.rename(tmp_path/'withdrawn');root.symlink_to(foreign, target_is_directory=True)
    elif kind == 'leaf-symlink':
        leaf.rename(root/'withdrawn');leaf.symlink_to(foreign,target_is_directory=True)
    elif kind == 'script-symlink':
        script.unlink();script.symlink_to(foreign/'keep')
    elif kind == 'extra':
        (leaf/'extra').write_bytes(b'preserve')
    elif kind == 'mode':
        leaf.chmod(0o777)
    elif kind == 'replacement':
        root.rename(tmp_path/'withdrawn');root.mkdir(mode=0o700)
    parent_identity = (0,0) if kind == 'parent' else identity(tmp_path)
    with pytest.raises(Exception):
        m.retire_leaf(root,'leaf',parent_identity=parent_identity,root_identity=expected,leaf_identity=identity(leaf) if leaf.exists() else (0,0))
    assert (foreign/'keep').read_bytes() == b'preserve' and os.path.lexists(root)


def test_recovery_validates_all_roots_before_mutation_and_readonly_never_deletes(tmp_path):
    root, leaf, script = fixture_tree(tmp_path)
    m = module()
    m.recover_scripts(tmp_path, [root.name], readonly=True)
    assert script.exists()
    extra = tmp_path/'runref-foreign'
    extra.mkdir(mode=0o700)
    (extra/'foreign').symlink_to('/not-followed')
    with pytest.raises(Exception):
        m.recover_scripts(tmp_path,[root.name,extra.name])
    assert script.exists()
    (extra/'foreign').unlink();extra.rmdir()
    m.recover_scripts(tmp_path,[root.name])
    assert not root.exists()


def test_script_unlink_failure_is_sticky_in_scope_and_preserves_the_script(tmp_path, monkeypatch):
    from orchestrator.workflow.run_ref import holder_scope
    root, leaf, script = fixture_tree(tmp_path)
    m = module()
    scope = holder_scope.HolderScope(object(),{},control_dir=tmp_path)
    scope.runref, scope._script_identities = root, m.identities(root)
    original = os.unlink
    def fail(name, **kwargs):
        if name == 'leaf.sh':
            raise OSError('private-unlink-canary')
        return original(name,**kwargs)
    monkeypatch.setattr(os,'unlink',fail)
    for _ in range(2):
        with pytest.raises(holder_scope.HolderDeathError,match='holder_script_retirement_refused'):
            scope.retire_leaf_script('leaf',identity(leaf))
    assert script.exists()


def test_old_boot_script_inventory_authorizes_retirement_but_never_current_scope_kill(tmp_path, monkeypatch):
    from orchestrator.workflow.run_ref import holder_scope
    from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
    control = tmp_path/'holder'
    control.mkdir(mode=0o700)
    name = 'a'*16
    root = control/('runref-'+name)
    root.mkdir(mode=0o700)
    leaf = root/'leaf'
    leaf.mkdir(mode=0o700)
    (leaf/'leaf.sh').write_bytes(b'private-revoked-fixture-capability')
    (leaf/'leaf.sh').chmod(0o600)
    row = dict(schema_version='run_ref_holder_scope.v1',boot_id='old',
        scope_path='/sys/fs/cgroup/run-ref-'+name+'.scope',unit='run-ref-'+name+'.scope',
        launch_token='sha256:'+'a'*64,containment_identity='sha256:'+'b'*64)
    (control/('scope-'+name+'.json')).write_bytes(canonical_json_bytes(row))
    monkeypatch.setattr(holder_scope,'boot_id',lambda:'current')
    monkeypatch.setattr(holder_scope,'kill_cgroup',lambda *a,**kw:pytest.fail('old boot never authorizes current kill'))
    assert holder_scope.recover_holder_scopes(control,readonly=True) is False
    assert (leaf/'leaf.sh').exists()
    assert holder_scope.recover_holder_scopes(control) is False
    assert not root.exists()
