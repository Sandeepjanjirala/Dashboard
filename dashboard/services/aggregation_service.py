"""
Filtering + low-level aggregation over the branch DataFrame.

This module knows how to turn (agm, ri, branch) query params into a
filtered DataFrame, and how to sum/group columns. It does NOT know about
KPI business rules -- that belongs in dashboard_service.py.
"""
import pandas as pd

from dashboard.services import excel_service
from dashboard.utils import column_mapping as cm

ALL_TOKENS = {"", "all"}


class InvalidFilterError(Exception):
    """Raised when a requested AGM/RI/Branch value doesn't exist in the data."""

    def __init__(self, field, value):
        self.field = field
        self.value = value
        super().__init__(f"Unknown {field}: {value!r}")


def is_all(value) -> bool:
    """True if the filter value means 'no filter' (None, '', or 'All')."""
    return value is None or str(value).strip().lower() in ALL_TOKENS


def get_filter_options(agm=None, ri=None, zone=None, dataset_id="branch_analytics"):
    """
    Return the AGM / RI / Zone / Branch options available given the current
    (partial) selection, for cascading dropdowns.
    """
    df = excel_service.get_dataframe(dataset_id=dataset_id)

    agms = sorted(df[cm.COL_AGM].unique().tolist())

    scoped = df
    if not is_all(agm):
        if agm not in agms:
            raise InvalidFilterError("agm", agm)
        scoped = scoped[scoped[cm.COL_AGM] == agm]

    ris = sorted(scoped[cm.COL_RI].unique().tolist())

    if not is_all(ri):
        if ri not in ris:
            raise InvalidFilterError("ri", ri)
        scoped = scoped[scoped[cm.COL_RI] == ri]

    zones = sorted(scoped[cm.COL_ZONE].unique().tolist())

    if not is_all(zone):
        if zone not in zones:
            raise InvalidFilterError("zone", zone)
        scoped = scoped[scoped[cm.COL_ZONE] == zone]

    branches = sorted(scoped[cm.COL_BRANCH].unique().tolist())

    return {"agms": agms, "ris": ris, "zones": zones, "branches": branches}


def get_filtered_dataframe(agm=None, ri=None, zone=None, branch=None, dataset_id="branch_analytics") -> pd.DataFrame:
    """
    Apply the AGM -> RI -> Zone -> Branch hierarchy filter, strictly
    progressively on the specified dataset DataFrame.
    """
    df = excel_service.get_dataframe(dataset_id=dataset_id)

    df = _validate_and_filter(df, cm.COL_AGM, agm, "agm")
    df = _validate_and_filter(df, cm.COL_RI, ri, "ri")
    df = _validate_and_filter(df, cm.COL_ZONE, zone, "zone")
    df = _validate_and_filter(df, cm.COL_BRANCH, branch, "branch")

    return df



def _validate_and_filter(df: pd.DataFrame, column: str, value, field_name: str) -> pd.DataFrame:
    """
    Validate `value` against the unique values of `column` in the
    DataFrame *as already scoped by the caller* (this is what makes the
    hierarchy strict: the caller always passes in the previously-filtered
    df, never the original unfiltered one), then filter to it.

    "All" / blank / None means "no filter at this level" -- the incoming
    `df` (already scoped by whatever levels came before) is returned
    unchanged.
    """
    if is_all(value):
        return df

    valid_values = set(df[column].unique())
    if value not in valid_values:
        raise InvalidFilterError(field_name, value)

    return df[df[column] == value]


def col_sum(df: pd.DataFrame, column: str) -> float:
    """Sum a column, treating an empty (fully-filtered-out) DataFrame as 0."""
    if df.empty or column not in df.columns:
        return 0.0
    return float(df[column].sum())


def group_sum(df: pd.DataFrame, group_col: str, value_cols: list[str]) -> pd.DataFrame:
    """
    Group by `group_col` and sum each column in `value_cols`.
    Returns an empty DataFrame with the right columns if `df` is empty,
    rather than raising, so downstream code can iterate safely.
    """
    if df.empty:
        return pd.DataFrame(columns=[group_col] + value_cols)
    return df.groupby(group_col, as_index=False)[value_cols].sum()
