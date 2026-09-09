# ABV OB In Progress

A daily, manager-facing read on the **whole onboarding team's** ABV book — built for
Beth King and Daniel Angol, who were asked for a daily pipeline read.

**Live page:** https://claude.ai/code/artifact/0d2649df-3387-4b0b-bfbe-b3410a461b43

This is deliberately *not* the [FY26 Onboarding Command Center](https://claude.ai/code/artifact/73bae801-d13e-4a48-b879-034fb2b2f132).
That page is person-filtered to Ricardo's own accounts. This one has **no person filter** —
it is every ABV account across every consultant, which is the whole point.

## What's on it

Five tabbed sections, hash-linked so you can send someone straight to one:

| Tab | Answers |
|---|---|
| **Overview** | How big is the book, how much revenue is in it, what stands out today |
| **AOE Coverage** | Where the gaps are, by stage, and exactly which accounts to chase |
| **Team** | Who is carrying what — open any consultant to see their accounts |
| **Aging** | How long accounts have been open, as a neutral distribution |
| **Completed & Data** | The onboarded accounts, and everything the board is missing |

The AOE-by-stage and consultant rows expand to reveal the accounts behind them, each
deep-linked to its Monday item. The worklist is searchable, filterable by stage and region,
and sortable on every column.

## Design

Adobe Spectrum, read out of `~/Documents/Adobe Branding/` — which turns out to be a saved
Adobe web app, not a written guideline, so the brand lives entirely in its design tokens.

Three things that came out of reading it:

- **Adobe red `#EB1000` is the logo colour and nothing else.** In that whole bundle it is
  declared once, as `--feds-color-adobeBrand`, and dresses only the logo. Adobe's working UI
  accent is `#3B63FB`. So red is the ABV mark here and the reserved critical status, and blue
  does the work — exactly how Adobe uses them.
- **Adobe Clean can't be loaded.** It is Typekit-licensed and the artifact CSP admits only
  Google Fonts. Adobe's own declared fallback is Source Sans Pro, which Google Fonts ships as
  **Source Sans 3** — so that, with Source Code Pro for data.
- **Spectrum's `gray-500` is not a text colour.** `#909090` is 3.19:1 on white and fails AA.
  It is a placeholder colour and is used as one; muted text bottoms out at `gray-600`.

Light and dark are both designed, not flipped — the chart palette was re-checked against each
surface separately. Every colour pair on the page was run through a WCAG checker and every
chart palette through a six-check colourblind/contrast validator. Full keyboard operation,
`forced-colors` support, and a `<noscript>` fallback that drops the tabs and prints the whole
thing as one document.

## Build

```bash
python3 abv.py
```

Reads `data/abv_data.json`, writes:

- `dist/abv-ob-progress.html` — full document, for sending or opening locally
- `dist/abv-ob-progress.artifact.html` — outer wrapper stripped, the artifact publish source

The build refuses a snapshot older than 26h or dated in the future. Pass `--allow-stale`
to override for a historical rebuild.

## Where the data comes from

Two Monday reads, nothing else — see [`abv_pull.md`](abv_pull.md) for the exact call shape.
Board `18372591859`, groups `group_mm6c6h21` (in progress) and `group_mm6cwt2z` (onboarded),
fetched through the virtual `group` column. No `get_updates`, no per-item fan-out, and never
`execute_code` — it raises an interactive prompt that freezes an unattended run permanently.

The snapshot stores Monday's column values **verbatim**. All parsing lives in `abv.py`, so
each quirk is handled once and can be tested.

## Three things that will bite you

**1. ABV is a board group, not a name pattern.** Most ABV accounts are named plainly —
Colgate, Asus, Kohler, Mango. A name regex like `/adobe|abv|llmo/i` matches only 4 of 57.
Membership of `group_mm6c6h21` is the only correct definition.

**2. The AOE Assigned checkbox serialises two different ways.** Checked → the *string* `"v"`.
Unchecked → the *object* `{"checked": false}`. Both naive readings fail silently and
plausibly:

| Reading | Result on the 2026-09-09 pull |
|---|---|
| `bool(v)` | 57 of 57 — every row, because `{"checked": false}` is a non-empty dict |
| `v.get("checked")` | 0 of 57 — none, because the checked case is a bare string |
| `abv.py:checked(v)` | **41 of 57** ✓ |

**3. `Days Open` is not always a number.** It returns the *string* `"null"` — not JSON null —
when Subscription Start is empty (7 of 57), and it goes **negative** for a future start date
(Trex Inc: `-53`). Neither may be folded into a "0–14 days" bucket; both render as their own
categories.

## No time-to-value target here

ABV accounts run on their own program clock. The onboarding board's 42-day target is written
for standard onboarding and does not apply to them, so the aging buckets are neutral — no
target line, no pass/fail, no zone colour. Don't add one, and don't invent a substitute.

## Privacy

The page is forwarded to managers, so it carries account names, stages and counts only.
Contact columns (`email_mkyrsh69`, `link_mkyrzrkh`) are never read. `abv.py` hard-fails the
build twice over: if a contact-shaped field reaches the snapshot, and if anything
email-shaped reaches the rendered output.

## Daily refresh

A scheduled weekday run (`30 11 * * 1-5` — 7:30 AM EDT, half an hour after the FY26 rebuild
so the two never contend for Monday) re-crawls, rebuilds and republishes to the same URL.
Prompt and invariants: [`abv_trigger_prompt.md`](abv_trigger_prompt.md),
[`abv_trigger_config.json`](abv_trigger_config.json). Trigger
`trig_016ABnWHXKb2xEfR43J2rLDU`.

`abv_send_trigger.py` emits the create/update body from those two files and diffs an echoed
response back against them — resends are documented to drop fields silently, so the prompt is
never hand-retyped and the echo is always checked.

**Monday reaches a scheduled session through `mcp_connections`, not `mcp_config`.** The FY26
trigger's `mcp_config` holds only the remote-devices bridge, which isn't mounted in scheduled
sessions at all; copying it verbatim would ship a trigger with no board access.

**One manual step before the page refreshes itself:** upload `abv.py` and `abv_pull.md` to the
claude.ai project through the project UI. The scheduled sandbox has no access to this Mac and no
git credentials, so it fetches its bundle from project knowledge docs. Until they're there the run
still crawls, writes the snapshot and sends a summary — it just says loudly that it couldn't build
the page. That path is proven: the first hand-fired run (2026-09-09) took it cleanly.

If a run fails, the page says so itself: past 26 hours without a refresh a banner appears at
the top. No banner means the figures are current.
