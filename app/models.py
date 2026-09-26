from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class GoalRequest(BaseModel):
    goal: str = Field(..., example="Chase overdue invoices over ₹10,000")
    mode: Optional[str] = Field("auto", example="auto") # "manual" or "auto"
    threshold: Optional[float] = Field(50000.0, example=50000.0)

class ApprovalDecision(BaseModel):
    approval_id: str
    decision: str = Field(..., example="approve") # "approve" or "reject"
    channel: Optional[str] = Field("web", example="web") # "web" or "telegram"
    reason: Optional[str] = None

class ModeToggleRequest(BaseModel):
    mode: str = Field(..., example="auto") # "manual" or "auto"

class AgentStatus(BaseModel):
    name: str
    role: str
    state: str # "idle", "perceiving", "planning", "working", "waiting_approval", "error_recovered", "done"
    current_task: Optional[str] = None
    detail: Optional[str] = None

class SystemState(BaseModel):
    mode: str
    approval_threshold: float
    active_run_id: Optional[str]
    agents: Dict[str, AgentStatus]
    pending_approvals_count: int
    total_tokens_saved: int
