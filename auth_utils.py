"""
# Add parent directory to path to allow absolute imports
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))


Authentication Utilities

This module handles authentication-related functions to avoid circular imports.
"""
import logging
import hmac
import re
import sqlite3
import hashlib
import secrets
import os
import db_utils as dbm
import context_utils as cu
import funcUtils as fu

# PBKDF2-HMAC-SHA256. New hashes use the current iteration count and record it
# in the stored string. Older rows are a bare hex digest from LEGACY_PBKDF2_ITERATIONS.
PBKDF2_ITERATIONS = 600_000
LEGACY_PBKDF2_ITERATIONS = 100_000
_HASH_PREFIX = "pbkdf2_sha256$"
# SHA-256 hex digest. New password hashes and stored reset tokens use this shape.
# Legacy password hashes are a bare digest; legacy reset tokens are url-safe strings.
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

def _pbkdf2_hex(password, salt, iterations):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    ).hex()

def hash_password(password, salt=None, iterations=None):
    """Hash password with salt using PBKDF2-HMAC-SHA256.

    Returns (stored_hash, salt). stored_hash includes the iteration count:
    ``pbkdf2_sha256$<iterations>$<hex digest>``.
    """
    if salt is None:
        salt = secrets.token_hex(16)
    if iterations is None:
        iterations = PBKDF2_ITERATIONS
    digest = _pbkdf2_hex(password, salt, iterations)
    return f"{_HASH_PREFIX}{int(iterations)}${digest}", salt

def _split_stored_hash(stored_hash):
    """Return (iterations, digest) or None if the value is not a known hash."""
    if not isinstance(stored_hash, str) or not stored_hash:
        return None
    if stored_hash.startswith(_HASH_PREFIX):
        rest = stored_hash[len(_HASH_PREFIX):]
        iter_text, sep, digest = rest.partition("$")
        if sep and iter_text.isdigit() and _SHA256_HEX.fullmatch(digest):
            return int(iter_text), digest
        return None
    # Legacy rows: hex digest only, produced with 100k iterations.
    if _SHA256_HEX.fullmatch(stored_hash):
        return LEGACY_PBKDF2_ITERATIONS, stored_hash
    return None

def _password_ok(password, salt, stored_hash):
    """Constant-time check of password against a stored hash."""
    parsed = _split_stored_hash(stored_hash)
    if parsed is None or not isinstance(salt, str):
        return False
    iterations, digest = parsed
    try:
        candidate = _pbkdf2_hex(password, salt, iterations)
    except (TypeError, ValueError):
        return False
    if len(candidate) != len(digest):
        return False
    return hmac.compare_digest(candidate, digest)

def _needs_rehash(stored_hash):
    parsed = _split_stored_hash(stored_hash)
    if parsed is None:
        return False
    iterations, _digest = parsed
    return iterations != PBKDF2_ITERATIONS or not stored_hash.startswith(_HASH_PREFIX)

def _rehash_password_if_needed(cursor, user_id, password, stored_hash):
    """Replace a legacy or outdated hash after a successful login."""
    if not _needs_rehash(stored_hash):
        return
    new_hash, new_salt = hash_password(password)
    cursor.execute(f"""
        UPDATE {dbm.db_tables['users']}
        SET password_hash = ?, salt = ?
        WHERE id = ?
    """, (new_hash, new_salt, user_id))

def hash_reset_token(token):
    """SHA-256 hex digest of a password-reset token. The raw token is not stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def is_stored_reset_token(value):
    """True when value is already a SHA-256 hex digest rather than a raw token."""
    return isinstance(value, str) and _SHA256_HEX.fullmatch(value) is not None

def verify_fmember(email, password):
    """Verify family member credentials and membership status
    
    Args:
        email: The email address of the member
        password: The password of the member
        
    Returns:
        bool: True if the credentials are valid and user is a member, False otherwise
    """
    try:
        with dbm.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, password_hash, salt,
                family_id, member_id, l10n 
                FROM {dbm.db_tables['users']} 
                WHERE email = ? 
                AND is_admin = {dbm.User_State['f_member']} 
            """, (email,))
            
            result = cursor.fetchone()
            if result is None:
                return False
                
            user_id, stored_hash, salt, family_id, member_id, l10n = result
            if _password_ok(password, salt, stored_hash):
                _rehash_password_if_needed(cursor, user_id, password, stored_hash)
                # Update last login time with current timestamp
                try:
                    cursor.execute(f"""
                        UPDATE {dbm.db_tables['users']} 
                        SET updated_at = datetime('now')
                        WHERE id = ?
                    """, (user_id,))
                    conn.commit()
                except sqlite3.Error as update_error:
                    fu.show_user_error("⚠️ Error updating login time", update_error, warn=True)
                    # Continue even if update fails, as auth was successful
                # Update context
                cu.update_context({
                    'member_id': member_id,
                    'family_id': family_id,
                    'language': l10n
                })  
                return True
            
            return False
            
    except sqlite3.Error as e:
        fu.show_user_error("Error verifying member", e)
        return False

