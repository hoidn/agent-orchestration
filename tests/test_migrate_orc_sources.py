"""Behavioral tests for scripts/migrate_orc_sources.py: headers, clauses and `fn`-form loops."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "migrate_orc_sources.py"

OLD_ORC = '''; a comment before the module stays
(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule grow) (export run)
  (defproc step ((n Int)) -> Int
    :effects ((uses-command step)) :lowering inline
    (command-result step :argv ("python" "step.py" n) :returns Int))
  ;; between forms
  (defworkflow run ((limit Int)) -> Int
    (loop/recur :max limit :state 0
      :on-exhausted (+ pads 100)
      (fn (pads)
        ;; inside the body
        (if (< 3 pads) (done pads) (continue (step pads)))))))
'''
NEW_ORC = '''; a comment before the module stays
(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule grow) (export run)
  (defproc step ((n Int)) -> Int
    (command-result step :argv ("python" "step.py" n) :returns Int))
  ;; between forms
  (defworkflow run ((limit Int)) -> Int
    (loop/recur ((pads 0)) :max limit
      :on-exhausted (+ pads 100)
      ;; inside the body
        (if (< 3 pads) (done pads) (continue (step pads))))))
'''

PROCEDURES = '''(defproc seed ((n Int)) -> Int (command-result seed :argv ("python" "seed.py" n) :returns Int))
  (defproc budget ((n Int)) -> Int (command-result budget :argv ("python" "budget.py" n) :returns Int))
  (defproc step ((n Int)) -> Int (command-result step :argv ("python" "step.py" n) :returns Int))'''


def _source(body: str, *, module: str = "probe", target: str = "2.40") -> str:
    return f'''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
  (defmodule {module}) (export run)
  {PROCEDURES}
  (defworkflow run () -> Int
    {body}))
'''


NESTED_FN = _source('''(loop/recur :max 2 :state 0 :on-exhausted outer
      (fn (outer) (if (< 1 outer) (done outer)
        (continue (loop/recur :state (seed outer) :max 3 :on-exhausted inner
          (fn (inner) (if (< 2 inner) (done inner) (continue (step inner)))))))))''')
NESTED_BINDER = _source('''(loop/recur ((outer 0)) :max 2 :on-exhausted outer
      (if (< 1 outer) (done outer)
        (continue (loop/recur ((inner (seed outer))) :max 3 :on-exhausted inner
          (if (< 2 inner) (done inner) (continue (step inner)))))))''')
BUDGET_FIRST = _source('''(loop/recur :max (budget 3) :state (seed 0) :on-exhausted s
      (fn (s) (if (< 2 s) (done s) (continue (step s)))))''')


def _migrate(*args: object) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=REPO, env=env,
                          capture_output=True, text=True, check=False)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_orc_file_gets_header_clauses_and_binder_loop_with_comments_kept(tmp_path: Path) -> None:
    path = _write(tmp_path / "grow.orc", OLD_ORC)

    result = _migrate(path)

    assert (result.returncode, path.read_text(encoding="utf-8")) == (0, NEW_ORC), result.stdout + result.stderr


def test_check_mode_reports_and_writes_nothing(tmp_path: Path) -> None:
    path = _write(tmp_path / "grow.orc", OLD_ORC)

    result = _migrate("--check", path)

    assert (result.returncode, path.read_text(encoding="utf-8"), "1 rewritten" in result.stdout) == (1, OLD_ORC, True)


def test_second_run_changes_nothing(tmp_path: Path) -> None:
    path = _write(tmp_path / "grow.orc", OLD_ORC)
    _migrate(path)

    result = _migrate("--check", path)

    assert (result.returncode, path.read_text(encoding="utf-8")) == (0, NEW_ORC), result.stdout


def test_nested_loops_are_both_rewritten(tmp_path: Path) -> None:
    path = _write(tmp_path / "probe.orc", NESTED_FN)

    result = _migrate(path)

    assert path.read_text(encoding="utf-8") == NESTED_BINDER, result.stdout + result.stderr


def test_loop_with_effects_in_max_then_state_is_left_and_listed(tmp_path: Path) -> None:
    path = _write(tmp_path / "probe.orc", BUDGET_FIRST)

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), f"left in fn form {path}:7: the program hash changes" in result.stdout) == (
        BUDGET_FIRST, True), result.stdout


def test_loop_in_a_source_that_does_not_build_is_left_and_listed(tmp_path: Path) -> None:
    broken = NESTED_FN.replace("(continue (step inner))", "(continue (step missing))")
    path = _write(tmp_path / "probe.orc", broken)

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), result.stdout.count("does not build")) == (broken, 2), result.stdout


def _python_module(*strings: str) -> str:
    return "import textwrap\n\nTARGET = '2.40'\n\n" + "\n\n".join(strings) + "\n"


def test_python_strings_are_rewritten_and_fstrings_and_parameters_skipped(tmp_path: Path) -> None:
    plain = f'PLAIN = """{NESTED_FN}"""'
    fstring = 'FSTRING = f"""' + NESTED_FN.replace('"2.40"', '"{TARGET}"').replace("(defmodule probe)", "(defmodule other)") + '"""'
    parameter = 'PARAMETER = """' + BUDGET_FIRST.replace('"2.40"', '"{TARGET}"') + '""".format(TARGET=TARGET)'
    path = _write(tmp_path / "test_sample.py", _python_module(plain, fstring, parameter))

    result = _migrate(path)

    expected = _python_module(f'PLAIN = """{NESTED_BINDER}"""', fstring, parameter)
    reasons = sorted(line.split(": ", 1)[1] for line in result.stdout.splitlines() if line.startswith("left in fn form"))
    assert (path.read_text(encoding="utf-8"), reasons) == (
        expected,
        ["inside an f-string"] * 2 + ["parameterized header `{TARGET}`"],
    ), result.stdout + result.stderr


def test_python_string_header_and_loop_are_migrated_together(tmp_path: Path) -> None:
    old = NESTED_FN.replace('"2.40"', '"2.37"')
    path = _write(tmp_path / "test_sample.py", _python_module(f"SOURCE = '''{old}'''"))

    result = _migrate(path)

    assert path.read_text(encoding="utf-8") == _python_module(f"SOURCE = '''{NESTED_BINDER}'''"), result.stdout
