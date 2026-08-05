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
evidence = json.loads(
    (input_root / request["candidate_evidence_path"]).read_bytes()
)

output = result_path.parent / request["lifecycle_output_dir"]
output.mkdir(parents=True)
execution = PyTorchExecutionConfig(
    accelerator="cpu",
    deterministic=True,
    num_workers=0,
    enable_progress_bar=False,
    enable_checkpointing=False,
    logger_backend=None,
)
declarations = [
    *evidence["builtin_architectures"],
    evidence["candidate_witness"],
]
architecture_results: list[dict[str, str]] = []
for ordinal, (declaration, architecture_case) in enumerate(
    zip(declarations, request["architecture_cases"], strict=True),
    start=1,
):
    architecture = architecture_case["architecture_id"]
    if declaration["public_id"] != architecture:
        raise RuntimeError("candidate evidence/request architecture join drifted")
    base = json.loads(
        (input_root / architecture_case["config"]["path"]).read_bytes()
    )
    fixture = json.loads(
        (input_root / architecture_case["input"]["path"]).read_bytes()
    )
    architecture_output = output / f"{ordinal:02d}-{architecture}"
    rng = np.random.default_rng(fixture["seed"])
    diffraction = rng.random(
        (fixture["sample_count"], fixture["image_size"], fixture["image_size"]),
        dtype=np.float32,
    )
    probe_guess = np.ones(
        (fixture["image_size"], fixture["image_size"]), dtype=np.complex64
    )
    data_path = architecture_output / "train.npz"
    data_path.parent.mkdir(parents=True, exist_ok=True)
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
    structural = {
        row["name"]: row["baseline_value"]
        for row in architecture_case["structural_fields"]
    }
    common = {name: value for name, value in base.items() if name != "schema_version"}
    adapter_architecture = (
        "ffno"
        if ordinal == 15 and scenario == "missing_persisted_builder"
        else architecture
    )
    checkpoint_structural = dict(structural)
    bundle_structural = dict(structural)
    if ordinal == 15 and scenario == "checkpoint_field_loss":
        checkpoint_structural = {
            row["name"]: row["alternate_value"]
            for row in architecture_case["structural_fields"]
        }
    if ordinal == 15 and scenario == "bundle_field_loss":
        bundle_structural = {
            row["name"]: row["alternate_value"]
            for row in architecture_case["structural_fields"]
        }
    checkpoint_overrides = {
        **common,
        **checkpoint_structural,
        "architecture": adapter_architecture,
    }
    checkpoint_payload = create_training_payload(
        data_path,
        architecture_output / "checkpoint-configuration",
        overrides=checkpoint_overrides,
        execution_config=execution,
    )
    model = build_ptychopinn_application(
        checkpoint_payload.model_spec,
        checkpoint_payload.pt_data_config,
        checkpoint_payload.pt_training_config,
        checkpoint_payload.pt_inference_config,
    )
    checkpoint = architecture_output / "model.ckpt"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    trainer = Trainer(
        max_epochs=0,
        enable_checkpointing=True,
        logger=False,
        enable_progress_bar=False,
        accelerator="cpu",
        default_root_dir=architecture_output,
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
        architecture_output / "training",
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
        overrides=bundle_overrides,
    )
    bundle = Path(bundle_payload.tf_training_config.output_dir) / "wts.h5.zip"
    architecture_results.append({
        "architecture_id": architecture,
        "bundle_path": bundle.relative_to(result_path.parent).as_posix(),
        "checkpoint_path": checkpoint.relative_to(result_path.parent).as_posix(),
    })

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
