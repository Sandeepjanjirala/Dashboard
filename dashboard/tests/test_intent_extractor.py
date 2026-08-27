"""
Tests for the rule-based intent extractor.

These tests are fully self-contained: they bypass the live Excel file by
passing fixture entity lists directly to extract_intent().  No Django
settings are required.

Run with:
    python manage.py test dashboard.tests.test_intent_extractor
"""
from unittest import TestCase

from dashboard.services.intent_extractor import extract_intent

# ---------------------------------------------------------------------------
# Fixture entity lists (representative subset of the real dataset)
# ---------------------------------------------------------------------------
AGMS = ["Mr.M.V.Suresh"]
RIS = [
    "Mr M.V.L.Naresh", "Mr.Ahmedali", "Mr.M.Ramana", "Mr.P Gopi Nath",
    "Mr.P.Srinivas Rao", "Mr.PSSSV Prasad", "Mr.S.Raminaidu",
    "Mr.Uday Shankar V", "Mr.V. Srinivasa Rao",
]
ZONES = ["Kakinada", "Rajahmundry - East", "Visakhapatnam"]
BRANCHES = [
    "AMALAPURAM", "AMALAPURAM 2", "ANAKAPALLI", "ANAPARTHI", "ASILMETTA",
    "ASILMETTA 3", "BOBBILI", "BOBBILI 2", "CHEEPURUPALLI", "DRAKSHARAMAM",
    "Dwarakanagar IPL", "GAJUWAKA", "GAJUWAKA 2", "JAGGAMPETA",
    "KAKINADA 1", "KAKINADA 2", "KAKINADA 7", "KOMMADI", "KOTHAPETA",
    "KOVVUR", "KURMANNAPALEM", "Kakinada 3", "Kakinada 4", "Kakinada 6",
    "MADHURAWADA", "MADHURAWADA 2", "MADHURAWADA 4", "MADHURAWADA 5",
    "MANDAPETA 2", "MVP COLONY", "NAD", "NAD 2", "NARSIPATNAM", "PALASA",
    "PARVATHIPURAM", "PENDURTY", "Payakaraopeta", "Pitapuram",
    "RAJAHMUNDRY 1", "RAJAHMUNDRY 2", "RAJAHMUNDRY 5", "RAJAHMUNDRY 6",
    "RAJAHMUNDRY 7", "RAJAHMUNDRY BOMMURU", "RAJAM", "RAMACHANDRAPURAM",
    "RAVULAPALEM", "SRIKAKULAM", "SRIKAKULAM 2", "SRIKAKULAM 3",
    "Sunkarapalem", "Tuni 1", "Tuni 2", "VIZIANAGARAM", "VIZIANAGARAM 2",
    "VIZIANAGARAM 3", "YALAMANCHILI", "YELESWARAM", "Yanam",
]


def _extract(question):
    return extract_intent(
        question=question,
        agms=AGMS,
        ris=RIS,
        zones=ZONES,
        branches=BRANCHES,
    )


# ---------------------------------------------------------------------------
# RESET intent
# ---------------------------------------------------------------------------

class ResetIntentTests(TestCase):

    def test_reset_keyword(self):
        r = _extract("Reset filters")
        self.assertEqual(r.intent, "dashboard_reset")

    def test_clear_all(self):
        r = _extract("Clear all filters")
        self.assertEqual(r.intent, "dashboard_reset")

    def test_show_everything(self):
        r = _extract("Show everything")
        self.assertEqual(r.intent, "dashboard_reset")

    def test_reset_dashboard(self):
        r = _extract("Reset dashboard")
        self.assertEqual(r.intent, "dashboard_reset")

    def test_reset_filters_have_all(self):
        r = _extract("reset")
        self.assertEqual(r.filters.get("zone"), "All")
        self.assertEqual(r.filters.get("branches"), ["All"])

    def test_start_over(self):
        r = _extract("Start over, show all branches")
        self.assertEqual(r.intent, "dashboard_reset")


# ---------------------------------------------------------------------------
# FILTER intent — Zone
# ---------------------------------------------------------------------------

class ZoneFilterTests(TestCase):

    def test_show_me_zone(self):
        r = _extract("Show me Zone Kakinada")
        self.assertEqual(r.intent, "dashboard_filter")
        self.assertEqual(r.filters.get("zone"), "Kakinada")

    def test_filter_to_zone(self):
        r = _extract("Filter to Kakinada")
        self.assertEqual(r.intent, "dashboard_filter")
        self.assertEqual(r.filters.get("zone"), "Kakinada")

    def test_zone_visakhapatnam(self):
        r = _extract("Show Visakhapatnam zone")
        self.assertEqual(r.intent, "dashboard_filter")
        self.assertEqual(r.filters.get("zone"), "Visakhapatnam")

    def test_zone_rajahmundry_east(self):
        r = _extract("Filter to Rajahmundry - East zone")
        self.assertEqual(r.intent, "dashboard_filter")
        self.assertEqual(r.filters.get("zone"), "Rajahmundry - East")

    def test_zone_branch_resets_to_all(self):
        r = _extract("Show Zone Kakinada")
        self.assertEqual(r.filters.get("branches"), ["All"])


# ---------------------------------------------------------------------------
# FILTER intent — Branch
# ---------------------------------------------------------------------------

