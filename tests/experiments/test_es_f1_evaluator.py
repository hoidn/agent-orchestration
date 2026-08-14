from __future__ import annotations

from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
from types import SimpleNamespace
from typing import Any

from jsonschema import Draft202012Validator
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments.es import f1_evaluator as evaluator  # noqa: E402
from scripts.experiments.es.task_package import scan_configuration_consumers  # noqa: E402


EVALUATOR_ROOT = ROOT / "experiments/orc_effectiveness/f1_es/evaluator"
F1_ROOT = ROOT / "experiments/orc_effectiveness/f1_es"
FIXTURE_MANIFEST = EVALUATOR_ROOT / "fixture-manifest.json"
CALIBRATION_CASES = ROOT / "tests/experiments/fixtures/es_f1/calibration-cases.json"
HARD_FINDING_SCHEMA = EVALUATOR_ROOT / "hard-finding.schema.json"
FIXTURE_ADAPTER = ROOT / "tests/experiments/fixtures/es_f1/config_resolution_adapter.py"

CLAUSES = (
    "F1-H01-FOCUSED-SUITES",
    "F1-H02-SCHEMA-CONFORMANCE",
    "F1-H03-PUBLIC-RESOLUTION",
    "F1-H04-TRANSACTIONAL-APPLICATION",
    "F1-H05-STRICT-INPUT-CONTRACT",
    "F1-H06-DERIVED-PUBLIC-FIELDS",
    "F1-H07-CONSUMER-CLOSURE",
    "F1-H08-PROVENANCE-ROUNDTRIP",
    "F1-H09-CROSS-SURFACE-COHERENCE",
    "F1-H10-BYPASS-ORACLE",
)
ROLES = ("SIMULATION", "TRAINING", "INFERENCE", "RUNTIME_EXECUTION")
HOOKS = (
    "CONFIG_SURFACE",
    "CONFIG_CARRIER",
    "TORCH_TRANSACTION",
    "SIMULATION_DERIVATION",
)
BYPASSES = (
    "AMBIENT_CONFIGURATION_READ",
    "TOLERANT_OR_COMPATIBILITY_LOADER",
    "LEGACY_CONFIGURATION_STATE_MUTATION",
)
SELECTORS = ("tests/test_baseline.py",)
CANDIDATE_SELECTOR = "tests/test_es_f1_config_ownership.py"
DESELECTED_NODES = ("tests/test_baseline.py::test_retired_contract",)
DIGEST = "sha256:" + "1" * 64


def _candidate_claims() -> dict[str, Any]:
    return {
        "candidate_id": "candidate-a",
        "claims": [
            {
                "clause_id": clause,
                "evidence_paths": [CANDIDATE_SELECTOR],
                "scope": "IMPLEMENTED",
            }
            for clause in CLAUSES
        ],
        "configuration_decision_path": "docs/configuration-decision.md",
        "evaluation_hooks": [
            {"hook_id": hook_id, "symbol": f"candidate.hooks.{hook_id.lower()}"}
            for hook_id in HOOKS
        ],
        "fixed_outputs": {
            "adapter_path": "scripts/es_f1_config_resolution_adapter.py",
            "candidate_test_path": CANDIDATE_SELECTOR,
        },
        "migration_guide_path": "docs/configuration-migration.md",
        "public_resolution_routes": [
            {"roles": list(ROLES), "symbol": "candidate.config.resolve"}
        ],
        "schema_version": "candidate_config_evidence.v2",
    }


def _visible_result() -> dict[str, Any]:
    return {
        "copy_digest_after": DIGEST,
        "copy_digest_before": DIGEST,
        "invocations": [
            {
                "argv": [sys.executable, "-m", "pytest", *SELECTORS],
                "exit_code": 0,
                "invocation_id": "PRE_EDIT_FOCUSED",
                "deselectors": [],
                "selectors": list(SELECTORS),
                "stderr_sha256": DIGEST,
                "stdout_sha256": DIGEST,
            },
            {
                "argv": [sys.executable, "-m", "pytest", CANDIDATE_SELECTOR],
                "exit_code": 0,
                "invocation_id": "CANDIDATE_CONFIG",
                "deselectors": [],
                "selectors": [CANDIDATE_SELECTOR],
                "stderr_sha256": DIGEST,
                "stdout_sha256": DIGEST,
            },
        ],
        "schema_version": "es-f1-visible-check-result.v3",
    }


def _root_visible_result() -> dict[str, Any]:
    result = _visible_result()
    result["invocations"][0]["selectors"] = list(
        evaluator.F1_PROVIDER_VISIBLE_SELECTORS
    )
    result["invocations"][0]["deselectors"] = list(
        evaluator.F1_PROVIDER_VISIBLE_DESELECTORS
    )
    result["invocations"][0]["argv"] = [
        sys.executable,
        "-m",
        "pytest",
        *evaluator.F1_PROVIDER_VISIBLE_SELECTORS,
        *(f"--deselect={node}" for node in evaluator.F1_PROVIDER_VISIBLE_DESELECTORS),
    ]
    return result


def _failed(observations: list[dict[str, Any]]) -> set[str]:
    return {row["clause_id"] for row in observations if not row["satisfied"]}


def _write_canonical(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(evaluator.canonical_json_bytes(value))


def _candidate_workspace(tmp_path: Path, *, resolver_body: str) -> tuple[Path, Path]:
    workspace = tmp_path / "candidate"
    (workspace / "candidate").mkdir(parents=True)
    (workspace / "candidate/__init__.py").write_text("", encoding="utf-8")
    (workspace / "candidate/config.py").write_text(resolver_body, encoding="utf-8")
    (workspace / "candidate/hooks.py").write_text(
        textwrap.dedent(
            """
            import base64
            from dataclasses import asdict, dataclass, fields, is_dataclass
            import hashlib
            import json

            from candidate.config import SimulationConfig, derive_fields, resolve

            def _bytes(value):
                return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

            def _merge(left, right):
                result = dict(left)
                for key, value in right.items():
                    result[key] = _merge(result[key], value) if key in result and isinstance(result[key], dict) and isinstance(value, dict) else value
                return result

            def _sources(value, file_mapping, cli_patch, prefix=""):
                result = {}
                for key, item in value.items():
                    pointer = prefix + "/" + key
                    file_item = file_mapping.get(key)
                    patch_item = cli_patch.get(key)
                    if isinstance(item, dict):
                        result.update(_sources(item, file_item if isinstance(file_item, dict) else {}, patch_item if isinstance(patch_item, dict) else {}, pointer))
                    else:
                        result[pointer] = "CLI_PATCH" if key in cli_patch else "FILE_MAPPING" if key in file_mapping else "DEFAULT"
                return result

            def resolve_surface(file_mapping, cli_patch):
                value = resolve(file_mapping, cli_patch)
                resolved = asdict(value) if is_dataclass(value) else value
                return {"resolved": resolved, "source_by_pointer": _sources(resolved, file_mapping, cli_patch)}

            def simulation_surface(file_mapping, cli_patch): return resolve_surface(file_mapping, cli_patch)
            def core_surface(file_mapping, cli_patch): return resolve_surface(file_mapping, cli_patch)
            def torch_surface(file_mapping, cli_patch): return resolve_surface(file_mapping, cli_patch)
            def cli_surface(file_mapping, cli_patch): return resolve_surface(file_mapping, cli_patch)
            def workflow_surface(file_mapping, cli_patch): return resolve_surface(file_mapping, cli_patch)
            def study_surface(file_mapping, cli_patch): return resolve_surface(file_mapping, cli_patch)

            def config_surface(request):
                if request == {"op": "DESCRIBE"}:
                    return {"surface_symbols": {
                        "SIMULATION": "candidate.hooks.simulation_surface",
                        "CORE": "candidate.hooks.core_surface",
                        "TORCH": "candidate.hooks.torch_surface",
                        "CLI": "candidate.hooks.cli_surface",
                        "WORKFLOW": "candidate.hooks.workflow_surface",
                        "STUDY": "candidate.hooks.study_surface",
                    }}
                target = {
                    "SIMULATION": simulation_surface,
                    "CORE": core_surface,
                    "TORCH": torch_surface,
                    "CLI": cli_surface,
                    "WORKFLOW": workflow_surface,
                    "STUDY": study_surface,
                }[request["surface"]]
                return target(request["file_mapping"], request["cli_patch"])

            def config_carrier(request):
                if request["op"] == "ENCODE":
                    payload = _bytes(request["carrier"])
                    return {"payload_b64": base64.b64encode(payload).decode(), "payload_sha256": "sha256:" + hashlib.sha256(payload).hexdigest()}
                return {"carrier": json.loads(base64.b64decode(request["payload_b64"], validate=True))}

            _state = {}
            def commit(value):
                _state.update(value)
            def apply(file_mapping, cli_patch):
                value = resolve_surface(file_mapping, cli_patch)
                before = dict(_state)
                try:
                    commit(value["resolved"])
                except Exception:
                    _state.clear()
                    _state.update(before)
                    raise
                return value
            def torch_transaction(request):
                if request == {"op": "DESCRIBE"}:
                    return {"apply_symbol": "candidate.hooks.apply", "commit_symbol": "candidate.hooks.commit", "state_symbols": ["candidate.hooks._state"]}
                return apply(request["file_mapping"], request["cli_patch"])

            def derive(owner):
                return derive_fields(owner)
            def simulation_derivation(request):
                if request == {"op": "DESCRIBE"}:
                    return {"resolver_symbol": "candidate.config.resolve", "owners": [{"owner_symbol": "candidate.config.SimulationConfig", "deriver_symbol": "candidate.config.derive_fields"}]}
                return {"fields": list(derive(SimulationConfig))}
            """
        ),
        encoding="utf-8",
    )
    adapter = workspace / "scripts/es_f1_config_resolution_adapter.py"
    adapter.parent.mkdir()
    shutil.copy2(FIXTURE_ADAPTER, adapter)
    evidence_path = workspace / "es_f1_candidate_evidence.json"
    _write_canonical(evidence_path, _candidate_claims())
    return workspace, evidence_path


def _inspect_added_consumer(
    tmp_path: Path, relative: str, source: str
) -> dict[str, Any]:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    path = workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [
                {
                    "consumer_id": "authority",
                    "path": "candidate/config.py",
                    "public_entry_route": "candidate.config.resolve",
                }
            ]
        },
        workspace=workspace,
    )


def _synthetic_owner_route(
    tmp_path: Path,
    *,
    module: str,
    owner: str,
    source: str,
    available_external_imports: frozenset[str] = frozenset(),
) -> tuple[list[str], set[str], bool]:
    path = tmp_path.joinpath(*module.split(".")).with_suffix(".py")
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        module,
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=[{"public_entry_route": owner}],
        workspace_module_roots=frozenset({module.split(".", 1)[0]}),
        available_external_imports=available_external_imports,
    )
    result = evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": "synthetic-owner",
            "entry_symbol": owner,
            "requires_authority": False,
        }],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )
    return graph[owner], terminals, result["closed"]


@pytest.mark.parametrize(
    ("import_source", "call", "target"),
    (
        ("from dataclasses import replace\n", "replace(value)", "dataclasses.replace"),
        ("from pathlib import Path\n", "Path(value)", "pathlib.Path"),
        ("import numpy as np\n", "np.asarray(value)", "numpy.asarray"),
    ),
    ids=("dataclasses", "pathlib", "numpy-like"),
)
def test_contextual_external_target_is_terminal(
    tmp_path: Path,
    import_source: str,
    call: str,
    target: str,
) -> None:
    path = tmp_path / "package/sink.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        import_source + "def adapt(value):\n" f"    return {call}\n",
        encoding="utf-8",
    )
    context = "@context:package.sink.adapt:value"
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "package.sink",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=[{
            "context_symbol": context,
            "public_entry_route": "package.sink.adapt",
            "tainted_formals": ["value"],
        }],
        workspace_module_roots=frozenset({"package"}),
        available_external_imports=frozenset({target}),
    )

    assert graph[context] == [target]
    assert target in terminals
    assert evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": "contextual-external",
            "entry_symbol": context,
            "requires_authority": False,
        }],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )["closed"] is True


def test_contextual_tolerant_external_loader_is_not_terminal(tmp_path: Path) -> None:
    path = tmp_path / "package/sink.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "from dependency import fallback_loader\n"
        "def adapt(value):\n"
        "    return fallback_loader(value)\n",
        encoding="utf-8",
    )
    context = "@context:package.sink.adapt:value"
    target = "dependency.fallback_loader"
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "package.sink",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=[{
            "context_symbol": context,
            "public_entry_route": "package.sink.adapt",
            "tainted_formals": ["value"],
        }],
        workspace_module_roots=frozenset({"package"}),
        available_external_imports=frozenset({target}),
    )

    assert graph[context] == [target]
    assert target not in terminals
    assert bypasses[context] == ("TOLERANT_OR_COMPATIBILITY_LOADER",)
    assert evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": "contextual-tolerant-external",
            "entry_symbol": context,
            "requires_authority": False,
        }],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )["closed"] is False


@pytest.mark.parametrize(
    "mutation",
    (
        "json.dumps = replacement\n",
        "setattr(json, 'dumps', replacement)\n",
        "mutate(json)\n",
        "other.dumps = replacement\n",
        "setattr(other, 'dumps', replacement)\n",
    ),
    ids=(
        "member-assignment",
        "setattr",
        "unknown-call-escape",
        "second-alias-assignment",
        "second-alias-setattr",
    ),
)
def test_contextual_mutated_external_target_is_not_terminal(
    tmp_path: Path,
    mutation: str,
) -> None:
    path = tmp_path / "package/sink.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "import json\n"
        "import json as other\n"
        "def replacement(value):\n"
        "    return value\n"
        "def mutate(value):\n"
        "    return None\n"
        + mutation
        + "def adapt(value):\n"
        + "    return json.dumps(value)\n",
        encoding="utf-8",
    )
    context = "@context:package.sink.adapt:value"
    target = "json.dumps"
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "package.sink",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=[{
            "context_symbol": context,
            "public_entry_route": "package.sink.adapt",
            "tainted_formals": ["value"],
        }],
        workspace_module_roots=frozenset({"package"}),
        available_external_imports=frozenset({target}),
    )

    assert target in graph[context]
    assert target not in terminals
    assert evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": "contextual-mutated-external",
            "entry_symbol": context,
            "requires_authority": False,
        }],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )["closed"] is False


def test_contextual_zero_arg_helper_cannot_reassign_external_target(
    tmp_path: Path,
) -> None:
    path = tmp_path / "package/sink.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "import json\n"
        "def replacement(value):\n"
        "    return value\n"
        "def poison():\n"
        "    json.dumps = replacement\n"
        "def adapt(value):\n"
        "    poison()\n"
        "    return json.dumps(value)\n",
        encoding="utf-8",
    )
    context = "@context:package.sink.adapt:value"
    target = "json.dumps"
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "package.sink",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=[{
            "context_symbol": context,
            "public_entry_route": "package.sink.adapt",
            "tainted_formals": ["value"],
        }],
        workspace_module_roots=frozenset({"package"}),
        available_external_imports=frozenset({target}),
    )

    assert target in graph[context]
    assert target not in terminals
    assert evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": "contextual-helper-reassigned-external",
            "entry_symbol": context,
            "requires_authority": False,
        }],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )["closed"] is False


def _conforming_protocol_workspace(tmp_path: Path) -> tuple[Path, Path]:
    return _candidate_workspace(
        tmp_path,
        resolver_body=textwrap.dedent(
            """
            from copy import deepcopy
            from dataclasses import dataclass, fields
            from types import UnionType
            from typing import get_args, get_origin

            @dataclass
            class Model:
                N: int = None
                generator_output_mode: str = None
                rect_s1s2_init: str = None

            @dataclass
            class RuntimeConfig:
                model: Model = None
                n_groups: int = None
                n_subsample: int = None
                subsample_seed: int = None
                enable_oversampling: bool = None
                neighbor_pool_size: int = None
                sequential_sampling: bool = None
                batch_size: int = None
                model_path: str = None
                test_data_file: str = None

            @dataclass
            class Probe:
                source: str = None
                ideal_scale: float = None

            @dataclass
            class Object:
                kind: str = None
                image_size: list[int] = None
                objects_per_probe: int = None
                diffractions_per_object: int = None
                set_phi: bool = None
                patch_amplitude_normalization: str = None

            @dataclass
            class Scan:
                kind: str = None
                grid_size: list[int] = None
                offset: int = None
                outer_offset_train: int = None
                outer_offset_test: int = None
                train_groups: int = None
                test_groups: int = None
                buffer: int = None
                position_layout: str = None

            @dataclass
            class Detector:
                photons_per_pattern: float = None
                beamstop_diameter: float = None

            @dataclass
            class SimulationConfig:
                N: int = None
                seed: int = None
                probe: Probe = None
                object: Object = None
                scan: Scan = None
                detector: Detector = None

            def derive_fields(owner):
                return tuple(sorted(field.name for field in fields(owner)))

            def _merge(left, right):
                result = deepcopy(left)
                for key, value in right.items():
                    if key in result and isinstance(value, dict) and isinstance(result[key], dict):
                        result[key] = _merge(result[key], value)
                    else:
                        result[key] = deepcopy(value)
                return result

            def _validate(cls, value):
                if not isinstance(value, dict):
                    raise TypeError("mapping required")
                owner_fields = {field.name: field.type for field in fields(cls)}
                declared = {name: owner_fields[name] for name in derive_fields(cls)}
                result = {}
                for key, item in value.items():
                    if key not in declared:
                        raise ValueError("unknown field")
                    expected = declared[key]
                    if hasattr(expected, "__dataclass_fields__"):
                        result[key] = _validate(expected, item)
                        continue
                    origin = get_origin(expected)
                    if origin is list:
                        args = get_args(expected)
                        if not isinstance(item, list) or any(type(part) is not args[0] for part in item):
                            raise TypeError("invalid list field")
                    elif type(item) is not expected:
                        raise TypeError("invalid scalar field")
                    if key in {"N", "n_groups", "batch_size"} and item < 1:
                        raise ValueError("non-positive field")
                    if key == "grid_size" and len(item) != 2:
                        raise ValueError("invalid grid")
                    result[key] = deepcopy(item)
                return cls(**result)

            def resolve(file_mapping, cli_patch):
                resolved = _merge(file_mapping, cli_patch)
                owner = SimulationConfig if "probe" in resolved else RuntimeConfig
                return _validate(owner, resolved)
            """
        ),
    )


def _run_direct_protocol(
    tmp_path: Path, workspace: Path, evidence_path: Path
) -> dict[str, Any]:
    return evaluator.run_direct_resolver_probe(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "direct-probe",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )


def _mutated_protocol_workspace(
    tmp_path: Path, old: str, new: str
) -> tuple[Path, Path]:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    source_path = workspace / "candidate/config.py"
    source = source_path.read_text(encoding="utf-8")
    assert source.count(old) == 1
    source_path.write_text(source.replace(old, new), encoding="utf-8")
    return workspace, evidence_path


def _request(candidate_evidence_digest: str) -> dict[str, Any]:
    return {
        "candidate_evidence_path": "es_f1_candidate_evidence.json",
        "candidate_evidence_sha256": candidate_evidence_digest,
        "candidate_id": "candidate-a",
        "operation_version": "ptychopinn_public_config_resolution.v1",
        "probe_cases": [
            {
                "case_id": "strict-precedence",
                "cli_patch": {
                    "path": "inputs/cli.json",
                    "sha256": "sha256:" + "0" * 64,
                },
                "file_mapping": {
                    "path": "inputs/file.json",
                    "sha256": "sha256:" + "0" * 64,
                },
                "role": "TRAINING",
            }
        ],
        "schema_version": "config_resolution_probe_request.v1",
    }


def test_f1v2_constants_replace_the_architecture_vocabulary() -> None:
    assert evaluator.HARD_CLAUSE_IDS == CLAUSES
    assert evaluator.CONFIG_RESOLUTION_ROLES == ROLES
    assert evaluator.BYPASS_CLASSES == BYPASSES
    for obsolete in (
        "ARTIFACT_ERA_IDS",
        "derive_lifecycle_observations",
        "classify_task0_bypass_discovery",
        "build_artifact_fixture_pack",
    ):
        assert not hasattr(evaluator, obsolete)


