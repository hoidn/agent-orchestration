"""Task 9: exact `prompt import` grammar and ordinary-run routing."""

import hashlib
from argparse import Namespace
from pathlib import Path

import pytest

from orchestrator.cli.main import main
from orchestrator.prompt_session import (
    PromptSessionError,
    ResolvedPrimary,
    SessionLink,
    with_private_execution_authority,
)
from tests.test_cli_prompt import TASK_TEXT, fake_runtime
from tests.test_prompt_session import PRIMARY, SESSION_ID, _canonical, _journal, _link, _user


def _invoke(argv: list[str]) -> int:
    try:
        return main(argv)
    except SystemExit as exc:
        return int(exc.code)


def _resolved(tmp_path: Path, prompt: str = "imported prompt") -> ResolvedPrimary:
    document = _link(
        digests={
            **_link()["digests"],
            "composed_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        }
    )
    raw = _canonical(document)
    return ResolvedPrimary(
        "run-1", "task__v1", SESSION_ID, PRIMARY, SessionLink(document, raw),
        tmp_path / "runs" / "run-1", (1, 2), _journal(_user(prompt)),
    )


def _real_private_resolved(
    tmp_path: Path,
    *,
    provider: str = "omp",
) -> tuple[ResolvedPrimary, Path]:
    import json
    from orchestrator.prompt_contract import default_semantic_contract, semantic_contract_sha256
    from orchestrator.prompt_scaffold import ScaffoldInputs, generate_scaffold
    from orchestrator.prompt_session import with_private_execution_authority
    from orchestrator.providers.omp_pin import OMP_BINARY_PIN

    prompt = b"imported prompt"
    inputs = ScaffoldInputs(
        prompt_sha256=hashlib.sha256(prompt).hexdigest(),
        contract=default_semantic_contract(),
        provider=provider,
        model="gpt-5.6-sol",
        conf_manifest=None,
        slug="task",
        pin=OMP_BINARY_PIN,
    )
    generated = tmp_path / "generated"
    generated.mkdir()
    scaffold = generate_scaffold(
        generated_root=generated,
        inputs=inputs,
        prompt_bytes=prompt,
        authoring={"mode": "exact"},
    )
    run = tmp_path / "runs" / "run-1"
    private = run / "prompt-inputs"
    private.mkdir(parents=True)
    verification = with_private_execution_authority(scaffold.verification)
    for relative, data in verification.files.items():
        target = private / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o400)
    document = _link(
        provider={
            "name": verification.provider,
            "model": verification.model,
            "lane": "no-tools" if provider == "omp_no_tools" else "ambient",
        },
        paths={
            **_link()["paths"],
            "conf": (
                "provider_sessions/task__v1.conf"
                if provider == "omp_no_tools"
                else None
            ),
        },
        scaffold_identity=verification.identity,
        digests={
            **_link()["digests"],
            "scaffold_manifest_sha256": hashlib.sha256(
                verification.manifest_bytes
            ).hexdigest(),
            "authored_prompt_sha256": hashlib.sha256(prompt).hexdigest(),
            "source_sha256": hashlib.sha256(
                verification.files["run.orc"]
            ).hexdigest(),
            "semantic_contract_sha256": semantic_contract_sha256(
                verification.semantic_contract
            ),
            "conf_manifest_sha256": (
                inputs.conf_manifest_sha256
                if provider == "omp_no_tools"
                else None
            ),
            "composed_prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        },
    )
    raw = _canonical(document)
    stat = run.stat()
    resolved = ResolvedPrimary(
        "run-1",
        "task__v1",
        SESSION_ID,
        PRIMARY,
        SessionLink(document, raw),
        run,
        (stat.st_dev, stat.st_ino),
        _journal(_user(prompt.decode())),
    )
    return resolved, private


@pytest.mark.parametrize(
    "argv",
    (
        ["prompt", "import", "id"],
        ["prompt", "import", "id", "extra", "--provider", "omp"],
        ["prompt", "import", "id", "--reuse-run-contract", "--provider", "omp"],
        ["prompt", "import", "id", "--reuse-run-contract", "--model", "m"],
        ["prompt", "import", "id", "--provider", "omp_conf"],
        ["prompt", "import", "id", "--provider", "omp", "--conf", "x"],
        ["prompt", "import", "id", "--provider", "omp", "--returns", "String", "--output", "text"],
        ["prompt", "import", "id", "--provider", "omp", "--provider", "omp"],
        ["prompt", "import", "id", "--reuse-run-contract", "--reuse-run-contract"],
    ),
)
def test_import_closed_grammar_exits_two_before_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    called = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "orchestrator.cli.commands.prompt_import.resolve_prompt_session",
        lambda *_args: called.append(True),
    )
    assert _invoke(argv) == 2
    assert called == []


