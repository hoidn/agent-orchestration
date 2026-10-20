"""The mode 1 readout (mode1.run_mode1 writes it to <evidence>/readout.json): per-seed outcomes, episode outcomes
and refusals, skeleton diversity and provider allocation among accepted children, their evaluation outcomes and
the records pending a scan verdict. Input: the log's records (records.read_records). A failed or incident row
whose launch hit a provider quota (quota.quota_reason) reads as `quota_incident`."""

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import mean, stdev

from experiments.orc_structural_search.quota import quota_reason
from experiments.orc_structural_search.records import UNAVAILABLE, Store, Index, campaign_candidates, find_campaign, read_records
from experiments.orc_structural_search import pricing
ESTIMATOR_VERSION = "campaign-estimate-1"

QUOTA_INCIDENT = "quota_incident"

COLLAPSE_THRESHOLD = 0.75  # design default: a terminal-only share above it means the interface collapsed


def share(count: int, total: int) -> float | str:
    return count / total if total else UNAVAILABLE


def outcome(row: Mapping, evidence_root: Path | None = None) -> str:
    return QUOTA_INCIDENT if quota_reason(row, evidence_root) else row["outcome"]


def catalog_outcomes(rows: Sequence[Mapping]) -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for row in rows:
        if row["kind"] == "evaluation" and row["mode"] == "catalog":
            entry = catalog.setdefault(row["seed"], {"candidate_id": row["candidate_id"], "outcomes": []})
            entry["outcomes"].append(outcome(row))
    return catalog


def child_outcomes(rows: Sequence[Mapping]) -> dict[str, list]:
    children: dict[str, list] = {}
    for row in rows:
        if row["kind"] == "evaluation" and row["mode"] == "unguided":
            children.setdefault(row["candidate_id"], []).append(outcome(row))
    return children


def revisit_count(accepted: Sequence[Mapping]) -> int:
    seen, revisits = set(), 0
    for row in accepted:
        seen.add(row["parent_skeleton"])
        revisits += row["skeleton"] in seen
        seen.add(row["skeleton"])
    return revisits


def diversity(accepted: Sequence[Mapping]) -> dict:
    """Skeleton diversity among accepted children. A child is terminal-only when both its skeleton and its
    provider allocation equal the parent's; one with the parent's skeleton but another allocation is
    `allocation_distinct`."""
    same_skeleton = [row for row in accepted if row["skeleton"] == row["parent_skeleton"]]
    terminal = sum(row["provider_allocation"] == row["parent_provider_allocation"] for row in same_skeleton)
    terminal_only = share(terminal, len(accepted))
    return {"distinct_skeletons": len({row["skeleton"] for row in accepted}),
            "revisit_rate": share(revisit_count(accepted), len(accepted)), "terminal_only_share": terminal_only,
            "allocation_distinct": len(same_skeleton) - terminal,
            "collapsed": terminal_only if terminal_only == UNAVAILABLE else terminal_only > COLLAPSE_THRESHOLD}


def readout(rows: Sequence[Mapping], evidence_root: Path | None = None) -> dict:
    """Per-seed outcomes, episode outcomes and refusals, skeleton diversity and provider allocation among
    accepted children, their evaluation outcomes and the evaluations and episodes pending a scan verdict;
    `evidence_root` lets episode rows from before the quota guard be read for quota messages."""
    episodes = [row for row in rows if row["kind"] == "episode"]
    accepted = [row for row in episodes if row["outcome"] == "accepted"]
    return {"catalog": catalog_outcomes(rows),
            "episodes": dict(Counter(outcome(row, evidence_root) for row in episodes)),
            "refused": dict(Counter(row["refusal_code"] or row["diagnostics_class"]
                                    for row in episodes if row["outcome"] == "rejected")),
            **diversity(accepted), "child_outcomes": child_outcomes(rows),
            "scan_pending": [row.get("evaluation_id") or row["episode_id"] for row in rows if row.get("scan_pending")]}


