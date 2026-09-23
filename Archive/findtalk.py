for ctrl in win.descendants():
    t = ctrl.window_text()
    if t and "talk" in t.lower():
        print(f"  type='{ctrl.element_info.control_type}' | text='{t}' | rect={ctrl.rectangle()}")   