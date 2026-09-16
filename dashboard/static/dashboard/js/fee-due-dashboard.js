/*
 * Fee Due Analysis Dashboard - Client-side UI Renderer module.
 *
 * Renders 8 KPI cards, 5 Chart.js visual instances, dynamic key insights,
 * and breakdown tables (Overview, AGM, RI, Zone, Branch) from the payload
 * returned by GET /api/dashboard/fee-due/.
 */

const FeeDueDashboard = (function () {
  let feeAmtChart = null;
  let feeCntChart = null;
  let feeSegChart = null;
  let feeTopChart = null;
  let feeTypeChart = null;

  let currentBreakdowns = null;
  let currentSubtab = "overview";

  function render(payload) {
    if (!payload || !payload.success) return;

    renderKpis(payload.kpis);
    renderCharts(payload.charts);
    renderInsights(payload.key_insights);

    currentBreakdowns = payload.breakdowns;
    renderBreakdownTable(currentSubtab);
  }

  /* ---------------------------------------------------------------------
   * 1. KPI Cards (8 Cards)
   * ------------------------------------------------------------------- */
  function renderKpis(kpis) {
    if (!kpis) return;

    // 1. 2024-25 Fee Due
    setFeeKpiText("fee-kpi-ly-fd", formatCurrency(kpis.ly_fee_due.value));

    // 2. 2024-25 Due Count
    setFeeKpiText("fee-kpi-ly-fdc", formatInt(kpis.ly_due_count.value));

    // 3. 2025-26 Live Student Fee Due
    setFeeKpiText("fee-kpi-cy-fd", formatCurrency(kpis.cy_live_student_fee_due.value));
    setFeeKpiBadge("fee-kpi-cy-fd-badge", kpis.cy_live_student_fee_due);

    // 4. 2025-26 Live Student Due Count
    setFeeKpiText("fee-kpi-cy-fdc", formatInt(kpis.cy_live_student_due_count.value));
    setFeeKpiBadge("fee-kpi-cy-fdc-badge", kpis.cy_live_student_due_count);

    // 5. Actual Zero Paid Count
    setFeeKpiText("fee-kpi-zp-count", formatInt(kpis.actual_zero_paid_count.value));

    // 6. Current Year Zero Paid Fee Due
    setFeeKpiText("fee-kpi-zp-fd", formatCurrency(kpis.cy_zero_paid_fee_due.value));

    // 7. Fee Paid But Books Not Purchased
    setFeeKpiText("fee-kpi-fp-bn", formatInt(kpis.fee_paid_books_not_purchased.value));

    // 8. Fee Not Paid & Books Not Purchased
    setFeeKpiText("fee-kpi-fn-bn", formatInt(kpis.fee_not_paid_books_not_purchased.value));
  }

  function setFeeKpiText(elemId, text) {
    $("#" + elemId).text(text);
  }

  function setFeeKpiBadge(elemId, kpiObj) {
    const $b = $("#" + elemId);
    if (!kpiObj || kpiObj.yoy_change_pct === undefined) {
      $b.hide();
      return;
    }
    const pct = Math.abs(kpiObj.yoy_change_pct);
    const dir = kpiObj.yoy_direction || "down";
    const arrow = dir === "down" ? "↓" : "↑";
    const cssClass = dir === "down" ? "badge-good" : "badge-warn";
    $b.removeClass("badge-good badge-warn")
      .addClass(cssClass)
      .html(arrow + " " + pct + "% vs 2024-25")
      .show();
  }

  /* ---------------------------------------------------------------------
   * 2. Charts (Chart.js)
   * ------------------------------------------------------------------- */
  function renderCharts(charts) {
    if (!charts) return;

    renderAmountCompChart(charts.fee_due_comparison_amount || []);
    renderCountCompChart(charts.fee_due_comparison_count || []);
    renderSegmentationChart(charts.student_segmentation || {});
    renderTop5Chart(charts.top_5_branches_fee_due || []);
    renderTypeChart(charts.branch_type_wise_fee_due || []);
  }

  // 1. Fee Due Comparison (Amount) - Bar
  function renderAmountCompChart(data) {
    const ctx = document.getElementById("chart-fee-amount-comp");
    if (!ctx || typeof Chart === "undefined") return;

    const labels = data.map(d => d.branch);
    const lyData = data.map(d => d.ly_fee_due);
    const cyData = data.map(d => d.cy_fee_due);

    if (feeAmtChart) {
      feeAmtChart.data.labels = labels;
      feeAmtChart.data.datasets[0].data = lyData;
      feeAmtChart.data.datasets[1].data = cyData;
      feeAmtChart.update();
      return;
    }

    feeAmtChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          { label: "2024-25 Fee Due", data: lyData, backgroundColor: "#1e40af", borderRadius: 4 },
          { label: "2025-26 Live Student Fee Due", data: cyData, backgroundColor: "#38bdf8", borderRadius: 4 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "top" },
          tooltip: {
            callbacks: {
              label: function (c) {
                return c.dataset.label + ": " + formatCurrency(c.raw);
              },
            },
          },
        },
        scales: {
          y: {
            ticks: {
              callback: function (val) {
                return formatShortCurrency(val);
              },
            },
          },
        },
      },
    });
  }

  // 2. Fee Due Comparison (Count) - Bar
  function renderCountCompChart(data) {
    const ctx = document.getElementById("chart-fee-count-comp");
    if (!ctx || typeof Chart === "undefined") return;

    const labels = data.map(d => d.branch);
    const lyData = data.map(d => d.ly_due_count);
    const cyData = data.map(d => d.cy_due_count);

    if (feeCntChart) {
      feeCntChart.data.labels = labels;
      feeCntChart.data.datasets[0].data = lyData;
      feeCntChart.data.datasets[1].data = cyData;
      feeCntChart.update();
      return;
    }

    feeCntChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          { label: "2024-25 Due Count", data: lyData, backgroundColor: "#1e3a8a", borderRadius: 4 },
          { label: "2025-26 Live Student Due Count", data: cyData, backgroundColor: "#60a5fa", borderRadius: 4 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "top" } },
        scales: { y: { beginAtZero: true } },
      },
    });
  }

  // 3. Student Segmentation (Donut)
  function renderSegmentationChart(seg) {
    const ctx = document.getElementById("chart-fee-student-seg");
    if (!ctx || typeof Chart === "undefined") return;

    const zp = seg.actual_zero_paid || 0;
    const nonZp = seg.non_zero_paid || 0;
    const total = seg.total_students || 0;

    $("#fee-seg-center-total").text(formatInt(total));

    if (feeSegChart) {
      feeSegChart.data.datasets[0].data = [zp, nonZp];
      feeSegChart.update();
      return;
    }

    feeSegChart = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: ["Actual Zero Paid", "Non Zero Paid"],
        datasets: [
          {
            data: [zp, nonZp],
            backgroundColor: ["#ef4444", "#3b82f6"],
            borderWidth: 0,
          },
        ],
      },
      options: {
        cutout: "70%",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom" },
        },
      },
    });
  }

  // 4. Top 5 Branches by Fee Due - H-Bar
  function renderTop5Chart(data) {
    const ctx = document.getElementById("chart-fee-top5");
    if (!ctx || typeof Chart === "undefined") return;

    const labels = data.map(d => d.branch);
    const liveData = data.map(d => d.live_student_fee_due);
    const zpData = data.map(d => d.zero_paid_fee_due);

    if (feeTopChart) {
      feeTopChart.data.labels = labels;
      feeTopChart.data.datasets[0].data = liveData;
      feeTopChart.data.datasets[1].data = zpData;
      feeTopChart.update();
      return;
    }

    feeTopChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          { label: "Live Student Fee Due", data: liveData, backgroundColor: "#2563eb", borderRadius: 4 },
          { label: "Zero Paid Fee Due", data: zpData, backgroundColor: "#93c5fd", borderRadius: 4 },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "top" },
          tooltip: {
            callbacks: {
              label: function (c) {
                return c.dataset.label + ": " + formatCurrency(c.raw);
              },
            },
          },
        },
        scales: {
          x: {
            ticks: {
              callback: function (val) {
                return formatShortCurrency(val);
              },
            },
          },
        },
      },
    });
  }

  // 5. Branch Type Wise Fee Due (S_Type) - Donut
  function renderTypeChart(data) {
    const ctx = document.getElementById("chart-fee-type-wise");
    if (!ctx || typeof Chart === "undefined") return;

    const labels = data.map(d => d.type);
    const values = data.map(d => d.fee_due);
    const colors = ["#2563eb", "#f97316", "#64748b", "#10b981"];

    if (feeTypeChart) {
      feeTypeChart.data.labels = labels;
      feeTypeChart.data.datasets[0].data = values;
      feeTypeChart.update();
      return;
    }

    feeTypeChart = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [
          {
            data: values,
            backgroundColor: colors.slice(0, labels.length),
            borderWidth: 0,
          },
        ],
      },
      options: {
        cutout: "65%",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              label: function (c) {
                return c.label + ": " + formatCurrency(c.raw);
              },
            },
          },
        },
      },
    });
  }

  /* ---------------------------------------------------------------------
   * 3. Key Insights Panel
   * ------------------------------------------------------------------- */
  function renderInsights(insights) {
    const $container = $("#fee-insights-list").empty();
    if (!insights || insights.length === 0) {
      $container.append('<div class="insight-item">No key insights calculated for this selection.</div>');
      return;
    }

    insights.forEach(function (item) {
      const iconSvg = getInsightIconSvg(item.direction);
      const $el = $(
        '<div class="insight-item">' +
          '<div class="insight-icon ' + escapeHtml(item.direction) + '">' + iconSvg + '</div>' +
          '<div class="insight-text">' + escapeHtml(item.text) + '</div>' +
        '</div>'
      );
      $container.append($el);
    });
  }

  function getInsightIconSvg(dir) {
    if (dir === "down") {
      return '<svg viewBox="0 0 24 24"><path d="M12 5v14M19 12l-7 7-7-7"/></svg>';
    }
    if (dir === "up") {
      return '<svg viewBox="0 0 24 24"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
    }
    if (dir === "warning" || dir === "alert") {
      return '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg>';
    }
    return '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/></svg>';
  }

  /* ---------------------------------------------------------------------
   * 4. Breakdown Table (Overview, AGM, RI, Zone, Branch)
   * ------------------------------------------------------------------- */
  function setSubtab(tabName) {
    currentSubtab = tabName;
    $(".fee-subtab-btn").removeClass("active");
    $('.fee-subtab-btn[data-tab="' + tabName + '"]').addClass("active");
    renderBreakdownTable(tabName);
  }

  function renderBreakdownTable(tabName) {
    const $thead = $("#fee-table-head").empty();
    const $tbody = $("#fee-table-body").empty();

    if (!currentBreakdowns) {
      $tbody.append('<tr><td colspan="8" class="text-center">No data available</td></tr>');
      return;
    }

    const keyMap = {
      overview: { data: currentBreakdowns.overview, nameHeader: "Branch", nameKey: "branch_name" },
      agm_analysis: { data: currentBreakdowns.agm_analysis, nameHeader: "AGM Name", nameKey: "agm_name" },
      ri_analysis: { data: currentBreakdowns.ri_analysis, nameHeader: "RI Name", nameKey: "ri_name" },
      zone_analysis: { data: currentBreakdowns.zone_analysis, nameHeader: "Zone", nameKey: "zone_name" },
      branch_analysis: { data: currentBreakdowns.branch_analysis, nameHeader: "Branch Name", nameKey: "branch_name" },
    };

    const cfg = keyMap[tabName] || keyMap["overview"];
    const rows = cfg.data || [];

    // Table Header
    const $hr = $(
      "<tr>" +
        '<th class="text-left">' + cfg.nameHeader + "</th>" +
        '<th class="text-right">2024-25 Fee Due</th>' +
        '<th class="text-right">2024-25 Due Count</th>' +
        '<th class="text-right">2025-26 Live Fee Due</th>' +
        '<th class="text-right">2025-26 Live Due Count</th>' +
        '<th class="text-right">Actual Zero Paid</th>' +
        '<th class="text-right">Zero Paid Fee Due</th>' +
        '<th class="text-right">Books Not Purchased</th>' +
      "</tr>"
    );
    $thead.append($hr);

    if (rows.length === 0) {
      $tbody.append('<tr><td colspan="8" class="text-center">No data for this selection</td></tr>');
      return;
    }

    rows.forEach(function (r) {
      const nameVal = r[cfg.nameKey] || "--";
      const booksNotBought = (r.fee_paid_books_not_purchased || 0) + (r.fee_not_paid_books_not_purchased || 0);

      const $row = $(
        "<tr>" +
          '<td class="text-left font-medium">' + escapeHtml(nameVal) + "</td>" +
          '<td class="text-right">' + formatCurrency(r.ly_fee_due) + "</td>" +
          '<td class="text-right">' + formatInt(r.ly_due_count) + "</td>" +
          '<td class="text-right font-medium text-blue">' + formatCurrency(r.cy_live_student_fee_due) + "</td>" +
          '<td class="text-right">' + formatInt(r.cy_live_student_due_count) + "</td>" +
          '<td class="text-right text-red">' + formatInt(r.actual_zero_paid_count) + "</td>" +
          '<td class="text-right">' + formatCurrency(r.cy_zero_paid_fee_due) + "</td>" +
          '<td class="text-right">' + formatInt(booksNotBought) + "</td>" +
        "</tr>"
      );
      $tbody.append($row);
    });
  }

  /* ---------------------------------------------------------------------
   * Helper Formatters
   * ------------------------------------------------------------------- */
  function formatCurrency(val) {
    if (val === null || val === undefined) return "--";
    const num = Number(val);
    if (isNaN(num)) return "--";
    if (num >= 10000000) {
      return "\u20b9" + (num / 10000000).toFixed(2) + " Cr";
    }
    if (num >= 100000) {
      return "\u20b9" + (num / 100000).toFixed(2) + " L";
    }
    return "\u20b9" + num.toLocaleString("en-IN");
  }

  function formatShortCurrency(val) {
    const num = Number(val);
    if (isNaN(num)) return "0";
    if (num >= 1000000) return (num / 1000000).toFixed(1) + "M";
    if (num >= 1000) return (num / 1000).toFixed(0) + "K";
    return String(num);
  }

  function formatInt(val) {
    if (val === null || val === undefined) return "--";
    const num = Number(val);
    if (isNaN(num)) return "--";
    return num.toLocaleString("en-IN");
  }

  function escapeHtml(str) {
    return $("<div></div>").text(str == null ? "" : str).html();
  }

  return {
    render: render,
    setSubtab: setSubtab,
  };
})();