def test_four_declared_hooks_execute_under_strict_json_abi(tmp_path: Path) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)

    result = evaluator.run_evaluation_hooks(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "hooks",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert [row["hook_id"] for row in result["transcript"]] == list(HOOKS)
    assert [row["operations"] for row in result["transcript"]] == [
        ["DESCRIBE"],
        ["ENCODE", "ENCODE", "DECODE"],
        ["DESCRIBE"],
        ["DESCRIBE", "CATALOG"],
    ]
    assert result["facts"] == {
        "F1-H04-TRANSACTIONAL-APPLICATION": False,
        "F1-H06-DERIVED-PUBLIC-FIELDS": False,
        "F1-H08-PROVENANCE-ROUNDTRIP": False,
        "F1-H09-CROSS-SURFACE-COHERENCE": False,
    }


def test_hook_output_cannot_forge_an_evaluator_fact(tmp_path: Path) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    hooks = workspace / "candidate/hooks.py"
    hooks.write_text(
        hooks.read_text(encoding="utf-8").replace(
            'return {"surface_symbols":',
            'return {"passed": True, "surface_symbols":',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(evaluator.EvaluatorError, match="authority|field set"):
        evaluator.run_evaluation_hooks(
            candidate_evidence_path=evidence_path,
            output_root=tmp_path / "hooks",
            python_executable=Path(sys.executable),
            timeout_seconds=30,
            workspace=workspace,
        )


def test_surface_and_carrier_proof_executes_real_targets_and_fresh_decode(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)

    result = evaluator.run_surface_and_carrier_proof(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "surface-proof",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {
        "F1-H03-PUBLIC-RESOLUTION": True,
        "F1-H08-PROVENANCE-ROUNDTRIP": True,
        "F1-H09-CROSS-SURFACE-COHERENCE": True,
    }
    assert result["runtime_bypass_classes"] == []
    assert len(result["surface_transcript"]["rows"]) == 30


def test_surface_hook_that_does_not_forward_target_result_fails_closed(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    hooks = workspace / "candidate/hooks.py"
    source = hooks.read_text(encoding="utf-8")
    hooks.write_text(
        source.replace(
            '    return target(request["file_mapping"], request["cli_patch"])',
            '    target(request["file_mapping"], request["cli_patch"])\n'
            '    return {"resolved": {}, "source_by_pointer": {}}',
        ),
        encoding="utf-8",
    )

    result = evaluator.run_surface_and_carrier_proof(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "surface-proof",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {
        "F1-H03-PUBLIC-RESOLUTION": False,
        "F1-H08-PROVENANCE-ROUNDTRIP": False,
        "F1-H09-CROSS-SURFACE-COHERENCE": False,
    }


def test_runtime_hidden_getenv_fails_h10_when_ast_oracle_misses_it(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    config = workspace / "candidate/config.py"
    source = config.read_text(encoding="utf-8").replace(
        "from typing import get_args, get_origin\n",
        "from typing import get_args, get_origin\n"
        "_hidden_getenv = getattr(__import__('os'), ''.join(('get', 'env')))\n",
    ).replace(
        "def resolve(file_mapping, cli_patch):\n",
        "def resolve(file_mapping, cli_patch):\n"
        "    _hidden_getenv('ES_F1_RUNTIME_ONLY')\n",
    )
    config.write_text(source, encoding="utf-8")
    assert "AMBIENT_CONFIGURATION_READ" not in evaluator.detect_ast_bypasses(source)

    observations = evaluator._evaluate_candidate(
        calibration_cases=[{
            "case_id": "nested-precedence",
            "defect_kind": "none",
            "expected_failed_clauses": [],
            "probe": {
                "cli_patch": {"model": {"N": 128}, "n_groups": 7},
                "file_mapping": _TRAINING_ROOT_INPUT,
                "role": "TRAINING",
            },
        }],
        candidate_evidence_path=evidence_path,
        consumer_census={"rows": [{
            "consumer_id": "public-resolution",
            "path": "candidate/config.py",
            "public_entry_route": "candidate.config.resolve",
        }]},
        output_root=tmp_path / "evaluation",
        package_conformance={
            "candidate_evidence": "candidate_config_evidence.v2",
            "probe_request": "config_resolution_probe_request.v1",
            "probe_result": "config_resolution_probe_result.v1",
            "validated": True,
        },
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        visible_result=_root_visible_result(),
        workspace=workspace,
    )
    h10 = next(row for row in observations if row["clause_id"] == "F1-H10-BYPASS-ORACLE")
    assert h10["satisfied"] is False
    transcript = json.loads(
        (tmp_path / "evaluation/surface-proof/surface-transcript.json").read_bytes()
    )
    assert evaluator.normalize_bypass_events(transcript["runtime_bypass_events"]) == (
        "AMBIENT_CONFIGURATION_READ",
    )


def test_simulation_derivation_proof_binds_owner_and_sentinel(tmp_path: Path) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)

    result = evaluator.run_simulation_derivation_proof(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "derivation-proof",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {"F1-H06-DERIVED-PUBLIC-FIELDS": True}
    assert result["transcript"]["rows"][0] == {
        "called_by_resolver": True,
        "direct_fields": ["N", "detector", "object", "probe", "scan", "seed"],
        "owner_present": True,
        "owner_symbol": "candidate.config.SimulationConfig",
        "sentinel_derived": True,
    }


def test_fixed_simulation_catalog_fails_sentinel_derivation(tmp_path: Path) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    source_path = workspace / "candidate/config.py"
    source = source_path.read_text(encoding="utf-8")
    source_path.write_text(
        source.replace(
            "return tuple(sorted(field.name for field in fields(owner)))",
            'return ("N", "detector", "object", "probe", "scan", "seed") if any(base.__name__ == "SimulationConfig" for base in owner.__mro__) else tuple(sorted(field.name for field in fields(owner)))',
        ),
        encoding="utf-8",
    )

    result = evaluator.run_simulation_derivation_proof(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "derivation-proof",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {"F1-H06-DERIVED-PUBLIC-FIELDS": False}


def test_torch_transaction_proof_counts_commit_and_rolls_back(tmp_path: Path) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)

    result = evaluator.run_torch_transaction_proof(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "transaction-proof",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {"F1-H04-TRANSACTIONAL-APPLICATION": True}
    assert [row["commit_count"] for row in result["transcripts"]] == [1, 0, 1]
    assert result["transcripts"][1]["before"] == result["transcripts"][1]["after"]
    assert result["transcripts"][2]["before"] == result["transcripts"][2]["after"]


def test_transaction_state_omission_cannot_hide_the_mutated_global(tmp_path: Path) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    hooks = workspace / "candidate/hooks.py"
    source = hooks.read_text(encoding="utf-8")
    hooks.write_text(
        source.replace("_state = {}", "_other = {}\n_state = {}").replace(
            '["candidate.hooks._state"]', '["candidate.hooks._other"]'
        ),
        encoding="utf-8",
    )

    result = evaluator.run_torch_transaction_proof(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "transaction-proof",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {"F1-H04-TRANSACTIONAL-APPLICATION": False}


def test_checked_in_evaluator_assets_are_one_coherent_successor() -> None:
    fixtures = evaluator.load_controller_asset(
        FIXTURE_MANIFEST,
        expected_schema_version="es-f1-fixture-manifest.v3",
    )
    calibration = evaluator.load_controller_asset(
        CALIBRATION_CASES,
        expected_schema_version="es-f1-calibration-cases.v4",
    )
    assert tuple(fixtures["hard_clause_ids"]) == CLAUSES
    assert tuple(fixtures["configuration_roles"]) == ROLES
    assert tuple(fixtures["bypass_classes"]) == BYPASSES
    assert fixtures["versions"] == {
        "candidate_evidence": "candidate_config_evidence.v2",
        "hard_evaluation": "es-f1-hard-evaluation.v3",
        "hard_finding": "es-f1-hard-finding.v3",
        "probe_request": "config_resolution_probe_request.v1",
        "probe_result": "config_resolution_probe_result.v1",
        "visible_result": "es-f1-visible-check-result.v3",
    }
    assert fixtures["calibration_cases"]["schema_version"] == calibration["schema_version"]
    assert fixtures["calibration_cases"]["sha256"] == evaluator.file_sha256(CALIBRATION_CASES)
    assert fixtures["fixture_adapter"] == {
        "path": "tests/experiments/fixtures/es_f1/config_resolution_adapter.py",
        "policy": "path-only.v1",
        "sha256": evaluator.file_sha256(FIXTURE_ADAPTER),
    }
    positives = [row for row in calibration["cases"] if row["defect_kind"] == "none"]
    assert [row["case_id"] for row in positives] == list(
        evaluator.CALIBRATION_POSITIVE_CASE_IDS
    )
    assert all(
        set(row) == {"case_id", "defect_kind", "expected_failed_clauses", "probe"}
        and set(row["probe"]) == {"cli_patch", "file_mapping", "role"}
        for row in positives
    )


def test_public_evaluation_root_has_no_package_injection_parameters() -> None:
    parameters = inspect.signature(evaluator.evaluate_candidate).parameters
    assert set(parameters) == {
        "candidate_evidence_path",
        "output_root",
        "workspace",
    }
    package = evaluator.load_checked_in_evaluator_package()
    assert package["calibration_cases"]["schema_version"] == (
        "es-f1-calibration-cases.v4"
    )


def test_frozen_evaluator_package_binds_the_task1_census_and_selectors() -> None:
    package = evaluator.load_frozen_evaluator_package(
        calibration_cases_path=CALIBRATION_CASES,
        consumer_census_path=(
            ROOT
            / "docs/plans/evidence/es-f1-large-scope-refreeze/f1v2/"
            "configuration-consumer-census.json"
        ),
        fixture_manifest_path=FIXTURE_MANIFEST,
        reviewer_perspectives_path=EVALUATOR_ROOT / "reviewer-perspectives.json",
        task_profile_path=F1_ROOT / "task-profile.json",
        visible_check_path=F1_ROOT / "task/visible-check-manifest.json",
        visible_contract_path=F1_ROOT / "task/visible-task-contract.json",
    )
    assert package["package_conformance"]["validated"] is True
    assert package["consumer_census"]["consumer_count"] == len(
        package["consumer_census"]["rows"]
    )
    assert tuple(package["visible_checks"].pre_edit_selectors) == tuple(
        package["visible_contract"]["focused_selectors"]
    )


def test_mixed_predecessor_evaluator_package_rejects_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = json.loads(FIXTURE_MANIFEST.read_bytes())
    fixture["schema_version"] = "es-f1-fixture-manifest.v2"
    path = tmp_path / "fixture.json"
    _write_canonical(path, fixture)
    calls: list[object] = []
    monkeypatch.setattr(
        evaluator,
        "_run_audited_subprocess",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    with pytest.raises(evaluator.EvaluatorError, match="successor"):
        evaluator.load_frozen_evaluator_package(
            calibration_cases_path=CALIBRATION_CASES,
            consumer_census_path=(
                ROOT
                / "docs/plans/evidence/es-f1-large-scope-refreeze/f1v2/"
                "configuration-consumer-census.json"
            ),
            fixture_manifest_path=path,
            reviewer_perspectives_path=EVALUATOR_ROOT / "reviewer-perspectives.json",
            task_profile_path=F1_ROOT / "task-profile.json",
            visible_check_path=F1_ROOT / "task/visible-check-manifest.json",
            visible_contract_path=F1_ROOT / "task/visible-task-contract.json",
        )
    assert calls == []


def test_frozen_package_rejects_fixture_adapter_digest_tamper(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE_MANIFEST.read_bytes())
    fixture["fixture_adapter"]["sha256"] = "sha256:" + "0" * 64
    path = tmp_path / "fixture.json"
    _write_canonical(path, fixture)

    with pytest.raises(evaluator.EvaluatorError, match="fixture.*binding"):
        evaluator.load_frozen_evaluator_package(
            calibration_cases_path=CALIBRATION_CASES,
            consumer_census_path=(
                ROOT
                / "docs/plans/evidence/es-f1-large-scope-refreeze/f1v2/"
                "configuration-consumer-census.json"
            ),
            fixture_manifest_path=path,
            reviewer_perspectives_path=EVALUATOR_ROOT / "reviewer-perspectives.json",
            task_profile_path=F1_ROOT / "task-profile.json",
            visible_check_path=F1_ROOT / "task/visible-check-manifest.json",
            visible_contract_path=F1_ROOT / "task/visible-task-contract.json",
        )


def test_calibration_manifest_covers_positive_surfaces_and_every_negative() -> None:
    payload = evaluator.load_controller_asset(
        CALIBRATION_CASES,
        expected_schema_version="es-f1-calibration-cases.v4",
    )
    positives = {
        row["case_id"] for row in payload["cases"] if row["defect_kind"] == "none"
    }
    assert positives == {
        "cli_patch",
        "file_mapping",
        "fresh_process_provenance",
        "precedence",
        "public_cli",
        "study_script",
        "strict_roundtrip",
        "tensorflow_backend",
        "torch_backend",
        "workflow_component",
    }
    negatives = {
        row["defect_kind"]: tuple(row["expected_failed_clauses"])
        for row in payload["cases"]
        if row["defect_kind"] != "none"
    }
    assert negatives == evaluator.CALIBRATION_DEFECT_CLAUSES


@pytest.mark.parametrize(
    "mutation",
    ["positive-shape", "positive-role", "negative-shape", "duplicate-id"],
)
def test_calibration_case_contract_is_exact(mutation: str) -> None:
    cases = deepcopy(json.loads(CALIBRATION_CASES.read_bytes())["cases"])
    if mutation == "positive-shape":
        del cases[0]["probe"]
    elif mutation == "positive-role":
        cases[0]["probe"]["role"] = "EXTRA"
    elif mutation == "negative-shape":
        cases[-1]["probe"] = {}
    else:
        cases[-1]["case_id"] = cases[-2]["case_id"]

    with pytest.raises(evaluator.EvaluatorError, match="calibration"):
        evaluator._validate_calibration_cases(cases)


def test_transitive_consumer_walk_does_not_stop_at_a_facade() -> None:
    consumers = [{"consumer_id": "consumer-a", "entry_symbol": "public.start"}]
    assert evaluator.walk_consumer_routes(
        consumer_rows=consumers,
        call_graph={"public.start": ["facade"], "facade": ["authority"]},
        authority_symbols={"authority"},
        bypass_symbols={},
    )["closed"] is True
    result = evaluator.walk_consumer_routes(
        consumer_rows=consumers,
        call_graph={"public.start": ["facade"]},
        authority_symbols={"authority"},
        bypass_symbols={},
    )
    assert result["closed"] is False
    assert result["unresolved_consumers"] == ["consumer-a"]


def test_constructor_route_accepts_analyzed_safe_siblings_but_not_unknown_ones() -> None:
    consumer = [{"consumer_id": "consumer-a", "entry_symbol": "public.start"}]
    assert evaluator.walk_consumer_routes(
        consumer_rows=consumer,
        call_graph={"public.start": ["authority", "safe"], "safe": []},
        authority_symbols={"authority"},
        bypass_symbols={},
    )["closed"] is True
    assert evaluator.walk_consumer_routes(
        consumer_rows=consumer,
        call_graph={"public.start": ["authority", "unknown"]},
        authority_symbols={"authority"},
        bypass_symbols={},
    )["closed"] is False


def test_wrapper_deep_bypass_is_not_hidden_by_an_authority_sibling() -> None:
    result = evaluator.walk_consumer_routes(
        consumer_rows=[{"consumer_id": "consumer-a", "entry_symbol": "entry"}],
        call_graph={
            "entry": ["wrapper"],
            "wrapper": ["authority", "old.path"],
            "old.path": ["authority"],
        },
        authority_symbols={"authority"},
        bypass_symbols={"old.path": "TOLERANT_OR_COMPATIBILITY_LOADER"},
    )
    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


def test_resolved_value_read_need_not_reenter_authority_but_bypass_still_fails() -> None:
    consumer = [{
        "consumer_id": "read-a",
        "entry_symbol": "read.value",
        "requires_authority": False,
    }]
    assert evaluator.walk_consumer_routes(
        consumer_rows=consumer,
        call_graph={"read.value": []},
        authority_symbols={"authority"},
        bypass_symbols={},
    )["closed"] is True
    result = evaluator.walk_consumer_routes(
        consumer_rows=consumer,
        call_graph={"read.value": ["old.path"]},
        authority_symbols={"authority"},
        bypass_symbols={"old.path": "TOLERANT_OR_COMPATIBILITY_LOADER"},
    )
    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]

    missing = evaluator.walk_consumer_routes(
        consumer_rows=consumer,
        call_graph={},
        authority_symbols={"authority"},
        bypass_symbols={},
    )
    assert missing["closed"] is False
    assert missing["unresolved_consumers"] == ["read-a"]


def test_resolved_value_read_may_terminate_at_an_analyzed_helper() -> None:
    result = evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": "read-a",
            "entry_symbol": "read.value",
            "requires_authority": False,
        }],
        call_graph={"read.value": ["read.helper"], "read.helper": []},
        authority_symbols={"authority"},
        bypass_symbols={},
    )

    assert result["closed"] is True
    assert result["unresolved_consumers"] == []


def test_resolved_value_read_may_reach_an_external_terminal_operation() -> None:
    result = evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": "read-a",
            "entry_symbol": "read.value",
            "requires_authority": False,
        }],
        call_graph={"read.value": ["numpy.squeeze"]},
        authority_symbols={"authority"},
        bypass_symbols={},
        terminal_symbols={"numpy.squeeze"},
    )

    assert result["closed"] is True
    assert result["unresolved_consumers"] == []


@pytest.mark.parametrize(
    "terminal",
    (
        "build_config",
        "TrainingConfig",
        "_fresh_config",
        "profile.to_model_config",
        "setup_configuration",
        "setup_inference_configuration",
        "make_config",
    ),
)
def test_only_configuration_authority_construction_requires_resolution(
    terminal: str,
) -> None:
    assert evaluator._requires_resolution_authority({
        "match_kind": "CONFIGURATION_CONSTRUCTION",
        "transitive_wrapper_chain": ["consumer", terminal],
    }) is True


def test_ast_and_runtime_oracle_use_only_the_three_closed_classes() -> None:
    source = """
import os

def resolve(config, legacy_config):
    mode = os.getenv("MODE")
    value = config.get("value", 1)
    legacy_config.mode = mode
    return value
"""
    assert evaluator.detect_ast_bypasses(
        source, _tainted_names=("config", "legacy_config")
    ) == BYPASSES
    with pytest.raises(evaluator.EvaluatorError, match="bypass class"):
        evaluator.normalize_bypass_events(
            [{"class_id": "NEW_CLASS", "consumer_id": "a", "symbol": "a"}]
        )


def test_explicit_scalar_conversion_is_a_tolerant_loader_bypass() -> None:
    assert evaluator.detect_ast_bypasses(
        "def resolve(file_mapping):\n    return str(file_mapping['mode'])\n",
        _tainted_names=("file_mapping",),
    ) == ("TOLERANT_OR_COMPATIBILITY_LOADER",)


def test_data_loader_is_not_a_tolerant_configuration_loader() -> None:
    assert evaluator.detect_ast_bypasses(
        "import ptycho.loader\n"
        "def consume(config):\n"
        "    dataset = lambda: range(config['N'])\n"
        "    return ptycho.loader.load(dataset)\n",
        _tainted_names=("config",),
    ) == ()
    assert evaluator.detect_ast_bypasses(
        "def consume(config):\n"
        "    return load_config_with_fallback(config)\n",
        _tainted_names=("config",),
    ) == ("TOLERANT_OR_COMPATIBILITY_LOADER",)


@pytest.mark.parametrize(
    "callable_name",
    (
        "_FallbackSpectralConv2d",
        "CompatFallbackSpectralConv2d",
        "fallback_payload_projection",
    ),
)
def test_compute_fallback_is_not_a_tolerant_configuration_loader(
    callable_name: str,
) -> None:
    assert evaluator.detect_ast_bypasses(
        "def consume(config):\n"
        f"    return {callable_name}(\n"
        "        config.channels, config.channels, config.modes\n"
        "    )\n",
        _tainted_names=("config",),
    ) == ()


def test_contextual_compute_fallback_is_not_a_tolerant_loader(
    tmp_path: Path,
) -> None:
    path = tmp_path / "package/compute.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "from dependency import _FallbackSpectralConv2d\n"
        "def build(channels, modes):\n"
        "    return _FallbackSpectralConv2d(channels, channels, modes)\n",
        encoding="utf-8",
    )
    context = "@context:package.compute.build:channels,modes"

    _, bypasses, _, _, _ = evaluator._module_functions(
        path,
        "package.compute",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=[{
            "context_symbol": context,
            "public_entry_route": "package.compute.build",
            "tainted_formals": ["channels", "modes"],
        }],
    )

    assert context not in bypasses


@pytest.mark.parametrize(
    ("imported", "expected"),
    (
        ("from package.dataloader import normalize_legacy_grouping_records", ()),
        (
            "from package.runtime import normalize_legacy_loader",
            ("TOLERANT_OR_COMPATIBILITY_LOADER",),
        ),
    ),
)
def test_tolerant_loader_name_uses_the_callable_not_its_module(
    imported: str, expected: tuple[str, ...]
) -> None:
    callable_name = imported.rsplit(" ", 1)[-1]
    source = f"{imported}\ndef consume(config):\n    return {callable_name}(config)\n"

    assert evaluator.detect_ast_bypasses(
        source,
        _tainted_names=("config",),
    ) == expected


def test_strict_compatibility_validation_is_not_a_tolerant_loader() -> None:
    assert evaluator.detect_ast_bypasses(
        "def consume(config):\n"
        "    requirements = DatasetCompatibilityRequirements(config['shape'])\n"
        "    return validate_dataset_compatibility(requirements)\n",
        _tainted_names=("config",),
    ) == ()
    assert evaluator.detect_ast_bypasses(
        "def consume(config):\n"
        "    return compatibility_adapter(config)\n",
        _tainted_names=("config",),
    ) == ("TOLERANT_OR_COMPATIBILITY_LOADER",)


def test_strict_config_loading_names_are_not_tolerant_by_name() -> None:
    assert evaluator.detect_ast_bypasses(
        "def consume(config):\n"
        "    payload = resolve_training_payload(config)\n"
        "    return load_checkpoint_with_configs(payload)\n",
        _tainted_names=("config",),
    ) == ()


def test_resolved_typed_configuration_access_is_not_a_tolerant_loader() -> None:
    assert evaluator.detect_ast_bypasses(
        "def use(model_config: ModelConfig):\n"
        "    return getattr(model_config, 'mode', 'default')\n"
    ) == ()
    assert evaluator.detect_ast_bypasses(
        "def use(model_config: ModelConfig | None):\n"
        "    return getattr(model_config, 'mode', 'default')\n"
    ) == ()
    assert evaluator.detect_ast_bypasses(
        "from typing import Mapping\n"
        "def resolve(config: Mapping[str, object]):\n"
        "    return config.get('mode', 'default')\n",
        _tainted_names=("config",),
    ) == ("TOLERANT_OR_COMPATIBILITY_LOADER",)


@pytest.mark.parametrize("method", ("get", "setdefault"))
def test_mapping_tolerance_depends_on_the_receiver_not_the_default(
    method: str,
) -> None:
    source = (
        "def consume(config, observed):\n"
        f"    return observed.{method}('mode', config.mode)\n"
    )

    assert evaluator.detect_ast_bypasses(
        source,
        _tainted_names=("config",),
    ) == ()
    assert evaluator.detect_ast_bypasses(
        source,
        _tainted_names=("observed",),
    ) == ("TOLERANT_OR_COMPATIBILITY_LOADER",)


def test_mapping_tolerance_follows_a_configuration_receiver_alias() -> None:
    source = (
        "def consume(config):\n"
        "    alias = config\n"
        "    return alias.get('mode', 'safe')\n"
    )

    assert evaluator.detect_ast_bypasses(
        source,
        _tainted_names=("config",),
    ) == ("TOLERANT_OR_COMPATIBILITY_LOADER",)


@pytest.mark.parametrize(
    "source",
    (
        (
            "def consume(runtime_config):\n"
            "    observed = {'mode': 'strict'}\n"
            "    return observed.get('mode', runtime_config.mode)\n"
        ),
        (
            "def read(observed, default):\n"
            "    return observed.get('mode', default)\n"
            "def consume(runtime_config):\n"
            "    return read({'mode': 'strict'}, runtime_config.mode)\n"
        ),
    ),
    ids=("exact", "context"),
)
def test_mapping_default_does_not_create_a_route_bypass(
    tmp_path: Path,
    source: str,
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/mapping_default_consumer.py",
        source,
    )

    assert "TOLERANT_OR_COMPATIBILITY_LOADER" not in result["bypass_classes"]


def test_configuration_mapping_receiver_remains_a_route_bypass(
    tmp_path: Path,
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/config_mapping_consumer.py",
        "def read(config):\n"
        "    return config.get('mode', 'safe')\n"
        "def consume(runtime_config):\n"
        "    return read(runtime_config)\n",
    )

    assert "TOLERANT_OR_COMPATIBILITY_LOADER" in result["bypass_classes"]


def test_legacy_architecture_table_is_not_legacy_configuration_state() -> None:
    assert evaluator.detect_ast_bypasses(
        "MODEL_TO_LEGACY_ARCH['hybrid'] = 'hybrid'\n"
    ) == ()
    assert evaluator.detect_ast_bypasses(
        "def commit(config, params):\n"
        "    params.cfg.update(config)\n",
        _tainted_names=("config",),
    ) == ("LEGACY_CONFIGURATION_STATE_MUTATION",)


def test_bypass_detection_is_config_tainted_and_requires_a_real_legacy_write() -> None:
    source = """
def resolve(config, telemetry, legacy_state):
    telemetry.get("mode", "quiet")
    str("constant")
    current = legacy_state.mode
    return config["mode"]
"""
    assert evaluator.detect_ast_bypasses(
        source, _tainted_names=("config", "legacy_state")
    ) == ()


def test_swallowed_config_fallback_is_a_tolerant_bypass() -> None:
    source = """
def resolve(config):
    try:
        return strict_load(config)
    except (TypeError, ValueError):
        return {}
"""
    assert evaluator.detect_ast_bypasses(source, _tainted_names=("config",)) == (
        "TOLERANT_OR_COMPATIBILITY_LOADER",
    )


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("return os.getenv('MODE')", "AMBIENT_CONFIGURATION_READ"),
        ("return os.environ.get('MODE')", "AMBIENT_CONFIGURATION_READ"),
        ("return os.environ['MODE']", "AMBIENT_CONFIGURATION_READ"),
        ("return config.get('mode', 'safe')", "TOLERANT_OR_COMPATIBILITY_LOADER"),
        ("return str(config['mode'])", "TOLERANT_OR_COMPATIBILITY_LOADER"),
        ("return compatibility_load(config)", "TOLERANT_OR_COMPATIBILITY_LOADER"),
        ("legacy_state['mode'] = config['mode']\nreturn config", "LEGACY_CONFIGURATION_STATE_MUTATION"),
    ],
)
def test_config_tainted_bypass_forms_are_detected(
    statement: str, expected: str
) -> None:
    source = "import os\n\ndef resolve(config, legacy_state):\n    " + statement.replace("\n", "\n    ") + "\n"
    assert expected in evaluator.detect_ast_bypasses(
        source, _tainted_names=("config", "legacy_state")
    )


def test_nested_config_route_reaches_authority_without_external_call_dead_ends(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n"
            "def wrapper(config):\n"
            "    def nested(value):\n"
            "        audit('resolution-started')\n"
            "        return resolve(value, {})\n"
            "    return nested(config)\n"
        ),
    )
    row = {
        "consumer_id": "current-wrapper",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.wrapper",
        "source_span": {"start_line": 6, "start_col": 18, "end_line": 6, "end_col": 24},
        "transitive_wrapper_chain": ["candidate.config.wrapper", "config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )
    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [dict(row, consumer_id="frozen-wrapper")]},
        workspace=workspace,
    )
    assert result["closed"] is True
    assert result["paired_consumer_count"] == 1


def test_cross_module_context_treats_a_non_tolerant_value_method_as_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "helper.py").write_text(
        "def helper(value): return value.as_dict()\n", encoding="utf-8"
    )
    (package / "consumer.py").write_text(
        "from ptycho.helper import helper\n"
        "def consume(runtime_config):\n"
        "    mode = runtime_config.mode\n"
        "    return helper(mode)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "cross-module-context",
        "match_kind": "CONFIGURATION_READ",
        "path": "ptycho/consumer.py",
        "public_entry_route": "ptycho.consumer.consume",
        "source_span": {
            "start_line": 3,
            "start_col": 11,
            "end_line": 3,
            "end_col": 30,
        },
        "transitive_wrapper_chain": ["ptycho.consumer.consume", "runtime_config.mode"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []


def test_declared_authority_is_not_reopened_as_a_tolerant_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return file_mapping\n",
    )
    package = workspace / "ptycho"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "config.py").write_text(
        "def resolve(file_mapping, cli_patch):\n"
        "    return file_mapping.get('mode', 'strict')\n",
        encoding="utf-8",
    )
    evidence = json.loads(evidence_path.read_bytes())
    evidence["public_resolution_routes"] = [
        {
            "roles": ["SIMULATION", "TRAINING", "INFERENCE", "RUNTIME_EXECUTION"],
            "symbol": "ptycho.config.resolve",
        }
    ]
    evidence_path.write_bytes(evaluator.canonical_json_bytes(evidence))
    path = package / "use_authority.py"
    path.write_text(
        "from ptycho.config import resolve\n"
        "def helper(mapping): return resolve(mapping, {})\n"
        "def consume(runtime_config):\n"
        "    mapping = runtime_config.values\n"
        "    return helper(mapping)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "authority-call",
        "match_kind": "CONFIGURATION_READ",
        "path": "ptycho/use_authority.py",
        "public_entry_route": "ptycho.use_authority.consume",
        "source_span": {
            "start_line": 4,
            "start_col": 14,
            "end_line": 4,
            "end_col": 35,
        },
        "transitive_wrapper_chain": [
            "ptycho.use_authority.consume",
            "runtime_config.values",
        ],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []


def test_same_module_declared_authority_is_an_absorbing_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch):\n"
            "    return file_mapping.get('mode', 'strict')\n"
            "def helper(mapping): return resolve(mapping, {})\n"
            "def consume(runtime_config):\n"
            "    mapping = runtime_config.values\n"
            "    return helper(mapping)\n"
        ),
    )
    row = {
        "consumer_id": "authority-call",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.consume",
        "source_span": {
            "start_line": 5,
            "start_col": 14,
            "end_line": 5,
            "end_col": 35,
        },
        "transitive_wrapper_chain": ["candidate.config.consume", "runtime_config.values"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []


def test_cross_module_context_does_not_hide_a_dynamic_receiver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "helper.py").write_text(
        "def helper(adapter, value): return adapter.process(value)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from ptycho.helper import helper\n"
        "def consume(runtime_config, adapter):\n"
        "    mode = runtime_config.mode\n"
        "    return helper(adapter, mode)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "dynamic-receiver",
        "match_kind": "CONFIGURATION_READ",
        "path": "ptycho/consumer.py",
        "public_entry_route": "ptycho.consumer.consume",
        "source_span": {
            "start_line": 3,
            "start_col": 11,
            "end_line": 3,
            "end_col": 30,
        },
        "transitive_wrapper_chain": ["ptycho.consumer.consume", "runtime_config.mode"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is False


def test_dynamic_method_terminal_does_not_leak_between_consumers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "candidate/helper.py"
    path.write_text(
        "def first(value): return value.process()\n"
        "def second(value, config): return value.process(config)\n",
        encoding="utf-8",
    )
    rows = [
        {
            "consumer_id": "safe-receiver",
            "match_kind": "CONFIGURATION_READ",
            "path": "candidate/helper.py",
            "public_entry_route": "candidate.helper.first",
            "source_span": {
                "start_line": 1,
                "start_col": 25,
                "end_line": 1,
                "end_col": 30,
            },
            "transitive_wrapper_chain": ["candidate.helper.first", "value"],
        },
        {
            "consumer_id": "dynamic-receiver",
            "match_kind": "CONFIGURATION_READ",
            "path": "candidate/helper.py",
            "public_entry_route": "candidate.helper.second",
            "source_span": {
                "start_line": 2,
                "start_col": 48,
                "end_line": 2,
                "end_col": 54,
            },
            "transitive_wrapper_chain": ["candidate.helper.second", "config"],
        },
    ]
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": rows},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": rows},
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["unresolved_consumers"] == ["dynamic-receiver"]


def test_consumer_occurrences_reconcile_as_multisets() -> None:
    def row(consumer_id: str, line: int) -> dict[str, Any]:
        return {
            "consumer_id": consumer_id,
            "match_kind": "CONFIGURATION_READ",
            "path": "ptycho/config/example.py",
            "public_entry_route": "ptycho.config.example.consume",
            "source_span": {
                "start_line": line,
                "start_col": 4,
                "end_line": line,
                "end_col": 10,
            },
            "transitive_wrapper_chain": ["ptycho.config.example.consume", "config.mode"],
        }

    result = evaluator.reconcile_consumer_occurrences(
        [row("old-a", 10), row("old-b", 20)],
        [row("current-a", 10)],
    )
    assert result["old_count"] == 2
    assert result["current_count"] == 1
    assert result["paired_count"] == 1
    assert result["removed_count"] == 1
    assert result["added_count"] == 0
    assert result["old_count"] == result["paired_count"] + result["removed_count"]
    assert result["current_count"] == result["paired_count"] + result["added_count"]


def test_fresh_added_consumer_occurrence_is_evaluated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n"
            "def good(config): return resolve(config, {})\n"
            "def added(config): return config.get('mode', 'safe')\n"
        ),
    )

    def row(
        consumer_id: str, route: str, line: int, start_col: int, end_col: int,
        terminal: str,
    ) -> dict[str, Any]:
        return {
            "consumer_id": consumer_id,
            "match_kind": "CONFIGURATION_READ",
            "path": "candidate/config.py",
            "public_entry_route": route,
            "source_span": {
                "start_line": line, "start_col": start_col,
                "end_line": line, "end_col": end_col,
            },
            "transitive_wrapper_chain": [route, terminal],
        }

    old = row("old-good", "candidate.config.good", 2, 33, 39, "config")
    current = [
        row("current-good", "candidate.config.good", 2, 33, 39, "config"),
        row("current-added", "candidate.config.added", 3, 26, 52, "config.get"),
    ]
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": current},
    )
    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [old]},
        workspace=workspace,
    )
    assert result["closed"] is False
    assert result["added_consumer_count"] == 1
    assert result["introduced_consumer_symbols"] == ["candidate.config.added"]
    assert {trace["consumer_id"] for trace in result["traces"]} == {
        "current-good",
        "current-added",
    }
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


