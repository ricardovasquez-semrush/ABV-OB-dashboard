#!/usr/bin/env python3
"""ABV OB In Progress — a manager dashboard for Beth King and Daniel Angol.

Renders dist/abv-ob-progress.html from data/abv_data.json: a slim, team-wide
snapshot of two board groups, with no person filter. Five tabbed sections,
Adobe Spectrum design language, light and dark both designed and both validated
to WCAG AA.

DESIGN SYSTEM — read out of ~/Documents/Adobe Branding/ (a saved Adobe web app,
not a written guideline; the brand lives in its Spectrum tokens):
  * Adobe red #EB1000 is `--feds-color-adobeBrand` and in that whole bundle it
    dresses exactly one thing: the logo. Nothing else in Adobe's UI is red. So
    it is the ABV mark here and nothing else, and the working accent is
    Adobe's own CTA blue #3B63FB.
  * Type is adobe-clean, which is Typekit-licensed and cannot load here. Adobe's
    own declared fallback is Source Sans Pro — free, and on Google Fonts as
    Source Sans 3. Source Code Pro is Spectrum's mono.
  * 14px base, 4px spacing unit, 4/8/16px radii, 2px focus ring with a 2px gap.

Every colour pair on the page was run through a WCAG checker; every chart
palette through a six-check validator, light and dark separately. gray-500
#909090 is 3.19:1 on white and is therefore NEVER text — Spectrum means it as a
placeholder colour and it is used as one.

DATA QUIRKS — owned here, never in the crawl, because the snapshot stores
Monday's values verbatim:
  * AOE Assigned (boolean_mm71c8h0) is the STRING "v" when checked and the
    OBJECT {"checked": false} when not. Naive truthiness counts every row;
    .get("checked") counts none. checked() is the only correct reading.
  * Days Open (formula_mkzb9602) is the STRING "null" when Subscription Start is
    empty, and goes NEGATIVE for a future start date. Neither is a "0-14" day.
  * The "- LATAM" name suffix is a board marker, not part of the account name.

These accounts run on the ABV program clock. The board's 42-day target does NOT
apply, so aging is shown as a neutral distribution and no target is named.

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
# The Artifact host supplies its own <!doctype>/<head>/<body>, so the publish
# source is the same page with the outer wrapper removed and <title> first.
OUT_ARTIFACT = "dist/abv-ob-progress.artifact.html"
MAX_AGE_HOURS = 26

# Not Started is excluded from the stage chart on purpose — pipeline volume and
# in-progress breakdown were asked as separate questions, so Not Started gets
# its own KPI rather than dominating the bar scale.
STAGE_ORDER = ("Discovery", "Enablement", "Adoption", "Launch", "Risk")
# Adobe's Spectrum "visual colour" set — the categorical palette Adobe already
# tuned to sit at equal weight. Red is deliberately absent: it is the reserved
# negative status colour, so Risk gets it, with an icon and a label, never alone.
STAGE_VAR = {"Discovery": "--viz-1", "Enablement": "--viz-2",
             "Adoption": "--viz-3", "Launch": "--viz-4",
             "Risk": "--negative-icon"}
STAGE_ICON = {"Risk": "⚠"}

AGE_BUCKETS = ((0, 14, "0–14 days"), (15, 30, "15–30 days"),
               (31, 45, "31–45 days"), (46, 60, "46–60 days"),
               (61, 10 ** 6, "61+ days"))

TABS = (("overview", "Overview"), ("aoe", "AOE Coverage"), ("team", "Team"),
        ("aging", "Aging"), ("data", "Completed &amp; Data"))

LATAM_SUFFIX = re.compile(r"\s*-\s*LATAM\s*$", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


def _e(s):
    return html.escape(str(s), quote=False)


def _ea(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------- quirk parsers

def checked(v):
    """AOE Assigned is checked iff the value is the string "v", or a dict whose
    "checked" is true. Both naive readings fail: bool(v) counts every row
    because {"checked": false} is a non-empty dict, and v.get("checked") counts
    none because the checked case is a bare string."""
    if isinstance(v, str):
        return v.strip().lower() == "v"
    if isinstance(v, dict):
        return bool(v.get("checked"))
    return False


def days_open(r):
    """Board Days Open, or None when no clock is running. The formula returns
    the string "null" — not JSON null — when Subscription Start is empty."""
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


def money(v):
    """MRR, or None when the board carries no value. An absent MRR is a gap, and
    must never be silently read as zero — 12 accounts have none."""
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def disp_name(name):
    """Strip the '- LATAM' board marker; it is never part of a rendered name."""
    return LATAM_SUFFIX.sub("", re.sub(r"\s{2,}", " ", (name or "").strip())).strip()


def is_latam(r):
    return bool(LATAM_SUFFIX.search(re.sub(r"\s{2,}", " ", r.get("name") or "")))


def usd(v, dash="—"):
    return dash if v is None else "$" + format(int(round(v)), ",")


# ---------------------------------------------------------------------- derive

def derive(d):
    """Everything the page renders, computed from the verbatim snapshot."""
    rows = []
    for r in d["in_progress"]:
        rows.append(dict(
            r, disp=disp_name(r["name"]), latam=is_latam(r),
            aoe=checked(r.get("aoe_assigned")), days=days_open(r),
            oc=(r.get("oc") or "").strip() or None, mrr=money(r.get("mrr")),
            region=(r.get("region") or "").strip() or None,
        ))
    done = []
    for r in d["onboarded"]:
        done.append(dict(
            r, disp=disp_name(r["name"]), aoe=checked(r.get("aoe_assigned")),
            days=days_open(r), oc=(r.get("oc") or "").strip() or None,
            mrr=money(r.get("mrr")),
            ttv_outcome=(r.get("ttv_outcome") or "").strip(),
        ))

    stage_n = {s: sum(1 for r in rows if r["stage"] == s) for s in STAGE_ORDER}
    not_started = [r for r in rows if r["stage"] == "Not Started"]
    # anything that is not Not Started counts as in progress, including a stage
    # label this build has never seen — surfaced, never silently dropped
    in_progress = [r for r in rows if r["stage"] != "Not Started"]
    unknown_stages = sorted({r["stage"] for r in in_progress} - set(STAGE_ORDER))

    aoe_yes = [r for r in rows if r["aoe"]]
    aoe_no = [r for r in rows if not r["aoe"]]

    def mrr_sum(rs):
        return sum(r["mrr"] for r in rs if r["mrr"] is not None)

    def no_mrr(rs):
        return [r for r in rs if r["mrr"] is None]

    by_stage = []
    for s in ["Not Started"] + list(STAGE_ORDER):
        sub = [r for r in rows if r["stage"] == s]
        if not sub and s != "Risk":
            continue
        by_stage.append({"stage": s, "n": len(sub),
                         "yes": sum(1 for r in sub if r["aoe"]),
                         "mrr": mrr_sum(sub), "no_mrr": len(no_mrr(sub)),
                         "accts": sorted(sub, key=lambda r: (r["aoe"], r["disp"]))})

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
            "mrr": mrr_sum(sub), "no_mrr": len(no_mrr(sub)),
            "oldest": max(ages) if ages else None,
            "unassigned": oc == "Unassigned",
            "accts": sorted(sub, key=lambda r: (r["aoe"], -(r["days"] or -1), r["disp"])),
        })
    # busiest first, then worst coverage, then name — Unassigned always last
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
        "no_start": no_clock, "future_start": future,
        "no_oc": [r for r in rows if not r["oc"]],
        "no_region": [r for r in rows if not r["region"]],
        "no_products": [r for r in rows if not (r.get("products") or "").strip()],
        "no_mrr": no_mrr(rows),
        "zero_mrr": [r for r in rows if r["mrr"] == 0],
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
        "mrr_total": mrr_sum(rows), "mrr_aoe_no": mrr_sum(aoe_no),
        "by_stage": by_stage, "by_oc": by_oc,
        "ages": ages, "no_clock": no_clock, "future": future,
        "hygiene": hygiene, "risk_flagged": risk_flagged,
        "regions": sorted({r["region"] for r in rows if r["region"]}),
    }


# ------------------------------------------------------------------------- css
# Adobe Spectrum tokens, taken from ~/Documents/Adobe Branding/. Every colour is
# declared on the bare :root first, so nothing depends on a media query having
# matched; dark redefines only the token values, twice, so an explicit choice
# wins in either direction.
CSS = """
:root{
  color-scheme:light;
  /* Spectrum 2 gray ramp — light */
  --g50:#ffffff; --g75:#fdfdfd; --g100:#f8f8f8; --g200:#e6e6e6; --g300:#d5d5d5;
  --g400:#b1b1b1; --g500:#909090; --g600:#6d6d6d; --g700:#464646; --g800:#222222;
  --bg:#f8f8f8; --surface:#ffffff; --sunken:#f3f3f3; --raised:#ffffff;
  --line:#e6e6e6;            /* decorative hairline */
  --line-strong:#d5d5d5;
  --line-ui:#6d6d6d;         /* borders that identify a control — 5.17:1 */
  --ink:#222222;             /* 15.91:1 */
  --ink-2:#464646;           /* 9.44:1  */
  --ink-3:#6d6d6d;           /* 5.17:1  — the floor for text */
  --ink-disabled:#909090;    /* 3.19:1  — placeholder ONLY, never text */
  --accent:#3B63FB;          /* adobe.com CTA blue, 4.81:1 */
  --accent-strong:#274DEA;   /* 6.30:1 */
  --accent-wash:rgba(59,99,251,.09);
  --adobe-red:#EB1000;       /* identity mark only, exactly as Adobe uses it */
  --negative:#d31510; --negative-icon:#ea3829; --negative-wash:rgba(211,21,16,.09);
  --positive:#007a4d; --positive-icon:#15a46e; --positive-wash:rgba(0,122,77,.10);
  --notice:#b14c00;   --notice-icon:#e46f00;   --notice-wash:rgba(177,76,0,.10);
  --viz-1:#147af3; --viz-2:#e46f00; --viz-3:#15a46e; --viz-4:#d135c0;
  --viz-neutral:#909090;
  --focus:#147af3;
  --shadow-1:0 1px 3px rgba(0,0,0,.04);
  --shadow-2:0 4px 12px rgba(0,0,0,.08),0 2px 6px rgba(0,0,0,.04),0 0 2px rgba(0,0,0,.12);
  --sans:"Source Sans 3","Source Sans Pro",-apple-system,BlinkMacSystemFont,
         "Segoe UI",Roboto,Ubuntu,"Trebuchet MS","Lucida Grande",sans-serif;
  --mono:"Source Code Pro",Monaco,ui-monospace,SFMono-Regular,monospace;
  --r-sm:4px; --r-md:8px; --r-lg:16px;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    color-scheme:dark;
    /* Spectrum 2 gray ramp — darkest */
    --g50:#000000; --g75:#0e0e0e; --g100:#1d1d1d; --g200:#303030; --g300:#4b4b4b;
    --g400:#6a6a6a; --g500:#8d8d8d; --g600:#b0b0b0; --g700:#d0d0d0; --g800:#ebebeb;
    --bg:#0e0e0e; --surface:#1d1d1d; --sunken:#161616; --raised:#252525;
    --line:#303030; --line-strong:#4b4b4b; --line-ui:#8d8d8d;
    --ink:#ffffff; --ink-2:#d0d0d0; --ink-3:#b0b0b0; --ink-disabled:#6a6a6a;
    --accent:#5eaaf7; --accent-strong:#98cefd; --accent-wash:rgba(94,170,247,.14);
    --adobe-red:#ff816b;
    --negative:#ff816b; --negative-icon:#ff816b; --negative-wash:rgba(255,129,107,.14);
    --positive:#2fb880; --positive-icon:#2fb880; --positive-wash:rgba(47,184,128,.14);
    --notice:#ffa037;   --notice-icon:#ffa037;   --notice-wash:rgba(255,160,55,.14);
    --viz-1:#3892f3; --viz-2:#e46f00; --viz-3:#19a873; --viz-4:#d94ec4;
    --viz-neutral:#8d8d8d;
    --focus:#5eaaf7;
    --shadow-1:0 1px 3px rgba(0,0,0,.24);
    --shadow-2:0 4px 12px rgba(0,0,0,.34),0 2px 6px rgba(0,0,0,.18),0 0 2px rgba(0,0,0,.5);
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --g50:#000000; --g75:#0e0e0e; --g100:#1d1d1d; --g200:#303030; --g300:#4b4b4b;
  --g400:#6a6a6a; --g500:#8d8d8d; --g600:#b0b0b0; --g700:#d0d0d0; --g800:#ebebeb;
  --bg:#0e0e0e; --surface:#1d1d1d; --sunken:#161616; --raised:#252525;
  --line:#303030; --line-strong:#4b4b4b; --line-ui:#8d8d8d;
  --ink:#ffffff; --ink-2:#d0d0d0; --ink-3:#b0b0b0; --ink-disabled:#6a6a6a;
  --accent:#5eaaf7; --accent-strong:#98cefd; --accent-wash:rgba(94,170,247,.14);
  --adobe-red:#ff816b;
  --negative:#ff816b; --negative-icon:#ff816b; --negative-wash:rgba(255,129,107,.14);
  --positive:#2fb880; --positive-icon:#2fb880; --positive-wash:rgba(47,184,128,.14);
  --notice:#ffa037;   --notice-icon:#ffa037;   --notice-wash:rgba(255,160,55,.14);
  --viz-1:#3892f3; --viz-2:#e46f00; --viz-3:#19a873; --viz-4:#d94ec4;
  --viz-neutral:#8d8d8d;
  --focus:#5eaaf7;
  --shadow-1:0 1px 3px rgba(0,0,0,.24);
  --shadow-2:0 4px 12px rgba(0,0,0,.34),0 2px 6px rgba(0,0,0,.18),0 0 2px rgba(0,0,0,.5);
}

