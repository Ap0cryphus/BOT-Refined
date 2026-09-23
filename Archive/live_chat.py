from pywinauto import Application
import re
import time

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

win = app.top_window()

seen = set()

time_pattern = re.compile(r'^\d{1,2}:\d{2}\s?(AM|PM)$')

print("Watching chat...\n")

while True:

    texts = []

    for ctrl in win.descendants():

        try:
            if ctrl.element_info.control_type == "Text":

                text = ctrl.window_text().strip()

                if text:
                    texts.append(text)

        except:
            pass

    for i in range(len(texts) - 2):

        username = texts[i]
        timestamp = texts[i + 1]
        message = texts[i + 2]

        if time_pattern.match(timestamp):

            key = f"{username}|{timestamp}|{message}"

            if key not in seen:

                seen.add(key)

                print(f"\n[{timestamp}]")
                print(f"{username}: {message}")

    time.sleep(2)