def test_accounted_count_includes_paired_added_and_surviving_occurrences(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n"
            "def paired(config):\n"
            "    return config\n"
            "def added(config):\n"
            "    return config\n"
            "def surviving(config):\n"
            "    return config\n"
        ),
    )

    def row(consumer_id: str, route: str, line: int) -> dict[str, Any]:
        return {
            "consumer_id": consumer_id,
            "match_kind": "CONFIGURATION_READ",
            "path": "candidate/config.py",
            "public_entry_route": route,
            "source_span": {
                "start_line": line,
                "start_col": 11,
                "end_line": line,
                "end_col": 17,
            },
            "transitive_wrapper_chain": [route, "config"],
        }

    frozen = [
        row("frozen-paired", "candidate.config.paired", 3),
        row("frozen-surviving", "candidate.config.surviving", 7),
    ]
    current = [
        row("current-paired", "candidate.config.paired", 3),
        row("current-added", "candidate.config.added", 5),
    ]
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": current},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": frozen},
        workspace=workspace,
    )

    assert result["accounted_consumer_count"] == 3
    assert result["paired_consumer_count"] == 1
    assert result["added_consumer_count"] == 1
    assert result["removed_consumer_count"] == 0
    assert {trace["consumer_id"] for trace in result["traces"]} == {
        "current-paired",
        "current-added",
        "frozen-surviving",
    }


def test_stale_construction_span_cannot_force_a_current_nonconstruction_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/consumer.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "def consume(runtime_config):\n"
        "    logger.info('unchanged')\n"
        "    return runtime_config.mode\n"
        "def build(mapping):\n"
        "    return build_config(mapping)\n",
        encoding="utf-8",
    )
    current = evaluator.scan_workspace_configuration_consumers(workspace)["rows"]
    current_construction = next(
        row for row in current
        if row["match_kind"] == "CONFIGURATION_CONSTRUCTION"
        and row["public_entry_route"] == "scripts.consumer.build"
    )
    current_read = next(
        row for row in current
        if row["match_kind"] == "CONFIGURATION_READ"
        and row["public_entry_route"] == "scripts.consumer.consume"
    )
    stale_construction = {
        **current_construction,
        "consumer_id": "stale-construction",
        "public_entry_route": "scripts.consumer.consume",
        "source_span": {
            "start_line": 4,
            "start_col": 4,
            "end_line": 4,
            "end_col": 28,
        },
        "transitive_wrapper_chain": [
            "scripts.consumer.consume",
            "build_config",
        ],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": current},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [current_construction, stale_construction]},
        workspace=workspace,
    )

    traces = {trace["consumer_id"]: trace for trace in result["traces"]}
    assert traces[current_construction["consumer_id"]]["closed"] is False
    assert traces[current_read["consumer_id"]]["closed"] is True
    assert traces["stale-construction"]["closed"] is False
    assert not any(
        symbol == "scripts.consumer.logger.info"
        for route in traces["stale-construction"]["paths"]
        for symbol in route
    )
    assert result["removed_consumer_count"] == 0


def test_accounted_count_counts_occurrences_not_fanout_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "import json\n"
            "def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n"
            "def consume(config):\n"
            "    resolve(config, {})\n"
            "    return json.dumps(config)\n"
        ),
    )
    row = {
        "consumer_id": "fanout",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.consume",
        "transitive_wrapper_chain": ["candidate.config.consume", "config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["accounted_consumer_count"] == 1
    assert result["paired_consumer_count"] == 1
    assert len(result["traces"]) == 1
    assert len(result["traces"][0]["paths"]) == 2


def test_exact_read_occurrence_does_not_inherit_a_sibling_bypass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def consume(runtime_config):\n"
            "    safe = runtime_config.value\n"
            "    return runtime_config.get('mode', 'default')\n"
        ),
    )
    row = {
        "consumer_id": "safe-read",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.consume",
        "source_span": {
            "start_line": 2,
            "start_col": 11,
            "end_line": 2,
            "end_col": 31,
        },
        "transitive_wrapper_chain": [
            "candidate.config.consume",
            "runtime_config.value",
        ],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []


def test_exact_argument_does_not_inherit_a_sibling_coercion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def consume(runtime_config):\n"
            "    return sink(value=runtime_config.value, label=str(runtime_config.label))\n"
        ),
    )
    row = {
        "consumer_id": "exact-argument",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.consume",
        "source_span": {
            "start_line": 2,
            "start_col": 22,
            "end_line": 2,
            "end_col": 42,
        },
        "transitive_wrapper_chain": [
            "candidate.config.consume",
            "runtime_config.value",
        ],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["bypass_classes"] == []


def test_exact_field_bypass_propagates_through_a_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def helper(value):\n"
            "    return value.get('mode', 'default')\n"
            "def consume(runtime_config):\n"
            "    return helper(runtime_config.value)\n"
        ),
    )
    row = {
        "consumer_id": "helper-read",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.consume",
        "source_span": {
            "start_line": 4,
            "start_col": 18,
            "end_line": 4,
            "end_col": 38,
        },
        "transitive_wrapper_chain": [
            "candidate.config.consume",
            "runtime_config.value",
        ],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


def test_exact_field_does_not_inherit_a_sibling_helper_parameter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def helper(value, options):\n"
            "    return options.get('mode', 'default')\n"
            "def consume(value, options):\n"
            "    return helper(value, options)\n"
        ),
    )
    rows = [
        {
            "consumer_id": consumer_id,
            "match_kind": "CONFIGURATION_READ",
            "path": "candidate/config.py",
            "public_entry_route": "candidate.config.consume",
            "source_span": {
                "start_line": 4,
                "start_col": start_col,
                "end_line": 4,
                "end_col": end_col,
            },
            "transitive_wrapper_chain": ["candidate.config.consume", name],
        }
        for consumer_id, name, start_col, end_col in (
            ("safe-value", "value", 18, 23),
            ("tolerant-options", "options", 25, 32),
        )
    ]
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": rows},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": rows},
        workspace=workspace,
    )

    assert result["closed"] is False
    traces = {trace["consumer_id"]: trace for trace in result["traces"]}
    assert traces["safe-value"]["closed"] is True
    assert traces["safe-value"]["bypass_classes"] == []
    assert traces["tolerant-options"]["bypass_classes"] == [
        "TOLERANT_OR_COMPATIBILITY_LOADER"
    ]


def test_exact_field_does_not_inherit_an_unrelated_same_name_receiver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "class adapter:\n"
            "    def read(self, value):\n"
            "        return value.get('mode', 'default')\n"
            "def consume(config, adapter):\n"
            "    return adapter.read(config)\n"
        ),
    )
    row = {
        "consumer_id": "dynamic-reader",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.consume",
        "source_span": {
            "start_line": 5,
            "start_col": 24,
            "end_line": 5,
            "end_col": 30,
        },
        "transitive_wrapper_chain": ["candidate.config.consume", "config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []


def test_exact_construction_inside_authority_routes_to_that_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "class Settings:\n"
            "    def __init__(self, value): self.value = value\n"
            "def resolve(file_mapping, cli_patch):\n"
            "    return Settings(file_mapping)\n"
        ),
    )
    row = {
        "consumer_id": "authority-construction",
        "match_kind": "CONFIGURATION_CONSTRUCTION",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
        "source_span": {
            "start_line": 4,
            "start_col": 11,
            "end_line": 4,
            "end_col": 33,
        },
        "transitive_wrapper_chain": [
            "candidate.config.resolve",
            "candidate.config.Settings",
        ],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["traces"][0]["paths"] == [
        ["@consumer:authority-construction", "candidate.config.resolve"]
    ]


def test_exact_construction_inside_authority_does_not_hide_a_bypass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "class Settings:\n"
            "    def __init__(self, value): self.value = value\n"
            "def resolve(file_mapping, cli_patch):\n"
            "    return Settings(file_mapping.get('settings', {}))\n"
        ),
    )
    row = {
        "consumer_id": "authority-bypass",
        "match_kind": "CONFIGURATION_CONSTRUCTION",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
        "source_span": {
            "start_line": 4,
            "start_col": 11,
            "end_line": 4,
            "end_col": 53,
        },
        "transitive_wrapper_chain": [
            "candidate.config.resolve",
            "candidate.config.Settings",
        ],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


@pytest.mark.parametrize(
    ("expression", "start_col", "end_col"),
    (
        ("runtime_config or {}", 12, 26),
        ("{} or runtime_config", 18, 32),
        ("runtime_config if enabled else {}", 12, 26),
        ("{} if enabled else runtime_config", 31, 45),
    ),
)
def test_exact_carrier_fallback_expression_remains_tainted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expression: str,
    start_col: int,
    end_col: int,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def consume(runtime_config):\n"
            f"    alias = {expression}\n"
            "    return alias.get('mode', 'default')\n"
        ),
    )
    row = {
        "consumer_id": "fallback-carrier",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.consume",
        "source_span": {
            "start_line": 2,
            "start_col": start_col,
            "end_line": 2,
            "end_col": end_col,
        },
        "transitive_wrapper_chain": ["candidate.config.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


@pytest.mark.parametrize(
    "expression",
    (
        "value or {}",
        "value if sibling else {}",
        "{} if sibling else value",
    ),
)
def test_carrier_fallback_returned_from_one_wrapper_remains_tainted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expression: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/wrapped_carrier.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def carry(value, sibling):\n"
        f"    return {expression}\n"
        "def consume(runtime_config, metadata):\n"
        "    alias = carry(runtime_config, metadata)\n"
        "    return sink(alias)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "wrapped-fallback",
        "match_kind": "CONFIGURATION_READ",
        "path": "scripts/wrapped_carrier.py",
        "public_entry_route": "scripts.wrapped_carrier.consume",
        "source_span": {
            "start_line": 4,
            "start_col": 18,
            "end_line": 4,
            "end_col": 32,
        },
        "transitive_wrapper_chain": [
            "scripts.wrapped_carrier.consume",
            "runtime_config",
        ],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["traces"][0]["paths"] == [
        ["@consumer:wrapped-fallback", "scripts.wrapped_carrier.sink"]
    ]


@pytest.mark.parametrize(
    "expression",
    (
        "value * 2",
        "sibling or {}",
        "sibling if value else {}",
    ),
)
def test_wrapper_noncarrier_return_does_not_taint_downstream_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expression: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/wrapped_noncarrier.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def carry(value, sibling):\n"
        f"    return {expression}\n"
        "def consume(runtime_config, metadata):\n"
        "    alias = carry(runtime_config, metadata)\n"
        "    return sink(alias)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "wrapped-noncarrier",
        "match_kind": "CONFIGURATION_READ",
        "path": "scripts/wrapped_noncarrier.py",
        "public_entry_route": "scripts.wrapped_noncarrier.consume",
        "source_span": {
            "start_line": 4,
            "start_col": 18,
            "end_line": 4,
            "end_col": 32,
        },
        "transitive_wrapper_chain": [
            "scripts.wrapped_noncarrier.consume",
            "runtime_config",
        ],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["traces"][0]["paths"] == [["@consumer:wrapped-noncarrier"]]


@pytest.mark.parametrize(
    ("expression", "closed"),
    (
        ("value if metadata else {}", False),
        ("metadata if value else {}", True),
    ),
)
def test_contextual_ifexp_uses_only_result_branches_for_carrier_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expression: str,
    closed: bool,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def helper(value, metadata):\n"
            f"    alias = {expression}\n"
            "    return sink(alias)\n"
            "def consume(runtime_config, metadata):\n"
            "    return helper(runtime_config, metadata)\n"
        ),
    )
    row = {
        "consumer_id": "contextual-ifexp",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.consume",
        "source_span": {
            "start_line": 5,
            "start_col": 18,
            "end_line": 5,
            "end_col": 32,
        },
        "transitive_wrapper_chain": ["candidate.config.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is closed
    assert result["traces"][0]["paths"] == (
        [["@consumer:contextual-ifexp"]]
        if closed
        else [["@consumer:contextual-ifexp", "candidate.config.sink"]]
    )


@pytest.mark.parametrize(
    ("expression", "start_col", "end_col"),
    (
        ("runtime_config * 2", 12, 26),
        ("2 * runtime_config", 16, 30),
        ("1 if runtime_config else 2", 17, 31),
    ),
)
def test_exact_noncarrier_expression_does_not_taint_its_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expression: str,
    start_col: int,
    end_col: int,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def consume(runtime_config):\n"
            f"    alias = {expression}\n"
            "    return alias.get('mode', 'default')\n"
        ),
    )
    row = {
        "consumer_id": "noncarrier-expression",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.consume",
        "source_span": {
            "start_line": 2,
            "start_col": start_col,
            "end_line": 2,
            "end_col": end_col,
        },
        "transitive_wrapper_chain": ["candidate.config.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []


def test_contextual_noncarrier_expression_does_not_taint_its_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def helper(value):\n"
            "    alias = value * 2\n"
            "    return alias.get('mode', 'default')\n"
            "def consume(runtime_config):\n"
            "    return helper(runtime_config)\n"
        ),
    )
    row = {
        "consumer_id": "contextual-noncarrier",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.consume",
        "source_span": {
            "start_line": 5,
            "start_col": 18,
            "end_line": 5,
            "end_col": 32,
        },
        "transitive_wrapper_chain": ["candidate.config.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []


@pytest.mark.parametrize("authority_field", ["passed", "satisfied", "decision"])
def test_candidate_authority_is_rejected_at_any_depth(authority_field: str) -> None:
    claims = _candidate_claims()
    claims["public_resolution_routes"][0][authority_field] = True
    with pytest.raises(ValueError, match="candidate.*authority"):
        evaluator.evaluate_observations(
            candidate_claims=claims,
            evaluator_observations=[
                {
                    "clause_id": clause,
                    "details": "controller observation",
                    "evidence": [DIGEST],
                    "satisfied": True,
                }
                for clause in CLAUSES
            ],
            dispositions={},
            frozen_registry=set(ROLES),
        )


def test_hard_evaluation_v3_normalizes_observations_and_findings() -> None:
    observations = [
        {
            "clause_id": clause,
            "details": "controller observation",
            "evidence": [DIGEST],
            "satisfied": True,
        }
        for clause in CLAUSES
    ]
    observations[-1]["satisfied"] = False
    result = evaluator.evaluate_observations(
        candidate_claims=_candidate_claims(),
        evaluator_observations=observations,
        dispositions={"F1-H10-BYPASS-ORACLE": "PRODUCT_DEFECT"},
        frozen_registry=set(ROLES),
    )
    assert result["schema_version"] == "es-f1-hard-evaluation.v3"
    assert result["candidate_claims_digest"].startswith("sha256:")
    assert [row["clause_id"] for row in result["hard_findings"]] == [
        "F1-H10-BYPASS-ORACLE"
    ]
    assert result["hard_findings"][0]["schema_version"] == "es-f1-hard-finding.v3"


@pytest.mark.parametrize(
    "registry",
    [set(ROLES) - {"INFERENCE"}, set(ROLES) | {"EVALUATION"}],
)
def test_hard_evaluation_rejects_nonexact_role_domain(registry: set[str]) -> None:
    observations = [
        {
            "clause_id": clause,
            "details": "controller observation",
            "evidence": [DIGEST],
            "satisfied": True,
        }
        for clause in CLAUSES
    ]
    with pytest.raises(ValueError, match="role"):
        evaluator.evaluate_observations(
            candidate_claims=_candidate_claims(),
            evaluator_observations=observations,
            dispositions={},
            frozen_registry=registry,
        )


def test_path_only_result_rejects_adapter_authored_authority(tmp_path: Path) -> None:
    workspace = tmp_path / "candidate"
    adapter = workspace / "adapter.py"
    adapter.parent.mkdir()
    adapter.write_text(
        "import json,sys\n"
        "from pathlib import Path\n"
        "p=Path(sys.argv[sys.argv.index('--result')+1])\n"
        "p.write_text(json.dumps({'schema_version':'config_resolution_probe_result.v1','candidate_id':'candidate-a','operation_version':'ptychopinn_public_config_resolution.v1','probe_results':[{'case_id':'strict-precedence','resolved_record_path':'artifact.json'}],'passed':True})+'\\n')\n",
        encoding="utf-8",
    )
    input_root = tmp_path / "inputs"
    candidate_bytes = evaluator.canonical_json_bytes(_candidate_claims())
    _write_canonical(input_root / "es_f1_candidate_evidence.json", _candidate_claims())
    request = _request("sha256:" + hashlib.sha256(candidate_bytes).hexdigest())
    for field in ("file_mapping", "cli_patch"):
        path = input_root / request["probe_cases"][0][field]["path"]
        _write_canonical(path, {})
        request["probe_cases"][0][field]["sha256"] = evaluator.file_sha256(path)
    request_path = input_root / "request.json"
    _write_canonical(request_path, request)
    with pytest.raises(evaluator.EvaluatorError, match="probe result"):
        evaluator.run_config_resolution_adapter(
            adapter_relative_path="adapter.py",
            expected_candidate_id="candidate-a",
            expected_case_ids=("strict-precedence",),
            output_root=tmp_path / "output",
            python_executable=Path(sys.executable),
            request_path=request_path,
            timeout_seconds=30,
            workspace=workspace,
        )


def test_adapter_authored_provenance_is_rejected() -> None:
    payload = {
        "provenance": {"sample_count": "CLI_PATCH"},
        "resolved": {"mode": "strict", "sample_count": 16},
    }
    with pytest.raises(evaluator.EvaluatorError, match="field set"):
        evaluator._load_resolution_artifact_value(payload)


def test_evaluator_derives_provenance_from_raw_resolution_facts() -> None:
    raw = evaluator._load_resolution_artifact_value(
        {"resolved": {"mode": "strict", "sample_count": 16}}
    )
    observed = evaluator._derive_resolution_observation(
        cli_patch={"sample_count": 16},
        file_mapping={"mode": "strict", "sample_count": 8},
        raw=raw,
    )
    assert observed["provenance"] == {
        "mode": "FILE_MAPPING",
        "sample_count": "CLI_PATCH",
    }


def test_evaluator_derives_nested_precedence_without_dropping_file_fields() -> None:
    raw = evaluator._load_resolution_artifact_value(
        {"resolved": {"model": {"N": 128, "generator_output_mode": "amp_phase"}}}
    )
    observed = evaluator._derive_resolution_observation(
        cli_patch={"model": {"N": 128}},
        file_mapping={"model": {"N": 64, "generator_output_mode": "amp_phase"}},
        raw=raw,
    )
    assert observed["precedence_satisfied"] is True
    assert observed["provenance"] == {
        "model.N": "CLI_PATCH",
        "model.generator_output_mode": "FILE_MAPPING",
    }


def test_adapter_calls_candidate_declared_resolver_instead_of_merging(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch):\n"
            "    return {'marker': 'CALLED', **file_mapping, **cli_patch}\n"
        ),
    )
    run = evaluator.execute_empirical_probe(
        candidate_evidence_path=evidence_path,
        cases=[{
            "case_id": "declared-route",
            "cli_patch": {"sample_count": 16},
            "file_mapping": {"mode": "strict", "sample_count": 8},
            "role": "TRAINING",
        }],
        output_root=tmp_path / "probe",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )
    assert run["observations"][0]["resolved"]["marker"] == "CALLED"
    adapter_source = FIXTURE_ADAPTER.read_text(encoding="utf-8")
    assert "{**file_mapping, **cli_patch}" not in adapter_source
    assert "provenance" not in adapter_source and "source_by_field" not in adapter_source


def test_checked_in_adapter_consumes_the_digest_bound_v1_request(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch):\n"
            "    return {'marker': 'CALLED', **file_mapping, **cli_patch}\n"
        ),
    )
    request_root = tmp_path / "request"
    request_root.mkdir()
    evidence_copy = request_root / "es_f1_candidate_evidence.json"
    evidence_copy.write_bytes(evidence_path.read_bytes())
    request = _request(evaluator.file_sha256(evidence_copy))
    row = request["probe_cases"][0]
    values = {
        "file_mapping": {"mode": "strict", "sample_count": 8},
        "cli_patch": {"sample_count": 16},
    }
    for binding_name, value in values.items():
        binding = row[binding_name]
        path = request_root / binding["path"]
        _write_canonical(path, value)
        binding["sha256"] = evaluator.file_sha256(path)
    request_path = request_root / "request.json"
    _write_canonical(request_path, request)

    result = evaluator.run_config_resolution_adapter(
        adapter_relative_path="scripts/es_f1_config_resolution_adapter.py",
        expected_candidate_id="candidate-a",
        expected_case_ids=("strict-precedence",),
        output_root=tmp_path / "output",
        python_executable=Path(sys.executable),
        request_path=request_path,
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["observations"] == [
        {"resolved": {"marker": "CALLED", "mode": "strict", "sample_count": 16}}
    ]


def test_root_evaluation_derives_routes_from_census_and_candidate_ast(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch):\n"
            "    return {**file_mapping, **cli_patch}\n\n"
            "def wrapper(file_mapping, cli_patch):\n"
            "    return resolve(file_mapping, cli_patch)\n"
        ),
    )
    census = {
        "rows": [{
            "consumer_id": "consumer-a",
            "path": "candidate/config.py",
            "public_entry_route": "candidate.config.wrapper",
            "transitive_wrapper_chain": ["candidate.config.wrapper", "candidate.config.resolve"],
        }]
    }
    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )
    assert result["closed"] is True
    (workspace / "candidate/config.py").write_text(
        "def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n"
        "def wrapper(file_mapping, cli_patch): return legacy_load(file_mapping)\n",
        encoding="utf-8",
    )
    assert evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )["closed"] is False


def test_checked_in_frozen_census_projects_every_slot_exactly_once() -> None:
    package = evaluator.load_frozen_evaluator_package(
        calibration_cases_path=CALIBRATION_CASES,
        consumer_census_path=(
            ROOT
            / "docs/plans/evidence/es-f1-large-scope-refreeze/f1v2/"
            "configuration-consumer-census.json"
        ),
        fixture_manifest_path=FIXTURE_MANIFEST,
        reviewer_perspectives_path=EVALUATOR_ROOT / "reviewer-perspectives.json",
        task_profile_path=F1_ROOT / "task-profile.json",
        visible_check_path=F1_ROOT / "task/visible-check-manifest.json",
        visible_contract_path=F1_ROOT / "task/visible-task-contract.json",
    )
    rows = package["consumer_census"]["rows"]
    slots = evaluator.project_frozen_consumer_slots(rows)
    assert len(rows) == len(slots) == 4394
    assert len({slot["consumer_id"] for slot in slots}) == 4394


def test_consumer_inspection_handles_class_methods_retired_paths_and_new_consumers(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch):\n"
            "    return {**file_mapping, **cli_patch}\n\n"
            "class Runner:\n"
            "    def run(self, file_mapping, cli_patch):\n"
            "        return resolve(file_mapping, cli_patch)\n\n"
            "def introduced(file_mapping, cli_patch):\n"
            "    return resolve(file_mapping, cli_patch)\n"
        ),
    )
    census = {
        "rows": [
            {
                "consumer_id": "class-method",
                "path": "candidate/config.py",
                "public_entry_route": "candidate.config.Runner.run",
            },
            {
                "consumer_id": "retired",
                "path": "candidate/deleted.py",
                "public_entry_route": "candidate.deleted.old",
            },
        ]
    }
    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )
    assert result["closed"] is True
    assert result["retired_consumer_ids"] == ["retired"]
    assert "candidate.config.introduced" in result["introduced_consumer_symbols"]
    assert "candidate.config.Runner.run" not in result["introduced_consumer_symbols"]
    assert result["accounted_consumer_count"] == 1
    assert result["paired_consumer_count"] == 1
    assert result["removed_consumer_count"] == 1


def test_consumer_inspection_fails_closed_on_ambiguous_method_resolution(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n"
            "class A:\n"
            "    def run(self, file_mapping, cli_patch): return resolve(file_mapping, cli_patch)\n"
            "class B:\n"
            "    def run(self, file_mapping, cli_patch): return resolve(file_mapping, cli_patch)\n"
        ),
    )
    census = {"rows": [{
        "consumer_id": "ambiguous",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.run",
    }]}
    with pytest.raises(evaluator.EvaluatorError, match="ambiguous"):
        evaluator.inspect_candidate_consumers(
            candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
            consumer_census=census,
            workspace=workspace,
        )


