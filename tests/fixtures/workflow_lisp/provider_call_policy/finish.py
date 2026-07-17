"""Fail until resumed, then write the declared typed result bundle only."""

from __future__ import annotations

import json
import os
from pathlib import Path


if not Path("finish.marker").is_file():
    raise SystemExit(17)

bundle_path = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
bundle_path.parent.mkdir(parents=True, exist_ok=True)
bundle_path.write_text(
    json.dumps({"approved": True, "summary": "resumed command"}) + "\n",
    encoding="utf-8",
)
