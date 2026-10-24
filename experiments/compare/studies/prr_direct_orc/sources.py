"""Study-local source rendering for the bounded PRR pilot."""

import json
from pathlib import Path
import shutil


_COPIED_FILES = ("common.orc", "providers.json")
_RENDERED_FILES = ("direct.orc", "implement_check_diagnose_repair.orc", "commands.json")


def render_sources(destination, python_executable, trusted_check_path):
    """Copy the fixed sources and bind only the interpreter and trusted command path."""
    source = Path(__file__).resolve().parent
    target = Path(destination).resolve()
    if target == source:
        raise ValueError("render destination must differ from the frozen source snapshot")
    trusted = Path(trusted_check_path).resolve(strict=True)
    if trusted != source / "trusted_check.py":
        raise ValueError("trusted_check_path must name the frozen source snapshot helper")
    dev_check = source / "dev_check.py"
    if not dev_check.is_file():
        raise ValueError("the frozen source snapshot is missing dev_check.py")
    target.mkdir(parents=True, exist_ok=True)
    python = str(Path(python_executable).resolve(strict=True))
    for name in _COPIED_FILES:
        shutil.copyfile(source / name, target / name)
    replacements = {
        '"__PYTHON__"': json.dumps(python),
        '"__TRUSTED_CHECK__"': json.dumps(str(trusted)),
        '"__DEV_CHECK__"': json.dumps(str(dev_check)),
    }
    for name in _RENDERED_FILES:
        rendered = (source / name).read_text()
        for old, new in replacements.items():
            rendered = rendered.replace(old, new)
        if "__PYTHON__" in rendered or "__TRUSTED_CHECK__" in rendered or "__DEV_CHECK__" in rendered:
            raise ValueError(f"unrendered source placeholder in {name}")
        (target / name).write_text(rendered)
    return {
        "source_root": target,
        "direct": target / "direct.orc",
        "orc": target / "implement_check_diagnose_repair.orc",
        "providers": target / "providers.json",
        "commands": target / "commands.json",
    }
