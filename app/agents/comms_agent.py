import asyncio
from typing import Dict, Any, List
from app.database import log_audit
from app.tools import tool_registry
from app.jev_dispatcher import jev_dispatcher

class CommsAgent:
    """
    Comms Agent:
    Specialist responsible for communications, drafting emails with tailored tones,
    and dispatching external notifications through the approval gate.
    """
    def __init__(self):
        self.name = "Comms Agent"
        self.role = "Communications & Outreach Specialist"

    async def draft_and_send(self, account: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        run_id = context.get("run_id", "default")
        customer = account.get("customer_name", "Customer")
        email = account.get("contact_email")
        amount = float(account.get("amount_inr", 0.0))
        days = int(account.get("days_overdue", 0))
        inv_no = account.get("invoice_number", "INV")

        # Pick appropriate tone using judgment
        tone = "urgent" if days >= 60 or amount >= 75000 else ("firm" if days >= 35 else "polite")

        # Draft email with Jev's judgment engine
        system_prompt = (
            "You are the Comms Agent for NERV. Draft clear, professional, "
            "and firm collection emails tailored to invoice amount and overdue days."
        )
        user_prompt = f"Draft email for {customer} ({inv_no}) owing ₹{amount:,.2f}, {days} days overdue with tone: {tone}"

        email_text = await jev_dispatcher.execute_judgment_call(user_prompt, system_prompt, context)

        lines = email_text.strip().split("\n")
        subject = lines[0].replace("Subject:", "").strip() if lines and "Subject:" in lines[0] else f"Invoice Reminder: {inv_no}"
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else email_text

        log_audit(
            run_id=run_id,
            agent=self.name,
            action="DRAFT_EMAIL",
            details=f"Drafted {tone} email for {customer} (Invoice {inv_no}, ₹{amount:,.2f})",
            model_tier="large_model",
            tokens_saved=0
        )

        # Execute send_email tool through approval gate
        tool_res = await tool_registry.execute_tool(
            "send_email",
            {
                "recipient_email": email,
                "recipient_name": customer,
                "subject": subject,
                "body": body,
                "tone": tone,
                "amount": amount,
                "invoice_number": inv_no
            },
            {**context, "agent_name": self.name}
        )

        if tool_res.requires_approval:
            return {
                "success": False,
                "status": "waiting_approval",
                "approval_id": tool_res.approval_id,
                "account": account,
                "subject": subject,
                "body": body,
                "amount": amount,
                "message": f"Paused: Sending email to {customer} (₹{amount:,.2f}) requires human approval."
            }

        if not tool_res.success:
            return {
                "success": False,
                "status": "failed",
                "error": tool_res.error,
                "account": account
            }

        return {
            "success": True,
            "status": "sent",
            "account": account,
            "data": tool_res.data
        }

comms_agent = CommsAgent()
