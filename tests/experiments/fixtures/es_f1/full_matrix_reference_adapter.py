from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


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
declarations = [
    *evidence["builtin_architectures"],
    evidence["candidate_witness"],
]
cases = request["architecture_cases"]
if [row["public_id"] for row in declarations] != [
    row["architecture_id"] for row in cases
]:
    raise RuntimeError("reference adapter architecture join drifted")

output = result_path.parent / request["lifecycle_output_dir"]
output.mkdir(parents=True)
architecture_results: list[dict[str, str]] = []
for ordinal, case in enumerate(cases, start=1):
    architecture_id = case["architecture_id"]
    for binding_name in ("config", "input"):
        binding = case[binding_name]
        payload = (input_root / binding["path"]).read_bytes()
        if "sha256:" + hashlib.sha256(payload).hexdigest() != binding["sha256"]:
            raise RuntimeError("reference adapter evaluator input digest drifted")
    architecture_output = output / f"{ordinal:02d}-{architecture_id}"
    architecture_output.mkdir(parents=True)
    paths: dict[str, Path] = {}
    for kind, filename in (
        ("checkpoint", "model.ckpt"),
        ("bundle", "wts.h5.zip"),
    ):
        path = architecture_output / filename
        path.write_bytes(
            canonical_json_bytes(
                {
                    "architecture_id": architecture_id,
                    "artifact_kind": kind,
                    "ordinal": ordinal,
                    "schema_version": "es-f1-reference-path-artifact.v1",
                }
            )
        )
        paths[kind] = path
    architecture_results.append(
        {
            "architecture_id": architecture_id,
            "bundle_path": paths["bundle"].relative_to(result_path.parent).as_posix(),
            "checkpoint_path": paths["checkpoint"]
            .relative_to(result_path.parent)
            .as_posix(),
        }
    )

result_path.write_bytes(
    canonical_json_bytes(
        {
            "architecture_results": architecture_results,
            "candidate_id": request["candidate_id"],
            "operation_version": request["operation_version"],
            "schema_version": "lifecycle_probe_result.v3",
        }
    )
)
