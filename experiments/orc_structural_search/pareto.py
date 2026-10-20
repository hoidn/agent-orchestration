"""Calibrated quality/cost comparisons; recompute the complete tolerant frontier."""
import random
from collections.abc import Collection, Mapping, Sequence

from experiments.orc_structural_search.pricing import number
from experiments.orc_structural_search.records import UNAVAILABLE


def tolerances(tau_q, tau_c):
    if not number(tau_q) or not number(tau_c):
        raise ValueError('dominance tolerances must be finite nonnegative numbers')


def dominates(a, b, tau_q, tau_c):
    tolerances(tau_q, tau_c)
    q_a, q_b, c_a, c_b = a['quality'], b['quality'], a['cost'], b['cost']
    return (q_a >= q_b - tau_q and c_a <= c_b * (1 + tau_c) and
            (q_a > q_b + tau_q or c_a < c_b * (1 - tau_c)))


def frontier(rows, tau_q, tau_c):
    tolerances(tau_q, tau_c)
    eligible = [row for row in rows if row['above_floor'] and number(row['quality']) and number(row['cost'])]
    return sorted(a['candidate_id'] for a in eligible
                  if not any(dominates(b, a, tau_q, tau_c) for b in eligible if a is not b))


def bounded_frontier(table: Mapping[str, Mapping], *, size: int, tau_q: float, tau_c: float) -> list[str]:
    if type(size) is not int or size < 1:
        raise ValueError('frontier size must be a positive integer')
    candidates = frontier(table.values(), tau_q, tau_c)
    ranked = sorted((table[cid] for cid in candidates), key=lambda row: (row['cost'], row['candidate_id']))
    if len(ranked) <= size:
        return candidates
    selected = {ranked[0]['candidate_id']}
    if size == 1:
        return sorted(selected)
    selected.add(min(ranked, key=lambda row: (-row['quality'], row['candidate_id']))['candidate_id'])
    while len(selected) < size:
        remaining = [row for row in ranked if row['candidate_id'] not in selected]
        chosen = min(remaining, key=lambda row: (
            -min(abs(row['cost'] - table[cid]['cost']) for cid in selected), row['candidate_id']))
        selected.add(chosen['candidate_id'])
    return sorted(selected)


def _reservoir_eligible(candidate_id: str, table: Mapping[str, Mapping], frontier_ids: Collection[str],
                        disposed: Collection[str]) -> bool:
    row = table.get(candidate_id)
    return (row is not None and candidate_id not in frontier_ids and candidate_id not in disposed
            and number(row.get('quality')) and row.get('support') == 'every_adaptive_task')


def _retained_reservoir(reservoir, table, frontier_ids, disposed_ids):
    prior, seen = [], set()
    for row in reservoir:
        candidate_id, admitted = row['candidate_id'], row['admitted_generation']
        if type(admitted) is not int or admitted < 0:
            raise ValueError(f'invalid admission generation for {candidate_id}')
        if candidate_id not in seen and _reservoir_eligible(candidate_id, table, frontier_ids, disposed_ids):
            prior.append({'candidate_id': candidate_id, 'admitted_generation': admitted})
            seen.add(candidate_id)
    return prior, seen


def reservoir_update(reservoir: Sequence[Mapping], table: Mapping[str, Mapping], frontier: Collection[str], *,
                     generation: int, capacity: int, disposed: Collection[str]) -> list[dict]:
    if type(generation) is not int or generation < 0 or type(capacity) is not int or capacity < 0:
        raise ValueError('reservoir generation and capacity must be nonnegative integers')
    frontier_ids, disposed_ids = set(frontier), set(disposed)
    prior, seen = _retained_reservoir(reservoir, table, frontier_ids, disposed_ids)
    admitted = prior + [{'candidate_id': candidate_id, 'admitted_generation': generation}
                        for candidate_id in sorted(table) if candidate_id not in seen and
                        _reservoir_eligible(candidate_id, table, frontier_ids, disposed_ids)]
    admitted.sort(key=lambda row: row['admitted_generation'])
    return admitted[-capacity:] if capacity else []


def _parent_inputs(policy, draw, episodes, fraction, frontier, reservoir):
    if policy not in ('frontier_only', 'mixture'):
        raise ValueError(f'unknown parent policy {policy!r}')
    if type(episodes) is not int or episodes < 1 or type(draw) is not int or not 0 <= draw < episodes:
        raise ValueError('parent draw must be an index in a positive episode count')
    if not number(fraction) or not 0 <= fraction < 0.5:
        raise ValueError('exploration fraction must be finite and in [0, 0.5)')
    frontier_ids = list(frontier)
    reservoir_ids = [row['candidate_id'] for row in reservoir]
    if not frontier_ids or any(not isinstance(candidate_id, str) for candidate_id in frontier_ids + reservoir_ids):
        raise ValueError('parent selection requires a nonempty frontier and string candidate ids')
    return frontier_ids, reservoir_ids


def select_parent(policy: str, *, draw: int, episodes: int, fraction: float, frontier: Sequence[str],
                  reservoir: Sequence[Mapping], rng: random.Random) -> tuple[str, str]:
    frontier_ids, reservoir_ids = _parent_inputs(policy, draw, episodes, fraction, frontier, reservoir)
    value = rng.random()
    if policy == 'mixture' and draw < int(episodes * fraction):
        choices, source = (reservoir_ids, 'reservoir') if reservoir_ids else (frontier_ids, 'reservoir_empty')
    else:
        choices, source = frontier_ids, 'frontier'
    return choices[min(int(value * len(choices)), len(choices) - 1)], source
