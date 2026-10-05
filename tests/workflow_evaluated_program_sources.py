"""Compact paired-search fixtures for public evaluated runs: stock, scripted and growth.

The stock controller is copied with only its target header changed. Scripted leaves are
the fixture's stand-ins, installed with their answers in the declared closure. The
growth variant adds 14 audit counters and their 27 source `if` selectors; it keeps the
A/B policy, commands and budget, and its counters are checked against a fold over the
Python trace, never against ORC state.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import sys
from typing import Any, NamedTuple
from unittest.mock import patch

import pytest

from experiments.mlevolve_pair import leaves
from experiments.mlevolve_pair.search import run_search
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.workflow.evaluated import machine, runtime, values
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import ListExpr, SymbolAtom
from tests.experiments.test_mlevolve_pair_fixture import _SCRIPTED_LEAVES, _reference, _scenario_answers
from tests.test_workflow_evaluated_command_lifecycle import _InterruptedRun
from tests.test_workflow_evaluated_resume import _resume_cli, _snapshot
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args
from tests.workflow_evaluated_totality_helpers import assert_commit_bytes, checked_run, compile_public


PAIR = Path(__file__).resolve().parents[1] / "experiments" / "mlevolve_pair"
LEAVES = "experiments/mlevolve_pair/leaves.py"
ANSWERS = "experiments/mlevolve_pair/answers.json"
PROPOSAL = ("operation", "branch", "candidate_a", "candidate_b", "other_a", "other_b", "history_size")
FRESH = "execute_pure_run.<locals>.handle"
VIEW_REPLAY = "_replay.<locals>.handle"
_LOOP = "workflow:mlevolve_pair/search_compact::run-search / else"
PAUSE_SITES = {  # the commit paused at: seed B with budget 2, else the first post-seed evaluation
    2: f"{_LOOP} / seed-b-evaluation",
    4: f"{_LOOP} / loop:state[1] / else / else / else / else"
       " / next-state=procedure:mlevolve_pair/search_compact::branch-step / evaluation",
}
AUDIT = ("valid_trials", "invalid_trials", "accepted_trials", "rejected_trials", "best_changes",
         "accepted_a", "accepted_b", "invalid_a", "invalid_b", "repairs_a", "repairs_b",
         "rejected_a", "rejected_b", "last_accepted_at")


def stock_source() -> str:
    text = (PAIR / "search_compact.orc").read_text(encoding="utf-8")
    header = '(:target-dsl "2.33")'
    assert text.count(header) == 1
    return text.replace(header, '(:target-dsl "2.35")')


def install(root: Path, text: str, scenario: dict | None) -> dict[str, Path]:
    pair = root / "experiments" / "mlevolve_pair"
    pair.mkdir(parents=True)
    (pair / "search_compact.orc").write_text(text, encoding="utf-8")
    closure = [LEAVES]
    if scenario is None:
        shutil.copy2(PAIR / "leaves.py", pair / "leaves.py")
    else:
        (pair / "leaves.py").write_text(_SCRIPTED_LEAVES, encoding="utf-8")
        (pair / "answers.json").write_text(json.dumps(_scenario_answers(scenario)), encoding="utf-8")
        closure.append(ANSWERS)
    rows = json.loads((PAIR / "commands_compact.json").read_text(encoding="utf-8"))
    for row in rows.values():
        row["closure"] = closure
    files = {"workspace": root, "source": pair / "search_compact.orc", "source_root": root / "experiments",
             "providers": root / "providers.json", "prompts": root / "prompts.json",
             "commands": root / "commands.json"}
    files["providers"].write_text("{}", encoding="utf-8")
    files["prompts"].write_text("{}", encoding="utf-8")
    files["commands"].write_text(json.dumps(rows), encoding="utf-8")
    return files


def public_run(files: dict[str, Path], budget: int):
    args = _run_args(files)
    args.entry_workflow, args.emit_debug_yaml = None, False
    args.command_boundaries_file = str(files["commands"])
    args.input = [f"max_evaluations={budget}"]
    argv = ["orchestrator", "run", str(files["source"]), "--source-root", str(files["source_root"]),
            "--provider-externs-file", str(files["providers"]), "--prompt-externs-file",
            str(files["prompts"]), "--command-boundaries-file", str(files["commands"]),
            "--input", f"max_evaluations={budget}"]
    with patch.object(sys, "argv", argv):
        return run_workflow(args)


def reference(scenario: dict | None, budget: int) -> tuple[dict, list[dict]]:
    """Python result and ordered leaf requests; the stock case delegates to the real leaves."""
    if scenario is not None:
        return _reference(scenario, budget)
    calls = []

    def propose(*arguments):
        inputs = dict(zip(PROPOSAL, arguments, strict=True))
        calls.append({"outer_operation": "proposal", "command": "propose_candidate", "inputs": inputs})
        return leaves.propose(*arguments)

    def evaluate(a, b):
        calls.append({"outer_operation": "evaluate", "command": "evaluate_candidate", "inputs": {"a": a, "b": b}})
        return leaves.evaluate(a, b)

    return run_search(max_evaluations=budget, proposal=propose, evaluator=evaluate), calls


def observe_requests(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Record each effective argv handed to the real command performer, then delegate."""
    calls = []
    real = runtime.perform_command

    def perform(node, argv, **kwargs):
        calls.append({"outer_operation": argv[-2], "command": node["boundary"], "inputs": json.loads(argv[-1])})
        return real(node, argv, **kwargs)

    monkeypatch.setattr(runtime, "perform_command", perform)
    return calls


