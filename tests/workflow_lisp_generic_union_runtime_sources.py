"""Workflow Lisp sources and command probes for the generic-union runtime tests.

`tests/test_workflow_lisp_generic_unions_runtime.py` owns the assertions. The
probes append their argv to `<probe>.log` so tests can assert that committed
hook work is not replayed on resume.
"""

from __future__ import annotations


HEADER = '(workflow-lisp\n  (:language "0.1")\n  (:target-dsl "2.33")\n'


DECISION_LIB = HEADER + """  (defmodule grt/lib)
  (export Decision Box keep-first)
  (defunion Decision :forall (F B)
    (APPROVE (evidence F))
    (BLOCKED (reason B)))
  (defrecord Box (n Int))
  (defproc keep-first
    :forall (F B)
    ((decision Decision[F B]) (fallback F))
    -> Box
    :effects ()
    (record Box :n 1)))
"""


TRIVIAL_ENTRY = HEADER + """  (defmodule grt/entry)
  (import grt/lib :only (Decision))
  (export run)
  (defrecord Out (n Int))
  (defworkflow run () -> Out
    (record Out :n 1)))
"""


CALLING_ENTRY = HEADER + """  (defmodule grt/entry)
  (import grt/lib :only (Decision Box keep-first))
  (export run)
  (defrecord Note (text String))
  (defworkflow run () -> Box
    (keep-first (variant Decision[Note Note] APPROVE :evidence (record Note :text "a"))
                (record Note :text "b"))))
"""


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
    :effects ()
    :lowering inline
    (check subject)))
"""


CANDIDATE_CHECK = """  (defrecord Candidate (title String) (score Int))
  (defproc check-candidate
    ((candidate Candidate))
    -> Outcome[Candidate String]
    :effects ((uses-command probe_check))
    :lowering inline
    (command-result probe_check
      :argv ("python" "PROBE_CHECK" candidate.title)
      :returns Outcome[Candidate String]))
"""


LOOP_ENTRY = HEADER + """  (defmodule grt/entry)
  (import grt/lib :only (Outcome attempt))
  (export run)
""" + CANDIDATE_CHECK + """  (defworkflow run ((limit Int)) -> Outcome[Candidate String]
    (loop/recur :max limit
      :state (loop-state (current Candidate (record Candidate :title "seed" :score 0)))
      :on-exhausted (variant Outcome[Candidate String] ERROR :error "exhausted")
      (fn (state)
        (let* ((outcome (attempt state.current (proc-ref check-candidate))))
          (match outcome
            ((OK ok) (done outcome))
            ((ERROR err)
             (continue (loop-state :like state
                         :current (record Candidate :title err.error :score (+ state.current.score 1)))))))))))
"""


REVIEW_PROBE = """import json, os, sys
from pathlib import Path
title = sys.argv[1]
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(title + "\\n")
if title == "blocked":
    payload = {"variant": "BLOCKED", "reason": {"why": "refused-" + title}}
elif title.startswith("revised"):
    payload = {"variant": "APPROVE", "evidence": {"note": "ok-" + title}}
else:
    payload = {"variant": "REVISE", "feedback": {"note": "revised-" + title}}
bundle = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
if bundle:
    Path(bundle).parent.mkdir(parents=True, exist_ok=True)
    Path(bundle).write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps(payload))
"""


REVISE_PROBE = OUTCOME_PROBE.split("if title.startswith")[0] + """payload = {"title": title, "score": title.count("revised")}
bundle = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
if bundle:
    Path(bundle).parent.mkdir(parents=True, exist_ok=True)
    Path(bundle).write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps(payload))
"""


IMPROVE_LIB = HEADER + """  (defmodule grt/lib)
  (export Decision Improvement improve)
  (defunion Decision :forall (F B)
    (APPROVE (evidence F))
    (REVISE (feedback F))
    (BLOCKED (reason B)))
  (defunion Improvement :forall (S F B)
    (APPROVED (value S) (evidence F))
    (BLOCKED (value S) (reason B))
    (EXHAUSTED (value S)))
  (defproc improve
    :forall (S F B)
    ((initial S)
     (review ProcRef[(S) -> Decision[F B]])
     (revise ProcRef[(S F) -> S])
     (limit Int))
    :where ((S is-record))
    -> Improvement[S F B]
    :effects ()
    :lowering inline
    (loop/recur :max limit
      :state (loop-state (current S initial))
      :on-exhausted (variant Improvement[S F B] EXHAUSTED :value state.current)
      (fn (state)
        (let* ((decision (review state.current)))
          (match decision
            ((APPROVE a)
             (done (variant Improvement[S F B] APPROVED :value state.current :evidence a.evidence)))
            ((BLOCKED b)
             (done (variant Improvement[S F B] BLOCKED :value state.current :reason b.reason)))
            ((REVISE r)
             (let* ((next (revise state.current r.feedback)))
               (continue (loop-state :like state :current next))))))))))
