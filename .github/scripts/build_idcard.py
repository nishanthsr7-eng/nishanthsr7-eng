"""Builds assets/id-card.svg - a torii-at-dusk scene carrying name, location,
gender and about.

Static by design. The card holds facts that change on the order of years, so it
is generated once and committed rather than rebuilt nightly; that keeps the hero
image alive even if the panel workflow ever fails. Re-run this script after
changing any field below.

    python .github/scripts/build_idcard.py

Depth comes from layering, back to front: sky and a few stars, a rose sun with
cloud bands drifting across it, a far range, Fuji, a pagoda hill, far mist, the
near ridge, water, the torii on its rocks, near mist, a small flock of birds, and
a cherry branch swaying in from the top-right corner. Each nearer layer is darker
and moves faster. Petals fall over everything. All motion is CSS keyframes, so
it runs inside GitHub's <img> context; nothing here fetches fonts or images.
"""

import pathlib
import random

from theme import BG, LINE, MONO, WHITE, esc

HERE = pathlib.Path(__file__).parent
OUT = HERE.parent.parent / "assets" / "id-card.svg"

# -- Card contents ------------------------------------------------------------
NAME     = "Nishanth S"
LOCATION = "Bengaluru, India"
GENDER   = "Male"
ABOUT    = "AIML Engineer · Product and Web Designer · Full-Stack Developer"
KANA     = "ニシャント"          # the name, transliterated, down the left edge
GREETING = "ようこそ"

ACCENT = "#e07a90"                # a quieter rose, for the kana and rule only

# Every face here ships with Windows/macOS - an <img>-loaded SVG can't fetch fonts.
MINCHO = ("'Yu Mincho',YuMincho,'Hiragino Mincho ProN','Noto Serif JP','Noto Serif CJK JP',"
          "'MS PMincho',serif")

# -- Geometry -----------------------------------------------------------------
W, H = 880, 360
HZ = 252                          # horizon
SX, SY, SR = 702, 168, 60         # sun
TX = 702                          # torii centre

CSS = """
  .rise { opacity:0; animation:rise .9s cubic-bezier(.2,.7,.3,1) forwards; }
  .grow { transform-box:fill-box; transform-origin:0 50%; transform:scaleX(0);
          animation:grow 1s cubic-bezier(.2,.7,.3,1) forwards; }
  .tw   { animation:tw 3.2s ease-in-out infinite; }
  .vk   { writing-mode:vertical-rl; }
  @keyframes rise { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
  @keyframes grow { to { transform:scaleX(1); } }
  @keyframes tw   { 0%,100% { opacity:.15; } 50% { opacity:.9; } }

  .sun  { transform-box:fill-box; transform-origin:center; animation:sun 9s ease-in-out infinite; }
  @keyframes sun { 0%,100% { opacity:.55; transform:scale(1); } 50% { opacity:.8; transform:scale(1.06); } }
  .cloud { animation:cloud ease-in-out infinite alternate; }
  @keyframes cloud { from { transform:translateX(-50px); } to { transform:translateX(50px); } }
  .mist { animation:mist ease-in-out infinite alternate; }
  @keyframes mist { from { transform:translateX(-60px); opacity:.6; } to { transform:translateX(60px); opacity:1; } }
  .branch { transform-origin:880px 0px; animation:sway 7s ease-in-out infinite; }
  @keyframes sway { 0%,100% { transform:rotate(-1.4deg); } 50% { transform:rotate(1.6deg); } }
  .bloom { transform-box:fill-box; transform-origin:center; animation:bloom 4s ease-in-out infinite; }
  @keyframes bloom { 0%,100% { transform:scale(1); } 50% { transform:scale(1.08); } }
  .fly { animation:fly linear infinite; }
  @keyframes fly { 0% { transform:translate(0,0); opacity:0; } 10% { opacity:.7; } 85% { opacity:.7; }
                   100% { transform:translate(-400px,-26px); opacity:0; } }
  .flap { transform-box:fill-box; transform-origin:center; animation:flap .7s ease-in-out infinite; }
  @keyframes flap { 0%,100% { transform:scaleY(1); } 50% { transform:scaleY(-.5); } }
  .petal { animation:fall linear infinite; }
  @keyframes fall { 0%   { transform:translate(0,-40px) rotate(0deg); opacity:0; }
                    8%   { opacity:1; }
                    50%  { transform:translate(-70px,180px) rotate(200deg); }
                    92%  { opacity:1; }
                    100% { transform:translate(-150px,420px) rotate(420deg); opacity:0; } }

  @media (prefers-reduced-motion: reduce) {
    * { animation-duration:.01ms !important; animation-iteration-count:1 !important; }
    .rise { opacity:1 !important; transform:none !important; }
  }
"""


# -- Scenery ------------------------------------------------------------------

