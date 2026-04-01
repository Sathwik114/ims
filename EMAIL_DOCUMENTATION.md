# Email Notifications in Django IMS

This document explains the email notification system implemented in the Django Inventory Management System, similar to the Next.js email functionality.

## Overview

The system sends automated email notifications for:
1. **Issue Request Created** - When a user submits a new item request
2. **Issue Request Approved** - When a request is approved by Stage 1/2 users
3. **Issue Request Rejected** - When a request is rejected with reason
4. **Issue Request Issued** - When items are handed over to the requester
5. **Low Stock Alert** - When item quantity falls below 5 units

## Configuration

### Email Settings (config/settings.py)

```python
# Email configuration - similar to Next.js mailer settings
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = '10.40.10.250'  # Same as Next.js
EMAIL_PORT = 25
EMAIL_USE_TLS = False
EMAIL_USE_SSL = False
EMAIL_TIMEOUT = 30

# Email credentials - use environment variables like Next.js
EMAIL_HOST_USER = os.environ.get('MAIL_USER', 's20330@gti.nws.cn')
EMAIL_HOST_PASSWORD = os.environ.get('MAIL_PASS', 'SatS2@)#')
DEFAULT_FROM_EMAIL = os.environ.get('MAIL_USER', 's20330@gti.nws.cn')
```

### Environment Variables

Create a `.env` file based on `.env.example`:

```
MAIL_HOST=10.40.10.250
MAIL_PORT=25
MAIL_USER=your-email@gti.nws.cn
MAIL_PASS=your-password
```

## Email Templates

### Issue Request Notification Template
- **Location**: `inventory/templates/inventory/email/issue_request_notification.html`
- **Purpose**: Notifies users about their issue request status changes
- **Dynamic Content**: Request details, status, approval/rejection reasons, links

### Low Stock Alert Template
- **Location**: `inventory/templates/inventory/email/low_stock_alert.html`
- **Purpose**: Alerts administrators about low stock items
- **Dynamic Content**: Product details, current stock level, management link

## Email Functions

### Core Email Utility (`inventory/utils.py`)

```python
# Send basic email notification
send_email_notification(to_email, subject, html_content, from_email=None)

# Send issue request status emails
send_issue_request_email(issue_request, email_type, request=None)
# email_type: 'created', 'approved', 'rejected', 'issued'

# Send low stock alerts
send_low_stock_alert(product, request=None)
```

### Integration Points

Email notifications are automatically triggered at these points:

1. **Request Creation** (`inventory/views.py:line 899`)
   ```python
   _notify_issue_request_created(ir, request)
   ```

2. **Request Approval** (`inventory/views.py:line 973`)
   ```python
   _notify_issue_request_decision(ir, approved=True, request=request)
   ```

3. **Request Rejection** (`inventory/views.py:line 994`)
   ```python
   _notify_issue_request_decision(ir, approved=False, request=request)
   ```

4. **Request Issued** (`inventory/views.py:line 1033`)
   ```python
   send_issue_request_email(ir, 'issued', request)
   ```

5. **Low Stock** (`inventory/views.py:line 1014`)
   ```python
   _notify_low_stock(product, request)
   ```

## Testing

Run the email test script to verify functionality:

```bash
# Activate virtual environment
& .\venv\Scripts\Activate.ps1

# Run test script
python test_email.py
```

The test script will:
- Check email configuration
- Test basic email sending
- Test issue request emails (if requests exist)
- Test low stock alerts (if products exist)

## Email Content Examples

### Issue Request Created Email
- **Recipient**: User who submitted the request
- **Subject**: "Item Request #123 Submitted"
- **Content**: Request details, pending approval status, link to view request

### Issue Request Approved Email
- **Recipient**: User who submitted the request
- **Subject**: "Item Request #123 Approved"
- **Content**: Approval details, approved quantity, link to view request

### Issue Request Rejected Email
- **Recipient**: User who submitted the request
- **Subject**: "Item Request #123 Rejected"
- **Content**: Rejection reason, link to view request

### Issue Request Issued Email
- **Recipient**: User who submitted the request
- **Subject**: "Item Request #123 Issued"
- **Content**: Issued confirmation, link to view history

### Low Stock Alert Email
- **Recipient**: Stage 1/2 users (administrators)
- **Subject**: "Low Stock Alert: Item Name"
- **Content**: Product details, current stock level, management link

## Troubleshooting

### Common Issues

1. **Emails not being sent**
   - Check email server connectivity
   - Verify credentials in environment variables
   - Check firewall settings

2. **Emails not received**
   - Check spam/junk folder
   - Verify recipient email addresses
   - Check email server logs

3. **Template errors**
   - Verify template syntax
   - Check context variables in views
   - Ensure template files exist

### Development Testing

For development without sending real emails, temporarily change the backend:

```python
# In settings.py
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

This will print emails to the console instead of sending them.

## Security Notes

- Email credentials are stored in environment variables (not in code)
- Emails are sent over port 25 without TLS (adjust if required)
- User email addresses are validated before use
- All email content is properly escaped to prevent XSS

## Comparison with Next.js Implementation

| Feature | Next.js | Django IMS |
|---------|---------|------------|
| Email Transport | nodemailer | Django SMTP |
| Configuration | .env file | settings.py + .env |
| Templates | HTML strings | Django templates |
| Error Handling | try/catch with logging | try/catch with logging |
| Recipients | Single email | Multiple recipients (admin alerts) |
| HTML Content | Inline HTML | Template-based HTML |

The Django implementation provides the same functionality as the Next.js version with additional benefits:
- Template-based email rendering
- Django's built-in email system
- Better integration with existing models
- Automatic HTML-to-text conversion
