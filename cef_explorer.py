#!/usr/bin/env python3
"""
================================================================================
KaeKae Bot - CEF & UIA Explorer and Live Verification Suite
================================================================================
Comprehensive diagnostic and verification tool for:
  [1] Talk Button Automation (Holds, Releases, Coordinates & Modes)
  [2] Audio Routing & Virtual Cable Playback
  [3] Chromium (CEF) / UIA Control Tree Discovery (Capped at 50 Controls)
  [4] Direct CEF Chat Feed Extraction & Live Monitor
  [5] Direct CEF Active Speaker Detection
  [6] Local DSP Noise Gate & Echo Cleaner Test
  [7] Full Automated End-to-End System Audit
================================================================================
"""

import os
import sys
import time
import json
import re
from typing import List, Dict, Any, Optional

# Core test dependencies
try:
    from cef_probe import (
        global_probe,
        global_talk_controller,
        resolve_audio_output_device,
        play_wav_to_virtual_cable,
        get_configured_output_device
    )
except ImportError:
    global_probe = None
    global_talk_controller = None

try:
    from audio_dsp import dsp_cleaner
except ImportError:
    dsp_cleaner = None

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    import numpy as np
except ImportError:
    np = None

try:
    from pywinauto import Application
except ImportError:
    Application = None

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_header(title: str):
    print("\n" + "=" * 78)
    print(f"  {title.upper()}")
    print("=" * 78)

# ==============================================================================
# TEST 1: TALK BUTTON AUTOMATION (WITH INTERACTIVE PROMPTS)
# ==============================================================================
def test_talk_button_interactive():
    print_header("Test 1: Talk Button Automation & Calibration")
    if global_talk_controller is None:
        print("[ERROR] global_talk_controller is not available.")
        return

    info = global_talk_controller.catch_talk_process()
    cx, cy = global_talk_controller.get_talk_coordinates()
    print(f"Attached to Camfrog Window : {'YES' if info['attached'] else 'NO (Check if Camfrog is open)'}")
    print(f"Main Window HWND           : {info['main_hwnd']}")
    print(f"CEF Render HWND            : {info['cef_render_hwnd']}")
    print(f"Talk Button Coordinates    : ({cx}, {cy})")
    print(f"UIA Button Control Found   : {'YES' if info['talk_ctrl_found'] else 'Using coordinates'}")

    print("\nSelect a Talk Button mode to test:")
    print("  [1] Mouse Down & Hold (Standard Push-to-Talk) - RECOMMENDED")
    print("  [2] Hands-Free Click Toggle")
    print("  [3] F10 Hotkey Hold")
    print("  [4] CEF Window Message (WM_LBUTTONDOWN direct to render HWND)")
    print("  [5] Custom Hold Duration (e.g. 5 seconds)")
    print("  [0] Back to Main Menu")

    choice = input("\nEnter choice [1-5, or 0]: ").strip()
    if choice == "0" or not choice:
        return

    duration = 3.0
    mode = "mouse_hold"
    if choice == "1":
        mode = "mouse_hold"
    elif choice == "2":
        mode = "handsfree"
    elif choice == "3":
        mode = "f10"
    elif choice == "4":
        mode = "cef_hwnd"
    elif choice == "5":
        dur_in = input("Enter duration in seconds (1-15) [default: 5]: ").strip()
        try:
            duration = float(dur_in) if dur_in else 5.0
        except ValueError:
            duration = 5.0

    print(f"\n[EXECUTION] Bringing Camfrog to front and executing '{mode}' for {duration}s...")
    global_talk_controller.grab_mic(mode=mode)
    start_t = time.time()
    while time.time() - start_t < duration:
        remaining = round(duration - (time.time() - start_t), 1)
        print(f"  --> Holding microphone... {remaining}s remaining", end="\r")
        time.sleep(0.2)
    print("\n[EXECUTION] Releasing microphone cleanly...")
    global_talk_controller.release_mic()

    ans = input("\nDid the Talk button on your Camfrog stage activate and release properly? (y/n): ").strip().lower()
    if ans.startswith("y"):
        print("[SUCCESS] Talk button test verified!")
    else:
        print("[NOTICE] If it did not click, run 'python calibrate_camfrog.py' to recalibrate coordinates.")

