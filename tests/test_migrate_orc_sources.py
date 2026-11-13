"""Behavioral tests for scripts/migrate_orc_sources.py: headers, clauses and `fn`-form loops."""

from __future__ import annotations

import json
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

    assert (path.read_text(encoding="utf-8"), f"left in fn form {path}:7: [reorder]" in result.stdout,
            "program hash changes" in result.stdout) == (BUDGET_FIRST, True, True), result.stdout


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


def test_python_plain_and_fstring_sources_are_rewritten_and_format_templates_left(tmp_path: Path) -> None:
    plain = f'PLAIN = """{NESTED_FN}"""'
    fstring = 'FSTRING = f"""' + _parameterized(NESTED_FN).replace("(done outer)", "(done {RESULT})") + '"""'
    template = 'TEMPLATE = """' + _parameterized(NESTED_FN) + '""".format(TARGET=TARGET)'
    path = _write(tmp_path / "tests" / "test_sample.py", _python_module(plain, fstring, template))

    result = _migrate(path)

    expected = _python_module(
        f'PLAIN = """{NESTED_BINDER}"""',
        'FSTRING = f"""' + _parameterized(NESTED_BINDER).replace("(done outer)", "(done {RESULT})") + '"""',
        template,
    )
    assert (path.read_text(encoding="utf-8"), "header `{TARGET}` is a parameter" in result.stdout,
            result.stdout.count("[substitution] operand of `.format(`")) == (expected, True, 2), result.stdout


def test_fstring_field_as_operand_is_unknown(tmp_path: Path) -> None:
    module = _python_module('LOOP = f"(loop/recur :max (budget 3) :state {SEED} (fn (s) (done s)))"')
    path = _write(tmp_path / "tests" / "test_sample.py", module)

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), "cannot be compiled" in result.stdout) == (module, True), result.stdout


def test_fstring_fields_and_braces_are_restored_exactly(tmp_path: Path) -> None:
    before = 'LOOP = f"(loop/recur :max {LIMIT} :state {{}} (fn ({NAME}) (done {NAME}.x)))"'
    path = _write(tmp_path / "tests" / "test_sample.py", _python_module(before))

    _migrate(path)

    assert path.read_text(encoding="utf-8") == _python_module(
        'LOOP = f"(loop/recur (({NAME} {{}})) :max {LIMIT} (done {NAME}.x))"')


def test_python_escape_sequences_are_kept_byte_for_byte(tmp_path: Path) -> None:
    before = r'LOOP = "(loop/recur :max 2 :state \"a\\tb\"\n  (fn (s) (done s)))"'
    path = _write(tmp_path / "tests" / "test_sample.py", _python_module(before))

    _migrate(path)

    assert path.read_text(encoding="utf-8") == _python_module(
        r'LOOP = "(loop/recur ((s \"a\\tb\")) :max 2\n  (done s))"')


def test_python_string_header_and_loop_are_migrated_together(tmp_path: Path) -> None:
    old = NESTED_FN.replace('"2.40"', '"2.37"')
    path = _write(tmp_path / "tests" / "test_sample.py", _python_module(f"SOURCE = '''{old}'''"))

    result = _migrate(path)

    assert path.read_text(encoding="utf-8") == _python_module(f"SOURCE = '''{NESTED_BINDER}'''"), result.stdout


def test_implicitly_concatenated_literals_keep_their_quotes_and_lines(tmp_path: Path) -> None:
    before = ("LOOP = ('(loop/recur :max 2 :state (loop-state (i Int 0)) :on-exhausted 0 (fn (state) '\n"
              "        '(let* ((x state.i)) (done x))))')")
    path = _write(tmp_path / "tests" / "test_sample.py", _python_module(before))

    _migrate(path)

    assert path.read_text(encoding="utf-8") == _python_module(
        "LOOP = ('(loop/recur ((state (loop-state (i Int 0)))) :max 2 :on-exhausted 0 '\n"
        "        '(let* ((x state.i)) (done x)))')")


def test_state_moved_across_literals_with_other_quotes_is_reencoded(tmp_path: Path) -> None:
    before = ('LOOP = ("(loop/recur :max 1 :state (record R\\n"\n'
              "        '   :status \"ready\")\\n'\n"
              '        "  (fn (state) (done state)))")')
    path = _write(tmp_path / "tests" / "test_sample.py", _python_module(before))

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


# --- review fixes ---------------------------------------------------------------------------

