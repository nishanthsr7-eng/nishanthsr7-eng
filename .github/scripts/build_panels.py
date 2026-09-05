"""Builds the four data-driven SVGs for the profile README: the contribution
calendar, the activity graph, the recent-coding-habits panel, and the
repository-stats grid.

    python .github/scripts/build_panels.py --out dist

With GITHUB_TOKEN set it reads GitHub's GraphQL API (plus one REST call per
repo for traffic views). Without one it falls back to the public REST API
plus the contributions HTML fragment, which is enough to render everything
locally for design work — the habits panel's day rhythm and the stats grid's
sponsors/packages/releases/watchers/storage/views all need the authenticated
query, though, and render as 0/flat without a token.

Style is flat and mostly neutral (white/gray on near-black, matched to the
id-card's canvas), with the rose-red accent spent sparingly — one highlight
per chart (the best day, the peak point) rather than colouring everything.
Each panel floats as its own inset card rather than filling edge-to-edge, so
it never has to match whatever theme the viewer's page is in.

Output: dist/contribution-calendar.svg (last 6 months, as a small isometric
skyline — one extruded tile per day), dist/activity-graph.svg (the 12-month
trend line), dist/habits.svg (commit activity by day of week, plus top
languages), and dist/repo-stats.svg (repo/star/fork/release/watcher/sponsor/
package/storage/traffic counts) — all self-contained SVGs that animate
inside an <img>.
"""

import argparse
import collections
import datetime as dt
import json
import os
import pathlib
import re
import urllib.request

from theme import (LINE, DIM, MUTED, WHITE, ROSE, SANS, BASE_CSS, card_frame,
                    esc, rect, svg_open, text)

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


def _traffic_views_14d(token, repo_names):
    """Sum the 14-day view count across repos via the traffic API. This is
    REST-only (no GraphQL equivalent) and needs push access to each repo, so
    it's best-effort: any repo that 403s (no access, traffic disabled, etc.)
    is just skipped rather than failing the whole build.
    """
    total = 0
    for name in repo_names:
        try:
            body = json.loads(_get(
                "%s/repos/%s/%s/traffic/views" % (API, USER, name), token=token))
            total += body.get("count", 0)
        except Exception:
            continue
    return total


