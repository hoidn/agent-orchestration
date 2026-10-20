"""Offline-qualified cumulative whole-program campaigns; historical mode 2 is read-only."""
import json
import random
import threading
import time
from pathlib import Path

from experiments.compare import repos, summarize
from experiments.compare.pool import rubric
from experiments.orc_structural_search import campaign, driver, judging, ledger, mode1, qualification, scoring
from experiments.orc_structural_search.briefs import structural_summary
from experiments.orc_structural_search.call_identity import require_campaign_scan, campaign_proxy_comparable
from experiments.orc_structural_search.config import load_config
from experiments.orc_structural_search.evaluation import EVALUATOR_VERSION
from experiments.orc_structural_search.qualification import check_warm_inputs, check_campaign, check_run_parameters
from experiments.orc_structural_search.qualification_io import package_digest
from experiments.orc_structural_search.quota import quota_reason, with_retries, campaign_guard, campaign_elapsed
from experiments.orc_structural_search.three_arm_gate import QuotaExhausted, CapGate
from experiments.orc_structural_search.three_arm import episode_indexes
from experiments.orc_structural_search.records import UNAVAILABLE, append_record, find_campaign, read_records, tuples, prepare_log, replay_judge_incidents
from experiments.orc_structural_search.scoring_phase2 import (
    rank, make_entry, initial_archive, incumbent, dominates, frontier, prune, retain, select_parent,
    terminal, feedback, lineage_config, write_archive, mode2_readout, validate_finalists,
    check_splits, check_pools_root, run_mode2)

from experiments.orc_structural_search.judging import evaluate_and_judge
from experiments.orc_structural_search.ledger import check_budget, planned_judged

ADAPTIVE, PRIOR, ARCHIVE_SIZE = 'adaptive', 'phase1-prior', 6
EVALUATION_KEYS = ('work_root', 'evidence_root', 'runtime', 'env', 'timeout_sec', 'solutions', 'call_cap')


def read_log(path):
    return read_records(path) if path.exists() else []



def subject_config(subject, config):
    """Capped seeds and their children retain their one entry source module."""
    root = Path(subject['source']) / config.source_root
    module = next(path for path in root.glob('*.orc') if path.stem != 'common')
    return mode1.seed_config(module, config)


def register(store, root, config, runtime, campaign_id, parent=None):
    from experiments.orc_structural_search.acceptance import require_candidate
    shape = structural_summary(root, config, runtime=runtime)
    compiled = require_candidate(root, config, runtime=runtime)
    cid = campaign.register_subject(store, root, runtime=runtime, parent=parent, skeleton=driver.skeleton(root, config),
        policies=frozenset(tuple(p) for p in shape['policy_set']), idea_key=shape['idea_key'],
        descriptor={'realized_provider_calls': UNAVAILABLE, 'distinct_provider_roles': UNAVAILABLE},
        structure=shape, program_digest=compiled.program_digest, campaign_id=campaign_id)
    return next(row for row in store.rows('subject') if (row['candidate_id'], row['campaign_id']) == (cid, campaign_id))


def context(frozen, tasks, runtime):
    return campaign.context_key(frozen, package_digests={t.name: package_digest(t) for t in tasks},
        runtime_commit=repos.runtime_commit(runtime), evaluator_version=EVALUATOR_VERSION)


def roots_of(launch):
    return {'work': launch['work_root'], 'evidence': launch['evidence_root'], 'pools': launch['pools_root']}


def pool_paths(evidence_root, *, finished=True):
    kinds = ('judging',) if finished else ('judging', 'judge_pool')
    return list(dict.fromkeys(Path(row['pool']) for row in read_log(evidence_root / 'log.jsonl') if row['kind'] in kinds))


def pool_values(roots, criterion):
    return [scoring.read_pool(pool / 'records/results.json', evidence / 'log.jsonl', criterion)
            for evidence in roots for pool in pool_paths(evidence)]


