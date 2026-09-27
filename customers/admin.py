from django.contrib import admin
from .models import Cliente, User
from .forms_admin import UserCreationForm, UserChangeForm
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin




@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "telefone", "email", "tenant")
    list_filter = ("tenant",)
    search_fields = ("nome", "email")

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    model = User
    list_display = ("username", "email", "is_staff", "is_active", "tenant", "date_joined")
    search_fields = ("username", "email")
    list_filter = ("tenant", "is_staff", "is_active")
    readonly_fields = ("date_joined",)
    fieldsets = (
        (None, {'fields': ('username', 'email', 'tenant', 'password')}),
        ('Permissões', {'fields': ('is_staff', 'is_active', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'tenant', 'password1', 'password2', 'is_staff', 'is_active'),
        }),
    )


