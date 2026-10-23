"""Fixtures for the structural search evaluation tests: scripted `claude`/`codex` and a tiny task package.

The scripted executables stand in for the real CLIs behind the comparison-harness shims (no provider is
called). Each reads its prompt on stdin, takes the first entry of the JSON list in $SCRIPTED_RESULTS_FILE
whose `match` substring occurs in the prompt, sleeps its `sleep` seconds (default 0), prints its `print` text (default
none) and either writes its `result` (JSON) to
the file on the prompt's last `- path:` line (the shims hide $ORCHESTRATOR_OUTPUT_BUNDLE_PATH) or, with `exit`, exits
with that status without writing anything.
They are named `claude` and `codex` because the provider templates run those names.

The runtime is a detached worktree of a shared clone of this checkout's HEAD (the real orchestrator,
committed and clean; `run_arm` refuses a runtime that is its own main checkout) into which the task
repository's solution commit and its parent, the base commit, are fetched, so `run_arm` can resolve and fetch
the base and the driver can check the operator's solution hash.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.orc_structural_search.config import ExperimentConfig
from tests.experiments.qualification_support import measure_free, sha
from tests.experiments.compare_harness_support import (
    OUTSIDE_SANDBOX_MOUNTS, commit, git, open_up, write_test_sandbox_config,
)

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "experiments" / "orc_structural_search" / "seeds"
_CAPPED_DIRECT = (SEEDS / 'direct.orc').read_text().replace('claude-sonnet-5-5', 'gpt-5.6-terra')
MUTATOR_STEPPING_STONE = f'''#!{sys.executable} -I
from pathlib import Path
entry = next(path for path in Path('.').glob('*.orc') if path.stem != 'common')
source = entry.read_text()
base = {_CAPPED_DIRECT!r}
if entry.stem != 'direct':
    base = base.replace('(defmodule direct)', '(defmodule ' + entry.stem + ')').replace('(Change Outcome)', '(Change CheckReport Outcome)')
start = base.index('(provider-result providers.coder')
end = base.index(':timeout-sec 5400)', start) + len(':timeout-sec 5400)')
call = base[start:end]
if 'helper-b' in source:
    record = '(defrecord CheckC (passed Bool) (failing List[String]) (excerpt String))\\n'
    source = base.replace('(defworkflow run', record + '  (defworkflow run')
    source = source.replace('((change ', '((check-c (command-result dev-check :argv ("python" "dev_check.py") :returns CheckC)) (change ')
    source = source.replace(call, '(if check-c.passed ' + call + ' ' + call + ')')
else:
    bindings = ' '.join('(b' + str(i) + ' ' + call + ')' for i in range(2))
    helper = '(defproc helper-b ((task String) (repo String)) -> Change :effects ((uses-provider providers.coder)) (let* (' + bindings + ') b' + str(len(bindings.split('(provider-result')) - 2) + '))\\n'
    source = base.replace(call, '(helper-b task repo)').replace('(defworkflow run', helper + '  (defworkflow run')
entry.write_text(source)
'''
MUTATOR_SAME_IDEA = f'''#!{sys.executable} -I
import sys
from pathlib import Path
base = {_CAPPED_DIRECT!r}
brief = Path('EPISODE.md').read_text()
entry = next(path for path in Path('.').glob('*.orc') if path.stem != 'common')
if entry.stem != 'direct':
    base = base.replace('(defmodule direct)', '(defmodule ' + entry.stem + ')').replace('(Change Outcome)', '(Change CheckReport Outcome)')
tried = any('control [if=1,' in line and 'check-gated no' in line for line in brief.splitlines())
condition = 'true' if '--deaf' in sys.argv or not tried else '(not false)'
if '--same-idea-new-skeleton' in sys.argv:
    condition = '(and true true)'
start = base.index('(provider-result providers.coder')
end = base.index(':timeout-sec 5400)', start) + len(':timeout-sec 5400)')
call = base[start:end]
entry.write_text(base.replace(call, '(if ' + condition + ' ' + call + ' (record Change :summary "skipped" :account "skipped"))'))
'''


@pytest.fixture
def synthetic_receipts(monkeypatch):
    """Complete Terra native metadata per scripted shim call; no provider activity."""
    import hashlib
    from experiments.orc_structural_search import metering
    def capture(records, **_context):
        usage = []
        paths = []
        for call in sorted((Path(records) / 'calls').glob('*')):
            native = call / 'synthetic-native.jsonl'
            native.write_text(json.dumps({'type': 'turn_context', 'payload': {'model': 'gpt-5.6-terra'}}) + '\n')
            paths.append(str(native))
            metadata = Path(records) / 'record.json'
            tokens = 200 if metadata.exists() and 'implement_check_diagnose_repair.orc' in metadata.read_text() else 100
            usage.append({'call_id': call.name, 'provider': 'codex', 'status': 'complete', 'reason': None,
                'usage': [{'model': 'gpt-5.6-terra', 'total_tokens': 120,
                    'charge_tokens': {'input': tokens, 'output': tokens // 5, 'cache_read': 0, 'cache_write': 0},
                    'provenance': {'complete_native_transcript': True, 'model_source': 'turn_context.model',
                        'session_sha256': 'sha256:' + hashlib.sha256(native.read_bytes()).hexdigest()}}]})
        return {'receipt_usage': usage, 'consumption': 'synthetic', 'native_session_paths': paths}
    monkeypatch.setattr(metering, 'receipts', capture)
    return capture
PYTHON_PARENT = REPO / "experiments" / "orc_structural_search" / "three_arm" / "python"  # the I3 parent
I3_CONFIG = ExperimentConfig(
    mutable_files=("direct.py",), mutable_definitions=("run",), condition="topology-only", interface="I3",
    entry_workflow="direct::run", source_root=".", providers_file="providers.json", command_boundaries_file=None,
    episode_wall_clock_sec=600, criterion_sha256=None)
SCRIPTED = f"""#!{sys.executable} -I
import json, os, re, sys, time
prompt = sys.stdin.read()
for entry in json.load(open(os.environ["SCRIPTED_RESULTS_FILE"])):
    if entry["match"] in prompt:
        break
