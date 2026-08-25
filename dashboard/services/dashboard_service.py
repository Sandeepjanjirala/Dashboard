"""
Business-rule layer. Takes a filtered DataFrame (produced by
aggregation_service) and turns it into the JSON-safe dashboard structures
the API returns.

Every calculation here follows the aggregate-then-divide rule agreed for
this project: never average a per-branch percentage or ratio across
branches. Always sum the underlying numerators and denominators first,
then divide once.
"""
from dashboard.services import aggregation_service as agg
from dashboard.utils import calculations as calc
from dashboard.utils import column_mapping as cm

# ---------------------------------------------------------------------------
# KPI section
# ---------------------------------------------------------------------------


def build_kpis(df):
    total_sections = agg.col_sum(df, cm.COL_NOS)
    total_class_rooms = agg.col_sum(df, cm.COL_NOCR)
    occupied_rooms = agg.col_sum(df, cm.COL_NOOR)
    empty_rooms = agg.col_sum(df, cm.COL_NOVR)

    cy_ns = agg.col_sum(df, cm.COL_CY_NS)
    avg_strength_per_section = calc.safe_round(calc.safe_div(cy_ns, total_sections), 1)

    cy_dp = agg.col_sum(df, cm.COL_CY_DP)
    cy_gs = agg.col_sum(df, cm.COL_CY_GS)
    cy_dropout_pct = calc.safe_pct(cy_dp, cy_gs, decimals=1)

    ly_dp = agg.col_sum(df, cm.COL_LY_DP)
    ly_gs = agg.col_sum(df, cm.COL_LY_GS)
    ly_dropout_pct = calc.safe_pct(ly_dp, ly_gs, decimals=1)

    return {
        "total_sections": {
            "value": int(total_sections),
            "ly_value": None,  # not derivable -- see README "Ambiguities" section
        },
        "total_class_rooms": {
            "value": int(total_class_rooms),
            "ly_value": None,
        },
        "occupied_rooms": {
            "value": int(occupied_rooms),
            "occupancy_pct": calc.safe_pct(occupied_rooms, total_class_rooms, decimals=1),
        },
        "empty_rooms": {
            "value": int(empty_rooms),
            "vacancy_pct": calc.safe_pct(empty_rooms, total_class_rooms, decimals=1),
        },
        "avg_strength_per_section": {
            "value": avg_strength_per_section,
            "ly_value": None,  # no LY section-count column exists to divide by
        },
        "cy_dropout_percentage": {
            "value": cy_dropout_pct,
            "ly_value": ly_dropout_pct,
        },
    }


# ---------------------------------------------------------------------------
# Dropout analysis (overall LY vs CY, plus PP/PS/HS breakdown)
# ---------------------------------------------------------------------------


def _period_block(df, period):
    dp = agg.col_sum(df, cm.strength_col("DP", period))
    gs = agg.col_sum(df, cm.strength_col("GS", period))
    ns = agg.col_sum(df, cm.strength_col("NS", period))
    return {
        "grant_strength": int(gs),
        "dropouts": int(dp),
        "net_strength": int(ns),
        "dropout_pct": calc.safe_pct(dp, gs, decimals=1),
    }


def _category_block(df, category):
    sections = agg.col_sum(df, cm.shape_col("NOS", category=category))
    cy_ns = agg.col_sum(df, cm.strength_col("NS", "CY", category=category))
    avg_strength_per_section = calc.safe_round(calc.safe_div(cy_ns, sections), 1)

    return {
        "label": cm.CATEGORY_LABELS[category],
        "sections": int(sections),
        "avg_strength_per_section": avg_strength_per_section,
        "ly": _category_period_block(df, category, "LY"),
        "cy": _category_period_block(df, category, "CY"),
    }


def _category_period_block(df, category, period):
    dp = agg.col_sum(df, cm.strength_col("DP", period, category=category))
    gs = agg.col_sum(df, cm.strength_col("GS", period, category=category))
    ns = agg.col_sum(df, cm.strength_col("NS", period, category=category))
    return {
        "grant_strength": int(gs),
        "dropouts": int(dp),
        "net_strength": int(ns),
        "dropout_pct": calc.safe_pct(dp, gs, decimals=1),
    }


