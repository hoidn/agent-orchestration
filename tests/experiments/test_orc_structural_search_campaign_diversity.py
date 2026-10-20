"""Cumulative campaign diversity helpers; all checks are local and provider-free."""

import hashlib
import json
from pathlib import Path

import pytest

from experiments.orc_structural_search import campaign, evaluation, site_evidence
from experiments.compare.repos import runtime_commit
from experiments.orc_structural_search.candidates import candidate_id, compile_candidate
from experiments.orc_structural_search.briefs import feedback_text
from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.records import UNAVAILABLE
from tests.experiments.orc_structural_search_support import world


def _config():
    return ExperimentConfig(
        mutable_files=("implement_check_diagnose_repair.orc",), mutable_definitions=("run",),
        condition="module", interface="I1", entry_workflow="implement_check_diagnose_repair::run",
        source_root=".", providers_file="providers.json", command_boundaries_file="commands.json",
        episode_wall_clock_sec=600, criterion_sha256=None,
        models={"claude-sonnet-5-5": ["medium"], "gpt-5.6-terra": ["high"]},
        per_call_timeout_sec=5400)


def _summary(candidate_id, *, idea="idea-a", skeleton="skeleton-a", policies=("provider", "model", "effort"),
             digest=None, campaign_id="c1-1"):
    return {"candidate_id": candidate_id, "campaign_id": campaign_id, "idea_key": idea, "skeleton": skeleton,
            "policies": [list(policies)], "program_digest": digest, "structure": {
                "heads_outline": [{"definition": "run", "forms": [{"head": "defworkflow", "arity": 3}]}],
                "control_heads": {"if": 1}, "provider_roles": ["providers.coder"], "loop": False,
                "check_gated": True, "idea_key": idea}}


def _store():
    initial, own_a, own_b, sibling = "seed", "child-a", "child-b", "sibling"
    rows = [
        {"kind": "campaign", "campaign_id": "warm-1", "warm_start": []},
        {"kind": "campaign", "campaign_id": "c1-1", "warm_start": ["warm-trial"]},
        {"kind": "campaign", "campaign_id": "c2-1", "warm_start": ["warm-trial"]},
        {"kind": "trial", "trial_id": "warm-trial", "campaign_id": "warm-1", "candidate_id": initial},
        {"kind": "trial", "trial_id": "own-a", "campaign_id": "c1-1", "candidate_id": own_a},
        {"kind": "trial", "trial_id": "own-b", "campaign_id": "c1-1", "candidate_id": own_b},
        {"kind": "trial", "trial_id": "sib", "campaign_id": "c2-1", "candidate_id": sibling},
        {"kind": "subject", **_summary(initial, digest="digest-seed", campaign_id="warm-1")},
        {"kind": "subject", **_summary(own_a, idea="idea-shared", skeleton="skeleton-a", policies=("p", "m", "e"),
                                         digest="digest-a", campaign_id="c1-1")},
        {"kind": "subject", **_summary(own_b, idea="idea-shared", skeleton="skeleton-b", policies=("p", "m", "e"),
                                         digest="digest-b", campaign_id="c1-1")},
        {"kind": "subject", **_summary(sibling, idea="sibling-idea", skeleton="sibling-skeleton",
                                         digest="digest-sibling", campaign_id="c2-1")},
    ]
    return campaign.Store(Path("/store"), rows)


def test_structural_summary_reads_authored_source_and_has_an_idea_key(world):
    (world.candidate / "evaluator-only.json").write_text('{"value": 999, "hidden": "must not be read"}')
    result = campaign.structural_summary(world.candidate, _config(), runtime=world.runtime)
    assert result["heads_outline"] and result["control_heads"]["if"] == 1
    assert result["provider_roles"] == ["providers.coder", "providers.reviewer", "providers.coder"]
    assert result["check_gated"] is True and result["loop"] is False
    assert result["policy_set"] and result["call_sites"] == len(result["provider_roles"])
    expected = hashlib.sha256(json.dumps({"control_heads": result["control_heads"],
                                          "provider_roles": result["provider_roles"],
                                          "check_gated": result["check_gated"]}, sort_keys=True).encode()).hexdigest()
    assert result["idea_key"] == expected and "value" not in result and "hidden" not in result
    assert result["call_sites"] > 0 and result["private_definitions"] >= 1


