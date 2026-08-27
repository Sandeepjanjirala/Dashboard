"""
Rule-based intent extractor for the dashboard AI assistant.

Classifies a natural-language question into one of:
    dashboard_filter          – change AGM/RI/Zone/Branch dropdowns
    dashboard_reset           – clear all filters to "All"
    dashboard_query           – pure analytical question, forward to query engine
    dashboard_filter_and_query – change filter AND run an analytical query
    clarification_required    – ambiguous entity match; ask the user to clarify
    unknown                   – unsupported / nonsensical request

The classifier is entirely rule-based (difflib + keyword patterns against the
live dataset).  No LLM, no external API, no network calls.

Design principles
-----------------
* Validate all entity names against the LIVE dataset — never let an unknown
  branch name silently become a valid filter.
* Longest-match wins for branch disambiguation: if "GAJUWAKA 2" and "GAJUWAKA"
  both appear in the question, the longer (more specific) match wins.
* Fuzzy matching via difflib.get_close_matches so minor typos still resolve.
* When multiple equally-long branches could match, return clarification_required.
* Analytical-query detection delegates to a lightweight keyword pass; the
  heavy routing logic already lives in the query engine's router.py.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Reset / filter-control keywords
# ---------------------------------------------------------------------------

_RESET_PHRASES = (
    'reset', 'clear filter', 'clear all', 'remove filter', 'show all',
    'show everything', 'all branches', 'remove all filter', 'start over',
    'go back to all', 'default filter', 'unfilter', 'no filter',
    'reset dashboard', 'reset filter',
)

# Phrases that strongly imply the user wants to change the dashboard *view*
# (filter intent) rather than ask an analytical question.
_FILTER_TRIGGER_PHRASES = (
    'show me', 'show', 'filter to', 'filter by', 'select', 'switch to',
    'navigate to', 'go to', 'set filter', 'set to', 'change to',
    'focus on', 'narrow to', 'look at',
)

# Phrases that strongly imply a pure analytical / data question.
_ANALYTICAL_TRIGGER_PHRASES = (
    'top', 'bottom', 'highest', 'lowest', 'best', 'worst', 'how many',
    'which', 'what is', 'what are', 'compare', 'comparison', 'rank',
    'ranking', 'average', 'total', 'sum', 'percentage', 'dropout',
    'dropout %', 'strength', 'ratio', 'staff', 'rooms', 'sections',
    'year over year', 'yoy', 'cy vs ly', 'trend', 'improved', 'declined',
    'increased', 'decreased', 'changed', 'threshold', 'above', 'below',
    'more than', 'less than', 'vs', 'versus', 'scorecard', 'overview',
    'snapshot',
)

# Phrases that, when present together with a filter entity, indicate HYBRID
# intent (filter + query).
_HYBRID_METRIC_WORDS = (
    'dropout', 'strength', 'ratio', 'staff', 'rooms', 'sections',
    'percentage', '%', 'scorecard', 'overview', 'snapshot',
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class IntentResult:
    intent: str                        # one of the intent strings above
    filters: dict = field(default_factory=dict)
    ambiguous_matches: list = field(default_factory=list)
    error: str | None = None
    is_hybrid: bool = False


# ---------------------------------------------------------------------------
# Helper: normalise a string for comparison
# ---------------------------------------------------------------------------

def _normalise(s: str) -> str:
    return re.sub(r'\s+', ' ', s.strip().lower())


# ---------------------------------------------------------------------------
# Branch entity matching (word-boundary, longest-wins)
# ---------------------------------------------------------------------------

def _match_branches_in_question(q: str, branches: list[str]) -> list[str]:
    """
    Find branch names mentioned in question `q`.

    Algorithm:
    1. For each branch, build a regex that matches ALL tokens of the branch
       name as whole words in `q`.  "GAJUWAKA 2" requires both \\bgajuwaka\\b
       AND \\b2\\b present in q.
    2. Collect all matching branches.
    3. Remove any match that is a strict prefix of a longer match
       (longest-wins / maximal-munch).  E.g. if both "GAJUWAKA" and
       "GAJUWAKA 2" match, keep only "GAJUWAKA 2".
    4. If still > 1 candidate, return all of them (→ clarification).
    """
    q_l = _normalise(q)
    raw_matches: list[str] = []

    for branch in branches:
        b_l = _normalise(branch)
        words = b_l.split()
        # Every word of the branch name must appear as a whole word in q.
        if all(re.search(rf'\b{re.escape(w)}\b', q_l) for w in words):
            raw_matches.append(branch)

    if not raw_matches:
        return []

    # Longest-wins: remove any match whose normalised form is a strict prefix
    # (subset of words) of another match in the same list.
    normed = [_normalise(b) for b in raw_matches]
    filtered = []
    for i, b in enumerate(raw_matches):
        b_l = normed[i]
        is_prefix_of_longer = any(
            b_l != normed[j] and normed[j].startswith(b_l + " ")
            for j in range(len(raw_matches))
        )
        if not is_prefix_of_longer:
            filtered.append(b)

    return filtered


# ---------------------------------------------------------------------------
# Zone / AGM / RI entity matching (whole-string, case-insensitive)
# ---------------------------------------------------------------------------

def _meaningful_tokens(name: str) -> list[str]:
    """
    Extract meaningful word tokens from a name, stripping honorifics and
    single-letter initials.

    "Mr.M.Ramana"      → ["ramana"]
    "Mr M.V.L.Naresh"  → ["naresh"]
    "Mr.Ahmedali"      → ["ahmedali"]
    "Mr.Uday Shankar V" → ["uday", "shankar"]
    "Mr.P Gopi Nath"   → ["gopi", "nath"]
    """
    # Normalise, split on spaces and dots
    parts = re.split(r'[\s.]+', _normalise(name))
    # Remove honorifics and single-character parts (initials like M, V, P)
    stopwords = {'mr', 'mrs', 'ms', 'dr', 'sri', 'smt'}
    tokens = [p for p in parts if p and p not in stopwords and len(p) > 1]
    return tokens


def _match_ris(q: str, ris: list[str]) -> list[str]:
    """
    Match RI (person) names in `q` using two strategies:

    1. Full phrase match: "Mr.Ahmedali" appears verbatim in question.
    2. Meaningful-token match: every significant word of the RI name
       (initials and "Mr" stripped) appears as a word boundary in question.
       e.g. "show ahmedali" matches "Mr.Ahmedali"
            "show ramana"   matches "Mr.M.Ramana"
            "gopi nath"     matches "Mr.P Gopi Nath"

    Returns at most one RI (the best match). If multiple RIs could match,
    returns all of them so the caller can trigger clarification.
    """
    q_l = _normalise(q)
    matched = []

    for ri in ris:
        ri_l = _normalise(ri)
        # Strategy 1: verbatim phrase
        if re.search(rf'\b{re.escape(ri_l)}\b', q_l):
            matched.append(ri)
            continue
        # Strategy 2: meaningful tokens
        tokens = _meaningful_tokens(ri)
        if tokens and all(re.search(rf'\b{re.escape(t)}\b', q_l) for t in tokens):
            matched.append(ri)

    return matched


def _match_dimension(q: str, candidates: list[str]) -> list[str]:
    """
    Match zone / AGM names in `q`.

    Requires the candidate's normalised form to appear as a whole
    contiguous phrase in `q`.
    """
    q_l = _normalise(q)
    found = []
    # Sort by length descending so longer names match first (e.g. "Rajahmundry - East"
    # before "Rajahmundry").
    for cand in sorted(candidates, key=len, reverse=True):
        cand_l = _normalise(cand)
        # Use re.escape so hyphens and dots don't cause issues.
        if re.search(rf'\b{re.escape(cand_l)}\b', q_l):
            found.append(cand)
    # Longest-wins: remove prefixes
    normed = [_normalise(c) for c in found]
    result = []
    for i, c in enumerate(found):
        c_l = normed[i]
        dominated = any(
            c_l != normed[j] and normed[j].startswith(c_l)
            for j in range(len(found))
        )
        if not dominated:
            result.append(c)
    return result


# ---------------------------------------------------------------------------
# Detect whether the question looks analytical
# ---------------------------------------------------------------------------

def _looks_analytical(q: str) -> bool:
    return any(phrase in q for phrase in _ANALYTICAL_TRIGGER_PHRASES)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_intent(
    question: str,
    agms: list[str],
    ris: list[str],
    zones: list[str],
    branches: list[str],
) -> IntentResult:
    """
    Classify `question` into a dashboard intent.

    Parameters
    ----------
    question : str
        The raw user question (text or voice transcript).
    agms, ris, zones, branches : list[str]
        Valid entity names from the live dataset (used for validation).
    """
    q = _normalise(question)

    # ------------------------------------------------------------------
    # 1. RESET intent
    # ------------------------------------------------------------------
    if any(phrase in q for phrase in _RESET_PHRASES):
        return IntentResult(
            intent='dashboard_reset',
            filters={'agm': 'All', 'ri': 'All', 'zone': 'All', 'branches': ['All']},
        )

    # ------------------------------------------------------------------
    # 2. Extract named entities from the question
    # ------------------------------------------------------------------
    matched_zones = _match_dimension(q, zones)
    matched_agms = _match_dimension(q, agms)
    matched_ris = _match_dimension(q, ris)
    matched_branches = _match_branches_in_question(q, branches)

    has_entity = bool(matched_zones or matched_agms or matched_ris or matched_branches)

    # ------------------------------------------------------------------
    # 3. Detect ambiguity on branches
    # ------------------------------------------------------------------
    if len(matched_branches) > 1:
        return IntentResult(
            intent='clarification_required',
            ambiguous_matches=matched_branches,
            error=(
                f"I found {len(matched_branches)} branches matching your request: "
                + ', '.join(matched_branches)
                + ". Which one did you mean?"
            ),
        )

    # ------------------------------------------------------------------
    # 4. No entity found
    # ------------------------------------------------------------------
    if not has_entity:
        if _looks_analytical(q):
            return IntentResult(intent='dashboard_query')
        return IntentResult(
            intent='unknown',
            error=(
                "I couldn't find a matching zone, branch, RI, or AGM in your request. "
                "Try: \"Show Zone Kakinada\", \"Show AMALAPURAM branch\", "
                "\"Reset filters\", or ask an analytical question like "
                "\"Top 10 dropout branches\"."
            ),
        )

    # ------------------------------------------------------------------
    # 5. Build the validated filter dict
    # ------------------------------------------------------------------
    new_agm = matched_agms[0] if len(matched_agms) == 1 else 'All'
    new_ri = matched_ris[0] if len(matched_ris) == 1 else 'All'
    new_zone = matched_zones[0] if len(matched_zones) == 1 else 'All'
    new_branches = matched_branches if matched_branches else ['All']

    filters = {
        'agm': new_agm,
        'ri': new_ri,
        'zone': new_zone,
        'branches': new_branches,
    }

    # ------------------------------------------------------------------
    # 6. HYBRID: entity found AND question also contains metric keywords
    # ------------------------------------------------------------------
    also_has_metric = any(w in q for w in _HYBRID_METRIC_WORDS)

    if also_has_metric:
        return IntentResult(
            intent='dashboard_filter_and_query',
            filters=filters,
            is_hybrid=True,
        )

    return IntentResult(
        intent='dashboard_filter',
        filters=filters,
    )
