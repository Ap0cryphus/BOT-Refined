import ollama
import pyautogui
import time

with open("incoming.txt", "r") as file:
    message = file.read()

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

print(reply)

print("Click inside Notepad")

time.sleep(5)

pyautogui.write(reply, interval=0.02)