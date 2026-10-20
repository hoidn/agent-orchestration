"""Campaign evidence store: identities, exposure on actual use, the campaign-scoped candidate set, idempotent
ingestion through read_pool, dispositions, estimates and the atomic checkpoint. Synthetic logs, pools and receipts;
no provider is called."""
import json
import os
import shutil
import subprocess
import sys
from statistics import stdev
from types import SimpleNamespace

import pytest

from experiments.compare.repos import SEED_COMMIT, SEED_DATES, git
from experiments.orc_structural_search import campaign
from experiments.orc_structural_search.campaign import (
    SCHEMA, campaign_candidates, campaign_label, check_split_roles, context_key, dispose, evidence, exposure, ingest,
    open_store, read_checkpoint, record_exposure, register_subject, start_campaign, trial_id, warm_start_id,
    write_checkpoint)
from experiments.orc_structural_search.evaluation import EVALUATOR_VERSION
from experiments.orc_structural_search.records import UNAVAILABLE, append_record
from tests.experiments.qualification_support import REPO, package_sha, sha, write
from tests.experiments.readout_support import report_pool, report_qualification

SONNET = "claude-sonnet-5-5"
TABLE = {"currency": "USD", "tokens_per_unit": 1000000, "source": "frozen synthetic", "date": "2026-10-19",
         "models": {SONNET: {"input": 3, "output": 15, "cache_read": 0.3, "cache_write": 3.75}}}
ENVELOPE = {"episode_wall_clock_sec": 1800, "evaluation_wall_clock_sec": 7200, "per_call_timeout_sec": 5400}
MODEL_POLICY = {SONNET: ["low", "medium", "high"], "gpt-5.6-terra": ["low", "medium", "high"]}
A1, A2, VALIDATION, SEALED = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)  # package sha256s


def receipt(tokens=1000):
    """One complete Sonnet call: tokens * (3 + 15) / 10^6 USD."""
    return {"provider_calls": 1, "receipt_usage": [{"call_id": "1", "status": "complete", "provider": "claude",
            "usage": [{"model": SONNET, "provenance": {"complete_native_transcript": True},
                       "charge_tokens": {"input": tokens, "output": tokens, "cache_read": 0, "cache_write": 0}}]}]}


@pytest.fixture
def study(tmp_path):
    """A qualified two-task criterion (t1, t2), two contexts under it (two runtime commits) and a writer store."""
    q = report_qualification(tmp_path / "q", {"tasks": ["t1", "t2"], "envelope": ENVELOPE,
                                              "model_policy": MODEL_POLICY}, ["t1", "t2"])
    frozen = json.loads(q.criterion.read_text()) | {"criterion_sha256": sha(q.criterion)}
    digests = {task.name: package_sha(task) for task in q.tasks}
    contexts = [context_key(frozen, package_digests=digests, runtime_commit=commit,
                            evaluator_version=EVALUATOR_VERSION) for commit in ("c" * 40, "d" * 40)]
    s = SimpleNamespace(q=q, sha=sha(q.criterion), ctx=contexts[0], other_ctx=contexts[1], root=tmp_path,
                        store=open_store(tmp_path / "S", writer=True))
    yield s
    s.store.close()


def start(s, label, *, context=None, policy="frontier_only", warm=(), roles=None, roots=None):
    return start_campaign(s.store, label=label, context=context or s.ctx, policy=policy,
                          parameters={"criterion_sha256": s.sha}, budget={"call_cap": 115}, seeds=["direct"],
                          run_seed=7, warm_start=list(warm), declared_roles=roles or {},
                          roots=roots or {"work": str(s.root / "W" / label), "evidence": str(s.root / "E" / label)})


def ev(eid, cid, task, value, replicate=1, **fields):
    """An evaluation spec: a numeric `value` is a completed run's summarize value, a string the outcome."""
    return {"eid": eid, "cid": cid, "task": task, "value": value, "replicate": replicate, "fields": fields}


