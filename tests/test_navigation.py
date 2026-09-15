from __future__ import annotations

from app.navigation import navigation_group, ordered_navigation_labels


def test_navigation_maps_primary_sections() -> None:
    assert navigation_group("Chat") == "Companion"
    assert navigation_group("Intimität") == "Companion"
    assert navigation_group("Session Studio") == "Session"
    assert navigation_group("Mood & Details") == "Kreativ"
    assert navigation_group("Kontext") == "Persona & Gedächtnis"
    assert navigation_group("Character Studio") == "Medien"
    assert navigation_group("Backup") == "System"
    assert navigation_group("Unbekannt") == "Weitere"


def test_navigation_grouping_uses_stable_category_and_page_order() -> None:
    labels = [
        "Backup",
        "Chat",
        "Szenen",
        "Einstellungen",
        "Mood & Details",
        "Session Studio",
        "Kontext",
        "Intimität",
        "Eigenes Werkzeug",
    ]

    assert ordered_navigation_labels(labels) == [
        ("Companion", ["Chat", "Intimität"]),
        ("Session", ["Session Studio", "Szenen"]),
        ("Kreativ", ["Mood & Details"]),
        ("Persona & Gedächtnis", ["Kontext"]),
        ("System", ["Einstellungen", "Backup"]),
        ("Weitere", ["Eigenes Werkzeug"]),
    ]
