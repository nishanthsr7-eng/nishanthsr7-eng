"""Builds two SVGs for section 2 of the profile README: the contribution
calendar and the activity graph — nothing else.

    python .github/scripts/build_panels.py --out dist

With GITHUB_TOKEN set it reads GitHub's GraphQL API. Without one it falls back
to the public REST API plus the contributions HTML fragment, which is enough to
render everything locally for design work.

Style is flat and mostly neutral (white/gray on near-black, matched to the
id-card's canvas), with the rose-red accent spent sparingly — one highlight
per chart (the best day, the peak point) rather than colouring everything.
No card borders, no per-section icons or headings, just the two charts.

Output: dist/contribution-calendar.svg (last 6 months, as a small isometric
skyline — one extruded tile per day) and dist/activity-graph.svg (the
12-month trend line), both self-contained SVGs that animate inside an <img>.
"""

import argparse
import collections
import datetime as dt
import json
import os
import pathlib
import re
import urllib.request

from theme import BG, LINE, DIM, MUTED, WHITE, ROSE, SANS, BASE_CSS, rect, svg_open, text

USER = "nishanthsr7-eng"
API = "https://api.github.com"

# Shared canvas width — matched to the id-card so both sit flush in the README.
W = 880
L, R = 40, 840
CW = R - L

CAL_DAYS = 182                            # ~6 months


# ── vendored code ─────────────────────────────────────────────────────────────
# GitHub's language stats count every byte in the tree, including third-party
# code that was checked in wholesale. Video_Editor-MCP vendors `auto-subs`
# (its own MIT licence, dated 2023 — before this account existed), and every
# Rust, C++ and TypeScript file in that repository lives inside it. Counting
# them would credit ~1.4 MB of somebody else's work, so only the Python MCP
# tools that are actually authored here are kept.
VENDORED_KEEP = {"Video_Editor-MCP": {"Python"}}

# Markup and build glue are not the point of a languages panel.
IGNORE_LANGS = {"HTML", "CSS", "SCSS", "Batchfile", "Shell", "Makefile",
                "CMake", "NSIS", "PowerShell", "Dockerfile", "C"}

# ═══════════════════════════════════════════════════════════════ data ════════

def _get(url, token=None, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={
        "User-Agent": "profile-panels", "Accept": accept,
        **({"Authorization": "Bearer " + token} if token else {})})
    return urllib.request.urlopen(req, timeout=45).read()


