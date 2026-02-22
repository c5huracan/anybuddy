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
python anybuddy_discord.py
```

### Telegram

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Set env vars and run:
```bash
export ANYBUDDY_TELEGRAM_TOKEN=your-token
python anybuddy_telegram.py
```

### Choosing a Brain

AnyBuddy supports two AI backends:

- **SolveitBrain** (default) — uses a [SolveIt](https://solve.it.com) dialog as the AI backend. Gets web search, tool calling, and dialog memory for free. Requires a running solveit instance.
- **ClaudetteBrain** — uses [claudette](https://github.com/AnswerDotAI/claudette) to call Claude directly. Self-hosted, no solveit dependency. Includes web search via Anthropic's built-in tool.

Switch via CLI flag or env var:
```bash
python anybuddy_telegram.py --brain claudette
python anybuddy_discord.py --brain solveit
# or
export ANYBUDDY_BRAIN=claudette
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANYBUDDY_DISCORD_TOKEN` | Discord | — | Discord bot token |
| `ANYBUDDY_TELEGRAM_TOKEN` | Telegram | — | Telegram bot token |
| `ANYBUDDY_CHANNEL` | Discord | — | Discord channel ID |
| `ANYBUDDY_BRAIN` | No | `solveit` | Brain backend (`solveit` or `claudette`) |
| `ANYBUDDY_DIALOG` | No | `anybuddy-discord` | SolveIt dialog name |
| `ANYBUDDY_TZ` | No | `US/Central` | Timezone |
| `ANYBUDDY_VERBOSE` | No | `false` | Debug logging (`1`/`true`) |

### CLI Flags

All env vars can be overridden via CLI flags (flags take priority):

```bash
python anybuddy_telegram.py --brain claudette --verbose true --tz Europe/Amsterdam
```

## Architecture

Three clean layers:

- **Adapter** — thin platform wrapper (Discord, Telegram, WhatsApp...)
- **Brain** — AI backend (SolveIt dialog, claudette, any LLM)
- **Runner** — wires adapter events to brain

~90 lines per adapter. No framework. No magic.

## Roadmap

- [x] Discord adapter
- [x] Telegram adapter
- [x] ClaudetteBrain (self-hosted mode)
- [ ] WhatsApp adapter (neonize)
- [ ] Image/attachment handling
- [ ] Message batching

## Origin

Born from [FamilyBuddy](https://share.solve.it.com/d/0083d6c75ceaa87d05a6d7590a357aa4) and [SecureClaw](https://github.com/c5huracan/secureclaw).
