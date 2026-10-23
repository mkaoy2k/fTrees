"""
Database Management Operations

This module contains core database operations for the admin interface.
"""
import re
import sqlite3
import db_utils as dbm
import logging
from dotenv import load_dotenv
import os

# Column definitions accepted by the admin "add column" action.
_COLUMN_DEFINITION = re.compile(r"^[A-Za-z0-9_ (),'.+-]+$")

# Load environment variables from .env file
load_dotenv(".env")

# Configure log for this module
log = logging.getLogger(__name__)
# Set log level from environment variable or default to WARNING
log_level = os.getenv('LOGGING', 'WARNING').upper()
log.setLevel(getattr(logging, log_level, logging.WARNING))

# Configure console handler for debug output
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
console_handler.setFormatter(formatter)
log.addHandler(console_handler)

def init_db_management():
    """Initialize database management"""
    try:
        log.debug("Initializing database management")
        return get_tables()
    except sqlite3.Error as e:
        log.error(f"Database error: {e}")
        return []

def get_table_structure(table_name):
    """Get the structure of a table"""
    try:
        with dbm.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({dbm.quote_ident(table_name)})")
            return cursor.fetchall()
    except (sqlite3.Error, ValueError) as e:
        log.error(f"Error getting table structure: {e}")
        return []

def drop_table(table_name):
    """Drop a table from the database"""
    try:
        with dbm.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"DROP TABLE IF EXISTS {dbm.quote_ident(table_name)}")
            conn.commit()
            return True
    except (sqlite3.Error, ValueError) as e:
        log.error(f"Error dropping table: {e}")
        return False

def init_admin_features():
    """Initialize admin features by adding necessary columns to user table"""
    try:
        with dbm.get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if password_hash column exists
            users = dbm.quote_ident(dbm.db_tables['users'])
            cursor.execute(f"PRAGMA table_info({users})")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Add password_hash column if it doesn't exist
            if 'password_hash' not in columns:
                cursor.execute(f"ALTER TABLE {users} ADD COLUMN password_hash TEXT")
            
            # Add salt column if it doesn't exist
            if 'salt' not in columns:
                cursor.execute(f"ALTER TABLE {users} ADD COLUMN salt TEXT")
            
            # Add is_admin column if it doesn't exist
            if 'is_admin' not in columns:
                cursor.execute(f"ALTER TABLE {users} ADD COLUMN is_admin INTEGER DEFAULT 0")
            
            conn.commit()
            return True
            
    except (sqlite3.Error, ValueError) as e:
        log.error(f"Error initializing admin features: {e}")
        return False


def add_column_if_not_exists(table_name, column_name, column_definition):
    """
    Add a column to the specified table if it doesn't exist
    
    Args:
        table_name (str): Name of the table
        column_name (str): Name of the column to add
        column_definition (str): Column definition (e.g., "TEXT NOT NULL DEFAULT 'US'")
    """
    try:
        if not _COLUMN_DEFINITION.fullmatch(column_definition or ""):
            log.error("Rejected column definition: %s", column_definition)
            return False
        with dbm.get_db_connection() as conn:
            cursor = conn.cursor()
            table = dbm.quote_ident(table_name)
            column = dbm.quote_ident(column_name)
            
            # Check if column exists
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [column[1] for column in cursor.fetchall()]
            
            if column_name not in columns:
                # Column doesn't exist, add it
                alter_table_sql = f"ALTER TABLE {table} ADD COLUMN {column} {column_definition}"
                cursor.execute(alter_table_sql)
                conn.commit()
                return True
            return True  # Column already exists
            
    except (sqlite3.Error, ValueError) as e:
        log.error(f"Error adding column: {e}")
        return False

def remove_column_if_exists(table_name, column_name):
    """
    Remove a column from a table if it exists
    
    Args:
        table_name (str): Name of the table
        column_name (str): Name of the column to remove
    """
    try:
        with dbm.get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if column exists
            table = dbm.quote_ident(table_name)
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [column[1] for column in cursor.fetchall()]
            
            if column_name in columns:
                # SQLite doesn't support DROP COLUMN directly, so we need to:
                # 1. Create a new table without the column
                # 2. Copy data from old table to new table
                # 3. Drop old table
                # 4. Rename new table to old table name
                
                # Get all columns except the one to remove
                columns_to_keep = [dbm.quote_ident(col) for col in columns if col != column_name]
                
                if not columns:
                    print(f"No columns found in table: {table_name}")
                    return False
                    
                staging = dbm.quote_ident(f"{table_name}_new")
                # Create new table with the same schema but without the column
                cursor.execute(f"CREATE TABLE {staging} AS SELECT {', '.join(columns_to_keep)} FROM {table} WHERE 1=0")
                
                # Copy data
                cursor.execute(f"INSERT INTO {staging} SELECT {', '.join(columns_to_keep)} FROM {table}")
                
                # Drop old table
                cursor.execute(f"DROP TABLE {table}")
                
                # Rename new table
                cursor.execute(f"ALTER TABLE {staging} RENAME TO {table}")
                
                conn.commit()
                return True
            return False  # Column doesn't exist
            
    except (sqlite3.Error, ValueError) as e:
        log.error(f"Error removing column: {e}")
        return False

def get_tables():
    """Get list of all tables in the database"""
    try:
        with dbm.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'")
            return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        log.error(f"Error getting tables: {e}")
        return []
