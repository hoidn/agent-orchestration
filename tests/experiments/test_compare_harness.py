"""Comparison harness, run side (experiments/compare): candidates, layout, commands, shim, collect, scan.

Behaviour on temporary git repositories with a stand-in agent CLI; see compare_harness_support.
"""

import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from experiments.compare import prepare, repos
from tests.experiments.compare_harness_support import (  # noqa: F401 (world is a fixture)
    READY, REPO, call, drive, edit, git, selects, skip_without_sandbox, start, world, write_memo, write_task,
)

skip_without_sandbox()


def test_candidates_hold_the_base_commit_alone(world):
    _, record = start(world, "best_of_n", candidates=2)
    for cand in record["candidates"]:
        readable = [subprocess.run(["git", "-C", cand, "cat-file", "-e", c], capture_output=True).returncode == 0
                    for c in (world.old, world.solution)]
        assert (git(cand, "rev-parse", "HEAD~1"), git(cand, "for-each-ref"), git(cand, "remote"), readable) == (
            world.base, "", "", [False, False])


def test_candidates_do_not_name_the_checkout_they_were_fetched_from(world):
    _, record = start(world, "direct_task")
    git_dir = Path(record["candidates"][0]) / ".git"
    assert [p.name for p in git_dir.rglob("*") if p.is_file() and str(world.runtime).encode() in p.read_bytes()] == []


def test_seed_files_are_committed_and_the_seeded_commit_is_compare_base(world):
    _, record = start(world, "best_of_n", candidates=2)
    heads = {git(cand, "rev-parse", "HEAD") for cand in record["candidates"]}
    statuses = {git(cand, "status", "--porcelain") for cand in record["candidates"]}
    assert (heads, statuses, (Path(record["candidates"][1]) / "bugs/report.md").is_file()) == (
        {record["compare_base"]}, {""}, True)


@pytest.mark.parametrize("arm, fields", [
    ("best_of_n", {"task", "intent", "repos"}),
    ("reviewed_change", {"task", "intent", "repo"}),
    ("design_review_execute", {"task", "planner_model", "reviewer_model"}),
    ("direct_task", {"task", "model", "effort"}),
    ("review_once", {"repo", "intent", "account", "replies"}),
])
def test_inputs_hold_the_arms_typed_fields(world, arm, fields):
    records, _ = start(world, arm)
    assert set(json.loads((records / "inputs.json").read_text())) == fields


def test_repository_inputs_name_absolute_candidate_paths(world):
    bon, bon_record = start(world, "best_of_n", candidates=3)
    rc, rc_record = start(world, "reviewed_change")
    assert (json.loads((bon / "inputs.json").read_text())["repos"],
            json.loads((rc / "inputs.json").read_text())["repo"]) == (
        bon_record["candidates"], rc_record["candidates"][0])


def test_run_refuses_inputs_the_arm_does_not_take(world):
    with pytest.raises(SystemExit, match="model"):
        start(world, "direct_task", sets=("effort=high",))


def test_run_refuses_a_work_root_under_the_main_checkout_prefix(world):
    with pytest.raises(SystemExit, match="main checkout prefix"):
        start(world, "direct_task", root=world.tmp / "main-evidence" / "work")


def test_run_refuses_a_runtime_under_the_main_checkout_prefix(world):
    git(world.main, "worktree", "add", "-q", "--detach", str(world.tmp / "main-frozen"), world.solution)
    world.runtime = world.tmp / "main-frozen"
    with pytest.raises(SystemExit, match="main checkout prefix"):
        start(world, "direct_task")


def test_run_refuses_a_runtime_inside_the_work_root(world):
    with pytest.raises(SystemExit, match="inside the work root"):
        start(world, "direct_task", root=world.tmp)


@pytest.mark.parametrize("root", ["/tmp/compare-work", "/dev/shm/compare-work", "/var/tmp/compare-work"])
def test_run_refuses_a_work_root_the_sandbox_would_hide(world, root):
    with pytest.raises(SystemExit, match="which the shims. sandbox replaces"):
        start(world, "direct_task", root=Path(root))