def pause_after(files: dict[str, Path], budget: int, monkeypatch: pytest.MonkeyPatch, count: int) -> list:
    appended = []
    real_append = runtime.append_record

    def after_commit(path, record, **kwargs):
        entry = real_append(path, record, **kwargs)
        if record.get("record") == "committed":
            appended.append(entry)
            if len(appended) == count:
                raise _InterruptedRun()
        return entry

    with monkeypatch.context() as patched:
        patched.setattr(runtime, "append_record", after_commit)
        with pytest.raises(_InterruptedRun):
            public_run(files, budget)
    return appended


@dataclass(frozen=True)
class Outcome:
    """Observed terminal value and requests, with what the Python reference expects of them.

    `calls` are the requests seen by the in-process performer seam; after a CLI resume
    only the paused prefix is in process. `log` is the stand-in children's own log.
    """

    actual: dict
    expected: dict
    calls: list
    expected_calls: list
    log: list
    expected_log: list

    def observed(self, result: Any = None) -> dict:
        return {"result": self.actual if result is None else result, "requests": self.calls,
                "child_log": self.log}

    def wanted(self) -> dict:
        return {"result": self.expected, "requests": self.expected_calls, "child_log": self.expected_log}


def resume_service(root: Path, run_id: str) -> None:
    assert resume_workflow(run_id) == 0


def resume_cli(root: Path, run_id: str) -> None:
    result = _resume_cli(root, run_id)
    assert result.returncode == 0, result.stderr


def _stand_in_log(files: dict[str, Path]) -> list[dict]:
    log = files["source"].with_name("calls.jsonl")
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


def _pause_and_resume(files, budget, monkeypatch, count, requests, resume) -> None:
    calls, python_calls, child_calls = requests
    appended = pause_after(files, budget, monkeypatch, count)
    authority, paused = checked_run(files["workspace"])
    commits = sorted(paused.active_commits.values(), key=lambda entry: entry.offset)
    assert paused.terminal is None
    assert [entry.data for entry in commits] == [entry.data for entry in appended]
    for entry in commits:
        assert_commit_bytes(authority, entry)
    assert {"site": commits[-1].data["identity"], "requests": calls, "child_log": _stand_in_log(files)} == {
        "site": PAUSE_SITES[count], "requests": python_calls[:count], "child_log": child_calls[:count]}
    prefix = authority.memo_path.read_bytes()
    resume(files["workspace"], authority.run_root.name)
    assert authority.memo_path.read_bytes().startswith(prefix)


