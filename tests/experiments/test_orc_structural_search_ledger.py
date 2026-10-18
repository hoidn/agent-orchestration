"""The planned maximum of one launch (ledger.max_provider_calls) over the module's own definitions."""

import pytest

from experiments.orc_structural_search.ledger import CallCapExceeded, max_provider_calls

MODULE = """(workflow-lisp
  (:language "0.1")
  (defmodule m)
  (defproc draft ((xs List[String])) -> List[String]
    (list/map-effect ((x xs)) :max 3
      (provider-result providers.coder :prompt x)))
  (defworkflow run ((task String)) -> String
    (let* ((drafts (draft (list task task)))) task)))
"""
# the shape of a child the driver refuses as unbounded_calls (it compiles: driver test of the same name)
LOOP = """(workflow-lisp
  (:language "0.1")
  (defmodule m)
  (defworkflow run ((task String)) -> Change
    (let* ((tries 2))
      (loop/recur :max tries
        :state (record Change :summary "none" :account "none")
        :on-exhausted state
        (fn (state)
          (let* ((next (provider-result providers.coder :prompt task)))
            (done next)))))))
"""
# a binding named like its procedure is no call of it; a pure recursive defun reaches no provider call
BINDERS = """(workflow-lisp
  (:language "0.1")
  (defmodule m)
  (defun count-down ((n Int)) -> Int
    (if (= n 0) 0 (count-down (- n 1))))
  (defproc review ((task String)) -> Review
    (let* ((review (provider-result providers.reviewer :prompt task)))
      review))
  (defworkflow run ((task String)) -> Review
    (let* ((left (count-down 3)))
      (review task))))
"""


def test_a_helper_called_from_the_entry_plans_its_provider_calls_times_the_literal_max(tmp_path):
    (tmp_path / "m.orc").write_text(MODULE)
    assert max_provider_calls(tmp_path / "m.orc", "run") == 3


def test_a_loop_whose_max_is_a_variable_around_a_provider_call_refuses_the_launch(tmp_path):
    (tmp_path / "m.orc").write_text(LOOP)
    with pytest.raises(CallCapExceeded, match="unbounded"):
        max_provider_calls(tmp_path / "m.orc", "run")


def test_binder_names_are_not_calls_and_a_pure_recursive_defun_plans_nothing(tmp_path):
    (tmp_path / "m.orc").write_text(BINDERS)
    assert max_provider_calls(tmp_path / "m.orc", "run") == 1


def test_recursion_through_a_provider_call_refuses_the_launch(tmp_path):
    (tmp_path / "m.orc").write_text(BINDERS.replace("(provider-result providers.reviewer :prompt task)",
                                                    "(review (provider-result providers.reviewer :prompt task))"))
    with pytest.raises(CallCapExceeded, match="unbounded"):
        max_provider_calls(tmp_path / "m.orc", "run")
