"""CF-1b Task 4: generic unions instantiated through specialization, end to end.

Contract: docs/design/workflow_lisp_parametric_type_system.md, "Proposed CF-1
First-Order Generic Unions"; transport obligations in
docs/design/workflow_lisp_composition_first.md sections 4, 9 and 10.

Hooks are command-backed probes (the supported deterministic route); every
probe appends its argv to a call log so tests can assert provider-free replay.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.test_workflow_lisp_generic_stdlib_composition import _execute_bundle

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


def _write_sources(root: Path, sources: dict[str, str]) -> Path:
    for relative, text in sources.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root / "grt" / "entry.orc"


def _compile(root: Path, *, probes: dict[str, Path] | None = None, validate_shared: bool = True):
    return compile_stage3_entrypoint(
        root / "grt" / "entry.orc",
        source_roots=(root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            name: ExternalToolBinding(name=name, stable_command=("python", path.as_posix()))
            for name, path in (probes or {}).items()
        },
        validate_shared=validate_shared,
        workspace_root=root,
        lowering_route=None,
    )


def test_uncalled_generic_with_applied_union_parameter_compiles(tmp_path: Path) -> None:
    """Addendum A: a generic template is not lowered before specialization."""

    _write_sources(tmp_path, {"grt/lib.orc": DECISION_LIB, "grt/entry.orc": TRIVIAL_ENTRY})

    result = _compile(tmp_path)

    assert "grt/entry::run" in result.validated_bundles_by_name


CALLING_ENTRY = HEADER + """  (defmodule grt/entry)
  (import grt/lib :only (Decision Box keep-first))
  (export run)
  (defrecord Note (text String))
  (defworkflow run () -> Box
    (keep-first (variant Decision[Note Note] APPROVE :evidence (record Note :text "a"))
                (record Note :text "b"))))
"""


def test_generic_with_applied_union_parameter_lowers_after_specialization(tmp_path: Path) -> None:
    _write_sources(tmp_path, {"grt/lib.orc": DECISION_LIB, "grt/entry.orc": CALLING_ENTRY})

    result = _compile(tmp_path)

    assert "grt/entry::run" in result.validated_bundles_by_name


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


def _write_probe(root: Path, name: str, text: str) -> Path:
    probe = root / f"{name}.py"
    probe.write_text(text, encoding="utf-8")
    return probe


def _run(result, workflow: str, root: Path) -> dict[str, object]:
    bundle = result.validated_bundles_by_name[workflow]
    outcome = _execute_bundle(bundle, workflow_path=root / "grt" / "entry.orc", workspace=root, run_id="run")
    assert outcome["status"] == "completed", outcome.get("error")
    return dict(outcome["workflow_outputs"])


@pytest.mark.parametrize(
    ("limit", "expected"),
    [
        (2, {"return__variant": "OK", "return__value__title": "revise-seed", "return__value__score": 1}),
        (1, {"return__variant": "ERROR", "return__error": "exhausted"}),
    ],
    ids=["matched-ok", "exhausted"],
)
def test_imported_generic_result_is_matched_and_returned_from_a_caller_loop(
    tmp_path: Path, limit: int, expected: dict[str, object]
) -> None:
    probe = _write_probe(tmp_path, "probe_check", OUTCOME_PROBE)
    entry = LOOP_ENTRY.replace("PROBE_CHECK", probe.as_posix()).replace(":max limit", f":max {limit}")
    _write_sources(tmp_path, {"grt/lib.orc": OUTCOME_LIB, "grt/entry.orc": entry.replace("((limit Int))", "()")})

    result = _compile(tmp_path, probes={"probe_check": probe})

    assert _run(result, "grt/entry::run", tmp_path) == expected


def test_variant_payload_record_is_populated_from_a_bound_name(tmp_path: Path) -> None:
    """Addendum D (F1): `:value ok.value` lowers without rebuilding the record."""

    probe = _write_probe(tmp_path, "probe_check", OUTCOME_PROBE)
    entry = LOOP_ENTRY.replace("PROBE_CHECK", probe.as_posix()).replace(":max limit", ":max 2")
    entry = entry.replace("((limit Int))", "()").replace(
        "((OK ok) (done outcome))",
        "((OK ok) (done (variant Outcome[Candidate String] OK :value ok.value)))",
    )
    _write_sources(tmp_path, {"grt/lib.orc": OUTCOME_LIB, "grt/entry.orc": entry})

    result = _compile(tmp_path, probes={"probe_check": probe})

    assert _run(result, "grt/entry::run", tmp_path) == {
        "return__variant": "OK",
        "return__value__title": "revise-seed",
        "return__value__score": 1,
    }


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


def _compile_improve(root: Path, *, seed: str, limit: int):
    probes = {
        "probe_review": _write_probe(root, "probe_review", REVIEW_PROBE),
        "probe_revise": _write_probe(root, "probe_revise", REVISE_PROBE),
    }
    entry = (
        IMPROVE_ENTRY.replace("PROBE_REVIEW", probes["probe_review"].as_posix())
        .replace("PROBE_REVISE", probes["probe_revise"].as_posix())
        .replace('"SEED"', f'"{seed}"')
        .replace("LIMIT", str(limit))
    )
    _write_sources(root, {"grt/lib.orc": IMPROVE_LIB, "grt/entry.orc": entry})
    return _compile(root, probes=probes)


@pytest.mark.parametrize(
    ("seed", "expected"),
    [
        (
            "seed",
            {
                "return__variant": "APPROVED",
                "return__value__title": "revised-seed",
                "return__value__score": 1,
                "return__evidence__note": "ok-revised-seed",
            },
        ),
        (
            "blocked",
            {
                "return__variant": "BLOCKED",
                "return__value__title": "blocked",
                "return__value__score": 0,
                "return__reason__why": "refused-blocked",
            },
        ),
    ],
    ids=["approved-after-revision", "blocked"],
)
def test_generic_loop_returns_variants_carrying_its_record_state(
    tmp_path: Path, seed: str, expected: dict[str, object]
) -> None:
    result = _compile_improve(tmp_path, seed=seed, limit=3)

    assert _run(result, "grt/entry::run", tmp_path) == expected
