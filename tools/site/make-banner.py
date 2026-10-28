"""Build the CodeFRAME README banner (1600x500) as an all-outline SVG.

Every glyph is converted to a path, so the SVG renders identically wherever it
is shown, including GitHub's <img> sandbox, which cannot load web fonts.
Writes codeframe_github_header.svg; render the PNG from it for places that need
a raster (codeframe_github_header_1600x500.png). Edit the copy strings below
when marketing copy changes, then re-run.

Needs fontTools (and cairosvg for the PNG), plus IBM Plex Sans and IBM Plex Mono
as .woff, e.g. from `npm pack @ibm/plex-sans @ibm/plex-mono` (fonts/complete/woff/).

    python3 tools/site/make-banner.py site/codeframe-lockup-reverse.svg \
        <plex-sans>/fonts/complete/woff <plex-mono>/fonts/complete/woff \
        codeframe_github_header.svg
    python3 -c "import cairosvg; cairosvg.svg2png(url='codeframe_github_header.svg', \
        write_to='codeframe_github_header_1600x500.png', output_width=1600, output_height=500)"
"""
import re
import sys

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

lockup_svg, sans_dir, mono_dir, out = sys.argv[1:5]

FONTS = {
    "sans": TTFont(f"{sans_dir}/IBMPlexSans-Regular.woff"),
    "sans-med": TTFont(f"{sans_dir}/IBMPlexSans-Medium.woff"),
    "mono": TTFont(f"{mono_dir}/IBMPlexMono-Regular.woff"),
    "mono-med": TTFont(f"{mono_dir}/IBMPlexMono-Medium.woff"),
}


def kern_table(font):
    """Pair kerning from GPOS PairPos format 1 (enough for Plex's Latin pairs)."""
    pairs = {}
    if "GPOS" not in font:
        return pairs
    for lookup in font["GPOS"].table.LookupList.Lookup:
        for st in lookup.SubTable:
            if getattr(st, "ExtSubTable", None):
                st = st.ExtSubTable
            if getattr(st, "Format", None) == 1 and hasattr(st, "PairSet"):
                firsts = st.Coverage.glyphs
                for first, ps in zip(firsts, st.PairSet):
                    for rec in ps.PairValueRecord:
                        v = getattr(rec.Value1, "XAdvance", 0) if rec.Value1 else 0
                        if v:
                            pairs[(first, rec.SecondGlyph)] = v
            elif getattr(st, "Format", None) == 2 and hasattr(st, "Class1Record"):
                cov = set(st.Coverage.glyphs)
                c1 = st.ClassDef1.classDefs
                c2 = st.ClassDef2.classDefs
                st._kern2 = (cov, c1, c2, st.Class1Record)
                pairs.setdefault("_class", []).append(st._kern2)
    return pairs


KERN = {k: kern_table(f) for k, f in FONTS.items()}


def kern(key, a, b):
    t = KERN[key]
    if (a, b) in t:
        return t[(a, b)]
    for cov, c1, c2, recs in t.get("_class", []):
        if a in cov:
            r = recs[c1.get(a, 0)].Class2Record[c2.get(b, 0)]
            v = getattr(r.Value1, "XAdvance", 0) if r.Value1 else 0
            if v:
                return v
    return 0


def text_path(key, s, x, y, size, fill, tracking=0.0):
    """Return (svg <path>, advance width in px) for string s with baseline at y."""
    font = FONTS[key]
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    scale = size / upm
    pen = SVGPathPen(gs)
    cursor = 0.0
    prev = None
    for ch in s:
        g = cmap.get(ord(ch))
        if g is None:
            raise SystemExit(f"glyph missing for {ch!r} in {key}")
        if prev:
            cursor += kern(key, prev, g)
        tp = TransformPen(pen, (scale, 0, 0, -scale, x + cursor * scale, y))
        gs[g].draw(tp)
        cursor += gs[g].width + tracking * upm
        prev = g
    d = pen.getCommands()
    d = re.sub(r"-?\d+\.\d+", lambda m: f"{float(m.group()):.2f}".rstrip("0").rstrip("."), d)
    return f'<path fill="{fill}" d="{d}"/>', cursor * scale


