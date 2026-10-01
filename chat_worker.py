"""
================================================================================
KAEKAE CHAT WORKER (TERMINAL 1: TEXT & CHAT ENGINE)
================================================================================
Dedicated strictly to chat operations:
- OCR & CEF direct chat message capture
- Room moderation & user command processing (!info, !who, !seen, !profile, !diss)
- Creator commands (!say, !diss, !chill)
- When speech is requested, pushes cleanly into pending_speech_queue.json for Terminal 2!
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
print("  Status      : Starting OCR & Chat Monitor...")
print("  Integration : Pushes !say and voice requests to pending_speech_queue.json")
print("  Audio Worker: Terminal 2 handles physical mic lock & virtual cable audio")
print("=" * 76 + "\n")

# Re-use core chat engine from kaekae_bot with audio recording disabled in this terminal
import kaekae_bot

# In chat worker, disable microphone recording so sounddevice doesn't touch this process
kaekae_bot.AUDIO_RECORD_ENABLED = False

if __name__ == "__main__":
    try:
        print("[CHAT WORKER] Launching dedicated chat loop...")
        kaekae_bot.main()
    except KeyboardInterrupt:
        print("\n[CHAT WORKER] Stopped by user.")