def behaviour_descriptor(evaluation_rows: Sequence[Mapping], episode_row: Mapping | None) -> dict:
    """A reporting-only descriptor from recorded provider effects and accepted source evidence."""
    calls = _realized_provider_calls(evaluation_rows)
    role_count = UNAVAILABLE if calls == UNAVAILABLE else len({call["provider_role"] for call in calls})
    structure = episode_row.get("structure", {}) if episode_row is not None else {}
    if not isinstance(structure, Mapping):
        structure = {}
    controls = structure.get("control_heads", {})
    loop = structure.get("loop")
    if type(loop) is not bool:
        loop = isinstance(controls, Mapping) and type(controls.get("loop/recur")) is int \
            and controls["loop/recur"] > 0
    changed = episode_row.get("allocation_changed", UNAVAILABLE) if episode_row is not None else UNAVAILABLE
    return {"realized_provider_calls": calls, "distinct_provider_roles": role_count, "loop_present": loop,
            "allocation_changed": changed if type(changed) is bool else UNAVAILABLE}


def _realized_provider_calls(evaluation_rows: Sequence[Mapping]) -> list[dict] | str:
    if not evaluation_rows:
        return UNAVAILABLE
    calls = []
    for row in evaluation_rows:
        sites = row.get("realized_perform_sites")
        if not isinstance(sites, list):
            return UNAVAILABLE
        for site in sites:
            call = _provider_call(site)
            if call == UNAVAILABLE:
                return UNAVAILABLE
            if call is not None:
                calls.append(call | ({"task_id": row["task_id"]} if isinstance(row.get("task_id"), str) else {}))
    return calls


def _provider_call(site: Mapping) -> dict | None | str:
    if not isinstance(site, Mapping):
        return UNAVAILABLE
    if site.get("effect_class") != "provider":
        return None
    identity, attempts, role = site.get("identity"), site.get("attempts"), site.get("provider_role")
    if (not isinstance(identity, str) or type(attempts) is not int or attempts < 1
            or not isinstance(role, str) or not role or role == UNAVAILABLE):
        return UNAVAILABLE
    return {"identity": identity, "attempts": attempts, "provider_role": role}


def convergence(store, campaign_id: str) -> dict:
    """Share of campaign-local evaluated children per idea key; warm starts and siblings do not count."""
    from experiments.orc_structural_search.campaign import _campaign, campaign_candidates

    candidates, campaign = campaign_candidates(store, campaign_id), _campaign(store, campaign_id)
    trials = store.index().trials
    initial = {trials[trial_id]["candidate_id"] for trial_id in campaign["warm_start"]}
    children = {trial["candidate_id"] for trial in store.rows("trial")
                if trial["campaign_id"] == campaign_id and trial["candidate_id"] not in initial and trial.get("split") not in ("validation", "sealed")}
    counts = defaultdict(int)
    for candidate_id in children:
        subject, structure = candidates[candidate_id], candidates[candidate_id].get("structure")
        idea = subject.get("idea_key") or (structure.get("idea_key") if isinstance(structure, Mapping) else None)
        if not isinstance(idea, str):
            raise ValueError(f"evaluated candidate {candidate_id} has no structural idea_key")
        counts[idea] += 1
    shares = {idea: count / len(children) for idea, count in sorted(counts.items())} if children else {}
    return {"shares": shares, "max_share": max(shares.values(), default=0.0)}


def _campaign_prefix(checkpoint, rows):
    position = checkpoint['log_position']
    if type(position) is not int or not 0 <= position <= len(rows):
        raise ValueError('checkpoint log_position must identify an available log prefix')
    return rows[:position]


def _campaign_events(rows):
    episodes = {row['episode_id']: row for row in rows if row['kind'] == 'episode'}
    decisions = {row['episode_id']: row for row in rows if row.get('campaign_decision') is True}
    draws = {(row['generation'], row['draw']): row for row in rows if row['kind'] == 'parent_decision'}
    return list(episodes.values()), decisions, draws


