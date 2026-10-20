"""Frozen final-choice rule over evaluation records."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import mean

from experiments.orc_structural_search.records import UNAVAILABLE


def final_choice(rows: Sequence[Mapping], *, criterion: Mapping) -> str:
    """Return the `candidate_id` the frozen criterion selects among `rows`.

    `mean_cost_ceiling` must be numeric; rows above it, and rows whose cost is
    "unavailable", are excluded. Among the
    rest: rows within `equivalence_tolerance` of the best
    `validation_success`, then lower `mean_cost`, fewer `provider_calls`,
    lexically earlier `candidate_id`. The reference seed competes like any row.
    """

    if not criterion.get("criterion_sha256"):
        raise ValueError("criterion_sha256 required")
    if not any(row["is_reference"] for row in rows):
        raise ValueError("reference seed missing")
    ceiling = criterion["mean_cost_ceiling"]
    if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)):
        raise ValueError("mean_cost_ceiling must be numeric")
    eligible = [row for row in rows if _under_ceiling(row["mean_cost"], ceiling)]
    if not eligible:
        raise ValueError(f"no candidate under mean_cost_ceiling {ceiling!r}")
    best = max(row["validation_success"] for row in eligible)
    tied = [row for row in eligible if row["validation_success"] >= best - criterion["equivalence_tolerance"]]
    return min(tied, key=_tie_key)["candidate_id"]


def _under_ceiling(cost: float | str, ceiling: float) -> bool:
    return cost != UNAVAILABLE and cost <= ceiling


def _tie_key(row: Mapping) -> tuple:
    return (row["mean_cost"], row["provider_calls"], row["candidate_id"])


def assessment_sequences(store, authorization, pool):
    from experiments.orc_structural_search.records import trial_id
    sequences = []
    index = store.index()
    for row in pool['rows']:
        raw = pool['raw'][row['evaluation_id']]
        tid = trial_id(authorization['campaign_id'], raw['run_id'], raw['evaluation_id'], raw.get('attempt', 1))
        trial = index.trials.get(tid, {})
        if (trial.get('origin_trial_id'), trial.get('split'), trial.get('context_key')) != (None, raw['split'], authorization['context_key']):
            raise ValueError('final assessment lacks its original owner trial')
        assessments = [a for a in index.assessments.get(tid, ()) if a['results'] == str(Path(pool['results']).resolve())]
        if len(assessments) != 1:
            raise ValueError('final pool must be ingested through the assessment store')
        assessment = assessments[0]
        if (assessment['criterion_sha256'], assessment['proof_sha256']) != (pool['criterion_sha256'], pool['proof_sha256']):
            raise ValueError('stored assessment qualification provenance differs from verified pool')
        if (assessment['value'], assessment['clone_ids']) != (row['value'], row.get('clone_ids', [])):
            raise ValueError('stored assessment differs from verified clone join')
        if tid in index.dispositions:
            raise ValueError('final assessment trial has been disposed')
        sequences.append(assessment['seq'])
    return sorted(sequences)


def final_figures(authorization, pool):
    from experiments.orc_structural_search import pricing, scoring
    frozen = json.loads(Path(authorization['criterion_path']).read_text())
    figures = {}
    for cid in authorization['candidate_ids']:
        rows = [row for row in pool['rows'] if row['candidate_id'] == cid]
        costs = [pricing.cost(pool['raw'][row['evaluation_id']], frozen['price_table']) for row in rows]
        figures[cid] = {'candidate_id': cid, 'is_reference': cid == authorization['reference_id'],
            'validation_success': mean(scoring.primary_value(row) for row in rows),
            'mean_cost': mean(costs) if all(pricing.number(cost) for cost in costs) else UNAVAILABLE,
            'provider_calls': scoring.known_mean([row['calls'] for row in rows])}
    return figures


def validation_projection(store, authorization, pool):
    frozen = json.loads(Path(authorization['criterion_path']).read_text())
    figures = final_figures(authorization, pool)
    rule = frozen['final_choice'] | {'criterion_sha256': authorization['criterion_sha256'],
                                    'mean_cost_ceiling': authorization['mean_cost_ceiling']}
    result = {}
    for cid in authorization['campaign_ids']:
        ids = sorted({authorization['reference_id'], *authorization['finalists'][cid]})
        rows = [figures[candidate] for candidate in ids]
        shrinkage = {candidate: authorization['finalist_projection'][cid][candidate]['quality'] - figures[candidate]['validation_success']
                     for candidate in authorization['finalists'][cid]}
        result[cid] = {'choice': final_choice(rows, criterion=rule), 'finalists': authorization['finalists'][cid],
                       'reference': authorization['reference_id'], 'rows': rows, 'shrinkage': shrinkage}
    return result