*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font:400 14px/1.5 var(--sans);-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px 72px}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px;border-radius:2px}

a.skip{position:absolute;left:-9999px;top:8px;z-index:20;background:var(--surface);
  color:var(--accent);border:1px solid var(--accent);border-radius:var(--r-sm);
  padding:10px 16px;font-weight:700;text-decoration:none}
a.skip:focus{left:24px}

/* ---------- header ---------- */
header{display:flex;gap:16px;align-items:center;padding:28px 0 20px}
.mark{flex:0 0 auto;width:48px;height:48px;border-radius:var(--r-md);
  background:var(--adobe-red);color:#fff;display:flex;align-items:center;
  justify-content:center;font:800 17px/1 var(--sans);letter-spacing:.02em}
:root[data-theme="dark"] .mark,
:root:not([data-theme="light"]) .mark{color:#1d1d1d}
@media (prefers-color-scheme:light){:root:not([data-theme="dark"]) .mark{color:#fff}}
.hd{min-width:0;flex:1}
h1{margin:0;font:800 28px/1.15 var(--sans);letter-spacing:-.01em;color:var(--ink);
   text-wrap:balance}
.sub{margin-top:5px;color:var(--ink-3);font:400 13px/1.5 var(--mono)}
.sub b{color:var(--ink-2);font-weight:600}

.stale{background:var(--notice-wash);border:1px solid var(--notice);
  border-radius:var(--r-md);padding:12px 16px;margin-bottom:20px;color:var(--ink-2)}
.stale b{display:block;color:var(--notice);font-weight:700;margin-bottom:2px}

/* ---------- tabs ---------- */
nav.tabs{position:sticky;top:0;z-index:10;display:flex;gap:2px;flex-wrap:wrap;
  background:var(--bg);border-bottom:1px solid var(--line-strong);
  margin-bottom:24px;padding-top:2px}
.tab{appearance:none;background:none;border:0;border-bottom:2px solid transparent;
  margin-bottom:-1px;padding:11px 16px;cursor:pointer;color:var(--ink-3);
  font:600 14px/1.3 var(--sans);white-space:nowrap;border-radius:var(--r-sm) var(--r-sm) 0 0}
.tab:hover{color:var(--ink);background:var(--accent-wash)}
.tab[aria-selected="true"]{color:var(--accent-strong);border-bottom-color:var(--accent);
  font-weight:700}
.tab .cnt{margin-left:7px;font:600 11px/1 var(--mono);color:var(--ink-3);
  background:var(--sunken);border:1px solid var(--line);border-radius:999px;
  padding:3px 7px;vertical-align:1px}
.tab[aria-selected="true"] .cnt{color:var(--accent-strong);background:var(--accent-wash);
  border-color:transparent}

.panel[hidden]{display:none}
.panel:focus{outline:none}
h2{margin:32px 0 12px;font:700 20px/1.25 var(--sans);color:var(--ink);letter-spacing:-.005em}
.panel > h2:first-child{margin-top:4px}
h3{margin:0 0 10px;font:700 15px/1.3 var(--sans);color:var(--ink)}
.lede{margin:0 0 20px;color:var(--ink-2);font-size:15px;line-height:1.6;max-width:70ch}
.eyebrow{font:700 11px/1 var(--sans);letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink-3);margin-bottom:8px}

/* ---------- KPI tiles ---------- */
.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin-bottom:8px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-md);
  padding:16px 18px;box-shadow:var(--shadow-1);min-width:0}
