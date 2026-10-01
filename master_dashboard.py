"""
==============================================================================
KAEKAE MASTER DASHBOARD (TERMINAL 3: HUD + SILENT COMMAND CONSOLE)
==============================================================================
Read-only heads-up display of the whole cluster plus a control console that
never touches Camfrog directly:
  [1] Speak on the room mic  -> broadcast_queue.json (Terminal 2 speaks it)
  [2] Voice / Engine picker  -> config.json (persists everywhere)
  [3] Send a silent command  -> command_inbox.jsonl (Terminal 1 runs it)
  [4] Grab / Release the mic -> verified controller, honest result
  [5] Stop transcription     -> silent command (obeys the one-hour gate + dedupe)

Every action goes through kaekae_core's cross-process-safe store.
==============================================================================
"""

import os
import sys
import time
from datetime import datetime

os.environ.setdefault("KAEKAE_TERMINAL", "t3")

if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.kernel32.SetConsoleTitleW("KaeKae Master Control [Terminal 3 - HUD & Console]")
    except Exception:
        pass

try:
    import kaekae_core as core
except Exception:
    core = None


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def _read(name, default):
    if core is not None:
        try:
            return core.read_json(name, default)
        except Exception:
            return default
    return default


def _status(flag):
    return "\033[92mONLINE\033[0m" if flag else "\033[91mOFFLINE\033[0m"


def print_hud():
    state_data = _read("bot_state.json", {}) or {}
    users_data = _read("bot_users.json", {}) or {}
    kicks_data = _read("bot_kicks.json", []) or []
    cfg = _read("config.json", {}) or {}
    beats = _read("terminal_heartbeats.json", {}) or {}
    talk = _read("talk_state.json", {}) or {}
    gate = _read("outbound_gate.json", {}) or {}
    bqueue = _read("broadcast_queue.json", []) or []

    clear_screen()
    now_str = datetime.now().strftime("%Y-%m-%d  %I:%M:%S %p")
    print("=" * 78)
    print(f"  KAEKAE CLUSTER - MASTER CONTROL   |   {now_str}")
    print("=" * 78)

    print("  [TERMINAL STATUS]")
    print(f"    - Chat Worker (Term 1) : {_status(core.terminal_alive('t1') if core else False)}"
          f"   CEF chat + commands + chat writer")
    print(f"    - Audio Worker (Term 2): {_status(core.terminal_alive('t2') if core else False)}"
          f"   STT + verified talk control")
    print(f"    - Room Focused         : {state_data.get('current_focused_room', 'unknown')}")
    print(f"    - Active Mic Speaker   : {state_data.get('current_active_speaker', 'Unknown speaker')}")
    print(f"    - Transcription        : {'ON' if state_data.get('transcribe_enabled') else 'OFF'}"
          f"   |  Listening: {'ON' if state_data.get('listening_enabled') else 'OFF'}"
          f"   |  Chatty: {'ON' if state_data.get('chatty_mode') else 'OFF'}"
          f"   |  Muted: {'YES' if state_data.get('responses_muted') else 'no'}")
    diss = state_data.get("diss_active", False)
    diss_target = state_data.get("diss_target", "")
    print(f"    - Diss System          : {'[ACTIVE -> ' + str(diss_target) + ']' if diss else '[STANDBY]'}")
    print("-" * 78)

    print("  [VOICE]")
    engine = cfg.get("engine", "edge")
    has_el = bool(cfg.get("elevenlabs_api_key") or os.environ.get("ELEVENLABS_API_KEY"))
    print(f"    - Engine               : {engine}")
    if engine == "qwen":
        print(f"    - Qwen speaker         : {cfg.get('qwen_speaker', 'vivian')}")
    elif engine == "elevenlabs":
        print(f"    - Persona              : {cfg.get('elevenlabs_persona', 'valley')}")
    else:
        print(f"    - Edge voice           : {cfg.get('voice', 'en-US-AvaNeural')}")
    print(f"    - ElevenLabs key       : {'configured' if has_el else 'not set'}")
    print(f"    - Queued broadcasts    : {len(bqueue)}")
    print(f"    - Repeat gate (1h)     : {len(gate)} distinct replies remembered")
    print("-" * 78)

    if talk:
        print("  [TALK BUTTON]")
        print(f"    - Holder               : {talk.get('holder', '?')}  ({talk.get('method', 'none')})")
        print(f"    - Holding              : {'YES' if talk.get('holding') else 'no'}")
        print("-" * 78)

    room_users = state_data.get("current_room_users", []) or []
    print(f"  [ROOM PARTICIPANTS] Total: {len(room_users)}")
    if room_users:
        chunk = []
        for u in room_users[:14]:
            gender = (users_data.get(u.lower(), {}) or {}).get("gender", "unknown")
            tag = "[M]" if gender == "male" else ("[F]" if gender == "female" else "[?]")
            chunk.append(f"{tag}{u}")
        print("    " + "  ".join(chunk))
    else:
        print("    (no users tracked yet)")
    print("-" * 78)

    print(f"  [RECENT MODERATION] Total tracked: {len(kicks_data)}")
    for k in kicks_data[-3:]:
        print(f"    - {k.get('time', '')} | {k.get('actor', '')} {k.get('action', '')} {k.get('target', '')}")
    if not kicks_data:
        print("    (none recorded)")
    print("=" * 78)
    print("  [1] Speak on mic   [2] Voice/Engine   [3] Send command   [4] Grab/Release mic   [5] Stop transcription   [0] Exit")
    print("=" * 78)