# ---- palette (brand: #101D2E navy, #2563EB / #60A5FA blues, #F8FAFC light) ----
BG = "#0E0F11"
INK = "#F8FAFC"
MUTED = "#9FA3AB"
DIM = "#5B6170"
BLUE = "#60A5FA"
NAVY = "#101D2E"
GREEN = "#4ADE80"
LINE = "#1E2533"

W, H = 1600, 500
parts = []

# Lockup: inline the reverse wordmark as a nested <svg> so the banner is one file.
lk = open(lockup_svg).read()
lk_inner = re.search(r"<svg[^>]*>(.*)</svg>", lk, re.S).group(1)
lk_inner = re.sub(r"<title.*?</title>|<desc.*?</desc>", "", lk_inner, flags=re.S)
LK_W = 470
LK_H = LK_W * 128 / 621
LX, LY = 92, 92
parts.append(
    f'<svg x="{LX - 12}" y="{LY}" width="{LK_W}" height="{LK_H:.1f}" viewBox="0 0 621 128">{lk_inner}</svg>'
)

# Headline, two lines.
h1, _ = text_path("sans-med", "Your coding agent can’t quietly", LX, 262, 46, INK)
h2, _ = text_path("sans-med", "undo what you already decided.", LX, 320, 46, INK)
parts += [h1, h2]

# Subline.
sub, _ = text_path(
    "sans", "Regression memory for coding agents.", LX, 372, 24, MUTED
)
parts.append(sub)

# Install line in a soft pill.
inst = "/plugin install proof9"
ip, iw = text_path("mono", inst, LX + 22, 433, 21, INK)
parts.append(
    f'<rect x="{LX}" y="404" width="{iw + 44:.1f}" height="44" rx="8" fill="#161A22" stroke="{LINE}"/>'
)
parts.append(ip)

# ---- Right: a stylized proof ledger panel ----
PX, PY, PW, PH = 960, 98, 548, 352
parts.append(
    f'<rect x="{PX}" y="{PY}" width="{PW}" height="{PH}" rx="14" fill="#12151B" stroke="{LINE}"/>'
)
title, _ = text_path("mono-med", "PROOF9 ledger", PX + 28, PY + 46, 19, INK)
parts.append(title)
summary, sw = text_path("mono", "4 requirements · 0 failing", PX + 28, PY + 76, 16, MUTED)
parts.append(summary)
parts.append(f'<line x1="{PX + 28}" y1="{PY + 98}" x2="{PX + PW - 28}" y2="{PY + 98}" stroke="{LINE}"/>')

rows = [
    ("REQ-0001", "Empty password shows an error"),
    ("REQ-0002", "Free shipping over $50 stays free"),
    ("REQ-0003", "Refund keeps its audit record"),
    ("REQ-0004", "Session expires after 30 minutes"),
]
for i, (rid, label) in enumerate(rows):
    y = PY + 140 + i * 42
    cx = PX + 40
    # check in a circle, drawn as geometry (no font dependency)
    parts.append(f'<circle cx="{cx}" cy="{y - 6}" r="10" fill="none" stroke="{GREEN}" stroke-width="2"/>')
    parts.append(
        f'<path d="M{cx - 4.5} {y - 6} l3.2 3.4 l6 -7" fill="none" stroke="{GREEN}" '
        f'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    rp, rw = text_path("mono", rid, cx + 24, y, 16, BLUE)
    lp, _ = text_path("sans", label, cx + 24 + rw + 18, y, 17, INK)
    parts += [rp, lp]

parts.append(f'<line x1="{PX + 28}" y1="{PY + PH - 62}" x2="{PX + PW - 28}" y2="{PY + PH - 62}" stroke="{LINE}"/>')
foot, _ = text_path("mono", "checked before every commit", PX + 28, PY + PH - 28, 15, DIM)
parts.append(foot)

# Thin brand rule along the bottom.
parts.append(f'<rect x="0" y="{H - 6}" width="{W}" height="6" fill="#2563EB"/>')

svg = (
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
    f'role="img" aria-labelledby="t d">'
    f'<title id="t">CodeFRAME®: regression memory for coding agents</title>'
    f'<desc id="d">CodeFRAME wordmark. Your coding agent can’t quietly undo what you already decided. '
    f'Install: /plugin install proof9. A PROOF9 ledger panel lists four satisfied requirements.</desc>'
    f'<rect width="{W}" height="{H}" fill="{BG}"/>'
    + "".join(parts)
    + "</svg>"
)
open(out, "w").write(svg)
print(out, len(svg))
