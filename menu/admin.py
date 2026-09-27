from django.contrib import admin
from .models import Category, Produto

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant")
    list_filter = ("tenant",)
    search_fields = ("name",)

@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ("nome", "category", "price", "tenant")
    list_filter = ("category", "tenant")
    search_fields = ("nome",)


