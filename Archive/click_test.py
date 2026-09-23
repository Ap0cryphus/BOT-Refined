from pywinauto import Application
import pyautogui
import time

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

# Center of the editor pane
x = 1286
y = 1127

print("Clicking editor...")

pyautogui.click(x, y)

time.sleep(1)

pyautogui.write(
    "THIS IS A TEST",
    interval=0.05
)

input("Press Enter to exit...")