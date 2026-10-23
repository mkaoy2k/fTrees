"""
db_utils.py - Database Utility Module

This module provides functions for interacting with an SQLite database,
managing database operations for the family tree system.
"""

import os
import re
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union
import funcUtils as fu
import auth_utils as au
import csv
import json
from datetime import datetime
from dotenv import load_dotenv
import logging

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

# Database configuration
database_name = os.getenv("DB_NAME", "data/family.db")
db_path = os.path.join(os.path.dirname(__file__), database_name)

db_tables = {
    "users": os.getenv("TBL_USERS", "users"),
    "members": os.getenv("TBL_MEMBERS", "members"),
    "relations": os.getenv("TBL_RELATIONS", "relations"),
    "families": os.getenv("TBL_FAMILIES", "families"),
    "mirrors": os.getenv("TBL_MIRRORS", "mirrors")
}

# Subscriber states ~is_active
# Subscription status values for users
# Used in the 'is_active' field of the mirdb_table['users'] table
Subscriber_State = {
    'active': 1,    # User is active and can access the system
    'pending': 0,   # User is pending approval/activation
    'inactive': -1  # User is inactive/cannot access the system
}

# User role values
# Used in the 'is_admin' field of the mirdb_table['users'] table
User_State = {
    'p_admin': 2,    # Platform Administrator with full access
    'f_admin': 1,     # Family Administrator with full access
    'f_member': 0    # Family Member with limited access
}

# Member codes in mirrors table
# Used in the 'status' field of the db_table['mirrors'] table
Member_Status = {
    'single': 0,    # single
    'married': 1,   # married
    'together': 2   # live-together
}
# Used in the 'relation' vs parents of the db_table['mirrors'] table
Member_Relation = {
    'bio': 0,    # biological
    'adopt': 1,   # adopted
    'step': 2   # step
}
# Used in the 'sex' field of the db_table['mirrors'] table
Member_Sex = {
    'male': 0,    # male
    'female': 1,   # female
    'inlaw-male': 2,   # inlaw-male
    'inlaw-female': 3   # inlaw-female
}

# Used in the 'relation_type' field of the db_table['relations'] table
Relation_Type = {
    'child': 'child',   # biological child
    'child ai': 'child adopted within the family',   # adopted child within the family
    'child ao': 'child adopted from another family',   # adopted child from another family
    'child step': 'child step',   # step child
    'parent': 'parent',   # biological parent
    'parent ai': 'parent adopted within the family',   # adopted parent within the family
    'parent ao': 'parent adopted from another family',   # adopted parent from another family
    'parent step': 'parent step',   # step parent
    'sibling': 'sibling',   # biological sibling
    'spouse': 'spouse',    # married spouse 
    'spouse cu': 'spouse civil union',   # civil union spouse
    'spouse divorced': 'spouse divorced',   # divorced spouse
    'spouse dp': 'spouse domestic partnership',   # domestic partnership spouse
    'spouse separated': 'spouse separated',   # separated spouse
    'other': 'other'   # other
}
# Log database configuration
log.debug("Database configuration:")
log.debug(f"- Database path: {db_path}")
log.debug(f"- Log level: {log_level}")
log.debug(f"- Database tables: {db_tables}")
log.debug("Database module initialized")

def get_db_connection() -> sqlite3.Connection:
    """
    Create and return a database connection.
    
    Returns:
        sqlite3.Connection: A connection to the SQLite database
    """
    conn = sqlite3.connect(database_name)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    return conn

def init_db() -> None:
    """
    Initialize the database by creating necessary tables and triggers if they don't exist.
    Sets up the database schema for users, members, and relations tables.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Database optimization settings
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA temp_store = MEMORY")
        
        # Create users table
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {db_tables['users']} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            is_active INTEGER DEFAULT -1,
            l10n TEXT DEFAULT 'US',
            token TEXT DEFAULT '',
            is_admin INTEGER DEFAULT 0,
            family_id INTEGER DEFAULT 0,
            member_id INTEGER DEFAULT 0,
            password_hash TEXT DEFAULT '',
            salt TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create members table
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {db_tables['members']} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            family_id INTEGER,
            alias TEXT,
            email TEXT,
            url TEXT,
            born DATE DEFAULT '0000-00-00',
            died DATE DEFAULT '0000-00-00',
            sex TEXT,
            gen_order INTEGER,
            dad_id INTEGER,
            mom_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create relations table to store relationships between 
        # member and partner members. The relation field is used to 
        # store the type of relationship (e.g., 'spouse', 'parent').
        # It means that member has partner as `parent, for example.
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {db_tables["relations"]} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_family_id INTEGER,  -- Original family ID before joining
            original_name TEXT,       -- Original name before marriage
            partner_id INTEGER,       -- Reference to the partner member
            member_id INTEGER,        -- Reference to this member
            relation TEXT,            -- Type of relationship (e.g., 'spouse', 'parent')
            dad_name TEXT,            -- Father's name
            mom_name TEXT,            -- Mother's name
            join_date DATE DEFAULT '0000-00-00', -- Date when relationship started
            end_date DATE DEFAULT '0000-00-00', -- Date when relationship ended (if applicable)
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
                
        # Create families table
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {db_tables["families"]} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            background TEXT,
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create indexes to improve query performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_name ON members(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_family ON members(family_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_email ON members(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_member ON relations(member_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_partner ON relations(partner_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_original ON relations(original_family_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_families_name ON families(name)")
        
        # Create triggers to automatically update timestamps on record updates
        cursor.execute(f"""
        CREATE TRIGGER IF NOT EXISTS update_users_timestamp
        AFTER UPDATE ON {db_tables["users"]}
        FOR EACH ROW
        BEGIN
            UPDATE {db_tables["users"]} SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_member ON relations(member_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_partner ON relations(partner_id)")
        
        # Create triggers to automatically update timestamps on record updates
        cursor.execute(f"""
        CREATE TRIGGER IF NOT EXISTS update_users_timestamp
        AFTER UPDATE ON {db_tables["users"]}
        FOR EACH ROW
        BEGIN
            UPDATE {db_tables["users"]} SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
        """)
        cursor.execute(f"""
        CREATE TRIGGER IF NOT EXISTS update_members_timestamp
        AFTER UPDATE ON {db_tables["members"]}
        FOR EACH ROW
        BEGIN
            UPDATE {db_tables["members"]} SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
        """)
        
        cursor.execute(f"""
        CREATE TRIGGER IF NOT EXISTS update_relations_timestamp
        AFTER UPDATE ON {db_tables["relations"]}
        FOR EACH ROW
        BEGIN
            UPDATE {db_tables["relations"]} SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
        """)

        cursor.execute(f"""
        CREATE TRIGGER IF NOT EXISTS update_families_timestamp
        AFTER UPDATE ON {db_tables["families"]}
        FOR EACH ROW
        BEGIN
            UPDATE {db_tables["families"]} SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
        """)
        
        # Create mirrors table
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {db_tables["mirrors"]} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Name TEXT NOT NULL,
            Aka TEXT,
            Sex INTEGER,
            Born DATE DEFAULT '0000-01-01',
            Died DATE DEFAULT '0000-01-01',
            Dad TEXT,
            Mom TEXT,
            Relation INTEGER DEFAULT 0,
            Spouse TEXT,
            Married DATE DEFAULT '0000-01-01',
            'Order' INTEGER DEFAULT 0,
            Href TEXT,
            Status INTEGER DEFAULT 0
        )    
        """)
        
        # Create password_reset_tokens table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
        )
        """)
        
        # Create index on token for faster lookups
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_reset_token ON password_reset_tokens(token)
        """)
        
        # Create index on email for faster lookups
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_reset_email ON password_reset_tokens(email)
        """)
        
        # Create index on expires_at for cleanup operations
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_reset_expires ON password_reset_tokens(expires_at)
        """)
        
        # Create index on name for faster lookups
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_mirrors_name ON {db_tables["mirrors"]}(Name)
        """)
            
        # Create index on generation order for sorting
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_mirrors_order ON {db_tables["mirrors"]}('Order')
        """)

        migrate_plaintext_reset_tokens(conn)
        conn.commit()

def migrate_plaintext_reset_tokens(conn) -> int:
    """Hash leftover plaintext password-reset tokens in place.

    Existing email links still work: validation hashes the presented token
    and compares it to the stored digest. Expiry and the used flag are kept.
    Rows that already store a SHA-256 hex digest are skipped.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, token FROM password_reset_tokens")
    updated = 0
    for row in cursor.fetchall():
        token = row["token"]
        if token and not au.is_stored_reset_token(token):
            cursor.execute(
                "UPDATE password_reset_tokens SET token = ? WHERE id = ?",
                (au.hash_reset_token(token), row["id"]),
            )
            updated += 1
    return updated

def add_subscriber(email: str, token: str, lang: str = None) -> Tuple[bool, str]:
    """
    Add a new subscriber with pending status or 
    update an existing one with active status.
    
    Args:
        email: The email address of the subscriber
        token: Verification token for the subscription
        lang: Optional language/locale code (e.g., 'en')
        
    Returns:
        Tuple[bool, str]: (success status, error message if any)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if email already exists
            cursor.execute(f"""
                SELECT id FROM {db_tables['users']} 
                WHERE email = ?
            """, (email,))
            
            result = cursor.fetchone()
            
            if result:
                # Update existing user
                cursor.execute(f"""
                    UPDATE {db_tables['users']} 
                    SET token = ?, is_active = ?, l10n = ?,
                    updated_at = CURRENT_TIMESTAMP
                    WHERE email = ?
                """, (token, Subscriber_State['active'], 
                      lang, email))
            else:
                # Insert new user
                cursor.execute(f"""
                    INSERT INTO {db_tables['users']} 
                    (email, token, is_active, l10n) 
                    VALUES (?, ?, ?, ?)
                """, (email, token, Subscriber_State['pending'], lang))
            
            conn.commit()
            return True, ""
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        return False, error_msg
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        return False, error_msg

def remove_subscriber(email: str) -> bool:
    """
    Unsubscribe an email address by setting its status to inactive.
    
    Args:
        email: The email address to unsubscribe
        
    Returns:
        bool: True if the record was successfully updated, False otherwise
    """
    if not email or not isinstance(email, str):
        log.warning("Invalid email address provided to remove_subscriber")
        return False
        
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # First, check if the email exists and is active
            cursor.execute(f"""
                SELECT id, is_active FROM {db_tables['users']} 
                WHERE email = ?
            """, (email,))
            
            result = cursor.fetchone()
            if not result:
                log.warning(f"Email not found: {email}")
                return False
                
            # If already inactive, no need to update
            if result['is_active'] == Subscriber_State['inactive']:
                log.debug(f"Email already unsubscribed: {email}")
                return True
                
            # Update status to inactive
            cursor.execute(f"""
                UPDATE {db_tables['users']} 
                SET is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE email = ?
            """, (Subscriber_State['inactive'], email))
            
            conn.commit()
            
            if cursor.rowcount > 0:
                log.debug(f"Successfully unsubscribed: {email}")
                return True
            
            log.warning(f"No records updated when unsubscribing: {email}")
            return False
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        return False
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        return False

def verify_token(email: str, token: str) -> bool:
    """
    Verify if the provided token is valid for the given email address.
    
    Args:
        email: The email address to verify
        token: The verification token to check
        
    Returns:
        bool: True if the token is valid, False otherwise
    """
    if not email or not token:
        log.warning("Email or token not provided to verify_token")
        return False
        
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id FROM {db_tables['users']} 
                WHERE email = ? 
                AND token = ? 
                AND is_active = ?
            """, (email, token, Subscriber_State['active']))
            
            result = cursor.fetchone() is not None
            if result:
                log.debug(f"Token verified for email: {email}")
            else:
                log.warning(f"Token verification failed for email: {email}")
                
            return result
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        return False
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        return False

def get_subscribers(state: str = 'active', lang: str = None) -> List[Dict[str, Any]]:
    """
    Fetch subscribers from the database based on their status and optional language filter.
    
    Args:
        state: Filter subscribers by state. Possible values:
            - 'active': only active subscribers (default)
            - 'inactive': only inactive subscribers
            - 'pending': only pending subscribers
            - 'all': all subscribers regardless of state
        lang: Optional language code to filter subscribers by language (e.g., 'en', 'zh-TW')
    
    Returns:
        List[Dict[str, Any]]: A list of subscriber records, where each record is a dictionary
        with keys: id, email, token, is_active, l10n, created_at, updated_at
        
    Raises:
        ValueError: If an invalid state is provided
        sqlite3.Error: If there's a database error
    """
    # Validate state parameter
    valid_states = ['active', 'inactive', 'pending', 'all']
    if state not in valid_states:
        error_msg = f"Invalid state '{state}'. Must be one of: {', '.join(valid_states)}"
        log.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        # Build the base query
        query = f"""
            SELECT * 
            FROM {db_tables['users']}
            WHERE 1=1
        """
        
        params = []
        
        # Add state condition if not 'all'
        if state != 'all':
            query += " AND is_active = ?"
            params.append(Subscriber_State[state])
        
        # Add language filter if provided
        if lang:
            query += " AND l10n = ?"
            params.append(lang)
        
        # Always order by creation date, newest first
        query += " ORDER BY created_at DESC"
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            # if no subscribers found, return empty list
            if cursor.rowcount == 0:
                log.debug(f"No subscribers found with state='{state}'" + 
                        (f" and language='{lang}'" if lang else ""))
                return []
            subscribers = [dict(row) for row in cursor.fetchall()]
            log.debug(f"Fetched {len(subscribers)} subscribers with state='{state}'" + 
                    (f" and language='{lang}'" if lang else ""))
            return subscribers
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise

