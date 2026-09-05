"""Builds assets/id-card.svg - a frosted-glass profile panel.

Static by design. The panel holds facts that change on the order of years, so it
is generated once and committed rather than rebuilt nightly; that keeps the hero
image alive even if the panel workflow ever fails. Re-run this script after
changing your avatar or any field below.

    python .github/scripts/build_idcard.py

The panel itself is still: a frosted sheet with a turbulence grain, a single
soft white highlight where light would hit the glass, a bright rim, and one
diagonal gloss sweep laid on top like lacquer — all static gradients and
filters, no motion. The only thing that moves is the photo, which gets a slow
light sheen sliding down behind the clip.
"""

import base64
import pathlib

from theme import MONO, SANS, esc, rect, svg_open, text

HERE = pathlib.Path(__file__).parent
OUT = HERE.parent.parent / "assets" / "id-card.svg"

# -- Palette ------------------------------------------------------------------
# Rose-red and white only — no blue/cyan/purple/green. Four shades of rose
# carry the category accents; every other line of text is white at a weight
# chosen for hierarchy (full opacity for values, faded for small caps labels).
ROSE      = "#f7768e"     # base rose-red
ROSE_SOFT = "#ff9bb0"     # lightest — LANGUAGES
ROSE_MID  = "#e2597a"     # mid       — DATABASES
ROSE_DEEP = "#c9445f"     # deepest   — WEB
WHITE     = "#f5f5f6"
LABEL_OP  = 0.44           # small-caps section labels: white, faded
VALUE_OP  = 0.88           # body copy: white, near-solid

# -- Panel contents ----------------------------------------------------------
NAME     = "Nishanth S"
LOCATION = "Bengaluru, India"
GENDER   = "Male"
ABOUT = [
    "Applied AI engineer. I build agentic systems and RAG pipelines — and the",
    "database internals underneath them when the abstraction has to come off.",
]

# Vertical katakana down the right gutter - the name, transliterated. Ties the
# panel to the README's opening greeting.
KANA = "ニシャント"

SKILLS = [
    ("LANGUAGES", ROSE_SOFT, [
        "Python", "C", "SQL"]),
    ("DATABASES", ROSE_MID, [
        "PostgreSQL", "MySQL", "MongoDB", "ChromaDB"]),
    ("WEB", ROSE_DEEP, [
        "FastAPI", "Flask", "React", "Next.js", "TypeScript", "Tailwind CSS",
        "REST APIs", "WebSockets", "SSE", "Gradio"]),
    ("AI / ML", ROSE, [
        "PyTorch", "TensorFlow", "Scikit-learn", "XGBoost",
        "Hugging Face Transformers", "Torchvision", "Ultralytics", "OpenCV",
        "NLTK", "spaCy", "LibROSA",
        "Unsloth", "PEFT", "ONNX Runtime", "vLLM", "SentenceTransformers",
        "LangChain", "LangGraph", "LlamaIndex", "TRL",
        "RAG", "Agentic Workflows", "LoRA/QLoRA", "4-bit Quantization",
        "Flash Attention", "Transfer Learning", "Knowledge Distillation",
        "Multimodal Learning", "MCP"]),
]

# No webfont can be fetched from inside an <img>-loaded SVG, so the CJK stack is
# built entirely from faces that ship with Windows, macOS and most Linux distros.
JP = ("'Yu Gothic','Hiragino Kaku Gothic ProN','Hiragino Sans','Noto Sans JP',"
      "'Noto Sans CJK JP',Meiryo,'MS PGothic',sans-serif")

# -- Geometry -----------------------------------------------------------------
W       = 880
PX, PY  = 26, 26
PW      = W - 2 * PX
RX      = 24
PAD     = 32
L       = PX + PAD                # content left edge
R       = PX + PW - PAD           # content right edge

PHOTO_S = 148
PHOTO_X, PHOTO_Y = L, PY + 30
FIELD_X = PHOTO_X + PHOTO_S + 28

# mascot badge, top-right — robot.png is a pre-cut 520x300 (26:15) transparent
# PNG; sized down to sit clear of both the field column and the kana gutter
ROBOT_W  = 165
ROBOT_H  = round(ROBOT_W * 300 / 520)
ROBOT_X  = R - ROBOT_W - 22
ROBOT_Y  = PY + 24

