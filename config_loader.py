"""Shared configuration loader for ultrastar2singIt.

Reads config_default.yml and config.yml, merges them,
and returns a Munch object for dot-access.
"""

import yaml
from pathlib import Path
from typing import Optional, Union
from munch import Munch, munchify


def deep_override_config(default: dict, override: dict) -> dict:
    """Recursively merge *override* into *default*, skipping None values."""
    merged = dict(default)
    for key, override_value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(override_value, dict)
        ):
            merged[key] = deep_override_config(merged[key], override_value)
        elif override_value is not None:
            merged[key] = override_value
    return merged


def load_config(base_dir: Optional[Union[str, Path]] = None) -> Munch:
    """Load and merge config_default.yml + config.yml from *base_dir*.

    Parameters
    ----------
    base_dir : path-like, optional
        Directory containing the YAML files.  Defaults to the directory
        that contains *this* source file (i.e. the project root).

    Returns
    -------
    Munch
        Merged configuration with dot-access.
    """
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent
    else:
        base_dir = Path(base_dir)

    default_path = base_dir / "config_default.yml"
    user_path = base_dir / "config.yml"

    with open(default_path, "r", encoding="utf-8") as f:
        config_default = yaml.safe_load(f) or {}

    if user_path.exists():
        with open(user_path, "r", encoding="utf-8") as f:
            config_user = yaml.safe_load(f) or {}
    else:
        config_user = {}

    merged = deep_override_config(config_default, config_user)
    return munchify(merged)

