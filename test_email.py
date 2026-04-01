#!/usr/bin/env python
"""
Test script for email functionality.
Run this script to test if email sending works correctly.
"""
import os
import sys
import django

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core.mail import send_mail
from inventory.utils import send_email_notification, send_issue_request_email, send_low_stock_alert
from inventory.models import IssueRequest, Product, User

def test_basic_email():
    """Test basic email sending functionality."""
    print("Testing basic email sending...")
    
    try:
        subject = "Test Email from Django IMS"
        html_content = """
        <html>
        <body>
            <h2>Test Email</h2>
            <p>This is a test email from the Django Inventory Management System.</p>
            <p>If you receive this, email configuration is working correctly.</p>
        </body>
        </html>
        """
        
        # Send to test email (replace with actual test email)
        test_email = "s20330@gti.nws.cn"  # Replace with your test email
        success = send_email_notification(test_email, subject, html_content)
        
        if success:
            print("✅ Basic email test successful!")
        else:
            print("❌ Basic email test failed!")
            
    except Exception as e:
        print(f"❌ Basic email test error: {e}")

def test_issue_request_email():
    """Test issue request email functionality."""
    print("\nTesting issue request email...")
    
    try:
        # Get a sample issue request (or create one for testing)
        issue_request = IssueRequest.objects.first()
        
        if not issue_request:
            print("❌ No issue requests found in database. Create one first.")
            return False
            
        success = send_issue_request_email(issue_request, 'created')
        
        if success:
            print("✅ Issue request email test successful!")
        else:
            print("❌ Issue request email test failed!")
            
    except Exception as e:
        print(f"❌ Issue request email test error: {e}")

def test_low_stock_email():
    """Test low stock email functionality."""
    print("\nTesting low stock email...")
    
    try:
        # Get a sample product (or create one for testing)
        product = Product.objects.first()
        
        if not product:
            print("❌ No products found in database. Create one first.")
            return False
            
        success = send_low_stock_alert(product)
        
        if success:
            print("✅ Low stock email test successful!")
        else:
            print("❌ Low stock email test failed!")
            
    except Exception as e:
        print(f"❌ Low stock email test error: {e}")

def test_django_send_mail():
    """Test Django's built-in send_mail function directly."""
    print("\nTesting Django send_mail directly...")
    
    try:
        subject = "Direct Django Test Email"
        message = "This is a plain text test message from Django."
        html_message = """
        <html>
        <body>
            <h2>Direct Django Test</h2>
            <p>This is a test email sent using Django's send_mail function.</p>
        </body>
        </html>
        """
        
        from_email = f'"IT Support" <{os.environ.get("MAIL_USER", "s20330@gti.nws.cn")}>'
        recipient_list = ["s20330@gti.nws.cn"]  # Replace with your test email
        
        result = send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=False,
        )
        
        print(f"✅ Django send_mail test successful! Result: {result}")
        
    except Exception as e:
        print(f"❌ Django send_mail test error: {e}")

def check_email_settings():
    """Check email configuration settings."""
    print("\nChecking email configuration...")
    
    from django.conf import settings
    
    print(f"EMAIL_BACKEND: {getattr(settings, 'EMAIL_BACKEND', 'Not set')}")
    print(f"EMAIL_HOST: {getattr(settings, 'EMAIL_HOST', 'Not set')}")
    print(f"EMAIL_PORT: {getattr(settings, 'EMAIL_PORT', 'Not set')}")
    print(f"EMAIL_HOST_USER: {getattr(settings, 'EMAIL_HOST_USER', 'Not set')}")
    print(f"DEFAULT_FROM_EMAIL: {getattr(settings, 'DEFAULT_FROM_EMAIL', 'Not set')}")
    print(f"EMAIL_USE_TLS: {getattr(settings, 'EMAIL_USE_TLS', 'Not set')}")
    print(f"EMAIL_USE_SSL: {getattr(settings, 'EMAIL_USE_SSL', 'Not set')}")

if __name__ == "__main__":
    print("🔧 Django IMS Email Testing Script")
    print("=" * 50)
    
    # Check configuration
    check_email_settings()
    
    # Run tests
    test_django_send_mail()
    test_basic_email()
    test_issue_request_email()
    test_low_stock_email()
    
    print("\n" + "=" * 50)
    print("Email testing completed!")
    print("\nNote: If emails are not being received, check:")
    print("1. Email server settings in settings.py")
    print("2. Network connectivity to email server")
    print("3. Email credentials (MAIL_USER, MAIL_PASS)")
    print("4. Spam/junk folder in email client")
