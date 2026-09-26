(function() {
  let ws = null;
  let currentMode = "auto";
  let tokensSaved = 2450;
  let hudScore = 3672;

  // DOM Elements
  const themeToggle = document.getElementById("theme-toggle");
  const modeToggleBtn = document.getElementById("mode-toggle-btn");
  const modeDot = document.getElementById("mode-dot");
  const modeText = document.getElementById("mode-text");
  const goalInput = document.getElementById("goal-input");
  const dispatchGoalBtn = document.getElementById("dispatch-goal-btn");
  const liveTerminal = document.getElementById("live-terminal-feed");
  const clearLogBtn = document.getElementById("clear-log-btn");
  const approvalQueueList = document.getElementById("approval-queue-list");
  const approvalCountBadge = document.getElementById("approval-count-badge");
  const accountsTableBody = document.getElementById("accounts-table-body");
  const auditTableBody = document.getElementById("audit-table-body");
  const refreshAuditBtn = document.getElementById("refresh-audit-btn");
  const wsIndicator = document.getElementById("ws-indicator");
  const wsStatus = document.getElementById("ws-status");
  const hudTokensSaved = document.getElementById("hud-tokens-saved");
  const hudScoreEl = document.getElementById("hud-score");

  // Presets
  const presetGolden = document.getElementById("preset-golden");
  const presetFailure = document.getElementById("preset-failure");
  const presetMode = document.getElementById("preset-mode");
  const presetReset = document.getElementById("preset-reset");

  // Telegram Mockup Elements
  const simPhoneChat = document.getElementById("sim-phone-chat");
  const simTgInput = document.getElementById("sim-tg-input");
  const simTgSendBtn = document.getElementById("sim-tg-send-btn");

  // ---------- Theme Management & Mobile Drawer ----------
  function initTheme() {
    const themeCheckbox = document.getElementById("theme-toggle-checkbox");
    const savedTheme = localStorage.getItem("nerv-theme") || "light";

    if (savedTheme === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
      if (themeCheckbox) themeCheckbox.checked = true;
    } else {
      document.documentElement.removeAttribute("data-theme");
      if (themeCheckbox) themeCheckbox.checked = false;
    }

    if (themeCheckbox) {
      themeCheckbox.addEventListener("change", (e) => {
        const isDark = e.target.checked;
        if (isDark) {
          document.documentElement.setAttribute("data-theme", "dark");
          localStorage.setItem("nerv-theme", "dark");
        } else {
          document.documentElement.removeAttribute("data-theme");
          localStorage.setItem("nerv-theme", "light");
        }
      });
    }

    // Mobile Drawer Toggle
    const mobileBtn = document.getElementById("mobile-toggle-btn");
    const mobileDrawer = document.getElementById("mobile-drawer");
    if (mobileBtn && mobileDrawer) {
      mobileBtn.addEventListener("click", () => {
        mobileDrawer.classList.toggle("open");
      });
      // Close drawer when any nav link is tapped
      mobileDrawer.querySelectorAll("a").forEach(link => {
        link.addEventListener("click", () => {
          mobileDrawer.classList.remove("open");
        });
      });
    }
  }

  // ---------- Scroll-Driven Office Expansion ----------
  function initOfficeScrollExpansion() {
    const officeFrame = document.getElementById("live-office-frame");
    const officeSection = document.getElementById("office");
    if (!officeFrame || !officeSection) return;

    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    let ticking = false;

    function updateOfficeScale() {
      const rect = officeSection.getBoundingClientRect();
      const windowHeight = window.innerHeight || document.documentElement.clientHeight;

      const start = windowHeight;
      const end = windowHeight * 0.2;
      const current = rect.top;

      let progress = 0;
      if (current < start) {
        progress = Math.min(1, Math.max(0, (start - current) / (start - end)));
      }

      if (rect.bottom < windowHeight * 0.4) {
        const exitProgress = Math.max(0, rect.bottom / (windowHeight * 0.4));
        progress = Math.min(progress, exitProgress);
      }

      const isMobile = window.innerWidth < 768;
      if (isMobile) {
        const scale = 0.96 + progress * 0.04;
        officeFrame.style.transform = `scale(${scale.toFixed(3)})`;
      } else {
        const scale = 0.93 + progress * 0.14;
        const shadowSpread = Math.round(progress * 15);
        officeFrame.style.transform = `scale(${scale.toFixed(3)})`;
        officeFrame.style.boxShadow = `0 ${10 + shadowSpread}px ${30 + shadowSpread * 2}px rgba(0,0,0,0.5), 0 6px 0 var(--border-dark)`;
      }

      ticking = false;
    }

    window.addEventListener("scroll", () => {
      if (!ticking) {
        window.requestAnimationFrame(updateOfficeScale);
        ticking = true;
      }
    }, { passive: true });

    updateOfficeScale();
  }

  // ---------- WebSocket Connection ----------
  function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host || "localhost:8000";
    const wsUrl = `${protocol}//${host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      if (wsIndicator) wsIndicator.className = "ws-dot online";
      if (wsStatus) wsStatus.textContent = "WebSocket: Connected";
      appendTerminalLog("SYSTEM", "WebSocket connected to NERV multi-agent orchestrator.", "dim");
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        handleServerEvent(payload);
      } catch (e) {
        console.error("Error parsing WS message:", e);
      }
    };

    ws.onclose = () => {
      if (wsIndicator) wsIndicator.className = "ws-dot";
      if (wsStatus) wsStatus.textContent = "WebSocket: Disconnected (reconnecting...)";
      setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
      console.warn("WebSocket error:", err);
    };
  }

  // ---------- Server Event Dispatcher ----------
  function handleServerEvent(event) {
    const { type, data, agents, timestamp } = event;

    if (type === "initial_state") {
      const state = event.state;
      if (state) {
        updateModeUI(state.mode);
        if (state.total_tokens_saved) {
          tokensSaved = state.total_tokens_saved;
          updateTokensUI(tokensSaved);
        }
        if (state.agents) updateAgentCards(state.agents);
      }
      fetchPendingApprovals();
      fetchAccounts();
      fetchAuditTrail();
      return;
    }

    if (agents) updateAgentCards(agents);

    if (type === "loop_stage") {
      const stage = data.stage;
      const msg = data.message;
      const agent = data.agent || "manager";
      appendTerminalLog(stage, `[${agent.toUpperCase()}] ${msg}`, `stage-${stage.toLowerCase()}`);

      // Add to HUD score & token metric
      hudScore += 45;
      if (hudScoreEl) hudScoreEl.textContent = hudScore;
      tokensSaved += (stage === "PLAN" ? 450 : (stage === "ACT" ? 300 : 0));
      updateTokensUI(tokensSaved);

      // If failure detected in OBSERVE
      if (data.has_failure) {
        appendTerminalLog("ANOMALY", "⚠️ Missing email observed for Wayne Enterprises. Pipeline entering RE-PLAN.", "stage-replan");
        pushTelegramBubble("⚠️ <em>Anomaly Observed:</em> Missing contact record detected for Wayne Enterprises. Self-healing re-plan activated.");
      }
    }

    if (type === "approval_required") {
      appendTerminalLog("ESCALATE", `PAUSED: Approval required for ${data.customer} (₹${Number(data.amount).toLocaleString('en-IN')})`, "stage-escalate");
      addApprovalCard(data);
      pushTelegramApproval(data);
    }

    if (type === "approval_decided") {
      const icon = data.decision === "approved" ? "✅" : "❌";
      appendTerminalLog("APPROVAL", `${icon} ${data.title} ${data.decision.toUpperCase()} via ${data.channel.toUpperCase()}`, "stage-act");
      removeApprovalCard(data.approval_id);
      pushTelegramBubble(`${icon} <strong>Action ${data.decision.toUpperCase()}</strong>: ${data.title} (Channel: ${data.channel})`);
      fetchAccounts();
      fetchAuditTrail();
    }

    if (type === "email_sent") {
      appendTerminalLog("COMMS", `✅ Email successfully sent to ${data.customer} [${data.invoice}]`, "stage-act");
      fetchAccounts();
    }

    if (type === "mode_changed") {
      updateModeUI(data.mode);
      appendTerminalLog("MODE", `Approval Gate mode changed to ${data.mode.toUpperCase()}`, "dim");
    }

    if (type === "system_reset") {
      appendTerminalLog("RESET", "Demo system and database reset.", "system-welcome");
      fetchAccounts();
      fetchAuditTrail();
      fetchPendingApprovals();
    }
  }

  // ---------- Terminal Logging ----------
  function appendTerminalLog(prefix, message, cssClass = "") {
    if (!liveTerminal) return;
    const now = new Date().toTimeString().split(" ")[0];
    const line = document.createElement("div");
    line.className = `log-line ${cssClass}`;
    line.innerHTML = `<span class="time">[${now}]</span> <span class="prefix">[${prefix}]</span> <span>${escapeHtml(message)}</span>`;
    liveTerminal.appendChild(line);
    liveTerminal.scrollTop = liveTerminal.scrollHeight;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // ---------- Mode Management ----------
  function updateModeUI(mode) {
    currentMode = mode;
    if (modeText) modeText.textContent = `${mode.toUpperCase()} MODE`;
    if (modeDot) {
      modeDot.className = `mode-indicator ${mode === "manual" ? "manual" : ""}`;
    }
  }

  async function toggleMode() {
    const next = currentMode === "auto" ? "manual" : "auto";
    try {
      const resp = await fetch("/api/mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: next })
      });
      const data = await resp.json();
      if (data.success) {
        updateModeUI(data.mode);
      }
    } catch (e) {
      console.error("Failed to toggle mode:", e);
    }
  }

  function updateTokensUI(count) {
    if (hudTokensSaved) hudTokensSaved.textContent = Number(count).toLocaleString('en-IN');
  }

  // ---------- Agent Status Cards ----------
  function updateAgentCards(agents) {
    for (const [key, agent] of Object.entries(agents)) {
      const card = document.getElementById(`card-${key}`);
      const badge = document.getElementById(`badge-${key}`);
      const desc = document.getElementById(`desc-${key}`);

      if (badge) {
        badge.textContent = agent.state.toUpperCase();
        badge.className = `agent-status-badge badge-${agent.state === "working" ? "working" : (agent.state === "error_recovered" ? "recovered" : (agent.state === "waiting_approval" ? "waiting" : "idle"))}`;
      }
      if (desc && agent.detail) {
        desc.textContent = agent.detail;
      }
      if (card) {
        card.className = `agent-card state-${agent.state === "working" ? "working" : (agent.state === "error_recovered" ? "recovered" : (agent.state === "waiting_approval" ? "waiting" : "idle"))}`;
      }
    }
  }

  // ---------- Approval Queue Cards ----------
  function addApprovalCard(appr) {
    if (!approvalQueueList) return;
    const existing = document.getElementById(`appr-card-${appr.approval_id}`);
    if (existing) return;

    // Remove placeholder
    const placeholder = approvalQueueList.querySelector(".empty-queue-placeholder");
    if (placeholder) placeholder.remove();

    const card = document.createElement("div");
    card.className = "approval-item";
    card.id = `appr-card-${appr.approval_id}`;
    card.innerHTML = `
      <div class="approval-item-header">
        <span class="approval-title">${escapeHtml(appr.customer)} [${escapeHtml(appr.invoice)}]</span>
        <span class="approval-amount">₹${Number(appr.amount).toLocaleString('en-IN')}</span>
      </div>
      <p class="approval-desc">${escapeHtml(appr.message || appr.description || "Action paused for human approval")}</p>
      <div class="approval-actions">
        <button class="btn-approve" onclick="window.decideApproval('${appr.approval_id}', 'approve')">✅ Approve</button>
        <button class="btn-reject" onclick="window.decideApproval('${appr.approval_id}', 'reject')">❌ Reject</button>
      </div>
    `;
    approvalQueueList.prepend(card);
    updateApprovalCount();
  }

  function removeApprovalCard(approvalId) {
    const card = document.getElementById(`appr-card-${approvalId}`);
    if (card) card.remove();
    updateApprovalCount();
  }

  function updateApprovalCount() {
    if (!approvalQueueList || !approvalCountBadge) return;
    const items = approvalQueueList.querySelectorAll(".approval-item");
    approvalCountBadge.textContent = `${items.length} Pending`;
    if (items.length === 0) {
      approvalQueueList.innerHTML = `
        <div class="empty-queue-placeholder">
          <span>✅</span>
          <p>Approval queue is clear. Low-risk operations run automatically.</p>
        </div>
      `;
    }
  }

  window.decideApproval = async function(approvalId, decision) {
    try {
      const resp = await fetch(`/api/${decision}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approval_id: approvalId,
          decision: decision,
          channel: "web"
        })
      });
      if (!resp.ok) throw new Error("API not available");
      const data = await resp.json();
      if (!data.success) {
        alert(`Error: ${data.error}`);
      }
    } catch (e) {
      // Client fallback for static/GitHub Pages viewing
      removeApprovalCard(approvalId);
      const isApproved = decision === "approve";
      appendTerminalLog("APPROVAL", `Human operator ${isApproved ? 'APPROVED' : 'REJECTED'} action [${approvalId}] via Web console.`, isApproved ? "stage-act" : "stage-observe");
      updateAgentUI("finance", "idle", `Audit complete (${isApproved ? 'Approved' : 'Rejected'})`);
      
      if (isApproved) {
        setTimeout(() => {
          appendTerminalLog("COMMS", `send_email("billing@apexdyn.com", tone="firm_professional") -> Payment notice delivered.`, "stage-act");
          updateAgentUI("comms", "active", "Email dispatched to debtor");
          setTimeout(() => {
            appendTerminalLog("MANAGER", `Goal execution completed. All active accounts processed.`, "stage-plan");
            updateAgentUI("manager", "idle", "Standby for next mission");
            updateAgentUI("comms", "idle", "Standby");
          }, 1200);
        }, 800);
      }
    }
  };

  async function fetchPendingApprovals() {
    try {
      const resp = await fetch("/api/approvals");
      const data = await resp.json();
      if (data.approvals) {
        data.approvals.forEach(a => {
          addApprovalCard({
            approval_id: a.id,
            customer: a.title,
            amount: a.amount_inr,
            invoice: a.task_id || "INV",
            message: a.description
          });
        });
      }
    } catch (e) {
      console.warn("Could not fetch pending approvals:", e);
    }
  }

  // ---------- Live Accounts Table ----------
  // ---------- Live Accounts Table ----------
  const DEFAULT_SAMPLE_ACCOUNTS = [
    { customer_name: "GlobalTech Solutions", invoice_number: "INV-101", amount_inr: 18500, days_overdue: 37, contact_email: "accounts@globaltech.io" },
    { customer_name: "Apex Dynamics", invoice_number: "INV-102", amount_inr: 68400, days_overdue: 42, contact_email: "billing@apexdyn.com" },
    { customer_name: "Wayne Enterprises", invoice_number: "INV-103", amount_inr: 12200, days_overdue: 32, contact_email: "" },
    { customer_name: "Cyberdyne Systems", invoice_number: "INV-104", amount_inr: 95000, days_overdue: 60, contact_email: "sarah@cyberdyne.net" },
    { customer_name: "Umbreon Biotech", invoice_number: "INV-106", amount_inr: 54000, days_overdue: 47, contact_email: "accounts@umbreon.io" }
  ];

  function renderAccountsList(accounts) {
    if (!accountsTableBody) return;
    accountsTableBody.innerHTML = accounts.map(a => {
      const isFlagged = !a.contact_email;
      const statusClass = isFlagged ? "flagged" : (a.days_overdue >= 30 ? "overdue" : "current");
      const statusText = isFlagged ? "MISSING EMAIL (FLAGGED)" : `${a.days_overdue}D OVERDUE`;

      return `
        <div class="acc-row">
          <div class="acc-left">
            <span class="acc-name">${escapeHtml(a.customer_name)}</span>
            <span class="acc-meta">${a.invoice_number} &bull; ${a.contact_email || '⚠️ No email'}</span>
          </div>
          <div class="acc-right">
            <div class="acc-amount">₹${Number(a.amount_inr).toLocaleString('en-IN')}</div>
            <span class="acc-status ${statusClass}">${statusText}</span>
          </div>
        </div>
      `;
    }).join("");

    const summary = document.getElementById("accounts-count-summary");
    if (summary) summary.textContent = `${accounts.length} total accounts`;
  }

  async function fetchAccounts() {
    if (!accountsTableBody) return;
    try {
      const resp = await fetch("/api/accounts");
      if (!resp.ok) throw new Error("API not available");
      const data = await resp.json();
      renderAccountsList(data.accounts || DEFAULT_SAMPLE_ACCOUNTS);
    } catch (e) {
      // Fallback for GitHub Pages static viewing
      renderAccountsList(DEFAULT_SAMPLE_ACCOUNTS);
    }
  }

  // ---------- Audit Trail Table ----------
  const DEFAULT_SAMPLE_AUDIT = [
    { timestamp: "14:32:10", action: "send_email", agent: "comms", details: "Dispatched payment notice to accounts@globaltech.io (₹18,500)", status: "completed" },
    { timestamp: "14:31:55", action: "request_approval", agent: "finance", details: "Approval APPR-002 requested for Apex Dynamics (₹68,400 > ₹50k limit)", status: "paused" },
    { timestamp: "14:31:40", action: "missing_record_recovery", agent: "manager", details: "Self-healing: Flagged Wayne Enterprises (missing email) to Telegram, continued batch", status: "recovered" },
    { timestamp: "14:31:12", action: "read_spreadsheet", agent: "data", details: "Parsed data/accounts_overdue.csv: 6 records identified, 5 overdue", status: "completed" }
  ];

  function renderAuditTrailList(trail) {
    if (!auditTableBody) return;
    auditTableBody.innerHTML = trail.map(row => {
      const isRecovered = row.status === "recovered" || row.status === "flagged";
      const isApproved = row.status === "approved";
      const isWarn = row.status === "paused" || row.status === "warning";
      const statusPill = isRecovered
        ? '<span class="status-pill-rec">RECOVERED</span>'
        : (isApproved
          ? '<span class="status-pill-ok">APPROVED</span>'
          : (isWarn ? '<span class="status-pill-warn">WAITING</span>' : '<span class="status-pill-ok">OK</span>'));

      return `
        <tr>
          <td><span class="audit-time">${row.timestamp || ''}</span></td>
          <td><span class="audit-badge ${row.agent || 'sys'}">${(row.agent || 'SYSTEM').toUpperCase()}</span></td>
          <td><span class="audit-action">${escapeHtml(row.action || '')}</span></td>
          <td><span class="audit-desc">${escapeHtml(row.details || '')}</span></td>
          <td>${statusPill}</td>
        </tr>
      `;
    }).join("");
  }

  async function fetchAuditTrail() {
    if (!auditTableBody) return;
    try {
      const resp = await fetch("/api/audit");
      if (!resp.ok) throw new Error("API not available");
      const data = await resp.json();
      renderAuditTrailList(data.audit_trail || DEFAULT_SAMPLE_AUDIT);
    } catch (e) {
      renderAuditTrailList(DEFAULT_SAMPLE_AUDIT);
    }
  }

        return `
          <tr>
            <td><code>${row.timestamp ? row.timestamp.split(" ")[1] : ''}</code></td>
            <td><strong>${escapeHtml(row.agent)}</strong></td>
            <td><code>${escapeHtml(row.action)}</code></td>
            <td><span class="pill pill-tag">${escapeHtml(row.model_tier)}</span></td>
            <td>${escapeHtml(row.details)}</td>
            <td>${statusPill}</td>
          </tr>
        `;
      }).join("");
    } catch (e) {
      console.warn("Could not fetch audit trail:", e);
    }
  }

  // ---------- Dispatching Goals ----------
  function runClientSideSimulation(goalText) {
    appendTerminalLog("MANAGER", `[PERCEIVE] Goal accepted: "${goalText}". Initiating Jev Dispatcher.`, "stage-plan");
    updateAgentUI("manager", "planning", "Formulating multi-agent breakdown...");
    
    setTimeout(() => {
      appendTerminalLog("JEV", `Classifying tasks: deterministic math -> Code (0 tokens), email tone -> DeepSeek API.`, "stage-plan");
      updateAgentUI("jev", "active", "Routing tasks across tiers");
    }, 700);

    setTimeout(() => {
      appendTerminalLog("DATA", `read_spreadsheet("data/accounts_overdue.csv") -> 5 overdue records loaded.`, "stage-act");
      appendTerminalLog("DATA", `WARNING: Record ACC-003 (Wayne Enterprises) has missing contact email!`, "stage-observe");
      updateAgentUI("data", "active", "Parsing CSV & DB records");
    }, 1500);

    setTimeout(() => {
      appendTerminalLog("MANAGER", `[RE-PLAN] Self-healing activated: Flagging ACC-003 to Human, proceeding with remaining 4 accounts.`, "stage-plan");
      updateAgentUI("manager", "active", "Self-healing re-plan applied");
    }, 2300);

    setTimeout(() => {
      appendTerminalLog("FINANCE", `Auditing amounts: 2 accounts exceed ₹50,000 threshold (Apex Dynamics ₹68,400, Cyberdyne ₹95,000).`, "stage-observe");
      appendTerminalLog("FINANCE", `[ESCALATE] Triggering human approval gate for Apex Dynamics (₹68,400).`, "stage-escalate");
      updateAgentUI("finance", "waiting_approval", "Awaiting human authorization");
      
      const simAppr = {
        approval_id: "APPR-" + Math.floor(100 + Math.random() * 900),
        customer: "Apex Dynamics",
        amount: 68400,
        due_date: "2026-08-15",
        status: "pending"
      };
      pendingApprovals.push(simAppr);
      renderApprovals();
      pushTelegramApproval(simAppr);
      pushTelegramBubble(`🔔 <em>Action Paused:</em> Apex Dynamics invoice ₹68,400 requires executive sign-off.`);
    }, 3200);
  }

  async function dispatchGoal(goalText) {
    if (!goalText) return;
    appendTerminalLog("DISPATCH", `Submitting goal: "${goalText}" in ${currentMode.toUpperCase()} mode.`, "stage-plan");

    try {
      const resp = await fetch("/api/goal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: goalText,
          mode: currentMode,
          threshold: 50000.0
        })
      });
      if (!resp.ok) throw new Error("API responded with error");
      const data = await resp.json();
      if (!data.success) {
        alert(`Failed to dispatch: ${data.message}`);
      }
    } catch (e) {
      console.warn("Backend API not reachable. Running client-side simulation:", e);
      runClientSideSimulation(goalText);
    }
  }

  // ---------- Telegram Phone Simulator ----------
  function pushTelegramBubble(html, isUser = false) {
    if (!simPhoneChat) return;
    const now = new Date().toTimeString().slice(0, 5);
    const bubble = document.createElement("div");
    bubble.className = `msg-bubble ${isUser ? 'user' : 'bot'}`;
    bubble.innerHTML = `
      <div class="msg-text">${html}</div>
      <span class="msg-time">${now}</span>
    `;
    simPhoneChat.appendChild(bubble);
    simPhoneChat.scrollTop = simPhoneChat.scrollHeight;
  }

  function pushTelegramApproval(appr) {
    if (!simPhoneChat) return;
    const now = new Date().toTimeString().slice(0, 5);
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble bot";
    bubble.id = `tg-appr-${appr.approval_id}`;
    bubble.innerHTML = `
      <div class="msg-text">
        ⚠️ <strong>Approval Request [${appr.approval_id}]</strong><br>
        Invoice for <strong>${escapeHtml(appr.customer)}</strong> exceeds ₹50k limit: <strong>₹${Number(appr.amount).toLocaleString('en-IN')}</strong>.<br>
        Do you approve sending collection notice?
      </div>
      <div class="msg-inline-buttons">
        <button class="sim-btn sim-btn-approve" onclick="simulateTelegramAction('approve', '${appr.approval_id}')">✅ Approve</button>
        <button class="sim-btn sim-btn-reject" onclick="simulateTelegramAction('reject', '${appr.approval_id}')">❌ Reject</button>
      </div>
      <span class="msg-time">${now}</span>
    `;
    simPhoneChat.appendChild(bubble);
    simPhoneChat.scrollTop = simPhoneChat.scrollHeight;
  }

  window.simulateTelegramAction = async function(action, approvalId) {
    if (approvalId) {
      try {
        const resp = await fetch(`/api/${action}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            approval_id: approvalId,
            decision: action,
            channel: "telegram"
          })
        });
        const data = await resp.json();
        const icon = action === "approve" ? "✅" : "❌";
        pushTelegramBubble(`${icon} You tapped <strong>${action.toUpperCase()}</strong> on your phone. Manager Agent notified.`, true);
      } catch (e) {
        console.error("Error in simulated telegram action:", e);
      }
    } else {
      // General sim call
      try {
        const resp = await fetch("/api/telegram/sim", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: action })
        });
        const data = await resp.json();
        if (data.reply) pushTelegramBubble(data.reply);
      } catch (e) {
        console.error("Sim error:", e);
      }
    }
  };

  async function sendTelegramInput() {
    if (!simTgInput) return;
    const text = simTgInput.value.trim();
    if (!text) return;
    simTgInput.value = "";

    pushTelegramBubble(escapeHtml(text), true);

    let action = "ask";
    if (text.startsWith("/status")) action = "status";
    else if (text.startsWith("/audit")) action = "audit";
    else if (text.startsWith("/approvals")) action = "approvals";
    else if (text.startsWith("/approve")) action = "approve";
    else if (text.startsWith("/reject")) action = "reject";

    try {
      const resp = await fetch("/api/telegram/sim", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action, text: text })
      });
      const data = await resp.json();
      if (data.reply) pushTelegramBubble(data.reply);
    } catch (e) {
      console.error("Sim error:", e);
    }
  }

  // ---------- Chibi Talking Floor Animation ----------
  function initChibiFloor() {
    const floor = document.getElementById("chibi-floor");
    if (!floor) return;

    const SCRIPT = [
      { who: "manager", text: "Goal perceived: chase overdue invoices over ₹10k." },
      { who: "jev", text: "Jev routing: math to code (0 tokens), tone to DeepSeek." },
      { who: "data", text: "5 accounts pulled. Notice: 1 record missing contact email!" },
      { who: "manager", text: "Self-healing re-plan: skip missing record, proceed with other 4." },
      { who: "finance", text: "2 invoices exceed ₹50,000 threshold. Holding for approval." },
      { who: "comms", text: "Drafted firm emails. Approval prompt dispatched to Telegram!" }
    ];

    let idx = 0;
    setInterval(() => {
      const line = SCRIPT[idx % SCRIPT.length];
      idx++;

      floor.querySelectorAll(".chibi").forEach(c => {
        c.classList.remove("talking");
        const b = c.querySelector(".chibi-bubble");
        if (b) b.className = "chibi-bubble";
      });

      const active = floor.querySelector(`.chibi[data-name="${line.who}"]`);
      if (active) {
        active.classList.add("talking");
        const bubble = active.querySelector(".chibi-bubble");
        if (bubble) {
          bubble.textContent = line.text;
          bubble.className = "chibi-bubble show";
        }
      }
    }, 3600);
  }

  // ---------- Event Listeners Setup ----------
  function initEvents() {
    if (modeToggleBtn) {
      modeToggleBtn.addEventListener("click", toggleMode);
    }

    if (dispatchGoalBtn && goalInput) {
      dispatchGoalBtn.addEventListener("click", () => dispatchGoal(goalInput.value.trim()));
      goalInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") dispatchGoal(goalInput.value.trim());
      });
    }

    if (clearLogBtn && liveTerminal) {
      clearLogBtn.addEventListener("click", () => {
        liveTerminal.innerHTML = '<div class="log-line dim">Log cleared. Ready for next loop stage.</div>';
      });
    }

    if (refreshAuditBtn) {
      refreshAuditBtn.addEventListener("click", fetchAuditTrail);
    }

    // Presets
    if (presetGolden) {
      presetGolden.addEventListener("click", () => {
        if (goalInput) goalInput.value = "Chase overdue invoices over ₹10,000";
        if (currentMode !== "auto") toggleMode();
        dispatchGoal("Chase overdue invoices over ₹10,000");
      });
    }

    if (presetFailure) {
      presetFailure.addEventListener("click", () => {
        if (goalInput) goalInput.value = "Chase all invoices and test missing record resilience";
        dispatchGoal("Chase all invoices and test missing record resilience");
      });
    }

    if (presetMode) {
      presetMode.addEventListener("click", toggleMode);
    }

    if (presetReset) {
      presetReset.addEventListener("click", async () => {
        await fetch("/api/reset", { method: "POST" });
      });
    }

    // Phone simulator input
    if (simTgSendBtn) {
      simTgSendBtn.addEventListener("click", sendTelegramInput);
    }
    if (simTgInput) {
      simTgInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") sendTelegramInput();
      });
    }

    // Floating Telegram button smooth scroll
    const floatBtn = document.getElementById("tg-float-btn");
    if (floatBtn) {
      floatBtn.addEventListener("click", () => {
        const tgSec = document.getElementById("telegram");
        if (tgSec) tgSec.scrollIntoView({ behavior: "smooth" });
      });
    }
  }

  // Initialization
  initTheme();
  initEvents();
  initOfficeScrollExpansion();
  connectWebSocket();
})();
