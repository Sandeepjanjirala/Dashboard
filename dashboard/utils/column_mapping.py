"""
Column mapping / configuration for the branch_analytics.xlsx workbook.

This is the ONLY place in the codebase that should know the literal Excel
column names. Every service builds column names through the helpers below
instead of hard-coding strings, so if the workbook's column names ever
change, this is the only file that needs updating.

Verified against the actual uploaded workbook (Sheet1, 59 rows, 146 cols).

Naming pattern used by the source Excel file:
    <CATEGORY>-<SUBGROUP>-<PERIOD>-<METRIC>      e.g. PP-E-LY-GS
    <CATEGORY>-<PERIOD>-<METRIC>                 e.g. PP-CY-GS   (E + N combined)
    <SUBGROUP>-<PERIOD>-<METRIC>                 e.g. E-CY-GS    (overall, existing only)
    <PERIOD>-<METRIC>                            e.g. CY-GS      (overall, combined)
    <CATEGORY>-<FIELD>                           e.g. PP-NOS, PP-Avg-SPS, PP-CY-STR
    <FIELD>                                      e.g. NOS, Avg-SPS, CY-STR   (overall)
    <STAFFTYPE>-<FIELD>                          e.g. AC-CY-SC, AD-LY-STR

Where:
    CATEGORY  = PP (Pre Primary) | PS (Primary School) | HS (High School)
    SUBGROUP  = E (Existing) | N (New)
    PERIOD    = LY (Last Year, 2024-25) | CY (Current Year, 2025-26)
    METRIC    = GS (Grant Strength) | DP (Dropouts) | DPP (Dropout %) | NS (Net Strength)
    STAFFTYPE = AC (Activity Staff) | AD (Administration Staff)
"""

# ---------------------------------------------------------------------------
# Identifier / hierarchy columns
# ---------------------------------------------------------------------------
COL_AGM = "AGM Name"
COL_RI = "RI Name"
COL_ZONE = "Zone"
COL_BRANCH = "Branch"

IDENTIFIER_COLUMNS = [COL_AGM, COL_RI, COL_ZONE, COL_BRANCH]

# ---------------------------------------------------------------------------
# School categories
# ---------------------------------------------------------------------------
CATEGORIES = ["PP", "PS", "HS"]

CATEGORY_LABELS = {
    "PP": "Pre Primary",
    "PS": "Primary School",
    "HS": "High School",
}

SUBGROUPS = ["E", "N"]  # E = Existing, N = New

SUBGROUP_LABELS = {
    "E": "Existing",
    "N": "New",
}

PERIODS = ["LY", "CY"]

PERIOD_LABELS = {
    "LY": "2024-25",
    "CY": "2025-26",
}

# GS = Grant Strength, DP = Dropouts, DPP = Dropout %, NS = Net Strength
STRENGTH_METRICS = ["GS", "DP", "DPP", "NS"]

# ---------------------------------------------------------------------------
# Column builders (strength/dropout block: GS / DP / DPP / NS)
# ---------------------------------------------------------------------------


def strength_col(metric, period, category=None, subgroup=None):
    """
    Build a strength/dropout column name.

    strength_col("GS", "CY")                      -> "CY-GS"          (overall, combined)
    strength_col("GS", "CY", subgroup="E")         -> "E-CY-GS"       (overall, existing)
    strength_col("GS", "CY", category="PP")        -> "PP-CY-GS"      (PP, combined)
    strength_col("GS", "CY", category="PP", subgroup="E") -> "PP-E-CY-GS"
    """
    if metric not in STRENGTH_METRICS:
        raise ValueError(f"Unknown strength metric: {metric}")
    if period not in PERIODS:
        raise ValueError(f"Unknown period: {period}")

    parts = []
    if category:
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category}")
        parts.append(category)
    if subgroup:
        if subgroup not in SUBGROUPS:
            raise ValueError(f"Unknown subgroup: {subgroup}")
        parts.append(subgroup)
    parts.append(period)
    parts.append(metric)
    return "-".join(parts)


