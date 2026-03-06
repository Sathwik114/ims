import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Sum, Q
from django.views.decorators.http import require_http_methods, require_POST
from django.utils import timezone
from .models import (
    User, Product, Rack, IssueRequest, IssueHistory, UploadHistory, Order, Notification, ManagementUploadRequest,
    CATEGORY_CHOICES,
)
from .forms import (
    LoginForm, AddProductForm, AddRackForm, IssueRequestForm, UploadQuantityForm,
    OrderForm, OrderFulfillForm, AddUserForm, ChangePasswordForm,
)


def _notify_low_stock(product):
    """Create notification for Stage 1 users when product quantity < 5."""
    if product.quantity_available >= 5:
        return
    stage1 = User.objects.filter(is_superuser=True) | User.objects.filter(stage=1)
    msg = f'The {product.item_name} has low stock, request new stock.'
    for u in stage1.distinct():
        Notification.objects.create(
            recipient=u,
            title=f'Low stock: {product.asset_id}',
            message=msg,
            link=f'/category/{product.category}/',
            kind='low_stock',
        )


def _as_decimal(value):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _notify_issue_request_created(ir: IssueRequest):
    """Notify Stage 1 and Stage 2 users that a new request needs approval."""
    approvers = User.objects.filter(stage__in=[1, 2]) | User.objects.filter(is_superuser=True)
    req_name = ir.requested_by.full_name or ir.requested_by.username
    msg = f'{req_name} ({ir.requested_by_mobile or ir.requested_by.mobile_number}) requested {ir.product.item_name} ({ir.product.asset_id}).'
    for u in approvers.distinct():
        Notification.objects.create(
            recipient=u,
            title='Issue request',
            message=msg,
            link='/issue-requests/',
            kind='issue_request',
        )


def _notify_issue_request_decision(ir: IssueRequest, approved: bool):
    """Notify requester that their request was approved/rejected (with reason)."""
    if approved:
        title = 'Issue request approved'
        msg = f'Your request for {ir.product.item_name} ({ir.product.asset_id}) was approved.'
        kind = 'issue_approved'
    else:
        title = 'Issue request rejected'
        reason = ir.rejection_reason.strip() or 'No reason provided.'
        msg = f'Your request for {ir.product.item_name} ({ir.product.asset_id}) was rejected. Reason: {reason}'
        kind = 'issue_rejected'
    Notification.objects.create(
        recipient=ir.requested_by,
        title=title,
        message=msg,
        link='/issue-requests/',
        kind=kind,
    )

