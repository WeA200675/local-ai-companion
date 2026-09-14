from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Any

from app.settings import AppSettings

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
REGISTRY = ROOT / "oss_components.json"

_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9_.-]+)")
_DISALLOWED_LICENSE_MARKERS = {
    "",
    "unknown",
    "proprietary",
    "commercial",
    "closed-source",
    "source-available",
}


def normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value.strip().casefold())


def requirement_name(requirement: str) -> str:
    match = _REQUIREMENT_NAME.match(requirement)
    if match is None:
        raise ValueError(f"Could not parse dependency requirement: {requirement!r}")
    return normalize_name(match.group(1))


def declared_python_dependencies(pyproject_path: Path = PYPROJECT) -> dict[str, set[str]]:
    with pyproject_path.open("rb") as handle:
        data = tomllib.load(handle)

    result: dict[str, set[str]] = {}

    def add(requirement: str, role: str) -> None:
        name = requirement_name(requirement)
        result.setdefault(name, set()).add(role)

    build_system = data.get("build-system", {})
    if isinstance(build_system, dict):
        for requirement in build_system.get("requires", []) or []:
            add(str(requirement), "build")

    project = data.get("project", {})
    if isinstance(project, dict):
        for requirement in project.get("dependencies", []) or []:
            add(str(requirement), "runtime")
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for group, requirements in optional.items():
                for requirement in requirements or []:
                    add(str(requirement), f"optional:{group}")

    return result


def load_registry(path: Path = REGISTRY) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Could not read OSS registry: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeError("Unsupported or invalid OSS component registry")
    return payload


def _entry_issues(name: str, entry: object, *, section: str) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{section}:{name} has no valid registry object"]
    issues: list[str] = []
    if entry.get("open_source") is not True:
        issues.append(f"{section}:{name} is not explicitly marked open_source=true")
    license_text = str(entry.get("license") or "").strip()
    if license_text.casefold() in _DISALLOWED_LICENSE_MARKERS:
        issues.append(f"{section}:{name} has no accepted open-source license identifier")
    return issues


def audit_open_source_stack(
    *,
    pyproject_path: Path = PYPROJECT,
    registry_path: Path = REGISTRY,
) -> list[str]:
    """Return policy violations; an empty list means the deterministic audit passed."""

    registry = load_registry(registry_path)
    python_registry_raw = registry.get("python", {})
    external_registry_raw = registry.get("external", {})
    if not isinstance(python_registry_raw, dict):
        return ["OSS registry section 'python' must be an object"]
    if not isinstance(external_registry_raw, dict):
        return ["OSS registry section 'external' must be an object"]

    python_registry = {
        normalize_name(str(name)): entry for name, entry in python_registry_raw.items()
    }
    external_registry = {
        str(name).strip().casefold(): entry for name, entry in external_registry_raw.items()
    }

    issues: list[str] = []
    declared = declared_python_dependencies(pyproject_path)
    for name, roles in sorted(declared.items()):
        entry = python_registry.get(name)
        if entry is None:
            issues.append(
                f"python:{name} is declared in pyproject.toml but missing from oss_components.json "
                f"({', '.join(sorted(roles))})"
            )
            continue
        issues.extend(_entry_issues(name, entry, section="python"))

    for name, entry in sorted(python_registry.items()):
        issues.extend(_entry_issues(name, entry, section="python"))

    required_external = {"ollama", "comfyui", AppSettings().model_name.casefold()}
    for name in sorted(required_external):
        entry = external_registry.get(name)
        if entry is None:
            issues.append(f"external:{name} is a default component but is not registered")
            continue
        issues.extend(_entry_issues(name, entry, section="external"))

    for name, entry in sorted(external_registry.items()):
        issues.extend(_entry_issues(name, entry, section="external"))

    return list(dict.fromkeys(issues))


def render_report(issues: list[str]) -> str:
    if not issues:
        return "Open-source audit: PASS — all declared direct components are registered as open source."
    return "Open-source audit: FAIL\n" + "\n".join(f"- {issue}" for issue in issues)


def main() -> int:
    try:
        issues = audit_open_source_stack()
    except Exception as exc:
        print(f"Open-source audit: ERROR — {exc}")
        return 2
    print(render_report(issues))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
