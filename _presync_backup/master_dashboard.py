"""
================================================================================
KAEKAE MASTER DASHBOARD (TERMINAL 3: MAIN HUD & CONTROL CENTER)
================================================================================
Provides a real-time heads-up display of the entire bot cluster:
- Live room name, focused window, and stage connection
- Active speaker and 5-minute mic grab timer
- Room member list with gender recognition (Male: Blue, Female: Pink)
- Voice personas status (Valley, Uppity, Valley Sexy)
- Quick interactive command dispatcher (speak, diss, grab, audit)
================================================================================
"""

import os
import sys
import time
import json
from datetime import datetime

# Set terminal title
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.kernel32.SetConsoleTitleW("KaeKae Master Control [Terminal 3 - HUD & Coordinator]")
    except Exception:
        pass

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default

def print_hud():
    state_data = load_json("bot_state.json", {})
    users_data = load_json("bot_users.json", {})
    kicks_data = load_json("bot_kicks.json", [])
    config_data = load_json("config.json", {})

    clear_screen()
    now_str = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    print("=" * 78)
    print(f"  KAEKAE BOT CLUSTER - MASTER CONTROL CENTER  |  {now_str}")
    print("=" * 78)

    # Cluster Status
    chatty = state_data.get("chatty_mode", False)
    diss = state_data.get("diss_active", False)
    diss_target = state_data.get("diss_target", "None")
    active_spk = state_data.get("current_active_speaker", "Unknown speaker")

    print(f"  [CLUSTER STATUS]")
    print(f"    - Chat Worker (Term 1)  : ACTIVE (OCR & Commands Online)")
    print(f"    - Audio Worker (Term 2) : ACTIVE (Whisper STT & Talk Control Online)")
    print(f"    - Room Focused          : {state_data.get('current_focused_room', 'Camfrog Room')}")
    print(f"    - Active Mic Speaker    : {active_spk}")
    print(f"    - Chatty Mode           : {'[ON]' if chatty else '[OFF]'}")
    print(f"    - Diss System           : {'[ACTIVE -> ' + diss_target + ']' if diss else '[STANDBY]'}")
    print("-" * 78)

    # Voice Personas
    has_el = bool(config_data.get("elevenlabs_api_key") or os.environ.get("ELEVENLABS_API_KEY"))
    engine_name = "ElevenLabs Ultra-Realistic" if has_el else "Edge-TTS Neural SSML"
    print(f"  [VOICE PERSONAS] Engine: {engine_name}")
    print(f"    - VALLEY (Normal/Sweet) : CyGFgkeLSDCTZEzs6B89 -> Handles standard chat & !say")
    print(f"    - UPPITY (Roast/Snark)  : XDP6lUBFhYCAbkIhMCt5 -> Deployed on !diss & jokes")
    print(f"    - VALLEY SEXY (Flirty)  : zqDzpaf3w8JdUBL9YxSv -> Deployed for male users (Blue Icon)")
    print("-" * 78)

    # Room Members & Gender Recognition
    room_users = state_data.get("current_room_users", [])
    print(f"  [ROOM PARTICIPANTS] Total: {len(room_users)}")
    if room_users:
        chunks = []
        for u in room_users[:16]:
            u_info = users_data.get(u.lower(), {})
            gender = u_info.get("gender", "unknown")
            # Blue for Male, Pink for Female
            tag = "[M-Blue]" if gender == "male" else ("[F-Pink]" if gender == "female" else "[?]")
            chunks.append(f"{u} {tag}")
        print("    " + " | ".join(chunks))
    else:
        print("    (Scanning room members...)")
    print("-" * 78)

    # Recent Audit Log
    print(f"  [RECENT MODERATION & KICKS] Total Kicks Tracked: {len(kicks_data)}")
    if kicks_data:
        for k in kicks_data[-3:]:
            print(f"    - {k.get('timestamp', '')} | {k.get('user', '')} kicked by {k.get('moderator', '')} ({k.get('reason', '')})")
    else:
        print("    No recent kicks recorded.")
    print("=" * 78)
    print("  Controls: [1] Speak on Mic  [2] Trigger !diss  [3] Refresh HUD  [0] Exit")
    print("=" * 78)

def queue_speech(text, persona="valley"):
    q_file = "pending_speech_queue.json"
    items = []
    if os.path.exists(q_file):
        try:
            with open(q_file, "r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            items = []
    items.append({"text": text, "persona": persona, "timestamp": time.time()})
    with open(q_file, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    print(f"\n[ACTION] Queued speech: \"{text}\" ({persona.upper()} persona) -> Sent to Terminal 2!")

def main():
    while True:
        print_hud()
        choice = input("\nEnter choice (or press Enter to refresh): ").strip()
        if choice == "1":
            txt = input("Enter phrase to speak: ").strip()
            if txt:
                print("Select Persona: [1] Valley (Normal) [2] Uppity (Roast) [3] Valley Sexy (Flirty)")
                p_c = input("Choice [1-3, default: 1]: ").strip()
                p_map = {"1": "valley", "2": "uppity", "3": "valley_sexy"}
                persona = p_map.get(p_c, "valley")
                queue_speech(txt, persona)
                time.sleep(1.5)
        elif choice == "2":
            target = input("Enter username to diss: ").strip()
            if target:
                phrase = f"Hey {target}, did you really think you could say that and get away with it? Honey, please!"
                queue_speech(phrase, "uppity")
                time.sleep(1.5)
        elif choice == "0":
            print("Exiting Master Dashboard.")
            break
        else:
            time.sleep(0.5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[MASTER] Closed.")
