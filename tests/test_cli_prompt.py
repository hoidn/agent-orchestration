"""Task 8: `prompt run` — closed CLI grammar (Step 8.1).

Grammar failures exit 2 before provider calls or destination creation;
verified rerun accepts exactly ``--scaffold PATH``; argparse abbreviation
is disabled so ``--scaf``/``--ret``/``--provide`` are unrecognized; slugs
are exact (inline prompt -> literal ``prompt``, prompt-file -> normalized
lowercase file stem). Sibling modules cover Step 8.2 orchestration
(``test_cli_prompt_orchestration``), Step 8.3 the structured run seam
(``test_cli_prompt_run_seam``), and adversarial filesystem trust boundaries
(``test_cli_prompt_security``). The shared fake-OMP harness lives here.
"""

import os
from pathlib import Path

from pathlib import Path

import pytest

from orchestrator.cli.main import main
from orchestrator.prompt_contract import canonical_json_bytes
from orchestrator.providers.executor import (
    ProviderExecutionResult,
    ProviderExecutor,
    ProviderInvocation,
)
INFERENCE_PROVIDER = "omp_conf_inference"
TASK_TEXT = "Summarize the meeting notes into three bullets."
OUTPUT_REQUEST = "one concise summary"
DRAFT = {"fields": [{"name": "summary", "type": "String"}]}
MODEL = "fake-model"


def _usage_row() -> dict:
    return {
        "input": 10,
        "output": 5,
        "cacheRead": 0,
        "cacheWrite": 0,
        "totalTokens": 15,
        "cost": {
            "input": 0.0,
            "output": 0.0,
            "cacheRead": 0.0,
            "cacheWrite": 0.0,
            "total": 0.0,
        },
    }


class _FakeRuntime:
    """Captures ProviderExecutor.execute invocations (real prepare_invocation)."""

    def __init__(self) -> None:
        self.executed: list[ProviderInvocation] = []
        self.draft: dict | None = DRAFT
        self._saw_inference = False
        # When set, the fake child never writes the output bundle and the
        # normalized assistant text is its stdout (a real OMP confined child
        # never receives the runtime bundle path, so the ordinary runner must
        # materialize the compiled bundle from that text).
        self.skip_bundle_write = False
        # Adversarial workspace planting for the bundle-fallback REDs: the
        # fake child mutates the compiler-owned bundle path before exiting.
        self.plant = None  # None|symlink-leaf|existing-leaf|special-leaf|symlink-parent
        self.plant_target: Path | None = None

    def provider_names(self) -> list[str]:
        names: list[str] = []
        for invocation in self.executed:
            policy = getattr(invocation, "prepared_provider_policy", None)
            names.append(policy.provider_name if policy is not None else "<none>")
        return names


