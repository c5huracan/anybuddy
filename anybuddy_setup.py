import os, sys, asyncio
from pathlib import Path
from dialoghelper import create_dialog, add_msg, dh_settings

__dialog_name = 'anybuddy'

def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or default

async def setup():
    global __dialog_name
    print("🤙 AnyBuddy Setup\n")
    platform = ask("Platform (discord/telegram)", "discord")
    dname = ask("Dialog name", "anybuddy")
    tz = ask("Timezone", "US/Central")

    if platform == 'discord':
        token = ask("Discord bot token")
        channel = ask("Discord channel ID")
        print(f"\nAdd these env vars to your instance:\n  ANYBUDDY_DISCORD_TOKEN={token}\n  ANYBUDDY_CHANNEL={channel}")
    elif platform == 'telegram':
        token = ask("Telegram bot token (from @BotFather)")
        print(f"\nAdd this env var to your instance:\n  ANYBUDDY_TELEGRAM_TOKEN={token}")
    else:
        print(f"Unknown platform: {platform}"); return

    __dialog_name = dname
    dh_settings['dname'] = dname
    print(f"\nCreating dialog '{dname}'...")
    await create_dialog(dname)
    mid = await add_msg("# AnyBuddy 🤙", msg_type='note', dname=dname, placement='at_end')
    mid = await add_msg("You are AnyBuddy, a friendly and helpful personal AI assistant. Keep responses short and punchy — this is chat, not an essay. Use markdown sparingly. Never be sycophantic. Be real.", msg_type='note', dname=dname, id=mid)
    mid = await add_msg('Messages arrive as `<username>message</username>`. Respond naturally — never echo back the XML tags. Address users by name when helpful.', msg_type='note', dname=dname, id=mid)

    print(f"✅ Dialog '{dname}' created!")
    print(f"\nTo run:")
    print(f"  1. Add env vars above to your solveit instance (or export in terminal)")
    print(f"  2. Open the '{dname}' dialog in solveit (keep it open)")
    print(f"  3. Run: python anybuddy_{platform}.py --dialog {dname} --tz {tz}")
    print(f"\nFor self-hosted mode (no solveit needed):")
    print(f"  python anybuddy_{platform}.py --brain claudette")

if __name__ == '__main__': asyncio.run(setup())