def test_new_contract_import_routes_extracted_text_through_prompt_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[Namespace] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "orchestrator.cli.commands.prompt_import.resolve_prompt_session",
        lambda *_args: _resolved(tmp_path),
    )
    monkeypatch.setattr(
        "orchestrator.cli.commands.prompt_import.prompt_workflow",
        lambda args: captured.append(args) or 0,
    )

    assert _invoke(["prompt", "import", "run-1", "--provider", "omp", "--model", "m"]) == 0
    [args] = captured
    assert args.prompt == ["imported prompt"]
    assert args.provider == ["omp"]
    assert args.model == ["m"]
    assert args.scaffold is None


def test_reuse_import_verifies_composed_digest_before_private_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolved = _resolved(tmp_path)
    calls = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "orchestrator.cli.commands.prompt_import.resolve_prompt_session",
        lambda *_args: resolved,
    )
    monkeypatch.setattr(
        "orchestrator.cli.commands.prompt_import._run_private_reuse",
        lambda value: calls.append(value) or 0,
    )
    assert _invoke(["prompt", "import", "run-1", "--reuse-run-contract"]) == 0
    assert calls == [resolved]

    bad_link = SessionLink(
        {**resolved.link.document, "digests": {**resolved.link.document["digests"], "composed_prompt_sha256": "0" * 64}},
        resolved.link.raw_bytes,
    )
    monkeypatch.setattr(
        "orchestrator.cli.commands.prompt_import.resolve_prompt_session",
        lambda *_args: ResolvedPrimary(
            resolved.run_id, resolved.visit_key, resolved.session_id,
            resolved.primary_basename, bad_link, resolved.run_root,
            resolved.run_identity, resolved.journal_bytes,
        ),
    )
    calls.clear()
    assert _invoke(["prompt", "import", "run-1", "--reuse-run-contract"]) == 1
    assert calls == []



@pytest.mark.parametrize(
    "mutation",
    ("providers", "prompts", "extra", "contract", "model", "pin"),
)
def test_private_reuse_fully_verifies_source_occupant(
    tmp_path: Path,
    mutation: str,
) -> None:
    import json
    from dataclasses import replace
    from orchestrator.cli.commands.prompt_import import _verified_private_scaffold

    resolved, private = _real_private_resolved(tmp_path)
    if mutation in ("providers", "prompts"):
        target = private / f"{mutation}.json"
        target.chmod(0o600)
        target.write_bytes(target.read_bytes() + b" ")
        target.chmod(0o400)
    elif mutation == "extra":
        (private / "extra.txt").write_bytes(b"unexpected")
    elif mutation == "contract":
        target = private / "output-contract.json"
        target.chmod(0o600)
        target.write_bytes(b"[]\n")
        target.chmod(0o400)
    elif mutation == "model":
        document = {
            **resolved.link.document,
            "provider": {
                **resolved.link.document["provider"],
                "model": "different-model",
            },
        }
        resolved = replace(
            resolved,
            link=SessionLink(document, _canonical(document)),
        )
    else:
        manifest_path = private / "scaffold.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["binary"]["sha256"] = "b" * 64
        changed = _canonical(manifest)
        manifest_path.chmod(0o600)
        manifest_path.write_bytes(changed)
        manifest_path.chmod(0o400)
        document = {
            **resolved.link.document,
            "digests": {
                **resolved.link.document["digests"],
                "scaffold_manifest_sha256": hashlib.sha256(changed).hexdigest(),
            },
        }
        resolved = replace(
            resolved,
            link=SessionLink(document, _canonical(document)),
        )
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        _verified_private_scaffold(resolved)