def exercise(root: Path, monkeypatch: pytest.MonkeyPatch, text: str, budget: int,
             scenario: dict | None = None, *, compile: bool = True, cli: bool = False) -> Outcome:
    """Public run paused after the first post-seed evaluation, resume, completed resume.

    `compile` adds the public compile first; `cli` resumes both times through the
    `orchestrator resume` subprocess instead of the in-process resume service.
    """
    files = install(root, text, scenario)
    if compile:
        compile_public(files)
    monkeypatch.chdir(root)
    expected, python_calls = reference(scenario, budget)
    child_calls = python_calls if scenario is not None else []
    effects, resume = max(0, 2 * expected["evaluations"] - 2), resume_cli if cli else resume_service
    calls = observe_requests(monkeypatch)
    if effects:
        _pause_and_resume(files, budget, monkeypatch, min(4, effects), (calls, python_calls, child_calls), resume)
    else:
        assert public_run(files, budget).exit_code == 0
    authority, snapshot = checked_run(root)
    assert snapshot.terminal.data["outcome"] == "completed"
    assert len(snapshot.active_commits) == len(snapshot.latest_starts) == effects
    for entry in snapshot.active_commits.values():
        assert_commit_bytes(authority, entry)
    before = {"state": _snapshot(root / ".orchestrate"), "requests": list(calls), "child_log": _stand_in_log(files)}
    resume(root, authority.run_root.name)
    assert {"state": _snapshot(root / ".orchestrate"), "requests": calls, "child_log": _stand_in_log(files)} == before
    return Outcome(snapshot.terminal.data["value"], expected, before["requests"],
                   python_calls[:min(4, effects)] if cli else python_calls, before["child_log"], child_calls)


# Growth variant ------------------------------------------------------------------


def _inc(field: str, condition: str, *, when: bool = True) -> str:
    up, keep = f"(+ state.{field} 1)", f"state.{field}"
    return f":{field} (if {condition} {up} {keep})" if when else f":{field} (if {condition} {keep} {up})"


def _tallies(best: str, where: str) -> list:
    return [((f"valid_trials:{where}",), _inc("valid_trials", "evaluation.valid")),
            ((f"invalid_trials:{where}",), _inc("invalid_trials", "evaluation.valid", when=False)),
            ((f"accepted_trials:{where}",), _inc("accepted_trials", "accepted")),
            ((f"rejected_trials:{where}",), _inc("rejected_trials", "accepted", when=False)),
            ((f"best_changes:{where}",), _inc("best_changes", best)),
            ((f"last_accepted_at:{where}",),
             ":last_accepted_at (if accepted (+ state.evaluations 1) state.last_accepted_at)")]


def _side(side: str) -> list:
    where = side.upper()
    return [((f"accepted_{side}:{where}",), _inc(f"accepted_{side}", "accepted")),
            ((f"invalid_{side}:{where}",), _inc(f"invalid_{side}", "evaluation.valid", when=False)),
            ((f"repairs_{side}:{where}",), _inc(f"repairs_{side}", '(= operation "repair")')),
            ((f"rejected_{side}:{where}",), _inc(f"rejected_{side}", "accepted", when=False))]


def _plain(template: str) -> list:
    return [((), " ".join(template.format(name) for name in AUDIT))]


_SEEDS = [
    (("valid_trials:seed-a", "valid_trials:seed-b"),
     ":valid_trials (+ (if seed-a-evaluation.valid 1 0) (if seed-b-evaluation.valid 1 0))"),
    (("invalid_trials:seed-a", "invalid_trials:seed-b"),
     ":invalid_trials (+ (if seed-a-evaluation.valid 0 1) (if seed-b-evaluation.valid 0 1))"),
    ((), ":accepted_trials 2 :rejected_trials 0"),
    (("best_changes:seed",), ":best_changes (if seed-b-is-best 1 0)"),
    ((), ":accepted_a 1 :accepted_b 1"),
    (("invalid_a:seed",), ":invalid_a (if seed-a-evaluation.valid 0 1)"),
    (("invalid_b:seed",), ":invalid_b (if seed-b-evaluation.valid 0 1)"),
    ((), ":repairs_a 0 :repairs_b 0 :rejected_a 0 :rejected_b 0 :last_accepted_at 2"),
]

# Each anchor occurs once in the stock source; its insertion goes right after it.
GROWTH = {
    "(fused Bool)": _plain("({} Int)"),
    "(trace List[Trial])": _plain("({} Int)"),
    ":status status :trace state.history": _plain(":{0} state.{0}"),
    ":fused state.fused": _tallies("best-changed", "S"),
    ":stall_a (if accepted 0 (+ state.stall_a 1))": _side("a"),
    ":stall_b (if accepted 0 (+ state.stall_b 1))": _side("b"),
    ':status "invalid_budget" :trace (list)': _plain(":{} 0"),
    ":fused false": _SEEDS,
    ":fused true": _tallies("accepted", "F"),
}


