"""Spike of evaluated execution, iteration 3, item C: an explicit continuation after a divergence.

Throwaway. Review 2, finding 7: after `effect_input_diverged` a resume stops, and the
design names no way on. `invalidate(run_root, identity)` appends an `invalidated` record
for the chosen effect and for every effect committed after it in the journal (the rule
the owner accepted after review 3, finding 1: a dependence through a file is not
recorded). With `follow="values"` it follows only the evaluator's value dependence,
recorded as `depends_on` in each commit: names, calls, loop state, join parameters, and
the conditions that chose an outcome's value. The journal stays append-only; the next
resume runs exactly the invalidated effects again.

The program `chain.orc`: `b` reads `a`, `d` reads `b`, `c` reads nothing, and `e` is
chosen by a condition on `a` but its own input reads nothing. The probe adds 1000 to
`fetch 1` when a file `offset` exists: a result that depends on something no boundary
declares, which is why someone would ask for the rerun.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from experiments.evaluated_execution_spike.evaluator import EvaluationFailed, evaluate, invalidate
from experiments.evaluated_execution_spike.memo import MemoBusy
from tests.experiments.test_evaluated_execution_spike import build, calls, fixture, records, run_root, spike
from tests.workflow_lisp_totality_matrix_sources import PROBE

OFFSET_PROBE = PROBE.replace('"fetch": {"n": n}', '"fetch": {"n": n + (1000 if n == 1 and Path("offset").exists() else 0)}')


def completed_run(root: Path, monkeypatch: pytest.MonkeyPatch, **options):
    """The program run once to its end (133), then the undeclared data changed."""

    monkeypatch.chdir(root)
    sources = fixture("chain")
    closed = build(root, sources)
    (root / "probe.py").write_text(OFFSET_PROBE, encoding="utf-8")
    _, result = spike(root, sources, closed=closed, **options)
    assert (result.value, calls(root)) == ({"n": 133}, ["fetch 1", "fetch 11", "fetch 3", "fetch 111", "fetch 7"])
    (root / "offset").write_text("", encoding="utf-8")
    return sources, closed, {name: r["identity"] for name, r in zip("abcde", records(root))}


def test_invalidating_an_effect_reruns_it_and_every_effect_committed_after_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, closed, ids = completed_run(tmp_path, monkeypatch)
    _, unchanged = spike(tmp_path, sources, closed=closed)  # a plain resume reuses every commit
    journal = (run_root(tmp_path) / "memo.jsonl").read_bytes()

    invalidated = invalidate(run_root(tmp_path), ids["b"])
    _, resumed = spike(tmp_path, sources, closed=closed)

    assert unchanged.value == {"n": 133}
    assert invalidated == [ids["b"], ids["c"], ids["d"], ids["e"]]
    assert calls(tmp_path)[5:] == ["fetch 11", "fetch 3", "fetch 111", "fetch 7"]
    assert resumed.value == {"n": 133}  # `a` kept its commit: 1, not 1001
    assert (run_root(tmp_path) / "memo.jsonl").read_bytes().startswith(journal)  # appended, nothing rewritten


def test_following_values_reruns_it_and_exactly_the_effects_whose_inputs_read_its_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources, closed, ids = completed_run(tmp_path, monkeypatch)
    journal = (run_root(tmp_path) / "memo.jsonl").read_bytes()

    invalidated = invalidate(run_root(tmp_path), ids["a"], follow="values")
    _, resumed = spike(tmp_path, sources, closed=closed)

    assert invalidated == [ids["a"], ids["b"], ids["d"]]
    assert calls(tmp_path)[5:] == ["fetch 1", "fetch 1011", "fetch 1111"]
    assert resumed.value == {"n": 1001 + 1011 + 3 + 1111 + 7}
    assert (run_root(tmp_path) / "memo.jsonl").read_bytes().startswith(journal)  # appended, nothing rewritten
    assert [(r["identity"], r["by"]) for r in records(tmp_path, "invalidated")] == [
        (ids["a"], ids["a"]), (ids["b"], ids["a"]), (ids["d"], ids["a"])]


def test_following_values_an_effect_that_reads_nothing_keeps_its_commit_even_under_its_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`c` is independent; `e` stands in a branch chosen by `a`'s value, but its input reads nothing of `a`."""

    sources, closed, ids = completed_run(tmp_path, monkeypatch)
    invalidate(run_root(tmp_path), ids["a"], follow="values")
    spike(tmp_path, sources, closed=closed)

    started = [r["identity"] for r in records(tmp_path, "started")]
    depends = {r["identity"]: r["depends_on"] for r in records(tmp_path)[:5]}
    assert (started.count(ids["c"]), started.count(ids["e"])) == (1, 1)
    assert depends == {ids["a"]: [], ids["b"]: [ids["a"]], ids["c"]: [], ids["d"]: [ids["b"]], ids["e"]: []}