def login_view(request):
    if request.user.is_authenticated:
        return redirect('inventory:dashboard')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next') or 'inventory:dashboard'
                return redirect(next_url)
            messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Please correct the errors below.')
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

    show_right = request.user.stage in [1, 2] or request.user.is_superuser
    recent_logins = []
    recent_issued = []
    if show_right:
        recent_logins = User.objects.exclude(last_login__isnull=True).order_by('-last_login')[:5]
        recent_issued = IssueHistory.objects.select_related('product', 'receiver', 'issued_by').order_by('-issued_at')[:5]

    return render(request, 'inventory/dashboard.html', {
        'overall_pie_json': json.dumps(overall),
        'per_category_json': json.dumps(per_category),
        'show_right_panel': show_right,
        'recent_logins': recent_logins,
        'recent_issued': recent_issued,
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
    products = qs.order_by('asset_id')
    category_name = dict(CATEGORY_CHOICES).get(category, category)
    return render(request, 'inventory/category_detail.html', {
        'category': category,
        'category_name': category_name,
        'products': products,
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
    products = qs.select_related('rack').order_by('category', 'asset_id')[:500]
    return render(request, 'inventory/view_items.html', {
        'products': products,
        'selected_category': category,
        'q': q,
        'categories': [{'slug': c[0], 'name': c[1]} for c in CATEGORY_CHOICES],
    })


@login_required
def view_items_pdf(request):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from io import BytesIO
    except ImportError:
        return HttpResponse('PDF export requires reportlab. Install with: pip install reportlab', status=501)

    category = request.GET.get('category', '').strip()
    q = request.GET.get('q', '').strip()
    qs = Product.objects.select_related('rack').all().order_by('category', 'asset_id')
    if category:
        qs = qs.filter(category=category)
    if q:
        qs = qs.filter(Q(asset_id__icontains=q) | Q(item_code__icontains=q) | Q(item_name__icontains=q))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    title = 'Category Items'
    if category:
        title += f' - {dict(CATEGORY_CHOICES).get(category, category)}'
    elements.append(Paragraph(title, styles['Title']))
    elements.append(Spacer(1, 12))
    data = [['Category', 'Asset ID', 'Item Code', 'Item', 'Location', 'Qty', 'Price']]
    for p in qs[:500]:
        data.append([
            p.get_category_display(),
            p.asset_id,
            p.item_code or '-',
            p.item_name,
            p.computed_location or p.location or '-',
            str(p.quantity_available),
            str(p.price) if p.price is not None else '-',
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
    response['Content-Disposition'] = 'attachment; filename=\"category_items.pdf\"'
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
            return redirect('inventory:category_detail', category=product.category)
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


# ---- Issuing ----
@login_required
def issuing_items(request, category):
    # Legacy route: redirect to the unified Issue Requests page
    return redirect(f"/issue-requests/?category={category}")


@login_required
def get_product_details(request, category, asset_id):
    product = get_object_or_404(Product, category=category, asset_id=asset_id)
    return JsonResponse({
        'asset_id': product.asset_id,
        'item_code': product.item_code,
        'item_name': product.item_name,
        'location': product.computed_location,
        'quantity_available': product.quantity_available,
        'price': str(product.price) if product.price else '',
    })


@login_required
def get_user_by_username(request):
    username = request.GET.get('username', '').strip()
    if not username:
        return JsonResponse({'full_name': '', 'mobile_number': ''})
    try:
        user = User.objects.get(username=username)
        name = user.full_name or user.get_full_name() or user.username
        return JsonResponse({'full_name': name, 'mobile_number': user.mobile_number or ''})
    except User.DoesNotExist:
        return JsonResponse({'full_name': '', 'mobile_number': ''})


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
def issue_requests(request):
    """Unified page:
    - Stage 3: can request items and see "My requests".
    - Stage 1/2: can approve / reject requests and see pending + approved lists (no request form).
    """
    category = request.GET.get('category', '').strip() or 'networking'
    products = Product.objects.filter(category=category).order_by('asset_id')

    # Stage 3 creates requests only
    if request.user.is_stage3() and request.method == 'POST' and request.POST.get('action') == 'request':
        form = IssueRequestForm(request.POST)
        asset_id = request.POST.get('asset_id', '').strip()
        if not asset_id or not form.is_valid():
            messages.error(request, 'Invalid request.')
            return redirect(f"/issue-requests/?category={category}")
        product = get_object_or_404(Product, category=category, asset_id=asset_id)
        qty = form.cleaned_data['quantity']
        if product.quantity_available < qty:
            messages.error(request, 'Insufficient quantity.')
            return redirect(f"/issue-requests/?category={category}")
        ir = IssueRequest.objects.create(
            product=product,
            requested_by=request.user,
            requested_by_full_name=request.user.full_name or request.user.get_full_name() or request.user.username,
            requested_by_mobile=request.user.mobile_number or '',
            quantity=qty,
            status=IssueRequest.STATUS_PENDING,
        )
        _notify_issue_request_created(ir)
        messages.success(request, 'Request submitted. Waiting for approval.')
        return redirect(f"/issue-requests/?category={category}")

    # Lists for the UI
    pending = IssueRequest.objects.filter(status=IssueRequest.STATUS_PENDING).select_related('product', 'requested_by').order_by('-created_at')[:200]
    approved_not_issued = IssueRequest.objects.filter(status=IssueRequest.STATUS_APPROVED).select_related('product', 'requested_by').order_by('-approved_at')[:200]
    my_requests = IssueRequest.objects.filter(requested_by=request.user).select_related('product').order_by('-created_at')[:100]

    return render(request, 'inventory/issue_requests.html', {
        'category': category,
        'category_name': dict(CATEGORY_CHOICES).get(category, category),
        'products': products,
        'form': IssueRequestForm(),
        'pending_requests': pending,
        'approved_requests': approved_not_issued,
        'my_requests': my_requests,
    })


@login_required
@require_POST
def issue_request_approve(request, pk):
    if not request.user.can_approve_issue_requests():
        messages.error(request, 'Only Stage 1/2 can approve requests.')
        return redirect('inventory:issue_requests')
    ir = get_object_or_404(IssueRequest, pk=pk, status=IssueRequest.STATUS_PENDING)
    if ir.product.quantity_available < ir.quantity:
        messages.error(request, 'Insufficient stock. Reject with reason instead.')
        return redirect('inventory:issue_requests')
    # Approve only (no stock change yet); item is marked "issue completed" when handover is done
    ir.status = IssueRequest.STATUS_APPROVED
    ir.approved_by = request.user
    ir.approved_at = timezone.now()
    ir.rejection_reason = ''
    ir.rejected_by = None
    ir.rejected_at = None
    ir.save()
    _notify_issue_request_decision(ir, approved=True)
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
    ir.rejection_reason = reason
    ir.save()
    _notify_issue_request_decision(ir, approved=False)
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
    if ir.product.quantity_available < ir.quantity:
        messages.error(request, 'Insufficient stock.')
        return redirect('inventory:issue_requests')
    product = ir.product
    product.quantity_available -= ir.quantity
    product.save()
    _notify_low_stock(product)
    unit_price = _as_decimal(product.price)
    total_cost = unit_price * Decimal(ir.quantity) if unit_price is not None else None
    IssueHistory.objects.create(
        product=product,
        issued_by=request.user,
        approved_by=ir.approved_by,
        receiver=ir.requested_by,
        receiver_full_name=ir.requested_by_full_name,
        receiver_mobile=ir.requested_by_mobile,
        quantity=ir.quantity,
        unit_price=unit_price,
        total_cost=total_cost,
    )
    ir.status = IssueRequest.STATUS_ISSUED
    ir.issued_by = request.user
    ir.issued_at = timezone.now()
    ir.save()
    Notification.objects.create(
        recipient=ir.requested_by,
        title='Issue completed',
        message=f'{product.item_name} ({product.asset_id}) was handed over.',
        link='/my-history/',
        kind='issue_issued',
    )
    messages.success(request, 'Marked as issued (issue completed).')
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
def order_history_pdf(request, category):
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

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph(f'Order History - {dict(CATEGORY_CHOICES).get(category, category)}', styles['Title']))
    elements.append(Spacer(1, 12))
    data = [['Date', 'Asset ID', 'Item', 'Req', 'Prov', 'Unit price', 'Total req', 'Total prov', 'Status']]
    for o in qs[:500]:
        data.append([
            o.created_at.strftime('%Y-%m-%d %H:%M'),
            o.product.asset_id,
            o.product.item_name,
            str(o.quantity_requested),
            str(o.quantity_provided),
            str(o.unit_price) if o.unit_price is not None else '-',
            str(o.total_cost_requested) if o.total_cost_requested is not None else '-',
            str(o.total_cost_provided) if o.total_cost_provided is not None else '-',
            o.status,
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
    response['Content-Disposition'] = f'attachment; filename=\"order_history_{category}.pdf\"'
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
        'from_date': from_date,
        'to_date': to_date,
        'search_date': search_date,
        'search_day': search_day,
        'search_month': search_month,
    })


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


# ---- Notifications ----
@login_required
def notifications_center(request):
    qs = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:200]
    return render(request, 'inventory/notifications.html', {'notifications': qs})


@login_required
@require_POST
def notification_mark_read(request, pk):
    Notification.objects.filter(pk=pk, recipient=request.user).update(read=True)
    return redirect('inventory:notifications')


@login_required
@require_POST
def notification_mark_all_read(request):
    Notification.objects.filter(recipient=request.user, read=False).update(read=True)
    return redirect('inventory:notifications')


@login_required
def my_history(request):
    """Stage 3: show my requests and issued items history."""
    my_requests = IssueRequest.objects.filter(requested_by=request.user).select_related('product').order_by('-created_at')[:200]
    my_issued = IssueHistory.objects.filter(receiver=request.user).select_related('product', 'issued_by', 'approved_by').order_by('-issued_at')[:200]
    return render(request, 'inventory/my_history.html', {'my_requests': my_requests, 'my_issued': my_issued})


@login_required
def item_requests_history(request):
    """Item request history (approved/rejected/issue completed) for Stage 1/2."""
    if not request.user.can_approve_issue_requests():
        messages.error(request, 'Permission denied.')
        return redirect('inventory:dashboard')
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
    return render(request, 'inventory/item_requests_history.html', {
        'records': qs[:500],
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

# ---- Upload Requests to Management ----
@login_required
def management_upload_requests(request):
    """
    Internal upload requests (requesting stock from management).
    - Any stage can create a request.
    - Stage 1/2 can fulfill (add stock to DB) or mark disclosed.
    """
    category = request.GET.get('category', '').strip()
    # Upload Requests are only for Stage 1/2
    if request.user.stage == 3 and not request.user.is_superuser:
        messages.error(request, 'Upload Requests are only available for Stage 1 and Stage 2.')
        return redirect('inventory:dashboard')

    qs = ManagementUploadRequest.objects.select_related('product', 'requested_by').order_by('-created_at')
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


@login_required
@require_POST
def management_upload_request_fulfill(request, pk):
    if not (request.user.stage in [1, 2] or request.user.is_superuser):
        messages.error(request, 'Only Stage 1/2 can fulfill.')
        return redirect('inventory:management_upload_requests')
    req = get_object_or_404(ManagementUploadRequest, pk=pk, status=ManagementUploadRequest.STATUS_PENDING)
    qty = request.POST.get('quantity_received', '').strip()
    if not qty.isdigit() or int(qty) < 0:
        messages.error(request, 'Enter a valid received quantity.')
        return redirect('inventory:management_upload_requests')
    qty = int(qty)
    if qty <= 0:
        messages.error(request, 'Received quantity must be greater than 0. Use Disclose if nothing received.')
        return redirect('inventory:management_upload_requests')

    # Add only received quantity to DB; keep remaining pending if partial
    req.quantity_received += qty
    req.product.quantity_available += qty
    req.product.save()
    unit_price = _as_decimal(req.product.price)
    total_cost = unit_price * Decimal(qty) if unit_price is not None else None
    UploadHistory.objects.create(
        product=req.product,
        uploaded_by=request.user,
        quantity_added=qty,
        unit_price=unit_price,
        total_cost=total_cost,
    )

    if req.quantity_received >= req.quantity_requested:
        req.status = ManagementUploadRequest.STATUS_COMPLETED
    else:
        req.status = ManagementUploadRequest.STATUS_PENDING
    req.save()
    messages.success(request, 'Request updated.')
    return redirect('inventory:management_upload_requests')


@login_required
@require_POST
def management_upload_request_disclose(request, pk):
    if not (request.user.stage in [1, 2] or request.user.is_superuser):
        messages.error(request, 'Only Stage 1/2 can disclose.')
        return redirect('inventory:management_upload_requests')
    req = get_object_or_404(ManagementUploadRequest, pk=pk, status=ManagementUploadRequest.STATUS_PENDING)
    req.status = ManagementUploadRequest.STATUS_DISCLOSED
    req.save()
    messages.success(request, 'Marked as Disclosed.')
    return redirect('inventory:management_upload_requests')


@login_required
def management_upload_requests_pdf(request):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from io import BytesIO
    except ImportError:
        return HttpResponse('PDF export requires reportlab. Install with: pip install reportlab', status=501)
    category = request.GET.get('category', '').strip()
    if request.user.stage == 3 and not request.user.is_superuser:
        return HttpResponse('Forbidden', status=403)
    qs = ManagementUploadRequest.objects.select_related('product', 'requested_by').order_by('-created_at')
    if category:
        qs = qs.filter(product__category=category)
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    title = 'Upload Requests (Management)'
    if category:
        title += f' - {dict(CATEGORY_CHOICES).get(category, category)}'
    elements.append(Paragraph(title, styles['Title']))
    elements.append(Spacer(1, 12))
    data = [['Date', 'Request ID', 'Asset ID', 'Item', 'Requested', 'Received', 'Remaining', 'Status', 'By']]
    for r in qs[:500]:
        remaining = 0
        try:
            remaining = max(0, int(r.quantity_requested) - int(r.quantity_received))
        except Exception:
            remaining = 0
        data.append([
            r.created_at.strftime('%Y-%m-%d %H:%M'),
            str(r.request_id or ''),
            r.product.asset_id,
            r.product.item_name,
            str(r.quantity_requested),
            str(r.quantity_received),
            str(remaining),
            r.status,
            r.requested_by.username if r.requested_by else '-',
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
    response['Content-Disposition'] = 'attachment; filename=\"upload_requests_management.pdf\"'
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
    qs = User.objects.all().order_by('-last_login')
    if from_date:
        qs = qs.filter(last_login__date__gte=from_date)
    if to_date:
        qs = qs.filter(last_login__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(last_login__month=int(month))
        except ValueError:
            pass
    return render(request, 'inventory/reports_logins.html', {
        'users': qs[:500],
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
    qs = User.objects.all().order_by('-last_login')
    if from_date:
        qs = qs.filter(last_login__date__gte=from_date)
    if to_date:
        qs = qs.filter(last_login__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(last_login__month=int(month))
        except ValueError:
            pass
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph('All Logins', styles['Title']), Spacer(1, 12)]
    data = [['Username', 'Full name', 'Stage', 'Last login']]
    for u in qs[:500]:
        data.append([u.username, u.full_name or '-', u.stage, u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else '-'])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.grey), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke), ('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    return HttpResponse(buf.read(), content_type='application/pdf', headers={'Content-Disposition': 'attachment; filename="all_logins.pdf"'})


@login_required
def reports_transactions(request):
    if not _reports_allowed(request):
        return redirect('inventory:dashboard')
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    # Combine issue history, upload history, orders as "transactions"
    issues = IssueHistory.objects.select_related('product', 'receiver', 'issued_by').order_by('-issued_at')
    uploads = UploadHistory.objects.select_related('product', 'uploaded_by').order_by('-uploaded_at')
    if from_date:
        issues = issues.filter(issued_at__date__gte=from_date)
        uploads = uploads.filter(uploaded_at__date__gte=from_date)
    if to_date:
        issues = issues.filter(issued_at__date__lte=to_date)
        uploads = uploads.filter(uploaded_at__date__lte=to_date)
    if month:
        try:
            m = int(month)
            issues = issues.filter(issued_at__month=m)
            uploads = uploads.filter(uploaded_at__month=m)
        except ValueError:
            pass
    return render(request, 'inventory/reports_transactions.html', {
        'issues': issues[:300],
        'uploads': uploads[:300],
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
    issues = IssueHistory.objects.select_related('product').order_by('-issued_at')
    uploads = UploadHistory.objects.select_related('product').order_by('-uploaded_at')
    if from_date:
        issues = issues.filter(issued_at__date__gte=from_date)
        uploads = uploads.filter(uploaded_at__date__gte=from_date)
    if to_date:
        issues = issues.filter(issued_at__date__lte=to_date)
        uploads = uploads.filter(uploaded_at__date__lte=to_date)
    if month:
        try:
            m = int(month)
            issues = issues.filter(issued_at__month=m)
            uploads = uploads.filter(uploaded_at__month=m)
        except ValueError:
            pass
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph('All Transactions', styles['Title']), Spacer(1, 12)]
    elements.append(Paragraph('Issues', styles['Heading2']))
    data = [['Date', 'Asset ID', 'Item', 'Qty', 'Receiver']]
    for r in issues[:200]:
        data.append([r.issued_at.strftime('%Y-%m-%d %H:%M'), r.product.asset_id, r.product.item_name, str(r.quantity), r.receiver.username if r.receiver else '-'])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.grey), ('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
    elements.append(t)
    elements.append(Spacer(1, 12))
    elements.append(Paragraph('Uploads', styles['Heading2']))
    data2 = [['Date', 'Asset ID', 'Item', 'Qty added', 'By']]
    for r in uploads[:200]:
        data2.append([r.uploaded_at.strftime('%Y-%m-%d %H:%M'), r.product.asset_id, r.product.item_name, str(r.quantity_added), r.uploaded_by.username if r.uploaded_by else '-'])
    t2 = Table(data2, repeatRows=1)
    t2.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.grey), ('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
    elements.append(t2)
    doc.build(elements)
    buf.seek(0)
    return HttpResponse(buf.read(), content_type='application/pdf', headers={'Content-Disposition': 'attachment; filename="all_transactions.pdf"'})


@login_required
def reports_updates(request):
    if not _reports_allowed(request):
        return redirect('inventory:dashboard')
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    month = request.GET.get('month', '')
    qs = Product.objects.all().order_by('-updated_at')
    if from_date:
        qs = qs.filter(updated_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(updated_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(updated_at__month=int(month))
        except ValueError:
            pass
    return render(request, 'inventory/reports_updates.html', {
        'products': qs[:500],
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
    qs = Product.objects.all().order_by('-updated_at')
    if from_date:
        qs = qs.filter(updated_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(updated_at__date__lte=to_date)
    if month:
        try:
            qs = qs.filter(updated_at__month=int(month))
        except ValueError:
            pass
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph('All Updates (Items added/updated)', styles['Title']), Spacer(1, 12)]
    data = [['Asset ID', 'Item', 'Category', 'Qty', 'Created', 'Updated']]
    for p in qs[:500]:
        data.append([p.asset_id, p.item_name, p.get_category_display(), str(p.quantity_available), p.created_at.strftime('%Y-%m-%d'), p.updated_at.strftime('%Y-%m-%d %H:%M')])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.grey), ('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    return HttpResponse(buf.read(), content_type='application/pdf', headers={'Content-Disposition': 'attachment; filename="all_updates.pdf"'})


@login_required
def change_password(request):
    if request.method == 'POST':
        form = ChangePasswordForm(request.user, request.POST)
        if form.is_valid():
            request.user.set_password(form.cleaned_data['new_password1'])
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Password changed. Use the new password for future logins.')
            return redirect('inventory:profile')
    else:
        form = ChangePasswordForm(request.user)
    return render(request, 'inventory/change_password.html', {'form': form})


@login_required
def add_user(request):
    if not request.user.can_manage_users():
        messages.error(request, 'Only Stage 1 users can add users.')
        return redirect('inventory:dashboard')
    if request.method == 'POST':
        form = AddUserForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'User created successfully.')
            return redirect('inventory:profile')
    else:
        form = AddUserForm()
    return render(request, 'inventory/add_user.html', {'form': form})