def _fresh_children(episodes, decisions, draws):
    fresh = {}
    for row in episodes:
        decision = decisions.get(row['episode_id'], {})
        if decision.get('kind') != 'fresh' or row['outcome'] != 'accepted':
            continue
        cid, parent = row['candidate_id'], row['parent_candidate_id']
        draw = draws[(row['generation'], row['draw'])]
        if decision['candidate_id'] != cid or draw['parent_candidate_id'] != parent:
            raise ValueError('campaign decision does not match its episode and parent draw')
        if cid != parent:
            fresh[cid] = row | {'parent_source': draw['parent_source']}
    return fresh


def _ancestor_path(candidate_id, parents, initial_ids):
    ancestors, seen = [], {candidate_id}
    while candidate_id not in initial_ids and candidate_id in parents:
        candidate_id = parents[candidate_id]
        if candidate_id in seen:
            raise ValueError('campaign lineage contains a cycle')
        seen.add(candidate_id)
        ancestors.append(candidate_id)
    return ancestors, candidate_id in initial_ids


def _campaign_lineage(frontier, fresh, initial_ids):
    parents = {cid: row['parent_candidate_id'] for cid, row in fresh.items()}
    depths, descendants = {}, defaultdict(list)
    for cid in frontier:
        ancestors, complete = _ancestor_path(cid, parents, initial_ids)
        depths[cid] = len(ancestors) if complete else UNAVAILABLE
        for ancestor in ancestors:
            descendants[ancestor].append(cid)
    return {'lineage_depth': depths,
            'frontier_by_ancestor': {cid: sorted(values) for cid, values in sorted(descendants.items())}}


def _campaign_improvements(fresh, table, criterion):
    from experiments.orc_structural_search.pareto_readout import dominating_children

    tolerances = criterion['final_choice']['equivalence_tolerance'], criterion['dominance_cost_tolerance']
    improvements = []
    for cid, row in fresh.items():
        parent = row['parent_candidate_id']
        if cid in table and parent in table:
            improvements += dominating_children([cid], table, parent, tolerances)
    return sorted(improvements)


def campaign_diagnostics(checkpoint, log_rows, *, criterion, initial_ids):
    """Describe a checkpoint using its own table and committed adaptive log prefix."""
    from experiments.orc_structural_search.pareto_readout import completed_episodes

    episodes, decisions, draws = _campaign_events(_campaign_prefix(checkpoint, log_rows))
    completed = completed_episodes(episodes, None)
    accepted = [row for row in episodes if row['outcome'] == 'accepted']
    fresh = _fresh_children(completed, decisions, draws)
    entries = sorted(set(fresh).intersection(checkpoint['frontier']))
    improvements = _campaign_improvements(fresh, checkpoint['table'], criterion)
    revisits = sum(row['kind'] == 'revisit' for row in decisions.values())
    return {'completed': len(completed), 'dominating_improvements': improvements,
            'improvements_per_completed_episode': share(len(improvements), len(completed)),
            'frontier_entries': entries, 'frontier_entries_per_completed_episode': share(len(entries), len(completed)),
            'diversity': diversity(accepted), 'campaign_revisits': revisits,
            'campaign_revisit_rate': share(revisits, len(accepted)),
            'reservoir_draws': sum(row['parent_source'] == 'reservoir' for row in draws.values()),
            'reservoir_empty_draws': sum(row['parent_source'] == 'reservoir_empty' for row in draws.values()),
            'reservoir_frontier_entries': [cid for cid in entries if fresh[cid]['parent_source'] == 'reservoir'],
            **_campaign_lineage(checkpoint['frontier'], fresh, initial_ids)}


def _evidence_trials(index: Index, candidate_id: str, context: str, names: Sequence[str]) -> tuple[list, list, list]:
    attempts = [t for t in index.trials.values() if (t["candidate_id"], t["context_key"]) == (candidate_id, context)
                and t["origin_trial_id"] is None and t["task"] in names and t.get("split") not in ("validation", "sealed")]
    excluded = sorted(t["trial_id"] for t in attempts if t["trial_id"] in index.dispositions)
    counted = [t for t in attempts if t["trial_id"] not in excluded]
    return attempts, excluded, counted


