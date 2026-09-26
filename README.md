# NERV · Multi-Agent Digital Office & Telegram Control

> **Not a chatbot. A self-healing digital office of AI workers that plans, uses real tools, requests human approvals, and is controllable from both a web dashboard and Telegram.**

---

## ⚡ Key Highlights for Judges

1. **Manager Agent Loop**: Runs `Perceive → Plan → Act → Observe → Re-Plan → Escalate` rather than a single LLM call.
2. **JEV Dispatcher (Middleman)**:
   - Sits directly beneath the Top-Level Model (DeepSeek / Main API).
   - **Tier 1 (Code)**: Routes deterministic business logic (e.g. `days_overdue > 30` or `amount > 50,000`) straight to plain Python code (**0 LLM tokens burned!**).
   - **Tier 2 (Small Model)**: Routes simple data lookups, contact extraction, and table formatting to lightweight models (~75% cost savings).
   - **Tier 3 (Large Model)**: Reserves deep reasoning for complex planning and nuanced email tone selection.
   - **Prompt Caching**: Caches shared system context across worker calls to prevent redundant token consumption.
3. **Mid-Run Failure Recovery (Self-Healing)**:
   - When scanning accounts, if a record has missing/corrupted data (e.g., **Wayne Enterprises** missing contact email), the system **does not crash**.
   - It **observes** the failure, **re-plans** on the fly, flags the record for manual follow-up, and continues the automated run for all other healthy accounts.
4. **Approval Gate (Manual vs. Auto)**:
   - Single mode switch: **Auto** (only high-risk actions > ₹50,000 or external communications pause for approval) vs. **Manual** (every tool call waits for a human tap).
5. **Dual-Channel Synchronization (Web + Telegram `@nervvbot`)**:
   - Web dashboard and Telegram bot share the exact same backend state and SQLite database.
   - When a pause occurs, you get an inline push notification on Telegram with `[ ✅ Approve ]` and `[ ❌ Reject ]` buttons. Tapping approve on your phone updates the web dashboard in real time via WebSockets.
6. **Design & Brand Identity**:
   - **NERV** branding styled in the distinct **Fandom bold rounded typography** with embedded neon flame-heart emblem.
   - Retro arcade HUD (`LEVEL 1: OFFICE HARNESS`, `SCORE`, pixel hearts, `TOKENS SAVED`).
   - Cleaned of all irrelevant pricing tiers and GitHub rankings.

---

## 🚀 Quick Start

### 1. Launch NERV
```bash
python run.py
```
- **Web Dashboard**: [http://localhost:8000](http://localhost:8000)
- **Live WebSocket Bus**: `ws://localhost:8000/ws`
- **Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Connect Your Live Telegram Bot (Optional)
1. Message **@BotFather** on Telegram and create a bot (e.g. `@nervvbot`).
2. Copy your token and paste it into `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```
3. Restart `python run.py`. You can now text your bot `/start`, `/status`, `/goal`, and approve high-risk actions from your phone.
*(Note: If no token is set, the built-in interactive **Telegram Simulator** widget on the web dashboard lets you test the exact same Telegram experience right in your browser!)*

---

## 🎬 3-Minute Hackathon Demo Script

1. Open [http://localhost:8000](http://localhost:8000).
2. Click **"▶ Run Golden Path Demo"**:
   - Watch the Manager Agent **Perceive** the goal: *"Chase overdue invoices over ₹10,000"*.
   - Watch **JEV Dispatcher** route deterministic calculations to code (saving ~1,000 tokens).
   - Data Agent & Finance Agent execute in parallel.
   - Low-risk invoice (GlobalTech Solutions ₹18,500) automatically sends an email.
   - High-risk invoices (> ₹50,000: Apex Dynamics ₹68,400, Cyberdyne ₹95,000) pause at the **Approval Gate**.
3. **Approve from Phone / Telegram**:
   - Look at the right panel or the interactive Telegram phone simulator.
   - Click `[ ✅ Approve ]`. Watch the agent loop resume instantly and dispatch the notification!
4. **Trigger Mid-Run Failure Recovery**:
   - Click **"💥 Simulate Failure & Recovery"**.
   - Data Agent pulls Wayne Enterprises which lacks an email address.
   - Terminal logs: `[ANOMALY OBSERVED] Missing contact email for Wayne Enterprises`.
   - Manager Agent executes `RE-PLAN`: flags the account for manual follow-up without halting or crashing the remaining invoices!
5. **Review Audit Trail**:
   - Scroll down to the **Timestamped Audit Trail** to show judges every tool call, routing decision, model tier, and tokens saved.
