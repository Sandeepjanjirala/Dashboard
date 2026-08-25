/*
 * Branch Analytics Dashboard - Phase 2 frontend.
 *
 * All numbers come from the Django REST API. This file only:
 *   - fetches filter metadata + dashboard data via jQuery AJAX
 *   - renders values it received into the DOM
 * It performs NO business calculations (no dropout %, no averages,
 * no ratios) -- those all come pre-computed from the backend.
 */

const API_BASE = "/api/dashboard/";
const FILTERS_URL = API_BASE + "filters/";

let dropoutRingChart = null;

$(document).ready(function () {
  initSidebarToggle();

  // Initial page load: get top-level filter options, then load the
  // dashboard once the dropdowns reflect them.
  loadFilters("All", "All", "All", { resetRi: true, resetZone: true, resetBranch: true }).done(function () {
    loadDashboard();
  });

  $("#agm-select").on("change", function () {
    const agm = $(this).val();
    // AGM changed -> RI, Zone and Branch must reset to All and their option
    // lists must be reloaded for the new AGM BEFORE the dashboard is
    // requested, otherwise a stale RI/Zone/Branch selection could be sent.
    loadFilters(agm, "All", "All", { resetRi: true, resetZone: true, resetBranch: true }).done(function () {
      loadDashboard();
    });
  });

  $("#ri-select").on("change", function () {
    const agm = $("#agm-select").val();
    const ri = $(this).val();
    // RI changed -> Zone and Branch must reset to All and reload for
    // AGM+RI before the dashboard is requested.
    loadFilters(agm, ri, "All", { resetZone: true, resetBranch: true }).done(function () {
      loadDashboard();
    });
  });

  $("#zone-select").on("change", function () {
    const agm = $("#agm-select").val();
    const ri = $("#ri-select").val();
    const zone = $(this).val();
    // Zone changed -> Branch must reset to All and reload for AGM+RI+Zone
    // before the dashboard is requested.
    loadFilters(agm, ri, zone, { resetBranch: true }).done(function () {
      loadDashboard();
    });
  });

  $("#branch-select").on("change", function () {
    loadDashboard();
  });

  $("#view-all-branches-btn").on("click", function () {
    branchSummaryExpanded = !branchSummaryExpanded;
    renderBranchSummaryRows();
  });
});

/* ---------------------------------------------------------------------
 * Sidebar toggle (purely presentational -- no data implications)
 * ------------------------------------------------------------------- */

function initSidebarToggle() {
  $("#sidebar-toggle").on("click", function () {
    $("body").toggleClass("sidebar-open");
  });
  // Tapping the scrim (mobile overlay backdrop) closes the sidebar again.
  $("#sidebar-scrim").on("click", function () {
    $("body").removeClass("sidebar-open");
  });
}

/* ---------------------------------------------------------------------
 * Filter metadata (AGM -> RI -> Zone -> Branch cascading dropdowns)
 * ------------------------------------------------------------------- */

// Returns the jqXHR promise so callers can chain .done() and only call
// loadDashboard() after the dropdowns have actually been updated -- this
// is what prevents the AGM/RI/Zone change race condition described in the spec.
function loadFilters(agm, ri, zone, opts) {
  opts = opts || {};
  const params = {};
  if (agm && agm !== "All") params.agm = agm;
  if (ri && ri !== "All") params.ri = ri;
  if (zone && zone !== "All") params.zone = zone;

  return $.ajax({
    url: FILTERS_URL,
    method: "GET",
    data: params,
    dataType: "json",
  })
    .done(function (resp) {
      if (!resp.success) {
        showError(resp.error || "Failed to load filters.");
        return;
      }
      populateAgmDropdown(resp.agms, agm);
      populateRiDropdown(resp.ris, opts.resetRi ? "All" : ri);
      populateZoneDropdown(resp.zones, opts.resetZone ? "All" : $("#zone-select").val());
      populateBranchDropdown(resp.branches, opts.resetBranch ? "All" : $("#branch-select").val());
    })
    .fail(function (xhr) {
      showError(extractError(xhr, "Could not load filter options."));
    });
}

