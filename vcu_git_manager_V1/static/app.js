const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

async function api(path, opts) {
  const res = await fetch(path, Object.assign({
    headers: { "Content-Type": "application/json" },
  }, opts));
  const data = await res.json().catch(() => ({ ok: false, error: "Invalid response from server." }));
  return data;
}

// ---------------------------------------------------------------- Nav

function showView(name) {
  $$(".view").forEach(v => v.classList.remove("active"));
  $(`#view-${name}`).classList.add("active");
  $$(".rail-btn").forEach(b => b.classList.toggle("active", b.dataset.view === name));
  if (name === "status") loadStatus();
  if (name === "activity") loadActivity();
}

$$(".rail-btn").forEach(btn => {
  btn.addEventListener("click", () => showView(btn.dataset.view));
});

// ---------------------------------------------------------------- Settings

const CONFIG_FIELDS = [
  "local_project_path", "project_name", "github_owner", "github_repo",
  "github_token", "branch", "github_path", "previous_revision",
  "new_revision", "revision_notes", "revision_notes_folder", "backup_folder",
];

async function loadConfig() {
  const data = await api("/api/config");
  if (!data.ok) return;
  const cfg = data.config;
  CONFIG_FIELDS.forEach(key => {
    const el = $(`#cfg-${key}`);
    if (el) el.value = cfg[key] ?? "";
  });
  // Prefill the per-revision workflow fields from settings too
  $("#upload-from").value = cfg.previous_revision || "";
  $("#upload-to").value = cfg.new_revision || "";
  $("#upload-notes").value = cfg.revision_notes || "";
  $("#pull-from").value = cfg.previous_revision || "";
  $("#pull-to").value = cfg.new_revision || "";
}

$("#btn-save-settings").addEventListener("click", async () => {
  const payload = {};
  CONFIG_FIELDS.forEach(key => {
    const el = $(`#cfg-${key}`);
    if (el) payload[key] = el.value;
  });
  const result = $("#settings-save-result");
  result.textContent = "Saving…";
  result.className = "log-line";
  const data = await api("/api/config", { method: "POST", body: JSON.stringify(payload) });
  if (data.ok) {
    result.textContent = "Settings saved. They will be here next time you open this app.";
    result.className = "log-line ok";
  } else {
    result.textContent = data.error || "Could not save settings.";
    result.className = "log-line bad";
  }
});

// ---------------------------------------------------------------- Environment / git indicator

async function loadEnvironment() {
  const data = await api("/api/environment");
  const dot = $("#git-indicator");
  const label = $("#git-indicator-label");
  if (data.ok && data.git_available) {
    dot.className = "dot dot-ok";
    label.textContent = "git ready";
  } else {
    dot.className = "dot dot-bad";
    label.textContent = "git not found";
  }
}

// ---------------------------------------------------------------- Status

async function loadStatus() {
  const card = $("#status-card");
  const prepareCard = $("#prepare-card");
  card.innerHTML = `<div class="empty">Loading…</div>`;
  prepareCard.style.display = "none";

  const data = await api("/api/status");
  if (!data.ok) {
    card.innerHTML = `<div class="empty">${escapeHtml(data.message || data.error || "Unable to load status.")}</div>`;
    return;
  }
  if (!data.repo_ready) {
    card.innerHTML = `<div class="empty">${escapeHtml(data.message || "Set up your Local Project Path and GitHub details in Settings.")}</div>`;
    if (data.local_project_path) prepareCard.style.display = "block";
    return;
  }

  const changes = data.uncommitted_changes || [];
  card.innerHTML = `
    <dl class="kv">
      <dt>Local project path</dt><dd>${escapeHtml(data.local_project_path)}</dd>
      <dt>Remote</dt><dd>${escapeHtml(data.remote_url || "not set")}</dd>
      <dt>Current branch</dt><dd>${escapeHtml(data.current_branch || "-")}</dd>
      <dt>Current commit</dt><dd>${escapeHtml((data.current_commit || "-").slice(0, 12))}</dd>
      <dt>Uncommitted changes</dt><dd>${changes.length ? changes.length + " file(s)" : "none"}</dd>
    </dl>
    ${changes.length ? `<div class="file-list" style="margin-top:14px;">` +
      changes.slice(0, 50).map(l => `<div class="file-row"><span class="path">${escapeHtml(l)}</span></div>`).join("") +
      `</div>` : ""}
  `;
}

$("#btn-prepare").addEventListener("click", async () => {
  const el = $("#prepare-result");
  el.textContent = "Working…";
  el.className = "log-line";
  const data = await api("/api/init_or_clone", { method: "POST" });
  if (data.ok) {
    el.textContent = "Done: " + data.action;
    el.className = "log-line ok";
    loadStatus();
  } else {
    el.textContent = data.error;
    el.className = "log-line bad";
  }
});

// ---------------------------------------------------------------- Shared: summary + file list rendering

function renderStats(container, summary) {
  const items = [
    ["Checked", summary.files_checked],
    ["Modified", summary.modified],
    ["Added", summary.added],
    ["Deleted", summary.deleted],
    ["Unchanged", summary.unchanged],
  ];
  container.innerHTML = items.map(([label, num]) =>
    `<div class="stat"><div class="num">${num}</div><div class="label">${label}</div></div>`
  ).join("");
}

