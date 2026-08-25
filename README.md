# Branch Analytics Dashboard — Backend (Phase 1)

Django + DRF + Pandas backend for the branch analytics dashboard. This
phase delivers the **data/backend foundation only** — Excel ingestion,
column mapping, aggregation rules, and REST API. No HTML/CSS/jQuery UI yet
(that's Phase 2, built on top of the API below).

---

## 1. Project structure

```
branch_dashboard/
├── manage.py
├── requirements.txt
├── data/
│   └── branch_analytics.xlsx          # source workbook (source of truth)
├── config/                            # Django project config
│   ├── settings.py                    # EXCEL_DATA_PATH, DRF, CORS, logging
│   ├── urls.py                        # mounts dashboard.urls at /api/
│   └── wsgi.py / asgi.py
└── dashboard/                         # the app
    ├── views.py                       # thin: parse params -> call service -> Response
    ├── serializers.py                 # validates ?agm=&ri=&branch= query params
    ├── urls.py                        # /filters/ and / (dashboard) routes
    ├── services/
    │   ├── excel_service.py           # loads + caches the workbook as a DataFrame
    │   ├── aggregation_service.py      # AGM->RI->Branch filtering, sum/groupby helpers
    │   └── dashboard_service.py        # business rules: KPIs, dropout/staff/room analysis
    ├── utils/
    │   ├── column_mapping.py           # the ONLY file with literal Excel column names
    │   └── calculations.py             # safe_div, safe_pct, JSON-safety helpers
    └── tests/
        └── test_dashboard.py           # 21 tests covering the required test matrix
```

**Data flow:** `Excel → excel_service (pandas, cached) → aggregation_service
(filtering) → dashboard_service (business rules) → views.py → JSON`.
jQuery/AJAX will only ever talk to the JSON API — no Excel or Pandas logic
in the browser.

---

## 2. Excel column mapping

The workbook has **146 columns**, all following one consistent naming
grammar. `dashboard/utils/column_mapping.py` builds every column name
programmatically from this grammar (rather than hardcoding 146 strings),
and an automated test (`ColumnMappingTests`) asserts the built list matches
the real workbook exactly — 146/146, no gaps, nothing left over.

| Pattern | Example | Meaning |
|---|---|---|
| `<CAT>-<SUB>-<PERIOD>-<METRIC>` | `PP-E-CY-GS` | Pre Primary, Existing, Current Year, Grant Strength |
| `<CAT>-<PERIOD>-<METRIC>` | `PP-CY-GS` | Pre Primary, Current Year, Grant Strength (E+N combined) |
| `<SUB>-<PERIOD>-<METRIC>` | `E-CY-GS` | Overall, Existing only |
| `<PERIOD>-<METRIC>` | `CY-GS` | Overall, combined |
| `<CAT>-<FIELD>` | `PP-NOS` | Pre Primary, Number of Sections |
| `<FIELD>` | `NOS` | Overall, Number of Sections |
| `<STAFFTYPE>-<FIELD>` | `AC-CY-SC` | Activity Staff, Current Year Staff Count |

Where:
- `CAT` = `PP` (Pre Primary) / `PS` (Primary School) / `HS` (High School)
- `SUB` = `E` (Existing) / `N` (New)
- `PERIOD` = `LY` (2024-25) / `CY` (2025-26)
- `METRIC` = `GS` (Grant Strength) / `DP` (Dropouts) / `DPP` (Dropout %) / `NS` (Net Strength)
- Per-category/overall "shape" fields: `NSD`, `NOS`, `Avg-SPS`, `CY-SC`,
  `LY-SC`, `SD`, `CY-STR`, `LY-STR`
- Room fields (overall only, no PP/PS/HS split): `NOCR`, `NOOR`, `NOVR`, `ARCS`
- Identifier columns: `AGM Name`, `RI Name`, `Zone`, `Branch`

Verified relationships in the actual data (used as the basis for the
aggregation rules below):
- `NOCR = NOOR + NOVR` for every row
- `NOS = PP-NOS + PS-NOS + HS-NOS`, and same for `CY-GS`, `CY-NS`, `CY-DP`
- `CY-DPP = CY-DP / CY-GS × 100` (i.e. the pre-computed `DPP` columns are
  just the row-level version of the same formula we use when aggregating)
- `Avg-SPS = CY-NS / NOS`

---

## 3. Calculation rules

All aggregation follows one rule: **sum the underlying totals first, divide
once.** Never average a per-branch percentage or ratio across branches.

| KPI | Formula |
|---|---|
| Total Sections | `SUM(NOS)` |
| Total Class Rooms | `SUM(NOCR)` |
| Rooms Occupied | `SUM(NOOR)` |
| Empty Rooms | `SUM(NOVR)` |
| Avg Strength / Section | `SUM(CY-NS) / SUM(NOS)` |
| CY Dropout % | `SUM(CY-DP) / SUM(CY-GS) × 100` |
| Category (PP/PS/HS) Avg Strength / Section | `SUM(cat CY-NS) / SUM(cat NOS)` |
| Category Dropout % | `SUM(cat CY-DP) / SUM(cat CY-GS) × 100` |
| Student-Teacher Ratio (any grouping) | `SUM(CY-NS) / SUM(CY-SC)` — weighted, not an average of the row-level ratio |

Division by zero never crashes: `calculations.safe_div` / `safe_pct` return
`0` (or the field's stated default) instead of raising, and every float is
passed through `to_json_safe()` so `NaN`/`Infinity` can never reach the
response (tested explicitly in `test_response_has_no_nan_or_infinity`).

---

## 4. API endpoints

### `GET /api/dashboard/filters/?agm=&ri=`
Cascading filter metadata. `agm` and `ri` are optional; passing one scopes
the options returned for the level(s) below it.

```json
{
  "success": true,
  "agms": ["Mr.M.V.Suresh"],
  "ris": ["Mr.Ahmedali", "Mr M.V.L.Naresh", "..."],
  "branches": ["ASILMETTA", "ASILMETTA 3", "..."]
}
```

### `GET /api/dashboard/?agm=&ri=&branch=`
Full dashboard payload for the given filter selection. All three params
are optional; omit or pass `All` for "no filter at this level".

Example — `?ri=Mr.P Gopi Nath&branch=KAKINADA 1` (single branch):

```json
{
  "success": true,
  "filters": { "agm": "All", "ri": "Mr.P Gopi Nath", "branch": "KAKINADA 1" },
  "row_count": 1,
  "kpis": {
    "total_sections": { "value": 23, "ly_value": null },
    "total_class_rooms": { "value": 32, "ly_value": null },
    "occupied_rooms": { "value": 23, "occupancy_pct": 71.9 },
    "empty_rooms": { "value": 9, "vacancy_pct": 28.1 },
    "avg_strength_per_section": { "value": 33.3, "ly_value": null },
    "cy_dropout_percentage": { "value": 15.2, "ly_value": 11.8 }
  },
  "dropout_analysis": {
    "overall": {
      "ly": { "grant_strength": 959, "dropouts": 113, "net_strength": 846, "dropout_pct": 11.8 },
      "cy": { "grant_strength": 903, "dropouts": 137, "net_strength": 766, "dropout_pct": 15.2 }
    },
    "categories": {
      "PP": { "label": "Pre Primary", "sections": 5, "avg_strength_per_section": 23.4,
              "ly": { "...": "..." }, "cy": { "...": "..." } },
      "PS": { "...": "..." },
      "HS": { "...": "..." }
    }
  },
  "staff_analysis": {
    "AC": { "label": "Activity Staff", "cy_count": 3, "ly_count": 4, "diff": -1 },
    "AD": { "label": "Administration Staff", "cy_count": 12, "ly_count": 13, "diff": -1 },
    "student_teacher_ratio": {
      "PP": { "label": "Pre Primary", "cy_ratio": 23.4, "ly_ratio": 27.0 },
      "PS": { "...": "..." }, "HS": { "...": "..." },
      "overall": { "label": "Overall", "cy_ratio": 16.3, "ly_ratio": 16.0 }
    }
  },
  "room_analysis": {
    "total_class_rooms": 32, "occupied_rooms": 23, "empty_rooms": 9,
    "occupancy_pct": 71.9, "vacancy_pct": 28.1
  },
  "ri_analysis": [
    { "ri_name": "Mr.P Gopi Nath", "cy_dropouts": 137, "dropout_pct": 15.2,
      "student_teacher_ratio": 16.3, "empty_rooms": 9 }
  ],
  "branch_analysis": [
    { "branch_name": "KAKINADA 1", "cy_dropouts": 137, "dropout_pct": 15.2,
      "student_teacher_ratio": 16.3, "empty_rooms": 9 }
  ]
}
```

`ri_analysis` and `branch_analysis` are grouped breakdowns *within the
current filter selection* — with no filters applied you get all 9 RIs /
all 59 branches; scope down to one RI and you get that RI's branches, etc.
Both are sorted by `cy_dropouts` descending, matching the "Top N" framing
in your reference screenshot.

**Invalid filter values return a clean error, never a crash:**
```
GET /api/dashboard/?ri=NoSuchRI
→ 400 {"success": false, "error": "Unknown ri: 'NoSuchRI'"}

GET /api/dashboard/?ri=Mr.P Gopi Nath&branch=BOBBILI   (BOBBILI isn't under that RI)
→ 400 {"success": false, "error": "Unknown branch: 'BOBBILI'"}
```

---

## 5. How to start the server

```bash
cd branch_dashboard
pip install -r requirements.txt
python manage.py migrate      # only needed for Django's own admin/auth tables
python manage.py runserver 0.0.0.0:8000
```

Then:
- `http://localhost:8000/api/dashboard/filters/`
- `http://localhost:8000/api/dashboard/`
- `http://localhost:8000/api/dashboard/?ri=Mr.Ahmedali`

The Browsable API (DRF's default renderer) also works directly in a
browser at those URLs for manual poking-around.

To swap in a different workbook, just replace
`data/branch_analytics.xlsx` — the cache in `excel_service.py` checks the
file's mtime and reloads automatically on the next request.

---

## 6. How to test the APIs

Automated (recommended — 21 tests, covers the full matrix from the spec):

```bash
python manage.py test dashboard -v 2
```

Covers: all-AGM / individual AGM / individual RI / individual branch / AGM
+ all-RI + all-branch / AGM + RI + all-branch / AGM + RI + branch, plus
PP/PS/HS aggregation correctness, invalid-filter error handling, and
JSON-safety (no NaN/Infinity).

Manual, with curl:

```bash
curl "http://localhost:8000/api/dashboard/filters/"
curl "http://localhost:8000/api/dashboard/"
curl "http://localhost:8000/api/dashboard/?agm=Mr.M.V.Suresh"
curl "http://localhost:8000/api/dashboard/?ri=Mr.P%20Gopi%20Nath"
curl "http://localhost:8000/api/dashboard/?ri=Mr.P%20Gopi%20Nath&branch=KAKINADA%201"
```

---

## 7. Assumptions I made

1. **"All" filter value.** Empty string, missing param, or the literal
   string `All`/`all` are all treated as "no filter at this level" —
   picked so the frontend doesn't have to special-case an unset dropdown.
2. **Row 0 GS = 0 edge case.** KAKINADA 1's `HS-LY-GS` is 0 (no High
   School existed there last year) while `HS-CY-GS` is 33. `safe_div`
   returns `0.0` for the LY dropout % in that case rather than dividing by
   zero — I did not attempt to infer a "meaningful" LY value.
3. **Sort order for `ri_analysis` / `branch_analysis`.** Sorted by CY
   dropout count descending, matching your screenshot's "Top 8" framing.
   Trivial to change to alphabetical or by dropout % if you'd prefer.
4. **Rounding.** All percentages and averages are rounded to 1 decimal
   place for display, matching your screenshot's precision (e.g. `34.2`).
   Raw sums (`grant_strength`, `dropouts`, etc.) are returned as integers,
   unrounded.

## 8. Ambiguities that need your confirmation

1. **`SC` = Section Count or Staff Count?** Your glossary states
   `SC = Section Count`, but the data doesn't support that literally:
   `NOS` (23) already represents section count, while `CY-SC` (47) is
   roughly double that and lines up closely with `CY-NS / CY-STR`
   (Student Teacher Ratio). I've treated `SC` as **Staff/Teacher Count**
   throughout (Staff Analysis panel, Student-Teacher Ratio calc) since
   that's what the numbers actually support — but please confirm, since
   swapping the interpretation would change the Staff Analysis panel
   meaningfully.
2. **No Last-Year figure for KPIs 1–5** (Total Sections, Class Rooms,
   Occupied Rooms, Empty Rooms, Avg Strength/Section). The workbook only
   has *current-year* values for `NOS`, `NOCR`, `NOOR`, `NOVR` — there's
   no `LY-NOS`/`LY-NOCR`/etc. column to compute a "2024-25: X" comparison
   subtitle like your screenshot shows for these cards. I return
   `ly_value: null` for these five rather than guessing. Only KPI 6
   (Dropout %) has genuine LY and CY figures in the source data. If a
   true LY comparison for sections/rooms is needed, that data isn't in
   this workbook and would need to come from somewhere else (a prior
   year's workbook, a new column, etc.).
3. **`ARCS` (Average Room Capacity Sq Ft)** is `0` for all 59 rows — the
   column exists in the schema but has no populated data. It's not used
   in any KPI currently; flagging in case it matters for a future card.

---

## 9. What's deliberately *not* in this phase

Per the spec: no final HTML/CSS, no jQuery/AJAX wiring, no Chart.js. This
phase is the data foundation only — Phase 2 builds the actual dashboard UI
against the two endpoints documented above.
