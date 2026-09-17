import logging

from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from dashboard.serializers import AskAiRequestSerializer, DashboardFilterQuerySerializer
from dashboard.services import aggregation_service as agg
from dashboard.services import dashboard_service
from dashboard.services import query_engine_client
from dashboard.services.excel_service import ExcelDataError

logger = logging.getLogger(__name__)


def dashboard_page(request):
    """
    GET /

    Serves the Phase 2 HTML/CSS/jQuery dashboard shell. This view renders
    only static markup -- every number on the page is filled in client-side
    by dashboard.js calling the JSON endpoints below.
    """
    return render(request, "dashboard/index.html")


from dashboard.services import fee_due_service


@api_view(["GET"])
def filters_view(request):
    """
    GET /api/dashboard/filters/?agm=&ri=&zone=&dataset=

    Returns the AGM / RI / Branch options available for the current
    (partial) selection, so the frontend can populate cascading dropdowns.
    """
    query = DashboardFilterQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    agm = query.validated_data.get("agm", "")
    ri = query.validated_data.get("ri", "")
    zone = query.validated_data.get("zone", "")
    dataset_id = query.validated_data.get("dataset", "branch_analytics")

    try:
        options = agg.get_filter_options(agm=agm, ri=ri, zone=zone, dataset_id=dataset_id)
    except agg.InvalidFilterError as exc:
        return Response(
            {"success": False, "error": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except ExcelDataError as exc:
        logger.exception("Excel data error while building filters")
        return Response(
            {"success": False, "error": f"Data source error: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({"success": True, **options})


@api_view(["GET"])
def dashboard_view(request):
    """
    GET /api/dashboard/?agm=&ri=&branch=

    Returns the full dashboard payload for Main Report (Dropouts & Staff Ratio)
    for the given filter selection.
    """
    query = DashboardFilterQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    agm = query.validated_data.get("agm", "")
    ri = query.validated_data.get("ri", "")
    zone = query.validated_data.get("zone", "")
    branch = query.validated_data.get("branch", "")

    try:
        payload = dashboard_service.build_dashboard_response(agm=agm, ri=ri, zone=zone, branch=branch)
    except agg.InvalidFilterError as exc:
        return Response(
            {"success": False, "error": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except ExcelDataError as exc:
        logger.exception("Excel data error while building dashboard")
        return Response(
            {"success": False, "error": f"Data source error: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(payload)


@api_view(["GET"])
def fee_due_dashboard_view(request):
    """
    GET /api/dashboard/fee-due/?agm=&ri=&zone=&branch=

    Returns the full dashboard payload for Fee Due Analysis Dashboard
    (8 KPIs, 6 charts, breakdowns, key insights) for the given filter selection.
    """
    query = DashboardFilterQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    agm = query.validated_data.get("agm", "")
    ri = query.validated_data.get("ri", "")
    zone = query.validated_data.get("zone", "")
    branch = query.validated_data.get("branch", "")

    try:
        payload = fee_due_service.build_fee_due_dashboard_response(agm=agm, ri=ri, zone=zone, branch=branch)
    except agg.InvalidFilterError as exc:
        return Response(
            {"success": False, "error": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except ExcelDataError as exc:
        logger.exception("Excel data error while building Fee Due dashboard")
        return Response(
            {"success": False, "error": f"Data source error: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(payload)


from dashboard.services import revenue_salary_service


@api_view(["GET"])
def revenue_salary_dashboard_view(request):
    """
    GET /api/dashboard/revenue-vs-salary/?agm=&ri=&zone=&branch=

    Returns the full dashboard payload for Revenue vs Salary Analysis Dashboard
    (KPIs, segment breakdowns, top branch rankings, chart metrics) for the given filter selection.
    """
    query = DashboardFilterQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    agm = query.validated_data.get("agm", "")
    ri = query.validated_data.get("ri", "")
    zone = query.validated_data.get("zone", "")
    branch = query.validated_data.get("branch", "")

    try:
        payload = revenue_salary_service.build_revenue_salary_dashboard_response(agm=agm, ri=ri, zone=zone, branch=branch)
    except agg.InvalidFilterError as exc:
        return Response(
            {"success": False, "error": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except ExcelDataError as exc:
        logger.exception("Excel data error while building Revenue vs Salary dashboard")
        return Response(
            {"success": False, "error": f"Data source error: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(payload)



# ---------------------------------------------------------------------------
# AI Assistant helpers
# ---------------------------------------------------------------------------

def _build_filter_context(filters: dict) -> dict:
    """Normalise a raw filters dict into a complete, predictable context."""
    return {
        "agm": filters.get("agm") or "All",
        "ri": filters.get("ri") or "All",
        "zone": filters.get("zone") or "All",
        "branches": filters.get("branches") or ["All"],
    }


def _describe_filter_change(new_filters: dict) -> str:
    """Build a human-readable confirmation sentence for a filter change."""
    parts = []
    if new_filters.get("agm") and new_filters["agm"] != "All":
        parts.append(f"AGM: {new_filters['agm']}")
    if new_filters.get("ri") and new_filters["ri"] != "All":
        parts.append(f"RI: {new_filters['ri']}")
    if new_filters.get("zone") and new_filters["zone"] != "All":
        parts.append(f"Zone: {new_filters['zone']}")
    branches = [b for b in (new_filters.get("branches") or []) if b != "All"]
    if branches:
        parts.append("Branch: " + ", ".join(branches))
    if not parts:
        return "Done. Showing all data."
    return "Done. Dashboard filtered to: " + " | ".join(parts) + "."


@api_view(["POST"])
def ask_ai_view(request):
    """
    POST /api/dashboard/ask-ai/
    Body: {"question": "...", "filters": {...}}

    Extended flow:
    1. Run the rule-based IntentExtractor to classify the question.
    2. If dashboard_filter / dashboard_reset: return a structured command
       response so the JS can update the dropdowns without calling the
       query engine.
    3. If dashboard_query: forward to query_engine_client.ask() as before.
    4. If dashboard_filter_and_query (hybrid): return the filter command
       AND the query engine result together.
    5. If clarification_required / unknown: return the error message.

    All existing callers that only check `answer`, `data`, and `function`
    continue to work unchanged -- the new `intent` and `command` keys are
    additive.
    """
    query = AskAiRequestSerializer(data=request.data)
    query.is_valid(raise_exception=True)
    question = query.validated_data["question"]

    # Normalise current dashboard filter context (sent by the frontend).
    raw_filters = query.validated_data.get("filters") or {}
    filter_context = _build_filter_context(raw_filters)

    # ------------------------------------------------------------------
    # Step 1: classify intent
    # ------------------------------------------------------------------
    intent_result = None
    try:
        from dashboard.services.intent_extractor import extract_intent

        all_options = agg.get_filter_options()
        intent_result = extract_intent(
            question=question,
            agms=all_options["agms"],
            ris=all_options["ris"],
            zones=all_options["zones"],
            branches=all_options["branches"],
        )
    except ExcelDataError as exc:
        logger.exception("Excel data error during intent extraction")
    except Exception as exc:
        logger.exception("Unexpected error during intent extraction: %s", exc)

    # ------------------------------------------------------------------
    # Step 2a: RESET
    # ------------------------------------------------------------------
    if intent_result and intent_result.intent == "dashboard_reset":
        return Response({
            "success": True,
            "intent": "dashboard_reset",
            "command": {"filters": intent_result.filters},
            "answer": "Filters cleared. Showing all data.",
            "data": None,
            "function": None,
        })

    # ------------------------------------------------------------------
    # Step 2b: Clarification required
    # ------------------------------------------------------------------
    if intent_result and intent_result.intent == "clarification_required":
        return Response({
            "success": True,
            "intent": "clarification_required",
            "command": None,
            "answer": intent_result.error,
            "data": None,
            "function": None,
        })

    # ------------------------------------------------------------------
    # Step 2c: Unknown / unsupported
    # ------------------------------------------------------------------
    if intent_result and intent_result.intent == "unknown":
        return Response({
            "success": False,
            "intent": "unknown",
            "command": None,
            "answer": (
                intent_result.error
                or "I can't answer that from the current dashboard data."
            ),
            "data": None,
            "function": None,
        }, status=status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------
    # Step 2d: Filter-only (no analytical query needed)
    # ------------------------------------------------------------------
    if intent_result and intent_result.intent == "dashboard_filter":
        answer = _describe_filter_change(intent_result.filters)
        return Response({
            "success": True,
            "intent": "dashboard_filter",
            "command": {"filters": intent_result.filters},
            "answer": answer,
            "data": None,
            "function": None,
        })

    # ------------------------------------------------------------------
    # Step 2e: Hybrid (filter + query) or pure analytical query
    # ------------------------------------------------------------------
    # For hybrid intent, merge the AI-detected filters into the context
    # so the query engine answers scoped to the new selection.
    if intent_result and intent_result.intent == "dashboard_filter_and_query":
        effective_context = _build_filter_context(intent_result.filters)
        filter_cmd = {"filters": intent_result.filters}
        intent_label = "dashboard_filter_and_query"
    else:
        # dashboard_query or intent_result is None (fallback to query engine)
        effective_context = filter_context
        filter_cmd = None
        intent_label = "dashboard_query"

    try:
        result = query_engine_client.ask(question, filters=effective_context)
    except query_engine_client.QueryEngineError as exc:
        logger.warning("Query engine call failed: %s", exc)
        return Response(
            {"success": False, "answer": str(exc), "function": None},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    http_status = status.HTTP_200_OK if result.get("success") else status.HTTP_400_BAD_REQUEST
    return Response({
        **result,
        "intent": intent_label,
        "command": filter_cmd,
    }, status=http_status)


from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import parser_classes


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def transcribe_view(request):
    """
    POST /api/dashboard/transcribe/
    Proxies audio recording to the query engine's local faster-whisper service.
    """
    audio_file = request.FILES.get("audio") or request.FILES.get("file")
    if not audio_file:
        return Response(
            {"success": False, "error": "No audio file provided. Please try speaking again."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if audio_file.size == 0:
        return Response(
            {"success": False, "error": "Audio recording is empty. Please try speaking again."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    content_type = getattr(audio_file, "content_type", "") or "audio/webm"

    try:
        res = query_engine_client.transcribe(audio_file, content_type=content_type)
        return Response(res)
    except query_engine_client.QueryEngineError as exc:
        return Response(
            {"success": False, "error": str(exc)},
            status=status.HTTP_502_BAD_GATEWAY,
        )

