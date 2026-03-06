"""
Inventory Management System models.
Stage 1 = full (superuser), Stage 2 = edit no user creation, Stage 3 = read-only.
"""
from django.db import models
from django.contrib.auth.models import AbstractUser

STAGE_CHOICES = [(1, 'Stage 1'), (2, 'Stage 2'), (3, 'Stage 3')]

CATEGORY_CHOICES = [
    ('networking', 'Networking'),
    ('hardware', 'Hardware'),
    ('security', 'Security'),
    ('server_parts', 'Server Parts'),
]

MEASUREMENT_UNIT_CHOICES = [
    ('m', 'Meters'),
    ('cm', 'Centimeters'),
    ('dimension', 'Dimensions'),
]


class User(AbstractUser):
    """Custom user with stage and category. Superusers are Stage 1."""
    # Do not add stage/category to REQUIRED_FIELDS so createsuperuser does not ask for them
    REQUIRED_FIELDS = ['email']  # only email besides username
    stage = models.PositiveSmallIntegerField(choices=STAGE_CHOICES, default=1)
    full_name = models.CharField(max_length=200, blank=True, default='')
    mobile_number = models.CharField(max_length=30, blank=True, default='')
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        blank=True,
        null=True,
        help_text='Assigned category for Stage 2/3 (Networking, Hardware, etc.)'
    )

    def is_stage1(self):
        return self.is_superuser or self.stage == 1

    def is_stage2(self):
        return self.stage == 2

    def is_stage3(self):
        return self.stage == 3

    def can_edit(self):
        return self.is_stage1() or self.is_stage2()

    def can_approve_issue_requests(self):
        return self.is_stage1() or self.is_stage2()

    def can_request_issue(self):
        return self.is_stage1() or self.is_stage2() or self.is_stage3()

    def can_issue_items(self):
        # Stage 1 and 2 can operate on issued history / item flows if needed
        return self.is_stage1() or self.is_stage2()

    def can_manage_users(self):
        return self.is_stage1()

    def allowed_categories(self):
        """All stages can view all categories (read-only for Stage 3)."""
        return [c[0] for c in CATEGORY_CHOICES]

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'


class Category(models.Model):
    """Category for inventory (Networking, Hardware, Security, Server Parts)."""
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Rack(models.Model):
    """Rack with cabin, rows and columns. Belongs to a category."""
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, db_index=True)
    cabin_name = models.CharField(max_length=100, blank=True, default='')
    rack_number = models.CharField(max_length=50)
    rows = models.PositiveIntegerField(default=1)
    columns = models.PositiveIntegerField(default=1)
    number_of_racks = models.PositiveIntegerField(default=1, help_text='Number of racks in this cabin/setup')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('category', 'rack_number')]
        ordering = ['category', 'rack_number']

    def __str__(self):
        return f"{self.get_category_display()} - Rack {self.rack_number}"


class Product(models.Model):
    """Inventory item. Linked to category and optionally to a rack."""
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, db_index=True)
    asset_id = models.CharField(max_length=100)
    item_code = models.CharField(max_length=100, blank=True, default='')
    item_name = models.CharField(max_length=200)
    cabin_name = models.CharField(max_length=100, blank=True, default='')
    row_number = models.PositiveIntegerField(null=True, blank=True)
    column_number = models.PositiveIntegerField(null=True, blank=True)
    measurement_unit = models.CharField(max_length=20, choices=MEASUREMENT_UNIT_CHOICES, blank=True, default='')
    measurement_value = models.CharField(max_length=200, blank=True, default='')
    location = models.CharField(max_length=200, blank=True, default='')
    quantity_available = models.PositiveIntegerField(default=0)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rack = models.ForeignKey(Rack, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('category', 'asset_id')]
        ordering = ['category', 'asset_id']

    def __str__(self):
        return f"{self.asset_id} - {self.item_name}"

    @property
    def is_low_stock(self):
        return self.quantity_available < 5

    @property
    def computed_location(self):
        parts = []
        if self.cabin_name:
            parts.append(self.cabin_name)
        if self.rack_id and self.rack and self.rack.rack_number:
            parts.append(f"Rack {self.rack.rack_number}")
        if self.row_number is not None:
            parts.append(f"Row {self.row_number}")
        if self.column_number is not None:
            parts.append(f"Col {self.column_number}")
        return " / ".join(parts) or self.location


class IssueRequest(models.Model):
    """Request to issue an item. Approved by Stage 1/2, issued by Stage 3."""
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_ISSUED = 'issued'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_ISSUED, 'Issue completed'),
    ]
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='issue_requests')
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='issue_requests_made')
    requested_by_full_name = models.CharField(max_length=200, blank=True, default='')
    requested_by_mobile = models.CharField(max_length=30, blank=True, default='')
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issue_requests_approved')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issue_requests_rejected')
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='')
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issue_requests_issued')
    issued_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class IssueHistory(models.Model):
    """Record of issued items (approved and completed)."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='issue_history')
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='issues_made')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issues_approved')
    receiver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issues_received')
    receiver_full_name = models.CharField(max_length=200, blank=True, default='')
    receiver_mobile = models.CharField(max_length=30, blank=True, default='')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issued_at']
        verbose_name_plural = 'Issue history'


class UploadHistory(models.Model):
    """Record when stock was uploaded (quantity added)."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='upload_history')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='uploads_made')
    quantity_added = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name_plural = 'Upload history'


class Order(models.Model):
    """Order request for items. Can be fulfilled or marked disclosed."""
    STATUS_PENDING = 'pending'
    STATUS_PARTIAL = 'partial'
    STATUS_COMPLETED = 'completed'
    STATUS_DISCLOSED = 'disclosed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PARTIAL, 'Partial'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_DISCLOSED, 'Disclosed'),
    ]
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='orders')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='orders_made')
    quantity_requested = models.PositiveIntegerField()
    quantity_provided = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_cost_requested = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_cost_provided = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class Notification(models.Model):
    """In-app notifications (low stock, issue request approval)."""
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    kind = models.CharField(max_length=50, blank=True, default='')
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class ManagementUploadRequest(models.Model):
    """Internal request to management for stock. Not tied to notifications."""
    STATUS_PENDING = 'pending'
    STATUS_COMPLETED = 'completed'
    STATUS_DISCLOSED = 'disclosed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_DISCLOSED, 'Disclosed'),
    ]
    request_id = models.PositiveIntegerField(unique=True, null=True, blank=True, db_index=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='management_upload_requests')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='management_upload_requests_made')
    quantity_requested = models.PositiveIntegerField()
    quantity_received = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.request_id:
            last = (
                ManagementUploadRequest.objects.exclude(request_id__isnull=True)
                .order_by('-request_id')
                .values_list('request_id', flat=True)
                .first()
            )
            self.request_id = (last + 1) if last else 1000
        super().save(*args, **kwargs)
