const startBtn = document.getElementById("start-btn");
const cancelBtn = document.getElementById("cancel-btn");
const runStatusEl = document.getElementById("run-status");
const summarySection = document.getElementById("summary-section");
const summaryGrid = document.getElementById("summary-grid");
const resultsSection = document.getElementById("results-section");
const resultsList = document.getElementById("results-list");
const auditSection = document.getElementById("audit-section");
const auditBody = document.getElementById("audit-body");

let runId = null;

const OUTCOME_LABELS = {
  autonomous_triaged: "AUTONOMOUS — TRIAGE DRAFTED",
  escalated: "ESCALATION REQUIRED",
  handoff: "HUMAN HAND-OFF (ACA-2026/2)",
  not_processed: "NOT PROCESSED",
  failed: "UNEXPECTED ERROR",
};

function renderState(state) {
  runStatusEl.hidden = false;
  runStatusEl.textContent = `status: ${state.status}`;
  cancelBtn.hidden = state.status !== "running";

  summarySection.hidden = false;
  summaryGrid.innerHTML = "";
  for (const [key, count] of Object.entries(state.summary)) {
    const cell = document.createElement("div");
    cell.className = `summary-cell outcome-${key}`;
    cell.innerHTML = `<div class="summary-count">${count}</div><div class="summary-label">${OUTCOME_LABELS[key] || key}</div>`;
    summaryGrid.appendChild(cell);
  }

  resultsSection.hidden = false;
  resultsList.innerHTML = "";
  for (const r of state.results) {
    resultsList.appendChild(renderResult(r));
  }

  if (state.status === "completed" || state.status === "cancelled") {
    startBtn.disabled = false;
    startBtn.textContent = "Run again";
    loadAudit();
  }
}

function renderResult(r) {
  const li = document.createElement("li");
  li.className = `result outcome-${r.outcome}`;

  const header = document.createElement("div");
  header.className = "result-header";
  header.innerHTML = `
    <span class="badge">${OUTCOME_LABELS[r.outcome] || r.outcome}</span>
    <strong>${r.referral_id}</strong>
    <span class="resident">${r.resident_ref}</span>
    <span class="requested-action">${r.requested_action}</span>
  `;
  li.appendChild(header);

  const trace = document.createElement("div");
  trace.className = "trace";
  trace.textContent = r.trace.join(" → ");
  li.appendChild(trace);

  if (r.triage_note) {
    const note = document.createElement("div");
    note.className = "detail";
    note.innerHTML = `<p>${r.triage_note.narrative}</p>`;
    if (r.triage_note.adopted === null) {
      const adoptBtn = document.createElement("button");
      adoptBtn.textContent = "Adopt note";
      adoptBtn.className = "adopt";
      adoptBtn.onclick = () => decideAdoption(r.referral_id, "approve");
      const declineBtn = document.createElement("button");
      declineBtn.textContent = "Decline note";
      declineBtn.className = "decline";
      declineBtn.onclick = () => decideAdoption(r.referral_id, "reject");
      note.append(adoptBtn, declineBtn);
    } else {
      const status = document.createElement("p");
      status.className = "adoption-status";
      status.textContent = r.triage_note.adopted ? "Adopted by caseworker." : "Declined by caseworker.";
      note.appendChild(status);
    }
    li.appendChild(note);
  }

  if (r.escalation) {
    const esc = document.createElement("div");
    esc.className = "detail";
    esc.innerHTML = `<p><strong>Policy basis:</strong> ${r.escalation.basis}</p><p>${r.escalation.explanation}</p>`;
    li.appendChild(esc);
  }

  if (r.handoff) {
    const ho = document.createElement("div");
    ho.className = "detail";
    ho.innerHTML = `<p><strong>Policy basis:</strong> ${r.handoff.basis}</p><p>${r.handoff.explanation}</p><p class="no-note">TRIAGE NOTE NOT GENERATED</p>`;
    li.appendChild(ho);
  }

  return li;
}

async function decideAdoption(referralId, decision) {
  const res = await fetch(`/api/runs/${runId}/referrals/${referralId}/adopt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
  const state = await res.json();
  if (res.ok) renderState(state);
  else alert(state.detail || "adoption failed");
}

async function loadAudit() {
  if (!runId) return;
  const res = await fetch(`/api/runs/${runId}/audit`);
  if (!res.ok) return;
  const entries = await res.json();
  auditSection.hidden = false;
  auditBody.innerHTML = "";
  for (const e of entries) {
    const detail = JSON.parse(e.detail || "{}").detail || "";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${e.timestamp}</td>
      <td>${e.target_id ?? ""}</td>
      <td>${e.action}</td>
      <td>${e.outcome}</td>
      <td class="detail-cell">${detail}</td>
    `;
    auditBody.appendChild(tr);
  }
}

startBtn.addEventListener("click", async () => {
  startBtn.disabled = true;
  startBtn.textContent = "Processing...";
  resultsList.innerHTML = "";
  auditSection.hidden = true;
  try {
    const res = await fetch("/api/runs", { method: "POST" });
    const state = await res.json();
    runId = state.run_id;
    renderState(state);
  } catch (err) {
    startBtn.disabled = false;
    startBtn.textContent = "Process overnight referral queue";
    alert(`Failed to start run: ${err}`);
  }
});

cancelBtn.addEventListener("click", async () => {
  if (!runId) return;
  const res = await fetch(`/api/runs/${runId}/cancel`, { method: "POST" });
  const state = await res.json();
  if (res.ok) renderState(state);
});
