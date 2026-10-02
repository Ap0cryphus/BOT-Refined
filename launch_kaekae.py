"""
================================================================================
KAEKAE CLUSTER LAUNCHER (1-CLICK MULTI-TERMINAL LAUNCHER)
================================================================================
Launches all 3 specialized terminals side-by-side:
- Terminal 1: python chat_worker.py (CEF chat capture & command engine)
- Terminal 2: python audio_worker.py (Whisper STT, voice & verified talk control)
- Terminal 3: python master_dashboard.py (HUD + silent command console)
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
        # CREATE_NEW_CONSOLE instead of `start "title" cmd /k "..."`.
        # The shell form depends on nested quote balancing and silently failed
        # to spawn Terminal 2 while T1/T3 came up fine, so the failure looked
        # like "T2 closes on its own". Passing an argv list to Popen removes
        # the shell from the path entirely.
        flag = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        workers = [
            ("Terminal 1", "chat_worker.py", "Chat Worker (Text & Moderation Engine)"),
            ("Terminal 2", "audio_worker.py", "Audio Worker (Microphone & Talk Controller)"),
            ("Terminal 3", "master_dashboard.py", "Master Dashboard (Live HUD & Controls)"),
        ]
        started = []
        for idx, (label, script, desc) in enumerate(workers, 1):
            print(f"[{idx}/3] Spawning {label}: {desc} ...")
            try:
                proc = subprocess.Popen([py_exe, script], creationflags=flag)
                started.append((label, script, proc))
            except Exception as e:
                print(f"    !! FAILED to spawn {label}: {e}")
            time.sleep(1.2)

        # Verify each one is still alive a few seconds later. A worker that
        # dies during import looks identical to one that never started unless
        # it is actually checked, which is what made this confusing to debug.
        time.sleep(4.0)
        print("\n" + "=" * 76)
        bad = 0
        for label, script, proc in started:
            if proc.poll() is None:
                print(f"  {label}: RUNNING  (pid {proc.pid})  {script}")
            else:
                bad += 1
                print(f"  {label}: *** DIED *** exit code {proc.returncode}  {script}")
        print("=" * 76)
        if bad:
            print(f"\n[WARNING] {bad} terminal(s) did not stay up. Run that script")
            print("directly in its own window to see the real error.")
        else:
            print("\n[SUCCESS] All 3 terminals launched and are still running.")
        print("You can position them across your monitors for full visibility.\n")
    else:
        print("[INFO] Non-Windows environment detected. Launching processes...")
        subprocess.Popen([py_exe, "chat_worker.py"])
        subprocess.Popen([py_exe, "audio_worker.py"])
        subprocess.call([py_exe, "master_dashboard.py"])

if __name__ == "__main__":
    main()
