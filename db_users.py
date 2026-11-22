"""User and subscriber records."""
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import funcUtils as fu
import auth_utils as au
from db_connection import (
    USER_COLUMNS,
    Subscriber_State,
    User_State,
    column_assignments,
    db_tables,
    family_ids_equal,
    get_db_connection,
    log,
    normalize_subscriber_email,
    parse_family_id,
    quote_ident,
)


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
    normalized = normalize_subscriber_email(email)
    if not normalized:
        log.warning("Invalid email address provided to remove_subscriber")
        return False

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, is_active FROM {db_tables['users']}
                WHERE LOWER(email) = ?
                ORDER BY CASE WHEN email = ? THEN 0 ELSE 1 END, id ASC
                LIMIT 1
            """, (normalized, normalized))

            result = cursor.fetchone()
            if not result:
                log.warning(f"Email not found: {email}")
                return False

            if result['is_active'] == Subscriber_State['inactive']:
                log.debug(f"Email already unsubscribed: {email}")
                return True

            cursor.execute(f"""
                UPDATE {db_tables['users']}
                SET is_active = ?, token = '', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (Subscriber_State['inactive'], result['id']))
            
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


def verify_subscription_token(email, token) -> bool:
    """True when this address holds this subscription token, in any state.

    The address match is case-insensitive. Pending rows can be confirmed.
    ``verify_token`` still requires an already-active subscriber.
    """
    normalized = normalize_subscriber_email(email)
    if not normalized or not token:
        return False
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                f"""
                SELECT id FROM {db_tables['users']}
                WHERE LOWER(email) = ? AND token = ?
                ORDER BY CASE WHEN email = ? THEN 0 ELSE 1 END, id ASC
                LIMIT 1
                """,
                (normalized, token, normalized),
            ).fetchone()
        return row is not None
    except sqlite3.Error as exc:
        log.error("Database error in verify_subscription_token: %s", exc)
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


def list_family_subscribers(family_id, state=None) -> List[Dict[str, Any]]:
    """User rows whose ``family_id`` equals this family.

    Subscription state lives on the shared ``users`` table, which is the
    same table ``ops_svr`` updates. ``state`` is ``active``, ``pending``,
    ``inactive``, or ``in_contact``. Omit it to return every row for the
    family. A blank or non-numeric family id matches nothing.
    """
    try:
        number = parse_family_id(family_id)
    except ValueError:
        return []
    if number is None:
        return []
    if state is not None and state not in Subscriber_State:
        raise ValueError(
            f"Invalid state {state!r}. Must be one of: {', '.join(Subscriber_State)}"
        )
    query = f"""
        SELECT id, email, is_active, l10n, family_id, created_at, updated_at
        FROM {db_tables['users']}
        WHERE family_id = ?
    """
    params = [number]
    if state is not None and state != "all":
        query += " AND is_active = ?"
        params.append(Subscriber_State[state])
    query += " ORDER BY email COLLATE NOCASE ASC"
    try:
        with get_db_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as exc:
        log.error("Database error in list_family_subscribers: %s", exc)
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
    normalized = normalize_subscriber_email(email)
    if not normalized:
        return None

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Case-insensitive. Prefer the row already stored in lowercase.
            cursor.execute(f"""
                SELECT * FROM {db_tables['users']}
                WHERE LOWER(email) = ?
                ORDER BY CASE WHEN email = ? THEN 0 ELSE 1 END, id ASC
                LIMIT 1
            """, (normalized, normalized))

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
            - l10n: Language code stored as text. There is no database
              enum or check constraint. The operations server writes the
              catalog keys US, 繁中, 简中, 日本語, and 한국어. Other values
              already stored, including Streamlit languages such as
              Spanish, are left unchanged.
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
                
                # password is stored as password_hash and salt. There is no
                # password column. Other keys must be real user columns.
                assignments, assigned = column_assignments(
                    user_data,
                    USER_COLUMNS,
                    ignore={"password"},
                )
                if user_data.get("password"):
                    password_hash, salt = au.hash_password(user_data["password"])
                    assignments.extend(["password_hash = ?", "salt = ?"])
                    assigned.extend([password_hash, salt])
                update_fields.extend(assignments)
                params.extend(assigned)
                
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
                user_id = au.create_user(email, password, 
                    role=user_fields['is_admin'],
                    is_active=user_fields['is_active'],
                    l10n=user_fields['l10n'],
                    family_id=user_fields['family_id'],
                    member_id=user_fields['member_id'])
                if user_id:
                    return True, ""
                return False, "Failed to create user"
                
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
            users_table = quote_ident(db_tables['users'])
            if role == 'all':
                cursor.execute(f"SELECT * FROM {users_table} ORDER BY id ASC")
            else:
                if isinstance(role, str):
                    roles = [int(part.strip()) for part in role.split(",") if part.strip()]
                elif isinstance(role, (list, tuple, set)):
                    roles = [int(part) for part in role]
                else:
                    roles = [int(role)]
                if not roles:
                    return []
                placeholders = ", ".join("?" for _ in roles)
                cursor.execute(
                    f"SELECT * FROM {users_table} WHERE is_admin IN ({placeholders}) ORDER BY id ASC",
                    roles,
                )
            
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


