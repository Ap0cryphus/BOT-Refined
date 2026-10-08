#!/usr/bin/env python3
"""
Final validation script for the enhanced Camfrog bot database schema
"""

import sqlite3
import os

def validate_database_schema():
    """Validate that all required tables and indexes have been created"""
    
    # Check if database file exists
    db_path = 'data/camfrog_bot.db'
    if not os.path.exists(db_path):
        print("❌ Database file does not exist")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"✅ Tables found: {tables}")
        
        expected_tables = ['users', 'chat_history', 'user_activity', 'chat_sessions', 'message_analysis']
        missing_tables = [table for table in expected_tables if table not in tables]
        
        if missing_tables:
            print(f"❌ Missing tables: {missing_tables}")
            return False
        else:
            print("✅ All required tables created successfully")
        
        # Check users table structure
        cursor.execute("PRAGMA table_info(users)")
        users_columns = [row[1] for row in cursor.fetchall()]
        print(f"✅ Users table columns: {users_columns}")
        
        # Check chat_history table structure
        cursor.execute("PRAGMA table_info(chat_history)")
        chat_columns = [row[1] for row in cursor.fetchall()]
        print(f"✅ Chat history table columns: {chat_columns}")
        
        # Check indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
        indexes = [row[0] for row in cursor.fetchall()]
        print(f"✅ Indexes found: {indexes}")
        
        # Validate that we have the required indexes
        expected_indexes = [
            'idx_users_username', 
            'idx_users_join_time',
            'idx_chat_history_timestamp',
            'idx_chat_history_username',
            'idx_chat_history_message_length',
            'idx_user_activity_timestamp',
            'idx_user_activity_user_id'
        ]
        
        missing_indexes = [index for index in expected_indexes if index not in indexes]
        
        if missing_indexes:
            print(f"❌ Missing indexes: {missing_indexes}")
            return False
        else:
            print("✅ All required indexes created successfully")
        
        conn.close()
        print("\n🎉 Database schema validation completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error validating database: {e}")
        return False

if __name__ == "__main__":
    print("Validating enhanced Camfrog bot database schema...")
    success = validate_database_schema()
    if success:
        print("\n✅ All validations passed - Database schema is correctly implemented")
    else:
        print("\n❌ Validation failed - Please check the implementation")