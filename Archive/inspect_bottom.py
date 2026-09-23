from pywinauto import Application

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

win = app.top_window()

for ctrl in win.descendants():

    try:
        rect = ctrl.rectangle()

        # bottom area of window
        if rect.top > 1050:

            print(
                f"{ctrl.element_info.control_type} | "
                f"{ctrl.element_info.name} | "
                f"{rect}"
            )

    except:
        pass

input("Press Enter...")