def warm_start(store, criterion, config_path, *, seeds, adaptive_tasks, launch, judge):
    frozen = check_campaign(config_path, criterion, agent_cmd=launch['agent_cmd'], timeout_sec=launch['timeout_sec'],
                            policy='frontier_only', runtime=launch['runtime'])
    ctx = context(frozen, adaptive_tasks, launch['runtime'])
    check_warm_inputs(frozen, seeds, adaptive_tasks, launch)
    existing = campaign.warm_start_id(store, ctx)
    launch = dict(launch)
    launch['work_root'], launch['evidence_root'] = driver.check_roots(launch['work_root'], launch['evidence_root'])
    check_pools_root(launch['pools_root'], launch['work_root'], launch['evidence_root'])
    campaign.check_roots(store.root, roots_of(launch).values())
    prepare_log(launch['evidence_root'], bool(existing))
    declared = {package_digest(t): 'adaptive' for t in adaptive_tasks}
    params = parameters(config_path, frozen, seeds=seeds, run_seed=0, call_cap=launch['call_cap'],
                        concurrency=launch['concurrency'], runtime=launch['runtime'], judges=judge['judges'], roots=roots_of(launch))
    if existing:
        cid, state = existing, campaign.read_checkpoint(store, existing) or {}
        if (launch.get('resume'), find_campaign(store, existing)['parameters'], state.get('generation'), state.get('stopped')) != (True, params, 0, None):
            raise ValueError('warm resume requires the same incomplete frozen acquisition')
    else:
        cid = campaign.start_campaign(store, label='warm', context=ctx, policy=campaign.WARM_START,
            parameters=params, budget={'call_cap': launch['call_cap']}, seeds=[p.stem for p in seeds],
            run_seed=0, warm_start=[], declared_roles=declared, roots=roots_of(launch))
        state = {'generation': 0, 'frontier': [], 'reservoir': [], 'rng_state': None, 'ingestion_position': 0,
                 'ledger_index': 0, 'futility_streak': 0, 'budget': {}, 'stopped': None, 'started_at': time.time()}
    launch['pools_root'].mkdir(parents=True, exist_ok=True)
    launch.update(resume=True, scan_roots=[launch['pools_root'], *masked_roots(store, cid, launch.get('hide', ()))], judge_env={**launch['env'],
        'COMPARE_CLAUDE_MODELS': 'gpt-5.6-terra', 'ORC_ALLOWED_CLAUDE_MODELS': 'gpt-5.6-terra'})
    settled = install_gate(store, cid, state, frozen, criterion, launch, random.Random(0))
    jobs = mode1.catalog_jobs(seeds, load_config(config_path), launch['evidence_root'], launch['runtime'])
    for root, config, fields in jobs:
        register(store, root, config, launch['runtime'], cid)
        fields.update(campaign_id=cid, generation=0, split=ADAPTIVE)
    settled()
    try:
        evaluate_and_judge(jobs, 0, adaptive_tasks, replicates=frozen['horizon']['warm_start']['replicates'], launch=launch, judge=judge)
        settled()
        if not calibrate_generation(store, cid, 0, state, frozen, pool_values([launch['evidence_root']], criterion)):
            raise ValueError('warm acquisition has invalid evidence')
    except (ledger.CallCapExceeded, QuotaExhausted, ValueError) as error:
        state['stopped'] = 'call_cap' if isinstance(error, ledger.CallCapExceeded) else 'quota_exhaustion' if isinstance(error, QuotaExhausted) else 'invalid_evidence'
        campaign.write_checkpoint(store, cid, state)
        raise
    state['stopped'] = 'complete'
    campaign.write_checkpoint(store, cid, state)
    return {'campaign_id': cid, 'context_key': ctx}


def scan_work(evidence, frozen):
    rows = read_log(evidence / 'log.jsonl')
    for row in rows:
        if row['kind'] in ('episode', 'evaluation'):
            require_campaign_scan(row, frozen['model_policy']['allowed'])
    for pool in pool_paths(evidence):
        mapping = json.loads((pool / 'records/mapping.json').read_text())
        for name in mapping['judges']:
            path = pool / 'records/judges' / name / 'record.json'
            require_campaign_scan(json.loads(path.read_text()), frozen['model_policy']['allowed'])