.kpi .v{font:800 30px/1.1 var(--sans);color:var(--ink);font-variant-numeric:tabular-nums;
  letter-spacing:-.02em}
.kpi .v small{font:700 16px/1 var(--sans);color:var(--ink-3);letter-spacing:0}
.kpi .l{margin-top:6px;font:700 11px/1.3 var(--sans);letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink-3)}
.kpi .s{margin-top:10px;padding-top:9px;border-top:1px solid var(--line);
  font:400 11px/1.45 var(--mono);color:var(--ink-3)}
.kpi.lead{border-color:var(--accent);box-shadow:var(--shadow-2)}
.kpi.lead .v{color:var(--accent-strong)}

/* ---------- cards, callouts, charts ---------- */
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-md);
  padding:18px;box-shadow:var(--shadow-1)}
.callout{background:var(--surface);border:1px solid var(--line);
  border-left:3px solid var(--accent);border-radius:var(--r-md);padding:14px 18px;
  color:var(--ink-2);font-size:14.5px;line-height:1.6;max-width:80ch}
.callout b{color:var(--ink)}
.callout.warn{border-left-color:var(--notice)}
.callout.crit{border-left-color:var(--negative)}
.callout .big{display:block;font:800 21px/1.2 var(--sans);color:var(--ink);
  margin-bottom:5px;letter-spacing:-.01em}

.chart{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-md);
  padding:20px 20px 14px;box-shadow:var(--shadow-1)}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.chart .cap{margin-top:14px;padding-top:11px;border-top:1px solid var(--line);
  color:var(--ink-3);font:400 12px/1.55 var(--sans)}
text{font:600 12px var(--sans);fill:var(--ink-2)}
text.nm{fill:var(--ink);font:700 13px var(--sans)}
text.val{fill:var(--ink-2);font-variant-numeric:tabular-nums}
text.zero{fill:var(--ink-3);font-weight:400}
.bar-g rect.bar{transition:opacity .12s ease}
.bar-g:hover rect.bar{opacity:.82}
.legend{display:flex;flex-wrap:wrap;gap:8px 20px;margin-top:14px;
  color:var(--ink-2);font:600 12px var(--sans)}
.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;
  margin-right:7px;vertical-align:-1px}

/* ---------- toolbar: search + chips ---------- */
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 14px}
.search{position:relative;flex:0 1 300px;min-width:200px}
.search input{width:100%;padding:8px 30px 8px 12px;font:400 14px var(--sans);
  color:var(--ink);background:var(--surface);border:1px solid var(--line-ui);
  border-radius:var(--r-sm)}
.search input::placeholder{color:var(--ink-disabled)}
.search .clr{position:absolute;right:4px;top:50%;transform:translateY(-50%);
  appearance:none;background:none;border:0;cursor:pointer;color:var(--ink-3);
  font:400 17px/1 var(--sans);padding:3px 7px;border-radius:var(--r-sm)}
.search .clr:hover{color:var(--ink);background:var(--sunken)}
.chip{appearance:none;cursor:pointer;background:var(--surface);color:var(--ink-2);
  border:1px solid var(--line-strong);border-radius:999px;padding:6px 13px;
  font:600 12.5px/1.2 var(--sans);white-space:nowrap}
.chip:hover{border-color:var(--ink-3);color:var(--ink)}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
:root[data-theme="dark"] .chip[aria-pressed="true"]{color:#0e0e0e}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]) .chip[aria-pressed="true"]{color:#0e0e0e}}
.chipset{display:flex;flex-wrap:wrap;gap:7px;align-items:center}
.chipset .lbl{font:700 11px/1 var(--sans);letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink-3);margin-right:2px}
.count{font:400 13px var(--mono);color:var(--ink-3);margin-left:auto;white-space:nowrap}
.count b{color:var(--ink);font-weight:700}

/* ---------- tables ---------- */
.tw{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-md);
  overflow-x:auto;box-shadow:var(--shadow-1)}
table{width:100%;border-collapse:collapse;font-size:13.5px;
  font-variant-numeric:tabular-nums}
caption{text-align:left;padding:14px 18px 0;font:700 15px/1.3 var(--sans);color:var(--ink)}
th{text-align:left;padding:11px 16px;font:700 11px/1.3 var(--sans);letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink-3);border-bottom:1px solid var(--line-strong);
  white-space:nowrap;background:var(--surface)}
td{padding:10px 16px;border-bottom:1px solid var(--line);color:var(--ink-2);
   vertical-align:middle}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover td{background:var(--sunken)}
td.nm{color:var(--ink);font-weight:600}
th.num,td.num{text-align:right}
tr.tot td{border-top:1px solid var(--line-strong);border-bottom:0;background:var(--sunken);
  color:var(--ink-2);font-weight:700}
th[aria-sort]{cursor:pointer;user-select:none}
th[aria-sort]:hover{color:var(--ink)}
th[aria-sort] .ar{opacity:0;margin-left:5px;font-size:10px}
th[aria-sort="ascending"] .ar,th[aria-sort="descending"] .ar{opacity:1;color:var(--accent)}
th[aria-sort="descending"] .ar{display:inline-block;transform:rotate(180deg)}
table a{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--line-strong)}
table a:hover{color:var(--accent-strong);border-bottom-color:var(--accent)}
tr[hidden]{display:none}

/* ---------- expandable account lists ---------- */
details.acc{border-bottom:1px solid var(--line)}
details.acc:last-of-type{border-bottom:0}
details.acc > summary{list-style:none;cursor:pointer;display:grid;
  grid-template-columns:1.6fr .7fr .7fr 1fr .9fr;gap:12px;align-items:center;
  padding:12px 16px;color:var(--ink-2);font-size:13.5px}
details.acc > summary::-webkit-details-marker{display:none}
details.acc > summary:hover{background:var(--sunken)}
details.acc > summary .nm{color:var(--ink);font-weight:600;display:flex;
  align-items:center;gap:9px;min-width:0}
details.acc > summary .tw2{flex:0 0 auto;width:15px;height:15px;color:var(--ink-3);
  transition:transform .15s ease}
details.acc[open] > summary .tw2{transform:rotate(90deg);color:var(--accent)}
details.acc[open] > summary{background:var(--accent-wash)}
details.acc .inner{padding:0 16px 16px;background:var(--sunken)}
details.acc .inner table{font-size:13px;background:var(--surface);
  border:1px solid var(--line);border-radius:var(--r-sm);overflow:hidden}
details.acc .inner th{padding:8px 12px;font-size:10px;background:var(--surface)}
details.acc .inner td{padding:7px 12px}
.acchead{display:grid;grid-template-columns:1.6fr .7fr .7fr 1fr .9fr;gap:12px;
  padding:10px 16px;border-bottom:1px solid var(--line-strong);
  font:700 11px/1.3 var(--sans);letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink-3)}

/* ---------- pills, rates ---------- */
.pill{display:inline-block;padding:3px 9px;border-radius:999px;border:1px solid;
  font:700 10.5px/1.4 var(--sans);letter-spacing:.04em;text-transform:uppercase;
  white-space:nowrap}