def get_subscriber(email: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single user record by email address.
    
    This function queries the database for a user record based on the email address.
    If a matching user is found, returns a dictionary containing the user information;
    otherwise, returns None.
    
    Args:
        email: The email address to query (case-sensitive)
        
    Returns:
        Optional[Dict[str, Any]]: A dictionary containing user information if found, 
        None otherwise. The dictionary includes the following keys:
            - id: Unique user identifier (int)
            - email: Email address (str)
            - token: Verification token (str or None)
            - is_active: Account status (int, see Subscriber_State)
            - l10n: Language/locale code (str or None)
            - created_at: Creation timestamp (str in ISO format)
            - updated_at: Last update timestamp (str in ISO format)
            
    Raises:
        ValueError: If email is empty or not a string
        sqlite3.Error: If there's a database error
    """
    if not email or not isinstance(email, str):
        error_msg = "Email must be a non-empty string"
        log.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT * FROM {db_tables['users']}
                WHERE email = ?
                LIMIT 1
            """, (email,))
            
            result = cursor.fetchone()
            
            if result:
                user_data = dict(result)
                log.debug(f"Retrieved user: {user_data['email']} (ID: {user_data['id']})")
                return user_data
                
            log.debug(f"No user found with email: {email}")
            return None
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise

def delete_subscriber(email: str) -> bool:
    """
    Permanently delete a subscriber from the database by their email address.
    
    This function will remove all records associated with the subscriber's email
    from the users table. 
    Use with caution as this action cannot be undone.
    
    Args:
        email: The email address of the subscriber to delete (case-sensitive)
        
    Returns:
        bool: True if the subscriber was successfully deleted, False if the email
              was not found or if an error occurred
              
    Raises:
        ValueError: If email is empty or not a valid string
        sqlite3.Error: If there's a database error during deletion
    """
    # Validate email
    if not email or not isinstance(email, str):
        error_msg = "Email must be a non-empty string"
        log.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # First, verify the subscriber exists and get their ID for logging
            cursor.execute(f"""
                SELECT id FROM {db_tables['users']} 
                WHERE email = ?
                LIMIT 1
            """, (email,))
            
            result = cursor.fetchone()
            if not result:
                log.warning(f"Cannot delete: Subscriber with email '{email}' not found")
                return False
                
            user_id = dict(result).get('id')
            
            # Perform the deletion
            cursor.execute(f"""
                DELETE FROM {db_tables['users']} 
                WHERE email = ?
            """, (email,))
            
            rows_affected = cursor.rowcount
            conn.commit()
            
            if rows_affected > 0:
                log.debug(f"Successfully deleted subscriber: {email} (ID: {user_id})")
                return True
                
            log.warning(f"No rows affected when deleting subscriber: {email}")
            return False
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise

def insert_user(user_data: Dict[str, Any]) -> int:
    """
    Insert a new user into the db_table['users'] table by id.
    This function is used for importing members from a CSV/JSON
    file. All the fields except `updated_at` can be imported.
    
    Args:
        user_data: Dictionary containing user information,
        see db_table['users'] for details.
        
    Returns:
        int: A positive integer ID of the inserted user. 
        Zero if failed.
        
    Raises:
        ValueError: If user_data is not a dictionary or if id is invalid.
        sqlite3.Error: If there is a database error.
    """
    try:
        if not isinstance(user_data, dict):
            error_msg = f"Invalid user data: {user_data}. Must be a dictionary."
            log.error(error_msg)
            raise ValueError(error_msg)
        id = user_data.get('id')
        if not id or not isinstance(id, int) or id <= 0:
            error_msg = f"Invalid user data: {user_data}. Invalid id."
            log.error(error_msg)
            raise ValueError(error_msg)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                INSERT INTO {db_tables['users']} (
                    id, email, password_hash, salt, 
                    is_admin, is_active, l10n, token,
                    created_at, family_id, member_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_data['id'],
                user_data['email'],
                user_data['password_hash'],
                user_data['salt'],
                user_data.get('is_admin', User_State['f_member']),
                user_data.get('is_active', Subscriber_State['inactive']),
                user_data.get('l10n', 'US'),
                user_data.get('token'),
                user_data.get('created_at'),
                user_data.get('family_id'),
                user_data.get('member_id')
            ))
            if cursor.rowcount > 0:
                log.debug(f"Successfully inserted user: {user_data['email']} (ID: {user_data['id']})")
                conn.commit()
                return user_data['id']
            else:
                log.debug(f"Failed to insert user: {user_data['email']} (ID: {user_data['id']})")
                return 0
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    
def add_or_update_user(
    email: str,
    password: str,
    user_data: Dict[str, Any],
    update: bool = False) -> Tuple[bool, str]:
    """
    Add a new user or update an existing user to the 
    db_table['users'] table.
    If the user already exists, determine whether to update 
    based on the `update` parameter.
    
    Args:
        email: The user's email address (required)
        password: The user's password (required)
        user_data (optional): Other user data, may include all the fields 
            in the db_table['users'] table, including:
            - is_admin: The user's role, must be one of the following:
                - User_State['p_admin']
                - User_State['f_admin']
                - User_State['f_member']
            - is_active: The user's active status, must be one of the following:
                - Subscriber_State['active']
                - Subscriber_State['inactive']
            - l10n: The user's language, must be one of the following:
                - 'US'
            - family_id: The user's family ID, must be an integer
            - member_id: The user's member ID, must be an integer
        update: If True, update the user when the user already exists; 
        if False, return an error when the user already exists
    
    Returns:
        Tuple[bool, str]: (success status, error message if any)
    
    Raises:
        ValueError: If email is empty or not a valid string
        sqlite3.Error: If there's a database error
        Exception: If an unexpected error occurs
    
    Example:
        >>> add_or_update_user("test@example.com", "password", update=False, user_data={"password": "password"})
        (True, "User added successfully")
    """
    if not email or not isinstance(email, str) or '@' not in email:
        return False, "Invalid email address"
    
    if not password or not isinstance(password, str):
        return False, "Invalid password"
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if user already exists
            cursor.execute(f"""
                SELECT id FROM {db_tables['users']} 
                WHERE email = ?
            """, (email,))
            
            existing_user = cursor.fetchone()
            
            if existing_user:
                if not update:
                    return False, "User already exists"
                    
                # Update existing user
                update_fields = []
                params = []
                
                # valid fields allowed to update
                for field in ['password', 'is_admin', 
                              'family_id', 'member_id',
                              'l10n', 'is_active']:
                    if field in user_data and user_data[field] is not None:
                        update_fields.append(f"{field} = ?")
                        params.append(user_data[field])
                
                if not update_fields:
                    return False, "No fields to update"
                    
                query = f"""
                    UPDATE {db_tables['users']}
                    SET {', '.join(update_fields)}
                    WHERE email = ?
                """
                params.append(email)
                
                cursor.execute(query, params)
                conn.commit()
                
                log.debug(f"User updated successfully: {email}")
                return True, ""
                
            else:
                # Create a new user
                user_fields = {
                    'is_admin': user_data['is_admin'] if 'is_admin' in user_data else User_State['f_member'],
                    'is_active': user_data['is_active'] if 'is_active' in user_data else Subscriber_State['inactive'],
                    'l10n': user_data['l10n'] if 'l10n' in user_data else 'US',
                    'family_id': user_data['family_id'] if 'family_id' in user_data else 0,
                    'member_id': user_data['member_id'] if 'member_id' in user_data else 0,
                }
                au.create_user(email, password, 
                    role=user_fields['is_admin'],
                    is_active=user_fields['is_active'],
                    l10n=user_fields['l10n'],
                    family_id=user_fields['family_id'],
                    member_id=user_fields['member_id'])
                
    except sqlite3.IntegrityError:
        error_msg = "Database integrity error"
        log.error(error_msg, exc_info=True)
        return False, error_msg
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        return False, error_msg
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        return False, error_msg

