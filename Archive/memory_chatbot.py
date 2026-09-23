import sqlite3
import ollama

# Load previous conversations
db = sqlite3.connect("memory.db")

rows = db.execute(
    "SELECT user_message, bot_response FROM messages ORDER BY id DESC LIMIT 5"
)

messages = []

for user_msg, bot_msg in reversed(list(rows)):
    messages.append({
        "role": "user",
        "content": user_msg
    })

    messages.append({
        "role": "assistant",
        "content": bot_msg
    })

# Get new input
user_message = input("You: ")

messages.append({
    "role": "user",
    "content": user_message
})

# Ask AI
response = ollama.chat(
    model="llama3",
    messages=messages
)

bot_reply = response["message"]["content"]

print("\nBot:", bot_reply)

# Save conversation
db.execute(
    "INSERT INTO messages(user_message, bot_response) VALUES (?, ?)",
    (user_message, bot_reply)
)

db.commit()
db.close()