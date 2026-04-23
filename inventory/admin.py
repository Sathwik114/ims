from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Category, Rack, Product,
    IssueRequest, IssueHistory, UploadHistory, Order, ManagementUploadRequest,
    PeripheralApplication, LoginHistory, DeletedHistory, PurchaseModificationHistory,
    UserStageHistory, TemporaryItemHistory, ReturnedItem
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
    list_display = ['rack_number', 'cabin_name', 'rows', 'columns', 'number_of_racks', 'created_at']
    list_filter = ['created_at']


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


@admin.register(PeripheralApplication)
class PeripheralApplicationAdmin(admin.ModelAdmin):
    list_display = ['form_id', 'equipment_name', 'created_by', 'created_at']
    list_filter = ['created_at']


@admin.register(LoginHistory)
class LoginHistoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'logged_in_at', 'ip_address', 'hostname', 'is_lan']
    list_filter = ['logged_in_at', 'is_lan']


@admin.register(DeletedHistory)
class DeletedHistoryAdmin(admin.ModelAdmin):
    list_display = ['asset_id', 'item_name', 'deleted_by', 'deleted_at']
    list_filter = ['deleted_at']


@admin.register(PurchaseModificationHistory)
class PurchaseModificationHistoryAdmin(admin.ModelAdmin):
    list_display = ['upload_request', 'modification_type', 'previous_quantity', 'new_quantity', 'modified_by', 'modified_at']
    list_filter = ['modified_at', 'modification_type']


@admin.register(UserStageHistory)
class UserStageHistoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'old_stage', 'new_stage', 'changed_by', 'changed_at', 'hostname']
    list_filter = ['changed_at', 'old_stage', 'new_stage']


@admin.register(TemporaryItemHistory)
class TemporaryItemHistoryAdmin(admin.ModelAdmin):
    list_display = ['request_id', 'product', 'username', 'full_name', 'quantity', 'issued_at']
    list_filter = ['issued_at']


@admin.register(ReturnedItem)
class ReturnedItemAdmin(admin.ModelAdmin):
    list_display = ['request_id', 'product', 'username', 'full_name', 'quantity', 'returned_at']
    list_filter = ['returned_at']
