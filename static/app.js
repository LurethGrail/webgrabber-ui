const urlInput      = document.getElementById("url");
const filenameInput = document.getElementById("filename");
const outputDirInput= document.getElementById("outputDir");
const downloadBtn   = document.getElementById("downloadBtn");
const progressFill  = document.getElementById("progressFill");
const progressMsg   = document.getElementById("progressMsg");
const pctLabel      = document.getElementById("pct-label");
const statusPill    = document.getElementById("status-pill");
const resultMsg     = document.getElementById("resultMsg");
const metaBox       = document.getElementById("meta");
const thumb         = document.getElementById("thumb");
const metaTitle     = document.getElementById("metaTitle");
const metaSub       = document.getElementById("metaSub");

let selectedFormat = "mp4";
let metaFetchTimer = null;
let pollTimer = null;

document.querySelectorAll(".fmt-grid .toggle-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".fmt-grid .toggle-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    selectedFormat = btn.dataset.format;
  });
});

urlInput.addEventListener("input", () => {
  clearTimeout(metaFetchTimer);
  const url = urlInput.value.trim();
  if (!url) { metaBox.hidden = true; updateStepState(); return; }
  metaFetchTimer = setTimeout(() => fetchMeta(url), 700);
  updateStepState();
});

async function fetchMeta(url) {
  try {
    const res = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const d = await res.json();
    if (d.error) { metaBox.hidden = true; return; }
    thumb.src = d.thumbnail || "";
    metaTitle.textContent = d.title || "";
    metaSub.textContent = d.uploader || "";
    metaBox.hidden = false;
    if (!filenameInput.value)
      filenameInput.placeholder = d.title || "Auto (video title)";
  } catch { metaBox.hidden = true; }
}

downloadBtn.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) { showResult("Paste a YouTube URL first.", "error"); return; }

  clearResult();
  downloadBtn.disabled = true;
  setStatus("running");
  setProgress(0, "Starting…");

  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        output_dir: outputDirInput.value.trim(),
        format: selectedFormat,
        filename: filenameInput.value.trim(),
      }),
    });
    const d = await res.json();
    if (d.error) { showResult(d.error, "error"); resetBtn(); return; }
    pollStatus(d.job_id);
  } catch (e) {
    showResult("Server error: " + e.message, "error");
    resetBtn();
  }
});

function pollStatus(jobId) {
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/status/${jobId}`);
      const job = await res.json();
      setProgress(job.progress || 0, job.message || "");
      if (job.status === "done") {
        clearInterval(pollTimer);
        setStatus("done");
        showResult("Saved: " + job.filename, "success");
        resetBtn();
      } else if (job.status === "error") {
        clearInterval(pollTimer);
        setStatus("error");
        showResult("Error: " + job.message, "error");
        resetBtn();
      }
    } catch {
      clearInterval(pollTimer);
      showResult("Lost connection to server.", "error");
      resetBtn();
    }
  }, 800);
}

function setProgress(pct, msg) {
  progressFill.style.width = pct + "%";
  pctLabel.textContent = pct + "%";
  progressMsg.textContent = msg || "no active job";
}

function setStatus(state) {
  statusPill.className = "status-pill " + state;
  const map = {
    idle:    '<span id="status-text">idle</span>',
    running: '<span class="pulse"></span><span>downloading</span>',
    done:    '<span style="color:var(--green)">✓</span> <span>done</span>',
    error:   '<span>✕</span> <span>error</span>',
  };
  statusPill.innerHTML = map[state] || map.idle;
}

function showResult(text, type) {
  resultMsg.textContent = text;
  resultMsg.className = "result-msg " + type;
  document.getElementById("sec-result").classList.add("visible");
}

function clearResult() {
  resultMsg.textContent = "";
  resultMsg.className = "result-msg";
  document.getElementById("sec-result").classList.remove("visible");
}

function resetBtn() { downloadBtn.disabled = false; }

function updateStepState() {
  const urlSec      = document.getElementById("sec-url");
  const settingsSec = document.getElementById("sec-settings");
  const hasUrl      = urlInput.value.trim().length > 0;

  urlSec.classList.remove("blinking", "active-step");
  settingsSec.classList.remove("blinking", "active-step");

  if (!hasUrl) {
    urlSec.classList.add("blinking");
  } else {
    urlSec.classList.add("active-step");
    settingsSec.classList.add("blinking");
  }
}

function setTheme(theme) {
  document.body.classList.remove("theme-light", "theme-darker");
  if (theme !== "dark") document.body.classList.add("theme-" + theme);
  document.getElementById("theme-select").value = theme;
  localStorage.setItem("webgrabber-theme", theme);
}

function toggleLayout() {
  const next = document.body.classList.contains("dashboard-mode") ? "classic" : "dashboard";
  applyLayout(next);
}

function applyLayout(mode) {
  document.body.classList.toggle("dashboard-mode", mode === "dashboard");
  document.getElementById("layout-toggle").textContent = mode === "dashboard" ? "classic" : "dashboard";
  localStorage.setItem("webgrabber-layout", mode);
}

(function init() {
  setTheme(localStorage.getItem("webgrabber-theme") || "dark");
  applyLayout(localStorage.getItem("webgrabber-layout") || "dashboard");
  updateStepState();
})();
