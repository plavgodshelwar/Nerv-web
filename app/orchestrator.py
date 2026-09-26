import asyncio
import json
from typing import Dict, Any, List, Set, Optional
from datetime import datetime
from app.database import get_db, log_audit, init_db, seed_accounts
from app.agents.manager import ManagerAgent
from app.models import AgentStatus, SystemState

class Orchestrator:
    def __init__(self):
        self.active_run_id: Optional[str] = None
        self.mode: str = "auto" # "manual" or "auto"
        self.threshold: float = 50000.0
        self.connected_websockets: Set[Any] = set()
        self.agents_state: Dict[str, AgentStatus] = {
            "manager": AgentStatus(name="Manager Agent", role="Office Orchestrator", state="idle"),
            "jev": AgentStatus(name="JEV Dispatcher", role="Routing & Prompt Cache", state="idle"),
            "data": AgentStatus(name="Data Agent", role="Spreadsheet & DB", state="idle"),
            "finance": AgentStatus(name="Finance Agent", role="Auditor & Risk Gate", state="idle"),
            "comms": AgentStatus(name="Comms Agent", role="Outreach & Tone Engine", state="idle")
        }
        self.manager = ManagerAgent(broadcast_fn=self.broadcast_event)

    async def register_websocket(self, websocket):
        self.connected_websockets.add(websocket)
        # Send current state immediately
        await websocket.send_json({
            "type": "initial_state",
            "state": self.get_system_state()
        })

    def unregister_websocket(self, websocket):
        self.connected_websockets.discard(websocket)

    async def broadcast_event(self, event_type: str, data: Dict[str, Any]):
        # Update agent status cards based on stage
        if event_type == "loop_stage":
            stage = data.get("stage")
            agent_key = data.get("agent", "manager")
            msg = data.get("message", "")

            if stage == "PERCEIVE":
                self.agents_state["manager"].state = "perceiving"
                self.agents_state["manager"].detail = msg
            elif stage == "PLAN":
                self.agents_state["manager"].state = "planning"
                self.agents_state["jev"].state = "working"
                self.agents_state["jev"].detail = "Routing tasks & evaluating token cache"
            elif stage == "ACT":
                if agent_key in self.agents_state:
                    self.agents_state[agent_key].state = "working"
                    self.agents_state[agent_key].detail = msg
            elif stage == "OBSERVE":
                if data.get("has_failure"):
                    self.agents_state["data"].state = "error_recovered"
                    self.agents_state["data"].detail = "Anomaly observed: Missing email flagged"
            elif stage == "RE-PLAN":
                self.agents_state["manager"].state = "re-planning"
                self.agents_state["manager"].detail = msg
            elif stage == "ESCALATE":
                self.agents_state["comms"].state = "working"
                self.agents_state["comms"].detail = msg
            elif stage == "FINISH":
                for a in self.agents_state.values():
                    a.state = "idle"
                    a.detail = "Goal completed"

        payload = {
            "type": event_type,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "data": data,
            "agents": {k: v.dict() for k, v in self.agents_state.items()}
        }

        # Broadcast to all connected clients
        dead_sockets = set()
        for ws in self.connected_websockets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead_sockets.add(ws)

        for ws in dead_sockets:
            self.connected_websockets.discard(ws)

    def get_system_state(self) -> Dict[str, Any]:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM approvals WHERE status = 'pending'")
        pending_count = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(tokens_saved) FROM audit_log")
        row = cursor.fetchone()
        tokens_saved = row[0] if row and row[0] else 0
        conn.close()

        from app.jev_dispatcher import jev_dispatcher
        tokens_saved += jev_dispatcher.total_tokens_saved

        return {
            "mode": self.mode,
            "threshold": self.threshold,
            "active_run_id": self.active_run_id,
            "agents": {k: v.dict() for k, v in self.agents_state.items()},
            "pending_approvals_count": pending_count,
            "total_tokens_saved": tokens_saved
        }

    async def start_goal(self, goal: str, mode: Optional[str] = None, threshold: Optional[float] = None) -> Dict[str, Any]:
        if mode:
            self.mode = mode
        if threshold is not None:
            self.threshold = threshold

        run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.active_run_id = run_id

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO runs (id, goal, mode, status, created_at)
        VALUES (?, ?, ?, 'running', ?)
        """, (run_id, goal, self.mode, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

        await self.broadcast_event("run_started", {
            "run_id": run_id,
            "goal": goal,
            "mode": self.mode,
            "threshold": self.threshold
        })

        # Run the manager agent loop
        result = await self.manager.run_goal(run_id, goal, self.mode, self.threshold)
        return result

    async def decide_approval(self, approval_id: str, decision: str, channel: str = "web", reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Processes human approval from either Web or Telegram!
        Both channels instantly mirror the decision.
        """
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
        approval = cursor.fetchone()

        if not approval:
            conn.close()
            return {"success": False, "error": f"Approval {approval_id} not found"}

        if approval["status"] != "pending":
            conn.close()
            return {"success": False, "error": f"Approval {approval_id} is already {approval['status']}"}

        new_status = "approved" if decision.lower() == "approve" else "rejected"
        decided_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
        UPDATE approvals
        SET status = ?, decided_at = ?, decision_channel = ?
        WHERE id = ?
        """, (new_status, decided_at, channel, approval_id))
        conn.commit()
        conn.close()

        run_id = approval["run_id"]
        log_audit(
            run_id=run_id,
            agent="Human Supervisor",
            action=f"APPROVAL_{new_status.upper()}",
            details=f"Decision: {new_status.upper()} via {channel.upper()} for: {approval['title']} ({approval['description']})",
            model_tier="code",
            status="approved" if new_status == "approved" else "rejected"
        )

        # Notify via WebSocket to sync all Web & Telegram interfaces
        await self.broadcast_event("approval_decided", {
            "approval_id": approval_id,
            "decision": new_status,
            "channel": channel,
            "title": approval["title"],
            "amount": approval["amount_inr"],
            "description": approval["description"]
        })

        return {
            "success": True,
            "approval_id": approval_id,
            "status": new_status,
            "channel": channel
        }

    def set_mode(self, new_mode: str):
        if new_mode in ["manual", "auto"]:
            self.mode = new_mode

orchestrator = Orchestrator()
