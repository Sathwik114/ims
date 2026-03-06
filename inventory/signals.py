from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

User = get_user_model()


@receiver(post_save, sender=User)
def set_stage1_for_superuser(sender, instance, created, **kwargs):
    """When a user is created as superuser, set stage=1. No category asked during createsuperuser."""
    if created and instance.is_superuser and instance.stage != 1:
        User.objects.filter(pk=instance.pk).update(stage=1)
