"""
================================================================================
KAEKAE CLUSTER LAUNCHER (1-CLICK MULTI-TERMINAL LAUNCHER)
================================================================================
Launches all 3 specialized terminals side-by-side:
- Terminal 1: python chat_worker.py (OCR & Text Chat Engine)
- Terminal 2: python audio_worker.py (Whisper STT, Mic & Talk Controller)
- Terminal 3: python master_dashboard.py (HUD & Control Center)
================================================================================
"""

import os
import sys
import subprocess
import time

def main():
    print("=" * 76)
    print("  LAUNCHING KAEKAE MULTI-TERMINAL CLUSTER")
    print("=" * 76)
    print("  Terminal 1 -> Chat Worker (Text & Moderation Engine)")
    print("  Terminal 2 -> Audio Worker (Microphone & Talk Controller)")
    print("  Terminal 3 -> Master Dashboard (Live HUD & Controls)")
    print("=" * 76 + "\n")

    py_exe = sys.executable

    if sys.platform == "win32":
        # Launch Terminal 1 (Chat Worker)
        print("[1/3] Spawning Terminal 1: Chat Worker...")
        subprocess.Popen(
            f'start "KaeKae Chat Worker [Term 1]" cmd /k ""{py_exe}" chat_worker.py"',
            shell=True
        )
        time.sleep(1.2)

        # Launch Terminal 2 (Audio Worker)
        print("[2/3] Spawning Terminal 2: Audio Worker...")
        subprocess.Popen(
            f'start "KaeKae Audio Worker [Term 2]" cmd /k ""{py_exe}" audio_worker.py"',
            shell=True
        )
        time.sleep(1.2)

        # Launch Terminal 3 (Master Dashboard)
        print("[3/3] Spawning Terminal 3: Master Dashboard...")
        subprocess.Popen(
            f'start "KaeKae Master Dashboard [Term 3]" cmd /k ""{py_exe}" master_dashboard.py"',
            shell=True
        )

        print("\n[SUCCESS] All 3 terminals launched successfully!")
        print("You can position them across your monitors for full visibility.\n")
    else:
        print("[INFO] Non-Windows environment detected. Launching processes...")
        subprocess.Popen([py_exe, "chat_worker.py"])
        subprocess.Popen([py_exe, "audio_worker.py"])
        subprocess.call([py_exe, "master_dashboard.py"])

if __name__ == "__main__":
    main()
