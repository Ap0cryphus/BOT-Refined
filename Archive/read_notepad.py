from pywinauto import Application

app = Application(backend="uia").connect(
    title_re=".*Notepad.*"
)

window = app.top_window()

edit = window.child_window(control_type="Edit")

print(edit.window_text())