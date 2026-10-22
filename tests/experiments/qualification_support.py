"""Temporary qualification evidence; no provider calls and no committed study criteria."""

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def ref(path):
    return {"file": str(path), "sha256": sha(path)}


def package_sha(task):
    lines = "".join(f"{sha(p)}  ./{p.relative_to(task).as_posix()}\n"
                    for p in sorted(task.rglob('*')) if p.is_file())
    return hashlib.sha256(lines.encode()).hexdigest()


def measure_free(root, *, template=None, tasks=()):
    value = json.loads(Path(template).read_text()) if template else {}
    value.update(purpose="measure-free", tasks=[str(t) for t in tasks])
    return write(root / "measure-free.json", value)


def qualified(root, *, runtime=None, tasks=None, judges=("gpt-6.1-sol",), providers=None):
    """Create two qualifying raw R55 samples and a calibrated blind anchor pool per task."""
    root.mkdir(parents=True, exist_ok=True)
    runtime = runtime or root / "runtime"
    if not (runtime / "experiments/compare/score.orc").exists():
        (runtime / "experiments/compare").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / "experiments/compare/score.orc", runtime / "experiments/compare/score.orc")
    bindings = runtime / "experiments/compare/score.providers.json"
    if not bindings.exists():
        write(bindings, {"providers.judge": "codex_unrestricted_workspace"})
    if tasks is None:
        task = root / "task"
        (task / "anchors").mkdir(parents=True)
        (task / "task.txt").write_text("Repair the task")
        (task / "base_commit").write_text("a" * 40)
        tasks = [task]
    family, measurements, pools = {}, {}, []
    for task in tasks:
        anchors = task / "anchors"
        anchors.mkdir(exist_ok=True)
        controls = {}
        for role in ("upstream", "stub"):
            anchor = anchors / f"{task.name}-{role}.diff"
            if not anchor.exists():
                alternatives = list(anchors.glob('*.diff'))
                selected = [p for p in alternatives if ('upstream' in p.stem) == (role == 'upstream')]
                if len(alternatives) == 2 and len(selected) == 1:
                    anchor = selected[0]
                else:
                    anchor.write_text(f"{role} patch")
            controls[role] = {"label": anchor.stem, "source": ref(anchor), "pooled_patch_sha256": sha(anchor)}
        digest, samples = package_sha(task), []
        for n in (1, 2):
            direct_dir = root / "private" / task.name / "direct_task" / f"run-{n}"
            review_dir = root / "private" / task.name / "review_once" / f"run-{n}"
            patch = direct_dir / "collected/final.diff"
            patch.parent.mkdir(parents=True)
            patch.write_text(f"patch {n}")
            common = {"task": str(task), "base": (task / "base_commit").read_text().strip(),
                      "compare_base": "b" * 40, "outcome": "completed", "calls": 1,
                      "scan": {"calls": 1, "hits": [], "verdict": None}}
            direct = write(direct_dir / "record.json", common | {
                "arm": "direct_task", "records": str(direct_dir), "patches": {"final": "collected/final.diff"}})
            inputs = write(direct_dir / "inputs.json", {"model": "gpt-6.1-sol", "effort": "high",
                                                       "task": (task / "task.txt").read_text()})
            review = write(review_dir / "record.json", common | {
                "arm": "review_once", "records": str(review_dir),
                "applied": {"path": str(patch), "sha256": sha(patch)},
                "review": {"variant": "REQUEST_CHANGES", "findings": ["one", "two"]}})
            samples.append({"direct_record": ref(direct), "direct_inputs": ref(inputs), "patch": ref(patch),
                            "review_record": ref(review)})
        source = write(root / "private" / task.name / "source.json", {"slug": task.name, "package_sha256": digest,
            "single_calls": [{"run": f"direct_task/run-{n}"} for n in (1, 2)]})
        family[task.name] = {"package_sha256": digest, "sources": [ref(source)], "samples": samples}
        measurements[task.name] = {"package_sha256": digest, "controls": controls}
    measurement = {"evaluator": {
        "score_workflow": ref(runtime / "experiments/compare/score.orc"),
        "judges": {name: {"effort": "high", "providers": ref((providers or {}).get(name, bindings))} for name in judges}},
        "tasks": measurements}
    calibration = write(root / "private/calibration/criterion.json", {
        "purpose": "calibration", "calibration_kind": "measure", "budget": {"call_cap": 20},
        "judges": list(judges), "calibration": {"margin": 2, "error_rate": 0}, "measurement": measurement})
    for task in tasks:
        pool = root / "private/calibration" / task.name
        clones = {role: {"arm": "anchor", "run": None, "labels": [measurements[task.name]["controls"][role]["label"]]}
                  for role in ("upstream", "stub")}
        mapping = write(pool / "records/mapping.json", {
            "task": str(task), "runtime": str(runtime), "criterion_sha256": sha(calibration), "runs": {},
            "judges": {name: {"dir": name, "providers": str((providers or {}).get(name, bindings))} for name in judges},
            "clones": clones, "batches": [["upstream", "stub"]]})
        for judge in judges:
            write(pool / 'records' / f'score-inputs-{judge}.json',
                  {'judge_model': judge, 'criterion_sha256': sha(calibration)})
        results = write(pool / "records/results.json", {
            "criterion_sha256": sha(calibration), "judges": list(judges), "excluded_judges": {},
            "clones": {cid: clone | {"ratings": {name: {key: 2 if cid == "upstream" else 0
                for key in ("root_cause", "scope", "generality", "layering")} for name in judges}}
                for cid, clone in clones.items()}})
        patches = {}
        for role in clones:
            path = pool / "records/patches" / f"{role}.diff"
            path.parent.mkdir(exist_ok=True)
            shutil.copyfile(Path(controls[role]["source"]["file"]) if len(tasks) == 1 else
                            Path(measurements[task.name]["controls"][role]["source"]["file"]), path)
            patches[role] = ref(path)
        pools.append({"task_id": task.name, "mapping": ref(mapping), "results": ref(results), "patches": patches})
    receipt = write(root / "private/qualification.json", {
        "schema": "orc-structural-qualification-v1",
        "family": {"kind": "review-blockers-r55", "rule": ref(REPO / "experiments/compare/criteria/calibration.json"),
                   "tasks": family}, "measure": {"criterion": ref(calibration), "pools": pools}})
    criterion = write(root / "criterion.json", {
        "purpose": "quality", "tasks": [str(t) for t in tasks], "judges": list(judges),
        "judge_bindings": {name: info["providers"]["file"]
                           for name, info in measurement["evaluator"]["judges"].items()},
        "calibration": {"margin": 2, "error_rate": 0}, "measurement": measurement, "qualification": ref(receipt)})
    return SimpleNamespace(criterion=criterion, receipt=receipt, calibration=calibration, runtime=runtime,
                           tasks=tasks, pools=pools, bindings=bindings, judges=list(judges))


