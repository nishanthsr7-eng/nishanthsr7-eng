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

Output: dist/contribution-calendar.svg (last 3 months, as a small isometric
skyline — one extruded tile per day), dist/activity-graph.svg (the same
3-month window as bars), dist/habits.svg (commit activity by day of week,
plus top languages), and dist/repo-stats.svg (repo/star/fork/release/
watcher/sponsor/package/storage/traffic counts) — all self-contained SVGs
that animate inside an <img>.
"""

import argparse
import collections
import datetime as dt
import json
import math
import os
import pathlib
import re
import urllib.request

from theme import (BG, LINE, DIM, MUTED, WHITE, ROSE, SANS, BASE_CSS, PANEL_CSS,
                    esc, rect, svg_open, text)

USER = "nishanthsr7-eng"
API = "https://api.github.com"

# Shared canvas width — matched to the id-card so both sit flush in the README.
W = 880
L, R = 40, 840
CW = R - L

# The calendar and activity graph now sit side by side as a table-style pair
# (two inline images, not an actual <table> — see README.md) instead of each
# spanning the full width, so both are designed at these narrower canvases
# instead of a shrunk-down copy of the old full-width one. Uneven on
# purpose: the calendar's grid needs the extra breadth more than the
# 3-bar activity chart does, which stays legible — arguably reads better —
# narrower and with thicker bars.
CAL_W = 430
ACT_W = 300
# Bottom row: repo stats and habits are laid out 336 wide, then each gets this
# much empty canvas on the side facing the outro image. The README gives both
# 37%, so the panels reach the outer edges and the spare room sits evenly on
# either side of the image instead of at the row's ends.
SIDE_GAP = 78
# Both bottom-row panels share one height and one visual top/bottom line:
# first thing drawn starts at BOTTOM_TOP, last text baseline sits on
# BOTTOM_BASE, and each panel spaces its own contents evenly in between.
BOTTOM_H, BOTTOM_TOP, BOTTOM_BASE = 460, 18, 442

CAL_DAYS = 91                              # ~3 months — shorter to fit the narrower box


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
    sponsors(first:1){ totalCount }
    packages(first:1){ totalCount }
    repositories(first:100, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC,
                 orderBy:{field:PUSHED_AT, direction:DESC}){
      totalCount
      nodes{
        name stargazerCount forkCount isFork isPrivate diskUsage pushedAt
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
        repos = [{"name": r["name"], "stars": r["stargazerCount"], "pushed": r.get("pushedAt"),
                  "private": bool(r.get("isPrivate")),
                  "forks": r.get("forkCount") or 0, "disk_kb": r.get("diskUsage") or 0,
                  "releases": (r.get("releases") or {}).get("totalCount", 0),
                  "watchers": (r.get("watchers") or {}).get("totalCount", 0),
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
        repos.append({"name": r["name"], "stars": r["stargazers_count"], "pushed": r.get("pushed_at"),
                      "private": bool(r.get("private")),
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


# ═══════════════════════════════════════════════════════ isometric grid ══════
# LOCKED DESIGN — emissive towers + diagonal wave. Settled after comparing the
# alternatives side by side; keep the look as is and only fix bugs here.
#
# One "little building" per day: a solid dark tower whose top face glows,
# brighter and taller the more was committed that day. Rose is spent on
# exactly one tile — the single best day.

TOWER_BODY = "#1b2028"


def _mix(a, b, t):
    """t of colour a over (1 - t) of colour b, as a solid hex."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x * t + y * (1 - t)) for x, y in zip(ca, cb))


def _poly(pts, fill, attrs=""):
    d = "M" + " L".join("%.2f,%.2f" % p for p in pts) + " Z"
    return '<path d="%s" fill="%s"%s/>' % (d, fill, attrs)


