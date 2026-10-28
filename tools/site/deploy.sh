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

REPO_URL=https://github.com/frankbria/codeframe
SRC=/opt/codeframe-site
DOCROOT=/var/www/codeframe.sh

if [ ! -d "$SRC/.git" ]; then
  git clone -q --depth 1 "$REPO_URL" "$SRC"
fi
git -C "$SRC" fetch -q --depth 1 origin main
git -C "$SRC" reset -q --hard origin/main

# One rolling backup of whatever is being replaced.
tar -C "$(dirname "$DOCROOT")" -czf /root/codeframe.sh-predeploy.tgz "$(basename "$DOCROOT")"

# .well-known/ is left alone in case certificate renewal ever uses this root.
rsync -a --delete --exclude '/.well-known/' --exclude '/.deployed-sha' "$SRC/site/" "$DOCROOT/"
git -C "$SRC" rev-parse HEAD > "$DOCROOT/.deployed-sha"
chown -R www-data:www-data "$DOCROOT"

echo "deployed $(cut -c1-12 "$DOCROOT/.deployed-sha") to $DOCROOT"
