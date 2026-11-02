"""Path classification driven by the versioned mapping configuration (REQ-01)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).with_name("mapping-v1.1.yaml")


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


@dataclass(frozen=True)
class MappingConfig:
    config_version: str
    rules: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...]
    default_category: str
    supported_extensions: frozenset[str]
    supported_filenames: frozenset[str]
    max_changed_files: int
    raw: dict[str, Any]

    def classify(self, path: str) -> str:
        for category, patterns in self.rules:
            if any(p.match(path) for p in patterns):
                return category
        return self.default_category

    def is_supported(self, path: str) -> bool:
        p = PurePosixPath(path)
        return p.suffix.lower() in self.supported_extensions or p.name in self.supported_filenames


@lru_cache(maxsize=1)
def load_config(path: Path = CONFIG_PATH) -> MappingConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = tuple(
        (entry["category"], tuple(glob_to_regex(p) for p in entry["patterns"]))
        for entry in raw["categories"]
    )
    return MappingConfig(
        config_version=raw["config_version"],
        rules=rules,
        default_category=raw["default_category"],
        supported_extensions=frozenset(e.lower() for e in raw["supported_extensions"]),
        supported_filenames=frozenset(raw["supported_filenames"]),
        max_changed_files=int(raw["max_changed_files"]),
        raw=raw,
    )
