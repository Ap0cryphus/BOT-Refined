"""
==============================================================================
KAEKAE CAMFROG COORDINATE CALIBRATION
==============================================================================
Captures the two coordinates the bot still needs to click:
  - chat_input  : the Camfrog chat typing bar
  - talk_button : the Camfrog Talk / PTT button

The active speaker is read from the CEF accessibility tree, so there is NO
OCR region to calibrate any more.
==============================================================================
"""

import os
import json
import time

try:
    import pyautogui
except ImportError:
    pyautogui = None

ROOT = os.path.dirname(os.path.abspath(__file__))
COORDS_FILE = os.path.join(ROOT, "camfrog_coords.json")


def prompt_user_for_corner(title, instruction):
    print(f"\n>>> {title.upper()}")
    print(instruction)
    input("   Move your mouse to the spot, then press [ENTER] here: ")
    time.sleep(0.3)
    if pyautogui:
        pos = pyautogui.position()
        print(f"   CAPTURED: X={pos.x}, Y={pos.y}")
        return pos.x, pos.y
    print("[ERROR] pyautogui is not installed. Please run: pip install pyautogui")
    return 0, 0


def calibrate():
    print("=" * 60)
    print("   KAEKAE BOT: CAMFROG COORDINATE CALIBRATION")
    print("=" * 60)
    print("Make sure your Camfrog window is visible on your screen.")
    print("(Speaker detection uses the CEF accessibility tree - no OCR region needed.)")
    input("Press [ENTER] to start...")

    chat_x, chat_y = prompt_user_for_corner(
        "Step 1: Camfrog Chat Input Box",
        "Hover your mouse over the Camfrog chat typing bar."
    )
    talk_x, talk_y = prompt_user_for_corner(
        "Step 2: Camfrog Talk / Mic Button",
        "Hover your mouse over the center of the Talk button."
    )

    coords = {
        "chat_input": {"x": chat_x, "y": chat_y},
        "talk_button": {"x": talk_x, "y": talk_y}
    }

    with open(COORDS_FILE, "w") as f:
        json.dump(coords, f, indent=2)

    print("\n" + "=" * 60)
    print(f"SUCCESS! Coordinates saved to {COORDS_FILE}:")
    print(json.dumps(coords, indent=2))
    print("=" * 60)


# Alias used by `kaekae_bot.py --calibrate` and the diagnostics menu
run_calibration_wizard = calibrate

if __name__ == "__main__":
    calibrate()
