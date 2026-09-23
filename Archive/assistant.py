import sqlite3
import ollama

while True:

    user_message = input("You: ")

    if user_message.lower() == "exit":
        break

    db = sqlite3.connect("memory.db")

    rows = db.execute(
        "SELECT user_message, bot_response FROM messages ORDER BY id DESC LIMIT 10"
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

    messages.append({
        "role": "user",
        "content": user_message
    })

    response = ollama.chat(
        model="llama3",
        messages=messages
    )

    bot_reply = response["message"]["content"]

    print("\nBot:", bot_reply)

    db.execute(
        "INSERT INTO messages(user_message, bot_response) VALUES (?, ?)",
        (user_message, bot_reply)
    )

    db.commit()
    db.close()