def get_users(role: str = 'all') -> List[Dict[str, Any]]:
    """
    Retrieve users from the `users` table depending the roles or `all`.
    The roles are: `p_admin`, `f_admin`, `f_member`.
    The order of the users is by id in ascending order.
    
    Returns:
        List[Dict[str, Any]]: A list of user dictionaries, 
        where each dictionary contains the user's data including all the fields.
        
    Raises:
        sqlite3.Error: If there's a database error while fetching users
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if role == 'all':
                cursor.execute(f"""
                               SELECT * FROM {db_tables['users']}
                               ORDER BY id ASC
                               """)
            else:
                cursor.execute(f"""
                               SELECT * FROM {db_tables['users']}
                               WHERE is_admin IN ({role})
                               ORDER BY id ASC
                               """)
            
            # Get column names from cursor description
            columns = [column[0] for column in cursor.description]
            
            # Convert each row to a dictionary
            users = []
            for row in cursor.fetchall():
                users.append(dict(zip(columns, row)))
                
            log.debug(f"Retrieved {len(users)} users from database")
            return users
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise

def delete_user(user_id: int) -> bool:
    """
    Permanently delete a user from the database by their ID.
    
    This function will remove all records associated with the user from the users table.
    Use with caution as this action cannot be undone.
    
    Args:
        user_id: The unique identifier of the user to delete (must be a positive integer)
        
    Returns:
        bool: True if the user was successfully deleted, False otherwise
        
    Raises:
        ValueError: If user_id is not a positive integer
        sqlite3.Error: If there's a database error during deletion
    """
    # Validate user_id
    if not isinstance(user_id, int) or user_id <= 0:
        error_msg = f"Invalid user ID: {user_id}. Must be a positive integer."
        log.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # First, verify the user exists
            cursor.execute(f"""
                SELECT id, email FROM {db_tables['users']} 
                WHERE id = ?
                LIMIT 1
            """, (user_id,))
            
            user = cursor.fetchone()
            if not user:
                log.warning(f"Cannot delete: User with ID {user_id} not found")
                return False
                
            # Store email for logging before deletion
            user_email = dict(user).get('email', 'unknown')
            
            # Perform the deletion
            cursor.execute(f"""
                DELETE FROM {db_tables['users']} 
                WHERE id = ?
            """, (user_id,))
            
            rows_affected = cursor.rowcount
            conn.commit()
            
            if rows_affected > 0:
                log.debug(f"Successfully deleted user: {user_email} (ID: {user_id})")
                return True
            
            log.warning(f"No rows affected when deleting user ID: {user_id}")
            return False
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    
def insert_member(member_data: Dict[str, Any]) -> int:
    """
    Insert a new member into the db_table['members'] table by id.
    This function is used for importing members from a CSV/JSON
    file. All the fields except `updated_at` can be imported.
    
    Args:
        member_data: Dictionary containing member information,
        see db_tables['members'] for details. 
        
    Returns:
        int: A positive integer ID of the inserted member. 
        Zero if failed.
        
    Raises:
        ValueError: If member_data is not a dictionary or if id is invalid.
        sqlite3.Error: If there is a database error.
    """
    try:
        if not isinstance(member_data, dict):
            error_msg = f"Invalid member data: {member_data}. Must be a dictionary."
            log.error(error_msg)
            raise ValueError(error_msg)
        id = member_data.get('id')
        if not id or not isinstance(id, int) or id <= 0:
            error_msg = f"Invalid member data: {member_data}. Invalid id."
            log.error(error_msg)
            raise ValueError(error_msg)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                INSERT INTO {db_tables['members']} (
                    id, name, family_id, born, sex, gen_order,
                    alias, email, url, died, dad_id, mom_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                member_data['id'],
                member_data['name'],
                member_data['family_id'],
                member_data['born'],
                member_data['sex'],
                member_data['gen_order'],
                member_data.get('alias'),
                member_data.get('email'),
                member_data.get('url'),
                member_data.get('died'),
                member_data.get('dad_id'),
                member_data.get('mom_id'),
                member_data.get('created_at')
            ))
            if cursor.rowcount > 0:
                log.debug(f"Successfully inserted member: {member_data['name']} (ID: {member_data['id']})")
                conn.commit()
                return member_data['id']
            else:
                log.debug(f"Failed to insert member: {member_data['name']} (ID: {member_data['id']})")
                return 0
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    
def add_or_update_member(member_data: Dict[str, Any], update: bool = False) -> int:
    """
    Add a new member to the database or update an existing one.
    
    This function inserts a new member record into the members table with the provided data.
    If update is True and a member with the same name, birth date, and generation order exists,
    it will update the existing record instead of creating a new one.
    
    Args:
        member_data: Dictionary containing member information,
        see db_tables['members'] for details
        update (bool): If True, update existing member with matching name, born, and gen_order
        
    Returns:
        int: The ID of the created or updated member
        
    Raises:
        ValueError: If required fields are missing or data is invalid
        sqlite3.IntegrityError: If a database integrity constraint is violated
        sqlite3.Error: For other database-related errors
        
    Example:
        >>> member_data = {
        ...     'name': 'Smith',
        ...     'born': '1990-01-01',
        ...     'gen_order': 1,
        ...     'email': 'john@example.com'
        ... }
        >>> member_id = add_or_update_member(member_data, True)
    """
    # Validate required fields
    required_fields = ['name', 'born', 'gen_order']
    missing_fields = [field for field in required_fields if field not in member_data]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if member with same name, born, and gen_order exists
            cursor.execute(f"""
                SELECT id FROM {db_tables['members']}
                WHERE name = ? AND born = ? AND gen_order = ?
            """, (member_data['name'], member_data['born'], member_data['gen_order']))
            
            existing_member = cursor.fetchone()
            
            if existing_member and update:
                # Update existing member
                member_id = existing_member['id']
                update_fields = []
                params = []
                
                # Build SET clause for update - include all fields including required ones
                for field, value in member_data.items():
                    if value is not None:
                        update_fields.append(f"{field} = ?")
                        params.append(value)
                
                if not update_fields:
                    log.debug("No fields to update for existing member")
                    return member_id
                
                # Add member_id to params for WHERE clause
                params.append(member_id)
                
                # Build and execute update query
                update_sql = f"""
                    UPDATE {db_tables['members']}
                    SET {', '.join(update_fields)}
                    WHERE id = ?
                """
                
                cursor.execute(update_sql, params)
                conn.commit()
                
                log.debug(f"Updated existing member ID {member_id}: {member_data.get('name')}")
                return member_id
            
            elif existing_member and not update:
                raise ValueError(
                    f"Member '{member_data['name']}' with birth date {member_data['born']} "
                    f"and generation order {member_data['gen_order']} already exists. "
                    "Set update=True to update existing member."
                )
            
            # Insert new member
            # Prepare fields and values for insert
            fields = []
            placeholders = []
            values = []
            
            # valid fields to add
            valid_fields = ['name', 'born', 'gen_order', 'email', 'alias', 'sex', 'generation', 'family_id', 'url']
            for field, value in member_data.items():
                if value is not None and field in valid_fields:
                    fields.append(field)
                    placeholders.append('?')
                    values.append(value)
            
            # Add created_at timestamp
            fields.extend(['created_at'])
            placeholders.extend(["datetime('now')"])
            
            # Build and execute insert query
            insert_sql = f"""
                INSERT INTO {db_tables['members']} ({', '.join(fields)})
                VALUES ({', '.join(placeholders)})
            """
            
            cursor.execute(insert_sql, values)
            member_id = cursor.lastrowid
            conn.commit()
            
            log.debug(f"Added new member: {member_data.get('name')} (ID: {member_id})")
            return member_id
            
    except sqlite3.IntegrityError as e:
        if "FOREIGN KEY" in str(e):
            error_msg = (
                "Invalid parent ID provided. The specified father or mother "
                "does not exist in the database."
            )
        else:
            error_msg = f"Database integrity error in {fu.get_function_name()}"
        log.error("%s", error_msg, exc_info=e)
        raise ValueError(error_msg) from e
        
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise

def add_related_member(
    member_data: Dict[str, Any],
    partner_id: int,
    relation: str,
    join_date: str,
    original_family_id: int = 0,
    original_name: str = None,
    end_date: str = None
) -> Tuple[int, int]:
    """
    Add a new member and establish a relationship with 
    an existing partner member.
    
    This function performs the following operations in a single 
    transaction:
    1. Adds a new member to the database using the provided member_data
    2. Creates a relationship record between the new member and an existing member
    3. Optionally updates the new member's family ID and/or name
    
    Args:
        member_data: Dictionary containing the new member's data. See add_or_update_member() for
            required and optional fields.
        partner_id: ID of the existing member to create a relationship with.
            Must be a positive integer.
        relation: Type of relationship to establish. 
            Common values see Relation_Type.
        join_date: Start date of the relationship in YYYY-MM-DD format.
        original_family_id: (Optional) Original family ID 
            to set for the new member.
        original_name: (Optional) Original name to set for 
            the new member.
        end_date: (Optional) End date of the relationship in 
            YYYY-MM-DD format.
            Used for terminated relationships (e.g., divorce).
        
    Returns:
        Tuple[int, int]: A tuple containing (new_member_id, relation_id)
        
    Raises:
        ValueError: If required parameters are missing or invalid.
        sqlite3.IntegrityError: If a database integrity constraint is violated.
        sqlite3.Error: For other database-related errors.
        
    Example:
        >>> new_member = {
        ...     'name': 'Smith',
        ...     'sex': 'F',
        ...     'born': '1990-05-15',
        ...     'email': 'jane@example.com'
        ... }
        >>> member_id, rel_id = add_related_member(
        ...     member_data=new_member,
        ...     partner_id=123,
        ...     relation='spouse',
        ...     join_date='2015-06-20',
        ...     original_family_id=123,
        ...     original_name='John Doe'
        ... )
    """
    # Input validation
    if not member_data:
        raise ValueError("Member data is required")
    if not isinstance(partner_id, int) or partner_id <= 0:
        raise ValueError("partner_id must be a positive integer")
    if not relation or not isinstance(relation, str):
        raise ValueError("A valid relation type is required")
    if not join_date or not isinstance(join_date, str):
        raise ValueError("A valid join_date is required (YYYY-MM-DD)")
    
    # Validate date formats
    try:
        datetime.strptime(join_date, "%Y-%m-%d")
        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid date format: {str(e)}. Use YYYY-MM-DD format.")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Start transaction
            cursor.execute("BEGIN TRANSACTION")
            
            try:
                # 1. Add the new member
                member_id = add_or_update_member(member_data)
                if not member_id:
                    raise ValueError("Failed to add new member")
                
                log.debug(f"Added new member with ID: {member_id}")
                
                # 2. Create the relationship
                cursor.execute(f"""
                    INSERT INTO {db_tables["relations"]} 
                    (member_id, partner_id, relation, join_date, end_date, created_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    member_id,
                    partner_id,
                    relation.lower(),  # Normalize to lowercase
                    join_date,
                    end_date
                ))
                
                relation_id = cursor.lastrowid
                log.debug(f"Created relationship {relation_id} between members {member_id} and {partner_id}")
                
                # 3. Update original family ID and/or name if provided
                update_fields = []
                update_values = []
                
                if original_family_id:
                    update_fields.append("family_id = ?")
                    update_values.append(original_family_id)
                if original_name:
                    update_fields.append("name = ?")
                    update_values.append(original_name)
                
                if update_fields:
                    update_values.append(member_id)
                    update_sql = f"""
                        UPDATE {db_tables["members"]}
                        SET {', '.join(update_fields)}
                        WHERE id = ?
                    """
                    cursor.execute(update_sql, update_values)
                    log.debug(f"Updated member {member_id} with fields: {', '.join(update_fields)}")
                
                # Commit the transaction
                conn.commit()
                return member_id, relation_id
                
            except Exception as e:
                conn.rollback()
                log.error(f"Transaction rolled back in {fu.get_function_name()}: due to error: {str(e)}")
                raise
                
    except sqlite3.IntegrityError as e:
        error_msg = "Database integrity error in {fu.get_function_name()}: when adding related member"
        if "FOREIGN KEY" in str(e):
            error_msg = "The specified partner_id does not exist in the database."
        log.error(f"{error_msg}: {str(e)}")
        raise ValueError(error_msg) from e
        
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: adding related member"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: adding related member"
        log.error(error_msg, exc_info=True)

def update_related_member(
    relation_id: int,
    end_date: str = None,
    **updates: Any
) -> bool:
    """
    Update relationship data between members, primarily used to set relationship end dates.
    
    This function allows updating relationship records in the database, typically used to
    mark relationships as ended (e.g., divorce, end of partnership) or to update other
    relationship attributes.
    
    Args:
        relation_id: The unique identifier of the relationship to update (must be > 0).
        end_date: Optional end date of the relationship in YYYY-MM-DD format.
                 If provided, this will mark when the relationship ended.
        **updates: Additional fields to update as keyword arguments. Common fields include:
                 - relation: Update the type of relationship
                 - join_date: Update the start date of the relationship
                 - notes: Add or update notes about the relationship
                 
    Returns:
        bool: True if the update was successful and affected at least one row, False otherwise.
        
    Raises:
        ValueError: If relation_id is invalid or no update data is provided.
        sqlite3.IntegrityError: If the update violates database constraints.
        sqlite3.Error: For other database-related errors.
        
    Example:
        # Mark a relationship as ended
        >>> success = update_related_member(
        ...     relation_id=42,
        ...     end_date='2023-12-31',
        ...     notes='Divorce finalized on this date.'
        ... )
        >>> if success:
        ...     print("Relationship updated successfully")
    """
    # Input validation
    if not isinstance(relation_id, int) or relation_id <= 0:
        raise ValueError("relation_id must be a positive integer")
    
    if end_date is None and not updates:
        raise ValueError("At least one update field or end_date must be provided")
    
    # Validate date format if provided
    if end_date is not None:
        try:
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"Invalid end_date format: {str(e)}. Use YYYY-MM-DD format.")
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Start transaction
        cursor.execute("BEGIN TRANSACTION")
        
        # First, verify the relationship exists and get current values
        cursor.execute(f"""
            SELECT * FROM {db_tables["relations"]}
            WHERE id = ?
            FOR UPDATE  -- Lock the row for update
        """, (relation_id,))
        
        relationship = cursor.fetchone()
        if not relationship:
            raise ValueError(f"No relationship found with ID {relation_id}")
        
        # Start building the update query
        set_clauses = []
        params = []
        
        # Add end_date to updates if provided
        if end_date is not None:
            set_clauses.append("end_date = ?")
            params.append(end_date)
        
        # Add other update fields
        for field, value in updates.items():
            if value is not None:
                # Handle special field types
                if field in ['join_date', 'end_date']:
                    try:
                        datetime.strptime(value, "%Y-%m-%d")
                    except ValueError as e:
                        raise ValueError(f"Invalid {field} format: {str(e)}. Use YYYY-MM-DD format.")
                
                # Only update if the value is different
                if str(relationship.get(field, '')) != str(value):
                    set_clauses.append(f"{field} = ?")
                    params.append(value)
        
        # If no fields to update, return early
        if not set_clauses:
            log.warning(f"No changes to update for relationship ID {relation_id}")
            return False
            
        # Add updated_at timestamp
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        
        # Build and execute the update query
        update_query = f"""
            UPDATE {db_tables["relations"]}
            SET {', '.join(set_clauses)}
            WHERE id = ?
            RETURNING *
        """
        
        params.append(relation_id)
        cursor.execute(update_query, params)
        
        # Verify the update was successful
        if cursor.rowcount == 0:
            conn.rollback()
            log.error(f"Failed to update relationship ID {relation_id}: No rows affected")
            return False
            
        # Commit the transaction
        conn.commit()
        log.debug(f"Successfully updated relationship ID {relation_id}")
        
        return True
        
    except sqlite3.Error as dbe:
        if conn:
            conn.rollback()
        log.error(f"Database error in {fu.get_function_name()}: {str(dbe)}")
        raise sqlite3.Error(f"Database operation failed: {str(dbe)}")
        
    except ValueError as ve:
        if conn:
            conn.rollback()
        log.error(f"Validation error in {fu.get_function_name()}: {str(ve)}")
        raise
        
    except Exception as e:
        if conn:
            conn.rollback()
        log.error(f"Unexpected error in {fu.get_function_name()}: {str(e)}")
        raise Exception(f"An unexpected error occurred: {str(e)}")
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_members() -> List[Dict[str, Any]]:
    """
    Retrieve all members from the database.
    
    Returns:
        List[Dict[str, Any]]: A list of member dictionaries, 
        where each dictionary contains all the fields from the members table.
        
    Raises:
        sqlite3.Error: If there's a database error while fetching members
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT * FROM {db_tables['members']}
                ORDER BY name, id
            """)
            
            # Get column names from cursor description
            columns = [column[0] for column in cursor.description]
            
            # Convert each row to a dictionary
            members = []
            for row in cursor.fetchall():
                members.append(dict(zip(columns, row)))
                
            log.debug(f"Retrieved {len(members)} members from database")
            return members
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: while fetching members"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: while fetching members"
        log.error(error_msg, exc_info=True)
        raise

def get_member_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a member record given by unique member email.
    
    This function fetches all available information for a specific member record 
    from the database.
    
    Args:
        email: The unique identifier of the member to retrieve 
        (must be a valid email address)
        
    Returns:
        Optional[Dict[str, Any]]: A dictionary containing 
        the member's data if found.
        None if no member exists with the given email. 
        The dictionary includes all the fields from the `members` table.
            
    Raises:
        ValueError: If email is not a valid email address
        sqlite3.Error: If a database error occurs
        Exception: For any other unexpected errors
        
    Example:
        >>> member = get_member_by_email('example@example.com')
        >>> if member:
        ...     print(f"Found member: {member['name']} ({member['email']})")
        ... else:
        ...     print("No member found with that email")
    """
    if not email or not isinstance(email, str) or '@' not in email:
        error_msg = "Invalid email address provided"
        log.error(error_msg)
        raise ValueError(error_msg)
        
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM members 
                WHERE email = ?
                """,
                (email,)
            )
            
            columns = [column[0] for column in cursor.description]
            member = cursor.fetchone()
            
            if member:
                return dict(zip(columns, member))
            return None
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: while fetching member by email"
        log.error(error_msg, exc_info=True)
        raise
    except ValueError:
        error_msg = "Invalid email address provided"
        log.error(error_msg)
        raise ValueError(error_msg)
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: while fetching member by email"
        log.error(error_msg, exc_info=True)
        raise
    
