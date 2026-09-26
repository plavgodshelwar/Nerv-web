import os
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger("nerv.telegram")

class TelegramNervBot:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.subscribed_chat_ids = set()
        self.app = None
        self.is_running = False

    async def start(self):
        if not self.token or self.token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
            logger.warning("No valid TELEGRAM_BOT_TOKEN found. Telegram live polling inactive; web simulator fully active.")
            return

        try:
            from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
            from telegram.ext import (
                ApplicationBuilder,
                CommandHandler,
                CallbackQueryHandler,
                MessageHandler,
                filters,
                ContextTypes
            )

            self.app = ApplicationBuilder().token(self.token).build()

            # Command Handlers
            self.app.add_handler(CommandHandler("start", self.cmd_start))
            self.app.add_handler(CommandHandler("help", self.cmd_help))
            self.app.add_handler(CommandHandler("status", self.cmd_status))
            self.app.add_handler(CommandHandler("mode", self.cmd_mode))
            self.app.add_handler(CommandHandler("goal", self.cmd_goal))
            self.app.add_handler(CommandHandler("approvals", self.cmd_approvals))
            self.app.add_handler(CommandHandler("audit", self.cmd_audit))
            self.app.add_handler(CallbackQueryHandler(self.handle_callback))
            self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

            logger.info("Initializing Telegram bot (@nervvbot)...")
            await self.app.initialize()
            await self.app.start()
            await self.app.updater.start_polling()
            self.is_running = True
            logger.info("Telegram bot (@nervvbot) is running and polling for updates!")

        except Exception as e:
            logger.error(f"Failed to start live Telegram bot: {e}")

    async def stop(self):
        if self.app and self.is_running:
            try:
                await self.app.updater.stop()
                await self.app.stop()
                await self.app.shutdown()
                self.is_running = False
            except Exception as e:
                logger.error(f"Error stopping Telegram bot: {e}")

    # ---------------- Telegram Commands ----------------
    async def cmd_start(self, update, context):
        chat_id = update.effective_chat.id
        self.subscribed_chat_ids.add(chat_id)
        msg = (
            "🏢 *NERV Autonomous Office Bot* (`@nervvbot`)\n\n"
            "Welcome to your pocket command center. I mirror the web dashboard 1:1.\n\n"
            "⚙️ *Available Commands:*\n"
            "• `/goal <instruction>` — Dispatch a business goal to Manager Agent\n"
            "• `/status` — View current office state & agent statuses\n"
            "• `/mode <auto|manual>` — Toggle approval gate sensitivity\n"
            "• `/approvals` — Inspect & tap pending approval requests\n"
            "• `/audit` — Retrieve latest timestamped audit log entries\n\n"
            "_Whenever an agent hits a high-risk tool call (e.g. invoices > ₹50,000), "
            "you'll receive instant approval buttons right here._"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def cmd_help(self, update, context):
        await self.cmd_start(update, context)

    async def cmd_status(self, update, context):
        state = self.orchestrator.get_system_state()
        agents = state["agents"]
        status_lines = [
            f"• *{a['name']}*: `{a['state'].upper()}`" + (f" ({a['detail']})" if a.get('detail') else "")
            for a in agents.values()
        ]
        msg = (
            f"📊 *NERV Office Status*\n"
            f"Mode: `{state['mode'].upper()}` | Threshold: `₹{state['threshold']:,.0f}`\n"
            f"Pending Approvals: `{state['pending_approvals_count']}`\n"
            f"Tokens Saved by Jev: `~{state['total_tokens_saved']}`\n\n"
            f"*Agents:*\n" + "\n".join(status_lines)
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def cmd_mode(self, update, context):
        args = context.args
        if not args or args[0].lower() not in ["manual", "auto"]:
            await update.message.reply_text("Usage: `/mode auto` or `/mode manual`", parse_mode="Markdown")
            return
        new_mode = args[0].lower()
        self.orchestrator.set_mode(new_mode)
        await update.message.reply_text(f"⚙️ System mode switched to *{new_mode.upper()}* mode.", parse_mode="Markdown")

    async def cmd_goal(self, update, context):
        goal_text = " ".join(context.args).strip()
        if not goal_text:
            goal_text = "Chase overdue invoices over ₹10,000"

        await update.message.reply_text(
            f"🚀 *Goal received*: \"{goal_text}\"\n"
            f"Routing to Manager Agent & Jev Dispatcher...",
            parse_mode="Markdown"
        )

        # Run asynchronously so bot doesn't block
        asyncio.create_task(self.orchestrator.start_goal(goal_text))

    async def cmd_approvals(self, update, context):
        from app.database import get_pending_approvals
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        approvals = get_pending_approvals()
        if not approvals:
            await update.message.reply_text("✅ No pending approvals. All agents are running clear.")
            return

        for app in approvals:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"appr:{app['id']}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"rejc:{app['id']}")
                ]
            ]
            markup = InlineKeyboardMarkup(keyboard)
            text = (
                f"⚠️ *Approval Request* [{app['id']}]\n"
                f"*Action*: {app['title']}\n"
                f"*Amount*: ₹{app['amount_inr']:,.2f}\n"
                f"*Reason*: {app['description']}"
            )
            await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")

    async def cmd_audit(self, update, context):
        from app.database import get_audit_trail
        logs = get_audit_trail(limit=5)
        if not logs:
            await update.message.reply_text("No audit log records yet.")
            return

        lines = []
        for l in logs:
            lines.append(f"• `{l['timestamp'][11:]}` *{l['agent']}* — {l['action']}: {l['details'][:80]}...")

        msg = "📋 *Recent Audit Trail Records:*\n\n" + "\n".join(lines)
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def handle_callback(self, update, context):
        query = update.callback_query
        await query.answer()
        data = query.data

        if ":" not in data:
            return

        action, approval_id = data.split(":", 1)
        decision = "approve" if action == "appr" else "reject"

        res = await self.orchestrator.decide_approval(approval_id, decision, channel="telegram")
        if res.get("success"):
            icon = "✅" if decision == "approve" else "❌"
            await query.edit_message_text(
                f"{icon} *Action {decision.upper()}D via Telegram*\n"
                f"Approval ID: `{approval_id}`\n"
                f"The Manager Agent and worker pipeline are resuming.",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(f"⚠️ Error: {res.get('error')}")

    async def handle_message(self, update, context):
        text = update.message.text.strip()
        # Default text received without command treated as goal
        await update.message.reply_text(f"🎯 Setting new goal: \"{text}\"")
        asyncio.create_task(self.orchestrator.start_goal(text))

    # ---------------- Simulated Telegram Dispatcher ----------------
    # Allows the interactive Telegram widget in the web dashboard to exercise the exact same bot logic!
    async def process_simulated_command(self, action: str, text: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes Telegram bot command logic and returns responses for the web UI widget.
        """
        if action == "ask":
            goal = text or "Chase overdue invoices over ₹10,000"
            asyncio.create_task(self.orchestrator.start_goal(goal))
            return {
                "reply": f"⌨️ Goal forwarded to Manager Agent: \"{goal}\"",
                "type": "goal_started"
            }
        elif action == "status":
            state = self.orchestrator.get_system_state()
            active_agents = [k for k, v in state["agents"].items() if v["state"] != "idle"]
            return {
                "reply": f"📊 Manager: {len(active_agents)} active agents. {state['pending_approvals_count']} approvals pending. Total tokens saved: ~{state['total_tokens_saved']}.",
                "state": state
            }
        elif action == "approve":
            from app.database import get_pending_approvals
            pending = get_pending_approvals()
            if not pending:
                return {"reply": "ℹ️ No pending approvals waiting."}
            target = pending[0]
            await self.orchestrator.decide_approval(target["id"], "approve", channel="telegram_sim")
            return {
                "reply": f"✅ Approved [{target['id']}]: {target['title']} (₹{target['amount_inr']:,.2f}). Workflow resuming.",
                "approval_id": target["id"]
            }
        elif action == "reject":
            from app.database import get_pending_approvals
            pending = get_pending_approvals()
            if not pending:
                return {"reply": "ℹ️ No pending approvals waiting."}
            target = pending[0]
            await self.orchestrator.decide_approval(target["id"], "reject", channel="telegram_sim")
            return {
                "reply": f"❌ Rejected [{target['id']}]: Flagged for manual review.",
                "approval_id": target["id"]
            }
        elif action == "log" or action == "audit":
            from app.database import get_audit_trail
            logs = get_audit_trail(limit=3)
            return {
                "reply": f"📋 Last {len(logs)} audit steps sent to chat.",
                "logs": logs
            }
        return {"reply": "Command processed."}