def settle(store, cid, state, frozen, criterion, launch, rng):
    evidence = launch['evidence_root']
    state.update(rng_state=rng.getstate(),
                 ledger_index=len(ledger._read(evidence / ledger.LEDGER)),
                 budget=campaign.budget_union(read_log(evidence / 'log.jsonl'), pool_paths(evidence, finished=False), frozen['price_table']))
    try:
        scan_work(evidence, frozen)
        pools = [{'results': str(p / 'records/results.json')} for p in pool_paths(evidence)]
        if not calibrate_generation(store, cid, state['generation'], state, frozen, pools):
            raise ValueError('generation calibration failed before assessment ingestion')
        result = campaign.ingest(store, cid, find_campaign(store, cid)['context_key'], evidence,
            [p / 'records/results.json' for p in pool_paths(evidence)], criterion=criterion)
        state['ingestion_position'] = result['position']
    finally:
        rows = read_log(evidence / 'log.jsonl')
        snapshot = {key: state.get(key) for key in ('generation', 'completed_generation', 'frontier', 'reservoir', 'table', 'budget')}
        state.setdefault('trajectory', []).append(snapshot | {'log_position': len(rows),
            'convergence': campaign.convergence(store, cid), 'calls_proxy_comparable': campaign_proxy_comparable(
                rows, pool_paths(evidence, finished=False), frozen['models'])})
        campaign.write_checkpoint(store, cid, state)


def generation_jobs(state, config):
    return [(Path(s['source']), subject_config(s, config), {'mode': 'campaign', 'split': ADAPTIVE,
        'campaign_id': state['campaign_id'], 'generation': state['generation'], 'candidate_id': s['candidate_id'],
        'candidate_root': s['source'], 'parent_candidate_id': s['parent'], 'episode_id': s['episode_id']})
        for s in state.get('scheduled', [])]


def install_gate(store, cid, state, frozen, criterion, launch, rng):
    lock = threading.RLock()
    def settled():
        with lock, driver._LOG_LOCK:
            settle(store, cid, state, frozen, criterion, launch, rng)
    guard = campaign_guard(state, settled, lock)
    cap = CapGate(guard)
    def gate(launch_one):
        try:
            return cap.run(launch_one)
        finally:
            settled()
    launch.update(gate=gate, guard=guard, cap_gate=cap, settled=settled)
    return settled


def evaluate_pending(jobs, tasks, launch):
    pending = mode1.continued(jobs, tasks, 1, read_log(launch['evidence_root'] / 'log.jsonl'))
    driver.launch_units(pending, concurrency=launch['concurrency'], gate=launch['gate'], guard=launch['guard'],
        holdouts=launch['holdouts'], criterion=launch['criterion'], scan_roots=launch['scan_roots'],
        **{key: launch[key] for key in EVALUATION_KEYS})
    if launch['cap_gate'].exhausted:
        raise QuotaExhausted(launch['cap_gate'].exhausted)


def decision(store, cid, state, config, frozen, launch, rng, draw):
    log = launch['evidence_root'] / 'log.jsonl'
    prior = [r for r in read_log(log) if r['kind'] == 'parent_decision'
             and (r['generation'], r['draw']) == (state['generation'], draw)]
    if prior:
        chosen = prior[-1]
        rng.setstate(tuples(chosen['rng_state']))
        return chosen
    # Persist the consumed draw before any paid work can start.
    parent, source = campaign.select_parent(find_campaign(store, cid)['policy'], draw=draw,
        episodes=frozen['horizon']['episodes_per_generation'], fraction=frozen['exploration_fraction'],
        frontier=state['frontier'], reservoir=state['reservoir'], rng=rng)
    chosen = {'kind': 'parent_decision', 'generation': state['generation'], 'draw': draw,
        'parent_candidate_id': parent, 'parent_source': source, 'rng_state': rng.getstate(), 'created_at': time.time(),
        'episode_index': next(episode_indexes(
            [r for r in read_log(log) if r['kind'] == 'episode'], launch['work_root']))}
    append_record(log, chosen)
    return chosen


