# Site tooling

Scripts for the static `codeframe.sh` page in `site/`. They live here rather than
in `site/` so that everything under `site/` is servable, and a deploy can copy the
directory as-is with no exclude list to remember.

| Script | What it does |
|---|---|
| `make-og-image.sh` | Regenerates `site/og-image.png` (the 1200x630 social card) and `site/proof9-loop-still.png`. Needs ffmpeg and DejaVu fonts. |
| `make-banner.py` | Builds the outlined banner SVG. Usage is in its docstring. |
| `deploy.sh` | Publishes `site/` at `origin/main` to the web root. Runs on the server. |

## Deploying

The trigger is manual. After a change to `site/` merges:

```bash
tailscale ssh root@frank-prod-server deploy-codeframe-site
```

One-time setup on the server:

```bash
git clone --depth 1 https://github.com/frankbria/codeframe /opt/codeframe-site
install -m 755 /opt/codeframe-site/tools/site/deploy.sh /usr/local/bin/deploy-codeframe-site
```

Re-run the `install` line whenever `deploy.sh` itself changes; the installed copy
does not update itself.

What a run does:

- pulls the public repository, so no credential is needed and none is stored;
- keeps one rolling backup of the current web root at `/root/codeframe.sh-predeploy.tgz`;
- mirrors `site/` into the web root with `rsync --delete`, so an asset removed or
  renamed in the repository disappears on the next deploy;
- writes the deployed commit to `.deployed-sha` in the web root.

Check what is live:

```bash
tailscale ssh root@frank-prod-server cat /var/www/codeframe.sh/.deployed-sha
```
