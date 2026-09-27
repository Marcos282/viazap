from django.db import models
from customers.models import User


class Pagamento(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('approved', 'Aprovado'),
        ('rejected', 'Rejeitado'),
        ('cancelled', 'Cancelado'),
        ('refunded', 'Estornado'),
        ('in_process', 'Em análise'),
    ]
    FORMA_PAGAMENTO_CHOICES = [
        ('pix', 'Pix'),
        ('cartao', 'Cartão'),
        ('boleto', 'Boleto'),
    ]
    nr_cobranca = models.CharField(max_length=100, unique=True, help_text="Identificador único da cobrança (ex: ID do gateway de pagamento)")
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='pagamentos')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pagamentos')
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    forma_pagamento = models.CharField(max_length=20, choices=FORMA_PAGAMENTO_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Identificadores do Mercado Pago
    mp_payment_id = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    mp_preference_id = models.CharField(max_length=100, blank=True, null=True)
    external_reference = models.CharField(max_length=100, blank=True, null=True, unique=True)

    # Dados do Pix (quando aplicável)
    pix_qr_code = models.TextField(blank=True, null=True)          # copia-e-cola
    pix_qr_code_base64 = models.TextField(blank=True, null=True)   # imagem do QR

    dias_creditados = models.PositiveIntegerField(default=30)

    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)
    data_aprovacao = models.DateTimeField(blank=True, null=True)

    # Payload bruto do webhook, útil para auditoria/depuração
    resposta_bruta = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ['-data_criacao']

    def __str__(self):
        return f'{self.user} - R$ {self.valor} ({self.status})'