def test_new_resolved_value_reader_is_scanned_without_reentering_authority(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    new_path = workspace / "scripts/new_config_consumer.py"
    new_path.parent.mkdir(exist_ok=True)
    new_path.write_text(
        "def consume(runtime_config):\n    return runtime_config.value\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}
    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )
    assert result["closed"] is True
    assert "scripts.new_config_consumer.consume" in result["introduced_consumer_symbols"]


def test_new_configuration_constructor_must_close_to_authority(tmp_path: Path) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    new_path = workspace / "scripts/new_config_constructor.py"
    new_path.parent.mkdir(exist_ok=True)
    new_path.write_text(
        "def consume(mapping):\n    return build_config(mapping)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}
    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )
    assert result["closed"] is False
    assert "scripts.new_config_constructor.consume" in result["introduced_consumer_symbols"]


def test_module_level_ambient_read_is_not_hidden_by_missing_function_graph(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    new_path = workspace / "scripts/ambient_config.py"
    new_path.parent.mkdir(exist_ok=True)
    new_path.write_text(
        "import os\nVALUE = os.getenv('APP_CONFIG_PATH')\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}
    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )
    assert result["closed"] is False
    assert result["bypass_classes"] == ["AMBIENT_CONFIGURATION_READ"]


@pytest.mark.parametrize(
    "source",
    (
        "from dependency import fetch\n"
        "def consume(runtime_config):\n"
        "    return fetch(runtime_config)\n",
        "def consume(runtime_config):\n"
        "    resolved = runtime_config\n"
        "    return fetch(resolved)\n",
        "import dependency\n"
        "def consume(runtime_config):\n"
        "    return dependency.fetch(runtime_config)\n",
        "def consume(runtime_config):\n"
        "    return fetch(runtime_config)\n",
    ),
)
def test_resolved_value_reader_fails_closed_on_unindexed_helper(
    tmp_path: Path, source: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/new_config_consumer.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(source, encoding="utf-8")
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert "scripts.new_config_consumer.consume" in result["introduced_consumer_symbols"]


def test_module_level_legacy_mutation_taints_module_readers(tmp_path: Path) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/legacy_mutation.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "import legacy_state\n"
        "legacy_state.value = 1\n"
        "def consume(runtime_config):\n"
        "    return runtime_config.value\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["LEGACY_CONFIGURATION_STATE_MUTATION"]


def test_cross_module_tainted_call_qualifies_global_legacy_mutation(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "params.py").write_text(
        "cfg = {}\n"
        "def set(key, value):\n"
        "    cfg[key] = value\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "import ptycho.params as module\n"
        "def consume(runtime_config):\n"
        "    module.set('mode', runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["LEGACY_CONFIGURATION_STATE_MUTATION"]


def test_cross_module_tainted_call_does_not_qualify_a_local_cfg(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "params.py").write_text(
        "cfg = {'unrelated': True}\n"
        "def set(key, value):\n"
        "    cfg = {}\n"
        "    cfg[key] = value\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "import ptycho.params as module\n"
        "def consume(runtime_config):\n"
        "    module.set('mode', runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []


@pytest.mark.parametrize(
    ("declaration", "closed"),
    (("    global cfg\n", False), ("", True)),
)
def test_cross_module_direct_cfg_assignment_respects_global_declaration(
    tmp_path: Path,
    declaration: str,
    closed: bool,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "params.py").write_text(
        "def set(value):\n"
        + declaration
        + "    cfg = value\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "import ptycho.params as module\n"
        "def consume(runtime_config):\n"
        "    module.set(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is closed
    assert result["bypass_classes"] == (
        [] if closed else ["LEGACY_CONFIGURATION_STATE_MUTATION"]
    )


@pytest.mark.parametrize(
    ("declaration", "target", "start_col", "legacy_mutation"),
    (
        ("    global cfg\n", "cfg", 10, True),
        ("", "cfg", 10, False),
        ("", "cfg.value", 16, True),
        ("", "cfg['value']", 19, True),
    ),
    ids=("global-name", "local-name", "attribute", "subscript"),
)
def test_exact_cfg_assignment_classifies_only_qualified_legacy_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    declaration: str,
    target: str,
    start_col: int,
    legacy_mutation: bool,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "params.py").write_text(
        "cfg = {}\n"
        "def consume(runtime_config):\n"
        + declaration
        + f"    {target} = runtime_config\n",
        encoding="utf-8",
    )
    line = 4 if declaration else 3
    row = {
        "consumer_id": f"exact-{target}",
        "match_kind": "CONFIGURATION_READ",
        "path": "ptycho/params.py",
        "public_entry_route": "ptycho.params.consume",
        "source_span": {
            "start_line": line,
            "start_col": start_col,
            "end_line": line,
            "end_col": start_col + len("runtime_config"),
        },
        "transitive_wrapper_chain": ["ptycho.params.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is not legacy_mutation
    assert result["bypass_classes"] == (
        ["LEGACY_CONFIGURATION_STATE_MUTATION"] if legacy_mutation else []
    )
    assert result["traces"][0]["paths"] == [[f"@consumer:exact-{target}"]]


@pytest.mark.parametrize(
    ("declaration", "legacy_mutation"),
    (("    global cfg\n", True), ("", False)),
)
def test_exact_named_expression_classifies_only_a_qualified_global_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    declaration: str,
    legacy_mutation: bool,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "params.py").write_text(
        "cfg = {}\n"
        "def consume(runtime_config):\n"
        + declaration
        + "    return (cfg := runtime_config)\n",
        encoding="utf-8",
    )
    line = 4 if declaration else 3
    row = {
        "consumer_id": "exact-named-expression",
        "match_kind": "CONFIGURATION_READ",
        "path": "ptycho/params.py",
        "public_entry_route": "ptycho.params.consume",
        "source_span": {
            "start_line": line,
            "start_col": 19,
            "end_line": line,
            "end_col": 33,
        },
        "transitive_wrapper_chain": ["ptycho.params.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is not legacy_mutation
    assert result["bypass_classes"] == (
        ["LEGACY_CONFIGURATION_STATE_MUTATION"] if legacy_mutation else []
    )
    assert result["traces"][0]["paths"] == [
        ["@consumer:exact-named-expression"]
    ]


@pytest.mark.parametrize(
    ("declaration", "legacy_mutation"),
    (("    global cfg\n", True), ("", False)),
)
def test_owner_wide_named_expression_respects_global_declaration(
    tmp_path: Path,
    declaration: str,
    legacy_mutation: bool,
) -> None:
    path = tmp_path / "ptycho/params.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "cfg = {}\n"
        "def consume(runtime_config):\n"
        + declaration
        + "    return (cfg := runtime_config)\n",
        encoding="utf-8",
    )

    _, bypasses, _, _, _ = evaluator._module_functions(
        path,
        "ptycho.params",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=[{"public_entry_route": "ptycho.params.consume"}],
    )

    assert (
        "LEGACY_CONFIGURATION_STATE_MUTATION"
        in bypasses.get("ptycho.params.consume", ())
    ) is legacy_mutation


def test_non_configuration_get_is_not_a_tolerant_config_bypass(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/scientific_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def consume(runtime_config, scientific_data):\n"
        "    scale = scientific_data.get('scale', 1)\n"
        "    return runtime_config.value * scale\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []


def test_imported_external_terminal_consumes_a_resolved_value(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/scientific_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "import numpy as np\n"
        "def consume(runtime_config):\n"
        "    return np.squeeze(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True


def test_workspace_dataclass_type_is_a_terminal_for_a_resolved_read(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class LocalRecord:\n"
            "    value: object\n"
            "def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n"
            "def consume(runtime_config): return LocalRecord(runtime_config)\n"
        ),
    )
    row = {
        "consumer_id": "resolved-read",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.consume",
        "source_span": {
            "start_line": 6,
            "start_col": 48,
            "end_line": 6,
            "end_col": 62,
        },
        "transitive_wrapper_chain": ["candidate.config.consume", "runtime_config"],
    }

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is True


def test_plain_builtin_exception_subclass_is_a_terminal(tmp_path: Path) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/plain_exception.py",
        "class ConfigError(ValueError):\n"
        "    'Raised when configuration is invalid.'\n"
        "    pass\n"
        "def consume(runtime_config):\n"
        "    return ConfigError(runtime_config)\n",
    )

    assert result["closed"] is True


def test_cross_module_plain_exception_subclass_is_a_terminal(tmp_path: Path) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    package = workspace / "errors"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "types.py").write_text(
        "class ConfigError(ValueError):\n    pass\n", encoding="utf-8"
    )
    (package / "consumer.py").write_text(
        "from errors.types import ConfigError\n"
        "def consume(runtime_config):\n"
        "    return ConfigError(runtime_config)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "plain-exception",
        "match_kind": "CONFIGURATION_READ",
        "path": "errors/consumer.py",
        "public_entry_route": "errors.consumer.consume",
        "source_span": {
            "start_line": 3,
            "start_col": 23,
            "end_line": 3,
            "end_col": 37,
        },
        "transitive_wrapper_chain": ["errors.consumer.consume", "runtime_config"],
    }

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is True


@pytest.mark.parametrize("kind", ("exception", "dataclass"))
@pytest.mark.parametrize(
    "mutation",
    (
        "{name}.{hook} = sink\n",
        "setattr({name}, '{hook}', sink)\n",
        "Alias = {name}\nAlias.{hook} = sink\n",
        (
            "def mutate():\n"
            "    {name}.{hook} = sink\n"
            "mutate()\n"
        ),
        (
            "def mutate(target):\n"
            "    target.{hook} = sink\n"
            "mutate({name})\n"
        ),
    ),
    ids=("direct", "setattr", "alias", "closure-mutator", "argument-mutator"),
)
def test_cross_module_plain_class_mutation_fails_closed(
    tmp_path: Path, kind: str, mutation: str
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    package = workspace / "records"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    if kind == "exception":
        name, hook = "ConfigError", "__init__"
        definition = "class ConfigError(ValueError):\n    pass\n"
        sink = (
            "def sink(self, payload):\n"
            "    payload.get('mode', 'fallback')\n"
        )
    else:
        name, hook = "ConfigRecord", "__setattr__"
        definition = (
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class ConfigRecord:\n"
            "    value: object\n"
        )
        sink = (
            "def sink(self, name, payload):\n"
            "    payload.get('mode', 'fallback')\n"
        )
    (package / "types.py").write_text(definition, encoding="utf-8")
    source = (
        f"from records.types import {name}\n"
        + sink
        + mutation.format(name=name, hook=hook)
        + "def consume(runtime_config):\n"
        + f"    return {name}(runtime_config)\n"
    )
    (package / "consumer.py").write_text(source, encoding="utf-8")
    consume_line = source.splitlines()[-1]
    start_col = consume_line.index("runtime_config")

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [{
                "consumer_id": f"cross-module-{kind}",
                "match_kind": "CONFIGURATION_READ",
                "path": "records/consumer.py",
                "public_entry_route": "records.consumer.consume",
                "source_span": {
                    "start_line": len(source.splitlines()),
                    "start_col": start_col,
                    "end_line": len(source.splitlines()),
                    "end_col": start_col + len("runtime_config"),
                },
                "transitive_wrapper_chain": [
                    "records.consumer.consume",
                    "runtime_config",
                ],
            }]
        },
        workspace=workspace,
    )

    assert result["closed"] is False


def test_plain_exception_base_shadowed_by_local_alias_fails_closed(
    tmp_path: Path,
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/shadowed_exception.py",
        "class UnsafeBase:\n"
        "    def __init__(self, payload):\n"
        "        payload.get('mode', 'fallback')\n"
        "ValueError = UnsafeBase\n"
        "class ConfigError(ValueError):\n"
        "    pass\n"
        "def consume(runtime_config):\n"
        "    return ConfigError(runtime_config)\n",
    )

    assert result["closed"] is False


def test_plain_exception_base_shadowed_by_workspace_import_fails_closed(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    (workspace / "scripts/custom_errors.py").write_text(
        "class ValueError:\n"
        "    def __init__(self, payload):\n"
        "        payload.get('mode', 'fallback')\n",
        encoding="utf-8",
    )
    (workspace / "scripts/imported_exception.py").write_text(
        "from scripts.custom_errors import ValueError\n"
        "class ConfigError(ValueError):\n"
        "    pass\n"
        "def consume(runtime_config):\n"
        "    return ConfigError(runtime_config)\n",
        encoding="utf-8",
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [
                {
                    "consumer_id": "authority",
                    "path": "candidate/config.py",
                    "public_entry_route": "candidate.config.resolve",
                }
            ]
        },
        workspace=workspace,
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "mutation",
    (
        "ConfigError.__init__ = sink\n",
        "setattr(ConfigError, '__init__', sink)\n",
    ),
    ids=("attribute-assignment", "setattr"),
)
def test_plain_exception_mutated_after_declaration_fails_closed(
    tmp_path: Path, mutation: str
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/mutated_exception.py",
        "class ConfigError(ValueError):\n"
        "    pass\n"
        "def sink(self, payload):\n"
        "    payload.get('mode', 'fallback')\n"
        + mutation
        + "def consume(runtime_config):\n"
        "    return ConfigError(runtime_config)\n",
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "declaration",
    (
        (
            "class ConfigError(ValueError):\n"
            "    def __init__(self, value):\n"
            "        value.get('mode', 'default')\n"
        ),
        (
            "def decorate(cls): return cls\n"
            "@decorate\n"
            "class ConfigError(ValueError):\n"
            "    pass\n"
        ),
        "class ConfigError(ValueError, LookupError):\n    pass\n",
        (
            "class CustomError(Exception):\n"
            "    pass\n"
            "class ConfigError(CustomError):\n"
            "    pass\n"
        ),
        "class ConfigError(ValueError):\n    code = 7\n",
    ),
    ids=("custom-init", "decorated", "multiple-base", "custom-base", "body-logic"),
)
def test_non_plain_exception_subclasses_fail_closed(
    tmp_path: Path, declaration: str
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/custom_exception.py",
        declaration
        + "def consume(runtime_config):\n"
        + "    return ConfigError(runtime_config)\n",
    )

    assert result["closed"] is False


def test_plain_dataclass_allows_regular_methods_properties_and_literal_defaults(
    tmp_path: Path,
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/plain_dataclass.py",
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class LocalRecord:\n"
        "    value: object\n"
        "    enabled: bool = True\n"
        "    label: str = 'strict'\n"
        "    limit: int = 3\n"
        "    optional: object = None\n"
        "    def describe(self):\n"
        "        return self.label\n"
        "    @property\n"
        "    def ready(self):\n"
        "        return self.enabled\n"
        "def consume(runtime_config):\n"
        "    return LocalRecord(runtime_config)\n",
    )

    assert result["closed"] is True


def test_dataclass_decorator_ignores_class_body_binding(tmp_path: Path) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/class_binding_dataclass.py",
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class R:\n"
        "    value: object\n"
        "    dataclass: object = None\n"
        "def consume(runtime_config):\n"
        "    return R(runtime_config)\n",
    )

    assert result["closed"] is True


@pytest.mark.parametrize(
    "field_or_hook",
    (
        "    values: list = []\n",
        "    values: list = field(default_factory=list)\n",
        (
            "    def __init__(self, value):\n"
            "        value.get('mode', 'default')\n"
        ),
    ),
    ids=("mutable-default", "default-factory", "custom-init"),
)
def test_dataclass_nonliteral_defaults_and_hooks_fail_closed(
    tmp_path: Path, field_or_hook: str
) -> None:
    imports = (
        "from dataclasses import dataclass, field\n"
        if "field(" in field_or_hook
        else "from dataclasses import dataclass\n"
    )
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/non_plain_dataclass.py",
        imports
        + "@dataclass\n"
        + "class LocalRecord:\n"
        + "    value: object\n"
        + field_or_hook
        + "def consume(runtime_config):\n"
        + "    return LocalRecord(runtime_config)\n",
    )

    assert result["closed"] is False


def test_same_module_dataclass_field_factory_requires_stable_index(
    tmp_path: Path,
) -> None:
    calls, terminals, closed = _synthetic_owner_route(
        tmp_path,
        module="package.records",
        owner="package.records.consume",
        source=(
            "from builtins import dict\n"
            "from dataclasses import dataclass, field\n"
            "@dataclass\n"
            "class LocalRecord:\n"
            "    value: object\n"
            "    items: dict = field(default_factory=dict)\n"
            "def consume(runtime_config):\n"
            "    return LocalRecord(runtime_config)\n"
        ),
    )

    assert calls == ["package.records.LocalRecord"]
    assert "package.records.LocalRecord" not in terminals
    assert closed is False


@pytest.mark.parametrize(
    "mutation",
    (
        (
            "def sink(self, name, payload):\n"
            "    payload.get('mode', 'fallback')\n"
            "    object.__setattr__(self, name, payload)\n"
            "Alias = LocalRecord\n"
            "Alias.__setattr__ = sink\n"
        ),
        (
            "class Sink:\n"
            "    def __set__(self, instance, payload):\n"
            "        payload.get('mode', 'fallback')\n"
            "        object.__setattr__(instance, '_value', payload)\n"
            "Alias = LocalRecord\n"
            "Alias.value = Sink()\n"
        ),
    ),
    ids=("setattr-alias", "descriptor-alias"),
)
def test_dataclass_mutated_through_class_alias_fails_closed(
    tmp_path: Path, mutation: str
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/aliased_dataclass.py",
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class LocalRecord:\n"
        "    value: object\n"
        + mutation
        + "def consume(runtime_config):\n"
        "    return LocalRecord(runtime_config)\n",
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "declaration",
    (
        (
            "class ConfigError(ValueError):\n"
            "    pass\n"
            "def sink(self, payload):\n"
            "    payload.get('mode', 'fallback')\n"
            "def mutate(target):\n"
            "    target.__init__ = sink\n"
            "mutate(ConfigError)\n"
            "def consume(runtime_config):\n"
            "    return ConfigError(runtime_config)\n"
        ),
        (
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class LocalRecord:\n"
            "    value: object\n"
            "def sink(self, name, payload):\n"
            "    payload.get('mode', 'fallback')\n"
            "def mutate(target):\n"
            "    target.__setattr__ = sink\n"
            "mutate(LocalRecord)\n"
            "def consume(runtime_config):\n"
            "    return LocalRecord(runtime_config)\n"
        ),
    ),
    ids=("exception", "dataclass"),
)
def test_invoked_module_class_mutator_fails_closed(
    tmp_path: Path, declaration: str
) -> None:
    result = _inspect_added_consumer(
        tmp_path, "scripts/invoked_class_mutator.py", declaration
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "declaration",
    (
        (
            "class ConfigError(ValueError):\n"
            "    pass\n"
            "def sink(self, payload):\n"
            "    payload.get('mode', 'fallback')\n"
            "def mutate():\n"
            "    ConfigError.__init__ = sink\n"
            "mutate()\n"
            "def consume(runtime_config):\n"
            "    return ConfigError(runtime_config)\n"
        ),
        (
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class LocalRecord:\n"
            "    value: object\n"
            "def sink(self, name, payload):\n"
            "    payload.get('mode', 'fallback')\n"
            "def mutate():\n"
            "    LocalRecord.__setattr__ = sink\n"
            "mutate()\n"
            "def consume(runtime_config):\n"
            "    return LocalRecord(runtime_config)\n"
        ),
    ),
    ids=("exception", "dataclass"),
)
def test_invoked_closure_class_mutator_fails_closed(
    tmp_path: Path, declaration: str
) -> None:
    result = _inspect_added_consumer(
        tmp_path, "scripts/invoked_closure_class_mutator.py", declaration
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "declaration",
    (
        (
            "class ConfigError(ValueError):\n"
            "    pass\n"
            "def sink(self, payload):\n"
            "    payload.get('mode', 'fallback')\n"
            "Alias, = (ConfigError,)\n"
            "Alias.__init__ = sink\n"
            "def consume(runtime_config):\n"
            "    return ConfigError(runtime_config)\n"
        ),
        (
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class LocalRecord:\n"
            "    value: object\n"
            "def sink(self, name, payload):\n"
            "    payload.get('mode', 'fallback')\n"
            "Alias, = (LocalRecord,)\n"
            "Alias.__setattr__ = sink\n"
            "def consume(runtime_config):\n"
            "    return LocalRecord(runtime_config)\n"
        ),
    ),
    ids=("exception", "dataclass"),
)
def test_unpacked_class_alias_mutation_fails_closed(
    tmp_path: Path, declaration: str
) -> None:
    result = _inspect_added_consumer(
        tmp_path, "scripts/unpacked_class_alias.py", declaration
    )

    assert result["closed"] is False


def test_verified_external_factory_receiver_is_occurrence_terminal(
    tmp_path: Path,
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/logger_consumer.py",
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "def consume(runtime_config):\n"
        "    logger.info(runtime_config.mode)\n",
    )

    assert result["closed"] is True


def test_synthetic_owner_reuses_verified_external_receiver_terminal_proof(
    tmp_path: Path,
) -> None:
    calls, _, closed = _synthetic_owner_route(
        tmp_path,
        module="package.sink",
        owner="package.sink.consume",
        source=(
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            "def consume(runtime_config):\n"
            "    logger.debug('starting')\n"
            "    logger.info(runtime_config)\n"
        ),
        available_external_imports=frozenset({"logging.getLogger"}),
    )

    assert closed is True
    assert calls[0].startswith("@terminal:")


def test_synthetic_owner_keeps_dynamic_receiver_unresolved(
    tmp_path: Path,
) -> None:
    calls, terminals, _ = _synthetic_owner_route(
        tmp_path,
        module="package.sink",
        owner="package.sink.consume",
        source=(
            "def consume(runtime_config, receiver):\n"
            "    receiver.info(runtime_config)\n"
        ),
    )

    assert calls == ["package.sink.receiver.info"]
    assert "package.sink.receiver.info" not in terminals


@pytest.mark.parametrize(
    "mutation",
    (
        "    alias = logger\n"
        "    alias.info = runtime_config.sink\n",
        "    setattr(logger, runtime_config.method_name, runtime_config.sink)\n",
        "    mutate(logger)\n",
        "    logger.__dict__.update({'info': runtime_config.sink})\n",
        "    mutate((alias := logger))\n",
    ),
    ids=(
        "local-alias",
        "dynamic-setattr",
        "argument-escape",
        "callee-receiver",
        "named-expression-escape",
    ),
)
def test_synthetic_owner_mutated_external_receiver_fails_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    calls, terminals, closed = _synthetic_owner_route(
        tmp_path,
        module="package.sink",
        owner="package.sink.consume",
        source=(
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            "def consume(runtime_config, mutate):\n"
            + mutation
            + "    logger.info(runtime_config)\n"
        ),
        available_external_imports=frozenset({"logging.getLogger"}),
    )

    assert closed is False
    assert "package.sink.logger.info" in calls
    assert not any(
        terminal.endswith(":package.sink.logger.info")
        for terminal in terminals
    )


def test_stable_function_local_list_receiver_is_occurrence_terminal(
    tmp_path: Path,
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/local_list_consumer.py",
        "def consume(runtime_config):\n"
        "    output = ['--mode']\n"
        "    output.extend([runtime_config.mode])\n"
        "    return output\n",
    )

    assert result["closed"] is True


@pytest.mark.parametrize(
    ("definition", "operation"),
    (
        ("output = {}", "output.update(runtime_config)"),
        ("output = dict()", "output.update(runtime_config)"),
        ("output = {0}", "output.update(runtime_config)"),
        ("output = set()", "output.update(runtime_config)"),
    ),
    ids=("dict-literal", "dict-call", "set-literal", "set-call"),
)
def test_stable_function_local_builtin_container_is_occurrence_terminal(
    tmp_path: Path,
    definition: str,
    operation: str,
) -> None:
    calls, _, closed = _synthetic_owner_route(
        tmp_path,
        module="package.sink",
        owner="package.sink.consume",
        source=(
            "def consume(runtime_config):\n"
            f"    {definition}\n"
            f"    {operation}\n"
        ),
    )

    assert closed is True
    assert len(calls) == 1
    assert calls[0].startswith("@terminal:")


@pytest.mark.parametrize(
    "source",
    (
        (
            "def consume(runtime_config, output):\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    output = runtime_config.values\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    output = {}\n"
            "    alias = output\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "def retain(value):\n"
            "    return None\n"
            "def consume(runtime_config):\n"
            "    output = {}\n"
            "    retain(output)\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    output = {}\n"
            "    output = runtime_config.values\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    output = {}\n"
            "    del output\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    output = {}\n"
            "    def capture():\n"
            "        return output\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "def consume(runtime_config, mutate):\n"
            "    output = {}\n"
            "    for _ in range(2):\n"
            "        output.update(runtime_config)\n"
            "        mutate(output)\n"
        ),
        (
            "def make_output():\n"
            "    return {}\n"
            "def consume(runtime_config):\n"
            "    output = make_output()\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "def consume(runtime_config, dict):\n"
            "    output = dict()\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "dict = object\n"
            "def consume(runtime_config):\n"
            "    output = dict()\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "def poison():\n"
            "    global dict\n"
            "    dict = object\n"
            "poison()\n"
            "def consume(runtime_config):\n"
            "    output = dict()\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "def poison():\n"
            "    global set\n"
            "    set = object\n"
            "def consume(runtime_config):\n"
            "    poison()\n"
            "    output = set()\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "def poison():\n"
            "    global dict\n"
            "    import collections as dict\n"
            "poison()\n"
            "def consume(runtime_config):\n"
            "    output = dict()\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "def consume(runtime_config, candidate):\n"
            "    match candidate:\n"
            "        case {\"factory\": set}:\n"
            "            pass\n"
            "    output = set()\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "class Poison:\n"
            "    global dict\n"
            "    from collections import Counter as dict\n"
            "def consume(runtime_config):\n"
            "    output = dict()\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "import builtins\n"
            "class Fake:\n"
            "    pass\n"
            "builtins.dict = Fake\n"
            "def consume(runtime_config):\n"
            "    output = dict()\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "import builtins as b\n"
            "class Fake:\n"
            "    pass\n"
            "setattr(b, \"set\", Fake)\n"
            "def consume(runtime_config):\n"
            "    output = set()\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "import builtins\n"
            "class Fake:\n"
            "    pass\n"
            "def poison(value=setattr(builtins, \"dict\", Fake)):\n"
            "    return value\n"
            "def consume(runtime_config):\n"
            "    output = dict()\n"
            "    output.update(runtime_config)\n"
        ),
        (
            "import builtins as b\n"
            "def decorate(value):\n"
            "    return lambda function: function\n"
            "@decorate(b)\n"
            "def poison():\n"
            "    pass\n"
            "def consume(runtime_config):\n"
            "    output = set()\n"
            "    output.update(runtime_config)\n"
        ),
    ),
    ids=(
        "formal",
        "configuration-derived",
        "alias",
        "argument-escape",
        "rebound",
        "deleted",
        "nested-capture",
        "loop-escape",
        "helper-returned",
        "formal-constructor",
        "module-rebound-constructor",
        "module-invoked-global-constructor-poison",
        "owner-invoked-global-constructor-poison",
        "nested-global-import-alias-constructor-poison",
        "match-binder-constructor-poison",
        "class-global-import-alias-constructor-poison",
        "direct-builtins-attribute-constructor-poison",
        "aliased-builtins-setattr-constructor-poison",
        "default-expression-builtins-mutation",
        "decorator-builtins-escape",
    ),
)
def test_unverified_function_local_builtin_container_fails_closed(
    tmp_path: Path,
    source: str,
) -> None:
    calls, terminals, closed = _synthetic_owner_route(
        tmp_path,
        module="package.sink",
        owner="package.sink.consume",
        source=source,
    )

    target = "package.sink.output.update"
    assert closed is False
    assert target in calls
    assert not any(terminal.endswith(f":{target}") for terminal in terminals)


def test_local_container_literal_ignores_rebound_constructor_name(
    tmp_path: Path,
) -> None:
    calls, _, closed = _synthetic_owner_route(
        tmp_path,
        module="package.sink",
        owner="package.sink.consume",
        source=(
            "dict = object\n"
            "def consume(runtime_config):\n"
            "    output = {}\n"
            "    output.update(runtime_config)\n"
        ),
    )

    assert closed is True
    assert len(calls) == 1
    assert calls[0].startswith("@terminal:")


@pytest.mark.parametrize(
    ("poison", "definition"),
    (
        (
            "import builtins\n"
            "class Fake:\n"
            "    pass\n"
            "builtins.dict = Fake\n",
            "output = {}",
        ),
        (
            "import builtins as b\n"
            "class Fake:\n"
            "    pass\n"
            "setattr(b, \"set\", Fake)\n",
            "output = {0}",
        ),
    ),
    ids=("dict", "set"),
)
def test_local_container_literal_ignores_mutated_builtin_object(
    tmp_path: Path,
    poison: str,
    definition: str,
) -> None:
    calls, _, closed = _synthetic_owner_route(
        tmp_path,
        module="package.sink",
        owner="package.sink.consume",
        source=(
            poison
            + "def consume(runtime_config):\n"
            + f"    {definition}\n"
            + "    output.update(runtime_config)\n"
        ),
    )

    assert closed is True
    assert len(calls) == 1
    assert calls[0].startswith("@terminal:")


def test_repeated_local_list_receiver_escape_fails_closed(tmp_path: Path) -> None:
    calls, terminals, closed = _synthetic_owner_route(
        tmp_path,
        module="package.sink",
        owner="package.sink.consume",
        source=(
            "def consume(runtime_config, mutate):\n"
            "    output = []\n"
            "    for _ in range(2):\n"
            "        output.append(runtime_config)\n"
            "        mutate(output)\n"
        ),
    )

    target = "package.sink.output.append"
    assert closed is False
    assert target in calls
    assert not any(terminal.endswith(f":{target}") for terminal in terminals)


def test_stable_initializer_attribute_external_collection_is_terminal(
    tmp_path: Path,
) -> None:
    calls, _, closed = _synthetic_owner_route(
        tmp_path,
        module="package.builder",
        owner="package.builder.Builder.__init__",
        source=(
            "from dependency import Base, Collection\n"
            "class Builder(Base):\n"
            "    def __init__(self, runtime_config):\n"
            "        super().__init__()\n"
            "        self.encoder_blocks = Collection()\n"
            "        self.downsample_layers = Collection()\n"
            "        for block in runtime_config.blocks:\n"
            "            self.encoder_blocks.append(block)\n"
            "            self.downsample_layers.append(block)\n"
        ),
        available_external_imports=frozenset({"dependency.Collection"}),
    )

    assert closed is True
    assert len(calls) == 2
    assert all(call.startswith("@terminal:") for call in calls)


def test_rebound_initializer_attribute_receiver_fails_closed(
    tmp_path: Path,
) -> None:
    _, _, closed = _synthetic_owner_route(
        tmp_path,
        module="package.builder",
        owner="package.builder.Builder.__init__",
        source=(
            "from dependency import Collection\n"
            "class Builder:\n"
            "    def __init__(self, runtime_config):\n"
            "        self.items = Collection()\n"
            "        self.items = runtime_config.items\n"
            "        self.items.append(runtime_config)\n"
        ),
        available_external_imports=frozenset({"dependency.Collection"}),
    )

    assert closed is False


@pytest.mark.parametrize(
    "class_source",
    (
        "class Builder:\n"
        "    def __init__(self, runtime_config):\n"
        "        self.items = Collection()\n"
        "        alias = self\n"
        "        alias.items = runtime_config.items\n"
        "        self.items.append(runtime_config)\n",
        "class Builder:\n"
        "    def __init__(self, runtime_config):\n"
        "        self.items = Collection()\n"
        "        setattr(self, runtime_config.name, runtime_config.items)\n"
        "        self.items.append(runtime_config)\n",
        "class Builder:\n"
        "    def __init__(self, runtime_config):\n"
        "        self.items = Collection()\n"
        "        self.__dict__['items'] = runtime_config.items\n"
        "        self.items.append(runtime_config)\n",
        "class Builder:\n"
        "    @property\n"
        "    def items(self):\n"
        "        return self._dynamic\n"
        "    @items.setter\n"
        "    def items(self, value):\n"
        "        self._discarded = value\n"
        "    def __init__(self, runtime_config):\n"
        "        self._dynamic = runtime_config.items\n"
        "        self.items = Collection()\n"
        "        self.items.append(runtime_config)\n",
        "class Builder:\n"
        "    def reset(self):\n"
        "        self.items = object()\n"
        "    def __init__(self, runtime_config):\n"
        "        self.items = Collection()\n"
        "        self.reset()\n"
        "        self.items.append(runtime_config)\n",
        "class Builder:\n"
        "    def __init__(self, runtime_config):\n"
        "        self.items = Collection()\n"
        "        self.__setattr__('items', runtime_config.items)\n"
        "        self.items.append(runtime_config)\n",
        "class Builder(Base):\n"
        "    def __init__(self, runtime_config):\n"
        "        self.items = Collection()\n"
        "        super().__init__()\n"
        "        self.items.append(runtime_config)\n",
        "class Descriptor:\n"
        "    pass\n"
        "class Builder:\n"
        "    def __init__(self, runtime_config):\n"
        "        self.items = Collection()\n"
        "        self.items.append(runtime_config)\n"
        "Alias = Builder\n"
        "Alias.items = Descriptor()\n",
    ),
    ids=(
        "self-alias",
        "dynamic-setattr",
        "dict-rebind",
        "descriptor",
        "bound-self-call",
        "bound-self-setattr",
        "super-init-after-definition",
        "class-alias-descriptor",
    ),
)
def test_indirect_initializer_attribute_receiver_fails_closed(
    tmp_path: Path,
    class_source: str,
) -> None:
    calls, terminals, closed = _synthetic_owner_route(
        tmp_path,
        module="package.builder",
        owner="package.builder.Builder.__init__",
        source="from dependency import Base, Collection\n" + class_source,
        available_external_imports=frozenset({"dependency.Collection"}),
    )
    target = "package.builder.self.items.append"
    assert closed is False
    assert target in calls
    assert not any(terminal.endswith(f":{target}") for terminal in terminals)


def test_for_target_configuration_reaches_stable_initializer_collection(
    tmp_path: Path,
) -> None:
    calls, _, closed = _synthetic_owner_route(
        tmp_path,
        module="package.builder",
        owner="package.builder.Builder.__init__",
        source=(
            "from dependency import Collection\n"
            "class Builder:\n"
            "    def __init__(self, runtime_config):\n"
            "        self.items = Collection()\n"
            "        for item in runtime_config.items:\n"
            "            self.items.append(item)\n"
        ),
        available_external_imports=frozenset({"dependency.Collection"}),
    )

    assert closed is True
    assert len(calls) == 1
    assert calls[0].startswith("@terminal:")


@pytest.mark.parametrize(
    "source",
    (
        (
            "def consume(runtime_config, output):\n"
            "    output.extend([runtime_config.mode])\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    output = runtime_config.values\n"
            "    output.extend([runtime_config.mode])\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    output = []\n"
            "    alias = output\n"
            "    output.extend([runtime_config.mode])\n"
        ),
        (
            "def retain(value):\n"
            "    return None\n"
            "def consume(runtime_config):\n"
            "    output = []\n"
            "    retain(output)\n"
            "    output.extend([runtime_config.mode])\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    output = []\n"
            "    output = runtime_config.values\n"
            "    output.extend([runtime_config.mode])\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    output = []\n"
            "    del output\n"
            "    output.extend([runtime_config.mode])\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    output = []\n"
            "    def capture():\n"
            "        return output\n"
            "    output.extend([runtime_config.mode])\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    output = []\n"
            "    try:\n"
            "        pass\n"
            "    except ValueError as output:\n"
            "        pass\n"
            "    output.extend([runtime_config.mode])\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    output = []\n"
            "    import pathlib as output\n"
            "    output.extend([runtime_config.mode])\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    output = []\n"
            "    match runtime_config.other:\n"
            "        case {'x': output}:\n"
            "            pass\n"
            "    output.extend([runtime_config.mode])\n"
        ),
    ),
    ids=(
        "formal",
        "configuration-derived",
        "alias",
        "argument-escape",
        "rebound",
        "deleted",
        "nested-capture",
        "except-binder",
        "import-binder",
        "match-binder",
    ),
)
def test_unverified_local_list_receiver_fails_closed(
    tmp_path: Path,
    source: str,
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/unverified_local_list_consumer.py",
        source,
    )

    assert result["closed"] is False


def test_external_factory_accepts_stable_same_module_workspace_class(
    tmp_path: Path,
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/class_factory_consumer.py",
        "from unittest.mock import Mock\n"
        "class Schema:\n"
        "    pass\n"
        "receiver = Mock(Schema)\n"
        "def consume(runtime_config):\n"
        "    return receiver.consume_payload(runtime_config)\n",
    )

    assert result["closed"] is True


def test_external_factory_accepts_uniquely_imported_workspace_class(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    (workspace / "candidate/schema.py").write_text(
        "class Schema:\n"
        "    pass\n",
        encoding="utf-8",
    )
    path = workspace / "scripts/imported_class_factory_consumer.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from candidate.schema import Schema\n"
        "from unittest.mock import Mock\n"
        "receiver = Mock(Schema)\n"
        "def consume(runtime_config):\n"
        "    return receiver.consume_payload(runtime_config)\n",
        encoding="utf-8",
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [
                {
                    "consumer_id": "authority",
                    "path": "candidate/config.py",
                    "public_entry_route": "candidate.config.resolve",
                }
            ]
        },
        workspace=workspace,
    )

    assert result["closed"] is True


def _inspect_imported_class_factory(
    tmp_path: Path, fields_setup: str, fields_call: str
) -> dict[str, Any]:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    (workspace / "candidate/schema.py").write_text(
        "class Schema:\n"
        "    pass\n"
        "class OtherSchema:\n"
        "    pass\n",
        encoding="utf-8",
    )
    path = workspace / "scripts/imported_class_fields_consumer.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from candidate.schema import OtherSchema, Schema\n"
        "from pydantic import TypeAdapter\n"
        + fields_setup
        + f"declared_fields = {fields_call}\n"
        + "receiver = TypeAdapter(Schema)\n"
        "def consume(runtime_config):\n"
        "    return receiver.validate_python(runtime_config)\n",
        encoding="utf-8",
    )
    return evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [
                {
                    "consumer_id": "authority",
                    "path": "candidate/config.py",
                    "public_entry_route": "candidate.config.resolve",
                }
            ]
        },
        workspace=workspace,
    )