def is_family_member(email, family_id) -> bool:
    """True when this address's user row belongs to ``family_id``.

    Membership is ``users.family_id`` equaling the family id as an integer
    (``1`` and ``\"01\"`` match). The address match is case-insensitive. A missing
    row, a NULL family id, and a different family id are all non-members.
    Those cases are not distinguished.
    """
    normalized = normalize_subscriber_email(email)
    try:
        expected = parse_family_id(family_id)
    except ValueError:
        return False
    if not normalized or expected is None:
        return False
    user = get_subscriber(normalized)
    if not user:
        return False
    return family_ids_equal(user.get("family_id"), family_id)


def add_or_update_subscriber(user_data, update=True):
    """Set subscription state on an existing user, or insert a subscriber row.

    Does not change ``family_id`` or the admin role. The stored address is
    rewritten to the lowercase form when that spelling is free. Returns True
    on success.
    """
    if not isinstance(user_data, dict):
        raise ValueError("Missing required fields: email, is_active, token, l10n")
    required = ("email", "is_active", "token", "l10n")
    missing = [field for field in required if field not in user_data]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    email = normalize_subscriber_email(user_data.get("email"))
    if not email:
        raise ValueError("Missing required fields: email")
    is_active = user_data.get("is_active")
    token = user_data.get("token")
    lang = user_data.get("l10n")

    existing = get_subscriber(email)
    with get_db_connection() as conn:
        if existing and not update:
            raise sqlite3.IntegrityError(f"Subscriber with email {email} already exists")
        if existing:
            user_id = existing["id"]
            taken = conn.execute(
                f"SELECT id FROM {db_tables['users']} WHERE email = ? AND id != ?",
                (email, user_id),
            ).fetchone()
            stored_email = existing["email"] if taken else email
            if lang:
                conn.execute(
                    f"""
                    UPDATE {db_tables['users']}
                    SET email = ?, is_active = ?, token = ?, l10n = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (stored_email, is_active, token, lang, user_id),
                )
            else:
                conn.execute(
                    f"""
                    UPDATE {db_tables['users']}
                    SET email = ?, is_active = ?, token = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (stored_email, is_active, token, user_id),
                )
            return True

        conn.execute(
            f"""
            INSERT INTO {db_tables['users']} (email, is_active, token, l10n, family_id)
            VALUES (?, ?, ?, ?, NULL)
            """,
            (email, is_active, token, lang),
        )
        return True


def create_user(email, state, lang=None):
    """Insert a user row for the contact form. Does not assign a family.

    This is not ``auth_utils.create_user``. It does not set a password.
    ``family_id`` is left NULL so the address is not a member of any family
    until an admin registers it. Returns the new id, or None.
    """
    import email_utils as eu

    normalized = normalize_subscriber_email(email)
    if not normalized or not eu.validate_email(normalized):
        log.error("Invalid email provided to create_user")
        return None
    if state not in Subscriber_State.values():
        log.error("Invalid state provided to create_user: %s", state)
        return None
    if get_subscriber(normalized):
        log.warning("User with email %s already exists", normalized)
        return None
    try:
        with get_db_connection() as conn:
            conn.execute(
                f"""
                INSERT INTO {db_tables['users']} (email, is_active, l10n, family_id)
                VALUES (?, ?, ?, NULL)
                """,
                (normalized, state, lang),
            )
            row = conn.execute("SELECT last_insert_rowid()").fetchone()
            return row[0] if row else None
    except sqlite3.Error as exc:
        log.error("Database error while creating user %s: %s", normalized, exc)
        return None


def get_user(user_id):
    """Return one user row by id, or None."""
    if not isinstance(user_id, int) or user_id <= 0:
        return None
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                f"SELECT * FROM {db_tables['users']} WHERE id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error as exc:
        log.error("Database error while reading user %s: %s", user_id, exc)
        return None


def get_user_email(user_id):
    """Return the email for a user id, or None."""
    user = get_user(user_id)
    if not user:
        return None
    return user.get("email")


def update_user(user_id, update_fields):
    """Update columns on one user row. Returns the id, or None.

    ``id`` and ``created_at`` are ignored. Unknown column names are ignored.
    """
    if not isinstance(user_id, int) or user_id <= 0:
        return None
    if not isinstance(update_fields, dict) or not update_fields:
        return None
    try:
        with get_db_connection() as conn:
            columns = {
                row[1]
                for row in conn.execute(
                    f"PRAGMA table_info({quote_ident(db_tables['users'])})"
                ).fetchall()
            }
            columns.discard("id")
            columns.discard("created_at")
            fields = []
            params = []
            for key, value in update_fields.items():
                if key in columns and value is not None:
                    fields.append(f"{quote_ident(key)} = ?")
                    params.append(value)
            if not fields:
                return None
            params.append(user_id)
            cursor = conn.execute(
                f"UPDATE {db_tables['users']} SET {', '.join(fields)} WHERE id = ?",
                tuple(params),
            )
            if cursor.rowcount > 0:
                return user_id
            return None
    except sqlite3.Error as exc:
        log.error("Database error while updating user %s: %s", user_id, exc)
        return None
