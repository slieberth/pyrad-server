from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from pyrad_server.config.schema import PyradServerConfig


@dataclass(frozen=True, slots=True)
class ConfigLoadError(Exception):
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return self.message


def load_config(path: str | Path) -> PyradServerConfig:
    config_path = Path(path)

    if not config_path.exists():
        raise ConfigLoadError(f"Config file not found: {config_path}")

    raw_text = config_path.read_text(encoding="utf-8")
    data = _parse_config_text(raw_text, config_path)

    return validate_config(data, source=str(config_path))


def validate_config(data: Any, *, source: str = "<memory>") -> PyradServerConfig:
    try:
        return PyradServerConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigLoadError(format_validation_error(exc, source=source)) from exc


def _parse_config_text(raw_text: str, path: Path) -> Any:
    suffix = path.suffix.lower()

    if suffix in {".yml", ".yaml"}:
        try:
            parsed = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise ConfigLoadError(f"YAML parse error in {path}: {exc}") from exc
        if parsed is None:
            raise ConfigLoadError(f"Empty YAML document: {path}")
        return parsed

    if suffix == ".json":
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ConfigLoadError(f"JSON parse error in {path}: {exc}") from exc

    raise ConfigLoadError(f"Unsupported config format '{path.suffix}'. Use .yml/.yaml or .json.")


def format_validation_error(error: ValidationError, *, source: str) -> str:
    lines: list[str] = [f"Config validation failed: {source}"]
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        message = item.get("msg", "invalid value")
        error_type = item.get("type", "validation_error")
        lines.append(f" - {location}: {message} ({error_type})")
    return "\n".join(lines)
