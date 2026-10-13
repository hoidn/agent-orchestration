"""Public REPL inspection, source lifecycle, and read-only evidence."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import selectors
import shlex
import shutil
import subprocess
import sys
import time

import pytest

from orchestrator.run_lock import run_writer_lock
from tests.test_workflow_evaluated_repl import (
    BODY, FEEDBACK, PLAN, SOURCE, _env, _fixture, _repl, _run, _run_root, _typed_values,
)
from tests.test_workflow_evaluated_resume import _snapshot


def _load_line(fixture):
    source, providers, prompts, _ = fixture
    return shlex.join((":load", str(source), "--source-root", str(source.parent),
                       "--provider-externs-file", str(providers), "--prompt-externs-file", str(prompts)))


def _type_results(stdout):
    lines = stdout.splitlines()
    return [(left.removeprefix("type: "), right.removeprefix("effects: "))
            for left, right in zip(lines, lines[1:])
            if left.startswith("type: ") and right.startswith("effects: ")]


@pytest.mark.parametrize("target", ["2.35", "2.36"])
def test_public_repl_module_introspection(tmp_path, target):
    source = SOURCE.format(target=target, body=BODY).replace(
        "(defmodule main)", "(defmodule main) (import library :as lib :only (Plan))"
    ).replace("  (defrecord Plan (steps List[String]))\n", "")
    fixture = _fixture(tmp_path, source)
    prompt = '(defprompt inspect-prompt (:fills (task :text) (steps :value List[String])) -> Plan "Fixture café {task} {steps}")'
    library = f'''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
      (defmodule library) (export Plan Status helper inspect-prompt)
      (defenum Status READY DONE)
      (defrecord Plan (steps List[String]))
      (defun helper ((input String)) -> String input)
      (defrecord Private (value String))
      {prompt})'''
    (tmp_path / "library.orc").write_text(library, encoding="utf-8")
    warm = _repl(tmp_path, [":quit"], fixture=fixture)
    assert warm.returncode == 0, warm.stderr
    before = _snapshot(tmp_path)
    repl = _repl(tmp_path, [
        ":browse", ":info Plan", ":info lib.Status", ":info lib.helper",
        ":info lib.inspect-prompt", ":source lib.inspect-prompt",
        r':type "two words with \"quoted\" and \\path"',
        ':type (list/length (list "two words" "another string"))',
        ':type (request-feedback "analysis only")', ":type (/ 1.0 0.0)",
        ':type (/ 1.0 (if (= "fixture" "fixture") 0.0 1.0))',
        ":type draft", ":info lib.Private", ":source String", ":quit",
    ], fixture=fixture)
    assert repl.returncode == 0, repl.stderr
    assert "module: main" in repl.stdout
    assert "steps: List[String]" in repl.stdout
    assert "members: READY, DONE" in repl.stdout
    assert "lib.helper" in repl.stdout and "library/helper" in repl.stdout
    assert "task: text" in repl.stdout and "steps: value" in repl.stdout
    assert prompt in repl.stdout
    assert "loaded snapshot: sha256:" in repl.stdout
    assert _type_results(repl.stdout)[:2] == [("String", "()"), ("Int", "()")]
    assert ("Float", "()") in _type_results(repl.stdout)
    assert any(ref == "Feedback" and "uses-provider(providers.review)" in effects
               for ref, effects in _type_results(repl.stdout))
    assert "[name_unknown]" in repl.stderr
    assert "[pure_expr_division_by_zero]" in repl.stderr
    assert "[repl_name_unknown]" in repl.stderr
    assert "[repl_source_unavailable]" in repl.stderr
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / "requests.jsonl").exists()
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_public_repl_argument_introspection_recovers(tmp_path):
    empty = _repl(tmp_path, [":browse", ":info Plan", ":source Plan", ":type 1", ":quit"])
    assert empty.returncode == 0, empty.stderr
    assert empty.stderr.count("[repl_module_required]") == 4
    fixture = _fixture(tmp_path)
    repl = _repl(tmp_path, [
        ":browse extra", ":info", ':info "Plan"', ":info (Plan)", ":info Plan Extra", ':info "unterminated',
        ":source", ':source "Plan"', ":source (Plan)", ":source Plan Extra", ':source "unterminated',
        ":type", ":type 1 2", ':type "unterminated', ":info Missing",
        ":help", ":type 7", ":info Plan", ":quit",
    ], fixture=fixture)
    assert repl.returncode == 0, repl.stderr
    assert repl.stderr.count("[repl_command_invalid]") == 11
    assert repl.stderr.count("[repl_expression_arity]") == 2
    assert "[frontend_parse_error]" in repl.stderr
    assert "[repl_name_unknown]" in repl.stderr
    assert _type_results(repl.stdout) == [("Int", "()")]
    assert "steps: List[String]" in repl.stdout
    for command in (":browse", ":info", ":source", ":type"):
        assert command in repl.stdout
    for family in ("named types", "functions", "procedures", "workflows", "prompts", "externs"):
        assert family in repl.stdout
    assert "macros" in repl.stdout and "specializations" in repl.stdout


@pytest.mark.parametrize("target", ["2.35", "2.36"])
def test_public_repl_attached_introspection_is_readonly_under_writer_lock(tmp_path, target):
    body = BODY.replace("(let* ((draft", '(let* ((Plan "lexical shadow") (draft')
    fixture = _fixture(tmp_path, SOURCE.format(target=target, body=body))
    run = _run(tmp_path, fixture, "task=fixture", "scale=2.0")
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    before, requests = _snapshot(tmp_path / ".orchestrate"), (tmp_path / "requests.jsonl").read_bytes()
    with run_writer_lock(run_root):
        repl = _repl(tmp_path, [
            ":browse", ":info Plan", ":source Plan", ":type Plan", ":type draft.steps",
            ":type (count-steps draft)", ":type (request-feedback task)",
            "(request-feedback task)", ":info draft", ":type Missing",
            "(count-steps draft)", ":bindings", ":result", ":quit",
        ], fixture=fixture, run_id=run_root.name)
    assert repl.returncode == 0, repl.stderr
    assert _type_results(repl.stdout)[:3] == [("String", "()"), ("List[String]", "()"), ("Int", "()")]
    assert any(ref == "Feedback" and "uses-provider(providers.review)" in effects
               for ref, effects in _type_results(repl.stdout))
    assert "record: Plan" in repl.stdout
    assert "[repl_effect_refused]" in repl.stderr and "[repl_name_unknown]" in repl.stderr
    assert "[name_unknown]" in repl.stderr
    assert _typed_values(repl.stdout) == [(2, "Int"), (FEEDBACK, "Feedback")]
    assert "Plan : String" in repl.stdout and "draft : Plan" in repl.stdout
    assert _snapshot(tmp_path / ".orchestrate") == before
    assert (tmp_path / "requests.jsonl").read_bytes() == requests


def test_public_repl_source_snapshot_survives_delete_failed_load_and_reload(tmp_path):
    original = '(defprompt snapshot-prompt (:fills (message :text)) -> Bool\n    "Fixture café {message}\\n")'
    replacement = original.replace("café", "updated")
    source = SOURCE.format(target="2.35", body=BODY).replace("(export run)", "(export run) " + original)
    fixture = _fixture(tmp_path, source)
    fixture[0].write_bytes(source.replace("\n", "\r\n").encode("utf-8"))
    broken = tmp_path / "broken.orc"
    broken.write_text("(workflow-lisp", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-B", "-u", "-m", "orchestrator", "repl"],
        cwd=tmp_path, env=_env(tmp_path), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    stdout, stderr = bytearray(), bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, stdout)
            selector.register(process.stderr, selectors.EVENT_READ, stderr)

            def send_ready(lines):
                mark = len(stdout)
                process.stdin.write(("\n".join((*lines, ':type "ready"')) + "\n").encode())
                process.stdin.flush()
                deadline = time.monotonic() + 60
                while b"effects: ()\n" not in stdout[mark:]:
                    remaining = deadline - time.monotonic()
                    assert remaining > 0, f"REPL readiness timed out: {bytes(stdout)!r}; {bytes(stderr)!r}"
                    for key, _ in selector.select(remaining):
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            pytest.fail(f"REPL exited before readiness: {bytes(stdout)!r}; {bytes(stderr)!r}")
                        key.data.extend(chunk)

            send_ready([_load_line(fixture)])
            fixture[0].unlink()
            before = _snapshot(tmp_path)
            send_ready([":source snapshot-prompt", f":load {broken}", ":source snapshot-prompt"])
            assert _snapshot(tmp_path) == before
            new_source = source.replace(original, replacement)
            fixture[0].write_text(new_source, encoding="utf-8")
            send_ready([_load_line(fixture), ":source snapshot-prompt"])
        tail_out, tail_err = process.communicate(b":quit\n", timeout=60)
        stdout.extend(tail_out)
        stderr.extend(tail_err)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
    assert process.returncode == 0, bytes(stderr)
    text = stdout.decode("utf-8")
    assert text.count(original) == 2
    assert text.count(replacement) == 1
    assert text.count("loaded snapshot: sha256:") == 3
    assert "[frontend_parse_error]" in stderr.decode()
    assert not (tmp_path / "requests.jsonl").exists()


def test_public_repl_introspection_load_and_attach_digest_states(tmp_path):
    fixture = _fixture(tmp_path)
    run = _run(tmp_path, fixture, "task=fixture", "scale=2.0")
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    compatible = tmp_path / "compatible" / "main.orc"
    compatible.parent.mkdir()
    text = fixture[0].read_text().replace("(list/length plan.steps))\n  (defun count-through-proc", "(list/length plan.steps) ; compatible fixture\n  )\n  (defun count-through-proc")
    compatible.write_text(text, encoding="utf-8")
    changed = tmp_path / "changed" / "main.orc"
    changed.parent.mkdir()
    changed.write_text(text.replace('"chosen-model"', '"changed-model"'), encoding="utf-8")
    before = _snapshot(run_root)
    requests = (tmp_path / "requests.jsonl").read_bytes()
    repl = _repl(tmp_path, [
        f":load {tmp_path / 'missing.orc'}", ":result",
        _load_line((compatible, *fixture[1:])), ":type draft.steps", ":source count-steps", ":result",
        _load_line((changed, *fixture[1:])), ":type draft.steps", ":bindings", ":result",
        f":attach {run_root.name}", ":info Plan", ":source count-steps", ":quit",
    ], fixture=fixture, run_id=run_root.name)
    assert repl.returncode == 0, repl.stderr
    assert "[workflow_lisp_cli_input_missing]" in repl.stderr
    assert "[resume_program_changed]" in repl.stderr
    assert "[name_unknown]" in repl.stderr
    assert repl.stderr.count("[repl_not_attached]") == 2
    assert _type_results(repl.stdout) == [("List[String]", "()")]
    assert _typed_values(repl.stdout) == [(FEEDBACK, "Feedback")] * 2
    assert "compatible fixture" in repl.stdout and "steps: List[String]" in repl.stdout
    assert _snapshot(run_root) == before
    assert (tmp_path / "requests.jsonl").read_bytes() == requests


def test_public_repl_introspection_recipe_source_is_fresh_and_does_not_publish_cache(tmp_path):
    fixture = _fixture(tmp_path)
    run = _run(tmp_path, fixture, "task=fixture", "scale=2.0")
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    source = fixture[0]
    source.write_text(source.read_text().replace(
        "(defun count-steps ((plan Plan)) -> Int", "(defun count-steps ((plan Plan)) -> Int\n    ; reconstructed fixture marker\n    "), encoding="utf-8")
    cache = tmp_path / ".orchestrate" / "build"
    shutil.rmtree(cache, ignore_errors=True)
    before = _snapshot(tmp_path / ".orchestrate")
    requests = (tmp_path / "requests.jsonl").read_bytes()
    repl = _repl(tmp_path, [":browse", ":source count-steps", ":type draft.steps", ":result", ":quit"], run_id=run_root.name)
    assert repl.returncode == 0, repl.stderr
    assert "reconstructed module source: sha256:" in repl.stdout
    assert "reconstructed fixture marker" in repl.stdout
    assert "loaded snapshot" not in repl.stdout
    assert _type_results(repl.stdout) == [("List[String]", "()")]
    assert _typed_values(repl.stdout) == [(FEEDBACK, "Feedback")]
    assert not cache.exists()
    assert _snapshot(tmp_path / ".orchestrate") == before
    assert (tmp_path / "requests.jsonl").read_bytes() == requests


def test_public_repl_introspection_dispatch_preserves_builder_and_capture(tmp_path, monkeypatch, capsys):
    from orchestrator.cli.commands import repl as cli
    from orchestrator.workflow_lisp import repl_expr
    fixture = _fixture(tmp_path)
    run = _run(tmp_path, fixture, "task=fixture", "scale=2.0")
    assert run.returncode == 0, run.stderr
    run_root = _run_root(tmp_path)
    monkeypatch.chdir(tmp_path)
    session = cli.ReplSession(tmp_path, None)
    cli._dispatch(session, _load_line(fixture))
    cli._dispatch(session, f":attach {run_root.name}")
    builder = session.module.builder
    before = deepcopy((builder.definitions, builder.nominal_types))
    capture, frame = session.captured, session.captured.environment
    bindings = dict(frame.bindings)
    for line in (":browse", ":info Plan", ":source count-steps", ":type draft.steps", ":type (request-feedback task)"):
        assert cli._dispatch(session, line)
    with pytest.raises(repl_expr.ReplRefusal) as error:
        cli._dispatch(session, ":source providers.review")
    assert error.value.code == "repl_source_unavailable"
    assert (builder.definitions, builder.nominal_types) == before
    assert session.captured is capture and session.captured.environment is frame
    assert dict(frame.bindings) == bindings
    assert "effects:" in capsys.readouterr().out
