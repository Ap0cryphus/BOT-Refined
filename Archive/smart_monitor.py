from pywinauto import Application
import time

BOT_NAME = "jarvis"

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

win = app.top_window()

seen = set()

print("Watching room...")

while True:

    for ctrl in win.descendants():

        try:

            if ctrl.element_info.control_type == "Text":

                txt = ctrl.window_text().strip()

                if txt and txt not in seen:

                    seen.add(txt)

                    if BOT_NAME in txt.lower():

                        print("\nBOT TRIGGERED:")
                        print(txt)

        except:
            pass

    time.sleep(2)