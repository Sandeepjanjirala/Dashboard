"""
Fee Due Analysis business logic service.

Computes 8 KPI cards, chart datasets, analysis breakdown tables (Overview,
AGM, RI, Zone, Branch), and key insights for the Fee Due Dashboard.
"""
import pandas as pd

from dashboard.services import aggregation_service as agg
from dashboard.utils import calculations as calc


def build_kpis(df: pd.DataFrame) -> dict:
    ly_fd = agg.col_sum(df, "LY_FD")
    ly_fdc = agg.col_sum(df, "LY_FDC")
    cy_a_fd = agg.col_sum(df, "CY_A_FD")
    cy_a_fdc = agg.col_sum(df, "CY_A_FDC")
    actual_zp = agg.col_sum(df, "CY_A_ZP") if "CY_A_ZP" in df.columns else agg.col_sum(df, "CY_ZP")
    cy_zp_fd = agg.col_sum(df, "CY_ZP_FD")
    cy_fp_bn = agg.col_sum(df, "CY_FP_BN")
    cy_fn_bn = agg.col_sum(df, "CY_FN_BN")

    # YoY Percent Changes
    fd_diff_pct = calc.safe_pct(cy_a_fd - ly_fd, ly_fd, decimals=1) if ly_fd > 0 else 0.0
    fdc_diff_pct = calc.safe_pct(cy_a_fdc - ly_fdc, ly_fdc, decimals=1) if ly_fdc > 0 else 0.0

    return {
        "ly_fee_due": {
            "value": round(float(ly_fd), 2),
            "label": "2024-25 Fee Due",
        },
        "ly_due_count": {
            "value": int(ly_fdc),
            "label": "2024-25 Due Count",
        },
        "cy_live_student_fee_due": {
            "value": round(float(cy_a_fd), 2),
            "label": "2025-26 Live Student Fee Due",
            "yoy_change_pct": fd_diff_pct,
            "yoy_direction": "down" if cy_a_fd < ly_fd else "up",
        },
        "cy_live_student_due_count": {
            "value": int(cy_a_fdc),
            "label": "2025-26 Live Student Due Count",
            "yoy_change_pct": fdc_diff_pct,
            "yoy_direction": "down" if cy_a_fdc < ly_fdc else "up",
        },
        "actual_zero_paid_count": {
            "value": int(actual_zp),
            "label": "Actual Zero Paid Count (2025-26)",
        },
        "cy_zero_paid_fee_due": {
            "value": round(float(cy_zp_fd), 2),
            "label": "Current Year Zero Paid Fee Due",
        },
        "fee_paid_books_not_purchased": {
            "value": int(cy_fp_bn),
            "label": "Fee Paid But Books Not Purchased",
        },
        "fee_not_paid_books_not_purchased": {
            "value": int(cy_fn_bn),
            "label": "Fee Not Paid & Books Not Purchased",
        },
    }


