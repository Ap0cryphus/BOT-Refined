from pywinauto import Application
import ollama
import pyautogui
import time

try:

    print("Connecting to Notepad...")

    app = Application(backend="uia").connect(
        title_re=".*Notepad.*"
    )

    window = app.top_window()

    document = window.child_window(
        control_type="Document"
    )

    print("Reading text...")

    message = document.window_text()

    print("\nUser:")
    print(message)

    print("\nGenerating response...")

    response = ollama.chat(
        model="llama3",
        messages=[
            {
                "role": "user",
                "content": message
            }
        ]
    )

    reply = response["message"]["content"]

    print("\nBot:")
    print(reply)

    print("\nClick inside Notepad.")
    print("Typing starts in 10 seconds...")

    time.sleep(10)

    pyautogui.press("end")
    pyautogui.press("enter")
    pyautogui.press("enter")

    pyautogui.write(
        reply,
        interval=0.02
    )

    print("\nFinished")

except Exception as e:

    print("\nERROR:")
    print(e)