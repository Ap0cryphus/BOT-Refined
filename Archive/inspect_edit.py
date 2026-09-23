from pywinauto import Application

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

win = app.top_window()

edit = win.descendants(control_type="Edit")[0]

print("Control Type:", edit.element_info.control_type)
print("Name:", edit.element_info.name)

input("\nPress Enter to exit...")