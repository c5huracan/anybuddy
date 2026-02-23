# AnyBuddy Setup Guide

## Quick Setup

Run the interactive setup script:

```bash
python anybuddy_setup.py
```

It walks you through platform selection, token creation, and dialog setup.

## Manual Setup

### 1. Create a bot

**Discord:** Go to [discord.com/developers](https://discord.com/developers/applications) → New Application → Bot tab → copy token → enable **Message Content Intent** → OAuth2 URL Generator → check `bot` scope + Send Messages, Read Message History, View Channels → open URL to invite bot.

**Telegram:** Message [@BotFather](https://t.me/BotFather) → `/newbot` → follow prompts → copy token.

### 2. Set env vars

```bash
# Discord
export ANYBUDDY_DISCORD_TOKEN=your-token
export ANYBUDDY_CHANNEL=your-channel-id

# Telegram
export ANYBUDDY_TELEGRAM_TOKEN=your-token
```

### 3. Run

```bash
python anybuddy_discord.py
python anybuddy_telegram.py
```

For self-hosted mode (no solveit needed):

```bash
python anybuddy_discord.py --brain claudette
python anybuddy_telegram.py --brain claudette
```

### 4. Customize

Add tools and personality via a CRAFT file in your dialog's folder. The AI handles routing — you just type naturally.
