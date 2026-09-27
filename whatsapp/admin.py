from django.contrib import admin

from .models import MensagemProcesso, WhatsAppConfiguracao


@admin.register(WhatsAppConfiguracao)
class WhatsAppConfiguracaoAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'instance_name', 'status', 'numero_whatsapp', 'atualizado_em')
    search_fields = ('tenant__name', 'tenant__subdomain', 'instance_name', 'numero_whatsapp')
    readonly_fields = ('instance_name', 'conectado_em', 'atualizado_em')


@admin.register(MensagemProcesso)
class MensagemProcessoAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'cenario', 'status_pedido', 'ativa', 'atualizado_em')
    list_filter = ('cenario', 'status_pedido', 'ativa')
    search_fields = ('tenant__name', 'mensagem')
