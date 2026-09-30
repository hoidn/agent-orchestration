"""Performers (design section 9.2): one attempt of one effect, at a result path of its own.

A performer receives the effect node, its resolved input and the attempt's
result path. It launches through the existing executor of its class, validates
the file at the result path against the node's contract, and returns the value
or a failure. It reads and writes no run state.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from orchestrator.contracts.prompt_contract import (
    render_output_bundle_contract_block,
    render_variant_output_contract_block,
)
from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_output_bundle,
    validate_variant_output_bundle,
)
from orchestrator.exec.step_executor import StepExecutor
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.types import ProviderParams
from orchestrator.workflow.view_renderer import render_view

from .sites import canonical_digest

BUNDLE_ENV = "ORCHESTRATOR_OUTPUT_BUNDLE_PATH"


def result_path(run_root: Path, identity: str, attempt: int) -> Path:
    """Derived from the identity and the attempt ordinal; a new attempt never shares a path."""

    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return run_root / "effects" / key / f"attempt-{attempt}" / "result.json"


def render_argument(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int)):
        return str(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def project(value: Any, desc: dict[str, Any]) -> Any:
    """The value of the declared type in a validated document: undeclared keys are dropped."""

    kind = desc["kind"]
    if kind == "record":
        return {f["name"]: project(value.get(f["name"]), f["type"]) for f in desc["fields"]}
    if kind == "union":
        variant = next(v for v in desc["variants"] if v["name"] == value["variant"])
        return {"variant": variant["name"], **{f["name"]: project(value.get(f["name"]), f["type"]) for f in variant["fields"]}}
    if kind == "list":
        return [project(item, desc["item"]) for item in value]
    if kind == "optional":
        return None if value is None else project(value, desc["item"])
    return value


_DIGESTS: dict[tuple, str] = {}


def file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    # ponytail: per-process cache keyed by inode, size and change time (a write always moves ctime, and utime
    # cannot set it); the interpreter behind `python` is 35 MB. Drop it if a filesystem without ctime matters.
    stat = path.stat()
    key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    if key not in _DIGESTS:
        _DIGESTS[key] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return _DIGESTS[key]


def _join(text: str, block: str) -> str:
    """The runtime's rule for appending a prompt block (`prompting.py`)."""

    if not block:
        return text
    if not text:
        return block
    return text + ("\n" if text.endswith("\n") else "\n\n") + block


def assemble_prompt(workspace: Path, resolved: dict[str, Any], contract: dict[str, Any], bundle: str) -> str:
    """The prompt, in the order and with the renderers the flat route uses: the asset or the rendered
    template, the typed prompt inputs, the prompt dependencies, the output contract."""

    prompt = resolved["prompt"]
    if isinstance(prompt, str):
        text = (workspace / prompt).read_text(encoding="utf-8")
    else:
        text = prompt["template"]
        for name, renderer, value in prompt["fills"]:
            rendered = value if renderer == "raw-utf8-string" else render_view(renderer, 1, value).decode("utf-8")
            text = text.replace("{" + name + "}", rendered.removesuffix("\n"))
    typed = [f"## Typed Prompt Input: {name}\n" + render_view(renderer, 1, value).decode("utf-8").rstrip("\n")
             for name, renderer, value in resolved["inputs"]]
    text = _join(text, "\n\n".join(typed))
    dependencies = resolved.get("dependencies")
    if dependencies:  # not the flat route's snapshot rendering
        files = [p for p in dependencies["required"] + dependencies["optional"] if (workspace / p).is_file()]
        block = "\n\n".join(f"## Prompt Dependency: {p}\n" + (workspace / p).read_text(encoding="utf-8") for p in files)
        block = _join(dependencies.get("instruction") or "", block)
        text = _join(block, text) if dependencies["position"] == "prepend" else _join(text, block)
    payload = {**contract["payload"], "path": bundle}
    render = render_output_bundle_contract_block if contract["kind"] == "output_bundle" else render_variant_output_contract_block
    return _join(text, render(payload))