def refresh(q):
    """Rehash edited referenced JSON files up to the study; changes remain subject to semantic validation."""
    receipt = json.loads(q.receipt.read_text())
    for task in receipt["family"]["tasks"].values():
        for source in task.get("sources", []):
            source.update(ref(Path(source["file"])))
        for sample in task.get("samples", []):
            for key, value in sample.items():
                if value is not None:
                    sample[key] = ref(Path(value["file"]))
    receipt["measure"]["criterion"] = ref(q.calibration)
    for pool in receipt["measure"]["pools"]:
        for key in ("mapping", "results"):
            pool[key] = ref(Path(pool[key]["file"]))
        mapping = json.loads(Path(pool['mapping']['file']).read_text())
        for judge in mapping['judges']:
            path = Path(pool['mapping']['file']).parent / f'score-inputs-{judge}.json'
            if path.exists():
                inputs = json.loads(path.read_text())
                inputs['criterion_sha256'] = mapping['criterion_sha256']
                write(path, inputs)
    write(q.receipt, receipt)
    study = json.loads(q.criterion.read_text())
    study["qualification"] = ref(q.receipt)
    write(q.criterion, study)


def module_criterion(root):
    template = REPO / 'experiments/orc_structural_search/criteria/three_arm.json'
    value = json.loads(template.read_text())
    value.update(models={'gpt-6.1-sol': ['high'], 'claude-opus-5-5': ['high']}, per_call_timeout_sec=5400,
                 arms={'I1': {'interface': 'I1', 'condition': 'topology-only', 'parent': 'orc'},
                       'I2': {'interface': 'I2', 'condition': 'topology-only', 'parent': 'orc'},
                       'I3': {'interface': 'I3', 'condition': 'topology-only', 'parent': 'python'},
                       'I1/module': {'interface': 'I1', 'condition': 'module', 'parent': 'orc'}})
    return write(root / 'module-criterion.json', value)