else:
    sys.exit("scripted provider: no entry matches the prompt")
time.sleep(entry.get("sleep", 0))
print(entry.get("print", ""), flush=True)
if "exit" in entry:
    sys.exit(entry["exit"])
with open(re.findall(r"^- path: (.+)$", prompt, re.M)[-1], "w") as out:
    json.dump(entry["result"], out)
"""
DEV_CHECK = {"argv": [sys.executable, "-c", "import pkg"], "timeout_sec": 30}
# The scripted I1 mutator: reads the episode index from EPISODE.md's first line ("# Episode <n>") and edits
# direct.orc in its working directory. 0: wraps the coder call in an `if` on a literal (a structural child);
# 1: renames the `change` binding (a rename child, the parent's skeleton); 2: edits the import (refused).
MUTATOR = f"""#!{sys.executable} -I
import re
from pathlib import Path
index = int(re.match(r"# Episode (\\d+)", Path("EPISODE.md").read_text()).group(1))
edits = [
    [("(change (provider-result providers.coder", "(change (if true (provider-result providers.coder"),
     (":timeout-sec 5400)))", ':timeout-sec 5400) (record Change :summary "skipped" :account "skipped"))))')],
    [("(change (provider-result", "(result (provider-result"), ("change.summary", "result.summary")],
    [("(import common :only (Change Outcome))", "(import common :only (Change CheckReport Outcome))")],
][index]
source = Path("direct.orc").read_text()
for old, new in edits:
    assert source.count(old) == 1, old
    source = source.replace(old, new)
