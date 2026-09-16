"""
Loads branch_analytics.xlsx into a pandas DataFrame and caches it in memory
so we don't re-read the workbook from disk on every API request.

The cache is invalidated automatically if the file's mtime changes on disk
(handy in development -- overwrite the workbook and the next request just
picks up the new data). Call `get_dataframe(force_reload=True)` to bust the
cache explicitly.

When this project eventually moves the data into PostgreSQL, this module is
the only place that needs to change -- everything downstream (aggregation
services, views) only calls `get_dataframe()` and doesn't know or care
whether the data came from Excel or a database.
"""
import logging
import os
import threading

import pandas as pd
from django.conf import settings

from dashboard.utils import column_mapping as cm

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_caches = {}  # dataset_id -> {"df": df, "mtime": mtime}

FEE_DUE_REQUIRED_COLUMNS = [
    "AGM Name", "RI Name", "Zone", "Branch", "S_Type",
    "LY_FD", "LY_FDC", "CY_A_FD", "CY_A_FDC",
    "CY_A_ZP", "CY_ZP", "CY_ZP_FD", "CY_FP_BN", "CY_FN_BN"
]


class ExcelDataError(Exception):
    """Raised when the workbook can't be loaded or doesn't match the expected schema."""


def _load_branch_analytics_from_disk() -> pd.DataFrame:
    path = settings.EXCEL_DATA_PATH
    if not os.path.exists(path):
        raise ExcelDataError(f"Excel data file not found at {path}")

    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]

    missing = [c for c in cm.REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ExcelDataError(
            "Excel workbook is missing expected columns: " + ", ".join(missing)
        )

    numeric_cols = [c for c in cm.REQUIRED_COLUMNS if c not in cm.IDENTIFIER_COLUMNS]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    for col in cm.IDENTIFIER_COLUMNS:
        df[col] = df[col].astype(str).str.strip()
    df = df[df[cm.COL_BRANCH].str.len() > 0].reset_index(drop=True)

    dupes = df[cm.COL_BRANCH][df[cm.COL_BRANCH].duplicated()].unique().tolist()
    if dupes:
        logger.warning("Duplicate Branch values found in workbook: %s", dupes)

    logger.info("Loaded %d rows from %s", len(df), path)
    return df


def _load_fee_due_from_disk() -> pd.DataFrame:
    path = getattr(settings, "FEE_DUE_DATA_PATH", settings.BASE_DIR / "data" / "fee due.xlsx")
    if not os.path.exists(path):
        raise ExcelDataError(f"Fee Due Excel file not found at {path}")

    df = pd.read_excel(path, sheet_name=0)
    df.columns = [str(c).strip() for c in df.columns]

    # Normalize standard dimension header names
    col_rename = {
        "AGM_Name": "AGM Name",
        "RI_Name": "RI Name",
        "Branch_Name": "Branch",
    }
    df = df.rename(columns=col_rename)

    missing = [c for c in FEE_DUE_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ExcelDataError(
            "Fee Due workbook is missing expected columns: " + ", ".join(missing)
        )

    # Standardize identifier columns
    id_cols = ["AGM Name", "RI Name", "Zone", "Branch", "S_Type"]
    for col in id_cols:
        df[col] = df[col].astype(str).str.strip()

    # Numeric columns
    num_cols = [c for c in FEE_DUE_REQUIRED_COLUMNS if c not in id_cols]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df = df[df["Branch"].str.len() > 0].reset_index(drop=True)
    logger.info("Loaded %d rows from %s", len(df), path)
    return df


def _load_revenue_salary_from_disk() -> pd.DataFrame:
    path = getattr(settings, "REVENUE_VS_SALARY_DATA_PATH", settings.BASE_DIR / "data" / "Revenue vs salary.xlsx")
    if not os.path.exists(path):
        raise ExcelDataError(f"Revenue vs Salary Excel file not found at {path}")

    try:
        df = pd.read_excel(path, sheet_name="Anys_Rev_vs_Sal")
    except Exception:
        df = pd.read_excel(path, sheet_name=0)

    df.columns = [str(c).strip() for c in df.columns]

    col_rename = {
        "AGM_Name": "AGM Name",
        "RI_Name": "RI Name",
        "Branch_Name": "Branch",
    }
    df = df.rename(columns=col_rename)

    id_cols = ["AGM Name", "RI Name", "Zone", "Branch", "S_Type"]
    for col in id_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    num_cols = [c for c in df.columns if c not in id_cols]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    if "Branch" in df.columns:
        df = df[df["Branch"].str.len() > 0].reset_index(drop=True)
    logger.info("Loaded %d rows from %s", len(df), path)
    return df


def get_dataframe(dataset_id: str = "branch_analytics", force_reload: bool = False) -> pd.DataFrame:
    """
    Returns cached DataFrame for the given dataset_id ('branch_analytics', 'fee_due', or 'revenue_vs_salary').
    Auto-invalidates cache if workbook mtime changes on disk.
    """
    if dataset_id in ("fee_due", "fee", "fee_analysis"):
        path = getattr(settings, "FEE_DUE_DATA_PATH", settings.BASE_DIR / "data" / "fee due.xlsx")
        loader_fn = _load_fee_due_from_disk
        key = "fee_due"
    elif dataset_id in ("revenue_vs_salary", "revenue_salary", "rev_sal"):
        path = getattr(settings, "REVENUE_VS_SALARY_DATA_PATH", settings.BASE_DIR / "data" / "Revenue vs salary.xlsx")
        loader_fn = _load_revenue_salary_from_disk
        key = "revenue_vs_salary"
    else:
        path = settings.EXCEL_DATA_PATH
        loader_fn = _load_branch_analytics_from_disk
        key = "branch_analytics"

    mtime = os.path.getmtime(path) if os.path.exists(path) else None

    with _lock:
        cache_entry = _caches.get(key)
        needs_load = (
            force_reload
            or cache_entry is None
            or cache_entry.get("mtime") != mtime
        )
        if needs_load:
            df = loader_fn()
            _caches[key] = {"df": df, "mtime": mtime}
        return _caches[key]["df"]