def _tool():
    import importlib.util

    spec = importlib.util.spec_from_file_location("migrate_orc_sources_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


def test_verify_reports_a_mismatch_under_an_unsound_rule(tmp_path: Path, monkeypatch, capsys) -> None:
    tool = _tool()
    monkeypatch.setattr(tool, "syntactic_rule", lambda loop: True)
    path = _write(tmp_path / "probe.orc", BUDGET_FIRST)

    code = tool.main(["--check", "--verify", str(path)])

    output = capsys.readouterr().out
    assert (code, "0 syntactic rewrites compiled with equal hash" in output, "1 mismatches" in output,
            "[mismatch]" in output) == (2, True, True, True), output


@pytest.mark.parametrize("before", [
    "(loop/recur :max (budget limit) :state (seed x) (fn (s) (done s)))",
    "(loop/recur :max lim{x} :state (seed 0) (fn (s) (done s)))",
])
def test_a_call_of_symbols_or_a_field_inside_a_symbol_is_not_an_atom(tmp_path: Path, before: str) -> None:
    module = _python_module(f'LOOP = f"{before}"')
    path = _write(tmp_path / "tests" / "test_sample.py", module)

    _migrate(path)

    assert path.read_text(encoding="utf-8") == module


def test_dedent_needs_every_later_line_at_least_as_deep_as_the_body(tmp_path: Path) -> None:
    source = "(loop/recur :max 2 :state 0\n  (fn (s)\n    (if (< 1 s)\n   (done s) (continue s))))\n"
    path = _write(tmp_path / "fragment.orc", source)

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), "1 bodies kept their indentation" in result.stdout) == (
        "(loop/recur ((s 0)) :max 2\n  (if (< 1 s)\n   (done s) (continue s)))\n", True), result.stdout


def test_a_multiline_state_is_reindented_by_the_distance_it_moves(tmp_path: Path) -> None:
    source = ("(loop/recur\n  :max 4\n  :state (record S\n           :round 1)\n  (fn (s) (done s)))\n")
    path = _write(tmp_path / "fragment.orc", source)

    _migrate(path)

    assert path.read_text(encoding="utf-8") == (
        "(loop/recur ((s (record S\n                  :round 1)))\n  :max 4\n  (done s))\n")


def test_a_multiline_state_split_over_literals_is_reindented_as_in_a_file(tmp_path: Path) -> None:
    loop = "(loop/recur\n  :max 4\n  :state (record S\n           :round 1)\n  (fn (s) (done s)))\n"
    path = _write(tmp_path / "fragment.orc", loop)
    module = _write(tmp_path / "tests" / "test_sample.py", _python_module(
        "LOOP = (" + "\n        ".join(repr(line) for line in loop.splitlines(keepends=True)) + ")"))

    _migrate(path, module)

    namespace: dict[str, object] = {}
    exec(module.read_text(encoding="utf-8"), namespace)
    assert namespace["LOOP"] == path.read_text(encoding="utf-8")


def test_a_loop_in_a_macro_template_is_compared_by_compiling(tmp_path: Path) -> None:
    source = _source("(grow 1)").replace(
        "  (defworkflow run",
        "  (defmacro grow (x) (let* ((tmp (seed x))) (loop/recur :max 2 :state tmp :on-exhausted s\n"
        "      (fn (s) (if (< 1 s) (done s) (continue (step s)))))))\n  (defworkflow run")
    path = _write(tmp_path / "probe.orc", source)

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), "1 rewritten with equal hash" in result.stdout) == (source.replace(
        "(loop/recur :max 2 :state tmp :on-exhausted s\n      (fn (s) (if (< 1 s) (done s) (continue (step s)))))",
        "(loop/recur ((s tmp)) :max 2 :on-exhausted s\n      (if (< 1 s) (done s) (continue (step s))))"), True), result.stdout


def test_a_loop_in_a_macro_template_that_cannot_be_compiled_is_left(tmp_path: Path) -> None:
    source = "(defmacro grow (x) (let* ((tmp (seed x))) (loop/recur :max 1 :state tmp (fn (s) (done s)))))\n"
    path = _write(tmp_path / "fragment.orc", source)

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), "[macro]" in result.stdout) == (source, True), result.stdout


OLD_SOURCE = NESTED_FN.replace('"2.40"', '"2.35"').replace(
    "(defproc seed ((n Int)) -> Int", "(defproc seed ((n Int)) -> Int :lowering inline")


def test_a_header_split_from_its_clauses_is_left_and_reported(tmp_path: Path) -> None:
    head, rest = OLD_SOURCE.split("\n", 1)
    module = _python_module("SOURCE = \"\\n\".join([\n    " + repr(head) + ",\n    '''" + rest + "''',\n])")
    path = _write(tmp_path / "tests" / "test_sample.py", module)

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), "[partial-source]" in result.stdout) == (module, True), result.stdout