def build_dropout_analysis(df):
    return {
        "overall": {
            "ly": _period_block(df, "LY"),
            "cy": _period_block(df, "CY"),
        },
        "categories": {
            category: _category_block(df, category) for category in cm.CATEGORIES
        },
    }


# ---------------------------------------------------------------------------
# Staff analysis (Activity / Administration)
# ---------------------------------------------------------------------------


def build_staff_analysis(df):
    result = {}
    for staff_type in cm.STAFF_TYPES:
        cy_count = agg.col_sum(df, cm.staff_col(staff_type, "CY-SC"))
        ly_count = agg.col_sum(df, cm.staff_col(staff_type, "LY-SC"))
        result[staff_type] = {
            "label": cm.STAFF_TYPE_LABELS[staff_type],
            "cy_count": int(cy_count),
            "ly_count": int(ly_count),
            "diff": int(cy_count - ly_count),
        }

    # Category-wise student-teacher ratio (weighted, not averaged).
    result["student_teacher_ratio"] = {}
    for category in cm.CATEGORIES:
        cy_ns = agg.col_sum(df, cm.strength_col("NS", "CY", category=category))
        cy_sc = agg.col_sum(df, cm.shape_col("CY-SC", category=category))
        ly_ns = agg.col_sum(df, cm.strength_col("NS", "LY", category=category))
        ly_sc = agg.col_sum(df, cm.shape_col("LY-SC", category=category))
        result["student_teacher_ratio"][category] = {
            "label": cm.CATEGORY_LABELS[category],
            "cy_ratio": calc.safe_round(calc.safe_div(cy_ns, cy_sc), 1),
            "ly_ratio": calc.safe_round(calc.safe_div(ly_ns, ly_sc), 1),
            # cy_sc/ly_sc were already being computed above for the ratio
            # itself -- exposing them too (same numbers, no new source
            # data) is what lets the UI show the "24-25/25-26 Staff Count"
            # + diff line the per-category ratio cards need.
            "cy_staff_count": int(cy_sc),
            "ly_staff_count": int(ly_sc),
            "diff": int(cy_sc - ly_sc),
        }

    overall_cy_ns = agg.col_sum(df, cm.COL_CY_NS)
    overall_cy_sc = agg.col_sum(df, cm.shape_col("CY-SC"))
    overall_ly_ns = agg.col_sum(df, cm.COL_LY_NS)
    overall_ly_sc = agg.col_sum(df, cm.shape_col("LY-SC"))
    result["student_teacher_ratio"]["overall"] = {
        "label": "Overall",
        "cy_ratio": calc.safe_round(calc.safe_div(overall_cy_ns, overall_cy_sc), 1),
        "ly_ratio": calc.safe_round(calc.safe_div(overall_ly_ns, overall_ly_sc), 1),
        # Overall Student/Teacher Count -- this is the workbook's overall
        # CY-SC / LY-SC columns, NOT AC-CY-SC + AD-CY-SC. AC (Activity Staff)
        # and AD (Administration Staff) are separate categories tracked
        # above and must never be summed to produce this figure.
        "cy_staff_count": int(overall_cy_sc),
        "ly_staff_count": int(overall_ly_sc),
    }

    return result


# ---------------------------------------------------------------------------
# Room analysis
# ---------------------------------------------------------------------------


def build_room_analysis(df):
    total = agg.col_sum(df, cm.COL_NOCR)
    occupied = agg.col_sum(df, cm.COL_NOOR)
    empty = agg.col_sum(df, cm.COL_NOVR)
    return {
        "total_class_rooms": int(total),
        "occupied_rooms": int(occupied),
        "empty_rooms": int(empty),
        "occupancy_pct": calc.safe_pct(occupied, total, decimals=1),
        "vacancy_pct": calc.safe_pct(empty, total, decimals=1),
    }


# ---------------------------------------------------------------------------
# RI-wise breakdown (used when the current selection spans multiple RIs)
# ---------------------------------------------------------------------------


