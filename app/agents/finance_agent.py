import asyncio
from typing import Dict, Any, List
from app.database import log_audit
from app.jev_dispatcher import jev_dispatcher

class FinanceAgent:
    """
    Finance Agent:
    Audits numbers, checks days overdue, applies company credit rules,
    and flags any invoices exceeding the configurable approval threshold.
    Operates independently and runs in parallel with Data and Comms agents.
    """
    def __init__(self):
        self.name = "Finance Agent"
        self.role = "Financial Analyst & Risk Auditor"

    async def execute(self, task: str, payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        run_id = context.get("run_id", "default")
        records = payload.get("records", [])
        threshold = float(context.get("threshold", 50000.0))

        log_audit(
            run_id=run_id,
            agent=self.name,
            action="AUDIT_INVOICES",
            details=f"Auditing {len(records)} records against approval threshold ₹{threshold:,.2f}.",
            tool_name="calculate_threshold",
            model_tier="code",
            tokens_saved=500
        )

        overdue_eligible = []
        high_risk_invoices = []
        low_risk_invoices = []
        total_overdue_amount = 0.0

        for r in records:
            amount = float(r.get("amount_inr", 0.0))
            days = int(r.get("days_overdue", 0))

            # Plain deterministic code: Jev routes this with 0 tokens!
            if days >= 30: # Only pursue if >= 30 days overdue
                overdue_eligible.append(r)
                total_overdue_amount += amount

                if amount >= threshold:
                    high_risk_invoices.append(r)
                else:
                    low_risk_invoices.append(r)

        summary = (
            f"Finance Agent analyzed {len(records)} accounts: {len(overdue_eligible)} are >= 30 days overdue "
            f"(Total: ₹{total_overdue_amount:,.2f}). {len(high_risk_invoices)} exceed threshold ₹{threshold:,.2f}."
        )

        log_audit(
            run_id=run_id,
            agent=self.name,
            action="AUDIT_COMPLETE",
            details=summary,
            model_tier="code",
            tokens_saved=420
        )

        return {
            "success": True,
            "overdue_count": len(overdue_eligible),
            "total_amount": total_overdue_amount,
            "high_risk_invoices": high_risk_invoices,
            "low_risk_invoices": low_risk_invoices,
            "eligible_records": overdue_eligible,
            "summary": summary
        }

finance_agent = FinanceAgent()