def _evidence_values(index: Index, counted: Sequence[Mapping], names: Sequence[str]) -> dict[str, list]:
    from experiments.orc_structural_search import scoring
    values = {name: [] for name in names}
    for trial in counted:
        assessed = index.assessments.get(trial["trial_id"])
        row = assessed[-1] if assessed else {
            "outcome": scoring.scored_outcome(trial | {"kind": "evaluation", "task_id": trial["task"]}),
            "value": None}
        if (value := scoring.primary_value(row)) is not None:
            values[trial["task"]].append(value)
    return values


def _observed_summary(values: Mapping[str, Sequence], counted: Sequence[Mapping], price_table: Mapping,
                      min_trials: int) -> dict:
    from experiments.orc_structural_search import scoring
    per_task = {name: {"n": len(v), "mean": mean(v) if v else UNAVAILABLE,
                       "sd": stdev(v) if len(v) > 1 else "insufficient_support"} for name, v in values.items()}
    supported = all(summary["n"] >= min_trials for summary in per_task.values())
    costs = [pricing.cost(trial, price_table) for trial in counted]
    return {"tasks": per_task, "support": "every_adaptive_task" if supported else "insufficient",
            "quality": mean(summary["mean"] for summary in per_task.values()) if supported else UNAVAILABLE,
            "cost": UNAVAILABLE if UNAVAILABLE in costs else mean(costs),
            "calls": scoring.known_mean([trial["provider_calls"] for trial in counted]),
            "wall_clock_sec": scoring.known_mean([trial["wall_clock_sec"] for trial in counted])}


def evidence(store: Store, candidate_id: str, context: str, *, tasks: Sequence[str], price_table: Mapping,
             min_trials: int) -> dict:
    """The observed estimate of `candidate_id` on `tasks` over every non-disposed original trial of equal
    `context`, across campaigns: per-task primary means (failure-inclusive) with n and SD, quality = their
    equal-weight mean when every task has `min_trials`, mean metered cost per trial (unavailable when any is),
    calls and wall clock; `unobserved` without trials, never a score."""
    index, names = store.index(), [Path(task).name for task in tasks]
    attempts, excluded, counted = _evidence_trials(index, candidate_id, context, names)
    result = {"estimator_version": ESTIMATOR_VERSION, "candidate_id": candidate_id, "context_key": context,
              "trial_ids": sorted(t["trial_id"] for t in counted), "trials": len(counted),
              "attempts": len(attempts), "disposed": len(excluded), "excluded": excluded}
    if not counted:
        return result | {"kind": "unobserved", "quality": UNAVAILABLE, "cost": UNAVAILABLE}
    return result | {"kind": "observed"} | _observed_summary(
        _evidence_values(index, counted, names), counted, price_table, min_trials)


def _candidate_row(store: Store, candidate_id: str, context: str, tasks: Sequence[str], price_table: Mapping,
                   floor: float | str, min_trials: int) -> dict:
    estimate = evidence(store, candidate_id, context, tasks=tasks, price_table=price_table, min_trials=min_trials)
    quality, cost = estimate["quality"], estimate["cost"]
    above_floor = (estimate.get("support") == "every_adaptive_task" and floor != UNAVAILABLE
                   and pricing.number(quality) and quality > floor)
    if estimate["kind"] == "unobserved":
        reason = "unobserved"
    elif estimate.get("support") != "every_adaptive_task":
        reason = "insufficient_support"
    elif floor == UNAVAILABLE:
        reason = "quality_floor_unavailable"
    elif not pricing.number(quality):
        reason = "quality_unavailable"
    elif not above_floor:
        reason = "below_quality_floor"
    elif cost == UNAVAILABLE:
        reason = "cost_unavailable"
    else:
        reason = None
    return {"candidate_id": candidate_id, "quality": quality, "cost": cost, "above_floor": above_floor,
            "reason": reason, "support": estimate.get("support", "unobserved"),
            "provider_calls": estimate.get("calls", UNAVAILABLE),
            "wall_clock_sec": estimate.get("wall_clock_sec", UNAVAILABLE)}


