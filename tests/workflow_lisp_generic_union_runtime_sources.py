"""Workflow Lisp sources and command probes for the generic-union runtime tests.

`tests/test_workflow_lisp_generic_unions_runtime.py` owns the assertions. The
probes append their argv to `<probe>.log` so tests can assert that committed
hook work is not replayed on resume.
"""

from __future__ import annotations


HEADER = '(workflow-lisp\n  (:language "0.1")\n  (:target-dsl "2.40")\n'


OUTCOME_PROBE = """import json, os, sys
from pathlib import Path
title = sys.argv[1]
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(title + "\\n")
if title.startswith("revise"):
    payload = {"variant": "OK", "value": {"title": title, "score": title.count("revise")}}
else:
    payload = {"variant": "ERROR", "error": "revise-" + title}
bundle = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
if bundle:
    Path(bundle).parent.mkdir(parents=True, exist_ok=True)
    Path(bundle).write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps(payload))
"""


OUTCOME_LIB = HEADER + """  (defmodule grt/lib)
  (export Outcome attempt)
  (defunion Outcome :forall (T E)
    (OK (value T))
    (ERROR (error E)))
  (defproc attempt
    :forall (S)
    ((subject S)
     (check ProcRef[(S) -> Outcome[S String]]))
    :where ((S is-record))
    -> Outcome[S String]
    (check subject)))
"""


CANDIDATE_CHECK = """  (defrecord Candidate (title String) (score Int))
  (defproc check-candidate
    ((candidate Candidate))
    -> Outcome[Candidate String]
    (command-result probe_check
      :argv ("python" "PROBE_CHECK" candidate.title)
      :returns Outcome[Candidate String]))
"""


MAKE_LIB = HEADER + """  (defmodule grt/lib)
  (export Outcome make)
  (defunion Outcome :forall (T E)
    (OK (value T))
    (ERROR (error E)))
  (defproc make
    :forall (S)
    ((x S))
    -> Outcome[S String]
    (variant Outcome[S String] OK :value x)))
"""

PROC_REF_PAYLOAD_ENTRY = HEADER + """  (defmodule grt/entry)
  (import grt/lib :only (Outcome make))
  (export run)
  (defrecord Out (n Int))
  (defproc inc ((n Int)) -> Out
    (record Out :n n))
  (defproc use-it
    ((n Int))
    -> Out
    (let* ((o (make (proc-ref inc))))
      (record Out :n n)))
  (defworkflow run () -> Out
    (use-it 1)))
"""