ABSOLUTE_RUBRIC = {'workflow': 'score_absolute.orc', 'entry': 'score_absolute::score',
                   'criteria': ['completeness', 'correctness', 'scope', 'layering'], 'reference': None}


def campaign_criterion(root, *, tasks, validation, sealed, judges=('gpt-5.6-terra',),
                       models=None, price_table=None, rubric=ABSOLUTE_RUBRIC, **overrides):
    """The complete prospective C1 shape, constructed only in temporary test roots."""
    value = {
        'purpose': 'quality', 'experiment': 'synthetic C1', 'plan': 'offline fixture',
        'tasks': list(map(str, tasks)), 'validation_task': str(validation), 'sealed_task': str(sealed),
        'base_commits': {p.name: (p / 'base_commit').read_text().strip() for p in [*tasks, validation, sealed]},
        'judges': list(judges), 'judge_bindings': {}, 'rubric': rubric,
        'accepted_measure': {}, 'anchors': {}, 'calibration': {'margin': 4, 'mutant_margin': 2, 'error_rate': 0},
        'anchor_spread_limit': 2, 'qualification': {}, 'family_amendments': {}, 'measurement': {},
        'price_table': price_table or {'currency': 'USD', 'tokens_per_unit': 1000000,
            'date': '2026-10-19', 'source': 'synthetic offline table',
            'models': {j: {'input': 2, 'output': 12, 'cache_read': .2, 'cache_write': 2.5} for j in judges}},
        'models': models or {'gpt-5.6-terra': ['medium', 'high']}, 'per_call_timeout_sec': 3600,
        'model_policy': {'allowed': list(judges), 'all_roles': True, 'fable': 'forbidden',
            'nested_claude': 'claude-sonnet-5-5' if 'claude-sonnet-5-5' in judges else 'forbidden', 'codex_native_agents': 'disabled', 'mutator': 'codex --model gpt-5.6-terra'},
        'envelope': {'episode': 3600, 'evaluation': 14400, 'per_call_timeout_sec': 3600,
            'concurrency': 4, 'child_planned_maximum': 4, 'wall_clock_ceiling_h': 30},
        'quality_floor': {'kind': 'above_stub'}, 'dominance_cost_tolerance': .10,
        'final_choice': {'equivalence_tolerance': .5, 'mean_cost': 'metered_USD',
            'mean_cost_ceiling_rule': '4 x c_ref, resolved after P0 and passed as a readout argument',
            'provider_calls': 'mean'},
        'support': {'rule': 'every_adaptive_task', 'task_weights': 'equal', 'min_trials': 1},
        'reference_seed': 'direct', 'archive': {'size': 6, 'spread_rule': 'cheapest_highest_largest_gaps',
            'scope': 'campaign'}, 'reservoir': {'capacity': 4, 'admission': 'valued_non_frontier', 'eviction': 'fifo'},
        'exploration_fraction': .25, 'policies': ['frontier_only', 'mixture'],
        'revisit_key': 'digest, or skeleton+policy',
        'revisit_match_set': 'already evaluated or scheduled in the current generation, in this campaign, initial evidence included',
        'futility': {'consecutive': 4, 'counts': ['revisit', 'rejected', 'exhausted'],
            'resets': ['fresh'], 'ignored': ['incident']},
        'horizon': {'generations': 4, 'episodes_per_generation': 4, 'adaptive_replicates': 1,
            'validation_replicates': 3, 'sealed_replicates': 3, 'finalists_per_campaign': 2,
            'warm_start': {'seeds': ['direct', 'implement_check_diagnose_repair'], 'replicates': 2,
                           'smoke': 'first evaluation'}},
        'checkpoints': 'after every ledger settlement and after every generation',
        'stop_rules': {'horizon': True, 'futility': True, 'call_cap': True, 'quota_exhaustion': True,
            'wall_clock_ceiling': True,
            'invalid_evidence': ['calibration', 'unadjudicated_contamination', 'malformed_ingest'],
            'judge_incidents': 2, 'persistent_infrastructure': 3},
        'exposure': 'recorded on actual use; roles checked against prior actual exposures',
        'endpoints': {'cost_ceilings': [1, 2, 4], 'quality_targets': [.5, 1., 2.],
            'budget_cuts': [.5, .75, 1.], 'B_plan_usd': 25., 'calls_cuts': [39, 58, 77]},
        'power': {'formula': 'delta = (z_(1-alpha/2) + z_(1-beta)) * sigma_c * sqrt(2 / R)',
            'assumptions': 'alpha=.05, power=.80; search variance unknown; campaign SD bracket includes measurement noise',
            'delta': 1., 'R': 1, 'bracket': [.64, 1.27], 'statement': 'descriptive pilot; no policy claim'},
        'budget': {'steps': {step: {'planned': 4, 'cap': 8} for step in ('P0', 'P1', 'P2', 'P3', 'P4')},
            'cap_rule': 'settled calls + next batch planned maximum + one relaunch of largest unit; stop before cap'},
        'campaigns': [{'label': 'c1-frontier', 'policy': 'frontier_only', 'run_seed': 1},
                      {'label': 'c1-mixture', 'policy': 'mixture', 'run_seed': 1}],
        'context': {'evaluator_version': 'synthetic-v2'},
        'convergence_diagnostic': 'share per idea_key, per campaign', 'collapse_threshold': .75,
        'not_tested': ['policy claim'], 'written_before_scoring': True}
    value.update(overrides)
    return write(root / 'criterion.json', value)




