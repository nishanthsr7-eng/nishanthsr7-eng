"""Builds assets/yokoso.svg - the README's rose-red greeting.

GitHub's markdown sanitizer strips `style` attributes from raw HTML in a
README, so `<span style="color:...">` silently renders in the default text
colour. An inline SVG has no such restriction, so the greeting is a tiny
standalone image instead of styled text.

    python .github/scripts/build_yokoso.py
"""

import pathlib

from theme import ROSE, esc

HERE = pathlib.Path(__file__).parent
OUT = HERE.parent.parent / "assets" / "yokoso.svg"

TEXT = "ようこそ"
SIZE = 34
JP = ("'Yu Gothic','Hiragino Kaku Gothic ProN','Hiragino Sans','Noto Sans JP',"
      "'Noto Sans CJK JP',Meiryo,'MS PGothic',sans-serif")

W, H = len(TEXT) * SIZE + 16, SIZE + 24


def build():
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" aria-label="{esc(TEXT)}">'
        f'<text x="{W / 2}" y="{H / 2 + SIZE * 0.36}" text-anchor="middle" '
        f'font-family="{JP}" font-size="{SIZE}" font-weight="600" '
        f'fill="{ROSE}">{esc(TEXT)}</text></svg>'
    )


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf8")
    print("wrote " + str(OUT) + "  (" + format(OUT.stat().st_size, ",") + " bytes)")
