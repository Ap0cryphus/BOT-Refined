from pywinauto import Application

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

win = app.top_window()

for i, ctrl in enumerate(win.descendants()):

    try:
        rect = ctrl.rectangle()

        print(
            f"{i}: "
            f"{ctrl.element_info.control_type} | "
            f"{ctrl.element_info.name} | "
            f"{rect}"
        )

    except:
        pass

input("Press Enter...")