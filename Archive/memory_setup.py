import sqlite3

db = sqlite3.connect("memory.db")

db.execute("""
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    fact TEXT UNIQUE
)
""")

db.commit()
db.close()