@pytest.fixture
def fake_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _FakeRuntime:
    # Real prepare_invocation requires the OMP positive environment.
    for name, sub in (
        ("HOME", ""),
        ("XDG_DATA_HOME", "data"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_CONFIG_HOME", "config"),
        ("TMPDIR", "tmp"),
    ):
        target = tmp_path if sub == "" else tmp_path / sub
        target.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(name, str(target))
    (tmp_path / ".omp").mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    runtime = _FakeRuntime()

    def execute_provider(_self, invocation, **_kwargs):
        runtime.executed.append(invocation)
        policy = getattr(invocation, "prepared_provider_policy", None)
        provider = policy.provider_name if policy is not None else None
        if runtime.skip_bundle_write:
            payload = None
        elif provider == INFERENCE_PROVIDER:
            payload = canonical_json_bytes(runtime.draft)
            runtime._saw_inference = True
        elif runtime._saw_inference and isinstance(runtime.draft, dict):
            fields = runtime.draft.get("fields")
            if isinstance(fields, list) and all(
                isinstance(field, dict) and isinstance(field.get("name"), str)
                for field in fields
            ):
                payload = canonical_json_bytes(
                    {field["name"]: "fresh-value" for field in fields}
                )
            else:
                payload = b'"fresh-value"'
        else:
            payload = b'"fresh-value"'
        output_path = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if runtime.plant == "symlink-leaf":
            target = runtime.plant_target or output_path.with_suffix(".target")
            target.write_bytes(b'"planted-target"')
            output_path.symlink_to(target)
        elif runtime.plant == "existing-leaf":
            output_path.write_bytes(b'"planted-leaf"')
        elif runtime.plant == "special-leaf":
            os.mkfifo(output_path)
        elif runtime.plant == "symlink-parent":
            parent = output_path.parent
            moved = parent.with_name(parent.name + "-moved")
            os.replace(parent, moved)
            # Bare sibling target: resolves to the moved directory, so a
            # link-following parent write would land inside it.
            parent.symlink_to(parent.name + "-moved", target_is_directory=True)
        elif payload is not None:
            output_path.write_bytes(payload + b"\n")
        return ProviderExecutionResult(
            exit_code=0,
            stdout=(b'"fresh-value"' if runtime.skip_bundle_write else b""),
            stderr=b"",
            duration_ms=1,
            provider_session={
                "session_id": f"session-{provider}",
                "event_count": 2,
                "messages": [
                    {
                        "provider": "omp",
                        "model": MODEL,
                        "usage": _usage_row(),
                        "stop_reason": "stop",
                    }
                ],
                "total_tokens": 15,
                "total_cost": 0.0,
                "final_provider": "omp",
                "final_model": MODEL,
                "launch_frame": None,
            },
        )

    monkeypatch.setattr(ProviderExecutor, "execute", execute_provider)
    return runtime


def _rerun_fails_closed(
    tmp_path, monkeypatch, fake_runtime, capsys, filename, payload
):
    """First run succeeds; corrupt one scaffold file; rerun fails closed."""
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    scaffold = _generated_scaffold(tmp_path)
    (scaffold / filename).write_bytes(payload)
    fake_runtime.executed.clear()
    code = _exit(
        ["prompt", "run", "--scaffold", str(scaffold)],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "prompt run:" in err


def _exit(main_argv: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """Run the real CLI; argparse failures surface as SystemExit(2)."""
    monkeypatch.chdir(tmp_path)
    try:
        return main(main_argv)
    except SystemExit as exc:
        return int(exc.code)


def _generated_scaffold(tmp_path: Path) -> Path:
    generated = tmp_path / "workflows" / "generated"
    scaffolds = sorted(
        p for p in generated.iterdir() if p.name != ".omp-scaffold-locks"
    ) if generated.exists() else []
    assert len(scaffolds) == 1, [str(p) for p in scaffolds]
    return scaffolds[0]


def _run_roots(tmp_path: Path) -> list[Path]:
    runs = tmp_path / ".orchestrate" / "runs"
    return sorted(runs.iterdir()) if runs.exists() else []


# ---------------------------------------------------------------------------
# Step 8.1 — closed CLI grammar
# ---------------------------------------------------------------------------


def test_prompt_requires_exactly_one_prompt_source(tmp_path, monkeypatch):
    assert _exit(["prompt", "run", "--provider", "omp_no_tools"], tmp_path, monkeypatch) == 2
    assert (
        _exit(
            ["prompt", "run", "--prompt", "x", "--prompt-file", "p.md",
             "--provider", "omp_no_tools"],
            tmp_path,
            monkeypatch,
        )
        == 2
    )
    assert not (tmp_path / ".orchestrate").exists()


def test_prompt_requires_public_provider(tmp_path, monkeypatch):
    assert _exit(["prompt", "run", "--prompt", "x"], tmp_path, monkeypatch) == 2
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", INFERENCE_PROVIDER],
              tmp_path, monkeypatch)
        == 2
    )
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", "bogus"],
              tmp_path, monkeypatch)
        == 2
    )
    assert not (tmp_path / ".orchestrate").exists()


def test_conf_required_iff_omp_conf(tmp_path, monkeypatch):
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", "omp_conf"],
              tmp_path, monkeypatch)
        == 2
    )
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", "omp_no_tools",
               "--conf", "c"],
              tmp_path, monkeypatch)
        == 2
    )
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", "omp",
               "--conf", "c"],
              tmp_path, monkeypatch)
        == 2
    )