function populateAgmDropdown(agms, selected) {
  const $sel = $("#agm-select");
  const current = selected || $sel.val() || "All";
  $sel.empty().append('<option value="All">All</option>');
  (agms || []).forEach(function (name) {
    $sel.append($("<option></option>").val(name).text(name));
  });
  if ($sel.find('option[value="' + cssEscape(current) + '"]').length) {
    $sel.val(current);
  } else {
    $sel.val("All");
  }
}

function populateRiDropdown(ris, selected) {
  const $sel = $("#ri-select");
  const current = selected || "All";
  $sel.empty().append('<option value="All">All</option>');
  (ris || []).forEach(function (name) {
    $sel.append($("<option></option>").val(name).text(name));
  });
  if ($sel.find('option[value="' + cssEscape(current) + '"]').length) {
    $sel.val(current);
  } else {
    $sel.val("All");
  }
}

function populateZoneDropdown(zones, selected) {
  const $sel = $("#zone-select");
  const current = selected || "All";
  $sel.empty().append('<option value="All">All</option>');
  (zones || []).forEach(function (name) {
    $sel.append($("<option></option>").val(name).text(name));
  });
  if ($sel.find('option[value="' + cssEscape(current) + '"]').length) {
    $sel.val(current);
  } else {
    $sel.val("All");
  }
}

function populateBranchDropdown(branches, selected) {
  const $sel = $("#branch-select");
  const current = selected || "All";
  $sel.empty().append('<option value="All">All</option>');
  (branches || []).forEach(function (name) {
    $sel.append($("<option></option>").val(name).text(name));
  });
  if ($sel.find('option[value="' + cssEscape(current) + '"]').length) {
    $sel.val(current);
  } else {
    $sel.val("All");
  }
}

/* ---------------------------------------------------------------------
 * Filter context (shared with the AI Assistant panel)
 *
 * Single source of truth for the AGM/RI/Branch selection the dashboard
 * is currently showing. ai-assistant.js calls this (via sendQuestion())
 * so every AI question -- typed or spoken -- automatically carries the
 * same filter scope, without duplicating any dropdown-reading logic.
 * ------------------------------------------------------------------- */

function getDashboardFilterContext() {
  const branchVal = $("#branch-select").val() || "All";
  return {
    agm: $("#agm-select").val() || "All",
    ri: $("#ri-select").val() || "All",
    zone: $("#zone-select").val() || "All",
    // #branch-select is a single <select> today, so this is always a
    // 1-element array. It's modelled as an array (not a single string) so
    // the AI request contract already supports multi-branch selection if
    // that dropdown becomes multi-select later -- no further changes
    // would be needed here or on the backend.
    branches: [branchVal],
  };
}

/* ---------------------------------------------------------------------
 * Dashboard data
 * ------------------------------------------------------------------- */

function loadDashboard() {
  const params = {
    agm: $("#agm-select").val() || "All",
    ri: $("#ri-select").val() || "All",
    zone: $("#zone-select").val() || "All",
    branch: $("#branch-select").val() || "All",
  };

  showLoading();
  hideError();

  $.ajax({
    url: API_BASE,
    method: "GET",
    data: params,
    dataType: "json",
  })
    .done(function (resp) {
      if (!resp || !resp.success) {
        showError((resp && resp.error) || "No data returned for this selection.");
        return;
      }
      renderKpis(resp.kpis);
      renderDropoutAnalysis(resp.dropout_analysis);
      renderStaffAnalysis(resp.staff_analysis);
      renderRiAnalysis(resp.ri_analysis, resp.ri_grand_total, resp.filters);
      renderBranchSummary(resp.branch_analysis, resp.filters);
    })
    .fail(function (xhr) {
      showError(extractError(xhr, "Could not load dashboard data."));
    })
    .always(function () {
      hideLoading();
    });
}

/* ---------------------------------------------------------------------
 * Renderers
 * ------------------------------------------------------------------- */

