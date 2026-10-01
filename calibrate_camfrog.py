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

COORDS_FILE = "camfrog_coords.json"

def prompt_user_for_corner(title, instruction):
    print(f"\n>>> {title.upper()}")
    print(instruction)
    input("?? Move your mouse to the spot, then press [ENTER] here: ")
    time.sleep(0.3)
    if pyautogui:
        pos = pyautogui.position()
        print(f"? CAPTURED: X={pos.x}, Y={pos.y}")
        return pos.x, pos.y
    else:
        print("[ERROR] pyautogui is not installed. Please run: pip install pyautogui")
        return 0, 0

def calibrate():
    print("=" * 60)
    print("   KAEKAE BOT: CAMFROG ACTIVE SPEAKER CALIBRATION")
    print("=" * 60)
    print("Make sure your Camfrog window is visible on your screen.")
    input("Press [ENTER] to start...")

    # Step 1: Top-Left
    tl_x, tl_y = prompt_user_for_corner(
        "Step 1: Top-Left Corner of Speaker Name",
        "Hover your mouse over the TOP-LEFT of where the active speaker's username appears."
    )

    # Step 2: Bottom-Right
    br_x, br_y = prompt_user_for_corner(
        "Step 2: Bottom-Right Corner of Speaker Name",
        "Hover your mouse over the BOTTOM-RIGHT of where the username appears."
    )

    left = min(tl_x, br_x)
    top = min(tl_y, br_y)
    width = max(180, abs(br_x - tl_x))
    height = max(28, abs(br_y - tl_y))

    # Step 3: Chat Input box
    chat_x, chat_y = prompt_user_for_corner(
        "Step 3: Camfrog Chat Input Box",
        "Hover your mouse over the Camfrog chat typing bar."
    )

    # Step 4: Talk Button
    talk_x, talk_y = prompt_user_for_corner(
        "Step 4: Camfrog Talk / Mic Button",
        "Hover your mouse over the center of the Talk button."
    )

    coords = {
        "active_speaker_ocr_region": {
            "left": left,
            "top": top,
            "width": width,
            "height": height
        },
        "chat_input": {"x": chat_x, "y": chat_y},
        "talk_button": {"x": talk_x, "y": talk_y}
    }

    with open(COORDS_FILE, "w") as f:
        json.dump(coords, f, indent=2)

    print("\n" + "=" * 60)
    print(f"? SUCCESS! Coordinates saved to {COORDS_FILE}:")
    print(json.dumps(coords, indent=2))
    print("=" * 60)

if __name__ == "__main__":
    calibrate()
