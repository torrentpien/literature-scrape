/**
 * Journal PDF Scraper - Frontend JS
 *
 * Handles pipeline execution and progress polling.
 */

let pollInterval = null;

const PHASE_LABELS = {
  fetching: "取得文章",
  downloading: "下載 PDF",
  summarizing: "產生摘要",
  done: "完成",
  error: "錯誤",
};

function _collectParams() {
  return {
    journal: document.getElementById("sel-journal").value,
    backend: document.getElementById("sel-backend").value,
    lang: document.getElementById("sel-lang").value,
    force: (document.getElementById("chk-force") || {}).checked || false,
  };
}

function _setButtonsDisabled(disabled) {
  const ids = ["btn-run", "btn-summarize"];
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = disabled;
  });
}

function startPipeline() {
  _setButtonsDisabled(true);
  fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(_collectParams()),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        alert(data.error);
        _setButtonsDisabled(false);
        return;
      }
      showProgress();
      startPolling();
    })
    .catch((err) => {
      alert("啟動失敗：" + err);
      _setButtonsDisabled(false);
    });
}

function startSummarizeOnly() {
  _setButtonsDisabled(true);
  fetch("/api/summarize-only", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(_collectParams()),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        alert(data.error);
        _setButtonsDisabled(false);
        return;
      }
      showProgress();
      startPolling();
    })
    .catch((err) => {
      alert("啟動失敗：" + err);
      _setButtonsDisabled(false);
    });
}

function showProgress() {
  const section = document.getElementById("progress-section");
  if (section) section.classList.remove("hidden");
}

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(pollStatus, 1000);
}

function pollStatus() {
  fetch("/api/status")
    .then((r) => r.json())
    .then((state) => {
      updateProgressUI(state);
      if (!state.running) {
        clearInterval(pollInterval);
        pollInterval = null;
        _setButtonsDisabled(false);
        // Auto-reload after done
        if (state.phase === "done") {
          setTimeout(() => location.reload(), 1500);
        }
      }
    })
    .catch(() => {});
}

function updateProgressUI(state) {
  // Phase tag
  const phaseEl = document.getElementById("progress-phase");
  if (phaseEl) {
    phaseEl.textContent = PHASE_LABELS[state.phase] || state.phase;
    phaseEl.className = "phase-tag phase-" + state.phase;
  }

  // Detail text
  const detailEl = document.getElementById("progress-detail");
  if (detailEl) {
    if (state.total_articles > 0) {
      detailEl.textContent = state.current_title || "";
    } else {
      detailEl.textContent = state.current_title || "";
    }
  }

  // Progress bar
  const barEl = document.getElementById("progress-bar");
  if (barEl) {
    barEl.style.width = state.progress + "%";
  }

  // Log
  const logEl = document.getElementById("progress-log");
  if (logEl && state.log) {
    logEl.innerHTML = state.log
      .map((l) => '<div class="log-line">' + escapeHtml(l) + "</div>")
      .join("");
    logEl.scrollTop = logEl.scrollHeight;
  }
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// On page load, check if pipeline is already running
document.addEventListener("DOMContentLoaded", () => {
  fetch("/api/status")
    .then((r) => r.json())
    .then((state) => {
      if (state.running) {
        showProgress();
        updateProgressUI(state);
        startPolling();
        _setButtonsDisabled(true);
      }
    })
    .catch(() => {});
});
