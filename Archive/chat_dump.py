from pywinauto import Application

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

win = app.top_window()

for ctrl in win.descendants():

    try:
        if ctrl.element_info.control_type == "Text":

            text = ctrl.window_text().strip()

            if text:
                print(text)

    except:
        pass