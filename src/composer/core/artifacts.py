"""Read/write typed artifacts under .appgen directory."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


class ArtifactStore:
    def __init__(self, root: str = ".appgen") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_model(self, filename: str, model: BaseModel) -> Path:
        path = self.root / filename
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(model.model_dump(mode="json"), f, sort_keys=False)
        return path

    def save_dict(self, filename: str, payload: dict) -> Path:
        path = self.root / filename
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, sort_keys=False)
        return path

    def load_model(self, filename: str, model_cls: type[T]) -> T:
        path = self.root / filename
        with path.open("r", encoding="utf-8") as f:
            payload = yaml.safe_load(f) or {}
        return model_cls.model_validate(payload)
