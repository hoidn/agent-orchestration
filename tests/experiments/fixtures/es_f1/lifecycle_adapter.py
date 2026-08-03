from __future__ import annotations

import argparse
import json
import os
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
request = json.loads(request_path.read_bytes())
candidate_id = request["candidate_id"]
scenario = candidate_id.removeprefix("calibration-")
os.chdir(Path(__file__).resolve().parent)
evidence = json.loads(
    (request_path.parent / request["candidate_evidence_path"]).read_bytes()
)
if evidence["candidate_id"] != candidate_id:
    raise RuntimeError("request-root candidate evidence identity drifted")

if scenario == "mutate-copy":
    Path("product.txt").write_text("mutated\n", encoding="utf-8")
elif scenario == "forbidden-import":
    __import__("ptycho.evaluation")
elif scenario == "forbidden-path":
    Path("/home/ollie/Documents/PtychoPINN/README.md").read_bytes()

result_root = Path(args.result).parent
output = result_root / request["lifecycle_output_dir"]
output.mkdir(parents=True)
artifacts: dict[str, dict[str, str]] = {}
for role in ("representative", "witness"):
    checkpoint = output / f"{role}.ckpt"
    bundle = output / f"{role}.zip"
    checkpoint.write_bytes(b"calibration checkpoint\n")
    bundle.write_bytes(b"calibration bundle\n")
    artifacts[role] = {
        "bundle_path": bundle.relative_to(result_root).as_posix(),
        "checkpoint_path": checkpoint.relative_to(result_root).as_posix(),
    }

result = {
    "artifacts": artifacts,
    "candidate_id": candidate_id,
    "operation_version": "wrong.v1"
    if scenario == "operation-drift"
    else request["operation_version"],
    "schema_version": "lifecycle_probe_result.v2",
}
if scenario == "pass-bit":
    result["passed"] = True
Path(args.result).write_bytes(canonical_json_bytes(result))