def campaign_episode(draw, state, config, *, store, campaign_id, criterion, rng, launch):
    log, frozen = launch['evidence_root'] / 'log.jsonl', launch['frozen']
    chosen = decision(store, campaign_id, state, config, frozen, launch, rng, draw)
    previous = [r for r in read_log(log) if r.get('campaign_decision') and
                (r['generation'], r['draw']) == (state['generation'], draw)]
    if previous:
        if previous[-1]['kind'] == 'fresh' and previous[-1]['subject'] not in state['scheduled']:
            state['scheduled'].append(previous[-1]['subject'])
        return previous[-1]
    launch['settled']()
    subject = campaign.campaign_candidates(store, campaign_id)[chosen['parent_candidate_id']]
    lineage = subject_config(subject, config)
    before = [r for r in read_log(log) if r['kind'] == 'episode' and
              (r['generation'], r.get('draw'), r['episode_index']) == (state['generation'], draw, chosen['episode_index'])]
    row = before[-1] if before and not quota_reason(before[-1]) else launch_episode(subject, lineage, chosen, draw, state, store, campaign_id, criterion, launch)
    launch['settled']()
    outcome, detail = classify_child(row, state, store, campaign_id, lineage, launch)
    resolved = {'kind': outcome, 'campaign_decision': True, 'generation': state['generation'], 'draw': draw,
                'episode_id': row['episode_id'], 'candidate_id': row['candidate_id'], **detail}
    append_record(log, resolved)
    return resolved


def launch_episode(subject, config, chosen, draw, state, store, cid, criterion, launch):
    index = chosen['episode_index']
    prior = [r for r in read_log(launch['evidence_root'] / 'log.jsonl') if r['kind'] == 'episode' and r['episode_index'] == index]
    key = driver.episode_key(subject['candidate_id'], config, 'I1', index, state['generation'], run_seed=launch['run_seed'])
    slot = ledger.episode_reservation(launch['evidence_root'], key)
    if slot and not prior:
        return killed_episode(subject, chosen, state, launch, slot)
    if not prior and (launch['work_root'] / 'episodes' / f'episode-{index}').exists():
        raise ValueError('episode workspace without its reservation')
    own = campaign.evidence(store, subject['candidate_id'], find_campaign(store, cid)['context_key'],
        tasks=launch['frozen']['tasks'], price_table=launch['frozen']['price_table'], min_trials=1)
    def run(attempt):
        if (launch['work_root'] / 'episodes' / f"episode-{chosen['episode_index']}").exists():
            chosen.update(episode_index=next(episode_indexes([r for r in read_log(launch['evidence_root'] / 'log.jsonl')
                if r['kind'] == 'episode'], launch['work_root'])), created_at=time.time())
            append_record(launch['evidence_root'] / 'log.jsonl', chosen)
            launch['settled']()
        row = driver.run_episode(Path(subject['source']), config, interface='I1', mode='campaign',
            agent_cmd=launch['agent_cmd'], episode_index=chosen['episode_index'], holdouts=launch['holdouts'], hide=launch['hide'],
            generation=state['generation'], run_seed=launch['run_seed'], criterion=criterion,
            fields={'campaign_id': cid, 'policy': find_campaign(store, cid)['policy'],
                    'parent_source': chosen['parent_source'], 'draw': draw, 'attempt': attempt},
            feedback={'mean_value': own.get('tasks', {}), 'evaluated_structures': campaign.evaluated_structures(
                store, cid, scheduled=state.get('scheduled', []))},
            **{key: launch[key] for key in EVALUATION_KEYS if key != 'timeout_sec'})
        launch['settled']()
        return row
    return with_retries(run, launch['guard'], prior[-1].get('attempt', 1) + 1 if prior else 1)


def classify_child(row, state, store, cid, config, launch):
    if quota_reason(row, launch['evidence_root']):
        raise QuotaExhausted('campaign episode quota exhausted')
    if row['outcome'] != 'accepted':
        return row['outcome'], {}
    root = Path(row['candidate_root'])
    if ledger.planned_calls(root, config, runtime=launch['runtime']) > launch['frozen']['envelope']['child_planned_maximum']:
        return 'rejected', {'reason': 'planned_maximum_exceeded'}
    shape = structural_summary(root, config, runtime=launch['runtime'])
    known, digests = campaign.known_structures(store, cid, scheduled=state.get('scheduled', []))
    if campaign.is_revisit(row['skeleton'], row['program_digest'], frozenset(tuple(p) for p in shape['policy_set']),
                           known=known, known_digests=digests):
        return 'revisit', {'matched': row['skeleton']}
    subject = register(store, root, config, launch['runtime'], cid, row['parent_candidate_id'])
    subject = subject | {'episode_id': row['episode_id']}
    state.setdefault('scheduled', []).append(subject)
    return 'fresh', {'subject': subject}


