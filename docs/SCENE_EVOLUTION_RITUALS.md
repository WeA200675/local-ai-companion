# Scene Evolution & Rituale

Diese Erweiterung bringt zwei lokale, reversible Abwechslungsebenen in längere Companion-Sessions. Beide Ebenen sind pro Unterhaltung getrennt und verändern weder Persona noch Core Memory, adaptives Memory, Character-Identität oder Modellgewichte.

## Scene Evolution

Scene Evolution legt eine mehrstufige Entwicklung über die aktuell gewählte Szene, ohne das Szenen-Preset selbst umzuschreiben. Dadurch kann derselbe Ort sichtbar und erzählerisch weiterleben, statt bei jeder Antwort statisch zu bleiben oder abrupt durch eine neue Szene ersetzt zu werden.

Mitgelieferte Abläufe sind unter anderem:

- Night Deepens
- Storm Passing
- Studio Afterhours
- Threshold Shift

Jeder Ablauf besteht aus mehreren Stufen. Die Stufen können manuell gewechselt oder optional automatisch nach 1–10 abgeschlossenen Assistant-Antworten fortgeschaltet werden. Ein Loop kann ausdrücklich aktiviert werden; ohne Loop bleibt eine Evolution am Ende auf ihrer letzten Stufe stehen und deaktiviert die Automatik.

Scene Evolution ergänzt den aktuellen Szenenkontext nur. Ein vorhandenes Szenen-Preset bleibt unverändert und kann jederzeit gewechselt oder deaktiviert werden.

## Rituale

Rituale sind kurze, wiederverwendbare Sequenzen für Gesprächsrhythmus und visuelle Inszenierung. Sie sind keine Regeln, Pflichten oder Langzeitpräferenzen. Die aktuelle Nachricht des Nutzers hat immer Vorrang.

Mitgelieferte Rituale sind:

- Arrival & Focus
- Wardrobe & Detail
- Challenge & Reward
- Camera Sequence
- Mystery Reveal
- Cooldown & Debrief

Ein Ritual kann manuell Schritt für Schritt geführt oder optional automatisch nach 1–6 abgeschlossenen Assistant-Antworten fortgeschaltet werden. Ohne Loop endet es nach dem letzten Schritt und wird automatisch deaktiviert. Mit aktiviertem Loop beginnt es wieder beim ersten Schritt.

## Chat- und Medienintegration

Die aktive Scene-Evolution-Stufe und der aktive Ritual-Schritt werden als klar markierte temporäre Kontextschichten an den lokalen Chat-Prompt angehängt. Ihre Style-Tags fließen außerdem in die lokale Medienplanung ein. Dadurch können Licht, Komposition, Raumgefühl, Materialdetails oder Dialogrhythmus mitwandern, ohne Character- oder Memory-Zustände zu überschreiben.

Der lokale Anti-Wiederholungs-Tracker berücksichtigt die aktuelle Evolution-Stufe und den Ritual-Schritt in seiner kreativen Signatur. Dadurch kann er wiederkehrende Kombinationen besser erkennen.

## Transparenz

Der Kontext-Inspector zeigt:

- aktive Scene Evolution und aktuelle Stufe
- manuellen oder automatischen Fortschritt
- Evolutionsintervall
- aktives Ritual und aktuellen Schritt
- manuellen oder automatischen Fortschritt
- Ritualintervall
- den tatsächlich in den System-Prompt eingebrachten Kontext

## Sicherheit und Kontrolle

Scene Evolution und Rituale sind vollständig lokal und user-kontrolliert. Sie werden nie automatisch in Core Memory oder adaptives Memory übernommen. Ein Ritual ist ausdrücklich nur eine optionale Strukturhilfe und kann keine versteckte Verpflichtung erzeugen. Aktuelle Nutzeranweisungen, explizite Auswahlen, Grenzen und Stop-Aktionen haben immer Vorrang.

## Open Source

Die Erweiterung fügt keine neue Abhängigkeit, keinen Cloud-Dienst, keine Telemetrie und keine proprietäre Komponente hinzu. Sie verwendet nur den vorhandenen Python/PySide6/Pydantic/SQLite-Stack und unterliegt weiterhin dem bestehenden Open-Source-only-CI-Audit.
