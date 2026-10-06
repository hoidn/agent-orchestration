"""Original Python illustration of validation and sequential result recovery.

The historical filename does not imply equivalence with the ORC runtime.
This script checks a few response shapes, journals completed effects and
reuses those results in a fixed sequential program. An interrupted effect
without a durable result may run again. selfcheck.py exercises specific
committed-boundary recovery, malformed-answer and missing-answer cases.

A Python workflow library could supply these services to its callers;
implementing them here is not an inherent cost of Python authoring. See
README.md for the conceptual language comparisons.

    python -m experiments.orc_vs_python_showcase.improve_equivalent run "<question>"
    python -m experiments.orc_vs_python_showcase.improve_equivalent resume .runs/<id>
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

PROMPTS = Path("workflows/examples/prompts/workflows/improve_experiment_proposal")
AGENT = os.environ.get("AGENT_CMD", "codex exec -").split()
LAUNCHER = os.environ.get("LAUNCHER_CMD", "python scripts/launch_experiment.py").split()
LIMIT = 3

# The shapes the .orc declares with defrecord/defunion.
PARAMETER = {"name": str, "value": int}
PROPOSAL = {"hypothesis": str, "parameters": [PARAMETER]}
DECISION = {
    "APPROVE": {"evidence": {"notes": str}},
    "REVISE": {"feedback": {"notes": str}},
    "BLOCKED": {"reason": {"issue": str}},
}
EXPERIMENT_RUN = {"status": str}


class Violation(Exception):
    """An answer that does not have its declared shape; the message names where."""


def check(value, shape, at=""):
    if isinstance(shape, dict):
        if not isinstance(value, dict):
            raise Violation(f"{at or '/'}: expected an object")
        if set(value) != set(shape):
            raise Violation(f"{at or '/'}: fields differ: {sorted(set(value) ^ set(shape))}")
        for key, field_shape in shape.items():
            check(value[key], field_shape, f"{at}/{key}")
    elif isinstance(shape, list):
        if not isinstance(value, list):
            raise Violation(f"{at or '/'}: expected a list")
        for index, item in enumerate(value):
            check(item, shape[0], f"{at}/{index}")
    elif not isinstance(value, shape) or (shape is int and isinstance(value, bool)):
        raise Violation(f"{at or '/'}: expected {shape.__name__}")
    return value


def check_decision(value):
    kind = value.get("kind") if isinstance(value, dict) else None
    if kind not in DECISION:
        raise Violation(f"/kind: expected one of {sorted(DECISION)}")
    return check({k: v for k, v in value.items() if k != "kind"}, DECISION[kind])


class Run:
    """A journal of completed effects for one fixed sequential program."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.journal = root / "journal.jsonl"
        self.committed: list[dict] = []
        self.next = 0
        if self.journal.exists():
            for line in self.journal.read_text(encoding="utf-8").splitlines():
                try:
                    self.committed.append(json.loads(line))
                except json.JSONDecodeError:  # the crash tore the last line: not committed
                    break

    def effect(self, name: str, perform):
        # The i-th effect of a run is the same effect on every resume: control flow
        # depends only on committed answers, so the ordinal identifies it. A loop
        # whose shape depended on anything else would need a key, not a count.
        ordinal, self.next = self.next, self.next + 1
        if ordinal < len(self.committed):
            record = self.committed[ordinal]
            if record["name"] != name:
                raise RuntimeError(f"resume diverged at effect {ordinal}: {record['name']} != {name}")
            return record["value"]
        value = perform(self.root / f"effect-{ordinal}.json")
        with self.journal.open("a", encoding="utf-8") as journal:
            journal.write(json.dumps({"name": name, "value": value}) + "\n")
            journal.flush()
            os.fsync(journal.fileno())
        return value


def ask(run: Run, prompt_file: str, inputs: dict, validate):
    def perform(bundle: Path):
        bundle.unlink(missing_ok=True)  # this call, not an earlier one, must produce it
        prompt = (PROMPTS / prompt_file).read_text(encoding="utf-8") + "\n" + json.dumps(inputs)
        env = {**os.environ, "OUTPUT_BUNDLE_PATH": str(bundle)}
        subprocess.run(AGENT, input=prompt, text=True, check=True, env=env)
        if not bundle.exists():
            raise Violation(f"{prompt_file}: the agent produced no answer file")
        return validate(json.loads(bundle.read_text(encoding="utf-8")))

    return run.effect(prompt_file, perform)


def review_proposal(run: Run, proposal: dict, question: str) -> dict:
    return ask(run, "review.md", {"question": question, **proposal}, check_decision)


def revise_proposal(run: Run, proposal: dict, question: str, notes: str) -> dict:
    inputs = {"question": question, **proposal, "notes": notes}
    return ask(run, "revise.md", inputs, lambda value: check(value, PROPOSAL))


def improve(run: Run, initial: dict, inputs, review, revise, limit: int):
    """`std/improve::improve`: review, revise on request, at most `limit` reviews."""
    current = initial
    for _ in range(limit):
        decision = review(run, current, inputs)
        if "evidence" in decision:
            return "approved", current, decision["evidence"]["notes"]
        if "reason" in decision:
            return "blocked", current, decision["reason"]["issue"]
        current = revise(run, current, inputs, decision["feedback"]["notes"])
    return "exhausted", current, ""


def execute(run: Run, proposal: dict, outcome: str, note: str):
    argv = [*LAUNCHER, "--outcome", outcome, "--note", note, "--hypothesis", proposal["hypothesis"],
            "--parameters", json.dumps(proposal["parameters"])]

    def perform(bundle: Path):
        bundle.unlink(missing_ok=True)
        subprocess.run(argv, check=True, env={**os.environ, "OUTPUT_BUNDLE_PATH": str(bundle)})
        return check(json.loads(bundle.read_text(encoding="utf-8")), EXPERIMENT_RUN)

    return run.effect("launch_experiment", perform)


def run_experiment(run: Run, question: str) -> dict:
    proposal = {"hypothesis": question, "parameters": [{"name": "seed", "value": 0}]}
    outcome, final, note = improve(run, proposal, question, review_proposal, revise_proposal, LIMIT)
    return execute(run, final, outcome, note)


def main(argv: list[str]) -> int:
    if argv[:1] == ["run"]:
        root = Path(".runs") / uuid.uuid4().hex[:8]
        root.mkdir(parents=True)
        (root / "inputs.json").write_text(json.dumps({"question": argv[1]}), encoding="utf-8")
    elif argv[:1] == ["resume"]:
        root = Path(argv[1])
    else:
        print(__doc__, file=sys.stderr)
        return 2
    question = json.loads((root / "inputs.json").read_text(encoding="utf-8"))["question"]
    print(json.dumps({"run": str(root), **run_experiment(Run(root), question)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