def _candidate_table_names(context, tasks):
    if not isinstance(context, str) or not context or not isinstance(tasks, Sequence) or not tasks:
        raise ValueError("candidate table requires a context and nonempty tasks")
    names = [Path(task).name for task in tasks]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("candidate table tasks must have unique nonempty basenames")
    return names


def _validate_candidate_cost(min_trials, floor, price_table):
    if type(min_trials) is not int or min_trials < 1:
        raise ValueError("candidate table min_trials must be a positive integer")
    if floor != UNAVAILABLE and not pricing.number(floor):
        raise ValueError("candidate table floor must be a finite nonnegative number or unavailable")
    pricing.validate(price_table)


def candidate_table(store: Store, campaign_id: str, *, context: str, tasks: Sequence[str], price_table: Mapping,
                    floor: float | str, min_trials: int, scheduled: Sequence[Mapping] = ()) -> dict[str, dict]:
    _candidate_table_names(context, tasks)
    _validate_candidate_cost(min_trials, floor, price_table)
    campaign = find_campaign(store, campaign_id)
    if campaign["context_key"] != context:
        raise ValueError(f"candidate table context {context} differs from campaign {campaign_id}'s context")
    subjects = campaign_candidates(store, campaign_id, scheduled=scheduled)
    return {candidate_id: _candidate_row(store, candidate_id, context, tasks, price_table, floor, min_trials)
            for candidate_id in sorted(subjects)}


def _assessment_log(authorization):
    role = authorization['role']
    roots = authorization[f'{role}_roots']
    log = Path(roots['evidence_root']) / 'log.jsonl'
    rows = read_records(log) if log.exists() else []
    mine = [Path(r['pool']) for r in rows if r['kind'] in ('judge_pool', 'judging')]
    if any(not path.resolve().is_relative_to(Path(roots['pools_root']).resolve()) for path in mine):
        raise ValueError('assessment budget pool is outside authorized roots')
    return rows, mine


def _study_assessments(store, manifest):
    from experiments.orc_structural_search import readout_join, selection
    opened = next((r for r in store.rows('disposition') if r['disposition'] == 'sealed_opened'
                   and r.get('validation_manifest_seq') == manifest['seq']), None)
    authorizations = [manifest]
    if opened:
        authorizations += [r for r in store.rows('exposure') if r['seq'] == opened['exposure_seq']]
    final, logs, pools = {}, [], []
    for authorization in authorizations:
        role = authorization['role']
        rows, mine = _assessment_log(authorization)
        logs.extend(rows)
        pools.extend(mine)
        if not any(r['kind'] == 'judging' for r in rows):
            continue
        verified = readout_join.final_pool(store, authorization, role=role)
        selection.assessment_sequences(store, authorization, verified)
        final[role] = _verified_validation(store, manifest, verified) if role == 'validation' else selection.final_figures(authorization, verified)
    return final, opened, logs, pools


def _verified_validation(store, manifest, pool):
    from experiments.orc_structural_search import records, selection
    frozen = [r for r in store.rows('disposition') if r['disposition'] == 'frozen'
              and r.get('validation_manifest_seq') == manifest['seq']]
    if frozen:
        records.frozen_rows(store, manifest, frozen[0]['reason'])
    return selection.validation_projection(store, manifest, pool)


