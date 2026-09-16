from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from dashboard.services import aggregation_service as agg
from dashboard.services import excel_service
from dashboard.services import fee_due_service
from dashboard.views import fee_due_dashboard_view, filters_view


class FeeDueAPITests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_fee_due_dataframe_loading(self):
        df = excel_service.get_dataframe(dataset_id="fee_due")
        self.assertFalse(df.empty)
        self.assertIn("CY_A_FD", df.columns)
        self.assertIn("LY_FD", df.columns)
        self.assertIn("Branch", df.columns)

    def test_fee_due_service_aggregations(self):
        payload = fee_due_service.build_fee_due_dashboard_response()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["dataset"], "fee_due")
        self.assertIn("kpis", payload)
        self.assertIn("charts", payload)
        self.assertIn("breakdowns", payload)
        self.assertIn("key_insights", payload)

        kpis = payload["kpis"]
        self.assertIn("cy_live_student_fee_due", kpis)
        self.assertIn("actual_zero_paid_count", kpis)
        self.assertGreater(kpis["cy_live_student_fee_due"]["value"], 0)

        charts = payload["charts"]
        self.assertIn("fee_due_comparison_amount", charts)
        self.assertIn("student_segmentation", charts)

        breakdowns = payload["breakdowns"]
        self.assertIn("overview", breakdowns)
        self.assertIn("zone_analysis", breakdowns)

    def test_fee_due_dashboard_view_api(self):
        request = self.factory.get("/api/dashboard/fee-due/")
        response = fee_due_dashboard_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["filters"]["zone"], "All")
        self.assertIn("kpis", response.data)

    def test_fee_due_dashboard_view_filtered(self):
        # Filter by zone=Kakinada
        request = self.factory.get("/api/dashboard/fee-due/?zone=Kakinada")
        response = fee_due_dashboard_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["filters"]["zone"], "Kakinada")
        self.assertGreater(response.data["row_count"], 0)

    def test_fee_due_filters_view_api(self):
        request = self.factory.get("/api/dashboard/filters/?dataset=fee_due")
        response = filters_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertIn("zones", response.data)
        self.assertIn("Kakinada", response.data["zones"])