def test_structural_summaries_render_only_safe_fields_even_when_strays_are_nested():
    structure = {"heads_outline": [{"definition": "run", "forms": [{"head": "if", "arity": 3},
                                                               {"head": "loop/recur", "arity": 2}],
                                    "value": 987, "hidden": "/e/hidden"}],
                 "control_heads": {"if": 1, "sealed": "/s/sealed"},
                 "provider_roles": ["providers.coder", "/p/pool"], "loop": False, "check_gated": True,
                 "idea_key": "a" * 64, "pool": "/p/pool", "evidence_root": "/e/root",
                 "validation": {"score": 88}, "sealed": {"outcome": "pass"}}
    text = feedback_text({"evaluated_structures": [structure], "value": "root-score-marker",
                          "hidden": "root-hidden-marker", "pool": "/p/root-pool",
                          "evidence_root": "/e/root", "validation": "root-validation-marker",
                          "sealed": "root-sealed-marker"})
    assert all(piece in text for piece in ("run: if/3, loop/recur/2", "if=1", "providers.coder", "a" * 12))
    assert all(secret not in text for secret in ("987", "/e/hidden", "/s/sealed", "/p/pool", "/e/root",
                                                  "root-score-marker", "root-hidden-marker",
                                                  "root-validation-marker", "root-sealed-marker", "outcome"))


def test_evaluated_structures_use_only_initial_own_and_scheduled_candidates():
    store = _store()
    scheduled = [{**_summary("scheduled", idea="new", skeleton="skeleton-a", policies=("p", "m", "f"),
                              digest="digest-scheduled", campaign_id="c1-1")}]
    summaries = campaign.evaluated_structures(store, "c1-1", scheduled=scheduled)
    assert {row["candidate_id"] for row in summaries} == {"seed", "child-a", "child-b", "scheduled"}
    assert [row["candidate_id"] for row in summaries] == sorted(row["candidate_id"] for row in summaries)
    assert all(not {"source", "descriptor", "program_digest", "pool", "evidence_root"} & row.keys()
               for row in summaries)


def test_known_structures_keep_all_seen_policy_sets_and_digests():
    store = _store()
    scheduled_subject = _summary("scheduled", idea="new", skeleton="skeleton-a", policies=("p", "m", "f"),
                                 digest="digest-scheduled", campaign_id="c1-1")
    scheduled_subject["policies"] = frozenset({("p", "m", "f")})
    scheduled = [scheduled_subject]
    known, digests = campaign.known_structures(store, "c1-1", scheduled=scheduled)
    assert known["skeleton-a"] == {frozenset({("provider", "model", "effort")}),
                                    frozenset({("p", "m", "e")}), frozenset({("p", "m", "f")})}
    assert "skeleton-b" in known and "sibling-skeleton" not in known
    assert digests == {"digest-seed", "digest-a", "digest-b", "digest-scheduled"}


def test_evaluated_structures_keep_the_twelve_most_recent():
    store = _store()
    scheduled = [{**_summary(f"scheduled-{index:02}", digest=f"digest-{index}", campaign_id="c1-1")}
                 for index in range(13)]
    summaries = campaign.evaluated_structures(store, "c1-1", scheduled=scheduled)
    assert {row["candidate_id"] for row in summaries} == {f"scheduled-{index:02}" for index in range(1, 13)}


def test_revisit_uses_digest_or_skeleton_and_every_seen_policy_set():
    known = {"same": {frozenset({("p", "m", "e")}), frozenset({("p", "m", "h")})}}
    digests = {"digest-known"}
    assert campaign.is_revisit("different", "digest-known", frozenset(), known=known, known_digests=digests)
    assert campaign.is_revisit("same", None, frozenset({("p", "m", "e")}), known=known,
                                known_digests=digests)
    assert campaign.is_revisit("same", None, frozenset({("p", "m", "h")}), known=known,
                                known_digests=digests)
    assert not campaign.is_revisit("same", None, frozenset({("p", "m", "f")}), known=known,
                                   known_digests=digests)


def test_futility_counts_failures_ignores_incidents_and_fresh_resets():
    assert campaign.futility(["revisit", "incident", "rejected", "exhausted"], consecutive=3)
    assert not campaign.futility(["revisit", "rejected", "fresh", "incident", "exhausted"], consecutive=3)
    assert campaign.futility(["fresh", "revisit", "incident", "rejected"], consecutive=2)


