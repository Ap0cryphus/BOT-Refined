"""
================================================================================
KAEKAE CHAT WORKER (TERMINAL 1: TEXT & CHAT ENGINE)
================================================================================
Dedicated strictly to chat operations:
- Captures chat straight from the CEF/Chromium DOM (no OCR, no screenshots)
- Claims every captured message once (durable dedupe, survives restarts)
- Runs all room moderation + user commands (!info, !who, !diss, ...)
- Creator commands (!say, !diss, !chill) - !say is queued for Terminal 2
- Consumes chat_outbox.jsonl so Terminal 2/3 speak through this one writer
================================================================================
"""

import os
import sys
import time
import json
import re

# Set terminal title
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.kernel32.SetConsoleTitleW("KaeKae Chat Engine [Terminal 1 - Text & Moderation]")
    except Exception:
        pass

print("=" * 76)
print("  KAEKAE CHAT WORKER (TERMINAL 1: TEXT & CHAT ENGINE)")
print("=" * 76)
print("  Status      : Starting CEF chat monitor (no OCR)...")
print("  Chat writes : DIRECT (this terminal types into the Camfrog chat box)")
print("  Audio Worker: Terminal 2 handles mic capture, STT and the talk button")
print("=" * 76 + "\n")

# Re-use the core chat engine from kaekae_bot, with microphone recording OFF in
# this process (Terminal 2 owns the audio device) and chat writes ON (we are the
# single chat writer).
import kaekae_bot

kaekae_bot.AUDIO_RECORD_ENABLED = False
kaekae_bot.CHAT_SEND_MODE = "direct"

if __name__ == "__main__":
    try:
        print("[CHAT WORKER] Launching dedicated chat loop...")
        kaekae_bot.main()
    except KeyboardInterrupt:
        print("\n[CHAT WORKER] Stopped by user.")
