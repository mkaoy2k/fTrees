"""
# Add parent directory to path to allow absolute imports
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))


Database Initialization Script

This script initializes the database with required tables 
and creates the first admin user.
"""
import os
from dotenv import load_dotenv
import db_utils as dbm
import auth_utils as au

# Load environment variables
load_dotenv()

def create_admin_user():
    """Create the initial admin user"""
    email = os.getenv('DB_ADMIN')
    password = os.getenv('DB_ADMIN_PW')
    
    if not email or not password:
        print("❌ Error: DB_ADMIN and DB_ADMIN_PW must be set in .env file")
        return False
    
    try:
        # Create the admin user
        user_id = au.create_user(email, password, 
                role=dbm.User_State['p_admin'])
        if user_id:
            print("✅ Successfully created admin user:")
            print(f"   Email: {email}")
            print(f"   User ID: {user_id}")
            return True
        else:
            print("❌ Failed to create admin user.")
            return False
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting database initialization...")
    
    # Initialize database
    dbm.init_db()
    
    # Create admin user
    print("\n👤 Creating admin user...")
    if not create_admin_user():
        exit(1)
    
    print("\n✨ Database setup completed successfully!")
