import pyautogui
import time

print("Click inside Notepad within 5 seconds...")

time.sleep(5)

pyautogui.write(
    "THIS IS A TEST",
    interval=0.05
)