def test_reuse_cli_normalizes_malformed_private_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved, private = _real_private_resolved(tmp_path)
    contract = private / "output-contract.json"
    contract.chmod(0o600)
    contract.write_bytes(b"[]\n")
    contract.chmod(0o400)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "orchestrator.cli.commands.prompt_import.resolve_prompt_session",
        lambda *_args: resolved,
    )
    assert _invoke([
        "prompt", "import", "run-1", "--reuse-run-contract",
    ]) == 1





def test_no_tools_private_reuse_checks_current_identity_and_link_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace
    from orchestrator.cli.commands.prompt_import import _verified_private_scaffold

    resolved, _private = _real_private_resolved(
        tmp_path,
        provider="omp_no_tools",
    )
    monkeypatch.setattr(
        "orchestrator.providers.omp_launch.neutral_conf_root",
        lambda: (_ for _ in ()).throw(AssertionError("neutral conf reopened")),
    )
    verification, _captured, _contract = _verified_private_scaffold(resolved)
    assert with_private_execution_authority(verification).conf_files
    assert verification.provider == "omp_no_tools"
    document = {
        **resolved.link.document,
        "provider": {
            **resolved.link.document["provider"],
            "model": "different-model",
        },
    }
    changed = replace(
        resolved,
        link=SessionLink(document, _canonical(document)),
    )
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        _verified_private_scaffold(changed)

def test_prompt_run_publishes_inside_retained_private_snapshot_after_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_runtime
) -> None:
    import os

    calls = []
    monkeypatch.chdir(tmp_path)

    def publish(_manager, **kwargs):
        os.fstat(kwargs["private_snapshot_fd"])
        calls.append(kwargs)
        return tmp_path / "link.json"

    monkeypatch.setattr(
        "orchestrator.cli.commands.prompt_run_service.publish_prompt_run_link", publish
    )
    assert _invoke(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"]
    ) == 0
    assert len(calls) == 1


def test_prompt_run_link_publication_failure_turns_success_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_runtime
) -> None:
    monkeypatch.chdir(tmp_path)

    def fail(*_args, **_kwargs):
        raise PromptSessionError("session_link_invalid")

    monkeypatch.setattr(
        "orchestrator.cli.commands.prompt_run_service.publish_prompt_run_link", fail
    )
    assert _invoke(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"]
    ) == 1


def test_private_reuse_rejects_source_run_directory_swap(
    tmp_path: Path,
) -> None:
    from dataclasses import replace
    from orchestrator.cli.commands.prompt_import import _open_source_private

    run = tmp_path / "runs" / "run-1"
    (run / "prompt-inputs").mkdir(parents=True)
    stat = run.stat()
    resolved = replace(
        _resolved(tmp_path),
        run_root=run,
        run_identity=(stat.st_dev, stat.st_ino),
    )
    run.rename(run.with_name("old-run"))
    (run / "prompt-inputs").mkdir(parents=True)
    with pytest.raises(PromptSessionError, match="source run directory identity changed"):
        _open_source_private(resolved)