# Review 3, finding 1: `a` writes `data.txt`, `b` reads it by a fixed path, and no value passes between them.
FILE_PROBE = """import json, os, sys
from pathlib import Path
n = int(sys.argv[2])
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(f"fetch {n}\\n")
if n == 1:  # writes the file the next command reads
    value = 1 + (1000 if Path("offset").exists() else 0)
    Path("data.txt").write_text(str(value), encoding="utf-8")
elif n == 2:  # reads it by a fixed path
    value = int(Path("data.txt").read_text(encoding="utf-8")) + n
else:
    value = n
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"n": value}), encoding="utf-8")
"""


@pytest.mark.parametrize(("follow", "expected"), [("suffix", 1001 + 1003 + 3), ("values", 1001 + 3 + 3)])
def test_a_dependence_through_a_file_is_rerun_only_under_the_suffix_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, follow: str, expected: int
) -> None:
    """A fresh run after the change gives 2007; following values mixes `b`'s old result into 1007."""

    monkeypatch.chdir(tmp_path)
    sources = fixture("three_call_sites")
    closed = build(tmp_path, sources)
    (tmp_path / "probe.py").write_text(FILE_PROBE, encoding="utf-8")
    _, first = spike(tmp_path, sources, closed=closed)
    (tmp_path / "offset").write_text("", encoding="utf-8")

    invalidate(run_root(tmp_path), records(tmp_path)[0]["identity"], follow=follow)
    _, resumed = spike(tmp_path, sources, closed=closed)

    assert (first.value, resumed.value) == ({"n": 1 + 3 + 3}, {"n": expected})
    assert [r["depends_on"] for r in records(tmp_path)[:3]] == [[], [], []]


def test_invalidate_is_refused_while_an_evaluator_holds_the_memo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    sources = fixture("chain")
    closed = build(tmp_path, sources)
    refused = []

    def hook(event: str, identity: str) -> None:
        if event == "committed" and len(records(tmp_path)) == 2:
            with pytest.raises(MemoBusy) as busy:
                invalidate(run_root(tmp_path), records(tmp_path)[0]["identity"])
            refused.append(str(busy.value))

    spike(tmp_path, sources, closed=closed, hook=hook)

    assert refused == [f"the memo {run_root(tmp_path) / 'memo.jsonl'} has another writer"]
    assert records(tmp_path, "invalidated") == []


def test_invalidating_a_coordinator_effect_with_a_final_commit_is_refused_with_what_the_design_must_decide(
    tmp_path: Path,
) -> None:
    from experiments.evaluated_execution_spike.memo import read_records
    from tests.experiments.test_evaluated_execution_spike_coordinator import PROGRAM, SITE, RunRefCoordinator

    coordinator = RunRefCoordinator(tmp_path / "coordinator")
    evaluate(PROGRAM, inputs={}, workspace=tmp_path, run_root=tmp_path / "run", coordinators={"run_ref": coordinator})
    before = read_records(tmp_path / "run")

    with pytest.raises(EvaluationFailed) as refused:
        invalidate(tmp_path / "run", SITE)

    assert (refused.value.code, refused.value.detail) == (
        "invalidate_coordinator_committed", {"coordinated": [SITE], "settled": [True]})
    assert "the design must decide whether a committed visit can be superseded" in str(refused.value)
    assert coordinator.ledger(SITE)[-1] == (1, "committed")
    assert read_records(tmp_path / "run") == before