def get_member(member_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve a member record given by unique member ID.
    
    This function fetches all available information for a specific member record 
    from the database.
    
    Args:
        member_id: The unique identifier of the member to retrieve 
        (must be a positive integer)
        
    Returns:
        Optional[Dict[str, Any]]: A dictionary containing the member's data if found, 
        None if no member exists with the given ID. 
        The dictionary includes all the fields from the members table.
            
    Raises:
        ValueError: If member_id is not a positive integer
        sqlite3.Error: If a database error occurs
        
    Example:
        >>> member = get_member(123)
        >>> if member:
        ...     print(f"Found member: {member['name']}")
        ... else:
        ...     print("Member not found")
    """
    # Validate input
    if not isinstance(member_id, int) or member_id <= 0:
        error_msg = f"Invalid member ID: {member_id}. Must be a positive integer."
        log.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Query the database for the member
            cursor.execute(f"""
                SELECT * FROM {db_tables['members']}
                WHERE id = ?
                LIMIT 1
            """, (member_id,))
            
            # Fetch the result and convert to dictionary if found
            result = cursor.fetchone()
            
            if result:
                member_data = dict(result)
                log.debug(f"Retrieved member ID {member_id}: {member_data.get('name')}")
                return member_data
                
            log.debug(f"No member found with ID: {member_id}")
            return None
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: fetching member ID {member_id}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: fetching member ID {member_id}"
        log.error(error_msg, exc_info=True)
        raise


def get_families_by_name(name):
    """
    Retrieve a family record given by name-like family records.
    
    This function fetches all available information for a specific 
    family record from the db_tables['families'] table.
    
    Args:
        name: The name-like string to search for 
        in the db_tables['families'] table.
        
    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing 
        the family's records if found, 
        empty list if no family exists with the similar name-like string. 
        Each dictionary includes all the fields from the 
        db_tables['families'] table.
            
    Raises:
        ValueError: If name is not a string
        sqlite3.Error: If a database error occurs
        
    Example:
        >>> families = get_families_by_name("Smith")
        >>> if families:
        ...     for family in families:
        ...         print(f"Found family: {family['name']}")
        ... else:
        ...     print("No matching families found")
    """
    if not isinstance(name, str):
        raise ValueError("Name must be a string")
    
    if not name.strip():
        return []
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Use LIKE with wildcards for partial matching and case-insensitive search
        query = f"""
            SELECT * FROM {db_tables['families']}
            WHERE LOWER(name) LIKE LOWER(?)
            ORDER BY id ASC
        """
        
        cursor.execute(query, (f'%{name}%',))
        
        # Get column names from cursor description
        columns = [col[0] for col in cursor.description]
        
        # Convert results to list of dictionaries
        families = []
        for row in cursor.fetchall():
            families.append(dict(zip(columns, row)))
            
        return families
        
    except sqlite3.Error:
        error_msg = f"❌ Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"❌ Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    
def get_families_by_background(background: str) -> List[Dict[str, Any]]:
    """
    Retrieve family records that match the given background search text.
    
    This function performs a case-insensitive partial match search on the 
    background field of the db_tables['families'] table.
    
    Args:
        background: The text to search for in the background field
        
    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing 
        the family records if found, 
        empty list if no family exists with matching background text. 
        Each dictionary includes all the fields from the 
        db_tables['families'] table.
            
    Raises:
        ValueError: If background is not a string
        sqlite3.Error: If a database error occurs
        
    Example:
        >>> families = get_families_by_background("merchant")
        >>> if families:
        ...     for family in families:
        ...         print(f"Found family: {family['name']} (ID: {family['id']})")
        ... else:
        ...     print("No matching families found")
    """
    if not isinstance(background, str):
        raise ValueError("Background must be a string")
    
    if not background.strip():
        return []
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Use LIKE with wildcards for partial matching and case-insensitive search
        query = f"""
            SELECT * FROM {db_tables['families']}
            WHERE LOWER(background) LIKE LOWER(?)
            ORDER BY id ASC
        """
        
        cursor.execute(query, (f'%{background}%',))
        
        # Get column names from cursor description
        columns = [col[0] for col in cursor.description]
        
        # Convert results to list of dictionaries
        families = []
        for row in cursor.fetchall():
            families.append(dict(zip(columns, row)))
            
        return families
        
    except sqlite3.Error:
        error_msg = f"❌ Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"❌ Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise


def get_relations_by_id(member_id: int,
                        relation: str = None,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve a relation record given by ID that either member_id 
    or partner_id matches.
    
    This function fetches all available information for a specific 
    relation record from the `relations` table.
    
    Args:
        member_id: The unique identifier of the relation to retrieve 
        (must be a positive integer)

        relation: The relation type to search for in the relation field.
        get all relations if relation is None
        
    Returns:
        Optional[List[Dict[str, Any]]]: A list of dictionaries containing 
        the relation's data if found, 
        None if no relation exists with the given ID. 
        The dictionary includes all the fields from the relations table.
            
    Raises:
        ValueError: If member_id is not a positive integer
        sqlite3.Error: If a database error occurs
        
    Example:
        >>> member_id = 123
        >>> relations = get_relations_by_id(member_id)
        >>> if relations:
        ...     print(f"Found relation either member id is {member_id} or partner id is {member_id}")
        ... else:
        ...     print("Relation not found")
    """
    # Validate input
    if not isinstance(member_id, int) or member_id < 0:
        error_msg = f"Invalid ID to search for member_id or partner_id: {member_id}. Must be a positive integer."
        log.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if relation:
                # Query the database for the relation
                cursor.execute(f"""
                    SELECT * FROM {db_tables['relations']}
                    WHERE member_id = ? or partner_id = ?
                    AND relation LIKE ?
                """, (member_id, member_id, f'%{relation}%'))
            else:
                # Query the database for the relation
                cursor.execute(f"""
                    SELECT * FROM {db_tables['relations']}
                    WHERE member_id = ? or partner_id = ?
                """, (member_id, member_id))
            
            # Get column names from cursor description
            columns = [col[0] for col in cursor.description]
            
            # Fetch all results and convert to list of dictionaries
            results = cursor.fetchall()
            
            # Convert results to list of dictionaries
            relations = []
            for row in results:
                relations.append(dict(zip(columns, row)))
            
            return relations
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: fetching relation with either member_id or partner_id is {member_id}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: fetching relation with either member_id or partner_id is {member_id}"
        log.error(error_msg, exc_info=True)
        raise

def get_relations_by_relation(relation_type: str) -> List[Dict[str, Any]]:
    """
    Retrieve relation records that match the given relation type.
    
    This function searches the relations table for records where the relation
    matches the specified relation type.
    
    Args:
        relation_type (str): The relation type to search for in the relation field
        
    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing 
        the relation records if found, 
        empty list if no relation exists with matching relation type. 
        Each dictionary includes all the fields from the 
        `relations` table.
            
    Raises:
        ValueError: If relation_type is not a string
        sqlite3.Error: If a database error occurs
        
    Example:
        >>> relations = get_relations_by_relation("spouse")
        >>> if relations:
        ...     for relation in relations:
        ...         print(f"Found relation between member {relation['member_id']} and {relation['partner_id']}")
        ... else:
        ...     print("No matching relations found")
    """
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Use LIKE with wildcards for partial matching and case-insensitive search
        query = f"""
            SELECT * FROM {db_tables['relations']}
            WHERE LOWER(relation) LIKE LOWER(?)
            ORDER BY id ASC
        """
        
        cursor.execute(query, (f'%{relation_type}%',))
        
        # Get column names from cursor description
        columns = [col[0] for col in cursor.description]
        
        # Convert results to list of dictionaries
        relations = []
        for row in cursor.fetchall():
            relations.append(dict(zip(columns, row)))
            
        return relations
        
    except sqlite3.Error:
        error_msg = f"❌ Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"❌ Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    
def get_relations_by_join_between(from_date: str, to_date: str) -> List[Dict[str, Any]]:
    """
    Retrieve relation records that match the given join date range.
    
    This function searches the relations table for records where the join_date
    falls within the specified date range (inclusive).
    
    Args:
        from_date: The start date to search for in the join_date field (YYYY-MM-DD format)
        to_date: The end date to search for in the join_date field (YYYY-MM-DD format)
        
    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing 
        the relation records if found, 
        empty list if no relation exists with matching join date range. 
        Each dictionary includes all the fields from the 
        `relations` table.
            
    Raises:
        ValueError: If from_date or to_date is not a valid date string in YYYY-MM-DD format
        sqlite3.Error: If a database error occurs
        
    Example:
        >>> relations = get_relations_by_join_between("2020-01-01", "2020-12-31")
        >>> if relations:
        ...     for relation in relations:
        ...         print(f"Found relation between member {relation['member_id']} and {relation['partner_id']}")
        ... else:
        ...     print("No matching relations found")
    """
    # Validate input parameters
    if not isinstance(from_date, str) or not isinstance(to_date, str):
        raise ValueError("Both from_date and to_date must be strings")
        
    # Ensure dates are in YYYY-MM-DD format
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    if not date_pattern.match(from_date) or not date_pattern.match(to_date):
        raise ValueError("Dates must be in YYYY-MM-DD format")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query to find relations with join_date between from_date and to_date (inclusive)
        query = f"""
            SELECT * FROM {db_tables['relations']}
            WHERE join_date >= ? AND join_date <= ?
            ORDER BY join_date, id
        """
        
        cursor.execute(query, (from_date, to_date))
        
        # Get column names from cursor description
        columns = [col[0] for col in cursor.description]
        
        # Convert results to list of dictionaries
        relations = []
        for row in cursor.fetchall():
            relations.append(dict(zip(columns, row)))
            
        return relations
        
    except sqlite3.Error:
        error_msg = f"❌ Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"❌ Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    
def update_member(member_id: int, update_data: Dict[str, Any]) -> bool:
    """
    Update an existing member's information in the database.
    
    This function updates the specified fields for a member record. 
    Only non-None values in the update_data dictionary will be updated. 
    The updated_at timestamp is automatically set to the current time.
    
    Args:
        member_id: The unique identifier of the member to update (must be a positive integer)
        update_data: Dictionary containing the fields to update. Valid keys include:
            - name (str): Last name
            - sex (str): Gender ('M'/'F'/'O')
            - born (str): Date of birth (YYYY-MM-DD)
            - family_id (int): Family identifier
            - alias (str): Nickname or alternative name
            - email (str): Contact email
            - url (str): Personal website URL
            - died (str): Date of death (YYYY-MM-DD), if applicable
            - gen_order (int): Generation order number
            - dad_id (int): Father's member ID
            - mom_id (int): Mother's member ID
            
    Returns:
        bool: True if the update was successful and affected at least one row, False otherwise
        
    Raises:
        ValueError: If member_id is invalid or update_data is empty/None
        sqlite3.Error: If a database error occurs
        
    Example:
        >>> updates = {
        ...     'name': 'Smith',
        ...     'email': 'new.email@example.com'
        ... }
        >>> success = update_member(123, updates)
        >>> if success:
        ...     print("Member updated successfully")
    """
    # Input validation
    if not isinstance(member_id, int) or member_id <= 0:
        error_msg = f"Invalid member ID: {member_id}. Must be a positive integer."
        log.error(error_msg)
        raise ValueError(error_msg)
        
    if not update_data:
        error_msg = "No update data provided. At least one field must be specified."
        log.error(error_msg)
        raise ValueError(error_msg)
    
    # Filter out None values and empty strings
    filtered_updates = {k: v for k, v in update_data.items() if v is not None and v != ''}
    if not filtered_updates:
        log.warning("No valid fields to update after filtering out None/empty values")
        return False
    
    # Prepare SET clause and parameters
    set_clause = ", ".join(f"{field} = ?" for field in filtered_updates.keys())
    values = list(filtered_updates.values())
    values.append(member_id)  # Add WHERE clause parameter
    
    # Build the SQL query
    sql = f"""
        UPDATE {db_tables["members"]}
        SET {set_clause}, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, values)
            rows_affected = cursor.rowcount
            conn.commit()
            
            if rows_affected > 0:
                log.debug(f"Successfully updated member ID {member_id}. Fields updated: {', '.join(filtered_updates.keys())}")
                return True
            else:
                log.warning(f"No member found with ID {member_id} to update")
                return False
                
    except sqlite3.IntegrityError as e:
        error_msg = f"Database integrity error in {fu.get_function_name()}: updating member"
        if "FOREIGN KEY" in str(e):
            error_msg = f"Invalid parent ID provided in {fu.get_function_name()}. The specified father or mother does not exist."
        log.error(f"{error_msg}: {str(e)}")
        raise ValueError(error_msg) from e
        
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: updating member ID {member_id}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: updating member ID {member_id}"
        log.error(error_msg, exc_info=True)
        raise

def delete_member(member_id: int) -> bool:
    """
    Delete a member from the database by their ID.
    
    This function permanently removes a member record from the database.
    Use with caution as this action cannot be undone.
    
    Note: This function will fail if the member has existing relationships
    that would violate foreign key constraints. Consider updating or removing
    those relationships first.
    
    Args:
        member_id: The unique identifier of the member to delete (must be a positive integer)
        
    Returns:
        bool: True if the member was successfully deleted, False if no member
              was found with the given ID
              
    Raises:
        ValueError: If member_id is not a positive integer
        sqlite3.Error: If a database error occurs during deletion
        
    Example:
        >>> success = delete_member(123)
        >>> if success:
        ...     print("Member deleted successfully")
        ... else:
        ...     print("No member found with that ID")
    """
    # Input validation
    if not isinstance(member_id, int) or member_id <= 0:
        error_msg = f"Invalid member ID: {member_id}. Must be a positive integer."
        log.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # First, check if member exists to provide better error messaging
            cursor.execute(f"SELECT name FROM {db_tables['members']} WHERE id = ?", (member_id,))
            member = cursor.fetchone()
            
            if not member:
                log.warning(f"Attempted to delete non-existent member ID: {member_id}")
                return False
            
            member_name = member[0] if member[0] else "[Unnamed]"
            
            # Delete the member
            cursor.execute(f"DELETE FROM {db_tables['members']} WHERE id = ?", (member_id,))
            rows_affected = cursor.rowcount
            conn.commit()
            
            if rows_affected > 0:
                log.debug(f"Successfully deleted member ID {member_id} (Name: {member_name})")
                return True
            else:
                log.warning(f"No member found with ID {member_id} (Name: {member_name})")
                return False
                
    except sqlite3.IntegrityError as e:
        error_msg = f"""
        Cannot delete member due to referential integrity constraint 
        in {fu.get_function_name()}. This member likely has existing 
        relationships that must be resolved first. Consider removing 
        or updating related records before deleting this member.
        """.strip()
        log.error(f"{error_msg} Member ID: {member_id}, Error: {str(e)}")
        raise ValueError(error_msg) from e
        
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: deleting member ID {member_id}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: deleting member ID {member_id}"
        log.error(error_msg, exc_info=True)
        raise

def get_members_when_born_in(month: int) -> List[Dict[str, Any]]:
    """
    Query all living members born in a specific month.
    
    This function only includes members with full birth dates (YYYY-MM-DD) where
    the month can be accurately determined. Year-only dates (YYYY) are excluded.
    
    Args:
        month (int): The month to query (1-12)
        
    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing member data that matches the query,
        with each member dictionary containing all member fields
        
    Raises:
        ValueError: When the month is not in the range of 1-12
    """
    if not 1 <= month <= 12:
        raise ValueError("Month must be between 1 and 12")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Format month as two digits (01-12)
            month_str = f"{month:02d}"
            
            # Query to find living members with valid full birth dates (YYYY-MM-DD) matching the specified month
            query = f"""
                SELECT *
                FROM {db_tables['members']}
                WHERE 
                -- Must be exactly 10 characters (YYYY-MM-DD)
                LENGTH(TRIM(born)) = 10
                -- Exclude placeholder and invalid dates
                AND born NOT IN ('0000-01-01', '0', '')
                AND born IS NOT NULL
                -- Check month part matches (positions 6-7 in YYYY-MM-DD)
                AND substr(born, 6, 2) = ?
                ORDER BY born ASC
            """            
            cursor.execute(query, (month_str,))
            
            # Get column names
            columns = get_table_columns(db_tables['members'])
            
            # Convert results to list of dictionaries
            rows = cursor.fetchall()
            members = []
            for row in rows:
                member = dict(zip(columns, row))
                if member_is_alive(member):
                    members.append(member)
                    log.debug(f"member: {member}")
            log.debug(f"Found {len(members)} members with birthdays in month of {month:02d}")
            
            return members
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: Querying members born in month {month} failed"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: Querying members born in month {month} failed"
        log.error(error_msg, exc_info=True)
        raise

def member_is_alive(member_data: Dict[str, Any]) -> bool:
    """
    Check if a member is alive based on the 'died' field.
    
    A member is considered alive if:
    - 'died' field is None or empty string
    - 'died' field contains invalid or placeholder values
    
    A member is considered deceased if:
    - 'died' field contains a valid year (as int or str)
    - 'died' field contains a valid date string
    - 'died' field contains '0000-01-01', indicating the member is 
        deceased with unknown date
    
    Args:
        member_data (Dict[str, Any]): Dictionary containing member 
            data with 'died' field
        
    Returns:
        bool: True if the member is alive, False if deceased
    """
    if not member_data:
        log.debug("Member record is required")
        return False
        
    member_id = member_data.get('id', 'unknown')
    died = member_data.get('died')
    
    # Handle None or empty string
    if died is None or died == '':
        log.debug(f"Member {member_id} is alive: no death date")
        return True
    
    # Convert to string for consistent processing
    died_str = str(died).strip()
    
    # Check for placeholder values that indicate deceased
    if died_str in ('0', '0000-01-01'):
        log.debug(f"Member {member_id} is deceased: placeholder death date: {died}")
        return False
    
    # Check for invalid/placeholder values that indicate deceased
    if died_str in ('YYYY', 'YYYY-MM', 'YYYY-MM-DD'):
        log.debug(f"Member {member_id} is deceased: invalid/placeholder death date: {died}")
        return False
        
    # Check if it's a valid year (4 digits)
    if (isinstance(died, int) and 1000 <= died <= 9999) or \
       (isinstance(died, str) and died.isdigit() and len(died) == 4):
        log.debug(f"Member {member_id} is deceased: died in year {died}")
        return False
        
    # Check for valid date format (YYYY-MM-DD or YYYY-MM)
    try:
        if isinstance(died, str) and (len(died) == 10 or len(died) == 7):
            datetime.strptime(died, '%Y-%m-%d' if len(died) == 10 else '%Y-%m')
            log.debug(f"Member {member_id} is deceased: died on {died}")
            return False
    except ValueError:
        pass
    
    # If we get here, it's some other format we'll consider as alive
    log.debug(f"Member {member_id} is alive: unrecognized death date format: {died}")
    return True

def search_members(
    name: str = "",
    family_id: int = 0,
    gen_order: int = 0,
    born: str = "",
    alias: str = "",
    died: str = "",
    id: int = 0,
    email: str = "",
    sex: str = "",
    alive: bool = False
) -> List[Dict[str, Any]]:
    """
    Search for members based on various filter criteria.
    
    This function allows searching for members using 
    flexible filtering options. All parameters are optional, 
    and multiple filters can be combined.
    
    Args:
        name: Full or partial last name to search for (case-insensitive)
        family_id: Full or partial family ID to search for (case-insensitive)
        gen_order: Exact generation order number to filter by (must be > 0)
        born: Date of birth filter, which can be:
              - Full date (YYYY-MM-DD)
              - Year and month (YYYY-MM)
              - Just year (YYYY)
        alias: Full or partial alias/nickname to search for (case-insensitive)
        died: Date of death filter, which can be:
              - Full date (YYYY-MM-DD)
              - Year and month (YYYY-MM)
              - Just year (YYYY)
        sex: Gender filter, which can be:
              - "M" for male
              - "F" for female
              - "O" for other
        alive: Boolean flag to filter for living members only
    Returns:
        List[Dict[str, Any]]: A list of member dictionaries 
        matching the search criteria. Each dictionary contains 
        all fields from the members table for a matching member.
        Returns an empty list if no matches are found.
        
    Raises:
        sqlite3.Error: If a database error occurs during the search
        
    Example:
        # Search for members with last name containing 'Smith' born in 1980
        >>> results = search_members(name='Smith', born='1980')
        >>> for member in results:
        ...     print(f"{member['name']} ({member['born']})")
        
        # Search for members by generation order
        >>> gen_results = search_members(gen_order=2)
    """
    conditions = []
    params = []
    
    # Add name filter if provided
    if name and name.strip():
        conditions.append("name LIKE ?")
        params.append(f"%{name.strip()}%")
    
    # Add alias filter if provided
    if alias and alias.strip():
        conditions.append("alias LIKE ?")
        params.append(f"%{alias.strip()}%")
    
    # Add family_id filter if provided
    if family_id and int(family_id) > 0:
        conditions.append("family_id = ?")
        params.append(int(family_id))
    
    # Add generation order filter if provided and valid
    if isinstance(gen_order, int) and int(gen_order) > 0:
        conditions.append("gen_order = ?")
        params.append(int(gen_order))
    
    # Add birth date filter if provided
    if born and born.strip():
        born = born.strip()
        # Support full date, year-month, or year search with substring matching
        if len(born) == 10 and born[4] == '-' and born[7] == '-':  # YYYY-MM-DD
            conditions.append("born = ?")
            params.append(born)
        elif len(born) == 7 and born[4] == '-':  # YYYY-MM
            conditions.append("SUBSTR(born, 1, 7) = ?")
            params.append(born)
        elif len(born) == 4 and born.isdigit():  # YYYY
            conditions.append("born LIKE ?")
            params.append(f"{born}%")
        else:
            log.warning(f"Invalid date format for 'born' parameter: {born}")
    
    # Add death date filter if provided
    if died and died.strip():
        died = died.strip()
        # Support full date, year-month, or year search with substring matching
        if len(died) == 10 and died[4] == '-' and died[7] == '-':  # YYYY-MM-DD
            conditions.append("died = ?")
            params.append(died)
        elif len(died) == 7 and died[4] == '-':  # YYYY-MM
            conditions.append("SUBSTR(died, 1, 7) = ?")
            params.append(died)
        elif len(died) == 4 and died.isdigit():  # YYYY
            conditions.append("died LIKE ?")
            params.append(f"{died}%")
        else:
            log.warning(f"Invalid date format for 'died' parameter: {died}")
    
    # Add ID filter if provided
    if isinstance(id, int) and int(id) > 0:
        conditions.append("id = ?")
        params.append(int(id))
    
    # Add email filter if provided
    if email and email.strip():
        conditions.append("email LIKE ?")
        params.append(f"%{email.strip()}%")
    
    # Add sex filter if provided
    if sex and sex.strip():
        conditions.append("sex = ?")
        params.append(sex)
    
    # Build the WHERE clause
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Execute the query with the constructed conditions
            query = f"""
                SELECT * FROM {db_tables['members']} 
                WHERE {where_clause} 
                ORDER BY gen_order, born, name
            """
            
            log.debug(f"Executing search query: {query} with params: {params}")
            cursor.execute(query, params)
            
            # Convert results to list of dictionaries
            results = [dict(row) for row in cursor.fetchall()]
            if alive:
                results = [member for member in results if member_is_alive(member)]
            log.debug(f"Found {len(results)} members matching search criteria")
            
            return results
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: during member search"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: during member search"
        log.error(error_msg, exc_info=True)
        raise

def get_member_relations(member_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve all relationships for a given member.
    
    This function fetches all relationship records where the specified member
    is either the 'member_id' or 'partner_id' in the db_tables['relations'] table.
    This provides a complete view of all relationships (e.g., spouse, parent, child)
    for the given member.
    
    Args:
        member_id: The unique identifier of the member to retrieve relationships for.
                 Must be a positive integer.
                 
    Returns:
        List[Dict[str, Any]]: A list of relationship records where each record is a dictionary
        containing the relationship details. 
        Returns an empty list if no relationships are found.
        
        Each relationship dictionary contains all fields from the 
        db_tables['relations'] table.
        
    Raises:
        ValueError: If member_id is not a positive integer.
        sqlite3.Error: If a database error occurs during the query.
        
    Example:
        >>> relationships = get_member_relations(123)
        >>> for rel in relationships:
        ...     print(f"Relationship ID: {rel['id']}, Type: {rel['relation']}")
        ...     print(f"Between members: {rel['member_id']} and {rel['partner_id']}")
        ...     print(f"Dates: {rel['join_date']} to {rel.get('end_date', 'present')}")
    """
    # Input validation
    if not isinstance(member_id, int) or member_id <= 0:
        raise ValueError("member_id must be a positive integer")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Query to get all relationships where the member is either member_id or partner_id
            query = f"""
                SELECT * 
                FROM {db_tables["relations"]}
                WHERE member_id = ? OR partner_id = ?
                ORDER BY join_date DESC  -- Most recent first within each group
            """
            
            cursor.execute(query, (member_id, member_id))
            
            # Convert Row objects to dictionaries for better serialization
            results = [dict(row) for row in cursor.fetchall()]
            
            log.debug(f"Found {len(results)} relationships for member {member_id}")
            return results
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: retrieving relationships for member {member_id}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: retrieving relationships"
        log.error(error_msg, exc_info=True)
        raise

def update_relation_when_ended(
    member1_id: int,
    member2_id: int,
    relation: str,
    end_date: str
) -> int:
    """
    Update the relationship status between two members 
    when the relationship ends.
    
    This function updates the relationship record between two members 
    by setting the end_date to indicate when the relationship ended. 
    This is typically used for events like divorce, end of partnership, 
    or other relationship terminations.
    
    Args:
        member1_id: The ID of the first member in the relationship.
                  Must be a positive integer.
        member2_id: The ID of the second member in the relationship.
                  Must be a positive integer.
        relation: The type of relationship being ended (e.g., 'spouse', 'partner').
        end_date: The end date of the relationship in YYYY-MM-DD format.
        
    Returns:
        int: The number of relationship records updated (should be 1 or 2 if successful).
        Zero if not successful.
        
    Raises:
        ValueError: If any input parameters are invalid.
        sqlite3.Error: If a database error occurs during the update.
        
    Example:
        >>> update_count = update_relation_when_ended(
        ...     member1_id=123,
        ...     member2_id=456,
        ...     relation='spouse divorced',
        ...     end_date='2023-01-15'
        ... )
        >>> if update_count > 0:
        ...     print("Relationship successfully updated")
    """
    # Input validation
    if not all([member1_id, member2_id, relation, end_date]):
        raise ValueError("All parameters are required")
        
    if not all(isinstance(id_, int) and id_ > 0 for id_ in [member1_id, member2_id]):
        raise ValueError("Member IDs must be positive integers")
    
    if member1_id == member2_id:
        raise ValueError("Member IDs cannot be the same")
        
    # Validate date format
    try:
        datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        raise ValueError("end_date must be in YYYY-MM-DD format")
    
    conn = None
    cursor = None
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
        
            # Check if both members exist
            cursor.execute(f"""
                SELECT id FROM {db_tables["members"]} 
                WHERE id IN (?, ?)
            """, (member1_id, member2_id))
        
            members = cursor.fetchall()
        
            if len(members) != 2:
                found_ids = [str(m[0]) for m in members]
                raise ValueError(f"One or both members not found. Found member IDs: {', '.join(found_ids) if found_ids else 'None'}")
        
            # Update the relationship record
            cursor.execute(f"""
                UPDATE {db_tables["relations"]}
                SET end_date = ?,
                    relation = ?
                WHERE ((member_id = ? AND partner_id = ?) OR
                   (member_id = ? AND partner_id = ?))
                AND (end_date IS NULL OR end_date = '' OR end_date <= ?)
            """, (
                end_date,
                relation,
                member1_id,
                member2_id,
                member2_id,
                member1_id,
                end_date
            ))
        
            updated_count = cursor.rowcount
        
            if updated_count == 1 or updated_count == 2:
                log.debug(f"Updated relations:{updated_count} for {member1_id}-{member2_id}")
            else:
                # should not happen, but just in case
                log.warning(f"Updated relations:{updated_count} for {member1_id}-{member2_id}")
            return updated_count
        
    except sqlite3.Error as dbe:
        log.error(f"Database error in {fu.get_function_name()}: {str(dbe)}")
        raise sqlite3.Error(f"Database operation failed: {str(dbe)}")
        
    except Exception as e:
        log.error(f"Unexpected error in {fu.get_function_name()}: {str(e)}")
        raise Exception(f"An unexpected error occurred: {str(e)}")

def update_relations_when_died(
    member_id: int,
    died_date: str
) -> Tuple[bool, int, int]:
    """
    Update a member's status to deceased and update related 
    relationship records in the db_tables['relations'] table.
    
    This function performs the following operations in a single transaction:
    1. Updates the member's 'died' field with the provided date
    2. Updates any active relationships to mark them as ended
    
    Args:
        member_id: The ID of the member who has died (must be a positive integer)
        died_date: Date of death in YYYY-MM-DD format
        
    Returns:
        Tuple[bool, int, int]: A tuple containing:
            - success: True if the update was successful, False otherwise
            - updated_members_count: Number of members updated
            - updated_relations_count: Number of relationships updated
        
    Raises:
        ValueError: If member_id is invalid or died_date is not in the correct format
        sqlite3.Error: If a database error occurs during the update
        
    Example:
        >>> updated = update_relations_when_died(123, '2023-12-31')
        >>> if updated[0]:
            print(f"Updated member count: {updated[1]}\nUpdated relationships count: {updated[2]}")
    """
    # Input validation
    if not isinstance(member_id, int) or member_id <= 0:
        raise ValueError("member_id must be a positive integer")
        
    try:
        # Validate date format
        datetime.strptime(died_date, '%Y-%m-%d')
    except ValueError:
        raise ValueError("died_date must be in YYYY-MM-DD format")
    
    conn = None
    cursor = None
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
        
            # 1. Update the member's died date
            cursor.execute(f"""
                UPDATE {db_tables["members"]}
                SET died = ?
                WHERE id = ?
            """, (died_date, member_id))
        
            updated_members = cursor.rowcount
        
            if updated_members == 0:
                raise ValueError(f"No member found with ID {member_id}")
            log.debug(f"Marked member ID: {member_id} as deceased on {died_date} in members table.")
                    
            # 2. Update any active relationships to mark them as ended
            cursor.execute(f"""
                UPDATE {db_tables["relations"]}
                SET end_date = ?
                WHERE (member_id = ? OR partner_id = ?)
                AND (end_date IS NULL OR end_date = ''
                OR end_date = '0000-00-00'
                OR end_date > ?)
            """, (died_date, member_id, member_id, died_date))
        
            updated_relations = cursor.rowcount
        
            log.debug(f"Marked member ID: {member_id} as deceased on {died_date} in relations table. " +
                    f"Updated {updated_relations} relationships.")
        
            return updated_relations > 0, updated_members, updated_relations
        
    except Exception as e:
        log.error(f"Unexpected error in {fu.get_function_name()}: {str(e)}")
        raise
        
def get_members_when_alive() -> List[Dict[str, Any]]:
    """
    Retrieve a list of all living members
    
    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing data of all living members
        
    Raises:
        sqlite3.Error: When a database operation fails
    
    Example:
        alive_members = get_members_when_alive()
        print(f"Found {len(alive_members)} living members")
        for member in alive_members[:5]:  # Only show first 5 members
            print(f"- {member.get('name', '')} (ID: {member.get('id')})")
            print(f"\tDied:{member.get('died')}")
        if len(alive_members) > 5:
            print(f"... and {len(alive_members) - 5} more members")
    """
    with get_db_connection() as conn:
        try:
            cursor = conn.cursor()
            
            # First, get all members
            cursor.execute(f"""
                SELECT * FROM {db_tables["members"]} 
                ORDER BY id
            """)
            
            # Filter members using member_is_alive function
            members = []
            for row in cursor.fetchall():
                member = dict(row)
                if member_is_alive(member):
                    members.append(member)
                
            return members
            
        except sqlite3.Error as e:
            raise sqlite3.Error(f"Database error in {fu.get_function_name()}: Error querying living members: {str(e)}")

def get_relation(relation_id: int) -> Dict[str, Any]:
    """
    Retrieve a single relation by its ID.
    
    Args:
        relation_id: The ID of the relation to retrieve (case-sensitive)
        
    Returns:
        Dict[str, Any]: A dictionary containing data of the relation with the specified ID
        
    Raises:
        sqlite3.Error: When a database operation fails
    """
    with get_db_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT * FROM {db_tables['relations']}
                WHERE id = ?
            """, (relation_id,))
            
            relation = cursor.fetchone()
            
            if relation:
                return dict(relation)
            else:
                return None
            
        except sqlite3.Error as e:
            raise sqlite3.Error(f"Database error in {fu.get_function_name()}: Error querying relation: {str(e)}")

def get_relations() -> List[Dict[str, Any]]:
    """
    Retrieve all the records from the db_tables['relations'] table.
    
    Returns:
        List[Dict[str, Any]]: A list of relation dictionaries, 
        where each dictionary contains all fields from the 
        db_tables['relations'] table.
        The list is sorted by member_id in ascending order.
        
    Raises:
        sqlite3.Error: If there's a database error while fetching relations
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT 
                    id,
                    member_id,
                    partner_id,
                    relation,
                    join_date,
                    COALESCE(end_date, '') as end_date,
                    COALESCE(original_family_id, 0) as original_family_id,
                    COALESCE(original_name, '') as original_name,
                    created_at,
                    updated_at
                FROM {db_tables['relations']}
                ORDER BY member_id ASC
            """)
            
            # Get column names from cursor description
            columns = [column[0] for column in cursor.description]
            
            # Convert each row to a dictionary with proper type handling
            relations = []
            for row in cursor.fetchall():
                row_dict = {}
                for idx, value in enumerate(row):
                    col_name = columns[idx]
                    # Convert None to empty string for string fields
                    if value is None:
                        if col_name in ['end_date', 'original_name']:
                            row_dict[col_name] = ''
                        elif col_name in ['original_family_id']:
                            row_dict[col_name] = 0
                        else:
                            row_dict[col_name] = value
                    else:
                        row_dict[col_name] = value
                relations.append(row_dict)
                
            log.debug(f"Retrieved {len(relations)} relations from database")
            return relations
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: while fetching relations"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: while fetching relations"
        log.error(error_msg, exc_info=True)
        raise

def insert_relation(relation_data: Dict[str, Any]) -> int:
    """
    Insert a new relationship record into db_tables['relations'] 
    table. This function is used for importing relations from 
    external sources.
    
    Args:
        relation_data: A dictionary containing relationship 
        information, see db_tables['relations'] table for details.
    
    Returns:
        int: An positive integer ID of the inserted relationship record.
        Zero if failed.
        
    Raises:
        sqlite3.Error: If there's a database error while inserting the relation.
        Exception: If there's an unexpected error while inserting the relation.
    """
    try:
        if not isinstance(relation_data, dict):
            error_msg = f"Invalid relation data: {relation_data}. Must be a dictionary."
            log.error(error_msg)
            raise ValueError(error_msg)
        
        id = relation_data.get('id')
        if not id or not isinstance(id, int) or id <= 0:
            error_msg = f"Invalid relation data: {relation_data}. Invalid id."
            log.error(error_msg)
            raise ValueError(error_msg)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                INSERT INTO {db_tables['relations']} (
                    id,
                    member_id,
                    partner_id,
                    relation,
                    join_date,
                    end_date,
                    original_family_id,
                    original_name,
                    dad_name,
                    mom_name,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                relation_data['id'],
                relation_data['member_id'],
                relation_data['partner_id'],
                relation_data['relation'],
                relation_data['join_date'],
                relation_data['end_date'],
                relation_data['original_family_id'],
                relation_data['original_name'],
                relation_data['dad_name'],
                relation_data['mom_name'],
                relation_data['created_at']
            ))
            if cursor.rowcount > 0:
                log.debug(f"Relation {relation_data['id']} inserted successfully.")
                conn.commit()
                return relation_data['id']
            else:
                log.debug(f"Relation {relation_data['id']} not inserted.")
                return 0
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: Error inserting relation"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: Error inserting relation"
        log.error(error_msg, exc_info=True)
        raise
    
def add_or_update_relation(relation_data: Dict[str, Any], update: bool = False) -> int:
    """
    Add if not exists or update a relationship record in db_tables['relations'] 
    table when matching record (member_id, partner_id) is found.
    
    This function is used to add or update a relationship record.
    
    Args:
        relation_data: A dictionary containing relationship 
        information, see db_tables['relations'] table for details.
        update (bool): If True, when the relationship already exists, update the existing record
    
    Returns:
        int: The ID of the added or updated relationship record.
        If update is True and a duplicate relationship record exists, 
        it will update the existing record. 
        Return error if update is False and a duplicate relationship record exists.
    
    Raises:
        ValueError: If missing required fields or data is invalid
        sqlite3.IntegrityError: If database integrity constraint is violated
        sqlite3.Error: Other database related errors
    
    Example:
        >>> relation_data = {
        ...     'member_id': 1,
        ...     'partner_id': 2,
        ...     'relation': 'spouse',
        ...     'join_date': '2020-01-01',
        ...     'original_family_id': 1
        ... }
        >>> relation_id = add_or_update_relation(relation_data, update=True)
    """
    # Validate required fields
    required_fields = ['member_id', 'partner_id', 'relation']
    for field in required_fields:
        if field not in relation_data or relation_data[field] is None:
            raise ValueError(f"Missing required field: {field}")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if the same relationship record already exists
            cursor.execute(f"""
                SELECT id FROM {db_tables['relations']}
                WHERE member_id = ? AND partner_id = ?
            """, (
                relation_data['member_id'],
                relation_data['partner_id'],
            ))
            
            existing_relation = cursor.fetchone()
            
            if existing_relation and update:
                # Update existing relationship
                relation_id = existing_relation['id']
                update_fields = []
                params = []
                
                # Build update field list - including all provided fields
                optional_fields = [
                    'relation', 'original_family_id', 
                    'original_name', 'dad_name', 'mom_name',
                    'join_date', 'end_date'
                ]
                
                for field in optional_fields:
                    if field in relation_data and relation_data[field] is not None:
                        update_fields.append(f"{field} = ?")
                        params.append(relation_data[field])
                
                if not update_fields:
                    log.debug("No fields to update")
                    return relation_id
                
                # Add relation_id to parameters for WHERE clause
                params.append(relation_id)
                
                # Build and execute update query
                update_sql = f"""
                    UPDATE {db_tables['relations']}
                    SET {', '.join(update_fields)}
                    WHERE id = ?
                """
                
                cursor.execute(update_sql, params)
                conn.commit()
                
                log.debug(f"Updated existing relationship ID {relation_id}")
                return relation_id
            
            elif existing_relation and not update:
                raise ValueError(
                    f"Relation record already exists (ID: {existing_relation['id']})"
                    "Please set update=True to update the existing record."
                )
            
            # Add new relationship record
            fields = ['member_id', 'partner_id']
            placeholders = ['?', '?']
            values = [
                relation_data['member_id'],
                relation_data['partner_id']
            ]
            
            # Add optional fields
            optional_fields = [
                'relation', 'original_family_id', 
                'original_name', 'dad_name', 'mom_name',
                'join_date', 'end_date'
            ]
            
            for field in optional_fields:
                if field in relation_data:
                    fields.append(field)
                    placeholders.append('?')
                    values.append(relation_data[field])

            # Build and execute insert query
            insert_sql = f"""
                INSERT INTO {db_tables['relations']} ({', '.join(fields)})
                VALUES ({', '.join(placeholders)})
            """
            
            cursor.execute(insert_sql, values)
            relation_id = cursor.lastrowid
            conn.commit()
            
            log.debug(f"Added new relationship record ID: {relation_id}")
            return relation_id
            
    except sqlite3.Error:
        error_msg = f"Error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise

def delete_relation(relation_id: int) -> bool:
    """
    Permanently delete a relation from the database by its ID.
    
    Args:
        relation_id: The ID of the relation to delete (case-sensitive)
        
    Returns:
        bool: True if the relation was successfully deleted, False if the ID was not found or if an error occurred
        
    Raises:
        ValueError: If relation_id is empty or not a valid integer
        sqlite3.Error: If there's a database error during deletion
    """
    log.debug(f"Starting delete_relation for ID: {relation_id}")
    
    # Validate relation_id
    if not relation_id or not isinstance(relation_id, int):
        error_msg = "Relation ID must be a non-empty integer"
        log.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            log.debug("Database connection and cursor created")
            
            # First, verify the relation exists and get its details for logging
            log.debug(f"Checking if relation with ID {relation_id} exists")
            cursor.execute(f"""
                SELECT id, member_id, partner_id, relation 
                FROM {db_tables['relations']} 
                WHERE id = ?
                LIMIT 1
            """, (relation_id,))
            
            result = cursor.fetchone()
            if not result:
                log.warning(f"Cannot delete: Relation with ID '{relation_id}' not found")
                return False
            
            relation_id, member_id, partner_id, relation_type = result
            log.debug(f"Found relation - ID: {relation_id}, Member: {member_id}, Partner: {partner_id}, Type: {relation_type}")
            
            # Delete the relation
            cursor.execute(f"DELETE FROM {db_tables['relations']} WHERE id = ?", (relation_id,))
            rows_affected = cursor.rowcount
            conn.commit()
            
            if rows_affected > 0:
                log.debug(f"Successfully deleted relation ID {relation_id} (Member: {member_id}, Partner: {partner_id}, Type: {relation_type})")
                return True
            else:
                log.warning(f"No relation found with ID {relation_id} (Member: {member_id}, Partner: {partner_id}, Type: {relation_type})")
                return False
                
    except sqlite3.Error:
        error_msg = "Database error in delete_relation"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = "Unexpected error in delete_relation"
        log.error(error_msg, exc_info=True)
        raise

def get_family(family_id: int) -> Dict[str, Any]:
    """
    Retrieve a single family by its ID.
    
    Args:
        family_id: The ID of the family to retrieve (case-sensitive)
        
    Returns:
        Dict[str, Any]: A dictionary containing data of the family with the specified ID
        
    Raises:
        sqlite3.Error: When a database operation fails
    """
    with get_db_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT * FROM {db_tables['families']}
                WHERE id = ?
            """, (family_id,))
            
            family = cursor.fetchone()
            
            if family:
                return dict(family)
            else:
                return None
            
        except sqlite3.Error as e:
            raise sqlite3.Error(f"Database error in {fu.get_function_name()}: Error querying family: {str(e)}")

