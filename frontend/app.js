const startBtn = document.getElementById("start-btn");
const runStatusEl = document.getElementById("run-status");
const stepListEl = document.getElementById("step-list");
const approvalCard = document.getElementById("approval-card");
const approvalDesc = document.getElementById("approval-desc");
const approvalReason = document.getElementById("approval-reason");
const approvalPayload = document.getElementById("approval-payload");
const approveBtn = document.getElementById("approve-btn");
const rejectBtn = document.getElementById("reject-btn");
const approvalError = document.getElementById("approval-error");
const auditSection = document.getElementById("audit-section");
const auditBody = document.getElementById("audit-body");

let runId = null;

function renderState(state) {
  runStatusEl.hidden = false;
  runStatusEl.textContent = `status: ${state.status}`;

  stepListEl.innerHTML = "";
  for (const step of state.step_results) {
    const li = document.createElement("li");
    const badge = document.createElement("span");
    badge.className = `outcome-badge outcome-${step.outcome}`;
    badge.textContent = step.outcome;
    const text = document.createElement("span");
    text.textContent = `${step.step_id} — ${step.summary}`;
    li.append(badge, text);
    stepListEl.appendChild(li);
  }

  if (state.pending_approval) {
    const p = state.pending_approval;
    approvalCard.hidden = false;
    approvalDesc.textContent = p.action_description;
    approvalReason.textContent = p.reason;
    approvalPayload.textContent = JSON.stringify(p.payload, null, 2);
    approvalError.hidden = true;
    approveBtn.disabled = false;
    rejectBtn.disabled = false;
  } else {
    approvalCard.hidden = true;
  }

  if (state.status === "completed") {
    startBtn.disabled = false;
    startBtn.textContent = "Start a new morning workflow";
    loadAudit();
  }
}

async function decide(decision) {
  const state = window.__lastState;
  if (!state || !state.pending_approval) return;
  const p = state.pending_approval;
  approveBtn.disabled = true;
  rejectBtn.disabled = true;
  try {
    const res = await fetch(`/api/runs/${runId}/approvals`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        step_id: p.step_id,
        target_id: p.target_id,
        decision,
      }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      approvalError.hidden = false;
      approvalError.textContent = body.detail || `Request failed (${res.status})`;
      approveBtn.disabled = false;
      rejectBtn.disabled = false;
      return;
    }
    const newState = await res.json();
    window.__lastState = newState;
    renderState(newState);
  } catch (err) {
    approvalError.hidden = false;
    approvalError.textContent = `Network error: ${err}`;
    approveBtn.disabled = false;
    rejectBtn.disabled = false;
  }
}

async function loadAudit() {
  if (!runId) return;
  const res = await fetch(`/api/runs/${runId}/audit`);
  if (!res.ok) return;
  const entries = await res.json();
  auditSection.hidden = false;
  auditBody.innerHTML = "";
  for (const e of entries) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${e.timestamp}</td>
      <td>${e.step_id}</td>
      <td>${e.target_id ?? ""}</td>
      <td>${e.action}</td>
      <td>${e.outcome}</td>
    `;
    auditBody.appendChild(tr);
  }
}

startBtn.addEventListener("click", async () => {
  startBtn.disabled = true;
  startBtn.textContent = "Running...";
  stepListEl.innerHTML = "";
  auditSection.hidden = true;
  try {
    const res = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const state = await res.json();
    runId = state.run_id;
    window.__lastState = state;
    renderState(state);
    if (state.status !== "completed") {
      startBtn.textContent = "Running... (approve/reject below)";
    }
  } catch (err) {
    startBtn.disabled = false;
    startBtn.textContent = "Start morning workflow";
    alert(`Failed to start run: ${err}`);
  }
});

approveBtn.addEventListener("click", () => decide("approve"));
rejectBtn.addEventListener("click", () => decide("reject"));
