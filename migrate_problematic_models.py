"""
Custom script to migrate IssueRequest and TemporaryItemHistory models with error handling
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

from inventory.models import IssueRequest, TemporaryItemHistory
from django.db import transaction

def truncate_string(value, max_length):
    """Truncate string to max_length if it exceeds"""
    if value and len(str(value)) > max_length:
        return str(value)[:max_length]
    return value

def migrate_issue_requests():
    """Migrate IssueRequest model with truncation handling"""
    print("\nMigrating IssueRequest...")
    
    # Get all IssueRequests from SQLite
    from django.db import connections
    sqlite_conn = connections['default']
    
    with sqlite_conn.cursor() as cursor:
        cursor.execute("SELECT * FROM inventory_issuerequest")
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
    
    print(f"Found {len(rows)} IssueRequest records")
    
    # Create mapping of column names to max lengths
    field_max_lengths = {
        'requested_by_username': 100,
        'requested_by_full_name': 200,
        'requested_by_mobile': 30,
        'requested_by_department': 20,
        'requested_by_section': 50,
        'status': 20,
        'approval_note': 500,
        'request_reason': 2000,
        'approved_by_section': 50,
        'approved_by_department': 20,
        'receiver_username': 100,
        'receiver_full_name': 200,
        'receiver_mobile': 30,
        'receiver_department': 20,
        'receiver_section': 50,
        'confirmed_by_department': 20,
        'confirmed_by_section': 50,
        'issued_by_department': 20,
        'issued_by_section': 50,
        'rejected_by_department': 20,
        'rejected_by_section': 50,
    }
    
    # Switch to MSSQL for insertion
    from django.conf import settings
    from importlib import reload
    import config.settings
    
    # Temporarily modify settings to use MSSQL
    original_databases = settings.DATABASES.copy()
    settings.DATABASES['default'] = {
        'ENGINE': 'mssql',
        'NAME': 'ITIMS',
        'USER': 'sa',
        'PASSWORD': 'sqlsa@2012',
        'HOST': '10.40.20.4',
        'PORT': '1433',
        'OPTIONS': {
            'driver': 'SQL Server Native Client 11.0',
        },
    }
    reload(config.settings)
    
    from django.db import connections
    mssql_conn = connections['default']
    
    success_count = 0
    error_count = 0
    
    for row in rows:
        try:
            # Create dict from row
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                if col in field_max_lengths:
                    value = truncate_string(value, field_max_lengths[col])
                # Exclude 'id' field to avoid ID conflicts
                if col == 'id':
                    continue
                row_dict[col] = value
            
            # Check if request_id already exists
            request_id = row_dict.get('request_id')
            if request_id:
                existing = IssueRequest.objects.filter(request_id=request_id).first()
                if existing:
                    # Update existing record
                    for key, value in row_dict.items():
                        setattr(existing, key, value)
                    existing.save()
                    success_count += 1
                    print(f"  Updated existing IssueRequest with request_id: {request_id}")
                    continue
            
            # Create IssueRequest using Django ORM
            with transaction.atomic():
                IssueRequest.objects.create(**row_dict)
            success_count += 1
            print(f"  Inserted IssueRequest {success_count}/{len(rows)}")
        except Exception as e:
            error_count += 1
            print(f"  Error inserting IssueRequest: {e}")
            continue
    
    # Restore original settings
    settings.DATABASES = original_databases
    reload(config.settings)
    
    print(f"IssueRequest migration completed: {success_count} successful, {error_count} errors")

def migrate_temporary_item_history():
    """Migrate TemporaryItemHistory model with duplicate key handling"""
    print("\nMigrating TemporaryItemHistory...")
    
    # Get all TemporaryItemHistory from SQLite
    from django.db import connections
    sqlite_conn = connections['default']
    
    with sqlite_conn.cursor() as cursor:
        cursor.execute("SELECT * FROM inventory_temporaryitemhistory")
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
    
    print(f"Found {len(rows)} TemporaryItemHistory records")
    
    # Switch to MSSQL for insertion
    from django.conf import settings
    from importlib import reload
    import config.settings
    
    # Temporarily modify settings to use MSSQL
    original_databases = settings.DATABASES.copy()
    settings.DATABASES['default'] = {
        'ENGINE': 'mssql',
        'NAME': 'ITIMS',
        'USER': 'sa',
        'PASSWORD': 'sqlsa@2012',
        'HOST': '10.40.20.4',
        'PORT': '1433',
        'OPTIONS': {
            'driver': 'SQL Server Native Client 11.0',
        },
    }
    reload(config.settings)
    
    from django.db import connections
    mssql_conn = connections['default']
    
    success_count = 0
    error_count = 0
    
    for row in rows:
        try:
            # Create dict from row
            row_dict = {}
            for i, col in enumerate(columns):
                # Exclude 'id' field to avoid ID conflicts
                if col == 'id':
                    continue
                row_dict[col] = row[i]
            
            # Check if request_id already exists
            request_id = row_dict.get('request_id')
            if request_id:
                existing = TemporaryItemHistory.objects.filter(request_id=request_id).first()
                if existing:
                    # Update existing record
                    for key, value in row_dict.items():
                        setattr(existing, key, value)
                    existing.save()
                    success_count += 1
                    print(f"  Updated existing TemporaryItemHistory with request_id: {request_id}")
                    continue
            
            # Create TemporaryItemHistory using Django ORM
            with transaction.atomic():
                TemporaryItemHistory.objects.create(**row_dict)
            success_count += 1
            print(f"  Inserted TemporaryItemHistory {success_count}")
        except Exception as e:
            error_count += 1
            print(f"  Error inserting TemporaryItemHistory: {e}")
            continue
    
    # Restore original settings
    settings.DATABASES = original_databases
    reload(config.settings)
    
    print(f"TemporaryItemHistory migration completed: {success_count} successful, {error_count} errors")

def main():
    print("=" * 60)
    print("Migrating Problematic Models (IssueRequest, TemporaryItemHistory)")
    print("=" * 60)
    
    migrate_issue_requests()
    migrate_temporary_item_history()
    
    print("=" * 60)
    print("Migration completed!")
    print("=" * 60)

if __name__ == '__main__':
    main()
