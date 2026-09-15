from __future__ import annotations

from collections import OrderedDict


NAVIGATION_GROUPS: "OrderedDict[str, tuple[str, ...]]" = OrderedDict(
    [
        (
            "Companion",
            (
                "Chat",
                "Intimität",
                "Unterhaltungen",
            ),
        ),
        (
            "Session",
            (
                "Session Studio",
                "Impulse",
                "Session-Modi",
                "Szenen",
            ),
        ),
        (
            "Kreativ",
            (
                "Abwechslung",
                "Mood & Details",
                "Momente & Twists",
                "Evolution & Rituale",
            ),
        ),
        (
            "Persona & Gedächtnis",
            (
                "Kontext",
                "Persona Lab",
                "Memory",
            ),
        ),
        (
            "Medien",
            (
                "Character Studio",
                "Medien",
            ),
        ),
        (
            "System",
            (
                "Einstellungen",
                "Privatsphäre",
                "Backup",
            ),
        ),
    ]
)


def navigation_group(label: str) -> str:
    clean = label.strip()
    for group, labels in NAVIGATION_GROUPS.items():
        if clean in labels:
            return group
    return "Weitere"


def ordered_navigation_labels(labels: list[str]) -> list[tuple[str, list[str]]]:
    """Group existing tab labels while preserving each group's configured order."""

    remaining = list(labels)
    grouped: list[tuple[str, list[str]]] = []
    for group, configured in NAVIGATION_GROUPS.items():
        matches = [label for label in configured if label in remaining]
        if not matches:
            continue
        grouped.append((group, matches))
        for label in matches:
            remaining.remove(label)
    if remaining:
        grouped.append(("Weitere", remaining))
    return grouped