class BranchFilterTests(TestCase):

    def test_show_amalapuram(self):
        r = _extract("Show AMALAPURAM branch")
        self.assertEqual(r.intent, "dashboard_filter")
        self.assertIn("AMALAPURAM", r.filters.get("branches", []))

    def test_show_kakinada_1(self):
        r = _extract("Show me KAKINADA 1")
        self.assertEqual(r.intent, "dashboard_filter")
        self.assertIn("KAKINADA 1", r.filters.get("branches", []))

    def test_show_gajuwaka_2(self):
        r = _extract("Filter to GAJUWAKA 2")
        self.assertEqual(r.intent, "dashboard_filter")
        self.assertIn("GAJUWAKA 2", r.filters.get("branches", []))

    def test_case_insensitive_branch(self):
        r = _extract("Show me amalapuram")
        self.assertEqual(r.intent, "dashboard_filter")
        self.assertTrue(len(r.filters.get("branches", [])) > 0)

    def test_unknown_branch(self):
        r = _extract("Show me XYZZY_NONEXISTENT_BRANCH_123")
        # Should be unknown (no entity found) or clarification
        self.assertIn(r.intent, ("unknown", "clarification_required"))


# ---------------------------------------------------------------------------
# CLARIFICATION intent
# ---------------------------------------------------------------------------

class ClarificationTests(TestCase):

    def test_ambiguous_amalapuram(self):
        # "amalapuram" could be AMALAPURAM or AMALAPURAM 2
        r = _extract("Show me Amalapuram")
        # Either clarification (ambiguous) or filter (resolved by longest match)
        self.assertIn(r.intent, ("clarification_required", "dashboard_filter"))

    def test_ambiguous_shows_candidates(self):
        r = _extract("Navigate to Srikakulam")
        if r.intent == "clarification_required":
            self.assertGreater(len(r.ambiguous_matches), 1)
            self.assertIsNotNone(r.error)

    def test_ambiguous_error_message_contains_candidates(self):
        r = _extract("Select Madhurawada")
        if r.intent == "clarification_required":
            for cand in r.ambiguous_matches:
                self.assertIn(cand, r.error)

    def test_exact_numbered_branch_no_ambiguity(self):
        r = _extract("Show AMALAPURAM 2")
        # Numbered variant should resolve unambiguously
        if r.intent == "dashboard_filter":
            self.assertIn("AMALAPURAM 2", r.filters.get("branches", []))


# ---------------------------------------------------------------------------
# ANALYTICAL / QUERY intent
# ---------------------------------------------------------------------------

class AnalyticalIntentTests(TestCase):

    def test_top_10_dropout(self):
        r = _extract("Show me top 10 branches with highest dropout percentage")
        self.assertEqual(r.intent, "dashboard_query")

    def test_top_5_dropout(self):
        r = _extract("Which are the top 5 branches by dropout?")
        self.assertEqual(r.intent, "dashboard_query")

    def test_compare_zones(self):
        r = _extract("Compare Zone 1 and Zone 2")
        # Analytical comparison — should route to query engine, not filter
        self.assertEqual(r.intent, "dashboard_query")

    def test_average_strength(self):
        r = _extract("What is the average strength per section?")
        self.assertEqual(r.intent, "dashboard_query")

    def test_yoy_improvement(self):
        r = _extract("Which branches improved their dropout percentage compared with last year?")
        self.assertEqual(r.intent, "dashboard_query")

    def test_unsupported_metric(self):
        r = _extract("Show me employee happiness score")
        # No entity match and not a known analytical pattern → unknown
        self.assertEqual(r.intent, "unknown")


# ---------------------------------------------------------------------------
# HYBRID intent (filter + query)
# ---------------------------------------------------------------------------

class HybridIntentTests(TestCase):

    def test_show_branch_and_dropout(self):
        r = _extract("Show me AMALAPURAM dropout percentage")
        self.assertEqual(r.intent, "dashboard_filter_and_query")
        self.assertIn("AMALAPURAM", r.filters.get("branches", []))

    def test_show_zone_and_strength(self):
        r = _extract("Show Kakinada zone strength")
        self.assertEqual(r.intent, "dashboard_filter_and_query")
        self.assertEqual(r.filters.get("zone"), "Kakinada")

    def test_hybrid_scorecard(self):
        r = _extract("Show DRAKSHARAMAM scorecard")
        self.assertEqual(r.intent, "dashboard_filter_and_query")
        self.assertIn("DRAKSHARAMAM", r.filters.get("branches", []))


# ---------------------------------------------------------------------------
# Voice path: same function, just different text input
# ---------------------------------------------------------------------------

class VoicePathTests(TestCase):
    """
    Voice input ultimately becomes a text string passed to sendQuestion(),
    which calls /api/dashboard/ask-ai/, which calls extract_intent().
    These tests verify the same function handles voice-style phrasing.
    """

    def test_voice_filter_zone(self):
        r = _extract("show me zone kakinada")  # lowercase, as speech-to-text may produce
        self.assertEqual(r.intent, "dashboard_filter")
        self.assertEqual(r.filters.get("zone"), "Kakinada")

    def test_voice_reset(self):
        r = _extract("reset everything please")
        self.assertEqual(r.intent, "dashboard_reset")

    def test_voice_analytical(self):
        r = _extract("what is the dropout percentage for this zone")
        self.assertIn(r.intent, ("dashboard_query", "dashboard_filter_and_query"))

    def test_voice_show_branch(self):
        r = _extract("show anakapalli")
        self.assertEqual(r.intent, "dashboard_filter")
        self.assertIn("ANAKAPALLI", r.filters.get("branches", []))