def stars(n, seed, y_max, x_min=0, x_max=W, r=(0.5, 1.1)):
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        cx, cy = rnd.uniform(x_min, x_max), rnd.uniform(8, y_max)
        rr = rnd.uniform(*r)
        out.append(f'<circle class="tw" style="animation-delay:-{rnd.uniform(0, 3.2):.2f}s;'
                   f'animation-duration:{rnd.uniform(2.4, 4.8):.1f}s" cx="{cx:.1f}" '
                   f'cy="{cy:.1f}" r="{rr:.2f}" fill="{WHITE}"/>')
    return "".join(out)


def mountains(pts, fill, op=1):
    d = f"M{pts[0][0]},{HZ} " + " ".join(f"L{x},{y}" for x, y in pts) + f" L{pts[-1][0]},{HZ} Z"
    return f'<path d="{d}" fill="{fill}" opacity="{op}"/>'


def torii(cx, base, h):
    """Torii silhouette centred on cx, standing on y=base, height h."""
    pw, sp, top = 7, 36, base - h
    return (
        f'<rect x="{cx-sp-pw/2}" y="{top+12}" width="{pw}" height="{h-12}"/>'
        f'<rect x="{cx+sp-pw/2}" y="{top+12}" width="{pw}" height="{h-12}"/>'
        f'<path d="M{cx-64},{top-4} Q{cx},{top+6} {cx+64},{top-4} L{cx+58},{top+6} '
        f'Q{cx},{top+13} {cx-58},{top+6} Z"/>'
        f'<rect x="{cx-52}" y="{top+22}" width="104" height="6"/>'
        f'<rect x="{cx-3}" y="{top+10}" width="6" height="13"/>'
    )


def pagoda(cx, base, s=1.0):
    """Five-tier pagoda silhouette standing on (cx, base)."""
    out = []
    y = base
    for i in range(5):
        bw = (15 - i * 2) * s                  # body width
        rw = (22 - i * 2.6) * s                # roof half-width
        bh, rh = 7 * s, 4 * s
        out.append(f'<rect x="{cx-bw/2:.1f}" y="{y-bh:.1f}" width="{bw:.1f}" height="{bh:.1f}"/>')
        y -= bh
        out.append(f'<path d="M{cx-rw:.1f},{y-1*s:.1f} Q{cx-rw*.6:.1f},{y:.1f} {cx-rw*.45:.1f},{y-rh*.4:.1f} '
                   f'L{cx:.1f},{y-rh:.1f} L{cx+rw*.45:.1f},{y-rh*.4:.1f} Q{cx+rw*.6:.1f},{y:.1f} '
                   f'{cx+rw:.1f},{y-1*s:.1f} Z"/>')
        y -= rh
    out.append(f'<rect x="{cx-.8*s:.1f}" y="{y-14*s:.1f}" width="{1.6*s:.1f}" height="{14*s:.1f}"/>')
    for k in range(3):
        out.append(f'<rect x="{cx-2.2*s:.1f}" y="{y-(4+k*3.5)*s:.1f}" width="{4.4*s:.1f}" height="{1*s:.1f}"/>')
    return "".join(out)


def cloud(cx, cy, w, h, fill, op, dur, delay):
    """A long, flat cloud bank built from overlapping ellipses."""
    parts = [f'<ellipse cx="{cx}" cy="{cy}" rx="{w/2}" ry="{h/2}"/>',
             f'<ellipse cx="{cx-w*.18:.0f}" cy="{cy-h*.35:.1f}" rx="{w*.22:.0f}" ry="{h*.5:.1f}"/>',
             f'<ellipse cx="{cx+w*.12:.0f}" cy="{cy-h*.45:.1f}" rx="{w*.18:.0f}" ry="{h*.55:.1f}"/>']
    return (f'<g class="cloud" style="animation-duration:{dur}s;animation-delay:-{delay}s" '
            f'fill="{fill}" opacity="{op}">{"".join(parts)}</g>')


def branch():
    """Cherry branch reaching in from the top-right corner, swaying."""
    limbs = [
        "M890,-6 C860,10 830,18 800,22 C780,25 764,34 752,48",
        "M842,14 C836,30 826,42 812,52",
        "M800,22 C792,12 782,8 768,8",
        "M776,30 C770,44 772,56 764,70",
    ]
    out = [f'<path d="{d}" fill="none" stroke="#0a080c" stroke-width="{w}" stroke-linecap="round"/>'
           for d, w in zip(limbs, (5, 3, 2.5, 2))]
    rnd = random.Random(8)
    tips = [(752, 48), (812, 52), (768, 8), (764, 70), (800, 22), (842, 14), (786, 26), (826, 40)]
    for i, (x, y) in enumerate(tips):
        g = []
        for _ in range(rnd.randint(4, 7)):
            dx, dy = rnd.uniform(-9, 9), rnd.uniform(-7, 7)
            col = rnd.choice(("#e9a9b9", "#d98ea2", "#f3c9d3", "#b8667e"))
            g.append(f'<circle cx="{x+dx:.1f}" cy="{y+dy:.1f}" r="{rnd.uniform(2.2, 4.2):.1f}" fill="{col}"/>')
        out.append(f'<g class="bloom" style="animation-delay:-{i*.5:.1f}s" opacity=".85">{"".join(g)}</g>')
    # scaled up from the corner so it reads as the nearest layer
    return (f'<g transform="translate(880,0) scale(1.7) translate(-880,0)">'
            f'<g class="branch">{"".join(out)}</g></g>')


