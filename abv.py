#!/usr/bin/env python3
"""ABV OB In Progress — a manager-facing static page for Beth King and Daniel Angol.

Renders dist/abv-ob-progress.html from data/abv_data.json, which is a slim,
team-wide snapshot of two board groups (no person filter). Zero JS, one dark
page, print flips to light — the beth.py treatment, same tokens.

Everything on the page is derived here, never in the crawl: the snapshot stores
Monday's column values verbatim so the three known serialisation quirks are
handled once, in one place, and can be tested:

  * AOE Assigned (boolean_mm71c8h0) comes back as the STRING "v" when checked and
    the OBJECT {"checked": false} when not. Naive truthiness counts every row;
    .get("checked") counts none. checked() is the only correct reading.
  * Days Open (formula_mkzb9602) comes back as the STRING "null" — not JSON null —
    when Subscription Start is empty, and can be NEGATIVE when the start date is
    in the future. Neither may be folded into a "0-14" bucket.
  * The "- LATAM" name suffix is a board marker, not part of the account name.

These accounts run on the ABV program clock. The board's 42-day TTV target does
NOT apply to them, so this page shows neutral aging buckets and names no target.

    python3 abv.py                 # build from data/abv_data.json
    python3 abv.py --allow-stale   # skip the freshness gate
"""
import html
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

DATA = "data/abv_data.json"
OUT = "dist/abv-ob-progress.html"
# The Artifact host supplies its own <!doctype>/<head>/<body> skeleton, so the
# publish source is the same page with the outer wrapper removed and <title>
# first — the same rule build.py applies to the Command Center.
OUT_ARTIFACT = "dist/abv-ob-progress.artifact.html"
MAX_AGE_HOURS = 26
BOARD_URL = "https://semrush.monday.com/boards/18372591859/pulses/%s"

# Not Started is excluded from the stage chart on purpose — Tommy asked for
# pipeline volume and in-progress breakdown as separate questions, so it gets
# its own KPI tile instead of competing for the same bar scale.
STAGE_ORDER = ("Discovery", "Enablement", "Adoption", "Launch", "Risk")
# Series colours go through tokens, never raw hex, so the print block flips them
# with everything else. Dark steps (#119dab #8f7ff0 #c0851f #cf5f8a on --panel) and
# print steps (#0f8fa3 #6a4fc8 #8a6410 #a8305d on white) each pass the six-check
# palette validation independently — the print set is stepped, not auto-inverted.
STAGE_COLOR = {"Discovery": "var(--s1)", "Enablement": "var(--s2)",
               "Adoption": "var(--s3)", "Launch": "var(--s4)",
               # --crit is a RESERVED status colour: it ships with an icon and a
               # label, never as colour alone.
               "Risk": "var(--crit)"}
STAGE_ICON = {"Risk": "⚠"}

AGE_BUCKETS = ((0, 14, "0–14 days"), (15, 30, "15–30 days"),
               (31, 45, "31–45 days"), (46, 60, "46–60 days"),
               (61, 10 ** 6, "61+ days"))

