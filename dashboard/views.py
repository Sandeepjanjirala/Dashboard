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


@api_view(["GET"])
def filters_view(request):
    """
    GET /api/dashboard/filters/?agm=&ri=

    Returns the AGM / RI / Branch options available for the current
    (partial) selection, so the frontend can populate cascading dropdowns.
    """
    query = DashboardFilterQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    agm = query.validated_data.get("agm", "")
    ri = query.validated_data.get("ri", "")
    zone = query.validated_data.get("zone", "")

    try:
        options = agg.get_filter_options(agm=agm, ri=ri, zone=zone)
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

    Returns the full dashboard payload (KPIs, dropout analysis, staff
    analysis, room analysis, RI-wise and branch-wise breakdowns) for the
    given filter selection. Any of the three params may be omitted or set
    to "All".
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


@api_view(["POST"])
def ask_ai_view(request):
    """
    POST /api/dashboard/ask-ai/
    Body: {"question": "..."}

    Forwards the question, server-to-server, to the independent
    branch_query_engine_v2 service and relays its response back to the
    AI Assistant chat UI. No AI/query logic runs in branch_dashboard --
    this view is a thin pass-through around dashboard.services.query_engine_client.
    """
    query = AskAiRequestSerializer(data=request.data)
    query.is_valid(raise_exception=True)
    question = query.validated_data["question"]

    # `filters` is only present in validated_data when the caller actually
    # sent a "filters" object (nested serializers don't materialize a
    # default when their key is absent). Normalize to the same "All" /
    # empty-list defaults either way so query_engine_client always gets a
    # complete, predictable dict.
    filters = query.validated_data.get("filters") or {}
    filter_context = {
        "agm": filters.get("agm") or "All",
        "ri": filters.get("ri") or "All",
        "zone": filters.get("zone") or "All",
        "branches": filters.get("branches") or ["All"],
    }

    try:
        result = query_engine_client.ask(question, filters=filter_context)
    except query_engine_client.QueryEngineError as exc:
        logger.warning("Query engine call failed: %s", exc)
        return Response(
            {"success": False, "answer": str(exc), "function": None},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    # Relay the query engine's own success/failure status verbatim so the
    # chat UI can show its actual answer text either way.
    http_status = status.HTTP_200_OK if result.get("success") else status.HTTP_400_BAD_REQUEST
    return Response(result, status=http_status)