def logged(s, name, specs):
    """Evidence root <tmp>/<name> whose log holds one evaluation row per spec, and one qualified pool per task over
    its completed evaluations; (evidence root, pool results paths)."""
    evidence_root, runs = s.root / name, {}
    evidence_root.mkdir()
    for spec in specs:
        records, completed = evidence_root / "records" / spec["eid"], not isinstance(spec["value"], str)
        append_record(evidence_root / "log.jsonl", {
            "kind": "evaluation", "mode": "campaign", "evaluation_id": spec["eid"], "candidate_id": spec["cid"],
            "task_id": spec["task"], "replicate": spec["replicate"], "records_dir": str(records),
            "run_id": f"run-{name}-{spec['eid']}", "state_dir": str(evidence_root / "runs" / spec["eid"]),
            "outcome": "completed" if completed else spec["value"], "criterion_sha256": s.sha, "split": "adaptive",
            "wall_clock_sec": 30.0, **receipt(), **spec["fields"]})
        if completed:
            runs.setdefault(spec["task"], []).append({"run": str(records), "arm": spec["eid"], "value": spec["value"],
                                                      "hidden_value": 0.5, "calls": 1, "wall_clock_sec": 30.0})
    pools = [write(s.root / f"pools-{name}" / task / "records/results.json", {
        "criterion_sha256": s.sha, "runs": task_runs, "anchors": [], "agreement": {}, "excluded_judges": {}})
        for task, task_runs in runs.items()]
    return evidence_root, [report_pool(results, s.q, results.parent.parent.name) for results in pools]


def ingested(s, campaign_id, name, specs, context=None):
    evidence_root, pools = logged(s, name, specs)
    return ingest(s.store, campaign_id, context or s.ctx, evidence_root, pools, criterion=s.q.criterion)


def estimate(s, cid, tasks=("t1",), context=None):
    return evidence(s.store, cid, context or s.ctx, tasks=list(tasks), price_table=TABLE, min_trials=1)


def trial_ids(s):
    return {trial["evaluation_id"]: tid for tid, trial in s.store.index().trials.items()}


def test_store_refuses_a_malformed_line_and_an_unknown_kind(study, monkeypatch):
    s = study
    start(s, "c1")
    s.store.close()
    log = s.root / "S" / "evidence.jsonl"
    good = log.read_text()
    exposure_row = {"schema": SCHEMA, "kind": "exposure", "seq": 2, "package_sha256": A1, "role": "adaptive",
                    "campaign_id": "c1-1", "criterion_sha256": s.sha}
    for bad in ('{"schema": "campaign-evidence-v1", "kind": "exp', json.dumps(exposure_row | {"kind": "fitness"}),
                json.dumps({key: value for key, value in exposure_row.items() if key != "role"}),
                json.dumps(exposure_row | {"seq": 5}), json.dumps(exposure_row | {"schema": "campaign-evidence-v0"})):
        log.write_text(good + bad + "\n")
        with pytest.raises(ValueError, match="line 2"):
            open_store(s.root / "S", writer=False)
    log.write_text(good)
    s.store = open_store(s.root / "S", writer=True)
    with pytest.raises(ValueError, match="known kind"):
        s.store.append({"kind": "fitness"})
    with pytest.raises(ValueError, match="nest"):
        start(s, "c2", roots={"evidence": str(s.root)})
    monkeypatch.setattr(campaign, "main_prefix", lambda: s.root)
    with pytest.raises(SystemExit, match="main checkout prefix"):
        open_store(s.root / "S2", writer=True)
    assert not (s.root / "S2").exists()


def test_campaign_ids_carry_the_store_sequence_and_a_label_cannot_be_reused(study):
    s = study
    with pytest.raises(ValueError, match="label"):
        start(s, "C1-frontier")
    assert (start(s, "c1-frontier"), start(s, "c1-mixture")) == ("c1-frontier-1", "c1-mixture-2")
    with pytest.raises(ValueError, match="reused"):
        start(s, "c1-frontier")
    for bad in ("C1", "c1_frontier", "", "x" * 33):
        with pytest.raises(ValueError, match="label"):
            campaign_label(bad)
    assert trial_id("c1-frontier-1", "r", "e", 1) != trial_id("c1-mixture-2", "r", "e", 1)
    assert trial_id("c1-frontier-1", "r", "e", 1).startswith("trial:")


