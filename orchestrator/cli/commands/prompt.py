"""`prompt run`: deterministic OMP prompt scaffolds and ordinary runs (Task 8).

Generation: exactly one of --prompt/--prompt-file, one public OMP provider,
--conf iff omp_conf, optional non-empty --model, at most one of
--returns/--output. Rerun: exactly --scaffold PATH naming the scaffold root.
Capture precedes inference and destination creation; --output runs the internal
omp_conf_inference workflow with typed inputs, then the task runs ordinary
run_workflow on a private snapshot under a reserved run root.
"""
from __future__ import annotations
import json
import os
import sys
from typing import Mapping
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from orchestrator import prompt_scaffold
from orchestrator._common.safe_tree import SafeTreeError, read_regular_file
from orchestrator.cli.commands.prompt_io import (
    INFERENCE_PROVIDER,
    PromptCliError,
    PromptRunError,
    _admit_conf_dir,
    _create_prompt_inputs_root,
    _ensure_generated_root,
    _new_reserved_run,
    _revalidate_run_root,
    _thaw_frozen,
    _read_prompt_file,
    _write_inference_snapshot,
)
from orchestrator.cli.commands.prompt_run_service import (
    materialize_and_run,
    run_namespace,
)
from orchestrator.cli.commands.run import run_workflow
from orchestrator.omp_assets import inference_output_contract_path
from orchestrator.prompt_contract import (
    PromptContractError,
    canonical_json_bytes,
    default_semantic_contract,
    parse_inferred_draft,
    parse_semantic_contract,
    sha256_hex,
    validate_authoring,
)
from orchestrator.prompt_scaffold import (
    PUBLIC_PROVIDER_NAMES,
    ScaffoldCompileError,
    ScaffoldVerification,
    ScaffoldInputs,
    ScaffoldSnapshotError,
    ScaffoldVerificationError,
)
from orchestrator.prompt_scaffold_fs import open_generated_root
from orchestrator.prompt_scaffold_render import wfl_string_literal
from orchestrator.providers.omp_pin import OMP_BINARY_PIN
from orchestrator.providers.omp_templates import omp_templates
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.prompt_session import PromptSessionError

GENERATED_DIR = "workflows/generated"
_ZERO_USAGE = {
    "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0,
    "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.0},
}
_INFERENCE_PROMPT = (
    "Synthesize the exact machine-readable output contract for the task in task_prompt and the requested output in output_request. Reply with exactly one JSON object on one line: {\"fields\": [{\"name\": \"<lowercase identifier>\", \"type\": \"<canonical type>\"}, ...]}. Each row has exactly name and type; names are unique lowercase identifiers; types are one of String, Bool, Int, Float, Optional[T], List[T], Map[String,T]. No prose, no code fences, no extra keys."
)
@dataclass(frozen=True)
class _Captured:
    """Captures taken before inference or destination creation."""
    prompt: bytes
    prompt_sha256: str
    provider: str
    model: str
    conf_manifest: object
    contract_mode: str
    contract_request: str | None
    slug: str
def _single(values: list[str] | None, flag: str) -> str | None:
    items = values or []
    if len(items) > 1:
        raise PromptCliError(f"--{flag} must be given at most once")
    return items[0] if items else None
def _require_nonempty(value: str | None, flag: str) -> str:
    if not value:
        raise PromptCliError(f"--{flag} must be a non-empty value")
    return value
def _inline_slug() -> str:
    """Inline --prompt scaffolds are always named 'prompt-<identity>'."""
    return "prompt"
def _prompt_file_slug(prompt_file: str) -> str:
    """A --prompt-file scaffold is named from its normalized lowercase stem."""
    return prompt_scaffold.slugify(Path(prompt_file).stem)
