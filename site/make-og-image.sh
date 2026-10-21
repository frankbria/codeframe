#!/usr/bin/env bash
# Regenerates site/og-image.png (1200x630 social card) and site/proof9-loop-still.png
# (the reduced-motion still: the demo GIF's last frame). Needs ffmpeg + DejaVu fonts.
# Edit the COPY strings below when marketing copy changes, then re-run.
set -euo pipefail
cd "$(dirname "$0")"

# COPY: card strings
LINE1="Your coding agent can't quietly"
LINE2="undo what you already decided."
PIPE="/plugin install proof9"
URL="codeframe.sh"

FONTS=/usr/share/fonts/truetype/dejavu
BOLD="$FONTS/DejaVuSans-Bold.ttf" SANS="$FONTS/DejaVuSans.ttf" MONO="$FONTS/DejaVuSansMono.ttf"

# Strings go through textfile= so quotes, colons and commas in copy can't break the filtergraph.
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
for k in LINE1 LINE2 PIPE URL; do printf '%s' "${!k}" > "$T/$k"; done

# Dark card (hsl 220 9% 6% / 98% / 65%) with the reverse lockup, the variant
# for dark surfaces (brand rules, #1476).
ffmpeg -v error -y -f lavfi -i "color=c=0x0e0f11:s=1200x630" -i codeframe-lockup-reverse.png -frames:v 1 \
  -filter_complex "[1:v]scale=560:-1[logo];[0:v][logo]overlay=x=65:y=110,\
drawtext=fontfile=$SANS:textfile=$T/LINE1:expansion=none:fontsize=52:fontcolor=0xfafafa:x=80:y=280,\
drawtext=fontfile=$SANS:textfile=$T/LINE2:expansion=none:fontsize=52:fontcolor=0xfafafa:x=80:y=346,\
drawtext=fontfile=$MONO:textfile=$T/PIPE:expansion=none:fontsize=32:fontcolor=0x9fa3ab:x=80:y=460,\
drawtext=fontfile=$BOLD:textfile=$T/URL:expansion=none:fontsize=30:fontcolor=0x9fa3ab:x=80:y=540" \
  og-image.png

# -update 1 keeps overwriting one output file, so the last decoded frame wins.
ffmpeg -v error -y -i proof9-loop.gif -update 1 proof9-loop-still.png
