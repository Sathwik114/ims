# Inventory Management System (IMS)

A Django-based inventory system with three access levels (Stage 1, Stage 2, Stage 3), category-based inventory (Networking, Hardware, Security, Server Parts), and approval workflow for issuing items.

## Features

- **Login**: Username/password; common for all stages.
- **Stage 1**: Full permissions (view, edit, delete, user management). Created via `createsuperuser`; no category asked.
- **Stage 2**: Edit and issue items; cannot create users. Assigned a category by Stage 1.
- **Stage 3**: Read-only access. Assigned a category by Stage 1.
- **Dashboard**: Graphs for inventory by category.
- **Sidebar**: Networking, Hardware, Security, Server Parts (per user access).
- **Category pages**: List items, search by Asset ID or Rack Name.
- **Add**: Add Product (Asset ID, Item Name, Location, Quantity, Price, Rack), Add Racks (Rack Number, rows, columns). Low-stock notification when quantity &lt; 5.
- **Issuing**: Click Asset ID to fill form; enter receiver username (name auto-fetched). Stage 1 approval required; approved issues stored in History.
- **Items**: Upload Items (add quantity), Upload History (search/filter by date/day).
- **Order**: Create order request; update quantity provided; mark Disclosed if needed. Order History with search/filter.
- **History**: Issued items; search by date/day/month; download PDF.
- **Profile**: Username, Settings (change password), Add User (Stage 1 only).

## Setup

1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate   # Windows
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create the first administrator (Stage 1). The system does **not** ask for category; the user is automatically Stage 1:
   ```bash
   python manage.py createsuperuser
   ```

4. Run migrations (if not already applied):
   ```bash
   python manage.py migrate
   ```

5. Start the server:
   ```bash
   python manage.py runserver
   ```

6. Open http://127.0.0.1:8000/ and log in. Use the Django admin at http://127.0.0.1:8000/admin/ to view all users (Stage 1, 2, 3) and other data.

## Creating Stage 2 / Stage 3 users

- Log in as a Stage 1 user.
- Open the profile dropdown (top right) → **Add User**.
- Choose Stage 2 or Stage 3 and assign a category (Networking, Hardware, Security, Server Parts). These users are stored in the database and visible in Django admin.

## Tech stack

- Django 4.2+
- SQLite (default)
- Bootstrap 5, Chart.js (dashboard)
- reportlab (PDF export for History)
