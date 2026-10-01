#!/usr/bin/env python3
"""
================================================================================
KaeKae Bot - Camfrog Active Speaker & Audio Filing Calibration Tool
================================================================================
Purpose:
  Calibrate the exact on-screen region where Camfrog displays the username of
  the active speaker on the microphone. This ensures all 7-second audio clips
  are filed accurately into:
      audio_memory/usernames/<speaker_username>/

Interactive Flow:
  - Asks you to move your mouse and press [ENTER] when ready (NO rushed countdowns).
  - You mark the TOP-LEFT and BOTTOM-RIGHT of the speaker username area.
  - Instantly takes a screenshot, saves 'preview_speaker_box.png', and runs OCR.
  - Shows you the detected name and asks you to confirm or retry.
  - Automatically saves coordinates to 'camfrog_coords.json' and 'config.json'.
================================================================================
"""

import sys
import os
import time
import json
import re

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import pytesseract
    from PIL import Image, ImageOps, ImageEnhance
except ImportError:
    pytesseract = None
    Image = None

CONFIG_FILE = "config.json"
COORDS_FILE = "camfrog_coords.json"
AUDIO_MEMORY_DIR = os.path.join("audio_memory", "usernames")

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def banner():
    print("=" * 76)
    print("   KAEKAE BOT: ACTIVE SPEAKER CALIBRATION & AUDIO FILING WIZARD")
    print("=" * 76)
    print(" Goal: Identify who is speaking on the mic so audio recordings get filed")
    print("       accurately into dedicated user folders on your computer.")
    print("=" * 76)

def prompt_user_for_corner(title: str, instruction: str) -> tuple:
    """Waits for the user to press ENTER, then captures the current mouse coordinate."""
    print(f"\n>>> {title.upper()}")
    print(instruction)
    input("👉 Move your mouse to the spot, then press [ENTER] here: ")
    
    # Brief pause to ensure mouse has settled
    time.sleep(0.3)
    if pyautogui:
        pos = pyautogui.position()
        print(f"✓ CAPTURED: X={pos.x}, Y={pos.y}")
        return pos.x, pos.y
    else:
        print("[ERROR] pyautogui is not installed. Please run: pip install pyautogui")
        return 0, 0

def run_ocr_on_box(left: int, top: int, width: int, height: int) -> tuple:
    """Takes a screenshot of the specified box, preprocesses it, and runs OCR."""
    if not pyautogui or not pytesseract or not Image:
        return "OCR library unavailable", None

    # Capture the region
    shot = pyautogui.screenshot(region=(left, top, width, height))
    shot.save("preview_speaker_box.png")

    # Upscale 3x for high-resolution OCR (Camfrog fonts are small)
    w, h = shot.size
    upscaled = shot.resize((w * 3, h * 3), Image.BICUBIC if hasattr(Image, "BICUBIC") else Image.Resampling.BICUBIC)

    # Convert to grayscale
    gray = upscaled.convert("L")

    # High contrast enhancement
    enhancer = ImageEnhance.Contrast(gray)
    contrast_img = enhancer.enhance(2.2)

    # Invert if dark background with light text
    stat = contrast_img.histogram()
    # Check average brightness
    avg_brightness = sum(i * count for i, count in enumerate(stat)) / (w * h * 9)
    if avg_brightness < 125:
        # Dark theme Camfrog: invert so text is black on white for Tesseract
        contrast_img = ImageOps.invert(contrast_img)

    contrast_img.save("preview_speaker_box_processed.png")

    # Run Tesseract with single line / sparse text mode
    custom_config = r'--psm 7 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-$.'
    raw_text = pytesseract.image_to_string(contrast_img, config=custom_config).strip()
    
    # Clean up non-username characters
    clean_username = re.sub(r'[^a-zA-Z0-9_\-\$]', '', raw_text)
    return clean_username, raw_text

