"""Offline model receipts and candidate-local site evidence; no provider spend."""

import json
from pathlib import Path

import pytest

from experiments.orc_structural_search import metering, site_evidence
from tests.experiments.test_orc_structural_search_metering import FULL, _assistant, _call, _jsonl, _user
from tests.experiments.test_orc_structural_search_module import PRIVATE, REPO, SOURCE, cfg, pair


def codex_receipt(path, prompt="task", models=("gpt-6.1-sol",), **changes):
    usage = dict(input_tokens=100, cached_input_tokens=30, cache_write_input_tokens=4,
                 output_tokens=20, reasoning_output_tokens=10, total_tokens=120)
    usage.update(changes)
    return _jsonl(path, [{"type": "turn_context", "payload": {"model": model}} for model in models] + [
        {"type": "event_msg", "payload": {"type": "user_message", "message": prompt}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": usage}}}])


def test_receipt_usage_keeps_model_counters_and_hashes_without_native_paths(tmp_path):
    records = tmp_path / "records"
    _call(records, 1, "task")
    session = _jsonl(tmp_path / "s.jsonl", [_user("task"), _assistant("m", FULL), _assistant("m", FULL)])
    sub = _jsonl(tmp_path / "s/subagents/a.jsonl", [_assistant("sub", FULL, "claude-sonnet-5-5")])
    report = metering.coverage(records, claude_sessions=[session, sub], codex_rollouts=[])
    call = report["receipt_usage"][0]
    assert call["status"] == "complete"
    assert [row["model"] for row in call["usage"]] == ["claude-opus-5-5", "claude-sonnet-5-5"]
    assert [row["charge_tokens"] for row in call["usage"]] == [
        dict(input=10, output=5, cache_read=3, cache_write=2)] * 2
    assert all(row["provenance"]["session_sha256"].startswith("sha256:") for row in call["usage"])
    assert str(tmp_path) not in json.dumps(call)


def test_codex_receipt_charges_last_cumulative_usage_and_never_adds_reasoning(tmp_path):
    records = tmp_path / "records"
    _call(records, 1, "task")
    rollout = codex_receipt(tmp_path / "rollout.jsonl")
    report = metering.coverage(records, claude_sessions=[], codex_rollouts=[rollout])
    row = report["receipt_usage"][0]["usage"][0]
    assert row["charge_tokens"] == dict(input=66, output=20, cache_read=30, cache_write=4)
    assert report["codex"]["tokens"] == 120
    assert row["model"] == "gpt-6.1-sol"
    assert row["reasoning_output_tokens"] == 10
    assert row["provenance"]["model_source"] == "turn_context.model"


def test_codex_charge_leaves_cache_write_out_of_input_when_total_counts_it_separately(tmp_path):
    records = tmp_path / "records"
    _call(records, 1, "task")
    rollout = codex_receipt(tmp_path / "rollout.jsonl", total_tokens=124)
    row = metering.coverage(records, claude_sessions=[], codex_rollouts=[rollout])["receipt_usage"][0]["usage"][0]
    assert row["charge_tokens"] == dict(input=70, output=20, cache_read=30, cache_write=4)


@pytest.mark.parametrize("changes", [dict(cache_write_input_tokens=None), dict(input_tokens=-1),
                                    dict(cached_input_tokens=101), dict(output_tokens=True), dict(total_tokens=-1)])
def test_incomplete_or_invalid_codex_counters_preserve_raw_but_cannot_charge(tmp_path, changes):
    records = tmp_path / "records"
    _call(records, 1, "task")
    rollout = codex_receipt(tmp_path / "rollout.jsonl", **changes)
    call = metering.coverage(records, claude_sessions=[], codex_rollouts=[rollout])["receipt_usage"][0]
    assert call["status"] == "unavailable" and call["usage"][0]["charge_tokens"] == "unavailable"


@pytest.mark.parametrize("changes", [dict(cached_input_tokens=100, cache_write_input_tokens=1),
                                    dict(total_tokens=123)])
def test_codex_charge_rejects_underflow_or_inconsistent_total(tmp_path, changes):
    records = tmp_path / "records"
    _call(records, 1, "task")
    rollout = codex_receipt(tmp_path / "rollout.jsonl", **changes)
    call = metering.coverage(records, claude_sessions=[], codex_rollouts=[rollout])["receipt_usage"][0]
    assert call["status"] == "unavailable" and call["usage"][0]["charge_tokens"] == "unavailable"


@pytest.mark.parametrize("models", [(), ("unknown",), ("gpt-6.1-sol", "gpt-6-luna")])
def test_unknown_or_mixed_codex_model_is_unavailable(tmp_path, models):
    records = tmp_path / "records"
    _call(records, 1, "task")
    rollout = codex_receipt(tmp_path / "rollout.jsonl", models=models)
    row = metering.coverage(records, claude_sessions=[], codex_rollouts=[rollout])["receipt_usage"][0]["usage"][0]
    assert row["model"] == row["charge_tokens"] == "unavailable"


def test_codex_model_can_come_from_unambiguous_recorded_argv(tmp_path):
    records = tmp_path / "records"
    _call(records, 1, "task")
    (records / "calls/1/argv.nul").write_bytes(b"exec\0--model\0gpt-6.1-sol\0")
    rollout = codex_receipt(tmp_path / "rollout.jsonl", models=())
    row = metering.coverage(records, claude_sessions=[], codex_rollouts=[rollout])["receipt_usage"][0]["usage"][0]
    assert row["model"] == "gpt-6.1-sol" and row["provenance"]["model_source"] == "shim.argv"


def test_refused_attempt_without_prompt_remains_an_unmatched_receipt(tmp_path):
    call = tmp_path / "records/calls/1"
    call.mkdir(parents=True)
    (call / "stderr.txt").write_text("cap refused")
    report = metering.coverage(tmp_path / "records", claude_sessions=[], codex_rollouts=[])
    assert report["unmatched_calls"] == 1
    assert report["receipt_usage"][0]["status"] == "unavailable"


@pytest.mark.parametrize("before,after", [(':effort "high"', ':effort "low"'),
                                        ('"gpt-6.1-sol"', '"gpt-6-luna"')])
def test_allocation_tracks_model_changes_even_with_identical_skeleton(tmp_path, before, after):
    parent, child = pair(tmp_path, SOURCE.replace(before, after))
    before = site_evidence.candidate_evidence(parent, cfg(), runtime=REPO)
    after = site_evidence.candidate_evidence(child, cfg(), runtime=REPO)
    assert site_evidence.allocation_comparison(before, after)["allocation_changed"] is True
    assert before["allocation_signature"] != after["allocation_signature"]
    assert before["planned_perform_sites"]


def test_private_rename_prompt_edit_preserve_policy_but_removing_distinct_policy_changes_it(tmp_path):
    source = SOURCE.replace("  (defworkflow run", PRIVATE + "\n  (defworkflow run")
    source = source.replace('(variant Outcome DONE :summary change.summary)',
                            '(let* ((ignored (review change.summary))) (variant Outcome DONE :summary change.summary))')
    parent, child = pair(tmp_path, source)
    (parent / "direct.orc").write_text(source)
    (child / "direct.orc").write_text(source.replace("review", "renamed"))
    before = site_evidence.candidate_evidence(parent, cfg(), runtime=REPO)
    after = site_evidence.candidate_evidence(child, cfg(), runtime=REPO)
    assert site_evidence.allocation_comparison(before, after)["allocation_changed"] is False
    (child / "direct.orc").write_text(SOURCE)
    fewer = site_evidence.candidate_evidence(child, cfg(), runtime=REPO)
    assert site_evidence.allocation_comparison(before, fewer)["allocation_changed"] is True


def test_dynamic_policy_comparison_has_explicit_unavailable_reason(tmp_path):
    parent, child = pair(tmp_path, SOURCE.replace(':effort "high"', ':effort intent'))
    before = site_evidence.candidate_evidence(parent, cfg(), runtime=REPO)
    after = site_evidence.candidate_evidence(child, cfg(), runtime=REPO)
    comparison = site_evidence.allocation_comparison(before, after)
    assert comparison["allocation_changed"] == "unavailable"
    assert comparison["allocation_comparison_reason"]


def test_unexercised_join_matches_dynamic_indices_and_refuses_unmatched_effect():
    planned = [{"identity": "run / loop[*] / call", "effect_class": "provider"},
               {"identity": "run / else", "effect_class": "command"}]
    realized = [{"identity": "run / loop[2] / call", "effect_class": "provider"}]
    assert site_evidence.unexercised_sites(planned, realized, completed=True) == [planned[1]]
    assert site_evidence.unexercised_sites(planned, realized, completed=False) == "unavailable"
    assert site_evidence.unexercised_sites([], realized, completed=True) == "unavailable"


def test_truncated_session_retains_known_usage_and_path_but_never_claims_complete(tmp_path):
    import re
    tree, home, records = tmp_path / "tree", tmp_path / "home", tmp_path / "records"
    _call(records, 1, "task")
    session = _jsonl(home / ".claude/projects" / re.sub(r"[^A-Za-z0-9]", "-", str(tree)) / "s.jsonl",
                     [_user("task"), _assistant("m", FULL)])
    session.write_text(session.read_text() + '{"type":')
    report = metering.receipts(records, tree=tree, home=home, since=0)
    assert report["consumption"] == "unavailable"
    assert report["native_session_paths"] == [str(session)]
    assert report["receipt_usage"][0]["usage"][0]["input_tokens"] == 10
    assert report["receipt_usage"][0]["usage"][0]["charge_tokens"] == "unavailable"


def test_malformed_final_codex_total_never_reuses_earlier_valid_total(tmp_path):
    records = tmp_path / "records"
    _call(records, 1, "task")
    session = codex_receipt(tmp_path / "s.jsonl")
    with session.open("a") as stream:
        stream.write(json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": "bad"}}}) + "\n")
    report = metering.coverage(records, claude_sessions=[], codex_rollouts=[session])
    assert report["receipt_usage"][0]["status"] == "unavailable"


@pytest.mark.parametrize("args", [b"exec\0--\0--model\0gpt-6.1-sol\0",
                                  b"exec\0--model\0gpt-6.1-sol\0-c\0model=other\0"])
def test_codex_model_argv_requires_one_unambiguous_option(tmp_path, args):
    records = tmp_path / "records"
    _call(records, 1, "task")
    (records / "calls/1/argv.nul").write_bytes(args)
    session = codex_receipt(tmp_path / "s.jsonl", models=())
    row = metering.coverage(records, claude_sessions=[], codex_rollouts=[session])["receipt_usage"][0]["usage"][0]
    assert row["model"] == "unavailable"


def test_second_same_policy_static_helper_invocation_does_not_change_allocation(tmp_path):
    source = SOURCE.replace("  (defworkflow run", PRIVATE + "\n  (defworkflow run")
    use = '(let* ((ignored (review change.summary))) (variant Outcome DONE :summary change.summary))'
    source = source.replace('(variant Outcome DONE :summary change.summary)', use)
    parent, child = pair(tmp_path, source.replace('((ignored (review change.summary)))',
                                                 '((ignored (review change.summary)) (again (review change.summary)))'))
    (parent / 'direct.orc').write_text(source)
    before = site_evidence.candidate_evidence(parent, cfg(), runtime=REPO)
    after = site_evidence.candidate_evidence(child, cfg(), runtime=REPO)
    assert len(after["allocation_signature"]) == len(before["allocation_signature"]) + 1
    assert after["allocation_signature"] != before["allocation_signature"]
    assert site_evidence.allocation_comparison(before, after)["allocation_changed"] is False


def test_loop_budget_changes_structure_but_not_static_allocation(tmp_path):
    helper = '(defproc helper ((task String) (repo String)) -> Change\n      (loop/recur :max 2 :state (loop-state (i Int 0))\n        :on-exhausted (record Change :summary "exhausted" :account "exhausted")\n        (fn (state) (done (provider-result providers.coder\n          :prompt (implement-prompt :task task :repo repo)\n          :model "gpt-6.1-sol" :effort "high" :timeout-sec 5400)))))'
    source = SOURCE.replace("  (defworkflow run", helper + "\n  (defworkflow run")
    start = source.index("(provider-result providers.coder", source.index("(defworkflow run"))
    stop = source.index(":timeout-sec 5400)", start) + len(":timeout-sec 5400)")
    source = source[:start] + "(helper task repo)" + source[stop:]
    parent, child = pair(tmp_path, source.replace(":max 2", ":max 3"))
    (parent / "direct.orc").write_text(source)
    before = site_evidence.candidate_evidence(parent, cfg(), runtime=REPO)
    after = site_evidence.candidate_evidence(child, cfg(), runtime=REPO)
    assert isinstance(before["allocation_signature"], dict)
    assert site_evidence.allocation_comparison(before, after)["allocation_changed"] is False


@pytest.mark.parametrize("bad", ['{"type":', json.dumps({"type": "assistant", "message": ["bad"]})])
def test_malformed_subagent_preserves_main_usage_and_makes_call_unavailable(tmp_path, bad):
    records = tmp_path / "records"
    _call(records, 1, "task")
    session = _jsonl(tmp_path / "main.jsonl", [_user("task"), _assistant("m", FULL)])
    sub = _jsonl(tmp_path / "main/subagents/a.jsonl", [])
    sub.write_text(bad)
    report = metering.coverage(records, claude_sessions=[session, sub], codex_rollouts=[])
    assert report["receipt_usage"][0]["status"] == report["claude"]["tokens"] == "unavailable"
    assert report["receipt_usage"][0]["usage"][0]["input_tokens"] == 10


def test_malformed_user_message_retains_prior_raw_and_invalidates_coverage(tmp_path):
    records = tmp_path / "records"
    _call(records, 1, "task")
    session = _jsonl(tmp_path / "main.jsonl", [_user("task"), _assistant("m", FULL),
                                               {"type": "user", "message": ["bad"]}])
    report = metering.coverage(records, claude_sessions=[session], codex_rollouts=[])
    assert report["receipt_usage"][0]["status"] == "unavailable"
    assert report["receipt_usage"][0]["usage"][0]["input_tokens"] == 10


def test_repeated_prompt_different_argv_models_cannot_price_arbitrary_session_pairing(tmp_path):
    records = tmp_path / "records"
    for n, model in enumerate(("gpt-6.1-sol", "gpt-6-luna"), 1):
        _call(records, n, "task")
        (records / "calls" / str(n) / "argv.nul").write_bytes(f"exec\0--model\0{model}\0".encode())
    sessions = [codex_receipt(tmp_path / "a.jsonl", models=()),
                codex_receipt(tmp_path / "b.jsonl", models=(), input_tokens=200, total_tokens=220)]
    for order in (sessions, list(reversed(sessions))):
        report = metering.coverage(records, claude_sessions=[], codex_rollouts=order)
        assert all(call["status"] == "unavailable" for call in report["receipt_usage"])
        assert all(call["usage"][0]["charge_tokens"] == "unavailable" for call in report["receipt_usage"])
