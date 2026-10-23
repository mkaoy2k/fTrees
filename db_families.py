"""Family records."""
import sqlite3
from typing import Any, Dict, List
import funcUtils as fu
from db_connection import (
    FAMILY_COLUMNS,
    db_tables,
    get_db_connection,
    log,
    column_assignments,
)


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
                
                assignments, assigned = column_assignments(
                    family_data,
                    FAMILY_COLUMNS,
                    ignore={"id"},
                )
                update_fields.extend(assignments)
                params.extend(assigned)
                
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