def test_same_idea_with_distinct_skeletons_is_evaluated_and_convergence_is_diagnostic():
    assert not campaign.is_revisit("skeleton-a", None, frozenset({("p", "m", "e")}),
                                   known={"skeleton-b": {frozenset({("p", "m", "e")})}},
                                   known_digests=set())
    result = campaign.convergence(_store(), "c1-1")
    assert result == {"shares": {"idea-shared": 1.0}, "max_share": 1.0}


def test_convergence_excludes_initial_evidence_and_sibling_campaign_children():
    store = _store()
    store._rows.append({"kind": "trial", "trial_id": "own-c", "campaign_id": "c1-1", "candidate_id": "child-c"})
    store._rows.append({"kind": "subject", **_summary("child-c", idea="idea-other", skeleton="skeleton-c",
                                                       campaign_id="c1-1")})
    assert campaign.convergence(store, "c1-1") == {
        "shares": {"idea-other": 1 / 3, "idea-shared": 2 / 3}, "max_share": 2 / 3}


def test_convergence_excludes_a_warm_start_seed_if_this_campaign_evaluates_it_again():
    store = _store()
    before = campaign.convergence(store, "c1-1")
    store._rows.append({"kind": "trial", "trial_id": "own-seed", "campaign_id": "c1-1", "candidate_id": "seed"})
    store._rows.append({"kind": "subject", **_summary("seed", idea="seed-idea", campaign_id="c1-1")})
    assert campaign.convergence(store, "c1-1") == before


def test_behaviour_descriptor_joins_actual_compiled_and_realized_site_identities(monkeypatch, world):
    compiled = compile_candidate(world.candidate, _config(), runtime=world.runtime)
    commit = runtime_commit(world.runtime)
    identity = candidate_id(world.candidate, orchestrator_commit=commit)
    planned = site_evidence.candidate_evidence(
        world.candidate, _config(), runtime=world.runtime, compiled=compiled,
        candidate_identity=identity, orchestrator_commit=commit)["planned_perform_sites"]
    providers = [site for site in planned if site["effect_class"] == "provider"]
    assert [site.get("provider_role") for site in providers] == [
        "providers.coder", "providers.reviewer", "providers.coder"]
    steps = {site["identity"]: {"identity": site["identity"], "effect_class": "provider",
                                "attempt": index + 1, "status": "completed"}
             for index, site in enumerate(providers)}
    monkeypatch.setattr("orchestrator.workflow.evaluated.views.load_evaluated_view",
                        lambda _root: {"status": "completed", "steps": steps})
    state_dir = world.tmp / "state"
    run_dir = state_dir / "fixture-run"
    run_dir.mkdir(parents=True)
    (run_dir / "closed_program.json").write_text(
        (world.candidate / ".orchestrate/build" / compiled.build_key / "closed_program.json").read_text())
    source = world.candidate / "implement_check_diagnose_repair.orc"
    source.write_text("(")
    effects = evaluation.realized_effects(
        state_dir, "fixture-run", generic=False, planned_sites=planned,
        candidate_identity=identity, program_digest=compiled.program_digest)
    descriptor = campaign.behaviour_descriptor(
        [{"task_id": "task-1", **effects}],
        {"structure": {"loop": False}, "allocation_changed": False})
    assert [call["identity"] for call in descriptor["realized_provider_calls"]] == [
        site["identity"] for site in providers]
    assert [call["provider_role"] for call in descriptor["realized_provider_calls"]] == [
        "providers.coder", "providers.reviewer", "providers.coder"]
    assert [call["attempts"] for call in descriptor["realized_provider_calls"]] == [1, 2, 3]
    assert (descriptor["distinct_provider_roles"], descriptor["loop_present"],
            descriptor["allocation_changed"]) == (2, False, False)


def test_behaviour_descriptor_reports_known_empty_effects_as_zero():
    result = campaign.behaviour_descriptor(
        [{"realized_perform_sites": []}], {"structure": {"loop": True}, "allocation_changed": False})
    assert result == {"realized_provider_calls": [], "distinct_provider_roles": 0,
                      "loop_present": True, "allocation_changed": False}


