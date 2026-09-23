from pywinauto import Application
import time

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

win = app.top_window()

seen = set()

print("Monitoring chat...")
print("Press Ctrl+C to stop.\n")

while True:

    current_messages = []

    for ctrl in win.descendants():

        try:

            if ctrl.element_info.control_type == "Text":

                txt = ctrl.window_text().strip()

                if txt:
                    current_messages.append(txt)

        except:
            pass

    for msg in current_messages:

        if msg not in seen:

            seen.add(msg)

            print("NEW:", msg)

    time.sleep(2)