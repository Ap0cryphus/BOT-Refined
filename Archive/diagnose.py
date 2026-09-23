from pywinauto import Application

app = Application(backend="uia").connect(
    found_index=0,
    title_re=".*Players__L.*"
)
win = app.top_window()
win_rect = win.rectangle()

# Print ALL controls in the bottom 200px of the window (where chat input lives)
for ctrl in win.descendants():
    try:
        rect = ctrl.rectangle()
        if rect.bottom > win_rect.bottom - 200:
            print(f"type='{ctrl.element_info.control_type}' | class='{ctrl.class_name()}' | text='{ctrl.window_text()[:30]}' | rect={rect}")
    except:
        pass   