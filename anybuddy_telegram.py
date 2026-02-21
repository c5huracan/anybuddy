import os, re, asyncio
import datetime as dt
from zoneinfo import ZoneInfo
from fastcore.utils import store_attr
from dialoghelper import find_msgs, add_msg, add_prompt, update_msg, dh_settings
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

DNAME = os.environ.get('ANYBUDDY_DIALOG', 'anybuddy-discord')
TOKEN = os.environ['ANYBUDDY_TELEGRAM_TOKEN']
TZ = os.environ.get('ANYBUDDY_TZ', 'US/Central')
VERBOSE = os.environ.get('ANYBUDDY_VERBOSE', '').lower() in ('1', 'true')

dh_settings['dname'] = DNAME
__dialog_name = DNAME

class Brain:
    "Base class for AI backends"
    async def send_prompt(self, text): raise NotImplementedError
    async def ensure_section(self): raise NotImplementedError
    async def hide_section(self, header): raise NotImplementedError

class SolveitBrain(Brain):
    "Solveit dialoghelper backend"
    def __init__(self, dname, tz=TZ):
        store_attr()
        self._tz = ZoneInfo(tz)

    async def send_prompt(self, text): return await add_prompt(text, dname=self.dname, placement='at_end')

    async def hide_section(self, header):
        "Skip and collapse a section"
        msgs = await find_msgs(header_section=header, dname=self.dname)
        for m in msgs: await update_msg(id=m['id'], skipped=1, dname=self.dname)
        if msgs: await update_msg(id=msgs[0]['id'], heading_collapsed=1, dname=self.dname)

    async def ensure_section(self):
        "Create today's section, hide yesterday's"
        today = dt.datetime.now(self._tz).date().strftime('%a %d %b %Y')
        if (existing := await find_msgs(re_pattern=f"^## {today}$", dname=self.dname)): return existing[0]['id']
        for sec in await find_msgs(re_pattern=r"^## [A-Z][a-z]{2} \d{2} [A-Z][a-z]{2} \d{4}$", dname=self.dname):
            await self.hide_section(sec['content'])
        return await add_msg(f"## {today}", placement='at_end', dname=self.dname)

class TelegramAdapter:
    "Telegram messaging adapter"
    def __init__(self, token):
        store_attr()
        self.app = ApplicationBuilder().token(token).build()

    @staticmethod
    def format_output(output):
        output = re.sub(r"<details class='tool-usage-details'>\s*<summary>(.*?)</summary>.*?</details>", lambda m: f"🔧`{m.group(1)}`", output, flags=re.DOTALL)
        return re.sub(r'\n{3,}', '\n\n', output).strip('\n')

def log(*args):
    if VERBOSE: print(*args)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    brain = context.bot_data['brain']
    adapter = context.bot_data['adapter']
    name = update.effective_user.first_name
    text = update.message.text
    log(f"📨 {name}: {text}")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    try:
        await brain.ensure_section()
        prompt = f'<{name}>{text}</{name}>'
        output = await brain.send_prompt(prompt)
        log(f"💬 Response: {output[:200] if output else 'EMPTY'}")
        if output:
            formatted = adapter.format_output(output)
            while formatted:
                await update.message.reply_text(formatted[:4096])
                formatted = formatted[4096:]
    except Exception as e: await update.message.reply_text(f"🚨 Error:\n{type(e).__name__}: {e}")

if __name__ == '__main__':
    adapter = TelegramAdapter(TOKEN)
    brain = SolveitBrain(DNAME)
    adapter.app.bot_data['brain'] = brain
    adapter.app.bot_data['adapter'] = adapter
    adapter.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Starting AnyBuddy on Telegram...")
    adapter.app.run_polling()
