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
    'statistics', 'statistic', 'stats', 'analyze', 'analysis', 'review', 'performance', 'health',
    'top', 'bottom', 'highest', 'lowest', 'best', 'worst', 'how many',
    'which', 'what is', 'what was', 'what are', 'how much', 'compare', 'comparison', 'rank',
    'ranking', 'average', 'total', 'sum', 'balance', 'percentage', 'dropout',
    'dropout %', 'strength', 'ratio', 'staff', 'rooms', 'sections',
    'fee', 'fees', 'fee due', 'zero paid', 'zero-paid', 'due count', 'books',
    'revenue', 'salary', 'surplus', 'cost per student', 'fee average', 'employee count', 'employee salary', 'employee cost', 'total employees',
    'school level', 'education level',
    'year over year', 'yoy', 'cy vs ly', 'trend', 'improved', 'declined',
    'increased', 'decreased', 'changed', 'threshold', 'above', 'below',
    'more than', 'less than', 'vs', 'versus', 'scorecard', 'overview',
    'snapshot', 'summary', 'complete summary', 'report', 'full report',
    'details', 'profile', 'card', 'breakdown',
)

# Phrases that, when present together with a filter entity, indicate HYBRID
# intent (filter + query).
_HYBRID_METRIC_WORDS = (
    'statistics', 'statistic', 'stats', 'analyze', 'analysis', 'review', 'performance', 'health',
    'dropout', 'strength', 'ratio', 'staff', 'rooms', 'sections',
    'fee', 'fees', 'fee due', 'zero paid', 'zero-paid', 'due count', 'books', 'balance',
    'revenue', 'salary', 'surplus', 'cost per student', 'fee average', 'employee count', 'employee salary', 'employee cost', 'total employees',
    'school level', 'education level',
    'percentage', '%', 'scorecard', 'overview', 'snapshot', 'summary',
    'report', 'details', 'breakdown', 'profile', 'how many', 'what is', 'what was', 'how much', 'total',
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
NUMBER_WORDS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
    'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11,
    'twelve': 12, 'fifteen': 15, 'twenty': 20,
}


def normalize_entity_name(s: str) -> str:
    """Normalize text for entity matching: lowercase, strip honorifics, strip punctuation, collapse spaces, convert word numbers to digits."""
    if not s:
        return ""
    s = str(s).lower().strip()
    s = re.sub(r'^(mr\.|mr\s+|mrs\.|mrs\s+|dr\.|dr\s+)', '', s)
    s = re.sub(r'[._\-,]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    words = s.split()
    converted = [str(NUMBER_WORDS[w]) if w in NUMBER_WORDS else w for w in words]
    return ' '.join(converted)


def resolve_single_entity(query_text: str, candidate_entities: list[str], entity_type: str = 'branch') -> str | None:
    """
    Resolves the intended entity from `query_text` against `candidate_entities`.
    Returns the exact canonical string from `candidate_entities` if matched, else None.
    
    Priority Matching:
    1. Exact normalized phrase match in query (longest match wins).
    2. High-confidence fuzzy match (>= 80%).
    3. Moderate-confidence fuzzy match (70-79%) if single clear winner.
    """
    candidates = [str(c).strip() for c in candidate_entities if c and str(c).strip()]
    if not candidates:
        return None

    norm_q = normalize_entity_name(query_text)
    if not norm_q:
        return None
    
    query_digits = set(re.findall(r'\b\d+\b', norm_q))

    # Step A: Exact / Word-Boundary Phrase Match (Longest Wins)
    exact_matches = []
    for raw_cand in candidates:
        norm_cand = normalize_entity_name(raw_cand)
        if not norm_cand:
            continue
        
        cand_digits = set(re.findall(r'\b\d+\b', norm_cand))
        if cand_digits and not cand_digits.issubset(query_digits):
            continue

        pattern = r'\b' + re.escape(norm_cand) + r'\b'
        if re.search(pattern, norm_q):
            exact_matches.append((raw_cand, norm_cand, len(norm_cand)))

    if exact_matches:
        exact_matches.sort(key=lambda x: x[2], reverse=True)
        return exact_matches[0][0]

    # For person names (RI / AGM), check strategy for token-set match
    if entity_type in ('ri', 'agm'):
        person_matches = []
        for raw_cand in candidates:
            norm_cand = normalize_entity_name(raw_cand)
            cand_digits = set(re.findall(r'\b\d+\b', norm_cand))
            if cand_digits and not cand_digits.issubset(query_digits):
                continue
            tokens = [t for t in norm_cand.split() if len(t) > 1]
            if tokens and all(re.search(r'\b' + re.escape(t) + r'\b', norm_q) for t in tokens):
                person_matches.append((raw_cand, len(norm_cand)))
        if person_matches:
            person_matches.sort(key=lambda x: x[1], reverse=True)
            return person_matches[0][0]

    # Step B & C: Fuzzy Matching
    stopwords = {
        'statistics', 'statistic', 'stats', 'show', 'give', 'of', 'branch', 'branches',
        'ri', 'ris', 'agm', 'agms', 'zone', 'zones', 'the', 'analyze', 'analysis',
        'review', 'performance', 'summary', 'scorecard', 'report', 'details', 'for',
        'in', 'at', 'please', 'me', 'what', 'is', 'are', 'highest', 'lowest', 'top'
    }
    q_words = [w for w in norm_q.split() if w not in stopwords]
    clean_q = ' '.join(q_words).strip()
    
    if not clean_q:
        return None

    scores = []
    for raw_cand in candidates:
        norm_cand = normalize_entity_name(raw_cand)
        if not norm_cand:
            continue
        
        cand_digits = set(re.findall(r'\b\d+\b', norm_cand))
        if cand_digits and not cand_digits.issubset(query_digits):
            continue

        ratio = difflib.SequenceMatcher(None, clean_q, norm_cand).ratio()
        
        cand_tokens = norm_cand.split()
        if len(q_words) == 1:
            w = q_words[0]
            for ct in cand_tokens:
                token_ratio = difflib.SequenceMatcher(None, w, ct).ratio()
                if token_ratio > ratio:
                    ratio = token_ratio
        
        scores.append((raw_cand, ratio))

    scores.sort(key=lambda x: x[1], reverse=True)

    if not scores:
        return None

    best_cand, best_score = scores[0]
    second_score = scores[1][1] if len(scores) > 1 else 0.0

    if best_score >= 0.80:
        return best_cand

    if 0.70 <= best_score < 0.80:
        if (best_score - second_score) >= 0.10:
            return best_cand

    return None


def _match_branches_in_question(q: str, branches: list[str]) -> list[str]:
    res = resolve_single_entity(q, branches, 'branch')
    return [res] if res else []


def _match_ris(q: str, ris: list[str]) -> list[str]:
    res = resolve_single_entity(q, ris, 'ri')
    return [res] if res else []


def _match_dimension(q: str, candidates: list[str]) -> list[str]:
    res = resolve_single_entity(q, candidates, 'zone')
    return [res] if res else []


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
    matched_agms = _match_ris(q, agms) or _match_dimension(q, agms)
    matched_ris = _match_ris(q, ris)
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
