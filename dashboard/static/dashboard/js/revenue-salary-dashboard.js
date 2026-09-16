/*
 * Revenue vs Salary Analysis Dashboard Controller.
 *
 * Fetches and renders live data from GET /api/dashboard/revenue-vs-salary/
 * Displays API endpoint info, KPIs, segment breakdown, and branch data.
 */

const RevenueSalaryDashboard = (function () {

  function formatCurrency(val) {
    if (val === undefined || val === null) return "--";
    try {
      const v = Math.round(Number(val));
      const s = String(Math.abs(v));
      const sign = v < 0 ? "-" : "";
      if (s.length <= 3) return sign + "₹" + s;
      const last3 = s.slice(-3);
      let rest = s.slice(0, -3);
      const parts = [];
      while (rest.length > 0) {
        parts.push(rest.slice(-2));
        rest = rest.slice(0, -2);
      }
      return sign + "₹" + parts.reverse().join(",") + "," + last3;
    } catch (e) {
      return "₹" + val;
    }
  }

  function formatNum(val) {
    if (val === undefined || val === null) return "--";
    return Number(val).toLocaleString("en-IN");
  }

  function render(resp) {
    if (!resp || !resp.success) return;

    // 1. Update API Endpoint Info banner
    const currentParams = $.param(resp.filters || {});
    const apiUrl = "/api/dashboard/revenue-vs-salary/?" + currentParams;
    $("#rev-sal-api-url").text(apiUrl).attr("href", apiUrl);
    $("#rev-sal-json-output").text(JSON.stringify(resp, null, 2));

    // 2. Render KPI cards
    const kpis = resp.kpis || {};
    if (kpis.total_revenue) $("#kpi-rs-revenue").text(formatCurrency(kpis.total_revenue.value));
    if (kpis.total_salary) $("#kpi-rs-salary").text(formatCurrency(kpis.total_salary.value));
    if (kpis.net_surplus) $("#kpi-rs-surplus").text(formatCurrency(kpis.net_surplus.value));
    if (kpis.total_students) $("#kpi-rs-students").text(formatNum(kpis.total_students.value));
    if (kpis.total_employees) $("#kpi-rs-employees").text(formatNum(kpis.total_employees.value));
    if (kpis.fee_average) $("#kpi-rs-fee-avg").text(formatCurrency(kpis.fee_average.value));
    if (kpis.cost_per_student) $("#kpi-rs-cost-student").text(formatCurrency(kpis.cost_per_student.value));
    if (kpis.salary_vs_revenue_pct) $("#kpi-rs-sal-v-rev").text(kpis.salary_vs_revenue_pct.value + "%");
    if (kpis.student_teacher_ratio) $("#kpi-rs-str").text(kpis.student_teacher_ratio.value);

    // 3. Render Segment Analysis Table
    const segments = resp.segment_analysis || [];
    const $segTbody = $("#rev-sal-segment-tbody");
    $segTbody.empty();
    if (segments.length === 0) {
      $segTbody.append('<tr><td colspan="8" style="text-align:center;">No segment data available for current filters.</td></tr>');
    } else {
      segments.forEach(function (s) {
        $segTbody.append(
          '<tr>' +
            '<td><strong>' + s.segment_name + '</strong> (' + s.segment_code + ')</td>' +
            '<td>' + formatCurrency(s.total_revenue) + '</td>' +
            '<td>' + formatCurrency(s.total_salary) + '</td>' +
            '<td>' + formatCurrency(s.surplus) + '</td>' +
            '<td>' + formatNum(s.student_count) + '</td>' +
            '<td>' + formatNum(s.employee_count) + '</td>' +
            '<td>' + s.salary_vs_revenue_pct + '%</td>' +
            '<td>' + s.student_teacher_ratio + '</td>' +
          '</tr>'
        );
      });
    }

    // 4. Render Branch Analysis Table
    const branches = resp.branch_analysis || [];
    const $brTbody = $("#rev-sal-branch-tbody");
    $brTbody.empty();
    if (branches.length === 0) {
      $brTbody.append('<tr><td colspan="8" style="text-align:center;">No branch data available for current filters.</td></tr>');
    } else {
      branches.forEach(function (b, idx) {
        $brTbody.append(
          '<tr>' +
            '<td>' + (idx + 1) + '</td>' +
            '<td><strong>' + b.branch + '</strong></td>' +
            '<td>' + formatCurrency(b.total_revenue) + '</td>' +
            '<td>' + formatCurrency(b.total_salary) + '</td>' +
            '<td>' + formatCurrency(b.surplus) + '</td>' +
            '<td>' + formatNum(b.students) + '</td>' +
            '<td>' + b.salary_vs_revenue_pct + '%</td>' +
            '<td>' + b.student_teacher_ratio + '</td>' +
          '</tr>'
        );
      });
    }
  }

  return {
    render: render
  };
})();
