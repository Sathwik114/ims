from django.db import migrations


def migrate_returned_item_request_ids(apps, schema_editor):
    """Convert existing numeric request IDs to RET format."""
    ReturnedItem = apps.get_model('inventory', 'ReturnedItem')
    
    for item in ReturnedItem.objects.all():
        if item.request_id:
            # Check if it's a numeric string (old format)
            try:
                # Try to convert to int - if successful, it's the old numeric format
                num = int(item.request_id)
                item.request_id = f'RET{num}'
                item.save()
            except (ValueError, TypeError):
                # Already in RET format or some other format, skip
                pass


def reverse_migration(apps, schema_editor):
    """Reverse migration - convert RET format back to numeric."""
    ReturnedItem = apps.get_model('inventory', 'ReturnedItem')
    
    for item in ReturnedItem.objects.all():
        if item.request_id and item.request_id.startswith('RET'):
            try:
                num = int(item.request_id[3:])  # Remove 'RET' prefix
                item.request_id = num
                item.save()
            except (ValueError, TypeError):
                pass


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0047_alter_returneditem_request_id'),
    ]

    operations = [
        migrations.RunPython(migrate_returned_item_request_ids, reverse_migration),
    ]
