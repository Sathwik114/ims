import json
from decimal import Decimal
from pathlib import Path
import hashlib
from .ldap_auth import ldap_authenticate
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Sum, Q, F, IntegerField, Case, When
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.http import FileResponse
from django.core.files.base import ContentFile
from django.views.decorators.http import require_http_methods, require_POST
from django.utils import timezone
from .ldap_auth import ldap_authenticate
from django.contrib.auth import login
from django.contrib.auth import get_user_model

from .models import (
    User, Product, Rack, IssueRequest, IssueHistory, PeripheralApplication,
    UploadHistory, Order, ManagementUploadRequest,
    LoginHistory, DeletedHistory,
    CATEGORY_CHOICES,
)

from .forms import (
    LoginForm, AddProductForm, AddRackForm, IssueRequestForm,
    UploadQuantityForm, OrderForm, OrderFulfillForm,
    AddUserForm, ChangePasswordForm, DeletionReasonForm,
)
from .utils import send_issue_request_email, send_low_stock_alert, save_compressed_file, get_compressed_file_content, compress_file_content
import os
from django.conf import settings


def _notify_low_stock(product, request=None):
    """Send email alert for Stage 1 users when product quantity < 5."""
    if product.quantity_available >= 5:
        return
    
    # Only send email notification (no in-app notifications)
    send_low_stock_alert(product, request)


def _handle_compressed_upload(upload_file, upload_dir):
    """
    Handle file upload with compression.
    
    Args:
        upload_file: Django UploadedFile object
        upload_dir: Directory path relative to MEDIA_ROOT
    
    Returns:
        str: Filename of the saved file (None if no file)
    """
    if not upload_file:
        return None
    
    # Create upload directory if it doesn't exist
    full_upload_path = os.path.join(settings.MEDIA_ROOT, upload_dir)
    os.makedirs(full_upload_path, exist_ok=True)
    
    # Save compressed file
    result = save_compressed_file(upload_file, full_upload_path)
    
    if result['is_compressed']:
        print(f"🗜️ File compressed: {result['original_size']:,} → {result['compressed_size']:,} bytes "
              f"({result['compression_ratio']}% saved)")
    
    return result['filename']


def get_client_ip(request):
    """
    Get the real client IP address and system information.
    This handles various scenarios including:
    - Direct connections (REMOTE_ADDR)
    - Behind proxy/load balancer (X-Forwarded-For)
    - LAN connections with private IPs
    - Localhost connections (try to get real network IP)
    """
    # List of headers to check in order of preference
    headers_to_check = [
        'HTTP_X_FORWARDED_FOR',
        'HTTP_X_REAL_IP',
        'HTTP_CLIENT_IP',
        'HTTP_X_FORWARDED',
        'HTTP_FORWARDED_FOR',
        'HTTP_FORWARDED',
        'REMOTE_ADDR'
    ]
    
    client_ip = None
    for header in headers_to_check:
        ip = request.META.get(header, '')
        if ip:
            # X-Forwarded-For can contain multiple IPs, get the first one (original client)
            if ',' in ip:
                ip = ip.split(',')[0].strip()
            
            # Validate IP address format
            ip = ip.strip()
            if ip and ip != 'unknown':
                client_ip = ip
                break
    
    # If we got localhost, try to get the real network IP
    if client_ip in ['127.0.0.1', 'localhost', '::1']:
        try:
            import socket
            # Try to get the actual network interface IP
            hostname = socket.gethostname()
            real_ip = socket.gethostbyname(hostname)
            if real_ip and real_ip not in ['127.0.0.1', 'localhost']:
                client_ip = real_ip
        except Exception:
            pass
    
    # Try to get hostname for the IP
    hostname = ''
    if client_ip:
        try:
            import socket
            hostname = socket.gethostbyaddr(client_ip)[0]
        except (socket.herror, socket.gaierror, Exception):
            hostname = ''
    
    return client_ip or '127.0.0.1', hostname


def is_lan_ip(ip):
    """
    Check if an IP address is a private/LAN IP address.
    Returns True for private IP ranges (10.x.x.x, 172.16-31.x.x, 192.168.x.x, 127.0.0.1)
    """
    try:
        import ipaddress
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private
    except (ValueError, ImportError):
        # Fallback manual check if ipaddress module not available
        if not ip:
            return False
        
        # Check for common private IP patterns
        if ip.startswith('10.') or ip.startswith('192.168.') or ip == '127.0.0.1':
            return True
        
        # Check 172.16-31.x.x range
        if ip.startswith('172.'):
            parts = ip.split('.')
            if len(parts) >= 2:
                try:
                    second_octet = int(parts[1])
                    if 16 <= second_octet <= 31:
                        return True
                except ValueError:
                    pass
        
        return False


def _as_decimal(value):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _notify_issue_request_created(ir: IssueRequest, request=None):
    """Notify Stage 1 and Stage 2 users that a new request needs approval."""
    approvers = User.objects.filter(stage__in=[1, 2]) | User.objects.filter(is_superuser=True)
    req_name = ir.requested_by.full_name or ir.requested_by.username
    
    # Send email notification to approvers with company emails
    for u in approvers.distinct():
        if u.email and u.email.endswith('@gti.nws.cn'):
            try:
                from .utils import send_email_notification
                subject = f"New Issue Request #{ir.request_id} - {ir.product.item_name}"
                html_content = f"""
                <div style="font-family: Arial, sans-serif; padding:20px; background:#f4f6f8;">
                    <div style="max-width:600px; margin:auto; background:white; padding:20px; border-radius:8px;">
                        <h2 style="color:#2563eb;">New Issue Request Submitted</h2>
                        <p>A new issue request requires your approval:</p>
                        <table style="width:100%; border-collapse:collapse; font-size:14px;">
                            <tr><td style="font-weight:bold; padding:5px;">Request ID</td><td style="padding:5px;">#{ir.request_id}</td></tr>
                            <tr style="background:#f9fafb;"><td style="font-weight:bold; padding:5px;">Requested By</td><td style="padding:5px;">{req_name}</td></tr>
                            <tr><td style="font-weight:bold; padding:5px;">Item</td><td style="padding:5px;">{ir.product.item_name} ({ir.product.asset_id})</td></tr>
                            <tr style="background:#f9fafb;"><td style="font-weight:bold; padding:5px;">Quantity</td><td style="padding:5px;">{ir.quantity}</td></tr>
                            <tr><td style="font-weight:bold; padding:5px;">Reason</td><td style="padding:5px;">{ir.request_reason if ir.request_reason else "No reason provided"}</td></tr>
                        </table>
                        <div style="text-align:center; margin-top:20px;">
                            <a href="http://10.40.20.4:8000/issue-requests/" style="background:#16a34a; color:white; padding:10px 16px; text-decoration:none; border-radius:5px;">View Requests</a>
                        </div>
                    </div>
                </div>
                """
                send_email_notification(u.email, subject, html_content)
                print(f"✅ Sent approval notification to {u.email}")
            except Exception as e:
                print(f"❌ Failed to send approval notification to {u.email}: {e}")
    
    # Send email notification to requester
    send_issue_request_email(ir, 'created', request)


def _notify_issue_request_decision(ir: IssueRequest, approved: bool, request=None):
    """Notify requester that their request was approved/rejected (with reason)."""
    if approved:
        title = 'Issue request approved'
        qty = ir.approved_quantity or ir.quantity
        if qty != ir.quantity:
            msg = (
                f'Your request for {ir.product.item_name} ({ir.product.asset_id}) was approved '
                f'partially: {qty} of {ir.quantity}.'
            )
        else:
            msg = f'Your request for {ir.product.item_name} ({ir.product.asset_id}) was approved.'
        kind = 'issue_approved'
        email_type = 'approved'
    else:
        title = 'Issue request rejected'
        reason = ir.rejection_reason.strip() or 'No reason provided.'
        msg = f'Your request for {ir.product.item_name} ({ir.product.asset_id}) was rejected. Reason: {reason}'
        kind = 'issue_rejected'
        email_type = 'rejected'
    
    # Send email notification (no in-app notifications)
    send_issue_request_email(ir, email_type, request)

User = get_user_model()

