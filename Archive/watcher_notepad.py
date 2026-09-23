from pywinauto import Application
import ollama
import pyautogui
import time

last_text = ""

print("Watcher Started")

while True:

    try:

        app = Application(
            backend="uia"
        ).connect(
            title_re=".*Notepad.*"
        )

        window = app.top_window()

        document = window.child_window(
            control_type="Document"
        )

        current_text = document.window_text()

        if current_text != last_text:

            print("\nNew Change Detected")

            response = ollama.chat(
                model="llama3",
                messages=[
                    {
                        "role": "user",
                        "content": current_text
                    }
                ]
            )

            reply = response["message"]["content"]

            print("\nBot:")
            print(reply)

            print(
                "\nClick inside Notepad. "
                "Typing starts in 5 seconds..."
            )

            time.sleep(5)

            pyautogui.press("end")
            pyautogui.press("enter")
            pyautogui.press("enter")

            pyautogui.write(
                reply,
                interval=0.02
            )

            last_text = current_text

        time.sleep(2)

    except Exception as e:

        print("Error:", e)

        time.sleep(5)