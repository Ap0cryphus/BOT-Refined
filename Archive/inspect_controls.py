from pywinauto import Application

app = Application(backend="uia").connect(
    title_re=".*Notepad.*"
)

window = app.top_window()

print("Connected to:", window.window_text())

window.print_control_identifiers()