def test_run_records_the_runtime_commit(world):
    _, record = start(world, "direct_task")
    assert record["runtime_commit"] == world.solution


def test_run_refuses_a_runtime_with_uncommitted_changes_to_tracked_files(world):
    (world.runtime / "README.md").write_text("edited\n")
    with pytest.raises(SystemExit, match="uncommitted changes to tracked files"):
        start(world, "direct_task")


def test_agents_trees_have_unguessable_names_and_hold_only_candidates(world):
    _, record = start(world, "best_of_n", candidates=2)
    tree = Path(record["tree"])
    assert (tree.parent, len(tree.name), int(tree.name, 16) >= 0, sorted(p.name for p in tree.iterdir())) == (
        world.root.resolve() / "agents", 16, True, ["cand-1", "cand-2", "tmp"])


def test_bookkeeping_lives_in_the_records_directory_not_in_the_agents_tree(world):
    records, record = drive(world, "direct_task", [edit("$PWD", "a + b")], True)
    assert (records.parent, sorted(p.name for p in Path(record["tree"]).iterdir()),
            sorted(p.name for p in records.iterdir())) == (
        world.root.resolve() / "records" / "direct_task", [".model-guard", "cand-1", "tmp"],
        ["calls", "collected", "command.sh", "inputs.json", "record.json", "resume.sh"])


def execute(command):
    return json.loads(subprocess.run(["bash", "-c", command], capture_output=True, text=True, check=True).stdout)


def test_printed_command_runs_the_frozen_runtime_inside_the_candidate(world, capsys):
    records, record = start(world, "direct_task")
    rt, h, tree = world.runtime, world.runtime / "experiments/compare", Path(record["tree"])
    seen = execute(capsys.readouterr().out)
    assert (seen["main"], seen["cwd"], seen["path0"], seen["env"], seen["argv"]) == (
        str(rt / "orchestrator/__main__.py"), record["candidates"][0], str(h / "shim"),
        {"PYTHONPATH": str(rt), "COMPARE_ROOT": str(records), "COMPARE_TREE": str(tree),
         "COMPARE_BASE": record["compare_base"], "TMPDIR": str(tree / "tmp")},
        ["run", str(h / "control/direct_task.orc"), "--entry-workflow", "control/direct_task::direct-task",
         "--source-root", str(h), "--provider-externs-file", str(h / "control/direct_task.providers.json"),
         "--input-file", str(records / "inputs.json")])


def test_run_state_and_so_every_result_path_lies_inside_the_working_directory(world):
    records, record = drive(world, "direct_task", [edit("$PWD", "a + b")], True)
    memo = next(Path(record["state_root"]).glob("*/memo.jsonl"))
    assert (Path(record["state_root"]), memo.is_relative_to(record["cwd"]),
            json.loads((records / "record.json").read_text())["outcome"]) == (
        Path(record["cwd"]) / ".orchestrate" / "runs", True, "completed")


def test_resume_script_resumes_from_the_same_working_directory(world):
    records, record = start(world, "reviewed_change")
    seen = execute(f"bash {records / 'resume.sh'} 20261014T000000Z-abc")
    assert (seen["cwd"], seen["argv"]) == (record["cwd"], ["resume", "20261014T000000Z-abc"])


def test_best_of_n_result_paths_resolve_from_the_tree_and_every_candidate(world):
    records, record = start(world, "best_of_n", candidates=2)
    state, tree = Path(record["state_root"]), Path(record["tree"])
    seen = execute(f"bash {records / 'resume.sh'} R1")
    relative = state.relative_to(tree)
    assert (seen["cwd"], seen["argv"], [(Path(c) / relative).resolve() for c in record["candidates"]],
            [git(Path(c), "status", "--porcelain") for c in record["candidates"]]) == (
        str(tree), ["resume", "R1", "--state-dir", str(state)], [state.resolve()] * 2, ["", ""])


