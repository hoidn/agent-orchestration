"""One baseline launch projected to every applicable arm, admitted against every policy."""
import json
from pathlib import Path

import pytest

from experiments.orc_structural_search import three_arm
from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.mode1 import continued


def test_parent_jobs_admit_every_arm_but_launch_each_snapshot_once(tmp_path, monkeypatch):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'mutable_files': ['direct.orc'], 'mutable_definitions': ['run'],
                                 'condition': 'topology-only', 'entry_workflow': 'direct::run', 'interface': 'I1',
                                 'source_root': '.', 'providers_file': 'providers.json',
                                 'command_boundaries_file': 'commands.json', 'episode_wall_clock_sec': 30,
                                 'criterion_sha256': 'ab' * 32, 'models': {'m': ['high']}, 'per_call_timeout_sec': 60}))
    frozen = {'arms': {'I1': {'interface': 'I1', 'condition': 'topology-only', 'parent': 'orc'},
                      'I1/module': {'interface': 'I1', 'condition': 'module', 'parent': 'orc'},
                      'I3': {'interface': 'I3', 'condition': 'topology-only', 'parent': 'python'}}}
    roots = {'orc': tmp_path / 'ORC', 'python': tmp_path / 'PY'}
    seen = []
    monkeypatch.setattr(three_arm, 'require_candidate', lambda root, cfg, **kw: seen.append((root, cfg.condition)))
    monkeypatch.setattr(three_arm, 'check_parent', lambda root, cfg, **kw: seen.append((root, cfg.interface)))
    jobs = three_arm.parent_jobs(roots, config, frozen, runtime=tmp_path)
    assert seen == [(roots['orc'], 'topology-only'), (roots['orc'], 'module'), (roots['python'], 'I3')]
    assert len(jobs) == 2
    assert jobs[0][2]['parent_for_arms'] == ['I1', 'I1/module']
    task = tmp_path / 'task'
    units = continued(jobs, [task], 2, [])
    assert len(units) == 4
    prior = [{'kind': 'evaluation', **u.fields, 'task_id': u.task.name, 'replicate': u.replicate,
              'outcome': 'completed', 'split': 'unavailable'} for u in units]
    assert continued(jobs, [task], 2, prior) == []


def test_stronger_module_parent_admission_cannot_be_bypassed(tmp_path, monkeypatch):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'mutable_files': ['direct.orc'], 'mutable_definitions': ['run'],
                                 'condition': 'topology-only', 'entry_workflow': 'direct::run', 'interface': 'I1',
                                 'source_root': '.', 'providers_file': 'providers.json',
                                 'command_boundaries_file': 'commands.json', 'episode_wall_clock_sec': 30,
                                 'criterion_sha256': 'ab' * 32, 'models': {'m': ['high']}, 'per_call_timeout_sec': 60}))
    frozen = {'arms': {'I1': {'interface': 'I1', 'condition': 'topology-only', 'parent': 'orc'},
                      'module': {'interface': 'I1', 'condition': 'module', 'parent': 'orc'}}}
    def admit(root, cfg, **kw):
        if cfg.condition == 'module':
            raise ValueError('module policy refused')
    monkeypatch.setattr(three_arm, 'require_candidate', admit)
    with pytest.raises(ValueError, match='module policy refused'):
        three_arm.parent_jobs({'orc': tmp_path / 'ORC'}, config, frozen, runtime=tmp_path)


def test_frozen_surface_adjudication_counts_malformed_as_unadjudicated(tmp_path):
    from experiments.orc_structural_search.three_arm_figures import frozen_surface
    episodes = []
    for index, adjudication in enumerate([{'verdict': 'worked_around', 'note': 'read transcript'},
            {'verdict': 'asked', 'note': ''}, {'verdict': 'none', 'note': 'reviewed'},
            {'verdict': 'none', 'note': None}, None]):
        episode = {'episode_id': str(index)}
        episodes.append(episode)
        path = tmp_path / 'episodes' / str(index) / 'record.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'frozen_surface': adjudication}))
    assert frozen_surface(episodes, tmp_path) == {'worked_around': 1, 'asked': 1, 'none': 1, 'unadjudicated': 2}
