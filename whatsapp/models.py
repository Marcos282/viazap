from django.db import models
import re

from tenants.models import Tenant


class WhatsAppConfiguracao(models.Model):
    class Status(models.TextChoices):
        DESCONECTADO = 'desconectado', 'Não conectado'
        PREPARANDO = 'preparando', 'Preparando conexão'
        AGUARDANDO_QR = 'aguardando_qr', 'Aguardando QR Code'
        CONECTADO = 'conectado', 'Conectado'
        ERRO = 'erro', 'Erro de comunicação'

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='whatsapp_configuracao')
    instance_name = models.CharField(max_length=100, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DESCONECTADO)
    numero_whatsapp = models.CharField(max_length=20, blank=True, default='')
    conectado_em = models.DateTimeField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.instance_name = f'viazap_tenant_{self.tenant_id}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.tenant} — {self.get_status_display()}'

    @property
    def numero_formatado(self):
        numero = re.sub(r'\D', '', self.numero_whatsapp or '')
        if numero.startswith('55') and len(numero) in (12, 13):
            numero = numero[2:]
        if len(numero) == 11:
            return f'({numero[:2]}) {numero[2:7]}-{numero[7:]}'
        if len(numero) == 10:
            return f'({numero[:2]}) {numero[2:6]}-{numero[6:]}'
        return self.numero_whatsapp


class MensagemProcesso(models.Model):
    class Cenario(models.TextChoices):
        DELIVERY = 'delivery', 'Alimentação / Delivery'
        VAREJO = 'varejo', 'Comércio / Venda de produtos'
        PAGAMENTO = 'pagamento', 'Pagamento'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='mensagens_processo_whatsapp')
    cenario = models.CharField(max_length=20, choices=Cenario.choices)
    status_pedido = models.CharField(max_length=20)
    ativa = models.BooleanField(default=True)
    mensagem = models.TextField(max_length=1200)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['cenario', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'cenario', 'status_pedido'],
                name='whatsapp_processo_unico_tenant_cenario_status',
            ),
        ]

    def __str__(self):
        return f'{self.tenant} — {self.get_cenario_display()} — {self.status_pedido}'
