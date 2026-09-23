from pywinauto import Application
import pyautogui
import time

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

win = app.top_window()

# Bring Camfrog to the front
win.set_focus()

time.sleep(2)

# Move mouse to center of the editor area
pyautogui.click(1286, 1127)

time.sleep(1)

pyautogui.write(
    "TEST",
    interval=0.05
)

input("Press Enter...")