LATAM_SUFFIX = re.compile(r"\s*-\s*LATAM\s*$", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


def _e(s):
    return html.escape(str(s), quote=False)


def _ea(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------- quirk parsers

def checked(v):
    """AOE Assigned is checked iff the value is the string "v", or a dict whose
    "checked" is true. Anything else — including {"checked": false} and None —
    is unchecked. Both naive readings fail: bool(v) counts every row because
    {"checked": false} is a non-empty dict, and v.get("checked") counts none
    because the checked case is a bare string."""
    if isinstance(v, str):
        return v.strip().lower() == "v"
    if isinstance(v, dict):
        return bool(v.get("checked"))
    return False


def days_open(r):
    """Board Days Open, or None when there is no clock. The formula returns the
    string "null" (not JSON null) when Subscription Start is empty."""
    v = r.get("days_open")
    if v is None:
        return None
    v = str(v).strip()
    if v in ("", "null", "None"):
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def disp_name(name):
    """Strip the '- LATAM' board marker; it is never part of a rendered name."""
    return LATAM_SUFFIX.sub("", re.sub(r"\s{2,}", " ", (name or "").strip())).strip()


def is_latam(r):
    return bool(LATAM_SUFFIX.search(re.sub(r"\s{2,}", " ", r.get("name") or "")))


def money(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n


# ---------------------------------------------------------------------- derive

def derive(d):
    """Everything the page renders, computed from the verbatim snapshot."""
    rows = []
    for r in d["in_progress"]:
        rows.append(dict(
            r,
            disp=disp_name(r["name"]),
            latam=is_latam(r),
            aoe=checked(r.get("aoe_assigned")),
            days=days_open(r),
            oc=(r.get("oc") or "").strip() or None,
            mrr=money(r.get("mrr")),
        ))
    done = []
    for r in d["onboarded"]:
        done.append(dict(
            r,
            disp=disp_name(r["name"]),
            aoe=checked(r.get("aoe_assigned")),
            days=days_open(r),
            oc=(r.get("oc") or "").strip() or None,
            ttv_outcome=(r.get("ttv_outcome") or "").strip(),
        ))

    stage_n = {s: sum(1 for r in rows if r["stage"] == s) for s in STAGE_ORDER}
    not_started = [r for r in rows if r["stage"] == "Not Started"]
    # any stage that is not "Not Started" counts as in progress, including a
    # stage label this build has never seen — surfaced, never silently dropped.
    in_progress = [r for r in rows if r["stage"] != "Not Started"]
    unknown_stages = sorted({r["stage"] for r in in_progress} - set(STAGE_ORDER))

    aoe_yes = [r for r in rows if r["aoe"]]
    aoe_no = [r for r in rows if not r["aoe"]]

    by_stage = []
    for s in ["Not Started"] + list(STAGE_ORDER):
        sub = [r for r in rows if r["stage"] == s]
        if not sub and s == "Risk":
            by_stage.append({"stage": s, "n": 0, "yes": 0})
            continue
        if not sub:
            continue
        by_stage.append({"stage": s, "n": len(sub),
                         "yes": sum(1 for r in sub if r["aoe"])})

    ocs = defaultdict(list)
    for r in rows:
        ocs[r["oc"] or "Unassigned"].append(r)
    by_oc = []
    for oc, sub in ocs.items():
        ages = [r["days"] for r in sub if r["days"] is not None and r["days"] >= 0]
        by_oc.append({
            "oc": oc, "n": len(sub),
            "not_started": sum(1 for r in sub if r["stage"] == "Not Started"),
            "in_progress": sum(1 for r in sub if r["stage"] != "Not Started"),
            "yes": sum(1 for r in sub if r["aoe"]),
            "oldest": max(ages) if ages else None,
            "unassigned": oc == "Unassigned",
        })
    # busiest first, then worst AOE rate, then name — Unassigned always last
    by_oc.sort(key=lambda x: (x["unassigned"], -x["n"], x["yes"] / x["n"], x["oc"]))

    ages = {lab: 0 for _, _, lab in AGE_BUCKETS}
    no_clock, future = [], []
    for r in rows:
        v = r["days"]
        if v is None:
            no_clock.append(r)
            continue
        if v < 0:
            future.append(r)
            continue
        for lo, hi, lab in AGE_BUCKETS:
            if lo <= v <= hi:
                ages[lab] += 1
                break

    hygiene = {
        "no_start": no_clock,
        "future_start": future,
        "no_oc": [r for r in rows if not r["oc"]],
        "no_region": [r for r in rows if not (r.get("region") or "").strip()],
        "no_products": [r for r in rows if not (r.get("products") or "").strip()],
    }
    risk_flagged = [r for r in rows
                    if (r.get("risk_status") or "").strip()
                    and (r.get("risk_status") or "").strip() != "Done"]

    gen = datetime.strptime(d["generated_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - gen).total_seconds() / 3600

    return {
        "generated_at_utc": d["generated_at_utc"], "age_h": age_h,
        "board": d["board"], "groups": d["groups"],
        "rows": rows, "done": done, "total": len(rows),
        "stage_n": stage_n, "unknown_stages": unknown_stages,
        "not_started": not_started, "in_progress": in_progress,
        "aoe_yes": aoe_yes, "aoe_no": aoe_no,
        "by_stage": by_stage, "by_oc": by_oc,
        "ages": ages, "no_clock": no_clock, "future": future,
        "hygiene": hygiene, "risk_flagged": risk_flagged,
    }


# ------------------------------------------------------------------------- css
# Dark by deliberate commitment (this is the Command Center's visual world, and
# the two pages sit side by side); print flips the tokens to light so the
# handout stays clean. Every colour is a token declared on :root, so nothing
# depends on a media query having matched.
CSS = """
:root{color-scheme:dark;
  --void:#0a0e14; --panel:#11161f; --raise:#171e2b;
  --ink:#e9eef7; --ink-2:#9aa7ba; --muted:#7b89a0;
  --grid:#232c3d; --hair:rgba(140,170,220,.14); --hover:#151c28;
  --cy:#3ee0f0; --vi:#8f7ff0;
  --good:#3ddc97; --warn:#f5b83d; --crit:#ff5d5d;
  --s1:#119dab; --s2:#8f7ff0; --s3:#c0851f; --s4:#cf5f8a;
  --disp:"Geist",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"Geist Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--void);color:var(--ink);font:14.5px/1.6 var(--disp)}
.wrap{max-width:980px;margin:0 auto;padding:34px 26px 64px}

header{display:flex;gap:16px;align-items:flex-start;
       border-bottom:2px solid var(--cy);padding-bottom:16px;margin-bottom:26px}
.tile{flex:0 0 auto;width:46px;height:46px;border-radius:11px;background:var(--raise);
      border:1px solid var(--grid);display:flex;align-items:center;justify-content:center;
      font:700 16px var(--mono);letter-spacing:.06em;color:var(--cy)}
.hd{min-width:0}
h1{font:700 25px/1.15 var(--disp);letter-spacing:.035em;text-transform:uppercase;margin:0;
   text-wrap:balance}
h1 b{color:var(--cy);font-weight:700}
.sub{color:var(--muted);font:12px/1.65 var(--mono);margin-top:7px}
.lede{color:var(--ink-2);font:14px/1.65 var(--disp);margin:0 0 4px;max-width:64ch}

h2{font:700 12px/1.3 var(--disp);letter-spacing:.14em;text-transform:uppercase;
   color:var(--cy);margin:38px 0 12px;display:flex;align-items:center;gap:8px}
h2::before{content:"//";color:var(--muted);font:700 11px var(--mono)}
h2 span.n{color:var(--muted);font:600 11px var(--mono);letter-spacing:.06em}

.stalebanner{background:rgba(245,184,61,.1);border:1px solid rgba(245,184,61,.45);
  border-left:3px solid var(--warn);border-radius:10px;padding:11px 15px;margin:0 0 22px;
  color:var(--ink-2);font:13px/1.6 var(--disp)}
.stalebanner b{color:var(--warn);display:block;font:700 12px var(--disp);
  letter-spacing:.09em;text-transform:uppercase;margin-bottom:3px}

.bkpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:11px}
.bkpi{background:var(--panel);border:1px solid var(--grid);border-radius:12px;
      padding:14px 16px;cursor:help;min-width:0}
.bkpi .v{font:700 27px/1.1 var(--disp);color:var(--ink);font-variant-numeric:tabular-nums}
.bkpi .v small{font:600 15px var(--disp);color:var(--ink-2)}
.bkpi .l{font:600 10.5px/1.4 var(--disp);letter-spacing:.09em;text-transform:uppercase;
         color:var(--muted);margin-top:5px}
.bkpi .s{font:11px/1.5 var(--mono);color:var(--muted);margin-top:7px;
         padding-top:7px;border-top:1px solid var(--hair)}

.chart{background:var(--panel);border:1px solid var(--hair);border-radius:12px;
       padding:16px 16px 12px}
.chart svg{display:block;width:100%;height:auto}
.chart .cap{color:var(--muted);font:11.5px/1.6 var(--mono);margin-top:10px;
            padding-top:9px;border-top:1px solid var(--hair)}
text{font:600 11px var(--mono);fill:var(--ink-2)}
text.nm{fill:var(--ink);font:600 12px var(--disp)}
text.val{fill:var(--ink-2);font-variant-numeric:tabular-nums}
text.zero{fill:var(--muted)}

.tblwrap{overflow-x:auto;background:var(--panel);border:1px solid var(--hair);
         border-radius:12px}
.btbl{width:100%;border-collapse:collapse;font:13px/1.5 var(--disp);
      font-variant-numeric:tabular-nums}
.btbl th{font:600 10px var(--disp);letter-spacing:.1em;text-transform:uppercase;
         color:var(--muted);text-align:left;padding:9px 12px;
         border-bottom:1px solid var(--grid);white-space:nowrap}
.btbl td{padding:8px 12px;border-bottom:1px solid var(--hair);color:var(--ink-2);
         vertical-align:middle}
.btbl tr:last-child td{border-bottom:0}
.btbl td.nm{color:var(--ink);font-weight:600}
.btbl td.num,.btbl th.num{text-align:right}
.btbl a{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--hair)}
.btbl a:hover{color:var(--cy);border-bottom-color:var(--cy)}
.btbl a:focus-visible{outline:2px solid var(--cy);outline-offset:2px;border-radius:2px}
.btbl tr.tot td{border-top:1px solid var(--grid);border-bottom:0;color:var(--muted);
                font:600 11px var(--mono);letter-spacing:.04em}

.rate{display:inline-flex;align-items:center;gap:7px;justify-content:flex-end;width:100%}
.rate .bar{width:52px;height:5px;border-radius:3px;background:var(--grid);
           overflow:hidden;flex:0 0 auto}
.rate .bar i{display:block;height:100%;background:var(--cy);border-radius:3px}
.rate .bar.full i{background:var(--good)}
.rate .bar.none i{background:var(--crit)}
.rate .pc{font:600 11.5px var(--mono);color:var(--ink-2);min-width:34px;text-align:right}

.chip{font:700 9.5px var(--mono);text-transform:uppercase;letter-spacing:.07em;
      border-radius:5px;padding:2px 7px;white-space:nowrap;border:1px solid;
      display:inline-block}
.chip.gap{background:rgba(255,93,93,.12);color:var(--crit);border-color:rgba(255,93,93,.4)}
.chip.hyg{background:rgba(245,184,61,.1);color:var(--warn);border-color:rgba(245,184,61,.4)}
.chip.ok{background:rgba(61,220,151,.1);color:var(--good);border-color:rgba(61,220,151,.4)}
.chip.na{background:rgba(123,137,160,.12);color:var(--muted);border-color:rgba(123,137,160,.4)}

.note{color:var(--ink-2);font:13px/1.7 var(--disp);background:var(--panel);
      border:1px solid var(--hair);border-radius:12px;padding:12px 16px;max-width:74ch}
.note b{color:var(--ink)}
.note.q{border-left:3px solid var(--vi)}
.note.w{border-left:3px solid var(--warn)}

.two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:11px;align-items:start}
.stack{display:flex;flex-direction:column;gap:11px}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:10px;
        color:var(--ink-2);font:600 11px var(--mono)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;
          margin-right:6px;vertical-align:-1px}

footer{margin-top:46px;padding-top:16px;border-top:1px solid var(--grid);
       color:var(--muted);font:11.5px/1.75 var(--disp);max-width:78ch}
footer b{color:var(--ink-2)}

@media(max-width:820px){
  .bkpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  .two{grid-template-columns:minmax(0,1fr)}
  .wrap{padding:26px 16px 48px}
  h1{font-size:21px}
}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

/* print flips the tokens back to light for the handout */
@media print{
  :root{color-scheme:light;
    --void:#fff; --panel:#fff; --raise:#f2f5fa;
    --ink:#1c2433; --ink-2:#3a4557; --muted:#5a6678;
    --grid:#c9d2e0; --hair:#d7deea; --hover:#f2f5fa;
    --cy:#0e7a8a; --vi:#6a4fc8;
    --good:#20713a; --warn:#8a6410; --crit:#b8322f;
    --s1:#0f8fa3; --s2:#6a4fc8; --s3:#8a6410; --s4:#a8305d}
  body{background:#fff}
  .chart,.tblwrap,.note,.bkpi,.stalebanner{border-color:#c9d2e0}
  h2{margin-top:22px}
  .btbl a{color:#1c2433;border-bottom:0}
  section{break-inside:avoid}
}
@page{margin:1.5cm}
"""


# ---------------------------------------------------------------------- charts

def chart_stages(c):
    """Horizontal bars, one per in-progress stage. Not Started is excluded by
    design and carried as its own KPI. Every bar is directly labelled, which is
    also the secondary encoding the stage hues need (adjacent-pair tritan
    separation sits in the 6-8 band)."""
    rows = [(s, c["stage_n"].get(s, 0)) for s in STAGE_ORDER]
    mx = max([n for _, n in rows] + [1])
    # VW reserves room for the longest value label ("100 accounts · 100% of book")
    # so the longest bar's label still lands inside the viewBox.
    W, LAB, VW, BH, GAP = 800, 116, 196, 26, 11
    plot = W - LAB - VW
    H = len(rows) * (BH + GAP) + 4
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">'
         % (W, H, _ea("Accounts at each in-progress stage: "
                      + ", ".join("%s %d" % (s, n) for s, n in rows)))]
    for i, (s, n) in enumerate(rows):
        y = i * (BH + GAP) + 2
        icon = STAGE_ICON.get(s, "")
        label = (icon + " " if icon else "") + s
        p.append('<text class="nm" x="0" y="%d">%s</text>' % (y + BH - 8, _e(label)))
        if n:
            w = max(6, round(plot * n / mx))
            p.append('<rect x="%d" y="%d" width="%d" height="%d" rx="4" fill="%s"/>'
                     % (LAB, y, w, BH, STAGE_COLOR[s]))
            share = 100.0 * n / c["total"] if c["total"] else 0
            p.append('<text class="val" x="%d" y="%d">%d account%s · %.0f%% of book</text>'
                     % (LAB + w + 10, y + BH - 8, n, "" if n == 1 else "s", share))
        else:
            p.append('<rect x="%d" y="%d" width="4" height="%d" rx="2" fill="var(--grid)"/>'
                     % (LAB, y, BH))
            p.append('<text class="zero" x="%d" y="%d">none at this stage</text>'
                     % (LAB + 14, y + BH - 8))
    p.append("</svg>")
    leg = "".join('<span><i style="background:%s"></i>%s</span>'
                  % (STAGE_COLOR[s], _e((STAGE_ICON.get(s, "") + " " + s).strip()))
                  for s, _ in rows)
    return ('<div class="chart">' + "".join(p) + '<div class="legend">' + leg + "</div>"
            '<div class="cap">The %d accounts already moving. Not Started (%d) is counted '
            'separately above — it is a different question. Share is of all %d ABV accounts '
            'in the pipeline.</div></div>'
            % (len(c["in_progress"]), len(c["not_started"]), c["total"]))


def chart_aging(c):
    """Neutral aging distribution. One violet series, no target line, no zones —
    ABV accounts run on their own program clock and the board's TTV target does
    not apply to them, so nothing here is scored good or bad."""
    rows = [(lab, c["ages"][lab]) for _, _, lab in AGE_BUCKETS]
    extra = [("No start date yet", len(c["no_clock"])),
             ("Start date in the future", len(c["future"]))]
    mx = max([n for _, n in rows + extra] + [1])
    W, LAB, VW, BH, GAP = 800, 178, 120, 22, 10
    plot = W - LAB - VW
    SEP = 16
    H = (len(rows) + len(extra)) * (BH + GAP) + SEP + 6
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">'
         % (W, H, _ea("Days open across the ABV pipeline: "
                      + ", ".join("%s %d" % (l, n) for l, n in rows + extra)))]
    y = 2
    for lab, n in rows:
        p.append('<text class="nm" x="0" y="%d">%s</text>' % (y + BH - 6, _e(lab)))
        if n:
            w = max(5, round(plot * n / mx))
            p.append('<rect x="%d" y="%d" width="%d" height="%d" rx="4" fill="var(--vi)"/>'
                     % (LAB, y, w, BH))
            p.append('<text class="val" x="%d" y="%d">%d</text>' % (LAB + w + 10, y + BH - 6, n))
        else:
            p.append('<rect x="%d" y="%d" width="4" height="%d" rx="2" fill="var(--grid)"/>'
                     % (LAB, y, BH))
            p.append('<text class="zero" x="%d" y="%d">0</text>' % (LAB + 14, y + BH - 6))
        y += BH + GAP
    # the two no-clock categories are drawn below a rule, hollow, so they read as
    # "not on this scale" rather than as a longer or shorter duration
    p.append('<line x1="0" y1="%d" x2="%d" y2="%d" stroke="var(--grid)" stroke-width="1"/>'
             % (y + SEP // 2 - 4, W, y + SEP // 2 - 4))
    y += SEP
    for lab, n in extra:
        p.append('<text class="nm" x="0" y="%d" style="fill:var(--muted)">%s</text>'
                 % (y + BH - 6, _e(lab)))
        w = max(5, round(plot * n / mx)) if n else 4
        p.append('<rect x="%d" y="%d" width="%d" height="%d" rx="4" fill="none" '
                 'stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="3 3"/>'
                 % (LAB, y, w, BH))
        p.append('<text class="val" x="%d" y="%d">%d</text>' % (LAB + w + 10, y + BH - 6, n))
        y += BH + GAP
    p.append("</svg>")
    tot = sum(n for _, n in rows) + sum(n for _, n in extra)
    return ('<div class="chart">' + "".join(p) +
            '<div class="cap">Board Days Open, counted from Subscription Start. '
            'All categories sum to %d. The two dashed rows have no clock running and are '
            'not placed on the day scale.</div></div>' % tot)


# ------------------------------------------------------------------------ page

def kpi(v, label, src, sub=None):
    small = ("<small>%s</small>" % _e(sub)) if sub else ""
    return ('<div class="bkpi" title="%s"><div class="v">%s%s</div>'
            '<div class="l">%s</div><div class="s">%s</div></div>'
            % (_ea(src), _e(v), small, _e(label), _e(src)))


def rate_cell(yes, n):
    pc = round(100.0 * yes / n) if n else 0
    cls = " full" if yes == n and n else (" none" if yes == 0 else "")
    return ('<td class="num"><span class="rate"><span class="bar%s">'
            '<i style="width:%d%%"></i></span><span class="pc">%d%%</span></span></td>'
            % (cls, pc, pc))


def render(c):
    A = []
    a = A.append
    grp = c["groups"]["in_progress"]

    a('<div class="wrap">')
    a('<header><div class="tile" aria-hidden="true">OB</div><div class="hd">'
      '<h1>ABV <b>OB In Progress</b></h1>'
      '<div class="sub">Beth King · Daniel Angol · %s · generated %s</div>'
      '</div></header>'
      % (_e(c["board"]["name"]), _e(et_stamp(c["generated_at_utc"]))))

    if c["age_h"] > MAX_AGE_HOURS:
        a('<div class="stalebanner"><b>This page has not refreshed</b>'
          'The last successful pull was %.0f hours ago (%s). The scheduled weekday '
          'rebuild has not run or could not publish — the numbers below are from that '
          'earlier pull, not from the board as it stands now.</div>'
          % (c["age_h"], _e(et_stamp(c["generated_at_utc"]))))

    a('<p class="lede">Every ABV account the onboarding team is carrying, across all '
      'consultants — read straight off the board group “%s”, with no person filter.</p>'
      % _e(grp["title"]))

    # ---- KPI row
    a('<div class="bkpis">')
    a(kpi(c["total"], "In the ABV pipeline",
          "board group %s, live count" % grp["id"]))
    a(kpi(len(c["not_started"]), "Not Started",
          "Stage = Not Started (color_mkyrdx3)"))
    a(kpi(len(c["in_progress"]), "In progress",
          "every stage except Not Started"))
    a(kpi(len(c["aoe_yes"]), "AOE Assigned",
          "AOE Assigned ticked (boolean_mm71c8h0)",
          sub=" / %d" % c["total"]))
    a("</div>")

    if c["unknown_stages"]:
        a('<div class="note w" style="margin-top:11px"><b>New stage label on the board.</b> '
          '%s — counted as in progress and shown in the tables, but this page has no '
          'colour for it yet.</div>'
          % _e(", ".join(c["unknown_stages"])))

    # ---- stage breakdown
    a('<section><h2>Where the in-progress work sits <span class="n">%d accounts</span></h2>'
      % len(c["in_progress"]))
    a(chart_stages(c))
    a("</section>")

    # ---- AOE
    yes, no = len(c["aoe_yes"]), len(c["aoe_no"])
    pc = round(100.0 * yes / c["total"]) if c["total"] else 0
    ns_miss = sum(1 for r in c["aoe_no"] if r["stage"] == "Not Started")
    a('<section><h2>AOE Assigned <span class="n">%d of %d · %d%%</span></h2>' % (yes, c["total"], pc))
    a('<div class="note q"><b>%d ABV accounts have no AOE assigned.</b> %s</div>'
      % (no,
         _e("%d of those %d sit in Not Started — the gap is concentrated at the front of the "
            "pipeline, before onboarding has begun." % (ns_miss, no)
            if ns_miss and no else
            "They are spread across the active stages rather than concentrated in one place."
            if no else
            "Every account on the board has one.")))

    a('<div class="two" style="margin-top:11px">')
    # by stage
    a('<div class="tblwrap"><table class="btbl">'
      '<thead><tr><th>Stage</th><th class="num">Assigned</th><th class="num">Total</th>'
      '<th class="num">Rate</th></tr></thead><tbody>')
    for s in c["by_stage"]:
        label = (STAGE_ICON.get(s["stage"], "") + " " + s["stage"]).strip()
        if not s["n"]:
            a('<tr><td class="nm">%s</td><td class="num">—</td><td class="num">0</td>'
              '<td class="num"><span class="chip na">none</span></td></tr>' % _e(label))
            continue
        a('<tr><td class="nm">%s</td><td class="num">%d</td><td class="num">%d</td>%s</tr>'
          % (_e(label), s["yes"], s["n"], rate_cell(s["yes"], s["n"])))
    a('<tr class="tot"><td>All stages</td><td class="num">%d</td><td class="num">%d</td>'
      '<td class="num">%d%%</td></tr>' % (yes, c["total"], pc))
    a("</tbody></table></div>")
    # by consultant
    a('<div class="tblwrap"><table class="btbl">'
      '<thead><tr><th>Consultant</th><th class="num">Assigned</th><th class="num">Total</th>'
      '<th class="num">Rate</th></tr></thead><tbody>')
    for o in c["by_oc"]:
        nm = ('<span class="chip na">%s</span>' % _e(o["oc"])) if o["unassigned"] else _e(o["oc"])
        a('<tr><td class="nm">%s</td><td class="num">%d</td><td class="num">%d</td>%s</tr>'
          % (nm, o["yes"], o["n"], rate_cell(o["yes"], o["n"])))
    a('<tr class="tot"><td>%d consultants</td><td class="num">%d</td><td class="num">%d</td>'
      '<td class="num">%d%%</td></tr>' % (len(c["by_oc"]), yes, c["total"], pc))
    a("</tbody></table></div></div>")

    # the actionable list
    if c["aoe_no"]:
        a('<h2 style="margin-top:26px">AOE not assigned <span class="n">%d accounts</span></h2>' % no)
        a('<div class="tblwrap"><table class="btbl">'
          '<thead><tr><th>Account</th><th>Stage</th><th>Consultant</th>'
          '<th class="num">Days open</th></tr></thead><tbody>')
        order = {"Not Started": 0}
        for i, s in enumerate(STAGE_ORDER):
            order[s] = i + 1
        for r in sorted(c["aoe_no"], key=lambda r: (order.get(r["stage"], 9),
                                                    -(r["days"] if r["days"] is not None else -1),
                                                    r["disp"])):
            d = ("—" if r["days"] is None else str(r["days"]))
            a('<tr><td class="nm"><a href="%s">%s</a></td><td>%s</td><td>%s</td>'
              '<td class="num">%s</td></tr>'
              % (_ea(r["url"]), _e(r["disp"]), _e(r["stage"]),
                 _e(r["oc"] or "Unassigned"), _e(d)))
        a("</tbody></table></div>")
    a("</section>")

    # ---- consultant load
    a('<section><h2>Consultant load <span class="n">%d rows · %d accounts</span></h2>'
      % (len(c["by_oc"]), c["total"]))
    a('<div class="tblwrap"><table class="btbl">'
      '<thead><tr><th>Consultant</th><th class="num">Accounts</th><th class="num">Not Started</th>'
      '<th class="num">In progress</th><th class="num">AOE</th>'
      '<th class="num">Oldest</th></tr></thead><tbody>')
    for o in c["by_oc"]:
        nm = ('<span class="chip na">%s</span>' % _e(o["oc"])) if o["unassigned"] else _e(o["oc"])
        old = "—" if o["oldest"] is None else "%dd" % o["oldest"]
        a('<tr><td class="nm">%s</td><td class="num">%d</td><td class="num">%d</td>'
          '<td class="num">%d</td>%s<td class="num">%s</td></tr>'
          % (nm, o["n"], o["not_started"], o["in_progress"],
             rate_cell(o["yes"], o["n"]), _e(old)))
    a('<tr class="tot"><td>Total</td><td class="num">%d</td><td class="num">%d</td>'
      '<td class="num">%d</td><td class="num">%d%%</td><td class="num"></td></tr>'
      % (c["total"], len(c["not_started"]), len(c["in_progress"]), pc))
    a("</tbody></table></div>")
    a('<div class="note" style="margin-top:11px"><b>Oldest</b> is the highest Days Open in that '
      'consultant’s ABV book. Accounts with no Subscription Start have no clock and are '
      'excluded from it.</div>')
    a("</section>")

    # ---- aging
    a('<section><h2>How long these have been open</h2>')
    a('<div class="note q">These accounts run on the <b>ABV program clock</b>. The onboarding '
      'board’s day-count target is written for standard onboarding and does not apply to '
      'them, so the buckets below are neutral — no target line, no pass or fail, nothing '
      'scored good or bad. Read them as distribution, not performance.</div>')
    a('<div style="margin-top:11px">' + chart_aging(c) + "</div>")
    a("</section>")

    # ---- completed + hygiene
    a('<section><h2>Completed &amp; data gaps</h2><div class="two">')
    a('<div class="stack">')
    a('<div class="tblwrap"><table class="btbl">'
      '<thead><tr><th>ABV Onboarded</th><th>Consultant</th><th class="num">Days open</th>'
      '<th>End date</th></tr></thead><tbody>')
    for r in sorted(c["done"], key=lambda r: -(r["days"] or 0)):
        end = r.get("end_date") or ""
        cell = _e(end) if end else '<span class="chip hyg">missing</span>'
        a('<tr><td class="nm"><a href="%s">%s</a></td><td>%s</td><td class="num">%s</td>'
          '<td>%s</td></tr>'
          % (_ea(r["url"]), _e(r["disp"]), _e(r["oc"] or "Unassigned"),
             _e("—" if r["days"] is None else r["days"]), cell))
    a("</tbody></table></div>")
    noend = [r for r in c["done"] if not (r.get("end_date") or "")]
    if noend:
        a('<div class="note w"><b>No cycle time can be read from this group.</b> %d of the %d '
          'onboarded accounts have no Onboarding End Date, so their Days Open is still '
          'counting (%s) and the board’s TTV Outcome column stays blank. Treat this as a '
          'board-hygiene item, not '
          'as throughput.</div>'
          % (len(noend), len(c["done"]),
             _e(", ".join("%s %dd" % (r["disp"], r["days"])
                          for r in noend if r["days"] is not None))))
    a("</div>")

    h = c["hygiene"]
    a('<div class="tblwrap"><table class="btbl">'
      '<thead><tr><th>Gap in the in-progress group</th><th class="num">Accounts</th>'
      '</tr></thead><tbody>')
    for label, rows_ in (("No Subscription Start (no clock)", h["no_start"]),
                         ("Start date in the future", h["future_start"]),
                         ("No onboarding consultant", h["no_oc"]),
                         ("No Region", h["no_region"]),
                         ("No Products Purchased", h["no_products"])):
        if not rows_:
            a('<tr><td class="nm">%s</td><td class="num"><span class="chip ok">clear</span>'
              '</td></tr>' % _e(label))
            continue
        names = ", ".join(r["disp"] for r in sorted(rows_, key=lambda r: r["disp"]))
        a('<tr><td class="nm">%s<div style="font:11.5px/1.55 var(--mono);color:var(--muted);'
          'font-weight:400;margin-top:3px">%s</div></td>'
          '<td class="num"><span class="chip hyg">%d</span></td></tr>'
          % (_e(label), _e(names), len(rows_)))
    a("</tbody></table></div></div>")
    a('<div class="note" style="margin-top:11px">Suggest-only. Nothing on this page is written '
      'back to Monday — the board stays the source of truth.</div>')
    a("</section>")

    # ---- risk
    if c["risk_flagged"]:
        a('<section><h2>Risk flags <span class="n">%d</span></h2>' % len(c["risk_flagged"]))
        a('<div class="tblwrap"><table class="btbl">'
          '<thead><tr><th>Account</th><th>Status</th><th>Type</th><th>Stage</th>'
          '<th>Consultant</th></tr></thead><tbody>')
        for r in c["risk_flagged"]:
            a('<tr><td class="nm"><a href="%s">%s</a></td>'
              '<td><span class="chip gap">%s</span></td><td>%s</td><td>%s</td><td>%s</td></tr>'
              % (_ea(r["url"]), _e(r["disp"]), _e(r["risk_status"]),
                 _e(r.get("risk_type") or "—"), _e(r.get("risk_stage") or "—"),
                 _e(r["oc"] or "Unassigned")))
        a("</tbody></table></div></section>")

    a('<footer><b>Where these numbers come from.</b> Two reads of board %s — group '
      '%s (%d accounts) and group %s (%d accounts) — with no person filter, so this is the '
      'whole team’s ABV book. Stage, AOE Assigned, consultant, dates and Days Open are '
      'copied from the board columns; nothing on this page is authored by hand and nothing '
      'is written back.<br><br>'
      '<b>Two things worth knowing.</b> ABV accounts are identified by board group, not by '
      'account name — most are named plainly (Colgate, Asus, Kohler), so a name-based rule '
      'would miss them. And Days Open counts from Subscription Start, so the %d accounts '
      'without one show no age at all rather than a zero.<br><br>'
      'Rebuilt each weekday morning. If the run fails, a banner appears at the top of this '
      'page — no banner means these figures are current.</footer>'
      % (_e(c["board"]["id"]), _e(c["groups"]["in_progress"]["id"]), c["total"],
         _e(c["groups"]["onboarded"]["id"]), len(c["done"]), len(c["no_clock"])))
    a("</div>")
    return "\n".join(A)


def et_stamp(utc):
    """UTC ISO -> a readable America/New_York stamp, without pulling in a tz
    dependency: ET is UTC-4 between the second Sunday in March and the first
    Sunday in November, UTC-5 otherwise."""
    from datetime import timedelta
    t = datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ")

    def nth_sunday(year, month, n):
        d = datetime(year, month, 1)
        d += timedelta(days=(6 - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)

    start = nth_sunday(t.year, 3, 2) + timedelta(hours=7)    # 02:00 ET = 07:00 UTC
    end = nth_sunday(t.year, 11, 1) + timedelta(hours=6)     # 02:00 EDT = 06:00 UTC
    edt = start <= t < end
    local = t - timedelta(hours=4 if edt else 5)
    return local.strftime("%a %-d %b %Y · %-I:%M %p ") + ("EDT" if edt else "EST")


HEAD = ("<title>ABV OB In Progress</title>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Geist:wght@400;600;700&family=Geist+Mono:wght@400;600;700&display=swap">\n')


# ------------------------------------------------------------------ privacy gate

def privacy_check(d, page):
    """This page is manager-facing and will be forwarded. It carries account
    names, stages and counts — never contact details. The snapshot is not
    supposed to contain any, so the gate is structural on both sides: refuse if
    a contact-shaped column ever joins the snapshot, and refuse if anything
    email-shaped reaches the rendered bytes."""
    banned = ("poc_email", "sf_url", "email", "contact", "body", "subject")
    for group in ("in_progress", "onboarded"):
        for r in d.get(group, []):
            hit = sorted(set(r) & set(banned))
            if hit:
                raise SystemExit("ABV EXPORT REFUSED — snapshot carries contact-shaped "
                                 "fields %r on %r" % (hit, r.get("name")))
    found = EMAIL.findall(page)
    if found:
        raise SystemExit("ABV EXPORT REFUSED — email addresses reached the output: %r"
                         % sorted(set(found))[:3])


def emit(d, out=OUT, out_artifact=OUT_ARTIFACT):
    c = derive(d)
    page = HEAD + "<style>%s</style>\n" % CSS + render(c)
    privacy_check(d, page)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write("<!DOCTYPE html>\n<html lang='en'>\n" + page + "\n</html>\n")
    with open(out_artifact, "w") as f:
        f.write(page)
    return out, c


def main(argv):
    with open(DATA) as f:
        d = json.load(f)
    gen = datetime.strptime(d["generated_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - gen).total_seconds() / 3600
    if age_h > MAX_AGE_HOURS and "--allow-stale" not in argv:
        print("BUILD FAILED: snapshot is %.1fh old (> %dh). Re-run the crawl in abv_pull.md "
              "or pass --allow-stale." % (age_h, MAX_AGE_HOURS))
        return 1
    if age_h < -0.5:
        print("BUILD FAILED: generated_at_utc is %.1fh in the future — clock or typo error."
              % -age_h)
        return 1
    path, c = emit(d)
    for p in (path, OUT_ARTIFACT):
        print("OK %s  %s B" % (p, format(os.path.getsize(p), ",")))
    print("   %d in pipeline · %d Not Started · %d in progress · AOE %d/%d"
          % (c["total"], len(c["not_started"]), len(c["in_progress"]),
             len(c["aoe_yes"]), c["total"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