def login_view(request):

    if request.user.is_authenticated:
        return redirect('inventory:dashboard')

    if request.method == 'POST':

        form = LoginForm(request.POST)

        if form.is_valid():

            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            # LDAP authentication
            if ldap_authenticate(username, password):

                user, created = User.objects.get_or_create(username=username)
                
                # Check if user is active before allowing login
                if not user.is_active:
                    messages.error(request, 'Your account has been disabled. Please contact an administrator.')
                    return redirect('inventory:login')

                login(request, user)

                try:
                    ip, hostname = get_client_ip(request)
                    ua = request.META.get('HTTP_USER_AGENT', '') or ''
                    lan_connection = is_lan_ip(ip)

                    LoginHistory.objects.create(
                        user=user,
                        ip_address=ip[:64],
                        hostname=hostname[:255],
                        user_agent=ua[:512],
                        is_lan=lan_connection
                    )

                except Exception:
                    pass

                # Redirect to issue_requests page with login_redirect parameter
                return redirect('/issue-requests/?login_redirect=1')

            else:
                messages.error(request, "Invalid LDAP credentials")

    else:
        form = LoginForm()

    return render(request, 'inventory/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('inventory:login')


@login_required
def dashboard(request):
    categories = [c[0] for c in CATEGORY_CHOICES]
    label_map = dict(CATEGORY_CHOICES)

    # Main pie: available items by category (sum of quantities)
    overall = []
    for cat in categories:
        total = Product.objects.filter(category=cat).aggregate(s=Sum('quantity_available'))['s'] or 0
        overall.append({'label': label_map.get(cat, cat), 'value': total})

    # 4 pies: per-category breakdown by item_name (top 8 + Other)
    per_category = {}
    for cat in categories:
        rows = (
            Product.objects.filter(category=cat)
            .values('item_name')
            .annotate(total=Sum('quantity_available'))
            .order_by('-total')
        )
        top = list(rows[:8])
        other = sum([r['total'] for r in rows[8:]])
        series = [{'label': r['item_name'], 'value': r['total']} for r in top]
        if other:
            series.append({'label': 'Other', 'value': other})
        per_category[cat] = series

    # Distinct item "types" per category (for stat tiles)
    type_counts = {}
    for cat in categories:
        type_counts[cat] = Product.objects.filter(category=cat).count()

    # Issued-by-category overview for dashboard bar chart (which category issued more)
    issued_by_category = (
        IssueHistory.objects.values('product__category')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')
    )
    issued_by_category_series = [
        {
            'label': label_map.get(row['product__category'], row['product__category']),
            'value': row['total_qty'] or 0,
        }
        for row in issued_by_category
    ]

    show_right = True  # Show right panel for all users
    recent_logins = []
    recent_issued = []
    
    # Prepare item lists for regular users
    item_lists = {}
    
    if request.user.stage in [1, 2] or request.user.is_superuser:
        # Admin/Stage 1/2: Show all recent logins with IP/hostname and issued items
        recent_logins = LoginHistory.objects.select_related('user').order_by('-logged_in_at')[:6]
        recent_issued = IssueHistory.objects.select_related('product', 'receiver', 'issued_by').order_by('-issued_at')[:8]
    else:
        # Stage 3: Show user's own logins and issued items to them
        recent_logins = LoginHistory.objects.filter(user=request.user).order_by('-logged_in_at')[:6]
        recent_issued = IssueHistory.objects.filter(receiver=request.user).select_related('product', 'issued_by').order_by('-issued_at')[:8]
        
        # Get chart data for each category for users (item counts)
        categories = ['networking', 'hardware', 'security', 'server_parts']
        for category in categories:
            item_lists[f'{category}_items'] = Product.objects.filter(category=category)[:8]  # Still provide item lists
            
        # Create category data with individual items for user charts (equal distribution)
        user_category_data = {}
        categories = ['networking', 'hardware', 'security', 'server_parts']
        for category in categories:
            items = Product.objects.filter(category=category)[:8]  # Get 8 items per category
            # Give equal weight to each item (no counts shown)
            user_category_data[f'{category}_items'] = [
                {'label': item.item_name, 'value': 1} for item in items
            ]
        item_lists['user_category_data'] = user_category_data

    return render(request, 'inventory/dashboard.html', {
        'overall_pie_json': json.dumps(overall),
        'per_category_json': json.dumps(per_category),
        'type_counts_json': json.dumps(type_counts),
        'issued_by_category_json': json.dumps(issued_by_category_series),
        'show_right_panel': show_right,
        'recent_logins': recent_logins,
        'recent_issued': recent_issued,
        **item_lists,  # Add item lists for regular users
    })


@login_required
def category_detail(request, category):
    search_asset = request.GET.get('asset_id', '').strip()
    search_item_code = request.GET.get('item_code', '').strip()
    search_rack = request.GET.get('rack_name', '').strip()
    search_text = request.GET.get('q', '').strip()
    qs = Product.objects.filter(category=category)
    if search_asset:
        qs = qs.filter(asset_id__icontains=search_asset)
    if search_item_code:
        qs = qs.filter(item_code__icontains=search_item_code)
    if search_rack:
        qs = qs.filter(rack__rack_number__icontains=search_rack)
    if search_text:
        qs = qs.filter(Q(item_name__icontains=search_text) | Q(item_code__icontains=search_text))

    # Annotate per-row on-order quantities so we can roll them up per rack/item.
    qs = qs.select_related('rack').annotate(
        on_order=Coalesce(
            Sum(
                Case(
                    When(
                        orders__status__in=[Order.STATUS_PENDING, Order.STATUS_PARTIAL],
                        then=F('orders__quantity_requested') - F('orders__quantity_provided'),
                    ),
                    default=0,
                    output_field=IntegerField(),
                )
            ),
            0,
        )
    ).annotate(
        total_items=F('quantity_available') + F('on_order')
    )

    rows = qs.order_by('asset_id')

    # Group items by asset_id so all racks/locations show inside one container/row.
    grouped = {}
    for product in rows:
        key = product.asset_id
        if key not in grouped:
            grouped[key] = {
                'asset_id': product.asset_id,
                'item_code': product.item_code,
                'item_name': product.item_name,
                'racks': [],
                'total_quantity': 0,
                'total_on_order': 0,
                'total_items': 0,
                'price': product.price,
            }

        rack_label = product.computed_location or product.location or '—'
        rack_info = {
            'location': rack_label,
            'quantity': product.quantity_available,
            'on_order': product.on_order,
            'total': product.total_items,
            'rack_number': (product.rack.rack_number if product.rack_id and product.rack else ''),
        }

        existing = None
        for r in grouped[key]['racks']:
            if r['location'] == rack_info['location']:
                existing = r
                break

        if existing:
            existing['quantity'] += rack_info['quantity']
            existing['on_order'] += rack_info['on_order']
            existing['total'] += rack_info['total']
        else:
            grouped[key]['racks'].append(rack_info)

        grouped[key]['total_quantity'] += product.quantity_available
        grouped[key]['total_on_order'] += product.on_order
        grouped[key]['total_items'] += product.total_items

    products = list(grouped.values())
    category_name = dict(CATEGORY_CHOICES).get(category, category)
    return render(request, 'inventory/category_detail.html', {
        'category': category,
        'category_name': category_name,
        'products': products,
        'grouped_view': True,
        'search_asset': search_asset,
        'search_item_code': search_item_code,
        'search_rack': search_rack,
        'search_text': search_text,
    })


@login_required
def view_items(request):
    """Global view/search: category dropdown + search by asset id / item code / name."""
    category = request.GET.get('category', '').strip()
    q = request.GET.get('q', '').strip()
    qs = Product.objects.all()
    if category:
        qs = qs.filter(category=category)
    if q:
        qs = qs.filter(Q(asset_id__icontains=q) | Q(item_code__icontains=q) | Q(item_name__icontains=q))

    # On hand / On order / Total per item (by item code)
    # Include both regular orders and purchase requests
    qs = qs.select_related('rack').annotate(
        # Calculate on_order from regular orders
        regular_orders_on_order=Coalesce(
            Sum(
                Case(
                    When(
                        orders__status__in=[Order.STATUS_PENDING, Order.STATUS_PARTIAL],
                        then=F('orders__quantity_requested') - F('orders__quantity_provided'),
                    ),
                    default=0,
                    output_field=IntegerField(),
                )
            ),
            0,
        ),
        # Calculate on_order from purchase requests
        purchase_requests_on_order=Coalesce(
            Sum(
                Case(
                    When(
                        management_upload_requests__status=ManagementUploadRequest.STATUS_PENDING,
                        then=F('management_upload_requests__quantity_requested') - F('management_upload_requests__quantity_received'),
                    ),
                    default=0,
                    output_field=IntegerField(),
                )
            ),
            0,
        )
    ).annotate(
        # Total on_order is sum of both regular orders and purchase requests
        on_order=F('regular_orders_on_order') + F('purchase_requests_on_order'),
        total_items=F('quantity_available') + F('on_order')
    )

    products = qs.order_by('category', 'asset_id')[:500]
    
    # Group items by asset_id to show all racks for same item
    grouped_products = {}
    for product in products:
        key = product.asset_id
        if key not in grouped_products:
            grouped_products[key] = {
                'category': product.get_category_display(),
                'asset_id': product.asset_id,
                'item_code': product.item_code,
                'item_name': product.item_name,
                'racks': [],
                'total_quantity': 0,
                'total_on_order': 0,
                'total_items': 0,
                'price': product.price,
                'first_product_pk': product.pk,  # Store pk of first product for editing
            }
        
        # Add rack information
        rack_info = {
            'location': product.computed_location or product.location,
            'quantity': product.quantity_available,
            'on_order': product.on_order,
            'total': product.total_items,
        }
        
        # Check if this rack already exists for this item
        existing_rack = None
        for rack in grouped_products[key]['racks']:
            if rack['location'] == rack_info['location']:
                existing_rack = rack
                break
        
        if existing_rack:
            # Update existing rack quantities
            existing_rack['quantity'] += rack_info['quantity']
            existing_rack['on_order'] += rack_info['on_order']
            existing_rack['total'] += rack_info['total']
        else:
            # Add new rack
            grouped_products[key]['racks'].append(rack_info)
        
        # Update totals
        grouped_products[key]['total_quantity'] += product.quantity_available
        grouped_products[key]['total_on_order'] += product.on_order
        grouped_products[key]['total_items'] += product.total_items
    
    # Convert to list for template
    grouped_products_list = list(grouped_products.values())
    
    return render(request, 'inventory/view_items.html', {
        'products': grouped_products_list,
        'selected_category': category,
        'q': q,
        'categories': [{'slug': c[0], 'name': c[1]} for c in CATEGORY_CHOICES],
        'grouped_view': True,
    })


@login_required
def product_delete_confirm(request, pk):
    """Show confirmation form with reason input before deleting product."""
    product = get_object_or_404(Product, pk=pk)
    
    if not request.user.is_stage1():
        messages.error(request, 'Only Stage 1 can delete items.')
        return redirect('inventory:view_items')
    
    if request.method == 'POST':
        form = DeletionReasonForm(request.POST)
        if form.is_valid():
            # Create deleted history record with reason
            DeletedHistory.objects.create(
                asset_id=product.asset_id,
                item_code=product.item_code,
                item_name=product.item_name,
                category=product.category,
                cabin_name=product.cabin_name,
                row_number=product.row_number,
                column_number=product.column_number,
                measurement_unit=product.measurement_unit,
                measurement_value=product.measurement_value,
                location=product.location,
                quantity_available=product.quantity_available,
                price=product.price,
                deleted_by=request.user,
                deletion_reason=form.cleaned_data['deletion_reason']
            )
            
            asset = product.asset_id
            product.delete()
            messages.success(request, f'Item {asset} deleted successfully.')
            return redirect('inventory:view_items')
    else:
        form = DeletionReasonForm()
    
    return render(request, 'inventory/product_delete_confirm.html', {
        'product': product,
        'form': form,
    })


@login_required
@require_POST
def product_delete(request, pk):
    """Stage 1: safe delete for products (only if no history)."""
    if not request.user.is_stage1():
        messages.error(request, 'Only Stage 1 can delete items.')
        return redirect('inventory:view_items')
    product = get_object_or_404(Product, pk=pk)
    
    # Check if deletion reason is provided
    deletion_reason = request.POST.get('deletion_reason', '').strip()
    if not deletion_reason:
        messages.error(request, 'Deletion reason is required.')
        return redirect('inventory:product_delete_confirm', pk=pk)
    
    # basic safety: do not delete if there is history
    if product.issue_history.exists() or product.upload_history.exists() or product.orders.exists() or product.management_upload_requests.exists():
        messages.error(request, 'Cannot delete item because it has related history/requests.')
        return redirect('inventory:view_items')
    
    # Create deleted history record with reason
    DeletedHistory.objects.create(
        asset_id=product.asset_id,
        item_code=product.item_code,
        item_name=product.item_name,
        category=product.category,
        cabin_name=product.cabin_name,
        row_number=product.row_number,
        column_number=product.column_number,
        measurement_unit=product.measurement_unit,
        measurement_value=product.measurement_value,
        location=product.location,
        quantity_available=product.quantity_available,
        price=product.price,
        deleted_by=request.user,
        deletion_reason=deletion_reason
    )
    
    asset = product.asset_id
    product.delete()
    messages.success(request, f'Item {asset} deleted.')
    return redirect('inventory:view_items')


@login_required
def view_items_excel(request):
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        from io import BytesIO
    except ImportError:
        return HttpResponse('Excel export requires openpyxl. Install with: pip install openpyxl', status=501)

    category = request.GET.get('category', '').strip()
    q = request.GET.get('q', '').strip()
    qs = Product.objects.select_related('rack').all().order_by('category', 'asset_id')
    if category:
        qs = qs.filter(category=category)
    if q:
        qs = qs.filter(Q(asset_id__icontains=q) | Q(item_code__icontains=q) | Q(item_name__icontains=q))

    # Create workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Category Items"
    
    # Headers
    headers = ['Category', 'Asset ID', 'Item Code', 'Item Name', 'Location', 'Quantity Available', 'Price']
    
    # Add headers
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                           top=Side(style='thin'), bottom=Side(style='thin'))
    
    # Add data
    for row, p in enumerate(qs[:500], 2):
        data = [
            p.get_category_display(),
            p.asset_id,
            p.item_code or '-',
            p.item_name,
            p.computed_location or p.location or '-',
            str(p.quantity_available),
            str(p.price) if p.price is not None else '-',
        ]
        
        for col, value in enumerate(data, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                               top=Side(style='thin'), bottom=Side(style='thin'))
    
    # Set column widths
    column_widths = [15, 12, 12, 30, 20, 15, 12]
    for col, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    
    # Save to memory
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    
    # Create response
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="category_items.xlsx"'
    return response


@login_required
def add_product_global(request):
    if not request.user.can_edit():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:dashboard')
    if request.method == 'POST':
        form = AddProductForm(request.POST)
        if form.is_valid():
            if not form.cleaned_data.get('rack'):
                form.add_error('rack', 'Rack must exist before adding an item. Please create/select a rack.')
                return render(request, 'inventory/add_product_global.html', {'form': form})
            product = form.save()
            if product.is_low_stock:
                messages.warning(request, f'The {product.item_name} has low stock, request new stock.')
                _notify_low_stock(product)
            messages.success(request, 'Item added successfully.')
            # Jump straight to the relevant category page and pre-filter to the new asset.
            return redirect(f"/category/{product.category}/?asset_id={product.asset_id}")
    else:
        form = AddProductForm()
    return render(request, 'inventory/add_product_global.html', {'form': form})


@login_required
def add_rack_global(request):
    if not request.user.can_edit():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:dashboard')
    if request.method == 'POST':
        form = AddRackForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Rack added successfully.')
            return redirect('inventory:dashboard')
    else:
        form = AddRackForm()
    return render(request, 'inventory/add_rack_global.html', {'form': form})


# ---- Add Product / Add Rack ----
@login_required
def add_product(request, category):
    if category not in request.user.allowed_categories() or not request.user.can_edit():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:dashboard')
    if request.method == 'POST':
        form = AddProductForm(category, request.POST)
        if form.is_valid():
            product = form.save()
            if product.is_low_stock:
                messages.warning(request, f'The {product.item_name} has low stock, request new stock.')
                _notify_low_stock(product)
            messages.success(request, 'Product added successfully.')
            return redirect('inventory:category_detail', category=category)
    else:
        form = AddProductForm(category)
    return render(request, 'inventory/add_product.html', {
        'form': form, 'category': category,
        'category_name': dict(CATEGORY_CHOICES).get(category, category),
    })


