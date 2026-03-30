# OpenClaw Integration

OmniFeed can run as an [OpenClaw](https://github.com/openclaw/openclaw) skill for enhanced personalization.

## What it adds

- **Auto profile from context**: Mines `USER.md`, `MEMORY.md`, and daily notes for interest signals
- **Scheduled fetches**: Set up cron jobs to keep your feed fresh
- **Chat integration**: Push daily digests to Telegram, Discord, etc.
- **Conversational triggers**: "What's new?" / "帮我看看今天有什么" triggers instant fetch

## Setup

1. Copy the `SKILL.md` to your OpenClaw skills directory:
   ```bash
   cp -r integrations/openclaw ~/.openclaw/skills/omnifeed
   ```

2. OmniFeed should already be installed (`pip install omnifeed`)

3. Tell your agent: "Set up omnifeed daily digest" — it will create cron jobs automatically.

## Skill File

See `SKILL.md` in this directory for the full skill definition.