def get_families() -> List[Dict[str, Any]]:
    """
    Retrieve all the records from the families table.
    
    Returns:
        List[Dict[str, Any]]: A list of family dictionaries, where each dictionary contains
        all fields from the families table including id, name, background, url, created_at,
        and updated_at.
        
    Raises:
        sqlite3.Error: If there's a database error while fetching families
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT * FROM {db_tables['families']}
                ORDER BY id
            """)
            
            # Get column names from cursor description
            columns = [column[0] for column in cursor.description]
            
            # Convert each row to a dictionary
            families = []
            for row in cursor.fetchall():
                families.append(dict(zip(columns, row)))
                
            log.debug(f"Retrieved {len(families)} families from database")
            return families
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: while fetching families"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: while fetching families"
        log.error(error_msg, exc_info=True)
        raise

def insert_family(family_data: Dict[str, Any]) -> int:
    """
    Insert a new family into the `families` table by id.
    This function is used to import family data from a CSV/JSON
    file. All fields, except `updated_at` in `families` table 
    can be inserted.
    
    Args:
        family_data: A dictionary containing family information, 
        containing fields in `families` table.
    
    Returns:
        int: A positive integer ID of the inserted family record.
        Zero if failed.
        
    Raises:
        ValueError: If family_data is not a dictionary or if id is invalid.
        sqlite3.Error: If there is a database error.
    """
    try:
        if not isinstance(family_data, dict):
            error_msg = f"Invalid family data: {family_data}. Must be a dictionary."
            log.error(error_msg)
            raise ValueError(error_msg)
        id = family_data.get('id')
        if not id or not isinstance(id, int) or id <= 0:
            error_msg = f"Invalid family data: {family_data}. Invalid id."
            log.error(error_msg)
            raise ValueError(error_msg)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                INSERT INTO {db_tables['families']} (
                    id, name, background, url, created_at   )
                VALUES (?, ?, ?, ?, ?)
                """, (family_data['id'], 
                      family_data['name'], 
                      family_data.get('background'), 
                      family_data.get('url'), 
                      family_data.get('created_at')))
            if cursor.rowcount > 0:
                log.debug(f"Family {family_data['name']} inserted successfully.")
                conn.commit()
                return family_data['id']
            else:
                log.debug(f"Family {family_data['name']} not inserted.")
                return 0
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: Error inserting family"
        log.error(error_msg, exc_info=True)
        raise
    
def add_or_update_family(family_data: Dict[str, Any], update: bool = False) -> int:
    """
    Add or update family data to the `families` table.
    
    This function will insert a new family record into the families table.
    If update is True and a family with the same name already exists, it will update the existing record.
    
    Args:
        family_data: A dictionary containing family information, containing the following keys:
            - name (str): Family name (required)
            - background (str, optional): Family background/description
            - url (str, optional): Family website URL
        update (bool): If True and a family with the same name already exists, it will update the existing record.
        
    Returns:
        int: The ID of the newly added or updated family
        
    Raises:
        ValueError: If missing required fields or data is invalid
        sqlite3.IntegrityError: If database integrity constraint is violated
        sqlite3.Error: Other database related errors
        
    Example:
        >>> family_data = {
        ...     'name': 'Zhang Family',
        ...     'background': 'Zhang family from Taiwan',
        ...     'url': 'http://example.com/zhang-family'
        ... }
        >>> family_id = add_or_update_family(family_data, True)
    """
    # Validate required fields
    if 'name' not in family_data or not family_data['name']:
        raise ValueError("Family name is required")
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if a family with the same name already exists
            cursor.execute(f"""
                SELECT id FROM {db_tables['families']}
                WHERE name = ?
            """, (family_data['name'],))
            
            existing_family = cursor.fetchone()
            
            if existing_family and update:
                # Update existing family
                family_id = existing_family['id']
                update_fields = []
                params = []
                
                # Create update field list - include all provided fields
                for field, value in family_data.items():
                    update_fields.append(f"{field} = ?")
                    params.append(value)
                
                if not update_fields:
                    log.debug("No fields need to be updated")
                    return family_id
                
                # Add updated_at timestamp
                update_fields.append("updated_at = datetime('now')")
                
                # Add family_id to parameters for WHERE clause
                params.append(family_id)
                
                # Create and execute update query
                update_sql = f"""
                    UPDATE {db_tables['families']}
                    SET {', '.join(update_fields)}
                    WHERE id = ?
                """
                
                cursor.execute(update_sql, params)
                conn.commit()
                
                log.debug(f"Updated family ID {family_id}: {family_data.get('name')}")
                return family_id
            
            elif existing_family and not update:
                raise ValueError(
                    f"Family name '{family_data['name']}' already exists."
                    "Please set update=True to update the existing family."
                )
            
            # Add new family
            fields = ['name']
            placeholders = ['?']
            values = [family_data['name']]
            
            # Add optional fields
            optional_fields = {'background', 'url'}
            for field in optional_fields:
                if field in family_data and family_data[field] is not None:
                    fields.append(field)
                    placeholders.append('?')
                    values.append(family_data[field])
            
            # Add timestamps
            fields.extend(['created_at', 'updated_at'])
            placeholders.extend(["datetime('now')", "datetime('now')"])
            
            # Build and execute insert query
            insert_sql = f"""
                INSERT INTO {db_tables['families']} ({', '.join(fields)})
                VALUES ({', '.join(placeholders)})
            """
            
            cursor.execute(insert_sql, values)
            family_id = cursor.lastrowid
            conn.commit()
            
            log.debug(f"Added new family: {family_data.get('name')} (ID: {family_id})")
            return family_id
            
    except sqlite3.IntegrityError as e:
        error_msg = f"Error in {fu.get_function_name()}: adding/updating family"
        log.error(f"{error_msg}: {str(e)}")
        raise ValueError(error_msg) from e
        
    except sqlite3.Error:
        error_msg = f"Error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise

def delete_family(family_id: int) -> bool:
    """
    Permanently delete a family from the database by its ID.
    
    Args:
        family_id: The ID of the family to delete (case-sensitive)
        
    Returns:
        bool: True if the family was successfully deleted, False if the ID was not found or if an error occurred
        
    Raises:
        ValueError: If family_id is empty or not a valid integer
        sqlite3.Error: If there's a database error during deletion
    """
    # Validate family_id
    if not family_id or not isinstance(family_id, int):
        error_msg = "Family ID must be a non-empty integer"
        log.error(error_msg)
        raise ValueError(error_msg)
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # First, verify the family exists and get its ID for logging
            cursor.execute(f"""
                SELECT id FROM {db_tables['families']} 
                WHERE id = ?
                LIMIT 1
            """, (family_id,))
            
            result = cursor.fetchone()
            if not result:
                log.warning(f"Cannot delete: Family with ID '{family_id}' not found")
                return False
                
            family_id = dict(result).get('id')
            
            # Perform the deletion
            cursor.execute(f"""
                DELETE FROM {db_tables['families']} 
                WHERE id = ?
            """, (family_id,))
            
            rows_affected = cursor.rowcount
            conn.commit()
            
            if rows_affected > 0:
                log.debug(f"Successfully deleted family: {family_id}")
                return True
                
            log.warning(f"No rows affected when deleting family: {family_id}")
            return False
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}"
        log.error(error_msg, exc_info=True)
        raise
    
def get_mirrors() -> List[Dict[str, Any]]:
    """
    Retrieve all the records from the mirrors table.
    
    Returns:
        List[Dict[str, Any]]: A list of mirror dictionaries, where each dictionary contains
        all fields from the mirrors table including:
        id, name, alias, born, died, gen_order,
        url, dad_id, mom_id, created_at, updated_at.
        
    Raises:
        sqlite3.Error: If there's a database error while fetching mirrors
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT * FROM {db_tables['mirrors']}
                ORDER BY id ASC
            """)
            
            # Get column names from cursor description
            columns = [column[0] for column in cursor.description]
            
            # Convert each row to a dictionary
            mirrors = []
            for row in cursor.fetchall():
                mirrors.append(dict(zip(columns, row)))
                
            log.debug(f"Retrieved {len(mirrors)} mirrors from database")
            return mirrors
            
    except sqlite3.Error:
        error_msg = f"Database error in {fu.get_function_name()}: while fetching mirrors"
        log.error(error_msg, exc_info=True)
        raise
    except Exception:
        error_msg = f"Unexpected error in {fu.get_function_name()}: while fetching mirrors"
        log.error(error_msg, exc_info=True)
        raise
    
def import_users(users: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Import users into the db_tables['users'] table.
    
    Args:
        users: List of user dictionaries with required fields.
        - id (int): User identifier (required)
        - email (str): User email (required)
        - password_hash (str): User password hash (required)
        - salt (str): User salt (required)
        
    Returns:
        Dict with import results
        {
            'success': bool,
            'imported': int,
            'skipped': int,
            'errors': List[str]
        }
    """
    imported = 0
    skipped = 0
    errors = []
    required_fields = ['id', 'email', 'password_hash', 'salt']

    with get_db_connection() as conn:
        conn.cursor()
    
        for i, user in enumerate(users, 1):
            try:
                # Check for required fields
                missing_fields = [field for field in required_fields if field not in user]
                if missing_fields:
                    errors.append(f"User {i} is missing required fields: {', '.join(missing_fields)}")
                    skipped += 1
                    continue
                
                
                # Prepare user data for add_user function
                user_data = {
                    'id': int(user.get('id')),
                    'email': user.get('email'),
                    'password_hash': user.get('password_hash'),
                    'salt': user.get('salt'),
                    'is_admin': user.get('is_admin', User_State['f_member']),
                    'is_active': user.get('is_active', Subscriber_State['inactive']),
                    'l10n': user.get('l10n', 'US'),
                    'token': user.get('token'),
                    'created_at': user.get('created_at'),
                    'family_id': int(user.get('family_id')) if user.get('family_id') else 0,
                    'member_id': int(user.get('member_id')) if user.get('member_id') else 0
                }
            
                user_id = insert_user(user_data)
                if user_id > 0:
                    imported += 1
                else:
                    errors.append(f"User {i} ({user.get('email', 'unknown')}): insert failed")
                    skipped += 1
            
            except Exception as e:
                errors.append(f"Error in {fu.get_function_name()}: importing user {i} ({user['email']})")
                log.error("Failed to import user", exc_info=e)
                skipped += 1
    
        if imported > 0:
            conn.commit()
    
    return {
        'success': len(errors) == 0,
        'imported': imported,
        'skipped': skipped,
        'errors': errors
        }