def test_ingest_is_idempotent_across_processes_and_a_rerun_adds_a_trial(study):
    s = study
    c1 = start(s, "c1-frontier")
    evidence_root, pools = logged(s, "E1", [
        ev("e1", "A", "t1", "incident", incidents=["quota: usage limit reached"]),
        ev("e2", "A", "t1", 6, attempt=2), ev("e3", "A", "t2", 5)])
    assert ingest(s.store, c1, s.ctx, evidence_root, pools, criterion=s.q.criterion) == {
        "trials": 3, "assessments": 2, "superseded": 1, "position": 3}
    s.store.close()
    code = ("import json, sys; from pathlib import Path; from experiments.orc_structural_search import campaign; "
            "store = campaign.open_store(Path(sys.argv[1]), writer=True); "
            "print(json.dumps(campaign.ingest(store, sys.argv[2], sys.argv[3], Path(sys.argv[4]), "
            "[Path(p) for p in sys.argv[6:]], criterion=Path(sys.argv[5]))))")
    done = subprocess.run([sys.executable, "-c", code, str(s.root / "S"), c1, s.ctx, str(evidence_root),
                           str(s.q.criterion), *map(str, pools)], cwd=REPO, capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(REPO)}, check=True)
    assert json.loads(done.stdout) == {"trials": 0, "assessments": 0, "superseded": 0, "position": 3}
    s.store = open_store(s.root / "S", writer=True)
    assert len(s.store.rows("trial")) == 3
    c2 = start(s, "c1-mixture")
    assert ingested(s, c2, "E2", [ev("e3", "A", "t2", 7)])["trials"] == 1
    trials = s.store.index().trials.values()
    assert sorted((t["campaign_id"], t["evaluation_id"]) for t in trials if t["evaluation_id"] == "e3") == [
        (c1, "e3"), (c2, "e3")]


def test_warm_start_is_one_campaign_per_context_and_two_contexts_never_share_a_trial_id(study):
    s = study
    warm = start(s, "warm", policy="warm_start")
    assert warm == f"warm-{s.ctx[5:17]}-1"
    assert (warm_start_id(s.store, s.ctx), warm_start_id(s.store, s.other_ctx)) == (warm, None)
    with pytest.raises(ValueError, match="reused"):
        start(s, "warm", policy="warm_start")
    other = start(s, "warm", policy="warm_start", context=s.other_ctx)
    assert other == f"warm-{s.other_ctx[5:17]}-2"
    evidence_root, _ = logged(s, "E0", [ev("e1", "A", "t1", 5)])
    for campaign_id, context in ((warm, s.ctx), (other, s.other_ctx)):
        ingest(s.store, campaign_id, context, evidence_root, [], criterion=s.q.criterion)
    by_context = {context: {tid for tid, t in s.store.index().trials.items() if t["context_key"] == context}
                  for context in (s.ctx, s.other_ctx)}
    assert all(by_context.values()) and not by_context[s.ctx] & by_context[s.other_ctx]
    with pytest.raises(ValueError, match="context"):
        start(s, "c1", context=s.other_ctx, warm=by_context[s.ctx])


def test_campaign_candidates_hold_initial_evidence_own_children_and_scheduled_children_only(study):
    s = study
    runtime = s.root / "runtime-repo"
    runtime.mkdir()
    git(runtime, "init", "-q")
    (runtime / "README").write_text("runtime\n")
    git(runtime, "add", "README")
    git(runtime, *SEED_COMMIT, env=SEED_DATES)

    def register(name, campaign_id, parent=None):
        root = s.root / "candidates" / name
        root.mkdir(parents=True)
        (root / "main.orc").write_text(f"; {name}\n")
        return register_subject(s.store, root, runtime=runtime, parent=parent, skeleton=f"skeleton-{name}",
                                policies=frozenset({("claude", SONNET, "medium")}), idea_key=f"idea-{name}",
                                descriptor={"control_heads": 1}, campaign_id=campaign_id)

    warm = start(s, "warm", policy="warm_start")
    seed = register("seed", warm)
    ingested(s, warm, "E0", [ev("w1", seed, "t1", 5)])
    initial = list(s.store.index().trials)
    c1, c2 = start(s, "c1-frontier", warm=initial), start(s, "c1-mixture", warm=initial)
    own, sibling = register("own", c1, seed), register("sibling", c2, seed)
    ingested(s, c1, "E1", [ev("k1", own, "t1", 6)])
    ingested(s, c2, "E2", [ev("k2", sibling, "t1", 7), ev("s2", seed, "t1", 3, replicate=2)])
    scheduled = {"candidate_id": "sha256:scheduled", "parent": own, "campaign_id": c1}
    held = campaign_candidates(s.store, c1, scheduled=[scheduled])
    assert set(held) == {seed, own, "sha256:scheduled"}
    assert (held[own]["parent"], held[own]["campaign_id"], held[seed]["campaign_id"]) == (seed, c1, warm)
    assert (s.store.root / "candidates" / own).is_dir()
    pooled = estimate(s, seed)
    assert (pooled["trials"], pooled["tasks"]["t1"]["mean"]) == (2, 4)


