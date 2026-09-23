import ollama
import pyautogui
import time

last_message = ""

print("Watcher Bot Started")

while True:

    with open("incoming.txt", "r") as file:
        current_message = file.read().strip()

    if current_message != last_message:

        print("\nNew Message:", current_message)

        response = ollama.chat(
            model="llama3",
            messages=[
                {
                    "role": "user",
                    "content": current_message
                }
            ]
        )

        reply = response["message"]["content"]

        print("\nBot:", reply)

        time.sleep(3)

        pyautogui.write(reply, interval=0.02)

        last_message = current_message

    time.sleep(1)