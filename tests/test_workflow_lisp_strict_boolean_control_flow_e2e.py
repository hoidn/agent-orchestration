"""Public strict Bool effects, lazy operands and committed-boundary resume."""

import pytest
from tests.workflow_evaluated_totality_helpers import (
    CONTROL_PROBE, _public_run_files, _write_probe, _write_sources, exercise,
)


@pytest.mark.parametrize(("body", "expected", "calls"), [
    ('(not (check 1))', False, ['check 1']),
    ('(or (check 1) (check 0))', True, ['check 1']),
    ('(or (check 0) (check 1))', True, ['check 0', 'check 1']),
    ('(and (check 0) (check 1))', False, ['check 0']),
    ('(and (check 1) (check 0))', False, ['check 1', 'check 0']),
], ids=['not-once', 'or-short-circuit', 'or-left-to-right',
        'and-short-circuit', 'and-left-to-right'])
def test_public_boolean_effects_preserve_order_and_resume_without_replay(
    tmp_path, monkeypatch, body, expected, calls,
):
    probe = _write_probe(tmp_path, "probe", CONTROL_PROBE)
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule grt/entry) (export run)
      (defproc check ((n Int)) -> Bool
        :effects ((uses-command check)) :lowering inline
        (command-result check :argv ("python" "{probe.as_posix()}" "check" n) :returns Bool))
      (defworkflow run () -> Bool {body}))'''
    _write_sources(tmp_path, {"grt/entry.orc": source})
    files = _public_run_files(tmp_path, {"check": probe})
    files["workspace"] = tmp_path
    exercise(tmp_path, files,
             probe, expected, calls, monkeypatch)