def test_best_of_n_result_written_from_a_candidate_lands_in_the_state_and_not_in_its_patch(world):
    records, record = start(world, "best_of_n", candidates=2)
    relative = Path(record["state_root"]).relative_to(record["tree"]) / "r1" / "result.json"
    cand = Path(record["candidates"][0])
    Path(record["state_root"]).mkdir(parents=True)  # the runtime creates it before the first call
    call(world, record, f"cd {cand} && mkdir -p {relative.parent} && echo '{{}}' > {relative}")
    patch = (records / "calls" / "1" / "patch-cand-1.diff").read_text()
    assert ((Path(record["state_root"]) / "r1" / "result.json").read_text(), ".orchestrate" in patch) == ("{}\n", False)


def test_shim_forwards_to_the_real_cli_without_pythonpath(world):
    _, record = start(world, "direct_task")
    done = call(world, record, "echo agent-said-hello; exit 3", binary="codex")
    assert (done.returncode, "agent-said-hello" in done.stdout, "PYTHONPATH=unset" in done.stdout) == (3, True, True)


def test_shim_hides_the_runtime_and_the_records_from_the_agent(world):
    records, record = start(world, "direct_task")
    env = dict(line.split("=", 1) for line in call(world, record, "env").stdout.splitlines()[1:] if "=" in line)
    assert (sorted(k for k in env if k.startswith("COMPARE_") or k == "PYTHONPATH"),
            [d for d in env["PATH"].split(":") if d.endswith("experiments/compare/shim")],
            [k for k, v in env.items() if str(world.runtime) in v or str(records) in v],
            env.get("CLAUDE_CODE_SUBAGENT_MODEL"), env.get("CLAUDE_CODE_SUBAGENT_MODEL_FORCE")) == (
        [], [], [], "claude-opus-5-5", "1")


def test_shim_gives_the_agent_a_private_tmp_and_process_list(world):
    _, record = start(world, "direct_task")
    done = call(world, record, "echo probe > /tmp/probe.txt; ps -e --no-headers | wc -l; ls -A /var/tmp | wc -l")
    processes, var_tmp_entries = (int(n) for n in done.stdout.split()[-2:])
    assert ((Path(record["tree"]) / "tmp/probe.txt").read_text(), processes <= 10, var_tmp_entries) == (
        "probe\n", True, 0)


def test_shim_passes_stderr_through_and_records_the_same_bytes(world):
    records, record = start(world, "direct_task")
    done = call(world, record, "for i in 1 2 3; do echo warning $i >&2; done")
    assert (done.stderr, (records / "calls/1/stderr.txt").read_text()) == ("warning 1\nwarning 2\nwarning 3\n",) * 2


def test_shim_records_each_call_with_a_patch_including_new_files(world):
    records, record = start(world, "direct_task")
    script = edit("$PWD", "a + b")
    call(world, record, script)
    call(world, record, "true")
    patch = (records / "calls/1/patch-cand-1.diff").read_text()
    assert ((records / "calls/1/prompt.txt").read_text(), "pkg/extra.py" in patch, "a + b" in patch,
            "bugs/report.md" in patch, sorted(p.name for p in (records / "calls").iterdir()),
            git(record["candidates"][0], "status", "--porcelain", "--", "pkg/extra.py")) == (
        script, True, True, False, ["1", "2"], "?? pkg/extra.py")


def test_shim_leaves_what_the_agent_staged_staged_and_records_it_in_the_patch(world):
    records, record = start(world, "direct_task")
    call(world, record, "echo new > staged.txt && git add staged.txt")
    assert (git(record["candidates"][0], "status", "--porcelain", "--", "staged.txt"),
            "staged.txt" in (records / "calls/1/patch-cand-1.diff").read_text()) == ("A  staged.txt", True)


