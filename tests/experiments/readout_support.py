"""Qualified, temporary scoring provenance for historical readout mechanics fixtures."""
import json
from pathlib import Path

from tests.experiments.qualification_support import qualified, sha, write


def report_qualification(root, template, names=None):
    frozen = json.loads(Path(template).read_text()) if isinstance(template, Path) else dict(template)
    names = names or [Path(t).name for t in frozen['tasks']]
    tasks = []
    for name in names:
        task = root / 'tasks' / name
        (task / 'anchors').mkdir(parents=True)
        (task / 'task.txt').write_text('Synthetic repair')
        (task / 'base_commit').write_text('a' * 40)
        roles = frozen.get('anchors', {}).get(name, {'upstream': f'{name}-upstream', 'stub': f'{name}-stub'})
        for role, label in roles.items():
            (task / 'anchors' / f'{label}.diff').write_text(f'{role} synthetic control')
        tasks.append(task)
    q = qualified(root / 'qualification', tasks=tasks, judges=['j'])
    actual = json.loads(q.criterion.read_text())
    write(q.criterion, frozen | actual)
    return q


def report_pool(results, q, task):
    directory = results.parent.parent if results.parent.name == 'records' else results.parent
    actual_task = next(p for p in q.tasks if p.name == task)
    write(directory / 'records/mapping.json', {'runtime': str(q.runtime), 'task': str(actual_task),
        'criterion_sha256': sha(q.criterion), 'judges': {'j': {'providers': str(q.bindings)}}})
    write(directory / 'records/score-inputs-j.json', {'judge_model': 'j', 'criterion_sha256': sha(q.criterion)})
    return results
