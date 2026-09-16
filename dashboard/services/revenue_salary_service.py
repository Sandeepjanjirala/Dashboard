"""
Revenue vs Salary Analysis business logic service.

Computes 9 KPI cards, chart datasets, academic segment breakdown tables, and key insights for the Revenue vs Salary Dashboard.
"""
import pandas as pd

from dashboard.services import aggregation_service as agg
from dashboard.utils import calculations as calc


def build_kpis(df: pd.DataFrame) -> dict:
    tot_rev = agg.col_sum(df, "TOT_REV_N")
    tot_sal = agg.col_sum(df, "TOT_SAL")
    tot_ns = agg.col_sum(df, "TOT_NS")
    tot_sc = agg.col_sum(df, "TOT_SC")
    surplus = tot_rev - tot_sal

    fa = (tot_rev / tot_ns) if tot_ns > 0 else 0.0
    cs = (tot_sal / tot_ns) if tot_ns > 0 else 0.0
    sal_v_rev = ((tot_sal / tot_rev) * 100.0) if tot_rev > 0 else 0.0
    str_ratio = (tot_ns / tot_sc) if tot_sc > 0 else 0.0

    return {
        "total_revenue": {
            "value": round(float(tot_rev), 2),
            "label": "Total Net Revenue",
        },
        "total_salary": {
            "value": round(float(tot_sal), 2),
            "label": "Total Salary Cost",
        },
        "net_surplus": {
            "value": round(float(surplus), 2),
            "label": "Net Surplus",
        },
        "total_students": {
            "value": int(tot_ns),
            "label": "Total Students",
        },
        "total_employees": {
            "value": int(tot_sc),
            "label": "Total Employees",
        },
        "fee_average": {
            "value": round(float(fa), 2),
            "label": "Fee Average",
        },
        "cost_per_student": {
            "value": round(float(cs), 2),
            "label": "Cost per Student",
        },
        "salary_vs_revenue_pct": {
            "value": round(float(sal_v_rev), 2),
            "label": "Salary vs Revenue %",
        },
        "student_teacher_ratio": {
            "value": round(float(str_ratio), 2),
            "label": "Student Teacher Ratio",
        },
    }


def build_segment_analysis(df: pd.DataFrame) -> list[dict]:
    segments = [
        ("PP", "Pre Primary"),
        ("LPS", "Lower Primary"),
        ("UPS", "Upper Primary"),
        ("HS", "High School"),
        ("ACD", "ACD"),
        ("AD_AC", "Activity & Admin"),
    ]
    out = []
    for code, label in segments:
        rev_col = f"{code}_REV_N"
        sal_col = f"{code}_SAL"
        ns_col = f"{code}_NS"
        sc_col = f"{code}_SC"

        rev = agg.col_sum(df, rev_col) if rev_col in df.columns else 0.0
        sal = agg.col_sum(df, sal_col) if sal_col in df.columns else 0.0
        ns = agg.col_sum(df, ns_col) if ns_col in df.columns else 0.0
        sc = agg.col_sum(df, sc_col) if sc_col in df.columns else 0.0
        surplus = rev - sal

        fa = (rev / ns) if ns > 0 else 0.0
        cs = (sal / ns) if ns > 0 else 0.0
        sal_v_rev = ((sal / rev) * 100.0) if rev > 0 else 0.0
        str_ratio = (ns / sc) if sc > 0 else 0.0

        out.append({
            "segment_code": code,
            "segment_name": label,
            "total_revenue": round(float(rev), 2),
            "total_salary": round(float(sal), 2),
            "surplus": round(float(surplus), 2),
            "student_count": int(ns),
            "employee_count": int(sc),
            "fee_average": round(float(fa), 2),
            "cost_per_student": round(float(cs), 2),
            "salary_vs_revenue_pct": round(float(sal_v_rev), 2),
            "student_teacher_ratio": round(float(str_ratio), 2),
        })
    return out


def build_charts(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "top_branches_revenue": [],
            "top_branches_surplus": [],
            "segment_comparison": [],
        }

    grouped_rev = agg.group_sum(df, "Branch", ["TOT_REV_N", "TOT_SAL"])
    grouped_rev["surplus"] = grouped_rev["TOT_REV_N"] - grouped_rev["TOT_SAL"]
    top_rev = grouped_rev.sort_values(by="TOT_REV_N", ascending=False).head(5)

    top_branches_rev = [
        {
            "branch": str(r["Branch"]),
            "revenue": round(float(r["TOT_REV_N"]), 2),
            "salary": round(float(r["TOT_SAL"]), 2),
            "surplus": round(float(r["surplus"]), 2),
        }
        for _, r in top_rev.iterrows()
    ]

    top_surp = grouped_rev.sort_values(by="surplus", ascending=False).head(5)
    top_branches_surp = [
        {
            "branch": str(r["Branch"]),
            "revenue": round(float(r["TOT_REV_N"]), 2),
            "salary": round(float(r["TOT_SAL"]), 2),
            "surplus": round(float(r["surplus"]), 2),
        }
        for _, r in top_surp.iterrows()
    ]

    segment_data = build_segment_analysis(df)
    segment_comp = [
        {
            "segment": s["segment_name"],
            "revenue": s["total_revenue"],
            "salary": s["total_salary"],
            "surplus": s["surplus"],
        }
        for s in segment_data
    ]

    return {
        "top_branches_revenue": top_branches_rev,
        "top_branches_surplus": top_branches_surp,
        "segment_comparison": segment_comp,
    }


def build_revenue_salary_dashboard_response(agm=None, ri=None, zone=None, branch=None) -> dict:
    df = agg.get_filtered_dataframe(agm=agm, ri=ri, zone=zone, branch=branch, dataset_id="revenue_vs_salary")
    kpis = build_kpis(df)
    segments = build_segment_analysis(df)
    charts = build_charts(df)

    branch_rows = []
    if not df.empty:
        grouped = agg.group_sum(df, "Branch", ["TOT_REV_N", "TOT_SAL", "TOT_NS", "TOT_SC"])
        for _, r in grouped.iterrows():
            rev = float(r["TOT_REV_N"])
            sal = float(r["TOT_SAL"])
            ns = float(r["TOT_NS"])
            sc = float(r["TOT_SC"])
            surplus = rev - sal
            sal_v_rev = ((sal / rev) * 100.0) if rev > 0 else 0.0
            str_ratio = (ns / sc) if sc > 0 else 0.0
            branch_rows.append({
                "branch": str(r["Branch"]),
                "total_revenue": round(rev, 2),
                "total_salary": round(sal, 2),
                "surplus": round(surplus, 2),
                "students": int(ns),
                "employees": int(sc),
                "salary_vs_revenue_pct": round(sal_v_rev, 2),
                "student_teacher_ratio": round(str_ratio, 2),
            })

    return {
        "success": True,
        "filters": {
            "agm": agm or "All",
            "ri": ri or "All",
            "zone": zone or "All",
            "branch": branch or "All",
        },
        "kpis": kpis,
        "segment_analysis": segments,
        "charts": charts,
        "branch_analysis": branch_rows,
    }