def test_patches_ignore_external_diff_and_colour_settings(world):
    records, record = start(world, "direct_task")
    cand = record["candidates"][0]
    for key, value in (("diff.external", "false"), ("color.diff", "always"), ("diff.noprefix", "true"),
                       ("diff.mnemonicPrefix", "true")):
        git(cand, "config", key, value)
    call(world, record, edit("$PWD", "a + b"))
    patch = (records / "calls/1/patch-cand-1.diff").read_text()
    again = repos.patch_of(cand, record["compare_base"]).decode()
    assert (patch.startswith("diff --git a/"), "\n+++ b/" in patch, "\x1b[" in patch, again) == (
        True, True, False, patch)


def test_collect_takes_each_best_of_n_candidate_from_its_own_call(world):
    scripts = [edit("$PWD/cand-1", "a + b"), edit("$PWD/cand-2", "b + a"), "echo n > $PWD/cand-1/selector.txt"]
    records, collected = drive(world, "best_of_n", scripts, selects(2), candidates=2)
    first, second = ((records / collected["patches"][f"cand-{k}"]).read_text() for k in (1, 2))
    assert (collected["selected"], collected["calls"], "b + a" in second, "b + a" in first,
            "selector.txt" in first) == ("cand-2", 3, True, False, False)


def test_collect_takes_first_and_final_patches_of_reviewed_change(world):
    scripts = [edit("$PWD", "a - b + 0"), "true", edit("$PWD", "a + b"), "true"]
    records, collected = drive(world, "reviewed_change", scripts, READY)
    assert ("a - b + 0" in (records / collected["patches"]["first"]).read_text(),
            "a + b" in (records / collected["patches"]["final"]).read_text(), collected["variant"]) == (
        True, True, "READY")


@pytest.mark.parametrize("memo_prompts, message", [(["true", "true"], "2 provider starts"), (["false"], "prompt")])
def test_collect_refuses_calls_that_do_not_pair_with_the_memo(world, memo_prompts, message):
    records, record = start(world, "direct_task")
    call(world, record, "true")
    write_memo(record, memo_prompts, True)
    with pytest.raises(SystemExit, match=message):
        prepare.collect(records)


def test_collect_records_a_failed_run_with_its_reason_and_no_patch(world):
    _, collected = drive(world, "direct_task", ["true"], None, outcome="failed")
    assert (collected["outcome"], collected["failure"]["code"], collected["patches"]) == (
        "failed", "provider_timeout", {})


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_scan_records_each_hit_with_file_line_and_excerpt(world):
    records, record = start(world, "direct_task")
    cand = record["candidates"][0]
    call(world, record, "echo fine; echo 'pushed through gh pr view 3'; echo github.com/x")
    home = world.tmp / "home"
    slug = "".join(c if c.isalnum() else "-" for c in cand)
    jsonl(home / ".claude/projects" / slug / "s.jsonl", [
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": str(world.main)}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "input": {"command": f"cat {world.main}/pkg/calc.py"}}]}},
    ])
    jsonl(home / ".codex/sessions/2026/10/14/rollout-a.jsonl", [
        {"type": "session_meta", "payload": {"cwd": cand}},
        {"type": "response_item", "payload": {"type": "function_call", "arguments": f"git show {world.solution[:7]}"}},
        {"type": "response_item", "payload": {"type": "custom_tool_call", "input": f"ls {world.runtime}"}},
    ])
    jsonl(home / ".codex/sessions/2026/10/14/rollout-b.jsonl", [
        {"type": "session_meta", "payload": {"cwd": str(world.tmp)}},
        {"type": "response_item", "payload": {"type": "function_call", "arguments": "git fetch"}},
    ])
    hits = prepare.scan(records, world.solution, home=home)
    assert sorted((Path(h["file"]).name, h["line"], h["pattern"], "gh pr" in h["text"]) for h in hits) == [
        ("rollout-a.jsonl", 2, "solution hash", False), ("rollout-a.jsonl", 3, "frozen checkout", False),
        ("s.jsonl", 2, "main checkout prefix", False), ("stdout.txt", 3, "gh", True),
        ("stdout.txt", 4, "github.com", False)]


