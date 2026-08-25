/*
 * AI Assistant chat panel.
 *
 * This file communicates with branch_dashboard's API (POST /api/dashboard/ask-ai/).
 * It sends questions and current filter context, and renders the response:
 * - If structured table data is returned: renders ONLY the structured result table.
 * - If text-only / error / count response: renders the text message bubble.
 * Never renders duplicate text alongside the table.
 */

const ASK_AI_URL = "/api/dashboard/ask-ai/";

$(document).ready(function () {
  $("#ai-input-row").on("submit", function (e) {
    e.preventDefault();

    const $input = $("#ai-question-input");
    const question = $input.val().trim();
    if (!question) return;

    $input.val("");
    sendQuestion(question);
  });

  initVoiceInput();
});

/*
 * Single shared entry point for asking the AI assistant a question.
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
      const answerText = (resp && resp.answer) || "No response received.";
      const isError = !(resp && resp.success);
      const data = resp && resp.data;

      appendBotMessage(answerText, isError, data);
    })
    .fail(function (xhr) {
      const msg =
        (xhr.responseJSON && xhr.responseJSON.answer) ||
        (xhr.responseJSON && xhr.responseJSON.error) ||
        "The AI assistant is currently unavailable. Please try again.";
      appendBotMessage(msg, true, null);
    })
    .always(function () {
      setSending(false);
    });
}

function appendUserMessage(text) {
  const $wrap = $('<div class="ai-msg ai-msg-user"></div>');
  $wrap.append($('<div class="ai-msg-bubble"></div>').text(text));
  $("#ai-messages").append($wrap);
  scrollToBottom();
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
 * Render Bot response:
 * - When structured table data exists: RENDER ONLY THE RESULT TABLE (NO narrative text).
 * - Otherwise: RENDER THE TEXT BUBBLE.
 */
function appendBotMessage(text, isError, data) {
  const $wrap = $('<div class="ai-msg ai-msg-bot' + (isError ? " ai-msg-error" : "") + '"></div>');

  if (!isError && hasValidTableData(data)) {
    // ONLY render the structured result table
    const $table = renderAiDataTable(data);
    if ($table) {
      const $tableCard = $('<div class="ai-table-card"></div>').append($table);
      $wrap.append($tableCard);
    } else {
      $wrap.append($('<div class="ai-msg-bubble"></div>').text(text));
    }
  } else {
    // Render the text response
    $wrap.append($('<div class="ai-msg-bubble"></div>').text(text));
  }

  $("#ai-messages").append($wrap);
  scrollToBottom();
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

function scrollToBottom() {
  const $messages = $("#ai-messages");
  if ($messages.length) {
    $messages.scrollTop($messages[0].scrollHeight);
  }
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
