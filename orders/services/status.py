"""Regras compartilhadas pelo painel, AJAX e mensagens."""
import re
from urllib.parse import urlencode
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from orders.models import Ordem, HistoricoStatusPedido

TERMINAIS = {'concluido', 'cancelado'}
COLORS = {'novo': 'warning', 'confirmado': 'primary', 'processando': 'primary',
          'pronto': 'purple', 'enviado': 'info', 'concluido': 'success', 'cancelado': 'danger'}


def get_status_label(ordem, status=None):
    status = status or ordem.status
    delivery = ordem.tipo_operacao == 'delivery'
    retirada = ordem.tipo_entrega == 'retirada'
    labels = dict(Ordem.Status.choices)
    labels['processando'] = 'Em preparação' if delivery else 'Separando pedido'
    labels['pronto'] = ('Pronto para retirada' if retirada else
                       'Pronto' if delivery else 'Pronto para envio' if ordem.tipo_entrega == 'entrega' else 'Pronto — definir entrega/retirada')
    labels['enviado'] = 'Saiu para entrega' if delivery else 'Enviado'
    labels['concluido'] = ('Concluído' if delivery else 'Retirado' if retirada else
                          'Entregue' if ordem.tipo_entrega == 'entrega' else 'Concluído')
    return labels.get(status, status)


def get_next_action(ordem):
    delivery = ordem.tipo_operacao == 'delivery'
    if ordem.status in TERMINAIS:
        return None
    if ordem.status == 'novo':
        return {'status': 'processando' if delivery else 'confirmado',
                'label': 'Aceitar pedido' if delivery else 'Confirmar pedido'}
    if ordem.status == 'confirmado':
        return {'status': 'processando', 'label': 'Iniciar preparação' if delivery else 'Iniciar separação'}
    if ordem.status == 'processando':
        if ordem.tipo_entrega == 'a_combinar':
            return None
        return {'status': 'pronto', 'label': 'Marcar como pronto' if delivery else
                'Pronto para retirada' if ordem.tipo_entrega == 'retirada' else 'Pronto para envio'}
    if ordem.status == 'pronto':
        if ordem.tipo_entrega == 'retirada':
            return {'status': 'concluido', 'label': 'Concluir pedido' if delivery else 'Marcar como retirado'}
        if ordem.tipo_entrega == 'entrega':
            return {'status': 'enviado', 'label': 'Saiu para entrega' if delivery else 'Pedido enviado'}
        return None
    if ordem.status == 'enviado':
        return {'status': 'concluido', 'label': 'Concluir pedido' if delivery else 'Marcar como entregue'}
    return None


def _check_user(usuario, tenant_id):
    if not usuario.is_authenticated or usuario.tenant_id != tenant_id:
        raise PermissionDenied('Acesso negado à loja.')


@transaction.atomic
def change_status(*, ordem_id, tenant_id, novo_status, usuario, expected_status):
    _check_user(usuario, tenant_id)
    ordem = Ordem.objects.select_for_update().get(pk=ordem_id, tenant_id=tenant_id)
    if novo_status not in Ordem.Status.values:
        raise ValidationError('Status inválido.')
    if ordem.status == novo_status:
        return ordem  # Repetição da mesma ação não duplica histórico.
    if ordem.status != expected_status:
        raise ValidationError('O pedido foi atualizado por outra pessoa. Atualize o painel.')
    next_action = get_next_action(ordem)
    valid = (novo_status == 'cancelado' and ordem.status not in TERMINAIS) or (
        next_action and next_action['status'] == novo_status)
    if not valid:
        raise ValidationError('Esta transição não é permitida.')
    anterior = ordem.status
    ordem.status = novo_status
    ordem.completo = novo_status in TERMINAIS
    if novo_status == 'concluido':
        ordem.concluido_em = timezone.now()
    ordem.save(update_fields=['status', 'completo', 'concluido_em'])
    HistoricoStatusPedido.objects.create(ordem=ordem, status_anterior=anterior,
                                        status_novo=novo_status, usuario=usuario)
    # O pedido precisa estar confirmado no banco antes de chamar um serviço externo.
    # A função de envio trata as falhas sem desfazer a mudança de status.
    from whatsapp.services.notifications import send_order_status_message
    transaction.on_commit(
        lambda order_id=ordem.pk: send_order_status_message(order_id),
        robust=True,
    )
    return ordem


