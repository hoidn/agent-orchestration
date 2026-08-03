from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import torch
from lightning.pytorch import Trainer

from ptycho.config.config import PyTorchExecutionConfig
from ptycho.raw_data import RawData
from ptycho_torch.application_factory import build_ptychopinn_application
from ptycho_torch.config_factory import create_training_payload
from ptycho_torch.workflows.components import run_cdi_example_torch


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
os.chdir(Path(__file__).resolve().parent)
scenario = request["candidate_id"].removeprefix("calibration-")
if scenario == "copy_mutation":
    Path("README.md").write_text("calibration mutation\n", encoding="utf-8")
elif scenario == "forbidden_import":
    __import__("ptycho.evaluation")
input_root = request_path.parent
base = json.loads(
    (input_root / request["evaluator_inputs"]["base_config"]["path"]).read_bytes()
)
fixture = json.loads(
    (input_root / request["evaluator_inputs"]["cdi_fixture"]["path"]).read_bytes()
)
evidence = json.loads(
    (input_root / request["candidate_evidence_path"]).read_bytes()
)

output = result_path.parent / request["lifecycle_output_dir"]
output.mkdir(parents=True)
rng = np.random.default_rng(fixture["seed"])
diffraction = rng.random(
    (fixture["sample_count"], fixture["image_size"], fixture["image_size"]),
    dtype=np.float32,
)
probe_guess = np.ones(
    (fixture["image_size"], fixture["image_size"]), dtype=np.complex64
)
data_path = output / "train.npz"
np.savez(data_path, diffraction=diffraction, probeGuess=probe_guess)
coords = np.arange(fixture["sample_count"], dtype=np.float64)
raw_data = RawData(
    xcoords=coords,
    ycoords=coords,
    xcoords_start=coords,
    ycoords_start=coords,
    diff3d=diffraction,
    probeGuess=probe_guess,
    scan_index=np.arange(fixture["sample_count"], dtype=int),
)
execution = PyTorchExecutionConfig(
    accelerator="cpu",
    deterministic=True,
    num_workers=0,
    enable_progress_bar=False,
    enable_checkpointing=False,
    logger_backend=None,
)
structural = {
    row["name"]: row["baseline_value"] for row in evidence["structural_fields"]
}
common = {name: value for name, value in base.items() if name != "schema_version"}
artifacts: dict[str, dict[str, str]] = {}
for role, architecture in (
    ("representative", request["representative_architecture"]),
    ("witness", request["witness_architecture"]),
):
    role_output = output / role
    adapter_architecture = (
        "ffno"
        if role == "witness" and scenario == "missing_persisted_builder"
        else architecture
    )
    checkpoint_structural = dict(structural)
    bundle_structural = dict(structural)
    if role == "witness" and scenario == "checkpoint_field_loss":
        checkpoint_structural = {
            row["name"]: row["alternate_value"]
            for row in evidence["structural_fields"]
        }
    if role == "witness" and scenario == "bundle_field_loss":
        bundle_structural = {
            row["name"]: row["alternate_value"]
            for row in evidence["structural_fields"]
        }
    checkpoint_overrides = {
        **common,
        **checkpoint_structural,
        "architecture": adapter_architecture,
    }
    checkpoint_payload = create_training_payload(
        data_path,
        role_output / "checkpoint-configuration",
        overrides=checkpoint_overrides,
        execution_config=execution,
    )
    model = build_ptychopinn_application(
        checkpoint_payload.model_spec,
        checkpoint_payload.pt_data_config,
        checkpoint_payload.pt_training_config,
        checkpoint_payload.pt_inference_config,
    )
    checkpoint = role_output / "model.ckpt"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    trainer = Trainer(
        max_epochs=0,
        enable_checkpointing=True,
        logger=False,
        enable_progress_bar=False,
        accelerator="cpu",
        default_root_dir=role_output,
    )
    trainer.strategy._lightning_module = model
    trainer.save_checkpoint(checkpoint)
    bundle_overrides = {
        **common,
        **bundle_structural,
        "architecture": adapter_architecture,
    }
    bundle_payload = create_training_payload(
        data_path,
        role_output / "training",
        overrides=bundle_overrides,
        execution_config=execution,
    )
    torch.manual_seed(request["seed"])
    run_cdi_example_torch(
        raw_data,
        None,
        bundle_payload.tf_training_config,
        do_stitching=False,
        execution_config=execution,
        overrides={
            "scale_contract_version": base["scale_contract_version"],
            "measurement_domain": base["measurement_domain"],
        },
    )
    bundle = Path(bundle_payload.tf_training_config.output_dir) / "wts.h5.zip"
    artifacts[role] = {
        "bundle_path": bundle.relative_to(result_path.parent).as_posix(),
        "checkpoint_path": checkpoint.relative_to(result_path.parent).as_posix(),
    }

result_path.write_bytes(
    canonical_json_bytes(
        {
            "artifacts": artifacts,
            "candidate_id": request["candidate_id"],
            "operation_version": request["operation_version"],
            "schema_version": "lifecycle_probe_result.v2",
        }
    )
)
