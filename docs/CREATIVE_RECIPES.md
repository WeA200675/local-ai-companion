# Creative Recipes und Visual-Motive

Creative Recipes bündeln mehrere **temporäre** Kreativ-Layer zu einer wiederverwendbaren Kombination. Ein Recipe kann einen Look, einen Impuls, einen Session-Arc, ein Visual-Motiv und einen Scene-Mixer-Stand enthalten.

## Sicherheits- und Persistenzgrenzen

Recipes enthalten ausdrücklich **keine** Persona-Traits, kein Core Memory, kein adaptives Memory und keine stabile Character-Studio-Identität. Sie verändern deshalb weder das Langzeitlernen noch die visuelle Grundidentität der Figur.

Eigene Recipes werden ausschließlich im lokalen App-State gespeichert. Beim Speichern einer aktuellen Kombination wird ein aktiver Scene-Mixer-Stand exakt mitgesichert. Die eingebauten Recipes dürfen dagegen beim Anwenden bewusst einen frischen Scene-Mix erzeugen, damit sie nicht immer dasselbe Bild wiederholen.

## Visual-Motive

Visual-Motive sind ein weiterer unterhaltungsspezifischer Layer für Abwechslung in lokalen Bildern. Sie beschreiben drei Dinge:

- Ausdruck und Blickwirkung,
- Haltung beziehungsweise Pose,
- Kamera- und Bildkomposition.

Die Motive bleiben im erwachsenen, nicht expliziten visuellen Bereich und ergänzen die vorhandenen Look-, Scene- und Character-Continuity-Layer. Sie können manuell gewählt, zufällig gewechselt oder vom opt-in Creative Director rotiert werden.

## Creative Director

Der Creative Director kann Visual-Motive wie andere temporäre Layer behandeln. Visual-Motive lassen sich sperren und als Favoriten markieren. Bei deaktivierter Automatik findet keine selbständige Rotation statt.

## Open Source und lokal

Die Erweiterung führt keine neue Abhängigkeit, keinen Cloud-Dienst, keine Telemetrie und keine proprietäre Komponente ein. Persistenz und Auswahl laufen vollständig über die bestehende lokale Python-/SQLite-Anwendung.