def growth_source(stock: str) -> tuple[str, dict[str, int]]:
    """Return the growth source and the offset of each added `if` by its label."""
    ends = []
    for anchor, items in GROWTH.items():
        assert stock.count(anchor) == 1, anchor
        ends.append((stock.index(anchor) + len(anchor), items))
    text, cursor, labels = "", 0, {}
    for end, items in sorted(ends, key=lambda pair: pair[0]):
        text, cursor = text + stock[cursor:end], end
        for names, snippet in items:
            starts = [index for index in range(len(snippet)) if snippet.startswith("(if ", index)]
            assert len(starts) == len(names), snippet
            labels.update((name, len(text) + 1 + start) for name, start in zip(names, starts))
            text += " " + snippet
    return text + stock[cursor:], labels


def _ifs(node) -> list[ListExpr]:
    if not isinstance(node, ListExpr):
        return []
    head = node.items[0] if node.items else None
    own = [node] if isinstance(head, SymbolAtom) and head.value == "if" else []
    return own + [found for item in node.items for found in _ifs(item)]


def census(text: str, path: str) -> tuple[dict[str, int], dict[int, tuple[int, int]]]:
    """Record fields and source `if` nodes per reachable definition, counted once each."""
    (module,) = read_sexpr_text(text, source_path=path).items
    forms = {form.items[1].value: form for form in module.items
             if isinstance(form, ListExpr) and isinstance(form.items[0], SymbolAtom)
             and form.items[0].value in ("defrecord", "defun", "defproc", "defworkflow")}
    found = {name: _ifs(forms[name]) for name in ("result", "branch-step", "run-search")}
    counts = {name: len(forms[name].items) - 2 for name in ("SearchState", "SearchResult")}
    starts = {node.span.start.offset: (node.span.start.line, node.span.start.column)
              for nodes in found.values() for node in nodes}
    return {**counts, **{name: len(nodes) for name, nodes in found.items()}}, starts


def label_spans(text: str, source: Path, labels: dict[str, int]) -> dict[str, str]:
    """Map each added label to the checked provenance span of its parsed `if` form."""
    _, starts = census(text, str(source))
    return {f"{source}:{starts[offset][0]}:{starts[offset][1]}": label for label, offset in labels.items()}


def closed_nodes(node, kind: str, path: str = "") -> list[tuple[str, dict]]:
    """(path, node) for every checked node of `kind`; the path names its exact occurrence."""
    if isinstance(node, dict):
        own = [(path, node)] if node.get("k") == kind else []
        return own + [found for key, item in node.items() for found in closed_nodes(item, kind, f"{path}/{key}")]
    if isinstance(node, list):
        return [found for index, item in enumerate(node)
                for found in closed_nodes(item, kind, f"{path}[{index}]")]
    return []


def occurrences(tree: dict, kind: str, spans: dict[str, str]) -> dict[str, list[str]]:
    """Checked occurrence paths of `kind` for each label, matched by provenance span."""
    found = {label: [] for label in spans.values()}
    for path, node in closed_nodes(tree, kind):
        span = node.get("@", {}).get("span")
        if span in spans:
            found[spans[span]].append(path)
    return found


def _seed_best(trace: list[dict]) -> tuple[dict, int]:
    seed_a, seed_b = (row["evaluation"] for row in trace[:2])
    b_first = seed_b["valid"] and (not seed_a["valid"] or seed_b["score"] < seed_a["score"])
    return (seed_b if b_first else seed_a), int(b_first)


def _tally(audit: dict[str, int], ordinal: int, row: dict) -> None:
    valid, accepted, side = row["evaluation"]["valid"], row["accepted"], row["branch"].lower()
    audit["valid_trials" if valid else "invalid_trials"] += 1
    audit["accepted_trials" if accepted else "rejected_trials"] += 1
    if accepted:
        audit["last_accepted_at"] = ordinal
    if side in ("a", "b"):
        audit[f"accepted_{side}" if accepted else f"rejected_{side}"] += 1
        audit[f"invalid_{side}"] += not valid
        audit[f"repairs_{side}"] += row["action"] == "repair"


