from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User

UserAdmin.fieldsets += (("Tenant", {"fields": ("tenant", "role")}),)
admin.site.register(User, UserAdmin)