def _campaign_view(store, header, criterion, reference):
    from experiments.orc_structural_search.records import read_checkpoint
    state = read_checkpoint(store, header['campaign_id'])
    if not state or not state.get('trajectory') or state['trajectory'][0]['generation'] != 0:
        raise ValueError('campaign readout requires its generation-zero trajectory baseline')
    rows = read_records(Path(header['roots']['evidence']) / 'log.jsonl')
    initial_ids = set(state['trajectory'][0]['table'])
    trajectory = [snapshot | {'diagnostics': campaign_diagnostics(snapshot, rows, criterion=criterion, initial_ids=initial_ids)}
                  for snapshot in state['trajectory']]
    return state | {'trajectory': trajectory, 'reference': reference, 'policy': header['policy']}


def _final_views(store, campaign_ids, views):
    exposures = [r for r in store.rows('exposure') if r['role'] == 'validation'
                 and set(r.get('campaign_ids', ())).intersection(campaign_ids)]
    final, opened, logs, pools = {}, None, [], []
    if exposures:
        if len(exposures) != 1 or sorted(campaign_ids) != exposures[0]['campaign_ids']:
            raise ValueError('final readout requires the complete authorized study manifest')
        manifest = exposures[0]
        final, opened, logs, pools = _study_assessments(store, manifest)
        for cid, view in views.items():
            if 'validation' in final:
                view['final_assessment'] = {'validation': final['validation'][cid]}
            if opened and 'sealed' in final:
                choice = final['validation'][cid]['choice']
                view['sealed_opened'] = opened
                view['final_assessment']['sealed'] = {'choice': _sealed_figure(final['sealed'][choice]),
                    'reference': _sealed_figure(final['sealed'][manifest['reference_id']])}
    return exposures, logs, pools


def _sealed_figure(figure):
    return {key: figure[key] for key in ('candidate_id', 'mean_cost', 'provider_calls')} | {'quality': figure['validation_success']}


def campaign_report(store, campaign_ids, *, criterion, ceiling, validation_results=None, sealed_results=None):
    from experiments.orc_structural_search import campaign, pareto_readout, qualification, readout_join, records
    from experiments.compare.repos import sha256_file
    frozen = json.loads(Path(criterion).read_text())
    headers = [find_campaign(store, cid) for cid in campaign_ids]
    if not headers or any(r['criterion_sha256'] != sha256_file(criterion) for r in headers):
        raise ValueError('readout campaign criterion mismatch')
    qualification.validate(criterion, runtime=Path(headers[0]['parameters']['runtime']), operation='readout')
    references = [readout_join.warm_reference(store, header, criterion) for header in headers]
    reference = {key: references[0][key] for key in ('candidate_id', 'quality', 'cost')}
    views = {header['campaign_id']: _campaign_view(store, header, frozen,
        {key: ref[key] for key in ('candidate_id', 'quality', 'cost')}) for header, ref in zip(headers, references, strict=True)}
    exposures, logs, pools = _final_views(store, campaign_ids, views)
    _requested_results(store, exposures, validation_results, sealed_results)
    report = pareto_readout.compare_campaigns(views, criterion=frozen, ceiling=ceiling)
    return report | {'reference': reference, 'warm_start': headers[0]['budget'].get('warm_start'),
                     'final_budget': campaign.budget_union(logs, pools, frozen['price_table'])}


def _requested_results(store, exposures, validation_results, sealed_results):
    from experiments.orc_structural_search.readout_join import _ingestion_authorization
    for role, supplied in (('validation', validation_results), ('sealed', sealed_results)):
        if supplied is None:
            continue
        allowed = [r for r in store.rows('exposure') if r['role'] == role and exposures
                   and r.get('campaign_ids') == exposures[0]['campaign_ids']]
        if len(allowed) != 1:
            raise ValueError('results argument lacks an authorized study manifest')
        roots = allowed[0][f'{role}_roots']
        _ingestion_authorization(store, allowed[0]['campaign_id'], roots['evidence_root'], role)
        logged = [Path(r['results']).resolve() for r in read_records(Path(roots['evidence_root']) / 'log.jsonl') if r['kind'] == 'judging']
        if [Path(supplied).resolve()] != logged:
            raise ValueError('results argument is not the authorized judging result reference')
