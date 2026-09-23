from pywinauto import Application
import time

app = Application(backend="uia").connect(
    title_re=".*Notepad.*"
)

window = app.top_window()

print("Focusing Notepad...")

time.sleep(3)

window.set_focus()

print("Done.")