.pill.ok{color:var(--positive);border-color:var(--positive);background:var(--positive-wash)}
.pill.gap{color:var(--negative);border-color:var(--negative);background:var(--negative-wash)}
.pill.hyg{color:var(--notice);border-color:var(--notice);background:var(--notice-wash)}
.pill.na{color:var(--ink-3);border-color:var(--line-strong);background:var(--sunken)}
.stagedot{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:7px;
  vertical-align:-1px;flex:0 0 auto}

.rate{display:inline-flex;align-items:center;gap:9px;justify-content:flex-end;width:100%}
.rate .track{width:58px;height:6px;border-radius:3px;background:var(--g200);
  overflow:hidden;flex:0 0 auto}
:root[data-theme="dark"] .rate .track{background:var(--g300)}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]) .rate .track{background:var(--g300)}}
.rate .track i{display:block;height:100%;background:var(--accent);border-radius:3px}
.rate .track.full i{background:var(--positive-icon)}
.rate .track.none i{background:var(--negative-icon)}
.rate .pc{font:700 12.5px var(--mono);color:var(--ink-2);min-width:36px;text-align:right}

.grid2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;
  align-items:start}
.stack{display:flex;flex-direction:column;gap:16px}
.empty{padding:26px 18px;text-align:center;color:var(--ink-3);font-size:14px}
.sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;
  clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap;border:0}

footer{margin-top:48px;padding-top:20px;border-top:1px solid var(--line-strong);
  color:var(--ink-3);font-size:12.5px;line-height:1.7;max-width:88ch}
footer b{color:var(--ink-2)}
footer p{margin:0 0 12px}

/* ---------- responsive ---------- */
@media (max-width:1080px){
  .kpis{grid-template-columns:repeat(3,minmax(0,1fr))}
}
@media (max-width:860px){
  .grid2{grid-template-columns:minmax(0,1fr)}
  details.acc > summary,.acchead{grid-template-columns:1.4fr .8fr .8fr}
  details.acc > summary .h4,details.acc > summary .h5,
  .acchead .h4,.acchead .h5{display:none}
}
@media (max-width:640px){
  .wrap{padding:0 14px 48px}
  .kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  h1{font-size:22px}
  .kpi .v{font-size:25px}
  nav.tabs{gap:0}
  .tab{padding:10px 11px;font-size:13px}
  details.acc > summary,.acchead{grid-template-columns:1.5fr .9fr}
  details.acc > summary .h3c,.acchead .h3c{display:none}
  .count{margin-left:0;width:100%}
}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
}
@media (forced-colors:active){
  .kpi,.card,.callout,.chart,.tw,.chip,.tab,.pill,.search input{border:1px solid CanvasText}
  .tab[aria-selected="true"],.chip[aria-pressed="true"]{outline:2px solid Highlight}
  .rate .track i{background:Highlight}
}

