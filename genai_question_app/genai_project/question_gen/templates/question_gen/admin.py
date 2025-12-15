from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, InterviewRequest, ChatMessage

class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'user_type', 'package', 'company', 'date_joined', 'is_active')
    list_filter = ('user_type', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'package', 'company')
    ordering = ('-date_joined',)

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email')}),
        ('User Type', {'fields': ('user_type',)}),
        ('Interviewer Info', {'fields': ('package', 'company', 'role', 'skills', 'bio', 'profile_image')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'user_type', 'password1', 'password2'),
        }),
    )

@admin.register(InterviewRequest)
class InterviewRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'interviewer', 'requested_date', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('student__username', 'interviewer__username')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'short_message', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('sender__username', 'receiver__username', 'message')

    def short_message(self, obj):
        return obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
    short_message.short_description = 'Message'

admin.site.register(User, UserAdmin)

admin.site.site_header = "InterviewPrep Pro Administration"
admin.site.site_title = "InterviewPrep Pro Admin"
admin.site.index_title = "Welcome to InterviewPrep Pro"