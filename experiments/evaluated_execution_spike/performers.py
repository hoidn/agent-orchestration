"""Performers (design section 9.2): one attempt of one effect, at a result path of its own.

A performer receives the effect node, its resolved input and the attempt's
result path. It launches through the existing executor of its class, validates
the file at the result path against the node's contract, and returns the value
or a failure. It reads and writes no run state.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

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


def assemble_prompt(workspace: Path, prompt: str | dict[str, Any], inputs: list[Any]) -> str:
    """Not the flat route's assembly: an asset file and the inputs as JSON, or a template with its fills
    rendered by the view renderers the runtime uses for prompt fragments."""

    if isinstance(prompt, str):
        return (workspace / prompt).read_text(encoding="utf-8") + "\n" + render_argument(inputs)
    text = prompt["template"]
    for name, renderer, value in prompt["fills"]:
        rendered = value if renderer == "raw-utf8-string" else render_view(renderer, 1, value).decode("utf-8")
        text = text.replace("{" + name + "}", rendered.removesuffix("\n"))
    return text


class Performers:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()

    def perform(self, node: dict[str, Any], resolved: dict[str, Any], path: Path) -> tuple[Any, dict | None]:
        path.parent.mkdir(parents=True)  # a new attempt directory: nothing of an earlier attempt is in it
        failure = self.command(resolved, path) if node["class"] == "command" else self.provider(resolved, path)
        if failure is not None:
            return None, failure
        return self.validate(node, path)

    def command(self, resolved: dict[str, Any], path: Path) -> dict | None:
        executor = StepExecutor(self.workspace, logs_dir=path.parent)
        result = executor.execute_command("command", resolved["command"], env={BUNDLE_ENV: str(path)})
        if result.exit_code != 0:
            return {"code": "command_failed", "exit_code": result.exit_code, "error": result.error}
        return None

    def provider(self, resolved: dict[str, Any], path: Path) -> dict | None:
        prompt = assemble_prompt(self.workspace, resolved["prompt"], resolved["inputs"])
        (path.parent / "prompt.txt").write_text(prompt, encoding="utf-8")
        executor = ProviderExecutor(self.workspace, ProviderRegistry())
        invocation, error = executor.prepare_invocation(
            resolved["provider"], ProviderParams(params={}), {}, prompt_content=prompt, env={BUNDLE_ENV: str(path)}
        )
        if error is not None:
            return {"code": "provider_invocation_invalid", "error": error}
        result = executor.execute(invocation, cwd=self.workspace)
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