@login_required
def add_rack(request, category):
    if category not in request.user.allowed_categories() or not request.user.can_edit():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:dashboard')
    if request.method == 'POST':
        form = AddRackForm(category, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Rack added successfully.')
            return redirect('inventory:category_detail', category=category)
    else:
        form = AddRackForm(category)
    return render(request, 'inventory/add_rack.html', {
        'form': form, 'category': category,
        'category_name': dict(CATEGORY_CHOICES).get(category, category),
    })


@login_required
def edit_product(request, pk):
    """Stage 1/2: edit existing product from View Items."""
    product = get_object_or_404(Product, pk=pk)
    if not request.user.can_edit() or product.category not in request.user.allowed_categories():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:view_items')
    if request.method == 'POST':
        form = AddProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Item updated successfully.')
            return redirect('inventory:view_items')
    else:
        form = AddProductForm(instance=product)
    return render(request, 'inventory/add_product_global.html', {'form': form})


# ---- Issuing ----
@login_required
def issuing_items(request, category):
    # Legacy route: redirect to the unified Issue Requests page
    return redirect(f"/issue-requests/?category={category}")


@login_required
def get_product_details(request, category, asset_id):
    products = Product.objects.filter(category=category, asset_id=asset_id)
    if not products.exists():
        return JsonResponse({'error': 'Product not found'}, status=404)
    if products.count() > 1:
        # If multiple products found, use the first one
        product = products.first()
    else:
        product = products.first()
    return JsonResponse({
        'asset_id': product.asset_id,
        'item_code': product.item_code,
        'item_name': product.item_name,
        'location': product.computed_location,
        'quantity_available': product.quantity_available,
        'price': str(product.price) if product.price else '',
    })


@login_required
def search_products_api(request):
    """AJAX search for Stage 3 item request autocomplete."""
    if not request.user.is_authenticated or not request.user.is_stage3():
        return JsonResponse([], safe=False)
    q = (request.GET.get('q') or '').strip()
    if not q:
        return JsonResponse([], safe=False)
    qs = (
        Product.objects.filter(
            Q(asset_id__icontains=q) |
            Q(item_code__icontains=q) |
            Q(item_name__icontains=q)
        )
        .order_by('asset_id')[:10]
    )
    results = [
        {
            'asset_id': p.asset_id,
            'item_code': p.item_code or '',
            'item_name': p.item_name,
            'available': p.quantity_available,
        }
        for p in qs
    ]
    return JsonResponse(results, safe=False)


@login_required
def search_products_internal_api(request):
    """AJAX search for Stage 1/2 product selection (purchase/upload requests)."""
    if request.user.is_stage3():
        return JsonResponse([], safe=False)
    q = (request.GET.get('q') or '').strip()
    if not q:
        return JsonResponse([], safe=False)
    qs = (
        Product.objects.filter(
            Q(asset_id__icontains=q) |
            Q(item_code__icontains=q) |
            Q(item_name__icontains=q)
        )
        .order_by('category', 'asset_id')[:10]
    )
    results = [
        {
            'asset_id': p.asset_id,
            'item_code': p.item_code or '',
            'item_name': p.item_name,
            'category': p.get_category_display(),
        }
        for p in qs
    ]
    return JsonResponse(results, safe=False)


@login_required
def get_user_by_username(request):
    username = request.GET.get('username', '').strip()
    print(f"API called with username: {username}")
    
    if not username:
        return JsonResponse({'full_name': '', 'mobile_number': '', 'department': '', 'section': ''})
    
    # Try fetching from MSSQL first using the config dictionary provided in settings
    from .models import get_employee_data_from_mssql
    print(f"Calling get_employee_data_from_mssql with: {username}")
    mssql_data = get_employee_data_from_mssql(username)
    print(f"MSSQL returned: {mssql_data}")
    
    if mssql_data:
        response_data = {
            'full_name': mssql_data.get('full_name', ''),
            'mobile_number': mssql_data.get('mobile_number', ''),
            'department': mssql_data.get('department', ''),
            'section': mssql_data.get('section', '')
        }
        print(f"Returning JSON response: {response_data}")
        return JsonResponse(response_data)

    # Fallback to local user
    try:
        user = User.objects.get(username=username)
        name = user.full_name or user.get_full_name() or user.username
        response_data = {
            'full_name': name, 
            'mobile_number': user.mobile_number or '',
            'department': user.department or '',
            'section': user.section or ''
        }
        print(f"Returning fallback user data: {response_data}")
        return JsonResponse(response_data)
    except User.DoesNotExist:
        print(f"User {username} not found in local database")
        return JsonResponse({'full_name': '', 'mobile_number': '', 'department': '', 'section': ''})


@login_required
@require_POST
def submit_issue_request(request, category):
    return redirect('inventory:issue_requests')


@login_required
@require_POST
def approve_issue_request(request, pk):
    return redirect('inventory:issue_requests')


@login_required
@require_POST
def disapprove_issue_request(request, pk):
    return redirect('inventory:issue_requests')


# ---- New unified Issue Requests flow ----
@login_required
def issue_requests_new(request):
    """Simplified page for Stage 1/2 users to request items and see their requests."""
    if not request.user.can_approve_issue_requests():
        messages.error(request, 'This page is for Stage 1/2 users only.')
        return redirect('inventory:issue_requests')
    
    messages.info(request, 'Welcome! You can request items here and track your requests below.')
    
    raw_category = request.GET.get('category', '').strip()
    search_q = request.GET.get('q', '').strip()
    
    # Use category for Stage 1/2 users
    category = raw_category or 'networking'
    products_qs = Product.objects.filter(category=category).order_by('asset_id')
    
    # Search by asset / code / name
    if search_q:
        products_qs = products_qs.filter(
            Q(asset_id__icontains=search_q) |
            Q(item_code__icontains=search_q) |
            Q(item_name__icontains=search_q)
        )
    
    products = products_qs
    
    # Handle request form submission
    if request.method == 'POST' and request.POST.get('action') == 'request':
        form = IssueRequestForm(request.POST, request.FILES)
        asset_id = request.POST.get('asset_id', '').strip()
        if not asset_id or not form.is_valid():
            messages.error(request, 'Invalid request.')
            return redirect('inventory:issue_requests_new')
        
        product = Product.objects.filter(asset_id=asset_id).first()
        if not product:
            messages.error(request, 'Product not found.')
            return redirect('inventory:issue_requests_new')
        
        qty = form.cleaned_data['quantity']
        if product.quantity_available < qty:
            messages.error(request, 'Insufficient quantity.')
            return redirect('inventory:issue_requests_new')
        
        # Handle file upload with compression
        attachment_filename = _handle_compressed_upload(
            form.cleaned_data.get('attachment'), 
            'issue_request_files'
        )
        
        # Ensure proper path for Django FileField (upload_to='issue_request_files/')
        if attachment_filename and not attachment_filename.startswith('issue_request_files/'):
            attachment_path = f'issue_request_files/{attachment_filename}'
        else:
            attachment_path = attachment_filename
        
        ir = IssueRequest.objects.create(
            product=product,
            requested_by=request.user,
            requested_by_full_name=request.user.full_name or request.user.get_full_name() or request.user.username,
            requested_by_mobile=request.user.mobile_number or '',
            quantity=qty,
            request_reason=form.cleaned_data['reason'],
            attachment=attachment_path,
            status=IssueRequest.STATUS_PENDING,
        )
        
        # Add user location
        ir.requested_by_department = request.user.department
        ir.requested_by_section = request.user.section
        ir.save()
        _notify_issue_request_created(ir, request)
        messages.success(request, 'Request submitted. Waiting for approval.')
        return redirect('inventory:issue_requests_new')
    
    # Get user's requests (all statuses)
    my_requests = IssueRequest.objects.filter(
        requested_by=request.user
    ).select_related('product', 'approved_by', 'issued_by', 'confirmed_by').order_by('-created_at')[:100]
    
    # Get issued requests for confirmation
    issued_requests = IssueRequest.objects.filter(
        status=IssueRequest.STATUS_ISSUED,
        requested_by=request.user
    ).select_related('product', 'issued_by', 'approved_by').order_by('-issued_at')[:100]
    
    return render(request, 'inventory/issue_requests_new.html', {
        'category': category,
        'category_name': dict(CATEGORY_CHOICES).get(category, category),
        'products': products,
        'search_q': search_q,
        'form': IssueRequestForm(),
        'my_requests': my_requests,
        'issued_requests': issued_requests,
    })


@login_required
def issue_requests(request):
    """Unified page:
    - Stage 3: can request items and see "My requests".
    - Stage 1/2: can request items, approve / reject requests, and see pending + approved lists.
    """
    # Redirect based on user stage after login
    if request.GET.get('login_redirect'):
        if request.user.is_stage3():
            messages.info(request, 'Welcome! You can submit item requests here.')
        else:
            messages.info(request, 'Welcome! You can review and approve requests here.')
    
    # Show welcome message for new request form
    if request.GET.get('action') == 'new':
        messages.info(request, 'Fill in the form below to request an item.')
    
    raw_category = request.GET.get('category', '').strip()

    search_q = request.GET.get('q', '').strip()

    # Stage 3: search across all items (no category dropdown, no list until search)
    if request.user.is_stage3():
        category = ''
        products_qs = Product.objects.all().order_by('asset_id')
        if not search_q:
            products_qs = Product.objects.none()
    else:
        category = raw_category or 'networking'
        products_qs = Product.objects.filter(category=category).order_by('asset_id')

    # Stage 3 + others: search by asset / code / name
    if search_q:
        products_qs = products_qs.filter(
            Q(asset_id__icontains=search_q) |
            Q(item_code__icontains=search_q) |
            Q(item_name__icontains=search_q)
        )

    products = products_qs

    # Stage 3 and Stage 1/2 can create requests
    if (request.user.is_stage3() or request.user.can_approve_issue_requests()) and request.method == 'POST' and request.POST.get('action') == 'request':
        form = IssueRequestForm(request.POST, request.FILES)
        asset_id = request.POST.get('asset_id', '').strip()
        if not asset_id or not form.is_valid():
            messages.error(request, 'Invalid request.')
            return redirect("/issue-requests/")
        # All users select from table; asset id is enough
        products = Product.objects.filter(asset_id=asset_id)
        if not products.exists():
            messages.error(request, 'Product not found.')
            return redirect("/issue-requests/")
        if products.count() > 1:
            # If multiple products found, use first one and log warning
            product = products.first()
            messages.warning(request, f'Multiple products found for asset ID {asset_id}. Using first one.')
        else:
            product = products.first()
        qty = form.cleaned_data['quantity']
        if product.quantity_available < qty:
            messages.error(request, 'Insufficient quantity.')
            return redirect("/issue-requests/")
        
        # Handle file upload with compression
        attachment_filename = _handle_compressed_upload(
            form.cleaned_data.get('attachment'), 
            'issue_request_files'
        )
        
        # Ensure proper path for Django FileField (upload_to='issue_request_files/')
        if attachment_filename and not attachment_filename.startswith('issue_request_files/'):
            attachment_path = f'issue_request_files/{attachment_filename}'
        else:
            attachment_path = attachment_filename
        
        ir = IssueRequest.objects.create(
            product=product,
            requested_by=request.user,
            requested_by_full_name=request.user.full_name or request.user.get_full_name() or request.user.username,
            requested_by_mobile=request.user.mobile_number or '',
            quantity=qty,
            request_reason=form.cleaned_data['reason'],
            attachment=attachment_path,
            status=IssueRequest.STATUS_PENDING,
        )
        
        # Add user location (department/section) to request
        ir.requested_by_department = request.user.department
        ir.requested_by_section = request.user.section
        ir.save()
        _notify_issue_request_created(ir, request)
        messages.success(request, 'Request submitted. Waiting for approval.')
        return redirect("/issue-requests/")

    # Lists for the UI (with pagination)
    pending_qs = IssueRequest.objects.filter(status=IssueRequest.STATUS_PENDING).select_related('product', 'requested_by').order_by('-created_at')
    approved_qs = IssueRequest.objects.filter(status=IssueRequest.STATUS_APPROVED).select_related('product', 'requested_by').order_by('-approved_at')

    pending_paginator = Paginator(pending_qs, 25)
    approved_paginator = Paginator(approved_qs, 25)

    pending_page_number = request.GET.get('p_page') or 1
    approved_page_number = request.GET.get('a_page') or 1

    pending = pending_paginator.get_page(pending_page_number)
    approved_not_issued = approved_paginator.get_page(approved_page_number)

    my_requests = IssueRequest.objects.filter(requested_by=request.user).select_related('product').order_by('-created_at')[:100]
    
    # Add issued requests for confirmation (Stage 3 users)
    issued_requests = IssueRequest.objects.filter(
        status=IssueRequest.STATUS_ISSUED,
        requested_by=request.user
    ).select_related('product', 'issued_by', 'approved_by').order_by('-issued_at')[:100]

    # Add confirmed requests for Stage 1/2 users to see closed requests
    if request.user.can_approve_issue_requests():
        confirmed_requests = IssueRequest.objects.filter(
            status=IssueRequest.STATUS_CONFIRMED
        ).select_related('product', 'requested_by', 'approved_by', 'issued_by', 'confirmed_by').order_by('-confirmed_at')[:100]
    else:
        confirmed_requests = IssueRequest.objects.none()
    
    # Add my action items for all users
    if request.user.is_stage3():
        # Stage 3: Show their requests until confirmed
        my_action_items = IssueRequest.objects.filter(
            requested_by=request.user,
            status__in=[IssueRequest.STATUS_PENDING, IssueRequest.STATUS_APPROVED, IssueRequest.STATUS_ISSUED]
        ).select_related('product', 'requested_by', 'approved_by', 'rejected_by', 'issued_by', 'confirmed_by').order_by('-created_at')[:50]
    else:
        # Stage 1/2: Show all requests they need to act on
        my_action_items = IssueRequest.objects.filter(
            Q(status=IssueRequest.STATUS_PENDING) |
            Q(status=IssueRequest.STATUS_APPROVED) |
            Q(status=IssueRequest.STATUS_ISSUED)
        ).select_related('product', 'requested_by', 'approved_by', 'rejected_by', 'issued_by', 'confirmed_by').order_by('-created_at')[:50]
    
    return render(request, 'inventory/issue_requests.html', {
        'category': category,
        'category_name': dict(CATEGORY_CHOICES).get(category, category),
        'products': products,
        'search_q': search_q,
        'form': IssueRequestForm(),
        'pending_requests': pending,
        'approved_requests': approved_not_issued,
        'my_requests': my_requests,
        'issued_requests': issued_requests,
        'confirmed_requests': confirmed_requests,
        'my_action_items': my_action_items,
    })


@login_required
def issue_request_detail(request, request_id):
    """View individual issue request details by request_id."""
    try:
        issue_request = get_object_or_404(IssueRequest, request_id=request_id)
        
        # Check permissions: users can only view their own requests, admins can view all
        if not request.user.can_approve_issue_requests() and issue_request.requested_by != request.user:
            messages.error(request, 'Permission denied.')
            return redirect('inventory:issue_requests')
        
        return render(request, 'inventory/issue_request_detail.html', {
            'issue_request': issue_request,
        })
    except Exception as e:
        messages.error(request, f'Error loading request: {e}')
        return redirect('inventory:issue_requests')


@login_required
def issue_request_brochure(request, pk):
    """Brochure/print-friendly view of a single issue request."""
    ir = get_object_or_404(IssueRequest, pk=pk)
    if not request.user.can_approve_issue_requests() and ir.requested_by != request.user:
        messages.error(request, 'Permission denied.')
        return redirect('inventory:issue_requests')
    return render(request, 'inventory/issue_request_brochure.html', {'ir': ir})


@login_required
def issue_request_attachment(request, pk):
    """View/download the uploaded attachment for an issue request."""
    ir = get_object_or_404(IssueRequest, pk=pk)
    if not request.user.can_approve_issue_requests() and ir.requested_by != request.user:
        messages.error(request, 'Permission denied.')
        return redirect('inventory:issue_requests')
    if not ir.attachment:
        messages.error(request, 'No file attached to this request.')
        return redirect('inventory:issue_requests')

    as_attachment = request.GET.get('download') == '1'
    filename = ir.attachment.name.split('/')[-1]
    
    try:
        # Debug info
        print(f"DEBUG: Attachment name in DB: {ir.attachment.name}")
        print(f"DEBUG: Attachment path: {ir.attachment.path}")
        print(f"DEBUG: File exists check: {ir.attachment.storage.exists(ir.attachment.name)}")
        
        # Check if file exists
        if not ir.attachment.storage.exists(ir.attachment.name):
            messages.error(request, f'File not found on server. Path: {ir.attachment.name}')
            return redirect('inventory:issue_requests')
        
        # Get decompressed content if file is compressed
        file_path = ir.attachment.path
        if filename.endswith('.gz'):
            # Remove .gz extension for original filename
            original_filename = filename[:-3]
            content = get_compressed_file_content(file_path)
            
            # Detect content type from original filename
            content_type = 'application/octet-stream'
            if original_filename.lower().endswith('.pdf'):
                content_type = 'application/pdf'
            elif original_filename.lower().endswith(('.jpg', '.jpeg')):
                content_type = 'image/jpeg'
            elif original_filename.lower().endswith('.png'):
                content_type = 'image/png'
            elif original_filename.lower().endswith('.gif'):
                content_type = 'image/gif'
            elif original_filename.lower().endswith('.txt'):
                content_type = 'text/plain'
            
            response = HttpResponse(content, content_type=content_type)
            if as_attachment:
                response['Content-Disposition'] = f'attachment; filename="{original_filename}"'
            else:
                response['Content-Disposition'] = f'inline; filename="{original_filename}"'
                response['Cache-Control'] = 'public, max-age=0'
                if original_filename.lower().endswith('.pdf'):
                    response['X-Content-Type-Options'] = 'nosniff'
            return response
        else:
            # Serve file directly using HttpResponse for better compatibility
            file_obj = ir.attachment.open('rb')
            content = file_obj.read()
            file_obj.close()
            
            content_type = 'application/octet-stream'
            
            # Set proper content type based on extension
            if filename.lower().endswith('.pdf'):
                content_type = 'application/pdf'
            elif filename.lower().endswith(('.jpg', '.jpeg')):
                content_type = 'image/jpeg'
            elif filename.lower().endswith('.png'):
                content_type = 'image/png'
            elif filename.lower().endswith('.gif'):
                content_type = 'image/gif'
            elif filename.lower().endswith('.txt'):
                content_type = 'text/plain'
            elif filename.lower().endswith('.doc'):
                content_type = 'application/msword'
            elif filename.lower().endswith('.docx'):
                content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            elif filename.lower().endswith('.xls'):
                content_type = 'application/vnd.ms-excel'
            elif filename.lower().endswith('.xlsx'):
                content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            
            response = HttpResponse(content, content_type=content_type)
            if as_attachment:
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
            else:
                # For inline viewing - ensure browser displays the file
                response['Content-Disposition'] = f'inline; filename="{filename}"'
                # Prevent caching issues
                response['Cache-Control'] = 'public, max-age=0'
                # Ensure proper handling for PDFs
                if filename.lower().endswith('.pdf'):
                    response['X-Content-Type-Options'] = 'nosniff'
            return response
    except Exception as e:
        messages.error(request, f'Error accessing file: {str(e)}')
        return redirect('inventory:issue_requests')


@login_required
def peripheral_application_create(request):
    """Stage 3: create a brochure draft and show printable form."""
    if not request.user.is_stage3():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:issue_requests')
    pa = PeripheralApplication.objects.create(
        created_by=request.user,
        application_department=request.user.get_department_display() if getattr(request.user, 'department', None) else '',
        user_full_name=request.user.full_name or request.user.get_full_name() or request.user.username,
        employee_id=request.user.username,
        applicant_name=request.user.full_name or request.user.get_full_name() or request.user.username,
    )
    request.session['peripheral_application_id'] = pa.pk
    return redirect('inventory:peripheral_application_print', pk=pa.pk)


@login_required
def peripheral_application_print(request, pk):
    """Print view for brochure draft (prefilled)."""
    pa = get_object_or_404(PeripheralApplication, pk=pk)
    if pa.created_by != request.user and not request.user.can_approve_issue_requests():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:issue_requests')
    return render(request, 'inventory/peripheral_application_print.html', {'pa': pa})


@login_required
@require_POST
def issue_request_approve(request, pk):
    if not request.user.can_approve_issue_requests():
        messages.error(request, 'Only Stage 1/2 can approve requests.')
        return redirect('inventory:issue_requests')
    ir = get_object_or_404(IssueRequest, pk=pk, status=IssueRequest.STATUS_PENDING)

    # Determine approved quantity (can be less than requested)
    approved_raw = request.POST.get('approved_quantity', '').strip()
    try:
        approved_qty = int(approved_raw) if approved_raw else ir.quantity
    except ValueError:
        messages.error(request, 'Approved quantity must be a valid number.')
        return redirect('inventory:issue_requests')

    if approved_qty <= 0:
        messages.error(request, 'Approved quantity must be at least 1.')
        return redirect('inventory:issue_requests')

    if approved_qty > ir.quantity:
        messages.error(request, 'Approved quantity cannot be more than requested quantity.')
        return redirect('inventory:issue_requests')

    if ir.product.quantity_available < approved_qty:
        messages.error(request, 'Insufficient stock for approved quantity. Reject with reason instead.')
        return redirect('inventory:issue_requests')

    partial_reason = (request.POST.get('partial_reason') or '').strip()
    if approved_qty < ir.quantity and not partial_reason:
        messages.error(request, 'Reason is required when approving less than requested.')
        return redirect('inventory:issue_requests')

    # Approve only (no stock change yet); item is marked "issue completed" when handover is done
    ir.status = IssueRequest.STATUS_APPROVED
    ir.approved_quantity = approved_qty
    ir.approval_note = partial_reason if approved_qty < ir.quantity else ''
    ir.approved_by = request.user
    ir.approved_at = timezone.now()
    ir.approved_by_section = request.user.section  # Capture user section
    ir.approved_by_department = request.user.department  # Capture user department
    ir.rejection_reason = ''
    ir.rejected_by = None
    ir.rejected_at = None
    ir.save()
    _notify_issue_request_decision(ir, approved=True, request=request)
    messages.success(request, 'Request approved. Mark as issued when the item is handed over.')
    return redirect('inventory:issue_requests')


@login_required
@require_POST
def issue_request_reject(request, pk):
    if not request.user.can_approve_issue_requests():
        messages.error(request, 'Only Stage 1/2 can reject requests.')
        return redirect('inventory:issue_requests')
    ir = get_object_or_404(IssueRequest, pk=pk, status=IssueRequest.STATUS_PENDING)
    reason = (request.POST.get('reason') or '').strip()
    if not reason:
        messages.error(request, 'Reject reason is required.')
        return redirect('inventory:issue_requests')
    ir.status = IssueRequest.STATUS_REJECTED
    ir.rejected_by = request.user
    ir.rejected_at = timezone.now()
    ir.rejected_by_section = request.user.section  # Capture user section
    ir.rejected_by_department = request.user.department  # Capture user department
    ir.rejection_reason = reason
    ir.save()
    _notify_issue_request_decision(ir, approved=False, request=request)
    messages.success(request, 'Request rejected.')
    return redirect('inventory:issue_requests')


@login_required
@require_POST
def issue_request_issue(request, pk):
    """Stage 1/2: mark approved request as issued (handover) - deduct stock, create IssueHistory, status -> Issue completed."""
    if not request.user.can_approve_issue_requests():
        messages.error(request, 'Only Stage 1/2 can mark as issued.')
        return redirect('inventory:issue_requests')
    ir = get_object_or_404(IssueRequest, pk=pk, status=IssueRequest.STATUS_APPROVED)
    qty_to_issue = ir.approved_quantity or ir.quantity
    if ir.product.quantity_available < qty_to_issue:
        messages.error(request, 'Insufficient stock.')
        return redirect('inventory:issue_requests')
    product = ir.product
    product.quantity_available -= qty_to_issue
    product.save()
    _notify_low_stock(product, request)
    unit_price = _as_decimal(product.price)
    total_cost = unit_price * Decimal(qty_to_issue) if unit_price is not None else None
    IssueHistory.objects.create(
        product=product,
        issued_by=request.user,
        issued_by_section=request.user.section,  # Capture user section
        issued_by_department=request.user.department,  # Capture user department
        approved_by=ir.approved_by,
        approved_by_section=ir.approved_by_section,  # Transfer from request
        approved_by_department=ir.approved_by_department,  # Transfer from request
        receiver=ir.requested_by,
        receiver_full_name=ir.requested_by_full_name,
        receiver_mobile=ir.requested_by_mobile,
        quantity=qty_to_issue,
        unit_price=unit_price,
        total_cost=total_cost,
    )
    ir.status = IssueRequest.STATUS_ISSUED
    ir.issued_by = request.user
    ir.issued_by_section = request.user.section  # Capture user section
    ir.issued_by_department = request.user.department  # Capture user department
    ir.issued_at = timezone.now()
    ir.save()
    # Send email notification for issued status
    send_issue_request_email(ir, 'issued', request)
    messages.success(request, 'Marked as issued (issue completed).')
    return redirect('inventory:issue_requests')


@login_required
@require_POST
def issue_request_confirm(request, pk):
    """User confirms receipt of issued item. Works for both Stage 3 and Stage 1/2 users."""
    ir = get_object_or_404(IssueRequest, pk=pk, status=IssueRequest.STATUS_ISSUED)
    
    # Only the requester can confirm receipt (works for any stage)
    if ir.requested_by != request.user:
        messages.error(request, 'Only the requester can confirm receipt.')
        return redirect('inventory:issue_requests')
    
    ir.status = IssueRequest.STATUS_CONFIRMED
    ir.confirmed_by = request.user
    ir.confirmed_by_section = request.user.section  # Capture user section
    ir.confirmed_by_department = request.user.department  # Capture user department
    ir.confirmed_at = timezone.now()
    ir.save()
    
    messages.success(request, 'Receipt confirmed. Issue completed.')
    return redirect('inventory:issue_requests')


@login_required
@require_POST
def issue_request_confirm(request, pk):
    """User confirms receipt of issued item. Works for both Stage 3 and Stage 1/2 users."""
    ir = get_object_or_404(IssueRequest, pk=pk, status=IssueRequest.STATUS_ISSUED)
    
    # Only the requester can confirm receipt (works for any stage)
    if ir.requested_by != request.user:
        messages.error(request, 'Only the requester can confirm receipt.')
        return redirect('inventory:issue_requests')
    
    ir.status = IssueRequest.STATUS_CONFIRMED
    ir.confirmed_by = request.user
    ir.confirmed_by_section = request.user.section  # Capture user section
    ir.confirmed_by_department = request.user.department  # Capture user department
    ir.confirmed_at = timezone.now()
    ir.save()
    
    # Send email notification for confirmation
    send_issue_request_email(ir, 'confirmed', request)
    messages.success(request, 'Receipt confirmed. Request completed.')
    return redirect('inventory:issue_requests')


# ---- Upload Items / Upload History ----
@login_required
def upload_items(request, category):
    if category not in request.user.allowed_categories() or not request.user.can_edit():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:dashboard')
    products = Product.objects.filter(category=category).order_by('asset_id')
    if request.method == 'POST':
        form = UploadQuantityForm(request.POST)
        asset_id = request.POST.get('asset_id')
        if asset_id and form.is_valid():
            product = get_object_or_404(Product, category=category, asset_id=asset_id)
            qty = form.cleaned_data['quantity_added']
            product.quantity_available += qty
            product.save()
            unit_price = _as_decimal(product.price)
            total_cost = None
            if unit_price is not None:
                total_cost = unit_price * Decimal(qty)
            UploadHistory.objects.create(
                product=product,
                uploaded_by=request.user,
                quantity_added=qty,
                unit_price=unit_price,
                total_cost=total_cost,
            )
            messages.success(request, f'Added {qty} to {product.item_name}.')
            return redirect('inventory:upload_items', category=category)
    else:
        form = UploadQuantityForm()
    return render(request, 'inventory/upload_items.html', {
        'category': category,
        'category_name': dict(CATEGORY_CHOICES).get(category, category),
        'products': products,
        'form': form,
    })


@login_required
def upload_history(request, category):
    if category not in request.user.allowed_categories():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:dashboard')
    qs = UploadHistory.objects.filter(product__category=category).select_related('product', 'uploaded_by').order_by('-uploaded_at')
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    search_date = request.GET.get('date', '')
    search_month = request.GET.get('month', '')
    search_day = request.GET.get('day', '')
    if from_date:
        qs = qs.filter(uploaded_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(uploaded_at__date__lte=to_date)
    if search_date:
        qs = qs.filter(uploaded_at__date=search_date)
    if search_month:
        try:
            qs = qs.filter(uploaded_at__month=int(search_month))
        except ValueError:
            pass
    if search_day:
        try:
            qs = qs.filter(uploaded_at__week_day=int(search_day))  # 1=Sunday, 7=Saturday
        except ValueError:
            pass
    return render(request, 'inventory/upload_history.html', {
        'category': category,
        'category_name': dict(CATEGORY_CHOICES).get(category, category),
        'records': qs,
        'from_date': from_date,
        'to_date': to_date,
        'search_date': search_date,
        'search_month': search_month,
        'search_day': search_day,
    })


@login_required
def upload_history_pdf(request, category):
    if category not in request.user.allowed_categories():
        return HttpResponse('Forbidden', status=403)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from io import BytesIO
    except ImportError:
        return HttpResponse('PDF export requires reportlab. Install with: pip install reportlab', status=501)

    qs = UploadHistory.objects.filter(product__category=category).select_related('product', 'uploaded_by').order_by('-uploaded_at')
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    search_date = request.GET.get('date', '')
    search_month = request.GET.get('month', '')
    search_day = request.GET.get('day', '')
    if from_date:
        qs = qs.filter(uploaded_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(uploaded_at__date__lte=to_date)
    if search_date:
        qs = qs.filter(uploaded_at__date=search_date)
    if search_month:
        try:
            qs = qs.filter(uploaded_at__month=int(search_month))
        except ValueError:
            pass
    if search_day:
        try:
            qs = qs.filter(uploaded_at__week_day=int(search_day))
        except ValueError:
            pass

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph(f'Upload History - {dict(CATEGORY_CHOICES).get(category, category)}', styles['Title']))
    elements.append(Spacer(1, 12))
    data = [['Date', 'Asset ID', 'Item', 'Location', 'Qty added', 'Unit price', 'Total', 'Uploaded by']]
    for r in qs[:500]:
        data.append([
            r.uploaded_at.strftime('%Y-%m-%d %H:%M'),
            r.product.asset_id,
            r.product.item_name,
            (r.product.computed_location or r.product.location or '-'),
            str(r.quantity_added),
            str(r.unit_price) if r.unit_price is not None else '-',
            str(r.total_cost) if r.total_cost is not None else '-',
            r.uploaded_by.username if r.uploaded_by else '-',
        ])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    response = HttpResponse(buf.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=\"upload_history_{category}.pdf\"'
    return response


# ---- Order ----
@login_required
def order_create(request, category):
    if category not in request.user.allowed_categories() or not request.user.can_edit():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:dashboard')
    products = Product.objects.filter(category=category).order_by('asset_id')
    if request.method == 'POST':
        form = OrderForm(request.POST)
        asset_id = request.POST.get('asset_id')
        if asset_id and form.is_valid():
            product = get_object_or_404(Product, category=category, asset_id=asset_id)
            unit_price = _as_decimal(product.price)
            qty_req = form.cleaned_data['quantity_requested']
            total_req = None
            if unit_price is not None:
                total_req = unit_price * Decimal(qty_req)
            Order.objects.create(
                product=product,
                requested_by=request.user,
                quantity_requested=qty_req,
                status=Order.STATUS_PENDING,
                unit_price=unit_price,
                total_cost_requested=total_req,
                total_cost_provided=Decimal('0.00') if unit_price is not None else None,
            )
            messages.success(request, 'Order request saved.')
            return redirect('inventory:order_list', category=category)
    else:
        form = OrderForm()
    return render(request, 'inventory/order_create.html', {
        'category': category,
        'category_name': dict(CATEGORY_CHOICES).get(category, category),
        'products': products,
        'form': form,
    })


@login_required
def order_list(request, category):
    if category not in request.user.allowed_categories():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:dashboard')
    qs = Order.objects.filter(product__category=category).select_related('product', 'requested_by').order_by('-created_at')
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    search_date = request.GET.get('date', '')
    search_month = request.GET.get('month', '')
    search_day = request.GET.get('day', '')
    if from_date:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(created_at__date__lte=to_date)
    if search_date:
        qs = qs.filter(created_at__date=search_date)
    if search_month:
        try:
            qs = qs.filter(created_at__month=int(search_month))
        except ValueError:
            pass
    if search_day:
        try:
            qs = qs.filter(created_at__week_day=int(search_day))
        except ValueError:
            pass
    return render(request, 'inventory/order_list.html', {
        'category': category,
        'category_name': dict(CATEGORY_CHOICES).get(category, category),
        'orders': qs,
        'from_date': from_date,
        'to_date': to_date,
        'search_date': search_date,
        'search_month': search_month,
        'search_day': search_day,
    })


@login_required
def order_history_excel(request, category):
    if category not in request.user.allowed_categories():
        return HttpResponse('Forbidden', status=403)
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        from io import BytesIO
    except ImportError:
        return HttpResponse('Excel export requires openpyxl. Install with: pip install openpyxl', status=501)

    qs = Order.objects.filter(product__category=category).select_related('product', 'requested_by').order_by('-created_at')
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    search_date = request.GET.get('date', '')
    search_month = request.GET.get('month', '')
    search_day = request.GET.get('day', '')
    if from_date:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(created_at__date__lte=to_date)
    if search_date:
        qs = qs.filter(created_at__date=search_date)
    if search_month:
        try:
            qs = qs.filter(created_at__month=int(search_month))
        except ValueError:
            pass
    if search_day:
        try:
            qs = qs.filter(created_at__week_day=int(search_day))
        except ValueError:
            pass

    # Create workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Order History"
    
    # Headers
    headers = ['Date', 'Asset ID', 'Item Name', 'Requested', 'Provided', 'Unit Price', 'Total Requested', 'Total Provided', 'Status']
    
    # Add headers
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                           top=Side(style='thin'), bottom=Side(style='thin'))
    
    # Add data
    for row, o in enumerate(qs[:500], 2):
        data = [
            o.created_at.strftime('%Y-%m-%d %H:%M'),
            o.product.asset_id,
            o.product.item_name,
            str(o.quantity_requested),
            str(o.quantity_provided),
            str(o.unit_price) if o.unit_price is not None else '-',
            str(o.total_cost_requested) if o.total_cost_requested is not None else '-',
            str(o.total_cost_provided) if o.total_cost_provided is not None else '-',
            o.status,
        ]
        
        for col, value in enumerate(data, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                               top=Side(style='thin'), bottom=Side(style='thin'))
    
    # Set column widths
    column_widths = [18, 12, 30, 12, 12, 12, 15, 15, 12]
    for col, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    
    # Save to memory
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    
    # Create response
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="order_history_{category}.xlsx"'
    return response


@login_required
@require_POST
def order_fulfill(request, pk):
    if not request.user.can_edit():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:dashboard')
    order = get_object_or_404(Order, pk=pk)
    if order.product.category not in request.user.allowed_categories():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:dashboard')
    form = OrderFulfillForm(request.POST)
    if form.is_valid():
        qty = form.cleaned_data['quantity_provided']
        order.quantity_provided += qty
        order.product.quantity_available += qty
        order.product.save()
        if order.unit_price is None:
            order.unit_price = _as_decimal(order.product.price)
        if order.unit_price is not None:
            order.total_cost_provided = (order.unit_price * Decimal(order.quantity_provided))
        if order.quantity_provided >= order.quantity_requested:
            order.status = Order.STATUS_COMPLETED
        else:
            order.status = Order.STATUS_PARTIAL
        order.save()
        messages.success(request, 'Quantity updated.')
    return redirect('inventory:order_list', category=order.product.category)


@login_required
@require_POST
def order_mark_disclosed(request, pk):
    if not request.user.can_edit():
        return redirect('inventory:dashboard')
    order = get_object_or_404(Order, pk=pk)
    if order.product.category not in request.user.allowed_categories():
        return redirect('inventory:dashboard')
    order.status = Order.STATUS_DISCLOSED
    order.save()
    messages.success(request, 'Order marked as Disclosed.')
    return redirect('inventory:order_list', category=order.product.category)


# ---- History (issued items) ----
@login_required
def issue_history(request, category):
    if category not in request.user.allowed_categories():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:dashboard')
    qs = IssueHistory.objects.filter(product__category=category).select_related('product', 'issued_by', 'approved_by', 'receiver').order_by('-issued_at')
    
    # Also get confirmed requests for the completed requests table
    confirmed_requests = IssueRequest.objects.filter(status='confirmed', product__category=category).select_related('product', 'requested_by', 'approved_by', 'rejected_by', 'issued_by', 'confirmed_by').order_by('-confirmed_at')
    
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    search_date = request.GET.get('date', '')
    search_day = request.GET.get('day', '')
    search_month = request.GET.get('month', '')
    if from_date:
        qs = qs.filter(issued_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(issued_at__date__lte=to_date)
    if search_date:
        qs = qs.filter(issued_at__date=search_date)
    if search_day:
        try:
            qs = qs.filter(issued_at__week_day=int(search_day))
        except ValueError:
            pass
    if search_month:
        try:
            qs = qs.filter(issued_at__month=int(search_month))
        except ValueError:
            pass

    return render(request, 'inventory/issue_history.html', {
        'category': category,
        'category_name': dict(CATEGORY_CHOICES).get(category, category),
        'records': qs,
        'confirmed_requests': confirmed_requests,
        'from_date': from_date,
        'to_date': to_date,
        'search_date': search_date,
        'search_day': search_day,
        'search_month': search_month,
    })


@login_required
def issued_overview(request):
    """Stage 1/2 overview: 4 per-category charts + 1 all-categories chart."""
    if not request.user.can_approve_issue_requests():
        messages.error(request, 'Only Stage 1/2 can view issued overview.')
        return redirect('inventory:dashboard')

    label_map = dict(CATEGORY_CHOICES)

    # Totals by category (for line chart + table)
    by_category_rows = (
        IssueHistory.objects.values('product__category')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')
    )
    by_category = [
        {
            'slug': row['product__category'],
            'name': label_map.get(row['product__category'], row['product__category']),
            'total': row['total_qty'] or 0,
        }
        for row in by_category_rows
    ]

    # Totals by item (for table) - top 100 items
    by_item_rows = (
        IssueHistory.objects.values('product__category', 'product__asset_id', 'product__item_name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:100]
    )
    by_item = [
        {
            'category': label_map.get(r['product__category'], r['product__category']),
            'asset_id': r['product__asset_id'],
            'item_name': r['product__item_name'],
            'total': r['total_qty'] or 0,
        }
        for r in by_item_rows
    ]

    line_series = [{'label': r['name'], 'value': r['total']} for r in by_category]

    return render(request, 'inventory/issued_overview.html', {
        'line_series_json': json.dumps(line_series),
        'by_category': by_category,
        'by_item': by_item,
    })


@login_required
def issued_overview_pdf(request):
    if not request.user.can_approve_issue_requests():
        return HttpResponse('Forbidden', status=403)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from io import BytesIO
    except ImportError:
        return HttpResponse('PDF export requires reportlab.', status=501)

    label_map = dict(CATEGORY_CHOICES)
    by_category_rows = (
        IssueHistory.objects.values('product__category')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')
    )
    by_item_rows = (
        IssueHistory.objects.values('product__category', 'product__asset_id', 'product__item_name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:500]
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter))
    styles = getSampleStyleSheet()
    elements = [Paragraph('Issued Overview', styles['Title']), Spacer(1, 12)]

    elements.append(Paragraph('Total issued by category', styles['Heading2']))
    data = [['Category', 'Total issued']]
    for r in by_category_rows:
        data.append([label_map.get(r['product__category'], r['product__category']), str(r['total_qty'] or 0)])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 12))

    elements.append(Paragraph('Total issued by item (top 500)', styles['Heading2']))
    data2 = [['Category', 'Asset ID', 'Item', 'Total issued']]
    for r in by_item_rows:
        data2.append([
            label_map.get(r['product__category'], r['product__category']),
            r['product__asset_id'],
            r['product__item_name'],
            str(r['total_qty'] or 0),
        ])
    t2 = Table(data2, repeatRows=1)
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(t2)

    doc.build(elements)
    buf.seek(0)
    response = HttpResponse(buf.read(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="issued_overview.pdf"'
    return response


@login_required
def issue_history_pdf(request, category):
    if category not in request.user.allowed_categories():
        return HttpResponse('Forbidden', status=403)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from io import BytesIO
    except ImportError:
        return HttpResponse('PDF export requires reportlab. Install with: pip install reportlab', status=501)
    qs = IssueHistory.objects.filter(product__category=category).select_related('product', 'issued_by', 'receiver').order_by('-issued_at')
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    search_date = request.GET.get('date', '')
    search_day = request.GET.get('day', '')
    search_month = request.GET.get('month', '')
    if from_date:
        qs = qs.filter(issued_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(issued_at__date__lte=to_date)
    if search_date:
        qs = qs.filter(issued_at__date=search_date)
    if search_day:
        try:
            qs = qs.filter(issued_at__week_day=int(search_day))
        except ValueError:
            pass
    if search_month:
        try:
            qs = qs.filter(issued_at__month=int(search_month))
        except ValueError:
            pass
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph(f'Issue History - {dict(CATEGORY_CHOICES).get(category, category)}', styles['Title']))
    elements.append(Spacer(1, 12))
    data = [['Asset ID', 'Item', 'Receiver', 'Mobile', 'Quantity', 'Unit price', 'Total', 'Issued By', 'Date']]
    for r in qs:
        data.append([
            r.product.asset_id,
            r.product.item_name,
            (r.receiver_full_name or (r.receiver.username if r.receiver else '-')),
            (r.receiver_mobile or '-'),
            str(r.quantity),
            str(r.unit_price) if r.unit_price is not None else '-',
            str(r.total_cost) if r.total_cost is not None else '-',
            r.issued_by.username if r.issued_by else '-',
            r.issued_at.strftime('%Y-%m-%d %H:%M'),
        ])
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    response = HttpResponse(buf.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="issue_history_{category}.pdf"'
    return response


@login_required
def my_history(request):
    """Stage 3: show my requests and issued items history."""
    my_requests = IssueRequest.objects.filter(requested_by=request.user).select_related('product').order_by('-created_at')[:200]
    my_issued = IssueHistory.objects.filter(receiver=request.user).select_related('product', 'issued_by', 'approved_by').order_by('-issued_at')[:200]
    return render(request, 'inventory/my_history.html', {'my_requests': my_requests, 'my_issued': my_issued})


@login_required
def item_requests_history(request):
    """Item request history (all requests including pending, approved, rejected, issued, confirmed) for Stage 1/2."""
    if not request.user.can_approve_issue_requests():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:dashboard')
    asset = request.GET.get('asset_id', '').strip()
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    
    # Get all requests (not just non-pending) for complete history
    qs = IssueRequest.objects.select_related('product', 'requested_by', 'approved_by', 'rejected_by', 'issued_by', 'confirmed_by').order_by('-created_at')
    
    if asset:
        qs = qs.filter(product__asset_id__icontains=asset)
    if from_date:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(created_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(created_at__month=int(month))
        except ValueError:
            pass
    return render(request, 'inventory/item_requests_history.html', {
        'records': qs[:500],
        'confirmed_requests': qs[:500],  # Use all requests for the completed requests table
        'asset_id': asset,
        'from_date': from_date,
        'to_date': to_date,
        'search_month': month,
    })


@login_required
def item_requests_history_pdf(request):
    if not request.user.can_approve_issue_requests():
        return HttpResponse('Forbidden', status=403)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from io import BytesIO
    except ImportError:
        return HttpResponse('PDF export requires reportlab. Install with: pip install reportlab', status=501)
    asset = request.GET.get('asset_id', '').strip()
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    qs = IssueRequest.objects.exclude(status=IssueRequest.STATUS_PENDING).select_related('product', 'requested_by', 'approved_by', 'rejected_by', 'issued_by').order_by('-updated_at')
    if asset:
        qs = qs.filter(product__asset_id__icontains=asset)
    if from_date:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(created_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(created_at__month=int(month))
        except ValueError:
            pass
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph('Item Requests - Issued History', styles['Title']))
    elements.append(Spacer(1, 12))
    data = [['Date', 'Asset ID', 'Item', 'User', 'Mobile', 'Qty', 'Status', 'Approved by', 'Rejected by', 'Reason', 'Issued by']]
    for r in qs[:500]:
        data.append([
            r.created_at.strftime('%Y-%m-%d %H:%M'),
            r.product.asset_id,
            r.product.item_name,
            r.requested_by_full_name or (r.requested_by.username if r.requested_by else '-'),
            r.requested_by_mobile or '-',
            str(r.quantity),
            r.get_status_display(),
            r.approved_by.username if r.approved_by else '-',
            r.rejected_by.username if r.rejected_by else '-',
            (r.rejection_reason or '-'),
            r.issued_by.username if r.issued_by else '-',
        ])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    response = HttpResponse(buf.read(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename=\"item_requests_issued_history.pdf\"'
    return response


@login_required
def item_requests_history_excel(request):
    if not request.user.can_approve_issue_requests():
        return HttpResponse('Forbidden', status=403)
    
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        from io import BytesIO
    except ImportError:
        return HttpResponse('Excel export requires openpyxl. Install with: pip install openpyxl', status=501)
    
    asset = request.GET.get('asset_id', '').strip()
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    
    qs = IssueRequest.objects.exclude(status=IssueRequest.STATUS_PENDING).select_related(
        'product', 'requested_by', 'approved_by', 'rejected_by', 'issued_by', 'confirmed_by'
    ).order_by('-updated_at')
    
    if asset:
        qs = qs.filter(product__asset_id__icontains=asset)
    if from_date:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(created_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(created_at__month=int(month))
        except ValueError:
            pass
    
    # Create workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Item Requests History"
    
    # Headers
    headers = [
        'Request ID', 'Date/Time', 'Asset ID', 'Item Name', 'User', 'User Dept|Section', 
        'Mobile', 'Quantity', 'Reason for Request', 'Approved By', 'Rejected By', 
        'Reject Reason', 'Issued By', 'Confirmed By', 'Confirmed DateTime', 'Status'
    ]
    
    # Add headers
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                           top=Side(style='thin'), bottom=Side(style='thin'))
    
    # Add data
    for row, ir in enumerate(qs[:500], 2):
        data = [
            ir.request_id or ir.id,
            ir.created_at.strftime('%Y-%m-%d %H:%M') if ir.created_at else '',
            ir.product.asset_id if ir.product else '',
            ir.product.item_name if ir.product else '',
            f"{ir.requested_by.username} | {ir.requested_by_full_name}" if ir.requested_by else '',
            f"{ir.get_requested_by_department_display()} | {ir.get_requested_by_section_display()}" if ir.requested_by_department else '',
            ir.requested_by_mobile or '',
            str(ir.approved_quantity or ir.quantity),
            ir.request_reason or '',
            f"{ir.approved_by.username}" + (f"\n{ir.approved_by.get_full_name()}" if ir.approved_by.get_full_name() else "") if ir.approved_by else '',
            f"{ir.rejected_by.username}" + (f"\n{ir.rejected_by.get_full_name()}" if ir.rejected_by.get_full_name() else "") if ir.rejected_by else '',
            ir.rejection_reason or '',
            f"{ir.issued_by.username}" + (f"\n{ir.issued_by.get_full_name()}" if ir.issued_by.get_full_name() else "") if ir.issued_by else '',
            f"{ir.confirmed_by.username}" + (f"\n{ir.confirmed_by.get_full_name()}" if ir.confirmed_by.get_full_name() else "") if ir.confirmed_by else '',
            ir.confirmed_at.strftime('%Y-%m-%d %H:%M') if ir.confirmed_at else '',
            ir.get_status_display()
        ]
        
        for col, value in enumerate(data, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                               top=Side(style='thin'), bottom=Side(style='thin'))
            
            # Set special formatting for Reason for Request and Reject Reason columns (col 9 and 12)
            if col in [9, 12]:
                cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    
    # Set column widths
    column_widths = [12, 18, 12, 25, 20, 18, 12, 8, 30, 20, 20, 30, 20, 20, 18, 12]
    for col, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    
    # Save to memory
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    
    # Create response
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="item_requests_history.xlsx"'
    return response


# ---- Upload Requests to Management ----
@login_required
def management_upload_requests(request):

    category = request.GET.get('category', '').strip()

    if request.user.stage == 3 and not request.user.is_superuser:
        messages.error(request, 'Upload Requests are only available for Stage 1 and Stage 2.')
        return redirect('inventory:dashboard')

    qs = ManagementUploadRequest.objects.select_related(
        'product', 'requested_by'
    ).order_by('-created_at')

    if category:
        qs = qs.filter(product__category=category)

    products = Product.objects.all().order_by('category', 'asset_id')

    if request.method == 'POST' and request.POST.get('action') == 'request':

        asset_id = request.POST.get('asset_id', '').strip()
        qty = request.POST.get('quantity_requested', '').strip()

        if not asset_id or not qty.isdigit() or int(qty) <= 0:
            messages.error(request, 'Select Asset ID and enter a valid quantity.')
            return redirect('inventory:management_upload_requests')

        product = get_object_or_404(Product, asset_id=asset_id)

        ManagementUploadRequest.objects.create(
            product=product,
            requested_by=request.user,
            quantity_requested=int(qty),
            status=ManagementUploadRequest.STATUS_PENDING,
        )

        messages.success(request, 'Upload request saved (internal).')
        return redirect('inventory:management_upload_requests')

    reqs = list(qs[:300])

    for r in reqs:
        try:
            r.remaining = max(0, int(r.quantity_requested) - int(r.quantity_received))
        except Exception:
            r.remaining = 0

    return render(request, 'inventory/management_upload_requests.html', {
        'requests': reqs,
        'products': products,
        'selected_category': category,
        'categories': [{'slug': c[0], 'name': c[1]} for c in CATEGORY_CHOICES],
        'can_fulfill': request.user.stage in [1, 2] or request.user.is_superuser,
    })


# ---- Fulfill Request ----
@login_required
@require_POST
def management_upload_request_fulfill(request, pk):

    if not (request.user.stage in [1, 2] or request.user.is_superuser):
        messages.error(request, 'Only Stage 1/2 can fulfill.')
        return redirect('inventory:management_upload_requests')

    req = get_object_or_404(
        ManagementUploadRequest,
        pk=pk,
        status=ManagementUploadRequest.STATUS_PENDING
    )

    qty_raw = request.POST.get('quantity_received', '').strip()
    if not qty_raw.isdigit() or int(qty_raw) <= 0:
        messages.error(request, 'Enter a valid received quantity.')
        return redirect('inventory:management_upload_requests')
    qty = int(qty_raw)

    receipt = request.FILES.get('receipt')
    if not receipt:
        messages.error(request, 'Please upload a supporting file before marking as received.')
        return redirect('inventory:management_upload_requests')

    total_received = req.quantity_received + qty
    remaining = req.quantity_requested - total_received

    if remaining < 0:
        messages.error(request, 'Received quantity exceeds requested.')
        return redirect('inventory:management_upload_requests')

    # update received
    req.quantity_received = total_received

    # update stock
    req.product.quantity_available += qty
    req.product.save()

    # store receipt file with compression and hashed name (Stage 1/2 only view)
    content = receipt.read()
    digest = hashlib.sha256(content).hexdigest()
    ext = Path(receipt.name).suffix or '.bin'
    
    # Compress content if beneficial
    compressed_content, is_compressed, original_size, compressed_size = compress_file_content(content, receipt.name)
    
    if is_compressed:
        hashed_name = f"{digest}{ext}.gz"
        print(f"🗜️ Receipt file compressed: {original_size:,} → {compressed_size:,} bytes "
              f"({round((1 - compressed_size / original_size) * 100, 1)}% saved)")
    else:
        hashed_name = f"{digest}{ext}"
    
    req.receipt_file.save(hashed_name, ContentFile(compressed_content), save=False)
    req.receipt_file_hash = digest

    unit_price = _as_decimal(req.product.price)
    total_cost = unit_price * Decimal(qty) if unit_price else None

    UploadHistory.objects.create(
        product=req.product,
        uploaded_by=request.user,
        quantity_added=qty,
        unit_price=unit_price,
        total_cost=total_cost,
    )

    # partial receive
    if remaining > 0:

        ManagementUploadRequest.objects.create(
            product=req.product,
            requested_by=req.requested_by,
            quantity_requested=remaining,
            quantity_received=0,
            status=ManagementUploadRequest.STATUS_PENDING,
        )

        req.status = ManagementUploadRequest.STATUS_COMPLETED

    else:
        req.status = ManagementUploadRequest.STATUS_COMPLETED

    req.save()

    messages.success(request, 'Request updated.')
    return redirect('inventory:management_upload_requests')


# ---- Disclose Request ----
@login_required
@require_POST
def management_upload_request_disclose(request, pk):

    if not (request.user.stage in [1, 2] or request.user.is_superuser):
        messages.error(request, 'Only Stage 1/2 can disclose.')
        return redirect('inventory:management_upload_requests')

    req = get_object_or_404(
        ManagementUploadRequest,
        pk=pk,
        status=ManagementUploadRequest.STATUS_PENDING
    )

    req.status = ManagementUploadRequest.STATUS_DISCLOSED
    req.save()

    messages.success(request, 'Marked as Disclosed.')
    return redirect('inventory:management_upload_requests')


@login_required
def management_upload_request_receipt(request, pk):
    """Download receipt file for a management upload request (Stage 1/2 only)."""
    if not (request.user.stage in [1, 2] or request.user.is_superuser):
        messages.error(request, 'Only Stage 1/2 can view receipts.')
        return redirect('inventory:dashboard')
    req = get_object_or_404(ManagementUploadRequest, pk=pk)
    if not req.receipt_file:
        messages.error(request, 'No file attached for this request.')
        return redirect('inventory:management_upload_requests')
    
    filename = req.receipt_file.name.split('/')[-1]
    
    # Get decompressed content if file is compressed
    file_path = req.receipt_file.path
    if filename.endswith('.gz'):
        # Remove .gz extension for original filename
        original_filename = filename[:-3]
        content = get_compressed_file_content(file_path)
        response = HttpResponse(content, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="receipt_{req.request_id or req.pk}{original_filename}"'
        return response
    else:
        return FileResponse(
            req.receipt_file.open('rb'),
            as_attachment=True,
            filename=f"receipt_{req.request_id or req.pk}{Path(req.receipt_file.name).suffix}",
        )


# ---- PDF Export ----
@login_required
def management_upload_requests_excel(request):
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        from io import BytesIO
    except ImportError:
        return HttpResponse('Excel export requires openpyxl. Install with: pip install openpyxl', status=501)

    category = request.GET.get('category', '').strip()

    if request.user.stage == 3 and not request.user.is_superuser:
        return HttpResponse('Forbidden', status=403)

    qs = ManagementUploadRequest.objects.select_related(
        'product', 'requested_by'
    ).order_by('-created_at')

    if category:
        qs = qs.filter(product__category=category)

    # Create workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Upload Requests (Management)"
    
    # Headers
    headers = ['Date', 'Request ID', 'Asset ID', 'Item Name', 'Requested', 'Received', 'Remaining', 'Status', 'By']
    
    # Add headers
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                           top=Side(style='thin'), bottom=Side(style='thin'))
    
    # Add data
    for row, r in enumerate(qs[:500], 2):
        remaining = max(0, r.quantity_requested - r.quantity_received)
        
        data = [
            r.created_at.strftime('%Y-%m-%d %H:%M'),
            str(r.request_id or ''),
            r.product.asset_id,
            r.product.item_name,
            str(r.quantity_requested),
            str(r.quantity_received),
            str(remaining),
            r.status,
            r.requested_by.username if r.requested_by else '-',
        ]
        
        for col, value in enumerate(data, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                               top=Side(style='thin'), bottom=Side(style='thin'))
    
    # Set column widths
    column_widths = [18, 12, 12, 30, 12, 12, 12, 12, 15]
    for col, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    
    # Save to memory
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    
    # Create response
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="upload_requests_management.xlsx"'
    return response
# ---- Profile / Settings / Add User ----
@login_required
def profile(request):
    return render(request, 'inventory/profile.html')


# ---- Stage 1 Reports: All logins, All transactions, All updates ----
def _reports_allowed(request):
    if not request.user.is_authenticated or not request.user.is_stage1():
        messages.error(request, 'Only Stage 1 can access reports.')
        return False
    return True


@login_required
def reports_logins(request):
    if not _reports_allowed(request):
        return redirect('inventory:dashboard')
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    qs = LoginHistory.objects.select_related('user').all().order_by('-logged_in_at')
    if from_date:
        qs = qs.filter(logged_in_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(logged_in_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(logged_in_at__month=int(month))
        except ValueError:
            pass
    return render(request, 'inventory/reports_logins.html', {
        'logins': qs[:1000],
        'from_date': from_date,
        'to_date': to_date,
        'search_month': month,
    })


@login_required
def reports_logins_pdf(request):
    if not _reports_allowed(request):
        return HttpResponse('Forbidden', status=403)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from io import BytesIO
    except ImportError:
        return HttpResponse('PDF export requires reportlab.', status=501)
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    qs = LoginHistory.objects.select_related('user').all().order_by('-logged_in_at')
    if from_date:
        qs = qs.filter(logged_in_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(logged_in_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(logged_in_at__month=int(month))
        except ValueError:
            pass
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph('All Logins', styles['Title']), Spacer(1, 12)]
    data = [['When', 'Username', 'Full Name', 'Stage', 'System IP', 'Hostname', 'Type']]
    for r in qs[:1000]:
        u = r.user
        connection_type = 'LAN' if r.is_lan else 'External'
        data.append([
            r.logged_in_at.strftime('%Y-%m-%d %H:%M'),
            u.username,
            u.full_name or '-',
            u.stage,
            r.ip_address or '-',
            r.hostname or 'Unknown',
            connection_type,
        ])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.grey), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke), ('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    return HttpResponse(buf.read(), content_type='application/pdf', headers={'Content-Disposition': 'attachment; filename="all_logins.pdf"'})


@login_required
def reports_logins_excel(request):
    if not _reports_allowed(request):
        return HttpResponse('Forbidden', status=403)
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        from io import BytesIO
    except ImportError:
        return HttpResponse('Excel export requires openpyxl. Install with: pip install openpyxl', status=501)
    
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    qs = LoginHistory.objects.select_related('user').all().order_by('-logged_in_at')
    if from_date:
        qs = qs.filter(logged_in_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(logged_in_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(logged_in_at__month=int(month))
        except ValueError:
            pass
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "All Logins"
    
    headers = ['When', 'Username', 'Full Name', 'Stage', 'System IP', 'Hostname', 'Type']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                           top=Side(style='thin'), bottom=Side(style='thin'))
    
    for row, r in enumerate(qs[:1000], 2):
        u = r.user
        connection_type = 'LAN' if r.is_lan else 'External'
        data = [
            r.logged_in_at.strftime('%Y-%m-%d %H:%M'),
            u.username,
            u.full_name or '-',
            u.stage,
            r.ip_address or '-',
            r.hostname or 'Unknown',
            connection_type,
        ]
        for col, value in enumerate(data, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(horizontal="left", vertical="top")
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                               top=Side(style='thin'), bottom=Side(style='thin'))
    
    column_widths = [18, 15, 20, 8, 15, 20, 10]
    for col, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="all_logins.xlsx"'
    return response


@login_required
def reports_transactions(request):
    if not _reports_allowed(request):
        return redirect('inventory:dashboard')
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    
    # Use the same query as item_requests_history for consistency
    qs = IssueRequest.objects.select_related('product', 'requested_by', 'approved_by', 'rejected_by', 'issued_by', 'confirmed_by').order_by('-created_at')
    
    if from_date:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(created_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(created_at__month=int(month))
        except ValueError:
            pass
    
    return render(request, 'inventory/reports_transactions.html', {
        'confirmed_requests': qs[:500],  # Use same variable name as item_requests_history
        'from_date': from_date,
        'to_date': to_date,
        'search_month': month,
    })


@login_required
def reports_transactions_pdf(request):
    if not _reports_allowed(request):
        return HttpResponse('Forbidden', status=403)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from io import BytesIO
    except ImportError:
        return HttpResponse('PDF export requires reportlab.', status=501)
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    
    # Use the same query as item_requests_history for consistency
    qs = IssueRequest.objects.select_related('product', 'requested_by', 'approved_by', 'rejected_by', 'issued_by', 'confirmed_by').order_by('-created_at')
    
    if from_date:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(created_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(created_at__month=int(month))
        except ValueError:
            pass
    
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph('All Transactions', styles['Title']), Spacer(1, 12)]
    elements.append(Paragraph('Item Requests History', styles['Heading2']))
    data = [['Requested Date', 'Asset ID', 'Item', 'Requested By', 'Dept|Section', 'Mobile', 'Quantity', 'Status', 'Approved By', 'Issued By', 'Confirmed By']]
    for r in qs[:200]:
        data.append([
            r.created_at.strftime('%Y-%m-%d %H:%M'), 
            r.product.asset_id, 
            r.product.item_name, 
            r.requested_by.username,
            f"{r.get_requested_by_department_display()|default:'-'}|{r.get_requested_by_section_display()|default:'-'}",
            r.requested_by_mobile or '-',
            r.approved_quantity or r.quantity,
            r.get_status_display(),
            r.approved_by.username if r.approved_by else '-',
            r.issued_by.username if r.issued_by else '-',
            r.confirmed_by.username if r.confirmed_by else '-'
        ])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.grey), ('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    return HttpResponse(buf.read(), content_type='application/pdf', headers={'Content-Disposition': 'attachment; filename="all_transactions.pdf"'})


@login_required
def reports_transactions_excel(request):
    if not _reports_allowed(request):
        return HttpResponse('Forbidden', status=403)
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        from io import BytesIO
    except ImportError:
        return HttpResponse('Excel export requires openpyxl. Install with: pip install openpyxl', status=501)
    
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    
    qs = IssueRequest.objects.select_related('product', 'requested_by', 'approved_by', 'rejected_by', 'issued_by', 'confirmed_by').order_by('-created_at')
    
    if from_date:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(created_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(created_at__month=int(month))
        except ValueError:
            pass
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "All Transactions"
    
    headers = ['Requested Date', 'Asset ID', 'Item', 'Requested By', 'Dept|Section', 'Mobile', 'Quantity', 'Status', 'Approved By', 'Issued By', 'Confirmed By']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                           top=Side(style='thin'), bottom=Side(style='thin'))
    
    for row, r in enumerate(qs[:500], 2):
        data = [
            r.created_at.strftime('%Y-%m-%d %H:%M'),
            r.product.asset_id,
            r.product.item_name,
            r.requested_by.username if r.requested_by else '-',
            f"{r.get_requested_by_department_display() or '-'}|{r.get_requested_by_section_display() or '-'}",
            r.requested_by_mobile or '-',
            r.approved_quantity or r.quantity,
            r.get_status_display(),
            r.approved_by.username if r.approved_by else '-',
            r.issued_by.username if r.issued_by else '-',
            r.confirmed_by.username if r.confirmed_by else '-',
        ]
        for col, value in enumerate(data, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                               top=Side(style='thin'), bottom=Side(style='thin'))
    
    column_widths = [18, 12, 25, 15, 15, 12, 10, 12, 15, 15, 15]
    for col, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="all_transactions.xlsx"'
    return response


@login_required
def reports_updates(request):
    if not _reports_allowed(request):
        return redirect('inventory:dashboard')
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    
    # Use UploadHistory to show each upload as a separate row
    qs = UploadHistory.objects.select_related('product', 'uploaded_by').order_by('-uploaded_at')
    
    if from_date:
        qs = qs.filter(uploaded_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(uploaded_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(uploaded_at__month=int(month))
        except ValueError:
            pass
    return render(request, 'inventory/reports_updates.html', {
        'upload_history': qs[:500],
        'from_date': from_date,
        'to_date': to_date,
        'search_month': month,
    })


@login_required
def reports_updates_pdf(request):
    if not _reports_allowed(request):
        return HttpResponse('Forbidden', status=403)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from io import BytesIO
    except ImportError:
        return HttpResponse('PDF export requires reportlab.', status=501)
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    
    # Use UploadHistory to show each upload as a separate row
    qs = UploadHistory.objects.select_related('product', 'uploaded_by').order_by('-uploaded_at')
    
    if from_date:
        qs = qs.filter(uploaded_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(uploaded_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(uploaded_at__month=int(month))
        except ValueError:
            pass
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph('All Updates (Items added/updated)', styles['Title']), Spacer(1, 12)]
    data = [['Uploaded At', 'Asset ID', 'Item', 'Category', 'Qty Added', 'Uploaded By']]
    for h in qs[:500]:
        data.append([
            h.uploaded_at.strftime('%Y-%m-%d %H:%M'),
            h.product.asset_id,
            h.product.item_name,
            h.product.get_category_display(),
            str(h.quantity_added),
            h.uploaded_by.username if h.uploaded_by else '-'
        ])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.grey), ('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    return HttpResponse(buf.read(), content_type='application/pdf', headers={'Content-Disposition': 'attachment; filename="all_updates.pdf"'})


@login_required
def reports_updates_excel(request):
    if not _reports_allowed(request):
        return HttpResponse('Forbidden', status=403)
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        from io import BytesIO
    except ImportError:
        return HttpResponse('Excel export requires openpyxl. Install with: pip install openpyxl', status=501)
    
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    
    # Use UploadHistory to show each upload as a separate row
    qs = UploadHistory.objects.select_related('product', 'uploaded_by').order_by('-uploaded_at')
    
    if from_date:
        qs = qs.filter(uploaded_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(uploaded_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(uploaded_at__month=int(month))
        except ValueError:
            pass
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "All Updates"
    
    headers = ['Uploaded At', 'Asset ID', 'Item', 'Category', 'Qty Added', 'Uploaded By']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                           top=Side(style='thin'), bottom=Side(style='thin'))
    
    for row, h in enumerate(qs[:500], 2):
        data = [
            h.uploaded_at.strftime('%Y-%m-%d %H:%M'),
            h.product.asset_id,
            h.product.item_name,
            h.product.get_category_display(),
            h.quantity_added,
            h.uploaded_by.username if h.uploaded_by else '-',
        ]
        for col, value in enumerate(data, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(horizontal="left", vertical="top")
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                               top=Side(style='thin'), bottom=Side(style='thin'))
    
    column_widths = [18, 15, 30, 15, 12, 15]
    for col, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="all_updates.xlsx"'
    return response


@login_required
def reports_deleted_history(request):
    if not request.user.is_stage1():
        messages.error(request, 'Only Stage 1 can view deleted history.')
        return redirect('inventory:dashboard')
    
    qs = DeletedHistory.objects.all().select_related('deleted_by').order_by('-deleted_at')
    
    # Search filters
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    search_month = request.GET.get('month', '')
    category = request.GET.get('category', '')
    search_asset = request.GET.get('asset_id', '').strip()
    
    if from_date:
        qs = qs.filter(deleted_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(deleted_at__date__lte=to_date)
    if search_month:
        try:
            qs = qs.filter(deleted_at__month=int(search_month))
        except ValueError:
            pass
    if category:
        qs = qs.filter(category=category)
    if search_asset:
        qs = qs.filter(asset_id__icontains=search_asset)
    
    return render(request, 'inventory/reports_deleted_history.html', {
        'records': qs,
        'from_date': from_date,
        'to_date': to_date,
        'search_month': search_month,
        'selected_category': category,
        'search_asset': search_asset,
        'categories': [{'slug': c[0], 'name': c[1]} for c in CATEGORY_CHOICES],
    })


@login_required
def reports_deleted_history_pdf(request):
    if not request.user.is_stage1():
        return HttpResponse('Forbidden', status=403)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from io import BytesIO
    except ImportError:
        return HttpResponse('PDF export requires reportlab. Install with: pip install reportlab', status=501)

    qs = DeletedHistory.objects.all().select_related('deleted_by').order_by('-deleted_at')
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    search_month = request.GET.get('month', '')
    category = request.GET.get('category', '')
    search_asset = request.GET.get('asset_id', '').strip()
    
    if from_date:
        qs = qs.filter(deleted_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(deleted_at__date__lte=to_date)
    if search_month:
        try:
            qs = qs.filter(deleted_at__month=int(search_month))
        except ValueError:
            pass
    if category:
        qs = qs.filter(category=category)
    if search_asset:
        qs = qs.filter(asset_id__icontains=search_asset)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph('Deleted Items History', styles['Title']), Spacer(1, 12)]
    data = [['Asset ID', 'Item Name', 'Category', 'Qty', 'Deleted By', 'Deleted At', 'Reason']]
    for record in qs[:500]:
        data.append([
            record.asset_id,
            record.item_name,
            record.get_category_display(),
            str(record.quantity_available),
            record.deleted_by.username if record.deleted_by else 'Unknown',
            record.deleted_at.strftime('%Y-%m-%d %H:%M'),
            record.deletion_reason[:50] + '...' if len(record.deletion_reason) > 50 else record.deletion_reason or '-'
        ])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    response = HttpResponse(buf.read(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="deleted_history.pdf"'
    return response


@login_required
def reports_deleted_history_excel(request):
    if not request.user.is_stage1():
        return HttpResponse('Forbidden', status=403)
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        from io import BytesIO
    except ImportError:
        return HttpResponse('Excel export requires openpyxl. Install with: pip install openpyxl', status=501)

    qs = DeletedHistory.objects.all().select_related('deleted_by').order_by('-deleted_at')
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    search_month = request.GET.get('month', '')
    category = request.GET.get('category', '')
    search_asset = request.GET.get('asset_id', '').strip()
    
    if from_date:
        qs = qs.filter(deleted_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(deleted_at__date__lte=to_date)
    if search_month:
        try:
            qs = qs.filter(deleted_at__month=int(search_month))
        except ValueError:
            pass
    if category:
        qs = qs.filter(category=category)
    if search_asset:
        qs = qs.filter(asset_id__icontains=search_asset)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Deleted History"
    
    headers = ['Asset ID', 'Item Name', 'Category', 'Qty', 'Deleted By', 'Deleted At', 'Reason']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                           top=Side(style='thin'), bottom=Side(style='thin'))
    
    for row, record in enumerate(qs[:500], 2):
        data = [
            record.asset_id,
            record.item_name,
            record.get_category_display(),
            record.quantity_available,
            record.deleted_by.username if record.deleted_by else 'Unknown',
            record.deleted_at.strftime('%Y-%m-%d %H:%M'),
            record.deletion_reason or '-',
        ]
        for col, value in enumerate(data, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                               top=Side(style='thin'), bottom=Side(style='thin'))
    
    column_widths = [15, 30, 15, 10, 15, 18, 40]
    for col, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="deleted_history.xlsx"'
    return response


@login_required
def add_user(request):
    if not request.user.can_manage_users():
        messages.error(request, 'Only Stage 1 users can add users.')
        return redirect('inventory:dashboard')
    
    if request.method == 'POST':
        form = AddUserForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                messages.success(request, f'User "{user.username}" created successfully with default password: temp123456')
                return redirect('inventory:profile')
            except Exception as e:
                messages.error(request, f'Error creating user: {str(e)}')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field.title()}: {error}')
    else:
        form = AddUserForm()
    
    return render(request, 'inventory/add_user.html', {'form': form})


@login_required
def available_racks(request):
    """Display available racks with items for Stage 1 and 2 users."""
    if not (request.user.stage == 1 or request.user.stage == 2):
        messages.error(request, 'Only Stage 1 and 2 users can view available racks.')
        return redirect('inventory:dashboard')
    
    # Get search and filter parameters
    category = request.GET.get('category', '').strip()
    search = request.GET.get('search', '').strip()
    
    # Get all racks with filtering
    racks_query = Rack.objects.all()
    if category:
        racks_query = racks_query.filter(category=category)

    racks = racks_query.order_by('category', 'rack_number')
    rack_data = []
    
    for rack in racks:
        # If searching, allow matching by rack/cabin even when there are no items.
        rack_matches_search = True
        if search:
            s = search.lower()
            rack_matches_search = (
                (rack.rack_number or '').lower().find(s) != -1
                or (rack.cabin_name or '').lower().find(s) != -1
            )

        # Get products in this rack with proper annotations and filtering
        products_query = Product.objects.filter(rack=rack).select_related('rack')
        
        # Apply search filter if provided
        if search:
            products_query = products_query.filter(
                Q(asset_id__icontains=search) | 
                Q(item_name__icontains=search)
            )
        
        products = products_query.annotate(
            on_order=Coalesce(
                Sum(
                    Case(
                        When(
                            orders__status__in=[Order.STATUS_PENDING, Order.STATUS_PARTIAL],
                            then=F('orders__quantity_requested') - F('orders__quantity_provided'),
                        ),
                        default=0,
                        output_field=IntegerField(),
                    )
                ),
                0,
            )
        ).annotate(
            total_items=F('quantity_available') + F('on_order')
        )
        
        items = []
        total_value = Decimal('0.00')
        
        for product in products:
            if product.price is not None:
                try:
                    total_value += (Decimal(str(product.price)) * Decimal(int(product.quantity_available)))
                except Exception:
                    pass
            items.append({
                'asset_id': product.asset_id,
                'item_name': product.item_name,
                'quantity_available': product.quantity_available,
                'on_order': product.on_order,
                'total_items': product.total_items,
                'price': product.price,
            })
        
        # Show racks even when empty (especially for newly added racks).
        # When searching, include racks that either have matching items OR match rack/cabin name.
        if (not search) or items or rack_matches_search:
            rack_data.append({
                'rack': rack,
                'items': items,
                'total_items': len(items),
                'total_quantity': sum(item['quantity_available'] for item in items),
                'total_value': total_value,
            })
    
    return render(request, 'inventory/available_racks.html', {
        'rack_data': rack_data,
        'total_racks': len(rack_data),
        'selected_category': category,
        'search': search,
        'categories': [{'slug': c[0], 'name': c[1]} for c in CATEGORY_CHOICES],
    })


@login_required
def view_racks(request):
    """Display all available racks in a simple table format for Stage 1 and 2 users."""
    if not (request.user.stage == 1 or request.user.stage == 2):
        messages.error(request, 'Only Stage 1 and 2 users can view racks.')
        return redirect('inventory:dashboard')
    
    # Get search and filter parameters
    category = request.GET.get('category', '').strip()
    search = request.GET.get('search', '').strip()
    
    # Get all racks with filtering
    racks_query = Rack.objects.all()
    if category:
        racks_query = racks_query.filter(category=category)

    racks = racks_query.order_by('category', 'rack_number')
    rack_summary = []
    
    for rack in racks:
        # Get products in this rack
        products_query = Product.objects.filter(rack=rack)
        
        # Apply search filter if provided
        if search:
            products_query = products_query.filter(
                Q(asset_id__icontains=search) | 
                Q(item_name__icontains=search)
            )
        
        products = products_query.annotate(
            on_order=Coalesce(
                Sum(
                    Case(
                        When(
                            orders__status__in=[Order.STATUS_PENDING, Order.STATUS_PARTIAL],
                            then=F('orders__quantity_requested') - F('orders__quantity_provided'),
                        ),
                        default=0,
                        output_field=IntegerField(),
                    )
                ),
                0,
            )
        )
        
        # Calculate totals
        total_items = products.count()
        total_quantity = products.aggregate(Sum('quantity_available'))['quantity_available__sum'] or 0
        total_value = Decimal('0.00')
        
        for product in products:
            if product.price is not None:
                try:
                    total_value += (Decimal(str(product.price)) * Decimal(int(product.quantity_available)))
                except Exception:
                    pass
        
        # Show rack if it has items or matches search
        if total_items > 0 or (search and (
            (rack.rack_number or '').lower().find(search.lower()) != -1
            or (rack.cabin_name or '').lower().find(search.lower()) != -1
        )):
            rack_summary.append({
                'rack': rack,
                'total_items': total_items,
                'total_quantity': total_quantity,
                'total_value': total_value,
            })
    
    # Calculate totals
        total_items_count = 0
        total_quantity_sum = 0
        total_value_sum = Decimal('0.00')
        
        for rack_info in rack_summary:
            total_items_count += rack_info['total_items']
            total_quantity_sum += rack_info['total_quantity']
            total_value_sum += rack_info['total_value']
    
    return render(request, 'inventory/view_racks.html', {
        'rack_summary': rack_summary,
        'total_racks': len(rack_summary),
        'selected_category': category,
        'search': search,
        'categories': [{'slug': c[0], 'name': c[1]} for c in CATEGORY_CHOICES],
        'total_items_count': total_items_count,
        'total_quantity_sum': total_quantity_sum,
        'total_value_sum': total_value_sum,
    })


@login_required
def rack_detail(request, rack_id):
    """Show detailed items in a specific rack."""
    if not (request.user.stage == 1 or request.user.stage == 2):
        messages.error(request, 'Only Stage 1 and 2 users can view rack details.')
        return redirect('inventory:dashboard')
    
    rack = get_object_or_404(Rack, pk=rack_id)
    
    # Get all products in this rack
    products = Product.objects.filter(rack=rack).annotate(
        on_order=Coalesce(
            Sum(
                Case(
                    When(
                        orders__status__in=[Order.STATUS_PENDING, Order.STATUS_PARTIAL],
                        then=F('orders__quantity_requested') - F('orders__quantity_provided'),
                    ),
                    default=0,
                    output_field=IntegerField(),
                    )
                ),
                0,
            )
    ).order_by('asset_id')
    
    # Calculate total value for the rack
    total_value = Decimal('0.00')
    products_with_values = []
    for product in products:
        product_total_value = Decimal('0.00')
        total_quantity = product.quantity_available + product.on_order
        if product.price is not None:
            try:
                product_total_value = (Decimal(str(product.price)) * Decimal(int(product.quantity_available)))
                total_value += product_total_value
            except Exception:
                pass
        products_with_values.append({
            'product': product,
            'total_value': product_total_value,
            'total_quantity': total_quantity,
        })
    
    return render(request, 'inventory/rack_detail.html', {
        'rack': rack,
        'products_with_values': products_with_values,
        'products': products,
        'total_items': products.count(),
        'total_quantity': products.aggregate(Sum('quantity_available'))['quantity_available__sum'] or 0,
        'total_value': total_value,
    })


@login_required
def toggle_user_status(request, user_id):
    """Toggle user active status (enable/disable)."""
    if not request.user.can_manage_users():
        messages.error(request, 'Only Stage 1 users can manage user status.')
        return redirect('inventory:dashboard')
    
    target = get_object_or_404(User, pk=user_id)
    
    # Prevent toggling superusers or other Stage 1 users
    if target.is_superuser or target.can_manage_users():
        messages.error(request, 'You cannot change the status of this user.')
        return redirect('inventory:manage_users')
    
    # Prevent self-deactivation
    if target == request.user:
        messages.error(request, 'You cannot disable your own account.')
        return redirect('inventory:manage_users')
    
    # Toggle status
    target.is_active = not target.is_active
    target.save()
    
    status_text = "enabled" if target.is_active else "disabled"
    messages.success(request, f'User "{target.username}" {status_text}.')
    return redirect('inventory:manage_users')


@login_required
def manage_users(request):
    """Stage 1: manage users (view & delete)."""
    if not request.user.can_manage_users():
        messages.error(request, 'Only Stage 1 users can manage users.')
        return redirect('inventory:dashboard')

    search = request.GET.get('q', '').strip()
    users = User.objects.exclude(pk=request.user.pk).order_by('username')
    if search:
        users = users.filter(Q(username__icontains=search) | Q(full_name__icontains=search))

    if request.method == 'POST':
        user_id = request.POST.get('user_id', '').strip()
        target = get_object_or_404(User, pk=user_id)
        if target.is_superuser or target.can_manage_users():
            messages.error(request, 'You cannot delete this user.')
            return redirect('inventory:manage_users')
        
        # Check for database relationships
        has_relations = False
        relation_details = []
        
        # Check issue requests made by user
        if target.issue_requests_made.exists():
            has_relations = True
            relation_details.append(f"Issue Requests ({target.issue_requests_made.count()})")
        
        # Check issue requests approved/rejected/issued/confirmed by user
        if target.issue_requests_approved.exists():
            has_relations = True
            relation_details.append(f"Approved Requests ({target.issue_requests_approved.count()})")
        if target.issue_requests_rejected.exists():
            has_relations = True
            relation_details.append(f"Rejected Requests ({target.issue_requests_rejected.count()})")
        if target.issue_requests_issued.exists():
            has_relations = True
            relation_details.append(f"Issued Requests ({target.issue_requests_issued.count()})")
        if target.issue_requests_confirmed.exists():
            has_relations = True
            relation_details.append(f"Confirmed Requests ({target.issue_requests_confirmed.count()})")
        
        # Check issue history
        if target.issues_made.exists():
            has_relations = True
            relation_details.append(f"Issues Made ({target.issues_made.count()})")
        if target.issues_approved.exists():
            has_relations = True
            relation_details.append(f"Issues Approved ({target.issues_approved.count()})")
        if target.issues_confirmed.exists():
            has_relations = True
            relation_details.append(f"Issues Confirmed ({target.issues_confirmed.count()})")
        if target.issues_received.exists():
            has_relations = True
            relation_details.append(f"Issues Received ({target.issues_received.count()})")
        
        # Check upload history
        if target.uploads_made.exists():
            has_relations = True
            relation_details.append(f"Uploads Made ({target.uploads_made.count()})")
        
        # Check orders
        if target.orders_made.exists():
            has_relations = True
            relation_details.append(f"Orders Made ({target.orders_made.count()})")
        
        # Check management upload requests
        if target.management_upload_requests_made.exists():
            has_relations = True
            relation_details.append(f"Management Upload Requests ({target.management_upload_requests_made.count()})")
        
        # Check peripheral applications
        if target.peripheral_applications.exists():
            has_relations = True
            relation_details.append(f"Peripheral Applications ({target.peripheral_applications.count()})")
        
        # Check login history
        if target.login_history.exists():
            has_relations = True
            relation_details.append(f"Login History ({target.login_history.count()})")
        
        # Check deleted items
        if target.items_deleted.exists():
            has_relations = True
            relation_details.append(f"Deleted Items ({target.items_deleted.count()})")
        
        if has_relations:
            details_str = ", ".join(relation_details)
            messages.error(request, f'Cannot delete user "{target.username}". User has existing database records: {details_str}')
            return redirect('inventory:manage_users')
        
        username = target.username
        target.delete()
        messages.success(request, f'User "{username}" deleted.')
        return redirect('inventory:manage_users')

    return render(request, 'inventory/manage_users.html', {
        'users': users,
        'search': search,
    })