def queue_speech(text, persona=""):
    """Queue a mic broadcast for Terminal 2 (cross-process safe)."""
    if core is None:
        print("\n[ERROR] kaekae_core unavailable; cannot queue.")
        return False
    cfg = core.load_config()
    persona = persona or cfg.get("elevenlabs_persona", "valley")
    ok = core.enqueue_broadcast(
        text, persona=persona, voice=cfg.get("voice", "en-US-AvaNeural"),
        rate=cfg.get("voice_rate", "+12%"), pitch=cfg.get("voice_pitch", "+16Hz"),
        source="t3")
    print(f"\n[ACTION] {'Queued' if ok else 'FAILED to queue'} mic speech: \"{text}\" "
          f"(persona={persona}) -> Terminal 2")
    return ok


def voice_menu():
    from cef_probe import voice_persona_menu, _voice_summary
    voice_persona_menu()
    print(f"[VOICE] Active now: {_voice_summary()}")


def send_command(text):
    """Send a SILENT command - Terminal 1 executes it through the same
    claim-and-dispatch path used for chat, so dedupe + the one-hour gate apply."""
    if core is None:
        print("\n[ERROR] kaekae_core unavailable.")
        return False
    core.dump_inbox_command(text, source="t3")
    print(f"\n[ACTION] Silent command queued for Terminal 1: \"{text}\"")
    return True


def toggle_transcription():
    """Stop live transcription via the same silent-command path (state stays
    owned by Terminal 1 - no cross-process file clobbering)."""
    send_command("!transcribed")


def grab_or_release():
    """Verified mic control from the console, with the honest result shown."""
    try:
        from cef_probe import global_talk_controller
    except Exception as e:
        print(f"\n[ERROR] Could not load talk controller: {e}")
        return
    if global_talk_controller is None:
        print("\n[ERROR] Talk controller unavailable.")
        return
    try:
        ans = input("Action - [g]rab (verified) or [r]elease? ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if ans.startswith("r"):
        global_talk_controller.release_mic()
        print("\n[ACTION] Microphone released.")
        return
    print("\n[ACTION] Attempting verified grab (rapid re-press until KaeKae's name holds)...")
    res = global_talk_controller.acquire_talk()
    print(f"  attempts={res.get('attempts')} patterns={res.get('patterns')}")
    print(f"  speaker={res.get('observed_speaker')!r} stable={res.get('stability_seconds')}s")
    print(f"  OUTCOME: {'CONFIRMED' if res.get('ok') else 'FAILED - ' + str(res.get('reason'))}")
    if res.get("ok"):
        print("  Holding for 3s, then releasing...")
        time.sleep(3)
        global_talk_controller.release_mic()


def main():
    if core is not None:
        core.heartbeat("t3")
    while True:
        try:
            if core is not None:
                core.heartbeat("t3")
            print_hud()
            try:
                choice = input("\nEnter choice (Enter refreshes): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[MASTER] Exiting.")
                break

            if choice == "1":
                txt = input("Phrase to speak on the mic: ").strip()
                if txt:
                    persona = input("Persona - [1] valley  [2] uppity  [3] valley_sexy  (default: saved): ").strip()
                    p_map = {"1": "valley", "2": "uppity", "3": "valley_sexy"}
                    queue_speech(txt, p_map.get(persona, ""))
                    time.sleep(1.0)
            elif choice == "2":
                voice_menu()
                time.sleep(0.8)
            elif choice == "3":
                cmd = input("Command to run silently (!who, !info on bob, !diss, ...): ").strip()
                if cmd:
                    send_command(cmd)
                    time.sleep(1.0)
            elif choice == "4":
                grab_or_release()
                time.sleep(0.8)
            elif choice == "5":
                toggle_transcription()
                time.sleep(1.0)
            elif choice == "0":
                print("Exiting Master Dashboard.")
                break
        except Exception as e:
            print(f"[MASTER ERROR] {e}")
            time.sleep(1.0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[MASTER] Closed.")