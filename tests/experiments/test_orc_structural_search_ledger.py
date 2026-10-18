"""The planned maximum of one launch (ledger.max_provider_calls) over the module's own definitions."""

import pytest

from experiments.orc_structural_search.ledger import CallCapExceeded, max_provider_calls

MODULE = """(workflow-lisp
  (:language "0.1")
  (defmodule m)
  (defproc draft ((xs List[String])) -> List[String]
    (list/map-effect ((x xs)) :max {bound}
      (provider-result providers.coder :prompt x)))
  (defworkflow run ((task String) (n Int)) -> String
    (let* ((drafts (draft (list task task)))) task)))
"""


def test_a_helper_called_from_the_entry_plans_its_provider_calls_times_the_literal_max(tmp_path):
    (tmp_path / "m.orc").write_text(MODULE.format(bound=3))
    assert max_provider_calls(tmp_path / "m.orc", "run") == 3


def test_a_non_literal_max_around_a_provider_call_refuses_the_launch(tmp_path):
    (tmp_path / "m.orc").write_text(MODULE.format(bound="n"))
    with pytest.raises(CallCapExceeded, match="unbounded"):
        max_provider_calls(tmp_path / "m.orc", "run")
