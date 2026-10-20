"""Matched candidate/parent observations and per-arm calibrated Pareto endpoints."""
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import mean

from experiments.orc_structural_search import call_identity, pareto, pricing
from experiments.orc_structural_search.quota import quota_reason
from experiments.orc_structural_search.readout import share
from experiments.orc_structural_search.records import UNAVAILABLE
from experiments.orc_structural_search.scoring import latest_evaluations, primary_value

TERMINAL = ('accepted', 'rejected', 'exhausted', 'incident')


def rules(criterion):
    tau_q = criterion['final_choice']['equivalence_tolerance']
    tau_c = criterion['dominance_cost_tolerance']
    pareto.tolerances(tau_q, tau_c)
    if criterion.get('quality_floor') != {'kind': 'above_stub'}:
        raise ValueError('quality_floor supports only {kind: above_stub}')
    if 'calibration' not in criterion:
        raise ValueError('calibration required for Pareto readout')
    pricing.validate(criterion.get('price_table'))
    return tau_q, tau_c


def stub_floor(pools, criterion):
    totals = {}
    for pool in pools:
        task = Path(pool['task']).name
        role = criterion['anchors'][task]['stub']
        valid = [a['total'] for a in pool['anchors'] if a.get('anchor') == role and pricing.number(a.get('total'))]
        if valid:
            totals.setdefault(task, []).extend(valid)
    tasks = {Path(task).name for task in criterion['tasks']}
    return mean(mean(totals[task]) for task in tasks) if set(totals) == tasks else UNAVAILABLE


def joined_rows(pools, raw, sha):
    joined = {}
    for pool in pools:
        if pool.get('criterion_sha256') != sha:
            raise ValueError('pool criterion_sha256 differs from Pareto criterion')
        for row in pool['rows']:
            eid = row['evaluation_id']
            if eid not in raw:
                raise ValueError(f'joined evaluation {eid} has no current log receipt')
            if eid in joined and joined[eid] != row:
                raise ValueError(f'conflicting harness joins for {eid}')
            joined[eid] = row
    return list(joined.values())


def signature_pairs(signature):
    if not isinstance(signature, Mapping) or not signature:
        return None
    pairs = set()
    for policy in signature.values():
        if not isinstance(policy, Mapping) or not known_policy(policy):
            return None
        pair = policy.get('model'), policy.get('effort')
        if not all(isinstance(v, str) and v.strip() and v not in ('unavailable', 'unknown', 'auto', 'default') for v in pair):
            return None
        pairs.add(pair)
    return pairs


def known_policy(policy):
    values = [policy.get(key) for key in ('provider', 'model', 'effort')]
    return all(isinstance(v, str) and bool(v.strip()) and
               v.lower() not in ('unavailable', 'unknown', 'auto', 'default') for v in values)


def homogeneous(raw, candidates):
    grouped = {cid: [] for cid in candidates}
    for row in raw.values():
        if row['candidate_id'] in grouped:
            grouped[row['candidate_id']].append(resolved_pairs(row))
    pairs = set()
    for signatures in grouped.values():
        if not signatures or any(s is None for s in signatures):
            return False
        for signature in signatures:
            pairs.update(signature)
    return len(pairs) == 1


def resolved_pairs(row):
    declared = signature_pairs(row.get('allocation_signature'))
    observed = call_identity.observed_pairs(row)
    if declared is None or observed is None or declared != observed:
        return None
    return declared


def support(criterion):
    replicates = criterion['subset']['replicates']
    if type(replicates) is not int or replicates < 1:
        raise ValueError('subset.replicates must be a positive integer')
    return {(Path(task).name, rep) for task in criterion['tasks'] for rep in range(1, replicates + 1)}


def candidate_rows(cid, joined, expected):
    mine = [row for row in joined if row['candidate_id'] == cid]
    keys = [(row['task'], row['replicate']) for row in mine]
    values = [primary_value(row) for row in mine]
    matched = len(keys) == len(set(keys)) and set(keys) == expected
    valued = all(pricing.number(value) for value in values)
    return mine, matched and valued


def complete_mean(mine, expected, values):
    keys = [(row['task'], row['replicate']) for row in mine]
    if len(keys) != len(expected) or set(keys) != expected:
        return UNAVAILABLE
    return mean(values) if all(pricing.number(value) for value in values) else UNAVAILABLE


