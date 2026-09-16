/*
 * AI Assistant chat panel.
 *
 * This file communicates with branch_dashboard's API (POST /api/dashboard/ask-ai/).
 * It sends questions and current filter context, and handles intent-aware responses:
 *
 * - dashboard_filter / dashboard_reset → apply filter command to dropdowns
 *   then refresh the dashboard (no text response for filter commands by default)
 * - dashboard_filter_and_query → apply filters silently, then show analytical result
 * - dashboard_query → show analytical result table or text bubble
 * - clarification_required / unknown → show text message bubble
 *
 * Voice and text input both flow through the same sendQuestion() entry point.
 */

const ASK_AI_URL = "/api/dashboard/ask-ai/";

$(document).ready(function () {
  initResizer();

  $("#ai-input-row").on("submit", function (e) {
    e.preventDefault();

    const $input = $("#ai-question-input");
    const question = $input.val().trim();
    if (!question) return;

    $input.val("").blur();
    sendQuestion(question);
  });

  initVoiceInput();
});

function initResizer() {
  const resizer = document.getElementById('resizer');
  const aiPanel = document.getElementById('ai-panel');
  let isDragging = false;

  if (resizer && aiPanel) {
    resizer.addEventListener('mousedown', (e) => {
      isDragging = true;
      resizer.classList.add('dragging');
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      const windowWidth = window.innerWidth;
      let newWidth = windowWidth - e.clientX;
      if (newWidth < 250) newWidth = 250;
      const maxAllowed = Math.max(300, windowWidth - 60);
      if (newWidth > maxAllowed) newWidth = maxAllowed;
      aiPanel.style.width = `${newWidth}px`;
      document.documentElement.style.setProperty('--ai-panel-w', `${newWidth}px`);
    });

    document.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        resizer.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    });
  }
}

/*
 * Single shared entry point for asking the AI assistant a question.
 * Called identically by typed input and voice input.
 */
function sendQuestion(question) {
  question = (question || "").trim();
  if (!question) return;

  appendUserMessage(question);
  setSending(true);

  // Attach the dashboard's current AGM/RI/Zone/Branch selection
  const filters = (typeof getDashboardFilterContext === "function")
    ? getDashboardFilterContext()
    : { agm: "All", ri: "All", zone: "All", branches: ["All"] };

  $.ajax({
    url: ASK_AI_URL,
    method: "POST",
    contentType: "application/json",
    data: JSON.stringify({ question: question, filters: filters }),
    dataType: "json",
  })
    .done(function (resp) {
      handleAiResponse(resp);
    })
    .fail(function (xhr) {
      // Try to extract intent-aware error from the body
      const body = xhr.responseJSON || {};
      if (body.intent === "unknown") {
        appendBotMessage(body.answer || "I can't answer that from the current dashboard data.", true, null);
        return;
      }
      const msg =
        body.answer ||
        body.error ||
        "The AI assistant is currently unavailable. Please try again.";
      appendBotMessage(msg, true, null);
    })
    .always(function () {
      setSending(false);
    });
}

/*
 * Route the API response based on intent.
 */
function handleAiResponse(resp) {
  if (!resp) {
    appendBotMessage("No response received.", true, null);
    return;
  }

  const intent = resp.intent || "dashboard_query";

  // ------------------------------------------------------------------
  // dashboard_reset / dashboard_filter → apply to dropdowns and refresh
  // ------------------------------------------------------------------
  if (intent === "dashboard_reset" || intent === "dashboard_filter") {
    if (resp.command && resp.command.filters) {
      applyDashboardCommand(resp.command.filters, resp.answer || "Done.");
    } else {
      appendBotMessage(resp.answer || "Done.", false, null);
    }
    return;
  }

  // ------------------------------------------------------------------
  // dashboard_filter_and_query → apply filter silently, then show result
  // ------------------------------------------------------------------
  if (intent === "dashboard_filter_and_query") {
    if (resp.command && resp.command.filters) {
      // Apply the filter change silently (no AI bubble for the filter part)
      applyDashboardCommand(resp.command.filters, null);
    }
    // Then show the analytical result
    const isError = !resp.success;
    const answerText = resp.answer || "No response received.";
    appendBotMessage(answerText, isError, resp.data || null);
    return;
  }

  // ------------------------------------------------------------------
  // clarification_required → ask the user a follow-up question
  // ------------------------------------------------------------------
  if (intent === "clarification_required") {
    appendBotMessage(resp.answer || "Could you clarify your request?", false, null);
    return;
  }

  // ------------------------------------------------------------------
  // dashboard_query (and unknown, and any unrecognised intent)
  // ------------------------------------------------------------------
  const isError = !resp.success;
  const answerText = resp.answer || "No response received.";
  appendBotMessage(answerText, isError, resp.data || null);
}