def _parse_prompt_run(args: Namespace) -> dict:
    """Validate the closed grammar; returns one mode dict (no side effects)."""
    scaffold = _single(getattr(args, "scaffold", None), "scaffold")
    if scaffold is not None:
        _require_nonempty(scaffold, "scaffold")
        for flag in ("prompt", "prompt_file", "provider", "model", "conf", "returns", "output"):
            if getattr(args, flag, None):
                raise PromptCliError(f"--{flag} cannot be combined with --scaffold")
        path = Path(scaffold).expanduser()
        if path.name == "run.orc":
            raise PromptCliError("--scaffold must name the scaffold root, not run.orc")
        return {"kind": "rerun", "scaffold": path}
    prompt = _single(getattr(args, "prompt", None), "prompt")
    prompt_file = _single(getattr(args, "prompt_file", None), "prompt-file")
    if prompt is not None and prompt_file is not None:
        raise PromptCliError("--prompt and --prompt-file are mutually exclusive")
    if prompt_file is not None and not prompt_file:
        raise PromptCliError("--prompt-file must be a non-empty value")
    if prompt is None and prompt_file is None:
        raise PromptCliError("exactly one of --prompt/--prompt-file is required")
    provider = _single(getattr(args, "provider", None), "provider")
    if provider is None:
        raise PromptCliError("exactly one public --provider is required")
    if provider not in PUBLIC_PROVIDER_NAMES:
        raise PromptCliError(f"internal or unknown provider: {provider!r}")
    model = _single(getattr(args, "model", None), "model")
    if model is not None:
        _require_nonempty(model, "model")
    conf = _single(getattr(args, "conf", None), "conf")
    if provider == "omp_conf" and conf is None:
        raise PromptCliError("--conf is required for provider omp_conf")
    if provider != "omp_conf" and conf is not None:
        raise PromptCliError("--conf is only allowed for provider omp_conf")
    returns = _single(getattr(args, "returns", None), "returns")
    output = _single(getattr(args, "output", None), "output")
    if returns is not None:
        _require_nonempty(returns, "returns")
    if output is not None:
        _require_nonempty(output, "output")
    if returns is not None and output is not None:
        raise PromptCliError("--returns and --output are mutually exclusive")
    if prompt is not None:
        _require_nonempty(prompt, "prompt")
        prompt_bytes = prompt.encode("utf-8")
        slug = _inline_slug()
    else:
        prompt_path = Path(prompt_file).expanduser()
        prompt_bytes = _read_prompt_file(prompt_path)
        if not prompt_bytes:
            raise PromptCliError("--prompt-file must name a non-empty file")
        try:
            prompt_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PromptRunError("--prompt-file must be valid UTF-8") from exc
        slug = _prompt_file_slug(prompt_file)
    return {"kind": "generate", "prompt": prompt_bytes, "provider": provider,
            "model": model, "conf": conf, "returns": returns, "output": output,
            "slug": slug}
def _capture_generation(mode: dict) -> _Captured:
    """Capture prompt, registry template, concrete model, conf, and request."""
    prompt = mode["prompt"]
    provider = mode["provider"]
    template = ProviderRegistry().get(provider)
    if template is None:
        raise PromptCliError(f"provider {provider!r} is not registered")
    pinned = omp_templates()[provider]
    if template != pinned:
        raise PromptRunError(
            f"provider {provider!r} template is not the pinned "
            "code-owned template")
    model = mode["model"] or template.defaults.get("model")
    if not isinstance(model, str) or not model:
        raise PromptRunError(f"no concrete model for provider {provider!r}")
    try:
        wfl_string_literal(model)
    except ValueError as exc:
        raise PromptRunError(
            f"model selector cannot be rendered into a workflow: {exc}"
        ) from exc
    conf_manifest = (
        _admit_conf_dir(Path(mode["conf"]).expanduser())
        if provider == "omp_conf"
        else None
    )
    if mode["returns"] is not None:
        contract_mode, contract_request = "exact", mode["returns"]
    elif mode["output"] is not None:
        contract_mode, contract_request = "inferred", mode["output"]
    else:
        contract_mode, contract_request = "default", None
    return _Captured(
        prompt=prompt, prompt_sha256=sha256_hex(prompt), provider=provider,
        model=model, conf_manifest=conf_manifest,
        contract_mode=contract_mode, contract_request=contract_request,
        slug=mode["slug"])