@transaction.atomic
def change_delivery(*, ordem_id, tenant_id, tipo_entrega, usuario):
    _check_user(usuario, tenant_id)
    ordem = Ordem.objects.select_for_update().get(pk=ordem_id, tenant_id=tenant_id)
    if tipo_entrega not in ('entrega', 'retirada'):
        raise ValidationError('Selecione entrega ou retirada.')
    if ordem.status not in ('novo', 'confirmado', 'processando'):
        raise ValidationError('Não é possível alterar a modalidade nesta etapa.')
    ordem.tipo_entrega = tipo_entrega
    ordem.save(update_fields=['tipo_entrega'])
    return ordem


@transaction.atomic
def change_payment(*, ordem_id, tenant_id, status_pagamento, usuario):
    _check_user(usuario, tenant_id)
    ordem = Ordem.objects.select_for_update().get(pk=ordem_id, tenant_id=tenant_id)
    allowed = {'pendente': {'pago', 'cancelado'}, 'pago': {'estornado'},
               'cancelado': {'pendente'}, 'estornado': set()}
    if status_pagamento != ordem.status_pagamento and status_pagamento not in allowed[ordem.status_pagamento]:
        raise ValidationError('Esta alteração de pagamento não é permitida.')
    if status_pagamento == ordem.status_pagamento:
        return ordem
    ordem.status_pagamento = status_pagamento
    ordem.save(update_fields=['status_pagamento'])
    from whatsapp.services.notifications import send_payment_status_message
    transaction.on_commit(
        lambda order_id=ordem.pk: send_payment_status_message(order_id),
        robust=True,
    )
    return ordem


def get_whatsapp_message(ordem):
    number = ordem.pk
    status = ordem.status
    if status == 'cancelado':
        return f'Seu pedido nº {number} foi cancelado. Entre em contato conosco caso tenha alguma dúvida.'
    if status == 'novo':
        return f'Olá! Recebemos seu pedido nº {number}.'
    if ordem.tipo_entrega == 'a_combinar' and status in ('pronto', 'concluido'):
        return f'Seu pedido nº {number} ' + ('está pronto. Combine a entrega ou retirada com a loja.' if status == 'pronto' else 'foi concluído. Obrigado pela preferência!')
    if ordem.tipo_operacao == 'delivery':
        messages = {
            'confirmado': f'Olá! Seu pedido nº {number} foi confirmado.',
            'processando': f'Olá! Seu pedido nº {number} foi recebido e já está sendo preparado.',
            'pronto': f'Seu pedido nº {number} está pronto' + (' para retirada.' if ordem.tipo_entrega == 'retirada' else '.'),
            'enviado': f'Seu pedido nº {number} saiu para entrega.',
            'concluido': f'Seu pedido nº {number} foi concluído. Obrigado pela preferência!',
        }
    else:
        final = 'retirado' if ordem.tipo_entrega == 'retirada' else 'entregue'
        ready = 'retirada' if ordem.tipo_entrega == 'retirada' else 'envio'
        messages = {
            'confirmado': f'Olá! Seu pedido nº {number} foi confirmado.',
            'processando': f'Estamos separando os produtos do seu pedido nº {number}.',
            'pronto': f'Seu pedido nº {number} está pronto para {ready}.',
            'enviado': f'Seu pedido nº {number} foi enviado.',
            'concluido': f'Seu pedido nº {number} foi concluído como {final}. Obrigado pela preferência!',
        }
    return messages.get(status, f'Seu pedido nº {number}: {get_status_label(ordem)}.')


def get_whatsapp_url(ordem):
    if not ordem.cliente or ordem.cliente.tenant_id != ordem.tenant_id:
        return ''
    phone = re.sub(r'\D', '', ordem.cliente.telefone or '')
    if len(phone) in (10, 11):
        phone = '55' + phone
    if not 12 <= len(phone) <= 15:
        return ''
    return 'https://wa.me/' + phone + '?' + urlencode({'text': get_whatsapp_message(ordem)})
