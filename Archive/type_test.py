import pyautogui
import time

print("You have 5 seconds to click inside Notepad.")

time.sleep(5)

pyautogui.write(
    "Hello from my AI bot!",
    interval=0.05
)

pyautogui.press("enter")