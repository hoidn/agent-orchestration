from __future__ import annotations

import py_compile
import sys
from pathlib import Path

import pytest

import orchestrator.workflow.evaluated.runtime as runtime_module
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import memo_writer_lock, read_memo
from tests.test_workflow_evaluated_command_lifecycle import _InterruptedRun, _program, _publish

BODY = '(command-result emit :argv ("python" "tool") :returns Int)'
MAIN = (
    "import os\nfrom pathlib import Path\nimport helper\n"
    'Path("dispatches.txt").open("a", encoding="utf-8").write("x\\n")\n'
    "{during}"
    'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(str(helper.VALUE), encoding="utf-8")\n'
)


def _cache_file(tool: Path) -> Path:
    return tool / "__pycache__" / f"helper.{sys.implementation.cache_tag}.pyc"


def _package(root: Path, *, during: str = "") -> Path:
    tool = root / "tool"
    tool.mkdir()
    (tool / "helper.py").write_text("VALUE = 5\n", encoding="utf-8")
    (tool / "__main__.py").write_text(MAIN.format(during=during), encoding="utf-8")
    return tool


def _records(authority, program) -> list[str]:
    return [entry.data["record"] for entry in read_memo(authority.memo_path, site_classes(program)).entries]


def _committed_then_interrupted(root: Path, monkeypatch: pytest.MonkeyPatch, program):
    real_append = runtime_module.append_record

    def interrupt_after_commit(path, record, **kwargs):
        entry = real_append(path, record, **kwargs)
        if record.get("record") == "committed":
            raise _InterruptedRun()
        return entry

    with _publish(root, program) as authority, monkeypatch.context() as patched:
        patched.setattr(runtime_module, "append_record", interrupt_after_commit)
        with pytest.raises(_InterruptedRun):
            runtime_module.execute_pure_run(authority, {}, run_id="run-1", workspace=root)
    return load_run_authority(root / ".state" / "runs" / "run-1")


def _resume(authority, root: Path):
    with memo_writer_lock(authority.run_root):
        return runtime_module.execute_pure_resume(authority, {}, run_id="run-1", workspace=root)


def _write_bytecode(tool: Path, placement: str) -> None:
    cache = _cache_file(tool)
    if placement == "cache":
        py_compile.compile(str(tool / "helper.py"), cfile=str(cache), doraise=True)
        assert cache.is_file()
    elif placement == "atomic-temp":
        cache.parent.mkdir()
        Path(f"{cache}.140245").write_bytes(b"partial bytecode")
    else:
        # The whole __pycache__ directory is skipped, so a file in it is not
        # evidence even when it is not bytecode.
        cache.parent.mkdir()
        (cache.parent / "notes.txt").write_text("not bytecode\n", encoding="utf-8")


@pytest.mark.parametrize("placement", ("cache", "atomic-temp", "non-bytecode-in-pycache"))
def test_bytecode_appearing_between_commit_and_resume_reuses_the_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, placement: str
) -> None:
    tool = _package(tmp_path)
    _source, program = _program(tmp_path, BODY, bindings={"emit": "tool"})
    authority = _committed_then_interrupted(tmp_path, monkeypatch, program)
    _write_bytecode(tool, placement)

    assert _resume(authority, tmp_path) == (0, 5)
    assert _records(authority, program) == ["started", "committed", "terminal"]
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["x"]


def test_bytecode_written_during_the_attempt_does_not_fail_the_commit(tmp_path: Path) -> None:
    cache = _cache_file(tmp_path / "tool")
    compile_helper = f"import py_compile\npy_compile.compile(helper.__file__, cfile={str(cache)!r}, doraise=True)\n"
    _package(tmp_path, during=compile_helper)
    _source, program = _program(tmp_path, BODY, bindings={"emit": "tool"})

    with _publish(tmp_path, program) as authority:
        result = runtime_module.execute_pure_run(authority, {}, run_id="run-1", workspace=tmp_path)

    assert result == (0, 5)
    assert _records(authority, program) == ["started", "committed", "terminal"]
    assert cache.is_file()


@pytest.mark.parametrize("change", ("changed-source", "sourceless-pyc-outside-pycache"))
def test_bound_source_or_sourceless_bytecode_change_still_diverges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, change: str
) -> None:
    tool = _package(tmp_path)
    _source, program = _program(tmp_path, BODY, bindings={"emit": "tool"})
    authority = _committed_then_interrupted(tmp_path, monkeypatch, program)
    before = authority.memo_path.read_bytes()
    if change == "changed-source":
        (tool / "helper.py").write_text("VALUE = 6\n", encoding="utf-8")
        py_compile.compile(str(tool / "helper.py"), cfile=str(_cache_file(tool)), doraise=True)
    else:
        # Python imports a `.pyc` with no source beside it, so a `.pyc` outside `__pycache__` stays bound.
        source = tmp_path / "legacy.py"
        source.write_text("VALUE = 7\n", encoding="utf-8")
        py_compile.compile(str(source), cfile=str(tool / "legacy.pyc"), doraise=True)
        source.unlink()

    assert _resume(authority, tmp_path) == (2, None)
    assert authority.memo_path.read_bytes() == before
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["x"]
    assert "[effect_input_diverged]" in caplog.text
