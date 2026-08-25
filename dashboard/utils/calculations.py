"""
Pure, dependency-light calculation helpers shared by the aggregation and
dashboard services. Nothing here touches pandas DataFrames directly -- it
operates on plain numbers so it stays easy to unit test.
"""
import math

import numpy as np


def to_json_safe(value, decimals=None):
    """
    Convert numpy/pandas scalar types into plain Python types that are safe
    to pass to json.dumps / DRF's Response. NaN and Inf become None so the
    frontend never receives invalid JSON.
    """
    if value is None:
        return None

    if isinstance(value, (np.integer,)):
        value = int(value)
    elif isinstance(value, (np.floating,)):
        value = float(value)
    elif isinstance(value, np.bool_):
        value = bool(value)

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        if decimals is not None:
            value = round(value, decimals)
        return value

    if isinstance(value, int):
        return value

    return value


def safe_div(numerator, denominator, default=0.0):
    """
    Division that never raises and never produces NaN/Inf.
    Returns `default` when the denominator is zero, missing, or NaN.
    """
    try:
        numerator = float(numerator)
        denominator = float(denominator)
    except (TypeError, ValueError):
        return default

    if denominator == 0 or math.isnan(denominator) or math.isnan(numerator):
        return default

    result = numerator / denominator
    if math.isinf(result) or math.isnan(result):
        return default
    return result


def safe_pct(numerator, denominator, decimals=1, default=0.0):
    """Percentage = numerator / denominator * 100, JSON-safe and rounded."""
    result = safe_div(numerator, denominator, default=default) * 100
    return to_json_safe(result, decimals=decimals)


def safe_round(value, decimals=1):
    return to_json_safe(value, decimals=decimals)


def safe_diff(a, b):
    """a - b, JSON-safe. Used for YoY difference cards (e.g. staff SD)."""
    try:
        return to_json_safe(float(a) - float(b))
    except (TypeError, ValueError):
        return None