def test_external_factory_allows_direct_dataclass_fields_of_imported_class(
    tmp_path: Path,
) -> None:
    result = _inspect_imported_class_factory(
        tmp_path,
        "from dataclasses import fields\n",
        "fields(Schema)",
    )

    assert result["closed"] is True


@pytest.mark.parametrize(
    ("fields_setup", "fields_call"),
    (
        ("import dataclasses\n", "dataclasses.fields(Schema)"),
        ("from dataclasses import fields as inspect_fields\n", "inspect_fields(Schema)"),
        ("def fields(value):\n    return ()\n", "fields(Schema)"),
        ("from dataclasses import fields\nfields = lambda value: ()\n", "fields(Schema)"),
        ("from dataclasses import fields\n", "fields(Schema, ())"),
        ("from dataclasses import fields\n", "fields(class_or_instance=Schema)"),
        ("from dataclasses import fields\n", "fields((OtherSchema, Schema))"),
        ("from dataclasses import fields\nfields.marker = object()\n", "fields(Schema)"),
        ("from dataclasses import fields\nfields_alias = fields\n", "fields(Schema)"),
        (
            "from dataclasses import fields\n"
            "def retain(value):\n"
            "    return None\n"
            "retain(fields)\n",
            "fields(Schema)",
        ),
    ),
    ids=(
        "qualified",
        "aliased-import",
        "custom",
        "rebound",
        "extra-positional",
        "keyword",
        "wrong-class",
        "mutated",
        "aliased-value",
        "escaped",
    ),
)
def test_external_factory_dataclass_fields_exception_fails_closed(
    tmp_path: Path,
    fields_setup: str,
    fields_call: str,
) -> None:
    result = _inspect_imported_class_factory(tmp_path, fields_setup, fields_call)

    assert result["closed"] is False


@pytest.mark.parametrize(
    "schema_source",
    (
        "class Schema:\n    pass\nSchema.marker = object()\n",
        "class Schema:\n    pass\nescaped = Schema\n",
        (
            "class Schema:\n"
            "    pass\n"
            "def retain(value):\n"
            "    return None\n"
            "retain(Schema)\n"
        ),
    ),
    ids=("origin-mutation", "origin-alias", "origin-argument-escape"),
)
def test_imported_workspace_class_origin_must_remain_stable(
    tmp_path: Path,
    schema_source: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    (workspace / "candidate/schema.py").write_text(
        schema_source,
        encoding="utf-8",
    )
    path = workspace / "scripts/unstable_imported_class_consumer.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from candidate.schema import Schema\n"
        "from unittest.mock import Mock\n"
        "receiver = Mock(Schema)\n"
        "def consume(runtime_config):\n"
        "    return receiver.consume_payload(runtime_config)\n",
        encoding="utf-8",
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [
                {
                    "consumer_id": "authority",
                    "path": "candidate/config.py",
                    "public_entry_route": "candidate.config.resolve",
                }
            ]
        },
        workspace=workspace,
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "invocation",
    ("mutate()\n", "indirect = mutate\nindirect()\n"),
    ids=("original-name", "callable-alias"),
)
def test_same_module_factory_class_mutator_must_be_detectably_invoked(
    tmp_path: Path,
    invocation: str,
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/invoked_factory_class_mutator.py",
        "from unittest.mock import Mock\n"
        "class Schema:\n"
        "    pass\n"
        "def mutate():\n"
        "    Schema.marker = object()\n"
        + invocation
        + "receiver = Mock(Schema)\n"
        "def consume(runtime_config):\n"
        "    return receiver.consume_payload(runtime_config)\n",
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "invocation",
    ("mutate()\n", "indirect = mutate\nindirect()\n"),
    ids=("original-name", "callable-alias"),
)
def test_imported_factory_class_mutator_must_be_detectably_invoked(
    tmp_path: Path,
    invocation: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    (workspace / "candidate/schema.py").write_text(
        "class Schema:\n"
        "    pass\n"
        "def mutate():\n"
        "    Schema.marker = object()\n"
        + invocation,
        encoding="utf-8",
    )
    path = workspace / "scripts/imported_invoked_factory_class_mutator.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from candidate.schema import Schema\n"
        "from unittest.mock import Mock\n"
        "receiver = Mock(Schema)\n"
        "def consume(runtime_config):\n"
        "    return receiver.consume_payload(runtime_config)\n",
        encoding="utf-8",
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [
                {
                    "consumer_id": "authority",
                    "path": "candidate/config.py",
                    "public_entry_route": "candidate.config.resolve",
                }
            ]
        },
        workspace=workspace,
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "source",
    (
        (
            "from unittest.mock import Mock\n"
            "class Schema:\n"
            "    pass\n"
            "Schema = object\n"
            "receiver = Mock(Schema)\n"
        ),
        (
            "from unittest.mock import Mock\n"
            "class Schema:\n"
            "    pass\n"
            "del Schema\n"
            "receiver = Mock(Schema)\n"
        ),
        (
            "from candidate.config import resolve as Schema\n"
            "from unittest.mock import Mock\n"
            "class Schema:\n"
            "    pass\n"
            "receiver = Mock(Schema)\n"
        ),
        (
            "if __name__:\n"
            "    from candidate.config import resolve as Schema\n"
            "else:\n"
            "    from candidate.hooks import resolve_surface as Schema\n"
            "from unittest.mock import Mock\n"
            "receiver = Mock(Schema)\n"
        ),
        (
            "from unittest.mock import Mock\n"
            "class Schema:\n"
            "    pass\n"
            "def choose_schema():\n"
            "    return Schema\n"
            "receiver = Mock(choose_schema())\n"
        ),
        (
            "from unittest.mock import Mock\n"
            "runtime_schema = object()\n"
            "receiver = Mock(runtime_schema)\n"
        ),
        (
            "from unavailable_dependency import Factory\n"
            "class Schema:\n"
            "    pass\n"
            "receiver = Factory(Schema)\n"
        ),
        (
            "if __name__:\n"
            "    from unittest.mock import Mock\n"
            "class Schema:\n"
            "    pass\n"
            "receiver = Mock(Schema)\n"
        ),
        (
            "from unittest.mock import Mock\n"
            "class Schema:\n"
            "    pass\n"
            "Schema.marker = object()\n"
            "receiver = Mock(Schema)\n"
        ),
        (
            "from unittest.mock import Mock\n"
            "class Schema:\n"
            "    pass\n"
            "escaped = Schema\n"
            "receiver = Mock(Schema)\n"
        ),
    ),
    ids=(
        "rebound",
        "deleted",
        "shadowed",
        "ambiguous-import",
        "dynamic-call",
        "configuration-derived",
        "unavailable-factory",
        "non-dominating-factory-import",
        "mutated",
        "escaped",
    ),
)
def test_external_factory_workspace_class_argument_must_be_statically_stable(
    tmp_path: Path,
    source: str,
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/unverified_class_factory_consumer.py",
        source
        + "def consume(runtime_config):\n"
        "    return receiver.consume_payload(runtime_config)\n",
    )

    assert result["closed"] is False


def test_reassigned_external_factory_receiver_fails_closed(tmp_path: Path) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/reassigned_factory.py",
        "import logging\n"
        "class Receiver:\n"
        "    def info(self, payload):\n"
        "        payload.get('mode', 'fallback')\n"
        "def replacement(name):\n"
        "    return Receiver()\n"
        "logging.getLogger = replacement\n"
        "logger = logging.getLogger(__name__)\n"
        "def consume(runtime_config):\n"
        "    logger.info(runtime_config)\n",
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "mutation",
    (
        "logger.info = sink\n",
        "setattr(logger, 'info', sink)\n",
    ),
    ids=("attribute-assignment", "setattr"),
)
def test_mutated_external_receiver_method_fails_closed(
    tmp_path: Path, mutation: str
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/mutated_receiver.py",
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "def sink(payload):\n"
        "    payload.get('mode', 'fallback')\n"
        + mutation
        + "def consume(runtime_config):\n"
        "    logger.info(runtime_config)\n",
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "mutation",
    (
        "alias = logger\nalias.info = sink\n",
        "attribute = 'info'\nsetattr(logger, attribute, sink)\n",
        "logging.Logger.info = sink\n",
        "logging_alias = logging\nlogging_alias.getLogger = sink\n",
    ),
    ids=(
        "receiver-alias",
        "dynamic-setattr",
        "receiver-class",
        "module-alias-factory",
    ),
)
def test_indirect_external_receiver_mutation_fails_closed(
    tmp_path: Path, mutation: str
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/indirect_receiver_mutation.py",
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "def sink(payload):\n"
        "    payload.get('mode', 'fallback')\n"
        + mutation
        + "def consume(runtime_config):\n"
        "    logger.info(runtime_config)\n",
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "source",
    (
        (
            "import logging\n"
            "runtime_config = object()\n"
            "logger = logging.getLogger(runtime_config.name)\n"
            "def consume(config):\n"
            "    logger.info(config.mode)\n"
        ),
        (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            "logger = object()\n"
            "def consume(runtime_config):\n"
            "    logger.info(runtime_config.mode)\n"
        ),
        (
            "import logging\n"
            "def make_logger(): return logging.getLogger(__name__)\n"
            "logger = make_logger()\n"
            "def consume(runtime_config):\n"
            "    logger.info(runtime_config.mode)\n"
        ),
        (
            "def consume(runtime_config, logger):\n"
            "    logger.info(runtime_config.mode)\n"
        ),
    ),
    ids=("config-argument", "rebound", "workspace-factory", "dynamic-receiver"),
)
def test_unverified_factory_receivers_fail_closed(
    tmp_path: Path, source: str
) -> None:
    result = _inspect_added_consumer(
        tmp_path, "scripts/unverified_receiver.py", source
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "record_source",
    [
        (
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class LocalRecord:\n"
            "    value: object\n"
            "    def __new__(cls, value):\n"
            "        value.get('mode', 'default')\n"
            "        return super().__new__(cls)\n"
        ),
        (
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class LocalRecord:\n"
            "    value: object\n"
            "    def __setattr__(self, name, value):\n"
            "        value.get('mode', 'default')\n"
            "        object.__setattr__(self, name, value)\n"
        ),
        (
            "from dataclasses import dataclass\n"
            "class Base:\n"
            "    def __post_init__(self):\n"
            "        self.value.get('mode', 'default')\n"
            "@dataclass\n"
            "class LocalRecord(Base):\n"
            "    value: object\n"
        ),
        (
            "from dataclasses import dataclass\n"
            "class Base:\n"
            "    def __init__(self, value):\n"
            "        value.get('mode', 'default')\n"
            "@dataclass(init=False)\n"
            "class LocalRecord(Base):\n"
            "    value: object\n"
        ),
        (
            "from dataclasses import dataclass\n"
            "def wrapped(cls):\n"
            "    def build(value):\n"
            "        value.get('mode', 'default')\n"
            "        return cls(value)\n"
            "    return build\n"
            "@wrapped\n"
            "@dataclass\n"
            "class LocalRecord:\n"
            "    value: object\n"
        ),
        (
            "from dataclasses import dataclass\n"
            "class Sink:\n"
            "    def __set_name__(self, owner, name): self.name = '_' + name\n"
            "    def __get__(self, instance, owner): return getattr(instance, self.name)\n"
            "    def __set__(self, instance, value):\n"
            "        value.get('mode', 'default')\n"
            "        setattr(instance, self.name, value)\n"
            "@dataclass\n"
            "class LocalRecord:\n"
            "    value: object = Sink()\n"
        ),
        (
            "from dataclasses import dataclass\n"
            "class Sink:\n"
            "    def __set_name__(self, owner, name): self.name = '_' + name\n"
            "    def __get__(self, instance, owner): return getattr(instance, self.name)\n"
            "    def __set__(self, instance, value):\n"
            "        value.get('mode', 'default')\n"
            "        setattr(instance, self.name, value)\n"
            "@dataclass\n"
            "class LocalRecord:\n"
            "    value: object\n"
            "    value = Sink()\n"
        ),
        (
            "from dataclasses import dataclass\n"
            "class Sink:\n"
            "    def __set_name__(self, owner, name): self.name = '_' + name\n"
            "    def __get__(self, instance, owner): return getattr(instance, self.name)\n"
            "    def __set__(self, instance, value):\n"
            "        value.get('mode', 'default')\n"
            "        setattr(instance, self.name, value)\n"
            "@dataclass\n"
            "class LocalRecord:\n"
            "    value: object\n"
            "LocalRecord.value = Sink()\n"
        ),
        (
            "from dataclasses import dataclass\n"
            "class Sink:\n"
            "    def __set_name__(self, owner, name): self.name = '_' + name\n"
            "    def __get__(self, instance, owner): return getattr(instance, self.name)\n"
            "    def __set__(self, instance, value):\n"
            "        value.get('mode', 'default')\n"
            "        setattr(instance, self.name, value)\n"
            "@dataclass\n"
            "class LocalRecord:\n"
            "    value: object\n"
            "if True:\n"
            "    setattr(LocalRecord, 'value', Sink())\n"
        ),
    ],
    ids=(
        "new",
        "setattr",
        "inherited-post-init",
        "init-false",
        "wrapper",
        "descriptor-default",
        "descriptor-rebind",
        "descriptor-post-definition-rebind",
        "descriptor-conditional-setattr",
    ),
)
def test_workspace_dataclass_construction_hooks_are_not_terminals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_source: str,
) -> None:
    source = (
        record_source
        + "def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n"
        + "def consume(runtime_config): return LocalRecord(runtime_config)\n"
    )
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=source,
    )
    consume_line = source.splitlines()[-1]
    start_col = consume_line.rindex("runtime_config")
    row = {
        "consumer_id": "resolved-read",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.consume",
        "source_span": {
            "start_line": len(source.splitlines()),
            "start_col": start_col,
            "end_line": len(source.splitlines()),
            "end_col": start_col + len("runtime_config"),
        },
        "transitive_wrapper_chain": ["candidate.config.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is False


def test_cross_module_generated_dataclass_traces_strict_post_init(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    (workspace / "scripts/strict_record.py").write_text(
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\n"
        "class StrictRecord:\n"
        "    value: str\n"
        "    notices: tuple[str, ...] = ()\n"
        "    def __post_init__(self):\n"
        "        if self.value.strip() != self.value:\n"
        "            raise ValueError('value must already be normalized')\n",
        encoding="utf-8",
    )
    (workspace / "scripts/strict_consumer.py").write_text(
        "from scripts.strict_record import StrictRecord\n"
        "def consume(runtime_config):\n"
        "    return StrictRecord(runtime_config)\n",
        encoding="utf-8",
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [{
                "consumer_id": "authority",
                "path": "candidate/config.py",
                "public_entry_route": "candidate.config.resolve",
            }]
        },
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []
    assert any(
        "@context:scripts.strict_record.StrictRecord:self" in path
        for trace in result["traces"]
        for path in trace["paths"]
    )


def _inspect_cross_module_resolved_records(
    tmp_path: Path, record_source: str
) -> dict[str, Any]:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    (workspace / "scripts/resolved_records.py").write_text(
        record_source,
        encoding="utf-8",
    )
    (workspace / "scripts/resolved_records_consumer.py").write_text(
        "from scripts.resolved_records import ResolvedRecords\n"
        "def consume(runtime_config):\n"
        "    return ResolvedRecords(runtime_config)\n",
        encoding="utf-8",
    )
    return evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [{
                "consumer_id": "authority",
                "path": "candidate/config.py",
                "public_entry_route": "candidate.config.resolve",
            }]
        },
        workspace=workspace,
    )


@pytest.mark.parametrize(
    ("imports", "decorator", "field_name"),
    (
        ("from dataclasses import dataclass, field\n", "@dataclass\n", "field"),
        ("import dataclasses as dc\n", "@dc.dataclass\n", "dc.field"),
    ),
    ids=("direct-alias", "module-alias"),
)
def test_cross_module_generated_dataclass_allows_stable_dict_factory(
    tmp_path: Path,
    imports: str,
    decorator: str,
    field_name: str,
) -> None:
    result = _inspect_cross_module_resolved_records(
        tmp_path,
        imports
        + decorator
        + "class ResolvedRecords:\n"
        + "    primary: object\n"
        + f"    by_name: dict[str, object] = {field_name}(default_factory=dict)\n",
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []
    assert result["traces"][0]["paths"][-1][-1] == (
        "scripts.resolved_records.ResolvedRecords"
    )


def test_cross_module_generated_dataclass_dict_factory_traces_strict_post_init(
    tmp_path: Path,
) -> None:
    result = _inspect_cross_module_resolved_records(
        tmp_path,
        "from dataclasses import dataclass, field\n"
        "@dataclass(frozen=True)\n"
        "class ResolvedRecords:\n"
        "    primary: str\n"
        "    by_name: dict[str, object] = field(default_factory=dict)\n"
        "    def __post_init__(self):\n"
        "        if self.primary.strip() != self.primary:\n"
        "            raise ValueError('primary must already be normalized')\n",
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []
    assert any(
        "@context:scripts.resolved_records.ResolvedRecords:self" in path
        for trace in result["traces"]
        for path in trace["paths"]
    )


@pytest.mark.parametrize(
    ("setup", "default_expression", "tail"),
    (
        ("", "field(default_factory=list)", ""),
        (
            "def make_records():\n"
            "    return {}\n",
            "field(default_factory=make_records)",
            "",
        ),
        (
            "def make_records():\n"
            "    return {}\n"
            "dict = make_records\n",
            "field(default_factory=dict)",
            "",
        ),
        (
            "def make_records():\n"
            "    return {}\n",
            "field(default_factory=dict)",
            "dict = make_records\n",
        ),
        (
            "import builtins\n"
            "class FakeDict:\n"
            "    pass\n"
            "builtins.dict = FakeDict\n",
            "field(default_factory=dict)",
            "",
        ),
        ("field.marker = object()\n", "field(default_factory=dict)", ""),
        (
            "def capture(value):\n"
            "    return value\n"
            "capture(field)\n",
            "field(default_factory=dict)",
            "",
        ),
        ("", "field(default_factory=dict, repr=False)", ""),
        ("", "field(dict)", ""),
        ("", "field(default_factory=dict, **{})", ""),
        ("Factory = dict\n", "field(default_factory=Factory)", ""),
        ("", "field(default_factory=dict())", ""),
        ("import builtins\n", "field(default_factory=builtins.dict)", ""),
        ("", "(field(default_factory=dict),)", ""),
        ("", "((field(default_factory=dict),),)", ""),
    ),
    ids=(
        "list-factory",
        "custom-factory",
        "shadowed-dict",
        "rebound-dict",
        "mutated-builtins-dict",
        "mutated-field-alias",
        "escaped-field-alias",
        "extra-keyword",
        "positional-argument",
        "kwargs",
        "aliased-factory",
        "called-factory",
        "qualified-factory",
        "tuple-field",
        "nested-tuple-field",
    ),
)
def test_cross_module_generated_dataclass_dict_factory_hazards_fail_closed(
    tmp_path: Path,
    setup: str,
    default_expression: str,
    tail: str,
) -> None:
    result = _inspect_cross_module_resolved_records(
        tmp_path,
        "from dataclasses import dataclass, field\n"
        + setup
        + "@dataclass\n"
        + "class ResolvedRecords:\n"
        + "    primary: object\n"
        + f"    by_name: dict[str, object] = {default_expression}\n"
        + tail,
    )

    assert result["closed"] is False
    assert result["unresolved_consumers"]
    assert any(
        "@unresolved-context:scripts.resolved_records.ResolvedRecords" in path
        for trace in result["traces"]
        for path in trace["paths"]
    )


@pytest.mark.parametrize(
    ("imports", "decorator", "field_name", "before", "after"),
    (
        (
            "from dataclasses import dataclass, field\n",
            "@dataclass\n",
            "field",
            "    dict: object = None\n",
            "",
        ),
        (
            "from dataclasses import dataclass, field\n",
            "@dataclass\n",
            "field",
            "",
            "    field: object = None\n",
        ),
        (
            "import dataclasses as dc\n",
            "@dc.dataclass\n",
            "dc.field",
            "",
            "    dc: object = None\n",
        ),
    ),
    ids=("bare-dict", "direct-field-alias", "dataclasses-module-alias"),
)
def test_cross_module_generated_dataclass_class_bindings_fail_closed(
    tmp_path: Path,
    imports: str,
    decorator: str,
    field_name: str,
    before: str,
    after: str,
) -> None:
    result = _inspect_cross_module_resolved_records(
        tmp_path,
        imports
        + decorator
        + "class ResolvedRecords:\n"
        + "    primary: object\n"
        + before
        + f"    by_name: dict[str, object] = {field_name}(default_factory=dict)\n"
        + after,
    )

    assert result["closed"] is False
    assert result["unresolved_consumers"]


@pytest.mark.parametrize(
    "default_expression",
    ("([],)", "(factory(),)"),
    ids=("mutable-element", "call-element"),
)
def test_cross_module_generated_dataclass_tuple_default_hazards_fail_closed(
    tmp_path: Path,
    default_expression: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    (workspace / "scripts/tuple_default_hazard_record.py").write_text(
        "from dataclasses import dataclass\n"
        "def factory():\n"
        "    return ()\n"
        "@dataclass(frozen=True)\n"
        "class Record:\n"
        "    value: str\n"
        f"    notices: tuple[object, ...] = {default_expression}\n"
        "    def __post_init__(self):\n"
        "        if self.value.strip() != self.value:\n"
        "            raise ValueError('value must already be normalized')\n",
        encoding="utf-8",
    )
    (workspace / "scripts/tuple_default_hazard_consumer.py").write_text(
        "from scripts.tuple_default_hazard_record import Record\n"
        "def consume(runtime_config):\n"
        "    return Record(runtime_config)\n",
        encoding="utf-8",
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [{
                "consumer_id": "authority",
                "path": "candidate/config.py",
                "public_entry_route": "candidate.config.resolve",
            }]
        },
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["unresolved_consumers"]
    assert any(
        "@unresolved-context:scripts.tuple_default_hazard_record.Record" in path
        for trace in result["traces"]
        for path in trace["paths"]
    )


def test_cross_module_generated_dataclass_post_init_tolerant_read_fails_closed(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    (workspace / "scripts/tolerant_record.py").write_text(
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class TolerantRecord:\n"
        "    value: object\n"
        "    def __post_init__(self):\n"
        "        self.value.get('mode', 'default')\n",
        encoding="utf-8",
    )
    (workspace / "scripts/tolerant_consumer.py").write_text(
        "from scripts.tolerant_record import TolerantRecord\n"
        "def consume(runtime_config):\n"
        "    return TolerantRecord(runtime_config)\n",
        encoding="utf-8",
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [{
                "consumer_id": "authority",
                "path": "candidate/config.py",
                "public_entry_route": "candidate.config.resolve",
            }]
        },
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


@pytest.mark.parametrize(
    "hazard",
    (
        (
            "    def __new__(cls, value):\n"
            "        return super().__new__(cls)\n"
        ),
        (
            "    def __setattr__(self, name, value):\n"
            "        object.__setattr__(self, name, value)\n"
        ),
        "Record.value = property(lambda self: self._value)\n",
        "Record = dataclass(Record)\n",
    ),
    ids=("custom-new", "custom-setattr", "descriptor", "class-rebound"),
)
def test_cross_module_generated_dataclass_post_init_hazards_fail_closed(
    tmp_path: Path,
    hazard: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    (workspace / "scripts/hazard_record.py").write_text(
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Record:\n"
        "    value: object\n"
        "    def __post_init__(self):\n"
        "        self.value.strip()\n"
        + hazard,
        encoding="utf-8",
    )
    (workspace / "scripts/hazard_consumer.py").write_text(
        "from scripts.hazard_record import Record\n"
        "def consume(runtime_config):\n"
        "    return Record(runtime_config)\n",
        encoding="utf-8",
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [{
                "consumer_id": "authority",
                "path": "candidate/config.py",
                "public_entry_route": "candidate.config.resolve",
            }]
        },
        workspace=workspace,
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "decorator_setup",
    (
        (
            "import dataclasses\n"
            "def mutate():\n"
            "    dataclasses.dataclass = lambda cls: cls\n"
            "@dataclasses.dataclass\n"
        ),
        (
            "import dataclasses\n"
            "def escape():\n"
            "    sink(dataclasses.dataclass)\n"
            "@dataclasses.dataclass\n"
        ),
        (
            "from dataclasses import dataclass\n"
            "from dataclasses import dataclass as alternate\n"
            "def escape():\n"
            "    sink(alternate)\n"
            "@dataclass\n"
        ),
    ),
    ids=("attribute-mutation", "direct-escape", "duplicate-alias-escape"),
)
def test_generated_dataclass_post_init_decorator_hazards_fail_closed(
    tmp_path: Path,
    decorator_setup: str,
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/decorator_hazard.py",
        decorator_setup
        + "class Record:\n"
        "    value: object\n"
        "    def __post_init__(self):\n"
        "        self.value.strip()\n"
        "def consume(runtime_config):\n"
        "    return Record(runtime_config)\n",
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "alias_hazard",
    (
        "def mutate():\n    Alias.value = property(lambda self: None)\n",
        "def escape():\n    sink(Alias)\n",
    ),
    ids=("mutation", "escape"),
)
def test_generated_dataclass_post_init_duplicate_import_alias_hazards_fail_closed(
    tmp_path: Path,
    alias_hazard: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    (workspace / "scripts/aliased_record.py").write_text(
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Record:\n"
        "    value: object\n"
        "    def __post_init__(self):\n"
        "        self.value.strip()\n",
        encoding="utf-8",
    )
    (workspace / "scripts/aliased_consumer.py").write_text(
        "from scripts.aliased_record import Record\n"
        "from scripts.aliased_record import Record as Alias\n"
        + alias_hazard
        + "def consume(runtime_config):\n"
        "    return Record(runtime_config)\n",
        encoding="utf-8",
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [{
                "consumer_id": "authority",
                "path": "candidate/config.py",
                "public_entry_route": "candidate.config.resolve",
            }]
        },
        workspace=workspace,
    )

    assert result["closed"] is False


def test_generated_dataclass_post_init_qualified_decorator_alias_mutation_fails_closed(
    tmp_path: Path,
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/qualified_decorator_alias.py",
        "import dataclasses as decorators\n"
        "from dataclasses import dataclass as direct_decorator\n"
        "def mutate():\n"
        "    direct_decorator.marker = True\n"
        "@decorators.dataclass\n"
        "class Record:\n"
        "    value: object\n"
        "    def __post_init__(self):\n"
        "        self.value.strip()\n"
        "def consume(runtime_config):\n"
        "    return Record(runtime_config)\n",
    )

    assert result["closed"] is False


def test_generated_dataclass_post_init_qualified_class_alias_escape_fails_closed(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    (workspace / "scripts/qualified_record.py").write_text(
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Record:\n"
        "    value: object\n"
        "    def __post_init__(self):\n"
        "        self.value.strip()\n",
        encoding="utf-8",
    )
    (workspace / "scripts/qualified_consumer.py").write_text(
        "import scripts.qualified_record as records\n"
        "from scripts.qualified_record import Record\n"
        "def escape():\n"
        "    sink(records.Record)\n"
        "def consume(runtime_config):\n"
        "    return Record(runtime_config)\n",
        encoding="utf-8",
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={
            "rows": [{
                "consumer_id": "authority",
                "path": "candidate/config.py",
                "public_entry_route": "candidate.config.resolve",
            }]
        },
        workspace=workspace,
    )

    assert result["closed"] is False


def test_generated_dataclass_post_init_ambiguous_direct_module_alias_fails_closed(
    tmp_path: Path,
) -> None:
    result = _inspect_added_consumer(
        tmp_path,
        "scripts/ambiguous_decorator_alias.py",
        "import dataclasses as decorators\n"
        "from dataclasses import dataclass as ambiguous\n"
        "from dependency import decorator as ambiguous\n"
        "@decorators.dataclass\n"
        "class Record:\n"
        "    value: object\n"
        "    def __post_init__(self):\n"
        "        self.value.strip()\n"
        "def consume(runtime_config):\n"
        "    return Record(runtime_config)\n",
    )

    assert result["closed"] is False


def test_workspace_dataclass_descriptor_is_caught_by_the_real_scanner(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "ptycho/consumer.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "from dataclasses import dataclass\n"
        "class Sink:\n"
        "    def __set_name__(self, owner, name): self.name = '_' + name\n"
        "    def __get__(self, instance, owner): return getattr(instance, self.name)\n"
        "    def __set__(self, instance, runtime_config):\n"
        "        runtime_config.get('mode', 'default')\n"
        "        setattr(instance, self.name, runtime_config)\n"
        "@dataclass\n"
        "class LocalRecord:\n"
        "    value: object\n"
        "if True:\n"
        "    setattr(LocalRecord, 'value', Sink())\n"
        "def consume(runtime_config): return LocalRecord(runtime_config)\n",
        encoding="utf-8",
    )
    census = evaluator.scan_workspace_configuration_consumers(workspace)

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


def test_class_decorator_call_and_argument_get_exact_external_routes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ptycho/config.py"
    path.parent.mkdir()
    path.write_text(
        "from pydantic import with_config\n"
        "_DATACLASS_ADAPTER_CONFIG = {}\n"
        "@with_config(_DATACLASS_ADAPTER_CONFIG)\n"
        "class ExampleConfig:\n"
        "    pass\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]

    graph, _, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.config",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"pydantic.with_config"}),
    )

    assert len(rows) == 2
    assert {
        row["transitive_wrapper_chain"][-1] for row in rows
    } == {"with_config", "_DATACLASS_ADAPTER_CONFIG"}
    assert {
        f"@consumer:{row['consumer_id']}": graph.get(
            f"@consumer:{row['consumer_id']}"
        )
        for row in rows
    } == {
        f"@consumer:{row['consumer_id']}": ["pydantic.with_config"]
        for row in rows
    }
    assert "pydantic.with_config" in terminals


def test_class_decorator_nested_get_is_not_erased_by_outer_terminal(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ptycho/config.py"
    path.parent.mkdir()
    path.write_text(
        "from pydantic import with_config\n"
        "_CONFIG = {}\n"
        "@with_config(_CONFIG.get('adapter', {}))\n"
        "class ExampleConfig:\n"
        "    pass\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]

    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.config",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"pydantic.with_config"}),
    )

    consumers = {f"@consumer:{row['consumer_id']}" for row in rows}
    assert len(consumers) == 2
    assert all("ptycho.config._CONFIG.get" in graph[symbol] for symbol in consumers)
    assert all(
        bypasses[symbol] == ("TOLERANT_OR_COMPATIBILITY_LOADER",)
        for symbol in consumers
    )
    result = evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": row["consumer_id"],
            "entry_symbol": f"@consumer:{row['consumer_id']}",
            "requires_authority": False,
        } for row in rows],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )
    assert result["closed"] is False


@pytest.mark.parametrize(
    ("adapter_body", "closed"),
    (
        ("return value.get('adapter', {})", False),
        ("return value", True),
    ),
)
def test_class_decorator_argument_uses_local_adapter_context(
    tmp_path: Path,
    adapter_body: str,
    closed: bool,
) -> None:
    path = tmp_path / "ptycho/config.py"
    path.parent.mkdir()
    path.write_text(
        "from pydantic import with_config\n"
        "_CONFIG = {}\n"
        "def adapt(value):\n"
        f"    {adapter_body}\n"
        "@with_config(adapt(_CONFIG))\n"
        "class ExampleConfig:\n"
        "    pass\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.config",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"pydantic.with_config"}),
    )

    consumers = {f"@consumer:{row['consumer_id']}" for row in rows}
    assert len(consumers) == 2
    assert all("pydantic.with_config" in graph[symbol] for symbol in consumers)
    if closed:
        assert all(graph[symbol] == ["pydantic.with_config"] for symbol in consumers)
        assert all(symbol not in bypasses for symbol in consumers)
    else:
        assert all("ptycho.config.value.get" in graph[symbol] for symbol in consumers)
        assert all(
            bypasses[symbol] == ("TOLERANT_OR_COMPATIBILITY_LOADER",)
            for symbol in consumers
        )
    result = evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": row["consumer_id"],
            "entry_symbol": f"@consumer:{row['consumer_id']}",
            "requires_authority": False,
        } for row in rows],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )
    assert result["closed"] is closed