def killed_episode(subject, chosen, state, launch, slot):
    """A paid, unlogged launch consumes its original draw and is never repeated."""
    evidence, index = launch['evidence_root'], chosen['episode_index']
    records, tree = evidence / 'episodes' / slot['key'], launch['work_root'] / 'episodes' / f'episode-{index}'
    driver.scan_episode(records, tree, runtime=launch['runtime'], work_root=launch['work_root'],
        evidence_root=evidence, solutions=launch['solutions'], holdouts=launch['holdouts'],
        created_at=chosen['created_at'], hide=launch['hide'])
    from experiments.orc_structural_search import metering
    row = {'kind': 'episode', 'outcome': 'incident', 'mode': 'campaign', 'interface': 'I1', 'generation': state['generation'],
        'draw': chosen['draw'], 'episode_index': index, 'episode_id': slot['key'], 'candidate_id': subject['candidate_id'],
        'parent_candidate_id': subject['candidate_id'], 'parent_source': chosen['parent_source'], 'campaign_id': state['campaign_id'],
        'records_dir': str(records), 'provider_calls': slot['calls'], 'wall_clock_sec': time.time() - chosen['created_at'],
        'incidents': ['interrupted unlogged episode'], 'criterion_sha256': launch['frozen']['criterion_sha256'],
        **metering.receipts(records, tree=tree, since=chosen['created_at'], home=Path.home())}
    append_record(evidence / 'log.jsonl', row)
    return row


def campaign_generation(n, state, config, *, store, campaign_id, criterion, rng, adaptive_tasks, launch, judge):
    frozen = launch['frozen']
    state.update(generation=n)
    count = frozen['horizon']['episodes_per_generation']
    if not any(r['kind'] == 'parent_decision' and r['generation'] == n for r in read_log(launch['evidence_root'] / 'log.jsonl')):
        planned = count + planned_judged([frozen['envelope']['child_planned_maximum']] * count,
            len(adaptive_tasks), 1, len(judge['judges']), capacities=[scoring.fillers_per_batch(t, rubric(criterion)) for t in adaptive_tasks])
        check_budget(launch['evidence_root'], planned, launch['call_cap'], f'generation {n}')
    for draw in range(count):
        resolved = campaign_episode(draw, state, config, store=store, campaign_id=campaign_id,
            criterion=criterion, rng=rng, launch=launch)
        record_resolution(state, resolved, n, draw)
        launch['settled']()
        if state.get('infrastructure_streak', 0) >= frozen['stop_rules']['persistent_infrastructure']:
            state['stopped'] = 'persistent_infrastructure'
            return state
        if resolved['kind'] == 'fresh':
            evaluate_pending(generation_jobs(state, config), adaptive_tasks, launch)
            mark_evaluated(state, n, draw)
            launch['settled']()
        if campaign.futility(state['outcomes'], consecutive=frozen['futility']['consecutive']):
            state['stopped'] = 'futility'
            break
    evaluate_and_judge(generation_jobs(state, config), n, adaptive_tasks, replicates=1, launch=launch, judge=judge)
    launch['settled']()
    pools = pool_values([launch['evidence_root']], criterion)
    if not calibrate_generation(store, campaign_id, n, state, frozen, pools):
        launch['settled']()
        return state
    warm = find_campaign(store, campaign.warm_start_id(store, find_campaign(store, campaign_id)['context_key']))
    values = pool_values([Path(warm['roots']['evidence']), launch['evidence_root']], criterion)
    state.update(campaign.rebuild(store, campaign_id, criterion=frozen, pools=values, generation=n, previous=state))
    state['completed_generation'], state['scheduled'] = n, []
    launch['settled']()
    return state


def record_resolution(state, resolved, generation, draw):
    if [generation, draw] not in state['resolved']:
        state['resolved'].append([generation, draw])
        state['outcomes'].append('incident' if resolved['kind'] == 'fresh' else resolved['kind'])
        state['infrastructure_streak'] = state.get('infrastructure_streak', 0) + 1 if resolved['kind'] == 'incident' else 0
        state['futility_streak'] += int(resolved['kind'] in ('revisit', 'rejected', 'exhausted'))


