#!/usr/bin/env python3
from __future__ import annotations

import ctypes
import json
import os
import struct
import sys
import tempfile
from pathlib import Path

from build_harness import build_harness


ROOT = Path(__file__).resolve().parents[3]
LIBC = ctypes.CDLL(None)


def _make_argv(case: dict[str, object], tmpdir: Path) -> list[str]:
    argv = [str(item) for item in case["argv"]]
    float_path = tmpdir / "floatimage.bin"
    int_path = tmpdir / "intimage.img"
    noise_path = tmpdir / "noiseimage.img"
    pgm_path = tmpdir / "image.pgm"
    argv.extend(
        [
            "-floatfile",
            str(float_path),
            "-intfile",
            str(int_path),
            "-noisefile",
            str(noise_path),
            "-pgmfile",
            str(pgm_path),
            "-nopgm",
            "-nonoise",
            "-noprogress",
        ]
    )
    return argv


def run_reference_case(fixture_path: Path) -> dict[str, object]:
    case = json.loads(fixture_path.read_text())
    so_path = build_harness()
    lib = ctypes.CDLL(str(so_path))
    lib.nanobragg_run.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]
    lib.nanobragg_run.restype = ctypes.c_int

    with tempfile.TemporaryDirectory(prefix="nanobragg-entrypoint-ref-") as tmp:
        tmpdir = Path(tmp)
        argv = _make_argv(case, tmpdir)
        argv_bytes = [b"nanobragg"] + [arg.encode("utf-8") for arg in argv]
        argc = len(argv_bytes)
        argv_array = (ctypes.c_char_p * argc)(*argv_bytes)

        old_cwd = Path.cwd()
        stdout_fd = os.dup(1)
        stderr_fd = os.dup(2)
        null_fd = os.open(os.devnull, os.O_WRONLY)
        try:
            os.chdir(tmpdir)
            os.dup2(null_fd, 1)
            os.dup2(null_fd, 2)
            rc = lib.nanobragg_run(argc, argv_array)
        finally:
            LIBC.fflush(None)
            os.dup2(stdout_fd, 1)
            os.dup2(stderr_fd, 2)
            os.close(stdout_fd)
            os.close(stderr_fd)
            os.close(null_fd)
            os.chdir(old_cwd)

        if rc != 0:
            raise RuntimeError(f"nanobragg_run returned status {rc}")

        float_path = tmpdir / "floatimage.bin"
        if not float_path.is_file():
            raise FileNotFoundError(f"expected float output not found: {float_path}")

        raw = float_path.read_bytes()
        elem_count = case["output_shape"][0] * case["output_shape"][1]
        values = list(struct.unpack(f"{elem_count}f", raw[: elem_count * 4]))

    return {
        "case_id": case["case_id"],
        "shape": case["output_shape"],
        "dtype": "float32",
        "flat_data": values,
        "reference_method": "nanobragg_main_wrapper",
        "reference_source": str(ROOT.parent / "nanoBragg" / "golden_suite_generator" / "nanoBragg.c"),
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
