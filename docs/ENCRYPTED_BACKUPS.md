# Encrypted local backups

The Backup tab can export either the existing portable ZIP format or an authenticated encrypted `.laicb` container. Encryption is enabled by default in the UI.

## Design

The application first creates the same consistent portable ZIP snapshot used by normal backups. That temporary ZIP is then encrypted as one payload with AES-256-GCM. A 256-bit key is derived from the user-supplied backup passphrase using scrypt with a random salt. A fresh random nonce is generated for every backup.

The container header stores only non-secret cryptographic metadata such as the salt, nonce, KDF parameters, format version, and cipher identifier. Header bytes are authenticated as associated data, so changing encryption metadata invalidates the backup.

The passphrase is never persisted in SQLite, settings, logs, or the encrypted container. Export and restore workers clear their in-memory passphrase reference when the operation finishes.

## Restore

Encrypted backups are decrypted into an operating-system temporary directory, validated using the existing backup manifest checks, and then staged through the same non-destructive restore path as plain ZIP backups. The live SQLite database is still untouched until the next application start, where the current database is copied to a `pre_restore` backup before replacement.

A wrong passphrase or modified ciphertext fails AES-GCM authentication and is rejected before restore staging.

## Scope

Encrypted backup files protect exported data at rest. They do not encrypt the live `data/companion.sqlite3` database or generated media directory. For protection of the live machine, use operating-system account security and full-disk encryption in addition to the app's optional UI privacy lock.
