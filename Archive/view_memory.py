import sqlite3

db = sqlite3.connect("memory.db")

cursor = db.execute(
    "SELECT * FROM messages"
)

for row in cursor:
    print(row)

db.close()