function renderKpis(kpis) {
  if (!kpis) return;

  setKpiFull("total_sections", formatNumber(kpis.total_sections.value), kpis.total_sections.ly_value);
  setKpiFull("total_class_rooms", formatNumber(kpis.total_class_rooms.value), kpis.total_class_rooms.ly_value);

  setKpiCustom("occupied_rooms", formatNumber(kpis.occupied_rooms.value),
    "Occupancy: " + formatPct(kpis.occupied_rooms.occupancy_pct));
  setKpiCustom("empty_rooms", formatNumber(kpis.empty_rooms.value),
    "Occupancy: " + formatPct(kpis.empty_rooms.vacancy_pct));

  setKpiFull("avg_strength_per_section", formatNumber(kpis.avg_strength_per_section.value), kpis.avg_strength_per_section.ly_value);

  setKpiFull("cy_dropout_percentage", formatPct(kpis.cy_dropout_percentage.value),
    kpis.cy_dropout_percentage.ly_value !== null && kpis.cy_dropout_percentage.ly_value !== undefined
      ? formatPct(kpis.cy_dropout_percentage.ly_value)
      : null);
}

// Sets a KPI card's value and, if an LY value exists, a "2024-25: X" subtitle.
// Cards where the backend returns ly_value: null show no subtitle (per spec --
// never invent an LY figure the backend didn't provide).
function setKpiFull(kpiKey, valueText, lyValue) {
  const $card = $('.kpi-card[data-kpi="' + kpiKey + '"]');
  $card.find('[data-field="value"]').text(valueText);
  const $sub = $card.find('[data-field="ly"]');
  if (lyValue === null || lyValue === undefined) {
    $sub.html("&nbsp;");
  } else {
    $sub.text("2024-25: " + lyValue);
  }
}

function setKpiCustom(kpiKey, valueText, subtitleText) {
  const $card = $('.kpi-card[data-kpi="' + kpiKey + '"]');
  $card.find('[data-field="value"]').text(valueText);
  const $sub = $card.find('[data-field="ly"]');
  if (subtitleText) {
    $sub.text(subtitleText);
  } else {
    $sub.html("&nbsp;");
  }
}

function renderDropoutAnalysis(data) {
  if (!data) return;
  const overall = data.overall;

  $("#overall-ly-pct").text(formatPct(overall.ly.dropout_pct));
  $("#overall-ly-total").text(formatNumber(overall.ly.dropouts));
  $("#overall-cy-pct").text(formatPct(overall.cy.dropout_pct));
  $("#overall-cy-total").text(formatNumber(overall.cy.dropouts));

  renderDropoutRing(overall.cy.dropout_pct);

  const $cards = $("#category-cards").empty();
  ["PP", "PS", "HS"].forEach(function (catKey) {
    const cat = data.categories[catKey];
    if (!cat) return;
    const cyPct = cat.cy.dropout_pct;
    const lyPct = cat.ly.dropout_pct;
    const trendClass = cyPct >= lyPct ? "up" : "down";
    const arrow = cyPct >= lyPct ? "&#9650;" : "&#9660;";

    const $card = $(
      '<div class="category-card">' +
        '<span class="badge ' + catKey + '">' + catKey + "</span>" +
        '<div class="cat-fullname">' + escapeHtml(cat.label) + "</div>" +
        '<div class="cat-line">No. of Sections</div>' +
        '<div class="cat-value">' + formatNumber(cat.sections) + "</div>" +
        '<div class="cat-line">Avg Strength/Section</div>' +
        '<div class="cat-value">' + formatNumber(cat.avg_strength_per_section) + "</div>" +
        '<div class="cat-line">Dropouts %</div>' +
        '<div class="cat-dropout ' + trendClass + '">' + formatPct(cyPct) + " " + arrow + "</div>" +
        '<div class="cat-ly">(2024-25: ' + formatPct(lyPct) + ")</div>" +
      "</div>"
    );
    $cards.append($card);
  });
}

function renderDropoutRing(cyPct) {
  const ctx = document.getElementById("dropout-ring-chart");
  if (!ctx || typeof Chart === "undefined") return;

  const pct = Math.max(0, Math.min(100, Number(cyPct) || 0));

  if (dropoutRingChart) {
    dropoutRingChart.data.datasets[0].data = [pct, 100 - pct];
    dropoutRingChart.update();
    return;
  }

  dropoutRingChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      datasets: [
        {
          data: [pct, 100 - pct],
          backgroundColor: ["#dc2626", "#e5e7eb"],
          borderWidth: 0,
        },
      ],
    },
    options: {
      cutout: "72%",
      responsive: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
    },
  });
}

