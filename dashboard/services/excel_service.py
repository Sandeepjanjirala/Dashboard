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
_cache = {"df": None, "mtime": None}


class ExcelDataError(Exception):
    """Raised when the workbook can't be loaded or doesn't match the expected schema."""


def _load_from_disk() -> pd.DataFrame:
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

    # Data safety: coerce numeric columns, treat blanks/NaN as 0 rather than
    # letting them propagate into aggregations as NaN.
    numeric_cols = [c for c in cm.REQUIRED_COLUMNS if c not in cm.IDENTIFIER_COLUMNS]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Data safety: strip whitespace on identifier/text columns and drop
    # fully blank rows (e.g. trailing empty Excel rows).
    for col in cm.IDENTIFIER_COLUMNS:
        df[col] = df[col].astype(str).str.strip()
    df = df[df[cm.COL_BRANCH].str.len() > 0].reset_index(drop=True)

    # Data safety: warn (don't crash) on duplicate branch names, since the
    # dashboard treats Branch as a selectable, near-unique dimension.
    dupes = df[cm.COL_BRANCH][df[cm.COL_BRANCH].duplicated()].unique().tolist()
    if dupes:
        logger.warning("Duplicate Branch values found in workbook: %s", dupes)

    logger.info("Loaded %d rows from %s", len(df), path)
    return df


def get_dataframe(force_reload: bool = False) -> pd.DataFrame:
    path = settings.EXCEL_DATA_PATH
    mtime = os.path.getmtime(path) if os.path.exists(path) else None

    with _lock:
        needs_load = (
            force_reload
            or _cache["df"] is None
            or _cache["mtime"] != mtime
        )
        if needs_load:
            _cache["df"] = _load_from_disk()
            _cache["mtime"] = mtime
        return _cache["df"]
