from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Category, Rack, Product,
    IssueRequest, IssueHistory, UploadHistory, Order, ManagementUploadRequest
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'full_name', 'mobile_number', 'stage', 'category', 'is_staff', 'is_superuser']
    list_filter = ['stage', 'category', 'is_staff', 'is_superuser']
    fieldsets = BaseUserAdmin.fieldsets + (
        (None, {'fields': ('stage', 'full_name', 'mobile_number', 'category')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (None, {'fields': ('stage', 'full_name', 'mobile_number', 'category')}),
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']


@admin.register(Rack)
class RackAdmin(admin.ModelAdmin):
    list_display = ['rack_number', 'category', 'cabin_name', 'rows', 'columns', 'number_of_racks', 'created_at']
    list_filter = ['category']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['asset_id', 'item_code', 'item_name', 'category', 'computed_location', 'quantity_available', 'price', 'rack']
    list_filter = ['category']
    search_fields = ['asset_id', 'item_code', 'item_name']


@admin.register(IssueRequest)
class IssueRequestAdmin(admin.ModelAdmin):
    list_display = ['product', 'requested_by', 'requested_by_full_name', 'requested_by_mobile', 'quantity', 'status', 'created_at']
    list_filter = ['status', 'created_at']


@admin.register(IssueHistory)
class IssueHistoryAdmin(admin.ModelAdmin):
    list_display = ['product', 'receiver', 'receiver_full_name', 'receiver_mobile', 'quantity', 'unit_price', 'total_cost', 'issued_by', 'issued_at']
    list_filter = ['issued_at']


@admin.register(UploadHistory)
class UploadHistoryAdmin(admin.ModelAdmin):
    list_display = ['product', 'quantity_added', 'unit_price', 'total_cost', 'uploaded_by', 'uploaded_at']
    list_filter = ['uploaded_at']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['product', 'quantity_requested', 'quantity_provided', 'unit_price', 'total_cost_requested', 'total_cost_provided', 'status', 'requested_by', 'created_at']
    list_filter = ['status', 'created_at']


@admin.register(ManagementUploadRequest)
class ManagementUploadRequestAdmin(admin.ModelAdmin):
    list_display = ['product', 'quantity_requested', 'quantity_received', 'status', 'requested_by', 'created_at']
    list_filter = ['status', 'created_at']