/* ---------- print: no tabs, every panel on the page ---------- */
@media print{
  :root{color-scheme:light;
    --bg:#fff; --surface:#fff; --sunken:#fff; --raised:#fff;
    --line:#d5d5d5; --line-strong:#b1b1b1; --line-ui:#6d6d6d;
    --ink:#000; --ink-2:#333; --ink-3:#555;
    --shadow-1:none; --shadow-2:none}
  body{background:#fff}
  nav.tabs,.toolbar,a.skip{display:none!important}
  .panel[hidden]{display:block!important}
  .panel{break-before:page}
  .panel:first-of-type{break-before:auto}
  details.acc{break-inside:avoid}
  details.acc > .inner{display:block!important}
  .kpi,.card,.callout,.chart,.tw{box-shadow:none;border:1px solid #d5d5d5}
  h2{margin-top:18px}
  table a{border-bottom:0;color:#000}
}
@page{margin:1.4cm}
"""


# -------------------------------------------------------------------------- js
# Progressive enhancement only. Python has already rendered every row into the
# DOM; this layer shows, hides, sorts and counts. With JS off the page is still
# complete and readable — which is also what keeps it printable.
JS = """
(function(){
  "use strict";
  var $ = function(s, r){ return (r||document).querySelector(s); };
  var $$ = function(s, r){ return Array.prototype.slice.call((r||document).querySelectorAll(s)); };

  /* ---------------------------------------------------------------- tabs */
  var tabs = $$("nav.tabs .tab");
  var panels = tabs.map(function(t){ return document.getElementById(t.getAttribute("aria-controls")); });

  function setPanel(id, push){
    tabs.forEach(function(t, i){
      var on = t.getAttribute("aria-controls") === id;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
      if (panels[i]) panels[i].hidden = !on;
    });
    if (push !== false){
      if (location.hash !== "#" + id) history.replaceState(null, "", "#" + id);
      var p = document.getElementById(id);
      if (p){ p.focus({ preventScroll: true }); }
      window.scrollTo({ top: 0, behavior: "instant" in document.documentElement.style ? "instant" : "auto" });
    }
  }
  tabs.forEach(function(t){
    t.addEventListener("click", function(){ setPanel(t.getAttribute("aria-controls")); });
  });
  var nav = $("nav.tabs");
  if (nav) nav.addEventListener("keydown", function(e){
    var i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    var j = null;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") j = (i + 1) % tabs.length;
    if (e.key === "ArrowLeft"  || e.key === "ArrowUp")   j = (i - 1 + tabs.length) % tabs.length;
    if (e.key === "Home") j = 0;
    if (e.key === "End")  j = tabs.length - 1;
    if (j === null) return;
    e.preventDefault();
    tabs[j].focus();
    setPanel(tabs[j].getAttribute("aria-controls"));
  });
  addEventListener("hashchange", function(){
    var h = location.hash.slice(1);
    if (document.getElementById(h) && h.indexOf("panel-") === 0) setPanel(h, false);
  });
  (function(){
    var h = location.hash.slice(1);
    if (h && document.getElementById(h) && h.indexOf("panel-") === 0) setPanel(h, false);
  })();
  $$("a.jump").forEach(function(a){
    a.addEventListener("click", function(e){
      e.preventDefault();
      setPanel(a.getAttribute("href").slice(1));
    });
  });

  /* ------------------------------------------------------------ filtering */
  $$(".toolbar").forEach(function(bar){
    var table = document.getElementById(bar.getAttribute("data-controls"));
    if (!table) return;
    var input = $("input", bar);
    var clear = $(".clr", bar);
    var chips = $$(".chip", bar);
    var out = $(".count", bar);
    var noneRow = $("tr.nores", table);
    /* the empty-state row lives in the same tbody — it is never a result */
    var rows = $$("tbody tr", table).filter(function(t){ return !t.classList.contains("nores"); });
    var total = rows.length;

    function apply(){
      var q = (input && input.value || "").trim().toLowerCase();
      var active = {};
      chips.forEach(function(c){
        if (c.getAttribute("aria-pressed") !== "true") return;
        var k = c.getAttribute("data-filter");
        (active[k] = active[k] || []).push(c.getAttribute("data-value"));
      });
      var shown = 0;
      rows.forEach(function(tr){
        var ok = true;
        if (q && (tr.getAttribute("data-search") || "").indexOf(q) < 0) ok = false;
        if (ok) Object.keys(active).forEach(function(k){
          if (active[k].indexOf(tr.getAttribute("data-" + k)) < 0) ok = false;
        });
        tr.hidden = !ok;
        if (ok) shown++;
      });
      if (noneRow){ noneRow.hidden = shown !== 0; }
      if (clear) clear.hidden = !q;
      if (out){
        out.innerHTML = shown === total
          ? "<b>" + total + "</b> accounts"
          : "<b>" + shown + "</b> of " + total + " accounts";
      }
      var any = q || Object.keys(active).length;
      var reset = $(".reset", bar);
      if (reset) reset.hidden = !any;
    }
    if (input) input.addEventListener("input", apply);
    if (clear) clear.addEventListener("click", function(){
      input.value = ""; apply(); input.focus();
    });
    chips.forEach(function(c){
      c.addEventListener("click", function(){
        c.setAttribute("aria-pressed", c.getAttribute("aria-pressed") === "true" ? "false" : "true");
        apply();
      });
    });
    var reset = $(".reset", bar);
    if (reset) reset.addEventListener("click", function(){
      if (input) input.value = "";
      chips.forEach(function(c){ c.setAttribute("aria-pressed", "false"); });
      apply();
      if (input) input.focus();
    });
    apply();
  });

  /* -------------------------------------------------------------- sorting */
  $$("table").forEach(function(table){
    var heads = $$("th[aria-sort]", table);
    if (!heads.length) return;
    var body = $("tbody", table);
    if (!body) return;

    function cellVal(tr, idx, type){
      var td = tr.children[idx];
      if (!td) return type === "num" ? -Infinity : "";
      var raw = td.getAttribute("data-v");
      if (raw === null) raw = td.textContent;
      raw = String(raw).trim();
      if (type !== "num") return raw.toLowerCase();
      if (raw === "" || raw === "—") return -Infinity;
      var n = parseFloat(raw.replace(/[^0-9.\\-]/g, ""));
      return isNaN(n) ? -Infinity : n;
    }
    heads.forEach(function(th){
      var idx = Array.prototype.indexOf.call(th.parentNode.children, th);
      var type = th.getAttribute("data-type") || "text";
      function sort(){
        var cur = th.getAttribute("aria-sort");
        var dir = cur === "ascending" ? -1 : 1;
        heads.forEach(function(o){ o.setAttribute("aria-sort", "none"); });
        th.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
        var trs = $$("tr", body).filter(function(t){ return !t.classList.contains("nores"); });
        trs.map(function(tr, i){ return [tr, i]; })
           .sort(function(a, b){
             var x = cellVal(a[0], idx, type), y = cellVal(b[0], idx, type);
             if (x < y) return -1 * dir;
             if (x > y) return  1 * dir;
             return a[1] - b[1];                    /* stable */
           })
           .forEach(function(p){ body.appendChild(p[0]); });
        var nres = $("tr.nores", body);
        if (nres) body.appendChild(nres);
      }
      th.addEventListener("click", sort);
      th.tabIndex = 0;
      th.addEventListener("keydown", function(e){
        if (e.key === "Enter" || e.key === " "){ e.preventDefault(); sort(); }
      });
    });
  });
})();
"""


# ---------------------------------------------------------------------- charts

def chart_stages(c):
    """Horizontal bars, one per in-progress stage, each directly labelled with
    its count and its MRR. Not Started is excluded by design and carried as its
    own KPI. Direct labels are also the secondary encoding the categorical hues
    need, so nothing depends on colour alone."""
    mrr = {s["stage"]: s for s in c["by_stage"]}
    rows = [(s, c["stage_n"].get(s, 0), mrr.get(s, {}).get("mrr", 0)) for s in STAGE_ORDER]
    mx = max([n for _, n, _ in rows] + [1])
    W, LAB, VW, BH, GAP = 820, 118, 232, 30, 12
    plot = W - LAB - VW
    H = len(rows) * (BH + GAP) + 4
    aria = "Accounts at each in-progress stage: " + ", ".join(
        "%s %d" % (s, n) for s, n, _ in rows)
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (W, H, _ea(aria))]
    for i, (s, n, m) in enumerate(rows):
        y = i * (BH + GAP) + 2
        icon = STAGE_ICON.get(s, "")
        p.append('<text class="nm" x="0" y="%d">%s</text>'
                 % (y + BH - 9, _e((icon + " " + s).strip())))
        if n:
            w = max(7, round(plot * n / mx))
            p.append('<g class="bar-g"><rect class="bar" x="%d" y="%d" width="%d" '
                     'height="%d" rx="4" fill="var(%s)"><title>%s</title></rect></g>'
                     % (LAB, y, w, BH, STAGE_VAR[s],
                        _e("%s — %d accounts, %s MRR" % (s, n, usd(m, "no MRR")))))
            p.append('<text class="val" x="%d" y="%d">%d account%s · %s</text>'
                     % (LAB + w + 12, y + BH - 9, n, "" if n == 1 else "s",
                        _e(usd(m, "no MRR on file"))))
        else:
            p.append('<rect x="%d" y="%d" width="5" height="%d" rx="2" '
                     'fill="var(--line-strong)"/>' % (LAB, y, BH))
            p.append('<text class="zero" x="%d" y="%d">no accounts at this stage</text>'
                     % (LAB + 16, y + BH - 9))
    p.append("</svg>")
    leg = "".join('<span><i style="background:var(%s)"></i>%s</span>'
                  % (STAGE_VAR[s], _e((STAGE_ICON.get(s, "") + " " + s).strip()))
                  for s, _, _ in rows)
    return ('<div class="chart">' + "".join(p) + '<div class="legend">' + leg + "</div>"
            '<div class="cap">The %d accounts already moving, and the revenue behind each '
            'stage. Not Started (%d) is counted separately — it answers a different '
            'question. Risk is a board stage, not a judgement this page makes.</div></div>'
            % (len(c["in_progress"]), len(c["not_started"])))


def chart_aging(c):
    """Neutral aging distribution: one series, no target line, no zones. ABV
    accounts run on their own program clock, so nothing here is scored."""
    rows = [(lab, c["ages"][lab]) for _, _, lab in AGE_BUCKETS]
    extra = [("No start date yet", len(c["no_clock"])),
             ("Start date in the future", len(c["future"]))]
    mx = max([n for _, n in rows + extra] + [1])
    W, LAB, VW, BH, GAP = 820, 196, 90, 26, 11
    plot = W - LAB - VW
    SEP = 20
    H = (len(rows) + len(extra)) * (BH + GAP) + SEP + 6
    aria = "Days open across the ABV pipeline: " + ", ".join(
        "%s %d" % (l, n) for l, n in rows + extra)
    p = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (W, H, _ea(aria))]
    y = 2
    for lab, n in rows:
        p.append('<text class="nm" x="0" y="%d">%s</text>' % (y + BH - 8, _e(lab)))
        if n:
            w = max(6, round(plot * n / mx))
            p.append('<g class="bar-g"><rect class="bar" x="%d" y="%d" width="%d" height="%d" '
                     'rx="4" fill="var(--accent)"><title>%s</title></rect></g>'
                     % (LAB, y, w, BH, _e("%s — %d accounts" % (lab, n))))
            p.append('<text class="val" x="%d" y="%d">%d</text>' % (LAB + w + 12, y + BH - 8, n))
        else:
            p.append('<rect x="%d" y="%d" width="5" height="%d" rx="2" '
                     'fill="var(--line-strong)"/>' % (LAB, y, BH))
            p.append('<text class="zero" x="%d" y="%d">0</text>' % (LAB + 16, y + BH - 8))
        y += BH + GAP
    # the two clockless categories sit below a rule, drawn hollow, so they read
    # as "not on this scale" rather than as a longer or shorter duration
    p.append('<line x1="0" y1="%d" x2="%d" y2="%d" stroke="var(--line-strong)" '
             'stroke-width="1"/>' % (y + SEP // 2 - 5, W, y + SEP // 2 - 5))
    y += SEP
    for lab, n in extra:
        p.append('<text class="nm" x="0" y="%d" style="fill:var(--ink-3)">%s</text>'
                 % (y + BH - 8, _e(lab)))
        w = max(6, round(plot * n / mx)) if n else 5
        p.append('<rect x="%d" y="%d" width="%d" height="%d" rx="4" fill="none" '
                 'stroke="var(--ink-3)" stroke-width="1.5" stroke-dasharray="3 3">'
                 '<title>%s</title></rect>'
                 % (LAB, y, w, BH, _e("%s — %d accounts" % (lab, n))))
        p.append('<text class="val" x="%d" y="%d">%d</text>' % (LAB + w + 12, y + BH - 8, n))
        y += BH + GAP
    p.append("</svg>")
    tot = sum(n for _, n in rows) + sum(n for _, n in extra)
    return ('<div class="chart">' + "".join(p) +
            '<div class="cap">Board Days Open, counted from Subscription Start. All '
            'categories sum to %d. The two dashed rows have no clock running, so they are '
            'not placed on the day scale at all.</div></div>' % tot)


# ------------------------------------------------------------------ components

def kpi(v, label, src, sub=None, lead=False):
    small = ("<small>%s</small>" % _e(sub)) if sub else ""
    return ('<div class="kpi%s"><div class="v">%s%s</div><div class="l">%s</div>'
            '<div class="s">%s</div></div>'
            % (" lead" if lead else "", _e(v), small, _e(label), _e(src)))


def rate_cell(yes, n, cell=True):
    pc = round(100.0 * yes / n) if n else 0
    cls = " full" if (n and yes == n) else (" none" if yes == 0 else "")
    inner = ('<span class="rate"><span class="track%s"><i style="width:%d%%"></i></span>'
             '<span class="pc">%d%%</span></span>' % (cls, pc, pc))
    return ('<td class="num" data-v="%d">%s</td>' % (pc, inner)) if cell else inner


def stage_dot(stage):
    var = STAGE_VAR.get(stage, "--viz-neutral")
    return '<span class="stagedot" style="background:var(%s)" aria-hidden="true"></span>' % var


TWISTY = ('<svg class="tw2" viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
          '<path d="M6 3.5 L11 8 L6 12.5" fill="none" stroke="currentColor" '
          'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def acct_subtable(accts, show_stage=True):
    """The account list revealed when a row is expanded."""
    h = ['<div class="inner"><table><thead><tr><th scope="col">Account</th>']
    if show_stage:
        h.append('<th scope="col">Stage</th>')
    h.append('<th scope="col">Consultant</th><th scope="col">AOE</th>'
             '<th scope="col" class="num">Days open</th>'
             '<th scope="col" class="num">MRR</th></tr></thead><tbody>')
    for r in accts:
        h.append('<tr><td class="nm"><a href="%s">%s</a></td>' % (_ea(r["url"]), _e(r["disp"])))
        if show_stage:
            h.append("<td>%s%s</td>" % (stage_dot(r["stage"]), _e(r["stage"])))
        aoe = ('<span class="pill ok">yes</span>' if r["aoe"]
               else '<span class="pill gap">not assigned</span>')
        h.append('<td>%s</td><td>%s</td><td class="num">%s</td><td class="num">%s</td></tr>'
                 % (_e(r["oc"] or "Unassigned"), aoe,
                    "—" if r["days"] is None else r["days"],
                    _e(usd(r["mrr"]))))
    h.append("</tbody></table></div>")
    return "".join(h)


def acc_row(summary_cells, accts, show_stage=True):
    """One expandable row: a five-column summary that opens onto its accounts."""
    cells = "".join(summary_cells)
    return ('<details class="acc"><summary>%s</summary>%s</details>'
            % (cells, acct_subtable(accts, show_stage)))


# ------------------------------------------------------------------------ page

def _tabs_bar(counts):
    h = ['<nav class="tabs" role="tablist" aria-label="Dashboard sections">']
    for i, (key, label) in enumerate(TABS):
        cnt = counts.get(key)
        badge = ('<span class="cnt">%s</span>' % _e(cnt)) if cnt is not None else ""
        h.append('<button class="tab" type="button" role="tab" id="tab-%s" '
                 'aria-controls="panel-%s" aria-selected="%s" tabindex="%d">%s%s</button>'
                 % (key, key, "true" if i == 0 else "false", 0 if i == 0 else -1,
                    label, badge))
    h.append("</nav>")
    return "".join(h)


def _panel(key, first=False):
    return ('<section class="panel" id="panel-%s" role="tabpanel" '
            'aria-labelledby="tab-%s" tabindex="-1"%s>' % (key, key, "" if first else " hidden"))


def render(c):
    A = []
    a = A.append
    total, yes, no = c["total"], len(c["aoe_yes"]), len(c["aoe_no"])
    pc = round(100.0 * yes / total) if total else 0
    ns_miss = sum(1 for r in c["aoe_no"] if r["stage"] == "Not Started")

    a('<a class="skip" href="#panel-overview">Skip to dashboard</a>')
    a('<div class="wrap">')
    a('<header><div class="mark" aria-hidden="true">ABV</div><div class="hd">'
      '<h1>ABV OB In Progress</h1>'
      '<div class="sub">Beth King · Daniel Angol · <b>%s</b> · generated %s</div>'
      '</div></header>'
      % (_e(c["board"]["name"]), _e(et_stamp(c["generated_at_utc"]))))

    if c["age_h"] > MAX_AGE_HOURS:
        a('<div class="stale" role="status"><b>This page has not refreshed</b>'
          'The last successful pull was %.0f hours ago (%s). The scheduled weekday rebuild '
          'has not run or could not publish, so these figures are from that earlier pull — '
          'not from the board as it stands now.</div>'
          % (c["age_h"], _e(et_stamp(c["generated_at_utc"]))))

    a(_tabs_bar({"aoe": no, "team": len(c["by_oc"])}))
    a("<main>")

    # ============================================================ OVERVIEW
    a(_panel("overview", first=True))
    a('<p class="lede">Every ABV account the onboarding team is carrying, across all %d '
      'consultants — read straight off the board group “%s”, with no person filter.</p>'
      % (len(c["by_oc"]) - (1 if any(o["unassigned"] for o in c["by_oc"]) else 0),
         _e(c["groups"]["in_progress"]["title"])))

    a('<div class="kpis">')
    a(kpi(total, "In the ABV pipeline", "board group %s, live count"
          % c["groups"]["in_progress"]["id"]))
    a(kpi(len(c["not_started"]), "Not Started", "Stage = Not Started (color_mkyrdx3)"))
    a(kpi(len(c["in_progress"]), "In progress", "every stage except Not Started"))
    a(kpi(yes, "AOE Assigned", "AOE Assigned ticked (boolean_mm71c8h0)",
          sub=" / %d" % total))
    a(kpi(usd(c["mrr_total"]), "Pipeline MRR",
          "sum of MRR (numeric_mkyr2fx) over %d accounts" % (total - len(c["hygiene"]["no_mrr"])),
          lead=True))
    a("</div>")

    a('<h2>What stands out today</h2><div class="stack">')
    a('<div class="callout crit"><span class="big">%s sits behind the %d accounts with no '
      'AOE assigned.</span>%s</div>'
      % (_e(usd(c["mrr_aoe_no"])), no,
         _e("%d of those %d are still in Not Started, so the gap is concentrated at the front "
            "of the pipeline — before onboarding has begun." % (ns_miss, no) if ns_miss and no
            else "They are spread across the active stages rather than concentrated in one place."
            if no else "Every account on the board has one.")))
    nm = len(c["hygiene"]["no_mrr"])
    zm = len(c["hygiene"]["zero_mrr"])
    if nm or zm:
        a('<div class="callout warn"><span class="big">%d of %d accounts carry no usable '
          'revenue figure.</span>%d have no MRR value at all and %d are set to exactly $0, so '
          'the %s pipeline total is a floor, not a full picture.</div>'
          % (nm + zm, total, nm, zm, _e(usd(c["mrr_total"]))))
    if c["no_clock"]:
        a('<div class="callout"><span class="big">%d accounts have no clock running.</span>'
          'Their Subscription Start is empty, so the board reports no age for them at all. '
          'They are shown as their own category throughout, never as day zero.</div>'
          % len(c["no_clock"]))
    a("</div>")

    if c["unknown_stages"]:
        a('<div class="callout warn" style="margin-top:16px"><b>New stage label on the '
          'board.</b> %s — counted as in progress and shown in every table, but this page '
          'has no colour assigned to it yet.</div>' % _e(", ".join(c["unknown_stages"])))

    a('<h2>Where the in-progress work sits</h2>')
    a(chart_stages(c))

    if c["risk_flagged"]:
        a('<h2>Risk flags</h2><div class="tw"><table>'
          '<thead><tr><th scope="col">Account</th><th scope="col">Status</th>'
          '<th scope="col">Type</th><th scope="col">Stage</th>'
          '<th scope="col">Consultant</th></tr></thead><tbody>')
        for r in c["risk_flagged"]:
            a('<tr><td class="nm"><a href="%s">%s</a></td>'
              '<td><span class="pill gap">⚠ %s</span></td><td>%s</td><td>%s</td><td>%s</td></tr>'
              % (_ea(r["url"]), _e(r["disp"]), _e(r["risk_status"]),
                 _e(r.get("risk_type") or "—"), _e(r.get("risk_stage") or "—"),
                 _e(r["oc"] or "Unassigned")))
        a("</tbody></table></div>")
    a("</section>")

    # ================================================================= AOE
    a(_panel("aoe"))
    a('<h2>AOE Assigned — %d of %d accounts (%d%%)</h2>' % (yes, total, pc))
    a('<p class="lede">An AOE is the agreed outcome an account is onboarding toward. '
      'Where one is missing, there is no shared definition of what success looks like.</p>')
    a('<div class="callout crit"><span class="big">%s across %d accounts has no AOE '
      'assigned.</span>%s</div>'
      % (_e(usd(c["mrr_aoe_no"])), no,
         _e("%d of them sit in Not Started — the cheapest place to fix this, and the "
            "one where it matters most." % ns_miss if ns_miss else
            "They are spread across the active stages.")))

    a('<h2>By stage</h2>')
    a('<p class="lede">Open any stage to see the accounts behind it.</p>')
    a('<div class="tw"><div class="acchead"><span>Stage</span>'
      '<span class="num h3c">Assigned</span><span class="num h3c">Total</span>'
      '<span class="h4">Coverage</span><span class="num h5">MRR</span></div>')
    for s in c["by_stage"]:
        st = s["stage"]
        label = (STAGE_ICON.get(st, "") + " " + st).strip()
        if not s["n"]:
            a('<div class="acchead" style="border-bottom:1px solid var(--line);'
              'text-transform:none;letter-spacing:0;font-weight:400;color:var(--ink-3)">'
              '<span>%s%s</span><span class="num h3c">—</span><span class="num h3c">0</span>'
              '<span class="h4"><span class="pill na">none</span></span>'
              '<span class="num h5">—</span></div>' % (stage_dot(st), _e(label)))
            continue
        a(acc_row([
            '<span class="nm">%s%s%s</span>' % (TWISTY, stage_dot(st), _e(label)),
            '<span class="num h3c">%d</span>' % s["yes"],
            '<span class="num h3c">%d</span>' % s["n"],
            '<span class="h4">%s</span>' % rate_cell(s["yes"], s["n"], cell=False),
            '<span class="num h5">%s</span>' % _e(usd(s["mrr"])),
        ], s["accts"], show_stage=False))
    a('<div class="acchead" style="border-bottom:0;border-top:1px solid var(--line-strong);'
      'background:var(--sunken)"><span>All stages</span>'
      '<span class="num h3c">%d</span><span class="num h3c">%d</span>'
      '<span class="h4">%d%%</span><span class="num h5">%s</span></div></div>'
      % (yes, total, pc, _e(usd(c["mrr_total"]))))

    # the flat worklist — the actionable half
    a('<h2>Not assigned — the worklist</h2>')
    a('<p class="lede">The %d accounts to chase. Search by account or consultant, filter by '
      'stage or region, and sort any column.</p>' % no)
    stages_present = [s for s in (["Not Started"] + list(STAGE_ORDER))
                      if any(r["stage"] == s for r in c["aoe_no"])]
    a('<div class="toolbar" data-controls="aoe-list">')
    a('<div class="search"><label class="sr" for="aoe-q">Search accounts by name or '
      'consultant</label>'
      '<input id="aoe-q" type="search" placeholder="Search account or consultant…" '
      'autocomplete="off"><button class="clr" type="button" hidden '
      'aria-label="Clear search">&times;</button></div>')
    a('<div class="chipset"><span class="lbl">Stage</span>')
    for s in stages_present:
        a('<button class="chip" type="button" data-filter="stage" data-value="%s" '
          'aria-pressed="false">%s</button>' % (_ea(s), _e(s)))
    a("</div>")
    if c["regions"]:
        a('<div class="chipset"><span class="lbl">Region</span>')
        for rg in c["regions"]:
            a('<button class="chip" type="button" data-filter="region" data-value="%s" '
              'aria-pressed="false">%s</button>' % (_ea(rg), _e(rg)))
        a("</div>")
    a('<button class="chip reset" type="button" hidden>Clear all</button>')
    a('<p class="count" role="status" aria-live="polite"></p>')
    a("</div>")

    a('<div class="tw"><table id="aoe-list">'
      '<caption class="sr">Accounts with no AOE assigned</caption><thead><tr>'
      '<th scope="col" aria-sort="none" data-type="text">Account<span class="ar">▲</span></th>'
      '<th scope="col" aria-sort="none" data-type="text">Stage<span class="ar">▲</span></th>'
      '<th scope="col" aria-sort="none" data-type="text">Consultant<span class="ar">▲</span></th>'
      '<th scope="col" aria-sort="none" data-type="text">Region<span class="ar">▲</span></th>'
      '<th scope="col" class="num" aria-sort="none" data-type="num">Days open<span class="ar">▲</span></th>'
      '<th scope="col" class="num" aria-sort="none" data-type="num">MRR<span class="ar">▲</span></th>'
      '</tr></thead><tbody>')
    order = {"Not Started": 0}
    for i, s in enumerate(STAGE_ORDER):
        order[s] = i + 1
    for r in sorted(c["aoe_no"], key=lambda r: (order.get(r["stage"], 9),
                                                -(r["days"] if r["days"] is not None else -1),
                                                r["disp"])):
        srch = " ".join(x for x in (r["disp"], r["oc"] or "Unassigned", r["stage"],
                                    r["region"] or "") if x).lower()
        a('<tr data-search="%s" data-stage="%s" data-region="%s">'
          '<td class="nm"><a href="%s">%s</a></td>'
          '<td data-v="%s">%s%s</td><td>%s</td><td>%s</td>'
          '<td class="num" data-v="%s">%s</td><td class="num" data-v="%s">%s</td></tr>'
          % (_ea(srch), _ea(r["stage"]), _ea(r["region"] or ""),
             _ea(r["url"]), _e(r["disp"]),
             _ea(r["stage"]), stage_dot(r["stage"]), _e(r["stage"]),
             _e(r["oc"] or "Unassigned"), _e(r["region"] or "—"),
             "" if r["days"] is None else r["days"],
             "—" if r["days"] is None else r["days"],
             "" if r["mrr"] is None else int(r["mrr"]), _e(usd(r["mrr"]))))
    a('<tr class="nores" hidden><td colspan="6" class="empty">No accounts match those '
      'filters.</td></tr>')
    a("</tbody></table></div>")
    a("</section>")

    # ================================================================ TEAM
    a(_panel("team"))
    a('<h2>Consultant load</h2>')
    a('<p class="lede">%d consultants carrying %d accounts. Open any row to see whose they '
      'are.</p>' % (len(c["by_oc"]) - (1 if any(o["unassigned"] for o in c["by_oc"]) else 0),
                    total))
    a('<div class="tw"><div class="acchead"><span>Consultant</span>'
      '<span class="num h3c">Accounts</span><span class="num h3c">In progress</span>'
      '<span class="h4">AOE coverage</span><span class="num h5">MRR</span></div>')
    for o in c["by_oc"]:
        nm2 = ('<span class="pill na">%s</span>' % _e(o["oc"])) if o["unassigned"] else _e(o["oc"])
        old = "—" if o["oldest"] is None else "%dd oldest" % o["oldest"]
        a(acc_row([
            '<span class="nm">%s%s</span>' % (TWISTY, nm2),
            '<span class="num h3c">%d</span>' % o["n"],
            '<span class="num h3c">%d</span>' % o["in_progress"],
            '<span class="h4">%s</span>' % rate_cell(o["yes"], o["n"], cell=False),
            '<span class="num h5">%s <span style="color:var(--ink-3);font-size:11px">· %s'
            '</span></span>' % (_e(usd(o["mrr"])), _e(old)),
        ], o["accts"], show_stage=True))
    a('<div class="acchead" style="border-bottom:0;border-top:1px solid var(--line-strong);'
      'background:var(--sunken)"><span>Total</span><span class="num h3c">%d</span>'
      '<span class="num h3c">%d</span><span class="h4">%d%%</span>'
      '<span class="num h5">%s</span></div></div>'
      % (total, len(c["in_progress"]), pc, _e(usd(c["mrr_total"]))))
    a('<div class="callout" style="margin-top:16px"><b>Oldest</b> is the highest Days Open in '
      'that consultant’s ABV book. Accounts with no Subscription Start have no clock and are '
      'left out of it. <b>In progress</b> excludes Not Started.</div>')
    a("</section>")

    # =============================================================== AGING
    a(_panel("aging"))
    a('<h2>How long these have been open</h2>')
    a('<div class="callout"><span class="big">These accounts run on the ABV program '
      'clock.</span>The onboarding board’s day-count target is written for standard '
      'onboarding and does not apply to them, so the buckets below are neutral — no target '
      'line, no pass or fail, nothing scored good or bad. Read them as distribution, not '
      'performance.</div>')
    a('<div style="margin-top:16px">' + chart_aging(c) + "</div>")
    if c["no_clock"] or c["future"]:
        a('<h2>The accounts with no clock</h2><div class="grid2">')
        for title, rows_, why in (
                ("No start date yet", c["no_clock"],
                 "Subscription Start is empty, so the board reports no age at all."),
                ("Start date in the future", c["future"],
                 "Subscription Start is later than today, so Days Open is negative.")):
            if not rows_:
                continue
            a('<div class="tw"><table><caption>%s <span style="font-weight:400;'
              'color:var(--ink-3)">— %d</span></caption>'
              '<thead><tr><th scope="col">Account</th><th scope="col">Stage</th>'
              '<th scope="col">Consultant</th></tr></thead><tbody>' % (_e(title), len(rows_)))
            for r in sorted(rows_, key=lambda r: r["disp"]):
                a('<tr><td class="nm"><a href="%s">%s</a></td><td>%s%s</td><td>%s</td></tr>'
                  % (_ea(r["url"]), _e(r["disp"]), stage_dot(r["stage"]), _e(r["stage"]),
                     _e(r["oc"] or "Unassigned")))
            a('</tbody></table><p style="padding:0 18px 16px;margin:10px 0 0;'
              'color:var(--ink-3);font-size:12.5px">%s</p></div>' % _e(why))
        a("</div>")
    a("</section>")

    # ================================================== COMPLETED & DATA
    a(_panel("data"))
    a('<h2>ABV Onboarded</h2>')
    a('<div class="tw"><table><thead><tr><th scope="col">Account</th>'
      '<th scope="col">Consultant</th><th scope="col" class="num">Days open</th>'
      '<th scope="col">Onboarding End Date</th><th scope="col" class="num">MRR</th>'
      '</tr></thead><tbody>')
    for r in sorted(c["done"], key=lambda r: -(r["days"] or 0)):
        end = r.get("end_date") or ""
        cell = _e(end) if end else '<span class="pill hyg">missing</span>'
        a('<tr><td class="nm"><a href="%s">%s</a></td><td>%s</td>'
          '<td class="num">%s</td><td>%s</td><td class="num">%s</td></tr>'
          % (_ea(r["url"]), _e(r["disp"]), _e(r["oc"] or "Unassigned"),
             _e("—" if r["days"] is None else r["days"]), cell, _e(usd(r["mrr"]))))
    a("</tbody></table></div>")
    noend = [r for r in c["done"] if not (r.get("end_date") or "")]
    if noend:
        a('<div class="callout warn" style="margin-top:16px"><span class="big">No cycle time '
          'can be read from this group.</span>%d of the %d onboarded accounts have no '
          'Onboarding End Date, so their Days Open is still counting (%s) and the board’s TTV '
          'Outcome column stays blank. Treat this as board hygiene, not throughput.</div>'
          % (len(noend), len(c["done"]),
             _e(", ".join("%s %dd" % (r["disp"], r["days"])
                          for r in noend if r["days"] is not None))))

    h = c["hygiene"]
    a('<h2>Board data gaps</h2>')
    a('<p class="lede">Everything the board is missing for the %d in-progress accounts. '
      'Suggest-only — nothing here is written back to Monday.</p>' % total)
    a('<div class="tw"><table><thead><tr><th scope="col">Gap</th>'
      '<th scope="col" class="num">Accounts</th><th scope="col">Which</th>'
      '</tr></thead><tbody>')
    for label, rows_ in (("No Subscription Start (no clock)", h["no_start"]),
                         ("Start date in the future", h["future_start"]),
                         ("No MRR value", h["no_mrr"]),
                         ("MRR set to exactly $0", h["zero_mrr"]),
                         ("No onboarding consultant", h["no_oc"]),
                         ("No Region", h["no_region"]),
                         ("No Products Purchased", h["no_products"])):
        if not rows_:
            a('<tr><td class="nm">%s</td><td class="num">'
              '<span class="pill ok">clear</span></td><td>—</td></tr>' % _e(label))
            continue
        names = ", ".join(r["disp"] for r in sorted(rows_, key=lambda r: r["disp"]))
        a('<tr><td class="nm">%s</td><td class="num"><span class="pill hyg">%d</span></td>'
          '<td style="font-size:12.5px;color:var(--ink-3)">%s</td></tr>'
          % (_e(label), len(rows_), _e(names)))
    a("</tbody></table></div>")
    a("</section>")

    a("</main>")

    a('<footer>'
      '<p><b>Where these numbers come from.</b> Two reads of board %s — group %s (%d '
      'accounts) and group %s (%d accounts) — with no person filter, so this is the whole '
      'team’s ABV book. Stage, AOE Assigned, consultant, dates, MRR and Days Open are copied '
      'from the board columns; nothing here is authored by hand and nothing is written back.</p>'
      '<p><b>Two things worth knowing.</b> ABV accounts are identified by board group, not by '
      'account name — most are named plainly (Colgate, Asus, Kohler), so a name-based rule '
      'would miss almost all of them. And Days Open counts from Subscription Start, so the %d '
      'accounts without one show no age at all rather than a zero.</p>'
      '<p><b>Design.</b> Adobe Spectrum tokens, with Source Sans 3 standing in for Adobe '
      'Clean, which is licensed and cannot be loaded here. Every colour pair on this page was '
      'checked to WCAG AA in both light and dark.</p>'
      '<p>Rebuilt each weekday morning. If a run fails, a banner appears at the top of this '
      'page — no banner means these figures are current.</p>'
      '</footer>'
      % (_e(c["board"]["id"]), _e(c["groups"]["in_progress"]["id"]), total,
         _e(c["groups"]["onboarded"]["id"]), len(c["done"]), len(c["no_clock"])))
    a("</div>")
    return "\n".join(A)


def et_stamp(utc):
    """UTC ISO -> a readable America/New_York stamp without a tz dependency: ET
    is UTC-4 between the second Sunday in March and the first Sunday in
    November, UTC-5 otherwise."""
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
        'family=Source+Sans+3:wght@400;600;700;800&'
        'family=Source+Code+Pro:wght@400;600&display=swap">\n')

NOSCRIPT = ("<noscript><style>"
            ".panel[hidden]{display:block!important}"
            "nav.tabs,.toolbar{display:none!important}"
            ".panel{border-top:1px solid var(--line-strong);padding-top:8px;margin-top:28px}"
            ".panel:first-of-type{border-top:0;margin-top:0}"
            "</style></noscript>\n")


# ------------------------------------------------------------ privacy gate

def privacy_check(d, page):
    """This page is manager-facing and gets forwarded. It carries account names,
    stages, counts and MRR — never contact details. The snapshot should contain
    none, so the gate is structural on both sides: refuse if a contact-shaped
    column ever joins the snapshot, and refuse if anything email-shaped reaches
    the rendered bytes."""
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
    page = (HEAD + "<style>%s</style>\n" % CSS + NOSCRIPT + render(c)
            + "\n<script>" + JS + "</script>\n")
    privacy_check(d, page)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write("<!DOCTYPE html>\n<html lang='en'>\n" + page + "</html>\n")
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
    print("   %d in pipeline · %d Not Started · %d in progress · AOE %d/%d · MRR %s"
          % (c["total"], len(c["not_started"]), len(c["in_progress"]),
             len(c["aoe_yes"]), c["total"], usd(c["mrr_total"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
