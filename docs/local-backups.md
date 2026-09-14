# Local backups and staged restore

The app can export its local state to a portable ZIP from the **Backup** tab.

## Export

A backup always contains a consistent SQLite snapshot made with SQLite's backup API, so the live database is not copied while partially written. When **Lokale Medien aus der Historie ins Backup aufnehmen** is enabled, the archive also includes existing files referenced by the media history that are located inside the configured local media output directory.

The archive manifest records its format version, app version, backup id, database member, and included media-event mappings. Files outside the configured media directory are not swept into the archive.

## Restore

Import is deliberately staged rather than applied to the database while the desktop app is running.

1. Select a backup ZIP in the **Backup** tab.
2. The archive is validated and extracted into a private pending-restore directory.
3. Restored media paths and pinned character-reference paths are rewritten to safe local destinations.
4. Nothing changes in the running app yet.
5. On the next app start, before SQLAlchemy opens the live database, the current SQLite state is first copied to `data/backups/pre_restore_<timestamp>.sqlite3`.
6. Only then is the staged database activated.

Existing generated media are never deleted during restore. Restored files use unique names, so a restore does not overwrite an existing media file.

A staged import can be discarded from the Backup tab before restarting.

## Privacy

Backup archives can contain chat history, persona state, learned preferences, adaptive memory, settings, snapshot history, media metadata, and optionally generated media. Treat a backup as private data and store it accordingly. The application does not upload backups or media to a cloud service.
