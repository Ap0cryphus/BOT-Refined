from pywinauto import Application

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

win = app.top_window()

print("\n--- CONTROLS FOUND ---\n")

for control in win.descendants():
    try:
        print(
            f"{control.element_info.control_type} | "
            f"{control.element_info.name}"
        )
    except:
        pass

input("\nPress Enter to exit...")