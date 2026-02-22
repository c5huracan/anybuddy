import os, asyncio, discord
from anybuddy import get_brain, format_output, log
from fastcore.utils import store_attr

class DiscordAdapter:
    "Discord messaging adapter"
    def __init__(self, token, channel_id, allowed_users=None):
        store_attr()
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self._channel = None

    async def send(self, text):
        while text:
            await self._channel.send(text[:2000])
            text = text[2000:]

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
                if output: await adapter.send(format_output(output))
            except Exception as e: await adapter.send(f"🚨 Error:\n{type(e).__name__}: {e}")

    await adapter.client.start(adapter.token)

if __name__ == '__main__':
    channel = int(os.environ.get('ANYBUDDY_CHANNEL', '1440419500494422069'))
    da = DiscordAdapter(os.environ['ANYBUDDY_DISCORD_TOKEN'], channel_id=channel)
    asyncio.run(run_discord_bot(da, get_brain()))
