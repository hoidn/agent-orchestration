from tests.experiments.orc_structural_search_support import launch_config
"""Mutator isolation: the shims mask the evidence root, sibling episodes and the work root's evaluation
directories from an episode's sandboxed CLI calls (scripted mutator and CLI; no provider is called)."""

import sys
from pathlib import Path

import pytest

from experiments.orc_structural_search.driver import archive, hidden_roots, run_episode
from tests.experiments.orc_structural_search_support import world  # noqa: F401 (fixture)
from tests.experiments.test_orc_structural_search_driver import (  # noqa: F401 (sandboxed: fixture)
    MUTATOR_ONE_CALL, config_of, fake_claude, mode1, sandboxed)


def test_a_mutator_cannot_read_a_siblings_file_or_the_evidence_root(sandboxed, world):
    work, evidence = world.outside / "work", world.evidence  # both outside the sandbox's private /tmp
    sibling = work / "episodes" / "episode-0" / "cand-1" / "direct.orc"
    sibling.parent.mkdir(parents=True)
    sibling.write_text("sibling-edit\n")
    _, parent = archive(world.candidate, evidence, world.runtime)
    (evidence / "log.jsonl").write_text('{"kind": "evidence-row"}\n')
    reads = f"{sibling} {evidence / 'log.jsonl'} direct.orc ../py/orchestrator/__init__.py"
    env = fake_claude(world, f"#!/bin/sh\ncat {reads} 2>/dev/null\nexit 0\n")
    (world.outside / "mutator.py").write_text(MUTATOR_ONE_CALL)
    row = run_episode(parent, launch_config(world, config_of()), interface="I1", mode="unguided", episode_index=1, work_root=work,
                      agent_cmd=[sys.executable, "-I", str(world.outside / "mutator.py")], evidence_root=evidence,
                      runtime=world.runtime, env=env, solutions={world.task.name: world.solution}, call_cap=160, criterion=world.criterion)
    out = (evidence / "episodes" / row["episode_id"] / "calls" / "1" / "stdout.txt").read_text()
    names = ("episodes", "records", "runs", "agents", "env-manifests")
    assert ((parent / "direct.orc").read_text() in out, "__version__" in out, "sibling-edit" in out,
            "evidence-row" in out, row["hidden_roots"], row["outcome"] != "incident") == (
        True, True, False, False, [str(evidence.resolve()), *(str(work.resolve() / name) for name in names)], True)


def test_hide_paths_from_the_command_line_reach_the_episode(sandboxed, world):
    hidden = world.outside / "other-run"
    hidden.mkdir()
    _, rows, _ = mode1(world, ["direct"], hide=[hidden])
    assert [str(hidden) in row["hidden_roots"] for row in rows if row["kind"] == "episode"] == [True] * 3


def test_hidden_roots_are_absolute_whatever_the_operator_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "other" / "run").mkdir(parents=True)
    roots = hidden_roots(Path("w"), Path("e"), hide=[Path("other/run")])
    assert all(root.is_absolute() for root in roots) and tmp_path / "other" / "run" in roots


def test_a_hide_path_that_does_not_exist_is_refused_and_never_created(tmp_path):
    with pytest.raises(ValueError, match="not an existing directory"):
        hidden_roots(tmp_path / "w", tmp_path / "e", hide=[tmp_path / "ss-evidnce2"])
    assert not (tmp_path / "ss-evidnce2").exists()