def _v2_runtime(runtime, rubric, judges):
    import subprocess
    compare = runtime / 'experiments/compare'
    compare.mkdir(parents=True, exist_ok=True)
    workflow = compare / rubric['workflow']
    if not workflow.exists():
        shutil.copyfile(REPO / 'experiments/compare' / rubric['workflow'], workflow)
    binding = write(compare / 'score.providers.json', {'providers.judge': 'codex_unrestricted_workspace'})
    binding_paths = {j: binding if j == 'gpt-5.6-terra' else write(compare / f'{j}.providers.json',
        {'providers.judge': 'claude_unrestricted_workspace'}) for j in judges}
    control = compare / 'control'
    control.mkdir(exist_ok=True)
    for arm in ('direct_task', 'review_once'):
        for name in (f'{arm}.orc', f'{arm}.providers.json'):
            shutil.copyfile(REPO / 'experiments/compare/control' / name, control / name)
    subprocess.run(['git', 'init', '-q', str(runtime)], check=True)
    subprocess.run(['git', '-C', str(runtime), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(runtime), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                    'commit', '-qm', 'synthetic runtime'], check=True)
    commit = subprocess.check_output(['git', '-C', str(runtime), 'rev-parse', 'HEAD'], text=True).strip()
    return workflow, binding, binding_paths, control, commit


