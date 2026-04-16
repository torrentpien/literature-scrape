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

function startPipeline() {
  const journal = document.getElementById("sel-journal").value;
  const backend = document.getElementById("sel-backend").value;
  const lang = document.getElementById("sel-lang").value;
  const btn = document.getElementById("btn-run");

  btn.disabled = true;
  btn.textContent = "執行中...";

  fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ journal, backend, lang }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        alert(data.error);
        btn.disabled = false;
        btn.textContent = "開始抓取";
        return;
      }
      showProgress();
      startPolling();
    })
    .catch((err) => {
      alert("啟動失敗：" + err);
      btn.disabled = false;
      btn.textContent = "開始抓取";
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
        const btn = document.getElementById("btn-run");
        if (btn) {
          btn.disabled = false;
          btn.textContent = "開始抓取";
        }
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
        const btn = document.getElementById("btn-run");
        if (btn) {
          btn.disabled = true;
          btn.textContent = "執行中...";
        }
      }
    })
    .catch(() => {});
});
