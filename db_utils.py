"""Public database API.

Connection policy lives in db_connection. Schema and migrations live in
db_schema. Record helpers are split by table and re-exported here so
existing `import db_utils as dbm` callers keep working.
"""
import sys
import types

from db_connection import (
    FAMILY_COLUMNS,
    MEMBER_COLUMNS,
    MEMBER_FK_COLUMNS,
    RELATION_COLUMNS,
    RELATION_FK_COLUMNS,
    USER_COLUMNS,
    Member_Relation,
    Member_Sex,
    Member_Status,
    Relation_Type,
    Subscriber_State,
    User_State,
    column_assignments,
    config,
    db_tables,
    get_db_connection,
    get_table_columns,
    get_total_records,
    nullable_fk,
    quote_ident,
    required_member_id,
)
from db_schema import init_db, migrate_plaintext_reset_tokens, migrate_referential_integrity
from db_users import (
    add_subscriber,
    remove_subscriber,
    verify_token,
    get_subscribers,
    get_subscriber,
    delete_subscriber,
    insert_user,
    add_or_update_user,
    get_users,
    delete_user,
)
from db_members import (
    insert_member,
    add_or_update_member,
    get_members,
    get_member_by_email,
    get_member,
    update_member,
    delete_member,
    get_members_when_born_in,
    member_is_alive,
    search_members,
    get_members_when_alive,
    get_children,
    get_parents,
)
from db_relations import (
    add_related_member,
    update_related_member,
    get_relations_by_id,
    get_relations_by_relation,
    get_relations_by_join_between,
    get_member_relations,
    update_relation_when_ended,
    update_relations_when_died,
    get_relation,
    get_relations,
    insert_relation,
    add_or_update_relation,
    delete_relation,
)
from db_families import (
    get_families_by_name,
    get_families_by_background,
    get_family,
    get_families,
    insert_family,
    add_or_update_family,
    delete_family,
)
from db_exchange import (
    get_mirrors,
    import_users,
    import_members,
    import_relations,
    import_families,
    import_from_file,
    export_to_file,
)

__all__ = [
    "FAMILY_COLUMNS",
    "MEMBER_COLUMNS",
    "MEMBER_FK_COLUMNS",
    "RELATION_COLUMNS",
    "RELATION_FK_COLUMNS",
    "USER_COLUMNS",
    "Member_Relation",
    "Member_Sex",
    "Member_Status",
    "Relation_Type",
    "Subscriber_State",
    "User_State",
    "column_assignments",
    "db_tables",
    "get_db_connection",
    "get_table_columns",
    "get_total_records",
    "nullable_fk",
    "quote_ident",
    "required_member_id",
    "init_db",
    "migrate_plaintext_reset_tokens",
    "migrate_referential_integrity",
    "add_subscriber",
    "remove_subscriber",
    "verify_token",
    "get_subscribers",
    "get_subscriber",
    "delete_subscriber",
    "insert_user",
    "add_or_update_user",
    "get_users",
    "delete_user",
    "insert_member",
    "add_or_update_member",
    "get_members",
    "get_member_by_email",
    "get_member",
    "update_member",
    "delete_member",
    "get_members_when_born_in",
    "member_is_alive",
    "search_members",
    "get_members_when_alive",
    "get_children",
    "get_parents",
    "add_related_member",
    "update_related_member",
    "get_relations_by_id",
    "get_relations_by_relation",
    "get_relations_by_join_between",
    "get_member_relations",
    "update_relation_when_ended",
    "update_relations_when_died",
    "get_relation",
    "get_relations",
    "insert_relation",
    "add_or_update_relation",
    "delete_relation",
    "get_families_by_name",
    "get_families_by_background",
    "get_family",
    "get_families",
    "insert_family",
    "add_or_update_family",
    "delete_family",
    "get_mirrors",
    "import_users",
    "import_members",
    "import_relations",
    "import_families",
    "import_from_file",
    "export_to_file",
]

class _DatabaseModule(types.ModuleType):
    @property
    def database_name(self):
        return config.database_name

    @database_name.setter
    def database_name(self, value):
        config.database_name = value

    @property
    def db_path(self):
        return str(config.resolve_path())


sys.modules[__name__].__class__ = _DatabaseModule

if __name__ == "__main__":
    init_db()
    print("Database initialization completed")
    print(f"Database location: {config.resolve_path()}")