def verify_padmin(email, password):
    """Verify platform admin credentials
    
    Args:
        email: The email address of the admin
        password: The password of the admin
        
    Returns:
        bool: True if the credentials are valid, False otherwise
    """
    try:
        with dbm.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, password_hash, salt, 
                family_id, member_id, l10n  
                FROM {dbm.db_tables['users']} 
                WHERE email = ? 
                AND is_admin = {dbm.User_State['p_admin']} 
            """, (email,))
            
            result = cursor.fetchone()
            if result is None:
                return False
                
            user_id, stored_hash, salt, family_id, member_id, l10n = result
            if _password_ok(password, salt, stored_hash):
                _rehash_password_if_needed(cursor, user_id, password, stored_hash)
                # Update last login time with current timestamp
                try:
                    cursor.execute(f"""
                        UPDATE {dbm.db_tables['users']} 
                        SET updated_at = datetime('now')
                        WHERE id = ?
                    """, (user_id,))
                    conn.commit()
                except sqlite3.Error as update_error:
                    fu.show_user_error("⚠️ Error updating login time", update_error, warn=True)
                    # Continue even if update fails, as auth was successful
                # Update context
                cu.update_context({
                    'member_id': member_id,
                    'family_id': family_id,
                    'language': l10n
                })  
                
                return True
            
            return False
            
    except sqlite3.Error as e:
        fu.show_user_error("Error verifying admin", e)
        return False

def verify_fadmin(email, password):
    """Verify family admin credentials
    
    Args:
        email: The email address of the admin
        password: The password of the admin
        
    Returns:
        bool: True if the credentials are valid, False otherwise
    """
    try:
        with dbm.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, password_hash, salt,
                family_id, member_id, l10n
                FROM {dbm.db_tables['users']} 
                WHERE email = ? 
                AND is_admin = {dbm.User_State['f_admin']} 
            """, (email,))
            
            result = cursor.fetchone()
            if result is None:
                return False
                
            user_id, stored_hash, salt, family_id, member_id, l10n = result
            if _password_ok(password, salt, stored_hash):
                _rehash_password_if_needed(cursor, user_id, password, stored_hash)
                # Update last login time with current timestamp
                try:
                    cursor.execute(f"""
                        UPDATE {dbm.db_tables['users']} 
                        SET updated_at = datetime('now')
                        WHERE id = ?
                    """, (user_id,))
                    conn.commit()
                except sqlite3.Error as update_error:
                    # Continue even if update fails, as auth was successful
                    fu.show_user_error("⚠️ Error updating login time", update_error, warn=True)
                # Update context
                cu.update_context({
                    'member_id': member_id,
                    'family_id': family_id,
                    'language': l10n
                })  
                return True
            
            return False
            
    except sqlite3.Error as e:
        fu.show_user_error("Error verifying admin", e)
        return False

def create_password_reset_token(email: str, expires_hours: int = None):
    """Create a password reset token for the given email
    
    Args:
        email: The email address to create a token for
        expires_hours: Number of hours until the token expires. If None, uses the value from
                     PASSWORD_RESET_TOKEN_EXPIRY_HOURS environment variable (default: 24)
        
    Returns:
        str: The generated token if successful, None otherwise
    """
    try:
        # Get expiration hours from environment variable if not provided
        if expires_hours is None:
            expires_hours = int(os.getenv('PASSWORD_RESET_TOKEN_EXPIRY_HOURS', '24'))
        
        # Generate a secure random token. Only its hash is stored.
        token = secrets.token_urlsafe(32)
        
        with dbm.get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO password_reset_tokens (
                    email, 
                    token, 
                    expires_at
                ) VALUES (?, ?, datetime('now', ? || ' hours'))
            """, (email, hash_reset_token(token), str(expires_hours)))
            
            conn.commit()
            return token
            
    except Exception as e:
        fu.show_user_error("Error creating password reset token", e)
        return None

def validate_password_reset_token(token: str) -> tuple:
    """Validate a password reset token
    
    Args:
        token: The token to validate
        
    Returns:
        tuple: (is_valid, email) where is_valid is a boolean indicating if the token is valid,
               and email is the associated email address if valid, None otherwise
    """
    try:
        if not token:
            return False, None
        token_hash = hash_reset_token(token)
        with dbm.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT email
                FROM password_reset_tokens
                WHERE token = ?
                AND used = 0
                AND expires_at > datetime('now')
            """, (token_hash,))
            result = cursor.fetchone()
            if result:
                return True, result[0]

            # Rows created before hashing still hold the raw token.
            # Do not accept a stored digest presented as the token.
            if is_stored_reset_token(token):
                return False, None
            cursor.execute("""
                SELECT id, email
                FROM password_reset_tokens
                WHERE token = ?
                AND used = 0
                AND expires_at > datetime('now')
            """, (token,))
            legacy = cursor.fetchone()
            if not legacy:
                return False, None
            cursor.execute("""
                UPDATE password_reset_tokens
                SET token = ?
                WHERE id = ?
            """, (token_hash, legacy[0]))
            conn.commit()
            return True, legacy[1]
            
    except Exception as e:
        fu.show_user_error("Error validating password reset token", e)
        return False, None

