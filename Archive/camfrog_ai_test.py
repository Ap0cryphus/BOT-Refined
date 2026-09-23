import requests
from pywinauto import Application
import pyautogui
import time

question = input("Question: ")

response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "llama3.2",
        "prompt": question,
        "stream": False
    }
)

answer = response.json()["response"]

print("\nAnswer:")
print(answer)

app = Application(backend="uia").connect(
    title_re=".*Fight Night.*"
)

win = app.top_window()
win.set_focus()

time.sleep(2)

# Click center of the Camfrog editor
pyautogui.click(1286, 1127)

time.sleep(1)

# Limit length for testing
short_answer = answer[:150]

pyautogui.write(short_answer, interval=0.02)

print("\nTyped into Camfrog.")