def _v2_tasks(root, tasks, validation, sealed, roles=('upstream', 'stub', 'partial', 'mutant')):
    def task(name):
        path = root / 'tasks' / name
        (path / 'anchors').mkdir(parents=True)
        (path / 'task.txt').write_text('Synthetic task ' + name)
        (path / 'intent.txt').write_text('Synthetic intent ' + name)
        (path / 'base_commit').write_text('a' * 40)
        return path

    tasks = tasks or [task('adaptive')]
    validation, sealed = validation or task('validation'), sealed or task('sealed')
    all_tasks = [*tasks, validation, sealed]
    measurements, anchors = {}, {}
    for path in all_tasks:
        (path / 'anchors').mkdir(exist_ok=True)
        controls = {}
        for role in roles:
            patch = path / 'anchors' / f'{path.name}-{role}.diff'
            if not patch.exists():
                patch.write_text(f'{path.name} {role} patch')
            controls[role] = {'label': patch.stem, 'source': ref(patch), 'pooled_patch_sha256': sha(patch)}
        anchors[path.name] = {role: info['label'] for role, info in controls.items()}
        measurements[path.name] = {'package_sha256': package_sha(path), 'controls': controls}
    return tasks, validation, sealed, all_tasks, measurements, anchors


def _v2_family(root, runtime, control, tasks, validation, sealed, all_tasks, commit):
    rules = {}
    for amendment, paths in [('amends_5', tasks), ('amends_6', [validation, sealed])]:
        rules[amendment] = write(root / f'private/rules/{amendment}.json', {
            'runtime': {'path': str(runtime), 'commit': commit, 'validity': 'exact implementation commit and package hashes'},
            'written_before_scoring': True, 'purpose': 'family-calibration',
            amendment: {'reviewer': 'gpt-5.6-terra', 'implementation_commit': commit,
                        'packages': {p.name: package_sha(p) for p in paths}},
            'single_call': {'model': 'gpt-5.6-terra', 'effort': 'high'},
            'review': {'reviewer': 'gpt-5.6-terra, high, timeout 5400; codex_unrestricted_workspace',
                       'workflow_sha256': sha(control / 'review_once.orc')},
            'k': 2, 'borderline': 'if 1 <= mean < 1.5, one third pair',
            'qualifies': 'mean review blockers >= 1',
            'packages': {p.name: {'package_sha256': package_sha(p), 'path': str(p)} for p in paths}})
    family = {}
    for path in all_tasks:
        samples = []
        for n in (1, 2):
            direct = root / 'private/family' / path.name / 'direct_task' / f'run-{n}'
            review = direct.parent.parent / 'review_once' / f'run-{n}'
            patch = direct / 'collected/final.diff'
            patch.parent.mkdir(parents=True)
            patch.write_text(f'{path.name} candidate {n}')
            common = {'task': str(path), 'base': (path / 'base_commit').read_text().strip(), 'compare_base': 'b' * 40,
                'runtime': str(runtime), 'runtime_commit': commit, 'outcome': 'completed', 'calls': 1,
                'scan': {'calls': 1, 'hits': [], 'verdict': None}}
            direct_record = write(direct / 'record.json', common | {'arm': 'direct_task', 'records': str(direct),
                'patches': {'final': 'collected/final.diff'},
                'command': f'python -m orchestrator run {control / "direct_task.orc"} --provider-externs-file {control / "direct_task.providers.json"} --input-file {direct / "inputs.json"}'})
            inputs = write(direct / 'inputs.json', {'model': 'gpt-5.6-terra', 'effort': 'high',
                'task': (path / 'task.txt').read_text()})
            reviewer = write(review / 'inputs.json', {'repo': str(root / 'private/candidates' / path.name / str(n)),
                'intent': (path / 'intent.txt').read_text(), 'account': 'No account was provided.', 'replies': 'none'})
            review_record = write(review / 'record.json', common | {'arm': 'review_once', 'records': str(review),
                'applied': {'path': str(patch), 'sha256': sha(patch)},
                'cwd': str(root / 'private/candidates' / path.name / str(n)),
                'command': f'python -m orchestrator run {control / "review_once.orc"} --provider-externs-file {control / "review_once.providers.json"} --input-file {review / "inputs.json"}',
                'review': {'variant': 'REQUEST_CHANGES', 'findings': ['one', 'two']}})
            samples.append({'direct_record': ref(direct_record), 'direct_inputs': ref(inputs), 'patch': ref(patch),
                            'review_record': ref(review_record), 'review_inputs': ref(reviewer)})
        source = write(root / 'private/family' / path.name / 'source.json', {'slug': path.name,
            'package_sha256': package_sha(path), 'single_calls': [{'run': f'direct_task/run-{n}'} for n in (1, 2)]})
        family[path.name] = {'package_sha256': package_sha(path), 'sources': [ref(source)], 'samples': samples}
    return rules, family