def candidate_figure(cid, joined, raw, expected, table, floor):
    mine, matched = candidate_rows(cid, joined, expected)
    quality = mean(primary_value(row) for row in mine) if matched else UNAVAILABLE
    costs = [pricing.cost(raw[row['evaluation_id']], table) for row in mine]
    calls = [row.get('calls') for row in mine]
    return {'candidate_id': cid, 'quality': quality, 'metered_cost': complete_mean(mine, expected, costs),
            'provider_calls': complete_mean(mine, expected, calls),
            'above_floor': matched and floor != UNAVAILABLE and quality > floor,
            'reason': None if matched else 'unmatched_task_replicate_support',
            'support': sorted([row['task'], row['replicate']] for row in mine)}


def allocation_class(episodes, cid):
    values = {episode_change_class(row) for row in episodes if row.get('candidate_id') == cid}
    return next(iter(values)) if len(values) == 1 else 'unknown'


def episode_change_class(row):
    policy_changed = row.get('allocation_changed')
    skeleton, parent = row.get('skeleton'), row.get('parent_skeleton')
    if type(policy_changed) is not bool or any(not isinstance(value, str) or not value or
                                               value.lower() in (UNAVAILABLE, 'unknown')
                                               for value in (skeleton, parent)):
        return 'unknown'
    structure_changed = skeleton != parent
    if policy_changed and structure_changed:
        return 'both'
    if policy_changed:
        return 'policy_only'
    return 'structure_only' if structure_changed else 'unchanged'


def comparable(a, b):
    return all(pricing.number(row[key]) for row in (a, b) for key in ('quality', 'cost'))


def arm_endpoints(episodes, table, parent, frontier, tolerances, evidence_root):
    completed = completed_episodes(episodes, evidence_root)
    children = sorted({row['candidate_id'] for row in completed
                       if row['outcome'] == 'accepted' and row['candidate_id'] != parent})
    valued = [cid for cid in children if cid in table and comparable(table[cid], table[cid])]
    improvements = dominating_children(valued, table, parent, tolerances)
    entries = [cid for cid in children if cid in frontier]
    result = {'parent_candidate_id': parent, 'frontier': frontier, 'completed': len(completed), 'dominating_improvements': improvements,
              'improvements_per_completed_episode': share(len(improvements), len(completed)),
              'frontier_entries': entries, 'frontier_entries_per_completed_episode': share(len(entries), len(completed)),
              'unvalued': [cid for cid in children if cid not in valued]}
    for kind in ('policy_only', 'structure_only', 'both', 'unchanged', 'unknown'):
        result[kind] = split_endpoints(children, completed, improvements, entries, kind)
    return result


def completed_episodes(episodes, evidence_root):
    return [row for row in episodes if row['outcome'] in TERMINAL and quota_reason(row, evidence_root) is None]


def dominating_children(valued, table, parent, tolerances):
    return [cid for cid in valued if table[cid]['above_floor'] and comparable(table[cid], table[parent]) and
            pareto.dominates(table[cid], table[parent], *tolerances)]


def split_endpoints(children, episodes, improvements, entries, kind):
    mine = [cid for cid in children if allocation_class(episodes, cid) == kind]
    improved = sorted(set(mine).intersection(improvements))
    members = sorted(set(mine).intersection(entries))
    return {'children': mine, 'dominating_improvements': improved, 'frontier_entries': members,
            'improvements_per_completed_episode': share(len(improved), len(episodes)),
            'frontier_entries_per_completed_episode': share(len(members), len(episodes))}


