"""
Thin HTTP client for the independent branch_query_engine_v2 service.

This module owns ALL knowledge of how to reach the query engine (base URL,
endpoint path, timeout, request/response shape). Nothing else in
branch_dashboard should know or care about those details -- the view that
uses this module only ever sees a plain dict back.

No AI/query/LLM logic lives here or anywhere else in branch_dashboard --
this is a network call to a separate service and nothing more.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class QueryEngineError(Exception):
    """Raised when the query engine can't be reached or returns something
    unexpected. Callers should catch this and turn it into a friendly
    API response rather than letting it bubble up as a 500 traceback."""


def ask(question: str, filters: dict | None = None) -> dict:
    """
    Forward `question` to branch_query_engine_v2's /api/query/ endpoint and
    return its JSON body as-is (a dict with success/answer/function/data).

    `filters` is the dashboard's current AGM/RI/branches selection (see
    dashboard.views.ask_ai_view). It's forwarded under the same "filters"
    key so the query engine can use it for filter-aware functions later;
    when omitted, the request body is just {"question": ...} exactly as
    before this parameter existed, so nothing about the existing single
    pre-function's behavior changes.

    Raises QueryEngineError on network failure, timeout, or a non-JSON /
    malformed response. A well-formed error response from the query engine
    itself (e.g. {"success": false, "answer": "..."}) is NOT an exception --
    it's returned normally so the caller can relay it to the frontend.
    """
    url = settings.QUERY_ENGINE_BASE_URL.rstrip("/") + "/api/query/"

    payload = {"question": question}
    if filters:
        payload["filters"] = filters

    try:
        resp = requests.post(
            url,
            json=payload,
            timeout=settings.QUERY_ENGINE_TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout as exc:
        logger.warning("Query engine timed out for question=%r", question)
        raise QueryEngineError("The AI assistant took too long to respond. Please try again.") from exc
    except requests.exceptions.ConnectionError as exc:
        logger.warning("Query engine unreachable at %s: %s", url, exc)
        raise QueryEngineError("The AI assistant is currently unavailable.") from exc
    except requests.exceptions.RequestException as exc:
        logger.exception("Unexpected error calling query engine")
        raise QueryEngineError("The AI assistant could not process this request.") from exc

    try:
        body = resp.json()
    except ValueError as exc:
        logger.exception("Query engine returned non-JSON response (status=%s)", resp.status_code)
        raise QueryEngineError("The AI assistant returned an unreadable response.") from exc

    # The query engine returns a well-formed {"success": false, "answer": ...}
    # body for both routing misses (400) and internal errors (500) -- that's
    # valid data to relay, not a transport failure, so we don't raise here.
    return body