@pytest.mark.parametrize("structure", [None, UNAVAILABLE, []])
def test_behaviour_descriptor_treats_non_mapping_structure_as_no_loop(structure):
    result = campaign.behaviour_descriptor(
        [{"realized_perform_sites": []}], {"structure": structure, "allocation_changed": False})
    assert result["loop_present"] is False


def test_behaviour_descriptor_preserves_unavailable_and_incomplete_call_evidence():
    incomplete_rows = [[], [{"realized_perform_sites": UNAVAILABLE}],
                       [{"realized_perform_sites": [{"identity": "run / call", "effect_class": "provider",
                                                       "provider_role": "providers.coder"}]}],
                       [{"realized_perform_sites": [{"identity": "run / call", "effect_class": "provider",
                                                       "attempts": 1}]}]]
    for rows in incomplete_rows:
        result = campaign.behaviour_descriptor(rows, {"structure": {"loop": True}, "allocation_changed": False})
        assert (result["realized_provider_calls"], result["distinct_provider_roles"],
                result["loop_present"], result["allocation_changed"]) == (
                    UNAVAILABLE, UNAVAILABLE, True, False)


def test_realized_effects_adds_provider_roles_without_dropping_recorded_fields(monkeypatch, world):
    compiled = compile_candidate(world.candidate, _config(), runtime=world.runtime)
    commit = runtime_commit(world.runtime)
    identity = candidate_id(world.candidate, orchestrator_commit=commit)
    planned = site_evidence.candidate_evidence(
        world.candidate, _config(), runtime=world.runtime, compiled=compiled,
        candidate_identity=identity, orchestrator_commit=commit)["planned_perform_sites"]
    providers = [site for site in planned if site["effect_class"] == "provider"]
    steps = {site["identity"]: {"identity": site["identity"], "effect_class": "provider",
                                "attempt": index + 1, "status": "completed"}
             for index, site in enumerate(providers)}
    monkeypatch.setattr("orchestrator.workflow.evaluated.views.load_evaluated_view",
                        lambda _root: {"status": "completed", "steps": steps})
    state_dir = world.tmp / "state"
    run_dir = state_dir / "fixture-run"
    run_dir.mkdir(parents=True)
    (run_dir / "closed_program.json").write_text(
        (world.candidate / ".orchestrate/build" / compiled.build_key / "closed_program.json").read_text())
    source = world.candidate / "implement_check_diagnose_repair.orc"
    source.write_text(source.read_text().replace("providers.reviewer", "providers.forged"))
    result = evaluation.realized_effects(
        state_dir, "fixture-run", generic=False, planned_sites=planned,
        candidate_identity=identity, program_digest=compiled.program_digest)
    assert result["realized_perform_sites"] == [
        {"identity": site["identity"], "effect_class": "provider", "attempts": index + 1,
         "status": "completed", "provider_role": role}
        for index, (site, role) in enumerate(zip(providers,
                                                 ("providers.coder", "providers.reviewer", "providers.coder")))]
    mismatch = evaluation.realized_effects(
        state_dir, "fixture-run", generic=False, planned_sites=planned,
        candidate_identity=identity, program_digest="sha256:mismatch")
    assert [(site["identity"], site["attempts"], site["provider_role"])
            for site in mismatch["realized_perform_sites"]] == [
                (site["identity"], index + 1, UNAVAILABLE) for index, site in enumerate(providers)]


def test_planned_site_roles_require_candidate_identity_and_ignore_mutated_source(world):
    compiled = compile_candidate(world.candidate, _config(), runtime=world.runtime)
    commit = runtime_commit(world.runtime)
    identity = candidate_id(world.candidate, orchestrator_commit=commit)
    source = world.candidate / "implement_check_diagnose_repair.orc"
    source.write_text(source.read_text().replace("providers.reviewer", "providers.forged"))
    result = site_evidence.candidate_evidence(
        world.candidate, _config(), runtime=world.runtime, compiled=compiled,
        candidate_identity=identity, orchestrator_commit=commit)
    roles = [row["provider_role"] for row in result["planned_perform_sites"]
             if row["effect_class"] == "provider"]
    assert roles == [UNAVAILABLE, UNAVAILABLE, UNAVAILABLE]