def iso_tile(gx, gy, hw, hh, eh, top, right, left):
    """Ground point (gx, gy), footprint half-extents (hw, hh), extrusion
    height eh, one solid fill per visible face. Returns (side paths, top
    path) so the caller can put the glowing top in its own animated group.
    eh=0 renders as a flat ground tile — a day with no contributions still
    shows up, just level with the ground.
    """
    N = (gx, gy - eh - hh)
    E = (gx + hw, gy - eh)
    S = (gx, gy - eh + hh)
    Wp = (gx - hw, gy - eh)
    sides = []
    if eh > 0:
        Sg, Wg, Eg = (gx, gy + hh), (gx - hw, gy), (gx + hw, gy)
        sides.append(_poly([Wp, S, Sg, Wg], left))
        sides.append(_poly([S, E, Eg, Sg], right))
    return sides, (N, E, S, Wp)


# ═══════════════════════════════════════════════════════════ charts ══════════

def build_calendar(d):
    """Contributions, last 3 months, as a small isometric skyline — just the
    one chart, no section icons, no card. Used to run the weekday rhythm
    bars alongside it, but that's the same weekday breakdown the habits
    panel's COMMIT ACTIVITY BY DAY bars already show over the full year, so
    dropping it here removes a repeat rather than a unique view. Sized to
    sit beside the narrower activity graph as a table-style pair — see
    CAL_W/ACT_W — rather than spanning the full width on its own.
    """
    W, L, R = CAL_W, 20, CAL_W - 20
    CW = R - L
    cal = d["cal"]
    o = []
    top_y = 44

    o.append(text(L, top_y, "Contributions, last 3 months", size=11, fill=MUTED, family=SANS))
    o.append(text(R, top_y, dt.date.today().isoformat(), size=8.5, fill=DIM,
                  anchor="end", family=SANS))

    cal_top = top_y + 30
    cal_w = CW

    pad = cal[0][0].weekday() if cal else 0
    slots = [None] * pad + list(cal)
    rows = 7
    cols = max(1, -(-len(slots) // 7))
    hw = cal_w / (cols + rows)
    hh = hw * 0.55
    max_eh = 26
    foot = 0.82          # footprint scale — the gap keeps each day its own tower

    cells = [(idx // 7, idx % 7, slot[0], slot[1])
             for idx, slot in enumerate(slots) if slot is not None]

    cal_bottom = cal_top
    loop_dur = 0
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

        # glow colour per level (1..4); the tops fade from this at the centre
        # to about half-way into the tower body at the edges
        GLOW = [None] + [_mix(WHITE, BG, t) for t in (0.30, 0.50, 0.75, 1.0)]
        GLOW_OP = [0, 0.12, 0.12, 0.35, 0.35]
        GROUND = _mix(WHITE, BG, 0.07)
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

        # a diagonal wave: one band of light rolls across the grid, week by
        # week, lighting each top as it passes. Every lit tile shares one
        # @keyframes rule and one duration; only animation-delay differs,
        # so the band falls out of the stagger instead of per-tile timelines.
        loop_dur = 5.0
        # solid towers overlap, so draw back to front (farther diagonals first)
        for col, row, day, v in sorted(cells, key=lambda c: (c[0] + c[1], c[0])):
            gx, gy = ox + (col - row) * hw, oy + (col + row) * hh
            lv = level(v)
            if not lv:
                _, top = iso_tile(gx, gy, hw * foot, hh * foot, 0, GROUND, GROUND, GROUND)
                o.append(_poly(top, GROUND))
                continue
            is_best = (col, row, day, v) == best
            # sqrt, so one huge day doesn't flatten every other tower
            eh = max(4, max_eh * math.sqrt(v / peak_c))
            glow = ROSE if is_best else GLOW[lv]
            sides, top = iso_tile(gx, gy, hw * foot, hh * foot, eh, None,
                                  _mix(TOWER_BODY, BG, 0.9), _mix(TOWER_BODY, BG, 0.6))
            delay = col * 0.13 - row * 0.05
            o.append('<g>'
                     + _poly(top, glow, ' class="wglow" filter="url(#calglow)" '
                             'style="opacity:%.2f;animation-delay:%.2fs"'
                             % (0.9 if is_best else GLOW_OP[lv], delay))
                     + "".join(sides)
                     + _poly(top, "url(#caltop%s)" % ("p" if is_best else lv),
                             ' class="wtop" style="animation-delay:%.2fs"' % delay)
                     + '</g>')

        cal_bottom = oy + max(gys) + hh

    H = round(cal_bottom + 34)

    # The diamond grid leaves two empty corners: totals go in the top-right,
    # above the grid's upper-right edge, and a Less -> More legend of five
    # mini towers (same tops as the grid's levels) sits in the bottom-left.
    o.append('<g class="rise" style="animation-delay:.4s">'
             + text(R, top_y + 38, format(d["cal_total"], ","), size=22, fill=WHITE, family=SANS,
                    weight=800, anchor="end")
             + text(R, top_y + 51, "contributions", size=7.5, fill=DIM, family=SANS, anchor="end")
             + '</g><g class="rise" style="animation-delay:.6s">'
             + text(R, top_y + 76, format(d["cal_active"], ","), size=14, fill=WHITE, family=SANS,
                    weight=700, anchor="end")
             + text(R, top_y + 88, "active days", size=7.5, fill=DIM, family=SANS, anchor="end")
             + '</g>')
    lg_y = H - 18
    o.append(text(L, lg_y + 2, "Less", size=7.5, fill=DIM, family=SANS))
    for i, top in enumerate(["caltop1", "caltop2", "caltop3", "caltop4", "caltopp"]):
        gx, eh = L + 30 + i * 16, 2 + i * 3
        sides, face = iso_tile(gx, lg_y, 6, 3.4, eh, None, "#1f252e", "#161a21")
        o.append('<g class="mini" style="animation-delay:%.2fs">' % (i * .25)
                 + "".join(sides) + _poly(face, "url(#%s)" % top) + '</g>')
    o.append(text(L + 30 + 5 * 16 - 2, lg_y + 2, "More", size=7.5, fill=DIM, family=SANS))

    # no card frame — sits directly on the page background, same as the
    # repo-stats/outro/habits row below it, instead of floating as its own
    # boxed panel
    head = [svg_open(W, H, "Contributions - last 3 months")]
    defs = ['<filter id="calglow" x="-1" y="-1" width="3" height="3">'
            '<feGaussianBlur stdDeviation="3.5"/></filter>']
    for key, c in [(1, _mix(WHITE, BG, 0.30)), (2, _mix(WHITE, BG, 0.50)),
                   (3, _mix(WHITE, BG, 0.75)), (4, WHITE), ("p", ROSE)]:
        defs.append('<radialGradient id="caltop%s"><stop offset="0" stop-color="%s"/>'
                    '<stop offset="1" stop-color="%s"/></radialGradient>'
                    % (key, c, _mix(c, TOWER_BODY, 0.55)))
    head.append('<defs>' + "".join(defs) + '</defs>')
    head.append('<style>' + BASE_CSS + '''
  .wglow { animation:wglow %(d).2fs linear infinite both; }
  .wtop  { animation:wtop  %(d).2fs linear infinite both; }
  @keyframes wglow { 0%% { opacity:.1; } 6%% { opacity:1; } 18%%, 100%% { opacity:.1; } }
  @keyframes wtop  { 0%% { filter:brightness(1); } 6%% { filter:brightness(1.9); }
                     18%%, 100%% { filter:brightness(1); } }
  .mini  { transform-box:fill-box; transform-origin:50%% 100%%; animation:mini 3.2s ease-in-out infinite; }
  @keyframes mini { 0%%, 100%% { transform:scaleY(1); } 50%% { transform:scaleY(1.25); } }
  @media (prefers-reduced-motion: reduce) { .wglow, .wtop, .mini { animation:none; } }
''' % {"d": loop_dur} + '</style>')
    return "\n".join(head + o + ['</svg>'])


def build_activity_graph(d, target_h=None):
    """Monthly commit activity as bars, narrower than the contribution
    calendar it sits beside as a table-style pair (see CAL_W/ACT_W) — a
    3-bar chart doesn't need the calendar's grid-driven breadth, and
    staying narrower leaves room for the bars themselves to run thicker
    rather than thin. A smooth line chart reads poorly once it's this
    narrow with only a few points on it — bars stay legible however
    compressed the box gets, so the chart type changed along with the
    width. Matches the calendar's 3-month window rather than a longer,
    differently-scoped one.

    `target_h`, when given, pins this panel's height to match the
    calendar's own — the calendar's height falls out of its tile grid
    geometry (not a constant, since the 3-month window's day-of-week
    padding shifts its column count slightly depending on what today is),
    so main() measures the calendar's real height first and threads it
    through here rather than the two panels each guessing at a shared
    constant that would drift apart on the days the grid gains a column.
    """
    W, L, R = ACT_W, 20, ACT_W - 20
    CW = R - L
    months = list(d["monthly"].items())[-3:]
    peak = max((v for _, v in months), default=1) or 1

    top_y = 44
    o = []
    o.append(text(L, top_y, "Activity, last 3 months", size=11, fill=MUTED, family=SANS))
    o.append(text(R, top_y, dt.date.today().isoformat(), size=8.5, fill=DIM,
                  anchor="end", family=SANS))

    bar_top = top_y + 34
    overhead = bar_top + 44   # header above + peak label/month row below the bars
    bar_h_max = max(40, (target_h - overhead) if target_h else 90)
    bar_base = bar_top + bar_h_max
    n = max(1, len(months))
    gap = 34
    bar_w = min(26, (CW - gap * (n - 1)) / n)
    row_w = n * bar_w + (n - 1) * gap
    row_x0 = L + (CW - row_w) / 2   # centered — bar_w is capped, so it may not fill CW

    for i, (ym, v) in enumerate(months):
        bx = row_x0 + i * (bar_w + gap)
        h = max(4, bar_h_max * v / peak)
        is_peak = v == peak and v > 0
        color = ROSE if is_peak else WHITE
        o.append(rect(bx, bar_base - h, bar_w, h, rx=7, fill=color,
                      opacity=0.95 if is_peak else 0.32))
        if v:
            o.append(text(bx + bar_w / 2, bar_base - h - 10, str(v), size=10.5, fill=color,
                          anchor="middle", weight=700, family=SANS,
                          cls="fade", style="animation-delay:%.2fs" % (0.15 + i * 0.06)))
        month_name = dt.date.fromisoformat(ym + "-01").strftime("%b")
        o.append(text(bx + bar_w / 2, bar_base + 20, month_name, size=9.5,
                      fill=ROSE if is_peak else DIM, anchor="middle", family=SANS))

    H = target_h if target_h else round(bar_base + 44)
    head = [svg_open(W, H, "Activity - last 3 months")]
    head.append('<style>' + PANEL_CSS + '</style>')
    return "\n".join(head + o + ['</svg>'])


def build_habits(d):
    """Recent coding habits for the README's closing row, sat beside the
    outro image instead of leaving that space empty — day-of-week commit
    rhythm, plus a language-share ring. In the spirit of lowlighter/metrics'
    habits plugin, but in this project's own rose/neutral palette rather than
    its blue-and-green one.

    Languages are drawn as a hollow ring (stacked stroke-dasharray circles)
    rather than bars: its footprint is fixed by the ring's radius, not by how
    many languages there are or how long their names run, so nothing can
    overflow the panel regardless of the data.

    The four sections (title, day bars, languages, streaks) each have a fixed
    height; whatever is left of the shared BOTTOM_TOP..BOTTOM_BASE span is
    split evenly between them, so the panel covers exactly the same vertical
    stretch as the repo-stats panel on the other side of the outro image.
    """
    W, H = 336, BOTTOM_H
    # contents run flush to both side edges (2px only so strokes aren't clipped);
    # SIDE_GAP puts the space next to the outro image, same as repo stats
    x0, x1 = 2, W - 2

    HEADER_H, DAYS_H, LANGS_H, STREAKS_H = 17.5, 73, 96, 97
    gap = (BOTTOM_BASE - BOTTOM_TOP - HEADER_H - DAYS_H - LANGS_H - STREAKS_H) / 3

    body = []
    y = BOTTOM_TOP
    body.append(text(x0, y + 14.5, "Recent coding habits", size=15, fill=WHITE, family=SANS,
                     weight=700))
    body.append(text(x1, y + 14.5, "last 12 months", size=10.5, fill=DIM, family=SANS, anchor="end"))
    y += HEADER_H + gap

    # -- commit activity by day of week, as real bars
    body.append(text(x0, y - 7, "COMMIT ACTIVITY BY DAY", size=10, fill=DIM, family=SANS, spacing=1))
    wk_src = d["commit_weekday"] if sum(d["commit_weekday"].values()) else d["weekday"]
    wk = [wk_src.get(i, 0) for i in range(7)]
    peak_wk = max(wk) or 1
    bar_gap, bar_max = 10, 40
    bar_w = (x1 - x0 - bar_gap * 6) / 7
    base = y + 16 + bar_max
    for i, v in enumerate(wk):
        bx = x0 + i * (bar_w + bar_gap)
        bh = max(3, bar_max * v / peak_wk)
        is_peak = v == peak_wk and v > 0
        body.append(rect(bx, base - bh, bar_w, bh, rx=3,
                         fill=ROSE if is_peak else WHITE, opacity=0.95 if is_peak else 0.32))
        body.append(text(bx + bar_w / 2, base + 15, "MTWTFSS"[i], size=10,
                         fill=ROSE if is_peak else DIM, anchor="middle"))
    y += DAYS_H + gap

    # -- top languages, by byte share of owned repos, as a hollow ring -------
    # Capped at MAX_LANGS however many languages the account has, with the
    # legend row height shrinking as that count grows, so the section keeps
    # its fixed height.
    body.append(text(x0, y - 7, "LANGUAGE ACTIVITY", size=10, fill=DIM, family=SANS, spacing=1))
    MAX_LANGS = 6
    top = d["langs"].most_common(MAX_LANGS)
    total_bytes = sum(v for _, v in top) or 1
    # languages that round to 0% are noise (a template file here, a config
    # there) - drop them from ring and legend
    top = [(lang, v) for lang, v in top if 100 * v / total_bytes >= 0.5]
    # rose + neutrals only, at falling opacity, rather than reaching for new hues
    ring_colors = [(ROSE, 1), (WHITE, 0.9), (MUTED, 0.8), (DIM, 0.85), (ROSE, 0.55), (WHITE, 0.5)]
    row_h = min(22, 110 / max(1, len(top)))

    r, sw = 35, 8      # a thin ring - the legend beside it carries the numbers
    cx, cy = x0 + r + sw / 2, y + 16 + r + sw / 2
    circumference = 2 * math.pi * r
    body.append('<g transform="rotate(-90 %.1f %.1f)">' % (cx, cy))
    cum = 0.0
    for i, (lang, size) in enumerate(top):
        arc = circumference * size / total_bytes
        color, op = ring_colors[i % len(ring_colors)]
        body.append(
            '<circle cx="%.1f" cy="%.1f" r="%d" fill="none" stroke="%s" stroke-width="%d" '
            'stroke-opacity="%.2f" stroke-dasharray="%.2f %.2f" stroke-dashoffset="%.2f"/>'
            % (cx, cy, r, color, sw, op, arc, circumference - arc, -cum))
        cum += arc
    body.append('</g>')
    if top:
        body.append(text(cx, cy - 2, top[0][0][:10], size=10.5, fill=WHITE, family=SANS,
                         anchor="middle", weight=600))
        body.append(text(cx, cy + 14, "%.0f%%" % (100 * top[0][1] / total_bytes), size=13,
                         fill=ROSE, family=SANS, anchor="middle", weight=700))

    # label and share on one line per language, centred on the ring
    lx = cx + r + sw / 2 + 24
    ly0 = cy - (len(top) - 1) * row_h / 2
    for i, (lang, size) in enumerate(top):
        pct = 100 * size / total_bytes
        ly = ly0 + i * row_h
        color, op = ring_colors[i % len(ring_colors)]
        label = lang if len(lang) <= 13 else lang[:12] + "…"   # max size: never overflow the row
        body.append(rect(lx, ly - 7, 9, 9, rx=2, fill=color, opacity=op))
        body.append(text(lx + 15, ly + 2, label, size=11.5, fill=WHITE, family=SANS))
        body.append(text(x1, ly + 2, "%.0f%%" % pct, size=10.5, fill=DIM, family=SANS, anchor="end"))
    y += LANGS_H + gap

    # -- commit streaks: current and longest streak from the full contribution
    # window, plus active days and the best single day
    body.append(text(x0, y + 7, "COMMIT STREAKS", size=10, fill=DIM, family=SANS, spacing=1))
    streak_stats = [
        ("flame", "Current streak", "%d day%s" % (d["streak_now"], "" if d["streak_now"] == 1 else "s")),
        ("flame", "Best streak", "%d day%s" % (d["streak_long"], "" if d["streak_long"] == 1 else "s")),
        ("pulse", "Active days", "%d day%s" % (d["active_days"], "" if d["active_days"] == 1 else "s")),
        ("star", "Highest in a day", "%d commits" % d["best_day"]),
    ]
    tile_h = 50
    # box layout: the right column is pushed out until its widest entry ends
    # exactly on the panel's right edge, instead of starting at the midpoint
    right_w = max(28 + max(text_w(lbl, 10), text_w(val, 16, bold=True))
                  for _, lbl, val in streak_stats[1::2])
    col_x = (x0, x1 - right_w)
    for i, (icon, label, value) in enumerate(streak_stats):
        col, row = i % 2, i // 2
        bx, by = col_x[col], y + 20 + row * tile_h
        color = ROSE if label in ("Current streak", "Highest in a day") else WHITE
        body.append(_stat_icon(icon, bx, by, color, scale=1.4))
        body.append(text(bx + 28, by + 6, label, size=10, fill=DIM, family=SANS))
        body.append(text(bx + 28, by + 26, value, size=16, fill=color, family=SANS, weight=700,
                         cls="fade", style="animation-delay:%.2fs" % (0.05 + i * 0.04)))

    o = [svg_open(W + SIDE_GAP, H, "Recent coding habits")]
    o.append('<style>' + PANEL_CSS + '</style>')
    o.append('<g transform="translate(%d,0)">' % SIDE_GAP)   # gap on the left, toward the image
    o.extend(body)
    o.append('</g>')
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
    "calendar": '<rect x="1.5" y="2.5" width="11" height="10" rx="1.5"/><path d="M1.5 5.5h11"/>'
                '<path d="M4 1v3M10 1v3"/>',
    "flame":    '<path d="M7 13c-2.7 0-4.6-1.7-4.6-4.1 0-1.9 1.1-2.9 1.8-4.4.3.9.8 1.5 1.5 1.5'
                '.2-2.3 1.2-3.6 2.4-4.5-.3 1.5.2 2.7 1.1 3.7 1 1.1 2.1 1.9 2.1 3.7'
                'C11.6 11.3 9.7 13 7 13Z"/>',
    "check":    '<path d="M2.5 7.3 5.4 10 11.5 3.8"/>',
    "minus":    '<path d="M3 7h8"/>',
    "dot":      '<circle cx="7" cy="7" r="1.6"/>',
}


# Rough advance widths for the system sans stack, as a fraction of the font
# size - close enough to line a column's right edge up with the panel's edge
# (an <img>-loaded SVG can't measure its own text).
_NARROW, _WIDE = set("ijlt.,:;'!|()[] 1rf"), set("mwMW@")


def text_w(s, size, bold=False):
    w = 0.0
    for ch in s:
        if ch in _NARROW:
            w += 0.30
        elif ch in _WIDE:
            w += 0.82
        elif ch.isupper():
            w += 0.64
        elif ch.isdigit():
            w += 0.56
        else:
            w += 0.52
    return w * size * (1.12 if bold else 1.0)


def _stat_icon(name, x, y, color, scale=1.0):
    return ('<g transform="translate(%.1f,%.1f) scale(%.2f)" fill="none" stroke="%s" '
            'stroke-width="1.15" stroke-linecap="round" stroke-linejoin="round">%s</g>'
            % (x, y, scale, color, STAT_ICONS[name]))


def build_repo_stats(d):
    """The left-hand panel next to the outro image, pulled from this run's
    real account data (see `collect`): a two-column grid of account stats,
    then the most recently pushed repositories with their main language and
    how long ago they moved. Zero-by-default counters (sponsors, packages,
    watchers), storage used and the license breakdown were dropped as noise.
    Views need the authenticated query, so without METRICS_TOKEN that stat
    drops out instead of showing 0.
    """
    def plural(n, singular, plural_form):
        return "%s %s" % (format(n, ","), singular if n == 1 else plural_form)

    lang_total = sum(d["langs"].values()) or 1
    n_langs = sum(1 for v in d["langs"].values() if 100 * v / lang_total >= 0.5)
    views = d.get("views_14d")
    stats = [
        ("repo",     plural(d["repo_count"], "Repository", "Repositories"), True),
        ("star",     plural(d["stars"], "Stargazer", "Stargazers"),        False),
        ("fork",     plural(d["forks"], "Forker", "Forkers"),              False),
        ("release",  plural(d["releases"], "Release", "Releases"),         False),
        ("pulse",    plural(d["total"], "contribution", "contributions"),   False),
        ("package",  plural(n_langs, "language", "languages"),             False),
        ("calendar", "Member since %s" % d["created"][:4],                 False),
    ]
    if views is not None:
        stats.append(("eye", ("%.1fk views (14d)" % (views / 1000)) if views >= 1000
                      else "%s (14d)" % plural(views, "view", "views"), False))

    today = dt.date.today()

    def ago(stamp):
        days = (today - dt.date.fromisoformat(stamp[:10])).days
        if days <= 0:
            return "today"
        if days < 30:
            return "%dd ago" % days
        if days < 365:
            return "%dmo ago" % (days // 30)
        return "%dy ago" % (days // 365)

    def main_lang(r):
        langs = {k: v for k, v in r["langs"].items() if k not in IGNORE_LANGS} or r["langs"]
        return max(langs, key=langs.get) if langs else None

    # never list a private repo or this profile repo itself - the queries
    # already ask for public repos only, this is the belt to that brace
    recent = sorted((r for r in d["repos"]
                     if r.get("pushed") and not r.get("private")
                     and r["name"].lower() != USER.lower()),
                    key=lambda r: r["pushed"], reverse=True)[:5]
    # the same rose/neutral steps as the habits ring, so a language keeps
    # one colour across both panels
    ring = [lang for lang, _ in d["langs"].most_common(6)]
    shades = [(ROSE, 1), (WHITE, 0.9), (MUTED, 0.8), (DIM, 0.85), (ROSE, 0.55), (WHITE, 0.5)]

    # Same width and height as the habits panel, so the two sit as a matched
    # pair around the outro image.
    W, H = 336, BOTTOM_H
    pad_x = 2          # flush to both edges; the README spaces it from the outro image
    # box layout: left column on the left edge, right column pushed out until
    # its widest label ends exactly on the right edge
    col_x = (pad_x, W - pad_x - max(27 + text_w(lbl, 14.5) for _, lbl, _ in stats[1::2]))
    # one row height for the stat grid and the repo list alike, stretched so
    # the first icon's top lands on BOTTOM_TOP and the last line's baseline on
    # BOTTOM_BASE - the same span the habits panel fills
    n_stat_rows = -(-len(stats) // 2)
    gap_above, gap_below, label_gap = 18, 26, 6     # divider, section label, list
    n_rows = n_stat_rows + len(recent)
    seps = gap_above + (gap_below + label_gap if recent else 0)
    last_base = 4.5 if recent else 5                # text baseline below row centre
    row_h = (BOTTOM_BASE - BOTTOM_TOP - 9.5 - last_base - seps) / max(1, n_rows - 1)
    stat_h = repo_h = row_h
    y = BOTTOM_TOP + 9.5 - row_h / 2

    body = []
    for i, (key, label, highlight) in enumerate(stats):
        col, row = i % 2, i // 2
        cx = col_x[col]
        cy = y + row * stat_h + stat_h / 2
        body.append(_stat_icon(key, cx, cy - 9.5, ROSE if highlight else MUTED, scale=1.35))
        body.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="14.5" fill="%s" '
                    'class="fade" style="animation-delay:%.2fs">%s</text>'
                    % (cx + 27, cy + 5, SANS, ROSE if highlight else WHITE, i * 0.04, esc(label)))
    y += n_stat_rows * stat_h + gap_above
    body.append('<path d="M%d %.1f H%d" stroke="%s" stroke-width="1"/>' % (pad_x, y, W - pad_x, LINE))
    y += gap_below

    if recent:
        body.append(text(pad_x, y, "RECENTLY PUSHED", size=10, fill=DIM, family=SANS, spacing=1))
        y += label_gap
        for i, r in enumerate(recent):
            ry = y + i * repo_h + repo_h / 2
            lang = main_lang(r)
            color, op = shades[ring.index(lang)] if lang in ring else (DIM, 0.85)
            name = r["name"] if len(r["name"]) <= 24 else r["name"][:23] + "…"
            meta = "%s · %s" % (lang, ago(r["pushed"])) if lang else ago(r["pushed"])
            body.append('<circle cx="%d" cy="%.1f" r="4" fill="%s" opacity="%.2f"/>'
                        % (pad_x + 4, ry, color, op)
                        + '<g class="fade" style="animation-delay:%.2fs">' % (0.1 + i * 0.04)
                        + text(pad_x + 18, ry + 4.5, name, size=13, fill=WHITE, family=SANS)
                        + text(W - pad_x, ry + 4.5, meta, size=11, fill=DIM, family=SANS, anchor="end")
                        + "</g>")

    o = [svg_open(W + SIDE_GAP, H, "Repository stats")]   # gap on the right, toward the image
    o.append('<style>' + PANEL_CSS + '</style>')
    o.extend(body)
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

    # calendar built first so its (data-independent, but grid-shape-dependent)
    # height can be measured and handed to the activity graph — see
    # build_activity_graph's target_h docstring for why that beats each
    # panel guessing at a shared constant
    cal_svg = build_calendar(d)
    cal_h = int(re.search(r'height="(\d+)"', cal_svg).group(1))

    for name, svg in (("contribution-calendar", cal_svg),
                       ("activity-graph", build_activity_graph(d, target_h=cal_h)),
                       ("habits", build_habits(d)),
                       ("repo-stats", build_repo_stats(d))):
        p = out / ("%s.svg" % name)
        p.write_text(svg, encoding="utf8")
        print("  %-22s %7d bytes" % (p.name, p.stat().st_size))


if __name__ == "__main__":
    main()