def calibrate_active_speaker():
    clear_screen()
    banner()

    print("\nVisual Camfrog Guide:")
    print("  [ TALK ]  [ ▼ ARROW ]  [ 🎙️ MIC ]  [ 🔊 SPEAKER ]  [ 👤 SPEAKER USERNAME HERE ]")
    print("                                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^")
    print("  When someone talks on Camfrog, their username appears right here, to the")
    print("  RIGHT of the speaker sound icon.")
    print("\nReady to calibrate? Make sure your Camfrog room window is visible on screen.")
    input("Press [ENTER] to begin...")

    while True:
        # STEP 1: Top-Left corner
        tl_x, tl_y = prompt_user_for_corner(
            "Step 1 of 2: Top-Left Corner of Username Area",
            "Hover your mouse over the TOP-LEFT corner of where the active speaker's\n"
            "username appears (to the right of the speaker icon)."
        )

        # STEP 2: Bottom-Right corner
        br_x, br_y = prompt_user_for_corner(
            "Step 2 of 2: Bottom-Right Corner of Username Area",
            "Hover your mouse over the BOTTOM-RIGHT corner of the username area.\n"
            "(Give a little extra space to the right so long usernames don't get cut off)."
        )

        # Calculate bounding box
        left = min(tl_x, br_x)
        top = min(tl_y, br_y)
        width = abs(br_x - tl_x)
        height = abs(br_y - tl_y)

        # Safety minimums
        if width < 30:
            width = 180
        if height < 12:
            height = 28

        print("\n" + "-" * 76)
        print(f"Calculated Username OCR Box:")
        print(f"  Left={left}, Top={top}, Width={width}px, Height={height}px")
        print("-" * 76)

        # Run OCR Test
        print("\nCapturing test screenshot of that exact box right now...")
        detected_name, raw_ocr = run_ocr_on_box(left, top, width, height)

        print(f"\n[OCR TEST RESULTS]")
        print(f"  Cleaned Username : '{detected_name}'")
        print(f"  Raw OCR Output   : '{raw_ocr}'")
        print(f"  Saved Image Crop : 'preview_speaker_box.png' (you can open this to see what was captured)")

        if not detected_name:
            print("\n💡 NOTE: If nobody was talking on the microphone right now, the area may be blank.")
            print("   You can ask someone in the room to speak on mic, or hold the mic yourself to test.")

        print("\nOptions:")
        print("  [Y] YES - This box is good, save it and proceed.")
        print("  [T] TEST AGAIN - Take another screenshot in 3 seconds (e.g., when someone speaks).")
        print("  [R] RETRY - Re-pick the corners.")
        
        choice = input("Your choice (Y/T/R) [default: Y]: ").strip().lower()

        if choice == "t":
            print("\nWaiting 3 seconds for active speaker on mic...")
            time.sleep(3)
            detected_name, raw_ocr = run_ocr_on_box(left, top, width, height)
            print(f"Retest Result: Clean='{detected_name}' (Raw='{raw_ocr}')")
            confirm = input("Save this box now? (y/n) [default: y]: ").strip().lower()
            if confirm in ("", "y", "yes"):
                break
        elif choice == "r":
            print("\nRestarting corner selection...")
            time.sleep(1)
            continue
        else:
            # Default to Y
            break

    # Save to coordinates file
    coords = {}
    if os.path.exists(COORDS_FILE):
        try:
            with open(COORDS_FILE, "r") as f:
                coords = json.load(f)
        except Exception:
            coords = {}

    coords["active_speaker_ocr_region"] = {
        "left": left,
        "top": top,
        "width": width,
        "height": height
    }

    with open(COORDS_FILE, "w") as f:
        json.dump(coords, f, indent=2)
    print(f"\n✓ Saved to {COORDS_FILE}!")

    # Update config.json
    try:
        cfg = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
        cfg.setdefault("camfrog_ui_layout", {})
        cfg["camfrog_ui_layout"]["active_speaker_ocr_region"] = coords["active_speaker_ocr_region"]
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
        print(f"✓ Updated {CONFIG_FILE} with new speaker OCR coordinates!")
    except Exception as e:
        print(f"[NOTE] Could not update config.json: {e}")

    # Set up and test the audio filing directory
    sample_user = detected_name if detected_name and len(detected_name) >= 2 else "sample_user"
    user_audio_folder = os.path.join(AUDIO_MEMORY_DIR, sample_user)
    os.makedirs(user_audio_folder, exist_ok=True)
    
    print("\n" + "=" * 76)
    print(" AUDIO FILING VERIFICATION")
    print("=" * 76)
    print("✓ Audio memory structure initialized:")
    print(f"  {os.path.abspath(AUDIO_MEMORY_DIR)}/<username>/")
    print(f"\nWhen '{sample_user}' speaks on the mic, KaeKae Bot will now automatically:")
    print(f"  1. OCR the speaker: '{sample_user}'")
    print(f"  2. Save their 7s audio chunk to: {user_audio_folder}/clip_<timestamp>.wav")
    print(f"  3. Log their voice transcript to: {user_audio_folder}/transcripts.jsonl")
    print("=" * 76)

    # Optional Live Monitoring Test
    print("\nWould you like to run a Live Monitor test for 20 seconds?")
    print("This will watch the speaker box every 2 seconds and display who is speaking live.")
    mon_choice = input("Run live test? (y/n) [default: y]: ").strip().lower()
    if mon_choice in ("", "y", "yes"):
        print("\n--- LIVE MONITORING STARTED (Press Ctrl+C to stop) ---")
        start_t = time.time()
        try:
            while time.time() - start_t < 20:
                name, _ = run_ocr_on_box(left, top, width, height)
                ts = time.strftime("%H:%M:%S")
                if name and len(name) >= 2:
                    print(f"[{ts}] 🎙️ ACTIVE SPEAKER: '{name}' -> Filing to: audio_memory/usernames/{name}/")
                else:
                    print(f"[{ts}] [No active speaker on mic / silent]")
                time.sleep(2.0)
        except KeyboardInterrupt:
            print("\nLive test stopped by user.")
        print("--- LIVE MONITORING COMPLETED ---")

    # Optional Talk Button Calibration
    print("\n" + "-" * 76)
    talk_opt = input("Do you also want to calibrate the TALK button (to the left of the arrow)? (y/n) [default: n]: ").strip().lower()
    if talk_opt in ("y", "yes"):
        calibrate_talk_button()

    print("\n" + "=" * 76)
    print(" CALIBRATION COMPLETE! Audio recordings will now be accurately filed.")
    print("=" * 76)