Path("direct.orc").write_text(source)
"""
# The scripted I2 mutator: reads the episode index and the site ("Site: <owner>@<file>:<line>:<column>") from
# EPISODE.md, replaces the form starting at the site and writes HYPOTHESIS.txt. 0: wraps the site's call in an `if`
# on a literal; 1: the same, and renames the `change` binding outside the site (scope_exceeded); 2: a call of a fresh
# `defproc` helper holding a planner call of the same type; 3: the string literal "x" (no manifest type).
MUTATOR_I2 = f"""#!{sys.executable} -I
import re
from pathlib import Path
brief = Path("EPISODE.md").read_text()
index = int(re.match(r"# Episode (\\d+)", brief).group(1))
name, line, column = re.search(r"^Site: .*@(.+):(\\d+):(\\d+)$", brief, re.M).groups()
source = Path(name).read_text()
start = sum(len(text) for text in source.splitlines(keepends=True)[:int(line) - 1]) + int(column) - 1
depth = 0
for end in range(start, len(source)):  # ponytail: the seeds' site forms hold no parenthesis inside a string
    depth += {{"(": 1, ")": -1}}.get(source[end], 0)
    if depth == 0:
        break
call = source[start:end + 1]
wrapped = f'(if true {{call}} (record Change :summary "skipped" :account "skipped"))'
helper = ("(defproc plan-change ((task String) (repo String)) -> Change\\n    :effects ((uses-provider providers.planner))"
          "\\n    (provider-result providers.planner :prompt (implement-prompt :task task :repo repo)"
          ' :model "claude-sonnet-5-5" :effort "medium" :timeout-sec 5400))\\n\\n  (defworkflow run')
replacement, extra = [
    (wrapped, []),
    (wrapped, [("(change ", "(result "), ("change.summary", "result.summary")]),
    ("(plan-change task repo)", [("(defworkflow run", helper)]),
    ('"x"', []),
][index]
source = source[:start] + replacement + source[end + 1:]
for old, new in extra:
    assert source.count(old) == 1, old
    source = source.replace(old, new)
Path(name).write_text(source)
Path("HYPOTHESIS.txt").write_text(f"episode {{index}} should do better\\nsecond line\\n")
"""


def python_pair(tmp_path: Path, *edits: tuple[str, str]) -> tuple[Path, Path]:
    """(parent, child): copies of the I3 parent; the child's direct.py with each (old, new) edit applied once."""
    parent, child = tmp_path / "parent", tmp_path / "child"
    for root in (parent, child):
        shutil.copytree(PYTHON_PARENT, root, ignore=shutil.ignore_patterns("__pycache__"))
    source = (child / "direct.py").read_text()
    for old, new in edits:
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    (child / "direct.py").write_text(source)
    return parent, child


@pytest.fixture
def pyright():
    if shutil.which("pyright") is None:
        pytest.skip("pyright is not on PATH")


def script(world, entries):
    """Make `entries` (match/result or match/exit) the scripted providers' answers."""
    world.results.write_text(json.dumps(entries))