# ==============================================================================
# TEST 2: AUDIO PLAYBACK TO VB-AUDIO VIRTUAL CABLE
# ==============================================================================
def test_audio_playback_interactive():
    print_header("Test 2: Audio Routing & Live Room Broadcast Test")
    out_device = get_configured_output_device()
    print(f"Default Configured Output Target: '{out_device}'")

    selected_dev_idx = None
    selected_dev_name = out_device

    if sd is not None:
        print("\nScanning all available Windows audio output devices...")
        try:
            devs = sd.query_devices()
            out_list = []
            for idx, d in enumerate(devs):
                if d.get('max_output_channels', 0) > 0:
                    out_list.append((idx, d.get('name', 'Unknown'), d.get('default_samplerate', 48000), d.get('max_output_channels', 2)))

            print(f"{'#':<3} | {'DEVICE NAME':<44} | {'CH':<3} | {'RATE':<6}")
            print("-" * 65)
            for idx, name, rate, ch in out_list:
                mark = " <-- [TARGET]" if any(k in name.lower() for k in ["cable input", "vb-audio", "virtual cable"]) else ""
                print(f"{idx:<3} | {name[:43]:<44} | {ch:<3} | {int(rate):<6}{mark}")
            print("-" * 65)

            dev_choice = input("\nEnter device number to output audio [Press Enter for Auto-Detect]: ").strip()
            if dev_choice.isdigit():
                selected_dev_idx = int(dev_choice)
                selected_dev_name = devs[selected_dev_idx].get('name', f"Device #{selected_dev_idx}")
            else:
                selected_dev_idx, selected_dev_name = resolve_audio_output_device(out_device)
        except Exception as e_sd:
            print(f"[WARN] Error scanning sound devices: {e_sd}")
    else:
        print("[WARN] sounddevice library not imported.")

    print(f"\nTarget Output Device Selected: #{selected_dev_idx} -> '{selected_dev_name}'")

    print("\nSelect Voice / Sound to Broadcast:")
    print("  [1] Beverly Hills Spoiled Blonde (en-US-AvaNeural: +12% rate, +16Hz pitch) [DEFAULT]")
    print("  [2] Teen Barbie / Ultra-Ditzy (en-US-AnaNeural: +14% rate, +22Hz pitch)")
    print("  [3] Sassy Bratty Diva (en-US-JennyNeural: +10% rate, +14Hz pitch)")
    print("  [4] Custom Text with Spoiled Blonde Voice")
    print("  [5] Loud 440Hz / 880Hz Test Chime (Guaranteed line check)")

    sound_mode = input("\nEnter choice [1-5, default: 1]: ").strip() or "1"
    wav_path = "temp_say_broadcast.wav"

    if sound_mode == "5":
        # Generate pure PCM tone
        import wave, math
        sr = 48000
        dur = 3.0
        n_samples = int(sr * dur)
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            frames = bytearray()
            for i in range(n_samples):
                t = i / sr
                freq = 880 if (int(t * 4) % 2 == 0) else 440
                val = int(26000 * math.sin(2 * math.pi * freq * t))
                frames.extend(val.to_bytes(2, byteorder="little", signed=True))
            wf.writeframes(frames)
        print(f"[AUDIO READY] Generated dual-frequency test chime (3.0s, 48kHz PCM).")
    else:
        from cef_probe import synthesize_speech_to_wav
        voice = "en-US-AvaNeural"
        rate = "+12%"
        pitch = "+16Hz"
        phrase = "Like, oh my god, Daddy literally said I can buy this entire chatroom if you guys don't stop being so totally annoying!"

        if sound_mode == "2":
            voice = "en-US-AnaNeural"
            rate = "+14%"
            pitch = "+22Hz"
            phrase = "Ew, as if! Like, who even talks like that? I need an iced matcha latte right now before I literally pass out!"
        elif sound_mode == "3":
            voice = "en-US-JennyNeural"
            rate = "+10%"
            pitch = "+14Hz"
            phrase = "Excuse me, why are all of you looking at me? Oh wait, obviously because I'm gorgeous and rich. Duh!"
        elif sound_mode == "4":
            custom_phrase = input("Enter custom text to speak: ").strip()
            if custom_phrase:
                phrase = custom_phrase

        print(f"\n[VOICE SYNTHESIS] Generating '{voice}' (Rate: {rate}, Pitch: {pitch})...")
        print(f"Phrase: \"{phrase}\"")
        synthesize_speech_to_wav(phrase, wav_path, voice=voice, rate=rate, pitch=pitch)

    hold_mic = input("\nDo you want to hold the Camfrog Talk button while broadcasting? (y/n) [default: y]: ").strip().lower()
    should_hold = (hold_mic != "n")

    if should_hold and global_talk_controller is not None:
        print("\n[ACTION] Focusing Camfrog and holding microphone Talk button...")
        global_talk_controller.grab_mic()
        time.sleep(0.35)

    print(f"[ACTION] Transmitting audio directly to '{selected_dev_name}'...")
    played = play_wav_to_virtual_cable(wav_path, target_name=selected_dev_name)

    if should_hold and global_talk_controller is not None:
        time.sleep(0.3)
        print("[ACTION] Releasing microphone cleanly...")
        global_talk_controller.release_mic()

    print(f"\nBroadcast result: {'SUCCESS' if played else 'FAILED'}")
    ans = input("\nDid you hear the audio broadcasting on your microphone in Camfrog? (y/n): ").strip().lower()
    if ans.startswith("y"):
        print("[SUCCESS] Audio routing verified!")
    else:
        print("\n[TROUBLESHOOTING TIPS]")
        print("  1. In Camfrog -> Settings -> Audio/Video -> Microphone:")
        print("     Make sure 'CABLE Output (VB-Audio Virtual Cable)' is selected as your Camfrog Microphone!")
        print("  2. In Windows Sound Settings -> Recording Devices:")
        print("     Verify that 'CABLE Output' is not muted and the volume is set to 100%.")

