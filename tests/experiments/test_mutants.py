"""Tests of the mechanical mutation operators (Phase 6 readiness R3, Task T1).

Plan: docs/plans/2026-11-13-phase-6-mutant-generator-plan.md. No test compiles or runs anything:
a mutant is a string, re-read here with the package's reader. `SEED` is the only source the
default suite mutates until T6. It is spelled the way the frozen seed will be (ruling M8): effort
per role is a string literal at each call site, model per role is an entry input.

The sample relies on `random.Random(seed).random()` only, the one method whose sequence the
Python documentation fixes across versions. Written and run under Python 3.13.9.
"""

import pytest

from experiments.mutants import operators
from experiments.mutants.operators import Mutation
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr, StringAtom

# The closed sets, written out: `operators.py` may not hold a Fable model, a model above the
# Sonnet ceiling or an undeclared effort (AGENTS.md, experiment rules).
MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")
EFFORTS = ("low", "medium", "high", "xhigh", "max")

SEED = r"""(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule fixture) (export run)
  (defrecord Change (summary String)) (defrecord CheckReport (passed Bool) (excerpt String))
  (defunion Verdict (MET (evidence String)) (NOT_MET (reason String)))
  (defunion Outcome (DONE (summary String)) (BLOCKED (reason String)))
  (defprompt plan (:fills (task :text) (repo :text)) -> Change
    "Work in {repo}. Plan the task below. Write no code.\n\nTask: {task}")
  (defprompt work (:fills (repo :text) (plan :value Change) (note :text)) -> Change
    "Work in {repo}. Carry out this plan: {plan}. The last review said \"{note}\".")
  (defprompt review (:fills (repo :text) (report :value CheckReport)) -> Verdict
    "Review {repo}. The check reported: {report}. MET if the goal is reached.")
  (defworkflow run ((task String) (repo String) (planner String) (coder String) (reviewer String)) -> Outcome
    (let* ((plan (provider-result providers.planner :model planner :effort "medium" :timeout-sec 1200
                   :prompt (plan :task task :repo repo))))
      (loop/recur :max 2 :state (loop-state (note String ""))
        :on-exhausted (variant Outcome BLOCKED :reason "round limit reached")
        (fn (state)
          (let* ((change (provider-result providers.coder :model coder :effort "medium" :timeout-sec 3600
                           :prompt (work :repo repo :plan plan :note state.note)))
                 (report (command-result dev-check :returns CheckReport)))
            (match (provider-result providers.reviewer :model reviewer :effort "medium" :timeout-sec 1200
                     :prompt (review :repo repo :report report))
              ((MET met) (done (variant Outcome DONE :summary met.evidence)))
              ((NOT_MET gap) (continue (loop-state :like state :note gap.reason))))))))))
"""


def read(text: str) -> ListExpr:
    return read_sexpr_text(text, source_path="<test>")


def shape(node):
    """A form without its spans, so that two readings compare equal."""
    if isinstance(node, ListExpr):
        return tuple(shape(item) for item in node.items)
    return type(node).__name__, node.value


def lists(node):
    """Every list at or under `node`, in document order."""
    if isinstance(node, ListExpr):
        yield node
        for item in node.items:
            yield from lists(item)


def headed(text: str, head: str) -> list[ListExpr]:
    return [form for form in lists(read(text)) if form.items and getattr(form.items[0], "value", None) == head]


def operand(form: ListExpr, key: str):
    """The item after the keyword `key` among the form's own items, or None."""
    for item, after in zip(form.items, form.items[1:]):
        if isinstance(item, KeywordAtom) and item.value == key:
            return after
    return None


def test_the_closed_sets_are_the_declared_ones():
    assert (operators.MODELS, operators.EFFORTS) == (MODELS, EFFORTS)


def test_apply_splices_disjoint_edits_given_in_any_order():
    mutation = Mutation("graft", "0<-1", ((4, 6, "Z"), (0, 2, "long")))
    assert operators.apply("abcdef", mutation) == "longcdZ"


@pytest.mark.parametrize("edits", [((0, 3, "X"), (2, 4, "Y")), ((2, 4, "Y"), (0, 3, "X")), ((4, 9, "X"),)])
def test_apply_refuses_overlapping_edits(edits):
    with pytest.raises(ValueError):
        operators.apply("abcdef", Mutation("graft", "0<-1", edits))
