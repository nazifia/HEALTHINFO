from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import User


# Stock auth forms key on `username` and wrap it in UsernameField, which calls
# len() on the value — our username is nullable, so editing a user with no
# username crashes. Re-key both forms on `phone` (our USERNAME_FIELD).
class UserChangeFormPhone(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        field_classes = {}


class UserCreationFormPhone(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("phone",)
        field_classes = {}


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    form = UserChangeFormPhone
    add_form = UserCreationFormPhone
    ordering = ("phone",)
    list_display = ("phone", "username", "email", "role", "tenant", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
    search_fields = ("phone", "username", "email")
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Personal info", {"fields": ("username", "first_name", "last_name", "email")}),
        ("Tenant", {"fields": ("tenant", "role")}),
        ("Permissions", {"fields": (
            "is_active", "is_staff", "is_superuser", "groups", "user_permissions",
        )}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("phone", "password1", "password2"),
        }),
    )