def calibrate_talk_button():
    print("\n--- TALK BUTTON CALIBRATION ---")
    print("In Camfrog, the TALK button is visually to the LEFT of the push-to-talk dropdown arrow.")
    tb_x, tb_y = prompt_user_for_corner(
        "Talk Button Center",
        "Hover your mouse over the center of the TALK button (to the left of the arrow)."
    )

    arr_x, arr_y = prompt_user_for_corner(
        "Dropdown Arrow Center",
        "Hover your mouse over the small dropdown ARROW directly to the right of the talk button."
    )

    offset_x = tb_x - arr_x
    print(f"✓ Talk button is {abs(offset_x)}px to the {'LEFT' if offset_x < 0 else 'RIGHT'} of the arrow.")

    coords = {}
    if os.path.exists(COORDS_FILE):
        try:
            with open(COORDS_FILE, "r") as f:
                coords = json.load(f)
        except Exception:
            coords = {}

    coords["talk_button"] = {"x": tb_x, "y": tb_y, "offset_from_arrow_x": offset_x}
    coords["dropdown_arrow"] = {"x": arr_x, "y": arr_y}

    with open(COORDS_FILE, "w") as f:
        json.dump(coords, f, indent=2)
    print(f"✓ Saved Talk Button coordinates to {COORDS_FILE}!")

run_calibration_wizard = calibrate_active_speaker

if __name__ == "__main__":
    calibrate_active_speaker()
