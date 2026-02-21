# AnyBuddy 🤙

**Your AI, your chat app, your rules.**

AnyBuddy connects your favorite messaging app to an AI backend — your own personal assistant, running on your own infra, with your own tools.

## Quick Start

### Discord

1. Create a bot at [discord.com/developers](https://discord.com/developers/applications)
2. Enable **Message Content Intent** in Bot settings
3. Invite bot to your server (OAuth2 → bot scope → Send Messages, Read Message History, View Channels)
4. Set env vars and run:
```bash
export ANYBUDDY_DISCORD_TOKEN=your-token
export ANYBUDDY_CHANNEL=your-channel-id
export ANYBUDDY_DIALOG=anybuddy-discord
python anybuddy_discord.py
```

### Telegram

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Set env vars and run:
```bash
export ANYBUDDY_TELEGRAM_TOKEN=your-token
export ANYBUDDY_DIALOG=anybuddy-discord
python anybuddy_telegram.py
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANYBUDDY_DISCORD_TOKEN` | Discord | — | Discord bot token |
| `ANYBUDDY_TELEGRAM_TOKEN` | Telegram | — | Telegram bot token |
| `ANYBUDDY_CHANNEL` | Discord | — | Discord channel ID |
| `ANYBUDDY_DIALOG` | No | `anybuddy-discord` | SolveIt dialog name |
| `ANYBUDDY_TZ` | No | `US/Central` | Timezone |
| `ANYBUDDY_VERBOSE` | No | `false` | Debug logging (`1`/`true`) |

## Architecture

Three clean layers:

- **Adapter** — thin platform wrapper (Discord, Telegram, WhatsApp...)
- **Brain** — AI backend (SolveIt dialog, claudette, any LLM)
- **Runner** — wires adapter events to brain

~90 lines per adapter. No framework. No magic.

## Roadmap

- [x] Discord adapter
- [x] Telegram adapter
- [ ] WhatsApp adapter (neonize)
- [ ] ClaudetteBrain (self-hosted mode)
- [ ] Image/attachment handling
- [ ] Message batching

## Origin

Born from [FamilyBuddy](https://share.solve.it.com/d/0083d6c75ceaa87d05a6d7590a357aa4) and [SecureClaw](https://github.com/c5huracan/secureclaw).
