from pywinauto import Application

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

win = app.top_window()

edit = win.descendants(control_type="Edit")[0]

edit.set_edit_text("HELLO TEST")

input("Press Enter to exit...")