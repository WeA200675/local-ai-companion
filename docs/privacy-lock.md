# Local privacy lock

The privacy lock hides the companion UI behind a local passphrase without changing or deleting chat, memory, persona, media, or backup data.

## What it protects

When enabled, the app starts on a lock screen. The same screen can be activated immediately with **Ctrl+Shift+L** or the **Jetzt sperren** button in the Privacy tab. Optional inactivity locking can automatically return to that screen after a user-selected number of minutes.

The protected tabs remain mounted locally so an already-running model/media job can finish without being destroyed, but their contents are not visible while the lock screen is active.

## Passphrase storage

The passphrase itself is never written to SQLite. The app stores only a PBKDF2-HMAC-SHA256 verification digest, a random 128-bit salt, and the iteration count. Verification uses a constant-time digest comparison.

Changing or removing an existing lock requires the current passphrase from the Privacy tab. There is intentionally no cloud recovery path because the application is private/local-first.

## Important limit

This feature is an application-level privacy barrier, not full disk encryption. Someone with filesystem access can still copy the SQLite database or generated media directory. For protection against that threat, use operating-system account security and full-disk/device encryption as well.

## Backup and restore

Privacy-lock configuration is stored in the existing local `app_state` table, so local backups preserve it. After restoring a backup that had the lock enabled, the restored passphrase is required at the next app start. Restore notices are deferred until after successful unlock so file paths and state details are not shown over the lock screen.