def build_ri_analysis(df):
    value_cols = [cm.COL_CY_DP, cm.COL_CY_GS, cm.COL_CY_NS, cm.shape_col("CY-SC"), cm.COL_NOVR]
    grouped = agg.group_sum(df, cm.COL_RI, value_cols)

    rows = []
    for _, row in grouped.iterrows():
        cy_dp = row[cm.COL_CY_DP]
        cy_gs = row[cm.COL_CY_GS]
        cy_ns = row[cm.COL_CY_NS]
        cy_sc = row[cm.shape_col("CY-SC")]
        rows.append(
            {
                "ri_name": row[cm.COL_RI],
                "cy_dropouts": int(cy_dp),
                "dropout_pct": calc.safe_pct(cy_dp, cy_gs, decimals=1),
                "student_teacher_ratio": calc.safe_round(calc.safe_div(cy_ns, cy_sc), 1),
                "empty_rooms": int(row[cm.COL_NOVR]),
            }
        )

    rows.sort(key=lambda r: r["cy_dropouts"], reverse=True)
    return rows


def build_grand_total(df):
    """
    Aggregate totals across the entire filtered DataFrame -- used for the
    RI-wise table's "Grand Total" row. Computed the same way as every other
    aggregate in this module: sum the underlying totals first, divide once.
    """
    cy_dp = agg.col_sum(df, cm.COL_CY_DP)
    cy_gs = agg.col_sum(df, cm.COL_CY_GS)
    cy_ns = agg.col_sum(df, cm.COL_CY_NS)
    cy_sc = agg.col_sum(df, cm.shape_col("CY-SC"))
    empty_rooms = agg.col_sum(df, cm.COL_NOVR)

    return {
        "cy_dropouts": int(cy_dp),
        "dropout_pct": calc.safe_pct(cy_dp, cy_gs, decimals=1),
        "student_teacher_ratio": calc.safe_round(calc.safe_div(cy_ns, cy_sc), 1),
        "empty_rooms": int(empty_rooms),
    }


# ---------------------------------------------------------------------------
# Branch-wise breakdown
# ---------------------------------------------------------------------------


def build_branch_analysis(df):
    value_cols = [cm.COL_CY_DP, cm.COL_CY_GS, cm.COL_CY_NS, cm.shape_col("CY-SC"), cm.COL_NOVR]
    grouped = agg.group_sum(df, cm.COL_BRANCH, value_cols)

    rows = []
    for _, row in grouped.iterrows():
        cy_dp = row[cm.COL_CY_DP]
        cy_gs = row[cm.COL_CY_GS]
        cy_ns = row[cm.COL_CY_NS]
        cy_sc = row[cm.shape_col("CY-SC")]
        rows.append(
            {
                "branch_name": row[cm.COL_BRANCH],
                "cy_dropouts": int(cy_dp),
                "dropout_pct": calc.safe_pct(cy_dp, cy_gs, decimals=1),
                "student_teacher_ratio": calc.safe_round(calc.safe_div(cy_ns, cy_sc), 1),
                "empty_rooms": int(row[cm.COL_NOVR]),
            }
        )

    rows.sort(key=lambda r: r["cy_dropouts"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def build_dashboard_response(agm=None, ri=None, zone=None, branch=None):
    df = agg.get_filtered_dataframe(agm=agm, ri=ri, zone=zone, branch=branch)

    return {
        "success": True,
        "filters": {
            "agm": agm if not agg.is_all(agm) else "All",
            "ri": ri if not agg.is_all(ri) else "All",
            "zone": zone if not agg.is_all(zone) else "All",
            "branch": branch if not agg.is_all(branch) else "All",
        },
        "row_count": int(len(df)),
        "kpis": build_kpis(df),
        "dropout_analysis": build_dropout_analysis(df),
        "staff_analysis": build_staff_analysis(df),
        "room_analysis": build_room_analysis(df),
        "ri_analysis": build_ri_analysis(df),
        "ri_grand_total": build_grand_total(df),
        "branch_analysis": build_branch_analysis(df),
    }
