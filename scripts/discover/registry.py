"""Provider registry for deterministic source discovery."""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from discover.core import Coverage, SourceConfig


@dataclass(frozen=True)
class SourceAdapter:
    modes: tuple[str, ...]
    discover: Callable[[SourceConfig, list[str], int], Coverage]
    options_schema: Mapping[str, type] | None = None
    requires: tuple[str, ...] = ()


_REGISTRY_CACHE: dict[str, SourceAdapter] | None = None


def _adapter_objects(module: object) -> list[SourceAdapter]:
    adapters: list[SourceAdapter] = []
    source = getattr(module, "SOURCE", None)
    if source is not None:
        adapters.append(source)
    sources = getattr(module, "SOURCES", None)
    if sources is not None:
        adapters.extend(list(sources))
    return adapters


def _requires_available(adapter: SourceAdapter) -> bool:
    return all(importlib.util.find_spec(requirement) is not None for requirement in adapter.requires)


def load_registry() -> dict[str, SourceAdapter]:
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return dict(_REGISTRY_CACHE)

    from discover import sources

    registry: dict[str, SourceAdapter] = {}
    for module_info in pkgutil.iter_modules(sources.__path__):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{sources.__name__}.{module_info.name}")
        for adapter in _adapter_objects(module):
            for mode in adapter.modes:
                if mode in registry:
                    raise ValueError(f"Duplicate discovery provider for mode {mode!r}")
                registry[mode] = adapter

    _REGISTRY_CACHE = registry
    return dict(registry)


def available_registry() -> dict[str, SourceAdapter]:
    return {mode: adapter for mode, adapter in load_registry().items() if _requires_available(adapter)}
