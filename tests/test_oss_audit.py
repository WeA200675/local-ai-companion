from __future__ import annotations

import json
from pathlib import Path

from app.oss_audit import REGISTRY, audit_open_source_stack, load_registry


def test_repository_open_source_audit_passes() -> None:
    assert audit_open_source_stack() == []


def test_unregistered_direct_dependency_fails_audit(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[build-system]
requires = ["setuptools>=75", "wheel"]

[project]
name = "audit-fixture"
version = "0.0.0"
dependencies = [
  "pydantic>=2",
  "proprietary-sdk>=1"
]
""".strip(),
        encoding="utf-8",
    )

    issues = audit_open_source_stack(pyproject_path=pyproject, registry_path=REGISTRY)
    assert any("python:proprietary-sdk" in issue and "missing" in issue for issue in issues)


def test_component_not_marked_open_source_fails_audit(tmp_path: Path) -> None:
    registry = load_registry(REGISTRY)
    registry["python"]["pydantic"]["open_source"] = False
    registry_path = tmp_path / "oss_components.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    issues = audit_open_source_stack(registry_path=registry_path)
    assert any("python:pydantic" in issue and "open_source=true" in issue for issue in issues)


def test_unknown_license_marker_fails_audit(tmp_path: Path) -> None:
    registry = load_registry(REGISTRY)
    registry["python"]["httpx"]["license"] = "proprietary"
    registry_path = tmp_path / "oss_components.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    issues = audit_open_source_stack(registry_path=registry_path)
    assert any("python:httpx" in issue and "license" in issue for issue in issues)
