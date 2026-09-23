from pywinauto import Application
import ollama

print("Connecting to Notepad...")

app = Application(backend="uia").connect(
    title_re=".*Notepad.*"
)

window = app.top_window()

document = window.child_window(control_type="Document")

message = document.window_text()

print("\nUser:")
print(message)

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