@pytest.mark.parametrize("module", [
    # tests/test_workflow_evaluated_public_identity.py: count, then a header replace
    "assert source.count('(:target-dsl \"2.35\")') == 1\n"
    "path.write_text(source.replace('(:target-dsl \"2.35\")', '(:target-dsl \"2.36\")', 1))",
    # tests/test_workflow_lisp_host_input.py: pairs handed to a replacing helper
    "_confined(tmp_path, ('(:target-dsl \"2.38\")', '(:target-dsl \"2.40\")'), ('(export run)', '(export run)'))",
    # tests/test_phase2_exit_e2e.py: a count and an f-string replacement
    "assert source.count(SERIAL_MAP) == 1 and source.count('(:target-dsl \"2.35\")') == 1\n"
    "root.write_text(source.replace('(:target-dsl \"2.35\")', f'(:target-dsl \"{NEWEST}\")'))",
    # tests/test_workflow_evaluated_parallel_consumers.py: the same with a variable target
    "root.write_text(source.replace('(:target-dsl \"2.35\")', f'(:target-dsl \"{target}\")').replace(A, B))",
    # a fn-form loop used as a replacement needle, through a name
    "OLD = '(loop/recur :max 1 :state 0 (fn (s) (done s)))'\nsource = source.replace(OLD, NEW)",
    # a complete old source used as a `.replace` subject
    f"derived = '''{NESTED_FN.replace(chr(34) + '2.40' + chr(34), chr(34) + '2.35' + chr(34))}'''.replace('a', 'b')",
])
def test_text_patterns_and_partial_headers_are_never_touched(tmp_path: Path, module: str) -> None:
    text = _python_module(module)
    path = _write(tmp_path / "tests" / "test_sample.py", text)

    _migrate(path)

    assert path.read_text(encoding="utf-8") == text


def test_a_complete_old_source_in_one_literal_is_migrated(tmp_path: Path) -> None:
    path = _write(tmp_path / "tests" / "test_sample.py", _python_module(f"SOURCE = '''{OLD_SOURCE}'''"))

    _migrate(path)

    assert path.read_text(encoding="utf-8") == _python_module(
        "SOURCE = '''" + NESTED_BINDER + "'''")


def test_docstrings_and_expected_text_are_left(tmp_path: Path) -> None:
    text = _python_module(
        'def test_x():\n    """Rewrites (loop/recur :max 3 :state 0 (fn (s) (done s)))."""\n'
        '    assert render() == "(loop/recur :max 3 :state 0 (fn (s) (done s)))"')
    path = _write(tmp_path / "tests" / "test_sample.py", text)

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), "[docstring]" in result.stdout, "[comparison]" in result.stdout) == (
        text, True, True), result.stdout


def test_an_unreadable_orc_source_is_left_whole(tmp_path: Path) -> None:
    source = OLD_SOURCE.replace("(defproc seed ((n Int)) -> Int :lowering inline", "(defproc seed ((n Int)) -> Int :effects (")
    path = _write(tmp_path / "probe.orc", source)

    result = _migrate(path)

    assert (path.read_text(encoding="utf-8"), "[reader]" in result.stdout) == (source, True), result.stdout


def test_clause_words_inside_strings_and_comments_stay(tmp_path: Path) -> None:
    extra = ('  ; a comment that says :lowering inline\n'
             '  (defproc label ((n Int)) -> String ":lowering inline :effects (x)")\n  (defworkflow run')
    path = _write(tmp_path / "probe.orc", OLD_SOURCE.replace("  (defworkflow run", extra))

    _migrate(path)

    assert path.read_text(encoding="utf-8") == NESTED_BINDER.replace("  (defworkflow run", extra)


def test_crlf_line_endings_are_kept(tmp_path: Path) -> None:
    path = tmp_path / "probe.orc"
    path.write_bytes(NESTED_FN.replace("\n", "\r\n").encode("utf-8"))

    _migrate(path)

    assert path.read_bytes() == NESTED_BINDER.replace("\n", "\r\n").encode("utf-8")


def test_an_unreadable_file_is_reported_and_the_run_continues(tmp_path: Path) -> None:
    bad = tmp_path / "bad.orc"
    bad.write_bytes(b"\xff\xfe(loop/recur")
    good = _write(tmp_path / "probe.orc", NESTED_FN)

    result = _migrate(bad, tmp_path / "missing.orc", good)

    assert (good.read_text(encoding="utf-8"), result.stdout.count("error "), result.returncode) == (NESTED_BINDER, 2, 2), result.stdout


def test_report_lists_changed_files_and_hand_work(tmp_path: Path) -> None:
    good = _write(tmp_path / "probe.orc", NESTED_FN)
    left = _write(tmp_path / "budget.orc", BUDGET_FIRST.replace("(defmodule probe)", "(defmodule budget)"))
    report = tmp_path / "report.json"

    _migrate("--check", "--report", report, good, left)

    document = json.loads(report.read_text(encoding="utf-8"))
    assert ([row["path"] for row in document["changed"]],
            [(row["path"], row["line"], row["kind"], row["category"]) for row in document["hand_work"]]) == (
        [str(good)], [(str(left), 7, "loop", "reorder")])