/*
 * Apply a filter command from the AI to the actual dashboard dropdowns,
 * then trigger a cascading reload.
 *
 * Respects the full cascade hierarchy:
 *   AGM changed → reset RI, Zone, Branch → loadFilters → loadDashboard
 *   RI changed  → reset Zone, Branch → loadFilters → loadDashboard
 *   Zone changed → reset Branch → loadFilters → loadDashboard
 *   Branch changed → loadDashboard only
 *
 * confirmText: if non-null, shows a confirmation bubble in the AI panel.
 */
function applyDashboardCommand(newFilters, confirmText) {
  if (!newFilters) return;

  const currentAgm  = (typeof getDashboardFilterContext === "function")
    ? getDashboardFilterContext().agm  : "All";
  const currentRi   = (typeof getDashboardFilterContext === "function")
    ? getDashboardFilterContext().ri   : "All";
  const currentZone = (typeof getDashboardFilterContext === "function")
    ? getDashboardFilterContext().zone : "All";

  const newAgm    = newFilters.agm    || "All";
  const newRi     = newFilters.ri     || "All";
  const newZone   = newFilters.zone   || "All";
  const newBranches = newFilters.branches || ["All"];
  const newBranch = (Array.isArray(newBranches) && newBranches.length > 0)
    ? newBranches[0]
    : "All";

  // Determine the highest-changed level so we know how far to cascade.
  const agmChanged    = newAgm  !== currentAgm;
  const riChanged     = newRi   !== currentRi;
  const zoneChanged   = newZone !== currentZone;

  // Programmatically set the select values.
  // These calls do NOT fire the jQuery .on("change") handlers (which call
  // loadFilters/loadDashboard again), because we use .val() not .trigger().
  // We will call loadFilters/loadDashboard ourselves below.
  setSelectValue("#agm-select",    newAgm);
  setSelectValue("#ri-select",     agmChanged  ? "All" : newRi);
  setSelectValue("#zone-select",   (agmChanged || riChanged) ? "All" : newZone);
  setSelectValue("#branch-select", (agmChanged || riChanged || zoneChanged) ? "All" : newBranch);

  // Determine cascading reload options.
  const resetRi     = agmChanged;
  const resetZone   = agmChanged || riChanged;
  const resetBranch = agmChanged || riChanged || zoneChanged;

  // After updating the select values, show confirmation and reload.
  const reloadAgm  = newAgm  !== "All" ? newAgm  : "";
  const reloadRi   = (!agmChanged && newRi   !== "All") ? newRi   : "";
  const reloadZone = (!agmChanged && !riChanged && newZone !== "All") ? newZone : "";

  // Use the existing loadFilters / loadDashboard from dashboard.js.
  if (typeof loadFilters === "function") {
    loadFilters(newAgm, resetRi ? "All" : newRi, resetZone ? "All" : newZone, {
      resetRi:     resetRi,
      resetZone:   resetZone,
      resetBranch: resetBranch,
    }).done(function () {
      // After dropdown options are refreshed, set the final branch value
      // (the list may have changed after the filter cascade).
      if (!resetBranch) {
        setSelectValue("#branch-select", newBranch);
      }
      if (typeof loadDashboard === "function") {
        loadDashboard();
      }
    });
  } else if (typeof loadDashboard === "function") {
    loadDashboard();
  }

  // Show confirmation bubble (after a short tick so the dashboard starts loading first).
  if (confirmText) {
    setTimeout(function () {
      appendBotMessage(confirmText, false, null);
    }, 80);
  }
}

/*
 * Safely set a <select> element's value, but only if that option actually
 * exists in the dropdown.  Falls back to "All" if not found.
 */
function setSelectValue(selector, value) {
  const $sel = $(selector);
  if (!$sel.length) return;
  const target = (value && value !== "") ? value : "All";
  // If the option exists, set it; otherwise fall back to "All".
  if ($sel.find('option[value="' + cssEscapeAI(target) + '"]').length) {
    $sel.val(target);
  } else {
    $sel.val("All");
  }
}