def import_members(members: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Import members into the db_tables['members'] table.
    
    Args:
        members: List of member dictionaries with required fields:
        - id (int): Member identifier (required)
        - name (str): Full name (required)
        - born (str): Date of birth in YYYY-MM-DD format (required)
        - gen_order (int): Generation order (required)
    
    Returns:
        Dict with import results:
        {
            'success': bool,
            'imported': int,
            'skipped': int,
            'errors': List[str]
        }
    """
    imported = 0
    skipped = 0
    errors = []
    
    required_fields = ['id', 'name', 'born', 'gen_order']
    
    with get_db_connection() as conn:
        conn.cursor()
        
        for i, member in enumerate(members, 1):
            try:
                # Check for required fields
                missing_fields = [field for field in required_fields if field not in member]
                if missing_fields:
                    errors.append(f"Member {i} is missing required fields: {', '.join(missing_fields)}")
                    skipped += 1
                    continue
                
                # Prepare member data
                member_data = {
                    'id': int(member['id']),
                    'name': member['name'],
                    'family_id': int(member['family_id']) if member['family_id'] and member['family_id'].strip() else 0,
                    'born': member['born'],
                    'sex': member['sex'],
                    'gen_order': int(member['gen_order']) if member['gen_order'] and member['gen_order'].strip() else 0,
                    'alias': member.get('alias'),
                    'email': member.get('email'),
                    'url': member.get('url'),
                    'died': member.get('died'),
                    'dad_id': int(member.get('dad_id')) if member.get('dad_id') and member.get('dad_id').strip() else 0,
                    'mom_id': int(member.get('mom_id')) if member.get('mom_id') and member.get('mom_id').strip() else 0,
                    'created_at': member.get('created_at')
                }
                
                # Add new member only
                member_id = insert_member(member_data)
                if member_id > 0:
                    imported += 1
                else:
                    errors.append(f"Failed to import member {i}: {member.get('name', 'Unknown')}")
                    skipped += 1
                
            except Exception as e:
                errors.append(f"Error in {fu.get_function_name()}: importing member {i} ({member.get('name', 'Unknown')})")
                log.error("Failed to import record", exc_info=e)
                skipped += 1
        
        if imported > 0:
            conn.commit()
    
    return {
        'success': len(errors) == 0,
        'imported': imported,
        'skipped': skipped,
        'errors': errors
    }

def import_relations(relations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Import member relations into the db_tables['relations'] table.
    This function is used to import family data from a CSV/JSON
    file. All fields, except `updated_at` in `relations` table 
    can be inserted.
    
    Args:
        relations: List of relation dictionaries with required fields:
        - member_id (int): ID of the first member in the relationship (required)
        - partner_id (int): ID of the second member in the relationship (required)
        - relation (str): Type of relationship, e.g., 'spouse', 'parent' (required)
    
    Returns:
        Dict with import results
        {
            'success': bool,
            'imported': int,
            'skipped': int,
            'errors': List[str]
        }
    """
    imported = 0
    skipped = 0
    errors = []
    
    required_fields = ['id', 'member_id', 'partner_id', 'relation']
    
    with get_db_connection() as conn:
        conn.cursor()
        
        for i, rel in enumerate(relations, 1):
            try:
                # Check for required fields
                missing_fields = [field for field in required_fields if field not in rel]
                if missing_fields:
                    errors.append(f"Relation {i} is missing required fields: {', '.join(missing_fields)}")
                    skipped += 1
                    continue
                
                # prepare relation data for insert_relation function
                relation_data = {
                    'id': int(rel.get('id')),
                    'member_id': int(rel.get('member_id')),
                    'partner_id': int(rel.get('partner_id')),
                    'relation': rel.get('relation'),
                    'join_date': rel.get('join_date'),
                    'end_date': rel.get('end_date'),
                    'original_family_id': int(rel.get('original_family_id')),
                    'original_name': rel.get('original_name'),
                    'dad_name': rel.get('dad_name'),
                    'mom_name': rel.get('mom_name'),
                    'created_at': rel.get('created_at')
                }
                
                # add new relation only
                relation_id = insert_relation(relation_data)
                if relation_id > 0:
                    imported += 1
                else:
                    errors.append(f"Failed to import relation {i}: {rel.get('member_id', '?')}-{rel.get('partner_id', '?')}")
                    skipped += 1
                
            except Exception as e:
                errors.append(f"Error in {fu.get_function_name()}: importing relation {i} (members {rel.get('member_id', '?')}-{rel.get('partner_id', '?')})")
                log.error("Failed to import record", exc_info=e)
                skipped += 1
        
        if imported > 0:
            conn.commit()
    
    return {
        'success': len(errors) == 0,
        'imported': imported,
        'skipped': skipped,
        'errors': errors
    }

def import_families(families: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Import families into the db_tables['families'] table.
    
    Args:
        families: List of family dictionaries with required fields:
            - id (int): Family identifier (required)
            - name (str): Family name (required)
            
    Returns:
        Dict with import results
        {
            'success': bool,
            'imported': int,
            'skipped': int,
            'errors': List[str]
        }
    """
    imported = 0
    skipped = 0
    errors = []
    required_fields = ['id', 'name']
    
    with get_db_connection() as conn:
        conn.cursor()
        
        for i, family in enumerate(families, 1):
            try:
                # Check for required fields
                missing_fields = [field for field in required_fields if field not in family]
                if missing_fields:
                    errors.append(f"Family {i} is missing required fields: {', '.join(missing_fields)}")
                    skipped += 1
                    continue
                
                # prepare family data for insert_family function
                family_data = {
                    'id': int(family.get('id')),
                    'name': family.get('name'),
                    'url': family.get('url'),
                    'background': family.get('background'),
                    'created_at': family.get('created_at')
                }
                family_id = insert_family(family_data)
                if family_id > 0:
                    imported += 1
                else:
                    errors.append(f"Failed to import family {i}: {family.get('name', 'Unknown')}")
                    skipped += 1
                
            except Exception as e:
                errors.append(f"Error in {fu.get_function_name()}: importing family {i} ('{family.get('name', 'Unknown')}')")
                log.error("Failed to import record", exc_info=e)
                skipped += 1
        
        if imported > 0:
            conn.commit()
    
    return {
        'success': len(errors) == 0,
        'imported': imported,
        'skipped': skipped,
        'errors': errors
    }

def import_from_file(file_path: Union[str, Path], table: str) -> Dict[str, Any]:
    """
    Import records from a JSON or CSV file into the specified table.
    
    Args:
        file_path: Path to the JSON or CSV file containing 
        records data
        table: Name of the table to import records into
        
    Returns:
        Dict with import results: {
            'success': bool,
            'imported': int,
            'skipped': int,
            'errors': List[str]
        }
    """
    file_path = Path(file_path)
    if not file_path.exists():
        return {
            'success': False,
            'imported': 0,
            'skipped': 0,
            'errors': [f"File not found: {file_path}"]
        }
    
    try:
        if file_path.suffix.lower() == '.json':
            with open(file_path, 'r', encoding='utf-8') as f:
                rcds = json.load(f)
                if not isinstance(rcds, list):
                    rcds = [rcds]  # Handle single user object
        elif file_path.suffix.lower() == '.csv':
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rcds = list(reader)
        else:
            return {
                'success': False,
                'imported': 0,
                'skipped': 0,
                'errors': ["Unsupported file format. Please use JSON or CSV."]
            }
        if table == db_tables['users']:
            return import_users(rcds)
        elif table == db_tables['members']:
            return import_members(rcds)
        elif table == db_tables['relations']:
            return import_relations(rcds)
        elif table == db_tables['families']:
            return import_families(rcds)
        else:
            return {
                'success': False,
                'imported': 0,
                'skipped': 0,
                'errors': [f"Unsupported table: {table}"]
        }
    
    except Exception as e:
        log.error("Error reading file", exc_info=e)
        return {
            'success': False,
            'imported': 0,
            'skipped': 0,
            'errors': ["Error reading file"]
        }

def export_to_file(file_path: Union[str, Path], table: str) -> Dict[str, Any]:
    """
    Export a table from the database to a JSON or CSV file.
    
    Args:
        file_path: Path to save the exported file (must end with .json or .csv)
        table: Name of the table to export
        
    Returns:
        Dict with export results
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Get the appropriate data based on table name
        table_map = {
            db_tables['users']: get_users,
            db_tables['members']: get_members,
            db_tables['relations']: get_relations,
            db_tables['families']: get_families,
            db_tables['mirrors']: get_mirrors
        }
        
        if table not in table_map:
            return {
                'success': False,
                'message': f"Unsupported table: {table}. Must be one of: {', '.join(table_map.keys())}"
            }
        
        # Get the records
        rcds = table_map[table]()
        
        # Ensure all records have consistent field types
        if rcds and table == db_tables['relations']:
            for rcd in rcds:
                # Ensure all relation records have the same fields
                rcd.setdefault('end_date', '')
                rcd.setdefault('original_family_id', 0)
                rcd.setdefault('original_name', '')
        
        # Write to file
        if file_path.suffix.lower() == '.json':
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(rcds, f, indent=2, ensure_ascii=False, default=str)
        elif file_path.suffix.lower() == '.csv':
            if rcds:
                # Get all possible fieldnames from all records
                fieldnames = set()
                for rcd in rcds:
                    fieldnames.update(rcd.keys())
                fieldnames = sorted(fieldnames)
                
                with open(file_path, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for rcd in rcds:
                        # Ensure all records have all fields
                        row = {field: rcd.get(field, '') for field in fieldnames}
                        writer.writerow(row)
        else:
            return {
                'success': False,
                'message': "Unsupported file format. Please use .json or .csv"
            }
        
        return {
            'success': True,
            'message': f"Successfully exported {len(rcds)} records to {file_path}",
            'file_path': str(file_path.absolute()),
            'count': len(rcds)
        }
    
    except Exception as e:
        log.error("Error exporting records", exc_info=e)
        return {
            'success': False,
            'message': "Error exporting records"
        }

def get_table_columns(table: str) -> List[str]:
    """
    Get the column names of a table.
    
    Args:
        table: Name of the table to query
        
    Returns:
        List[str]: List of column names in the table.
        None if table does not exist or an error occurs.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [column[1] for column in cursor.fetchall()]
            return columns
    except sqlite3.Error as e:
        log.error(f"Database error in {fu.get_function_name()}: fetching table columns: {str(e)}")
        raise sqlite3.Error(f"Failed in {fu.get_function_name()}: to fetch table columns: {str(e)}")

def get_total_records(table: str) -> int:
    """
    Get the total number of records in a table.
    
    Args:
        table: Name of the table to query
        
    Returns:
        int: Total number of records in the table.
        None if table does not exist or an error occurs.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            result = cursor.fetchone()
            return result[0] if result else 0
    except sqlite3.Error as e:
        log.error(f"Database error in {fu.get_function_name()}: fetching total records: {str(e)}")
        raise sqlite3.Error(f"Failed in {fu.get_function_name()}: to fetch total records: {str(e)}")

def get_children(member_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve the member records of the children given a member ID.
    The children, retrieved from the `members` table, 
    where the `dad_id` or `mom_id` matches the given member ID, 
    are then returned.
    
    Args:
        member_id: ID of the member to query
        
    Returns:
        List of dictionaries containing child member records
        If no child is found, an empty list is returned
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Find all records where the given member_id is either dad_id or mom_id
            cursor.execute(f"""
                SELECT * FROM {db_tables['members']} 
                WHERE dad_id = ? OR mom_id = ?
                ORDER BY born
            """, (member_id, member_id))
            
            # Convert rows to list of dictionaries
            children = [dict(row) for row in cursor.fetchall()]
            return children
    except sqlite3.Error as e:
        log.error(f"Database error in {fu.get_function_name()}: fetching children: {str(e)}")
        raise sqlite3.Error(f"Failed in {fu.get_function_name()} to fetch children: {str(e)}")
    except Exception as e:
        log.error(f"Unexpected error in {fu.get_function_name()}: fetching children: {str(e)}")
        raise

def get_parents(member_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve the member records of the parents given a member ID.
    Both parents, identified by 'dad_id' and 'mom_id', if exist, 
    are used to query the `members` table and the records are returned.
    
    Args:
        member_id: ID of the member to query
        
    Returns:
        List of dictionaries containing parent member records
        If no parent is found, an empty list is returned
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT * FROM {db_tables['members']} 
                WHERE id = ?""", (member_id,))
            result = cursor.fetchone()
            if not result:
                return []
            
            parents = []
            # Get dad
            if result['dad_id']:
                cursor.execute(f"""
                    SELECT * FROM {db_tables['members']} 
                    WHERE id = ?
                    """, (result['dad_id'],))
                
                parent = cursor.fetchone()
                if parent:
                    parents.append(dict(parent))  # Convert to dict
            # Get mom
            if result['mom_id']:
                cursor.execute(f"""
                    SELECT * FROM {db_tables['members']} 
                    WHERE id = ?""", (result['mom_id'],))
                
                parent = cursor.fetchone()
                if parent:
                    parents.append(dict(parent))  # Convert to dict
            return parents
    except sqlite3.Error as e:
        log.error(f"Database error in {fu.get_function_name()}: fetching parents: {str(e)}")
        raise sqlite3.Error(f"Failed in {fu.get_function_name()} to fetch parents: {str(e)}")
    except Exception as e:
        log.error(f"Unexpected error in {fu.get_function_name()}: fetching parents: {str(e)}")
        raise sqlite3.Error(f"Failed in {fu.get_function_name()} to fetch parents: {str(e)}")

# Initialize database (if not already initialized)
init_db()
if __name__ == "__main__":
    # Test database connection and initialization
    print("Database initialization completed")
    print(f"Database location: {db_path}")
    
    # Test query for living members
    try: 
        updated = update_relations_when_died(1650, '2023-12-31')
        if updated[0]:
            print(f"Updated member count: {updated[1]}\nUpdated relationships count: {updated[2]}")
    except sqlite3.Error as e:
        print(f"Error: {str(e)}")