def birds():
    out = []
    for i, (x, y, sc, dur, dl) in enumerate([(880, 92, 1, 34, 0), (900, 100, .8, 34, 1.2),
                                             (916, 88, .7, 34, 2.1), (880, 60, .6, 46, 22)]):
        out.append(
            f'<g class="fly" style="animation-duration:{dur}s;animation-delay:-{dl}s">'
            f'<g transform="translate({x},{y}) scale({sc})"><path class="flap" style="animation-delay:-{i*.2:.1f}s" '
            'd="M-7,0 Q-3.5,-4 0,0 Q3.5,-4 7,0" fill="none" stroke="#d9c2cb" stroke-width="1.2" '
            'stroke-linecap="round"/></g></g>')
    return "".join(out)


def petals():
    rnd = random.Random(21)
    out = []
    for _ in range(16):
        depth = rnd.choice([0, 0, 1, 1, 2])
        sc = (.8, 1.2, 1.7)[depth]
        dur = (15, 11, 8)[depth] + rnd.uniform(-1.5, 1.5)
        op = (.3, .45, .65)[depth]
        x = rnd.uniform(60, W + 120)
        out.append(f'<g transform="translate({x:.0f},0)"><g class="petal" '
                   f'style="animation-duration:{dur:.1f}s;animation-delay:-{rnd.uniform(0, dur):.1f}s">'
                   f'<use href="#petal" transform="scale({sc})" fill="#f3c9d3" opacity="{op}"/></g></g>')
    return "".join(out)


def scene():
    b = [
        '<defs>'
        '<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#0d1117"/><stop offset=".5" stop-color="#16121c"/>'
        '<stop offset=".8" stop-color="#2a1726"/><stop offset="1" stop-color="#361b2c"/></linearGradient>'
        '<linearGradient id="water" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#1e1320"/><stop offset="1" stop-color="#0c0d12"/></linearGradient>'
        '<radialGradient id="glow"><stop offset="0" stop-color="#e07a90" stop-opacity=".26"/>'
        '<stop offset="1" stop-color="#e07a90" stop-opacity="0"/></radialGradient>'
        '<linearGradient id="disc" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f6d6de"/>'
        '<stop offset="1" stop-color="#b8566f"/></linearGradient>'
        '<radialGradient id="fog"><stop offset="0" stop-color="#e8c3cf" stop-opacity=".16"/>'
        '<stop offset="1" stop-color="#e8c3cf" stop-opacity="0"/></radialGradient>'
        f'<clipPath id="skyclip"><rect width="{W}" height="{HZ}"/></clipPath>'
        '<path id="petal" d="M0,-4 C3,-3 3.5,2 0,4 C-3.5,2 -3,-3 0,-4 Z"/>'
        '</defs>',
        f'<rect width="{W}" height="{H}" fill="url(#sky)"/>',
        stars(14, 3, 140, x_min=360),
        f'<g clip-path="url(#skyclip)">'
        f'<circle class="sun" cx="{SX}" cy="{SY}" r="150" fill="url(#glow)"/>'
        f'<circle cx="{SX}" cy="{SY}" r="{SR}" fill="url(#disc)" opacity=".85"/>'
        + cloud(690, 150, 190, 9, "#2c1b29", .85, 26, 0)
        + cloud(730, 186, 240, 11, "#301d2c", .9, 34, 12)
        + cloud(560, 118, 140, 7, "#241824", .6, 30, 6)
        + '</g>',
        # far range - palest, lowest contrast
        mountains([(330, HZ), (400, HZ-26), (450, HZ-18), (520, HZ-40), (600, HZ-30), (680, HZ-52),
                   (760, HZ-34), (820, HZ-46), (880, HZ-30)], "#2f1f2e", .7),
        # fuji
        f'<path d="M380,{HZ} L490,{HZ-44} Q530,{HZ-78} 558,{HZ-86} L580,{HZ-86} Q610,{HZ-76} 650,{HZ-46} '
        f'L880,{HZ-18} L880,{HZ} Z" fill="#261a26"/>'
        f'<path d="M542,{HZ-80} L558,{HZ-86} L580,{HZ-86} L594,{HZ-80} L582,{HZ-74} L570,{HZ-79} '
        f'L556,{HZ-73} Z" fill="#cfc6ca" opacity=".3"/>',
        # pagoda hill
        f'<path d="M740,{HZ} Q790,{HZ-34} 830,{HZ-36} Q862,{HZ-36} 890,{HZ-24} L890,{HZ} Z" fill="#150f16"/>'
        f'<g fill="#150f16">{pagoda(824, HZ - 34, 1.25)}</g>',
        # far mist between fuji and the ridge
        f'<ellipse class="mist" style="animation-duration:18s" cx="600" cy="{HZ-8}" rx="300" ry="16" fill="url(#fog)"/>',
        # near ridge
        f'<path d="M400,{HZ} Q490,{HZ-30} 560,{HZ-16} Q620,{HZ-6} 660,{HZ-4} L880,{HZ-10} L880,{HZ} Z" fill="#1a121a"/>',
        f'<rect y="{HZ}" width="{W}" height="{H-HZ}" fill="url(#water)"/>',
    ]
    tb, th = HZ + 12, 116
    b.append(f'<g fill="#0b0a0e">{torii(TX, tb, th)}'
             f'<ellipse cx="{TX-36}" cy="{tb+1}" rx="13" ry="4"/><ellipse cx="{TX+36}" cy="{tb+1}" rx="13" ry="4"/>'
             f'<ellipse cx="{TX-22}" cy="{tb+3}" rx="7" ry="2.5"/><ellipse cx="{TX+52}" cy="{tb+2}" rx="6" ry="2"/></g>')
    # near mist over the water, drifting the other way and faster
    b.append(f'<ellipse class="mist" style="animation-duration:11s;animation-direction:alternate-reverse" '
             f'cx="{TX}" cy="{tb+8}" rx="220" ry="12" fill="url(#fog)"/>')
    b.append(birds())
    b.append(branch())
    return "".join(b)


