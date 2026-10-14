"""Read-only historical resource-transition audit helpers."""

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

def transition_audit_file_digest(audit_path: Path) -> str | None:
    """Return the current audit-file digest when the audit file exists."""

    if not audit_path.exists():
        return None
    return f"sha256:{sha256(audit_path.read_bytes()).hexdigest()}"

def read_transition_audit_rows(audit_path: Path) -> list[dict[str, Any]]:
    """Return the parsed audit rows for one transition audit log."""

    return _read_audit_rows(audit_path)

def _read_audit_rows(audit_path: Path) -> list[dict[str, Any]]:
    if not audit_path.exists():
        return []
    return [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