function renderFiles(container, files) {
  const changed = files.filter(f => f.status !== "UNCHANGED");
  if (changed.length === 0) {
    container.innerHTML = `<div class="file-row"><span class="path">No differences found.</span></div>`;
    return;
  }
  container.innerHTML = changed.map(f => `
    <div class="file-row">
      <span class="path">${escapeHtml(f.path)}${f.binary ? " (binary)" : ""}</span>
      <span class="badge badge-${f.status}">${f.status}</span>
    </div>
  `).join("");
}

function setPipeline(id, activeStep) {
  const steps = ["scan", "review", "confirm"];
  const idx = steps.indexOf(activeStep);
  $$(`#${id} li`).forEach((li, i) => {
    li.classList.remove("pipe-active", "pipe-done");
    if (i < idx) li.classList.add("pipe-done");
    if (i === idx) li.classList.add("pipe-active");
  });
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// ---------------------------------------------------------------- Upload workflow

let uploadNote = "";

$("#btn-upload-scan").addEventListener("click", async () => {
  const err = $("#upload-scan-error");
  err.textContent = "Scanning and comparing…";
  err.className = "log-line";
  $("#upload-summary-card").style.display = "none";
  $("#upload-confirm-card").style.display = "none";

  await api("/api/config", {
    method: "POST",
    body: JSON.stringify({
      previous_revision: $("#upload-from").value,
      new_revision: $("#upload-to").value,
      revision_notes: $("#upload-notes").value,
    }),
  });

  const data = await api("/api/upload/scan", { method: "POST" });
  if (!data.ok) {
    err.textContent = data.error;
    err.className = "log-line bad";
    setPipeline("upload-pipeline", "scan");
    return;
  }
  err.textContent = "";
  uploadNote = data.note_text;
  renderStats($("#upload-stats"), data.summary);
  renderFiles($("#upload-files"), data.files);
  $("#upload-summary-card").style.display = "block";
  $("#upload-confirm-card").style.display = "block";
  setPipeline("upload-pipeline", "confirm");
});

$("#btn-upload-view-note").addEventListener("click", () => openNoteModal("Difference note (preview)", uploadNote));

$("#btn-upload-confirm").addEventListener("click", async () => {
  const el = $("#upload-confirm-result");
  el.textContent = "Committing and pushing…";
  el.className = "log-line";
  const data = await api("/api/upload/confirm", { method: "POST" });
  if (data.ok) {
    el.textContent = `Push ${data.verified ? "verified" : "completed"}: ${data.record.revision} on ${data.record.branch}.`;
    el.className = "log-line ok";
    loadConfig();
  } else {
    el.textContent = data.error;
    el.className = "log-line bad";
  }
});

// ---------------------------------------------------------------- Pull workflow

let pullNote = "";

$("#btn-pull-scan").addEventListener("click", async () => {
  const err = $("#pull-scan-error");
  err.textContent = "Fetching and comparing…";
  err.className = "log-line";
  $("#pull-summary-card").style.display = "none";
  $("#pull-confirm-card").style.display = "none";

  await api("/api/config", {
    method: "POST",
    body: JSON.stringify({
      previous_revision: $("#pull-from").value,
      new_revision: $("#pull-to").value,
    }),
  });

  const data = await api("/api/pull/scan", { method: "POST" });
  if (!data.ok) {
    err.textContent = data.error;
    err.className = "log-line bad";
    setPipeline("pull-pipeline", "scan");
    return;
  }
  err.textContent = "";
  pullNote = data.note_text;
  renderStats($("#pull-stats"), data.summary);
  renderFiles($("#pull-files"), data.files);
  $("#pull-summary-card").style.display = "block";
  $("#pull-confirm-card").style.display = "block";
  setPipeline("pull-pipeline", "confirm");
});

$("#btn-pull-view-note").addEventListener("click", () => openNoteModal("Difference note (preview)", pullNote));

$("#btn-pull-confirm").addEventListener("click", async () => {
  const el = $("#pull-confirm-result");
  el.textContent = "Backing up and replacing…";
  el.className = "log-line";
  const data = await api("/api/pull/confirm", { method: "POST" });
  if (data.ok) {
    el.textContent = `Replace ${data.verified ? "verified" : "completed"}: ${data.record.revision} on ${data.record.branch}. Backup: ${data.record.backup_path}`;
    el.className = "log-line ok";
    loadConfig();
  } else {
    el.textContent = data.error;
    el.className = "log-line bad";
  }
});

// ---------------------------------------------------------------- Activity

async function loadActivity() {
  const data = await api("/api/activity");
  const tbody = $("#activity-table tbody");
  const empty = $("#activity-empty");
  if (!data.ok || !data.records.length) {
    tbody.innerHTML = "";
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";
  tbody.innerHTML = data.records.map(r => `
    <tr>
      <td class="mono">${escapeHtml((r.timestamp || "").replace("T", " "))}</td>
      <td>${escapeHtml(r.operation || "-")}</td>
      <td class="mono">${escapeHtml(r.revision || "-")}</td>
      <td>${escapeHtml(r.result || "-")}</td>
      <td class="mono">${r.files_changed ?? "-"}</td>
    </tr>
  `).join("");
}

// ---------------------------------------------------------------- Modal

function openNoteModal(title, text) {
  $("#note-modal-title").textContent = title;
  $("#note-modal-body").textContent = text || "(empty)";
  $("#note-modal-backdrop").classList.add("open");
}
$("#note-modal-close").addEventListener("click", () => {
  $("#note-modal-backdrop").classList.remove("open");
});
$("#note-modal-backdrop").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) e.currentTarget.classList.remove("open");
});

// ---------------------------------------------------------------- Init

loadConfig();
loadEnvironment();
loadStatus();