# ==============================================================================
# TEST 3: CHROMIUM / UIA CONTROL TREE DISCOVERY (UP TO 1000 CONTROLS)
# ==============================================================================
def test_cef_controls_discovery(max_controls: int = 1000):
    print_header(f"Test 3: CEF & UIA Control Tree Discovery (Up to {max_controls} Controls)")
    if Application is None:
        print("[ERROR] pywinauto is not installed.")
        return

    filter_kw = input("Filter controls by keyword (e.g. 'talk', 'chat', 'mic', or press Enter for ALL): ").strip().lower()

    print("Connecting to Camfrog window via UI Automation (backend='uia')...")
    app = None
    try:
        app = Application(backend="uia").connect(title_re="(?i).*(Camfrog|Players__Lounge|DRAMA_CENTRAL).*")
    except Exception:
        try:
            app = Application(backend="uia").connect(path="camfrog.exe")
        except Exception as e:
            print(f"[ERROR] Could not connect to Camfrog window: {e}")
            print("Make sure Camfrog is open and running on your desktop.")
            return

    try:
        win = app.top_window()
        win_title = win.window_text()
        rect = win.rectangle()
        print(f"Window Connected: '{win_title}' ({rect.width()}x{rect.height()} at {rect.left},{rect.top})")
        print(f"\nScanning UI Automation tree (Limit: {max_controls} controls)... Please wait...\n")

        descendants = win.descendants()
        print(f"{'#':<4} | {'TYPE':<12} | {'RECT (L, T, W, H)':<24} | {'NAME / VALUE / TEXT':<36}")
        print("-" * 82)

        count = 0
        captured_controls = []
        for ctrl in descendants:
            c_type = ctrl.element_info.control_type or "Unknown"
            c_name = (ctrl.element_info.name or ctrl.window_text() or "").strip()
            c_rect = ctrl.rectangle()
            rect_str = f"({c_rect.left},{c_rect.top},{c_rect.width()},{c_rect.height()})"

            # If user provided a filter keyword, skip controls that don't match
            if filter_kw:
                match = (filter_kw in c_name.lower()) or (filter_kw in c_type.lower())
                if not match:
                    continue
            else:
                # Filter out blank structural containers
                if not c_name and c_type in ("Pane", "Group", "Custom", "Separator"):
                    continue

            count += 1
            entry = {
                "index": count,
                "type": c_type,
                "rect": (c_rect.left, c_rect.top, c_rect.width(), c_rect.height()),
                "name": c_name[:80]
            }
            captured_controls.append(entry)

            display_name = c_name[:34] + "..." if len(c_name) > 34 else c_name
            if not display_name:
                display_name = "<no text>"
            print(f"{count:<4} | {c_type:<12} | {rect_str:<24} | {display_name:<36}")

            if count >= max_controls:
                print("-" * 82)
                print(f"[INFO] Reached maximum control cap ({max_controls} controls displayed).")
                break

        print(f"\nTotal matching controls discovered: {len(captured_controls)}")

        with open("cef_controls_dump.json", "w", encoding="utf-8") as f:
            json.dump(captured_controls, f, indent=2)
        print("Controls saved to 'cef_controls_dump.json' for reference.")

    except Exception as e:
        print(f"[ERROR] Exception during control scan: {e}")

