import sqlite3
import ollama

user_message = input("You: ")

response = ollama.chat(
    model="llama3",
    messages=[
        {"role": "user", "content": user_message}
    ]
)

bot_reply = response["message"]["content"]

print("Bot:", bot_reply)

db = sqlite3.connect("memory.db")

db.execute(
    "INSERT INTO messages(user_message, bot_response) VALUES (?, ?)",
    (user_message, bot_reply)
)

db.commit()
db.close()