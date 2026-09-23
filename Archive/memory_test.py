import sqlite3

db = sqlite3.connect("memory.db")

cursor = db.execute(
    "SELECT user_message, bot_response FROM messages"
)

for row in cursor:
    print(row)

db.close()