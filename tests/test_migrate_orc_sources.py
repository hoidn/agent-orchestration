"""Behavioral tests for scripts/migrate_orc_sources.py: headers, clauses and `fn`-form loops."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


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


def test_orc_file_gets_header_clauses_and_dedented_binder_loop_with_comments_kept(tmp_path: Path) -> None:
    path = _write(tmp_path / "grow.orc", OLD_ORC)

    result = _migrate(path)

    assert (result.returncode, path.read_text(encoding="utf-8")) == (0, NEW_ORC), result.stdout + result.stderr


def test_check_mode_reports_and_writes_nothing(tmp_path: Path) -> None:
    path = _write(tmp_path / "grow.orc", OLD_ORC)

    result = _migrate("--check", path)

    assert (result.returncode, path.read_text(encoding="utf-8"), "1 rewritten by the syntactic rule" in result.stdout) == (
        1, OLD_ORC, True), result.stdout


def test_second_run_changes_nothing(tmp_path: Path) -> None:
    path = _write(tmp_path / "grow.orc", OLD_ORC)
    _migrate(path)

    result = _migrate("--check", path)

    assert (result.returncode, path.read_text(encoding="utf-8")) == (0, NEW_ORC), result.stdout


def test_nested_loops_are_both_rewritten(tmp_path: Path) -> None:
    path = _write(tmp_path / "probe.orc", NESTED_FN)

    result = _migrate(path)

    assert path.read_text(encoding="utf-8") == NESTED_BINDER, result.stdout + result.stderr


# The syntactic rule, one branch per test, on headerless fragments: nothing can be compiled there, so
# a rewrite proves the rule decided it alone.
FRAGMENTS = {
    "state_written_first": (
        "(loop/recur :state (seed 0) :max (budget 3) (fn (s) (done s)))",
        "(loop/recur ((s (seed 0))) :max (budget 3) (done s))",
    ),
    "atomic_max_symbol": (
        "(loop/recur :max limit :state (seed 0) (fn (s) (done s)))",
        "(loop/recur ((s (seed 0))) :max limit (done s))",
    ),
    "atomic_max_field": (
        "(loop/recur :max c.r :state (seed 0) (fn (s) (done s)))",
        "(loop/recur ((s (seed 0))) :max c.r (done s))",
    ),
    "atomic_state": (
        "(loop/recur :max (budget 3) :state 0 (fn (s) (done s)))",
        "(loop/recur ((s 0)) :max (budget 3) (done s))",
    ),
    "constant_record_state": (
        "(loop/recur :max (budget 3) :state (record S :round 1 :history (list)) (fn (s) (done s)))",
        "(loop/recur ((s (record S :round 1 :history (list)))) :max (budget 3) (done s))",
    ),
    "constant_loop_state": (
        "(loop/recur :max (budget 3) :state (loop-state (i Int 0) (seen List[Int] (list))) (fn (s) (done s)))",
        "(loop/recur ((s (loop-state (i Int 0) (seen List[Int] (list))))) :max (budget 3) (done s))",
    ),
}


@pytest.mark.parametrize("case", sorted(FRAGMENTS))
def test_syntactic_rule_rewrites_without_compiling(tmp_path: Path, case: str) -> None:
    before, after = FRAGMENTS[case]
    path = _write(tmp_path / "fragment.orc", before + "\n")

    result = _migrate(path)

    assert path.read_text(encoding="utf-8") == after + "\n", result.stdout


@pytest.mark.parametrize("before", [
    "(loop/recur :max (budget 3) :state (seed 0) (fn (s) (done s)))",
    "(loop/recur :max (budget 3) :state (record S :n (seed 0)) (fn (s) (done s)))",
    "(loop/recur :max (+ n 1) :state (seed 0) (fn (s) (done s)))",
])
def test_effect_capable_operands_with_max_first_are_not_rewritten_syntactically(tmp_path: Path, before: str) -> None:
    path = _write(tmp_path / "fragment.orc", before + "\n")

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), "a source without a literal header cannot be compiled" in result.stdout) == (
        before + "\n", True), result.stdout


def test_macro_parameter_is_not_an_atom(tmp_path: Path) -> None:
    source = "(defmacro bounded (limit) (loop/recur :max limit :state (seed 0) (fn (s) (done s))))\n"
    path = _write(tmp_path / "fragment.orc", source)

    result = _migrate(path)

    assert path.read_text(encoding="utf-8") == source, result.stdout


def test_loop_with_effects_in_max_then_state_is_compared_and_left(tmp_path: Path) -> None:
    path = _write(tmp_path / "probe.orc", BUDGET_FIRST)

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), f"left in fn form {path}:7: the program hash changes" in result.stdout) == (
        BUDGET_FIRST, True), result.stdout


def test_loop_outside_the_rule_is_rewritten_when_its_hash_is_equal(tmp_path: Path) -> None:
    source = BUDGET_FIRST.replace(":state (seed 0)", ":state (+ 0 1)")
    path = _write(tmp_path / "probe.orc", source)

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), "1 rewritten with equal hash" in result.stdout) == (source.replace(
        "(loop/recur :max (budget 3) :state (+ 0 1) :on-exhausted s\n      (fn (s) (if (< 2 s) (done s) (continue (step s)))))",
        "(loop/recur ((s (+ 0 1))) :max (budget 3) :on-exhausted s\n      (if (< 2 s) (done s) (continue (step s))))"), True), result.stdout


def test_source_that_does_not_build_is_rewritten_by_the_rule(tmp_path: Path) -> None:
    broken = NESTED_FN.replace("(continue (step inner))", "(continue (step missing))")
    path = _write(tmp_path / "probe.orc", broken)

    _migrate(path)

    assert path.read_text(encoding="utf-8") == NESTED_BINDER.replace("(continue (step inner))", "(continue (step missing))")


def test_library_module_without_workflow_and_older_target_are_rewritten(tmp_path: Path) -> None:
    source = ('(workflow-lisp (:language "0.1") (:target-dsl "2.30")\n  (defmodule lib) (export grow)\n'
              '  (defproc grow ((n Int)) -> Int (loop/recur :max n :state 0 (fn (k) (done k)))))\n')
    path = _write(tmp_path / "lib.orc", source)

    _migrate(path)

    assert path.read_text(encoding="utf-8") == source.replace(
        "(loop/recur :max n :state 0 (fn (k) (done k)))", "(loop/recur ((k 0)) :max n (done k))")


def test_body_shallower_than_its_first_line_keeps_its_indentation(tmp_path: Path) -> None:
    source = "(loop/recur :max 2 :state 0\n  (fn (s) (if (< 1 s)\n    (done s) (continue s))))\n"
    path = _write(tmp_path / "fragment.orc", source)

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), "1 bodies kept their indentation" in result.stdout) == (
        "(loop/recur ((s 0)) :max 2\n  (if (< 1 s)\n    (done s) (continue s)))\n", True), result.stdout


def test_verify_compiles_syntactic_rewrites(tmp_path: Path) -> None:
    path = _write(tmp_path / "probe.orc", NESTED_FN)

    result = _migrate("--check", "--verify", path)

    assert "verify: 2 syntactic rewrites compiled with equal hash, 0 could not be compiled, 0 mismatches" in result.stdout, result.stdout


def _python_module(*strings: str) -> str:
    return "import textwrap\n\nTARGET = '2.40'\n\n" + "\n\n".join(strings) + "\n"


def _parameterized(source: str) -> str:
    return source.replace('"2.40"', '"{TARGET}"')


def test_python_plain_fstring_and_parameterized_strings_are_rewritten(tmp_path: Path) -> None:
    plain = f'PLAIN = """{NESTED_FN}"""'
    fstring = 'FSTRING = f"""' + _parameterized(NESTED_FN).replace("(done outer)", "(done {RESULT})") + '"""'
    parameter = 'PARAMETER = """' + _parameterized(NESTED_FN) + '""".format(TARGET=TARGET)'
    path = _write(tmp_path / "test_sample.py", _python_module(plain, fstring, parameter))

    result = _migrate(path)

    expected = _python_module(
        f'PLAIN = """{NESTED_BINDER}"""',
        'FSTRING = f"""' + _parameterized(NESTED_BINDER).replace("(done outer)", "(done {RESULT})") + '"""',
        'PARAMETER = """' + _parameterized(NESTED_BINDER) + '""".format(TARGET=TARGET)',
    )
    assert (path.read_text(encoding="utf-8"), result.stdout.count("is a parameter, left to the caller")) == (expected, 2), result.stdout


def test_fstring_field_as_operand_is_unknown(tmp_path: Path) -> None:
    module = _python_module('LOOP = f"(loop/recur :max (budget 3) :state {SEED} (fn (s) (done s)))"')
    path = _write(tmp_path / "test_sample.py", module)

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), "cannot be compiled" in result.stdout) == (module, True), result.stdout


def test_fstring_fields_and_braces_are_restored_exactly(tmp_path: Path) -> None:
    before = 'LOOP = f"(loop/recur :max {LIMIT} :state {{}} (fn ({NAME}) (done {NAME}.x)))"'
    path = _write(tmp_path / "test_sample.py", _python_module(before))

    _migrate(path)

    assert path.read_text(encoding="utf-8") == _python_module(
        'LOOP = f"(loop/recur (({NAME} {{}})) :max {LIMIT} (done {NAME}.x))"')


def test_python_escape_sequences_are_kept_byte_for_byte(tmp_path: Path) -> None:
    before = r'LOOP = "(loop/recur :max 2 :state \"a\\tb\"\n  (fn (s) (done s)))"'
    path = _write(tmp_path / "test_sample.py", _python_module(before))

    _migrate(path)

    assert path.read_text(encoding="utf-8") == _python_module(
        r'LOOP = "(loop/recur ((s \"a\\tb\")) :max 2\n  (done s))"')


def test_python_string_header_and_loop_are_migrated_together(tmp_path: Path) -> None:
    old = NESTED_FN.replace('"2.40"', '"2.37"')
    path = _write(tmp_path / "test_sample.py", _python_module(f"SOURCE = '''{old}'''"))

    result = _migrate(path)

    assert path.read_text(encoding="utf-8") == _python_module(f"SOURCE = '''{NESTED_BINDER}'''"), result.stdout


def test_implicitly_concatenated_literals_keep_their_quotes_and_lines(tmp_path: Path) -> None:
    before = ("LOOP = ('(loop/recur :max 2 :state (loop-state (i Int 0)) :on-exhausted 0 (fn (state) '\n"
              "        '(let* ((x state.i)) (done x))))')")
    path = _write(tmp_path / "test_sample.py", _python_module(before))

    _migrate(path)

    assert path.read_text(encoding="utf-8") == _python_module(
        "LOOP = ('(loop/recur ((state (loop-state (i Int 0)))) :max 2 :on-exhausted 0 '\n"
        "        '(let* ((x state.i)) (done x)))')")


def test_state_moved_across_literals_with_other_quotes_is_reencoded(tmp_path: Path) -> None:
    before = ('LOOP = ("(loop/recur :max 1 :state (record R\\n"\n'
              "        '   :status \"ready\")\\n'\n"
              '        "  (fn (state) (done state)))")')
    path = _write(tmp_path / "test_sample.py", _python_module(before))

    _migrate(path)

    namespace: dict[str, object] = {}
    exec(path.read_text(encoding="utf-8"), namespace)
    assert namespace["LOOP"] == '(loop/recur ((state (record R\n   :status "ready"))) :max 1\n  (done state))'


def test_a_directory_skips_the_tools_own_fixtures_unless_named(tmp_path: Path) -> None:
    own = _write(tmp_path / "tests" / "test_migrate_orc_sources.py", _python_module(f'S = """{NESTED_FN}"""'))
    other = _write(tmp_path / "tests" / "test_other.py", _python_module(f'S = """{NESTED_FN}"""'))

    _migrate(tmp_path / "tests")
    walked = (own.read_text(encoding="utf-8"), other.read_text(encoding="utf-8"))
    _migrate(own)

    assert (walked, own.read_text(encoding="utf-8")) == (
        (_python_module(f'S = """{NESTED_FN}"""'), _python_module(f'S = """{NESTED_BINDER}"""')),
        _python_module(f'S = """{NESTED_BINDER}"""'),
    )
