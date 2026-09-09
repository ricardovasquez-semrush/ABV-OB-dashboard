# ABV crawl spec — how `data/abv_data.json` is produced

Two Monday reads, nothing else. No `get_updates`, no per-item fan-out, and
**never `execute_code`** — it raises an interactive permission prompt that
freezes an unattended run in `requires_action` forever.

Monday MCP server `monday_com` (connector `e9a2b928-6092-4726-acac-587a31d24d5c`),
board **18372591859**, **no person filter** — this is the whole team's book.

## The two calls

```
get_board_items_page
  boardId: 18372591859
  includeColumns: true
  limit: 300
  filters: [{"columnId":"group","compareValue":"<GROUP>","operator":"any_of"}]
  columnIds: ["color_mkyrdx3","boolean_mm71c8h0","multiple_person_mkyrfhms",
              "formula_mkzb9602","formula_mkzb2g32","date_mkpjnjj3","date2__1",
              "date_mm01p45x","dropdown_mkyrqgq0","numeric_mkyr2fx",
              "dropdown_mkxj9tkf","color_mm58e60r","dropdown_mm58tn82",
              "color_mm588nx2"]
```

| `<GROUP>` | Title | Snapshot key |
|---|---|---|
| `group_mm6c6h21` | ABV Onboarding In Progress | `in_progress` |
| `group_mm6cwt2z` | ABV Onboarded | `onboarded` |

`group` is a **virtual** column — `get_board_info` never returns it, but it is
filterable and the `columnId` is the literal string `"group"`.

There is no cutoff to compute. Both groups are read in full every run, so there
is no hand-typed date to get wrong.

## Column map

`boolean_mm71c8h0` (**AOE Assigned**) is the one column that is not in the main
dashboard's `schema.BOARD_COLUMNS` — it is a newer checkbox.

| Snapshot field | Column | Board title |
|---|---|---|
| `stage` | `color_mkyrdx3` | Stage |
| `aoe_assigned` | `boolean_mm71c8h0` | AOE Assigned |
| `oc` | `multiple_person_mkyrfhms` | Onboarding Consultant |
| `days_open` | `formula_mkzb9602` | Days Open |
| `ttv_outcome` | `formula_mkzb2g32` | TTV Outcome (onboarded group only) |
| `sub_start` | `date_mkpjnjj3` | Subscription Start |
| `end_date` | `date2__1` | Onboarding End Date |
| `forecast_end` | `date_mm01p45x` | Forecast End |
| `region` | `dropdown_mkyrqgq0` | Region |
| `mrr` | `numeric_mkyr2fx` | MRR |
| `products` | `dropdown_mkxj9tkf` | Products Purchased |
| `risk_status` / `risk_type` / `risk_stage` | `color_mm58e60r` / `dropdown_mm58tn82` / `color_mm588nx2` | Risk Status / Type / Stage |

Contact columns are **deliberately not read**. `email_mkyrsh69` (Main POC Email)
and `link_mkyrzrkh` (Salesforce) must never enter this snapshot — `abv.py`'s
privacy gate hard-fails the build if a field named like a contact appears, and
again if anything email-shaped reaches the rendered bytes. This page is
forwarded to managers.

## Write the values VERBATIM

Copy each column value exactly as Monday returned it. Do **not** normalise,
coerce or pre-parse. Every quirk is handled once, in `abv.py`, where it is
readable and testable:

1. **`boolean_mm71c8h0` serialises two ways.** Checked → the *string* `"v"`.
   Unchecked → the *object* `{"checked": false}`. Store whichever came back.
   (`abv.py:checked()` is the only correct reading — `bool(v)` counts every row
   because `{"checked": false}` is a non-empty dict, and `v.get("checked")`
   counts none because the checked case is a bare string.)
2. **`formula_mkzb9602` returns the string `"null"`** — not JSON null — when
   Subscription Start is empty, and can be **negative** when the start date is
   in the future. Store the string as-is.
3. **Names keep their `- LATAM` suffix in the snapshot.** `abv.py` strips it for
   display; the raw name stays the board's.
4. **An item can have no consultant.** Store `null`; `abv.py` renders an
   explicit "Unassigned" row and never drops it.

## Snapshot shape

```json
{
  "generated_at_utc": "2026-09-09T17:26:33Z",
  "board":   {"id": "18372591859", "name": "FY26 Onboarding Board"},
  "groups":  {"in_progress": {"id": "group_mm6c6h21", "title": "..."},
              "onboarded":   {"id": "group_mm6cwt2z", "title": "..."}},
  "columns": { ...the map above, for provenance... },
  "in_progress": [ {"id","name","url","group", ...columns above} ],
  "onboarded":   [ {... same, plus "ttv_outcome"} ]
}
```

`generated_at_utc` must be the real request time from the environment clock —
`abv.py` refuses to build a snapshot older than 26h (or one dated in the
future), and the page shows a stale banner past the same threshold.

## Then

```bash
python3 abv.py
```

emits `dist/abv-ob-progress.html` (full document, for SendUserFile) and
`dist/abv-ob-progress.artifact.html` (outer wrapper stripped — the publish
source). A non-zero exit is a run failure; do not publish an unbuilt file.

## Sanity floor

The 2026-09-09 read returned **57** in-progress and **3** onboarded, with **41**
AOE boxes ticked. Counts move daily, so these are not assertions — but a run
that reports 0 or 57-of-57 ticked has hit the checkbox quirk and must be
investigated, not published.
