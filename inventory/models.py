"""
Inventory Management System models.
Stage 1 = full (superuser), Stage 2 = edit no user creation, Stage 3 = read-only.
"""
from django.db import models
from django.contrib.auth.models import AbstractUser

STAGE_CHOICES = [(1, 'Stage 1'), (2, 'Stage 2'), (3, 'Stage 3')]

DEPARTMENT_CHOICES = [
    ('admin', 'Administration'),
    ('business', 'Business'),
    ('finance', 'Finance'),
    ('foundary', 'Foundary'),
    ('gm office', 'GM Office'),
    ('hr', 'HR'),
    ('hse', 'HSE'),
    ('it', 'IT'),
    ('material', 'Material'),
    ('ms', 'MS'),
    ('pmc', 'PMC'),
    ('qa', 'QA'),
]

ADMIN_SECTION_CHOICES = [
    # Administration Department
    ('admin', 'Admin'),
    ('business', 'Business'),
    ('finance', 'Finance'),
    ('foundary', 'Foundary'),
    ('gm office', 'GM Office'),
    ('hr', 'HR'),
    ('hse', 'HSE'),
    ('it', 'IT'),
    ('material', 'Material'),
    ('ms', 'MS'),
    ('pmc', 'PMC'),
    ('qa ', 'QA'),
    
    # Admin Department
    ('ga' , 'GA'),
    ('facility', 'Facility'),
    #business department
    ('common', 'Common'),
    ('customer Quality Support' , 'Customer Quality Support'),
    ('customs' , 'Customs'),
    ('nPI' , 'NPI'),
    ('shipping and Logistics' , 'Shipping and Logistics'),
    #finance department
    ('common', 'Common'),
    ('costing', 'Costing'),
    ('general A/c', 'General A/c'),
    ('management Accounting', 'Management Accounting'),
    #foundary department
    ('common', 'Common'),
    ('core shop', 'Core shop'),
    ('ie', 'IE'),
    ('maintenance', 'Maintenance'),
    ('melting', 'Melting'),
    ('molding', 'Molding'),
    ('post treatment', 'Post treatment'),
    ('production planning', 'Production Planning'),
    ('quality control', 'Quality Control'),
    ('sand factory', 'Sand Factory'),
    ('technical', 'Technical'),
    ('tooling', 'Tooling'),
    #gm oFfice 
    ('common', 'Common'),
    ('security office', 'Security Office'),
    #HSE department
    ('hse', 'HSE'),
    ('ohc', 'OHC'),
    #human resource department
    ('common', 'Common'),
    ('employee engagement', 'Employee Engagement'),
    ('industrial relation', 'Industrial Relation'),
    ('payroll', 'Payroll'),
    ('training and development', 'Training and Development'),
    #information technology department
    ('it-tools', 'IT-Tools'),
    #machine shop department
    ('automation', 'Automation'),
    ('epcp', 'EPCP'),
    ('fixture maintenance', 'Fixture Maintenance'),
    ('general / office', 'General / Office'),
    ('general affaires', 'General Affaires'),
    ('machining1', 'Machining1'),
    ('machining2', 'Machining2'),
    ('machining3-sec1', 'Machining3-Sec1'),
    ('machining3-sec2', 'Machining3-Sec2'),
    ('maintenance', 'Maintenance'),
    ('post machining2', 'Post Machining2'),
    ('post machining3-sec1', 'Post Machining3-Sec1'),
    ('post machining3-sec2', 'Post Machining3-Sec2'),
    ('production planning', 'Production Planning'),
    ('qc support', 'QC Support'),
    ('quality control2', 'Quality Control2'),
    ('quality control3-sec1', 'Quality Control3-Sec1'),
    ('quality control3-sec2', 'Quality Control3-Sec2'),
    ('technical', 'Technical'),
    ('tooling', 'Tooling'),
    #material department
    ('common', 'Common'),
    ('purchase', 'Purchase'),
    ('warehouse', 'Warehouse'),
    #pmc department
    ('common', 'Common'),
    ('material control', 'Material Control'),
    ('production control', 'Production Control'),
    #Quality assurance department
    ('calibration', 'Calibration'),
    ('common', 'Common'),
    ('iso', 'ISO'),
    ('mis', 'MIS'),    
]

