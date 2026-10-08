# Camfrog UI-Automation Bot Console (Web Runtime)

This web application ports the Windows UI-Automation (`pywinauto` / `uia`) Camfrog Bot, SQLite persistence layer, non-queryable suppression vault, and multi-room coordinate processor to a Node.js + React + TypeScript runtime running on port 3000.

## Core Features Ported

- **Live UIA Event Stream & Command Dispatcher (`src/lib/camfrogBot.ts`)**:
  - Full support for documented room triggers: `!chat`, `!chatoff`, `!shutup`, `!transcribe`, `!transcribed`, `!suppress`, `!unsuppress`, `!who is <user>`, `!info on <user>`, `!grabs [user] [5m|30m|1h|24h|72h]`, `!idk <question>`, `!diss <target>`, `!say`, `!happy`, `!sad`, `!mad`, `!triggers`, and `-` pagination.
  - Strict moderation notice parser (`detectModeration`) that logs room actions (`kicked`, `banned`, `unbanned`, `blocked`, `unblocked`, `punished`, `unpunished`) and answers `who <action> <target>?` while rejecting conversational prose.
  - Native operator slash-command gate (`MODERATION_ALLOWED_SENDERS`) for `!unpunish`, `!unblockmic`, `!unban`, `!topic`, and `!watchlist`.
- **SQLite Store & Suppression Vault**:
  - Tracks `bot_users`, `bot_messages`, `presence_events`, `moderation_events`, and `mic_grabs`.
  - `!suppress` moves a user's profile, messages, and mic grabs into the isolated suppression vault (`data/suppressed/<user>.json`) and excludes them from queries until that user issues `!unsuppress`.
- **UIA Control Tree & Multi-Room Tab Coordinate Inspector**:
  - Simulates the Camfrog CEF/UIA accessibility node hierarchy, filtering UI chrome (`GIFTUsers2`, clock timestamps, and panel labels) via `cleanUsername`.
  - Interactive coordinate hit-testing and tab switching for `Room List`, `Players__Lounge`, and `Drama_Central`.
- **Offline Unit Test Suite**:
  - Built-in runner executing the 4 verification tests from `test_bot.py`.

## Development

```bash
npm install
npm run dev
```
