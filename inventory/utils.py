"""
Email utility functions for the Inventory Management System.
Similar to the Next.js mailer functionality.
"""
import os
import gzip
import io
from pathlib import Path
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from django.db.models import Q
from django.core.files.base import ContentFile
from PIL import Image


def send_email_notification(to_email, subject, html_content, from_email=None):
    """
    Send email notification similar to Next.js sendMail function.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_content: HTML email content
        from_email: Sender email (optional, uses default if not provided)
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not from_email:
            from_email = f'"IT Support" <{settings.DEFAULT_FROM_EMAIL}>'
        
        # Create plain text version from HTML
        text_content = strip_tags(html_content)
        
        # Send email
        send_mail(
            subject=subject,
            message=text_content,
            from_email=from_email,
            recipient_list=[to_email],
            html_message=html_content,
            fail_silently=False,
        )
        
        print(f"✅ Email sent to {to_email}: {subject}")
        return True
        
    except Exception as error:
        print(f"❌ Email error: {error}")
        return False


def send_issue_request_email(issue_request, email_type, request=None):
    """
    Send email notifications for issue request status changes.
    
    Args:
        issue_request: IssueRequest instance
        email_type: Type of email ('created', 'approved', 'rejected', 'issued', 'confirmed')
        request: HttpRequest object (for generating links)
    """
    try:
        if not issue_request.requested_by:
            print("Skipping issue request email — no linked Django user for requester")
            return False
        # Only send to users with company email addresses (@gti.nws.cn)
        if not issue_request.requested_by.email.endswith('@gti.nws.cn'):
            print(f"Skipping email - user {issue_request.requested_by.email} does not have company email address")
            return False
        
        # Generate the appropriate link based on user stage
        base_url = "http://10.40.20.4:8000"
        
        # Stage 3 users (requesters) go to my-history page
        # Stage 1/2 users (approvers) can go to individual request page
        if issue_request.requested_by.is_stage3():
            link = f"{base_url}/my-history/"
        else:
            link = f"{base_url}/issue-requests/{issue_request.request_id}/"
        
        # Determine recipient and email content based on type
        if email_type == 'created':
            to_email = issue_request.requested_by.email
            subject = f"Item Request #{issue_request.request_id} Submitted"
            template_context = {
                'issue_request': issue_request,
                'link': link,
                'status': 'submitted for approval',
                'message': 'Your request has been submitted and is pending approval.',
                'user_stage': 'stage3' if issue_request.requested_by.is_stage3() else 'admin'
            }
            
        elif email_type == 'approved':
            to_email = issue_request.requested_by.email
            subject = f"Item Request #{issue_request.request_id} Approved"
            template_context = {
                'issue_request': issue_request,
                'link': link,
                'status': 'approved',
                'message': f'Your request has been approved by {issue_request.approved_by.get_full_name() or issue_request.approved_by.username}.',
                'user_stage': 'stage3' if issue_request.requested_by.is_stage3() else 'admin'
            }
            
        elif email_type == 'rejected':
            to_email = issue_request.requested_by.email
            subject = f"Item Request #{issue_request.request_id} Rejected"
            template_context = {
                'issue_request': issue_request,
                'link': link,
                'status': 'rejected',
                'message': f'Your request has been rejected by {issue_request.rejected_by.get_full_name() or issue_request.rejected_by.username}.',
                'rejection_reason': issue_request.rejection_reason,
                'user_stage': 'stage3' if issue_request.requested_by.is_stage3() else 'admin'
            }
            
        elif email_type == 'issued':
            to_email = issue_request.requested_by.email
            subject = f"Item Request #{issue_request.request_id} Issued"
            template_context = {
                'issue_request': issue_request,
                'link': link,
                'status': 'issued',
                'message': f'Your requested items have been issued by {issue_request.issued_by.get_full_name() or issue_request.issued_by.username}.',
                'user_stage': 'stage3' if issue_request.requested_by.is_stage3() else 'admin'
            }
            
        elif email_type == 'confirmed':
            to_email = issue_request.requested_by.email
            subject = f"Item Request #{issue_request.request_id} Confirmed"
            template_context = {
                'issue_request': issue_request,
                'link': link,
                'status': 'confirmed',
                'message': f'You have confirmed receipt of {issue_request.product.item_name}. The request is now complete.',
                'user_stage': 'stage3' if issue_request.requested_by.is_stage3() else 'admin'
            }
        else:
            return False
        
        # Generate HTML content
        html_content = render_to_string('inventory/email/issue_request_notification.html', template_context)
        
        # Send email
        return send_email_notification(to_email, subject, html_content)
        
    except Exception as error:
        print(f"❌ Issue request email error: {error}")
        return False


def send_low_stock_alert(product, request=None):
    """
    Send email alert for low stock items to internal company users only.
    
    Args:
        product: Product instance
        request: HttpRequest object (for generating links)
    """
    try:
        # Get admin users who should receive low stock alerts (internal users only)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Only send to users with company email addresses (@gti.nws.cn)
        admin_users = User.objects.filter(
            (Q(is_superuser=True) | Q(stage__in=[1, 2])) & 
            Q(email__endswith='@gti.nws.cn')
        )
        
        if not admin_users.exists():
            print("No admin users with company email addresses found")
            return False
        
        # Generate link to product
        link = f"http://10.40.20.4:8000/items/"
        
        subject = f"Low Stock Alert: {product.item_name}"
        template_context = {
            'product': product,
            'link': link,
            'message': f'The item {product.item_name} ({product.asset_id}) is running low on stock.'
        }
        
        # Generate HTML content
        html_content = render_to_string('inventory/email/low_stock_alert.html', template_context)
        
        # Send to all admin users with company emails
        success_count = 0
        for admin in admin_users:
            if admin.email and admin.email.endswith('@gti.nws.cn'):
                if send_email_notification(admin.email, subject, html_content):
                    success_count += 1
        
        return success_count > 0
        
    except Exception as error:
        print(f"❌ Low stock alert email error: {error}")
        return False


def compress_image(file_content, filename):
    """
    Compress image files using Pillow.
    
    Args:
        file_content: Image content (bytes)
        filename: Original filename
        
    Returns:
        tuple: (compressed_content, is_compressed, original_size, compressed_size)
    """
    try:
        img = Image.open(io.BytesIO(file_content))
        original_size = len(file_content)
        
        # Determine format
        fmt = img.format if img.format else 'JPEG'
        if fmt not in ['JPEG', 'PNG', 'WEBP']:
            fmt = 'JPEG'
            
        # Optimization: Resize if extremely large (e.g. > 2000px)
        max_dim = 2000
        if max(img.size) > max_dim:
            scale = max_dim / max(img.size)
            new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
            img = img.resize(new_size, Image.LANCZOS)
            
        output = io.BytesIO()
        
        # Save with 90% quality or optimization
        if fmt == 'JPEG':
            img.convert('RGB').save(output, format=fmt, quality=90, optimize=True)
        elif fmt == 'PNG':
            img.save(output, format=fmt, optimize=True)
        else:
            img.save(output, format=fmt, quality=90)
            
        compressed_content = output.getvalue()
        compressed_size = len(compressed_content)
        
        # Ensure we actually saved at least some space (or at least didn't explode)
        if compressed_size < original_size:
            return compressed_content, True, original_size, compressed_size
        return file_content, False, original_size, original_size
        
    except Exception as e:
        print(f"Image compression error: {e}")
        return file_content, False, len(file_content), len(file_content)


def compress_file_content(file_content, filename=None):
    """
    Compress file content based on type (Image via Pillow, others via gzip).
    
    Args:
        file_content: File content (bytes)
        filename: Original filename
    
    Returns:
        tuple: (compressed_content, is_compressed, original_size, compressed_size)
    """
    if not file_content:
        return file_content, False, 0, 0
    
    original_size = len(file_content)
    
    if filename:
        ext = Path(filename).suffix.lower()
        
        # Handle Images specifically
        if ext in {'.jpg', '.jpeg', '.png', '.webp'}:
            return compress_image(file_content, filename)
            
        # Don't compress already zipped or complex formats that don't gzip well
        compressed_extensions = {'.zip', '.rar', '.pdf', '.7z', '.gz', '.bz2', '.xz', '.mp3', '.mp4', '.avi', '.mov'}
        if ext in compressed_extensions:
            return file_content, False, original_size, original_size
    
    # Compress the content using gzip for non-images
    try:
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode='wb', compresslevel=6) as gz_file:
            gz_file.write(file_content)
        
        compressed_content = buffer.getvalue()
        compressed_size = len(compressed_content)
        
        # Target at least 10% reduction
        if compressed_size < original_size * 0.95: 
            return compressed_content, True, original_size, compressed_size
    except Exception:
        pass
        
    return file_content, False, original_size, original_size


def save_compressed_file(upload_file, upload_path, filename_prefix=""):
    """
    Save uploaded file with compression if beneficial.
    
    Args:
        upload_file: Django UploadedFile object
        upload_path: Path where to save the file
        filename_prefix: Optional prefix for the filename
    
    Returns:
        dict: {
            'filename': final filename,
            'original_size': original file size,
            'compressed_size': final file size,
            'is_compressed': whether compression was applied,
            'compression_ratio': percentage saved (if compressed)
        }
    """
    # Read the file content
    file_content = upload_file.read()
    original_filename = upload_file.name
    
    # Compress if beneficial
    compressed_content, is_compressed, original_size, compressed_size = compress_file_content(
        file_content, original_filename
    )
    
    # Generate filename
    if is_compressed:
        # Add .gz extension for compressed files
        name_without_ext = Path(original_filename).stem
        ext = Path(original_filename).suffix
        final_filename = f"{filename_prefix}{name_without_ext}{ext}.gz"
    else:
        final_filename = f"{filename_prefix}{original_filename}"
    
    # Create full path
    full_path = Path(upload_path) / final_filename
    
    # Save the file
    with open(full_path, 'wb') as f:
        f.write(compressed_content)
    
    # Calculate compression ratio
    compression_ratio = 0
    if is_compressed and original_size > 0:
        compression_ratio = round((1 - compressed_size / original_size) * 100, 1)
    
    return {
        'filename': final_filename,
        'original_size': original_size,
        'compressed_size': compressed_size,
        'is_compressed': is_compressed,
        'compression_ratio': compression_ratio
    }


def compress_django_file(uploaded_file):
    """
    Helper to compress a Django FileField content before saving.
    """
    if not uploaded_file:
        return uploaded_file
        
    try:
        # Prevent multiple compressions
        if hasattr(uploaded_file, '_compressed'):
            return uploaded_file
            
        file_content = uploaded_file.read()
        compressed_content, is_compressed, _, _ = compress_file_content(file_content, uploaded_file.name)
        
        if is_compressed:
            ext = Path(uploaded_file.name).suffix.lower()
            new_name = uploaded_file.name
            
            # For non-images, we add .gz to indicate gzip compression
            if ext not in {'.jpg', '.jpeg', '.png', '.webp'} and not new_name.endswith('.gz'):
                new_name += '.gz'
                
            new_file = ContentFile(compressed_content)
            new_file.name = new_name
            new_file._compressed = True # Flag to avoid recursion
            return new_file
            
    except Exception as e:
        print(f"Error compressing Django file: {e}")
        
    return uploaded_file


def get_compressed_file_content(file_path):
    """
    Read and decompress file content if it's compressed.
    
    Args:
        file_path: Path to the file
    
    Returns:
        bytes: Decompressed file content
    """
    with open(file_path, 'rb') as f:
        content = f.read()
    
    # Check if file is gzip compressed
    if content.startswith(b'\x1f\x8b'):
        try:
            # Decompress the content
            buffer = io.BytesIO(content)
            with gzip.GzipFile(fileobj=buffer, mode='rb') as gz_file:
                return gz_file.read()
        except Exception:
            # If decompression fails, return original content
            return content
    
    return content