# -- Text ---------------------------------------------------------------------

def rise(delay, inner):
    return f'<g class="rise" style="animation-delay:{delay:.2f}s">{inner}</g>'


def t(x, y, s, *, fam=MINCHO, size, fill=WHITE, op=None, weight=None, sp=None):
    a = [f'x="{x}"', f'y="{y}"', f'font-family="{fam}"', f'font-size="{size}"', f'fill="{fill}"']
    if op is not None:
        a.append(f'opacity="{op}"')
    if weight:
        a.append(f'font-weight="{weight}"')
    if sp is not None:
        a.append(f'letter-spacing="{sp}"')
    return f'<text {" ".join(a)}>{esc(s)}</text>'


def label(x, y, s):
    return t(x, y, s, fam=MONO, size=10, op=.42, sp=3)


def text_layer():
    """Vertical katakana down the left edge, about as a tagline under the
    name, location/gender as a quiet footer pair - staggered in on load."""
    x = 108
    kana = (f'<text class="vk" x="66" y="72" font-family="{MINCHO}" font-size="13" fill="{ACCENT}" '
            f'opacity=".7" letter-spacing="9">{esc(KANA)}</text>')
    return "".join([
        rise(.1, kana + f'<rect x="65" y="172" width="1" height="120" fill="{WHITE}" opacity=".12"/>'),
        rise(.22, t(x, 88, GREETING, size=11.5, op=.45, sp=8)),
        rise(.34, t(x - 1, 136, NAME, size=42, weight=600)),
        f'<rect class="grow" style="animation-delay:.55s" x="{x}" y="158" width="34" height="2" '
        f'rx="1" fill="{ACCENT}"/>',
        rise(.66, label(x, 200, "ABOUT") + t(x, 222, ABOUT, size=13.5, op=.88)),
        rise(.8, label(x, 270, "LOCATION") + t(x, 292, LOCATION, size=14.5, op=.92)),
        rise(.92, label(x + 210, 270, "GENDER") + t(x + 210, 292, GENDER, size=14.5, op=.92)),
    ])


def build():
    title = f"{NAME} - {LOCATION} - {ABOUT}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'role="img" aria-label="{esc(title)}"><title>{esc(title)}</title>'
        f'<style>{CSS}</style>'
        f'<defs><clipPath id="frame"><rect x="1" y="1" width="{W-2}" height="{H-2}" rx="18"/></clipPath></defs>'
        f'<rect width="{W}" height="{H}" rx="18" fill="{BG}"/>'
        f'<g clip-path="url(#frame)">{scene()}{text_layer()}{petals()}</g>'
        f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="18" fill="none" stroke="{LINE}"/>'
        '</svg>'
    )


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf8")
    print("wrote " + str(OUT) + "  (" + format(OUT.stat().st_size, ",") + " bytes)")
