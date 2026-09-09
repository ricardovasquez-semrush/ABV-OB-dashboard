Rebuild the ABV OB In Progress dashboard for Beth King and Daniel Angol from live Monday data, using abv.py — do not re-derive the page design from this prompt.

UNATTENDED RUN. Nobody can answer questions. Never block, never guess, never skip the run. Anything uncertain is reported in the run summary, not resolved by invention.

PERMISSION RULE: NEVER call monday-code `execute_code`, and never any tool that raises an interactive permission prompt. A prompt in a scheduled session freezes the run in `requires_action` forever — it does not time out. If one appears, abandon that call and finish with the permitted read tools.
DATE RULE: take the current date and time from the environment clock. Never infer "today" from an item's updated_at. There is no scan cutoff to compute in this run — both board groups are read in full every time.

Owner: Ricardo Vasquez, Product Success Manager Enterprise, Semrush, America/New_York. Audience: Beth King and Daniel Angol, who manage the onboarding team, and Tommy, who asked them for a daily read. Scope: the WHOLE TEAM's ABV book across every onboarding consultant — this is deliberately NOT person-filtered, which is what makes it different from the FY26 Onboarding Command Center.

=== STEP 0 — FETCH THE BUNDLE ===
Fetch `abv.py` and `abv_pull.md` in this order:
(A) project knowledge docs at ROOT filenames (`abv.py`, `abv_pull.md`) — Ricardo uploads these through the claude.ai project UI, and they are AUTHORITATIVE;
(B) the project file store under `abv-dashboard/` (cached by a previous run) — fallback only, never preferred over a root upload.
After reading from root, WRITE copies to `abv-dashboard/abv.py` and `abv-dashboard/abv_pull.md` so the next run can use (B).
The remote-devices bridge tools are NOT mounted in scheduled sessions — do not look for them.
If NEITHER source yields `abv.py`: run DATA-ONLY — do the crawl, write `data/abv_data.json` and a concise markdown summary of the counts to the project store, SendUserFile the summary, and report loudly that the bundle needs caching. NEVER rebuild the page from prose.

=== STEP 1 — CRAWL (exactly two calls) ===
Follow `abv_pull.md`. It is the contract; this is the summary.

Board 18372591859, monday_com MCP, NO person filter. Two `get_board_items_page` calls, one per group, `includeColumns: true`, `limit: 300`, filter `[{"columnId":"group","compareValue":"<GROUP>","operator":"any_of"}]` — `group` is a virtual column and the columnId is the literal string `"group"`.
  · `group_mm6c6h21` — ABV Onboarding In Progress → snapshot key `in_progress`
  · `group_mm6cwt2z` — ABV Onboarded → snapshot key `onboarded`

columnIds (all fourteen, both calls): `color_mkyrdx3` Stage · `boolean_mm71c8h0` AOE Assigned · `multiple_person_mkyrfhms` Onboarding Consultant · `formula_mkzb9602` Days Open · `formula_mkzb2g32` TTV Outcome · `date_mkpjnjj3` Subscription Start · `date2__1` Onboarding End Date · `date_mm01p45x` Forecast End · `dropdown_mkyrqgq0` Region · `numeric_mkyr2fx` MRR · `dropdown_mkxj9tkf` Products Purchased · `color_mm58e60r` Risk Status · `dropdown_mm58tn82` Risk Type · `color_mm588nx2` Risk Stage.

NO `get_updates`. No per-item fan-out. Two calls is the whole crawl.

NEVER read `email_mkyrsh69` (Main POC Email) or `link_mkyrzrkh` (Salesforce). This page is forwarded to managers and carries account names, stages and counts only. abv.py's privacy gate hard-fails the build if a contact-shaped field reaches the snapshot or an email address reaches the output — a refusal there is the gate working, not a bug to route around.

=== STEP 2 — WRITE THE SNAPSHOT ===
Write `data/abv_data.json` in the shape `abv_pull.md` specifies, with every column value copied VERBATIM — not normalised, not coerced, not pre-parsed. abv.py owns every quirk. In particular:
  · `boolean_mm71c8h0` comes back as the STRING `"v"` when checked and the OBJECT `{"checked": false}` when not. Store whichever arrived. Do not convert it to a boolean.
  · `formula_mkzb9602` comes back as the STRING `"null"` when Subscription Start is empty, and can be NEGATIVE for a future start date. Store the string.
  · Keep the raw board name including any `- LATAM` suffix; abv.py strips it for display.
  · An item with no consultant gets `null` — abv.py renders an explicit Unassigned row.
`generated_at_utc` is the real request time from the environment clock.

=== STEP 3 — BUILD + VERIFY ===
`python3 abv.py`. It emits `dist/abv-ob-progress.html` (full document) and `dist/abv-ob-progress.artifact.html` (outer wrapper stripped — the publish source), and refuses to build a snapshot older than 26h or dated in the future. A non-zero exit is a RUN FAILURE: report it precisely and do not publish.

Reconcile before publishing, and put these numbers in the run summary:
  · total in `in_progress` == the count the board returned for `group_mm6c6h21`;
  · AOE ticked is neither 0 nor equal to the total — both are the signature of the checkbox quirk being mis-parsed, and both look plausible on screen. On 2026-09-09 the true figure was 41 of 57. If you see 0 or all, STOP and report; do not publish.
  · the aging categories sum to the total, with "no start date" and "future start date" as their own categories.
  · the consultant table sums to the total, including the Unassigned row.
  · MRR: report the pipeline total, and how many accounts have NO MRR value and how many are set to exactly $0. An absent MRR is a gap and must never be counted as zero. On 2026-09-09 that was $229,663 across 45 accounts, with 12 missing and 11 at $0.

=== STEP 4 — DELIVER ===
SendUserFile `dist/abv-ob-progress.html` every run — this is the fallback that makes the run useful even if publishing fails.
Then publish `dist/abv-ob-progress.artifact.html` to https://claude.ai/code/artifact/0d2649df-3387-4b0b-bfbe-b3410a461b43 (favicon 📊, title "ABV OB In Progress"). Pass the URL as `url` so it updates in place instead of creating a second artifact. NEVER pass a `capabilities` argument — this page declares none and must stay freely shareable. NEVER `force` on a publish conflict: re-read the live version, merge, publish again.
If no Artifact tool is available in the session, write the artifact variant and its SHA-256 to the project store and say so loudly in the report.
Write `data/abv_data.json` and a short `abv-dashboard/last-run.md` (counts, deltas since the previous run, anything that looked wrong) back to the project store.

=== GUARDRAILS ===
READ-ONLY toward Monday: never `create_update`, never `change_item_column_values`, never any write tool. The board is the source of truth and this page never edits it — the data-gaps panel is suggest-only.
Never invent a value. A missing column renders as a gap, never as a zero or a guess.
NEVER judge these accounts against the board's 42-day time-to-value target. ABV runs on its own program clock; the aging buckets on this page are deliberately neutral, with no target line and no pass/fail. Do not add one, and do not invent an alternative threshold.
Accuracy over favourable framing: report the AOE gaps, the missing start dates and the unassigned account even where they reflect badly.
Push notification only if the run FAILS or the reconciliation check above trips.