NAME_LBL_Y  = PHOTO_Y + 6
NAME_Y      = PHOTO_Y + 40
RULE1_Y     = PHOTO_Y + 56
LG_LBL_Y    = PHOTO_Y + 78
LG_VAL_Y    = PHOTO_Y + 99
ABOUT_LBL_Y = PHOTO_Y + 124
ABOUT_Y0    = PHOTO_Y + 146
ABOUT_LH    = 18

DIVIDER_Y = max(PHOTO_Y + PHOTO_S, ABOUT_Y0 + (len(ABOUT) - 1) * ABOUT_LH + 14) + 20
SKILL_TOP = DIVIDER_Y + 28

VAL_X   = L + 96
VAL_W   = R - VAL_X
VAL_SZ  = 12
LH      = 16.5
ROW_GAP = 12

CHW = 0.60                        # mono advance width, as a fraction of em


def wrap(items, width, size, sep=" · "):
    """Greedy-wrap `items` into lines that fit `width` px at `size`."""
    adv = size * CHW
    lines, cur = [], ""
    for it in items:
        trial = it if not cur else cur + sep + it
        if cur and len(trial) * adv > width:
            lines.append(cur)
            cur = it
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def pill(x, y, w, h, colour, r=None):
    """A small glass chip: a colour-tinted rounded rect with a hairline
    border, echoing pill-shaped tags on a frosted surface. Static — no glow
    animation, just the shape."""
    r = h / 2 if r is None else r
    return (rect(x, y, w, h, rx=r, fill=colour, opacity=0.16)
            + rect(x, y, w, h, rx=r, fill="none", stroke=colour, sw=1, opacity=0.55))


def defs(PH):
    return (
        '<defs>'
        '<clipPath id="panel"><rect x="%d" y="%d" width="%d" height="%d" rx="%d"/></clipPath>'
        '<clipPath id="photo"><rect x="%d" y="%d" width="%d" height="%d" rx="20"/></clipPath>'

        '<linearGradient id="canvas" x1="0" y1="0" x2="0.4" y2="1">'
        '<stop offset="0%%" stop-color="#0c0c0e"/>'
        '<stop offset="100%%" stop-color="#131315"/></linearGradient>'

        # the one highlight where light lands on the glass — neutral white;
        # this plus the frost grain is the entire "glass" cue, no tint blob
        '<radialGradient id="highlight" cx="0.5" cy="0.5" r="0.5">'
        '<stop offset="0%%" stop-color="#ffffff" stop-opacity="0.24"/>'
        '<stop offset="55%%" stop-color="#ffffff" stop-opacity="0.08"/>'
        '<stop offset="100%%" stop-color="#ffffff" stop-opacity="0"/></radialGradient>'

        # the sheet itself: a hair of white, brighter at the top — no colour
        '<linearGradient id="glass" x1="0" y1="0" x2="0.25" y2="1">'
        '<stop offset="0%%" stop-color="#ffffff" stop-opacity="0.16"/>'
        '<stop offset="55%%" stop-color="#ffffff" stop-opacity="0.07"/>'
        '<stop offset="100%%" stop-color="#ffffff" stop-opacity="0.04"/></linearGradient>'

        # one wide diagonal highlight across the top-left third — the lacquer
        '<linearGradient id="gloss" x1="0" y1="0" x2="1" y2="0.9">'
        '<stop offset="0%%" stop-color="#ffffff" stop-opacity="0"/>'
        '<stop offset="10%%" stop-color="#ffffff" stop-opacity="0.07"/>'
        '<stop offset="24%%" stop-color="#ffffff" stop-opacity="0.035"/>'
        '<stop offset="40%%" stop-color="#ffffff" stop-opacity="0"/>'
        '<stop offset="100%%" stop-color="#ffffff" stop-opacity="0"/></linearGradient>'

        '<linearGradient id="rim" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0%%" stop-color="#ffffff" stop-opacity="0.40"/>'
        '<stop offset="42%%" stop-color="#ffffff" stop-opacity="0.08"/>'
        '<stop offset="100%%" stop-color="#ffffff" stop-opacity="0.22"/></linearGradient>'
        '<linearGradient id="topline" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%%" stop-color="#ffffff" stop-opacity="0"/>'
        '<stop offset="28%%" stop-color="#ffffff" stop-opacity="0.38"/>'
        '<stop offset="72%%" stop-color="#ffffff" stop-opacity="0.16"/>'
        '<stop offset="100%%" stop-color="#ffffff" stop-opacity="0"/></linearGradient>'
        '<linearGradient id="hair" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%%" stop-color="#ffffff" stop-opacity="0.16"/>'
        '<stop offset="100%%" stop-color="#ffffff" stop-opacity="0.02"/></linearGradient>'

        '<linearGradient id="namefade" gradientUnits="userSpaceOnUse" '
        'x1="%d" y1="0" x2="%d" y2="0">'
        '<stop offset="0%%" stop-color="{WHITE}"/>'
        '<stop offset="100%%" stop-color="{ROSE}"/></linearGradient>'

        '<linearGradient id="pring" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0%%" stop-color="#ffffff" stop-opacity="0.32"/>'
        '<stop offset="55%%" stop-color="#ffffff" stop-opacity="0.05"/>'
        '<stop offset="100%%" stop-color="#ffffff" stop-opacity="0.18"/></linearGradient>'
        '<linearGradient id="psheen" x1="0" y1="0" x2="0.7" y2="1">'
        '<stop offset="0%%" stop-color="#ffffff" stop-opacity="0.18"/>'
        '<stop offset="42%%" stop-color="#ffffff" stop-opacity="0"/></linearGradient>'

        # frost: fine achromatic grain over the whole sheet — this is the
        # single most important cue for "glass" rather than "flat panel"
        '<filter id="grain" x="0%%" y="0%%" width="100%%" height="100%%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" '
        'stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter>'
        '<filter id="drop" x="-20%%" y="-20%%" width="140%%" height="140%%">'
        '<feDropShadow dx="0" dy="16" stdDeviation="22" flood-color="#000000" '
        'flood-opacity="0.5"/></filter>'
        '<pattern id="grid" width="26" height="26" patternUnits="userSpaceOnUse">'
        '<path d="M26 0 H0 V26" fill="none" stroke="#ffffff" stroke-width="0.5" '
        'opacity="0.045"/></pattern>'
        '</defs>'
    ).format(WHITE=WHITE, ROSE=ROSE) % (
        PX, PY, PW, PH, RX,
        PHOTO_X, PHOTO_Y, PHOTO_S, PHOTO_S,
        FIELD_X, FIELD_X + 260,
    )


