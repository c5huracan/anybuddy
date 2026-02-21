import os, re, asyncio, discord
import datetime as dt
from zoneinfo import ZoneInfo
from fastcore.utils import store_attr
from dialoghelper import find_msgs, add_msg, add_prompt, update_msg, dh_settings

DNAME = os.environ.get('ANYBUDDY_DIALOG', 'anybuddy-discord')
TOKEN = os.environ['ANYBUDDY_DISCORD_TOKEN']
CHANNEL = int(os.environ.get('ANYBUDDY_CHANNEL', '1440419500494422069'))
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

class DiscordAdapter:
    "Discord messaging adapter"
    def __init__(self, token, channel_id, allowed_users=None):
        store_attr()
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self._channel = None

    async def send(self, text):
        "Send text, splitting at 2000 char boundary if needed"
        while text:
            await self._channel.send(text[:2000])
            text = text[2000:]

    @staticmethod
    def format_output(output):
        output = re.sub(r"<details class='tool-usage-details'>\s*<summary>(.*?)</summary>.*?</details>", lambda m: f"🔧`{m.group(1)}`", output, flags=re.DOTALL)
        return re.sub(r'\n{3,}', '\n\n', output).strip('\n')

def log(*args):
    if VERBOSE: print(*args)

async def run_discord_bot(adapter, brain):
    "Wire Discord adapter events to brain and start"
    @adapter.client.event
    async def on_ready(): print(f"✅ Connected as {adapter.client.user}")

    @adapter.client.event
    async def on_message(message):
        if message.author == adapter.client.user: return
        if message.channel.id != adapter.channel_id: return
        if adapter.allowed_users and str(message.author.id) not in adapter.allowed_users: return
        adapter._channel = message.channel
        log(f"📨 {message.author.display_name}: {message.content}")
        async with message.channel.typing():
            try:
                await brain.ensure_section()
                name = message.author.display_name
                text = f'<{name}>{message.content}</{name}>'
                output = await brain.send_prompt(text)
                log(f"💬 Response: {output[:200] if output else 'EMPTY'}")
                if output: await adapter.send(adapter.format_output(output))
            except Exception as e: await adapter.send(f"🚨 Error:\n{type(e).__name__}: {e}")

    await adapter.client.start(adapter.token)

if __name__ == '__main__':
    da = DiscordAdapter(TOKEN, channel_id=CHANNEL)
    brain = SolveitBrain(DNAME)
    asyncio.run(run_discord_bot(da, brain))
