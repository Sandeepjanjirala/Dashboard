"""
Automated tests covering the test matrix from the spec (section 16):
  1. All AGMs
  2. Individual AGM
  3. Individual RI
  4. Individual Branch
  5. AGM + All RI + All Branch
  6. AGM + RI + All Branch
  7. AGM + RI + Branch

Plus: PP/PS/HS aggregation rules, error handling for invalid filters, and
JSON-safety (no NaN/Infinity ever reaches the response).

Run with:
    python manage.py test dashboard
"""
import math
from unittest.mock import patch

import pandas as pd
from django.test import TestCase
from rest_framework.test import APIClient

from dashboard.services import aggregation_service as agg
from dashboard.services import dashboard_service
from dashboard.services import excel_service
from dashboard.utils import column_mapping as cm


class ColumnMappingTests(TestCase):
    def test_every_mapped_column_exists_in_workbook(self):
        df = excel_service.get_dataframe()
        missing = [c for c in cm.REQUIRED_COLUMNS if c not in df.columns]
        self.assertEqual(missing, [], f"Mapped columns missing from workbook: {missing}")

    def test_no_stray_columns_left_unmapped(self):
        df = excel_service.get_dataframe()
        unmapped = [c for c in df.columns if c not in cm.REQUIRED_COLUMNS]
        self.assertEqual(unmapped, [], f"Workbook columns not covered by mapping: {unmapped}")


class AggregationRuleTests(TestCase):
    """Verify the underlying-totals-first aggregation rules against raw sums."""

    def setUp(self):
        self.df = excel_service.get_dataframe()

    def test_category_nos_sums_to_overall_nos(self):
        total = self.df[cm.COL_NOS].sum()
        cat_total = sum(self.df[cm.shape_col("NOS", category=c)].sum() for c in cm.CATEGORIES)
        self.assertEqual(total, cat_total)

    def test_category_cy_gs_sums_to_overall_cy_gs(self):
        total = self.df[cm.COL_CY_GS].sum()
        cat_total = sum(
            self.df[cm.strength_col("GS", "CY", category=c)].sum() for c in cm.CATEGORIES
        )
        self.assertEqual(total, cat_total)

    def test_nocr_equals_noor_plus_novr(self):
        diff = self.df[cm.COL_NOCR] - (self.df[cm.COL_NOOR] + self.df[cm.COL_NOVR])
        self.assertTrue((diff == 0).all())

    def test_dropout_pct_is_never_averaged(self):
        """
        Overall CY dropout % for the whole dataset must equal
        SUM(CY-DP)/SUM(CY-GS)*100, NOT the mean of the per-branch CY-DPP column.
        """
        correct = self.df[cm.COL_CY_DP].sum() / self.df[cm.COL_CY_GS].sum() * 100
        wrong_if_averaged = self.df[cm.COL_CY_DPP].mean()

        payload = dashboard_service.build_dashboard_response()
        reported = payload["kpis"]["cy_dropout_percentage"]["value"]

        self.assertAlmostEqual(reported, round(correct, 1), places=1)
        self.assertNotAlmostEqual(reported, round(wrong_if_averaged, 1), places=1)

    def test_avg_strength_per_section_uses_totals_not_average(self):
        correct = self.df[cm.COL_CY_NS].sum() / self.df[cm.COL_NOS].sum()
        payload = dashboard_service.build_dashboard_response()
        reported = payload["kpis"]["avg_strength_per_section"]["value"]
        self.assertAlmostEqual(reported, round(correct, 1), places=1)


class DashboardAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.df = excel_service.get_dataframe()
        self.some_agm = self.df[cm.COL_AGM].iloc[0]
        self.some_ri = self.df[cm.COL_RI].iloc[0]
        self.some_branch = self.df[cm.COL_BRANCH].iloc[0]

    def _get(self, **params):
        return self.client.get("/api/dashboard/", params)

    # -- Test matrix ---------------------------------------------------

    def test_1_all_agms(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["row_count"], len(self.df))
        self.assertEqual(body["kpis"]["total_sections"]["value"], int(self.df[cm.COL_NOS].sum()))

    def test_2_individual_agm(self):
        resp = self._get(agm=self.some_agm)
        body = resp.json()
        expected_rows = self.df[self.df[cm.COL_AGM] == self.some_agm]
        self.assertEqual(body["row_count"], len(expected_rows))

    def test_3_individual_ri(self):
        resp = self._get(ri=self.some_ri)
        body = resp.json()
        expected_rows = self.df[self.df[cm.COL_RI] == self.some_ri]
        self.assertEqual(body["row_count"], len(expected_rows))
        self.assertEqual(
            body["kpis"]["total_sections"]["value"], int(expected_rows[cm.COL_NOS].sum())
        )

    def test_4_individual_branch(self):
        resp = self._get(branch=self.some_branch)
        body = resp.json()
        expected_rows = self.df[self.df[cm.COL_BRANCH] == self.some_branch]
        self.assertEqual(body["row_count"], 1)
        self.assertEqual(
            body["kpis"]["total_sections"]["value"], int(expected_rows[cm.COL_NOS].sum())
        )

    def test_5_agm_all_ri_all_branch(self):
        resp = self._get(agm=self.some_agm, ri="All", branch="All")
        body = resp.json()
        expected_rows = self.df[self.df[cm.COL_AGM] == self.some_agm]
        self.assertEqual(body["row_count"], len(expected_rows))

    def test_6_agm_ri_all_branch(self):
        resp = self._get(agm=self.some_agm, ri=self.some_ri, branch="All")
        body = resp.json()
        expected_rows = self.df[
            (self.df[cm.COL_AGM] == self.some_agm) & (self.df[cm.COL_RI] == self.some_ri)
        ]
        self.assertEqual(body["row_count"], len(expected_rows))

    def test_7_agm_ri_branch(self):
        resp = self._get(agm=self.some_agm, ri=self.some_ri, branch=self.some_branch)
        body = resp.json()
        self.assertEqual(body["row_count"], 1)
        self.assertEqual(body["filters"]["branch"], self.some_branch)

    # -- PP / PS / HS aggregation -------------------------------------

    def test_category_sections_sum_to_total(self):
        resp = self._get()
        body = resp.json()
        cats = body["dropout_analysis"]["categories"]
        total_from_categories = sum(cats[c]["sections"] for c in cm.CATEGORIES)
        self.assertEqual(total_from_categories, body["kpis"]["total_sections"]["value"])

    # -- Error handling --------------------------------------------------

    def test_invalid_ri_returns_400(self):
        resp = self._get(ri="Does Not Exist")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_branch_not_belonging_to_ri_returns_400(self):
        other_ri = self.df[self.df[cm.COL_RI] != self.some_ri][cm.COL_RI].iloc[0]
        other_branch = self.df[self.df[cm.COL_RI] == other_ri][cm.COL_BRANCH].iloc[0]
        resp = self._get(ri=self.some_ri, branch=other_branch)
        self.assertEqual(resp.status_code, 400)

    # -- JSON safety -----------------------------------------------------

    def test_response_has_no_nan_or_infinity(self):
        resp = self._get()
        raw = resp.content.decode()
        self.assertNotIn("NaN", raw)
        self.assertNotIn("Infinity", raw)


class FiltersAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_filters_endpoint_returns_all_agms(self):
        resp = self.client.get("/api/dashboard/filters/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertGreater(len(body["agms"]), 0)

    def test_filters_cascade_by_agm(self):
        df = excel_service.get_dataframe()
        agm = df[cm.COL_AGM].iloc[0]
        resp = self.client.get("/api/dashboard/filters/", {"agm": agm})
        body = resp.json()
        expected_ris = sorted(df[df[cm.COL_AGM] == agm][cm.COL_RI].unique().tolist())
        self.assertEqual(sorted(body["ris"]), expected_ris)

    def test_filters_invalid_agm_returns_400(self):
        resp = self.client.get("/api/dashboard/filters/", {"agm": "Nobody"})
        self.assertEqual(resp.status_code, 400)


class OverallStaffCountTests(TestCase):
    """
    Regression tests for the Phase 2 correction: the overall Student/Teacher
    Count (CY-SC / LY-SC) must come from the workbook's overall CY-SC / LY-SC
    columns, never from summing AC-CY-SC + AD-CY-SC (Activity + Admin staff
    are separate categories).
    """

    def setUp(self):
        self.client = APIClient()
        self.df = excel_service.get_dataframe()

    def test_overall_cy_sc_matches_workbook_column_not_ac_plus_ad(self):
        correct_cy_sc = int(self.df[cm.shape_col("CY-SC")].sum())
        wrong_if_summed = int(
            self.df[cm.staff_col("AC", "CY-SC")].sum() + self.df[cm.staff_col("AD", "CY-SC")].sum()
        )

        resp = self.client.get("/api/dashboard/")
        body = resp.json()
        reported = body["staff_analysis"]["student_teacher_ratio"]["overall"]["cy_staff_count"]

        self.assertEqual(reported, correct_cy_sc)
        self.assertNotEqual(reported, wrong_if_summed)

    def test_overall_ly_sc_matches_workbook_column_not_ac_plus_ad(self):
        correct_ly_sc = int(self.df[cm.shape_col("LY-SC")].sum())
        wrong_if_summed = int(
            self.df[cm.staff_col("AC", "LY-SC")].sum() + self.df[cm.staff_col("AD", "LY-SC")].sum()
        )

        resp = self.client.get("/api/dashboard/")
        body = resp.json()
        reported = body["staff_analysis"]["student_teacher_ratio"]["overall"]["ly_staff_count"]

        self.assertEqual(reported, correct_ly_sc)
        self.assertNotEqual(reported, wrong_if_summed)

    def test_overall_cy_str_uses_overall_cy_sc_not_ac_plus_ad(self):
        correct = self.df[cm.COL_CY_NS].sum() / self.df[cm.shape_col("CY-SC")].sum()

        resp = self.client.get("/api/dashboard/")
        body = resp.json()
        reported = body["staff_analysis"]["student_teacher_ratio"]["overall"]["cy_ratio"]

        self.assertAlmostEqual(reported, round(correct, 1), places=1)

    def test_overall_ly_str_uses_overall_ly_sc_not_ac_plus_ad(self):
        correct = self.df[cm.COL_LY_NS].sum() / self.df[cm.shape_col("LY-SC")].sum()

        resp = self.client.get("/api/dashboard/")
        body = resp.json()
        reported = body["staff_analysis"]["student_teacher_ratio"]["overall"]["ly_ratio"]

        self.assertAlmostEqual(reported, round(correct, 1), places=1)

    def test_ac_and_ad_remain_separate_categories(self):
        resp = self.client.get("/api/dashboard/")
        body = resp.json()
        self.assertIn("AC", body["staff_analysis"])
        self.assertIn("AD", body["staff_analysis"])
        self.assertEqual(body["staff_analysis"]["AC"]["label"], "Activity Staff")
        self.assertEqual(body["staff_analysis"]["AD"]["label"], "Administration Staff")


class HierarchicalValidationTests(TestCase):
    """
    AGM -> RI -> Branch is a real hierarchy: a value at one level must be
    validated against the dataset already scoped by the level(s) above it,
    not against the global dataset.
    """

    def setUp(self):
        self.client = APIClient()
        self.df = excel_service.get_dataframe()

    def test_branch_under_wrong_ri_is_rejected(self):
        ri_a = self.df[cm.COL_RI].iloc[0]
        branch_under_other_ri = self.df[self.df[cm.COL_RI] != ri_a][cm.COL_BRANCH].iloc[0]

        resp = self.client.get("/api/dashboard/", {"ri": ri_a, "branch": branch_under_other_ri})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_branch_under_correct_ri_is_accepted(self):
        ri_a = self.df[cm.COL_RI].iloc[0]
        branch_under_ri_a = self.df[self.df[cm.COL_RI] == ri_a][cm.COL_BRANCH].iloc[0]

        resp = self.client.get("/api/dashboard/", {"ri": ri_a, "branch": branch_under_ri_a})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    def test_ri_under_wrong_agm_is_rejected(self):
        agm_a = self.df[cm.COL_AGM].iloc[0]
        ris_under_agm_a = set(self.df[self.df[cm.COL_AGM] == agm_a][cm.COL_RI].unique())
        ri_not_under_agm_a = next(
            (r for r in self.df[cm.COL_RI].unique() if r not in ris_under_agm_a), None
        )
        if ri_not_under_agm_a is None:
            self.skipTest("Workbook has only one AGM -- no cross-AGM RI to test against.")

        resp = self.client.get("/api/dashboard/", {"agm": agm_a, "ri": ri_not_under_agm_a})
        self.assertEqual(resp.status_code, 400)

    def test_filters_endpoint_scopes_branches_by_agm_and_ri(self):
        ri_a = self.df[cm.COL_RI].iloc[0]
        agm_a = self.df[self.df[cm.COL_RI] == ri_a][cm.COL_AGM].iloc[0]
        expected_branches = sorted(
            self.df[(self.df[cm.COL_AGM] == agm_a) & (self.df[cm.COL_RI] == ri_a)][
                cm.COL_BRANCH
            ].unique().tolist()
        )

        resp = self.client.get("/api/dashboard/filters/", {"agm": agm_a, "ri": ri_a})
        body = resp.json()
        self.assertEqual(sorted(body["branches"]), expected_branches)


class RiGrandTotalTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.df = excel_service.get_dataframe()

    def test_grand_total_present_and_correct_for_all_data(self):
        correct_dropouts = int(self.df[cm.COL_CY_DP].sum())
        correct_pct = round(
            self.df[cm.COL_CY_DP].sum() / self.df[cm.COL_CY_GS].sum() * 100, 1
        )
        correct_str = round(
            self.df[cm.COL_CY_NS].sum() / self.df[cm.shape_col("CY-SC")].sum(), 1
        )
        correct_empty = int(self.df[cm.COL_NOVR].sum())

        resp = self.client.get("/api/dashboard/")
        body = resp.json()
        gt = body["ri_grand_total"]

        self.assertEqual(gt["cy_dropouts"], correct_dropouts)
        self.assertAlmostEqual(gt["dropout_pct"], correct_pct, places=1)
        self.assertAlmostEqual(gt["student_teacher_ratio"], correct_str, places=1)
        self.assertEqual(gt["empty_rooms"], correct_empty)

    def test_grand_total_equals_sum_of_ri_rows(self):
        resp = self.client.get("/api/dashboard/")
        body = resp.json()
        summed_dropouts = sum(row["cy_dropouts"] for row in body["ri_analysis"])
        summed_empty = sum(row["empty_rooms"] for row in body["ri_analysis"])
        self.assertEqual(body["ri_grand_total"]["cy_dropouts"], summed_dropouts)
        self.assertEqual(body["ri_grand_total"]["empty_rooms"], summed_empty)


class BranchAnalysisCompletenessTests(TestCase):
    """All branches in the current filter scope must be present -- the
    frontend is responsible for scroll/pagination UI, not the backend for
    silently truncating rows."""

    def setUp(self):
        self.client = APIClient()
        self.df = excel_service.get_dataframe()

    def test_all_59_branches_present_with_no_filter(self):
        resp = self.client.get("/api/dashboard/")
        body = resp.json()
        expected = self.df[cm.COL_BRANCH].nunique()
        self.assertEqual(len(body["branch_analysis"]), expected)

    def test_branch_analysis_scoped_to_selected_ri(self):
        ri_a = self.df[cm.COL_RI].iloc[0]
        expected = self.df[self.df[cm.COL_RI] == ri_a][cm.COL_BRANCH].nunique()

        resp = self.client.get("/api/dashboard/", {"ri": ri_a})
        body = resp.json()
        self.assertEqual(len(body["branch_analysis"]), expected)


class MockedTwoAgmHierarchyTests(TestCase):
    """
    The real workbook only has one AGM, so it can never exercise a
    cross-AGM rejection. This class builds a small synthetic DataFrame
    with TWO AGMs (never touching the production Excel file) and patches
    excel_service.get_dataframe() so aggregation_service.get_filtered_dataframe
    runs its real hierarchy-validation logic against it.

    Fixture shape:
        AGM-A -> RI-A  -> Branch-A
        AGM-A -> RI-A2 -> Branch-A2
        AGM-B -> RI-B  -> Branch-B
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        identifiers = {
            cm.COL_AGM: ["AGM-A", "AGM-A", "AGM-B"],
            cm.COL_RI: ["RI-A", "RI-A2", "RI-B"],
            cm.COL_ZONE: ["Zone-1", "Zone-1", "Zone-2"],
            cm.COL_BRANCH: ["Branch-A", "Branch-A2", "Branch-B"],
        }
        # Fill every other required column (KPI/business fields) with 0 so
        # that a full end-to-end request through dashboard_service (which
        # needs those columns to build KPIs/dropout/staff blocks) doesn't
        # KeyError -- this fixture is only exercising hierarchy validation,
        # not business-rule correctness, so zeros are fine.
        numeric_cols = [c for c in cm.REQUIRED_COLUMNS if c not in identifiers]
        data = {**identifiers, **{col: [0, 0, 0] for col in numeric_cols}}
        cls.mock_df = pd.DataFrame(data)

    def setUp(self):
        patcher = patch.object(excel_service, "get_dataframe", return_value=self.mock_df)
        self.mock_get_dataframe = patcher.start()
        self.addCleanup(patcher.stop)

    # -- 1/2: RI validated within AGM scope -----------------------------

    def test_ri_belonging_to_selected_agm_is_accepted(self):
        result = agg.get_filtered_dataframe(agm="AGM-A", ri="RI-A")
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0][cm.COL_BRANCH], "Branch-A")

    def test_ri_belonging_to_another_agm_is_rejected(self):
        with self.assertRaises(agg.InvalidFilterError) as ctx:
            agg.get_filtered_dataframe(agm="AGM-A", ri="RI-B")
        self.assertEqual(ctx.exception.field, "ri")
        self.assertEqual(ctx.exception.value, "RI-B")

    # -- 3/4/5: Branch validated within AGM + RI scope -------------------

    def test_branch_belonging_to_selected_agm_and_ri_is_accepted(self):
        result = agg.get_filtered_dataframe(agm="AGM-A", ri="RI-A", branch="Branch-A")
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0][cm.COL_BRANCH], "Branch-A")

    def test_branch_belonging_to_another_ri_under_same_agm_is_rejected(self):
        # Branch-A2 exists under AGM-A, but under RI-A2, not RI-A.
        with self.assertRaises(agg.InvalidFilterError) as ctx:
            agg.get_filtered_dataframe(agm="AGM-A", ri="RI-A", branch="Branch-A2")
        self.assertEqual(ctx.exception.field, "branch")
        self.assertEqual(ctx.exception.value, "Branch-A2")

    def test_branch_belonging_to_another_agm_is_rejected(self):
        # Branch-B exists, but under AGM-B, not AGM-A.
        with self.assertRaises(agg.InvalidFilterError) as ctx:
            agg.get_filtered_dataframe(agm="AGM-A", ri="RI-A", branch="Branch-B")
        self.assertEqual(ctx.exception.field, "branch")
        self.assertEqual(ctx.exception.value, "Branch-B")

    # -- 6/7/8: filtered row counts at each hierarchy level ---------------

    def test_agm_only_returns_correct_row_count(self):
        result = agg.get_filtered_dataframe(agm="AGM-A")
        self.assertEqual(len(result), 2)  # RI-A + RI-A2, both under AGM-A

    def test_agm_and_ri_returns_correct_row_count(self):
        result = agg.get_filtered_dataframe(agm="AGM-A", ri="RI-A")
        self.assertEqual(len(result), 1)

    def test_agm_ri_and_branch_returns_correct_row_count(self):
        result = agg.get_filtered_dataframe(agm="AGM-A", ri="RI-A", branch="Branch-A")
        self.assertEqual(len(result), 1)

    # -- End-to-end via the public API, same mocked fixture ---------------

    def test_api_rejects_ri_from_another_agm(self):
        client = APIClient()
        resp = client.get("/api/dashboard/", {"agm": "AGM-A", "ri": "RI-B"})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_api_rejects_branch_from_another_ri(self):
        client = APIClient()
        resp = client.get(
            "/api/dashboard/", {"agm": "AGM-A", "ri": "RI-A", "branch": "Branch-A2"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_api_accepts_valid_full_hierarchy(self):
        client = APIClient()
        resp = client.get(
            "/api/dashboard/", {"agm": "AGM-A", "ri": "RI-A", "branch": "Branch-A"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(resp.json()["row_count"], 1)
