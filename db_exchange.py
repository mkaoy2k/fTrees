"""CSV and JSON import and export."""
import sqlite3
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Union
import funcUtils as fu
from db_connection import (
    Subscriber_State,
    User_State,
    db_tables,
    get_db_connection,
    log,
    nullable_fk,
    quote_ident,
)
from db_families import get_families, insert_family
from db_members import get_members, insert_member
from db_relations import get_relations, insert_relation
from db_users import get_users, insert_user


def _csv_fk(value):
    """Parse a CSV foreign key. Blank and 0 mean no reference."""
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        return nullable_fk(value.strip())
    return nullable_fk(value)

def _apply_imported_member_links(conn, member_id, dad_id, mom_id, family_id, errors, index, name):
    """Point a just-imported member at parents and a family, when those rows exist."""
    table = quote_ident(db_tables["members"])
    for column, value in (("dad_id", dad_id), ("mom_id", mom_id), ("family_id", family_id)):
        if value is None:
            continue
        try:
            conn.execute(
                f"UPDATE {table} SET {quote_ident(column)} = ? WHERE id = ?",
                (value, member_id),
            )
        except sqlite3.IntegrityError:
            errors.append(
                f"Member {index} ({name}): {column} {value} does not match an existing row and was left empty"
            )

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
    pending_links = []
    
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
                
                # Parents are applied after every row exists so a child can
                # precede their parent in the file. 0 means "no one".
                family_id = _csv_fk(member.get('family_id'))
                dad_id = _csv_fk(member.get('dad_id'))
                mom_id = _csv_fk(member.get('mom_id'))
                member_data = {
                    'id': int(member['id']),
                    'name': member['name'],
                    'family_id': None,
                    'born': member['born'],
                    'sex': member['sex'],
                    'gen_order': int(member['gen_order']) if member['gen_order'] and str(member['gen_order']).strip() else 0,
                    'alias': member.get('alias'),
                    'email': member.get('email'),
                    'url': member.get('url'),
                    'died': member.get('died'),
                    'dad_id': None,
                    'mom_id': None,
                    'created_at': member.get('created_at')
                }
                
                # Add new member only
                member_id = insert_member(member_data)
                if member_id > 0:
                    imported += 1
                    pending_links.append((member_id, dad_id, mom_id, family_id, i, member.get('name', 'Unknown')))
                else:
                    errors.append(f"Failed to import member {i}: {member.get('name', 'Unknown')}")
                    skipped += 1
                
            except Exception as e:
                errors.append(f"Error in {fu.get_function_name()}: importing member {i} ({member.get('name', 'Unknown')})")
                log.error("Failed to import record", exc_info=e)
                skipped += 1
        
        for member_id, dad_id, mom_id, family_id, index, name in pending_links:
            _apply_imported_member_links(conn, member_id, dad_id, mom_id, family_id, errors, index, name)
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