DEPARTMENT_SECTIONS = {
    'admin': ['facility', 'ga'],
    'business': ['common', 'customer Quality Support', 'customs', 'nPI', 'shipping and Logistics'], 
    'finance': ['common', 'costing', 'general A/c', 'management Accounting'],
    'foundary': ['common', 'core shop', 'ie', 'maintenance', 'melting', 'molding', 'post treatment', 'production planning', 'quality control', 'sand factory', 'technical', 'tooling'],
    'gm office': ['common', 'security office'],
    'hse': ['hse', 'ohc'],
    'hr': ['common', 'employee engagement', 'industrial relation', 'payroll', 'training and development'],
    'it': ['it-tools'],
    'material': ['common', 'purchase', 'warehouse'],
    'ms': ['automation', 'epcp', 'fixture maintenance', 'general / office', 'general affaires', 'machining1', 'machining2', 'machining3-sec1', 'machining3-sec2', 'maintenance', 'post machining2', 'post machining3-sec1', 'post machining3-sec2', 'production planning', 'qc support', 'quality control2', 'quality control3-sec1', 'quality control3-sec2', 'technical', 'tooling'],
    'pmc': ['common', 'material control', 'production control'],
    'qa': ['calibration', 'common', 'iso', 'mis'],
}

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

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user with stage and dynamic department/section from MSSQL."""

    REQUIRED_FIELDS = ['email']

    # 🔹 Core fields
    stage = models.PositiveSmallIntegerField(default=1)
    full_name = models.CharField(max_length=200, blank=True, default='')
    mobile_number = models.CharField(max_length=30, blank=True, default='')

    # 🔹 Category (keep choices if needed OR remove if dynamic)
    category = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    # 🔹 Admin fields (REMOVED choices → now dynamic)
    admin_section = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    admin_department = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    # 🔹 User fields (REMOVED choices → dynamic from MSSQL)
    department = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    section = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    is_active = models.BooleanField(
        default=True,
        help_text='Designates whether this user should be treated as active.'
    )

    # 🔹 Role helpers
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
        return True  # all stages allowed

    def can_issue_items(self):
        return self.is_stage1() or self.is_stage2()

    def can_manage_users(self):
        return self.is_stage1()

    def allowed_categories(self):
        """Return list of categories this user can access."""
        if self.is_stage1() or self.is_stage2():
            # Stage 1 and 2 can access all categories
            return [choice[0] for choice in CATEGORY_CHOICES]
        return []  # Stage 3 has no category access

    def __str__(self):
        return self.username

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

def get_employee_data_from_mssql(emp_id):
    try:
        import pyodbc
        from django.conf import settings

        # Show available ODBC drivers
        drivers = [x for x in pyodbc.drivers() if x.endswith('SQL Server')]
        print(f"Available SQL Server drivers: {drivers}")

        db_config = settings.DATABASES.get('sqlserver', {})
        driver = db_config.get('OPTIONS', {}).get('driver')
        host = db_config.get('HOST')
        database = db_config.get('NAME')
        user = db_config.get('USER')
        password = db_config.get('PASSWORD')

        print(f"Using driver: {driver}")
        print(f"Connecting to: {host}, Database: {database}, User: {user}")

        conn_str = f"DRIVER={{{driver}}};SERVER={host};DATABASE={database};UID={user};PWD={password}"
        
        try:
            conn = pyodbc.connect(conn_str)
            print("✅ Connection successful!")
        except Exception as conn_error:
            print(f"❌ Connection failed: {conn_error}")
            
            # Try alternative drivers
            alt_drivers = ['SQL Server Native Client 11.0', 'ODBC Driver 13 for SQL Server', 'ODBC Driver 11 for SQL Server']
            for alt_driver in alt_drivers:
                if alt_driver in drivers:
                    print(f"Trying alternative driver: {alt_driver}")
                    try:
                        conn_str_alt = f"DRIVER={{{alt_driver}}};SERVER={host};DATABASE={database};UID={user};PWD={password}"
                        conn = pyodbc.connect(conn_str_alt)
                        print(f"✅ Connection successful with {alt_driver}!")
                        break
                    except Exception as alt_error:
                        print(f"❌ {alt_driver} also failed: {alt_error}")
                        continue
                else:
                    print(f"❌ {alt_driver} not available")
            else:
                return None

        cursor = conn.cursor()

        # Query across three databases: payroll, payTemp, PayrollITI
        query = """
        SELECT a.empcode, a.empname, b.deptname, c.nsection 
        FROM (
            SELECT empcode, empname, deptcode, nseccode, active FROM payroll.dbo.empmast
            UNION ALL
            SELECT empcode, empname, deptcode, nseccode, active FROM payTemp.dbo.empmast  
            UNION ALL
            SELECT empcode, empname, deptcode, nseccode, active FROM PayrollITI.dbo.empmast
        ) as a 
        LEFT JOIN payroll.dbo.deptmast as b on b.deptcode = a.deptcode 
        LEFT JOIN payroll.dbo.nsecmast as c on c.nseccode = a.nseccode 
        WHERE a.active='Y' AND a.empcode=?
        """
        
        print(f"Executing cross-database UNION query with empcode: {emp_id}")
        
        try:
            cursor.execute(query, (emp_id,))
            row = cursor.fetchone()
            print(f"Cross-database UNION query result: {row}")
            
            if row:
                result = {
                    "username": str(row[0]),    # a.empcode
                    "full_name": row[1],        # a.empname
                    "department": row[2],       # b.deptname
                    "section": row[3],          # c.nsection
                }
                print(f"Returning: {result}")
                return result
            else:
                print(f"No data found for empcode: {emp_id}")
                
                # Try each database individually
                databases = ['payroll', 'payTemp', 'PayrollITI']
                for db in databases:
                    try:
                        cursor.execute(f"SELECT TOP 1 empcode, empname FROM {db}.dbo.empmast WHERE active = 'Y'")
                        test_row = cursor.fetchone()
                        print(f"Sample from {db}.dbo.empmast: {test_row}")
                        
                        cursor.execute(f"SELECT COUNT(*) FROM {db}.dbo.empmast WHERE empcode = ? AND active = 'Y'", (emp_id,))
                        emp_count = cursor.fetchone()[0]
                        print(f"   Employee {emp_id} found in {db}: {emp_count > 0}")
                    except Exception as db_error:
                        print(f"Error accessing {db}.dbo.empmast: {db_error}")
                
        except Exception as query_error:
            print(f"❌ Cross-database UNION query error: {query_error}")
            
            # Try simple query to test database access
            try:
                cursor.execute("SELECT TOP 1 empcode, empname FROM payroll.dbo.empmast WHERE active = 'Y'")
                test_row = cursor.fetchone()
                print(f"Simple payroll.dbo.empmast test: {test_row}")
            except Exception as simple_error:
                print(f"❌ Simple cross-database query error: {simple_error}")
            
            # Try without parameter first to see if tables work
            try:
                cursor.execute("select top 1 a.empcode,a.empname from empmast as a where a.active='Y'")
                test_row = cursor.fetchone()
                print(f"Test query result: {test_row}")
            except Exception as test_error:
                print(f"❌ Test query error: {test_error}")

        return None

    except Exception as e:
        print("❌ MSSQL ERROR:", e)
        return None

    finally:
        try:
            conn.close()
        except:
            pass


class Category(models.Model):
    """Category for inventory (Networking, Hardware, Security, Server Parts)."""
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Rack(models.Model):
    """Rack with cabin, rows and columns."""
    cabin_name = models.CharField(max_length=100, blank=True, default='')
    rack_number = models.CharField(max_length=50)
    rows = models.PositiveIntegerField(default=1)
    columns = models.PositiveIntegerField(default=1)
    number_of_racks = models.PositiveIntegerField(default=1, help_text='Number of racks in this cabin/setup')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('rack_number', 'cabin_name')]
        ordering = ['rack_number']

    def __str__(self):
        return f"Rack {self.rack_number} - {self.cabin_name or 'No Cabin'}"


class Product(models.Model):
    """Inventory item. Linked to category and optionally to a rack."""
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, db_index=True)
    asset_id = models.CharField(max_length=100, blank=True)
    item_code = models.CharField(max_length=100, blank=True, default='')
    item_name = models.CharField(max_length=200)
    cabin_name = models.CharField(max_length=100, blank=True, default='')
    row_number = models.PositiveIntegerField(null=True, blank=True)
    column_number = models.PositiveIntegerField(null=True, blank=True)
    measurement_unit = models.CharField(max_length=20, choices=MEASUREMENT_UNIT_CHOICES, blank=True, default='')
    measurement_value = models.CharField(max_length=200, blank=True, default='')
    location = models.CharField(max_length=200, blank=True, default='')
    quantity_available = models.PositiveIntegerField(default=0)
    requested_count = models.PositiveIntegerField(default=0)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rack = models.ForeignKey(Rack, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('category', 'asset_id')]
        ordering = ['category', 'asset_id']

    def __str__(self):
        return f"{self.asset_id} - {self.item_name}"

    def save(self, *args, **kwargs):
        if not self.asset_id:
            self.asset_id = self.generate_next_asset_id()
        super().save(*args, **kwargs)

    @classmethod
    def generate_next_asset_id(cls):
        # Get all existing asset IDs that start with GTIIT
        existing_ids = cls.objects.filter(asset_id__startswith='GTIIT').values_list('asset_id', flat=True)
        
        # Extract numbers from existing IDs
        numbers = []
        for asset_id in existing_ids:
            if asset_id.startswith('GTIIT'):
                try:
                    num = int(asset_id[5:])  # Extract number after GTIIT
                    numbers.append(num)
                except ValueError:
                    pass
        
        # Find the next available number
        next_num = 1
        if numbers:
            next_num = max(numbers) + 1
        
        return f'GTIIT{next_num}'

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
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_ISSUED, 'Issued'),
        (STATUS_CONFIRMED, 'Confirmed'),
    ]
    request_id = models.PositiveIntegerField(unique=True, null=True, blank=True, db_index=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='issue_requests')
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='issue_requests_made', null=True, blank=True)
    requested_by_username = models.CharField(max_length=100, blank=True, default='')
    requested_by_full_name = models.CharField(max_length=200, blank=True, default='')
    requested_by_mobile = models.CharField(max_length=30, blank=True, default='')
    requested_by_department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        blank=True,
        null=True,
        help_text='Department of the user who made this request'
    )
    requested_by_section = models.CharField(
        max_length=50,
        choices=ADMIN_SECTION_CHOICES,
        blank=True,
        null=True,
        help_text='Section of the user who made this request'
    )
    quantity = models.PositiveIntegerField(default=1)
    request_reason = models.TextField(blank=True, default='')
    attachment = models.FileField(upload_to='issue_request_files/', null=True, blank=True)
    application_form = models.ForeignKey(
        'PeripheralApplication',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='issue_requests',
        help_text='Printed brochure/application form linked to this request'
    )
    approved_quantity = models.PositiveIntegerField(null=True, blank=True)
    needs_confirmation = models.BooleanField(default=False, help_text='Whether the user needs to confirm receipt of the item')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issue_requests_approved')
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by_section = models.CharField(
        max_length=50,
        choices=ADMIN_SECTION_CHOICES,
        blank=True,
        null=True,
        help_text='Admin section that approved this request'
    )
    approved_by_department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        blank=True,
        null=True,
        help_text='Admin department that approved this request'
    )
    rejected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issue_requests_rejected')
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by_section = models.CharField(
        max_length=50,
        choices=ADMIN_SECTION_CHOICES,
        blank=True,
        null=True,
        help_text='Admin section that rejected this request'
    )
    rejected_by_department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        blank=True,
        null=True,
        help_text='Admin department that rejected this request'
    )
    rejection_reason = models.TextField(blank=True, default='')
    approval_note = models.TextField(blank=True, default='')
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issue_requests_issued')
    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by_section = models.CharField(
        max_length=50,
        choices=ADMIN_SECTION_CHOICES,
        blank=True,
        null=True,
        help_text='Admin section that issued this item'
    )
    issued_by_department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        blank=True,
        null=True,
        help_text='Admin department that issued this item'
    )
    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issue_requests_confirmed')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by_department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        blank=True,
        null=True,
        help_text='Department of user who confirmed receipt'
    )
    confirmed_by_section = models.CharField(
        max_length=50,
        choices=ADMIN_SECTION_CHOICES,
        blank=True,
        null=True,
        help_text='Section of user who confirmed receipt'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.request_id:
            last = (
                IssueRequest.objects.exclude(request_id__isnull=True)
                .order_by('-request_id')
                .values_list('request_id', flat=True)
                .first()
            )
            self.request_id = (last + 1) if last else 1000
        
        # 🔹 Compress attachment if it's a new upload
        if self.attachment:
            from .utils import compress_django_file
            self.attachment = compress_django_file(self.attachment)
            
        super().save(*args, **kwargs)

    @property
    def requester_username_display(self) -> str:
        """Login name for templates; avoids resolving username on a null requested_by FK."""
        if self.requested_by_username:
            return self.requested_by_username
        if self.requested_by_id:
            return self.requested_by.username
        return '-'


class PeripheralApplication(models.Model):
    """
    Stage 3 printable brochure ("Computer and Peripheral Application") that is created
    BEFORE the item request, prefilled with user credentials.
    """
    form_id = models.PositiveIntegerField(unique=True, null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='peripheral_applications')
    created_at = models.DateTimeField(auto_now_add=True)

    application_department = models.CharField(max_length=50, blank=True, default='')
    user_full_name = models.CharField(max_length=200, blank=True, default='')
    employee_id = models.CharField(max_length=100, blank=True, default='')
    intercom_no = models.CharField(max_length=100, blank=True, default='')

    equipment_name = models.CharField(max_length=250, blank=True, default='')
    quantity = models.PositiveIntegerField(default=1)
    equipment_type = models.CharField(max_length=100, blank=True, default='')

    budget_number = models.CharField(max_length=100, blank=True, default='')
    remaining_pcs_count = models.CharField(max_length=100, blank=True, default='')

    account_passed_date = models.DateField(null=True, blank=True)
    requirement_date = models.DateField(null=True, blank=True)
    specification = models.TextField(blank=True, default='')
    additional_item = models.TextField(blank=True, default='')
    reason_of_application = models.TextField(blank=True, default='')

    applicant_name = models.CharField(max_length=200, blank=True, default='')
    head_of_section = models.CharField(max_length=200, blank=True, default='')
    department_head = models.CharField(max_length=200, blank=True, default='')

    # optional: store uploaded/printed/signed scan
    signed_form_file = models.FileField(upload_to='peripheral_applications/', null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.form_id:
            last = (
                PeripheralApplication.objects.exclude(form_id__isnull=True)
                .order_by('-form_id')
                .values_list('form_id', flat=True)
                .first()
            )
            self.form_id = (last + 1) if last else 1000
            
        # 🔹 Compress signed form if it's a new upload
        if self.signed_form_file:
            from .utils import compress_django_file
            self.signed_form_file = compress_django_file(self.signed_form_file)
            
        super().save(*args, **kwargs)


class IssueHistory(models.Model):
    """Record of issued items (approved and completed)."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='issue_history')
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='issues_made')
    issued_by_section = models.CharField(
        max_length=50,
        choices=ADMIN_SECTION_CHOICES,
        blank=True,
        null=True,
        help_text='Admin section that issued this item'
    )
    issued_by_department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        blank=True,
        null=True,
        help_text='Admin department that issued this item'
    )
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issues_approved')
    approved_by_section = models.CharField(
        max_length=50,
        choices=ADMIN_SECTION_CHOICES,
        blank=True,
        null=True,
        help_text='Admin section that approved this issue'
    )
    approved_by_department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        blank=True,
        null=True,
        help_text='Admin department that approved this issue'
    )
    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issues_confirmed')
    confirmed_by_department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        blank=True,
        null=True,
        help_text='Department of user who confirmed receipt'
    )
    confirmed_by_section = models.CharField(
        max_length=50,
        choices=ADMIN_SECTION_CHOICES,
        blank=True,
        null=True,
        help_text='Section of user who confirmed receipt'
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
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


class LoginHistory(models.Model):
    """Audit table: store every login event."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_history')
    logged_in_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.CharField(max_length=64, blank=True, default='')
    hostname = models.CharField(max_length=255, blank=True, default='', help_text='System hostname resolved from IP address')
    user_agent = models.CharField(max_length=512, blank=True, default='')
    is_lan = models.BooleanField(default=False, help_text='Whether the login was from a LAN/private IP address')

    class Meta:
        ordering = ['-logged_in_at']
        verbose_name_plural = 'Login history'


class DeletedHistory(models.Model):
    """Record of deleted items with user who deleted and timestamp."""
    asset_id = models.CharField(max_length=100)
    item_code = models.CharField(max_length=100, blank=True, default='')
    item_name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, db_index=True)
    cabin_name = models.CharField(max_length=100, blank=True, default='')
    row_number = models.PositiveIntegerField(null=True, blank=True)
    column_number = models.PositiveIntegerField(null=True, blank=True)
    measurement_unit = models.CharField(max_length=20, choices=MEASUREMENT_UNIT_CHOICES, blank=True, default='')
    measurement_value = models.CharField(max_length=200, blank=True, default='')
    location = models.CharField(max_length=200, blank=True, default='')
    quantity_available = models.PositiveIntegerField(default=0)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    deleted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='items_deleted')
    deleted_at = models.DateTimeField(auto_now_add=True)
    deletion_reason = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-deleted_at']
        verbose_name_plural = 'Deleted history'

    def __str__(self):
        return f"{self.asset_id} - {self.item_name} (deleted by {self.deleted_by})"


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
    material_upload_form = models.FileField(upload_to='material_upload_forms/', null=True, blank=True)
    receipt_file = models.FileField(upload_to='management_receipts/', null=True, blank=True)
    receipt_file_hash = models.CharField(max_length=64, blank=True, default='')
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
            
        # 🔹 Compress receipt if it's a new upload
        if self.receipt_file:
            from .utils import compress_django_file
            self.receipt_file = compress_django_file(self.receipt_file)

        super().save(*args, **kwargs)


class UserStageHistory(models.Model):
    """Record of user stage changes."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stage_history')
    old_stage = models.IntegerField(choices=STAGE_CHOICES)
    new_stage = models.IntegerField(choices=STAGE_CHOICES)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='stage_changes_made')
    changed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.CharField(max_length=64, blank=True, default='')
    hostname = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.user.username}: Stage {self.old_stage} -> Stage {self.new_stage}"


