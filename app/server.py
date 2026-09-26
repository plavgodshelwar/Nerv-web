import os
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.database import init_db, seed_accounts, get_audit_trail, get_pending_approvals, get_accounts
from app.orchestrator import orchestrator
from app.models import GoalRequest, ApprovalDecision, ModeToggleRequest
from app.telegram_bot import TelegramNervBot

telegram_bot = TelegramNervBot(orchestrator)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    asyncio.create_task(telegram_bot.start())
    yield
    # Shutdown
    await telegram_bot.stop()

app = FastAPI(title="NERV Multi-Agent Office", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# ----------------- WebSocket Live Stream -----------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await orchestrator.register_websocket(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming ping or messages if needed
    except WebSocketDisconnect:
        orchestrator.unregister_websocket(websocket)

# ----------------- REST API Endpoints -----------------
@app.get("/api/status")
async def get_status():
    return orchestrator.get_system_state()

@app.post("/api/goal")
async def post_goal(req: GoalRequest):
    # Non-blocking run
    asyncio.create_task(orchestrator.start_goal(req.goal, mode=req.mode, threshold=req.threshold))
    return {"success": True, "message": "Goal dispatched to Manager Agent & Jev"}

@app.get("/api/approvals")
async def get_approvals():
    return {"approvals": get_pending_approvals()}

@app.post("/api/approve")
async def post_approve(req: ApprovalDecision):
    res = await orchestrator.decide_approval(req.approval_id, "approve", channel=req.channel, reason=req.reason)
    return res

@app.post("/api/reject")
async def post_reject(req: ApprovalDecision):
    res = await orchestrator.decide_approval(req.approval_id, "reject", channel=req.channel, reason=req.reason)
    return res

@app.post("/api/mode")
async def toggle_mode(req: ModeToggleRequest):
    orchestrator.set_mode(req.mode)
    await orchestrator.broadcast_event("mode_changed", {"mode": req.mode})
    return {"success": True, "mode": orchestrator.mode}

@app.get("/api/audit")
async def get_audit(limit: int = 50):
    return {"audit_trail": get_audit_trail(limit=limit)}

@app.get("/api/accounts")
async def list_accounts():
    return {"accounts": get_accounts()}

@app.post("/api/telegram/sim")
async def telegram_sim(payload: Dict[str, Any]):
    action = payload.get("action", "ask")
    text = payload.get("text", "")
    res = await telegram_bot.process_simulated_command(action, text)
    return res

@app.post("/api/reset")
async def reset_demo():
    seed_accounts(force=True)
    await orchestrator.broadcast_event("system_reset", {"message": "Database and agent states reset"})
    return {"success": True, "message": "Demo state reset successfully"}

# Serve static frontend
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
