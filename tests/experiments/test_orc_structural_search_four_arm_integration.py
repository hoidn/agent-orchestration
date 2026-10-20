"""Four-arm scripted launch -> blind harness clone join -> qualified Pareto readout, no provider spend."""
import json
from collections import Counter
from pathlib import Path

import pytest

from experiments.orc_structural_search import three_arm, three_arm_readout
from experiments.orc_structural_search.records import read_records
from experiments.orc_structural_search.scoring import pool_evaluations
from tests.experiments.qualification_support import module_criterion, qualified, sha, write
from tests.experiments.test_orc_structural_search_three_arm import (
    CONFIG, JUDGES, CODEX_MUTATOR, add_anchors, capped_criterion, env_of, install, kind, pyright, sandboxed, scripted_judge, world)

MODULE_EDIT = '''from pathlib import Path
p = Path('direct.orc')
s = p.read_text()
start = s.index('(provider-result providers.coder', s.index('(defworkflow run'))
stop = s.index(':timeout-sec 5400)', start) + len(':timeout-sec 5400)')
call = s[start:stop]
s = s[:start] + '(helper task repo)' + s[stop:]
helper = '(defproc helper ((task String) (repo String)) -> Change ' + call + ')\\n'
s = s.replace('  (defworkflow run', helper + '  (defworkflow run')
s = s.replace('(variant Outcome DONE :summary change.summary)',
              '(if true (variant Outcome DONE :summary change.summary) (variant Outcome BLOCKED :reason "unused"))')
p.write_text(s)
'''


def execute(world, criterion, *, continue_run=False):
    frozen = json.loads(capped_criterion(criterion).read_text())
    config = write(world.tmp / 'four-config.json', CONFIG | {'criterion_sha256': sha(criterion),
        'models': frozen['models'], 'per_call_timeout_sec': frozen['per_call_timeout_sec']})
    return three_arm.run_three_arm(config, parents={name: world.tmp / 'parents' / name for name in ('orc', 'python')},
        tasks=[world.task], work_root=world.outside / 'four-work', evidence_root=world.tmp / 'four-evidence',
        episodes_per_arm=1, agent_cmd=CODEX_MUTATOR, runtime=world.runtime, env=env_of(world), timeout_sec=14400,
        solutions={world.task.name: world.solution}, call_cap=250, concurrency=4, run_seed=7, subset_seed=3,
        criterion=criterion, continue_run=continue_run)


def test_refused_module_parent_stops_before_any_mutator_launch(sandboxed, world, pyright):
    install(world)
    criterion = module_criterion(world.tmp)
    frozen = json.loads(criterion.read_text())
    frozen.update(purpose='measure-free', tasks=[str(world.task)], models={'different-model': ['high']})
    write(criterion, frozen)
    with pytest.raises(ValueError, match='model_not_allowed'):
        execute(world, criterion)
    rows = read_records(world.tmp / 'four-evidence/log.jsonl')
    assert kind(rows, 'episode') == [] and kind(rows, 'evaluation') == []
    assert not (world.outside / 'four-work/episodes').exists()


def test_four_arms_share_parent_replicates_and_read_all_harness_joined_children(sandboxed, world, pyright):
    install(world)
    add_anchors(world.task)
    q = qualified(world.tmp / 'four-quality', runtime=world.runtime, tasks=[world.task], judges=JUDGES)
    frozen = json.loads(module_criterion(world.tmp).read_text()) | json.loads(q.criterion.read_text())
    frozen.update(quality_floor={'kind': 'above_stub'}, dominance_cost_tolerance=.1,
                  final_choice={'equivalence_tolerance': .5},
                  price_table={'currency': 'USD', 'tokens_per_unit': 1000000, 'source': 'synthetic frozen rates',
                               'date': '2026-10-19', 'models': {'gpt-6.1-sol': {
                                   'input': 1, 'output': 1, 'cache_read': 1, 'cache_write': 1}}})
    frozen['anchors'] = {world.task.name: {'stub': f'{world.task.name}-stub', 'upstream': f'{world.task.name}-upstream'}}
    frozen['subset'].update(replicates=2, per_arm=1)
    write(q.criterion, frozen)
    (world.fakebin / 'module.py').write_text(MODULE_EDIT)
    codex = world.fakebin / 'codex'
    codex.write_text(codex.read_text().replace('runpy.run_path(str(here / ("i2.py"',
        'runpy.run_path(str(here / ("module.py" if "condition module" in brief else "i2.py"'))
    execute(world, q.criterion)
    evidence = world.tmp / 'four-evidence'
    log = evidence / 'log.jsonl'
    rows = read_records(log)
    episodes, evaluations = kind(rows, 'episode'), kind(rows, 'evaluation')
    assert {row['arm'] for row in episodes} == {'I1', 'I2', 'I3', 'I1/module'}
    module = next(row for row in episodes if row['arm'] == 'I1/module')
    assert module['outcome'] == 'accepted', module
    parents = [row for row in evaluations if row.get('parent_for_arms')]
    assert len(parents) == 4  # two unique snapshots times two declared replicates
    assert {tuple(row['parent_for_arms']) for row in parents} == {('I1', 'I2', 'I1/module'), ('I3',)}
    assert max(Counter((row['candidate_id'], row['task_id'], row['replicate']) for row in evaluations).values()) == 1
    execute(world, q.criterion, continue_run=True)
    assert kind(read_records(log), 'evaluation') == evaluations
    pool = pool_evaluations(evidence, world.task, out=world.outside / 'four-pool', judges=JUDGES, criterion=q.criterion)
    judged = three_arm.judge(evidence, pool, world.task, criterion=q.criterion, judges=JUDGES,
        solution=world.solution, call_cap=250, scorer=scripted_judge(log))
    driver = json.loads((evidence / 'readout.json').read_text())
    driver['arms']['I1/module']['subset'] = []  # a later subset no longer chooses this evaluated child
    write(evidence / 'readout.json', driver)
    report = three_arm_readout.readout(log, evidence / 'readout.json', q.criterion, [Path(judged['results'])])
    task = report['tasks'][world.task.name]
    assert task['anchor_checks']['anchors_ok']
    assert list(task)[0] == 'anchors'
    assert module['candidate_id'] in task['arms']['I1/module']['children']
    child = task['arms']['I1/module']['children'][module['candidate_id']]
    assert child['values'] == [6, 6]
    assert child['realized_perform_sites'] != 'unavailable'
    assert report['pareto']['cost_axis'] == 'metered_USD'  # I3 allocation is unknown; no global calls proxy
    assert all(arm['frontier'] == [] for arm in report['pareto']['arms'].values())
    assert all(row['cost'] == 'unavailable' for row in report['pareto']['candidates'].values())
    assert len(report['pareto']['candidates']) == len({r['candidate_id'] for r in evaluations})
