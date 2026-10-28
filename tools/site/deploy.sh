#!/usr/bin/env bash
# Publish site/ at origin/main to the codeframe.sh web root.
#
# Runs ON the web server, not on a workstation. Installed as
# /usr/local/bin/deploy-codeframe-site; see tools/site/README.md.
#
# The repository is public, so this pulls with no credential. rsync --delete
# makes the web root an exact copy of site/: an asset removed or renamed in the
# repository disappears here on the next run.
set -euo pipefail

REPO_URL=${REPO_URL:-https://github.com/frankbria/codeframe}
SRC=${SRC:-/opt/codeframe-site}
DOCROOT=${DOCROOT:-/var/www/codeframe.sh}
BACKUP=${BACKUP:-/root/codeframe.sh-predeploy.tgz}
# Present only while a sync is under way. If it survives, a previous run died
# mid-sync and the web root is a torn mix of two commits.
INCOMPLETE=${INCOMPLETE:-${BACKUP%.tgz}.incomplete}

if [ ! -d "$SRC/.git" ]; then
  git clone -q --depth 1 "$REPO_URL" "$SRC"
fi
git -C "$SRC" fetch -q --depth 1 origin main
git -C "$SRC" reset -q --hard origin/main
HEAD_SHA=$(git -C "$SRC" rev-parse HEAD)

# One rolling backup of what is being replaced, taken only when the web root is
# a complete deploy of a different commit. Skipped on a first deploy (no root),
# on a re-run at the same commit, and after an interrupted run (torn root): in
# each of those cases a backup would replace the last good copy with something
# that is not one. The sync below still runs, so a re-run repairs the root.
if [ -d "$DOCROOT" ] && [ ! -e "$INCOMPLETE" ] \
   && [ "$(cat "$DOCROOT/.deployed-sha" 2>/dev/null)" != "$HEAD_SHA" ]; then
  # Written aside and renamed: a tar that fails part-way (disk full) must not
  # truncate the backup it was meant to replace.
  tar -C "$(dirname "$DOCROOT")" -czf "$BACKUP.tmp" "$(basename "$DOCROOT")"
  mv "$BACKUP.tmp" "$BACKUP"
fi

mkdir -p "$DOCROOT"
touch "$INCOMPLETE"
# .well-known/ is left alone in case certificate renewal ever uses this root.
rsync -a --delete --exclude '/.well-known/' --exclude '/.deployed-sha' "$SRC/site/" "$DOCROOT/"
echo "$HEAD_SHA" > "$DOCROOT/.deployed-sha"
chown -R www-data:www-data "$DOCROOT"
rm -f "$INCOMPLETE"

echo "deployed ${HEAD_SHA:0:12} to $DOCROOT"
