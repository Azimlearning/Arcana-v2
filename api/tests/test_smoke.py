"""Toolchain smoke test: the dependency set imports on the pinned Python."""

import importlib
import sys

import pytest

MODULES = ["fastapi", "langgraph", "networkx", "pymupdf", "rank_bm25", "sqlalchemy", "structlog"]


def test_python_is_313():
    assert sys.version_info[:2] == (3, 13)


@pytest.mark.parametrize("name", MODULES)
def test_dependency_imports(name: str):
    importlib.import_module(name)
