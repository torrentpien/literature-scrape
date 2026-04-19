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

// ── Check for new articles ───────────────────────────────────────────────

function checkUpdates(journalKey) {
  const btn = document.getElementById("btn-check-" + journalKey);
  const resultDiv = document.getElementById("update-result-" + journalKey);
  if (!btn || !resultDiv) return;

  btn.disabled = true;
  btn.textContent = "檢查中...";
  resultDiv.classList.remove("hidden");
  resultDiv.innerHTML = '<span class="update-loading">正在查詢 RSS ...</span>';

  fetch("/api/check-updates/" + journalKey)
    .then((r) => r.json())
    .then((data) => {
      btn.disabled = false;
      btn.textContent = "檢查新文章";

      if (data.error) {
        resultDiv.innerHTML =
          '<span class="update-error">查詢失敗：' + escapeHtml(data.error) + "</span>";
        return;
      }

      if (data.new_count === 0) {
        resultDiv.innerHTML =
          '<span class="update-none">沒有新文章（RSS 共 ' +
          data.rss_total + " 篇，已有 " + data.existing_total + " 篇）</span>";
        return;
      }

      // Build new article list
      let html =
        '<div class="update-found">' +
        '<strong>發現 ' + data.new_count + ' 篇新文章！</strong>' +
        '<ul class="update-article-list">';
      data.new_articles.forEach((a) => {
        html +=
          "<li>" + escapeHtml(a.title) +
          ' <span class="update-doi">' + escapeHtml(a.doi) + "</span></li>";
      });
      if (data.new_count > 20) {
        html += "<li>...及另外 " + (data.new_count - 20) + " 篇</li>";
      }
      html += "</ul>";
      html +=
        '<button class="btn btn-sm btn-primary" onclick="fetchNewArticles(\'' +
        journalKey + "')\">" +
        "下載新文章並產生摘要</button>";
      html += "</div>";
      resultDiv.innerHTML = html;
    })
    .catch((err) => {
      btn.disabled = false;
      btn.textContent = "檢查新文章";
      resultDiv.innerHTML =
        '<span class="update-error">查詢失敗：' + escapeHtml(String(err)) + "</span>";
    });
}

function fetchNewArticles(journalKey) {
  // Set the journal selector to match and trigger full pipeline
  const sel = document.getElementById("sel-journal");
  if (sel) sel.value = journalKey;
  startPipeline();
}

function checkAllUpdates() {
  // Trigger check for every journal card on the page
  document.querySelectorAll("[id^='btn-check-']").forEach((btn) => {
    const key = btn.id.replace("btn-check-", "");
    checkUpdates(key);
  });
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
