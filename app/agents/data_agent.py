import asyncio
from typing import Dict, Any, List
from app.tools import tool_registry
from app.database import log_audit

class DataAgent:
    """
    Data Agent:
    Specialist responsible for reading spreadsheets and querying customer databases.
    Crucial feature: Resilient to mid-run failures. If a record has missing fields
    (e.g., missing contact email), it detects it, flags it for manual follow-up,
    and returns clean partitioned batches without crashing the pipeline!
    """
    def __init__(self):
        self.name = "Data Agent"
        self.role = "Data & Database Specialist"

    async def execute(self, task: str, payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        run_id = context.get("run_id", "default")
        log_audit(
            run_id=run_id,
            agent=self.name,
            action="READ_DATA",
            details="Scanning accounts spreadsheet and customer database for overdue records.",
            tool_name="read_spreadsheet",
            model_tier="code",
            tokens_saved=350
        )

        # Call real tool
        tool_res = await tool_registry.execute_tool(
            "read_spreadsheet",
            {"file_path": payload.get("file_path")},
            {**context, "agent_name": self.name}
        )

        if not tool_res.success:
            return {"success": False, "error": tool_res.error}

        raw_rows = tool_res.data.get("rows", [])
        valid_records = []
        flagged_records = []

        # Validate records & handle deliberate failure gracefully
        for row in raw_rows:
            # Check for missing email or critical field
            email = row.get("contact_email")
            cust_name = row.get("customer_name", "Unknown")
            inv_num = row.get("invoice_number", "N/A")

            if not email or "@" not in str(email).strip():
                # DELIBERATE MID-RUN FAILURE RECOVERY BEAT:
                flag_reason = f"Missing contact email for invoice {inv_num} ({cust_name})"
                flagged_records.append({**row, "flag_reason": flag_reason})
                log_audit(
                    run_id=run_id,
                    agent=self.name,
                    action="FAILURE_HANDLED",
                    details=f"OBSERVED: {flag_reason}. Gracefully flagged for manual review; continuing batch.",
                    tool_name="read_spreadsheet",
                    model_tier="code",
                    tokens_saved=200,
                    status="flagged"
                )
            else:
                valid_records.append(row)

        return {
            "success": True,
            "total_count": len(raw_rows),
            "valid_records": valid_records,
            "flagged_records": flagged_records,
            "summary": f"Data Agent read {len(raw_rows)} records: {len(valid_records)} valid, {len(flagged_records)} flagged for manual review."
        }

data_agent = DataAgent()