function renderStaffAnalysis(data) {
  if (!data) return;

  const ac = data.AC; // Activity Staff
  const ad = data.AD; // Administration Staff

  if (ad) {
    $("#admin-ly").text(formatNumber(ad.ly_count));
    $("#admin-cy").text(formatNumber(ad.cy_count));
    $("#admin-diff").text(formatSignedNumber(ad.diff));
  }
  if (ac) {
    $("#activity-ly").text(formatNumber(ac.ly_count));
    $("#activity-cy").text(formatNumber(ac.cy_count));
    $("#activity-diff").text(formatSignedNumber(ac.diff));
  }

  const str = data.student_teacher_ratio || {};
  const $ratioCards = $("#ratio-cards").empty();

  const ratioLabels = {
    PP: "Pre Primary Ratio",
    PS: "Primary Ratio",
    HS: "High School Ratio",
    overall: "Overall Ratio",
  };

  ["PP", "PS", "HS"].forEach(function (key) {
    const block = str[key];
    if (!block) return;
    const $card = $(
      '<div class="ratio-card">' +
        '<div class="ratio-title">' + ratioLabels[key] + "</div>" +
        '<div class="ratio-sub">Teacher Student Ratio</div>' +
        '<div class="ratio-values">' +
          '<span class="ratio-value-cy">' + formatNumber(block.cy_ratio) + "</span>" +
          '<span class="ratio-value-ly">(' + formatNumber(block.ly_ratio) + ")</span>" +
        "</div>" +
        '<div class="ratio-years">' +
          "<span>(2024-25)</span>" +
          "<span>(2025-26)</span>" +
        "</div>" +
        '<div class="ratio-staffcount">' +
          "24-25 Staff Count: <strong>" + formatNumber(block.ly_staff_count) + "</strong>" +
        "</div>" +
        '<div class="ratio-staffcount">' +
          "25-26 Staff Count: <strong>" + formatNumber(block.cy_staff_count) + "</strong>" +
        "</div>" +
        '<div class="ratio-diff">' + formatSignedNumber(block.diff) + "</div>" +
      "</div>"
    );
    $ratioCards.append($card);
  });

  const overallStr = str.overall;
  if (overallStr) {
    $("#overall-cy-ratio").text(formatNumber(overallStr.cy_ratio));
    $("#overall-ly-ratio").text(formatNumber(overallStr.ly_ratio));
    // Overall Student/Teacher Count comes straight from the backend's
    // overall CY-SC / LY-SC aggregation -- NOT a sum of Activity + Admin
    // staff counts (AC and AD are separate categories, rendered above).
    $("#overall-cy-staff-count").text(formatNumber(overallStr.cy_staff_count));
    $("#overall-ly-staff-count").text(formatNumber(overallStr.ly_staff_count));
  }
}

function renderRiAnalysis(rows, grandTotal, filters) {
  const $body = $("#ri-analysis-body").empty();
  const $title = $("#ri-analysis-title");

  if (!rows || rows.length === 0) {
    $body.append('<tr><td colspan="5" class="empty-row">No data for this selection</td></tr>');
    $("#ri-analysis-total").empty();
    return;
  }

  const isSingleRi = filters && filters.ri && filters.ri !== "All";
  $title.text(isSingleRi ? "RI Wise Dropout Analysis" : "Top 8 RI Wise Dropout Analysis");

  // `rows` is already sorted by CY dropouts descending (see
  // dashboard_service.build_ri_analysis). Showing only the top 8 is a
  // display cap, not a data change -- the Grand Total row below still
  // sums the full filtered set via `grandTotal`, exactly as the backend
  // computed it, regardless of how many rows are shown here.
  const displayRows = isSingleRi ? rows : rows.slice(0, 8);

  displayRows.forEach(function (row) {
    $body.append(
      "<tr>" +
        "<td>" + escapeHtml(row.ri_name) + "</td>" +
        "<td>" + formatNumber(row.cy_dropouts) + "</td>" +
        "<td>" + formatPct(row.dropout_pct) + "</td>" +
        "<td>" + formatNumber(row.student_teacher_ratio) + "</td>" +
        "<td>" + formatNumber(row.empty_rooms) + "</td>" +
      "</tr>"
    );
  });

  // Grand Total row is rendered exactly as returned by the backend
  // (SUM(CY-DP)/SUM(CY-GS), SUM(CY-NS)/SUM(CY-SC), SUM(NOVR)) -- no
  // percentage or ratio math happens here in JavaScript.
  if (grandTotal) {
    $("#ri-analysis-total").html(
      "<td>Grand Total</td>" +
      "<td>" + formatNumber(grandTotal.cy_dropouts) + "</td>" +
      "<td>" + formatPct(grandTotal.dropout_pct) + "</td>" +
      "<td>" + formatNumber(grandTotal.student_teacher_ratio) + "</td>" +
      "<td>" + formatNumber(grandTotal.empty_rooms) + "</td>"
    );
  } else {
    $("#ri-analysis-total").empty();
  }
}

