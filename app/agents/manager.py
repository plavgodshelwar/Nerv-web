import asyncio
import json
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from app.database import get_db, log_audit
from app.jev_dispatcher import jev_dispatcher
from app.agents.data_agent import data_agent
from app.agents.finance_agent import finance_agent
from app.agents.comms_agent import comms_agent

class ManagerAgent:
    """
    Manager Agent: The Central Brain & Orchestrator.
    Runs the agent loop:
    1. PERCEIVE  → Inspect goal, determine data sources & operational scope
    2. PLAN      → Consult Jev Dispatcher to break goal into tasks & routes
    3. ACT       → Dispatch tasks to Data, Finance, and Comms workers in parallel
    4. OBSERVE   → Monitor outcomes, check for data failures or anomalies
    5. RE-PLAN   → If a worker encounters an error (missing record), adapt without crashing!
    6. ESCALATE  → If risky (over threshold), pause and demand human approval (Web/Telegram)
    7. FINISH    → Execute approved actions, audit everything, report final state
    """
    def __init__(self, broadcast_fn: Optional[Callable] = None):
        self.name = "Manager Agent"
        self.role = "Office Orchestrator & Workflow Manager"
        self.broadcast_fn = broadcast_fn

    async def notify(self, event_type: str, data: Dict[str, Any]):
        if self.broadcast_fn:
            await self.broadcast_fn(event_type, data)

    async def run_goal(self, run_id: str, goal: str, mode: str = "auto", threshold: float = 50000.0) -> Dict[str, Any]:
        context = {
            "run_id": run_id,
            "goal": goal,
            "mode": mode,
            "threshold": threshold
        }

        # ----------------------------------------------------
        # 1. PERCEIVE
        # ----------------------------------------------------
        await self.notify("loop_stage", {
            "stage": "PERCEIVE",
            "agent": "manager",
            "message": f"Perceiving operational goal: '{goal}'. Inspecting data repositories and rules."
        })
        log_audit(
            run_id=run_id,
            agent=self.name,
            action="PERCEIVE",
            details=f"Perceiving goal: '{goal}' in {mode.upper()} mode with approval threshold ₹{threshold:,.2f}.",
            model_tier="large_model"
        )
        await asyncio.sleep(0.6)

        # ----------------------------------------------------
        # 2. PLAN
        # ----------------------------------------------------
        await self.notify("loop_stage", {
            "stage": "PLAN",
            "agent": "manager",
            "message": "Formulating execution plan with JEV Dispatcher: parallel pull of data and financial metrics."
        })

        jev_plan = jev_dispatcher.route_task("plan", goal, {"threshold": threshold})
        log_audit(
            run_id=run_id,
            agent="JEV Dispatcher",
            action="PLAN_DISPATCH",
            details=f"Jev generated 3-stage plan: Data extraction -> Finance audit -> Comms outreach. {jev_plan['rationale']}",
            model_tier=jev_plan["tier"],
            tokens_saved=jev_plan.get("tokens_saved", 0)
        )
        await asyncio.sleep(0.6)

        # ----------------------------------------------------
        # 3. ACT (Data Extraction & Finance Audit)
        # Parallel Execution: Data Agent + System Pre-checks
        # ----------------------------------------------------
        await self.notify("loop_stage", {
            "stage": "ACT",
            "agent": "data",
            "message": "Data Agent reading spreadsheet and customer database."
        })

        data_task = data_agent.execute("read_spreadsheet", {}, context)
        # Execute in parallel
        data_result, = await asyncio.gather(data_task)

        if not data_result.get("success"):
            error_msg = f"Fatal pipeline failure in Data Agent: {data_result.get('error')}"
            await self.notify("error", {"message": error_msg})
            return {"success": False, "error": error_msg}

        raw_records = data_result.get("valid_records", [])
        flagged_records = data_result.get("flagged_records", [])

        # Act: Finance Worker audits numbers in parallel
        await self.notify("loop_stage", {
            "stage": "ACT",
            "agent": "finance",
            "message": f"Finance Agent auditing {len(raw_records)} accounts against credit rules."
        })
        finance_result = await finance_agent.execute("audit", {"records": raw_records}, context)

        eligible_records = finance_result.get("eligible_records", [])
        high_risk_invoices = finance_result.get("high_risk_invoices", [])
        low_risk_invoices = finance_result.get("low_risk_invoices", [])

        await asyncio.sleep(0.7)

        # ----------------------------------------------------
        # 4. OBSERVE (The Mid-Run Failure Detection Beat!)
        # ----------------------------------------------------
        failure_detected = len(flagged_records) > 0
        observe_text = f"Observed {len(raw_records)} valid accounts, {len(eligible_records)} overdue >= 30 days."
        if failure_detected:
            flag_info = ", ".join([f["customer_name"] for f in flagged_records])
            observe_text += f" [ANOMALY DETECTED]: Missing contact email for {flag_info}!"

        await self.notify("loop_stage", {
            "stage": "OBSERVE",
            "agent": "manager",
            "message": observe_text,
            "has_failure": failure_detected,
            "flagged": flagged_records
        })
        log_audit(
            run_id=run_id,
            agent=self.name,
            action="OBSERVE",
            details=observe_text,
            status="warning" if failure_detected else "ok"
        )
        await asyncio.sleep(0.8)

        # ----------------------------------------------------
        # 5. RE-PLAN (Self-Healing / Adaptability)
        # ----------------------------------------------------
        if failure_detected:
            replan_text = (
                f"RE-PLANNING: Detected {len(flagged_records)} corrupted/incomplete records. "
                "Skipping automated email for these records, creating manual follow-up tickets, "
                f"and continuing automated workflow for the other {len(eligible_records)} healthy accounts."
            )
            await self.notify("loop_stage", {
                "stage": "RE-PLAN",
                "agent": "manager",
                "message": replan_text
            })
            log_audit(
                run_id=run_id,
                agent=self.name,
                action="RE_PLAN",
                details=replan_text,
                model_tier="large_model",
                status="recovered"
            )
            await asyncio.sleep(0.8)

        # ----------------------------------------------------
        # 6. ESCALATE & APPROVAL GATE
        # ----------------------------------------------------
        pending_comms = []
        waiting_approvals = []
        sent_emails = []

        await self.notify("loop_stage", {
            "stage": "ESCALATE",
            "agent": "comms",
            "message": f"Comms Agent preparing outreach for {len(eligible_records)} overdue accounts."
        })

        for acc in eligible_records:
            draft_res = await comms_agent.draft_and_send(acc, context)
            if draft_res.get("status") == "waiting_approval":
                waiting_approvals.append(draft_res)
                await self.notify("approval_required", {
                    "approval_id": draft_res["approval_id"],
                    "customer": acc["customer_name"],
                    "amount": acc["amount_inr"],
                    "invoice": acc["invoice_number"],
                    "subject": draft_res["subject"],
                    "body": draft_res["body"],
                    "message": draft_res["message"]
                })
            elif draft_res.get("status") == "sent":
                sent_emails.append(draft_res)
                await self.notify("email_sent", {
                    "customer": acc["customer_name"],
                    "amount": acc["amount_inr"],
                    "invoice": acc["invoice_number"]
                })

        summary = (
            f"Run completed: {len(sent_emails)} emails sent directly, "
            f"{len(waiting_approvals)} paused for approval (> ₹{threshold:,.2f} or manual mode), "
            f"{len(flagged_records)} flagged for manual review."
        )

        status = "waiting_approval" if waiting_approvals else "completed"

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE runs SET status = ?, summary = ? WHERE id = ?", (status, summary, run_id))
        conn.commit()
        conn.close()

        await self.notify("loop_stage", {
            "stage": "FINISH" if not waiting_approvals else "PAUSED",
            "agent": "manager",
            "message": summary,
            "status": status
        })

        return {
            "success": True,
            "status": status,
            "run_id": run_id,
            "sent_count": len(sent_emails),
            "waiting_approval_count": len(waiting_approvals),
            "flagged_count": len(flagged_records),
            "summary": summary
        }