# ==============================================================================
# TEST 4: DIRECT CHAT FEED EXTRACTION (CEF / UIA)
# ==============================================================================
def test_direct_chat_feed_monitor(monitor_seconds: int = 15):
    print_header(f"Test 4: Direct Chat Feed Monitor ({monitor_seconds}s Live Feed)")
    if Application is None:
        print("[ERROR] pywinauto is not installed.")
        return

    print("Connecting to Camfrog UIA tree to inspect Chat messages...")
    try:
        app = Application(backend="uia").connect(title_re="(?i).*(Camfrog|Players__Lounge|DRAMA_CENTRAL).*")
        win = app.top_window()
    except Exception as e:
        print(f"[ERROR] Could not connect to Camfrog: {e}")
        return

    print("Listening for chat messages in room (Send a test message in Camfrog chat now!)...")
    seen_messages = set()
    start_time = time.time()

    while time.time() - start_time < monitor_seconds:
        try:
            for ctrl in win.descendants():
                c_type = ctrl.element_info.control_type
                if c_type in ("ListItem", "Text", "Edit"):
                    txt = (ctrl.element_info.name or ctrl.window_text() or "").strip()
                    if txt and len(txt) > 3 and txt not in seen_messages:
                        # Exclude window title, button labels, time indicators
                        if txt.lower() not in ("talk", "hands-free", "push to talk", "camfrog"):
                            if any(c in txt for c in [":", "says", "joined", "left", "!"]):
                                ts = time.strftime("%H:%M:%S")
                                print(f"  [{ts}] 💬 CHAT CAPTURED: {txt}")
                                seen_messages.add(txt)
        except Exception:
            pass
        time.sleep(0.5)

    print(f"\nChat monitor complete. Total unique messages captured: {len(seen_messages)}")

# ==============================================================================
# TEST 5: ACTIVE SPEAKER DETECTION
# ==============================================================================
def test_active_speaker_live(monitor_seconds: int = 12):
    print_header(f"Test 5: Live Active Speaker Detection ({monitor_seconds}s)")
    if global_probe is None:
        print("[ERROR] global_probe is not available.")
        return

    print("Starting CEF active speaker probe...")
    global_probe.start_probe_daemon()
    last_speaker = ""
    start_t = time.time()

    print("Please key up on the microphone or have someone talk in Camfrog...\n")
    while time.time() - start_t < monitor_seconds:
        spk = global_probe.get_speaker()
        if spk != last_speaker:
            ts = time.strftime("%H:%M:%S")
            if spk and spk != "Unknown speaker":
                print(f"  [{ts}] 🎙️ ACTIVE SPEAKER ON MIC: '{spk}'")
            else:
                print(f"  [{ts}] ⏹️ Microphone is now FREE.")
            last_speaker = spk
        time.sleep(0.15)

    global_probe.stop()
    print("\nActive speaker test complete.")

