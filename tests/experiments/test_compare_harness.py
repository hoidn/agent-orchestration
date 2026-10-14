"""Behaviour of the comparison harness (experiments/compare): candidates, shim, collect, scan, pool, summarize.

Everything runs on temporary git repositories with a stand-in agent that executes its
prompt as a shell script; no provider is called.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.compare import prepare, summarize

REPO = Path(__file__).resolve().parents[2]
SHIM = REPO / "experiments" / "compare" / "shim"
UPSTREAM = (
    "diff --git a/pkg/calc.py b/pkg/calc.py\n--- a/pkg/calc.py\n+++ b/pkg/calc.py\n"
    "@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"
)
SYMPTOM = (
    "diff --git a/pkg/calc.py b/pkg/calc.py\n--- a/pkg/calc.py\n+++ b/pkg/calc.py\n"
    "@@ -1,2 +1,4 @@\n def add(a, b):\n+    if (a, b) == (2, 3):\n+        return 5\n     return a - b\n"
)
RUNTIME_MAIN = (  # the frozen runtime's stand-in orchestrator: reports where and how it was started
    "import json, os, sys\nprint(json.dumps({'main': __file__, 'cwd': os.getcwd(), 'argv': sys.argv[1:],"
    " 'path0': os.environ['PATH'].split(':')[0], 'env': {k: os.environ.get(k) for k in"
    " ('PYTHONPATH', 'COMPARE_ROOT', 'COMPARE_BASE', 'TMPDIR')}}))\n"
)
HIDDEN_TEST = (
    "from pkg.calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n\n\n"
    "def test_zero():\n    assert add(0, 0) == 0\n"
)


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(repo, files, message):
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def write_task(task, base, *, anchors=True, hidden=False):
    files = {"task.txt": "Make add correct.\n", "intent.txt": "add returns the sum.\n", "base_commit": base,
             "seed/bugs/report.md": "add(2, 3) returns -1\n"}
    files |= {"anchors/upstream.diff": UPSTREAM, "anchors/symptom.diff": SYMPTOM} if anchors else {}
    files |= {"hidden/tests/test_hidden.py": HIDDEN_TEST, "hidden_tests.txt": "".join(
        f"tests/test_hidden.py::test_{name}\n" for name in ("add", "zero", "missing"))} if hidden else {}
    for name, text in files.items():
        (task / name).parent.mkdir(parents=True, exist_ok=True)
        (task / name).write_text(text)


@pytest.fixture
def world(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q")
    old = commit(main, {"README.md": "toy\n", ".gitignore": ".orchestrate/\nartifacts/\n"}, "old")
    base = commit(main, {"pkg/__init__.py": "", "pkg/calc.py": "def add(a, b):\n    return a - b\n",
                         "orchestrator/__init__.py": "", "orchestrator/__main__.py": "print('candidate')\n"}, "base")
    solution = commit(main, {"pkg/calc.py": "def add(a, b):\n    return a + b\n",
                             "orchestrator/__main__.py": RUNTIME_MAIN}, "solution")
    runtime = tmp_path / "runtime"
    git(main, "worktree", "add", "-q", "--detach", str(runtime), solution)
    task = tmp_path / "task"
    write_task(task, base[:10] + "\n")
    criterion = tmp_path / "criterion.json"
    criterion.write_text(json.dumps({
        "primary": [{"measure": "best_of_n.group_gain_mean", "op": ">=", "value": 0.75}],
        "secondary": [{"measure": "best_of_n.paired_gain_mean", "op": ">=", "value": 0}],
    }))
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    for name in ("claude", "codex"):
        (fakebin / name).write_text('#!/bin/sh\necho "PYTHONPATH=${PYTHONPATH-unset}"\nexec bash -c "$(cat)"\n')
        (fakebin / name).chmod(0o755)
    return SimpleNamespace(
        tmp=tmp_path, main=main, old=old, base=base, solution=solution, runtime=runtime,
        task=task, criterion=criterion, fakebin=fakebin, root=tmp_path / "main-evidence",
    )


def start(world, arm, candidates=None, sets=(), task=None):
    sets = sets or {
        "design_review_execute": ("planner_model=p", "reviewer_model=r"),
        "direct_task": ("model=m", "effort=high"),
    }.get(arm, ())
    run = prepare.run_arm(task or world.task, arm, world.root, world.runtime, candidates, sets)
    return run, json.loads((run / "record.json").read_text())


def call(world, record, script, binary="claude"):
    env = {
        **os.environ, "PATH": f"{SHIM}:{world.fakebin}:{os.environ['PATH']}",
        "COMPARE_ROOT": str(Path(record["candidates"][0]).parent),
        "COMPARE_BASE": record["compare_base"], "PYTHONPATH": str(world.runtime),
    }
    return subprocess.run(
        [str(SHIM / binary), "-p"], input=script, text=True, capture_output=True,
        cwd=record["cwd"], env=env,
    )


def write_memo(record, prompts, value, outcome="completed"):
    rows = []
    for index, prompt in enumerate(prompts):
        identity = f"workflow / effect {index}"
        digest = "sha256:" + hashlib.sha256(prompt.encode()).hexdigest()
        rows.append({"record": "started", "identity": identity, "attempt": 1, "time": 100.0 + index,
                     "input_parts": {"prompt": digest}})
        rows.append({"record": "committed", "identity": identity, "attempt": 1, "effect_class": "provider",
                     "value": {}, "time": 101.0 + index})
    terminal = {"record": "terminal", "outcome": outcome}
    terminal.update({"value": value} if outcome == "completed" else {"code": "provider_timeout", "message": "t"})
    rows.append(terminal)
    memo = Path(record["cwd"]) / ".orchestrate" / "runs" / "r1" / "memo.jsonl"
    memo.parent.mkdir(parents=True)
    memo.write_text("".join(json.dumps(row) + "\n" for row in rows))


def drive(world, arm, scripts, value, candidates=None, task=None, outcome="completed"):
    """Start a run, make each call through the shim, write its memo, collect and scan it."""
    run, record = start(world, arm, candidates, task=task)
    for script in scripts:
        assert call(world, record, script).returncode == 0
    write_memo(record, scripts, value(record) if callable(value) else value, outcome)
    collected = prepare.collect(run)
    prepare.scan(run, world.solution, home=world.tmp / "home")
    return run, collected


def selects(k):
    return lambda record: {"winner": record["candidates"][k - 1], "ranking": [], "report": "artifacts/review/r.md"}


READY = {"variant": "READY", "report": "artifacts/review/r.md", "rounds": 1}


def edit(cand, body, design=False):
    script = f"cd {cand} && printf 'def add(a, b):\\n    return {body}\\n' > pkg/calc.py && echo 'X = 1' > pkg/extra.py"
    return script + (" && mkdir -p docs/design && echo d > docs/design/plan.md\n" if design else "\n")


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
    run, _ = start(world, arm)
    assert set(json.loads((run / "inputs.json").read_text())) == fields


def test_repository_inputs_name_absolute_candidate_paths(world):
    bon, bon_record = start(world, "best_of_n", candidates=3)
    rc, rc_record = start(world, "reviewed_change")
    assert (json.loads((bon / "inputs.json").read_text())["repos"],
            json.loads((rc / "inputs.json").read_text())["repo"]) == (
        bon_record["candidates"], rc_record["candidates"][0])


def test_run_refuses_inputs_the_arm_does_not_take(world):
    with pytest.raises(SystemExit, match="model"):
        start(world, "direct_task", sets=("effort=high",))


def execute_printed(capsys):
    done = subprocess.run(["bash", "-c", capsys.readouterr().out], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_printed_command_runs_the_frozen_runtime_inside_the_candidate(world, capsys):
    run, record = start(world, "direct_task")
    rt, h = world.runtime, world.runtime / "experiments/compare"
    seen = execute_printed(capsys)
    assert (seen["main"], seen["cwd"], seen["path0"], seen["env"], seen["argv"]) == (
        str(rt / "orchestrator/__main__.py"), record["candidates"][0], str(h / "shim"),
        {"PYTHONPATH": str(rt), "COMPARE_ROOT": str(run), "COMPARE_BASE": record["compare_base"],
         "TMPDIR": str(run / "tmp")},
        ["run", str(h / "control/direct_task.orc"), "--entry-workflow", "control/direct_task::direct-task",
         "--source-root", str(h), "--provider-externs-file", str(h / "control/direct_task.providers.json"),
         "--input-file", str(run / "inputs.json")])


def test_best_of_n_runs_from_the_run_root(world, capsys):
    run, _ = start(world, "best_of_n", candidates=2)
    assert execute_printed(capsys)["cwd"] == str(run)


def test_shim_forwards_to_the_real_cli_without_pythonpath(world):
    _, record = start(world, "direct_task")
    done = call(world, record, "echo agent-said-hello; exit 3", binary="codex")
    assert (done.returncode, "agent-said-hello" in done.stdout, "PYTHONPATH=unset" in done.stdout) == (3, True, True)


def test_shim_records_each_call_with_a_patch_including_new_files(world):
    run, record = start(world, "direct_task")
    script = edit("$PWD", "a + b")
    call(world, record, script)
    call(world, record, "true")
    patch = (run / "calls/1/patch-cand-1.diff").read_text()
    assert ((run / "calls/1/prompt.txt").read_text(), "pkg/extra.py" in patch, "a + b" in patch,
            "bugs/report.md" in patch, sorted(p.name for p in (run / "calls").iterdir()),
            git(record["candidates"][0], "status", "--porcelain", "--", "pkg/extra.py")) == (
        script, True, True, False, ["1", "2"], "?? pkg/extra.py")


def test_collect_takes_each_best_of_n_candidate_from_its_own_call(world):
    scripts = [edit("$PWD/cand-1", "a + b"), edit("$PWD/cand-2", "b + a"), "echo n > $PWD/cand-1/selector.txt"]
    run, collected = drive(world, "best_of_n", scripts, selects(2), candidates=2)
    first, second = ((run / collected["patches"][f"cand-{k}"]).read_text() for k in (1, 2))
    assert (collected["selected"], collected["calls"], "b + a" in second, "b + a" in first,
            "selector.txt" in first) == ("cand-2", 3, True, False, False)


def test_collect_takes_first_and_final_patches_of_reviewed_change(world):
    scripts = [edit("$PWD", "a - b + 0"), "true", edit("$PWD", "a + b"), "true"]
    run, collected = drive(world, "reviewed_change", scripts, READY)
    assert ("a - b + 0" in (run / collected["patches"]["first"]).read_text(),
            "a + b" in (run / collected["patches"]["final"]).read_text(), collected["variant"]) == (
        True, True, "READY")


@pytest.mark.parametrize("memo_prompts, message", [(["true", "true"], "2 provider starts"), (["false"], "prompt")])
def test_collect_refuses_calls_that_do_not_pair_with_the_memo(world, memo_prompts, message):
    run, record = start(world, "direct_task")
    call(world, record, "true")
    write_memo(record, memo_prompts, True)
    with pytest.raises(SystemExit, match=message):
        prepare.collect(run)


def test_collect_records_a_failed_run_with_its_reason_and_no_patch(world):
    _, collected = drive(world, "direct_task", ["true"], None, outcome="failed")
    assert (collected["outcome"], collected["failure"]["code"], collected["patches"]) == (
        "failed", "provider_timeout", {})


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_scan_reports_each_hit_with_file_and_line(world):
    run, record = start(world, "direct_task")
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
    hits = prepare.scan(run, world.solution, home=home)
    assert sorted((Path(h["file"]).name, h["line"], h["pattern"]) for h in hits) == [
        ("rollout-a.jsonl", 2, "solution hash"), ("rollout-a.jsonl", 3, "frozen checkout"),
        ("s.jsonl", 2, "main checkout"), ("stdout.txt", 3, "gh"), ("stdout.txt", 4, "github.com"),
    ]


def test_scan_does_not_mistake_sibling_paths_for_the_main_checkout(world):
    run, record = start(world, "direct_task")
    call(world, record, f"echo {record['candidates'][0]}; echo going through the gate")
    assert prepare.scan(run, world.solution, home=world.tmp / "home") == []


@pytest.fixture
def pooled(world):
    """One best_of_n run (two candidates, the second with a design file), two reviewed_change runs
    (one whose final patch equals its first), one control run and one failed control run."""
    implement = edit("$PWD", "a + b")
    runs = [
        drive(world, "best_of_n", [edit("$PWD/cand-1", "a + b"), edit("$PWD/cand-2", "b + a", design=True),
                                   "true"], selects(2), candidates=2)[0],
        drive(world, "reviewed_change", [implement, "true", edit("$PWD", "a * 1 + b"), "true"], READY)[0],
        drive(world, "reviewed_change", [implement, "true"], READY)[0],
        drive(world, "direct_task", [edit("$PWD", "b + a")], True)[0],
        drive(world, "direct_task", ["true"], None, outcome="failed")[0],
    ]
    out = world.tmp / "pool"
    mapping = prepare.pool(world.task, world.criterion, out, ["judge-a", "judge-b"], runs)
    return SimpleNamespace(out=out, mapping=mapping, failed=runs[-1])


def test_pool_composes_batches_per_d4(pooled):  # each reviewed_change stage is drawn at random: two valid shapes
    clones, anchors = pooled.mapping["clones"], [("anchor", "symptom"), ("anchor", "upstream")]
    bon = [("best_of_n", "cand-1"), ("best_of_n", "cand-2"), ("direct_task", "final")]
    rc = "reviewed_change"
    same, first, final = (rc, "first", "final"), (rc, "first"), (rc, "final")
    shapes = sorted(sorted((clones[c]["arm"], *clones[c]["labels"]) for c in b) for b in pooled.mapping["batches"])
    assert shapes in [sorted(sorted(b + anchors) for b in (bon, [same, x], [y]))
                      for x, y in ((first, final), (final, first))]


def test_pool_strips_design_artifacts_and_records_the_removal(pooled):
    cid = next(cid for cid, c in pooled.mapping["clones"].items() if c["labels"] == ["cand-2"])
    clone = pooled.out / "clones" / cid
    assert (pooled.mapping["clones"][cid]["stripped"], (clone / "docs/design/plan.md").exists(),
            "pkg/extra.py" in git(clone, "diff", "--name-only")) == (["docs/design/plan.md"], False, True)


def test_pool_keeps_arms_and_stages_out_of_what_judges_see(pooled):
    inputs = (pooled.out / "score-inputs-judge-a.json").read_text().replace(str(pooled.out), "")
    names = [p.name for p in (pooled.out / "clones").iterdir()]
    words = ("best_of_n", "reviewed_change", "direct_task", "first", "final", "cand-", "anchor", "run-")
    assert [w for w in words if w in inputs or any(w in n for n in names)] == []


def test_pool_writes_one_complete_scoring_input_per_judge(pooled):
    inputs = {j: json.loads((pooled.out / f"score-inputs-{j}.json").read_text()) for j in ("judge-a", "judge-b")}
    ids = [sorted(Path(c).name for c in batch["clones"]) for batch in inputs["judge-a"]["batches"]]
    assert ({j: (i["judge_model"], i["criterion_sha256"]) for j, i in inputs.items()}, ids) == (
        {j: (j, prepare.sha256_file(pooled.out.parent / "criterion.json")) for j in inputs},
        [sorted(batch) for batch in pooled.mapping["batches"]])


def test_pool_refuses_an_unscanned_run(world):
    run, record = start(world, "direct_task")
    call(world, record, "true")
    write_memo(record, ["true"], True)
    prepare.collect(run)
    with pytest.raises(SystemExit, match="scanned"):
        prepare.pool(world.task, world.criterion, world.tmp / "pool", ["j"], [run])


def test_pool_excludes_a_run_with_scan_hits(world):
    dirty, _ = drive(world, "direct_task", ["echo github.com"], True)
    clean, _ = drive(world, "direct_task", ["true"], True)
    mapping = prepare.pool(world.task, world.criterion, world.tmp / "pool", ["j"], [dirty, clean])
    assert (mapping["runs"][str(dirty)]["excluded"].startswith("contamination"),
            sorted({c["run"] for c in mapping["clones"].values() if c["run"]})) == (True, [str(clean)])


def test_verify_pool_restores_a_clone_a_judge_changed(pooled, capsys):
    cid = next(iter(pooled.mapping["clones"]))
    clone = pooled.out / "clones" / cid
    recorded = prepare.patch_of(clone, pooled.mapping["compare_base"])
    (clone / "pkg/calc.py").write_text("broken\n")
    (clone / "notes.txt").write_text("judge notes\n")
    with pytest.raises(SystemExit):
        prepare.verify_pool(pooled.out)
    printed = capsys.readouterr().out
    assert (cid in printed, "notes.txt" in printed,
            prepare.patch_of(clone, pooled.mapping["compare_base"]) == recorded) == (True, True, True)
    prepare.verify_pool(pooled.out)


TOTALS = {  # (arm, label) -> per judge four tokens
    ("best_of_n", "cand-1"): ("S1",) * 4,
    ("best_of_n", "cand-2"): ("S2",) * 4,
    ("reviewed_change", "first"): ("S0",) * 4,
    ("reviewed_change", "final"): ("S2",) * 4,
    ("direct_task", "final"): ("S1",) * 4,
    ("anchor", "upstream"): ("S2",) * 4,
    ("anchor", "symptom"): ("S0",) * 4,
}


def rating(path, clone, judge):
    tokens = TOTALS[(clone["arm"], clone["labels"][-1])]
    if judge == "judge-b" and clone["arm"] == "direct_task":
        tokens = ("S2",) + tokens[1:]
    return dict(zip(("root_cause", "scope", "generality", "layering"), tokens), clone=path, reason="r")


def score(out, judge, mapping, *, tamper=None, sha=None):
    inputs = json.loads((out / f"score-inputs-{judge}.json").read_text())
    value = [[rating(path, mapping["clones"][Path(path).name], judge) for path in batch["clones"]]
             for batch in inputs["batches"]]
    if tamper:
        tamper(value)
    if sha:
        inputs["criterion_sha256"] = sha
    run = out / "clones" / ".orchestrate" / "runs" / judge
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"bound_inputs": inputs}))
    (run / "memo.jsonl").write_text(json.dumps({"outcome": "completed", "record": "terminal", "value": value}) + "\n")


@pytest.fixture
def results(pooled, world):
    for judge in ("judge-a", "judge-b"):
        score(pooled.out, judge, pooled.mapping)
    return summarize.summarize(pooled.out, world.criterion)


def test_summarize_joins_ratings_by_position_and_computes_measures(results):
    m = results["measures"]
    assert (m["best_of_n.mean"], m["best_of_n.paired_gain_mean"], m["best_of_n.group_gain_mean"],
            m["best_of_n.minus_control"], m["reviewed_change.paired_gain_mean"],
            m["reviewed_change.paired_gain_runs_negative"], results["verdict"]["primary"][0]["met"]) == (
        8, 4, 2, 3.5, 4, 0, True)


def test_summarize_counts_exact_agreement_per_criterion(results, pooled):
    n = len(pooled.mapping["clones"])
    assert results["agreement"] == {"root_cause": {"agree": n - 1, "of": n}, "scope": {"agree": n, "of": n},
                                    "generality": {"agree": n, "of": n}, "layering": {"agree": n, "of": n}}


def test_summarize_reports_anchor_scores_per_batch_and_judge(results):
    assert sorted((a["batch"], a["anchor"], a["judge"], a["total"]) for a in results["anchors"]) == sorted(
        (i, name, judge, total) for i in range(3) for judge in ("judge-a", "judge-b")
        for name, total in (("upstream", 8), ("symptom", 0)))


def test_failed_runs_are_listed_with_their_reason_and_never_pooled(results, pooled):
    row = next(row for row in results["runs"] if row["run"] == str(pooled.failed))
    assert (row["outcome"], row["failure"]["code"], row["value"], row["scores"]) == (
        "failed", "provider_timeout", None, {})


def test_summarize_refuses_a_batch_with_a_missing_rating(pooled, world):
    score(pooled.out, "judge-a", pooled.mapping, tamper=lambda value: value[1].pop())
    with pytest.raises(SystemExit, match="batch 1"):
        summarize.summarize(pooled.out, world.criterion)


def test_summarize_refuses_a_copied_back_id_that_disagrees_with_its_position(pooled, world):
    def swap(value):
        value[0][0]["clone"], value[0][1]["clone"] = value[0][1]["clone"], value[0][0]["clone"]
    score(pooled.out, "judge-a", pooled.mapping, tamper=swap)
    with pytest.raises(SystemExit, match="batch 0 position 0"):
        summarize.summarize(pooled.out, world.criterion)


def test_summarize_refuses_a_scoring_run_bound_to_another_criterion(pooled, world):
    score(pooled.out, "judge-a", pooled.mapping, sha="0" * 64)
    with pytest.raises(SystemExit, match=f"{'0' * 64}.*{prepare.sha256_file(world.criterion)}"):
        summarize.summarize(pooled.out, world.criterion)


def test_summarize_runs_hidden_acceptance_in_an_untouched_copy_of_each_clone(world):
    task = world.tmp / "task-hidden"
    write_task(task, world.base, anchors=False, hidden=True)
    own_test = "mkdir -p tests && printf 'def test_missing():\\n    pass\\n' > tests/test_hidden.py"
    run, _ = drive(world, "direct_task", [edit("$PWD", "a + b") + own_test], True, task=task)
    out = world.tmp / "pool-hidden"
    mapping = prepare.pool(task, world.criterion, out, ["judge-a"], [run])
    score(out, "judge-a", mapping)
    results = summarize.summarize(out, world.criterion)
    prepare.verify_pool(out)
    assert results["measures"]["direct_task.hidden_mean"] == pytest.approx(2 / 3)


def test_control_differs_from_the_library_file_by_its_time_limit_only():
    library = (REPO / "workflows/library/control/direct_task.orc").read_text().splitlines()
    control = (REPO / "experiments/compare/control/direct_task.orc").read_text().splitlines()
    added = [line for line in control if line not in library]
    assert ([line.strip() for line in added], [line for line in control if line not in added]) == (
        [":timeout-sec 14400"], library)
