"""Atomically publish the latest shared chess text and return a typed Bool."""

import json
import os
from pathlib import Path
import sys
import tempfile


def main() -> None:
    try:
        request = json.loads(Path(sys.argv[-1]).read_text(encoding="utf-8"))
        if type(request) is not dict or set(request) != {"board", "path"}:
            raise ValueError("expected board and path fields")
        board, path = request["board"], Path(request["path"])
        if not isinstance(board, str) or not isinstance(request["path"], str):
            raise ValueError("board and path must be strings")
        if path.is_absolute() or ".." in path.parts or path.parts[:2] != ("artifacts", "agent_chess"):
            raise ValueError("path must stay under artifacts/agent_chess")

        workspace = Path.cwd().resolve()
        board_root = (workspace / "artifacts" / "agent_chess").resolve()
        target = (workspace / path).resolve()
        board_root.relative_to(workspace)
        target.relative_to(board_root)
        if target == board_root:
            raise ValueError("path must name a file under artifacts/agent_chess")
        target.parent.mkdir(parents=True, exist_ok=True)

        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=target.parent,
                prefix=f".{target.name}.", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(board)
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

        Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("true\n", encoding="utf-8")
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"write_board: {exc}") from exc


if __name__ == "__main__":
    main()