def _capture_rerun(scaffold: Path) -> tuple[_Captured, ScaffoldInputs]:
    """Rebuild identity inputs from one published scaffold (pre-verification)."""
    try:
        scaffold_fd = open_generated_root(scaffold)
    except ScaffoldVerificationError as exc:
        raise PromptRunError(f"cannot open scaffold {scaffold}: {exc}") from exc
    try:
        try:
            manifest_raw = read_regular_file(scaffold_fd, "scaffold.json")
        except SafeTreeError as exc:
            raise PromptRunError(f"scaffold manifest is invalid: {exc}") from exc
        try:
            manifest = json.loads(manifest_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PromptRunError(f"scaffold manifest is invalid: {exc}") from exc
        if not isinstance(manifest, Mapping):
            raise PromptRunError("scaffold manifest is not a JSON object")
        try:
            contract_doc = json.loads(
                read_regular_file(
                    scaffold_fd, "output-contract.json"
                ).decode("utf-8")
            )
            semantic = parse_semantic_contract(
                canonical_json_bytes(contract_doc["semantic"])
            )
        except (SafeTreeError, KeyError, TypeError, UnicodeDecodeError,
                json.JSONDecodeError, PromptContractError) as exc:
            raise PromptRunError(
                f"scaffold output contract is invalid: {exc}") from exc
    finally:
        os.close(scaffold_fd)
    provider_doc = manifest.get("provider")
    if not isinstance(provider_doc, Mapping):
        raise PromptRunError("scaffold manifest provider is not a JSON object")
    provider = provider_doc.get("registry_name")
    if provider not in PUBLIC_PROVIDER_NAMES:
        raise PromptRunError(f"scaffold provider {provider!r} is not public")
    model = provider_doc.get("concrete_model")
    if not isinstance(model, str) or not model:
        raise PromptRunError("scaffold manifest model is missing")
    prompt_sha256 = manifest.get("prompt_sha256")
    if not isinstance(prompt_sha256, str):
        raise PromptRunError("scaffold manifest prompt_sha256 is missing")
    conf_manifest = (
        _admit_conf_dir(scaffold / "conf") if provider == "omp_conf" else None
    )
    captured = _Captured(
        prompt=b"", prompt_sha256=prompt_sha256, provider=provider,
        model=model, conf_manifest=conf_manifest, contract_mode="rerun",
        contract_request=None, slug=scaffold.name[: -13])
    try:
        inputs = ScaffoldInputs(
            prompt_sha256=prompt_sha256, contract=semantic, provider=provider,
            model=model, conf_manifest=conf_manifest, slug=captured.slug,
            pin=OMP_BINARY_PIN,
        )
    except (ValueError, TypeError) as exc:
        raise PromptRunError(f"invalid scaffold inputs: {exc}") from exc
    return captured, inputs


def _exact_contract(payload: str) -> object:
    try:
        return parse_semantic_contract(payload)
    except PromptContractError as exc:
        raise PromptCliError(f"invalid --returns contract: {exc}") from exc








def _infer_output_contract(
    captured: _Captured, runs_root: Path, workspace: Path
) -> tuple[object, dict]:
    """Run the packaged inference workflow; parse only the typed draft."""
    if captured.provider in ("omp", "omp_unrestricted_workspace"):
        raise PromptCliError(
            f"--output is not supported for ambient provider {captured.provider!r}; "
            "use omp_no_tools or omp_conf"
        )
    if captured.contract_request is None:
        raise PromptRunError("--output requires an output request")
    run_id, run_root, identity = _new_reserved_run(runs_root, workspace)
    prompt_inputs = _create_prompt_inputs_root(run_root, identity)
    _write_inference_snapshot(
        prompt_inputs, captured.model, _INFERENCE_PROMPT,
        inference_output_contract_path())
    _revalidate_run_root(run_root, identity)
    ns = run_namespace(
        workflow=str(prompt_inputs / "infer-output-contract.orc"),
        input=[
            f"task_prompt={captured.prompt.decode('utf-8')}",
            f"output_request={captured.contract_request}",
        ],
        state_dir=str(runs_root),
        source_root=[str(prompt_inputs)],
        provider_externs_file=str(prompt_inputs / "providers.json"),
        prompt_externs_file=str(prompt_inputs / "prompts.json"),
    )
    result = run_workflow(ns, run_id=run_id, expected_run_identity=identity)
    if result.run_id != run_id or result.run_root != run_root:
        raise PromptRunError(
            f"inference run identity mismatch: {result.run_id!r}/{result.run_root!r} "
            f"!= {run_id!r}/{run_root!r}")
    if result.exit_code != 0:
        raise PromptRunError(f"output inference failed with exit code {result.exit_code}")
    try:
        contract = parse_inferred_draft(
            {"fields": _thaw_frozen(
                result.workflow_outputs.get("return__fields"))},
            prompt_sha256=captured.prompt_sha256,
        )
    except PromptContractError as exc:
        raise PromptRunError(f"invalid inferred output contract: {exc}") from exc
    usage_rows = _thaw_frozen(result.usage)
    record = next(
        (r for r in usage_rows.values()
         if isinstance(r, dict) and r.get("session_id")),
        {},
    )
    authoring = {
        "mode": "inferred",
        "output_request_sha256": sha256_hex(captured.contract_request.encode("utf-8")),
        "provider": INFERENCE_PROVIDER,
        "model": captured.model,
        "session_id": record.get("session_id"),
        "usage": record.get("usage") or _ZERO_USAGE,
    }
    try:
        authoring = validate_authoring(authoring)
    except PromptContractError as exc:
        raise PromptRunError(f"invalid inference provenance: {exc}") from exc
    return contract, authoring


def _resolve_contract(
    captured: _Captured, runs_root: Path, workspace: Path
) -> tuple[object, dict]:
    """The admitted contract/authoring from the captured mode/payload only.

    ``_Captured`` freezes the contract mode and payload before any inference
    or destination creation; later mutation of the parsed CLI mode dict
    cannot change which contract runs.
    """
    if captured.contract_mode == "exact":
        return _exact_contract(captured.contract_request), {"mode": "exact"}
    if captured.contract_mode == "inferred":
        return _infer_output_contract(captured, runs_root, workspace)
    return default_semantic_contract(), {"mode": "default"}




def prompt_workflow(args: Namespace) -> int:
    """Entry for `orchestrate prompt run`; returns the process exit code."""
    if getattr(args, "prompt_command", None) == "import":
        from orchestrator.cli.commands.prompt_import import prompt_import_workflow
        return prompt_import_workflow(args)
    if getattr(args, "prompt_command", None) == "resume":
        from orchestrator.prompt_resume import prompt_resume_workflow
        return prompt_resume_workflow(args)
    try:
        mode = _parse_prompt_run(args)
        workspace = Path.cwd()
        runs_root = workspace / ".orchestrate" / "runs"
        if mode["kind"] == "rerun":
            scaffold_workspace = mode["scaffold"].resolve().parents[2]
            if scaffold_workspace != workspace.resolve():
                raise PromptRunError(
                    "rerun scaffold must belong to the current workspace"
                )
            run_id, run_root, identity = _new_reserved_run(runs_root, workspace)
            captured, inputs = _capture_rerun(mode["scaffold"])
            verification = prompt_scaffold.verify_scaffold(
                generated_root=mode["scaffold"].parent,
                inputs=inputs, name=mode["scaffold"].name)
            return materialize_and_run(
                workspace=workspace, runs_root=runs_root, run_id=run_id,
                run_root=run_root, identity=identity, captured=captured,
                contract=verification.semantic_contract,
                verification=verification, print_scaffold=False,
                scaffold_path=mode["scaffold"],
                scaffold_workspace=workspace.resolve(),
            )
        captured = _capture_generation(mode)
        contract, authoring = _resolve_contract(captured, runs_root, workspace)
        try:
            inputs = ScaffoldInputs(
                prompt_sha256=captured.prompt_sha256, contract=contract,
                provider=captured.provider, model=captured.model,
                conf_manifest=captured.conf_manifest, slug=captured.slug,
                pin=OMP_BINARY_PIN,
            )
        except (ValueError, TypeError) as exc:
            raise PromptRunError(f"invalid scaffold inputs: {exc}") from exc
        run_id, run_root, identity = _new_reserved_run(runs_root, workspace)
        scaffold = prompt_scaffold.generate_scaffold(
            generated_root=_ensure_generated_root(workspace),
            inputs=inputs,
            prompt_bytes=captured.prompt,
            authoring=authoring,
        )
        return materialize_and_run(
            workspace=workspace, runs_root=runs_root, run_id=run_id,
            run_root=run_root, identity=identity, captured=captured,
            contract=contract, verification=scaffold.verification,
            print_scaffold=True, scaffold_path=scaffold.path,
        )
    except PromptCliError as exc:
        print(f"prompt run: {exc}", file=sys.stderr)
        return 2
    except (PromptRunError, PromptSessionError, ScaffoldCompileError,
            ScaffoldVerificationError, ScaffoldSnapshotError) as exc:
        print(f"prompt run: {exc}", file=sys.stderr)
        return 1