def calibrate_generation(store, cid, generation, state, frozen, pools):
    local = frozen | {'purpose': 'calibration'}
    valid = all(summarize.calibration(json.loads(Path(p['results']).read_text()),
        json.loads((Path(p['results']).parent / 'mapping.json').read_text()), local)['passed'] for p in pools)
    if not valid:
        disposed = store.index().dispositions
        for trial in store.rows('trial'):
            if (trial['campaign_id'], trial.get('generation')) == (cid, generation) and trial['trial_id'] not in disposed:
                campaign.dispose(store, target_kind='trial', target_id=trial['trial_id'],
                                 kind='invalidated', reason='generation calibration failed')
        state['stopped'] = 'invalid_evidence'
    return valid


def mark_evaluated(state, generation, draw):
    done = state.setdefault('fresh_resets', [])
    if [generation, draw] not in done:
        done.append([generation, draw])
        state['outcomes'][state['resolved'].index([generation, draw])] = 'fresh'
        state['futility_streak'] = 0


def parameters(config_path, frozen, *, seeds, run_seed, call_cap, concurrency, runtime, judges, roots):
    return {'criterion_sha256': frozen['criterion_sha256'], 'config_sha256': repos.sha256_file(config_path),
        'horizon': frozen['horizon'], 'seeds': {str(p.resolve()): mode1.seed_digest(p) for p in seeds},
        'run_seed': run_seed, 'call_cap': call_cap, 'concurrency': concurrency,
        'runtime': str(runtime.resolve()), 'runtime_commit': repos.runtime_commit(runtime),
        'judges': list(judges), 'roots': {k: str(Path(v).resolve()) for k, v in roots.items()}}


def start_state(store, label, policy, ctx, params, frozen, adaptive_tasks, validation_task, sealed_task):
    warm_id = campaign.warm_start_id(store, ctx)
    if not warm_id:
        raise ValueError('run requires the context\'s shared warm start')
    warm = find_campaign(store, warm_id)
    if (campaign.read_checkpoint(store, warm_id) or {}).get('stopped') != 'complete':
        raise ValueError('campaign requires a complete calibrated warm acquisition')
    evidence = Path(warm['roots']['evidence'])
    acquisition = campaign.budget_union(read_log(evidence / 'log.jsonl'), pool_paths(evidence), frozen['price_table'])
    trials = [r['trial_id'] for r in store.rows('trial') if r['campaign_id'] == warm_id]
    declared = {package_digest(t): 'adaptive' for t in adaptive_tasks} | {
        package_digest(validation_task): 'validation', package_digest(sealed_task): 'sealed'}
    cid = campaign.start_campaign(store, label=label, context=ctx, policy=policy, parameters=params,
        budget={'call_cap': params['call_cap'], 'warm_start': acquisition}, seeds=warm['seeds'],
        run_seed=params['run_seed'], warm_start=trials, declared_roles=declared, roots=params['roots'])
    state = {'campaign_id': cid, 'generation': 0, 'completed_generation': 0, 'rng_state': None,
        'ingestion_position': 0, 'ledger_index': 0, 'futility_streak': 0, 'budget': {}, 'stopped': None,
        'scheduled': [], 'outcomes': [], 'resolved': [], 'trajectory': [], 'started_at': time.time()}
    state.update(campaign.rebuild(store, cid, criterion=frozen, pools=pool_values([evidence], Path(params['criterion_path'])),
                                  generation=0, previous={}))
    return cid, state


