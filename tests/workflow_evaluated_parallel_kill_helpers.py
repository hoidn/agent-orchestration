"""A four-item parallel batch for public kill and resume tests (Phase 5 Task 5).

`STEP` is the stand-in command copied into each item directory. It logs every dispatch
to the control directory, fails while its cwd holds `fail`, exits 0 without a result while
it holds `noresult`, and blocks the steps listed
in `hold.json`; once every listed step blocks it publishes the `kill_at` marker, so the
kill lands with exactly the memo the test planned. It answers from its arguments only.
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from tests.test_workflow_evaluated_cli import _run_cli
from tests.workflow_evaluated_recovery_helpers import kill_at


ITEMS = ("a", "b", "c", "d")
FOUR = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule main) (export run)
  (defworkflow worker ((repo String)) -> Int
    (let* ((first (command-result step :argv ("python" "step.py" repo "first") :returns Int)))
      (if (= repo "b")
          (command-result step :argv ("python" "step.py" repo "second" first) :returns Int)
          first)))
  (defworkflow run () -> List[Int]
    (list/map-effect ((repo (list "a" "b" "c" "d"))) :max 4 :parallel 2 :workspace repo
      (call worker :repo repo))))
'''
FOUR_VALUE = [1, 21, 3, 4]
STEP = '''import json, os, signal, sys, time
from pathlib import Path
CONTROL = Path(@CONTROL@)
repo, stage = sys.argv[1], sys.argv[2]
bundle = os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
with open(CONTROL / "dispatches.jsonl", "a", encoding="utf-8") as log:
    log.write(json.dumps({"repo": repo, "stage": stage, "bundle": bundle}) + "\\n")
if Path("fail").exists():
    raise SystemExit(3)
if Path("noresult").exists():
    raise SystemExit(0)
quiet = CONTROL / "quiet.json"
if quiet.exists() and [repo, stage] in json.loads(quiet.read_text()):
    (CONTROL / f"quiet-{repo}-{stage}").write_text("")
    while True:
        signal.pause()
hold = CONTROL / "hold.json"
held = json.loads(hold.read_text()) if hold.exists() else []
if [repo, stage] in held:
    (CONTROL / f"held-{repo}-{stage}").write_text("")
    if all((CONTROL / f"held-{r}-{s}").exists() for r, s in held):
        marker = CONTROL / "marker.json"
        marker.with_name("marker.tmp").write_text(json.dumps({"pid": os.getpid(), "pgid": os.getpgrp(),
            "runner_pid": os.getppid()}))
        marker.with_name("marker.tmp").replace(marker)
    while True:
        signal.pause()
memo, wait = Path(bundle).parents[3] / "memo.jsonl", WAITS.get((repo, stage), 0)
deadline = time.monotonic() + 60
while wait and memo.read_text().count('"record":"committed"') < wait and time.monotonic() < deadline:
    time.sleep(0.02)
value = {"a": 1, "c": 3, "d": 4}.get(repo, 20) if stage == "first" else int(sys.argv[3]) + 1
Path(bundle).write_text(str(value))
'''


class Batch:
    """A workspace whose items (`a` to `d` by default) each hold a copy of `STEP`.

    `source` is written as `ws/main.orc`; with `source=None` the caller has already written
    the program into `ws`, and `run_args` names it (with any flags it needs, such as
    `--run-ref-root`). `refs` is the run-reference root, when there is one.
    """

    def __init__(self, root: Path, *, source: str | None = FOUR, items=ITEMS, waits=None, boundaries=None,
                 ws: Path | None = None, run_args: tuple[str, ...] = ("main.orc",), refs: Path | None = None):
        self.ws, self.control, self.run_args, self.refs = ws or root / "ws", root / "control", run_args, refs
        self.control.mkdir(parents=True)
        self.ws.mkdir(exist_ok=True)
        if source is not None:
            (self.ws / "main.orc").write_text(source)
        boundary = {"stable_command": ["python", "step.py"], "closure": []}
        (self.ws / "commands.json").write_text(json.dumps(boundaries or {"step": boundary}))
        script = STEP.replace("@CONTROL@", json.dumps(str(self.control))).replace(
            "WAITS.get", f"{dict(waits or {})!r}.get")
        for item in items:
            (self.ws / item).mkdir()
            (self.ws / item / "step.py").write_text(script)

    def argv(self, *extra: str) -> list[str]:
        return ["run", *self.run_args, "--command-boundaries-file", "commands.json", *extra]

    def run(self, *extra: str):
        return _run_cli(self.ws, *self.argv(*extra)[1:])

    def kill(self, holds, check=lambda marker: None, *, window=None, extra=(), quiet=()):
        """Kill at `window` or once every step in `holds` blocks; steps in `quiet` block unannounced."""
        (self.control / "hold.json").write_text(json.dumps([list(hold) for hold in holds]))
        (self.control / "quiet.json").write_text(json.dumps([list(step) for step in quiet]))
        marker = kill_at(self.ws, self.control, self.argv(*extra), window, check)
        (self.control / "hold.json").unlink()
        (self.control / "quiet.json").unlink()
        return marker

    def quietly_held(self, repo: str, stage: str) -> bool:
        return (self.control / f"quiet-{repo}-{stage}").exists()

    def run_root(self) -> Path:
        (root,) = (self.ws / ".orchestrate" / "runs").iterdir()
        return root

    def snapshot(self):
        authority = load_run_authority(self.run_root())
        return read_memo(authority.memo_path, site_classes(authority.program))

    def dispatches(self) -> list[tuple[str, str]]:
        log = self.control / "dispatches.jsonl"
        rows = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return [(row["repo"], row["stage"]) for row in rows]


def committed(snapshot) -> list[dict]:
    return [entry.data for entry in snapshot.entries if entry.data["record"] == "committed"]


def item_of(identity: str) -> str:
    """The item name of a `par-map:repo[<index>]` identity."""
    return ITEMS[int(identity.split("par-map:repo[", 1)[1].split("]", 1)[0])]


def run_ref_batch(root: Path, invoke: str, items: tuple[str, ...], *, must_not_repeat=()) -> Batch:
    """A 2.37 controller whose items call `invoke` (its run reference spelled `CALL`) in `parent/<item>`.

    Its commands are `peer` and `target`; those named in `must_not_repeat` declare it.
    """
    from tests.test_workflow_evaluated_run_ref import _public_fixture
    root.mkdir(parents=True)
    listed = " ".join(json.dumps(item) for item in items)
    body = (f'(list/map-effect ((repo (list {listed}))) :max {len(items)} :parallel 2 :workspace repo '
            '(call invoke :repo repo))')
    parent, source, refs = _public_fixture(root, parent_target="2.37", child_target="2.35",
        definitions=lambda call: invoke.replace("CALL", call),
        body=lambda _call: f"(let* ((items {body})) (= (list/length items) {len(items)}))")
    boundary = {"stable_command": ["python", "step.py"], "closure": []}
    boundaries = {name: {**boundary, "must_not_repeat": name in must_not_repeat} for name in ("peer", "target")}
    return Batch(root, source=None, items=items, boundaries=boundaries, ws=parent,
                 run_args=(str(source), "--run-ref-root", str(refs)), refs=refs)


def child_launches(batch: Batch) -> int:
    return len(list(batch.refs.rglob("child-request.json")))