def test_loops_stay_when_their_rewrite_moves_a_pattern_a_module_matches_against_the_file(tmp_path: Path) -> None:
    fixture = _write(tmp_path / "fixtures" / "grow.orc", OLD_ORC)
    named = _write(tmp_path / "fixtures" / "named.orc", NESTED_FN)
    other = _write(tmp_path / "fixtures" / "other.orc", NESTED_FN.replace("(defmodule probe)", "(defmodule other)"))
    _write(tmp_path / "tests" / "test_seed.py", 'from pathlib import Path\n\n'
           'SOURCE = (Path(__file__).parent / "fixtures/grow.orc").read_text()\n'
           'NAMED = "fixtures/named.orc"\n'
           'SEEDED = SOURCE.replace("(fn (pads)", "(fn (state)").replace("\\n", "\\r\\n")\n')
    report = tmp_path / "report.json"

    _migrate("--report", report, tmp_path)

    rows = json.loads(report.read_text(encoding="utf-8"))["hand_work"]
    header_only = OLD_ORC.replace('"2.38"', '"2.40"').replace("    :effects ((uses-command step)) :lowering inline\n", "")
    assert (fixture.read_text(encoding="utf-8"), named.read_text(encoding="utf-8"), other.read_text(encoding="utf-8"),
            {row["category"] for row in rows if row["path"] == str(fixture)}) == (
        header_only, NESTED_BINDER, NESTED_BINDER.replace("(defmodule probe)", "(defmodule other)"), {"pattern"})


def test_a_header_a_module_substitutes_is_migrated_and_listed(tmp_path: Path) -> None:
    fixture = _write(tmp_path / "fixtures" / "grow.orc", OLD_ORC)
    _write(tmp_path / "tests" / "test_targets.py", 'from pathlib import Path\n\n'
           'SOURCE = (Path(__file__).parent / "fixtures/grow.orc").read_text()\n'
           'OLDER = SOURCE.replace(\'(:target-dsl "2.38")\', \'(:target-dsl "2.37")\').replace(":lowering inline", "")\n')
    report = tmp_path / "report.json"

    _migrate("--report", report, tmp_path)

    rows = json.loads(report.read_text(encoding="utf-8"))["hand_work"]
    assert (fixture.read_text(encoding="utf-8") == NEW_ORC,
            [(row["kind"], row["category"]) for row in rows if row["path"] == str(fixture)]) == (
        True, [("literal", "pattern"), ("literal", "pattern")])


def test_a_loop_whose_fn_is_not_last_is_listed(tmp_path: Path) -> None:
    source = _source("(loop/recur :max 3 :state 0 (fn (s) (done s)) :on-exhausted 0)")
    path = _write(tmp_path / "probe.orc", source)
    report = tmp_path / "report.json"

    _migrate("--report", report, path)

    rows = json.loads(report.read_text(encoding="utf-8"))["hand_work"]
    assert (path.read_text(encoding="utf-8"), [(row["kind"], row["category"]) for row in rows]) == (
        source, [("loop", "malformed")])


def test_a_balanced_header_outside_a_whole_module_is_left_and_listed(tmp_path: Path) -> None:
    module = _write(tmp_path / "tests" / "test_sample.py", _python_module(
        'SOURCE = "\\n".join([\'(:target-dsl "2.35")\', "(defmodule probe)"])'))
    before = module.read_text(encoding="utf-8")
    report = tmp_path / "report.json"

    _migrate("--report", report, module)

    rows = json.loads(report.read_text(encoding="utf-8"))["hand_work"]
    assert (module.read_text(encoding="utf-8"), [row["category"] for row in rows]) == (before, ["partial-source"])


def test_python_outside_tests_and_experiments_is_left_and_listed(tmp_path: Path) -> None:
    message = '"or write the `fn` form `(loop/recur :max n :state init (fn (state) body))`"'
    module = _write(tmp_path / "orchestrator" / "workflow_lisp" / "expressions.py",
                    f"MESSAGE = (\n    {message}\n)\nHEADER = '(:target-dsl \"2.35\")'\n")
    before = module.read_text(encoding="utf-8")
    report = tmp_path / "report.json"

    _migrate("--report", report, tmp_path)

    rows = json.loads(report.read_text(encoding="utf-8"))["hand_work"]
    assert (module.read_text(encoding="utf-8"), [(row["line"], row["category"]) for row in rows]) == (
        before, [(2, "outside-sweep"), (4, "outside-sweep")])