# The only motion left in the whole file: a slow light sheen sliding down
# behind the photo's clip. Everything else in the panel is still.
STYLE = '''<style>
  .psweep { animation:psweep 4.2s cubic-bezier(.4,0,.3,1) infinite; }
  @keyframes psweep { 0% { transform:translateY(-160px); }
                       55%,100% { transform:translateY(160px); } }
  @media (prefers-reduced-motion: reduce) {
    .psweep { animation:none; }
  }
</style>'''


def build():
    b64 = base64.b64encode((HERE / "avatar.jpg").read_bytes()).decode()
    rb64 = base64.b64encode((HERE / "robot.png").read_bytes()).decode()

    rows, y = [], SKILL_TOP
    for lab, colour, items in SKILLS:
        lines = wrap(items, VAL_W, VAL_SZ)
        rows.append((lab, colour, lines, y))
        y += len(lines) * LH + ROW_GAP
    PB = round(y - ROW_GAP - LH + 6 + PAD)
    PH = PB - PY
    H = PB + PX

    o = [svg_open(W, H, NAME + " - profile")]
    o.append(defs(PH))
    o.append(STYLE)

    # -- ground + the sheet ---------------------------------------------------
    o.append(rect(0, 0, W, H, fill="url(#canvas)", rx=18))
    o.append(rect(PX, PY, PW, PH, rx=RX, fill="#151517", opacity=0.92,
                  style="filter:url(#drop)"))

    o.append('<g clip-path="url(#panel)">')
    # the one light landing on the glass — static, neutral white, no tint
    o.append('<ellipse cx="130" cy="70" rx="280" ry="220" fill="url(#highlight)"/>')

    o.append(rect(PX, PY, PW, PH, fill="url(#glass)"))
    o.append(rect(PX, PY, PW, PH, fill="#808080", opacity=0.055, style="filter:url(#grain)"))
    o.append(rect(PX, PY, PW, PH, fill="url(#grid)"))

    # katakana sublayer down the right gutter
    kx = PX + PW - 24
    ky = int((PY + PB) / 2 - (len(KANA) - 1) * 19) + 6
    for i, ch in enumerate(KANA):
        o.append('<text x="' + str(kx) + '" y="' + str(ky + i * 38) + '" font-family="'
                 + JP + '" font-size="24" fill="#ffffff" opacity="0.08" '
                 'text-anchor="middle">' + esc(ch) + '</text>')

    # -- photo — the one place motion still lives ------------------------
    o.append('<g clip-path="url(#photo)">')
    o.append('<image x="' + str(PHOTO_X) + '" y="' + str(PHOTO_Y) + '" width="'
             + str(PHOTO_S) + '" height="' + str(PHOTO_S)
             + '" preserveAspectRatio="xMidYMid slice" '
               'xlink:href="data:image/jpeg;base64,' + b64 + '"/>')
    o.append('<g class="psweep">' + rect(PHOTO_X, PHOTO_Y - 40, PHOTO_S, 60,
                                        fill="url(#psheen)") + '</g>')
    o.append('</g>')
    o.append(rect(PHOTO_X, PHOTO_Y, PHOTO_S, PHOTO_S, rx=20, fill="none",
                  stroke="url(#pring)", sw=1.4))

    # -- mascot badge, top-right — static, pre-cut transparent PNG ----------
    o.append('<image x="' + str(ROBOT_X) + '" y="' + str(ROBOT_Y) + '" width="'
             + str(ROBOT_W) + '" height="' + str(ROBOT_H)
             + '" preserveAspectRatio="xMidYMid meet" '
               'xlink:href="data:image/png;base64,' + rb64 + '"/>')

    # -- fields ----------------------------------------------------------
    o.append(text(FIELD_X, NAME_LBL_Y, "NAME", size=9.5, fill=WHITE, spacing=3.2,
                  opacity=LABEL_OP))
    o.append('<text x="' + str(FIELD_X) + '" y="' + str(NAME_Y) + '" font-family="' + SANS
             + '" font-size="30" font-weight="800" fill="url(#namefade)" '
               'letter-spacing="-1.1">' + esc(NAME) + '</text>')
    o.append('<path d="M' + str(FIELD_X) + ' ' + str(RULE1_Y) + ' H' + str(R)
             + '" stroke="url(#hair)" stroke-width="1"/>')

    for lx, lab, val in ((FIELD_X, "LOCATION", LOCATION), (FIELD_X + 220, "GENDER", GENDER)):
        o.append(text(lx, LG_LBL_Y, lab, size=9.5, fill=WHITE, spacing=3.2, opacity=LABEL_OP))
        o.append(text(lx, LG_VAL_Y, val, size=13.5, fill=WHITE, opacity=VALUE_OP))

    o.append(text(FIELD_X, ABOUT_LBL_Y, "ABOUT", size=9.5, fill=WHITE, spacing=3.2,
                  opacity=LABEL_OP))
    for i, line in enumerate(ABOUT):
        o.append('<text x="' + str(FIELD_X) + '" y="' + str(ABOUT_Y0 + i * ABOUT_LH)
                 + '" font-family="' + SANS + '" font-style="italic" font-size="13" fill="'
                 + WHITE + '" opacity="' + str(VALUE_OP) + '">' + esc(line) + '</text>')

    # -- skills, category labels as small static glass chips ----------------
    o.append('<path d="M' + str(L) + ' ' + str(DIVIDER_Y) + ' H' + str(R)
             + '" stroke="url(#hair)" stroke-width="1"/>')
    for lab, colour, lines, ry in rows:
        chip_w = 14 + len(lab) * 6.6
        o.append(pill(L, ry - 12, chip_w, 17, colour))
        o.append(text(L + 8, ry, lab, size=9, fill=colour, spacing=1.2, weight=600))
        for i, line in enumerate(lines):
            o.append(text(VAL_X, ry + i * LH, line, size=VAL_SZ, fill=WHITE, opacity=VALUE_OP))

    o.append('</g>')

    # -- rim + top specular line, outside the clip ---------------------------
    o.append(rect(PX, PY, PW, PH, rx=RX, fill="none", stroke="url(#rim)", sw=1.2))
    o.append('<path d="M' + str(PX + 34) + ' ' + str(PY + 1) + ' H' + str(PX + PW - 34)
             + '" stroke="url(#topline)" stroke-width="1.2"/>')
    # the gloss sits on top of everything, as lacquer would — static
    o.append('<g clip-path="url(#panel)" style="mix-blend-mode:overlay">'
             + rect(PX, PY, PW, PH, fill="url(#gloss)") + '</g>')

    o.append('</svg>')
    return "\n".join(o)


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf8")
    print("wrote " + str(OUT) + "  (" + format(OUT.stat().st_size, ",") + " bytes)")
