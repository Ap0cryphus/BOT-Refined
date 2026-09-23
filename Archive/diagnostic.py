from pywinauto import Application
import time

app = Application(backend="uia").connect(
    found_index=0,
    title_re=".*Players__L.*"
)
win = app.top_window()

print("Watching for kick/block messages... (have someone get kicked now)")
print("Press Ctrl+C to stop.\n")

seen = set()

while True:
    try:
        for ctrl in win.descendants():
            try:
                if ctrl.element_info.control_type == "Text":
                    text = ctrl.window_text().strip()
                    if not text:
                        continue
                    if len(text) > 80:
                        continue
                    if text in seen:
                        continue
                    seen.add(text)
                    # Print anything that looks like it could be a system message
                    if "kick" in text.lower() or "block" in text.lower():
                        print(f"  FOUND: type='Text' | class='{ctrl.class_name()}' | text='{text}' | rect={ctrl.rectangle()}")
                    # Also print ALL short new text so we can spot the format
                    elif len(text) < 40:
                        print(f"  new:   type='Text' | class='{ctrl.class_name()}' | text='{text}' | rect={ctrl.rectangle()}")
            except:
                pass
        time.sleep(0.5)
    except KeyboardInterrupt:
        break   