"""
Custom script to migrate data from SQLite to MSSQL with truncation handling
"""
import os
import sys
import django
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from inventory.models import *

def truncate_string(value, max_length):
    """Truncate string to max_length if it exceeds"""
    if value and len(str(value)) > max_length:
        return str(value)[:max_length]
    return value

def migrate_model(model_class, field_max_lengths):
    """Migrate a model with truncation handling"""
    print(f"\nMigrating {model_class.__name__}...")
    
    # Get all objects from SQLite
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT * FROM {model_class._meta.db_table}")
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
    
    if not rows:
        print(f"No data found for {model_class.__name__}")
        return
    
    print(f"Found {len(rows)} records")
    
    # Insert into MSSQL with truncation
    for row in rows:
        try:
            obj_data = {}
            for i, col in enumerate(columns):
                value = row[i]
                if col in field_max_lengths:
                    value = truncate_string(value, field_max_lengths[col])
                obj_data[col] = value
            
            # Create object using Django ORM
            model_class.objects.create(**obj_data)
            print(f"Inserted record {model_class.__name__}...")
        except Exception as e:
            print(f"Error inserting record: {e}")
            continue
    
    print(f"Completed migrating {model_class.__name__}")

def main():
    print("=" * 60)
    print("SQLite to MSSQL Migration with Truncation Handling")
    print("=" * 60)
    
    # Define field max lengths for models with truncation issues
    field_limits = {
        'ReturnedItem': {
            'request_id': 20,
            'username': 100,
            'full_name': 200,
            'department': 20,
            'section': 50,
        },
        'IssueRequest': {
            'requested_by_username': 100,
            'full_name': 200,
        },
        'TemporaryItemHistory': {
            'request_id': 20,
            'username': 100,
            'full_name': 200,
        },
    }
    
    # Migrate basic models first
    print("\nMigrating basic models...")
    from django.contrib.auth.models import User
    from django.contrib.contenttypes.models import ContentType
    
    # User model
    print("\nMigrating User...")
    users = User.objects.using('default').all()
    for user in users:
        try:
            # Truncate if needed
            if user.username and len(user.username) > 150:
                user.username = user.username[:150]
            if user.email and len(user.email) > 254:
                user.email = user.email[:254]
            user.save(using='default')
        except Exception as e:
            print(f"Error migrating user {user.username}: {e}")
    
    print("Migration completed!")

if __name__ == '__main__':
    main()