def test_assessments_come_from_read_pool_and_a_refused_pool_is_refused(study):
    s = study
    ingested(s, start(s, "c1"), "E1", [ev("e1", "A", "t1", 6), ev("e2", "A", "t1", "failed", replicate=2)])
    completed, failed = sorted(s.store.rows("assessment"), key=lambda row: row["outcome"])
    proof = json.loads(s.q.criterion.read_text())["qualification"]["sha256"]
    assert completed["clone_ids"] and (completed["value"], completed["proof_sha256"]) == (6, proof)
    assert (completed["criterion_sha256"], completed["split"]) == (s.sha, "adaptive")
    assert (failed["outcome"], failed["value"]) == ("failed", None)
    c2 = start(s, "c2")
    evidence_root, [forged] = logged(s, "E2", [ev("e9", "B", "t1", 6)])
    data = json.loads(forged.read_text())
    next(iter(data["clones"].values()))["score"] = 1
    write(forged, data)
    before = len(s.store.rows())
    with pytest.raises(ValueError, match="clone|harness"):
        ingest(s.store, c2, s.ctx, evidence_root, [forged], criterion=s.q.criterion)
    assert len(s.store.rows()) == before


def test_evidence_pools_equal_context_and_partitions_a_changed_context(study):
    s = study
    for label, context, value in (("c1", s.ctx, 4), ("c2", s.ctx, 6), ("c3", s.other_ctx, 9)):
        ingested(s, start(s, label, context=context), f"E-{label}", [ev("e1", "A", "t1", value)], context=context)
    pooled, other = estimate(s, "A"), estimate(s, "A", context=s.other_ctx)
    assert (pooled["trials"], pooled["quality"], other["trials"], other["quality"]) == (2, 5, 1, 9)
    assert pooled["context_key"] == s.ctx and not set(pooled["trial_ids"]) & set(other["trial_ids"])


def test_evidence_is_unobserved_without_trials_and_excludes_disposed_ones_and_reports_support(study):
    s = study
    ingested(s, start(s, "c1"), "E1", [ev("e1", "A", "t1", 4), ev("e2", "A", "t1", 6, replicate=2),
                                       ev("e3", "A", "t1", 8, replicate=3, receipt_usage=UNAVAILABLE)])
    unobserved = estimate(s, "B")
    assert (unobserved["kind"], unobserved["trials"], unobserved["quality"]) == ("unobserved", 0, UNAVAILABLE)
    assert estimate(s, "A")["cost"] == UNAVAILABLE
    ids = trial_ids(s)
    dispose(s.store, target_kind="trial", target_id=ids["e3"], kind="contaminated", reason="adjudicated scan hit")
    kept = estimate(s, "A")
    assert (kept["kind"], kept["quality"], kept["tasks"]["t1"]["sd"]) == ("observed", 5, stdev([4, 6]))
    assert (kept["disposed"], kept["excluded"], kept["cost"]) == (1, [ids["e3"]], pytest.approx(0.018))
    assert len(s.store.rows("trial")) == 3
    dispose(s.store, target_kind="trial", target_id=ids["e2"], kind="invalidated", reason="calibration failed")
    assert estimate(s, "A")["tasks"]["t1"]["sd"] == "insufficient_support"
    partial = estimate(s, "A", tasks=("t1", "t2"))
    assert (partial["quality"], partial["support"], partial["tasks"]["t2"]["n"]) == (UNAVAILABLE, "insufficient", 0)


def test_cost_is_unavailable_when_any_trial_receipt_is_incomplete(study):
    s = study
    ingested(s, start(s, "c1"), "E1", [
        ev("e1", "A", "t1", 4), ev("e2", "A", "t1", 6, replicate=2, **receipt(2000)),
        ev("e3", "B", "t1", 5), ev("e4", "B", "t1", 5, replicate=2, receipt_usage=UNAVAILABLE)])
    metered, unmetered = estimate(s, "A"), estimate(s, "B")
    assert metered["cost"] == pytest.approx((0.018 + 0.036) / 2)
    assert (unmetered["cost"], unmetered["calls"], unmetered["quality"]) == (UNAVAILABLE, 1, 5)