@pytest.mark.parametrize(
    "wrappers",
    (
        "def adapt(value):\n"
        "    return helper(value)\n",
        "def adapt(value):\n"
        "    return wrapper(value)\n"
        "def wrapper(value):\n"
        "    return helper(value)\n",
    ),
    ids=("one-wrapper", "two-wrappers"),
)
def test_decorator_wrapper_context_preserves_source_time_module_binding(
    tmp_path: Path,
    wrappers: str,
) -> None:
    path = tmp_path / "ptycho/config.py"
    path.parent.mkdir()
    path.write_text(
        "from dependency import compatibility_load as helper\n"
        "from pydantic import with_config\n"
        "_CONFIG = {}\n"
        + wrappers
        + "@with_config(adapt(_CONFIG))\n"
        "class ExampleConfig:\n"
        "    pass\n"
        "def helper(value):\n"
        "    return value\n"
        "def consume(runtime_config):\n"
        "    return adapt(runtime_config)\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, _, _ = evaluator._module_functions(
        path,
        "ptycho.config",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"pydantic.with_config"}),
    )
    class_consumers = {
        f"@consumer:{row['consumer_id']}"
        for row in rows
        if row["public_entry_route"] == "ptycho.config.ExampleConfig"
    }
    runtime_consumer = next(
        f"@consumer:{row['consumer_id']}"
        for row in rows
        if row["public_entry_route"] == "ptycho.config.consume"
    )

    assert all(
        "dependency.compatibility_load" in graph[consumer]
        and bypasses[consumer] == ("TOLERANT_OR_COMPATIBILITY_LOADER",)
        for consumer in class_consumers
    )
    assert graph[runtime_consumer] == []
    assert runtime_consumer not in bypasses


@pytest.mark.parametrize(
    "mutation",
    ("helper = lambda value: value\n", "del helper\n"),
)
def test_decorator_wrapper_context_ignores_later_dynamic_module_binding(
    tmp_path: Path,
    mutation: str,
) -> None:
    path = tmp_path / "ptycho/config.py"
    path.parent.mkdir()
    path.write_text(
        "from dependency import compatibility_load as helper\n"
        "from pydantic import with_config\n"
        "_CONFIG = {}\n"
        "def adapt(value):\n"
        "    return helper(value)\n"
        "@with_config(adapt(_CONFIG))\n"
        "class ExampleConfig:\n"
        "    pass\n"
        + mutation
        + "def consume(runtime_config):\n"
        "    return adapt(runtime_config)\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, _, _ = evaluator._module_functions(
        path,
        "ptycho.config",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"pydantic.with_config"}),
    )
    class_consumers = {
        f"@consumer:{row['consumer_id']}"
        for row in rows
        if row["public_entry_route"] == "ptycho.config.ExampleConfig"
    }
    runtime_consumer = next(
        f"@consumer:{row['consumer_id']}"
        for row in rows
        if row["public_entry_route"] == "ptycho.config.consume"
    )

    assert all(
        "dependency.compatibility_load" in graph[consumer]
        and bypasses[consumer] == ("TOLERANT_OR_COMPATIBILITY_LOADER",)
        for consumer in class_consumers
    )
    assert "dependency.compatibility_load" not in graph[runtime_consumer]
    assert runtime_consumer not in bypasses


@pytest.mark.parametrize(
    ("mutation", "closed"),
    (
        ("", True),
        ("adapt = lambda value: value.get('adapter', {})\n", False),
        ("del adapt\n", False),
    ),
)
def test_class_decorator_adapter_binding_must_remain_unique(
    tmp_path: Path,
    mutation: str,
    closed: bool,
) -> None:
    path = tmp_path / "ptycho/config.py"
    path.parent.mkdir()
    path.write_text(
        "from pydantic import with_config\n"
        "_CONFIG = {}\n"
        "def adapt(value):\n"
        "    return value\n"
        + mutation
        + "@with_config(adapt(_CONFIG))\n"
        "class ExampleConfig:\n"
        "    pass\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.config",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"pydantic.with_config"}),
    )

    consumers = {f"@consumer:{row['consumer_id']}" for row in rows}
    if closed:
        assert all(graph[symbol] == ["pydantic.with_config"] for symbol in consumers)
    else:
        assert all(
            any(call.startswith("@unresolved-binding:") for call in graph[symbol])
            for symbol in consumers
        )
    result = evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": row["consumer_id"],
            "entry_symbol": f"@consumer:{row['consumer_id']}",
            "requires_authority": False,
        } for row in rows],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )
    assert result["closed"] is closed


def test_rebound_local_function_call_does_not_use_stale_definition(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ptycho/consumer.py"
    path.parent.mkdir()
    path.write_text(
        "def adapt(value):\n"
        "    return value\n"
        "adapt = lambda value: value\n"
        "def consume(runtime_config):\n"
        "    return adapt(runtime_config)\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.consumer",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
    )
    consumer = f"@consumer:{rows[0]['consumer_id']}"

    assert any(
        call.startswith("@unresolved-binding:") for call in graph[consumer]
    )
    result = evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": rows[0]["consumer_id"],
            "entry_symbol": consumer,
            "requires_authority": False,
        }],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )
    assert result["closed"] is False


@pytest.mark.parametrize(
    ("definition_before_decorator", "expected_call", "has_bypass"),
    (
        (False, "dependency.compatibility_load", True),
        (True, "pydantic.with_config", False),
    ),
)
def test_class_decorator_uses_binding_active_at_its_source_position(
    tmp_path: Path,
    definition_before_decorator: bool,
    expected_call: str,
    has_bypass: bool,
) -> None:
    path = tmp_path / "ptycho/config.py"
    path.parent.mkdir()
    definition = "def adapt(value):\n    return value\n"
    decorator = (
        "@with_config(adapt(_CONFIG))\n"
        "class ExampleConfig:\n"
        "    pass\n"
    )
    path.write_text(
        "from dependency import compatibility_load as adapt\n"
        "from pydantic import with_config\n"
        "_CONFIG = {}\n"
        + (definition + decorator if definition_before_decorator else decorator + definition),
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.config",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"pydantic.with_config"}),
    )

    consumers = {f"@consumer:{row['consumer_id']}" for row in rows}
    assert all(expected_call in graph[symbol] for symbol in consumers)
    assert all(
        ("TOLERANT_OR_COMPATIBILITY_LOADER" in bypasses.get(symbol, ()))
        is has_bypass
        for symbol in consumers
    )


def test_conditional_module_import_is_not_active_for_class_decorator(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ptycho/config.py"
    path.parent.mkdir()
    path.write_text(
        "if False:\n"
        "    from pydantic import with_config\n"
        "_CONFIG = {}\n"
        "@with_config(_CONFIG)\n"
        "class ExampleConfig:\n"
        "    pass\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.config",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"pydantic.with_config"}),
    )

    consumers = {f"@consumer:{row['consumer_id']}" for row in rows}
    assert all("pydantic.with_config" not in graph[symbol] for symbol in consumers)
    result = evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": row["consumer_id"],
            "entry_symbol": f"@consumer:{row['consumer_id']}",
            "requires_authority": False,
        } for row in rows],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )
    assert result["closed"] is False


def test_ordinary_calls_use_final_module_function_after_import_shadow(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ptycho/consumer.py"
    path.parent.mkdir()
    path.write_text(
        "from dependency import compatibility_load as adapt\n"
        "def before(runtime_config):\n"
        "    return adapt(runtime_config)\n"
        "def adapt(value):\n"
        "    return value.get('mode', 'default')\n"
        "def after(runtime_config):\n"
        "    return adapt(runtime_config)\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, _, _ = evaluator._module_functions(
        path,
        "ptycho.consumer",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
    )
    consumers = {
        row["public_entry_route"].rsplit(".", 1)[-1]:
            f"@consumer:{row['consumer_id']}"
        for row in rows
    }

    for consumer in consumers.values():
        assert "dependency.compatibility_load" not in graph[consumer]
        assert "ptycho.consumer.value.get" in graph[consumer]
        assert bypasses[consumer] == ("TOLERANT_OR_COMPATIBILITY_LOADER",)


def test_future_function_local_import_does_not_fall_back_to_module_import(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ptycho/consumer.py"
    path.parent.mkdir()
    path.write_text(
        "from dependency import compatibility_load as adapt\n"
        "def consume(runtime_config):\n"
        "    result = adapt(runtime_config)\n"
        "    from json import dumps as adapt\n"
        "    return result\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, _, _, _, _ = evaluator._module_functions(
        path,
        "ptycho.consumer",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
    )
    consumer = f"@consumer:{rows[0]['consumer_id']}"

    assert not {
        "dependency.compatibility_load", "json.dumps"
    } & set(graph[consumer])


@pytest.mark.parametrize(
    "compound",
    (
        "    if False:\n"
        "        from json import dumps as adapt\n",
        "    try:\n"
        "        from json import dumps as adapt\n"
        "    except ImportError:\n"
        "        pass\n",
        "    for _ in ():\n"
        "        from json import dumps as adapt\n",
        "    while False:\n"
        "        from json import dumps as adapt\n",
        "    match False:\n"
        "        case True:\n"
        "            from json import dumps as adapt\n",
        "    with nullcontext():\n"
        "        from json import dumps as adapt\n",
    ),
    ids=("if-false", "try", "for", "while", "match", "with"),
)
def test_compound_function_import_is_not_a_definite_binding(
    tmp_path: Path,
    compound: str,
) -> None:
    path = tmp_path / "ptycho/consumer.py"
    path.parent.mkdir()
    path.write_text(
        "from contextlib import nullcontext\n"
        "def consume(runtime_config):\n"
        + compound
        + "    return adapt(runtime_config)\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.consumer",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"json.dumps"}),
    )
    consumer = f"@consumer:{rows[0]['consumer_id']}"

    assert "json.dumps" not in graph[consumer]
    result = evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": rows[0]["consumer_id"],
            "entry_symbol": consumer,
            "requires_authority": False,
        }],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )
    assert result["closed"] is False


@pytest.mark.parametrize(
    "mutation",
    (
        "adapt = lambda value: value\n",
        "del adapt\n",
    ),
)
def test_ordinary_function_binding_becomes_unresolved_at_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    path = tmp_path / "ptycho/consumer.py"
    path.parent.mkdir()
    path.write_text(
        "def adapt(value):\n"
        "    return value\n"
        "def before(runtime_config):\n"
        "    return adapt(runtime_config)\n"
        + mutation
        + "def after(runtime_config):\n"
        "    return adapt(runtime_config)\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, _, _, _, _ = evaluator._module_functions(
        path,
        "ptycho.consumer",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
    )
    consumers = {
        row["public_entry_route"].rsplit(".", 1)[-1]:
            f"@consumer:{row['consumer_id']}"
        for row in rows
    }

    assert all(
        any(call.startswith("@unresolved-binding:") for call in graph[consumer])
        for consumer in consumers.values()
    )


def test_duplicate_class_basenames_keep_decorator_occurrences_unambiguous(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    for relative in ("ptycho/first.py", "ptycho/second.py"):
        path = workspace / relative
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            "from pydantic import with_config\n"
            "_CONFIG = {}\n"
            "@with_config(_CONFIG)\n"
            "class SharedConfig:\n"
            "    pass\n",
            encoding="utf-8",
        )
    census = {"rows": [{
        "consumer_id": "retired-authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["added_consumer_count"] == 4
    assert all(
        trace["paths"][0][-1] == "pydantic.with_config"
        for trace in result["traces"]
    )


def test_class_decorator_occurrence_is_not_absorbed_by_explicit_init(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ptycho/config.py"
    path.parent.mkdir()
    path.write_text(
        "from pydantic import with_config\n"
        "_CONFIG = {}\n"
        "@with_config(_CONFIG)\n"
        "class ExampleConfig:\n"
        "    def __init__(self):\n"
        "        self.value = 1\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]

    graph, _, _, _, _ = evaluator._module_functions(
        path,
        "ptycho.config",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"pydantic.with_config"}),
    )

    assert graph["ptycho.config.ExampleConfig"] == [
        "ptycho.config.ExampleConfig.__init__"
    ]
    assert all(
        graph[f"@consumer:{row['consumer_id']}"] == ["pydantic.with_config"]
        for row in rows
    )


def test_class_decorator_missing_span_or_mismatched_owner_fails_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ptycho/config.py"
    path.parent.mkdir()
    path.write_text(
        "from pydantic import with_config\n"
        "_CONFIG = {}\n"
        "@with_config(_CONFIG)\n"
        "class ExampleConfig:\n"
        "    def __init__(self):\n"
        "        candidate_authority()\n"
        "def consume():\n"
        "    pass\n",
        encoding="utf-8",
    )
    decorator_rows = evaluator.scan_workspace_configuration_consumers(tmp_path)[
        "rows"
    ]
    missing_span = dict(decorator_rows[0], consumer_id="missing-span")
    missing_span.pop("source_span")
    mismatched_owner = dict(
        decorator_rows[1],
        consumer_id="mismatched-owner",
        public_entry_route="ptycho.config.consume",
    )

    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.config",
        authority_symbols={"ptycho.config.candidate_authority"},
        consumer_rows=[missing_span, mismatched_owner],
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"pydantic.with_config"}),
    )

    assert graph["@consumer:missing-span"] == [
        "@unresolved-class-decorator:missing-span"
    ]
    assert graph["@consumer:mismatched-owner"] == [
        "@unresolved-class-decorator:mismatched-owner"
    ]
    result = evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": consumer_id,
            "entry_symbol": f"@consumer:{consumer_id}",
            "requires_authority": False,
        } for consumer_id in ("missing-span", "mismatched-owner")],
        call_graph=graph,
        authority_symbols={"ptycho.config.candidate_authority"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )
    assert result["closed"] is False


@pytest.mark.parametrize(
    "prefix",
    (
        "",
        "from pydantic import with_config\n"
        "with_config = lambda value: value\n",
    ),
)
def test_unresolved_or_rebound_class_decorator_fails_closed(
    tmp_path: Path,
    prefix: str,
) -> None:
    path = tmp_path / "ptycho/config.py"
    path.parent.mkdir()
    path.write_text(
        prefix
        + "_CONFIG = {}\n"
        "@with_config(_CONFIG)\n"
        "class ExampleConfig:\n"
        "    pass\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.config",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"pydantic.with_config"}),
    )

    result = evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": row["consumer_id"],
            "entry_symbol": f"@consumer:{row['consumer_id']}",
            "requires_authority": False,
        } for row in rows],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )

    assert all(f"@consumer:{row['consumer_id']}" in graph for row in rows)
    assert result["closed"] is False


def test_class_decorator_construction_cannot_close_at_external_terminal(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ptycho/config.py"
    path.parent.mkdir()
    path.write_text(
        "from pydantic import with_config\n"
        "_CONFIG = {}\n"
        "@with_config(_CONFIG)\n"
        "class ExampleConfig:\n"
        "    pass\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    call_row = next(
        row for row in rows
        if row["transitive_wrapper_chain"][-1] == "with_config"
    )
    call_row["match_kind"] = "CONFIGURATION_CONSTRUCTION"
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.config",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=[call_row],
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"pydantic.with_config"}),
    )

    result = evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": call_row["consumer_id"],
            "entry_symbol": f"@consumer:{call_row['consumer_id']}",
            "requires_authority": evaluator._requires_resolution_authority(call_row),
        }],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )

    assert graph[f"@consumer:{call_row['consumer_id']}"] == [
        "pydantic.with_config"
    ]
    assert result["closed"] is False


