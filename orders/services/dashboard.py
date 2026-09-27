from decimal import Decimal
from django.db.models import Count, Q, Sum
from django.utils import timezone
from orders.models import Ordem


def get_indicators(tenant):
    today = timezone.localdate()
    totals = Ordem.objects.filter(tenant=tenant).aggregate(
        novos=Count('id', filter=Q(status='novo')),
        confirmados=Count('id', filter=Q(status='confirmado')),
        andamento=Count('id', filter=Q(status__in=['confirmado', 'processando', 'pronto', 'enviado'])),
        processando=Count('id', filter=Q(status='processando')),
        prontos=Count('id', filter=Q(status='pronto')),
        enviados=Count('id', filter=Q(status='enviado')),
        concluidos=Count('id', filter=Q(status='concluido', concluido_em__date=today)),
        cancelados=Count('id', filter=Q(status='cancelado')),
        vendas=Sum('valor_total', filter=Q(status='concluido', concluido_em__date=today)),
        frete=Sum('tx_entrega', filter=Q(status='concluido', concluido_em__date=today)),
    )
    totals['faturamento'] = (totals.pop('vendas') or Decimal('0')) + (totals.pop('frete') or Decimal('0'))
    return totals
