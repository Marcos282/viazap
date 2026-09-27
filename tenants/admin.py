from django.contrib import admin
from django import forms
from django.db.models import Sum
from django.urls import reverse
from django.utils.html import format_html
from .models import Tenant, TenantSettings, HorarioFuncionamento,Configuracao

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "subdomain", "created_at", "tokens_entrada", "tokens_saida", "tokens_total", "consumo_ia")
    search_fields = ("name", "subdomain")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            total_entrada=Sum('ai_token_usage__input_tokens', default=0),
            total_saida=Sum('ai_token_usage__output_tokens', default=0),
            total_consumo=Sum('ai_token_usage__total_tokens', default=0),
        )

    @admin.display(description='Tokens de entrada', ordering='total_entrada')
    def tokens_entrada(self, obj):
        return obj.total_entrada

    @admin.display(description='Tokens de saída', ordering='total_saida')
    def tokens_saida(self, obj):
        return obj.total_saida

    @admin.display(description='Total de tokens', ordering='total_consumo')
    def tokens_total(self, obj):
        return obj.total_consumo

    @admin.display(description='Consumo de IA')
    def consumo_ia(self, obj):
        url = reverse('admin:core_aitokenusage_changelist')
        return format_html('<a href="{}?tenant__id__exact={}">Ver relatório</a>', url, obj.pk)

@admin.register(TenantSettings)
class TenantSettingsAdmin(admin.ModelAdmin):
    list_display = ("tenant", "theme_color", "support_email", "nome_loja")
    search_fields = ("tenant__name", "support_email", "nome_loja")

    """def has_add_permission(self, request):
        # Bloqueia a adição se já houver qualquer TenantSettings
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)"""

@admin.register(HorarioFuncionamento)
class HorarioFuncionamentoAdmin(admin.ModelAdmin):
    list_display = ("tenant", "get_dia_display", "horario_abre", "horario_fecha", "ativo", "data_especifica")
    list_filter = ("dia_semana", "ativo")
    search_fields = ("tenant__name", "descricao")
    ordering = ("tenant", "dia_semana", "horario_abre")
    
    def get_dia_display(self, obj):
        return obj.get_dia_semana_display()
    get_dia_display.short_description = "Dia da Semana"

@admin.register(Configuracao)
class ConfiguracaoAdmin(admin.ModelAdmin):
    list_display = ("nome_empresa", "email_contato", "telefone", "dominio", "valor_mensalidade")
    search_fields = ("nome_empresa", "email_contato", "dominio")
    fields = (
        "nome_empresa", "email_contato", "telefone", "logo", "dominio", "favicon",
        "valor_mensalidade", "SecrectKey", "client_id_mercadolivre",
        "secret_mercadolivre", "Token_mercadolivre",
        "endereco", "numero", "complemento", "bairro", "cidade", "estado", "cep",
        "cnpj", "inscricao_estadual","nome_razao_social","logo_footer"
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["SecrectKey"].label = "Access Token do Mercado Pago"
        form.base_fields["SecrectKey"].widget = forms.PasswordInput(render_value=True)
        return form
