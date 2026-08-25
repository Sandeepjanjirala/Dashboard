/*
 * AI Assistant chat panel.
 *
 * This file only talks to branch_dashboard's own API
 * (POST /api/dashboard/ask-ai/). It never calls the query-engine service
 * directly and contains no AI/query logic of its own -- it just renders
 * whatever answer text the backend relays back.
 *
 * No request is made automatically on page load; the dashboard's existing
 * load flow (dashboard.js) is completely untouched.
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
 * Single shared entry point for asking the AI assistant a question,
 * regardless of whether it came from typing (existing flow) or voice
 * (new flow). This is the exact AJAX call the text flow used before --
 * unchanged, just pulled into a function so voice can call it too
 * instead of duplicating the request logic.
 */
function sendQuestion(question) {
  question = (question || "").trim();
  if (!question) return;

  appendUserMessage(question);
  setSending(true);

  // Attach the dashboard's current AGM/RI/Branch selection to every
  // question -- typed or spoken, both paths funnel through this one
  // function -- so the backend (and, later, filter-aware query-engine
  // functions) always know what the user is looking at. Falls back to
  // "All" scope if dashboard.js hasn't loaded for some reason, so a
  // missing filter context never blocks asking a question.
  const filters = (typeof getDashboardFilterContext === "function")
    ? getDashboardFilterContext()
    : { agm: "All", ri: "All", branches: ["All"] };

  $.ajax({
    url: ASK_AI_URL,
    method: "POST",
    contentType: "application/json",
    data: JSON.stringify({ question: question, filters: filters }),
    dataType: "json",
  })
    .done(function (resp) {
      appendBotMessage(
        (resp && resp.answer) || "Sorry, I didn't get a usable answer for that.",
        !(resp && resp.success),
        resp && resp.data
      );
    })
    .fail(function (xhr) {
      const msg =
        (xhr.responseJSON && xhr.responseJSON.answer) ||
        (xhr.responseJSON && xhr.responseJSON.error) ||
        "The AI assistant is currently unavailable. Please try again.";
      appendBotMessage(msg, true);
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

function appendBotMessage(text, isError, data) {
  const $wrap = $('<div class="ai-msg ai-msg-bot' + (isError ? " ai-msg-error" : "") + '"></div>');
  $wrap.append($('<div class="ai-msg-bubble"></div>').text(text));

  // When the query engine's response includes structured data (a list of
  // rows -- e.g. one per branch), render it as a real table straight from
  // that data. If `data` isn't in that shape, this quietly does nothing --
  // no columns or rows are ever invented client-side.
  const $table = renderAiDataTable(data);
  if ($table) $wrap.append($table);

  $("#ai-messages").append($wrap);
  scrollToBottom();
}

function renderAiDataTable(data) {
  const rows = Array.isArray(data)
    ? data
    : data && Array.isArray(data.rows)
      ? data.rows
      : null;

  if (!rows || rows.length === 0 || typeof rows[0] !== "object" || rows[0] === null) {
    return null;
  }

  const columns = Object.keys(rows[0]);
  const $table = $('<table class="ai-data-table"></table>');
  const $headRow = $("<tr></tr>");
  columns.forEach(function (col) {
    $headRow.append($("<th></th>").text(formatColumnLabel(col)));
  });
  $table.append($("<thead></thead>").append($headRow));

  const $tbody = $("<tbody></tbody>");
  rows.forEach(function (row) {
    const $tr = $("<tr></tr>");
    columns.forEach(function (col) {
      const value = row[col];
      $tr.append($("<td></td>").text(value === null || value === undefined ? "--" : value));
    });
    $tbody.append($tr);
  });
  $table.append($tbody);

  return $table;
}

function formatColumnLabel(col) {
  return String(col)
    .replace(/_/g, " ")
    .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
}

function setSending(isSending) {
  $("#ai-send-btn").prop("disabled", isSending);
  $("#ai-question-input").prop("disabled", isSending);
}

function scrollToBottom() {
  const $messages = $("#ai-messages");
  $messages.scrollTop($messages[0].scrollHeight);
}

/* ==========================================================================
 * Voice input (browser Web Speech API only).
 *
 * Purely front-end: converts speech to text, drops it into the existing
 * #ai-question-input field, and submits it through the same sendQuestion()
 * the text flow uses. No audio is ever sent to Django; the query engine
 * and /api/dashboard/ask-ai/ contract are untouched.
 * ========================================================================== */

function initVoiceInput() {
  const $micBtn = $("#ai-mic-btn");
  const $input = $("#ai-question-input");
  const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognitionCtor) {
    $micBtn.prop("disabled", true).attr("title", "Voice input is not supported in this browser");
    setVoiceStatus("Voice input isn't supported in this browser. You can still type your question.");
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
      // Nothing recognized (e.g. silence, or the user stopped early) --
      // do not auto-submit an empty question.
      return;
    }

    // Show the raw recognized transcript in the input first, so the user
    // sees exactly what was heard before any normalization happens.
    $input.val(question);

    const selectedLang = $("#ai-lang-select").val() || "en-IN";
    if (selectedLang === "te-IN") {
      // Telugu (or Telugu+English mixed) speech: normalize to an English
      // question the existing query engine already understands, then feed
      // it through the exact same sendQuestion() the text flow uses.
      setVoiceStatus("Translating...");
      translateToEnglish(question)
        .then(function (english) {
          const finalQuestion = (english || "").trim() || question;
          $input.val(finalQuestion);
          setVoiceStatus("");
          sendQuestion(finalQuestion);
        })
        .catch(function () {
          // Translation failed -- fall back to the raw transcript rather
          // than blocking the user; the query engine may still fail on it,
          // but the flow doesn't get stuck.
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
      // Second click while active: stop instead of starting another session.
      recognition.stop();
      return;
    }
    setVoiceStatus("");
    recognition.lang = $("#ai-lang-select").val() || "en-IN";
    try {
      recognition.start();
    } catch (err) {
      // start() throws if a session is somehow already active; ignore.
    }
  });
}

function setVoiceStatus(message, isError) {
  const $status = $("#ai-voice-status");
  $status.text(message || "").toggleClass("ai-voice-error", !!isError);
}

/*
 * Language normalization layer.
 *
 * Only called for Telugu (or Telugu+English mixed) voice input. Translates
 * the recognized text to English so the existing query engine -- which
 * only understands English intent/keyword phrasing -- can handle it.
 * This does not touch query logic; it purely converts the question text
 * before it reaches sendQuestion().
 *
 * Uses the free MyMemory Translation API (https://mymemory.translated.net):
 *   - No API key required for normal usage
 *   - CORS-enabled, safe to call directly from the browser
 *   - Anonymous free tier: ~5000 words/day per IP (higher with a free
 *     registered email, paid tiers beyond that)
 *   - Requires internet access from the user's browser
 * If this call fails or the service is unreachable, the caller falls back
 * to sending the raw recognized transcript instead of blocking the user.
 */
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
