"""Shared palette, typography and SVG helpers for every generated panel.

Everything here targets one hostile rendering context: an SVG loaded through
GitHub's camo proxy inside an <img> tag. That means no scripts, no external
resource loads (fonts, images), and no interaction. CSS animations and SMIL do
run, which is the entire budget we have for motion.
"""

from xml.sax.saxutils import escape as _escape

# ── mostly neutral, rose as a sparing accent ───────────────────────────────
# White/gray on near-black, matched to the id-card's canvas — and to GitHub's
# own dark-theme canvas/border colors, so the panels sit flush against the
# profile page instead of showing up as an off-black box.
BG    = "#0d1117"   # GitHub dark-theme canvas.default
LINE  = "#30363d"   # GitHub dark-theme border.default
DIM   = "#8a8790"
MUTED = "#c7c5c8"
FG    = "#f5f5f6"

WHITE = "#f5f5f6"
ROSE  = "#f7768e"   # the one accent colour

# No webfont can be fetched from inside an <img>-loaded SVG, so both stacks are
# built entirely from faces that ship with the OS.
MONO = "ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def esc(s) -> str:
    """XML-escape a value for use as SVG text content."""
    return _escape(str(s))


def text(x, y, s, *, size=12, fill=MUTED, family=MONO, weight=400,
         anchor="start", spacing=None, cls=None, style=None, opacity=None):
    a = [f'x="{x}"', f'y="{y}"', f'font-family="{family}"', f'font-size="{size}"',
         f'fill="{fill}"']
    if weight != 400:
        a.append(f'font-weight="{weight}"')
    if anchor != "start":
        a.append(f'text-anchor="{anchor}"')
    if spacing is not None:
        a.append(f'letter-spacing="{spacing}"')
    if opacity is not None:
        a.append(f'opacity="{opacity}"')
    if cls:
        a.append(f'class="{cls}"')
    if style:
        a.append(f'style="{style}"')
    return f'<text {" ".join(a)}>{esc(s)}</text>'


def rect(x, y, w, h, *, fill="none", stroke=None, sw=1, rx=0, cls=None,
         style=None, opacity=None):
    a = [f'x="{x}"', f'y="{y}"', f'width="{w}"', f'height="{h}"', f'fill="{fill}"']
    if rx:
        a.append(f'rx="{rx}"')
    if stroke:
        a += [f'stroke="{stroke}"', f'stroke-width="{sw}"']
    if opacity is not None:
        a.append(f'opacity="{opacity}"')
    if cls:
        a.append(f'class="{cls}"')
    if style:
        a.append(f'style="{style}"')
    return f'<rect {" ".join(a)}/>'


# Motion shared by every panel. Kept in one string so the panel and the
# ID card breathe on the same clock.
BASE_CSS = f"""
  .fade    {{ opacity:0; animation:fade .8s ease forwards; }}
  .rise    {{ opacity:0; animation:rise .7s cubic-bezier(.2,.7,.3,1) forwards; }}
  .build   {{ opacity:0; transform-box:fill-box; transform-origin:50% 100%;
              transform:scaleY(.05); animation:build .55s cubic-bezier(.3,1.3,.4,1) forwards; }}
  @keyframes fade  {{ to {{ opacity:1; }} }}
  @keyframes rise  {{ from {{ opacity:0; transform:translateY(9px); }}
                      to   {{ opacity:1; transform:translateY(0); }} }}
  @keyframes build {{ 0%   {{ opacity:0; transform:scaleY(.05); }}
                       55%  {{ opacity:1; }}
                       100% {{ opacity:1; transform:scaleY(1); }} }}
  @media (prefers-reduced-motion: reduce) {{
    * {{ animation-duration:.01ms !important; animation-iteration-count:1 !important; }}
    .fade, .rise, .build {{ opacity:1 !important; transform:none !important; }}
  }}
"""


def svg_open(w, h, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="{esc(title)}">'
            f'<title>{esc(title)}</title>')
