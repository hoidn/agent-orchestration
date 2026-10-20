"""Candidate source metrics shared by recording and closed-site allocation evidence."""

from pathlib import Path

from experiments.orc_structural_search import ledger
from experiments.orc_structural_search.candidates import _exported_names, _parent_forms, _split_forms
from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.python_metrics import python_provider_allocation, python_skeleton_hash
from experiments.orc_structural_search.records import provider_allocation, skeleton_hash


def is_python(config: ExperimentConfig) -> bool:
    """An I3 entry module is Python; this selection is shared by metrics and launch."""
    return ledger.entry_of(Path(), config)[0].suffix == ".py"


def mutable_source(root: Path, config: ExperimentConfig) -> str:
    suffix = ".py" if is_python(config) else ".orc"
    return "\n".join((root / name).read_text() for name in config.mutable_files if name.endswith(suffix))


def skeleton(root: Path, config: ExperimentConfig) -> str:
    """The skeleton hash of the mutable definitions; prompts contribute nothing (records.skeleton_hash, for an I3
    module python_metrics.python_skeleton_hash)."""
    hash_of = python_skeleton_hash if is_python(config) else skeleton_hash
    options = {"module_entry": config.entry_workflow} if config.condition == "module" and not is_python(config) else {}
    return hash_of(mutable_source(root, config), definitions=metric_definitions(root, config), **options)


def allocation(root: Path, config: ExperimentConfig) -> dict[str, list[str]]:
    """The provider externs (an I3 module: provider keys) each non-prompt mutable definition names, in source
    order."""
    allocate = python_provider_allocation if is_python(config) else provider_allocation
    options = {"module_entry": config.entry_workflow} if config.condition == "module" and not is_python(config) else {}
    return allocate(mutable_source(root, config), definitions=metric_definitions(root, config), **options)


def metric_definitions(root: Path, config: ExperimentConfig) -> tuple[str, ...]:
    """Module metrics include the entry first, then every private declaration in source order."""
    if config.condition != "module" or is_python(config):
        return config.mutable_definitions
    entry = config.entry_workflow.split("::")[1]
    names = [entry]
    for name in config.mutable_files:
        if name.endswith(".orc"):
            forms = _parent_forms(root / name)
            exported = _exported_names(forms)
            names.extend(name for _, name in _split_forms(forms, whole_module=True)[1]
                         if name != entry and name not in exported)
    return tuple(names)