def test_qualified_episode_masks_external_truth_and_scans_read_attempts(sandboxed, world):
    from tests.experiments.qualification_support import qualified
    from tests.experiments.test_orc_structural_search_driver import episode
    q = qualified(world.outside / 'qualification', runtime=world.runtime, tasks=[world.task])
    world.criterion = q.criterion
    rule = Path(__file__).resolve().parents[2] / 'experiments/compare/criteria/calibration.json'
    score = rule.parent.parent / 'score.orc'
    env = fake_claude(world, f'#!/bin/sh\nfor denied in {q.receipt} {q.calibration} {rule} {score}; do\n'
                             '  if test -r "$denied"; then exit 91; fi\ndone\n'
                             'cat direct.orc ../py/orchestrator/__init__.py\n'
                             f'echo "cat {q.receipt}"\nexit 0\n')
    check_brief = f'assert {str(q.receipt)!r} not in Path("EPISODE.md").read_text()\n'
    mutator = MUTATOR_ONE_CALL.replace('subprocess.run(', check_brief + 'subprocess.run(', 1)
    row, evidence = episode(world, mutator, config_of(), env=env)
    records = evidence / 'episodes' / row['episode_id']
    output = (records / 'calls/1/stdout.txt').read_text()
    assert row['outcome'] == 'accepted' and row['scan_hits'] > 0
    assert str(q.receipt.parent) in row['hidden_roots']
    assert 'orc-structural-qualification-v1' not in output and 'calibration_kind' not in output
    assert (world.candidate / 'direct.orc').read_text() in output and '__version__' in output
    assert row['agent_exit'] == 0
    import json
    scan = json.loads((records / 'record.json').read_text())['scan']
    assert any(hit['pattern'] == 'qualification' for hit in scan['hits'])


def test_qualified_evaluation_and_resume_keep_truth_masked_and_rescan_history(sandboxed, world):
    import json
    from experiments.orc_structural_search.evaluation import resume
    from tests.experiments.qualification_support import qualified
    from tests.experiments.orc_structural_search_support import SCRIPTED, script
    from tests.experiments.test_orc_structural_search_evaluation import run, HANG, CHANGE, KILL_AFTER_SEC
    q = qualified(world.outside / 'qualification', runtime=world.runtime, tasks=[world.task])
    world.criterion = q.criterion
    probe = (f'import subprocess\nsubprocess.run(["cat", {str(q.receipt)!r}], check=False)\n'
             f'print("cat {q.receipt}", flush=True)\n')
    (world.fakebin / 'claude').write_text(SCRIPTED.replace('prompt = sys.stdin.read()\n',
                                                        'prompt = sys.stdin.read()\n' + probe))
    script(world, [HANG])
    first, env = run(world, timeout_sec=KILL_AFTER_SEC)
    metadata = json.loads((first.records_dir / 'record.json').read_text())
    assert first.outcome == 'incident' and metadata['qualification_scan']['error']
    assert metadata['qualification_scan']['hits'] == 'unavailable'
    assert str(q.receipt.parent) in metadata['qualification_private_roots']
    inputs = (first.records_dir / 'inputs.json').read_text()
    assert str(q.receipt) not in inputs and 'orc-structural-qualification-v1' not in inputs
    metadata['scan'] = {'calls': 1, 'hits': [], 'verdict': {'verdict': 'cleared', 'reason': 'old'}}
    (first.records_dir / 'record.json').write_text(json.dumps(metadata))
    script(world, [CHANGE])
    final = resume(first, env=env, timeout_sec=600, criterion=q.criterion)
    metadata = json.loads((final.records_dir / 'record.json').read_text())
    from experiments.orc_structural_search.evaluation import _classify
    assert _classify(final.state_dir, generic=False)[1] == 'completed'
    assert final.outcome == 'incident' and final.resume_count == 1
    assert final.qualification['qualification_sha256'] == first.qualification['qualification_sha256']
    assert metadata['qualification_scan']['calls'] == 2 and metadata['qualification_scan']['error']
    from experiments.compare import prepare
    with pytest.raises(SystemExit, match='publication'):
        prepare.collect(final.records_dir)
    assert 'scan' not in metadata
    outputs = ''.join(path.read_text() for path in (final.records_dir / 'calls').glob('*/stdout.txt'))
    assert 'orc-structural-qualification-v1' not in outputs
