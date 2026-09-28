"""Workflow Lisp sources and command probes for `tests/test_workflow_lisp_improve_stdlib.py`.

Each probe appends its argv (space-joined) to `<probe>.log`, so tests can assert
the ordered hook operations and that committed hook work is not replayed.

Review probe policy, keyed on the candidate title (`+r` marks one revision):
`malformed` -> an APPROVE payload that fails `Feedback`; `approve*` -> APPROVE;
`block*` after a revision -> BLOCKED; anything else -> REVISE with `fb<n>`.
Revise probe: appends `+r`; a `fail*` candidate that was already revised exits 3.
"""

from __future__ import annotations

from pathlib import Path

import orchestrator.workflow_lisp as workflow_lisp_package


STD_IMPROVE_PATH = Path(workflow_lisp_package.__file__).resolve().parent / "stdlib_modules" / "std" / "improve.orc"


_PROBE_PRELUDE = """import json, os, sys
from pathlib import Path
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
"""

_PROBE_WRITE = """bundle = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
if bundle:
    Path(bundle).parent.mkdir(parents=True, exist_ok=True)
    Path(bundle).write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps(payload))
"""

REVIEW_PROBE = _PROBE_PRELUDE + """title, goal = sys.argv[1], sys.argv[2]
if title == "malformed":
    payload = {"variant": "APPROVE", "evidence": {"score": 1}}
elif title.startswith("approve"):
    payload = {"variant": "APPROVE", "evidence": {"note": "ok:" + title + ":" + goal}}
elif title.startswith("block") and "+r" in title:
    payload = {"variant": "BLOCKED", "reason": {"why": "refused:" + title}}
else:
    payload = {"variant": "REVISE", "feedback": {"note": "fb" + str(title.count("+r"))}}
""" + _PROBE_WRITE

REVISE_PROBE = _PROBE_PRELUDE + """title = sys.argv[1]
if title.startswith("fail") and "+r" in title:
    sys.exit(3)
payload = {"title": title + "+r", "score": title.count("+r") + 1}
""" + _PROBE_WRITE


IMPORT_LINE = "  (import std/improve :only (Decision Improvement improve))\n"

ENTRY = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule grt/entry)
""" + IMPORT_LINE + """  (export run)
  (defrecord Candidate (title String) (score Int))
  (defrecord Brief (goal String))
  (defrecord Feedback (note String))
  (defrecord Blocker (why String))
  (defproc review-candidate
    ((candidate Candidate) (brief Brief))
    -> Decision[Feedback Blocker]
    :effects ((uses-command probe_review))
    :lowering inline
    (command-result probe_review
      :argv ("python" "PROBE_REVIEW" candidate.title brief.goal)
      :returns Decision[Feedback Blocker]))
  (defproc revise-candidate
    ((candidate Candidate) (brief Brief) (feedback Feedback))
    -> Candidate
    :effects ((uses-command probe_revise))
    :lowering inline
    (command-result probe_revise
      :argv ("python" "PROBE_REVISE" candidate.title brief.goal feedback.note)
      :returns Candidate))
  (defworkflow run () -> Improvement[Candidate Feedback Blocker]
    (improve (record Candidate :title "SEED" :score 0)
             (record Brief :goal "tidy")
             (proc-ref review-candidate)
             (proc-ref revise-candidate)
             LIMIT)))
"""

BARE_IMPORT_232 = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.32")
  (defmodule grt/entry)
""" + IMPORT_LINE + """  (export run)
  (defrecord Out (n Int))
  (defworkflow run () -> Out (record Out :n 1)))
"""

PROVIDER_REVISE = """  (defproc revise-candidate
    ((candidate Candidate) (brief Brief) (feedback Feedback))
    -> Candidate
    :effects ((uses-provider providers.execute))
    :lowering inline
    (provider-result providers.execute
      :prompt prompts.implementation.execute
      :inputs (feedback.note)
      :returns Candidate))
"""


def entry_source(*, seed: str, limit: int, probes: dict[str, Path], target: str = "2.33") -> str:
    return (
        ENTRY.replace("PROBE_REVIEW", probes["probe_review"].as_posix())
        .replace("PROBE_REVISE", probes["probe_revise"].as_posix())
        .replace('"SEED"', f'"{seed}"')
        .replace("LIMIT", str(limit))
        .replace('(:target-dsl "2.33")', f'(:target-dsl "{target}")')
    )


def inline_entry_source(imported: str) -> str:
    """The same caller with the `std/improve` declarations pasted in place of the import."""

    library = STD_IMPROVE_PATH.read_text(encoding="utf-8")
    declarations = library[library.index("  (defunion Decision") :].rstrip()[:-1].rstrip()
    return imported.replace(IMPORT_LINE, "").replace("  (export run)\n", "  (export run)\n" + declarations + "\n")


def provider_revise_entry_source(imported: str) -> str:
    start = imported.index("  (defproc revise-candidate")
    end = imported.index("  (defworkflow run")
    return imported[:start] + PROVIDER_REVISE + imported[end:]
