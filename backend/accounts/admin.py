from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth import get_user_model

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "cnpj", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome", "cnpj")


User = get_user_model()


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Perfil", {"fields": ("role", "cliente", "funcao")}),
    )
    list_display = DjangoUserAdmin.list_display + ("role", "cliente", "funcao")
    list_filter = DjangoUserAdmin.list_filter + ("role", "cliente", "funcao")
