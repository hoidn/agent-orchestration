from __future__ import annotations

import argparse
import dataclasses
import enum
import importlib
import json
from pathlib import Path


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        + b"\n"
    )


def normalize(value: object) -> object:
    if isinstance(value, enum.Enum):
        return normalize(value.value)
    if isinstance(value, Path):
        return value.as_posix()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: normalize(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(key): normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    return value


def load_mapping(root: Path, binding: dict[str, str]) -> dict[str, object]:
    value = json.loads((root / binding["path"]).read_bytes())
    if not isinstance(value, dict):
        raise RuntimeError("probe input is not a mapping")
    return value


def resolve_symbol(symbol: str):
    module_name, _, name = symbol.rpartition(".")
    if not module_name or not name:
        raise RuntimeError("resolver symbol is not importable")
    return getattr(importlib.import_module(module_name), name)


parser = argparse.ArgumentParser()
parser.add_argument("--request", required=True)
parser.add_argument("--result", required=True)
args = parser.parse_args()
request_path = Path(args.request)
result_path = Path(args.result)
request = json.loads(request_path.read_bytes())
input_root = request_path.parent
evidence = json.loads(
    (input_root / request["candidate_evidence_path"]).read_bytes()
)
symbols = {
    role: route["symbol"]
    for route in evidence["public_resolution_routes"]
    for role in route["roles"]
}
rows = []
for case in request["probe_cases"]:
    resolved = resolve_symbol(symbols[case["role"]])(
        load_mapping(input_root, case["file_mapping"]),
        load_mapping(input_root, case["cli_patch"]),
    )
    artifact = result_path.parent / "artifacts" / f"{case['case_id']}.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(canonical({"resolved": normalize(resolved)}))
    rows.append(
        {
            "case_id": case["case_id"],
            "resolved_record_path": artifact.relative_to(result_path.parent).as_posix(),
        }
    )
result_path.write_bytes(
    canonical(
        {
            "candidate_id": request["candidate_id"],
            "operation_version": request["operation_version"],
            "probe_results": rows,
            "schema_version": "config_resolution_probe_result.v1",
        }
    )
)