function cssEscapeAI(value) {
  return String(value).replace(/(["\\])/g, "\\$1");
}

function appendUserMessage(text) {
  const $wrap = $('<div class="ai-msg ai-msg-user"></div>');
  $wrap.append($('<div class="ai-msg-bubble"></div>').text(text));
  $("#ai-messages").append($wrap);
  scrollToMessageStart($wrap);
}

/**
 * Check if the response contains tabular data suitable for rendering as a result table.
 */
function hasValidTableData(data) {
  if (!data) return false;
  const rows = Array.isArray(data)
    ? data
    : data && Array.isArray(data.rows)
      ? data.rows
      : null;

  if (!rows || rows.length === 0) return false;
  if (typeof rows[0] !== "object" || rows[0] === null) return false;

  const keys = Object.keys(rows[0]);
  // If it's only a single count or single scalar key, text answer is preferred
  if (rows.length === 1 && keys.length === 1 && (keys[0] === "count" || keys[0] === "metric")) {
    return false;
  }

  return true;
}

/**
 * Render Bot response using full 5-Layer Markdown structure:
 * - Direct Answer, Key Metrics, Key Findings, Attention Areas, Evidence Table
 */
function appendBotMessage(text, isError, data) {
  const $wrap = $('<div class="ai-msg ai-msg-bot' + (isError ? " ai-msg-error" : "") + '"></div>');
  const $bubble = $('<div class="ai-msg-bubble markdown-body"></div>');

  if (!isError && text) {
    if (typeof marked !== "undefined" && typeof marked.parse === "function") {
      $bubble.html(marked.parse(text));
    } else {
      $bubble.text(text);
    }
  } else {
    $bubble.text(text || "No response received.");
  }

  $wrap.append($bubble);
  $("#ai-messages").append($wrap);
  scrollToMessageStart($wrap);
}

/**
 * Professional BI Result Table Renderer
 */
function renderAiDataTable(data) {
  const rows = Array.isArray(data)
    ? data
    : data && Array.isArray(data.rows)
      ? data.rows
      : null;

  if (!rows || rows.length === 0 || typeof rows[0] !== "object" || rows[0] === null) {
    return null;
  }

  // Filter out internal / non-display keys if any
  const rawColumns = Object.keys(rows[0]);
  const columns = rawColumns.filter(function (col) {
    return !col.startsWith("_") && col !== "abs_change";
  });

  if (columns.length === 0) return null;

  const $tableWrapper = $('<div class="ai-table-scroll"></div>');
  const $table = $('<table class="ai-data-table"></table>');

  // Header
  const $headRow = $("<tr></tr>");
  columns.forEach(function (col) {
    const alignClass = getColumnAlignment(col, rows);
    $headRow.append($('<th class="' + alignClass + '"></th>').text(formatColumnHeader(col)));
  });
  $table.append($("<thead></thead>").append($headRow));

  // Body
  const $tbody = $("<tbody></tbody>");
  rows.forEach(function (row) {
    const $tr = $("<tr></tr>");
    columns.forEach(function (col) {
      const alignClass = getColumnAlignment(col, rows);
      const formattedVal = formatCellValue(col, row[col]);
      $tr.append($('<td class="' + alignClass + '"></td>').text(formattedVal));
    });
    $tbody.append($tr);
  });
  $table.append($tbody);
  $tableWrapper.append($table);

  return $tableWrapper;
}

/**
 * Determine column text alignment (left for names/groups, center for rank, right for numbers)
 */
function getColumnAlignment(col, rows) {
  const key = col.toLowerCase();
  if (key === "rank") return "text-center";
  if (key === "branch" || key === "branch_name" || key === "group" || key === "category" || key === "ri_name" || key === "agm_name" || key === "zone") {
    return "text-left";
  }

  // Check if first non-null value is number
  for (let i = 0; i < rows.length; i++) {
    const val = rows[i][col];
    if (val !== null && val !== undefined) {
      if (typeof val === "number" || !isNaN(Number(val))) {
        return "text-right";
      }
      break;
    }
  }

  return "text-left";
}

/**
 * Format column header nicely
 */
function formatColumnHeader(col) {
  const key = col.toLowerCase();
  const knownHeaders = {
    "rank": "Rank",
    "branch": "Branch",
    "branch_name": "Branch",
    "group": "Group",
    "category": "Category",
    "dropout_percentage": "Dropout %",
    "dropout_pct": "Dropout %",
    "dpp": "Dropout %",
    "cy-dpp": "CY Dropout %",
    "ly-dpp": "LY Dropout %",
    "pp-cy-dpp": "PP Dropout %",
    "ps-cy-dpp": "PS Dropout %",
    "hs-cy-dpp": "HS Dropout %",
    "dropouts": "Dropouts",
    "cy_dropouts": "CY Dropouts",
    "dp": "Dropouts",
    "current_year": "Current Year",
    "last_year": "Last Year",
    "change": "Change",
    "value": "Value",
    "net_strength": "Net Strength",
    "ns": "Net Strength",
    "cy-ns": "CY Net Strength",
    "ly-ns": "LY Net Strength",
    "grant_strength": "Grant Strength",
    "gs": "Grant Strength",
    "sections": "Sections",
    "nos": "Sections",
    "avg-sps": "Avg SPS",
    "student_teacher_ratio": "STR",
    "str": "STR",
    "cy-str": "CY STR",
    "ly-str": "LY STR",
    "staff_count": "Staff Count",
    "sc": "Staff Count",
    "cy-sc": "CY Staff Count",
    "ly-sc": "LY Staff Count",
    "nocr": "Class Rooms",
    "noor": "Occupied Rooms",
    "novr": "Empty Rooms",
    "percentage": "Percentage",
    "occupancy_pct": "Occupancy %",
    "vacancy_pct": "Vacancy %",
  };

  if (knownHeaders[key]) return knownHeaders[key];

  return String(col)
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
}

/**
 * Format cell value based on column type
 */
function formatCellValue(col, value) {
  if (value === null || value === undefined) return "--";

  const key = col.toLowerCase();
  const num = Number(value);

  if (isNaN(num)) {
    return String(value);
  }

  // Rank
  if (key === "rank") {
    return String(Math.round(num));
  }

  // Change (signed delta)
  if (key === "change" || key.endsWith("_diff") || key === "diff") {
    const sign = num > 0 ? "+" : "";
    return sign + num.toFixed(2);
  }

  // Percentages
  if (key.includes("percentage") || key.includes("pct") || key.includes("dpp") || key === "percentage") {
    return num.toFixed(2) + "%";
  }

  // Integer counts (rooms, sections, dropouts if whole number)
  if (Number.isInteger(num)) {
    return num.toLocaleString("en-IN");
  }

  // Floating point values (ratios, averages)
  return num.toLocaleString("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
}

function setSending(isSending) {
  $("#ai-send-btn").prop("disabled", isSending);
  $("#ai-question-input").prop("disabled", isSending);
}

function scrollToMessageStart($elem) {
  const $messages = $("#ai-messages");
  if (!$messages.length || !$elem || !$elem.length) return;

  function doScroll() {
    const container = $messages[0];
    const elemNode = $elem[0];
    if (!container || !elemNode) return;

    const targetTop = Math.max(0, elemNode.offsetTop - 10);
    container.scrollTop = targetTop;
  }

  doScroll();
  requestAnimationFrame(doScroll);
  setTimeout(doScroll, 50);
  setTimeout(doScroll, 200);
}

/* ==========================================================================
 * Voice input (browser Web Speech API)
 * ========================================================================== */

function initVoiceInput() {
  const $micBtn = $("#ai-mic-btn");
  const $input = $("#ai-question-input");
  const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognitionCtor) {
    $micBtn.prop("disabled", true).attr("title", "Voice input is not supported in this browser");
    setVoiceStatus("Voice input is not supported in this browser.");
    return;
  }

  const recognition = new SpeechRecognitionCtor();
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  let isListening = false;
  let finalTranscript = "";

  recognition.onstart = function () {
    isListening = true;
    finalTranscript = "";
    $micBtn.addClass("ai-mic-listening");
    setVoiceStatus("Listening...");
  };

  recognition.onresult = function (event) {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        finalTranscript += transcript;
      } else {
        interim += transcript;
      }
    }
    $input.val((finalTranscript + interim).trim());
  };

  recognition.onerror = function (event) {
    let message = "Voice input error. Please try again or type your question.";
    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      message = "Microphone permission was denied. You can still type your question.";
    } else if (event.error === "no-speech") {
      message = "No speech detected. Please try again.";
    } else if (event.error === "network") {
      message = "Network error during voice recognition. Please try again.";
    }
    setVoiceStatus(message, true);
  };

  recognition.onend = function () {
    isListening = false;
    $micBtn.removeClass("ai-mic-listening");

    const question = finalTranscript.trim();
    finalTranscript = "";

    if (!question) {
      return;
    }

    $input.val(question);

    const selectedLang = $("#ai-lang-select").val() || "en-IN";
    if (selectedLang === "te-IN") {
      setVoiceStatus("Translating...");
      translateToEnglish(question)
        .then(function (english) {
          const finalQuestion = (english || "").trim() || question;
          $input.val(finalQuestion);
          setVoiceStatus("");
          sendQuestion(finalQuestion);
        })
        .catch(function () {
          setVoiceStatus("Translation unavailable, sending as recognized.", true);
          sendQuestion(question);
        });
    } else {
      $input.val("");
      setVoiceStatus("");
      sendQuestion(question);
    }
  };

  $micBtn.on("click", function () {
    if (isListening) {
      recognition.stop();
      return;
    }
    setVoiceStatus("");
    recognition.lang = $("#ai-lang-select").val() || "en-IN";
    try {
      recognition.start();
    } catch (err) {}
  });
}

function setVoiceStatus(message, isError) {
  const $status = $("#ai-voice-status");
  $status.text(message || "").toggleClass("ai-voice-error", !!isError);
}

function translateToEnglish(text) {
  return $.ajax({
    url: "https://api.mymemory.translated.net/get",
    method: "GET",
    dataType: "json",
    data: { q: text, langpair: "te|en" },
    timeout: 8000,
  }).then(function (resp) {
    const translated = resp && resp.responseData && resp.responseData.translatedText;
    if (!translated) {
      throw new Error("No translation returned");
    }
    return translated;
  });
}