def _graphql(token, query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API + "/graphql", data=body, headers={
        "User-Agent": "profile-panels", "Authorization": "Bearer " + token,
        "Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(req, timeout=45).read())
    if "errors" in out:
        # A field the token lacks scope for (e.g. packages needs read:packages)
        # comes back as one entry in "errors" alongside otherwise-complete
        # "data", with that one field set to null. Failing the whole build
        # over one such field would take out the calendar and activity graph
        # too, so only a genuinely fatal response (no data at all) raises.
        print("GraphQL returned partial errors:", out["errors"])
        if not out.get("data"):
            raise RuntimeError(out["errors"])
    return out["data"]


GQL = """
query($login:String!,$from:DateTime!,$to:DateTime!,$since:GitTimestamp!){
  user(login:$login){
    name login createdAt
    sponsors{ totalCount }
    packages(first:1){ totalCount }
    repositories(first:100, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC,
                 orderBy:{field:PUSHED_AT, direction:DESC}){
      totalCount
      nodes{
        name stargazerCount forkCount isFork diskUsage
        licenseInfo{ name }
        releases{ totalCount }
        watchers{ totalCount }
        repositoryTopics(first:25){ nodes{ topic{ name } } }
        languages(first:25){ edges{ size node{ name } } }
        defaultBranchRef{ target{ ... on Commit{
          history(first:50, since:$since){ nodes{ committedDate } }
        } } }
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
            "to": today.isoformat() + "T23:59:59Z",
            "since": (today - dt.timedelta(days=90)).isoformat() + "T00:00:00Z"})
        u = data["user"]
        cc = u["contributionsCollection"]
        days = {d["date"]: d["contributionCount"]
                for w in cc["contributionCalendar"]["weeks"]
                for d in w["contributionDays"]}
        repos = [{"name": r["name"], "stars": r["stargazerCount"],
                  "forks": r["forkCount"], "disk_kb": r["diskUsage"] or 0,
                  "releases": r["releases"]["totalCount"],
                  "watchers": r["watchers"]["totalCount"],
                  "license": (r.get("licenseInfo") or {}).get("name"),
                  "topics": [t["topic"]["name"] for t in r["repositoryTopics"]["nodes"]],
                  "langs": {e["node"]["name"]: e["size"] for e in r["languages"]["edges"]}}
                 for r in u["repositories"]["nodes"] if not r["isFork"]]
        # recent commit timestamps (last ~90 days, up to 50 per repo) — the
        # only source of real time-of-day/day-of-week "coding habits" data,
        # since the contribution calendar itself is day-granularity only
        commit_times = [
            c["committedDate"]
            for r in u["repositories"]["nodes"] if not r["isFork"]
            for c in ((r.get("defaultBranchRef") or {}).get("target") or {})
                .get("history", {}).get("nodes", [])]
        d = {"name": u["name"], "created": u["createdAt"][:10],
             "repo_count": len(repos), "repos": repos, "days": days,
             "total": cc["contributionCalendar"]["totalContributions"],
             "commits": cc["totalCommitContributions"],
             "prs": cc["totalPullRequestContributions"],
             "issues": cc["totalIssueContributions"],
             "reviews": cc["totalPullRequestReviewContributions"],
             "commit_times": commit_times,
             "sponsors": (u.get("sponsors") or {}).get("totalCount", 0),
             "packages": (u.get("packages") or {}).get("totalCount", 0),
             "views_14d": _traffic_views_14d(token, [r["name"] for r in repos])}
    else:
        d = _collect_public()
        d["views_14d"] = None

    # ── derived ──────────────────────────────────────────────────────────────
    d["stars"] = sum(r["stars"] for r in d["repos"])
    d["forks"] = sum(r.get("forks", 0) for r in d["repos"])
    d["releases"] = sum(r.get("releases", 0) for r in d["repos"])
    d["watchers"] = sum(r.get("watchers", 0) for r in d["repos"])
    d["storage_gb"] = sum(r.get("disk_kb", 0) for r in d["repos"]) / 1_048_576
    d["license"] = (collections.Counter(
        r["license"] for r in d["repos"] if r.get("license")).most_common(1) or [(None, 0)])[0][0]

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

    # recent coding habits — day-of-week from real commit timestamps, used as
    # a fresher alternative to the day-granularity contribution calendar when
    # there's been recent commit activity to draw it from
    d["commit_weekday"] = collections.Counter()
    for ts in d["commit_times"]:
        when = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        d["commit_weekday"][when.weekday()] += 1

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
                      "forks": r.get("forks_count", 0), "disk_kb": r.get("size", 0),
                      # releases/watchers need per-repo calls the public path skips
                      "releases": 0, "watchers": 0,
                      "license": (r.get("license") or {}).get("name"),
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
            # the public fragment does not split contributions by type, and has
            # no commit timestamps, sponsors, or package count at all (those
            # need an authenticated query)
            "commits": 0, "prs": 0, "issues": 0, "reviews": 0, "commit_times": [],
            "sponsors": 0, "packages": 0}


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

    # a small glow travelling the trend line on an endless loop — "activity
    # moving through time", layered under the static peak marker above
    o.append('<g><animateMotion dur="6s" repeatCount="indefinite" path="%s"/>'
             '<circle r="7" fill="%s" opacity="0.16"/>'
             '<circle r="2.6" fill="%s"/></g>' % (path, peak_color, accent))


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


def iso_tile(gx, gy, hw, hh, eh, fill, base_op, delay=None):
    """Ground point (gx, gy), footprint half-extents (hw, hh), extrusion
    height eh. eh=0 renders as a flat ground tile — a day with no
    contributions still shows up, just level with the ground.

    `delay`, when given, wraps the tile in a `.build` group so it grows up
    out of the ground on load — staggered per-tile, the skyline rises one
    building at a time instead of appearing all at once.
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
    if delay is None:
        return parts
    return ['<g class="build" style="animation-delay:%.3fs">' % delay
            + "".join(parts) + '</g>']


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
            delay = col * 0.03 + row * 0.012
            o.extend(iso_tile(gx, gy, hw, hh, eh, fill, base_op, delay=delay))

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
                      fill=ROSE if is_best else WHITE, opacity=0.95 if is_best else 0.3,
                      cls="build", style="animation-delay:%.2fs" % (0.5 + i * 0.07)))
        o.append(text(bx_ + bar_w / 2, base_y + 14, "MTWTFSS"[i], size=8,
                      fill=ROSE if is_best else DIM, anchor="middle",
                      cls="fade", style="animation-delay:%.2fs" % (0.6 + i * 0.07)))

    H = round(max(cal_bottom, base_y) + 34)
    M = 14   # card inset — leaves a transparent margin so the card floats
             # on the page instead of matching it

    # a faint diagonal band of light drifting across the whole skyline on an
    # endless loop, clipped to the panel's own rounded outline
    o.append(
        '<defs>'
        '<clipPath id="calsweep"><rect x="%d" y="%d" width="%d" height="%d" rx="14"/></clipPath>'
        '<linearGradient id="moonbeam" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0%%" stop-color="#ffffff" stop-opacity="0"/>'
        '<stop offset="50%%" stop-color="#ffffff" stop-opacity="0.05"/>'
        '<stop offset="100%%" stop-color="#ffffff" stop-opacity="0"/></linearGradient>'
        '</defs>' % (M, M, W - 2 * M, H - 2 * M))
    o.append(
        '<g clip-path="url(#calsweep)" style="mix-blend-mode:screen">'
        '<g transform="rotate(22 %d %d)">'
        '<rect class="moonsweep" x="-260" y="-200" width="160" height="%d" fill="url(#moonbeam)"/>'
        '</g></g>' % (W // 2, H // 2, H + 400))

    head = [svg_open(W, H, "Contributions - last 6 months")]
    head.append('<style>' + BASE_CSS + '''
  .moonsweep { animation:moonsweep 8s ease-in-out infinite; }
  @keyframes moonsweep { 0% { transform:translateX(0); } 100% { transform:translateX(1400px); } }
''' + '</style>')
    head.append(card_frame(M, M, W - 2 * M, H - 2 * M))
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
    Mg = 14   # card inset — see build_calendar for why this floats instead
    o.append(card_frame(Mg, Mg, Wg - 2 * Mg, Hg - 2 * Mg))
    o.append(text(Lg, 26, "Activity graph, last 12 months", size=11, fill=MUTED, family=SANS))
    o.append(text(Rg, 26, dt.date.today().isoformat(), size=8.5, fill=DIM,
                  anchor="end", family=SANS))
    hr(o, 38, x0=Lg, x1=Rg)
    months = list(d["monthly"].items())[-12:]
    draw_activity_graph(o, Lg, Rg, 62, Hg - 38, months)
    o.append('</svg>')
    return "\n".join(o)


def build_habits(d):
    """Recent coding habits for the README's closing row, sat beside the
    outro image instead of leaving that space empty — day-of-week commit
    rhythm, plus top languages. In the spirit of lowlighter/metrics' habits
    plugin, but in this project's own rose/neutral palette rather than its
    blue-and-green one.

    The card is a fixed size (H below is a constant, not derived from how
    much data there is): the language list is capped to the top 3 and clipped
    to a fixed-height viewport, so extra languages are cut off rather than
    growing the card. A real scrollbar isn't possible here — this SVG is
    loaded through an <img> tag, which GitHub (and browsers generally) treat
    as a flat, non-interactive image; nothing inside it can respond to a
    wheel or drag. Clipping is the closest equivalent: it keeps the panel's
    size locked instead of letting overflow distort the layout.
    """
    W = 380
    M = 14    # card inset — see theme.card_frame for why this floats instead
    pad = 22
    x0, x1 = M + pad, W - M - pad

    header_h = 34
    day_h = 88     # label + bars + weekday letters
    lang_label_h = 24
    lang_rows_visible = 3
    lang_row_h = 22
    H = round(M * 2 + pad * 2 + header_h + day_h + lang_label_h
              + lang_rows_visible * lang_row_h)

    body = []
    y = M + pad
    body.append(text(x0, y + 10, "Recent coding habits", size=12, fill=WHITE, family=SANS,
                     weight=700))
    body.append(text(x1, y + 10, "last 12 months", size=8.5, fill=DIM, family=SANS, anchor="end"))
    y += header_h

    # -- commit activity by day of week, as real bars (not the calendar's
    # capsule rhythm bars — a taller, flatter-topped bar reads more like a
    # standalone chart now that it's the headline row instead of one of three)
    body.append(text(x0, y, "COMMIT ACTIVITY BY DAY", size=8, fill=DIM, family=SANS, spacing=1))
    wk_src = d["commit_weekday"] if sum(d["commit_weekday"].values()) else d["weekday"]
    wk = [wk_src.get(i, 0) for i in range(7)]
    peak_wk = max(wk) or 1
    bar_gap = 10
    bar_w = (x1 - x0 - bar_gap * 6) / 7
    base = y + 14 + 46
    for i, v in enumerate(wk):
        bx = x0 + i * (bar_w + bar_gap)
        bh = max(3, 46 * v / peak_wk)
        is_peak = v == peak_wk and v > 0
        body.append(rect(bx, base - bh, bar_w, bh, rx=3,
                         fill=ROSE if is_peak else WHITE, opacity=0.95 if is_peak else 0.32,
                         cls="build", style="animation-delay:%.2fs" % (0.1 + i * 0.05)))
        body.append(text(bx + bar_w / 2, base + 14, "MTWTFSS"[i], size=8,
                         fill=ROSE if is_peak else DIM, anchor="middle"))
    y += day_h

    # -- top languages, by byte share of owned repos — clipped to a fixed
    # number of rows so the card never grows past its default size
    body.append(text(x0, y, "LANGUAGE ACTIVITY", size=8, fill=DIM, family=SANS, spacing=1))
    y += lang_label_h
    clip_id = "langclip"
    body.append('<clipPath id="%s"><rect x="%.1f" y="%.1f" width="%.1f" height="%.1f"/>'
               '</clipPath>' % (clip_id, x0, y, x1 - x0, lang_rows_visible * lang_row_h))
    top = d["langs"].most_common(lang_rows_visible)
    total_bytes = sum(v for _, v in top) or 1
    lang_body = []
    for i, (lang, size) in enumerate(top):
        pct = 100 * size / total_bytes
        ly = y + i * lang_row_h
        lang_body.append(text(x0, ly + 9, lang, size=9.5, fill=WHITE, family=SANS))
        lang_body.append(text(x1, ly + 9, "%.0f%%" % pct, size=8.5, fill=DIM, family=SANS,
                              anchor="end"))
        lang_body.append(rect(x0, ly + 13, x1 - x0, 4, rx=2, fill=LINE))
        lang_body.append(rect(x0, ly + 13, (x1 - x0) * pct / 100, 4, rx=2,
                              fill=ROSE if i == 0 else WHITE, opacity=1 if i == 0 else 0.55,
                              cls="build", style="animation-delay:%.2fs" % (0.5 + i * 0.1)))
    body.append('<g clip-path="url(#%s)">' % clip_id + "".join(lang_body) + '</g>')

    o = [svg_open(W, H, "Recent coding habits")]
    o.append('<style>' + BASE_CSS + '</style>')
    o.append(card_frame(M, M, W - 2 * M, H - 2 * M))
    o.extend(body)
    o.append('</svg>')
    return "\n".join(o)


# ═══════════════════════════════════════════════════ repo stats grid ═════════
# Small hand-drawn line icons (14x14-ish, local coordinates) — no icon font
# can be fetched from inside an <img>-loaded SVG, so these are plain paths.
STAT_ICONS = {
    "repo":     '<rect x="2" y="1.5" width="10" height="12" rx="1.5"/><path d="M7 1.5v12"/>',
    "heart":    '<path d="M7 12.3 2.2 7.8a3 3 0 1 1 4.5-3.9l.3.3.3-.3a3 3 0 1 1 4.5 3.9Z"/>',
    "tag":      '<path d="M1.6 7.4 7 2h5a1 1 0 0 1 1 1v5l-5.4 5.4a1 1 0 0 1-1.4 0L1.6 8.8a1 1 0 0 1 0-1.4Z"/>'
                '<circle cx="10" cy="5" r="1"/>',
    "star":     '<path d="M7 1.3 8.8 5l4.1.5-3 2.9.7 4.1L7 10.6 3.4 12.5l.7-4.1-3-2.9L5.2 5Z"/>',
    "release":  '<path d="M1.6 7.4 7 2h5a1 1 0 0 1 1 1v5l-5.4 5.4a1 1 0 0 1-1.4 0L1.6 8.8a1 1 0 0 1 0-1.4Z"/>'
                '<circle cx="10" cy="5" r="1"/>',
    "fork":     '<circle cx="3.4" cy="3" r="1.4"/><circle cx="10.6" cy="3" r="1.4"/>'
                '<circle cx="7" cy="11.4" r="1.4"/>'
                '<path d="M3.4 4.4v.8A2.4 2.4 0 0 0 5.8 7.6h2.4A2.4 2.4 0 0 0 10.6 5.2v-.8M7 7.6v2.4"/>',
    "package":  '<path d="M7 1 12.6 4v6L7 13 1.4 10V4Z"/><path d="M1.4 4 7 7l5.6-3M7 7v6"/>',
    "eye":      '<path d="M1 7s2.3-4.4 6-4.4S13 7 13 7s-2.3 4.4-6 4.4S1 7 1 7Z"/><circle cx="7" cy="7" r="2"/>',
    "database": '<ellipse cx="7" cy="3.2" rx="5" ry="1.9"/>'
                '<path d="M2 3.2v7.6c0 1 2.2 1.9 5 1.9s5-.9 5-1.9V3.2"/>'
                '<path d="M2 7c0 1 2.2 1.9 5 1.9s5-.9 5-1.9"/>',
    "pulse":    '<path d="M1 8h2.3l1.4-3.8 2 6.8 1.4-4.6.9 1.6H13"/>',
}


def _stat_icon(name, x, y, color):
    return ('<g transform="translate(%.1f,%.1f)" fill="none" stroke="%s" '
            'stroke-width="1.15" stroke-linecap="round" stroke-linejoin="round">%s</g>'
            % (x, y, color, STAT_ICONS[name]))


def build_repo_stats(d):
    """The left-hand stat grid next to the outro image, mirroring GitHub's
    own repository-overview sidebar — pulled from this run's real account
    data (see `collect`), not sample numbers. Views/sponsors/packages/
    releases/watchers/storage all read 0 without METRICS_TOKEN, the same as
    every other authenticated-only field in this file.
    """
    def plural(n, singular, plural_form):
        return "%s %s" % (format(n, ","), singular if n == 1 else plural_form)

    views = d.get("views_14d")
    views_str = ("—" if views is None else
                 "%.1fk views (14d)" % (views / 1000) if (views or 0) >= 1000 else
                 "%s (14d)" % plural(views or 0, "view", "views"))
    license_str = "Prefers %s license" % d["license"] if d["license"] else "No license set"

    rows = [
        ("repo",     plural(d["repo_count"], "Repository", "Repositories"), True),
        ("heart",    plural(d["sponsors"], "Sponsor", "Sponsors"),          False),
        ("tag",      license_str,                                          False),
        ("star",     plural(d["stars"], "Stargazer", "Stargazers"),        False),
        ("release",  plural(d["releases"], "Release", "Releases"),         False),
        ("fork",     plural(d["forks"], "Forker", "Forkers"),              False),
        ("package",  plural(d["packages"], "Package", "Packages"),         False),
        ("eye",      plural(d["watchers"], "Watcher", "Watchers"),         False),
        ("database", "%.2f GB used" % d["storage_gb"],                     False),
        ("pulse",    views_str,                                            False),
    ]

    W = 380
    M = 14   # card inset — see theme.card_frame for why this floats instead
    pad_x, pad_top = 28, 24
    row_h = 34
    col_gap = 18
    n_rows = len(rows) // 2
    H = round(M * 2 + pad_top * 2 + row_h * n_rows)
    col_w = (W - 2 * M - pad_x * 2 - col_gap) / 2

    o = [svg_open(W, H, "Repository stats")]
    o.append(card_frame(M, M, W - 2 * M, H - 2 * M))
    for i in range(n_rows):
        for c in range(2):
            key, label, highlight = rows[i * 2 + c]
            cx = M + pad_x + c * (col_w + col_gap)
            cy = M + pad_top + i * row_h + row_h / 2
            color = ROSE if highlight else DIM
            o.append(_stat_icon(key, cx, cy - 7, color))
            o.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="12.5" fill="%s">%s</text>'
                      % (cx + 20, cy + 4.5, SANS, ROSE if highlight else WHITE, esc(label)))
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
            {k: v for k, v in d.items()
             if k not in ("days", "cal", "weekday", "langs", "commit_times", "commit_weekday",
                          "repos")},
            indent=1, default=str), encoding="utf8")

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in (("contribution-calendar", build_calendar),
                     ("activity-graph", build_activity_graph),
                     ("habits", build_habits),
                     ("repo-stats", build_repo_stats)):
        p = out / ("%s.svg" % name)
        p.write_text(fn(d), encoding="utf8")
        print("  %-22s %7d bytes" % (p.name, p.stat().st_size))


if __name__ == "__main__":
    main()
