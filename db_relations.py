"""Relationships between members."""
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import funcUtils as fu
from db_connection import (
    RELATION_COLUMNS,
    RELATION_FK_COLUMNS,
    db_tables,
    get_db_connection,
    log,
    nullable_fk,
    quote_ident,
    column_assignments,
    required_member_id,
)
from db_members import add_or_update_member


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
        
        # Add other update fields. Unknown names never reach the SQL text.
        for field, value in updates.items():
            if field not in RELATION_COLUMNS:
                raise ValueError(f"Unknown column: {field}")
            if value is not None:
                if field in RELATION_FK_COLUMNS:
                    value = nullable_fk(value)
                # Handle special field types
                if field in ['join_date', 'end_date']:
                    try:
                        datetime.strptime(value, "%Y-%m-%d")
                    except ValueError as e:
                        raise ValueError(f"Invalid {field} format: {str(e)}. Use YYYY-MM-DD format.")
                
                # Only update if the value is different
                if str(relationship.get(field, '')) != str(value):
                    set_clauses.append(f"{quote_ident(field)} = ?")
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
                required_member_id(relation_data.get('member_id'), 'member_id'),
                required_member_id(relation_data.get('partner_id'), 'partner_id'),
                relation_data['relation'],
                relation_data['join_date'],
                relation_data['end_date'],
                nullable_fk(relation_data.get('original_family_id')),
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
                
                assignments, assigned = column_assignments(
                    {field: relation_data[field] for field in optional_fields if field in relation_data},
                    RELATION_COLUMNS,
                    fk_fields=RELATION_FK_COLUMNS,
                )
                update_fields.extend(assignments)
                params.extend(assigned)
                
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
            fields = [quote_ident('member_id'), quote_ident('partner_id')]
            placeholders = ['?', '?']
            values = [
                required_member_id(relation_data['member_id'], 'member_id'),
                required_member_id(relation_data['partner_id'], 'partner_id'),
            ]
            
            optional_fields = [
                'relation', 'original_family_id',
                'original_name', 'dad_name', 'mom_name',
                'join_date', 'end_date'
            ]
            
            for field in optional_fields:
                if field in relation_data:
                    fields.append(quote_ident(field))
                    placeholders.append('?')
                    value = relation_data[field]
                    if field in RELATION_FK_COLUMNS:
                        value = nullable_fk(value)
                    values.append(value)

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
