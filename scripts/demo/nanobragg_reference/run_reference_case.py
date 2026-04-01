#!/usr/bin/env python3
"""Run the offline nanoBragg reference harness on one visible fixture."""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HARNESS_DIR = Path(__file__).resolve().parent
HARNESS_C = HARNESS_DIR / "reference_harness.c"
HARNESS_SO = HARNESS_DIR / "reference_harness.so"
HEADER = HARNESS_DIR / "reference_types.h"
REFERENCE_SOURCE = ROOT.parent / "nanoBragg" / "golden_suite_generator" / "nanoBragg.c"


class ReferenceFixture(ctypes.Structure):
    _fields_ = [
        ("spixels", ctypes.c_int),
        ("fpixels", ctypes.c_int),
        ("subpixel_steps", ctypes.c_int),
        ("detector_thicksteps", ctypes.c_int),
        ("oversample_omega", ctypes.c_int),
        ("oversample_thick", ctypes.c_int),
        ("n_sources", ctypes.c_int),
        ("n_phi_values", ctypes.c_int),
        ("n_mosaic_domains", ctypes.c_int),
        ("subpixel_size", ctypes.c_double),
        ("pixel_size", ctypes.c_double),
        ("close_distance", ctypes.c_double),
        ("thickness", ctypes.c_double),
        ("mu", ctypes.c_double),
        ("detector_origin", ctypes.c_double * 3),
        ("fast_axis", ctypes.c_double * 3),
        ("slow_axis", ctypes.c_double * 3),
    ]


class ReferenceSource(ctypes.Structure):
    _fields_ = [
        ("direction", ctypes.c_double * 3),
        ("wavelength", ctypes.c_double),
        ("weight", ctypes.c_double),
    ]


class ReferenceMosaicDomain(ctypes.Structure):
    _fields_ = [("weight", ctypes.c_double)]


def _compile_harness() -> Path:
    if HARNESS_SO.exists() and HARNESS_SO.stat().st_mtime >= max(HARNESS_C.stat().st_mtime, HEADER.stat().st_mtime):
        return HARNESS_SO
    subprocess.run(
        ["cc", "-shared", "-fPIC", "-O2", str(HARNESS_C), "-lm", "-o", str(HARNESS_SO)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return HARNESS_SO


def _triple(values: list[float]) -> ctypes.Array[ctypes.c_double]:
    return (ctypes.c_double * 3)(*values)


def run_reference_case(fixture_path: Path) -> dict[str, object]:
    fixture = json.loads(fixture_path.read_text())
    so_path = _compile_harness()
    lib = ctypes.CDLL(str(so_path))
    lib.accumulate_reference_image.argtypes = [
        ctypes.POINTER(ReferenceFixture),
        ctypes.POINTER(ReferenceSource),
        ctypes.POINTER(ReferenceMosaicDomain),
        ctypes.POINTER(ctypes.c_double),
    ]
    lib.accumulate_reference_image.restype = ctypes.c_int

    sources = [
        ReferenceSource(
            direction=_triple(source["direction"]),
            wavelength=source["wavelength"],
            weight=source["weight"],
        )
        for source in fixture["sources"]
    ]
    domains = [
        ReferenceMosaicDomain(weight=domain["weight"])
        for domain in fixture["mosaic_domains"]
    ]

    fixture_struct = ReferenceFixture(
        spixels=fixture["detector"]["spixels"],
        fpixels=fixture["detector"]["fpixels"],
        subpixel_steps=fixture["oversample"]["subpixel_steps"],
        detector_thicksteps=fixture["oversample"]["detector_thicksteps"],
        oversample_omega=int(fixture["oversample"]["oversample_omega"]),
        oversample_thick=int(fixture["oversample"]["oversample_thick"]),
        n_sources=len(sources),
        n_phi_values=len(fixture["phi_values"]),
        n_mosaic_domains=len(domains),
        subpixel_size=fixture["detector"]["subpixel_size"],
        pixel_size=fixture["detector"]["pixel_size"],
        close_distance=fixture["detector"]["close_distance"],
        thickness=fixture["geometry"]["thickness"],
        mu=fixture["geometry"]["mu"],
        detector_origin=_triple(fixture["geometry"]["detector_origin"]),
        fast_axis=_triple(fixture["geometry"]["fast_axis"]),
        slow_axis=_triple(fixture["geometry"]["slow_axis"]),
    )

    source_array = (ReferenceSource * len(sources))(*sources)
    domain_array = (ReferenceMosaicDomain * len(domains))(*domains)
    out_size = fixture_struct.spixels * fixture_struct.fpixels
    out_image = (ctypes.c_double * out_size)()
    rc = lib.accumulate_reference_image(
        ctypes.byref(fixture_struct),
        source_array,
        domain_array,
        out_image,
    )
    if rc != 0:
        raise RuntimeError(f"reference harness returned status {rc}")

    return {
        "case_id": fixture["case_id"],
        "shape": [fixture_struct.spixels, fixture_struct.fpixels],
        "dtype": "float64",
        "flat_data": list(out_image),
        "reference_method": "offline_reference_harness",
        "reference_source": str(REFERENCE_SOURCE),
        "reference_snapshot": "scoped-simplified-harness-v1",
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(json.dumps({"error": "usage: run_reference_case.py <fixture.json>"}))
        return 2
    payload = run_reference_case(Path(argv[0]))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