def build_charts(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "fee_due_comparison_amount": [],
            "fee_due_comparison_count": [],
            "student_segmentation": {"actual_zero_paid": 0, "non_zero_paid": 0, "total_students": 0, "zero_paid_pct": 0.0},
            "top_5_branches_fee_due": [],
            "branch_type_wise_fee_due": [],
            "zero_paid_vs_others": {"actual_zero_paid": 0, "non_zero_paid": 0},
        }

    # 1. Fee Due Comparison (Amount) by Branch
    grouped_amt = agg.group_sum(df, "Branch", ["LY_FD", "CY_A_FD"])
    grouped_amt = grouped_amt.sort_values(by="CY_A_FD", ascending=False)
    fee_due_comp_amt = [
        {
            "branch": str(r["Branch"]),
            "ly_fee_due": round(float(r["LY_FD"]), 2),
            "cy_fee_due": round(float(r["CY_A_FD"]), 2),
        }
        for _, r in grouped_amt.iterrows()
    ]

    # 2. Fee Due Comparison (Count) by Branch
    grouped_cnt = agg.group_sum(df, "Branch", ["LY_FDC", "CY_A_FDC"])
    grouped_cnt = grouped_cnt.sort_values(by="CY_A_FDC", ascending=False)
    fee_due_comp_cnt = [
        {
            "branch": str(r["Branch"]),
            "ly_due_count": int(r["LY_FDC"]),
            "cy_due_count": int(r["CY_A_FDC"]),
        }
        for _, r in grouped_cnt.iterrows()
    ]

    # 3. Student Segmentation (Zero Paid vs Non Zero Paid)
    actual_zp = agg.col_sum(df, "CY_A_ZP") if "CY_A_ZP" in df.columns else agg.col_sum(df, "CY_ZP")
    total_due_cnt = agg.col_sum(df, "CY_A_FDC")
    non_zero_paid = max(0.0, total_due_cnt - actual_zp)
    zp_pct = calc.safe_pct(actual_zp, total_due_cnt, decimals=1)

    student_segmentation = {
        "actual_zero_paid": int(actual_zp),
        "non_zero_paid": int(non_zero_paid),
        "total_students": int(total_due_cnt),
        "zero_paid_pct": zp_pct,
    }

    # 4. Top 5 Branches by Fee Due (CY_A_FD + CY_ZP_FD)
    grouped_top = agg.group_sum(df, "Branch", ["CY_A_FD", "CY_ZP_FD"])
    top5_df = grouped_top.sort_values(by="CY_A_FD", ascending=False).head(5)
    top_5_branches = [
        {
            "branch": str(r["Branch"]),
            "live_student_fee_due": round(float(r["CY_A_FD"]), 2),
            "zero_paid_fee_due": round(float(r["CY_ZP_FD"]), 2),
        }
        for _, r in top5_df.iterrows()
    ]

    # 5. Branch Type Wise Fee Due (S_Type)
    s_type_col = "S_Type" if "S_Type" in df.columns else None
    type_breakdown = []
    if s_type_col and not df.empty:
        grouped_type = agg.group_sum(df, s_type_col, ["CY_A_FD"])
        total_cy_fd = grouped_type["CY_A_FD"].sum()
        for _, r in grouped_type.iterrows():
            fd_val = round(float(r["CY_A_FD"]), 2)
            pct = calc.safe_pct(fd_val, total_cy_fd, decimals=1)
            type_breakdown.append({
                "type": str(r[s_type_col]),
                "fee_due": fd_val,
                "percentage": pct,
            })
        type_breakdown.sort(key=lambda x: x["fee_due"], reverse=True)

    return {
        "fee_due_comparison_amount": fee_due_comp_amt,
        "fee_due_comparison_count": fee_due_comp_cnt,
        "student_segmentation": student_segmentation,
        "top_5_branches_fee_due": top_5_branches,
        "branch_type_wise_fee_due": type_breakdown,
        "zero_paid_vs_others": {
            "actual_zero_paid": int(actual_zp),
            "non_zero_paid": int(non_zero_paid),
        },
    }


def build_analysis_breakdowns(df: pd.DataFrame) -> dict:
    """
    Build breakdown tables for Overview, AGM Analysis, RI Analysis, Zone Analysis, and Branch Analysis.
    """
    value_cols = [
        "LY_FD", "LY_FDC", "CY_A_FD", "CY_A_FDC",
        "CY_A_ZP", "CY_ZP_FD", "CY_FP_BN", "CY_FN_BN"
    ]
    existing_cols = [c for c in value_cols if c in df.columns]

    def _group_rows(group_col: str, name_key: str):
        if df.empty or group_col not in df.columns:
            return []
        grouped = agg.group_sum(df, group_col, existing_cols)
        rows = []
        for _, r in grouped.iterrows():
            ly_fd = r.get("LY_FD", 0.0)
            cy_fd = r.get("CY_A_FD", 0.0)
            rows.append({
                name_key: str(r[group_col]),
                "ly_fee_due": round(float(ly_fd), 2),
                "ly_due_count": int(r.get("LY_FDC", 0)),
                "cy_live_student_fee_due": round(float(cy_fd), 2),
                "cy_live_student_due_count": int(r.get("CY_A_FDC", 0)),
                "actual_zero_paid_count": int(r.get("CY_A_ZP", 0)),
                "cy_zero_paid_fee_due": round(float(r.get("CY_ZP_FD", 0.0)), 2),
                "fee_paid_books_not_purchased": int(r.get("CY_FP_BN", 0)),
                "fee_not_paid_books_not_purchased": int(r.get("CY_FN_BN", 0)),
            })
        rows.sort(key=lambda x: x["cy_live_student_fee_due"], reverse=True)
        return rows

    return {
        "overview": _group_rows("Branch", "branch_name"),
        "agm_analysis": _group_rows("AGM Name", "agm_name"),
        "ri_analysis": _group_rows("RI Name", "ri_name"),
        "zone_analysis": _group_rows("Zone", "zone_name"),
        "branch_analysis": _group_rows("Branch", "branch_name"),
    }


