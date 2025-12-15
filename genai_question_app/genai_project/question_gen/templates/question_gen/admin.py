from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, InterviewRequest, ChatMessage

# Custom admin for your User model
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'user_type', 'package', 'company', 'role', 'is_active', 'date_joined')
    list_filter = ('user_type', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'package', 'company')
    ordering = ('-date_joined',)

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email')}),
        ('User Type & Status', {'fields': ('user_type', 'is_active', 'is_staff', 'is_superuser')}),
        ('Interviewer Profile', {'fields': ('package', 'company', 'role', 'skills', 'bio', 'profile_image')}),
        ('Permissions', {'fields': ('groups', 'user_permissions')}),
        ('Dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'user_type', 'password1', 'password2'),
        }),
    )

# Register your models
admin.site.register(User, UserAdmin)
admin.site.register(InterviewRequest)
admin.site.register(ChatMessage)

# Nice branding
admin.site.site_header = "InterviewPrep Pro Admin"
admin.site.site_title = "InterviewPrep Pro"
admin.site.index_title = "Welcome to InterviewPrep Pro Admin Panel"