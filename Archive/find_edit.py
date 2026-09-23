from pywinauto import Application

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

win = app.top_window()

# Find all Edit controls
edits = win.descendants(control_type="Edit")

print(f"Found {len(edits)} Edit controls")

for i, edit in enumerate(edits):
    print(f"Edit #{i}")

input("Press Enter to exit...")