def _v2_measurement(rubric, judges, binding_paths, measurements, all_tasks, runtime, commit,
                    anchors, overrides, workflow):
    bindings = {j: {'providers': str(binding_paths[j]), 'providers_sha256': sha(binding_paths[j]),
                    'effort': 'high', 'timeout_sec': 3600} for j in judges}
    measurement = {'evaluator': {'score_workflow': ref(workflow),
        'judges': {j: {'effort': 'high', 'providers': ref(binding_paths[j])} for j in judges}}, 'tasks': measurements}
    price_table = overrides.get('price_table') or {'currency': 'USD', 'tokens_per_unit': 1000000,
        'date': '2026-10-19', 'source': 'synthetic offline table',
        'models': {j: {'input': 2, 'output': 12, 'cache_read': .2, 'cache_write': 2.5} for j in judges}}
    origin_common = {'price_table': price_table, 'runtime': {'path': str(runtime), 'commit': commit}, 'purpose': 'calibration',
        'tasks': list(map(str, all_tasks)), 'judges': list(judges), 'judge_bindings': bindings,
        'rubric': rubric, 'workflow_sha256': sha(workflow), 'anchors': anchors,
        'calibration': overrides.get('calibration', {'margin': 4, 'mutant_margin': 2, 'error_rate': 0}),
        'anchor_spread_limit': 2,
        'batches': {'A2': {'count': 2}, 'A': {'count': 2}, 'B2': {'count': 1},
                    'Q1': {'count': 2}, 'Q2': {'count': 2}}}
    return bindings, measurement, origin_common


def _v2_pool_batch(pool, path, batch, anchors, rubric):
    clones, ids, patches = {}, [], {}
    for role, label in anchors[path.name].items():
        cid = f'{batch}-{role}'
        clones[cid] = {'arm': 'anchor', 'run': None, 'labels': [label]}
        ids.append(cid)
        copied = pool / 'records/patches' / f'{cid}.diff'
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path / 'anchors' / f'{label}.diff', copied)
        patches[cid] = ref(copied)
    if rubric['reference']:
        cid = f'{batch}-reference'
        clones[cid] = {'arm': 'reference', 'run': None, 'labels': ['reference']}
        copied = pool / 'records/patches' / f'{cid}.diff'
        shutil.copyfile(path / 'anchors' / f'{anchors[path.name]["upstream"]}.diff', copied)
        patches[cid] = ref(copied)
    return clones, ids, patches