def test_empty_values_and_mixed_contract_flags_fail(tmp_path, monkeypatch):
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", "omp_no_tools",
               "--model", ""],
              tmp_path, monkeypatch)
        == 2
    )
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", "omp_no_tools",
               "--returns", ""],
              tmp_path, monkeypatch)
        == 2
    )
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", "omp_no_tools",
               "--output", ""],
              tmp_path, monkeypatch)
        == 2
    )
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", "omp_no_tools",
               "--returns", '{"mode":"scalar","type":"String"}', "--output", "y"],
              tmp_path, monkeypatch)
        == 2
    )
    assert not (tmp_path / ".orchestrate").exists()


def test_duplicate_singletons_fail(tmp_path, monkeypatch):
    assert (
        _exit(["prompt", "run", "--prompt", "a", "--prompt", "b",
               "--provider", "omp_no_tools"],
              tmp_path, monkeypatch)
        == 2
    )
    assert (
        _exit(["prompt", "run", "--prompt", "x",
               "--provider", "omp_no_tools", "--provider", "omp"],
              tmp_path, monkeypatch)
        == 2
    )
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", "omp_no_tools",
               "--model", "a", "--model", "b"],
              tmp_path, monkeypatch)
        == 2
    )
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", "omp_no_tools",
               "--returns", '{"mode":"scalar","type":"String"}',
               "--returns", '{"mode":"scalar","type":"Int"}'],
              tmp_path, monkeypatch)
        == 2
    )
    assert (
        _exit(["prompt", "run", "--prompt", "x", "--provider", "omp_no_tools",
               "--output", "a", "--output", "b"],
              tmp_path, monkeypatch)
        == 2
    )


def test_positional_extras_fail(tmp_path, monkeypatch):
    assert (
        _exit(["prompt", "run", "extra", "--prompt", "x",
               "--provider", "omp_no_tools"],
              tmp_path, monkeypatch)
        == 2
    )
    assert not (tmp_path / ".orchestrate").exists()


def test_generation_flags_with_scaffold_fail(tmp_path, monkeypatch):
    assert (
        _exit(["prompt", "run", "--scaffold", "d", "--prompt", "x"],
              tmp_path, monkeypatch)
        == 2
    )
    assert (
        _exit(["prompt", "run", "--scaffold", "d", "--provider", "omp_no_tools"],
              tmp_path, monkeypatch)
        == 2
    )


def test_rerun_accepts_scaffold_root_only(tmp_path, monkeypatch):
    # A missing scaffold directory is a post-grammar runtime failure (exit 1).
    assert (
        _exit(["prompt", "run", "--scaffold", str(tmp_path / "missing")],
              tmp_path, monkeypatch)
        == 1
    )
    # run.orc is never the scaffold root.
    assert (
        _exit(["prompt", "run", "--scaffold", str(tmp_path / "run.orc")],
              tmp_path, monkeypatch)
        == 2
    )
    scaffold_root = tmp_path / "scaffold-root"
    scaffold_root.mkdir()
    (scaffold_root / "run.orc").write_text("x")
    assert (
        _exit(["prompt", "run", "--scaffold", str(scaffold_root / "run.orc")],
              tmp_path, monkeypatch)
        == 2
    )


def test_grammar_errors_precede_provider_calls_and_destination_creation(
    tmp_path, monkeypatch, fake_runtime
):
    bad_argv = [
        ["prompt", "run", "--provider", "omp_no_tools"],
        ["prompt", "run", "--prompt", "", "--provider", "omp_no_tools"],
        ["prompt", "run", "--prompt", "x", "--prompt-file", "p.md",
         "--provider", "omp_no_tools"],
        ["prompt", "run", "--prompt", "x"],
        ["prompt", "run", "--prompt", "x", "--provider", INFERENCE_PROVIDER],
        ["prompt", "run", "--prompt", "x", "--provider", "omp_conf"],
        ["prompt", "run", "--prompt", "x", "--provider", "omp_no_tools",
         "--conf", "c"],
        ["prompt", "run", "--prompt", "x", "--provider", "omp_no_tools",
         "--returns", '{"mode":"scalar","type":"String"}', "--output", "y"],
        ["prompt", "run", "--prompt", "x", "--provider", "omp_no_tools", "extra"],
        ["prompt", "run", "--prompt", "x", "--provider", "omp_no_tools",
         "--model", ""],
    ]
    for argv in bad_argv:
        assert _exit(argv, tmp_path, monkeypatch) == 2, argv
        assert fake_runtime.executed == [], argv
        assert not (tmp_path / ".orchestrate").exists(), argv


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Security: argparse abbreviation is closed (no side effects)
# ---------------------------------------------------------------------------


