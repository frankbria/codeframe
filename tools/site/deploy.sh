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

if [ ! -d "$SRC/.git" ]; then
  git clone -q --depth 1 "$REPO_URL" "$SRC"
fi
git -C "$SRC" fetch -q --depth 1 origin main
git -C "$SRC" reset -q --hard origin/main
HEAD_SHA=$(git -C "$SRC" rev-parse HEAD)

# One rolling backup of what is being replaced. Skipped on a first deploy (no
# web root yet) and when the web root already holds this commit: right after a
# bad deploy, a re-run would otherwise overwrite the last-good backup with the
# broken tree. The sync below still runs, so a re-run repairs a hand-edited root.
if [ -d "$DOCROOT" ] && [ "$(cat "$DOCROOT/.deployed-sha" 2>/dev/null)" != "$HEAD_SHA" ]; then
  tar -C "$(dirname "$DOCROOT")" -czf "$BACKUP" "$(basename "$DOCROOT")"
fi

mkdir -p "$DOCROOT"
# .well-known/ is left alone in case certificate renewal ever uses this root.
rsync -a --delete --exclude '/.well-known/' --exclude '/.deployed-sha' "$SRC/site/" "$DOCROOT/"
echo "$HEAD_SHA" > "$DOCROOT/.deployed-sha"
chown -R www-data:www-data "$DOCROOT"

echo "deployed ${HEAD_SHA:0:12} to $DOCROOT"
