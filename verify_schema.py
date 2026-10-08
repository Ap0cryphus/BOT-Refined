import sqlite3
import os

# Create data directory if it doesn't exist
os.makedirs('data', exist_ok=True)

# Test database creation and schema validation
try:
    # Connect to database (this will create it if it doesn't exist)
    conn = sqlite3.connect('data/camfrog_bot.db')
    cursor = conn.cursor()
    
    # Test creating tables (these should work without error)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            gender TEXT,
            join_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_messages INTEGER DEFAULT 0,
            total_mic_grabs INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            first_join_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            message TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_mic BOOLEAN DEFAULT FALSE,
            message_length INTEGER DEFAULT 0,
            message_word_count INTEGER DEFAULT 0,
            is_positive BOOLEAN DEFAULT NULL,
            is_negative BOOLEAN DEFAULT NULL,
            sentiment_score REAL DEFAULT 0.0
        )
    """)
    
    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_timestamp ON chat_history(timestamp)")
    
    conn.commit()
    conn.close()
    
    print("✅ Database schema successfully validated")
    print("✅ All tables and indexes created without errors")
    
except Exception as e:
    print(f"❌ Error: {e}")