def test_scan_counts_sibling_checkouts_of_main_as_hits_but_not_its_own_tree(world):
    records, record = start(world, "direct_task")
    call(world, record, f"echo {record['candidates'][0]}; echo going through; echo {world.main}-repl/orchestrator")
    assert [(h["line"], h["pattern"]) for h in prepare.scan(records, world.solution, home=world.tmp / "home")] == [
        (4, "main checkout prefix")]


def test_scan_counts_another_runs_agents_tree_as_a_hit(world):
    records, record = start(world, "direct_task")
    _, other = start(world, "direct_task")
    call(world, record, f"ls {Path(other['tree']).name}")
    assert [h["pattern"] for h in prepare.scan(records, world.solution, home=world.tmp / "home")] == [
        "other tree or judge"]


def test_scan_counts_other_runs_records_and_pool_records_but_not_its_own_state(world):
    records, record = start(world, "direct_task")
    w = world.root.resolve()
    lines = [f"{record['state_root']}/r1/effects/x/attempt-1/result.json", ".orchestrate/runs/r1/effects/x/result.json",
             f"cat {w}/records/best_of_n/run-1/collected/cand-1.diff", "cat ../../../records/direct_task/run-2/state/x",
             f"cat {records}/record.json", "cat /elsewhere/pools/p1/records/mapping.json", f"ls {w}/records"]
    call(world, record, "".join(f"echo '{line}'\n" for line in lines))
    hits = prepare.scan(records, world.solution, home=world.tmp / "home")
    assert sorted((h["line"], h["pattern"]) for h in hits) == [
        (4, "records layout"), (4, "records root"), (5, "records layout"), (6, "records layout"), (6, "records root"),
        (7, "pool record files"), (8, "records root")]


def test_scan_counts_reads_of_other_sessions_transcripts(world):
    records, record = start(world, "direct_task")
    call(world, record, "echo 'cat ~/.claude/projects/-x/s.jsonl'")
    assert [h["pattern"] for h in prepare.scan(records, world.solution, home=world.tmp / "home")] == [
        "other sessions' files"]


def test_scan_matches_paths_written_under_the_home_directory(world):
    records, record = start(world, "direct_task")
    lines = ["~/main/specs", "$HOME/main-repl/x", "${HOME}/runtime/orchestrator", "main/specs"]
    call(world, record, "".join(f"echo '{line}'\n" for line in lines))
    hits = prepare.scan(records, world.solution, home=world.tmp)
    assert sorted((h["line"], h["pattern"]) for h in hits) == [
        (2, "main checkout prefix"), (3, "main checkout prefix"), (4, "frozen checkout")]


def test_scan_matches_the_records_root_written_under_the_home_directory(world):
    records, record = start(world, "direct_task")
    call(world, record, f"echo '~/{world.root.relative_to(world.outside)}/records'")
    hits = prepare.scan(records, world.solution, home=world.outside)
    assert [h["pattern"] for h in hits] == ["records root"]


def test_run_refuses_a_base_that_does_not_ignore_run_state(world):
    task = world.tmp / "task-no-ignore"
    write_task(task, world.base)
    (task / "seed" / ".gitignore").write_text("artifacts/\n")
    with pytest.raises(SystemExit, match="does not ignore .orchestrate/"):
        start(world, "direct_task", task=task)


def log_claude_argv(world, monkeypatch):
    """Make the stand-in claude CLI log its arguments, one call per line, before running its prompt."""
    log = world.outside / "claude-argv.log"
    (world.fakebin / "claude").write_text('#!/bin/sh\necho "$*" >> "$CLAUDE_ARGV_LOG"\nexec bash -c "$(cat)"\n')
    monkeypatch.setenv("CLAUDE_ARGV_LOG", str(log))
    return log


def test_claude_without_a_model_runs_opus_at_the_top_and_when_nested(world, monkeypatch):
    log = log_claude_argv(world, monkeypatch)
    _, record = start(world, "direct_task")
    assert call(world, record, "claude -p nested </dev/null").returncode == 0
    assert log.read_text().splitlines() == ["--model claude-opus-5-5 -p", "--model claude-opus-5-5 -p nested"]