def test_abbreviated_prompt_long_options_are_rejected(
    tmp_path, monkeypatch, fake_runtime
):
    """Unique prefixes such as --scaf/--ret/--provide are unrecognized:
    verified rerun and generation accept exactly the named flags, so any
    abbreviation must exit 2 before provider calls or destination creation."""
    prompt_file = tmp_path / "abbrev.md"
    prompt_file.write_bytes(TASK_TEXT.encode("utf-8"))
    bad_argv = [
        # --scaf abbreviates --scaffold on the rerun branch.
        ["prompt", "run", "--scaf", str(tmp_path / "missing-scaffold")],
        # --ret abbreviates --returns on the generation branch.
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools",
         "--ret", '{"mode":"scalar","type":"String"}'],
        # --provide abbreviates --provider.
        ["prompt", "run", "--prompt", TASK_TEXT, "--provide", "omp_no_tools"],
        # --prompt-f abbreviates --prompt-file.
        ["prompt", "run", "--prompt-f", str(prompt_file),
         "--provider", "omp_no_tools"],
    ]
    for argv in bad_argv:
        assert _exit(argv, tmp_path, monkeypatch) == 2, argv
        assert fake_runtime.executed == [], argv
        assert not (tmp_path / ".orchestrate").exists(), argv
        assert not (tmp_path / "workflows" / "generated").exists(), argv


# ---------------------------------------------------------------------------
# Exact slug semantics
# ---------------------------------------------------------------------------


def test_inline_prompt_slug_is_literal_prompt(tmp_path, monkeypatch, fake_runtime):
    """An inline --prompt always names its scaffold 'prompt-<identity>'."""
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    scaffold = _generated_scaffold(tmp_path)
    assert scaffold.name.startswith("prompt-")


def test_prompt_file_slug_is_normalized_lowercase_stem(
    tmp_path, monkeypatch, fake_runtime
):
    """A --prompt-file names its scaffold from the normalized lowercase stem,
    never from the prompt's first line."""
    prompt_file = tmp_path / "My Meeting Notes v2.md"
    prompt_file.write_bytes(TASK_TEXT.encode("utf-8"))
    code = _exit(
        ["prompt", "run", "--prompt-file", str(prompt_file),
         "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    scaffold = _generated_scaffold(tmp_path)
    assert scaffold.name.startswith("my-meeting-notes-v2-"), scaffold.name


def test_prompt_file_slug_rerun_reconstructs_identity(
    tmp_path, monkeypatch, fake_runtime
):
    """A verified rerun of a file-stem scaffold keeps the exact slug."""
    prompt_file = tmp_path / "My Meeting Notes v2.md"
    prompt_file.write_bytes(TASK_TEXT.encode("utf-8"))
    code = _exit(
        ["prompt", "run", "--prompt-file", str(prompt_file),
         "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    scaffold = _generated_scaffold(tmp_path)
    fake_runtime.executed.clear()
    rerun_workspace = tmp_path / "slug-rerun"
    rerun_workspace.mkdir()
    code = _exit(
        ["prompt", "run", "--scaffold", str(scaffold)],
        rerun_workspace,
        monkeypatch,
    )
    assert code == 0
    assert fake_runtime.provider_names() == ["omp_no_tools"]
    [invocation] = fake_runtime.executed
    assert TASK_TEXT in invocation.prompt
