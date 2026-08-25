from rest_framework import serializers


class DashboardFilterQuerySerializer(serializers.Serializer):
    """
    Validates the ?agm=&ri=&zone=&branch= query params shared by both the
    /filters/ and /dashboard/ endpoints. All four are optional; an
    absent or empty value (or the literal string "All") means "no filter
    at this level".
    """

    agm = serializers.CharField(required=False, allow_blank=True, default="")
    ri = serializers.CharField(required=False, allow_blank=True, default="")
    zone = serializers.CharField(required=False, allow_blank=True, default="")
    branch = serializers.CharField(required=False, allow_blank=True, default="")


class AskAiFilterContextSerializer(serializers.Serializer):
    """
    The AGM / RI / Branch selection currently active on the dashboard,
    sent alongside every question so the query engine can (now or in a
    future function) scope its answer to what the user is actually
    looking at.

    Every field is optional and defaults to "no filter" -- a request that
    omits `filters` entirely keeps working exactly as before this layer
    was added.

    `branches` is a list (not a single string) even though the dashboard's
    branch dropdown is single-select today: it's the one field of the
    three that may need to carry more than one value if/when that
    dropdown becomes multi-select, and modelling it as a list now means
    the wire contract won't need to change later.
    """

    agm = serializers.CharField(required=False, allow_blank=True, default="All")
    ri = serializers.CharField(required=False, allow_blank=True, default="All")
    zone = serializers.CharField(required=False, allow_blank=True, default="All")
    branches = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        default=list,
    )


class AskAiRequestSerializer(serializers.Serializer):
    """Validates the AI Assistant chat panel's POST body."""

    question = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)
    # Optional: present whenever the request comes from the dashboard's own
    # AI panel (both text and voice flows send it via the same
    # sendQuestion() call). Absent for any older/other caller.
    filters = AskAiFilterContextSerializer(required=False)