def test_planned_sites_without_a_verified_source_binding_do_not_open_span_paths(world):
    compiled = compile_candidate(world.candidate, _config(), runtime=world.runtime)
    program = site_evidence.checked_program(world.candidate, compiled.build_key)
    (world.candidate / "implement_check_diagnose_repair.orc").write_text("(")
    rows = site_evidence.planned_sites(program)
    assert all(row["provider_role"] == UNAVAILABLE for row in rows if row["effect_class"] == "provider")


def test_candidate_evidence_reports_malformed_postcompile_source_as_unavailable(world):
    compiled = compile_candidate(world.candidate, _config(), runtime=world.runtime)
    commit = runtime_commit(world.runtime)
    identity = candidate_id(world.candidate, orchestrator_commit=commit)
    (world.candidate / "implement_check_diagnose_repair.orc").write_text("(")
    result = site_evidence.candidate_evidence(
        world.candidate, _config(), runtime=world.runtime, compiled=compiled,
        candidate_identity=identity, orchestrator_commit=commit)
    roles = [row["provider_role"] for row in result["planned_perform_sites"]
             if row["effect_class"] == "provider"]
    assert roles == [UNAVAILABLE, UNAVAILABLE, UNAVAILABLE]
    assert result["allocation_signature"] == UNAVAILABLE and result["allocation_signature_reason"]


def test_realized_effects_preserves_known_empty_and_incomplete_fields(monkeypatch, tmp_path, world):
    run_dir = tmp_path / "state" / "run"
    run_dir.mkdir(parents=True)
    compiled = compile_candidate(world.candidate, _config(), runtime=world.runtime)
    commit = runtime_commit(world.runtime)
    identity = candidate_id(world.candidate, orchestrator_commit=commit)
    planned = site_evidence.candidate_evidence(
        world.candidate, _config(), runtime=world.runtime, compiled=compiled,
        candidate_identity=identity, orchestrator_commit=commit)["planned_perform_sites"]
    (run_dir / "closed_program.json").write_text(
        (world.candidate / ".orchestrate/build" / compiled.build_key / "closed_program.json").read_text())
    monkeypatch.setattr("orchestrator.workflow.evaluated.views.load_evaluated_view",
                        lambda _root: {"status": "completed", "steps": {}})
    empty = evaluation.realized_effects(
        tmp_path / "state", "run", generic=False, planned_sites=planned,
        candidate_identity=identity, program_digest=compiled.program_digest)
    assert empty["realized_perform_sites"] == [] and empty["planned_perform_sites"] == planned
    assert len(empty["unexercised_perform_sites"]) == len(planned)
    zero = campaign.behaviour_descriptor([empty], {"structure": {"loop": False}, "allocation_changed": False})
    assert (zero["realized_provider_calls"], zero["distinct_provider_roles"]) == ([], 0)

    provider = next(site for site in planned if site["effect_class"] == "provider")
    step_id = provider["identity"]
    steps = {step_id: {"identity": step_id, "effect_class": "provider", "status": "completed"}}
    monkeypatch.setattr("orchestrator.workflow.evaluated.views.load_evaluated_view",
                        lambda _root: {"status": "completed", "steps": steps})
    incomplete = evaluation.realized_effects(
        tmp_path / "state", "run", generic=False, planned_sites=planned,
        candidate_identity=identity, program_digest=compiled.program_digest)
    assert incomplete["realized_perform_sites"] == [{
        "identity": step_id, "effect_class": "provider", "attempts": UNAVAILABLE,
        "status": "completed", "provider_role": provider["provider_role"]}]
    incomplete_descriptor = campaign.behaviour_descriptor(
        [incomplete], {"structure": {"loop": True}, "allocation_changed": False})
    assert incomplete_descriptor["realized_provider_calls"] == UNAVAILABLE
    role_missing = [{key: value for key, value in site.items() if key != "provider_role"} if site == provider else site
                    for site in planned]
    steps[step_id]["attempt"] = 2
    no_role = evaluation.realized_effects(
        tmp_path / "state", "run", generic=False, planned_sites=role_missing,
        candidate_identity=identity, program_digest=compiled.program_digest)
    assert no_role["realized_perform_sites"] == [{
        "identity": step_id, "effect_class": "provider", "attempts": 2,
        "status": "completed", "provider_role": UNAVAILABLE}]
