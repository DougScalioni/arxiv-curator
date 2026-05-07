"""Shared configuration loader."""
import os
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH  = PROJECT_ROOT / "config.yaml"


def load_config() -> dict:
    """Load config.yaml, substituting ${ENV_VAR} placeholders.
    Falls back to config.example.yaml so CI works without a local config.yaml."""
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


def today_str() -> str:
    """Return today's date as YYYY-MM-DD in Chicago time.
    On weekends, snaps back to Friday — arXiv doesn't post new papers Sat/Sun."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    d = datetime.now(ZoneInfo("America/Chicago")).date()
    if d.weekday() == 5:    # Saturday → Friday
        d -= timedelta(days=1)
    elif d.weekday() == 6:  # Sunday → Friday
        d -= timedelta(days=2)
    return d.isoformat()
