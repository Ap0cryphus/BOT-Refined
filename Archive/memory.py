import sqlite3

db = sqlite3.connect("memory.db")

db.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    user_message TEXT,
    bot_response TEXT
)
""")

db.commit()
db.close()

print("Database initialized.")