class Performers:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()

    def declared_files(self, tokens: list[str], closure: list[str] | None) -> dict[str, Any]:
        """What a command runs, bound by the `declared` rule: each token of the stable command that names a
        workspace path, the program (the first token) resolved on PATH now when it is a bare name, and each
        entry of the boundary's implementation closure. Modification times are not bound."""

        files = {}
        for index, token in enumerate(tokens):
            path = Path(token) if Path(token).is_absolute() else self.workspace / token
            if "/" in token or path.exists():
                files[token] = self.path_digest(path)
            elif index == 0:
                found = shutil.which(token)
                files[token] = {"path": found, "file": self.path_digest(Path(found))} if found else None
        for entry in closure or ():
            files[entry] = self.path_digest(self.workspace / entry)
        return files

    def path_digest(self, path: Path) -> Any:
        """A file: its content digest. A directory: the digest of its files' relative paths and digests, sorted.
        A path through a symbolic link: also the path it resolves to. Missing: None."""

        if not path.exists():
            return None
        if path.is_dir():
            digest = canonical_digest(sorted([item.relative_to(path).as_posix(), self.path_digest(item)]
                                             for item in path.rglob("*") if item.is_file()))
        else:
            digest = file_digest(path)
        target = path.resolve()
        if target == path.absolute():
            return digest
        where = target.relative_to(self.workspace).as_posix() if target.is_relative_to(self.workspace) else str(target)
        return {"digest": digest, "target": where}

    def provider_files(self, prompt: str | dict[str, Any], dependencies: dict[str, Any] | None) -> dict[str, str | None]:
        """The prompt asset and the prompt dependencies of a provider effect, with their digests."""

        paths = [prompt] if isinstance(prompt, str) else []
        if dependencies:
            paths += [*dependencies["required"], *dependencies["optional"]]
        return {path: file_digest(self.workspace / path) for path in paths}

    def perform(self, node: dict[str, Any], resolved: dict[str, Any], path: Path, identity: str) -> tuple[Any, dict | None]:
        path.parent.mkdir(parents=True)  # a new attempt directory: nothing of an earlier attempt is in it
        if node["class"] == "command":
            failure = self.command(resolved, path)
        else:
            failure = self.provider(node, resolved, path, identity)
        if failure is not None:
            return None, failure
        return self.validate(node, path)

    def command(self, resolved: dict[str, Any], path: Path) -> dict | None:
        executor = StepExecutor(self.workspace, logs_dir=path.parent)
        result = executor.execute_command("command", resolved["command"], env={BUNDLE_ENV: str(path)})
        (path.parent / "stdout.txt").write_text(result.capture_result.output or "", encoding="utf-8")  # evidence
        if result.exit_code != 0:
            return {"code": "command_failed", "exit_code": result.exit_code, "error": result.error}
        return None

    def provider(self, node: dict[str, Any], resolved: dict[str, Any], path: Path, identity: str) -> dict | None:
        prompt = assemble_prompt(self.workspace, resolved, node["contract"], path.relative_to(self.workspace).as_posix())
        (path.parent / "prompt.txt").write_text(prompt, encoding="utf-8")
        policy = resolved["policy"]
        executor = ProviderExecutor(self.workspace, ProviderRegistry())
        invocation, error = executor.prepare_invocation(
            provider_name=resolved["provider"], params=ProviderParams(params={}), context={}, prompt_content=prompt,
            session_request=None, env={BUNDLE_ENV: str(path)}, secrets=None, timeout_sec=policy.get("timeout_sec"),
            provider_call_policy={key: policy[key] for key in ("model", "effort") if key in policy},
            provider_session_dir=None, provider_session_identity=None,
        )
        if error is not None:
            return {"code": "provider_invocation_invalid", "error": error}
        site_key = "sha256:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
        result = executor.execute(invocation, cwd=self.workspace, stream_output=False,
                                  execution_env_overlay={"ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY": site_key})
        if result.exit_code != 0:
            return {"code": "provider_failed", "exit_code": result.exit_code, "error": result.error}
        return None

    def validate(self, node: dict[str, Any], path: Path) -> tuple[Any, dict | None]:
        contract = {**node["contract"]["payload"], "path": path.relative_to(self.workspace).as_posix()}
        validator = validate_output_bundle if node["contract"]["kind"] == "output_bundle" else validate_variant_output_bundle
        try:
            validator(contract, self.workspace)
        except OutputContractError as exc:
            return None, {"code": "contract_violation", "violations": [v["type"] for v in exc.violations]}
        return project(json.loads(path.read_text(encoding="utf-8")), node["result"]), None