"""


IMPROVE_ENTRY = HEADER + """  (defmodule grt/entry)
  (import grt/lib :only (Decision Improvement improve))
  (export run summarize)
  (defrecord Candidate (title String) (score Int))
  (defrecord Feedback (note String))
  (defrecord Blocker (why String))
  (defrecord Summary (title String) (status String) (note String))
  (defproc review-candidate
    ((candidate Candidate))
    -> Decision[Feedback Blocker]
    :effects ((uses-command probe_review))
    :lowering inline
    (command-result probe_review
      :argv ("python" "PROBE_REVIEW" candidate.title)
      :returns Decision[Feedback Blocker]))
  (defproc revise-candidate
    ((candidate Candidate) (feedback Feedback))
    -> Candidate
    :effects ((uses-command probe_revise))
    :lowering inline
    (command-result probe_revise
      :argv ("python" "PROBE_REVISE" feedback.note)
      :returns Candidate))
  (defworkflow run () -> Improvement[Candidate Feedback Blocker]
    (improve (record Candidate :title "SEED" :score 0)
             (proc-ref review-candidate) (proc-ref revise-candidate) LIMIT))
  (defworkflow summarize () -> Summary
    (let* ((result (improve (record Candidate :title "SEED" :score 0)
                            (proc-ref review-candidate) (proc-ref revise-candidate) LIMIT)))
      (match result
        ((APPROVED a) (record Summary :title a.value.title :status "approved" :note a.evidence.note))
        ((BLOCKED b) (record Summary :title b.value.title :status "blocked" :note b.reason.why))
        ((EXHAUSTED e) (record Summary :title e.value.title :status "exhausted" :note ""))))))
"""


RAW_REVIEW_PROBE = REVIEW_PROBE.replace(
    '{"variant": "BLOCKED", "reason": {"why": "refused-" + title}}', '{"variant": "BLOCKED", "note": "refused-" + title}'
).replace('{"variant": "APPROVE", "evidence": {"note": "ok-" + title}}', '{"variant": "APPROVE", "note": "ok-" + title}').replace(
    '{"variant": "REVISE", "feedback": {"note": "revised-" + title}}', '{"variant": "REVISE", "note": "revised-" + title}'
)


ADAPTER_REVIEW = """  (defunion RawVerdict
    (APPROVE (note String))
    (REVISE (note String))
    (BLOCKED (note String)))
  (defproc review-candidate
    ((candidate Candidate))
    -> Decision[Feedback Blocker]
    :effects ((uses-command probe_review))
    :lowering inline
    (let* ((raw (command-result probe_review
                  :argv ("python" "PROBE_REVIEW" candidate.title)
                  :returns RawVerdict)))
      (match raw
        ((APPROVE a) (variant Decision[Feedback Blocker] APPROVE :evidence (record Feedback :note a.note)))
        ((REVISE r) (variant Decision[Feedback Blocker] REVISE :feedback (record Feedback :note r.note)))
        ((BLOCKED b) (variant Decision[Feedback Blocker] BLOCKED :reason (record Blocker :why b.note))))))
"""


CLASSIFY_LIB = IMPROVE_LIB.replace(
    "(export Decision Improvement improve)", "(export Decision Improvement improve classify)"
).rstrip()[:-1] + """
  (defproc classify
    :forall (S F B)
    ((subject S) (review ProcRef[(S) -> Decision[F B]]))
    :where ((S is-record))
    -> Improvement[S F B]
    :effects ()
    :lowering inline
    (let* ((decision (review subject)))
      (match decision
        ((APPROVE a) (variant Improvement[S F B] APPROVED :value subject :evidence a.evidence))
        ((REVISE r) (variant Improvement[S F B] EXHAUSTED :value subject))
        ((BLOCKED b) (variant Improvement[S F B] BLOCKED :value subject :reason b.reason))))))
"""

TWO_INSTANCES_ENTRY = HEADER + """  (defmodule grt/entry)
  (import grt/lib :only (Decision Improvement classify))
  (export run)
  (defrecord Candidate (title String) (score Int))
  (defrecord Draft (title String) (words Int) (tag String))
  (defrecord Feedback (note String))
  (defrecord Blocker (why String))
  (defrecord Pair (first String) (second String))
  (defproc review-candidate ((candidate Candidate)) -> Decision[Feedback Blocker]
    :effects ((uses-command probe_review))
    :lowering inline
    (command-result probe_review :argv ("python" "PROBE_REVIEW" candidate.title) :returns Decision[Feedback Blocker]))
  (defproc review-draft ((draft Draft)) -> Decision[Feedback Blocker]
    :effects ((uses-command probe_review))
    :lowering inline
    (command-result probe_review :argv ("python" "PROBE_REVIEW" draft.title) :returns Decision[Feedback Blocker]))
  (defworkflow run () -> Pair
    (let* ((a (classify (record Candidate :title "revised-a" :score 1) (proc-ref review-candidate)))
           (b (classify (record Draft :title "blocked" :words 2 :tag "t") (proc-ref review-draft))))
      (record Pair
        :first (match a ((APPROVED x) x.value.title) ((BLOCKED y) y.reason.why) ((EXHAUSTED z) "exhausted"))
        :second (match b ((APPROVED x) x.value.title) ((BLOCKED y) y.reason.why) ((EXHAUSTED z) "exhausted"))))))
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
    :effects ()
    :lowering inline
    (variant Outcome[S String] OK :value x)))
"""

PROC_REF_PAYLOAD_ENTRY = HEADER + """  (defmodule grt/entry)
  (import grt/lib :only (Outcome make))
  (export run)
  (defrecord Out (n Int))
  (defproc inc ((n Int)) -> Out :effects () (record Out :n n))
  (defproc use-it
    ((n Int))
    -> Out
    :effects ()
    (let* ((o (make (proc-ref inc))))
      (record Out :n n)))
  (defworkflow run () -> Out
    (use-it 1)))
"""


LIST_PAYLOAD_ENTRY = HEADER + """  (defmodule grt/entry)
  (import grt/lib :only (Outcome))
  (export run)
  (defrecord Item (label String))
  (defproc fetch
    ((title String))
    -> Outcome[List[Item] String]
    :effects ((uses-command probe_check))
    :lowering inline
    (command-result probe_check
      :argv ("python" "PROBE_CHECK" title)
      :returns Outcome[List[Item] String]))
  (defworkflow run () -> Outcome[List[Item] String]
    (fetch "x")))
"""
