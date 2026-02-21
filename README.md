# AnyBuddy 🤙

**Your AI, your chat app, your rules.**

AnyBuddy connects your favorite messaging app to an AI backend — your own personal assistant, running on your own infra, with your own tools.

## Quick Start (Discord + SolveIt)

1. Create a Discord bot at [discord.com/developers](https://discord.com/developers/applications)
2. Enable **Message Content Intent** in Bot settings
3. Invite bot to your server (OAuth2 → bot scope → Send Messages, Read Message History, View Channels)
4. Set env vars:
   - `ANYBUDDY_DISCORD_TOKEN` — your bot token
   - `ANYBUDDY_CHANNEL` — channel ID to listen on
   - `ANYBUDDY_DIALOG` — solveit dialog name (default: `anybuddy-discord`)
   - `ANYBUDDY_TZ` — timezone (default: `US/Central`)
   - `ANYBUDDY_VERBOSE` — set to `1` for debug logging
5. `python anybuddy_discord.py`

## Architecture

Three clean layers:

- **Adapter** — thin platform wrapper (Discord, WhatsApp, Telegram...)
- **Brain** — AI backend (SolveIt dialog, claudette, any LLM)
- **Runner** — wires adapter events to brain

~90 lines. No framework. No magic.

## Roadmap

- [x] Discord adapter
- [ ] WhatsApp adapter (neonize)
- [ ] Telegram adapter
- [ ] ClaudetteBrain (self-hosted mode)
- [ ] Image/attachment handling
- [ ] Message batching

## Origin

Born from [FamilyBuddy](https://share.solve.it.com/d/0083d6c75ceaa87d05a6d7590a357aa4) and [SecureClaw](https://github.com/c5huracan/secureclaw).
