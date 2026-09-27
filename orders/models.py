# orders/models.py
from django.db import models
from tenants.models import Tenant, TenantSettings
from django.conf import settings
from menu.models import Produto


class Ordem(models.Model):
    class Status(models.TextChoices):
        NOVO = 'novo', 'Novo'
        CONFIRMADO = 'confirmado', 'Confirmado'
        PROCESSANDO = 'processando', 'Processando'
        PRONTO = 'pronto', 'Pronto'
        ENVIADO = 'enviado', 'Enviado'
        CONCLUIDO = 'concluido', 'Concluído'
        CANCELADO = 'cancelado', 'Cancelado'

    class TipoEntrega(models.TextChoices):
        ENTREGA = 'entrega', 'Entrega'
        RETIRADA = 'retirada', 'Retirada'
        A_COMBINAR = 'a_combinar', 'A combinar'

    class PagamentoStatus(models.TextChoices):
        PENDENTE = 'pendente', 'Pendente'
        PAGO = 'pago', 'Pago'
        CANCELADO = 'cancelado', 'Cancelado'
        ESTORNADO = 'estornado', 'Estornado'

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOVO, db_index=True)
    tipo_operacao = models.CharField(max_length=20, choices=TenantSettings.TipoOperacao.choices, default='', editable=False)
    tipo_entrega = models.CharField(max_length=20, choices=TipoEntrega.choices, default=TipoEntrega.A_COMBINAR)
    status_pagamento = models.CharField(max_length=20, choices=PagamentoStatus.choices, default=PagamentoStatus.PENDENTE)
    observacoes = models.TextField(blank=True, default='', max_length=2000, verbose_name='Observações do pedido')
    concluido_em = models.DateTimeField(null=True, blank=True, db_index=True)

    def save(self, *args, **kwargs):
        if self._state.adding and not self.tipo_operacao:
            self.tipo_operacao = (TenantSettings.objects.filter(tenant_id=self.tenant_id)
                                  .values_list('tipo_operacao', flat=True).first() or TenantSettings.TipoOperacao.VAREJO)
        super().save(*args, **kwargs)

    valor_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Valor total da ordem no momento do fechamento")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    
    # Assumindo que o modelo Cliente está em um aplicativo chamado 'customers'
    cliente = models.ForeignKey("customers.Cliente", on_delete=models.SET_NULL, null=True, blank=True)
    dataHora = models.DateTimeField(auto_now_add=True)
    completo = models.BooleanField(default=False)
    transacao_id = models.CharField(max_length=100, null=True)
    formade_pagamento = models.CharField(max_length=100, null=True, blank=True)
    vendedor = models.CharField(max_length=150, null=True, blank=True)
    tx_entrega = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    
    def __str__(self):
        return str(self.id)

    @property
    def get_car_total(self):
        ordemitens = self.ordemitem_set.all()
        return sum([item.get_total for item in ordemitens])

    @property
    def get_car_itens(self):
        ordemitens = self.ordemitem_set.all()
        return sum([item.quantidade for item in ordemitens])
    

class OrdemItem(models.Model):
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Preço do produto no momento do pedido")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    produto = models.ForeignKey(Produto, on_delete=models.SET_NULL, null=True)
    ordem = models.ForeignKey(Ordem, on_delete=models.SET_NULL, null=True)
    quantidade = models.IntegerField(default=0, null=True, blank=True)
    dataHora = models.DateTimeField(auto_now_add=True)
    observacao = models.CharField(max_length=200, null=True, blank=True)
    

    @property
    def get_total(self):
        price = self.preco_unitario
        if price is None:
            price = self.produto.price if self.produto else 0
        return price * (self.quantidade or 0)
    def __str__(self):
        return str(self.id)

class HistoricoStatusPedido(models.Model):
    ordem = models.ForeignKey(Ordem, on_delete=models.PROTECT, related_name='historico_status')
    status_anterior = models.CharField(max_length=20, choices=Ordem.Status.choices)
    status_novo = models.CharField(max_length=20, choices=Ordem.Status.choices)
    alterado_em = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    observacao = models.TextField(blank=True)

    class Meta:
        ordering = ['alterado_em', 'id']
        verbose_name = 'Histórico de status do pedido'
        verbose_name_plural = 'Históricos de status dos pedidos'
