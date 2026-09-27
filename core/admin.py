from django.contrib import admin
from django.db.models import Sum

from .models import AITokenUsage


@admin.register(AITokenUsage)
class AITokenUsageAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'model', 'input_tokens', 'output_tokens', 'total_tokens', 'created_at')
    list_filter = ('tenant', 'model', 'created_at')
    search_fields = ('tenant__name', 'tenant__subdomain')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    list_select_related = ('tenant',)
    readonly_fields = ('tenant', 'model', 'input_tokens', 'output_tokens', 'total_tokens', 'created_at')
    change_list_template = 'admin/core/aitokenusage/change_list.html'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        if hasattr(response, 'context_data') and response.context_data and 'cl' in response.context_data:
            response.context_data['usage_totals'] = response.context_data['cl'].queryset.aggregate(
                entrada=Sum('input_tokens', default=0),
                saida=Sum('output_tokens', default=0),
                total=Sum('total_tokens', default=0),
            )
        return response