# ---------------------------------------------------------------------------
# Category / overall "shape" fields
# NSD  = Net Strength Difference (CY-NS - LY-NS)
# NOS  = Number of Sections
# Avg-SPS = Average Students Per Section (CY-NS / NOS)
# CY-SC / LY-SC = Staff Count (current / last year) -- see README ambiguity note
# SD   = Strength Difference (CY-SC - LY-SC, i.e. staff count YoY change)
# CY-STR / LY-STR = Student Teacher Ratio (as supplied in the source data)
# ---------------------------------------------------------------------------
SHAPE_FIELDS = ["NSD", "NOS", "Avg-SPS", "CY-SC", "LY-SC", "SD", "CY-STR", "LY-STR"]


def shape_col(field, category=None):
    """
    shape_col("NOS")                 -> "NOS"        (overall)
    shape_col("NOS", category="PP")  -> "PP-NOS"
    """
    if field not in SHAPE_FIELDS:
        raise ValueError(f"Unknown shape field: {field}")
    if category:
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category}")
        return f"{category}-{field}"
    return field


# ---------------------------------------------------------------------------
# Staff (Activity / Administration) columns
# ---------------------------------------------------------------------------
STAFF_TYPES = ["AC", "AD"]

STAFF_TYPE_LABELS = {
    "AC": "Activity Staff",
    "AD": "Administration Staff",
}

STAFF_FIELDS = ["CY-SC", "LY-SC", "SD", "CY-STR", "LY-STR"]


def staff_col(staff_type, field):
    if staff_type not in STAFF_TYPES:
        raise ValueError(f"Unknown staff type: {staff_type}")
    if field not in STAFF_FIELDS:
        raise ValueError(f"Unknown staff field: {field}")
    return f"{staff_type}-{field}"


# ---------------------------------------------------------------------------
# Room columns (overall only, no category breakdown in source data)
# NOCR = Number of Class Rooms
# NOOR = Number of Occupied Rooms
# NOVR = Number of Vacancy Rooms
# ARCS = Average Room Capacity Square Feet (present in schema; all zero in
#        the current workbook -- see README ambiguity note)
# ---------------------------------------------------------------------------
COL_NOCR = "NOCR"
COL_NOOR = "NOOR"
COL_NOVR = "NOVR"
COL_ARCS = "ARCS"

ROOM_COLUMNS = [COL_NOCR, COL_NOOR, COL_NOVR, COL_ARCS]

# ---------------------------------------------------------------------------
# Convenience: frequently used overall columns
# ---------------------------------------------------------------------------
COL_NOS = shape_col("NOS")
COL_AVG_SPS = shape_col("Avg-SPS")
COL_CY_NS = strength_col("NS", "CY")
COL_LY_NS = strength_col("NS", "LY")
COL_CY_GS = strength_col("GS", "CY")
COL_LY_GS = strength_col("GS", "LY")
COL_CY_DP = strength_col("DP", "CY")
COL_LY_DP = strength_col("DP", "LY")
COL_CY_DPP = strength_col("DPP", "CY")
COL_LY_DPP = strength_col("DPP", "LY")


def build_required_columns():
    """
    Every column name this application ever references, generated from the
    same builders the services use. Used at startup to validate the
    workbook actually contains what we expect, instead of failing deep
    inside an aggregation with a confusing KeyError.
    """
    cols = set(IDENTIFIER_COLUMNS)

    for metric in STRENGTH_METRICS:
        for period in PERIODS:
            cols.add(strength_col(metric, period))
            cols.add(strength_col(metric, period, subgroup="E"))
            cols.add(strength_col(metric, period, subgroup="N"))
            for category in CATEGORIES:
                cols.add(strength_col(metric, period, category=category))
                cols.add(strength_col(metric, period, category=category, subgroup="E"))
                cols.add(strength_col(metric, period, category=category, subgroup="N"))

    for field in SHAPE_FIELDS:
        cols.add(shape_col(field))
        for category in CATEGORIES:
            cols.add(shape_col(field, category=category))

    for staff_type in STAFF_TYPES:
        for field in STAFF_FIELDS:
            cols.add(staff_col(staff_type, field))

    cols.update(ROOM_COLUMNS)
    return sorted(cols)


REQUIRED_COLUMNS = build_required_columns()