@pytest.mark.parametrize("model", ["--model fable", "--model=claude-fable-5-1"])
def test_nested_claude_asking_for_fable_is_refused_before_the_cli_runs(world, monkeypatch, model):
    log = log_claude_argv(world, monkeypatch)
    _, record = start(world, "direct_task")
    done = call(world, record, f"claude {model} -p nested </dev/null; echo nested-exit=$?")
    assert (log.read_text().splitlines(), "nested-exit=2" in done.stdout) == (["--model claude-opus-5-5 -p"], True)


@pytest.mark.parametrize("fallback", ["--model opus --fallback-model fable",
                                      "--fallback-model=claude-sonnet-5-5,claude-fable-5-1"])
def test_nested_claude_with_a_fable_fallback_is_refused_before_the_cli_runs(world, monkeypatch, fallback):
    log = log_claude_argv(world, monkeypatch)
    _, record = start(world, "direct_task")
    done = call(world, record, f"claude {fallback} -p nested </dev/null; echo nested-exit=$?")
    assert (log.read_text().splitlines(), "nested-exit=2" in done.stdout) == (["--model claude-opus-5-5 -p"], True)


def test_a_fallback_model_alone_still_gets_opus_as_the_model(world, monkeypatch):
    log = log_claude_argv(world, monkeypatch)
    _, record = start(world, "direct_task")
    call(world, record, "claude --fallback-model claude-sonnet-5-5 -p nested </dev/null")
    assert log.read_text().splitlines()[1] == "--model claude-opus-5-5 --fallback-model claude-sonnet-5-5 -p nested"


def test_a_top_level_fable_call_is_refused_and_still_recorded(world, monkeypatch):
    log = log_claude_argv(world, monkeypatch)
    records, record = start(world, "direct_task")
    done = call(world, record, "echo agent-ran", args=("--model", "claude-fable-5-1", "-p"))
    assert (done.returncode, "agent-ran" in done.stdout, log.exists(), (records / "calls/1/prompt.txt").is_file()) == (
        2, False, False, True)


def test_nested_claude_keeps_an_explicit_other_model(world, monkeypatch):
    log = log_claude_argv(world, monkeypatch)
    _, record = start(world, "direct_task")
    call(world, record, "claude --model claude-sonnet-5-5 -p nested </dev/null")
    assert log.read_text().splitlines()[1] == "--model claude-sonnet-5-5 -p nested"


def test_claude_started_by_a_codex_agent_runs_opus(world, monkeypatch):
    log = log_claude_argv(world, monkeypatch)
    _, record = start(world, "direct_task")
    assert call(world, record, "claude -p nested </dev/null", binary="codex").returncode == 0
    assert log.read_text().splitlines() == ["--model claude-opus-5-5 -p nested"]


def test_parallel_calls_in_one_tree_all_run_through_the_guard(world, monkeypatch):
    log = log_claude_argv(world, monkeypatch)
    _, record = start(world, "direct_task")
    with ThreadPoolExecutor(8) as pool:
        done = list(pool.map(lambda k: call(world, record, f"claude -p nested-{k} </dev/null"), range(16)))
    nested = sorted(line for line in log.read_text().splitlines() if "nested" in line)
    assert ([d.returncode for d in done], nested, sorted(p.name for p in (Path(record["tree"]) / ".model-guard").iterdir())) == (
        [0] * 16, sorted(f"--model claude-opus-5-5 -p nested-{k}" for k in range(16)), ["claude"])


def test_an_edited_guard_is_restored_by_the_next_call(world, monkeypatch):
    log = log_claude_argv(world, monkeypatch)
    _, record = start(world, "direct_task")
    call(world, record, "true")
    edited = Path(record["tree"]) / ".model-guard" / "claude"
    edited.write_text(f'#!/bin/sh\nexec {world.fakebin}/claude "$@"\n')
    call(world, record, "claude -p nested </dev/null")
    assert log.read_text().splitlines()[-1] == "--model claude-opus-5-5 -p nested"


