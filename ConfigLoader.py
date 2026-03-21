import sys
import yaml
from pathlib import Path
from typing import Optional, Union
from munch import Munch, munchify

def plugins_dir() -> Path:
    return app_dir() / "plugins"

def bundle_dir() -> Path:
    if getattr(sys, '_MEIPASS', None):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


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

def load_default_config() -> Munch:
    default_path = bundle_dir() / "config_default.yml"
    with open(default_path, "r", encoding="utf-8") as f:
        config_default = yaml.safe_load(f) or {}
    return munchify(config_default)


def load_config(base_dir: Optional[Union[str, Path]] = None) -> Munch:
    default_path = bundle_dir() / "config_default.yml"

    if base_dir is not None:
        user_path = Path(base_dir) / "config.yml"
    else:
        user_path = app_dir() / "config.yml"

    with open(default_path, "r", encoding="utf-8") as f:
        config_default = yaml.safe_load(f) or {}

    if user_path.exists():
        with open(user_path, "r", encoding="utf-8") as f:
            config_user = yaml.safe_load(f) or {}
    else:
        config_user = {}

    merged = deep_override_config(config_default, config_user)
    return munchify(merged)