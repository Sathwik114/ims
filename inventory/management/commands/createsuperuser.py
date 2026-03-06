"""
Custom createsuperuser: no category prompt; superuser is automatically Stage 1.
Stage and category are not in REQUIRED_FIELDS, so Django never asks for them.
"""
from django.contrib.auth.management.commands import createsuperuser as base


class Command(base.Command):
    def handle(self, *args, **options):
        result = super().handle(*args, **options)
        username = options.get('username')
        if username:
            try:
                user = self.UserModel.objects.get(username=username)
                user.stage = 1
                user.save(update_fields=['stage'])
            except self.UserModel.DoesNotExist:
                pass
        return result