def capped_copy(source, destination):
    """Copy launch fixtures under today's cap; captured source workflows stay unchanged."""
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__"))
    for path in destination.rglob("*"):
        if path.suffix in (".orc", ".py"):
            text = path.read_text().replace("claude-opus-5-5", "claude-sonnet-5-5")
            path.write_text(text.replace("gpt-6.1-sol", "gpt-5.6-terra").replace("gpt-6-sol", "gpt-5.6-terra"))


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A clean runtime clone holding a tiny task repository's base commit, its task package, the seed catalog
    as a candidate root, an evidence root and the scripted providers (all but the runtime, task and candidate
    outside the shims' sandbox mounts)."""
    task_repo = tmp_path / "task-repo"
    task_repo.mkdir()
    git(task_repo, "init", "-q")
    base = commit(task_repo, {".gitignore": ".orchestrate/\n", "pkg/__init__.py": "VALUE = 1\n",
                              "tests/test_base_visible.py": "def test_base_visible(): pass\n"}, "base")
    solution = commit(task_repo, {"pkg/__init__.py": "VALUE = 2\n"}, "solution")
    main, runtime = tmp_path / "main", tmp_path / "runtime"
    git(REPO, "clone", "-q", "--shared", "--no-checkout", str(REPO), str(main))
    git(main, "fetch", "-q", str(task_repo), solution)  # and its parent, the base
    git(main, "worktree", "add", "-q", "--detach", str(runtime), "HEAD")
    changed = []
    for relative in ('experiments/compare/shim/claude', 'experiments/compare/shim/model-guard',
                     'experiments/compare/sandbox.py', 'experiments/compare/codex-models-0.163.0.json'):
        source, destination = REPO / relative, runtime / relative
        if not destination.exists() or destination.read_bytes() != source.read_bytes():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            changed.append(relative)
    if changed:
        git(runtime, 'add', *changed)
        git(runtime, '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '-qm', 'fixture current comparison sandbox')
    task = tmp_path / "task-1"
    for name, text in {"task.txt": "Set VALUE to 2.\n", "intent.txt": "VALUE is 2.\n", "base_commit": base + "\n",
                       "seed/dev-check.json": json.dumps(DEV_CHECK)}.items():
        (task / name).parent.mkdir(parents=True, exist_ok=True)
        (task / name).write_text(text)
    candidate = tmp_path / "candidate"
    capped_copy(SEEDS, candidate)
    OUTSIDE_SANDBOX_MOUNTS.mkdir(parents=True, exist_ok=True)
    outside = Path(tempfile.mkdtemp(dir=OUTSIDE_SANDBOX_MOUNTS))
    fakebin = outside / "fakebin"
    fakebin.mkdir()
    for name in ("claude", "codex"):
        (fakebin / name).write_text(SCRIPTED)
        (fakebin / name).chmod(0o755)
    results = outside / "results.json"
    results.write_text("[]\n")
    sandbox_config = write_test_sandbox_config(fakebin, outside / "sandbox-dependencies.json",
                                                readonly_files=(results,),
                                                environment_names=("SCRIPTED_RESULTS_FILE",))
    empty_home = tmp_path / "empty-host-home"
    empty_home.mkdir()
    monkeypatch.setenv("COMPARE_SANDBOX", str(sandbox_config))
    monkeypatch.setenv("HOME", str(empty_home))
    monkeypatch.setenv("CODEX_HOME", str(empty_home / ".codex"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(empty_home / ".claude"))
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
                "CLAUDE_CODE_OAUTH_TOKEN_FILE"):
        monkeypatch.delenv(key, raising=False)
    criterion = measure_free(tmp_path, tasks=[task])
    yield SimpleNamespace(criterion=criterion, tmp=tmp_path, runtime=runtime, task=task, candidate=candidate, fakebin=fakebin, solution=solution,
                          results=results, evidence=outside / "evidence", outside=outside,
                          sandbox_config=sandbox_config, empty_home=empty_home)
    open_up(tmp_path)
    open_up(outside)
    shutil.rmtree(runtime)
    shutil.rmtree(main)
    shutil.rmtree(outside)


def launch_config(world, config):
    """Mechanics fixtures declare measure-free execution explicitly and bind its actual criterion bytes."""
    from dataclasses import replace
    return replace(config, criterion_sha256=sha(world.criterion))


def acquire_study(s, store_path):
    from experiments.orc_structural_search import campaign, records, readout_join
    from tests.experiments.test_orc_structural_search_campaign_loop import cli_args
    campaign.main(['warm-start', *cli_args(s, 'lifecycle-warm', store_path)])
    for declaration in s.frozen['campaigns']:
        args = ['run', *cli_args(s, 'lifecycle-' + declaration['policy'], store_path),
            '--label', declaration['label'], '--policy', declaration['policy'], '--generations', '2',
            '--episodes-per-generation', '4', '--run-seed', str(declaration['run_seed'])]
        campaign.main(args)
        campaign.main([*args, '--continue'])
    with_store = campaign.open_store(store_path, writer=False)
    try:
        headers = [row for row in with_store.rows('campaign') if row['policy'] != 'warm_start']
        ids = sorted(row['campaign_id'] for row in headers)
        reference = readout_join.warm_reference(with_store, headers[0], s.q.criterion)
        ceiling = 4 * reference['cost']
        checkpoint_bytes = {cid: records._checkpoint(with_store, cid)[0].read_bytes() for cid in ids}
    finally:
        with_store.close()
    return headers, ids, ceiling, checkpoint_bytes


def sealed_jobs(s, with_store, authorization, ids, store_path, sealed, validation, headers):
    from experiments.orc_structural_search import adaptive, driver
    from experiments.orc_structural_search.config import load_config
    subjects = {row['candidate_id']: row for row in with_store.rows('subject')}
    config = load_config(s.config)
    jobs = [(Path(subjects[cid]['source']), adaptive.subject_config(subjects[cid], config),
        {'mode': 'campaign', 'split': 'sealed', 'generation': -1, 'campaign_id': min(ids),
         'candidate_id': cid, 'candidate_root': subjects[cid]['source']}) for cid in authorization['candidate_ids']]
    launch = {key: value for key, value in s.launch.items() if key not in ('work_root', 'evidence_root', 'pools_root')}
    launch.update({key: Path(value) for key, value in authorization['sealed_roots'].items()})
    launch['work_root'], launch['evidence_root'] = driver.check_roots(launch['work_root'], launch['evidence_root'])
    launch['pools_root'].mkdir(parents=True, exist_ok=True)
    launch.update(resume=True, solutions={s.q.sealed.name: s.world.solution},
        holdouts=[s.q.validation, *s.common['adaptive_tasks']],
        scan_roots=[store_path, sealed / 'P', validation, *(Path(value) for header in headers for value in header['roots'].values())])
    return jobs, launch


def assess_sealed(s, store_path, ids, sealed, validation, headers, checkpoint_bytes):
    from experiments.orc_structural_search import campaign, records, readout_join
    from experiments.orc_structural_search import judging
    with_store = campaign.open_store(store_path, writer=True)
    try:
        authorization = next(row for row in with_store.rows('exposure') if row['role'] == 'sealed')
        jobs, launch = sealed_jobs(s, with_store, authorization, ids, store_path, sealed, validation, headers)
        judge = {'criterion': s.q.criterion, 'judges': s.common['judges']}
        for _ in range(2):
            judging.evaluate_and_judge(jobs, -1, [s.q.sealed], replicates=authorization['replicates'],
                                      launch=launch, judge=judge, include=lambda row: row.get('split') == 'sealed')
            verified = readout_join.final_pool(with_store, authorization, role='sealed')
            campaign.ingest(with_store, min(ids), authorization['context_key'], sealed / 'E',
                            [Path(verified['results'])], criterion=s.q.criterion)
        assert all(records._checkpoint(with_store, cid)[0].read_bytes() == checkpoint_bytes[cid] for cid in ids)
        assert {row['campaign_id'] for row in with_store.rows('trial') if row['split'] in ('validation', 'sealed')} == {min(ids)}
        assert all(row['clone_ids'] for row in with_store.rows('assessment'))
        with pytest.raises(ValueError, match='already'):
            campaign.open_sealed(with_store, ids, s.q.sealed)
        validation_manifest = records.study_manifest(with_store, ids)
        validation_results = readout_join.final_pool(with_store, validation_manifest, role='validation')['results']
        sealed_results = verified['results']
    finally:
        with_store.close()
    return validation_results, sealed_results