def report(pools, rows, criterion, evidence_root, *, excluded=frozenset()):
    """Every valued candidate has identical declared task/replicate support, including the parent."""
    from experiments.orc_structural_search.three_arm import arm_specs
    tolerances = rules(criterion)
    sha = criterion['criterion_sha256']
    raw = raw_evidence(rows, sha)
    parents = next(row for row in rows if row['kind'] == 'parents')
    episodes = study_episodes(rows)
    candidates = evaluated_candidates(raw, parents, arm_specs(criterion))
    joined, floor, expected = joined_rows(pools, raw, sha), stub_floor(pools, criterion), support(criterion)
    table = {cid: candidate_figure(cid, joined, raw, expected, criterion['price_table'], floor) for cid in sorted(candidates)}
    use_proxy = homogeneous(raw, candidates) and any(r['metered_cost'] == UNAVAILABLE for r in table.values())
    axis = 'provider_calls' if use_proxy else 'metered_USD'
    for row in table.values():
        row['cost'] = row['provider_calls'] if use_proxy else row['metered_cost']
    for cid in excluded.intersection(table):
        table[cid].update(quality=UNAVAILABLE, above_floor=False, reason='contaminated_episode')
    arms = arm_reports(arm_specs(criterion), episodes, parents, table, tolerances, evidence_root)
    return {'quality_floor': floor, 'cost_axis': axis, 'candidates': table, 'arms': arms}


def raw_evidence(rows, sha):
    raw = {row['evaluation_id']: row for row in latest_evaluations(rows)}
    if any(row.get('criterion_sha256') != sha for row in raw.values()):
        raise ValueError('evaluation criterion_sha256 differs from Pareto criterion')
    return raw


def study_episodes(rows):
    return [row for row in rows if row['kind'] == 'episode' and row.get('mode') == 'three_arm']


def evaluated_candidates(raw, parents, specs):
    candidates = {row['candidate_id'] for row in raw.values()}
    candidates.update(parents[spec['parent']] for spec in specs.values())
    return candidates


def arm_reports(specs, episodes, parents, table, tolerances, evidence_root):
    result = {}
    for arm, spec in specs.items():
        mine = [row for row in episodes if row['arm'] == arm]
        parent = parents[spec['parent']]
        children = {row['candidate_id'] for row in mine if row['outcome'] == 'accepted'}
        candidates = [table[cid] for cid in children | {parent} if cid in table]
        frontier = pareto.frontier(candidates, *tolerances)
        result[arm] = arm_endpoints(mine, table, parent, frontier, tolerances, evidence_root)
    return result


def _endpoint_thresholds(**thresholds):
    for name, values in thresholds.items():
        if any(not pricing.number(value) for value in values):
            raise ValueError(f'{name} must contain finite nonnegative numbers')


def _supported_frontier(checkpoint):
    rows = [checkpoint['table'][cid] for cid in checkpoint['frontier']]
    return [row for row in rows if row.get('support') == 'every_adaptive_task'
            and row.get('above_floor') is True and comparable(row, row)]


def _campaign_checkpoint(checkpoint, ceilings, targets):
    rows = _supported_frontier(checkpoint)
    return {'generation': checkpoint['generation'], 'budget': dict(checkpoint['budget']),
            'frontier': list(checkpoint['frontier']),
            'best_quality_under': {str(ceiling): max((row['quality'] for row in rows if row['cost'] <= ceiling),
                                                    default=UNAVAILABLE) for ceiling in ceilings},
            'cheapest_meeting': {str(target): min((row['cost'] for row in rows if row['quality'] >= target),
                                                 default=UNAVAILABLE) for target in targets}}


def _cost_cut(checkpoints, cut):
    eligible = [checkpoint for checkpoint in checkpoints
                if pricing.number(checkpoint['budget']['metered_cost'])
                and checkpoint['budget']['metered_cost'] <= cut]
    return {'cut': cut, 'checkpoint': eligible[-1] if eligible else None}


def campaign_endpoints(trajectory: Sequence[Mapping], *, ceilings, targets, cuts, calls_cuts) -> dict:
    """Read bounded-frontier endpoints at the last accounted checkpoint within each cost cut.

    Append order preserves settlements within a generation. An earlier pending budget is not
    repriced from later receipts; only the latest accounting snapshot decides cost comparability.
    """
    _endpoint_thresholds(ceilings=ceilings, targets=targets, cuts=cuts)
    checkpoints = [_campaign_checkpoint(checkpoint, ceilings, targets) for checkpoint in trajectory]
    result = {'checkpoints': checkpoints}
    if not checkpoints or not pricing.number(checkpoints[-1]['budget']['metered_cost']):
        return result | {'not_comparable_at_cost_cuts': True}
    return result | {'cost_cuts': [_cost_cut(checkpoints, cut) for cut in cuts]}
