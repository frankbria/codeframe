#!/usr/bin/env bash
# Pre-deploy backup of the live SQLite database (#1295).
#
# Usage: backup-db.sh <output-file> <state-dir>
#
# The live DB is /data/codeframe.db inside the codeframe_codeframe-data named
# volume. The old step copied .codeframe/state.db, which no longer exists on a
# container host, so it skipped silently and reported success.
#
# This takes an online SQLite backup (consistent even while the backend is
# writing, unlike cp of a WAL-mode file) in a throwaway container, checks it,
# and streams it out to <output-file>.
#
# <state-dir> (the host's backups directory, outside the volume) records that
# this host has had a database. That, not the volume, is what tells a first
# deploy from data loss: a first deploy that crashed before creating the DB
# leaves a volume with no DB in it, and a lost volume leaves nothing at all.
#
#   no DB (or no volume), never backed up here -> first deploy, exit 0
#   no DB (or no volume), backed up before     -> exit 1, data loss
#   backup or check fails                      -> exit 1, no partial file
#
# After an intentional reset, delete <state-dir>/.database-backed-up.
set -euo pipefail
# The backup holds password hashes and tokens, and this is a shared host: the
# partial file must never exist with group/other bits, not even mid-stream.
umask 077

OUT="${1:?usage: backup-db.sh <output-file> <state-dir>}"
STATE_DIR="${2:?usage: backup-db.sh <output-file> <state-dir>}"
VOLUME="${CODEFRAME_DATA_VOLUME:-codeframe_codeframe-data}"
# Pinned by digest (#1390): this image mounts the production volume read-write.
# Refresh: deploy/README.md -> "Refreshing the helper image digests".
IMAGE="${CODEFRAME_BACKUP_IMAGE:-python:3.12-alpine@sha256:0687a6bc9716edc2a6ee0fbfb0f87e7ee358b262b67c9215de91bc9b2d38ba71}"
MARKER="$STATE_DIR/.database-backed-up"

no_database() {
  if [ -f "$MARKER" ]; then
    echo "❌ $1, but this host has backed up a database before ($MARKER)."
    echo "   That is data loss, not a fresh install. Restore from $STATE_DIR"
    echo "   (deploy/README.md), or delete the marker after an intentional reset."
    exit 1
  fi
  echo "ℹ️  $1 and none was ever backed up here (first deploy) — nothing to back up"
  exit 0
}

if ! docker volume inspect "$VOLUME" >/dev/null 2>&1; then
  no_database "No $VOLUME volume"
fi

# uid 10001 is the backend's: SQLite may create -wal/-shm files beside the DB,
# and root-owned ones would lock the app out of its own database.
# </dev/null, never -i: callers run this from `ssh host bash -s << EOF`, where
# stdin IS the rest of the calling script, and a container that reads it
# swallows every line after this one while the step still exits 0.
set +e
docker run --rm --user 10001:10001 -v "$VOLUME":/data "$IMAGE" python -c '
import os, sqlite3, sys, tempfile
src_path = "/data/codeframe.db"
# A zero-byte file opens as a valid, empty database, so it counts as gone.
if not os.path.isfile(src_path) or os.path.getsize(src_path) == 0:
    sys.exit(3)
# Checked above, so connect cannot create an empty one in its place.
src = sqlite3.connect(src_path)
tmp = os.path.join(tempfile.mkdtemp(), "backup.db")
dst = sqlite3.connect(tmp)
src.backup(dst)
src.close()
verdict = dst.execute("PRAGMA integrity_check").fetchone()[0]
dst.close()
if verdict != "ok":
    sys.exit("backup failed integrity_check: " + verdict)
with open(tmp, "rb") as f:
    while chunk := f.read(1 << 20):
        sys.stdout.buffer.write(chunk)
' > "$OUT.partial" < /dev/null
status=$?
set -e

if [ "$status" -ne 0 ]; then
  rm -f "$OUT.partial"
  if [ "$status" -eq 3 ]; then
    no_database "The $VOLUME volume has no codeframe.db (or an empty one)"
  fi
  echo "❌ Database backup failed (see the error above). Not deploying over an unbacked-up database."
  exit 1
fi

mv "$OUT.partial" "$OUT"
chmod 600 "$OUT"
mkdir -p "$STATE_DIR"
touch "$MARKER"
echo "✅ Database backed up: $OUT ($(du -h "$OUT" | cut -f1))"