def test_a_task_exposed_in_an_earlier_campaign_is_refused_as_validation_or_sealed(study):
    s = study
    c1 = start(s, "c1", roles={A1: "adaptive", VALIDATION: "validation", SEALED: "sealed"})
    assert exposure(s.store) == {A1: {"roles": {"adaptive"}, "campaigns": [c1]}}
    for role in ("validation", "sealed"):
        with pytest.raises(ValueError, match="adaptive"):
            start(s, "c2", roles={A2: "adaptive", A1: role})
    assert len(s.store.rows("campaign")) == 1 and A2 not in exposure(s.store)
    record_exposure(s.store, package_sha256=VALIDATION, role="validation", campaign_id=c1, criterion_sha256=s.sha)
    with pytest.raises(ValueError, match="validation"):
        check_split_roles(s.store, adaptive=[A2], validation=None, sealed=VALIDATION)
    check_split_roles(s.store, adaptive=[A1], validation=VALIDATION, sealed=SEALED)
    record_exposure(s.store, package_sha256=SEALED, role="sealed", campaign_id=c1, criterion_sha256=s.sha)
    with pytest.raises(ValueError, match="sealed"):
        check_split_roles(s.store, adaptive=[SEALED], validation=None, sealed=None)


def test_two_campaigns_under_one_criterion_share_declared_roles_and_the_sealed_package_opens_once(study):
    s = study
    roles = {A1: "adaptive", A2: "adaptive", VALIDATION: "validation", SEALED: "sealed"}
    c1, c2 = start(s, "c1-frontier", roles=roles), start(s, "c1-mixture", roles=roles)
    assert exposure(s.store) == {package: {"roles": {"adaptive"}, "campaigns": [c1, c2]} for package in (A1, A2)}
    declared = {"adaptive": [A1, A2], "validation": VALIDATION, "sealed": SEALED}
    check_split_roles(s.store, **declared)  # the validation stage's setup, once for both campaigns
    record_exposure(s.store, package_sha256=VALIDATION, role="validation", campaign_id=c1, criterion_sha256=s.sha)
    assert exposure(s.store)[VALIDATION] == {"roles": {"validation"}, "campaigns": [c1]}

    def open_sealed():
        check_split_roles(s.store, **declared)
        record_exposure(s.store, package_sha256=SEALED, role="sealed", campaign_id=c1, criterion_sha256=s.sha)

    open_sealed()
    with pytest.raises(ValueError, match="sealed"):
        open_sealed()
    assert [row["role"] for row in s.store.rows("exposure") if row["package_sha256"] == SEALED] == ["sealed"]


def test_checkpoint_is_atomic_and_rejects_another_campaigns_state(study, monkeypatch):
    s = study
    c1, c2 = start(s, "c1"), start(s, "c2")
    state = {"generation": 1, "frontier": ["A"], "reservoir": [], "rng_state": [3, [1, 2], None],
             "ingestion_position": {"E1": 3}, "ledger_index": 4, "futility_streak": 0, "budget": {"calls": 9},
             "stopped": None}
    path = write_checkpoint(s.store, c1, state)
    assert path == s.store.root / "campaigns" / c1 / "checkpoint.json"
    assert read_checkpoint(s.store, c1) == state | {"schema": "campaign-checkpoint-v1", "campaign_id": c1,
                                                    "context_key": s.ctx, "criterion_sha256": s.sha}
    assert read_checkpoint(s.store, c2) is None
    with pytest.raises(ValueError, match="stopped"):
        write_checkpoint(s.store, c1, {key: value for key, value in state.items() if key != "stopped"})

    def crash(*args):
        raise OSError("killed before the rename")

    monkeypatch.setattr(campaign.os, "replace", crash)
    with pytest.raises(OSError, match="killed"):
        write_checkpoint(s.store, c1, state | {"generation": 2})
    monkeypatch.undo()
    assert read_checkpoint(s.store, c1)["generation"] == 1
    (s.store.root / "campaigns" / c2).mkdir()
    shutil.copyfile(path, s.store.root / "campaigns" / c2 / "checkpoint.json")
    with pytest.raises(ValueError, match="campaign"):
        read_checkpoint(s.store, c2)


def test_second_writer_is_refused_while_the_lock_is_held(study):
    s = study
    with pytest.raises(RuntimeError, match="writer"):
        open_store(s.root / "S", writer=True)
    reader = open_store(s.root / "S", writer=False)
    with pytest.raises(PermissionError):
        reader.append({"kind": "exposure"})
    s.store.close()
    s.store = open_store(s.root / "S", writer=True)
    assert s.store.writer
