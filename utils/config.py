"""Shared configuration loader."""
import os
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
DATA_DIR = PROJECT_ROOT / "data"


def load_config():
    """Load config.yaml with ${ENV_VAR} substitution.
    Falls back to config.example.yaml (used in CI where config.yaml is gitignored)."""
    path = CONFIG_PATH if CONFIG_PATH.exists() else PROJECT_ROOT / "config.example.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Config not found at {CONFIG_PATH}. "
            "Copy config.example.yaml to config.yaml and edit it."
        )
    text = path.read_text()
    for key, val in os.environ.items():
        text = text.replace(f"${{{key}}}", val)
    return yaml.safe_load(text)


def ensure_dirs():
    """Create data directories if needed."""
    for sub in ("raw", "scored", "curated"):
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def today_str():
    """Today's date as YYYY-MM-DD."""
    from datetime import date
    return date.today().isoformat()
