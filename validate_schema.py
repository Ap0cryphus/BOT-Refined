import sqlite3
import os

# Check if database file exists
db_path = 'data/camfrog_bot.db'
if not os.path.exists(db_path):
    print("Database file does not exist")
else:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print("Tables in database:")
        for table in tables:
            print(f"  - {table[0]}")
            
        # Check users table structure
        print("\nUsers table structure:")
        cursor.execute("PRAGMA table_info(users)")
        users_columns = cursor.fetchall()
        for col in users_columns:
            print(f"  {col[1]} ({col[2]})")
            
        # Check chat_history table structure
        print("\nChat history table structure:")
        cursor.execute("PRAGMA table_info(chat_history)")
        chat_columns = cursor.fetchall()
        for col in chat_columns:
            print(f"  {col[1]} ({col[2]})")
        
        # Check indexes
        print("\nIndexes in database:")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
        indexes = cursor.fetchall()
        for index in indexes:
            print(f"  - {index[0]}")
            
        conn.close()
        print("\nDatabase schema validation completed successfully!")
        
    except Exception as e:
        print(f"Error validating database: {e}")