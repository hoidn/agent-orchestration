"""The identity invariant kit of `scripts/invariants/`, each script on a tree of two sources."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tests.agent_session_shims import closed_path

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "scripts" / "invariants"
BUILDS = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule tiny) (export run)
  (defworkflow run ((n Int)) -> Int (+ n 1)))
'''
REFUSED = BUILDS.replace("(defmodule tiny)", "(defmodule refused)").replace("(+ n 1)", "(+ missing 1)")
NAMES_A_PROVIDER = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule asks) (export run)
  (defprompt ask (:fills (q :text)) -> String "Answer {q}.")
  (defworkflow run ((q String)) -> String
    (provider-result providers.coder :model "m" :prompt (ask :q q))))
'''
NAMES_A_PROMPT_EXTERN = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule extern) (export run)
  (defworkflow run ((q String)) -> String
    (provider-result providers.worker.codex :prompt prompts.review :inputs (q) :returns String)))
'''


@pytest.fixture
def tree(tmp_path) -> Path:
    """What an export holds, as far as the kit reads it: sources under a corpus root and the corpus inventory."""
    root = tmp_path / "tree"
    (root / "workflows" / "examples").mkdir(parents=True)
    (root / "workflows" / "examples" / "tiny.orc").write_text(BUILDS, encoding="utf-8")
    (root / "workflows" / "examples" / "refused.orc").write_text(REFUSED, encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    shutil.copy(REPO / "tests" / "workflow_lisp_closed_program_corpus.py", root / "tests")
    return root


def _run(command: list[str], cwd: Path, tmp_path: Path, tree: Path | None = None) -> str:
    scratch = tmp_path / "scratch"
    scratch.mkdir(exist_ok=True)
    env = {**os.environ, "PATH": closed_path(REPO / "experiments" / "thread_m" / "no_provider"),
           "PYTHONPATH": os.pathsep.join(map(str, filter(None, [tree, REPO]))), "TMPDIR": str(scratch),
           "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout


def test_compile_all_records_each_source_without_machine_paths(tree, tmp_path):
    out = tmp_path / "compile.json"

    _run([sys.executable, str(KIT / "compile_all.py"), str(tree), str(out), "2"], tmp_path, tmp_path)

    rows = json.loads(out.read_text())
    assert {name: row["exit"] for name, row in rows.items()} == {
        "workflows/examples/tiny.orc": 0, "workflows/examples/refused.orc": 2}
    assert "sha256:" in rows["workflows/examples/tiny.orc"]["stdout"]
    assert str(tmp_path) not in out.read_text()
    assert not (tree / ".orchestrate").exists()


def test_compile_all_gives_a_source_that_names_a_provider_its_externs(tree, tmp_path):
    (tree / "workflows" / "examples" / "asks.orc").write_text(NAMES_A_PROVIDER, encoding="utf-8")
    out = tmp_path / "compile.json"

    printed = _run([sys.executable, str(KIT / "compile_all.py"), str(tree), str(out), "2"], tmp_path, tmp_path)

    assert json.loads(out.read_text())["workflows/examples/asks.orc"]["exit"] == 0
    assert printed.split() == "3 files; 2 built, 1 of them name a provider".split()


def test_compile_all_binds_dotted_provider_names_and_prompt_externs(tree, tmp_path):
    (tree / "workflows" / "examples" / "extern.orc").write_text(NAMES_A_PROMPT_EXTERN, encoding="utf-8")
    out = tmp_path / "compile.json"

    _run([sys.executable, str(KIT / "compile_all.py"), str(tree), str(out), "2"], tmp_path, tmp_path)

    assert json.loads(out.read_text())["workflows/examples/extern.orc"]["exit"] == 0


def test_digests_snapshots_the_corpus_of_the_tree_on_the_path(tree, tmp_path):
    out = tmp_path / "digests.json"

    _run([sys.executable, str(KIT / "digests.py"), str(out)], tree, tmp_path, tree)

    rows = json.loads(out.read_text())
    assert sorted(rows) == ["workflows/examples/refused.orc::run", "workflows/examples/tiny.orc::run"]
    assert rows["workflows/examples/tiny.orc::run"].startswith("sha256:")
    assert rows["workflows/examples/refused.orc::run"] == "Refused:name_unknown"


def test_program_digests_keeps_run_reference_programs_without_the_package_identity(tmp_path):
    def program(folder: str, identity: str, body: str) -> None:
        path = tmp_path / "basetemp" / folder / "run" / "closed_program.json"
        path.parent.mkdir(parents=True)
        config = base64.b64encode(json.dumps({"compiler_runtime_identity_digest": identity}).encode()).decode()
        path.write_text(json.dumps({"body": body, "compiler_runtime_identity_digest": identity, "config": config}))
    program("test_a0", "sha256:old", "x")
    program("test_b0", "sha256:new", "x")
    plain = tmp_path / "basetemp" / "test_c0" / "closed_program.json"
    plain.parent.mkdir(parents=True)
    plain.write_text(json.dumps({"body": "no run reference"}))
    out = tmp_path / "runref.json"

    _run([sys.executable, str(KIT / "program_digests.py"), str(tmp_path / "basetemp"), str(out)], tmp_path, tmp_path)

    rows = json.loads(out.read_text())
    assert sorted(rows) == ["test_a0", "test_b0"] and rows["test_a0"] == rows["test_b0"]


def test_wrapper_exports_a_revision_and_prints_the_hash_of_both_files(tree, tmp_path):
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "init.defaultBranch=main",
           "-c", "commit.gpgsign=false"]
    for arguments in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "tree"]):
        subprocess.run([*git, *arguments], cwd=tree, check=True, capture_output=True)
    out = tmp_path / "out"

    printed = _run(["bash", str(KIT / "inv.sh"), "HEAD", str(out)], tree, tmp_path)

    hashes = {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in ("compile.json", "digests.json")}
    assert [line.split()[0] for line in printed.splitlines()[-2:]] == [hashes["compile.json"], hashes["digests.json"]]
    assert list((tmp_path / "scratch").iterdir()) == []
