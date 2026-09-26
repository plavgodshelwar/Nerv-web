import os
import sys
import uvicorn
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Load local environment variables if available
load_dotenv()

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🏢 NERV Multi-Agent Digital Office & Telegram Bot")
    print("="*60)
    print("• Web Dashboard:  http://localhost:8000")
    print("• WebSocket Bus:  ws://localhost:8000/ws")
    print("• API Docs:       http://localhost:8000/docs")
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if telegram_token and telegram_token != "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("• Telegram Bot:   CONNECTED (@nervvbot polling active)")
    else:
        print("• Telegram Bot:   SIMULATOR MODE (Set TELEGRAM_BOT_TOKEN to connect live)")
    print("="*60 + "\n")

    uvicorn.run("app.server:app", host="0.0.0.0", port=8000, reload=True)