def test_private_reuse_executes_full_import_and_publishes_new_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_runtime
) -> None:
    import json

    from orchestrator.cli.commands import prompt_run_service
    from orchestrator.prompt_session_publish import publish_prompt_run_link
    from orchestrator.providers.executor import (
        ProviderExecutionResult,
        ProviderExecutor,
    )
    from orchestrator.providers.omp_launch_contract import POSITIVE_ENV_NAMES

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        prompt_run_service, "publish_prompt_run_link", publish_prompt_run_link
    )
    invocation_count = 0

    def execute_provider(_self, invocation, **_kwargs):
        nonlocal invocation_count
        invocation_count += 1
        fake_runtime.executed.append(invocation)
        expectation = invocation.omp_transport_expectation
        assert expectation is not None
        session_id = f"00000000-0000-4000-8000-{invocation_count:012d}"
        primary = f"{session_id}.jsonl"
        prompt = invocation.prompt
        assert isinstance(prompt, str)
        journal = _journal(_user(prompt), session_id=session_id)
        session_root = Path(invocation.provider_session_dir)
        (session_root / primary).write_bytes(journal)
        confinement = (
            {
                "schema_version": "omp_write_confinement.v1",
                "landlock_abi": 3,
                "policy_sha256": expectation.confinement_policy_sha256,
            }
            if expectation.confinement_policy_sha256 is not None
            else None
        )
        frame = {
            "type": "orchestrator.omp_launch.v1",
            "lane": expectation.lane,
            "persistence": expectation.persistence,
            "binary": dict(expectation.binary),
            "child": {
                "argv": list(expectation.child_argv),
                "cwd": str(tmp_path / ("omp-empty-" + "1" * 16 + "-" + "2" * 16)),
                "env_names": list(POSITIVE_ENV_NAMES),
                "exit_code": 0,
            },
            "session": {
                "id": session_id,
                "visit_key": expectation.visit_key,
                "primary_relpath": primary,
                "primary_sha256": hashlib.sha256(journal).hexdigest(),
            },
            "conf": {
                "manifest_sha256": expectation.conf_manifest_sha256
            },
            "confinement": confinement,
            "observed": {
                "advisor_relpaths": [],
                "child_relpaths": [primary],
            },
        }
        Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
            '"fresh-value"\n', encoding="utf-8"
        )
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            provider_session={
                "session_id": session_id,
                "event_count": 2,
                "messages": [],
                "total_tokens": 0,
                "total_cost": 0.0,
                "final_provider": "omp",
                "final_model": "gpt-5.6-sol",
                "launch_frame": frame,
            },
        )

    monkeypatch.setattr(ProviderExecutor, "execute", execute_provider)
    assert _invoke(
        ["prompt", "run", "--prompt", "authored prompt", "--provider", "omp_no_tools"]
    ) == 0
    source_prompt = fake_runtime.executed[0].prompt
    assert isinstance(source_prompt, str)
    guidance = source_prompt.removeprefix("authored prompt")
    assert guidance.startswith("\n\n## Output Contract")
    runs_root = tmp_path / ".orchestrate" / "runs"
    source_run = next(runs_root.iterdir())
    source_link_path = next((source_run / "provider_sessions").glob("*.session-link.json"))
    source_link = json.loads(source_link_path.read_text(encoding="utf-8"))

    assert _invoke(
        ["prompt", "import", source_link["session"]["id"], "--reuse-run-contract"]
    ) == 0
    assert [item.prepared_provider_policy.provider_name for item in fake_runtime.executed] == [
        "omp_no_tools", "omp_no_tools"
    ]
    assert [item.prepared_provider_policy.model for item in fake_runtime.executed] == [
        "openai-codex/gpt-5.6-sol", "openai-codex/gpt-5.6-sol"
    ]
    source_output = fake_runtime.executed[0].env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
    destination_output = fake_runtime.executed[1].env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
    expected_guidance = guidance.replace(source_output, destination_output)
    assert fake_runtime.executed[1].prompt == "authored prompt" + expected_guidance
    assert fake_runtime.executed[1].prompt.count(expected_guidance) == 1
    links = list(runs_root.glob("*/provider_sessions/*.session-link.json"))
    assert len(links) == 2
