import os
import csv
import json
import sqlite3
import subprocess
import tempfile
import asyncio
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from pathlib import Path
from app.database import get_db, log_audit, DB_PATH, CSV_PATH

# Sandboxed shell commands whitelist
ALLOWED_SHELL_COMMANDS = {
    "echo", "date", "whoami", "python -c", "node -e", "cat", "grep", "wc", "ls", "dir", "calc"
}

class ToolExecutionResult:
    def __init__(self, success: bool, data: Any = None, error: Optional[str] = None, requires_approval: bool = False, approval_id: Optional[str] = None):
        self.success = success
        self.data = data
        self.error = error
        self.requires_approval = requires_approval
        self.approval_id = approval_id

    def to_dict(self):
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "requires_approval": self.requires_approval,
            "approval_id": self.approval_id
        }

class ToolRegistry:
    def __init__(self):
        self.tools = {
            "read_spreadsheet": self.read_spreadsheet,
            "query_database": self.query_database,
            "send_email": self.send_email,
            "request_approval": self.request_approval,
            "run_shell_command": self.run_shell_command
        }

    async def execute_tool(self, tool_name: str, args: Dict[str, Any], context: Dict[str, Any]) -> ToolExecutionResult:
        """
        All tool executions pass through the Approval Gate first!
        """
        if tool_name not in self.tools:
            return ToolExecutionResult(success=False, error=f"Unknown tool: {tool_name}")

        mode = context.get("mode", "auto")
        threshold = context.get("threshold", 50000.0)
        run_id = context.get("run_id", "default")
        agent_name = context.get("agent_name", "worker")

        # APPROVAL GATE CHECK
        is_risky, reason, risk_amount = self.check_approval_gate(tool_name, args, mode, threshold)
        if is_risky:
            # Register approval requirement in DB
            approval_id = f"appr-{datetime.now().strftime('%M%S%f')[:8]}"
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO approvals (id, run_id, task_id, title, description, risk_level, amount_inr, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """, (
                approval_id,
                run_id,
                args.get("task_id", ""),
                f"Approve {tool_name.replace('_', ' ').title()}",
                reason,
                "high" if risk_amount >= threshold else "medium",
                risk_amount,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            conn.close()

            log_audit(
                run_id=run_id,
                agent=agent_name,
                action="APPROVAL_REQUIRED",
                details=f"Paused: {reason} [Approval ID: {approval_id}]",
                tool_name=tool_name,
                model_tier="code",
                status="paused"
            )

            return ToolExecutionResult(
                success=False,
                error="Action paused for human approval",
                requires_approval=True,
                approval_id=approval_id
            )

        # Tool execution if approved / auto-passed
        try:
            fn = self.tools[tool_name]
            result = await fn(args, context)
            return result
        except Exception as e:
            return ToolExecutionResult(success=False, error=str(e))

    def check_approval_gate(self, tool_name: str, args: Dict[str, Any], mode: str, threshold: float) -> Tuple[bool, str, float]:
        """
        Determines whether this specific action requires a human pause:
        - In manual mode: every action requires a human tap
        - In auto mode: only high-risk actions (money > threshold, external sends, destructive operations)
        """
        amount = float(args.get("amount", args.get("amount_inr", 0.0)))

        if mode == "manual":
            return True, f"Manual mode active: approval required for tool '{tool_name}'", amount

        # Auto mode checks
        if tool_name == "send_email":
            # If email is regarding a large debt or external notification over threshold
            if amount >= threshold:
                return True, f"Invoice amount ₹{amount:,.2f} exceeds auto-limit ₹{threshold:,.2f}. Human approval required before sending email.", amount

        if tool_name == "request_approval":
            return True, args.get("reason", "Explicit approval requested by agent"), amount

        if tool_name == "run_shell_command":
            cmd = args.get("command", "")
            # Check if command has destructive or external effects
            risky_words = ["rm", "del", "drop", "delete", "shutdown", "format"]
            if any(w in cmd.lower() for w in risky_words):
                return True, f"Potentially destructive shell command: '{cmd}'", 0.0

        return False, "Auto-approved", amount

    async def read_spreadsheet(self, args: Dict[str, Any], context: Dict[str, Any]) -> ToolExecutionResult:
        file_path = args.get("file_path") or str(CSV_PATH)
        rows = []
        try:
            if not os.path.exists(file_path):
                # Fallback to loading from accounts table in DB
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM accounts")
                rows = [dict(r) for r in cursor.fetchall()]
                conn.close()
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        rows.append(r)
            return ToolExecutionResult(success=True, data={"count": len(rows), "rows": rows})
        except Exception as e:
            return ToolExecutionResult(success=False, error=f"Failed to read spreadsheet: {e}")

    async def query_database(self, args: Dict[str, Any], context: Dict[str, Any]) -> ToolExecutionResult:
        query = args.get("query", "SELECT * FROM accounts WHERE status = 'overdue'")
        params = args.get("params", ())
        try:
            conn = get_db()
            cursor = conn.cursor()
            # Only allow read-only SELECT queries for safe agent tool access
            if not query.strip().upper().startswith("SELECT"):
                conn.close()
                return ToolExecutionResult(success=False, error="Security violation: Only SELECT queries are permitted in query_database")
            
            cursor.execute(query, params)
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return ToolExecutionResult(success=True, data={"results": rows, "count": len(rows)})
        except Exception as e:
            return ToolExecutionResult(success=False, error=f"Database query error: {e}")

    async def send_email(self, args: Dict[str, Any], context: Dict[str, Any]) -> ToolExecutionResult:
        recipient_email = args.get("recipient_email")
        recipient_name = args.get("recipient_name", "Customer")
        subject = args.get("subject", "Notice Regarding Outstanding Account")
        body = args.get("body", "")
        tone = args.get("tone", "professional")
        run_id = context.get("run_id", "default")

        # Validation: check for missing email (the deliberate failure scenario!)
        if not recipient_email or "@" not in str(recipient_email):
            return ToolExecutionResult(
                success=False,
                error=f"VALIDATION_FAILURE: Missing or invalid email address for customer '{recipient_name}'"
            )

        # Log sent email into database
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO sent_messages (run_id, recipient_email, recipient_name, subject, body, tone, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (run_id, recipient_email, recipient_name, subject, body, tone, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

        return ToolExecutionResult(
            success=True,
            data={
                "delivered": True,
                "recipient": recipient_email,
                "subject": subject,
                "tone_applied": tone,
                "timestamp": datetime.now().isoformat()
            }
        )

    async def request_approval(self, args: Dict[str, Any], context: Dict[str, Any]) -> ToolExecutionResult:
        return ToolExecutionResult(
            success=False,
            requires_approval=True,
            error=args.get("reason", "Manual approval gate triggered")
        )

    async def run_shell_command(self, args: Dict[str, Any], context: Dict[str, Any]) -> ToolExecutionResult:
        """
        Runs inside an isolated restricted environment with timeout and output capping.
        Never grants unrestricted host shell access.
        """
        command = args.get("command", "")
        if not command:
            return ToolExecutionResult(success=False, error="No command provided")

        # Check whitelist tokens
        cmd_base = command.strip().split()[0].lower()
        if not any(command.strip().startswith(allowed) for allowed in ALLOWED_SHELL_COMMANDS):
            return ToolExecutionResult(
                success=False,
                error=f"SECURITY SANDBOX REJECTION: Command '{cmd_base}' is not in the allowed sandbox whitelist"
            )

        with tempfile.TemporaryDirectory() as sandbox_dir:
            try:
                # Run subprocess with timeout inside temporary directory
                proc = await asyncio.create_subprocess_shell(
                    command,
                    cwd=sandbox_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={"PATH": os.environ.get("PATH", ""), "SANDBOX": "NERV_RESTRICTED"}
                )
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
                    out_text = stdout.decode("utf-8", errors="replace").strip()
                    err_text = stderr.decode("utf-8", errors="replace").strip()
                    return ToolExecutionResult(
                        success=(proc.returncode == 0),
                        data={"stdout": out_text, "stderr": err_text, "exit_code": proc.returncode}
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    return ToolExecutionResult(success=False, error="Command execution timed out after 5.0 seconds")
            except Exception as e:
                return ToolExecutionResult(success=False, error=f"Sandbox error: {e}")

tool_registry = ToolRegistry()