let lastBranchRows = [];
let branchSummaryExpanded = false;

function renderBranchSummary(rows, filters) {
  lastBranchRows = rows || [];
  branchSummaryExpanded = false;
  renderBranchSummaryRows();
}

function renderBranchSummaryRows() {
  const rows = lastBranchRows;
  const $body = $("#branch-summary-body").empty();
  const $btn = $("#view-all-branches-btn");

  if (!rows || rows.length === 0) {
    $body.append('<tr><td colspan="5" class="empty-row">No data for this selection</td></tr>');
    $("#branch-count-note").text("");
    $btn.hide();
    return;
  }

  const BRANCH_PREVIEW_COUNT = 5;
  const displayRows = branchSummaryExpanded ? rows : rows.slice(0, BRANCH_PREVIEW_COUNT);

  displayRows.forEach(function (row) {
    $body.append(
      "<tr>" +
        "<td>" + escapeHtml(row.branch_name) + "</td>" +
        "<td>" + formatNumber(row.cy_dropouts) + "</td>" +
        "<td>" + formatPct(row.dropout_pct) + "</td>" +
        "<td>" + formatNumber(row.student_teacher_ratio) + "</td>" +
        "<td>" + formatNumber(row.empty_rooms) + "</td>" +
      "</tr>"
    );
  });

  $("#branch-count-note").text(
    branchSummaryExpanded
      ? "Showing all " + rows.length + " branch" + (rows.length === 1 ? "" : "es") + "."
      : "Showing " + displayRows.length + " of " + rows.length + " branches."
  );

  // Only worth showing the toggle when there's actually more to reveal --
  // real data already fetched, just displayed progressively.
  if (rows.length > BRANCH_PREVIEW_COUNT) {
    $btn.show().html(
      branchSummaryExpanded
        ? "Show Less"
        : 'View All Branches <span aria-hidden="true">&rarr;</span>'
    );
  } else {
    $btn.hide();
  }
}

/* ---------------------------------------------------------------------
 * Loading / error UI
 * ------------------------------------------------------------------- */

function showLoading() {
  $("#loading-overlay").show();
}
function hideLoading() {
  $("#loading-overlay").hide();
}
function showError(message) {
  $("#error-banner").text(message).show();
}
function hideError() {
  $("#error-banner").hide().text("");
}

function extractError(xhr, fallback) {
  if (xhr && xhr.responseJSON && xhr.responseJSON.error) {
    return xhr.responseJSON.error;
  }
  if (xhr && xhr.status === 0) {
    return "Network error: could not reach the server.";
  }
  return fallback;
}

/* ---------------------------------------------------------------------
 * Formatting helpers (display only -- never changes underlying values)
 * ------------------------------------------------------------------- */

function formatNumber(value) {
  if (value === null || value === undefined) return "--";
  const num = Number(value);
  if (Number.isNaN(num)) return "--";
  if (Number.isInteger(num)) return num.toLocaleString("en-IN");
  return num.toLocaleString("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function formatSignedNumber(value) {
  if (value === null || value === undefined) return "--";
  const num = Number(value);
  if (Number.isNaN(num)) return "--";
  return (num > 0 ? "+" : "") + num.toLocaleString("en-IN");
}

function formatPct(value) {
  if (value === null || value === undefined) return "--";
  const num = Number(value);
  if (Number.isNaN(num)) return "--";
  return num.toLocaleString("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
}

function escapeHtml(str) {
  return $("<div></div>").text(str == null ? "" : str).html();
}

function cssEscape(value) {
  return String(value).replace(/(["\\])/g, "\\$1");
}
