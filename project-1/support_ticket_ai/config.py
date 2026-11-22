from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str | None = None
    base_url: str | None = None


def load_json_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def openai_config_from_dict(config: dict[str, Any]) -> OpenAIConfig:
    api_key = config.get("OPENAI_API_KEY") or None
    base_url = (
        config.get("OPENAI_BASE_URL")
        or config.get("OPENAI_API_BASE")
        or config.get("OPENAI_API_ENDPOINT")
        or None
    )
    return OpenAIConfig(api_key=api_key, base_url=base_url)


def apply_openai_env(cfg: OpenAIConfig) -> None:
    """
    Applies env vars used by `openai` and `langchain-openai`.
    """
    if cfg.api_key:
        os.environ["OPENAI_API_KEY"] = cfg.api_key
    if cfg.base_url:
        os.environ["OPENAI_BASE_URL"] = cfg.base_url

