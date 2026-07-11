"""Chat with the bot in your terminal — no Telegram needed. Run: python cli.py"""
from agents import orchestrator

print("SahaayakAI CLI — type 'quit' to exit. Try: /start")
while True:
    try:
        text = input("\nseller> ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if text.lower() in ("quit", "exit"):
        break
    if not text:
        continue
    print("\nbot>", orchestrator.handle_message("cli", text))
