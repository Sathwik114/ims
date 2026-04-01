from django.core.management.base import BaseCommand
from inventory.models import IssueRequest
import os
from django.conf import settings

class Command(BaseCommand):
    help = 'Fix attachment paths by adding issue_request_files/ prefix'

    def handle(self, *args, **kwargs):
        # Get all issue requests with attachments
        requests = IssueRequest.objects.exclude(attachment='').exclude(attachment__isnull=True)
        
        fixed_count = 0
        error_count = 0
        
        for ir in requests:
            current_path = ir.attachment.name
            
            # Skip if already has correct prefix
            if current_path.startswith('issue_request_files/'):
                self.stdout.write(f"  OK: {current_path}")
                continue
            
            # Build new path with prefix
            new_path = f"issue_request_files/{current_path}"
            
            # Check if file exists in old location
            old_full_path = os.path.join(settings.MEDIA_ROOT, current_path)
            new_full_path = os.path.join(settings.MEDIA_ROOT, new_path)
            
            try:
                # If file exists at old location, move it
                if os.path.exists(old_full_path):
                    # Ensure target directory exists
                    os.makedirs(os.path.dirname(new_full_path), exist_ok=True)
                    # Move file
                    os.rename(old_full_path, new_full_path)
                    self.stdout.write(f"  MOVED: {current_path} -> {new_path}")
                else:
                    # File might already be in new location
                    if os.path.exists(new_full_path):
                        self.stdout.write(f"  EXISTS: {new_path}")
                    else:
                        self.stdout.write(self.style.ERROR(f"  MISSING: {current_path} not found"))
                        error_count += 1
                        continue
                
                # Update database
                ir.attachment.name = new_path
                ir.save(update_fields=['attachment'])
                fixed_count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ERROR: {current_path} - {str(e)}"))
                error_count += 1
        
        self.stdout.write(self.style.SUCCESS(f"\nFixed: {fixed_count}, Errors: {error_count}"))
