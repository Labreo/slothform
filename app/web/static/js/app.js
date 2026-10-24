/**
 * SlothForm Web Dashboard Application
 * Connects to FastAPI REST backend and streams real-time SSE telemetry.
 * Sourced from Refero Styles AgentQL Design System.
 */

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("fill-form");
  const targetUrlInput = document.getElementById("target-url-input");
  const dryRunToggle = document.getElementById("dry-run-toggle");
  const dryRunLabel = document.getElementById("dry-run-status-text");
  const submitBtn = document.getElementById("submit-btn");
  const progressBar = document.getElementById("stage-progress-bar");
  const statusText = document.getElementById("pipeline-status-text");
  const terminalLogs = document.getElementById("terminal-logs");
  const replayContainer = document.getElementById("replay-container");
  const replayFrame = document.getElementById("browserbase-replay-frame");
  const replayLiveDot = document.getElementById("replay-live-dot");
  const diffTbody = document.getElementById("diff-tbody");
  const diffModal = document.getElementById("diff-inspection-modal");
  const modalCloseBtn = document.getElementById("modal-close-btn");
  const modalCloseActionBtn = document.getElementById("modal-close-action-btn");
  const viewDiffBtn = document.getElementById("view-diff-btn");

  // CIBA Consent Elements
  const cibaConsentCard = document.getElementById("ciba-consent-card");
  const cibaTimerBadge = document.getElementById("ciba-timer-badge");
  const cibaApproveBtn = document.getElementById("ciba-approve-btn");
  const cibaRejectBtn = document.getElementById("ciba-reject-btn");
  const cibaInspectModalBtn = document.getElementById("ciba-inspect-modal-btn");
  const modalApproveBtn = document.getElementById("modal-approve-btn");
  const modalRejectBtn = document.getElementById("modal-reject-btn");

  let activeEventSource = null;
  let currentActiveTaskId = null;

  // Toggle dry run label
  if (dryRunToggle && dryRunLabel) {
    dryRunToggle.addEventListener("change", (e) => {
      if (e.target.checked) {
        dryRunLabel.textContent = "DRY-RUN GUARD: ON";
        dryRunLabel.style.color = "var(--amber-primary)";
      } else {
        dryRunLabel.textContent = "LIVE SUBMISSION: ON";
        dryRunLabel.style.color = "var(--rose-danger)";
      }
    });
  }

  // Quick fill sample chips (scoped strictly to .quick-samples)
  document.querySelectorAll(".quick-samples .sample-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const sampleUrl = chip.getAttribute("data-url");
      if (sampleUrl && targetUrlInput) {
        targetUrlInput.value = sampleUrl;
        targetUrlInput.focus();
        chip.style.transform = "scale(0.96)";
        setTimeout(() => {
          chip.style.transform = "";
        }, 150);
      }
    });
  });

  // Modal Handlers
  function openDiffModal() {
    if (diffModal) {
      diffModal.classList.add("active");
    }
  }

  function closeDiffModal() {
    if (diffModal) {
      diffModal.classList.remove("active");
    }
  }

  if (viewDiffBtn) {
    viewDiffBtn.addEventListener("click", openDiffModal);
  }
  if (cibaInspectModalBtn) {
    cibaInspectModalBtn.addEventListener("click", openDiffModal);
  }
  if (modalCloseBtn) {
    modalCloseBtn.addEventListener("click", closeDiffModal);
  }
  if (modalCloseActionBtn) {
    modalCloseActionBtn.addEventListener("click", closeDiffModal);
  }
  if (diffModal) {
    diffModal.addEventListener("click", (e) => {
      if (e.target === diffModal) {
        closeDiffModal();
      }
    });
  }

  // Interactive CIBA Consent Decision Submissions
  async function submitConsentDecision(approved) {
    if (!currentActiveTaskId) return;

    if (cibaApproveBtn) cibaApproveBtn.disabled = true;
    if (cibaRejectBtn) cibaRejectBtn.disabled = true;
    if (modalApproveBtn) modalApproveBtn.disabled = true;
    if (modalRejectBtn) modalRejectBtn.disabled = true;

    if (cibaTimerBadge) {
      cibaTimerBadge.textContent = approved
        ? "Decision: Approved — Resuming Form Fill..."
        : "Decision: Denied — Halting Pipeline...";
      cibaTimerBadge.style.color = approved ? "var(--emerald-success)" : "var(--rose-danger)";
    }

    try {
      const response = await fetch(`/api/tasks/${currentActiveTaskId}/consent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved }),
      });

      if (!response.ok) {
        throw new Error("Failed to record CIBA consent decision on backend");
      }

      appendLog(
        "CIBA",
        `Human-in-the-loop consent ${approved ? "GRANTED" : "REFUSED"} for task ${currentActiveTaskId}`
      );
      closeDiffModal();
    } catch (err) {
      appendLog("ERROR", `Consent submission error: ${err.message}`);
      if (cibaApproveBtn) cibaApproveBtn.disabled = false;
      if (cibaRejectBtn) cibaRejectBtn.disabled = false;
      if (modalApproveBtn) modalApproveBtn.disabled = false;
      if (modalRejectBtn) modalRejectBtn.disabled = false;
    }
  }

  if (cibaApproveBtn) {
    cibaApproveBtn.addEventListener("click", () => submitConsentDecision(true));
  }
  if (cibaRejectBtn) {
    cibaRejectBtn.addEventListener("click", () => submitConsentDecision(false));
  }
  if (modalApproveBtn) {
    modalApproveBtn.addEventListener("click", () => submitConsentDecision(true));
  }
  if (modalRejectBtn) {
    modalRejectBtn.addEventListener("click", () => submitConsentDecision(false));
  }

  // Stage steps
  const stageElements = {
    SESSION_INIT: document.getElementById("stage-step-1"),
    DOM_EXTRACTION: document.getElementById("stage-step-2"),
    AI_REASONING: document.getElementById("stage-step-3"),
    CIBA_CONSENT: document.getElementById("stage-step-4"),
    FORM_FILLING: document.getElementById("stage-step-5"),
    COMPLETED: document.getElementById("stage-step-5"),
  };

  const stageOrder = [
    "SESSION_INIT",
    "DOM_EXTRACTION",
    "AI_REASONING",
    "CIBA_CONSENT",
    "FORM_FILLING",
    "COMPLETED",
  ];

  function resetStages() {
    Object.values(stageElements).forEach((el) => {
      if (el) {
        el.classList.remove("active", "completed");
      }
    });
    if (progressBar) {
      progressBar.style.width = "0%";
      progressBar.style.backgroundColor = "";
    }
    if (terminalLogs) {
      terminalLogs.innerHTML = "";
    }
    if (cibaConsentCard) {
      cibaConsentCard.style.display = "none";
    }
    if (replayLiveDot) {
      replayLiveDot.style.display = "none";
    }
  }

  function appendLog(stage, message, timestamp) {
    if (!terminalLogs) return;
    const timeStr = timestamp
      ? new Date(timestamp * 1000).toLocaleTimeString()
      : new Date().toLocaleTimeString();
    const logDiv = document.createElement("div");
    logDiv.className = "log-entry";
    logDiv.innerHTML = `
      <span class="log-time">[${timeStr}]</span>
      <span class="log-stage">&lt;${stage}&gt;</span>
      <span class="log-msg">${escapeHtml(message)}</span>
    `;
    terminalLogs.appendChild(logDiv);
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  }

  function updatePipelineStage(stage, percentage) {
    if (progressBar) {
      progressBar.style.width = `${percentage}%`;
    }

    const currentIdx = stageOrder.indexOf(stage);
    stageOrder.forEach((st, idx) => {
      const el = stageElements[st];
      if (!el) return;
      if (idx < currentIdx) {
        el.classList.remove("active");
        el.classList.add("completed");
      } else if (idx === currentIdx) {
        el.classList.remove("completed");
        el.classList.add("active");
      } else {
        el.classList.remove("active", "completed");
      }
    });

    if (stage === "COMPLETED") {
      Object.values(stageElements).forEach((el) => {
        if (el) el.classList.add("completed");
      });
    }

    // Trigger CIBA interactive card
    if (stage === "CIBA_CONSENT") {
      if (cibaConsentCard) {
        cibaConsentCard.style.display = "block";
        if (cibaApproveBtn) cibaApproveBtn.disabled = false;
        if (cibaRejectBtn) cibaRejectBtn.disabled = false;
      }
      if (modalApproveBtn) modalApproveBtn.style.display = "inline-flex";
      if (modalRejectBtn) modalRejectBtn.style.display = "inline-flex";
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Handle Form Submission
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const targetUrl = targetUrlInput ? targetUrlInput.value.trim() : "";
      const isDryRun = dryRunToggle ? dryRunToggle.checked : true;

      if (!targetUrl) {
        alert("Please enter a target form URL (ATS job or W-8BEN compliance form).");
        return;
      }

      resetStages();
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Processing Pipeline...";
      }
      if (statusText) {
        statusText.textContent = "Initiating cloud sandbox...";
        statusText.style.color = "var(--amber-primary)";
      }
      if (replayLiveDot) {
        replayLiveDot.style.display = "inline-block";
      }

      try {
        const response = await fetch("/api/fill", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: targetUrl, dry_run: isDryRun }),
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || "Failed to start form filling task");
        }

        const data = await response.json();
        const taskId = data.task_id;
        currentActiveTaskId = taskId;
        appendLog("DISPATCH", `Task created: ${taskId} (dry_run=${isDryRun})`);

        // Connect SSE telemetry stream
        connectTelemetryStream(taskId, isDryRun);
      } catch (err) {
        appendLog("ERROR", err.message);
        if (statusText) {
          statusText.textContent = `Error: ${err.message}`;
          statusText.style.color = "var(--rose-danger)";
        }
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Start Autonomous Fill";
        }
        if (replayLiveDot) {
          replayLiveDot.style.display = "none";
        }
      }
    });
  }

  function connectTelemetryStream(taskId, isDryRun) {
    currentActiveTaskId = taskId;
    if (activeEventSource) {
      activeEventSource.close();
    }

    if (replayLiveDot) {
      replayLiveDot.style.display = "inline-block";
    }

    const eventSource = new EventSource(`/api/tasks/${taskId}/events`);
    activeEventSource = eventSource;

    eventSource.onopen = () => {
      appendLog("SSE", `Live telemetry stream connected to /api/tasks/${taskId}/events`);
    };

    eventSource.onmessage = (e) => {
      try {
        const eventData = JSON.parse(e.data);
        const { stage, percentage, message, timestamp, result, error } = eventData;

        updatePipelineStage(stage, percentage);
        appendLog(stage, message, timestamp);

        if (statusText) {
          statusText.textContent = `${stage} (${percentage}%) — ${message}`;
        }

        if (stage === "COMPLETED") {
          eventSource.close();
          handleCompletion(taskId, result || {}, isDryRun);
        } else if (stage === "FAILED" || stage === "REFUSED") {
          eventSource.close();
          handleFailure(error || message, stage);
        }
      } catch (err) {
        console.error("SSE parse error:", err);
      }
    };

    eventSource.onerror = (err) => {
      console.warn("SSE connection error or completed:", err);
      // Check task status directly
      fetch(`/api/tasks/${taskId}`)
        .then((res) => res.json())
        .then((task) => {
          if (task.status === "completed") {
            eventSource.close();
            handleCompletion(taskId, task.result || task || {}, isDryRun);
          } else if (task.status === "failed" || task.status === "refused") {
            eventSource.close();
            handleFailure(task.error || `Task halted with status: ${task.status}`, task.status.toUpperCase());
          }
        })
        .catch(() => {});
    };
  }

  function handleCompletion(taskId, result, isDryRun) {
    if (statusText) {
      statusText.textContent = isDryRun
        ? "✓ DRY_RUN_SUCCESS — Halting safely before submission"
        : "✓ SUBMITTED — Application filed successfully";
      statusText.style.color = "var(--emerald-success)";
    }

    if (progressBar) {
      progressBar.style.width = "100%";
      progressBar.style.backgroundColor = "var(--emerald-success)";
    }

    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Start Autonomous Fill";
    }

    if (replayLiveDot) {
      replayLiveDot.style.display = "none";
    }

    if (cibaConsentCard) {
      if (cibaTimerBadge) {
        cibaTimerBadge.textContent = "✓ Identity Released (RFC 9396 Approved)";
        cibaTimerBadge.style.color = "var(--emerald-success)";
      }
    }

    // Embed replay
    const replayUrl =
      result.replay_url ||
      result.live_view_url ||
      `https://browserbase.com/sessions/${result.session_id || taskId}`;
    if (replayFrame) {
      replayFrame.src = replayUrl;
      replayFrame.style.display = "block";
    }
    const placeholder = document.getElementById("replay-placeholder");
    if (placeholder) {
      placeholder.style.display = "none";
    }

    const replayLink = document.getElementById("replay-external-link");
    if (replayLink) {
      replayLink.href = replayUrl;
      replayLink.textContent = "Open in Browserbase ↗";
    }

    // Populate dynamic field diff table
    populateDiffTable(result);
  }

  function handleFailure(errorMessage, stage = "FAILED") {
    if (statusText) {
      statusText.textContent = `Execution Halted [${stage}]: ${errorMessage}`;
      statusText.style.color = stage === "REFUSED" ? "var(--amber-primary)" : "var(--rose-danger)";
    }
    if (progressBar) {
      progressBar.style.backgroundColor = stage === "REFUSED" ? "var(--amber-primary)" : "var(--rose-danger)";
    }
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Start Autonomous Fill";
    }
    if (replayLiveDot) {
      replayLiveDot.style.display = "none";
    }
    if (diffTbody && (!diffTbody.children.length || diffTbody.textContent.includes("Streaming"))) {
      diffTbody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; color: ${stage === 'REFUSED' ? 'var(--amber-primary)' : 'var(--rose-danger)'}; padding: 1.5rem;">
            ⚠️ Pipeline halted [${escapeHtml(stage)}]: ${escapeHtml(errorMessage)}
          </td>
        </tr>
      `;
    }
  }

  function populateDiffTable(result) {
    if (!diffTbody) return;
    diffTbody.innerHTML = "";

    let items = [];
    if (result && Array.isArray(result.diff)) {
      items = result.diff;
    } else if (result && result.diff && Array.isArray(result.diff.items)) {
      items = result.diff.items;
    } else if (result && Array.isArray(result.items)) {
      items = result.items;
    } else if (result && result.plan && Array.isArray(result.plan.items)) {
      items = result.plan.items;
    }

    if (!items || items.length === 0) {
      diffTbody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; color: var(--text-dim); padding: 1.5rem;">
            No form field diff records available for this task.
          </td>
        </tr>
      `;
      return;
    }

    items.forEach((item) => {
      const tr = document.createElement("tr");
      const fieldName = item.field || item.field_name || item.field_id || "Field";
      const tier = item.tier || "PUBLIC";
      const value = item.value !== undefined ? String(item.value) : (item.masked_value !== undefined ? String(item.masked_value) : "");
      const status = item.status || "Filled";

      const badgeClass =
        tier === "PUBLIC"
          ? "badge-public"
          : tier === "SEMI_SENSITIVE"
          ? "badge-semi"
          : tier === "CRITICAL_TAX"
          ? "badge-tax"
          : "badge-fin";

      const statusColor =
        status === "Filled" || status === "Uploaded" || status === "Selected"
          ? "var(--emerald-success)"
          : status === "Protected"
          ? "var(--amber-primary)"
          : "var(--text-dim)";

      tr.innerHTML = `
        <td style="font-weight: 600;">${escapeHtml(fieldName)}</td>
        <td><span class="badge ${badgeClass}">${escapeHtml(tier)}</span></td>
        <td style="font-family: var(--font-mono);">${escapeHtml(value)}</td>
        <td><span style="color: ${statusColor}; font-weight: 600;">${escapeHtml(status)}</span></td>
      `;
      diffTbody.appendChild(tr);
    });

    const modalDiffContent = document.getElementById("modal-diff-content");
    if (modalDiffContent && items.length > 0) {
      modalDiffContent.innerHTML = `<pre style="font-family: var(--font-mono); font-size: 0.8rem; overflow-x: auto; background: var(--color-abyss); padding: 1.25rem; border-radius: 8px; border: 1px solid var(--color-inkline);">${escapeHtml(JSON.stringify(items, null, 2))}</pre>`;
    }
  }

  // Auto-connect telemetry if page specifies data-task-id (e.g. task_detail.html)
  const pageTaskId =
    document.body.getAttribute("data-task-id") ||
    document.querySelector("[data-task-id]")?.getAttribute("data-task-id") ||
    (typeof currentTaskId !== "undefined" ? currentTaskId : null);
  if (pageTaskId) {
    currentActiveTaskId = pageTaskId;
    // Pre-fetch task details immediately for fast rendering
    fetch(`/api/tasks/${pageTaskId}`)
      .then((res) => {
        if (!res.ok) return null;
        return res.json();
      })
      .then((task) => {
        if (!task) return;
        if (task.status === "completed") {
          updatePipelineStage("COMPLETED", 100);
          handleCompletion(pageTaskId, task.result || task, true);
        } else if (task.status === "failed" || task.status === "refused") {
          handleFailure(task.error || `Task halted with status: ${task.status}`, task.status.toUpperCase());
        } else if (task.current_stage) {
          updatePipelineStage(task.current_stage, task.progress_percentage || 50);
          if (task.diff) {
            populateDiffTable({ diff: task.diff });
          }
        }
      })
      .catch(() => {});

    connectTelemetryStream(pageTaskId, true);
  }

  // Expose methods for external scripts or unit tests
  window.connectTelemetryStream = connectTelemetryStream;
  window.populateDiffTable = populateDiffTable;
  window.submitConsentDecision = submitConsentDecision;
});
