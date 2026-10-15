#!/usr/bin/env bash
# Regenerates site/og-image.png (1200x630 social card) and site/cli-tour-still.png
# (the reduced-motion still: the demo GIF's last frame). Needs ffmpeg + DejaVu fonts.
# Edit the COPY strings below when marketing copy changes, then re-run.
set -euo pipefail
cd "$(dirname "$0")"

# COPY: card strings
TITLE="CodeFRAME"
LINE1="A project delivery system"
LINE2="for AI-written software."
PIPE="Think → Build → Prove → Ship"
URL="codeframe.sh"

FONTS=/usr/share/fonts/truetype/dejavu
BOLD="$FONTS/DejaVuSans-Bold.ttf" SANS="$FONTS/DejaVuSans.ttf" MONO="$FONTS/DejaVuSansMono.ttf"

# Strings go through textfile= so quotes, colons and commas in copy can't break the filtergraph.
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
for k in TITLE LINE1 LINE2 PIPE URL; do printf '%s' "${!k}" > "$T/$k"; done

# Colors are the web UI's dark gray tokens (hsl 220 9% 6% / 98% / 65%).
ffmpeg -v error -y -f lavfi -i "color=c=0x0e0f11:s=1200x630" -frames:v 1 -vf "\
drawbox=x=80:y=96:w=64:h=6:color=0xfafafa:t=fill,\
drawtext=fontfile=$BOLD:textfile=$T/TITLE:expansion=none:fontsize=96:fontcolor=0xfafafa:x=80:y=130,\
drawtext=fontfile=$SANS:textfile=$T/LINE1:expansion=none:fontsize=52:fontcolor=0xfafafa:x=80:y=280,\
drawtext=fontfile=$SANS:textfile=$T/LINE2:expansion=none:fontsize=52:fontcolor=0xfafafa:x=80:y=346,\
drawtext=fontfile=$MONO:textfile=$T/PIPE:expansion=none:fontsize=32:fontcolor=0x9fa3ab:x=80:y=460,\
drawtext=fontfile=$BOLD:textfile=$T/URL:expansion=none:fontsize=30:fontcolor=0x9fa3ab:x=80:y=540" \
  og-image.png

# -update 1 keeps overwriting one output file, so the last decoded frame wins.
ffmpeg -v error -y -i cli-tour.gif -update 1 cli-tour-still.png