def _v2_pool(root, path, stage, anchors, rubric, judges, binding_paths, calibration, runtime, commit):
    pool = root / 'private/calibration' / path.name / stage
    clones, batches, patches = {}, [], {}
    for batch in range(1 if stage == 'B2' else 2):
        batch_clones, ids, batch_patches = _v2_pool_batch(pool, path, batch, anchors, rubric)
        clones.update(batch_clones)
        batches.append(ids)
        patches.update(batch_patches)
    mapping = {'task': str(path), 'runtime': str(runtime), 'runtime_commit': commit,
        'criterion_sha256': sha(calibration), 'rubric': rubric, 'runs': {},
        'judges': {j: {'providers': str(binding_paths[j])} for j in judges}, 'clones': clones, 'batches': batches,
        'references': [cid for cid in clones if cid.endswith('reference')]}
    mapping_path = write(pool / 'records/mapping.json', mapping)
    for judge in judges:
        write(pool / 'records' / f'score-inputs-{judge}.json', {'judge_model': judge,
            'criterion_sha256': sha(calibration)})
    totals = {'upstream': 8, 'stub': 0, 'partial': 4, 'mutant': 4}
    results = write(pool / 'records/results.json', {'task': str(path), 'criterion_sha256': sha(calibration),
        'judges': list(judges), 'excluded_judges': {}, 'calibration': {'passed': True},
        'clones': {cid: info | {'ratings': {} if info['arm'] == 'reference' else {j: {
            key: min(2, max(0, totals[cid.split('-', 1)[1]] - i * 2))
            for i, key in enumerate(rubric['criteria'])} for j in judges}}
            for cid, info in clones.items()}})
    return {'task_id': path.name, 'stage': stage, 'criterion': ref(calibration),
        'mapping': ref(mapping_path), 'results': ref(results), 'patches': patches}


def _v2_pools(root, all_tasks, tasks, sealed, accepted_step, anchors, rubric, judges, binding_paths,
              calibration, runtime, commit):
    pools = []
    for path in all_tasks:
        stages = [accepted_step, 'B2'] if path in tasks else ['Q1' if path == sealed else 'Q2']
        for stage in stages:
            pools.append(_v2_pool(root, path, stage, anchors, rubric, judges, binding_paths,
                                  calibration, runtime, commit))
    return pools


def qualified_v2(root, *, runtime=None, tasks=None, validation=None, sealed=None,
                 judges=('gpt-5.6-terra',), rubric=ABSOLUTE_RUBRIC, accepted_step='A_prime', **overrides):
    """Four-role synthetic raw evidence, origin rules and stage-complete pools; zero providers."""
    root.mkdir(parents=True, exist_ok=True)
    runtime = runtime or root / 'runtime'
    workflow, binding, binding_paths, control, commit = _v2_runtime(runtime, rubric, judges)
    roles = ('upstream', 'stub', 'mutant') if overrides.get('calibration', {}).get('rule') == 'control-means-v1' else ('upstream', 'stub', 'partial', 'mutant')
    tasks, validation, sealed, all_tasks, measurements, anchors = _v2_tasks(root, tasks, validation, sealed, roles)
    rules, family = _v2_family(root, runtime, control, tasks, validation, sealed, all_tasks, commit)
    bindings, measurement, origin_common = _v2_measurement(
        rubric, judges, binding_paths, measurements, all_tasks, runtime, commit, anchors, overrides, workflow)
    calibration = write(root / 'private/calibration/criterion.json', origin_common)
    pools = _v2_pools(root, all_tasks, tasks, sealed, accepted_step, anchors, rubric,
                       judges, binding_paths, calibration, runtime, commit)
    receipt = write(root / 'private/qualification.json', {'schema': 'orc-structural-qualification-v2',
        'family': {'kind': 'review-blockers-r55', 'rules': {package_sha(p): ref(rules[
            'amends_5' if p in tasks else 'amends_6']) for p in all_tasks}, 'tasks': family},
        'measure': {'criterion': ref(calibration), 'pools': pools}})
    criterion = campaign_criterion(root, tasks=tasks, validation=validation, sealed=sealed, judges=judges,
        rubric=rubric, judge_bindings=bindings, anchors=anchors, measurement=measurement,
        family_amendments={k: ref(v) for k, v in rules.items()}, qualification=ref(receipt),
        accepted_measure={'step': accepted_step, 'criterion': ref(calibration), 'approval': 'synthetic ledger'}, **overrides)
    return SimpleNamespace(criterion=criterion, receipt=receipt, calibration=calibration, runtime=runtime,
        tasks=tasks, validation=validation, sealed=sealed, pools=pools, bindings=binding, judges=list(judges))
