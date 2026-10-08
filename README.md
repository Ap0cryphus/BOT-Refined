# Camfrog UI-Automation Bot

This build uses Windows UI Automation (`pywinauto` with the `uia` backend) as
its only source of room text. It does not invoke OCR, DXCam, screenshots,
template matching, OpenCV, or Tesseract.

Use the project environment, which already contains the required Windows UIA
packages:

```powershell
.venv\Scripts\python.exe test_bot.py
.venv\Scripts\python.exe camfrog_boy.py --dry-run --locations
.venv\Scripts\python.exe camfrog_boy.py --dry-run
```

Remove `--dry-run` only after confirming that Camfrog exposes the chat input
through UI Automation; that mode reads and logs room text but prints replies
instead of sending them.

`camfrog_boy.py` is the requested compatibility entry point. The implementation
lives in `camfrog_bot.py`; `ui_automation.py` owns all live UIA discovery and
interaction.

The bot records UIA chat messages, join/quit notices, roster names, and strict
moderation notices in `data/camfrog_bot.db`. `!suppress` moves a user's stored
data to `data/suppressed/` and excludes them from ordinary recall; that user can
restore it with `!unsuppress`.

Native moderation commands stay disabled by default. Add trusted bot-account
operators to `MODERATION_ALLOWED_SENDERS` in `config.py` before `!unban`,
`!unpunish`, `!unblockmic`, `!topic`, or `!watchlist` may emit a slash command.
