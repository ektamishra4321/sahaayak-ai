"""Telegram bot entry point (P0.1 + P1.4 feedback buttons).

Run:  python main.py
Requires TELEGRAM_BOT_TOKEN and ANTHROPIC_API_KEY in .env
Long polling — no public webhook/server needed for the pilot.
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

import config
from agents import orchestrator, telemetry, vision

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("sahaayak")

FEEDBACK_KB = InlineKeyboardMarkup([[
    InlineKeyboardButton("👍", callback_data="fb:up"),
    InlineKeyboardButton("👎", callback_data="fb:down"),
]])


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    reply = orchestrator.handle_message(str(update.effective_chat.id), "/start")
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


async def on_photo(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """P1.2: seller sends a seller-panel screenshot; we extract the issue as
    text and feed it through the normal pipeline."""
    chat_id = str(update.effective_chat.id)
    try:
        photo = update.message.photo[-1]                 # largest resolution
        tg_file = await photo.get_file()
        image_bytes = bytes(await tg_file.download_as_bytearray())
        extracted = vision.extract_issue(image_bytes)
        if extracted.startswith(vision.IRRELEVANT):
            await update.message.reply_text(
                "Ye screenshot seller panel ka nahi lag raha 🤔 — apne "
                "Supplier Panel / Seller Central ki screen bhejo ya problem "
                "type karke batao.")
            return
        caption = (update.message.caption or "").strip()
        text = f"[Screenshot] {extracted}" + (f"\nSeller adds: {caption}" if caption else "")
        log.info("chat=%s screenshot=%r", chat_id, extracted[:80])
        reply = orchestrator.handle_message(chat_id, text)
    except Exception:
        log.exception("photo handler failed")
        await update.message.reply_text(
            "Screenshot process nahi ho paya 😅 — problem type karke batao.")
        return
    await update.message.reply_text(reply, reply_markup=FEEDBACK_KB)


async def on_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    text = update.message.text or ""
    log.info("chat=%s in=%r", chat_id, text[:80])
    try:
        reply = orchestrator.handle_message(chat_id, text)
    except Exception:
        log.exception("handler failed")
        await update.message.reply_text("Kuch technical problem aa gayi 😅 — thodi der mein dobara try karo.")
        return
    await update.message.reply_text(reply, reply_markup=FEEDBACK_KB)


async def on_feedback(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    verdict = "up" if q.data == "fb:up" else "down"
    telemetry.log_turn(
        chat_id=str(q.message.chat.id),
        text_in=f"[feedback on: {(q.message.text or '')[:120]}]",
        text_out=verdict,
        intent="feedback", language="", marketplace=None, latency_ms=0,
        event=f"feedback_{verdict}",
    )
    await q.answer("Shukriya! 🙏" if verdict == "up" else "Noted — hum isse behtar karenge. 🙏")
    await q.edit_message_reply_markup(reply_markup=None)   # remove buttons after vote


def main() -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env (get one from @BotFather on Telegram)")
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_feedback, pattern=r"^fb:"))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log.info("SahaayakAI polling…")
    app.run_polling()


if __name__ == "__main__":
    main()
