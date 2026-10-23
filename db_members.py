"""Family-member records."""
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional
import funcUtils as fu
from db_connection import (
    MEMBER_COLUMNS,
    MEMBER_FK_COLUMNS,
    db_tables,
    get_db_connection,
    log,
    nullable_fk,
    quote_ident,
    column_assignments,
)

# Matches member_is_alive: empty and unrecognized values (including the
# default '0000-00-00', which is not a real date) are living members.
# Placeholder tokens, a 4-digit year, and a parseable YYYY-MM-DD or YYYY-MM
# mean the member has died.
ALIVE_SQL = """
(
  "died" IS NULL OR TRIM(CAST("died" AS TEXT)) = ''
  OR (
    TRIM(CAST("died" AS TEXT)) NOT IN ('0', '0000-01-01', 'YYYY', 'YYYY-MM', 'YYYY-MM-DD')
    AND NOT (
      LENGTH(TRIM(CAST("died" AS TEXT))) = 4
      AND TRIM(CAST("died" AS TEXT)) GLOB '[0-9][0-9][0-9][0-9]'
    )
    AND NOT (
      LENGTH(TRIM(CAST("died" AS TEXT))) = 10
      AND date(TRIM(CAST("died" AS TEXT))) IS NOT NULL
    )
    AND NOT (
      LENGTH(TRIM(CAST("died" AS TEXT))) = 7
      AND date(TRIM(CAST("died" AS TEXT)) || '-01') IS NOT NULL
    )
  )
)
"""


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
                nullable_fk(member_data['family_id']),
                member_data['born'],
                member_data['sex'],
                member_data['gen_order'],
                member_data.get('alias'),
                member_data.get('email'),
                member_data.get('url'),
                member_data.get('died'),
                nullable_fk(member_data.get('dad_id')),
                nullable_fk(member_data.get('mom_id')),
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
                
                # Only real member columns are written. password and id are ignored.
                assignments, assigned = column_assignments(
                    member_data,
                    MEMBER_COLUMNS,
                    fk_fields=MEMBER_FK_COLUMNS,
                    ignore={"id", "password", "created_at", "updated_at", "generation"},
                )
                update_fields.extend(assignments)
                params.extend(assigned)
                
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
            
            for field in (
                "name", "born", "gen_order", "email", "alias", "sex",
                "family_id", "url", "died", "dad_id", "mom_id",
            ):
                if field not in member_data or member_data[field] is None:
                    continue
                fields.append(quote_ident(field))
                placeholders.append("?")
                value = nullable_fk(member_data[field]) if field in MEMBER_FK_COLUMNS else member_data[field]
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
    
    # Filter out None values and empty strings, then keep known columns only.
    filtered_updates = {k: v for k, v in update_data.items() if v is not None and v != ''}
    if not filtered_updates:
        log.warning("No valid fields to update after filtering out None/empty values")
        return False
    assignments, values = column_assignments(
        filtered_updates,
        MEMBER_COLUMNS,
        fk_fields=MEMBER_FK_COLUMNS,
    )
    if not assignments:
        log.warning("No valid fields to update after filtering out None/empty values")
        return False
    set_clause = ", ".join(assignments)
    values.append(member_id)
    
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
            
            members_table = quote_ident(db_tables['members'])
            query = f"""
                SELECT *
                FROM {members_table}
                WHERE
                LENGTH(TRIM(born)) = 10
                AND born NOT IN ('0000-01-01', '0', '')
                AND born IS NOT NULL
                AND substr(born, 6, 2) = ?
                AND {ALIVE_SQL}
                ORDER BY born ASC
            """
            cursor.execute(query, (month_str,))
            members = [dict(row) for row in cursor.fetchall()]
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

def _limit_clause(limit, offset):
    """Return a bound LIMIT/OFFSET fragment. Omit both when limit is None."""
    if limit is None:
        return "", []
    if isinstance(limit, bool) or isinstance(offset, bool):
        raise ValueError("limit and offset must be non-negative integers")
    try:
        limit = int(limit)
        offset = int(offset or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit and offset must be non-negative integers") from exc
    if limit < 0 or offset < 0:
        raise ValueError("limit and offset must be non-negative integers")
    return "LIMIT ? OFFSET ?", [limit, offset]

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
    alive: bool = False,
    limit: int = None,
    offset: int = 0,
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
        limit: Maximum rows to return. Omit it to return every match.
        offset: Number of matching rows to skip when limit is set.
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

    if alive:
        conditions.append(ALIVE_SQL)

    limit_sql, limit_params = _limit_clause(limit, offset)
    
    # Build the WHERE clause
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            members_table = quote_ident(db_tables['members'])
            query = f"""
                SELECT * FROM {members_table}
                WHERE {where_clause}
                ORDER BY gen_order, born, name
                {limit_sql}
            """
            
            log.debug(f"Executing search query: {query} with params: {params}")
            cursor.execute(query, params + limit_params)
            
            results = [dict(row) for row in cursor.fetchall()]
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
            
            members_table = quote_ident(db_tables["members"])
            cursor.execute(f"""
                SELECT * FROM {members_table}
                WHERE {ALIVE_SQL}
                ORDER BY id
            """)
            return [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.Error as e:
            raise sqlite3.Error(f"Database error in {fu.get_function_name()}: Error querying living members: {str(e)}")

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
