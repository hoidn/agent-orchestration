"""Comparison harness, run side (experiments/compare): candidates, layout, commands, shim, collect, scan.

Behaviour on temporary git repositories with a stand-in agent CLI; see compare_harness_support.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from experiments.compare import prepare
from tests.experiments.compare_harness_support import (  # noqa: F401 (world is a fixture)
    READY, REPO, call, drive, edit, git, selects, start, world, write_memo,
)


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


def test_agents_trees_sit_under_a_parent_agents_cannot_list(world):
    _, record = start(world, "best_of_n", candidates=2)
    tree = Path(record["tree"])
    with pytest.raises(PermissionError):
        os.listdir(world.root / "agents")
    assert (tree.parent, len(tree.name), sorted(p.name for p in tree.iterdir())) == (
        world.root.resolve() / "agents", 16, ["cand-1", "cand-2", "tmp"])


def test_bookkeeping_lives_in_the_records_directory_not_in_the_agents_tree(world):
    records, record = drive(world, "direct_task", [edit("$PWD", "a + b")], True)
    assert (records.parent, sorted(p.name for p in Path(record["tree"]).iterdir()),
            sorted(p.name for p in records.iterdir())) == (
        world.root.resolve() / "records" / "direct_task", ["cand-1", "tmp"],
        ["calls", "collected", "command.sh", "inputs.json", "record.json", "resume.sh", "state"])


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
         "--input-file", str(records / "inputs.json"), "--state-dir", str(records / "state")])


def test_resume_script_resumes_with_the_runs_state_directory(world):
    records, record = start(world, "best_of_n", candidates=2)
    seen = execute(f"bash {records / 'resume.sh'} 20261014T000000Z-abc")
    assert (seen["cwd"], seen["argv"]) == (
        record["tree"], ["resume", "20261014T000000Z-abc", "--state-dir", str(records / "state")])


def test_shim_forwards_to_the_real_cli_without_pythonpath(world):
    _, record = start(world, "direct_task")
    done = call(world, record, "echo agent-said-hello; exit 3", binary="codex")
    assert (done.returncode, "agent-said-hello" in done.stdout, "PYTHONPATH=unset" in done.stdout) == (3, True, True)


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