def run_campaign(config_path, *, criterion, label, policy, store, seeds, adaptive_tasks, validation_task,
                 sealed_task, generations, episodes_per_generation, run_seed, work_root, evidence_root,
                 pools_root, agent_cmd, runtime, env, timeout_sec, solutions, call_cap, concurrency, judges,
                 hide=(), continue_run=False, scorer=None):
    frozen = check_campaign(config_path, criterion, agent_cmd=agent_cmd, timeout_sec=timeout_sec, policy=policy, runtime=runtime)
    check_run_parameters(frozen, generations, episodes_per_generation, label, policy, run_seed, call_cap, concurrency,
                         adaptive_tasks, validation_task, sealed_task, runtime)
    work_root, evidence_root = driver.check_roots(work_root, evidence_root)
    pools_root = check_pools_root(pools_root, work_root, evidence_root)
    roots = {'work': work_root, 'evidence': evidence_root, 'pools': pools_root}
    campaign.check_roots(store.root, roots.values())
    prepare_log(evidence_root, continue_run)
    params = parameters(config_path, frozen, seeds=seeds, run_seed=run_seed, call_cap=call_cap,
        concurrency=concurrency, runtime=runtime, judges=judges, roots=roots) | {'criterion_path': str(criterion.resolve())}
    ctx = context(frozen, adaptive_tasks, runtime)
    previous = [r for r in store.rows('campaign') if r['label'] == label]
    if continue_run:
        if not previous or (previous[-1]['parameters'], previous[-1]['policy'], previous[-1]['context_key']) != (params, policy, ctx):
            raise ValueError('resume differs from frozen campaign parameters')
        cid = previous[-1]['campaign_id']
        state = campaign.read_checkpoint(store, cid)
        if state is None:
            raise ValueError('resume requires an existing campaign checkpoint')
    else:
        cid, state = start_state(store, label, policy, ctx, params, frozen, adaptive_tasks, validation_task, sealed_task)
    replay_judge_incidents(state, read_log(evidence_root / 'log.jsonl'))
    rng = random.Random(run_seed)
    if state['rng_state'] is not None:
        rng.setstate(tuples(state['rng_state']))
    ledger.settle_killed_episodes(evidence_root)
    pools_root.mkdir(parents=True, exist_ok=True)
    hidden = [pools_root, *masked_roots(store, cid, hide)]
    launch = dict(work_root=work_root, evidence_root=evidence_root, pools_root=pools_root, runtime=runtime,
        env=env, timeout_sec=timeout_sec, solutions=driver.check_solutions(adaptive_tasks, solutions, runtime),
        call_cap=call_cap, concurrency=concurrency, holdouts=[validation_task, sealed_task], hide=hidden,
        scan_roots=hidden, agent_cmd=agent_cmd, run_seed=run_seed, frozen=frozen, criterion=criterion, resume=True,
        judge_env={**env, 'COMPARE_CLAUDE_MODELS': 'gpt-5.6-terra', 'ORC_ALLOWED_CLAUDE_MODELS': 'gpt-5.6-terra'})
    settled = install_gate(store, cid, state, frozen, criterion, launch, rng)
    judge = {'criterion': criterion, 'judges': judges, 'scorer': scorer}
    settled()
    try:
        run_generations(state, generations, load_config(config_path), store, cid, criterion, rng, adaptive_tasks, launch, judge)
    except (ledger.CallCapExceeded, QuotaExhausted, ValueError) as error:
        state['stopped'] = 'call_cap' if isinstance(error, ledger.CallCapExceeded) else 'quota_exhaustion' if isinstance(error, QuotaExhausted) else 'invalid_evidence'
        state['stop_detail'] = str(error)
    state['rng_state'] = rng.getstate()
    campaign.write_checkpoint(store, cid, state)
    result = state | {'parameters': params, 'convergence': campaign.convergence(store, cid)}
    (evidence_root / 'readout.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def run_generations(state, generations, config, store, cid, criterion, rng, tasks, launch, judge):
    while state['completed_generation'] < generations and not state['stopped']:
        if campaign_elapsed(state, time.time()) >= launch['frozen']['envelope']['wall_clock_ceiling_h'] * 3600:
            state['stopped'] = 'wall_clock_ceiling'
            break
        try:
            campaign_generation(state['completed_generation'] + 1, state, config, store=store, campaign_id=cid,
                criterion=criterion, rng=rng, adaptive_tasks=tasks, launch=launch, judge=judge)
        except judging.JudgeIncident:
            count = state.get('judge_incidents', 0) + 1
            log = launch['evidence_root'] / 'log.jsonl'
            append_record(log, {'kind': 'judge_incident', 'campaign_id': cid, 'generation': state['generation'],
                'completed_generation': state['generation'], 'judge_incidents': count, 'rng_state': rng.getstate(),
                'stopped': 'judge_incidents' if count >= 2 else None})
            replay_judge_incidents(state, read_log(log))
            launch['settled']()
    if not state['stopped'] and generations == launch['frozen']['horizon']['generations']:
        state['stopped'] = 'horizon'


def masked_roots(store, cid, hide):
    previous = [Path(value) for row in store.rows('campaign') if row['campaign_id'] != cid
                for value in row['roots'].values() if Path(value).is_dir()]
    return list(dict.fromkeys([store.root, *hide, *previous]))
