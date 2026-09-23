from pywinauto import Application

app = Application(backend="uia").connect(
    title_re=".*Notepad.*"
)

window = app.top_window()

for child in window.descendants():
    try:
        print(
            "Type:",
            child.element_info.control_type,
            "| Text:",
            repr(child.window_text())
        )
    except:
        pass