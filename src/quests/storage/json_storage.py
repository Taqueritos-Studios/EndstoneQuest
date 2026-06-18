import copy
import json
from pathlib import Path
from typing import Any


class JsonStorage:
    def __init__(self, logger: Any):
        self.logger = logger

    def load_dict(self, path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
        fallback = {} if default is None else copy.deepcopy(default)

        if not path.exists():
            self.save_dict(path, fallback)
            return fallback

        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as error:
            self.logger.error(f"Could not load {path.name}: {error}")
            return fallback

        if not isinstance(data, dict):
            self.logger.error(f"Could not load {path.name}: root JSON value must be an object.")
            return fallback

        return data

    def load_dict_with_defaults(self, path: Path, defaults: dict[str, Any]) -> dict[str, Any]:
        data = self.load_dict(path, defaults)
        merged = self.deep_merge(data, defaults)

        if merged != data:
            self.save_dict(path, merged)

        return merged

    def save_dict(self, path: Path, data: dict[str, Any]):
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(data, indent=4) + "\n"

        if path.exists() and path.read_text(encoding="utf-8-sig") == content:
            return

        path.write_text(content, encoding="utf-8")

    def deep_merge(self, data: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
        merged = copy.deepcopy(data)

        for key, default_value in defaults.items():
            if key not in merged:
                merged[key] = copy.deepcopy(default_value)
                continue

            current_value = merged[key]
            if isinstance(current_value, dict) and isinstance(default_value, dict):
                merged[key] = self.deep_merge(current_value, default_value)

        return merged