def model_session(home, directory, model):
    """A Claude CLI session file of `directory` holding one assistant message from `model`."""
    slug = "".join(c if c.isalnum() else "-" for c in str(directory))
    jsonl(home / ".claude/projects" / slug / f"{model}.jsonl",
          [{"type": "assistant", "message": {"model": model, "content": [{"type": "text", "text": "OK"}]}}])


def test_scan_flags_fable_answers_in_a_nested_session_of_the_tree(world):
    records, record = start(world, "direct_task")
    call(world, record, "true")
    home = world.tmp / "home"
    nested = Path(record["tree"]) / "tmp/pytest-of-u/pytest-0/probe0"
    model_session(home, nested, "claude-fable-5-1")
    model_session(home, nested, "claude-opus-5-5")
    assert [(Path(h["file"]).name, h["pattern"]) for h in prepare.scan(records, world.solution, home=home)] == [
        ("claude-fable-5-1.jsonl", "Fable model")]


def test_printed_text_naming_a_fable_model_is_not_a_fable_answer(world):
    records, record = start(world, "direct_task")
    call(world, record, "echo 'assistant model: claude-fable-5-1'")
    assert prepare.scan(records, world.solution, home=world.tmp / "home") == []


def test_fable_model_use_cannot_be_cleared(world):
    records, record = start(world, "direct_task")
    call(world, record, "true")
    model_session(world.tmp / "home", record["tree"], "claude-fable-5-1")
    prepare.scan(records, world.solution, home=world.tmp / "home")
    with pytest.raises(SystemExit, match="Fable model"):
        prepare.adjudicate(records, "cleared", "a probe")


def test_scan_records_hits_without_a_verdict_and_adjudicate_records_one(world):
    records, _ = drive(world, "direct_task", ["echo github.com"], True)
    before = json.loads((records / "record.json").read_text())["scan"]["verdict"]
    prepare.adjudicate(records, "cleared", "printed by a test fixture")
    after = json.loads((records / "record.json").read_text())["scan"]["verdict"]
    assert (before, after) == (None, {"verdict": "cleared", "reason": "printed by a test fixture", "hits": 1})


def test_control_differs_from_the_library_file_by_its_time_limit_only():
    library = (REPO / "workflows/library/control/direct_task.orc").read_text().splitlines()
    control = (REPO / "experiments/compare/control/direct_task.orc").read_text().splitlines()
    added = [line for line in control if line not in library]
    assert ([line.strip() for line in added], [line for line in control if line not in added]) == (
        [":timeout-sec 14400"], library)


def test_existing_arms_layout_unchanged(world):
    records, record = start(world, "reviewed_change")
    rt, cand, tree = world.runtime, record["candidates"][0], Path(record["tree"])
    wf = rt / "experiments/orc_vs_single_call/workflows"
    prefix = (f"cd {cand} && env PYTHONPATH={rt} COMPARE_ROOT={records} COMPARE_TREE={tree} "
              f"COMPARE_BASE={record['compare_base']} TMPDIR={tree / 'tmp'} "
              f'PATH={rt / "experiments/compare/shim"}:"$PATH" {sys.executable} -P -m orchestrator ')
    assert ((records / "command.sh").read_text(), (records / "resume.sh").read_text(), record["arm_kind"],
            sorted(p.name for p in records.iterdir())) == (
        prefix + f"run {wf / 'reviewed_change.orc'} --entry-workflow reviewed_change::reviewed-change "
        f"--source-root {wf} --provider-externs-file {wf / 'reviewed_change.providers.json'} "
        f"--input-file {records / 'inputs.json'}\n", prefix + 'resume "$1"\n', "orc",
        ["command.sh", "inputs.json", "record.json", "resume.sh"])


