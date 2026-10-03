#!/usr/bin/env bash
# Pre-deploy backup of the live SQLite database (#1295).
#
# Usage: backup-db.sh <output-file>
#
# The live DB is /data/codeframe.db inside the codeframe_codeframe-data named
# volume. The old step copied .codeframe/state.db, which no longer exists on a
# container host, so it skipped silently and reported success.
#
# This takes an online SQLite backup (consistent even while the backend is
# writing, unlike cp of a WAL-mode file) in a throwaway container, checks it,
# and streams it out to <output-file>.
#
#   no data volume        -> first deploy, nothing to back up, exit 0
#   volume but no DB      -> exit 1: this host has run before, so a missing DB
#                            is data loss, not a fresh install
#   backup or check fails -> exit 1, no partial file left behind
set -euo pipefail

OUT="${1:?usage: backup-db.sh <output-file>}"
VOLUME="${CODEFRAME_DATA_VOLUME:-codeframe_codeframe-data}"
IMAGE="${CODEFRAME_BACKUP_IMAGE:-python:3.12-alpine}"

if ! docker volume inspect "$VOLUME" >/dev/null 2>&1; then
  echo "ℹ️  No $VOLUME volume yet (first deploy) — no database to back up"
  exit 0
fi

# uid 10001 is the backend's: SQLite may create -wal/-shm files beside the DB,
# and root-owned ones would lock the app out of its own database.
if ! docker run --rm -i --user 10001:10001 -v "$VOLUME":/data "$IMAGE" python -c '
import os, sqlite3, sys, tempfile
src_path = "/data/codeframe.db"
if not os.path.isfile(src_path):
    sys.exit("database missing: " + src_path)
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
    sys.stdout.buffer.write(f.read())
' > "$OUT.partial"; then
  rm -f "$OUT.partial"
  echo "❌ Database backup failed (see the error above). Not deploying over an unbacked-up database."
  exit 1
fi

mv "$OUT.partial" "$OUT"
chmod 600 "$OUT"
echo "✅ Database backed up: $OUT ($(du -h "$OUT" | cut -f1))"