def audit_fold(trace: list[dict]) -> dict[str, int]:
    """The 14 audit counters from the Python trace alone."""
    audit = dict.fromkeys(AUDIT, 0)
    if not trace:
        return audit
    best, audit["best_changes"] = _seed_best(trace)
    for ordinal, row in enumerate(trace, start=1):
        _tally(audit, ordinal, row)
        if ordinal > 2 and row["accepted"] and row["evaluation"]["score"] < best["score"]:
            best, audit["best_changes"] = row["evaluation"], audit["best_changes"] + 1
    return audit


class SelectEvent(NamedTuple):
    span: str | None
    arm: bool
    lane: str | None
    owner: str | None
    activation: tuple
    loops: tuple
    occurrence: str | None  # checked-tree path of the select node, resolved in the fresh lane


def _occurrence(cache: dict, tree: dict, node: dict) -> str | None:
    if id(tree) not in cache:  # the tree is kept alive so its id is not reused
        cache[id(tree)] = (tree, {id(found): path for path, found in closed_nodes(tree, "select")})
    return cache[id(tree)][1].get(id(node))


@contextmanager
def selector_events(monkeypatch: pytest.MonkeyPatch):
    """Yield a SelectEvent for each value select, forwarding every call unchanged."""
    events, active, frames, cache = [], [], [], {}
    real_select = values._VALUE_EVALUATORS["select"]
    real_coerce, real_value = values.coerce_pure_value, machine._Machine._value

    def select(node, environment, evaluate_body, evaluate_binding):
        active.append(node)
        try:
            return real_select(node, environment, evaluate_body, evaluate_binding)
        finally:
            active.pop()

    def coerce(value, descriptor, *args, **kwargs):
        result = real_coerce(value, descriptor, *args, **kwargs)
        if kwargs.get("context") == "select condition" and active:
            tree, lane, owner, activation, loops = frames[-1] if frames else (None, None, None, (), ())
            node = active[-1]
            occurrence = _occurrence(cache, tree, node) if lane == FRESH else None
            events.append(SelectEvent(node.get("@", {}).get("span"), result, lane, owner, activation, loops,
                                      occurrence))
        return result

    def value(self, node, environment, owner, activation, loops):
        frames.append((self.program.tree, getattr(self.effect_handler, "__qualname__", None), owner,
                       activation, loops))
        try:
            return real_value(self, node, environment, owner, activation, loops)
        finally:
            frames.pop()

    with monkeypatch.context() as patched:
        patched.setitem(values._VALUE_EVALUATORS, "select", select)
        patched.setattr(values, "coerce_pure_value", coerce)
        patched.setattr(machine._Machine, "_value", value)
        yield events


def fresh_rows(events: list[SelectEvent], spans: dict[str, str], tree: dict,
               trace: list[dict]) -> tuple[list[dict], Counter]:
    """Fresh-lane events of the added selectors, checked against the run's checked program.

    Each reached seed is evaluated once (7 selectors), each branch step once (6 common
    and 4 per side) and the fusion once (6); seeds run outside the loop, the rest inside
    it: in the loop body itself (`loops`) or in the called step (its `loop:` activation).
    """
    lanes = Counter(event.lane for event in events if event.span in spans)
    rows = [{"label": spans[event.span], "arm": event.arm, "owner": event.owner,
             "activation": " / ".join(event.activation), "loops": [list(loop) for loop in event.loops],
             "occurrence": event.occurrence}
            for event in events if event.lane == FRESH and event.span in spans]
    seen, checked = _seen_occurrences(rows), occurrences(tree, "select", spans)
    mismatched = [row for row in rows
                  if (bool(row["loops"]) or " / loop:" in row["activation"]) == (":seed" in row["label"])]
    assert {"lanes": set(lanes) - {FRESH, VIEW_REPLAY}, "fresh_events": len(rows), "occurrences": seen,
            "seed_loop_mismatch": mismatched} == {
        "lanes": set(), "fresh_events": _reached_selectors(trace),
        "occurrences": {label: set(checked[label]) for label in seen}, "seed_loop_mismatch": []}
    return rows, lanes


def _reached_selectors(trace: list[dict]) -> int:
    return 7 + sum(10 if row["branch"] in ("A", "B") else 6 for row in trace[2:]) if trace else 0


def _seen_occurrences(rows: list[dict]) -> dict[str, set]:
    seen = {}
    for row in rows:
        seen.setdefault(row["label"], set()).add(row["occurrence"])
    return seen