def _graphql(token, query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API + "/graphql", data=body, headers={
        "User-Agent": "profile-panels", "Authorization": "Bearer " + token,
        "Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(req, timeout=45).read())
    if "errors" in out:
        raise RuntimeError(out["errors"])
    return out["data"]


GQL = """
query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){
    name login createdAt
    repositories(first:100, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC,
                 orderBy:{field:PUSHED_AT, direction:DESC}){
      totalCount
      nodes{
        name stargazerCount isFork
        repositoryTopics(first:25){ nodes{ topic{ name } } }
        languages(first:25){ edges{ size node{ name } } }
      }
    }
    contributionsCollection(from:$from,to:$to){
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      contributionCalendar{
        totalContributions
        weeks{ contributionDays{ date contributionCount } }
      }
    }
  }
}"""


def collect(token):
    """Return one normalised dict regardless of which source was used."""
    today = dt.date.today()
    if token:
        data = _graphql(token, GQL, {
            "login": USER,
            "from": (today - dt.timedelta(days=364)).isoformat() + "T00:00:00Z",
            "to": today.isoformat() + "T23:59:59Z"})
        u = data["user"]
        cc = u["contributionsCollection"]
        days = {d["date"]: d["contributionCount"]
                for w in cc["contributionCalendar"]["weeks"]
                for d in w["contributionDays"]}
        repos = [{"name": r["name"], "stars": r["stargazerCount"],
                  "topics": [t["topic"]["name"] for t in r["repositoryTopics"]["nodes"]],
                  "langs": {e["node"]["name"]: e["size"] for e in r["languages"]["edges"]}}
                 for r in u["repositories"]["nodes"] if not r["isFork"]]
        d = {"name": u["name"], "created": u["createdAt"][:10],
             "repo_count": len(repos), "repos": repos, "days": days,
             "total": cc["contributionCalendar"]["totalContributions"],
             "commits": cc["totalCommitContributions"],
             "prs": cc["totalPullRequestContributions"],
             "issues": cc["totalIssueContributions"],
             "reviews": cc["totalPullRequestReviewContributions"]}
    else:
        d = _collect_public()

    # ── derived ──────────────────────────────────────────────────────────────
    d["stars"] = sum(r["stars"] for r in d["repos"])

    langs = collections.Counter()
    for r in d["repos"]:
        keep = VENDORED_KEEP.get(r["name"])
        for lang, size in r["langs"].items():
            if lang in IGNORE_LANGS or (keep is not None and lang not in keep):
                continue
            langs[lang] += size
    d["langs"] = langs
    d["code_bytes"] = sum(langs.values())

    window = [(dt.date.fromisoformat(k), v) for k, v in d["days"].items()]
    window.sort()
    d["cal"] = window[-CAL_DAYS:]
    d["cal_total"] = sum(v for _, v in d["cal"])
    d["cal_active"] = sum(1 for _, v in d["cal"] if v)
    d["active_days"] = sum(1 for _, v in window if v)
    d["best_day"] = max((v for _, v in window), default=0)

    # streaks, counted over the full year and ending today
    cur = best = 0
    for _, v in window:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    d["streak_long"] = best
    tail = 0
    for _, v in reversed(window):
        if v:
            tail += 1
        else:
            break
    d["streak_now"] = tail

    d["weekday"] = collections.Counter()
    for day, v in window:
        d["weekday"][day.weekday()] += v

    d["monthly"] = collections.OrderedDict()
    for day, v in window:
        d["monthly"].setdefault(day.strftime("%Y-%m"), 0)
        d["monthly"][day.strftime("%Y-%m")] += v

    return d


def _collect_public():
    """No token: public REST plus the contributions HTML fragment."""
    repos_raw = json.loads(_get(API + "/users/" + USER + "/repos?per_page=100"))
    user = json.loads(_get(API + "/users/" + USER))
    repos = []
    for r in repos_raw:
        if r["fork"] or r["name"] == USER:
            continue
        langs = json.loads(_get(r["languages_url"]))
        repos.append({"name": r["name"], "stars": r["stargazers_count"],
                      "topics": r.get("topics") or [], "langs": langs})

    html = _get("https://github.com/users/" + USER + "/contributions",
                accept="text/html").decode("utf8", "replace")
    dates = dict(re.findall(
        r'id="(contribution-day-component-\d+-\d+)"[^>]*data-date="(\d{4}-\d{2}-\d{2})"', html))
    if not dates:   # attribute order is not guaranteed
        dates = {i: d for d, i in re.findall(
            r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*id="(contribution-day-component-\d+-\d+)"', html)}
    days = {}
    for cid, body in re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)</tool-tip>', html):
        if cid not in dates:
            continue
        m = re.match(r"([\d,]+)\s+contribution", body.strip())
        days[dates[cid]] = int(m.group(1).replace(",", "")) if m else 0
    for cid, day in dates.items():
        days.setdefault(day, 0)

    total = sum(days.values())
    return {"name": user.get("name") or USER, "created": user["created_at"][:10],
            "repo_count": len(repos), "repos": repos, "days": days, "total": total,
            # the public fragment does not split contributions by type
            "commits": 0, "prs": 0, "issues": 0, "reviews": 0}


# ═══════════════════════════════════════════════════════════ layout ══════════
# Flat and mostly neutral: no cards, no bullet-icon section headings — just
# plain small caption text, and rose spent on exactly one highlight per chart.

def hr(o, y, x0=L, x1=R, color=LINE, weight=1):
    o.append('<path d="M%.1f %.1f H%.1f" stroke="%s" stroke-width="%s"/>'
              % (x0, y, x1, color, weight))


def draw_activity_graph(o, x0, x1, ytop, base, months, accent=WHITE, peak_color=ROSE):
    """The 12-month contribution trend as a flat gradient-area line chart —
    neutral line and fill, with rose spent only on the single peak point.
    Shared by the standalone activity-graph.svg export (currently its only
    caller, kept as its own function since the geometry is non-trivial).
    """
    peak = max((v for _, v in months), default=1) or 1
    step = (x1 - x0) / (len(months) - 1 or 1)
    pts = [(x0 + i * step, base - (base - ytop) * v / peak) for i, (_, v) in enumerate(months)]
    path, plen = spline(pts)

    o.append('<defs><linearGradient id="actgrad" x1="0" y1="0" x2="0" y2="1">'
             '<stop offset="0%" stop-color="' + accent + '" stop-opacity="0.36"/>'
             '<stop offset="100%" stop-color="' + accent + '" stop-opacity="0"/>'
             '</linearGradient></defs>')
    for gy in (ytop, (ytop + base) / 2, base):
        o.append('<path d="M%.1f %.1f H%.1f" stroke="%s" stroke-width="1" '
                 'stroke-dasharray="2 4" opacity="0.4"/>' % (x0, gy, x1, LINE))

    o.append('<path d="%s L%.1f,%.1f L%.1f,%.1f Z" fill="url(#actgrad)" class="fade" '
             'style="animation-delay:.5s"/>' % (path, pts[-1][0], base, pts[0][0], base))
    o.append('<path d="%s" fill="none" stroke="%s" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round" '
             'stroke-dasharray="%.0f" stroke-dashoffset="%.0f" class="draw"/>'
             % (path, accent, plen, plen))

    for i, ((ym, v), (px, py)) in enumerate(zip(months, pts)):
        top = v == peak
        if v:
            o.append('<circle cx="%.1f" cy="%.1f" r="%s" fill="%s" class="pop" '
                     'style="animation-delay:%.2fs"/>'
                     % (px, py, "3.4" if top else "2.4", peak_color if top else accent,
                        .5 + i * .05))
        if top:
            o.append(text(px, py - 10, str(v), size=9.5, fill=peak_color, anchor="middle",
                          weight=600, family=SANS, cls="fade", style="animation-delay:1.1s"))
        o.append(text(px, base + 16, dt.date.fromisoformat(ym + "-01").strftime("%b")[0],
                      size=8.5, fill=DIM, anchor="middle"))


def spline(pts):
    """Catmull-Rom through `pts`, emitted as cubic beziers, plus its length."""
    d = ["M%.1f,%.1f" % pts[0]]
    length = 0.0
    for i in range(len(pts) - 1):
        p0 = pts[max(i - 1, 0)]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        d.append("C%.1f,%.1f %.1f,%.1f %.1f,%.1f" % (c1 + c2 + p2))
        length += ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
    return " ".join(d), length * 1.25


# ═══════════════════════════════════════════════════════ isometric grid ══════
# One "little building" per day: an extruded diamond tile, height by
# contribution count. Neutral white at every level; rose is spent on exactly
# one tile — the single best day.

def _poly(pts, fill, opacity):
    d = "M" + " L".join("%.2f,%.2f" % p for p in pts) + " Z"
    return '<path d="%s" fill="%s" opacity="%.3f"/>' % (d, fill, opacity)


def iso_tile(gx, gy, hw, hh, eh, fill, base_op):
    """Ground point (gx, gy), footprint half-extents (hw, hh), extrusion
    height eh. eh=0 renders as a flat ground tile — a day with no
    contributions still shows up, just level with the ground.
    """
    N = (gx, gy - eh - hh)
    E = (gx + hw, gy - eh)
    S = (gx, gy - eh + hh)
    Wp = (gx - hw, gy - eh)
    parts = []
    if eh > 0:
        Sg, Wg, Eg = (gx, gy + hh), (gx - hw, gy), (gx + hw, gy)
        parts.append(_poly([Wp, S, Sg, Wg], fill, base_op * 0.42))   # left, darkest
        parts.append(_poly([S, E, Eg, Sg], fill, base_op * 0.68))    # right, mid
    parts.append(_poly([N, E, S, Wp], fill, base_op))                # top, brightest
    return parts


# ═══════════════════════════════════════════════════════════ charts ══════════

def build_calendar(d):
    """Contributions, last 6 months, as a small isometric skyline, with the
    weekday rhythm spread alongside it. Just these two — no other stats, no
    section icons, no card.
    """
    cal = d["cal"]
    o = []
    top_y = 44

    o.append(text(L, top_y, "Contributions, last 6 months", size=11, fill=MUTED, family=SANS))
    o.append(text(R, top_y, dt.date.today().isoformat(), size=8.5, fill=DIM,
                  anchor="end", family=SANS))

    cal_top = top_y + 30
    gap, rhythm_w = 40, 190
    cal_w = CW - gap - rhythm_w

    pad = cal[0][0].weekday() if cal else 0
    slots = [None] * pad + list(cal)
    rows = 7
    cols = max(1, -(-len(slots) // 7))
    hw = cal_w / (cols + rows)
    hh = hw * 0.55
    max_eh = 22

    cells = [(idx // 7, idx % 7, slot[0], slot[1])
             for idx, slot in enumerate(slots) if slot is not None]

    cal_bottom = cal_top
    if cells:
        peak_c = max(v for _, _, _, v in cells) or 1
        gxs = [(c - r) * hw for c, r, _, _ in cells]
        gys = [(c + r) * hh for c, r, _, _ in cells]
        ox = L + hw - min(gxs)
        oy = cal_top + hh + max_eh - min(gys)

        def level(v):
            if v <= 0:
                return 0
            return min(4, 1 + int(3 * (v - 1) / max(1, peak_c - 1)))

        LEVEL_OP = [0.05, 0.24, 0.44, 0.66, 0.88]
        best = max(cells, key=lambda c: c[3])

        seen_months = set()
        for col, row, day, v in cells:
            if row == 0 and day.day <= 7:
                key = day.strftime("%Y-%m")
                if key not in seen_months:
                    seen_months.add(key)
                    mx, my = ox + col * hw, oy + col * hh
                    o.append(text(mx, my - hh - max_eh - 8, day.strftime("%b").upper(),
                                  size=7.5, fill=DIM, anchor="middle", spacing=0.8))

        for col, row, day, v in cells:
            gx, gy = ox + (col - row) * hw, oy + (col + row) * hh
            is_best = (col, row, day, v) == best and v > 0
            eh = max_eh * v / peak_c if v else 0
            if v and eh < 4:
                eh = 4
            fill = ROSE if is_best else WHITE
            base_op = 0.95 if is_best else LEVEL_OP[level(v)]
            o.extend(iso_tile(gx, gy, hw, hh, eh, fill, base_op))

        cal_bottom = oy + max(gys) + hh

    # ── weekday rhythm, spread alongside the same 6-month window ───────────
    wk = collections.Counter()
    for day, v in cal:
        wk[day.weekday()] += v
    wk_totals = [wk.get(i, 0) for i in range(7)]
    peak_wk = max(wk_totals) or 1

    wkx0 = L + cal_w + gap
    o.append(text(wkx0, top_y, "Weekday rhythm", size=11, fill=MUTED, family=SANS))
    bar_gap = 10
    bar_w = (rhythm_w - bar_gap * 6) / 7
    base_y = cal_bottom
    max_h = max(20, base_y - cal_top - 6)
    for i, v in enumerate(wk_totals):
        bx_ = wkx0 + i * (bar_w + bar_gap)
        h = max(3, max_h * v / peak_wk)
        is_best = v == peak_wk and v > 0
        o.append(rect(bx_, base_y - h, bar_w, h, rx=bar_w / 2,
                      fill=ROSE if is_best else WHITE, opacity=0.95 if is_best else 0.3))
        o.append(text(bx_ + bar_w / 2, base_y + 14, "MTWTFSS"[i], size=8,
                      fill=ROSE if is_best else DIM, anchor="middle"))

    H = round(max(cal_bottom, base_y) + 34)
    head = [svg_open(W, H, "Contributions - last 6 months")]
    head.append('<style>' + BASE_CSS + '</style>')
    head.append(rect(0, 0, W, H, fill=BG, rx=10))
    head.append(rect(0.5, 0.5, W - 1, H - 1, fill="none", stroke=LINE, sw=1, rx=10))
    return "\n".join(head + o + ['</svg>'])


def build_activity_graph(d):
    """The 12-month contribution trend, standalone."""
    Wg, Hg = 880, 220
    Lg, Rg = 40, 840
    o = [svg_open(Wg, Hg, "Activity graph - 12 month trend")]
    o.append('<style>' + BASE_CSS + '''
  .pop  { transform-box:fill-box; transform-origin:center; opacity:0;
          animation:pop .4s cubic-bezier(.2,1.4,.4,1) forwards; }
  @keyframes pop { from { opacity:0; transform:scale(.4); } to { opacity:1; transform:scale(1); } }
  .draw { animation:draw 1.6s cubic-bezier(.3,.7,.3,1) forwards; }
  @keyframes draw { to { stroke-dashoffset:0; } }
</style>''')
    o.append(rect(0, 0, Wg, Hg, fill=BG, rx=10))
    o.append(rect(0.5, 0.5, Wg - 1, Hg - 1, fill="none", stroke=LINE, sw=1, rx=10))
    o.append(text(Lg, 26, "Activity graph, last 12 months", size=11, fill=MUTED, family=SANS))
    o.append(text(Rg, 26, dt.date.today().isoformat(), size=8.5, fill=DIM,
                  anchor="end", family=SANS))
    hr(o, 38, x0=Lg, x1=Rg)
    months = list(d["monthly"].items())[-12:]
    draw_activity_graph(o, Lg, Rg, 62, Hg - 38, months)
    o.append('</svg>')
    return "\n".join(o)


# ═══════════════════════════════════════════════════════════ main ════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist")
    ap.add_argument("--dump", help="write the collected data as JSON for inspection")
    args = ap.parse_args()

    token = os.environ.get("METRICS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    print("source:", "graphql" if token else "public (no token)")
    d = collect(token)
    if args.dump:
        pathlib.Path(args.dump).write_text(json.dumps(
            {k: v for k, v in d.items() if k not in ("days", "cal", "weekday", "langs")},
            indent=1, default=str), encoding="utf8")

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in (("contribution-calendar", build_calendar),
                     ("activity-graph", build_activity_graph)):
        p = out / ("%s.svg" % name)
        p.write_text(fn(d), encoding="utf8")
        print("  %-22s %7d bytes" % (p.name, p.stat().st_size))


if __name__ == "__main__":
    main()