def build_key_insights(df: pd.DataFrame) -> list:
    """
    Generate dynamic key insights bullet points based on the filtered DataFrame.
    """
    ly_fd = agg.col_sum(df, "LY_FD")
    cy_a_fd = agg.col_sum(df, "CY_A_FD")
    ly_fdc = agg.col_sum(df, "LY_FDC")
    cy_a_fdc = agg.col_sum(df, "CY_A_FDC")
    actual_zp = agg.col_sum(df, "CY_A_ZP") if "CY_A_ZP" in df.columns else agg.col_sum(df, "CY_ZP")
    cy_fp_bn = agg.col_sum(df, "CY_FP_BN")
    cy_fn_bn = agg.col_sum(df, "CY_FN_BN")

    insights = []

    # 1. Fee Due Amount Change
    if ly_fd > 0:
        diff_amt = cy_a_fd - ly_fd
        pct_change = abs(calc.safe_pct(diff_amt, ly_fd, decimals=1))
        direction = "reduced" if diff_amt <= 0 else "increased"
        insights.append({
            "type": "fee_due_change",
            "text": f"Live Student Fee Due {direction} by {pct_change}% compared to 2024-25.",
            "direction": "down" if diff_amt <= 0 else "up",
        })

    # 2. Due Count Change
    if ly_fdc > 0:
        diff_cnt = cy_a_fdc - ly_fdc
        pct_change_cnt = abs(calc.safe_pct(diff_cnt, ly_fdc, decimals=1))
        direction_cnt = "reduced" if diff_cnt <= 0 else "increased"
        insights.append({
            "type": "due_count_change",
            "text": f"Student Due Count {direction_cnt} by {pct_change_cnt}% compared to 2024-25 ({int(ly_fdc)} → {int(cy_a_fdc)}).",
            "direction": "down" if diff_cnt <= 0 else "up",
        })

    # 3. Actual Zero Paid
    if cy_a_fdc > 0:
        zp_pct = calc.safe_pct(actual_zp, cy_a_fdc, decimals=1)
        insights.append({
            "type": "zero_paid",
            "text": f"{int(actual_zp)} students ({zp_pct}%) are Actual Zero Paid in 2025-26.",
            "direction": "warning",
        })

    # 4. Books Not Purchased
    if cy_fp_bn > 0:
        insights.append({
            "type": "books_fp_bn",
            "text": f"{int(cy_fp_bn)} students have paid fee but not purchased books.",
            "direction": "info",
        })

    if cy_fn_bn > 0:
        insights.append({
            "type": "books_fn_bn",
            "text": f"{int(cy_fn_bn)} students have neither paid fee nor purchased books.",
            "direction": "alert",
        })

    return insights


def build_fee_due_dashboard_response(agm=None, ri=None, zone=None, branch=None) -> dict:
    df = agg.get_filtered_dataframe(agm=agm, ri=ri, zone=zone, branch=branch, dataset_id="fee_due")

    return {
        "success": True,
        "dataset": "fee_due",
        "filters": {
            "agm": agm if not agg.is_all(agm) else "All",
            "ri": ri if not agg.is_all(ri) else "All",
            "zone": zone if not agg.is_all(zone) else "All",
            "branch": branch if not agg.is_all(branch) else "All",
        },
        "row_count": int(len(df)),
        "kpis": build_kpis(df),
        "charts": build_charts(df),
        "breakdowns": build_analysis_breakdowns(df),
        "key_insights": build_key_insights(df),
    }