def candidate_root(world):
    root = world.outside / "archive" / "c1"
    for name in ("main.orc", "providers.json", "commands.json"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("{}\n")
    return root


def candidate_spec(world, root, **extra):
    return prepare.ArmSpec(source=root / "main.orc", entry="main::run", source_root=root,
                           providers=root / "providers.json", inputs=("task", "intent", "repo"), **extra)


def test_candidate_root_spec_builds_command_with_its_own_source_root_and_state_dir(world, capsys):
    root, state = candidate_root(world), world.outside / "evidence" / "runs" / "e1"
    spec = candidate_spec(world, root, state_dir=state, command_boundaries=root / "commands.json")
    records = prepare.run_arm(world.task, "candidate", world.root, world.runtime, spec=spec)
    record = json.loads((records / "record.json").read_text())
    seen, resumed = execute(capsys.readouterr().out), execute(f"bash {records / 'resume.sh'} R1")
    assert (seen["cwd"], seen["argv"], resumed["argv"], record["state_root"], record["arm_kind"],
            sorted(json.loads((records / "inputs.json").read_text()))) == (
        record["candidates"][0],
        ["run", str(root / "main.orc"), "--entry-workflow", "main::run", "--source-root", str(root),
         "--provider-externs-file", str(root / "providers.json"), "--input-file", str(records / "inputs.json"),
         "--state-dir", str(state), "--command-boundaries-file", str(root / "commands.json")],
        ["resume", "R1", "--state-dir", str(state)], str(state), "orc", ["intent", "repo", "task"])


@pytest.mark.parametrize("where, message", [("main", "main checkout prefix"), ("work", "inside the work root")])
def test_candidate_root_spec_refuses_a_root_where_the_runtime_is_refused(world, where, message):
    root = {"main": world.tmp / "main-candidates" / "c1", "work": world.root / "c1"}[where]
    root.mkdir(parents=True)
    with pytest.raises(SystemExit, match=message):
        prepare.run_arm(world.task, "candidate", world.root, world.runtime, spec=candidate_spec(world, root))


def test_generic_command_arm_runs_behind_shims_and_records_arm_kind(world, capsys):
    script = 'printf "%s\\n" "$PWD" "$0" "$COMPARE_BASE" "$TMPDIR"; echo "echo agent-called" | claude -p'
    spec = candidate_spec(world, candidate_root(world), command=("bash", "-c", script))
    records = prepare.run_arm(world.task, "control", world.root, world.runtime, spec=spec)
    record = json.loads((records / "record.json").read_text())
    shutil.copytree(REPO / "experiments/compare/shim", world.runtime / "experiments/compare/shim")  # untracked
    done = subprocess.run(["bash", "-c", capsys.readouterr().out], capture_output=True, text=True,
                          env={**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}"})
    assert (done.stdout.splitlines()[:4], (records / "calls/1/stdout.txt").read_text().splitlines()[-1],
            record["arm_kind"]) == (
        [record["candidates"][0], str(records / "inputs.json"), record["compare_base"],
         str(Path(record["tree"]) / "tmp")], "agent-called", "generic-command")


def test_scan_flags_archive_lineage_and_holdout_roots(world, monkeypatch):
    records, record = start(world, "direct_task")
    archive, lineage = world.outside / "evidence" / "candidates", world.outside / "evidence" / "log.jsonl"
    holdouts = [world.outside / "holdout-a", world.outside / "holdout-b"]
    lines = [f"ls {archive}/c1", f"cat {lineage}", f"ls {holdouts[0]}", f"ls {holdouts[1]}/t", "ls elsewhere"]
    call(world, record, "".join(f"echo '{line}'\n" for line in lines))
    monkeypatch.setenv("HOME", str(world.tmp / "home"))
    prepare.main(["scan", "--run", str(records), "--hash", world.solution, "--root", f"archive={archive}",
                  "--root", f"lineage={lineage}", *(f"--root=holdout={h}" for h in holdouts)])
    hits = json.loads((records / "record.json").read_text())["scan"]["hits"]
    assert sorted((h["line"], h["pattern"]) for h in hits) == [
        (2, "archive"), (3, "lineage"), (4, "holdout"), (5, "holdout")]
