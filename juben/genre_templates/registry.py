"""题材模板注册表"""
from __future__ import annotations
from typing import Callable, Any

_REGISTRY: dict[str, Callable] = {}


def register(name: str):
    def decorator(func):
        _REGISTRY[name] = func
        return func
    return decorator


def get_template(name: str) -> Callable | None:
    return _REGISTRY.get(name)


def list_templates() -> list[str]:
    return list(_REGISTRY.keys())
