from pywinauto import Application

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

win = app.top_window()

edit = win.descendants(control_type="Edit")[0]

edit.set_focus()

edit.type_keys(
    "TEST MESSAGE",
    with_spaces=True
)

input("Press Enter to exit...")