def test_canonical_dataclass_decorators_create_all_sixteen_exact_routes(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): "
            "return {**file_mapping, **cli_patch}\n"
        ),
    )
    path = workspace / "ptycho/config/config.py"
    path.parent.mkdir(parents=True)
    classes = (
        "ProbeSimulationConfig",
        "SyntheticObjectConfig",
        "ScanSimulationConfig",
        "DetectorSimulationConfig",
        "SimulationConfig",
        "ModelConfig",
        "TrainingConfig",
        "InferenceConfig",
    )
    path.write_text(
        "from dataclasses import dataclass\n"
        "from pydantic import with_config\n"
        "_DATACLASS_ADAPTER_CONFIG = {}\n\n"
        + "\n\n".join(
            "@with_config(_DATACLASS_ADAPTER_CONFIG)\n"
            "@dataclass(frozen=True)\n"
            f"class {name}:\n"
            "    pass"
            for name in classes
        )
        + "\n",
        encoding="utf-8",
    )
    scanned = evaluator.scan_workspace_configuration_consumers(workspace)["rows"]
    rows = [row for row in scanned if row["path"] == "ptycho/config/config.py"]
    census = {"rows": [{
        "consumer_id": "retired-authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert len(rows) == 16
    assert {row["public_entry_route"].rsplit(".", 1)[-1] for row in rows} == set(
        classes
    )
    assert result["added_consumer_count"] == 16
    assert result["accounted_consumer_count"] == 16
    assert result["closed"] is True
    assert all(
        trace["paths"][0][0] == f"@consumer:{trace['consumer_id']}"
        and trace["paths"][0][-1] == "pydantic.with_config"
        for trace in result["traces"]
    )


def test_external_import_probe_requires_the_exact_target() -> None:
    assert evaluator._available_external_imports(
        frozenset({
            "json.dumps",
            "json.encoder.INFINITY",
            "json.definitely_missing",
        }),
        Path(sys.executable),
    ) == frozenset({"json.dumps"})


def test_external_import_probe_walks_attributes_after_longest_module_prefix() -> None:
    target = "json.encoder.JSONEncoder.default"
    assert evaluator._available_external_imports(
        frozenset({target}), Path(sys.executable)
    ) == frozenset({target})


def test_external_import_probe_handles_nested_ml_attribute_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tensorflow_target = "tensorflow.python.framework.ops.convert_to_tensor"
    tensordict_target = "tensordict.nn.TensorDictModule.forward"
    modules = {
        "tensorflow.python.framework.ops": SimpleNamespace(
            convert_to_tensor=lambda value: value
        ),
        "tensordict.nn": SimpleNamespace(
            TensorDictModule=type(
                "TensorDictModule", (), {"forward": lambda self, value: value}
            )
        ),
    }

    def import_module(name: str) -> Any:
        if name not in modules:
            raise ModuleNotFoundError(name)
        return modules[name]

    monkeypatch.setattr(evaluator.importlib, "import_module", import_module)

    assert evaluator._available_external_imports(
        frozenset({tensorflow_target, tensordict_target}), None
    ) == frozenset({tensorflow_target, tensordict_target})


def test_simple_module_callable_alias_is_a_static_graph_edge(tmp_path: Path) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "helper.py").write_text(
        "def read(value):\n    return value\n", encoding="utf-8"
    )
    (package / "alias.py").write_text(
        "from ptycho import helper\nread = helper.read\n", encoding="utf-8"
    )
    (package / "consumer.py").write_text(
        "from ptycho.alias import read\n"
        "def consume(runtime_config):\n"
        "    return read(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True


def test_simple_module_callable_alias_may_target_an_external_callable(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/alias_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "import json\n"
        "encode = json.dumps\n"
        "def consume(runtime_config):\n"
        "    return encode(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True


@pytest.mark.parametrize(
    "alias_source",
    (
        "from ptycho import helper\n"
        "read = helper.read\n"
        "read = lambda value: value\n",
        "from ptycho.helper import missing as read\n"
        "from ptycho import helper\n"
        "read = helper.read\n",
        "from ptycho import helper\n"
        "read = helper.read\n"
        "del read\n",
    ),
)
def test_rebound_module_callable_alias_fails_closed(
    tmp_path: Path, alias_source: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "helper.py").write_text(
        "def read(value):\n    return value\n", encoding="utf-8"
    )
    (package / "alias.py").write_text(
        alias_source,
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from ptycho.alias import read\n"
        "def consume(runtime_config):\n"
        "    return read(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False


def test_missing_attribute_on_imported_module_is_not_a_terminal(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/external_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "import json\n"
        "def consume(runtime_config):\n"
        "    return json.definitely_missing(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False


def test_namespace_only_workspace_directory_does_not_shadow_external_package(
    tmp_path: Path,
) -> None:
    workspace, _ = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    (workspace / "torch").mkdir()
    path = workspace / "scripts/external_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "import torch.nn.functional as functional\n"
        "def consume(runtime_config):\n"
        "    return functional.normalize(runtime_config)\n",
        encoding="utf-8",
    )
    _, _, _, terminals, _ = evaluator._module_functions(
        path,
        "scripts.external_reader",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=[{"public_entry_route": "scripts.external_reader.consume"}],
        workspace_module_roots=frozenset({"candidate", "scripts"}),
        available_external_imports=frozenset({
            "torch.nn.functional.normalize"
        }),
    )

    assert "torch.nn.functional.normalize" in terminals


@pytest.mark.parametrize(
    ("shadow", "closed"),
    ((None, True), ("module", False), ("package", False)),
)
def test_census_root_shadows_external_package_only_when_importable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shadow: str | None,
    closed: bool,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "json"
    package.mkdir()
    if shadow == "module":
        (workspace / "json.py").write_text("value = 1\n", encoding="utf-8")
    elif shadow == "package":
        (package / "__init__.py").write_text("value = 1\n", encoding="utf-8")
    path = package / "consumer.py"
    path.write_text(
        "import json\n"
        "def consume(runtime_config):\n"
        "    return json.dumps(runtime_config)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "json-consumer",
        "match_kind": "CONFIGURATION_READ",
        "path": "json/consumer.py",
        "public_entry_route": "json.consumer.consume",
        "source_span": {
            "start_line": 3,
            "start_col": 22,
            "end_line": 3,
            "end_col": 36,
        },
        "transitive_wrapper_chain": ["json.consumer.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
        python_executable=Path(sys.executable),
    )

    assert result["closed"] is closed


def test_parameter_shadowing_an_import_is_not_an_external_terminal(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/external_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "from json import dumps\n"
        "def consume(runtime_config, dumps):\n"
        "    return dumps(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False


def test_module_rebinding_an_import_is_not_an_external_terminal(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/external_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "import json\n"
        "class Adapter:\n"
        "    def dumps(self, value):\n"
        "        return value.get('mode', 'default')\n"
        "json = Adapter()\n"
        "def consume(runtime_config):\n"
        "    return json.dumps(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "source",
    (
        "from pathlib import Path\n"
        "class Path:\n"
        "    def __init__(self, value):\n"
        "        self.value = value.get('mode', 'default')\n"
        "def consume(runtime_config):\n"
        "    return Path(runtime_config)\n",
        "from json import dumps\n"
        "def dumps(value):\n"
        "    return value.get('mode', 'default')\n"
        "def consume(runtime_config):\n"
        "    return dumps(runtime_config)\n",
    ),
)
def test_local_callable_binding_shadows_imported_terminal(
    tmp_path: Path,
    source: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/local_binding.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(source, encoding="utf-8")
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


def test_deleted_module_import_is_not_an_external_terminal(tmp_path: Path) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/deleted_import.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "import json\n"
        "del json\n"
        "def consume(runtime_config):\n"
        "    return json.dumps(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False


@pytest.mark.parametrize(
    "source",
    (
        (
            "import candidate.config as backend\n"
            "import candidate.config as backend\n"
            "import candidate.config as backend\n"
            "def consume(runtime_config):\n"
            "    return backend.resolve(runtime_config, {})\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    import candidate.config as backend\n"
            "    import candidate.config as backend\n"
            "    return backend.resolve(runtime_config, {})\n"
        ),
    ),
    ids=("module-triple", "function-double"),
)
def test_same_suite_same_target_reimports_remain_definite(
    tmp_path: Path,
    source: str,
) -> None:
    calls, _, closed = _synthetic_owner_route(
        tmp_path,
        module="package.reimports",
        owner="package.reimports.consume",
        source=source,
    )

    assert calls == ["candidate.config.resolve"]
    assert closed is True


@pytest.mark.parametrize(
    "source",
    (
        (
            "import candidate.config as backend\n"
            "import candidate.config as backend\n"
            "backend.resolve = replacement\n"
            "def consume(runtime_config):\n"
            "    return backend.resolve(runtime_config, {})\n"
        ),
        (
            "import candidate.config as backend\n"
            "import candidate.config as backend\n"
            "capture(backend)\n"
            "def consume(runtime_config):\n"
            "    return backend.resolve(runtime_config, {})\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    import candidate.config as backend\n"
            "    import candidate.config as backend\n"
            "    backend.resolve = replacement\n"
            "    return backend.resolve(runtime_config, {})\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    import candidate.config as backend\n"
            "    import candidate.config as backend\n"
            "    capture(backend)\n"
            "    return backend.resolve(runtime_config, {})\n"
        ),
        (
            "import candidate.config as backend\n"
            "import candidate.config as backend\n"
            "class MutateBackend:\n"
            "    backend.resolve = replacement\n"
            "def consume(runtime_config):\n"
            "    return backend.resolve(runtime_config, {})\n"
        ),
        (
            "def consume(runtime_config):\n"
            "    import candidate.config as backend\n"
            "    import candidate.config as backend\n"
            "    class Outer:\n"
            "        class LeakBackend:\n"
            "            capture(backend)\n"
            "    return backend.resolve(runtime_config, {})\n"
        ),
    ),
    ids=(
        "module-attribute-mutation",
        "module-argument-escape",
        "function-attribute-mutation",
        "function-argument-escape",
        "module-class-attribute-mutation",
        "function-class-argument-escape",
    ),
)
def test_authority_reimport_recovery_rejects_mutation_or_escape(
    tmp_path: Path,
    source: str,
) -> None:
    calls, _, closed = _synthetic_owner_route(
        tmp_path,
        module="package.reimports",
        owner="package.reimports.consume",
        source=source,
    )

    assert calls == ["package.reimports.backend"]
    assert closed is False


@pytest.mark.parametrize(
    "source",
    (
        (
            "import json as backend\n"
            "import pathlib as backend\n"
            "def consume(runtime_config):\n"
            "    return backend.dumps(runtime_config)\n"
        ),
        (
            "import json as backend\n"
            "if enabled:\n"
            "    import json as backend\n"
            "def consume(runtime_config):\n"
            "    return backend.dumps(runtime_config)\n"
        ),
        (
            "import json as backend\n"
            "try:\n"
            "    import json as backend\n"
            "except ImportError:\n"
            "    pass\n"
            "def consume(runtime_config):\n"
            "    return backend.dumps(runtime_config)\n"
        ),
        (
            "import json as backend\n"
            "backend = replacement\n"
            "import json as backend\n"
            "def consume(runtime_config):\n"
            "    return backend.dumps(runtime_config)\n"
        ),
        (
            "import json as backend\n"
            "del backend\n"
            "import json as backend\n"
            "def consume(runtime_config):\n"
            "    return backend.dumps(runtime_config)\n"
        ),
        (
            "import json as backend\n"
            "import json as backend\n"
            "backend.dumps = replacement\n"
            "def consume(runtime_config):\n"
            "    return backend.dumps(runtime_config)\n"
        ),
        (
            "import json as backend\n"
            "import json as backend\n"
            "capture(backend)\n"
            "def consume(runtime_config):\n"
            "    return backend.dumps(runtime_config)\n"
        ),
    ),
    ids=(
        "different-target",
        "branch",
        "try",
        "assignment",
        "delete",
        "object-mutation",
        "argument-escape",
    ),
)
def test_reimport_recovery_rejects_ambiguous_or_unsafe_bindings(
    tmp_path: Path,
    source: str,
) -> None:
    calls, terminals, closed = _synthetic_owner_route(
        tmp_path,
        module="package.reimports",
        owner="package.reimports.consume",
        source=source,
        available_external_imports=frozenset({"json.dumps"}),
    )

    assert calls != ["json.dumps"] or "json.dumps" not in terminals
    assert closed is False


@pytest.mark.parametrize(
    "imports",
    (
        "    from json import dumps as read\n"
        "    from pathlib import Path as read\n",
        "    from pathlib import Path as read\n"
        "    from json import dumps as read\n",
    ),
)
def test_conflicting_function_local_imports_fail_closed_in_both_orders(
    tmp_path: Path,
    imports: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/ambiguous_import.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def consume(runtime_config):\n"
        + imports
        + "    return read(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False


def test_conflicting_module_imports_are_unresolved_for_all_function_bodies(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ptycho/consumer.py"
    path.parent.mkdir()
    path.write_text(
        "from json import dumps as read\n"
        "def before(runtime_config):\n"
        "    return read(runtime_config)\n"
        "from pathlib import Path as read\n"
        "def after(runtime_config):\n"
        "    return read(runtime_config)\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, _, _, _, _ = evaluator._module_functions(
        path,
        "ptycho.consumer",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
    )
    consumers = {
        row["public_entry_route"].rsplit(".", 1)[-1]:
            f"@consumer:{row['consumer_id']}"
        for row in rows
    }

    assert all(
        not {"json.dumps", "pathlib.Path"} & set(graph[consumer])
        for consumer in consumers.values()
    )


@pytest.mark.parametrize(
    "binding",
    (
        "    match marker:\n"
        "        case dumps:\n"
        "            pass\n",
        "    match marker:\n"
        "        case [*dumps]:\n"
        "            pass\n",
        "    match marker:\n"
        "        case {**dumps}:\n"
        "            pass\n",
        "    try:\n"
        "        pass\n"
        "    except Exception as dumps:\n"
        "        pass\n",
    ),
    ids=("match-as", "match-star", "match-mapping-rest", "except-name"),
)
def test_string_backed_local_binding_invalidates_an_imported_terminal(
    tmp_path: Path,
    binding: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/pattern_binding.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def consume(runtime_config, marker):\n"
        "    from json import dumps\n"
        + binding
        + "    return dumps(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False


def test_unambiguous_function_local_import_is_an_external_terminal(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/local_import.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def consume(runtime_config):\n"
        "    from json import dumps\n"
        "    return dumps(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True


def test_external_import_probe_timeout_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*args: Any, **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(evaluator.subprocess, "run", timeout)
    with pytest.raises(evaluator.EvaluatorError, match="external module probe failed"):
        evaluator._available_external_imports(
            frozenset({"json.dumps"}), Path(sys.executable)
        )


def test_external_import_probe_ignores_dependency_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evaluator.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, '["json.dumps"]\n', "optional accelerator unavailable\n"
        ),
    )

    assert evaluator._available_external_imports(
        frozenset({"json.dumps"}), Path(sys.executable)
    ) == frozenset({"json.dumps"})


@pytest.mark.parametrize("tolerant", (False, True))
def test_workspace_constructor_is_recursively_analyzed(
    tmp_path: Path, tolerant: bool,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "owner.py").write_text(
        "class Owner:\n"
        "    def __init__(self, value):\n"
        + (
            "        self.value = value.get('mode', 'default')\n"
            if tolerant
            else "        self.value = value\n"
        ),
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from ptycho.owner import Owner\n"
        "def consume(runtime_config):\n"
        "    return Owner(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is not tolerant
    assert ("TOLERANT_OR_COMPATIBILITY_LOADER" in result["bypass_classes"]) is tolerant


def test_already_indexed_cross_module_helper_receives_carrier_taint(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "helper.py").write_text(
        "def unrelated(config):\n"
        "    return config.value\n"
        "def read(value):\n"
        "    return value.get('mode', 'default')\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from ptycho.helper import read\n"
        "def consume(runtime_config):\n"
        "    return read(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


@pytest.mark.parametrize(
    ("tolerant_formal", "closed"),
    (("data", False), ("options", True)),
)
def test_exact_cross_module_taint_binds_only_the_relevant_formal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tolerant_formal: str,
    closed: bool,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "helper.py").write_text(
        "def helper(data, options):\n"
        f"    return {tolerant_formal}.get('mode', 'default')\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from ptycho.helper import helper\n"
        "def consume(runtime_config, options):\n"
        "    return helper(runtime_config, options)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "cross-module-formal",
        "match_kind": "CONFIGURATION_READ",
        "path": "ptycho/consumer.py",
        "public_entry_route": "ptycho.consumer.consume",
        "source_span": {
            "start_line": 3,
            "start_col": 18,
            "end_line": 3,
            "end_col": 32,
        },
        "transitive_wrapper_chain": ["ptycho.consumer.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is closed
    assert result["bypass_classes"] == (
        [] if closed else ["TOLERANT_OR_COMPATIBILITY_LOADER"]
    )


def test_ambiguous_cross_module_formal_binding_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "helper.py").write_text(
        "def helper(data, options):\n"
        "    return options.get('mode', 'default')\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from ptycho.helper import helper\n"
        "def consume(runtime_config):\n"
        "    return helper(*runtime_config)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "ambiguous-cross-module-formal",
        "match_kind": "CONFIGURATION_READ",
        "path": "ptycho/consumer.py",
        "public_entry_route": "ptycho.consumer.consume",
        "source_span": {
            "start_line": 3,
            "start_col": 19,
            "end_line": 3,
            "end_col": 33,
        },
        "transitive_wrapper_chain": ["ptycho.consumer.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


def test_missing_cross_module_context_remains_conservative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "helper.py").write_text(
        "def helper(data, options):\n"
        "    return options.get('mode', 'default')\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from ptycho.helper import helper\n"
        "def consume(runtime_config, options):\n"
        "    return helper(runtime_config, options)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "missing-cross-module-context",
        "match_kind": "CONFIGURATION_READ",
        "path": "ptycho/consumer.py",
        "public_entry_route": "ptycho.consumer.consume",
        "transitive_wrapper_chain": ["ptycho.consumer.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


@pytest.mark.parametrize(
    ("tolerant_formal", "closed"),
    (("data", False), ("options", True)),
)
def test_exact_context_crosses_a_valid_static_callable_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tolerant_formal: str,
    closed: bool,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "helper.py").write_text(
        "def read(data, options):\n"
        f"    return {tolerant_formal}.get('mode', 'default')\n",
        encoding="utf-8",
    )
    (package / "alias.py").write_text(
        "from ptycho import helper\nread = helper.read\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from ptycho.alias import read\n"
        "def consume(runtime_config, options):\n"
        "    return read(runtime_config, options)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "aliased-cross-module-formal",
        "match_kind": "CONFIGURATION_READ",
        "path": "ptycho/consumer.py",
        "public_entry_route": "ptycho.consumer.consume",
        "source_span": {
            "start_line": 3,
            "start_col": 16,
            "end_line": 3,
            "end_col": 30,
        },
        "transitive_wrapper_chain": ["ptycho.consumer.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is closed
    assert result["bypass_classes"] == (
        [] if closed else ["TOLERANT_OR_COMPATIBILITY_LOADER"]
    )


@pytest.mark.parametrize(
    ("tolerant_formal", "closed"),
    (("data", False), ("options", True)),
)
def test_exact_context_binds_a_workspace_constructor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tolerant_formal: str,
    closed: bool,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "owner.py").write_text(
        "class Owner:\n"
        "    def __init__(self, data, options):\n"
        f"        self.value = {tolerant_formal}.get('mode', 'default')\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from ptycho.owner import Owner\n"
        "def consume(runtime_config, options):\n"
        "    return Owner(runtime_config, options)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "constructor-cross-module-formal",
        "match_kind": "CONFIGURATION_READ",
        "path": "ptycho/consumer.py",
        "public_entry_route": "ptycho.consumer.consume",
        "source_span": {
            "start_line": 3,
            "start_col": 17,
            "end_line": 3,
            "end_col": 31,
        },
        "transitive_wrapper_chain": ["ptycho.consumer.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is closed
    assert result["bypass_classes"] == (
        [] if closed else ["TOLERANT_OR_COMPATIBILITY_LOADER"]
    )


def test_workspace_constructor_without_static_context_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "owner.py").write_text("class Owner: pass\n", encoding="utf-8")
    (package / "consumer.py").write_text(
        "from ptycho.owner import Owner\n"
        "def consume(runtime_config):\n"
        "    return Owner(runtime_config)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "unresolved-constructor-context",
        "match_kind": "CONFIGURATION_READ",
        "path": "ptycho/consumer.py",
        "public_entry_route": "ptycho.consumer.consume",
        "source_span": {
            "start_line": 3,
            "start_col": 17,
            "end_line": 3,
            "end_col": 31,
        },
        "transitive_wrapper_chain": ["ptycho.consumer.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is False


def test_implicit_inherited_workspace_constructor_context_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "owner.py").write_text(
        "class Base:\n"
        "    def __init__(self, data, options):\n"
        "        self.value = data\n"
        "class Owner(Base):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from ptycho.owner import Owner\n"
        "def consume(runtime_config, options):\n"
        "    return Owner(runtime_config, options)\n",
        encoding="utf-8",
    )
    row = {
        "consumer_id": "implicit-inherited-constructor",
        "match_kind": "CONFIGURATION_READ",
        "path": "ptycho/consumer.py",
        "public_entry_route": "ptycho.consumer.consume",
        "source_span": {
            "start_line": 3,
            "start_col": 17,
            "end_line": 3,
            "end_col": 31,
        },
        "transitive_wrapper_chain": ["ptycho.consumer.consume", "runtime_config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [row]},
        workspace=workspace,
    )

    assert result["closed"] is False


def test_inherited_workspace_constructor_is_recursively_analyzed(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "owner.py").write_text(
        "class Base:\n"
        "    def __init__(self, value):\n"
        "        self.value = value.get('mode', 'default')\n"
        "class Owner(Base):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from ptycho.owner import Owner\n"
        "def consume(runtime_config):\n"
        "    return Owner(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


def test_inherited_external_constructor_is_a_valid_terminal(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/external_owner.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "from pathlib import Path\n"
        "class Owner(Path):\n"
        "    pass\n"
        "def consume(runtime_config):\n"
        "    return Owner(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True


@pytest.mark.parametrize("tolerant", (False, True))
def test_super_constructor_is_resolved_before_terminal_classification(
    tmp_path: Path, tolerant: bool,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    package = workspace / "ptycho"
    package.mkdir(exist_ok=True)
    (package / "owner.py").write_text(
        "class Base:\n"
        "    def __init__(self, value):\n"
        + (
            "        self.value = value.get('mode', 'default')\n"
            if tolerant
            else "        self.value = value\n"
        )
        + "class Owner(Base):\n"
        "    def __init__(self, value):\n"
        "        super().__init__(value)\n",
        encoding="utf-8",
    )
    (package / "consumer.py").write_text(
        "from ptycho.owner import Owner\n"
        "def consume(runtime_config):\n"
        "    return Owner(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is not tolerant
    assert ("TOLERANT_OR_COMPATIBILITY_LOADER" in result["bypass_classes"]) is tolerant


def test_non_configuration_local_helper_is_not_a_consumer_route(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/scientific_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def scientific_scale(value):\n"
        "    return value * 2\n"
        "def consume(runtime_config):\n"
        "    return runtime_config.value * scientific_scale(1)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []


def test_derived_configuration_field_is_not_propagated_as_the_whole_carrier(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/scientific_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def scientific_scale(value):\n"
        "    return value * 2\n"
        "def consume(runtime_config):\n"
        "    return scientific_scale(runtime_config.scale)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["bypass_classes"] == []


def test_candidate_type_alias_cannot_hide_a_tolerant_configuration_read(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/alias_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "ModelConfig = dict\n"
        "def consume(config: ModelConfig):\n"
        "    return config.get('mode', 'default')\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


def test_frozen_route_survives_a_lexical_carrier_rename(tmp_path: Path) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/renamed_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def consume(settings):\n"
        "    return settings.get('mode', 'default')\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "frozen-reader",
        "match_kind": "CONFIGURATION_READ",
        "path": "scripts/renamed_reader.py",
        "public_entry_route": "scripts.renamed_reader.consume",
        "source_span": {
            "start_line": 2, "start_col": 11, "end_line": 2, "end_col": 19,
        },
        "transitive_wrapper_chain": ["scripts.renamed_reader.consume", "config"],
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]
    assert result["accounted_consumer_count"] == 1
    assert len(result["traces"]) == 1
    assert result["removed_consumer_count"] == 0


def test_frozen_route_with_a_stale_span_uses_conservative_route_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/rewritten_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "from candidate.config import resolve\n"
        "def consume(settings):\n"
        "    return resolve(settings, {})\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": []},
    )
    census = {"rows": [{
        "consumer_id": "frozen-rewritten-reader",
        "bypass_classes": ["TOLERANT_OR_COMPATIBILITY_LOADER"],
        "match_kind": "CONFIGURATION_READ",
        "path": "scripts/rewritten_reader.py",
        "public_entry_route": "scripts.rewritten_reader.consume",
        "source_span": {
            "start_line": 99, "start_col": 0, "end_line": 99, "end_col": 1,
        },
        "transitive_wrapper_chain": ["scripts.rewritten_reader.consume", "config"],
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True
    assert result["removed_consumer_count"] == 1


@pytest.mark.parametrize(
    "source",
    (
        "class C:\n"
        "    def helper(self, value):\n"
        "        return value.get('mode', 'default')\n"
        "def consume(runtime_config):\n"
        "    return C.helper(C(), runtime_config)\n",
        "def helper(*values):\n"
        "    return values[0].get('mode', 'default')\n"
        "def consume(runtime_config):\n"
        "    return helper(runtime_config)\n",
        "def helper(**values):\n"
        "    return values.get('config', {}).get('mode', 'default')\n"
        "def consume(runtime_config):\n"
        "    return helper(config=runtime_config)\n",
        "def helper(first, second):\n"
        "    return second.get('mode', 'default')\n"
        "def consume(runtime_config, values):\n"
        "    return helper(*values, runtime_config)\n",
    ),
)
def test_whole_carrier_taint_survives_python_call_binding(
    tmp_path: Path, source: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/wrapper_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(source, encoding="utf-8")
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


@pytest.mark.parametrize(
    "expression",
    ("helper(identity(runtime_config))", "helper(runtime_config or {})"),
)
def test_carrier_taint_survives_calls_and_fallback_expressions(
    tmp_path: Path, expression: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/expression_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def identity(value):\n"
        "    return value\n"
        "def helper(value):\n"
        "    return value.get('mode', 'default')\n"
        "def consume(runtime_config):\n"
        f"    return {expression}\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert "TOLERANT_OR_COMPATIBILITY_LOADER" in result["bypass_classes"]


@pytest.mark.parametrize(
    "source",
    (
        "class C:\n"
        "    @classmethod\n"
        "    def helper(receiver, value):\n"
        "        return value.get('mode', 'default')\n"
        "def consume(runtime_config):\n"
        "    return C.helper(runtime_config)\n",
        "class C:\n"
        "    def helper(receiver, value):\n"
        "        return value.get('mode', 'default')\n"
        "    def consume(receiver, runtime_config):\n"
        "        return receiver.helper(runtime_config)\n",
    ),
)
def test_bound_method_taint_does_not_depend_on_parameter_spelling(
    tmp_path: Path, source: str,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/method_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(source, encoding="utf-8")
    route = (
        "scripts.method_reader.C.consume"
        if "def consume(receiver" in source
        else "scripts.method_reader.consume"
    )
    census = {"rows": [
        {
            "consumer_id": "authority",
            "path": "candidate/config.py",
            "public_entry_route": "candidate.config.resolve",
        },
        {
            "consumer_id": "method-reader",
            "match_kind": "CONFIGURATION_READ",
            "path": "scripts/method_reader.py",
            "public_entry_route": route,
            "source_span": {
                "start_line": 5 if ".C." in route else 6,
                "start_col": 31 if ".C." in route else 20,
                "end_line": 5 if ".C." in route else 6,
                "end_col": 45 if ".C." in route else 34,
            },
            "transitive_wrapper_chain": [route, "runtime_config"],
        },
    ]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


def test_rebound_import_cannot_masquerade_as_the_authority(tmp_path: Path) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/rebound_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "from candidate.config import resolve\n"
        "def compatibility_load(value):\n"
        "    return value.get('mode', 'default')\n"
        "def consume(runtime_config):\n"
        "    resolve = compatibility_load\n"
        "    return resolve(runtime_config)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert any(
        "scripts.rebound_reader.resolve" in path
        for trace in result["traces"]
        for path in trace["paths"]
    )


@pytest.mark.parametrize(
    "source",
    (
        "from .config import resolve\n"
        "def consume(runtime_config):\n"
        "    return resolve(runtime_config)\n",
        "def consume(runtime_config):\n"
        "    from .config import resolve\n"
        "    return resolve(runtime_config)\n",
    ),
)
def test_relative_and_local_imports_resolve_to_the_authority(
    tmp_path: Path, source: str,
) -> None:
    workspace = tmp_path / "workspace"
    path = workspace / "ptycho/consumer.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    rows = evaluator.scan_workspace_configuration_consumers(workspace)["rows"]

    graph, bypasses, _, _, _ = evaluator._module_functions(
        path,
        "ptycho.consumer",
        authority_symbols={"ptycho.config.resolve"},
        consumer_rows=rows,
    )

    assert graph["ptycho.consumer.consume"] == ["ptycho.config.resolve"]
    assert bypasses == {}


def test_taint_propagates_only_to_the_matching_callee_parameter(tmp_path: Path) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/scientific_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "class Options: pass\n"
        "def helper(data, options):\n"
        "    return data.value * getattr(options, 'scale', 1)\n"
        "def consume(runtime_config):\n"
        "    return helper(runtime_config, Options())\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True


def test_runtime_object_returned_from_a_configured_call_is_not_a_carrier(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/runtime_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "class Runtime:\n"
        "    def execute(self): return 1\n"
        "def build(runtime_config): return Runtime()\n"
        "def consume(runtime_config):\n"
        "    runtime = build(runtime_config)\n"
        "    return runtime.execute()\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True


def test_leaf_returned_from_a_configured_call_is_not_a_carrier(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/leaf_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def output_dir(runtime_config): return runtime_config.output_dir\n"
        "def consume(runtime_config):\n"
        "    path = output_dir(runtime_config)\n"
        "    return str(path)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True


def test_typed_leaf_may_be_serialized_without_becoming_a_tolerant_loader(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/serialize_leaf.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def consume(runtime_config):\n"
        "    return str(runtime_config.output_dir)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True


def test_external_result_derived_from_a_leaf_is_not_a_config_carrier(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/external_leaf.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "from pathlib import Path\n"
        "def consume(runtime_config):\n"
        "    path = Path(runtime_config.output_dir)\n"
        "    return path.exists()\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True


def test_expression_derived_from_a_leaf_is_not_a_config_carrier(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/derived_leaf.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def consume(runtime_config):\n"
        "    path = runtime_config.output_dir / 'result.json'\n"
        "    return path.exists()\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is True


def test_unverified_dynamic_runtime_method_cannot_consume_a_typed_leaf(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/runtime_method.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def consume(runtime_config, model):\n"
        "    return model.to(runtime_config.device)\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False


def test_carrier_returned_from_identity_call_remains_tainted(tmp_path: Path) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/identity_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def identity(value): return value\n"
        "def consume(runtime_config):\n"
        "    alias = identity(runtime_config)\n"
        "    return alias.get('mode', 'default')\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


def test_nested_multiline_flow_is_parsed_for_exact_bypasses(tmp_path: Path) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    path = workspace / "scripts/nested_reader.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "def consume(runtime_config):\n"
        "    if runtime_config:\n"
        "        try:\n"
        "            return strict(runtime_config)\n"
        "        except ValueError:\n"
        "            return runtime_config.get('mode', 'default')\n"
        "    return runtime_config\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}

    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )

    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


def test_workspace_detector_matches_git_detector_on_identical_tree(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    source = repository / "ptycho/config/example.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "def consume(runtime_config):\n    return runtime_config.value\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-qm", "fixture",
        ],
        cwd=repository,
        check=True,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    git_rows = scan_configuration_consumers(repository, commit)["rows"]
    workspace_rows = evaluator.scan_workspace_configuration_consumers(repository)["rows"]
    assert git_rows == workspace_rows


def test_controller_root_ignores_caller_authored_green_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert not hasattr(evaluator, "derive_complete_observations")
    assert not hasattr(evaluator, "_probe_matrix")
    assert not hasattr(evaluator, "apply_calibration_defect")
    with pytest.raises(evaluator.EvaluatorError, match="workspace"):
        evaluator._evaluate_candidate(
            calibration_cases=[],
            candidate_evidence_path=Path("missing"),
            consumer_census={"rows": []},
            output_root=Path("missing"),
            package_conformance={"validated": True},
            python_executable=Path(sys.executable),
            timeout_seconds=30,
            visible_result=_visible_result(),
            workspace=Path("missing"),
        )


def test_case_expectation_labels_cannot_green_a_nonconforming_resolver(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _mutated_protocol_workspace(
        tmp_path,
        "    return _validate(owner, resolved)\n",
        "    return {'wrong': True}\n",
    )
    case = {
        "case_id": "bad",
        "defect_kind": "none",
        "expected_failed_clauses": [],
        "probe": {
            "cli_patch": {"sample_count": 16},
            "file_mapping": {"mode": "strict", "sample_count": 8},
            "role": "TRAINING",
        },
    }
    census = {
        "rows": [{
            "consumer_id": "consumer-a",
            "path": "candidate/config.py",
            "public_entry_route": "candidate.config.resolve",
        }]
    }
    observations = evaluator._evaluate_candidate(
        calibration_cases=[case],
        candidate_evidence_path=evidence_path,
        consumer_census=census,
        output_root=tmp_path / "evaluation",
        package_conformance={
            "candidate_evidence": "candidate_config_evidence.v2",
            "probe_request": "config_resolution_probe_request.v1",
            "probe_result": "config_resolution_probe_result.v1",
            "validated": True,
        },
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        visible_result=_visible_result(),
        workspace=workspace,
    )
    assert {
        "F1-H03-PUBLIC-RESOLUTION",
        "F1-H04-TRANSACTIONAL-APPLICATION",
        "F1-H05-STRICT-INPUT-CONTRACT",
        "F1-H06-DERIVED-PUBLIC-FIELDS",
        "F1-H09-CROSS-SURFACE-COHERENCE",
    } <= _failed(observations)


def test_root_evaluation_consumes_direct_facts_and_can_green_all_ten(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    observations = evaluator._evaluate_candidate(
        calibration_cases=[{
            "case_id": "nested-precedence",
            "defect_kind": "none",
            "expected_failed_clauses": [],
            "probe": {
                "cli_patch": {"model": {"N": 128}, "n_groups": 7},
                "file_mapping": _TRAINING_ROOT_INPUT,
                "role": "TRAINING",
            },
        }],
        candidate_evidence_path=evidence_path,
        consumer_census={"rows": [{
            "consumer_id": "public-resolution",
            "path": "candidate/config.py",
            "public_entry_route": "candidate.config.resolve",
        }]},
        output_root=tmp_path / "evaluation",
        package_conformance={
            "candidate_evidence": "candidate_config_evidence.v2",
            "probe_request": "config_resolution_probe_request.v1",
            "probe_result": "config_resolution_probe_result.v1",
            "validated": True,
        },
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        visible_result=_root_visible_result(),
        workspace=workspace,
    )
    assert _failed(observations) == set()


_TRAINING_ROOT_INPUT = {
    "model": {"N": 64, "generator_output_mode": "amp_phase"},
    "n_groups": 5,
    "n_subsample": 3,
    "subsample_seed": 17,
    "enable_oversampling": True,
    "neighbor_pool_size": 5,
    "sequential_sampling": True,
}


def test_direct_resolver_protocol_derives_strict_and_validation_facts(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)

    result = evaluator.run_direct_resolver_probe(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "direct-probe",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {
        "F1-H05-STRICT-INPUT-CONTRACT": True,
        "F1-H06-DERIVED-PUBLIC-FIELDS": True,
    }
    assert [row["case_id"] for row in result["transcript"]["rows"]] == list(
        evaluator.DIRECT_RESOLVER_CASE_IDS
    )
    assert all(
        set(row) == {"case_id", "input_before", "input_after", "outcome"}
        and row["outcome"]["kind"] in {"returned", "raised"}
        for row in result["transcript"]["rows"]
    )


def test_direct_resolver_transcript_order_and_digest_tamper_fail_closed(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    result = evaluator.run_direct_resolver_probe(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "direct-probe",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )
    transcript_path = tmp_path / "direct-probe/transcript.json"
    rows = result["transcript"]["rows"]
    rows[0], rows[1] = rows[1], rows[0]
    _write_canonical(transcript_path, result["transcript"])

    with pytest.raises(evaluator.EvaluatorError, match="digest|order"):
        evaluator.load_direct_resolver_transcript(
            transcript_path,
            expected_sha256=result["transcript_sha256"],
        )


def test_direct_resolver_transcript_order_fails_with_a_fresh_digest(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    result = _run_direct_protocol(tmp_path, workspace, evidence_path)
    transcript_path = tmp_path / "direct-probe/transcript.json"
    rows = result["transcript"]["rows"]
    rows[0], rows[1] = rows[1], rows[0]
    _write_canonical(transcript_path, result["transcript"])

    with pytest.raises(evaluator.EvaluatorError, match="order"):
        evaluator.load_direct_resolver_transcript(
            transcript_path,
            expected_sha256=evaluator.file_sha256(transcript_path),
        )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            '            raise ValueError("unknown field")',
            "            if cls is RuntimeConfig:\n"
            "                continue\n"
            '            raise ValueError("unknown field")',
        ),
        (
            "        elif type(item) is not expected:",
            "        elif not isinstance(item, expected):",
        ),
        (
            "        result[key] = deepcopy(item)",
            "        if key != 'n_subsample':\n"
            "            result[key] = deepcopy(item)",
        ),
    ],
    ids=("accept-unknown", "coerce-bool", "drop-retained"),
)
def test_strict_input_defects_flip_only_h05(
    tmp_path: Path, old: str, new: str
) -> None:
    workspace, evidence_path = _mutated_protocol_workspace(tmp_path, old, new)
    facts = _run_direct_protocol(tmp_path, workspace, evidence_path)["facts"]
    assert facts["F1-H05-STRICT-INPUT-CONTRACT"] is False
    assert {clause for clause, value in facts.items() if not value} == {
        "F1-H05-STRICT-INPUT-CONTRACT"
    }


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            '            raise ValueError("invalid grid")',
            "            pass",
        ),
    ],
    ids=("accept-invalid-simulation",),
)
def test_simulation_contract_defects_flip_only_h06(
    tmp_path: Path, old: str, new: str
) -> None:
    workspace, evidence_path = _mutated_protocol_workspace(tmp_path, old, new)
    facts = _run_direct_protocol(tmp_path, workspace, evidence_path)["facts"]
    assert facts["F1-H06-DERIVED-PUBLIC-FIELDS"] is False
    assert {clause for clause, value in facts.items() if not value} == {
        "F1-H06-DERIVED-PUBLIC-FIELDS"
    }


def test_path_only_adapter_cannot_establish_direct_resolver_facts(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    (workspace / "scripts/es_f1_config_resolution_adapter.py").write_text(
        "raise RuntimeError('adapter must not run during direct probe')\n",
        encoding="utf-8",
    )
    assert all(_run_direct_protocol(tmp_path, workspace, evidence_path)["facts"].values())


def test_opaque_direct_resolver_return_fails_closed(tmp_path: Path) -> None:
    workspace, evidence_path = _mutated_protocol_workspace(
        tmp_path,
        "    return _validate(owner, resolved)",
        "    return object()",
    )
    with pytest.raises(evaluator.EvaluatorError, match="opaque"):
        _run_direct_protocol(tmp_path, workspace, evidence_path)


def test_direct_resolver_input_mutation_fails_closed(tmp_path: Path) -> None:
    workspace, evidence_path = _mutated_protocol_workspace(
        tmp_path,
        "def resolve(file_mapping, cli_patch):\n",
        "def resolve(file_mapping, cli_patch):\n"
        "    file_mapping['mutated'] = True\n",
    )
    with pytest.raises(evaluator.EvaluatorError, match="mutated probe input"):
        _run_direct_protocol(tmp_path, workspace, evidence_path)


def test_direct_resolver_transcript_authority_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    result = _run_direct_protocol(tmp_path, workspace, evidence_path)
    transcript_path = tmp_path / "direct-probe/transcript.json"
    result["transcript"]["rows"][0]["outcome"]["passed"] = True
    _write_canonical(transcript_path, result["transcript"])
    with pytest.raises(evaluator.EvaluatorError, match="outcome"):
        evaluator.load_direct_resolver_transcript(
            transcript_path,
            expected_sha256=evaluator.file_sha256(transcript_path),
        )


def test_roundtrip_uses_a_true_second_audited_process(tmp_path: Path) -> None:
    protected = tmp_path / "candidate"
    protected.mkdir()
    value = {
        "provenance": {"mode": "FILE_MAPPING"},
        "resolved": {"mode": "strict"},
    }
    observed = evaluator.fresh_process_roundtrip(
        value,
        output_root=tmp_path / "roundtrip",
        python_executable=Path(sys.executable),
        protected_workspace=protected,
        timeout_seconds=30,
    )
    assert observed == value
    assert observed is not value


def test_audited_probe_rejects_forbidden_import_and_outside_project_origin(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "candidate"
    workspace.mkdir()
    with pytest.raises(evaluator.EvaluatorError, match="forbidden import"):
        evaluator.run_candidate_probe(
            code="import ptycho.evaluation\n",
            environment={},
            label="forbidden",
            python_executable=Path(sys.executable),
            timeout_seconds=30,
            workspace=workspace,
        )
    outside = tmp_path / "outside"
    (outside / "ptycho").mkdir(parents=True)
    (outside / "ptycho/__init__.py").write_text("", encoding="utf-8")
    (outside / "ptycho/bad.py").write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(evaluator.EvaluatorError, match="outside.*origin"):
        evaluator.run_candidate_probe(
            code="import ptycho.bad\n",
            environment={"PYTHONPATH": str(outside)},
            label="outside-origin",
            python_executable=Path(sys.executable),
            timeout_seconds=30,
            workspace=workspace,
        )


def test_visible_checks_use_one_audited_subprocess_route_and_v3_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "candidate"
    tests = workspace / "tests"
    tests.mkdir(parents=True)
    (tests / "test_baseline.py").write_text(
        "def test_ok(): assert True\n"
        "def test_retired_contract(): assert False\n",
        encoding="utf-8",
    )
    (tests / "test_es_f1_config_ownership.py").write_text(
        "def test_contract(): assert True\n", encoding="utf-8"
    )
    visible_checks = {
        "invocation_order": ["PRE_EDIT_FOCUSED", "CANDIDATE_CONFIG"],
        "invocations": [
            {
                "candidate_owned": False,
                "id": "PRE_EDIT_FOCUSED",
                "required": True,
                "deselectors": list(DESELECTED_NODES),
                "selectors": list(SELECTORS),
            },
            {
                "candidate_owned": True,
                "id": "CANDIDATE_CONFIG",
                "required": True,
                "deselectors": [],
                "selectors": [CANDIDATE_SELECTOR],
            },
        ],
        "runner": {
            "argv_prefix": ["-m", "pytest", "-q", "-p", "no:cacheprovider"],
            "execution_copy_policy": "disposable-exact-extract.v1",
            "install_policy": "no-install-build-or-editable.v1",
            "mutation_policy": "verify-product-digest-before-after.v1",
            "python_executable": sys.executable,
            "python_executable_sha256": evaluator.file_sha256(Path(sys.executable)),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "required_environment": [
                {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                {"name": "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "value": "1"},
            ],
            "result_policy": "every-required-invocation-exit-zero.v1",
            "timeout_seconds": 30,
            "working_directory_policy": "external-disposable-invocation-root.v1",
        },
        "schema_version": "es_f1_visible_checks.v3",
        "task_id": "F1",
    }
    calls: list[str] = []
    original = evaluator.run_candidate_probe

    def audited(**kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(kwargs["label"])
        return original(**kwargs)

    monkeypatch.setattr(evaluator, "run_candidate_probe", audited)
    before = evaluator.directory_digest(workspace)
    result = evaluator.run_visible_checks(workspace=workspace, visible_checks=visible_checks)
    assert result["schema_version"] == "es-f1-visible-check-result.v3"
    assert result["copy_digest_before"] == result["copy_digest_after"] == before
    assert [row["invocation_id"] for row in result["invocations"]] == [
        "PRE_EDIT_FOCUSED",
        "CANDIDATE_CONFIG",
    ]
    assert all(row["exit_code"] == 0 for row in result["invocations"])
    assert result["invocations"][0]["deselectors"] == list(DESELECTED_NODES)
    assert evaluator.directory_digest(workspace) == before
    assert calls == [
        "visible invocation PRE_EDIT_FOCUSED",
        "visible invocation CANDIDATE_CONFIG",
    ]


def test_visible_check_mutation_fails_closed(tmp_path: Path) -> None:
    workspace = tmp_path / "candidate"
    tests = workspace / "tests"
    tests.mkdir(parents=True)
    (tests / "test_baseline.py").write_text(
        textwrap.dedent(
            """
            from pathlib import Path

            def test_mutates():
                Path(__file__).with_name("leak.txt").write_text("leak")
            """
        ),
        encoding="utf-8",
    )
    checks = {
        "invocation_order": ["PRE_EDIT_FOCUSED"],
        "invocations": [{
            "candidate_owned": False,
            "id": "PRE_EDIT_FOCUSED",
            "required": True,
            "deselectors": [],
            "selectors": list(SELECTORS),
        }],
        "runner": {
            "argv_prefix": ["-m", "pytest", "-q", "-p", "no:cacheprovider"],
            "execution_copy_policy": "disposable-exact-extract.v1",
            "install_policy": "no-install-build-or-editable.v1",
            "mutation_policy": "verify-product-digest-before-after.v1",
            "python_executable": sys.executable,
            "python_executable_sha256": evaluator.file_sha256(Path(sys.executable)),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "required_environment": [
                {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                {"name": "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "value": "1"},
            ],
            "result_policy": "every-required-invocation-exit-zero.v1",
            "timeout_seconds": 30,
            "working_directory_policy": "external-disposable-invocation-root.v1",
        },
        "schema_version": "es_f1_visible_checks.v3",
        "task_id": "F1",
    }
    with pytest.raises(evaluator.EvaluatorError, match="mutated"):
        evaluator.run_visible_checks(workspace=workspace, visible_checks=checks)


def test_hard_finding_schema_is_exact_v3() -> None:
    schema = json.loads(HARD_FINDING_SCHEMA.read_bytes())
    Draft202012Validator.check_schema(schema)
    finding = {
        "candidate_id": "candidate-a",
        "clause_id": "F1-H10-BYPASS-ORACLE",
        "details": "controller observation",
        "disposition": "PRODUCT_DEFECT",
        "evaluator_observation": {"evidence_digest": DIGEST, "satisfied": False},
        "schema_version": "es-f1-hard-finding.v3",
    }
    Draft202012Validator(schema).validate(finding)
    predecessor = deepcopy(finding)
    predecessor["schema_version"] = "es-f1-hard-finding.v2"
    assert list(Draft202012Validator(schema).iter_errors(predecessor))


def test_evaluator_source_contains_no_superseded_task0_or_architecture_authority() -> None:
    source = Path(evaluator.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "ARTIFACT_ERA_IDS",
        "architecture_results",
        "classify_task0_bypass_discovery",
        "lifecycle_probe_result",
        "_LEGACY_BYPASS_AUTHORITY",
    ):
        assert forbidden not in source


@pytest.mark.parametrize(
    "body",
    (
        "    if enabled:\n"
        "        from json import dumps as render\n"
        "        return render(runtime_config)\n"
        "    return None\n",
        "    try:\n"
        "        from json import dumps as render\n"
        "        return render(runtime_config)\n"
        "    except TypeError:\n"
        "        raise\n",
        "    if enabled:\n"
        "        import json\n"
        "        return json.dumps(runtime_config)\n"
        "    return None\n",
    ),
    ids=("if-suite", "try-suite", "attribute-if-suite"),
)
def test_import_dominating_call_in_same_lexical_suite_is_terminal(
    tmp_path: Path,
    body: str,
) -> None:
    path = tmp_path / "ptycho/consumer.py"
    path.parent.mkdir()
    path.write_text(
        "def consume(runtime_config, enabled=True):\n" + body,
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.consumer",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"json.dumps"}),
    )
    consumers = {f"@consumer:{row['consumer_id']}" for row in rows}

    assert consumers
    assert all("json.dumps" in graph[consumer] for consumer in consumers)
    assert evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": row["consumer_id"],
            "entry_symbol": f"@consumer:{row['consumer_id']}",
            "requires_authority": False,
        } for row in rows],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )["closed"] is True


@pytest.mark.parametrize(
    "source",
    (
        "def consume(runtime_config):\n"
        "    try:\n"
        "        import json\n"
        "    except ImportError as exc:\n"
        "        raise RuntimeError('json is required') from exc\n"
        "    return json.dumps(runtime_config)\n",
        "def consume(runtime_config):\n"
        "    try:\n"
        "        from json import dumps as render\n"
        "    except ImportError:\n"
        "        return None\n"
        "    return render(runtime_config)\n",
        "try:\n"
        "    import json\n"
        "except ImportError as exc:\n"
        "    raise RuntimeError('json is required') from exc\n"
        "def consume(runtime_config):\n"
        "    return json.dumps(runtime_config)\n",
    ),
    ids=("function-raise", "function-return", "module-raise"),
)
def test_try_import_with_terminating_handlers_dominates_following_call(
    tmp_path: Path,
    source: str,
) -> None:
    path = tmp_path / "ptycho/consumer.py"
    path.parent.mkdir()
    path.write_text(source, encoding="utf-8")
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.consumer",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"json.dumps"}),
    )

    assert rows
    assert all(
        "json.dumps" in graph[f"@consumer:{row['consumer_id']}"]
        for row in rows
    )
    assert evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": row["consumer_id"],
            "entry_symbol": f"@consumer:{row['consumer_id']}",
            "requires_authority": False,
        } for row in rows],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )["closed"] is True


def test_module_try_import_with_nested_global_mutation_fails_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ptycho/consumer.py"
    path.parent.mkdir()
    path.write_text(
        "def replacement(value):\n"
        "    return value\n"
        "try:\n"
        "    import json\n"
        "    def mutate():\n"
        "        global json\n"
        "        json = replacement\n"
        "    mutate()\n"
        "except ImportError:\n"
        "    raise\n"
        "def consume(runtime_config):\n"
        "    return json.dumps(runtime_config)\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.consumer",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"json.dumps"}),
    )

    assert rows
    assert all(
        "json.dumps" not in graph[f"@consumer:{row['consumer_id']}"]
        for row in rows
    )
    assert evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": row["consumer_id"],
            "entry_symbol": f"@consumer:{row['consumer_id']}",
            "requires_authority": False,
        } for row in rows],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )["closed"] is False


@pytest.mark.parametrize(
    "body",
    (
        "    if enabled:\n"
        "        from json import dumps as render\n"
        "    return render(runtime_config)\n",
        "    try:\n"
        "        from json import dumps as render\n"
        "    except ImportError:\n"
        "        pass\n"
        "    return render(runtime_config)\n",
        "    if enabled:\n"
        "        from json import dumps as render\n"
        "    else:\n"
        "        from pathlib import Path as render\n"
        "    return render(runtime_config)\n",
        "    if enabled:\n"
        "        from json import dumps as render\n"
        "        return render(runtime_config)\n"
        "    else:\n"
        "        from pathlib import Path as render\n"
        "        return render(runtime_config)\n",
        "    if enabled:\n"
        "        from json import dumps as render\n"
        "        render = replacement\n"
        "        return render(runtime_config)\n",
        "    if enabled:\n"
        "        from json import dumps as render\n"
        "        del render\n"
        "        return render(runtime_config)\n",
        "    if enabled:\n"
        "        import json\n"
        "    return json.dumps(runtime_config)\n",
        "    try:\n"
        "        import json\n"
        "    except ImportError:\n"
        "        pass\n"
        "    return json.dumps(runtime_config)\n",
        "    try:\n"
        "        import json\n"
        "    except ImportError:\n"
        "        if enabled:\n"
        "            raise\n"
        "    return json.dumps(runtime_config)\n",
        "    try:\n"
        "        import json\n"
        "    except ImportError:\n"
        "        raise\n"
        "    except OSError:\n"
        "        pass\n"
        "    return json.dumps(runtime_config)\n",
        "    try:\n"
        "        import json\n"
        "    except* ImportError:\n"
        "        raise\n"
        "    return json.dumps(runtime_config)\n",
        "    try:\n"
        "        import json\n"
        "    except ImportError:\n"
        "        raise\n"
        "    finally:\n"
        "        enabled = False\n"
        "    return json.dumps(runtime_config)\n",
        "    try:\n"
        "        import json\n"
        "        json = replacement\n"
        "    except ImportError:\n"
        "        raise\n"
        "    return json.dumps(runtime_config)\n",
        "    try:\n"
        "        import json\n"
        "        del json\n"
        "    except ImportError:\n"
        "        raise\n"
        "    return json.dumps(runtime_config)\n",
        "    for _ in range(1):\n"
        "        try:\n"
        "            import json\n"
        "        except ImportError:\n"
        "            continue\n"
        "        return json.dumps(runtime_config)\n"
        "    return None\n",
        "    try:\n"
        "        from json import dumps as render\n"
        "        def mutate():\n"
        "            nonlocal render\n"
        "            render = replacement\n"
        "        mutate()\n"
        "    except ImportError:\n"
        "        raise\n"
        "    return render(runtime_config)\n",
        "    if enabled:\n"
        "        from json import dumps as render\n"
        "        class Mutate:\n"
        "            nonlocal render\n"
        "            render = replacement\n"
        "        return render(runtime_config)\n",
        "    if enabled:\n"
        "        from json import dumps as render\n"
        "        def mutate():\n"
        "            nonlocal render\n"
        "            render = replacement\n"
        "        mutate()\n"
        "        return render(runtime_config)\n",
    ),
    ids=(
        "outside-if",
        "continuing-except",
        "conflicting-branch-join",
        "conflicting-branch-calls",
        "rebind",
        "delete",
        "attribute-outside-if",
        "attribute-continuing-except",
        "conditional-handler",
        "mixed-handlers",
        "try-star",
        "finally-effect",
        "try-rebind",
        "try-delete",
        "continuing-handler",
        "try-nonlocal-rebind",
        "nested-class-nonlocal-rebind",
        "invoked-closure-nonlocal-rebind",
    ),
)
def test_nested_import_without_local_dominance_fails_closed(
    tmp_path: Path,
    body: str,
) -> None:
    path = tmp_path / "ptycho/consumer.py"
    path.parent.mkdir()
    path.write_text(
        "def replacement(value):\n"
        "    return value\n"
        "def consume(runtime_config, enabled=True):\n"
        + body,
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.consumer",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"json.dumps", "pathlib.Path"}),
    )
    consumers = {f"@consumer:{row['consumer_id']}" for row in rows}

    assert consumers
    assert all(
        not {"json.dumps", "pathlib.Path"} & set(graph[consumer])
        for consumer in consumers
    )
    assert evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": row["consumer_id"],
            "entry_symbol": f"@consumer:{row['consumer_id']}",
            "requires_authority": False,
        } for row in rows],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )["closed"] is False


def test_optional_module_import_does_not_dominate_function_attribute_call(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ptycho/consumer.py"
    path.parent.mkdir()
    path.write_text(
        "if False:\n"
        "    import json\n"
        "def consume(runtime_config):\n"
        "    return json.dumps(runtime_config)\n",
        encoding="utf-8",
    )
    rows = evaluator.scan_workspace_configuration_consumers(tmp_path)["rows"]
    graph, bypasses, _, terminals, _ = evaluator._module_functions(
        path,
        "ptycho.consumer",
        authority_symbols={"candidate.config.resolve"},
        consumer_rows=rows,
        workspace_module_roots=frozenset({"ptycho"}),
        available_external_imports=frozenset({"json.dumps"}),
    )

    assert evaluator.walk_consumer_routes(
        consumer_rows=[{
            "consumer_id": row["consumer_id"],
            "entry_symbol": f"@consumer:{row['consumer_id']}",
            "requires_authority": False,
        } for row in rows],
        call_graph=graph,
        authority_symbols={"candidate.config.resolve"},
        bypass_symbols=bypasses,
        terminal_symbols=terminals,
    )["closed"] is False