class TemporaryItemHistory(models.Model):
    """Record of temporary item requests issued to users."""
    request_id = models.CharField(max_length=20, unique=True, null=True, blank=True, db_index=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='temporary_history')
    issued_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='temporary_items_received')
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='temporary_items_issued')
    taken_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='temporary_items_taken')
    username = models.CharField(max_length=100, blank=True, default='', help_text='Username of the person the item is issued to')
    full_name = models.CharField(max_length=200, blank=True, default='', help_text='Full name of the person the item is issued to')
    quantity = models.PositiveIntegerField()
    issued_at = models.DateTimeField(auto_now_add=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('issued', 'Issued'), ('returned', 'Returned')],
        default='issued'
    )
    reason = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-issued_at']

    def __str__(self):
        return f"{self.request_id if self.request_id else 'N/A'} - {self.product.asset_id} - {self.issued_to.username if self.issued_to else self.username} ({self.status})"


class ReturnedItem(models.Model):
    """Record of returned items."""
    request_id = models.PositiveIntegerField(unique=True, null=True, blank=True, db_index=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='returned_items')
    returned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='items_returned')
    returned_by_section = models.CharField(
        max_length=50,
        choices=ADMIN_SECTION_CHOICES,
        blank=True,
        null=True,
        help_text='Section of user who returned the item'
    )
    returned_by_department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        blank=True,
        null=True,
        help_text='Department of user who returned the item'
    )
    username = models.CharField(max_length=100, blank=True, default='')
    full_name = models.CharField(max_length=200, blank=True, default='')
    department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        blank=True,
        null=True,
        help_text='Department of the user who is returning the item'
    )
    section = models.CharField(
        max_length=50,
        choices=ADMIN_SECTION_CHOICES,
        blank=True,
        null=True,
        help_text='Section of the user who is returning the item'
    )
    quantity = models.PositiveIntegerField()
    taken_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='items_taken')
    reason = models.TextField(blank=True, default='')
    returned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-returned_at']

    def save(self, *args, **kwargs):
        if not self.request_id:
            last = (
                ReturnedItem.objects.exclude(request_id__isnull=True)
                .order_by('-request_id')
                .values_list('request_id', flat=True)
                .first()
            )
            self.request_id = (last + 1) if last else 1000
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.request_id if self.request_id else 'N/A'} - {self.product.asset_id} - {self.username or self.full_name}"


