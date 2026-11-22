from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """
    Returns the project root directory (the folder that contains `run_pipeline.py`).
    """
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    return project_root() / "data"


def outputs_dir() -> Path:
    return project_root() / "outputs"


def reports_dir() -> Path:
    return project_root() / "reports"