def delete_password_reset_token(token: str) -> None:
    """Delete the reset-token row for a raw token (hashed or leftover plaintext)."""
    if not token:
        return
    token_hash = hash_reset_token(token)
    with dbm.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM password_reset_tokens WHERE token = ?",
            (token_hash,),
        )
        if not is_stored_reset_token(token):
            cursor.execute(
                "DELETE FROM password_reset_tokens WHERE token = ?",
                (token,),
            )
        conn.commit()

def reset_password(email: str, new_password: str) -> bool:
    """Reset a user's password
    
    Args:
        email: The email address of the user
        new_password: The new password to set
        
    Returns:
        bool: True if the password was successfully reset, False otherwise
    """
    try:
        # Hash the new password
        password_hash, salt = hash_password(new_password)
        
        with dbm.get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Update the user's password
            cursor.execute(f"""
                UPDATE {dbm.db_tables['users']}
                SET password_hash = ?,
                    salt = ?
                WHERE email = ?
            """, (password_hash, salt, email))
            result = cursor.rowcount > 0
            
            # Optionally, mark all tokens for this email as used
            try:
                cursor.execute("""
                    UPDATE password_reset_tokens
                    SET used = 1
                    WHERE email = ?
                """, (email,))
            except Exception as e:
                logging.getLogger("ftpe").error("Could not mark reset tokens as used", exc_info=e)
            conn.commit()
            return result
            
    except Exception as e:
        fu.show_user_error("Error resetting password", e)
        return False


def create_user (email, 
    password, 
    role=None,
    l10n="US",
    is_active=None,
    family_id=0, 
    member_id=0):
    """Create a new user
    
    Args:
        email: The email address of the user
        password: The password of the user
        role: The role of the user, see dbm.User_State
        
    Returns:
        id: The id of the user if the user was created 
        when not existed or updated when existed
        successfully, None otherwise.
    
    Raises:
        ValueError: If the role is not valid
        sqlite3.Error: If there's a database error
        
    Examples:
        >>> create_user("test@example.com", "password", 
            role=dbm.User_State['f_admin'],
            l10n="US",
            is_active=dbm.Subscriber_State['inactive'],
            family_id=0, 
            member_id=0)
        1
    """
    try:
        # check if role is valid
        if role is not None and role not in dbm.User_State.values():
            raise ValueError("Invalid role")
        
        # Check if user already exists
        with dbm.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id 
                FROM {dbm.db_tables['users']} 
                WHERE email = ?
            """, (email,))
            
            existing_user = cursor.fetchone()
            if role not in (
                dbm.User_State['p_admin'],
                dbm.User_State['f_admin'],
                dbm.User_State['f_member'],
            ):
                raise ValueError("Invalid role")
            if existing_user:
                # Update existing user
                user_id = existing_user[0]
                password_hash, salt = hash_password(password)
                cursor.execute(f"""
                    UPDATE {dbm.db_tables['users']} 
                    SET password_hash = ?, 
                        salt = ?, 
                        is_admin = ?, 
                        is_active = ?,
                        l10n = ?,
                        family_id = ?,
                        member_id = ?
                    WHERE id = ?
                """, 
                (password_hash, salt, 
                 role, is_active, 
                 l10n, family_id, 
                 member_id, user_id)
                )
                conn.commit()
                return user_id
            else:
                # Create new user
                password_hash, salt = hash_password(password)
                cursor.execute(f"""
                    INSERT INTO {dbm.db_tables['users']} (
                        email, password_hash, salt, 
                        is_admin, 
                        is_active,
                        l10n,
                        family_id,
                        member_id,
                        created_at
                    ) 
                    VALUES (?, ?, ?, 
                    ?, ?, ?, ?, ?, 
                    datetime('now')
                    )
                """, (email, password_hash, salt, 
                      role, is_active, l10n, 
                      family_id, member_id))
                conn.commit()
                user_id = cursor.lastrowid
                return user_id
    except sqlite3.Error:
        raise

