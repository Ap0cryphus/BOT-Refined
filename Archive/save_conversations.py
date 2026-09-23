import sqlite3

def save_conversation(user, bot):

    db = sqlite3.connect("memory.db")

    db.execute(
        "INSERT INTO messages(user_message, bot_response) VALUES (?, ?)",
        (user, bot)
    )

    db.commit()
    db.close()

save_conversation(
    "Hello",
    "Hi there!"
)

print("Conversation saved.")