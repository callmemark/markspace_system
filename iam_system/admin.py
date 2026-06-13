from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from .models import Account  # explicit import – adjust path as needed

User = get_user_model()


@admin.register(User)
class AccountAdmin(BaseUserAdmin):
    # Fields to display in the user list
    list_display = (
        'email',
        'display_name',
        'account_type',
        'is_active',
        'is_staff',
        'date_joined',
    )
    list_filter = ('account_type', 'is_active', 'is_staff')

    # Fields for editing an existing user
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {
            'fields': (
                'display_name',
                'account_type',
                'company',
                'job_title',
                'website',
                'description',
                'avatar',
            )
        }),
        ('Permissions', {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions',
            )
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    # Fields for creating a new user via admin
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email',
                'display_name',
                'account_type',
                'company',
                'job_title',
                'website',
                'description',
                'password1',
                'password2',
            ),
        }),
    )

    search_fields = ('email', 'display_name')
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions',)