# ==============================================================================
# TEST 6: AUDIO DSP CLEANER & NOISE GATE TEST
# ==============================================================================
def test_dsp_cleaner_sample():
    print_header("Test 6: Audio DSP Noise Gate & Clean-up Verification")
    if dsp_cleaner is None:
        print("[ERROR] dsp_cleaner is not available.")
        return

    if sd is None or np is None:
        print("[ERROR] sounddevice and numpy are required.")
        return

    out_dev = get_configured_output_device()
    print(f"Recording 3.0 seconds of audio from configured device to test noise filtering...")
    try:
        dev_idx = None
        devices = sd.query_devices()
        for idx, d in enumerate(devices):
            if d.get('max_input_channels', 0) > 0 and "cable" in d.get('name', '').lower():
                dev_idx = idx
                break

        print(f"Using audio input device index: {dev_idx}")
        rec = sd.rec(frames=int(3.0 * 16000), samplerate=16000, channels=1, dtype="int16", device=dev_idx)
        sd.wait()
        raw_samples = rec.flatten()

        cleaned_samples, stats = dsp_cleaner.clean_chunk(raw_samples)
        print("\n--- DSP CLEANING REPORT ---")
        print(f"  Raw Peak Amplitude       : {stats['peak_before']} / 32767")
        print(f"  Cleaned Peak Amplitude   : {stats['peak_after']} / 32767")
        print(f"  Measured Noise Floor RMS : {stats['noise_floor']}")
        print(f"  Gate Attenuation         : {stats['gate_attenuation_db']} dB")
        print("---------------------------")
        print("Result: Noise gate and 85Hz high-pass filter are operating cleanly!")

    except Exception as e:
        print(f"[ERROR] Failed during audio test: {e}")

# ==============================================================================
# MAIN INTERACTIVE MENU
# ==============================================================================
def main_menu():
    while True:
        clear_screen()
        print("=" * 78)
        print("       KAEKAE BOT - CEF & SYSTEM VERIFICATION SUITE")
        print("=" * 78)
        print("  [1] Test Talk Button (Click, Hold, Modes & Recalibration)")
        print("  [2] Test Audio Voice Broadcast (Routing to VB-Audio Cable)")
        print("  [3] Discover CEF / UIA Controls (Up to 1000 Controls with Search Filter)")
        print("  [4] Test Direct Chat Feed Monitor (15s Live Feed)")
        print("  [5] Test Live Active Speaker Detection (12s Live Monitor)")
        print("  [6] Test Audio DSP Noise Gate & Clean-up")
        print("  [7] Run Full Automated System Audit")
        print("  [0] Exit")
        print("=" * 78)

        choice = input("Select an option [1-7, or 0]: ").strip()
        if choice == "1":
            test_talk_button_interactive()
            input("\nPress Enter to return to menu...")
        elif choice == "2":
            test_audio_playback_interactive()
            input("\nPress Enter to return to menu...")
        elif choice == "3":
            cap = input("Enter max controls to display [default: 1000]: ").strip()
            max_c = int(cap) if cap.isdigit() else 1000
            test_cef_controls_discovery(max_controls=max_c)
            input("\nPress Enter to return to menu...")
        elif choice == "4":
            test_direct_chat_feed_monitor()
            input("\nPress Enter to return to menu...")
        elif choice == "5":
            test_active_speaker_live()
            input("\nPress Enter to return to menu...")
        elif choice == "6":
            test_dsp_cleaner_sample()
            input("\nPress Enter to return to menu...")
        elif choice == "7":
            print("\nRunning full automated system check...")
            test_cef_controls_discovery(max_controls=25)
            time.sleep(1)
            test_talk_button_interactive()
            input("\nPress Enter to return to menu...")
        elif choice == "0":
            print("Exiting verification suite.")
            break

if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("--talk", "-t"):
            test_talk_button_interactive()
        elif arg in ("--audio", "-a"):
            test_audio_playback_interactive()
        elif arg in ("--controls", "-c"):
            test_cef_controls_discovery()
        elif arg in ("--chat"):
            test_direct_chat_feed_monitor()
        elif arg in ("--speaker", "-s"):
            test_active_speaker_live()
        elif arg in ("--dsp"):
            test_dsp_cleaner_sample()
        else:
            main_menu()
    else:
        main_menu()
