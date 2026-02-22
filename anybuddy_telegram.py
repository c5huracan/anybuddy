import os
from anybuddy import get_brain, format_output, log
from fastcore.utils import store_attr
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

class TelegramAdapter:
    "Telegram messaging adapter"
    def __init__(self, token):
        store_attr()
        self.app = ApplicationBuilder().token(token).build()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    brain = context.bot_data['brain']
    name = update.effective_user.first_name
    text = update.message.text
    log(f"📨 {name}: {text}")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    try:
        await brain.ensure_section()
        output = await brain.send_prompt(f'<{name}>{text}</{name}>')
        log(f"💬 Response: {output[:200] if output else 'EMPTY'}")
        if output:
            formatted = format_output(output)
            while formatted:
                await update.message.reply_text(formatted[:4096])
                formatted = formatted[4096:]
    except Exception as e: await update.message.reply_text(f"🚨 Error:\n{type(e).__name__}: {e}")

if __name__ == '__main__':
    adapter = TelegramAdapter(os.environ['ANYBUDDY_TELEGRAM_TOKEN'])
    brain = get_brain()
    adapter.app.bot_data['brain'] = brain
    adapter.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Starting AnyBuddy on Telegram...")
    adapter.app.run_polling()
