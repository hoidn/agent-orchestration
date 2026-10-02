"""The obvious Python version of `workflows/examples/improve_experiment_proposal.orc`.

Shorter than the workflow. It is also a different program: an agent answer is
trusted as it comes, a crash after the second agent call repeats both calls,
nothing records which answer led to which decision, and a typo in a dictionary
key is found after the agents it follows have already been paid for.
"""

import json
import os
import subprocess
import sys
import tempfile

PROMPTS = "workflows/examples/prompts/workflows/improve_experiment_proposal"


def ask(prompt_file, **inputs):
    prompt = open(f"{PROMPTS}/{prompt_file}").read() + "\n" + json.dumps(inputs)
    bundle = tempfile.mktemp(suffix=".json")
    subprocess.run(
        ["codex", "exec", "-"], input=prompt, text=True, check=True,
        env={**os.environ, "OUTPUT_BUNDLE_PATH": bundle},
    )
    return json.load(open(bundle))


def run(question):
    proposal = {"hypothesis": question, "parameters": [{"name": "seed", "value": 0}]}
    outcome, note = "exhausted", ""
    for _ in range(3):
        decision = ask("review.md", question=question, **proposal)
        if decision["kind"] == "APPROVE":
            outcome, note = "approved", decision["evidence"]["notes"]
            break
        if decision["kind"] == "BLOCKED":
            outcome, note = "blocked", decision["reason"]["issue"]
            break
        proposal = ask("revise.md", question=question, **proposal, notes=decision["feedback"]["notes"])
    subprocess.run(
        ["python", "scripts/launch_experiment.py", "--outcome", outcome, "--note", note,
         "--hypothesis", proposal["hypothesis"], "--parameters", json.dumps(proposal["parameters"])],
        check=True,
    )


if __name__ == "__main__":
    run(sys.argv[1])
